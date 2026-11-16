"""Modelo comum dos relatórios (PDF e Excel): cabeçalho com a clínica e o período, rodapé com paginação,
área de assinatura opcional, cores e fontes padronizadas. Os números são calculados por quem chama; aqui só se formata.
"""
from __future__ import annotations

import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

VERDE = colors.HexColor('#255f39')
CINZA = colors.HexColor('#666666')
GRADE = colors.HexColor('#9aa8a0')
ZEBRA = colors.HexColor('#f1f6f3')
TOTAL = colors.HexColor('#e2ece6')
MARGEM = 14 * mm
FONTE = 'Helvetica'
FONTE_NEGRITO = 'Helvetica-Bold'


def _esc(v):
    return str(v if v is not None else '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def estilos():
    """Estilos de texto padronizados (títulos, subtítulos, células e cabeçalhos de tabela)."""
    return {
        'titulo': ParagraphStyle('titulo', fontName=FONTE_NEGRITO, fontSize=15, leading=19, textColor=VERDE),
        'sub': ParagraphStyle('sub', fontName=FONTE, fontSize=9.5, leading=12.5, textColor=colors.HexColor('#444444')),
        'h2': ParagraphStyle('h2', fontName=FONTE_NEGRITO, fontSize=11, leading=14, textColor=VERDE, spaceBefore=10, keepWithNext=1),
        'nota': ParagraphStyle('nota', fontName=FONTE, fontSize=8.5, leading=11, textColor=colors.HexColor('#555555')),
        'cel': ParagraphStyle('cel', fontName=FONTE, fontSize=8.8, leading=11),
        'cel_dir': ParagraphStyle('cel_dir', fontName=FONTE, fontSize=8.8, leading=11, alignment=2),
        'total': ParagraphStyle('total', fontName=FONTE_NEGRITO, fontSize=8.8, leading=11),
        'total_dir': ParagraphStyle('total_dir', fontName=FONTE_NEGRITO, fontSize=8.8, leading=11, alignment=2),
        'cab': ParagraphStyle('cab', fontName=FONTE_NEGRITO, fontSize=8, leading=9.5, textColor=colors.white),
    }


class RelatorioPDF:
    """Um relatório em PDF no modelo comum. Use `historia()` para montar o conteúdo e `bytes()` para gerar o arquivo."""

    def __init__(self, titulo, empresa='', periodo='', paisagem=False, assinaturas=None, validacao=None):
        self.titulo = titulo
        self.validacao = validacao
        self.empresa = empresa or 'Nucleleste'
        self.periodo = periodo or ''
        self.pagina = landscape(A4) if paisagem else A4
        self.assinaturas = assinaturas or []
        self.e = estilos()
        self.buf = io.BytesIO()
        self.gerado = datetime.now().strftime('%d/%m/%Y %H:%M')
        self.margem = MARGEM      # margem lateral (cabeçalho e rodapé acompanham); pode ser trocada em `bytes()`
        self.paginas = 0          # páginas do último `bytes()` (contadas no rodapé)

    def _cabecalho(self, c, d):
        w, h = self.pagina
        c.saveState()
        c.setFillColor(VERDE)
        c.setFont(FONTE_NEGRITO, 9)
        c.drawString(self.margem, h - 9 * mm, self.empresa.upper())
        c.setFont(FONTE, 8.5)
        c.setFillColor(CINZA)
        c.drawRightString(w - self.margem, h - 9 * mm, self.periodo)
        c.setStrokeColor(VERDE)
        c.setLineWidth(.6)
        c.line(self.margem, h - 11 * mm, w - self.margem, h - 11 * mm)
        c.restoreState()

    def _rodape(self, c, d):
        w, _h = self.pagina
        c.saveState()
        c.setFont(FONTE, 8)
        c.setFillColor(CINZA)
        c.drawString(self.margem, 8 * mm, 'Nucleleste · %s · gerado em %s' % (self.titulo, self.gerado))
        c.drawRightString(w - self.margem, 8 * mm, 'Página %d' % d.page)
        c.restoreState()

    def inicio(self):
        """Título e subtítulo do relatório (primeiro bloco do conteúdo)."""
        return [Paragraph(_esc(self.titulo), self.e['titulo']),
                Paragraph(_esc(self.periodo), self.e['sub']), Spacer(1, 6)]

    def tabela(self, cab, linhas, larguras_mm, totais=None, direita=()):
        """Tabela padrão: cabeçalho verde, linhas alternadas e (opcional) linha de totais em negrito.
        `direita`: índices das colunas numéricas (alinhadas à direita)."""
        e = self.e
        dados = [[Paragraph(_esc(c), e['cab']) for c in cab]]
        for linha in linhas:
            dados.append([Paragraph(_esc(v), e['cel_dir' if i in direita else 'cel']) for i, v in enumerate(linha)])
        if totais:
            dados.append([Paragraph(_esc(v), e['total_dir' if i in direita else 'total']) for i, v in enumerate(totais)])
        t = Table(dados, repeatRows=1, colWidths=[w * mm for w in larguras_mm])
        estilo = [('BACKGROUND', (0, 0), (-1, 0), VERDE), ('GRID', (0, 0), (-1, -1), .5, GRADE),
                  ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('TOPPADDING', (0, 0), (-1, -1), 3.5),
                  ('BOTTOMPADDING', (0, 0), (-1, -1), 3.5),
                  ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, ZEBRA])]
        if totais:
            estilo.append(('BACKGROUND', (0, len(dados) - 1), (-1, len(dados) - 1), TOTAL))
        t.setStyle(TableStyle(estilo))
        return t

    def assinatura(self):
        """Área de assinatura, com uma linha por nome (quando o relatório pede assinatura)."""
        if not self.assinaturas:
            return []
        blocos = [Spacer(1, 26)]
        for nome in self.assinaturas:
            blocos += [Paragraph('_______________________________________<br/>%s' % _esc(nome), self.e['sub']), Spacer(1, 20)]
        return blocos

    def validacao_bloco(self):
        """Quadro de validação e assinaturas para apresentar a órgãos e auditorias: identificação do documento, três campos de
        assinatura (nome, cargo/registro, data, assinatura) e o parecer. `validacao` pode ser True ou um dicionário com
        `documento`, `versao`, `emissao`, `revisao` (próxima revisão), `papeis` e `nomes` ({papel: nome}) já conhecidos."""
        v = self.validacao
        if not v:
            return []
        v = v if isinstance(v, dict) else {}
        e = self.e
        largura = self.pagina[0] - 2 * MARGEM
        papeis = v.get('papeis') or ['Elaborado por', 'Revisado por (responsável técnico / supervisor de proteção radiológica)', 'Aprovado e validado por (direção)']
        nomes = v.get('nomes') or {}
        ident = Table([[Paragraph('<b>Documento</b><br/>%s' % (_esc(v.get('documento')) or _esc(self.titulo[:60])), e['cel']),
                        Paragraph('<b>Versão</b><br/>%s' % (_esc(v.get('versao')) or '_____'), e['cel']),
                        Paragraph('<b>Data de emissão</b><br/>%s' % (_esc(v.get('emissao')) or self.gerado[:10]), e['cel']),
                        Paragraph('<b>Válido até / próxima revisão</b><br/>%s' % (_esc(v.get('revisao')) or '____/____/________'), e['cel'])]],
                      colWidths=[largura * f for f in (.40, .14, .20, .26)])
        ident.setStyle(TableStyle([('GRID', (0, 0), (-1, -1), .5, GRADE), ('BACKGROUND', (0, 0), (-1, -1), ZEBRA), ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                                   ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4)]))
        linhas = [[Paragraph(c, e['cab']) for c in ('Função', 'Nome completo', 'Cargo e registro (CRM, CRF, CNEN)', 'Data', 'Assinatura')]]
        for papel in papeis:
            linhas.append([Paragraph(_esc(papel), e['cel']), Paragraph(_esc(nomes.get(papel, '')), e['cel']), '', Paragraph('___/___/______', e['nota']), ''])
        t = Table(linhas, colWidths=[largura * f for f in (.23, .24, .22, .11, .20)], rowHeights=[None] + [17 * mm] * len(papeis))
        t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), VERDE), ('GRID', (0, 0), (-1, -1), .5, GRADE), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                               ('TOPPADDING', (0, 0), (-1, 0), 3), ('BOTTOMPADDING', (0, 0), (-1, 0), 3)]))
        bloco = [Spacer(1, 12), Paragraph('Validação e assinaturas', e['h2']), ident, Spacer(1, 4), t, Spacer(1, 6)]
        if v.get('parecer', True):
            bloco.append(Paragraph('Parecer da validação: &nbsp; ( ) Aprovado &nbsp;&nbsp; ( ) Aprovado com restrições &nbsp;&nbsp; ( ) Reprovado '
                                   '&nbsp;&nbsp;&nbsp; Observações: ________________________________________________', e['sub']))
        bloco.append(Spacer(1, 3))
        bloco.append(Paragraph('Documento válido somente com as assinaturas, o nome e a data da validação preenchidos. %s' % _esc(v.get('nota') or ''), e['nota']))
        return [KeepTogether(bloco)]

    def bytes(self, historia, margem=None, topo=18 * mm, base=16 * mm):
        """Gera o PDF. `margem`, `topo` e `base` são opcionais (padrão do modelo); `self.paginas` fica com o número de páginas gerado."""
        if margem is not None:
            self.margem = margem
        doc = SimpleDocTemplate(self.buf, pagesize=self.pagina, leftMargin=self.margem, rightMargin=self.margem,
                                topMargin=topo, bottomMargin=base, title=self.titulo, author=self.empresa)
        completa = self.inicio() + historia + self.assinatura() + self.validacao_bloco()
        doc.build(completa, onFirstPage=self._pagina, onLaterPages=self._pagina)
        return self.buf.getvalue()

    def _pagina(self, c, d):
        self.paginas = max(self.paginas, d.page)
        self._cabecalho(c, d)
        self._rodape(c, d)



