"""Tela de login: lembra os usuários que já entraram neste computador (cookie nuc_usuarios), sem nunca guardar a senha."""
import os
import re
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import quote, unquote

from werkzeug.security import generate_password_hash

from app import create_app
from app import db as dbmod


class LoginLembrar(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        ambiente = patch.dict(os.environ, {'NUCLELESTE_DADOS': self.pasta.name})
        ambiente.start()
        self.addCleanup(ambiente.stop)
        self.app = create_app(os.path.join(self.pasta.name, 't.db'))
        self.app.config['TESTING'] = True
        self.conn = dbmod.conectar(self.app.config['DATABASE'])
        self.addCleanup(self.conn.close)
        self.usuario('ANA', 'ana123')
        self.usuario('BRUNO', 'bruno123')
        self.usuario('INATIVO', 'inativo123', ativo=0)

    def usuario(self, nome, senha, ativo=1):
        with self.conn:
            self.conn.execute('INSERT INTO usuarios (usuario, senha_hash, admin, ativo, criado_em, modulos, trocar_senha) '
                              'VALUES (?,?,0,?,?,?,0)',
                              (nome, generate_password_hash(senha), ativo, '2026-01-01 00:00:00', '[]'))

    def token(self, cliente):
        cliente.get('/login')
        with cliente.session_transaction() as sessao:
            return sessao['csrf']

    def entrar(self, usuario, senha, cliente=None):
        cliente = cliente or self.app.test_client()
        token = self.token(cliente)
        return cliente.post('/login', data={'usuario': usuario, 'senha': senha, '_csrf': token})

    def cookie_gravado(self, resposta):
        """Valor do Set-Cookie nuc_usuarios da resposta, ou None se a resposta não gravou o cookie."""
        for linha in resposta.headers.getlist('Set-Cookie'):
            if linha.startswith('nuc_usuarios='):
                return linha
        return None

    def lembrados_no_cookie(self, linha):
        valor = linha.split(';')[0].split('=', 1)[1]
        return unquote(valor).split('\n')

    def opcoes_datalist(self, html):
        bloco = re.search(r'<datalist id="usuarios-lembrados">(.*?)</datalist>', html, re.S)
        return re.findall(r'<option value="([^"]*)"', bloco.group(1)) if bloco else []

    def test_login_certo_grava_cookie_com_o_nome(self):
        resposta = self.entrar('ANA', 'ana123')
        self.assertEqual(resposta.status_code, 302)
        linha = self.cookie_gravado(resposta)
        self.assertIsNotNone(linha)
        self.assertEqual(self.lembrados_no_cookie(linha), ['ANA'])
        self.assertIn('HttpOnly', linha)
        self.assertIn('SameSite=Lax', linha)
        self.assertIn('Path=/', linha)
        self.assertIn('Max-Age=31536000', linha)

    def test_cookie_guarda_o_mais_recente_sem_repetir_e_sem_diferenciar_caixa(self):
        cliente = self.app.test_client()
        self.entrar('ANA', 'ana123', cliente)
        resposta = self.entrar('bruno', 'bruno123', cliente)
        self.assertEqual(self.lembrados_no_cookie(self.cookie_gravado(resposta)), ['BRUNO', 'ANA'])
        resposta = self.entrar('ana', 'ana123', cliente)
        self.assertEqual(self.lembrados_no_cookie(self.cookie_gravado(resposta)), ['ANA', 'BRUNO'])

    def test_senha_errada_nao_grava_cookie(self):
        resposta = self.entrar('ANA', 'errada')
        self.assertEqual(resposta.status_code, 200)
        self.assertIsNone(self.cookie_gravado(resposta))

    def test_nome_inexistente_nao_grava_cookie(self):
        resposta = self.entrar('FANTASMA', 'qualquer')
        self.assertEqual(resposta.status_code, 200)
        self.assertIsNone(self.cookie_gravado(resposta))

    def test_usuario_inativo_nao_grava_cookie(self):
        resposta = self.entrar('INATIVO', 'inativo123')
        self.assertEqual(resposta.status_code, 200)
        self.assertIsNone(self.cookie_gravado(resposta))

    def test_get_mostra_no_datalist_so_o_nome_valido_e_ativo(self):
        valor = quote('\n'.join(['FANTASMA', 'INATIVO', 'ANA']))
        cliente = self.app.test_client()
        cliente.set_cookie('nuc_usuarios', valor)
        resposta = cliente.get('/login')
        html = resposta.get_data(as_text=True)
        self.assertEqual(self.opcoes_datalist(html), ['ANA'])
        self.assertIn('list="usuarios-lembrados"', html)
        self.assertIn('autocomplete="username"', html)
        self.assertIn('value="ANA"', html)

    def test_cookie_corrompido_e_ignorado(self):
        cliente = self.app.test_client()
        cliente.set_cookie('nuc_usuarios', '%FF%00%%%zz')
        resposta = cliente.get('/login')
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(self.opcoes_datalist(resposta.get_data(as_text=True)), [])

    def test_sem_lembrados_o_campo_fica_vazio_com_foco(self):
        resposta = self.app.test_client().get('/login')
        html = resposta.get_data(as_text=True)
        self.assertEqual(self.opcoes_datalist(html), [])
        self.assertNotRegex(html, r'id="usuario"[^>]*value=')

    def test_senha_nunca_aparece_no_cookie(self):
        resposta = self.entrar('ANA', 'ana123')
        linha = self.cookie_gravado(resposta)
        self.assertNotIn('ana123', linha)
        self.assertNotIn('ana123', unquote(linha))


if __name__ == '__main__':
    unittest.main()
