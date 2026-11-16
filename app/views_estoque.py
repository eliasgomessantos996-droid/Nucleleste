"""Telas do Estoque de materiais e medicamentos: itens, entradas, baixas, ajuste de inventário, histórico, movimentações
e pedidos de compra (criar, enviar, receber, cancelar, duplicar, PDF e impressão)."""
import io
from datetime import date

from flask import Blueprint, abort, flash, g, jsonify, redirect, render_template, request, send_file, url_for

from . import estoque as est, estoque_docs, estoque_pedidos as ep, estoque_relatorios as er, fornecedores, login_obrigatorio
from .db import config_get, get_db

bp = Blueprint('est', __name__, url_prefix='/estoque')


@bp.app_template_filter('est_qtd')
def _filtro_quantidade(n):
    return est.qtd_txt(n or 0)


@bp.app_template_filter('est_dh')
def _filtro_data_hora(v):
    """'2026-10-27 14:05:00' -> '27/10/2026 14:05'."""
    return '%s/%s/%s %s' % (v[8:10], v[5:7], v[:4], v[11:16]) if v else ''


def _voltar(padrao):
    """Volta para a tela de onde o formulário foi enviado (só dentro do módulo de estoque)."""
    destino = request.form.get('voltar', '')
    return destino if destino.startswith('/estoque') else padrao


def _data_filtro(valor):
    try:
        return date.fromisoformat(valor).isoformat() if valor else ''
    except ValueError:
        return ''


def _movimento(fazer):
    db = get_db()
    try:
        fazer(db)
    except est.ErroEstoque as e:
        db.rollback()
        flash(str(e), 'erro')
    else:
        flash('Movimento registrado.', 'ok')
    return redirect(_voltar(url_for('est.itens')))


# ------------------------------------------------------------------ itens
@bp.route('')
@login_obrigatorio
def itens():
    db = get_db()
    tipo = request.args.get('tipo', '')
    busca = request.args.get('busca', '')
    so_abaixo = bool(request.args.get('abaixo'))
    inativos = bool(request.args.get('inativos'))
    return render_template('estoque/itens.html', itens=est.itens(db, tipo, busca, so_abaixo, inativos), tipo=tipo, busca=busca,
                           so_abaixo=so_abaixo, inativos=inativos, abaixo_total=est.resumo_alertas(db), tipos=est.TIPOS,
                           motivos=est.MOTIVOS_SAIDA, fornecedores=fornecedores.listar(db, so_ativos=True), hoje=date.today().isoformat())


@bp.route('/item', methods=['GET', 'POST'], defaults={'iid': None})
@bp.route('/item/<int:iid>', methods=['GET', 'POST'])
@login_obrigatorio
def item_editar(iid):
    db = get_db()
    atual = est.obter(db, iid) if iid else None
    if iid and atual is None:
        abort(404)
    if request.method == 'POST':
        try:
            est.salvar_item(db, request.form, g.usuario['usuario'], iid)
        except est.ErroEstoque as e:
            db.rollback()
            flash(str(e), 'erro')
            # volta com o que foi digitado (o formulário não perde os dados)
            return render_template('estoque/item_form.html', item=dict(request.form), iid=iid, tipos=est.TIPOS,
                                   tem_movimentos=_tem_movimentos(db, iid))
        flash('Item salvo.', 'ok')
        return redirect(url_for('est.itens'))
    return render_template('estoque/item_form.html', item=atual, iid=iid, tipos=est.TIPOS, tem_movimentos=_tem_movimentos(db, iid))


def _tem_movimentos(db, iid):
    return bool(iid and db.execute('SELECT 1 FROM est_movimentos WHERE item_id=? LIMIT 1', (iid,)).fetchone())


@bp.route('/item/<int:iid>/excluir', methods=['POST'])
@login_obrigatorio
def item_excluir(iid):
    db = get_db()
    try:
        est.excluir_item(db, iid)
    except est.ErroEstoque as e:
        db.rollback()
        flash(str(e), 'erro')
        return redirect(url_for('est.item_editar', iid=iid))
    flash('Item excluído.', 'ok')
    return redirect(url_for('est.itens'))


