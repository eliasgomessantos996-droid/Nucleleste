"""Integração com o portal Medcloud: ao lançar um atendimento de convênio marcado, um robô cria o acesso do paciente.

O acesso (usuário, senha e QR de login) fica em `medcloud_acessos` e a senha vai cifrada. Os pedidos ficam em
`medcloud_fila` (um por atendimento) e são processados em segundo plano por `iniciar`. Só funciona com a função
ligada (config `medcloud_ativo` = '1') e com login e senha da Medcloud gravados.
"""
import base64
import hashlib
import hmac
import os
import re
import secrets
import threading
import time
from datetime import date

from . import util
from .db import agora, conectar

TENTATIVAS_MAXIMAS = 3
INTERVALO_FILA = 5          # segundos entre as conferências da fila (acordar() as antecipa)
OCIOSO_MAXIMO = 900         # o navegador logado fica aberto até 15 min sem uso
NAVEGADORES = ('chrome', 'msedge')   # canais do Playwright, na ordem de preferência
ESPERA_NA_TELA = 60        # segundos que a tela de carregamento espera o robô antes de abrir as fichas sem o protocolo
ESPERA_NA_HORA = 12       # quanto o lançamento espera o robô antes de abrir a impressão
TEXTO_LINK_PADRAO = '?page=nucleleste'

_CHAVE = None               # SECRET_KEY da aplicação (definida em create_app); base da cifra das senhas
_PREFIXO = 'v1:'
_TAMANHO_TAG = 16


def definir_chave(chave):
    """Guarda a chave da aplicação para cifrar e decifrar as senhas (chamada em create_app)."""
    global _CHAVE
    _CHAVE = chave.encode('utf-8') if isinstance(chave, str) else chave


def _chaves():
    if not _CHAVE:
        raise RuntimeError('Chave da Medcloud não definida (create_app não foi chamada).')
    enc = hmac.new(_CHAVE, b'medcloud-enc', hashlib.sha256).digest()
    mac = hmac.new(_CHAVE, b'medcloud-mac', hashlib.sha256).digest()
    return enc, mac


def _keystream(chave, nonce, tamanho):
    """HMAC-SHA256(chave, nonce || contador) em blocos de 32 bytes, até cobrir o tamanho pedido."""
    saida = b''
    contador = 0
    while len(saida) < tamanho:
        saida += hmac.new(chave, nonce + contador.to_bytes(8, 'big'), hashlib.sha256).digest()
        contador += 1
    return saida[:tamanho]


def _xor(a, b):
    return bytes(x ^ y for x, y in zip(a, b))


def cifrar(texto):
    """Cifra um texto (stdlib). Token: 'v1:' + base64 urlsafe de nonce (16) + dados cifrados + tag HMAC (16)."""
    enc, mac = _chaves()
    dados = (texto or '').encode('utf-8')
    nonce = secrets.token_bytes(16)
    corpo = nonce + _xor(dados, _keystream(enc, nonce, len(dados)))
    tag = hmac.new(mac, corpo, hashlib.sha256).digest()[:_TAMANHO_TAG]
    return _PREFIXO + base64.urlsafe_b64encode(corpo + tag).decode('ascii')


def decifrar(token):
    """Devolve o texto original, ou '' quando o token é inválido (formato errado, adulterado ou de outra chave)."""
    if not token or not str(token).startswith(_PREFIXO):
        return ''
    enc, mac = _chaves()
    try:
        bruto = token[len(_PREFIXO):]
        bruto += '=' * (-len(bruto) % 4)
        raw = base64.urlsafe_b64decode(bruto.encode('ascii'))
    except (ValueError, UnicodeError):
        return ''
    if len(raw) < 16 + _TAMANHO_TAG:
        return ''
    corpo, tag = raw[:-_TAMANHO_TAG], raw[-_TAMANHO_TAG:]
    if not hmac.compare_digest(tag, hmac.new(mac, corpo, hashlib.sha256).digest()[:_TAMANHO_TAG]):
        return ''
    nonce, cifrado = corpo[:16], corpo[16:]
    try:
        return _xor(cifrado, _keystream(enc, nonce, len(cifrado))).decode('utf-8')
    except UnicodeDecodeError:
        return ''


def _cfg(db, chave, padrao=''):
    row = db.execute('SELECT valor FROM config WHERE chave=?', (chave,)).fetchone()
    return (row['valor'] if row and row['valor'] is not None else padrao)


def ativo(db):
    """Função ligada pela gerência e com login e senha da Medcloud preenchidos."""
    return (_cfg(db, 'medcloud_ativo') == '1' and bool(_cfg(db, 'medcloud_login').strip())
            and bool(_cfg(db, 'medcloud_senha')))


def _minutos(texto):
    """'05:50' -> 350; texto inválido -> None."""
    m = re.fullmatch(r'\s*([01]?\d|2[0-3]):([0-5]\d)\s*', texto or '')
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def dentro_do_horario(db, momento=None):
    """Com o horário de funcionamento ligado, só vale entre o início e o fim, nos dias marcados (0 = segunda ... 6 = domingo).
    Fim menor que o início atravessa a meia-noite. Sem horário ligado (ou configurado de forma inválida), vale o dia todo."""
    if _cfg(db, 'medcloud_horario') != '1':
        return True
    ini, fim = _minutos(_cfg(db, 'medcloud_inicio')), _minutos(_cfg(db, 'medcloud_fim'))
    if ini is None or fim is None:
        return True
    from datetime import datetime
    momento = momento or datetime.now()
    dias = _cfg(db, 'medcloud_dias', '0123456')
    if str(momento.weekday()) not in dias:
        return False
    agora_ = momento.hour * 60 + momento.minute
    return ini <= agora_ < fim if ini <= fim else (agora_ >= ini or agora_ < fim)


def operando(db, momento=None):
    """Função ligada, com login e senha, e dentro do horário de funcionamento."""
    return ativo(db) and dentro_do_horario(db, momento)


def horario_ligado(db):
    return _cfg(db, 'medcloud_horario') == '1' and _minutos(_cfg(db, 'medcloud_inicio')) is not None \
        and _minutos(_cfg(db, 'medcloud_fim')) is not None


