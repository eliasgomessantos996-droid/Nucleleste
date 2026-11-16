"""Documentos avulsos: atestado, declarações e recibo."""
from datetime import date

from flask import Blueprint, abort, flash, g, jsonify, redirect, render_template, request, url_for

from . import guias_convenio, login_obrigatorio, util
from .db import agora, config_get, get_db

bp = Blueprint('doc', __name__)

DOCUMENTOS = {
    'atestado': {
        'titulo': 'Atestado',
        'campos': [('nome', 'Nome do paciente', 'text'), ('dias', 'Dias de afastamento', 'number'),
                   ('data_inicio', 'A partir de', 'date'), ('cid', 'CID', 'text'), ('data', 'Data do documento', 'date')],
    },
    'decl_comparecimento': {
        'titulo': 'Declaração de comparecimento',
        'campos': [('nome', 'Nome do paciente', 'text'), ('exame', 'Exame realizado', 'text'),
                   ('periodo', 'Período', 'periodo'), ('dias', 'Dia(s) (ex.: 05 e 06 de agosto de 2026)', 'text'),
                   ('data', 'Data do documento', 'date')],
    },
    'decl_acompanhante': {
        'titulo': 'Declaração de acompanhante',
        'campos': [('acompanhante', 'Nome do acompanhante', 'text'), ('nome', 'Nome do paciente', 'text'),
                   ('exame', 'Exame realizado', 'text'), ('dias', 'Dia(s)', 'text'),
                   ('periodo', 'Período', 'periodo'), ('data', 'Data do documento', 'date')],
    },
    'recibo': {
        'titulo': 'Recibo',
        'campos': [('nome', 'Recebi(emos) de', 'text'), ('valor', 'Valor (R$)', 'text'),
                   ('referente', 'Proveniente de (referente a)', 'text'), ('data', 'Data', 'date')],
    },
    'pedido_exame': {
        'titulo': 'Pedido de exame', 'url': 'doc.pedido_exame', 'campos': [],
    },
    'guia_unimed': {
        'titulo': 'Guia SP/SADT Unimed', 'url': 'doc.guia_editar', 'url_args': {'modelo': 'unimed_sadt'}, 'campos': [],
    },
    'guia_ipsemg': {
        'titulo': 'Pedido IPSEMG (diagnóstico e tratamento)', 'url': 'doc.guia_editar',
        'url_args': {'modelo': 'ipsemg_pedido'}, 'campos': [],
    },
    'guias': {
        'titulo': 'Guias digitadas', 'url': 'doc.guias', 'campos': [],
    },
}
PERIODOS = ['MANHÃ', 'TARDE', 'MANHÃ E TARDE']
PEDIDO_TITULO = 'Pedido de exame'
PEDIDOS_RECENTES = 10


@bp.route('/documentos')
@login_obrigatorio
def indice():
    return render_template('documentos.html', documentos=DOCUMENTOS)


def _normalizar_exames(texto):
    """Um exame por linha, em maiúsculas; tira linhas vazias e o '- ' inicial digitado."""
    exames = []
    for linha in (texto or '').splitlines():
        s = linha.strip()
        if s.startswith('-'):
            s = s[1:].strip()
        if s:
            exames.append(util.maiusculas(s))
    return exames


def _garantir_colunas_pedido(con):
    """Garante as colunas novas em bancos que ainda não passaram pela migração da inicialização."""
    existentes = {r[1] for r in con.execute("PRAGMA table_info(pedidos_exame)")}
    for col in ('convenio', 'hipotese', 'observacoes'):
        if col not in existentes:
            con.execute("ALTER TABLE pedidos_exame ADD COLUMN %s TEXT" % col)


