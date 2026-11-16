"""Estoque de materiais e medicamentos: itens, entradas, baixas manuais, ajuste de inventário, histórico de compras e
alerta de estoque mínimo à gerência. Independente do módulo de enfermagem (tabelas est_itens e est_movimentos).

Cada função que grava faz tudo numa única transação: se alguma regra falhar, nada é gravado (ErroEstoque).
"""
from __future__ import annotations

from datetime import date

from . import util
from .db import agora

TIPOS = ('MATERIAL', 'MEDICAMENTO')
MOTIVOS_SAIDA = ('Uso', 'Perda', 'Vencido', 'Doação', 'Outro')
CASAS = 3          # quantidades aceitam até 3 casas decimais
TOLERANCIA = 0.0005


class ErroEstoque(ValueError):
    """Erro de validação mostrado ao usuário."""


# ------------------------------------------------------------------ valores
def _texto(v, maximo=200):
    return str(v or '').strip()[:maximo]


def _quantidade(v, rotulo, positivo=False, minimo=None):
    txt = str(v if v is not None else '').strip().replace(',', '.')
    try:
        n = float(txt)
    except ValueError:
        raise ErroEstoque('%s inválido.' % rotulo)
    if n != n or n in (float('inf'), float('-inf')):
        raise ErroEstoque('%s inválido.' % rotulo)
    if round(n, CASAS) != n:
        raise ErroEstoque('%s aceita no máximo %d casas decimais.' % (rotulo, CASAS))
    if positivo and n <= 0:
        raise ErroEstoque('%s deve ser maior que zero.' % rotulo)
    if minimo is not None and n < minimo:
        raise ErroEstoque('%s não pode ser menor que %s.' % (rotulo, minimo))
    return round(n, CASAS)


def _valor_unitario(v):
    if v in (None, ''):
        return None
    txt = str(v).strip()
    if ',' in txt:   # formato brasileiro: 1.234,56
        txt = txt.replace('.', '').replace(',', '.')
    try:
        n = float(txt)
    except ValueError:
        raise ErroEstoque('Valor unitário inválido.')
    if n < 0:
        raise ErroEstoque('Valor unitário não pode ser negativo.')
    return round(n, 4)


def _data_iso(v, rotulo):
    txt = str(v or '').strip()
    if not txt:
        return None
    try:
        return date.fromisoformat(txt).isoformat()
    except ValueError:
        raise ErroEstoque('%s inválida.' % rotulo)


def qtd_txt(n):
    """Número no formato brasileiro, sem zeros à direita (1,5 e 2)."""
    return ('%.3f' % n).rstrip('0').rstrip('.').replace('.', ',')


def situacao_de(saldo, minimo):
    if (saldo or 0) <= 0:
        return 'zerado'
    if (minimo or 0) > 0 and saldo <= minimo:
        return 'abaixo'
    return 'ok'


# ------------------------------------------------------------------ itens
def obter(db, iid):
    r = db.execute('SELECT * FROM est_itens WHERE id=?', (iid,)).fetchone()
    return dict(r) if r else None


def _obter_ativo(db, iid):
    item = obter(db, iid)
    if item is None:
        raise ErroEstoque('Item não encontrado.')
    if not item['ativo']:
        raise ErroEstoque('Item desativado. Reative-o para lançar movimentos.')
    return item


def _nome_unico(db, tipo, nome, iid=None):
    r = db.execute('SELECT id FROM est_itens WHERE tipo=? AND nome=? COLLATE NOCASE AND id<>?', (tipo, nome, iid or 0)).fetchone()
    if r:
        raise ErroEstoque('Já existe um item com este nome neste tipo (%s).' % tipo.lower())


