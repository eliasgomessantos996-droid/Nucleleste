"""Apostila do sistema em PDF: guia de uso de todas as funcionalidades, com capa, "Como usar", "Primeiros passos", "Novidades
desta versão" (itens da versão mais recente de `novidades.VERSOES`), sumário com página, um capítulo por tema do menu e um bloco
por módulo e área. O conteúdo das áreas vem de `ajuda.base(db)`, então acompanha as edições feitas pela administração na NucleAI.
O visual segue o do dossiê ONA (verde Nucleleste), em A4 retrato.

O último PDF gerado fica em memória e só é refeito quando muda a versão, o nome da clínica, o conteúdo da ajuda ou as novidades.
"""
from __future__ import annotations

import hashlib
import io
import os
import re
import threading
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import (BaseDocTemplate, Flowable, Frame, NextPageTemplate, PageBreak, PageTemplate, Paragraph, Spacer, Table,
                                TableStyle)
from reportlab.platypus.tableofcontents import TableOfContents

from . import ajuda, novidades
from .ona_dossie import (AMARELO, ESCURO, H, LARGURA, LINHA, LOGO_CLARA, LOGO_ESCURA, M, MENTA, SUAVE, TEXTO, VERDE, VERDE2, W,
                         _data_ext, _esc)

# substituições para a fonte padrão (Helvetica, codificação cp1252)
MAPA_CARACTERES = {'→': '->', '⇔': '<->', '−': '-', '◀': '<', '▶': '>'}
PASSO = re.compile(r'^(\d+(?:\.\d+)*\.)\s+(.*)$')     # "1. texto" ou "2.1. texto"

EST = {
    'corpo': ParagraphStyle('apo_corpo', fontName='Helvetica', fontSize=10, leading=14.5, textColor=TEXTO, spaceAfter=3),
    'peq': ParagraphStyle('apo_peq', fontName='Helvetica', fontSize=9, leading=12.5, textColor=SUAVE, spaceAfter=6),
    'sub': ParagraphStyle('Sub', fontName='Helvetica-Bold', fontSize=13, leading=17, textColor=ESCURO, spaceBefore=14, spaceAfter=4,
                          keepWithNext=1),
    'area': ParagraphStyle('apo_area', fontName='Helvetica-Bold', fontSize=10.8, leading=14, textColor=VERDE, spaceBefore=8, spaceAfter=3,
                           keepWithNext=1),
    'item': ParagraphStyle('apo_item', fontName='Helvetica', fontSize=10, leading=14, textColor=TEXTO, leftIndent=14, bulletIndent=3,
                           spaceAfter=2),
    'passo': ParagraphStyle('apo_passo', fontName='Helvetica-Bold', fontSize=10, leading=14, textColor=VERDE),
    'sum0': ParagraphStyle('S0', fontName='Helvetica-Bold', fontSize=11, leading=19, textColor=VERDE, leftIndent=0, spaceBefore=3),
    'sum1': ParagraphStyle('S1', fontName='Helvetica', fontSize=9, leading=12.5, textColor=TEXTO, leftIndent=18),
}

# textos escritos para o guia (não vêm da ajuda da NucleAI)
COMO_USAR = [
    ('Organização', 'Esta apostila segue o menu lateral do sistema. Cada capítulo é um tema do menu, e cada módulo do tema tem o seu título.\n'
                    '• Os passos vêm numerados, na ordem em que devem ser feitos.\n'
                    '• As observações vêm em parágrafos, logo abaixo do passo a que se referem.\n'
                    '• O sumário traz a página de cada capítulo e de cada módulo.'),
    ('Como seguir um passo a passo', '1. Abra o tema no menu lateral.\n2. Clique no módulo que você precisa.\n'
                                     '3. Leia a parte da tela que você quer usar e siga os passos numerados.'),
    ('O que aparece para você', 'O sistema mostra apenas os módulos liberados para o seu perfil. A gerência ou a administração define o perfil '
                                'de cada pessoa. Se um item não aparece no menu, ele não está liberado para você: peça à gerência para verificar.'),
    ('Ajuda dentro do sistema', 'O botão redondo no canto da tela abre a NucleAI, a assistente de ajuda. Ela responde dúvidas com o passo a passo '
                                'da área, pergunta se resolveu e, se não resolver, pode avisar a gerência.'),
]

