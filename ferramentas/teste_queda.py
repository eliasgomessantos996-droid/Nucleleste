"""Teste de queda: derruba o servidor de TESTE no meio de muitas gravações e confere se o banco volta íntegro.

1. Copia o banco de teste para uma pasta própria e sobe o servidor de carga nela.
2. Vários usuários gravam ao mesmo tempo (ocorrências, pesquisas, mensagens e batidas de presença).
3. No meio das gravações o processo é encerrado à força (como uma queda de energia do programa).
4. O servidor sobe de novo: o SQLite recupera o diário (WAL), roda PRAGMA integrity_check e conta o que ficou gravado.

Uso:
    python ferramentas/teste_queda.py --origem %TEMP%\\nucleleste_carga_S --pasta %TEMP%\\nucleleste_queda
"""
import argparse
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)


def subir(pasta, porta):
    p = subprocess.Popen([sys.executable, os.path.join(RAIZ, 'ferramentas', 'servidor_carga.py'), '--pasta', pasta, '--porta', str(porta)],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=RAIZ)
    for _ in range(120):
        try:
            urllib.request.urlopen('http://127.0.0.1:%d/login' % porta, timeout=2).read()
            return p
        except Exception:
            time.sleep(0.5)
    raise SystemExit('o servidor de teste não subiu')


def contar(banco):
    con = sqlite3.connect(banco)
    try:
        ok = con.execute('PRAGMA integrity_check').fetchone()[0]
        n = {t: con.execute('SELECT COUNT(*) FROM %s' % t).fetchone()[0] for t in ('cq_ocorrencias', 'cq_pesquisas', 'chat_mensagens')}
        return ok, n
    finally:
        con.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--origem', required=True)
    ap.add_argument('--pasta', required=True)
    ap.add_argument('--porta', type=int, default=8098)
    ap.add_argument('--usuarios', type=int, default=30)
    ap.add_argument('--segundos', type=float, default=20, help='tempo de gravações antes da queda')
    a = ap.parse_args()
    from ferramentas.gerar_carga import proteger
    from ferramentas.carga_http import Usuario
    proteger(a.pasta)
    proteger(a.origem)
    if os.path.exists(a.pasta):
        shutil.rmtree(a.pasta)
    os.makedirs(a.pasta)
    for nome in os.listdir(a.origem):
        if nome.startswith('sistema.db') or nome == 'chave_secreta.txt':
            shutil.copy2(os.path.join(a.origem, nome), os.path.join(a.pasta, nome))
    banco = os.path.join(a.pasta, 'sistema.db')
    antes_ok, antes = contar(banco)
    print('antes: integridade %s, %s' % (antes_ok, antes), flush=True)
    srv = subir(a.pasta, a.porta)
    parar = threading.Event()
    enviados = {'ok': 0, 'falha': 0}
    trava = threading.Lock()

    def registrar(_nome, _dt, st, _txt):
        with trava:
            enviados['ok' if 200 <= st < 400 else 'falha'] += 1

    def gravar(i):
        u = Usuario('http://127.0.0.1:%d' % a.porta, 'CARGA%03d' % (100 + i), registrar)
        if not u.entrar():
            return
        k = 0
        while not parar.is_set():
            k += 1
            if k % 3 == 0:
                u.post('ocorrência', '/qualidade/ocorrencias/salvar', {'tipo': 'Reclamação', 'descricao': 'queda %d-%d' % (i, k), 'gravidade': 'Leve'})
            elif k % 3 == 1:
                u.post('pesquisa', '/qualidade/pesquisa', {'nota': 9})
            else:
                u.post('mensagem', '/mensagens/enviar', {'para': 5 + (i + 1) % a.usuarios, 'corpo': 'queda %d-%d' % (i, k)}, json_=True)
    ts = [threading.Thread(target=gravar, args=(i,), daemon=True) for i in range(a.usuarios)]
    for t in ts:
        t.start()
    time.sleep(a.segundos)
    print('derrubando o servidor (pid %d) no meio das gravações...' % srv.pid, flush=True)
    subprocess.run(['taskkill', '/PID', str(srv.pid), '/F', '/T'], capture_output=True)
    parar.set()
    for t in ts:
        t.join(timeout=5)
    time.sleep(1)
    wal = os.path.join(a.pasta, 'sistema.db-wal')
    print('arquivo WAL depois da queda: %s bytes' % (os.path.getsize(wal) if os.path.exists(wal) else 0), flush=True)
    srv2 = subir(a.pasta, a.porta)       # reabrir recupera o WAL
    try:
        urllib.request.urlopen('http://127.0.0.1:%d/login' % a.porta, timeout=5).read()
    finally:
        subprocess.run(['taskkill', '/PID', str(srv2.pid), '/F', '/T'], capture_output=True)
    time.sleep(1)
    depois_ok, depois = contar(banco)
    novos = {k: depois[k] - antes[k] for k in antes}
    print('requisições de gravação: %d com sucesso, %d interrompidas/falhas' % (enviados['ok'], enviados['falha']))
    print('depois: integridade %s, linhas novas gravadas %s' % (depois_ok, novos))
    print('RESULTADO:', 'BANCO ÍNTEGRO' if depois_ok == 'ok' else 'PROBLEMA NA INTEGRIDADE')


if __name__ == '__main__':
    main()
