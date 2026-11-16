"""Atendimentos (lançamento de exames + fichas), protocolo de guias e caixa."""
import json
import os
from datetime import date

from flask import Blueprint, abort, current_app, flash, g, jsonify, redirect, render_template, request, send_file, url_for

from . import admin_obrigatorio, fichas, laudos_word, login_obrigatorio, medcloud, medcloud_envios, prazo_laudo, prontuario, util
from .db import agora, config_get, get_db

bp = Blueprint('atend', __name__)

OPCAO_SEM_ANTERIOR = 'NÃO INFORMADO'
DIAS_SEMANA = ('segunda-feira', 'terça-feira', 'quarta-feira', 'quinta-feira', 'sexta-feira', 'sábado', 'domingo')


def exame_por_nome(nome):
    return get_db().execute('SELECT * FROM exames WHERE nome=?', ((nome or '').strip(),)).fetchone()


def convenio_gera_caixa(nome):
    r = get_db().execute('SELECT gera_caixa FROM convenios WHERE nome=?', ((nome or '').strip(),)).fetchone()
    return bool(r and r['gera_caixa'])


# ---------------------------------------------------------------- lançar atendimento
@bp.route('/atendimentos/novo', methods=['GET', 'POST'])
@login_obrigatorio
def novo():
    db = get_db()
    exames = db.execute('SELECT * FROM exames WHERE ativo=1 ORDER BY ordem, nome').fetchall()
    convenios = db.execute('SELECT * FROM convenios WHERE ativo=1 ORDER BY nome').fetchall()
    f = {'cliente_id': request.args.get('cliente', ''), 'data': date.today().isoformat(), 'exame': '',
         'medico': '', 'convenio': '', 'medicamentos': '', 'exame_anterior': '', 'interno': '', 'interno_local': ''}
    respostas_iniciais = {'manual': 0, 'itens': []}
    if request.method == 'POST':
        f = {k: (request.form.get(k) or '').strip() for k in f}
        f['exame'] = util.maiusculas(f['exame'])
        f['medico'] = util.maiusculas(f['medico'])
        f['interno'] = '1' if f['interno'] == '1' else ''   # paciente interno do hospital (caixa marcada)
        interno = f['interno'] == '1'
        cliente = db.execute('SELECT * FROM clientes WHERE id=?', (f['cliente_id'] or 0,)).fetchone()
        exame = exame_por_nome(f['exame'])
        _, perguntas = fichas.questionario_do_exame(exame)
        manual = request.form.get('manual') == '1'
        respostas_iniciais = _respostas_do_form(perguntas, manual)
        tem_anteriores = cliente and db.execute(
            "SELECT 1 FROM atendimentos WHERE cliente_id=? OR (COALESCE(cpf,'')<>'' AND cpf=?) LIMIT 1",
            (cliente['id'], cliente['cpf'] or '-')).fetchone()
        erros = []
        if not cliente:
            erros.append('Selecione o cliente.')
        if not f['exame']:
            erros.append('Informe o exame.')
        if not f['medico']:
            erros.append('Informe o médico solicitante.')
        # o convênio é obrigatório (critério para o lançamento na Medcloud): o escolhido aqui ou, se deixar em branco, o do cadastro
        if cliente and not (util.maiusculas(f['convenio']) or (cliente['convenio'] or '').strip()):
            erros.append('Informe o convênio do atendimento (o cadastro deste cliente está sem convênio).')
        if not util.para_data(f['data']):
            erros.append('Informe a data do atendimento.')
        if exame is not None and exame['pede_medicamentos'] and not f['medicamentos']:
            erros.append('Preencha os medicamentos em uso (ou marque "Não se aplica").')
        if tem_anteriores and not f['exame_anterior']:
            erros.append('O cliente possui exames anteriores: selecione o último exame.')
        if interno and not f['interno_local']:
            erros.append('Informe de onde veio o paciente interno (hospital / setor / leito).')
        if perguntas and not manual and any(it['r'] not in ('SIM', 'NÃO') for it in respostas_iniciais['itens']):
            erros.append('Responda todas as perguntas do questionário (ou clique em "Preencher manual").')
        if erros:
            for e in erros:
                flash(e, 'erro')
        else:
            convenio = util.maiusculas(f['convenio']) or (cliente['convenio'] or '')
            respostas = _gravar_respostas(respostas_iniciais, perguntas)
            if f['exame_anterior'] == OPCAO_SEM_ANTERIOR:
                f['exame_anterior'] = ''
            data = util.data_iso(f['data'])
            usuario = g.usuario['usuario']
            previsao = prazo_laudo.previsao(date.fromisoformat(data)).isoformat()
            cur = db.execute(
                'INSERT INTO atendimentos (cliente_id, cliente_nome, cpf, medico, data, exame, convenio, medicamentos, '
                'exame_anterior, respostas, usuario, criado_em, previsao_laudo, interno, interno_local) '
                'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (cliente['id'], cliente['nome'], cliente['cpf'], f['medico'], data, f['exame'], convenio,
                 f['medicamentos'], f['exame_anterior'], json.dumps(respostas, ensure_ascii=False) if respostas else None,
                 usuario, agora(), previsao, 1 if interno else 0, (f['interno_local'] or None) if interno else None))
            aid = cur.lastrowid
            # todo paciente atendido tem prontuário; o interno do hospital ganha o SBAR pendente para a equipe preencher
            pront = prontuario.garantir(db, cliente['id'], usuario)
            aviso_prontuario = ' Prontuário nº %s.' % pront['numero']
            if interno:
                prontuario.criar_doc(db, cliente['id'], 'sbar', usuario, atendimento_id=aid)
                aviso_prontuario += ' SBAR pendente no prontuário.'
            # Médico novo entra no cadastro automaticamente
            if not db.execute('SELECT 1 FROM medicos WHERE TRIM(UPPER(nome))=?', (f['medico'],)).fetchone():
                db.execute('INSERT INTO medicos (nome) VALUES (?)', (f['medico'],))
            # Particular/SMS/Mais Med -> caixa; demais convênios -> protocolo de guias
            if convenio_gera_caixa(convenio):
                db.execute('INSERT INTO caixa (atendimento_id, data, cliente, cpf, procedimento, convenio, status, usuario) '
                           "VALUES (?,?,?,?,?,?,'ABERTO',?)",
                           (aid, data, cliente['nome'], cliente['cpf'], f['exame'], convenio, usuario))
                destino = 'caixa'
            else:
                db.execute('INSERT INTO guias (atendimento_id, paciente, convenio, data, exame, usuario) VALUES (?,?,?,?,?,?)',
                           (aid, cliente['nome'], convenio, data, f['exame'], usuario))
                destino = 'protocolo de guias'
            mc_pendente = False
            try:   # convênio marcado para a Medcloud: o robô cria o acesso (falha aqui não impede o lançamento)
                mc_pendente = medcloud.enfileirar(db, aid) == 'pendente'
            except Exception:
                flash('O pedido de acesso à Medcloud não foi registrado. Abra a impressão para tentar de novo.', 'aviso')
            db.commit()
            flash('Atendimento lançado com sucesso! Registro enviado para o %s. Previsão de entrega do laudo: %s.%s'
                  % (destino, util.data_br(previsao), aviso_prontuario), 'ok')
            if mc_pendente:
                medcloud.acordar()   # o paciente está na clínica: o robô começa já, e a tela de carregamento espera o protocolo
                return redirect(url_for('atend.medcloud_aguarde', aid=aid, novo=1))
            return redirect(url_for('atend.imprimir', aid=aid, novo=1))
    if request.method == 'GET':
        medcloud.aquecer_se_ativo(db)   # abre o navegador do robô e faz o login enquanto a recepção preenche o formulário
    medicos = [r['nome'] for r in db.execute(
        "SELECT DISTINCT TRIM(nome) AS nome FROM medicos WHERE TRIM(COALESCE(nome,''))<>'' ORDER BY 1").fetchall()]
    return render_template('atendimento_form.html', f=f, exames=exames, convenios=convenios, medicos=medicos,
                           sem_anterior=OPCAO_SEM_ANTERIOR, respostas_iniciais=respostas_iniciais,
                           exames_json=json.dumps({e['nome']: {'questionario': fichas.questionario_do_exame(e)[1],
                                                               'medicamentos': e['pede_medicamentos']} for e in exames},
                                                  ensure_ascii=False))


