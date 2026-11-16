"""Mapa de laudos: quadro com a situação de cada exame após o atendimento."""
from datetime import date, datetime, timedelta

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from . import laudos, login_obrigatorio, prazo_laudo, util
from .db import get_db

bp = Blueprint('laudo', __name__, url_prefix='/laudos')


def _perm():
    return laudos.permissoes(g.usuario, g.modulos)


@bp.route('')
@login_obrigatorio
def quadro():
    hoje = date.today()
    de = util.para_data(request.args.get('de')) or hoje - timedelta(days=6)
    ate = util.para_data(request.args.get('ate')) or hoje
    if ate < de:
        de, ate = ate, de
    q = laudos.quadro(get_db(), de.isoformat(), ate.isoformat())
    perm = _perm()
    if perm is not None:   # usuário restrito só vê as situações liberadas pela gerência
        q['colunas'] = [c for c in q['colunas'] if c[0] in perm['ver']]
        q['total'] = sum(len(c[2]) for c in q['colunas'])
    destaque = request.args.get('destaque', type=int)  # laudo recém-entregue pelo aviso: a tela rola até ele e o anima
    cfg = prazo_laudo.atuais()
    for _, _, itens in q['colunas']:   # previsão de entrega de cada exame, com o prazo vigente
        for r in itens:
            r['previsao'] = prazo_laudo.previsao(date.fromisoformat(r['data']), cfg).isoformat() if r.get('data') else ''
    return render_template('laudos.html', q=q, de=de.isoformat(), ate=ate.isoformat(), situacoes=laudos.SITUACOES,
                           dias=laudos.DIAS_MENSAGEM, destaque=destaque, hoje=hoje.isoformat(), prazo=cfg, perm=perm, proximas={c: laudos.proxima(c) for c in laudos.CHAVES}, agora_local=datetime.now().strftime('%Y-%m-%dT%H:%M'),
                           prazo_tipos=prazo_laudo.TIPOS, prazo_texto=prazo_laudo.descricao(cfg),
                           pode_prazo=bool(g.usuario['admin']) or 'gerencia' in g.modulos)


@bp.route('/prazo', methods=['POST'])
@login_obrigatorio
def prazo():
    erro = prazo_laudo.salvar(request.form)
    flash(erro or 'Prazo de entrega dos laudos atualizado: %s.' % prazo_laudo.descricao(), 'erro' if erro else 'ok')
    return redirect(url_for('laudo.quadro'))


@bp.route('/<int:rid>/entregar', methods=['POST'])
@login_obrigatorio
def entregar(rid):
    """Botão da mensagem de aviso: marca como entregue e leva ao laudo no mapa."""
    try:
        texto, data_exame = laudos.entregar(get_db(), rid, g.usuario['usuario'], _perm())
    except laudos.ErroLaudo as e:
        flash(str(e), 'erro')
        return redirect(url_for('laudo.quadro'))
    flash(texto, 'ok')
    hoje = date.today()
    de = min(util.para_data(data_exame) or hoje, hoje - timedelta(days=6))
    return redirect(url_for('laudo.quadro', de=de.isoformat(), ate=hoje.isoformat(), destaque=rid) + '#laudo-%d' % rid)


@bp.route('/<int:rid>/situacao', methods=['POST'])
@login_obrigatorio
def situacao(rid):
    try:
        rotulo = laudos.mudar(get_db(), rid, request.form.get('situacao', ''), g.usuario['usuario'],
                              liberado_em_informado=request.form.get('liberado_em'), perm=_perm())
        flash('Situação do laudo: %s.' % rotulo, 'ok')
    except laudos.ErroLaudo as e:
        flash(str(e), 'erro')
    return redirect(request.form.get('voltar') or url_for('laudo.quadro'))


@bp.route('/limpar', methods=['POST'])
@login_obrigatorio
def limpar():
    """Tira do mapa os laudos entregues do período mostrado; eles seguem na página Laudos entregues."""
    de = util.para_data(request.form.get('de')) or date.today() - timedelta(days=6)
    ate = util.para_data(request.form.get('ate')) or date.today()
    n = laudos.arquivar_entregues(get_db(), min(de, ate).isoformat(), max(de, ate).isoformat(), g.usuario['usuario'])
    flash('%d laudo(s) entregue(s) saíram do mapa e estão em Laudos entregues.' % n if n else 'Não há laudos entregues neste período para limpar.',
          'ok' if n else 'aviso')
    return redirect(url_for('laudo.quadro', de=de.isoformat(), ate=ate.isoformat()))


@bp.route('/entregues')
@login_obrigatorio
def entregues():
    hoje = date.today()
    de = util.para_data(request.args.get('de')) or hoje - timedelta(days=29)
    ate = util.para_data(request.args.get('ate')) or hoje
    if ate < de:
        de, ate = ate, de
    busca = (request.args.get('q') or '').strip()
    itens = laudos.entregues(get_db(), de.isoformat(), ate.isoformat(), busca)
    return render_template('laudos_entregues.html', itens=itens, de=de.isoformat(), ate=ate.isoformat(), q=busca,
                           n_retificados=sum(1 for i in itens if i['laudo_retificado_em']))


@bp.route('/<int:rid>/retificar', methods=['POST'])
@login_obrigatorio
def retificar(rid):
    db = get_db()
    try:
        if request.form.get('desfazer'):
            laudos.desfazer_retificacao(db, rid)
            flash('Retificação removida.', 'ok')
        else:
            nome = laudos.retificar(db, rid, request.form.get('motivo'), g.usuario['usuario'])
            flash('Laudo de %s marcado como retificado (entra no indicador da ONA).' % nome, 'ok')
    except laudos.ErroLaudo as e:
        flash(str(e), 'erro')
    return redirect(request.form.get('voltar') or url_for('laudo.entregues'))
