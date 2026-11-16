"""Pedidos de compra do estoque: criar e salvar (rascunho), sugerir itens abaixo do mínimo, marcar como enviado, receber
(cada linha vira uma ENTRADA no estoque, com o pedido, o fornecedor e a nota fiscal), cancelar e duplicar.

Cada função que grava faz tudo numa única transação: se alguma regra falhar, nada é gravado (ErroEstoque).
"""
from __future__ import annotations

from datetime import date

from . import estoque as est, util
from .db import agora
from .estoque import ErroEstoque

STATUS = ('RASCUNHO', 'ENVIADO', 'RECEBIDO', 'CANCELADO')
STATUS_NOMES = {'RASCUNHO': 'Rascunho', 'ENVIADO': 'Enviado', 'RECEBIDO': 'Recebido', 'CANCELADO': 'Cancelado'}
ETIQUETAS = {'RASCUNHO': '', 'ENVIADO': 'aberto', 'RECEBIDO': 'pago', 'CANCELADO': 'cancelado'}   # classes de etiqueta.css
TOLERANCIA = est.TOLERANCIA


# ------------------------------------------------------------------ consultas
def obter(db, pid):
    r = db.execute('SELECT * FROM est_pedidos WHERE id=?', (pid,)).fetchone()
    return dict(r) if r else None


def _obter_ou_erro(db, pid):
    ped = obter(db, pid)
    if ped is None:
        raise ErroEstoque('Pedido não encontrado.')
    return ped


def tem_recebimento(db, pid):
    return bool(db.execute('SELECT 1 FROM est_pedido_itens WHERE pedido_id=? AND qtd_recebida>0 LIMIT 1', (pid,)).fetchone())


def editavel(db, ped):
    """Pode mudar itens e dados só enquanto for rascunho ou enviado sem nenhum recebimento."""
    return ped['status'] in ('RASCUNHO', 'ENVIADO') and not tem_recebimento(db, ped['id'])


def listar(db, status=''):
    where, params = ['1=1'], []
    if status in STATUS:
        where.append('p.status=?')
        params.append(status)
    return [dict(r) for r in db.execute(
        'SELECT p.*, (SELECT COALESCE(SUM(i.qtd*COALESCE(i.valor_unitario,0)),0) FROM est_pedido_itens i WHERE i.pedido_id=p.id) AS total '
        'FROM est_pedidos p WHERE %s ORDER BY p.id DESC' % ' AND '.join(where), params)]


def itens_do_pedido(db, pid):
    """Itens com o nome e a unidade do estoque, o recebido, o que falta e o total de cada linha."""
    saida = []
    for r in db.execute('SELECT i.*, it.nome AS item_nome, it.unidade FROM est_pedido_itens i JOIN est_itens it ON it.id=i.item_id '
                        'WHERE i.pedido_id=? ORDER BY i.id', (pid,)):
        d = dict(r)
        d['falta'] = round(max(d['qtd'] - d['qtd_recebida'], 0), est.CASAS)
        d['total'] = round(d['qtd'] * (d['valor_unitario'] or 0), 2)
        saida.append(d)
    return saida


def completo(db, pid):
    """(pedido, itens) para PDF e impressão, com o fornecedor cadastrado e o total. (None, None) se não existir."""
    ped = obter(db, pid)
    if ped is None:
        return None, None
    ped['fornecedor'] = None
    if ped['fornecedor_id']:
        f = db.execute('SELECT * FROM fornecedores WHERE id=?', (ped['fornecedor_id'],)).fetchone()
        ped['fornecedor'] = dict(f) if f else None
    itens = itens_do_pedido(db, pid)
    ped['total'] = round(sum(i['total'] for i in itens), 2)
    return ped, itens


def sugerir_itens(db):
    """Itens ativos com mínimo cadastrado, no mínimo ou abaixo: quantidade = dobro do mínimo menos o saldo (mínimo 1)
    e valor previsto = último valor comprado."""
    saida = []
    for it in est.itens(db, so_abaixo=True):
        qtd = max(1.0, round(2 * it['estoque_minimo'] - it['saldo'], est.CASAS))
        saida.append({'item_id': it['id'], 'nome': it['nome'], 'unidade': it['unidade'] or '', 'saldo': it['saldo'],
                      'minimo': it['estoque_minimo'], 'qtd': qtd, 'valor_unitario': it['ultimo_valor']})
    return saida


