"""Suporte ao desenvolvedor: os usuários enviam formulários de SUGESTÃO ou de CORREÇÃO DE BUG; o perfil DESENVOLVEDOR (e o administrador)
vê tudo, aceita ou recusa cada um e guarda os aceitos na "pasta" para a próxima atualização, com o texto editável e um relatório em PDF.

Ciclo de cada formulário (`suporte_itens.status`): NOVA → ACEITA (vai para a pasta) ou RECUSADA → APLICADA (já entrou numa atualização).
As correções de bugs aparecem sempre acima das sugestões."""
from __future__ import annotations

import json

from werkzeug.security import generate_password_hash

from .db import agora

USUARIO_DEV = 'DESENVOLVEDOR'
NOME_ANTIGO = 'SUPORTE DO DESENVOLVEDOR'   # nome que o perfil teve antes; é renomeado sozinho
SENHA_PADRAO = '123'                       # provisória: o perfil nasce pedindo a troca no primeiro acesso
CHAVE_CONFIG = 'suporte_usuario_id'
MODULO_DEV = 'suporte_dev'

SUGESTAO, BUG = 'SUGESTAO', 'BUG'
NOVA, ACEITA, RECUSADA, APLICADA = 'NOVA', 'ACEITA', 'RECUSADA', 'APLICADA'
GRAVIDADES = (('IMPEDE', 'Não consigo trabalhar'), ('ATRAPALHA', 'Atrapalha o trabalho'), ('PEQUENO', 'Pequeno incômodo'))
ROTULO_GRAVIDADE = dict(GRAVIDADES)
ORDEM_GRAVIDADE = {'IMPEDE': 0, 'ATRAPALHA': 1, 'PEQUENO': 2}
ROTULO_STATUS = {NOVA: 'Enviado', ACEITA: 'Aceito', RECUSADA: 'Não aceito', APLICADA: 'Já está no sistema'}
LIMITES = {'titulo': 120, 'descricao': 2000, 'tela': 80, 'passos': 1000, 'texto_atualizacao': 2000, 'versao': 20}
MAX_POR_HORA = 10
TEMAS = ('Segurança', 'Organização', 'Desempenho', 'Facilidade de uso', 'Relatórios e documentos', 'Financeiro e faturamento', 'Agenda e atendimento',
         'Laudos e exames', 'Outro')
TEMA_PADRAO = 'Outro'


class ErroSuporte(ValueError):
    """Erro de validação mostrado ao usuário."""


# ------------------------------------------------------------------ perfil
def garantir(con):
    """Cria o perfil DESENVOLVEDOR uma única vez e guarda o id em `config` (então ele pode ser renomeado depois). Quem já tinha o perfil com o
    nome antigo ("SUPORTE DO DESENVOLVEDOR") passa a se chamar DESENVOLVEDOR, sem mexer na senha. É o topo da hierarquia: Desenvolvedor > Gestão > Outros."""
    atual = con.execute('SELECT valor FROM config WHERE chave=?', (CHAVE_CONFIG,)).fetchone()
    uid = None
    if atual and con.execute('SELECT 1 FROM usuarios WHERE id=?', (atual[0],)).fetchone():
        uid = int(atual[0])
    if uid is None:
        for nome in (USUARIO_DEV, NOME_ANTIGO):
            achado = con.execute('SELECT id FROM usuarios WHERE UPPER(usuario)=?', (nome,)).fetchone()
            if achado:
                uid = achado[0]
                break
    if uid is None:
        uid = con.execute('INSERT INTO usuarios (usuario, senha_hash, admin, ativo, modulos, trocar_senha, criado_em) VALUES (?,?,0,1,?,1,?)',
                          (USUARIO_DEV, generate_password_hash(SENHA_PADRAO), json.dumps([MODULO_DEV]), agora())).lastrowid
    con.execute('INSERT INTO config (chave, valor) VALUES (?,?) ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor', (CHAVE_CONFIG, str(uid)))
    u = con.execute('SELECT usuario, modulos FROM usuarios WHERE id=?', (uid,)).fetchone()
    if (u[0] or '').upper() == NOME_ANTIGO and not con.execute('SELECT 1 FROM usuarios WHERE UPPER(usuario)=? AND id<>?', (USUARIO_DEV, uid)).fetchone():
        con.execute('UPDATE usuarios SET usuario=? WHERE id=?', (USUARIO_DEV, uid))
    try:
        modulos = json.loads(u[1]) if u[1] else []
    except ValueError:
        modulos = []
    con.execute('UPDATE usuarios SET admin=1 WHERE id=?', (uid,))   # o desenvolvedor está acima da gestão (ver hierarquia.py)
    if not modulos:   # perfil criado antes do módulo existir: libera só o módulo do suporte
        con.execute('UPDATE usuarios SET modulos=? WHERE id=?', (json.dumps([MODULO_DEV]), uid))


