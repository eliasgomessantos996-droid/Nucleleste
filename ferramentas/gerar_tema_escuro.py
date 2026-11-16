"""Gera app/static/css/tema-escuro.css: a versão ESCURA do sistema (brilho "escuro" em Minha conta).

Como funciona: lê os CSS e os <style> dos templates e, para cada regra com fundo claro, texto escuro ou borda clara,
escreve uma regra equivalente para `html[data-brilho="escuro"]` com as cores trocadas por variáveis (--sup, --texto, --borda)
ou por uma versão escurecida da mesma cor (o matiz é mantido: um status azul-claro vira um azul-escuro). Assim o modo escuro
acompanha qualquer mudança futura nos CSS, e o tema (a cor) continua valendo.

Uso (na pasta do projeto):  python ferramentas/gerar_tema_escuro.py
Rode de novo sempre que mexer nas cores dos CSS; o arquivo gerado deve ser levado junto.
"""
import colorsys
import glob
import os
import re

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSS = os.path.join(RAIZ, 'app', 'static', 'css')
SAIDA = os.path.join(CSS, 'tema-escuro.css')
PREFIXO = 'html[data-brilho="escuro"] '
EXTRA = os.path.join(CSS, 'tema-escuro-agenda.css')   # parte escrita à mão (agenda): vai copiada para o fim da saída
IGNORAR = {'tema-escuro.css', 'tema-escuro-agenda.css', 'aguarde.css'}

