"""Anexos (PDF, Word, Excel, imagens) guardados em um segundo banco SQLite, `anexos.db`, ao lado do `sistema.db`.

O `sistema.db` fica só com os metadados (nome, tipo, tamanho, SHA-256, quem enviou, datas) e a coluna `anexo_id`, que
aponta para a linha daqui. Assim o banco principal e os seus backups não crescem com os arquivos.

O caminho do `anexos.db` é sempre derivado do banco principal em uso (mesma pasta), então vale em qualquer contexto
(sistema, linha de comando e testes). Sem arquivo em disco (banco em memória), as funções devolvem None e quem chama
guarda o conteúdo no próprio banco, como antes.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
from datetime import datetime

NOME_ARQUIVO = 'anexos.db'
ESQUEMA = """
CREATE TABLE IF NOT EXISTS anexos (
    id INTEGER PRIMARY KEY,
    origem TEXT NOT NULL,
    origem_id INTEGER,
    sha256 TEXT NOT NULL,
    tamanho INTEGER NOT NULL,
    conteudo BLOB NOT NULL,
    criado_em TEXT
);
CREATE INDEX IF NOT EXISTS ix_anexos_origem ON anexos(origem, origem_id);
"""


def sha256(conteudo):
    return hashlib.sha256(conteudo).hexdigest()


def caminho_do_banco(conn):
    """Arquivo do banco principal da conexão (None se for em memória)."""
    for _seq, nome, arquivo in conn.execute('PRAGMA database_list'):
        if nome == 'main':
            return arquivo or None
    return None


def caminho_ao_lado(caminho_sistema):
    return os.path.join(os.path.dirname(os.path.abspath(caminho_sistema)), NOME_ARQUIVO)


def caminho_de(conn):
    principal = caminho_do_banco(conn)
    return caminho_ao_lado(principal) if principal else None


def conectar(caminho):
    con = sqlite3.connect(caminho, timeout=30)
    con.execute('PRAGMA journal_mode=WAL')
    con.execute('PRAGMA busy_timeout=30000')
    con.executescript(ESQUEMA)
    return con


def garantir(caminho):
    """Cria o anexos.db (e o esquema) se ainda não existir."""
    conectar(caminho).close()


def gravar(caminho, origem, conteudo, sha=None, origem_id=None):
    """Grava o conteúdo e devolve o id do anexo. O conteúdo é gravado e conferido antes de o metadado existir."""
    sha = sha or sha256(conteudo)
    con = conectar(caminho)
    try:
        with con:
            anexo_id = con.execute('INSERT INTO anexos (origem, origem_id, sha256, tamanho, conteudo, criado_em) VALUES (?,?,?,?,?,?)',
                                   (origem, origem_id, sha, len(conteudo), conteudo, datetime.now().isoformat(timespec='seconds'))).lastrowid
        return anexo_id
    finally:
        con.close()


def vincular(caminho, anexo_id, origem_id):
    """Anota a que registro o anexo pertence (informativo; a ligação oficial é a coluna anexo_id do sistema.db)."""
    try:
        con = conectar(caminho)
        try:
            with con:
                con.execute('UPDATE anexos SET origem_id=? WHERE id=?', (origem_id, anexo_id))
        finally:
            con.close()
    except sqlite3.Error:
        pass


def ler(caminho, anexo_id):
    """Conteúdo do anexo, ou None se não existir."""
    if not caminho or not os.path.exists(caminho):
        return None
    con = conectar(caminho)
    try:
        r = con.execute('SELECT conteudo FROM anexos WHERE id=?', (anexo_id,)).fetchone()
        return None if r is None else bytes(r[0])
    finally:
        con.close()


def apagar(caminho, anexo_id):
    """Remove o conteúdo (usado quando o metadado não pôde ser gravado ou o documento foi excluído)."""
    if not caminho or anexo_id is None or not os.path.exists(caminho):
        return
    try:
        con = conectar(caminho)
        try:
            with con:
                con.execute('DELETE FROM anexos WHERE id=?', (anexo_id,))
        finally:
            con.close()
    except sqlite3.Error:
        pass
