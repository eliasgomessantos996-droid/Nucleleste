"""Leitura e agrupamento de arquivos enviados pelo usuário na conversa com a NucleAI.

Formatos aceitos: .xlsx, .xls, .csv e .txt (validados pelo conteúdo, até 5 MB).
PDF é recusado com mensagem clara porque não há biblioteca de extração de texto instalada.
Os cálculos (contagem, soma, média, filtros) são feitos em Python no servidor; a IA só escolhe colunas e operações.
"""
from __future__ import annotations

import csv
import io
import math
import os
import re
import unicodedata
from collections import defaultdict
from datetime import date, datetime

import openpyxl
import xlrd

from . import anexos

ARQUIVO_MAX = 5 * 1024 * 1024
MAX_LINHAS = 20_000
MAX_COLUNAS = 60
MAX_AMOSTRA = 5
MAX_GRUPOS = 200
MAX_TEXTO_PLANO = 4000
ORIGEM_ANEXO = 'chat_ia'

MIME_XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
MIME_XLS = 'application/vnd.ms-excel'
MIME_CSV = 'text/csv'
MIME_TXT = 'text/plain'

TIPOS_ACEITOS = {
    MIME_XLSX: 'xlsx',
    MIME_XLS: 'xls',
    MIME_CSV: 'csv',
    MIME_TXT: 'txt',
}


class ErroArquivo(ValueError):
    """Erro de validação ou leitura de arquivo enviado ao chat."""


def _normalizar(txt):
    s = unicodedata.normalize('NFKD', str(txt or ''))
    return ''.join(c for c in s if not unicodedata.combining(c)).strip().lower()


def _eh_imagem(c):
    if c[:3] == b'\xff\xd8\xff':
        return True
    if c[:8] == b'\x89PNG\r\n\x1a\n':
        return True
    if c[:6] in (b'GIF87a', b'GIF89a'):
        return True
    if c[:4] == b'RIFF' and c[8:12] == b'WEBP':
        return True
    return False


def _decodificar_texto(conteudo):
    for enc in ('utf-8-sig', 'utf-8', 'cp1252', 'latin-1'):
        try:
            return conteudo.decode(enc)
        except UnicodeDecodeError:
            continue
    return None


def validar_arquivo(conteudo, nome=''):
    """Valida o tamanho e o tipo real pelo conteúdo. Devolve o MIME aceito ou levanta ErroArquivo."""
    c = conteudo or b''
    if not c:
        raise ErroArquivo('O arquivo está vazio.')
    if len(c) > ARQUIVO_MAX:
        raise ErroArquivo('O arquivo pode ter no máximo 5 MB.')

    ext = os.path.splitext(str(nome or '').strip().lower())[1]

    if c.lstrip()[:5] == b'%PDF-' or ext == '.pdf':
        raise ErroArquivo('A leitura de PDF não está disponível neste servidor; envie a planilha em .xlsx, .xls ou .csv, ou um arquivo .txt.')

    if _eh_imagem(c):
        raise ErroArquivo('A NucleAI não lê imagens aqui. Envie um arquivo .xlsx, .xls, .csv ou .txt.')

    if c[:4] == b'PK\x03\x04':
        if ext and ext != '.xlsx':
            raise ErroArquivo('O conteúdo do arquivo é um pacote comprimido (.xlsx) e não corresponde à extensão %s.' % ext)
        try:
            wb = openpyxl.load_workbook(io.BytesIO(c), read_only=True, data_only=True)
            try:
                if not wb.sheetnames:
                    raise ErroArquivo('A planilha .xlsx não tem abas.')
            finally:
                wb.close()
        except ErroArquivo:
            raise
        except Exception:
            raise ErroArquivo('O arquivo não é uma planilha .xlsx válida.') from None
        return MIME_XLSX

    if c[:8] == b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1' or c[:2] == b'\x09\x08':
        if ext and ext != '.xls':
            raise ErroArquivo('O conteúdo do arquivo é um documento binário (.xls) e não corresponde à extensão %s.' % ext)
        try:
            wb = xlrd.open_workbook(file_contents=c)
            if wb.nsheets < 1:
                raise ErroArquivo('A planilha .xls não tem abas.')
        except ErroArquivo:
            raise
        except Exception:
            raise ErroArquivo('O arquivo não é uma planilha .xls válida.') from None
        return MIME_XLS

    if ext in ('.xlsx', '.xls'):
        raise ErroArquivo('O conteúdo do arquivo não corresponde a uma planilha Excel válida (%s).' % ext)
    if ext and ext not in ('.csv', '.txt'):
        raise ErroArquivo('Formato não aceito. Envie um arquivo .xlsx, .xls, .csv ou .txt.')

    if b'\x00' in c[:16384]:
        raise ErroArquivo('O arquivo parece ser binário e não é um texto ou CSV válido.')
    texto = _decodificar_texto(c)
    if texto is None:
        raise ErroArquivo('Não foi possível decodificar o texto do arquivo.')
    amostra = texto[:8192]
    if any(ord(ch) < 32 and ch not in '\t\n\r\x0c' for ch in amostra):
        raise ErroArquivo('O arquivo contém caracteres binários inválidos e não é um texto ou CSV válido.')
    if not texto.strip():
        raise ErroArquivo('O arquivo está vazio.')

    return MIME_CSV if ext == '.csv' else MIME_TXT


