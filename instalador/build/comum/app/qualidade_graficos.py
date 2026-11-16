"""Desenhos da Qualidade para os PDFs (fluxograma com raias, organograma, espinha de peixe do Ishikawa, cinco porquês,
matriz de risco e gráfico de Pareto). Tudo em vetores do reportlab; só caracteres que as fontes padrão do PDF aceitam."""
from __future__ import annotations

from reportlab.graphics.shapes import Circle, Drawing, Group, Line, PolyLine, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.platypus import Flowable
from reportlab.pdfbase.pdfmetrics import stringWidth

FONTE = 'Helvetica'
NEGRITO = 'Helvetica-Bold'
VERDE = colors.HexColor('#255f39')
TEXTO = colors.HexColor('#263238')
LINHA = colors.HexColor('#546e7a')
PALETA_RAIA = ['#e3f2fd', '#e8f5e9', '#fff8e1', '#fce4ec', '#ede7f6', '#e0f7fa', '#fbe9e7', '#f1f8e9']
COR_FORMA = {'inicio': '#c8e6c9', 'processo': '#e3f2fd', 'decisao': '#fff3cd', 'documento': '#f3e5f5', 'dados': '#e0f7fa',
             'subprocesso': '#ede7f6', 'conector': '#eceff1', 'espera': '#ffe0b2'}
RAIA_H = 150
RAIA_ROT = 120


def _cor(h, padrao='#ffffff'):
    try:
        return colors.HexColor(h or padrao)
    except (ValueError, TypeError):
        return colors.HexColor(padrao)


def _limpo(t):
    """Troca o que as fontes padrão do PDF não desenham."""
    return str(t or '').replace('★', '*').replace('≥', '>=').replace('≤', '<=').replace('→', '->').replace('–', '-').replace('\n', ' ')


def quebrar(texto, fonte, tamanho, largura, max_linhas=None):
    palavras = _limpo(texto).split()
    linhas, atual = [], ''
    for p in palavras:
        teste = (atual + ' ' + p).strip()
        if stringWidth(teste, fonte, tamanho) <= largura or not atual:
            atual = teste
        else:
            linhas.append(atual)
            atual = p
    if atual:
        linhas.append(atual)
    if max_linhas and len(linhas) > max_linhas:
        linhas = linhas[:max_linhas]
        linhas[-1] = linhas[-1][:max(1, len(linhas[-1]) - 3)] + '...'
    return linhas


def _texto_centrado(g, cx, cy, linhas, tamanho, fonte=FONTE, cor=TEXTO):
    entre = tamanho * 1.18
    topo = cy + (len(linhas) - 1) * entre / 2.0
    for i, ln in enumerate(linhas):
        g.add(String(cx, topo - i * entre - tamanho * 0.34, ln, fontName=fonte, fontSize=tamanho, fillColor=cor, textAnchor='middle'))


def ajustar(desenho, largura_max, altura_max):
    """Reduz o desenho para caber na área do PDF (nunca amplia além de 1,25x)."""
    esc = min(largura_max / float(desenho.width), altura_max / float(desenho.height), 1.25)
    desenho.scale(esc, esc)
    desenho.width *= esc
    desenho.height *= esc
    return desenho


