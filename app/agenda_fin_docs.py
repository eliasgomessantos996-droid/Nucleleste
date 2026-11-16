"""Financeiro da agenda (repasse médico) em PDF e Excel, no modelo comum de relatórios."""
from __future__ import annotations

import math

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Flowable, Paragraph, Table, TableStyle

from . import util
from .relatorio_base import FONTE, FONTE_NEGRITO, GRADE, MARGEM, VERDE, ZEBRA, RelatorioPDF, _esc, planilha, xlsx_bytes

COLUNAS = ['Nº', 'Paciente', 'Convênio', 'Valor do convênio', 'Valor a repassar']
ETAPAS_SIGLA = [('Repouso', 'R'), ('Estresse', 'E'), ('Protocolo', 'P')]
DIAS_NOMES = ['seg', 'ter', 'qua', 'qui', 'sex', 'sáb', 'dom']
DINHEIRO = '"R$" #,##0.00'
# PDF compacto: margem lateral e níveis de densidade (blocos de pacientes lado a lado, tamanho da fonte em pt).
# Do mais confortável ao mais denso; usa-se o primeiro nível cujo PDF cabe em uma única página.
MARGEM_COMPACTA = 10 * mm
NIVEIS = [(1, 8.0), (1, 7.5), (1, 6.5), (2, 6.5), (2, 5.5), (3, 5.5), (4, 4.8), (5, 4.2)]


def dias_texto(dias, sep=' e '):
    """Nomes curtos dos dias da semana (0=segunda ... 6=domingo): 'ter e sex' (ou 'ter, sex' com sep=', ')."""
    nomes = [DIAS_NOMES[d] for d in dias or ()]
    if len(nomes) <= 1:
        return ''.join(nomes)
    return ', '.join(nomes[:-1]) + sep + nomes[-1]


def _periodo(rel):
    txt = '%s a %s' % (util.data_br(rel['de']), util.data_br(rel['ate']))
    txt += (' · exame: %s' % rel['exame']) if rel.get('exame') else ' · todos os exames'
    if rel.get('dias'):
        txt += ' · dias: %s' % dias_texto(rel['dias'])
    return txt + ' · repasse de %s%%' % ('%g' % rel['pct']).replace('.', ',')


class Caixa(Flowable):
    """Quadradinho de marcação desenhado à mão (a fonte Helvetica não tem o glifo de caixa). Marcado = com um X, centralizado na célula."""

    def __init__(self, marcado, lado):
        Flowable.__init__(self)
        self.marcado = marcado
        self.lado = lado

    def wrap(self, largura, altura):
        self._largura = largura
        return largura, self.lado

    def draw(self):
        c = self.canv
        x = (self._largura - self.lado) / 2
        c.saveState()
        c.setStrokeColor(VERDE)
        c.setLineWidth(.6)
        c.rect(x, 0, self.lado, self.lado, stroke=1, fill=0)
        if self.marcado:
            m = self.lado * .22
            c.setLineWidth(1)
            c.line(x + m, m, x + self.lado - m, self.lado - m)
            c.line(x + m, self.lado - m, x + self.lado - m, m)
        c.restoreState()


def _estilos(f):
    """Estilos de texto do nível de densidade `f` (tamanho da fonte em pt)."""
    pad = 1.2 if f < 7 else 2.2
    return {
        'sub': ParagraphStyle('fsub', fontName=FONTE, fontSize=f, leading=f * 1.25, textColor=colors.HexColor('#444444')),
        'nota': ParagraphStyle('fnota', fontName=FONTE, fontSize=max(4.5, f - .5), leading=max(5.5, f * 1.2), textColor=colors.HexColor('#555555')),
        'h2': ParagraphStyle('fh2', fontName=FONTE_NEGRITO, fontSize=f + 1.5, leading=(f + 1.5) * 1.25, textColor=VERDE, spaceBefore=4,
                             spaceAfter=2, keepWithNext=1),
        'cel': ParagraphStyle('fcel', fontName=FONTE, fontSize=f, leading=f * 1.2),
        'cel_dir': ParagraphStyle('fcel_dir', fontName=FONTE, fontSize=f, leading=f * 1.2, alignment=2),
        'cab': ParagraphStyle('fcab', fontName=FONTE_NEGRITO, fontSize=max(4.5, f - .5), leading=max(5.5, f * 1.15), textColor=colors.white),
        'total': ParagraphStyle('ftotal', fontName=FONTE_NEGRITO, fontSize=f + .5, leading=(f + .5) * 1.25, spaceBefore=4),
        'pad': pad,
        'lado': max(4.5, f * .8),
    }