@bp.route('/atendimentos/previsao')
@login_obrigatorio
def previsao():
    """Previsão de entrega do laudo para uma data de atendimento (mostrada na tela de lançamento)."""
    dia = util.para_data(request.args.get('data'))
    if not dia:
        return jsonify({'texto': ''})
    prev = prazo_laudo.previsao(dia)
    return jsonify({'texto': 'Previsão de entrega do laudo: %s (%s; prazo de %s)'
                    % (util.data_br(prev.isoformat()), DIAS_SEMANA[prev.weekday()], prazo_laudo.descricao())})


def _respostas_do_form(perguntas, manual):
    """Lê do formulário as respostas (r1, r2...) e as justificativas (o1, o2...) de cada pergunta."""
    itens = []
    for i, (_, rotulo) in enumerate(perguntas, 1):
        if manual:
            itens.append({'r': '', 'o': ''})
            continue
        r = request.form.get('r%d' % i) or ''
        itens.append({'r': r if r in ('SIM', 'NÃO') else '', 'o': (request.form.get('o%d' % i) or '').strip() if rotulo else ''})
    return {'manual': 1 if manual else 0, 'itens': itens}


def _gravar_respostas(lidas, perguntas):
    """Monta o JSON gravado no atendimento. Justificativa só é guardada quando a resposta é SIM."""
    if not perguntas:
        return {}
    if lidas['manual']:   # preenchimento manual: nenhuma resposta é guardada, mesmo que algo tenha sido marcado antes
        return {'manual': 1}
    saida = {}
    for i, it in enumerate(lidas['itens'], 1):
        if it['r']:
            saida['r%d' % i] = it['r']
        if it['r'] == 'SIM' and it['o']:
            saida['o%d' % i] = it['o']
    if lidas['manual']:
        saida['manual'] = 1
    return saida


