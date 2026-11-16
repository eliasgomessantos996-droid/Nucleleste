"""Gera nucleleste.ico (átomo da marca) em vários tamanhos. Usa Pillow; só roda na máquina de build."""
import math
import os
from PIL import Image, ImageDraw

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def desenhar(t):
    S = 4  # supersampling para bordas suaves
    n = t * S
    img = Image.new('RGBA', (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # fundo: quadrado arredondado em degradê verde
    for y in range(n):
        f = y / n
        cor = (int(23 + (47 - 23) * f), int(61 + (158 - 61) * f), int(37 + (106 - 37) * f), 255)
        d.line([(0, y), (n, y)], fill=cor)
    mascara = Image.new('L', (n, n), 0)
    ImageDraw.Draw(mascara).rounded_rectangle([0, 0, n - 1, n - 1], radius=int(n * .22), fill=255)
    img.putalpha(mascara)
    # órbitas do átomo (3 elipses giradas)
    cx = cy = n / 2
    esp = max(S, int(n * .045))
    for ang in (0, 60, 120):
        orb = Image.new('RGBA', (n, n), (0, 0, 0, 0))
        do = ImageDraw.Draw(orb)
        a, b = n * .40, n * .15
        pts = []
        for i in range(0, 361, 3):
            r = math.radians(i)
            pts.append((cx + a * math.cos(r), cy + b * math.sin(r)))
        do.line(pts, fill=(255, 255, 255, 235), width=esp, joint='curve')
        orb = orb.rotate(ang, center=(cx, cy), resample=Image.BICUBIC)
        img.alpha_composite(orb)
    # núcleo
    r = n * .085
    d = ImageDraw.Draw(img)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 213, 74, 255))
    return img.resize((t, t), Image.LANCZOS)


if __name__ == '__main__':
    tamanhos = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    base = desenhar(256)
    destino = os.path.join(RAIZ, 'nucleleste.ico')
    base.save(destino, sizes=[(t, t) for t in tamanhos])
    desenhar(256).save(os.path.join(RAIZ, 'instalador', 'assistente.png'))
    # imagens do assistente do instalador (BMP): lateral 164x314 e pequena 55x55
    lat = Image.new('RGB', (164, 314))
    dl = ImageDraw.Draw(lat)
    for y in range(314):
        f = y / 313
        dl.line([(0, y), (164, y)], fill=(int(23 + 24 * f), int(61 + 97 * f), int(37 + 69 * f)))
    lat.paste(desenhar(120), (22, 60), desenhar(120))
    lat.save(os.path.join(RAIZ, 'instalador', 'lateral.bmp'))
    peq = Image.new('RGB', (55, 55), (255, 255, 255))
    peq.paste(desenhar(48), (4, 4), desenhar(48))
    peq.save(os.path.join(RAIZ, 'instalador', 'pequena.bmp'))
    print('ícone gerado:', destino, os.path.getsize(destino), 'bytes')