# ------------------------------------------------------------------ movimentos
@bp.route('/<int:iid>/entrada', methods=['POST'])
@login_obrigatorio
def entrada(iid):
    return _movimento(lambda db: est.entrada(db, iid, request.form, g.usuario['usuario']))


@bp.route('/<int:iid>/saida', methods=['POST'])
@login_obrigatorio
def saida(iid):
    f = request.form
    return _movimento(lambda db: est.saida(db, iid, f.get('qtd'), f.get('motivo'), f.get('obs'), g.usuario['usuario']))


@bp.route('/<int:iid>/ajuste', methods=['POST'])
@login_obrigatorio
def ajuste(iid):
    f = request.form
    return _movimento(lambda db: est.ajuste(db, iid, f.get('contagem'), f.get('obs'), g.usuario['usuario']))


@bp.route('/<int:iid>/historico')
@login_obrigatorio
def historico(iid):
    db = get_db()
    item = est.obter(db, iid)
    if item is None:
        abort(404)
    linhas, _totais = est.movimentos(db, item_id=iid)
    return render_template('estoque/historico.html', item=item, linhas=linhas, ultimos=est.ultimos_valores(db, iid),
                           situacao=est.situacao_de(item['saldo'], item['estoque_minimo']))


@bp.route('/movimentos')
@login_obrigatorio
def movimentos():
    db = get_db()
    de = _data_filtro(request.args.get('de', ''))
    ate = _data_filtro(request.args.get('ate', ''))
    item_id = request.args.get('item', type=int)
    tipo = request.args.get('tipo', '')
    linhas, totais = est.movimentos(db, de, ate, item_id, tipo)
    return render_template('estoque/movimentos.html', linhas=linhas, totais=totais, de=de, ate=ate, item_id=item_id, tipo=tipo,
                           itens=est.itens(db, incluir_inativos=True))


# ------------------------------------------------------------------ pedidos de compra
def _na(lista, i):
    return lista[i] if i < len(lista) else ''


def _itens_do_form(f):
    """Linhas do pedido enviadas em listas paralelas, uma por linha da tabela."""
    ids = f.getlist('item_id')
    return [{'item_id': ids[i], 'qtd': _na(f.getlist('qtd'), i), 'valor_unitario': _na(f.getlist('valor_unitario'), i),
             'obs': _na(f.getlist('item_obs'), i)} for i in range(len(ids))]


def _valor_txt(v):
    """Valor com vírgula decimal (2,50), como o formulário mostra."""
    return '' if v in (None, '') else ('%.2f' % float(v)).replace('.', ',')


def _linhas_do_banco(itens):
    return [{'item_id': i['item_id'], 'item_nome': i['item_nome'], 'unidade': i['unidade'] or '', 'qtd': est.qtd_txt(i['qtd']),
             'valor_unitario': _valor_txt(i['valor_unitario']), 'obs': i['obs'] or '', 'total': i['total'],
             'qtd_recebida': i['qtd_recebida']} for i in itens]


def _itens_estoque_js(db):
    return [{'id': i['id'], 'nome': i['nome'], 'unidade': i['unidade'] or '', 'valor': _valor_txt(i['ultimo_valor'])}
            for i in est.itens(db)]


def _pagina_pedido(db, atual, dados, linhas):
    editavel = atual is None or ep.editavel(db, atual)
    linhas_js = [{'item_id': str(l.get('item_id') or ''), 'nome': l.get('item_nome') or '', 'unidade': l.get('unidade') or '',
                  'qtd': l.get('qtd') or '', 'valor_unitario': l.get('valor_unitario') or '', 'obs': l.get('obs') or ''} for l in linhas]
    return render_template('estoque/pedido_form.html', pedido=atual, dados=dados, linhas=linhas, editavel=editavel,
                           etiqueta=ep.ETIQUETAS.get(atual['status'], '') if atual else '',
                           status_nome=ep.STATUS_NOMES.get(atual['status'], '') if atual else '',
                           fornecedores=fornecedores.listar(db, so_ativos=True), estoque_js=_itens_estoque_js(db),
                           linhas_js=linhas_js, solicitante_padrao=g.usuario['usuario'])


