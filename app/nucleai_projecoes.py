"""Simulações da NucleAI IA: projeções calculadas aqui, em Python, com os dados do sistema.

A IA só escolhe os parâmetros e explica o resultado; os números saem destas funções (nunca do modelo de linguagem).
Método: tendência linear (mínimos quadrados) sobre os meses completos escolhidos, com faixa de incerteza de ±1,96 desvio
dos resíduos. Com menos de 3 meses de histórico, usa a média simples.
"""
from __future__ import annotations

import math
from datetime import date

MESES_MIN, MESES_MAX = 2, 36
FUTURO_MAX = 12
NOMES_MES = ('jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez')


def _somar_meses(ano, mes, n):
    t = ano * 12 + (mes - 1) + n
    return t // 12, t % 12 + 1


def meses_completos(n, hoje=None):
    """Os `n` meses completos antes do mês atual, do mais antigo ao mais novo, como 'AAAA-MM'."""
    hoje = hoje or date.today()
    return ['%04d-%02d' % _somar_meses(hoje.year, hoje.month, -i) for i in range(n, 0, -1)]


def meses_futuros(n, hoje=None, incluir_atual=False):
    hoje = hoje or date.today()
    ini = 0 if incluir_atual else 1
    return ['%04d-%02d' % _somar_meses(hoje.year, hoje.month, i) for i in range(ini, ini + n)]


def rotulo(mes):
    a, m = mes.split('-')
    return '%s/%s' % (NOMES_MES[int(m) - 1], a[2:])


def _limitar(v, minimo, maximo, padrao):
    try:
        v = int(v)
    except (TypeError, ValueError):
        return padrao
    return max(minimo, min(maximo, v))


def tendencia(valores, futuros):
    """Projeção dos próximos `futuros` pontos. Devolve (projetados, faixa, inclinação por mês)."""
    n = len(valores)
    if n == 0:
        return [0.0] * futuros, 0.0, 0.0
    if n < 3:
        media = sum(valores) / n
        desvio = math.sqrt(sum((v - media) ** 2 for v in valores) / n) if n > 1 else 0.0
        return [media] * futuros, 1.96 * desvio, 0.0
    xs = list(range(n))
    mx, my = sum(xs) / n, sum(valores) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, valores)) / sxx if sxx else 0.0
    a = my - b * mx
    residuos = [y - (a + b * x) for x, y in zip(xs, valores)]
    desvio = math.sqrt(sum(r * r for r in residuos) / max(1, n - 2))
    proj = [max(0.0, a + b * (n + i)) for i in range(futuros)]
    return proj, 1.96 * desvio, b


def _por_mes(db, sql, meses, params=()):
    contagem = {m: 0 for m in meses}
    for r in db.execute(sql, (meses[0] + '-01', meses[-1] + '-31', *params)).fetchall():
        if r[0] in contagem:
            contagem[r[0]] = r[1]
    return [contagem[m] for m in meses]


def _resultado(titulo, meses, valores, futuros, unidade, premissa, extra=None):
    fut = meses_futuros(futuros)
    proj, faixa, incl = tendencia(valores, futuros)
    saida = {
        'titulo': titulo, 'unidade': unidade, 'premissa': premissa,
        'historico': [{'mes': m, 'rotulo': rotulo(m), 'valor': v} for m, v in zip(meses, valores)],
        'projecao': [{'mes': m, 'rotulo': rotulo(m), 'valor': round(p, 1), 'min': round(max(0.0, p - faixa), 1),
                      'max': round(p + faixa, 1)} for m, p in zip(fut, proj)],
        'inclinacao_mes': round(incl, 2),
        'media_historico': round(sum(valores) / len(valores), 1) if valores else 0,
    }
    if extra:
        saida.update(extra)
    return saida


def projecao_atendimentos(db, meses_hist=6, meses_futuro=3):
    """Pacientes atendidos (fichas lançadas em Atendimentos) por mês e a projeção dos próximos meses."""
    n = _limitar(meses_hist, MESES_MIN, MESES_MAX, 6)
    f = _limitar(meses_futuro, 1, FUTURO_MAX, 3)
    meses = meses_completos(n)
    valores = _por_mes(db, 'SELECT substr(data,1,7) AS m, COUNT(*) FROM atendimentos WHERE data BETWEEN ? AND ? GROUP BY m', meses)
    metodo = 'tendência linear' if n >= 3 else 'média simples'
    return _resultado('Pacientes atendidos por mês', meses, valores, f, 'pacientes',
                      'Baseado nos %d meses completos anteriores (%s a %s), %s.' % (n, rotulo(meses[0]), rotulo(meses[-1]), metodo))


