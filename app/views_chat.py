"""Mensagens livres: conversa entre quaisquer usuários, com avisos na hora.

Tempo real: a consulta /novas pode esperar até ESPERA_MAX segundos por novidade (conexão que "segura" a resposta). Assim a
mensagem chega na hora, sem o navegador perguntar a cada 2 segundos. O número de esperas simultâneas é limitado; passando
do limite, a consulta volta na hora (consulta curta, como antes).
"""
import threading
import time
from datetime import date

import io

from flask import Blueprint, abort, flash, g, jsonify, redirect, render_template, request, send_file, url_for

from . import chat, encerrar_sessao_substituida, login_obrigatorio, nucleai_arquivos, nucleai_ilustrar, presenca, sessao_substituida
from .db import get_db

bp = Blueprint('chat', __name__, url_prefix='/mensagens')

ESPERA_MAX = 15            # segundos que uma consulta pode esperar por novidade
PASSO_ESPERA = 1.0         # verificação de segurança: a espera acorda antes, na hora, quando alguém grava algo (_avisar)
_vagas_de_espera = threading.BoundedSemaphore(24)
ESPERAS_POR_USUARIO = 3    # abas de uma mesma pessoa esperando ao mesmo tempo (as demais consultam por intervalos)
_esperas_do_usuario = {}
_trava_esperas = threading.Lock()
_novidade = threading.Condition()


def _avisar():
    """Acorda as consultas em espera: chegou mensagem, aviso de digitando ou leitura. Evita consultar o banco a cada passo."""
    with _novidade:
        _novidade.notify_all()


def _reservar_espera(uid):
    """Reserva uma espera para o usuário e uma vaga geral. Devolve a função que libera, ou None se não houver vaga."""
    with _trava_esperas:
        if _esperas_do_usuario.get(uid, 0) >= ESPERAS_POR_USUARIO:
            return None
        if not _vagas_de_espera.acquire(blocking=False):
            return None
        _esperas_do_usuario[uid] = _esperas_do_usuario.get(uid, 0) + 1

    def liberar():
        with _trava_esperas:
            _esperas_do_usuario[uid] -= 1
            if _esperas_do_usuario[uid] <= 0:
                _esperas_do_usuario.pop(uid, None)
            _vagas_de_espera.release()
    return liberar


def _inteiro(nome, padrao=0):
    bruto = request.values.get(nome, '')
    return int(bruto) if bruto.isdigit() else padrao


def _contato_json(c):
    return {k: c[k] for k in ('id', 'nome', 'gestao', 'nao_lidas', 'previa', 'ultima_em', 'ultima_minha', 'iniciais', 'cor',
                              'online', 'visto', 'avatar')}


@bp.route('')
@login_obrigatorio
def conversa():
    db = get_db()
    eu = g.usuario['id']
    lista = chat.contatos(db, eu)
    pode_transmitir = chat.pode_transmitir(db, eu)
    canais = chat.canais(db, eu) if pode_transmitir else []
    canal_id = _inteiro('canal')
    canal_atual = next((c for c in canais if c['id'] == canal_id), None)
    if canal_id and canal_atual is None:
        abort(404)
    com = _inteiro('com')
    atual, mensagens = None, []
    if com and not canal_atual:
        atual = next((c for c in lista if c['id'] == com), None)
        if atual is None:
            abort(404)
        mensagens = chat.conversa(db, eu, com)
        chat.marcar_lidas(db, eu, com)
        atual = dict(atual, nao_lidas=0)
        lista = [dict(c, nao_lidas=0) if c['id'] == com else c for c in lista]
    return render_template('chat.html', contatos=lista, atual=atual, hoje=date.today().isoformat(),
                           mensagens=chat.serializar_lista(db, mensagens, eu),
                           ultimo_id=mensagens[-1]['id'] if mensagens else 0,
                           primeiro_id=mensagens[0]['id'] if mensagens else 0,
                           lidas_n=chat.contar_lidas(db, eu, com) if com else 0,
                           pode_transmitir=pode_transmitir, canais=canais, canal_atual=canal_atual,
                           destinatarios=chat.destinatarios_canal(db, eu) if pode_transmitir else [])


