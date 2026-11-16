"""Dossiê ONA em PDF: o relatório completo da qualidade para apresentar a auditorias.

Capa com a logo da clínica, sumário (o mesmo que índice) com número de página, uma seção para cada assunto (indicadores ONA, produção, perfil
epidemiológico, agenda, indicadores da qualidade, satisfação, gestão da qualidade, segurança do paciente), cada gráfico com um texto que explica
o que ele representa e uma leitura rápida, quadro de validação e contracapa. Os números vêm só do próprio sistema; o que não tem dado aparece
como "sem dados". Visual no padrão do registro de atualizações (verde Nucleleste), em A4 retrato."""
from __future__ import annotations

import io
import os
from collections import Counter
from datetime import datetime

from reportlab.graphics.shapes import Drawing, Group, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Flowable, Frame, KeepTogether, NextPageTemplate, PageBreak, PageTemplate, Paragraph, Spacer, Table,
                                TableStyle)
from reportlab.platypus.tableofcontents import TableOfContents

from . import qualidade_graficos as gr
from . import util
from .relatorio_base import RelatorioPDF, validacao_padrao

W, H = A4
M = 14 * mm
LARGURA = W - 2 * M                     # 515,9 pt úteis
ESCURO = colors.HexColor('#173c24')
VERDE = colors.HexColor('#255f39')
VERDE2 = colors.HexColor('#2f9e6a')
MENTA = colors.HexColor('#7fd6ae')
CLARO = colors.HexColor('#e8f2ec')
AMARELO = colors.HexColor('#ffd54a')
TEXTO = colors.HexColor('#263238')
SUAVE = colors.HexColor('#5d6b64')
LINHA = colors.HexColor('#cdd6d1')
PASTA = os.path.join(os.path.dirname(__file__), 'static', 'img', 'logo')
LOGO_CLARA = os.path.join(PASTA, 'verde-escuro.png')     # letras claras: para fundo verde escuro
LOGO_ESCURA = os.path.join(PASTA, 'verde-claro.png')     # letras verdes: para fundo branco
MESES = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']


def _data_ext(d):
    return '%d de %s de %d' % (d.day, MESES[d.month - 1], d.year)


def _pct(v, casas=1):
    return '—' if v is None else (('%.' + str(casas) + 'f%%') % v).replace('.', ',')


def _esc(t):
    return str(t if t is not None else '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _est():
    base = dict(fontName='Helvetica', textColor=TEXTO)
    return {
        'corpo': ParagraphStyle('corpo', fontSize=10, leading=14.5, **base),
        'peq': ParagraphStyle('peq', fontSize=8.5, leading=11.5, fontName='Helvetica', textColor=SUAVE),
        'h1': ParagraphStyle('h1', fontName='Helvetica-Bold', fontSize=20, leading=24, textColor=VERDE, spaceAfter=8),
        'sub': ParagraphStyle('Sub', fontName='Helvetica-Bold', fontSize=12.5, leading=16, textColor=VERDE, spaceBefore=12, spaceAfter=5, keepWithNext=1),
        'item': ParagraphStyle('item', fontSize=10, leading=14, leftIndent=13, bulletIndent=2, **base),
        'callout': ParagraphStyle('callout', fontSize=9.4, leading=13.2, **base),
        'cartao_n': ParagraphStyle('cn', fontName='Helvetica-Bold', fontSize=21, leading=24, textColor=VERDE),
        'cartao_t': ParagraphStyle('ct', fontName='Helvetica', fontSize=8.3, leading=10.5, textColor=SUAVE),
    }


EST = _est()


# ------------------------------------------------------------------ elementos de página
class _Secao(Flowable):
    """Faixa verde que abre cada seção: número em círculo amarelo, título e uma frase. Entra no sumário e nos marcadores do PDF."""

    def __init__(self, numero, titulo, frase=''):
        super().__init__()
        self.numero, self.titulo, self.frase = numero, titulo, frase
        self.toc = (0, '%d. %s' % (numero, titulo)) if numero else None

    def wrap(self, aw, ah):
        return aw, 19 * mm

    def draw(self):
        c = self.canv
        c.saveState()
        caminho = c.beginPath()
        caminho.roundRect(0, 0, LARGURA, 17 * mm, 4 * mm)
        c.clipPath(caminho, stroke=0, fill=0)
        c.setFillColor(VERDE)
        c.rect(0, 0, LARGURA, 17 * mm, stroke=0, fill=1)
        c.setFillColor(VERDE2)
        c.setFillAlpha(.55)
        c.circle(LARGURA - 8 * mm, 17 * mm, 22 * mm, stroke=0, fill=1)
        c.setFillAlpha(.35)
        c.circle(LARGURA - 34 * mm, -2 * mm, 15 * mm, stroke=0, fill=1)
        c.setFillAlpha(1)
        c.restoreState()
        c.setFillColor(AMARELO)
        c.circle(10 * mm, 8.5 * mm, 6 * mm, stroke=0, fill=1)
        c.setFillColor(ESCURO)
        if self.numero:
            c.setFont('Helvetica-Bold', 15)
            c.drawCentredString(10 * mm, 6.2 * mm, str(self.numero))
        else:                                           # sumário: ícone de lista
            for k in range(3):
                c.rect(6.4 * mm, (6.6 + k * 2.3) * mm, 7.2 * mm, 1.1 * mm, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont('Helvetica-Bold', 15)
        c.drawString(21 * mm, 9.6 * mm, self.titulo)
        if self.frase:
            c.setFont('Helvetica', 8.8)
            c.setFillColor(colors.HexColor('#d4ecdd'))
            c.drawString(21 * mm, 4.2 * mm, self.frase[:110])


def _sub(texto):
    return Paragraph(_esc(texto), EST['sub'])


def _p(texto, estilo='corpo'):
    return Paragraph(texto, EST[estilo])


def _marcadores(frases, estilo='item'):
    return [Paragraph(_esc(f), EST[estilo], bulletText='•') for f in frases if f]


def _caixa(titulo, texto, fundo=CLARO, barra=VERDE2):
    """Caixa com barra lateral: "Como ler este gráfico" (verde) e "Leitura rápida" (amarela)."""
    corpo = [Paragraph('<b>%s</b>' % _esc(titulo), EST['callout'])]
    if isinstance(texto, (list, tuple)):
        corpo += [Paragraph('• ' + _esc(t), EST['callout']) for t in texto if t]
    else:
        corpo.append(Paragraph(texto, EST['callout']))
    t = Table([[corpo]], colWidths=[LARGURA])
    t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), fundo), ('LINEBEFORE', (0, 0), (0, -1), 3.2, barra), ('LEFTPADDING', (0, 0), (-1, -1), 11),
                           ('RIGHTPADDING', (0, 0), (-1, -1), 10), ('TOPPADDING', (0, 0), (-1, -1), 7), ('BOTTOMPADDING', (0, 0), (-1, -1), 8)]))
    return t


def _como_ler(texto, alvo='este gráfico'):
    return [Spacer(1, 3), _caixa('Como ler ' + alvo, texto)]


def _leitura(frases):
    frases = [f for f in frases if f]
    return [Spacer(1, 4), _caixa('Leitura rápida', frases, fundo=colors.HexColor('#fff8dc'), barra=AMARELO)] if frases else []


