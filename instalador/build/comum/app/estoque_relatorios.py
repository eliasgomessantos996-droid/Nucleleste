"""Relatórios do estoque: posição atual com valor, itens abaixo do mínimo, movimentação do período (por item e por motivo
de saída), validades a vencer, escrituração (livro de movimentação por item) e estudo de preços por fornecedor.

Só calcula: lê est_itens, est_movimentos e fornecedores. Os PDFs e as planilhas ficam em estoque_docs.
"""
from __future__ import annotations

from collections import OrderedDict
from datetime import date, timedelta

from . import estoque as est, util

DIAS_VALIDADE = 60          # validade que vence em até este prazo entra no relatório
TOLERANCIA = est.TOLERANCIA
TIPO_NOME = {'ENTRADA': 'Entrada', 'SAIDA': 'Baixa', 'AJUSTE': 'Ajuste'}


def _tipo(tipo):
    return tipo if tipo in est.TIPOS else ''


def _clausulas(de, ate, campo='date(m.data_hora)'):
    """Filtro de período sobre a data da movimentação (De/Até são AAAA-MM-DD ou vazio)."""
    clausulas, params = [], []
    if de:
        clausulas.append('%s >= ?' % campo)
        params.append(de)
    if ate:
        clausulas.append('%s <= ?' % campo)
        params.append(ate)
    return clausulas, params


# ------------------------------------------------------------------ posição e alertas
def posicao(db, tipo=''):
    """Itens ativos com saldo, último valor, valor em estoque (saldo × último valor) e situação. Devolve (linhas, total)."""
    linhas = []
    for i in est.itens(db, _tipo(tipo)):
        valor = round(i['saldo'] * (i['ultimo_valor'] or 0), 2)
        linhas.append({'id': i['id'], 'nome': i['nome'], 'tipo': i['tipo'], 'unidade': i['unidade'] or '', 'saldo': i['saldo'],
                       'minimo': i['estoque_minimo'], 'ultimo_valor': i['ultimo_valor'], 'valor': valor, 'situacao': i['situacao']})
    return linhas, round(sum(l['valor'] for l in linhas), 2)


def abaixo_minimo(db, tipo=''):
    """Itens com mínimo cadastrado, no mínimo ou abaixo, com a quantidade que falta para chegar ao mínimo."""
    return [dict(i, falta=round(i['estoque_minimo'] - i['saldo'], est.CASAS)) for i in est.itens(db, _tipo(tipo), so_abaixo=True)]


# ------------------------------------------------------------------ movimentação do período
def movimentacao(db, de='', ate='', tipo=''):
    """Por item: entradas, saídas, ajustes líquidos (+/-) e saldo do período (entradas - saídas ± ajustes), e as saídas
    separadas por motivo. Devolve {'itens': [...], 'totais': {...}}."""
    clausulas, params = _clausulas(de, ate)
    if _tipo(tipo):
        clausulas.append('i.tipo=?')
        params.append(_tipo(tipo))
    where = ' AND '.join(['1=1'] + clausulas)
    base = 'FROM est_movimentos m JOIN est_itens i ON i.id=m.item_id WHERE %s' % where
    linhas = OrderedDict()
    for r in db.execute('SELECT i.id, i.nome, i.tipo, i.unidade, '
                        "COALESCE(SUM(CASE WHEN m.tipo='ENTRADA' THEN m.qtd ELSE 0 END),0) AS entradas, "
                        "COALESCE(SUM(CASE WHEN m.tipo='SAIDA' THEN m.qtd ELSE 0 END),0) AS saidas, "
                        "COALESCE(SUM(CASE WHEN m.tipo='AJUSTE' THEN m.sentido*m.qtd ELSE 0 END),0) AS ajustes " + base +
                        ' GROUP BY i.id ORDER BY i.tipo, UPPER(i.nome)', params):
        linhas[r['id']] = {'id': r['id'], 'nome': r['nome'], 'tipo': r['tipo'], 'unidade': r['unidade'] or '', 'entradas': r['entradas'],
                           'saidas': r['saidas'], 'ajustes': r['ajustes'], 'motivos': {m: 0.0 for m in est.MOTIVOS_SAIDA}}
    for r in db.execute("SELECT i.id, m.motivo, SUM(m.qtd) AS qtd " + base + " AND m.tipo='SAIDA' GROUP BY i.id, m.motivo", params):
        if r['id'] in linhas and r['motivo'] in linhas[r['id']]['motivos']:
            linhas[r['id']]['motivos'][r['motivo']] = r['qtd']
    itens = []
    for l in linhas.values():
        l['saldo'] = round(l['entradas'] - l['saidas'] + l['ajustes'], est.CASAS)
        itens.append(l)
    totais = {'entradas': sum(l['entradas'] for l in itens), 'saidas': sum(l['saidas'] for l in itens),
              'ajustes': sum(l['ajustes'] for l in itens), 'saldo': sum(l['saldo'] for l in itens),
              'motivos': {m: sum(l['motivos'][m] for l in itens) for m in est.MOTIVOS_SAIDA}}
    return {'itens': itens, 'totais': totais}


