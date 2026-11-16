"""Relatório ONA: página, PDF e Excel."""
import io
from datetime import date

from flask import Blueprint, g, render_template, request, send_file

from . import login_obrigatorio, ona, util
from .db import config_get, get_db

bp = Blueprint('ona', __name__, url_prefix='/ona')


def _periodo():
    hoje = date.today()
    de = util.para_data(request.args.get('de')) or hoje.replace(day=1)
    ate = util.para_data(request.args.get('ate')) or hoje
    if ate < de:
        de, ate = ate, de
    return de, ate


def _pct(v):
    return '—' if v is None else ('%.1f%%' % v).replace('.', ',')


@bp.route('')
@login_obrigatorio
def pagina():
    de, ate = _periodo()
    return render_template('ona.html', r=_indicadores(de, ate), de=de.isoformat(), ate=ate.isoformat(), pct=_pct)


def _indicadores(de, ate):
    """Indicadores do período com cache curto (1 minuto, calculado uma vez só); um exame realizado novo aparece na hora."""
    from . import cache_curto
    from .anexos import caminho_do_banco
    db = get_db()
    marca = tuple(db.execute('SELECT MAX(id), COUNT(*) FROM realizacoes WHERE data BETWEEN ? AND ?', (de.isoformat(), ate.isoformat())).fetchone())
    marca += tuple(db.execute('SELECT MAX(id) FROM agenda_horarios').fetchone())
    return cache_curto.obter(('ona', caminho_do_banco(db), de.isoformat(), ate.isoformat()) + marca, lambda: ona.indicadores(db, de, ate), 60)


@bp.route('/relatorio.pdf')
@login_obrigatorio
def pdf():
    """Dossiê ONA completo: capa, sumário, seções com gráficos explicados, validação e contracapa."""
    from .ona_dossie import dossie_pdf
    de, ate = _periodo()
    dados = dossie_pdf(get_db(), de, ate, config_get('clinica_nome', ''), g.usuario['usuario'])
    return send_file(io.BytesIO(dados), mimetype='application/pdf', as_attachment=request.args.get('baixar') == '1', download_name='dossie-ona.pdf')


@bp.route('/relatorio-resumido.pdf')
@login_obrigatorio
def pdf_resumido():
    from .ona_docs import relatorio_pdf
    de, ate = _periodo()
    dados = relatorio_pdf(ona.indicadores(get_db(), de, ate), config_get('clinica_nome', ''))
    return send_file(io.BytesIO(dados), mimetype='application/pdf', as_attachment=True, download_name='relatorio-ona.pdf')


@bp.route('/relatorio.xlsx')
@login_obrigatorio
def xlsx():
    from .ona_docs import relatorio_xlsx
    de, ate = _periodo()
    dados = relatorio_xlsx(ona.indicadores(get_db(), de, ate), config_get('clinica_nome', ''))
    return send_file(io.BytesIO(dados), as_attachment=True, download_name='relatorio-ona.xlsx',
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
