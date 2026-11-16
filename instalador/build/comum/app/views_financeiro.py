"""Contas a pagar e relatórios de atendimentos."""
import calendar
import io
from datetime import date

from flask import Blueprint, abort, flash, g, jsonify, redirect, render_template, request, send_file, url_for

from . import contas_lotes
from . import contas_recorrentes as rec_mod
from . import fornecedores as forn_mod
from . import fornecedores_docs as fdocs
from . import login_obrigatorio, util
from .contas_lotes import ErroLote
from .db import config_get, get_db

bp = Blueprint('fin', __name__)

CATEGORIAS = [
    'Receitas de consultas e exames', 'Receitas de convênios', 'Receitas particulares',
    'Materiais médicos e hospitalares', 'Medicamentos e radiofármacos', 'Honorários médicos',
    'Salários e benefícios', 'Encargos trabalhistas', 'Aluguel e condomínio', 'Água, energia e internet',
    'Manutenção de equipamentos', 'Manutenção predial', 'Limpeza e conservação', 'Serviços terceirizados',
    'Sistemas e informática', 'Material de escritório', 'Impostos e tributos', 'Despesas bancárias',
    'Marketing e publicidade', 'Transporte e combustível', 'Licenças e taxas',
    'Contabilidade e assessoria jurídica', 'Equipamentos e investimentos', 'Empréstimos e financiamentos',
    'Resíduos hospitalares', 'Segurança do trabalho', 'Glosas e inadimplência', 'Pró-labore dos sócios',
    'Distribuição de lucros', 'Outras receitas e despesas',
]
BANCOS = ['BANCO DO BRASIL', 'UNICRED', 'DINHEIRO', 'CAIXA']


@bp.route('/contas')
@login_obrigatorio
def contas():
    db = get_db()
    rec_mod.gerar(db)   # contas recorrentes do mês atual e do seguinte entram aqui antes da lista
    status = request.args.get('status', 'ABERTO')
    de, ate = request.args.get('de', ''), request.args.get('ate', '')
    where, params = ['1=1'], []
    # 'ABERTO' é só a lista normal; contas em lote de pagamento aparecem em 'LOTE'
    if status == 'ABERTO':
        where.append("status='ABERTO' AND lote_id IS NULL")
    elif status == 'LOTE':
        where.append("status='ABERTO' AND lote_id IS NOT NULL")
    elif status:
        where.append('status=?')
        params.append(status)
    if de:
        where.append('vencimento>=?')
        params.append(de)
    if ate:
        where.append('vencimento<=?')
        params.append(ate)
    rows = db.execute('SELECT * FROM contas WHERE %s ORDER BY vencimento, id' % ' AND '.join(where), params).fetchall()
    total = sum(r['valor'] or 0 for r in rows)
    return render_template('contas.html', rows=rows, status=status, de=de, ate=ate, total=total, bancos=BANCOS,
                           hoje=date.today().isoformat())


