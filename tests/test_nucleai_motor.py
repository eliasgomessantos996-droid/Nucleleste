"""NucleAI IA de ponta a ponta, com o OpenRouter simulado: desvio só para quem tem nível, ferramentas e cartões, privacidade,
níveis e módulos, queda e volta da internet, confirmação Sim/Não com registro e desfazer, acessos, chat Treinador,
memória (GEMINI.md e TREINAMENTO.txt), projeções e a aba IA online."""
import io
import json
import os
import re
import unittest
import urllib.error
from unittest import mock
from datetime import date, timedelta

from app import agenda, ajuda, chat, llm
from app import db as dbmod
from app import nucleai_ferramentas as ferr
from app import nucleai_ia as ia
from app import nucleai_memoria as mem
from app import nucleai_motor as motor
from app import nucleai_projecoes as proj
from tests.test_chat_blindagens import Base


class OpenRouter:
    """OpenRouter de mentira: devolve as respostas da fila e guarda o que recebeu."""

    def __init__(self, *respostas):
        self.fila = list(respostas)
        self.pedidos = []

    def __call__(self, url, cabecalhos, corpo=None):
        self.pedidos.append(json.loads(corpo.decode('utf-8')) if corpo else None)
        r = self.fila.pop(0) if self.fila else 'Ok. <<confianca:3>>'
        if isinstance(r, Exception):
            raise r
        msg = {'role': 'assistant', 'content': None if isinstance(r, tuple) else r}
        if isinstance(r, tuple):
            msg['tool_calls'] = [{'id': 'call_%d' % len(self.pedidos), 'type': 'function',
                                  'function': {'name': r[0], 'arguments': json.dumps(r[1])}}]
        return {'choices': [{'message': msg}], 'usage': {'total_tokens': 50, 'prompt_tokens': 30, 'completion_tokens': 20}}



def sem_rede(*_a, **_k):
    raise urllib.error.URLError('sem rede')


def com_rede(*_a, **_k):
    raise urllib.error.HTTPError('u', 404, 'nf', {}, None)


class MotorBase(Base):
    def setUp(self):
        bloqueio = mock.patch('urllib.request.urlopen', side_effect=AssertionError('Teste tentou acessar a internet'))
        bloqueio.start()
        self.addCleanup(bloqueio.stop)
        self.admin = self.criar_usuario('IA_ADM', [], admin=1)
        self.func = self.criar_usuario('IA_REC', ['agenda', 'atendimentos', 'dashboard'])
        self.sem_agenda = self.criar_usuario('IA_FIN', ['contas'])
        self.alvo = self.criar_usuario('IA_ALVO', ['agenda', 'caixa'])
        self.con = dbmod.conectar(self.app.config['DATABASE'])
        for t in ('chat_mensagens', 'ajuda_sessoes', 'nucleai_llm_nivel', 'nucleai_llm_uso', 'nucleai_llm_log', 'nucleai_llm_sessao',
                  'nucleai_treinadores', 'nucleai_treino_msgs', 'nucleai_memoria', 'nucleai_memoria_versoes', 'agenda_horarios',
                  'agenda_exames', 'atendimentos'):
            self.con.execute('DELETE FROM %s' % t)
        self.con.execute("DELETE FROM config WHERE chave LIKE 'nucleai_%'")
        self.con.execute("DELETE FROM auditoria WHERE acao LIKE '%NucleAI%'")
        self.con.commit()
        ajuda.invalidar()
        llm.limpar_cache()
        motor.BAIXAR = None
        motor.BAIXAR_CONEXAO = None
        self.bot = ajuda.bot_id(self.con)
        self.rc = self.app.test_request_context()
        self.rc.push()

    def tearDown(self):
        self.rc.pop()
        motor.BAIXAR = None
        motor.BAIXAR_CONEXAO = None
        llm.limpar_cache()
        for nome in mem.ARQUIVOS:
            c = mem.caminho_arquivo(self.con, nome)
            if c and os.path.exists(c):
                os.remove(c)
        self.con.close()

    def liberar(self, *niveis):
        ia.definir(self.con, 'nucleai_llm_ativo', '1')
        ia.definir_estado(self.con, ia.LIBERADA)
        for uid, n in niveis:
            ia.definir_nivel(self.con, uid, n, 'teste')
        self.con.commit()

    def falar(self, uid, texto):
        if not ajuda.sessao(self.con, uid):
            ajuda.iniciar(self.con, uid)
        m = chat.enviar(self.con, uid, self.bot, texto)
        return m['_respostas']

    def agenda_amanha(self):
        d = (date.today() + timedelta(days=1)).isoformat()
        aid = self.con.execute("INSERT INTO agenda_exames (data, exame, inicio, intervalo, vagas) VALUES (?, 'MIBI', '06:00', 30, 1)", (d,)).lastrowid
        for hora, pac, st in (('06:00', 'ANA ANTES', 'AGENDADO'), ('06:30', 'BRUNO SILVA', 'AGENDADO'), ('07:30', 'CARLA SOUZA', 'VEIO'),
                              ('08:30', 'DANIEL LIMA', 'AGENDADO'), ('09:00', 'EVA DEPOIS', 'AGENDADO')):
            self.con.execute('INSERT INTO agenda_horarios (agenda_id, hora, paciente, convenio, status) VALUES (?,?,?,?,?)',
                             (aid, hora, pac, 'SUS', st))
        self.con.commit()
        return d


