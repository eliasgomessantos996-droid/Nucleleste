"""Importa a planilha EXAMES.xlsx (controle de realização de exames, uma aba por mês) para a tabela realizacoes.

    python -m app.cli importar-exames "C:\\caminho\\EXAMES.xlsx"

As abas mudaram de formato ao longo dos anos (idade x data de nascimento, REGISTRO x CODIGO, colunas novas como
SEXO, CID e ELUIÇÃO): as colunas são localizadas pelo nome do cabeçalho de cada aba. A cor da linha (que na planilha
indica o tipo do exame) é guardada à parte em cor_planilha.
"""
import re
from datetime import date, datetime, time

from .db import agora
from .exames_cores import normalizar

ORIGEM = 'planilha:'
COLUNAS = ('data', 'numero', 'codigo', 'cliente_id', 'paciente', 'sexo', 'data_nasc', 'idade', 'peso', 'altura', 'convenio',
           'medico_id', 'medico', 'cid', 'radio', 'eluicao', 'farmaco', 'lote', 'ativ_prescrita', 'ativ_administrada', 'exame',
           'hora_injecao', 'hora_exame', 'responsavel', 'obs', 'cor_planilha', 'origem', 'criado_por', 'criado_em')

# cabeçalho normalizado -> campo
ALIAS = {
    'DATA': 'data', 'CODIGO': 'codigo', 'REGISTRO': 'codigo', 'NOME PACIENTE': 'paciente', 'IDADE': 'idade',
    'DATA DE NASCIMENTO': 'data_nasc', 'PESO': 'peso', 'ALTURA': 'altura', 'CONVENIO': 'convenio',
    'MEDICO SOLICITANTE': 'medico', 'CID': 'cid', 'RADIO': 'radio', 'ELUICAO': 'eluicao', 'FARMACO': 'farmaco', 'LOTE': 'lote',
    'ATIVIDADE PRESCRITA': 'ativ_prescrita', 'ATIVIDADE ADIMINISTRADA': 'ativ_administrada',
    'ATIVIDADE ADMINISTRADA': 'ativ_administrada', 'EXAME': 'exame', 'HORA DA INJECAO': 'hora_injecao',
    'HORA DO EXAME': 'hora_exame', 'RESPONSAVEL': 'responsavel',
}


def _texto(v):
    if v is None:
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    t = re.sub(r'\s+', ' ', str(v)).strip()
    return t or None


def _numero(v):
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v).strip().replace(',', '.')
    try:
        return float(t)
    except ValueError:
        return None


def _data(v):
    """datetime/date ou texto como '04 / 09 / 2026' -> 'AAAA-MM-DD' (None se não for uma data válida)."""
    if isinstance(v, datetime):
        return v.date().isoformat() if 1900 <= v.year <= 2100 else None
    if isinstance(v, date):
        return v.isoformat() if 1900 <= v.year <= 2100 else None
    if isinstance(v, str):
        m = re.search(r'(\d{1,2})\s*[/.\-]\s*(\d{1,2})\s*[/.\-]\s*(\d{2,4})', v)
        if m:
            d, mes, a = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if a < 100:
                a += 2000 if a < 50 else 1900
            if not 1900 <= a <= 2100:
                return None
            try:
                return date(a, mes, d).isoformat()
            except ValueError:
                return None
    return None