def usuario_dev_id(db):
    r = db.execute('SELECT u.id FROM config c JOIN usuarios u ON u.id=CAST(c.valor AS INTEGER) WHERE c.chave=? AND u.ativo=1', (CHAVE_CONFIG,)).fetchone()
    return r['id'] if r else None


# ------------------------------------------------------------------ envio
def _texto(valor, campo, obrigatorio=False, minimo=0):
    t = str(valor or '').replace('\r\n', '\n').replace('\r', '\n').strip()
    if obrigatorio and not t:
        raise ErroSuporte('Preencha o campo “%s”.' % campo)
    if minimo and len(t) < minimo:
        raise ErroSuporte('Escreva um pouco mais no campo “%s” (pelo menos %d letras).' % (campo, minimo))
    return t


def enviar(db, usuario_id, usuario, tipo, titulo, descricao, tela='', passos='', gravidade='', tema='', meta=None):
    """Grava um formulário de sugestão ou de correção de bug. `meta`: dados do envio (dicionário). Devolve o id."""
    if tipo not in (SUGESTAO, BUG):
        raise ErroSuporte('Tipo de formulário inválido.')
    titulo = _texto(titulo, 'Título', True, 3)
    descricao = _texto(descricao, 'O que aconteceu' if tipo == BUG else 'Descreva a sua sugestão', True, 10)
    tela, passos = _texto(tela, 'Tela'), _texto(passos, 'Como acontece')
    for campo, valor in (('titulo', titulo), ('descricao', descricao), ('tela', tela), ('passos', passos)):
        if len(valor) > LIMITES[campo]:
            raise ErroSuporte('O campo “%s” aceita no máximo %d letras.' % (campo, LIMITES[campo]))
    if tipo == BUG:
        gravidade = gravidade if gravidade in ROTULO_GRAVIDADE else 'ATRAPALHA'
    else:
        gravidade, passos = None, ''
    recentes = db.execute("SELECT COUNT(*) FROM suporte_itens WHERE usuario_id=? AND criado_em>=datetime('now','localtime','-1 hour')", (usuario_id,)).fetchone()[0]
    if recentes >= MAX_POR_HORA:
        raise ErroSuporte('Muitos envios em pouco tempo. Aguarde um pouco e envie de novo.')
    tema = tema if tema in TEMAS else TEMA_PADRAO
    cur = db.execute('INSERT INTO suporte_itens (tipo, titulo, descricao, tela, passos, gravidade, usuario_id, usuario, criado_em, status, tema, meta) '
                     'VALUES (?,?,?,?,?,?,?,?,?,?,?,?)', (tipo, titulo, descricao, tela or None, passos or None, gravidade, usuario_id, usuario, agora(), NOVA,
                                                         tema, json.dumps(meta, ensure_ascii=False) if meta else None))
    db.commit()
    return cur.lastrowid


def _ordenar(itens):
    """Correções de bugs acima das sugestões; entre os bugs, os mais graves primeiro; depois os mais antigos primeiro."""
    return sorted(itens, key=lambda i: (0 if i['tipo'] == BUG else 1, ORDEM_GRAVIDADE.get(i['gravidade'], 3) if i['tipo'] == BUG else 0, i['criado_em'], i['id']))


def _dict(r):
    d = dict(r)
    d['status_rotulo'] = ROTULO_STATUS.get(d['status'], d['status'])
    d['gravidade_rotulo'] = ROTULO_GRAVIDADE.get(d.get('gravidade') or '', '')
    d['tema'] = d.get('tema') or TEMA_PADRAO
    try:
        d['meta_obj'] = json.loads(d['meta']) if d.get('meta') else {}
    except ValueError:
        d['meta_obj'] = {}
    return d


def do_usuario(db, usuario_id, tipo):
    """Os envios de uma pessoa (de um tipo), do mais novo para o mais antigo."""
    return [_dict(r) for r in db.execute('SELECT * FROM suporte_itens WHERE usuario_id=? AND tipo=? ORDER BY id DESC LIMIT 100', (usuario_id, tipo))]


def recebidos(db, status=NOVA):
    """Formulários numa situação (NOVA por padrão), com os bugs primeiro."""
    return _ordenar(_dict(r) for r in db.execute('SELECT * FROM suporte_itens WHERE status=?', (status,)))


def contar_novos(db):
    return db.execute("SELECT COUNT(*) FROM suporte_itens WHERE status='NOVA'").fetchone()[0]


