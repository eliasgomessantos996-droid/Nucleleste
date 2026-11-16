"""Traz os dados do programa autônomo Banco de Horas (banco.sqlite3) para o banco da Nucleleste.

    python -m app.cli importar-bh C:\\ProgramData\\BancoDeHoras\\dados\\banco.sqlite3

- Funcionários, jornadas, importações (com a planilha original), correções, ajustes, histórico, relatórios emitidos,
  escala, documentos e mensagens entram nas tabelas bh_* mantendo os mesmos números de registro.
- Usuários: Administração -> administrador; Gestão -> módulos de Banco de Horas; Consulta -> só consulta;
  Funcionário -> "Minha área". Quem já existe na Nucleleste (mesmo nome) é mantido como está.
- Só roda se as tabelas bh_* estiverem vazias (não mistura dois conjuntos de dados). Nada é apagado na origem.
"""
from __future__ import annotations

import json
import sqlite3

TABELAS = ['employees', 'schedules', 'imports', 'import_rows', 'corrections', 'adjustments', 'audit_log',
           'report_snapshots', 'roster_days', 'employee_documents', 'message_threads']
PERFIS = {
    'manager': ['bh_consulta', 'bh_gestao', 'bh_dp', 'bh_mensagens'],
    'viewer': ['bh_consulta'],
    'employee': ['bh_portal'],
}


def _colunas(con, tabela):
    return [r[1] for r in con.execute(f'PRAGMA table_info({tabela})')]


def importar(destino: sqlite3.Connection, caminho_origem: str, agora: str) -> dict:
    origem = sqlite3.connect(f'file:///{caminho_origem.replace(chr(92), "/")}?mode=ro', uri=True)
    origem.row_factory = sqlite3.Row
    try:
        return _importar(destino, origem, agora)
    finally:
        origem.close()


def _importar(destino, origem, agora):
    resumo = {'tabelas': {}, 'usuarios_criados': [], 'usuarios_existentes': []}
    existentes = {r[0] for r in origem.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'employees' not in existentes or 'users' not in existentes:
        raise ValueError('O arquivo não é um banco do programa Banco de Horas.')
    if destino.execute('SELECT COUNT(*) FROM bh_employees').fetchone()[0] or destino.execute('SELECT COUNT(*) FROM bh_imports').fetchone()[0]:
        raise ValueError('O Banco de Horas da Nucleleste já tem dados; a importação não mistura dois conjuntos de dados.')

    # ---- usuários (precisam existir antes das mensagens)
    mapa_usuarios = {}
    mapa_funcionario_de_usuario = {}
    for u in origem.execute('SELECT * FROM users ORDER BY id'):
        nome = u['username'].strip().upper()
        atual = destino.execute('SELECT id FROM usuarios WHERE usuario=?', (nome,)).fetchone()
        if atual:
            mapa_usuarios[u['id']] = atual['id']
            resumo['usuarios_existentes'].append(nome)
            continue
        papel = u['role'] if 'role' in u.keys() else 'admin'
        admin = 1 if papel == 'admin' else 0
        modulos = None if admin else json.dumps(PERFIS.get(papel, ['bh_consulta']))
        funcionario = u['employee_id'] if 'employee_id' in u.keys() else None
        trocar = int(u['must_change']) if 'must_change' in u.keys() and u['must_change'] else 0
        cur = destino.execute(
            'INSERT INTO usuarios (usuario,senha_hash,ativo,admin,criado_em,modulos,criado_por,bh_funcionario_id,trocar_senha) '
            'VALUES (?,?,?,?,?,?,?,?,?)',
            (nome, u['password_hash'], int(u['active']) if 'active' in u.keys() else 1, admin, agora, modulos,
             'importação do Banco de Horas', funcionario if papel == 'employee' else None, trocar))
        mapa_usuarios[u['id']] = cur.lastrowid
        resumo['usuarios_criados'].append(nome)

    # ---- tabelas de dados (mesmos nomes de coluna; ids preservados)
    for tabela in TABELAS:
        if tabela not in existentes:
            continue
        cols_o = _colunas(origem, tabela)
        cols_d = set(_colunas(destino, 'bh_' + tabela))
        cols = [c for c in cols_o if c in cols_d]
        marcas = ','.join('?' * len(cols))
        n = 0
        for linha in origem.execute(f'SELECT {",".join(cols)} FROM {tabela}'):
            destino.execute(f'INSERT INTO bh_{tabela} ({",".join(cols)}) VALUES ({marcas})', tuple(linha))
            n += 1
        resumo['tabelas'][tabela] = n

    # ---- mensagens: remapeia o autor para o usuário da Nucleleste
    if 'messages' in existentes:
        n = 0
        for m in origem.execute('SELECT * FROM messages ORDER BY id'):
            autor = mapa_usuarios.get(m['sender_user_id'])
            if autor is None:
                continue
            destino.execute(
                'INSERT INTO bh_messages (id,employee_id,sender_user_id,sender_role,sender_label,sender_name,body,created_at) '
                'VALUES (?,?,?,?,?,?,?,?)',
                (m['id'], m['employee_id'], autor, m['sender_role'], m['sender_label'], m['sender_name'], m['body'], m['created_at']))
            n += 1
        resumo['tabelas']['messages'] = n

    return resumo
