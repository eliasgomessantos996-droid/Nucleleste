"""Telas da Qualidade: central, indicadores (KPI), robô do PDCA, problemas e PDCA, Pareto, Ishikawa, 5 Porquês, GUT,
matriz de risco, plano 5W2H, SWOT, fluxogramas, organograma, ocorrências/satisfação e avaliação de fornecedores (ONA)."""
import io
from datetime import date, timedelta

from urllib.parse import quote

from flask import Blueprint, Response, abort, current_app, flash, g, jsonify, redirect, render_template, request, send_file, url_for

from . import login_obrigatorio
from . import pesquisa as pesq
from . import pesquisa_docs as pdocs
from . import qualidade as q
from . import qualidade_aplicar as aplicar
from . import qualidade_pops as pops
from . import qualidade_protocolos as prot
from . import qualidade_dados as qd
from . import qualidade_epidemio as epi
from . import qualidade_docs as docs
from . import qualidade_modelos as modelos
from . import qualidade_robo as robo
from .db import config_get, get_db

bp = Blueprint('qual', __name__, url_prefix='/qualidade')


@bp.app_template_global()
def fmt_kpi(valor, unidade):
    """Valor de indicador para a tela: 92,5% · 18,3 h · 8,7 · 3."""
    if valor is None:
        return '—'
    if unidade == '%':
        return ('%.1f%%' % valor).replace('.', ',')
    if unidade == 'h':
        return ('%.1f h' % valor).replace('.', ',')
    if unidade == 'nota':
        return ('%.1f' % valor).replace('.', ',')
    return ('%g' % valor).replace('.', ',')


@bp.before_request
def _tabelas():
    q.garantir(get_db())


def _usuario():
    return g.usuario['usuario']


def _empresa():
    return config_get('clinica_nome') or 'Nucleleste'


def _periodo(padrao_dias=30):
    hoje = date.today()
    try:
        ate = date.fromisoformat(request.args.get('ate') or '')
    except ValueError:
        ate = hoje
    try:
        de = date.fromisoformat(request.args.get('de') or '')
    except ValueError:
        de = ate - timedelta(days=padrao_dias - 1)
    if de > ate:
        de, ate = ate, de
    if (ate - de).days > 3660:
        de = ate - timedelta(days=3660)
    return de, ate


def _arquivo(conteudo, nome, tipo):
    """PDF abre no navegador (ou baixa com ?baixar=1); Excel sempre baixa."""
    mime = 'application/pdf' if tipo == 'pdf' else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    baixar = tipo != 'pdf' or request.args.get('baixar') == '1'
    return send_file(io.BytesIO(conteudo), mimetype=mime, as_attachment=baixar, download_name='%s.%s' % (nome, tipo))


def _voltar(endpoint, **kw):
    destino = request.form.get('voltar') or ''
    if destino.startswith('/qualidade'):
        return redirect(destino)
    return redirect(url_for(endpoint, **kw))


def _erro(e, endpoint, **kw):
    flash(str(e), 'erro')
    return _voltar(endpoint, **kw)


# ------------------------------------------------------------------ central
@bp.route('')
@login_obrigatorio
def central():
    db = get_db()
    de, ate = date.today() - timedelta(days=29), date.today()
    from . import cache_curto
    from .anexos import caminho_do_banco
    plano, _ = cache_curto.obter(('central', caminho_do_banco(db), de.isoformat(), ate.isoformat(), qd._marca(db)),
                                 lambda: qd.coletar(db, de, ate), 60)
    metas = q.metas(db)
    criticos = [c for c in qd.DEFINICOES if plano.get(c[0]) is not None and qd._situacao(plano[c[0]], *metas[c[0]]) == 'critico']
    probs = q.problemas(db)
    return render_template('qualidade/central.html', criticos=criticos, plano=plano,
                           rascunhos=sum(1 for p in probs if p['status'] == robo.RASCUNHO),
                           abertos=sum(1 for p in probs if p['status'] in ('ABERTO', 'EM ANDAMENTO')),
                           acoes_atrasadas=sum(1 for a in q.acoes(db) if a['atrasada']), ultima=robo.ultima_execucao(db))


# ------------------------------------------------------------------ indicadores (KPI)
@bp.route('/indicadores')
@login_obrigatorio
def kpi():
    de, ate = _periodo()
    painel = qd.painel(get_db(), de, ate)
    return render_template('qualidade/kpi.html', painel=painel, de=de.isoformat(), ate=ate.isoformat())


@bp.route('/indicadores/metas', methods=['POST'])
@login_obrigatorio
def kpi_metas():
    try:
        q.salvar_metas(get_db(), request.form, _usuario())
    except q.ErroQualidade as e:
        return _erro(e, 'qual.kpi')
    flash('Metas gravadas.', 'ok')
    return _voltar('qual.kpi')


@bp.route('/indicadores.<tipo>')
@login_obrigatorio
def kpi_arquivo(tipo):
    if tipo not in ('pdf', 'xlsx'):
        abort(404)
    de, ate = _periodo()
    painel = qd.painel(get_db(), de, ate)
    conteudo = docs.kpi_pdf(painel, _empresa(), _usuario()) if tipo == 'pdf' else docs.kpi_xlsx(painel, _empresa())
    return _arquivo(conteudo, 'Indicadores da qualidade', tipo)


# ------------------------------------------------------------------ robô do PDCA
@bp.route('/robo')
@login_obrigatorio
def robo_pagina():
    db = get_db()
    rasc = [p for p in q.problemas(db) if p['status'] == robo.RASCUNHO]
    return render_template('qualidade/robo.html', ultima=robo.ultima_execucao(db), rascunhos=rasc,
                           de=(date.today() - timedelta(days=29)).isoformat(), ate=date.today().isoformat())


