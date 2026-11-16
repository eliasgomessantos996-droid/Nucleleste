"""Telas do módulo Enfermagem e Segurança (carrinho, medicamentos, equipamentos, esterilização, radioproteção) e a importação da assinatura do profissional."""
import io
import json
import time

from flask import Blueprint, Response, abort, flash, g, redirect, render_template, request, send_file, session, url_for

from . import admin_obrigatorio, enfermagem as enf, hierarquia, laudos, login_obrigatorio, modulos, pesquisa as pesq
from .auditoria import registrar
from .db import config_get, get_db

bp = Blueprint('enf', __name__, url_prefix='/enfermagem')


@bp.before_request
def _tabelas():
    enf.garantir(get_db())


def _eu():
    return g.usuario['id']


def _gestao():
    return bool(g.usuario['admin']) or 'gerencia' in g.modulos


def _erro(e, endpoint, **kw):
    flash(str(e), 'erro')
    return redirect(url_for(endpoint, **kw))


def _usuarios_do_modulo(db):
    saida = []
    for u in db.execute('SELECT u.id, u.usuario, u.admin, u.modulos, u.bh_funcionario_id, COALESCE(e.name, u.usuario) AS nome FROM usuarios u '
                        'LEFT JOIN bh_employees e ON e.id=u.bh_funcionario_id WHERE u.ativo=1 AND COALESCE(u.sistema,0)=0 ORDER BY nome'):
        if 'enfermagem' in modulos.modulos_do_usuario(u) and enf.assinatura_valida(db, u['id']):
            saida.append(dict(u))
    return saida


# ------------------------------------------------------------------ painel
@bp.route('')
@login_obrigatorio
def painel():
    db = get_db()
    return render_template('enfermagem/painel.html', resumo=enf.resumo(db), areas=enf.AREAS, resp=enf.responsaveis(db), usuarios=_usuarios_do_modulo(db), gestao=_gestao(),
                           minha=enf.profissional(db, _eu()), hora_teste=enf.hora_teste(db))


@bp.route('/responsaveis', methods=['POST'])
@login_obrigatorio
def responsaveis():
    if not _gestao():
        abort(403)
    enf.salvar_responsaveis(get_db(), request.form)
    registrar('Enfermagem', 'Definiu os responsáveis das áreas')
    flash('Responsáveis salvos. Os avisos de cada área vão para o titular e o substituto.', 'ok')
    return redirect(url_for('enf.painel'))


# ------------------------------------------------------------------ profissionais e assinatura
@bp.route('/profissionais')
@login_obrigatorio
def profissionais():
    return render_template('enfermagem/profissionais.html', lista=enf.profissionais(get_db()), gestao=_gestao())


