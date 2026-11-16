"""Inicia o Sistema de Recepção Nucleleste.

    python servidor.py            -> servidor de produção (Waitress) na porta do config.json (padrão 8080)
    python servidor.py --dev      -> modo desenvolvimento (recarrega ao editar o código)

Os outros computadores da rede acessam pelo navegador: http://NOME-OU-IP-DESTE-PC:8080
"""
import socket
import sys

from app import create_app

app = create_app(avisos_automaticos=True)

if __name__ == '__main__':
    porta = int(app.config['PORTA'])
    if '--dev' in sys.argv:
        app.run(host='127.0.0.1', port=porta, debug=True)
    else:
        from waitress import serve
        nome = socket.gethostname()
        print('=' * 64)
        print(' Sistema de Recepção Nucleleste')
        print(' Neste computador:   http://localhost:%d' % porta)
        print(' Em outros da rede:  http://%s:%d' % (nome, porta))
        print(' Banco de dados:     %s' % app.config['DATABASE'])
        print(' Para encerrar, feche esta janela.')
        print('=' * 64)
        serve(app, host='0.0.0.0', port=porta, threads=48)   # 24 delas podem ficar esperando mensagens (tempo real do chat)