@bp.route('/robo/analisar', methods=['POST'])
@login_obrigatorio
def robo_analisar():
    try:
        de = date.fromisoformat(request.form.get('de') or '')
        ate = date.fromisoformat(request.form.get('ate') or '')
    except ValueError:
        de, ate = date.today() - timedelta(days=29), date.today()
    r = robo.analisar(get_db(), min(de, ate), max(de, ate), usuario=_usuario())
    flash('Análise concluída: %d problema(s) encontrado(s), %d novo(s) para revisar.' % (len(r['achados']), r['novos']), 'ok')
    return redirect(url_for('qual.robo_pagina'))


@bp.route('/robo/<int:pid>/aceitar', methods=['POST'])
@login_obrigatorio
def robo_aceitar(pid):
    try:
        robo.aceitar(get_db(), pid, _usuario())
    except q.ErroQualidade as e:
        return _erro(e, 'qual.robo_pagina')
    flash('Plano aceito: o problema está aberto no Ciclo PDCA.', 'ok')
    return redirect(url_for('qual.problema_pagina', pid=pid))


@bp.route('/robo/<int:pid>/descartar', methods=['POST'])
@login_obrigatorio
def robo_descartar(pid):
    try:
        robo.descartar(get_db(), pid, _usuario())
    except q.ErroQualidade as e:
        return _erro(e, 'qual.robo_pagina')
    flash('Sugestão descartada. O robô não vai sugerir o mesmo problema pelos próximos %d dias.' % robo.DIAS_DESCARTE, 'ok')
    return redirect(url_for('qual.robo_pagina'))


# ------------------------------------------------------------------ problemas e PDCA
@bp.route('/pdca')
@login_obrigatorio
def pdca():
    db = get_db()
    status = request.args.get('status') if request.args.get('status') in q.STATUS_PROBLEMA else ''
    return render_template('qualidade/pdca.html', problemas=q.problemas(db, status or None), status=status, statuses=q.STATUS_PROBLEMA,
                           fases=q.FASES_PDCA, modelos=aplicar.galeria_problemas())


@bp.route('/pdca/novo', methods=['POST'])
@login_obrigatorio
def problema_novo():
    try:
        pid = q.criar_problema(get_db(), request.form, _usuario())
    except q.ErroQualidade as e:
        return _erro(e, 'qual.pdca')
    flash('Problema aberto. Agora analise as causas e monte o plano.', 'ok')
    return redirect(url_for('qual.problema_pagina', pid=pid))


@bp.route('/pdca/<int:pid>')
@login_obrigatorio
def problema_pagina(pid):
    db = get_db()
    try:
        p = q.problema(db, pid)
    except q.ErroQualidade:
        abort(404)
    return render_template('qualidade/problema.html', p=p, isk=q.ishikawa(db, pid), seis_m=q.SEIS_M, statuses=q.STATUS_PROBLEMA,
                           fases=q.FASES_PDCA, status_acao=q.STATUS_ACAO, hoje=date.today().isoformat())


@bp.route('/pdca/<int:pid>/salvar', methods=['POST'])
@login_obrigatorio
def problema_salvar(pid):
    try:
        q.salvar_problema(get_db(), pid, request.form, _usuario())
    except q.ErroQualidade as e:
        return _erro(e, 'qual.problema_pagina', pid=pid)
    flash('Problema salvo.', 'ok')
    return _voltar('qual.problema_pagina', pid=pid)


@bp.route('/pdca/<int:pid>/excluir', methods=['POST'])
@login_obrigatorio
def problema_excluir(pid):
    q.excluir_problema(get_db(), pid)
    flash('Problema excluído.', 'ok')
    return redirect(url_for('qual.pdca'))


@bp.route('/pdca/<int:pid>.pdf')
@login_obrigatorio
def problema_pdf(pid):
    db = get_db()
    try:
        p = q.problema(db, pid)
    except q.ErroQualidade:
        abort(404)
    return _arquivo(docs.problema_pdf(p, q.ishikawa(db, pid), _empresa(), _usuario()), 'PDCA %d' % pid, 'pdf')


@bp.route('/pdca/<int:pid>/causas', methods=['POST'])
@login_obrigatorio
def causa_nova(pid):
    try:
        q.adicionar_causa(get_db(), pid, request.form)
    except q.ErroQualidade as e:
        return _erro(e, 'qual.problema_pagina', pid=pid)
    return _voltar('qual.problema_pagina', pid=pid)


@bp.route('/causas/<int:cid>/principal', methods=['POST'])
@login_obrigatorio
def causa_principal(cid):
    db = get_db()
    q.alternar_causa_principal(db, cid)
    r = db.execute('SELECT problema_id FROM cq_causas WHERE id=?', (cid,)).fetchone()
    return _voltar('qual.problema_pagina', pid=r['problema_id'] if r else 0)


@bp.route('/causas/<int:cid>/excluir', methods=['POST'])
@login_obrigatorio
def causa_excluir(cid):
    pid = q.excluir_causa(get_db(), cid)
    return _voltar('qual.problema_pagina', pid=pid or 0)


@bp.route('/pdca/<int:pid>/porques', methods=['POST'])
@login_obrigatorio
def porques_salvar(pid):
    try:
        q.salvar_porques(get_db(), pid, request.form)
    except q.ErroQualidade as e:
        return _erro(e, 'qual.problema_pagina', pid=pid)
    flash('Cinco porquês salvos.', 'ok')
    return _voltar('qual.problema_pagina', pid=pid)


@bp.route('/pdca/<int:pid>/gut', methods=['POST'])
@login_obrigatorio
def gut_salvar(pid):
    try:
        q.salvar_gut(get_db(), pid, request.form, _usuario())
    except q.ErroQualidade as e:
        return _erro(e, 'qual.gut')
    return _voltar('qual.gut')


@bp.route('/acoes', methods=['POST'])
@login_obrigatorio
def acao_nova():
    pid = request.form.get('problema_id')
    pid = int(pid) if pid and pid.isdigit() else None
    try:
        q.adicionar_acao(get_db(), pid, request.form, _usuario())
    except q.ErroQualidade as e:
        return _erro(e, 'qual.plano')
    flash('Ação incluída no plano.', 'ok')
    return _voltar('qual.plano')


