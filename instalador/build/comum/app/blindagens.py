"""Controle de blindagens (geradores de tecnécio): cadastro, validade e solicitação de devolução."""
from __future__ import annotations

import re
from datetime import date

from . import util
from .db import agora

VALIDO = 'VÁLIDO'
VENCIDO = 'VENCIDO'
DEVOLUCAO = 'DEVOLUÇÃO SOLICITADA'
DEVOLVIDA = 'DEVOLVIDA'
STATUS = (VALIDO, VENCIDO, DEVOLUCAO, DEVOLVIDA)
# Status que não podem mais ser editadas nem excluídas (já fazem parte de uma solicitação)
TRAVADAS = (DEVOLUCAO, DEVOLVIDA)


class ErroBlindagem(ValueError):
    """Erro de validação mostrado ao usuário."""


def atualizar_status(db):
    """VÁLIDO vira VENCIDO quando a validade passa (e volta a VÁLIDO se a validade for corrigida para o futuro).
    Blindagens com devolução solicitada nunca mudam sozinhas."""
    hoje = date.today().isoformat()
    a = db.execute("UPDATE blindagens SET status=? WHERE status=? AND validade<?", (VENCIDO, VALIDO, hoje)).rowcount
    b = db.execute("UPDATE blindagens SET status=? WHERE status=? AND validade>=?", (VALIDO, VENCIDO, hoje)).rowcount
    if a or b:
        db.commit()
    return a + b


def validar(f, db, bid=None):
    """Valida o formulário e devolve (dados normalizados, lista de erros)."""
    erros = []
    lote = re.sub(r'\s+', '', f.get('lote') or '').upper()
    if not lote:
        erros.append('Informe o lote.')
    elif not re.fullmatch(r'[A-Z0-9]+', lote):
        erros.append('O lote aceita somente letras e números (sem espaços, hífens ou símbolos).')
    elif len(lote) > 30:
        erros.append('O lote pode ter no máximo 30 caracteres.')
    nota = (f.get('nota_fiscal') or '').strip()
    if not nota:
        erros.append('Informe a nota fiscal.')
    elif len(nota) > 20:
        erros.append('A nota fiscal pode ter no máximo 20 caracteres.')
    serie = (f.get('serie') or '').strip().upper()
    if not serie:
        erros.append('Informe a série.')
    elif len(serie) > 10:
        erros.append('A série pode ter no máximo 10 caracteres.')
    data_nota = util.para_data(f.get('data_nota'))
    if not data_nota:
        erros.append('Informe a data da nota fiscal.')
    cfop = re.sub(r'\D', '', f.get('cfop') or '')
    if not cfop:
        erros.append('Informe o CFOP.')
    elif len(cfop) != 4:
        erros.append('O CFOP tem 4 dígitos (exemplo: 5949).')
    validade = util.para_data(f.get('validade'))
    if not validade:
        erros.append('Informe a validade.')
    elif data_nota and validade < data_nota:
        erros.append('A validade não pode ser anterior à data da nota fiscal.')
    if lote and not erros:
        igual = db.execute('SELECT id FROM blindagens WHERE lote=? AND id IS NOT ?', (lote, bid)).fetchone()
        if igual:
            erros.append('Já existe uma blindagem cadastrada com o lote %s.' % lote)
    dados = {'lote': lote, 'nota_fiscal': nota, 'serie': serie, 'cfop': cfop,
             'data_nota': data_nota.isoformat() if data_nota else '', 'validade': validade.isoformat() if validade else ''}
    return dados, erros


def criar(db, dados, usuario):
    cur = db.execute(
        'INSERT INTO blindagens (lote, nota_fiscal, serie, data_nota, cfop, validade, status, criado_por, criado_em) '
        'VALUES (?,?,?,?,?,?,?,?,?)', (dados['lote'], dados['nota_fiscal'], dados['serie'], dados['data_nota'], dados['cfop'],
                                       dados['validade'], VALIDO, usuario, agora()))
    db.commit()
    atualizar_status(db)
    return cur.lastrowid


def atualizar(db, bid, dados, usuario):
    db.execute('UPDATE blindagens SET lote=?, nota_fiscal=?, serie=?, data_nota=?, cfop=?, validade=?, atualizado_por=?, '
               'atualizado_em=? WHERE id=?', (dados['lote'], dados['nota_fiscal'], dados['serie'], dados['data_nota'],
                                              dados['cfop'], dados['validade'], usuario, agora(), bid))
    db.commit()
    atualizar_status(db)


