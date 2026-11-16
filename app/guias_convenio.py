"""Guias de convênio digitadas: SP/SADT da Unimed e Pedido para diagnóstico e tratamento do IPSEMG.

A definição de cada modelo (campos numerados, seções e tipos) fica aqui. O formulário e a folha de
impressão (templates/fichas/guia_*.html) percorrem a mesma lista de blocos, então os números batem com o impresso.
Tipos de célula: texto, data (guardada em ISO), num, moeda, calc (calculado), escolha (lista de (valor, rótulo)),
area (várias linhas, campo n), vazio (caixa de assinatura, não guarda nada).
"""
import json
import re
import sqlite3
from datetime import date

from . import util
from .db import agora, config_get, config_set

def _c(k, r, w, t='texto', op=None, n=1):
    return {'k': k, 'r': r, 'w': w, 't': t, 'op': op or [], 'n': n}


def _linha(*cels):
    return {'t': 'linha', 'cels': list(cels)}


def _faixa(titulo):
    return {'t': 'faixa', 'titulo': titulo}


def _tabela(chave, linhas, cols, proc=None):
    """proc: colunas de código, descrição, quantidade (e valor) que o busca de preços preenche na 1ª linha livre."""
    return {'t': 'tabela', 'chave': chave, 'linhas': linhas, 'cols': cols, 'proc': proc}


UNIMED = [
    {'t': 'topo', 'chaves': ['2']},
    _linha(_c('1', '1 - Registro ANS', 20), _c('3', '3 - Número da Guia Principal', 20),
           _c('4', '4 - Data da Autorização', 15, 'data'), _c('5', '5 - Senha', 15),
           _c('6', '6 - Data de Validade da Senha', 15, 'data'),
           _c('7', '7 - Número da Guia Atribuído pela Operadora', 15)),
    _faixa('Dados do Beneficiário'),
    _linha(_c('8', '8 - Número da Carteira', 20), _c('9', '9 - Validade da Carteira', 12, 'data'),
           _c('10', '10 - Nome', 30), _c('11', '11 - Cartão Nacional de Saúde', 20),
           _c('12', '12 - Atendimento a RN (S/N)', 18, 'escolha', [('S', 'Sim'), ('N', 'Não')])),
    _faixa('Dados do Solicitante'),
    _linha(_c('13', '13 - Código na Operadora', 15), _c('14', '14 - Nome do Contratado', 85)),
    _linha(_c('15', '15 - Nome do Profissional Solicitante', 30), _c('16', '16 - Conselho Profissional', 12),
           _c('17', '17 - Número no Conselho', 15), _c('18', '18 - UF', 8), _c('19', '19 - Código CBO', 15),
           _c('20', '20 - Assinatura do Profissional Solicitante', 20, 'vazio')),
    _faixa('Dados da Solicitação / Procedimentos ou Itens Assistenciais Solicitados'),
    _linha(_c('21', '21 - Caráter do Atendimento', 25, 'escolha', [('E', 'Eletivo'), ('U', 'Urgência/Emergência')]),
           _c('22', '22 - Data da Solicitação', 20, 'data'), _c('23', '23 - Indicação Clínica', 55)),
    _tabela('sol', 5, [_c('24', '24 - Tabela', 10), _c('25', '25 - Código do Procedimento ou Item Assistencial', 20),
                       _c('26', '26 - Descrição', 40), _c('27', '27 - Qtde. Solic.', 15, 'num'),
                       _c('28', '28 - Qtde. Aut.', 15, 'num')],
            proc={'cod': '25', 'desc': '26', 'qtd': '27'}),
    _faixa('Dados do Contratado Executante'),
    _linha(_c('29', '29 - Código na Operadora', 20), _c('30', '30 - Nome do Contratado', 60),
           _c('31', '31 - Código CNES', 20)),
    _faixa('Dados do Atendimento'),
    _linha(_c('32', '32 - Tipo de Atendimento', 25), _c('33', '33 - Indicação de Acidente (acidente ou doença relacionada)', 25),
           _c('34', '34 - Tipo de Consulta', 25), _c('35', '35 - Motivo de Encerramento do Atendimento', 25)),
    _faixa('Dados da Execução / Procedimentos e Exames Realizados'),
    _tabela('exe', 5, [_c('36', '36 - Data', 10, 'data'), _c('37', '37 - Hora Inicial', 7), _c('38', '38 - Hora Final', 7),
                       _c('39', '39 - Tabela', 6), _c('40', '40 - Código do Procedimento', 10),
                       _c('41', '41 - Descrição', 22), _c('42', '42 - Qtde.', 5, 'num'), _c('43', '43 - Via', 5),
                       _c('44', '44 - Téc.', 5), _c('45', '45 - Fator Red./Acresc.', 7),
                       _c('46', '46 - Valor Unitário (R$)', 8, 'moeda'), _c('47', '47 - Valor Total (R$)', 8, 'calc')],
            proc={'cod': '40', 'desc': '41', 'qtd': '42', 'valor': '46'}),
    _faixa('Identificação do(s) Profissional(is) Executante(s)'),
    _tabela('prof', 4, [_c('48', '48 - Seq.Ref', 8), _c('49', '49 - Grau Part.', 12),
                        _c('50', '50 - Código na Operadora/CPF', 14), _c('51', '51 - Nome do Profissional', 26),
                        _c('52', '52 - Conselho Profissional', 12), _c('53', '53 - Número no Conselho', 12),
                        _c('54', '54 - UF', 6), _c('55', '55 - Código CBO', 10)]),
    {'t': 'serie', 'chave': '56', 'n': 10,
     'titulo': '56 - Data de Realização de Procedimentos em Série / 57 - Assinatura do Beneficiário ou Responsável'},
    _linha(_c('58', '58 - Observação / Justificativa', 100, 'area', n=2)),
    _linha(_c('59', '59 - Total de Procedimentos (R$)', 14, 'calc'), _c('60', '60 - Total de Taxas e Aluguéis (R$)', 14, 'moeda'),
           _c('61', '61 - Total de Materiais (R$)', 14, 'moeda'), _c('62', '62 - Total de OPME (R$)', 14, 'moeda'),
           _c('63', '63 - Total de Medicamentos (R$)', 14, 'moeda'), _c('64', '64 - Total de Gases Medicinais (R$)', 14, 'moeda'),
           _c('65', '65 - Total Geral (R$)', 16, 'calc')),
    _linha(_c('66', '66 - Assinatura do Responsável pela Autorização', 34, 'vazio'),
           _c('67', '67 - Assinatura do Beneficiário ou Responsável', 33, 'vazio'),
           _c('68', '68 - Assinatura do Contratado', 33, 'vazio')),
]

