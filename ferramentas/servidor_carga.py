"""Sobe o sistema contra um banco de TESTE, para o teste de carga (mesmo Waitress e mesmas 48 threads do servidor real).

Uso:
    python ferramentas/servidor_carga.py --pasta %TEMP%\\nucleleste_carga_M --porta 8099
Recusa a pasta da instalação real, a pasta dados/ do projeto e a porta 8080. Não inicia os avisos automáticos (e o robô
diário), para que a carga meça só as telas; use --avisos para incluí-los.
"""
import argparse
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pasta', required=True)
    ap.add_argument('--porta', type=int, default=8099)
    ap.add_argument('--threads', type=int, default=48)
    ap.add_argument('--avisos', action='store_true')
    a = ap.parse_args()
    from ferramentas.gerar_carga import proteger
    proteger(a.pasta)
    if a.porta == 8080:
        raise SystemExit('Recusado: a porta 8080 é a da instalação real.')
    os.environ['NUCLELESTE_DADOS'] = a.pasta
    os.environ['NUCLELESTE_PORTA'] = str(a.porta)
    from waitress import serve
    from app import create_app
    app = create_app(os.path.join(a.pasta, 'sistema.db'), avisos_automaticos=a.avisos)
    print('servidor de carga em http://127.0.0.1:%d (pasta %s, pid %d)' % (a.porta, a.pasta, os.getpid()), flush=True)
    serve(app, host='127.0.0.1', port=a.porta, threads=a.threads, connection_limit=1000, channel_timeout=120)


if __name__ == '__main__':
    main()