@bp.route('/assinatura/<int:uid>', methods=['GET', 'POST'])
@admin_obrigatorio
def assinatura(uid):
    db = get_db()
    u = db.execute('SELECT id, usuario, bh_funcionario_id FROM usuarios WHERE id=?', (uid,)).fetchone()
    if u is None:
        abort(404)
    pend = session.get('enf_pendente')
    if pend and (pend.get('uid') != uid or time.time() - pend.get('ts', time.time()) > 1800):
        pend = None
    if pend and 'ts' not in pend:
        pend['ts'] = time.time()
        session['enf_pendente'] = pend
    atual = enf.profissional(db, uid)
    if request.method == 'POST':
        arquivo = request.files.get('assinatura')
        conteudo = arquivo.read() if arquivo and arquivo.filename else b''
        try:
            resultado = enf.salvar_profissional(db, uid, request.form.get('cargo'), request.form.get('conselho'), request.form.get('numero'), request.form.get('uf'),
                                                conteudo, g.usuario['usuario'], request.form.get('acao') == 'manter')
        except enf.ErroEnfermagem as e:
            db.rollback()
            flash(str(e), 'erro')
            return render_template('enfermagem/assinatura.html', alvo=u, atual=atual, pend=bool(pend), conselhos=enf.CONSELHOS, ufs=enf.UFS, f=request.form,
                                   nome=enf.nome_profissional(db, uid))
        if resultado != 'mantida':
            registrar('Enfermagem', 'Importou assinatura' if resultado == 'nova' else 'Trocou a assinatura', 'profissional %s (%s %s-%s %s)' % (
                u['usuario'], request.form.get('cargo'), request.form.get('conselho'), request.form.get('uf'), request.form.get('numero')))
        if pend:   # conclui a mudança de permissão que estava esperando a assinatura
            db.execute('UPDATE usuarios SET admin=?, modulos=?, laudo_perm=? WHERE id=?', (pend['admin'], json.dumps(pend['modulos']), pend['laudo_perm'], uid))
            if pend.get('login') and not hierarquia.validar_login(db, uid, pend['login']):
                hierarquia.renomear_login(db, uid, pend['login'])
            if pend.get('senha_hash'):
                db.execute('UPDATE usuarios SET senha_hash=? WHERE id=?', (pend['senha_hash'], uid))
            db.commit()
            session.pop('enf_pendente', None)
            registrar('Enfermagem', 'Liberou o módulo Enfermagem e Segurança', 'usuário %s, com assinatura importada' % u['usuario'])
            flash('Assinatura importada e permissões de %s salvas: o módulo Enfermagem e Segurança está liberado.' % u['usuario'], 'ok')
            return redirect(url_for('admin.usuarios'))
        flash('Assinatura mantida.' if resultado == 'mantida' else 'Assinatura salva.', 'ok')
        return redirect(url_for('admin.usuario_editar', uid=uid))
    return render_template('enfermagem/assinatura.html', alvo=u, atual=atual, pend=bool(pend), conselhos=enf.CONSELHOS, ufs=enf.UFS, f={}, nome=enf.nome_profissional(db, uid))


@bp.route('/assinatura/<int:uid>/cancelar', methods=['POST'])
@admin_obrigatorio
def assinatura_cancelar(uid):
    session.pop('enf_pendente', None)
    flash('Cancelado: a permissão do módulo continua como estava e nada foi salvo.', 'aviso')
    return redirect(url_for('admin.usuario_editar', uid=uid))


@bp.route('/assinatura/<int:uid>.png')
@login_obrigatorio
def assinatura_png(uid):
    png = enf.assinatura_png(get_db(), uid)
    if png is None:
        abort(404)
    return Response(png, mimetype='image/png', headers={'Cache-Control': 'private, max-age=300'})


# ------------------------------------------------------------------ carrinho de emergência e kit de derramamento
@bp.route('/carrinho')
@login_obrigatorio
def carrinho():
    return render_template('enfermagem/carrinho.html', lista=enf.carrinhos(get_db()))


@bp.route('/carrinho/novo', methods=['POST'])
@login_obrigatorio
def carrinho_novo():
    tipo = 'KIT' if request.form.get('tipo') == 'KIT' else 'CARRINHO'
    try:
        cid = enf.salvar_carrinho(get_db(), request.form, tipo)
    except enf.ErroEnfermagem as e:
        return _erro(e, 'enf.radioprotecao' if tipo == 'KIT' else 'enf.carrinho')
    return redirect(url_for('enf.carrinho_detalhe', cid=cid))


@bp.route('/carrinho/<int:cid>')
@login_obrigatorio
def carrinho_detalhe(cid):
    db = get_db()
    try:
        c = enf.carrinho(db, cid)
    except enf.ErroEnfermagem:
        abort(404)
    lista = enf.CHECKLIST_KIT if c['tipo'] == 'KIT' else enf.CHECKLIST_CARRINHO
    return render_template('enfermagem/carrinho_det.html', c=c, checklist=lista, historico=enf.historico_conferencias(db, cid), eu=enf.bloco_assinatura(db, _eu()))


@bp.route('/carrinho/<int:cid>/item', methods=['POST'])
@login_obrigatorio
def carrinho_item(cid):
    iid = request.form.get('id')
    try:
        enf.salvar_item(get_db(), cid, request.form, int(iid) if iid and iid.isdigit() else None)
    except enf.ErroEnfermagem as e:
        return _erro(e, 'enf.carrinho_detalhe', cid=cid)
    return redirect(url_for('enf.carrinho_detalhe', cid=cid))


@bp.route('/carrinho/<int:cid>/item/<int:iid>/excluir', methods=['POST'])
@login_obrigatorio
def carrinho_item_excluir(cid, iid):
    enf.excluir_item(get_db(), cid, iid)
    return redirect(url_for('enf.carrinho_detalhe', cid=cid))