CABECALHO = '''/* GERADO por ferramentas/gerar_tema_escuro.py: não edite à mão (rode o script de novo). */
html[data-brilho="escuro"] {
  color-scheme: dark;
  --sup: color-mix(in srgb, var(--verde-escuro) 50%, #0c0f11);
  --sup-2: color-mix(in srgb, var(--verde-escuro) 68%, #161b1e);
  --texto: #e7ece9; --suave: #a9b5af; --branco: var(--sup); --fundo: var(--sup);
  --borda: color-mix(in srgb, var(--verde-2) 30%, #1a1f22);
  --verde-claro: color-mix(in srgb, var(--verde-2) 24%, var(--sup));
  --ok-fundo: #12301e; --erro-fundo: #3a1714; --aviso-fundo: #3a2c0c; --erro: #ff9d94; --aviso: #ffd27a;
  --pagina-1: color-mix(in srgb, var(--verde-escuro) 40%, #06080a);
  --pagina-2: color-mix(in srgb, var(--verde-escuro) 66%, #0b0e10);
}
html[data-brilho="escuro"] .dash { --d-card: var(--sup); --d-texto: #e7ece9; --d-suave: #a9b5af; --d-linha: color-mix(in srgb, var(--verde-2) 30%, #1a1f22); }
html[data-brilho="escuro"] .chat { --c-dele: color-mix(in srgb, var(--verde-2) 26%, var(--sup-2)); --c-minha: color-mix(in srgb, var(--brilho-2) 55%, var(--sup)); --c-fundo: var(--sup); }
html[data-brilho="escuro"] .chat-balao, html[data-brilho="escuro"] .chat-balao * { color: #f1f5f3; }
html[data-brilho="escuro"] .chat-balao .chat-rodape, html[data-brilho="escuro"] .chat-balao small, html[data-brilho="escuro"] .chat-rodape time { color: #c4d0ca; }
html[data-brilho="escuro"] .chat-citacao span { color: #d3dcd7; }
html[data-brilho="escuro"] .chat-dia { background: color-mix(in srgb, var(--verde-2) 30%, var(--sup-2)); color: #e7ece9; }
html[data-brilho="escuro"] .chat-lista, html[data-brilho="escuro"] .chat-topo, html[data-brilho="escuro"] .chat-form, html[data-brilho="escuro"] .chat-busca-conv, html[data-brilho="escuro"] .chat-resposta { background: var(--sup); }
html[data-brilho="escuro"] .chat-item:hover { background: var(--sup-2); }
html[data-brilho="escuro"] .chat-busca input { background: var(--sup-2); }
html[data-brilho="escuro"] .chat-tag { background: #4a3a10; color: #ffd98a; }
html[data-brilho="escuro"] .chat-busca-texto mark { background: #7a5f12; color: #fff; }
html[data-brilho="escuro"] a { color: var(--brilho); }
html[data-brilho="escuro"] .conteudo h1, html[data-brilho="escuro"] .cabecalho h1 { color: color-mix(in srgb, var(--brilho) 65%, #fff); }
html[data-brilho="escuro"] .hero h1, html[data-brilho="escuro"] .ph-hero h1 { color: #fff; }
html[data-brilho="escuro"] .btn, html[data-brilho="escuro"] .btn:hover { color: #fff; }
html[data-brilho="escuro"] .btn.sec { color: color-mix(in srgb, var(--brilho) 60%, #fff); border-color: color-mix(in srgb, var(--brilho-2) 55%, transparent);
  background-color: var(--sup); background-image: radial-gradient(120px circle at var(--mx, -300px) var(--my, -300px), rgba(var(--brilho-rgb), .25), transparent 65%), linear-gradient(180deg, var(--sup-2), var(--sup)); }
html[data-brilho="escuro"] .btn.sec:hover { background-image: radial-gradient(120px circle at var(--mx, -300px) var(--my, -300px), rgba(var(--brilho-rgb), .32), transparent 65%), linear-gradient(180deg, var(--verde-claro), var(--verde-claro)); }
html[data-brilho="escuro"] .btn.perigo { color: #ff9d94; border-color: rgba(255, 157, 148, .45); background-color: var(--sup);
  background-image: radial-gradient(120px circle at var(--mx, -300px) var(--my, -300px), rgba(255, 120, 110, .2), transparent 65%), linear-gradient(180deg, var(--sup-2), #2a1513); }
html[data-brilho="escuro"] .btn.perigo:hover { background-image: linear-gradient(180deg, #3a1714, #3a1714); }
html[data-brilho="escuro"] .tabela th { background: linear-gradient(180deg, var(--verde-claro), var(--sup-2)); color: color-mix(in srgb, var(--brilho) 70%, #fff); }
html[data-brilho="escuro"] .tabela tbody tr:hover td { background: rgba(var(--brilho-rgb), .1); }
html[data-brilho="escuro"] .cartao, html[data-brilho="escuro"] .indicador, html[data-brilho="escuro"] .tabela-wrap, html[data-brilho="escuro"] .atalhos a {
  border-top-color: color-mix(in srgb, var(--verde-2) 70%, transparent); border-color: var(--borda); }
html[data-brilho="escuro"] dialog { background: var(--sup); color: var(--texto); }
html[data-brilho="escuro"] .menu-alternar { background: var(--sup); color: color-mix(in srgb, var(--brilho) 70%, #fff); }
html[data-brilho="escuro"] .indicador .n, html[data-brilho="escuro"] .etiqueta { color: color-mix(in srgb, var(--brilho) 70%, #fff); }
html[data-brilho="escuro"] input, html[data-brilho="escuro"] select, html[data-brilho="escuro"] textarea { background-color: var(--sup-2); color: var(--texto); border-color: var(--borda); }
html[data-brilho="escuro"] input[readonly] { background-color: var(--sup); }
html[data-brilho="escuro"] ::placeholder { color: var(--suave); }
html[data-brilho="escuro"] .menu .rodape select option, html[data-brilho="escuro"] select option { color: var(--texto); background: var(--sup-2); }
html[data-brilho="escuro"] img.logo, html[data-brilho="escuro"] .login-caixa img { filter: none; }
'''


