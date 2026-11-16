"""NucleAI: assistente de ajuda que conversa pelas Mensagens.

O usuário clica no botão redondo, a NucleAI cumpre e conduz o chat por listas numeradas (tema -> módulo -> área ->
instruções) ou entende uma dúvida escrita com as palavras do usuário. Depois pergunta se ajudou (e pede uma nota); se
não ajudou, oferece outra área, outro módulo, outro tema, chamar a gerência ou encerrar. O chat é temporário: ao
encerrar, as mensagens são apagadas. A essência (dúvida, quem chamou, se resolveu, nota) fica em `ajuda_registros`.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta

from . import ajuda_frases as F
from . import modulos, presenca
from . import nucleai_comandos as cmds
from .ajuda_alias import ALIASES
from .ajuda_base import TEMAS
from .ajuda_busca import CERTO, TALVEZ, Indice, decidir, normalizar, palavras
from .db import agora

BOT_USUARIO = 'NucleAI'
DESPEDIDA_S = 60        # padrão: a despedida some depois deste tempo (configurável)
SESSAO_MAX_H = 6        # padrão: conversa abandonada é apagada depois deste tempo (configurável)
CHAMADO_DIAS = 7        # os pedidos à gerência ficam nas mensagens por este tempo
FMT = '%Y-%m-%d %H:%M:%S'

TEMA, MODULO, AREA, ESCOLHA, SATISFEITO, NOTA, POS, ENCERRADO = (
    'TEMA', 'MODULO', 'AREA', 'ESCOLHA', 'SATISFEITO', 'NOTA', 'POS', 'ENCERRADO')

CMD = 'CMD'      # esperando o Sim/Não de um pedido ("imprimir a agenda do dia")

# resultados de cada consulta (para o painel)
RESOLVEU, RESOLVEU_E_NOVA, NAO_RESOLVEU, SEM_AVALIACAO, ABANDONOU = (
    'RESOLVEU', 'RESOLVEU_E_NOVA', 'NAO_RESOLVEU', 'SEM_AVALIACAO', 'ABANDONOU')


# ------------------------------------------------------------------ configuração (tabela config)
PADROES = {'nucleai_ativa': '1', 'nucleai_abandono_h': str(SESSAO_MAX_H), 'nucleai_despedida_s': str(DESPEDIDA_S),
           'nucleai_destinatarios': '[]'}


def cfg(db, chave):
    r = db.execute('SELECT valor FROM config WHERE chave=?', (chave,)).fetchone()
    return r['valor'] if r and r['valor'] is not None else PADROES[chave]


def cfg_int(db, chave, minimo, maximo):
    try:
        v = int(cfg(db, chave))
    except (TypeError, ValueError):
        v = int(PADROES[chave])
    return max(minimo, min(maximo, v))


def definir(db, chave, valor):
    db.execute('INSERT INTO config (chave, valor) VALUES (?,?) ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor',
               (chave, str(valor)))


def ativa(db):
    return cfg(db, 'nucleai_ativa') == '1'


def abandono_h(db):
    return cfg_int(db, 'nucleai_abandono_h', 1, 72)


def despedida_s(db):
    return cfg_int(db, 'nucleai_despedida_s', 10, 600)


def destinatarios_escolhidos(db):
    """Ids de usuário escolhidos pela administração para receber os pedidos de ajuda (vazio = toda a gerência)."""
    try:
        return [int(x) for x in json.loads(cfg(db, 'nucleai_destinatarios')) if str(x).isdigit()]
    except (ValueError, TypeError):
        return []


# ------------------------------------------------------------------ acesso básico
def bot_id(db):
    r = db.execute('SELECT id FROM usuarios WHERE sistema=3 AND usuario=?', (BOT_USUARIO,)).fetchone()
    return r['id'] if r else None


def sessao(db, uid):
    return db.execute('SELECT * FROM ajuda_sessoes WHERE usuario_id=?', (uid,)).fetchone()


def _salvar(db, uid, **campos):
    campos['atualizado_em'] = agora()
    nomes = ', '.join('%s=?' % k for k in campos)
    db.execute('UPDATE ajuda_sessoes SET %s WHERE usuario_id=?' % nomes, (*campos.values(), uid))


def _nome_completo(db, uid):
    from . import chat
    r = chat.usuario_ativo(db, uid)
    return ((r['nome'] if r else '') or '').strip().title() or 'Usuário'


def _primeiro_nome(db, uid):
    return (_nome_completo(db, uid).split() or ['amigo(a)'])[0]


def _bot_diz(db, uid, corpo, expira_s=None, para=None):
    """Mensagem da NucleAI para `uid` (ou para `para`). `expira_s`: some sozinha depois desse tempo."""
    expira = (datetime.now() + timedelta(seconds=expira_s)).strftime(FMT) if expira_s else None
    cur = db.execute('INSERT INTO chat_mensagens (de_id, para_id, corpo, criado_em, expira_em) VALUES (?,?,?,?,?)',
                     (bot_id(db), para or uid, corpo, agora(), expira))
    return dict(db.execute('SELECT * FROM chat_mensagens WHERE id=?', (cur.lastrowid,)).fetchone())


def _apagar_conversa(db, uid):
    from . import anexos
    b = bot_id(db)
    caminho = anexos.caminho_de(db)
    if caminho:
        rows = db.execute(
            'SELECT anexo_id FROM chat_mensagens WHERE ((de_id=? AND para_id=?) OR (de_id=? AND para_id=?)) AND anexo_id IS NOT NULL',
            (b, uid, uid, b),
        ).fetchall()
        for r in rows:
            anexos.apagar(caminho, r['anexo_id'])
    db.execute('DELETE FROM chat_mensagens WHERE (de_id=? AND para_id=?) OR (de_id=? AND para_id=?)', (b, uid, uid, b))


# ------------------------------------------------------------------ árvore de ajuda (base do código + edições da administração)
# (tema, módulo da ajuda) -> chave do módulo de permissão (None = livre; '__admin__' = só administrador)
# chave pode ser uma tupla ("qualquer um destes módulos"): a ajuda usa o módulo principal, o primeiro
def _montar_acesso():
    acesso = {}
    for grupo, itens in modulos.MENU:
        tema = grupo or 'Início e mensagens'
        for chave, rotulo, ep, _pref in itens:
            if ep in modulos.ABAS:   # telas que viraram botões: cada uma com o seu módulo
                abas = modulos.ABAS[ep]
                for a in abas:
                    acesso[(tema, a[1])] = a[0][0] if isinstance(a[0], tuple) else a[0]
                if chave is None and abas[0][0] != '__admin__':
                    chave = abas[0][0]
                elif chave is None:
                    continue    # o item que reúne as telas de administração não tem ajuda própria: valem as de cada tela
            acesso.setdefault((tema, rotulo), chave[0] if isinstance(chave, tuple) else chave)
    return acesso


ACESSO = _montar_acesso()


class Base:
    """A árvore de ajuda efetiva (base + edições) com as regras de acesso e o índice de busca."""

    def __init__(self, temas, acesso):
        self.temas = temas
        self.acesso = acesso
        self._indice = None

    @property
    def indice(self):
        if self._indice is None:
            self._indice = Indice(self.temas, ALIASES)
        return self._indice

    def localizar(self, tema, modulo, area=None):
        for ti, (t, mods) in enumerate(self.temas):
            if t != tema:
                continue
            for mi, (m, areas) in enumerate(mods):
                if m != modulo:
                    continue
                if area is None:
                    return ti, mi, None
                for ai, (a, _x) in enumerate(areas):
                    if a == area:
                        return ti, mi, ai
        return None


_BASE_ORIGINAL = Base(TEMAS, ACESSO)
_cache = {}


def invalidar():
    """A administração mudou o conteúdo: a próxima conversa já usa a versão nova."""
    _cache.clear()


def _montar(db):
    # cópia editável: [tema, [[módulo, [[área, texto]]]]]
    T = [[t, [[m, [[a, x] for a, x in areas]] for m, areas in mods]] for t, mods in TEMAS]
    acesso = dict(ACESSO)
    for r in db.execute('SELECT * FROM ajuda_conteudo ORDER BY id').fetchall():
        tema, modulo, area, texto = r['tema'], r['modulo'], r['area'], r['texto']
        t = next((x for x in T if x[0] == tema), None)
        if r['estado'] == 'EDITADA':
            m = next((x for x in t[1] if x[0] == modulo), None) if t else None
            a = next((x for x in m[1] if x[0] == area), None) if m else None
            if a:
                a[1] = texto
            continue
        if t is None:
            t = [tema, []]
            T.append(t)
        m = next((x for x in t[1] if x[0] == modulo), None)
        if m is None:
            m = [modulo, []]
            t[1].append(m)
            acesso.setdefault((tema, modulo), r['chave_acesso'] or None)
        a = next((x for x in m[1] if x[0] == area), None)
        if a:
            a[1] = texto
        else:
            m[1].append([area, texto])
    temas = [(t, [(m, [(a, x) for a, x in areas]) for m, areas in mods]) for t, mods in T]
    return Base(temas, acesso)


def base(db):
    """Árvore de ajuda atual. Sem edições da administração, é a própria base do código."""
    sig = db.execute('SELECT COUNT(*), COALESCE(MAX(id),0), COALESCE(MAX(atualizado_em),\'\'), COALESCE(SUM(LENGTH(texto)),0) '
                     'FROM ajuda_conteudo').fetchone()
    chave = tuple(sig)
    if chave[0] == 0:
        return _BASE_ORIGINAL
    b = _cache.get(chave)
    if b is None:
        b = _montar(db)
        _cache.clear()
        _cache[chave] = b
    return b


def liberados(db, uid):
    """(conjunto de módulos liberados, é administrador) do usuário."""
    u = db.execute('SELECT admin, modulos FROM usuarios WHERE id=?', (uid,)).fetchone()
    if u is None:
        return set(), False
    return modulos.modulos_do_usuario(u), bool(u['admin'])


def _pode(acesso, tema, modulo, mods, admin):
    if (tema, modulo) not in acesso:
        return True      # módulo criado pela administração sem permissão exigida
    chave = acesso[(tema, modulo)]
    if chave is None:
        return True
    if chave == '__admin__':
        return admin
    return chave in mods


def modulos_visiveis(db, uid, ti, B=None):
    """Índices (na árvore de ajuda) dos módulos do tema que o usuário pode usar."""
    B = B or base(db)
    mods, admin = liberados(db, uid)
    tema = B.temas[ti]
    return [i for i, m in enumerate(tema[1]) if _pode(B.acesso, tema[0], m[0], mods, admin)]


def temas_visiveis(db, uid, B=None):
    """Índices dos temas que têm ao menos um módulo liberado para o usuário."""
    B = B or base(db)
    mods, admin = liberados(db, uid)
    return [ti for ti, (tema, ms) in enumerate(B.temas) if any(_pode(B.acesso, tema, m[0], mods, admin) for m in ms)]


# ------------------------------------------------------------------ textos
def _numero(texto):
    """Número digitado pelo usuário ('2', ' 2 ', '2.', '2)', '2 -'); None se não for só um número."""
    m = re.fullmatch(r'\s*(\d{1,2})\s*[.)\-]?\s*', str(texto or ''))
    return int(m.group(1)) if m else None


def _lista(itens):
    return '\n'.join('%d - %s' % (i, t) for i, t in enumerate(itens, 1))


def menu_temas(vis=None, T=None):
    T = T or TEMAS
    vis = list(range(len(T))) if vis is None else vis
    return ('Sobre qual tema você precisa de ajuda? Responda só com o número:\n\n'
            + _lista(T[i][0] for i in vis) + '\n0 - Encerrar este chat')


def menu_modulos(ti, vis=None, T=None):
    T = T or TEMAS
    tema = T[ti]
    vis = list(range(len(tema[1]))) if vis is None else vis
    return ('📂 %s\nQual módulo? Responda com o número:\n\n' % tema[0]
            + _lista(tema[1][i][0] for i in vis) + '\n0 - Voltar aos temas')


def menu_areas(ti, mi, T=None):
    T = T or TEMAS
    modulo = T[ti][1][mi]
    return ('🧩 %s\nEm qual parte do módulo você precisa de ajuda? Responda com o número:\n\n' % modulo[0]
            + _lista(a[0] for a in modulo[1]) + '\n0 - Voltar aos módulos')


def instrucoes(ti, mi, ai, T=None):
    T = T or TEMAS
    modulo = T[ti][1][mi]
    area = modulo[1][ai]
    return '📘 %s › %s\n\n%s' % (modulo[0], area[0], area[1])


PERGUNTA_SATISFEITO = ('Consegui te ajudar? 😊\n1 - Sim, deu certo!\n2 - Sim, ajudou, mas quero perguntar de novo\n'
                       '3 - Não, ainda preciso de ajuda')

MENU_POS = ('Poxa, que pena! 😔 Vamos tentar de outro jeito. O que você prefere?\n\n'
            '1 - Ver outra área deste módulo\n2 - Ver outro módulo deste tema\n3 - Ver outro tema\n'
            '4 - Chamar a gerência\n5 - Encerrar o chat')

DESATIVADA = 'A NucleAI está desligada no momento. Procure a administração para ajuda. 💚'


def menu_escolha(candidatos, T):
    linhas = ['%d - %s › %s' % (i, T[ti][1][mi][0], T[ti][1][mi][1][ai][0]) for i, (ti, mi, ai) in enumerate(candidatos, 1)]
    linhas.append('%d - Nenhuma dessas, quero ver a lista de temas' % (len(candidatos) + 1))
    return ('Encontrei estas possibilidades para a sua dúvida. 🔎 Qual delas é a mais parecida? Responda com o número:\n\n'
            + '\n'.join(linhas))


def saudacao(nome, vis=None, T=None):
    return '%s\n\n%s\n\n%s' % (F.escolher(F.SAUDACOES, nome=nome), F.SUFIXO_ESCOLHA, menu_temas(vis, T))


# ------------------------------------------------------------------ registros (a essência que fica depois que o chat é apagado)
def _registro_novo(db, uid, T, ti, mi, ai, origem, duvida):
    s = sessao(db, uid)
    if s and s['registro_id']:
        _registro_fechar(db, s['registro_id'], SEM_AVALIACAO, so_se_pendente=True)
    u = db.execute('SELECT usuario FROM usuarios WHERE id=?', (uid,)).fetchone()
    cur = db.execute('INSERT INTO ajuda_registros (criado_em, usuario_id, usuario, tema, modulo, area, origem, duvida) '
                     'VALUES (?,?,?,?,?,?,?,?)',
                     (agora(), uid, u['usuario'] if u else '', T[ti][0], T[ti][1][mi][0], T[ti][1][mi][1][ai][0], origem, duvida))
    return cur.lastrowid


def _registro_fechar(db, rid, resultado=None, nota=None, so_se_pendente=False):
    if not rid:
        return
    if so_se_pendente:
        db.execute('UPDATE ajuda_registros SET resultado=?, respondido_em=? WHERE id=? AND resultado IS NULL', (resultado, agora(), rid))
        return
    if resultado is not None:
        db.execute('UPDATE ajuda_registros SET resultado=?, respondido_em=? WHERE id=?', (resultado, agora(), rid))
    if nota is not None:
        db.execute('UPDATE ajuda_registros SET nota=? WHERE id=?', (nota, rid))


def _nao_entendida(db, uid, texto):
    u = db.execute('SELECT usuario FROM usuarios WHERE id=?', (uid,)).fetchone()
    db.execute('INSERT INTO ajuda_nao_entendidas (criado_em, usuario_id, usuario, texto) VALUES (?,?,?,?)',
               (agora(), uid, u['usuario'] if u else '', str(texto)[:300]))


# ------------------------------------------------------------------ fluxo
def _res(mensagens, encerrado=False):
    return {'mensagens': mensagens, 'encerrado': encerrado}


def iniciar(db, uid):
    """Começa (ou recomeça) uma conversa de ajuda: apaga o que havia e manda a saudação com a lista de temas."""
    s = sessao(db, uid)
    if s and s['registro_id']:
        _registro_fechar(db, s['registro_id'], SEM_AVALIACAO, so_se_pendente=True)
    _apagar_conversa(db, uid)
    db.execute('INSERT INTO ajuda_sessoes (usuario_id, estado, tema, modulo, area, gerencia_chamada, atualizado_em, candidatos, '
               'registro_id, duvida, origem, seguinte) VALUES (?,?,NULL,NULL,NULL,0,?,NULL,NULL,NULL,NULL,NULL) '
               'ON CONFLICT(usuario_id) DO UPDATE SET estado=excluded.estado, tema=NULL, modulo=NULL, area=NULL, '
               'gerencia_chamada=0, atualizado_em=excluded.atualizado_em, candidatos=NULL, registro_id=NULL, duvida=NULL, '
               'origem=NULL, seguinte=NULL', (uid, TEMA, agora()))
    B = base(db)
    from . import nucleai_motor
    ola = nucleai_motor.saudacao(db, uid, _primeiro_nome(db, uid))   # quem tem a IA liberada recebe a saudação dela
    msg = _bot_diz(db, uid, ola or saudacao(_primeiro_nome(db, uid), temas_visiveis(db, uid, B), B.temas))
    db.commit()
    return msg


def _encerrar(db, uid, frase):
    s = sessao(db, uid)
    if s and s['registro_id']:
        _registro_fechar(db, s['registro_id'], SEM_AVALIACAO, so_se_pendente=True)
    _apagar_conversa(db, uid)
    _salvar(db, uid, estado=ENCERRADO, registro_id=None)
    msg = _bot_diz(db, uid, frase, expira_s=despedida_s(db))
    return _res([msg], True)


# ---- chamado à gerência
def gerencia_do_sistema(db, excluir_uid=None):
    """Quem recebe os pedidos de ajuda: as pessoas escolhidas pela administração; sem escolha, toda a gerência."""
    escolhidos = destinatarios_escolhidos(db)
    saida = []
    for u in db.execute('SELECT id, admin, modulos FROM usuarios WHERE ativo=1 AND COALESCE(sistema,0)=0').fetchall():
        if u['id'] == excluir_uid:
            continue
        if escolhidos:
            if u['id'] in escolhidos:
                saida.append(u['id'])
        elif 'gerencia' in modulos.modulos_do_usuario(u):
            saida.append(u['id'])
    return saida


def _onde(T, ti, mi, ai):
    onde = T[ti][0]
    if mi is not None:
        onde += ' › ' + T[ti][1][mi][0]
        if ai is not None:
            onde += ' › ' + T[ti][1][mi][1][ai][0]
    return onde


def chamar_gerencia(db, uid, s, B):
    """Avisa a gerência pela NucleAI, com o botão para falar com o usuário. Devolve {avisados, online, chamado_id}."""
    T = B.temas
    destinos = gerencia_do_sistema(db, excluir_uid=uid)
    if not destinos:
        return {'avisados': 0, 'online': 0, 'chamado_id': None}
    ti, mi, ai = s['tema'], s['modulo'], s['area']
    onde = _onde(T, ti, mi, ai)
    duvida = s['duvida'] if s['origem'] == 'TEXTO' else None
    nome = _primeiro_nome(db, uid)
    login = db.execute('SELECT usuario FROM usuarios WHERE id=?', (uid,)).fetchone()['usuario']
    estado_pres = presenca.situacao(db)
    online = sum(1 for d in destinos if estado_pres.get(d, {}).get('online'))
    cur = db.execute('INSERT INTO ajuda_chamados (criado_em, usuario_id, usuario, registro_id, tema, modulo, area, duvida, '
                     'gerencia_online, avisados) VALUES (?,?,?,?,?,?,?,?,?,?)',
                     (agora(), uid, login, s['registro_id'], T[ti][0], T[ti][1][mi][0] if mi is not None else None,
                      T[ti][1][mi][1][ai][0] if mi is not None and ai is not None else None, duvida, 1 if online else 0, len(destinos)))
    cid = cur.lastrowid
    corpo = ('NucleAI enviou por %s: Olá, gestão! Aqui é a NucleAI 🤖. Infelizmente não consegui sanar as dúvidas do usuário %s '
             'sobre "%s"%s 😟 e é preciso ajuda. Aguardamos! 💚\n\nPara abrir a conversa com uma pergunta pronta, '
             'use o botão abaixo.' % (nome, nome, onde, (' (dúvida escrita: "%s")' % duvida) if duvida else ''))
    expira = (datetime.now() + timedelta(days=CHAMADO_DIAS)).strftime(FMT)
    for d in destinos:
        db.execute('INSERT INTO chat_mensagens (de_id, para_id, corpo, criado_em, expira_em, acao, chamado_id) VALUES (?,?,?,?,?,?,?)',
                   (bot_id(db), d, corpo, agora(), expira, 'CHAMADO_FALAR', cid))
    if s['registro_id']:
        db.execute('UPDATE ajuda_registros SET chamou_gerencia=1 WHERE id=?', (s['registro_id'],))
    return {'avisados': len(destinos), 'online': online, 'chamado_id': cid}


def _texto_chamado(r):
    return 'Pronto! 🚨 Avisei %s da gerência sobre o seu caso. Em breve alguém fala com você.' % (
        'a pessoa responsável' if r['avisados'] == 1 else '%d pessoas' % r['avisados'])


def _resposta_gerencia(r):
    if not r['avisados']:
        return 'Não encontrei ninguém da gerência para avisar agora. 😕 Procure a administração.'
    if r['online']:
        return _texto_chamado(r)
    return ('Avisei a gerência, mas no momento ninguém responsável está online, então não podem responder agora. 💚 '
            'Assim que entrarem no sistema vão ver o seu pedido e responder o mais rápido possível.')


# ---- fluxo principal
def _validar_indices(T, s):
    """False se a árvore mudou e os índices guardados deixaram de existir."""
    ti, mi, ai = s['tema'], s['modulo'], s['area']
    try:
        if ti is not None:
            tema = T[ti]
            if mi is not None:
                modulo = tema[1][mi]
                if ai is not None:
                    modulo[1][ai]
        return True
    except (IndexError, TypeError):
        return False


def _sim_ou_nao(texto):
    """1, 2 ou 3 se o texto for um 'sim', 'sim, mas quero perguntar de novo' ou 'não' em palavras; senão None."""
    p = set(normalizar(texto).split())
    if not p or len(p) > 6:
        return None
    sim = p & {'sim', 'ajudou', 'resolveu', 'consegui', 'certo', 'ok', 'obrigado', 'obrigada', 'valeu', 'perfeito'}
    nao = p & {'nao', 'nada', 'nunca'}
    if 'sim' in p and p & {'novo', 'novamente', 'outra', 'outro', 'perguntar'}:
        return 2                       # "sim, mas quero perguntar de novo"
    if nao:
        return 3                       # "não", "não ajudou", "não resolveu"
    if sim:
        return 1
    return None


def _nova_duvida(db, uid, texto, s, B, vt, menu_atual):
    """Dúvida escrita pelo usuário: entende e responde, mostra possibilidades ou diz que não entendeu e volta à lista."""
    T = B.temas
    permitidos = {(ti, mi) for ti in vt for mi in modulos_visiveis(db, uid, ti, B)}
    resultados = B.indice.buscar(texto, permitido=lambda ti, mi: (ti, mi) in permitidos)
    nivel, achados = decidir(resultados)
    if nivel == CERTO:
        r = achados[0]
        return _entregar(db, uid, B, r['ti'], r['mi'], r['ai'], 'TEXTO', texto, abertura=True)
    if nivel == TALVEZ:
        cands = [[r['ti'], r['mi'], r['ai']] for r in achados]
        _salvar(db, uid, estado=ESCOLHA, candidatos=json.dumps(cands), duvida=texto, origem='TEXTO')
        return _res([_bot_diz(db, uid, menu_escolha(cands, T))])
    _nao_entendida(db, uid, texto)
    return _res([_bot_diz(db, uid, F.escolher(F.NAO_ENTENDI_DUVIDA)), _bot_diz(db, uid, menu_atual)])


def _entregar(db, uid, B, ti, mi, ai, origem, duvida, abertura=False):
    T = B.temas
    rid = _registro_novo(db, uid, T, ti, mi, ai, origem, duvida)
    _salvar(db, uid, estado=SATISFEITO, tema=ti, modulo=mi, area=ai, registro_id=rid, duvida=duvida, origem=origem,
            candidatos=None)
    msgs = []
    if abertura:
        msgs.append(_bot_diz(db, uid, '%s «%s › %s». Veja:' % (F.escolher(F.ENTENDI), T[ti][1][mi][0], T[ti][1][mi][1][ai][0])))
    msgs.append(_bot_diz(db, uid, instrucoes(ti, mi, ai, T)))
    msgs.append(_bot_diz(db, uid, PERGUNTA_SATISFEITO))
    return _res(msgs)


def responder(db, uid, texto):
    """Resposta da NucleAI a uma mensagem do usuário. Devolve {'mensagens': [...], 'encerrado': bool}.
    Quem tem a IA online liberada (nucleai_ia) é atendido por ela; sem internet ou sem cota, a resposta volta a ser a
    automática (por regras), com um aviso antes."""
    s = sessao(db, uid)
    antes = []
    if s is not None and ativa(db) and s['estado'] != ENCERRADO:
        from . import nucleai_motor
        r = nucleai_motor.talvez_responder(db, uid, texto)
        if r is not None:
            if not r.get('seguir_regras'):
                return r
            antes = r['mensagens']
    r = _responder_regras(db, uid, texto)
    if antes:
        r['mensagens'] = antes + r['mensagens']
    return r


def _responder_regras(db, uid, texto):
    """Resposta automática (por regras): listas numeradas, busca na base de ajuda e comandos."""
    s = sessao(db, uid)
    if s is None:
        return _res([])
    if not ativa(db):
        return _encerrar(db, uid, DESATIVADA)
    B = base(db)
    T = B.temas
    n = _numero(texto)
    est = s['estado']
    nome = _primeiro_nome(db, uid)

    def diz(corpo):
        return _bot_diz(db, uid, corpo)

    def invalida(menu):
        return _res([diz(F.escolher(F.NAO_ENTENDI)), diz(menu)])

    if est == ENCERRADO:
        return _res([_bot_diz(db, uid, 'Esta conversa já foi encerrada. 💚 Para falar comigo de novo, clique no botão redondo no canto da tela.',
                              expira_s=despedida_s(db))], True)

    vt = temas_visiveis(db, uid, B)
    if est in (MODULO, AREA, SATISFEITO, POS) and not _validar_indices(T, s):
        _salvar(db, uid, estado=TEMA, tema=None, modulo=None, area=None)
        return _res([diz('O conteúdo da ajuda foi atualizado, então vamos recomeçar. 💚\n\n' + menu_temas(vt, T))])

    # ---- pedidos (comandos): perguntas continuam sendo dúvidas de ajuda; um pedido só é feito depois do Sim
    if est == CMD or (est != NOTA and n is None):
        r = cmds.tratar(db, uid, texto, est)
        if r is not None:
            return r

    def e_duvida_escrita():
        return n is None and len(palavras(texto)) >= 1 and len(normalizar(texto)) >= 3 and any(c.isalpha() for c in str(texto))

    # ---- nota de satisfação (opcional)
    if est == NOTA:
        if n is None or not 0 <= n <= 5:
            return invalida(F.PEDIDO_NOTA)
        if n:
            _registro_fechar(db, s['registro_id'], nota=n)
        if s['seguinte'] == 'NOVA':
            _salvar(db, uid, estado=TEMA, tema=None, modulo=None, area=None, candidatos=None, duvida=None, origem=None, seguinte=None)
            return _res([diz('Claro! 😊 Vamos lá de novo.\n\n%s\n\n%s' % (F.SUFIXO_ESCOLHA, menu_temas(vt, T)))])
        return _encerrar(db, uid, '%s\n\n%s' % (F.escolher(F.AGRADECIMENTOS, nome=nome), F.SUFIXO_APAGAR))

    # ---- lista de temas
    if est == TEMA:
        if n == 0:
            return _encerrar(db, uid, F.escolher(F.DESPEDIDAS, nome=nome))
        if n is not None:
            if not 1 <= n <= len(vt):
                return invalida(menu_temas(vt, T))
            ti = vt[n - 1]
            _salvar(db, uid, estado=MODULO, tema=ti, modulo=None, area=None)
            return _res([diz(menu_modulos(ti, modulos_visiveis(db, uid, ti, B), T))])
        if e_duvida_escrita():
            return _nova_duvida(db, uid, texto, s, B, vt, menu_temas(vt, T))
        return invalida(menu_temas(vt, T))

    # ---- lista de módulos
    if est == MODULO:
        ti = s['tema']
        vm = modulos_visiveis(db, uid, ti, B)
        if n == 0:
            _salvar(db, uid, estado=TEMA, tema=None)
            return _res([diz(menu_temas(vt, T))])
        if n is not None:
            if not 1 <= n <= len(vm):
                return invalida(menu_modulos(ti, vm, T))
            mi = vm[n - 1]
            _salvar(db, uid, estado=AREA, modulo=mi, area=None)
            return _res([diz(menu_areas(ti, mi, T))])
        if e_duvida_escrita():
            return _nova_duvida(db, uid, texto, s, B, vt, menu_modulos(ti, vm, T))
        return invalida(menu_modulos(ti, vm, T))

    # ---- lista de áreas
    if est == AREA:
        ti, mi = s['tema'], s['modulo']
        if n == 0:
            _salvar(db, uid, estado=MODULO, modulo=None)
            return _res([diz(menu_modulos(ti, modulos_visiveis(db, uid, ti, B), T))])
        if n is not None:
            if not 1 <= n <= len(T[ti][1][mi][1]):
                return invalida(menu_areas(ti, mi, T))
            return _entregar(db, uid, B, ti, mi, n - 1, 'LISTA', None)
        if e_duvida_escrita():
            return _nova_duvida(db, uid, texto, s, B, vt, menu_areas(ti, mi, T))
        return invalida(menu_areas(ti, mi, T))

    # ---- possibilidades encontradas pela busca
    if est == ESCOLHA:
        try:
            cands = json.loads(s['candidatos'] or '[]')
        except ValueError:
            cands = []
        if not cands:
            _salvar(db, uid, estado=TEMA, candidatos=None)
            return _res([diz(menu_temas(vt, T))])
        if n is not None:
            if 1 <= n <= len(cands):
                ti, mi, ai = cands[n - 1]
                return _entregar(db, uid, B, ti, mi, ai, 'TEXTO', s['duvida'])
            if n == len(cands) + 1:
                _salvar(db, uid, estado=TEMA, tema=None, modulo=None, area=None, candidatos=None)
                return _res([diz('Sem problemas! 😊 Escolha o tema abaixo, ou escreva a dúvida de outro jeito.\n\n' + menu_temas(vt, T))])
            return invalida(menu_escolha(cands, T))
        if e_duvida_escrita():
            return _nova_duvida(db, uid, texto, s, B, vt, menu_temas(vt, T))
        return invalida(menu_escolha(cands, T))

    # ---- "consegui te ajudar?"
    if est == SATISFEITO:
        escolha = n if n in (1, 2, 3) else (_sim_ou_nao(texto) if n is None else None)
        if escolha is None and e_duvida_escrita() and len(palavras(texto)) >= 2:
            return _nova_duvida(db, uid, texto, s, B, vt, PERGUNTA_SATISFEITO)   # já é uma nova dúvida
        if escolha == 1 or escolha == 2:
            _registro_fechar(db, s['registro_id'], RESOLVEU if escolha == 1 else RESOLVEU_E_NOVA)
            _salvar(db, uid, estado=NOTA, seguinte='ENCERRAR' if escolha == 1 else 'NOVA')
            return _res([diz(F.PEDIDO_NOTA)])
        if escolha == 3:
            _registro_fechar(db, s['registro_id'], NAO_RESOLVEU)
            _salvar(db, uid, estado=POS)
            return _res([diz(MENU_POS)])
        return invalida(PERGUNTA_SATISFEITO)

    # ---- "poxa, que pena": outras opções
    if est == POS:
        ti, mi = s['tema'], s['modulo']
        if n == 1:
            _salvar(db, uid, estado=AREA, area=None)
            return _res([diz(menu_areas(ti, mi, T))])
        if n == 2:
            _salvar(db, uid, estado=MODULO, modulo=None, area=None)
            return _res([diz(menu_modulos(ti, modulos_visiveis(db, uid, ti, B), T))])
        if n == 3:
            _salvar(db, uid, estado=TEMA, tema=None, modulo=None, area=None)
            return _res([diz(menu_temas(vt, T))])
        if n == 4:
            if s['gerencia_chamada']:
                aviso = 'Eu já avisei a gerência sobre o seu caso. 💚 Em breve alguém fala com você.'
            else:
                r = chamar_gerencia(db, uid, s, B)
                if r['avisados']:
                    _salvar(db, uid, gerencia_chamada=1)
                aviso = _resposta_gerencia(r)
            return _res([diz(aviso), diz(MENU_POS)])
        if n == 5:
            return _encerrar(db, uid, F.escolher(F.DESPEDIDAS, nome=nome))
        if n is None and e_duvida_escrita():
            return _nova_duvida(db, uid, texto, s, B, vt, MENU_POS)
        return invalida(MENU_POS)

    return _res([])


# ------------------------------------------------------------------ detalhes para a gerência (chamado confirmado)
def _readme_secoes():
    caminho = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'LEIA-ME.md')
    try:
        with open(caminho, encoding='utf-8') as fh:
            linhas = fh.read().splitlines()
    except OSError:
        return []
    secoes, titulo, corpo = [], None, []
    for ln in linhas:
        if ln.startswith('## ') or ln.startswith('### '):
            if titulo and corpo:
                secoes.append((titulo, '\n'.join(corpo).strip()))
            titulo, corpo = ln.lstrip('#').strip(), []
        elif titulo is not None:
            corpo.append(ln)
    if titulo and corpo:
        secoes.append((titulo, '\n'.join(corpo).strip()))
    return secoes


def trecho_readme(tema, modulo, area, limite=1100):
    """Citação do LEIA-ME mais ligada ao assunto: (título da seção, trecho) ou None."""
    from .ajuda_busca import radical
    alvo = {radical(p) for p in palavras('%s %s %s' % (modulo, area, tema))}
    melhor, pontos = None, 0
    for titulo, corpo in _readme_secoes():
        radicais = {radical(p) for p in palavras(titulo + ' ' + corpo)}
        titulos = {radical(p) for p in palavras(titulo)}
        p = len(alvo & radicais) + 3 * len(alvo & titulos)
        if p > pontos:
            melhor, pontos = (titulo, corpo), p
    if not melhor or pontos < 3:
        return None
    titulo, corpo = melhor
    trecho = corpo
    # prefere o parágrafo (ou linha de lista) que cita o módulo
    paragrafos = [x.strip() for x in re.split(r'\n\s*\n|\n(?=[-*|] )', corpo) if x.strip()]
    chave = {radical(p) for p in palavras(modulo)}
    achados = [x for x in paragrafos if chave & {radical(p) for p in palavras(x)}]
    if achados:
        trecho = '\n'.join(achados[:3])
    return titulo, (trecho[:limite].rstrip() + ('…' if len(trecho) > limite else ''))


CHECKLIST = ('✅ Se a pessoa continuar com dificuldade, confira nesta ordem:\n'
             '1. Peça para ela dizer em qual tela está e qual mensagem aparece.\n'
             '2. Veja se o perfil dela tem o módulo liberado (Configuração › Usuários e perfis).\n'
             '3. Peça para atualizar a página (tecla F5) e tentar de novo.\n'
             '4. Confira em "Registros de atividades" se a ação dela foi gravada.\n'
             '5. Se houver erro, veja os últimos erros e a versão em "Saúde do sistema".')


def detalhe_para_gerencia(db, ch):
    """Mensagens detalhadas (até 3) com a área da dúvida explicada, para a gerência ajudar o usuário."""
    B = base(db)
    T = B.temas
    loc = B.localizar(ch['tema'], ch['modulo'], ch['area']) if ch['modulo'] else None
    nome = ch['usuario']
    cab = '📋 Resumo para a gerência\nDúvida de %s\nAssunto: %s › %s › %s' % (nome, ch['tema'], ch['modulo'] or '—', ch['area'] or '—')
    if ch['duvida']:
        cab += '\nDúvida escrita pelo usuário: "%s"' % ch['duvida']
    msgs = []
    if loc and loc[2] is not None:
        ti, mi, ai = loc
        area_txt = T[ti][1][mi][1][ai][1]
        msgs.append(('%s\n\n📘 Passo a passo completo:\n%s' % (cab, area_txt))[:1990])
        # o módulo, o que ele faz e quem acessa
        chave = B.acesso.get((ch['tema'], ch['modulo']))
        descricao = next((m[3] for m in modulos.MODULOS if m[0] == chave), None) if chave else None
        partes = ['🧩 Sobre o módulo "%s"' % ch['modulo']]
        if descricao:
            partes.append('O que faz: %s.' % descricao.rstrip('.'))
        if chave == '__admin__':
            partes.append('Quem acessa: somente administradores.')
        elif chave:
            partes.append('Quem acessa: quem tem o módulo "%s" liberado em Configuração › Usuários e perfis (administradores sempre têm).'
                          % modulos.NOMES.get(chave, chave))
        outras = [a for k, a in enumerate(T[ti][1][mi][1]) if k != ai]
        if outras:
            partes.append('Outras áreas deste módulo (a pessoa pode estar na área ao lado):')
            for a, x in outras:
                primeira = re.sub(r'\s+', ' ', x.split('\n')[0]).strip()
                partes.append('• %s: %s' % (a, primeira[:140] + ('…' if len(primeira) > 140 else '')))
        partes.append('\n' + CHECKLIST)
        msgs.append('\n'.join(partes)[:1990])
        citacao = trecho_readme(ch['tema'], ch['modulo'], ch['area'])
        if citacao:
            msgs.append(('📖 Do LEIA-ME › %s:\n"%s"' % citacao)[:1990])
    else:
        msgs.append('%s\n\nNão encontrei a área no conteúdo atual (ela pode ter sido renomeada).\n\n%s' % (cab, CHECKLIST))
    return msgs


def _expira_chamado():
    return (datetime.now() + timedelta(days=CHAMADO_DIAS)).strftime(FMT)


def contatar_chamado(db, cid, gerente_id):
    """A gerência clicou em 'Falar com o usuário': marca em atendimento e envia ao usuário a pergunta de confirmação
    (com botões Sim/Não). Devolve (id do usuário, mensagem enviada ou None, aviso ou None); lança ValueError se não der."""
    ch = db.execute('SELECT * FROM ajuda_chamados WHERE id=?', (cid,)).fetchone()
    if ch is None:
        raise ValueError('Este pedido de ajuda não existe mais.')
    usuario = db.execute('SELECT id FROM usuarios WHERE id=? AND ativo=1', (ch['usuario_id'],)).fetchone()
    if usuario is None:
        raise ValueError('A pessoa que pediu ajuda não está mais ativa no sistema.')
    if ch['status'] == 'RESOLVIDO':
        raise ValueError('Este pedido já foi marcado como resolvido.')
    if ch['status'] == 'EM_ATENDIMENTO' and ch['atendido_por_id'] != gerente_id:
        return ch['usuario_id'], None, 'Este pedido já está sendo atendido por %s.' % ch['atendido_por']
    if ch['status'] == 'EM_ATENDIMENTO':
        return ch['usuario_id'], None, 'Você já iniciou a conversa deste pedido.'
    gerente = _nome_completo(db, gerente_id)
    db.execute("UPDATE ajuda_chamados SET status='EM_ATENDIMENTO', atendido_por=?, atendido_por_id=?, atendido_em=? WHERE id=?",
               (gerente, gerente_id, agora(), cid))
    onde = ch['tema'] + ((' › ' + ch['modulo']) if ch['modulo'] else '') + ((' › ' + ch['area']) if ch['area'] else '')
    corpo = ('Olá, %s! Aqui é %s, da gerência. Recebi o seu pedido de ajuda da NucleAI sobre «%s»%s. '
             'A sua dúvida é sobre isso mesmo? Responda com os botões abaixo.'
             % (ch['usuario'].title(), gerente, onde, (', com a dúvida "%s"' % ch['duvida']) if ch['duvida'] else ''))
    cur = db.execute('INSERT INTO chat_mensagens (de_id, para_id, corpo, criado_em, acao, chamado_id) VALUES (?,?,?,?,?,?)',
                     (gerente_id, ch['usuario_id'], corpo, agora(), 'CHAMADO_CONFIRMA', cid))
    msg = dict(db.execute('SELECT * FROM chat_mensagens WHERE id=?', (cur.lastrowid,)).fetchone())
    return ch['usuario_id'], msg, None


def confirmar_chamado(db, cid, usuario_id, resposta):
    """O usuário respondeu Sim ou Não à confirmação da gerência. Sim: a NucleAI envia à gerência o detalhamento da área.
    Devolve o texto para mostrar ao usuário."""
    ch = db.execute('SELECT * FROM ajuda_chamados WHERE id=?', (cid,)).fetchone()
    if ch is None or ch['usuario_id'] != usuario_id:
        raise ValueError('Este pedido não é seu.')
    if ch['confirmou']:
        return 'Você já respondeu a esta pergunta.'
    resposta = 'SIM' if resposta == 'SIM' else 'NAO'
    db.execute('UPDATE ajuda_chamados SET confirmou=?, confirmado_em=? WHERE id=?', (resposta, agora(), cid))
    db.execute("UPDATE chat_mensagens SET acao_resp=? WHERE chamado_id=? AND acao='CHAMADO_CONFIRMA' AND para_id=?",
               (resposta, cid, usuario_id))
    gerente = ch['atendido_por_id']
    if resposta == 'SIM':
        if gerente:
            for corpo in detalhe_para_gerencia(db, ch):
                _bot_diz(db, usuario_id, corpo, para=gerente, expira_s=CHAMADO_DIAS * 86400)
        return 'Obrigado! A gerência já recebeu os detalhes da sua dúvida e vai continuar a conversa com você.'
    if gerente:
        _bot_diz(db, usuario_id, 'ℹ️ %s respondeu que a dúvida NÃO é sobre "%s › %s". Converse com a pessoa para entender melhor o que ela precisa.'
                 % (ch['usuario'].title(), ch['modulo'] or ch['tema'], ch['area'] or '—'), para=gerente, expira_s=CHAMADO_DIAS * 86400)
    return 'Entendi! Conte na conversa qual é a sua dúvida, que a gerência vai ajudar você.'


def resolver_chamado(db, cid, gerente_id):
    ch = db.execute('SELECT status FROM ajuda_chamados WHERE id=?', (cid,)).fetchone()
    if ch is None:
        raise ValueError('Este pedido não existe mais.')
    db.execute("UPDATE ajuda_chamados SET status='RESOLVIDO', atendido_por=COALESCE(atendido_por, ?), "
               "atendido_por_id=COALESCE(atendido_por_id, ?), atendido_em=COALESCE(atendido_em, ?) WHERE id=?",
               (_nome_completo(db, gerente_id), gerente_id, agora(), cid))


# ------------------------------------------------------------------ limpeza
def limpar(db, agora_dt=None):
    """Despedidas vencidas, conversas abandonadas, pedidos vencidos e sessões encerradas já sem mensagens."""
    b = bot_id(db)
    if b is None:
        return
    agora_dt = agora_dt or datetime.now()
    db.execute("DELETE FROM chat_mensagens WHERE de_id=? AND expira_em IS NOT NULL AND expira_em<?", (b, agora_dt.strftime(FMT)))
    velhas = db.execute('SELECT usuario_id, registro_id FROM ajuda_sessoes WHERE atualizado_em<?',
                        ((agora_dt - timedelta(hours=abandono_h(db))).strftime(FMT),)).fetchall()
    for r in velhas:
        _registro_fechar(db, r['registro_id'], ABANDONOU, so_se_pendente=True)
        _apagar_conversa(db, r['usuario_id'])
        db.execute('DELETE FROM ajuda_sessoes WHERE usuario_id=?', (r['usuario_id'],))
    db.execute("DELETE FROM ajuda_sessoes WHERE estado=? AND NOT EXISTS (SELECT 1 FROM chat_mensagens m WHERE "
               "(m.de_id=? AND m.para_id=ajuda_sessoes.usuario_id) OR (m.para_id=? AND m.de_id=ajuda_sessoes.usuario_id))",
               (ENCERRADO, b, b))
    db.commit()