def salvar_item(db, dados, usuario, iid=None):
    """Cria ou altera um item. Na criação, 'saldo_inicial' (opcional) vira uma ENTRADA 'Saldo inicial'."""
    nome = util.maiusculas(_texto(dados.get('nome')))
    if not nome:
        raise ErroEstoque('Informe o nome do item.')
    tipo = util.maiusculas(_texto(dados.get('tipo'), 20))
    if tipo not in TIPOS:
        raise ErroEstoque('Escolha o tipo: material ou medicamento.')
    unidade = util.maiusculas(_texto(dados.get('unidade'), 20))
    if not unidade:
        raise ErroEstoque('Informe a unidade (ex.: UN, CX, AMP, FR).')
    minimo = _quantidade(dados.get('estoque_minimo') or 0, 'Estoque mínimo', minimo=0)
    codigo = _texto(dados.get('codigo'), 40) or None
    local = _texto(dados.get('local'), 80) or None
    obs = _texto(dados.get('obs'), 500) or None
    _nome_unico(db, tipo, nome, iid)
    if iid is None:
        saldo_inicial = _quantidade(dados.get('saldo_inicial') or 0, 'Saldo inicial', minimo=0)
        cur = db.execute('INSERT INTO est_itens (codigo, nome, tipo, unidade, local, estoque_minimo, saldo, obs, ativo, criado_em, criado_por) '
                         'VALUES (?,?,?,?,?,?,0,?,1,?,?)', (codigo, nome, tipo, unidade, local, minimo, obs, agora(), usuario))
        novo = cur.lastrowid
        if saldo_inicial > 0:
            _movimentar(db, novo, 'ENTRADA', 1, saldo_inicial, usuario, valor=None, obs='Saldo inicial')
        db.commit()
        return novo
    if obter(db, iid) is None:
        raise ErroEstoque('Item não encontrado.')
    ativo = 1 if dados.get('ativo') else 0
    db.execute('UPDATE est_itens SET codigo=?, nome=?, tipo=?, unidade=?, local=?, estoque_minimo=?, obs=?, ativo=? WHERE id=?',
               (codigo, nome, tipo, unidade, local, minimo, obs, ativo, iid))
    reavaliar_alerta(db, iid)
    db.commit()
    return iid


def excluir_item(db, iid):
    """Só exclui item sem nenhum movimento; item com histórico é desativado (a edição tem o campo Ativo)."""
    if obter(db, iid) is None:
        raise ErroEstoque('Item não encontrado.')
    if db.execute('SELECT 1 FROM est_movimentos WHERE item_id=? LIMIT 1', (iid,)).fetchone():
        raise ErroEstoque('Este item já tem movimentações. Desative-o em vez de excluir.')
    db.execute('DELETE FROM est_itens WHERE id=?', (iid,))
    db.commit()


def itens(db, tipo='', busca='', so_abaixo=False, incluir_inativos=False):
    """Lista de itens com a situação de cada um ('zerado', 'abaixo', 'ok')."""
    where, params = ['1=1'], []
    if not incluir_inativos:
        where.append('ativo=1')
    if tipo in TIPOS:
        where.append('tipo=?')
        params.append(tipo)
    busca = util.maiusculas(busca)
    if busca:
        where.append("(UPPER(nome) LIKE ? OR UPPER(COALESCE(codigo,'')) LIKE ?)")
        params += ['%' + busca + '%', '%' + busca + '%']
    if so_abaixo:
        where.append('estoque_minimo>0 AND saldo<=estoque_minimo')
    saida = []
    for r in db.execute('SELECT * FROM est_itens WHERE %s ORDER BY tipo, UPPER(nome)' % ' AND '.join(where), params):
        d = dict(r)
        d['situacao'] = situacao_de(d['saldo'], d['estoque_minimo'])
        saida.append(d)
    return saida


def resumo_alertas(db):
    """Quantos itens ativos estão no estoque mínimo ou abaixo (com mínimo cadastrado)."""
    return db.execute('SELECT COUNT(*) FROM est_itens WHERE ativo=1 AND estoque_minimo>0 AND saldo<=estoque_minimo').fetchone()[0]


