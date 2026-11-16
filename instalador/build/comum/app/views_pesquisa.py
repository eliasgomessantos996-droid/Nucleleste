"""Página pública da pesquisa de satisfação: o cliente abre pelo QR Code, sem login, e só dentro da rede interna da clínica."""
from flask import Blueprint, redirect, render_template, request, url_for

from . import pesquisa as pesq
from .db import agora, config_get, get_db

bp = Blueprint('pesq', __name__)


def _tela(modo, status=200, **extra):
    return render_template('pesquisa_publica.html', modo=modo, clinica=config_get('clinica_nome', ''), **extra), status


def _avisar_gerencia(db, rid):
    """Avisa a gerência, pelo contato do sistema, que chegou uma avaliação (só a nota, sem o que o cliente escreveu)."""
    from . import avisos
    de = avisos.sistema_id(db)
    r = db.execute('SELECT nota FROM cq_sat_respostas WHERE id=?', (rid,)).fetchone()
    if de is None or r is None:
        return
    corpo = ('Nova avaliação da pesquisa de satisfação: nota %.1f de 10. Quer abrir a avaliação agora?' % r['nota'])
    destino = url_for('qual.satisf_respostas') + '#resposta-%d' % rid
    for para in avisos.gerentes(db):
        db.execute('INSERT INTO chat_mensagens (de_id, para_id, corpo, criado_em, acao, acao_url) VALUES (?,?,?,?,?,?)',
                   (de, para, corpo, agora(), 'AVALIACAO_VER', destino))
    db.commit()


@bp.route('/pesquisa', methods=['GET', 'POST'])
def publica():
    db = get_db()
    if not pesq.ip_interno(request.remote_addr):
        return _tela('fora', 403)
    pesq.garantir(db)
    if not pesq.ativa(db):
        return _tela('encerrada')
    erro = ''
    if request.method == 'POST':
        try:
            rid = pesq.registrar_resposta(db, request.form, request.remote_addr)
            _avisar_gerencia(db, rid)
            return redirect(url_for('pesq.obrigado'))
        except pesq.ErroPesquisa as e:
            erro = str(e)
    return _tela('form', perguntas=pesq.perguntas(db), opcoes=pesq.OPCOES, erro=erro, f=request.form,
                 exames=pesq.exames_ativos(db), atendimentos=pesq.ATENDIMENTOS, respondentes=pesq.RESPONDENTES)


@bp.route('/pesquisa/obrigado')
def obrigado():
    if not pesq.ip_interno(request.remote_addr):
        return _tela('fora', 403)
    return _tela('obrigado')