def convenio_envia(db, nome):
    """O convênio está marcado para a Medcloud (comparação pelo nome, sem diferenciar maiúsculas)."""
    if not nome:
        return False
    row = db.execute('SELECT medcloud FROM convenios WHERE nome=? COLLATE NOCASE', (nome,)).fetchone()
    return bool(row and row['medcloud'] == 1)


def identificador_do_cliente(cliente):
    """Identificador do acesso: os dígitos do CPF; sem CPF válido (menos de 11 dígitos), os dígitos do contato; senão None."""
    cpf = re.sub(r'\D', '', cliente['cpf'] or '')
    if len(cpf) >= 11:
        return cpf
    contato = re.sub(r'\D', '', cliente['contato'] or '')
    return contato or None


def acesso_do_cliente(db, cliente_id):
    """Acesso já criado para o cliente, com a senha decifrada; None quando não existe."""
    if cliente_id is None:
        return None
    row = db.execute('SELECT usuario, senha, qr, criado_em FROM medcloud_acessos WHERE cliente_id=?', (cliente_id,)).fetchone()
    if not row:
        return None
    return {'usuario': row['usuario'], 'senha': decifrar(row['senha']), 'qr': row['qr'], 'criado_em': row['criado_em']}


def acesso_do_atendimento(db, aid):
    """Acesso (usuário, senha, QR) que VALE PARA ESTE ATENDIMENTO, ou None. Cada atendimento novo cadastra o paciente de novo
    na Medcloud (que gera uma senha nova), e a ficha mostra a senha do próprio atendimento: a ficha antiga mantém a senha
    antiga e a nova traz a nova. Pedido do fluxo novo sem acesso gravado ainda (ou que falhou) não tem protocolo: nunca cai no
    acesso antigo do cliente. Só atendimento sem pedido ou pedido antigo (de antes desta regra) usa o último acesso do cliente."""
    fila = db.execute('SELECT cliente_id, acesso_usuario, acesso_senha, acesso_qr, acesso_modo FROM medcloud_fila '
                      'WHERE atendimento_id=?', (aid,)).fetchone()
    if fila and fila['acesso_usuario']:
        return {'usuario': fila['acesso_usuario'], 'senha': decifrar(fila['acesso_senha'] or ''), 'qr': fila['acesso_qr']}
    if fila and fila['acesso_modo'] == 'proprio':
        return None
    at = fila or db.execute('SELECT cliente_id FROM atendimentos WHERE id=?', (aid,)).fetchone()
    return acesso_do_cliente(db, at['cliente_id']) if at else None


def enfileirar(db, atendimento_id, apenas_hoje=False):
    """Põe o atendimento na fila do robô, que cria o acesso do paciente (se ainda não tiver) E um estudo novo para este
    atendimento, mesmo que o paciente já esteja cadastrado na Medcloud.
    Devolve 'desativado', 'nao_se_aplica', 'pronto' (estudo já criado), 'sem_estudo' (o usuário escolheu imprimir sem o
    estudo), 'erro' ou 'pendente'. Não faz commit.
    `apenas_hoje`: só cria pedido novo para atendimento lançado hoje (reimprimir um atendimento antigo não cria estudo)."""
    if not operando(db):   # desligada ou fora do horário de funcionamento: o atendimento sai sem Medcloud
        return 'desativado'
    at = db.execute('SELECT cliente_id, convenio, criado_em FROM atendimentos WHERE id=?', (atendimento_id,)).fetchone()
    if not at or not convenio_envia(db, at['convenio']) or at['cliente_id'] is None:
        return 'nao_se_aplica'
    fila = db.execute('SELECT estado FROM medcloud_fila WHERE atendimento_id=?', (atendimento_id,)).fetchone()
    if fila:
        return {'OK': 'pronto', 'ERRO': 'erro', 'SEM_ESTUDO': 'sem_estudo'}.get(fila['estado'], 'pendente')
    if apenas_hoje and (at['criado_em'] or '')[:10] != date.today().isoformat():
        return 'nao_se_aplica'
    agora_ = agora()
    db.execute("INSERT OR IGNORE INTO medcloud_fila (atendimento_id, cliente_id, criado_em, atualizado_em, acesso_modo) "
               "VALUES (?,?,?,?,'proprio')", (atendimento_id, at['cliente_id'], agora_, agora_))
    return 'pendente'


def status_atendimento(db, aid):
    """Situação do acesso Medcloud de um atendimento, com o que precisa para a ficha (usuário, senha, QR, link).
    'pronto' só quando o estudo deste atendimento foi criado na Medcloud. Sem estudo, o protocolo só sai na ficha se o
    usuário escolher ('sem_estudo'): aí vai o acesso do paciente, quando ele existe, mas o exame não aparece no portal.
    `tem_acesso`: o paciente já tem acesso criado (define o que a tela de erro oferece)."""
    url = _cfg(db, 'medcloud_url', 'https://medcloud.co').rstrip('/')
    resultado = {'estado': 'nao_se_aplica', 'usuario': None, 'senha': None, 'qr': None, 'erro': None,
                 'link': url + TEXTO_LINK_PADRAO, 'tem_acesso': False}
    at = db.execute('SELECT cliente_id FROM atendimentos WHERE id=?', (aid,)).fetchone()
    if not at:
        return resultado
    resultado['tem_acesso'] = acesso_do_atendimento(db, aid) is not None
    fila = db.execute('SELECT estado, erro, fase, tentativas FROM medcloud_fila WHERE atendimento_id=?', (aid,)).fetchone()
    if fila and fila['estado'] in ('PENDENTE', 'PROCESSANDO'):
        resultado.update(estado='pendente', fase=fila['fase'] or 'Na fila', tentativas=fila['tentativas'], erro=fila['erro'])
    elif fila and fila['estado'] == 'ERRO':
        resultado.update(estado='erro', erro=fila['erro'])
    elif fila and fila['estado'] in ('OK', 'SEM_ESTUDO'):
        acesso = acesso_do_atendimento(db, aid)
        estado = 'pronto' if fila['estado'] == 'OK' else 'sem_estudo'
        if acesso:
            resultado.update(estado=estado, usuario=acesso['usuario'], senha=acesso['senha'], qr=acesso['qr'])
        elif estado == 'sem_estudo':
            resultado['estado'] = estado   # escolheu imprimir sem estudo e o acesso não chegou a ser criado: sem protocolo
    elif not operando(db):
        resultado['estado'] = 'desativado'
    return resultado