class Fatia(Flowable):
    """Janela de um desenho largo: o desenho é impresso em faixas (uma abaixo da outra) para manter o texto legível."""

    def __init__(self, desenho, x0, x1, parte, total, rotulos=None):
        super().__init__()
        self.d, self.x0, self.x1, self.parte, self.total, self.rotulos = desenho, x0, x1, parte, total, rotulos or []

    def wrap(self, largura, altura):
        self.width = self.x1 - self.x0
        self.height = self.d.height + 11
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.saveState()
        c.setFont(FONTE, 6.8)
        c.setFillColor(LINHA)
        c.drawString(0, self.d.height + 2, 'Parte %d de %d%s' % (self.parte, self.total, '  (continua na faixa seguinte)' if self.parte < self.total else ''))
        path = c.beginPath()
        path.rect(0, 0, self.width, self.d.height)
        c.clipPath(path, stroke=0, fill=0)
        from reportlab.graphics import renderPDF
        renderPDF.draw(self.d, c, -self.x0, 0)
        if self.parte > 1:                      # nome das raias no começo de cada faixa seguinte
            for nome, y, h in self.rotulos:
                c.setFillColor(colors.white)
                c.setFillAlpha(0.88)
                c.roundRect(1, y + 2, 50, h - 4, 3, stroke=0, fill=1)
                c.setFillAlpha(1)
                c.setFillColor(TEXTO)
                c.setFont(NEGRITO, 6.4)
                linhas = quebrar(nome, NEGRITO, 6.4, 44, 6)
                topo = y + h / 2.0 + (len(linhas) - 1) * 3.6
                for i, ln in enumerate(linhas):
                    c.drawCentredString(26, topo - i * 7.4 - 2, ln)
        c.restoreState()


def _fatiar(d, intervalos, rotulos, largura_max, altura_max, minimo):
    """Ajusta o desenho. Se ele precisar ficar menor que `minimo` para caber na largura, imprime em faixas cortadas entre as etapas."""
    W, H = float(d.width), float(d.height)
    ideal = min(largura_max / W, altura_max / H)
    if ideal >= minimo:
        return [ajustar(d, largura_max, altura_max)]
    esc = max(minimo, 0.1)
    if H * esc > altura_max:
        esc = altura_max / H
    d.scale(esc, esc)
    d.width, d.height = W * esc, H * esc
    if d.width <= largura_max + 1:
        return [d]
    ivs = [(a * esc, b * esc) for a, b in intervalos]
    import math
    livres = [b + 4 for _a, b in ivs if not any(a2 < b + 4 < b2 for a2, b2 in ivs)]      # posições entre etapas onde dá para cortar
    cortes = None
    for n in range(max(2, int(math.ceil(d.width / float(largura_max)))), 14):
        atual = [0.0]
        for i in range(1, n):
            ideal = i * d.width / n
            ok = [x for x in livres if atual[-1] + largura_max * 0.3 < x <= atual[-1] + largura_max and d.width - x <= (n - i) * largura_max]
            if not ok:
                break
            atual.append(min(ok, key=lambda x: abs(x - ideal)))
        else:
            cortes = atual
            break
    if cortes is None:                      # sem lugar entre as etapas: corta em pedaços iguais
        n = int(math.ceil(d.width / float(largura_max)))
        cortes = [i * d.width / n for i in range(n)]
    cortes.append(d.width)
    total = len(cortes) - 1
    rot = [(nome, y * esc, h * esc) for nome, y, h in rotulos]
    fatias = [Fatia(d, cortes[i], cortes[i + 1], i + 1, total, rot) for i in range(total)]
    for f in fatias:
        f.hAlign = 'CENTER'
    return fatias


# ------------------------------------------------------------------ fluxograma
def _seta(g, x1, y1, x2, y2, cor=LINHA):
    import math
    ang = math.atan2(y2 - y1, x2 - x1)
    t = 6.0
    g.add(Polygon([x2, y2, x2 - t * math.cos(ang - 0.45), y2 - t * math.sin(ang - 0.45), x2 - t * math.cos(ang + 0.45), y2 - t * math.sin(ang + 0.45)],
                  fillColor=cor, strokeColor=cor, strokeWidth=0.5))


