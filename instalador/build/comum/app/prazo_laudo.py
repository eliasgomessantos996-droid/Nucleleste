"""Prazo de entrega dos laudos e previsão de entrega (calendário de Governador Valadares, MG).

A gerência escolhe o prazo em "Mapa de laudos > Prazo de entrega": horas corridas (padrão: 24), dias corridos ou dias
úteis. Sábados, domingos e feriados não contam como dia útil. Feriados considerados: nacionais, Sexta-feira Santa,
aniversário da cidade (30/01) e Santo Antônio, padroeiro (13/06); Carnaval e Corpus Christi (pontos facultativos) entram
se a gerência marcar; datas extras (dd/mm ou dd/mm/aaaa) podem ser listadas em texto livre.
"""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta

from .db import config_get, config_set

TIPOS = (('horas', 'horas corridas'), ('dias', 'dias corridos'), ('uteis', 'dias úteis'))
PADRAO = {'tipo': 'horas', 'valor': 24, 'carnaval': False, 'corpus': False, 'extras': ''}
MAXIMO = {'horas': 720, 'dias': 60, 'uteis': 60}
FIXOS = ((1, 1), (21, 4), (1, 5), (7, 9), (12, 10), (2, 11), (15, 11), (20, 11), (25, 12),   # nacionais
         (30, 1), (13, 6))                                                                  # Governador Valadares


def pascoa(ano):
    a, b, c = ano % 19, ano // 100, ano % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes, dia = divmod(h + l - 7 * m + 114, 31)
    return date(ano, mes, dia + 1)


def extras_de(texto, ano):
    """Datas do texto livre (uma por linha ou separadas por vírgula/;) que valem para o ano."""
    dias = set()
    for p in re.split(r'[\n,;]+', texto or ''):
        m = re.fullmatch(r'\s*(\d{1,2})/(\d{1,2})(?:/(\d{4}))?\s*', p)
        if not m or (m.group(3) and int(m.group(3)) != ano):
            continue
        try:
            dias.add(date(ano, int(m.group(2)), int(m.group(1))))
        except ValueError:
            pass
    return dias


def feriados(ano, cfg=None):
    cfg = cfg or atuais()
    p = pascoa(ano)
    dias = {date(ano, m, d) for d, m in FIXOS}
    dias.add(p - timedelta(days=2))                      # Sexta-feira Santa
    if cfg['carnaval']:
        dias |= {p - timedelta(days=48), p - timedelta(days=47)}
    if cfg['corpus']:
        dias.add(p + timedelta(days=60))
    return dias | extras_de(cfg['extras'], ano)


def dia_util(dia, cfg=None):
    return dia.weekday() < 5 and dia not in feriados(dia.year, cfg)


def proximo_util(dia, cfg=None):
    """O próprio dia, se for útil; senão o primeiro dia útil depois dele."""
    while not dia_util(dia, cfg):
        dia += timedelta(days=1)
    return dia


def somar_uteis(dia, n, cfg=None):
    while n > 0:
        dia += timedelta(days=1)
        if dia_util(dia, cfg):
            n -= 1
    return dia


def atuais(db=None):
    """Configuração vigente. Com `db`, lê direto dele (útil fora de uma requisição)."""
    def ler(chave):
        if db is None:
            return config_get(chave, '') or ''
        r = db.execute('SELECT valor FROM config WHERE chave=?', (chave,)).fetchone()
        return (r['valor'] if r else '') or ''

    try:
        valor = int(ler('laudo_prazo_valor') or PADRAO['valor'])
    except ValueError:
        valor = PADRAO['valor']
    tipo = ler('laudo_prazo_tipo') or PADRAO['tipo']
    if tipo not in dict(TIPOS):
        tipo = PADRAO['tipo']
    return {'tipo': tipo, 'valor': max(1, min(MAXIMO[tipo], valor)),
            'carnaval': ler('laudo_prazo_carnaval') == '1', 'corpus': ler('laudo_prazo_corpus') == '1',
            'extras': ler('laudo_feriados_extras')}


def exibir_na_ficha():
    """A previsão aparece na impressão, salvo quando a configuração geral a desativa."""
    return config_get('laudo_previsao_ficha', '1') != '0'


def salvar(form):
    """Grava o prazo vindo do formulário. Devolve a mensagem de erro, ou '' se gravou."""
    tipo = (form.get('tipo') or '').strip()
    if tipo not in dict(TIPOS):
        return 'Escolha o tipo de prazo.'
    try:
        valor = int((form.get('valor') or '').strip())
    except ValueError:
        return 'Informe a quantidade como número inteiro.'
    if not 1 <= valor <= MAXIMO[tipo]:
        return 'A quantidade deve estar entre 1 e %d.' % MAXIMO[tipo]
    config_set('laudo_prazo_tipo', tipo)
    config_set('laudo_prazo_valor', str(valor))
    config_set('laudo_prazo_carnaval', '1' if form.get('carnaval') else '0')
    config_set('laudo_prazo_corpus', '1' if form.get('corpus') else '0')
    config_set('laudo_feriados_extras', (form.get('extras') or '').strip()[:2000])
    return ''


def descricao(cfg=None):
    cfg = cfg or atuais()
    return '%d %s' % (cfg['valor'], dict(TIPOS)[cfg['tipo']])


def limite(inicio, cfg=None):
    """Instante limite de entrega de um exame que começou em `inicio` (datetime)."""
    cfg = cfg or atuais()
    fim_do_dia = time(23, 59, 59)
    if cfg['tipo'] == 'horas':
        lim = inicio + timedelta(hours=cfg['valor'])
        if dia_util(lim.date(), cfg):
            return lim
        return datetime.combine(proximo_util(lim.date(), cfg), fim_do_dia)
    if cfg['tipo'] == 'dias':
        dia = proximo_util(inicio.date() + timedelta(days=cfg['valor']), cfg)
    else:
        dia = somar_uteis(inicio.date(), cfg['valor'], cfg)
    return datetime.combine(dia, fim_do_dia)


def previsao(dia, cfg=None):
    """Data prevista de entrega para um exame feito em `dia` (date)."""
    return limite(datetime.combine(dia, time(0, 0)), cfg).date()