@bp.route('/canais/salvar', methods=['POST'])
@login_obrigatorio
def canal_salvar():
    db = get_db()
    if not chat.pode_transmitir(db, g.usuario['id']):
        abort(403)
    try:
        cid = chat.salvar_canal(db, g.usuario['id'], _inteiro('canal'), request.form.get('nome'), request.form.getlist('membros'))
    except chat.ErroChat as erro:
        flash(str(erro), 'erro')
        return redirect(url_for('chat.conversa'))
    flash('Grupo de transmissão salvo.', 'ok')
    return redirect(url_for('chat.conversa', canal=cid))


@bp.route('/canais/<int:cid>/excluir', methods=['POST'])
@login_obrigatorio
def canal_excluir(cid):
    db = get_db()
    if not chat.pode_transmitir(db, g.usuario['id']):
        abort(403)
    try:
        chat.excluir_canal(db, g.usuario['id'], cid)
    except chat.ErroChat:
        abort(404)
    flash('Grupo excluído. As mensagens individuais enviadas foram mantidas.', 'ok')
    return redirect(url_for('chat.conversa'))


@bp.route('/canais/<int:cid>/enviar', methods=['POST'])
@login_obrigatorio
def canal_enviar(cid):
    db = get_db()
    if not chat.pode_transmitir(db, g.usuario['id']):
        abort(403)
    try:
        n = chat.transmitir(db, g.usuario['id'], cid, request.form.get('corpo'))
    except chat.ErroChat as erro:
        flash(str(erro), 'erro')
    else:
        _avisar()
        flash('Mensagem enviada individualmente para %d pessoa(s).' % n, 'ok')
    return redirect(url_for('chat.conversa', canal=cid))


@bp.route('/enviar', methods=['POST'])
@login_obrigatorio
def enviar():
    db = get_db()
    eu = g.usuario['id']
    arq_img = request.files.get('imagem')
    imagem = nome_img = None
    if arq_img and arq_img.filename:
        imagem = arq_img.read(chat.IMAGEM_MAX + 1)   # lê no máximo 1 byte a mais que o limite
        nome_img = arq_img.filename
    arq_doc = request.files.get('arquivo')
    arquivo = nome_arq = None
    if arq_doc and arq_doc.filename:
        arquivo = arq_doc.read(nucleai_arquivos.ARQUIVO_MAX + 1)
        nome_arq = arq_doc.filename
    try:
        m = chat.enviar(db, eu, _inteiro('para'), request.form.get('corpo'), responde_id=_inteiro('responde_id') or None,
                        imagem=imagem, imagem_nome=nome_img, arquivo=arquivo, arquivo_nome=nome_arq)
    except chat.ErroChat as erro:
        return jsonify(erro=str(erro)), 400
    _avisar()
    # conversa com a NucleAI: as respostas dela já vêm junto (aparecem sem esperar a consulta periódica)
    return jsonify(mensagem=chat.serializar_lista(db, [m], eu)[0], respostas=chat.serializar_lista(db, m.get('_respostas', []), eu),
                   encerrado=bool(m.get('_encerrado')))


@bp.route('/<int:mid>/acao', methods=['POST'])
@login_obrigatorio
def responder_acao(mid):
    """Sim/Não de uma mensagem com ação (ex.: "abrir a avaliação"). Só o destinatário responde, uma vez."""
    db = get_db()
    m = db.execute('SELECT * FROM chat_mensagens WHERE id=?', (mid,)).fetchone()
    if m is None or m['para_id'] != g.usuario['id'] or m['acao'] not in ('AVALIACAO_VER', 'AGENDA_VER') or not m['acao_url']:
        abort(404)
    resposta = 'SIM' if request.form.get('resposta') == 'SIM' else 'NAO'
    if not m['acao_resp']:
        db.execute('UPDATE chat_mensagens SET acao_resp=? WHERE id=?', (resposta, mid))
        db.commit()
    return jsonify(ok=True, resposta=m['acao_resp'] or resposta, url=m['acao_url'])


@bp.route('/anexo/<int:mid>')
@login_obrigatorio
def anexo(mid):
    """Imagem de uma mensagem: só para quem enviou ou recebeu; some 24 h depois do envio."""
    achado = chat.imagem_da_mensagem(get_db(), g.usuario['id'], mid)
    if achado is None:
        abort(404)
    conteudo, tipo = achado
    resp = send_file(io.BytesIO(conteudo), mimetype=tipo, max_age=0)
    resp.headers['Cache-Control'] = 'private, max-age=3600'
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    return resp


