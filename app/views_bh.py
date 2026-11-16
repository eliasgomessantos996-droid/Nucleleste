"""Banco de Horas: ponto, saldos, jornadas, escala, Departamento Pessoal, mensagens e "Minha área" do funcionário.

Porte do programa autônomo Banco de Horas para dentro da Nucleleste. As regras de cálculo vivem em app/bh/core.py;
aqui ficam as telas. Tudo usa o banco da Nucleleste (tabelas bh_*) e os usuários/permissões da Nucleleste.
"""
import hashlib
import io
import json
import re
from datetime import date, datetime

from flask import (Blueprint, abort, flash, g, jsonify, redirect, render_template, request, send_file, session, url_for)

from . import login_obrigatorio
from .bh import core, documents, messages, ocorrencias, planning, portal, search
from .bh.pdf import date_br, format_minutes, render_report
from .db import config_get, get_db

bp = Blueprint('bh', __name__, url_prefix='/banco-horas')

DIAS_SEMANA = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo']


# ------------------------------------------------------------------ utilidades
def hoje():
    return date.today()


def ator():
    return g.usuario['usuario']


def datetime_br(value):
    if not value:
        return '—'
    try:
        instante = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if instante.tzinfo:
            instante = instante.astimezone()
        return instante.strftime('%d/%m/%Y %H:%M')
    except ValueError:
        return str(value)


def duration(value, signed=False):
    padrao = r'([+\-−]?)(\d{1,5}):([0-5]\d)' if signed else r'()(\d{1,2}):([0-5]\d)'
    m = re.fullmatch(padrao, str(value).strip())
    if not m:
        raise ValueError('Informe as horas no formato HH:MM' + (', com + ou - quando necessário.' if signed else '.'))
    sinal, horas, minutos = m.groups()
    total = int(horas) * 60 + int(minutos)
    if not signed and total > 24 * 60:
        raise ValueError('A duração diária deve ser de até 24 horas.')
    return -total if sinal in ('-', '−') else total


def month_value():
    mes = request.values.get('month', hoje().strftime('%Y-%m'))
    if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', mes):
        raise ValueError('Selecione um mês válido.')
    return mes


def funcionario_ou_404(employee_id):
    try:
        return core.get_employee(get_db(), employee_id)
    except ValueError:
        abort(404)


def empresa():
    return config_get('clinica_nome', 'Clínica')


def equipe_mensagens():
    return 'bh_mensagens' in g.modulos


def _visao_funcionario():
    return messages.eh_funcionario(g.usuario) and 'bh_gestao' not in g.modulos


def _relatorio_visivel(employee_id, mes):
    if _visao_funcionario():
        if employee_id != g.usuario['bh_funcionario_id']:
            abort(403)
        return portal.relatorio_funcionario(get_db(), employee_id, mes)
    return core.monthly_report(get_db(), employee_id, mes)


@bp.app_template_filter('bh_min')
def f_min(n):
    return format_minutes(n)


@bp.app_template_filter('bh_smin')
def f_smin(n):
    return format_minutes(n, signed=True)


@bp.app_template_filter('bh_data')
def f_data(v):
    return date_br(v)


@bp.app_template_filter('bh_datahora')
def f_datahora(v):
    return datetime_br(v)


@bp.before_request
def _antes():
    # dados do formulário que falhou na validação voltam preenchidos
    g.bh_form = session.pop('bh_form', None) or {}


@bp.app_context_processor
def _contexto():
    return {'bh_form': getattr(g, 'bh_form', {}) if g else {}}


@bp.errorhandler(ValueError)
def _valor_invalido(erro):
    flash(str(erro), 'erro')
    if request.method == 'POST':
        session['bh_form'] = {k: v for k, v in request.form.items()
                              if k != '_csrf' and 'senha' not in k and 'password' not in k}
    destino = request.referrer or url_for('bh.painel')
    if request.endpoint == 'bh.portal_ocorrencia':
        destino = url_for('bh.portal_home')
    if request.endpoint == 'bh.painel' or destino == request.url:
        destino = url_for('bh.painel')
        if request.endpoint == 'bh.painel':
            abort(400, str(erro))
    if request.accept_mimetypes.best == 'application/json':
        return jsonify(error=str(erro)), 400
    return redirect(destino)