def _desenho_fluxo(dados):
    """Desenha o fluxograma do editor ({nos, ligacoes, raias}) com raias horizontais. Devolve (desenho, intervalos em x das etapas, rótulos das raias)."""
    nos = dados.get('nos') or []
    raias = dados.get('raias') or []
    if not nos:
        d = Drawing(300, 40)
        d.add(String(10, 15, 'Fluxograma sem etapas.', fontName=FONTE, fontSize=10))
        return d, [], []
    x_min = min(n['x'] for n in nos)
    x_max = max(n['x'] + n['l'] for n in nos)
    y_min = min(n['y'] for n in nos)
    y_max = max(n['y'] + n['a'] for n in nos)
    margem = 24
    esq = RAIA_ROT if raias else 0
    if raias:
        y_min, y_max = 0, max(y_max + margem, len(raias) * RAIA_H)
    ox = esq - x_min + margem
    larg = (x_max - x_min) + esq + 2 * margem
    alt = (y_max - y_min) + 2 * margem
    oy = margem - y_min
    d = Drawing(larg, alt)
    g = Group()

    def X(x):
        return x + ox

    def Y(y):          # y do editor cresce para baixo; no PDF cresce para cima
        return alt - (y + oy)

    rotulos = []
    for i, r in enumerate(raias):
        cor = _cor(r.get('cor') or PALETA_RAIA[i % len(PALETA_RAIA)])
        topo = Y(i * RAIA_H)
        rotulos.append((r.get('nome') or 'Raia', topo - RAIA_H, RAIA_H))
        g.add(Rect(margem, topo - RAIA_H, larg - 2 * margem, RAIA_H, fillColor=cor, strokeColor=LINHA, strokeWidth=0.6, fillOpacity=0.5))
        g.add(Rect(margem, topo - RAIA_H, esq - 8, RAIA_H, fillColor=cor, strokeColor=LINHA, strokeWidth=0.6))
        _texto_centrado(g, margem + (esq - 8) / 2.0, topo - RAIA_H / 2.0, quebrar(r.get('nome') or 'Raia', NEGRITO, 10.5, esq - 18, 5), 10.5, NEGRITO)
    indice = {n['id']: n for n in nos}
    for e in dados.get('ligacoes') or []:
        a, b = indice.get(e.get('de')), indice.get(e.get('para'))
        if not a or not b:
            continue
        cor = _cor(e.get('cor') or '#546e7a')
        ax, ay, bx, by = a['x'], a['y'], b['x'], b['y']
        if bx >= ax + a['l'] - 4:                         # alvo à direita: sai pela direita, entra pela esquerda
            p1 = (ax + a['l'], ay + a['a'] / 2.0)
            p2 = (bx, by + b['a'] / 2.0)
            meio = (p1[0] + p2[0]) / 2.0
            pts = [p1, (meio, p1[1]), (meio, p2[1]), p2]
        elif by >= ay + a['a']:                            # alvo abaixo
            p1 = (ax + a['l'] / 2.0, ay + a['a'])
            p2 = (bx + b['l'] / 2.0, by)
            meio = (p1[1] + p2[1]) / 2.0
            pts = [p1, (p1[0], meio), (p2[0], meio), p2]
        elif by + b['a'] <= ay:                            # alvo acima
            p1 = (ax + a['l'] / 2.0, ay)
            p2 = (bx + b['l'] / 2.0, by + b['a'])
            meio = (p1[1] + p2[1]) / 2.0
            pts = [p1, (p1[0], meio), (p2[0], meio), p2]
        else:                                              # volta para a esquerda: contorna por cima
            p1 = (ax + a['l'] / 2.0, ay)
            p2 = (bx + b['l'] / 2.0, by)
            topo = min(ay, by) - 18
            pts = [p1, (p1[0], topo), (p2[0], topo), p2]
        plano = []
        for px, py in pts:
            plano += [X(px), Y(py)]
        g.add(PolyLine(plano, strokeColor=cor, strokeWidth=1.1))
        _seta(g, plano[-4], plano[-3], plano[-2], plano[-1], cor)
        if e.get('rotulo'):
            mx, my = (plano[0] + plano[2]) / 2.0 + 3, (plano[1] + plano[3]) / 2.0 + 3
            g.add(String(mx, my, _limpo(e['rotulo']), fontName=NEGRITO, fontSize=9.5, fillColor=TEXTO))
    for n in nos:
        x, y, w, h = X(n['x']), Y(n['y'] + n['a']), n['l'], n['a']
        cor = _cor(n.get('cor') or COR_FORMA.get(n.get('forma'), '#ffffff'))
        forma = n.get('forma')
        borda = dict(strokeColor=LINHA, strokeWidth=1.0, fillColor=cor)
        if forma == 'inicio':
            g.add(Rect(x, y, w, h, rx=h / 2.0, ry=h / 2.0, **borda))
        elif forma == 'decisao':
            g.add(Polygon([x + w / 2.0, y + h, x + w, y + h / 2.0, x + w / 2.0, y, x, y + h / 2.0], **borda))
        elif forma == 'conector':
            g.add(Circle(x + w / 2.0, y + h / 2.0, min(w, h) / 2.0, **borda))
        elif forma == 'dados':
            g.add(Polygon([x + 12, y + h, x + w, y + h, x + w - 12, y, x, y], **borda))
        elif forma == 'subprocesso':
            g.add(Rect(x, y, w, h, **borda))
            g.add(Line(x + 8, y, x + 8, y + h, strokeColor=LINHA, strokeWidth=1))
            g.add(Line(x + w - 8, y, x + w - 8, y + h, strokeColor=LINHA, strokeWidth=1))
        elif forma == 'documento':
            g.add(Polygon([x, y + 6, x, y + h, x + w, y + h, x + w, y + 6, x + w * 0.75, y, x + w * 0.5, y + 6, x + w * 0.25, y + 12, x, y + 6], **borda))
        else:
            g.add(Rect(x, y, w, h, rx=4, ry=4, **borda))
        tam = 9.5
        util = w - (w * 0.38 if forma == 'decisao' else 14)
        linhas = quebrar(n.get('texto'), FONTE, tam, util, 5)
        while len(linhas) * tam * 1.18 > h - 4 and tam > 5.5:
            tam -= 0.5
            linhas = quebrar(n.get('texto'), FONTE, tam, util, 6)
        _texto_centrado(g, x + w / 2.0, y + h / 2.0, linhas, tam)
    d.add(g)
    return d, [(X(n['x']), X(n['x'] + n['l'])) for n in nos], rotulos


