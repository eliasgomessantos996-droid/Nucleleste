"""Agenda de exames: calendário, grade do dia, status, lista de espera, impressão e relatórios."""
import calendar
import io
import re
from datetime import date

from flask import Blueprint, abort, flash, g, jsonify, redirect, render_template, request, send_file, url_for

from . import agenda as ag
from . import agenda_docs as docs
from . import agenda_rel_docs as rdocs
from . import agenda_fin_docs as fdocs
from . import agenda_reservas as reservas
from . import login_obrigatorio, mensagens_whats as mw, util
from .db import config_get, get_db

bp = Blueprint('agenda', __name__, url_prefix='/agenda')


def _usuario():
    return g.usuario['usuario']


def _data(txt):
    d = util.para_data(txt)
    if not d:
        abort(404)
    return d.isoformat()


def _id(nome):
    bruto = (request.form.get(nome) or '').strip()
    return int(bruto) if bruto.isdigit() else 0


def _primeiro_nome_usuario():
    """Primeiro nome de quem está logado (o segundo nome e os seguintes não entram na mensagem do WhatsApp)."""
    partes = (g.usuario['usuario'] or '').split()
    return partes[0].lower().capitalize() if partes else ''


def _payload(db, data_iso):
    return {'data': data_iso, 'bloqueado': ag.bloqueio(db, data_iso), 'agendas': ag.listar_dia(db, data_iso),
            'espera': ag.espera_listar(db), 'modelos': ag.modelos(db), 'convenios': ag.convenios_ativos(db)}


def _resposta(acao):
    """Executa a ação e responde em JSON; erros de validação viram mensagens para a tela."""
    db = get_db()
    try:
        dados = acao()
    except ag.ErroConflito as e:
        db.rollback()
        return jsonify(conflito=True, atual=e.atual, por=e.por, erro=str(e)), 409
    except ag.ErroConfirmacao as e:
        db.rollback()
        return jsonify(erro=str(e), confirmar=True), 409
    except ag.ErroAgenda as e:
        db.rollback()
        return jsonify(erro=str(e)), 400
    return jsonify(ok=True, **(dados or {}))


# ------------------------------------------------------------------ tela e leitura
@bp.route('')
@login_obrigatorio
def pagina():
    db = get_db()
    data = (util.para_data(request.args.get('data')) or date.today()).isoformat()
    exames = [r['nome'] for r in db.execute('SELECT nome FROM exames WHERE ativo=1 ORDER BY ordem, nome')]
    exames_cad = [dict(r) for r in db.execute('SELECT id, nome FROM exames WHERE ativo=1 ORDER BY ordem, nome')]
    destacar = [int(x) for x in (request.args.get('destacar') or '').split(',') if x.strip().isdigit()][:20]
    return render_template('agenda.html', inicial=_payload(db, data), destacar=destacar, exames=exames, exames_cad=exames_cad, hoje=date.today().isoformat(),
                           pode_excluir=pode_excluir_agenda(), mensagens=mw.atuais(), usuario_envio=_primeiro_nome_usuario(),
                           somente_leitura=not (g.usuario['admin'] or 'agenda' in (g.get('modulos') or ())))


@bp.route('/dia/<data>')
@login_obrigatorio
def dia(data):
    return jsonify(_payload(get_db(), _data(data)))


@bp.route('/mes')
@login_obrigatorio
def mes():
    bruto = (request.args.get('mes') or '')[:7]
    d = util.para_data(bruto + '-01') if len(bruto) == 7 else None
    if not d:
        abort(404)
    return jsonify(ag.marcas_do_mes(get_db(), d.year, d.month))


@bp.route('/livres/<data>')
@login_obrigatorio
def livres(data):
    return jsonify(livres=ag.horarios_livres(get_db(), _data(data), convenio=request.args.get('convenio') or ''))


# ------------------------------------------------------------------ agendas
@bp.route('/criar', methods=['POST'])
@login_obrigatorio
def criar():
    def acao():
        db = get_db()
        dados = ag.validar_nova(request.form, db)
        r = ag.criar(db, dados, _usuario())
        return {'data': r['data'], 'criadas': len(r['ids']), 'pulados': r['pulados']}
    return _resposta(acao)


