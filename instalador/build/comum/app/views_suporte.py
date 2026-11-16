"""Suporte ao desenvolvedor: todo usuário envia sugestões e correções de bugs; o desenvolvedor (e o administrador) vê os formulários,
aceita ou recusa, guarda os aceitos na pasta da próxima atualização e gera o relatório em PDF."""
import io

from flask import Blueprint, abort, flash, g, redirect, render_template, request, send_file, url_for

from . import chat, login_obrigatorio, modulos, suporte, suporte_docs, versao
from .db import config_get, get_db

bp = Blueprint('sup', __name__, url_prefix='/suporte')


def _telas():
    """Nomes das telas que a pessoa enxerga, para o campo "Em qual tela?" (são só sugestões do campo; dá para digitar outra)."""
    vistos, saida = set(), []
    for _grupo, mod, rotulo, _ep in modulos.telas():
        if rotulo not in vistos and modulos._permitido(g.usuario, g.modulos, mod):
            vistos.add(rotulo)
            saida.append(rotulo)
    return saida


def _sou_dev():
    return suporte.usuario_dev_id(get_db()) == g.usuario['id']


def _tela_formulario(tipo, f=None):
    db = get_db()
    return render_template('suporte_form.html', tipo=tipo, f=f or {}, meus=suporte.do_usuario(db, g.usuario['id'], tipo), telas=_telas(),
                           gravidades=suporte.GRAVIDADES, limites=suporte.LIMITES, sou_dev=_sou_dev(), temas=suporte.TEMAS)


def _enviar(tipo):
    f = {k: request.form.get(k, '') for k in ('titulo', 'tela', 'descricao', 'passos', 'gravidade', 'tema')}
    db = get_db()
    cliente = {k[3:]: v for k, v in request.form.items() if k.startswith('cl_')}   # dados que só o navegador sabe (tela, fuso, aparelho...)
    meta = suporte.montar_meta(db, g.usuario['usuario'], request.headers, request.remote_addr, request.headers.get('X-Forwarded-For'), cliente,
                               sorted(g.modulos) if g.get('modulos') else [], versao())
    try:
        suporte.enviar(db, g.usuario['id'], g.usuario['usuario'], tipo, f['titulo'], f['descricao'], f['tela'], f['passos'], f['gravidade'], f['tema'], meta)
    except suporte.ErroSuporte as e:
        db.rollback()
        flash(str(e), 'erro')
        return _tela_formulario(tipo, f)   # mantém o que a pessoa já digitou
    flash('Enviado ao desenvolvedor. Obrigado!' if tipo == suporte.SUGESTAO else 'Correção de bug enviada ao desenvolvedor, com prioridade. Obrigado!', 'ok')
    return redirect(url_for('sup.sugestao' if tipo == suporte.SUGESTAO else 'sup.bug'))


# ------------------------------------------------------------------ todos os usuários
@bp.route('')
@login_obrigatorio
def sugestao():
    return _tela_formulario(suporte.SUGESTAO)


@bp.route('/sugestao', methods=['POST'])
@login_obrigatorio
def sugestao_enviar():
    return _enviar(suporte.SUGESTAO)


@bp.route('/bug')
@login_obrigatorio
def bug():
    return _tela_formulario(suporte.BUG)


@bp.route('/bug', methods=['POST'])
@login_obrigatorio
def bug_enviar():
    return _enviar(suporte.BUG)


# ------------------------------------------------------------------ desenvolvedor (módulo suporte_dev)
@bp.route('/recebidos')
@login_obrigatorio
def recebidos():
    db = get_db()
    novos = suporte.recebidos(db, suporte.NOVA)
    return render_template('suporte_recebidos.html', bugs=[i for i in novos if i['tipo'] == suporte.BUG],
                           sugestoes=[i for i in novos if i['tipo'] != suporte.BUG], resumo=suporte.resumo(db),
                           recusados=suporte.recebidos(db, suporte.RECUSADA) if request.args.get('mostrar') == 'recusados' else [])


@bp.route('/<int:iid>/decidir', methods=['POST'])
@login_obrigatorio
def decidir(iid):
    db = get_db()
    decisao = request.form.get('decisao')
    if decisao not in ('aceitar', 'recusar'):
        abort(400)
    try:
        suporte.decidir(db, iid, decisao == 'aceitar', g.usuario['usuario'])
    except suporte.ErroSuporte as e:
        db.rollback()
        flash(str(e), 'erro')
        return redirect(url_for('sup.recebidos'))
    if decisao == 'aceitar':
        flash('Aceito: foi para a pasta da próxima atualização.', 'ok')
    else:
        # não aceitar: abre a conversa nas Mensagens com quem enviou, já com o cartão especial citando o que a pessoa escreveu
        item = suporte._dict(suporte._item(db, iid))
        try:
            chat.enviar_cartao(db, g.usuario['id'], item['usuario_id'], suporte.cartao_recusa(item, g.usuario['usuario']),
                               'Sua %s “%s” não foi aceita.' % ('correção de bug' if item['tipo'] == suporte.BUG else 'sugestão', item['titulo']))
            flash('Não aceito. Explique para %s por que não foi aceita; o cartão com a mensagem dela já está na conversa.' % item['usuario'], 'ok')
            return redirect(url_for('chat.conversa', com=item['usuario_id']))
        except chat.ErroChat:
            flash('Não aceito, mas não foi possível abrir a conversa (a pessoa não está mais ativa).', 'aviso')
    return redirect(url_for('sup.recebidos', **({'mostrar': 'recusados'} if request.form.get('mostrar') == 'recusados' else {})))