def fluxograma(dados, largura_max=757, altura_max=470, minimo=0.7):
    """Lista de flowables do fluxograma: um desenho ajustado à página ou, se ficar largo demais, faixas legíveis cortadas entre as etapas."""
    d, ivs, rotulos = _desenho_fluxo(dados)
    return _fatiar(d, ivs, rotulos, largura_max, altura_max, minimo)


# ------------------------------------------------------------------ organograma
def _desenho_org(nos):
    """Árvore de cargos. `nos`: lista de dicts com id, cargo, pessoa, setor, pai_id, cor. Devolve (desenho, intervalos em x)."""
    if not nos:
        d = Drawing(300, 40)
        d.add(String(10, 15, 'Organograma sem cargos.', fontName=FONTE, fontSize=10))
        return d, []
    filhos = {}
    for n in nos:
        filhos.setdefault(n['pai_id'], []).append(n)
    L, A, ESPACO_X, ESPACO_Y = 118, 46, 14, 34
    posicoes = {}

    def largura(n):
        fs = filhos.get(n['id'], [])
        return max(L, sum(largura(f) for f in fs) + ESPACO_X * (len(fs) - 1)) if fs else L

    def colocar(n, x0, nivel):
        w = largura(n)
        posicoes[n['id']] = (x0 + w / 2.0 - L / 2.0, nivel)
        x = x0
        for f in filhos.get(n['id'], []):
            colocar(f, x, nivel + 1)
            x += largura(f) + ESPACO_X
    raizes = filhos.get(None, [])
    x = 0
    for r in raizes:
        colocar(r, x, 0)
        x += largura(r) + ESPACO_X
    niveis = max(p[1] for p in posicoes.values()) + 1
    larg = max(x - ESPACO_X, L) + 24
    alt = niveis * (A + ESPACO_Y) - ESPACO_Y + 24
    d = Drawing(larg, alt)
    g = Group()

    def pos(n):
        px, nv = posicoes[n['id']]
        return px + 12, alt - 12 - A - nv * (A + ESPACO_Y)
    por_id = {n['id']: n for n in nos}
    for n in nos:
        if n['pai_id'] in por_id:
            (px, py), (cx, cy) = pos(por_id[n['pai_id']]), pos(n)
            meio = py - ESPACO_Y / 2.0
            g.add(PolyLine([px + L / 2.0, py, px + L / 2.0, meio, cx + L / 2.0, meio, cx + L / 2.0, cy + A], strokeColor=LINHA, strokeWidth=1))
    for n in nos:
        x, y = pos(n)
        cor = _cor(n.get('cor') or '#255f39')
        g.add(Rect(x, y, L, A, rx=4, ry=4, fillColor=colors.white, strokeColor=cor, strokeWidth=1.2))
        g.add(Rect(x, y + A - 6, L, 6, fillColor=cor, strokeColor=cor, strokeWidth=0.5))
        linhas = quebrar(n['cargo'], NEGRITO, 7.8, L - 8, 2)
        extra = []
        if n.get('pessoa'):
            extra = quebrar(n['pessoa'], FONTE, 7.2, L - 8, 1)
        elif n.get('setor'):
            extra = quebrar(n['setor'], FONTE, 7, L - 8, 1)
        base = y + A - 8
        for i, ln in enumerate(linhas):
            g.add(String(x + L / 2.0, base - 8.5 - i * 9, ln, fontName=NEGRITO, fontSize=7.8, fillColor=TEXTO, textAnchor='middle'))
        for j, ln in enumerate(extra):
            g.add(String(x + L / 2.0, y + 5 - 0 + j * 8, ln, fontName=FONTE, fontSize=7.2, fillColor=LINHA, textAnchor='middle'))
    d.add(g)
    return d, [(pos(n)[0], pos(n)[0] + L) for n in nos]