@bp.route('/acoes/<int:aid>/salvar', methods=['POST'])
@login_obrigatorio
def acao_salvar(aid):
    try:
        q.salvar_acao(get_db(), aid, request.form)
    except q.ErroQualidade as e:
        return _erro(e, 'qual.plano')
    flash('Ação salva.', 'ok')
    return _voltar('qual.plano')


@bp.route('/acoes/<int:aid>/excluir', methods=['POST'])
@login_obrigatorio
def acao_excluir(aid):
    q.excluir_acao(get_db(), aid)
    return _voltar('qual.plano')


# ------------------------------------------------------------------ ferramentas ligadas aos problemas
def _escolher_problema(db):
    lista = [p for p in q.problemas(db) if p['status'] != 'DESCARTADO']
    pid = request.args.get('p', type=int) or (lista[0]['id'] if lista else None)
    return lista, pid


@bp.route('/ishikawa')
@login_obrigatorio
def ishikawa():
    db = get_db()
    lista, pid = _escolher_problema(db)
    isk = q.ishikawa(db, pid) if pid and any(p['id'] == pid for p in lista) else None
    return render_template('qualidade/ishikawa.html', problemas=lista, pid=pid, isk=isk, seis_m=q.SEIS_M, modelos=aplicar.galeria_problemas())


@bp.route('/porques')
@login_obrigatorio
def porques():
    db = get_db()
    lista, pid = _escolher_problema(db)
    p = q.problema(db, pid) if pid and any(x['id'] == pid for x in lista) else None
    return render_template('qualidade/porques.html', problemas=lista, pid=pid, p=p, modelos=aplicar.galeria_problemas())


@bp.route('/gut')
@login_obrigatorio
def gut():
    return render_template('qualidade/gut.html', lista=q.ranking_gut(get_db()), modelos=aplicar.galeria_problemas())


@bp.route('/gut.pdf')
@login_obrigatorio
def gut_pdf():
    return _arquivo(docs.gut_pdf(q.ranking_gut(get_db()), _empresa(), _usuario()), 'Matriz GUT', 'pdf')


@bp.route('/plano')
@login_obrigatorio
def plano():
    db = get_db()
    status = request.args.get('status') if request.args.get('status') in q.STATUS_ACAO else ''
    lista = q.acoes(db, status=status or None)
    if request.args.get('atrasadas'):
        lista = [a for a in lista if a['atrasada']]
    return render_template('qualidade/plano.html', acoes=lista, status=status, status_acao=q.STATUS_ACAO, modelos=aplicar.galeria_planos(),
                           problemas=[p for p in q.problemas(db) if p['status'] not in ('DESCARTADO', 'CONCLUÍDO')])


@bp.route('/plano.<tipo>')
@login_obrigatorio
def plano_arquivo(tipo):
    if tipo not in ('pdf', 'xlsx'):
        abort(404)
    lista = q.acoes(get_db())
    conteudo = docs.plano_pdf(lista, _empresa(), _usuario()) if tipo == 'pdf' else docs.plano_xlsx(lista, _empresa())
    return _arquivo(conteudo, 'Plano de acao 5W2H', tipo)


# ------------------------------------------------------------------ Pareto
@bp.route('/pareto')
@login_obrigatorio
def pareto():
    db = get_db()
    de, ate = _periodo(90)
    fonte = request.args.get('fonte') if request.args.get('fonte') in dict(qd.FONTES_PARETO) else qd.FONTES_PARETO[0][0]
    p = qd.pareto(db, fonte, de, ate)
    pendentes = qd.faltas_sem_motivo(db, de, ate) if fonte == 'faltas_motivo' else []
    return render_template('qualidade/pareto.html', p=p, fontes=qd.FONTES_PARETO, fonte=fonte, de=de.isoformat(), ate=ate.isoformat(),
                           pendentes=pendentes, motivos=q.MOTIVOS_FALTA)


@bp.route('/pareto.<tipo>')
@login_obrigatorio
def pareto_arquivo(tipo):
    if tipo not in ('pdf', 'xlsx'):
        abort(404)
    de, ate = _periodo(90)
    fonte = request.args.get('fonte') if request.args.get('fonte') in dict(qd.FONTES_PARETO) else qd.FONTES_PARETO[0][0]
    p = qd.pareto(get_db(), fonte, de, ate)
    conteudo = docs.pareto_pdf(p, _empresa(), _usuario()) if tipo == 'pdf' else docs.pareto_xlsx(p, _empresa())
    return _arquivo(conteudo, 'Pareto', tipo)


@bp.route('/faltas/<int:hid>/motivo', methods=['POST'])
@login_obrigatorio
def falta_motivo(hid):
    try:
        q.registrar_motivo_falta(get_db(), hid, request.form.get('motivo') or '', _usuario())
    except q.ErroQualidade as e:
        return _erro(e, 'qual.pareto', fonte='faltas_motivo')
    return _voltar('qual.pareto', fonte='faltas_motivo')


# ------------------------------------------------------------------ matriz de risco
@bp.route('/riscos')
@login_obrigatorio
def riscos():
    db = get_db()
    lista = q.riscos(db)
    editar = None
    if request.args.get('editar', type=int):
        editar = next((r for r in lista if r['id'] == request.args.get('editar', type=int)), None)
    return render_template('qualidade/riscos.html', lista=lista, grade=q.matriz_risco(lista), editar=editar, respostas=q.RESPOSTAS_RISCO,
                           modelos=aplicar.galeria_riscos())


@bp.route('/riscos/salvar', methods=['POST'])
@login_obrigatorio
def risco_salvar():
    rid = request.form.get('id')
    try:
        q.salvar_risco(get_db(), request.form, _usuario(), int(rid) if rid and rid.isdigit() else None)
    except q.ErroQualidade as e:
        return _erro(e, 'qual.riscos')
    flash('Risco salvo.', 'ok')
    return redirect(url_for('qual.riscos'))


