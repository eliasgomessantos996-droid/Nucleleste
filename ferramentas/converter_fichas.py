"""
Converte as abas de impressão da planilha original (VERSÃO 2.1 RECEPÇÃO1.xlsm)
em modelos HTML (Jinja2) usados pelo sistema para imprimir as fichas.

O layout (larguras, alturas, mesclagens, fontes, bordas, cores, imagens e
caixas de texto) é reproduzido a partir do próprio arquivo Excel. As células
que a planilha preenchia via VBA (ou que referenciavam 'FICHA GERAL' /
'FICHA MIBI') viram campos dinâmicos: {{ f.nome }}, {{ f.cpf }}, etc.

Uso (rodar uma vez, ou sempre que o layout de uma ficha mudar no Excel):
    python ferramentas/converter_fichas.py "caminho/da/planilha.xlsm"

Requer: openpyxl
"""
import colorsys
import datetime as dt
import html
import json
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

import openpyxl
from openpyxl.utils import column_index_from_string, get_column_letter, range_boundaries

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_TPL = os.path.join(BASE, 'app', 'templates', 'fichas')
OUT_IMG = os.path.join(BASE, 'app', 'static', 'fichas')

NS = {
    'xdr': 'http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing',
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'rel': 'http://schemas.openxmlformats.org/package/2006/relationships',
    'm': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
}
EMU_PX = 9525  # 1 px (96 dpi) = 9525 EMU

# ---------------------------------------------------------------------------
# Campos dinâmicos
# ---------------------------------------------------------------------------
# Células das fichas-base que o VBA preenchia. As outras abas referenciam estas
# células por fórmula, então resolvemos as fórmulas para os mesmos campos.
FICHA_GERAL = {
    'B5': 'titulo', 'F10': 'data', 'B12': 'nome', 'I12': 'id_cliente',
    'B14': 'nascimento', 'H14': 'profissao', 'E16': 'cpf', 'B18': 'idade',
    'B19': 'mae', 'B21': 'endereco', 'B23': 'bairro', 'F23': 'cidade',
    'B25': 'cep', 'D25': 'contato', 'B27': 'convenio', 'F29': 'cartao',
    'B29': 'exame', 'C31': 'medico', 'D33': 'exame_anterior',
}
FICHA_MIBI = {
    'F10': 'data', 'B12': 'nome', 'I12': 'id_cliente', 'B14': 'nascimento',
    'G14': 'profissao', 'E16': 'cpf', 'B18': 'idade', 'B20': 'mae',
    'B22': 'endereco', 'B24': 'bairro', 'F24': 'cidade', 'B26': 'cep',
    'D26': 'contato', 'B28': 'convenio', 'F28': 'cartao', 'B30': 'exame',
    'C32': 'medico', 'D34': 'exame_anterior',
}
REFS = {'FICHA GERAL': FICHA_GERAL, 'FICHA MIBI': FICHA_MIBI}

SIM_NAO = '(  ) SIM  (  ) NÃO'

