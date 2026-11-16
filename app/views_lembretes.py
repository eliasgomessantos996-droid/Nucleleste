"""Telas e rotas dos lembretes em checklist (regra de negócio em app/lembretes.py).

Páginas: /lembretes (gestão dos meus lembretes e dos "para todos"), formulário de novo/editar.
JSON (a janela que abre ao entrar no sistema): GET /lembretes/pendentes e POST de marcar, desmarcar e desativar.
"""
from flask import Blueprint, flash, g, jsonify, redirect, render_template, request, url_for

from . import login_obrigatorio, lembretes
from .db import get_db

bp = Blueprint('lem', __name__, url_prefix='/lembretes')


def _ajax():
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes.best == 'application/json'


def _voltar():
    destino = request.form.get('voltar') or ''
    return destino if destino.startswith('/') and not destino.startswith('//') else url_for('lem.painel')


@bp.route('')
@login_obrigatorio
def painel():
    db = get_db()
    gestao = lembretes.eh_gestao(db, g.usuario)
    return render_template('lembretes.html', lista=lembretes.listar(db, g.usuario, gestao), gestao=gestao)


@bp.route('/novo')
@login_obrigatorio
def novo():
    db = get_db()
    gestao = lembretes.eh_gestao(db, g.usuario)
    dados = {'titulo': '', 'para_todos': False, 'data_inicio': lembretes.hoje(), 'reset_diario': False, 'itens': ''}
    return render_template('lembrete_form.html', dados=dados, gestao=gestao, lid=None)


@bp.route('/<int:lid>/editar')
@login_obrigatorio
def editar(lid):
    db = get_db()
    gestao = lembretes.eh_gestao(db, g.usuario)
    dados = lembretes.dados_para_form(db, lid)
    if not dados or not lembretes.pode_editar({'para_todos': dados['para_todos'], 'usuario_id': dados['usuario_id']}, g.usuario['id'], gestao):
        flash('Lembrete não encontrado ou sem permissão para alterar.', 'erro')
        return redirect(url_for('lem.painel'))
    return render_template('lembrete_form.html', dados=dados, gestao=gestao, lid=lid)


@bp.route('/salvar', methods=['POST'])
@login_obrigatorio
def salvar():
    db = get_db()
    bruto = (request.form.get('id') or '').strip()
    lid = int(bruto) if bruto.isdigit() else None
    try:
        lembretes.salvar(db, g.usuario, request.form, lid)
    except lembretes.ErroLembrete as e:
        flash(str(e), 'erro')
        return redirect(url_for('lem.editar', lid=lid) if lid else url_for('lem.novo'))
    flash('Lembrete salvo.')
    return redirect(url_for('lem.painel'))


def _ativar(lid, ativo):
    try:
        lembretes.definir_ativo(get_db(), g.usuario, lid, ativo)
    except lembretes.ErroLembrete as e:
        if _ajax():
            return jsonify(ok=False, erro=str(e)), 400
        flash(str(e), 'erro')
        return redirect(_voltar())
    if _ajax():
        return jsonify(ok=True)
    flash('Lembrete %s.' % ('reativado' if ativo else 'desativado'))
    return redirect(_voltar())


@bp.route('/<int:lid>/ativar', methods=['POST'])
@login_obrigatorio
def ativar(lid):
    return _ativar(lid, True)


@bp.route('/<int:lid>/desativar', methods=['POST'])
@login_obrigatorio
def desativar(lid):
    return _ativar(lid, False)


@bp.route('/<int:lid>/excluir', methods=['POST'])
@login_obrigatorio
def excluir(lid):
    try:
        lembretes.excluir(get_db(), g.usuario, lid)
    except lembretes.ErroLembrete as e:
        flash(str(e), 'erro')
        return redirect(url_for('lem.painel'))
    flash('Lembrete excluído.')
    return redirect(url_for('lem.painel'))


@bp.route('/pendentes')
@login_obrigatorio
def pendentes():
    db = get_db()
    return jsonify(lembretes=lembretes.pendentes(db, g.usuario, lembretes.eh_gestao(db, g.usuario)))


@bp.route('/<int:lid>/item/<int:iid>/marcar', methods=['POST'])
@login_obrigatorio
def marcar(lid, iid):
    try:
        lembretes.marcar(get_db(), g.usuario, lid, iid, request.form.get('valor') == '1')
    except lembretes.ErroLembrete as e:
        return jsonify(ok=False, erro=str(e)), 400
    return jsonify(ok=True)


@bp.route('/<int:lid>/desmarcar', methods=['POST'])
@login_obrigatorio
def desmarcar(lid):
    try:
        lembretes.desmarcar_tudo(get_db(), g.usuario, lid)
    except lembretes.ErroLembrete as e:
        return jsonify(ok=False, erro=str(e)), 400
    return jsonify(ok=True)
