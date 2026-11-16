"""Relatórios da Qualidade em PDF e Excel (modelo comum: cabeçalho com a clínica, período, rodapé com página e data).

Todos os PDFs terminam com o quadro "Validação e assinaturas" (elaboração, revisão e aprovação, com nome, cargo/registro, data e
assinatura) para apresentação a auditorias e órgãos de fiscalização, e trazem a análise da ferramenta além dos dados."""
from __future__ import annotations

from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, Spacer, Table, TableStyle

from . import qualidade as q
from . import qualidade_graficos as gr
from . import util
from .relatorio_base import RelatorioPDF, planilha, validacao_padrao, xlsx_bytes

LARGURA_PAISAGEM = 757      # pontos úteis em A4 paisagem
LARGURA_RETRATO = 516


def _p(v, un='%'):
    if v is None:
        return '—'
    if un == '%':
        return ('%.1f%%' % v).replace('.', ',')
    if un == 'h':
        return ('%.1f h' % v).replace('.', ',')
    if un == 'nota':
        return ('%.1f' % v).replace('.', ',')
    return ('%g' % v).replace('.', ',')


def _per(de, ate):
    return '%s a %s' % (util.data_br(de), util.data_br(ate))


def util_esc(t):
    return str(t or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _sem_simbolos(t):
    """O PDF usa fontes padrão: troca símbolos que elas não desenham."""
    return str(t).replace('≥', '>=').replace('≤', '<=').replace('★', '*').replace('→', '->')


def _centro(flow):
    flow.hAlign = 'CENTER'
    return flow


def _analise(rp, titulo, frases):
    """Bloco "Análise" com marcadores (frases já escapadas ou simples)."""
    frases = [f for f in frases if f]
    if not frases:
        return []
    return [Paragraph(titulo, rp.e['h2'])] + [Paragraph('• ' + util_esc(f), rp.e['cel']) for f in frases]


SITUACAO = {'ok': 'Na meta', 'atencao': 'Atenção', 'critico': 'Crítico', 'sem_dado': 'Sem dado'}


# ------------------------------------------------------------------ indicadores
def _linhas_kpi(painel):
    return [[i['nome'], _p(i['valor'], i['unidade']), ('≥ ' if i['sentido'] == 'min' else '≤ ') + _p(i['meta'], i['unidade']),
             SITUACAO[i['situacao']], ' | '.join('%s: %s' % (s['rotulo'], _p(s['valor'], i['unidade'])) for s in i['serie'][-3:])]
            for i in painel['indicadores']]


def kpi_pdf(painel, empresa, por=''):
    rp = RelatorioPDF('Indicadores da qualidade (KPI)', empresa, _per(painel['de'], painel['ate']), paisagem=True,
                      validacao=validacao_padrao('Indicadores da qualidade', por))
    e = rp.e
    r = painel['resumo']
    criticos = [i['nome'] for i in painel['indicadores'] if i['situacao'] == 'critico']
    atencao = [i['nome'] for i in painel['indicadores'] if i['situacao'] == 'atencao']
    linhas = [[_sem_simbolos(c) for c in l] for l in _linhas_kpi(painel)]
    hist = [Paragraph('Na meta: %d · Atenção: %d · Crítico: %d · Sem dado: %d' % (r['ok'], r['atencao'], r['critico'], r['sem_dado']), e['total']),
            rp.tabela(['Indicador', 'Valor', 'Meta', 'Situação', 'Últimos meses'], linhas, [80, 24, 26, 22, 115], direita=(1, 2)),
            Spacer(1, 6), Paragraph('Calculado com os dados do próprio sistema. Indicadores "sem dado" dependem de lançamentos na Qualidade.', e['nota'])]
    hist += _analise(rp, 'Análise do período', [
        ('Indicadores críticos (exigem plano de ação): ' + '; '.join(criticos)) if criticos else 'Nenhum indicador crítico no período.',
        ('Indicadores em atenção: ' + '; '.join(atencao)) if atencao else '',
        '%d de %d indicadores com dado estão na meta.' % (r['ok'], r['ok'] + r['atencao'] + r['critico']) if (r['ok'] + r['atencao'] + r['critico']) else
        'Sem dados suficientes para avaliar as metas.'])
    return rp.bytes(hist)


def kpi_xlsx(painel, empresa):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = 'Indicadores'
    planilha(ws, 'Indicadores da qualidade (KPI)', empresa, _per(painel['de'], painel['ate']),
             ['Indicador', 'Valor', 'Meta', 'Situação', 'Últimos meses'], _linhas_kpi(painel), [48, 14, 14, 14, 70])
    return xlsx_bytes(wb)


# ------------------------------------------------------------------ problema / PDCA
def problema_pdf(p, isk, empresa, por=''):
    """Relatório completo de um problema: PDCA, GUT, Ishikawa, 5 Porquês e plano 5W2H."""
    rp = RelatorioPDF('PDCA: %s' % p['titulo'][:80], empresa, 'Situação: %s · Fase: %s' % (p['status'], p['fase']), paisagem=True,
                      validacao=validacao_padrao('PDCA: %s' % p['titulo'][:60], p['responsavel'] or por, revisao=util.data_br(p['prazo']) if p['prazo'] else None))
    e = rp.e
    hist = [Paragraph('Descrição', e['h2']), Paragraph(util_esc(p['descricao'] or '—').replace('\n', '<br/>'), e['cel'])]
    if p['evidencia_lista']:
        hist += [Paragraph('Evidências (dados do sistema)', e['h2'])] + [Paragraph('• ' + util_esc(x), e['cel']) for x in p['evidencia_lista']]
    hist += [Paragraph('Priorização GUT', e['h2']),
             rp.tabela(['Gravidade', 'Urgência', 'Tendência', 'Pontos'], [[str(p['gut_g']), str(p['gut_u']), str(p['gut_t']), str(p['gut'])]],
                       [40, 40, 40, 40], direita=(0, 1, 2, 3)),
             Paragraph('Ciclo PDCA', e['h2']),
             rp.tabela(['Fase', 'Conteúdo'], [['P · Planejar: meta', p['plan_meta']], ['P · Causa', p['plan_causa']],
                                              ['P · Indicador', p['plan_indicador']], ['D · Fazer', p['do_execucao']],
                                              ['C · Checar', '%s %s' % (util.data_br(p['check_data']) if p['check_data'] else '', p['check_resultado'])],
                                              ['A · Agir', p['act_padrao']]], [50, 217]),
             Paragraph('Diagrama de Ishikawa (6M)', e['h2']),
             _centro(gr.ishikawa(isk, LARGURA_PAISAGEM, 380)),
             rp.tabela(['Categoria', 'Causas'], [[g['categoria'], _sem_simbolos(' · '.join(('(principal) ' if c['principal'] else '') + c['texto'] for c in g['causas'])) or '—']
                                                for g in isk['grupos']], [45, 222]),
             Paragraph('Cinco porquês', e['h2']),
             rp.tabela(['Porquê', 'Resposta'], [['%dº' % (i + 1), t or '—'] for i, t in enumerate(p['porques'])], [20, 247]),
             Paragraph('Plano de ação 5W2H', e['h2']),
             rp.tabela(['O quê', 'Por quê', 'Onde', 'Quando', 'Quem', 'Como', 'Custo', 'Situação'],
                       [[a['o_que'], a['por_que'], a['onde'], util.data_br(a['quando']) if a['quando'] else '', a['quem'], a['como'],
                         util.moeda(a['quanto']) if a['quanto'] is not None else '', a['status']] for a in p['acoes']] or [['—'] * 8],
                       [45, 35, 25, 20, 25, 70, 22, 25], direita=(6,))]
    feitas = sum(1 for a in p['acoes'] if a['status'] == 'CONCLUÍDA')
    principais = [c['texto'] for c in p['causas'] if c['principal']]
    hist += _analise(rp, 'Análise', [
        'Prioridade GUT: %d pontos (de 125).' % p['gut'],
        ('Causas principais: ' + '; '.join(principais)) if principais else 'Nenhuma causa foi marcada como principal.',
        ('Causa raiz: ' + p['plan_causa']) if p['plan_causa'] else '',
        'Plano de ação: %d de %d ações concluídas%s.' % (feitas, len(p['acoes']), '; %d atrasada(s)' % sum(1 for a in p['acoes'] if a.get('atrasada'))
                                                         if any(a.get('atrasada') for a in p['acoes']) else '')])
    return rp.bytes(hist)


# ------------------------------------------------------------------ Ishikawa e cinco porquês (ferramentas isoladas)
def ishikawa_pdf(isk, p, empresa, por=''):
    rp = RelatorioPDF('Diagrama de Ishikawa: %s' % isk['problema'][:80], empresa, 'Causas agrupadas pelos 6M', paisagem=True,
                      validacao=validacao_padrao('Diagrama de Ishikawa: %s' % isk['problema'][:60], p.get('responsavel') or por))
    e = rp.e
    total = sum(len(g['causas']) for g in isk['grupos'])
    principais = [c['texto'] for g in isk['grupos'] for c in g['causas'] if c['principal']]
    maior = max(isk['grupos'], key=lambda g: len(g['causas']))
    hist = [_centro(gr.ishikawa(isk, LARGURA_PAISAGEM, 360)),
            rp.tabela(['Categoria (6M)', 'Causas identificadas'], [[g['categoria'], _sem_simbolos(' · '.join(('(principal) ' if c['principal'] else '') + c['texto']
                                                                                                  for c in g['causas'])) or '—'] for g in isk['grupos']],
                      [45, 222])]
    hist += _analise(rp, 'Análise', [
        '%d causa(s) levantada(s) em %d categorias.' % (total, sum(1 for g in isk['grupos'] if g['causas'])),
        ('Categoria com mais causas: %s (%d).' % (maior['categoria'], len(maior['causas']))) if total else 'Nenhuma causa cadastrada ainda.',
        ('Causas principais: ' + '; '.join(principais)) if principais else 'Marque as causas principais para priorizar o plano de ação.',
        ('Causa raiz registrada: ' + p['plan_causa']) if p.get('plan_causa') else ''])
    return rp.bytes(hist)


def porques_pdf(p, empresa, por=''):
    rp = RelatorioPDF('Cinco porquês: %s' % p['titulo'][:80], empresa, 'Análise da causa raiz', paisagem=False,
                      validacao=validacao_padrao('Cinco porquês: %s' % p['titulo'][:60], p['responsavel'] or por))
    preenchidos = sum(1 for t in p['porques'] if t)
    hist = [_centro(gr.porques(p['titulo'], p['porques'], p['plan_causa'], LARGURA_RETRATO, 430))]
    hist += _analise(rp, 'Análise', [
        '%d de 5 porquês respondidos.' % preenchidos,
        ('Causa raiz identificada: ' + p['plan_causa']) if p['plan_causa'] else 'A causa raiz ainda não foi registrada.',
        'A causa raiz deve levar a ações no plano 5W2H (%d ação(ões) vinculada(s)).' % len(p['acoes'])])
    return rp.bytes(hist)


# ------------------------------------------------------------------ 5W2H
def _linhas_acoes(acoes):
    return [[a['problema'] or '—', a['o_que'], a['por_que'], a['onde'], util.data_br(a['quando']) if a['quando'] else '', a['quem'], a['como'],
             util.moeda(a['quanto']) if a['quanto'] is not None else '', a['status'] + (' (ATRASADA)' if a['atrasada'] else '')] for a in acoes]


def plano_pdf(acoes, empresa, por=''):
    rp = RelatorioPDF('Plano de ação 5W2H', empresa, '%d ações' % len(acoes), paisagem=True, validacao=validacao_padrao('Plano de ação 5W2H', por))
    contagem = {}
    for a in acoes:
        contagem[a['status']] = contagem.get(a['status'], 0) + 1
    hist = [rp.tabela(['Problema', 'O quê (What)', 'Por quê (Why)', 'Onde (Where)', 'Quando (When)', 'Quem (Who)', 'Como (How)',
                       'Custo (How much)', 'Situação'], _linhas_acoes(acoes) or [['—'] * 9], [34, 38, 30, 22, 20, 22, 52, 22, 27], direita=(7,))]
    hist += _analise(rp, 'Análise', [
        ' · '.join('%s: %d' % (k.capitalize(), v) for k, v in contagem.items()) if contagem else 'Nenhuma ação cadastrada.',
        '%d ação(ões) atrasada(s).' % sum(1 for a in acoes if a['atrasada']) if any(a['atrasada'] for a in acoes) else 'Nenhuma ação atrasada.',
        '%d ação(ões) sem responsável.' % sum(1 for a in acoes if not a['quem']) if any(not a['quem'] for a in acoes) else ''])
    return rp.bytes(hist)


def plano_xlsx(acoes, empresa):
    from openpyxl import Workbook
    wb = Workbook()
    planilha(wb.active, 'Plano de ação 5W2H', empresa, '%d ações' % len(acoes),
             ['Problema', 'O quê', 'Por quê', 'Onde', 'Quando', 'Quem', 'Como', 'Custo', 'Situação'], _linhas_acoes(acoes),
             [34, 36, 30, 20, 12, 18, 50, 14, 20])
    return xlsx_bytes(wb)


# ------------------------------------------------------------------ GUT
def gut_pdf(lista, empresa, por=''):
    rp = RelatorioPDF('Matriz GUT: priorização dos problemas', empresa, '%d problemas abertos' % len(lista), validacao=validacao_padrao('Matriz GUT', por))
    hist = [rp.tabela(['#', 'Problema', 'G', 'U', 'T', 'G×U×T', 'Situação'],
                      [[str(i + 1), p['titulo'], str(p['gut_g']), str(p['gut_u']), str(p['gut_t']), str(p['gut']), p['status']]
                       for i, p in enumerate(lista)] or [['—'] * 7], [8, 92, 10, 10, 10, 18, 30], direita=(2, 3, 4, 5))]
    hist += _analise(rp, 'Análise', [
        ('Maior prioridade: %s (%d pontos).' % (lista[0]['titulo'], lista[0]['gut'])) if lista else 'Nenhum problema aberto para priorizar.',
        '%d problema(s) com 60 pontos ou mais (tratar primeiro).' % sum(1 for p in lista if p['gut'] >= 60) if any(p['gut'] >= 60 for p in lista) else '',
        'G = gravidade, U = urgência e T = tendência, de 1 a 5; o produto G×U×T vai de 1 a 125.'])
    return rp.bytes(hist)


# ------------------------------------------------------------------ riscos
def _linhas_riscos(lista):
    return [[r['titulo'], r['processo'], str(r['probabilidade']), str(r['impacto']), '%d · %s' % (r['pontos'], r['nivel']), r['resposta'], r['acao'],
             r['responsavel'], util.data_br(r['prazo']) if r['prazo'] else '', r['status']] for r in lista]


def riscos_pdf(lista, empresa, por=''):
    rp = RelatorioPDF('Matriz de risco', empresa, '%d riscos' % len(lista), paisagem=True, validacao=validacao_padrao('Matriz de risco', por))
    ativos = [r for r in lista if r['status'] != 'ENCERRADO']
    niveis = {}
    for r in ativos:
        niveis[r['nivel']] = niveis.get(r['nivel'], 0) + 1
    hist = [Paragraph('Mapa de calor (probabilidade x impacto, riscos não encerrados)', rp.e['h2']), _centro(gr.matriz_risco(q.matriz_risco(lista), 300, 270)),
            rp.tabela(['Risco', 'Processo', 'P', 'I', 'Nível', 'Resposta', 'Ação', 'Responsável', 'Prazo', 'Situação'],
                      _linhas_riscos(lista) or [['—'] * 10], [40, 25, 8, 8, 22, 20, 60, 26, 18, 20], direita=(2, 3))]
    topo = [r for r in ativos if r['pontos'] >= 15][:5]
    hist += _analise(rp, 'Análise', [
        ' · '.join('%s: %d' % (n, niveis.get(n, 0)) for n in ('Crítico', 'Alto', 'Moderado', 'Baixo')) if ativos else 'Nenhum risco ativo cadastrado.',
        ('Riscos críticos (tratar de imediato): ' + '; '.join(r['titulo'] for r in topo)) if topo else '',
        '%d risco(s) ativo(s) sem ação definida.' % sum(1 for r in ativos if not r['acao']) if any(not r['acao'] for r in ativos) else '',
        'Nível = probabilidade x impacto (1 a 25): crítico a partir de 15, alto de 10 a 14, moderado de 5 a 9 e baixo abaixo de 5.'])
    return rp.bytes(hist)


def riscos_xlsx(lista, empresa):
    from openpyxl import Workbook
    wb = Workbook()
    planilha(wb.active, 'Matriz de risco', empresa, '%d riscos' % len(lista),
             ['Risco', 'Processo', 'Probabilidade', 'Impacto', 'Nível', 'Resposta', 'Ação', 'Responsável', 'Prazo', 'Situação'],
             _linhas_riscos(lista), [36, 22, 12, 10, 16, 14, 50, 20, 12, 14])
    return xlsx_bytes(wb)


# ------------------------------------------------------------------ Pareto
def pareto_pdf(p, empresa, por=''):
    rp = RelatorioPDF('Gráfico de Pareto: %s' % p['nome'], empresa, _per(p['de'], p['ate']), validacao=validacao_padrao('Gráfico de Pareto', por))
    e = rp.e
    classe_a = [i for i in p['itens'] if i['classe'] == 'A']
    hist = [_centro(gr.pareto(p['itens'], LARGURA_RETRATO, 250)),
            rp.tabela(['Item', 'Quantidade', '%', '% acumulado', 'Classe'],
                      [[i['rotulo'], ('%g' % i['valor']).replace('.', ','), _p(i['pct']), _p(i['acum']), i['classe']] for i in p['itens']] or [['—'] * 5],
                      [80, 26, 22, 26, 16], direita=(1, 2, 3)),
            Spacer(1, 6),
            Paragraph('Classe A: itens que somam os primeiros 80% (os "poucos vitais"); B até 95%; C o restante.', e['nota'])]
    hist += _analise(rp, 'Análise', [
        ('Classe A (foco do plano de ação): ' + '; '.join('%s (%s)' % (i['rotulo'], _p(i['pct'])) for i in classe_a)) if classe_a else 'Sem dados no período.',
        ('%d item(ns) respondem por %s das ocorrências.' % (len(classe_a), _p(classe_a[-1]['acum']))) if classe_a else ''])
    return rp.bytes(hist)


def pareto_xlsx(p, empresa):
    from openpyxl import Workbook
    wb = Workbook()
    planilha(wb.active, 'Pareto: %s' % p['nome'], empresa, _per(p['de'], p['ate']), ['Item', 'Quantidade', '%', '% acumulado', 'Classe'],
             [[i['rotulo'], i['valor'], i['pct'], i['acum'], i['classe']] for i in p['itens']], [46, 14, 10, 14, 10])
    return xlsx_bytes(wb)


# ------------------------------------------------------------------ ocorrências
def _linhas_ocor(lista):
    return [[util.data_br(o['data']), o['tipo'], o['gravidade'], o['setor'], o['exame'], o['descricao'], o['acao_imediata'], o['status']] for o in lista]


def ocorrencias_pdf(lista, empresa, de, ate, por=''):
    rp = RelatorioPDF('Ocorrências e não conformidades', empresa, _per(de, ate), paisagem=True, validacao=validacao_padrao('Ocorrências e não conformidades', por))
    tipos, graves = {}, 0
    for o in lista:
        tipos[o['tipo']] = tipos.get(o['tipo'], 0) + 1
        graves += 1 if o['gravidade'] == 'Grave' else 0
    hist = [rp.tabela(['Data', 'Tipo', 'Gravidade', 'Setor', 'Exame', 'Descrição', 'Ação imediata', 'Situação'],
                      _linhas_ocor(lista) or [['—'] * 8], [18, 34, 18, 24, 26, 70, 56, 22])]
    abertas = sum(1 for o in lista if o['status'] != 'ENCERRADA')
    hist += _analise(rp, 'Análise', [
        '%d ocorrência(s) no período, %d grave(s), %d ainda não encerrada(s).' % (len(lista), graves, abertas),
        ('Mais frequente: %s (%d).' % max(tipos.items(), key=lambda kv: kv[1])) if tipos else '',
        'Toda ocorrência grave ou recorrente deve gerar análise de causa e plano de ação.'])
    return rp.bytes(hist)


def ocorrencias_xlsx(lista, empresa, de, ate):
    from openpyxl import Workbook
    wb = Workbook()
    planilha(wb.active, 'Ocorrências e não conformidades', empresa, _per(de, ate),
             ['Data', 'Tipo', 'Gravidade', 'Setor', 'Exame', 'Descrição', 'Ação imediata', 'Situação'], _linhas_ocor(lista),
             [12, 26, 12, 18, 20, 60, 46, 14])
    return xlsx_bytes(wb)


# ------------------------------------------------------------------ SWOT
def swot_pdf(s, empresa, por=''):
    a = s['analise']
    rp = RelatorioPDF('Matriz SWOT: %s' % a['titulo'][:80], empresa, util.data_br(a['data']) if a['data'] else '', paisagem=True,
                      validacao=validacao_padrao('Matriz SWOT: %s' % a['titulo'][:60], por))
    e = rp.e
    qd = s['quadrantes']

    def col(k):
        return '<br/>'.join('• %s (peso %d)' % (util_esc(i['texto']), i['peso']) for i in qd[k]) or '—'
    t = Table([[Paragraph('<b>Forças</b><br/>' + col('F'), e['cel']), Paragraph('<b>Fraquezas</b><br/>' + col('FR'), e['cel'])],
               [Paragraph('<b>Oportunidades</b><br/>' + col('O'), e['cel']), Paragraph('<b>Ameaças</b><br/>' + col('A'), e['cel'])]],
              colWidths=[133 * mm, 133 * mm])
    t.setStyle(TableStyle([('GRID', (0, 0), (-1, -1), .6, colors.HexColor('#9aa8a0')), ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                           ('BACKGROUND', (0, 0), (0, 0), colors.HexColor('#e8f5e9')), ('BACKGROUND', (1, 0), (1, 0), colors.HexColor('#fff3e0')),
                           ('BACKGROUND', (0, 1), (0, 1), colors.HexColor('#e3f2fd')), ('BACKGROUND', (1, 1), (1, 1), colors.HexColor('#fde7e9')),
                           ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6)]))
    hist = [t, Paragraph('Cruzamentos (estratégias sugeridas)', e['h2'])]
    hist += [Paragraph('<b>%s</b>: %s' % (c['sigla'], util_esc(c['texto'])), e['cel']) for c in s['cruzamentos']] or [Paragraph('—', e['cel'])]
    hist += _analise(rp, 'Análise', [
        'Saldo interno (forças menos fraquezas, pelos pesos): %+d. Saldo externo (oportunidades menos ameaças): %+d.' % (s['saldo_interno'], s['saldo_externo']),
        'O ambiente interno está %s e o externo está %s.' % ('favorável' if s['saldo_interno'] >= 0 else 'desfavorável',
                                                           'favorável' if s['saldo_externo'] >= 0 else 'desfavorável')])
    if a['obs']:
        hist += [Paragraph('Observações', e['h2']), Paragraph(util_esc(a['obs']), e['cel'])]
    return rp.bytes(hist)