# ------------------------------------------------------------------ leitura e normalização de células
def _limpar_cabecalho(bruto):
    colunas = []
    vistos = {}
    for idx, v in enumerate(list(bruto)[:MAX_COLUNAS]):
        nome = ' '.join(str(v if v is not None else '').split()) or ('Coluna %d' % (idx + 1))
        n_lower = nome.lower()
        if n_lower in vistos:
            vistos[n_lower] += 1
            nome = '%s (%d)' % (nome, vistos[n_lower])
        else:
            vistos[n_lower] = 1
        colunas.append(nome)
    return colunas


def _valor_celula(v):
    if v is None:
        return None
    if isinstance(v, datetime):
        if v.hour == 0 and v.minute == 0 and v.second == 0:
            return v.date()
        return v
    if isinstance(v, date):
        return v
    if isinstance(v, bool):
        return 'Sim' if v else 'Não'
    if isinstance(v, float):
        if not math.isfinite(v):
            return None
        return int(v) if v.is_integer() else v
    if isinstance(v, int):
        return v
    s = str(v).strip()
    return s if s != '' else None


def _linhas_de_matriz(matriz):
    colunas = None
    linhas = []
    truncado = False
    for row in matriz:
        vals = [_valor_celula(c) for c in list(row)[:MAX_COLUNAS]]
        if not any(v is not None for v in vals):
            continue
        if colunas is None:
            colunas = _limpar_cabecalho(vals)
            continue
        if len(linhas) >= MAX_LINHAS:
            truncado = True
            break
        if len(vals) < len(colunas):
            vals.extend([None] * (len(colunas) - len(vals)))
        else:
            vals = vals[:len(colunas)]
        linhas.append(vals)
    return colunas or [], linhas, truncado


def _ler_xlsx(conteudo, aba=None):
    wb = openpyxl.load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True)
    try:
        abas = list(wb.sheetnames)
        if aba:
            if aba not in abas:
                raise ErroArquivo('Aba «%s» não encontrada. Abas disponíveis: %s.' % (aba, ', '.join(abas)))
            ws = wb[aba]
            aba_usada = aba
        else:
            aba_usada = abas[0]
            ws = wb[aba_usada]
        colunas, linhas, truncado = _linhas_de_matriz(ws.iter_rows(values_only=True))
        return {'abas': abas, 'aba': aba_usada, 'colunas': colunas, 'linhas': linhas, 'truncado': truncado, 'texto_plano': None}
    finally:
        wb.close()


def _celula_xlrd(wb, cell):
    if cell.ctype == xlrd.XL_CELL_EMPTY or cell.ctype == xlrd.XL_CELL_BLANK:
        return None
    if cell.ctype == xlrd.XL_CELL_ERROR:
        return None
    if cell.ctype == xlrd.XL_CELL_BOOLEAN:
        return 'Sim' if cell.value else 'Não'
    if cell.ctype == xlrd.XL_CELL_DATE:
        try:
            dt = xlrd.xldate_as_datetime(cell.value, wb.datemode)
            return dt.date() if (dt.hour == 0 and dt.minute == 0 and dt.second == 0) else dt
        except Exception:
            return cell.value
    if cell.ctype == xlrd.XL_CELL_NUMBER:
        v = cell.value
        return int(v) if isinstance(v, float) and v.is_integer() else v
    return _valor_celula(cell.value)