@bp.route('/<int:aid>/nome', methods=['POST'])
@login_obrigatorio
def renomear_agenda(aid):
    return _resposta(lambda: ag.renomear_agenda(get_db(), aid, request.form.get('nome')))


@bp.route('/<int:aid>/excluir', methods=['POST'])
@login_obrigatorio
def excluir_agenda(aid):
    if not pode_excluir_agenda():
        return jsonify(erro='Somente o administrador e a gerência podem excluir uma agenda.'), 403
    return _resposta(lambda: ag.excluir_agenda(get_db(), aid, request.form.get('confirmar') == '1'))


def pode_excluir_agenda():
    return bool(g.usuario['admin']) or 'gerencia' in (g.get('modulos') or ())


@bp.route('/<int:aid>/reservar', methods=['POST'])
@login_obrigatorio
def reservar(aid):
    """Reserva (ou libera) para o UNACON os horários sem paciente entre dois horários da agenda."""
    return _resposta(lambda: ag.reservar_faixa(get_db(), aid, request.form.get('de'), request.form.get('ate'),
                                               request.form.get('valor') == '1'))


@bp.route('/horario/<int:hid>/reserva', methods=['POST'])
@login_obrigatorio
def reserva(hid):
    return _resposta(lambda: ag.reservar_linha(get_db(), hid, request.form.get('valor') == '1'))


@bp.route('/<int:aid>/horario', methods=['POST'])
@login_obrigatorio
def horario_adicionar(aid):
    return _resposta(lambda: ag.adicionar_horario(get_db(), aid, _usuario(), _id('depois') or None, _id('qtd') or 1))


@bp.route('/copiar', methods=['POST'])
@login_obrigatorio
def copiar():
    def acao():
        origem, destino = util.para_data(request.form.get('origem')), util.para_data(request.form.get('destino'))
        if not origem or not destino:
            raise ag.ErroAgenda('Escolha o dia de destino.')
        return ag.copiar(get_db(), origem.isoformat(), destino.isoformat(), request.form.get('com_pacientes') == '1',
                         _id('agenda_id') or None, _usuario(), apagar_origem=request.form.get('apagar_origem') == '1')
    return _resposta(acao)


@bp.route('/bloquear', methods=['POST'])
@login_obrigatorio
def bloquear():
    def acao():
        d = util.para_data(request.form.get('data'))
        if not d:
            raise ag.ErroAgenda('Data inválida.')
        ag.bloquear(get_db(), d.isoformat(), request.form.get('motivo'), _usuario())
        return {'data': d.isoformat()}
    return _resposta(acao)


@bp.route('/desbloquear', methods=['POST'])
@login_obrigatorio
def desbloquear():
    def acao():
        d = util.para_data(request.form.get('data'))
        if not d:
            raise ag.ErroAgenda('Data inválida.')
        ag.desbloquear(get_db(), d.isoformat())
        return {'data': d.isoformat()}
    return _resposta(acao)


# ------------------------------------------------------------------ linhas da grade
@bp.route('/horario/<int:hid>/campo', methods=['POST'])
@login_obrigatorio
def campo(hid):
    def acao():
        db = get_db()
        r = ag.salvar_campo(db, hid, request.form.get('campo'), request.form.get('valor'), request.form.get('antes'), _usuario())
        if request.form.get('campo') in ('paciente', 'contato'):
            try:   # o aviso de duplicidade nunca atrapalha o salvamento
                dia = db.execute('SELECT a.data FROM agenda_horarios h JOIN agenda_exames a ON a.id=h.agenda_id WHERE h.id=?', (hid,)).fetchone()
                if dia:
                    ag.avisar_duplicados(db, dia['data'])
            except Exception:
                db.rollback()
        return r
    return _resposta(acao)


@bp.route('/horario/<int:hid>/status', methods=['POST'])
@login_obrigatorio
def status(hid):
    def acao():
        db = get_db()
        # administrador e gerência podem alterar o status de linha já remarcada (pode_excluir_agenda)
        r = ag.definir_status(db, hid, request.form.get('status'), _usuario(), liberar_remarcado=pode_excluir_agenda())
        nome = ' '.join((db.execute('SELECT paciente FROM agenda_horarios WHERE id=?', (hid,)).fetchone()['paciente'] or '').upper().split())
        r['cadastrado'] = bool(nome and db.execute('SELECT 1 FROM clientes WHERE UPPER(TRIM(nome))=? LIMIT 1', (nome,)).fetchone())
        return r
    return _resposta(acao)


