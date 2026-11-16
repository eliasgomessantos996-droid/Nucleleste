"""Módulo NucleAI (só administração): painel de estatísticas, chamados à gerência, conteúdo da ajuda e configurações."""
import io
import json
from datetime import date

from flask import Blueprint, flash, g, redirect, render_template, request, send_file, url_for

from . import ajuda, ajuda_admin, ajuda_stats, login_obrigatorio, modulos, presenca, util
from .db import config_get, get_db

bp = Blueprint('nucleai', __name__, url_prefix='/nucleai')


def _periodo():
    hoje = date.today()
    de = util.para_data(request.args.get('de')) or hoje.replace(day=1)
    ate = util.para_data(request.args.get('ate')) or hoje
    if ate < de:
        de, ate = ate, de
    return de.isoformat(), ate.isoformat()


@bp.route('')
@login_obrigatorio
def painel():
    de, ate = _periodo()
    return render_template('nucleai_painel.html', aba='painel', p=ajuda_stats.painel(get_db(), de, ate), de=de, ate=ate,
                           resultados=ajuda_stats.RESULTADOS)


@bp.route('/chamados')
@login_obrigatorio
def chamados():
    de, ate = _periodo()
    status = request.args.get('status', '')
    return render_template('nucleai_chamados.html', aba='chamados', de=de, ate=ate, status=status,
                           rows=ajuda_stats.chamados(get_db(), de, ate, status or None), status_rotulos=ajuda_stats.STATUS_CHAMADO,
                           resumo=ajuda_stats.painel(get_db(), de, ate))


@bp.route('/chamados/<int:cid>/resolver', methods=['POST'])
@login_obrigatorio
def resolver(cid):
    try:
        ajuda.resolver_chamado(get_db(), cid, g.usuario['id'])
        get_db().commit()
        flash('Pedido de ajuda marcado como resolvido.', 'ok')
    except ValueError as e:
        flash(str(e), 'erro')
    return redirect(request.form.get('voltar') or url_for('nucleai.chamados'))


# ------------------------------------------------------------------ conteúdo
@bp.route('/conteudo')
@login_obrigatorio
def conteudo():
    db = get_db()
    arvore = ajuda_admin.arvore_para_tela(db)
    editadas = sum(1 for t in arvore for m in t['modulos'] for a in m['areas'] if a['estado'] == 'EDITADA')
    novas = sum(1 for t in arvore for m in t['modulos'] for a in m['areas'] if a['estado'] == 'NOVA')
    return render_template('nucleai_conteudo.html', aba='conteudo', arvore=arvore, editadas=editadas, novas=novas,
                           chaves=[(c[0], c[1]) for c in modulos.MODULOS], max_texto=ajuda_admin.MAX_TEXTO)


def _voltar(ancora=''):
    return redirect(url_for('nucleai.conteudo') + (('#' + ancora) if ancora else ''))


@bp.route('/conteudo/editar', methods=['POST'])
@login_obrigatorio
def editar():
    f = request.form
    try:
        ajuda_admin.editar(get_db(), g.usuario['usuario'], f.get('tema', ''), f.get('modulo', ''), f.get('area', ''), f.get('texto', ''))
        flash('Texto da ajuda atualizado. Já vale para todos.', 'ok')
    except ajuda_admin.ErroConteudo as e:
        flash(str(e), 'erro')
    return _voltar(f.get('ancora', ''))


@bp.route('/conteudo/restaurar', methods=['POST'])
@login_obrigatorio
def restaurar():
    f = request.form
    ajuda_admin.restaurar(get_db(), f.get('tema', ''), f.get('modulo', ''), f.get('area', ''))
    flash('Texto original restaurado.', 'ok')
    return _voltar(f.get('ancora', ''))


@bp.route('/conteudo/nova', methods=['POST'])
@login_obrigatorio
def nova():
    f = request.form
    tema = f.get('tema_novo', '').strip() or f.get('tema', '')
    modulo = f.get('modulo_novo', '').strip() or f.get('modulo', '')
    try:
        ajuda_admin.criar(get_db(), g.usuario['usuario'], tema, modulo, f.get('area', ''), f.get('texto', ''), f.get('chave_acesso', ''))
        flash('Área criada. Ela já aparece na NucleAI.', 'ok')
    except ajuda_admin.ErroConteudo as e:
        flash(str(e), 'erro')
    return _voltar()