# ------------------------------------------------------------------ validades
def validades(db, tipo='', hoje=None):
    """Itens cuja última entrada com validade vence em até DIAS_VALIDADE dias (ou já venceu). Mais próximas primeiro."""
    hoje = hoje or date.today()
    limite = (hoje + timedelta(days=DIAS_VALIDADE)).isoformat()
    saida = []
    for i in est.itens(db, _tipo(tipo)):
        m = db.execute("SELECT lote, validade FROM est_movimentos WHERE item_id=? AND tipo='ENTRADA' AND validade IS NOT NULL "
                       'ORDER BY data_hora DESC, id DESC LIMIT 1', (i['id'],)).fetchone()
        if m is None or m['validade'] > limite:
            continue
        dias = (date.fromisoformat(m['validade']) - hoje).days
        saida.append(dict(i, lote=m['lote'] or '', validade=m['validade'], dias=dias, vencido=dias < 0))
    return sorted(saida, key=lambda r: r['validade'])


def relatorio(db, de='', ate='', tipo='', hoje=None):
    """Tudo que o relatório do estoque mostra, num dicionário (a tela, o PDF e o Excel usam o mesmo)."""
    tipo = _tipo(tipo)
    pos, total = posicao(db, tipo)
    return {'de': de, 'ate': ate, 'tipo': tipo, 'posicao': pos, 'valor_total': total, 'abaixo': abaixo_minimo(db, tipo),
            'mov': movimentacao(db, de, ate, tipo), 'validades': validades(db, tipo, hoje), 'hoje': (hoje or date.today()).isoformat()}


# ------------------------------------------------------------------ escrituração
def _saldo_inicial(db, item_id, de):
    if not de:
        return 0.0
    r = db.execute('SELECT COALESCE(SUM(sentido*qtd),0) FROM est_movimentos WHERE item_id=? AND date(data_hora) < ?', (item_id, de)).fetchone()
    return round(r[0], est.CASAS)