def protocolo_do_atendimento(db, aid):
    """Protocolo de acesso para a ficha de um atendimento (também na REIMPRESSÃO): o acesso que o paciente já tem, quando o
    atendimento é de convênio marcado para a Medcloud ou já passou pela fila. Não cria nada e não depende do estudo nem do
    horário de funcionamento. None quando não há protocolo a imprimir."""
    at = db.execute('SELECT cliente_id, convenio FROM atendimentos WHERE id=?', (aid,)).fetchone()
    if not at or at['cliente_id'] is None:
        return None
    na_fila = db.execute('SELECT 1 FROM medcloud_fila WHERE atendimento_id=?', (aid,)).fetchone()
    if not na_fila and not convenio_envia(db, at['convenio']):
        return None
    acesso = acesso_do_atendimento(db, aid)
    if not acesso:
        return None
    return {'usuario': acesso['usuario'], 'senha': acesso['senha'], 'qr': acesso['qr']}


def tentar_de_novo(db, aid):
    """Volta um pedido com erro (ou impresso sem estudo) para a fila (zera erro e tentativas). Não faz commit.
    Devolve True se voltou."""
    cur = db.execute("UPDATE medcloud_fila SET estado='PENDENTE', erro=NULL, tentativas=0, fase=NULL, atualizado_em=? "
                     "WHERE atendimento_id=? AND estado IN ('ERRO','SEM_ESTUDO')", (agora(), aid))
    return cur.rowcount > 0


def imprimir_sem_estudo(db, aid):
    """O usuário escolheu imprimir as fichas SEM o estudo (com o protocolo de acesso, se o paciente tiver acesso).
    Só vale para pedido com erro ou ainda na fila; cancela a tentativa. Não faz commit. Devolve True se registrou."""
    cur = db.execute("UPDATE medcloud_fila SET estado='SEM_ESTUDO', fase=NULL, atualizado_em=? "
                     "WHERE atendimento_id=? AND estado IN ('ERRO','PENDENTE','PROCESSANDO')", (agora(), aid))
    return cur.rowcount > 0


def _mensagem_curta(exc):
    texto = ' '.join(str(exc).split())[:200]
    return texto or exc.__class__.__name__


def _fechar(robo):
    try:
        robo.fechar()
    except Exception:
        pass


def processar_proxima(con, criar_robo):
    """Processa o pedido PENDENTE mais antigo. `criar_robo(login, senha, url)` devolve um objeto com `criar_acesso` e `fechar`.
    Faz commit. Devolve True se processou algum pedido, False se a fila está vazia."""
    pedido = con.execute("SELECT id, atendimento_id, cliente_id, tentativas FROM medcloud_fila "
                         "WHERE estado='PENDENTE' AND tentativas<? ORDER BY criado_em, id LIMIT 1",
                         (TENTATIVAS_MAXIMAS,)).fetchone()
    if not pedido:
        return False
    con.execute("UPDATE medcloud_fila SET estado='PROCESSANDO', atualizado_em=? WHERE id=?", (agora(), pedido['id']))
    con.commit()
    try:
        cli = con.execute('SELECT nome, cpf, contato, cidade, uf, data_nasc FROM clientes WHERE id=?',
                          (pedido['cliente_id'],)).fetchone()
        at = con.execute('SELECT exame, data, cliente_nome FROM atendimentos WHERE id=?', (pedido['atendimento_id'],)).fetchone()
        ident = identificador_do_cliente(cli) if cli else None
        nasc = util.para_data(cli['data_nasc']) if cli else None
        data_estudo = util.para_data(at['data']) if at else None
        problema = None
        if not ident:
            problema = 'Cliente sem CPF nem celular'
        elif not nasc:
            problema = 'Cliente sem data de nascimento válida (a Medcloud exige para criar o estudo)'
        elif not data_estudo or not (at['exame'] or '').strip():
            problema = 'Atendimento sem data ou sem exame'
        if problema:
            # dado que falta no cadastro: tentar de novo não resolve; vai direto para ERRO (corrija e use "Tentar de novo")
            con.execute("UPDATE medcloud_fila SET estado='ERRO', tentativas=tentativas+1, erro=?, atualizado_em=? "
                        "WHERE id=? AND estado='PROCESSANDO'", (problema, agora(), pedido['id']))
            con.commit()
            return True
        login = _cfg(con, 'medcloud_login').strip()
        senha = decifrar(_cfg(con, 'medcloud_senha'))
        url = _cfg(con, 'medcloud_url', 'https://medcloud.co').rstrip('/')
        if not login or not senha:
            raise Exception('Login ou senha da Medcloud não configurados')
        robo = criar_robo(login, senha, url)

        def gravar_fase(texto):   # a tela de carregamento mostra em que etapa o robô está
            con.execute('UPDATE medcloud_fila SET fase=?, atualizado_em=? WHERE id=?', (texto, agora(), pedido['id']))
            con.commit()
        gravar_fase('Iniciando')
        robo.progresso = gravar_fase
        try:
            # CADA atendimento novo pega o protocolo da hora (a senha de um acesso antigo pode ter mudado e não há como conferir):
            # paciente que já existe na Medcloud tem os dados de login reenviados (mesmo usuário, senha nova); só o que não
            # existe é cadastrado. O acesso é gravado NO PEDIDO na hora: se o estudo falhar, a nova tentativa deste mesmo
            # atendimento não pede outra senha. Atendimentos antigos e as fichas já impressas não mudam.
            ja_gravado = con.execute('SELECT acesso_usuario FROM medcloud_fila WHERE id=?', (pedido['id'],)).fetchone()
            if not (ja_gravado and ja_gravado['acesso_usuario']):
                acesso = robo.obter_acesso(cli['nome'], ident, cli['cidade'] or '', cli['uf'] or '')
                senha_cifrada = cifrar(acesso['senha'])
                con.execute("UPDATE medcloud_fila SET acesso_usuario=?, acesso_senha=?, acesso_qr=?, acesso_modo='proprio' WHERE id=?",
                            (acesso['usuario'], senha_cifrada, acesso.get('qr'), pedido['id']))
                # também fica como "último acesso do cliente" (usado só por atendimentos antigos, sem pedido próprio)
                con.execute('INSERT OR REPLACE INTO medcloud_acessos (cliente_id, usuario, senha, qr, criado_em, atendimento_id) '
                            'VALUES (?,?,?,?,?,?)',
                            (pedido['cliente_id'], acesso['usuario'], senha_cifrada, acesso.get('qr'), agora(),
                             pedido['atendimento_id']))
                con.commit()
            # estudo novo para ESTE atendimento (mesmo que o paciente já estivesse cadastrado): modalidade NM, estudo = exame,
            # data = data do atendimento; o ID do paciente é gerado pela própria Medcloud
            estudo = robo.criar_estudo(cli['nome'], nasc.strftime('%d/%m/%Y'), data_estudo.strftime('%d/%m/%Y'),
                                       at['exame'].strip())
        except Exception:
            _fechar(robo)   # a sessão pode estar quebrada: a próxima tentativa abre outra
            raise
        # (só se o pedido ainda é desta rodada: se o usuário escolheu "imprimir sem o estudo" nesse meio tempo, a escolha vale)
        # estudo criado: a ficha já pode sair. O vínculo do estudo com o acesso do paciente (compartilhar) fica para o segundo plano
        con.execute("UPDATE medcloud_fila SET estado='OK', erro=NULL, estudo=?, fase='Pronto', atualizado_em=?, "
                    "compartilhado=?, comp_tentativas=0, comp_erro=NULL WHERE id=? AND estado='PROCESSANDO'",
                    (str(estudo or ''), agora(), 'PENDENTE' if estudo else None, pedido['id']))
        con.commit()
    except Exception as exc:
        con.rollback()
        erro = _mensagem_curta(exc)
        con.execute("UPDATE medcloud_fila SET tentativas=tentativas+1, erro=?, atualizado_em=?, fase='Tentando de novo', "
                    "estado=CASE WHEN tentativas+1<? THEN 'PENDENTE' ELSE 'ERRO' END WHERE id=? AND estado='PROCESSANDO'",
                    (erro, agora(), TENTATIVAS_MAXIMAS, pedido['id']))
        con.commit()
    return True


