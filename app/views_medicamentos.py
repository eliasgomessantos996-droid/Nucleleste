"""Agenda de medicamentos (doses de Iodo, Gálio e PCI)."""
from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from . import fichas, login_obrigatorio, util
from .db import agora, get_db
from .views_atendimentos import _docs_da_url, _opcoes_docs

bp = Blueprint('med', __name__)

MEDICAMENTOS = ['IODO', 'GÁLIO', 'PCI']
PREPAROS = ['30 DIAS', '15 DIAS']
SEM_PREPARO = 'SEM PREPARO'
DOCS_DOSE = ['ficha_agendamento', 'iodo_15dias', 'iodo_30dias', 'etiqueta_cliente']


@bp.route('/medicamentos')
@login_obrigatorio
def lista():
    db = get_db()
    status = request.args.get('status', 'AGENDADO')
    medicamento = request.args.get('medicamento', '')
    dia = request.args.get('dia', '')
    busca = (request.args.get('q') or '').strip()
    where, params = ['1=1'], []
    if status:
        where.append('status=?')
        params.append(status)
    if medicamento:
        where.append('medicamento=?')
        params.append(medicamento)
    if dia:
        where.append('data_dose=?')
        params.append(dia)
    if busca:
        where.append('UPPER(paciente) LIKE ?')
        params.append('%' + busca.upper() + '%')
    rows = db.execute('SELECT * FROM doses WHERE %s ORDER BY data_dose, paciente' % ' AND '.join(where), params).fetchall()
    tpl = 'doses_impressao.html' if request.args.get('imprimir') else 'doses.html'
    return render_template(tpl, rows=rows, status=status, medicamento=medicamento, dia=dia, q=busca,
                           medicamentos=MEDICAMENTOS)