def escrituracao(db, de='', ate='', item_id=None, tipo=''):
    """Livro de movimentação: para cada item, saldo inicial (movimentos antes de De), cada movimento do período em ordem,
    saldo final e totais. Entrada e saída seguem o sentido (AJUSTE entra como entrada ou saída conforme o sinal).
    `confere` indica se o saldo final bate com o saldo gravado no último movimento até Até."""
    tipo = _tipo(tipo)
    where, params = ['1=1'], []
    if item_id:
        where.append('i.id=?')
        params.append(item_id)
    else:
        where.append('(i.ativo=1 OR EXISTS (SELECT 1 FROM est_movimentos x WHERE x.item_id=i.id))')
        if tipo:
            where.append('i.tipo=?')
            params.append(tipo)
    itens = db.execute('SELECT i.* FROM est_itens i WHERE %s ORDER BY i.tipo, UPPER(i.nome)' % ' AND '.join(where), params).fetchall()
    clausulas, pparams = _clausulas(de, ate, 'date(m.data_hora)')
    saida = []
    for i in itens:
        movs = [dict(r) for r in db.execute(
            'SELECT m.* FROM est_movimentos m WHERE m.item_id=? %s ORDER BY m.data_hora, m.id'
            % ''.join(' AND ' + c for c in clausulas), [i['id']] + pparams)]
        inicial = _saldo_inicial(db, i['id'], de)
        if not movs and inicial == 0:
            continue
        saldo, entradas, saidas, linhas = inicial, 0.0, 0.0, []
        for m in movs:
            e = m['qtd'] if m['sentido'] > 0 else 0.0
            s = m['qtd'] if m['sentido'] < 0 else 0.0
            saldo = round(saldo + m['sentido'] * m['qtd'], est.CASAS)
            entradas += e
            saidas += s
            linhas.append({'data_hora': m['data_hora'], 'documento': m['documento'] or '', 'tipo': TIPO_NOME.get(m['tipo'], m['tipo']),
                           'motivo': (m['fornecedor_nome'] or '') if m['tipo'] == 'ENTRADA' else (m['motivo'] or ''),
                           'entrada': e, 'saida': s, 'saldo': saldo, 'valor': m['valor_unitario'], 'usuario': m['usuario'] or ''})
        entradas, saidas = round(entradas, est.CASAS), round(saidas, est.CASAS)
        final = round(inicial + entradas - saidas, est.CASAS)
        ultimo = db.execute('SELECT saldo_apos FROM est_movimentos WHERE item_id=? AND date(data_hora) <= ? '
                            'ORDER BY data_hora DESC, id DESC LIMIT 1', (i['id'], ate or '9999-12-31')).fetchone()
        gravado = ultimo[0] if ultimo else 0.0
        saida.append({'id': i['id'], 'nome': i['nome'], 'tipo': i['tipo'], 'unidade': i['unidade'] or '', 'inicial': inicial,
                      'entradas': entradas, 'saidas': saidas, 'final': final, 'linhas': linhas,
                      'confere': abs(final - gravado) < TOLERANCIA and abs(saldo - final) < TOLERANCIA})
    return saida


# ------------------------------------------------------------------ estudo de preços
def _fornecedor_nome(r):
    return r['forn_cad'] or r['fornecedor_nome'] or 'Não informado'


def _chave_fornecedor(r):
    return ('f', r['fornecedor_id']) if r['fornecedor_id'] else ('n', (r['fornecedor_nome'] or '').upper())


def fornecedores_com_entrada(db):
    """Opções do filtro de fornecedor: cadastrados (f:ID) e nomes digitados nas entradas sem cadastro (n:NOME)."""
    cadastrados = [dict(r) for r in db.execute(
        'SELECT DISTINCT f.id, f.nome FROM est_movimentos m JOIN fornecedores f ON f.id=m.fornecedor_id ORDER BY UPPER(f.nome)')]
    avulsos = [r[0] for r in db.execute("SELECT DISTINCT UPPER(fornecedor_nome) FROM est_movimentos "
                                        "WHERE tipo='ENTRADA' AND fornecedor_id IS NULL AND fornecedor_nome IS NOT NULL ORDER BY 1")]
    return cadastrados, avulsos


def compras(db, de='', ate='', item_id=None, fornecedor=''):
    """Entradas com valor unitário, em ordem cronológica, com o fornecedor cadastrado (se houver)."""
    clausulas, params = _clausulas(de, ate)
    clausulas += ["m.tipo='ENTRADA'", 'm.valor_unitario IS NOT NULL']
    if item_id:
        clausulas.append('m.item_id=?')
        params.append(item_id)
    tipo_f, _, valor_f = (fornecedor or '').partition(':')
    if tipo_f == 'f' and valor_f.isdigit():
        clausulas.append('m.fornecedor_id=?')
        params.append(int(valor_f))
    elif tipo_f == 'n' and valor_f:
        clausulas.append('m.fornecedor_id IS NULL AND UPPER(m.fornecedor_nome)=?')
        params.append(valor_f.upper())
    return [dict(r) for r in db.execute(
        'SELECT m.*, i.nome AS item_nome, i.unidade, i.tipo AS item_tipo, f.nome AS forn_cad, f.id AS forn_id '
        'FROM est_movimentos m JOIN est_itens i ON i.id=m.item_id LEFT JOIN fornecedores f ON f.id=m.fornecedor_id '
        'WHERE %s ORDER BY m.data_hora, m.id' % ' AND '.join(['1=1'] + clausulas), params)]


