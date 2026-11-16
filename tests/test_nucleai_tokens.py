"""Testes novos da Etapa 7: Saúde da NucleAI (liga/desliga) e gráficos de gasto de tokens."""
import json
import unittest
from datetime import date, datetime, timedelta
from unittest import mock

from app import db as dbmod
from app import llm, nucleai_ia as ia, nucleai_motor as motor, nucleai_tokens, nucleai_trocas
from tests.test_chat_blindagens import Base


class FakeOpenRouter:
    """Mock do OpenRouter sem rede que devolve tokens de entrada/saída e modelo."""

    def __init__(self, resposta='Resposta simulada da IA. <<confianca:4>>',
                 modelo='google/gemini-2.5-flash', entrada=35, saida=25):
        self.resposta = resposta
        self.modelo = modelo
        self.entrada = entrada
        self.saida = saida
        self.pedidos = []

    def __call__(self, url, cabecalhos, corpo=None):
        self.pedidos.append(json.loads(corpo.decode('utf-8')) if corpo else None)
        total = self.entrada + self.saida
        return {
            'model': self.modelo,
            'choices': [{
                'message': {
                    'role': 'assistant',
                    'content': self.resposta
                }
            }],
            'usage': {
                'prompt_tokens': self.entrada,
                'completion_tokens': self.saida,
                'total_tokens': total
            }
        }