PRIMEIROS_PASSOS = [
    ('Acessar o sistema', '1. Abra o navegador (Chrome, Edge ou Firefox) em um computador da rede da clínica.\n'
                          '2. Digite o endereço do servidor da clínica com a porta 8080, por exemplo: endereço-do-servidor:8080.\n'
                          '3. A tela de entrada do sistema aparece.'),
    ('Entrar com usuário e senha', '1. Digite o seu usuário e a sua senha.\n2. Clique em Entrar.\n'
                                   '• Se a senha estiver errada, o sistema avisa e não libera a entrada.'),
    ('Trocar a senha provisória', 'Quando a administração cria o seu acesso, a senha é provisória. No primeiro acesso, o sistema pede uma '
                                  'senha nova antes de liberar as telas. Depois, você pode trocar a senha em Minha conta.'),
    ('Menu lateral e pesquisa', 'O menu lateral lista os temas e módulos liberados para você. Para encontrar uma tela pelo nome, pressione '
                                'a tecla / e digite parte do nome.'),
    ('Tema de cor e modo claro ou escuro', 'Em Minha conta, escolha a cor do sistema e o brilho (claro ou escuro). A escolha fica no seu perfil '
                                           'e vale em qualquer computador em que você entrar.'),
    ('Perfis e módulos liberados', 'Cada usuário tem um perfil, com os módulos que pode usar. A gerência e a administração definem esses '
                                   'módulos em Configuração > Usuários e perfis.'),
    ('Sair do sistema', 'Ao terminar, use Sair, principalmente em computadores compartilhados. Se você entrar em outro computador, a sessão '
                        'anterior é encerrada.'),
]

_CACHE = {'chave': None, 'pdf': None}
_TRAVA = threading.Lock()


# ------------------------------------------------------------------ texto
def _limpar(texto):
    """Troca os símbolos que a fonte Helvetica não tem e descarta o que não existe em cp1252 (ex.: emoji)."""
    for antigo, novo in MAPA_CARACTERES.items():
        texto = texto.replace(antigo, novo)
    return texto.encode('cp1252', errors='ignore').decode('cp1252')


def _passo(numero, texto):
    """Passo numerado: número em verde e negrito, texto ao lado, com recuo."""
    t = Table([[Paragraph('<b>%s</b>' % _esc(numero), EST['passo']), Paragraph(_esc(texto), EST['corpo'])]], colWidths=[40, LARGURA - 40])
    t.setStyle(TableStyle([('LEFTPADDING', (0, 0), (0, 0), 14), ('LEFTPADDING', (1, 0), (1, 0), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                           ('TOPPADDING', (0, 0), (-1, -1), 1.5), ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5), ('VALIGN', (0, 0), (-1, -1), 'TOP')]))
    t.hAlign = 'LEFT'
    return t


def _corpo(texto):
    """Linhas do texto da ajuda viram passos ("1.", "2.1."), marcadores ("•") ou parágrafos."""
    saida = []
    for linha in _limpar(texto).split('\n'):
        s = linha.strip()
        if not s:
            continue
        m = PASSO.match(s)
        if m:
            saida.append(_passo(m.group(1), m.group(2)))
        elif s.startswith('•'):
            saida.append(Paragraph(_esc(s.lstrip('•').strip()), EST['item'], bulletText='•'))
        else:
            saida.append(Paragraph(_esc(s), EST['corpo']))
    return saida


def _area(titulo, texto):
    """Título da área (verde, fica junto da primeira linha) e o texto formatado."""
    return [Paragraph(_esc(_limpar(titulo)), EST['area'])] + _corpo(texto)


def _secao_textos(lista):
    saida = []
    for titulo, texto in lista:
        saida += _area(titulo, texto)
    return saida