def _form_pedido(v, erro=None):
    """Formulário do pedido: os médicos, convênios, hipóteses e exames vêm do cadastro e dos pedidos já emitidos."""
    con = get_db()
    _garantir_colunas_pedido(con)
    medicos = [dict(m) for m in con.execute(
        "SELECT DISTINCT medico, especialidade, registro FROM pedidos_exame "
        "WHERE medico IS NOT NULL AND medico <> '' ORDER BY id DESC").fetchall()]
    vistos_med = {(m['medico'] or '').strip().upper() for m in medicos}
    for m in con.execute("SELECT nome, crm FROM medicos ORDER BY nome").fetchall():
        chave = (m['nome'] or '').strip().upper()
        if chave and chave not in vistos_med:
            medicos.append({'medico': m['nome'], 'especialidade': '', 'registro': m['crm'] or ''})
            vistos_med.add(chave)
    convenios = [c['nome'] for c in con.execute("SELECT nome FROM convenios WHERE ativo=1 ORDER BY nome").fetchall()]
    vistos_conv = {c.upper() for c in convenios}
    for c in con.execute("SELECT DISTINCT convenio FROM pedidos_exame WHERE convenio IS NOT NULL AND convenio <> '' ORDER BY id DESC").fetchall():
        if c['convenio'].strip().upper() not in vistos_conv:
            convenios.append(c['convenio'].strip())
            vistos_conv.add(c['convenio'].strip().upper())
    hipoteses = [h['hipotese'] for h in con.execute(
        "SELECT DISTINCT hipotese FROM pedidos_exame WHERE hipotese IS NOT NULL AND hipotese <> '' ORDER BY id DESC LIMIT 25").fetchall()]
    exames = [e['nome'] for e in con.execute("SELECT nome FROM exames WHERE ativo=1 ORDER BY ordem, nome").fetchall()]
    recentes = con.execute(
        "SELECT id, data, paciente, exames, medico, convenio FROM pedidos_exame ORDER BY id DESC LIMIT ?",
        (PEDIDOS_RECENTES,)).fetchall()
    if erro:
        flash(erro, 'erro')
    return render_template(
        'pedido_exame_form.html', v=v, medicos=medicos, convenios=convenios, hipoteses=hipoteses, exames=exames,
        recentes=[dict(r, primeiro=(r['exames'] or '').split('\n')[0]) for r in recentes])


@bp.route('/documentos/pedido-exame', methods=['GET', 'POST'])
@login_obrigatorio
def pedido_exame():
    con = get_db()
    _garantir_colunas_pedido(con)
    if request.method == 'GET':
        v = {'paciente': '', 'exames': '', 'data': date.today().isoformat(), 'cliente_id': '',
             'medico': '', 'especialidade': '', 'registro': '', 'convenio': '', 'hipotese': '', 'observacoes': ''}
        ultimo = con.execute(
            "SELECT medico, especialidade, registro, convenio, hipotese, observacoes "
            "FROM pedidos_exame ORDER BY id DESC LIMIT 1").fetchone()
        if ultimo:
            v.update(medico=ultimo['medico'] or '', especialidade=ultimo['especialidade'] or '',
                     registro=ultimo['registro'] or '', convenio=ultimo['convenio'] or '',
                     hipotese=ultimo['hipotese'] or '', observacoes=ultimo['observacoes'] or '')
        cliente = request.args.get('cliente')
        if cliente and cliente.isdigit():
            c = con.execute("SELECT id, nome, convenio FROM clientes WHERE id=?", (int(cliente),)).fetchone()
            if c:
                v['cliente_id'] = c['id']
                v['paciente'] = util.maiusculas(c['nome'])
                if c['convenio']:
                    v['convenio'] = c['convenio']
        return _form_pedido(v)
    campos = ('paciente', 'exames', 'data', 'cliente_id', 'medico', 'especialidade', 'registro',
              'convenio', 'hipotese', 'observacoes')
    v = {k: (request.form.get(k) or '').strip() for k in campos}
    exames = _normalizar_exames(request.form.get('exames'))
    paciente = util.maiusculas(v['paciente'])
    if not paciente or not exames:
        v['exames'] = '\n'.join(exames)
        return _form_pedido(v, 'Informe o paciente e pelo menos um exame.')
    data = v['data'] or date.today().isoformat()
    cliente_id = int(v['cliente_id']) if v['cliente_id'].isdigit() else None
    cur = con.execute(
        "INSERT INTO pedidos_exame (cliente_id, paciente, exames, data, medico, especialidade, registro, "
        "convenio, hipotese, observacoes, usuario, criado_em) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (cliente_id, paciente, '\n'.join(exames), data, v['medico'], v['especialidade'], v['registro'],
         v['convenio'], v['hipotese'], v['observacoes'], g.usuario['usuario'], agora()))
    con.commit()
    return _imprimir_pedido(cur.lastrowid, novo=True)


