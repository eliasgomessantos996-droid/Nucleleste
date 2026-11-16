"""Relatório ONA em PDF e Excel, no modelo comum de relatórios."""
from __future__ import annotations

from reportlab.platypus import Paragraph, Spacer

from .relatorio_base import RelatorioPDF, planilha, xlsx_bytes


def _pct(v):
    return '—' if v is None else ('%.1f%%' % v).replace('.', ',')


def _periodo(r):
    from . import util
    return '%s a %s' % (util.data_br(r['de']), util.data_br(r['ate']))


def relatorio_pdf(r, empresa):
    rp = RelatorioPDF('Relatório ONA: indicadores', empresa, _periodo(r))
    e = rp.e
    historia = [Paragraph('Total de exames realizados no período: %d' % r['total_exames'], e['total']),
                Paragraph('Indicadores', e['h2']),
                rp.tabela(['Indicador', 'Critério', 'Numerador', 'Denominador', 'Percentual'],
                          [[i['nome'], i['criterio'], str(i['numerador']), str(i['denominador']), _pct(i['percentual'])]
                           for i in r['indicadores']],
                          [42, 66, 22, 24, 22], direita=(2, 3, 4))]
    for titulo, chave, cab in (('Produção por exame', 'por_exame', 'Exame'), ('Produção por convênio', 'por_convenio', 'Convênio'),
                               ('Produção por sexo do paciente', 'por_sexo', 'Sexo')):
        historia.append(Paragraph(titulo, e['h2']))
        historia.append(rp.tabela([cab, 'Exames'], [[k, str(v)] for k, v in r[chave]], [130, 40], direita=(1,)))
    historia.append(Spacer(1, 6))
    historia.append(Paragraph('Os indicadores são calculados com os dados do próprio sistema. Confira a definição de cada um '
                              'com o manual da ONA vigente antes de enviar.', e['nota']))
    return rp.bytes(historia)


def relatorio_xlsx(r, empresa):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = 'Indicadores'
    planilha(ws, 'Relatório ONA: indicadores', empresa, _periodo(r),
             ['Indicador', 'Critério', 'Numerador', 'Denominador', 'Percentual'],
             [[i['nome'], i['criterio'], i['numerador'], i['denominador'], _pct(i['percentual'])] for i in r['indicadores']],
             [40, 60, 14, 14, 14])
    for titulo, chave in (('Por exame', 'por_exame'), ('Por convênio', 'por_convenio'), ('Por sexo', 'por_sexo')):
        folha = wb.create_sheet(titulo)
        planilha(folha, 'Relatório ONA: %s' % titulo.lower(), empresa, _periodo(r), [titulo.replace('Por ', '').capitalize(), 'Exames'],
                 [[k, v] for k, v in r[chave]], [40, 14])
    return xlsx_bytes(wb)
