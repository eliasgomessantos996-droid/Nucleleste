"""Cliente OpenRouter sem SDK. Credenciais nunca entram no corpo nem nos erros."""
from __future__ import annotations

import json
import os
import tempfile
import time
import urllib.error
import urllib.request

BASE = 'https://openrouter.ai/api/v1/chat/completions'
MODELO_PADRAO = 'google/gemini-2.5-flash'
TIMEOUT_S = 12
TIMEOUT_CONEXAO_S = 3
VAR_CHAVE = 'NUCLELESTE_OPENROUTER_CHAVE'
CHAVE_TESTE = 'chave-de-teste'
CACHE_CONEXAO_S = 10
URL_CONEXAO = 'https://openrouter.ai/'
_cache_conexao = {'momento': None, 'ok': False}


class ErroLLM(Exception):
    """tipo: sem_chave, rede, cota, servidor, indisponivel ou resposta. Erros públicos sem segredos.

    Nas falhas de cota (`tipo='cota'`) o `escopo` diz de onde veio o limite:
      conta_dia / conta_min: limite da CONTA na OpenRouter (os modelos :free dividem o mesmo limite;
                             trocar de modelo não adianta);
      credito:               saldo insuficiente (HTTP 402);
      modelo:                só aquele modelo/provedor está limitado (trocar de modelo costuma resolver).
    `pausa_s` é a dica de espera dada pela OpenRouter (Retry-After / X-RateLimit-Reset), se houver;
    `detalhe` é o motivo textual dado pela OpenRouter (sem segredos), útil para a gerência;
    `retorno` (preenchido por quem pausa o modelo) é a hora em que a IA volta a ser tentada."""

    def __init__(self, tipo, mensagem, tempo_esgotado=False, escopo='', pausa_s=None, detalhe='', retorno=''):
        super().__init__(mensagem)
        self.tipo = tipo
        self.tempo_esgotado = tempo_esgotado
        self.escopo = escopo
        self.pausa_s = pausa_s
        self.detalhe = detalhe
        self.retorno = retorno


def caminho_chave(db=None):
    from flask import current_app, has_app_context
    from .nucleai_memoria import _pasta_dados
    pasta = current_app.config['PASTA_DADOS'] if has_app_context() else None
    if pasta is None and db is not None:
        pasta = _pasta_dados(db)
    return os.path.join(pasta, 'nucleai', 'openrouter_chave.txt') if pasta else None


def chave(db=None):
    """Arquivo tem precedência. Usa o ambiente somente quando não existe arquivo."""
    caminho = caminho_chave(db)
    if caminho:
        try:
            with open(caminho, encoding='utf-8') as f:
                return f.read().strip() or None
        except FileNotFoundError:
            pass
        except (OSError, UnicodeError):
            raise ErroLLM('sem_chave', 'Não foi possível ler a chave da IA.') from None
    return os.environ.get(VAR_CHAVE, '').strip() or None


def resumo_chave(db=None):
    valor = chave(db)
    return ('configurada, termina em ••••' + (valor[-4:] if len(valor) > 4 else '')) if valor else 'não configurada'


def salvar_chave(valor, db=None):
    """Grava atomicamente; None apaga o arquivo (o ambiente volta a valer)."""
    caminho = caminho_chave(db)
    if not caminho:
        raise ValueError('Pasta de dados da IA não configurada.')
    temporario = None
    try:
        if valor is None:
            try:
                os.remove(caminho)
            except FileNotFoundError:
                pass
            return
        valor = valor.strip()
        if not valor or len(valor) > 1024 or any(c.isspace() or ord(c) < 32 for c in valor):
            raise ValueError('Informe uma chave OpenRouter válida, sem espaços.')
        os.makedirs(os.path.dirname(caminho), exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=os.path.dirname(caminho), delete=False) as f:
            temporario = f.name
            f.write(valor)
        os.replace(temporario, caminho)
    except OSError:
        raise ValueError('Não foi possível salvar ou apagar a chave da IA.') from None
    finally:
        if temporario and os.path.exists(temporario):
            try:
                os.remove(temporario)
            except OSError:
                pass


