"""Ocorrências informadas pelo funcionário e conferidas pela gerência no fechamento."""
import json
import re
from datetime import date

from . import core

TIPOS = {'esquecimento': 'Esquecimento de batida', 'batida_errada': 'Batida errada', 'outro': 'Outro'}
STATUS = ('PENDENTE', 'APROVADA', 'CORRIGIDA', 'RECUSADA')


def _horarios(valor):
    return core._validate_punches([p for p in re.split(r'[,;\s]+', str(valor or '').strip()) if p])


def listar(conn, employee_id=None, pendentes=False):
    filtros, parametros = [], []
    if employee_id is not None:
        filtros.append('o.employee_id=?')
        parametros.append(employee_id)
    if pendentes:
        filtros.append("o.status='PENDENTE'")
    consulta = 'SELECT o.*,e.name FROM bh_ocorrencias o JOIN bh_employees e ON e.id=o.employee_id'
    if filtros:
        consulta += ' WHERE ' + ' AND '.join(filtros)
    resultado = []
    for registro in conn.execute(consulta + ' ORDER BY o.data DESC,o.id DESC', parametros):
        item = dict(registro)
        item['horarios'] = json.loads(item['horarios_json'])
        item['tipo_label'] = TIPOS.get(item['tipo'], item['tipo'])
        resultado.append(item)
    return resultado


def criar(conn, employee_id, data, tipo, horarios, observacao, ator):
    funcionario = core.get_employee(conn, employee_id)
    data = core._date(data)
    if funcionario['is_intern'] or not funcionario['active']:
        raise ValueError('O funcionário deve ter vínculo ativo com acompanhamento de ponto.')
    if not core._within_employment(funcionario, data) or data > date.today().isoformat():
        raise ValueError('Informe uma data dentro do vínculo, até o dia de hoje.')
    if tipo not in TIPOS:
        raise ValueError('Selecione um tipo de ocorrência válido.')
    horarios = _horarios(horarios)
    observacao = core._reason(observacao)
    with conn:
        cursor = conn.execute(
            'INSERT INTO bh_ocorrencias (employee_id,data,tipo,horarios_json,observacao,criado_por,criado_em) '
            'VALUES (?,?,?,?,?,?,?)',
            (employee_id, data, tipo, core._json(horarios), observacao, ator, core._now()))
        core.log_audit(conn, ator, 'ocorrencia_criada', observacao, employee_id=employee_id,
                       entity_type='ocorrencia', entity_id=cursor.lastrowid,
                       after={'data': data, 'tipo': tipo, 'horarios': horarios, 'status': 'PENDENTE'})
    return cursor.lastrowid


def tratar(conn, ocorrencia_id, status, horarios, classificacao, parecer, ator):
    if status not in STATUS[1:]:
        raise ValueError('Escolha aprovar, corrigir ou recusar a ocorrência.')
    parecer = core._reason(parecer)
    with conn:
        cursor = conn.execute(
            "UPDATE bh_ocorrencias SET status=?,tratado_por=?,tratado_em=?,parecer=? WHERE id=? AND status='PENDENTE'",
            (status, ator, core._now(), parecer, ocorrencia_id))
        if cursor.rowcount != 1:
            raise ValueError('Ocorrência não encontrada ou já tratada. Recarregue a página.')
        registro = dict(conn.execute('SELECT * FROM bh_ocorrencias WHERE id=?', (ocorrencia_id,)).fetchone())
        batidas = json.loads(registro['horarios_json']) if status == 'APROVADA' else _horarios(horarios) if status == 'CORRIGIDA' else []
        if status != 'RECUSADA':
            if status == 'APROVADA':
                classificacao = 'normal'
            if classificacao == 'normal' and (len(batidas) < 2 or len(batidas) % 2):
                raise ValueError('Informe todas as batidas do dia, em pares de entrada e saída, ou corrija a classificação.')
        core.log_audit(conn, ator, 'ocorrencia_tratada', parecer, employee_id=registro['employee_id'],
                       entity_type='ocorrencia', entity_id=ocorrencia_id,
                       before={'status': 'PENDENTE'},
                       after={'status': status, 'horarios': batidas, 'classificacao': classificacao})
        if status != 'RECUSADA':
            # A correção e o tratamento são confirmados na mesma transação pelo núcleo.
            core.correct_day(conn, registro['employee_id'], registro['data'], batidas, classificacao,
                             f'Ocorrência #{ocorrencia_id}: {parecer}', ator)
