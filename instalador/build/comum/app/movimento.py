"""Movimento de caixa: abertura e fechamento diário por usuário, recebimentos com quitação, troco e relatório.

Regras:
- Cada usuário abre o próprio caixa do dia e o fecha no fim. Enquanto tiver um caixa aberto de outra data,
  não pode abrir o de hoje nem lançar recebimentos: precisa fechar o caixa antigo primeiro.
- Recebimento: forma DINHEIRO ou PIX e número da nota fiscal emitida. Em dinheiro, informa-se o valor entregue
  e o sistema calcula o troco.
- Caixa fechado não se altera: só a administração e a gerência podem corrigi-lo.
"""
from __future__ import annotations

from . import avisos, util
from .db import agora

FORMAS = ('DINHEIRO', 'PIX')


class ErroCaixa(ValueError):
    """Erro de validação mostrado ao usuário."""


def _fmt(d):
    return '%s/%s' % (d[8:10], d[5:7])


def sessao_aberta(db, usuario):
    return db.execute("SELECT * FROM caixa_sessoes WHERE usuario=? AND status='ABERTO' ORDER BY data LIMIT 1", (usuario,)).fetchone()


def sessao_de_hoje(db, usuario, hoje):
    return db.execute('SELECT * FROM caixa_sessoes WHERE usuario=? AND data=?', (usuario, hoje)).fetchone()


def alertar(db, usuario_id, sessao, hoje):
    """Avisa pelo contato do sistema que o caixa de outra data continua aberto (uma vez por dia)."""
    if sessao['alertado_em'] == hoje:
        return False
    de = avisos.sistema_id(db)
    if de is not None:
        corpo = ('Atenção: o seu caixa de %s ainda está aberto. Feche o caixa antes de abrir o de hoje ou de lançar recebimentos.'
                 % _fmt(sessao['data']))
        db.execute('INSERT INTO chat_mensagens (de_id, para_id, corpo, criado_em) VALUES (?,?,?,?)', (de, usuario_id, corpo, agora()))
    db.execute('UPDATE caixa_sessoes SET alertado_em=? WHERE id=?', (hoje, sessao['id']))
    db.commit()
    return True


def alertar_caixas_abertos(db, hoje):
    """Caixas abertos de dias anteriores: avisa o dono (rotina de hora em hora e ao tentar lançar)."""
    n = 0
    for s in db.execute("SELECT s.*, u.id AS uid FROM caixa_sessoes s JOIN usuarios u ON u.usuario=s.usuario "
                        "WHERE s.status='ABERTO' AND s.data<?", (hoje,)).fetchall():
        if alertar(db, s['uid'], s, hoje):
            n += 1
    return n


HORA_LEMBRETE = 17  # a partir das 17h, o aviso lembra quem ainda está com o caixa aberto


def lembrar_fechamento(db, agora_dt):
    """Às 17h (ou depois), envia pelo contato do sistema o lembrete de fechar o caixa. Uma vez por dia e por caixa."""
    if agora_dt.hour < HORA_LEMBRETE:
        return 0
    hoje = agora_dt.date().isoformat()
    de = avisos.sistema_id(db)
    n = 0
    for s in db.execute("SELECT s.*, u.id AS uid FROM caixa_sessoes s JOIN usuarios u ON u.usuario=s.usuario WHERE s.status='ABERTO'").fetchall():
        if s['lembrado_em'] == hoje:
            continue
        if de is not None:
            corpo = ('Lembrete das 17h: o seu caixa de %s ainda está aberto. Feche o caixa para gerar o relatório de assinatura.'
                     % _fmt(s['data']))
            db.execute('INSERT INTO chat_mensagens (de_id, para_id, corpo, criado_em) VALUES (?,?,?,?)', (de, s['uid'], corpo, agora()))
        db.execute('UPDATE caixa_sessoes SET lembrado_em=? WHERE id=?', (hoje, s['id']))
        n += 1
    db.commit()
    return n


def abrir(db, usuario, usuario_id, fundo, hoje):
    aberta = sessao_aberta(db, usuario)
    if aberta and aberta['data'] != hoje:
        alertar(db, usuario_id, aberta, hoje)
        raise ErroCaixa('Você tem o caixa de %s aberto. Feche-o antes de abrir o caixa de hoje.' % _fmt(aberta['data']))
    if aberta:
        raise ErroCaixa('O seu caixa de hoje já está aberto.')
    if sessao_de_hoje(db, usuario, hoje):
        raise ErroCaixa('O caixa de hoje já foi aberto e fechado. Procure a gerência para uma correção.')
    cur = db.execute("INSERT INTO caixa_sessoes (usuario, data, fundo, status, aberto_em) VALUES (?,?,?, 'ABERTO', ?)",
                     (usuario, hoje, fundo, agora()))
    db.commit()
    return cur.lastrowid