def _baixar_json(url, cabecalhos, corpo=None, timeout=TIMEOUT_S):
    req = urllib.request.Request(url, data=corpo, headers=dict(cabecalhos), method='GET' if corpo is None else 'POST')
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8'))


def _baixar_conexao(url, cabecalhos, corpo=None):
    return _baixar_json(url, cabecalhos, corpo, timeout=TIMEOUT_CONEXAO_S)


def _corpo_do_erro(e):
    """Lê (sem estourar) o corpo de um HTTPError; vazio se não houver."""
    try:
        return e.read(4096)
    except Exception:
        return b''


def _como_dict(corpo):
    """Corpo de erro (bytes, str ou dict) -> dict de 'error' da OpenRouter, ou {}."""
    if isinstance(corpo, (bytes, bytearray)):
        corpo = corpo.decode('utf-8', 'replace')
    if isinstance(corpo, str):
        try:
            corpo = json.loads(corpo)
        except ValueError:
            return {'message': corpo.strip()[:300]} if corpo.strip() else {}
    if isinstance(corpo, dict):
        err = corpo.get('error', corpo)
        return err if isinstance(err, dict) else {'message': str(err)[:300]}
    return {}


def _segundos(valor, agora_epoch=None):
    """Dica de espera -> segundos (>0) ou None. Aceita segundos (Retry-After) ou epoch em s/ms (X-RateLimit-Reset)."""
    try:
        n = float(valor)
    except (TypeError, ValueError):
        return None
    if n > 1e11:                    # epoch em milissegundos
        n = n / 1000.0
    if n > 1e9:                     # epoch em segundos
        n = n - (agora_epoch if agora_epoch is not None else time.time())
    return int(n) if n > 0 else None


def _dica_de_espera(err, cabecalhos):
    """Menor dica de espera conhecida: cabeçalhos HTTP e metadata.headers do corpo."""
    achados = []
    for nome in ('Retry-After', 'X-RateLimit-Reset'):
        try:
            achados.append(_segundos((cabecalhos or {}).get(nome)))
        except Exception:
            pass
    meta_cab = ((err.get('metadata') or {}).get('headers') or {}) if isinstance(err.get('metadata'), dict) else {}
    if isinstance(meta_cab, dict):
        for nome in ('Retry-After', 'X-RateLimit-Reset'):
            achados.append(_segundos(meta_cab.get(nome)))
    achados = [a for a in achados if a]
    return min(achados) if achados else None


def _erro_cota(codigo, corpo, cabecalhos):
    err = _como_dict(corpo)
    texto = str(err.get('message') or '')
    meta = err.get('metadata') if isinstance(err.get('metadata'), dict) else {}
    provedor = str(meta.get('provider_name') or '')
    bruto = meta.get('raw')
    pista = (texto + ' ' + (bruto if isinstance(bruto, str) else '')).lower()
    if codigo == 402:
        escopo = 'credito'
    elif 'per-day' in pista or 'per day' in pista or 'daily' in pista:
        escopo = 'conta_dia'
    elif 'free-models-per-min' in pista or 'per-min' in pista or 'per minute' in pista:
        escopo = 'conta_min'
    else:
        escopo = 'modelo'
    detalhe = ('HTTP %d' % codigo) + (' · ' + provedor if provedor else '') + (' · ' + texto[:240] if texto else '')
    return ErroLLM('cota', 'Limite de uso da IA atingido. Tente de novo mais tarde.',
                   escopo=escopo, pausa_s=_dica_de_espera(err, cabecalhos), detalhe=detalhe)


def _erro_http(codigo, corpo=None, cabecalhos=None):
    if codigo in (429, 402):
        return _erro_cota(codigo, corpo, cabecalhos)
    if codigo == 404:   # o modelo não existe mais ou não aceita ferramentas: só ele está fora, os outros podem responder
        return ErroLLM('indisponivel', 'Este modelo da IA não está disponível.',
                       detalhe='HTTP 404 · ' + (str(_como_dict(corpo).get('message') or '')[:240]))
    if codigo == 408 or 500 <= codigo <= 599:
        return ErroLLM('servidor', 'O serviço de IA está indisponível no momento.', codigo == 408)
    return ErroLLM('resposta', 'A IA recusou a requisição (código %d).' % codigo)


