"""Relatório da NucleAI em PDF e Excel, no modelo comum de relatórios."""
from __future__ import annotations

from reportlab.platypus import Paragraph, Spacer

from . import util
from .ajuda_stats import RESULTADOS, STATUS_CHAMADO
from .relatorio_base import RelatorioPDF, planilha, xlsx_bytes


def _pct(v):
    return '—' if v is None else ('%.1f%%' % v).replace('.', ',')


def _periodo(p):
    return '%s a %s' % (util.data_br(p['de']), util.data_br(p['ate']))


def _rotulo(r):
    return RESULTADOS.get(r)


def relatorio_pdf(p, consultas, chamados, empresa):
    rp = RelatorioPDF('NucleAI: relatório de ajuda', empresa, _periodo(p))
    e = rp.e
    nota = '—' if p['nota_media'] is None else ('%.2f (%d avaliações)' % (p['nota_media'], p['n_notas'])).replace('.', ',')
    historia = [
        Paragraph('Resumo', e['h2']),
        rp.tabela(['Indicador', 'Valor'], [
            ['Consultas', str(p['total'])],
            ['Resolveram', '%d (%s das avaliadas)' % (p['resolveu'], _pct(p['taxa_resolucao']))],
            ['Resolveram e perguntaram de novo', str(p['resolveu_e_nova'])],
            ['Não resolveram', '%d (%s das avaliadas)' % (p['nao_resolveu'], _pct(p['taxa_nao']))],
            ['Sem resposta ou abandonadas', str(p['sem_resposta'])],
            ['Nota média', nota],
            ['Dúvidas escritas (busca por texto)', '%d (%s)' % (p['por_texto'], _pct(p['pct_texto']))],
            ['Chamados à gerência', '%d (confirmados: %d, negados: %d)' % (p['chamados'], p['chamados_confirmados'], p['chamados_negados'])],
            ['Chamados com a gerência offline', str(p['chamados_sem_gerencia_online'])],
        ], [90, 90]),
        Paragraph('Temas mais consultados', e['h2']),
        rp.tabela(['Tema', 'Consultas', 'Resolveu', 'Não resolveu'],
                  [[t['chave'], str(t['n']), str(t['resolveu']), str(t['nao'])] for t in p['temas']], [90, 28, 28, 34], direita=(1, 2, 3)),
        Paragraph('Áreas em que mais usuários disseram "não ajudou"', e['h2']),
        rp.tabela(['Área', 'Consultas', 'Não ajudou', 'Taxa'],
                  [[a['chave'], str(a['n']), str(a['nao']), _pct(a['taxa_nao'])] for a in p['nao_ajudou']] or [['Nenhuma no período', '', '', '']],
                  [100, 24, 26, 30], direita=(1, 2, 3)),
        Paragraph('Dúvidas escritas que a NucleAI não entendeu', e['h2']),
        rp.tabela(['Dúvida', 'Vezes'], [[x['texto'], str(x['n'])] for x in p['nao_entendidas']] or [['Nenhuma no período', '']],
                  [150, 30], direita=(1,)),
        Paragraph('Chamados à gerência', e['h2']),
        rp.tabela(['Data', 'Usuário', 'Assunto', 'Situação'],
                  [[util.data_br(c['criado_em'][:10]), c['usuario'], ' › '.join(x for x in (c['modulo'], c['area']) if x) or c['tema'],
                    STATUS_CHAMADO.get(c['status'], c['status'])] for c in chamados] or [['Nenhum no período', '', '', '']],
                  [24, 32, 90, 34]),
    ]
    historia.append(Spacer(1, 6))
    historia.append(Paragraph('As conversas com a NucleAI são apagadas; este relatório usa apenas o resumo guardado de cada consulta.', e['nota']))
    return rp.bytes(historia)


def relatorio_xlsx(p, consultas, chamados, empresa):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = 'Resumo'
    per = _periodo(p)
    planilha(ws, 'NucleAI: relatório de ajuda', empresa, per, ['Indicador', 'Valor'], [
        ['Consultas', p['total']], ['Resolveram', p['resolveu']], ['Resolveram e perguntaram de novo', p['resolveu_e_nova']],
        ['Não resolveram', p['nao_resolveu']], ['Sem resposta ou abandonadas', p['sem_resposta']],
        ['Taxa de resolução (%)', p['taxa_resolucao']], ['Nota média', p['nota_media']], ['Avaliações', p['n_notas']],
        ['Dúvidas escritas', p['por_texto']], ['Chamados à gerência', p['chamados']],
        ['Chamados confirmados', p['chamados_confirmados']], ['Chamados negados', p['chamados_negados']],
        ['Chamados com a gerência offline', p['chamados_sem_gerencia_online']]], [40, 16])
    f = wb.create_sheet('Temas e módulos')
    planilha(f, 'NucleAI: temas e módulos', empresa, per, ['Assunto', 'Consultas', 'Resolveu', 'Não resolveu'],
             [[t['chave'], t['n'], t['resolveu'], t['nao']] for t in p['temas'] + p['modulos']], [60, 12, 12, 14])
    f = wb.create_sheet('Não ajudou')
    planilha(f, 'NucleAI: áreas com mais "não ajudou"', empresa, per, ['Área', 'Consultas', 'Não ajudou', 'Taxa (%)'],
             [[a['chave'], a['n'], a['nao'], a['taxa_nao']] for a in p['nao_ajudou']], [70, 12, 12, 12])
    f = wb.create_sheet('Não entendidas')
    planilha(f, 'NucleAI: dúvidas não entendidas', empresa, per, ['Dúvida', 'Vezes'],
             [[x['texto'], x['n']] for x in p['nao_entendidas']], [70, 10])
    f = wb.create_sheet('Chamados')
    planilha(f, 'NucleAI: chamados à gerência', empresa, per,
             ['Data', 'Usuário', 'Tema', 'Módulo', 'Área', 'Dúvida', 'Situação', 'Atendido por', 'Confirmou'],
             [[c['criado_em'], c['usuario'], c['tema'], c['modulo'], c['area'], c['duvida'], STATUS_CHAMADO.get(c['status'], c['status']),
               c['atendido_por'], c['confirmou']] for c in chamados], [18, 16, 20, 24, 28, 40, 16, 20, 10])
    f = wb.create_sheet('Consultas')
    planilha(f, 'NucleAI: consultas', empresa, per, ['Data', 'Usuário', 'Tema', 'Módulo', 'Área', 'Origem', 'Dúvida', 'Resultado', 'Nota', 'Chamou gerência'],
             [[c['criado_em'], c['usuario'], c['tema'], c['modulo'], c['area'], 'Texto' if c['origem'] == 'TEXTO' else 'Lista', c['duvida'],
               _rotulo(c['resultado']), c['nota'], 'Sim' if c['chamou_gerencia'] else ''] for c in consultas],
             [18, 16, 20, 24, 28, 8, 40, 26, 6, 14])
    return xlsx_bytes(wb)