def fechar(db, usuario, sessao_id):
    s = db.execute('SELECT * FROM caixa_sessoes WHERE id=?', (sessao_id,)).fetchone()
    if not s or s['usuario'] != usuario or s['status'] != 'ABERTO':
        raise ErroCaixa('Este caixa não está aberto para o seu usuário.')
    db.execute("UPDATE caixa_sessoes SET status='FECHADO', fechado_em=?, fechado_por=? WHERE id=?", (agora(), usuario, sessao_id))
    db.commit()
    return sessao_id


def reabrir(db, privilegiado, sessao_id):
    """Reabre um caixa fechado sem querer. Só a administração e a gerência. O dono precisa estar sem outro caixa aberto."""
    if not privilegiado:
        raise ErroCaixa('Só a administração ou a gerência pode reabrir um caixa fechado.')
    s = db.execute('SELECT * FROM caixa_sessoes WHERE id=?', (sessao_id,)).fetchone()
    if not s:
        raise ErroCaixa('Este caixa não existe mais. Atualize a página.')
    if s['status'] != 'FECHADO':
        raise ErroCaixa('Este caixa já está aberto.')
    outra = db.execute("SELECT data FROM caixa_sessoes WHERE usuario=? AND status='ABERTO' AND id<>?", (s['usuario'], sessao_id)).fetchone()
    if outra:
        raise ErroCaixa('%s já tem o caixa de %s aberto. Feche-o antes de reabrir este.' % (s['usuario'], _fmt(outra['data'])))
    db.execute("UPDATE caixa_sessoes SET status='ABERTO', fechado_em=NULL, fechado_por=NULL WHERE id=?", (sessao_id,))
    db.commit()
    return dict(s)


def _sessao_para_lancar(db, usuario, usuario_id, hoje):
    aberta = sessao_aberta(db, usuario)
    if aberta and aberta['data'] != hoje:
        alertar(db, usuario_id, aberta, hoje)
        raise ErroCaixa('Você tem o caixa de %s aberto. Feche-o antes de lançar recebimentos.' % _fmt(aberta['data']))
    if not aberta:
        raise ErroCaixa('Abra o seu caixa de hoje antes de receber.')
    return aberta


def pendentes(db, usuario=None, privilegiado=True, dia=None, todos_usuarios=None):
    """Lançamentos que vão para o caixa e ainda não foram recebidos.
    `dia` (AAAA-MM-DD) limita ao dia do atendimento; sem ele, vêm de todas as datas.
    Cada pessoa vê só o que ela mesma lançou (mais os antigos sem dono). `todos_usuarios` (só para quem é privilegiado)
    mostra os de todos, para conferir e excluir; sem informar, mantém o comportamento antigo (privilegiado vê todos)."""
    if todos_usuarios is None:
        todos_usuarios = privilegiado
    sql, params = "SELECT * FROM caixa WHERE status='ABERTO'", []
    if dia:
        sql += ' AND data=?'
        params.append(dia)
    if not ((privilegiado and todos_usuarios) or usuario is None):
        sql += " AND (UPPER(usuario)=UPPER(?) OR COALESCE(usuario,'')='')"
        params.append(usuario)
    return [dict(r) for r in db.execute(sql + ' ORDER BY data, id', params)]


def pode_receber(row, usuario):
    """Só quem lançou o atendimento recebe o valor (lançamentos antigos sem dono podem ser recebidos por qualquer um)."""
    dono = (row['usuario'] or '').strip()
    return not dono or dono.upper() == (usuario or '').strip().upper()


def _valores_recebimento(valor, forma, valor_recebido, nf, forma2='', valor2=None):
    """Valida o recebimento. Com `forma2`, o pagamento é dividido em duas formas: `valor2` é a parte paga na segunda forma e
    o resto, na primeira. `valor_recebido` é o que o cliente entregou em dinheiro (se houver parte em dinheiro).
    Devolve (recebido, troco, nf, forma2, valor2); `recebido` é o total entregue (dinheiro entregue + parte em PIX)."""
    if forma not in FORMAS:
        raise ErroCaixa('Escolha a forma de pagamento: dinheiro ou PIX.')
    nf = (nf or '').strip()
    if not nf:
        raise ErroCaixa('Informe o número da nota fiscal emitida.')
    if valor is None or valor <= 0:
        raise ErroCaixa('Informe o valor a receber.')
    forma2 = (forma2 or '').strip()
    if forma2:
        if forma2 not in FORMAS or forma2 == forma:
            raise ErroCaixa('Para dividir o pagamento, a segunda forma precisa ser diferente da primeira (dinheiro e PIX).')
        if valor2 is None or valor2 <= 0 or round(valor2, 2) >= round(valor, 2):
            raise ErroCaixa('Informe quanto será pago na segunda forma: um valor maior que zero e menor que o total.')
        valor2 = round(valor2, 2)
        parte = {forma: round(valor - valor2, 2), forma2: valor2}
    else:
        valor2 = None
        parte = {forma: round(valor, 2)}
    pix = parte.get('PIX', 0.0)
    if 'DINHEIRO' in parte:
        entregue = valor_recebido if valor_recebido is not None else parte['DINHEIRO']
        if entregue < parte['DINHEIRO']:
            raise ErroCaixa('O valor entregue em dinheiro é menor que a parte a receber em dinheiro.')
        troco = round(entregue - parte['DINHEIRO'], 2)
        recebido = round(entregue + pix, 2)
    else:
        recebido, troco = round(valor, 2), 0.0
    return recebido, troco, nf, (forma2 or None), valor2


