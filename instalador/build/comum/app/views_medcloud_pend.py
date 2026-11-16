"""Pendências Medcloud: anexos e laudos de cada estudo criado, envio dos arquivos pelo robô e marcação de "enviado"/"entregue"."""
from flask import Blueprint, abort, flash, g, jsonify, redirect, render_template, request, url_for

from . import login_obrigatorio, medcloud, medcloud_envios as envios
from .db import get_db

bp = Blueprint('mpend', __name__)


def _volta():
    """Volta para a lista mantendo o filtro."""
    return redirect(url_for('mpend.lista', mostrar=request.form.get('mostrar') or None, q=request.form.get('q') or None))


@bp.route('/medcloud/pendencias')
@login_obrigatorio
def lista():
    db = get_db()
    mostrar = 'todos' if request.args.get('mostrar') == 'todos' else 'pendentes'
    busca = (request.args.get('q') or '').strip()
    itens = envios.pendencias(db, mostrar, busca)
    return render_template('medcloud_pendencias.html', itens=itens, mostrar=mostrar, q=busca, tipos=envios.TIPOS,
                           assinatura=envios.assinatura_do_andamento(db), robo_ligado=medcloud.operando(db),
                           extensoes=sorted(envios.EXTENSOES), max_mb=envios.MAX_BYTES // (1024 * 1024),
                           a_liberar=envios.resumo_enviados(db) if g.usuario['admin'] else (0, 0))


@bp.route('/medcloud/pendencias/andamento')
@login_obrigatorio
def andamento():
    """Assinatura do andamento da fila de envios: a tela recarrega sozinha quando ela muda."""
    return jsonify({'assinatura': envios.assinatura_do_andamento(get_db())})


@bp.route('/medcloud/pendencias/<int:aid>/enviar', methods=['POST'])
@login_obrigatorio
def enviar(aid):
    db = get_db()
    tipo = request.form.get('tipo', '')
    arquivos = [a for a in request.files.getlist('arquivo') if a and a.filename]
    if not arquivos:
        flash('Selecione o arquivo a enviar.', 'erro')
        return _volta()
    enviados, falhas = 0, []
    for arq in arquivos:
        try:
            envios.adicionar(db, aid, tipo, arq.filename, arq.read(), g.usuario['usuario'])
            enviados += 1
        except envios.ErroEnvio as exc:
            falhas.append('%s: %s' % (arq.filename, exc))
    if enviados:
        medcloud.acordar()   # o robô leva os arquivos ao estudo em segundo plano
        flash('%d arquivo(s) na fila para a Medcloud. O robô envia em segundo plano; a situação aparece aqui.' % enviados, 'ok')
        if not medcloud.operando(db):
            flash('A integração com a Medcloud está desligada ou fora do horário de funcionamento: os arquivos ficam na fila '
                  'até o robô voltar.', 'aviso')
    for f in falhas:
        flash(f, 'erro')
    return _volta()


@bp.route('/medcloud/pendencias/<int:aid>/marcar', methods=['POST'])
@login_obrigatorio
def marcar(aid):
    tipo = request.form.get('tipo', '')
    feito = request.form.get('acao') != 'reabrir'
    try:
        no_mapa = envios.marcar(get_db(), aid, tipo, g.usuario['usuario'], feito)
    except envios.ErroEnvio as exc:
        flash(str(exc), 'erro')
        return _volta()
    nome = 'Anexos' if tipo == 'ANEXO' else 'Laudos'
    texto = '%s marcados como %s.' % (nome, ('enviados' if tipo == 'ANEXO' else 'entregues') if feito else 'pendentes de novo')
    if no_mapa:
        texto += ' %d exame(s) no mapa de laudos passaram para Entregue.' % no_mapa
    flash(texto, 'ok')
    return _volta()


@bp.route('/medcloud/envios/<int:eid>/tentar', methods=['POST'])
@login_obrigatorio
def tentar(eid):
    if envios.tentar_de_novo(get_db(), eid):
        medcloud.acordar()
        flash('Arquivo recolocado na fila do robô.', 'ok')
    return _volta()