@bp.route('/documentos/pedido-exame/<int:pid>')
@login_obrigatorio
def pedido_exame_imprimir(pid):
    return _imprimir_pedido(pid)


def _imprimir_pedido(pid, novo=False):
    con = get_db()
    _garantir_colunas_pedido(con)
    p = con.execute("SELECT * FROM pedidos_exame WHERE id=?", (pid,)).fetchone()
    if not p:
        abort(404)
    cli = None
    if p['cliente_id']:
        cli = con.execute(
            "SELECT id, nome, cpf, data_nasc, contato, convenio, cartao_convenio FROM clientes WHERE id=?",
            (p['cliente_id'],)).fetchone()
    clinica_nome = config_get('clinica_nome', 'CENTRO DE MEDICINA NUCLEAR DO LESTE MINEIRO LTDA')
    clinica_cidade = config_get('clinica_cidade', 'Governador Valadares - MG')
    clinica_cnpj = config_get('clinica_cnpj', '73.964.983/0001-50')
    clinica_endereco = config_get('clinica_endereco', '')
    clinica_telefone = config_get('clinica_telefone', '')
    data_ext = util.data_extenso(p['data'])
    f = {
        'id': p['id'],
        'numero': '%05d' % p['id'],
        'cliente_id': p['cliente_id'] or '',
        'paciente': p['paciente'],
        'nascimento': util.data_br(cli['data_nasc']) if cli and cli['data_nasc'] else '',
        'idade': util.idade_texto(cli['data_nasc'], p['data']) if cli and cli['data_nasc'] else '',
        'cpf': (cli['cpf'] or '') if cli else '',
        'contato': (cli['contato'] or '') if cli else '',
        'convenio': (p['convenio'] or (cli['convenio'] if cli else '') or ''),
        'cartao': (cli['cartao_convenio'] or '') if cli else '',
        'hipotese': p['hipotese'] or '',
        'observacoes': p['observacoes'] or '',
        'exames': [e for e in (p['exames'] or '').split('\n') if e],
        'data': util.data_br(p['data']),
        'data_extenso': data_ext,
        'cidade_data': ('%s, %s' % (clinica_cidade, data_ext)) if clinica_cidade else data_ext,
        'medico': p['medico'] or '',
        'especialidade': p['especialidade'] or '',
        'registro': p['registro'] or '',
        'clinica_nome': clinica_nome,
        'clinica_cidade': clinica_cidade,
        'clinica_cnpj': clinica_cnpj,
        'clinica_endereco': clinica_endereco,
        'clinica_telefone': clinica_telefone,
    }
    return render_template('impressao.html', f=f, docs=[['pedido_exame', 1]], opcoes=None, titulo=PEDIDO_TITULO,
                           voltar=url_for('doc.pedido_exame'), novo=novo or None)


@bp.route('/documentos/guias')
@login_obrigatorio
def guias():
    return render_template('guias_lista.html', guias=guias_convenio.listar(get_db()))


def _id_arg(valor):
    """Número vindo da URL ou de campo oculto; None se vazio ou inválido."""
    texto = str(valor or '').strip()
    return int(texto) if texto.isdigit() else None