# ------------------------------------------------------------------ fluxograma
FORMAS_NOME = {'inicio': 'Início/fim', 'processo': 'Etapa', 'decisao': 'Decisão', 'documento': 'Documento', 'dados': 'Dados', 'subprocesso': 'Subprocesso',
               'conector': 'Conector', 'espera': 'Espera'}


def fluxo_pdf(f, empresa, por=''):
    d = f['dados_obj']
    nos = sorted(d.get('nos', []), key=lambda n: (n['x'], n['y']))
    raias = {r['id']: r['nome'] for r in d.get('raias', [])}
    rp = RelatorioPDF('Fluxograma: %s' % f['nome'][:80], empresa, 'Versão %d · %s%s' % (f['versao'], f['status'], (' em ' + util.data_br(f['aprovado_em'][:10])) if f.get('aprovado_em') else ''),
                      paisagem=True, validacao=validacao_padrao('Fluxograma: %s' % f['nome'][:60], por, versao=f['versao'],
                                                                nota=('Fluxograma aprovado no sistema por %s.' % f['aprovado_por']) if f.get('aprovado_por') else ''))
    e = rp.e
    hist = []
    if f.get('setor') or f.get('objetivo'):
        hist.append(Paragraph('<b>Setor:</b> %s &nbsp; <b>Objetivo:</b> %s' % (util_esc(f['setor'] or '—'), util_esc(f['objetivo'] or '—')), e['cel']))
        hist.append(Spacer(1, 4))
    hist += gr.fluxograma(d, LARGURA_PAISAGEM, 400)
    hist += [PageBreak(), Paragraph('Descrição das etapas', e['h2']),
             rp.tabela(['#', 'Tipo', 'Etapa', 'Setor / raia', 'Responsável', 'Implantação'],
                       [[str(i + 1), FORMAS_NOME.get(n['forma'], n['forma']), n['texto'], raias.get(n.get('raia'), ''), n.get('responsavel', ''),
                         {'a_implantar': 'A implantar', 'em_implantacao': 'Em implantação', 'implantado': 'Implantado', 'revisao': 'Em revisão'}.get(n.get('status'), '')]
                        for i, n in enumerate(nos)] or [['—'] * 6], [10, 28, 100, 54, 40, 35])]
    decisoes = sum(1 for n in nos if n['forma'] == 'decisao')
    hist += _analise(rp, 'Análise', [
        '%d etapa(s), %d decisão(ões) e %d setor(es) envolvido(s).' % (len(nos), decisoes, len(raias)),
        '%d etapa(s) sem responsável definido.' % sum(1 for n in nos if not n.get('responsavel')) if any(not n.get('responsavel') for n in nos) else '',
        'Após aprovado, qualquer alteração cria nova versão que deve ser validada de novo.'])
    return rp.bytes(hist)