# slug, título, campos específicos da aba (célula -> expressão Jinja ou None p/ limpar)
SHEETS = [
    ('FICHA GERAL', 'ficha_geral', 'Ficha Geral', dict(FICHA_GERAL)),
    ('FICHA MIBI', 'ficha_mibi', 'Ficha MIBI', dict(FICHA_MIBI)),
    ('PNT-MIBI', 'pnt_mibi', 'PNT - MIBI', {'A31': 'data'}),
    ('PNT-ÓSSEA', 'pnt_ossea', 'PNT - Óssea', {'D4': 'mae'}),
    ('PNT-RENAL', 'pnt_renal', 'PNT - Renal', {'A31': 'data'}),
    ('PNT-LINFONODO', 'pnt_linfonodo', 'PNT - Linfonodo', {
        'A30': 'data', 'D3': 'mae',
        'E5': "f.r1 or '   " + SIM_NAO + "'", 'E7': "f.r2 or '" + SIM_NAO + "'",
        'E9': "f.r3 or '" + SIM_NAO + "'", 'E11': "f.r4 or '" + SIM_NAO + "'",
    }),
    ('PNT- PULMONAR', 'pnt_pulmonar', 'PNT - Pulmonar', {}),
    ('PNT- SPECT', 'pnt_spect', 'PNT - SPECT Cerebral', {}),
    ('PNT-TGI', 'pnt_tgi', 'PNT - Tireoide', {}),
    ('PNT- PARATGI', 'pnt_paratgi', 'PNT - Paratireoide', {}),
    ('SAE (TODOS EXAMES)', 'sae_geral', 'SAE (todos os exames)', {'D2': 'id_cliente'}),
    ('SAE MIBI', 'sae_mibi', 'SAE MIBI', {}),
    ('TERMO DR HAROLDO', 'termo_haroldo', 'Termo de consentimento (MIBI)', {}),
    ('DR. HAROLDO', 'dr_haroldo', 'Orientação Dr. Haroldo (MIBI)', {'C8': 'medicamentos', 'B16': 'data'}),
    ('ESCORE NEWS (MIBI & PULMONAR)', 'escore_news', 'Escore NEWS', {}),
    ('FICHACLIENTEGERAL', 'etiqueta_cliente', 'Etiqueta do cliente', {}),
    ('FICHAAGENDAMENTO', 'ficha_agendamento', 'Ficha de agendamento (medicamentos)', {
        'B2': 'medicamento', 'B5': None, 'B7': 'id_cliente', 'B9': 'nome',
        'B11': 'nascimento', 'E11': 'idade', 'B13': 'idade', 'E13': 'cpf',
        'B16': 'medicamento', 'B17': 'dose', 'H16': 'data_dose',
        'B18': 'susp_medicacao', 'G18': 'dieta', 'C20': 'medico',
        'B32': 'nascimento', 'E32': 'idade', 'I9': None, 'I30': None,
    }),
    ('IODOHIPER', 'iodo_15dias', 'Orientações iodo (preparo 15 dias)', {'C1': 'nome'}),
    ('IODOPOSCIR', 'iodo_30dias', 'Orientações iodo (preparo 30 dias)', {'C1': 'nome'}),
    ('ATESTADO', 'atestado', 'Atestado', {
        'B10': 'nome', 'F13': 'dias_texto', 'F14': 'data_inicio',
        'A16': 'cid_texto', 'B27': 'data_extenso',
    }),
    ('DECLARAÇÃODECOMPARECIMENTO', 'decl_comparecimento', 'Declaração de comparecimento', {
        'F9': 'nome', 'A13': 'exame', 'A14': 'periodo', 'F14': 'dias',
        'B23': 'cidade_data',
    }),
    ('DECLARAÇÃODEACOMPANHANTE', 'decl_acompanhante', 'Declaração de acompanhante', {
        'F9': 'acompanhante', 'A13': 'nome', 'A14': 'exame', 'A15': 'dias',
        'A16': 'periodo', 'B26': 'cidade_data',
    }),
    ('RECIBO', 'recibo', 'Recibo', {
        'D6': 'nome', 'D7': 'valor', 'D8': 'valor_extenso', 'B11': 'referente',
        'E14': 'data_extenso', 'F18': None,
    }),
]

# ---------------------------------------------------------------------------
# Cores
# ---------------------------------------------------------------------------
INDEXED = [
    '000000', 'FFFFFF', 'FF0000', '00FF00', '0000FF', 'FFFF00', 'FF00FF', '00FFFF',
    '000000', 'FFFFFF', 'FF0000', '00FF00', '0000FF', 'FFFF00', 'FF00FF', '00FFFF',
    '800000', '008000', '000080', '808000', '800080', '008080', 'C0C0C0', '808080',
    '9999FF', '993366', 'FFFFCC', 'CCFFFF', '660066', 'FF8080', '0066CC', 'CCCCFF',
    '000080', 'FF00FF', 'FFFF00', '00FFFF', '800080', '800000', '008080', '0000FF',
    '00CCFF', 'CCFFFF', 'CCFFCC', 'FFFF99', '99CCFF', 'FF99CC', 'CC99FF', 'FFCC99',
    '3366FF', '33CCCC', '99CC00', 'FFCC00', 'FF9900', 'FF6600', '666699', '969696',
    '003366', '339966', '003300', '333300', '993300', '993366', '333399', '333333',
]


