"""Contas a pagar recorrentes: um cadastro gera, todo mês, uma conta em aberto no dia escolhido.

A geração é idempotente: o índice único (recorrente_id, vencimento) impede duplicar a conta de um mês,
mesmo que o gerador rode várias vezes. Contas já geradas não mudam quando a recorrência é editada;
excluir a recorrência não apaga as contas já lançadas.
"""
import calendar
from datetime import date

from . import util
from .db import agora


class ErroRecorrente(Exception):
    pass


def _vencimento(ano, mes, dia):
    """Dia escolhido no mês; se o mês não tem esse dia (31 em fevereiro), vale o último dia do mês."""
    return date(ano, mes, min(dia, calendar.monthrange(ano, mes)[1])).isoformat()


def _mes_seguinte(ano, mes):
    return (ano + 1, 1) if mes == 12 else (ano, mes + 1)


def _gerar_recorrencia(db, r, meses):
    """Cria as contas da recorrência nos meses dados (ano, mes), sem começar antes de mes_inicio. Devolve quantas foram criadas."""
    criadas = 0
    for ano, mes in meses:
        mes_ref = '%04d-%02d' % (ano, mes)
        if mes_ref < r['mes_inicio']:
            continue
        # a chave é (recorrente_id, recorrente_mes): mesmo que o vencimento da conta seja editado, o mês não se repete
        cur = db.execute(
            "INSERT OR IGNORE INTO contas (descricao, categoria, vencimento, valor, obs, fornecedor, fornecedor_id, status, usuario, recorrente_id, recorrente_mes) "
            "VALUES (?,?,?,?,?,?,?,'ABERTO',?,?,?)",
            (r['descricao'], r['categoria'], _vencimento(ano, mes, r['dia_vencimento']), r['valor'], r['obs'],
             r['fornecedor'], r['fornecedor_id'], r['criado_por'], r['id'], mes_ref))
        criadas += cur.rowcount
    return criadas


def gerar(db, hoje=None):
    """Garante as contas do mês de hoje e do mês seguinte de todas as recorrências ativas. Devolve quantas contas foram criadas."""
    hoje = hoje or date.today()
    meses = [(hoje.year, hoje.month), _mes_seguinte(hoje.year, hoje.month)]
    total = 0
    for r in db.execute('SELECT * FROM contas_recorrentes WHERE ativo=1').fetchall():
        total += _gerar_recorrencia(db, r, meses)
    db.commit()
    return total


def validar(d):
    """Confere os campos da recorrência. Devolve o dicionário pronto para gravar."""
    descricao = util.maiusculas((d.get('descricao') or '').strip())
    categoria = (d.get('categoria') or '').strip()
    valor = d.get('valor')
    dia = str(d.get('dia') or '').strip()
    if not descricao or not categoria:
        raise ErroRecorrente('Preencha descrição e categoria.')
    if valor is None or valor <= 0:
        raise ErroRecorrente('Informe um valor maior que zero.')
    if not dia.isdigit() or not 1 <= int(dia) <= 31:
        raise ErroRecorrente('O dia do vencimento deve ser um número de 1 a 31.')
    return {'descricao': descricao, 'categoria': categoria, 'valor': valor, 'dia': int(dia),
            'fornecedor': d.get('fornecedor') or None, 'fornecedor_id': d.get('fornecedor_id'),
            'obs': (d.get('obs') or '').strip() or None}


def listar(db):
    return db.execute('SELECT * FROM contas_recorrentes ORDER BY ativo DESC, descricao, id').fetchall()


def obter(db, rid):
    return db.execute('SELECT * FROM contas_recorrentes WHERE id=?', (rid,)).fetchone()


def salvar(db, d, usuario, primeiro_venc=None, rid=None):
    """Cria (com primeiro_venc, ISO) ou edita (com rid) uma recorrência. Ao criar, gera as contas do mês do primeiro vencimento e do seguinte."""
    f = validar(d)
    if rid:
        cur = db.execute('UPDATE contas_recorrentes SET descricao=?, categoria=?, valor=?, dia_vencimento=?, fornecedor=?, '
                         'fornecedor_id=?, obs=? WHERE id=?',
                         (f['descricao'], f['categoria'], f['valor'], f['dia'], f['fornecedor'], f['fornecedor_id'], f['obs'], rid))
        if not cur.rowcount:
            raise ErroRecorrente('Conta recorrente não encontrada.')
        db.commit()
        return rid
    if not primeiro_venc:
        raise ErroRecorrente('Informe o primeiro vencimento.')
    cur = db.execute('INSERT INTO contas_recorrentes (descricao, categoria, valor, dia_vencimento, fornecedor, fornecedor_id, obs, '
                     'ativo, mes_inicio, criado_em, criado_por) VALUES (?,?,?,?,?,?,?,1,?,?,?)',
                     (f['descricao'], f['categoria'], f['valor'], f['dia'], f['fornecedor'], f['fornecedor_id'], f['obs'],
                      primeiro_venc[:7], agora(), usuario))
    rid = cur.lastrowid
    ano, mes = int(primeiro_venc[:4]), int(primeiro_venc[5:7])
    _gerar_recorrencia(db, obter(db, rid), [(ano, mes), _mes_seguinte(ano, mes)])
    db.commit()
    return rid


def alternar_ativo(db, rid):
    """Pausa ou reativa. Devolve o novo estado (1 ativa, 0 pausada)."""
    if not obter(db, rid):
        raise ErroRecorrente('Conta recorrente não encontrada.')
    db.execute('UPDATE contas_recorrentes SET ativo = 1 - ativo WHERE id=?', (rid,))
    db.commit()
    return obter(db, rid)['ativo']


def excluir(db, rid):
    """Apaga só a recorrência; as contas já geradas continuam lançadas."""
    cur = db.execute('DELETE FROM contas_recorrentes WHERE id=?', (rid,))
    if not cur.rowcount:
        raise ErroRecorrente('Conta recorrente não encontrada.')
    db.commit()
