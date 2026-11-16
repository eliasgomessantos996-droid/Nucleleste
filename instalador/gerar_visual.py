r"""Gera as imagens do instalador (usa Pillow; só roda na máquina de build, chamado pelo build.ps1).

Saída em instalador\visual\:
- lateral.bmp / pequena.bmp: imagens do assistente (lateral 164x314 e cabeçalho 55x55 com a NucleAI);
- anim\lat00..lat15.bmp: quadros do átomo girando na lateral das páginas de boas-vindas e de conclusão;
- anim\peq00..peq11.bmp: quadros pequenos (64x64) do átomo girando na página de instalação e na espera.
"""
import math
import os
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

AQUI = os.path.dirname(os.path.abspath(__file__))
SAIDA = os.path.join(AQUI, 'visual')
ANIM = os.path.join(SAIDA, 'anim')
S = 3                                  # supersampling: bordas suaves

VERDE_ESCURO = (23, 61, 37)
VERDE = (37, 95, 57)
VERDE_CLARO = (47, 158, 106)
MENTA = (191, 232, 205)
OURO = (255, 213, 74)
BRANCO = (255, 255, 255)


def fonte(tam, negrito=False):
    for nome in (('segoeuib.ttf' if negrito else 'segoeui.ttf'), 'arial.ttf'):
        try:
            return ImageFont.truetype(nome, int(tam * S))
        except OSError:
            continue
    return ImageFont.load_default()


def degrade(w, h):
    img = Image.new('RGB', (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        f = y / (h - 1)
        d.line([(0, y), (w, y)], fill=(int(VERDE_ESCURO[0] + (VERDE_CLARO[0] - VERDE_ESCURO[0]) * f * .75),
                                       int(VERDE_ESCURO[1] + (VERDE_CLARO[1] - VERDE_ESCURO[1]) * f * .75),
                                       int(VERDE_ESCURO[2] + (VERDE_CLARO[2] - VERDE_ESCURO[2]) * f * .75)))
    return img


def ponto_orbita(cx, cy, a, b, ang_orbita, t):
    """Ponto da elipse (semi-eixos a, b) girada `ang_orbita` graus, no parâmetro t (radianos)."""
    x, y = a * math.cos(t), b * math.sin(t)
    r = math.radians(ang_orbita)
    return cx + x * math.cos(r) - y * math.sin(r), cy + x * math.sin(r) + y * math.cos(r)


def orbita(d, cx, cy, a, b, ang, cor, larg):
    pts = [ponto_orbita(cx, cy, a, b, ang, math.radians(i)) for i in range(0, 361, 4)]
    d.line(pts, fill=cor, width=max(1, int(larg)), joint='curve')


def atomo(img, cx, cy, a, quadro, total, larg_orbita, cor_orbita=(255, 255, 255, 235), eletron_cor=BRANCO, brilho=True):
    """Átomo de 3 órbitas com um elétron em cada uma; `quadro/total` define a volta (o laço é perfeito)."""
    n = img.size[0]
    b = a * .36
    camada = Image.new('RGBA', img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(camada)
    for ang in (0, 60, 120):
        orbita(d, cx, cy, a, b, ang, cor_orbita, larg_orbita)
    if brilho:
        halo = camada.filter(ImageFilter.GaussianBlur(radius=max(2, a * .05)))
        img.alpha_composite(halo)
    img.alpha_composite(camada)
    d = ImageDraw.Draw(img)
    base = 2 * math.pi * quadro / total
    r_e = max(2.5, a * .058)
    for k, ang in enumerate((0, 60, 120)):
        x, y = ponto_orbita(cx, cy, a, b, ang, base + k * 2 * math.pi / 3)
        if brilho:
            d.ellipse([x - r_e * 2.1, y - r_e * 2.1, x + r_e * 2.1, y + r_e * 2.1], fill=eletron_cor[:3] + (60,))
        d.ellipse([x - r_e, y - r_e, x + r_e, y + r_e], fill=eletron_cor)
    # núcleo que pulsa
    pulso = 1 + .18 * math.sin(base)
    r = a * .125 * pulso
    if brilho:
        d.ellipse([cx - r * 2.2, cy - r * 2.2, cx + r * 2.2, cy + r * 2.2], fill=OURO + (55,))
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=OURO + (255,))


def robo(img, cx, cy, r, fundo=(47, 138, 85)):
    """Rosto da NucleAI (mesmo desenho do avatar do sistema): robô sorridente com órbitas de átomo."""
    d = ImageDraw.Draw(img)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fundo + (255,))
    orb = Image.new('RGBA', img.size, (0, 0, 0, 0))
    do = ImageDraw.Draw(orb)
    for ang in (0, 60, 120):
        orbita(do, cx, cy, r * .86, r * .32, ang, MENTA + (215,), max(1, r * .05))
    # recorta as órbitas no círculo
    mascara = Image.new('L', img.size, 0)
    ImageDraw.Draw(mascara).ellipse([cx - r, cy - r, cx + r, cy + r], fill=255)
    orb.putalpha(Image.composite(orb.getchannel('A'), Image.new('L', img.size, 0), mascara))
    img.alpha_composite(orb)
    d = ImageDraw.Draw(img)
    # antena, cabeça, orelhas, olhos e sorriso
    d.line([cx, cy - r * .38, cx, cy - r * .56], fill=BRANCO, width=max(1, int(r * .06)))
    d.ellipse([cx - r * .09, cy - r * .70, cx + r * .09, cy - r * .52], fill=OURO + (255,))
    d.rounded_rectangle([cx - r * .50, cy - r * .38, cx + r * .50, cy + r * .44], radius=r * .28, fill=BRANCO)
    d.rounded_rectangle([cx - r * .60, cy - r * .08, cx - r * .48, cy + r * .24], radius=r * .06, fill=MENTA)
    d.rounded_rectangle([cx + r * .48, cy - r * .08, cx + r * .60, cy + r * .24], radius=r * .06, fill=MENTA)
    for sx in (-1, 1):
        ex, ey, er = cx + sx * r * .21, cy - r * .02, r * .11
        d.ellipse([ex - er, ey - er, ex + er, ey + er], fill=VERDE_ESCURO)
        d.ellipse([ex + er * .1, ey - er * .6, ex + er * .6, ey - er * .1], fill=BRANCO)
    d.arc([cx - r * .24, cy + r * .04, cx + r * .24, cy + r * .34], start=20, end=160, fill=VERDE_ESCURO, width=max(1, int(r * .07)))
    for sx in (-1, 1):
        d.ellipse([cx + sx * r * .33 - r * .06, cy + r * .17 - r * .06, cx + sx * r * .33 + r * .06, cy + r * .17 + r * .06],
                  fill=(255, 180, 168, 170))


def estrelas(img, semente, n=34):
    rnd = random.Random(semente)
    d = ImageDraw.Draw(img)
    w, h = img.size
    for _ in range(n):
        x, y = rnd.randint(0, w), rnd.randint(0, h)
        r = rnd.choice((1, 1, 1, 2)) * S * .5
        d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, rnd.randint(25, 70)))


