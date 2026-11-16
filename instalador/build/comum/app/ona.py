"""Relatório ONA (Organização Nacional de Acreditação): indicadores calculados a partir dos dados que o sistema guarda.

Cada indicador mostra numerador, denominador e percentual, para o período escolhido. Os itens são os que o sistema
consegue medir hoje (identificação do paciente, completude do registro, cadastro, prazo de laudo, comparecimento e
produção por exame, convênio e sexo). A lista oficial de indicadores deve ser conferida com o manual da ONA vigente.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from . import agenda as ag
from . import prazo_laudo

PRAZO_LAUDO_HORAS = 24


def _pct(n, d):
    return round(100.0 * n / d, 1) if d else None


def _linha(nome, criterio, n, d):
    return {'nome': nome, 'criterio': criterio, 'numerador': n, 'denominador': d, 'percentual': _pct(n, d)}


def _horas_entre(inicio, fim):
    return (fim - inicio).total_seconds() / 3600


def indicadores(db, de, ate):
    """Dicionário com os indicadores do período (de e ate são datas)."""
    ini, fim = de.isoformat(), ate.isoformat()
    exames = db.execute("""SELECT r.id, r.data, r.hora_exame, r.paciente, r.data_nasc, r.convenio, r.medico, r.cid,
            r.exame, r.cliente_id, r.laudo_liberado_em, r.laudo_retificado_em, c.cpf, c.sexo AS sexo_cliente
        FROM realizacoes r LEFT JOIN clientes c ON c.id=r.cliente_id
        WHERE r.data BETWEEN ? AND ?""", (ini, fim)).fetchall()
    total = len(exames)

    identificado = sum(1 for e in exames if (e['paciente'] or '').strip() and e['data_nasc'])
    completo = sum(1 for e in exames if e['convenio'] and e['medico'] and e['data'] and e['hora_exame'])
    com_cpf = sum(1 for e in exames if e['cliente_id'] and (e['cpf'] or '').strip())
    com_sexo = sum(1 for e in exames if e['cliente_id'] and e['sexo_cliente'] in ('M', 'F'))

    # prazo de entrega do laudo: o que a gerência definiu (padrão: 24 h após o horário do exame)
    cfg = prazo_laudo.atuais(db)
    liberados = [e for e in exames if e['laudo_liberado_em'] and e['hora_exame']]
    no_prazo = 0
    for e in liberados:
        inicio = datetime.fromisoformat('%s %s:00' % (e['data'], e['hora_exame']))
        liberado = datetime.fromisoformat(e['laudo_liberado_em'][:19])
        if inicio <= liberado <= prazo_laudo.limite(inicio, cfg):
            no_prazo += 1

    entregues_n = sum(1 for e in exames if e['laudo_liberado_em'])
    retificados = sum(1 for e in exames if e['laudo_retificado_em'])

    # comparecimento (agenda): quem veio entre os que estavam marcados
    geral = ag.relatorio(db, de, ate)['geral']
    marcados = geral['marcados']
    vieram = geral['VEIO']

    por_exame, por_convenio, por_sexo = {}, {}, {}
    for e in exames:
        por_exame[e['exame'] or '—'] = por_exame.get(e['exame'] or '—', 0) + 1
        por_convenio[e['convenio'] or '—'] = por_convenio.get(e['convenio'] or '—', 0) + 1
        rotulo_sexo = {'M': 'Masculino', 'F': 'Feminino'}.get(e['sexo_cliente'], 'Não informado')
        por_sexo[rotulo_sexo] = por_sexo.get(rotulo_sexo, 0) + 1

    return {
        'de': ini, 'ate': fim, 'total_exames': total,
        'indicadores': [
            _linha('Identificação do paciente', 'exames com nome e data de nascimento', identificado, total),
            _linha('Registro completo do exame', 'exames com convênio, médico solicitante, data e hora', completo, total),
            _linha('Cadastro com CPF', 'exames de clientes cadastrados com CPF', com_cpf, total),
            _linha('Cadastro com sexo informado', 'exames de clientes cadastrados com sexo', com_sexo, total),
            _linha('Laudo entregue no prazo', 'laudos liberados em até %s após o exame' % prazo_laudo.descricao(cfg),
                   no_prazo, len(liberados)),
            _linha('Laudos retificados', 'laudos corrigidos depois de liberados (menor é melhor)', retificados, entregues_n),
            _linha('Comparecimento na agenda', 'pacientes que vieram entre os marcados', vieram, marcados),
        ],
        'por_exame': sorted(por_exame.items(), key=lambda kv: (-kv[1], kv[0])),
        'por_convenio': sorted(por_convenio.items(), key=lambda kv: (-kv[1], kv[0])),
        'por_sexo': sorted(por_sexo.items(), key=lambda kv: (-kv[1], kv[0])),
    }