@bp.route('/riscos/<int:rid>/excluir', methods=['POST'])
@login_obrigatorio
def risco_excluir(rid):
    q.excluir_risco(get_db(), rid)
    return redirect(url_for('qual.riscos'))


@bp.route('/riscos.<tipo>')
@login_obrigatorio
def riscos_arquivo(tipo):
    if tipo not in ('pdf', 'xlsx'):
        abort(404)
    lista = q.riscos(get_db())
    conteudo = docs.riscos_pdf(lista, _empresa(), _usuario()) if tipo == 'pdf' else docs.riscos_xlsx(lista, _empresa())
    return _arquivo(conteudo, 'Matriz de risco', tipo)


# ------------------------------------------------------------------ SWOT
@bp.route('/swot')
@login_obrigatorio
def swot():
    db = get_db()
    analises = q.swot_analises(db)
    aid = request.args.get('a', type=int) or (analises[0]['id'] if analises else None)
    s = q.swot(db, aid) if aid and any(a['id'] == aid for a in analises) else None
    return render_template('qualidade/swot.html', analises=analises, aid=aid, s=s, quadrantes=q.QUADRANTES_SWOT, modelos=aplicar.galeria_swot())


@bp.route('/swot/nova', methods=['POST'])
@login_obrigatorio
def swot_nova():
    try:
        aid = q.criar_swot(get_db(), request.form, _usuario())
    except q.ErroQualidade as e:
        return _erro(e, 'qual.swot')
    return redirect(url_for('qual.swot', a=aid))


@bp.route('/swot/<int:aid>/item', methods=['POST'])
@login_obrigatorio
def swot_item(aid):
    try:
        q.adicionar_swot_item(get_db(), aid, request.form)
    except q.ErroQualidade as e:
        return _erro(e, 'qual.swot', a=aid)
    return redirect(url_for('qual.swot', a=aid))


@bp.route('/swot/item/<int:iid>/excluir', methods=['POST'])
@login_obrigatorio
def swot_item_excluir(iid):
    aid = q.excluir_swot_item(get_db(), iid)
    return redirect(url_for('qual.swot', a=aid))


@bp.route('/swot/<int:aid>/excluir', methods=['POST'])
@login_obrigatorio
def swot_excluir(aid):
    q.excluir_swot(get_db(), aid)
    return redirect(url_for('qual.swot'))


@bp.route('/swot/<int:aid>.pdf')
@login_obrigatorio
def swot_pdf(aid):
    try:
        s = q.swot(get_db(), aid)
    except q.ErroQualidade:
        abort(404)
    return _arquivo(docs.swot_pdf(s, _empresa(), _usuario()), 'SWOT', 'pdf')


# ------------------------------------------------------------------ fluxogramas
@bp.route('/fluxogramas')
@login_obrigatorio
def fluxos():
    return render_template('qualidade/fluxos.html', lista=q.processos(get_db()), modelos=modelos.MODELOS, fluxos_prontos=modelos.galeria())


@bp.route('/fluxogramas/novo', methods=['POST'])
@login_obrigatorio
def fluxo_novo():
    modelo = request.form.get('modelo') or None
    try:
        fid = q.criar_processo(get_db(), request.form, _usuario(), modelo if modelo in dict(modelos.MODELOS) else None)
    except q.ErroQualidade as e:
        return _erro(e, 'qual.fluxos')
    return redirect(url_for('qual.fluxo', fid=fid))


@bp.route('/fluxogramas/<int:fid>')
@login_obrigatorio
def fluxo(fid):
    try:
        f = q.processo(get_db(), fid)
    except q.ErroQualidade:
        abort(404)
    return render_template('qualidade/fluxo.html', f=f, formas=q.FORMAS)


@bp.route('/fluxogramas/<int:fid>/salvar', methods=['POST'])
@login_obrigatorio
def fluxo_salvar(fid):
    try:
        dados = q.salvar_processo(get_db(), fid, request.form, _usuario())
    except q.ErroQualidade as e:
        return jsonify(erro=str(e)), 400
    f = q.processo(get_db(), fid)
    return jsonify(ok=True, etapas=len(dados['nos']), versao=f['versao'], status=f['status'])


@bp.route('/fluxogramas/<int:fid>/aprovar', methods=['POST'])
@login_obrigatorio
def fluxo_aprovar(fid):
    try:
        q.aprovar_processo(get_db(), fid, _usuario())
    except q.ErroQualidade as e:
        return _erro(e, 'qual.fluxos')
    flash('Fluxograma aprovado. Qualquer alteração depois disso abre uma nova versão.', 'ok')
    return redirect(url_for('qual.fluxo', fid=fid))


@bp.route('/fluxogramas/<int:fid>/excluir', methods=['POST'])
@login_obrigatorio
def fluxo_excluir(fid):
    q.excluir_processo(get_db(), fid)
    flash('Fluxograma excluído.', 'ok')
    return redirect(url_for('qual.fluxos'))


# ------------------------------------------------------------------ organograma
@bp.route('/organograma')
@login_obrigatorio
def organograma():
    db = get_db()
    nos = q.organograma(db)
    funcionarios = [dict(r) for r in db.execute("SELECT id, name FROM bh_employees WHERE COALESCE(active,1)=1 ORDER BY name")] \
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='bh_employees'").fetchone() else []
    editar = next((n for n in nos if n['id'] == request.args.get('editar', type=int)), None)
    return render_template('qualidade/organograma.html', nos=nos, funcionarios=funcionarios, editar=editar, modelos=aplicar.galeria_organogramas())


@bp.route('/organograma/salvar', methods=['POST'])
@login_obrigatorio
def org_salvar():
    nid = request.form.get('id')
    try:
        q.salvar_no_org(get_db(), request.form, int(nid) if nid and nid.isdigit() else None)
    except q.ErroQualidade as e:
        return _erro(e, 'qual.organograma')
    return redirect(url_for('qual.organograma'))


