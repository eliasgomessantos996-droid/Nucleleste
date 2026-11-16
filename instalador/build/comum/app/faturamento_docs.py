"""Resumo de uma fatura em PDF (cadastro, nota fiscal, recebimento e glosa)."""
from __future__ import annotations

from reportlab.platypus import Paragraph, Spacer

from . import faturamento as fatu
from . import util
from .relatorio_base import RelatorioPDF


def _d(txt):
    return util.data_br(str(txt or '')[:10]) if txt else '—'


def _r(v):
    return 'R$ %s' % util.moeda(v or 0)


def resumo_pdf(r, glosa, empresa):
    rp = RelatorioPDF('Resumo da fatura', empresa, '%s · protocolo %s' % (r.get('convenio') or '', r.get('protocolo') or '—'))
    e = rp.e
    historia = [Paragraph('Situação: %s' % fatu.ROTULOS.get(r.get('status'), r.get('status') or ''), e['total']), Spacer(1, 4),
                Paragraph('Faturamento', e['h2']),
                rp.tabela(['Campo', 'Valor'], [
                    ['Convênio', r.get('convenio') or ''], ['Protocolo', r.get('protocolo') or '—'], ['Data de referência', _d(r.get('referencia'))],
                    ['Quantidade de guias faturadas', str(r.get('qtd_guias') or '—')], ['Valor faturado (bruto)', _r(r.get('valor_bruto'))],
                    ['Previsão de recebimento', _d(r.get('previsao'))], ['Cadastrada por', '%s em %s' % (r.get('usuario') or '—', _d(r.get('criado_em')))]],
                    [70, 110]),
                Paragraph('Nota fiscal', e['h2']),
                rp.tabela(['Campo', 'Valor'], [
                    ['Número', r.get('nota_fiscal') or 'ainda não emitida'], ['Data de emissão', _d(r.get('nf_emitida_em'))],
                    ['Emitida por', r.get('nf_emitida_por') or '—']], [70, 110])]
    if r.get('status') == fatu.RECEBIDO and glosa:
        rotulo = {'glosa': 'Glosa (recebeu menos)', 'acima': 'Diferença a maior', 'sem': 'Sem glosa'}[glosa['sentido']]
        historia += [Paragraph('Recebimento e glosa', e['h2']),
                     rp.tabela(['Campo', 'Valor'], [
                         ['Data do recebimento', _d(r.get('data_recebimento'))], ['Banco / conta', r.get('banco_recebimento') or '—'],
                         ['Bruto faturado', _r(r.get('valor_bruto'))], ['Bruto recebido', _r(glosa['bruto_recebido'])],
                         ['Tributos', _r(r.get('tributos'))], ['Líquido recebido', _r(r.get('valor_recebido'))],
                         [rotulo, '%s (%s%%)' % (_r(abs(glosa['valor'])), str(abs(glosa['pct'])).replace('.', ','))]], [70, 110])]
    if r.get('obs'):
        historia += [Paragraph('Observação', e['h2']), Paragraph(r['obs'].replace('&', '&amp;').replace('<', '&lt;'), e['cel'])]
    return rp.bytes(historia)