# ------------------------------------------------------------------ painel
@bp.route('')
@login_obrigatorio
def painel():
    mes = month_value()
    relatorios = core.summary(get_db(), mes)
    totais = dict(employee_count=len(relatorios),
                  positive_minutes=sum(max(r['final_balance'], 0) for r in relatorios),
                  negative_minutes=sum(min(r['final_balance'], 0) for r in relatorios),
                  pending_count=sum(r['pending_count'] for r in relatorios))
    return render_template('bh/painel.html', reports=relatorios, summary=totais, month=mes,
                           ocorrencias_pendentes=ocorrencias.listar(get_db(), pendentes=True) if 'bh_gestao' in g.modulos else [])


@bp.route('/pesquisar')
@login_obrigatorio
def pesquisa():
    consulta = request.args.get('q', '').strip()[:100]
    grupos = search.search(get_db(), consulta, g.modulos)
    return render_template('bh/pesquisa.html', query=consulta, groups=grupos)


# ------------------------------------------------------------------ funcionários
@bp.route('/funcionarios')
@login_obrigatorio
def funcionarios():
    arquivados = bool(request.args.get('arquivados'))
    todos = core.list_employees(get_db())
    lista = [e for e in todos if bool(e.get('archived_at')) == arquivados]   # desligados e arquivados saem da lista principal
    return render_template('bh/funcionarios.html', employees=lista, pending_ids=core.pending_ids(get_db()), arquivados=arquivados,
                           n_arquivados=sum(1 for e in todos if e.get('archived_at')))


def _dados_funcionario():
    dados = dict(request.form)
    dados['active'] = bool(request.form.get('active'))
    dados['is_intern'] = bool(request.form.get('is_intern'))
    return dados


@bp.route('/funcionarios/novo', methods=['GET', 'POST'])
@login_obrigatorio
def funcionario_novo():
    if request.method == 'POST':
        dados = _dados_funcionario()
        dados['opening_balance_minutes'] = duration(request.form.get('opening_balance', '00:00'), signed=True)
        funcionario = core.save_employee(get_db(), dados, ator())
        flash('Funcionário cadastrado. Configure a jornada abaixo para calcular as horas.', 'ok')
        login = portal.create_default_account(get_db(), funcionario['id'], ator())
        if login:
            flash('Acesso criado automaticamente: usuário %s e senha padrão %s. No primeiro login o sistema fica travado até ele trocar a senha.' % (login, portal.SENHA_PADRAO), 'ok')
        return redirect(url_for('bh.funcionario_editar', employee_id=funcionario['id']))
    inicio = request.args.get('start_date', hoje().replace(day=1).isoformat())
    funcionario = {'clock_id': request.args.get('clock_id', ''), 'name': request.args.get('name', ''), 'active': True,
                   'start_date': inicio, 'opening_balance_date': inicio}
    return render_template('bh/funcionario_form.html', employee=funcionario, schedules=[], is_new=True, portal_account=None)


@bp.route('/funcionarios/<int:employee_id>', methods=['GET', 'POST'])
@login_obrigatorio
def funcionario_editar(employee_id):
    funcionario = funcionario_ou_404(employee_id)
    if request.method == 'POST':
        dados = _dados_funcionario()
        dados['clock_id'] = funcionario['clock_id']
        dados['opening_balance_minutes'] = funcionario['opening_balance_minutes']
        dados['opening_balance_date'] = funcionario['opening_balance_date']
        if not dados.get('reason', '').strip():
            raise ValueError('Informe o motivo da alteração no cadastro.')
        core.save_employee(get_db(), dados, ator(), employee_id=employee_id)
        flash('Cadastro atualizado e alteração registrada no histórico.', 'ok')
        return redirect(url_for('bh.funcionario_editar', employee_id=employee_id))
    return render_template('bh/funcionario_form.html', employee=funcionario, schedules=funcionario.get('schedules', []),
                           is_new=False, portal_account=portal.get_account(get_db(), employee_id))