def _ler_xls(conteudo, aba=None):
    wb = xlrd.open_workbook(file_contents=conteudo)
    abas = list(wb.sheet_names())
    if aba:
        if aba not in abas:
            raise ErroArquivo('Aba «%s» não encontrada. Abas disponíveis: %s.' % (aba, ', '.join(abas)))
        ws = wb.sheet_by_name(aba)
        aba_usada = aba
    else:
        aba_usada = abas[0]
        ws = wb.sheet_by_index(0)
    matriz = ([_celula_xlrd(wb, ws.cell(r, c)) for c in range(min(ws.ncols, MAX_COLUNAS))] for r in range(ws.nrows))
    colunas, linhas, truncado = _linhas_de_matriz(matriz)
    return {'abas': abas, 'aba': aba_usada, 'colunas': colunas, 'linhas': linhas, 'truncado': truncado, 'texto_plano': None}


def _detectar_delimitador(texto):
    amostra = '\n'.join(texto.splitlines()[:10])
    try:
        dialeto = csv.Sniffer().sniff(amostra, delimiters=';,\t|')
        return dialeto.delimiter
    except csv.Error:
        primeira = next((ln for ln in texto.splitlines() if ln.strip()), '')
        for sep in (';', '\t', ',', '|'):
            if sep in primeira:
                return sep
        return ','


def _ler_csv(conteudo):
    texto = _decodificar_texto(conteudo) or ''
    delim = _detectar_delimitador(texto)
    leitor = csv.reader(io.StringIO(texto), delimiter=delim)
    colunas, linhas, truncado = _linhas_de_matriz(leitor)
    return {'abas': [], 'aba': None, 'colunas': colunas, 'linhas': linhas, 'truncado': truncado, 'texto_plano': None}


def _ler_txt(conteudo):
    texto = _decodificar_texto(conteudo) or ''
    linhas_brutas = [ln for ln in texto.splitlines() if ln.strip()]
    for sep in ('\t', ';', '|', ','):
        if len(linhas_brutas) >= 2 and all(sep in ln for ln in linhas_brutas[:3]):
            leitor = csv.reader(io.StringIO(texto), delimiter=sep)
            colunas, linhas, truncado = _linhas_de_matriz(leitor)
            if len(colunas) >= 2 and linhas:
                return {'abas': [], 'aba': None, 'colunas': colunas, 'linhas': linhas, 'truncado': truncado, 'texto_plano': None}
    preview = '\n'.join(linhas_brutas[:80])
    if len(preview) > MAX_TEXTO_PLANO:
        preview = preview[:MAX_TEXTO_PLANO] + '\n…'
    return {'abas': [], 'aba': None, 'colunas': [], 'linhas': [], 'truncado': len(linhas_brutas) > MAX_LINHAS,
            'total_linhas_txt': len(linhas_brutas), 'texto_plano': preview}


def ler_tabela(conteudo, tipo, aba=None):
    if tipo == MIME_XLSX:
        return _ler_xlsx(conteudo, aba=aba)
    if tipo == MIME_XLS:
        return _ler_xls(conteudo, aba=aba)
    if tipo == MIME_CSV:
        return _ler_csv(conteudo)
    if tipo == MIME_TXT:
        return _ler_txt(conteudo)
    raise ErroArquivo('Formato de arquivo não suportado.')


# ------------------------------------------------------------------ detecção de tipos, datas e números
def _para_numero(v):
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v) if math.isfinite(v) else None
    if isinstance(v, str):
        s = v.strip().replace('R$', '').replace('%', '').replace(' ', '')
        if not s:
            return None
        if ',' in s and '.' in s:
            if s.rfind(',') > s.rfind('.'):
                s = s.replace('.', '').replace(',', '.')
            else:
                s = s.replace(',', '')
        elif ',' in s:
            s = s.replace(',', '.')
        try:
            n = float(s)
        except ValueError:
            return None
        return n if math.isfinite(n) else None
    return None


