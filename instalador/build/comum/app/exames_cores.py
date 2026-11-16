"""Cores dos exames, como na planilha EXAMES.xlsx: cada linha é pintada conforme o TIPO do exame.

A planilha pinta a linha inteira com uma cor por tipo (óssea = ciano, MIBI = vermelho, DTPA = verde...). Aqui a cor
sai de regras editáveis (tabela exame_cores): cada tipo tem uma cor e uma lista de palavras que identificam o exame
digitado (ex.: "LINF. SENT", "LINFONODO" e "LINFO" são todos "Linfonodo sentinela").
"""
import re
import unicodedata

# (chave, rótulo, cor, palavras que identificam o exame). A ordem importa: o primeiro tipo que combina vence.
CATEGORIAS_PADRAO = [
    ('mibi_pirof', 'Pesquisa de sangramento / MIBI pirofosfato', '#E69138', 'PIROF, SANGRAMENTO, HEMAGIOMA, MECKEL'),
    ('galio', 'Gálio', '#FF00FF', 'GALIO'),
    ('iodo', 'Iodo / PCI', '#FFFF00', 'IODO, IODOTERAPIA, I131, PCI, PCIIODO, PCII131, DOSE'),
    ('mibi', 'MIBI', '#FF0000', 'MIBI'),
    ('dacrio', 'Dacriocintilografia', '#EA9999', 'DACRIO'),
    ('cisterno', 'Cisternocintilografia / fístula liquórica', '#6AA84F', 'CISTERNO, FISTULA, LIQUOR'),
    ('glandulas', 'Glândulas salivares / esvaziamento gástrico', '#C27BA0', 'SALIVAR, GL. SAL, GLAND, ESV, ESVAZ, GASTRIC'),
    ('refluxo', 'Refluxo gastroesofágico', '#FFE599', 'REFLUXO, RGE, PRGE'),
    ('paratgi', 'Paratireoide', '#FF9900', 'PARAT, PTGI, PARTGI'),
    ('tgi', 'Tireoide', '#D5A6BD', 'TGI, TIREO, TIREODE'),
    ('spect', 'SPECT', '#9900FF', 'SPECT'),
    ('pulmonar', 'Pulmonar (ventilação/perfusão)', '#783F04', 'PULMONAR, PULM'),
    ('linfo_mmii', 'Linfocintilografia de membros', '#666666', 'MMII, MMIII, MMSS, MM SS, MII, MEMBRO'),
    ('linfo', 'Linfonodo sentinela', '#D9D9D9', 'LINF, LINFO, LINFONODO, LIFONODO, SENTINELA'),
    ('dmsa', 'DMSA', '#4A86E8', 'DMSA'),
    ('dtpa', 'DTPA', '#B6D7A8', 'DTPA'),
    ('renal', 'Renal', '#6FA8DC', 'RENAL, REN.'),
    ('ossea', 'Óssea', '#00FFFF', 'OSSEA, CTO, MDP'),
    ('hepatica', 'Hepática / fígado e baço', '#741B47', 'HEPAT, FIGADO, BACO'),
]


def normalizar(texto):
    """Maiúsculas, sem acentos e com espaços simples: base de toda comparação de nomes."""
    t = unicodedata.normalize('NFKD', str(texto or '')).encode('ascii', 'ignore').decode().upper()
    return re.sub(r'\s+', ' ', t).strip()


def _combina(palavra, texto):
    # palavras curtas (CTO, RGE, PCI...) só valem como palavra inteira; as longas valem em qualquer parte do texto
    if len(palavra) <= 4:
        return re.search(r'(?<![A-Z0-9])' + re.escape(palavra) + r'(?![A-Z0-9])', texto) is not None
    return palavra in texto


class Classificador:
    """Descobre o tipo (e a cor) de um exame digitado, com cache por texto."""

    def __init__(self, categorias):
        self.cats = []
        for c in categorias:
            palavras = [normalizar(p) for p in (c['padroes'] or '').split(',') if normalizar(p)]
            self.cats.append((c['chave'], c['rotulo'], c['cor'], palavras))
        self._cache = {}

    def tipo(self, exame):
        texto = normalizar(exame)
        if texto in self._cache:
            return self._cache[texto]
        achou = None
        for chave, rotulo, cor, palavras in self.cats:
            if any(_combina(p, texto) for p in palavras):
                achou = (chave, rotulo, cor)
                break
        self._cache[texto] = achou
        return achou

    def cor(self, exame, cor_planilha=None):
        """(chave, rótulo, cor, cor do texto) — sem tipo reconhecido usa a cor que a linha tinha na planilha, se houver."""
        t = self.tipo(exame)
        if t:
            return t[0], t[1], t[2], cor_do_texto(t[2])
        if cor_planilha and cor_planilha.upper() not in ('#FFFFFF', '#FFF', 'FFFFFF'):
            return 'outros', 'Outros', cor_planilha, cor_do_texto(cor_planilha)
        return 'outros', 'Outros', '', ''


def cor_do_texto(fundo):
    """Preto ou branco, conforme a luminância do fundo (legível sobre qualquer cor)."""
    h = (fundo or '').lstrip('#')
    if len(h) == 3:
        h = ''.join(ch * 2 for ch in h)
    if len(h) != 6:
        return ''
    try:
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return ''
    lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return '#000' if lum > 0.5 else '#fff'


def cor_valida(texto):
    return bool(re.fullmatch(r'#[0-9A-Fa-f]{6}', texto or ''))