@bp.route('/conteudo/excluir', methods=['POST'])
@login_obrigatorio
def excluir():
    try:
        ajuda_admin.excluir(get_db(), request.form.get('id', type=int))
        flash('Área excluída.', 'ok')
    except ajuda_admin.ErroConteudo as e:
        flash(str(e), 'erro')
    return _voltar()


# ------------------------------------------------------------------ configurações
def _candidatos(db):
    """Pessoas que podem receber os pedidos de ajuda (usuários ativos, com a marca de quem já é gerência)."""
    saida = []
    estado = presenca.situacao(db)
    for u in db.execute("SELECT id, usuario, admin, modulos FROM usuarios WHERE ativo=1 AND COALESCE(sistema,0)=0 ORDER BY usuario").fetchall():
        saida.append({'id': u['id'], 'usuario': u['usuario'], 'gerencia': 'gerencia' in modulos.modulos_do_usuario(u),
                      'admin': bool(u['admin']), 'online': estado.get(u['id'], {}).get('online', False)})
    return saida


@bp.route('/config', methods=['GET', 'POST'])
@login_obrigatorio
def config():
    db = get_db()
    if request.method == 'POST':
        f = request.form
        try:
            abandono = int(f.get('abandono_h', ''))
            despedida = int(f.get('despedida_s', ''))
        except ValueError:
            flash('Informe os tempos em números.', 'erro')
            return redirect(url_for('nucleai.config'))
        if not 1 <= abandono <= 72:
            flash('O tempo para apagar conversas abandonadas deve ficar entre 1 e 72 horas.', 'erro')
            return redirect(url_for('nucleai.config'))
        if not 10 <= despedida <= 600:
            flash('O tempo da despedida deve ficar entre 10 e 600 segundos.', 'erro')
            return redirect(url_for('nucleai.config'))
        validos = {c['id'] for c in _candidatos(db)}
        escolhidos = sorted({int(x) for x in f.getlist('destinatarios') if x.isdigit() and int(x) in validos})
        ajuda.definir(db, 'nucleai_ativa', '1' if f.get('ativa') else '0')
        ajuda.definir(db, 'nucleai_abandono_h', abandono)
        ajuda.definir(db, 'nucleai_despedida_s', despedida)
        ajuda.definir(db, 'nucleai_destinatarios', json.dumps(escolhidos))
        db.commit()
        flash('Configurações da NucleAI salvas.', 'ok')
        return redirect(url_for('nucleai.config'))
    return render_template('nucleai_config.html', aba='config', ativa=ajuda.ativa(db), abandono_h=ajuda.abandono_h(db),
                           despedida_s=ajuda.despedida_s(db), escolhidos=set(ajuda.destinatarios_escolhidos(db)),
                           candidatos=_candidatos(db), gerencia_padrao=ajuda.gerencia_do_sistema(db))


# ------------------------------------------------------------------ relatório
@bp.route('/relatorio.pdf')
@login_obrigatorio
def pdf():
    from .ajuda_docs import relatorio_pdf
    de, ate = _periodo()
    db = get_db()
    dados = relatorio_pdf(ajuda_stats.painel(db, de, ate), ajuda_stats.consultas(db, de, ate), ajuda_stats.chamados(db, de, ate),
                          config_get('clinica_nome', ''))
    return send_file(io.BytesIO(dados), mimetype='application/pdf', as_attachment=True, download_name='relatorio-nucleai.pdf')


@bp.route('/relatorio.xlsx')
@login_obrigatorio
def xlsx():
    from .ajuda_docs import relatorio_xlsx
    de, ate = _periodo()
    db = get_db()
    dados = relatorio_xlsx(ajuda_stats.painel(db, de, ate), ajuda_stats.consultas(db, de, ate), ajuda_stats.chamados(db, de, ate),
                           config_get('clinica_nome', ''))
    return send_file(io.BytesIO(dados), as_attachment=True, download_name='relatorio-nucleai.xlsx',
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