def tentar_compartilhar_de_novo(db, aid):
    """Recoloca na fila o vínculo (compartilhamento) que deu erro. Não faz commit. Devolve True se voltou."""
    cur = db.execute("UPDATE medcloud_fila SET compartilhado='PENDENTE', comp_tentativas=0, comp_erro=NULL, atualizado_em=? "
                     "WHERE atendimento_id=? AND estado='OK' AND compartilhado='ERRO'", (agora(), aid))
    return cur.rowcount > 0


def compartilhar_proximo(con, criar_robo):
    """Segundo plano: vincula o estudo já criado ao acesso do paciente (na Medcloud, estudo e usuário não se conversam; é o
    'Compartilhar' do estudo com o paciente que faz o estudo aparecer no portal dele). Roda DEPOIS da ficha, sem travar nada.
    Faz commit. Devolve True se tentou algum vínculo, False se não há nenhum pendente."""
    pedido = con.execute("SELECT id, atendimento_id, cliente_id, estudo FROM medcloud_fila WHERE estado='OK' AND compartilhado='PENDENTE' "
                         "AND comp_tentativas<? ORDER BY id LIMIT 1", (TENTATIVAS_MAXIMAS,)).fetchone()
    if not pedido:
        return False
    con.execute("UPDATE medcloud_fila SET compartilhado='PROCESSANDO', atualizado_em=? WHERE id=? AND compartilhado='PENDENTE'",
                (agora(), pedido['id']))
    con.commit()
    try:
        cli = con.execute('SELECT nome FROM clientes WHERE id=?', (pedido['cliente_id'],)).fetchone()
        acesso = acesso_do_atendimento(con, pedido['atendimento_id'])
        if not cli or not acesso or not pedido['estudo']:
            # sem acesso ou sem estudo não há o que vincular: tentar de novo não resolve
            con.execute("UPDATE medcloud_fila SET compartilhado='ERRO', comp_erro=?, atualizado_em=? "
                        "WHERE id=? AND compartilhado='PROCESSANDO'",
                        ('Paciente sem acesso à Medcloud ou estudo sem ID', agora(), pedido['id']))
            con.commit()
            return True
        login = _cfg(con, 'medcloud_login').strip()
        senha = decifrar(_cfg(con, 'medcloud_senha'))
        url = _cfg(con, 'medcloud_url', 'https://medcloud.co').rstrip('/')
        if not login or not senha:
            raise Exception('Login ou senha da Medcloud não configurados')
        robo = criar_robo(login, senha, url)
        robo.progresso = None   # a etapa gravada pertence ao pedido anterior: aqui nada aparece na tela da recepção
        try:
            robo.compartilhar_estudo(pedido['estudo'], cli['nome'], acesso['usuario'])
        except Exception:
            _fechar(robo)
            raise
        con.execute("UPDATE medcloud_fila SET compartilhado='OK', comp_erro=NULL, atualizado_em=? "
                    "WHERE id=? AND compartilhado='PROCESSANDO'", (agora(), pedido['id']))
        con.commit()
    except Exception as exc:
        con.rollback()
        con.execute("UPDATE medcloud_fila SET comp_tentativas=comp_tentativas+1, comp_erro=?, atualizado_em=?, "
                    "compartilhado=CASE WHEN comp_tentativas+1<? THEN 'PENDENTE' ELSE 'ERRO' END "
                    "WHERE id=? AND compartilhado='PROCESSANDO'", (_mensagem_curta(exc), agora(), TENTATIVAS_MAXIMAS, pedido['id']))
        con.commit()
    return True


class _SessaoReusada:
    """Mantém o robô aberto e já logado (o cadastro fica rápido); fecha só depois de OCIOSO_MAXIMO segundos sem uso."""

    def __init__(self):
        self.robo = None
        self.ultimo_uso = time.monotonic()
        self.proxima_tentativa = 0.0     # depois de uma falha ao abrir/logar, só tenta o aquecimento automático após este instante

    def __call__(self, login, senha, url):
        if self.robo is None or getattr(self.robo, 'fechado', False):
            self.robo = RoboPlaywright(login, senha, url)
        self.ultimo_uso = time.monotonic()
        return self.robo

    def fechar(self):
        if self.robo is not None:
            _fechar(self.robo)
            self.robo = None

    def fechar_se_ocioso(self):
        if self.robo is not None and time.monotonic() - self.ultimo_uso > OCIOSO_MAXIMO:
            self.fechar()


