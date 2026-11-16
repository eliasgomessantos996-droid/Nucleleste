"""Ferramentas da NucleAI IA: o que ela pode pedir ao sistema.

Princípio: a IA só escolhe a ferramenta e os parâmetros. Quem consulta, calcula, desenha e grava é este código,
com as permissões do próprio usuário. Cada ferramenta devolve:
- `resumo`: o que volta para a IA escrever a resposta (nomes reais quando a gerência habilita dados de pacientes;
  nunca contatos ou documentos);
- `cartao`: o desenho mostrado no chat (tabela, gráfico, acessos...), que vai direto do servidor para a tela.

Cada ferramenta tem o nível mínimo de IA (1 Leve, 2 Médio, 3 Alto, 4 Max) e os módulos exigidos. Vale sempre o menor
entre o nível da IA e a permissão normal: a IA nunca dá acesso que a pessoa não tem.
Ferramentas que gravam (`escrita=True`) primeiro só propõem; a gravação acontece depois do "Sim", fica no registro de
atividades como "Feito com auxílio da NucleAI", com o nome de quem pediu, e com o botão Desfazer quando aplicável.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from flask import url_for

from . import agenda, ajuda, modulos
from . import nucleai_arquivos as arq_mod
from . import nucleai_ia as ia
from . import nucleai_ilustrar as ilustrar_mod
from . import nucleai_memoria as mem
from . import nucleai_projecoes as proj
from .ajuda_busca import normalizar
from .db import agora

LEVE, MEDIO, ALTO, MAX = 1, 2, 3, 4
NOMES_NIVEL = {0: 'Desligado', 1: 'Leve', 2: 'Médio', 3: 'Alto', 4: 'Max'}
DESCRICAO_NIVEL = {
    1: 'tirar dúvidas sobre o sistema',
    2: 'tirar dúvidas e puxar informações básicas (listas e contagens)',
    3: 'dúvidas, informações, simulações e projeções simples e alterações simples pelo chat',
    4: 'tudo: gráficos, simulações, alterações e a visão e edição de acessos',
}
MAX_LINHAS_TABELA = 200
VALIDADE_PENDENTE_MIN = 10


class ErroFerramenta(ValueError):
    """Erro explicado à IA (e, por ela, ao usuário)."""


@dataclass
class Ctx:
    db: object
    uid: int
    usuario: str
    nivel: int
    mods: set
    admin: bool
    treino: bool = False
    real: bool = True            # False: no chat Treinador sem "executar de verdade", as gravações são só simuladas
    treinador: str | None = None
    pseudonimos: dict = field(default_factory=dict)

    def pode_modulo(self, exigidos):
        if not exigidos:
            return True
        if exigidos == '__admin__':
            return self.admin
        return self.admin or any(m in self.mods for m in exigidos)

    def pseudonimo(self, nome):
        chave = (nome or '').strip().upper()
        if chave not in self.pseudonimos:
            self.pseudonimos[chave] = '[PACIENTE_%d]' % (len(self.pseudonimos) + 1)
        return self.pseudonimos[chave]


def contexto(db, uid, treino=False, nivel=None, treinador=None):
    u = db.execute('SELECT id, usuario, admin, modulos FROM usuarios WHERE id=?', (uid,)).fetchone()
    if u is None:
        raise ErroFerramenta('Usuário não encontrado.')
    n = MAX if treino and nivel is None else (ia.nivel(db, uid) if nivel is None else nivel)
    usuario_nome = treinador if (treino and treinador) else u['usuario']
    return Ctx(db=db, uid=uid, usuario=usuario_nome, nivel=n, mods=modulos.modulos_do_usuario(u), admin=bool(u['admin']),
               treino=treino, real=(not treino) or ia.treino_real(db), treinador=treinador)


# ------------------------------------------------------------------ utilidades
def _url(endpoint, **kw):
    try:
        return url_for(endpoint, **kw)
    except Exception:   # fora de uma requisição (ou rota inexistente): o cartão fica sem botão
        return None


def _link(rotulo, endpoint, **kw):
    u = _url(endpoint, **kw)
    return {'rotulo': rotulo, 'url': u} if u else None


def data_de(txt, hoje=None):
    """'hoje', 'amanhã', 'ontem', 'segunda'..., 'AAAA-MM-DD', 'DD/MM' ou 'DD/MM/AAAA' -> date."""
    hoje = hoje or date.today()
    t = normalizar(str(txt or '')).strip()
    if t in ('', 'hoje'):
        return hoje
    if t == 'amanha':
        return hoje + timedelta(days=1)
    if t in ('depois de amanha',):
        return hoje + timedelta(days=2)
    if t == 'ontem':
        return hoje - timedelta(days=1)
    dias = ('segunda', 'terca', 'quarta', 'quinta', 'sexta', 'sabado', 'domingo')
    for i, d in enumerate(dias):
        if t.startswith(d):
            delta = (i - hoje.weekday()) % 7 or 7
            return hoje + timedelta(days=delta)
    t = str(txt or '').strip()   # datas com números: o texto original (a normalização da busca tira as barras)
    m = re.fullmatch(r'(\d{4})-(\d{1,2})-(\d{1,2})', t)
    try:
        if m:
            return date(int(m[1]), int(m[2]), int(m[3]))
        m = re.fullmatch(r'(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?', t)
        if m:
            ano = int(m[3]) if m[3] else hoje.year
            ano = ano + 2000 if ano < 100 else ano
            return date(ano, int(m[2]), int(m[1]))
    except ValueError:
        pass
    raise ErroFerramenta('Não entendi a data «%s». Use hoje, amanhã ou DD/MM/AAAA.' % txt)


def hora_de(txt, padrao):
    t = str(txt or '').strip().lower().replace(' ', '')
    if not t:
        return padrao
    m = re.fullmatch(r'(\d{1,2})(?:[:h.](\d{2})?)?(?:min|h)?', t)
    if not m or int(m[1]) > 23 or (m[2] and int(m[2]) > 59):
        raise ErroFerramenta('Não entendi o horário «%s». Use, por exemplo, 6h30 ou 08:30.' % txt)
    return '%02d:%s' % (int(m[1]), m[2] or '00')


def _br(d):
    return d.strftime('%d/%m/%Y')


def _auditar(ctx, modulo, acao, detalhe, desfazer):
    """Registro de atividades: sempre com quem pediu e a marca "via chat (NucleAI)". Funciona com ou sem requisição."""
    ip = None
    try:
        from flask import has_request_context, request
        if has_request_context():
            ip = request.remote_addr
    except Exception:
        ip = None
    origem = 'via chat (NucleAI%s)' % (', treino %s' % ctx.treinador if ctx.treino else '')
    ctx.db.execute('INSERT INTO auditoria (data_hora, usuario, usuario_id, modulo, acao, detalhe, rota, ip, desfazer) VALUES (?,?,?,?,?,?,?,?,?)',
                   (agora(), ctx.usuario, ctx.uid, modulo, '%s (Feito com auxílio da NucleAI; %s)' % (acao, origem), detalhe[:400], '/mensagens (NucleAI)', ip,
                    json.dumps(desfazer, ensure_ascii=False) if desfazer else None))
    return ctx.db.execute('SELECT last_insert_rowid()').fetchone()[0]


# ------------------------------------------------------------------ registro das ferramentas
@dataclass
class Ferramenta:
    nome: str
    descricao: str
    parametros: dict
    nivel: int
    funcao: object
    modulos: tuple | str | None = None
    escrita: bool = False
    so_treino: bool = False
    executar: object = None      # ferramentas de escrita: grava depois do Sim


FERRAMENTAS = {}


def ferramenta(nome, descricao, nivel, parametros=None, modulos_=None, escrita=False, so_treino=False):
    def registrar(func):
        FERRAMENTAS[nome] = Ferramenta(nome, descricao, parametros or {}, nivel, func, modulos_, escrita, so_treino)
        return func
    return registrar


def _obj(props, obrig=()):
    return {'type': 'object', 'properties': props, 'required': list(obrig)}


def _s(desc):
    return {'type': 'string', 'description': desc}


def _i(desc):
    return {'type': 'integer', 'description': desc}


def disponiveis(ctx):
    """Ferramentas que esta pessoa pode usar agora (nível + módulos + treino)."""
    return [f for f in FERRAMENTAS.values()
            if f.nivel <= ctx.nivel and ctx.pode_modulo(f.modulos) and (ctx.treino or not f.so_treino)]


def declaracoes(ctx):
    """Ferramentas no formato OpenAI aceito pelo OpenRouter."""
    saida = []
    for f in disponiveis(ctx):
        d = {'name': f.nome, 'description': f.descricao}
        if f.parametros:
            d['parameters'] = _obj(f.parametros, [k for k, v in f.parametros.items() if v.get('_obrigatorio')])
            for v in d['parameters']['properties'].values():
                v.pop('_obrigatorio', None)
        d.setdefault('parameters', _obj({}))
        saida.append({'type': 'function', 'function': d})
    return saida


def bloqueio(ctx, nome):
    """Explicação (ou None) de por que a ferramenta não pode ser usada por esta pessoa."""
    f = FERRAMENTAS.get(nome)
    if f is None:
        return 'Essa ação não existe no sistema.'
    if f.so_treino and not ctx.treino:
        return 'Essa ação só existe no chat de treinamento.'
    if f.nivel > ctx.nivel:
        return ('Isso exige o nível %s da NucleAI, e o seu é %s. Com o seu nível eu posso: %s.'
                % (NOMES_NIVEL[f.nivel], NOMES_NIVEL.get(ctx.nivel, '?'), DESCRICAO_NIVEL.get(ctx.nivel, 'nada')))
    if f.escrita:
        u = ctx.db.execute('SELECT admin, modulos FROM usuarios WHERE id=? AND ativo=1', (ctx.uid,)).fetchone()
        if u is None:
            return 'Seu usuário não está ativo; não posso fazer essa alteração.'
        ctx.admin, ctx.mods = bool(u['admin']), modulos.modulos_do_usuario(u)
    if not ctx.pode_modulo(f.modulos):
        if f.escrita and f.modulos == ('agenda',):
            return 'Você não tem acesso à tela Agenda, por isso não posso fazer essa alteração.'
        return 'Você não tem acesso ao módulo dessa informação no sistema, então eu também não posso buscá-la.'
    return None


def chamar(ctx, nome, args):
    """Executa a ferramenta (ou a proposta, para as de escrita). Devolve {'resumo', 'cartao', 'pendente'}."""
    motivo = bloqueio(ctx, nome)
    if motivo:
        return {'resumo': 'RECUSADO: ' + motivo, 'cartao': None, 'recusado': True}
    f = FERRAMENTAS[nome]
    try:
        r = f.funcao(ctx, dict(args or {}))
    except (ErroFerramenta, mem.ErroMemoria, agenda.ErroAgenda, ValueError) as e:
        return {'resumo': 'ERRO: %s' % e, 'cartao': None}
    r.setdefault('cartao', None)
    if f.escrita and r.get('proposta'):
        r['pendente'] = {'ferramenta': nome, 'args': r['proposta'], 'criado_em': agora()}
    return r


def confirmar(ctx, pendente):
    """Executa a ação que estava esperando o Sim. Devolve {'texto', 'cartao'}."""
    f = FERRAMENTAS.get(pendente.get('ferramenta'))
    try:
        criado = datetime.strptime(pendente.get('criado_em', ''), '%Y-%m-%d %H:%M:%S')
    except ValueError:
        criado = datetime.min
    if f is None or not f.escrita or f.executar is None:
        return {'texto': 'Essa ação não pode mais ser feita.', 'cartao': None}
    if datetime.now() - criado > timedelta(minutes=VALIDADE_PENDENTE_MIN):
        return {'texto': 'A confirmação expirou (mais de %d minutos). Peça de novo, por favor.' % VALIDADE_PENDENTE_MIN, 'cartao': None}
    motivo = bloqueio(ctx, f.nome)   # a permissão é conferida de novo na hora de gravar
    if motivo:
        return {'texto': motivo, 'cartao': None}
    if not ctx.real:
        return {'texto': 'Simulação do treinamento: eu faria esta alteração, mas nada foi gravado. '
                         '(Para gravar de verdade no treino, ligue "Executar de verdade" na aba IA online.)', 'cartao': None}
    try:
        return f.executar(ctx, pendente['args'])
    except (ErroFerramenta, agenda.ErroAgenda, ValueError) as e:
        return {'texto': 'Não consegui fazer: %s' % e, 'cartao': None}


def executor(nome):
    def registrar(func):
        FERRAMENTAS[nome].executar = func
        return func
    return registrar


# ================================================================== nível 1: dúvidas
@ferramenta('buscar_ajuda', 'Busca na base de ajuda do sistema as instruções passo a passo sobre uma tela ou tarefa. '
            'Use sempre que o usuário perguntar como fazer algo no sistema.', LEVE,
            {'pergunta': dict(_s('A dúvida, com as palavras do usuário'), _obrigatorio=True)})
def _buscar_ajuda(ctx, a):
    B = ajuda.base(ctx.db)
    vt = ajuda.temas_visiveis(ctx.db, ctx.uid, B)
    permitidos = {(ti, mi) for ti in vt for mi in ajuda.modulos_visiveis(ctx.db, ctx.uid, ti, B)}
    achados = B.indice.buscar(str(a.get('pergunta', ''))[:300], permitido=lambda ti, mi: (ti, mi) in permitidos, limite=3)
    if not achados:
        return {'resumo': 'Nada encontrado na base de ajuda para essa dúvida (ou o usuário não tem acesso a esse módulo).'}
    partes = [ajuda.instrucoes(r['ti'], r['mi'], r['ai'], B.temas)[:1800] for r in achados]
    return {'resumo': 'Trechos da base de ajuda (use só o que responder à dúvida):\n\n' + '\n\n---\n\n'.join(partes)}


def _menu_do_usuario(ctx):
    itens = []
    for _grupo, entradas in modulos.MENU:
        for chave, rotulo, endpoint, _pref in entradas:
            if chave is None:
                pode = True
            elif chave == '__admin__':
                pode = ctx.admin
            else:
                pode = ctx.pode_modulo(chave if isinstance(chave, tuple) else (chave,))
            if pode:
                itens.append((rotulo, endpoint))
    return itens


@ferramenta('abrir_tela', 'Mostra um botão para abrir uma tela do sistema (por exemplo: agenda, atendimentos, caixa).', LEVE,
            {'tela': dict(_s('Nome da tela, como aparece no menu'), _obrigatorio=True)})
def _abrir_tela(ctx, a):
    alvo = set(normalizar(str(a.get('tela', ''))).split())
    if not alvo:
        raise ErroFerramenta('Diga qual tela.')
    pontuados = []
    for rotulo, ep in _menu_do_usuario(ctx):
        p = set(normalizar(rotulo).split())
        n = len(alvo & p)
        if n:
            pontuados.append((n, rotulo, ep))
    pontuados.sort(key=lambda x: -x[0])
    links = [l for l in (_link(r, ep) for _n, r, ep in pontuados[:3]) if l]
    if not links:
        return {'resumo': 'Não achei essa tela entre as que o usuário pode abrir. Telas disponíveis: '
                          + ', '.join(r for r, _ in _menu_do_usuario(ctx)[:40])}
    return {'resumo': 'Botões mostrados para: ' + ', '.join(l['rotulo'] for l in links),
            'cartao': {'tipo': 'IA_LINKS', 'titulo': 'Abrir no sistema', 'links': links}}


@ferramenta('anotar_preferencia', 'Anota na memória como ESTE usuário prefere ser atendido (tratamento, tom, '
            'tamanho das respostas, atalhos). Use quando ele disser ou demonstrar uma preferência. Nunca anote dados de '
            'pacientes, senhas ou documentos.', LEVE,
            {'preferencia': dict(_s('A preferência em uma frase curta'), _obrigatorio=True)})
def _anotar_preferencia(ctx, a):
    pref = a.get('preferencia', '')
    if ctx.treino:
        mem.anotar(ctx.db, mem.GEMINI, 'Preferências de usuários', 'Preferência (%s): %s' % (ctx.treinador, pref),
                   'NucleAI (teste %s)' % ctx.treinador)
        mem.anotar(ctx.db, mem.TREINAMENTO, mem.secao_treinador(ctx.treinador), 'Preferência: %s' % pref,
                   'NucleAI (treino %s)' % ctx.treinador)
    else:
        mem.anotar(ctx.db, mem.GEMINI, 'Preferências de usuários', '%s: %s' % (ctx.usuario, pref), 'NucleAI (%s)' % ctx.usuario)
        mem.anotar(ctx.db, mem.GEMINI, mem.secao_usuario(ctx.usuario), pref, 'NucleAI (%s)' % ctx.usuario)
    return {'resumo': 'Preferência anotada.'}


@ferramenta('anotar_aprendizado', 'Chat de teste: anota no manual compartilhado (seção Como agir) uma regra ou aprendizado '
            'sobre como agir ou responder (uma frase). Use quando a gerência ensinar ou corrigir algo.', LEVE,
            {'aprendizado': dict(_s('O que aprendeu, em uma frase'), _obrigatorio=True)}, so_treino=True)
def _anotar_aprendizado(ctx, a):
    texto = a.get('aprendizado') or a.get('regra') or ''
    origem = 'NucleAI (teste %s)' % (ctx.treinador or ctx.usuario)
    mem.anotar(ctx.db, mem.GEMINI, 'Como agir', texto, origem)
    if ctx.treinador:
        mem.anotar(ctx.db, mem.TREINAMENTO, mem.secao_treinador(ctx.treinador), texto, origem)
    return {'resumo': f'Aprendizado anotado em «Como agir» no manual compartilhado: {texto}. '
                      'Gravado na memória com versão anterior salva para desfazer.'}


@ferramenta('anotar_regra_geral', 'Chat de teste: anota no manual compartilhado (seção Como agir) uma regra de comportamento que vale para '
            'todos os usuários, quando a gerência ensinar ou pedir explicitamente.', LEVE,
            {'regra': dict(_s('A regra em uma frase'), _obrigatorio=True)}, so_treino=True)
def _anotar_regra(ctx, a):
    texto = a.get('regra') or a.get('aprendizado') or ''
    origem = 'NucleAI (teste %s)' % (ctx.treinador or ctx.usuario)
    mem.anotar(ctx.db, mem.GEMINI, 'Como agir', texto, origem)
    return {'resumo': f'Regra anotada em «Como agir» no manual compartilhado: {texto}. '
                      'Gravado na memória com versão anterior salva para desfazer.'}


CAMPOS_PERFIL = {'tratamento': 'Como chamar o treinador', 'tom': 'Tom das respostas',
                 'formalidade': 'Formalidade (1 a 5)', 'tamanho': 'Tamanho das respostas (1 a 5)',
                 'forca': 'Força no aprendizado (1 a 5)'}


def cartao_perfil(t):
    return {'tipo': 'IA_PERFIL', 'titulo': 'Perfil do treinador %s' % t['nome'],
            'campos': [{'nome': k, 'rotulo': r, 'valor': t.get(k) if t.get(k) not in (None, '') else '(não definido)',
                        'escala': k in ('formalidade', 'tamanho', 'forca')} for k, r in CAMPOS_PERFIL.items()],
            'rodape': 'Para mudar: /configperfil campo valor (ex.: /configperfil formalidade 4) ou peça com suas palavras.'}


@ferramenta('ajustar_perfil_treinador', 'Treinamento: muda uma opção do perfil do treinador atual (tratamento, tom, '
            'formalidade, tamanho ou forca).', LEVE,
            {'campo': dict(_s('tratamento, tom, formalidade, tamanho ou forca'), _obrigatorio=True),
             'valor': dict(_s('Novo valor (texto, ou número de 1 a 5)'), _obrigatorio=True)}, so_treino=True)
def _ajustar_perfil(ctx, a):
    campo = normalizar(str(a.get('campo', ''))).replace(' ', '')
    if campo not in CAMPOS_PERFIL:
        raise ErroFerramenta('Campo desconhecido. Use: ' + ', '.join(CAMPOS_PERFIL))
    valor = a.get('valor')
    if campo in ('formalidade', 'tamanho', 'forca'):
        try:
            valor = int(str(valor).strip())
        except ValueError:
            raise ErroFerramenta('Use um número de 1 a 5.')
    t = alterar_perfil(ctx, campo, valor)
    return {'resumo': 'Perfil atualizado: %s = %s.' % (campo, t.get(campo)), 'cartao': cartao_perfil(t)}


def alterar_perfil(ctx, campo, valor):
    antes = ia.treinador(ctx.db, ctx.treinador)
    t = ia.config_treinador(ctx.db, ctx.treinador, **{campo: valor})
    _auditar(ctx, 'NucleAI', 'Alterou o perfil do treinador %s: %s de «%s» para «%s»' % (ctx.treinador, campo, antes.get(campo), t.get(campo)),
             'treinador=%s; campo=%s' % (ctx.treinador, campo),
             {'nucleai_treinador': {'nome': ctx.treinador, 'campo': campo, 'antes': antes.get(campo), 'depois': t.get(campo)}})
    return t


# ================================================================== nível 2: informações básicas
AGENDA_MODS = ('agenda', 'agenda_leitura')


@ferramenta('agenda_listar', 'Lista os pacientes marcados na agenda de um dia, opcionalmente num intervalo de horário e/ou '
            'de um exame. A lista aparece para o usuário como tabela no chat; você recebe só a contagem.', MEDIO,
            {'data': dict(_s('hoje, amanhã, dia da semana ou DD/MM/AAAA'), _obrigatorio=True),
             'hora_inicio': _s('Início do intervalo, ex.: 6h30 (opcional)'),
             'hora_fim': _s('Fim do intervalo, ex.: 8h30 (opcional)'),
             'exame': _s('Nome (ou parte) do exame (opcional)')}, AGENDA_MODS)
def _agenda_listar(ctx, a):
    d = data_de(a.get('data'))
    ini, fim = hora_de(a.get('hora_inicio'), '00:00'), hora_de(a.get('hora_fim'), '23:59')
    if fim < ini:
        ini, fim = fim, ini
    sql = ("SELECT h.hora, a.exame, h.paciente, h.convenio, h.status FROM agenda_horarios h JOIN agenda_exames a ON a.id=h.agenda_id "
           "WHERE a.data=? AND TRIM(h.paciente)<>'' AND h.hora BETWEEN ? AND ?")
    params = [d.isoformat(), ini, fim]
    exame = str(a.get('exame') or '').strip()
    if exame:
        sql += ' AND a.exame LIKE ?'
        params.append('%' + exame + '%')
    linhas = ctx.db.execute(sql + ' ORDER BY h.hora, a.exame, h.id LIMIT ?', params + [MAX_LINHAS_TABELA]).fetchall()
    por_status, por_exame = {}, {}
    for r in linhas:
        por_status[r['status']] = por_status.get(r['status'], 0) + 1
        por_exame[r['exame']] = por_exame.get(r['exame'], 0) + 1
    faixa = '' if (ini, fim) == ('00:00', '23:59') else ' das %s às %s' % (ini, fim)
    titulo = 'Agenda de %s%s' % (_br(d), faixa)
    resumo = '%d paciente(s) marcados em %s%s%s. Por status: %s. Por exame: %s.' % (
        len(linhas), _br(d), faixa, (' no exame %s' % exame) if exame else '',
        ', '.join('%s %d' % (agenda.ROTULOS.get(k, k), v) for k, v in por_status.items()) or 'nenhum',
        ', '.join('%s %d' % kv for kv in por_exame.items()) or 'nenhum')
    if ia.dados_pacientes(ctx.db) and linhas:
        resumo += '\nLinhas: ' + '; '.join('%s %s %s %s' % (r['hora'], r['exame'], r['paciente'],
                                                                               agenda.ROTULOS.get(r['status'], r['status'])) for r in linhas[:60])
    cartao = {'tipo': 'IA_TABELA', 'titulo': titulo, 'subtitulo': '%d paciente(s)' % len(linhas),
              'colunas': ['Hora', 'Exame', 'Paciente', 'Convênio', 'Status'],
              'linhas': [[r['hora'], r['exame'], r['paciente'], r['convenio'], agenda.ROTULOS.get(r['status'], r['status'])] for r in linhas],
              'link': _link('Abrir a agenda do dia', 'agenda.dia', data=d.isoformat()),
              'vazio': 'Ninguém marcado nesse intervalo.'}
    return {'resumo': resumo, 'cartao': cartao}


def _cartao_consulta(ctx, titulo, linhas):
    colunas = ['Data', 'Hora', 'Paciente', 'Exame', 'Protocolo/fase', 'Convênio', 'Status']
    valores = [[_br(date.fromisoformat(r['data'])), r['hora'], r['paciente'], r['exame'],
                ('%s - %s' % (r['exame'], r['senha'])) if r['senha'] else r['exame'],
                r['convenio'], agenda.ROTULOS.get(r['status'], r['status'])] for r in linhas]
    if len(linhas) != 1:
        args = {'tipo': 'planilha', 'titulo': titulo, 'colunas': colunas, 'linhas': valores}
    else:
        args = {'tipo': 'cartao_info', 'titulo': titulo, 'icone': 'calendar',
                'itens': [{'rotulo': k, 'valor': v} for k, v in zip(colunas, valores[0])]} if valores else None
    if not args:
        return None
    subtipo, titulo, subtitulo, rodape, dados = ilustrar_mod.preparar(args['tipo'], args)
    return ilustrar_mod.salvar(ctx.db, ctx.uid, ctx.treino, subtipo, titulo, subtitulo, rodape, dados)[1]


def _resultado_consulta(ctx, titulo, linhas):
    resumo = '%s: %d agendamento(s).' % (titulo, len(linhas))
    if ia.dados_pacientes(ctx.db):
        resumo += '\n' + '; '.join('%s %s %s, %s, %s, %s, %s' % (
            r['data'], r['hora'], r['paciente'], r['exame'], r['senha'] or '-', r['convenio'], r['status']) for r in linhas)
    return {'resumo': resumo, 'cartao': _cartao_consulta(ctx, titulo, linhas)}


@ferramenta('agenda_consultar', 'Consulta agendamentos por data, hora ou faixa, exame e paciente. Mostra nome, exame, '
            'protocolo/fase, horário, convênio e status; para mais de 3 linhas usa planilha, para uma usa cartão.', MEDIO,
            {'data': dict(_s('Data do agendamento'), _obrigatorio=True), 'hora': _s('Horário exato'),
             'hora_inicio': _s('Início da faixa'), 'hora_fim': _s('Fim da faixa'),
             'exame': _s('Exame'), 'paciente': _s('Nome ou parte do nome')}, AGENDA_MODS)
def _agenda_consultar(ctx, a):
    d = data_de(a.get('data'))
    ini = fim = hora_de(a['hora'], '') if a.get('hora') else None
    if not ini:
        ini, fim = hora_de(a.get('hora_inicio'), '00:00'), hora_de(a.get('hora_fim'), '23:59')
    if fim < ini:
        ini, fim = fim, ini
    sql = ("SELECT a.data, h.hora, h.paciente, a.exame, h.senha, h.convenio, h.status "
           "FROM agenda_horarios h JOIN agenda_exames a ON a.id=h.agenda_id "
           "WHERE a.data=? AND h.hora BETWEEN ? AND ? AND TRIM(h.paciente)<>''")
    params = [d.isoformat(), ini, fim]
    for campo, coluna in (('exame', 'a.exame'), ('paciente', 'h.paciente')):
        if a.get(campo):
            sql += ' AND ' + coluna + ' LIKE ?'
            params.append('%' + str(a[campo]).strip() + '%')
    linhas = ctx.db.execute(sql + ' ORDER BY h.hora, a.exame, h.id LIMIT ?', params + [MAX_LINHAS_TABELA]).fetchall()
    return _resultado_consulta(ctx, 'Agenda de %s' % _br(d), linhas)


@ferramenta('paciente_agendamentos', 'Consulta agendamentos anteriores e próximos de um paciente pelo nome.', MEDIO,
            {'paciente': dict(_s('Nome do paciente'), _obrigatorio=True)}, AGENDA_MODS)
def _paciente_agendamentos(ctx, a):
    nome = str(a.get('paciente') or '').strip()
    if not nome:
        raise ErroFerramenta('Informe o nome do paciente.')
    linhas = ctx.db.execute(
        "SELECT a.data, h.hora, h.paciente, a.exame, h.senha, h.convenio, h.status "
        "FROM agenda_horarios h JOIN agenda_exames a ON a.id=h.agenda_id "
        "WHERE h.paciente LIKE ? AND TRIM(h.paciente)<>'' ORDER BY a.data DESC, h.hora DESC LIMIT ?",
        ('%' + nome + '%', MAX_LINHAS_TABELA)).fetchall()
    resultado = _resultado_consulta(ctx, 'Agendamentos de %s' % (nome if ia.dados_pacientes(ctx.db) else 'paciente'), linhas)
    hoje = date.today().isoformat()
    resultado['resumo'] += ' Próximos: %d; anteriores: %d.' % (
        sum(r['data'] >= hoje for r in linhas), sum(r['data'] < hoje for r in linhas))
    return resultado


@ferramenta('agenda_resumo', 'Conta os pacientes da agenda por status (veio, faltou, agendado...) num período e mostra um '
            'gráfico de barras.', MEDIO,
            {'de': dict(_s('Data inicial (hoje, DD/MM/AAAA...)'), _obrigatorio=True),
             'ate': dict(_s('Data final'), _obrigatorio=True)}, ('agenda', 'agenda_leitura', 'agenda_relatorios'))
def _agenda_resumo(ctx, a):
    d1, d2 = data_de(a.get('de')), data_de(a.get('ate'))
    if d2 < d1:
        d1, d2 = d2, d1
    if (d2 - d1).days > 400:
        raise ErroFerramenta('Escolha um período de até 13 meses.')
    rows = ctx.db.execute("SELECT h.status, COUNT(*) AS n FROM agenda_horarios h JOIN agenda_exames a ON a.id=h.agenda_id "
                          "WHERE a.data BETWEEN ? AND ? AND TRIM(h.paciente)<>'' GROUP BY h.status", (d1.isoformat(), d2.isoformat())).fetchall()
    cont = {r['status']: r['n'] for r in rows}
    pontos = [{'rotulo': agenda.ROTULOS.get(s, s), 'valor': cont.get(s, 0)} for s in agenda.STATUS]
    total = sum(cont.values())
    return {'resumo': 'Agenda de %s a %s: %d marcados. %s.' % (_br(d1), _br(d2), total,
                                                              ', '.join('%s %d' % (p['rotulo'], p['valor']) for p in pontos)),
            'cartao': {'tipo': 'IA_GRAFICO', 'modo': 'barras', 'titulo': 'Agenda por status', 'subtitulo': '%s a %s' % (_br(d1), _br(d2)),
                       'unidade': 'pacientes', 'series': [{'nome': 'Pacientes', 'estilo': 'real', 'pontos': pontos}],
                       'link': _link('Abrir os relatórios da agenda', 'agenda.relatorio') if ctx.pode_modulo(('agenda_relatorios',)) else None}}


@ferramenta('atendimentos_contar', 'Conta os atendimentos (fichas lançadas) de um período, por exame, com gráfico.', MEDIO,
            {'de': dict(_s('Data inicial'), _obrigatorio=True), 'ate': dict(_s('Data final'), _obrigatorio=True)},
            ('atendimentos', 'dashboard', 'relatorios'))
def _atendimentos_contar(ctx, a):
    d1, d2 = data_de(a.get('de')), data_de(a.get('ate'))
    if d2 < d1:
        d1, d2 = d2, d1
    rows = ctx.db.execute("SELECT COALESCE(NULLIF(TRIM(exame),''),'(sem exame)') AS e, COUNT(*) AS n FROM atendimentos "
                          "WHERE data BETWEEN ? AND ? GROUP BY e ORDER BY n DESC LIMIT 15", (d1.isoformat(), d2.isoformat())).fetchall()
    pontos = [{'rotulo': r['e'], 'valor': r['n']} for r in rows]
    total = sum(p['valor'] for p in pontos)
    return {'resumo': '%d atendimentos de %s a %s. Por exame: %s.' % (total, _br(d1), _br(d2), ', '.join('%s %d' % (p['rotulo'], p['valor']) for p in pontos) or 'nenhum'),
            'cartao': {'tipo': 'IA_GRAFICO', 'modo': 'barras', 'titulo': 'Atendimentos por exame', 'subtitulo': '%s a %s' % (_br(d1), _br(d2)),
                       'unidade': 'atendimentos', 'series': [{'nome': 'Atendimentos', 'estilo': 'real', 'pontos': pontos}],
                       'link': _link('Abrir o dashboard', 'dash.dashboard') if ctx.pode_modulo(('dashboard',)) else None}}


# ================================================================== nível 3: simulações e alterações simples
def _cartao_projecao(r, link):
    serie_real = {'nome': 'Realizado', 'estilo': 'real', 'pontos': [{'rotulo': p['rotulo'], 'valor': p['valor']} for p in r['historico']]}
    serie_proj = {'nome': 'Projeção', 'estilo': 'projecao', 'pontos': [{'rotulo': p['rotulo'], 'valor': p['valor'], 'min': p['min'], 'max': p['max']}
                                                                    for p in r['projecao']]}
    return {'tipo': 'IA_GRAFICO', 'modo': 'linha', 'titulo': r['titulo'], 'subtitulo': 'Estimativa: não é garantia',
            'unidade': r['unidade'], 'series': [serie_real, serie_proj], 'rodape': r['premissa'], 'link': link}


def _resumo_projecao(r):
    return ('%s. Histórico: %s. Projeção: %s. %s' % (
        r['titulo'], ', '.join('%s %s' % (p['rotulo'], p['valor']) for p in r['historico']),
        ', '.join('%s %s (entre %s e %s)' % (p['rotulo'], p['valor'], p['min'], p['max']) for p in r['projecao']), r['premissa']))


@ferramenta('projetar_pacientes', 'Simulação: projeta quantos pacientes virão nos próximos meses com base na tendência dos '
            'meses anteriores. fonte "agenda" (quem veio, indicador da ONA) ou "atendimentos" (fichas lançadas).', ALTO,
            {'meses_historico': _i('Quantos meses completos anteriores usar (2 a 36, padrão 6)'),
             'meses_futuros': _i('Quantos meses projetar (1 a 12, padrão 3)'),
             'fonte': _s('agenda ou atendimentos (padrão agenda)')},
            ('ona', 'agenda_relatorios', 'agenda', 'dashboard', 'relatorios'))
def _projetar_pacientes(ctx, a):
    fonte = normalizar(str(a.get('fonte') or 'agenda'))
    if fonte.startswith('atend'):
        if not ctx.pode_modulo(('atendimentos', 'dashboard', 'relatorios', 'ona')):
            raise ErroFerramenta('Você não tem acesso aos atendimentos.')
        r = proj.projecao_atendimentos(ctx.db, a.get('meses_historico', 6), a.get('meses_futuros', 3))
        link = _link('Abrir o dashboard', 'dash.dashboard') if ctx.pode_modulo(('dashboard',)) else None
    else:
        if not ctx.pode_modulo(('ona', 'agenda_relatorios', 'agenda')):
            raise ErroFerramenta('Você não tem acesso aos dados da agenda.')
        r = proj.projecao_comparecimento(ctx.db, a.get('meses_historico', 6), a.get('meses_futuros', 3))
        link = _link('Abrir o relatório ONA', 'ona.pagina') if ctx.pode_modulo(('ona',)) else None
    return {'resumo': _resumo_projecao(r), 'cartao': _cartao_projecao(r, link)}


@ferramenta('projetar_faltas', 'Simulação: estima quantos pacientes podem faltar no próximo mês, pela taxa de faltas dos '
            'meses anteriores aplicada aos agendados.', ALTO,
            {'meses_historico': _i('Quantos meses completos anteriores usar (2 a 36, padrão 6)')},
            ('agenda', 'agenda_faltas', 'agenda_relatorios', 'ona'))
def _projetar_faltas(ctx, a):
    r = proj.projecao_faltas(ctx.db, a.get('meses_historico', 6))
    cartao = _cartao_projecao(r, _link('Abrir faltas e reagendamento', 'agenda.faltas') if ctx.pode_modulo(('agenda_faltas',)) else None)
    cartao['destaque'] = {'rotulo': 'Faltas previstas', 'valor': r['projecao'][0]['valor'],
                          'faixa': '%s a %s' % (r['projecao'][0]['min'], r['projecao'][0]['max']), 'extra': 'Taxa média: %s%%' % r['taxa_media']}
    return {'resumo': _resumo_projecao(r) + ' Taxa média de falta: %s%%.' % r['taxa_media'], 'cartao': cartao}


def _linha_agenda(ctx, a):
    d = data_de(a.get('data'))
    hora = hora_de(a.get('hora'), '')
    exame = str(a.get('exame') or '').strip()
    sql = ("SELECT h.id, h.hora, h.paciente, h.status, a.exame FROM agenda_horarios h JOIN agenda_exames a ON a.id=h.agenda_id "
           "WHERE a.data=? AND h.hora=? AND TRIM(h.paciente)<>''")
    params = [d.isoformat(), hora]
    if exame:
        sql += ' AND a.exame LIKE ?'
        params.append('%' + exame + '%')
    linhas = ctx.db.execute(sql, params).fetchall()
    if not linhas:
        raise ErroFerramenta('Não achei paciente marcado em %s às %s%s.' % (_br(d), hora, (' no exame ' + exame) if exame else ''))
    if len(linhas) > 1:
        raise ErroFerramenta('Há %d pacientes às %s nesse dia (%s). Diga qual exame.' % (len(linhas), hora, ', '.join(r['exame'] for r in linhas)))
    return d, linhas[0]


STATUS_FALADOS = {'veio': 'VEIO', 'chegou': 'VEIO', 'compareceu': 'VEIO', 'faltou': 'FALTOU', 'falta': 'FALTOU',
                  'agendado': 'AGENDADO', 'retorno': 'RETORNO', 'desistiu': 'DESISTIU', 'resgatado': 'RESGATADO'}


@ferramenta('agenda_mudar_status', 'Alteração simples: muda o status de UM paciente na agenda (veio, faltou, agendado, '
            'retorno, desistiu). Primeiro mostra a proposta; só grava depois que o usuário responder Sim.', ALTO,
            {'data': dict(_s('Dia do agendamento'), _obrigatorio=True), 'hora': dict(_s('Horário do paciente'), _obrigatorio=True),
             'exame': _s('Exame (se houver mais de um paciente no horário)'),
             'status': dict(_s('veio, faltou, agendado, retorno ou desistiu'), _obrigatorio=True)}, ('agenda',), escrita=True)
def _agenda_mudar_status(ctx, a):
    novo = STATUS_FALADOS.get(normalizar(str(a.get('status', ''))).strip())
    if not novo:
        raise ErroFerramenta('Status inválido. Use veio, faltou, agendado, retorno ou desistiu.')
    d, r = _linha_agenda(ctx, a)
    if r['status'] == novo:
        return {'resumo': 'O paciente já está com o status %s. Nada a mudar.' % agenda.ROTULOS[novo]}
    cartao = {'tipo': 'IA_PROPOSTA', 'titulo': 'Confirma a alteração na agenda?',
              'itens': [['Dia', _br(d)], ['Hora', r['hora']], ['Exame', r['exame']], ['Paciente', r['paciente']],
                        ['Status', '%s → %s' % (agenda.ROTULOS.get(r['status'], r['status']), agenda.ROTULOS[novo])]],
              'rodape': 'Fica no registro de atividades como feito por você, pelo chat, com o botão Desfazer.'}
    return {'resumo': 'Proposta mostrada ao usuário (horário %s, exame %s, de %s para %s). Peça que ele responda Sim para '
                      'confirmar ou Não para cancelar.' % (r['hora'], r['exame'], r['status'], novo),
            'cartao': cartao, 'proposta': {'hid': r['id'], 'status': novo, 'data': d.isoformat()}}


@executor('agenda_mudar_status')
def _agenda_mudar_status_exec(ctx, p):
    hid = int(p['hid'])
    antes = agenda._tirar(ctx.db, 'agenda_horarios', [hid])
    if hid not in antes:
        raise ErroFerramenta('Esse horário não existe mais.')
    agenda.definir_status(ctx.db, hid, p['status'], ctx.usuario)
    depois = agenda._tirar(ctx.db, 'agenda_horarios', [hid])
    try:
        from flask import g, has_request_context
        if has_request_context():
            g.pop('desfazer', None)   # o desfazer vai no registro feito aqui, com a marca do chat
    except Exception:
        pass
    r = antes[hid]
    _auditar(ctx, modulos.NOMES['agenda'], 'Mudou o status na agenda para %s' % agenda.ROTULOS[p['status']],
             'data=%s; hora=%s; paciente=%s; status=%s → %s' % (p.get('data'), r['hora'], r['paciente'], r['status'], p['status']),
             {'tabelas': {'agenda_horarios': {'antes': {str(hid): antes[hid]}, 'depois': {str(hid): depois.get(hid)}}}})
    ctx.db.commit()
    return {'texto': 'Pronto! Status alterado para %s. Se precisar, dá para desfazer em Registros de atividades.' % agenda.ROTULOS[p['status']],
            'cartao': {'tipo': 'IA_LINKS', 'titulo': 'Feito', 'links': [l for l in (_link('Abrir a agenda do dia', 'agenda.dia', data=p.get('data')),) if l]}}


@ferramenta('agenda_remarcar', 'Propõe remarcar um paciente para horário livre do mesmo exame, na data e hora pedidas '
            'ou no horário mais próximo. Confirma com Sim/Não antes de gravar.', ALTO,
            {'data': dict(_s('Data do agendamento atual'), _obrigatorio=True),
             'hora': dict(_s('Hora do agendamento atual'), _obrigatorio=True),
             'exame': _s('Exame do agendamento atual'),
             'nova_data': dict(_s('Data desejada'), _obrigatorio=True),
             'nova_hora': _s('Horário desejado ou "mais próximo"')}, ('agenda',), escrita=True)
def _agenda_remarcar(ctx, a):
    origem_dia, r = _linha_agenda(ctx, a)
    origem = agenda._linha(ctx.db, r['id'])
    agenda._checar_remarcado(origem)
    dia = data_de(a.get('nova_data'))
    if agenda.bloqueio(ctx.db, dia.isoformat()) is not None:
        raise ErroFerramenta('O dia escolhido está bloqueado na agenda.')
    pedido = str(a.get('nova_hora') or 'mais próximo').strip()
    mais_proximo = normalizar(pedido) == 'mais proximo'
    hora = None if mais_proximo else hora_de(pedido, '')
    if not mais_proximo and not hora:
        raise ErroFerramenta('Informe a nova hora ou "mais próximo".')
    livres = [v for v in agenda.horarios_livres(ctx.db, dia.isoformat(), origem['convenio'])
              if v['exame'].casefold() == origem['exame_agenda'].casefold()]
    if not livres:
        raise ErroFerramenta('Não encontrei horário livre para %s em %s.' % (origem['exame_agenda'], _br(dia)))
    if hora:
        alvo = agenda.minutos(hora)
        livres.sort(key=lambda v: (abs(agenda.minutos(v['hora']) - alvo), v['hora'], v['id']))
    else:
        livres.sort(key=lambda v: (v['hora'], v['id']))
    escolhido = livres[0]
    diferenca = abs(agenda.minutos(escolhido['hora']) - agenda.minutos(hora)) if hora else 0
    tolerancia = ia.cfg_int(ctx.db, 'nucleai_llm_tolerancia_remarcacao', 0, 240)
    alternativa = bool(hora and diferenca > tolerancia)
    pergunta = ('Não encontrei horário próximo; pode ser às %s?' % escolhido['hora']) if alternativa else (
        'Confirma remarcar para %s às %s?' % (_br(dia), escolhido['hora']))
    args = {'tipo': 'cartao_decisao', 'titulo': 'Remarcar agendamento', 'pergunta': pergunta,
            'detalhes': [{'rotulo': 'Paciente', 'valor': origem['paciente']},
                         {'rotulo': 'Exame', 'valor': origem['exame_agenda']},
                         {'rotulo': 'De', 'valor': '%s %s' % (_br(origem_dia), origem['hora'])},
                         {'rotulo': 'Para', 'valor': '%s %s' % (_br(dia), escolhido['hora'])}]}
    subtipo, titulo, subtitulo, rodape, dados = ilustrar_mod.preparar('cartao_decisao', args)
    cartao = ilustrar_mod.salvar(ctx.db, ctx.uid, ctx.treino, subtipo, titulo, subtitulo, rodape, dados)[1]
    return {'resumo': pergunta + ' Peça Sim para confirmar ou Não para cancelar.', 'cartao': cartao,
            'proposta': {'hid': origem['id'], 'destino_hid': escolhido['id'], 'origem': dict(origem),
                         'destino': dict(agenda._linha(ctx.db, escolhido['id']))}}


@executor('agenda_remarcar')
def _agenda_remarcar_exec(ctx, p):
    hid, destino_hid = int(p['hid']), int(p['destino_hid'])
    origem = agenda._linha(ctx.db, hid)
    destino = agenda._linha(ctx.db, destino_hid)
    if dict(origem) != p['origem'] or dict(destino) != p['destino']:
        raise ErroFerramenta('O agendamento mudou desde a proposta. Peça uma nova consulta.')
    antes = agenda._tirar(ctx.db, 'agenda_horarios', [hid, destino_hid])
    agenda.remarcar(ctx.db, hid, destino_hid, ctx.usuario)
    depois = agenda._tirar(ctx.db, 'agenda_horarios', [hid, destino_hid])
    try:
        from flask import g, has_request_context
        if has_request_context():
            g.pop('desfazer', None)
    except Exception:
        pass
    ids = (hid, destino_hid)
    _auditar(ctx, modulos.NOMES['agenda'], 'Remarcou paciente na agenda',
             'paciente=%s; de=%s %s; para=%s %s' % (origem['paciente'], origem['dia'], origem['hora'], destino['dia'], destino['hora']),
             {'tabelas': {'agenda_horarios': {'antes': {str(i): antes[i] for i in ids},
                                              'depois': {str(i): depois[i] for i in ids}}}})
    ctx.db.commit()
    return {'texto': 'Agendamento remarcado para %s às %s. A gerência pode desfazer em Registros de atividades.'
            % (_br(date.fromisoformat(destino['dia'])), destino['hora']), 'cartao': None}


# ================================================================== nível 4: acessos
def _usuario_alvo(ctx, nome):
    nome = str(nome or '').strip()
    if not nome:
        raise ErroFerramenta('Diga de qual usuário.')
    u = ctx.db.execute("SELECT id, usuario, admin, modulos, ativo FROM usuarios WHERE usuario=? COLLATE NOCASE AND COALESCE(sistema,0)=0",
                       (nome,)).fetchone()
    if u is None:
        parecidos = [r['usuario'] for r in ctx.db.execute("SELECT usuario FROM usuarios WHERE usuario LIKE ? AND COALESCE(sistema,0)=0 LIMIT 5",
                                                          ('%' + nome + '%',))]
        raise ErroFerramenta('Usuário «%s» não encontrado.%s' % (nome, (' Parecidos: ' + ', '.join(parecidos)) if parecidos else ''))
    return u


def _cartao_acessos(u, atuais, novos=None):
    grupos = {}
    for chave, nome, grupo, _d in modulos.MODULOS:
        mud = None
        if novos is not None:
            if chave in novos and chave not in atuais:
                mud = '+'
            elif chave in atuais and chave not in novos:
                mud = '-'
        grupos.setdefault(grupo, []).append({'chave': chave, 'nome': nome, 'tem': chave in (novos if novos is not None else atuais), 'mudanca': mud})
    return {'tipo': 'IA_ACESSOS', 'titulo': ('Proposta de acessos de %s' if novos is not None else 'Acessos de %s') % u['usuario'],
            'subtitulo': 'Administrador: vê tudo' if u['admin'] else '%d módulo(s)' % len(novos if novos is not None else atuais),
            'grupos': [{'nome': g, 'itens': i} for g, i in grupos.items()],
            'link': _link('Abrir o cadastro do usuário', 'admin.usuario_editar', uid=u['id']),
            'rodape': 'Para mudar pelo chat, diga por exemplo: "tira a Agenda e dá o Caixa para %s".' % u['usuario']}


@ferramenta('acessos_ver', 'Mostra, de forma visual, a quais módulos um usuário tem acesso. Só administração.', MAX,
            {'usuario': dict(_s('Login do usuário'), _obrigatorio=True)}, '__admin__')
def _acessos_ver(ctx, a):
    u = _usuario_alvo(ctx, a.get('usuario'))
    atuais = modulos.modulos_do_usuario(u)
    return {'resumo': 'Usuário %s%s tem %d módulos: %s.' % (u['usuario'], ' (administrador)' if u['admin'] else '', len(atuais),
                                                           ', '.join(sorted(atuais))),
            'cartao': _cartao_acessos(u, atuais)}


def _chaves(lista):
    saida = []
    for item in (lista or []):
        t = normalizar(str(item))
        achado = next((c for c, n, _g, _d in modulos.MODULOS if t in (normalizar(c), normalizar(n))), None)
        if achado is None:
            achado = next((c for c, n, _g, _d in modulos.MODULOS if t and t in normalizar(n)), None)
        if achado is None:
            raise ErroFerramenta('Módulo «%s» não existe. Módulos: %s' % (item, ', '.join(n for _c, n, _g, _d in modulos.MODULOS)))
        saida.append(achado)
    return saida


@ferramenta('acessos_alterar', 'Alteração de acessos: propõe dar e/ou tirar módulos de um usuário. Mostra o antes e depois; '
            'só grava depois do Sim. Só administração.', MAX,
            {'usuario': dict(_s('Login do usuário'), _obrigatorio=True),
             'adicionar': {'type': 'array', 'items': {'type': 'string'}, 'description': 'Módulos a dar (nome ou chave)'},
             'remover': {'type': 'array', 'items': {'type': 'string'}, 'description': 'Módulos a tirar (nome ou chave)'}},
            '__admin__', escrita=True)
def _acessos_alterar(ctx, a):
    u = _usuario_alvo(ctx, a.get('usuario'))
    if u['admin']:
        raise ErroFerramenta('Administradores têm todos os módulos; não dá para mudar pelo chat.')
    if u['id'] == ctx.uid:
        raise ErroFerramenta('Não é possível mudar os próprios acessos pelo chat.')
    atuais = modulos.modulos_do_usuario(u)
    mais, menos = set(_chaves(a.get('adicionar'))), set(_chaves(a.get('remover')))
    novos = (atuais | mais) - menos
    if novos == atuais:
        return {'resumo': 'Nada muda: o usuário já está assim.', 'cartao': _cartao_acessos(u, atuais)}
    cartao = _cartao_acessos(u, atuais, novos)
    cartao['confirmar'] = True
    cartao['rodape'] = 'Responda Sim para aplicar ou Não para cancelar. Fica no registro de atividades, com o botão Desfazer.'
    return {'resumo': 'Proposta mostrada (dar: %s; tirar: %s). Peça Sim para confirmar ou Não para cancelar.'
                      % (', '.join(sorted(novos - atuais)) or 'nada', ', '.join(sorted(atuais - novos)) or 'nada'),
            'cartao': cartao, 'proposta': {'uid': u['id'], 'antes': u['modulos'], 'novos': sorted(novos)}}


@executor('acessos_alterar')
def _acessos_alterar_exec(ctx, p):
    u = ctx.db.execute('SELECT id, usuario, admin, modulos FROM usuarios WHERE id=?', (int(p['uid']),)).fetchone()
    if u is None or u['admin']:
        raise ErroFerramenta('Usuário não encontrado (ou virou administrador).')
    if u['modulos'] != p['antes']:
        raise ErroFerramenta('Os acessos desse usuário mudaram desde a proposta. Peça de novo.')
    novo = json.dumps(sorted(set(p['novos']) & set(modulos.CHAVES)))
    ctx.db.execute('UPDATE usuarios SET modulos=? WHERE id=?', (novo, u['id']))
    antes = modulos.modulos_do_usuario(u)
    depois = set(json.loads(novo))
    _auditar(ctx, 'Usuários', 'Alterou os acessos de %s' % u['usuario'],
             'usuario=%s; deu=%s; tirou=%s' % (u['usuario'], ','.join(sorted(depois - antes)) or '-', ','.join(sorted(antes - depois)) or '-'),
             {'nucleai_modulos': {'uid': u['id'], 'antes': p['antes'], 'depois': novo}})
    ctx.db.commit()
    u2 = ctx.db.execute('SELECT id, usuario, admin, modulos FROM usuarios WHERE id=?', (u['id'],)).fetchone()
    return {'texto': 'Pronto! Acessos de %s atualizados. Dá para desfazer em Registros de atividades.' % u['usuario'],
            'cartao': _cartao_acessos(u2, modulos.modulos_do_usuario(u2))}


def aplicar_desfazer(db, payload):
    """Desfazer das ações próprias da NucleAI que o desfazer geral não cobre (acessos de usuário e perfil de treinador)."""
    if 'nucleai_modulos' in payload:
        d = payload['nucleai_modulos']
        atual = db.execute('SELECT modulos FROM usuarios WHERE id=?', (int(d['uid']),)).fetchone()
        if atual is None:
            raise ValueError('O usuário não existe mais.')
        if atual['modulos'] != d['depois']:
            raise ValueError('Não dá para desfazer: os acessos desse usuário foram alterados depois desta ação.')
        db.execute('UPDATE usuarios SET modulos=? WHERE id=?', (d['antes'], int(d['uid'])))
        db.commit()
        return True
    if 'nucleai_treinador' in payload:
        d = payload['nucleai_treinador']
        if d['campo'] not in CAMPOS_PERFIL:
            raise ValueError('Campo do perfil inválido.')
        if d['antes'] is None and d['campo'] in ('tratamento', 'tom'):
            db.execute('UPDATE nucleai_treinadores SET %s=NULL WHERE nome=?' % d['campo'], (d['nome'],))
        elif d['antes'] is not None:
            ia.config_treinador(db, d['nome'], **{d['campo']: d['antes']})
        db.commit()
        return True
    return False


# ================================================================== Ilustrar (blocos visuais ricos)
@ferramenta(
    'ilustrar',
    'Desenha um bloco visual rico fora do balão comum para o usuário. Tipos suportados: '
    'planilha (tabela ordenável com download Excel e cópia), '
    'grafico (barras, linhas, pizza ou rosca em SVG com legenda e foco), '
    'cartao_info (título, ícone e pares rótulo/valor), '
    'cartao_decisao (pergunta Sim/Não que volta como resposta do usuário e trava após a escolha) e '
    'cartao_permissao (resumo do que vai mudar e quem precisa autorizar). '
    'Informe substitui com o id anterior quando reorganizar/atualizar uma ilustração já enviada.',
    LEVE,
    {
        'tipo': dict(_s('Tipo do bloco: planilha, grafico, cartao_info, cartao_decisao ou cartao_permissao.'), _obrigatorio=True),
        'titulo': _s('Título principal do bloco.'),
        'subtitulo': _s('Texto curto abaixo do título (opcional).'),
        'rodape': _s('Observação curta no rodapé (opcional).'),
        'substitui': _i('Id da ilustração anterior desta conversa que este bloco substitui/reorganiza.'),
        'colunas': {'type': 'array', 'description': 'Para planilha: lista de nomes das colunas (máx. 30).', 'items': {'type': 'string'}},
        'linhas': {'type': 'array', 'description': 'Para planilha: lista de linhas (máx. 500), cada linha sendo lista de células.', 'items': {'type': 'array', 'items': {'type': 'string'}}},
        'modo': _s('Para grafico: barras, linhas, pizza ou rosca.'),
        'unidade': _s('Para grafico: unidade opcional dos valores (ex.: R$, atend., %).'),
        'rotulos': {'type': 'array', 'description': 'Para grafico: rótulos do eixo/fatias.', 'items': {'type': 'string'}},
        'series': {'type': 'array', 'description': 'Para grafico: lista de séries [{nome, valores: [números]}].', 'items': {'type': 'object'}},
        'itens': {'type': 'array', 'description': 'Para cartao_info, grafico simples ou detalhes: lista de objetos {rotulo, valor}.', 'items': {'type': 'object'}},
        'icone': _s('Para cartao_info: nome do ícone do sistema (ex.: calendar, stethoscope, user-round, receipt, shield-check).'),
        'destaque': _s('Para cartao_info: selo curto de status (opcional).'),
        'pergunta': _s('Para cartao_decisao: pergunta objetiva para resposta Sim ou Não.'),
        'rotulo_sim': _s('Para cartao_decisao: rótulo do botão positivo (padrão: Sim).'),
        'rotulo_nao': _s('Para cartao_decisao: rótulo do botão negativo (padrão: Não).'),
        'risco': _s('Para cartao_decisao: baixo, medio ou alto.'),
        'alvo': _s('Para cartao_permissao: usuário ou cadastro afetado.'),
        'acao': _s('Para cartao_permissao: resumo do pedido/ação.'),
        'autorizadores': {'type': 'array', 'description': 'Para cartao_permissao: lista de cargos ou pessoas que precisam autorizar.', 'items': {'type': 'string'}},
        'mudancas': {'type': 'array', 'description': 'Para cartao_permissao: lista de alterações ({nome, detalhe, tipo: mais|menos|altera}).', 'items': {'type': 'object'}},
        'texto': _s('Texto simples caso precise enviar aviso textual.'),
    },
)
def _ilustrar(ctx, a):
    subtipo, titulo, subtitulo, rodape, dados = ilustrar_mod.preparar(a.get('tipo'), a)
    iid, cartao = ilustrar_mod.salvar(
        ctx.db, ctx.uid, ctx.treino, subtipo, titulo, subtitulo, rodape, dados,
        substitui=a.get('substitui'),
    )
    info_sub = f' (substituiu #{cartao["substitui"]})' if cartao.get('substitui') else ''
    return {
        'resumo': f'Ilustração #{iid} criada e exibida no chat (tipo={subtipo}, título={titulo!r}){info_sub}.',
        'cartao': cartao,
    }


@ferramenta(
    'ilustracao_atual',
    'Devolve os dados da última ilustração enviada nesta conversa (ou de um id específico) para reorganizar, '
    'ordenar ou filtrar antes de chamar ilustrar novamente com substitui.',
    LEVE,
    {
        'id': _i('Id da ilustração (opcional; se omitido, traz a mais recente da conversa).'),
    },
)
def _ilustracao_atual(ctx, a):
    reg = ilustrar_mod.atual(ctx.db, ctx.uid, treino=ctx.treino, iid=a.get('id'))
    if reg is None:
        return {'resumo': 'Nenhuma ilustração encontrada nesta conversa.'}
    carga = {
        'id': reg['id'],
        'tipo': reg['subtipo'],
        'titulo': reg['titulo'],
        'subtitulo': reg['subtitulo'],
        'rodape': reg['rodape'],
        'dados': reg['dados'],
    }
    return {'resumo': json.dumps(carga, ensure_ascii=False)}


# ================================================================== Arquivos enviados no chat
@ferramenta(
    'arquivo_ler',
    'Lê o cabeçalho, tipos detectados (texto, numero, data), total de linhas e amostra das primeiras linhas de um '
    'arquivo (.xlsx, .xls, .csv ou .txt) enviado pelo usuário nesta conversa.',
    LEVE,
    {
        'anexo_id': _i('Id do arquivo anexado na conversa (opcional; se omitido, lê o arquivo mais recente da conversa).'),
        'aba': _s('Nome da aba da planilha (opcional; padrão é a primeira aba).'),
    },
)
def _arquivo_ler(ctx, a):
    res = arq_mod.descrever(ctx.db, ctx.uid, anexo_id=a.get('anexo_id'), aba=a.get('aba'))
    return {'resumo': json.dumps(res, ensure_ascii=False)}


@ferramenta(
    'arquivo_agrupar',
    'Agrupa, filtra e calcula contagem, soma, média, mínimo ou máximo sobre um arquivo enviado pelo usuário nesta conversa. '
    'Todo cálculo é feito no servidor em Python; depois apresente o resultado com ilustrar (planilha e/ou grafico).',
    LEVE,
    {
        'anexo_id': _i('Id do arquivo anexado na conversa (opcional; se omitido, usa o mais recente da conversa).'),
        'aba': _s('Nome da aba da planilha (opcional; padrão é a primeira aba).'),
        'agrupar_por': {'type': 'array', 'description': 'Lista de nomes de colunas para agrupar (ex.: ["Fase"] ou ["Convênio", "Fase"]).', 'items': {'type': 'string'}},
        'granularidade_data': _s('Opcional quando agrupar por coluna de data: "mes" (AAAA-MM), "ano" (AAAA) ou "dia" (DD/MM/AAAA).'),
        'operacoes': {
            'type': 'array',
            'description': 'Operações a calcular: [{op: "contar"|"soma"|"media"|"min"|"max", coluna: "...", rotulo: "..."}]. Padrão: contar.',
            'items': {'type': 'object'},
        },
        'filtros': {
            'type': 'array',
            'description': 'Filtros simples antes do agrupamento: [{coluna: "...", op: "igual"|"contem"|"data_entre", valor: "...", valor_fim: "..."}].',
            'items': {'type': 'object'},
        },
        'ordenar': _s('Ordenação: "desc" (maior primeiro, padrão), "asc" (menor primeiro) ou "grupo" (alfabética).'),
        'limite': _i('Máximo de grupos retornados (padrão 50, máx. 200).'),
    },
)
def _arquivo_agrupar(ctx, a):
    res = arq_mod.agrupar(
        ctx.db,
        ctx.uid,
        anexo_id=a.get('anexo_id'),
        aba=a.get('aba'),
        agrupar_por=a.get('agrupar_por'),
        operacoes=a.get('operacoes'),
        filtros=a.get('filtros'),
        granularidade_data=a.get('granularidade_data'),
        ordenar=a.get('ordenar') or 'desc',
        limite=a.get('limite') or 50,
    )
    return {'resumo': json.dumps(res, ensure_ascii=False)}