@bp.route('/contas/nova', methods=['GET', 'POST'])
@bp.route('/contas/<int:cid>', methods=['GET', 'POST'])
@login_obrigatorio
def conta_editar(cid=None):
    db = get_db()
    conta = db.execute('SELECT * FROM contas WHERE id=?', (cid,)).fetchone() if cid else None
    if cid and not conta:
        abort(404)
    campos = ['descricao', 'categoria', 'vencimento', 'valor', 'obs', 'fornecedor', 'nota_fiscal']
    f = {k: (conta[k] if conta and conta[k] is not None else '') for k in campos}
    f['fornecedor_id'] = str(conta['fornecedor_id'] or '') if conta else (request.args.get('fornecedor_id') or '')
    f.update(parcelar='', parcelas='2', parcela_tipo='total', recorrente='', dia_vencimento='')
    datas_form = []   # vencimentos digitados para cada parcela (para reaparecerem se der erro)
    if conta:
        f['valor'] = util.moeda(conta['valor'])
    else:
        f['vencimento'] = date.today().isoformat()
        f['dia_vencimento'] = str(date.today().day)
    if request.method == 'POST':
        f = {k: (request.form.get(k) or '').strip() for k in campos + ['fornecedor_id', 'parcelar', 'parcelas', 'parcela_tipo',
                                                                       'recorrente', 'dia_vencimento']}
        f['descricao'] = util.maiusculas(f['descricao'])
        valor = util.para_valor(f['valor'])
        n_parc = int(f['parcelas']) if f['parcelas'].isdigit() else 0
        datas_form = [(request.form.get('venc_parcela_%d' % i) or '').strip() for i in range(1, min(n_parc, 60) + 1)]
        forn = forn_mod.obter(db, int(f['fornecedor_id'])) if f['fornecedor_id'].isdigit() else None
        nome_forn = forn['nome'] if forn else (util.maiusculas(f['fornecedor']) or None)
        if not f['descricao'] or not f['categoria'] or valor is None or not util.para_data(f['vencimento']):
            flash('Preencha descrição, categoria, valor e vencimento.', 'erro')
        elif not conta and f['parcelar'] == '1':
            try:
                parcelas = forn_mod.planejar_parcelas(valor, f['vencimento'], int(f['parcelas'] or 0), f['parcela_tipo'] != 'cada', datas_form)
            except (forn_mod.ErroFornecedor, ValueError) as e:
                flash(str(e) if isinstance(e, forn_mod.ErroFornecedor) else 'Informe o número de parcelas.', 'erro')
            else:
                forn_mod.criar_parcelas(db, {'descricao': f['descricao'], 'categoria': f['categoria'], 'obs': f['obs'] or None,
                                             'fornecedor': nome_forn, 'fornecedor_id': forn['id'] if forn else None,
                                             'nota_fiscal': f['nota_fiscal'] or None}, parcelas, g.usuario['usuario'])
                flash('Compra parcelada lançada em %d parcelas (1/%d a %d/%d).' % (len(parcelas), len(parcelas), len(parcelas), len(parcelas)), 'ok')
                return redirect(url_for('fin.conta_editar') if request.form.get('continuar') else url_for('fin.contas'))
        elif not conta and f['recorrente'] == '1':
            try:
                rec_mod.salvar(db, {'descricao': f['descricao'], 'categoria': f['categoria'], 'valor': valor, 'dia': f['dia_vencimento'],
                                    'fornecedor': nome_forn, 'fornecedor_id': forn['id'] if forn else None, 'obs': f['obs']},
                               g.usuario['usuario'], primeiro_venc=util.data_iso(f['vencimento']))
            except rec_mod.ErroRecorrente as e:
                flash(str(e), 'erro')
            else:
                flash('Conta recorrente cadastrada: ela será lançada todo mês no dia %s.' % f['dia_vencimento'], 'ok')
                return redirect(url_for('fin.conta_recorrentes'))
        else:
            dados = (f['descricao'], f['categoria'], util.data_iso(f['vencimento']), valor, f['obs'] or None,
                     nome_forn, forn['id'] if forn else None, f['nota_fiscal'] or None)
            if conta:
                db.execute('UPDATE contas SET descricao=?, categoria=?, vencimento=?, valor=?, obs=?, fornecedor=?, '
                           'fornecedor_id=?, nota_fiscal=? WHERE id=?', dados + (cid,))
            else:
                db.execute('INSERT INTO contas (descricao, categoria, vencimento, valor, obs, fornecedor, fornecedor_id, nota_fiscal, '
                           "status, usuario) VALUES (?,?,?,?,?,?,?,?,'ABERTO',?)", dados + (g.usuario['usuario'],))
            db.commit()
            flash('Dados inseridos com sucesso!', 'ok')
            if request.form.get('continuar'):
                return redirect(url_for('fin.conta_editar'))
            return redirect(url_for('fin.contas'))
    atuais = forn_mod.listar(db, so_ativos=True)
    if f['fornecedor_id'].isdigit() and not any(str(x['id']) == f['fornecedor_id'] for x in atuais):
        extra = forn_mod.obter(db, int(f['fornecedor_id']))
        if extra:
            atuais.append(extra)
    return render_template('conta_form.html', f=f, conta=conta, categorias=CATEGORIAS, fornecedores=atuais, datas_form=datas_form,
                           parcela=forn_mod.rotulo_parcela(conta) if conta else '')


@bp.route('/contas/<int:cid>/excluir-parcelas', methods=['POST'])
@login_obrigatorio
def conta_excluir_parcelas(cid):
    try:
        n = forn_mod.excluir_parcelas_abertas(get_db(), cid)
        flash('%d parcela(s) em aberto desta compra excluída(s).' % n, 'ok')
    except forn_mod.ErroFornecedor as e:
        flash(str(e), 'erro')
    return redirect(url_for('fin.contas'))


