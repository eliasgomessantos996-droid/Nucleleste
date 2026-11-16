"""Cache curto para contas pesadas (dashboard, indicadores da Qualidade).

- Guarda o resultado por alguns segundos, por banco e por chave (período, filtros e uma "marca" dos dados).
- Cálculo único: se dez pessoas pedem a mesma conta ao mesmo tempo, uma calcula e as outras esperam esse resultado,
  em vez de fazer dez vezes a mesma consulta pesada (era isso que derrubava o servidor no teste de sobrecarga).
- A marca dos dados (ex.: o maior id e a quantidade de linhas do período) faz um lançamento novo aparecer na hora.
"""
from __future__ import annotations

import threading
import time

_valores = {}
_calculando = {}
_trava = threading.Lock()
LIMITE_CHAVES = 300


def obter(chave, calcular, segundos=30):
    """Valor em cache para `chave` (até `segundos`), ou calcula uma única vez mesmo com vários pedidos simultâneos."""
    while True:
        with _trava:
            achado = _valores.get(chave)
            if achado and time.monotonic() - achado[0] < segundos:
                return achado[1]
            evento = _calculando.get(chave)
            if evento is None:
                evento = threading.Event()
                _calculando[chave] = evento
                sou_eu = True
            else:
                sou_eu = False
        if not sou_eu:
            evento.wait(120)          # outro pedido está calculando: espera e usa o resultado dele
            with _trava:
                achado = _valores.get(chave)
            if achado:
                return achado[1]
            continue                  # quem calculava falhou: tenta de novo
        try:
            valor = calcular()
            with _trava:
                if len(_valores) > LIMITE_CHAVES:
                    _valores.clear()
                _valores[chave] = (time.monotonic(), valor)
            return valor
        finally:
            with _trava:
                _calculando.pop(chave, None)
            evento.set()


def limpar():
    with _trava:
        _valores.clear()