@bp.route('/funcionarios/<int:employee_id>/jornada', methods=['POST'])
@login_obrigatorio
def funcionario_jornada(employee_id):
    funcionario_ou_404(employee_id)
    dados = dict(effective_date=request.form.get('effective_date'),
                 weekdays={str(i): duration(request.form.get(f'weekday_{i}', '00:00')) for i in range(7)},
                 two_punch_policy=request.form.get('two_punch_policy', 'review'),
                 required_break_minutes=duration(request.form.get('break_minutes', '00:00')),
                 deduct_break_minutes=duration(request.form.get('break_minutes', '00:00')),
                 reason=request.form.get('reason', ''))
    if not dados['reason'].strip():
        raise ValueError('Informe o motivo e a data inicial da jornada.')
    core.save_schedule(get_db(), employee_id, dados, ator())
    flash('Jornada registrada a partir da data informada.', 'ok')
    return redirect(url_for('bh.funcionario_editar', employee_id=employee_id))


@bp.route('/funcionarios/<int:employee_id>/acesso', methods=['POST'])
@login_obrigatorio
def portal_acesso_criar(employee_id):
    portal.create_account(get_db(), employee_id, request.form.get('username'), request.form.get('password', ''),
                          request.form.get('password_confirm', ''), ator())
    flash('Acesso criado. O funcionário será obrigado a trocar a senha no primeiro login.', 'ok')
    return redirect(url_for('bh.funcionario_editar', employee_id=employee_id))


@bp.route('/funcionarios/<int:employee_id>/acesso/atualizar', methods=['POST'])
@login_obrigatorio
def portal_acesso_atualizar(employee_id):
    portal.update_account(get_db(), employee_id, bool(request.form.get('active')), request.form.get('password') or None,
                          request.form.get('password_confirm', ''), request.form.get('reason'), ator())
    flash('Acesso atualizado.', 'ok')
    return redirect(url_for('bh.funcionario_editar', employee_id=employee_id))


# ------------------------------------------------------------------ importações
@bp.route('/importacoes')
@login_obrigatorio
def importacoes():
    return render_template('bh/importacoes.html', imports=core.list_imports(get_db()), pending_ids=core.pending_ids(get_db()))


@bp.route('/importacoes/enviar', methods=['POST'])
@login_obrigatorio
def importacao_enviar():
    arquivo = request.files.get('file')
    if not arquivo or not arquivo.filename:
        raise ValueError('Selecione a planilha .XLS exportada pelo relógio de ponto.')
    if not arquivo.filename.lower().endswith('.xls'):
        raise ValueError('Esta versão importa o formato .XLS do relógio de ponto.')
    conteudo = arquivo.read()
    if len(conteudo) > 20 * 1024 * 1024:
        raise ValueError('A planilha deve ter no máximo 20 MB.')
    resultado = core.import_xls(get_db(), conteudo, arquivo.filename, ator())
    if resultado.get('duplicate'):
        flash('Esse arquivo já foi importado. Nenhum lançamento foi duplicado.', 'ok')
    else:
        flash('Importação concluída. Confira os funcionários e as pendências do arquivo.', 'ok')
    return redirect(url_for('bh.importacao', batch_id=resultado['id']))


@bp.route('/importacoes/<int:batch_id>')
@login_obrigatorio
def importacao(batch_id):
    try:
        lote = core.get_import(get_db(), batch_id)
    except ValueError:
        abort(404)
    return render_template('bh/importacao.html', batch=lote)


@bp.route('/importacoes/<int:batch_id>/original')
@login_obrigatorio
def importacao_original(batch_id):
    lote = get_db().execute('SELECT filename,file_bytes FROM bh_imports WHERE id=?', (batch_id,)).fetchone()
    if not lote:
        abort(404)
    return send_file(io.BytesIO(lote['file_bytes']), mimetype='application/vnd.ms-excel', as_attachment=True,
                     download_name=lote['filename'])


