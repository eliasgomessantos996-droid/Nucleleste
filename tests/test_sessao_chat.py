"""Sessão única, avisos de MIBI e transmissão individual da gestão."""
import json
import os
import sqlite3
import tempfile
import unittest
from unittest import mock

from werkzeug.security import generate_password_hash

from app import agenda, chat, create_app, views_chat
from app import db as dbmod


class SessaoChat(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        ambiente = mock.patch.dict(os.environ, {'NUCLELESTE_DADOS': self.pasta.name})
        ambiente.start()
        self.addCleanup(ambiente.stop)
        self.app = create_app(os.path.join(self.pasta.name, 't.db'))
        self.app.config['TESTING'] = True
        self.db = dbmod.conectar(self.app.config['DATABASE'])
        self.addCleanup(self.db.close)
        self.admin = self.db.execute("SELECT id FROM usuarios WHERE usuario='ADMIN'").fetchone()[0]

    def usuario(self, nome, mods=(), admin=0):
        uid = self.db.execute('INSERT INTO usuarios (usuario, senha_hash, modulos, admin) VALUES (?,?,?,?)',
                              (nome, generate_password_hash('senha123'), json.dumps(list(mods)), admin)).lastrowid
        self.db.commit()
        return uid

    def cliente(self, nome='ADMIN', senha='admin'):
        c = self.app.test_client()
        c.get('/login')
        r = self.post(c, '/login', {'usuario': nome, 'senha': senha})
        self.assertEqual(r.status_code, 302)
        c.get('/minha-senha')
        return c

    def post(self, c, url, dados=None, **kw):
        with c.session_transaction() as s:
            token = s.get('csrf', '')
        return c.post(url, data=dict(dados or {}, _csrf=token), **kw)

    def horario(self, dia='2026-11-02', exame='MIBI', etapa='Estresse', nome='Agenda do exame'):
        eid = self.db.execute('SELECT id FROM exames WHERE nome=?', (exame,)).fetchone()[0]
        dados = agenda.validar_nova({'data': dia, 'exame': nome, 'exame_id': str(eid), 'inicio': '08:00',
                                    'intervalo': '30', 'qtd': '3', 'vagas': '1', 'etapa': etapa}, self.db)
        aid = agenda.criar(self.db, dados, 'ADMIN')['ids'][0]
        return self.db.execute('SELECT id FROM agenda_horarios WHERE agenda_id=? ORDER BY id', (aid,)).fetchone()[0]

    def mensagens_agenda(self):
        return self.db.execute("SELECT * FROM chat_mensagens WHERE tipo='AGENDA_MIBI' ORDER BY id").fetchall()

    def test_segundo_login_encerra_apenas_a_sessao_antiga(self):
        antigo = self.cliente()
        with antigo.session_transaction() as s:
            identificador = s['sessao_id']
        novo = self.cliente()
        with novo.session_transaction() as s:
            self.assertNotEqual(identificador, s['sessao_id'])
        r = antigo.get('/mensagens')
        self.assertEqual(r.status_code, 302)
        self.assertIn('motivo=outro_login', r.location)
        self.assertIn('Sua sessão foi encerrada porque você entrou em outro computador', antigo.get(r.location).get_data(as_text=True))
        with antigo.session_transaction() as s:
            self.assertNotIn('uid', s)
        self.assertEqual(novo.get('/mensagens').status_code, 200)

    def test_polling_e_post_antigos_recebem_login_sem_executar_acao(self):
        for url in ('/mensagens/novas', '/sessao/batida', '/mensagens/enviar'):
            with self.subTest(url=url):
                antigo = self.cliente()
                self.cliente()
                cabecalho = {'Accept': 'application/json', 'X-Passivo': '1'}
                r = antigo.get(url, headers=cabecalho) if url.endswith('novas') else self.post(antigo, url, {'aba': 'teste', 'para': self.admin, 'corpo': 'Não gravar'}, headers=cabecalho)
                self.assertEqual(r.status_code, 401)
                self.assertIn('outro_login', r.get_json()['login'])
                self.assertEqual(r.headers['X-Login-URL'], r.get_json()['login'])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM chat_mensagens').fetchone()[0], 0)

    def test_outro_usuario_e_senha_incorreta_nao_derrubam_sessao(self):
        self.usuario('ANA', ['agenda'])
        c = self.cliente()
        self.cliente('ANA', 'senha123')
        tentativa = self.app.test_client()
        tentativa.get('/login')
        self.assertEqual(self.post(tentativa, '/login', {'usuario': 'ADMIN', 'senha': 'errada'}).status_code, 200)
        self.assertEqual(c.get('/mensagens').status_code, 200)

    def test_relogin_da_sessao_substituida_aceita_csrf_e_permanece_logado(self):
        antigo = self.cliente()
        novo = self.cliente()
        self.assertEqual(self.post(antigo, '/login', {'usuario': 'ADMIN', 'senha': 'admin'}).status_code, 302)
        self.assertEqual(antigo.get('/mensagens').status_code, 200)
        self.assertEqual(novo.get('/mensagens/novas', headers={'Accept': 'application/json'}).status_code, 401)

    def test_sessao_legada_so_e_descartada_depois_do_proximo_login(self):
        c = self.app.test_client()
        with c.session_transaction() as s:
            s['uid'] = self.admin
        self.assertEqual(c.get('/mensagens').status_code, 200)
        self.cliente()
        self.assertIn('outro_login', c.get('/mensagens').location)

    def test_login_direto_mostra_aviso_e_logout_antigo_nao_afeta_o_novo(self):
        antigo = self.cliente()
        novo = self.cliente()
        r = self.post(antigo, '/logout', headers={'Accept': 'application/json'})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(novo.get('/mensagens').status_code, 200)
        terceiro = self.cliente()
        pagina = novo.get('/login').get_data(as_text=True)
        self.assertIn('Sua sessão foi encerrada porque você entrou em outro computador', pagina)
        self.assertEqual(terceiro.get('/mensagens').status_code, 200)

    def test_consulta_em_espera_revalida_sessao_antes_de_responder(self):
        c = self.cliente()
        def substituir(*args):
            self.db.execute("UPDATE usuarios SET sessao_id='outra' WHERE id=?", (self.admin,))
            self.db.commit()
        with mock.patch.object(views_chat, '_aguardar_novidade', side_effect=substituir):
            r = c.get('/mensagens/novas?espera=1', headers={'Accept': 'application/json'})
        self.assertEqual(r.status_code, 401)
        self.assertIn('outro_login', r.get_json()['login'])

    def test_login_e_canais_exigem_csrf(self):
        c = self.app.test_client()
        c.get('/login')
        self.assertEqual(c.post('/login', data={'usuario': 'ADMIN', 'senha': 'admin'}).status_code, 400)
        c = self.cliente()
        for url in ('/mensagens/canais/salvar', '/mensagens/canais/1/enviar', '/mensagens/canais/1/excluir'):
            self.assertEqual(c.post(url).status_code, 400)

    def test_aviso_mibi_usa_exame_vinculado_etapa_e_destinatarios_corretos(self):
        gerente = self.usuario('GERENTE', ['gerencia'])
        comum = self.usuario('RECEPCAO', ['agenda'])
        hid = self.horario()
        agenda.salvar_campo(self.db, hid, 'paciente', 'João da Silva', '', 'ADMIN')
        msgs = self.mensagens_agenda()
        self.assertIn(gerente, {m['para_id'] for m in msgs})
        self.assertNotIn(comum, {m['para_id'] for m in msgs})
        for texto in ('João da Silva', '02/11/2026', 'Estresse'):
            self.assertIn(texto, msgs[0]['corpo'])
        contato = self.db.execute('SELECT id FROM usuarios WHERE sistema=4').fetchone()[0]
        self.assertEqual(msgs[0]['de_id'], contato)
        self.assertIn(contato, {c['id'] for c in chat.contatos(self.db, gerente)})
        self.assertNotIn(contato, {c['id'] for c in chat.contatos(self.db, comum)})
        with self.assertRaises(chat.ErroChat):
            chat.enviar(self.db, self.admin, contato, 'Responder')

    def test_aviso_nao_duplica_salvar_igual_e_informa_correcao_da_etapa(self):
        hid = self.horario()
        agenda.salvar_campo(self.db, hid, 'paciente', 'Maria', '', 'ADMIN')
        n = len(self.mensagens_agenda())
        agenda.salvar_campo(self.db, hid, 'paciente', 'Maria', 'Maria', 'ADMIN')
        agenda.salvar_campo(self.db, hid, 'contato', '33332222', '', 'ADMIN')
        self.assertEqual(len(self.mensagens_agenda()), n)
        agenda.salvar_campo(self.db, hid, 'senha', 'Protocolo', 'Estresse', 'ADMIN')
        self.assertIn('Protocolo', self.mensagens_agenda()[-1]['corpo'])
        self.assertEqual(len(self.mensagens_agenda()), 2 * n)

    def test_outro_exame_e_linha_sem_paciente_nao_avisam(self):
        hid = self.horario(exame='ÓSSEA', etapa='')
        agenda.salvar_campo(self.db, hid, 'paciente', 'Ana', '', 'ADMIN')
        hid = self.horario(dia='2026-11-03')
        agenda.salvar_campo(self.db, hid, 'senha', 'Repouso', 'Estresse', 'ADMIN')
        self.assertEqual(self.mensagens_agenda(), [])

    def test_configuracao_desliga_e_religa_aviso(self):
        c = self.cliente()
        self.assertIn('name="agenda_aviso_mibi" value="1" checked', c.get('/configuracoes').get_data(as_text=True))
        self.post(c, '/configuracoes', {'clinica_nome': 'Clínica teste'})
        hid = self.horario()
        agenda.salvar_campo(self.db, hid, 'paciente', 'Ana', '', 'ADMIN')
        self.assertEqual(self.mensagens_agenda(), [])
        self.post(c, '/configuracoes', {'agenda_aviso_mibi': '1'})
        agenda.salvar_campo(self.db, hid, 'senha', 'Repouso', 'Estresse', 'ADMIN')
        self.assertTrue(self.mensagens_agenda())

    def test_falha_no_aviso_e_registrada_sem_desfazer_agendamento(self):
        hid = self.horario()
        with mock.patch.object(chat, 'avisar_agendamento_mibi', side_effect=RuntimeError('Falha simulada')):
            with self.assertLogs('app.agenda', level='ERROR') as registro:
                agenda.salvar_campo(self.db, hid, 'paciente', 'Paciente mantido', '', 'ADMIN')
        self.assertIn('agendamento foi mantido', registro.output[0])
        con = dbmod.conectar(self.app.config['DATABASE'])
        try:
            self.assertEqual(con.execute('SELECT paciente FROM agenda_horarios WHERE id=?', (hid,)).fetchone()[0], 'Paciente mantido')
        finally:
            con.close()

    def test_remarcar_copiar_recortar_e_copiar_dia_enviam_avisos(self):
        origem = self.horario()
        agenda.salvar_campo(self.db, origem, 'paciente', 'Ana', '', 'ADMIN')
        destino = self.horario(dia='2026-11-03')
        n = len(self.mensagens_agenda())
        agenda.remarcar(self.db, origem, destino, 'ADMIN')
        self.assertEqual(len(self.mensagens_agenda()), n * 2)
        terceiro = self.horario(dia='2026-11-04')
        agenda.copiar_linha(self.db, destino, terceiro, 'ADMIN')
        quarto = self.horario(dia='2026-11-05')
        agenda.recortar_linha(self.db, terceiro, quarto, 'ADMIN')
        agenda.copiar(self.db, '2026-11-05', '2026-11-06', True, None, 'ADMIN')
        self.assertEqual(len(self.mensagens_agenda()), n * 5)
        self.assertIn('06/11/2026', self.mensagens_agenda()[-1]['corpo'])
        self.assertIn('Repouso', self.mensagens_agenda()[-1]['corpo'])

    def test_falha_parcial_dos_avisos_preserva_paciente_e_desfaz_so_mensagens(self):
        gerente = self.usuario('GESTAO_AVISO', ['gerencia'])
        hid = self.horario()
        self.db.execute("CREATE TRIGGER falha_aviso BEFORE INSERT ON chat_mensagens WHEN NEW.tipo='AGENDA_MIBI' AND NEW.para_id=%d BEGIN SELECT RAISE(ABORT, 'Falha simulada'); END" % gerente)
        self.db.commit()
        with self.assertLogs('app.agenda', level='ERROR'):
            agenda.salvar_campo(self.db, hid, 'paciente', 'Paciente mantido', '', 'ADMIN')
        self.assertEqual(self.mensagens_agenda(), [])
        self.assertEqual(self.db.execute('SELECT paciente FROM agenda_horarios WHERE id=?', (hid,)).fetchone()[0], 'Paciente mantido')

    def test_canal_cria_edita_e_entrega_mensagens_individuais(self):
        ana = self.usuario('ANA', ['agenda'])
        bia = self.usuario('BIA', ['agenda_leitura'])
        cid = chat.salvar_canal(self.db, self.admin, 0, 'Equipe', [ana, ana, bia])
        self.assertEqual(len(chat.canais(self.db, self.admin)[0]['membros']), 2)
        self.assertEqual(chat.transmitir(self.db, self.admin, cid, 'Reunião às 15h'), 2)
        for uid in (ana, bia):
            self.assertEqual(chat.conversa(self.db, uid, self.admin)[-1]['corpo'], 'Reunião às 15h')
        chat.enviar(self.db, ana, self.admin, 'Confirmado')
        self.assertEqual(chat.conversa(self.db, bia, ana), [])
        chat.salvar_canal(self.db, self.admin, cid, 'Equipe menor', [bia])
        self.assertEqual(chat.canais(self.db, self.admin)[0]['membros'], [bia])
        self.assertEqual(chat.transmitir(self.db, self.admin, cid, 'Só para Bia'), 1)
        chat.excluir_canal(self.db, self.admin, cid)
        self.assertEqual(chat.canais(self.db, self.admin), [])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM chat_canal_membros').fetchone()[0], 0)
        self.assertEqual(chat.conversa(self.db, bia, self.admin)[-1]['corpo'], 'Só para Bia')

    def test_so_gestao_pode_usar_canais_mesmo_com_modulo_gerencia(self):
        uid = self.usuario('COMUM', ['agenda', 'gerencia'])
        self.assertFalse(chat.pode_transmitir(self.db, uid))
        for funcao, args in ((chat.salvar_canal, (0, 'Inválido', [self.admin])), (chat.canais, ()),
                             (chat.transmitir, (1, 'Oi')), (chat.excluir_canal, (1,))):
            with self.assertRaises(chat.ErroChat):
                funcao(self.db, uid, *args)
        c = self.cliente('COMUM', 'senha123')
        self.assertNotIn('Criar grupo', c.get('/mensagens').get_data(as_text=True))
        for url in ('/mensagens/canais/salvar', '/mensagens/canais/1/enviar', '/mensagens/canais/1/excluir'):
            self.assertEqual(self.post(c, url).status_code, 403)

    def test_canal_rejeita_inativos_sistema_sem_agenda_e_outro_gestor(self):
        ana = self.usuario('ANA', ['agenda'])
        fora = self.usuario('SEM_AGENDA')
        inativo = self.usuario('INATIVO', ['agenda'])
        self.db.execute('UPDATE usuarios SET ativo=0 WHERE id=?', (inativo,))
        self.db.commit()
        sistema = self.db.execute('SELECT id FROM usuarios WHERE sistema=4').fetchone()[0]
        for invalido in (fora, inativo, sistema, self.admin, 99999, 'abc'):
            with self.assertRaises(chat.ErroChat):
                chat.salvar_canal(self.db, self.admin, 0, 'Inválido', [ana, invalido])
        self.assertEqual(chat.canais(self.db, self.admin), [])
        cid = chat.salvar_canal(self.db, self.admin, 0, 'Privado', [ana])
        outro = self.usuario('OUTRA_GESTAO', admin=1)
        self.assertEqual(chat.canais(self.db, outro), [])
        with self.assertRaises(chat.ErroChat):
            chat.transmitir(self.db, outro, cid, 'Sem acesso')
        with self.assertRaises(chat.ErroChat):
            chat.salvar_canal(self.db, outro, cid, 'Alterado', [ana])
        with self.assertRaises(chat.ErroChat):
            chat.excluir_canal(self.db, outro, cid)

    def test_envio_revalida_permissoes_e_atividade_dos_membros(self):
        ana = self.usuario('ANA', ['agenda'])
        bia = self.usuario('BIA', ['agenda'])
        cid = chat.salvar_canal(self.db, self.admin, 0, 'Equipe', [ana, bia])
        self.db.execute("UPDATE usuarios SET modulos='[]' WHERE id=?", (ana,))
        self.db.commit()
        self.assertEqual(chat.transmitir(self.db, self.admin, cid, 'Para Bia'), 1)
        self.db.execute('UPDATE usuarios SET ativo=0 WHERE id=?', (bia,))
        self.db.commit()
        with self.assertRaises(chat.ErroChat):
            chat.transmitir(self.db, self.admin, cid, 'Ninguém')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM chat_mensagens').fetchone()[0], 1)

    def test_transmissao_e_atomica_se_um_destinatario_falhar(self):
        ana = self.usuario('ANA', ['agenda'])
        bia = self.usuario('BIA', ['agenda'])
        cid = chat.salvar_canal(self.db, self.admin, 0, 'Equipe', [ana, bia])
        self.db.execute("CREATE TRIGGER falha_chat BEFORE INSERT ON chat_mensagens WHEN NEW.para_id=%d BEGIN SELECT RAISE(ABORT, 'Falha simulada'); END" % bia)
        self.db.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            chat.transmitir(self.db, self.admin, cid, 'Tudo ou nada')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM chat_mensagens').fetchone()[0], 0)

    def test_validacoes_de_nome_corpo_e_limite_de_envio(self):
        ana = self.usuario('ANA', ['agenda'])
        for nome, membros in (('', [ana]), ('a' * 81, [ana]), ('Equipe', [])):
            with self.assertRaises(chat.ErroChat):
                chat.salvar_canal(self.db, self.admin, 0, nome, membros)
        cid = chat.salvar_canal(self.db, self.admin, 0, 'Equipe', [ana])
        for corpo in (' ', 'a' * 2001):
            with self.assertRaises(chat.ErroChat):
                chat.transmitir(self.db, self.admin, cid, corpo)
        for i in range(chat.MAX_POR_MINUTO):
            chat.enviar(self.db, self.admin, ana, str(i))
        with self.assertRaises(chat.ErroChat):
            chat.transmitir(self.db, self.admin, cid, 'Aguardar')

    def test_grupo_maior_que_limite_individual_recebe_o_lote_completo(self):
        senha = self.db.execute('SELECT senha_hash FROM usuarios WHERE id=?', (self.admin,)).fetchone()[0]
        ids = []
        for i in range(chat.MAX_POR_MINUTO + 2):
            ids.append(self.db.execute('INSERT INTO usuarios (usuario, senha_hash, modulos) VALUES (?,?,?)',
                                       ('DESTINO_%d' % i, senha, '["agenda"]')).lastrowid)
        self.db.commit()
        cid = chat.salvar_canal(self.db, self.admin, 0, 'Toda a equipe', ids)
        self.assertEqual(chat.transmitir(self.db, self.admin, cid, 'Para todos'), len(ids))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM chat_mensagens WHERE de_id=?', (self.admin,)).fetchone()[0], len(ids))

    def test_fluxo_das_telas_de_canal_e_tema_escuro(self):
        ana = self.usuario('ANA', ['agenda'])
        c = self.cliente()
        self.post(c, '/meu-tema', {'brilho': 'escuro'})
        r = self.post(c, '/mensagens/canais/salvar', {'nome': 'Equipe <teste>', 'membros': [str(ana)]})
        self.assertEqual(r.status_code, 302)
        pagina = c.get(r.location).get_data(as_text=True)
        for trecho in ('data-brilho="escuro"', 'Equipe &lt;teste&gt;', 'Enviar para todos', 'Editar nome e membros', 'chat-canal-desenho', '#i-users'):
            self.assertIn(trecho, pagina)
        cid = chat.canais(self.db, self.admin)[0]['id']
        r = self.post(c, '/mensagens/canais/%d/enviar' % cid, {'corpo': 'Aviso pela tela'}, follow_redirects=True)
        self.assertIn('Mensagem enviada individualmente para 1 pessoa(s).', r.get_data(as_text=True))
        self.post(c, '/mensagens/canais/salvar', {'canal': str(cid), 'nome': 'Novo nome', 'membros': [str(ana)]})
        self.assertEqual(chat.canais(self.db, self.admin)[0]['nome'], 'Novo nome')
        self.assertEqual(self.post(c, '/mensagens/canais/%d/excluir' % cid).status_code, 302)
        self.assertEqual(chat.canais(self.db, self.admin), [])

    def test_migracao_idempotente_preserva_configuracao_e_dados(self):
        self.db.execute('ALTER TABLE usuarios DROP COLUMN sessao_id')
        self.db.execute("UPDATE config SET valor='0' WHERE chave='agenda_aviso_mibi'")
        self.db.commit()
        dbmod.inicializar(self.app.config['DATABASE'])
        dbmod.inicializar(self.app.config['DATABASE'])
        self.assertIn('sessao_id', {r[1] for r in self.db.execute('PRAGMA table_info(usuarios)')})
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM usuarios WHERE sistema=4').fetchone()[0], 1)
        self.assertEqual(self.db.execute("SELECT valor FROM config WHERE chave='agenda_aviso_mibi'").fetchone()[0], '0')


if __name__ == '__main__':
    unittest.main()