# ------------------------------------------------------------------ elementos
class _Faixa(Flowable):
    """Faixa verde que abre um capítulo ou uma parte do guia. Entra no sumário (se `toc_texto`) e no cabeçalho das páginas."""

    def __init__(self, rotulo, titulo, frase='', toc_texto=None):
        super().__init__()
        self.rotulo, self.titulo, self.frase = rotulo, titulo, frase
        self.cabecalho = ('%s · %s' % (rotulo, titulo)) if rotulo else titulo
        self.toc = (0, toc_texto) if toc_texto else None

    def wrap(self, aw, ah):
        return aw, 19 * mm

    def draw(self):
        c = self.canv
        c.saveState()
        caminho = c.beginPath()   # recorta o círculo decorativo dentro da faixa (sem invadir o cabeçalho)
        caminho.roundRect(0, 0, LARGURA, 17 * mm, 4 * mm)
        c.clipPath(caminho, stroke=0, fill=0)
        c.setFillColor(VERDE)
        c.rect(0, 0, LARGURA, 17 * mm, stroke=0, fill=1)
        c.setFillColor(VERDE2)
        c.setFillAlpha(.55)
        c.circle(LARGURA - 8 * mm, 17 * mm, 22 * mm, stroke=0, fill=1)
        c.setFillAlpha(1)
        x = 6 * mm
        if self.rotulo:
            w = stringWidth(self.rotulo, 'Helvetica-Bold', 8.5) + 10
            c.setFillColor(AMARELO)
            c.roundRect(x, 8.2 * mm, w, 4.8 * mm, 2.4 * mm, stroke=0, fill=1)
            c.setFillColor(ESCURO)
            c.setFont('Helvetica-Bold', 8.5)
            c.drawCentredString(x + w / 2.0, 9.5 * mm, self.rotulo)
            x += w + 4 * mm
        c.setFillColor(colors.white)
        c.setFont('Helvetica-Bold', 14)
        c.drawString(x, 9.4 * mm, self.titulo)
        if self.frase:
            c.setFont('Helvetica', 8.8)
            c.setFillColor(colors.HexColor('#d4ecdd'))
            c.drawString(x, 3.6 * mm, self.frase[:120])
        c.restoreState()