def _analise(lst):
    """Resumo de preços de um item a partir das entradas dele (em ordem cronológica)."""
    valores = [r['valor_unitario'] for r in lst]
    ultima = lst[-1]
    penultima = lst[-2] if len(lst) > 1 else None
    variacao = None
    if penultima and penultima['valor_unitario']:
        variacao = round((ultima['valor_unitario'] - penultima['valor_unitario']) / penultima['valor_unitario'] * 100, 2)
    grupos = OrderedDict()
    for r in lst:
        grupos.setdefault(_chave_fornecedor(r), []).append(r)
    comparativo = []
    for g in grupos.values():
        ult = g[-1]
        vals = [x['valor_unitario'] for x in g]
        comparativo.append({'nome': _fornecedor_nome(ult), 'fid': ult['forn_id'], 'ultimo': ult['valor_unitario'], 'data': ult['data_hora'],
                            'qtd': ult['qtd'], 'media': round(sum(vals) / len(vals), 4), 'compras': len(vals)})
    comparativo.sort(key=lambda c: (c['ultimo'], c['nome']))
    historico = [{'data_hora': r['data_hora'], 'nota': r['documento'] or '', 'nome': _fornecedor_nome(r), 'fid': r['forn_id'],
                  'valor': r['valor_unitario'], 'qtd': r['qtd']} for r in lst]
    return {'iid': ultima['item_id'], 'nome': ultima['item_nome'], 'tipo': ultima['item_tipo'], 'unidade': ultima['unidade'] or '',
            'ultimo': ultima['valor_unitario'], 'ultimo_data': ultima['data_hora'], 'ultimo_fornecedor': _fornecedor_nome(ultima),
            'ultimo_fid': ultima['forn_id'], 'menor': min(valores), 'media': round(sum(valores) / len(valores), 4), 'maior': max(valores),
            'variacao': variacao, 'compras': len(lst), 'mais_barato': comparativo[0], 'comparativo': comparativo, 'historico': historico}


def estudo(db, de='', ate='', item_id=None, fornecedor=''):
    """Estudo de preços: um resumo por item com entradas valoradas (ordem pelo nome)."""
    por_item = OrderedDict()
    for r in compras(db, de, ate, item_id, fornecedor):
        por_item.setdefault(r['item_id'], []).append(r)
    itens = [_analise(lst) for lst in por_item.values()]
    itens.sort(key=lambda a: (a['tipo'], a['nome']))
    return itens


def grafico(historico, w=640, h=200, margem=28):
    """Pontos do gráfico de linha (SVG) do valor pago ao longo do tempo. None se não há histórico."""
    if not historico:
        return None
    vals = [r['valor'] for r in historico]
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    n = len(vals)
    passo = (w - 2 * margem) / max(n - 1, 1)
    pontos = []
    for k, r in enumerate(historico):
        x = margem + k * passo if n > 1 else w / 2
        y = h / 2 if hi == lo else h - margem - (r['valor'] - lo) / span * (h - 2 * margem)
        pontos.append({'x': round(x, 1), 'y': round(y, 1), 'valor': r['valor'], 'data': r['data_hora'][:10], 'nome': r['nome']})
    return {'w': w, 'h': h, 'margem': margem, 'pontos': pontos, 'linha': ' '.join('%s,%s' % (p['x'], p['y']) for p in pontos),
            'lo': lo, 'hi': hi}
