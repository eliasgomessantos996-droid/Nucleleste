"""Modelos prontos da Qualidade para medicina nuclear: catálogo, aplicação em cada ferramenta, protocolos (POPs) e PDFs com
quadro de validação e assinaturas."""
import re
import unittest

from reportlab import rl_config

from app import qualidade as q
from app import qualidade_catalogo as cat
from app import qualidade_catalogo_outros as cat2
from app import qualidade_graficos as graf
from app import qualidade_modelos as mod
from app import qualidade_pops as pops
from tests.test_chat_blindagens import Base


class Catalogo(unittest.TestCase):
    """Os modelos são dados: aqui se garante que todos respeitam as regras das telas onde serão aplicados."""

    def test_problemas(self):
        self.assertGreaterEqual(len(cat.PROBLEMAS), 15)
        for chave, m in cat.PROBLEMAS.items():
            with self.subTest(chave):
                self.assertTrue(m['titulo'] and m['descricao'] and m['meta'] and m['causa_raiz'] and m['padrao'])
                self.assertTrue(all(1 <= n <= 5 for n in m['gut']))
                self.assertEqual(len(m['porques']), 5)
                self.assertTrue(set(m['causas']) <= set(q.SEIS_M))
                self.assertGreaterEqual(sum(len(v) for v in m['causas'].values()), 4)
                self.assertGreaterEqual(len(m['acoes']), 3)
                for acao in m['acoes']:
                    self.assertEqual(len(acao), 6)
                    self.assertTrue(all(acao[:5]) and acao[5] > 0)

    def test_riscos_swot_organogramas(self):
        for chave, m in cat2.RISCOS.items():
            for titulo, processo, causa, consequencia, prob, imp, resposta, acao, prazo in m['itens']:
                self.assertTrue(1 <= prob <= 5 and 1 <= imp <= 5, titulo)
                self.assertIn(resposta, q.RESPOSTAS_RISCO)
        for chave, m in cat2.SWOT.items():
            self.assertEqual(set(m['itens']), {'F', 'FR', 'O', 'A'})
            for lista in m['itens'].values():
                self.assertTrue(all(1 <= peso <= 5 for _t, peso in lista))
        for chave, m in cat2.ORGANOGRAMAS.items():
            ids = [n[0] for n in m['nos']]
            self.assertEqual(len(ids), len(set(ids)))
            self.assertEqual(sum(1 for n in m['nos'] if n[3] is None), 1, chave)
            for n in m['nos']:
                self.assertTrue(n[3] is None or n[3] in ids)
                self.assertLess(ids.index(n[3]) if n[3] else -1, ids.index(n[0]), 'o superior vem antes: ' + chave)

    def test_ocorrencias_criterios_perguntas(self):
        for nome, tipo, grav, setor, descricao, acao in cat2.OCORRENCIAS:
            self.assertIn(tipo, q.TIPOS_OCORRENCIA)
            self.assertIn(grav, q.GRAVIDADES)
            self.assertTrue(descricao and acao)
        for m in cat2.CRITERIOS.values():
            self.assertTrue(all(1 <= p <= 5 and n and d for n, d, p in m['criterios']))
        for m in cat2.PERGUNTAS.values():
            self.assertTrue(1 <= len(m['perguntas']) <= 10)
            self.assertTrue(all(len(t) <= 200 for t in m['perguntas']))

    def test_fluxogramas(self):
        self.assertGreaterEqual(len(mod.MODELOS), 15)
        for chave, v in mod._MODELOS.items():
            nome, raias, nos, ligs = v
            ids = [n[0] for n in nos]
            with self.subTest(chave):
                self.assertEqual(len(ids), len(set(ids)))
                posicoes = [(n[3], n[5]) for n in nos]
                self.assertEqual(len(posicoes), len(set(posicoes)), 'duas etapas na mesma raia e coluna')
                for n in nos:
                    self.assertLess(int(n[5][1:]), len(raias))
                for de, para, _r in ligs:
                    self.assertIn(de, ids)
                    self.assertIn(para, ids)
                self.assertIn(chave, mod.INFO)
                d = q._limpar_fluxo(mod.fluxo(chave))
                self.assertEqual(len(d['nos']), len(nos))
        self.assertEqual({g for g, _ in mod.galeria()} <= {'Atendimento', 'Radiofarmácia e radioproteção', 'Segurança do paciente', 'Apoio'}, True)

    def test_protocolos(self):
        self.assertGreaterEqual(len(pops.POPS), 20)
        codigos = [m['codigo'] for m in pops.POPS.values()]
        self.assertEqual(len(codigos), len(set(codigos)))
        for chave, m in pops.POPS.items():
            with self.subTest(chave):
                self.assertTrue(m['objetivo'] and m['abrangencia'] and m['responsaveis'] and m['referencias'] and m['registros'])
                self.assertGreaterEqual(len(m['passos']), 6)
                if m['fluxo_modelo']:
                    self.assertIn(m['fluxo_modelo'], dict(mod.MODELOS))

    def test_graficos_nao_usam_simbolos_fora_do_pdf(self):
        faixas = graf.fluxograma(mod.fluxo('derramamento'), 757, 400)
        self.assertGreater(len(faixas), 1, 'fluxo largo deve sair em faixas legíveis')
        self.assertEqual(len(graf.fluxograma(mod.fluxo('agendamento'), 757, 400)) >= 1, True)
        self.assertEqual(graf._limpo('a ★ b ≥ c'), 'a * b >= c')


