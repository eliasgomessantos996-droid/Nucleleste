"""Pesquisa de satisfação do cliente: até 15 perguntas, de três tipos (escala Ótimo/Bom/Ruim/Péssimo, Sim ou Não, e nota de 0 a 10
do NPS), campo de elogio e de sugestão, nome e telefone opcionais. O cliente responde pelo celular (QR Code) conectado à rede
interna da clínica, ou responde um questionário impresso que a recepção lança depois (com a data em que foi respondido).
Perfil opcional de quem respondeu: exame, convênio ou particular, e paciente ou acompanhante. Cada resposta fica guardada na
Qualidade para a gerência avaliar, e alimenta os indicadores (satisfação, segurança, NPS) e o relatório de satisfação da ONA."""
from __future__ import annotations

import ipaddress
import re
import socket
import time
from datetime import date, timedelta

from reportlab.graphics.barcode import qrencoder

from .db import agora

OPCOES = ('Ótimo', 'Bom', 'Ruim', 'Péssimo')
NOTA_OPCAO = {'Ótimo': 10.0, 'Bom': 7.0, 'Ruim': 3.0, 'Péssimo': 0.0}   # a nota 0 a 10 que alimenta o indicador de satisfação
SATISFEITO = ('Ótimo', 'Bom')
SIM_NAO = ('Sim', 'Não')
NPS_OPCOES = tuple(str(i) for i in range(11))
TIPOS = {'ESCALA': 'Ótimo, Bom, Ruim ou Péssimo', 'SIMNAO': 'Sim ou Não', 'NPS': 'Nota de 0 a 10'}
OPCOES_POR_TIPO = {'ESCALA': OPCOES, 'SIMNAO': SIM_NAO, 'NPS': NPS_OPCOES}
ATENDIMENTOS = ('Convênio', 'Particular')
RESPONDENTES = ('Paciente', 'Acompanhante')
ORIGENS = {'QRCODE': 'QR Code', 'IMPRESSO': 'Impresso'}
MAX_PERGUNTAS = 15

PERGUNTAS_SUGERIDAS = (
    ('Como você avalia a facilidade para agendar o seu exame (telefone, WhatsApp ou presencial)?', 'ESCALA'),
    ('Como você avalia o acolhimento e a cordialidade da recepção?', 'ESCALA'),
    ('Como você avalia o tempo de espera entre a sua chegada e o início do exame?', 'ESCALA'),
    ('Como você avalia as orientações sobre o preparo do exame e os cuidados com a radiação?', 'ESCALA'),
    ('Como você avalia o respeito à sua privacidade e à sua dignidade durante o atendimento?', 'ESCALA'),
    ('Como você avalia a atenção e o cuidado da equipe técnica e de enfermagem durante o exame?', 'ESCALA'),
    ('Como você avalia a limpeza e a higiene dos ambientes e banheiros?', 'ESCALA'),
    ('Como você avalia o conforto da sala de espera e das salas de exame?', 'ESCALA'),
    ('Como você avalia as informações sobre quando e como receber o resultado (laudo)?', 'ESCALA'),
    ('De modo geral, como você avalia o atendimento da clínica?', 'ESCALA'),
    ('Antes do exame, a equipe confirmou o seu nome completo e a sua data de nascimento?', 'SIMNAO'),
    ('Você recebeu orientações sobre os cuidados depois do exame (por exemplo, hidratação e contato com gestantes e crianças)?', 'SIMNAO'),
    ('De 0 a 10, quanto você recomendaria a nossa clínica a um amigo ou familiar?', 'NPS'),
)

