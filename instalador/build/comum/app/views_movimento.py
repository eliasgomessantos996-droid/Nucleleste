"""Movimento de caixa: abertura e fechamento diário, recebimentos com quitação e relatório para assinatura."""
import io
from datetime import date
from urllib.parse import urlsplit

from flask import Blueprint, abort, flash, g, redirect, render_template, request, send_file, url_for

from . import login_obrigatorio, movimento, util
from .db import config_get, get_db

bp = Blueprint('mov', __name__, url_prefix='/movimento-caixa')


def _usuario():
    return g.usuario['usuario']


def _privilegiado():
    return movimento.pode_privilegiado(g.usuario, g.modulos)


def _hoje():
    return date.today().isoformat()


def _filtros():
    """(dia, todos_usuarios) escolhidos na tela. `dia`: AAAA-MM-DD (padrão: hoje) ou None para todas as datas.
    `todos_usuarios`: só vale para a administração e a gerência; os demais veem sempre só o que fizeram."""
    bruto = (request.values.get('dia') or '').strip()
    if bruto == 'todas':
        dia = None
    else:
        try:
            dia = date.fromisoformat(bruto).isoformat() if bruto else _hoje()
        except ValueError:
            dia = _hoje()
    return dia, _privilegiado() and request.values.get('usuarios') == 'todos'


def _volta():
    """Volta para a tela de onde veio (mantém a data e o filtro escolhidos); se não der, para a página do caixa."""
    ref = request.referrer or ''
    if ref.startswith(request.host_url) and urlsplit(ref).path == url_for('mov.pagina'):
        return redirect(ref)
    return redirect(url_for('mov.pagina'))


@bp.route('')
@login_obrigatorio
def pagina():
    db = get_db()
    hoje = _hoje()
    dia, todos_usuarios = _filtros()
    atual = movimento.sessao_aberta(db, _usuario())
    if atual is not None and atual['data'] != hoje:
        movimento.alertar(db, g.usuario['id'], atual, hoje)  # aviso pelo contato do sistema (uma vez por dia)
    aberta_hoje = atual if atual is not None and atual['data'] == hoje else None
    recebidos = []
    if aberta_hoje:
        recebidos = [dict(r) for r in db.execute("SELECT * FROM caixa WHERE sessao_id=? AND status='PAGO' ORDER BY pago_em, id",
                                                 (aberta_hoje['id'],))]
    sessoes = [dict(r) for r in db.execute(
        "SELECT s.*, (SELECT COUNT(*) FROM caixa c WHERE c.sessao_id=s.id AND c.status='PAGO') AS n "
        'FROM caixa_sessoes s ' + ('' if _privilegiado() else 'WHERE s.usuario=? ') + 'ORDER BY s.data DESC, s.id DESC LIMIT 60',
        () if _privilegiado() else (_usuario(),))]   # a lista de caixas é a visão da gestão (reabrir, relatório); os lançamentos seguem o filtro
    return render_template('movimento.html', hoje=hoje, atual=atual, aberta_hoje=aberta_hoje, recebidos=recebidos,
                           pendentes=movimento.pendentes(db, _usuario(), _privilegiado(), dia, todos_usuarios), eu=_usuario(),
                           sessoes=sessoes, privilegiado=_privilegiado(), dia=dia, todos_usuarios=todos_usuarios,
                           recentes=(movimento.recebimentos_recentes(db, usuario=None if todos_usuarios else _usuario(), dia=dia)
                                     if _privilegiado() else []),
                           formas=movimento.FORMAS, formas_texto=movimento.formas_texto,
                           fmt=lambda d: '%s/%s/%s' % (d[8:10], d[5:7], d[:4]))


@bp.route('/abrir', methods=['POST'])
@login_obrigatorio
def abrir():
    try:
        fundo = util.para_valor(request.form.get('fundo')) or 0
        movimento.abrir(get_db(), _usuario(), g.usuario['id'], round(fundo, 2), _hoje())
        flash('Caixa aberto. Bom trabalho!', 'ok')
    except movimento.ErroCaixa as e:
        flash(str(e), 'erro')
    return redirect(url_for('mov.pagina'))


@bp.route('/fechar', methods=['POST'])
@login_obrigatorio
def fechar():
    try:
        sid = movimento.fechar(get_db(), _usuario(), request.form.get('sessao', type=int))
        flash('Caixa fechado. Confira o relatório e assine.', 'ok')
        return redirect(url_for('mov.relatorio', sessao_id=sid))
    except movimento.ErroCaixa as e:
        flash(str(e), 'erro')
    return redirect(url_for('mov.pagina'))


@bp.route('/reabrir/<int:sessao_id>', methods=['POST'])
@login_obrigatorio
def reabrir(sessao_id):
    """Gerência: reabre um caixa que foi fechado sem querer. O dono recebe um aviso pelo contato do sistema."""
    from . import avisos
    from .db import agora
    db = get_db()
    try:
        s = movimento.reabrir(db, _privilegiado(), sessao_id)
    except movimento.ErroCaixa as e:
        flash(str(e), 'erro')
        return redirect(url_for('mov.pagina'))
    dono = db.execute('SELECT id FROM usuarios WHERE usuario=?', (s['usuario'],)).fetchone()
    de = avisos.sistema_id(db)
    if dono and de is not None and dono['id'] != g.usuario['id']:
        db.execute('INSERT INTO chat_mensagens (de_id, para_id, corpo, criado_em) VALUES (?,?,?,?)',
                   (de, dono['id'], 'O seu caixa de %s foi reaberto por %s. Feche-o novamente quando terminar.'
                    % ('%s/%s' % (s['data'][8:10], s['data'][5:7]), _usuario()), agora()))
        db.commit()
    g.detalhe_auditoria = 'caixa de %s (%s)' % (s['usuario'], s['data'])
    flash('Caixa de %s (%s) reaberto.' % (s['usuario'], '%s/%s/%s' % (s['data'][8:10], s['data'][5:7], s['data'][:4])), 'ok')
    return redirect(url_for('mov.pagina'))