# ------------------------------------------------------------------ extrato, correções, ajustes, relatório
@bp.route('/funcionarios/<int:employee_id>/extrato')
@login_obrigatorio
def extrato(employee_id):
    funcionario_ou_404(employee_id)
    relatorio = _relatorio_visivel(employee_id, month_value())
    emitidos = [dict(r) for r in get_db().execute(
        'SELECT id,version,issued_at FROM bh_report_snapshots WHERE employee_id=? AND month=? ORDER BY version DESC',
        (employee_id, relatorio['month']))]
    return render_template('bh/extrato.html', report=relatorio, issued_reports=emitidos, month=relatorio['month'],
                           ocorrencias_pendentes=ocorrencias.listar(get_db(), employee_id, True) if 'bh_gestao' in g.modulos else [])


@bp.route('/funcionarios/<int:employee_id>/dia/<data>', methods=['GET', 'POST'])
@login_obrigatorio
def correcao(employee_id, data):
    funcionario = funcionario_ou_404(employee_id)
    try:
        dia = datetime.strptime(data, '%Y-%m-%d').date()
    except ValueError:
        raise ValueError('Data inválida.') from None
    if request.method == 'POST':
        batidas = [p for p in re.split(r'[,;\s]+', request.form.get('punches', '').strip()) if p]
        core.correct_day(get_db(), employee_id, data, batidas, request.form.get('kind', 'normal'),
                         request.form.get('reason', ''), ator())
        flash('Correção salva. Os saldos foram recalculados, e o original permanece no histórico.', 'ok')
        return redirect(url_for('bh.extrato', employee_id=employee_id, month=data[:7]))
    relatorio = core.monthly_report(get_db(), employee_id, dia.strftime('%Y-%m'))
    linha = next((r for r in relatorio['rows'] if r['date'] == data), None)
    if linha is None:
        raise ValueError('A data está fora do vínculo do funcionário.')
    return render_template('bh/correcao.html', employee=funcionario, row=linha)


@bp.route('/funcionarios/<int:employee_id>/ajuste', methods=['POST'])
@login_obrigatorio
def ajuste(employee_id):
    funcionario_ou_404(employee_id)
    data = request.form.get('date', '')
    core.add_adjustment(get_db(), employee_id, data, duration(request.form.get('minutes', ''), signed=True),
                        request.form.get('reason', ''), ator())
    flash('Ajuste registrado no saldo e no histórico.', 'ok')
    return redirect(url_for('bh.extrato', employee_id=employee_id, month=data[:7]))


@bp.route('/funcionarios/<int:employee_id>/relatorio')
@login_obrigatorio
def relatorio(employee_id):
    funcionario_ou_404(employee_id)
    return render_template('bh/relatorio.html', report=_relatorio_visivel(employee_id, month_value()),
                           company_name=empresa())


@bp.route('/funcionarios/<int:employee_id>/relatorio/pdf', methods=['POST'])
@login_obrigatorio
def relatorio_pdf(employee_id):
    funcionario_ou_404(employee_id)
    db = get_db()
    rel = core.monthly_report(db, employee_id, month_value())
    if not rel['complete']:
        raise ValueError('Resolva as pendências deste mês e dos meses anteriores antes de emitir o relatório para assinatura.')
    empresa_nome = empresa()
    foto = json.dumps({'report': rel, 'company_name': empresa_nome}, ensure_ascii=False, sort_keys=True)
    resumo = hashlib.sha256(foto.encode()).hexdigest()
    anterior = db.execute('SELECT * FROM bh_report_snapshots WHERE employee_id=? AND month=? ORDER BY version DESC LIMIT 1',
                          (employee_id, rel['month'])).fetchone()
    if anterior and anterior['content_hash'] == resumo:
        pdf, versao = anterior['pdf_bytes'], anterior['version']
    else:
        versao = anterior['version'] + 1 if anterior else 1
        emitido = datetime.now().isoformat(timespec='seconds')
        pdf = render_report(rel, empresa_nome, versao, emitido)
        with db:
            db.execute('INSERT INTO bh_report_snapshots(employee_id,month,version,issued_at,content_hash,snapshot_json,pdf_bytes) '
                       'VALUES (?,?,?,?,?,?,?)', (employee_id, rel['month'], versao, emitido, resumo, foto, pdf))
            core.log_audit(db, ator(), 'report_issued', 'Emissão de relatório mensal para assinatura',
                           after={'month': rel['month'], 'version': versao}, employee_id=employee_id)
    return send_file(io.BytesIO(pdf), mimetype='application/pdf', as_attachment=True,
                     download_name=f"banco-horas-{rel['employee']['clock_id']}-{rel['month']}-v{versao}.pdf")