def listar(db, status='', busca=''):
    onde, params = ['1=1'], []
    if status in STATUS:
        onde.append('status=?')
        params.append(status)
    busca = (busca or '').strip()
    if busca:
        onde.append('(lote LIKE ? OR nota_fiscal LIKE ?)')
        params += ['%' + busca + '%'] * 2
    return db.execute('SELECT * FROM blindagens WHERE %s ORDER BY validade, lote' % ' AND '.join(onde), params).fetchall()


def contagem(db):
    base = {s: 0 for s in STATUS}
    for r in db.execute('SELECT status, COUNT(*) AS n FROM blindagens GROUP BY status'):
        base[r['status']] = r['n']
    return base


def solicitar_devolucao(db, ids, valor_unitario, usuario):
    """Marca as blindagens vencidas como 'devolução solicitada' e registra a solicitação. Devolve o id da solicitação."""
    ids = sorted({int(i) for i in ids})
    if not ids:
        raise ErroBlindagem('Marque ao menos uma blindagem vencida.')
    marcas = ','.join('?' * len(ids))
    linhas = db.execute('SELECT id, lote, status FROM blindagens WHERE id IN (%s)' % marcas, ids).fetchall()
    if len(linhas) != len(ids):
        raise ErroBlindagem('Alguma blindagem marcada não existe mais. Atualize a página.')
    nao = [r['lote'] for r in linhas if r['status'] != VENCIDO]
    if nao:
        raise ErroBlindagem('Só é possível solicitar a devolução de blindagens vencidas. Fora dessa condição: %s.' % ', '.join(nao))
    cur = db.execute('INSERT INTO blindagem_devolucoes (criado_em, criado_por, valor_unitario) VALUES (?,?,?)',
                     (agora(), usuario, valor_unitario))
    did = cur.lastrowid
    db.execute('UPDATE blindagens SET status=?, devolucao_id=? WHERE id IN (%s)' % marcas, [DEVOLUCAO, did] + ids)
    db.commit()
    return did


def pendentes_devolvida(db):
    """Blindagens com devolução solicitada que ainda aguardam a data da devolução."""
    return db.execute('SELECT b.*, d.criado_em AS solicitado_em FROM blindagens b '
                      'LEFT JOIN blindagem_devolucoes d ON d.id=b.devolucao_id '
                      'WHERE b.status=? ORDER BY b.validade, b.lote', (DEVOLUCAO,)).fetchall()


def registrar_devolvidas(db, ids, data_devolvida, usuario):
    """Marca as blindagens com devolução solicitada como DEVOLVIDA na data informada pelo usuário."""
    ids = sorted({int(i) for i in ids})
    if not ids:
        raise ErroBlindagem('Marque ao menos uma blindagem com devolução solicitada.')
    if not data_devolvida:
        raise ErroBlindagem('Informe a data em que a blindagem foi devolvida.')
    if data_devolvida > date.today():
        raise ErroBlindagem('A data da devolução não pode ser futura.')
    marcas = ','.join('?' * len(ids))
    linhas = db.execute('SELECT b.id, b.lote, b.status, d.criado_em AS solicitado_em FROM blindagens b '
                        'LEFT JOIN blindagem_devolucoes d ON d.id=b.devolucao_id WHERE b.id IN (%s)' % marcas, ids).fetchall()
    if len(linhas) != len(ids):
        raise ErroBlindagem('Alguma blindagem marcada não existe mais. Atualize a página.')
    nao = [r['lote'] for r in linhas if r['status'] != DEVOLUCAO]
    if nao:
        raise ErroBlindagem('Só é possível confirmar a devolução de blindagens com devolução solicitada. Fora dessa condição: %s.'
                            % ', '.join(nao))
    antes = [r['lote'] for r in linhas if r['solicitado_em'] and data_devolvida.isoformat() < r['solicitado_em'][:10]]
    if antes:
        raise ErroBlindagem('A data da devolução não pode ser anterior à solicitação: %s.' % ', '.join(antes))
    db.execute('UPDATE blindagens SET status=?, devolvida_em=?, devolvida_por=? WHERE id IN (%s)' % marcas,
               [DEVOLVIDA, data_devolvida.isoformat(), usuario] + ids)
    db.commit()
    return len(ids)


def devolucao(db, did):
    cab = db.execute('SELECT * FROM blindagem_devolucoes WHERE id=?', (did,)).fetchone()
    if not cab:
        return None, []
    itens = db.execute('SELECT * FROM blindagens WHERE devolucao_id=? ORDER BY id', (did,)).fetchall()
    return cab, itens