@bp.route('/carrinho/<int:cid>/conferir', methods=['POST'])
@login_obrigatorio
def carrinho_conferir(cid):
    db = get_db()
    try:
        conf = enf.conferir(db, cid, request.form, _eu())
    except enf.ErroEnfermagem as e:
        db.rollback()
        return _erro(e, 'enf.carrinho_detalhe', cid=cid)
    registrar('Enfermagem', 'Registrou conferência', 'carrinho/kit %d, conferência %d' % (cid, conf))
    flash('Conferência registrada. Imprima a ficha com a sua assinatura.', 'ok')
    return redirect(url_for('enf.carrinho_ficha', conf_id=conf))


@bp.route('/carrinho/conferencia/<int:conf_id>/ficha')
@login_obrigatorio
def carrinho_ficha(conf_id):
    db = get_db()
    try:
        conf = enf.conferencia(db, conf_id)
        c = enf.carrinho(db, conf['carrinho_id'])
    except enf.ErroEnfermagem:
        abort(404)
    ass = enf.bloco_assinatura(db, conf['profissional_id'])
    registrar('Enfermagem', 'Imprimiu ficha de conferência', 'conferência %d, assinada por %s%s' % (conf_id, ass['nome'], '' if ass['assinatura'] else ' (sem imagem de assinatura)'))
    return render_template('enfermagem/ficha_conferencia.html', conf=conf, c=c, ass=ass, clinica=config_get('clinica_nome') or 'Nucleleste')


# ------------------------------------------------------------------ medicamentos e insumos
@bp.route('/medicamentos')
@login_obrigatorio
def medicamentos():
    db = get_db()
    mn, mx = enf.limites_temperatura(db)
    editar = request.args.get('editar', type=int)
    lista = enf.medicamentos(db)
    return render_template('enfermagem/medicamentos.html', lista=lista, reposicao=enf.reposicao(db), locais=enf.LOCAIS_MED, temperaturas=enf.temperaturas(db),
                           t_min=mn, t_max=mx, pendentes_temp=enf.temperatura_pendente_hoje(db), gestao=_gestao(), editar=next((m for m in lista if m['id'] == editar), None),
                           locais_geladeira=sorted({m['local'] for m in lista if 'elad' in (m['local'] or '')} | {'Geladeira'}))


@bp.route('/medicamentos/salvar', methods=['POST'])
@login_obrigatorio
def medicamento_salvar():
    mid = request.form.get('id')
    try:
        enf.salvar_medicamento(get_db(), request.form, int(mid) if mid and mid.isdigit() else None)
    except enf.ErroEnfermagem as e:
        return _erro(e, 'enf.medicamentos')
    flash('Medicamento salvo.', 'ok')
    return redirect(url_for('enf.medicamentos'))


@bp.route('/medicamentos/carregar', methods=['POST'])
@login_obrigatorio
def medicamento_carregar():
    n = enf.carregar_medicamentos_mn(get_db())
    flash('%d medicamento(s) de medicina nuclear incluído(s). Informe lote, validade e quantidade de cada um.' % n if n else 'Os medicamentos de medicina nuclear já estão cadastrados.', 'ok')
    return redirect(url_for('enf.medicamentos'))


@bp.route('/medicamentos/<int:mid>/usar', methods=['POST'])
@login_obrigatorio
def medicamento_usar(mid):
    try:
        enf.usar_medicamento(get_db(), mid, request.form.get('qtd'), request.form.get('motivo'), _eu())
    except enf.ErroEnfermagem as e:
        get_db().rollback()
        return _erro(e, 'enf.medicamentos')
    flash('Uso registrado: a baixa foi feita e o item entrou na lista de reposição.', 'ok')
    return redirect(url_for('enf.medicamentos'))


@bp.route('/reposicao/<int:rid>/repor', methods=['POST'])
@login_obrigatorio
def reposicao_repor(rid):
    try:
        enf.repor(get_db(), rid, request.form)
    except enf.ErroEnfermagem as e:
        get_db().rollback()
        return _erro(e, 'enf.medicamentos')
    flash('Reposição registrada.', 'ok')
    return redirect(url_for('enf.medicamentos'))