def _cartoes(itens):
    """Linha de cartões de números: itens = [(valor, rótulo)] (até 4 por linha)."""
    linhas = []
    for k in range(0, len(itens), 4):
        grupo = itens[k:k + 4]
        grupo += [('', '')] * (4 - len(grupo))
        linhas.append([[Paragraph(_esc(v), EST['cartao_n']), Paragraph(_esc(r), EST['cartao_t'])] if v != '' else '' for v, r in grupo])
    t = Table(linhas, colWidths=[LARGURA / 4.0] * 4, rowHeights=[21 * mm] * len(linhas))
    estilo = [('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('LEFTPADDING', (0, 0), (-1, -1), 10), ('RIGHTPADDING', (0, 0), (-1, -1), 6)]
    for i, linha in enumerate(linhas):
        for j, cel in enumerate(linha):
            if cel != '':
                estilo += [('BOX', (j, i), (j, i), .8, LINHA), ('LINEABOVE', (j, i), (j, i), 3, VERDE2), ('BACKGROUND', (j, i), (j, i), colors.HexColor('#f7fbf8'))]
    t.setStyle(TableStyle(estilo))
    return [t, Spacer(1, 6)]


def _grafico(d):
    d.hAlign = 'CENTER'
    return d


def _itens(pares, maximo=10):
    pares = [(k, v) for k, v in pares if v]
    total = sum(v for _k, v in pares) or 1
    return [{'rotulo': str(k), 'n': v, 'pct': 100.0 * v / total} for k, v in pares[:maximo]]


def _barras_pct(linhas, largura=480):
    """Barras de 0 a 100 %: linhas = [(nome, percentual|None, melhor_menor)]. Verde 90 % ou mais, âmbar de 70 a 89, vermelho abaixo (invertido para os
    indicadores em que menor é melhor)."""
    alt = 22
    d = Drawing(largura, len(linhas) * alt + 18)
    g = Group()
    x0, area = 176, largura - 176 - 46
    for k, (nome, pct, menor) in enumerate(linhas):
        y = d.height - 12 - (k + 1) * alt + 6
        g.add(String(x0 - 6, y + 4, gr.quebrar(nome, gr.FONTE, 8, x0 - 10, 1)[0], fontName=gr.FONTE, fontSize=8, fillColor=gr.TEXTO, textAnchor='end'))
        g.add(Rect(x0, y, area, 11, fillColor=colors.HexColor('#e9efeb'), strokeColor=None, rx=5.5, ry=5.5))
        if pct is not None:
            bom = (100 - pct) if menor else pct
            cor = '#2f9e6a' if bom >= 90 else ('#f0a500' if bom >= 70 else '#d9534f')
            g.add(Rect(x0, y, max(2, area * min(pct, 100) / 100.0), 11, fillColor=gr._cor(cor), strokeColor=None, rx=5.5, ry=5.5))
            g.add(String(x0 + area + 6, y + 2.5, _pct(pct), fontName=gr.NEGRITO, fontSize=8.5, fillColor=gr.TEXTO))
        else:
            g.add(String(x0 + area + 6, y + 2.5, 'sem dados', fontName=gr.FONTE, fontSize=8, fillColor=gr.LINHA))
    for marca in (0, 50, 100):
        g.add(String(x0 + area * marca / 100.0, 2, '%d%%' % marca, fontName=gr.FONTE, fontSize=7, fillColor=gr.LINHA, textAnchor='middle'))
    d.add(g)
    return _grafico(d)


def _barras(pares, cor, maximo=10):
    return _grafico(gr.barras_h(_itens(pares, maximo), 480, cor, maximo))


def _colunas(pares, cor, altura=125):
    return _grafico(gr.colunas([{'rotulo': k, 'n': v} for k, v in pares], 480, altura, cor))


def _tabela(rp, cab, linhas, larguras, direita=()):
    return rp.tabela(cab, linhas, larguras, direita=direita)


# ------------------------------------------------------------------ documento
class _Doc(BaseDocTemplate):
    def __init__(self, buf, clinica, periodo, **kw):
        super().__init__(buf, pagesize=A4, leftMargin=M, rightMargin=M, topMargin=24 * mm, bottomMargin=19 * mm, **kw)
        self.clinica, self.periodo = clinica, periodo
        corpo = Frame(M, 19 * mm, LARGURA, H - 43 * mm, id='corpo', leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        info = Frame(M + 4 * mm, 17 * mm, LARGURA - 8 * mm, 58 * mm, id='info', leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        meio = Frame(M, 100 * mm, LARGURA, 62 * mm, id='meio', leftPadding=0, rightPadding=0)
        self.addPageTemplates([PageTemplate(id='capa', frames=[info], onPage=self._capa),
                               PageTemplate(id='miolo', frames=[corpo], onPage=self._miolo),
                               PageTemplate(id='contra', frames=[meio], onPage=self._contra)])
        self.gerado = datetime.now()
        self.eixo = {}

    def afterFlowable(self, f):
        toc = getattr(f, 'toc', None)
        if toc is None and isinstance(f, Paragraph) and f.style.name == 'Sub':
            toc = (1, f.getPlainText())
        if toc:
            nivel, texto = toc
            chave = 'm%d' % self.seq
            self.seq += 1
            self.canv.bookmarkPage(chave)
            self.canv.addOutlineEntry(texto, chave, level=nivel, closed=False)
            self.notify('TOCEntry', (nivel, texto, self.page, chave))

    def handle_documentBegin(self):
        self.seq = 0
        super().handle_documentBegin()

    # --- capa
    def _fundo(self, c):
        c.setFillColor(ESCURO)
        c.rect(0, 0, W, H, stroke=0, fill=1)
        c.saveState()
        c.setFillColor(VERDE)
        c.setFillAlpha(.55)
        c.circle(W - 2 * mm, H - 6 * mm, 92 * mm, stroke=0, fill=1)
        c.setFillColor(VERDE2)
        c.setFillAlpha(.35)
        c.circle(W - 34 * mm, H - 40 * mm, 52 * mm, stroke=0, fill=1)
        c.setStrokeColor(colors.white)
        c.setStrokeAlpha(.28)
        c.setLineWidth(1.4)
        for ang in (0, 60, 120):                       # átomo da marca
            c.saveState()
            c.translate(W - 44 * mm, H - 58 * mm)
            c.rotate(ang)
            c.ellipse(-38 * mm, -12 * mm, 38 * mm, 12 * mm, stroke=1, fill=0)
            c.restoreState()
        c.setFillColor(AMARELO)
        c.setFillAlpha(.9)
        c.circle(W - 44 * mm, H - 58 * mm, 3 * mm, stroke=0, fill=1)
        c.restoreState()

    def _logo(self, c, caminho, x, y, largura):
        if os.path.exists(caminho):
            c.drawImage(caminho, x, y, width=largura, height=largura * 0.396, mask='auto', preserveAspectRatio=True)

    def _capa(self, c, doc):
        c.saveState()
        self._fundo(c)
        self._logo(c, LOGO_CLARA, 14 * mm, H - 66 * mm, 118 * mm)
        c.setFillColor(AMARELO)
        c.rect(M, H - 118 * mm, 26 * mm, 2.2 * mm, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont('Helvetica-Bold', 44)
        c.drawString(M, H - 140 * mm, 'Dossiê ONA')
        c.setFont('Helvetica', 17)
        c.setFillColor(MENTA)
        c.drawString(M, H - 152 * mm, 'Qualidade, indicadores e perfil dos pacientes')
        c.setFont('Helvetica', 11.5)
        c.setFillColor(colors.HexColor('#d4ecdd'))
        c.drawString(M, H - 163 * mm, 'Relatório para auditoria de acreditação (Organização Nacional de Acreditação)')
        # painel branco com os dados da emissão
        c.setFillColor(colors.white)
        c.roundRect(M - 2 * mm, 14 * mm, LARGURA + 4 * mm, 70 * mm, 6 * mm, stroke=0, fill=1)
        c.setFillColor(AMARELO)
        c.rect(M + 4 * mm, 78 * mm, 22 * mm, 1.6 * mm, stroke=0, fill=1)
        c.restoreState()

    # --- miolo
    def _miolo(self, c, doc):
        c.saveState()
        c.setFillColor(ESCURO)
        c.rect(0, H - 16 * mm, W, 16 * mm, stroke=0, fill=1)
        c.setFillColor(AMARELO)
        c.rect(0, H - 16.8 * mm, W, .8 * mm, stroke=0, fill=1)
        self._logo(c, LOGO_CLARA, M - 4 * mm, H - 16.2 * mm, 40 * mm)
        c.setFillColor(colors.white)
        c.setFont('Helvetica-Bold', 9)
        c.drawRightString(W - M, H - 7.2 * mm, 'DOSSIÊ ONA')
        c.setFont('Helvetica', 8.3)
        c.setFillColor(colors.HexColor('#d4ecdd'))
        c.drawRightString(W - M, H - 11.6 * mm, self.periodo)
        c.setStrokeColor(LINHA)
        c.setLineWidth(.6)
        c.line(M, 14 * mm, W - M, 14 * mm)
        c.setFillColor(SUAVE)
        c.setFont('Helvetica', 8)
        c.drawString(M, 9.2 * mm, '%s · gerado em %s' % (self.clinica, self.gerado.strftime('%d/%m/%Y %H:%M')))
        c.setFillColor(VERDE)
        c.roundRect(W - M - 11 * mm, 6.6 * mm, 11 * mm, 6 * mm, 3 * mm, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont('Helvetica-Bold', 8.5)
        c.drawCentredString(W - M - 5.5 * mm, 8.6 * mm, str(doc.page))
        c.restoreState()

    # --- contracapa
    def _contra(self, c, doc):
        c.saveState()
        self._fundo(c)
        self._logo(c, LOGO_CLARA, (W - 130 * mm) / 2, H - 120 * mm, 130 * mm)
        c.setFillColor(AMARELO)
        c.rect((W - 24 * mm) / 2, H - 126 * mm, 24 * mm, 1.8 * mm, stroke=0, fill=1)
        c.restoreState()


def _info_capa(clinica, periodo, usuario, versao, agora):
    est = ParagraphStyle('ic', fontName='Helvetica', fontSize=11, leading=15, textColor=TEXTO)
    rot = ParagraphStyle('ir', fontName='Helvetica-Bold', fontSize=8.5, leading=11, textColor=VERDE2)
    linhas = [[Paragraph('CLÍNICA', rot), Paragraph('PERÍODO ANALISADO', rot)],
              [Paragraph('<b>%s</b>' % _esc(clinica), est), Paragraph('<b>%s</b>' % _esc(periodo), est)],
              [Paragraph('EMITIDO EM', rot), Paragraph('EMITIDO POR', rot)],
              [Paragraph(_data_ext(agora) + ', ' + agora.strftime('%H:%M'), est), Paragraph(_esc((usuario or 'Sistema').title()), est)],
              [Paragraph('VERSÃO DO SISTEMA', rot), Paragraph('ORIGEM DOS DADOS', rot)],
              [Paragraph('Nucleleste %s' % _esc(versao), est), Paragraph('Registros do próprio sistema', est)]]
    t = Table(linhas, colWidths=[(LARGURA - 8 * mm) / 2] * 2)
    t.setStyle(TableStyle([('TOPPADDING', (0, 0), (-1, -1), 1.5), ('BOTTOMPADDING', (0, 0), (-1, -1), 1.5), ('TOPPADDING', (0, 2), (-1, 2), 9),
                           ('TOPPADDING', (0, 4), (-1, 4), 9), ('LEFTPADDING', (0, 0), (-1, -1), 0)]))
    return [Spacer(1, 3 * mm), t]


# ------------------------------------------------------------------ coleta
def coletar(db, de, ate):
    """Reúne os dados de cada seção; quem falhar vira None (a seção mostra "sem dados" e o resto do dossiê sai normalmente)."""
    from . import agenda as ag
    from . import ona
    from . import pesquisa
    from . import qualidade as q
    from . import qualidade_dados as qd
    from . import qualidade_epidemio as epi

    def tentar(f):
        try:
            return f()
        except Exception:      # um módulo sem dados não pode impedir o relatório
            db.rollback()
            return None

    dados = {'ona': ona.indicadores(db, de, ate)}
    dados['epi'] = tentar(lambda: epi.perfil(db, de, ate))
    dados['agenda'] = tentar(lambda: ag.relatorio(db, de, ate))
    dados['kpi'] = tentar(lambda: qd.painel(db, de, ate))
    dados['sat'] = tentar(lambda: pesquisa.indicadores(db, de.isoformat(), ate.isoformat()))

    def qualidade():
        q.garantir(db)
        return {'problemas': q.problemas(db), 'acoes': q.acoes(db), 'riscos': q.riscos(db), 'ocorrencias': q.ocorrencias(db, de.isoformat(), ate.isoformat())}
    dados['qual'] = tentar(qualidade)

    def seguranca():
        from . import enfermagem as enf
        enf.garantir(db)
        return {'carrinhos': enf.carrinhos(db), 'equipamentos': enf.equipamentos(db), 'reposicao': enf.reposicao(db), 'pacotes': enf.pacotes(db)}
    dados['seg'] = tentar(seguranca)
    return dados


# ------------------------------------------------------------------ seções
EXPLICA_IND = {
    'Identificação do paciente': 'Garante que cada exame pertence à pessoa certa: nome e data de nascimento preenchidos. É a base da segurança do paciente.',
    'Registro completo do exame': 'Mede se o exame foi registrado por inteiro (convênio, médico solicitante, data e hora), o que permite rastrear o atendimento.',
    'Cadastro com CPF': 'Mostra quantos clientes têm o CPF no cadastro, o documento que evita cadastros duplicados e confusão entre homônimos.',
    'Cadastro com sexo informado': 'O sexo informado é necessário para o perfil epidemiológico e para protocolos clínicos que dependem dele.',
    'Laudo entregue no prazo': 'Percentual de laudos liberados dentro do prazo definido pela gerência. Reflete a agilidade da entrega ao paciente e ao médico.',
    'Laudos retificados': 'Laudos corrigidos depois de liberados. Aqui, quanto MENOR, melhor: indica menos erros que chegam ao paciente.',
    'Comparecimento na agenda': 'Entre os pacientes marcados, quantos vieram. Faltas desperdiçam doses de radiofármaco e horários de equipamento.',
}
MENOR_MELHOR = {'Laudos retificados'}


def _secao_apresentacao(d, rp, de, ate, clinica):
    n = d['ona']
    hist = [_Secao(1, 'Apresentação', 'O que é este documento e como lê-lo'),
            Spacer(1, 7),
            _p('Este dossiê reúne, em um só documento, as informações de qualidade da <b>%s</b> no período de <b>%s a %s</b>, organizadas para a '
               'apresentação a avaliadores da <b>ONA (Organização Nacional de Acreditação)</b>. A acreditação ONA avalia se a organização de saúde '
               'trabalha com segurança, qualidade e melhoria contínua, e pede que isso seja demonstrado com dados.' %
               (_esc(clinica), util.data_br(n['de']), util.data_br(n['ate']))),
            Spacer(1, 4),
            _p('Todos os números são calculados automaticamente pelo sistema Nucleleste, a partir do que a equipe registrou no dia a dia (atendimentos, '
               'exames realizados, agenda, laudos, pesquisa de satisfação, ferramentas da qualidade e controles da enfermagem). Nada foi digitado à parte. '
               'Quando não há registro suficiente, a seção diz "sem dados" em vez de inventar um valor.'),
            _sub('Como cada seção está organizada'),
            ] + _marcadores(['Um texto curto explica o assunto e por que ele importa para a acreditação.',
                             'Cada gráfico tem logo abaixo o quadro "Como ler este gráfico", em linguagem simples.',
                             'O quadro amarelo "Leitura rápida" resume o que os números mostram naquele período.',
                             'No fim, há o quadro de validação para as assinaturas de quem elaborou, revisou e aprovou.']) + [
        _sub('Cores usadas nos gráficos de indicadores'),
        Table([[Paragraph('<font color="#2f9e6a"><b>Verde</b></font>: resultado esperado (90% ou mais; para "menor é melhor", até 10%).', EST['peq']),
                Paragraph('<font color="#f0a500"><b>Âmbar</b></font>: atenção (entre 70% e 89%).', EST['peq']),
                Paragraph('<font color="#d9534f"><b>Vermelho</b></font>: crítico (abaixo de 70%).', EST['peq'])]], colWidths=[LARGURA * .42, LARGURA * .28, LARGURA * .30]),
        Spacer(1, 6),
        _caixa('Atenção', 'As definições dos indicadores devem ser conferidas com o manual da ONA vigente antes do envio. Este dossiê organiza e demonstra '
                          'os dados do sistema; a avaliação final é sempre do avaliador e da direção da clínica.',
               fundo=colors.HexColor('#fff8dc'), barra=AMARELO)]
    return hist


def _secao_resumo(d, rp, de, ate):
    n = d['ona']
    ind = {i['nome']: i for i in n['indicadores']}
    epi, ag, sat, kpi = d['epi'], d['agenda'], d['sat'], d['kpi']
    cart = [(str(n['total_exames']), 'exames realizados no período')]
    cart.append((str(epi['pacientes']) if epi else '—', 'pacientes atendidos'))
    cart.append((_pct(ind['Comparecimento na agenda']['percentual']), 'comparecimento na agenda'))
    cart.append((_pct(sat['geral']['satisfacao']) if sat and sat['respostas'] else '—', 'satisfação dos clientes'))
    if kpi:
        r = kpi['resumo']
        cart += [(str(r['ok']), 'indicadores da qualidade na meta'), (str(r['atencao'] + r['critico']), 'em atenção ou críticos')]
    com_dado = [i for i in n['indicadores'] if i['percentual'] is not None]
    pior = min(com_dado, key=lambda i: ((100 - i['percentual']) if i['nome'] in MENOR_MELHOR else i['percentual']) * (-1 if i['nome'] in MENOR_MELHOR else 1)) if com_dado else None
    melhor = max(com_dado, key=lambda i: ((100 - i['percentual']) if i['nome'] in MENOR_MELHOR else i['percentual'])) if com_dado else None
    leitura = []
    if melhor:
        leitura.append('Melhor resultado entre os indicadores ONA: %s (%s).' % (melhor['nome'], _pct(melhor['percentual'])))
    if pior and pior is not melhor:
        leitura.append('Principal ponto de atenção: %s (%s).' % (pior['nome'], _pct(pior['percentual'])))
    if ag and ag['geral']['taxa_falta'] is not None:
        leitura.append('Taxa de falta na agenda: %s (%d faltas entre %d que vieram ou faltaram).' %
                       (_pct(ag['geral']['taxa_falta']), ag['geral']['FALTOU'], ag['geral']['VEIO'] + ag['geral']['FALTOU']))
    if not n['total_exames']:
        leitura = ['Não há exames realizados registrados neste período; escolha outro período para um retrato mais completo.']
    mapa = [['3. Indicadores ONA', 'A qualidade do registro e do atendimento, com o percentual de cada indicador.'],
            ['4. Produção de exames', 'O volume de exames por tipo, convênio e sexo.'],
            ['5. Perfil epidemiológico', 'Quem são os pacientes: idade, sexo, procedência, convênios, médicos, diagnósticos e os capítulos da CID, IMC.'],
            ['6. Agenda e comparecimento', 'Quantos vieram, faltaram ou marcaram retorno, e onde se perde mais pacientes.'],
            ['7. Indicadores da qualidade', 'Cada indicador contra a sua meta, com a situação em cores.'],
            ['8. Satisfação do cliente', 'A opinião dos pacientes sobre o atendimento, pergunta a pergunta.'],
            ['9. Gestão da qualidade', 'Problemas, planos de ação, riscos e ocorrências (ciclo PDCA).'],
            ['10. Segurança do paciente', 'Carrinho de emergência, equipamentos, medicamentos e esterilização.']]
    return ([PageBreak(), _Secao(2, 'Resumo executivo', 'Os números principais do período em uma página'), Spacer(1, 7),
             _p('Os cartões abaixo mostram, de relance, o tamanho da operação e como a clínica está nos principais indicadores. Os detalhes de cada número '
                'estão nas seções seguintes.')] + [Spacer(1, 5)] + _cartoes(cart) + _leitura(leitura) +
            [_sub('Mapa do dossiê: o que cada seção responde'), rp.tabela(['Seção', 'O que mostra'], mapa, [52, 130])])


def _secao_indicadores(d, rp):
    n = d['ona']
    linhas = [(i['nome'], i['percentual'], i['nome'] in MENOR_MELHOR) for i in n['indicadores']]
    hist = [PageBreak(), _Secao(3, 'Indicadores ONA', 'Segurança, registro, entrega do laudo e comparecimento'), Spacer(1, 7),
            _p('Os indicadores abaixo medem a qualidade do registro e do atendimento com dados que o sistema consegue conferir sozinho. Cada um é uma fração: '
               'o <b>numerador</b> é quantos casos atendem ao critério e o <b>denominador</b> é o total considerado. O percentual é numerador dividido por denominador.'),
            _sub('Situação dos indicadores'), _barras_pct(linhas)]
    hist += _como_ler('Cada barra vai de 0 a 100%. Quanto mais cheia e verde, melhor o resultado. A exceção é "Laudos retificados", em que quanto menor a barra, '
                      'melhor. Barras cinzas sem número significam que ainda não há dados no período.')
    hist += [_sub('Números de cada indicador'),
             _tabela(rp, ['Indicador', 'Critério', 'Num.', 'Den.', '%'],
                     [[i['nome'], i['criterio'], i['numerador'], i['denominador'], _pct(i['percentual'])] for i in n['indicadores']], [40, 82, 16, 16, 20], direita=(2, 3, 4)),
             _sub('O que cada indicador significa')]
    for i in n['indicadores']:
        hist.append(KeepTogether([_p('<b>%s.</b> %s' % (_esc(i['nome']), _esc(EXPLICA_IND.get(i['nome'], i['criterio']))))]))
        hist.append(Spacer(1, 2))
    return hist


def _secao_producao(d, rp):
    n = d['ona']
    hist = [PageBreak(), _Secao(4, 'Produção de exames', 'O que foi realizado, por exame, convênio e sexo'), Spacer(1, 7),
            _p('A produção mostra o volume de trabalho da clínica e a quem ele serve. Para a acreditação, ajuda a provar que os serviços oferecidos '
               'estão em uso e que a organização conhece o seu público.'),
            _sub('Exames realizados por tipo de exame'), _barras(n['por_exame'], '#2f7a49')]
    hist += _como_ler('Cada barra é um tipo de exame; o número à direita é a quantidade realizada e, entre parênteses, a fatia dele no total. '
                      'Barras maiores são os exames mais frequentes.')
    hist += [_sub('Exames realizados por convênio'), _barras(n['por_convenio'], '#1565c0')]
    hist += _como_ler('Mostra de onde vêm os atendimentos: cada barra é um convênio (ou particular). Uma barra muito dominante indica dependência de uma só fonte pagadora.')
    hist += [_sub('Exames realizados por sexo do paciente'), _barras(n['por_sexo'], '#7b1fa2')]
    hist += _como_ler('Divide os exames entre pacientes do sexo masculino e feminino. "Não informado" mostra quantos cadastros ainda estão sem essa informação.')
    topo = n['por_exame'][0] if n['por_exame'] else None
    topc = n['por_convenio'][0] if n['por_convenio'] else None
    hist += _leitura([('Exame mais realizado: %s (%d).' % topo) if topo else '', ('Convênio com mais exames: %s (%d).' % topc) if topc else '',
                      ('Total no período: %d exames.' % n['total_exames'])])
    return hist


def _secao_epidemio(d, rp):
    pf = d['epi']
    hist = [PageBreak(), _Secao(5, 'Perfil epidemiológico', 'Quem são os pacientes atendidos'), Spacer(1, 7)]
    if not pf or not pf['total_exames']:
        return hist + [_p('Sem dados no período: não há exames realizados registrados para montar o perfil dos pacientes.')]
    hist += [_p('O perfil epidemiológico descreve as pessoas atendidas: idade, sexo, de onde vêm, que exames fazem e com quais diagnósticos (CID). '
                'A ONA espera que a organização conheça o seu público para planejar serviços e riscos. Cada paciente é contado uma vez, mesmo com vários exames.')]
    idade = pf['idade']
    cart = [(str(pf['pacientes']), 'pacientes atendidos'), (str(pf['total_exames']), 'exames realizados'),
            (_pct(pf['pct_retorno']), 'com mais de um exame no período'),
            (('%.1f' % idade['media']).replace('.', ',') + ' anos' if idade['media'] is not None else '—', 'idade média')]
    hist += _cartoes(cart)
    hist += [_sub('Pirâmide etária'), _grafico(gr.piramide_etaria(pf['piramide'], pf['max_faixa'], 480))]
    hist += _como_ler('Cada linha é uma faixa de idade. A barra azul à esquerda conta os homens e a rosa à direita as mulheres. Quanto mais larga a barra, mais pacientes '
                      'naquela faixa. O formato mostra se o público é mais jovem, mais idoso ou equilibrado.')
    hist += [_sub('Sexo e faixa etária'), _barras([(i['rotulo'], i['n']) for i in pf['sexo']], '#7b1fa2'), Spacer(1, 4),
             _barras([(i['rotulo'], i['n']) for i in pf['faixas']], '#2f7a49', 9)]
    hist += _como_ler('A primeira sequência de barras divide os pacientes por sexo; a segunda, por faixa de idade na data do exame. Os números são de pacientes, não de exames.')
    hist += [PageBreak(), _sub('Procedência: cidade e bairro'), _barras([(i['rotulo'], i['n']) for i in pf['cidades']], '#ef6c00'), Spacer(1, 4),
             _barras([(i['rotulo'], i['n']) for i in pf['bairros']], '#ef6c00')]
    hist += _como_ler('Mostra de onde as pessoas vêm. Cidades e bairros no topo são a área de abrangência real da clínica, útil para planejar divulgação e transporte.')
    hist += [_sub('Diagnósticos (CID)'), _barras([(i['rotulo'], i['n']) for i in pf['cids']], '#c62828')]
    hist += _como_ler('O CID é o código do diagnóstico informado no pedido. As barras mostram os mais frequentes. "Sem CID" indica pedidos que chegaram sem essa informação.')
    hist += [_sub('Convênios e médicos solicitantes'), _barras([(i['rotulo'], i['n']) for i in pf['convenios']], '#00838f'), Spacer(1, 4),
             _barras([(i['rotulo'], i['n']) for i in pf['medicos']], '#5d4037')]
    hist += _como_ler('A primeira sequência mostra os convênios; a segunda, os médicos que mais encaminham pacientes. Ajuda a ver quem sustenta a demanda.')
    hist += [PageBreak(), _sub('Evolução mensal e dias da semana'), _colunas([(i['rotulo'], i['n']) for i in pf['meses']], '#1565c0'), Spacer(1, 4),
             _colunas([(i['rotulo'], i['n']) for i in pf['dias']], '#2f7a49')]
    hist += _como_ler('As colunas de cima mostram quantos exames foram feitos em cada mês; as de baixo, em cada dia da semana. Servem para ver sazonalidade e os dias de maior movimento.')
    hist += [_sub('Diagnósticos por capítulo da CID-10'), _barras([(i['rotulo'], i['n']) for i in pf['cid_capitulos']], '#c62828')]
    hist += _como_ler('Agrupa os diagnósticos em grandes grupos de doenças (capítulos da CID-10). "Sem CID" indica pedidos sem diagnóstico informado.')
    media_imc = ('%.1f' % pf['imc_media']).replace('.', ',') if pf['imc_media'] is not None else None
    hist += [_sub('IMC dos pacientes adultos'), _barras([(i['rotulo'], i['n']) for i in pf['imc']], '#2f7a49')]
    hist += _como_ler('IMC é o peso dividido pelo quadrado da altura. Considera só pessoas com 18 anos ou mais e peso e altura válidos. ' +
                      ('Média do IMC: %s.' % media_imc if media_imc else 'Não há exames de adultos com peso e altura válidos no período.'))
    hist += [_sub('Idade média por exame'),
             _tabela(rp, ['Exame', 'Exames', 'Idade média'],
                     [[i['rotulo'], i['n'], ('%.1f' % i['media']).replace('.', ',') + ' anos' if i['media'] is not None else '—'] for i in pf['idade_por_exame']],
                     [60, 20, 20], direita=(1, 2))]
    hist += _como_ler('Mostra a idade média das pessoas que fizeram cada exame. Ajuda a ver para qual público cada exame é mais usado.', 'esta tabela')
    hist += [_sub('Exames por sexo'),
             _tabela(rp, ['Exame', 'Feminino', 'Masculino', 'Não informado'],
                     [[i['rotulo'], i['F'], i['M'], i['N']] for i in pf['exames_por_sexo']], [40, 20, 20, 20], direita=(1, 2, 3))]
    hist += _como_ler('Quantos exames de cada tipo foram feitos em mulheres, homens e pessoas sem sexo informado.', 'esta tabela')
    hist += [_sub('Procedência: mesma cidade × outras cidades'), _barras([(i['rotulo'], i['n']) for i in pf['procedencia_local']], '#ef6c00')]
    hist += _como_ler('Compara pacientes que moram na mesma cidade da clínica com os de outras cidades. "Não informado" são cadastros sem cidade.')
    hist += [_sub('Qualidade dos dados usados'),
             _tabela(rp, ['Informação', 'Preenchidos', 'Total', '%'],
                     [[q['rotulo'], q['n'], q['de'], _pct(100.0 * q['n'] / q['de']) if q['de'] else '—'] for q in pf['qualidade_dado']], [92, 30, 25, 25], direita=(1, 2, 3))]
    hist += _como_ler('Mostra quanto do cadastro está completo. Se sexo, nascimento, cidade ou CID estiverem em branco, o perfil fica incompleto. Quanto mais próximo de 100%, mais fiel o retrato.', 'esta tabela')
    ruim = [q['rotulo'] for q in pf['qualidade_dado'] if q['de'] and q['n'] / float(q['de']) < .9]
    hist += _leitura(['Idade média de %s anos (mediana %s).' % (('%.1f' % idade['media']).replace('.', ','), ('%g' % idade['mediana']).replace('.', ',')) if idade['media'] is not None else '',
                      ('Maior procedência: %s.' % pf['cidades'][0]['rotulo']) if pf['cidades'] else '',
                      ('Dados com menos de 90%% de preenchimento: %s.' % '; '.join(ruim)) if ruim else 'Cadastro com bom preenchimento nos itens avaliados.'])
    return hist


def _secao_agenda(d, rp):
    ag = d['agenda']
    hist = [PageBreak(), _Secao(6, 'Agenda e comparecimento', 'Quem foi agendado, veio, faltou ou marcou retorno'), Spacer(1, 7)]
    if not ag or not ag['geral']['marcados']:
        return hist + [_p('Sem dados no período: não há pacientes agendados.')]
    g = ag['geral']
    hist += [_p('A agenda mostra se o serviço é bem aproveitado. Faltas e remarcações em excesso significam horário de equipamento perdido, '
                'dose de radiofármaco desperdiçada e paciente sem atendimento. A taxa de falta considera quem veio e quem faltou.')]
    hist += _cartoes([(str(g['marcados']), 'pacientes agendados'), (str(g['VEIO']), 'vieram'), (str(g['FALTOU']), 'faltaram'),
                      (str(g['RETORNO']), 'retornos marcados'), (str(g.get('chegou', 0)), 'chegaram (caixa Chegou)'), (_pct(g['taxa_falta']), 'taxa de falta'),
                      (str(g['livres']), 'horários livres (de %d)' % g['vagas'])])
    hist += [_sub('Vieram e faltaram por exame'), _barras([(e['nome'], e['VEIO']) for e in ag['por_exame']], '#2f7a49'), Spacer(1, 4),
             _barras([(e['nome'], e['FALTOU']) for e in ag['por_exame']], '#c62828')]
    hist += _como_ler('A primeira sequência de barras (verde) conta quem VEIO em cada exame; a segunda (vermelha), quem FALTOU. Comparar as duas mostra quais exames perdem mais pacientes.')
    hist += [_sub('Comparecimento por exame'),
             _tabela(rp, ['Exame', 'Agend.', 'Vieram', 'Faltaram', 'Retorno', 'Taxa de falta'],
                     [[e['nome'], e['marcados'], e['VEIO'], e['FALTOU'], e['RETORNO'], _pct(e['taxa_falta'])] for e in ag['por_exame']], [62, 22, 22, 24, 22, 28], direita=(1, 2, 3, 4, 5))]
    hist += _como_ler('Cada linha é um exame com os números do período. A taxa de falta é faltaram dividido por (vieram + faltaram): quanto menor, melhor.', 'esta tabela')
    piores = [e for e in ag['por_exame'] if e['taxa_falta'] is not None]
    pior = max(piores, key=lambda e: e['taxa_falta']) if piores else None
    hist += _leitura([('Maior taxa de falta: %s (%s).' % (pior['nome'], _pct(pior['taxa_falta']))) if pior else '',
                      'No MIBI, Repouso e Estresse do mesmo paciente contam como um exame só; o Protocolo conta como um MIBI completo.'])
    return hist


COR_SIT = {'ok': '#2f9e6a', 'atencao': '#f0a500', 'critico': '#d9534f', 'sem_dado': '#90a4ae'}
NOME_SIT = {'ok': 'Na meta', 'atencao': 'Atenção', 'critico': 'Crítico', 'sem_dado': 'Sem dado'}


def _secao_kpi(d, rp):
    kpi = d['kpi']
    hist = [PageBreak(), _Secao(7, 'Indicadores da qualidade', 'Resultado contra a meta de cada indicador'), Spacer(1, 7)]
    if not kpi:
        return hist + [_p('Sem dados: o painel de indicadores da qualidade não está disponível.')]
    r = kpi['resumo']
    hist += [_p('Os indicadores da qualidade acompanham processos importantes (agenda, laudos, cadastro, retrabalho, financeiro, satisfação). Cada um tem uma '
                '<b>meta</b> definida pela clínica e uma <b>situação</b>: na meta, atenção ou crítico. Indicadores críticos pedem um plano de ação.')]
    hist += _cartoes([(str(r['ok']), 'na meta'), (str(r['atencao']), 'em atenção'), (str(r['critico']), 'críticos'), (str(r['sem_dado']), 'sem dado')])
    linhas = []
    for i in kpi['indicadores']:
        un = i['unidade']
        val = '—' if i['valor'] is None else (_pct(i['valor']) if un == '%' else ('%g' % i['valor']).replace('.', ',') + (' h' if un == 'h' else ''))
        meta = '—' if i['meta'] is None else ('>= ' if i['sentido'] == 'min' else '<= ') + (_pct(i['meta']) if un == '%' else ('%g' % i['meta']).replace('.', ',') + (' h' if un == 'h' else ''))
        linhas.append([i['nome'], val, meta, '<font color="%s"><b>%s</b></font>' % (COR_SIT[i['situacao']], NOME_SIT[i['situacao']])])
    cab = ['Indicador', 'Valor', 'Meta', 'Situação']
    est = rp.e
    dados = [[Paragraph(c, est['cab']) for c in cab]] + [[Paragraph(_esc(l[0]), est['cel']), Paragraph(_esc(l[1]), est['cel_dir']), Paragraph(_esc(l[2]), est['cel_dir']),
                                                         Paragraph(l[3], est['cel'])] for l in linhas]
    t = Table(dados, repeatRows=1, colWidths=[w * mm for w in (88, 26, 30, 38)])
    t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), VERDE), ('GRID', (0, 0), (-1, -1), .5, LINHA), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                           ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4), ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, CLARO])]))
    hist += [_sub('Indicadores, metas e situação'), t]
    hist += _como_ler('A coluna "Valor" é o resultado do período; "Meta" é o limite combinado (>= significa que o valor deve ser igual ou maior; <= , igual ou menor). '
                      'A situação é verde quando a meta é cumprida, âmbar quando está perto e vermelha quando está longe.', 'esta tabela')
    crit = [i['nome'] for i in kpi['indicadores'] if i['situacao'] == 'critico']
    atenc = [i['nome'] for i in kpi['indicadores'] if i['situacao'] == 'atencao']
    hist += _leitura([('Críticos (exigem plano de ação): ' + '; '.join(crit)) if crit else 'Nenhum indicador crítico no período.',
                      ('Em atenção: ' + '; '.join(atenc)) if atenc else ''])
    return hist