ESQUEMA = """
CREATE TABLE IF NOT EXISTS cq_sat_perguntas (
    id INTEGER PRIMARY KEY, texto TEXT NOT NULL, ordem INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS cq_sat_respostas (
    id INTEGER PRIMARY KEY, data TEXT NOT NULL, criado_em TEXT NOT NULL, nome TEXT NOT NULL DEFAULT '', telefone TEXT NOT NULL DEFAULT '',
    elogio TEXT NOT NULL DEFAULT '', sugestao TEXT NOT NULL DEFAULT '', nota REAL, ip TEXT,
    revisada INTEGER NOT NULL DEFAULT 0, revisada_por TEXT, revisada_em TEXT
);
CREATE INDEX IF NOT EXISTS ix_cq_sat_resp_data ON cq_sat_respostas(data);
CREATE TABLE IF NOT EXISTS cq_sat_itens (
    resposta_id INTEGER NOT NULL, ordem INTEGER NOT NULL, pergunta TEXT NOT NULL, opcao TEXT NOT NULL,
    PRIMARY KEY (resposta_id, ordem)
);
"""

# colunas acrescentadas depois da primeira versão (bancos antigos ganham as colunas ao abrir)
COLUNAS_NOVAS = (
    ('cq_sat_perguntas', 'tipo', "TEXT NOT NULL DEFAULT 'ESCALA'"),
    ('cq_sat_itens', 'tipo', "TEXT NOT NULL DEFAULT 'ESCALA'"),
    ('cq_sat_respostas', 'origem', "TEXT NOT NULL DEFAULT 'QRCODE'"),
    ('cq_sat_respostas', 'exame', "TEXT NOT NULL DEFAULT ''"),
    ('cq_sat_respostas', 'atendimento', "TEXT NOT NULL DEFAULT ''"),
    ('cq_sat_respostas', 'respondente', "TEXT NOT NULL DEFAULT ''"),
    ('cq_sat_respostas', 'nps', 'INTEGER'),
    ('cq_sat_respostas', 'lancado_por', 'TEXT'),
)

_garantido = set()


class ErroPesquisa(ValueError):
    """Erro de validação mostrado ao usuário."""


def garantir(db):
    from .anexos import caminho_do_banco
    chave = caminho_do_banco(db) or id(db)
    if chave in _garantido:
        return
    from . import qualidade
    qualidade.garantir(db)   # a nota da pesquisa também entra na tabela de pesquisas do indicador de satisfação
    db.executescript(ESQUEMA)
    for tabela, coluna, ddl in COLUNAS_NOVAS:
        _coluna(db, tabela, coluna, ddl)
    # troca as perguntas UMA vez (pedido do usuário, conforme as exigências da ONA); as respostas antigas ficam como estão
    if _cfg(db, 'pesquisa_perguntas_ona_v1') != '1':
        db.execute('DELETE FROM cq_sat_perguntas')
        db.executemany('INSERT INTO cq_sat_perguntas (texto, tipo, ordem) VALUES (?,?,?)',
                       [(t, tp, i) for i, (t, tp) in enumerate(PERGUNTAS_SUGERIDAS, 1)])
        _definir(db, 'pesquisa_perguntas_ona_v1', '1')
    db.commit()
    _garantido.add(chave)


def _coluna(db, tabela, coluna, ddl):
    """Acrescenta a coluna se ela ainda não existir (bancos criados antes desta versão)."""
    if coluna not in {r[1] for r in db.execute('PRAGMA table_info(%s)' % tabela)}:
        db.execute('ALTER TABLE %s ADD COLUMN %s %s' % (tabela, coluna, ddl))


def _cfg(db, chave, padrao=''):
    r = db.execute('SELECT valor FROM config WHERE chave=?', (chave,)).fetchone()
    return r['valor'] if r and r['valor'] is not None else padrao


def _definir(db, chave, valor):
    db.execute('INSERT INTO config (chave, valor) VALUES (?,?) ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor', (chave, str(valor)))


# ------------------------------------------------------------------ configuração
def ativa(db):
    return _cfg(db, 'pesquisa_ativa', '1') == '1'


def definir_ativa(db, ligada):
    _definir(db, 'pesquisa_ativa', '1' if ligada else '0')
    db.commit()