IPSEMG = [
    {'t': 'topo', 'chaves': []},
    _linha(_c('1', '1 - Matrícula Beneficiário', 50), _c('2', '2 - Plano', 50)),
    _linha(_c('3', '3 - Nome do Beneficiário', 100)),
    _linha(_c('4', '4 - Nome do Prestador Solicitante', 70), _c('5', '5 - Matrícula Prestador Solicitante', 30)),
    _linha(_c('6', '6 - Nome do Profissional Solicitante', 55), _c('7', '7 - Conselho Profissional', 15),
           _c('8', '8 - Número do Conselho', 30)),
    _linha(_c('9', '9 - UF', 15), _c('10', '10 - Especialidade', 85)),
    _linha(_c('11', '11 - Caráter da Solicitação', 60, 'escolha', [('E', 'Eletivo'), ('U', 'Urgência / Emergência')]),
           _c('12', '12 - Paciente Internado', 40, 'escolha', [('S', 'Sim'), ('N', 'Não')])),
    _linha(_c('13', '13 - CID Principal', 100)),
    _linha(_c('14', '14 - Justificativa / Situação Clínica', 100, 'area', n=5)),
    _linha(_c('15', '15 - Exames / Tratamento já Realizados', 100, 'area', n=5)),
    _linha(_c('16', '16 - Hipótese Diagnóstica', 100, 'area', n=5)),
    _tabela('17', 7, [_c('17', '17 - Código Procedimento Solicitado', 25), _c('18', '18 - Descrição do Procedimento', 60),
                      _c('19', '19 - Qte solicitada', 15, 'num')],
        proc={'cod': '17', 'desc': '18', 'qtd': '19'}),
    _linha(_c('20', '20 - Observação', 100, 'area', n=3)),
    _linha(_c('21', '21 - Data (dd / mm / aaaa)', 35), _c('assinatura', 'Assinatura do Solicitante', 65, 'vazio')),
]

MODELOS = {
    'unimed_sadt': {
        'titulo': 'Guia SP/SADT Unimed', 'ficha': 'guia_unimed_sadt', 'blocos': UNIMED,
        'campo_nome': '10', 'campo_cartao': '8', 'campo_medico': '15', 'prefixo': 'guia_unimed_',
        # campos da clínica lembrados entre as guias (chave em config = prefixo + nome)
        'lembrar': {'1': 'registro_ans', '13': 'codigo_operadora', '14': 'nome_contratado', '31': 'cnes'},
        # campo que copia o valor de outro (ex.: código na operadora também vai para o executante)
        'espelhos': {'29': '13', '30': '14'},
    },
    'ipsemg_pedido': {
        'titulo': 'Pedido IPSEMG (diagnóstico e tratamento)', 'ficha': 'guia_ipsemg_pedido', 'blocos': IPSEMG,
        'campo_nome': '3', 'campo_cartao': '1', 'campo_medico': '6', 'prefixo': 'guia_ipsemg_',
        'lembrar': {'4': 'prestador', '5': 'matricula'}, 'espelhos': {},
    },
}