def _secao_satisfacao(d, rp):
    sat = d['sat']
    hist = [PageBreak(), _Secao(8, 'Satisfação do cliente', 'O que os pacientes dizem do atendimento'), Spacer(1, 7)]
    if not sat or not sat['respostas']:
        return hist + [_p('Sem dados no período: nenhuma resposta da pesquisa de satisfação foi registrada.')]
    hist += [_p('A pesquisa de satisfação é respondida pelo próprio paciente, pelo celular, por QR Code. As opções Ótimo, Bom, Ruim e Péssimo viram uma nota de 0 a 10; '
                'a <b>satisfação</b> é o percentual de respostas Ótimo ou Bom. É uma das evidências mais valorizadas pela ONA, pois mostra a voz do cliente.')]
    hist += _cartoes([(str(sat['respostas']), 'respostas no período'), (_pct(sat['geral']['satisfacao']), 'satisfação geral (Ótimo + Bom)'),
                      (('%.1f' % sat['media']).replace('.', ',') if sat['media'] is not None else '—', 'nota média (0 a 10)'), (str(sat['elogios']), 'elogios escritos'),
                      (str(sat['sugestoes']), 'sugestões escritas'), (str(sat['pendentes']), 'respostas ainda não revisadas')])
    hist += [_sub('Satisfação por pergunta'), _barras_pct([(p['texto'], p['satisfacao'], False) for p in sat['perguntas']])]
    hist += _como_ler('Cada barra é uma pergunta da pesquisa, e o tamanho dela é o percentual de pessoas que responderam Ótimo ou Bom. Verde significa boa avaliação; '
                      'barras curtas e vermelhas apontam o que precisa melhorar.')
    if sat['meses']:
        hist += [_sub('Satisfação mês a mês'), _colunas([(m['mes'][5:] + '/' + m['mes'][:4], int(round(m['satisfacao'] or 0))) for m in sat['meses']], '#2f9e6a')]
        hist += _como_ler('Cada coluna é um mês e a altura é o percentual de satisfação (0 a 100). Mostra se o atendimento está melhorando ou piorando ao longo do tempo.')
    fraca = [p for p in sat['perguntas'] if p['satisfacao'] is not None]
    pior = min(fraca, key=lambda p: p['satisfacao']) if fraca else None
    hist += [_sub('Detalhe por pergunta'),
             _tabela(rp, ['Pergunta', 'Resp.', 'Ótimo', 'Bom', 'Ruim', 'Péssimo', 'Satisf.'],
                     [[p['texto'], p['total'], p['otimo'], p['bom'], p['ruim'], p['pessimo'], _pct(p['satisfacao'])] for p in sat['perguntas']], [66, 16, 18, 16, 16, 20, 22], direita=(1, 2, 3, 4, 5, 6))]
    hist += _leitura([('Pergunta com menor satisfação: %s (%s).' % (pior['texto'], _pct(pior['satisfacao']))) if pior else '',
                      'Há %d resposta(s) ainda sem revisão da gestão.' % sat['pendentes'] if sat['pendentes'] else 'Todas as respostas foram revisadas.'])
    return hist


