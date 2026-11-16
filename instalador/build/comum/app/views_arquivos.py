"""Módulo Documentos: upload de contratos e de documentos de fiscalização (com vencimento)."""
import io

from flask import Blueprint, abort, flash, g, redirect, render_template, request, send_file, url_for

from . import arquivos, avisos, login_obrigatorio
from .db import get_db

bp = Blueprint('arq', __name__, url_prefix='/documentos-arquivo')


def _usuario():
    return g.usuario['usuario']


def _aba_atual():
    return 'FISCALIZACAO' if request.values.get('aba') == 'fiscalizacao' else 'CONTRATO'


@bp.route('')
@login_obrigatorio
def lista():
    db = get_db()
    avisos.verificar(db)  # confere os vencimentos ao abrir a tela (o aviso automático também roda de hora em hora)
    aba = _aba_atual()
    return render_template('arquivos.html', aba=aba, tipos=arquivos.TIPOS, docs=arquivos.listar(db, aba),
                           extensoes=', '.join(sorted(arquivos.EXTENSOES)), max_mb=arquivos.MAX_BYTES // (1024 * 1024))


@bp.route('/novo', methods=['POST'])
@login_obrigatorio
def novo():
    tipo = request.form.get('tipo', '')
    arquivo = request.files.get('arquivo')
    try:
        conteudo = arquivo.read(arquivos.MAX_BYTES + 1) if arquivo and arquivo.filename else b''
        arquivos.adicionar(get_db(), tipo, request.form.get('nome', ''), request.form.get('vencimento', ''),
                           arquivo.filename if arquivo else '', conteudo, _usuario())
        flash('Documento enviado.', 'ok')
    except arquivos.ErroDocumento as e:
        flash(str(e), 'erro')
    return redirect(url_for('arq.lista', aba='fiscalizacao' if tipo == 'FISCALIZACAO' else 'contratos'))


@bp.route('/<int:aid>/arquivo')
@login_obrigatorio
def arquivo(aid):
    try:
        doc = arquivos.obter(get_db(), aid, True)
    except arquivos.ErroDocumento:
        abort(404)
    return send_file(io.BytesIO(doc['conteudo']), mimetype=doc['content_type'], as_attachment=bool(request.args.get('baixar')),
                     download_name=doc['arquivo_nome'])


@bp.route('/<int:aid>/editar', methods=['POST'])
@login_obrigatorio
def editar(aid):
    try:
        doc = arquivos.obter(get_db(), aid)
        arquivos.editar(get_db(), aid, request.form.get('nome', ''), request.form.get('vencimento', ''), _usuario())
        flash('Documento alterado.', 'ok')
    except arquivos.ErroDocumento as e:
        flash(str(e), 'erro')
        doc = None
    aba = 'fiscalizacao' if doc and doc['tipo'] == 'FISCALIZACAO' else 'contratos'
    return redirect(url_for('arq.lista', aba=aba))


@bp.route('/<int:aid>/excluir', methods=['POST'])
@login_obrigatorio
def excluir(aid):
    try:
        doc = arquivos.obter(get_db(), aid)
        arquivos.excluir(get_db(), aid)
        flash('Documento excluído.', 'ok')
    except arquivos.ErroDocumento as e:
        flash(str(e), 'erro')
        doc = None
    aba = 'fiscalizacao' if doc and doc['tipo'] == 'FISCALIZACAO' else 'contratos'
    return redirect(url_for('arq.lista', aba=aba))