class _Doc(BaseDocTemplate):
    def __init__(self, buf, versao, clinica, data, **kw):
        super().__init__(buf, pagesize=A4, leftMargin=M, rightMargin=M, topMargin=24 * mm, bottomMargin=19 * mm, **kw)
        self.versao, self.clinica, self.data = versao, clinica, data
        quadro = Frame(M, 19 * mm, LARGURA, H - 43 * mm, id='quadro', leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        self.addPageTemplates([PageTemplate(id='capa', frames=[quadro], onPage=self._capa),
                               PageTemplate(id='miolo', frames=[Frame(M, 19 * mm, LARGURA, H - 43 * mm, id='corpo', leftPadding=0,
                                                                       rightPadding=0, topPadding=0, bottomPadding=0)], onPage=self._miolo),
                               PageTemplate(id='contra', frames=[Frame(M, 19 * mm, LARGURA, H - 43 * mm, id='contra', leftPadding=0,
                                                                        rightPadding=0, topPadding=0, bottomPadding=0)], onPage=self._contra)])
        self.seq = 0
        self._cap_prev = {}      # página -> cabeçalho, da passagem anterior (o sumário só fica certo na passagem seguinte)
        self._cap_atual = {}

    def handle_documentBegin(self):
        self.seq = 0
        self._cap_prev = self._cap_atual
        self._cap_atual = {}
        super().handle_documentBegin()

    def afterFlowable(self, f):
        if isinstance(f, _Faixa):
            self._cap_atual[self.page] = f.cabecalho
        toc = getattr(f, 'toc', None)
        if toc is None and getattr(f, 'toc_texto', None):
            toc = (1, f.toc_texto)
        if toc:
            nivel, texto = toc
            chave = 'm%d' % self.seq
            self.seq += 1
            self.canv.bookmarkPage(chave)
            self.canv.addOutlineEntry(texto, chave, level=nivel, closed=False)
            self.notify('TOCEntry', (nivel, _esc(texto), self.page, chave))

    def _cabecalho(self, pagina):
        anteriores = [p for p in self._cap_prev if p <= pagina]
        return self._cap_prev[max(anteriores)] if anteriores else ''

    def _logo(self, c, caminho, x, y, largura):
        if os.path.exists(caminho):
            c.drawImage(caminho, x, y, width=largura, height=largura * 0.396, mask='auto', preserveAspectRatio=True)

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
        c.restoreState()

    # --- capa
    def _capa(self, c, doc):
        c.saveState()
        self._fundo(c)
        self._logo(c, LOGO_CLARA, 14 * mm, H - 66 * mm, 118 * mm)
        c.setFillColor(AMARELO)
        c.rect(M, H - 104 * mm, 26 * mm, 2.2 * mm, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont('Helvetica-Bold', 34)
        c.drawString(M, H - 122 * mm, 'Apostila do Sistema')
        c.drawString(M, H - 137 * mm, 'Nucleleste')
        c.setFont('Helvetica', 15)
        c.setFillColor(MENTA)
        c.drawString(M, H - 151 * mm, 'Guia completo de uso de todas as funcionalidades')
        if self.clinica:
            c.setFont('Helvetica', 12)
            c.setFillColor(colors.HexColor('#d4ecdd'))
            c.drawString(M, H - 161 * mm, self.clinica)
        c.setFillColor(MENTA)
        c.rect(M, H - 170 * mm, LARGURA, .8 * mm, stroke=0, fill=1)
        # painel branco com a versão e a data
        c.setFillColor(colors.white)
        c.roundRect(M - 2 * mm, 14 * mm, LARGURA + 4 * mm, 66 * mm, 6 * mm, stroke=0, fill=1)
        c.setFillColor(AMARELO)
        c.rect(M + 4 * mm, 70 * mm, 22 * mm, 1.6 * mm, stroke=0, fill=1)
        c.setFillColor(ESCURO)
        c.setFont('Helvetica-Bold', 16)
        c.drawString(M + 4 * mm, 58 * mm, 'Versão %s' % self.versao)
        c.setFillColor(TEXTO)
        c.setFont('Helvetica', 11)
        c.drawString(M + 4 * mm, 46 * mm, 'Emitida em %s' % self.data)
        c.setFillColor(SUAVE)
        c.setFont('Helvetica', 9.5)
        c.drawString(M + 4 * mm, 30 * mm, 'Atualizada automaticamente quando a ajuda da NucleAI é editada.')
        c.restoreState()

    # --- miolo
    def _miolo(self, c, doc):
        c.saveState()
        self._logo(c, LOGO_ESCURA, M, H - 13 * mm, 30 * mm)
        c.setFillColor(SUAVE)
        c.setFont('Helvetica', 8.5)
        c.drawRightString(W - M, H - 9 * mm, self._cabecalho(doc.page))
        c.setStrokeColor(LINHA)
        c.setLineWidth(.6)
        c.line(M, H - 16 * mm, W - M, H - 16 * mm)
        c.line(M, 14 * mm, W - M, 14 * mm)
        c.setFont('Helvetica', 8)
        c.drawString(M, 9.2 * mm, 'Apostila do Sistema Nucleleste · versão %s' % self.versao)
        c.drawRightString(W - M, 9.2 * mm, 'página %d' % doc.page)
        c.restoreState()

    # --- contracapa
    def _contra(self, c, doc):
        c.saveState()
        self._fundo(c)
        self._logo(c, LOGO_CLARA, (W - 130 * mm) / 2.0, H - 155 * mm, 130 * mm)   # abaixo dos círculos decorativos
        c.setFillColor(AMARELO)
        c.rect((W - 24 * mm) / 2.0, H - 161 * mm, 24 * mm, 1.8 * mm, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont('Helvetica', 13)
        c.drawCentredString(W / 2.0, H - 181 * mm, 'Dúvidas no dia a dia: use a NucleAI dentro do sistema')
        c.drawCentredString(W / 2.0, H - 189 * mm, 'ou fale com a gerência.')
        c.restoreState()


# ------------------------------------------------------------------ montagem
def _montar(db, versao, clinica):
    B = ajuda.base(db)
    agora = datetime.now()
    buf = io.BytesIO()
    doc = _Doc(buf, versao, clinica, _data_ext(agora), title='Apostila do Sistema Nucleleste', author='Nucleleste',
               subject='Guia de uso de todas as funcionalidades do sistema')
    sumario = TableOfContents()
    sumario.levelStyles = [EST['sum0'], EST['sum1']]
    sumario.dotsMinLevel = 0

    historia = [NextPageTemplate('miolo'), Spacer(1, 1), PageBreak()]
    historia += [_Faixa('', 'Sumário', 'Página de cada capítulo e de cada módulo'), Spacer(1, 10), sumario]
    historia += [PageBreak(), _Faixa('GUIA', 'Como usar esta apostila', 'Organização e leitura da apostila', toc_texto='Como usar esta apostila')]
    historia += _secao_textos(COMO_USAR)
    historia += [PageBreak(), _Faixa('GUIA', 'Primeiros passos', 'Do primeiro acesso ao dia a dia', toc_texto='Primeiros passos')]
    historia += _secao_textos(PRIMEIROS_PASSOS)
    # novidades da versão mais recente do log (cada item: categoria, título, descrição, passos)
    historia += [PageBreak(), _Faixa('GUIA', 'Novidades desta versão', 'O que mudou na versão %s' % versao,
                                     toc_texto='Novidades desta versão')]
    for categoria, titulo, descricao, passos in novidades.VERSOES[0]['itens']:
        historia.append(Paragraph(_esc(_limpar('%s · %s' % (categoria, titulo))), EST['area']))
        historia += _corpo(descricao)
        historia += [Paragraph(_esc(_limpar(p)), EST['item'], bulletText='•') for p in passos]
    for n, (tema, mods) in enumerate(B.temas, 1):
        nomes = [m[0] for m in mods]
        areas = sum(len(a) for _m, a in mods)
        historia += [PageBreak(),
                     _Faixa('Capítulo %d' % n, _limpar(tema), '%d módulo(s) e %d área(s) explicados passo a passo' % (len(mods), areas),
                            toc_texto='%d. %s' % (n, _limpar(tema))),
                     Spacer(1, 8),
                     Paragraph('<b>Módulos deste capítulo:</b> ' + _esc(_limpar(' · '.join(nomes))), EST['peq'])]
        for modulo, lista in mods:
            titulo = Paragraph(_esc(_limpar(modulo)), EST['sub'])
            titulo.toc_texto = _limpar(modulo)
            historia.append(titulo)
            for area, texto in lista:
                historia += _area(area, texto)
    historia += [NextPageTemplate('contra'), PageBreak(), Spacer(1, 1)]
    doc.multiBuild(historia)
    return buf.getvalue()


def gerar_pdf(db, versao='', clinica=''):
    """Bytes do PDF da apostila. Reaproveita o último PDF enquanto a versão, a clínica e o conteúdo da ajuda não mudarem."""
    if not versao:
        from . import versao as _versao_do_sistema
        versao = _versao_do_sistema()
    sig = tuple(db.execute("SELECT COUNT(*), COALESCE(MAX(id),0), COALESCE(MAX(atualizado_em),''), COALESCE(SUM(LENGTH(texto)),0) "
                           "FROM ajuda_conteudo").fetchone())
    novos = hashlib.sha1(repr(novidades.VERSOES[0]).encode('utf-8')).hexdigest()   # muda quando o log de novidades muda
    chave = (versao, clinica or '', sig, novos)
    with _TRAVA:       # uma geração por vez: a segunda chamada espera e pega o PDF pronto
        if _CACHE['chave'] != chave:
            _CACHE['pdf'] = _montar(db, versao, clinica or '')
            _CACHE['chave'] = chave
        return _CACHE['pdf']