def texto_centro(img, y, texto, tam, cor, negrito=False):
    d = ImageDraw.Draw(img)
    f = fonte(tam, negrito)
    box = d.textbbox((0, 0), texto, font=f)
    d.text(((img.size[0] - (box[2] - box[0])) / 2 - box[0], y - box[1]), texto, font=f, fill=cor)


def quadro_lateral(i, total=16):
    w, h = 164 * S, 314 * S
    img = degrade(w, h).convert('RGBA')
    estrelas(img, 7)
    texto_centro(img, 16 * S, 'NUCLELESTE', 14, BRANCO + (255,), negrito=True)
    texto_centro(img, 36 * S, 'Recepção · Medicina Nuclear', 7.2, MENTA + (255,))
    atomo(img, w / 2, 120 * S, 62 * S, i, total, 3.2 * S)
    robo(img, w / 2, 233 * S, 31 * S)
    texto_centro(img, 272 * S, 'NucleAI', 13, BRANCO + (255,), negrito=True)
    texto_centro(img, 292 * S, 'sua assistente de ajuda', 7.2, MENTA + (255,))
    return img.convert('RGB').resize((164, 314), Image.LANCZOS)


def quadro_pequeno(i, total=12, fundo=BRANCO):
    w = 64 * S
    img = Image.new('RGBA', (w, w), fundo + (255,))
    atomo(img, w / 2, w / 2, 27 * S, i, total, 2.4 * S, cor_orbita=VERDE_CLARO + (255,), eletron_cor=VERDE + (255,), brilho=False)
    return img.convert('RGB').resize((64, 64), Image.LANCZOS)


def cabecalho():
    """Imagem do cabeçalho do assistente (55x55): a NucleAI sobre o verde do cabeçalho."""
    w = 55 * S
    img = Image.new('RGBA', (w, w), VERDE + (255,))
    robo(img, w / 2, w / 2, 25 * S)
    return img.convert('RGB').resize((55, 55), Image.LANCZOS)


def main():
    os.makedirs(ANIM, exist_ok=True)
    for i in range(16):
        quadro_lateral(i).save(os.path.join(ANIM, 'lat%02d.bmp' % i))
    for i in range(12):
        quadro_pequeno(i).save(os.path.join(ANIM, 'peq%02d.bmp' % i))
    quadro_lateral(0).save(os.path.join(SAIDA, 'lateral.bmp'))
    cabecalho().save(os.path.join(SAIDA, 'pequena.bmp'))
    print('imagens do instalador geradas em', SAIDA)


if __name__ == '__main__':
    main()