@bp.route('/relatorios/<int:snapshot_id>/baixar')
@login_obrigatorio
def relatorio_baixar(snapshot_id):
    foto = get_db().execute('SELECT * FROM bh_report_snapshots WHERE id=?', (snapshot_id,)).fetchone()
    if not foto:
        abort(404)
    pdf = foto['pdf_bytes']
    if _visao_funcionario():
        if foto['employee_id'] != g.usuario['bh_funcionario_id']:
            abort(403)
        dados = json.loads(foto['snapshot_json'])
        rel = dict(dados['report'])
        rel['employee'] = core.get_employee(get_db(), foto['employee_id'])
        pdf = render_report(portal.filtrar_relatorio(rel), dados['company_name'], foto['version'], foto['issued_at'])
    return send_file(io.BytesIO(pdf), mimetype='application/pdf', as_attachment=True,
                     download_name=f"banco-horas-{foto['employee_id']}-{foto['month']}-v{foto['version']}.pdf")


@bp.route('/historico')
@login_obrigatorio
def historico():
    if _visao_funcionario():
        abort(403)
    entradas = core.audit_entries(get_db())
    nomes = {e['id']: e['name'] for e in core.list_employees(get_db())}
    for e in entradas:
        e['created_at'] = e.get('occurred_at', '')
        e['employee_name'] = nomes.get(e.get('employee_id'), 'Sistema')
    return render_template('bh/historico.html', entries=entradas[:2000])


# ------------------------------------------------------------------ escala
@bp.route('/escala')
@login_obrigatorio
def escala():
    mes = request.args.get('month', hoje().strftime('%Y-%m'))
    return render_template('bh/escala.html', report=planning.monthly_roster(get_db(), mes), month=mes, kinds=planning.KINDS)


@bp.route('/escala/salvar', methods=['POST'])
@login_obrigatorio
def escala_salvar():
    mes = request.form.get('month', '')
    core._month_bounds(mes)
    employee_id = core._integer(request.form.get('employee_id'), 'Colaborador', 1)
    planning.save_days(get_db(), employee_id, request.form.get('start'), request.form.get('end'), request.form.get('kind'),
                       request.form.get('start_time', ''), request.form.get('end_time', ''),
                       duration(request.form.get('break_duration', '00:00')), request.form.get('note', ''), ator(),
                       reset=bool(request.form.get('reset')))
    flash('Escala atualizada. O ponto e o banco de horas continuam sendo conferidos no extrato.', 'ok')
    return redirect(url_for('bh.escala', month=mes))


@bp.route('/escala/pdf')
@login_obrigatorio
def escala_pdf():
    mes = request.args.get('month', hoje().strftime('%Y-%m'))
    rel = planning.monthly_roster(get_db(), mes)
    pdf = planning.render_roster(rel, empresa())
    return send_file(io.BytesIO(pdf), mimetype='application/pdf', as_attachment=True, download_name=f'escala-{mes}.pdf')


# ------------------------------------------------------------------ Departamento Pessoal
def _documento_ou_404(document_id, com_conteudo=False):
    try:
        return documents.get_document(get_db(), document_id, com_conteudo)
    except LookupError:
        abort(404)


@bp.route('/pessoal')
@login_obrigatorio
def dp_indice():
    return render_template('bh/dp_indice.html', rows=documents.overview(get_db()))


@bp.route('/pessoal/<int:employee_id>')
@login_obrigatorio
def dp_funcionario(employee_id):
    funcionario = funcionario_ou_404(employee_id)
    ativos = documents.list_documents(get_db(), employee_id)
    return render_template('bh/dp_funcionario.html', employee=funcionario, categories=documents.CATEGORIES,
                           documents=[d for d in ativos if d['category'] != 'folha_ponto'],
                           timesheets=[d for d in ativos if d['category'] == 'folha_ponto'],
                           archived=documents.list_documents(get_db(), employee_id, archived=True),
                           required=[(c, documents.CATEGORIES[c]) for c in documents.REQUIRED],
                           present={d['category'] for d in ativos}, max_mb=documents.MAX_BYTES // (1024 * 1024),
                           current_month=hoje().strftime('%Y-%m'))


