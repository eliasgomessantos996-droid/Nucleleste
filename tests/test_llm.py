"""Cliente da IA (OpenRouter): resposta, corpo enviado, mapeamento de erros e teste de conectividade.
Nenhum teste acessa a internet: a rede é sempre substituída por `baixar` falso ou bloqueada."""
import io
import json
import os
import unittest
import urllib.error
from unittest import mock

from app import llm

CHAVE = 'segredo-de-teste-987'


def falso(resposta=None, erro=None):
    """Substitui `baixar`: guarda as chamadas e devolve `resposta` ou levanta `erro`."""
    chamadas = []

    def baixar(url, cabecalhos, corpo=None):
        chamadas.append({'url': url, 'cabecalhos': dict(cabecalhos), 'corpo': corpo})
        if erro is not None:
            raise erro
        return resposta
    baixar.chamadas = chamadas
    return baixar


def http(codigo):
    return urllib.error.HTTPError('https://exemplo.invalid/', codigo, 'msg', {}, io.BytesIO(b'corpo com detalhes'))


def resposta_texto(texto='Olá!', tokens=12):
    return {'choices': [{'message': {'role': 'assistant', 'content': texto}}],
            'usage': {'total_tokens': tokens, 'prompt_tokens': 8, 'completion_tokens': tokens - 8}}


HISTORICO = [{'role': 'user', 'content': 'Oi'}, {'role': 'assistant', 'content': 'Oi, tudo bem?'}]


class GerarResposta(unittest.TestCase):
    def setUp(self):
        p = mock.patch.dict(os.environ, {llm.VAR_CHAVE: CHAVE})
        p.start()
        self.addCleanup(p.stop)

    def test_texto_simples(self):
        r = llm.gerar(llm.MODELO_PADRAO, 'sistema', HISTORICO, baixar=falso(resposta_texto('Tudo certo', 30)))
        self.assertEqual(r['texto'], 'Tudo certo')
        self.assertEqual((r['tokens_entrada'], r['tokens_saida'], r['tokens_total']), (8, 22, 30))
        self.assertEqual(r['tokens'], 30)
        self.assertEqual(r['modelo'], llm.MODELO_PADRAO)

    def test_resposta_com_function_call(self):
        j = {'choices': [{'message': {'role': 'assistant', 'content': None, 'tool_calls': [
            {'id': 'call_1', 'type': 'function', 'function': {'name': 'buscar_agenda', 'arguments': '{"data":"2026-11-12"}'}}]}}],
            'usage': {'total_tokens': 7}}
        r = llm.gerar(llm.MODELO_PADRAO, 'sistema', HISTORICO, ferramentas=[{'type': 'function', 'function': {'name': 'buscar_agenda'}}],
                      baixar=falso(j))
        self.assertEqual(r['texto'], '')
        self.assertEqual(r['chamadas'], [{'id': 'call_1', 'nome': 'buscar_agenda', 'args': {'data': '2026-11-12'}}])
        self.assertEqual(r['tokens'], 7)

    def test_sem_usage_tokens_zero(self):
        j = {'choices': [{'message': {'role': 'assistant', 'content': 'x'}}]}
        self.assertEqual(llm.gerar(llm.MODELO_PADRAO, 's', HISTORICO, baixar=falso(j))['tokens'], 0)

    def test_corpo_e_cabecalhos(self):
        b = falso(resposta_texto())
        llm.gerar(llm.MODELO_PADRAO, 'Você é a NucleAI.', HISTORICO, baixar=b)
        c = b.chamadas[0]
        self.assertEqual(c['url'], llm.BASE)
        self.assertEqual(c['cabecalhos']['Content-Type'], 'application/json')
        self.assertEqual(c['cabecalhos']['Authorization'], 'Bearer ' + CHAVE)
        corpo = json.loads(c['corpo'].decode('utf-8'))
        self.assertEqual(corpo['messages'], [{'role': 'system', 'content': 'Você é a NucleAI.'}] + HISTORICO)
        self.assertEqual(corpo['model'], llm.MODELO_PADRAO)
        self.assertEqual(corpo['temperature'], 0.2)
        self.assertEqual(corpo['max_tokens'], 1500)
        self.assertEqual(c['cabecalhos']['HTTP-Referer'], 'https://nucleleste.invalid')
        self.assertEqual(c['cabecalhos']['X-Title'], 'Nucleleste')
        self.assertNotIn('tools', corpo)

    def test_tools_so_quando_passadas(self):
        b = falso(resposta_texto())
        llm.gerar(llm.MODELO_PADRAO, 's', HISTORICO, ferramentas=[{'type': 'function', 'function': {'name': 'f'}}], baixar=b)
        corpo = json.loads(b.chamadas[0]['corpo'].decode('utf-8'))
        self.assertEqual(corpo['tools'], [{'type': 'function', 'function': {'name': 'f'}}])

    def test_chave_nao_aparece_em_erro(self):
        for erro in (http(403), http(429), http(503), urllib.error.URLError('falha'),
                     TimeoutError('demorou')):
            with self.assertRaises(llm.ErroLLM) as cm:
                llm.gerar(llm.MODELO_PADRAO, 's', HISTORICO, baixar=falso(erro=erro))
            self.assertNotIn(CHAVE, str(cm.exception))

    def test_erros_mapeados(self):
        casos = ((http(429), 'cota'), (http(402), 'cota'), (http(408), 'servidor'), (TimeoutError('x'), 'rede'), (http(503), 'servidor'), (http(403), 'resposta'),
                 (urllib.error.URLError('x'), 'rede'))
        for erro, tipo in casos:
            with self.subTest(tipo=tipo):
                with self.assertRaises(llm.ErroLLM) as cm:
                    llm.gerar(llm.MODELO_PADRAO, 's', HISTORICO, baixar=falso(erro=erro))
                self.assertEqual(cm.exception.tipo, tipo)

    def erro_com_corpo(self, codigo, corpo, cabecalhos=None):
        dado = json.dumps(corpo) if not isinstance(corpo, (str, bytes)) else corpo
        return urllib.error.HTTPError('https://exemplo.invalid/', codigo, 'x', cabecalhos or {}, io.BytesIO(dado.encode() if isinstance(dado, str) else dado))

    def levantado(self, erro):
        with self.assertRaises(llm.ErroLLM) as cm:
            llm.gerar(llm.MODELO_PADRAO, 's', HISTORICO, baixar=falso(erro=erro))
        return cm.exception

    def test_cota_diz_de_onde_veio_o_limite_e_guarda_o_motivo(self):
        dia = self.levantado(self.erro_com_corpo(429, {'error': {'message': 'Rate limit exceeded: free-models-per-day', 'code': 429}}))
        self.assertEqual((dia.tipo, dia.escopo), ('cota', 'conta_dia'))
        self.assertIn('free-models-per-day', dia.detalhe)
        minuto = self.levantado(self.erro_com_corpo(429, {'error': {'message': 'Rate limit exceeded: free-models-per-min', 'code': 429}}))
        self.assertEqual(minuto.escopo, 'conta_min')
        prov = self.levantado(self.erro_com_corpo(429, {'error': {'message': 'Provider returned error', 'code': 429,
                                                                 'metadata': {'provider_name': 'Google AI Studio', 'raw': 'temporarily rate-limited upstream'}}}))
        self.assertEqual(prov.escopo, 'modelo')
        self.assertIn('Google AI Studio', prov.detalhe)
        self.assertEqual(self.levantado(self.erro_com_corpo(402, {'error': {'message': 'Insufficient credits', 'code': 402}})).escopo, 'credito')

    def test_dica_de_espera_vem_do_cabecalho_ou_do_corpo(self):
        self.assertEqual(self.levantado(self.erro_com_corpo(429, {}, {'Retry-After': '30'})).pausa_s, 30)
        import time
        reset_ms = str(int((time.time() + 120) * 1000))
        e = self.levantado(self.erro_com_corpo(429, {'error': {'message': 'x', 'metadata': {'headers': {'X-RateLimit-Reset': reset_ms}}}}))
        self.assertAlmostEqual(e.pausa_s, 120, delta=3)
        self.assertIsNone(self.levantado(self.erro_com_corpo(429, 'corpo sem json')).pausa_s)

    def test_erro_dentro_de_resposta_200_tambem_e_classificado(self):
        j = {'error': {'code': 429, 'message': 'Rate limit exceeded: free-models-per-day'}}
        e = self.levantado_sem_http(j)
        self.assertEqual((e.tipo, e.escopo), ('cota', 'conta_dia'))

    def levantado_sem_http(self, resposta):
        with self.assertRaises(llm.ErroLLM) as cm:
            llm.gerar(llm.MODELO_PADRAO, 's', HISTORICO, baixar=falso(resposta))
        return cm.exception

    def test_chave_nao_vai_para_o_detalhe(self):
        e = self.levantado(self.erro_com_corpo(429, {'error': {'message': 'chave %s invalida' % CHAVE, 'code': 429}}))
        self.assertNotIn(CHAVE, e.detalhe)
        self.assertNotIn(CHAVE, str(e))

    def test_404_e_modelo_indisponivel(self):
        e = self.levantado(self.erro_com_corpo(404, {'error': {'message': 'No endpoints found that support tool use'}}))
        self.assertEqual(e.tipo, 'indisponivel')
        self.assertIn('tool use', e.detalhe)

    def test_json_sem_choices_e_resposta(self):
        with self.assertRaises(llm.ErroLLM) as cm:
            llm.gerar(llm.MODELO_PADRAO, 's', HISTORICO, baixar=falso({'choices': []}))
        self.assertEqual(cm.exception.tipo, 'resposta')