class DesvioENiveis(MotorBase):
    def test_sem_liberar_responde_a_automatica(self):
        motor.BAIXAR = OpenRouter('não devia ser chamado')
        r = self.falar(self.func, 'como marco um paciente?')
        self.assertEqual(motor.BAIXAR.pedidos, [])
        self.assertTrue(r)   # resposta das regras

    def test_liberada_mas_nivel_zero_responde_a_automatica(self):
        self.liberar()
        motor.BAIXAR = OpenRouter('x')
        self.falar(self.func, 'oi')
        self.assertEqual(motor.BAIXAR.pedidos, [])

    def test_saudacao_da_ia(self):
        self.liberar((self.func, 1))
        m = ajuda.iniciar(self.con, self.func)
        self.assertIn('inteligência artificial', m['corpo'])
        self.assertIn('Leve', m['corpo'])

    def test_resposta_da_ia_tira_a_marca_e_registra(self):
        self.liberar((self.func, 1))
        motor.BAIXAR = OpenRouter('Para marcar, abra a Agenda. <<confianca:4>>')
        r = self.falar(self.func, 'como marco um paciente?')
        self.assertEqual(r[-1]['corpo'], 'Para marcar, abra a Agenda.')
        log = self.con.execute("SELECT * FROM nucleai_llm_log WHERE modo='IA'").fetchone()
        self.assertEqual(log['autoavaliacao'], '4')
        self.assertEqual(ia.usos_hoje(self.con, self.func), 1)
        sistema = motor.BAIXAR.pedidos[0]['messages'][0]['content']
        self.assertIn('Nucleleste', sistema)
        nomes = [d['function']['name'] for d in motor.BAIXAR.pedidos[0]['tools']]
        self.assertIn('buscar_ajuda', nomes)
        self.assertNotIn('agenda_listar', nomes)   # nível Leve: só dúvidas

    def test_ferramentas_respeitam_nivel_e_modulo(self):
        c1 = ferr.contexto(self.con, self.func, nivel=1)
        r = ferr.chamar(c1, 'agenda_listar', {'data': 'hoje'})
        self.assertTrue(r['recusado'])
        self.assertIn('Médio', r['resumo'])
        c4 = ferr.contexto(self.con, self.sem_agenda, nivel=4)
        r = ferr.chamar(c4, 'agenda_listar', {'data': 'hoje'})
        self.assertTrue(r['recusado'])
        self.assertIn('módulo', r['resumo'])
        self.assertTrue(ferr.chamar(c4, 'acessos_ver', {'usuario': 'IA_ALVO'})['recusado'])   # Max, mas não é administrador
        self.assertTrue(ferr.chamar(c1, 'nao_existe', {})['recusado'])

    def test_limite_diario(self):
        self.liberar((self.func, 1))
        ia.definir(self.con, 'nucleai_llm_limite_dia_n1', '1')
        self.con.commit()
        motor.BAIXAR = OpenRouter('primeira <<confianca:5>>', 'segunda')
        self.falar(self.func, 'pergunta 1')
        r = self.falar(self.func, 'pergunta 2')
        self.assertIn('limite diário', r[0]['corpo'])
        self.assertEqual(len(motor.BAIXAR.pedidos), 1)


class AgendaECartoes(MotorBase):
    def test_lista_da_agenda_em_cartao_sem_nomes_para_a_ia(self):
        self.agenda_amanha()
        ia.definir(self.con, 'nucleai_llm_dados_pacientes', '0')
        self.liberar((self.func, 2))
        motor.BAIXAR = OpenRouter(('agenda_listar', {'data': 'amanhã', 'hora_inicio': '6h30', 'hora_fim': '8h30'}),
                              'Aqui está a lista dos agendados. <<confianca:5>>')
        r = self.falar(self.func, 'Confere pra mim todo mundo que tá marcado amanhã de 6h30 às 8h30')
        cartao = next(json.loads(m['cartao']) for m in r if m.get('cartao'))
        self.assertEqual(cartao['tipo'], 'IA_TABELA')
        nomes = [l[2] for l in cartao['linhas']]
        self.assertEqual(nomes, ['BRUNO SILVA', 'CARLA SOUZA', 'DANIEL LIMA'])
        self.assertTrue(cartao['link']['url'].startswith('/agenda/dia/'))
        enviado = json.dumps(motor.BAIXAR.pedidos[1], ensure_ascii=False)
        self.assertIn('3 paciente(s)', enviado)
        for nome in ('BRUNO', 'CARLA', 'DANIEL'):
            self.assertNotIn(nome, enviado)   # nomes vão para a tela, nunca para o provedor

    def test_com_dados_de_pacientes_ligado_vao_nomes_reais(self):
        self.agenda_amanha()
        ia.definir(self.con, 'nucleai_llm_dados_pacientes', '1')
        c = ferr.contexto(self.con, self.func, nivel=2)
        r = ferr.chamar(c, 'agenda_listar', {'data': 'amanhã'})
        self.assertIn('ANA ANTES', r['resumo'])

    def test_datas_e_horas(self):
        hoje = date(2026, 11, 12)   # quinta-feira
        self.assertEqual(ferr.data_de('amanhã', hoje), date(2026, 11, 13))
        self.assertEqual(ferr.data_de('segunda', hoje), date(2026, 11, 16))
        self.assertEqual(ferr.data_de('05/01/2027', hoje), date(2027, 1, 5))
        self.assertEqual(ferr.hora_de('6h30', ''), '06:30')
        self.assertEqual(ferr.hora_de('8h', ''), '08:00')
        with self.assertRaises(ferr.ErroFerramenta):
            ferr.hora_de('25h', '')