def organograma(nos, largura_max=757, altura_max=470, minimo=0.75):
    d, ivs = _desenho_org(nos)
    return _fatiar(d, ivs, [], largura_max, altura_max, minimo)


# ------------------------------------------------------------------ Ishikawa
def ishikawa(isk, largura_max=757, altura_max=420):
    """Espinha de peixe: problema à direita, três categorias em cima e três embaixo."""
    W, H = 900, 430
    d = Drawing(W, H)
    g = Group()
    meio = H / 2.0
    cabeca_x = W - 150
    g.add(Line(20, meio, cabeca_x, meio, strokeColor=VERDE, strokeWidth=3))
    _seta(g, cabeca_x - 8, meio, cabeca_x, meio, VERDE)
    g.add(Rect(cabeca_x, meio - 44, 140, 88, rx=8, ry=8, fillColor=colors.HexColor('#e8f5e9'), strokeColor=VERDE, strokeWidth=1.6))
    _texto_centrado(g, cabeca_x + 70, meio, quebrar(isk.get('problema') or 'Problema', NEGRITO, 9.5, 126, 6), 9.5, NEGRITO)
    grupos = isk.get('grupos') or []
    colunas = [(262 + i * 210) for i in range(3)]
    for k, gr in enumerate(grupos[:6]):
        cima = k < 3
        cx = colunas[k % 3]
        y_ponta = meio + (170 if cima else -170)
        x_ponta = cx - 60
        g.add(Line(x_ponta, y_ponta, cx + 40, meio, strokeColor=LINHA, strokeWidth=1.8))
        g.add(Rect(x_ponta - 52, y_ponta + (0 if cima else -18), 104, 18, rx=3, ry=3, fillColor=VERDE, strokeColor=VERDE))
        g.add(String(x_ponta, y_ponta + (5.5 if cima else -12.5), gr['categoria'].upper(), fontName=NEGRITO, fontSize=8, fillColor=colors.white, textAnchor='middle'))
        causas = gr['causas'][:7]
        for i, c in enumerate(causas):
            frac = (i + 1.0) / (len(causas) + 1.0)
            yy = y_ponta + (meio - y_ponta) * frac
            xx = x_ponta + (cx + 40 - x_ponta) * frac
            g.add(Line(xx - 16, yy, xx, yy, strokeColor=LINHA, strokeWidth=0.8))
            linhas = quebrar(c['texto'], NEGRITO if c.get('principal') else FONTE, 7.4, 130, 2)
            for j, ln in enumerate(linhas):
                g.add(String(xx - 18, yy + 1.5 - j * 7 + (7 if len(linhas) > 1 else 0) * 0, ln, fontName=NEGRITO if c.get('principal') else FONTE, fontSize=7.4,
                             fillColor=colors.HexColor('#b71c1c') if c.get('principal') else TEXTO, textAnchor='end'))
        if not causas:
            g.add(String(x_ponta - 10, (y_ponta + meio) / 2.0, 'sem causas', fontName=FONTE, fontSize=6.6, fillColor=LINHA, textAnchor='end'))
    d.add(g)
    return ajustar(d, largura_max, altura_max)