@bp.route('/horario/<int:hid>/chegou', methods=['POST'])
@login_obrigatorio
def chegou(hid):
    return _resposta(lambda: ag.definir_chegou(get_db(), hid, request.form.get('valor') == '1', _usuario()))


@bp.route('/horario/<int:hid>/historico')
@login_obrigatorio
def historico(hid):
    return jsonify(itens=ag.historico(get_db(), hid))


@bp.route('/exame/mover', methods=['POST'])
@login_obrigatorio
def mover_exame():
    """Sobe ou desce um exame na lista de agendas (a ordem vale para todos os dias)."""
    return _resposta(lambda: ag.mover_exame(get_db(), (request.form.get('exame') or '').strip(), request.form.get('direcao')))


@bp.route('/horario/<int:hid>/excluir', methods=['POST'])
@login_obrigatorio
def horario_excluir(hid):
    return _resposta(lambda: ag.excluir_horario(get_db(), hid, request.form.get('confirmar') == '1'))


@bp.route('/horario/<int:hid>/remarcar', methods=['POST'])
@login_obrigatorio
def remarcar(hid):
    return _resposta(lambda: ag.remarcar(get_db(), hid, _id('destino'), _usuario()))


@bp.route('/horario/<int:hid>/reagendar', methods=['POST'])
@login_obrigatorio
def reagendar(hid):
    """Falta resgatada como reagendado: copia o paciente, com todas as informações, para outro dia e horário."""
    return _resposta(lambda: ag.remarcar(get_db(), hid, _id('destino'), _usuario(), status_origem='RESGATADO'))


@bp.route('/horario/<int:hid>/copiar_linha', methods=['POST'])
@login_obrigatorio
def copiar_linha(hid):
    return _resposta(lambda: ag.copiar_linha(get_db(), hid, _id('destino'), _usuario()))


@bp.route('/horario/<int:hid>/recortar', methods=['POST'])
@login_obrigatorio
def recortar_linha(hid):
    return _resposta(lambda: ag.recortar_linha(get_db(), hid, _id('destino'), _usuario()))


# ------------------------------------------------------------------ lista de espera
@bp.route('/espera', methods=['POST'])
@login_obrigatorio
def espera_adicionar():
    def acao():
        ag.espera_adicionar(get_db(), request.form, _usuario())
        return {}
    return _resposta(acao)


@bp.route('/espera/<int:eid>/excluir', methods=['POST'])
@login_obrigatorio
def espera_excluir(eid):
    def acao():
        ag.espera_excluir(get_db(), eid)
        return {}
    return _resposta(acao)


@bp.route('/espera/<int:eid>/encaixar', methods=['POST'])
@login_obrigatorio
def espera_encaixar(eid):
    return _resposta(lambda: ag.espera_encaixar(get_db(), eid, _id('destino'), _usuario()))


# ------------------------------------------------------------------ impressão
@bp.route('/imprimir/<data>.pdf')
@login_obrigatorio
def imprimir(data):
    """Agenda do dia em PDF (aberta no navegador para imprimir). `agenda=<id>` imprime só um exame."""
    data_iso = _data(data)
    agendas = ag.listar_dia(get_db(), data_iso)
    alvo = request.args.get('agenda', 'todos')
    if alvo.isdigit():
        agendas = [a for a in agendas if a['id'] == int(alvo)]
    pdf = docs.dia_pdf(data_iso, agendas, config_get('clinica_nome', ''))
    return send_file(io.BytesIO(pdf), mimetype='application/pdf', as_attachment=request.args.get('baixar') == '1',
                     download_name='agenda-%s.pdf' % data_iso)


# ------------------------------------------------------------------ relatórios
def _periodo():
    hoje = date.today()
    de = util.para_data(request.args.get('de')) or hoje.replace(day=1)
    ate = util.para_data(request.args.get('ate')) or hoje.replace(day=calendar.monthrange(hoje.year, hoje.month)[1])
    if ate < de:
        de, ate = ate, de
    return de, ate, (request.args.get('exame') or '').strip()


