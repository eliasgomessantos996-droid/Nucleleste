"""Laudos em Word do paciente: encontra, pelo nome, o arquivo do laudo numa pasta escolhida pela gestão.

Os arquivos têm nomes livres, como os da pasta de laudos da clínica:
    3F DEG - ANA CELIA DA FONSECA SERAFIM.doc      3F RAD- LUANA KARINE RUAS DE OLIVEIRA.docx
    08.03.2023 JANIA NÚBIA SANTOS MENDES.docx       09.03.2022 - KETHIZA PESSOA PASCOAL - RAD 2.docx
    3F NORMAL.doc   (modelo, sem nome)             4.docx   (sem nome)
`interpretar` separa o que é DATA (dd.mm.aaaa), o que é CÓDIGO (3F, DEG, RAD, números...) e o que é NOME. `buscar` compara
o nome com o do paciente e ordena os candidatos. A pasta é lida só para leitura e só se abre arquivo que esteja dentro dela.
"""
from __future__ import annotations

import os
import re
import time
import unicodedata
from datetime import date

EXTENSOES = ('.doc', '.docx', '.docm', '.rtf')
LIGACOES = {'DE', 'DA', 'DO', 'DAS', 'DOS', 'E'}
# palavras que os arquivos usam como código/tipo do laudo e que não fazem parte do nome da pessoa
CODIGOS = {'DEG', 'RAD', 'NORMAL', 'LAUDO', 'LAUDOS', 'COPIA', 'MODELO', 'ASSINADO', 'ASSINADA', 'FINAL', 'REVISADO'}
PROFUNDIDADE = 3
MAX_ARQUIVOS = 60000
VALIDADE_CACHE = 90
_cache = {}


def sem_acento(txt):
    return unicodedata.normalize('NFKD', txt or '').encode('ascii', 'ignore').decode().upper()


_DATA = re.compile(r'(?<!\d)(\d{1,2})[./\-](\d{1,2})[./\-](\d{4}|\d{2})(?!\d)')


def _data_valida(d, m, a):
    a = int(a)
    if a < 100:
        a += 2000
    try:
        return date(a, int(m), int(d))
    except ValueError:
        return None


def interpretar(nome_arquivo):
    """{'nome': 'ANA CELIA ...', 'palavras': [...], 'data': date|None, 'codigos': ['3F', 'DEG']} de um nome de arquivo."""
    base = os.path.splitext(os.path.basename(nome_arquivo))[0]
    texto = sem_acento(base).replace('_', ' ')
    data = None
    achada = _DATA.search(texto)
    if achada:
        data = _data_valida(*achada.groups())
        texto = texto[:achada.start()] + ' ' + texto[achada.end():]
    texto = re.sub(r'(?<!\d)\d{1,2}[./\-]\d{1,2}[./\-]\d{1,3}(?!\d)', ' ', texto)   # data truncada (ex.: 04.04.202): é data, não nome
    codigos, palavras = [], []
    for t in re.findall(r'[A-Z0-9]+', texto):
        if re.fullmatch(r'\d+[A-Z]?', t) or t in CODIGOS:
            codigos.append(t)
        elif re.fullmatch(r'[A-Z]{2,}', t) or t in LIGACOES:
            palavras.append(t)
    palavras_nome = [p for p in palavras if p not in LIGACOES]
    return {'nome': ' '.join(palavras), 'palavras': palavras_nome, 'data': data, 'codigos': codigos}


def palavras_do_nome(nome):
    return [t for t in re.findall(r'[A-Z]+', sem_acento(nome)) if t not in LIGACOES and len(t) > 1]


def pontuar(nome_paciente, nome_arquivo):
    """(cobertura, extras) ou None. cobertura = parte do nome do paciente achada no arquivo; extras = palavras do arquivo
    que não são do paciente. Só conta se o primeiro nome do paciente está no arquivo e a cobertura é de pelo menos 60%."""
    p = palavras_do_nome(nome_paciente)
    f = set(interpretar(nome_arquivo)['palavras'])
    if not p or not f or p[0] not in f:
        return None
    achadas = sum(1 for x in p if x in f)
    cobertura = achadas / len(p)
    if cobertura < 0.6 or (len(p) > 1 and achadas < 2):
        return None
    return cobertura, len(f - set(p))


def _varrer(pasta):
    """[(caminho relativo, nome, mtime)] dos documentos Word da pasta (até PROFUNDIDADE níveis, sem links simbólicos)."""
    agora = time.time()
    guardado = _cache.get(pasta)
    if guardado and agora - guardado[0] < VALIDADE_CACHE:
        return guardado[1]
    achados = []

    def andar(dir_abs, rel, nivel):
        if len(achados) >= MAX_ARQUIVOS:
            return
        try:
            with os.scandir(dir_abs) as it:
                for e in it:
                    try:
                        if e.is_symlink():
                            continue
                        if e.is_dir(follow_symlinks=False):
                            if nivel < PROFUNDIDADE:
                                andar(e.path, os.path.join(rel, e.name), nivel + 1)
                        elif e.is_file(follow_symlinks=False) and e.name.lower().endswith(EXTENSOES) and not e.name.startswith('~$'):
                            achados.append((os.path.join(rel, e.name), e.name, e.stat().st_mtime))
                    except OSError:
                        continue
        except OSError:
            return

    andar(pasta, '', 0)
    _cache[pasta] = (agora, achados)
    return achados


def limpar_cache():
    _cache.clear()


def buscar(pasta, nome_paciente, data=None, limite=40):
    """Candidatos (melhores primeiro): nome mais completo e sem palavras sobrando; depois a data mais próxima da pedida."""
    candidatos = []
    for rel, nome, mtime in _varrer(pasta):
        pt = pontuar(nome_paciente, nome)
        if pt is None:
            continue
        info = interpretar(nome)
        quando = info['data'] or date.fromtimestamp(mtime)
        distancia = abs((quando - data).days) if data else 0
        candidatos.append({'rel': rel, 'nome': nome, 'cobertura': pt[0], 'extras': pt[1], 'data': info['data'],
                           'modificado': date.fromtimestamp(mtime), 'distancia': distancia,
                           'exato': pt[0] == 1 and pt[1] == 0})
    candidatos.sort(key=lambda c: (-c['cobertura'], c['extras'], c['distancia'], -c['modificado'].toordinal()))
    return candidatos[:limite]


def caminho_seguro(pasta, rel):
    """Caminho absoluto do arquivo `rel` só se ele estiver mesmo dentro de `pasta`, for um documento Word e não for link."""
    if not pasta or not rel or '\x00' in rel:
        return None
    base = os.path.realpath(pasta)
    alvo = os.path.realpath(os.path.join(base, rel))
    try:
        if os.path.commonpath([base, alvo]) != base:
            return None
    except ValueError:
        return None
    if not alvo.lower().endswith(EXTENSOES) or not os.path.isfile(alvo):
        return None
    return alvo