@bp.route('/pedidos')
@login_obrigatorio
def pedidos():
    db = get_db()
    status = request.args.get('status', '')
    return render_template('estoque/pedidos.html', pedidos=ep.listar(db, status), status=status, status_lista=ep.STATUS,
                           status_nomes=ep.STATUS_NOMES, etiquetas=ep.ETIQUETAS)


@bp.route('/pedidos/sugestoes')
@login_obrigatorio
def pedido_sugestoes():
    """Itens abaixo do mínimo, com a quantidade e o valor previsto (a tela põe no pedido)."""
    return jsonify(ep.sugerir_itens(get_db()))


@bp.route('/pedidos/novo', methods=['GET', 'POST'])
@login_obrigatorio
def pedido_novo():
    return _formulario_pedido(None)


@bp.route('/pedidos/<int:pid>', methods=['GET', 'POST'])
@login_obrigatorio
def pedido(pid):
    return _formulario_pedido(pid)


def _formulario_pedido(pid):
    db = get_db()
    atual = None
    if pid is not None:
        atual = ep.obter(db, pid)
        if atual is None:
            abort(404)
    if request.method == 'POST':
        f = request.form
        try:
            novo = ep.salvar(db, f, _itens_do_form(f), g.usuario['usuario'], pid)
        except est.ErroEstoque as e:
            db.rollback()
            flash(str(e), 'erro')
            if atual is not None and not ep.editavel(db, atual):   # não pode mais mudar: mostra o que está gravado
                return _pagina_pedido(db, atual, atual, _linhas_do_banco(ep.itens_do_pedido(db, pid)))
            return _pagina_pedido(db, atual, f, _itens_do_form(f))   # volta com o que foi digitado
        flash('Pedido salvo.', 'ok')
        return redirect(url_for('est.pedido', pid=novo))
    if atual is None:
        return _pagina_pedido(db, None, {}, [])
    return _pagina_pedido(db, atual, atual, _linhas_do_banco(ep.itens_do_pedido(db, pid)))


def _acao_pedido(pid, fazer, ok):
    db = get_db()
    try:
        fazer(db)
    except est.ErroEstoque as e:
        db.rollback()
        flash(str(e), 'erro')
    else:
        flash(ok, 'ok')
    return redirect(url_for('est.pedido', pid=pid))


@bp.route('/pedidos/<int:pid>/enviar', methods=['POST'])
@login_obrigatorio
def pedido_enviar(pid):
    return _acao_pedido(pid, lambda db: ep.marcar_enviado(db, pid), 'Pedido marcado como enviado.')


@bp.route('/pedidos/<int:pid>/cancelar', methods=['POST'])
@login_obrigatorio
def pedido_cancelar(pid):
    return _acao_pedido(pid, lambda db: ep.cancelar(db, pid), 'Pedido cancelado.')


@bp.route('/pedidos/<int:pid>/duplicar', methods=['POST'])
@login_obrigatorio
def pedido_duplicar(pid):
    db = get_db()
    try:
        novo = ep.duplicar(db, pid, g.usuario['usuario'])
    except est.ErroEstoque as e:
        db.rollback()
        flash(str(e), 'erro')
        return redirect(url_for('est.pedido', pid=pid))
    flash('Rascunho criado a partir do pedido. Confira e salve.', 'ok')
    return redirect(url_for('est.pedido', pid=novo))


def _pagina_receber(ped, itens, documento='', digitados=None):
    """Tela de recebimento: a quantidade e o valor pré-preenchidos (o que falta e o valor previsto), ou o que foi digitado."""
    digitados = digitados or {}
    linhas = []
    for i in itens:
        padrao = (est.qtd_txt(i['falta']) if i['falta'] > 0 else '', _valor_txt(i['valor_unitario']))
        qtd, valor = digitados.get(i['item_id'], padrao)
        linhas.append(dict(i, qtd_digitada=qtd, valor_digitado=valor))
    return render_template('estoque/pedido_receber.html', pedido=ped, linhas=linhas, documento=documento or '')


