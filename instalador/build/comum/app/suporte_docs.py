"""Relatório em PDF das correções e sugestões aceitas que entram na próxima atualização (pasta do desenvolvedor):
capa, sumário, itens separados por tema (bugs primeiro dentro de cada tema), ficha de cada item com os dados do envio e contracapa."""
from __future__ import annotations

import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Frame, KeepTogether, NextPageTemplate, PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.platypus.tableofcontents import TableOfContents

from . import suporte, util
from .novidades import _Doc, _data_extenso
from .relatorio_base import _esc

VERDE = colors.HexColor('#255f39')


def _data(texto):
    return util.data_br(str(texto or '')[:10])


class _DocPendencias(_Doc):
    def __init__(self, buf, **kw):
        super().__init__(buf, **kw)
        quadro = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id='contra')
        self.addPageTemplates([PageTemplate(id='contra', frames=[quadro], onPage=self._contra)])
        self.cab = 'NUCLELESTE · Pendências para a próxima atualização'

    def afterFlowable(self, f):
        if isinstance(f, Paragraph):
            if f.style.name == 'Secao':
                self.notify('TOCEntry', (0, f.getPlainText(), self.page))
            elif f.style.name == 'ItemToc':
                self.notify('TOCEntry', (1, f.getPlainText(), self.page))

    def _contra(self, c, doc):
        c.saveState()
        c.setFillColor(VERDE)
        c.rect(0, 0, A4[0], A4[1], stroke=0, fill=1)
        c.setFillColor(colors.HexColor('#2f9e6a'))
        c.circle(A4[0] + 1 * cm, 2 * cm, 6 * cm, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont('Helvetica-Bold', 22)
        c.drawCentredString(A4[0] / 2, A4[1] / 2 + 1.2 * cm, 'NUCLELESTE')
        c.setFont('Helvetica', 11)
        c.drawCentredString(A4[0] / 2, A4[1] / 2 - 0.2 * cm, self.clinica)
        c.setFont('Helvetica', 9.5)
        c.drawCentredString(A4[0] / 2, 2.4 * cm, 'Documento gerado pelo sistema para organizar as correções da próxima atualização.')
        c.restoreState()


def relatorio_pdf(pendentes, empresa, versao_atual='', usuario='', agora=None):
    """`pendentes`: itens aceitos que ainda não entraram numa atualização (como vêm de `suporte.pasta`)."""
    agora = agora or datetime.now()
    ss = getSampleStyleSheet()
    est = {
        'titulo': ParagraphStyle('Titulo', parent=ss['Title'], fontSize=30, leading=34, textColor=colors.white, alignment=0),
        'versao': ParagraphStyle('Versao', parent=ss['Normal'], fontSize=14, leading=18, textColor=colors.HexColor('#ffd54a')),
        'h1': ParagraphStyle('Cap', parent=ss['Heading1'], fontSize=18, textColor=VERDE, spaceBefore=10, spaceAfter=8),
        'secao': ParagraphStyle('Secao', parent=ss['Heading1'], fontSize=17, textColor=colors.white, backColor=VERDE, borderPadding=(6, 8, 6, 8),
                                spaceBefore=16, spaceAfter=12, leading=21),
        'item': ParagraphStyle('ItemToc', parent=ss['Heading3'], fontSize=12, textColor=VERDE, spaceBefore=10, spaceAfter=3, leading=15),
        'corpo': ParagraphStyle('Corpo', parent=ss['BodyText'], fontSize=10.5, leading=15),
        'peq': ParagraphStyle('Peq', parent=ss['BodyText'], fontSize=8.8, leading=12, textColor=colors.HexColor('#5d6b64')),
    }
    bugs = [i for i in pendentes if i['tipo'] == suporte.BUG]
    sugestoes = [i for i in pendentes if i['tipo'] != suporte.BUG]
    grupos = suporte.por_tema(pendentes)
    buf = io.BytesIO()
    doc = _DocPendencias(buf, title='Pendências da próxima atualização', author='Nucleleste')
    doc.rotulo = 'Versão atual %s' % (versao_atual or '—')
    doc.clinica = empresa or 'Nucleleste'
    historia = [NextPageTemplate('miolo'), Spacer(1, 1.2 * cm), Paragraph('Pendências da<br/>próxima atualização', est['titulo']), Spacer(1, 4),
                Paragraph('Versão atual %s · %s' % (versao_atual or '—', _data_extenso(agora.strftime('%Y-%m-%d'))), est['versao']), Spacer(1, 3.4 * cm),
                Paragraph('Resumo', est['h1']),
                Paragraph('Este documento reúne tudo o que foi aceito e ainda não entrou numa atualização, separado por tema, com os bugs antes das sugestões '
                          'dentro de cada tema. Ele pode ser enviado ao desenvolvedor como lista de trabalho.', est['corpo']), Spacer(1, 0.5 * cm)]
    resumo = [['Correções de bugs', str(len(bugs))], ['Sugestões', str(len(sugestoes))], ['Temas', str(len(grupos))], ['Gerado por', (usuario or '—').title()],
              ['Gerado em', agora.strftime('%d/%m/%Y %H:%M')]]
    tabela = Table(resumo, colWidths=[5 * cm, 9 * cm])
    tabela.setStyle(TableStyle([('GRID', (0, 0), (-1, -1), .6, colors.HexColor('#cdd6d1')), ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#e8f2ec')),
                                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'), ('TEXTCOLOR', (0, 0), (0, -1), VERDE),
                                ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6)]))
    historia += [tabela, PageBreak()]
    sumario = TableOfContents()
    sumario.levelStyles = [ParagraphStyle('S0', fontSize=12, leading=21, leftIndent=8, firstLineIndent=-8, fontName='Helvetica-Bold'),
                           ParagraphStyle('S1', fontSize=10, leading=15, leftIndent=24, firstLineIndent=-8)]
    sumario.dotsMinLevel = 0
    historia += [Paragraph('Sumário', est['h1']), sumario, PageBreak()]
    if not pendentes:
        historia.append(Paragraph('Nenhum item aceito aguardando a próxima atualização.', est['corpo']))
    n = 0
    for tema, itens in grupos:
        historia.append(Paragraph('%s (%d)' % (_esc(tema), len(itens)), est['secao']))
        for i in itens:
            n += 1
            rotulo = 'CORREÇÃO DE BUG' + (' · %s' % i['gravidade_rotulo'].upper() if i['gravidade_rotulo'] else '') if i['tipo'] == suporte.BUG else 'SUGESTÃO'
            cor = '#b3261e' if i['tipo'] == suporte.BUG else '#2f7a49'
            ficha = [Paragraph('%d. %s' % (n, _esc(i['titulo'])), est['item']),
                     Paragraph('<font color="%s"><b>%s</b></font> · Tela: %s · Enviado por %s em %s' % (cor, rotulo, _esc(i['tela'] or '—'), _esc(i['usuario'] or '—'),
                                                                                                      _esc(str(i['criado_em'])[8:10] + '/' + str(i['criado_em'])[5:7] + '/' + str(i['criado_em'])[:4] +
                                                                                                           ' ' + str(i['criado_em'])[11:16])), est['peq']),
                     Spacer(1, 2), Paragraph(_esc(suporte.texto_final(i)).replace('\n', '<br/>'), est['corpo'])]
            if i['tipo'] == suporte.BUG and i.get('passos'):
                ficha.append(Paragraph('<b>Como acontece:</b> %s' % _esc(i['passos']).replace('\n', '<br/>'), est['corpo']))
            m = i.get('meta_obj') or {}
            if m:
                cl = m.get('cliente') or {}
                linha = ['Aparelho: %s, %s, %s' % (m.get('dispositivo', '?'), m.get('sistema', '?'), m.get('navegador', '?')), 'IP: %s' % (m.get('ip') or '?')]
                if cl.get('tela'):
                    linha.append('Tela: %s' % cl['tela'])
                if m.get('erros_recentes'):
                    linha.append('Erros registrados: ' + '; '.join('%s %s' % (e['data_hora'][5:16], e['detalhe'][:60]) for e in m['erros_recentes']))
                ficha.append(Paragraph(_esc(' · '.join(linha)), est['peq']))
            historia.append(KeepTogether(ficha))
    historia += [Spacer(1, 0.6 * cm), Paragraph('Os textos são os que o desenvolvedor escreveu para a atualização; onde não houve reescrita, vale o texto de quem enviou.', est['peq']),
                 NextPageTemplate('contra'), PageBreak(), Spacer(1, 1)]
    doc.multiBuild(historia)
    return buf.getvalue()
