"""Perfil epidemiológico dos pacientes atendidos (exigido pela ONA): sexo, idade, faixa etária por sexo, procedência (cidade e bairro),
exames, convênios, médicos solicitantes, CID e evolução por mês, calculados com os exames realizados e o cadastro de clientes do próprio sistema."""
from __future__ import annotations

import unicodedata
from collections import Counter, defaultdict
from datetime import date

from . import util

FAIXAS = (('0 a 11', 0, 11), ('12 a 17', 12, 17), ('18 a 29', 18, 29), ('30 a 39', 30, 39), ('40 a 49', 40, 49), ('50 a 59', 50, 59), ('60 a 69', 60, 69),
          ('70 a 79', 70, 79), ('80 ou mais', 80, 200))
DIAS = ('Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo')
SEXO = {'M': 'Masculino', 'F': 'Feminino'}


def _faixa(idade):
    for nome, a, b in FAIXAS:
        if a <= idade <= b:
            return nome
    return None


IMC_ROTULOS = ('Baixo peso (< 18,5)', 'Normal (18,5 a 24,9)', 'Sobrepeso (25 a 29,9)', 'Obesidade (30 ou mais)')
PROCEDENCIA_ROTULOS = ('Mesma cidade da clínica', 'Outras cidades', 'Não informado')
CAPITULOS_CID = {
    'A': 'I - Infecciosas e parasitárias', 'B': 'I - Infecciosas e parasitárias', 'C': 'II - Neoplasias', 'E': 'IV - Endócrinas, nutricionais e metabólicas',
    'F': 'V - Transtornos mentais', 'G': 'VI - Sistema nervoso', 'I': 'IX - Aparelho circulatório', 'J': 'X - Aparelho respiratório',
    'K': 'XI - Aparelho digestivo', 'L': 'XII - Pele', 'M': 'XIII - Osteomuscular', 'N': 'XIV - Geniturinário', 'O': 'XV - Gravidez e parto',
    'P': 'XVI - Perinatal', 'Q': 'XVII - Malformações congênitas', 'R': 'XVIII - Sintomas e achados anormais', 'S': 'XIX - Lesões e envenenamentos',
    'T': 'XIX - Lesões e envenenamentos', 'V': 'XX - Causas externas', 'W': 'XX - Causas externas', 'X': 'XX - Causas externas', 'Y': 'XX - Causas externas',
    'Z': 'XXI - Fatores que influenciam a saúde', 'U': 'XXII - Códigos especiais'}


def _capitulo_cid(cid):
    """Capítulo da CID-10 do código (ex.: 'C50' vira 'II - Neoplasias'); 'Sem CID' se vazio ou inválido."""
    t = ''.join(str(cid or '').split()).replace('.', '').upper()
    if len(t) < 3 or not t[0].isalpha() or not t[1:3].isdigit():
        return 'Sem CID'
    numero = int(t[1:3])
    if t[0] == 'D':
        return 'II - Neoplasias' if numero <= 48 else 'III - Sangue e imunidade'
    if t[0] == 'H':
        return 'VII - Olho' if numero <= 59 else 'VIII - Ouvido'
    return CAPITULOS_CID.get(t[0], 'Sem CID')


def _imc(peso, altura):
    """IMC com peso em kg e altura em m (ou em cm, se passar de 3); None se peso ou altura forem inválidos."""
    try:
        p, a = float(peso), float(altura)
    except (TypeError, ValueError):
        return None
    if a > 3:
        a = a / 100.0
    if not (2 <= p <= 400 and 0.5 <= a <= 2.5):
        return None
    return p / (a * a)


def _faixa_imc(imc):
    if imc < 18.5:
        return IMC_ROTULOS[0]
    if imc < 25:
        return IMC_ROTULOS[1]
    if imc < 30:
        return IMC_ROTULOS[2]
    return IMC_ROTULOS[3]


def _sem_acento(texto):
    t = unicodedata.normalize('NFKD', str(texto or '')).encode('ascii', 'ignore').decode()
    return ' '.join(t.upper().split())


def _cidade_clinica(db):
    """Cidade da clínica (parte antes de ' - ' em config.clinica_cidade)."""
    row = db.execute("SELECT valor FROM config WHERE chave='clinica_cidade'").fetchone()
    valor = row['valor'] if row and row['valor'] else 'Governador Valadares - MG'
    return valor.split(' - ')[0]