class Theme:
    def __init__(self, xml_bytes):
        root = ET.fromstring(xml_bytes)
        scheme = root.find('.//a:clrScheme', NS)
        self.colors = {}
        for child in scheme:
            tag = child.tag.split('}')[1]
            c = child[0]
            val = c.get('lastClr') or c.get('val')
            self.colors[tag] = val
        # ordem usada pelos índices de tema das células
        self.order = ['lt1', 'dk1', 'lt2', 'dk2', 'accent1', 'accent2', 'accent3',
                      'accent4', 'accent5', 'accent6', 'hlink', 'folHlink']

    def by_index(self, i):
        try:
            return self.colors[self.order[i]]
        except (IndexError, KeyError):
            return '000000'

    def by_name(self, name):
        alias = {'bg1': 'lt1', 'tx1': 'dk1', 'bg2': 'lt2', 'tx2': 'dk2'}
        return self.colors.get(alias.get(name, name), '000000')


def apply_tint(hexrgb, tint):
    r, g, b = (int(hexrgb[i:i + 2], 16) / 255 for i in (0, 2, 4))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    if tint < 0:
        l = l * (1 + tint)
    else:
        l = l * (1 - tint) + tint
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return '%02X%02X%02X' % (round(r * 255), round(g * 255), round(b * 255))


def cell_color(color, theme, default=None):
    """Converte um openpyxl Color em '#RRGGBB'."""
    if color is None:
        return default
    try:
        if color.type == 'rgb' and isinstance(color.rgb, str):
            rgb = color.rgb[-6:]
            if color.rgb.startswith('00') and len(color.rgb) == 8 and rgb == '000000':
                # alpha 0 + preto costuma significar "automático"
                return default
        elif color.type == 'theme':
            rgb = theme.by_index(color.theme)
        elif color.type == 'indexed':
            if color.indexed in (64, 65):
                return default
            rgb = INDEXED[color.indexed] if color.indexed < len(INDEXED) else '000000'
        else:
            return default
        if color.tint:
            rgb = apply_tint(rgb, color.tint)
        return '#' + rgb
    except Exception:
        return default


def dml_color(el, theme):
    """Cor de um elemento DrawingML (srgbClr, schemeClr, ...) com modificadores."""
    if el is None:
        return None
    tag = el.tag.split('}')[1]
    if tag == 'srgbClr':
        rgb = el.get('val')
    elif tag == 'schemeClr':
        rgb = theme.by_name(el.get('val'))
    elif tag == 'sysClr':
        rgb = el.get('lastClr', '000000')
    elif tag == 'scrgbClr':
        rgb = '%02X%02X%02X' % tuple(round(int(el.get(k)) / 100000 * 255) for k in 'rgb')
    elif tag == 'prstClr':
        rgb = {'black': '000000', 'white': 'FFFFFF', 'red': 'FF0000'}.get(el.get('val'), '000000')
    else:
        return None
    r, g, b = (int(rgb[i:i + 2], 16) / 255 for i in (0, 2, 4))
    for mod in el:
        mtag = mod.tag.split('}')[1]
        v = int(mod.get('val', '100000')) / 100000
        if mtag == 'shade':
            r, g, b = r * v, g * v, b * v
        elif mtag == 'tint':
            r, g, b = (1 - (1 - x) * v for x in (r, g, b))
        elif mtag in ('lumMod', 'lumOff'):
            h, l, s = colorsys.rgb_to_hls(r, g, b)
            l = l * v if mtag == 'lumMod' else min(1, l + v)
            r, g, b = colorsys.hls_to_rgb(h, l, s)
    return '#%02X%02X%02X' % tuple(max(0, min(255, round(x * 255))) for x in (r, g, b))


def first_color(parent, theme):
    if parent is None:
        return None
    for child in parent:
        c = dml_color(child, theme)
        if c:
            return c
    return None


# ---------------------------------------------------------------------------
# Geometria da planilha
# ---------------------------------------------------------------------------
def build_col_widths(ws):
    widths = {}
    default = 64
    if ws.sheet_format.defaultColWidth:
        default = int(float(ws.sheet_format.defaultColWidth) * 7)
    for key, dim in ws.column_dimensions.items():
        lo = dim.min or column_index_from_string(key)
        hi = dim.max or lo
        for i in range(lo, min(hi, 400) + 1):
            if dim.hidden:
                widths[i] = 0
            elif dim.width:
                widths[i] = int(float(dim.width) * 7)
    return widths, default


def build_row_heights(ws):
    default_pt = float(ws.sheet_format.defaultRowHeight or 15)
    heights = {}
    for r, dim in ws.row_dimensions.items():
        if dim.hidden:
            heights[r] = 0
        elif dim.ht is not None:
            heights[r] = float(dim.ht)
    return heights, default_pt


