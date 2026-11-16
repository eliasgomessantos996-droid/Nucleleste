"""Comandos de manutenção usados pelo instalador e pela bandeja.

    python -m app.cli backup                    backup .zip (sistema + anexos) na pasta backups
    python -m app.cli admin-senha ARQUIVO       define a senha do usuário ADMIN lendo-a de um arquivo (que é apagado)
    python -m app.cli importar-db ARQUIVO       copia um banco .db existente para a pasta de dados (se ainda não houver dados)
    python -m app.cli config PORTA              grava a porta no config.json da pasta de dados
    python -m app.cli importar-exames ARQUIVO   traz os exames da planilha EXAMES.xlsx (controle de realização)
    python -m app.cli importar-bh ARQUIVO       traz os dados do programa autônomo Banco de Horas (banco.sqlite3)

A pasta de dados vem da variável NUCLELESTE_DADOS (definida pelo instalador/bandeja).
"""
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime

from werkzeug.security import generate_password_hash

from . import carregar_config, db as dbmod


def _caminho_banco():
    return os.path.join(carregar_config()['pasta_dados'], 'sistema.db')


def backup(prefixo='BACKUP'):
    """Backup em .zip com os dois bancos (sistema.db + anexos.db) e o LEIA-ME.txt, na pasta backups."""
    from . import backup_pacote, versao
    if not os.path.exists(_caminho_banco()):
        print('Sem banco para copiar.')
        return None
    destino = backup_pacote.criar_zip(_caminho_banco(), prefixo, versao())
    # apaga backups com mais de 7 dias, mantendo os 3 mais recentes (.zip novos e .db antigos)
    if prefixo == 'BACKUP':
        backup_pacote.reter_backups(_caminho_banco())
    backup_pacote.sincronizar_externa(_caminho_banco(), os.environ.get('USERNAME', ''))   # cópia para o Drive/rede, se houver pasta escolhida
    print('Backup:', destino)
    return destino


def admin_senha(arquivo):
    with open(arquivo, encoding='utf-8-sig') as fh:
        senha = fh.read().strip()
    try:
        os.remove(arquivo)  # a senha não pode ficar em disco
    except OSError:
        pass
    if len(senha) < 3:
        print('Senha muito curta.'); return 1
    dbmod.inicializar(_caminho_banco())
    con = dbmod.conectar(_caminho_banco())
    existe = con.execute("SELECT id FROM usuarios WHERE usuario='ADMIN'").fetchone()
    h = generate_password_hash(senha)
    if existe:
        con.execute('UPDATE usuarios SET senha_hash=?, admin=1, ativo=1 WHERE id=?', (h, existe['id']))
    else:
        con.execute('INSERT INTO usuarios (usuario, senha_hash, admin, criado_em) VALUES (?,?,1,?)', ('ADMIN', h, dbmod.agora()))
    con.commit(); con.close()
    print('Usuário ADMIN configurado.')
    return 0


def importar_db(arquivo):
    destino = _caminho_banco()
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    if os.path.exists(destino):
        con = sqlite3.connect(destino)
        try:
            n = con.execute('SELECT COUNT(*) FROM clientes').fetchone()[0]
        except sqlite3.Error:
            n = 0
        con.close()
        if n:
            print('Já existem dados na instalação; o banco informado não foi copiado.')
            return 2
        backup('ANTES_DA_IMPORTACAO')
    a, b = sqlite3.connect(arquivo), sqlite3.connect(destino)
    with b:
        a.backup(b)
    a.close(); b.close()
    dbmod.inicializar(destino)  # aplica migrações de esquema, se o banco for de versão anterior
    print('Banco importado.')
    return 0


def importar_bh(arquivo):
    from .bh import migracao
    if not os.path.exists(arquivo):
        print('Arquivo não encontrado:', arquivo); return 1
    dbmod.inicializar(_caminho_banco())
    backup('ANTES_DO_BANCO_DE_HORAS')
    con = dbmod.conectar(_caminho_banco())
    try:
        with con:
            resumo = migracao.importar(con, os.path.abspath(arquivo), dbmod.agora())
    except ValueError as erro:
        print('Não importado:', erro); con.close(); return 2
    con.close()
    for tabela, n in resumo['tabelas'].items():
        print('  %-20s %d' % (tabela, n))
    print('Usuários criados:', ', '.join(resumo['usuarios_criados']) or 'nenhum')
    print('Usuários que já existiam (mantidos):', ', '.join(resumo['usuarios_existentes']) or 'nenhum')
    return 0


def importar_exames(arquivo):
    from . import exames_import
    if not os.path.exists(arquivo):
        print('Arquivo não encontrado:', arquivo); return 1
    dbmod.inicializar(_caminho_banco())
    backup('ANTES_DOS_EXAMES')
    con = dbmod.conectar(_caminho_banco())
    try:
        resumo = exames_import.importar_xlsx(con, arquivo, 'importação')
    except ValueError as erro:
        print('Não importado:', erro); con.close(); return 2
    con.close()
    print('Abas lidas: %(abas)d | lançamentos: %(linhas)d | ligados a clientes: %(com_cliente)d | a médicos: %(com_medico)d | '
          'datas corrigidas: %(datas_corrigidas)d' % resumo)
    return 0


def gravar_config(porta):
    pasta = carregar_config()['pasta_dados']
    os.makedirs(pasta, exist_ok=True)
    caminho = os.path.join(pasta, 'config.json')
    cfg = {}
    if os.path.exists(caminho):
        try:
            cfg = json.load(open(caminho, encoding='utf-8-sig'))
        except ValueError:
            cfg = {}
    cfg['porta'] = int(porta)
    with open(caminho, 'w', encoding='utf-8') as fh:
        json.dump(cfg, fh)
    print('Porta:', porta)
    return 0


def main(argv):
    # --dados PASTA define a pasta de dados (o instalador usa isto em vez de variável de ambiente)
    if len(argv) >= 2 and argv[0] == '--dados':
        os.environ['NUCLELESTE_DADOS'] = argv[1]
        argv = argv[2:]
    if not argv:
        print(__doc__); return 1
    cmd, args = argv[0], argv[1:]
    if cmd == 'backup':
        return 0 if backup() or True else 1
    if cmd == 'admin-senha' and args:
        return admin_senha(args[0])
    if cmd == 'importar-db' and args:
        return importar_db(args[0])
    if cmd == 'importar-exames' and args:
        return importar_exames(args[0])
    if cmd == 'importar-bh' and args:
        return importar_bh(args[0])
    if cmd == 'config' and args:
        return gravar_config(args[0])
    print(__doc__); return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