def modelo_valido(modelo):
    return modelo in MODELOS


def _m(modelo):
    return MODELOS[modelo]


def chaves(modelo):
    """Todos os campos que são gravados em `dados` (sem as caixas de assinatura)."""
    out = set()
    for b in _m(modelo)['blocos']:
        t = b['t']
        if t == 'topo':
            out.update(b['chaves'])
        elif t == 'linha':
            out.update(c['k'] for c in b['cels'] if c['t'] != 'vazio')
        elif t == 'tabela':
            for i in range(1, b['linhas'] + 1):
                out.update('%s_%d' % (c['k'], i) for c in b['cols'])
        elif t == 'serie':
            out.update('%s_%d' % (b['chave'], i) for i in range(1, b['n'] + 1))
    return out


def tipos(modelo):
    """{chave: tipo} de todos os campos, para formatar na impressão."""
    out = {}
    for b in _m(modelo)['blocos']:
        t = b['t']
        if t == 'linha':
            out.update({c['k']: c['t'] for c in b['cels']})
        elif t == 'tabela':
            for i in range(1, b['linhas'] + 1):
                out.update({'%s_%d' % (c['k'], i): c['t'] for c in b['cols']})
        elif t == 'serie':
            out.update({'%s_%d' % (b['chave'], i): 'data' for i in range(1, b['n'] + 1)})
    return out


def dados_do_form(form, modelo):
    """Pega do formulário só os campos do modelo, já sem espaços; vazios ficam de fora ao salvar."""
    return {k: (form.get(k) or '').strip()[:500] for k in chaves(modelo)}


