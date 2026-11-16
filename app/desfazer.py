"""Desfazer geral do registro de atividades.

Em todo POST (salvar, excluir, quitar, fechar caixa...) a conexão do banco recebe gatilhos TEMPORÁRIOS que anotam, linha a
linha, como cada registro estava antes e como ficou depois. Ao fim da requisição, a anotação vira o "desfazer" da linha do
registro de atividades (a mesma estrutura que a agenda já usava). O botão "Desfazer" só funciona se as linhas continuam
como a ação as deixou; senão nada é alterado e o sistema explica o motivo.

Ficam de fora: o próprio registro, os acessos, as contas de usuário (guardam senha), as mensagens e a NucleAI.
"""
from __future__ import annotations

import json
import threading

from flask import g, has_request_context, request

# tabelas que nunca entram (o próprio registro, segurança e dados temporários)
EXCLUIDAS = {'auditoria', 'acessos', 'usuarios', 'config', 'sqlite_sequence'}
PREFIXOS_EXCLUIDOS = ('chat_', 'ajuda_', 'nucleai', 'sqlite_', 'anexos', '_')
# ações que não entram: login, mensagens, ajuda, favoritos e a edição de células da agenda (tem desfazer próprio na agenda)
ENDPOINTS_SEM_DESFAZER = ('auth.', 'chat.', 'ajuda.', 'atu.', 'fav.', 'nucleai.', 'nov.', 'agenda.campo', 'pesq.',
                          'lanc.importar', 'bh.importacao', 'admin.backup')   # importações grandes e restauração de backup não entram
MAX_LINHAS = 400            # ação que mexe em mais linhas que isto (importações grandes) não ganha botão de desfazer
MAX_BYTES = 600_000

_cache = {}
_trava = threading.Lock()


def _tabelas(con):
    """[(tabela, [colunas])] que podem ser desfeitas, com cache por banco e versão do esquema."""
    caminho = con.execute('PRAGMA database_list').fetchone()[2]
    versao = con.execute('PRAGMA schema_version').fetchone()[0]
    chave = (caminho, versao)
    achado = _cache.get(chave)
    if achado is not None:
        return achado
    saida = []
    for nome, sql in con.execute("SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name").fetchall():
        if not sql or sql.lstrip().upper().startswith('CREATE VIRTUAL') or nome in EXCLUIDAS or nome.startswith(PREFIXOS_EXCLUIDOS):
            continue
        info = con.execute('PRAGMA table_info("%s")' % nome).fetchall()
        pks = [c for c in info if c[5]]
        if len(pks) != 1 or pks[0][1] != 'id' or (pks[0][2] or '').upper() != 'INTEGER':
            continue
        if any('BLOB' in (c[2] or '').upper() for c in info) or len(info) > 60:
            continue
        saida.append((nome, [c[1] for c in info]))
    with _trava:
        for k in [k for k in _cache if k[0] == caminho]:
            del _cache[k]
        _cache[chave] = saida
    return saida


def tabela_permitida(con, tabela):
    return any(t == tabela for t, _ in _tabelas(con))


def _json_linha(prefixo, colunas):
    return 'json_object(%s)' % ', '.join(
        "'%s', CASE typeof(%s.\"%s\") WHEN 'blob' THEN NULL ELSE %s.\"%s\" END" % (c, prefixo, c, prefixo, c) for c in colunas)


def _gatilhos(tabelas):
    sql = ['CREATE TEMP TABLE IF NOT EXISTS _mud (seq INTEGER PRIMARY KEY AUTOINCREMENT, tabela TEXT, rid INTEGER, antes TEXT, depois TEXT);']
    for t, cols in tabelas:
        novo, velho = _json_linha('NEW', cols), _json_linha('OLD', cols)
        sql.append('CREATE TEMP TRIGGER "_dz_i_%s" AFTER INSERT ON main."%s" BEGIN INSERT INTO _mud (tabela, rid, antes, depois) '
                   "VALUES ('%s', NEW.id, NULL, %s); END;" % (t, t, t, novo))
        sql.append('CREATE TEMP TRIGGER "_dz_u_%s" AFTER UPDATE ON main."%s" BEGIN INSERT INTO _mud (tabela, rid, antes, depois) '
                   "VALUES ('%s', NEW.id, %s, %s); END;" % (t, t, t, velho, novo))
        sql.append('CREATE TEMP TRIGGER "_dz_d_%s" AFTER DELETE ON main."%s" BEGIN INSERT INTO _mud (tabela, rid, antes, depois) '
                   "VALUES ('%s', OLD.id, %s, NULL); END;" % (t, t, t, velho))
    return '\n'.join(sql)


def deve_rastrear():
    if not has_request_context() or request.method != 'POST':
        return False
    return not (request.endpoint or '').startswith(ENDPOINTS_SEM_DESFAZER)


def instalar(con):
    """Liga o rastreio nesta conexão (só vale até ela fechar). Qualquer falha apenas deixa a ação sem botão de desfazer."""
    try:
        con.execute('PRAGMA recursive_triggers=ON')   # INSERT OR REPLACE também anota a linha substituída
        con.executescript(_gatilhos(_tabelas(con)))
        g._desfazer_ligado = True   # (a conexão do sqlite3 não aceita atributos; o aviso vale só para esta requisição)
    except Exception:
        pass


def coletar(con):
    """Estrutura do desfazer das mudanças feitas nesta conexão (ou None se não houve mudança desfazível)."""
    if con is None or not has_request_context() or not g.get('_desfazer_ligado'):
        return None
    try:
        n = con.execute('SELECT COUNT(*) FROM temp._mud').fetchone()[0]
        if not n or n > MAX_LINHAS:   # ação que mexeu em muitas linhas: sem desfazer (e sem carregar tudo na memória)
            return None
        linhas = con.execute('SELECT tabela, rid, antes, depois FROM temp._mud ORDER BY seq').fetchall()
    except Exception:
        return None
    primeira, ultima, ordem = {}, {}, []
    for tabela, rid, antes, depois in linhas:
        k = (tabela, rid)
        if k not in primeira:
            primeira[k] = json.loads(antes) if antes else None
            ordem.append(k)
        ultima[k] = json.loads(depois) if depois else None
    tabelas = {}
    for k in ordem:
        antes, depois = primeira[k], ultima[k]
        if antes == depois:
            continue
        t = tabelas.setdefault(k[0], {'antes': {}, 'depois': {}})
        t['antes'][str(k[1])] = antes
        t['depois'][str(k[1])] = depois
    if not tabelas:
        return None
    payload = {'tabelas': tabelas}
    return payload if len(json.dumps(payload, ensure_ascii=False)) <= MAX_BYTES else None