@bp.route('/organograma/<int:nid>/excluir', methods=['POST'])
@login_obrigatorio
def org_excluir(nid):
    q.excluir_no_org(get_db(), nid)
    return redirect(url_for('qual.organograma'))


# ------------------------------------------------------------------ ocorrências e satisfação
@bp.route('/ocorrencias')
@login_obrigatorio
def ocorrencias():
    db = get_db()
    de, ate = _periodo(90)
    lista = q.ocorrencias(db, de.isoformat(), ate.isoformat())
    oc = qd.ocorrencias(db, de, ate)
    editar = next((o for o in lista if o['id'] == request.args.get('editar', type=int)), None)
    return render_template('qualidade/ocorrencias.html', lista=lista, resumo=oc, de=de.isoformat(), ate=ate.isoformat(), editar=editar,
                           tipos=q.TIPOS_OCORRENCIA, gravidades=q.GRAVIDADES, status_ocorrencia=q.STATUS_OCORRENCIA,
                           hoje=date.today().isoformat(), modelos_ocor=aplicar.modelos_ocorrencia())


@bp.route('/ocorrencias/salvar', methods=['POST'])
@login_obrigatorio
def ocorrencia_salvar():
    oid = request.form.get('id')
    try:
        q.salvar_ocorrencia(get_db(), request.form, _usuario(), int(oid) if oid and oid.isdigit() else None)
    except q.ErroQualidade as e:
        return _erro(e, 'qual.ocorrencias')
    flash('Ocorrência registrada.', 'ok')
    return redirect(url_for('qual.ocorrencias'))


@bp.route('/ocorrencias/<int:oid>/excluir', methods=['POST'])
@login_obrigatorio
def ocorrencia_excluir(oid):
    q.excluir_ocorrencia(get_db(), oid)
    return redirect(url_for('qual.ocorrencias'))


@bp.route('/ocorrencias/<int:oid>/problema', methods=['POST'])
@login_obrigatorio
def ocorrencia_problema(oid):
    try:
        pid = q.abrir_problema_da_ocorrencia(get_db(), oid, _usuario())
    except q.ErroQualidade as e:
        return _erro(e, 'qual.ocorrencias')
    return redirect(url_for('qual.problema_pagina', pid=pid))


@bp.route('/ocorrencias.<tipo>')
@login_obrigatorio
def ocorrencias_arquivo(tipo):
    if tipo not in ('pdf', 'xlsx'):
        abort(404)
    de, ate = _periodo(90)
    lista = q.ocorrencias(get_db(), de.isoformat(), ate.isoformat())
    f = docs.ocorrencias_pdf if tipo == 'pdf' else docs.ocorrencias_xlsx
    args = (lista, _empresa(), de.isoformat(), ate.isoformat()) + ((_usuario(),) if tipo == 'pdf' else ())
    return _arquivo(f(*args), 'Ocorrencias', tipo)


@bp.route('/pesquisa', methods=['POST'])
@login_obrigatorio
def pesquisa():
    try:
        q.registrar_pesquisa(get_db(), request.form, _usuario())
    except q.ErroQualidade as e:
        return _erro(e, 'qual.ocorrencias')
    flash('Pesquisa de satisfação registrada.', 'ok')
    return redirect(url_for('qual.ocorrencias'))


# ------------------------------------------------------------------ avaliação de fornecedores (ONA)
@bp.route('/fornecedores')
@login_obrigatorio
def forn():
    db = get_db()
    lista = q.fornecedores_situacao(db)
    filtro = request.args.get('situacao') or ''
    if filtro:
        lista = [f for f in lista if f['situacao'] == filtro]
    de, ate = _periodo(365)
    return render_template('qualidade/fornecedores.html', lista=lista, filtro=filtro, de=de.isoformat(), ate=ate.isoformat(),
                           avaliacoes=q.avaliacoes_periodo(db, de.isoformat(), ate.isoformat()))


@bp.route('/fornecedores/<int:fid>/avaliar', methods=['GET', 'POST'])
@login_obrigatorio
def forn_avaliar(fid):
    db = get_db()
    f = db.execute('SELECT * FROM fornecedores WHERE id=?', (fid,)).fetchone()
    if f is None:
        abort(404)
    if request.method == 'POST':
        try:
            aid = q.avaliar_fornecedor(db, fid, request.form, _usuario())
        except q.ErroQualidade as e:
            flash(str(e), 'erro')
            return render_template('qualidade/fornecedor_avaliar.html', f=f, criterios=q.criterios(db), form=request.form,
                                   historico=_historico(db, fid), hoje=date.today().isoformat())
        a = q.avaliacao(db, aid)
        flash('Avaliação gravada: %s (%s da nota máxima).' % (a['classificacao'], docs._p(a['percentual'])), 'ok')
        return redirect(url_for('qual.forn'))
    return render_template('qualidade/fornecedor_avaliar.html', f=f, criterios=q.criterios(db), form={}, historico=_historico(db, fid),
                           hoje=date.today().isoformat())


def _historico(db, fid):
    return [dict(r) for r in db.execute('SELECT * FROM cq_forn_avaliacoes WHERE fornecedor_id=? ORDER BY data DESC, id DESC', (fid,))]


@bp.route('/fornecedores/criterios', methods=['GET', 'POST'])
@login_obrigatorio
def forn_criterios():
    db = get_db()
    if request.method == 'POST':
        try:
            q.salvar_criterios(db, request.form)
        except q.ErroQualidade as e:
            flash(str(e), 'erro')
        else:
            flash('Critérios gravados.', 'ok')
        return redirect(url_for('qual.forn_criterios'))
    return render_template('qualidade/fornecedor_criterios.html', criterios=q.criterios(db, False), modelos=aplicar.galeria_criterios())


