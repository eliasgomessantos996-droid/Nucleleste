"""PDFs do controle de blindagens: planilha da devolução e documentos de transporte preenchidos.

Os documentos reproduzem os modelos Word da clínica (declaração para transporte, etiquetas ONU 2910, etiqueta do
destinatário, "material radioativo" e a declaração do expedidor), com os dados das blindagens selecionadas.
"""
from __future__ import annotations

import io
import os
from datetime import date

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, LETTER, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from . import util

# ---------------------------------------------------------------- dados fixos dos modelos
ENDERECO = 'Rua Ranulfo Álvares, nº 1620, Bairro Vila Isa, CEP 35.044-220, Governador Valadares, MG'
DESTINATARIO = ['Comissão Nacional de Energia Nuclear – CNEN/SP',
                'Instituto de Pesquisas Energéticas e Nucleares – IPEN',
                'Av. Prof. Lineu Prestes, 2242 – Butantã',
                'CEP: 05508-000 – São Paulo – SP',
                'CNPJ: 50.753.755/0001-35',
                'I.E.: 110.670.880-110']
TRANSPORTADOR = ['Eckert & Ziegler Brasil Comercial Ltda.',
                 'Rua Miguel Nelson Bechara, 480 – Jd. Pereira Leite, CEP: 02712-130, São Paulo – SP',
                 'CNPJ: 02.887.124/0003-28']

DOCUMENTOS = [
    # slug, título, como a quantidade é contada, padrão (função do nº de blindagens)
    ('declaracao_transporte', 'Declaração para transporte (não contribuintes)', 'vias', lambda n: 2),
    ('declaracao_expedidor', 'Declaração do expedidor de materiais radioativos (ONU – Classe 7)', 'vias', lambda n: 4),
    ('etiqueta_destinatario', 'Etiqueta do destinatário e remetente (um lote por etiqueta)', 'etiquetas', lambda n: n),
    ('etiqueta_2910', 'Etiqueta ONU 2910', 'etiquetas', lambda n: n),
    ('material_radioativo', 'Etiqueta “Material radioativo”', 'etiquetas', lambda n: n),
]
SLUGS = [d[0] for d in DOCUMENTOS]
TITULOS = {d[0]: d[1] for d in DOCUMENTOS}
UNIDADES = {d[0]: d[2] for d in DOCUMENTOS}
MAX_QTD = 200

# ---------------------------------------------------------------- fontes (as do Word, quando existirem no Windows)
_FONTES = {}


def _fonte(chave, arquivos, padrao):
    if chave in _FONTES:
        return _FONTES[chave]
    pasta = os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts')
    nome = padrao
    for arq in arquivos:
        caminho = os.path.join(pasta, arq)
        if os.path.exists(caminho):
            try:
                pdfmetrics.registerFont(TTFont(chave, caminho))
                nome = chave
                break
            except Exception:  # noqa: BLE001 - qualquer problema de fonte cai no padrão
                pass
    _FONTES[chave] = nome
    return nome


def fonte_preta():
    return _fonte('ArialBlack', ['ariblk.ttf'], 'Helvetica-Bold')


def fonte_tahoma():
    return _fonte('Tahoma', ['tahoma.ttf'], 'Helvetica')


# ---------------------------------------------------------------- utilidades
def _data_extenso(d):
    return '%d de %s de %d' % (d.day, util.MESES[d.month - 1], d.year)


def _cidade(ctx):
    return (ctx.get('cidade') or 'Governador Valadares').split(' - ')[0].strip()


def montar_contexto(itens, empresa, cidade, cnpj, valor_unitario, quando=None):
    """`itens`: linhas de blindagens da solicitação."""
    n = len(itens)
    return {'itens': [dict(i) for i in itens], 'n': n, 'lotes': [i['lote'] for i in itens], 'empresa': empresa or '',
            'cidade': cidade, 'cnpj': cnpj or '', 'valor_unitario': valor_unitario or 0.0,
            'valor_total': round((valor_unitario or 0.0) * n, 2), 'data': quando or date.today()}


def _estilo(nome, **kw):
    base = dict(fontName='Helvetica', fontSize=11, leading=14, alignment=TA_LEFT)
    base.update(kw)
    return ParagraphStyle(nome, **base)


