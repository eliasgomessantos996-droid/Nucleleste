"""Lotes de pagamento do contas a pagar: as contas marcadas viram um lote ligado a um banco.

As funções recebem a conexão (get_db) e o login de quem está agindo. Não fazem commit: quem chama (a rota) faz.
"""
from .db import agora


class ErroLote(Exception):
    """Mensagem para mostrar ao usuário quando a operação não pode ser feita."""


def _marcas(ids):
    return ','.join('?' * len(ids))


def _pendentes(db, lote_id, conta_ids):
    """Contas do lote que ainda estão 'EM PAGAMENTO' (conta_ids=None pega todas)."""
    sql = "SELECT conta_id FROM contas_lote_itens WHERE lote_id=? AND situacao='EM PAGAMENTO'"
    params = [lote_id]
    if conta_ids is not None:
        if not conta_ids:
            return []
        sql += ' AND conta_id IN (%s)' % _marcas(conta_ids)
        params += list(conta_ids)
    return [r[0] for r in db.execute(sql + ' ORDER BY conta_id', params).fetchall()]


def _atualizar_status(db, lote_id):
    """Lote CONCLUIDO quando não sobra conta em pagamento; senão ABERTO."""
    pendentes = db.execute("SELECT COUNT(*) FROM contas_lote_itens WHERE lote_id=? AND situacao='EM PAGAMENTO'",
                           (lote_id,)).fetchone()[0]
    if pendentes == 0:
        db.execute("UPDATE contas_lotes SET status='CONCLUIDO', concluido_em=? WHERE id=?", (agora(), lote_id))
    else:
        db.execute("UPDATE contas_lotes SET status='ABERTO', concluido_em=NULL WHERE id=?", (lote_id,))


def criar(db, ids, banco, usuario, obs=None):
    """Cria o lote com as contas que estão ABERTO e fora de outro lote. Devolve o id do lote."""
    ids = sorted(set(ids))
    disponiveis = [r[0] for r in db.execute(
        "SELECT id FROM contas WHERE id IN (%s) AND status='ABERTO' AND lote_id IS NULL ORDER BY id" % _marcas(ids),
        ids).fetchall()] if ids else []
    if not disponiveis:
        raise ErroLote('Nenhuma das contas marcadas está disponível: elas já estão pagas ou em outro lote.')
    agora_ = agora()
    cur = db.execute('INSERT INTO contas_lotes (banco, criado_em, criado_por, obs) VALUES (?,?,?,?)',
                     (banco, agora_, usuario, obs))
    lote_id = cur.lastrowid
    for cid in disponiveis:
        db.execute("INSERT INTO contas_lote_itens (lote_id, conta_id, situacao, atualizado_em, atualizado_por) "
                   "VALUES (?,?,'EM PAGAMENTO',?,?)", (lote_id, cid, agora_, usuario))
        db.execute('UPDATE contas SET lote_id=? WHERE id=?', (lote_id, cid))
    return lote_id


def obter(db, lote_id):
    """Dados do lote, as contas dele e os totais. None se o lote não existir."""
    lote = db.execute('SELECT * FROM contas_lotes WHERE id=?', (lote_id,)).fetchone()
    if not lote:
        return None
    itens = [dict(r) for r in db.execute(
        'SELECT i.id AS item_id, i.situacao, i.atualizado_em, i.atualizado_por, '
        'c.id AS conta_id, c.descricao, c.fornecedor, c.vencimento, c.valor, c.parcela_n, c.parcela_total, '
        'c.status, c.data_pagamento, c.banco_pagamento '
        'FROM contas_lote_itens i JOIN contas c ON c.id=i.conta_id WHERE i.lote_id=? '
        'ORDER BY c.vencimento, c.id', (lote_id,)).fetchall()]

    def soma(situacao):
        sel = [i for i in itens if i['situacao'] == situacao]
        return len(sel), sum(i['valor'] or 0 for i in sel)

    qtd_pagas, total_pago = soma('PAGA')
    qtd_pend, total_pend = soma('EM PAGAMENTO')
    qtd_dev, _ = soma('DEVOLVIDA')
    return {
        'lote': dict(lote), 'itens': itens,
        'qtd': len(itens), 'total': sum(i['valor'] or 0 for i in itens),
        'qtd_pagas': qtd_pagas, 'total_pago': total_pago,
        'qtd_pendentes': qtd_pend, 'total_pendente': total_pend,
        'qtd_devolvidas': qtd_dev,
    }


