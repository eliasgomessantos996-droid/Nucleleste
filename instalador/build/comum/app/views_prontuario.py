"""Prontuário do paciente: busca, histórico, documentos clínicos (SBAR e os próximos modelos) e impressão."""
import json
from datetime import date

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from . import admin_obrigatorio, login_obrigatorio, prontuario, prontuario_modelos as pm, util
from .db import config_get, get_db

bp = Blueprint('pront', __name__)


def _quando(momento):
    """'2026-11-14 09:30:00' -> '14/11/2026 às 09:30' (vazio se não houver data)."""
    if not momento:
        return ''
    return '%s às %s' % (util.data_br(momento[:10]), momento[11:16])


def _indice_profissional(assinaturas):
    """Em qual linha final vão o nome e o registro do profissional: a que diz 'Profissional' (ou a primeira)."""
    for i, rot in enumerate(assinaturas):
        if 'rofissional' in rot:
            return i
    return 0


def _ficha_original(d, dados):
    """Link para imprimir a ficha PNT original do atendimento (só quando o PNT digital tem atendimento e ficha)."""
    if d['atendimento_id'] and dados.get('_pnt_slug'):
        return url_for('atend.imprimir', aid=d['atendimento_id'], d=dados['_pnt_slug'] + ':1')
    return ''


def _renderizar_doc(d, dados, prof, erros=()):
    modelo = pm.obter(d['tipo'])
    return render_template('prontuario_doc.html', d=d, modelo=modelo, secoes=pm.secoes_de(d['tipo'], dados), dados=dados,
                           prof=prof, conselhos=pm.CONSELHOS_PROFISSIONAL, erros=list(erros), ro=d['situacao'] == 'CONCLUIDO',
                           situacoes=prontuario.ROTULO_SITUACAO, sinais_sub=pm.SINAIS_SUB, opcoes_de=pm.opcoes_de,
                           ficha_url=_ficha_original(d, dados))


# ---------------------------------------------------------------- busca e lista
@bp.route('/prontuario')
@login_obrigatorio
def indice():
    db = get_db()
    q = (request.args.get('q') or '').strip()
    achados = prontuario.buscar_pacientes(db, q) if len(q) >= 2 else []
    return render_template('prontuario_indice.html', q=q, achados=achados,
                           pendencias=prontuario.pendencias(db), concluidos=prontuario.ultimos_concluidos(db),
                           situacoes=prontuario.ROTULO_SITUACAO)


# ---------------------------------------------------------------- prontuário do paciente
@bp.route('/prontuario/paciente/<int:cid>')
@login_obrigatorio
def paciente(cid):
    db = get_db()
    if not db.execute('SELECT 1 FROM clientes WHERE id=?', (cid,)).fetchone():
        abort(404)
    prontuario.garantir(db, cid, g.usuario['usuario'])   # todo paciente já tem número ao ser aberto
    db.commit()
    h = prontuario.historico(db, cid)
    return render_template('prontuario_paciente.html', h=h, cliente=h['cliente'], modelos=pm.tipos_disponiveis(),
                           situacoes=prontuario.ROTULO_SITUACAO)


@bp.route('/prontuario/paciente/<int:cid>/imprimir')
@login_obrigatorio
def paciente_imprimir(cid):
    db = get_db()
    h = prontuario.historico(db, cid)
    if h is None:
        abort(404)
    return render_template('prontuario_paciente_imprimir.html', h=h, cliente=h['cliente'],
                           clinica=config_get('clinica_nome', ''), hoje=util.data_br(date.today().isoformat()),
                           situacoes=prontuario.ROTULO_SITUACAO)


@bp.route('/prontuario/paciente/<int:cid>/novo', methods=['POST'])
@login_obrigatorio
def doc_novo(cid):
    db = get_db()
    if not db.execute('SELECT 1 FROM clientes WHERE id=?', (cid,)).fetchone():
        abort(404)
    tipo = request.form.get('tipo') or ''
    if tipo not in pm.MODELOS:
        flash('Escolha o tipo de documento.', 'erro')
        return redirect(url_for('pront.paciente', cid=cid))
    aid = request.form.get('atendimento_id') or ''
    atendimento_id = None
    if aid.isdigit() and db.execute('SELECT 1 FROM atendimentos WHERE id=? AND cliente_id=?', (int(aid), cid)).fetchone():
        atendimento_id = int(aid)
    try:
        did = prontuario.criar_doc(db, cid, tipo, g.usuario['usuario'], atendimento_id=atendimento_id, situacao='RASCUNHO')
    except prontuario.ErroProntuario as e:
        flash(str(e), 'erro')
        return redirect(url_for('pront.paciente', cid=cid))
    db.commit()
    flash('Documento criado. Preencha e conclua quando terminar.', 'ok')
    return redirect(url_for('pront.doc', did=did))