@bp.route('/relatorio')
@login_obrigatorio
def relatorio():
    db = get_db()
    de, ate, exame = _periodo()
    nomes = ag.exames_do_cadastro(db)
    return render_template('agenda_relatorio.html', rel=ag.relatorio(db, de, ate, exame), de=de.isoformat(), ate=ate.isoformat(),
                           exame=exame, exames=nomes)


@bp.route('/resgates')
@login_obrigatorio
def resgates():
    """Relatório de resgate (financeiro): quantos pacientes cada usuário resgatou no período."""
    de, ate, _ = _periodo()
    return render_template('agenda_resgates.html', rel=ag.resgates(get_db(), de, ate), de=de.isoformat(), ate=ate.isoformat())


@bp.route('/resgates.pdf')
@login_obrigatorio
def resgates_pdf():
    de, ate, _ = _periodo()
    pdf = rdocs.resgate_pdf(ag.resgates(get_db(), de, ate), config_get('clinica_nome', ''))
    return send_file(io.BytesIO(pdf), mimetype='application/pdf', as_attachment=True, download_name='relatorio-resgate.pdf')


@bp.route('/resgates.xlsx')
@login_obrigatorio
def resgates_xlsx():
    de, ate, _ = _periodo()
    dados = rdocs.resgate_xlsx(ag.resgates(get_db(), de, ate), config_get('clinica_nome', ''))
    return send_file(io.BytesIO(dados), as_attachment=True, download_name='relatorio-resgate.xlsx',
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@bp.route('/faltas')
@login_obrigatorio
def faltas():
    """Quem faltou no período, por exame, com contato direto (WhatsApp) para convidar a reagendar."""
    db = get_db()
    de, ate, exame = _periodo()
    nomes = [r['exame'] for r in db.execute('SELECT DISTINCT exame FROM agenda_exames ORDER BY exame COLLATE NOCASE')]
    return render_template('agenda_faltas.html', rel=ag.faltas(db, de, ate, exame), de=de.isoformat(), ate=ate.isoformat(),
                           exame=exame, exames=nomes, mensagens=mw.atuais())


@bp.route('/relatorio.pdf')
@login_obrigatorio
def relatorio_pdf():
    de, ate, exame = _periodo()
    pdf = rdocs.relatorio_pdf(ag.relatorio(get_db(), de, ate, exame), config_get('clinica_nome', ''))
    return send_file(io.BytesIO(pdf), mimetype='application/pdf', as_attachment=True, download_name='relatorio-agenda.pdf')


@bp.route('/relatorio.xlsx')
@login_obrigatorio
def relatorio_xlsx():
    de, ate, exame = _periodo()
    dados = rdocs.relatorio_xlsx(ag.relatorio(get_db(), de, ate, exame), config_get('clinica_nome', ''))
    return send_file(io.BytesIO(dados), as_attachment=True, download_name='relatorio-agenda.xlsx',
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


# ------------------------------------------------------------------ financeiro da agenda (repasse médico)
def _tipos():
    return request.args.getlist('tipo')


def _dias():
    """Dias da semana marcados (0=segunda ... 6=domingo); valores inválidos são ignorados."""
    return sorted({int(d) for d in request.args.getlist('dias') if d.strip().isdigit() and 0 <= int(d) <= 6})


def _financeiro_args():
    """Período e porcentagem de repasse. Sem porcentagem válida, não há relatório a gerar."""
    de, ate, exame = _periodo()
    pct = util.para_valor(request.args.get('pct'))
    if pct is not None and not 0 <= pct <= 100:
        pct = None
    return de, ate, pct, exame


@bp.route('/financeiro')
@login_obrigatorio
def financeiro():
    db = get_db()
    de, ate, pct, exame = _financeiro_args()
    rel = ag.financeiro(db, de, ate, pct, exame, _tipos(), _dias()) if pct is not None else None
    nomes = ag.exames_do_cadastro(db)
    return render_template('agenda_financeiro.html', rel=rel, tipos=_tipos(), dias=_dias(), dias_txt=fdocs.dias_texto(_dias(), ', '), etapas=ag.ETAPAS_MIBI,
                           de=de.isoformat(), ate=ate.isoformat(), exame=exame, exames=nomes, pct=request.args.get('pct', '') if pct is None else ('%g' % pct).replace('.', ','))


@bp.route('/financeiro.pdf')
@login_obrigatorio
def financeiro_pdf():
    de, ate, pct, exame = _financeiro_args()
    if pct is None:
        abort(400)
    pdf = fdocs.financeiro_pdf(ag.financeiro(get_db(), de, ate, pct, exame, _tipos(), _dias()), config_get('clinica_nome', ''))
    # abrir=1: devolve o PDF para visualizar/imprimir no navegador (em nova aba), sem baixar
    abrir = request.args.get('abrir') == '1'
    return send_file(io.BytesIO(pdf), mimetype='application/pdf', as_attachment=not abrir, download_name='financeiro-agenda.pdf')


@bp.route('/financeiro.xlsx')
@login_obrigatorio
def financeiro_xlsx():
    de, ate, pct, exame = _financeiro_args()
    if pct is None:
        abort(400)
    dados = fdocs.financeiro_xlsx(ag.financeiro(get_db(), de, ate, pct, exame, _tipos(), _dias()), config_get('clinica_nome', ''))
    return send_file(io.BytesIO(dados), as_attachment=True, download_name='financeiro-agenda.xlsx',
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


# ------------------------------------------------------------------ planilha das vagas reservadas para um convênio
def _periodo_reservas():
    hoje = date.today()
    de = util.para_data(request.values.get('de')) or hoje
    ate = util.para_data(request.values.get('ate')) or hoje.replace(day=28)
    return (de, ate) if de <= ate else (ate, de)


@bp.route('/reservas')
@login_obrigatorio
def reservas_pagina():
    de, ate = _periodo_reservas()
    return render_template('agenda_reservas.html', convenios=reservas.convenios_com_reserva(get_db()), de=de.isoformat(),
                           ate=ate.isoformat(), convenio=request.args.get('convenio', ''), resultado=None)


@bp.route('/reservas/planilha')
@login_obrigatorio
def reservas_planilha():
    """Uma planilha por dia reservado: um dia = .xlsx; período maior = .zip com uma planilha por dia e o relatório em PDF."""
    convenio = (request.args.get('convenio') or '').strip()
    de, ate = _periodo_reservas()
    pacote = reservas.pacote(get_db(), convenio, de.isoformat(), ate.isoformat(), config_get('clinica_nome', ''))
    if pacote is None:
        flash('Não há vagas reservadas sem paciente %sno período escolhido.' % ('para este convênio ' if convenio else ''), 'aviso')
        return redirect(url_for('agenda.reservas_pagina', convenio=convenio, de=de.isoformat(), ate=ate.isoformat()))
    nome, mimetype, dados, _ = pacote
    return send_file(io.BytesIO(dados), as_attachment=True, download_name=nome, mimetype=mimetype)


@bp.route('/reservas/importar', methods=['POST'])
@login_obrigatorio
def reservas_importar():
    """Importa a planilha devolvida pelo convênio (o arquivo é lido e descartado, não fica guardado). Na tela da agenda
    (`json=1`) responde em JSON; na tela de reservas, mostra o resultado."""
    de, ate = _periodo_reservas()
    em_json = request.values.get('json') == '1'
    arq = request.files.get('planilha')
    resultado, erro = None, ''
    if not arq or not arq.filename.lower().endswith('.xlsx'):
        erro = 'Escolha o arquivo .xlsx da planilha preenchida.'
    else:
        try:
            resultado = reservas.importar(get_db(), arq.read(reservas.MAX_BYTES + 1), _usuario())
        except ag.ErroAgenda as e:
            get_db().rollback()
            erro = str(e)
    if em_json:
        return (jsonify(erro=erro), 400) if erro else jsonify(ok=True, **resultado)
    if erro:
        flash(erro, 'erro')
    return render_template('agenda_reservas.html', convenios=reservas.convenios_com_reserva(get_db()), de=de.isoformat(),
                           ate=ate.isoformat(), convenio='', resultado=resultado)