# ------------------------------------------------------------------ organograma
def organograma_pdf(nos, empresa, por=''):
    rp = RelatorioPDF('Organograma', empresa, '%d cargos' % len(nos), paisagem=True, validacao=validacao_padrao('Organograma', por))
    por_id = {n['id']: n for n in nos}
    subordinados = {}
    for n in nos:
        subordinados[n['pai_id']] = subordinados.get(n['pai_id'], 0) + 1
    hist = gr.organograma(nos, LARGURA_PAISAGEM, 400) + [PageBreak(), Paragraph('Cargos e responsáveis', rp.e['h2']),
            rp.tabela(['Cargo', 'Pessoa', 'Setor', 'Reporta a', 'Subordinados'],
                      [[n['cargo'], n['pessoa'] or '', n['setor'], por_id[n['pai_id']]['cargo'] if n['pai_id'] in por_id else '—', str(subordinados.get(n['id'], 0))]
                       for n in nos] or [['—'] * 5], [70, 55, 45, 70, 27], direita=(4,))]
    hist += _analise(rp, 'Análise', [
        '%d cargos; %d sem pessoa designada.' % (len(nos), sum(1 for n in nos if not n['pessoa'])) if nos else 'Organograma vazio.',
        ('Maior amplitude de comando: %s (%d subordinados).' % (por_id[max((k for k in subordinados if k in por_id), key=lambda k: subordinados[k])]['cargo'],
                                                              max(v for k, v in subordinados.items() if k in por_id)))
        if any(k in por_id for k in subordinados) else ''])
    return rp.bytes(hist)


