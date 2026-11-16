"""Relatório de satisfação do cliente (ONA) em PDF e Excel, no modelo comum de relatórios."""
from __future__ import annotations

from reportlab.platypus import Paragraph, Spacer

from . import util
from .relatorio_base import RelatorioPDF, VERDE_XLSX, ZEBRA_XLSX, _esc, planilha, validacao_padrao, xlsx_bytes

CAB_PERGUNTAS = ['Pergunta', 'Respostas', 'Ótimo', 'Bom', 'Ruim', 'Péssimo', 'Satisfação (Ótimo+Bom)', 'Nota média (0 a 10)']
CAB_SEGURANCA = ['Pergunta', 'Respostas', 'Sim', 'Não', '% Sim']
CAB_EXAME = ['Exame', 'Respostas', 'Satisfação (Ótimo+Bom)']
CAB_NPS = ['Indicador', 'Resultado']
CAB_PERFIL = ['Atendimento', 'Respostas', 'Quem respondeu', 'Respostas']


def _p(v):
    return '—' if v is None else ('%.1f%%' % v).replace('.', ',')


def _n(v):
    return '—' if v is None else ('%.1f' % v).replace('.', ',')


def _periodo(ind):
    return '%s a %s' % (util.data_br(ind['de']), util.data_br(ind['ate']))


def _linhas(ind):
    return [[l['texto'], l['total'], l['otimo'], l['bom'], l['ruim'], l['pessimo'], _p(l['satisfacao']), _n(l['media'])]
            for l in ind['perguntas'] + [ind['geral']]]


def _sim_nao_linhas(ind):
    return [[s['texto'], s['total'], s['sim'], s['nao'], _p(s['pct_sim'])] for s in ind['seguranca']]


def _nps_linhas_pdf(nps):
    """Promotores, neutros, detratores, índice e nota média, com a contagem e o percentual de cada grupo."""
    tot = nps['total']

    def grupo(n):
        return '%d (%s)' % (n, _p(round(100.0 * n / tot, 1) if tot else None))
    return [['Promotores (9 a 10)', grupo(nps['promotores'])], ['Neutros (7 a 8)', grupo(nps['neutros'])],
            ['Detratores (0 a 6)', grupo(nps['detratores'])], ['Índice NPS', _n(nps['indice'])], ['Nota média (0 a 10)', _n(nps['media'])]]


def _perfil_linhas(ind):
    conv, resp = ind['por_atendimento'], ind['por_respondente']
    return [[a, str(conv[a]), b, str(resp[b])] for a, b in zip(conv, resp)]


def relatorio_pdf(ind, respostas, empresa, por=''):
    rp = RelatorioPDF('Satisfação do cliente (ONA)', empresa, _periodo(ind), paisagem=True,
                      validacao=validacao_padrao('Relatório de satisfação do cliente', por))
    e = rp.e
    g = ind['geral']
    origem = ind['por_origem']
    hist = [Paragraph('Pesquisa respondida pelos clientes no celular (QR Code) ou em papel (lançada pela recepção). '
                      'QR Code: %d · impressos: %d. Respostas: %d · satisfação (Ótimo e Bom): %s · '
                      'nota média: %s · elogios: %d · sugestões: %d.' % (origem.get('QRCODE', 0), origem.get('IMPRESSO', 0), ind['respostas'],
                                                                         _p(g['satisfacao']), _n(ind['media']),
                                                                         ind['elogios'], ind['sugestoes']), e['total']), Spacer(1, 4)]
    if ind['perguntas']:
        hist.append(Paragraph('Resultado por pergunta (escala)', e['h2']))
        hist.append(rp.tabela(CAB_PERGUNTAS, [[str(c) for c in l] for l in _linhas(ind)], [92, 18, 16, 16, 16, 18, 34, 32], direita=tuple(range(1, 8))))
    else:
        hist.append(Paragraph('Nenhuma resposta no período.', e['nota']))
    if ind['meses']:
        hist.append(Paragraph('Por mês', e['h2']))
        hist.append(rp.tabela(['Mês', 'Respostas', 'Satisfação (Ótimo+Bom)'],
                              [[m['mes'][5:7] + '/' + m['mes'][:4], str(m['respostas']), _p(m['satisfacao'])] for m in ind['meses']],
                              [30, 30, 50], direita=(1, 2)))
    if ind['seguranca']:
        hist.append(Paragraph('Segurança do paciente (Sim ou Não)', e['h2']))
        hist.append(rp.tabela(CAB_SEGURANCA, [[str(c) for c in l] for l in _sim_nao_linhas(ind)], [130, 22, 22, 22, 46], direita=(1, 2, 3, 4)))
    nps = ind['nps']
    if nps['total']:
        hist.append(Paragraph('Recomendação (nota de 0 a 10)', e['h2']))
        hist.append(rp.tabela(CAB_NPS, _nps_linhas_pdf(nps), [120, 80], direita=(1,)))
        hist.append(Paragraph('O índice NPS é a % de promotores menos a % de detratores. Ele vai de -100 a 100.', e['nota']))
    if ind['por_exame']:
        hist.append(Paragraph('Satisfação por exame', e['h2']))
        hist.append(rp.tabela(CAB_EXAME, [[x['exame'], str(x['respostas']), _p(x['satisfacao'])] for x in ind['por_exame']],
                              [150, 40, 52], direita=(1, 2)))
    if sum(ind['por_atendimento'].values()) or sum(ind['por_respondente'].values()):
        hist.append(Paragraph('Perfil de quem respondeu', e['h2']))
        hist.append(rp.tabela(CAB_PERFIL, [[str(c) for c in l] for l in _perfil_linhas(ind)], [70, 40, 70, 62], direita=(1, 3)))
    comentarios =[r for r in respostas if r['elogio'] or r['sugestao']][:60]
    if comentarios:
        hist.append(Paragraph('Elogios e sugestões recebidos', e['h2']))
        for r in comentarios:
            partes = []
            if r['elogio']:
                partes.append('<b>Elogio:</b> ' + _esc(r['elogio']))
            if r['sugestao']:
                partes.append('<b>Sugestão:</b> ' + _esc(r['sugestao']))
            hist.append(Paragraph('%s — %s' % (util.data_br(r['data']), '<br/>'.join(partes)), e['cel']))
    return rp.bytes(hist)


