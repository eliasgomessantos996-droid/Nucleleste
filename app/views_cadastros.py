"""Cadastros: clientes, convênios, médicos e exames."""
import io
import json
import re
from datetime import date

from flask import Blueprint, abort, flash, g, redirect, render_template, request, send_file, url_for

from . import admin_obrigatorio, clientes_docs, fichas, login_obrigatorio, util
from .db import agora, config_get, get_db

bp = Blueprint('cad', __name__)

POR_PAGINA = 50

CAMPOS_CLIENTE = ['nome', 'cpf', 'cep', 'rua', 'numero', 'complemento', 'bairro', 'cidade', 'uf',
                  'contato', 'convenio', 'nome_mae', 'data_nasc', 'sexo', 'cartao_convenio', 'profissao']


# ---------------------------------------------------------------- clientes
@bp.route('/clientes')
@login_obrigatorio
def clientes():
    q = (request.args.get('q') or '').strip()
    pagina = max(1, request.args.get('p', type=int) or 1)
    db = get_db()
    where, params = '1=1', []
    if q:
        dig = util.so_digitos(q)
        if dig and not any(ch.isalpha() for ch in q):
            where = "(id=? OR REPLACE(REPLACE(cpf,'.',''),'-','') LIKE ?)"
            params = [int(dig), dig + '%']
        else:
            termos = q.upper().split()
            where = ' AND '.join(["(UPPER(nome) LIKE ? OR UPPER(COALESCE(nome_mae,'')) LIKE ?)"] * len(termos))
            for t in termos:
                params += ['%' + t + '%', '%' + t + '%']
    total = db.execute('SELECT COUNT(*) FROM clientes WHERE ' + where, params).fetchone()[0]
    rows = db.execute('SELECT * FROM clientes WHERE %s ORDER BY nome LIMIT ? OFFSET ?' % where,
                      params + [POR_PAGINA, (pagina - 1) * POR_PAGINA]).fetchall()
    paginas = max(1, (total + POR_PAGINA - 1) // POR_PAGINA)
    return render_template('clientes.html', rows=rows, q=q, total=total, pagina=pagina, paginas=paginas)


def _convenios():
    return get_db().execute('SELECT * FROM convenios WHERE ativo=1 ORDER BY nome').fetchall()


def _ler_form_cliente():
    f = {k: (request.form.get(k) or '').strip() for k in CAMPOS_CLIENTE}
    for k in ('nome', 'rua', 'complemento', 'bairro', 'cidade', 'uf', 'nome_mae', 'profissao', 'convenio'):
        f[k] = util.maiusculas(f[k])
    f['cpf'] = util.cpf_formatado(f['cpf'])
    f['contato'] = util.telefone_padrao(f['contato'])
    f['sexo'] = (request.form.get('sexo') or '').strip().upper()[:1]
    f['data_nasc'] = util.data_iso(f['data_nasc']) if f['data_nasc'] else None
    return f


def _validar_cliente(f, atual=None):
    erros = []
    if not f['nome']:
        erros.append('Informe o nome do cliente.')
    if not f['data_nasc'] or not util.para_data(f['data_nasc']):
        erros.append('Informe uma data de nascimento válida.')
    if f['sexo'] not in ('M', 'F'):
        erros.append('Informe o sexo do cliente (feminino ou masculino).')
    if not f['convenio']:   # critério para o lançamento na Medcloud (e para guias/caixa): sem convênio não há cadastro
        erros.append('Informe o convênio do cliente.')
    if f['contato'] and not util.telefone_valido(f['contato']):
        erros.append('Telefone inválido: informe o DDD e o número, no formato (XX)9XXXX-XXXX.')
    if not f['cpf']:
        erros.append('Informe o CPF.')
    elif not util.cpf_valido(f['cpf']) and not (atual and atual['cpf'] == f['cpf']):
        erros.append('CPF inválido! Verifique o número informado.')
    else:
        dup = get_db().execute('SELECT id, nome FROM clientes WHERE cpf=? AND id<>?',
                               (f['cpf'], atual['id'] if atual else 0)).fetchone()
        if dup:
            erros.append('CPF já cadastrado para o cliente %s (código %d).' % (dup['nome'], dup['id']))
    return erros


def _convenio_id(nome):
    if not nome:
        return None
    r = get_db().execute('SELECT id FROM convenios WHERE nome=?', (nome,)).fetchone()
    return r['id'] if r else None


@bp.route('/clientes/novo', methods=['GET', 'POST'])
@login_obrigatorio
def cliente_novo():
    f = {k: '' for k in CAMPOS_CLIENTE}
    for k in ('nome', 'contato', 'convenio'):   # vindo da agenda: já traz os dados da linha
        f[k] = (request.args.get(k) or '').strip()[:120]
    f['nome'] = util.maiusculas(f['nome'])
    # idade vinda da agenda (só dígitos, até 3): aparece no cadastro para conferir com a data de nascimento
    idade_agenda = ''.join(c for c in (request.args.get('idade') or '') if c.isdigit())[:3]
    if request.method == 'POST':
        f = _ler_form_cliente()
        erros = _validar_cliente(f)
        if erros:
            for e in erros:
                flash(e, 'erro')
        else:
            db = get_db()
            cur = db.execute(
                'INSERT INTO clientes (%s, convenio_id, criado_em, atualizado_em, criado_por, atualizado_por) VALUES (%s,?,?,?,?,?)'
                % (', '.join(CAMPOS_CLIENTE), ','.join('?' * len(CAMPOS_CLIENTE))),
                [f[k] for k in CAMPOS_CLIENTE] + [_convenio_id(f['convenio']), agora(), agora(), g.usuario['usuario'], g.usuario['usuario']])
            db.commit()
            flash('Cliente cadastrado com sucesso! Código %d.' % cur.lastrowid, 'ok')
            if request.form.get('depois') == 'atender':
                return redirect(url_for('atend.novo', cliente=cur.lastrowid))
            return redirect(url_for('cad.cliente_editar', cid=cur.lastrowid))
    return render_template('cliente_form.html', f=f, cliente=None, convenios=_convenios(), atendimentos=[], idade_agenda=idade_agenda)


@bp.route('/clientes/<int:cid>', methods=['GET', 'POST'])
@login_obrigatorio
def cliente_editar(cid):
    db = get_db()
    atual = db.execute('SELECT * FROM clientes WHERE id=?', (cid,)).fetchone()
    if not atual:
        abort(404)
    f = dict(atual)
    if request.method == 'POST':
        f = _ler_form_cliente()
        erros = _validar_cliente(f, atual)
        if erros:
            for e in erros:
                flash(e, 'erro')
            f['id'] = cid
        else:
            db.execute('UPDATE clientes SET %s, convenio_id=?, atualizado_em=?, atualizado_por=? WHERE id=?'
                       % ', '.join(k + '=?' for k in CAMPOS_CLIENTE),
                       [f[k] for k in CAMPOS_CLIENTE] + [_convenio_id(f['convenio']), agora(), g.usuario['usuario'], cid])
            db.commit()
            flash('Registro alterado com sucesso!', 'ok')
            return redirect(url_for('cad.cliente_editar', cid=cid))
    atendimentos = db.execute(
        "SELECT * FROM atendimentos WHERE cliente_id=? OR (COALESCE(cpf,'')<>'' AND cpf=?) ORDER BY data DESC, id DESC",
        (cid, atual['cpf'] or '-')).fetchall()
    doses = db.execute('SELECT * FROM doses WHERE cliente_id=? ORDER BY data_dose DESC', (cid,)).fetchall()
    return render_template('cliente_form.html', f=f, cliente=atual, convenios=_convenios(),
                           atendimentos=atendimentos, doses=doses)


def _historico_cliente(db, cliente, de=None, ate=None):
    """Atendimentos do cliente: os ligados ao código e os lançados sem código (cliente_id NULL) com o mesmo CPF.
    de/ate (AAAA-MM-DD) são opcionais. Ordem: data e código decrescentes."""
    cond, params = ['cliente_id=?'], [cliente['id']]
    cpf = (cliente['cpf'] or '').strip()
    if cpf:
        cond.append('(cliente_id IS NULL AND cpf=?)')
        params.append(cpf)
    where = '(' + ' OR '.join(cond) + ')'
    if de:
        where += ' AND data>=?'
        params.append(de)
    if ate:
        where += ' AND data<=?'
        params.append(ate)
    return db.execute('SELECT cliente_id, cliente_nome, cpf, medico, data, exame, convenio FROM atendimentos WHERE %s '
                      'ORDER BY data DESC, id DESC' % where, params).fetchall()


def _periodo_historico():
    de = util.para_data(request.args.get('de'))
    ate = util.para_data(request.args.get('ate'))
    return (de.isoformat() if de else None), (ate.isoformat() if ate else None)


@bp.route('/clientes/<int:cid>/historico')
@login_obrigatorio
def cliente_historico(cid):
    db = get_db()
    cliente = db.execute('SELECT * FROM clientes WHERE id=?', (cid,)).fetchone()
    if not cliente:
        abort(404)
    de, ate = _periodo_historico()
    linhas = _historico_cliente(db, cliente, de, ate)
    return render_template('cliente_historico.html', cliente=cliente, linhas=linhas, de=de, ate=ate)


@bp.route('/clientes/<int:cid>/historico.pdf')
@login_obrigatorio
def cliente_historico_pdf(cid):
    db = get_db()
    cliente = db.execute('SELECT * FROM clientes WHERE id=?', (cid,)).fetchone()
    if not cliente:
        abort(404)
    de, ate = _periodo_historico()
    linhas = _historico_cliente(db, cliente, de, ate)
    pdf = clientes_docs.historico_pdf(cliente, linhas, de, ate, config_get('clinica_nome', ''))
    return send_file(io.BytesIO(pdf), mimetype='application/pdf', as_attachment=True,
                     download_name='historico-cliente-%d.pdf' % cid)


@bp.route('/clientes/<int:cid>/excluir', methods=['POST'])
@login_obrigatorio
def cliente_excluir(cid):
    db = get_db()
    n = db.execute('SELECT COUNT(*) FROM atendimentos WHERE cliente_id=?', (cid,)).fetchone()[0]
    n += db.execute('SELECT COUNT(*) FROM doses WHERE cliente_id=?', (cid,)).fetchone()[0]
    if n:
        flash('Este cliente possui %d atendimento(s)/dose(s) no histórico e não pode ser excluído.' % n, 'erro')
        return redirect(url_for('cad.cliente_editar', cid=cid))
    db.execute('DELETE FROM clientes WHERE id=?', (cid,))
    db.commit()
    flash('Registro excluído com sucesso!', 'ok')
    return redirect(url_for('cad.clientes'))


# ---------------------------------------------------------------- convênios
@bp.route('/convenios', methods=['GET', 'POST'])
@login_obrigatorio
def convenios():
    db = get_db()
    if request.method == 'POST':
        cid = request.form.get('id', type=int)
        nome = util.maiusculas(request.form.get('nome'))
        gera_caixa = 1 if request.form.get('gera_caixa') else 0
        ativo = 1 if request.form.get('ativo', '1') else 0
        if not nome:
            flash('Informe o nome do convênio.', 'erro')
        else:
            existe = db.execute('SELECT id FROM convenios WHERE nome=? AND id<>?', (nome, cid or 0)).fetchone()
            if existe:
                flash('Já existe um convênio com esse nome.', 'erro')
            elif cid:
                antigo = db.execute('SELECT nome FROM convenios WHERE id=?', (cid,)).fetchone()
                db.execute('UPDATE convenios SET nome=?, gera_caixa=?, ativo=? WHERE id=?', (nome, gera_caixa, ativo, cid))
                if antigo and antigo['nome'] != nome:
                    db.execute('UPDATE clientes SET convenio=? WHERE convenio_id=?', (nome, cid))
                _salvar_valores_exames(db, cid)
                db.commit()
                flash('Registro alterado com sucesso!', 'ok')
            else:
                novo = db.execute('INSERT INTO convenios (nome, gera_caixa, usuario) VALUES (?,?,?)',
                                  (nome, gera_caixa, g.usuario['usuario'])).lastrowid
                _salvar_valores_exames(db, novo)
                db.commit()
                flash('Convênio cadastrado com sucesso!', 'ok')
        return redirect(url_for('cad.convenios'))
    rows = db.execute('SELECT c.*, (SELECT COUNT(*) FROM clientes WHERE convenio_id=c.id) AS n_clientes '
                      'FROM convenios c ORDER BY c.nome').fetchall()
    exames_lista, valores = _valores_por_convenio(db)
    return render_template('convenios.html', rows=rows, exames=exames_lista, valores=valores)


# Colunas antigas do cadastro de convênios (mantidas em dia só por compatibilidade): exame -> coluna
_COLUNAS_ANTIGAS = {'MIBI': 'valor_mibi', 'ÓSSEA': 'valor_ossea', 'TGI': 'valor_tgi', 'PARATGI': 'valor_paratgi', 'GALIO': 'valor_galio'}


def _exames_com_valor(db):
    """Exames que aparecem na tela de valores: todos os ativos (um exame novo já nasce disponível para todo convênio)
    mais os inativos que ainda guardam algum valor."""
    return db.execute('SELECT id, nome FROM exames WHERE ativo=1 OR id IN (SELECT exame_id FROM convenio_valores) '
                      'ORDER BY ordem, nome').fetchall()


def _valores_por_convenio(db):
    exames_lista = _exames_com_valor(db)
    valores = {}
    for r in db.execute('SELECT convenio_id, exame_id, valor FROM convenio_valores'):
        valores.setdefault(r['convenio_id'], {})[str(r['exame_id'])] = util.moeda(r['valor'])
    return exames_lista, valores


def _salvar_valores_exames(db, cid):
    """Grava os campos valor_<id do exame> do formulário. Campo vazio apaga o valor; exame que não veio no formulário não muda."""
    for ex in _exames_com_valor(db):
        campo = 'valor_%d' % ex['id']
        if campo not in request.form:
            continue
        bruto = (request.form.get(campo) or '').replace('R$', '').strip()
        if re.fullmatch(r'\d{1,3}(\.\d{3})+', bruto):   # "1.250" é milhar no padrão brasileiro
            bruto = bruto.replace('.', '')
        valor = util.para_valor(bruto)
        if valor is None or valor < 0:
            db.execute('DELETE FROM convenio_valores WHERE convenio_id=? AND exame_id=?', (cid, ex['id']))
        else:
            db.execute('INSERT INTO convenio_valores (convenio_id, exame_id, valor) VALUES (?,?,?) '
                       'ON CONFLICT(convenio_id, exame_id) DO UPDATE SET valor=excluded.valor', (cid, ex['id'], valor))
        coluna = _COLUNAS_ANTIGAS.get((ex['nome'] or '').upper())
        if coluna:
            db.execute('UPDATE convenios SET %s=? WHERE id=?' % coluna, (valor if valor is not None and valor >= 0 else None, cid))


@bp.route('/convenios/<int:cid>/excluir', methods=['POST'])
@login_obrigatorio
def convenio_excluir(cid):
    db = get_db()
    n = db.execute('SELECT COUNT(*) FROM clientes WHERE convenio_id=?', (cid,)).fetchone()[0]
    if n:
        flash('Há %d cliente(s) com este convênio. Desative-o em vez de excluir.' % n, 'erro')
    else:
        db.execute('DELETE FROM convenio_valores WHERE convenio_id=?', (cid,))
        db.execute('DELETE FROM convenios WHERE id=?', (cid,))
        db.commit()
        flash('Registro excluído com sucesso!', 'ok')
    return redirect(url_for('cad.convenios'))


# ---------------------------------------------------------------- médicos
@bp.route('/medicos', methods=['GET', 'POST'])
@login_obrigatorio
def medicos():
    db = get_db()
    if request.method == 'POST':
        mid = request.form.get('id', type=int)
        nome = util.maiusculas(request.form.get('nome'))
        crm = (request.form.get('crm') or '').strip().upper()
        if not nome:
            flash('Informe o nome do médico.', 'erro')
        elif mid:
            db.execute('UPDATE medicos SET nome=?, crm=? WHERE id=?', (nome, crm, mid))
            db.commit()
            flash('Registro alterado com sucesso!', 'ok')
        else:
            if db.execute('SELECT 1 FROM medicos WHERE TRIM(UPPER(nome))=?', (nome,)).fetchone():
                flash('Médico já cadastrado.', 'erro')
            else:
                db.execute('INSERT INTO medicos (nome, crm, usuario) VALUES (?,?,?)', (nome, crm, g.usuario['usuario']))
                db.commit()
                flash('Médico cadastrado com sucesso!', 'ok')
        return redirect(url_for('cad.medicos', q=request.args.get('q', '')))
    q = (request.args.get('q') or '').strip().upper()
    rows = db.execute("SELECT m.*, (SELECT COUNT(*) FROM medicos m2 WHERE TRIM(UPPER(m2.nome))=TRIM(UPPER(m.nome))) AS dup "
                      "FROM medicos m WHERE UPPER(nome) LIKE ? ORDER BY TRIM(nome)", ('%' + q + '%',)).fetchall()
    return render_template('medicos.html', rows=rows, q=q)


@bp.route('/medicos/<int:mid>/excluir', methods=['POST'])
@login_obrigatorio
def medico_excluir(mid):
    db = get_db()
    db.execute('DELETE FROM medicos WHERE id=?', (mid,))
    db.commit()
    flash('Registro excluído com sucesso!', 'ok')
    return redirect(url_for('cad.medicos'))


# ---------------------------------------------------------------- exames
@bp.route('/exames')
@login_obrigatorio
def exames():
    rows = get_db().execute('SELECT * FROM exames ORDER BY ativo DESC, ordem, nome').fetchall()
    lista = []
    for r in rows:
        docs = fichas.documentos_do_exame(r)
        lista.append({'row': r, 'docs': ', '.join('%s%s' % (fichas.titulo(s), ' (x%d)' % c if c > 1 else '')
                                                    for s, c in docs)})
    return render_template('exames.html', lista=lista)


@bp.route('/exames/novo', methods=['GET', 'POST'])
@bp.route('/exames/<int:eid>', methods=['GET', 'POST'])
@login_obrigatorio
def exame_editar(eid=None):
    db = get_db()
    ex = db.execute('SELECT * FROM exames WHERE id=?', (eid,)).fetchone() if eid else None
    if eid and not ex:
        abort(404)
    if request.method == 'POST':
        nome = util.maiusculas(request.form.get('nome'))
        docs = []
        for slug in fichas.slugs_atendimento():
            if request.form.get('doc_' + slug):
                docs.append([slug, max(1, request.form.get('copias_' + slug, type=int) or 1)])
        ordem_docs = request.form.get('ordem_docs', '')
        if ordem_docs:
            pos = {s: i for i, s in enumerate(ordem_docs.split(','))}
            docs.sort(key=lambda d: pos.get(d[0], 99))
        dados = (nome, (request.form.get('titulo_ficha') or nome).strip().upper(), json.dumps(docs),
                 request.form.get('questionario') or None, 1 if request.form.get('pede_medicamentos') else 0,
                 1 if request.form.get('ativo') else 0, request.form.get('ordem', type=int) or 100)
        if not nome:
            flash('Informe o nome do exame.', 'erro')
        elif db.execute('SELECT 1 FROM exames WHERE nome=? AND id<>?', (nome, eid or 0)).fetchone():
            flash('Já existe um exame com esse nome.', 'erro')
        else:
            if ex:
                db.execute('UPDATE exames SET nome=?, titulo_ficha=?, documentos=?, questionario=?, pede_medicamentos=?, '
                           'ativo=?, ordem=? WHERE id=?', dados + (eid,))
            else:
                db.execute('INSERT INTO exames (nome, titulo_ficha, documentos, questionario, pede_medicamentos, ativo, '
                           'ordem) VALUES (?,?,?,?,?,?,?)', dados)
            db.commit()
            flash('Exame salvo com sucesso!', 'ok')
            return redirect(url_for('cad.exames'))
    docs = fichas.documentos_do_exame(ex) if ex else []
    marcados = {s: c for s, c in docs}
    ordem = [s for s, _ in docs] + [s for s in fichas.slugs_atendimento() if s not in marcados]
    opcoes = [{'slug': s, 'titulo': fichas.titulo(s), 'marcado': s in marcados, 'copias': marcados.get(s, 1)}
              for s in ordem]
    return render_template('exame_form.html', ex=ex, opcoes=opcoes)


# ---------------------------------------------------------------- fichas personalizadas
EXEMPLO_FICHA = """# TERMO DE CIÊNCIA

Eu, **{nome}**, CPF {cpf}, declaro que fui orientado(a) sobre o exame **{exame}**, solicitado por Dr(a). {medico},
e que estou ciente dos procedimentos e cuidados necessários.

[ ] Fui informado(a) sobre o preparo do exame.
[ ] Não estou grávida nem amamentando.

---
{clinica_cidade}, {hoje}


{linha}
{nome}
"""


def _dados_exemplo():
    cliente = {'id': 1234, 'nome': 'MARIA DA SILVA SANTOS', 'cpf': '123.456.789-09', 'data_nasc': '1980-05-17',
               'profissao': 'PROFESSORA', 'nome_mae': 'ANA DA SILVA', 'rua': 'RUA DAS FLORES', 'numero': '123',
               'bairro': 'CENTRO', 'cidade': 'GOVERNADOR VALADARES', 'cep': '35010-000', 'contato': '(33) 99999-9999',
               'convenio': 'PARTICULAR'}
    f = fichas.dados_cliente(cliente)
    f.update({'data': util.data_br(date.today().isoformat()), 'exame': 'MIBI', 'titulo': 'MIBI', 'medico': 'JOÃO PEREIRA',
              'exame_anterior': '12/03/2024', 'medicamentos': 'NENHUM'})
    return f


@bp.route('/exames/fichas')
@login_obrigatorio
def exame_fichas():
    rows = get_db().execute('SELECT * FROM fichas_extras ORDER BY ativa DESC, titulo COLLATE NOCASE').fetchall()
    return render_template('fichas_extras.html', lista=rows)


@bp.route('/exames/fichas/nova', methods=['GET', 'POST'])
@bp.route('/exames/fichas/<int:xid>', methods=['GET', 'POST'])
@login_obrigatorio
def exame_ficha_editar(xid=None):
    db = get_db()
    x = db.execute('SELECT * FROM fichas_extras WHERE id=?', (xid,)).fetchone() if xid else None
    if xid and not x:
        abort(404)
    if request.method == 'POST':
        titulo = (request.form.get('titulo') or '').strip()
        conteudo = (request.form.get('conteudo') or '').replace('\r\n', '\n')
        cab = 1 if request.form.get('cabecalho') else 0
        ativa = 1 if request.form.get('ativa') else 0
        if not titulo:
            flash('Informe o título da ficha.', 'erro')
        elif len(conteudo) > 20000:
            flash('O texto da ficha é grande demais (máximo de 20.000 caracteres).', 'erro')
        else:
            quem, quando = g.usuario['usuario'], agora()
            if x:
                db.execute('UPDATE fichas_extras SET titulo=?, conteudo=?, cabecalho=?, ativa=?, atualizado_por=?, atualizado_em=? WHERE id=?',
                           (titulo, conteudo, cab, ativa, quem, quando, xid))
            else:
                db.execute('INSERT INTO fichas_extras (titulo, conteudo, cabecalho, ativa, criado_por, criado_em) VALUES (?,?,?,?,?,?)',
                           (titulo, conteudo, cab, ativa, quem, quando))
            db.commit()
            flash('Ficha salva! Ela já aparece nas opções de impressão do atendimento e em “Exames e fichas”.', 'ok')
            return redirect(url_for('cad.exame_fichas'))
        x = {'titulo': titulo, 'conteudo': conteudo, 'cabecalho': cab, 'ativa': ativa, 'id': xid}
    elif not x:
        x = {'titulo': '', 'conteudo': EXEMPLO_FICHA, 'cabecalho': 1, 'ativa': 1, 'id': None}
    return render_template('ficha_extra_form.html', x=x, campos=fichas.CAMPOS_FICHA,
                           previa=fichas.renderizar_texto(x['conteudo'], _dados_exemplo()))


@bp.route('/exames/fichas/previa', methods=['POST'])
@login_obrigatorio
def exame_ficha_previa():
    html = fichas.renderizar_texto(request.form.get('conteudo') or '', _dados_exemplo())
    return {'html': str(html)}


@bp.route('/exames/fichas/<int:xid>/excluir', methods=['POST'])
@login_obrigatorio
def exame_ficha_excluir(xid):
    db = get_db()
    db.execute('DELETE FROM fichas_extras WHERE id=?', (xid,))
    db.commit()
    flash('Ficha excluída.', 'ok')
    return redirect(url_for('cad.exame_fichas'))
