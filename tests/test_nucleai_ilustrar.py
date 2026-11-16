"""Testes da ferramenta Ilustrar da NucleAI (ETAPA 3): todos os 5 tipos, fallback, limites, escape,
exclusividade do bot, substituição + ilustracao_atual, download Excel (até 30 colunas) e decisão Sim/Não ligada ao pendente."""
import io
import json
import unittest

from openpyxl import load_workbook

from app import chat, modulos
from app import nucleai_conhecimento as conh
from app import nucleai_ferramentas as ferr
from app import nucleai_ia as ia
from app import nucleai_ilustrar as ilustrar
from app import nucleai_motor as motor
from tests.test_nucleai_motor import MotorBase, OpenRouter


class IlustrarTestes(MotorBase):
    def setUp(self):
        super().setUp()
        self.con.execute('DELETE FROM nucleai_ilustracoes')
        self.con.commit()
        ia.definir(self.con, 'nucleai_llm_chave', 'sk-teste')
        self.liberar((self.func, ferr.ALTO), (self.admin, ferr.MAX))

    def _postar_chat(self, login_usuario, para_uid, corpo, extras=None):
        cli = self.cliente(login_usuario, 'senha123')
        dados = {'para': str(para_uid), 'corpo': corpo}
        if extras:
            dados.update(extras)
        return self.post(cli, '/mensagens/enviar', dados)

    def test_conhecimento_descreve_todos_os_tipos(self):
        texto = conh.REGRAS + conh.formato.GUIA   # os tipos de bloco e quando usar cada um ficam no guia de formatação
        for termo in ('ilustrar', 'ilustracao_atual', 'planilha', 'grafico',
                      'cartao_info', 'cartao_decisao', 'cartao_permissao', 'substitui'):
            self.assertIn(termo, texto)
        self.assertIsNone(modulos.modulo_do_endpoint('chat.ilustracao_excel'))

    def test_todos_os_tipos_via_openrouter(self):
        motor.BAIXAR = OpenRouter(
            ('ilustrar', {
                'tipo': 'planilha',
                'titulo': 'Pacientes da semana',
                'subtitulo': 'Unidade Centro',
                'colunas': ['Paciente', 'Idade', 'Status'],
                'linhas': [['Ana', 42, 'Agendado'], ['Bruno', 67, 'Veio']],
            }),
            'Segue a planilha acima. <<confianca:5>>',
            ('ilustrar', {
                'tipo': 'grafico',
                'titulo': 'Atendimentos por dia',
                'modo': 'barras',
                'unidade': 'atend.',
                'rotulos': ['Seg', 'Ter', 'Qua'],
                'series': [{'nome': 'Consultas', 'valores': [12, 18, 15]}],
            }),
            'Veja o comparativo diário. <<confianca:5>>',
            ('ilustrar', {
                'tipo': 'cartao_info',
                'titulo': 'Ficha de agendamento',
                'icone': 'calendar-days',
                'destaque': 'Confirmado',
                'itens': [{'rotulo': 'Paciente', 'valor': '[PACIENTE_1]'}, {'rotulo': 'Horário', 'valor': '14:30'}],
            }),
            'Resumo do agendamento. <<confianca:5>>',
            ('ilustrar', {
                'tipo': 'cartao_permissao',
                'titulo': 'Alteração de acessos',
                'alvo': 'IA_ALVO',
                'acao': 'Liberar Laudos',
                'autorizadores': ['Gerência', 'Administrador'],
                'mudancas': [{'nome': 'Laudos', 'detalhe': 'Acesso completo', 'tipo': 'mais'}],
            }),
            'Confira quem precisa aprovar. <<confianca:5>>',
        )

        # 1) planilha
        r1 = motor.talvez_responder(self.con, self.func, 'Me mostra uma planilha dos pacientes')
        msgs1 = chat.serializar_lista(self.con, r1['mensagens'], self.func)
        c1 = [m['cartao'] for m in msgs1 if m['cartao']][0]
        self.assertEqual(c1['tipo'], 'IA_ILUSTRACAO')
        self.assertEqual(c1['subtipo'], 'planilha')
        self.assertEqual(c1['dados']['colunas'], ['Paciente', 'Idade', 'Status'])
        self.assertEqual(len(c1['dados']['linhas']), 2)
        self.assertTrue(c1['id'])

        # 2) gráfico
        r2 = motor.talvez_responder(self.con, self.func, 'Agora em gráfico de barras')
        c2 = [m['cartao'] for m in chat.serializar_lista(self.con, r2['mensagens'], self.func) if m['cartao']][0]
        self.assertEqual(c2['subtipo'], 'grafico')
        self.assertEqual(c2['dados']['modo'], 'barras')
        self.assertEqual(c2['dados']['series'][0]['valores'], [12, 18, 15])

        # 3) cartao_info
        r3 = motor.talvez_responder(self.con, self.func, 'Mostra a ficha')
        c3 = [m['cartao'] for m in chat.serializar_lista(self.con, r3['mensagens'], self.func) if m['cartao']][0]
        self.assertEqual(c3['subtipo'], 'cartao_info')
        self.assertEqual(c3['dados']['icone'], 'calendar-days')
        self.assertEqual(c3['dados']['destaque'], 'Confirmado')

        # 4) cartao_permissao
        r4 = motor.talvez_responder(self.con, self.func, 'O que muda nas permissões?')
        c4 = [m['cartao'] for m in chat.serializar_lista(self.con, r4['mensagens'], self.func) if m['cartao']][0]
        self.assertEqual(c4['subtipo'], 'cartao_permissao')
        self.assertEqual(c4['dados']['alvo'], 'IA_ALVO')
        self.assertEqual(len(c4['dados']['autorizadores']), 2)
        self.assertEqual(c4['dados']['grupos'][0]['itens'][0]['tipo'], 'mais')

    def test_grafico_linhas_pizza_rosca_e_tipo_desconhecido_fallback(self):
        for modo in ('linhas', 'pizza', 'rosca'):
            sub, _tit, _subt, _rod, dados = ilustrar.preparar('grafico', {
                'titulo': 'Teste ' + modo,
                'modo': modo,
                'itens': [{'rotulo': 'A', 'valor': 10}, {'rotulo': 'B', 'valor': 20}],
            })
            self.assertEqual(sub, 'grafico')
            self.assertEqual(dados['modo'], modo)
            self.assertEqual(dados['rotulos'], ['A', 'B'])

        sub_fb, tit_fb, _s, _r, dados_fb = ilustrar.preparar('diagrama_desconhecido', {
            'titulo': 'Algo novo',
            'texto': '<script>xss</script> Texto comum',
        })
        self.assertEqual(sub_fb, 'texto')
        self.assertEqual(tit_fb, 'Algo novo')
        self.assertNotIn('<script>', dados_fb['texto'])
        self.assertIn('&lt;script&gt;xss&lt;/script&gt;', dados_fb['texto'])

    def test_limites_e_escape_html(self):
        cols = [f'<b>Col{i}</b>' for i in range(40)]
        linhas = [[f'<img onerror=x>{r}_{c}' for c in range(40)] for r in range(620)]
        sub, tit, subt, rod, dados = ilustrar.preparar('planilha', {
            'titulo': '<script>alert(1)</script>' + 'X' * 250,
            'subtitulo': '<i>Sub</i>',
            'rodape': '<u>Fim</u>',
            'colunas': cols,
            'linhas': linhas,
        })
        self.assertEqual(sub, 'planilha')
        self.assertEqual(len(dados['colunas']), ilustrar.MAX_COLUNAS)
        self.assertEqual(len(dados['linhas']), ilustrar.MAX_LINHAS)
        self.assertNotIn('<script>', tit)
        self.assertTrue(tit.startswith('&lt;script&gt;'))
        self.assertLessEqual(len(tit), ilustrar.MAX_TITULO + 30)  # + entidades escapadas após corte em 200
        self.assertNotIn('<', dados['colunas'][0])
        self.assertNotIn('<img', str(dados['linhas'][0][0]))
        self.assertIn('&lt;img onerror=x&gt;', dados['linhas'][0][0])

        # Ícone inventado/malicioso não passa na whitelist
        _s, _t, _sb, _rd, info = ilustrar.preparar('cartao_info', {
            'icone': 'javascript:alert(1)',
            'itens': [{'rotulo': '<a>R</a>', 'valor': '<b>V</b>'}],
        })
        self.assertEqual(info['icone'], 'clipboard-list')
        self.assertEqual(info['itens'][0]['rotulo'], '&lt;a&gt;R&lt;/a&gt;')

    def test_somente_bot_pode_publicar_ilustracao(self):
        # 1) Usuário humano tentando enviar campo cartao pelo endpoint HTTP
        resp = self._postar_chat('IA_REC', self.admin, 'Oi', extras={
            'cartao': json.dumps({'tipo': 'IA_ILUSTRACAO', 'subtipo': 'planilha', 'titulo': 'Falsa'}),
        })
        self.assertEqual(resp.status_code, 200)
        msg_srv = resp.get_json()['mensagem']
        self.assertIsNone(msg_srv['cartao'])

        # 2) Tentativa direta via chat.enviar_cartao usando id humano
        with self.assertRaises(chat.ErroChat):
            chat.enviar_cartao(
                self.con, self.func, self.admin,
                {'tipo': 'IA_ILUSTRACAO', 'subtipo': 'cartao_info', 'titulo': 'Forjada'},
                'Forjada',
            )

        # 3) Linha adulterada direto no SQLite por usuário humano é filtrada em serializar_lista
        cur = self.con.execute(
            'INSERT INTO chat_mensagens (de_id, para_id, corpo, criado_em, cartao) VALUES (?,?,?,?,?)',
            (self.func, self.admin, 'forjada', '2026-01-01 10:00:00',
             json.dumps({'tipo': 'IA_ILUSTRACAO', 'subtipo': 'planilha', 'titulo': 'Falsa'})),
        )
        self.con.commit()
        linha = self.con.execute('SELECT * FROM chat_mensagens WHERE id=?', (cur.lastrowid,)).fetchone()
        ser = chat.serializar_lista(self.con, [linha], self.admin)[0]
        self.assertIsNone(ser['cartao'])

    def test_continuidade_substitui_e_ilustracao_atual(self):
        motor.BAIXAR = OpenRouter(
            ('ilustrar', {
                'tipo': 'planilha',
                'titulo': 'Pacientes',
                'colunas': ['Nome', 'Idade'],
                'linhas': [['Ana', 25], ['Carlos', 68], ['Bia', 41]],
            }),
            'Criei a planilha inicial. <<confianca:5>>',
        )
        r1 = motor.talvez_responder(self.con, self.func, 'Liste os pacientes')
        c1 = [m['cartao'] for m in chat.serializar_lista(self.con, r1['mensagens'], self.func) if m['cartao']][0]
        id1 = c1['id']

        # Segunda rodada: IA consulta ilustracao_atual e reenvia com substitui=id1
        fake2 = OpenRouter(
            ('ilustracao_atual', {}),
            ('ilustrar', {
                'tipo': 'planilha',
                'titulo': 'Pacientes (por idade)',
                'substitui': id1,
                'colunas': ['Nome', 'Idade'],
                'linhas': [['Carlos', 68], ['Bia', 41], ['Ana', 25]],
            }),
            'Reorganizei do mais velho ao mais novo. <<confianca:5>>',
        )
        motor.BAIXAR = fake2
        r2 = motor.talvez_responder(self.con, self.func, 'Organize por idade, do mais velho ao mais novo')
        c2 = [m['cartao'] for m in chat.serializar_lista(self.con, r2['mensagens'], self.func) if m['cartao']][0]

        self.assertEqual(c2['substitui'], id1)
        self.assertNotEqual(c2['id'], id1)
        self.assertEqual(c2['dados']['linhas'][0], ['Carlos', 68])

        # Verifica que o histórico da ferramenta ilustracao_atual entregou os dados anteriores à IA
        mensagens_pedido2 = fake2.pedidos[1]['messages']
        tool_msgs = [m for m in mensagens_pedido2 if m.get('role') == 'tool']
        self.assertTrue(any('Carlos' in (m.get('content') or '') for m in tool_msgs))

        # O bloco antigo ficou marcado como substituído e ilustracao_atual retorna o mais recente
        antigo = self.con.execute('SELECT substituido_por FROM nucleai_ilustracoes WHERE id=?', (id1,)).fetchone()
        self.assertEqual(antigo['substituido_por'], c2['id'])
        ultimo = ilustrar.atual(self.con, self.func, treino=False)
        self.assertEqual(ultimo['id'], c2['id'])

    def test_download_excel_protegido_e_30_colunas(self):
        cols30 = [f'C{i}' for i in range(1, 31)]
        linhas30 = [[f'V{i}' if i > 1 else '=SUM(B1:B2)' for i in range(1, 31)],
                    ['Ana & Maria'] + [i for i in range(2, 31)]]
        _sub, tit, subt, rod, dados = ilustrar.preparar('planilha', {
            'titulo': 'Planilha Larga 30 Colunas',
            'colunas': cols30,
            'linhas': linhas30,
        })
        iid, _c = ilustrar.salvar(self.con, self.func, False, 'planilha', tit, subt, rod, dados)

        # Bloco que não é planilha não gera Excel
        _s2, t2, sb2, rd2, d2 = ilustrar.preparar('grafico', {'titulo': 'Graf', 'rotulos': ['A'], 'valores': [1]})
        iid_graf, _c2 = ilustrar.salvar(self.con, self.func, False, 'grafico', t2, sb2, rd2, d2)

        # Anônimo não acessa
        cli_anon = self.app.test_client()
        r_anon = cli_anon.get(f'/mensagens/ilustracao/{iid}/excel')
        self.assertEqual(r_anon.status_code, 302)

        # Outro usuário recebe 404
        cli_outro = self.cliente('IA_FIN', 'senha123')
        r_outro = cli_outro.get(f'/mensagens/ilustracao/{iid}/excel')
        self.assertEqual(r_outro.status_code, 404)

        # Dono tentando baixar gráfico recebe 404
        cli_dono = self.cliente('IA_REC', 'senha123')
        r_graf = cli_dono.get(f'/mensagens/ilustracao/{iid_graf}/excel')
        self.assertEqual(r_graf.status_code, 404)

        # Dono baixa planilha com 30 colunas com sucesso
        r_ok = cli_dono.get(f'/mensagens/ilustracao/{iid}/excel')
        self.assertEqual(r_ok.status_code, 200)
        self.assertIn('spreadsheetml.sheet', r_ok.content_type)
        wb = load_workbook(io.BytesIO(r_ok.data))
        ws = wb.active
        self.assertEqual(ws.cell(3, 1).value, 'C1')
        self.assertEqual(ws.cell(3, 30).value, 'C30')
        self.assertEqual(ws.cell(4, 1).value, "'=SUM(B1:B2)")
        self.assertEqual(ws.cell(5, 1).value, 'Ana & Maria')
        self.assertEqual(ws.cell(5, 30).value, 30)

    def test_cartao_decisao_ligado_ao_pendente_e_travamento(self):
        motor.BAIXAR = OpenRouter(
            ('acessos_alterar', {'usuario': 'IA_ALVO', 'adicionar': ['dashboard'], 'remover': []}),
            ('ilustrar', {
                'tipo': 'cartao_decisao',
                'titulo': 'Confirmar alteração',
                'pergunta': 'Liberar o módulo Dashboard para IA_ALVO?',
                'risco': 'medio',
            }),
            'Confirme clicando em Sim ou Não. <<confianca:5>>',
        )
        r1 = motor.talvez_responder(self.con, self.admin, 'Libera dashboard para IA_ALVO')
        msgs1 = chat.serializar_lista(self.con, r1['mensagens'], self.admin)
        decisoes = [m['cartao'] for m in msgs1 if m['cartao'] and m['cartao'].get('subtipo') == 'cartao_decisao']
        self.assertEqual(len(decisoes), 1)
        dec_id = decisoes[0]['id']
        self.assertIsNone(decisoes[0]['decisao_resp'])

        # Resposta "Sim" aciona _tratar_pendente -> confirmar(), aplica acesso e trava o cartão
        r2 = motor.talvez_responder(self.con, self.admin, 'Sim')
        self.assertTrue(any('Pronto' in m['corpo'] for m in r2['mensagens']))

        u_alvo = self.con.execute('SELECT modulos FROM usuarios WHERE id=?', (self.alvo,)).fetchone()
        self.assertIn('dashboard', json.loads(u_alvo['modulos']))

        # Ao recarregar as mensagens do banco, o cartao_decisao vem travado com decisao_resp == 'SIM'
        recarregadas = chat.conversa(self.con, self.admin, self.bot)
        ser = chat.serializar_lista(self.con, recarregadas, self.admin)
        card_rec = [m['cartao'] for m in ser if m['cartao'] and m['cartao'].get('id') == dec_id][0]
        self.assertEqual(card_rec['decisao_resp'], 'SIM')

        # Fluxo equivalente com "Não" no chat de treinamento: cancela e trava como 'NAO'
        motor.BAIXAR = OpenRouter(
            ('acessos_alterar', {'usuario': 'IA_ALVO', 'adicionar': ['contas'], 'remover': []}),
            ('ilustrar', {
                'tipo': 'cartao_decisao',
                'titulo': 'Confirmar contas',
                'pergunta': 'Liberar Contas para IA_ALVO?',
            }),
            'Confirma? <<confianca:5>>',
        )
        ia.trocar_treinador(self.con, self.admin, 'Chefe#0001')
        motor.responder_treino(self.con, self.admin, 'Dá contas para IA_ALVO')
        r_nao = motor.responder_treino(self.con, self.admin, 'Não')
        self.assertTrue(any('cancelei' in m['texto'].lower() for m in r_nao))

        u_alvo2 = self.con.execute('SELECT modulos FROM usuarios WHERE id=?', (self.alvo,)).fetchone()
        self.assertNotIn('contas', json.loads(u_alvo2['modulos']))

        hist_treino = motor.conversa_treino(self.con, self.admin)
        cards_treino = [m['cartao'] for m in hist_treino if m['cartao'] and m['cartao'].get('subtipo') == 'cartao_decisao']
        self.assertEqual(cards_treino[-1]['decisao_resp'], 'NAO')


if __name__ == '__main__':
    unittest.main()
