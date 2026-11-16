"""Tabela de preços dos exames: lista, edição da grade, ferramentas, PDF para imprimir e busca para as guias SADT."""
import io

from flask import Blueprint, abort, flash, g, jsonify, redirect, render_template, request, send_file, url_for

from . import login_obrigatorio, tabela_precos as tp, tabela_precos_docs as tdocs
from .db import config_get, get_db

bp = Blueprint('preco', __name__)


def _itens_do_formulario(form):
    """Lista de itens a partir das listas paralelas codigo[], descricao[], valor[], obs[] e exame_id[]."""
    cols = {c: form.getlist(c + '[]') for c in ('codigo', 'descricao', 'valor', 'obs', 'exame_id')}
    n = max(len(v) for v in cols.values())
    return [{c: (cols[c][i] if i < len(cols[c]) else '') for c in cols} for i in range(n)]


def _dados_do_formulario(form):
    return {'nome': form.get('nome', ''), 'vigencia': form.get('vigencia', ''), 'obs': form.get('obs', ''),
            'ativa': '1' if form.get('ativa') == '1' else '0'}


def _tela_edicao(tabela, itens, tid, erro=None):
    db = get_db()
    return render_template('precos_editar.html', tabela=tabela, itens=itens, tid=tid, exames=db.execute(
        'SELECT id, nome FROM exames WHERE ativo=1 ORDER BY ordem, nome').fetchall(),
        convenios=db.execute('SELECT id, nome FROM convenios WHERE ativo=1 ORDER BY nome').fetchall(), erro=erro)


@bp.route('/precos')
@login_obrigatorio
def lista():
    return render_template('precos_lista.html', rows=tp.listar(get_db()))


@bp.route('/precos/consulta')
@login_obrigatorio
def consulta():
    q = (request.args.get('q') or '').strip()
    dados = tp.consulta_rapida(get_db(), q)
    return render_template(
        'precos_consulta.html',
        q=q,
        itens=dados['itens'],
        rows=dados['itens'],
        tabelas=dados['tabelas'],
        convenios=dados['convenios'],
        total=dados['total'],
    )


@bp.route('/precos/consulta.json')
@login_obrigatorio
def consulta_json():
    q = (request.args.get('q') or '').strip()
    return jsonify(tp.consulta_rapida(get_db(), q)['itens'])


@bp.route('/precos/nova', methods=['GET', 'POST'], defaults={'tid': None})
@bp.route('/precos/<int:tid>', methods=['GET', 'POST'])
@login_obrigatorio
def editar(tid):
    db = get_db()
    if request.method == 'POST':
        try:
            tid = tp.salvar_tabela(db, _dados_do_formulario(request.form), g.usuario['usuario'], tid)
            tp.salvar_itens(db, tid, _itens_do_formulario(request.form))
            db.commit()
        except tp.ErroTabela as e:
            db.rollback()
            # mantém o que foi digitado para corrigir sem perder nada
            tabela = _dados_do_formulario(request.form)
            tabela['ativa'] = tabela['ativa'] == '1'
            return _tela_edicao(tabela, _itens_do_formulario(request.form), tid, erro=str(e)), 400
        flash('Tabela de preços salva.', 'ok')
        return redirect(url_for('preco.editar', tid=tid))
    if tid is None:
        return _tela_edicao({'nome': '', 'vigencia': '', 'obs': '', 'ativa': True}, [], None)
    obtido = tp.obter(db, tid)
    if not obtido:
        abort(404)
    tabela, itens = obtido
    return _tela_edicao(tabela, itens, tid)


@bp.route('/precos/<int:tid>/acao', methods=['POST'])
@login_obrigatorio
def acao(tid):
    db = get_db()
    if not tp.obter(db, tid):
        abort(404)
    acao_pedida = request.form.get('acao')
    usuario = g.usuario['usuario']
    try:
        if acao_pedida == 'exames':
            n = tp.adicionar_exames(db, tid)
            msg = ('%d exame(s) cadastrado(s) acrescentado(s) sem valor.' % n) if n else 'Todos os exames cadastrados já estão na tabela.'
        elif acao_pedida == 'convenio':
            cid = int(request.form.get('convenio_id') or 0)
            n = tp.copiar_convenio(db, tid, cid)
            msg = ('%d valor(es) copiado(s) do convênio.' % n) if n else 'O convênio não tem valores preenchidos.'
        elif acao_pedida == 'reajuste':
            n = tp.reajustar(db, tid, request.form.get('percentual'), request.form.get('arredondar', ''))
            msg = '%d valor(es) reajustado(s).' % n
        elif acao_pedida == 'duplicar':
            nid = tp.duplicar(db, tid, request.form.get('nome', ''), usuario)
            db.commit()
            flash('Tabela duplicada. Preencha a vigência e ajuste os valores.', 'ok')
            return redirect(url_for('preco.editar', tid=nid))
        elif acao_pedida == 'excluir':
            tp.excluir(db, tid)
            db.commit()
            flash('Tabela de preços excluída.', 'ok')
            return redirect(url_for('preco.lista'))
        else:
            flash('Ação desconhecida.', 'erro')
            return redirect(url_for('preco.editar', tid=tid))
        db.commit()
        flash(msg + ' Salve a tabela para confirmar a grade.' if acao_pedida in ('exames', 'convenio', 'reajuste') else msg, 'ok')
    except (tp.ErroTabela, ValueError) as e:
        db.rollback()
        flash(str(e) or 'Não foi possível concluir a ação.', 'erro')
    return redirect(url_for('preco.editar', tid=tid))


@bp.route('/precos/<int:tid>/pdf')
@login_obrigatorio
def pdf(tid):
    obtido = tp.obter(get_db(), tid)
    if not obtido:
        abort(404)
    tabela, itens = obtido
    dados = tdocs.tabela_pdf(tabela, itens, config_get('clinica_nome', '') or '', config_get('clinica_cnpj', '') or '')
    return send_file(io.BytesIO(dados), mimetype='application/pdf', as_attachment=request.args.get('baixar') == '1',
                     download_name='tabela-de-precos-%d.pdf' % tid)


@bp.route('/precos/itens.json')
@login_obrigatorio
def itens_json():
    return jsonify(tp.buscar_itens(get_db(), request.args.get('q', '')))