@bp.route('/receber/<int:cid>', methods=['POST'])
@login_obrigatorio
def receber(cid):
    try:
        r = movimento.receber(get_db(), _usuario(), g.usuario['id'], cid, request.form.get('valor'),
                              request.form.get('forma', ''), util.para_valor(request.form.get('recebido')),
                              request.form.get('nota_fiscal', ''), _hoje(),
                              request.form.get('forma2', ''), util.para_valor(request.form.get('valor2')))
        msg = 'Recebimento registrado.'
        if r['troco']:
            msg += ' Troco: R$ %s.' % util.moeda(r['troco'])
        flash(msg, 'ok')
    except movimento.ErroCaixa as e:
        flash(str(e), 'erro')
    return _volta()


@bp.route('/editar/<int:cid>', methods=['POST'])
@login_obrigatorio
def editar(cid):
    try:
        movimento.editar_recebimento(get_db(), _usuario(), _privilegiado(), cid, request.form.get('valor'),
                                     request.form.get('forma', ''), util.para_valor(request.form.get('recebido')),
                                     request.form.get('nota_fiscal', ''), request.form.get('obs', ''),
                                     request.form.get('forma2', ''), util.para_valor(request.form.get('valor2')))
        flash('Recebimento corrigido.', 'ok')
    except movimento.ErroCaixa as e:
        flash(str(e), 'erro')
    return _volta()


@bp.route('/excluir/<int:cid>', methods=['POST'])
@login_obrigatorio
def excluir(cid):
    try:
        r = movimento.excluir_lancamento(get_db(), _privilegiado(), cid)
        flash('Lançamento de %s excluído do movimento de caixa.' % (r['cliente'] or 'cliente'), 'ok')
    except movimento.ErroCaixa as e:
        flash(str(e), 'erro')
    return _volta()


@bp.route('/excluir-varios', methods=['POST'])
@login_obrigatorio
def excluir_varios():
    """Exclui os lançamentos marcados (checkbox) ou todos de uma lista ("todos" = pendentes ou recebidos)."""
    ids = [int(x) for x in request.form.getlist('ids') if x.isdigit()]
    todos = request.form.get('todos') or ''
    db = get_db()
    dia, todos_usuarios = _filtros()
    if todos == 'pendentes':   # "todos" = os que estão na lista (dia e usuários escolhidos na tela)
        ids = [p['id'] for p in movimento.pendentes(db, _usuario(), _privilegiado(), dia, todos_usuarios)]
    elif todos == 'recebidos':
        ids = [r['id'] for r in movimento.recebimentos_recentes(db, usuario=None if todos_usuarios else _usuario(), dia=dia)]
    try:
        r = movimento.excluir_varios(db, _privilegiado(), ids)
        g.detalhe_auditoria = 'excluídos=%d; ids=%s' % (r['qtd'], ','.join(map(str, r['ids'])))
        flash('%d lançamento(s) excluído(s) do movimento de caixa.' % r['qtd'], 'ok')
    except movimento.ErroCaixa as e:
        flash(str(e), 'erro')
    return _volta()


@bp.route('/quitacao/<int:cid>')
@login_obrigatorio
def quitacao(cid):
    try:
        r = movimento.quitacao(get_db(), cid)
    except movimento.ErroCaixa:
        abort(404)
    return render_template('movimento_quitacao.html', r=r, clinica=config_get('clinica_nome', ''),
                           cidade=config_get('clinica_cidade', ''), hoje=util.data_extenso())


def _relatorio_permitido(sessao_id):
    """Relatório do caixa: cada pessoa vê só o dela; a administração e a gerência veem os de todos."""
    try:
        rel = movimento.relatorio(get_db(), sessao_id)
    except movimento.ErroCaixa:
        abort(404)
    if not _privilegiado() and (rel['sessao']['usuario'] or '').upper() != _usuario().upper():
        abort(404)
    return rel


@bp.route('/relatorio/<int:sessao_id>')
@login_obrigatorio
def relatorio(sessao_id):
    rel = _relatorio_permitido(sessao_id)
    return render_template('movimento_relatorio.html', rel=rel, clinica=config_get('clinica_nome', ''))


@bp.route('/relatorio/<int:sessao_id>.pdf')
@login_obrigatorio
def relatorio_pdf(sessao_id):
    from . import movimento_docs
    rel = _relatorio_permitido(sessao_id)
    pdf = movimento_docs.relatorio_pdf(rel, config_get('clinica_nome', ''))
    return send_file(io.BytesIO(pdf), mimetype='application/pdf', as_attachment=request.args.get('baixar') == '1',
                     download_name='caixa-%s.pdf' % rel['sessao']['data'])