# ------------------------------------------------------------------ protocolos (POPs)
def protocolo_pdf(pop, fluxo_dados, empresa, por=''):
    rev = util.data_br(pop['proxima_revisao']) if pop.get('proxima_revisao') else None
    nomes_papeis = ['Elaborado por', 'Revisado por (responsável técnico / supervisor de proteção radiológica)', 'Aprovado e validado por (direção)']
    v = validacao_padrao('%s · %s' % (pop['codigo'], pop['titulo'][:50]), por, versao=pop['versao'], revisao=rev, papeis=nomes_papeis)
    v['nomes'] = {nomes_papeis[0]: pop['elaborado_por'] or por, nomes_papeis[1]: pop['revisado_por'], nomes_papeis[2]: pop['aprovado_por'] or ''}
    v['emissao'] = util.data_br(pop['aprovado_em'][:10]) if pop.get('aprovado_em') else None
    rp = RelatorioPDF('%s · %s' % (pop['codigo'], pop['titulo'][:90]), empresa, 'Versão %d · %s' % (pop['versao'], pop['status']), validacao=v)
    e = rp.e
    ident = rp.tabela(['Código', 'Versão', 'Setor / área', 'Situação', 'Próxima revisão'],
                      [[pop['codigo'], str(pop['versao']), pop['setor'] or '—', pop['status'], rev or '—']], [26, 16, 70, 30, 40])
    hist = [ident, Spacer(1, 4)]

    def secao(titulo, texto):
        return [Paragraph(titulo, e['h2']), Paragraph(util_esc(texto or '—').replace('\n', '<br/>'), e['cel'])]

    def lista(titulo, itens):
        return [Paragraph(titulo, e['h2'])] + ([Paragraph('• ' + util_esc(x), e['cel']) for x in itens] or [Paragraph('—', e['cel'])])
    hist += secao('1. Objetivo', pop['objetivo']) + secao('2. Abrangência', pop['abrangencia']) + secao('3. Responsabilidades', pop['responsaveis'])
    hist += lista('4. Definições', pop['definicoes_lista']) + lista('5. Materiais e recursos', pop['materiais_lista'])
    hist += [Paragraph('6. Procedimento (passo a passo)', e['h2']),
             rp.tabela(['Passo', 'Descrição'], [[str(i + 1), x] for i, x in enumerate(pop['passos_lista'])] or [['—', '—']], [14, 168])]
    if pop['cuidados_lista']:
        hist += lista('7. Pontos de atenção', pop['cuidados_lista'])
    hist += lista('8. Registros gerados', pop['registros_lista']) + lista('9. Referências', pop['referencias_lista'])
    if fluxo_dados and fluxo_dados.get('nos'):
        hist += [Paragraph('10. Fluxograma do processo', e['h2'])] + gr.fluxograma(fluxo_dados, LARGURA_RETRATO, 330)
    return rp.bytes(hist)