def _escapar(t):
    return str(t).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _desenhar_paragrafo(c, p, x, y_topo, largura):
    """Desenha um Paragraph com o topo em y_topo; devolve o y logo abaixo dele."""
    w, h = p.wrap(largura, 10000)
    p.drawOn(c, x, y_topo - h)
    return y_topo - h


# ---------------------------------------------------------------- 1) declaração para transporte
def _declaracao_transporte(c, ctx):
    c.setPageSize(A4)
    larg, alt = A4
    ml, mr, mt = 20 * mm, 15 * mm, 18 * mm
    cw = larg - ml - mr
    tn = 'Times-Roman'
    tb = 'Times-Bold'
    corpo = _estilo('c', fontName=tn, fontSize=12, leading=14.4)
    just = _estilo('j', fontName=tn, fontSize=12, leading=14.4, alignment=TA_JUSTIFY, firstLineIndent=1.25 * cm)
    y = alt - mt
    c.setFont(tb, 13)
    for linha, sublinhado in (('DECLARAÇÃO PARA TRANSPORTE', True), ('(não contribuintes)', False)):
        if sublinhado:
            c.setFont(tb, 13)
        else:
            c.setFont(tn, 13)
        c.drawCentredString(ml + cw / 2, y - 13, linha)
        if sublinhado:
            tw = c.stringWidth(linha, tb, 13)
            c.line(ml + cw / 2 - tw / 2, y - 15, ml + cw / 2 + tw / 2, y - 15)
        y -= 17
    y -= 12
    texto = ('Declaramos para fins e efeitos, legais e fiscais, que %s, CNPJ: %s, estabelecido no endereço %s, '
             'por se tratar de empresa exclusivamente prestadora de serviços, não é contribuinte de ICMS, estando '
             'consequentemente dispensada da emissão de nota fiscal para a remessa das mercadorias abaixo descritas:'
             % (_escapar(ctx['empresa']), _escapar(ctx['cnpj']), _escapar(ENDERECO)))
    y = _desenhar_paragrafo(c, Paragraph(texto, just), ml, y, cw) - 14

    def rotulo(titulo, sublinhado=True):
        nonlocal y
        t = '<b><u>%s</u></b>' % _escapar(titulo) if sublinhado else '<b>%s</b>' % _escapar(titulo)
        return t

    def linha(html, espaco=0):
        nonlocal y
        y = _desenhar_paragrafo(c, Paragraph(html, corpo), ml, y, cw) - espaco

    linha(rotulo('Destinatário') + ':')
    for d in DESTINATARIO:
        linha(_escapar(d))
    y -= 14
    linha(rotulo('Descrição Completa do Material') + ': Blindagem de Gerador de Tecnécio', 14)
    linha('<b>Quantidade de Vols:</b> %02d' % ctx['n'], 14)
    linha('<b>Número dos lotes:</b> %s' % _escapar(' / '.join(ctx['lotes'])), 14)
    n = ctx['n']
    sufixo = 'considerando %s' % ('1 blindagem' if n == 1 else '%d blindagens' % n)
    linha('<b>Valor da mercadoria:</b> R$ %s cada volume. Valor total R$ %s (%s)'
          % (util.moeda(ctx['valor_unitario']), util.moeda(ctx['valor_total']), sufixo), 20)
    linha(rotulo('Dados do Transportador', False) + ':')
    for t in TRANSPORTADOR:
        linha(_escapar(t))
    y -= 22
    linha('<b>MATERIAL RADIOATIVO, VOLUME EXCEPTIVO, QUANTIDADE LIMITADA DE MATERIAL, CLASSE 7, UN 2910.</b>')
    y = _desenhar_paragrafo(c, Paragraph(
        'Declaro que o conteúdo deste embarque está correto e plenamente de acordo com o nome do produto, sua classificação; '
        'embalado, marcado e sinalizado em todos os aspectos. Encontra-se em condições apropriadas para o transporte, conforme '
        'os regulamentos para produtos perigosos, regulamentações do transportador e as leis nacionais e internacionais '
        'pertinentes ou regulamentações governamentais.', just), ml, y, cw) - 26
    c.setFont(tn, 12)
    c.drawRightString(larg - mr, y - 12, '%s, %s' % (_cidade(ctx), _data_extenso(ctx['data'])))
    y -= 80
    c.line(ml + cw / 2 - 4.2 * cm, y, ml + cw / 2 + 4.2 * cm, y)
    c.drawCentredString(ml + cw / 2, y - 15, 'Supervisor Técnico de Medicina Nuclear')
    c.showPage()