class _Inviavel(Exception):
    """O nível de densidade não cabe na largura da página (colunas fixas grandes demais para os blocos)."""


def _colunas(spec, bw, estrito):
    """Larguras (pt) de um bloco. `spec` = [('x', mm)] colunas fixas ou [('f', peso)] colunas que dividem a sobra.
    Se a sobra for menor que 20 mm: no nível `estrito` o nível é descartado; no último, as fixas são reduzidas."""
    fixas = sum(v for k, v in spec if k == 'x') * mm
    pesos = sum(v for k, v in spec if k == 'f')
    minimo = 20 * mm
    if bw - fixas < minimo:
        if estrito:
            raise _Inviavel()
        fator = max(.1, (bw - minimo) / fixas) if fixas else 1
        return [v * mm * fator if k == 'x' else minimo * v / pesos for k, v in spec]
    sobra = bw - fixas
    return [v * mm if k == 'x' else sobra * v / pesos for k, v in spec]


def _grade(cab, linhas, spec, blocos, st, direita, largura, estrito):
    """Tabela em `blocos` colunas lado a lado: as linhas são divididas em pedaços consecutivos (a numeração segue a ordem).
    É uma tabela só, com cabeçalho repetido em cada bloco, então quebra de página continua funcionando."""
    if not linhas:
        return None
    tamanho = math.ceil(len(linhas) / blocos)
    pedacos = [linhas[i:i + tamanho] for i in range(0, len(linhas), tamanho)]
    n = len(pedacos)
    colunas = _colunas(spec, largura / n, estrito)
    m = len(cab)
    dados = [[Paragraph(_esc(c), st['cab']) for _ in range(n) for c in cab]]
    for linha in range(tamanho):
        linha_cels = []
        for pedaco in pedacos:
            if linha < len(pedaco):
                for i, v in enumerate(pedaco[linha]):
                    linha_cels.append(v if isinstance(v, Flowable) else Paragraph(_esc(v), st['cel_dir' if i in direita else 'cel']))
            else:
                linha_cels += [''] * m
        dados.append(linha_cels)
    t = Table(dados, repeatRows=1, colWidths=colunas * n)
    estilo = [('BACKGROUND', (0, 0), (-1, 0), VERDE), ('GRID', (0, 0), (-1, -1), .4, GRADE), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
              ('TOPPADDING', (0, 0), (-1, -1), st['pad']), ('BOTTOMPADDING', (0, 0), (-1, -1), st['pad']),
              ('LEFTPADDING', (0, 0), (-1, -1), 2), ('RIGHTPADDING', (0, 0), (-1, -1), 2),
              ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, ZEBRA])]
    t.setStyle(TableStyle(estilo))
    return t