def relatorio_xlsx(ind, respostas, empresa):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = 'Por pergunta'
    planilha(ws, 'Satisfação do cliente (ONA)', empresa, _periodo(ind), CAB_PERGUNTAS, _linhas(ind), [60, 12, 10, 10, 10, 10, 22, 20])
    ws3 = wb.create_sheet('Segurança e NPS')
    planilha(ws3, 'Segurança do paciente e recomendação (NPS)', empresa, _periodo(ind), CAB_SEGURANCA,
             [[s['texto'], s['total'], s['sim'], s['nao'], s['pct_sim']] for s in ind['seguranca']], [60, 12, 10, 10, 14],
             formatos={4: '0.0"%"'})
    nps = ind['nps']
    _bloco_xlsx(ws3, 'Recomendação (nota de 0 a 10)', CAB_NPS,
                [['Promotores (9 a 10)', nps['promotores']], ['Neutros (7 a 8)', nps['neutros']], ['Detratores (0 a 6)', nps['detratores']],
                 ['Índice NPS', nps['indice']], ['Nota média (0 a 10)', nps['media']]])
    ws4 = wb.create_sheet('Por exame')
    planilha(ws4, 'Satisfação por exame', empresa, _periodo(ind), CAB_EXAME,
             [[x['exame'], x['respostas'], x['satisfacao']] for x in ind['por_exame']], [60, 12, 22], formatos={2: '0.0"%"'})
    ws2 = wb.create_sheet('Respostas')
    linhas = []
    for r in respostas:
        linhas.append([util.data_br(r['data']), r['nome'], r['telefone'], r['nota'], ' | '.join('%s: %s' % (i['ordem'], i['opcao']) for i in r['itens']),
                       r['elogio'], r['sugestao'], 'Sim' if r['revisada'] else 'Não',
                       r['origem_rotulo'], r['exame'], r['atendimento'], r['respondente'], r['nps'], r['lancado_por'] or ''])
    planilha(ws2, 'Respostas da pesquisa de satisfação', empresa, _periodo(ind),
             ['Data', 'Nome', 'Telefone', 'Nota (0 a 10)', 'Respostas por pergunta', 'Elogio', 'Sugestão', 'Revisada',
              'Origem', 'Exame', 'Atendimento', 'Quem respondeu', 'NPS (0 a 10)', 'Lançado por'], linhas,
             [12, 24, 16, 14, 40, 50, 50, 10, 12, 22, 14, 16, 12, 16])
    return xlsx_bytes(wb)


def _bloco_xlsx(ws, titulo, cab, linhas):
    """Segunda tabela numa aba que já tem a primeira (no mesmo modelo: título verde, cabeçalho verde, linhas com bordas)."""
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    borda = Side(style='thin', color='9AA8A0')
    caixa = Border(left=borda, right=borda, top=borda, bottom=borda)
    ws.append([])
    ws.append([titulo])
    ws.cell(row=ws.max_row, column=1).font = Font(bold=True, size=12, color=VERDE_XLSX)
    ws.append(cab)
    for col in range(1, len(cab) + 1):
        c = ws.cell(row=ws.max_row, column=col)
        c.font = Font(bold=True, color='FFFFFF')
        c.fill = PatternFill('solid', fgColor=VERDE_XLSX)
        c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        c.border = caixa
    for k, linha in enumerate(linhas):
        ws.append(list(linha))
        for col in range(1, len(cab) + 1):
            c = ws.cell(row=ws.max_row, column=col)
            c.border = caixa
            if k % 2 == 1:
                c.fill = PatternFill('solid', fgColor=ZEBRA_XLSX)