def validacao_padrao(documento='', por='', versao=None, revisao=None, papeis=None, nota=''):
    """Dados do quadro de validação com o nome de quem gerou o documento já preenchido em "Elaborado por"."""
    papeis = papeis or ['Elaborado por', 'Revisado por (responsável técnico / supervisor de proteção radiológica)', 'Aprovado e validado por (direção)']
    v = {'documento': documento, 'papeis': papeis, 'nomes': {papeis[0]: por} if por else {}, 'nota': nota}
    if versao:
        v['versao'] = str(versao)
    if revisao:
        v['revisao'] = revisao
    return v

# ------------------------------------------------------------------ Excel no mesmo modelo
VERDE_XLSX = '255F39'
ZEBRA_XLSX = 'F1F6F3'
TOTAL_XLSX = 'E2ECE6'


def planilha(ws, titulo, empresa, periodo, cab, linhas, larguras, totais=None, formatos=None):
    """Escreve uma aba no modelo comum: título, período, cabeçalho verde, linhas com bordas e linha de totais.
    `formatos`: {índice da coluna: formato numérico do Excel}. Devolve a próxima linha livre."""
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    borda = Side(style='thin', color='9AA8A0')
    caixa = Border(left=borda, right=borda, top=borda, bottom=borda)
    formatos = formatos or {}
    ws.append([titulo])
    ws['A1'].font = Font(bold=True, size=14, color=VERDE_XLSX)
    ws.append([(empresa or 'Nucleleste') + ' · ' + periodo])
    ws.append([])
    ws.append(cab)
    for col in range(1, len(cab) + 1):
        c = ws.cell(row=4, column=col)
        c.font = Font(bold=True, color='FFFFFF')
        c.fill = PatternFill('solid', fgColor=VERDE_XLSX)
        c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        c.border = caixa
    primeira = 5
    for k, linha in enumerate(linhas):
        ws.append(list(linha))
        r = primeira + k
        for col in range(1, len(cab) + 1):
            c = ws.cell(row=r, column=col)
            c.border = caixa
            if k % 2 == 1:
                c.fill = PatternFill('solid', fgColor=ZEBRA_XLSX)
            if (col - 1) in formatos:
                c.number_format = formatos[col - 1]
    proxima = primeira + len(linhas)
    if totais:
        ws.append(list(totais))
        for col in range(1, len(cab) + 1):
            c = ws.cell(row=proxima, column=col)
            c.font = Font(bold=True)
            c.fill = PatternFill('solid', fgColor=TOTAL_XLSX)
            c.border = caixa
            if (col - 1) in formatos:
                c.number_format = formatos[col - 1]
        proxima += 1
    for letra, larg in zip([chr(65 + i) for i in range(len(larguras))], larguras):
        ws.column_dimensions[letra].width = larg
    return proxima + 1


def xlsx_bytes(wb):
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