class QuedaDaInternet(MotorBase):
    def test_cai_e_volta(self):
        self.liberar((self.func, 1))
        motor.BAIXAR = OpenRouter(urllib.error.URLError('caiu'))
        r = self.falar(self.func, 'como marco um paciente?')
        self.assertIn('Não consegui me conectar', r[0]['corpo'])
        self.assertGreater(len(r), 1)   # e a resposta automática veio logo depois
        self.assertEqual(ia.sessao(self.con, self.func)['modo'], 'REGRAS')
        # ainda sem internet: só a automática, sem chamar a IA
        motor.BAIXAR = OpenRouter('não devia')
        motor.BAIXAR_CONEXAO = sem_rede
        llm.limpar_cache()
        self.falar(self.func, '1')
        self.assertEqual(motor.BAIXAR.pedidos, [])
        # a conexão voltou: cancela a automática, avisa e responde
        motor.BAIXAR = OpenRouter('Certo, sobre a agenda: ... <<confianca:4>>')
        motor.BAIXAR_CONEXAO = com_rede
        llm.limpar_cache()
        r = self.falar(self.func, 'e agora?')
        textos = [m['corpo'] for m in r]
        self.assertEqual(textos[0], motor.AVISO_VOLTEI)
        self.assertEqual(textos[1], 'Certo, sobre a agenda: ...')
        self.assertEqual(ia.sessao(self.con, self.func)['modo'], 'IA')
        conversa = json.dumps(motor.BAIXAR.pedidos[0]['messages'], ensure_ascii=False)
        self.assertIn('como marco um paciente?', conversa)   # leu a conversa

    def test_cota_esgotada(self):
        self.liberar((self.func, 1))
        motor.BAIXAR = OpenRouter(urllib.error.HTTPError('u', 429, 'cota', {}, None))
        r = self.falar(self.func, 'oi')
        self.assertIn('limite de uso', r[0]['corpo'])


class TrocasNoChat(MotorBase):
    def setUp(self):
        super().setUp()
        self.liberar((self.func, 2))
        ia.salvar_modelos(self.con, [{'slug': 'google/primeiro', 'ativo': True}, {'slug': 'openai/segundo', 'ativo': True}])
        self.con.commit()

    def test_troca_silenciosa_e_ferramenta_respondida_com_mesmo_id(self):
        motor.BAIXAR = OpenRouter(urllib.error.HTTPError('u', 429, '', {}, None),
                                 ('buscar_ajuda', {'pergunta': 'agenda'}), 'Resposta após troca. <<confianca:5>>')
        r = self.falar(self.func, 'como marco um paciente?')
        self.assertEqual(r[-1]['corpo'], 'Resposta após troca.')
        self.assertFalse(any('modo automático' in m['corpo'] for m in r))
        pedidos = motor.BAIXAR.pedidos
        self.assertEqual([p['model'] for p in pedidos], ['google/primeiro', 'openai/segundo', 'openai/segundo'])
        chamadas = pedidos[-1]['messages'][-2]['tool_calls']
        resultado = pedidos[-1]['messages'][-1]
        self.assertEqual(resultado['role'], 'tool')
        self.assertEqual(resultado['tool_call_id'], chamadas[0]['id'])
        self.assertEqual(ia.sessao(self.con, self.func)['modo'], 'IA')

    def test_troca_depois_da_ferramenta_preserva_resultado_sem_reexecutar(self):
        motor.BAIXAR = OpenRouter(('buscar_ajuda', {'pergunta': 'agenda'}),
                                 urllib.error.HTTPError('u', 503, '', {}, None), 'Resposta recuperada.')
        with mock.patch.object(ferr, 'chamar', wraps=ferr.chamar) as chamar:
            r = self.falar(self.func, 'como marco um paciente?')
        self.assertEqual(r[-1]['corpo'], 'Resposta recuperada.')
        self.assertEqual(chamar.call_count, 1)
        self.assertEqual(motor.BAIXAR.pedidos[1]['messages'], motor.BAIXAR.pedidos[2]['messages'])

    def test_limite_diario_da_conta_avisa_o_motivo_e_nao_percorre_os_gratuitos(self):
        ia.salvar_modelos(self.con, [{'slug': 'google/a:free', 'ativo': True}, {'slug': 'openai/b:free', 'ativo': True}])
        self.con.commit()
        corpo = b'{"error":{"message":"Rate limit exceeded: free-models-per-day","code":429}}'
        motor.BAIXAR = OpenRouter(urllib.error.HTTPError('u', 429, 'x', {}, io.BytesIO(corpo)))
        r = self.falar(self.func, 'como marco um paciente?')
        self.assertIn('limite de uso diário', r[0]['corpo'])
        self.assertIn('Volto a tentar', r[0]['corpo'])
        self.assertEqual(len(motor.BAIXAR.pedidos), 1)   # a 2ª tentativa gastaria o mesmo limite da conta
        log = self.con.execute("SELECT resposta FROM nucleai_llm_log WHERE resposta LIKE 'Queda:%' ORDER BY id DESC").fetchone()[0]
        self.assertIn('free-models-per-day', log)

    def test_todos_falham_mantem_resposta_por_regras(self):
        motor.BAIXAR = OpenRouter(urllib.error.HTTPError('u', 429, '', {}, None),
                                 urllib.error.HTTPError('u', 402, '', {}, None))
        r = self.falar(self.func, 'como marco um paciente?')
        self.assertIn('limite de uso', r[0]['corpo'])
        self.assertGreater(len(r), 1)
        self.assertEqual(ia.sessao(self.con, self.func)['modo'], 'REGRAS')
        self.assertEqual(len(motor.BAIXAR.pedidos), 2)