# ---------------------------------------------------------------- lista / detalhe
def _filtros_atendimentos():
    a = request.args
    hoje = date.today()
    filtros = {
        'de': a.get('de') or hoje.replace(day=1).isoformat(),
        'ate': a.get('ate') or hoje.isoformat(),
        'exame': (a.get('exame') or '').strip(),
        'convenio': (a.get('convenio') or '').strip(),
        'medico': (a.get('medico') or '').strip(),
        'cliente': (a.get('cliente') or '').strip(),
        'usuario': (a.get('usuario') or '').strip(),
    }
    where, params = ['data BETWEEN ? AND ?'], [filtros['de'], filtros['ate']]
    for campo in ('exame', 'convenio', 'usuario'):
        if filtros[campo]:
            where.append('TRIM(UPPER(%s))=?' % campo)
            params.append(filtros[campo].upper())
    if filtros['medico']:
        where.append('UPPER(medico) LIKE ?')
        params.append('%' + filtros['medico'].upper() + '%')
    if filtros['cliente']:
        where.append('(UPPER(cliente_nome) LIKE ? OR cpf LIKE ?)')
        params += ['%' + filtros['cliente'].upper() + '%', filtros['cliente'] + '%']
    return filtros, ' AND '.join(where), params


@bp.route('/atendimentos')
@login_obrigatorio
def lista():
    db = get_db()
    filtros, where, params = _filtros_atendimentos()
    rows = db.execute('SELECT * FROM atendimentos WHERE %s ORDER BY data DESC, id DESC LIMIT 2000' % where,
                      params).fetchall()
    # DISTINCT na coluna crua usa o índice; o TRIM e a ordem são feitos aqui (são poucos valores)
    exames = sorted({(r[0] or '').strip() for r in db.execute('SELECT DISTINCT exame FROM atendimentos')} - {''})
    convenios = [r[0] for r in db.execute("SELECT nome FROM convenios ORDER BY nome")]
    usuarios = sorted({r[0] for r in db.execute('SELECT DISTINCT usuario FROM atendimentos') if r[0]})
    return render_template('atendimentos.html', rows=rows, f=filtros, exames=exames, convenios=convenios,
                           usuarios=usuarios, pend_mc=medcloud_envios.resumo(db, [r['id'] for r in rows]))