# ------------------------------------------------------------------ validação
def _proximo_numero(db, ano):
    """AAAA-NNNN, sequencial dentro do ano."""
    r = db.execute('SELECT numero FROM est_pedidos WHERE numero LIKE ? ORDER BY numero DESC LIMIT 1', ('%d-%%' % ano,)).fetchone()
    seq = int(r['numero'].split('-')[1]) + 1 if r else 1
    return '%d-%04d' % (ano, seq)


def _fornecedor(db, dados):
    """Fornecedor cadastrado e ativo (pelo id) ou nome digitado."""
    fid = str(dados.get('fornecedor_id') or '').strip()
    if fid.isdigit():
        f = db.execute('SELECT id, nome FROM fornecedores WHERE id=? AND ativo=1', (int(fid),)).fetchone()
        if f is None:
            raise ErroEstoque('Fornecedor não encontrado ou desativado.')
        return f['id'], f['nome']
    return None, util.maiusculas(est._texto(dados.get('fornecedor_nome'), 120)) or None


def _linhas(db, lista):
    """Valida as linhas do pedido: item ativo, quantidade maior que zero, sem item repetido. Linha sem item é ignorada.
    Devolve [(item_id, qtd, valor_unitario, obs)]."""
    saida, vistos = [], set()
    for linha in lista:
        txt = str(linha.get('item_id') or '').strip()
        if not txt:
            continue
        if not txt.isdigit():
            raise ErroEstoque('Item inválido.')
        item = est._obter_ativo(db, int(txt))
        if item['id'] in vistos:
            raise ErroEstoque('Item repetido no pedido: %s. Use uma linha só para ele.' % item['nome'])
        vistos.add(item['id'])
        qtd = est._quantidade(linha.get('qtd'), 'Quantidade de %s' % item['nome'], positivo=True)
        valor = est._valor_unitario(linha.get('valor_unitario'))
        saida.append((item['id'], qtd, valor, est._texto(linha.get('obs'), 200) or None))
    if not saida:
        raise ErroEstoque('Inclua pelo menos um item no pedido.')
    return saida


def _inserir(db, usuario, fid, fnome, condicoes, observacao, solicitante, linhas):
    hoje = date.today()
    cur = db.execute('INSERT INTO est_pedidos (numero, data, fornecedor_id, fornecedor_nome, status, condicoes, observacao, solicitante, '
                     'criado_por, criado_em) VALUES (?,?,?,?,?,?,?,?,?,?)',
                     (_proximo_numero(db, hoje.year), hoje.isoformat(), fid, fnome, 'RASCUNHO', condicoes, observacao,
                      solicitante or usuario, usuario, agora()))
    pid = cur.lastrowid
    _gravar_itens(db, pid, linhas)
    return pid


def _gravar_itens(db, pid, linhas):
    db.executemany('INSERT INTO est_pedido_itens (pedido_id, item_id, qtd, valor_unitario, qtd_recebida, obs) VALUES (?,?,?,?,0,?)',
                   [(pid, iid, qtd, valor, obs) for iid, qtd, valor, obs in linhas])


# ------------------------------------------------------------------ gravação
def salvar(db, dados, lista_itens, usuario, pid=None):
    """Cria o pedido como RASCUNHO (pid None) ou altera um pedido que ainda pode mudar. Devolve o id."""
    fid, fnome = _fornecedor(db, dados)
    condicoes = est._texto(dados.get('condicoes'), 200) or None
    observacao = est._texto(dados.get('observacao'), 500) or None
    solicitante = util.maiusculas(est._texto(dados.get('solicitante'), 120)) or None
    linhas = _linhas(db, lista_itens)
    if pid is None:
        novo = _inserir(db, usuario, fid, fnome, condicoes, observacao, solicitante, linhas)
    else:
        ped = _obter_ou_erro(db, pid)
        if ped['status'] not in ('RASCUNHO', 'ENVIADO'):
            raise ErroEstoque('Pedido %s: não pode mais ser alterado.' % STATUS_NOMES[ped['status']].lower())
        if tem_recebimento(db, pid):
            raise ErroEstoque('Este pedido já teve recebimento e não pode mais ser alterado.')
        db.execute('UPDATE est_pedidos SET fornecedor_id=?, fornecedor_nome=?, condicoes=?, observacao=?, solicitante=? WHERE id=?',
                   (fid, fnome, condicoes, observacao, solicitante or usuario, pid))
        db.execute('DELETE FROM est_pedido_itens WHERE pedido_id=?', (pid,))
        _gravar_itens(db, pid, linhas)
        novo = pid
    db.commit()
    return novo