def _para_data(v):
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if not isinstance(v, str):
        return None
    s = v.strip()
    if not s:
        return None
    m = re.fullmatch(r'(\d{4})-(\d{1,2})-(\d{1,2})(?:[T ]\d{1,2}:\d{2}(?::\d{2})?)?', s)
    if m:
        try:
            return date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            return None
    m = re.fullmatch(r'(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?', s)
    if m:
        ano = int(m[3])
        if ano < 100:
            ano += 2000
        try:
            return date(ano, int(m[2]), int(m[1]))
        except ValueError:
            return None
    return None


def _serializar_valor(v):
    if isinstance(v, datetime):
        return v.strftime('%d/%m/%Y %H:%M')
    if isinstance(v, date):
        return v.strftime('%d/%m/%Y')
    return v


def _detectar_tipo_coluna(linhas, idx):
    total = 0
    nums = 0
    datas = 0
    for row in linhas[:300]:
        v = row[idx]
        if v is None:
            continue
        total += 1
        if _para_data(v) is not None:
            datas += 1
        elif _para_numero(v) is not None:
            nums += 1
    if total == 0:
        return 'texto'
    if datas / total >= 0.8:
        return 'data'
    if nums / total >= 0.8:
        return 'numero'
    return 'texto'


# ------------------------------------------------------------------ acesso restrito à conversa do usuário
def buscar_arquivo_conversa(db, uid, anexo_id=None):
    """Busca um arquivo enviado PELO PRÓPRIO usuário `uid` na conversa com a NucleAI."""
    from . import ajuda
    bot = ajuda.bot_id(db)
    if bot is None:
        raise ErroArquivo('Assistente NucleAI não encontrada.')
    tipos = tuple(TIPOS_ACEITOS.keys())
    marcas = ','.join('?' * len(tipos))
    if anexo_id is not None:
        try:
            alvo = int(anexo_id)
        except (TypeError, ValueError):
            raise ErroArquivo('Identificador de arquivo inválido.') from None
        row = db.execute(
            'SELECT id, anexo_id, anexo_tipo, anexo_nome, criado_em FROM chat_mensagens '
            'WHERE id=? AND de_id=? AND para_id=? AND anexo_id IS NOT NULL AND anexo_tipo IN (%s)' % marcas,
            (alvo, uid, bot, *tipos),
        ).fetchone()
    else:
        row = db.execute(
            'SELECT id, anexo_id, anexo_tipo, anexo_nome, criado_em FROM chat_mensagens '
            'WHERE de_id=? AND para_id=? AND anexo_id IS NOT NULL AND anexo_tipo IN (%s) '
            'ORDER BY id DESC LIMIT 1' % marcas,
            (uid, bot, *tipos),
        ).fetchone()
    if row is None:
        raise ErroArquivo('Nenhum arquivo encontrado nesta conversa.')
    conteudo = anexos.ler(anexos.caminho_de(db), row['anexo_id'])
    if conteudo is None:
        raise ErroArquivo('O conteúdo do arquivo não está mais disponível.')
    return dict(row), conteudo


def _indice_coluna(colunas, nome):
    if not nome:
        return None
    alvo = _normalizar(nome)
    for i, c in enumerate(colunas):
        if _normalizar(c) == alvo:
            return i
    raise ErroArquivo('Coluna «%s» não encontrada. Colunas disponíveis: %s.' % (nome, ', '.join(colunas)))


# ------------------------------------------------------------------ ferramentas expostas à IA
def descrever(db, uid, anexo_id=None, aba=None):
    """Implementa `arquivo_ler`: cabeçalho, tipos detectados, total de linhas e amostra."""
    meta, conteudo = buscar_arquivo_conversa(db, uid, anexo_id=anexo_id)
    dados = ler_tabela(conteudo, meta['anexo_tipo'], aba=aba)
    info_arq = {
        'mensagem_id': meta['id'],
        'nome': meta['anexo_nome'] or ('arquivo.' + TIPOS_ACEITOS[meta['anexo_tipo']]),
        'formato': TIPOS_ACEITOS[meta['anexo_tipo']],
    }
    if dados['abas']:
        info_arq['aba'] = dados['aba']
        info_arq['abas'] = dados['abas']

    if dados['texto_plano'] is not None:
        return {
            'arquivo': info_arq,
            'tipo_conteudo': 'texto',
            'total_linhas': dados['total_linhas_txt'],
            'truncado': dados['truncado'],
            'amostra_texto': dados['texto_plano'],
        }

    colunas = dados['colunas']
    linhas = dados['linhas']
    cols_info = [{'nome': c, 'tipo': _detectar_tipo_coluna(linhas, i)} for i, c in enumerate(colunas)]
    amostra = [{colunas[i]: _serializar_valor(row[i]) for i in range(len(colunas))} for row in linhas[:MAX_AMOSTRA]]
    return {
        'arquivo': info_arq,
        'tipo_conteudo': 'tabela',
        'colunas': cols_info,
        'total_linhas': len(linhas),
        'truncado': dados['truncado'],
        'limite_linhas': MAX_LINHAS if dados['truncado'] else None,
        'amostra': amostra,
    }