# ---------------------------------------------------------------- contas recorrentes
@bp.route('/contas/recorrentes')
@login_obrigatorio
def conta_recorrentes():
    db = get_db()
    rec_mod.gerar(db)
    return render_template('contas_recorrentes.html', rows=rec_mod.listar(db))


@bp.route('/contas/recorrentes/<int:rid>/editar', methods=['GET', 'POST'])
@login_obrigatorio
def conta_recorrente_editar(rid):
    db = get_db()
    atual = rec_mod.obter(db, rid)
    if not atual:
        abort(404)
    f = dict(atual)
    f['valor'] = util.moeda(atual['valor'])
    f['dia'] = str(atual['dia_vencimento'])
    f['fornecedor_id'] = str(atual['fornecedor_id'] or '')
    if request.method == 'POST':
        f = {k: (request.form.get(k) or '').strip() for k in ('descricao', 'categoria', 'valor', 'dia', 'fornecedor', 'fornecedor_id', 'obs')}
        forn = forn_mod.obter(db, int(f['fornecedor_id'])) if f['fornecedor_id'].isdigit() else None
        nome_forn = forn['nome'] if forn else (util.maiusculas(f['fornecedor']) or None)
        try:
            rec_mod.salvar(db, dict(f, valor=util.para_valor(f['valor']), fornecedor=nome_forn,
                                    fornecedor_id=forn['id'] if forn else None), g.usuario['usuario'], rid=rid)
        except rec_mod.ErroRecorrente as e:
            flash(str(e), 'erro')
        else:
            flash('Conta recorrente salva. As contas já lançadas não mudam.', 'ok')
            return redirect(url_for('fin.conta_recorrentes'))
    atuais = forn_mod.listar(db, so_ativos=True)
    if f['fornecedor_id'].isdigit() and not any(str(x['id']) == f['fornecedor_id'] for x in atuais):
        extra = forn_mod.obter(db, int(f['fornecedor_id']))
        if extra:
            atuais.append(extra)
    return render_template('contas_recorrente_form.html', f=f, categorias=CATEGORIAS, fornecedores=atuais)


@bp.route('/contas/recorrentes/<int:rid>/alternar', methods=['POST'])
@login_obrigatorio
def conta_recorrente_alternar(rid):
    db = get_db()
    try:
        ativo = rec_mod.alternar_ativo(db, rid)
        if ativo:
            rec_mod.gerar(db)   # ao reativar, lança o que já deveria ter entrado
        flash('Conta recorrente reativada.' if ativo else 'Conta recorrente pausada: nenhuma conta nova será lançada.', 'ok')
    except rec_mod.ErroRecorrente as e:
        flash(str(e), 'erro')
    return redirect(url_for('fin.conta_recorrentes'))


@bp.route('/contas/recorrentes/<int:rid>/excluir', methods=['POST'])
@login_obrigatorio
def conta_recorrente_excluir(rid):
    try:
        rec_mod.excluir(get_db(), rid)
        flash('Conta recorrente excluída. As contas já lançadas continuam na lista.', 'ok')
    except rec_mod.ErroRecorrente as e:
        flash(str(e), 'erro')
    return redirect(url_for('fin.conta_recorrentes'))


# ---------------------------------------------------------------- fornecedores
@bp.route('/contas/fornecedores')
@login_obrigatorio
def conta_fornecedores():
    busca = (request.args.get('q') or '').strip()
    return render_template('fornecedores.html', rows=forn_mod.listar(get_db(), busca), q=busca)


@bp.route('/contas/fornecedores/lista.json')
@login_obrigatorio
def conta_fornecedores_json():
    return jsonify([{'id': r['id'], 'nome': r['nome']} for r in forn_mod.listar(get_db(), so_ativos=True)])


@bp.route('/contas/fornecedores/consulta')
@login_obrigatorio
def conta_fornecedor_consulta():
    """Consulta o CNPJ na internet e devolve os dados para preencher o cadastro."""
    try:
        return jsonify(ok=True, dados=forn_mod.consultar_cnpj(request.args.get('cnpj', '')))
    except forn_mod.ErroFornecedor as e:
        return jsonify(ok=False, erro=str(e)), 200