def _secao_qualidade(d, rp):
    qd = d['qual']
    hist = [PageBreak(), _Secao(9, 'Gestão da qualidade', 'Problemas, ações, riscos e ocorrências'), Spacer(1, 7)]
    if not qd:
        return hist + [_p('Sem dados: as ferramentas da qualidade não estão disponíveis.')]
    probs, acoes, riscos, ocor = qd['problemas'], qd['acoes'], qd['riscos'], qd['ocorrencias']
    hist += [_p('A ONA avalia se a organização identifica problemas, investiga as causas e age para corrigi-los, no ciclo PDCA (Planejar, Fazer, Verificar e Agir). '
                'Esta seção mostra o que está registrado nas ferramentas da qualidade do sistema: problemas em análise, planos de ação, riscos mapeados e ocorrências.')]
    abertos = [p for p in probs if p['status'] != 'CONCLUÍDO' and p['status'] != 'ENCERRADO'] if probs else []
    atrasadas = [a for a in acoes if a['atrasada']]
    ativos = [r for r in riscos if r['status'] != 'ENCERRADO']
    hist += _cartoes([(str(len(probs)), 'problemas registrados (PDCA)'), (str(len(abertos)), 'em andamento'), (str(len(acoes)), 'ações no plano 5W2H'),
                      (str(len(atrasadas)), 'ações atrasadas'), (str(len(ativos)), 'riscos ativos'), (str(len(ocor)), 'ocorrências no período')])
    cont_a = Counter(a['status'] for a in acoes)
    cont_r = Counter(r['nivel'] for r in ativos)
    cont_o = Counter(o.get('tipo') or 'Sem tipo' for o in ocor)
    cont_p = Counter(p['status'] for p in probs)
    hist += [_sub('Plano de ação por situação'), _barras(sorted(cont_a.items(), key=lambda kv: -kv[1]), '#2f7a49')]
    hist += _como_ler('Cada barra é uma situação das ações do plano 5W2H (a fazer, em andamento, concluída). Muitas concluídas mostram que os problemas estão sendo resolvidos; '
                      'muitas paradas ou atrasadas pedem atenção da gestão.')
    hist += [_sub('Riscos ativos por nível'), _barras(sorted(cont_r.items(), key=lambda kv: -kv[1]), '#ef6c00')]
    hist += _como_ler('Cada barra conta os riscos mapeados em um nível (baixo a crítico), pela combinação de probabilidade e impacto. Os de nível alto e crítico devem ter ação de controle.')
    hist += [_sub('Ocorrências por tipo (no período)'), _barras(sorted(cont_o.items(), key=lambda kv: -kv[1]), '#c62828')]
    hist += _como_ler('Ocorrências são eventos que fugiram do esperado (falha, quase-falha, reclamação). Cada barra é um tipo. Registrar e tratar ocorrências é uma exigência da cultura de segurança.')
    hist += [_sub('Problemas por situação'), _barras(sorted(cont_p.items(), key=lambda kv: -kv[1]), '#1565c0')]
    hist += _como_ler('Cada barra é uma situação dos problemas abertos no PDCA, desde a análise até a conclusão.')
    hist += _leitura([('%d ação(ões) com prazo vencido.' % len(atrasadas)) if atrasadas else 'Nenhuma ação atrasada.',
                      ('Riscos de nível alto ou crítico ativos: %d.' % sum(v for k, v in cont_r.items() if str(k).lower() in ('alto', 'crítico', 'critico', 'muito alto'))) if cont_r else
                      'Nenhum risco ativo registrado.'])
    return hist