def ip_da_maquina():
    """Endereço desta máquina na rede da clínica (o que o celular precisa digitar para chegar aqui)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))   # não envia nada: só descobre qual placa de rede seria usada
        return s.getsockname()[0]
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return '127.0.0.1'
    finally:
        s.close()


def endereco_base(db, porta):
    """http://endereço:porta usado no QR Code. A gerência pode trocar (ex.: http://recepcao:8080); sem isso usa o IP da máquina."""
    salvo = _cfg(db, 'pesquisa_endereco').strip().rstrip('/')
    if salvo:
        return salvo
    return 'http://%s:%s' % (ip_da_maquina(), porta)


def salvar_endereco(db, texto):
    texto = (texto or '').strip().rstrip('/')
    if texto and not re.match(r'^https?://', texto, re.I):
        texto = 'http://' + texto
    if texto and not re.fullmatch(r'https?://[A-Za-z0-9._\-]+(:\d{2,5})?', texto):
        raise ErroPesquisa('Endereço inválido. Use algo como http://192.168.0.10:8080 ou http://recepcao:8080.')
    _definir(db, 'pesquisa_endereco', texto)
    db.commit()


def endereco_salvo(db):
    return _cfg(db, 'pesquisa_endereco').strip()


def link_publico(db, porta):
    return endereco_base(db, porta) + '/pesquisa'


def ip_interno(addr):
    """A pesquisa só abre para quem está na rede interna (endereços privados, locais ou de link local)."""
    try:
        ip = ipaddress.ip_address((addr or '').split('%')[0])
    except ValueError:
        return False
    if getattr(ip, 'ipv4_mapped', None):
        ip = ip.ipv4_mapped
    return ip.is_private or ip.is_loopback or ip.is_link_local


# ------------------------------------------------------------------ QR Code (SVG, sem biblioteca extra)
def qr_svg(texto, borda=4):
    qr = qrencoder.QRCode(None, qrencoder.QRErrorCorrectLevel.M)
    qr.addData(texto)
    qr.make()
    n = qr.getModuleCount()
    caminhos = []
    for r in range(n):
        c = 0
        while c < n:
            if qr.isDark(r, c):
                ini = c
                while c < n and qr.isDark(r, c):
                    c += 1
                caminhos.append('M%d %dh%dv1h-%dz' % (ini + borda, r + borda, c - ini, c - ini))
            else:
                c += 1
    tam = n + 2 * borda
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" shape-rendering="crispEdges" role="img" '
            'aria-label="QR Code da pesquisa de satisfação"><rect width="100%%" height="100%%" fill="#fff"/>'
            '<path d="%s" fill="#000"/></svg>' % (tam, tam, ''.join(caminhos)))


# ------------------------------------------------------------------ perguntas
def _tipo(tipo):
    return tipo if tipo in OPCOES_POR_TIPO else 'ESCALA'


def perguntas(db):
    garantir(db)
    saida = []
    for r in db.execute('SELECT id, texto, ordem, tipo FROM cq_sat_perguntas ORDER BY ordem, id'):
        p = dict(r)
        p['tipo'] = _tipo(p['tipo'])
        p['opcoes'] = list(OPCOES_POR_TIPO[p['tipo']])
        saida.append(p)
    return saida


def exames_ativos(db):
    """Nomes dos exames ativos (para o perfil opcional da resposta)."""
    return [r['nome'] for r in db.execute('SELECT nome FROM exames WHERE ativo=1 ORDER BY ordem, nome')]