@bp.route('/temperatura', methods=['POST'])
@login_obrigatorio
def temperatura_registrar():
    try:
        ok = enf.registrar_temperatura(get_db(), request.form, _eu())
    except enf.ErroEnfermagem as e:
        return _erro(e, 'enf.medicamentos')
    flash('Temperatura registrada.' if ok else 'Temperatura FORA do limite: avise o responsável e verifique os medicamentos da geladeira.', 'ok' if ok else 'erro')
    return redirect(url_for('enf.medicamentos'))


@bp.route('/temperatura/limites', methods=['POST'])
@login_obrigatorio
def temperatura_limites():
    if not _gestao():
        abort(403)
    try:
        enf.salvar_limites(get_db(), request.form)
    except enf.ErroEnfermagem as e:
        return _erro(e, 'enf.medicamentos')
    flash('Limites de temperatura salvos.', 'ok')
    return redirect(url_for('enf.medicamentos'))


# ------------------------------------------------------------------ equipamentos
@bp.route('/equipamentos')
@login_obrigatorio
def equipamentos():
    db = get_db()
    lista = enf.equipamentos(db)
    editar = request.args.get('editar', type=int)
    for e in lista:
        e['testes'] = enf.testes_recentes(db, e['id'], 4)
    return render_template('enfermagem/equipamentos.html', lista=lista, tipos=enf.TIPOS_EQUIP, cheques=enf.CHECKLIST_CARDIOVERSOR, hora=enf.hora_teste(db), gestao=_gestao(),
                           editar=next((e for e in lista if e['id'] == editar), None))


@bp.route('/equipamentos/salvar', methods=['POST'])
@login_obrigatorio
def equipamento_salvar():
    eid = request.form.get('id')
    arq = request.files.get('laudo')
    try:
        enf.salvar_equipamento(get_db(), request.form, arq.read() if arq and arq.filename else None, arq.filename if arq else '', int(eid) if eid and eid.isdigit() else None)
    except enf.ErroEnfermagem as e:
        get_db().rollback()
        return _erro(e, 'enf.equipamentos')
    flash('Equipamento salvo.', 'ok')
    return redirect(url_for('enf.equipamentos'))


@bp.route('/equipamentos/<int:eid>/laudo')
@login_obrigatorio
def equipamento_laudo(eid):
    conteudo, nome = enf.laudo_pdf(get_db(), eid)
    if conteudo is None:
        abort(404)
    return send_file(io.BytesIO(conteudo), mimetype='application/pdf', as_attachment=request.args.get('baixar') == '1', download_name=nome or 'laudo.pdf')


@bp.route('/equipamentos/hora', methods=['POST'])
@login_obrigatorio
def equipamento_hora():
    if not _gestao():
        abort(403)
    try:
        enf.salvar_hora_teste(get_db(), request.form.get('hora'))
    except enf.ErroEnfermagem as e:
        return _erro(e, 'enf.equipamentos')
    flash('Horário limite do teste diário salvo.', 'ok')
    return redirect(url_for('enf.equipamentos'))


@bp.route('/equipamentos/<int:eid>/teste', methods=['POST'])
@login_obrigatorio
def teste_registrar(eid):
    try:
        tid = enf.registrar_teste(get_db(), eid, request.form, _eu())
    except enf.ErroEnfermagem as e:
        return _erro(e, 'enf.equipamentos')
    registrar('Enfermagem', 'Registrou teste diário', 'equipamento %d, teste %d' % (eid, tid))
    flash('Teste registrado. Imprima a ficha com a sua assinatura.', 'ok')
    return redirect(url_for('enf.teste_ficha', tid=tid))


@bp.route('/equipamentos/teste/<int:tid>/ficha')
@login_obrigatorio
def teste_ficha(tid):
    db = get_db()
    try:
        t = enf.teste(db, tid)
    except enf.ErroEnfermagem:
        abort(404)
    ass = enf.bloco_assinatura(db, t['profissional_id'])
    registrar('Enfermagem', 'Imprimiu ficha de teste diário', 'teste %d, assinada por %s%s' % (tid, ass['nome'], '' if ass['assinatura'] else ' (sem imagem de assinatura)'))
    return render_template('enfermagem/ficha_teste.html', t=t, ass=ass, cheques=enf.CHECKLIST_CARDIOVERSOR, clinica=config_get('clinica_nome') or 'Nucleleste')