@bp.route('/pasta')
@login_obrigatorio
def pasta():
    db = get_db()
    p = suporte.pasta(db)
    return render_template('suporte_pasta.html', pasta=p, bugs=[i for i in p['pendentes'] if i['tipo'] == suporte.BUG],
                           sugestoes=[i for i in p['pendentes'] if i['tipo'] != suporte.BUG], limites=suporte.LIMITES, versao_atual=versao(),
                           novos=suporte.contar_novos(db))


@bp.route('/<int:iid>/texto', methods=['POST'])
@login_obrigatorio
def texto_salvar(iid):
    db = get_db()
    try:
        suporte.salvar_texto(db, iid, request.form.get('texto'))
        flash('Texto da atualização salvo.', 'ok')
    except suporte.ErroSuporte as e:
        db.rollback()
        flash(str(e), 'erro')
    return redirect(url_for('sup.pasta') + '#item-%d' % iid)


@bp.route('/<int:iid>/situacao', methods=['POST'])
@login_obrigatorio
def situacao(iid):
    """Na pasta: marcar como aplicado, desfazer a aplicação ou devolver para a análise (também de um recusado)."""
    db = get_db()
    acao = request.form.get('acao')
    try:
        if acao == 'aplicada':
            suporte.marcar_aplicada(db, iid, request.form.get('versao'))
            flash('Marcado como aplicado na atualização.', 'ok')
        elif acao == 'desfazer':
            suporte.desfazer_aplicacao(db, iid)
            flash('A aplicação foi desfeita: o item voltou para a pasta.', 'ok')
        elif acao == 'voltar':
            suporte.voltar_para_analise(db, iid)
            flash('Voltou para análise em “Formulários recebidos”.', 'ok')
        else:
            abort(400)
    except suporte.ErroSuporte as e:
        db.rollback()
        flash(str(e), 'erro')
    if acao == 'voltar' and request.form.get('mostrar') == 'recusados':
        return redirect(url_for('sup.recebidos', mostrar='recusados'))
    return redirect(url_for('sup.recebidos' if acao == 'voltar' and request.form.get('de') == 'recebidos' else 'sup.pasta'))


@bp.route('/aplicar-todas', methods=['POST'])
@login_obrigatorio
def aplicar_todas():
    n = suporte.aplicar_todas(get_db(), request.form.get('versao'))
    g.detalhe_auditoria = 'aplicados=%d; versão=%s' % (n, (request.form.get('versao') or '').strip())
    flash('%d item(ns) marcado(s) como aplicado(s).' % n if n else 'Não há itens aceitos para marcar.', 'ok' if n else 'aviso')
    return redirect(url_for('sup.pasta'))


@bp.route('/dados')
@login_obrigatorio
def dados():
    """Dados protegidos (só o desenvolvedor): respostas da pesquisa de satisfação, que o resto do sistema não deixa excluir."""
    from datetime import date, timedelta
    from . import pesquisa
    de = request.args.get('de') or (date.today() - timedelta(days=365)).isoformat()
    ate = request.args.get('ate') or date.today().isoformat()
    return render_template('suporte_dados.html', respostas=pesquisa.lista_respostas(get_db(), de, ate, limite=500), de=de, ate=ate)


@bp.route('/dados/excluir', methods=['POST'])
@login_obrigatorio
def dados_excluir():
    from . import pesquisa
    ids = [int(x) for x in request.form.getlist('id') if x.isdigit()]
    n = pesquisa.excluir_respostas(get_db(), ids)
    g.sem_auditoria = True      # a exclusão não entra no registro de atividades
    flash('%d resposta(s) da pesquisa excluída(s).' % n if n else 'Nada foi excluído.', 'ok' if n else 'aviso')
    return redirect(url_for('sup.dados', de=request.form.get('de') or '', ate=request.form.get('ate') or ''))


@bp.route('/relatorio.pdf')
@login_obrigatorio
def relatorio():
    pdf = suporte_docs.relatorio_pdf(suporte.pasta(get_db())['pendentes'], config_get('clinica_nome', ''), versao(), g.usuario['usuario'])
    return send_file(io.BytesIO(pdf), mimetype='application/pdf', as_attachment=request.args.get('baixar') == '1',
                     download_name='proxima-atualizacao.pdf')