def lista_mestra_pdf(lista, empresa, por=''):
    rp = RelatorioPDF('Lista mestra de protocolos (POPs)', empresa, '%d documentos' % len(lista), paisagem=True,
                      validacao=validacao_padrao('Lista mestra de protocolos', por))
    hist = [rp.tabela(['Código', 'Título', 'Setor', 'Versão', 'Situação', 'Aprovado por', 'Próxima revisão'],
                      [[p['codigo'], p['titulo'], p['setor'], str(p['versao']), p['status'] + (' (REVISÃO VENCIDA)' if p['vencido'] else ''), p['aprovado_por'] or '—',
                        util.data_br(p['proxima_revisao']) if p['proxima_revisao'] else '—'] for p in lista] or [['—'] * 7],
                      [20, 90, 50, 14, 38, 30, 25], direita=(3,))]
    hist += _analise(rp, 'Análise', [
        '%d documento(s): %d aprovado(s), %d em rascunho.' % (len(lista), sum(1 for p in lista if p['status'] == 'APROVADO'),
                                                              sum(1 for p in lista if p['status'] != 'APROVADO')),
        '%d com revisão vencida.' % sum(1 for p in lista if p['vencido']) if any(p['vencido'] for p in lista) else ''])
    return rp.bytes(hist)