@bp.route('/atendimentos/laudo/<int:cid>')
@login_obrigatorio
def laudo_word(cid):
    """Abre o laudo em Word do cliente: procura, na pasta definida em "Dados da clínica", o arquivo com o nome dele.
    Um só candidato certo abre direto; vários aparecem numa lista para escolher."""
    db = get_db()
    cliente = db.execute('SELECT id, nome FROM clientes WHERE id=?', (cid,)).fetchone()
    if not cliente:
        abort(404)
    pasta = (config_get('laudos_pasta_word', '') or '').strip()
    if not pasta or not os.path.isdir(pasta):
        return render_template('laudo_word.html', cliente=cliente, pasta=pasta, candidatos=[], sem_pasta=True)
    escolhido = request.args.get('abrir')
    if escolhido:
        caminho = laudos_word.caminho_seguro(pasta, escolhido)
        if not caminho:
            abort(404)
        return send_file(caminho, as_attachment=True, download_name=os.path.basename(caminho))
    data = util.para_data(request.args.get('data'))
    candidatos = laudos_word.buscar(pasta, cliente['nome'], data)
    certos = [c for c in candidatos if c['exato']]
    unico = certos[0] if len(certos) == 1 else (candidatos[0] if len(candidatos) == 1 else None)
    if unico:
        return send_file(laudos_word.caminho_seguro(pasta, unico['rel']), as_attachment=True, download_name=unico['nome'])
    return render_template('laudo_word.html', cliente=cliente, pasta=pasta, candidatos=candidatos, sem_pasta=False,
                           data=request.args.get('data') or '')


@bp.route('/atendimentos/<int:aid>/excluir', methods=['POST'])
@admin_obrigatorio
def excluir(aid):
    db = get_db()
    db.execute('DELETE FROM guias WHERE atendimento_id=?', (aid,))
    db.execute('DELETE FROM caixa WHERE atendimento_id=?', (aid,))
    db.execute('DELETE FROM atendimentos WHERE id=?', (aid,))
    db.commit()
    flash('Atendimento excluído (com a guia/caixa vinculados).', 'ok')
    return redirect(request.form.get('voltar') or url_for('atend.lista'))


@bp.route('/atendimentos/<int:aid>/imprimir')
@login_obrigatorio
def imprimir(aid):
    db = get_db()
    at = db.execute('SELECT * FROM atendimentos WHERE id=?', (aid,)).fetchone()
    if not at:
        abort(404)
    cliente = db.execute('SELECT * FROM clientes WHERE id=?', (at['cliente_id'] or 0,)).fetchone()
    exame = exame_por_nome(at['exame'])
    padrao = fichas.documentos_do_exame(exame)
    selecionados = _docs_da_url(padrao)
    f = fichas.dados_atendimento(at, cliente, exame)
    opcoes = _opcoes_docs(fichas.slugs_atendimento(), selecionados)
    titulo = '%s - %s - %s' % (f['nome'], f['exame'], f['data'])
    extras = {s: r for s, r in fichas.extras(False).items() if any(s == d[0] for d in selecionados)}
    # previsão gravada no lançamento; atendimentos antigos (sem ela) são calculados com o prazo vigente
    prev_iso = at['previsao_laudo'] or prazo_laudo.previsao(date.fromisoformat(at['data'])).isoformat()
    # Medcloud: reimprimir NÃO cria estudo nem passa pela tela de carregamento (o estudo só nasce no lançamento do atendimento
    # novo). Aqui só entra o protocolo de acesso que o paciente já tem, quando houver.
    mc = medcloud.status_atendimento(db, aid)
    mc.update(medcloud.protocolo_do_atendimento(db, aid) or {'usuario': None})
    clinica = {k: (config_get('clinica_' + k, '') or '').strip() for k in ('nome', 'cidade', 'cnpj', 'endereco', 'telefone')}
    return render_template('impressao.html', f=f, docs=selecionados, opcoes=opcoes, titulo=titulo, extras=extras,
                           previsao=util.data_br(prev_iso), mc=mc, clinica=clinica,
                           texto_extra=fichas.renderizar_texto,
                           voltar=url_for('atend.lista'), novo=request.args.get('novo'), at=at)


@bp.route('/atendimentos/<int:aid>/medcloud/status')
@login_obrigatorio
def medcloud_status(aid):
    """Situação do acesso Medcloud (a impressão consulta até o robô terminar). Não devolve usuário nem senha."""
    s = medcloud.status_atendimento(get_db(), aid)
    return jsonify(estado=s['estado'], fase=s.get('fase'), erro=s.get('erro'), tentativas=s.get('tentativas'),
                   tem_acesso=s['tem_acesso'])