class Aplicacao(Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        rl_config.pageCompression = 0     # o texto do PDF fica legível para conferir o quadro de assinaturas

    @classmethod
    def tearDownClass(cls):
        rl_config.pageCompression = 1
        super().tearDownClass()

    def abrir(self, c, url):
        r = c.get(url)
        self.assertEqual(r.status_code, 200, url)
        return r

    def test_galerias_aparecem_em_cada_aba(self):
        c = self.cliente()
        esperado = {
            '/qualidade/pdca': 'Modelos prontos de análise de problemas', '/qualidade/ishikawa': 'Modelos prontos de análise de problemas',
            '/qualidade/porques': 'Modelos prontos de análise de problemas', '/qualidade/gut': 'Modelos prontos de análise de problemas',
            '/qualidade/plano': 'Modelos prontos de plano de ação 5W2H', '/qualidade/riscos': 'Modelos prontos de riscos',
            '/qualidade/swot': 'Modelos prontos de análise SWOT', '/qualidade/fluxogramas': 'Fluxogramas prontos',
            '/qualidade/organograma': 'Organogramas prontos', '/qualidade/ocorrencias': 'Começar de um modelo pronto',
            '/qualidade/fornecedores/criterios': 'Conjuntos prontos de critérios', '/qualidade/satisfacao': 'Modelos prontos de perguntas',
            '/qualidade/protocolos': 'Protocolos prontos para medicina nuclear'}
        for url, texto in esperado.items():
            self.assertIn(texto, self.texto(self.abrir(c, url)), url)
        central = self.texto(self.abrir(c, '/qualidade'))
        self.assertIn('Protocolos (POPs)', central)

    def test_aplicar_problema_cria_tudo_e_nao_duplica(self):
        c = self.cliente()
        r = self.post(c, '/qualidade/modelos/problema/atividade_fora_faixa', {'destino': 'ishikawa'})
        self.assertEqual(r.status_code, 302)
        self.assertIn('/qualidade/ishikawa?p=', r.headers['Location'])
        from app.db import conectar
        con = conectar(self.app.config['DATABASE'])
        p = con.execute("SELECT * FROM cq_problemas WHERE titulo=?", (cat.PROBLEMAS['atividade_fora_faixa']['titulo'],)).fetchall()
        self.assertEqual(len(p), 1)
        pid = p[0]['id']
        self.assertEqual(p[0]['origem'], 'MODELO')
        self.assertGreaterEqual(con.execute('SELECT COUNT(*) FROM cq_causas WHERE problema_id=?', (pid,)).fetchone()[0], 6)
        self.assertEqual(con.execute('SELECT COUNT(*) FROM cq_porques WHERE problema_id=?', (pid,)).fetchone()[0], 5)
        self.assertEqual(con.execute('SELECT COUNT(*) FROM cq_acoes WHERE problema_id=?', (pid,)).fetchone()[0], 4)
        con.close()
        self.post(c, '/qualidade/modelos/problema/atividade_fora_faixa', {'destino': 'pdca'})
        con = conectar(self.app.config['DATABASE'])
        self.assertEqual(con.execute("SELECT COUNT(*) FROM cq_problemas WHERE titulo=?", (cat.PROBLEMAS['atividade_fora_faixa']['titulo'],)).fetchone()[0], 1)
        con.close()
        # as ferramentas ligadas ao problema mostram o conteúdo do modelo e geram o PDF
        for url in ('/qualidade/ishikawa?p=%d' % pid, '/qualidade/porques?p=%d' % pid, '/qualidade/gut', '/qualidade/pdca/%d' % pid, '/qualidade/plano'):
            self.abrir(c, url)

    def test_todos_os_modelos_de_problema_se_aplicam(self):
        c = self.cliente()
        for chave in cat.PROBLEMAS:
            r = self.post(c, '/qualidade/modelos/problema/' + chave, {'destino': 'pdca'})
            self.assertEqual(r.status_code, 302, chave)
            self.assertIn('/qualidade/pdca/', r.headers['Location'])

    def test_planos_riscos_swot(self):
        c = self.cliente()
        for chave in cat2.PLANOS:
            self.assertEqual(self.post(c, '/qualidade/modelos/plano/' + chave).status_code, 302)
        n1 = self.texto(self.abrir(c, '/qualidade/plano'))
        self.assertIn('Calibrar e aferir monitores', n1)
        for chave in cat2.RISCOS:
            self.post(c, '/qualidade/modelos/riscos/' + chave)
        self.post(c, '/qualidade/modelos/riscos/radioprotecao')        # repetir não duplica
        from app.db import conectar
        con = conectar(self.app.config['DATABASE'])
        total = sum(len(m['itens']) for m in cat2.RISCOS.values())
        self.assertEqual(con.execute('SELECT COUNT(*) FROM cq_riscos').fetchone()[0], total)
        con.close()
        for chave in cat2.SWOT:
            r = self.post(c, '/qualidade/modelos/swot/' + chave)
            self.assertEqual(r.status_code, 302)
            self.abrir(c, r.headers['Location'])

    def test_fluxogramas_organogramas_criterios_perguntas(self):
        c = self.cliente()
        for chave in mod._MODELOS:
            r = self.post(c, '/qualidade/modelos/fluxograma/' + chave)
            self.assertEqual(r.status_code, 302, chave)
            self.abrir(c, r.headers['Location'])
        self.assertEqual(self.post(c, '/qualidade/modelos/fluxograma/nao_existe').status_code, 404)
        # organograma: o segundo precisa de "substituir"
        self.assertEqual(self.post(c, '/qualidade/modelos/organograma/basico').status_code, 302)
        r = self.post(c, '/qualidade/modelos/organograma/completo', follow_redirects=True)
        self.assertIn('Já existe um organograma', self.texto(r))
        self.post(c, '/qualidade/modelos/organograma/completo', {'substituir': '1'})
        from app.db import conectar
        con = conectar(self.app.config['DATABASE'])
        self.assertEqual(con.execute('SELECT COUNT(*) FROM cq_organograma').fetchone()[0], len(cat2.ORGANOGRAMAS['completo']['nos']))
        con.close()
        self.post(c, '/qualidade/modelos/criterios/radiofarmacos', {'substituir': '1'})
        con = conectar(self.app.config['DATABASE'])
        ativos = [r['nome'] for r in con.execute('SELECT nome FROM cq_forn_criterios WHERE ativo=1')]
        self.assertEqual(sorted(ativos), sorted(n for n, _d, _p in cat2.CRITERIOS['radiofarmacos']['criterios']))
        con.close()
        self.post(c, '/qualidade/modelos/perguntas/medicina_nuclear')
        con = conectar(self.app.config['DATABASE'])
        self.assertEqual(con.execute('SELECT COUNT(*) FROM cq_sat_perguntas').fetchone()[0], len(cat2.PERGUNTAS['medicina_nuclear']['perguntas']))
        con.close()

    def test_protocolos_fluxo_de_trabalho(self):
        c = self.cliente()
        self.assertEqual(self.post(c, '/qualidade/protocolos/modelos-todos').status_code, 302)
        lista = self.texto(self.abrir(c, '/qualidade/protocolos'))
        for m in pops.POPS.values():
            self.assertIn(m['codigo'], lista)
        from app.db import conectar
        con = conectar(self.app.config['DATABASE'])
        pid = con.execute("SELECT id FROM cq_protocolos WHERE modelo='administracao'").fetchone()['id']
        con.close()
        pagina = self.texto(self.abrir(c, '/qualidade/protocolos/%d' % pid))
        self.assertIn('Administração de radiofármacos', pagina)
        dados = {'codigo': 'POP-006', 'titulo': 'Administração de radiofármacos', 'passos': 'Passo um\nPasso dois', 'revisado_por': 'Fulano'}
        self.post(c, '/qualidade/protocolos/%d/salvar' % pid, dados)
        self.post(c, '/qualidade/protocolos/%d/aprovar' % pid, {'aprovado_por': 'Dra. Teste'})
        con = conectar(self.app.config['DATABASE'])
        p = con.execute('SELECT * FROM cq_protocolos WHERE id=?', (pid,)).fetchone()
        self.assertEqual((p['status'], p['versao'], p['aprovado_por']), ('APROVADO', 1, 'Dra. Teste'))
        self.assertTrue(p['proxima_revisao'])
        con.close()
        self.post(c, '/qualidade/protocolos/%d/salvar' % pid, dict(dados, passos='Passo um\nPasso dois\nPasso três'))
        con = conectar(self.app.config['DATABASE'])
        p = con.execute('SELECT * FROM cq_protocolos WHERE id=?', (pid,)).fetchone()
        self.assertEqual((p['status'], p['versao']), ('RASCUNHO', 2))
        con.close()
        r = self.abrir(c, '/qualidade/protocolos/%d.pdf' % pid)
        self.assertEqual(r.mimetype, 'application/pdf')
        self.assertNotIn('attachment', r.headers.get('Content-Disposition', ''))
        r2 = self.abrir(c, '/qualidade/protocolos/%d.pdf?baixar=1' % pid)
        self.assertIn('attachment', r2.headers['Content-Disposition'])
        self.assertEqual(self.post(c, '/qualidade/protocolos/modelo/nao_existe').status_code, 302)

    def test_pdfs_com_validacao_e_assinatura(self):
        c = self.cliente()
        r = self.post(c, '/qualidade/modelos/problema/glosa', {'destino': 'pdca'})
        pid = int(re.search(r'/pdca/(\d+)', r.headers['Location']).group(1))
        self.post(c, '/qualidade/modelos/riscos/radioprotecao')
        r = self.post(c, '/qualidade/modelos/swot/servico')
        aid = int(re.search(r'a=(\d+)', r.headers['Location']).group(1))
        r = self.post(c, '/qualidade/modelos/fluxograma/derramamento')
        fid = int(re.search(r'/fluxogramas/(\d+)', r.headers['Location']).group(1))
        self.post(c, '/qualidade/modelos/organograma/radioprotecao')
        self.post(c, '/qualidade/modelos/plano/radioprotecao_anual')
        self.post(c, '/qualidade/protocolos/modelos-todos')
        urls = ['/qualidade/pdca/%d.pdf' % pid, '/qualidade/ishikawa.pdf?p=%d' % pid, '/qualidade/porques.pdf?p=%d' % pid, '/qualidade/gut.pdf',
                '/qualidade/plano.pdf', '/qualidade/riscos.pdf', '/qualidade/swot/%d.pdf' % aid, '/qualidade/fluxogramas/%d.pdf' % fid,
                '/qualidade/organograma.pdf', '/qualidade/indicadores.pdf', '/qualidade/pareto.pdf', '/qualidade/ocorrencias.pdf',
                '/qualidade/fornecedores/relatorio.pdf', '/qualidade/satisfacao/relatorio.pdf', '/qualidade/protocolos/lista-mestra.pdf']
        for url in urls:
            r = self.abrir(c, url)
            corpo = r.get_data()
            self.assertEqual(r.mimetype, 'application/pdf', url)
            self.assertTrue(corpo.startswith(b'%PDF'), url)
            self.assertIn(b'Assinatura', corpo, 'sem o quadro de validação: ' + url)
            self.assertIn(b'Parecer da valida', corpo, url)
        self.assertEqual(self.abrir(c, '/qualidade/ishikawa.pdf?p=%d' % pid).get_data()[:4], b'%PDF')
        self.assertEqual(c.get('/qualidade/ishikawa.pdf?p=99999').status_code, 404)
        self.assertEqual(c.get('/qualidade/protocolos/99999.pdf').status_code, 404)

    def test_sem_permissao_nao_abre_protocolos(self):
        self.criar_usuario('SEMQUAL', modulos=['agenda'])
        c = self.cliente('SEMQUAL', 'senha123')
        r = c.get('/qualidade/protocolos')
        self.assertIn(r.status_code, (302, 403))
        self.assertIn(self.post(c, '/qualidade/protocolos/modelos-todos').status_code, (302, 403))


if __name__ == '__main__':
    unittest.main()


class Epidemio(Base):
    def test_perfil_epidemiologico_tela_pdf_e_calculos(self):
        from datetime import date
        from app import db as dbmod
        from app import qualidade_epidemio as epi
        con = dbmod.conectar(self.app.config['DATABASE'])
        hoje = date.today().isoformat()
        con.execute("INSERT INTO clientes (nome, data_nasc, sexo, cidade, uf, bairro) VALUES ('EPI A', '1960-01-01', 'F', 'Governador Valadares', 'MG', 'Centro')")
        a = con.execute("SELECT id FROM clientes WHERE nome='EPI A'").fetchone()[0]
        con.execute("INSERT INTO clientes (nome, data_nasc, sexo, cidade, uf) VALUES ('EPI B', '2000-06-01', 'M', 'Ipatinga', 'MG')")
        b = con.execute("SELECT id FROM clientes WHERE nome='EPI B'").fetchone()[0]
        for cid, nome, exame in ((a, 'EPI A', 'MIBI'), (a, 'EPI A', 'ÓSSEA'), (b, 'EPI B', 'MIBI')):
            con.execute("INSERT INTO realizacoes (data, cliente_id, paciente, convenio, exame, medico, cid) VALUES (?,?,?,?,?,?,?)", (hoje, cid, nome, 'SUS', exame, 'DR X', 'I25'))
        con.commit()
        pf = epi.perfil(con, date.fromisoformat(hoje), date.fromisoformat(hoje))
        con.close()
        self.assertEqual(pf['pacientes'], 2)
        self.assertEqual(pf['total_exames'], 3)
        self.assertEqual(pf['pacientes_com_mais_de_um'], 1)
        self.assertEqual({x['rotulo']: x['n'] for x in pf['sexo']}, {'Feminino': 1, 'Masculino': 1})
        self.assertEqual(pf['exames'][0]['rotulo'], 'MIBI')
        self.assertEqual({x['faixa']: x['F'] for x in pf['piramide']}['60 a 69'], 1)
        c = self.cliente()
        pagina = self.texto(c.get('/qualidade/epidemiologico?de=%s&ate=%s' % (hoje, hoje)))
        self.assertIn('Pirâmide etária', pagina)
        self.assertIn('GOVERNADOR VALADARES', pagina)
        r = c.get('/qualidade/epidemiologico.pdf?de=%s&ate=%s' % (hoje, hoje))
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_data().startswith(b'%PDF'))

    def _exame(self, con, data, exame, paciente, nasc=None, sexo=None, peso=None, altura=None, cid='I25', cliente=None):
        con.execute('INSERT INTO realizacoes (data, cliente_id, paciente, data_nasc, sexo, peso, altura, exame, cid) VALUES (?,?,?,?,?,?,?,?,?)',
                    (data, cliente, paciente, nasc, sexo, peso, altura, exame, cid))

    def test_capitulo_cid(self):
        from app import qualidade_epidemio as epi
        self.assertIn('Neoplasias', epi._capitulo_cid('C50'))
        self.assertIn('Neoplasias', epi._capitulo_cid('D48'))
        self.assertIn('Sangue', epi._capitulo_cid('D50'))
        self.assertIn('Olho', epi._capitulo_cid('H59'))
        self.assertIn('Ouvido', epi._capitulo_cid('H65'))
        self.assertEqual(epi._capitulo_cid('I25.1'), 'IX - Aparelho circulatório')
        self.assertIn('Neoplasias', epi._capitulo_cid(' c 50.1 '))
        self.assertEqual(epi._capitulo_cid(''), 'Sem CID')
        self.assertEqual(epi._capitulo_cid(None), 'Sem CID')
        self.assertEqual(epi._capitulo_cid('C5'), 'Sem CID')

    def test_imc_em_cm_e_em_metros_e_crianca_fora(self):
        from datetime import date
        from app import db as dbmod
        from app import qualidade_epidemio as epi
        con = dbmod.conectar(self.app.config['DATABASE'])
        dia = '2025-03-10'
        self._exame(con, dia, 'MIBI', 'IMC CM', nasc='1980-01-01', peso=90, altura=180)        # IMC 27,8
        self._exame(con, dia, 'MIBI', 'IMC M', nasc='1980-01-01', peso=90, altura=1.80)        # IMC 27,8
        self._exame(con, dia, 'MIBI', 'IMC MAGRO', nasc='1990-01-01', peso=50, altura=175)     # IMC 16,3
        self._exame(con, dia, 'MIBI', 'CRIANCA', nasc='2015-01-01', peso=35, altura=1.40)      # 10 anos: fora do IMC
        self._exame(con, dia, 'MIBI', 'SEM PESO', nasc='1990-01-01', peso=None, altura=170)    # sem peso: fora do IMC
        con.commit()
        pf = epi.perfil(con, date(2025, 3, 10), date(2025, 3, 10))
        con.close()
        imc = {x['rotulo']: x['n'] for x in pf['imc']}
        self.assertEqual(imc['Sobrepeso (25 a 29,9)'], 2)
        self.assertEqual(imc['Baixo peso (< 18,5)'], 1)
        self.assertEqual(sum(imc.values()), 3)
        self.assertEqual(pf['imc_media'], 24.0)
        self.assertEqual({x['rotulo']: x['n'] for x in pf['qualidade_dado']}['Exames com peso e altura'], 4)
        self.assertEqual((pf['idade_por_exame'][0]['rotulo'], pf['idade_por_exame'][0]['n']), ('MIBI', 5))
        self.assertEqual(pf['exames_por_sexo'][0]['N'], 5)

    def test_procedencia_local_capitulos_e_pdfs(self):
        from app import db as dbmod
        from app import qualidade_epidemio as epi
        from datetime import date
        con = dbmod.conectar(self.app.config['DATABASE'])
        dia = '2025-03-11'
        con.execute("INSERT INTO clientes (nome, sexo, cidade, uf) VALUES ('PROC A', 'F', 'GOVERNADÓR  VALADARES', 'MG')")
        con.execute("INSERT INTO clientes (nome, sexo, cidade, uf) VALUES ('PROC B', 'M', 'Ipatinga', 'MG')")
        con.execute("INSERT INTO clientes (nome, sexo, cidade, uf) VALUES ('PROC C', 'M', '', '')")
        ids = {n: con.execute('SELECT id FROM clientes WHERE nome=?', (n,)).fetchone()[0] for n in ('PROC A', 'PROC B', 'PROC C')}
        for n, cid in (('PROC A', 'C50'), ('PROC B', 'H65'), ('PROC C', '')):
            self._exame(con, dia, 'RIM', n, nasc='1970-01-01', cid=cid, cliente=ids[n], sexo='F' if n == 'PROC A' else 'M')
        con.commit()
        pf = epi.perfil(con, date(2025, 3, 11), date(2025, 3, 11))
        con.close()
        proc = {x['rotulo']: x['n'] for x in pf['procedencia_local']}
        self.assertEqual(proc, {'Mesma cidade da clínica': 1, 'Outras cidades': 1, 'Não informado': 1})
        capit = {x['rotulo'] for x in pf['cid_capitulos']}
        self.assertTrue({'II - Neoplasias', 'VIII - Ouvido', 'Sem CID'} <= capit)
        c = self.cliente()
        pagina = self.texto(c.get('/qualidade/epidemiologico?de=%s&ate=%s' % (dia, dia)))
        self.assertIn('mesma cidade × outras cidades', pagina)
        r = c.get('/qualidade/epidemiologico.pdf?de=%s&ate=%s' % (dia, dia))
        self.assertTrue(r.get_data().startswith(b'%PDF'))
        r = c.get('/ona/relatorio.pdf?de=%s&ate=%s' % (dia, dia))
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_data().startswith(b'%PDF'))