@bp.route('/contas/fornecedores/novo', methods=['GET', 'POST'])
@bp.route('/contas/fornecedores/<int:fid>', methods=['GET', 'POST'])
@login_obrigatorio
def conta_fornecedor_editar(fid=None):
    db = get_db()
    atual = forn_mod.obter(db, fid) if fid else None
    if fid and not atual:
        abort(404)
    f = dict(atual) if atual else {k: '' for k in forn_mod.CAMPOS}
    f.setdefault('ativo', 1)
    if request.method == 'POST':
        f = {k: (request.form.get(k) or '').strip() for k in forn_mod.CAMPOS}
        f['ativo'] = 1 if request.form.get('ativo') else 0
        try:
            novo = forn_mod.salvar(db, f, g.usuario['usuario'], fid)
        except forn_mod.ErroFornecedor as e:
            flash(str(e), 'erro')
        else:
            flash('Fornecedor salvo com sucesso!', 'ok')
            if not fid and request.form.get('para_conta'):
                return redirect(url_for('fin.conta_editar', fornecedor_id=novo))
            return redirect(url_for('fin.conta_fornecedores'))
    return render_template('fornecedor_form.html', f=f, fornecedor=atual, para_conta=request.args.get('para_conta') or request.form.get('para_conta'))


@bp.route('/contas/fornecedores/<int:fid>/excluir', methods=['POST'])
@login_obrigatorio
def conta_fornecedor_excluir(fid):
    try:
        f = forn_mod.excluir(get_db(), fid)
        flash('Fornecedor %s excluído. As contas dele continuam lançadas.' % f['nome'], 'ok')
    except forn_mod.ErroFornecedor as e:
        flash(str(e), 'erro')
    return redirect(url_for('fin.conta_fornecedores'))


def _rel_fornecedores():
    db = get_db()
    hoje = date.today()
    de = util.para_data(request.args.get('de')) or hoje.replace(day=1)
    ate = util.para_data(request.args.get('ate')) or hoje.replace(day=calendar.monthrange(hoje.year, hoje.month)[1])
    if ate < de:
        de, ate = ate, de
    status = request.args.get('status') if request.args.get('status') in ('ABERTO', 'PAGO') else ''
    fid = int(request.args['fornecedor']) if (request.args.get('fornecedor') or '').isdigit() else None
    return forn_mod.relatorio(db, de, ate, status, fid), fid


@bp.route('/contas/fornecedores/relatorio')
@login_obrigatorio
def conta_fornecedores_relatorio():
    rel, fid = _rel_fornecedores()
    return render_template('fornecedores_relatorio.html', rel=rel, fid=fid, fornecedores=forn_mod.listar(get_db()))


@bp.route('/contas/fornecedores/relatorio.pdf')
@login_obrigatorio
def conta_fornecedores_relatorio_pdf():
    rel, _ = _rel_fornecedores()
    pdf = fdocs.relatorio_pdf(rel, config_get('clinica_nome', ''))
    return send_file(io.BytesIO(pdf), mimetype='application/pdf', as_attachment=request.args.get('baixar') == '1',
                     download_name='contas-por-fornecedor.pdf')