class DadosInventados(MotorBase):
    """A IA não pode falar de agenda, contas, números ou gráficos sem ter consultado o sistema nesta resposta."""

    def setUp(self):
        super().setUp()
        self.liberar((self.func, 2))

    def test_numeros_sem_consultar_sao_corrigidos_e_a_resposta_final_vem_da_ferramenta(self):
        self.agenda_amanha()   # 5 pacientes de verdade
        motor.BAIXAR = OpenRouter('Amanhã são 24 pacientes agendados. <<confianca:5>>',
                                 ('agenda_listar', {'data': 'amanhã'}), 'São 5 pacientes amanhã. <<confianca:5>>')
        r = self.falar(self.func, 'me mande a agenda de amanha')
        textos = [m['corpo'] for m in r]
        self.assertIn('São 5 pacientes amanhã.', textos)          # (a última mensagem é o cartão da agenda)
        self.assertFalse(any('24' in t for t in textos))
        pedidos = motor.BAIXAR.pedidos
        self.assertEqual(len(pedidos), 3)
        self.assertEqual(pedidos[1]['messages'][-1], {'role': 'user', 'content': motor.NUDGE_SEM_CONSULTA})
        self.assertNotIn('24 pacientes', json.dumps(pedidos[2]['messages'][-1], ensure_ascii=False))

    def test_insistir_em_inventar_vira_resposta_honesta_sem_os_numeros(self):
        motor.BAIXAR = OpenRouter('Vencem R$ 1.386,00 amanhã (Unicred). <<confianca:4>>', 'Total de 2 contas: R$ 1.386,00. <<confianca:4>>')
        r = self.falar(self.func, 'contas vencendo amanha 16/11')
        corpo = r[-1]['corpo']
        self.assertEqual(corpo, motor.SEM_CONSULTA)
        self.assertNotIn('1.386', corpo)
        self.assertEqual(len(motor.BAIXAR.pedidos), 2)   # corrigiu uma vez e parou: cada tentativa gasta o limite da OpenRouter
        log = self.con.execute("SELECT resposta FROM nucleai_llm_log WHERE modo='IA' ORDER BY id DESC").fetchone()[0]
        self.assertNotIn('1.386', log)

    def test_pergunta_de_como_fazer_com_numeros_nao_e_corrigida(self):
        motor.BAIXAR = OpenRouter('1. Abra a Agenda. 2. Clique no horário. <<confianca:4>>')
        r = self.falar(self.func, 'como marco um paciente?')
        self.assertIn('Abra a Agenda', r[-1]['corpo'])
        self.assertEqual(len(motor.BAIXAR.pedidos), 1)

    def test_conversa_sem_dados_nao_e_corrigida(self):
        motor.BAIXAR = OpenRouter('Oi! Em que posso ajudar? <<confianca:5>>')
        self.falar(self.func, 'oi, tudo bem?')
        self.assertEqual(len(motor.BAIXAR.pedidos), 1)

    def test_marca_copiada_do_historico_sem_cartao_e_corrigida_e_removida(self):
        motor.BAIXAR = OpenRouter('De nada! [ilustração #2 (planilha): Contas a pagar] <<confianca:3>>', 'De nada! <<confianca:5>>')
        r = self.falar(self.func, 'obrigado')
        self.assertEqual(r[-1]['corpo'], 'De nada!')
        self.assertEqual(len(motor.BAIXAR.pedidos), 2)

    def test_so_buscar_ajuda_nao_libera_numeros_de_dados(self):
        motor.BAIXAR = OpenRouter(('buscar_ajuda', {'pergunta': 'contas'}), 'Há 3 contas vencendo amanhã. <<confianca:3>>',
                                 'Não consigo consultar contas por aqui. <<confianca:4>>')
        r = self.falar(self.func, 'quantas contas vencem amanha?')
        self.assertEqual(r[-1]['corpo'], 'Não consigo consultar contas por aqui.')

    def test_prompt_traz_as_regras_e_nao_repete_a_lista_de_ferramentas(self):
        motor.BAIXAR = OpenRouter('Oi! <<confianca:5>>')
        self.falar(self.func, 'oi')
        sistema = motor.BAIXAR.pedidos[0]['messages'][0]['content']
        self.assertNotIn('Lista de ferramentas disponíveis', sistema)        # já vai no campo de ferramentas
        self.assertIn('Consulta e fidelidade aos dados', sistema)            # o começo do manual não é mais cortado
        self.assertIn('só podem ser', sistema)                                # regra 17
        self.assertNotIn('Regra de anonimato do modelo', sistema)            # bloco duplicado removido

    def test_funcao_de_deteccao(self):
        d = lambda *nomes: [{'nome': n} for n in nomes]
        casos = (
            ('agenda de amanha', 'São 24 pacientes.', d(), [], True),
            ('agenda de amanha', 'São 24 pacientes.', d('agenda_listar'), [], False),
            ('agenda de amanha', 'Não encontrei nada.', d(), [], False),                    # sem números: não há o que checar
            ('gere o gráfico', 'O gráfico já está aí em cima.', d(), [], True),
            ('gere o gráfico', 'O gráfico já está aí em cima.', d(), [{'tipo': 'x'}], False),
            ('contas vencendo', 'Veja a planilha.', d('ilustrar'), [], True),                 # ilustrar sem consulta
            ('como faço a agenda?', 'Passo 1.', d(), [], False),
            ('oi', 'Olá! Tenho 2 dicas.', d(), [], False),
        )
        for pergunta, texto, chamadas, cartoes, esperado in casos:
            with self.subTest(pergunta=pergunta, texto=texto):
                self.assertEqual(motor.respondeu_sem_consultar(pergunta, texto, chamadas, cartoes), esperado)