# O laço dorme neste evento: `acordar()` o desperta na hora (sem esperar o intervalo da fila).
_ACORDAR = threading.Event()
_AQUECER = threading.Event()
_LACO_ATIVO = False


def acordar():
    """Avisa o robô que há pedido novo na fila (processa agora, sem esperar a próxima conferência)."""
    _ACORDAR.set()


def aquecer_se_ativo(db):
    """Abre o navegador e faz o login antes do pedido chegar (chamado quando a recepção abre a tela de lançar atendimento)."""
    if _LACO_ATIVO and operando(db):
        _AQUECER.set()
        _ACORDAR.set()


def aguardar_acesso(caminho_banco, atendimento_id, limite=ESPERA_NA_HORA):
    """Espera, por até `limite` segundos, o robô terminar o pedido do atendimento. Devolve o estado final ('pronto',
    'erro', ...) ou 'pendente' se passou do tempo (a impressão segue consultando). Sem o laço ligado (testes, CLI) não espera."""
    if not _LACO_ATIVO:
        return 'pendente'
    acordar()
    fim = time.monotonic() + limite
    estado = 'pendente'
    while time.monotonic() < fim:
        con = conectar(caminho_banco)
        try:
            estado = status_atendimento(con, atendimento_id)['estado']
        finally:
            con.close()
        if estado != 'pendente':
            return estado
        time.sleep(0.2)
    return estado


def parar():
    """Encerra o laço em segundo plano (usado nos testes)."""
    global _LACO_ATIVO
    _LACO_ATIVO = False
    _ACORDAR.set()


def iniciar(caminho_banco):
    """Thread em segundo plano que processa a fila assim que `acordar()` é chamado (ou a cada INTERVALO_FILA segundos).
    Só processa com a função ativa. Qualquer exceção é engolida: o laço segue na próxima rodada."""
    global _LACO_ATIVO
    from . import medcloud_envios
    try:   # vínculo e envio que ficaram "processando" porque o servidor caiu no meio: voltam para a fila
        con0 = conectar(caminho_banco)
        try:
            con0.execute("UPDATE medcloud_fila SET compartilhado='PENDENTE' WHERE compartilhado='PROCESSANDO'")
            con0.commit()
            medcloud_envios.recolocar_travados(con0)
        finally:
            con0.close()
    except Exception:
        pass

    def laco():
        sessao = _SessaoReusada()
        while _LACO_ATIVO:
            try:
                con = conectar(caminho_banco)
                try:
                    if operando(con):
                        # com horário de funcionamento, o navegador abre e loga sozinho no início e fica aberto até o fim
                        aquecer = _AQUECER.is_set() or (horario_ligado(con) and sessao.robo is None
                                                        and time.monotonic() >= sessao.proxima_tentativa)
                        if aquecer:
                            _AQUECER.clear()
                            try:
                                sessao(_cfg(con, 'medcloud_login').strip(), decifrar(_cfg(con, 'medcloud_senha')),
                                       _cfg(con, 'medcloud_url', 'https://medcloud.co').rstrip('/')).entrar()
                            except Exception:
                                sessao.fechar()
                                sessao.proxima_tentativa = time.monotonic() + 60   # sem internet ou login recusado: tenta de novo em 1 min
                        # esvazia a fila de uma vez (o navegador continua aberto e logado). Pedido novo de atendimento tem
                        # prioridade; o vínculo do estudo com o paciente (compartilhar) só roda quando não há pedido esperando
                        # (o envio de anexos e laudos vem por último: arquivo grande não atrasa o cadastro de quem está na clínica)
                        # (quem pediu para baixar um arquivo está esperando na tela: o download passa na frente do envio)
                        while (processar_proxima(con, sessao) or compartilhar_proximo(con, sessao)
                               or medcloud_envios.processar_download(con, sessao)
                               or medcloud_envios.processar_proximo(con, sessao)):
                            pass
                        if not horario_ligado(con):
                            sessao.fechar_se_ocioso()
                    else:
                        sessao.fechar()   # desligada ou fora do horário (ex.: depois das 19h): fecha o navegador
                finally:
                    con.close()
            except Exception:
                sessao.fechar()     # sessão possivelmente quebrada: a próxima rodada abre outra
            _ACORDAR.wait(INTERVALO_FILA)
            _ACORDAR.clear()
        sessao.fechar()
    _LACO_ATIVO = True
    threading.Thread(target=laco, name='medcloud-robo', daemon=True).start()


