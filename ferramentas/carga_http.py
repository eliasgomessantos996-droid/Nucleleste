"""Teste de carga por HTTP: muitos usuários simultâneos usando o sistema como a recepção usaria.

Cada usuário virtual entra com um login próprio (CARGA000...), e repete uma mistura de ações com pausas curtas: abrir o
início, a agenda do dia, buscar cliente, lista de atendimentos, dashboard, registros, mensagens (consulta curta, batida de
presença e envio), relatórios e telas da Qualidade, além de gravar ocorrências e pesquisas. Mede o tempo de cada
requisição e devolve p50/p95/p99, requisições por segundo e erros. Sem bibliotecas externas.

Uso:
    python ferramentas/carga_http.py --url http://127.0.0.1:8099 --usuarios 50 --duracao 120 --saida resultado.json
Rode só contra um servidor de TESTE (pasta e porta próprias), nunca contra a instalação real.
"""
from __future__ import annotations

import argparse
import http.cookiejar
import json
import random
import re
import statistics
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, timedelta

SENHA = 'carga123'
CSRF = re.compile(r'name="_csrf" value="([0-9a-f]+)"|<meta name="csrf" content="([0-9a-f]+)"')


class Usuario:
    def __init__(self, base, login, registro):
        self.base = base.rstrip('/')
        self.login = login
        self.reg = registro
        self.jar = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.csrf = ''
        self.uid = None

    def _req(self, nome, metodo, caminho, dados=None, cab=None):
        corpo = urllib.parse.urlencode(dados).encode() if dados is not None else None
        req = urllib.request.Request(self.base + caminho, data=corpo, method=metodo, headers=cab or {})
        t = time.perf_counter()
        status, texto = 0, ''
        try:
            with self.op.open(req, timeout=60) as r:
                status = r.status
                texto = r.read().decode('utf-8', 'replace')
        except urllib.error.HTTPError as e:
            status = e.code
            try:
                texto = e.read().decode('utf-8', 'replace')
            except Exception:
                texto = ''
        except Exception as e:      # tempo esgotado, conexão recusada
            status = -1
            texto = type(e).__name__
        self.reg(nome, time.perf_counter() - t, status, texto)
        m = CSRF.search(texto) if texto else None
        if m:
            self.csrf = m.group(1) or m.group(2)
        return status, texto

    def get(self, nome, caminho, cab=None):
        return self._req(nome, 'GET', caminho, cab=cab)

    def post(self, nome, caminho, dados, json_=False):
        cab = {'X-CSRF-Token': self.csrf}
        if json_:
            cab['Accept'] = 'application/json'
        return self._req(nome, 'POST', caminho, dict(dados, _csrf=self.csrf), cab)

    def entrar(self):
        self.get('login (tela)', '/login')
        st, txt = self.post('login (entrar)', '/login', {'usuario': self.login, 'senha': SENHA})
        return st == 200 and 'Sair' in txt or st == 200


def montar_acoes(destinos):
    hoje = date.today()

    def dia():
        return (hoje - timedelta(days=random.randrange(0, 30))).isoformat()

    def agenda(u):
        u.get('agenda (tela)', '/agenda')
        u.get('agenda (dia, JSON)', '/agenda/dia/' + dia(), {'Accept': 'application/json'})

    def busca(u):
        u.get('clientes (busca)', '/clientes?q=' + urllib.parse.quote(random.choice(('SILVA', 'MARIA', 'SANTOS JOSE', 'ROCHA', '123'))))

    def chat(u):
        u.get('mensagens (novas)', '/mensagens/novas?depois=0', {'X-Passivo': '1', 'Accept': 'application/json'})

    def batida(u):
        u.post('presença (batida)', '/sessao/batida', {'aba': 'carga%d' % random.randrange(3)}, json_=True)

    def enviar(u):
        u.post('mensagens (enviar)', '/mensagens/enviar', {'para': random.choice(destinos), 'corpo': 'teste de carga %d' % random.randrange(10 ** 6)},
               json_=True)

    def ocorrencia(u):
        u.post('qualidade (gravar ocorrência)', '/qualidade/ocorrencias/salvar',
               {'tipo': 'Reclamação', 'descricao': 'teste de carga', 'gravidade': 'Leve', 'data': hoje.isoformat()})

    return [
        (14, lambda u: u.get('início', '/')),
        (16, agenda),
        (10, busca),
        (8, lambda u: u.get('atendimentos (lista)', '/atendimentos')),
        (12, chat),
        (10, batida),
        (3, enviar),
        (4, lambda u: u.get('dashboard (mês)', '/dashboard')),
        (1, lambda u: u.get('dashboard (tudo)', '/dashboard?p=tudo')),
        (3, lambda u: u.get('registros', '/registros')),
        (2, lambda u: u.get('relatório ONA', '/ona')),
        (2, lambda u: u.get('agenda (relatório)', '/agenda/relatorio')),
        (3, lambda u: u.get('qualidade (indicadores)', '/qualidade/indicadores')),
        (2, lambda u: u.get('qualidade (pareto)', '/qualidade/pareto')),
        (1, lambda u: u.get('qualidade (central)', '/qualidade')),
        (1, ocorrencia),
        (1, lambda u: u.post('qualidade (pesquisa)', '/qualidade/pesquisa', {'nota': random.randrange(6, 11)})),
    ]


def percentil(valores, p):
    if not valores:
        return None
    v = sorted(valores)
    k = max(0, min(len(v) - 1, int(round(p / 100.0 * (len(v) - 1)))))
    return v[k]


