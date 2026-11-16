"""Saúde do sistema para a gestão: versão, disco, backups, banco, caixas abertos, vencimentos e últimos erros.

Não é um monitoramento novo: usa o backup já existente, o registro de atividades (onde os erros internos são gravados)
e as tabelas do próprio sistema.
"""
import os
import shutil
from datetime import date, datetime, timedelta

from flask import Blueprint, current_app, render_template

from . import anexos, login_obrigatorio, saude, versao
from .db import get_db

bp = Blueprint('saude', __name__, url_prefix='/saude')
ERRO_MODULO = 'Sistema'
ERRO_ACAO = 'Erro interno'
DIAS_VENCIMENTO = 60


def _arquivos_de_backup():
    """Caminhos dos backups (.zip e .db antigos), sem contar o *_anexos.db avulso."""
    from .views_admin import pasta_backup
    pasta = pasta_backup()
    return [os.path.join(pasta, f) for f in os.listdir(pasta)
            if f.lower().endswith(('.zip', '.db')) and not f.lower().endswith('_anexos.db')]


def _ultimo_backup():
    arquivos = _arquivos_de_backup()
    if not arquivos:
        return None
    caminho = max(arquivos, key=os.path.getmtime)
    return {'nome': os.path.basename(caminho), 'tamanho_mb': os.path.getsize(caminho) / 1048576,
            'quando': datetime.fromtimestamp(os.path.getmtime(caminho)).strftime('%d/%m/%Y %H:%M')}


def _backups_mb():
    return sum(os.path.getsize(c) for c in _arquivos_de_backup()) / 1048576


def indicadores(db):
    """Números da tela (separados para poder ser testados sem o navegador)."""
    pasta_dados = current_app.config['PASTA_DADOS']
    banco = current_app.config['DATABASE']
    anexos_db = anexos.caminho_ao_lado(banco)
    disco = shutil.disk_usage(pasta_dados)
    hoje = date.today()
    limite = (hoje + timedelta(days=DIAS_VENCIMENTO)).isoformat()
    ultimo = _ultimo_backup()
    agora = datetime.now()
    contar = lambda sql, *p: db.execute(sql, p).fetchone()[0]   # noqa: E731
    desde = lambda dias: (agora - timedelta(days=dias)).strftime('%Y-%m-%d %H:%M:%S')   # noqa: E731
    sql_erros = 'SELECT COUNT(*) FROM auditoria WHERE modulo=? AND acao=? AND data_hora>=?'
    vencidos = contar("SELECT COUNT(*) FROM arquivos_docs WHERE tipo='FISCALIZACAO' AND vencimento IS NOT NULL AND vencimento<?",
                      hoje.isoformat())
    pendentes = contar("SELECT COUNT(*) FROM arquivos_docs WHERE tipo='FISCALIZACAO' AND vencimento IS NOT NULL AND vencimento<=?", limite)
    s = {
        'versao': versao(),
        'disco_livre_gb': disco.free / 1024 ** 3,
        'disco_total_gb': disco.total / 1024 ** 3,
        'backup': ultimo,
        'backup_idade_dias': None if ultimo is None else max(0, (agora - datetime.strptime(ultimo['quando'], '%d/%m/%Y %H:%M')).total_seconds() / 86400),
        'backups_mb': _backups_mb(),
        'banco_mb': (os.path.getsize(banco) + (os.path.getsize(anexos_db) if os.path.exists(anexos_db) else 0)) / 1048576,   # sistema + anexos
        'banco_integro': db.execute('PRAGMA quick_check').fetchone()[0] == 'ok',
        'caixas_abertos': contar("SELECT COUNT(*) FROM caixa_sessoes WHERE status='ABERTO'"),
        'caixas_antigos': contar("SELECT COUNT(*) FROM caixa_sessoes WHERE status='ABERTO' AND data<?", hoje.isoformat()),
        'vencimentos_pendentes': pendentes,
        'docs_vencidos': vencidos,
        'docs_a_vencer': pendentes - vencidos,
        'dias_vencimento': DIAS_VENCIMENTO,
        'erros_24h': contar(sql_erros, ERRO_MODULO, ERRO_ACAO, desde(1)),
        'erros_7d': contar(sql_erros, ERRO_MODULO, ERRO_ACAO, desde(7)),
        'erros': [dict(r) for r in db.execute(
            'SELECT data_hora, usuario, rota, detalhe FROM auditoria WHERE modulo=? AND acao=? ORDER BY id DESC LIMIT 15',
            (ERRO_MODULO, ERRO_ACAO))],
        'atualizado_em': agora.strftime('%H:%M:%S'),
    }
    s['avaliacao'] = saude.avaliar(s)
    return s


@bp.route('')
@login_obrigatorio
def pagina():
    return render_template('saude.html', s=indicadores(get_db()), dias=DIAS_VENCIMENTO)