@bp.route('/medcloud/envios/<int:eid>/remover', methods=['POST'])
@login_obrigatorio
def remover(eid):
    if envios.remover(get_db(), eid):
        flash('Arquivo retirado da fila.', 'ok')
    else:
        flash('Só dá para retirar arquivo que ainda não foi enviado (na fila ou com erro).', 'erro')
    return _volta()


@bp.route('/medcloud/envios/<int:eid>/arquivo')
@login_obrigatorio
def baixar(eid):
    """Baixa o arquivo guardado (para conferir o que foi mandado ao estudo)."""
    from urllib.parse import quote

    from flask import Response
    db = get_db()
    envio = db.execute('SELECT id, anexo_id, arquivo_nome, content_type, estado FROM medcloud_envios WHERE id=?', (eid,)).fetchone()
    if not envio:
        abort(404)
    conteudo = envios.conteudo_do_envio(db, envio)
    if conteudo is None and envio['estado'] == 'OK':
        # já foi para a Medcloud e saiu do banco de anexos: o robô busca de volta na nuvem
        if not medcloud.operando(db):
            flash('Este arquivo está só na Medcloud. Para baixar, a integração com a Medcloud precisa estar ligada e dentro do '
                  'horário de funcionamento.', 'aviso')
            return redirect(request.referrer or url_for('mpend.lista'))
        conteudo, motivo = _baixar_da_medcloud(db, eid)
        if conteudo is None:
            flash(motivo, 'erro')
            return redirect(request.referrer or url_for('mpend.lista'))
    if conteudo is None:
        abort(404)
    resp = Response(conteudo, mimetype=envio['content_type'] or 'application/octet-stream')
    resp.headers['Content-Disposition'] = "attachment; filename*=UTF-8''%s" % quote(envio['arquivo_nome'])
    return resp


def _baixar_da_medcloud(db, eid):
    """Pede ao robô o arquivo e espera (até ESPERA_DOWNLOAD_S). Devolve (bytes, None) ou (None, motivo para mostrar)."""
    import os
    import time
    if not envios.pedir_download(db, eid):
        return None, 'Não foi possível pedir este arquivo à Medcloud.'
    medcloud.acordar()
    caminho = envios.arquivo_baixado(db, eid)
    fim = time.monotonic() + envios.ESPERA_DOWNLOAD_S
    estado, erro = 'PEDIDO', None
    while time.monotonic() < fim:
        db.rollback()   # enxerga o que o robô gravou em outra conexão
        r = db.execute('SELECT download_estado, download_erro FROM medcloud_envios WHERE id=?', (eid,)).fetchone()
        estado, erro = (r['download_estado'], r['download_erro']) if r else (None, None)
        if estado in ('PRONTO', 'ERRO'):
            break
        time.sleep(0.5)
    if estado == 'PRONTO' and caminho and os.path.exists(caminho):
        with open(caminho, 'rb') as f:
            conteudo = f.read()
        try:
            os.remove(caminho)
        except OSError:
            pass
        db.execute('UPDATE medcloud_envios SET download_estado=NULL WHERE id=?', (eid,))
        db.commit()
        return conteudo, None
    db.execute("UPDATE medcloud_envios SET download_estado=NULL WHERE id=? AND download_estado IN ('PEDIDO','PRONTO','ERRO')", (eid,))
    db.commit()
    if estado == 'ERRO':
        return None, 'A Medcloud não entregou o arquivo: %s' % (erro or 'erro desconhecido')
    return None, 'A Medcloud demorou para responder. Tente de novo em instantes.'


@bp.route('/medcloud/envios/limpar-enviados', methods=['POST'])
@login_obrigatorio
def limpar_enviados():
    """Tira do banco de anexos os arquivos que já estão na Medcloud (só administrador)."""
    if not g.usuario['admin']:
        flash('Só o administrador pode limpar os arquivos já enviados.', 'erro')
        return _volta()
    qtd, bytes_ = envios.limpar_enviados(get_db())
    flash('%d arquivo(s) já enviados à Medcloud saíram do banco de anexos (%.1f MB liberados).' % (qtd, bytes_ / 1048576), 'ok')
    return _volta()