def _hora(v):
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.strftime('%H:%M')
    if isinstance(v, time):
        return v.strftime('%H:%M')
    if isinstance(v, (int, float)) and 0 <= v < 1:  # fração do dia do Excel
        minutos = round(v * 24 * 60)
        return '%02d:%02d' % (minutos // 60 % 24, minutos % 60)
    m = re.search(r'(\d{1,2})\s*[:hH]\s*(\d{2})', str(v))
    return '%02d:%02d' % (int(m.group(1)), int(m.group(2))) if m and int(m.group(1)) < 24 and int(m.group(2)) < 60 else None


def _cor_celula(cel):
    try:
        f = cel.fill
        if f is None or f.fill_type != 'solid':
            return None
        cor = f.fgColor
        if cor is not None and cor.type == 'rgb' and isinstance(cor.rgb, str) and len(cor.rgb) == 8:
            return '#' + cor.rgb[2:].upper()
    except AttributeError:
        pass
    return None


def _cabecalho(linhas):
    """(índice da linha do cabeçalho, {campo: coluna}, coluna do número) ou None se a aba não tiver cabeçalho."""
    for i, linha in enumerate(linhas[:6]):
        norm = [normalizar(c.value) if c.value is not None else '' for c in linha]
        if 'NOME PACIENTE' not in norm:
            continue
        mapa, vistos = {}, set()
        for j, nome in enumerate(norm):
            campo = ALIAS.get(nome)
            if nome.startswith('SEXO'):
                campo = 'sexo'
            if not campo:
                continue
            if campo == 'data' and 'data' in vistos:  # algumas abas têm DATA duas vezes: a segunda é o código
                campo = 'codigo'
            if campo in vistos:
                continue
            vistos.add(campo)
            mapa[campo] = j
        return i, mapa
    return None


def _corrigir_datas(regs):
    """Erros de digitação de ano/mês (ex.: 2002 em vez de 2022) destoam muito do resto da aba: a linha recebe a data da
    linha anterior e o valor original fica registrado na observação."""
    if len(regs) < 5:
        return 0
    ordens = sorted(date.fromisoformat(r['data']).toordinal() for r in regs)
    mediana = ordens[len(ordens) // 2]
    corrigidas = 0
    anterior = None
    for r in regs:
        o = date.fromisoformat(r['data']).toordinal()
        if abs(o - mediana) > 120 and anterior:
            r['obs'] = 'Data na planilha: %s (corrigida na importação)' % date.fromisoformat(r['data']).strftime('%d/%m/%Y')
            r['data'] = anterior
            corrigidas += 1
        else:
            anterior = r['data']
    return corrigidas


def importar_xlsx(con, origem, usuario='importação'):
    """Lê o arquivo (caminho ou objeto de arquivo) e carrega as linhas. Troca o que veio de uma importação anterior."""
    import openpyxl
    import warnings
    warnings.filterwarnings('ignore')
    wb = openpyxl.load_workbook(origem, read_only=True, data_only=True)
    clientes = {}
    for r in con.execute('SELECT id, nome FROM clientes'):
        clientes.setdefault(normalizar(r['nome']), []).append(r['id'])
    medicos = {}
    for r in con.execute('SELECT id, nome FROM medicos'):
        medicos.setdefault(normalizar(r['nome']), r['id'])
    quando = agora()
    resumo = {'abas': 0, 'linhas': 0, 'ignoradas': 0, 'com_cliente': 0, 'com_medico': 0, 'datas_corrigidas': 0, 'abas_sem_cabecalho': []}
    linhas_novas = []
    for ws in wb.worksheets:
        todas = [list(r) for r in ws.iter_rows()]
        achado = _cabecalho(todas)
        if not achado:
            resumo['abas_sem_cabecalho'].append(ws.title)
            continue
        i0, mapa = achado
        resumo['abas'] += 1
        ultima_data = None
        sheet_regs = []
        for linha in todas[i0 + 1:]:
            def val(campo):
                j = mapa.get(campo)
                return linha[j].value if j is not None and j < len(linha) else None
            nome = _texto(val('paciente'))
            if not nome or normalizar(nome) == 'NOME PACIENTE':
                continue
            data = _data(val('data')) or ultima_data
            if not data:
                resumo['ignoradas'] += 1
                continue
            ultima_data = data
            nasc = _data(val('data_nasc'))
            idade = _texto(val('idade')) if not nasc else None
            if val('data_nasc') is not None and not nasc and idade is None:
                idade = None
            j_nome = mapa['paciente']
            cli = clientes.get(normalizar(nome), [])
            med = _texto(val('medico'))
            medico_id = medicos.get(normalizar(med)) if med else None
            sexo = (_texto(val('sexo')) or '')[:1].upper()
            numero = _numero(linha[0].value) if linha and linha[0].value is not None else None
            registro = dict(zip(COLUNAS, (data, int(numero) if numero is not None else None, _texto(val('codigo')),
                        cli[0] if len(cli) == 1 else None, nome, None, nasc, idade,
                        _numero(val('peso')), _numero(val('altura')), _texto(val('convenio')), medico_id, med,
                        _texto(val('cid')), _texto(val('radio')), _texto(val('eluicao')), _texto(val('farmaco')),
                        _texto(val('lote')), _texto(val('ativ_prescrita')), _texto(val('ativ_administrada')),
                        _texto(val('exame')), _hora(val('hora_injecao')), _hora(val('hora_exame')),
                        _texto(val('responsavel')), None, _cor_celula(linha[j_nome]), ORIGEM + ws.title.strip(), usuario, quando)))
            sheet_regs.append(registro)
            resumo['linhas'] += 1
            resumo['com_cliente'] += int(len(cli) == 1)
            resumo['com_medico'] += int(medico_id is not None)
        resumo['datas_corrigidas'] += _corrigir_datas(sheet_regs)
        linhas_novas.extend(tuple(r[c] for c in COLUNAS) for r in sheet_regs)
    wb.close()
    if not linhas_novas:
        raise ValueError('Nenhuma linha de exame foi encontrada no arquivo. Confira se é a planilha EXAMES.xlsx.')
    with con:
        con.execute("DELETE FROM realizacoes WHERE origem LIKE ?", (ORIGEM + '%',))
        con.executemany('INSERT INTO realizacoes (%s) VALUES (%s)' % (','.join(COLUNAS), ','.join('?' * len(COLUNAS))), linhas_novas)
    return resumo