def salvar_perguntas(db, textos, tipos=None):
    """Troca o conjunto de perguntas (de 1 a 15). Perguntas em branco são ignoradas junto com o tipo; as respostas antigas guardam o texto que tinham."""
    tipos = list(tipos or [])
    pares = []
    for i, t in enumerate(textos):
        texto = re.sub(r'\s+', ' ', str(t or '')).strip()
        if texto:
            tp = tipos[i] if i < len(tipos) else 'ESCALA'
            pares.append((texto, _tipo(tp)))
    if not pares:
        raise ErroPesquisa('Deixe pelo menos uma pergunta na pesquisa.')
    if len(pares) > MAX_PERGUNTAS:
        raise ErroPesquisa('A pesquisa pode ter no máximo %d perguntas.' % MAX_PERGUNTAS)
    if any(len(t) > 200 for t, _ in pares):
        raise ErroPesquisa('Cada pergunta pode ter até 200 letras.')
    garantir(db)
    db.execute('DELETE FROM cq_sat_perguntas')
    db.executemany('INSERT INTO cq_sat_perguntas (texto, tipo, ordem) VALUES (?,?,?)', [(t, tp, i) for i, (t, tp) in enumerate(pares, 1)])
    _definir(db, 'pesquisa_perguntas_editadas', '1')
    db.commit()


def restaurar_sugestoes(db):
    garantir(db)
    db.execute('DELETE FROM cq_sat_perguntas')
    db.executemany('INSERT INTO cq_sat_perguntas (texto, tipo, ordem) VALUES (?,?,?)',
                   [(t, tp, i) for i, (t, tp) in enumerate(PERGUNTAS_SUGERIDAS, 1)])
    db.commit()


# ------------------------------------------------------------------ resposta do cliente
_ULTIMA = {}          # ip -> instante do último envio (evita enviar a mesma pesquisa várias vezes seguidas)
ESPERA_S = 40


def _limpo(valor, limite):
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', str(valor or '')).strip()[:limite]


def _valor_item(tipo, opcao):
    """Nota 0 a 10 de uma resposta: escala pela tabela, Sim/Não como 10/0 e NPS pelo próprio número."""
    if tipo == 'SIMNAO':
        return 10.0 if opcao == 'Sim' else 0.0
    if tipo == 'NPS':
        return float(int(opcao))
    return NOTA_OPCAO[opcao]


def _data_impresso(valor):
    """Data em que o cliente respondeu o impresso: vazia = hoje; no máximo 1 ano atrás e nunca no futuro."""
    hoje = date.today()
    if not (valor or '').strip():
        return hoje.isoformat()
    try:
        d = date.fromisoformat(valor.strip())
    except (ValueError, TypeError):
        d = None
    if d is None or d > hoje or d < hoje - timedelta(days=365):
        raise ErroPesquisa('Informe a data em que o cliente respondeu (até 1 ano atrás).')
    return d.isoformat()