def projecao_comparecimento(db, meses_hist=6, meses_futuro=3):
    """Pacientes que vieram (Veio ou Retorno na agenda) por mês e a projeção (indicador de comparecimento da ONA)."""
    n = _limitar(meses_hist, MESES_MIN, MESES_MAX, 6)
    f = _limitar(meses_futuro, 1, FUTURO_MAX, 3)
    meses = meses_completos(n)
    valores = _por_mes(db, "SELECT substr(a.data,1,7) AS m, COUNT(*) FROM agenda_horarios h JOIN agenda_exames a ON a.id=h.agenda_id "
                           "WHERE a.data BETWEEN ? AND ? AND TRIM(h.paciente)<>'' AND h.status IN ('VEIO','RETORNO') GROUP BY m", meses)
    metodo = 'tendência linear' if n >= 3 else 'média simples'
    return _resultado('Pacientes que vieram (agenda)', meses, valores, f, 'pacientes',
                      'Baseado nos %d meses completos anteriores (%s a %s), %s.' % (n, rotulo(meses[0]), rotulo(meses[-1]), metodo))


def projecao_faltas(db, meses_hist=6):
    """Faltas previstas no próximo mês: taxa de falta dos últimos meses (Faltou sobre Veio + Retorno + Faltou) aplicada
    aos pacientes já agendados no próximo mês (ou à média de marcados, se a agenda ainda estiver vazia)."""
    n = _limitar(meses_hist, MESES_MIN, MESES_MAX, 6)
    meses = meses_completos(n)
    base_sql = ("SELECT substr(a.data,1,7) AS m, COUNT(*) FROM agenda_horarios h JOIN agenda_exames a ON a.id=h.agenda_id "
                "WHERE a.data BETWEEN ? AND ? AND TRIM(h.paciente)<>'' AND h.status IN (%s) GROUP BY m")
    faltas = _por_mes(db, base_sql % "'FALTOU'", meses)
    base = _por_mes(db, base_sql % "'VEIO','RETORNO','FALTOU'", meses)
    taxas = [round(100.0 * fa / b, 1) if b else 0.0 for fa, b in zip(faltas, base)]
    total_f, total_b = sum(faltas), sum(base)
    taxa = total_f / total_b if total_b else 0.0
    prox = meses_futuros(1)[0]
    agendados = db.execute("SELECT COUNT(*) FROM agenda_horarios h JOIN agenda_exames a ON a.id=h.agenda_id "
                           "WHERE substr(a.data,1,7)=? AND TRIM(h.paciente)<>'' AND h.status IN ('AGENDADO','VEIO','RETORNO','FALTOU')",
                           (prox,)).fetchone()[0]
    usa_media = agendados == 0
    referencia = (total_b / n) if usa_media else agendados
    previstas = taxa * referencia
    # faixa: variação da taxa mês a mês
    validas = [t / 100.0 for t, b in zip(taxas, base) if b]
    desvio = math.sqrt(sum((t - taxa) ** 2 for t in validas) / len(validas)) if len(validas) > 1 else 0.0
    premissa = ('Taxa de falta de %.1f%% nos %d meses completos anteriores (%s a %s), aplicada a %s.'
                % (100 * taxa, n, rotulo(meses[0]), rotulo(meses[-1]),
                   ('%d pacientes já agendados em %s' % (agendados, rotulo(prox))) if not usa_media
                   else 'uma média de %.0f pacientes por mês (a agenda de %s ainda está vazia)' % (referencia, rotulo(prox))))
    return {
        'titulo': 'Faltas previstas em %s' % rotulo(prox), 'unidade': 'faltas', 'premissa': premissa,
        'historico': [{'mes': m, 'rotulo': rotulo(m), 'valor': fa, 'taxa': t} for m, fa, t in zip(meses, faltas, taxas)],
        'projecao': [{'mes': prox, 'rotulo': rotulo(prox), 'valor': round(previstas, 1),
                      'min': round(max(0.0, (taxa - 1.96 * desvio) * referencia), 1),
                      'max': round((taxa + 1.96 * desvio) * referencia, 1)}],
        'taxa_media': round(100 * taxa, 1), 'agendados_proximo': agendados, 'usou_media': usa_media,
    }