def receber(db, usuario, usuario_id, caixa_id, valor, forma, valor_recebido, nf, hoje, forma2='', valor2=None):
    sessao = _sessao_para_lancar(db, usuario, usuario_id, hoje)
    row = db.execute('SELECT * FROM caixa WHERE id=?', (caixa_id,)).fetchone()
    if not row or row['status'] != 'ABERTO':
        raise ErroCaixa('Este lançamento já foi recebido ou não existe mais. Atualize a página.')
    if not pode_receber(row, usuario):
        raise ErroCaixa('Este atendimento foi lançado por %s. Só quem lançou pode receber o valor.' % row['usuario'])
    v = util.para_valor(valor) if valor not in (None, '') else row['valor']
    recebido, troco, nf, forma2, valor2 = _valores_recebimento(v, forma, valor_recebido, nf, forma2, valor2)
    db.execute("UPDATE caixa SET valor=?, status='PAGO', forma_pagamento=?, forma_pagamento2=?, valor_pagamento2=?, nota_fiscal=?, "
               'valor_recebido=?, troco=?, sessao_id=?, pago_em=?, recebido_por=?, editado_por=? WHERE id=?',
               (round(v, 2), forma, forma2, valor2, nf, recebido, troco, sessao['id'], agora(), usuario, usuario, caixa_id))
    db.commit()
    return {'troco': troco, 'recebido': recebido}


def pode_editar(db, usuario, privilegiado, caixa_row):
    """Caixa fechado só muda pela administração ou pela gerência. Caixa aberto muda pelo próprio usuário."""
    if not caixa_row['sessao_id']:
        return True
    s = db.execute('SELECT * FROM caixa_sessoes WHERE id=?', (caixa_row['sessao_id'],)).fetchone()
    if s is None:
        return True
    if s['status'] == 'FECHADO':
        return privilegiado
    return s['usuario'] == usuario or privilegiado


def editar_recebimento(db, usuario, privilegiado, caixa_id, valor, forma, valor_recebido, nf, obs, forma2='', valor2=None):
    row = db.execute('SELECT * FROM caixa WHERE id=?', (caixa_id,)).fetchone()
    if not row or row['status'] != 'PAGO':
        raise ErroCaixa('Só recebimentos já feitos podem ser corrigidos aqui.')
    if not pode_editar(db, usuario, privilegiado, row):
        raise ErroCaixa('Este caixa já foi fechado. Só a administração ou a gerência pode corrigi-lo.')
    v = util.para_valor(valor) if valor not in (None, '') else row['valor']
    recebido, troco, nf, forma2, valor2 = _valores_recebimento(v, forma, valor_recebido, nf, forma2, valor2)
    db.execute('UPDATE caixa SET valor=?, forma_pagamento=?, forma_pagamento2=?, valor_pagamento2=?, nota_fiscal=?, valor_recebido=?, '
               'troco=?, obs=?, editado_por=? WHERE id=?',
               (round(v, 2), forma, forma2, valor2, nf, recebido, troco, (obs or '').strip() or None, usuario, caixa_id))
    db.commit()


def excluir_lancamento(db, privilegiado, caixa_id):
    """Exclui um lançamento do movimento de caixa (a receber ou já recebido). Só a administração e a gerência."""
    if not privilegiado:
        raise ErroCaixa('Só a gerência pode excluir lançamentos do movimento de caixa.')
    row = db.execute('SELECT * FROM caixa WHERE id=?', (caixa_id,)).fetchone()
    if not row:
        raise ErroCaixa('Este lançamento não existe mais. Atualize a página.')
    db.execute('DELETE FROM caixa WHERE id=?', (caixa_id,))
    db.commit()
    return dict(row)