def marcar_enviado(db, pid):
    ped = _obter_ou_erro(db, pid)
    if ped['status'] != 'RASCUNHO':
        raise ErroEstoque('Só um rascunho pode ser marcado como enviado.')
    db.execute("UPDATE est_pedidos SET status='ENVIADO', enviado_em=? WHERE id=?", (agora(), pid))
    db.commit()


def cancelar(db, pid):
    ped = _obter_ou_erro(db, pid)
    if ped['status'] == 'RECEBIDO':
        raise ErroEstoque('Pedido recebido não pode ser cancelado.')
    if ped['status'] == 'CANCELADO':
        raise ErroEstoque('Este pedido já está cancelado.')
    db.execute("UPDATE est_pedidos SET status='CANCELADO', cancelado_em=? WHERE id=?", (agora(), pid))
    db.commit()


def duplicar(db, pid, usuario):
    """Cria um novo rascunho com os mesmos itens (sem o recebido). Devolve o id do novo pedido."""
    ped = _obter_ou_erro(db, pid)
    linhas = [(i['item_id'], i['qtd'], i['valor_unitario'], i['obs']) for i in itens_do_pedido(db, pid)]
    novo = _inserir(db, usuario, ped['fornecedor_id'], ped['fornecedor_nome'], ped['condicoes'], ped['observacao'], None, linhas)
    db.commit()
    return novo


def receber(db, pid, recebimentos, documento, usuario):
    """recebimentos: lista de (item_id, qtd, valor_unitario pago). Linha com quantidade em branco é ignorada.
    Cada linha vira uma ENTRADA no estoque com o pedido, o fornecedor e a nota fiscal. O pedido vira RECEBIDO quando
    tudo chegou; senão continua ENVIADO com o recebimento parcial. Devolve quantas linhas foram lançadas."""
    ped = _obter_ou_erro(db, pid)
    if ped['status'] != 'ENVIADO':
        raise ErroEstoque('Só um pedido enviado pode receber mercadoria.')
    pedido_itens = {i['item_id']: i for i in itens_do_pedido(db, pid)}
    doc = est._texto(documento, 60) or None
    hoje = date.today().isoformat()
    feitos, vistos = 0, set()
    for iid, qtd_bruta, valor_bruto in recebimentos:
        if str(qtd_bruta if qtd_bruta is not None else '').strip() == '':
            continue
        linha = pedido_itens.get(iid)
        if linha is None:
            raise ErroEstoque('Item que não faz parte deste pedido.')
        if iid in vistos:
            raise ErroEstoque('Item repetido no recebimento: %s.' % linha['item_nome'])
        vistos.add(iid)
        qtd = est._quantidade(qtd_bruta, 'Quantidade recebida de %s' % linha['item_nome'], positivo=True)
        if qtd > linha['falta'] + TOLERANCIA:
            raise ErroEstoque('%s: chegaram %s, mas faltam só %s.' % (linha['item_nome'], est.qtd_txt(qtd), est.qtd_txt(linha['falta'])))
        valor = est._valor_unitario(valor_bruto)
        if valor is None:
            raise ErroEstoque('Informe o valor pago de %s.' % linha['item_nome'])
        est.lancar_entrada(db, iid, {'qtd': qtd, 'valor_unitario': valor, 'fornecedor_id': ped['fornecedor_id'] or '',
                                     'fornecedor_nome': ped['fornecedor_nome'] or '', 'documento': doc, 'data_documento': hoje},
                           usuario, pedido_id=pid)
        db.execute('UPDATE est_pedido_itens SET qtd_recebida=qtd_recebida+? WHERE pedido_id=? AND item_id=?', (qtd, pid, iid))
        feitos += 1
    if not feitos:
        raise ErroEstoque('Informe a quantidade recebida de pelo menos um item.')
    pendente = db.execute('SELECT 1 FROM est_pedido_itens WHERE pedido_id=? AND qtd-qtd_recebida>? LIMIT 1', (pid, TOLERANCIA)).fetchone()
    if not pendente:
        db.execute("UPDATE est_pedidos SET status='RECEBIDO', recebido_em=? WHERE id=?", (agora(), pid))
    db.commit()
    return feitos
