"""PDF da tabela de preços dos exames (A4 retrato): logo da clínica, tabela com código, exame, valor e observação."""
from __future__ import annotations

import io
import os
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from . import util
from .relatorio_base import CINZA, FONTE, FONTE_NEGRITO, GRADE, VERDE, ZEBRA, _esc, estilos

LOGO = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'fichas', 'image1.jpeg')
MARGEM = 15 * mm
LARGURA_LOGO = 6 * cm
A_CONSULTAR = 'a consultar'


def _logo():
    """Logo com a largura fixa e a altura pela proporção original (None se o arquivo não existir)."""
    if not os.path.exists(LOGO):
        return None
    iw, ih = ImageReader(LOGO).getSize()
    return Image(LOGO, width=LARGURA_LOGO, height=LARGURA_LOGO * ih / iw)


def _com_total_de_paginas(largura, altura, emitido):
    """Canvas que escreve o rodapé 'Página X de Y' só depois de saber o total de páginas."""
    class Canvas(rl_canvas.Canvas):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self._estados = []

        def showPage(self):
            self._estados.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._estados)
            for estado in self._estados:
                self.__dict__.update(estado)
                self.setFont(FONTE, 8)
                self.setFillColor(CINZA)
                self.drawString(MARGEM, 9 * mm, 'Emitido em %s' % emitido)
                self.drawRightString(largura - MARGEM, 9 * mm, 'Página %d de %d' % (self.getPageNumber(), total))
                super().showPage()
            super().save()
    return Canvas


def tabela_pdf(tabela, itens, clinica_nome, clinica_cnpj=''):
    """Gera o PDF e devolve os bytes. `tabela` e cada item de `itens` são linhas (sqlite3.Row ou dicionário)."""
    e = estilos()
    agora = datetime.now().strftime('%d/%m/%Y %H:%M')
    buf = io.BytesIO()
    largura = A4[0]
    historia = []
    logo = _logo()
    if logo:
        historia += [logo, Spacer(1, 4)]
    historia.append(Paragraph(_esc((clinica_nome or 'Nucleleste').upper()), e['h2']))
    if clinica_cnpj:
        historia.append(Paragraph('CNPJ %s' % _esc(clinica_cnpj), e['sub']))
    historia.append(Spacer(1, 8))
    historia.append(Paragraph('TABELA DE PREÇOS — %s' % _esc(tabela['nome']), e['titulo']))
    if tabela['vigencia']:
        historia.append(Paragraph('Vigência a partir de %s' % util.data_br(tabela['vigencia']), e['sub']))
    historia.append(Spacer(1, 8))

    cab = [Paragraph(_esc(c), e['cab']) for c in ('Código', 'Exame / procedimento', 'Valor (R$)', 'Observação')]
    linhas = [cab]
    for it in itens:
        valor = util.moeda(it['valor']) if it['valor'] is not None else A_CONSULTAR
        linhas.append([Paragraph(_esc(it['codigo'] or ''), e['cel']), Paragraph(_esc(it['descricao']), e['cel']),
                       Paragraph(_esc(valor), e['cel_dir']), Paragraph(_esc(it['obs'] or ''), e['cel'])])
    if not itens:
        historia.append(Paragraph('Nenhum exame nesta tabela.', e['nota']))
    else:
        t = Table(linhas, repeatRows=1, colWidths=[26 * mm, 84 * mm, 30 * mm, 40 * mm])
        t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), VERDE), ('GRID', (0, 0), (-1, -1), .5, GRADE),
                               ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('TOPPADDING', (0, 0), (-1, -1), 3),
                               ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                               ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, ZEBRA])]))
        historia.append(t)
    if tabela['obs']:
        historia += [Spacer(1, 10), Paragraph('Observações', e['h2']), Paragraph(_esc(tabela['obs']).replace('\n', '<br/>'), e['cel'])]

    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=MARGEM, rightMargin=MARGEM, topMargin=14 * mm, bottomMargin=16 * mm,
                            title='Tabela de preços - %s' % tabela['nome'], author=clinica_nome or 'Nucleleste')
    doc.build(historia, canvasmaker=_com_total_de_paginas(largura, A4[1], agora))
    return buf.getvalue()