def resumo(db):
    """Contagem por situação e tipo, para os cabeçalhos das telas do desenvolvedor."""
    saida = {s: {SUGESTAO: 0, BUG: 0} for s in (NOVA, ACEITA, RECUSADA, APLICADA)}
    for r in db.execute('SELECT status, tipo, COUNT(*) AS n FROM suporte_itens GROUP BY status, tipo'):
        if r['status'] in saida and r['tipo'] in saida[r['status']]:
            saida[r['status']][r['tipo']] = r['n']
    return saida


# ------------------------------------------------------------------ decisões (desenvolvedor)
def _item(db, iid):
    r = db.execute('SELECT * FROM suporte_itens WHERE id=?', (iid,)).fetchone()
    if not r:
        raise ErroSuporte('Este formulário não existe mais. Atualize a página.')
    return r


def decidir(db, iid, aceitar, usuario):
    """Aceita (vai para a pasta) ou recusa. Dá para mudar de ideia: um recusado ainda pode ser aceito e vice-versa. Já aplicados não mudam."""
    r = _item(db, iid)
    if r['status'] == APLICADA:
        raise ErroSuporte('Este item já entrou numa atualização. Para mexer nele, desfaça a aplicação na pasta.')
    novo = ACEITA if aceitar else RECUSADA
    db.execute('UPDATE suporte_itens SET status=?, decidido_por=?, decidido_em=? WHERE id=?', (novo, usuario, agora(), iid))
    db.commit()
    return novo


def voltar_para_analise(db, iid):
    r = _item(db, iid)
    if r['status'] not in (ACEITA, RECUSADA):
        raise ErroSuporte('Só itens aceitos ou recusados voltam para análise.')
    db.execute("UPDATE suporte_itens SET status='NOVA', decidido_por=NULL, decidido_em=NULL WHERE id=?", (iid,))
    db.commit()


def salvar_texto(db, iid, texto):
    """Texto para a atualização (mais didático que o original). Vazio volta a usar o texto do usuário."""
    r = _item(db, iid)
    if r['status'] not in (ACEITA, APLICADA):
        raise ErroSuporte('Só itens aceitos têm texto de atualização.')
    texto = str(texto or '').replace('\r\n', '\n').replace('\r', '\n').strip()
    if len(texto) > LIMITES['texto_atualizacao']:
        raise ErroSuporte('O texto da atualização aceita no máximo %d letras.' % LIMITES['texto_atualizacao'])
    if texto == (r['descricao'] or '').strip():   # igual ao original: não guarda cópia
        texto = ''
    db.execute('UPDATE suporte_itens SET texto_atualizacao=? WHERE id=?', (texto or None, iid))
    db.commit()


def marcar_aplicada(db, iid, versao):
    r = _item(db, iid)
    if r['status'] != ACEITA:
        raise ErroSuporte('Só itens aceitos podem ser marcados como aplicados.')
    versao = str(versao or '').strip()[:LIMITES['versao']]
    db.execute("UPDATE suporte_itens SET status='APLICADA', versao=?, aplicada_em=? WHERE id=?", (versao or None, agora(), iid))
    db.commit()


def desfazer_aplicacao(db, iid):
    r = _item(db, iid)
    if r['status'] != APLICADA:
        raise ErroSuporte('Este item não está marcado como aplicado.')
    db.execute("UPDATE suporte_itens SET status='ACEITA', versao=NULL, aplicada_em=NULL WHERE id=?", (iid,))
    db.commit()


def aplicar_todas(db, versao):
    """Depois de lançar a atualização: marca todos os aceitos pendentes como aplicados na versão informada. Devolve quantos."""
    versao = str(versao or '').strip()[:LIMITES['versao']]
    cur = db.execute("UPDATE suporte_itens SET status='APLICADA', versao=?, aplicada_em=? WHERE status='ACEITA'", (versao or None, agora()))
    db.commit()
    return cur.rowcount


# ------------------------------------------------------------------ pasta
def pasta(db):
    """A pasta do desenvolvedor: {'pendentes': aceitos que ainda faltam entrar (bugs primeiro), 'aplicados': os que já entraram (recentes primeiro)}."""
    pend = _ordenar(_dict(r) for r in db.execute("SELECT * FROM suporte_itens WHERE status='ACEITA'"))
    apl = [_dict(r) for r in db.execute("SELECT * FROM suporte_itens WHERE status='APLICADA' ORDER BY aplicada_em DESC, id DESC LIMIT 200")]
    return {'pendentes': pend, 'aplicados': apl}