@bp.route('/contas/fornecedores/relatorio.xlsx')
@login_obrigatorio
def conta_fornecedores_relatorio_xlsx():
    rel, _ = _rel_fornecedores()
    return send_file(io.BytesIO(fdocs.relatorio_xlsx(rel, config_get('clinica_nome', ''))), as_attachment=True,
                     download_name='contas-por-fornecedor.xlsx',
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@bp.route('/contas/<int:cid>/quitar', methods=['POST'])
@login_obrigatorio
def conta_quitar(cid):
    banco = request.form.get('banco') or ''
    if banco not in BANCOS:
        flash('É obrigatório selecionar o banco para a quitação!', 'erro')
        return redirect(request.form.get('voltar') or url_for('fin.contas'))
    db = get_db()
    data_pag = util.data_iso(request.form.get('data_pagamento')) or date.today().isoformat()
    forma = request.form.get('forma_pagamento') or None
    linha = db.execute('SELECT lote_id FROM contas WHERE id=?', (cid,)).fetchone()
    # conta de lote de pagamento: a quitação passa pelo lote (fica registrada nele)
    if not (linha and linha['lote_id'] and contas_lotes.quitar(db, linha['lote_id'], [cid], g.usuario['usuario'], data_pag, forma, banco)):
        db.execute("UPDATE contas SET status='PAGO', banco_pagamento=?, data_pagamento=?, forma_pagamento=?, quitado_por=? WHERE id=?",
                   (banco, data_pag, forma, g.usuario['usuario'], cid))
    db.commit()
    flash('Conta quitada com sucesso!', 'ok')
    return redirect(request.form.get('voltar') or url_for('fin.contas'))


@bp.route('/contas/<int:cid>/reabrir', methods=['POST'])
@login_obrigatorio
def conta_reabrir(cid):
    db = get_db()
    contas_lotes.ao_reabrir(db, cid, g.usuario['usuario'])
    db.execute("UPDATE contas SET status='ABERTO', banco_pagamento=NULL, data_pagamento=NULL WHERE id=?", (cid,))
    db.commit()
    flash('Conta reaberta.', 'ok')
    return redirect(request.form.get('voltar') or url_for('fin.contas'))


@bp.route('/contas/<int:cid>/excluir', methods=['POST'])
@login_obrigatorio
def conta_excluir(cid):
    db = get_db()
    contas_lotes.ao_excluir(db, cid)
    db.execute('DELETE FROM contas WHERE id=?', (cid,))
    db.commit()
    flash('Registro excluído com sucesso!', 'ok')
    return redirect(url_for('fin.contas'))


@bp.route('/contas/imprimir', methods=['POST'])
@login_obrigatorio
def contas_imprimir():
    ids = [int(i) for i in request.form.getlist('ids') if i.isdigit()]
    banco = request.form.get('banco') or ''
    voltar = request.form.get('voltar') or url_for('fin.contas')
    if not ids:
        flash('Marque pelo menos uma conta para imprimir!', 'erro')
        return redirect(voltar)
    if banco not in BANCOS:
        flash('Selecione o banco em que as contas serão pagas!', 'erro')
        return redirect(voltar)
    db = get_db()
    try:
        lote_id = contas_lotes.criar(db, ids, banco, g.usuario['usuario'])
    except ErroLote as e:
        flash(str(e), 'erro')
        return redirect(voltar)
    db.commit()
    n = db.execute('SELECT COUNT(*) FROM contas_lote_itens WHERE lote_id=?', (lote_id,)).fetchone()[0]
    flash('Lote de pagamento nº %d criado com %d conta(s) para o banco %s. As contas saíram da lista normal e ficam em '
          '"Em pagamento" até a quitação.' % (lote_id, n, banco), 'ok')
    return redirect(url_for('fin.conta_lote', lote_id=lote_id, imprimir=1))


# ---------------------------------------------------------------- lotes de pagamento
@bp.route('/contas/lotes')
@login_obrigatorio
def conta_lotes():
    status = request.args.get('status') if request.args.get('status') in ('ABERTO', 'CONCLUIDO') else ''
    return render_template('contas_lotes.html', lotes=contas_lotes.listar(get_db(), status), status=status)


@bp.route('/contas/lotes/<int:lote_id>')
@login_obrigatorio
def conta_lote(lote_id):
    dados = contas_lotes.obter(get_db(), lote_id)
    if not dados:
        abort(404)
    return render_template('conta_lote.html', d=dados, bancos=BANCOS, hoje=date.today().isoformat(),
                           imprimir=request.args.get('imprimir'))


@bp.route('/contas/lotes/<int:lote_id>/acao', methods=['POST'])
@login_obrigatorio
def conta_lote_acao(lote_id):
    db = get_db()
    if not contas_lotes.obter(db, lote_id):
        abort(404)
    acao = request.form.get('acao') or ''
    ids = [int(i) for i in request.form.getlist('ids') if i.isdigit()]
    voltar = url_for('fin.conta_lote', lote_id=lote_id)
    usuario = g.usuario['usuario']
    if acao in ('quitar_marcadas', 'devolver') and not ids:
        flash('Marque pelo menos uma conta.', 'erro')
        return redirect(voltar)
    if acao in ('quitar_marcadas', 'quitar_todas'):
        banco = request.form.get('banco') or ''
        if banco not in BANCOS:
            flash('É obrigatório selecionar o banco para a quitação!', 'erro')
            return redirect(voltar)
        data_pag = util.data_iso(request.form.get('data_pagamento')) or date.today().isoformat()
        conta_ids = ids if acao == 'quitar_marcadas' else None
        n = contas_lotes.quitar(db, lote_id, conta_ids, usuario, data_pag, request.form.get('forma_pagamento') or None, banco)
        db.commit()
        if n:
            flash('%d conta(s) quitada(s) com o banco %s.' % (n, banco), 'ok')
        else:
            flash('Nenhuma conta pendente para quitar neste lote.', 'erro')
    elif acao == 'devolver':
        n = contas_lotes.devolver(db, lote_id, ids, usuario)
        db.commit()
        if n:
            flash('%d conta(s) devolvida(s) para a lista de contas a pagar.' % n, 'ok')
        else:
            flash('Nenhuma conta pendente entre as marcadas.', 'erro')
    else:
        abort(400)
    return redirect(voltar)


@bp.route('/contas/lotes/<int:lote_id>/imprimir')
@login_obrigatorio
def conta_lote_imprimir(lote_id):
    dados = contas_lotes.obter(get_db(), lote_id)
    if not dados:
        abort(404)
    # contas devolvidas saem da impressão; as pagas continuam para registro
    rows = [r for r in get_db().execute(
        "SELECT c.* FROM contas c JOIN contas_lote_itens i ON i.conta_id=c.id "
        "WHERE i.lote_id=? AND i.situacao<>'DEVOLVIDA' ORDER BY c.vencimento, c.id", (lote_id,)).fetchall()]
    total = sum(r['valor'] or 0 for r in rows)
    lote = dados['lote']
    return render_template('contas_impressao.html', rows=rows, banco=lote['banco'], total=total, lote=lote)


# ---------------------------------------------------------------- relatórios
AGRUPAMENTOS = {
    'exame': ('Exame', "UPPER(TRIM(exame))"),
    'convenio': ('Convênio', "UPPER(TRIM(convenio))"),
    'medico': ('Médico solicitante', "UPPER(TRIM(medico))"),
    'usuario': ('Usuário', "usuario"),
    'dia': ('Dia', "data"),
    'mes': ('Mês', "substr(data,1,7)"),
}


@bp.route('/relatorios')
@login_obrigatorio
def relatorios():
    db = get_db()
    hoje = date.today()
    de = request.args.get('de') or hoje.replace(day=1).isoformat()
    ate = request.args.get('ate') or hoje.isoformat()
    agrupar = request.args.get('agrupar') if request.args.get('agrupar') in AGRUPAMENTOS else 'exame'
    exame = (request.args.get('exame') or '').strip()
    convenio = (request.args.get('convenio') or '').strip()
    where, params = ['data BETWEEN ? AND ?'], [de, ate]
    if exame:
        where.append('UPPER(TRIM(exame))=?')
        params.append(exame.upper())
    if convenio:
        where.append('UPPER(TRIM(convenio))=?')
        params.append(convenio.upper())
    rotulo, expr = AGRUPAMENTOS[agrupar]
    grupos = db.execute('SELECT %s AS grupo, COUNT(*) AS qtd FROM atendimentos WHERE %s GROUP BY 1 ORDER BY %s'
                        % (expr, ' AND '.join(where), '1' if agrupar in ('dia', 'mes') else '2 DESC, 1'),
                        params).fetchall()
    total = sum(r['qtd'] for r in grupos)
    cruzado = db.execute('SELECT UPPER(TRIM(exame)) AS exame, UPPER(TRIM(convenio)) AS convenio, COUNT(*) AS qtd '
                         'FROM atendimentos WHERE %s GROUP BY 1, 2 ORDER BY 1, 3 DESC' % ' AND '.join(where),
                         params).fetchall()
    caixa = db.execute('SELECT status, COUNT(*) AS qtd, COALESCE(SUM(valor),0) AS total FROM caixa '
                       'WHERE data BETWEEN ? AND ? GROUP BY status', (de, ate)).fetchall()
    guias = db.execute('SELECT UPPER(TRIM(convenio)) AS convenio, COUNT(*) AS qtd FROM guias '
                       'WHERE data BETWEEN ? AND ? GROUP BY 1 ORDER BY 2 DESC', (de, ate)).fetchall()
    exames = [r[0] for r in db.execute("SELECT DISTINCT UPPER(TRIM(exame)) FROM atendimentos WHERE COALESCE(exame,'')<>'' ORDER BY 1")]
    convenios = [r[0] for r in db.execute("SELECT DISTINCT UPPER(TRIM(convenio)) FROM atendimentos WHERE COALESCE(convenio,'')<>'' ORDER BY 1")]
    return render_template('relatorios.html', de=de, ate=ate, agrupar=agrupar, rotulo=rotulo, grupos=grupos,
                           total=total, cruzado=cruzado, caixa=caixa, guias=guias, agrupamentos=AGRUPAMENTOS,
                           exame=exame, convenio=convenio, exames=exames, convenios=convenios,
                           imprimir=request.args.get('imprimir'))