class Grid:
    def __init__(self, ws):
        self.cw, self.cw_default = build_col_widths(ws)
        self.rh, self.rh_default = build_row_heights(ws)

    def colw(self, c):
        return self.cw.get(c, self.cw_default)

    def rowh_px(self, r):
        return round(self.rh.get(r, self.rh_default) * 96 / 72)

    def x_of(self, col0, origin_col):
        """Posição x (px) do início da coluna (índice 0-based), relativa à origem."""
        x = 0
        if col0 + 1 >= origin_col:
            for c in range(origin_col, col0 + 1):
                x += self.colw(c)
        else:
            for c in range(col0 + 1, origin_col):
                x -= self.colw(c)
        return x

    def y_of(self, row0, origin_row):
        y = 0
        if row0 + 1 >= origin_row:
            for r in range(origin_row, row0 + 1):
                y += self.rowh_px(r)
        else:
            for r in range(row0 + 1, origin_row):
                y -= self.rowh_px(r)
        return y


# ---------------------------------------------------------------------------
# Desenhos (imagens e caixas de texto)
# ---------------------------------------------------------------------------
def sheet_parts(zf):
    """Mapeia nome da aba -> caminho do XML da aba e do desenho."""
    wb = ET.fromstring(zf.read('xl/workbook.xml'))
    rels = ET.fromstring(zf.read('xl/_rels/workbook.xml.rels'))
    rid_target = {r.get('Id'): r.get('Target') for r in rels}
    out = {}
    for sh in wb.find('m:sheets', NS):
        rid = sh.get('{%s}id' % NS['r'])
        target = 'xl/' + rid_target[rid]
        drawing = None
        relpath = target.replace('worksheets/', 'worksheets/_rels/') + '.rels'
        if relpath in zf.namelist():
            for r in ET.fromstring(zf.read(relpath)):
                if r.get('Type', '').endswith('/drawing'):
                    drawing = os.path.normpath(os.path.join(os.path.dirname(target), r.get('Target'))).replace('\\', '/')
        out[sh.get('name')] = (target, drawing)
    return out


def read_anchor(anchor):
    tag = anchor.tag.split('}')[1]
    def pt(el):
        return (int(el.find('xdr:col', NS).text), int(el.find('xdr:colOff', NS).text),
                int(el.find('xdr:row', NS).text), int(el.find('xdr:rowOff', NS).text))
    frm = to = ext = None
    if tag in ('twoCellAnchor', 'oneCellAnchor'):
        frm = pt(anchor.find('xdr:from', NS))
    if tag == 'twoCellAnchor':
        to = pt(anchor.find('xdr:to', NS))
    e = anchor.find('xdr:ext', NS)
    if e is not None:
        ext = (int(e.get('cx')), int(e.get('cy')))
    return frm, to, ext


def anchor_box(anchor, grid, oc, orow):
    frm, to, ext = read_anchor(anchor)
    if frm is None:
        return None
    x = grid.x_of(frm[0], oc) + frm[1] / EMU_PX
    y = grid.y_of(frm[2], orow) + frm[3] / EMU_PX
    if to:
        x2 = grid.x_of(to[0], oc) + to[1] / EMU_PX
        y2 = grid.y_of(to[2], orow) + to[3] / EMU_PX
        w, h = x2 - x, y2 - y
    else:
        w, h = ext[0] / EMU_PX, ext[1] / EMU_PX
    return x, y, w, h, frm, to


def render_txbody(txbody, theme, default_color):
    parts = []
    paras = txbody.findall('a:p', NS)
    # parágrafos vazios no fim só ocupam espaço (e cortavam o texto em caixas justas)
    while paras and not ''.join(t.text or '' for t in paras[-1].iter('{%s}t' % NS['a'])).strip():
        paras.pop()
    for p in paras:
        ppr = p.find('a:pPr', NS)
        algn = {'ctr': 'center', 'r': 'right', 'just': 'justify'}.get(ppr.get('algn') if ppr is not None else None, 'left')
        runs = []
        size = None
        for el in p:
            t = el.tag.split('}')[1]
            if t == 'r':
                rpr = el.find('a:rPr', NS)
                text = el.find('a:t', NS).text or ''
                style = []
                if rpr is not None:
                    if rpr.get('sz'):
                        size = int(rpr.get('sz')) / 100
                        style.append('font-size:%spt' % size)
                    if rpr.get('b') == '1':
                        style.append('font-weight:bold')
                    if rpr.get('i') == '1':
                        style.append('font-style:italic')
                    if rpr.get('u') and rpr.get('u') != 'none':
                        style.append('text-decoration:underline')
                    col = first_color(rpr.find('a:solidFill', NS), theme)
                    if col:
                        style.append('color:' + col)
                runs.append('<span style="%s">%s</span>' % (';'.join(style), esc(text)))
            elif t == 'br':
                runs.append('<br>')
            elif t == 'endParaRPr' and el.get('sz'):
                size = size or int(el.get('sz')) / 100
        content = ''.join(runs) or '&nbsp;'
        fs = 'font-size:%spt;' % (size or 11)
        parts.append('<div style="text-align:%s;%s">%s</div>' % (algn, fs, content))
    return ''.join(parts), default_color