def hex_rgb(h):
    h = h.lstrip('#')
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def luz(h):
    r, g, b = (x / 255 for x in hex_rgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def saturacao(h):
    r, g, b = hex_rgb(h)
    return max(r, g, b) - min(r, g, b)


HEX = re.compile(r'^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$')


def fundo_escuro(h):
    l = luz(h)
    if l >= .965:
        return 'var(--sup)'
    if l >= .90:
        return 'var(--sup-2)'
    return 'color-mix(in srgb, %s 30%%, var(--sup))' % h


def texto_claro(h):
    l = luz(h)
    if saturacao(h) < 38:
        return 'var(--texto)' if l < .30 else 'var(--suave)'
    return 'color-mix(in srgb, %s 32%%, #ffffff)' % h


def declaracoes(corpo):
    saida = []
    for decl in corpo.split(';'):
        if ':' not in decl:
            continue
        prop, valor = decl.split(':', 1)
        prop, valor = prop.strip().lower(), valor.strip().replace('!important', '').strip()
        if prop in ('background', 'background-color') and HEX.match(valor) and luz(valor) >= .80:
            saida.append('background-color: %s' % fundo_escuro(valor))
        elif prop == 'color' and HEX.match(valor) and luz(valor) <= .45:
            saida.append('color: %s' % texto_claro(valor))
        elif prop == 'color' and re.fullmatch(r'var\(--verde(?:-2)?\)', valor):
            saida.append('color: var(--brilho)')
        elif prop.startswith('border'):
            m = re.search(r'#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b', valor)
            if m and luz(m.group(0)) >= .62 and saturacao(m.group(0)) < 40:
                lado = re.match(r'border(-top|-right|-bottom|-left)?', prop).group(1) or ''
                saida.append('border%s-color: var(--borda)' % lado)
    return saida


def regras(texto):
    """Itera (contexto, seletor, corpo) de regras simples e dentro de @media. Ignora @keyframes e outros."""
    texto = re.sub(r'/\*.*?\*/', '', texto, flags=re.S)
    i, n = 0, len(texto)
    pilha = []
    ini = 0
    while i < n:
        c = texto[i]
        if c == '{':
            cab = texto[ini:i].strip()
            if cab.startswith('@'):
                pilha.append(cab)
                ini = i + 1
            else:
                j = texto.index('}', i)
                yield (pilha[-1] if pilha else None), cab, texto[i + 1:j]
                i = j
                ini = i + 1
        elif c == '}':
            if pilha:
                pilha.pop()
            ini = i + 1
        i += 1


def prefixar(seletor):
    partes, nivel, atual = [], 0, ''
    for ch in seletor:
        if ch in '([':
            nivel += 1
        elif ch in ')]':
            nivel -= 1
        if ch == ',' and nivel == 0:
            partes.append(atual)
            atual = ''
        else:
            atual += ch
    partes.append(atual)
    saida = []
    for p in partes:
        p = p.strip()
        if not p or p.startswith(('from', 'to')) or re.match(r'^\d+%', p) or p.startswith(':root'):
            continue
        saida.append(PREFIXO + re.sub(r'^(html|body)\s*', '', p) if not p.startswith('html') else p)
    return ', '.join(saida)


def main():
    blocos = []
    fontes = [f for f in sorted(glob.glob(os.path.join(CSS, '*.css'))) if os.path.basename(f) not in IGNORAR]
    for f in fontes:
        texto = open(f, encoding='utf-8').read()
        blocos.append((os.path.basename(f), texto))
    for t in sorted(glob.glob(os.path.join(RAIZ, 'app', 'templates', '**', '*.html'), recursive=True)):
        conteudo = open(t, encoding='utf-8').read()
        for m in re.finditer(r'<style[^>]*>(.*?)</style>', conteudo, flags=re.S):
            blocos.append((os.path.relpath(t, RAIZ).replace('\\', '/'), m.group(1)))
    saida, vistos = [], set()
    for nome, texto in blocos:
        regs = []
        for contexto, seletor, corpo in regras(texto):
            decls = declaracoes(corpo)
            if not decls or '{{' in seletor or '{%' in seletor:
                continue
            sel = prefixar(seletor)
            if sel:
                regs.append((contexto, sel, '; '.join(dict.fromkeys(decls))))
        if regs:
            saida.append('\n/* %s */' % nome)
            for contexto, sel, decl in regs:
                chave = (contexto, sel, decl)
                if chave in vistos:
                    continue
                vistos.add(chave)
                linha = '%s { %s; }' % (sel, decl)
                saida.append('%s { %s }' % (contexto, linha) if contexto else linha)
    with open(SAIDA, 'w', encoding='utf-8', newline='\n') as fh:
        extra = ''
        if os.path.exists(EXTRA):
            extra = '\n' + open(EXTRA, encoding='utf-8').read().split('*/', 1)[1].lstrip('\n')
        fh.write(CABECALHO + '\n'.join(saida) + '\n' + extra)
    print('gerado: %s (%d regras)' % (SAIDA, len(vistos)))


if __name__ == '__main__':
    main()