def excluir_varios(db, privilegiado, ids=()):
    """Exclui vários lançamentos de uma vez (só administração e gerência). Quem escolhe a lista é a tela."""
    if not privilegiado:
        raise ErroCaixa('Só a gerência pode excluir lançamentos do movimento de caixa.')
    ids = sorted({int(i) for i in ids})
    if not ids:
        raise ErroCaixa('Nenhum lançamento selecionado.')
    marcas = ','.join('?' * len(ids))
    existentes = [r[0] for r in db.execute('SELECT id FROM caixa WHERE id IN (%s)' % marcas, ids)]
    if not existentes:
        raise ErroCaixa('Os lançamentos selecionados não existem mais. Atualize a página.')
    db.execute('DELETE FROM caixa WHERE id IN (%s)' % ','.join('?' * len(existentes)), existentes)
    db.commit()
    return {'qtd': len(existentes), 'ids': existentes}


def recebimentos_recentes(db, limite=100, usuario=None, dia=None):
    """Últimos recebimentos, para a gerência conferir e, se preciso, excluir. `usuario` limita a quem recebeu e `dia`
    (AAAA-MM-DD), ao dia do recebimento; sem eles, vêm os de todos os caixas."""
    sql, params = ("SELECT c.*, s.data AS caixa_data FROM caixa c LEFT JOIN caixa_sessoes s ON s.id=c.sessao_id "
                   "WHERE c.status='PAGO'"), []
    if usuario:
        sql += ' AND UPPER(c.recebido_por)=UPPER(?)'
        params.append(usuario)
    if dia:
        sql += ' AND substr(c.pago_em,1,10)=?'
        params.append(dia)
    return [dict(r) for r in db.execute(sql + ' ORDER BY c.pago_em DESC, c.id DESC LIMIT ?', params + [limite])]


def formas_texto(r):
    """"DINHEIRO", "PIX" ou "DINHEIRO + PIX" (pagamento dividido) de um lançamento."""
    segunda = r.get('forma_pagamento2')
    return '%s + %s' % (r.get('forma_pagamento') or '', segunda) if segunda else (r.get('forma_pagamento') or '')


def _partes(item):
    """Divide um recebimento em partes (forma, item com o valor daquela parte). Sem divisão, é uma parte só."""
    if not item.get('forma_pagamento2'):
        return [(item['forma_pagamento'], item)]
    v2 = item['valor_pagamento2'] or 0
    v1 = round((item['valor'] or 0) - v2, 2)
    valores = {item['forma_pagamento']: v1, item['forma_pagamento2']: v2}
    pix = valores.get('PIX', 0)
    partes = []
    if 'DINHEIRO' in valores:
        partes.append(('DINHEIRO', dict(item, valor=valores['DINHEIRO'], valor_recebido=round((item['valor_recebido'] or 0) - pix, 2))))
    if 'PIX' in valores:
        partes.append(('PIX', dict(item, valor=pix, valor_recebido=pix, troco=0.0)))
    return partes


def relatorio(db, sessao_id):
    """Dados do relatório para assinatura: dinheiro (com troco) e PIX separados, e o que deve haver no caixa."""
    s = db.execute('SELECT * FROM caixa_sessoes WHERE id=?', (sessao_id,)).fetchone()
    if not s:
        raise ErroCaixa('Este caixa não existe mais.')
    itens = [dict(r) for r in db.execute("SELECT * FROM caixa WHERE sessao_id=? AND status='PAGO' ORDER BY pago_em, id", (sessao_id,))]
    partes = [p for i in itens for p in _partes(i)]   # pagamento dividido entra em dinheiro e em PIX, cada um com a sua parte
    dinheiro = [p for f, p in partes if f == 'DINHEIRO']
    pix = [p for f, p in partes if f == 'PIX']
    din_devido = round(sum(i['valor'] or 0 for i in dinheiro), 2)
    din_recebido = round(sum(i['valor_recebido'] or 0 for i in dinheiro), 2)
    troco = round(sum(i['troco'] or 0 for i in dinheiro), 2)
    liquido = round(din_recebido - troco, 2)
    pix_total = round(sum(i['valor'] or 0 for i in pix), 2)
    return {'sessao': dict(s), 'dinheiro': dinheiro, 'pix': pix,
            'dinheiro_devido': din_devido, 'dinheiro_recebido': din_recebido, 'troco': troco, 'dinheiro_liquido': liquido,
            'pix_total': pix_total, 'total': round(din_devido + pix_total, 2), 'fundo': s['fundo'] or 0,
            'esperado_dinheiro': round((s['fundo'] or 0) + liquido, 2), 'quantidade': len(itens)}


def quitacao(db, caixa_id):
    r = db.execute("SELECT * FROM caixa WHERE id=? AND status='PAGO'", (caixa_id,)).fetchone()
    if not r:
        raise ErroCaixa('Este recebimento não existe ou ainda não foi feito.')
    return dict(r)


def pode_privilegiado(u, modulos_usuario):
    return bool(u['admin']) or 'gerencia' in modulos_usuario