def render_drawing(zf, drawing_path, grid, oc, orow, theme, slug):
    if not drawing_path or drawing_path not in zf.namelist():
        return [], (0, 0)
    root = ET.fromstring(zf.read(drawing_path))
    relp = drawing_path.replace('drawings/', 'drawings/_rels/') + '.rels'
    rels = {}
    if relp in zf.namelist():
        rels = {r.get('Id'): os.path.normpath(os.path.join(os.path.dirname(drawing_path), r.get('Target'))).replace('\\', '/')
                for r in ET.fromstring(zf.read(relp))}
    items, maxx, maxy = [], 0, 0
    for anchor in root:
        box = anchor_box(anchor, grid, oc, orow)
        if box is None:
            continue
        x, y, w, h, frm, to = box
        pic = anchor.find('xdr:pic', NS)
        sp = anchor.find('xdr:sp', NS)
        if pic is not None:
            blip = pic.find('.//a:blip', NS)
            rid = blip.get('{%s}embed' % NS['r'])
            src = rels.get(rid)
            if not src or src not in zf.namelist():
                continue
            name = os.path.basename(src)
            with open(os.path.join(OUT_IMG, name), 'wb') as fh:
                fh.write(zf.read(src))
            items.append('<img class="xl-obj" src="{{ url_for(\'static\', filename=\'fichas/%s\') }}" '
                         'style="left:%.1fpx;top:%.1fpx;width:%.1fpx;height:%.1fpx">' % (name, x, y, w, h))
        elif sp is not None:
            if sp.find('.//xdr:cNvPr', NS) is not None and 'Bot' in (sp.find('.//xdr:cNvPr', NS).get('name') or ''):
                continue  # botões de macro não são impressos
            sppr = sp.find('xdr:spPr', NS)
            style_el = sp.find('xdr:style', NS)
            geom = sppr.find('a:prstGeom', NS)
            prst = geom.get('prst') if geom is not None else 'rect'
            # preenchimento
            fill = None
            if sppr.find('a:noFill', NS) is not None:
                fill = None
            elif sppr.find('a:solidFill', NS) is not None:
                fill = first_color(sppr.find('a:solidFill', NS), theme)
            elif style_el is not None and style_el.find('a:fillRef', NS) is not None and style_el.find('a:fillRef', NS).get('idx') not in ('0', None):
                fill = first_color(style_el.find('a:fillRef', NS), theme)
            # contorno
            line, lw = None, 0.75
            ln = sppr.find('a:ln', NS)
            if ln is not None and ln.find('a:noFill', NS) is not None:
                line = None
            elif ln is not None and ln.find('a:solidFill', NS) is not None:
                line = first_color(ln.find('a:solidFill', NS), theme)
                if ln.get('w'):
                    lw = int(ln.get('w')) / 12700
            elif style_el is not None and style_el.find('a:lnRef', NS) is not None and style_el.find('a:lnRef', NS).get('idx') not in ('0', None):
                lnref = style_el.find('a:lnRef', NS)
                line = first_color(lnref, theme)
                lw = {'1': 0.5, '2': 1.0, '3': 1.5}.get(lnref.get('idx'), 0.75)
                if ln is not None and ln.get('w'):
                    lw = int(ln.get('w')) / 12700
            # cor do texto
            tcolor = '#000000'
            if style_el is not None and style_el.find('a:fontRef', NS) is not None:
                tcolor = first_color(style_el.find('a:fontRef', NS), theme) or tcolor
            css = ['left:%.1fpx' % x, 'top:%.1fpx' % y, 'width:%.1fpx' % w, 'height:%.1fpx' % h, 'color:' + tcolor]
            if fill:
                css.append('background:' + fill)
            if line:
                css.append('border:%.2fpt solid %s' % (lw, line))
            if prst == 'roundRect':
                css.append('border-radius:%dpx' % max(2, round(min(w, h) * 0.17)))
            elif prst == 'ellipse':
                css.append('border-radius:50%')
            txbody = sp.find('xdr:txBody', NS)
            inner = ''
            if txbody is not None:
                bpr = txbody.find('a:bodyPr', NS)
                anchor_v = bpr.get('anchor', 't') if bpr is not None else 't'
                li = int(bpr.get('lIns', 91440)) / EMU_PX if bpr is not None else 9.6
                ri = int(bpr.get('rIns', 91440)) / EMU_PX if bpr is not None else 9.6
                ti = int(bpr.get('tIns', 45720)) / EMU_PX if bpr is not None else 4.8
                bi = int(bpr.get('bIns', 45720)) / EMU_PX if bpr is not None else 4.8
                css.append('padding:%.1fpx %.1fpx %.1fpx %.1fpx' % (ti, ri, bi, li))
                css.append('justify-content:%s' % {'ctr': 'center', 'b': 'flex-end'}.get(anchor_v, 'flex-start'))
                if bpr is not None and bpr.get('wrap') == 'none':
                    css.append('white-space:nowrap')
                inner, _ = render_txbody(txbody, theme, tcolor)
                if not re.sub(r'<[^>]+>|&nbsp;', '', inner).strip():
                    inner = ''
            items.append('<div class="xl-obj xl-shape" style="%s">%s</div>' % (';'.join(css), inner))
        else:
            continue
        maxx, maxy = max(maxx, x + w), max(maxy, y + h)
    return items, (maxx, maxy)


