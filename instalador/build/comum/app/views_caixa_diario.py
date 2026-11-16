"""Caixa diário da empresa: tela dos lançamentos, saldos em cadeia e relatório do dia em Excel."""
import datetime as _dt

from flask import Blueprint, flash, g, redirect, render_template, request, send_file, url_for

from . import caixa_diario as cx
from . import login_obrigatorio
from .db import get_db

bp = Blueprint('cxd', __name__, url_prefix='/caixa-diario')


def _usuario():
    return g.usuario['usuario']


def _dia_da_tela(txt):
    try:
        return _dt.date.fromisoformat(txt).isoformat()
    except (TypeError, ValueError):
        return _dt.date.today().isoformat()


def _volta(dia):
    return redirect(url_for('cxd.pagina', data=dia))


def _erro(e, dia):
    flash(str(e), 'erro')
    return _volta(dia)


@bp.route('')
@login_obrigatorio
def pagina():
    db = get_db()
    cx.garantir(db)
    dia = _dia_da_tela(request.args.get('data'))
    editar = None
    if request.args.get('editar'):
        editar = db.execute('SELECT * FROM cxd_lancamentos WHERE id=?', (request.args.get('editar'),)).fetchone()
    ini = cx.inicio(db)
    sal = None
    erro_dia = None
    if ini is not None:
        try:
            sal = cx.saldos_do_dia(db, dia)
        except cx.ErroCaixaDiario as e:
            erro_dia = str(e)
    return render_template('caixa_diario.html', dia=dia, ini=ini, sal=sal, erro_dia=erro_dia,
                           lancamentos=cx.lancamentos_do_dia(db, dia), editar=editar, contas=cx.CONTAS, cores=cx.COR_CONTA, tipos=cx.TIPOS,
                           hoje=_dt.date.today().isoformat(), br=cx._br)


@bp.route('/inicio', methods=['POST'])
@login_obrigatorio
def inicio():
    db = get_db()
    cx.garantir(db)
    try:
        data = cx.definir_inicio(db, request.form, _usuario())
    except cx.ErroCaixaDiario as e:
        return _erro(e, _dia_da_tela(request.form.get('data')))
    flash('Saldos iniciais gravados a partir de %s.' % cx._br(data), 'ok')
    return _volta(data)


@bp.route('/lancar', methods=['POST'])
@login_obrigatorio
def lancar():
    db = get_db()
    cx.garantir(db)
    try:
        dados = cx.dados_do_formulario(request.form)
        cx.lancar(db, dados, _usuario())
    except cx.ErroCaixaDiario as e:
        return _erro(e, _dia_da_tela(request.form.get('data')))
    flash('Lançamento gravado.', 'ok')
    return _volta(dados['data'])


@bp.route('/<int:lid>/atualizar', methods=['POST'])
@login_obrigatorio
def atualizar(lid):
    db = get_db()
    cx.garantir(db)
    try:
        dados = cx.dados_do_formulario(request.form)
        cx.atualizar(db, lid, dados, _usuario())
    except cx.ErroCaixaDiario as e:
        return _erro(e, _dia_da_tela(request.form.get('data')))
    flash('Lançamento alterado.', 'ok')
    return _volta(dados['data'])


@bp.route('/<int:lid>/excluir', methods=['POST'])
@login_obrigatorio
def excluir(lid):
    db = get_db()
    cx.garantir(db)
    dia = _dia_da_tela(request.form.get('data'))
    cx.excluir(db, lid)
    flash('Lançamento excluído.', 'ok')
    return _volta(dia)


@bp.route('/retidas', methods=['POST'])
@login_obrigatorio
def retidas():
    db = get_db()
    cx.garantir(db)
    dia = _dia_da_tela(request.form.get('data'))
    try:
        cx.adicionar_retida(db, request.form)
    except cx.ErroCaixaDiario as e:
        return _erro(e, dia)
    flash('Retirada retida incluída.', 'ok')
    return _volta(dia)


@bp.route('/retidas/<int:rid>/excluir', methods=['POST'])
@login_obrigatorio
def retida_excluir(rid):
    db = get_db()
    cx.garantir(db)
    dia = _dia_da_tela(request.form.get('data'))
    cx.excluir_retida(db, rid)
    flash('Retirada retida excluída.', 'ok')
    return _volta(dia)


@bp.route('/relatorio.xlsx')
@login_obrigatorio
def relatorio():
    db = get_db()
    cx.garantir(db)
    dia = _dia_da_tela(request.args.get('data'))
    try:
        buf = cx.relatorio_xlsx(db, dia)
    except cx.ErroCaixaDiario as e:
        return _erro(e, dia)
    return send_file(buf, as_attachment=True, download_name='Caixa diario %s.xlsx' % cx._br(dia).replace('/', '-'),
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
