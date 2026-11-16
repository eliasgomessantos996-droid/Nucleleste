"""Temas de cor do perfil. Cada usuário escolhe o seu; a escolha vale em qualquer computador onde ele entrar.

Um tema troca as cores de TODO o sistema (barra lateral, barra do topo, botões, tabelas, cartões, fundo da página, átomo e
degradês). O texto e as áreas de leitura continuam claros, para a leitura não mudar. As cores de cada tema ficam em
static/css/tema.css.
"""

# chave: (nome, cor principal, cor de hover, cor suave de realce)
TEMAS = {
    'verde': ('Verde (padrão)', '#255f39', '#2f7a49', '#e8f2ec'),
    'azul': ('Azul', '#1f4e79', '#2a6aa3', '#e6eff8'),
    'vinho': ('Vinho', '#6b1e34', '#8a2b45', '#f5e8ec'),
    'roxo': ('Roxo', '#4b2a7b', '#63399f', '#efe9f7'),
    'terracota': ('Terracota', '#8a4b2a', '#a85d36', '#f6ece6'),
    'grafite': ('Grafite', '#374151', '#4b5563', '#eef0f3'),
    'oceano': ('Oceano', '#0f5c63', '#187f88', '#e1f3f4'),
    'indigo': ('Índigo', '#2b3990', '#3d4fb5', '#e8ebf8'),
}
PADRAO = 'verde'
# brilho: separado da cor. Claro = fundo claro (pastel); escuro = fundo fechado, para quem prefere trabalhar com o sistema escuro
BRILHOS = (('claro', 'Claro'), ('escuro', 'Escuro'))
BRILHO_PADRAO = 'claro'
# lista para o seletor (ordem de exibição)
LISTA = [(chave, nome) for chave, (nome, *_r) in TEMAS.items()]


def valido(chave):
    return chave if chave in TEMAS else PADRAO


def cor_calendario_valida(cor):
    """Cor de fundo do calendário da agenda: #rrggbb ou '' (cor padrão)."""
    import re
    return cor if re.fullmatch(r'#[0-9a-fA-F]{6}', cor or '') else ''


def brilho_valido(chave):
    return chave if chave in dict(BRILHOS) else BRILHO_PADRAO
