"""Consultas e remarcação da agenda pela NucleAI, sem chamadas de rede."""
import json
import unittest
from datetime import date, timedelta
from unittest import mock

from app import db as dbmod
from app import nucleai_ferramentas as ferr
from app import nucleai_ia as ia
from tests.test_chat_blindagens import Base


class AgendaIATestes(Base):
    def setUp(self):
        rede = mock.patch('urllib.request.urlopen', side_effect=AssertionError('Teste tentou baixar dados'))
        rede.start()
        self.addCleanup(rede.stop)
        self.uid = self.criar_usuario('IA_AGENDA', ['agenda'])
        self.comum = self.criar_usuario('IA_COMUM', ['agenda_leitura'])
        self.gerente = self.criar_usuario('IA_GERENTE', ['agenda', 'gerencia', 'registros'])
        self.db = dbmod.conectar(self.app.config['DATABASE'])
        self.addCleanup(self.db.close)
        self.db.execute('DELETE FROM agenda_horarios')
        self.db.execute('DELETE FROM agenda_exames')
        self.db.execute("DELETE FROM auditoria WHERE acao LIKE '%NucleAI%'")
        self.db.execute("DELETE FROM config WHERE chave LIKE 'nucleai_llm_%'")
        self.dia = (date.today() + timedelta(days=30)).isoformat()
        self.outro = (date.today() + timedelta(days=31)).isoformat()
        self.db.execute("INSERT INTO agenda_exames (data, exame, inicio, intervalo, vagas) VALUES (?,'MIBI','08:00',30,1)", (self.dia,))
        aid = self.db.execute('SELECT last_insert_rowid()').fetchone()[0]
        self.db.execute("INSERT INTO agenda_horarios (agenda_id, hora, paciente, convenio, senha) VALUES (?,'08:00','Maria Silva','UNIMED','Estresse')", (aid,))
        self.hid = self.db.execute('SELECT last_insert_rowid()').fetchone()[0]
        self.db.execute("INSERT INTO agenda_exames (data, exame, inicio, intervalo, vagas) VALUES (?,'MIBI','10:00',30,1)", (self.outro,))
        destino_aid = self.db.execute('SELECT last_insert_rowid()').fetchone()[0]
        for hora in ('10:00', '11:30'):
            self.db.execute('INSERT INTO agenda_horarios (agenda_id, hora) VALUES (?,?)', (destino_aid, hora))
        self.db.commit()
        self.ctx = ferr.contexto(self.db, self.uid, nivel=4)

    def _propor(self, hora='10:00'):
        return ferr.chamar(self.ctx, 'agenda_remarcar', {'data': self.dia, 'hora': '08:00', 'exame': 'MIBI',
                                                       'nova_data': self.outro, 'nova_hora': hora})

    def test_consulta_por_dia_e_hora(self):
        r = ferr.chamar(self.ctx, 'agenda_consultar', {'data': self.dia, 'hora': '08:00'})
        self.assertIn('Maria Silva', r['resumo'])
        self.assertEqual(r['cartao']['subtipo'], 'cartao_info')
        self.assertIn('Estresse', str(r['cartao']['dados']))
        r = ferr.chamar(self.ctx, 'paciente_agendamentos', {'paciente': 'Maria'})
        self.assertIn('Próximos: 1', r['resumo'])
        ia.definir(self.db, 'nucleai_llm_dados_pacientes', '0')
        r = ferr.chamar(self.ctx, 'agenda_consultar', {'data': self.dia})
        self.assertNotIn('Maria Silva', r['resumo'])

    def test_remarcar_livre_auditar_e_desfazer_pela_gerencia(self):
        r = self._propor()
        self.assertEqual(r['cartao']['subtipo'], 'cartao_decisao')
        self.assertEqual(self.db.execute('SELECT paciente FROM agenda_horarios WHERE hora=? AND agenda_id=(SELECT id FROM agenda_exames WHERE data=? LIMIT 1)', ('10:00', self.outro)).fetchone()[0], '')
        feito = ferr.confirmar(self.ctx, r['pendente'])
        self.assertIn('remarcado', feito['texto'])
        audit = self.db.execute("SELECT * FROM auditoria WHERE acao LIKE '%Remarcou paciente na agenda%' ORDER BY id DESC LIMIT 1").fetchone()
        self.assertEqual(audit['usuario_id'], self.uid)
        self.assertEqual(audit['usuario'], 'IA_AGENDA')
        self.assertIn('Feito com auxílio da NucleAI', audit['acao'])
        self.assertTrue(json.loads(audit['desfazer'])['tabelas'])
        # Usuário comum não desfaz; gerência pode usar a própria rota de registros.
        with self.app.test_request_context('/registros/%d/desfazer' % audit['id'], method='POST'):
            from flask import g
            from app import views_registros
            g.usuario = {'usuario': 'IA_COMUM', 'admin': 0}
            g.modulos = {'agenda_leitura'}
            self.assertFalse(views_registros._pode_desfazer())
            views_registros.desfazer.__wrapped__(audit['id'])
            self.assertIsNone(self.db.execute('SELECT desfeito_em FROM auditoria WHERE id=?', (audit['id'],)).fetchone()[0])
            g.usuario = {'usuario': 'IA_GERENTE', 'admin': 0}
            g.modulos = {'gerencia', 'registros'}
            self.assertTrue(views_registros._pode_desfazer())
            # A rota usa get_db da requisição; substitui apenas a conexão neste teste.
            with mock.patch.object(views_registros, 'get_db', return_value=self.db):
                views_registros.desfazer.__wrapped__(audit['id'])
            self.assertIsNotNone(self.db.execute('SELECT desfeito_em FROM auditoria WHERE id=?', (audit['id'],)).fetchone()[0])
        self.assertEqual(self.db.execute('SELECT status FROM agenda_horarios WHERE id=?', (self.hid,)).fetchone()[0], 'AGENDADO')

    def test_alternativa_fora_da_tolerancia(self):
        ia.definir(self.db, 'nucleai_llm_tolerancia_remarcacao', '20')
        r = self._propor('13:00')
        self.assertIn('Não encontrei horário próximo', r['resumo'])
        self.assertIn('11:30', r['resumo'])

    def test_recusa_sem_modulo(self):
        ctx = ferr.contexto(self.db, self.comum, nivel=4)
        r = ferr.chamar(ctx, 'agenda_remarcar', {'data': self.dia, 'hora': '08:00', 'nova_data': self.outro})
        self.assertTrue(r['recusado'])
        self.assertIn('Você não tem acesso à tela Agenda', r['resumo'])
        self.assertIsNone(self.db.execute("SELECT id FROM auditoria WHERE acao LIKE '%Remarcou paciente na agenda%'").fetchone())

    def test_permissao_revalidada_antes_do_sim(self):
        proposta = self._propor()
        self.db.execute("UPDATE usuarios SET modulos='[]' WHERE id=?", (self.uid,))
        self.db.commit()
        resposta = ferr.confirmar(self.ctx, proposta['pendente'])
        self.assertIn('Você não tem acesso à tela Agenda', resposta['texto'])
        self.assertEqual(self.db.execute('SELECT status FROM agenda_horarios WHERE id=?', (self.hid,)).fetchone()[0], 'AGENDADO')


if __name__ == '__main__':
    unittest.main()