# ---------------------------------------------------------------- 2) declaração do expedidor (formulário CNEN)
def _caixa(txt, marcado=False):
    return ('[X] ' if marcado else '[  ] ') + txt


def _declaracao_expedidor(c, ctx):
    pg = landscape(A4)
    c.setPageSize(pg)
    larg, alt = pg
    m = 12 * mm
    cw = larg - 2 * m
    p = _estilo('f', fontSize=8.8, leading=10.8)
    pb = _estilo('fb', fontSize=9, leading=11, fontName='Helvetica-Bold')
    pc = _estilo('fc', fontSize=8.8, leading=10.8, alignment=TA_CENTER)
    pcb = _estilo('fcb', fontSize=10.5, leading=13, alignment=TA_CENTER, fontName='Helvetica-Bold')
    pj = _estilo('fj', fontSize=8.8, leading=10.8, alignment=TA_JUSTIFY)

    def P(t, e=p):
        return Paragraph(t, e)

    n = ctx['n']
    lotes = '/ '.join(ctx['lotes'])
    cab_estilo = [('GRID', (0, 0), (-1, -1), .6, colors.black), ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                  ('LEFTPADDING', (0, 0), (-1, -1), 3), ('RIGHTPADDING', (0, 0), (-1, -1), 3),
                  ('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2)]
    blocos = []

    # título
    t = Table([[P('DECLARAÇÃO DO EXPEDIDOR DE MATERIAIS RADIOATIVOS (ONU - CLASSE 7)', pcb)]], colWidths=[cw])
    t.setStyle(TableStyle(cab_estilo + [('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#e8e8e8'))]))
    blocos.append(t)
    t = Table([[P('ESTA REMESSA ESTÁ DENTRO DAS LIMITAÇÕES PRESCRITAS PARA:', pb)],
               [P(_caixa('VEÍCULO DE PASSAGEIRO E CARGA') + '&nbsp;' * 40 + _caixa('VEÍCULO APENAS DE CARGA'), p)]], colWidths=[cw])
    t.setStyle(TableStyle(cab_estilo))
    blocos.append(t)

    # natureza e atividade máxima do conteúdo
    c1 = [0.17, 0.15, 0.2, 0.08, 0.1, 0.12, 0.08, 0.1]
    cws = [cw * x for x in c1]
    forma = '<br/>'.join(_caixa(x) for x in ['BAE - I', 'BAE - II', 'BAE - III', 'OCS - I', 'OCS - II', 'OUTRAS FORMAS'])
    categoria = '<br/>'.join(_caixa(x) for x in ['I - BRANCO', 'II - AMARELO', 'III - AMARELO', 'III - AMARELO SOB USO EXCLUSIVO', 'ISENTO'])
    tipo = '<br/>'.join(_caixa(x, x == 'EXCEPTIVO') for x in ['EXCEPTIVO', 'EI - I', 'EI - II', 'EI - III', 'TIPO A', 'TIPO B (U)',
                                                              'TIPO B (M)', 'ARRANJO ESPECIAL'])
    dados = [
        [P('NATUREZA E ATIVIDADE MÁXIMA DO CONTEÚDO', pb), '', '', '', P('EMBALADO', pb), '', '', ''],
        [P('RADIONUCLÍDEO', pb), P('FORMA', pb), P('ATIVIDADE', pb), P('NÚMERO DE EMBALADOS', pb), P('CATEGORIA', pb),
         P('ÍNDICE TRANSP.', pb), P('TIPO', pb), P('NÚMERO ONU', pb)],
        [P('NOME OU SÍMBOLO DO PRINCIPAL CONTEÚDO RADIOATIVO<br/><br/><b>Mo-99/Tc-99m</b>'),
         P('SOB FORMA ESPECIAL<br/>' + forma + '<br/><br/>FORMA QUÍMICA E ESTADO FÍSICO (GASOSO, LÍQUIDO OU SÓLIDO)<br/><b>Sólido</b>'),
         P('EM BECQUEREL<br/><br/><b>&lt; 15 MBq</b>'), P('<b>%d</b>' % n, pc), P(categoria),
         P('<b>NA</b><br/><br/>APENAS PARA CATEGORIAS DE RÓTULO AMARELO'), P(tipo), P('<b>2910</b>', pc)],
    ]
    t = Table(dados, colWidths=cws)
    t.setStyle(TableStyle(cab_estilo + [('SPAN', (0, 0), (3, 0)), ('SPAN', (4, 0), (7, 0))]))
    blocos.append(t)

    # certificados
    certs = ['- CERTIFICADO P/ MATERIAIS SOB FORMA ESPECIAL', '- CERTIFICADO DE APROVAÇÃO DE PROJETO DE EMBALADO',
             '- CERTIFICADO DE APROVAÇÃO NORMAL DE TRANSPORTE', '- CERTIFICADO DE APROVAÇÃO ESPECIAL DE TRANSPORTE']
    linhas_marca = _escapar(lotes) + '<br/>' + '<br/>'.join('_' * 62 for _ in range(3))
    t = Table([[P('CERTIFICADOS ADICIONAIS OBTIDOS PELO EXPEDIDOR', pb), P('MARCA E IDENTIFICAÇÃO DA AUT. COMP. (PAÍS / Nº / COD.)', pb)],
               [P('<br/>'.join(certs)), P(linhas_marca)],
               [P(_caixa('MATERIAL FÍSSIL')), P(_caixa('MATERIAL NÃO FÍSSIL', True))]],
              colWidths=[cw * .5, cw * .5])
    t.setStyle(TableStyle(cab_estilo))
    blocos.append(t)
    t = Table([[P('<b>INFORMAÇÕES ESPECIAIS DE MANUSEIO:</b> &nbsp;&nbsp;&nbsp;NA')]], colWidths=[cw])
    t.setStyle(TableStyle(cab_estilo))
    blocos.append(t)

    # declarações
    t = Table([[P('Declaração conforme requisito CNEN: "Atesto que os itens e materiais contidos nesta expedição, estão precisa e '
                  'completamente descritos acima pelos respectivos nomes para transporte, bem como devidamente classificados, '
                  'acondicionados, marcados e rotulados, encontrando-se, sob todos aspectos, em condições apropriadas para transporte '
                  'por via ( <b>terrestre</b> / aérea / aquaviária) de acordo com os regulamentos e normas governamentais nacionais e '
                  'internacionais aplicáveis."', pj)],
               [P('Declaração conforme requisito ANTT: "Declaro que os produtos perigosos estão adequadamente classificados, embalados, '
                  'identificados, e estivados para suportar os riscos das operações de transporte e que atendem às exigências da '
                  'regulamentação"', pj)]], colWidths=[cw])
    t.setStyle(TableStyle(cab_estilo))
    blocos.append(t)

    # expedidor / assinatura
    t = Table([
        [P('NOME E ENDEREÇO COMPLETO DO EXPEDIDOR', pb), P('NOME E TÍTULO DA PESSOA QUE ASSINA A DECLARAÇÃO', pb)],
        [P('<b>%s</b><br/>%s' % (_escapar(ctx['empresa'].replace(' LTDA.', ' LTDA')), _escapar(ENDERECO))),
         P('Dr. Einstein Aldrin Arruda Pereira<br/>Médico Nuclear')],
        [P('DATA: <b>%02d de %s de %d</b>' % (ctx['data'].day, util.MESES[ctx['data'].month - 1].upper(), ctx['data'].year)),
         P('ASSINATURA:<br/><br/><br/>')],
        [P('LOCAL DE EMBARQUE: <b>%s/MG</b>' % _escapar(_cidade(ctx))),
         P('DESTINO: <b>Instituto de Pesquisas Energéticas e Nucleares - IPEN</b><br/>Av. Prof. Lineu Prestes, 2242 - Cidade '
           'Universitária - Butantã - São Paulo - SP')],
    ], colWidths=[cw * .5, cw * .5])
    t.setStyle(TableStyle(cab_estilo))
    blocos.append(t)
    t = Table([[P('OBS.: A INOBSERVÂNCIA DOS PRECEITOS CONTIDOS NA NORMA CNEN - NE - 5.01, BEM COMO EM DEMAIS REGULAMENTAÇÕES '
                  'PERTINENTES AO TRANSPORTE DE PRODUTOS PERIGOSOS, SUJEITA O INFRATOR A PENALIDADES LEGAIS APLICÁVEIS. ESTA '
                  'DECLARAÇÃO SÓ TERÁ VALIDADE SE ASSINADA PELO EXPEDIDOR DA CARGA NO PAÍS.', pb)]], colWidths=[cw])
    t.setStyle(TableStyle(cab_estilo))
    blocos.append(t)

    y = alt - m
    for b in blocos:
        w, h = b.wrap(cw, alt)
        b.drawOn(c, m, y - h)
        y -= h
    c.setFont('Helvetica', 8.5)
    c.drawString(m, m + 4, '1ª via - Expedidor      2ª via - CNEN      3ª via - Transportador      4ª via - Destinatário.')
    c.drawRightString(larg - m, m + 4, 'FM-SPR-02-1_Rev01')
    c.showPage()

    # página 2: medidas de emergência
    c.setPageSize(pg)
    g = _estilo('g', fontSize=10.5, leading=14)
    gb = _estilo('gb', fontSize=11, leading=14, fontName='Helvetica-Bold')
    blocos = []
    medidas = ['Em caso de emergência estacione, se possível, em área vazia, avise o Supervisor de Proteção Radiológica '
               'LUCAS ROMERO GALVÃO no telefone de emergência nº 14 - 998421995.', '',
               'Usar Equipamento de Proteção Individual', 'Isolar a área, afastando curiosos', 'Sinalizar o local do acidente',
               'Eliminar ou manter afastadas todas as fontes de ignição',
               'Avisar imediatamente ao responsável pela operação de transporte, ao expedidor do produto, ao corpo de bombeiros '
               '(193) e a polícia (190)', 'Avisar imediatamente aos órgãos ou entidades de trânsito']
    t = Table([[Paragraph('MEDIDAS DE EMERGÊNCIA APROPRIADAS À EXPEDIÇÃO', gb)],
               [Paragraph('<br/>'.join(_escapar(x) for x in medidas), g)],
               [Paragraph('AÇÕES EM CASO DE ACIDENTE', gb)]], colWidths=[cw])
    t.setStyle(TableStyle([('BOX', (0, 0), (-1, -1), .6, colors.black), ('LINEBELOW', (0, 0), (-1, 0), .6, colors.black),
                           ('LEFTPADDING', (0, 0), (-1, -1), 5), ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                           ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e8e8e8')), ('BACKGROUND', (0, 2), (-1, 2), colors.HexColor('#e8e8e8'))]))
    blocos.append(t)
    acoes = [('VAZAMENTO', 'Isolar e sinalizar imediatamente a área afetada, manter afastadas as pessoas não autorizadas.<br/>'
                           'Entrar na área de isolamento somente para salvar vidas ou combater incêndio; limitar a permanência ao mínimo indispensável.'),
             ('FOGO', 'A presença de material radioativo não altera a eficácia das técnicas de controle de incêndios.<br/>'
                      'Incêndios devem ser combatidos com procedimentos padrões. Não mover os embalados.'),
             ('POLUIÇÃO', 'Risco de contaminação radioativa em caso de perda de contenção. Isolar a área afetada.'),
             ('ENVOLVIMENTO DE PESSOAS', 'Manter espectadores afastados no mínimo 50 m.<br/>'
                                         'Solicitar atendimento médico de emergência, ministrar primeiros socorros de acordo com a natureza dos ferimentos.')]
    t = Table([[Paragraph('<b>%s</b>' % a, g), Paragraph(b, g)] for a, b in acoes], colWidths=[cw * .17, cw * .83])
    t.setStyle(TableStyle([('GRID', (0, 0), (-1, -1), .6, colors.black), ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                           ('LEFTPADDING', (0, 0), (-1, -1), 5), ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4)]))
    blocos.append(t)
    y = alt - m
    for b in blocos:
        w, h = b.wrap(cw, alt)
        b.drawOn(c, m, y - h)
        y -= h
    c.showPage()


# ---------------------------------------------------------------- 3) etiqueta do destinatário/remetente (2 por folha)
def _etiqueta_destinatario(c, ctx, itens):
    """`itens`: lotes, um por etiqueta; duas etiquetas por folha carta."""
    larg, alt = LETTER
    ml = 72
    cw = larg - 2 * ml
    corpo = _estilo('e', fontSize=11, leading=14.5)
    for ini in range(0, len(itens), 2):
        c.setPageSize(LETTER)
        for pos, lote in enumerate(itens[ini:ini + 2]):
            y = alt - 36 - pos * (alt / 2 - 8)
            y = _desenhar_paragrafo(c, Paragraph('<b><u>Destinatário</u></b>:', corpo), ml, y, cw)
            for d in DESTINATARIO:
                y = _desenhar_paragrafo(c, Paragraph(_escapar(d), corpo), ml, y, cw)
            y -= 16
            y = _desenhar_paragrafo(c, Paragraph('<b><u>Remetente</u></b>:', _estilo('r', fontSize=11, leading=14)), ml, y, cw)
            y = _desenhar_paragrafo(c, Paragraph(_escapar(ctx['empresa'].rstrip('.') + '.'), _estilo('r1', fontSize=16, leading=20)), ml, y, cw)
            y = _desenhar_paragrafo(c, Paragraph(_escapar(ENDERECO), _estilo('r2', fontSize=18, leading=22)), ml, y, cw)
            y = _desenhar_paragrafo(c, Paragraph('CNPJ: ' + _escapar(ctx['cnpj']), _estilo('r3', fontSize=16, leading=20)), ml, y, cw)
            y -= 14
            _desenhar_paragrafo(c, Paragraph('<b>Número dos lotes:</b> <font size="14">%s</font>' % _escapar(lote),
                                             _estilo('r4', fontSize=12, leading=18)), ml, y, cw)
        c.setStrokeColor(colors.HexColor('#999999'))
        c.setDash(4, 4)
        c.line(36, alt / 2 - 4, larg - 36, alt / 2 - 4)
        c.setDash()
        c.setStrokeColor(colors.black)
        c.showPage()


# ---------------------------------------------------------------- 4) etiqueta ONU 2910 (2 por folha)
def _etiqueta_2910(c, ctx, quantidade):
    larg, alt = LETTER
    fonte = fonte_tahoma()
    for ini in range(0, quantidade, 2):
        c.setPageSize(LETTER)
        for pos in range(min(2, quantidade - ini)):
            c.setFont(fonte, 72)
            c.drawCentredString(larg / 2, alt * (0.74 if pos == 0 else 0.26) - 24, 'ONU 2910')
        c.setStrokeColor(colors.HexColor('#999999'))
        c.setDash(4, 4)
        c.line(36, alt / 2, larg - 36, alt / 2)
        c.setDash()
        c.setStrokeColor(colors.black)
        c.showPage()


# ---------------------------------------------------------------- 5) etiqueta "MATERIAL RADIOATIVO" (3 por folha)
def _material_radioativo(c, ctx, quantidade):
    larg, alt = A4
    fonte = fonte_preta()
    for ini in range(0, quantidade, 3):
        c.setPageSize(A4)
        for pos in range(min(3, quantidade - ini)):
            centro = alt * (0.835 - pos * 0.335)
            c.setFont(fonte, 48)
            for k, linha in enumerate(('MATERIAL', 'RADIOATIVO')):
                c.drawCentredString(larg / 2, centro + 14 - k * 58, linha)
        c.setStrokeColor(colors.HexColor('#999999'))
        c.setDash(4, 4)
        for f in (0.665, 0.33):
            c.line(36, alt * f, larg - 36, alt * f)
        c.setDash()
        c.setStrokeColor(colors.black)
        c.showPage()


# ---------------------------------------------------------------- montagem
def normalizar_quantidades(ctx, pedido=None):
    """{slug: quantidade} com os padrões do modelo; `pedido` (slug -> texto) sobrescreve. 0 = não imprimir."""
    qtd = {slug: padrao(ctx['n']) for slug, _t, _u, padrao in DOCUMENTOS}
    for slug, bruto in (pedido or {}).items():
        if slug in qtd and str(bruto).strip().isdigit():
            qtd[slug] = max(0, min(MAX_QTD, int(bruto)))
    return qtd


def gerar_documentos(ctx, quantidades):
    """PDF com os documentos pedidos (na ordem do cadastro), cada um na quantidade informada."""
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=A4)
    c.setTitle('Documentos de devolução de blindagens')
    c.setAuthor(ctx['empresa'])
    total = 0
    for slug, _t, _u, _p in DOCUMENTOS:
        q = int(quantidades.get(slug, 0))
        if q <= 0:
            continue
        total += q
        if slug == 'declaracao_transporte':
            for _ in range(q):
                _declaracao_transporte(c, ctx)
        elif slug == 'declaracao_expedidor':
            for _ in range(q):
                _declaracao_expedidor(c, ctx)
        elif slug == 'etiqueta_destinatario':
            lotes = ctx['lotes'] or ['']
            _etiqueta_destinatario(c, ctx, [lotes[i % len(lotes)] for i in range(q)])
        elif slug == 'etiqueta_2910':
            _etiqueta_2910(c, ctx, q)
        elif slug == 'material_radioativo':
            _material_radioativo(c, ctx, q)
    if not total:
        c.setPageSize(A4)
        c.setFont('Helvetica', 12)
        c.drawString(72, 700, 'Nenhum documento selecionado.')
        c.showPage()
    c.save()
    return buf.getvalue()


# ---------------------------------------------------------------- planilha (PDF e Excel)
COLUNAS = [('Item', 'item'), ('Lote', 'lote'), ('Nota fiscal', 'nota_fiscal'), ('Série', 'serie'),
           ('Data da nota fiscal', 'data_nota'), ('CFOP', 'cfop'), ('Validade', 'validade')]


def _linhas_planilha(ctx):
    return [[str(i), b['lote'], b['nota_fiscal'], b['serie'], util.data_br(b['data_nota']), b['cfop'], util.data_br(b['validade'])]
            for i, b in enumerate(ctx['itens'], 1)]


def planilha_pdf(ctx, numero):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
                            title='Planilha de devolução de blindagens', author=ctx['empresa'])
    titulo = _estilo('t', fontName='Helvetica-Bold', fontSize=16, leading=20)
    sub = _estilo('s', fontSize=10, leading=14, textColor=colors.HexColor('#444444'))
    cel = _estilo('c', fontSize=10.5, leading=13)
    cab = _estilo('h', fontSize=10, leading=12, fontName='Helvetica-Bold', textColor=colors.white)
    dados = [[Paragraph(n, cab) for n, _ in COLUNAS]] + [[Paragraph(_escapar(v), cel) for v in lin] for lin in _linhas_planilha(ctx)]
    t = Table(dados, repeatRows=1, colWidths=[1.4 * cm, 5.2 * cm, 3.8 * cm, 2.6 * cm, 4.2 * cm, 2.6 * cm, 3.8 * cm])
    t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#255f39')), ('GRID', (0, 0), (-1, -1), .5, colors.HexColor('#9aa8a0')),
                           ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f1f6f3')]),
                           ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5)]))
    historia = [Paragraph('Devolução de blindagens de gerador de tecnécio', titulo),
                Paragraph('%s · CNPJ %s' % (_escapar(ctx['empresa']), _escapar(ctx['cnpj'])), sub),
                Paragraph('Solicitação nº %s · %s · %d blindagem(ns)' % (numero, util.data_br(ctx['data']), ctx['n']), sub),
                Spacer(1, 12), t]

    def rodape(c, d):
        c.setFont('Helvetica', 8)
        c.setFillColor(colors.HexColor('#666666'))
        c.drawRightString(landscape(A4)[0] - 18 * mm, 9 * mm, 'Página %d' % d.page)

    doc.build(historia, onFirstPage=rodape, onLaterPages=rodape)
    return buf.getvalue()


