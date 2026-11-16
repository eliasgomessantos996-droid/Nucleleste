"""Fichas de impressão: catálogo (gerado a partir da planilha) e montagem dos dados."""
import json
import os
import re
from datetime import date
from functools import lru_cache

from markupsafe import Markup, escape

from . import util
from .db import DOCUMENTOS_OUTROS, config_get, get_db

PASTA_FICHAS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates', 'fichas')

# Questionário de cada ficha PNT, na ordem em que as perguntas aparecem na ficha.
# Cada pergunta: (texto, rótulo da justificativa ou None). Quando a pergunta tem rótulo, a resposta SIM
# abre um campo para escrever o detalhe (ex.: qual mama, qual cicatriz). Sem rótulo, não há campo.
GRAVIDEZ = ('No caso de paciente feminino: está grávida ou há suspeita de gravidez?', None)
ALERGIA = ('Possui alguma alergia ou restrições de medicamentos?', 'Qual(is)?')
INDIVIDUALIDADE = ('Alguma individualidade relacionada a crenças, valores ou religião a ser observada?', 'Observação')
QUESTIONARIOS = {
    'pnt_linfonodo': [
        ('É câncer de mama? Qual mama ou qual câncer?', 'Qual mama ou qual câncer?'),
        ('Possui alguma cicatriz cirúrgica?', 'Qual cicatriz?'),
        ALERGIA,
        GRAVIDEZ,
    ],
    'pnt_mibi': [
        ('Tem sentido dores no peito ultimamente?', None),
        ('Já fez alguma cirurgia cardíaca, cateterismo ou angioplastia?', 'Qual e quando?'),
        ('Diabetes?', None),
        ('Pressão alta?', None),
        ('Colesterol?', None),
        ALERGIA, GRAVIDEZ, INDIVIDUALIDADE,
    ],
    'pnt_ossea': [
        ('Teve alguma fratura no passado ou cirurgia nos ossos? Próteses, pinos, parafusos ou placas de metal?', 'Qual e onde?'),
        ('Sente dores ósseas ou artrite?', None),
        ('Teve alguma queda ou pancada recente?', None),
        ('Alguma biópsia ou cirurgia realizada de mama, próstata ou medula óssea?', 'Qual?'),
        ('Realizou algum tratamento para tumores?', 'Qual?'),
        ALERGIA, GRAVIDEZ, INDIVIDUALIDADE,
    ],
    'pnt_galio': [
        ('Próteses, pinos, parafusos, placas de metal e etc. em alguma parte do corpo?', 'Qual região?'),
        ('Alguma biópsia ou cirurgia realizada de melanoma?', None),
        ('Realizou algum tratamento para tumores?', None),
        ALERGIA, GRAVIDEZ, INDIVIDUALIDADE,
    ],
    'pnt_renal': [
        ('Tem dilatação no rim?', None),
        ('Já teve infecção urinária?', 'Quando?'),
        ('Tem ultrassonografia?', None),
        ALERGIA, GRAVIDEZ, INDIVIDUALIDADE,
    ],
    'pnt_pulmonar': [GRAVIDEZ, ALERGIA, INDIVIDUALIDADE],
    'pnt_spect': [
        ('Tem pressão alta?', None),
        ('Tem diabetes?', None),
        ('Já teve derrame?', None),
        ('Fez tomografia ou ressonância magnética?', None),
        ALERGIA, GRAVIDEZ, INDIVIDUALIDADE,
    ],
    'pnt_tgi': [
        ('Tem algum nódulo? De qual lado?', 'De qual lado? (direito ou esquerdo)'),
        ('Tem ultrassonografia?', None),
        ('Possui alguma alergia ou restrições de medicamentos?', 'Quais?'),
        GRAVIDEZ, INDIVIDUALIDADE,
    ],
    'pnt_paratgi': [
        ('Tem algum nódulo? De qual lado?', 'De qual lado? (direito ou esquerdo)'),
        ('Tem ultrassonografia?', None),
        ('Possui alguma alergia ou restrições de medicamentos?', 'Quais?'),
    ],
}

# Fichas que fazem parte do atendimento (as demais são documentos avulsos).
FICHAS_ATENDIMENTO = [
    'ficha_geral', 'ficha_mibi', 'pnt_mibi', 'pnt_ossea', 'pnt_galio', 'pnt_renal', 'pnt_linfonodo',
    'pnt_pulmonar', 'pnt_spect', 'pnt_tgi', 'pnt_paratgi', 'sae_geral', 'sae_mibi',
    'termo_haroldo', 'dr_haroldo', 'escore_news', 'etiqueta_cliente',
]


@lru_cache(maxsize=1)
def catalogo():
    with open(os.path.join(PASTA_FICHAS, '_manifesto.json'), encoding='utf-8') as fh:
        return {item['slug']: item for item in json.load(fh)}


