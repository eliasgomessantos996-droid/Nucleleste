"""Relatório de contas a pagar por fornecedor (PDF e Excel), no modelo comum de relatórios."""
from __future__ import annotations

from reportlab.platypus import Paragraph

from . import util
from .relatorio_base import RelatorioPDF, planilha, xlsx_bytes

SITUACAO = {'ABERTO': 'Em aberto', 'PAGO': 'Pagas'}


def _periodo(rel):
    txt = 'Vencimentos de %s a %s' % (util.data_br(rel['de']), util.data_br(rel['ate']))
    return txt + (' · %s' % SITUACAO[rel['status']] if rel['status'] in SITUACAO else '')


def _descricao(c):
    return c['descricao'] + (' (%s)' % c['parcela'] if c['parcela'] else '')


def relatorio_pdf(rel, empresa):
    rp = RelatorioPDF('Contas a pagar por fornecedor', empresa, _periodo(rel))
    e = rp.e
    historia = [Paragraph('Em aberto: R$ %s · Pago: R$ %s · Total: R$ %s · %d conta(s)' %
                          (util.moeda(rel['aberto']), util.moeda(rel['pago']), util.moeda(rel['total']), rel['quantidade']), e['total'])]
    if not rel['grupos']:
        historia.append(Paragraph('Nenhuma conta no período.', e['nota']))
    resumo = [[g['nome'], g['cnpj'], str(len(g['contas'])), util.moeda(g['aberto']), util.moeda(g['pago']), util.moeda(g['total'])]
              for g in rel['grupos']]
    if resumo:
        historia.append(Paragraph('Resumo por fornecedor', e['h2']))
        historia.append(rp.tabela(['Fornecedor', 'CNPJ', 'Contas', 'Em aberto (R$)', 'Pago (R$)', 'Total (R$)'], resumo,
                                  [58, 32, 14, 28, 24, 26], direita=(2, 3, 4, 5),
                                  totais=['TOTAL', '', str(rel['quantidade']), util.moeda(rel['aberto']), util.moeda(rel['pago']),
                                          util.moeda(rel['total'])]))
    for g in rel['grupos']:
        historia.append(Paragraph('%s%s' % (g['nome'], (' · CNPJ ' + g['cnpj']) if g['cnpj'] else ''), e['h2']))
        historia.append(rp.tabela(['Vencimento', 'Descrição', 'Situação', 'Valor (R$)'],
                                  [[util.data_br(c['vencimento']), _descricao(c),
                                    'Paga em %s' % util.data_br(c['data_pagamento']) if c['status'] == 'PAGO' and c['data_pagamento']
                                    else ('Paga' if c['status'] == 'PAGO' else 'Em aberto'), util.moeda(c['valor'])]
                                   for c in g['contas']],
                                  [26, 92, 38, 26], direita=(3,), totais=['', 'Total do fornecedor', '', util.moeda(g['total'])]))
    return rp.bytes(historia)


def relatorio_xlsx(rel, empresa):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = 'Resumo'
    planilha(ws, 'Contas a pagar por fornecedor', empresa, _periodo(rel),
             ['Fornecedor', 'CNPJ', 'Contas', 'Em aberto (R$)', 'Pago (R$)', 'Total (R$)'],
             [[g['nome'], g['cnpj'], len(g['contas']), g['aberto'], g['pago'], g['total']] for g in rel['grupos']],
             [40, 22, 10, 16, 16, 16], totais=['TOTAL', '', rel['quantidade'], rel['aberto'], rel['pago'], rel['total']],
             formatos={3: '#,##0.00', 4: '#,##0.00', 5: '#,##0.00'})
    det = wb.create_sheet('Contas')
    linhas = [[g['nome'], g['cnpj'], util.data_br(c['vencimento']), c['descricao'], c['parcela'], c['nota_fiscal'] or '',
               'Paga' if c['status'] == 'PAGO' else 'Em aberto', util.data_br(c['data_pagamento']), c['valor'] or 0]
              for g in rel['grupos'] for c in g['contas']]
    planilha(det, 'Contas a pagar por fornecedor: detalhe', empresa, _periodo(rel),
             ['Fornecedor', 'CNPJ', 'Vencimento', 'Descrição', 'Parcela', 'Nota fiscal', 'Situação', 'Pago em', 'Valor (R$)'], linhas,
             [34, 22, 14, 40, 10, 14, 12, 14, 14], formatos={8: '#,##0.00'})
    return xlsx_bytes(wb)