class TestNucleaiTokens(Base):

    def setUp(self):
        bloqueio = mock.patch('urllib.request.urlopen', side_effect=AssertionError('Tentou acessar a internet'))
        bloqueio.start()
        self.addCleanup(bloqueio.stop)

        self.admin = self.criar_usuario('ADM_TOKENS', [], admin=1)
        self.gerente = self.criar_usuario('GER_TOKENS', ['gerencia'])
        self.func = self.criar_usuario('FUNC_TOKENS', ['agenda'])

        con = dbmod.conectar(self.app.config['DATABASE'])
        try:
            for t in ('nucleai_tokens', 'nucleai_llm_log', 'nucleai_llm_uso', 'nucleai_llm_nivel',
                      'nucleai_llm_sessao', 'nucleai_treino_msgs', 'chat_mensagens'):
                con.execute(f'DELETE FROM {t}')
            con.execute("DELETE FROM config WHERE chave LIKE 'nucleai_%'")
            con.commit()
        finally:
            con.close()

        llm.limpar_cache()
        motor.BAIXAR = None
        motor.BAIXAR_CONEXAO = None

    def tearDown(self):
        motor.BAIXAR = None
        motor.BAIXAR_CONEXAO = None
        llm.limpar_cache()

    # ---------------------------------------------------------------- registro por pedido
    def test_registro_por_pedido(self):
        """Grava e confere todos os campos exigidos: usuário, modelo, tokens entrada/saída/total,
        tempo ms, se foi teste, data/hora."""
        con = dbmod.conectar(self.app.config['DATABASE'])
        try:
            agora_s = (datetime.now() - timedelta(minutes=5)).strftime(ia.FMT)
            nucleai_tokens.registrar(
                con,
                usuario='FUNC_TOKENS',
                modelo='google/gemini-2.5-flash',
                tokens_entrada=120,
                tokens_saida=80,
                tokens_total=200,
                tempo_ms=450,
                teste=False,
                criado_em=agora_s,
                usuario_id=self.func
            )

            r = con.execute('SELECT * FROM nucleai_tokens ORDER BY id DESC LIMIT 1').fetchone()
            self.assertIsNotNone(r)
            self.assertEqual(r['usuario'], 'FUNC_TOKENS')
            self.assertEqual(r['usuario_id'], self.func)
            self.assertEqual(r['modelo'], 'google/gemini-2.5-flash')
            self.assertEqual(r['tokens_entrada'], 120)
            self.assertEqual(r['tokens_saida'], 80)
            self.assertEqual(r['tokens_total'], 200)
            self.assertEqual(r['tempo_ms'], 450)
            self.assertEqual(r['teste'], 0)
            self.assertEqual(r['criado_em'], agora_s)

            # Registro com chat de teste e cálculo automático de tokens_total
            nucleai_tokens.registrar(
                con,
                usuario='ADM_TOKENS',
                modelo='anthropic/claude-3.5-sonnet',
                tokens_entrada=300,
                tokens_saida=150,
                tempo_ms=820,
                teste=True
            )
            r2 = con.execute('SELECT * FROM nucleai_tokens ORDER BY id DESC LIMIT 1').fetchone()
            self.assertEqual(r2['usuario'], 'ADM_TOKENS')
            self.assertEqual(r2['modelo'], 'anthropic/claude-3.5-sonnet')
            self.assertEqual(r2['tokens_entrada'], 300)
            self.assertEqual(r2['tokens_saida'], 150)
            self.assertEqual(r2['tokens_total'], 450)
            self.assertEqual(r2['tempo_ms'], 820)
            self.assertEqual(r2['teste'], 1)
        finally:
            con.close()

    # ---------------------------------------------------------------- agregações
    def test_agregacoes_modelo_dia_hora_usuario_geral(self):
        """Verifica todas as agregações: geral, por modelo, por dia, por hora, por usuário,
        maiores pedidos e histograma."""
        con = dbmod.conectar(self.app.config['DATABASE'])
        try:
            hoje = date.today().strftime('%Y-%m-%d')
            ontem = (date.today() - timedelta(days=1)).strftime('%Y-%m-%d')
            cinco_dias = (date.today() - timedelta(days=5)).strftime('%Y-%m-%d')

            # Pedido 1: hoje às 10:15 por ANA (total 150)
            nucleai_tokens.registrar(con, 'ANA', 'google/gemini-2.5-flash', 100, 50, 150, 200,
                                     teste=False, criado_em=f'{hoje} 10:15:00')
            # Pedido 2: hoje às 10:45 por ANA (total 300)
            nucleai_tokens.registrar(con, 'ANA', 'google/gemini-2.5-flash', 200, 100, 300, 400,
                                     teste=False, criado_em=f'{hoje} 10:45:00')
            # Pedido 3: hoje às 14:00 por BETO (total 1000)
            nucleai_tokens.registrar(con, 'BETO', 'meta/llama-3-70b', 500, 500, 1000, 800,
                                     teste=True, criado_em=f'{hoje} 14:00:00')
            # Pedido 4: ontem às 11:00 por CARLOS (total 600)
            nucleai_tokens.registrar(con, 'CARLOS', 'meta/llama-3-70b', 400, 200, 600, 500,
                                     teste=False, criado_em=f'{ontem} 11:00:00')
            # Pedido 5: 5 dias atrás às 16:00 por CARLOS (total 200)
            nucleai_tokens.registrar(con, 'CARLOS', 'google/gemini-2.5-flash', 150, 50, 200, 300,
                                     teste=False, criado_em=f'{cinco_dias} 16:00:00')

            # 1. Resumo Geral
            g_hoje = nucleai_tokens.resumo_geral(con, periodo='hoje')
            self.assertEqual(g_hoje['pedidos'], 3)
            self.assertEqual(g_hoje['tokens_total'], 1450)
            self.assertEqual(g_hoje['tokens_entrada'], 800)
            self.assertEqual(g_hoje['tokens_saida'], 650)
            self.assertEqual(g_hoje['usuarios'], 2)  # ANA e BETO

            g_todos = nucleai_tokens.resumo_geral(con, periodo='todos')
            self.assertEqual(g_todos['pedidos'], 5)
            self.assertEqual(g_todos['tokens_total'], 2250)
            self.assertEqual(g_todos['usuarios'], 3)

            # 2. Por Modelo
            mod_todos = nucleai_tokens.por_modelo(con, periodo='todos')
            self.assertEqual(len(mod_todos), 2)
            self.assertEqual(mod_todos[0]['modelo'], 'meta/llama-3-70b')
            self.assertEqual(mod_todos[0]['tokens_total'], 1600)
            self.assertEqual(mod_todos[0]['pedidos'], 2)
            self.assertEqual(mod_todos[1]['modelo'], 'google/gemini-2.5-flash')
            self.assertEqual(mod_todos[1]['tokens_total'], 650)
            self.assertEqual(mod_todos[1]['pedidos'], 3)

            # 3. Por Dia
            dias = nucleai_tokens.por_dia(con, periodo='todos')
            self.assertEqual(len(dias), 3)
            self.assertEqual(dias[0]['dia'], cinco_dias)
            self.assertEqual(dias[1]['dia'], ontem)
            self.assertEqual(dias[2]['dia'], hoje)
            self.assertEqual(dias[2]['tokens_total'], 1450)

            # 4. Por Hora
            horas_hoje = nucleai_tokens.por_hora(con, periodo='hoje')
            self.assertEqual(len(horas_hoje), 24)
            h10 = next(h for h in horas_hoje if h['hora'] == 10)
            self.assertEqual(h10['pedidos'], 2)
            self.assertEqual(h10['tokens_total'], 450)
            h14 = next(h for h in horas_hoje if h['hora'] == 14)
            self.assertEqual(h14['pedidos'], 1)
            self.assertEqual(h14['tokens_total'], 1000)
            h0 = next(h for h in horas_hoje if h['hora'] == 0)
            self.assertEqual(h0['pedidos'], 0)
            self.assertEqual(h0['tokens_total'], 0)

            # 5. Por Usuário
            usrs = nucleai_tokens.por_usuario(con, periodo='todos')
            self.assertEqual([u['usuario'] for u in usrs], ['BETO', 'CARLOS', 'ANA'])
            self.assertEqual(usrs[0]['tokens_total'], 1000)
            self.assertEqual(usrs[1]['tokens_total'], 800)
            self.assertEqual(usrs[2]['tokens_total'], 450)

            # 6. Maiores Pedidos
            top3 = nucleai_tokens.maiores_pedidos(con, periodo='todos', limite=3)
            self.assertEqual(len(top3), 3)
            self.assertEqual(top3[0]['tokens_total'], 1000)
            self.assertEqual(top3[0]['usuario'], 'BETO')
            self.assertTrue(top3[0]['teste'])
            self.assertEqual(top3[1]['tokens_total'], 600)
            self.assertEqual(top3[2]['tokens_total'], 300)

            # 7. Histograma: 150, 200, 300 (3 na faixa 101–300); 600 (1 na faixa 301–600); 1000 (1 na faixa 601–1200)
            hist = nucleai_tokens.histograma_pedidos(con, periodo='todos')
            self.assertTrue(any(f['faixa'] == '101–300' and f['pedidos'] == 3 for f in hist))
            self.assertTrue(any(f['faixa'] == '301–600' and f['pedidos'] == 1 for f in hist))
            self.assertTrue(any(f['faixa'] == '601–1200' and f['pedidos'] == 1 for f in hist))
        finally:
            con.close()

    # ---------------------------------------------------------------- indicadores de saúde
    def test_indicadores_saude(self):
        """Verifica os indicadores de saúde: estado, última resposta OK, tempo médio,
        taxa de erro, modelos em pausa e trocas de hoje."""
        con = dbmod.conectar(self.app.config['DATABASE'])
        try:
            # Estado em treino
            ia.definir_estado(con, ia.TREINO)
            ia.definir(con, 'nucleai_llm_ativo', '1')
            s1 = nucleai_tokens.indicadores_saude(con)
            self.assertEqual(s1['estado'], ia.TREINO)
            self.assertEqual(s1['estado_rotulo'], 'Em teste — só gerência')
            self.assertTrue(s1['ligada'])

            # Estado liberada
            ia.definir_estado(con, ia.LIBERADA)
            s2 = nucleai_tokens.indicadores_saude(con)
            self.assertEqual(s2['estado_rotulo'], 'Ligada para os usuários')

            # Estado desativada
            ia.desativar(con, 'ADMIN')
            s3 = nucleai_tokens.indicadores_saude(con)
            self.assertEqual(s3['estado_rotulo'], 'Desligada')

            # Última resposta OK e tempo médio hoje
            hoje_s = datetime.now().strftime(ia.FMT)
            ia.registrar_log(con, self.func, 'FUNC_TOKENS', 'Pergunta teste', 'Resposta OK', modo='IA')
            nucleai_tokens.registrar(con, 'FUNC_TOKENS', 'google/gemini-2.5-flash', 100, 50, 150,
                                     tempo_ms=300, criado_em=hoje_s)
            s4 = nucleai_tokens.indicadores_saude(con)
            self.assertNotEqual(s4['ultima_resposta_ok'], '—')
            self.assertIn('300 ms', s4['tempo_medio_hoje'])

            # Pausas por cota
            ia.definir(con, 'nucleai_llm_pausas', json.dumps({
                'google/gemini-2.5-flash': (datetime.now() + timedelta(minutes=15)).strftime(ia.FMT)
            }))
            s5 = nucleai_tokens.indicadores_saude(con)
            self.assertEqual(s5['modelos_pausa'], 1)

            # Trocas de hoje (usar nucleai_trocas.listar)
            nucleai_trocas.registrar_troca(con, 'google/gemini-2.5-flash', 'meta/llama-3', 'cota')
            s6 = nucleai_tokens.indicadores_saude(con)
            self.assertGreaterEqual(s6['trocas_hoje'], 1)
        finally:
            con.close()

    # ---------------------------------------------------------------- rotas e permissões
    def test_rota_tokens_bloqueada_para_nao_gerencia(self):
        """Usuário sem perfil de gerência é bloqueado em /nucleai/ia/tokens."""
        # 1. Sem login -> redireciona para /login
        c_anon = self.app.test_client()
        r_anon = c_anon.get('/nucleai/ia/tokens')
        self.assertEqual(r_anon.status_code, 302)
        self.assertIn('/login', r_anon.headers.get('Location', ''))

        # 2. Usuário comum (com módulo 'agenda', mas sem 'gerencia' e sem admin)
        c_func = self.cliente('FUNC_TOKENS', 'senha123')
        r_func = c_func.get('/nucleai/ia/tokens')
        # Redireciona para o Início por falta de permissão de módulo
        self.assertEqual(r_func.status_code, 302)
        self.assertNotEqual(r_func.status_code, 200)

        # 3. Usuário com módulo 'gerencia' entra com sucesso (200)
        c_ger = self.cliente('GER_TOKENS', 'senha123')
        r_ger = c_ger.get('/nucleai/ia/tokens')
        self.assertEqual(r_ger.status_code, 200)
        html = self.texto(r_ger)
        self.assertIn('Gasto de tokens', html)
        self.assertIn('Gasto por modelo', html)
        self.assertIn('Gasto por dia', html)
        self.assertIn('Gasto por hora do dia', html)
        self.assertIn('Gasto por usuário', html)
        self.assertIn('Histograma por tamanho de pedido', html)

        # 4. Formato JSON para gerência
        r_json = c_ger.get('/nucleai/ia/tokens?formato=json')
        self.assertEqual(r_json.status_code, 200)
        dados = r_json.get_json()
        self.assertIn('geral', dados)
        self.assertIn('modelos', dados)
        self.assertIn('dias', dados)
        self.assertIn('horas', dados)
        self.assertIn('usuarios', dados)
        self.assertIn('pedidos', dados)
        self.assertIn('histograma', dados)

    # ---------------------------------------------------------------- ligar / desligar pela tela com confirmação
    def test_rotas_saude_ligar_e_voltar_ao_teste(self):
        """Botões na área de saúde alternam o estado entre teste, ligada e desativada."""
        adm = self.cliente('ADM_TOKENS', 'senha123')
        with mock.patch('app.llm.chave', return_value='chave-falsa-teste'):
            con = dbmod.conectar(self.app.config['DATABASE'])
            try:
                ia.definir_estado(con, ia.TREINO)
                con.commit()
            finally:
                con.close()

            # 1. Ligar para os usuários (via confirmação direta na rota /liberar)
            r_lib = self.post(adm, '/nucleai/ia/liberar', {'confirmar': '1'})
            self.assertEqual(r_lib.status_code, 302)

            con = dbmod.conectar(self.app.config['DATABASE'])
            try:
                self.assertEqual(ia.estado(con), ia.LIBERADA)
                self.assertTrue(ia.ia_ligada(con))
            finally:
                con.close()

            # 2. Voltar ao teste
            r_tr = self.post(adm, '/nucleai/ia/treinar')
            self.assertEqual(r_tr.status_code, 302)

            con = dbmod.conectar(self.app.config['DATABASE'])
            try:
                self.assertEqual(ia.estado(con), ia.TREINO)
                self.assertTrue(ia.ia_ligada(con))
            finally:
                con.close()

            # 3. Desativar
            r_des = self.post(adm, '/nucleai/ia/desativar')
            self.assertEqual(r_des.status_code, 302)

            con = dbmod.conectar(self.app.config['DATABASE'])
            try:
                self.assertEqual(ia.estado(con), ia.DESATIVADA)
                self.assertFalse(ia.ia_ligada(con))
            finally:
                con.close()

    # ---------------------------------------------------------------- alternar entre IA e motor de regras
    def test_alternar_entre_ia_e_motor_de_regras(self):
        """Enquanto não estiver ligada, usuários comuns recebem o motor de regras;
        quando ligada, a IA responde e registra os tokens do pedido."""
        con = dbmod.conectar(self.app.config['DATABASE'])
        try:
            ia.definir_nivel(con, self.func, 2, 'ADM_TOKENS')
            con.commit()

            fake_llm = FakeOpenRouter(resposta='Esta é a IA da NucleAI respondendo! <<confianca:5>>',
                                      modelo='google/gemini-2.5-flash', entrada=40, saida=30)
            motor.BAIXAR = fake_llm

            with mock.patch('app.llm.chave', return_value='chave-falsa-teste'):
                # 1. IA em modo TREINO (só gerência testa; usuário comum não recebe IA)
                ia.definir_estado(con, ia.TREINO)
                ia.definir(con, 'nucleai_llm_ativo', '1')
                con.commit()

                resp_treino = motor.talvez_responder(con, self.func, 'Como preparo o MIBI?')
                # Em treino, talvez_responder devolve None para o usuário comum -> segue motor de regras
                self.assertIsNone(resp_treino)

                # 2. IA DESATIVADA -> também devolve None
                ia.desativar(con, 'ADM_TOKENS')
                con.commit()
                resp_desat = motor.talvez_responder(con, self.func, 'Como preparo o MIBI?')
                self.assertIsNone(resp_desat)

                # 3. IA LIGADA PARA OS USUÁRIOS (estado LIBERADA e ativo 1)
                ia.definir_estado(con, ia.LIBERADA)
                ia.definir(con, 'nucleai_llm_ativo', '1')
                con.commit()

                rc = self.app.test_request_context()
                rc.push()
                try:
                    resp_ligada = motor.talvez_responder(con, self.func, 'Como preparo o MIBI?')
                finally:
                    rc.pop()

                self.assertIsNotNone(resp_ligada)
                self.assertIn('mensagens', resp_ligada)
                self.assertFalse(resp_ligada.get('seguir_regras', False))
                texto_resp = resp_ligada['mensagens'][-1]['corpo']
                self.assertIn('Esta é a IA da NucleAI respondendo!', texto_resp)

                # Confere que o pedido foi registrado na tabela nucleai_tokens
                reg = con.execute('SELECT * FROM nucleai_tokens WHERE usuario="FUNC_TOKENS" ORDER BY id DESC LIMIT 1').fetchone()
                self.assertIsNotNone(reg)
                self.assertEqual(reg['tokens_entrada'], 40)
                self.assertEqual(reg['tokens_saida'], 30)
                self.assertEqual(reg['tokens_total'], 70)
                self.assertEqual(reg['teste'], 0)
                self.assertEqual(reg['modelo'], 'google/gemini-2.5-flash')

                # 4. Volta ao modo TREINO -> usuário comum volta imediatamente a receber motor de regras
                ia.definir_estado(con, ia.TREINO)
                con.commit()
                resp_volta = motor.talvez_responder(con, self.func, 'Como preparo o MIBI?')
                self.assertIsNone(resp_volta)
        finally:
            con.close()


if __name__ == '__main__':
    unittest.main()