def texto_final(item):
    """O texto que vai para o relatório: o da atualização (se o desenvolvedor reescreveu) ou o do próprio usuário."""
    return (item.get('texto_atualizacao') or item.get('descricao') or '').strip()


# ------------------------------------------------------------------ dados do envio
def _navegador(ua):
    for marca, nome in (('Edg/', 'Edge'), ('OPR/', 'Opera'), ('Firefox/', 'Firefox'), ('Chrome/', 'Chrome'), ('Safari/', 'Safari')):
        if marca in ua:
            versao = ua.split(marca, 1)[1].split(' ')[0].split('.')[0]
            return '%s %s' % (nome, versao)
    return 'Desconhecido'


def _sistema(ua):
    for marca, nome in (('Windows NT 10', 'Windows 10/11'), ('Windows NT 6.3', 'Windows 8.1'), ('Windows NT 6.1', 'Windows 7'), ('Android', 'Android'),
                        ('iPhone', 'iOS (iPhone)'), ('iPad', 'iPadOS'), ('Mac OS X', 'macOS'), ('Linux', 'Linux')):
        if marca in ua:
            return nome
    return 'Desconhecido'


def montar_meta(db, usuario, cabecalhos, ip, ip_encaminhado, cliente, modulos_usuario, versao_sistema):
    """Todos os dados possíveis do envio, para o desenvolvedor conferir com os erros que o sistema registra: quem, quando, de que aparelho,
    em que navegador, de que endereço, a página de onde veio e o que a pessoa fez nos minutos antes (registro de atividades)."""
    ua = cabecalhos.get('User-Agent', '')[:300]
    tipo = 'Celular' if ('Mobi' in ua or 'iPhone' in ua) else ('Tablet' if ('iPad' in ua or 'Tablet' in ua) else 'Computador')
    cliente = cliente or {}
    limpo = {k: str(cliente.get(k, ''))[:120] for k in ('tela', 'janela', 'pixel', 'fuso', 'plataforma', 'toque', 'nucleos', 'memoria', 'online', 'hora_local',
                                                         'pagina', 'tema', 'conexao')}
    ultimas = [dict(r) for r in db.execute('SELECT data_hora, modulo, acao, rota FROM auditoria WHERE usuario=? ORDER BY id DESC LIMIT 8', (usuario,))]
    erros = [dict(r) for r in db.execute("SELECT data_hora, rota, detalhe FROM auditoria WHERE usuario=? AND acao='Erro interno' ORDER BY id DESC LIMIT 3", (usuario,))]
    acesso = db.execute("SELECT data_hora, computador, detalhe FROM acessos WHERE usuario=? AND evento LIKE 'Entrou%' ORDER BY id DESC LIMIT 1", (usuario,)).fetchone()
    return {'enviado_em': agora(), 'usuario': usuario, 'ip': ip or '', 'ip_encaminhado': ip_encaminhado or '', 'navegador': _navegador(ua), 'sistema': _sistema(ua),
            'dispositivo': tipo, 'user_agent': ua, 'idioma': cabecalhos.get('Accept-Language', '')[:60], 'referencia': cabecalhos.get('Referer', '')[:200],
            'cliente': limpo, 'versao_sistema': versao_sistema, 'modulos': list(modulos_usuario or [])[:40],
            'ultima_entrada': dict(acesso) if acesso else None, 'ultimas_acoes': ultimas, 'erros_recentes': erros}


# ------------------------------------------------------------------ recusa: cartão na conversa de mensagens
def cartao_recusa(item, dev_nome):
    """Dados do cartão especial (cápsulas) que vai para a conversa do usuário. Só o servidor cria cartões: ninguém consegue escrever um igual."""
    return {'tipo': 'SUPORTE_RECUSA', 'item_id': item['id'], 'item_tipo': 'Correção de bug' if item['tipo'] == BUG else 'Sugestão',
            'titulo': item['titulo'], 'autor': item['usuario'] or '', 'enviado_em': item['criado_em'], 'tema': item.get('tema') or TEMA_PADRAO,
            'citacao': (item['descricao'] or '')[:600], 'tela': item.get('tela') or '', 'decidido_por': dev_nome, 'decidido_em': agora()}


def por_tema(itens):
    """Agrupa por tema, na ordem de TEMAS; dentro de cada tema, bugs primeiro (já vêm ordenados). [(tema, [itens])]"""
    grupos = {}
    for i in itens:
        grupos.setdefault(i.get('tema') or TEMA_PADRAO, []).append(i)
    return [(t, grupos[t]) for t in TEMAS if t in grupos] + [(t, v) for t, v in grupos.items() if t not in TEMAS]