# ------------------------------------------------------------------ fichas personalizadas (criadas pela clínica)
# Identificadas por "x<id>" para nunca colidir com as fichas da planilha.
CAMPOS_FICHA = [
    ('nome', 'Nome do paciente'), ('cpf', 'CPF'), ('nascimento', 'Data de nascimento'), ('idade', 'Idade'),
    ('profissao', 'Profissão'), ('mae', 'Nome da mãe'), ('endereco', 'Endereço'), ('bairro', 'Bairro'), ('cidade', 'Cidade'),
    ('cep', 'CEP'), ('contato', 'Contato'), ('id_cliente', 'Código (ID) do cliente'), ('convenio', 'Convênio'),
    ('cartao', 'Cartão/matrícula do convênio'), ('exame', 'Exame'), ('titulo', 'Título do exame na ficha'),
    ('medico', 'Médico solicitante'), ('data', 'Data do atendimento'), ('exame_anterior', 'Exame anterior'),
    ('medicamentos', 'Medicamentos em uso'), ('hoje', 'Data de hoje'),
    ('clinica_nome', 'Nome da clínica'), ('clinica_cidade', 'Cidade da clínica'), ('clinica_cnpj', 'CNPJ da clínica'),
    ('linha', 'Linha para preencher (____)'),
]


def eh_extra(slug):
    return bool(re.fullmatch(r'x\d+', slug or ''))


def extras(somente_ativas=True):
    """{slug: linha} das fichas personalizadas."""
    sql = 'SELECT * FROM fichas_extras' + (' WHERE ativa=1' if somente_ativas else '') + ' ORDER BY titulo COLLATE NOCASE'
    return {'x%d' % r['id']: r for r in get_db().execute(sql)}


def slugs_atendimento():
    """Todas as fichas que podem ser impressas num atendimento: as da planilha e as personalizadas ativas."""
    return FICHAS_ATENDIMENTO + list(extras())


def valido(slug):
    return slug in catalogo() or (eh_extra(slug) and slug in extras())


def titulo(slug):
    item = catalogo().get(slug)
    if item:
        return item['titulo']
    if eh_extra(slug):
        r = extras(False).get(slug)
        if r:
            return r['titulo']
    return slug


def _valores_ficha(f):
    v = {k: ('' if f.get(k) is None else str(f.get(k))) for k, _ in CAMPOS_FICHA}
    v['hoje'] = util.data_br(__import__('datetime').date.today().isoformat())
    v['clinica_nome'] = config_get('clinica_nome', '')
    v['clinica_cidade'] = config_get('clinica_cidade', '')
    v['clinica_cnpj'] = config_get('clinica_cnpj', '')
    v['linha'] = '_' * 36
    return v


def renderizar_texto(conteudo, f, previsao=''):
    """Texto simples -> HTML seguro (sem executar nada). Marcações: # título, ## subtítulo, --- linha,
    **negrito**, [ ] caixa, {campo} dados do paciente/atendimento."""
    valores = _valores_ficha(f)
    saida = []
    linhas = (conteudo or '').replace('\r\n', '\n').split('\n')
    indice_previsao = next((i for i, linha in enumerate(linhas)
                           if re.search(r'\{(?:exame|titulo)\}|^\s*\*{0,2}EXAME\s*:', linha, re.I)), None)
    if indice_previsao is None:
        indice_previsao = next((i for i, linha in enumerate(linhas)
                               if re.search(r'\{(?:nome|convenio|data)\}', linha)), 0)
    for i, linha in enumerate(linhas):
        texto = re.sub(r'\{(\w+)\}', lambda m: valores.get(m.group(1), m.group(0)), linha.rstrip())
        if not texto.strip():
            saida.append('<div class="fx-esp"></div>')
            continue
        if texto.strip() == '---':
            saida.append('<hr class="fx-hr">')
            continue
        classe, tag = 'fx-p', 'p'
        if texto.startswith('## '):
            classe, tag, texto = 'fx-h2', 'h3', texto[3:]
        elif texto.startswith('# '):
            classe, tag, texto = 'fx-h1', 'h2', texto[2:]
        html = str(escape(texto))
        html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
        html = html.replace('[ ]', '&#9744;').replace('[x]', '&#9746;').replace('[X]', '&#9746;')
        if previsao and i == indice_previsao:
            html += ' <span class="previsao-laudo" style="font:600 9pt Arial,Calibri,sans-serif;color:#000"> · Previsão de entrega do laudo: %s</span>' % escape(previsao)
        saida.append('<%s class="%s">%s</%s>' % (tag, classe, html, tag))
    return Markup('\n'.join(saida))


def documentos_do_exame(exame):
    """Lista [[slug, cópias], ...] configurada para o exame (ou o padrão de 'outros exames')."""
    if exame is not None:
        try:
            docs = json.loads(exame['documentos'] or '[]')
            if docs:
                return [[d[0], int(d[1])] for d in docs if valido(d[0])]
        except (ValueError, TypeError, IndexError):
            pass
    return [list(d) for d in DOCUMENTOS_OUTROS]