def salvar(db, modelo, dados, cliente_id, atendimento_id, usuario, gid=None):
    """Grava a guia (insere ou atualiza `gid`) e lembra os dados fixos da clínica. Devolve o id."""
    m = _m(modelo)
    limpos = {k: str(v).strip() for k, v in (dados or {}).items() if k in chaves(modelo) and str(v or '').strip()}
    if limpos.get(m['campo_nome']):   # nome do paciente em maiúsculas, como no resto do sistema
        limpos[m['campo_nome']] = util.maiusculas(limpos[m['campo_nome']])
    paciente = limpos.get(m['campo_nome'], '')
    json_dados = json.dumps(limpos, ensure_ascii=False)
    agora_ = agora()
    if gid:
        db.execute("UPDATE guias_convenio SET dados=?, paciente=?, cliente_id=?, atendimento_id=?, atualizado_em=? "
                   "WHERE id=?", (json_dados, paciente, cliente_id, atendimento_id, agora_, gid))
    else:
        cur = db.execute(
            "INSERT INTO guias_convenio (modelo, cliente_id, atendimento_id, paciente, dados, usuario, criado_em, atualizado_em) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (modelo, cliente_id, atendimento_id, paciente, json_dados, usuario, agora_, agora_))
        gid = cur.lastrowid
    db.commit()
    for campo, nome in m['lembrar'].items():   # dados fixos da clínica: valem para as próximas guias
        if limpos.get(campo):
            config_set(m['prefixo'] + nome, limpos[campo])
    return gid


def obter(db, gid, modelo=None):
    sql = "SELECT * FROM guias_convenio WHERE id=?"
    args = [gid]
    if modelo:
        sql += " AND modelo=?"
        args.append(modelo)
    r = db.execute(sql, args).fetchone()
    if not r:
        return None
    g = dict(r)
    try:
        g['valores'] = json.loads(r['dados'] or '{}')
    except ValueError:
        g['valores'] = {}
    return g


def listar(db, limite=30):
    rows = db.execute("SELECT id, modelo, paciente, cliente_id, atualizado_em FROM guias_convenio "
                      "ORDER BY id DESC LIMIT ?", (limite,)).fetchall()
    return [dict(r, titulo=MODELOS.get(r['modelo'], {}).get('titulo', r['modelo'])) for r in rows]


def excluir(db, gid):
    db.execute("DELETE FROM guias_convenio WHERE id=?", (gid,))
    db.commit()


def _preco(db, exame):
    """Código e valor do item da tabela de preços ativa cuja descrição é o exame (None se não houver)."""
    try:
        return db.execute(
            "SELECT i.codigo, i.valor FROM tabela_preco_itens i JOIN tabelas_preco t ON t.id=i.tabela_id "
            "WHERE t.ativa=1 AND UPPER(TRIM(i.descricao))=? ORDER BY t.vigencia DESC, i.id LIMIT 1", (exame,)).fetchone()
    except sqlite3.OperationalError:   # a tabela de preços ainda não existe neste banco
        return None


def prefill(db, modelo, cliente_id=None, atendimento_id=None):
    """Valores iniciais de uma guia nova: paciente, carteira, médico, exame e dados fixos da clínica."""
    m = _m(modelo)
    v = {}
    hoje = date.today().isoformat()
    at = db.execute("SELECT * FROM atendimentos WHERE id=?", (atendimento_id,)).fetchone() if atendimento_id else None
    cid = cliente_id or (at['cliente_id'] if at else None)
    cli = db.execute("SELECT * FROM clientes WHERE id=?", (cid,)).fetchone() if cid else None
    if cli:
        v[m['campo_nome']] = util.maiusculas(cli['nome'])
        v[m['campo_cartao']] = cli['cartao_convenio'] or ''
    data = (at['data'] if at and at['data'] else hoje)
    medico = util.maiusculas(at['medico']) if at else ''
    exame = util.maiusculas(at['exame']) if at else ''
    if medico:
        v[m['campo_medico']] = medico
    if modelo == 'unimed_sadt':
        v['22'] = data
        v['36_1'] = data
    else:
        v['21'] = date.fromisoformat(data).strftime('%d / %m / %Y')
    for campo, nome in m['lembrar'].items():   # dados da clínica lembrados da guia anterior
        v[campo] = config_get(m['prefixo'] + nome, '') or ''
    if modelo == 'unimed_sadt':
        v['14'] = v['14'] or config_get('clinica_nome', '') or ''
    else:
        v['4'] = v['4'] or config_get('clinica_nome', '') or ''
    for destino, origem in m['espelhos'].items():
        v[destino] = v.get(origem, '')
    if exame:
        preco = _preco(db, exame)
        for p in [b['proc'] for b in m['blocos'] if b.get('proc')]:
            v['%s_1' % p['desc']] = exame
            v['%s_1' % p['qtd']] = '1'
            if preco and preco['codigo']:
                v['%s_1' % p['cod']] = preco['codigo']
            if preco and preco['valor'] is not None and p.get('valor'):
                v['%s_1' % p['valor']] = util.moeda(preco['valor'])
    return {k: x for k, x in v.items() if x not in (None, '')}


def _numero(valor):
    return util.para_valor(valor) if valor not in (None, '') else None


def calcular(modelo, dados):
    """Cópia dos valores com os totais: 47 = 42 x 46 (se vazio); 59 = soma dos 47; 65 = 59 + 60..64 (se vazio)."""
    v = dict(dados)
    if modelo != 'unimed_sadt':
        return v
    soma = 0.0
    tem = False
    for i in range(1, 6):
        qtd, unit = _numero(v.get('42_%d' % i)), _numero(v.get('46_%d' % i))
        if not v.get('47_%d' % i) and qtd is not None and unit is not None:
            v['47_%d' % i] = '%.2f' % (qtd * unit)
        total = _numero(v.get('47_%d' % i))
        if total is not None:
            soma += total
            tem = True
    if tem:
        v['59'] = '%.2f' % soma
    outros = [_numero(v.get(k)) for k in ('60', '61', '62', '63', '64')]
    if tem or any(x is not None for x in outros):
        if not v.get('65'):
            v['65'] = '%.2f' % ((_numero(v.get('59')) or 0) + sum(x or 0 for x in outros))
    return v


def _formatar(tipo, valor, espacado=False):
    """espacado: data no formato 'dd / mm / aaaa' (campo 21 do IPSEMG). Datas ISO viram dd/mm/aaaa em qualquer campo."""
    if not valor:
        return ''
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', valor) or tipo == 'data':
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', valor):
            d = date.fromisoformat(valor)
            return d.strftime('%d / %m / %Y') if espacado else d.strftime('%d/%m/%Y')
        return util.data_br(valor)
    if tipo in ('moeda', 'calc'):
        n = _numero(valor)
        return util.moeda(n) if n is not None else valor
    return valor


def montar_impressao(modelo, dados):
    """Dicionário 'f' da folha: valores já formatados + os blocos do layout."""
    v = calcular(modelo, dados)
    tp = tipos(modelo)
    f = {k: _formatar(tp.get(k, 'texto'), v.get(k, ''), espacado=(modelo == 'ipsemg_pedido' and k == '21'))
         for k in chaves(modelo)}
    f['blocos'] = _m(modelo)['blocos']
    return f
