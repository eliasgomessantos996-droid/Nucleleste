"""Log de trocas de modelo da NucleAI IA em formato JSONL."""
from __future__ import annotations

import json
import os
import tempfile
import threading
import uuid
from datetime import date, datetime, timedelta

from .db import agora

_lock = threading.Lock()
ARQUIVO_NOME = 'trocas.jsonl'
CLASSIFICACOES_VALIDAS = ('Natural', 'Estranha', '')


def _pasta_dados(db=None):
    if db is not None:
        try:
            caminho = db.execute('PRAGMA database_list').fetchone()[2]
            if caminho:
                return os.path.dirname(os.path.abspath(caminho))
        except Exception:
            pass
    try:
        from flask import current_app, has_app_context
        if has_app_context() and 'PASTA_DADOS' in current_app.config:
            return current_app.config['PASTA_DADOS']
    except Exception:
        pass
    return None


def caminho_arquivo(db=None):
    pasta = _pasta_dados(db)
    return os.path.join(pasta, 'nucleai', ARQUIVO_NOME) if pasta else None


def registrar_troca(db, de, para, motivo, situacao='tentativa'):
    """Grava cada troca como uma linha JSON (JSONL, UTF-8) de forma segura entre threads.

    Campos: id (único), quando (data e hora local), de, para, motivo, situacao,
    classificacao ('', 'Natural' ou 'Estranha'), classificado_por, classificado_em.
    """
    caminho = caminho_arquivo(db)
    if not caminho:
        return None

    registro = {
        'id': uuid.uuid4().hex,
        'quando': agora(),
        'de': str(de or ''),
        'para': str(para or ''),
        'motivo': str(motivo or ''),
        'situacao': str(situacao or ''),
        'classificacao': '',
        'classificado_por': '',
        'classificado_em': '',
    }

    with _lock:
        pasta = os.path.dirname(caminho)
        os.makedirs(pasta, exist_ok=True)
        with open(caminho, 'a', encoding='utf-8') as f:
            f.write(json.dumps(registro, ensure_ascii=False) + '\n')

    return registro


def _ler_todos(caminho):
    """Lê todas as linhas válidas do arquivo JSONL, tolerando linhas corrompidas."""
    if not caminho or not os.path.isfile(caminho):
        return []
    registros = []
    with open(caminho, 'r', encoding='utf-8', errors='replace') as f:
        for linha in f:
            linha = linha.strip()
            if not linha:
                continue
            try:
                obj = json.loads(linha)
                if not isinstance(obj, dict):
                    continue
                if 'id' not in obj or not obj['id']:
                    continue
                registros.append({
                    'id': str(obj.get('id', '')),
                    'quando': str(obj.get('quando', '')),
                    'de': str(obj.get('de', '')),
                    'para': str(obj.get('para', '')),
                    'motivo': str(obj.get('motivo', '')),
                    'situacao': str(obj.get('situacao', '')),
                    'classificacao': str(obj.get('classificacao', '') or ''),
                    'classificado_por': str(obj.get('classificado_por', '') or ''),
                    'classificado_em': str(obj.get('classificado_em', '') or ''),
                })
            except (json.JSONDecodeError, ValueError, UnicodeDecodeError):
                continue
    return registros


def listar(db=None, periodo=None, modelo=None, classificacao=None, filtros=None):
    """Lista as trocas registradas com filtros opcionais (período, modelo, classificação).

    Tolerante a linha corrompida na leitura. Ordena da mais recente para a mais antiga.
    """
    if isinstance(periodo, dict):
        filtros = periodo
        periodo = None
    if filtros and isinstance(filtros, dict):
        periodo = periodo or filtros.get('periodo')
        modelo = modelo or filtros.get('modelo')
        classificacao = classificacao or filtros.get('classificacao')

    caminho = caminho_arquivo(db)
    with _lock:
        itens = _ler_todos(caminho)

    if periodo and str(periodo).strip() not in ('todos', 'todas', 'tudo', ''):
        periodo_s = str(periodo).strip()
        hoje = date.today()
        if periodo_s in ('hoje', 'dia', '1'):
            data_str = hoje.strftime('%Y-%m-%d')
            itens = [i for i in itens if i.get('quando', '').startswith(data_str)]
        elif periodo_s in ('7d', '7', 'semana'):
            limite = (hoje - timedelta(days=7)).strftime('%Y-%m-%d')
            itens = [i for i in itens if i.get('quando', '')[:10] >= limite]
        elif periodo_s in ('30d', '30', 'mes'):
            limite = (hoje - timedelta(days=30)).strftime('%Y-%m-%d')
            itens = [i for i in itens if i.get('quando', '')[:10] >= limite]
        else:
            itens = [i for i in itens if i.get('quando', '').startswith(periodo_s)]

    if modelo and str(modelo).strip() not in ('todos', 'todas', 'tudo', ''):
        mod_s = str(modelo).strip()
        itens = [i for i in itens if mod_s in (i.get('de'), i.get('para'))]

    if classificacao and str(classificacao).strip() not in ('todos', 'todas', 'tudo', ''):
        c_s = str(classificacao).strip()
        if c_s in ('pendente', 'sem', 'vazio', 'nao_classificado'):
            itens = [i for i in itens if not i.get('classificacao')]
        elif c_s in ('Natural', 'Estranha'):
            itens = [i for i in itens if i.get('classificacao') == c_s]

    itens.sort(key=lambda x: x.get('quando', ''), reverse=True)
    return itens


def classificar(db, id, valor, por):
    """Atualiza a classificação de uma troca de forma atômica (arquivo temporário + os.replace)."""
    valor_norm = str(valor or '').strip()
    if valor_norm not in CLASSIFICACOES_VALIDAS:
        raise ValueError('Classificação inválida. Use "Natural" ou "Estranha".')

    caminho = caminho_arquivo(db)
    if not caminho or not os.path.isfile(caminho):
        raise ValueError('Troca não encontrada.')

    target_id = str(id or '').strip()
    if not target_id:
        raise ValueError('ID da troca não informado.')

    with _lock:
        itens = _ler_todos(caminho)
        achou = False
        registro_alterado = None
        for item in itens:
            if item.get('id') == target_id:
                item['classificacao'] = valor_norm
                item['classificado_por'] = str(por or '') if valor_norm else ''
                item['classificado_em'] = agora() if valor_norm else ''
                achou = True
                registro_alterado = item
                break

        if not achou:
            raise ValueError('Troca não encontrada.')

        pasta = os.path.dirname(caminho)
        os.makedirs(pasta, exist_ok=True)
        tmp = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=pasta, delete=False, newline='\n') as f:
                tmp = f.name
                for item in itens:
                    f.write(json.dumps(item, ensure_ascii=False) + '\n')
            os.replace(tmp, caminho)
        finally:
            if tmp and os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass

    return registro_alterado


def contadores(db=None):
    """Devolve contadores das trocas: total, naturais, estranhas e pendentes."""
    todos = listar(db)
    total = len(todos)
    naturais = sum(1 for i in todos if i.get('classificacao') == 'Natural')
    estranhas = sum(1 for i in todos if i.get('classificacao') == 'Estranha')
    pendentes = sum(1 for i in todos if not i.get('classificacao'))
    return {
        'total': total,
        'naturais': naturais,
        'estranhas': estranhas,
        'pendentes': pendentes,
    }