def planilha_xlsx(ctx, numero):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    wb = Workbook()
    ws = wb.active
    ws.title = 'Devolução'
    ws.append(['Devolução de blindagens de gerador de tecnécio'])
    ws.append([ctx['empresa'] + ' · CNPJ ' + ctx['cnpj']])
    ws.append(['Solicitação nº %s · %s · %d blindagem(ns)' % (numero, util.data_br(ctx['data']), ctx['n'])])
    ws.append([])
    ws.append([n for n, _ in COLUNAS])
    borda = Side(style='thin', color='9AA8A0')
    for col in range(1, len(COLUNAS) + 1):
        c = ws.cell(row=5, column=col)
        c.font = Font(bold=True, color='FFFFFF')
        c.fill = PatternFill('solid', fgColor='255F39')
        c.alignment = Alignment(horizontal='center')
        c.border = Border(left=borda, right=borda, top=borda, bottom=borda)
    for lin in _linhas_planilha(ctx):
        ws.append(lin)
    for r in range(6, 6 + ctx['n']):
        for col in range(1, len(COLUNAS) + 1):
            ws.cell(row=r, column=col).border = Border(left=borda, right=borda, top=borda, bottom=borda)
    ws['A1'].font = Font(bold=True, size=14)
    for letra, larg in zip('ABCDEFG', (7, 18, 14, 9, 20, 10, 14)):
        ws.column_dimensions[letra].width = larg
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
