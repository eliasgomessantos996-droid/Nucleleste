"""Funções auxiliares: datas, CPF, idade, valores por extenso."""
import re
from datetime import date, datetime

MESES = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho',
         'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']


def hoje_iso():
    return date.today().isoformat()


def para_data(valor):
    """Converte 'dd/mm/aaaa', 'aaaa-mm-dd' (com ou sem hora) ou date em date. None se inválido."""
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    s = str(valor).strip()
    if not s:
        return None
    for fmt in ('%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%d/%m/%Y', '%d/%m/%y', '%d-%m-%Y'):
        try:
            return datetime.strptime(s[:19] if 'T' in s or ':' in s else s, fmt).date()
        except ValueError:
            continue
    return None


def data_iso(valor):
    """Normaliza para 'aaaa-mm-dd'. Se não for data reconhecível, devolve o texto original."""
    d = para_data(valor)
    if d:
        return d.isoformat()
    s = (str(valor).strip() if valor is not None else '')
    return s or None


def data_br(valor):
    """Formata para 'dd/mm/aaaa'. Textos que não são data são devolvidos como estão."""
    if valor in (None, ''):
        return ''
    d = para_data(valor)
    return d.strftime('%d/%m/%Y') if d else str(valor)


def data_extenso(valor=None):
    d = para_data(valor) or date.today()
    return '%d de %s de %d' % (d.day, MESES[d.month - 1].capitalize(), d.year)


def idade(data_nasc, referencia=None):
    """Idade em anos completos na data de referência (padrão: hoje)."""
    nasc = para_data(data_nasc)
    if not nasc:
        return None
    ref = para_data(referencia) or date.today()
    anos = ref.year - nasc.year - ((ref.month, ref.day) < (nasc.month, nasc.day))
    return anos if anos >= 0 else None


def idade_texto(data_nasc, referencia=None):
    i = idade(data_nasc, referencia)
    return '' if i is None else '%d Anos' % i


def so_digitos(s):
    return re.sub(r'\D', '', s or '')


def cpf_valido(cpf):
    n = so_digitos(cpf)
    if len(n) != 11 or n == n[0] * 11:
        return False
    for tam in (9, 10):
        soma = sum(int(n[i]) * (tam + 1 - i) for i in range(tam))
        dig = 11 - soma % 11
        dig = 0 if dig >= 10 else dig
        if dig != int(n[tam]):
            return False
    return True


def cpf_formatado(cpf):
    n = so_digitos(cpf)
    if len(n) != 11:
        return (cpf or '').strip()
    return '%s.%s.%s-%s' % (n[:3], n[3:6], n[6:9], n[9:])


def telefone_padrao(t):
    """Telefone no padrão (XX)9XXXX-XXXX (celular, 11 dígitos); fixo de 10 dígitos vira (XX)XXXX-XXXX.
    Sem número de telefone (ex.: só um nome), o texto digitado é mantido."""
    n = so_digitos(t)
    if len(n) == 13 and n.startswith('55'):   # com o código do Brasil
        n = n[2:]
    if len(n) == 11:
        return '(%s)%s-%s' % (n[:2], n[2:7], n[7:])
    if len(n) == 10:
        return '(%s)%s-%s' % (n[:2], n[2:6], n[6:])
    return (t or '').strip()


def telefone_valido(t):
    """Aceita só telefone com DDD e número (10 ou 11 dígitos; o código 55 do país é opcional)."""
    n = so_digitos(t)
    if len(n) == 13 and n.startswith('55'):
        n = n[2:]
    return len(n) in (10, 11)


def telefone_formatado(t):
    n = so_digitos(t)
    if len(n) == 11:
        return '(%s) %s-%s' % (n[:2], n[2:7], n[7:])
    if len(n) == 10:
        return '(%s) %s-%s' % (n[:2], n[2:6], n[6:])
    return (t or '').strip()


def maiusculas(s):
    return (s or '').strip().upper()


def para_valor(s):
    """'1.234,56' / '1234.56' / 1234.56 -> float (ou None)."""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    s = str(s).strip().replace('R$', '').replace(' ', '')
    if not s:
        return None
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return None


def moeda(v):
    if v is None or v == '':
        return ''
    s = '%.2f' % float(v)
    inteiro, dec = s.split('.')
    neg = inteiro.startswith('-')
    inteiro = inteiro.lstrip('-')
    grupos = []
    while inteiro:
        grupos.insert(0, inteiro[-3:])
        inteiro = inteiro[:-3]
    return ('-' if neg else '') + '.'.join(grupos) + ',' + dec


_UNID = ['', 'um', 'dois', 'três', 'quatro', 'cinco', 'seis', 'sete', 'oito', 'nove', 'dez',
         'onze', 'doze', 'treze', 'quatorze', 'quinze', 'dezesseis', 'dezessete', 'dezoito', 'dezenove']
_DEZ = ['', '', 'vinte', 'trinta', 'quarenta', 'cinquenta', 'sessenta', 'setenta', 'oitenta', 'noventa']
_CEM = ['', 'cento', 'duzentos', 'trezentos', 'quatrocentos', 'quinhentos', 'seiscentos',
        'setecentos', 'oitocentos', 'novecentos']


def _ate_mil(n):
    if n == 0:
        return ''
    if n == 100:
        return 'cem'
    partes = []
    c, resto = divmod(n, 100)
    if c:
        partes.append(_CEM[c])
    if resto < 20:
        if resto:
            partes.append(_UNID[resto])
    else:
        d, u = divmod(resto, 10)
        partes.append(_DEZ[d] + (' e ' + _UNID[u] if u else ''))
    return ' e '.join(partes)


def _inteiro_extenso(n):
    if n == 0:
        return 'zero'
    escalas = [(10 ** 9, 'bilhão', 'bilhões'), (10 ** 6, 'milhão', 'milhões'), (1000, 'mil', 'mil')]
    partes = []
    for valor, sing, plur in escalas:
        q, n = divmod(n, valor)
        if q:
            if valor == 1000:
                partes.append('mil' if q == 1 else _ate_mil(q) + ' mil')
            else:
                partes.append(_ate_mil(q) + ' ' + (sing if q == 1 else plur))
    if n:
        partes.append(_ate_mil(n))
    if len(partes) > 1 and (n < 100 or n % 100 == 0) and n:
        return ', '.join(partes[:-1]) + ' e ' + partes[-1]
    return ', '.join(partes)


def valor_extenso(v):
    """Valor monetário por extenso: 337 -> 'trezentos e trinta e sete reais'."""
    if v is None:
        return ''
    centavos_total = round(float(v) * 100)
    reais, centavos = divmod(centavos_total, 100)
    partes = []
    if reais:
        txt = _inteiro_extenso(reais)
        if reais % 1000000 == 0:
            txt += ' de'
        partes.append(txt + (' real' if reais == 1 else ' reais'))
    if centavos:
        partes.append(_inteiro_extenso(centavos) + (' centavo' if centavos == 1 else ' centavos'))
    return ' e '.join(partes) if partes else 'zero reais'