# ------------------------------------------------------------------ movimentos
def _movimentar(db, item_id, tipo, sentido, qtd, usuario, valor=None, fornecedor_id=None, fornecedor_nome=None, documento=None,
                lote=None, validade=None, data_documento=None, motivo=None, obs=None, pedido_id=None):
    """Grava o movimento e atualiza o saldo. Não faz commit (quem chama controla a transação)."""
    item = obter(db, item_id)
    novo_saldo = round(item['saldo'] + sentido * qtd, CASAS)
    if novo_saldo < -TOLERANCIA:
        raise ErroEstoque('Saldo insuficiente: %s %s disponível(eis), a baixa é de %s.' % (qtd_txt(item['saldo']), item['unidade'], qtd_txt(qtd)))
    novo_saldo = max(novo_saldo, 0.0)
    db.execute('INSERT INTO est_movimentos (item_id, data_hora, tipo, sentido, qtd, valor_unitario, fornecedor_id, fornecedor_nome, documento, '
               'lote, validade, data_documento, motivo, obs, usuario, saldo_apos, pedido_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
               (item_id, agora(), tipo, sentido, qtd, valor, fornecedor_id, fornecedor_nome, documento, lote, validade,
                data_documento, motivo, obs, usuario, novo_saldo, pedido_id))
    db.execute('UPDATE est_itens SET saldo=? WHERE id=?', (novo_saldo, item_id))
    return novo_saldo


def reavaliar_alerta(db, item_id):
    """Saldo voltou acima do mínimo: a próxima queda para o mínimo volta a avisar a gerência."""
    db.execute('UPDATE est_itens SET alerta_enviado=0 WHERE id=? AND estoque_minimo>0 AND saldo>estoque_minimo', (item_id,))


def entrada(db, item_id, dados, usuario):
    """Entrada de compra ou doação. Com valor unitário, atualiza o último valor e a última compra do item."""
    lancar_entrada(db, item_id, dados, usuario)
    db.commit()


def lancar_entrada(db, item_id, dados, usuario, pedido_id=None):
    """Mesma regra da entrada, sem commit (o recebimento de pedido grava várias linhas numa só transação)."""
    item = _obter_ativo(db, item_id)
    qtd = _quantidade(dados.get('qtd'), 'Quantidade', positivo=True)
    valor = _valor_unitario(dados.get('valor_unitario'))
    fid = dados.get('fornecedor_id')
    fornecedor_id, fornecedor_nome = None, None
    if str(fid or '').strip().isdigit():
        f = db.execute('SELECT id, nome FROM fornecedores WHERE id=?', (int(fid),)).fetchone()
        if f is None:
            raise ErroEstoque('Fornecedor não encontrado.')
        fornecedor_id, fornecedor_nome = f['id'], f['nome']
    else:
        fornecedor_nome = util.maiusculas(_texto(dados.get('fornecedor_nome'), 120)) or None
    documento = _texto(dados.get('documento'), 60) or None
    lote = _texto(dados.get('lote'), 60) or None
    validade = _data_iso(dados.get('validade'), 'Validade')
    data_doc = _data_iso(dados.get('data_documento'), 'Data da compra')
    obs = _texto(dados.get('obs'), 500) or None
    _movimentar(db, item['id'], 'ENTRADA', 1, qtd, usuario, valor=valor, fornecedor_id=fornecedor_id, fornecedor_nome=fornecedor_nome,
                documento=documento, lote=lote, validade=validade, data_documento=data_doc, obs=obs, pedido_id=pedido_id)
    if valor is not None:
        db.execute('UPDATE est_itens SET ultimo_valor=?, ultima_compra=? WHERE id=?', (valor, data_doc or date.today().isoformat(), item['id']))
    reavaliar_alerta(db, item['id'])
    verificar_alertas(db)


def saida(db, item_id, qtd, motivo, obs, usuario):
    """Baixa manual. Não deixa o saldo ficar negativo."""
    item = _obter_ativo(db, item_id)
    quantidade = _quantidade(qtd, 'Quantidade', positivo=True)
    motivo = _texto(motivo, 20)
    if motivo not in MOTIVOS_SAIDA:
        raise ErroEstoque('Escolha o motivo da baixa: %s.' % ', '.join(MOTIVOS_SAIDA))
    _movimentar(db, item['id'], 'SAIDA', -1, quantidade, usuario, motivo=motivo, obs=_texto(obs, 500) or None)
    verificar_alertas(db)
    db.commit()