@bp.route('/fornecedores/avaliacao/<int:aid>.pdf')
@login_obrigatorio
def forn_avaliacao_pdf(aid):
    try:
        a = q.avaliacao(get_db(), aid)
    except q.ErroQualidade:
        abort(404)
    return _arquivo(docs.avaliacao_pdf(a, _empresa(), _usuario()), 'Avaliacao de fornecedor %d' % aid, 'pdf')


@bp.route('/fornecedores/relatorio.<tipo>')
@login_obrigatorio
def forn_relatorio(tipo):
    if tipo not in ('pdf', 'xlsx'):
        abort(404)
    db = get_db()
    de, ate = _periodo(365)
    lista = q.fornecedores_situacao(db)
    avs = q.avaliacoes_periodo(db, de.isoformat(), ate.isoformat())
    f = docs.fornecedores_pdf if tipo == 'pdf' else docs.fornecedores_xlsx
    args = (lista, avs, _empresa(), de.isoformat(), ate.isoformat()) + ((_usuario(),) if tipo == 'pdf' else ())
    return _arquivo(f(*args), 'Avaliacao de fornecedores', tipo)


# ------------------------------------------------------------------ pesquisa de satisfação (QR Code)
def _link_pesquisa(db):
    return pesq.link_publico(db, current_app.config['PORTA'])


@bp.route('/satisfacao')
@login_obrigatorio
def satisf():
    db = get_db()
    link = _link_pesquisa(db)
    mensagem = 'Olá! Avalie o nosso atendimento em menos de 1 minuto. Conecte-se ao Wi-Fi da clínica e abra: %s' % link
    return render_template('qualidade/satisfacao.html', perguntas=pesq.perguntas(db), maximo=pesq.MAX_PERGUNTAS, link=link,
                           ativa=pesq.ativa(db), endereco=pesq.endereco_salvo(db), ip=pesq.ip_da_maquina(),
                           porta=current_app.config['PORTA'], wa_texto=quote(mensagem), modelos=aplicar.galeria_perguntas(),
                           tipos=pesq.TIPOS)


@bp.route('/satisfacao/perguntas', methods=['POST'])
@login_obrigatorio
def satisf_perguntas():
    db = get_db()
    try:
        if request.form.get('restaurar'):
            pesq.restaurar_sugestoes(db)
            flash('Perguntas sugeridas restauradas.', 'ok')
        else:
            pesq.salvar_perguntas(db, request.form.getlist('pergunta'), request.form.getlist('tipo'))
            flash('Perguntas da pesquisa salvas.', 'ok')
    except pesq.ErroPesquisa as e:
        flash(str(e), 'erro')
    return redirect(url_for('qual.satisf'))


@bp.route('/satisfacao/config', methods=['POST'])
@login_obrigatorio
def satisf_config():
    db = get_db()
    try:
        pesq.salvar_endereco(db, request.form.get('endereco'))
        pesq.definir_ativa(db, bool(request.form.get('ativa')))
        flash('Configuração da pesquisa salva.', 'ok')
    except pesq.ErroPesquisa as e:
        flash(str(e), 'erro')
    return redirect(url_for('qual.satisf'))


@bp.route('/satisfacao/qr.svg')
@login_obrigatorio
def satisf_qr():
    return Response(pesq.qr_svg(_link_pesquisa(get_db())), mimetype='image/svg+xml', headers={'Cache-Control': 'no-store'})


@bp.route('/satisfacao/cartaz')
@login_obrigatorio
def satisf_cartaz():
    return render_template('qualidade/satisfacao_cartaz.html', link=_link_pesquisa(get_db()), clinica=_empresa())


@bp.route('/satisfacao/respostas')
@login_obrigatorio
def satisf_respostas():
    db = get_db()
    de, ate = _periodo(90)
    so_pendentes = request.args.get('pendentes') == '1'
    return render_template('qualidade/satisfacao_respostas.html', de=de.isoformat(), ate=ate.isoformat(), so_pendentes=so_pendentes,
                           ind=pesq.indicadores(db, de.isoformat(), ate.isoformat()),
                           respostas=pesq.lista_respostas(db, de.isoformat(), ate.isoformat(), so_pendentes))


@bp.route('/satisfacao/impresso')
@login_obrigatorio
def satisf_impresso():
    db = get_db()
    return render_template('qualidade/satisfacao_impresso.html', perguntas=pesq.perguntas(db), clinica=_empresa(),
                           atendimentos=pesq.ATENDIMENTOS, respondentes=pesq.RESPONDENTES)


@bp.route('/satisfacao/lancar', methods=['GET', 'POST'])
@login_obrigatorio
def satisf_lancar():
    db = get_db()
    if request.method == 'POST':
        try:
            pesq.registrar_resposta(db, request.form, None, origem='IMPRESSO', usuario=_usuario())
            flash('Questionário impresso lançado. Pode lançar o próximo.', 'ok')
            return redirect(url_for('qual.satisf_lancar'))
        except pesq.ErroPesquisa as e:
            flash(str(e), 'erro')
            return _tela_lancar(db, request.form)
    return _tela_lancar(db, {})


def _tela_lancar(db, f):
    return render_template('qualidade/satisfacao_lancar.html', perguntas=pesq.perguntas(db), exames=pesq.exames_ativos(db),
                           atendimentos=pesq.ATENDIMENTOS, respondentes=pesq.RESPONDENTES, hoje=date.today().isoformat(), f=f)


@bp.route('/satisfacao/respostas/<int:rid>/revisar', methods=['POST'])
@login_obrigatorio
def satisf_revisar(rid):
    try:
        pesq.marcar_revisada(get_db(), rid, _usuario(), request.form.get('revisada') != '0')
    except pesq.ErroPesquisa as e:
        flash(str(e), 'erro')
    return _voltar('qual.satisf_respostas')