@bp.route('/documentos/guias/<modelo>/nova', methods=['GET', 'POST'])
@bp.route('/documentos/guias/<int:gid>', methods=['GET', 'POST'])
@login_obrigatorio
def guia_editar(modelo=None, gid=None):
    con = get_db()
    if gid is not None:   # guia já gravada
        salva = guias_convenio.obter(con, gid)
        if not salva:
            abort(404)
        modelo = salva['modelo']
        valores = salva['valores']
        cliente_id, atendimento_id = salva['cliente_id'], salva['atendimento_id']
    else:
        if not guias_convenio.modelo_valido(modelo):
            abort(404)
        cliente_id, atendimento_id = _id_arg(request.args.get('cliente')), _id_arg(request.args.get('atendimento'))
        valores = {} if request.method == 'POST' else guias_convenio.prefill(con, modelo, cliente_id, atendimento_id)
    if request.method == 'POST':
        dados = guias_convenio.dados_do_form(request.form, modelo)
        cliente_id = _id_arg(request.form.get('cliente_id')) or cliente_id
        atendimento_id = _id_arg(request.form.get('atendimento_id')) or atendimento_id
        novo_gid = guias_convenio.salvar(con, modelo, dados, cliente_id, atendimento_id, g.usuario['usuario'], gid=gid)
        editar = url_for('doc.guia_editar', gid=novo_gid)
        imprimir = url_for('doc.guia_imprimir', gid=novo_gid)
        if request.headers.get('X-Requisicao') == 'json':   # botão "Salvar e imprimir" (a página fica no lugar)
            return jsonify(ok=True, gid=novo_gid, editar=editar, imprimir=imprimir)
        if request.form.get('acao') == 'imprimir':
            return redirect(imprimir)
        flash('Guia salva.', 'ok')
        return redirect(editar)
    cliente = con.execute("SELECT id, nome FROM clientes WHERE id=?", (cliente_id,)).fetchone() if cliente_id else None
    return render_template('guia_form.html', modelo=modelo, m=guias_convenio.MODELOS[modelo], v=valores, gid=gid,
                           cliente=cliente, cliente_id=cliente_id or '', atendimento_id=atendimento_id or '')


@bp.route('/documentos/guias/<int:gid>/imprimir')
@login_obrigatorio
def guia_imprimir(gid):
    guia = guias_convenio.obter(get_db(), gid)
    if not guia:
        abort(404)
    m = guias_convenio.MODELOS[guia['modelo']]
    f = guias_convenio.montar_impressao(guia['modelo'], guia['valores'])
    return render_template('impressao.html', f=f, docs=[[m['ficha'], 1]], opcoes=None, titulo=m['titulo'],
                           voltar=url_for('doc.guia_editar', gid=gid), novo=None)


@bp.route('/documentos/guias/<int:gid>/excluir', methods=['POST'])
@login_obrigatorio
def guia_excluir(gid):
    con = get_db()
    if not guias_convenio.obter(con, gid):
        abort(404)
    guias_convenio.excluir(con, gid)
    flash('Guia excluída.', 'ok')
    return redirect(url_for('doc.guias'))


@bp.route('/documentos/<tipo>', methods=['GET', 'POST'])
@login_obrigatorio
def documento(tipo):
    doc = DOCUMENTOS.get(tipo)
    if not doc or 'url' in doc:   # tipos com tela própria (ex.: pedido de exame) não usam esta rota
        abort(404)
    if request.method == 'GET':
        valores = {'data': date.today().isoformat(), 'data_inicio': date.today().isoformat(), 'dias': ''}
        return render_template('documento_form.html', tipo=tipo, doc=doc, v=valores, periodos=PERIODOS)
    v = {k: (request.form.get(k) or '').strip() for k, _, _ in doc['campos']}
    cidade = config_get('clinica_cidade', 'Governador Valadares - MG')
    f = {
        'nome': util.maiusculas(v.get('nome')),
        'acompanhante': util.maiusculas(v.get('acompanhante')),
        'exame': util.maiusculas(v.get('exame')),
        'periodo': v.get('periodo', ''),
        'dias': v.get('dias', ''),
        'data': util.data_br(v.get('data')),
        'data_extenso': util.data_extenso(v.get('data')),
        'cidade_data': '%s, %s' % (cidade, util.data_extenso(v.get('data'))),
    }
    if tipo == 'atestado':
        f['dias_texto'] = '%s Dia(s)' % v.get('dias') if v.get('dias') else ''
        f['data_inicio'] = util.data_br(v.get('data_inicio'))
        f['cid_texto'] = 'CID  %s' % v.get('cid') if v.get('cid') else ''
    if tipo == 'recibo':
        valor = util.para_valor(v.get('valor'))
        f['valor'] = util.moeda(valor) if valor is not None else v.get('valor', '')
        f['valor_extenso'] = util.valor_extenso(valor) if valor is not None else ''
        f['referente'] = v.get('referente', '').upper()
    return render_template('impressao.html', f=f, docs=[[tipo, 1]], opcoes=None, titulo=doc['titulo'],
                           voltar=url_for('doc.documento', tipo=tipo), novo=None)