# ------------------------------------------------------------------ cinco porquês
def porques(titulo, respostas, raiz='', largura_max=500, altura_max=470):
    W = 560
    alt_caixa, espaco = 40, 16
    itens = [('Problema', titulo, '#fde7e9')] + [('%dº porquê' % (i + 1), t, '#e3f2fd') for i, t in enumerate(respostas)]
    if raiz:
        itens.append(('Causa raiz', raiz, '#c8e6c9'))
    H = len(itens) * (alt_caixa + espaco) - espaco + 8
    d = Drawing(W, H)
    g = Group()
    for i, (rot, txt, cor) in enumerate(itens):
        y = H - 4 - alt_caixa - i * (alt_caixa + espaco)
        g.add(Rect(4, y, W - 8, alt_caixa, rx=5, ry=5, fillColor=_cor(cor), strokeColor=LINHA, strokeWidth=0.9))
        g.add(Rect(4, y, 82, alt_caixa, rx=5, ry=5, fillColor=VERDE, strokeColor=VERDE))
        g.add(String(45, y + alt_caixa / 2.0 - 3, rot, fontName=NEGRITO, fontSize=8, fillColor=colors.white, textAnchor='middle'))
        linhas = quebrar(txt or '(não preenchido)', FONTE, 8.5, W - 120, 2)
        for j, ln in enumerate(linhas):
            g.add(String(94, y + alt_caixa / 2.0 + (4 if len(linhas) > 1 else -3) - j * 10, ln, fontName=FONTE, fontSize=8.5, fillColor=TEXTO))
        if i < len(itens) - 1:
            _seta(g, W / 2.0, y - 1, W / 2.0, y - espaco + 1, LINHA)
            g.add(Line(W / 2.0, y, W / 2.0, y - espaco + 5, strokeColor=LINHA, strokeWidth=1.2))
    d.add(g)
    return ajustar(d, largura_max, altura_max)


# ------------------------------------------------------------------ matriz de risco 5x5
def matriz_risco(grade, largura_max=380, altura_max=330):
    """`grade`: saída de qualidade.matriz_risco (linhas de probabilidade 5..1, colunas de impacto 1..5)."""
    c = 56
    W, H = 5 * c + 70, 5 * c + 56
    d = Drawing(W, H)
    g = Group()
    for i, linha in enumerate(grade):
        for j, cel in enumerate(linha):
            x, y = 50 + j * c, 30 + (4 - i) * c
            g.add(Rect(x, y, c, c, fillColor=_cor(cel['cor']), strokeColor=colors.white, strokeWidth=1.5, fillOpacity=0.85))
            g.add(String(x + 4, y + c - 10, str(cel['pontos']), fontName=FONTE, fontSize=6.5, fillColor=colors.white))
            n = len(cel['riscos'])
            if n:
                g.add(Circle(x + c / 2.0, y + c / 2.0 - 2, 11, fillColor=colors.white, strokeColor=TEXTO, strokeWidth=0.8))
                g.add(String(x + c / 2.0, y + c / 2.0 - 5, str(n), fontName=NEGRITO, fontSize=10, fillColor=TEXTO, textAnchor='middle'))
    for k in range(5):
        g.add(String(50 + k * c + c / 2.0, 18, str(k + 1), fontName=NEGRITO, fontSize=9, fillColor=TEXTO, textAnchor='middle'))
        g.add(String(42, 30 + (4 - k) * c + c / 2.0 - 3, str(5 - k), fontName=NEGRITO, fontSize=9, fillColor=TEXTO, textAnchor='end'))
    g.add(String(50 + 2.5 * c, 5, 'IMPACTO', fontName=NEGRITO, fontSize=8, fillColor=LINHA, textAnchor='middle'))
    g.add(String(4, 30 + 2.5 * c, 'PROB.', fontName=NEGRITO, fontSize=8, fillColor=LINHA))
    d.add(g)
    return ajustar(d, largura_max, altura_max)