def registrar_resposta(db, form, ip, origem='QRCODE', usuario=None):
    """Grava uma resposta. QR Code: todas as perguntas são obrigatórias e há espera e campo-armadilha. Impresso (lançado pela
    recepção): perguntas sem resposta são puladas e a data é a de quando o cliente respondeu."""
    garantir(db)
    if origem not in ORIGENS:
        origem = 'QRCODE'
    impresso = origem == 'IMPRESSO'
    if not impresso:
        if (form.get('site') or '').strip():      # campo-armadilha para robôs (escondido para as pessoas)
            raise ErroPesquisa('Não foi possível enviar.')
        agora_s = time.time()
        if agora_s - _ULTIMA.get(ip, 0) < ESPERA_S:
            raise ErroPesquisa('Sua resposta acabou de ser enviada. Obrigado!')
    perguntas_ativas = perguntas(db)
    if not perguntas_ativas:
        raise ErroPesquisa('A pesquisa está sendo atualizada. Tente novamente em instantes.')
    data = _data_impresso(form.get('data')) if impresso else date.today().isoformat()
    itens = []
    for i, p in enumerate(perguntas_ativas, 1):
        opcao = (form.get('p%d' % p['id']) or '').strip()
        if not opcao:
            if impresso:
                continue                           # no impresso, a pergunta sem marca é pulada
            raise ErroPesquisa('Responda todas as perguntas (falta a %d).' % i)
        if opcao not in OPCOES_POR_TIPO[p['tipo']]:
            raise ErroPesquisa('Resposta inválida na pergunta %d.' % i)
        itens.append((i, p['texto'], opcao, p['tipo']))
    if not itens:
        raise ErroPesquisa('Marque pelo menos uma resposta do questionário.')
    telefone = re.sub(r'[^0-9()+\-\s]', '', _limpo(form.get('telefone'), 30))
    escalas = [_valor_item(tp, o) for _, _, o, tp in itens if tp == 'ESCALA']
    valores = escalas or [_valor_item(tp, o) for _, _, o, tp in itens]
    nota = round(sum(valores) / len(valores), 1)
    nps_r = [int(o) for _, _, o, tp in itens if tp == 'NPS']
    nps = nps_r[0] if nps_r else None
    exame = _limpo(form.get('exame'), 80)
    atendimento = _limpo(form.get('atendimento'), 20)
    atendimento = atendimento if atendimento in ATENDIMENTOS else ''
    respondente = _limpo(form.get('respondente'), 20)
    respondente = respondente if respondente in RESPONDENTES else ''
    cur = db.execute('INSERT INTO cq_sat_respostas (data, criado_em, nome, telefone, elogio, sugestao, nota, ip, origem, exame, atendimento, '
                     'respondente, nps, lancado_por) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                     (data, agora(), _limpo(form.get('nome'), 80), telefone, _limpo(form.get('elogio'), 800),
                      _limpo(form.get('sugestao'), 800), nota, None if impresso else ip, origem, exame, atendimento, respondente,
                      nps, usuario if impresso else None))
    rid = cur.lastrowid
    db.executemany('INSERT INTO cq_sat_itens (resposta_id, ordem, pergunta, opcao, tipo) VALUES (?,?,?,?,?)', [(rid,) + t for t in itens])
    # a nota (0 a 10) da pesquisa também entra no indicador "Satisfação do paciente" do painel da qualidade
    try:
        db.execute('INSERT INTO cq_pesquisas (data, nota, exame, comentario, criado_por, criado_em) VALUES (?,?,?,?,?,?)',
                   (data, int(round(nota)), exame, (_limpo(form.get('sugestao'), 300) or _limpo(form.get('elogio'), 300)),
                    'PESQUISA QR CODE' if not impresso else 'PESQUISA IMPRESSA', agora()))
    except Exception:
        pass
    db.commit()
    if not impresso:
        _ULTIMA[ip] = agora_s
    return rid


# ------------------------------------------------------------------ respostas e indicadores
def lista_respostas(db, de, ate, so_pendentes=False, limite=500):
    garantir(db)
    sql = 'SELECT * FROM cq_sat_respostas WHERE data BETWEEN ? AND ?' + (' AND revisada=0' if so_pendentes else '') + ' ORDER BY id DESC LIMIT ?'
    saida = [dict(r) for r in db.execute(sql, (de, ate, limite))]
    if saida:
        ids = [r['id'] for r in saida]
        itens = {}
        for it in db.execute('SELECT * FROM cq_sat_itens WHERE resposta_id IN (%s) ORDER BY resposta_id, ordem' % ','.join('?' * len(ids)), ids):
            itens.setdefault(it['resposta_id'], []).append(dict(it))
        for r in saida:
            r['itens'] = itens.get(r['id'], [])
            r['origem_rotulo'] = ORIGENS.get(r['origem'], ORIGENS['QRCODE'])
            r['satisfeito'] = _satisfeito(r['itens'])
    return saida


def _satisfeito(itens):
    """Satisfeito = todas as escalas Ótimo/Bom e todos os Sim/Não em Sim (precisa ter ao menos uma escala ou Sim/Não)."""
    escalas = [i for i in itens if i['tipo'] == 'ESCALA']
    simnao = [i for i in itens if i['tipo'] == 'SIMNAO']
    if not escalas and not simnao:
        return False
    return all(i['opcao'] in SATISFEITO for i in escalas) and all(i['opcao'] == 'Sim' for i in simnao)