def amostrar_processo(pid, parar, saida):
    while not parar.is_set():
        try:
            r = subprocess.run(['powershell', '-NoProfile', '-Command',
                                '$p=Get-Process -Id %d; "{0} {1}" -f $p.WorkingSet64,$p.CPU' % pid],
                               capture_output=True, text=True, timeout=20)
            mem, cpu = r.stdout.strip().replace(',', '.').split()
            saida.append({'t': time.time(), 'mem_mb': round(int(float(mem)) / 1024 ** 2, 1), 'cpu_s': float(cpu)})
        except Exception:
            pass
        parar.wait(10)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--url', required=True)
    ap.add_argument('--usuarios', type=int, default=20)
    ap.add_argument('--duracao', type=int, default=60, help='segundos de carga depois da subida')
    ap.add_argument('--rampa', type=int, default=20, help='segundos para todos os usuários entrarem')
    ap.add_argument('--pausa', type=float, default=1.0, help='pausa média entre ações de cada usuário (s)')
    ap.add_argument('--primeiro', type=int, default=0, help='primeiro usuário CARGA a usar')
    ap.add_argument('--pid', type=int, default=0, help='processo do servidor, para medir memória e CPU')
    ap.add_argument('--saida', default='')
    a = ap.parse_args()
    if any(x in a.url for x in (':8080',)):
        raise SystemExit('Recusado: a porta 8080 é a da instalação real. Use o servidor de teste.')
    tempos = defaultdict(list)
    status = defaultdict(lambda: defaultdict(int))
    erros_texto = defaultdict(int)
    trava = threading.Lock()

    def registrar(nome, dt, st, texto):
        with trava:
            tempos[nome].append(dt)
            status[nome][st] += 1
            if st >= 500 or st < 0:
                chave = 'database is locked' if 'locked' in (texto or '') else texto[:60] if st < 0 else 'HTTP %d' % st
                erros_texto[chave] += 1

    destinos = list(range(5, 5 + a.usuarios))   # ids dos usuários CARGA (os 4 primeiros são do sistema)
    acoes = montar_acoes(destinos)
    pesos = [p for p, _ in acoes]
    parar = threading.Event()
    inicio_carga = [0.0]

    def trabalhar(i):
        time.sleep(a.rampa * i / max(1, a.usuarios))
        u = Usuario(a.url, 'CARGA%03d' % (a.primeiro + i), registrar)
        if not u.entrar():
            return
        while not parar.is_set():
            random.choices([f for _, f in acoes], pesos)[0](u)
            parar.wait(random.uniform(.3, 1.7) * a.pausa)

    amostras = []
    if a.pid:
        threading.Thread(target=amostrar_processo, args=(a.pid, parar, amostras), daemon=True).start()
    threads = [threading.Thread(target=trabalhar, args=(i,), daemon=True) for i in range(a.usuarios)]
    t0 = time.time()
    for t in threads:
        t.start()
    time.sleep(a.rampa)
    inicio_carga[0] = time.time()
    time.sleep(a.duracao)
    parar.set()
    for t in threads:
        t.join(timeout=70)
    total_s = time.time() - t0
    linhas = []
    for nome in sorted(tempos, key=lambda k: -percentil(tempos[k], 95)):
        v = tempos[nome]
        ok = sum(c for s, c in status[nome].items() if 200 <= s < 400)
        recusadas = sum(c for s, c in status[nome].items() if 400 <= s < 500)
        linhas.append({'acao': nome, 'n': len(v), 'ok': ok, 'erros': len(v) - ok - recusadas, 'recusadas_4xx': recusadas, 'p50_ms': round(1000 * percentil(v, 50)),
                       'p95_ms': round(1000 * percentil(v, 95)), 'p99_ms': round(1000 * percentil(v, 99)), 'max_ms': round(1000 * max(v)),
                       'media_ms': round(1000 * statistics.mean(v)), 'status': dict(status[nome])})
    todas = [x for v in tempos.values() for x in v]
    resumo = {'usuarios': a.usuarios, 'duracao_s': round(total_s, 1), 'requisicoes': len(todas), 'rps': round(len(todas) / total_s, 1),
              'p50_ms': round(1000 * percentil(todas, 50)) if todas else None, 'p95_ms': round(1000 * percentil(todas, 95)) if todas else None,
              'p99_ms': round(1000 * percentil(todas, 99)) if todas else None,
              'erros': sum(x['erros'] for x in linhas), 'recusadas_4xx': sum(x['recusadas_4xx'] for x in linhas), 'erros_por_tipo': dict(erros_texto), 'acoes': linhas,
              'memoria_mb': [s['mem_mb'] for s in amostras], 'cpu_s': [s['cpu_s'] for s in amostras]}
    print('usuários %d · %d requisições em %.0f s (%.1f/s) · p50 %s ms · p95 %s ms · p99 %s ms · erros do servidor %d · recusadas (4xx) %d %s' % (
        a.usuarios, resumo['requisicoes'], total_s, resumo['rps'], resumo['p50_ms'], resumo['p95_ms'], resumo['p99_ms'], resumo['erros'],
        resumo['recusadas_4xx'],
        dict(erros_texto) if erros_texto else ''))
    print('%-34s %7s %7s %8s %8s %8s %8s' % ('ação', 'n', 'erros', 'p50', 'p95', 'p99', 'máx'))
    for x in linhas:
        print('%-34s %7d %7d %8d %8d %8d %8d' % (x['acao'][:34], x['n'], x['erros'], x['p50_ms'], x['p95_ms'], x['p99_ms'], x['max_ms']))
    if amostras:
        print('memória do servidor (MB): início %.0f · máx %.0f · fim %.0f' % (amostras[0]['mem_mb'], max(s['mem_mb'] for s in amostras), amostras[-1]['mem_mb']))
    if a.saida:
        with open(a.saida, 'w', encoding='utf-8') as fh:
            json.dump(resumo, fh, ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