# ------------------------------------------------------------------ Pareto
def pareto(itens, largura_max=700, altura_max=300):
    """Barras do valor e linha do percentual acumulado, com a marca dos 80%."""
    itens = itens[:15]
    W, H = 720, 280
    d = Drawing(W, H)
    g = Group()
    if not itens:
        g.add(String(10, H / 2.0, 'Sem dados no período.', fontName=FONTE, fontSize=10))
        d.add(g)
        return d
    x0, y0, w, h = 50, 60, 620, 190
    maximo = max(i['valor'] for i in itens) or 1
    g.add(Rect(x0, y0, w, h, fillColor=None, strokeColor=colors.HexColor('#b0bec5'), strokeWidth=0.8))
    y80 = y0 + h * 0.8
    g.add(Line(x0, y80, x0 + w, y80, strokeColor=colors.HexColor('#ef6c00'), strokeWidth=0.8, strokeDashArray=[3, 3]))
    g.add(String(x0 + w + 4, y80 - 3, '80%', fontName=FONTE, fontSize=7, fillColor=colors.HexColor('#ef6c00')))
    larg_b = w / float(len(itens))
    pontos = []
    for k, it in enumerate(itens):
        altura = h * it['valor'] / float(maximo)
        bx = x0 + k * larg_b + larg_b * 0.15
        cor = {'A': '#c62828', 'B': '#ef6c00'}.get(it.get('classe'), '#2e7d32')
        g.add(Rect(bx, y0, larg_b * 0.7, altura, fillColor=_cor(cor), strokeColor=_cor(cor)))
        g.add(String(bx + larg_b * 0.35, y0 + altura + 2, ('%g' % it['valor']).replace('.', ','), fontName=FONTE, fontSize=6.5, fillColor=TEXTO, textAnchor='middle'))
        for j, ln in enumerate(quebrar(it['rotulo'], FONTE, 6.2, larg_b - 2, 3)):
            g.add(String(bx + larg_b * 0.35, y0 - 9 - j * 7, ln, fontName=FONTE, fontSize=6.2, fillColor=TEXTO, textAnchor='middle'))
        pontos.append((bx + larg_b * 0.35, y0 + h * min(100.0, it['acum']) / 100.0))
    if len(pontos) > 1:
        g.add(PolyLine([c for p in pontos for c in p], strokeColor=colors.HexColor('#1565c0'), strokeWidth=1.4))
    for px, py in pontos:
        g.add(Circle(px, py, 2.2, fillColor=colors.HexColor('#1565c0'), strokeColor=colors.HexColor('#1565c0')))
    g.add(String(x0 - 4, y0 + h - 3, '100%', fontName=FONTE, fontSize=7, fillColor=LINHA, textAnchor='end'))
    g.add(String(x0 - 4, y0 - 3, '0', fontName=FONTE, fontSize=7, fillColor=LINHA, textAnchor='end'))
    d.add(g)
    return ajustar(d, largura_max, altura_max)