def questionario_do_exame(exame):
    """(slug da ficha PNT, perguntas) do exame: a primeira ficha PNT que ele imprime. (None, []) se não houver."""
    for slug, _ in documentos_do_exame(exame):
        if slug in QUESTIONARIOS:
            return slug, QUESTIONARIOS[slug]
    return None, []


def _sem_quebra(texto):
    """Mantém "( X ) SIM  (   ) NÃO" numa linha só: se não couber, vai inteiro para a linha de baixo (não parte no meio)."""
    return Markup('<span style="white-space:nowrap">%s</span>') % texto.replace('  ', '  ')


def marca_sim_nao(resp):
    if resp == 'SIM':
        return _sem_quebra('( X ) SIM   (   ) NÃO')
    if resp == 'NÃO':
        return _sem_quebra('(   ) SIM   ( X ) NÃO')
    return _sem_quebra('(   ) SIM   (   ) NÃO')


def dados_cliente(cliente, referencia=None):
    c = cliente or {}
    g = c.get if hasattr(c, 'get') else (lambda k, d=None: c[k] if k in c.keys() else d)
    endereco = ' '.join(x for x in [(g('rua') or '').strip(), (g('numero') or '').strip()] if x)
    return {
        'id_cliente': str(g('id') or ''),
        'nome': (g('nome') or '').strip(),
        'cpf': g('cpf') or '',
        'nascimento': util.data_br(g('data_nasc')),
        'idade': util.idade_texto(g('data_nasc'), referencia),
        'profissao': g('profissao') or '',
        'mae': g('nome_mae') or '',
        'endereco': endereco,
        'bairro': g('bairro') or '',
        'cidade': g('cidade') or '',
        'cep': g('cep') or '',
        'contato': g('contato') or '',
        'convenio': g('convenio') or '',
        'cartao': g('cartao_convenio') or '',
    }


def dados_atendimento(at, cliente, exame):
    """Monta o dicionário 'f' usado pelos modelos de ficha de um atendimento."""
    from . import prazo_laudo

    cli = dict(cliente) if cliente else {'id': at['cliente_id'], 'nome': at['cliente_nome'], 'cpf': at['cpf']}
    f = dados_cliente(cli, at['data'])
    prev = ''
    if prazo_laudo.exibir_na_ficha():
        prev = at['previsao_laudo'] or prazo_laudo.previsao(date.fromisoformat(at['data'])).isoformat()
    f.update({
        'nome': (at['cliente_nome'] or f['nome']).strip(),
        'cpf': at['cpf'] or f['cpf'],
        'convenio': at['convenio'] or f['convenio'],
        'data': util.data_br(at['data']),
        'exame': at['exame'] or '',
        'titulo': (exame['titulo_ficha'] if exame is not None and exame['titulo_ficha'] else at['exame']) or '',
        'medico': at['medico'] or '',
        'exame_anterior': at['exame_anterior'] or '',
        'medicamentos': at['medicamentos'] or '',
        'previsao_laudo': util.data_br(prev),
        'interno': bool(at['interno']),
        'interno_local': (at['interno_local'] or '') if at['interno'] else '',
    })
    try:
        respostas = json.loads(at['respostas'] or '{}')
    except ValueError:
        respostas = {}
    manual = bool(respostas.get('manual'))   # preenchido à mão: a ficha sai em branco, sem respostas
    for i in range(1, 10):   # até 9 perguntas por ficha PNT (MIBI tem 8)
        f['r%d' % i] = marca_sim_nao(None if manual else respostas.get('r%d' % i))
        f['o%d' % i] = '' if manual else (respostas.get('o%d' % i) or '')
    return f


def dados_dose(dose, cliente):
    f = dados_cliente(dict(cliente) if cliente else {
        'id': dose['cliente_id'], 'nome': dose['paciente'], 'cpf': dose['cpf'],
        'data_nasc': dose['data_nasc'], 'contato': dose['contato']})
    f.update({
        'nome': (dose['paciente'] or '').strip(),
        'cpf': dose['cpf'] or f['cpf'],
        'nascimento': util.data_br(dose['data_nasc']) or f['nascimento'],
        'idade': util.idade_texto(dose['data_nasc']) or dose['idade'] or '',
        'medicamento': dose['medicamento'] or '',
        'dose': ('%s Mci' % dose['mci']) if (dose['mci'] or '').strip() else '',
        'data_dose': util.data_br(dose['data_dose']),
        'susp_medicacao': util.data_br(dose['susp_medicacao']),
        'dieta': util.data_br(dose['dieta']),
        'medico': dose['medico'] or '',
        'preparo': dose['preparo'] or '',
        'data': util.data_br(dose['data_dose']),
        'exame': dose['medicamento'] or '',
    })
    return f
