"""Controle de blindagens: cadastro, validade, solicitação de devolução, planilha e documentos de transporte."""
import io
from datetime import date

from flask import (Blueprint, abort, flash, g, redirect, render_template, request, send_file, url_for)

from . import blindagem_docs as docs
from . import blindagens as bl
from . import login_obrigatorio, util
from .db import config_get, config_set, get_db

bp = Blueprint('blind', __name__, url_prefix='/blindagens')

CLASSE_STATUS = {bl.VALIDO: 'pago', bl.VENCIDO: 'cancelado', bl.DEVOLUCAO: 'aberto', bl.DEVOLVIDA: 'pago'}


@bp.app_template_global('classe_status_blindagem')
def classe_status_blindagem(status):
    return CLASSE_STATUS.get(status, '')


# ------------------------------------------------------------------ cadastro
@bp.route('')
@login_obrigatorio
def lista():
    db = get_db()
    bl.atualizar_status(db)
    status = request.args.get('status', '')
    busca = request.args.get('q', '')
    return render_template('blindagens.html', rows=bl.listar(db, status, busca), status=status, busca=busca,
                           contagem=bl.contagem(db), hoje=date.today().isoformat())


@bp.route('/novo', methods=['GET', 'POST'])
@login_obrigatorio
def novo():
    return _formulario(None)


@bp.route('/<int:bid>', methods=['GET', 'POST'])
@login_obrigatorio
def editar(bid):
    return _formulario(bid)


def _formulario(bid):
    db = get_db()
    bl.atualizar_status(db)
    atual = db.execute('SELECT * FROM blindagens WHERE id=?', (bid,)).fetchone() if bid else None
    if bid and not atual:
        abort(404)
    campos = ['lote', 'nota_fiscal', 'serie', 'data_nota', 'cfop', 'validade']
    f = {k: (atual[k] if atual else '') for k in campos}
    if request.method == 'POST':
        if atual and atual['status'] in bl.TRAVADAS:
            flash('Esta blindagem já teve a devolução solicitada e não pode mais ser alterada.', 'erro')
            return redirect(url_for('blind.lista'))
        f = {k: (request.form.get(k) or '').strip() for k in campos}
        dados, erros = bl.validar(f, db, bid)
        if erros:
            for e in erros:
                flash(e, 'erro')
        else:
            usuario = g.usuario['usuario']
            if atual:
                bl.atualizar(db, bid, dados, usuario)
                flash('Blindagem atualizada com sucesso!', 'ok')
            else:
                bl.criar(db, dados, usuario)
                flash('Blindagem cadastrada com status VÁLIDO. Lote %s.' % dados['lote'], 'ok')
                if request.form.get('continuar'):
                    return redirect(url_for('blind.novo'))
            return redirect(url_for('blind.lista'))
    return render_template('blindagem_form.html', f=f, atual=atual)


@bp.route('/<int:bid>/excluir', methods=['POST'])
@login_obrigatorio
def excluir(bid):
    db = get_db()
    b = db.execute('SELECT * FROM blindagens WHERE id=?', (bid,)).fetchone()
    if not b:
        abort(404)
    if b['status'] in bl.TRAVADAS:
        flash('Não é possível excluir uma blindagem com devolução solicitada ou devolvida.', 'erro')
    else:
        db.execute('DELETE FROM blindagens WHERE id=?', (bid,))
        db.commit()
        flash('Blindagem %s excluída.' % b['lote'], 'ok')
    return redirect(url_for('blind.lista'))


# ------------------------------------------------------------------ solicitar devolução
@bp.route('/devolucao', methods=['GET', 'POST'])
@login_obrigatorio
def devolucao():
    db = get_db()
    bl.atualizar_status(db)
    valor_txt = config_get('blindagem_valor_unitario', '405,80')
    if request.method == 'POST':
        valor_txt = (request.form.get('valor_unitario') or '').strip() or valor_txt
        valor = util.para_valor(valor_txt)
        ids = [i for i in request.form.getlist('ids') if i.isdigit()]
        if valor is None or valor < 0:
            flash('Informe o valor da mercadoria por volume (exemplo: 405,80).', 'erro')
        else:
            try:
                did = bl.solicitar_devolucao(db, ids, valor, g.usuario['usuario'])
            except bl.ErroBlindagem as erro:
                flash(str(erro), 'erro')
            else:
                config_set('blindagem_valor_unitario', util.moeda(valor))
                flash('Devolução solicitada: status alterado para DEVOLUÇÃO SOLICITADA.', 'ok')
                return redirect(url_for('blind.devolucao_resultado', did=did))
    rows = db.execute("SELECT * FROM blindagens ORDER BY CASE status WHEN ? THEN 0 WHEN ? THEN 1 ELSE 2 END, validade, lote",
                      (bl.VENCIDO, bl.VALIDO)).fetchall()
    return render_template('blindagem_devolucao.html', rows=rows, valor=valor_txt, vencidas=sum(1 for r in rows if r['status'] == bl.VENCIDO),
                           hoje=date.today().isoformat())