# ------------------------------------------------------------------ perfil epidemiológico
def barras_h(itens, largura=360, cor='#2f7a49', max_itens=10):
    """Barras horizontais: itens = [{'rotulo', 'n', 'pct'}]."""
    itens = itens[:max_itens]
    alt_l = 15
    H = max(30, len(itens) * alt_l + 8)
    d = Drawing(largura, H)
    g = Group()
    if not itens:
        g.add(String(4, H / 2.0, 'Sem dados no período.', fontName=FONTE, fontSize=8, fillColor=LINHA))
        d.add(g)
        return d
    maximo = max(i['n'] for i in itens) or 1
    x0, area = 128, largura - 128 - 62
    for k, it in enumerate(itens):
        y = H - 4 - (k + 1) * alt_l + 3
        g.add(String(x0 - 4, y + 2, quebrar(it['rotulo'], FONTE, 7.4, x0 - 8, 1)[0] if it['rotulo'] else '', fontName=FONTE, fontSize=7.4, fillColor=TEXTO, textAnchor='end'))
        g.add(Rect(x0, y, max(1.5, area * it['n'] / float(maximo)), 9.5, fillColor=_cor(cor), strokeColor=_cor(cor)))
        g.add(String(x0 + max(1.5, area * it['n'] / float(maximo)) + 3, y + 2, '%d (%s%%)' % (it['n'], ('%.1f' % (it.get('pct') or 0)).replace('.', ',')), fontName=FONTE, fontSize=7, fillColor=LINHA))
    d.add(g)
    return d


def colunas(itens, largura=360, altura=120, cor='#1565c0'):
    """Colunas verticais (evolução por mês ou dia da semana)."""
    d = Drawing(largura, altura)
    g = Group()
    if not itens:
        g.add(String(4, altura / 2.0, 'Sem dados no período.', fontName=FONTE, fontSize=8, fillColor=LINHA))
        d.add(g)
        return d
    maximo = max(i['n'] for i in itens) or 1
    larg = (largura - 10) / float(len(itens))
    for k, it in enumerate(itens):
        h = (altura - 34) * it['n'] / float(maximo)
        x = 5 + k * larg + larg * 0.15
        g.add(Rect(x, 18, larg * 0.7, max(1, h), fillColor=_cor(cor), strokeColor=_cor(cor)))
        g.add(String(x + larg * 0.35, 20 + h, str(it['n']), fontName=NEGRITO, fontSize=7, fillColor=TEXTO, textAnchor='middle'))
        g.add(String(x + larg * 0.35, 7, it['rotulo'][:9], fontName=FONTE, fontSize=6.4 if len(itens) > 8 else 7, fillColor=LINHA, textAnchor='middle'))
    d.add(g)
    return d


def piramide_etaria(piramide, maximo, largura=360):
    """Pirâmide etária: mulheres à direita e homens à esquerda, por faixa."""
    alt_l = 15
    H = len(piramide) * alt_l + 22
    d = Drawing(largura, H)
    g = Group()
    meio = largura / 2.0
    lado = meio - 44
    for k, f in enumerate(reversed(piramide)):
        y = H - 20 - (k + 1) * alt_l + 3
        wm, wf = lado * f['M'] / float(maximo), lado * f['F'] / float(maximo)
        g.add(Rect(meio - 30 - wm, y, wm, 10, fillColor=_cor('#1565c0'), strokeColor=_cor('#1565c0')))
        g.add(Rect(meio + 30, y, wf, 10, fillColor=_cor('#c2185b'), strokeColor=_cor('#c2185b')))
        g.add(String(meio, y + 2, f['faixa'], fontName=FONTE, fontSize=7, fillColor=TEXTO, textAnchor='middle'))
        g.add(String(meio - 32 - wm, y + 2, str(f['M']), fontName=FONTE, fontSize=7, fillColor=LINHA, textAnchor='end'))
        g.add(String(meio + 32 + wf, y + 2, str(f['F']), fontName=FONTE, fontSize=7, fillColor=LINHA))
    g.add(String(meio - 60, H - 10, 'Masculino', fontName=NEGRITO, fontSize=8, fillColor=_cor('#1565c0'), textAnchor='middle'))
    g.add(String(meio + 60, H - 10, 'Feminino', fontName=NEGRITO, fontSize=8, fillColor=_cor('#c2185b'), textAnchor='middle'))
    d.add(g)
    return d