class SemChave(unittest.TestCase):
    def test_sem_chave_nao_toca_na_rede(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(llm.VAR_CHAVE, None)
            with mock.patch('urllib.request.urlopen', side_effect=AssertionError('rede chamada')):
                with self.assertRaises(llm.ErroLLM) as cm:
                    llm.gerar(llm.MODELO_PADRAO, 's', HISTORICO)
        self.assertEqual(cm.exception.tipo, 'sem_chave')

    def test_chave_so_espacos_conta_como_sem_chave(self):
        with mock.patch.dict(os.environ, {llm.VAR_CHAVE: '   '}):
            self.assertIsNone(llm.chave())


class Conectado(unittest.TestCase):
    def setUp(self):
        llm.limpar_cache()
        self.addCleanup(llm.limpar_cache)

    def test_http_404_conta_como_conectado(self):
        self.assertTrue(llm.conectado(baixar=falso(erro=http(404))))

    def test_urlerror_desconectado(self):
        self.assertFalse(llm.conectado(baixar=falso(erro=urllib.error.URLError('sem rota'))))

    def test_cache_de_10_segundos(self):
        b = falso(resposta={})
        self.assertTrue(llm.conectado(baixar=b))
        self.assertTrue(llm.conectado(baixar=b))
        self.assertEqual(len(b.chamadas), 1)

    def test_limpar_cache_forca_nova_checagem(self):
        b = falso(resposta={})
        llm.conectado(baixar=b)
        llm.limpar_cache()
        llm.conectado(baixar=b)
        self.assertEqual(len(b.chamadas), 2)


if __name__ == '__main__':
    unittest.main()