def listar(db, status=''):
    """Lotes, do mais novo para o mais antigo. status: 'ABERTO', 'CONCLUIDO' ou '' (todos)."""
    where, params = '1=1', []
    if status:
        where, params = 'l.status=?', [status]
    return [dict(r) for r in db.execute(
        "SELECT l.*, COUNT(i.id) AS qtd, COALESCE(SUM(c.valor),0) AS total, "
        "SUM(CASE WHEN i.situacao='EM PAGAMENTO' THEN 1 ELSE 0 END) AS pendentes, "
        "SUM(CASE WHEN i.situacao='PAGA' THEN 1 ELSE 0 END) AS pagas, "
        "SUM(CASE WHEN i.situacao='DEVOLVIDA' THEN 1 ELSE 0 END) AS devolvidas "
        'FROM contas_lotes l LEFT JOIN contas_lote_itens i ON i.lote_id=l.id '
        'LEFT JOIN contas c ON c.id=i.conta_id WHERE %s GROUP BY l.id ORDER BY l.id DESC' % where, params).fetchall()]


def quitar(db, lote_id, conta_ids, usuario, data_pagamento, forma_pagamento=None, banco=None):
    """Quita as contas pendentes do lote (conta_ids=None quita todas). Devolve quantas foram quitadas."""
    lote = db.execute('SELECT banco FROM contas_lotes WHERE id=?', (lote_id,)).fetchone()
    if not lote:
        raise ErroLote('Lote de pagamento não encontrado.')
    banco_final = banco or lote['banco']
    ids = _pendentes(db, lote_id, conta_ids)
    agora_ = agora()
    for cid in ids:
        db.execute("UPDATE contas SET status='PAGO', banco_pagamento=?, data_pagamento=?, forma_pagamento=?, quitado_por=? "
                   'WHERE id=?', (banco_final, data_pagamento, forma_pagamento, usuario, cid))
        db.execute("UPDATE contas_lote_itens SET situacao='PAGA', atualizado_em=?, atualizado_por=? "
                   'WHERE lote_id=? AND conta_id=?', (agora_, usuario, lote_id, cid))
    _atualizar_status(db, lote_id)
    return len(ids)


def devolver(db, lote_id, conta_ids, usuario):
    """Devolve as contas pendentes do lote para a lista normal de contas. Devolve quantas foram devolvidas."""
    ids = _pendentes(db, lote_id, conta_ids)
    agora_ = agora()
    for cid in ids:
        db.execute("UPDATE contas_lote_itens SET situacao='DEVOLVIDA', atualizado_em=?, atualizado_por=? "
                   'WHERE lote_id=? AND conta_id=?', (agora_, usuario, lote_id, cid))
        db.execute('UPDATE contas SET lote_id=NULL WHERE id=? AND lote_id=?', (cid, lote_id))
    _atualizar_status(db, lote_id)
    return len(ids)


def ao_reabrir(db, conta_id, usuario):
    """Conta de lote reaberta: sai do lote e volta para a lista normal."""
    linha = db.execute('SELECT lote_id FROM contas WHERE id=?', (conta_id,)).fetchone()
    if not linha or linha['lote_id'] is None:
        return
    lote_id = linha['lote_id']
    db.execute("UPDATE contas_lote_itens SET situacao='DEVOLVIDA', atualizado_em=?, atualizado_por=? "
               'WHERE lote_id=? AND conta_id=?', (agora(), usuario, lote_id, conta_id))
    db.execute('UPDATE contas SET lote_id=NULL WHERE id=?', (conta_id,))
    _atualizar_status(db, lote_id)


def ao_excluir(db, conta_id):
    """Conta excluída: apaga os itens dela nos lotes e atualiza o status desses lotes."""
    lotes = [r[0] for r in db.execute('SELECT DISTINCT lote_id FROM contas_lote_itens WHERE conta_id=?',
                                      (conta_id,)).fetchall()]
    db.execute('DELETE FROM contas_lote_itens WHERE conta_id=?', (conta_id,))
    for lote_id in lotes:
        _atualizar_status(db, lote_id)
