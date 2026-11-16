"""Testes da ETAPA 6: Chat de teste "Teste#XXXX" e memória compartilhada como manual.

Verifica:
1. Nome Teste#XXXX (4 dígitos aleatórios) e compatibilidade com Treinador#NNNN.
2. IA vê o usuário como Teste#XXXX no chat de teste.
3. Seções fixas da memória concreta (Quem sou, Ferramentas e como usar, Como agir, Preferências de usuários).
4. Todas as seções fixas presentes na instrução de sistema enviada a qualquer modelo, incluindo a regra de não revelar o modelo.
5. Contexto isolado por conversa: histórico de uma conversa não vaza para outra e some ao apagar.
6. Regra ensinada no chat de teste gravada em "Como agir", persistindo em outra conversa e após apagar a conversa, com suporte a versões e desfazer (reverter).
7. Gerência pode abrir várias conversas de teste, apagar cada uma e começar outra.
"""
from __future__ import annotations

import json
import unittest

from app import nucleai_conhecimento as conh
from app import nucleai_ferramentas as ferr
from app import nucleai_ia as ia
from app import nucleai_memoria as mem
from app import nucleai_motor as motor
from tests.test_nucleai_motor import MotorBase, OpenRouter


class TesteMemoriaManual(MotorBase):

    def setUp(self):
        super().setUp()
        ia.definir(self.con, 'nucleai_llm_ativo', '1')
        ia.definir_estado(self.con, ia.TREINO)

    def entrar(self, usuario):
        c = self.cliente(usuario, 'senha123')
        with c.session_transaction() as s:
            token = s.get('csrf')
        return c, token

    def test_formato_nome_teste_e_compatibilidade_treinador(self):
        # 1. Gera nome aleatório com 4 dígitos no formato Teste#XXXX
        nome = ia.novo_nome_teste()
        self.assertRegex(nome, r'^Teste#\d{4}$')
        self.assertTrue(ia.NOME_TREINADOR.fullmatch(nome))

        # 2. Usuário novo na gerência recebe Teste#XXXX automaticamente
        t = ia.treinador_atual(self.con, self.admin)
        self.assertRegex(t['nome'], r'^Teste#\d{4}$')

        # 3. Registros antigos "Treinador#NNNN" permanecem compatíveis
        t_antigo = ia.treinador(self.con, 'Treinador#0001')
        self.assertEqual(t_antigo['nome'], 'Treinador#0001')
        ia.trocar_treinador(self.con, self.admin, 'Treinador#0001')
        self.assertEqual(ia.treinador_atual(self.con, self.admin)['nome'], 'Treinador#0001')

        # 4. No contexto do chat de teste, a IA vê o usuário como Teste#XXXX
        ctx = ferr.contexto(self.con, self.admin, treino=True, treinador='Teste#8899')
        self.assertEqual(ctx.usuario, 'Teste#8899')
        self.assertEqual(ctx.treinador, 'Teste#8899')
        self.assertTrue(ctx.treino)

    def test_secoes_fixas_da_memoria_concreta(self):
        # Garante que as seções fixas são criadas automaticamente se não existirem
        conteudo = mem.ler(self.con, mem.GEMINI)
        for sec in mem.SECOES_FIXAS:
            self.assertIn('## ' + sec, conteudo, f'Seção «{sec}» ausente em GEMINI.md')

        # Seção 'Quem sou': identidade, tom, idioma pt-BR, respostas curtas e rápidas pela urgência
        quem_sou = mem.secao(self.con, mem.GEMINI, 'Quem sou')
        self.assertIn('NucleAI', quem_sou)
        self.assertIn('português do brasil', quem_sou.lower())
        self.assertIn('curtas', quem_sou.lower())
        self.assertIn('urgência', quem_sou.lower())
        self.assertIn('não diga ao usuário qual modelo', quem_sou.lower())

        # Seção 'Ferramentas e como usar': gerada da lista real de ferramentas em nucleai_ferramentas
        ferr_texto = mem.secao(self.con, mem.GEMINI, 'Ferramentas e como usar')
        self.assertIn('ilustrar', ferr_texto.lower())
        self.assertIn('confirmação', ferr_texto.lower())
        # Deve citar ferramentas reais registradas
        for f_nome in ('buscar_ajuda', 'abrir_tela', 'agenda_consultar', 'agenda_remarcar', 'ilustrar'):
            self.assertIn(f_nome, ferr_texto)

        # Seção 'Como agir' e 'Preferências de usuários'
        self.assertTrue(len(mem.secao(self.con, mem.GEMINI, 'Como agir')) > 0)
        self.assertTrue(len(mem.secao(self.con, mem.GEMINI, 'Preferências de usuários')) > 0)

    def test_secoes_fixas_presentes_na_instrucao_de_qualquer_modelo(self):
        # Configura IA ligada
        ia.definir(self.con, 'nucleai_llm_ativo', '1')
        ia.definir_estado(self.con, ia.LIBERADA)

        for modelo_slug in ('google/gemini-2.5-flash', 'anthropic/claude-3.5-sonnet', 'openai/gpt-4o-mini'):
            ia.salvar_modelos(self.con, [{'slug': modelo_slug, 'ativo': True}])

            # Instrução de sistema tanto para usuário comum quanto para o chat de teste
            for treino_flag in (False, True):
                ctx = ferr.contexto(self.con, self.admin, treino=treino_flag,
                                    treinador='Teste#4321' if treino_flag else None)
                instrucao = conh.instrucao_sistema(ctx)

                # Todas as 4 seções fixas devem estar presentes no prompt do sistema
                self.assertIn('Quem sou', instrucao)
                self.assertIn('Ferramentas e como usar', instrucao)
                self.assertIn('Como agir', instrucao)
                self.assertIn('Preferências de usuários', instrucao)

                # Regra de não revelar qual modelo está respondendo
                self.assertIn('Não diga ao usuário qual modelo está respondendo', instrucao)

                if treino_flag:
                    # IA vê o usuário como Teste#4321
                    self.assertIn('Usuário: Teste#4321', instrucao)
                    self.assertIn('Fake Chat', instrucao)

    def test_contexto_vale_so_para_conversa_e_some_ao_apagar(self):
        # 1. Conversa 1: Teste#1111
        ia.iniciar_conversa_teste(self.con, self.admin, 'Teste#1111')
        motor.BAIXAR = OpenRouter('Olá! Sou a NucleAI. <<confianca:5>>')
        motor.responder_treino(self.con, self.admin, 'Segredo da conversa 1: abacaxi azul.')

        hist_1 = motor._historico_treino(self.con, self.admin, treinador='Teste#1111')
        self.assertTrue(any('abacaxi azul' in m['content'] for m in hist_1))

        # 2. Inicia Conversa 2: Teste#2222
        ia.iniciar_conversa_teste(self.con, self.admin, 'Teste#2222')
        hist_2 = motor._historico_treino(self.con, self.admin, treinador='Teste#2222')
        # A conversa 2 começa limpa: NADA da conversa 1 é enviado no contexto da conversa 2!
        self.assertEqual(len(hist_2), 0)
        self.assertFalse(any('abacaxi azul' in m['content'] for m in hist_2))

        # Envia mensagem na conversa 2
        motor.BAIXAR = OpenRouter('Resposta na conversa 2. <<confianca:5>>')
        motor.responder_treino(self.con, self.admin, 'Pergunta na conversa 2.')

        # O pedido enviado ao LLM para a conversa 2 NÃO tem 'abacaxi azul'
        pedidos_corpo = motor.BAIXAR.pedidos[-1]['messages']
        self.assertFalse(any('abacaxi azul' in m.get('content', '') for m in pedidos_corpo))

        # 3. Apagar a conversa 1: o contexto dela some por completo
        motor.apagar_conversa_treino(self.con, self.admin, 'Teste#1111')
        hist_1_apos_apagar = motor._historico_treino(self.con, self.admin, treinador='Teste#1111')
        self.assertEqual(len(hist_1_apos_apagar), 0)

        # Se voltar à conversa 1 após apagar, nenhuma mensagem anterior é enviada
        ia.trocar_treinador(self.con, self.admin, 'Teste#1111')
        motor.BAIXAR = OpenRouter('Nova resposta limpa. <<confianca:5>>')
        motor.responder_treino(self.con, self.admin, 'Primeira pergunta após apagar.')
        pedidos_apos_apagar = motor.BAIXAR.pedidos[-1]['messages']
        self.assertFalse(any('abacaxi azul' in m.get('content', '') for m in pedidos_apos_apagar))

    def test_regra_ensinada_persiste_em_outra_conversa_e_versao_desfaz(self):
        ia.iniciar_conversa_teste(self.con, self.admin, 'Teste#3333')

        # Ensina uma regra no chat de teste via anotar_aprendizado / anotar_regra_geral
        regra = 'Quando perguntarem sobre preparo de MIBI, diga para jejuar 4 horas.'
        motor.BAIXAR = OpenRouter(('anotar_aprendizado', {'aprendizado': regra}), 'Regra anotada! <<confianca:5>>')
        respostas = motor.responder_treino(self.con, self.admin, f'Ensino: {regra}')

        # Verifica se gravou na seção "Como agir" da memória concreta compartilhada (GEMINI.md)
        como_agir = mem.secao(self.con, mem.GEMINI, 'Como agir')
        self.assertIn(regra, como_agir)

        # Versão foi registrada para possibilitar o desfazer
        versoes = mem.versoes(self.con, mem.GEMINI)
        self.assertTrue(len(versoes) > 0)
        self.assertIn('Como agir', versoes[0]['motivo'])

        # Apaga a conversa de teste 1
        motor.apagar_conversa_treino(self.con, self.admin, 'Teste#3333')
        self.assertEqual(len(motor._historico_treino(self.con, self.admin, treinador='Teste#3333')), 0)

        # Abre outra conversa de teste (Teste#4444): a regra ensinada PERSISTE na instrução de sistema!
        ia.iniciar_conversa_teste(self.con, self.admin, 'Teste#4444')
        ctx2 = ferr.contexto(self.con, self.admin, treino=True, treinador='Teste#4444')
        instrucao2 = conh.instrucao_sistema(ctx2)
        self.assertIn(regra, instrucao2)

        # E também persiste para o time na conversa normal
        ctx_time = ferr.contexto(self.con, self.func, treino=False)
        instrucao_time = conh.instrucao_sistema(ctx_time)
        self.assertIn(regra, instrucao_time)

        # Teste de desfazer: reverter para a versão anterior à anotação
        versao_antiga = versoes[0]['id']
        mem.reverter(self.con, versao_antiga, 'IA_ADM')
        como_agir_revertido = mem.secao(self.con, mem.GEMINI, 'Como agir')
        self.assertNotIn(regra, como_agir_revertido)

    def test_comandos_e_rotas_multiplas_conversas_de_teste(self):
        ia.iniciar_conversa_teste(self.con, self.admin, 'Teste#5555')

        # Comando /novoteste no chat
        r_novo = motor.responder_treino(self.con, self.admin, '/novoteste')
        novo_treinador = ia.treinador_atual(self.con, self.admin)['nome']
        self.assertNotEqual(novo_treinador, 'Teste#5555')
        self.assertRegex(novo_treinador, r'^Teste#\d{4}$')
        self.assertIn('Nova conversa de teste iniciada', r_novo[-1]['texto'])

        # Grava mensagem no novo teste
        motor.BAIXAR = OpenRouter('Resposta teste. <<confianca:5>>')
        motor.responder_treino(self.con, self.admin, 'Mensagem qualquer')
        self.assertTrue(len(motor.conversa_treino(self.con, self.admin, treinador=novo_treinador)) > 0)

        # Comando /limpar apaga esta conversa
        r_limpar = motor.responder_treino(self.con, self.admin, '/limpar')
        self.assertIn('apagada', r_limpar[-1]['texto'])
        msgs = motor.conversa_treino(self.con, self.admin, treinador=novo_treinador)
        # Apenas a mensagem de sistema informando a limpeza deve existir
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]['papel'], 'sistema')

        # Rotas HTTP pela tela
        c, tk = self.entrar('IA_ADM')
        # Iniciar novo teste via POST /nucleai/ia/treino/novo
        res = c.post('/nucleai/ia/treino/novo', data={'_csrf': tk}, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn('Nova conversa de teste iniciada', res.get_data(as_text=True))

        # Apagar teste via POST /nucleai/ia/treino/limpar
        res_limpar = c.post('/nucleai/ia/treino/limpar', data={'_csrf': tk}, follow_redirects=True)
        self.assertEqual(res_limpar.status_code, 200)
        self.assertIn('apagado', res_limpar.get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()