@bp.route('/atendimentos/<int:aid>/medcloud/aguarde')
@login_obrigatorio
def medcloud_aguarde(aid):
    """Tela de carregamento: espera o robô criar o acesso na Medcloud (mostrando a etapa) e só então abre as fichas."""
    db = get_db()
    if not db.execute('SELECT 1 FROM atendimentos WHERE id=?', (aid,)).fetchone():
        abort(404)
    destino = url_for('atend.imprimir', aid=aid, **request.args.to_dict(flat=False))
    if medcloud.status_atendimento(db, aid)['estado'] not in ('pendente', 'erro'):
        return redirect(destino)   # já terminou (ou nunca foi preciso): vai direto para as fichas
    medcloud.acordar()
    paciente = db.execute('SELECT cliente_nome FROM atendimentos WHERE id=?', (aid,)).fetchone()['cliente_nome']
    return render_template('medcloud_aguarde.html', aid=aid, paciente=paciente, destino=destino,
                           qs=request.query_string.decode('ascii', 'ignore'),
                           status_url=url_for('atend.medcloud_status', aid=aid), limite=medcloud.ESPERA_NA_TELA)


@bp.route('/atendimentos/<int:aid>/medcloud/sem-estudo', methods=['POST'])
@login_obrigatorio
def medcloud_sem_estudo(aid):
    """O usuário escolheu imprimir as fichas SEM o estudo: sai o protocolo de acesso (se o paciente já tem acesso) e o
    pedido do estudo é cancelado. A escolha fica registrada no atendimento."""
    db = get_db()
    if medcloud.imprimir_sem_estudo(db, aid):
        db.commit()
    qs = (request.form.get('qs') or '').strip()
    return redirect(url_for('atend.imprimir', aid=aid) + ('?' + qs if qs else ''))


@bp.route('/atendimentos/<int:aid>/medcloud/tentar', methods=['POST'])
@login_obrigatorio
def medcloud_tentar(aid):
    db = get_db()
    if medcloud.tentar_de_novo(db, aid):
        db.commit()
        return redirect(url_for('atend.medcloud_aguarde', aid=aid))   # volta para a tela de carregamento (etapas do robô)
    return redirect(url_for('atend.imprimir', aid=aid))


def _docs_da_url(padrao):
    """Lê ?d=slug:copias da URL; sem parâmetros usa o padrão do exame."""
    pedidos = request.args.getlist('d')
    if not pedidos:
        return padrao
    docs = []
    for p in pedidos:
        slug, _, cop = p.partition(':')
        if fichas.valido(slug):
            docs.append([slug, max(1, min(10, int(cop) if cop.isdigit() else 1))])
    return docs


def _opcoes_docs(slugs, selecionados):
    sel = {s: c for s, c in selecionados}
    ordem = [s for s, _ in selecionados] + [s for s in slugs if s not in sel]
    return [{'slug': s, 'titulo': fichas.titulo(s), 'marcado': s in sel, 'copias': sel.get(s, 1)} for s in ordem]


# ---------------------------------------------------------------- protocolo de guias
@bp.route('/guias')
@login_obrigatorio
def guias():
    db = get_db()
    hoje = date.today().isoformat()
    de = request.args.get('de') or hoje
    ate = request.args.get('ate') or hoje
    convenio = (request.args.get('convenio') or '').strip()
    where, params = 'data BETWEEN ? AND ?', [de, ate]
    if convenio:
        where += ' AND TRIM(convenio)=?'
        params.append(convenio)
    rows = db.execute('SELECT * FROM guias WHERE %s ORDER BY data, id' % where, params).fetchall()
    convenios = [r[0] for r in db.execute("SELECT DISTINCT TRIM(convenio) FROM guias WHERE COALESCE(convenio,'')<>'' ORDER BY 1")]
    tpl = 'guias_impressao.html' if request.args.get('imprimir') else 'guias.html'
    return render_template(tpl, rows=rows, de=de, ate=ate, convenio=convenio, convenios=convenios)


@bp.route('/guias/<int:gid>', methods=['POST'])
@login_obrigatorio
def guia_salvar(gid):
    db = get_db()
    if request.form.get('acao') == 'excluir':
        db.execute('DELETE FROM guias WHERE id=?', (gid,))
        flash('Guia removida do protocolo.', 'ok')
    else:
        db.execute('UPDATE guias SET horario=? WHERE id=?', ((request.form.get('horario') or '').strip(), gid))
        flash('Guia atualizada.', 'ok')
    db.commit()
    return redirect(request.form.get('voltar') or url_for('atend.guias'))