# ------------------------------------------------------------------ confirmar devolução
@bp.route('/devolvidas', methods=['GET', 'POST'])
@login_obrigatorio
def devolvidas():
    """Quem decide quando a devolução aconteceu: marca as solicitadas como DEVOLVIDA na data informada."""
    db = get_db()
    bl.atualizar_status(db)
    if request.method == 'POST':
        ids = [i for i in request.form.getlist('ids') if i.isdigit()]
        data_dev = util.para_data(request.form.get('data_devolvida'))
        if not data_dev:
            flash('Informe a data em que as blindagens foram devolvidas.', 'erro')
        else:
            try:
                n = bl.registrar_devolvidas(db, ids, data_dev, g.usuario['usuario'])
            except bl.ErroBlindagem as erro:
                flash(str(erro), 'erro')
            else:
                flash('%d blindagem(ns) marcada(s) como DEVOLVIDA em %s.' % (n, util.data_br(data_dev)), 'ok')
                return redirect(url_for('blind.devolvidas'))
    pendentes = bl.pendentes_devolvida(db)
    feitas = db.execute('SELECT * FROM blindagens WHERE status=? ORDER BY devolvida_em DESC, lote LIMIT 300',
                        (bl.DEVOLVIDA,)).fetchall()
    return render_template('blindagem_devolvidas.html', pendentes=pendentes, feitas=feitas, hoje=date.today().isoformat())


def _solicitacao(did):
    cab, itens = bl.devolucao(get_db(), did)
    if not cab or not itens:
        abort(404)
    ctx = docs.montar_contexto(itens, config_get('clinica_nome', ''), config_get('clinica_cidade', 'Governador Valadares - MG'),
                               config_get('clinica_cnpj', ''), cab['valor_unitario'], date.today())
    return cab, itens, ctx


@bp.route('/devolucao/<int:did>')
@login_obrigatorio
def devolucao_resultado(did):
    cab, itens, ctx = _solicitacao(did)
    qtd = docs.normalizar_quantidades(ctx)
    lista_docs = [{'slug': s, 'titulo': t, 'unidade': u, 'qtd': qtd[s]} for s, t, u, _p in docs.DOCUMENTOS]
    return render_template('blindagem_devolucao_ok.html', cab=cab, itens=itens, docs=lista_docs, ctx=ctx,
                           max_qtd=docs.MAX_QTD)


def _enviar_pdf(dados, nome, baixar):
    return send_file(io.BytesIO(dados), mimetype='application/pdf', as_attachment=baixar, download_name=nome)


@bp.route('/devolucao/<int:did>/planilha.pdf')
@login_obrigatorio
def planilha_pdf(did):
    cab, itens, ctx = _solicitacao(did)
    ctx['data'] = util.para_data(cab['criado_em']) or ctx['data']
    return _enviar_pdf(docs.planilha_pdf(ctx, did), 'planilha-devolucao-%d.pdf' % did, True)


@bp.route('/devolucao/<int:did>/planilha.xlsx')
@login_obrigatorio
def planilha_xlsx(did):
    cab, itens, ctx = _solicitacao(did)
    ctx['data'] = util.para_data(cab['criado_em']) or ctx['data']
    return send_file(io.BytesIO(docs.planilha_xlsx(ctx, did)), as_attachment=True, download_name='planilha-devolucao-%d.xlsx' % did,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@bp.route('/devolucao/<int:did>/documentos.pdf')
@login_obrigatorio
def documentos_pdf(did):
    """Todos os documentos num único PDF; as quantidades vêm de q_<documento>."""
    cab, itens, ctx = _solicitacao(did)
    pedido = {s: request.args.get('q_' + s) for s in docs.SLUGS if request.args.get('q_' + s) is not None}
    qtd = docs.normalizar_quantidades(ctx, pedido)
    return _enviar_pdf(docs.gerar_documentos(ctx, qtd), 'documentos-devolucao-%d.pdf' % did, request.args.get('baixar') == '1')


@bp.route('/devolucao/<int:did>/documento/<slug>.pdf')
@login_obrigatorio
def documento_pdf(did, slug):
    """Um documento só, na quantidade pedida, aberto para imprimir."""
    if slug not in docs.SLUGS:
        abort(404)
    cab, itens, ctx = _solicitacao(did)
    qtd = docs.normalizar_quantidades(ctx, {slug: request.args.get('qtd')})
    so_este = {s: (qtd[s] if s == slug else 0) for s in docs.SLUGS}
    return _enviar_pdf(docs.gerar_documentos(ctx, so_este), '%s-%d.pdf' % (slug.replace('_', '-'), did), request.args.get('baixar') == '1')