class FormatacaoDasMensagens(MotorBase):
    """A NucleAI aprende as marcas de formatação; só as mensagens dela são formatadas na tela."""

    def setUp(self):
        super().setUp()
        self.liberar((self.func, 2))

    def test_a_ia_recebe_o_guia_de_formatacao_e_de_blocos_visuais(self):
        motor.BAIXAR = OpenRouter('Oi! <<confianca:5>>')
        self.falar(self.func, 'oi')
        sistema = motor.BAIXAR.pedidos[0]['messages'][0]['content']
        self.assertIn('Como formatar suas mensagens', sistema)
        for trecho in ('**negrito**', '__itálico__', '~~riscado~~', '> [!aviso]', 'tipo planilha', 'tipo grafico',
                       'tipo cartao_info', 'tipo cartao_decisao', 'tipo cartao_permissao'):
            self.assertIn(trecho, sistema)

    def test_so_a_mensagem_da_nucleai_e_marcada_para_formatar(self):
        motor.BAIXAR = OpenRouter('Amanhã tem **3 pacientes**. <<confianca:5>>')
        self.falar(self.func, 'quero **teste** de texto')
        msgs = chat.serializar_lista(self.con, chat.conversa(self.con, self.func, self.bot), self.func)
        da_ia = [m for m in msgs if not m['minha'] and 'pacientes' in m['corpo']]
        minhas = [m for m in msgs if m['minha']]
        self.assertTrue(da_ia and da_ia[0]['ia'])
        self.assertIn('**3 pacientes**', da_ia[0]['corpo'])     # o texto segue com as marcas; quem desenha é a tela
        self.assertTrue(minhas and not minhas[0]['ia'])         # o que a pessoa digita não é formatado

    def test_previa_da_lista_de_conversas_nao_mostra_as_marcas(self):
        motor.BAIXAR = OpenRouter('## Resumo\n**Amanhã** tem `3` pacientes. <<confianca:5>>')
        self.falar(self.func, 'oi')
        previa = next(c['previa'] for c in chat.contatos(self.con, self.func) if c['sistema'] == 3)
        self.assertNotIn('**', previa)
        self.assertNotIn('##', previa)
        self.assertIn('Amanhã tem 3 pacientes', previa)

    def test_texto_simples(self):
        from app import nucleai_formato as f
        casos = (('**Resumo:** `x` e __y__', 'Resumo: x e y'), ('## Título\n- a\n> [!aviso] b', 'Título\n- a\nb'),
                 ('2 * 3 * 4 e agenda_listar', '2 * 3 * 4 e agenda_listar'), ('~~a~~ ++b++ *c*', 'a b c'), ('', ''))
        for entrada, esperado in casos:
            with self.subTest(entrada=entrada):
                self.assertEqual(f.texto_simples(entrada), esperado)


class AlteracoesPeloChat(MotorBase):
    def test_mudar_status_pede_sim_registra_e_desfaz(self):
        d = self.agenda_amanha()
        self.liberar((self.func, 3))
        motor.BAIXAR = OpenRouter(('agenda_mudar_status', {'data': 'amanhã', 'hora': '6h30', 'status': 'faltou'}),
                              'Confirma? Responda Sim ou Não. <<confianca:5>>')
        r = self.falar(self.func, 'marca que o paciente das 6h30 de amanhã faltou')
        cartao = next(json.loads(m['cartao']) for m in r if m.get('cartao'))
        self.assertEqual(cartao['tipo'], 'IA_PROPOSTA')
        hid = self.con.execute("SELECT id FROM agenda_horarios WHERE hora='06:30'").fetchone()[0]
        self.assertEqual(self.con.execute('SELECT status FROM agenda_horarios WHERE id=?', (hid,)).fetchone()[0], 'AGENDADO')
        motor.BAIXAR = OpenRouter()
        r = self.falar(self.func, 'sim')
        self.assertIn('Pronto', r[0]['corpo'])
        self.assertEqual(motor.BAIXAR.pedidos, [])   # o Sim é tratado pelo sistema, sem a IA
        self.assertEqual(self.con.execute('SELECT status FROM agenda_horarios WHERE id=?', (hid,)).fetchone()[0], 'FALTOU')
        reg = self.con.execute("SELECT * FROM auditoria WHERE acao LIKE '%via chat (NucleAI)%' ORDER BY id DESC").fetchone()
        self.assertEqual(reg['usuario'], 'IA_REC')
        self.assertIn(d, reg['detalhe'])
        agenda.aplicar_desfazer(self.con, json.loads(reg['desfazer']))
        self.assertEqual(self.con.execute('SELECT status FROM agenda_horarios WHERE id=?', (hid,)).fetchone()[0], 'AGENDADO')

    def test_nao_cancela(self):
        self.agenda_amanha()
        self.liberar((self.func, 3))
        motor.BAIXAR = OpenRouter(('agenda_mudar_status', {'data': 'amanhã', 'hora': '06:30', 'status': 'veio'}), 'Confirma?')
        self.falar(self.func, 'o das 6h30 veio')
        r = self.falar(self.func, 'não')
        self.assertIn('cancelei', r[0]['corpo'])
        self.assertEqual(self.con.execute("SELECT status FROM agenda_horarios WHERE hora='06:30'").fetchone()[0], 'AGENDADO')

    def test_nivel_medio_nao_altera(self):
        c = ferr.contexto(self.con, self.func, nivel=2)
        self.assertTrue(ferr.chamar(c, 'agenda_mudar_status', {'data': 'hoje', 'hora': '6h', 'status': 'veio'})['recusado'])

    def test_acessos_ver_alterar_e_desfazer(self):
        c = ferr.contexto(self.con, self.admin, nivel=4)
        r = ferr.chamar(c, 'acessos_ver', {'usuario': 'ia_alvo'})
        self.assertEqual(r['cartao']['tipo'], 'IA_ACESSOS')
        r = ferr.chamar(c, 'acessos_alterar', {'usuario': 'IA_ALVO', 'adicionar': ['Contas a pagar'], 'remover': ['agenda']})
        self.assertTrue(r['pendente'])
        mudancas = {i['chave']: i['mudanca'] for g in r['cartao']['grupos'] for i in g['itens'] if i['mudanca']}
        self.assertEqual(mudancas, {'contas': '+', 'agenda': '-'})
        feito = ferr.confirmar(c, r['pendente'])
        self.assertIn('Pronto', feito['texto'])
        mods = json.loads(self.con.execute('SELECT modulos FROM usuarios WHERE id=?', (self.alvo,)).fetchone()[0])
        self.assertEqual(sorted(mods), ['caixa', 'contas'])
        reg = self.con.execute("SELECT desfazer FROM auditoria WHERE acao LIKE 'Alterou os acessos de IA_ALVO%' ORDER BY id DESC").fetchone()
        self.assertTrue(ferr.aplicar_desfazer(self.con, json.loads(reg[0])))
        mods = json.loads(self.con.execute('SELECT modulos FROM usuarios WHERE id=?', (self.alvo,)).fetchone()[0])
        self.assertEqual(sorted(mods), ['agenda', 'caixa'])

    def test_nao_altera_admin_nem_a_si_mesmo(self):
        c = ferr.contexto(self.con, self.admin, nivel=4)
        self.assertIn('ERRO', ferr.chamar(c, 'acessos_alterar', {'usuario': 'IA_ADM', 'adicionar': ['caixa']})['resumo'])

    def test_confirmacao_expira(self):
        c = ferr.contexto(self.con, self.admin, nivel=4)
        r = ferr.chamar(c, 'acessos_alterar', {'usuario': 'IA_ALVO', 'adicionar': ['contas']})
        r['pendente']['criado_em'] = '2020-01-01 00:00:00'
        self.assertIn('expirou', ferr.confirmar(c, r['pendente'])['texto'])