@bp.route('/pedidos/<int:pid>/receber', methods=['GET', 'POST'])
@login_obrigatorio
def pedido_receber(pid):
    db = get_db()
    ped = ep.obter(db, pid)
    if ped is None:
        abort(404)
    itens = ep.itens_do_pedido(db, pid)
    if request.method == 'POST':
        f = request.form
        ids = f.getlist('item_id')
        recebimentos = [(int(_na(ids, i)) if _na(ids, i).isdigit() else None, _na(f.getlist('qtd'), i),
                         _na(f.getlist('valor_unitario'), i)) for i in range(len(ids))]
        try:
            feitos = ep.receber(db, pid, recebimentos, f.get('documento'), g.usuario['usuario'])
        except est.ErroEstoque as e:
            db.rollback()
            flash(str(e), 'erro')
            digitados = {r[0]: (r[1], r[2]) for r in recebimentos if r[0] is not None}
            return _pagina_receber(ped, itens, f.get('documento'), digitados)
        flash('Recebimento registrado: %d item(ns) lançado(s) no estoque.' % feitos, 'ok')
        return redirect(url_for('est.pedido', pid=pid))
    return _pagina_receber(ped, itens)


def _pedido_ou_404(db, pid):
    ped, itens = ep.completo(db, pid)
    if ped is None:
        abort(404)
    return ped, itens


@bp.route('/pedidos/<int:pid>.pdf')
@login_obrigatorio
def pedido_pdf(pid):
    ped, itens = _pedido_ou_404(get_db(), pid)
    pdf = estoque_docs.pedido_pdf(ped, itens, config_get('clinica_nome', '') or '', g.usuario['usuario'])
    return send_file(io.BytesIO(pdf), mimetype='application/pdf', as_attachment=request.args.get('baixar') == '1',
                     download_name='pedido_%s.pdf' % ped['numero'])


@bp.route('/pedidos/<int:pid>/imprimir')
@login_obrigatorio
def pedido_imprimir(pid):
    ped, itens = _pedido_ou_404(get_db(), pid)
    return render_template('estoque/pedido_impressao.html', pedido=ped, itens=itens,
                           status_nome=ep.STATUS_NOMES.get(ped['status'], ped['status']))


# ------------------------------------------------------------------ relatórios, escrituração e preços
def _arquivo(conteudo, nome, tipo):
    """PDF abre no navegador (ou baixa com ?baixar=1); Excel sempre baixa."""
    mime = 'application/pdf' if tipo == 'pdf' else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    baixar = tipo != 'pdf' or request.args.get('baixar') == '1'
    return send_file(io.BytesIO(conteudo), mimetype=mime, as_attachment=baixar, download_name='%s.%s' % (nome, tipo))


def _empresa():
    return config_get('clinica_nome', '') or ''


def _periodo_txt(de, ate):
    return ('Período de %s a %s' % (_data_br(de) or 'o início', _data_br(ate) or 'hoje')) if (de or ate) else ''


def _data_br(iso):
    return '%s/%s/%s' % (iso[8:10], iso[5:7], iso[:4]) if iso else ''


def _filtros_relatorio():
    """De/Até: sem parâmetro, o mês atual; se o campo foi enviado vazio, sem limite."""
    a = request.args
    hoje = date.today()
    de = _data_filtro(a.get('de')) if 'de' in a else hoje.replace(day=1).isoformat()
    ate = _data_filtro(a.get('ate')) if 'ate' in a else hoje.isoformat()
    return de, ate, a.get('tipo', '')


