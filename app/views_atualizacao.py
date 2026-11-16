"""Aviso antes da atualização: disparo pela gestão e consulta local (para o instalador ou um script de atualização)."""
import secrets

from flask import Blueprint, abort, current_app, flash, g, jsonify, redirect, request, url_for

from . import atualizacao, login_obrigatorio
from .db import get_db

bp = Blueprint('atu', __name__, url_prefix='/atualizacao')


@bp.route('/pendente')
def pendente():
    """Sem login e só a partir do próprio computador: informa se há aviso de atualização ainda no prazo."""
    if request.remote_addr not in ('127.0.0.1', '::1'):
        abort(403)
    aviso = atualizacao.pendente(get_db())
    if not aviso:
        return jsonify(pendente=False)
    return jsonify(pendente=True, ate=aviso['ate'], prazo_min=aviso['prazo_min'])


@bp.route('/estado')
def estado():
    """Sem login (a tela de espera também usa): segundos para a atualização anunciada e se o sistema está se atualizando."""
    resposta = jsonify(aviso=atualizacao.estado_aviso(get_db()),
                       atualizando=atualizacao.espera_restante(current_app.config['PASTA_DADOS'],
                                                               current_app.config['INICIO_SERVIDOR']))
    resposta.headers['Cache-Control'] = 'no-store'
    return resposta


@bp.route('/iniciar', methods=['POST'])
def iniciar():
    """O instalador, no computador-base, pede o aviso de 3 minutos. Só local e só com a chave do servidor
    (lida do arquivo de dados pelo instalador); responde o número de segundos que ele deve esperar."""
    chave = request.headers.get('X-Chave', '')
    if request.remote_addr not in ('127.0.0.1', '::1') or not chave or \
            not secrets.compare_digest(chave.encode(), current_app.config['SECRET_KEY'].encode()):
        abort(403)
    segundos = atualizacao.iniciar_pelo_instalador(get_db())
    return str(segundos), 200, {'Content-Type': 'text/plain; charset=utf-8'}


@bp.route('/avisar', methods=['POST'])
@login_obrigatorio
def avisar():
    """Gestão dispara o aviso (administração, gerência ou quem tem o módulo de backup)."""
    if not (g.usuario['admin'] or 'gerencia' in g.modulos or 'backup' in g.modulos):
        abort(403)
    try:
        r = atualizacao.disparar(get_db(), g.usuario['usuario'], request.form.get('prazo', atualizacao.PRAZO_PADRAO))
        flash('Aviso enviado a %d usuário(s). O prazo termina às %s.' % (r['destinatarios'], r['ate']), 'ok')
    except atualizacao.ErroAtualizacao as e:
        flash(str(e), 'erro')
    return redirect(url_for('admin.backup'))
