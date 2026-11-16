"""Desempenho dos estáticos e das respostas: sem banco para estáticos, cache com ?v=, gzip nas respostas dinâmicas."""
import gzip
import os
import re
import tempfile
import unittest
from unittest.mock import patch

from flask import Response

from app import create_app
from app import db as dbmod


class DesempenhoEstaticos(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        ambiente = patch.dict(os.environ, {'NUCLELESTE_DADOS': self.pasta.name})
        ambiente.start()
        self.addCleanup(ambiente.stop)
        self.app = create_app(os.path.join(self.pasta.name, 't.db'))
        self.app.config['TESTING'] = True

        # rota de teste só existe neste teste: download com Content-Disposition attachment
        def baixar():
            corpo = ('linha de teste ' * 400)
            return Response(corpo, mimetype='text/csv',
                            headers={'Content-Disposition': 'attachment; filename=teste.csv'})
        self.app.add_url_rule('/teste-download-desempenho', 'teste_download_desempenho', baixar)

    def test_estatico_sem_login_nao_abre_banco(self):
        original = dbmod.get_db
        chamadas = []

        def contar(*a, **kw):
            chamadas.append(1)
            return original(*a, **kw)

        with patch.object(dbmod, 'get_db', side_effect=contar):
            r = self.app.test_client().get('/static/css/app.css')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(chamadas, [])

    def test_pagina_referencia_estatico_com_versao_e_cache_longo(self):
        c = self.app.test_client()
        html = c.get('/login').get_data(as_text=True)
        urls = re.findall(r'/static/[^"\']+\?v=\d+', html)
        self.assertTrue(urls, 'a página de login deveria ter estáticos com ?v=')
        r = c.get(urls[0].replace('&amp;', '&'))
        self.assertEqual(r.status_code, 200)
        cache = r.headers.get('Cache-Control', '')
        self.assertIn('max-age=31536000', cache)
        self.assertIn('immutable', cache)

    def test_estatico_sem_versao_tem_cache_curto(self):
        r = self.app.test_client().get('/static/css/app.css')
        self.assertEqual(r.status_code, 200)
        self.assertIn('max-age=600', r.headers.get('Cache-Control', ''))
        self.assertNotIn('immutable', r.headers.get('Cache-Control', ''))

    def test_resposta_dinamica_comprimida_com_gzip(self):
        c = self.app.test_client()
        sem = c.get('/login')
        self.assertEqual(sem.status_code, 200)
        self.assertNotIn('Content-Encoding', sem.headers)
        self.assertGreaterEqual(len(sem.get_data()), 1500)

        com = c.get('/login', headers={'Accept-Encoding': 'gzip'})
        self.assertEqual(com.headers.get('Content-Encoding'), 'gzip')
        self.assertIn('Accept-Encoding', com.headers.get('Vary', ''))
        self.assertEqual(gzip.decompress(com.get_data()), sem.get_data())
        self.assertEqual(int(com.headers['Content-Length']), len(com.get_data()))

    def test_sem_accept_encoding_nao_comprime(self):
        r = self.app.test_client().get('/login')
        self.assertNotIn('Content-Encoding', r.headers)

    def test_download_nao_e_comprimido(self):
        r = self.app.test_client().get('/teste-download-desempenho', headers={'Accept-Encoding': 'gzip'})
        self.assertEqual(r.status_code, 200)
        self.assertNotIn('Content-Encoding', r.headers)
        self.assertIn('attachment', r.headers.get('Content-Disposition', ''))
        self.assertEqual(r.get_data(), ('linha de teste ' * 400).encode('utf-8'))


if __name__ == '__main__':
    unittest.main()