# ---------------------------------------------------------------- caixa
STATUS_CAIXA = ['ABERTO', 'PAGO', 'CANCELADO']
FORMAS_PAGAMENTO = ['DINHEIRO', 'PIX', 'CARTÃO DE DÉBITO', 'CARTÃO DE CRÉDITO', 'TRANSFERÊNCIA', 'CONVÊNIO/FATURA']


@bp.route('/caixa')
@login_obrigatorio
def caixa():
    db = get_db()
    hoje = date.today().isoformat()
    de = request.args.get('de') or hoje
    ate = request.args.get('ate') or hoje
    from . import movimento
    usuario = request.args.get('usuario')
    if not movimento.pode_privilegiado(g.usuario, g.modulos):
        usuario = g.usuario['usuario']   # cada pessoa só vê os atendimentos que ela mesma lançou
    elif usuario is None:
        usuario = ''
    status = request.args.get('status') or ''
    where, params = ['data BETWEEN ? AND ?'], [de, ate]
    if usuario:
        where.append('usuario=?')
        params.append(usuario)
    if status:
        where.append('status=?')
        params.append(status)
    rows = db.execute('SELECT * FROM caixa WHERE %s ORDER BY data, id' % ' AND '.join(where), params).fetchall()
    totais = {}
    for r in rows:
        t = totais.setdefault(r['status'] or 'ABERTO', [0, 0.0])
        t[0] += 1
        t[1] += r['valor'] or 0
    usuarios = [r[0] for r in db.execute("SELECT DISTINCT usuario FROM caixa WHERE COALESCE(usuario,'')<>'' ORDER BY 1")]
    if not movimento.pode_privilegiado(g.usuario, g.modulos):
        usuarios = [g.usuario['usuario']]
    tpl = 'caixa_impressao.html' if request.args.get('imprimir') else 'caixa.html'
    return render_template(tpl, rows=rows, de=de, ate=ate, usuario=usuario, status=status, totais=totais,
                           usuarios=usuarios, status_lista=STATUS_CAIXA, formas=FORMAS_PAGAMENTO)


@bp.route('/caixa/<int:cid>', methods=['POST'])
@login_obrigatorio
def caixa_salvar(cid):
    from . import movimento
    db = get_db()
    row = db.execute('SELECT * FROM caixa WHERE id=?', (cid,)).fetchone()
    if row is not None and not movimento.pode_privilegiado(g.usuario, g.modulos) and not movimento.pode_receber(row, g.usuario['usuario']):
        flash('Este atendimento foi lançado por %s. Só quem lançou pode alterar o recebimento.' % row['usuario'], 'erro')
        return redirect(request.form.get('voltar') or url_for('atend.caixa'))
    if row is not None and not movimento.pode_editar(db, g.usuario['usuario'], movimento.pode_privilegiado(g.usuario, g.modulos), row):
        flash('Este caixa já foi fechado. Só a administração ou a gerência pode corrigi-lo.', 'erro')
        return redirect(request.form.get('voltar') or url_for('atend.caixa'))
    status = request.form.get('status')
    if status not in STATUS_CAIXA:
        status = 'ABERTO'
    novo_valor, nova_forma = util.para_valor(request.form.get('valor')), request.form.get('forma_pagamento') or None
    dividido = row is not None and row['forma_pagamento2'] and (novo_valor != row['valor'] or nova_forma != row['forma_pagamento'])
    db.execute('UPDATE caixa SET valor=?, forma_pagamento=?, nota_fiscal=?, status=?, obs=?, editado_por=? WHERE id=?',
               (novo_valor, nova_forma,
                (request.form.get('nota_fiscal') or '').strip() or None, status,
                (request.form.get('obs') or '').strip() or None, g.usuario['usuario'], cid))
    if dividido:   # mudou o valor ou a forma de um pagamento dividido: a divisão deixa de valer (o ajuste fino é no Movimento de caixa)
        db.execute('UPDATE caixa SET forma_pagamento2=NULL, valor_pagamento2=NULL WHERE id=?', (cid,))
    db.commit()
    flash('Lançamento do caixa atualizado.', 'ok')
    return redirect(request.form.get('voltar') or url_for('atend.caixa'))