class Treinamento(MotorBase):
    def setUp(self):
        super().setUp()
        ia.definir(self.con, 'nucleai_llm_ativo', '1')
        self.con.commit()

    def test_desligada_nao_treina(self):
        ia.definir(self.con, 'nucleai_llm_ativo', '0')
        with self.assertRaises(ValueError):
            motor.responder_treino(self.con, self.admin, 'oi')

    def test_em_treino_o_time_nao_usa(self):
        ia.definir_nivel(self.con, self.func, 4, 'teste')
        motor.BAIXAR = OpenRouter('x')
        self.falar(self.func, 'oi')
        self.assertEqual(motor.BAIXAR.pedidos, [])

    def test_comandos_de_perfil(self):
        r = motor.responder_treino(self.con, self.admin, '/chanceperfil [Maria#0002]')
        self.assertEqual(r[-1]['treinador'], 'Maria#0002')
        self.assertEqual(r[-1]['cartao']['tipo'], 'IA_PERFIL')
        self.assertEqual(ia.treinador_atual(self.con, self.admin)['nome'], 'Maria#0002')
        r = motor.responder_treino(self.con, self.admin, '/configperfil formalidade 5')
        self.assertEqual(ia.treinador(self.con, 'Maria#0002')['formalidade'], 5)
        reg = self.con.execute("SELECT desfazer FROM auditoria WHERE acao LIKE '%perfil do treinador Maria#0002%' ORDER BY id DESC").fetchone()
        self.assertTrue(ferr.aplicar_desfazer(self.con, json.loads(reg[0])))
        self.assertEqual(ia.treinador(self.con, 'Maria#0002')['formalidade'], 3)
        r = motor.responder_treino(self.con, self.admin, '/chanceperfil semcerquilha')
        self.assertIn('inválido', r[-1]['texto'])
        r = motor.responder_treino(self.con, self.admin, '/configperfil forca 9')
        self.assertIn('1 a 5', r[-1]['texto'])

    def test_aprende_e_grava_no_treinamento(self):
        t_atual = ia.treinador_atual(self.con, self.admin)['nome']
        motor.BAIXAR = OpenRouter(('anotar_aprendizado', {'aprendizado': 'Sempre citar o caminho do menu.'}), 'Anotado! <<confianca:5>>')
        r = motor.responder_treino(self.con, self.admin, 'Quando explicar, cite o caminho do menu.')
        self.assertEqual(r[-1]['texto'], 'Anotado!')
        texto = mem.ler(self.con, mem.TREINAMENTO)
        self.assertIn('## Treinador: ' + t_atual, texto)
        self.assertIn('Sempre citar o caminho do menu.', texto)
        self.assertIn('Sempre citar o caminho do menu.', mem.secao(self.con, mem.GEMINI, 'Como agir'))
        with open(mem.caminho_arquivo(self.con, mem.TREINAMENTO), encoding='utf-8') as f:
            self.assertIn('Sempre citar o caminho do menu.', f.read())
        # no próximo pedido o aprendizado vai junto
        motor.BAIXAR = OpenRouter('ok')
        motor.responder_treino(self.con, self.admin, 'teste')
        self.assertIn('Sempre citar o caminho do menu.', motor.BAIXAR.pedidos[0]['messages'][0]['content'])

    def test_no_treino_a_alteracao_e_simulada(self):
        self.agenda_amanha()
        motor.BAIXAR = OpenRouter(('agenda_mudar_status', {'data': 'amanhã', 'hora': '6h30', 'status': 'veio'}), 'Confirma?')
        motor.responder_treino(self.con, self.admin, 'o das 6h30 de amanhã veio')
        r = motor.responder_treino(self.con, self.admin, 'sim')
        self.assertIn('Simulação', r[-1]['texto'])
        self.assertEqual(self.con.execute("SELECT status FROM agenda_horarios WHERE hora='06:30'").fetchone()[0], 'AGENDADO')

    def test_erro_de_rede_no_treino(self):
        motor.BAIXAR = OpenRouter(urllib.error.URLError('x'))
        r = motor.responder_treino(self.con, self.admin, 'oi')
        self.assertEqual(r[-1]['papel'], 'sistema')
        self.assertIn('internet', r[-1]['texto'])


