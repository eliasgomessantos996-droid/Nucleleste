"""Relatório de fechamento de caixa para assinatura (PDF), no modelo comum: dinheiro com troco e PIX separados."""
from __future__ import annotations

from reportlab.platypus import Paragraph, Spacer

from . import util
from .relatorio_base import RelatorioPDF


def _hora(v):
    return (v or '')[11:16]


def relatorio_pdf(rel, empresa):
    s = rel['sessao']
    rp = RelatorioPDF('Fechamento de caixa', empresa,
                      'Operador: %s · dia %s' % (s['usuario'], util.data_br(s['data'])),
                      assinaturas=['Operador: %s' % s['usuario'], 'Gerência / conferência'])
    e = rp.e
    historia = [Paragraph('Aberto em %s · fechado em %s' % (_hora(s.get('aberto_em')) or '—', _hora(s.get('fechado_em')) or '—'), e['sub']),
                Spacer(1, 4)]

    historia.append(Paragraph('Recebimentos em DINHEIRO (com troco)', e['h2']))
    if rel['dinheiro']:
        linhas = [[_hora(i['pago_em']), i['cliente'], i['procedimento'] or '', i['convenio'] or '', i['nota_fiscal'] or '',
                   util.moeda(i['valor']), util.moeda(i['valor_recebido']), util.moeda(i['troco'])] for i in rel['dinheiro']]
        historia.append(rp.tabela(['Hora', 'Cliente', 'Procedimento', 'Convênio', 'NF', 'Valor', 'Recebido', 'Troco'], linhas,
                                  [13, 42, 30, 22, 16, 17, 17, 16],
                                  totais=['TOTAL', '', '', '', '', util.moeda(rel['dinheiro_devido']),
                                          util.moeda(rel['dinheiro_recebido']), util.moeda(rel['troco'])],
                                  direita=(5, 6, 7)))
    else:
        historia.append(Paragraph('Nenhum recebimento em dinheiro neste caixa.', e['nota']))

    historia.append(Paragraph('Recebimentos em PIX', e['h2']))
    if rel['pix']:
        linhas = [[_hora(i['pago_em']), i['cliente'], i['procedimento'] or '', i['convenio'] or '', i['nota_fiscal'] or '',
                   util.moeda(i['valor'])] for i in rel['pix']]
        historia.append(rp.tabela(['Hora', 'Cliente', 'Procedimento', 'Convênio', 'NF', 'Valor'], linhas,
                                  [13, 56, 40, 26, 20, 25], totais=['TOTAL', '', '', '', '', util.moeda(rel['pix_total'])],
                                  direita=(5,)))
    else:
        historia.append(Paragraph('Nenhum recebimento em PIX neste caixa.', e['nota']))

    historia.append(Paragraph('Resumo para conferência', e['h2']))
    resumo = [
        ['Fundo de troco (abertura)', util.moeda(rel['fundo'])],
        ['Dinheiro recebido dos clientes', util.moeda(rel['dinheiro_recebido'])],
        ['(-) Troco dado', util.moeda(rel['troco'])],
        ['Dinheiro líquido recebido', util.moeda(rel['dinheiro_liquido'])],
        ['Dinheiro que deve haver no caixa (fundo + líquido)', util.moeda(rel['esperado_dinheiro'])],
        ['PIX recebido', util.moeda(rel['pix_total'])],
    ]
    historia.append(rp.tabela(['Item', 'Valor'], resumo, [130, 50],
                              totais=['TOTAL FATURADO NO CAIXA (dinheiro devido + PIX)', util.moeda(rel['total'])], direita=(1,)))
    historia.append(Spacer(1, 4))
    historia.append(Paragraph('Quantidade de recebimentos: %d. Confira o dinheiro físico com “Dinheiro que deve haver no caixa”.'
                              % rel['quantidade'], e['nota']))
    return rp.bytes(historia)