# ------------------------------------------------------------------ fornecedores
def _linhas_forn(lista):
    saida = []
    for f in lista:
        u = f['ultima']
        saida.append([f['nome'], f['cnpj'] or '', util.data_br(u['data']) if u else '—', _p(u['percentual']) if u else '—',
                      u['classificacao'] if u else '—', util.data_br(u['proxima']) if u and u['proxima'] else '—', f['situacao'],
                      str(f['contas_12m'])])
    return saida


def fornecedores_pdf(lista, avaliacoes, empresa, de, ate, por=''):
    rp = RelatorioPDF('Avaliação de fornecedores', empresa, _per(de, ate), paisagem=True,
                      validacao=validacao_padrao('Avaliação de fornecedores', por, papeis=['Elaborado por (qualidade)', 'Revisado por (compras)', 'Aprovado e validado por (gerência)']))
    e = rp.e
    em_dia = sum(1 for f in lista if f['situacao'] == 'EM DIA')
    hist = [Paragraph('Fornecedores ativos: %d · Avaliação em dia: %d (%s)' % (len(lista), em_dia, _p(100.0 * em_dia / len(lista)) if lista else '—'),
                      e['total']),
            Paragraph('Situação de cada fornecedor', e['h2']),
            rp.tabela(['Fornecedor', 'CNPJ', 'Última avaliação', 'Nota', 'Classificação', 'Próxima', 'Situação', 'Contas (12 meses)'],
                      _linhas_forn(lista) or [['—'] * 8], [62, 34, 26, 18, 40, 22, 26, 24], direita=(3, 7)),
            Paragraph('Avaliações realizadas no período', e['h2']),
            rp.tabela(['Data', 'Fornecedor', 'Avaliador', 'Nota', 'Classificação', 'Ação / observação'],
                      [[util.data_br(a['data']), a['fornecedor'], a['avaliador'] or '', _p(a['percentual']), a['classificacao'],
                        (a['acao'] or a['obs'] or '')[:200]] for a in avaliacoes] or [['—'] * 6], [20, 60, 28, 18, 40, 86], direita=(3,)),
            Spacer(1, 6),
            Paragraph('Classificação: aprovado a partir de 80% da nota máxima; aprovado com restrições de 60% a 79%; reprovado abaixo de 60%. '
                      'Confira os critérios com o manual da ONA vigente.', e['nota'])]
    sem = [f['nome'] for f in lista if f['situacao'] == 'SEM AVALIAÇÃO']
    vencidas = [f['nome'] for f in lista if f['situacao'] == 'VENCIDA']
    reprov = [f['nome'] for f in lista if f['ultima'] and f['ultima']['classificacao'] == 'REPROVADO']
    hist += _analise(rp, 'Análise', [
        ('Sem avaliação: ' + '; '.join(sem[:10]) + ('...' if len(sem) > 10 else '')) if sem else 'Todos os fornecedores ativos têm avaliação.',
        ('Avaliação vencida: ' + '; '.join(vencidas[:10])) if vencidas else '',
        ('Reprovados na última avaliação: ' + '; '.join(reprov)) if reprov else ''])
    return rp.bytes(hist)