def _top(contador, n=10):
    total = sum(contador.values()) or 1
    itens = sorted(contador.items(), key=lambda kv: (-kv[1], kv[0]))
    saida = [{'rotulo': k, 'n': v, 'pct': round(100.0 * v / total, 1)} for k, v in itens[:n]]
    resto = sum(v for _k, v in itens[n:])
    if resto:
        saida.append({'rotulo': 'Outros', 'n': resto, 'pct': round(100.0 * resto / total, 1)})
    return saida


def _limpo(v, padrao='Não informado'):
    t = ' '.join(str(v or '').split())
    return t.upper() if t else padrao


def perfil(db, de, ate):
    """Dicionário do perfil no período (`de` e `ate` são datas)."""
    ini, fim = de.isoformat(), ate.isoformat()
    linhas = db.execute(
        'SELECT r.id, r.data, r.paciente, r.data_nasc, r.convenio, r.medico, r.cid, r.exame, r.cliente_id, r.peso, r.altura, COALESCE(NULLIF(TRIM(c.sexo), ""), r.sexo) AS sexo, c.cidade AS cidade, c.bairro AS bairro, '
        'c.uf AS uf, c.data_nasc AS nasc_cliente FROM realizacoes r LEFT JOIN clientes c ON c.id=r.cliente_id WHERE r.data BETWEEN ? AND ? ORDER BY r.data', (ini, fim)).fetchall()
    total = len(linhas)
    pacientes = {}
    for r in linhas:
        chave = ('c', r['cliente_id']) if r['cliente_id'] else ('n', _limpo(r['paciente']), r['data_nasc'] or '')
        p = pacientes.setdefault(chave, {'exames': 0, 'sexo': r['sexo'] if r['sexo'] in SEXO else None, 'cidade': (r['cidade'] or '').strip(), 'bairro': (r['bairro'] or '').strip(),
                                         'uf': (r['uf'] or '').strip(), 'nasc': r['data_nasc'] or r['nasc_cliente'], 'ref': r['data']})
        p['exames'] += 1
    n_pac = len(pacientes)
    sexo = Counter()
    faixas = {f[0]: {'M': 0, 'F': 0, 'N': 0} for f in FAIXAS}
    idades = []
    cidades, bairros = Counter(), Counter()
    for p in pacientes.values():
        sexo[SEXO.get(p['sexo'], 'Não informado')] += 1
        idade = util.idade(p['nasc'], p['ref']) if p['nasc'] else None
        if idade is not None:
            idades.append(idade)
            f = _faixa(idade)
            if f:
                faixas[f][p['sexo'] if p['sexo'] in SEXO else 'N'] += 1
        cidades[_limpo(p['cidade']) + ((' / ' + p['uf'].upper()) if p['cidade'] and p['uf'] else '')] += 1
        bairros[_limpo(p['bairro'])] += 1
    idades.sort()
    meses, dias = Counter(), Counter()
    exames, convenios, medicos, cids = Counter(), Counter(), Counter(), Counter()
    capitulos, idades_exame, sexo_exame = Counter(), defaultdict(list), defaultdict(Counter)
    imc_adultos, com_peso_altura = [], 0
    for r in linhas:
        meses[r['data'][:7]] += 1
        try:
            dias[DIAS[date.fromisoformat(r['data']).weekday()]] += 1
        except ValueError:
            pass
        nome_exame = _limpo(r['exame'], 'Sem exame')
        exames[nome_exame] += 1
        convenios[_limpo(r['convenio'], 'Sem convênio')] += 1
        medicos[_limpo(r['medico'], 'Sem médico')] += 1
        cids[_limpo(r['cid'], 'Sem CID')] += 1
        capitulos[_capitulo_cid(r['cid'])] += 1
        nasc_exame = r['data_nasc'] or r['nasc_cliente']
        idade_exame = util.idade(nasc_exame, r['data']) if nasc_exame else None
        idades_exame[nome_exame].append(idade_exame)
        sexo_exame[nome_exame][r['sexo'] if r['sexo'] in SEXO else 'N'] += 1
        imc = _imc(r['peso'], r['altura'])
        if imc is not None:
            com_peso_altura += 1
            if idade_exame is not None and idade_exame >= 18:
                imc_adultos.append(imc)
    com_mais = sum(1 for p in pacientes.values() if p['exames'] > 1)

    def pct(n, d):
        return round(100.0 * n / d, 1) if d else None
    piramide = [{'faixa': nome, 'M': faixas[nome]['M'], 'F': faixas[nome]['F'], 'N': faixas[nome]['N'], 'total': sum(faixas[nome].values())} for nome, _a, _b in FAIXAS]
    mediana = (idades[len(idades) // 2] if len(idades) % 2 else (idades[len(idades) // 2 - 1] + idades[len(idades) // 2]) / 2.0) if idades else None
    top_exames = sorted(exames.items(), key=lambda kv: (-kv[1], kv[0]))
    idade_por_exame = []
    for nome, n in top_exames[:10]:
        ids = [i for i in idades_exame[nome] if i is not None]
        idade_por_exame.append({'rotulo': nome, 'n': n, 'media': round(sum(ids) / len(ids), 1) if ids else None})
    exames_por_sexo = [{'rotulo': nome, 'F': sexo_exame[nome]['F'], 'M': sexo_exame[nome]['M'], 'N': sexo_exame[nome]['N']} for nome, _n in top_exames[:8]]
    faixas_imc = Counter(_faixa_imc(v) for v in imc_adultos)
    n_imc = len(imc_adultos)
    cidade_clinica = _sem_acento(_cidade_clinica(db))
    procedencia = Counter()
    for p in pacientes.values():
        cidade_p = _sem_acento(p['cidade'])
        if not cidade_p:
            procedencia['Não informado'] += 1
        elif cidade_p == cidade_clinica:
            procedencia['Mesma cidade da clínica'] += 1
        else:
            procedencia['Outras cidades'] += 1
    return {
        'de': ini, 'ate': fim,'total_exames': total, 'pacientes': n_pac, 'pacientes_com_mais_de_um': com_mais, 'pct_retorno': pct(com_mais, n_pac),
        'sexo': _top(sexo), 'piramide': piramide, 'max_faixa': max([max(f['M'], f['F']) for f in piramide] or [0]) or 1,
        'idade': {'media': round(sum(idades) / len(idades), 1) if idades else None, 'mediana': mediana, 'minima': idades[0] if idades else None,
                  'maxima': idades[-1] if idades else None, 'n': len(idades)},
        'faixas': [{'rotulo': f['faixa'], 'n': f['total'], 'pct': pct(f['total'], sum(x['total'] for x in piramide))} for f in piramide],
        'cidades': _top(cidades), 'bairros': _top(bairros), 'exames': _top(exames), 'convenios': _top(convenios), 'medicos': _top(medicos), 'cids': _top(cids),
        'meses': [{'rotulo': '%s/%s' % (m[5:7], m[:4]), 'n': n} for m, n in sorted(meses.items())],
        'dias': [{'rotulo': d, 'n': dias.get(d, 0)} for d in DIAS],
        'qualidade_dado': [
            {'rotulo': 'Pacientes com sexo informado', 'n': sum(1 for p in pacientes.values() if p['sexo']), 'de': n_pac},
            {'rotulo': 'Pacientes com data de nascimento', 'n': sum(1 for p in pacientes.values() if p['nasc']), 'de': n_pac},
            {'rotulo': 'Pacientes com cidade informada', 'n': sum(1 for p in pacientes.values() if p['cidade']), 'de': n_pac},
            {'rotulo': 'Exames com CID informado', 'n': total - cids.get('Sem CID', 0), 'de': total},
            {'rotulo': 'Exames com médico solicitante', 'n': total - medicos.get('Sem médico', 0), 'de': total},
            {'rotulo': 'Exames com peso e altura', 'n': com_peso_altura, 'de': total}],
        'cid_capitulos': _top(capitulos),
        'imc': [{'rotulo': rot, 'n': faixas_imc[rot], 'pct': pct(faixas_imc[rot], n_imc)} for rot in IMC_ROTULOS],
        'imc_media': round(sum(imc_adultos) / n_imc, 1) if n_imc else None,
        'idade_por_exame': idade_por_exame,
        'exames_por_sexo': exames_por_sexo,
        'procedencia_local': [{'rotulo': rot, 'n': procedencia[rot], 'pct': pct(procedencia[rot], n_pac)} for rot in PROCEDENCIA_ROTULOS],
    }