def _secao_seguranca(d, rp):
    seg = d['seg']
    hist = [PageBreak(), _Secao(10, 'Segurança do paciente e enfermagem', 'Carrinho de emergência, equipamentos, medicamentos e esterilização'), Spacer(1, 7)]
    if not seg:
        return hist + [_p('Sem dados: o módulo de Enfermagem e Segurança não está disponível.')]
    car, eq, rep, pac = seg['carrinhos'], seg['equipamentos'], seg['reposicao'], seg['pacotes']
    hist += [_p('A segurança do paciente é eixo central da acreditação. O sistema acompanha os itens que a enfermagem controla: carrinho de emergência (validades e quantidades), '
                'equipamentos (testes diários e manutenção), medicamentos que precisam de reposição e pacotes esterilizados. Os números abaixo mostram a situação <b>no momento da emissão</b> do relatório.')]
    car_ok = sum(1 for c in car if not c['vermelho'] and not c['atrasada'])
    eq_ok = sum(1 for e in eq if not e['vermelho'])
    pac_ok = sum(1 for p in pac if not p['vermelho'])
    def de(ok, tot):
        return '%d de %d' % (ok, tot) if tot else '—'

    hist += _cartoes([(de(car_ok, len(car)), 'carrinhos conferidos e sem problema'), (de(eq_ok, len(eq)), 'equipamentos em dia'),
                      (str(len(rep)), 'medicamentos aguardando reposição'), (de(pac_ok, len(pac)), 'pacotes esterilizados conformes')])
    linhas = [('Carrinhos de emergência', 100.0 * car_ok / len(car) if car else None, False), ('Equipamentos em dia', 100.0 * eq_ok / len(eq) if eq else None, False),
              ('Pacotes esterilizados conformes', 100.0 * pac_ok / len(pac) if pac else None, False)]
    hist += [_sub('Situação dos controles'), _barras_pct(linhas)]
    hist += _como_ler('Cada barra mostra o percentual de itens sem problema em cada controle: carrinhos sem item vencido ou faltando e conferidos no prazo, equipamentos com teste e manutenção em dia, '
                      'pacotes dentro da validade e com indicadores conformes. Verde é o esperado; vermelho pede ação imediata.')
    problemas = []
    for c in car:
        problemas += ['Carrinho %s: %s' % (c['nome'], p) for p in c['problemas'][:3]]
        if c['atrasada']:
            problemas.append('Carrinho %s: conferência atrasada' % c['nome'])
    problemas += ['Equipamento %s: manutenção vencida' % e['nome'] for e in eq if e['manutencao'] == 'vencido']
    problemas += ['Equipamento %s: teste diário pendente' % e['nome'] for e in eq if e['teste_atrasado']]
    hist += _leitura(problemas[:8] or ['Nenhuma pendência nos controles no momento da emissão.'])
    return hist