@bp.route('/satisfacao/relatorio.<tipo>')
@login_obrigatorio
def satisf_relatorio(tipo):
    if tipo not in ('pdf', 'xlsx'):
        abort(404)
    db = get_db()
    de, ate = _periodo(90)
    ind = pesq.indicadores(db, de.isoformat(), ate.isoformat())
    resp = pesq.lista_respostas(db, de.isoformat(), ate.isoformat(), limite=2000)
    f = pdocs.relatorio_pdf if tipo == 'pdf' else pdocs.relatorio_xlsx
    args = (ind, resp, _empresa()) + ((_usuario(),) if tipo == 'pdf' else ())
    return _arquivo(f(*args), 'Satisfacao-do-cliente', tipo)


# ------------------------------------------------------------------ modelos prontos (um clique aplica; repetir não duplica)
@bp.route('/modelos/problema/<chave>', methods=['POST'])
@login_obrigatorio
def modelo_problema(chave):
    destino = request.form.get('destino') or 'pdca'
    try:
        pid, criado = aplicar.aplicar_problema(get_db(), chave, _usuario())
    except q.ErroQualidade as e:
        return _erro(e, 'qual.pdca')
    flash('Modelo aplicado: problema, causas, cinco porquês, GUT e plano 5W2H criados. Revise e ajuste os dados do seu serviço.' if criado
          else 'Este modelo já está aberto: abri o que existe.', 'ok')
    if destino == 'ishikawa':
        return redirect(url_for('qual.ishikawa', p=pid))
    if destino == 'porques':
        return redirect(url_for('qual.porques', p=pid))
    if destino == 'gut':
        return redirect(url_for('qual.gut'))
    return redirect(url_for('qual.problema_pagina', pid=pid))


@bp.route('/modelos/plano/<chave>', methods=['POST'])
@login_obrigatorio
def modelo_plano(chave):
    pid = request.form.get('problema_id')
    try:
        n = aplicar.aplicar_plano(get_db(), chave, _usuario(), int(pid) if pid and pid.isdigit() else None)
    except q.ErroQualidade as e:
        return _erro(e, 'qual.plano')
    flash('%d ação(ões) incluída(s) no plano. Ajuste responsáveis e prazos.' % n if n else 'Todas as ações deste modelo já estão no plano.', 'ok')
    return redirect(url_for('qual.plano'))


@bp.route('/modelos/riscos/<chave>', methods=['POST'])
@login_obrigatorio
def modelo_riscos(chave):
    try:
        n = aplicar.aplicar_riscos(get_db(), chave, _usuario())
    except q.ErroQualidade as e:
        return _erro(e, 'qual.riscos')
    flash('%d risco(s) incluído(s) na matriz. Ajuste probabilidade, impacto e responsáveis.' % n if n else 'Todos os riscos deste modelo já estão na matriz.', 'ok')
    return redirect(url_for('qual.riscos'))


@bp.route('/modelos/swot/<chave>', methods=['POST'])
@login_obrigatorio
def modelo_swot(chave):
    try:
        aid = aplicar.aplicar_swot(get_db(), chave, _usuario())
    except q.ErroQualidade as e:
        return _erro(e, 'qual.swot')
    flash('Análise SWOT criada a partir do modelo. Revise os itens e os pesos com a equipe.', 'ok')
    return redirect(url_for('qual.swot', a=aid))


@bp.route('/modelos/fluxograma/<chave>', methods=['POST'])
@login_obrigatorio
def modelo_fluxo(chave):
    if chave not in dict(modelos.MODELOS):
        abort(404)
    grupo, frase = modelos.INFO.get(chave, ('', ''))
    try:
        fid = q.criar_processo(get_db(), {'nome': dict(modelos.MODELOS)[chave], 'setor': grupo, 'objetivo': frase}, _usuario(), chave)
    except q.ErroQualidade as e:
        return _erro(e, 'qual.fluxos')
    flash('Fluxograma criado a partir do modelo. Ajuste as etapas, os setores e os responsáveis e depois aprove.', 'ok')
    return redirect(url_for('qual.fluxo', fid=fid))


@bp.route('/modelos/organograma/<chave>', methods=['POST'])
@login_obrigatorio
def modelo_organograma(chave):
    try:
        n = aplicar.aplicar_organograma(get_db(), chave, bool(request.form.get('substituir')))
    except q.ErroQualidade as e:
        return _erro(e, 'qual.organograma')
    flash('Organograma criado com %d cargos. Informe os nomes das pessoas e ajuste a estrutura.' % n, 'ok')
    return redirect(url_for('qual.organograma'))


@bp.route('/modelos/criterios/<chave>', methods=['POST'])
@login_obrigatorio
def modelo_criterios(chave):
    try:
        n = aplicar.aplicar_criterios(get_db(), chave, bool(request.form.get('substituir')))
    except q.ErroQualidade as e:
        return _erro(e, 'qual.forn_criterios')
    flash('Critérios aplicados (%d novo(s)). Ajuste pesos e descrições.' % n, 'ok')
    return redirect(url_for('qual.forn_criterios'))


@bp.route('/modelos/perguntas/<chave>', methods=['POST'])
@login_obrigatorio
def modelo_perguntas(chave):
    try:
        aplicar.aplicar_perguntas(get_db(), chave)
    except (q.ErroQualidade, pesq.ErroPesquisa) as e:
        return _erro(e, 'qual.satisf')
    flash('Perguntas da pesquisa trocadas pelo modelo. Respostas antigas continuam guardadas.', 'ok')
    return redirect(url_for('qual.satisf'))


# ------------------------------------------------------------------ PDFs das ferramentas que ainda não tinham
@bp.route('/ishikawa.pdf')
@login_obrigatorio
def ishikawa_pdf():
    db = get_db()
    pid = request.args.get('p', type=int)
    try:
        p = q.problema(db, pid or 0)
    except q.ErroQualidade:
        abort(404)
    return _arquivo(docs.ishikawa_pdf(q.ishikawa(db, pid), p, _empresa(), _usuario()), 'Ishikawa %d' % pid, 'pdf')


