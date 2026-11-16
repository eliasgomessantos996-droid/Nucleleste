"""PDF do pedido de compra do estoque, no modelo comum de relatórios (RelatorioPDF)."""
from __future__ import annotations

from reportlab.platypus import Paragraph, Spacer

from . import estoque as est, estoque_pedidos, fornecedores, util
from .relatorio_base import RelatorioPDF, planilha, validacao_padrao, xlsx_bytes


def _texto(v):
    """Texto seguro para Paragraph do reportlab (escapa &, < e >)."""
    return str(v if v is not None else '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _fornecedor_txt(pedido):
    f = pedido.get('fornecedor')
    if not f:
        return pedido.get('fornecedor_nome') or 'Não informado'
    partes = [f['nome']]
    if f.get('cnpj'):
        partes.append('CNPJ %s' % fornecedores.cnpj_formatado(f['cnpj']))
    if f.get('telefone'):
        partes.append('Tel. %s' % f['telefone'])
    if f.get('email'):
        partes.append(f['email'])
    endereco = ', '.join(p for p in (f.get('endereco'), f.get('cidade'), f.get('uf')) if p)
    if endereco:
        partes.append(endereco)
    return ' · '.join(partes)


def pedido_pdf(pedido, itens, empresa, por):
    """`pedido` vem de estoque_pedidos.completo (com 'fornecedor' e 'total'); `itens` são as linhas do pedido."""
    rp = RelatorioPDF('Pedido de compra %s' % pedido['numero'], empresa,
                      'Pedido %s · %s' % (pedido['numero'], util.data_br(pedido['data'])),
                      assinaturas=['Solicitante', 'Direção'])
    e = rp.e
    situacao = estoque_pedidos.STATUS_NOMES.get(pedido['status'], pedido['status'])
    historia = [
        Paragraph('Pedido de compra nº %s' % _texto(pedido['numero']), e['titulo']),
        Paragraph('Data: %s · Situação: %s' % (util.data_br(pedido['data']), situacao), e['sub']),
        Paragraph('Fornecedor', e['h2']),
        Paragraph(_texto(_fornecedor_txt(pedido)), e['cel']),
        Paragraph('Itens', e['h2']),
        rp.tabela(['Item', 'Unidade', 'Qtd', 'Valor unit. (R$)', 'Total (R$)'],
                  [[i['item_nome'], i['unidade'] or '', est.qtd_txt(i['qtd']), util.moeda(i['valor_unitario']) or '-', util.moeda(i['total'])]
                   for i in itens],
                  [84, 24, 20, 28, 28], direita=(2, 3, 4),
                  totais=['TOTAL DO PEDIDO', '', '', '', util.moeda(pedido['total'])]),
    ]
    if pedido.get('condicoes'):
        historia += [Paragraph('Condições de pagamento e prazo', e['h2']), Paragraph(_texto(pedido['condicoes']), e['cel'])]
    if pedido.get('observacao'):
        historia += [Paragraph('Observação', e['h2']), Paragraph(_texto(pedido['observacao']), e['cel'])]
    historia.append(Paragraph('Emitido por %s em %s.' % (_texto(por), rp.gerado), e['nota']))
    return rp.bytes(historia)


# ------------------------------------------------------------------ relatórios, escrituração e preços
_esc = _texto


def _d(v):
    """'2026-10-27' ou '2026-10-27 14:05:00' -> '27/10/2026' (ou com hora)."""
    if not v:
        return ''
    return '%s/%s/%s%s' % (v[8:10], v[5:7], v[:4], (' ' + v[11:16]) if len(v) > 10 else '')


def _qtd(n):
    return est.qtd_txt(n) if n else ''


def _periodo_rel(rel):
    if not rel['de'] and not rel['ate']:
        return 'Posição em %s' % _d(rel['hoje'])
    txt = 'Período de %s a %s' % (_d(rel['de']) or 'o início', _d(rel['ate']) or _d(rel['hoje']))
    return txt + (' · Tipo: %s' % rel['tipo'].capitalize() if rel['tipo'] else ' · Todos os tipos')


def _validacao(titulo, por):
    return validacao_padrao(documento=titulo, por=por)


def relatorios_pdf(rel, empresa, por):
    """Relatório do estoque em paisagem: posição, abaixo do mínimo, movimentação, saídas por motivo e validades."""
    titulo = 'Relatórios do estoque'
    rp = RelatorioPDF(titulo, empresa, _periodo_rel(rel), paisagem=True, validacao=_validacao(titulo, por))
    e = rp.e
    pos = rel['posicao']
    historia = [Paragraph('Posição atual do estoque', e['h2']),
                rp.tabela(['Item', 'Tipo', 'Unid.', 'Saldo', 'Último valor (R$)', 'Valor em estoque (R$)', 'Situação'],
                          [[i['nome'], i['tipo'].capitalize(), i['unidade'], est.qtd_txt(i['saldo']), util.moeda(i['ultimo_valor']) or '-',
                            util.moeda(i['valor']), {'ok': 'OK', 'abaixo': 'Abaixo do mínimo', 'zerado': 'Zerado'}[i['situacao']]] for i in pos]
                          or [['Nenhum item.', '', '', '', '', '', '']],
                          [84, 26, 16, 26, 34, 42, 37], direita=(3, 4, 5), totais=['TOTAL', '', '', '', '', util.moeda(rel['valor_total']), '']),
                Paragraph('Itens abaixo do mínimo', e['h2'])]
    if rel['abaixo']:
        historia.append(rp.tabela(['Item', 'Tipo', 'Unid.', 'Saldo', 'Mínimo', 'Falta para o mínimo'],
                                  [[i['nome'], i['tipo'].capitalize(), i['unidade'], est.qtd_txt(i['saldo']), est.qtd_txt(i['estoque_minimo']),
                                    est.qtd_txt(i['falta'])] for i in rel['abaixo']],
                                  [100, 34, 24, 30, 30, 47], direita=(3, 4, 5)))
    else:
        historia.append(Paragraph('Nenhum item abaixo do mínimo.', e['nota']))
    mov = rel['mov']
    historia += [Paragraph('Movimentação do período', e['h2']),
                 rp.tabela(['Item', 'Unid.', 'Entradas', 'Saídas', 'Ajustes (+/-)', 'Saldo do período'],
                           [[i['nome'], i['unidade'], est.qtd_txt(i['entradas']), est.qtd_txt(i['saidas']), _sinal(i['ajustes']),
                             _sinal(i['saldo'])] for i in mov['itens']] or [['Nenhuma movimentação no período.', '', '', '', '', '']],
                           [110, 24, 34, 34, 34, 29], direita=(2, 3, 4, 5),
                           totais=['TOTAL', '', est.qtd_txt(mov['totais']['entradas']), est.qtd_txt(mov['totais']['saidas']),
                                   _sinal(mov['totais']['ajustes']), _sinal(mov['totais']['saldo'])]),
                 Paragraph('Saídas por motivo', e['h2']),
                 rp.tabela(['Item'] + list(est.MOTIVOS_SAIDA) + ['Total'],
                           [[i['nome']] + [_qtd(i['motivos'][m]) for m in est.MOTIVOS_SAIDA] + [_qtd(i['saidas'])] for i in mov['itens'] if i['saidas']]
                           or [['Nenhuma saída no período.'] + [''] * (len(est.MOTIVOS_SAIDA) + 1)],
                           [85] + [30] * len(est.MOTIVOS_SAIDA) + [30], direita=tuple(range(1, len(est.MOTIVOS_SAIDA) + 2)),
                           totais=['TOTAL'] + [_qtd(mov['totais']['motivos'][m]) for m in est.MOTIVOS_SAIDA] + [_qtd(mov['totais']['saidas'])]),
                 Paragraph('Validades a vencer (até %d dias ou já vencidas)' % _dias_validade(), e['h2'])]
    if rel['validades']:
        historia.append(rp.tabela(['Item', 'Lote', 'Validade', 'Saldo', 'Situação'],
                                  [[v['nome'], v['lote'], _d(v['validade']), est.qtd_txt(v['saldo']),
                                    'Vencida' if v['vencido'] else 'Vence em %d dia(s)' % v['dias']] for v in rel['validades']],
                                  [100, 46, 30, 30, 59], direita=(3,)))
    else:
        historia.append(Paragraph('Nenhum lote vencido ou perto de vencer.', e['nota']))
    return rp.bytes(historia)


def _sinal(n):
    return ('+' if n > 0 else '') + est.qtd_txt(n) if n else '0'


def _dias_validade():
    from .estoque_relatorios import DIAS_VALIDADE
    return DIAS_VALIDADE


def relatorios_xlsx(rel, empresa):
    from openpyxl import Workbook
    from .estoque_relatorios import DIAS_VALIDADE
    per = _periodo_rel(rel)
    wb = Workbook()
    ws = wb.active
    ws.title = 'Posição'
    planilha(ws, 'Posição atual do estoque', empresa, per, ['Item', 'Tipo', 'Unidade', 'Saldo', 'Último valor (R$)', 'Valor em estoque (R$)', 'Situação'],
             [[i['nome'], i['tipo'].capitalize(), i['unidade'], i['saldo'], i['ultimo_valor'] or 0, i['valor'],
               {'ok': 'OK', 'abaixo': 'Abaixo do mínimo', 'zerado': 'Zerado'}[i['situacao']]] for i in rel['posicao']],
             [40, 14, 10, 12, 16, 20, 18], totais=['TOTAL', '', '', '', '', rel['valor_total'], ''],
             formatos={3: '#,##0.###', 4: '#,##0.00', 5: '#,##0.00'})
    abaixo = wb.create_sheet('Abaixo do mínimo')
    planilha(abaixo, 'Itens abaixo do mínimo', empresa, per, ['Item', 'Tipo', 'Unidade', 'Saldo', 'Mínimo', 'Falta para o mínimo'],
             [[i['nome'], i['tipo'].capitalize(), i['unidade'], i['saldo'], i['estoque_minimo'], i['falta']] for i in rel['abaixo']],
             [40, 14, 10, 12, 12, 20], formatos={3: '#,##0.###', 4: '#,##0.###', 5: '#,##0.###'})
    mov = rel['mov']
    det = wb.create_sheet('Movimentação')
    planilha(det, 'Movimentação do período', empresa, per, ['Item', 'Unidade', 'Entradas', 'Saídas', 'Ajustes (+/-)', 'Saldo do período'],
             [[i['nome'], i['unidade'], i['entradas'], i['saidas'], i['ajustes'], i['saldo']] for i in mov['itens']],
             [40, 10, 14, 14, 14, 16], totais=['TOTAL', '', mov['totais']['entradas'], mov['totais']['saidas'], mov['totais']['ajustes'],
                                              mov['totais']['saldo']],
             formatos={2: '#,##0.###', 3: '#,##0.###', 4: '#,##0.###', 5: '#,##0.###'})
    mot = wb.create_sheet('Saídas por motivo')
    planilha(mot, 'Saídas por motivo', empresa, per, ['Item'] + list(est.MOTIVOS_SAIDA) + ['Total'],
             [[i['nome']] + [i['motivos'][m] for m in est.MOTIVOS_SAIDA] + [i['saidas']] for i in mov['itens'] if i['saidas']],
             [40] + [13] * (len(est.MOTIVOS_SAIDA) + 1), formatos={k: '#,##0.###' for k in range(1, len(est.MOTIVOS_SAIDA) + 2)})
    val = wb.create_sheet('Validades')
    planilha(val, 'Validades a vencer (até %d dias ou já vencidas)' % DIAS_VALIDADE, empresa, per, ['Item', 'Lote', 'Validade', 'Saldo', 'Situação'],
             [[v['nome'], v['lote'], _d(v['validade']), v['saldo'], 'Vencida' if v['vencido'] else 'Vence em %d dia(s)' % v['dias']]
              for v in rel['validades']], [40, 16, 14, 12, 20], formatos={3: '#,##0.###'})
    return xlsx_bytes(wb)


def escrituracao_pdf(blocos, empresa, de, ate, por):
    """Livro de movimentação: termo de abertura, um quadro por item (saldo inicial, movimentos e saldo final) e termo de
    encerramento, com o quadro de validação e as assinaturas."""
    titulo = 'Escrituração do estoque'
    periodo = 'Período de %s a %s' % (_d(de) or 'o início', _d(ate) or _d(date_hoje()))
    rp = RelatorioPDF(titulo, empresa, periodo, paisagem=True, validacao=_validacao(titulo, por))
    e = rp.e
    n_mov = sum(len(b['linhas']) for b in blocos)
    historia = [Paragraph('Termo de abertura: livro de movimentação do estoque de materiais e medicamentos, para registro das '
                          'entradas, saídas e ajustes de cada item no período acima. Saldo inicial é o saldo no começo do período.', e['sub']),
                Spacer(1, 4)]
    if not blocos:
        historia.append(Paragraph('Nenhum item com movimentação ou saldo no período.', e['nota']))
    cab = ['Data e hora', 'Documento / nota', 'Tipo', 'Motivo / fornecedor', 'Entrada', 'Saída', 'Saldo após', 'Valor unit. (R$)', 'Usuário']
    for b in blocos:
        historia.append(Paragraph('%s · %s · %s' % (_esc(b['nome']), _esc(b['tipo'].capitalize()), _esc(b['unidade'])), e['h2']))
        linhas = [['', '', '', 'SALDO INICIAL', '', '', est.qtd_txt(b['inicial']), '', '']]
        linhas += [[_d(l['data_hora']), l['documento'], l['tipo'], l['motivo'], _qtd(l['entrada']), _qtd(l['saida']), est.qtd_txt(l['saldo']),
                    util.moeda(l['valor']) or '', l['usuario']] for l in b['linhas']]
        historia.append(rp.tabela(cab, linhas, [24, 32, 20, 56, 20, 20, 24, 24, 25], direita=(4, 5, 6, 7),
                                  totais=['SALDO FINAL', '', '', 'Entradas %s · Saídas %s' % (_qtd(b['entradas']) or '0', _qtd(b['saidas']) or '0'),
                                          _qtd(b['entradas']), _qtd(b['saidas']), est.qtd_txt(b['final']), '', '']))
        historia.append(Paragraph('Conferência: saldo inicial + entradas − saídas = saldo final: %s.'
                                  % ('confere' if b['confere'] else 'NÃO CONFERE, verificar'), e['nota']))
    historia.append(Paragraph('Termo de encerramento: encerra-se este livro em %s, com %d item(ns) e %d movimento(s) no período.'
                              % (_d(date_hoje()), len(blocos), n_mov), e['sub']))
    return rp.bytes(historia)


def date_hoje():
    from datetime import date
    return date.today().isoformat()


def escrituracao_xlsx(blocos, empresa, de, ate):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = 'Escrituração'
    periodo = 'Período de %s a %s' % (_d(de) or 'o início', _d(ate) or _d(date_hoje()))
    linhas = []
    for b in blocos:
        nome = '%s (%s, %s)' % (b['nome'], b['tipo'].capitalize(), b['unidade'])
        linhas.append([nome, '', '', 'SALDO INICIAL', '', '', b['inicial'], '', ''])
        linhas += [[nome, _d(l['data_hora']), l['documento'], l['tipo'], l['motivo'], l['entrada'], l['saida'], l['saldo'],
                    l['valor'] or '', l['usuario']] for l in b['linhas']]
        linhas.append([nome, '', '', 'SALDO FINAL', b['entradas'], b['saidas'], b['final'], '', ''])
    planilha(ws, 'Escrituração do estoque', empresa, periodo,
             ['Item', 'Data e hora', 'Documento / nota', 'Tipo', 'Motivo / fornecedor', 'Entrada', 'Saída', 'Saldo após', 'Valor unit. (R$)', 'Usuário'],
             linhas, [36, 16, 18, 12, 30, 12, 12, 12, 14, 16], formatos={5: '#,##0.###', 6: '#,##0.###', 7: '#,##0.###', 8: '#,##0.00'})
    return xlsx_bytes(wb)


def _estudo_resumo_cab():
    return ['Item', 'Último valor (R$)', 'Data', 'Fornecedor do último', 'Menor (R$)', 'Média (R$)', 'Maior (R$)', 'Variação últ. compras',
            'Entradas com valor', 'Fornecedor mais barato']


def _estudo_resumo_linha(a):
    mb = a['mais_barato']
    return [a['nome'], util.moeda(a['ultimo']), _d(a['ultimo_data']), a['ultimo_fornecedor'], util.moeda(a['menor']), util.moeda(a['media']),
            util.moeda(a['maior']), ('%s%%' % util.moeda(a['variacao'])) if a['variacao'] is not None else '-', str(a['compras']),
            '%s · R$ %s' % (mb['nome'], util.moeda(mb['ultimo']))]


def precos_pdf(estudo_itens, empresa, periodo, por):
    """Estudo de preços: resumo de todos os itens e, para cada um, o quadro por fornecedor e o histórico com o gráfico."""
    from .estoque_relatorios import grafico
    titulo = 'Estudo de preços do estoque'
    rp = RelatorioPDF(titulo, empresa, periodo or 'Todo o período', paisagem=True, validacao=_validacao(titulo, por))
    e = rp.e
    historia = [Paragraph('Resumo por item', e['h2'])]
    if estudo_itens:
        historia.append(rp.tabela(_estudo_resumo_cab(), [_estudo_resumo_linha(a) for a in estudo_itens],
                                  [44, 20, 18, 36, 18, 18, 18, 20, 16, 37], direita=(1, 4, 5, 6, 8)))
    else:
        historia.append(Paragraph('Nenhuma entrada com valor pago no período.', e['nota']))
    for a in estudo_itens:
        historia += [Paragraph('%s · %s · %s' % (_esc(a['nome']), _esc(a['tipo'].capitalize()), _esc(a['unidade'])), e['h2']),
                     rp.tabela(['Fornecedor', 'Último valor (R$)', 'Data da última', 'Qtd. da última', 'Média (R$)', 'Entradas'],
                               [[c['nome'], util.moeda(c['ultimo']), _d(c['data']), est.qtd_txt(c['qtd']), util.moeda(c['media']), str(c['compras'])]
                                for c in a['comparativo']],
                               [90, 32, 32, 32, 32, 47], direita=(1, 3, 4, 5)),
                     rp.tabela(['Data', 'Fornecedor', 'Nota fiscal', 'Qtd.', 'Valor unit. (R$)'],
                               [[_d(h['data_hora']), h['nome'], h['nota'], est.qtd_txt(h['qtd']), util.moeda(h['valor'])] for h in a['historico']],
                               [30, 110, 50, 35, 40], direita=(3, 4))]
    return rp.bytes(historia)


def precos_xlsx(estudo_itens, empresa, periodo):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = 'Resumo'
    planilha(ws, 'Estudo de preços do estoque', empresa, periodo or 'Todo o período',
             ['Item', 'Tipo', 'Unidade', 'Último valor (R$)', 'Data da última', 'Fornecedor do último', 'Menor (R$)', 'Média (R$)', 'Maior (R$)',
              'Variação % (últimas duas)', 'Entradas com valor', 'Fornecedor mais barato', 'Valor do mais barato (R$)'],
             [[a['nome'], a['tipo'].capitalize(), a['unidade'], a['ultimo'], _d(a['ultimo_data']), a['ultimo_fornecedor'], a['menor'], a['media'],
               a['maior'], a['variacao'] if a['variacao'] is not None else '', a['compras'], a['mais_barato']['nome'], a['mais_barato']['ultimo']]
              for a in estudo_itens],
             [36, 14, 10, 16, 14, 30, 12, 12, 12, 16, 14, 30, 18],
             formatos={3: '#,##0.00', 6: '#,##0.00', 7: '#,##0.00', 8: '#,##0.00', 9: '#,##0.00', 12: '#,##0.00'})
    forn = wb.create_sheet('Fornecedores')
    linhas = [[a['nome'], c['nome'], c['ultimo'], _d(c['data']), c['qtd'], c['media'], c['compras']] for a in estudo_itens for c in a['comparativo']]
    planilha(forn, 'Preços por fornecedor', empresa, periodo or 'Todo o período',
             ['Item', 'Fornecedor', 'Último valor (R$)', 'Data da última', 'Qtd. da última', 'Média (R$)', 'Entradas'], linhas,
             [36, 30, 16, 14, 14, 14, 12], formatos={2: '#,##0.00', 4: '#,##0.00', 5: '#,##0.00'})
    hist = wb.create_sheet('Histórico')
    linhas = [[a['nome'], _d(h['data_hora']), h['nome'], h['nota'], h['qtd'], h['valor']] for a in estudo_itens for h in a['historico']]
    planilha(hist, 'Histórico de preços', empresa, periodo or 'Todo o período',
             ['Item', 'Data e hora', 'Fornecedor', 'Nota fiscal', 'Qtd.', 'Valor unit. (R$)'], linhas,
             [36, 16, 30, 16, 12, 16], formatos={4: '#,##0.###', 5: '#,##0.00'})
    return xlsx_bytes(wb)