def ajuste(db, item_id, contagem, obs, usuario):
    """Inventário: o saldo passa a ser a contagem física. A diferença fica registrada como AJUSTE (motivo obrigatório)."""
    item = _obter_ativo(db, item_id)
    nova = _quantidade(contagem, 'Contagem física', minimo=0)
    motivo = _texto(obs, 500)
    if not motivo:
        raise ErroEstoque('Informe o motivo do ajuste na observação.')
    diferenca = round(nova - item['saldo'], CASAS)
    if abs(diferenca) < TOLERANCIA:
        raise ErroEstoque('A contagem já confere com o saldo. Nada foi alterado.')
    _movimentar(db, item['id'], 'AJUSTE', 1 if diferenca > 0 else -1, abs(diferenca), usuario, motivo=motivo, obs=motivo)
    reavaliar_alerta(db, item['id'])
    verificar_alertas(db)
    db.commit()


def historico_compras(db, item_id):
    """Entradas com valor unitário, da mais recente para a mais antiga."""
    return [dict(r) for r in db.execute(
        "SELECT * FROM est_movimentos WHERE item_id=? AND tipo='ENTRADA' AND valor_unitario IS NOT NULL "
        'ORDER BY data_hora DESC, id DESC', (item_id,))]


def ultimos_valores(db, item_id, quantidade=5):
    return historico_compras(db, item_id)[:quantidade]


def movimentos(db, de='', ate='', item_id=None, tipo=''):
    """Movimentações com filtros de período, item e tipo. Devolve (linhas, totais)."""
    where, params = ['1=1'], []
    if de:
        where.append('date(m.data_hora) >= ?')
        params.append(de)
    if ate:
        where.append('date(m.data_hora) <= ?')
        params.append(ate)
    if item_id:
        where.append('m.item_id=?')
        params.append(item_id)
    if tipo in ('ENTRADA', 'SAIDA', 'AJUSTE'):
        where.append('m.tipo=?')
        params.append(tipo)
    linhas = [dict(r) for r in db.execute(
        'SELECT m.*, i.nome AS item_nome, i.unidade, i.tipo AS item_tipo FROM est_movimentos m JOIN est_itens i ON i.id=m.item_id '
        'WHERE %s ORDER BY m.data_hora DESC, m.id DESC' % ' AND '.join(where), params)]
    totais = {'entradas': 0.0, 'saidas': 0.0, 'valor_entradas': 0.0}
    for m in linhas:
        if m['sentido'] > 0 and m['tipo'] == 'ENTRADA':
            totais['entradas'] += m['qtd']
            totais['valor_entradas'] += m['qtd'] * (m['valor_unitario'] or 0)
        elif m['sentido'] < 0:
            totais['saidas'] += m['qtd']
    return linhas, totais


# ------------------------------------------------------------------ alerta à gerência
def verificar_alertas(db):
    """Envia UMA mensagem à gerência por item que está no estoque mínimo (marca alerta_enviado). Não faz commit.
    Sem destinatário ou sem o contato do sistema, nada é marcado: o aviso sai quando houver quem receba."""
    from . import avisos
    de_sistema = avisos.sistema_id(db)
    destinos = avisos.gerentes(db)
    if de_sistema is None or not destinos:
        return 0
    criticos = db.execute('SELECT id, nome, unidade, saldo, estoque_minimo FROM est_itens '
                          'WHERE ativo=1 AND estoque_minimo>0 AND saldo<=estoque_minimo AND alerta_enviado=0 ORDER BY UPPER(nome)').fetchall()
    for it in criticos:
        corpo = 'Estoque baixo: %s está com %s %s (mínimo %s).' % (it['nome'], qtd_txt(it['saldo']), it['unidade'] or '',
                                                                 qtd_txt(it['estoque_minimo']))
        for para in destinos:
            db.execute('INSERT INTO chat_mensagens (de_id, para_id, corpo, criado_em) VALUES (?,?,?,?)', (de_sistema, para, corpo, agora()))
        db.execute('UPDATE est_itens SET alerta_enviado=1 WHERE id=?', (it['id'],))
    return len(criticos)