class Memoria(MotorBase):
    def test_recusa_dados_pessoais(self):
        for ruim in ('CPF 123.456.789-09', 'ligar 33 99999-1234', 'a senha é x', 'joao@x.com'):
            with self.assertRaises(mem.ErroMemoria):
                mem.anotar(self.con, mem.GEMINI, 'Geral', ruim, 'teste')

    def test_versoes_e_reverter(self):
        mem.anotar(self.con, mem.GEMINI, 'Usuário: IA_REC', 'Prefere respostas curtas.', 'teste')
        self.assertIn('Prefere respostas curtas.', mem.secao(self.con, mem.GEMINI, 'Usuário: IA_REC'))
        v = mem.versoes(self.con, mem.GEMINI)
        self.assertTrue(v)
        mem.reverter(self.con, v[0]['id'], 'teste')
        self.assertNotIn('Prefere respostas curtas.', mem.ler(self.con, mem.GEMINI))

    def test_edicao_manual_do_arquivo_e_importada(self):
        mem.ler(self.con, mem.GEMINI)
        caminho = mem.caminho_arquivo(self.con, mem.GEMINI)
        with open(caminho, 'a', encoding='utf-8') as f:
            f.write('- [manual] Chamar todos de você.\n')
        futuro = os.path.getmtime(caminho) + 120
        os.utime(caminho, (futuro, futuro))
        self.assertIn('Chamar todos de você.', mem.ler(self.con, mem.GEMINI))
        self.assertEqual(mem.versoes(self.con, mem.GEMINI)[0]['por'], 'edição manual do arquivo')

    def test_preferencia_do_usuario_vai_no_prompt_dele(self):
        self.liberar((self.func, 1))
        mem.anotar(self.con, mem.GEMINI, mem.secao_usuario('IA_REC'), 'Gosta de ser chamada de Rê.', 'teste')
        self.con.commit()
        motor.BAIXAR = OpenRouter('oi Rê')
        self.falar(self.func, 'oi')
        self.assertIn('Gosta de ser chamada de Rê.', motor.BAIXAR.pedidos[0]['messages'][0]['content'])


class Projecoes(MotorBase):
    def test_tendencia_linear(self):
        p, faixa, b = proj.tendencia([10, 20, 30, 40], 2)
        self.assertEqual([round(x) for x in p], [50, 60])
        self.assertAlmostEqual(b, 10)
        self.assertAlmostEqual(faixa, 0)

    def test_projecao_de_atendimentos(self):
        meses = proj.meses_completos(4)
        for i, m in enumerate(meses):
            for _ in range(10 * (i + 1)):
                self.con.execute("INSERT INTO atendimentos (data, exame) VALUES (?, 'MIBI')", (m + '-10',))
        self.con.commit()
        r = proj.projecao_atendimentos(self.con, 4, 2)
        self.assertEqual([h['valor'] for h in r['historico']], [10, 20, 30, 40])
        self.assertEqual([p['valor'] for p in r['projecao']], [50.0, 60.0])

    def test_projecao_de_faltas(self):
        meses = proj.meses_completos(2)
        for m in meses:
            aid = self.con.execute("INSERT INTO agenda_exames (data, exame, inicio, intervalo, vagas) VALUES (?, 'OSSEA', '07:00', 30, 1)",
                                   (m + '-05',)).lastrowid
            for i, st in enumerate(['VEIO'] * 8 + ['FALTOU'] * 2):
                self.con.execute('INSERT INTO agenda_horarios (agenda_id, hora, paciente, status) VALUES (?,?,?,?)', (aid, '07:%02d' % i, 'P%d' % i, st))
        prox = proj.meses_futuros(1)[0]
        aid = self.con.execute("INSERT INTO agenda_exames (data, exame, inicio, intervalo, vagas) VALUES (?, 'OSSEA', '07:00', 30, 1)",
                               (prox + '-05',)).lastrowid
        for i in range(50):
            self.con.execute("INSERT INTO agenda_horarios (agenda_id, hora, paciente, status) VALUES (?,?,?, 'AGENDADO')", (aid, '08:%02d' % i, 'F%d' % i))
        self.con.commit()
        r = proj.projecao_faltas(self.con, 2)
        self.assertEqual(r['taxa_media'], 20.0)
        self.assertEqual(r['projecao'][0]['valor'], 10.0)
        c = ferr.contexto(self.con, self.func, nivel=3)
        res = ferr.chamar(c, 'projetar_faltas', {'meses_historico': 2})
        self.assertEqual(res['cartao']['tipo'], 'IA_GRAFICO')
        self.assertEqual(res['cartao']['destaque']['valor'], 10.0)