def fornecedores_xlsx(lista, avaliacoes, empresa, de, ate):
    from openpyxl import Workbook
    wb = Workbook()
    planilha(wb.active, 'Avaliação de fornecedores', empresa, _per(de, ate),
             ['Fornecedor', 'CNPJ', 'Última avaliação', 'Nota (%)', 'Classificação', 'Próxima', 'Situação', 'Contas (12 meses)'],
             _linhas_forn(lista), [44, 22, 16, 10, 26, 14, 16, 16])
    ws = wb.create_sheet('Avaliações no período')
    planilha(ws, 'Avaliações no período', empresa, _per(de, ate), ['Data', 'Fornecedor', 'Avaliador', 'Nota (%)', 'Classificação', 'Ação / observação'],
             [[util.data_br(a['data']), a['fornecedor'], a['avaliador'] or '', a['percentual'], a['classificacao'], a['acao'] or a['obs'] or '']
              for a in avaliacoes], [12, 40, 18, 10, 26, 60])
    return xlsx_bytes(wb)


def avaliacao_pdf(a, empresa, por=''):
    rp = RelatorioPDF('Avaliação de fornecedor', empresa, util.data_br(a['data']),
                      validacao=validacao_padrao('Avaliação de fornecedor: %s' % a['fornecedor'][:50], a['avaliador'] or por,
                                                 papeis=['Avaliador', 'Revisado por (qualidade)', 'Aprovado e validado por (gerência)'],
                                                 revisao=util.data_br(a['proxima']) if a['proxima'] else None))
    e = rp.e
    hist = [Paragraph('<b>%s</b>%s' % (util_esc(a['fornecedor']), (' · CNPJ ' + util_esc(a['cnpj'])) if a['cnpj'] else ''), e['cel']),
            Paragraph('Período avaliado: %s · Avaliador: %s · Fornecedor crítico: %s' % (util_esc(a['periodo'] or '—'), util_esc(a['avaliador'] or '—'),
                                                                                          'sim' if a['critico'] else 'não'), e['cel']),
            Spacer(1, 4),
            rp.tabela(['Critério', 'Peso', 'Nota (1 a 5)', 'Comentário'], [[n['criterio'], str(n['peso']), str(n['nota']), n['comentario']] for n in a['notas']],
                      [60, 14, 24, 82], direita=(1, 2)),
            Spacer(1, 6),
            Paragraph('Resultado: %s da nota máxima · <b>%s</b> · Próxima avaliação: %s' % (_p(a['percentual']), a['classificacao'],
                                                                                          util.data_br(a['proxima']) if a['proxima'] else '—'), e['total'])]
    fracos = [n['criterio'] for n in a['notas'] if n['nota'] <= 2]
    hist += _analise(rp, 'Análise', [('Critérios com nota baixa (1 ou 2): ' + '; '.join(fracos)) if fracos else 'Nenhum critério com nota baixa.'])
    if a['acao'] or a['obs']:
        hist += [Paragraph('Ação e observações', e['h2']), Paragraph(util_esc((a['acao'] + '\n' + a['obs']).strip()).replace('\n', '<br/>'), e['cel'])]
    return rp.bytes(hist)