@bp.route('/pessoal/<int:employee_id>/documentos', methods=['POST'])
@login_obrigatorio
def dp_enviar(employee_id):
    arquivo = request.files.get('file')
    if not arquivo or not arquivo.filename:
        raise ValueError('Selecione um arquivo.')
    conteudo = arquivo.read(documents.MAX_BYTES + 1)
    documents.add_document(get_db(), employee_id, request.form.get('category', ''), request.form.get('title', ''),
                           request.form.get('month', ''), arquivo.filename, conteudo, request.form.get('note', ''), ator())
    flash('Documento anexado ao cadastro.', 'ok')
    return redirect(url_for('bh.dp_funcionario', employee_id=employee_id))


@bp.route('/pessoal/documentos/<int:document_id>/arquivo')
@login_obrigatorio
def dp_arquivo(document_id):
    doc = _documento_ou_404(document_id, True)
    return send_file(io.BytesIO(doc['content']), mimetype=doc['content_type'],
                     as_attachment=bool(request.args.get('baixar')), download_name=doc['filename'])


@bp.route('/pessoal/documentos/<int:document_id>/imprimir')
@login_obrigatorio
def dp_imprimir(document_id):
    doc = _documento_ou_404(document_id)
    if doc['content_type'] == 'application/pdf':
        return redirect(url_for('bh.dp_arquivo', document_id=document_id))
    return render_template('bh/dp_imprimir.html', document=doc, employee=core.get_employee(get_db(), doc['employee_id']))


@bp.route('/pessoal/documentos/<int:document_id>/arquivar', methods=['POST'])
@login_obrigatorio
def dp_arquivar(document_id):
    doc = _documento_ou_404(document_id)
    documents.set_archived(get_db(), document_id, True, request.form.get('reason'), ator())
    flash('Documento arquivado. Ele continua disponível na lista de arquivados.', 'ok')
    return redirect(url_for('bh.dp_funcionario', employee_id=doc['employee_id']))


@bp.route('/pessoal/documentos/<int:document_id>/restaurar', methods=['POST'])
@login_obrigatorio
def dp_restaurar(document_id):
    doc = _documento_ou_404(document_id)
    documents.set_archived(get_db(), document_id, False, request.form.get('reason'), ator())
    flash('Documento restaurado.', 'ok')
    return redirect(url_for('bh.dp_funcionario', employee_id=doc['employee_id']))


# ------------------------------------------------------------------ mensagens
def _participante():
    if not (messages.eh_funcionario(g.usuario) or equipe_mensagens()):
        abort(403, 'Seu perfil não participa das mensagens.')


def _funcionario_alvo(obrigatorio):
    """Funcionário vê só a própria conversa; a equipe escolhe qual."""
    if messages.eh_funcionario(g.usuario):
        return g.usuario['bh_funcionario_id']
    bruto = request.values.get('employee_id') or request.args.get('employee') or ''
    employee_id = int(bruto) if bruto.isdigit() else None
    if employee_id is None and obrigatorio:
        raise ValueError('Escolha o funcionário.')
    if employee_id is not None:
        try:
            core.get_employee(get_db(), employee_id)
        except ValueError:
            abort(404)
    return employee_id


def _quer_json():
    return 'application/json' in request.headers.get('Accept', '')


@bp.route('/mensagens')
@login_obrigatorio
def mensagens():
    _participante()
    db = get_db()
    equipe = not messages.eh_funcionario(g.usuario)
    employee_id = _funcionario_alvo(False)
    selecionado, lista, pode_enviar = None, [], False
    if employee_id:
        selecionado = core.get_employee(db, employee_id)
        lista = messages.thread(db, employee_id)
        pode_enviar = True if not equipe else messages.has_active_account(db, employee_id)
        if lista:
            messages.mark_read(db, employee_id, 'staff' if equipe else 'employee', lista[-1]['id'])
    return render_template('bh/mensagens.html', staff=equipe, selected=selecionado, can_send=pode_enviar,
                           conversations=messages.conversations(db) if equipe else [],
                           messages=[messages.serialize(m, g.usuario, datetime_br) for m in lista],
                           last_id=lista[-1]['id'] if lista else 0)