def _passa_filtro(row, idx, op, valor, valor_fim):
    cel = row[idx]
    if op == 'igual':
        if cel is None:
            return False
        n_cel = _para_numero(cel)
        n_val = _para_numero(valor)
        if n_cel is not None and n_val is not None:
            return abs(n_cel - n_val) < 1e-9
        d_cel = _para_data(cel)
        d_val = _para_data(valor)
        if d_cel is not None and d_val is not None:
            return d_cel == d_val
        return _normalizar(_serializar_valor(cel)) == _normalizar(valor)
    if op == 'contem':
        if cel is None:
            return False
        return _normalizar(valor) in _normalizar(_serializar_valor(cel))
    if op == 'data_entre':
        d_cel = _para_data(cel)
        if d_cel is None:
            return False
        d_ini = _para_data(valor)
        d_fim = _para_data(valor_fim)
        if d_ini and d_cel < d_ini:
            return False
        if d_fim and d_cel > d_fim:
            return False
        return True
    raise ErroArquivo('Operador de filtro inválido: «%s». Use igual, contem ou data_entre.' % op)


def _chave_grupo_valor(v, granularidade):
    if v is None:
        return '(Vazio)'
    if granularidade in ('mes', 'ano', 'dia'):
        d = _para_data(v)
        if d is not None:
            if granularidade == 'mes':
                return d.strftime('%Y-%m')
            if granularidade == 'ano':
                return d.strftime('%Y')
            return d.strftime('%d/%m/%Y')
    return str(_serializar_valor(v))


def _arred(n):
    if isinstance(n, float):
        if n.is_integer():
            return int(n)
        return round(n, 2)
    return n