# ------------------------------------------------------------------ esterilização
@bp.route('/esterilizacao')
@login_obrigatorio
def esterilizacao():
    return render_template('enfermagem/esterilizacao.html', lista=enf.pacotes(get_db()), dias=enf.DIAS_VALIDADE_PACOTE)


@bp.route('/esterilizacao/novo', methods=['POST'])
@login_obrigatorio
def esterilizacao_novo():
    try:
        pid = enf.salvar_pacote(get_db(), request.form, _eu())
    except enf.ErroEnfermagem as e:
        return _erro(e, 'enf.esterilizacao')
    flash('Pacote registrado. Imprima a etiqueta para colar nele.', 'ok')
    return redirect(url_for('enf.pacote_etiqueta', pid=pid))


@bp.route('/esterilizacao/<int:pid>/biologico', methods=['POST'])
@login_obrigatorio
def pacote_biologico(pid):
    try:
        enf.atualizar_biologico(get_db(), pid, request.form.get('resultado'))
    except enf.ErroEnfermagem as e:
        return _erro(e, 'enf.esterilizacao')
    return redirect(url_for('enf.esterilizacao'))


@bp.route('/esterilizacao/<int:pid>/usado', methods=['POST'])
@login_obrigatorio
def pacote_usado(pid):
    try:
        enf.marcar_usado(get_db(), pid)
    except enf.ErroEnfermagem as e:
        return _erro(e, 'enf.esterilizacao')
    flash('Pacote marcado como usado e retirado da lista.', 'ok')
    return redirect(url_for('enf.esterilizacao'))


@bp.route('/esterilizacao/<int:pid>/etiqueta')
@login_obrigatorio
def pacote_etiqueta(pid):
    db = get_db()
    try:
        p = enf.pacote(db, pid)
    except enf.ErroEnfermagem:
        abort(404)
    ass = enf.bloco_assinatura(db, p['operador_id']) if p['operador_id'] else None
    registrar('Enfermagem', 'Imprimiu etiqueta de esterilização', 'pacote %s' % p['codigo'])
    return render_template('enfermagem/etiqueta.html', p=p, ass=ass, clinica=config_get('clinica_nome') or 'Nucleleste')


@bp.route('/esterilizacao/<int:pid>/qr.svg')
@login_obrigatorio
def pacote_qr(pid):
    p = enf.pacote(get_db(), pid) if True else None
    return Response(pesq.qr_svg('NUCLELESTE-ENF:' + p['codigo']), mimetype='image/svg+xml')


# ------------------------------------------------------------------ radioproteção da enfermagem
@bp.route('/radioprotecao')
@login_obrigatorio
def radioprotecao():
    db = get_db()
    return render_template('enfermagem/radioprotecao.html', kits=enf.carrinhos(db, 'KIT'), testes=enf.rp_testes(db), hoje=enf.rp_teste_hoje(db), ocorrencias=enf.ocorrencias_rp(db),
                           tipos=enf.TIPOS_RP, hora=enf.hora_teste(db))


@bp.route('/radioprotecao/teste', methods=['POST'])
@login_obrigatorio
def rp_teste():
    ok = enf.registrar_rp_teste(get_db(), request.form, _eu())
    registrar('Enfermagem', 'Registrou teste do monitor de contaminação', 'resultado: %s' % ('conforme' if ok else 'NÃO conforme'))
    flash('Teste registrado.' if ok else 'Teste registrado como NÃO conforme: não use o monitor e avise o supervisor de proteção radiológica.', 'ok' if ok else 'erro')
    return redirect(url_for('enf.radioprotecao'))


@bp.route('/radioprotecao/ocorrencia', methods=['POST'])
@login_obrigatorio
def rp_ocorrencia():
    try:
        enf.registrar_ocorrencia_rp(get_db(), request.form, _eu())
    except enf.ErroEnfermagem as e:
        get_db().rollback()
        return _erro(e, 'enf.radioprotecao')
    flash('Ocorrência registrada.', 'ok')
    return redirect(url_for('enf.radioprotecao'))