@bp.route('/mensagens/enviar', methods=['POST'])
@login_obrigatorio
def msg_enviar():
    _participante()
    try:
        employee_id = _funcionario_alvo(True)
        mensagem = messages.send(get_db(), g.usuario, employee_id, request.form.get('body'))
    except ValueError as erro:
        if _quer_json():
            return jsonify(error=str(erro)), 400
        raise
    if _quer_json():
        return jsonify(message=messages.serialize(mensagem, g.usuario, datetime_br))
    equipe = not messages.eh_funcionario(g.usuario)
    return redirect(url_for('bh.mensagens', employee=employee_id) if equipe else url_for('bh.mensagens'))


@bp.route('/mensagens/novas')
@login_obrigatorio
def msg_novas():
    _participante()
    db = get_db()
    equipe = not messages.eh_funcionario(g.usuario)
    carga = {}
    employee_id = _funcionario_alvo(False)
    if employee_id:
        novas = messages.thread(db, employee_id, after=request.args.get('after', 0, type=int) or 0)
        carga['messages'] = [messages.serialize(m, g.usuario, datetime_br) for m in novas]
        if novas and request.args.get('visible') == '1':
            messages.mark_read(db, employee_id, 'staff' if equipe else 'employee', novas[-1]['id'])
    if equipe and request.args.get('list') == '1':
        carga['conversations'] = [{k: c[k] for k in ('id', 'name', 'unread', 'preview', 'has_account')}
                                  for c in messages.conversations(db)]
    carga['unread'] = messages.unread_total(db, g.usuario, equipe=equipe_mensagens())
    return jsonify(carga)


# ------------------------------------------------------------------ Minha área (funcionário)
@bp.route('/minha-area')
@login_obrigatorio
def portal_home():
    if not messages.eh_funcionario(g.usuario):
        flash('Esta tela é a área do funcionário. Use o Painel de saldos.', 'erro')
        return redirect(url_for('bh.painel') if 'bh_consulta' in g.modulos else url_for('inicio.painel'))
    mes = request.args.get('month', hoje().strftime('%Y-%m'))
    rel = portal.relatorio_funcionario(get_db(), g.usuario['bh_funcionario_id'], mes)
    return render_template('bh/minha_area.html', report=rel, month=rel['month'], employee=rel['employee'],
                           availability=documents.availability(get_db(), g.usuario['bh_funcionario_id']),
                           ocorrencias=ocorrencias.listar(get_db(), g.usuario['bh_funcionario_id']), tipos_ocorrencia=ocorrencias.TIPOS)


@bp.route('/minha-area/ocorrencia', methods=['POST'])
@login_obrigatorio
def portal_ocorrencia():
    if not messages.eh_funcionario(g.usuario):
        abort(403)
    ocorrencias.criar(get_db(), g.usuario['bh_funcionario_id'], request.form.get('data'),
                     request.form.get('tipo'), request.form.get('horarios'), request.form.get('observacao'), ator())
    flash('Ocorrência de ponto enviada. Aguarde a análise da gerência.', 'ok')
    return redirect(url_for('bh.portal_home', month=request.form['data'][:7]))


@bp.route('/ocorrencias/<int:ocorrencia_id>/tratar', methods=['POST'])
@login_obrigatorio
def ocorrencia_tratar(ocorrencia_id):
    mes = month_value()
    ocorrencias.tratar(get_db(), ocorrencia_id, request.form.get('status'), request.form.get('horarios'),
                      request.form.get('classificacao', 'normal'), request.form.get('parecer'), ator())
    flash('Ocorrência tratada e decisão registrada no histórico.', 'ok')
    return redirect(url_for('bh.painel', month=mes))