def agrupar(db, uid, anexo_id=None, aba=None, agrupar_por=None, operacoes=None, filtros=None,
            granularidade_data=None, ordenar='desc', limite=50):
    """Implementa `arquivo_agrupar`: filtra, agrupa e calcula contagem/soma/média/min/max em Python."""
    meta, conteudo = buscar_arquivo_conversa(db, uid, anexo_id=anexo_id)
    dados = ler_tabela(conteudo, meta['anexo_tipo'], aba=aba)
    if dados['texto_plano'] is not None or not dados['colunas']:
        raise ErroArquivo('Este arquivo não possui tabela com colunas para agrupar.')

    colunas = dados['colunas']
    linhas = dados['linhas']

    # 1. Filtros
    filtros_norm = []
    for f in (filtros or []):
        if not isinstance(f, dict):
            continue
        idx = _indice_coluna(colunas, f.get('coluna'))
        op = _normalizar(f.get('op') or f.get('operador') or 'igual')
        if op in ('=', '=='):
            op = 'igual'
        elif op in ('intervalo', 'entre', 'datas', 'data_entre'):
            op = 'data_entre'
        elif op in ('contém', 'contem', 'like'):
            op = 'contem'
        val = f.get('valor') if f.get('valor') is not None else f.get('de')
        val_fim = f.get('valor_fim') if f.get('valor_fim') is not None else f.get('ate')
        if op == 'data_entre' and not (_para_data(val) or _para_data(val_fim)):
            raise ErroArquivo('Informe ao menos uma data válida (DD/MM/AAAA ou AAAA-MM-DD) no filtro de datas.')
        filtros_norm.append((idx, op, val, val_fim))

    filtradas = []
    for row in linhas:
        if all(_passa_filtro(row, idx, op, val, val_fim) for idx, op, val, val_fim in filtros_norm):
            filtradas.append(row)

    # 2. Colunas de agrupamento
    if isinstance(agrupar_por, str):
        agrupar_por = [agrupar_por]
    grp_indices = [_indice_coluna(colunas, c) for c in (agrupar_por or []) if str(c or '').strip()]
    grp_nomes = [colunas[i] for i in grp_indices]
    gran = _normalizar(granularidade_data) if granularidade_data else None
    if gran not in (None, '', 'mes', 'ano', 'dia'):
        raise ErroArquivo('Granularidade de data inválida. Use mes, ano ou dia.')

    # 3. Operações
    ops_norm = []
    for item in (operacoes or []):
        if isinstance(item, str):
            item = {'op': item}
        if not isinstance(item, dict):
            continue
        op = _normalizar(item.get('op') or item.get('operacao') or item.get('tipo') or 'contar')
        if op in ('count', 'contagem', 'qtd'):
            op = 'contar'
        elif op in ('sum', 'somar'):
            op = 'soma'
        elif op in ('avg', 'mean', 'média'):
            op = 'media'
        if op not in ('contar', 'soma', 'media', 'min', 'max'):
            raise ErroArquivo('Operação inválida: «%s». Use contar, soma, media, min ou max.' % op)
        col_nome = item.get('coluna')
        col_idx = None
        if op != 'contar':
            col_idx = _indice_coluna(colunas, col_nome)
        rotulo = str(item.get('rotulo') or '').strip()
        if not rotulo:
            padroes = {'contar': 'Quantidade', 'soma': 'Soma (%s)', 'media': 'Média (%s)', 'min': 'Mín (%s)', 'max': 'Máx (%s)'}
            rotulo = padroes[op] if op == 'contar' else (padroes[op] % colunas[col_idx])
        ops_norm.append((op, col_idx, rotulo))
    if not ops_norm:
        ops_norm = [('contar', None, 'Quantidade')]

    # 4. Agrupamento
    grupos = defaultdict(list)
    for row in filtradas:
        chave = tuple(_chave_grupo_valor(row[i], gran) for i in grp_indices) if grp_indices else ('Total',)
        grupos[chave].append(row)

    saida_linhas = []
    for chave, rows_grp in grupos.items():
        metricas = []
        for op, col_idx, _rot in ops_norm:
            if op == 'contar':
                metricas.append(len(rows_grp))
            else:
                vals = [_para_numero(r[col_idx]) for r in rows_grp]
                vals = [v for v in vals if v is not None]
                if not vals:
                    metricas.append(0)
                elif op == 'soma':
                    metricas.append(_arred(sum(vals)))
                elif op == 'media':
                    metricas.append(_arred(sum(vals) / len(vals)))
                elif op == 'min':
                    metricas.append(_arred(min(vals)))
                elif op == 'max':
                    metricas.append(_arred(max(vals)))
        prefixo = list(chave) if grp_indices else []
        saida_linhas.append(prefixo + metricas)

    # 5. Ordenação e limite
    ord_norm = _normalizar(ordenar or 'desc')
    if ord_norm == 'grupo' and grp_indices:
        saida_linhas.sort(key=lambda r: tuple(str(x).lower() for x in r[:len(grp_indices)]))
    elif ord_norm == 'asc':
        idx_m = len(grp_indices)
        saida_linhas.sort(key=lambda r: (r[idx_m] if isinstance(r[idx_m], (int, float)) else 0))
    else:
        idx_m = len(grp_indices)
        saida_linhas.sort(key=lambda r: (r[idx_m] if isinstance(r[idx_m], (int, float)) else 0), reverse=True)

    lim = max(1, min(int(limite or 50), MAX_GRUPOS))
    truncado_grupos = len(saida_linhas) > lim
    saida_linhas = saida_linhas[:lim]

    colunas_saida = (grp_nomes if grp_indices else []) + [rot for _op, _idx, rot in ops_norm]
    return {
        'arquivo': {
            'mensagem_id': meta['id'],
            'nome': meta['anexo_nome'] or ('arquivo.' + TIPOS_ACEITOS[meta['anexo_tipo']]),
            'aba': dados['aba'],
        },
        'total_lido': len(linhas),
        'total_filtrado': len(filtradas),
        'colunas': colunas_saida,
        'linhas': saida_linhas,
        'truncado_grupos': truncado_grupos,
    }