# ---------------------------------------------------------------- documento
@bp.route('/prontuario/doc/<int:did>', methods=['GET', 'POST'])
@login_obrigatorio
def doc(did):
    db = get_db()
    d = prontuario.obter_doc(db, did)
    if d is None:
        abort(404)
    prof_padrao = {'nome': d['profissional_nome'] or '', 'conselho': d['profissional_conselho'] or '',
                   'registro': d['profissional_registro'] or ''}
    if request.method == 'POST':
        if d['situacao'] == 'CONCLUIDO':
            flash('Documento concluído não pode ser alterado. A administração pode reabri-lo para correção.', 'erro')
            return redirect(url_for('pront.doc', did=did))
        concluir = request.form.get('acao') == 'concluir'
        try:
            faltas = prontuario.salvar_doc(db, did, request.form, g.usuario['usuario'], concluir=concluir)
        except prontuario.ErroProntuario as e:
            flash(str(e), 'erro')
            return redirect(url_for('pront.doc', did=did))
        db.commit()
        if faltas:
            # o que foi digitado já ficou salvo como rascunho; a tela mostra o que falta
            for falta in faltas:
                flash('Falta preencher: %s.' % falta, 'erro')
            d = prontuario.obter_doc(db, did)
            prof = {'nome': (request.form.get('profissional_nome') or '').strip(),
                    'conselho': (request.form.get('profissional_conselho') or d['profissional_conselho'] or '').strip(),
                    'registro': (request.form.get('profissional_registro') or '').strip()}
            dados = pm.calcular_campos(d['tipo'], pm.ler_form(d['tipo'], request.form, json.loads(d['dados'] or '{}')))
            return _renderizar_doc(d, dados, prof, prontuario.chaves_pendentes(request.form, d))
        if concluir:
            flash('Documento concluído. Imprima e colha a assinatura do profissional.', 'ok')
            return redirect(url_for('pront.doc_imprimir', did=did))
        flash('Rascunho salvo.', 'ok')
        return redirect(url_for('pront.doc', did=did))
    dados = json.loads(d['dados'] or '{}')
    return _renderizar_doc(d, dados, prof_padrao)


@bp.route('/prontuario/doc/<int:did>/imprimir')
@login_obrigatorio
def doc_imprimir(did):
    """Folha A4 para imprimir. ?branco=1 sai com o modelo em branco, para preencher à mão."""
    db = get_db()
    d = prontuario.obter_doc(db, did)
    if d is None:
        abort(404)
    branco = request.args.get('branco') == '1'
    guardados = json.loads(d['dados'] or '{}')
    # em branco: sem respostas, mas com a estrutura do documento (ex.: as perguntas do PNT)
    dados = {k: v for k, v in guardados.items() if k.startswith('_')} if branco else guardados
    prof = {'nome': '', 'conselho': '', 'registro': ''} if branco else {
        'nome': d['profissional_nome'] or '', 'conselho': d['profissional_conselho'] or '',
        'registro': d['profissional_registro'] or ''}
    quando = d['concluido_em'] or d['atualizado_em'] or ''
    por = d['concluido_por'] or d['atualizado_por'] or ''
    return render_template('prontuario_doc_imprimir.html', d=d, modelo=pm.obter(d['tipo']), dados=dados, prof=prof,
                           secoes=pm.secoes_de(d['tipo'], dados), assinaturas=pm.assinaturas_de(d['tipo']),
                           prof_idx=_indice_profissional(pm.assinaturas_de(d['tipo'])), ficha_url=_ficha_original(d, dados),
                           branco=branco, texto_valor=pm.texto_impressao, clinica=config_get('clinica_nome', ''),
                           hoje=util.data_br(date.today().isoformat()), preenchido_por=por if not branco else '',
                           preenchido_em=_quando(quando) if not branco else '', situacoes=prontuario.ROTULO_SITUACAO)


@bp.route('/prontuario/doc/<int:did>/excluir', methods=['POST'])
@admin_obrigatorio
def doc_excluir(did):
    db = get_db()
    d = prontuario.obter_doc(db, did)
    if d is None:
        abort(404)
    cid = d['cliente_id']
    try:
        prontuario.excluir_doc(db, did)
    except prontuario.ErroProntuario as e:
        flash(str(e), 'erro')
        return redirect(url_for('pront.paciente', cid=cid))
    db.commit()
    flash('Documento excluído do prontuário.', 'ok')
    return redirect(url_for('pront.paciente', cid=cid))


@bp.route('/prontuario/doc/<int:did>/reabrir', methods=['POST'])
@admin_obrigatorio
def doc_reabrir(did):
    db = get_db()
    try:
        prontuario.reabrir_doc(db, did, g.usuario['usuario'])
    except prontuario.ErroProntuario as e:
        flash(str(e), 'erro')
        return redirect(url_for('pront.doc', did=did))
    db.commit()
    flash('Documento reaberto para correção. Conclua de novo quando terminar.', 'ok')
    return redirect(url_for('pront.doc', did=did))
