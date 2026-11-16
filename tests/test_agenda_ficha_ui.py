"""Agenda compacta e previsão de entrega integrada à ficha impressa."""
import os
import re
import tempfile
import unittest
from html.parser import HTMLParser
from unittest.mock import patch

from app import create_app
from app import db as dbmod
from app import prazo_laudo


class LinksAreas(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.grupo = None
        self.links = {'abas': [], 'menu': []}
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'nav':
            if a.get('id') == 'ag-areas-opcoes':
                self.grupo = 'menu'
            elif 'abas-modulo' in a.get('class', '').split():
                self.grupo = 'abas'
        elif tag == 'a' and self.grupo:
            self.links[self.grupo].append(a)

    def handle_endtag(self, tag):
        if tag == 'nav':
            self.grupo = None


class AgendaFichaUI(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        ambiente = patch.dict(os.environ, {'NUCLELESTE_DADOS': self.pasta.name})
        ambiente.start()
        self.addCleanup(ambiente.stop)
        self.app = create_app(os.path.join(self.pasta.name, 't.db'))
        self.app.config['TESTING'] = True
        self.c = self.app.test_client()
        self.c.get('/login')
        with self.c.session_transaction() as s:
            self.csrf = s['csrf']
        r = self.c.post('/login', data={'usuario': 'ADMIN', 'senha': 'admin', '_csrf': self.csrf})
        self.assertEqual(r.status_code, 302)
        with self.app.app_context():
            db = dbmod.get_db()
            cid = db.execute("INSERT INTO clientes (nome, cpf) VALUES ('PACIENTE TESTE', '')").lastrowid
            self.aid = db.execute(
                'INSERT INTO atendimentos (cliente_id, cliente_nome, data, exame, medico, criado_em, previsao_laudo) '
                'VALUES (?,?,?,?,?,?,?)',
                (cid, 'PACIENTE TESTE', '2026-10-19', 'MIBI', 'DR TESTE', '2026-10-19 08:00:00', '2026-10-27')).lastrowid
            db.commit()

    def imprimir(self, documentos):
        r = self.c.get('/atendimentos/%d/imprimir' % self.aid, query_string=[('d', d) for d in documentos])
        self.assertEqual(r.status_code, 200)
        return r.get_data(as_text=True)

    def test_menu_preserva_destinos_e_permissoes_das_abas(self):
        r = self.c.get('/agenda')
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        links = LinksAreas(html).links
        self.assertGreater(len(links['menu']), 1)
        self.assertEqual([a['href'] for a in links['abas']], [a['href'] for a in links['menu']])
        for a in links['menu']:
            self.assertEqual(a['role'], 'menuitem')
            self.assertEqual(a['tabindex'], '-1')
        self.assertEqual(sum(a.get('aria-current') == 'page' for a in links['menu']), 1)
        self.assertIn('aria-haspopup="menu"', html)
        self.assertIn('id="ag-areas-opcoes" role="menu"', html)

    def test_barra_recolhida_preserva_controles_e_ids(self):
        html = self.c.get('/agenda').get_data(as_text=True)
        self.assertRegex(html, r'id="ag-formato"[^>]*\bhidden')
        self.assertIn('aria-controls="ag-formato"', html)
        for identificador in ('ag-calendario', 'ag-painel', 'ag-dia', 'ag-aviso', 'ag-inicial', 'ag-destacar',
                              'form-criar', 'form-copiar', 'form-imprimir', 'form-horario'):
            self.assertIn('id="%s"' % identificador, html)
        for acao in ('menos', 'mais', 'neg', 'ita', 'sub', 'caixa', 'limpar'):
            self.assertIn('data-fmt="%s"' % acao, html)
        self.assertIn('css/tema-escuro-agenda.css', html)

    def test_previsao_padrao_fica_na_linha_apos_exame_em_cada_copia(self):
        with self.app.app_context():
            self.assertTrue(prazo_laudo.exibir_na_ficha())
        html = self.imprimir(['ficha_mibi:2', 'ficha_geral:1'])
        linhas = re.findall(r'<tr\b[^>]*>.*?</tr>', html, re.S)
        exames = [i for i, linha in enumerate(linhas) if '>Exame:</td>' in linha]
        self.assertEqual(len(exames), 3)
        for i in exames:
            self.assertIn('class="previsao-laudo"', linhas[i + 1])
            self.assertIn('27/10/2026', linhas[i + 1])
        self.assertEqual(html.count('class="previsao-laudo"'), 3)
        self.assertNotIn("fo.appendChild", html)
        self.assertNotIn('bottom:5mm', html)

    def test_desativar_oculta_previsao_sem_apagar_data_gravada(self):
        with self.app.app_context():
            dbmod.config_set('laudo_previsao_ficha', '0')
        html = self.imprimir(['ficha_mibi:1', 'ficha_geral:1'])
        self.assertNotIn('class="previsao-laudo"', html)
        self.assertNotIn('Previsão de entrega do laudo:', html)
        with self.app.app_context():
            self.assertEqual(dbmod.get_db().execute('SELECT previsao_laudo FROM atendimentos WHERE id=?',
                                                   (self.aid,)).fetchone()[0], '2026-10-27')

    def test_atendimento_antigo_calcula_previsao_com_prazo_vigente(self):
        with self.app.app_context():
            db = dbmod.get_db()
            db.execute('UPDATE atendimentos SET previsao_laudo=NULL WHERE id=?', (self.aid,))
            db.commit()
        self.assertIn('Previsão de entrega do laudo: 20/10/2026', self.imprimir(['ficha_geral:1']))

    def test_ficha_personalizada_respeita_a_configuracao(self):
        with self.app.app_context():
            db = dbmod.get_db()
            xid = db.execute("INSERT INTO fichas_extras (titulo, conteudo) VALUES (?,?)",
                             ('Ficha de teste', '**Exame:** {exame}\n**Paciente:** {nome}')).lastrowid
            db.commit()
        html = self.imprimir(['x%d:1' % xid])
        self.assertIn('Previsão de entrega do laudo: 27/10/2026', html)
        self.assertRegex(html, r'<p class="fx-p"><strong>Exame:</strong> MIBI <span class="previsao-laudo"')
        with self.app.app_context():
            dbmod.config_set('laudo_previsao_ficha', '0')
        self.assertNotIn('Previsão de entrega do laudo:', self.imprimir(['x%d:1' % xid]))


if __name__ == '__main__':
    unittest.main()
