"""Migrações únicas de dados. Cada uma tem um relatório (sem gravar nada) e só é aplicada com confirmação explícita.

Uso (sempre a partir da pasta do projeto, com o banco de teste ou com o banco real depois de conferir o relatório):
    python -m app.migracoes relatorio <caminho\\sistema.db>
    python -m app.migracoes aplicar <caminho\\sistema.db> --confirmo

Antes de aplicar, é feita uma cópia completa do banco (API de backup do SQLite) na mesma pasta do banco.
Cada migração é gravada na tabela migracoes_aplicadas, então não roda duas vezes.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import datetime

from . import util
from .db import agora, conectar

TELEFONES = 'telefones_padrao_v1'
SEXO = 'sexo_clientes_v1'
TABELA_CONTROLE = """CREATE TABLE IF NOT EXISTS migracoes_aplicadas (
    nome TEXT PRIMARY KEY,
    aplicada_em TEXT NOT NULL,
    detalhe TEXT
)"""


class ErroMigracao(ValueError):
    """Erro que impede a migração (mostrado ao operador)."""


def _ja_aplicada(db, nome):
    """Só consulta (não cria nada): o relatório nunca grava no banco."""
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='migracoes_aplicadas'").fetchone():
        return False
    return db.execute('SELECT 1 FROM migracoes_aplicadas WHERE nome=?', (nome,)).fetchone() is not None


def _telefones_a_mudar(db):
    """(tabela, id, antes, depois) de cada telefone que pode ser padronizado. Números sem DDD ficam como estão."""
    saida = []
    for tabela in ('agenda_horarios', 'agenda_espera', 'clientes'):
        for r in db.execute('SELECT id, contato FROM %s WHERE TRIM(COALESCE(contato,\'\'))<>\'\'' % tabela):
            antes = r['contato']
            if not util.telefone_valido(antes):
                continue
            depois = util.telefone_padrao(antes)
            if depois != antes:
                saida.append((tabela, r['id'], antes, depois))
    return saida


def _sexo_a_preencher(db):
    """(cliente_id, nome, sexo) para clientes sem sexo que têm exame realizado com o sexo anotado."""
    linhas = db.execute("""SELECT c.id, c.nome,
            (SELECT r.sexo FROM realizacoes r WHERE r.cliente_id=c.id AND r.sexo IN ('M','F')
               ORDER BY r.data DESC, r.id DESC LIMIT 1) AS sexo
        FROM clientes c WHERE TRIM(COALESCE(c.sexo,''))='' """).fetchall()
    return [(r['id'], r['nome'], r['sexo']) for r in linhas if r['sexo']]


def relatorio(db):
    """O que mudaria, sem gravar. Devolve um dicionário com a contagem e alguns exemplos."""
    tel = _telefones_a_mudar(db)
    sexo = _sexo_a_preencher(db)
    por_tabela = {}
    for tabela, *_r in tel:
        por_tabela[tabela] = por_tabela.get(tabela, 0) + 1
    return {
        TELEFONES: {'ja_aplicada': _ja_aplicada(db, TELEFONES), 'total': len(tel), 'por_tabela': por_tabela,
                    'exemplos': tel[:8]},
        SEXO: {'ja_aplicada': _ja_aplicada(db, SEXO), 'total': len(sexo), 'exemplos': sexo[:8]},
    }


def aplicar(db, nome):
    """Grava a migração. Tudo ou nada: se algo falhar, nada é gravado."""
    if nome not in (TELEFONES, SEXO):
        raise ErroMigracao('Migração desconhecida: %s' % nome)
    if _ja_aplicada(db, nome):
        raise ErroMigracao('A migração %s já foi aplicada neste banco. Não rode de novo.' % nome)
    detalhe = {}
    try:
        db.execute(TABELA_CONTROLE)
        if nome == TELEFONES:
            mudancas = _telefones_a_mudar(db)
            for tabela, rid, _antes, depois in mudancas:
                db.execute('UPDATE %s SET contato=? WHERE id=?' % tabela, (depois, rid))
            por_tabela = {}
            for tabela, *_r in mudancas:
                por_tabela[tabela] = por_tabela.get(tabela, 0) + 1
            detalhe = por_tabela
        else:
            sexo = _sexo_a_preencher(db)
            for cid, _nome, valor in sexo:
                db.execute("UPDATE clientes SET sexo=? WHERE id=? AND TRIM(COALESCE(sexo,''))=''", (valor, cid))
            detalhe = {'clientes': len(sexo)}
        db.execute('INSERT INTO migracoes_aplicadas (nome, aplicada_em, detalhe) VALUES (?,?,?)',
                   (nome, agora(), repr(detalhe)))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return detalhe


ZERAR_MOVIMENTO = 'zerar_movimento_caixa_v1'


def zerar_movimento_antigo(con, caminho):
    """Pedido da gerência na versão 1.4.4: o movimento de caixa antigo (caixas abertos/fechados e recebimentos já feitos)
    é apagado uma única vez, para começar do zero. Os lançamentos ainda A RECEBER não são tocados.
    Se houver algo a apagar, antes é feita a cópia completa do banco. Devolve o que foi apagado (ou None se já foi feito)."""
    con.execute(TABELA_CONTROLE)
    if _ja_aplicada(con, ZERAR_MOVIMENTO):
        return None
    sessoes = con.execute('SELECT COUNT(*) FROM caixa_sessoes').fetchone()[0]
    recebidos = con.execute("SELECT COUNT(*) FROM caixa WHERE status='PAGO'").fetchone()[0]
    copia = None
    if sessoes or recebidos:
        con.commit()
        copia = copia_do_banco(caminho, 'ANTES_ZERAR_CAIXA')
        con.execute("DELETE FROM caixa WHERE status='PAGO'")
        con.execute('DELETE FROM caixa_sessoes')
    detalhe = {'sessoes': sessoes, 'recebimentos': recebidos, 'copia': copia}
    con.execute('INSERT INTO migracoes_aplicadas (nome, aplicada_em, detalhe) VALUES (?,?,?)',
                (ZERAR_MOVIMENTO, agora(), repr(detalhe)))
    con.commit()
    return detalhe


ANEXOS_EXTERNOS = 'anexos_externos_v1'


def _anexos_pendentes(con):
    """(tabela, coluna do conteúdo, coluna do tamanho, ids) dos arquivos que ainda estão dentro do sistema.db."""
    saida = []
    for tabela, coluna, tam in (('arquivos_docs', 'conteudo', 'tamanho'), ('bh_employee_documents', 'content', 'size_bytes')):
        ids = [r[0] for r in con.execute('SELECT id FROM %s WHERE anexo_id IS NULL AND length(%s)>0 ORDER BY id' % (tabela, coluna))]
        if ids:
            saida.append((tabela, coluna, tam, ids))
    return saida


def migrar_anexos(con, caminho):
    """Leva os arquivos guardados nas colunas BLOB do sistema.db para o anexos.db (uma cópia confere, só então a coluna antiga é esvaziada).

    Idempotente: sem nada pendente não faz nada; roda de novo só se aparecerem arquivos antigos (ex.: restauração de um
    backup anterior). Se uma cópia falhar, aquele arquivo continua no sistema.db e é tentado de novo na próxima inicialização.
    Antes de mexer, guarda uma cópia do banco. Depois de migrar, faz VACUUM para o sistema.db encolher.
    Devolve {'migrados', 'falhas', 'copia'} ou None se não havia nada a fazer."""
    from . import anexos
    con.execute(TABELA_CONTROLE)
    pendentes = _anexos_pendentes(con)
    if not pendentes:
        return None
    con.commit()
    destino = anexos.caminho_ao_lado(caminho)
    anexos.garantir(destino)
    copia = copia_do_banco(caminho, 'ANTES_ANEXOS')
    migrados, falhas = 0, []
    for tabela, coluna, tam, ids in pendentes:
        for rid in ids:
            try:
                linha = con.execute('SELECT %s AS blob, %s AS tamanho FROM %s WHERE id=?' % (coluna, tam, tabela), (rid,)).fetchone()
                blob = bytes(linha['blob'] if hasattr(linha, 'keys') else linha[0])
                sha = anexos.sha256(blob)
                if tabela == 'bh_employee_documents':
                    guardado = con.execute('SELECT sha256 FROM bh_employee_documents WHERE id=?', (rid,)).fetchone()[0]
                    if guardado and guardado != sha:
                        raise ValueError('SHA-256 diferente do registrado')
                anexo_id = anexos.gravar(destino, tabela, blob, sha, rid)
                lido = anexos.ler(destino, anexo_id)
                if lido is None or len(lido) != len(blob) or anexos.sha256(lido) != sha:
                    anexos.apagar(destino, anexo_id)
                    raise ValueError('conferência da cópia falhou')
                if tabela == 'arquivos_docs':
                    con.execute("UPDATE arquivos_docs SET anexo_id=?, sha256=?, conteudo=x'' WHERE id=?", (anexo_id, sha, rid))
                else:
                    con.execute("UPDATE bh_employee_documents SET anexo_id=?, content=x'' WHERE id=?", (anexo_id, rid))
                con.commit()
                migrados += 1
            except Exception as e:   # este arquivo fica onde está
                con.rollback()
                falhas.append('%s %s: %s' % (tabela, rid, e))
    detalhe = {'migrados': migrados, 'falhas': falhas, 'copia': copia}
    con.execute('INSERT OR REPLACE INTO migracoes_aplicadas (nome, aplicada_em, detalhe) VALUES (?,?,?)',
                (ANEXOS_EXTERNOS, agora(), repr(detalhe)))
    con.commit()
    if migrados:
        con.execute('VACUUM')
    return detalhe


def copia_do_banco(caminho, prefixo='ANTES_MIGRACAO'):
    """Cópia completa do banco antes de gravar (API de backup do SQLite), na mesma pasta."""
    pasta = os.path.dirname(os.path.abspath(caminho))
    destino = os.path.join(pasta, 'backups', '%s_%s.db' % (prefixo, datetime.now().strftime('%Y-%m-%d_%H-%M-%S')))
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    origem = sqlite3.connect(caminho)
    copia = sqlite3.connect(destino)
    try:
        origem.backup(copia)
    finally:
        copia.close()
        origem.close()
    return destino


def _imprimir_relatorio(rel):
    for nome, dados in rel.items():
        print('\n== %s' % nome)
        print('   já aplicada: %s' % ('sim (não roda de novo)' if dados['ja_aplicada'] else 'não'))
        print('   registros que mudariam: %d' % dados['total'])
        if dados.get('por_tabela'):
            print('   por tabela: %s' % dados['por_tabela'])
        for ex in dados.get('exemplos', []):
            print('   exemplo: %s' % (ex,))


def main(argv=None):
    p = argparse.ArgumentParser(description='Migrações únicas de dados do Nucleleste.')
    sub = p.add_subparsers(dest='comando', required=True)
    r = sub.add_parser('relatorio', help='mostra o que mudaria, sem gravar nada')
    r.add_argument('banco')
    a = sub.add_parser('aplicar', help='aplica as migrações pendentes (exige --confirmo)')
    a.add_argument('banco')
    a.add_argument('--confirmo', action='store_true', help='confirma a gravação depois de conferir o relatório')
    args = p.parse_args(argv)
    if not os.path.exists(args.banco):
        print('Banco não encontrado: %s' % args.banco)
        return 1
    if args.comando == 'relatorio':
        con = conectar(args.banco)
        try:
            _imprimir_relatorio(relatorio(con))
        finally:
            con.close()
        print('\nNada foi gravado. Para aplicar, rode "aplicar" com --confirmo.')
        return 0
    if not args.confirmo:
        print('Nada foi gravado. Confira o relatório e rode de novo com --confirmo.')
        return 2
    print('Cópia de segurança: %s' % copia_do_banco(args.banco))
    con = conectar(args.banco)
    try:
        for nome in (TELEFONES, SEXO):
            if _ja_aplicada(con, nome):
                print('%s: já aplicada, pulando.' % nome)
                continue
            print('%s: aplicada, detalhe %s' % (nome, aplicar(con, nome)))
    except ErroMigracao as e:
        print('Não aplicado: %s' % e)
        return 1
    finally:
        con.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