@bp.route('/ilustracao/<int:iid>/excel')
@login_obrigatorio
def ilustracao_excel(iid):
    """Baixa uma planilha ilustrada pela NucleAI em formato Excel (.xlsx), somente para o destinatário."""
    try:
        res = nucleai_ilustrar.gerar_excel(
            get_db(),
            g.usuario['id'],
            iid,
            pode_treino='gerencia' in getattr(g, 'modulos', ()),
        )
    except PermissionError:
        abort(403)
    if res is None:
        abort(404)
    conteudo, nome = res
    return send_file(
        io.BytesIO(conteudo),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=nome,
        max_age=0,
    )


@bp.route('/digitando', methods=['POST'])
@login_obrigatorio
def digitando():
    """Aviso de que a pessoa está digitando para `para` (dura poucos segundos)."""
    chat.digitando_agora(g.usuario['id'], _inteiro('para'))
    _avisar()
    return '', 204


@bp.route('/buscar')
@login_obrigatorio
def buscar():
    """Pesquisa dentro da conversa aberta."""
    achadas = chat.buscar(get_db(), g.usuario['id'], _inteiro('com'), request.args.get('q', ''))
    return jsonify(resultados=achadas, limite=chat.LIMITE_BUSCA)


def _aguardar_novidade(db, eu, depois, com, depois_conv, lidas_n, digitando_antes, espera):
    """Segura a resposta até chegar algo novo (ou o prazo acabar). Só consulta o necessário a cada passo."""
    fim = time.monotonic() + espera
    while True:
        u = db.execute('SELECT * FROM usuarios WHERE id=?', (eu,)).fetchone()
        if u is None or sessao_substituida(u):
            return
        if chat.novas_para(db, eu, depois):
            return
        if com:
            if chat.conversa(db, eu, com, depois=depois_conv):
                return
            if chat.contar_lidas(db, eu, com) != lidas_n or chat.esta_digitando(com, eu) != digitando_antes:
                return
        restante = fim - time.monotonic()
        if restante <= 0:
            return
        with _novidade:
            _novidade.wait(min(PASSO_ESPERA, restante))


@bp.route('/novas')
@login_obrigatorio
def novas():
    """Uma única consulta alimenta o contador do menu, os avisos e a conversa aberta.
    Com `espera=N` ela só responde quando houver novidade (até N segundos): é o "tempo real"."""
    db = get_db()
    eu = g.usuario['id']
    depois = _inteiro('depois')
    com = _inteiro('com')
    espera = min(_inteiro('espera'), ESPERA_MAX)
    concedida = None
    if espera:
        liberar = _reservar_espera(eu)
        concedida = liberar is not None
        if concedida:
            try:
                _aguardar_novidade(db, eu, depois, com, _inteiro('depois_conv'), _inteiro('lidas_n'),
                                   request.values.get('dig') == '1', espera)
            finally:
                liberar()
    u = db.execute('SELECT * FROM usuarios WHERE id=?', (eu,)).fetchone()
    if u is None or not u['ativo'] or sessao_substituida(u):
        return encerrar_sessao_substituida()
    carga = {'espera': concedida}   # False = sem vaga de espera agora: o navegador espaça as consultas
    recebidas = chat.novas_para(db, eu, depois)
    carga['novas'] = recebidas
    carga['ultimo'] = recebidas[-1]['id'] if recebidas else depois
    if com:
        msgs = chat.conversa(db, eu, com, depois=_inteiro('depois_conv'))
        carga['conversa'] = chat.serializar_lista(db, msgs, eu)
        if request.values.get('visivel') == '1':
            chat.marcar_lidas(db, eu, com)
            _avisar()
        carga['lidas'] = chat.ids_lidos(db, eu, com, _inteiro('desde'))
        carga['lidas_n'] = chat.contar_lidas(db, eu, com)
        carga['digitando'] = chat.esta_digitando(com, eu)
    if request.values.get('lista') == '1':
        carga['contatos'] = [_contato_json(c) for c in chat.contatos(db, eu)]
    carga['nao_lidas'] = chat.nao_lidas_total(db, eu)
    # situação de todas as pessoas, em qualquer tela (a lista de conversas, a conversa aberta e os [data-presenca])
    carga['presenca'] = presenca.situacao(db)
    if request.values.get('resumo') == '1':
        carga['resumo'] = chat.resumo_nao_lidas(db, eu)
    return jsonify(carga)