# ------------------------------------------------------------------ perfil epidemiológico
def _pct_txt(v):
    return '—' if v is None else ('%.1f%%' % v).replace('.', ',')


def epidemio_pdf(pf, empresa, por=''):
    rp = RelatorioPDF('Perfil epidemiológico dos pacientes atendidos', empresa, _per(pf['de'], pf['ate']), paisagem=True,
                      validacao=validacao_padrao('Perfil epidemiológico', por))
    e = rp.e
    idade = pf['idade']
    resumo = [['Exames realizados', str(pf['total_exames'])], ['Pacientes atendidos', str(pf['pacientes'])],
              ['Pacientes com mais de um exame', '%d (%s)' % (pf['pacientes_com_mais_de_um'], _pct_txt(pf['pct_retorno']))],
              ['Idade média / mediana', '%s / %s anos' % (('%.1f' % idade['media']).replace('.', ',') if idade['media'] is not None else '—',
                                                         ('%g' % idade['mediana']).replace('.', ',') if idade['mediana'] is not None else '—')],
              ['Idade mínima / máxima', '%s / %s anos' % (idade['minima'] if idade['minima'] is not None else '—', idade['maxima'] if idade['maxima'] is not None else '—')]]
    tabela_t = lambda cab, itens: rp.tabela([cab, 'Pacientes/exames', '%'], [[i['rotulo'], str(i['n']), _pct_txt(i['pct'])] for i in itens] or [['—', '0', '—']], [70, 28, 18], direita=(1, 2))

    def duplo(titulo_a, a, titulo_b, b):
        t = Table([[[Paragraph(titulo_a, e['h2']), a], [Paragraph(titulo_b, e['h2']), b]]], colWidths=[133 * mm, 133 * mm])
        t.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP')]))
        return t
    hist = [rp.tabela(['Indicador', 'Valor'], resumo, [90, 60]), Spacer(1, 4),
            duplo('Pirâmide etária (pacientes por faixa e sexo)', gr.piramide_etaria(pf['piramide'], pf['max_faixa'], 360), 'Sexo dos pacientes', gr.barras_h(pf['sexo'], 360, '#7b1fa2')),
            duplo('Faixa etária', gr.barras_h(pf['faixas'], 360, '#2f7a49', 9), 'Exames realizados', gr.barras_h(pf['exames'], 360, '#1565c0')),
            PageBreak(),
            duplo('Procedência: cidade', gr.barras_h(pf['cidades'], 360, '#ef6c00'), 'Procedência: bairro', gr.barras_h(pf['bairros'], 360, '#ef6c00')),
            duplo('Convênios', gr.barras_h(pf['convenios'], 360, '#00838f'), 'Médicos solicitantes', gr.barras_h(pf['medicos'], 360, '#5d4037')),
            duplo('Diagnósticos (CID)', gr.barras_h(pf['cids'], 360, '#c62828'), 'Exames por dia da semana', gr.colunas(pf['dias'], 360, 120)),
            Paragraph('Evolução mensal de exames', e['h2']), gr.colunas(pf['meses'], 700, 130),
            Paragraph('Qualidade dos dados usados', e['h2']),
            rp.tabela(['Informação', 'Preenchidos', 'Total', '%'], [[q_['rotulo'], str(q_['n']), str(q_['de']), _pct_txt(100.0 * q_['n'] / q_['de'] if q_['de'] else None)] for q_ in pf['qualidade_dado']],
                      [100, 30, 30, 20], direita=(1, 2, 3))]
    ruim = [q_['rotulo'] for q_ in pf['qualidade_dado'] if q_['de'] and q_['n'] / float(q_['de']) < 0.9]
    top_exame = pf['exames'][0]['rotulo'] if pf['exames'] else '—'
    top_cidade = pf['cidades'][0]['rotulo'] if pf['cidades'] else '—'
    hist += _analise(rp, 'Análise', [
        '%d paciente(s) e %d exame(s) no período; exame mais frequente: %s; principal procedência: %s.' % (pf['pacientes'], pf['total_exames'], top_exame, top_cidade),
        ('Dados com menos de 90%% de preenchimento (melhorar o cadastro): %s.' % '; '.join(ruim)) if ruim else 'Cadastro com bom preenchimento nos itens avaliados.',
        'Idade calculada na data do exame; sexo e procedência vêm do cadastro do cliente.'])
    return rp.bytes(hist)
