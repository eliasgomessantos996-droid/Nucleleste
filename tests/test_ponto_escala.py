"""Vínculo no portal, carga da escala e ocorrências de ponto com banco isolado."""
import json
import os
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from flask import render_template

from app import create_app
from app import db as dbmod
from app.bh import core, ocorrencias, planning, portal
from tests.test_bh_core import REGULAR, workbook


class PontoEscala(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        ambiente = patch.dict(os.environ, {'NUCLELESTE_DADOS': self.pasta.name})
        ambiente.start()
        self.addCleanup(ambiente.stop)
        self.app = create_app(os.path.join(self.pasta.name, 't.db'))
        self.app.config['TESTING'] = True
        self.conn = dbmod.conectar(self.app.config['DATABASE'])
        self.addCleanup(self.conn.close)
        self.funcionario = self.novo()
        self.eid = self.funcionario['id']

    def novo(self, numero='1', nome='Maria Teste', **extra):
        dados = dict(clock_id=numero, name=nome, start_date='2026-09-10', opening_balance_date='2026-09-15')
        dados.update(extra)
        funcionario = core.save_employee(self.conn, dados, 'GESTAO')
        core.save_schedule(self.conn, funcionario['id'], dict(
            effective_date=dados['start_date'], weekdays={str(i): 480 if i < 5 else 0 for i in range(7)},
            required_break_minutes=60, two_punch_policy='review', reason='Jornada contratual'), 'GESTAO')
        return core.get_employee(self.conn, funcionario['id'])

    def conta(self, nome='MARIA', eid=None, modulos=None):
        portal.create_account(self.conn, eid or self.eid, nome, 'senha123', 'senha123', 'GESTAO')
        with self.conn:
            self.conn.execute('UPDATE usuarios SET trocar_senha=0,modulos=? WHERE usuario=?',
                              (json.dumps(modulos or ['bh_portal']), nome))
        return self.cliente(nome, 'senha123')

    def cliente(self, usuario='ADMIN', senha='admin'):
        cliente = self.app.test_client()
        cliente.get('/login')
        with cliente.session_transaction() as sessao:
            token = sessao['csrf']
        resposta = cliente.post('/login', data={'usuario': usuario, 'senha': senha, '_csrf': token})
        self.assertEqual(resposta.status_code, 302)
        cliente.get('/login')   # a sessão nova só recebe o token CSRF na próxima requisição
        return cliente

    def post(self, cliente, url, dados):
        with cliente.session_transaction() as sessao:
            token = sessao['csrf']
        return cliente.post(url, data={**dados, '_csrf': token}, headers={'Accept': 'application/json'})

    def importar(self):
        core.import_xls(self.conn, workbook([('1', 'Nome do relógio', {i: REGULAR for i in range(1, 31)})]),
                        'ponto.xls', 'GESTAO')

    def ocorrencia(self, dia='2026-09-16', horarios='08:00 12:00 13:00 17:00'):
        return ocorrencias.criar(self.conn, self.eid, dia, 'esquecimento', horarios, 'Esqueci a batida.', 'MARIA')

    def test_portal_filtra_no_servidor_sem_ocultar_anterior_ao_saldo_inicial(self):
        with self.conn:
            self.conn.execute("UPDATE bh_employees SET end_date='2026-09-20' WHERE id=?", (self.eid,))
        self.importar()
        gerencia = core.monthly_report(self.conn, self.eid, '2026-09')
        relatorio = portal.relatorio_funcionario(self.conn, self.eid, '2026-09')
        self.assertEqual(len(gerencia['rows']), 30)
        self.assertEqual([r['date'] for r in relatorio['rows']], [f'2026-09-{d:02}' for d in range(10, 21)])
        self.assertEqual(relatorio['rows'][0]['status'], 'before_balance')
        self.assertEqual(relatorio['final_balance'], gerencia['final_balance'])
        self.assertEqual(portal.relatorio_funcionario(self.conn, self.eid, '2026-08')['rows'], [])
        cliente = self.conta()
        with patch('app.views_bh.render_template', wraps=render_template) as tela:
            resposta = cliente.get('/banco-horas/minha-area?month=2026-09')
            self.assertEqual(resposta.status_code, 200)
            self.assertEqual(tela.call_args.kwargs['report']['rows'], relatorio['rows'])
        self.assertNotIn('Fora do vínculo', resposta.get_data(as_text=True))
        self.assertIn('Anterior ao saldo inicial', resposta.get_data(as_text=True))

    def test_extrato_relatorio_e_historico_respeitam_identidade(self):
        outro = self.novo('2', 'Outra Pessoa')
        cliente = self.conta(modulos=['bh_portal', 'bh_consulta'])
        for final in ('extrato', 'relatorio'):
            with patch('app.views_bh.render_template', wraps=render_template) as tela:
                resposta = cliente.get(f'/banco-horas/funcionarios/{self.eid}/{final}?month=2026-09')
                self.assertEqual(resposta.status_code, 200)
                self.assertTrue(all(r['date'] >= '2026-09-10' for r in tela.call_args.kwargs['report']['rows']))
            self.assertEqual(cliente.get(f"/banco-horas/funcionarios/{outro['id']}/{final}").status_code, 403)
        self.assertEqual(cliente.get('/banco-horas/historico').status_code, 403)
        gerencia = self.cliente()
        self.assertIn('Fora do vínculo', gerencia.get(
            f'/banco-horas/funcionarios/{self.eid}/extrato?month=2026-09').get_data(as_text=True))

    def test_pdf_historico_do_funcionario_regenera_copia_filtrada(self):
        relatorio = core.monthly_report(self.conn, self.eid, '2026-09')
        with self.conn:
            cursor = self.conn.execute(
                'INSERT INTO bh_report_snapshots (employee_id,month,version,issued_at,content_hash,snapshot_json,pdf_bytes) '
                'VALUES (?,?,?,?,?,?,?)', (self.eid, '2026-09', 1, core._now(), 'teste',
                                          json.dumps({'report': relatorio, 'company_name': 'Clínica'}), b'original preservado'))
        url = f'/banco-horas/relatorios/{cursor.lastrowid}/baixar'
        cliente = self.conta(modulos=['bh_portal', 'bh_consulta'])
        with patch('app.views_bh.render_report', return_value=b'%PDF-copia') as gerar:
            self.assertEqual(cliente.get(url).data, b'%PDF-copia')
            self.assertTrue(all(r['status'] != 'not_employed' for r in gerar.call_args.args[0]['rows']))
        self.assertEqual(self.cliente().get(url).data, b'original preservado')
        outro = self.novo('2', 'Joana Teste')
        outra_conta = self.conta('JOANA', outro['id'], ['bh_portal', 'bh_consulta'])
        self.assertEqual(outra_conta.get(url).status_code, 403)

    def test_escala_calcula_carga_descontando_intervalo_e_ausencias(self):
        planning.save_days(self.conn, self.eid, '2026-09-16', '2026-09-16', 'trabalho',
                           '07:30', '16:45', 75, 'Ajuste de horário', 'GESTAO')
        planning.save_days(self.conn, self.eid, '2026-09-17', '2026-09-17', 'ferias',
                           '', '', 0, 'Férias', 'GESTAO')
        relatorio = planning.monthly_roster(self.conn, '2026-09')
        linhas = {r['date']: r for r in relatorio['staff'][0]['rows']}
        self.assertEqual((linhas['2026-09-15']['start_time'], linhas['2026-09-15']['end_time']), ('08:00', '17:00'))
        self.assertEqual(linhas['2026-09-15']['work_minutes'], 480)
        self.assertEqual(linhas['2026-09-16']['work_minutes'], 480)
        self.assertEqual(linhas['2026-09-16']['break_minutes'], 75)
        self.assertEqual(linhas['2026-09-17']['work_minutes'], 0)
        self.assertEqual(linhas['2026-09-09']['kind'], 'fora')
        self.assertEqual(relatorio['staff'][0]['planned_minutes'], sum(r['work_minutes'] or 0 for r in linhas.values()))
        pagina = self.cliente().get('/banco-horas/escala?month=2026-09')
        self.assertEqual(pagina.status_code, 200)
        for texto in ('07:30', '16:45', '01:15', 'Carga diária', 'Carga do mês'):
            self.assertIn(texto, pagina.get_data(as_text=True))

    def test_pdf_escala_inclui_logo_e_carga_diaria(self):
        from reportlab.pdfgen.canvas import Canvas
        from reportlab.platypus import Table
        tabelas, imagens = [], []
        desenhar_original = Canvas.drawImage

        def tabela(dados, *args, **kwargs):
            tabelas.append(dados)
            return Table(dados, *args, **kwargs)

        def imagem(canvas, caminho, *args, **kwargs):
            imagens.append(caminho)
            return desenhar_original(canvas, caminho, *args, **kwargs)

        with patch('reportlab.platypus.Table', side_effect=tabela), patch.object(Canvas, 'drawImage', imagem):
            pdf = planning.render_roster(planning.monthly_roster(self.conn, '2026-09'), 'Clínica Nucleleste')
        self.assertTrue(pdf.startswith(b'%PDF-'))
        self.assertIn(b'/Subtype /Image', pdf)
        self.assertTrue(any(Path(p).name == 'verde-claro.png' for p in imagens))
        self.assertTrue(any(c.text == 'Carga diária' for c in tabelas[1][0]))
        self.assertTrue(any(linha[3:7] == ['08:00', '17:00', '01:00', '08:00'] for linha in tabelas[1][1:]))

    def test_ocorrencia_criada_pelo_portal_ignora_id_informado(self):
        outro = self.novo('2', 'Outra Pessoa')
        cliente = self.conta()
        resposta = self.post(cliente, '/banco-horas/minha-area/ocorrencia', {
            'employee_id': outro['id'], 'data': '2026-09-16', 'tipo': 'esquecimento',
            'horarios': '08:00 12:00 13:00 17:00', 'observacao': 'Esqueci a batida.'})
        self.assertEqual(resposta.status_code, 302)
        itens = ocorrencias.listar(self.conn, self.eid)
        self.assertEqual(len(itens), 1)
        self.assertEqual(itens[0]['status'], 'PENDENTE')
        self.assertEqual(ocorrencias.listar(self.conn, outro['id']), [])
        self.assertIn('Esqueci a batida.', cliente.get('/banco-horas/minha-area?month=2026-09').get_data(as_text=True))
        gerencia = self.cliente()
        for url in ('/banco-horas?month=2026-09', f'/banco-horas/funcionarios/{self.eid}/extrato?month=2026-09'):
            self.assertIn('Ocorrências de ponto pendentes (1)', gerencia.get(url).get_data(as_text=True))
        acoes = [r['action'] for r in core.audit_entries(self.conn, self.eid)]
        self.assertIn('ocorrencia_criada', acoes)

    def test_pendencia_nao_concede_credito_e_bloqueia_emissao(self):
        self.importar()
        core.correct_day(self.conn, self.eid, '2026-09-16', ['08:00', '12:00', '13:00', '18:00'],
                         'normal', 'Conferência anterior', 'GESTAO')
        anterior = core.monthly_report(self.conn, self.eid, '2026-09')
        self.assertTrue(anterior['complete'])
        self.ocorrencia()
        relatorio = core.monthly_report(self.conn, self.eid, '2026-09')
        linha = next(r for r in relatorio['rows'] if r['date'] == '2026-09-16')
        self.assertTrue(linha['pending'])
        self.assertIsNone(linha['delta_minutes'])
        self.assertFalse(relatorio['complete'])
        self.assertEqual(relatorio['pending_occurrence_count'], 1)
        self.assertEqual(relatorio['movement'], anterior['movement'] - 60)
        gerencia = self.cliente()
        resposta = self.post(gerencia, f'/banco-horas/funcionarios/{self.eid}/relatorio/pdf', {'month': '2026-09'})
        self.assertEqual(resposta.status_code, 400)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM bh_report_snapshots').fetchone()[0], 0)

    def test_pendencia_anterior_ao_saldo_inicial_continua_visivel_e_impede_fechamento(self):
        self.importar()
        self.ocorrencia('2026-09-12')
        setembro = portal.relatorio_funcionario(self.conn, self.eid, '2026-09')
        linha = next(r for r in setembro['rows'] if r['date'] == '2026-09-12')
        self.assertTrue(linha['pending'])
        self.assertFalse(setembro['complete'])
        outubro = core.monthly_report(self.conn, self.eid, '2026-10')
        self.assertEqual(outubro['previous_pending_count'], 1)
        self.assertEqual(outubro['pending_occurrence_count'], 1)
        self.assertFalse(outubro['complete'])

    def test_gerencia_aprova_corrige_recusa_e_funcionario_acompanha(self):
        cliente, gerencia = self.conta(), self.cliente()
        for dia, status in [('16', 'APROVADA'), ('17', 'CORRIGIDA'), ('18', 'RECUSADA')]:
            with self.subTest(status=status):
                oid = self.ocorrencia('2026-09-' + dia)
                resposta = self.post(gerencia, f'/banco-horas/ocorrencias/{oid}/tratar', {
                    'status': status, 'horarios': '', 'classificacao': 'abono',
                    'parecer': 'Conferido com o funcionário.', 'month': '2026-09'})
                self.assertEqual(resposta.status_code, 302, resposta.get_data(as_text=True))
                registro = self.conn.execute('SELECT * FROM bh_ocorrencias WHERE id=?', (oid,)).fetchone()
                self.assertEqual(registro['status'], status)
                self.assertEqual(registro['tratado_por'], 'ADMIN')
                correcao = self.conn.execute('SELECT * FROM bh_corrections WHERE date=?', ('2026-09-' + dia,)).fetchone()
                if status == 'APROVADA':
                    self.assertEqual(json.loads(correcao['punches_json']), REGULAR)
                elif status == 'CORRIGIDA':
                    self.assertEqual(correcao['kind'], 'abono')
                else:
                    self.assertIsNone(correcao)
        pagina = cliente.get('/banco-horas/minha-area?month=2026-09').get_data(as_text=True)
        for texto in ('APROVADA', 'CORRIGIDA', 'RECUSADA', 'Conferido com o funcionário.'):
            self.assertIn(texto, pagina)
        self.assertEqual(ocorrencias.listar(self.conn, pendentes=True), [])
        self.assertEqual(sum(r['action'] == 'ocorrencia_tratada' for r in core.audit_entries(self.conn)), 3)

    def test_tratamento_invalido_e_repetido_nao_deixa_mudancas_parciais(self):
        oid = self.ocorrencia(horarios='08:00')
        auditorias = self.conn.execute('SELECT COUNT(*) FROM bh_audit_log').fetchone()[0]
        for status, horarios, classe in [('APROVADA', '', 'normal'), ('CORRIGIDA', '25:00', 'normal'),
                                        ('CORRIGIDA', '', 'invalida')]:
            with self.subTest(status=status, classe=classe), self.assertRaises(ValueError):
                ocorrencias.tratar(self.conn, oid, status, horarios, classe, 'Conferência', 'GESTAO')
            self.assertEqual(ocorrencias.listar(self.conn)[0]['status'], 'PENDENTE')
            self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM bh_audit_log').fetchone()[0], auditorias)
            self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM bh_corrections').fetchone()[0], 0)
        ocorrencias.tratar(self.conn, oid, 'CORRIGIDA', '08:00 12:00 13:00 17:00', 'normal', 'Conferência', 'GESTAO')
        with self.assertRaises(ValueError):
            ocorrencias.tratar(self.conn, oid, 'RECUSADA', '', 'normal', 'Segunda decisão', 'GESTAO')
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM bh_corrections').fetchone()[0], 1)
        self.assertEqual(ocorrencias.listar(self.conn)[0]['status'], 'CORRIGIDA')

    def test_validacoes_da_ocorrencia(self):
        for dia, tipo, horarios, nota in [
                ('2026-09-09', 'outro', '', 'Fora do vínculo'),
                ((date.today() + timedelta(days=1)).isoformat(), 'outro', '', 'Futuro'),
                ('2026-09-16', 'invalido', '', 'Tipo inválido'),
                ('2026-09-16', 'outro', '08:00 07:00', 'Fora de ordem'),
                ('2026-09-16', 'outro', '99:99', 'Hora inválida'),
                ('2026-09-16', 'outro', '', '')]:
            with self.subTest(dia=dia, tipo=tipo, horarios=horarios, nota=nota), self.assertRaises(ValueError):
                ocorrencias.criar(self.conn, self.eid, dia, tipo, horarios, nota, 'MARIA')
        self.assertEqual(ocorrencias.listar(self.conn), [])

    def test_post_exige_csrf_e_permissoes(self):
        cliente, gerencia = self.conta(), self.cliente()
        self.assertEqual(cliente.post('/banco-horas/minha-area/ocorrencia', data={}).status_code, 400)
        oid = self.ocorrencia()
        url = f'/banco-horas/ocorrencias/{oid}/tratar'
        self.assertEqual(gerencia.post(url, data={'status': 'RECUSADA'}).status_code, 400)
        self.assertEqual(self.post(cliente, url, {'status': 'RECUSADA', 'parecer': 'Sem permissão'}).status_code, 302)
        self.assertEqual(ocorrencias.listar(self.conn)[0]['status'], 'PENDENTE')
        self.assertEqual(self.post(gerencia, '/banco-horas/minha-area/ocorrencia', {}).status_code, 403)

    def test_esquema_existente_preserva_ocorrencias_na_reinicializacao(self):
        oid = self.ocorrencia()
        outra_app = create_app(self.app.config['DATABASE'])
        self.assertEqual(outra_app.config['DATABASE'], self.app.config['DATABASE'])
        self.assertEqual(ocorrencias.listar(self.conn)[0]['id'], oid)
        self.assertEqual(ocorrencias.listar(self.conn)[0]['status'], 'PENDENTE')


if __name__ == '__main__':
    unittest.main()