# ---------------------------------------------------------------------------
# Células
# ---------------------------------------------------------------------------
def esc(text):
    s = html.escape(str(text), quote=False)
    return s.replace('{', '&#123;').replace('}', '&#125;')


BORDER_CSS = {
    'thin': '1px solid', 'medium': '2px solid', 'thick': '3px solid',
    'dashed': '1px dashed', 'dotted': '1px dotted', 'double': '3px double',
    'hair': '1px dotted', 'mediumDashed': '2px dashed', 'dashDot': '1px dashed',
    'mediumDashDot': '2px dashed', 'dashDotDot': '1px dashed',
    'mediumDashDotDot': '2px dashed', 'slantDashDot': '2px dashed',
}


def border_css(side, theme):
    if side is None or not side.style:
        return None
    color = cell_color(side.color, theme, '#000000')
    return '%s %s' % (BORDER_CSS.get(side.style, '1px solid'), color)


def fmt_static(value, number_format):
    if isinstance(value, dt.datetime):
        if value.hour or value.minute:
            if value.year < 1901:
                return value.strftime('%H:%M')
        return value.strftime('%d/%m/%Y')
    if isinstance(value, dt.date):
        return value.strftime('%d/%m/%Y')
    if isinstance(value, dt.time):
        return value.strftime('%H:%M')
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return ('%.2f' % value).replace('.', ',')
    return str(value)


FORMULA_REF = re.compile(r"^=\s*'?([^'!]+)'?!\$?([A-Z]+)\$?(\d+)\s*$")
FORMULA_LOCAL = re.compile(r"^=\s*\$?([A-Z]+)\$?(\d+)\s*$")


def resolve(ws, coord, fields, cached_ws, depth=0):
    """Devolve ('expr', jinja) ou ('text', texto) ou None para a célula."""
    if coord in fields:
        expr = fields[coord]
        return ('expr', expr) if expr else None
    cell = ws[coord]
    v = cell.value
    if v is None:
        return None
    if isinstance(v, str) and v.startswith('='):
        m = FORMULA_REF.match(v)
        if m and m.group(1) in REFS:
            field = REFS[m.group(1)].get(m.group(2) + m.group(3))
            return ('expr', field) if field else None
        m = FORMULA_LOCAL.match(v)
        if m and depth < 5:
            return resolve(ws, m.group(1) + m.group(2), fields, cached_ws, depth + 1)
        if 'TODAY()' in v.upper():
            return ('expr', 'data')
        if 'EXTENSO' in v.upper():
            return ('expr', 'valor_extenso')
        if '#REF' in v.upper():
            return None
        cv = cached_ws[coord].value if cached_ws is not None else None
        return ('text', fmt_static(cv, cell.number_format)) if cv not in (None, '') else None
    return ('text', fmt_static(v, cell.number_format))


