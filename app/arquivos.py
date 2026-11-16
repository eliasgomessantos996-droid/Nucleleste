"""Módulo Documentos: contratos e documentos de fiscalização (com vencimento). O arquivo fica no anexos.db (ver anexos.py)."""
from __future__ import annotations

import os
from datetime import date

from . import anexos, util
from .db import agora

TIPOS = {'CONTRATO': 'Documentos e contratos', 'FISCALIZACAO': 'Documentos de fiscalização'}
MAX_BYTES = 20 * 1024 * 1024
EXTENSOES = {'.pdf': 'application/pdf', '.doc': 'application/msword',
             '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
             '.xls': 'application/vnd.ms-excel',
             '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
             '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png'}
COLUNAS = ('id, tipo, nome, vencimento, arquivo_nome, content_type, tamanho, criado_por, criado_em, atualizado_por, atualizado_em, '
           'anexo_id, sha256')


class ErroDocumento(ValueError):
    """Erro de validação mostrado ao usuário."""


def situacao(vencimento, hoje=None):
    """('VENCIDO' | 'PROXIMO' | 'EM DIA' | None, dias restantes) para um documento de fiscalização."""
    if not vencimento:
        return None, None
    dias = (date.fromisoformat(vencimento) - (hoje or date.today())).days
    if dias < 0:
        return 'VENCIDO', dias
    if dias <= 30:
        return 'PROXIMO', dias
    return 'EM DIA', dias


def listar(db, tipo):
    linhas = db.execute('SELECT %s FROM arquivos_docs WHERE tipo=? ORDER BY %s' %
                        (COLUNAS, 'vencimento, nome COLLATE NOCASE' if tipo == 'FISCALIZACAO' else 'nome COLLATE NOCASE'),
                        (tipo,)).fetchall()
    saida = []
    for r in linhas:
        d = dict(r)
        d['situacao'], d['dias'] = situacao(d['vencimento'])
        saida.append(d)
    return saida


def obter(db, aid, com_conteudo=False):
    r = db.execute('SELECT %s FROM arquivos_docs WHERE id=?' % COLUNAS, (aid,)).fetchone()
    if not r:
        raise ErroDocumento('Este documento não existe mais. Atualize a página.')
    doc = dict(r)
    if com_conteudo:
        if doc['anexo_id'] is not None:
            conteudo = anexos.ler(anexos.caminho_de(db), doc['anexo_id'])
            if conteudo is None:
                raise ErroDocumento('O arquivo deste documento não foi encontrado no banco de anexos.')
        else:   # ainda não migrado: o arquivo continua na coluna antiga
            conteudo = bytes(db.execute('SELECT conteudo FROM arquivos_docs WHERE id=?', (aid,)).fetchone()[0])
        doc['conteudo'] = conteudo
    return doc


def _data(txt):
    d = util.para_data(txt)
    return d.isoformat() if d else None


def _validar(db, tipo, nome, vencimento):
    if tipo not in TIPOS:
        raise ErroDocumento('Escolha o tipo do documento.')
    nome = util.maiusculas(nome or '').strip()
    if not nome:
        raise ErroDocumento('Informe o nome do documento.')
    if len(nome) > 120:
        raise ErroDocumento('O nome pode ter no máximo 120 caracteres.')
    venc = None
    if tipo == 'FISCALIZACAO':
        venc = _data(vencimento)
        if not venc:
            raise ErroDocumento('Informe a data de vencimento do documento de fiscalização.')
    return nome, venc


def adicionar(db, tipo, nome, vencimento, arquivo_nome, conteudo, usuario):
    nome, venc = _validar(db, tipo, nome, vencimento)
    ext = os.path.splitext(arquivo_nome or '')[1].lower()
    if ext not in EXTENSOES:
        raise ErroDocumento('Formato não aceito. Envie PDF, Word, Excel ou imagem (JPG/PNG).')
    if not conteudo:
        raise ErroDocumento('Selecione um arquivo.')
    if len(conteudo) > MAX_BYTES:
        raise ErroDocumento('O arquivo deve ter no máximo 20 MB.')
    sha = anexos.sha256(conteudo)
    destino = anexos.caminho_de(db)
    anexo_id = anexos.gravar(destino, 'arquivos_docs', conteudo, sha) if destino else None   # conteúdo primeiro
    try:
        cur = db.execute('INSERT INTO arquivos_docs (tipo, nome, vencimento, arquivo_nome, content_type, tamanho, conteudo, '
                         'anexo_id, sha256, criado_por, criado_em, atualizado_por, atualizado_em) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                         (tipo, nome, venc, os.path.basename(arquivo_nome)[:200], EXTENSOES[ext], len(conteudo),
                          b'' if anexo_id is not None else conteudo, anexo_id, sha, usuario, agora(), usuario, agora()))
        db.commit()
    except Exception:   # sem metadado, o conteúdo não pode sobrar
        db.rollback()
        anexos.apagar(destino, anexo_id)
        raise
    if anexo_id is not None:
        anexos.vincular(destino, anexo_id, cur.lastrowid)
    return cur.lastrowid


def editar(db, aid, nome, vencimento, usuario):
    doc = obter(db, aid)
    nome, venc = _validar(db, doc['tipo'], nome, vencimento)
    db.execute('UPDATE arquivos_docs SET nome=?, vencimento=?, atualizado_por=?, atualizado_em=? WHERE id=?',
               (nome, venc, usuario, agora(), aid))
    db.commit()


def excluir(db, aid):
    doc = obter(db, aid)
    db.execute('DELETE FROM arquivos_docs WHERE id=?', (aid,))
    db.execute('DELETE FROM docs_avisos WHERE documento_id=?', (aid,))
    db.commit()
    anexos.apagar(anexos.caminho_de(db), doc['anexo_id'])   # o metadado já saiu: agora o conteúdo