class AbaIAOnline(MotorBase):
    def setUp(self):
        super().setUp()
        self.rc.pop()   # as requisições abaixo usam o cliente de teste
        self.ger = self.criar_usuario('IA_GER', ['gerencia'])

    def tearDown(self):
        self.rc.push()
        super().tearDown()

    def entrar(self, usuario):
        c = self.cliente(usuario, 'senha123')
        with c.session_transaction() as s:
            token = s.get('csrf')
        return c, token

    def test_so_gerencia_entra(self):
        c, _ = self.entrar('IA_GER')
        r = c.get('/nucleai/ia')
        self.assertEqual(r.status_code, 200)
        self.assertIn('Fake Chat', r.get_data(as_text=True))
        c2, _ = self.entrar('IA_REC')
        self.assertNotEqual(c2.get('/nucleai/ia').status_code, 200)

    def test_tela_mostra_o_ultimo_limite_informado_pela_openrouter(self):
        c, _ = self.entrar('IA_GER')
        self.assertNotIn('Último limite informado', c.get('/nucleai/ia').get_data(as_text=True))
        ia.definir(self.con, 'nucleai_llm_ultimo_erro', json.dumps(
            {'quando': '2026-11-15 20:50:17', 'modelo': 'google/a:free', 'tipo': 'cota', 'escopo': 'conta_dia',
             'detalhe': 'HTTP 429 · Rate limit exceeded: free-models-per-day', 'ate': '2026-11-16 21:00:05'}))
        self.con.commit()
        html = c.get('/nucleai/ia').get_data(as_text=True)
        self.assertIn('Último limite informado', html)
        self.assertIn('diário da conta', html)
        self.assertIn('free-models-per-day', html)
        self.assertIn('dividem o mesmo limite da conta', html)

    def test_liberar_com_codigo_pela_tela(self):
        os.environ[llm.VAR_CHAVE] = 'chave-de-teste'
        try:
            c, tk = self.entrar('IA_GER')
            c.post('/nucleai/ia/codigo', data={'_csrf': tk})
            con = dbmod.conectar(self.app.config['DATABASE'])
            codigo = con.execute("SELECT valor FROM config WHERE chave='nucleai_llm_codigo'").fetchone()[0]
            self.assertRegex(codigo, r'^\d{6}$')
            self.assertIn(codigo, c.get('/nucleai/ia').get_data(as_text=True))   # mostrado na página
            c.post('/nucleai/ia/liberar', data={'_csrf': tk, 'codigo': '000000' if codigo != '000000' else '111111'})
            self.assertEqual(ia.estado(con), ia.TREINO)
            c.post('/nucleai/ia/liberar', data={'_csrf': tk, 'codigo': codigo})
            self.assertEqual(ia.estado(con), ia.LIBERADA)
            c.post('/nucleai/ia/desativar', data={'_csrf': tk})
            self.assertEqual(ia.estado(con), ia.DESATIVADA)
            con.close()
        finally:
            os.environ.pop(llm.VAR_CHAVE, None)

    def test_niveis_pela_tela(self):
        c, tk = self.entrar('IA_GER')
        c.post('/nucleai/ia/niveis', data={'_csrf': tk, 'nivel_%d' % self.func: '3'})
        con = dbmod.conectar(self.app.config['DATABASE'])
        self.assertEqual(ia.nivel(con, self.func), 3)
        con.close()

    def test_chave_salva_trocada_apagada_sem_exposicao_na_tela_ou_banco(self):
        c, tk = self.entrar('IA_GER')
        for segredo in ('sk-or-ficticia-abcd', 'sk-or-substituta-efgh'):
            r = c.post('/nucleai/ia/config', data={'_csrf': tk, 'acao_ia': 'chave_salvar', 'openrouter_chave': segredo}, follow_redirects=True)
            html = r.get_data(as_text=True)
            self.assertEqual(r.status_code, 200)
            self.assertNotIn(segredo, html)
            self.assertIn('configurada, termina em ••••' + segredo[-4:], html)
            con = dbmod.conectar(self.app.config['DATABASE'])
            self.assertEqual(llm.chave(con), segredo)
            for tabela in ('config', 'auditoria', 'nucleai_llm_log'):
                self.assertNotIn(segredo, str([tuple(l) for l in con.execute('SELECT * FROM ' + tabela)]))
            con.close()
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(llm.VAR_CHAVE, None)
            r = c.post('/nucleai/ia/config', data={'_csrf': tk, 'acao_ia': 'chave_apagar'}, follow_redirects=True)
            self.assertIn('não configurada', r.get_data(as_text=True))
        self.assertFalse(os.path.exists(llm.caminho_chave(self.con)))

    def test_modelos_adicionar_ordenar_alternar_remover(self):
        c, tk = self.entrar('IA_GER')
        def acao(nome, slug):
            r = c.post('/nucleai/ia/config', data={'_csrf': tk, 'acao_ia': nome, 'modelo_slug': slug})
            self.assertEqual(r.status_code, 302)
        acao('modelo_adicionar', 'openai/modelo:free')
        acao('modelo_subir', 'openai/modelo:free')
        self.assertEqual(ia.modelo(self.con), 'openai/modelo:free')
        acao('modelo_alternar', 'openai/modelo:free')
        self.assertEqual(ia.modelo(self.con), llm.MODELO_PADRAO)
        acao('modelo_descer', 'openai/modelo:free')
        self.assertEqual(ia.modelos(self.con)[-1]['slug'], 'openai/modelo:free')
        acao('modelo_alternar', 'openai/modelo:free')
        acao('modelo_remover', llm.MODELO_PADRAO)
        self.assertEqual(ia.modelos(self.con), [{'slug': 'openai/modelo:free', 'ativo': True}])

    def test_chave_exige_gerencia_e_csrf(self):
        c, tk = self.entrar('IA_REC')
        r = c.post('/nucleai/ia/config', data={'_csrf': tk, 'acao_ia': 'chave_salvar', 'openrouter_chave': 'ficticia'})
        self.assertEqual(r.status_code, 302)
        self.assertNotIn('/nucleai/ia', r.headers['Location'])
        self.assertFalse(os.path.exists(llm.caminho_chave(self.con)))
        c, _ = self.entrar('IA_GER')
        self.assertEqual(c.post('/nucleai/ia/config', data={'acao_ia': 'chave_salvar', 'openrouter_chave': 'ficticia'}).status_code, 400)
        self.assertFalse(os.path.exists(llm.caminho_chave(self.con)))

    def test_treino_pela_tela(self):
        c, tk = self.entrar('IA_GER')
        c.post('/nucleai/ia/config', data={'_csrf': tk, 'ativo': '1', 'limite_n1': '30', 'limite_n2': '60',
                                           'limite_n3': '120', 'limite_n4': '300', 'limite_min': '6', 'padrao_nivel': '0'})
        motor.BAIXAR = OpenRouter('Olá, treinador! <<confianca:5>>')
        r = c.post('/nucleai/ia/treino', json={'texto': 'oi'}, headers={'X-CSRF-Token': tk})
        j = r.get_json()
        self.assertTrue(j['ok'], j)
        self.assertEqual(j['mensagens'][-1]['texto'], 'Olá, treinador!')


if __name__ == '__main__':
    unittest.main()