def jinja_expr(expr):
    if re.fullmatch(r'[a-z_][a-z0-9_]*', expr):
        expr = 'f.' + expr
    return '{{ %s }}' % expr


def convert_sheet(zf, wb, wbv, theme, parts, sheet_name, slug, title, fields):
    ws = wb[sheet_name]
    wsv = wbv[sheet_name]
    grid = Grid(ws)
    target, drawing = parts[sheet_name]

    # área de impressão
    if ws.print_area:
        area = ws.print_area if isinstance(ws.print_area, str) else ws.print_area[0]
        area = area.split('!')[-1].replace('$', '')
        c1, r1, c2, r2 = range_boundaries(area)
    else:
        c1, r1, c2, r2 = 1, 1, ws.max_column, ws.max_row
        c2 = min(c2, 12)
    # objetos desenhados (para ampliar a área quando a aba não tem área de impressão)
    _, (dx, dy) = render_drawing(zf, drawing, grid, c1, r1, theme, slug) if drawing else ([], (0, 0))
    if not ws.print_area:
        while grid.x_of(c2, c1) < dx and c2 < 60:
            c2 += 1
        while grid.y_of(r2, r1) < dy and r2 < 300:
            r2 += 1
    objs, _ = render_drawing(zf, drawing, grid, c1, r1, theme, slug) if drawing else ([], (0, 0))

    merged = {}
    covered = set()
    for mr in ws.merged_cells.ranges:
        if mr.min_col > c2 or mr.max_col < c1 or mr.min_row > r2 or mr.max_row < r1:
            continue
        merged[(mr.min_row, mr.min_col)] = (min(mr.max_row, r2), min(mr.max_col, c2))
        for r in range(mr.min_row, mr.max_row + 1):
            for c in range(mr.min_col, mr.max_col + 1):
                if (r, c) != (mr.min_row, mr.min_col):
                    covered.add((r, c))

    widths = [grid.colw(c) for c in range(c1, c2 + 1)]
    total_w = sum(widths)
    heights = [grid.rowh_px(r) for r in range(r1, r2 + 1)]
    total_h = sum(heights)

    rows_html = []
    for r in range(r1, r2 + 1):
        h = grid.rowh_px(r)
        tds = []
        for c in range(c1, c2 + 1):
            if (r, c) in covered:
                continue
            coord = get_column_letter(c) + str(r)
            cell = ws[coord]
            rs, cs = 1, 1
            er, ec = r, c
            if (r, c) in merged:
                er, ec = merged[(r, c)]
                rs, cs = er - r + 1, ec - c + 1
            css = []
            # bordas (em mesclagens, usa as bordas das extremidades)
            b_top = border_css(cell.border.top, theme)
            b_left = border_css(cell.border.left, theme)
            b_bottom = border_css(ws.cell(er, c).border.bottom, theme) or border_css(cell.border.bottom, theme)
            b_right = border_css(ws.cell(r, ec).border.right, theme) or border_css(cell.border.right, theme)
            for name, val in (('top', b_top), ('right', b_right), ('bottom', b_bottom), ('left', b_left)):
                if val:
                    css.append('border-%s:%s' % (name, val))
            fill = cell.fill
            if fill is not None and fill.fill_type == 'solid':
                col = cell_color(fill.fgColor, theme)
                # branco puro = papel; não pintar evita esconder texto que transborda da linha vizinha
                if col and col.upper() != '#FFFFFF':
                    css.append('background:' + col)
            font = cell.font
            if font is not None:
                if font.name and font.name != 'Calibri':
                    css.append("font-family:'%s',Calibri,Arial,sans-serif" % font.name)
                if font.sz and float(font.sz) != 11:
                    css.append('font-size:%gpt' % float(font.sz))
                if font.b:
                    css.append('font-weight:bold')
                if font.i:
                    css.append('font-style:italic')
                if font.u and font.u != 'none':
                    css.append('text-decoration:underline')
                fc = cell_color(font.color, theme)
                if fc and fc.upper() != '#000000':
                    css.append('color:' + fc)
            al = cell.alignment
            content = resolve(ws, coord, fields, wsv)
            halign = al.horizontal if al is not None else None
            if halign in (None, 'general'):
                halign = 'right' if (content and content[0] == 'text' and isinstance(cell.value, (int, float)) and not isinstance(cell.value, bool)) else 'left'
            halign = {'centerContinuous': 'center', 'distributed': 'justify', 'fill': 'left'}.get(halign, halign)
            if halign != 'left':
                css.append('text-align:' + halign)
            valign = (al.vertical if al is not None else None) or 'bottom'
            valign = {'center': 'middle', 'distributed': 'middle', 'justify': 'top'}.get(valign, valign)
            if valign != 'bottom':
                css.append('vertical-align:' + valign)
            wrap = bool(al is not None and al.wrap_text)
            if wrap:
                css.append('white-space:pre-wrap')
            if al is not None and al.indent:
                css.append('padding-left:%dpx' % (int(al.indent) * 9 + 2))
            inner = ''
            if content:
                if content[0] == 'text':
                    inner = esc(content[1]).replace('\n', '<br>') if not wrap else esc(content[1])
                else:
                    inner = jinja_expr(content[1])
            attrs = ''
            if rs > 1:
                attrs += ' rowspan="%d"' % rs
            if cs > 1:
                attrs += ' colspan="%d"' % cs
            if css:
                attrs += ' style="%s"' % ';'.join(css)
            tds.append('<td%s>%s</td>' % (attrs, inner))
        rows_html.append('<tr style="height:%dpx">%s</tr>' % (h, ''.join(tds)))

    # Página A4 e escala para caber em uma folha
    landscape = (ws.page_setup.orientation == 'landscape')
    pw_mm, ph_mm = (297, 210) if landscape else (210, 297)
    m = ws.page_margins
    ml, mr_, mt, mb = (m.left or 0.7), (m.right or 0.7), (m.top or 0.75), (m.bottom or 0.75)
    avail_w = (pw_mm / 25.4 - ml - mr_) * 96
    avail_h = (ph_mm / 25.4 - mt - mb) * 96
    fit = min(avail_w / max(total_w, 1), avail_h / max(total_h, 1))
    scale = (ws.page_setup.scale or 100) / 100
    fit_to_page = bool(ws.sheet_properties.pageSetUpPr and ws.sheet_properties.pageSetUpPr.fitToPage)
    zoom = fit if fit_to_page else min(scale, fit)
    zoom = round(min(zoom, 1.6), 4)
    centered = bool(ws.print_options.horizontalCentered)

    colgroup = ''.join('<col style="width:%dpx">' % w for w in widths)
    out = []
    out.append('{# Gerado por ferramentas/converter_fichas.py a partir da aba "%s". Não editar à mão. #}' % sheet_name)
    out.append('<section class="folha %s" data-ficha="%s" style="--ml:%.2fin;--mr:%.2fin;--mt:%.2fin;--mb:%.2fin">'
               % ('paisagem' if landscape else 'retrato', slug, ml, mr_, mt, mb))
    out.append('<div class="xl-sheet%s" style="width:%dpx;height:%dpx;zoom:%s">'
               % (' centralizado' if centered else '', total_w, total_h, zoom))
    out.append('<table class="xl" style="width:%dpx"><colgroup>%s</colgroup>' % (total_w, colgroup))
    out.extend(rows_html)
    out.append('</table>')
    out.extend(objs)
    out.append('</div></section>')
    with open(os.path.join(OUT_TPL, slug + '.html'), 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(out) + '\n')
    return {'slug': slug, 'titulo': title, 'aba': sheet_name, 'paisagem': landscape}


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else None
    if not src:
        print(__doc__)
        sys.exit(1)
    os.makedirs(OUT_TPL, exist_ok=True)
    os.makedirs(OUT_IMG, exist_ok=True)
    wb = openpyxl.load_workbook(src, data_only=False)
    wbv = openpyxl.load_workbook(src, data_only=True)
    with zipfile.ZipFile(src) as zf:
        theme = Theme(zf.read('xl/theme/theme1.xml'))
        parts = sheet_parts(zf)
        manifest = []
        for sheet_name, slug, title, fields in SHEETS:
            if sheet_name not in wb.sheetnames:
                print('AVISO: aba não encontrada:', sheet_name)
                continue
            manifest.append(convert_sheet(zf, wb, wbv, theme, parts, sheet_name, slug, title, fields))
            print('ok:', sheet_name, '->', slug + '.html')
    with open(os.path.join(OUT_TPL, '_manifesto.json'), 'w', encoding='utf-8') as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