@bp.route('/relatorios')
@login_obrigatorio
def relatorios():
    de, ate, tipo = _filtros_relatorio()
    rel = er.relatorio(get_db(), de, ate, tipo)
    return render_template('estoque/relatorios.html', rel=rel, tipos=est.TIPOS, motivos=est.MOTIVOS_SAIDA, dias=er.DIAS_VALIDADE)


@bp.route('/relatorios.pdf')
@login_obrigatorio
def relatorios_pdf():
    de, ate, tipo = _filtros_relatorio()
    rel = er.relatorio(get_db(), de, ate, tipo)
    return _arquivo(estoque_docs.relatorios_pdf(rel, _empresa(), g.usuario['usuario']), 'relatorios_estoque', 'pdf')


@bp.route('/relatorios.xlsx')
@login_obrigatorio
def relatorios_xlsx():
    de, ate, tipo = _filtros_relatorio()
    rel = er.relatorio(get_db(), de, ate, tipo)
    return _arquivo(estoque_docs.relatorios_xlsx(rel, _empresa()), 'relatorios_estoque', 'xlsx')


def _escrituracao_dados(db):
    de, ate, tipo = _filtros_relatorio()
    item_id = request.args.get('item', type=int)
    blocos = er.escrituracao(db, de, ate, item_id or None, tipo)
    return de, ate, tipo, item_id, blocos


@bp.route('/escrituracao')
@login_obrigatorio
def escrituracao():
    db = get_db()
    de, ate, tipo, item_id, blocos = _escrituracao_dados(db)
    return render_template('estoque/escrituracao.html', blocos=blocos, de=de, ate=ate, tipo=tipo, item_id=item_id, tipos=est.TIPOS,
                           itens=est.itens(db, incluir_inativos=True))


@bp.route('/escrituracao.pdf')
@login_obrigatorio
def escrituracao_pdf():
    de, ate, _tipo, _item, blocos = _escrituracao_dados(get_db())
    pdf = estoque_docs.escrituracao_pdf(blocos, _empresa(), de, ate, g.usuario['usuario'])
    return _arquivo(pdf, 'escrituracao_estoque', 'pdf')


@bp.route('/escrituracao.xlsx')
@login_obrigatorio
def escrituracao_xlsx():
    de, ate, _tipo, _item, blocos = _escrituracao_dados(get_db())
    return _arquivo(estoque_docs.escrituracao_xlsx(blocos, _empresa(), de, ate), 'escrituracao_estoque', 'xlsx')


def _precos_dados(db):
    a = request.args
    de = _data_filtro(a.get('de'))
    ate = _data_filtro(a.get('ate'))
    item_id = a.get('item', type=int)
    forn = a.get('fornecedor', '')
    return de, ate, item_id, forn, er.estudo(db, de, ate, item_id or None, forn)


@bp.route('/precos')
@login_obrigatorio
def precos():
    db = get_db()
    de, ate, item_id, forn, estudo = _precos_dados(db)
    detalhe = estudo[0] if item_id and estudo else None
    cadastrados, avulsos = er.fornecedores_com_entrada(db)
    return render_template('estoque/precos.html', estudo=estudo, detalhe=detalhe, grafico=er.grafico(detalhe['historico']) if detalhe else None,
                           de=de, ate=ate, item_id=item_id, fornecedor=forn, itens=est.itens(db, incluir_inativos=True),
                           cadastrados=cadastrados, avulsos=avulsos, ao_abrir=bool(item_id))


@bp.route('/precos.pdf')
@login_obrigatorio
def precos_pdf():
    de, ate, _item, _forn, estudo = _precos_dados(get_db())
    pdf = estoque_docs.precos_pdf(estudo, _empresa(), _periodo_txt(de, ate), g.usuario['usuario'])
    return _arquivo(pdf, 'estudo_precos_estoque', 'pdf')


@bp.route('/precos.xlsx')
@login_obrigatorio
def precos_xlsx():
    de, ate, _item, _forn, estudo = _precos_dados(get_db())
    return _arquivo(estoque_docs.precos_xlsx(estudo, _empresa(), _periodo_txt(de, ate)), 'estudo_precos_estoque', 'xlsx')