@bp.route('/porques.pdf')
@login_obrigatorio
def porques_pdf():
    pid = request.args.get('p', type=int)
    try:
        p = q.problema(get_db(), pid or 0)
    except q.ErroQualidade:
        abort(404)
    return _arquivo(docs.porques_pdf(p, _empresa(), _usuario()), 'Cinco porques %d' % pid, 'pdf')


@bp.route('/fluxogramas/<int:fid>.pdf')
@login_obrigatorio
def fluxo_pdf(fid):
    try:
        f = q.processo(get_db(), fid)
    except q.ErroQualidade:
        abort(404)
    return _arquivo(docs.fluxo_pdf(f, _empresa(), _usuario()), 'Fluxograma %d' % fid, 'pdf')


@bp.route('/organograma.pdf')
@login_obrigatorio
def organograma_pdf():
    return _arquivo(docs.organograma_pdf(q.organograma(get_db()), _empresa(), _usuario()), 'Organograma', 'pdf')


# ------------------------------------------------------------------ protocolos (POPs)
@bp.route('/protocolos')
@login_obrigatorio
def protocolos():
    db = get_db()
    return render_template('qualidade/protocolos.html', lista=prot.protocolos(db), modelos_pop=prot.galeria(db))


@bp.route('/protocolos/novo', methods=['POST'])
@login_obrigatorio
def protocolo_novo():
    try:
        pid = prot.criar(get_db(), request.form, _usuario())
    except q.ErroQualidade as e:
        return _erro(e, 'qual.protocolos')
    return redirect(url_for('qual.protocolo_pagina', pid=pid))


@bp.route('/protocolos/modelo/<chave>', methods=['POST'])
@login_obrigatorio
def protocolo_modelo(chave):
    try:
        pid, criado = prot.aplicar_modelo(get_db(), chave, _usuario())
    except q.ErroQualidade as e:
        return _erro(e, 'qual.protocolos')
    flash('Protocolo criado a partir do modelo. Revise, ajuste ao seu serviço e aprove.' if criado else 'Este protocolo já foi criado: abri o que existe.', 'ok')
    return redirect(url_for('qual.protocolo_pagina', pid=pid))


@bp.route('/protocolos/modelos-todos', methods=['POST'])
@login_obrigatorio
def protocolo_modelos_todos():
    n = prot.aplicar_todos(get_db(), _usuario())
    flash('%d protocolo(s) criado(s) a partir dos modelos.' % n if n else 'Todos os modelos de protocolo já estão criados.', 'ok')
    return redirect(url_for('qual.protocolos'))


@bp.route('/protocolos/<int:pid>')
@login_obrigatorio
def protocolo_pagina(pid):
    db = get_db()
    try:
        p = prot.protocolo(db, pid)
    except q.ErroQualidade:
        abort(404)
    return render_template('qualidade/protocolo.html', p=p, fluxos=q.processos(db), modelos_fluxo=modelos.MODELOS, hoje=date.today().isoformat())


@bp.route('/protocolos/<int:pid>/salvar', methods=['POST'])
@login_obrigatorio
def protocolo_salvar(pid):
    try:
        nova = prot.salvar(get_db(), pid, request.form, _usuario())
    except q.ErroQualidade as e:
        return _erro(e, 'qual.protocolo_pagina', pid=pid)
    flash('Protocolo salvo como nova versão (rascunho): a anterior estava aprovada.' if nova else 'Protocolo salvo.', 'ok')
    return redirect(url_for('qual.protocolo_pagina', pid=pid))


@bp.route('/protocolos/<int:pid>/aprovar', methods=['POST'])
@login_obrigatorio
def protocolo_aprovar(pid):
    try:
        prot.aprovar(get_db(), pid, request.form, _usuario())
    except q.ErroQualidade as e:
        return _erro(e, 'qual.protocolo_pagina', pid=pid)
    flash('Protocolo aprovado. Baixe o PDF e colete as assinaturas.', 'ok')
    return redirect(url_for('qual.protocolo_pagina', pid=pid))


@bp.route('/protocolos/<int:pid>/excluir', methods=['POST'])
@login_obrigatorio
def protocolo_excluir(pid):
    prot.excluir(get_db(), pid)
    flash('Protocolo excluído.', 'ok')
    return redirect(url_for('qual.protocolos'))


@bp.route('/protocolos/<int:pid>.pdf')
@login_obrigatorio
def protocolo_pdf(pid):
    db = get_db()
    try:
        p = prot.protocolo(db, pid)
    except q.ErroQualidade:
        abort(404)
    fluxo = None
    if p['fluxo_id']:
        try:
            fluxo = q.processo(db, p['fluxo_id'])['dados_obj']
        except q.ErroQualidade:
            fluxo = None
    if fluxo is None and p['fluxo_modelo']:
        fluxo = modelos.fluxo(p['fluxo_modelo'])
    return _arquivo(docs.protocolo_pdf(p, fluxo, _empresa(), _usuario()), p['codigo'], 'pdf')


@bp.route('/protocolos/lista-mestra.pdf')
@login_obrigatorio
def protocolos_lista_pdf():
    return _arquivo(docs.lista_mestra_pdf(prot.protocolos(get_db()), _empresa(), _usuario()), 'Lista mestra de protocolos', 'pdf')


# ------------------------------------------------------------------ perfil epidemiológico
@bp.route('/epidemiologico')
@login_obrigatorio
def epidemio():
    de, ate = _periodo(365)
    return render_template('qualidade/epidemio.html', pf=epi.perfil(get_db(), de, ate), de=de.isoformat(), ate=ate.isoformat())


@bp.route('/epidemiologico.pdf')
@login_obrigatorio
def epidemio_pdf():
    de, ate = _periodo(365)
    return _arquivo(docs.epidemio_pdf(epi.perfil(get_db(), de, ate), _empresa(), _usuario()), 'Perfil epidemiologico', 'pdf')
