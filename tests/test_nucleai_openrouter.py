"""Seleção e failover OpenRouter com SQLite isolado e transporte falso, sem internet."""
import io
import json
import os
import sqlite3
import tempfile
import unittest
import urllib.error
from datetime import datetime, timedelta
from unittest import mock

from app import llm, nucleai_ia as ia


def resposta(texto='OK'):
    return {'choices': [{'message': {'role': 'assistant', 'content': texto}}],
            'usage': {'prompt_tokens': 3, 'completion_tokens': 2, 'total_tokens': 5}}


class ModelosETrocas(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.row_factory = sqlite3.Row
        self.db.execute('CREATE TABLE config (chave TEXT PRIMARY KEY, valor TEXT)')
        self.addCleanup(self.db.close)
        bloqueio = mock.patch('urllib.request.urlopen', side_effect=AssertionError('Teste tentou acessar a internet'))
        bloqueio.start()
        self.addCleanup(bloqueio.stop)
        ia.salvar_modelos(self.db, [{'slug': 'google/primeiro', 'ativo': True},
                                    {'slug': 'openai/desligado', 'ativo': False},
                                    {'slug': 'openai/segundo', 'ativo': True}])

    def gerar(self, baixar):
        return ia.gerar_com_troca(self.db, 'sistema', [{'role': 'user', 'content': 'oi'}], baixar=baixar)

    def test_migracao_uma_vez_preserva_modelo_e_lista_vazia(self):
        self.db.execute("DELETE FROM config WHERE chave='nucleai_llm_modelos'")
        ia.definir(self.db, 'nucleai_llm_modelo', 'gemini-2.0-flash')
        self.assertEqual(ia.modelos(self.db), [{'slug': 'google/gemini-2.0-flash', 'ativo': True}])
        ia.definir(self.db, 'nucleai_llm_modelo', 'google/outro')
        self.assertEqual(ia.modelo(self.db), 'google/gemini-2.0-flash')
        ia.salvar_modelos(self.db, [])
        self.assertEqual(ia.modelos(self.db), [])

    def test_ordem_persistida_e_somente_primeiro_ativo(self):
        lista = list(reversed(ia.modelos(self.db)))
        ia.salvar_modelos(self.db, lista)
        self.assertEqual(ia.modelos(self.db), lista)
        b = mock.Mock(return_value=resposta())
        self.assertEqual(self.gerar(b)['modelo'], 'openai/segundo')
        self.assertEqual(b.call_count, 1)

    def test_troca_429_402_pausa_e_gancho(self):
        for codigo in (429, 402):
            with self.subTest(codigo=codigo):
                ia.definir(self.db, 'nucleai_llm_pausas', '{}')
                erro = urllib.error.HTTPError('u', codigo, 'segredo', {}, None)
                b = mock.Mock(side_effect=[erro, resposta()])
                with mock.patch('app.nucleai_trocas.registrar_troca') as gancho:
                    r = self.gerar(b)
                self.assertEqual(r['modelo'], 'openai/segundo')
                pedidos = [json.loads(c.args[2]) for c in b.call_args_list]
                self.assertEqual([p['model'] for p in pedidos], ['google/primeiro', 'openai/segundo'])
                self.assertEqual(pedidos[0]['messages'], pedidos[1]['messages'])
                gancho.assert_called_once_with(self.db, 'google/primeiro', 'openai/segundo', 'cota', 'tentativa')
                self.assertIn('google/primeiro', ia.pausas(self.db))
                b = mock.Mock(return_value=resposta())
                self.assertEqual(self.gerar(b)['modelo'], 'openai/segundo')
                self.assertEqual(b.call_count, 1)

    def pausa_s(self, slug='google/primeiro'):
        return (datetime.strptime(ia.pausas(self.db)[slug], ia.FMT) - datetime.now()).total_seconds()

    def test_pausa_cresce_a_cada_falha_seguida_ate_o_teto_configurado(self):
        # um 429 passageiro não trava o modelo por 15 min: começa em 1 min, dobra e para no teto ("Pausa por cota")
        ia.definir(self.db, 'nucleai_llm_pausa_min', '3')
        for esperado in (60, 120, 180, 180):
            ia.definir(self.db, 'nucleai_llm_pausas', '{}')
            self.gerar(mock.Mock(side_effect=[urllib.error.HTTPError('u', 429, '', {}, None), resposta()]))
            self.assertAlmostEqual(self.pausa_s(), esperado, delta=3)

    def test_pausa_expira_retorna_preferencia_e_resposta_zera_as_falhas(self):
        self.gerar(mock.Mock(side_effect=[urllib.error.HTTPError('u', 429, '', {}, None), resposta()]))
        self.assertEqual(json.loads(ia.cfg(self.db, 'nucleai_llm_falhas')), {'google/primeiro': 1})
        ia.definir(self.db, 'nucleai_llm_pausas', json.dumps({'google/primeiro': (datetime.now() - timedelta(seconds=1)).strftime(ia.FMT)}))
        self.assertEqual(self.gerar(mock.Mock(return_value=resposta()))['modelo'], 'google/primeiro')
        self.assertEqual(json.loads(ia.cfg(self.db, 'nucleai_llm_falhas')), {})

    def corpo_429(self, mensagem, **extra):
        corpo = {'error': {'message': mensagem, 'code': 429}}
        corpo['error'].update(extra)
        return urllib.error.HTTPError('u', 429, 'x', {}, io.BytesIO(json.dumps(corpo).encode()))

    def test_limite_da_conta_pausa_todos_os_gratuitos_e_nao_gasta_mais_pedidos(self):
        ia.salvar_modelos(self.db, [{'slug': 'google/a:free', 'ativo': True}, {'slug': 'baidu/b:free', 'ativo': True},
                                    {'slug': 'x/c:free', 'ativo': True}])
        b = mock.Mock(side_effect=[self.corpo_429('Rate limit exceeded: free-models-per-day. Add 10 credits to unlock 1000 free model requests per day')])
        with self.assertRaises(llm.ErroLLM) as cm:
            self.gerar(b)
        self.assertEqual(b.call_count, 1)          # os outros gratuitos dividem o limite: nem tenta
        self.assertEqual((cm.exception.tipo, cm.exception.escopo), ('cota', 'conta_dia'))
        self.assertIn('free-models-per-day', cm.exception.detalhe)
        self.assertEqual(set(ia.pausas(self.db)), {'google/a:free', 'baidu/b:free', 'x/c:free'})
        self.assertGreater(self.pausa_s('baidu/b:free'), 60)    # até a renovação, não 1 minuto
        ult = ia.ultimo_erro(self.db)
        self.assertEqual((ult['modelo'], ult['escopo']), ('google/a:free', 'conta_dia'))
        self.assertTrue(cm.exception.retorno)

    def test_limite_da_conta_ainda_tenta_modelo_pago(self):
        ia.salvar_modelos(self.db, [{'slug': 'google/a:free', 'ativo': True}, {'slug': 'x/c:free', 'ativo': True},
                                    {'slug': 'openai/pago', 'ativo': True}])
        b = mock.Mock(side_effect=[self.corpo_429('Rate limit exceeded: free-models-per-min'), resposta()])
        self.assertEqual(self.gerar(b)['modelo'], 'openai/pago')
        self.assertEqual([json.loads(c.args[2])['model'] for c in b.call_args_list], ['google/a:free', 'openai/pago'])

    def test_limite_so_do_modelo_ainda_troca_para_o_proximo_gratuito(self):
        ia.salvar_modelos(self.db, [{'slug': 'google/a:free', 'ativo': True}, {'slug': 'x/c:free', 'ativo': True}])
        b = mock.Mock(side_effect=[self.corpo_429('Provider returned error', metadata={'provider_name': 'Google AI Studio',
                                                                                   'raw': 'is temporarily rate-limited upstream'}),
                                   resposta()])
        self.assertEqual(self.gerar(b)['modelo'], 'x/c:free')
        self.assertEqual(set(ia.pausas(self.db)), {'google/a:free'})
        self.assertEqual(ia.ultimo_erro(self.db)['escopo'], 'modelo')

    def test_modelo_inexistente_404_troca_e_pausa(self):
        b = mock.Mock(side_effect=[urllib.error.HTTPError('u', 404, 'x', {}, io.BytesIO(b'{"error":{"message":"No endpoints found that support tool use"}}')),
                                   resposta()])
        self.assertEqual(self.gerar(b)['modelo'], 'openai/segundo')
        self.assertIn('google/primeiro', ia.pausas(self.db))
        self.assertIn('tool use', ia.ultimo_erro(self.db)['detalhe'])

    def test_troca_servidor_408_e_timeout_sem_pausa(self):
        for erro in (urllib.error.HTTPError('u', 503, '', {}, None),
                     urllib.error.HTTPError('u', 408, '', {}, None), TimeoutError('demorou'),
                     urllib.error.URLError(TimeoutError('demorou'))):
            with self.subTest(erro=type(erro).__name__):
                b = mock.Mock(side_effect=[erro, resposta()])
                self.assertEqual(self.gerar(b)['modelo'], 'openai/segundo')
                self.assertEqual(ia.pausas(self.db), {})

    def test_erros_permanentes_e_rede_sem_timeout_nao_trocam(self):
        for erro in (urllib.error.HTTPError('u', 401, '', {}, None), urllib.error.URLError('sem rota')):
            b = mock.Mock(side_effect=erro)
            with self.assertRaises(llm.ErroLLM):
                self.gerar(b)
            self.assertEqual(b.call_count, 1)

    def test_todos_falhando_repassa_erro_e_todos_pausados_nao_chamam_rede(self):
        b = mock.Mock(side_effect=urllib.error.HTTPError('u', 402, '', {}, None))
        with self.assertRaises(llm.ErroLLM) as cm:
            self.gerar(b)
        self.assertEqual(cm.exception.tipo, 'cota')
        self.assertEqual(b.call_count, 2)
        b.reset_mock()
        with self.assertRaises(llm.ErroLLM) as cm:
            self.gerar(b)
        self.assertEqual(cm.exception.tipo, 'cota')
        b.assert_not_called()

    def test_nenhum_ativo_nao_chama_rede(self):
        ia.salvar_modelos(self.db, [])
        b = mock.Mock()
        with self.assertRaises(llm.ErroLLM):
            self.gerar(b)
        b.assert_not_called()

    def test_timeout_configurado_chega_ao_transporte(self):
        ia.definir(self.db, 'nucleai_llm_timeout_s', '4')
        with mock.patch.dict(os.environ, {llm.VAR_CHAVE: 'chave-ficticia'}), mock.patch.object(llm, '_baixar_json', return_value=resposta()) as b:
            ia.gerar_com_troca(self.db, 's', [])
        self.assertEqual(b.call_args.kwargs['timeout'], 4)


class ChaveEmArquivo(unittest.TestCase):
    def test_arquivo_precede_ambiente_troca_apaga_e_nao_vaza(self):
        with tempfile.TemporaryDirectory() as pasta:
            db = sqlite3.connect(os.path.join(pasta, 'teste.db'))
            try:
                with mock.patch.dict(os.environ, {llm.VAR_CHAVE: 'ambiente-ficticio'}):
                    self.assertEqual(llm.chave(db), 'ambiente-ficticio')
                    llm.salvar_chave('sk-or-ficticia-1234', db)
                    self.assertEqual(llm.chave(db), 'sk-or-ficticia-1234')
                    with open(os.path.join(pasta, 'nucleai', 'openrouter_chave.txt'), encoding='utf-8') as f:
                        self.assertEqual(f.read(), 'sk-or-ficticia-1234')
                    self.assertEqual(llm.resumo_chave(db), 'configurada, termina em ••••1234')
                    b = mock.Mock(side_effect=urllib.error.HTTPError('u', 401, 'sk-or-ficticia-1234', {}, None))
                    with self.assertRaises(llm.ErroLLM) as cm:
                        llm.gerar(llm.MODELO_PADRAO, 's', [], baixar=b, db=db)
                    self.assertNotIn('sk-or-ficticia-1234', str(cm.exception))
                    self.assertNotIn('sk-or-ficticia-1234', b.call_args.args[2].decode())
                    llm.salvar_chave('substituta-5678', db)
                    self.assertEqual(llm.chave(db), 'substituta-5678')
                    llm.salvar_chave(None, db)
                    self.assertFalse(os.path.exists(llm.caminho_chave(db)))
                    self.assertEqual(llm.chave(db), 'ambiente-ficticio')
            finally:
                db.close()