def _historia(rel, rp, blocos, f, estrito):
    """Conteúdo do PDF compacto no nível de densidade dado (`estrito`: descarta o nível se não couber)."""
    st = _estilos(f)
    largura = rp.pagina[0] - 2 * MARGEM_COMPACTA
    mibi = bool(rel.get('tem_mibi'))
    h = [Paragraph('Só entram pacientes com status “Veio” no período.', st['sub'])]
    if rel['sem_valor']:
        h.append(Paragraph('Atenção: %d paciente(s) sem valor cadastrado para o convênio e o tipo de exame (contam como zero).'
                           % rel['sem_valor'], st['nota']))
    if mibi:
        h.append(Paragraph('R = Repouso · E = Estresse · P = Protocolo (quadrado com X = etapa realizada)', st['nota']))
    h.append(Paragraph('Por convênio e tipo de exame', st['h2']))
    if rel['resumo']:
        spec_res = [('f', 34), ('f', 19), ('x', 15), ('x', 1.9 * f + 3.5)]
        h.append(_grade(['Convênio', 'Tipo do exame', 'Pacientes', 'Valor do convênio'],
                        [[g['convenio'], g['tipo'], str(g['qtd']), util.moeda(g['valor'])] for g in rel['resumo']],
                        spec_res, 2 if len(rel['resumo']) > 8 else 1, st, (2, 3), largura, estrito))
    else:
        h.append(Paragraph('Nenhum paciente que veio no período.', st['nota']))
    h.append(Paragraph('Pacientes atendidos (veio ou retorno)', st['h2']))
    if rel['itens']:
        cab = ['Nº', 'Paciente', 'Convênio'] + (['R', 'E', 'P'] if mibi else []) + ['Valor do convênio', 'Valor a repassar']
        spec = [('x', .6 * f + 2.2), ('f', 50), ('f', 40)] + ([('x', st['lado'] * .353 + 2.2)] * 3 if mibi else []) + [('x', 1.9 * f + 1.5)] * 2
        linhas = []
        for i in rel['itens']:
            marcas = [Caixa(nome in i['etapas'], st['lado']) for nome, _sigla in ETAPAS_SIGLA] if mibi else []
            linhas.append([str(i['n']), i['paciente'], i['convenio']] + marcas + [util.moeda(i['valor']), util.moeda(i['repasse'])])
        direita = (0, len(cab) - 2, len(cab) - 1)
        h.append(_grade(cab, linhas, spec, blocos, st, direita, largura, estrito))
        h.append(Paragraph('TOTAL · faturado: %s · a repassar: %s · pacientes: %d'
                           % (util.moeda(rel['total_valor']), util.moeda(rel['total_repasse']), rel['qtd']), st['total']))
    else:
        h.append(Paragraph('Nenhum paciente que veio no período.', st['nota']))
    return h


def financeiro_pdf(rel, empresa):
    """PDF do financeiro. Tenta os níveis do mais confortável ao mais denso e usa o primeiro que cabe em uma única página.
    Se nenhum couber em uma página (cenário extremo), vale o último nível, que pode ter mais de uma página."""
    pdf = b''
    for i, (blocos, f) in enumerate(NIVEIS):
        estrito = i < len(NIVEIS) - 1
        rp = RelatorioPDF('Financeiro da agenda: repasse médico', empresa, _periodo(rel))
        try:
            historia = _historia(rel, rp, blocos, f, estrito)
        except _Inviavel:
            continue
        pdf = rp.bytes(historia, margem=MARGEM_COMPACTA, topo=15 * mm, base=12 * mm)
        if rp.paginas <= 1:
            break
    return pdf


def financeiro_xlsx(rel, empresa):
    from openpyxl import Workbook
    from openpyxl.utils import get_column_letter
    wb = Workbook()
    ws = wb.active
    ws.title = 'Repasse'
    mibi = bool(rel.get('tem_mibi'))
    cab = COLUNAS[:3] + (['Repouso', 'Estresse', 'Protocolo'] if mibi else []) + COLUNAS[3:]
    itens = rel['itens']
    linhas = []
    for i in itens:
        marcas = ['X' if nome in i['etapas'] else '' for nome, _sigla in ETAPAS_SIGLA] if mibi else []
        linhas.append([i['n'], i['paciente'], i['convenio']] + marcas + [i['valor'], i['repasse']])
    iv, ir = len(cab) - 2, len(cab) - 1
    primeira = 5
    ultima = primeira + len(itens) - 1 if itens else primeira - 1
    totais = [''] * len(cab)
    totais[1] = 'TOTAL'
    totais[iv] = '=SUM(%s%d:%s%d)' % (get_column_letter(iv + 1), primeira, get_column_letter(iv + 1), ultima) if itens else 0
    totais[ir] = '=SUM(%s%d:%s%d)' % (get_column_letter(ir + 1), primeira, get_column_letter(ir + 1), ultima) if itens else 0
    larguras = [6, 40, 24] + ([10, 10, 10] if mibi else []) + [20, 20]
    planilha(ws, 'Financeiro da agenda: repasse médico', empresa, _periodo(rel), cab, linhas, larguras,
             totais=totais, formatos={iv: DINHEIRO, ir: DINHEIRO})
    ws2 = wb.create_sheet('Por convênio e tipo')
    planilha(ws2, 'Financeiro da agenda: por convênio e tipo', empresa, _periodo(rel),
             ['Convênio', 'Tipo do exame', 'Pacientes', 'Valor do convênio'],
             [[g['convenio'], g['tipo'], g['qtd'], g['valor']] for g in rel['resumo']], [30, 18, 12, 20], formatos={3: DINHEIRO})
    return xlsx_bytes(wb)