def _pedaco_validacao(rp):
    return [PageBreak(), _Secao(11, 'Validação e assinaturas', 'Quem elaborou, revisou e aprovou este dossiê'), Spacer(1, 7),
            _p('Para valer como documento de auditoria, este dossiê precisa ser conferido e assinado. Preencha os campos abaixo com nome, cargo, registro profissional e data.')] + rp.validacao_bloco() + [
        _sub('Anotações da auditoria'),
        Table([[''] for _ in range(7)], colWidths=[LARGURA], rowHeights=[9 * mm] * 7,
              style=TableStyle([('LINEBELOW', (0, 0), (-1, -1), .5, LINHA)]))]


# ------------------------------------------------------------------ montagem
def dossie_pdf(db, de, ate, clinica='', usuario='', versao=''):
    """Gera o PDF completo. `de` e `ate` são datas."""
    from . import versao as _versao
    clinica = clinica or 'Nucleleste'
    periodo = '%s a %s' % (util.data_br(de.isoformat()), util.data_br(ate.isoformat()))
    versao = versao or _versao()
    dados = coletar(db, de, ate)
    rp = RelatorioPDF('Dossiê ONA', clinica, periodo, validacao=validacao_padrao('Dossiê ONA - ' + periodo, usuario, versao=versao))
    buf = io.BytesIO()
    doc = _Doc(buf, clinica, periodo, title='Dossiê ONA - %s' % periodo, author=clinica, subject='Relatório para auditoria de acreditação (ONA)')
    agora = datetime.now()
    doc.gerado = agora
    sumario = TableOfContents()
    sumario.levelStyles = [ParagraphStyle('S0', fontName='Helvetica-Bold', fontSize=11, leading=19, textColor=VERDE, leftIndent=0, spaceBefore=3),
                           ParagraphStyle('S1', fontName='Helvetica', fontSize=9, leading=12.5, textColor=TEXTO, leftIndent=18)]
    sumario.dotsMinLevel = 0
    sumario_faixa = _Secao(0, 'Sumário', 'Índice do relatório com a página de cada assunto')
    historia = [NextPageTemplate('miolo')] + _info_capa(clinica, periodo, usuario, versao, agora) + [PageBreak(), sumario_faixa, Spacer(1, 10), sumario, PageBreak()]
    historia += _secao_apresentacao(dados, rp, de, ate, clinica)
    historia += _secao_resumo(dados, rp, de, ate) + _secao_indicadores(dados, rp) + _secao_producao(dados, rp) + _secao_epidemio(dados, rp)
    historia += _secao_agenda(dados, rp) + _secao_kpi(dados, rp) + _secao_satisfacao(dados, rp) + _secao_qualidade(dados, rp) + _secao_seguranca(dados, rp)
    historia += _pedaco_validacao(rp)
    historia += [NextPageTemplate('contra'), PageBreak(), _fim(clinica, agora)]
    doc.multiBuild(historia)
    return buf.getvalue()


def _fim(clinica, agora):
    cent = ParagraphStyle('fim', fontName='Helvetica', fontSize=12, leading=17, textColor=colors.white, alignment=1)
    peq = ParagraphStyle('fimp', fontName='Helvetica', fontSize=9, leading=13, textColor=colors.HexColor('#d4ecdd'), alignment=1)
    return KeepTogether([Paragraph('<b>%s</b>' % _esc(clinica), ParagraphStyle('fimn', parent=cent, fontSize=16, leading=20)), Spacer(1, 6),
                         Paragraph('Qualidade, segurança e melhoria contínua a serviço do paciente.', cent), Spacer(1, 16),
                         Paragraph('Documento gerado automaticamente pelo sistema Nucleleste em %s, às %s, com os dados registrados no próprio sistema. '
                                   'As definições dos indicadores devem ser conferidas com o manual da ONA vigente.' % (_data_ext(agora), agora.strftime('%H:%M')), peq)])
