"""Relatório da agenda de exames (PDF e Excel), no modelo comum de relatórios. Os números vêm de agenda.relatorio()."""
from __future__ import annotations

from reportlab.platypus import Paragraph

from . import util
from .relatorio_base import RelatorioPDF, planilha, xlsx_bytes

COLUNAS_REL = ['Marcados', 'Vieram', 'Faltaram', 'Retornos', 'Ainda agendados', 'Taxa de falta']


def _pct(v):
    return '—' if v is None else ('%.1f%%' % v).replace('.', ',')


def _linha(b):
    return [str(b['marcados']), str(b['VEIO']), str(b['FALTOU']), str(b['RETORNO']), str(b['AGENDADO']), _pct(b['taxa_falta'])]


def _periodo(rel):
    txt = '%s a %s' % (util.data_br(rel['de']), util.data_br(rel['ate']))
    return txt + (' · exame: %s' % rel['exame'] if rel['exame'] else '') + ' · retornos já contados em Vieram'


def relatorio_pdf(rel, empresa):
    rp = RelatorioPDF('Relatório da agenda de exames', empresa, _periodo(rel))
    e = rp.e
    g = rel['geral']
    historia = [Paragraph('Resumo do período', e['h2']),
                rp.tabela(['Total'] + COLUNAS_REL, [['Todos os exames'] + _linha(g)], [56, 20, 20, 20, 20, 24, 20], direita=(1, 2, 3, 4, 5, 6)),
                Paragraph('Horários criados: %d · livres: %d · taxa de comparecimento: %s' %
                          (g['vagas'], g['livres'], _pct(g['taxa_comparecimento'])), e['nota'])]
    for rotulo, chave, vazio in (('Por exame', 'por_exame', 'Sem exames no período.'),
                                 ('Por convênio', 'por_convenio', 'Sem pacientes no período.'),
                                 ('Por dia', 'por_dia', 'Sem dias no período.')):
        historia.append(Paragraph(rotulo, e['h2']))
        if rel[chave]:
            linhas = [[util.data_br(b['nome']) if chave == 'por_dia' else b['nome']] + _linha(b) for b in rel[chave]]
            historia.append(rp.tabela([rotulo.replace('Por ', '').capitalize()] + COLUNAS_REL, linhas,
                                      [56, 20, 20, 20, 20, 24, 20], direita=(1, 2, 3, 4, 5, 6)))
        else:
            historia.append(Paragraph(vazio, e['nota']))
    return rp.bytes(historia)


def _numeros(b):
    """Contagens como números (no Excel elas continuam somáveis); a taxa segue no formato de texto, como antes."""
    return [b['marcados'], b['VEIO'], b['FALTOU'], b['RETORNO'], b['AGENDADO'], _pct(b['taxa_falta'])]


def relatorio_xlsx(rel, empresa):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = 'Resumo'
    g = rel['geral']
    planilha(ws, 'Relatório da agenda de exames', empresa, _periodo(rel), ['Total'] + COLUNAS_REL,
             [['Todos os exames'] + _numeros(g)], [34, 14, 14, 14, 14, 18, 16])
    for titulo, chave in (('Por exame', 'por_exame'), ('Por convênio', 'por_convenio'), ('Por dia', 'por_dia')):
        folha = wb.create_sheet(titulo)
        linhas = [[util.data_br(b['nome']) if chave == 'por_dia' else b['nome']] + _numeros(b) for b in rel[chave]]
        planilha(folha, 'Relatório da agenda: %s' % titulo.lower(), empresa, _periodo(rel),
                 [titulo.replace('Por ', '').capitalize()] + COLUNAS_REL, linhas, [34, 14, 14, 14, 14, 18, 16])
    return xlsx_bytes(wb)


def resgate_pdf(rel, empresa):
    """Relatório de resgate: quantos pacientes cada usuário resgatou no período (modelo comum)."""
    rp = RelatorioPDF('Relatório de resgate', empresa, '%s a %s' % (util.data_br(rel['de']), util.data_br(rel['ate'])))
    e = rp.e
    historia = [Paragraph('Total: %d resgate(s) · reagendados: %d · desistiram: %d' %
                          (rel['total'], rel['reagendados'], rel['desistiram']), e['total']),
                Paragraph('Por usuário', e['h2']),
                rp.tabela(['Usuário', 'Resgatados', 'Reagendados', 'Desistiram'],
                          [[u['usuario'], str(u['total']), str(u['reagendados']), str(u['desistiram'])] for u in rel['usuarios']],
                          [70, 35, 35, 35], direita=(1, 2, 3))]
    for u in rel['usuarios']:
        historia.append(Paragraph('%s: %d resgate(s)' % (u['usuario'], u['total']), e['h2']))
        historia.append(rp.tabela(['Paciente', 'Exame', 'Dia da falta', 'Situação', 'Quando reagendou'],
                                  [[i['paciente'], i['exame'], '%s %s' % (util.data_br(i['data']), i['hora']), i['status'],
                                    '%s %s' % (util.data_br(i['em'][:10]), i['em'][11:16])] for i in u['itens']],
                                  [52, 42, 34, 26, 28]))
    return rp.bytes(historia)


def resgate_xlsx(rel, empresa):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = 'Por usuário'
    planilha(ws, 'Relatório de resgate', empresa, '%s a %s' % (util.data_br(rel['de']), util.data_br(rel['ate'])),
             ['Usuário', 'Resgatados', 'Reagendados', 'Desistiram'],
             [[u['usuario'], u['total'], u['reagendados'], u['desistiram']] for u in rel['usuarios']],
             [34, 14, 14, 14], totais=['TOTAL', rel['total'], rel['reagendados'], rel['desistiram']])
    folha = wb.create_sheet('Detalhe')
    linhas = [[u['usuario'], i['paciente'], i['exame'], util.data_br(i['data']), i['hora'], i['status'], i['em']]
              for u in rel['usuarios'] for i in u['itens']]
    planilha(folha, 'Relatório de resgate: detalhe', empresa, '%s a %s' % (util.data_br(rel['de']), util.data_br(rel['ate'])),
             ['Usuário', 'Paciente', 'Exame', 'Dia da falta', 'Hora', 'Situação', 'Quando reagendou'], linhas,
             [22, 34, 26, 14, 10, 20, 20])
    return xlsx_bytes(wb)


def reservas_pdf(linhas, empresa, de, ate):
    """Relatório simples das reservas: as datas reservadas e a quantidade de vagas de cada uma (vem junto das planilhas no .zip)."""
    rp = RelatorioPDF('Reservas de convênio', empresa, '%s a %s' % (util.data_br(de), util.data_br(ate)))
    e = rp.e
    total = sum(l['vagas'] for l in linhas)
    historia = [Paragraph('%d data(s) reservada(s) · %d vaga(s) em branco para preencher. Cada data tem a sua planilha (.xlsx) neste pacote.'
                          % (len(linhas), total), e['total']),
                rp.tabela(['Data', 'Convênio', 'Vagas por exame', 'Vagas'],
                          [['%s (%s)' % (util.data_br(l['dia']), l['dia_semana']), l['convenio'],
                            ', '.join('%s: %d' % (ex, n) for ex, n in l['por_exame'].items()), str(l['vagas'])] for l in linhas],
                          [40, 36, 84, 20], totais=['TOTAL', '', '', str(total)], direita=(3,))]
    return rp.bytes(historia)
