"""NucleAI: o botão redondo começa uma conversa de ajuda nas Mensagens; botões dos pedidos de ajuda à gerência."""
from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from . import ajuda, login_obrigatorio, modulos
from . import nucleai_comandos as cmds
from .db import get_db

bp = Blueprint('ajuda', __name__, url_prefix='/ajuda')


@bp.route('/iniciar', methods=['POST'])
@login_obrigatorio
def iniciar():
    db = get_db()
    bot = ajuda.bot_id(db)
    if bot is None:
        flash('A assistente NucleAI não está disponível. Reinicie o programa.', 'erro')
        return redirect(url_for('inicio.painel'))
    if not ajuda.ativa(db):
        flash('A NucleAI está desligada no momento. Procure a administração para ajuda.', 'erro')
        return redirect(request.referrer or url_for('inicio.painel'))
    ajuda.iniciar(db, g.usuario['id'])
    return redirect(url_for('chat.conversa', com=bot))


@bp.route('/tutorial-visto', methods=['POST'])
@login_obrigatorio
def tutorial_visto():
    """O usuário concluiu ou dispensou o tutorial: ele não abre mais sozinho (continua disponível em Minha conta)."""
    db = get_db()
    db.execute('UPDATE usuarios SET tutorial_visto=1 WHERE id=?', (g.usuario['id'],))
    db.commit()
    return ('', 204)


@bp.route('/chamado/<int:cid>/contatar', methods=['POST'])
@login_obrigatorio
def contatar(cid):
    """Botão da mensagem da NucleAI para a gerência: abre a conversa com o usuário, com uma pergunta pronta."""
    db = get_db()
    eu = g.usuario['id']
    recebeu = db.execute("SELECT 1 FROM chat_mensagens WHERE chamado_id=? AND para_id=? AND acao='CHAMADO_FALAR'", (cid, eu)).fetchone()
    if not (recebeu or g.usuario['admin'] or 'gerencia' in g.modulos):
        flash('Este pedido de ajuda não foi enviado para você.', 'erro')
        return redirect(url_for('chat.conversa'))
    try:
        usuario_id, _msg, aviso = ajuda.contatar_chamado(db, cid, eu)
        db.commit()
    except ValueError as e:
        flash(str(e), 'erro')
        return redirect(url_for('chat.conversa'))
    if aviso:
        flash(aviso, 'ok')
    return redirect(url_for('chat.conversa', com=usuario_id))


@bp.route('/chamado/<int:cid>/confirmar', methods=['POST'])
@login_obrigatorio
def confirmar(cid):
    """Botões Sim/Não da pergunta da gerência ao usuário."""
    db = get_db()
    eu = g.usuario['id']
    ch = db.execute('SELECT atendido_por_id FROM ajuda_chamados WHERE id=?', (cid,)).fetchone()
    try:
        texto = ajuda.confirmar_chamado(db, cid, eu, 'SIM' if request.form.get('resposta') == 'SIM' else 'NAO')
        db.commit()
        flash(texto, 'ok')
    except ValueError as e:
        flash(str(e), 'erro')
    return redirect(url_for('chat.conversa', com=ch['atendido_por_id']) if ch and ch['atendido_por_id'] else url_for('chat.conversa'))


# ------------------------------------------------------------------ pedidos (comandos) da NucleAI
@bp.route('/comando/<int:pid>/responder', methods=['POST'])
@login_obrigatorio
def comando_responder(pid):
    """Botões Sim/Não de um pedido da NucleAI. Com Sim, o resultado aparece no chat e, se houver tela para abrir, ela abre (em outra aba)."""
    db = get_db()
    bot = ajuda.bot_id(db)
    try:
        r = cmds.resolver(db, g.usuario['id'], pid, request.form.get('resposta') == 'SIM', 'botao')
    except cmds.ErroComando as e:
        flash(str(e), 'erro')
        return redirect(url_for('chat.conversa', com=bot) if bot else url_for('inicio.painel'))
    url = r.get('url')
    if url and url.startswith('/') and not url.startswith('//'):
        return redirect(url)
    return redirect(url_for('chat.conversa', com=bot) if bot else url_for('inicio.painel'))


@bp.route('/imprimir')
@login_obrigatorio
def imprimir_pdf():
    """Mostra um PDF do próprio sistema e já abre a janela de impressão (usado pelos pedidos de impressão da NucleAI)."""
    alvo = request.args.get('u', '')
    if not alvo.startswith('/') or alvo.startswith('//') or ':' in alvo.split('?')[0]:
        abort(404)
    return render_template('nucleai_imprimir.html', alvo=alvo)


@bp.route('/comandos', methods=['GET', 'POST'])
@login_obrigatorio
def comandos():
    """Gerência: quem pode pedir o quê à NucleAI (e desligar comandos). Alto risco é só da gerência; o resto a gerência decide."""
    db = get_db()
    cmds.garantir(db)
    if request.method == 'POST':
        try:
            for c in cmds.COMANDOS:
                padrao = cmds.modo_de(db, c)
                cmds.salvar_config(db, c, request.form.get('modo_' + c.chave) or padrao,
                                   [i for i in request.form.getlist('usuarios_' + c.chave) if i.isdigit()])
            flash('Permissões dos comandos da NucleAI salvas.', 'ok')
        except cmds.ErroComando as e:
            flash(str(e), 'erro')
        return redirect(url_for('ajuda.comandos'))
    usuarios = db.execute("SELECT id, usuario FROM usuarios WHERE ativo=1 AND COALESCE(sistema,0)=0 ORDER BY usuario").fetchall()
    grupos = []
    for risco in (cmds.BAIXO, cmds.MEDIO, cmds.ALTO):
        itens = [{'c': c, 'modo': cmds.modo_de(db, c), 'escolhidos': cmds.escolhidos(db, c)} for c in cmds.COMANDOS if c.risco == risco]
        grupos.append({'risco': risco, 'rotulo': cmds.ROTULO_RISCO[risco], 'itens': itens})
    return render_template('nucleai_comandos.html', grupos=grupos, usuarios=usuarios, nomes_modulos=modulos.NOMES)