class RoboPlaywright:
    """Robô que opera o portal Medcloud com Chromium headless. O playwright só é importado quando usado."""

    def __init__(self, login, senha, url):
        self.login = login
        self.senha = senha
        self.url = url.rstrip('/')
        self.fechado = False
        self._pw = None
        self._browser = None
        self._page = None
        self._logado = False
        self.progresso = None      # função(texto) que quem usa o robô define para saber em que etapa ele está

    def _fase(self, texto):
        if self.progresso:
            try:
                self.progresso(texto)
            except Exception:
                pass

    def _abrir(self):
        if self._page is not None:
            return
        self._fase('Abrindo o navegador')
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise Exception('Pacote playwright não instalado neste computador (a integração só vai na versão de 64 bits)')
        self._pw = sync_playwright().start()
        # usa o navegador do computador: Google Chrome primeiro, Microsoft Edge como reserva (nada é baixado)
        for canal in NAVEGADORES:
            try:
                self._browser = self._pw.chromium.launch(channel=canal, headless=True)
                break
            except Exception:
                self._browser = None
        if self._browser is None:
            self._pw.stop()
            self._pw = None
            raise Exception('Google Chrome (ou Microsoft Edge) não encontrado neste computador')
        self._page = self._browser.new_page()
        # só o texto do protocolo e o QR (imagem embutida) interessam: não baixa fontes, mídia nem imagens externas
        self._page.route('**/*', lambda rota: rota.abort()
                         if rota.request.resource_type in ('image', 'media', 'font') else rota.continue_())

    def entrar(self):
        """Faz o login na Medcloud (uma vez por sessão do robô)."""
        self._abrir()
        if self._logado:
            return
        p = self._page
        self._fase('Entrando na Medcloud')
        p.goto(self.url + '/app/do/guest', timeout=30000)
        # na Medcloud "Usuário" e "Senha" são rótulos flutuantes (não placeholder): os campos são achados pelo id
        p.locator('#usernameInput').fill(self.login, timeout=20000)
        p.locator('#passwordInput').fill(self.senha, timeout=20000)
        p.locator('#submitLogin').click()
        try:
            p.locator('a:has-text("Estudos")').first.wait_for(state='visible', timeout=20000)
        except Exception:
            raise Exception('Login recusado pela Medcloud')
        self._logado = True

    def criar_acesso(self, nome, identificador, cidade, uf):
        """Cria o cadastro do paciente (versão sem email) e devolve {usuario, senha, qr}."""
        self.entrar()
        p = self._page
        self._fase('Cadastrando o paciente')
        campo_nome = p.locator('input[name="name"]')
        p.goto(self.url + '/app/signup/newpatient2.jsp', timeout=30000, wait_until='domcontentloaded')
        if campo_nome.count() == 0:
            # sessão expirada (a Medcloud devolveu a tela de login): entra de novo e repete uma vez
            self._logado = False
            self.entrar()
            p.goto(self.url + '/app/signup/newpatient2.jsp', timeout=30000, wait_until='domcontentloaded')
        campo_nome.fill(nome)
        p.locator('input[name="cellphone"]').fill(re.sub(r'\D', '', identificador))
        p.locator('input[name="city"]').fill(cidade or '')
        p.locator('input[name="state"]').fill(uf or '')
        p.locator('[value="Criar conta e gerar protocolo de acesso"]').click()
        return self._ler_protocolo()

    def _ler_protocolo(self):
        """Lê o bloco #access-protocol (cadastro novo OU reenvio de dados de login têm o mesmo formato): {usuario, senha, qr}."""
        p = self._page
        self._fase('Gerando o protocolo de acesso')
        protocolo = p.locator('#access-protocol')
        try:
            protocolo.wait_for(state='visible', timeout=30000)
        except Exception:
            raise Exception(self._mensagem_da_pagina() or 'A Medcloud não gerou o protocolo de acesso')
        texto = protocolo.inner_text()
        usuario = re.search(r'USU[AÁ]RIO:\s*(\S+)', texto)
        senha = re.search(r'SENHA:\s*(\S+)', texto)
        if not usuario or not senha:
            raise Exception(self._mensagem_da_pagina() or 'Protocolo de acesso sem usuário ou senha')
        qr = None   # (só o QR de login, imagem embutida; o reenvio traz apenas o QR fixo do aplicativo, que não é usado)
        imagens = protocolo.locator('img')
        if imagens.count() >= 3:
            src = imagens.nth(2).get_attribute('src') or ''
            if src.startswith('data:image'):
                qr = src
        return {'usuario': usuario.group(1), 'senha': senha.group(1), 'qr': qr}

    def reenviar_acesso(self, nome, identificador):
        """Paciente que JÁ existe na Medcloud: aperta "Reenviar novos dados de login para o usuário" (Gerenciar contas > Buscar
        paciente), que gera uma senha nova para o MESMO usuário, e devolve o protocolo {usuario, senha, qr}. Devolve None se o
        paciente não foi encontrado (aí o chamador cadastra). A busca é pelo nome (pelo número a Medcloud não acha) e só o botão
        da linha cujo e-mail é "<ID>@medcloud.com.br" é apertado."""
        self.entrar()
        p = self._page
        self._fase('Localizando o paciente')
        alvo = re.sub(r'\D', '', identificador)
        botao = None
        for busca in self._buscas_do_paciente(nome):
            p.goto(self.url + '/app/signup/patients.jsp', timeout=30000, wait_until='domcontentloaded')
            if p.locator('#usernameInput').count():   # sessão expirada: entra de novo e repete a busca
                self._logado = False
                self.entrar()
                p.goto(self.url + '/app/signup/patients.jsp', timeout=30000, wait_until='domcontentloaded')
            with p.expect_navigation(wait_until='domcontentloaded', timeout=30000):
                p.evaluate("""(nome) => { const f = document.userForm; f.name.value = nome;
                                          f.op.value = 'consultPatientByNameEmail'; f.target = '_self'; f.submit(); }""", busca)
            candidato = p.locator('a[href*="resetAccount"][href*="%s@medcloud.com.br"]' % alvo)
            if candidato.count() >= 1:
                botao = candidato.first
                break
        if botao is None:
            return None
        self._fase('Gerando o protocolo de acesso')
        botao.click()
        return self._ler_protocolo()

    def obter_acesso(self, nome, identificador, cidade, uf):
        """Protocolo de acesso da hora: se o paciente já existe, pede novos dados de login (mesmo usuário, senha nova); se não
        existe, cadastra. Nunca cadastra um paciente que já existe e nunca reaproveita uma senha antiga."""
        acesso = self.reenviar_acesso(nome, identificador)
        if acesso is not None:
            return acesso
        return self.criar_acesso(nome, identificador, cidade, uf)

    # JS que lê a lista de estudos da tela: {id do estudo: texto da linha em maiúsculas}. A linha é o maior ancestral do link
    # do estudo que ainda não contém outro estudo.
    _JS_ESTUDOS = """() => {
        const re = /[?&]id=(\\d+)/, res = {};
        document.querySelectorAll('a[href*="/app/viewer/?id="]').forEach((a) => {
            const m = re.exec(a.getAttribute('href') || ''); if (!m || res[m[1]] !== undefined) return;
            let el = a, texto = '';
            for (let i = 0; i < 8 && el.parentElement; i++) {
                el = el.parentElement;
                const ids = new Set([...el.querySelectorAll('a[href*="/app/viewer/?id="]')].map((x) => (re.exec(x.getAttribute('href') || '') || [])[1]));
                if (ids.size > 1) break;
                texto = el.innerText || '';
            }
            res[m[1]] = texto.replace(/\\s+/g, ' ').toUpperCase();
        });
        return res;
    }"""

    def _ir_para_inicio(self):
        """Abre a tela inicial da Medcloud (onde existe o formulário de busca e o de novo estudo). Se a sessão expirou, entra de novo."""
        p = self._page
        p.goto(self.url + '/app/do/guest', timeout=30000, wait_until='domcontentloaded')
        if p.locator('#usernameInput').count():
            self._logado = False
            self.entrar()

    def _estudos_do_paciente(self, nome):
        """Estudos que a Medcloud tem para o paciente (busca por nome da barra superior): {id: texto da linha}."""
        p = self._page
        self._ir_para_inicio()
        with p.expect_navigation(wait_until='domcontentloaded', timeout=30000):
            p.evaluate("""(nome) => { const f = document.virtualFilmForm; f.patientID.value = ''; f.patientName.value = nome;
                                       f.op.value = 'consultByPatientNameOnMenuBar'; f.submit(); }""", nome)
        return p.evaluate(self._JS_ESTUDOS)

    def criar_estudo(self, nome, nascimento, data_estudo, exame):
        """Cria um estudo novo para o paciente (mesmo que ele já tenha outros): modalidade NM, 'Estudo' = nome do exame,
        data do estudo = data do atendimento; o ID do paciente é gerado pela própria Medcloud. Só devolve o ID do estudo
        depois de confirmar que ele apareceu na lista do paciente; senão levanta exceção (o pedido é tentado de novo)."""
        self.entrar()
        p = self._page
        self._fase('Criando o estudo')
        antes = self._estudos_do_paciente(nome)
        self._ir_para_inicio()
        with p.expect_navigation(wait_until='domcontentloaded', timeout=30000):
            p.evaluate("() => { const f = document.virtualFilmForm; f.op.value = 'insertReportForm'; f.target = '_self'; f.submit(); }")
        p.locator('input[name="studyDecription"]').wait_for(state='visible', timeout=20000)
        # a barra de busca do topo também se chama patientName (id search-query-N): só o campo do formulário interessa
        p.locator('input[name="patientName"]:not([id^="search-query"])').fill(nome)
        p.locator('input[name="patientBirthDate"]').fill(nascimento)
        p.locator('input[name="studyDate"]').fill(data_estudo)
        p.locator('select[name="modality"]').select_option('NM')
        p.locator('input[name="studyDecription"]').fill(exame)      # (o nome do campo na Medcloud é mesmo "studyDecription")
        # o campo "ID" (patientID) NÃO é tocado: a Medcloud gera o ID do paciente sozinha
        with p.expect_navigation(wait_until='domcontentloaded', timeout=30000):
            p.locator('a:has-text("Salvar estudo")').first.click()
        erro_da_tela = self._mensagem_da_pagina()
        self._fase('Conferindo o estudo')
        depois = self._estudos_do_paciente(nome)
        novos = {i: t for i, t in depois.items() if i not in antes}
        alvo = nome.upper()
        confirmados = [i for i, t in novos.items() if alvo in t or not t]
        if not confirmados:
            raise Exception(erro_da_tela or 'A Medcloud não confirmou a criação do estudo')
        return max(confirmados, key=int)

    def _abrir_form_do_estudo(self, op, estudo_id):
        """Faz o que os ícones da linha do estudo fazem: preenche o formulário da lista com a operação e o ID do estudo."""
        p = self._page
        with p.expect_navigation(wait_until='domcontentloaded', timeout=30000):
            p.evaluate("""([op, id]) => { const f = document.virtualFilmForm; f.op.value = op; f.id.value = id;
                                          f.target = '_self'; f.submit(); }""", [op, str(estudo_id)])

    def _arquivos_anexados(self, nome_arquivo):
        """Quantas vezes o nome do arquivo aparece na tela "Anexos" do estudo."""
        alvo = nome_arquivo.lower()
        textos = self._page.locator('a').all_inner_texts()
        return sum(1 for t in textos if alvo in ' '.join(t.split()).lower())

    def enviar_anexo(self, estudo_id, nome_arquivo, conteudo, content_type=None):
        """Leva um arquivo ao estudo como "Anexar arquivo como anexo" (o paciente vê no portal; o laudo em arquivo vai pelo
        mesmo botão). Sequência: clipe (Anexos do estudo) > seta de enviar arquivos > "Anexar arquivo como anexo" > escolhe
        o arquivo. Só devolve depois que o envio foi aceito pelo uploader E o nome aparece na lista de Anexos do estudo."""
        self.entrar()
        p = self._page
        self._ir_para_inicio()
        self._fase('Abrindo os anexos do estudo')
        self._abrir_form_do_estudo('listAttachments', estudo_id)
        antes = self._arquivos_anexados(nome_arquivo)
        # seta "Anexar novos arquivos ao estudo" da barra de ícones
        with p.expect_navigation(wait_until='domcontentloaded', timeout=30000):
            p.locator('a:has(i:text-is("file_upload"))').first.click()
        # botão "Anexar arquivo como anexo" (não o "privado": o texto tem de ser exatamente esse)
        with p.expect_navigation(wait_until='domcontentloaded', timeout=30000):
            p.locator('a.btn', has_text=re.compile(r'^\s*Anexar arquivo como anexo\s*$')).first.click()
        self._fase('Enviando o arquivo')
        campo = p.locator('input[name="qqfile"]')
        campo.wait_for(state='attached', timeout=20000)
        campo.set_input_files({'name': nome_arquivo, 'mimeType': content_type or 'application/octet-stream', 'buffer': conteudo})
        # o uploader marca o item da lista com qq-upload-success (ou qq-upload-fail)
        try:
            p.locator('.qq-upload-success, .qq-upload-fail').first.wait_for(state='attached', timeout=180000)
        except Exception:
            raise Exception('A Medcloud não confirmou o envio do arquivo (demorou demais)')
        if p.locator('.qq-upload-fail').count():
            raise Exception('A Medcloud recusou o arquivo %s' % nome_arquivo)
        self._fase('Conferindo o anexo')
        self._abrir_form_do_estudo('listAttachments', estudo_id)
        depois = self._arquivos_anexados(nome_arquivo)
        if depois < 1 or depois < antes:
            raise Exception('O arquivo não apareceu na lista de anexos do estudo')

    def baixar_anexo(self, estudo_id, nome_arquivo):
        """Baixa da Medcloud um arquivo anexado ao estudo e devolve os bytes. Abre a tela "Anexos" do estudo, acha o link cujo
        texto contém o nome do arquivo e baixa pelo endereço do link (com o login do robô); se isso não devolver um arquivo,
        clica no link e captura o download do navegador.
        ATENÇÃO: escrito a partir do que o robô já faz em `enviar_anexo`; NÃO foi testado contra a Medcloud real."""
        from urllib.parse import urljoin
        self.entrar()
        p = self._page
        self._ir_para_inicio()
        self._fase('Baixando o arquivo da Medcloud')
        self._abrir_form_do_estudo('listAttachments', estudo_id)
        alvo = nome_arquivo.lower()
        link = None
        for cand in p.locator('a').all():
            try:
                if alvo in ' '.join(cand.inner_text().split()).lower():
                    link = cand
                    break
            except Exception:
                continue
        if link is None:
            raise Exception('O arquivo não foi encontrado nos anexos do estudo na Medcloud')
        href = link.get_attribute('href') or ''
        if href and not href.lower().startswith(('javascript:', '#')):
            try:
                resp = p.context.request.get(urljoin(p.url, href), timeout=120000)
                tipo = (resp.headers.get('content-type') or '').lower()
                corpo = resp.body() if resp.ok else b''
                if corpo and 'text/html' not in tipo:
                    return corpo
            except Exception:
                pass   # cai no clique abaixo
        import tempfile
        with p.expect_download(timeout=120000) as d:
            link.click()
        with tempfile.TemporaryDirectory() as pasta:
            destino = os.path.join(pasta, 'baixado')
            d.value.save_as(destino)
            with open(destino, 'rb') as f:
                return f.read()

    @staticmethod
    def _buscas_do_paciente(nome):
        """Textos para digitar na busca de destinatário (do mais específico ao mais amplo): nome inteiro, dois primeiros nomes, primeiro nome."""
        partes = nome.split()
        buscas = []
        for b in (' '.join(partes), ' '.join(partes[:2]), partes[0] if partes else ''):
            if b and b not in buscas:
                buscas.append(b)
        return buscas

    def compartilhar_estudo(self, estudo_id, nome, usuario):
        """Vincula o estudo ao acesso do paciente: abre 'Compartilhar estudo' (ícone de compartilhar da linha do estudo), escolhe o
        destinatário Paciente na sugestão 'Nome <ID@medcloud.com.br>' (a que tem o ID do acesso, o CPF/celular), clica em
        'Compartilhar' e depois em 'Confirmar e enviar'. Levanta exceção se não achar o paciente na sugestão. Depois do
        'Confirmar e enviar' NÃO repete nada (para não compartilhar duas vezes): só acusa erro se a página mostrar um aviso de erro."""
        self.entrar()
        p = self._page
        avisos = []

        def ao_dialogo(dialogo):   # a Medcloud usa alert() (ex.: "Selecione destinatário para o compartilhamento.")
            avisos.append(dialogo.message)
            try:
                dialogo.dismiss()
            except Exception:
                pass
        p.on('dialog', ao_dialogo)
        try:
            self._ir_para_inicio()
            # é o que o ícone de compartilhar da linha do estudo faz: abre a tela "Compartilhar estudo" pelo ID do estudo
            with p.expect_navigation(wait_until='domcontentloaded', timeout=30000):
                p.evaluate("""(id) => { const f = document.virtualFilmForm; f.id.value = id; f.op.value = 'mailForm2';
                                        f.target = '_self'; f.submit(); }""", str(estudo_id))
            campo = p.locator('#patientSuggester input')
            campo.wait_for(state='visible', timeout=20000)
            padrao = re.compile(r'<\s*' + re.escape(str(usuario).strip()) + r'@', re.I)
            escolhido = False
            for busca in self._buscas_do_paciente(nome):
                campo.fill('')
                campo.press_sequentially(busca, delay=30)
                opcao = p.locator('#patientSuggester button', has_text=padrao).first
                try:
                    opcao.wait_for(state='visible', timeout=7000)
                except Exception:
                    continue
                opcao.click()
                escolhido = True
                break
            if not escolhido:
                raise Exception('A Medcloud não achou o paciente %s (ID %s) para vincular o estudo' % (nome, usuario))
            p.locator('button[onclick="send();"]').click()
            confirmar = p.locator('#modalSendStudy input[value="Confirmar e enviar"]')
            try:
                confirmar.wait_for(state='visible', timeout=10000)
            except Exception:
                raise Exception(avisos[0] if avisos else 'A Medcloud não abriu a confirmação do compartilhamento')
            with p.expect_navigation(wait_until='domcontentloaded', timeout=30000):
                confirmar.click()
            erro = self._erro_forte_da_pagina()
            if erro:
                raise Exception(erro)
        finally:
            try:
                p.remove_listener('dialog', ao_dialogo)
            except Exception:
                pass

    def _erro_forte_da_pagina(self):
        """Só avisos claramente de erro (.alert-danger / .alert-error): um aviso de sucesso também usa a classe .alert, e errar
        aqui faria o robô compartilhar de novo."""
        try:
            for texto in self._page.locator('.alert-danger, .alert-error').all_inner_texts():
                if texto.strip():
                    return _mensagem_curta(texto.strip())
        except Exception:
            pass
        return ''

    def _mensagem_da_pagina(self):
        """Texto do aviso de erro visível na página (ou '' se não houver)."""
        try:
            for texto in self._page.locator('.alert, .error, .erro, [role="alert"]').all_inner_texts():
                if texto.strip():
                    return _mensagem_curta(texto.strip())
        except Exception:
            pass
        return ''

    def fechar(self):
        self.fechado = True
        for obj, metodo in ((self._browser, 'close'), (self._pw, 'stop')):
            try:
                if obj is not None:
                    getattr(obj, metodo)()
            except Exception:
                pass
        self._page = self._browser = self._pw = None
        self._logado = False


def testar_conexao(login, senha, url, criar_robo=RoboPlaywright):
    """Só confere o login na Medcloud (não cria cadastro). Devolve (True/False, mensagem)."""
    robo = criar_robo(login, senha, url)
    try:
        robo.entrar()
        return True, 'Login realizado na Medcloud.'
    except Exception as exc:
        return False, _mensagem_curta(exc)
    finally:
        _fechar(robo)