@bp.route('/medicamentos/novo', methods=['GET', 'POST'])
@bp.route('/medicamentos/<int:did>', methods=['GET', 'POST'])
@login_obrigatorio
def editar(did=None):
    db = get_db()
    dose = db.execute('SELECT * FROM doses WHERE id=?', (did,)).fetchone() if did else None
    if did and not dose:
        abort(404)
    campos = ['cliente_id', 'medicamento', 'mci', 'preparo', 'dieta', 'susp_medicacao', 'data_dose', 'medico', 'obs']
    if dose:
        f = {k: dose[k] or '' for k in campos}
        f['sem_preparo'] = dose['dieta'] == SEM_PREPARO
    else:
        f = {k: '' for k in campos}
        f['cliente_id'] = request.args.get('cliente', '')
        f['sem_preparo'] = False
    if request.method == 'POST':
        f = {k: (request.form.get(k) or '').strip() for k in campos}
        f['sem_preparo'] = bool(request.form.get('sem_preparo'))
        f['medico'] = util.maiusculas(f['medico'])
        if f['sem_preparo']:
            f['dieta'] = f['susp_medicacao'] = SEM_PREPARO
        cliente = db.execute('SELECT * FROM clientes WHERE id=?', (f['cliente_id'] or 0,)).fetchone()
        erros = []
        if not cliente and not dose:
            erros.append('Selecione o cliente.')
        if not f['medico']:
            erros.append('Informe o médico solicitante.')
        if f['medicamento'] not in MEDICAMENTOS:
            erros.append('Selecione o medicamento!')
        if not util.para_data(f['data_dose']):
            erros.append('Informe a data da dose.')
        if not f['dieta'] or not f['susp_medicacao']:
            erros.append('Informe a data da dieta e da suspensão da medicação (ou marque "Sem preparo").')
        if erros:
            for e in erros:
                flash(e, 'erro')
        else:
            dieta = f['dieta'] if f['dieta'] == SEM_PREPARO else util.data_iso(f['dieta'])
            susp = f['susp_medicacao'] if f['susp_medicacao'] == SEM_PREPARO else util.data_iso(f['susp_medicacao'])
            if cliente:
                pac = (cliente['id'], cliente['nome'], cliente['data_nasc'], cliente['contato'], cliente['cpf'],
                       util.idade_texto(cliente['data_nasc']))
            else:
                pac = (dose['cliente_id'], dose['paciente'], dose['data_nasc'], dose['contato'], dose['cpf'], dose['idade'])
            valores = pac + (f['medicamento'], f['mci'], f['preparo'], dieta, susp, util.data_iso(f['data_dose']),
                             f['medico'], f['obs'] or None)
            if dose:
                db.execute('UPDATE doses SET cliente_id=?, paciente=?, data_nasc=?, contato=?, cpf=?, idade=?, '
                           'medicamento=?, mci=?, preparo=?, dieta=?, susp_medicacao=?, data_dose=?, medico=?, obs=? '
                           'WHERE id=?', valores + (did,))
                novo_id = did
            else:
                cur = db.execute('INSERT INTO doses (cliente_id, paciente, data_nasc, contato, cpf, idade, medicamento, '
                                 'mci, preparo, dieta, susp_medicacao, data_dose, medico, obs, status, usuario, criado_em) '
                                 "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,'AGENDADO',?,?)",
                                 valores + (g.usuario['usuario'], agora()))
                novo_id = cur.lastrowid
            if not db.execute('SELECT 1 FROM medicos WHERE TRIM(UPPER(nome))=?', (f['medico'],)).fetchone():
                db.execute('INSERT INTO medicos (nome) VALUES (?)', (f['medico'],))
            db.commit()
            flash('Dados inseridos com sucesso!', 'ok')
            return redirect(url_for('med.imprimir', did=novo_id, novo=1))
    medicos = [r['nome'] for r in db.execute(
        "SELECT DISTINCT TRIM(nome) AS nome FROM medicos WHERE TRIM(COALESCE(nome,''))<>'' ORDER BY 1").fetchall()]
    for k in ('dieta', 'susp_medicacao', 'data_dose'):
        if f.get(k) and f[k] != SEM_PREPARO:
            f[k] = util.data_iso(f[k]) or f[k]
    return render_template('dose_form.html', f=f, dose=dose, medicos=medicos, medicamentos=MEDICAMENTOS,
                           preparos=PREPAROS, sem_preparo=SEM_PREPARO)


@bp.route('/medicamentos/<int:did>/status', methods=['POST'])
@login_obrigatorio
def status(did):
    novo = request.form.get('status')
    if novo not in ('AGENDADO', 'CONCLUIDO', 'CANCELADO'):
        abort(400)
    db = get_db()
    db.execute('UPDATE doses SET status=? WHERE id=?', (novo, did))
    db.commit()
    flash('Medicamento marcado como %s!' % novo, 'ok')
    return redirect(request.form.get('voltar') or url_for('med.lista'))


@bp.route('/medicamentos/<int:did>/imprimir')
@login_obrigatorio
def imprimir(did):
    db = get_db()
    dose = db.execute('SELECT * FROM doses WHERE id=?', (did,)).fetchone()
    if not dose:
        abort(404)
    cliente = db.execute('SELECT * FROM clientes WHERE id=?', (dose['cliente_id'] or 0,)).fetchone()
    padrao = [['ficha_agendamento', 1]]
    # Como na planilha: preparo de 15 dias -> IODOHIPER; 30 dias -> IODOPOSCIR
    if dose['preparo'] == '15 DIAS':
        padrao.append(['iodo_15dias', 1])
    elif dose['preparo'] == '30 DIAS':
        padrao.append(['iodo_30dias', 1])
    docs = _docs_da_url(padrao)
    f = fichas.dados_dose(dose, cliente)
    titulo = '%s - %s - %s' % (f['nome'], f['medicamento'], f['data_dose'])
    return render_template('impressao.html', f=f, docs=docs, opcoes=_opcoes_docs(DOCS_DOSE, docs), titulo=titulo,
                           voltar=url_for('med.lista'), novo=request.args.get('novo'))