def marcar_revisada(db, rid, usuario, revisada=True):
    garantir(db)
    if not db.execute('SELECT 1 FROM cq_sat_respostas WHERE id=?', (rid,)).fetchone():
        raise ErroPesquisa('Esta resposta não existe mais.')
    db.execute('UPDATE cq_sat_respostas SET revisada=?, revisada_por=?, revisada_em=? WHERE id=?',
               (1 if revisada else 0, usuario if revisada else None, agora() if revisada else None, rid))
    db.commit()


def _pct(parte, total):
    return round(100.0 * parte / total, 1) if total else None


def _linha(texto, cont):
    total = sum(cont.values())
    media = round(sum(NOTA_OPCAO[o] * n for o, n in cont.items()) / total, 1) if total else None
    return {'texto': texto, 'total': total, 'otimo': cont.get('Ótimo', 0), 'bom': cont.get('Bom', 0), 'ruim': cont.get('Ruim', 0),
            'pessimo': cont.get('Péssimo', 0), 'satisfacao': _pct(cont.get('Ótimo', 0) + cont.get('Bom', 0), total), 'media': media}


def indicadores(db, de, ate):
    """Números do período: por pergunta e geral (% de Ótimo+Bom e média 0 a 10), elogios, sugestões, e por mês."""
    garantir(db)
    resp = db.execute('SELECT COUNT(*) AS n, SUM(elogio<>\'\') AS elogios, SUM(sugestao<>\'\') AS sugestoes, SUM(revisada=0) AS pendentes, '
                      'AVG(nota) AS media FROM cq_sat_respostas WHERE data BETWEEN ? AND ?', (de, ate)).fetchone()
    por, ordem, geral = {}, {}, {}
    for r in db.execute("SELECT i.pergunta, i.opcao, i.ordem, COUNT(*) AS n FROM cq_sat_itens i JOIN cq_sat_respostas r ON r.id=i.resposta_id "
                        "WHERE r.data BETWEEN ? AND ? AND i.tipo='ESCALA' GROUP BY i.pergunta, i.opcao", (de, ate)):
        por.setdefault(r['pergunta'], {})[r['opcao']] = r['n']
        ordem[r['pergunta']] = min(ordem.get(r['pergunta'], 99), r['ordem'])
        geral[r['opcao']] = geral.get(r['opcao'], 0) + r['n']
    linhas = [_linha(t, por[t]) for t in sorted(por, key=lambda t: (ordem[t], t))]
    meses = []
    for r in db.execute('SELECT substr(r.data,1,7) AS mes, COUNT(DISTINCT r.id) AS n, '
                        "SUM(CASE WHEN i.opcao IN ('Ótimo','Bom') THEN 1 ELSE 0 END) AS sat, COUNT(i.ordem) AS itens "
                        "FROM cq_sat_respostas r LEFT JOIN cq_sat_itens i ON i.resposta_id=r.id AND i.tipo='ESCALA' WHERE r.data BETWEEN ? AND ? "
                        'GROUP BY 1 ORDER BY 1', (de, ate)):
        meses.append({'mes': r['mes'], 'respostas': r['n'], 'satisfacao': _pct(r['sat'] or 0, r['itens'])})
    # segurança: perguntas Sim ou Não (o que a equipe fez ou orientou)
    sim_nao, ordem_sn = {}, {}
    for r in db.execute("SELECT i.pergunta, i.opcao, i.ordem, COUNT(*) AS n FROM cq_sat_itens i JOIN cq_sat_respostas r ON r.id=i.resposta_id "
                        "WHERE r.data BETWEEN ? AND ? AND i.tipo='SIMNAO' GROUP BY i.pergunta, i.opcao", (de, ate)):
        sim_nao.setdefault(r['pergunta'], {})[r['opcao']] = r['n']
        ordem_sn[r['pergunta']] = min(ordem_sn.get(r['pergunta'], 99), r['ordem'])
    seguranca = []
    for t in sorted(sim_nao, key=lambda t: (ordem_sn[t], t)):
        sim, nao = sim_nao[t].get('Sim', 0), sim_nao[t].get('Não', 0)
        seguranca.append({'texto': t, 'total': sim + nao, 'sim': sim, 'nao': nao, 'pct_sim': _pct(sim, sim + nao)})
    # NPS: recomendação de 0 a 10 (índice = % promotores − % detratores)
    notas = [int(r['opcao']) for r in db.execute("SELECT i.opcao FROM cq_sat_itens i JOIN cq_sat_respostas r ON r.id=i.resposta_id "
                                                  "WHERE r.data BETWEEN ? AND ? AND i.tipo='NPS'", (de, ate)) if str(r['opcao']).isdigit()]
    total_nps = len(notas)
    prom = sum(1 for n in notas if n >= 9)
    det = sum(1 for n in notas if n <= 6)
    nps = {'total': total_nps, 'promotores': prom, 'neutros': total_nps - prom - det, 'detratores': det,
           'indice': round(_pct(prom, total_nps) - _pct(det, total_nps), 1) if total_nps else None,
           'media': round(sum(notas) / total_nps, 1) if total_nps else None}
    # satisfação por exame (só respostas com exame informado)
    acum = {}
    for r in db.execute("SELECT r.id, r.exame, i.opcao FROM cq_sat_respostas r LEFT JOIN cq_sat_itens i ON i.resposta_id=r.id AND i.tipo='ESCALA' "
                        "WHERE r.data BETWEEN ? AND ? AND r.exame<>''", (de, ate)):
        a = acum.setdefault(r['exame'], {'ids': set(), 'sat': 0, 'itens': 0})
        a['ids'].add(r['id'])
        if r['opcao'] is not None:
            a['itens'] += 1
            a['sat'] += 1 if r['opcao'] in SATISFEITO else 0
    por_exame = [{'exame': e, 'respostas': len(a['ids']), 'satisfacao': _pct(a['sat'], a['itens'])} for e, a in acum.items()]
    por_exame.sort(key=lambda x: (-x['respostas'], x['exame']))
    return {'de': de, 'ate': ate, 'respostas': resp['n'] or 0, 'elogios': resp['elogios'] or 0, 'sugestoes': resp['sugestoes'] or 0,
            'pendentes': resp['pendentes'] or 0, 'media': round(resp['media'], 1) if resp['media'] is not None else None,
            'geral': _linha('Geral (todas as perguntas)', geral), 'perguntas': linhas, 'meses': meses,
            'seguranca': seguranca, 'nps': nps, 'por_exame': por_exame,
            'por_origem': _contagem(db, 'origem', de, ate, tuple(ORIGENS)),
            'por_atendimento': _contagem(db, 'atendimento', de, ate, ATENDIMENTOS + ('Não informado',)),
            'por_respondente': _contagem(db, 'respondente', de, ate, RESPONDENTES + ('Não informado',))}


def _contagem(db, coluna, de, ate, chaves):
    """Quantas respostas há por valor de uma coluna do perfil; vazio ou desconhecido vai para 'Não informado' (quando existe)."""
    saida = {c: 0 for c in chaves}
    for r in db.execute('SELECT %s AS k, COUNT(*) AS n FROM cq_sat_respostas WHERE data BETWEEN ? AND ? GROUP BY 1' % coluna, (de, ate)):
        k = r['k'] or ''
        if k in saida:
            saida[k] += r['n']
        elif 'Não informado' in saida:
            saida['Não informado'] += r['n']
    return saida


def excluir_respostas(db, ids):
    """Exclui respostas (e os itens de cada uma) definitivamente. Devolve quantas foram excluídas."""
    garantir(db)
    n = 0
    for rid in ids:
        db.execute('DELETE FROM cq_sat_itens WHERE resposta_id=?', (rid,))
        n += db.execute('DELETE FROM cq_sat_respostas WHERE id=?', (rid,)).rowcount
    db.commit()
    return n