def gerar(modelo, sistema, historico, ferramentas=None, baixar=None, timeout=TIMEOUT_S, db=None):
    """Recebe messages OpenAI. tokens é o total legado; tokens_entrada/saida/total
    separam o uso. baixar falso mantém a assinatura de três argumentos.
    """
    segredo = chave(db)
    if not segredo:
        if baixar is None:
            raise ErroLLM('sem_chave', 'Chave da IA não configurada. Configure-a na tela da NucleAI.')
        segredo = CHAVE_TESTE
    corpo = {'model': modelo, 'messages': [{'role': 'system', 'content': sistema}] + historico,
             'temperature': 0.2, 'max_tokens': 1500}
    if ferramentas:
        corpo['tools'] = ferramentas
    cabecalhos = {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + segredo,
                  'HTTP-Referer': 'https://nucleleste.invalid', 'X-Title': 'Nucleleste'}
    try:
        dados = json.dumps(corpo, ensure_ascii=False).encode('utf-8')
        j = baixar(BASE, cabecalhos, dados) if baixar else _baixar_json(BASE, cabecalhos, dados, timeout=timeout)
    except urllib.error.HTTPError as e:
        erro = _erro_http(e.code, _corpo_do_erro(e), getattr(e, 'headers', None))
        erro.detalhe = erro.detalhe.replace(segredo, '***')   # a chave nunca vai para log, tela ou mensagem
        e.close()
        raise erro from None
    except urllib.error.URLError as e:
        raise ErroLLM('rede', 'Sem acesso à internet para falar com a IA.', isinstance(e.reason, TimeoutError)) from None
    except TimeoutError:
        raise ErroLLM('rede', 'Tempo esgotado ao consultar a IA.', True) from None
    except OSError:
        raise ErroLLM('rede', 'Sem acesso à internet para falar com a IA.') from None
    except ValueError:
        raise ErroLLM('resposta', 'A IA devolveu uma resposta inválida.') from None
    try:
        if j.get('error'):
            erro = _erro_http(int(j['error']['code']), j['error'])
            erro.detalhe = erro.detalhe.replace(segredo, '***')
            raise erro
        msg = j['choices'][0]['message']
        texto = msg.get('content') or ''
        if not isinstance(texto, str) or msg.get('role') != 'assistant':
            raise ValueError
        chamadas = []
        for c in msg.get('tool_calls') or []:
            args = json.loads(c['function']['arguments'])
            if not isinstance(args, dict) or not c['id'] or c['type'] != 'function' or not c['function']['name']:
                raise ValueError
            chamadas.append({'id': c['id'], 'nome': c['function']['name'], 'args': args})
        if not texto and not chamadas:
            raise ValueError
        uso = j.get('usage') or {}
        entrada, saida = int(uso.get('prompt_tokens') or 0), int(uso.get('completion_tokens') or 0)
        total = int(uso.get('total_tokens') or entrada + saida)
        return {'texto': texto, 'chamadas': chamadas, 'mensagem': msg, 'modelo': j.get('model') or modelo,
                'tokens': total, 'tokens_entrada': entrada, 'tokens_saida': saida, 'tokens_total': total}
    except (KeyError, IndexError, TypeError, ValueError, AttributeError):
        raise ErroLLM('resposta', 'A IA devolveu uma resposta inválida.') from None


def conectado(baixar=None):
    """Teste barato de conectividade com cache de 10 s; qualquer HTTP conta."""
    agora = time.monotonic()
    if _cache_conexao['momento'] is not None and agora - _cache_conexao['momento'] < CACHE_CONEXAO_S:
        return _cache_conexao['ok']
    try:
        (baixar or _baixar_conexao)(URL_CONEXAO, {}, None)
        ok = True
    except urllib.error.HTTPError as e:
        e.close()
        ok = True
    except ValueError:
        ok = True
    except (urllib.error.URLError, OSError):
        ok = False
    _cache_conexao.update(momento=time.monotonic(), ok=ok)
    return ok


def limpar_cache():
    _cache_conexao.update(momento=None, ok=False)
