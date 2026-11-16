"""Laudo entregue (botão na mensagem + destaque no mapa) e atualização: aviso de 3 minutos do instalador e tela de espera."""
import os
import time
import unittest
from datetime import date, datetime, timedelta

from app import atualizacao, laudos
from app import db as dbmod
from tests.test_chat_blindagens import Base


class EntregaTestes(Base):
    def _exame(self, paciente='ZELIA ENTREGA'):
        con = dbmod.conectar(self.app.config['DATABASE'])
        try:
            rid = con.execute("INSERT INTO realizacoes (data, paciente, hora_exame, exame, laudo_situacao) VALUES (?,?,?,?,?)",
                              (date.today().isoformat(), paciente, '10:30', 'PET-CT', 'PROCESSANDO')).lastrowid
            con.commit()
            return rid
        finally:
            con.close()

    def _linha(self, rid):
        con = dbmod.conectar(self.app.config['DATABASE'])
        try:
            return dict(con.execute('SELECT * FROM realizacoes WHERE id=?', (rid,)).fetchone())
        finally:
            con.close()

    def test_situacao_entregue_existe_e_registra_quem_entregou(self):
        self.assertEqual([c for c, _ in laudos.SITUACOES][-1], 'ENTREGUE')
        rid = self._exame()
        c = self.cliente()
        self.post(c, '/laudos/%d/situacao' % rid, {'situacao': 'LIBERADO'})
        self.post(c, '/laudos/%d/situacao' % rid, {'situacao': 'ENTREGUE'})
        r = self._linha(rid)
        self.assertEqual(r['laudo_situacao'], 'ENTREGUE')
        self.assertTrue(r['laudo_entregue_em'] and r['laudo_entregue_por'])
        self.assertTrue(r['laudo_liberado_em'])  # a liberação continua registrada (indicador de prazo do ONA)
        pagina = self.texto(c.get('/laudos'))
        self.assertIn('Entregue', pagina)
        self.assertIn('id="laudo-%d"' % rid, pagina)
        # voltar à situação anterior limpa a entrega
        self.post(c, '/laudos/%d/situacao' % rid, {'situacao': 'LIBERADO'})
        self.assertIsNone(self._linha(rid)['laudo_entregue_em'])

    def test_mensagem_de_laudo_tem_botao_e_leva_ao_laudo_entregue(self):
        rid = self._exame('PACIENTE DO BOTAO')
        adm = self.cliente()
        self.criar_usuario('LAUDO_RECEP', ['laudos'])  # recebe o aviso quem já existe na hora da liberação
        self.post(adm, '/laudos/%d/situacao' % rid, {'situacao': 'LIBERADO'})
        rec = self.cliente('LAUDO_RECEP', 'senha123')
        con =dbmod.conectar(self.app.config['DATABASE'])
        try:
            msg = con.execute("SELECT m.id, m.laudo_id, m.de_id, m.para_id FROM chat_mensagens m "
                              "JOIN usuarios u ON u.id=m.para_id WHERE u.usuario='LAUDO_RECEP' AND m.laudo_id=?", (rid,)).fetchone()
        finally:
            con.close()
        self.assertIsNotNone(msg)
        self.assertEqual(msg['laudo_id'], rid)
        carga = self.texto(rec.get('/mensagens?com=%d' % msg['de_id']))
        self.assertRegex(carga, r'"laudo_id":\s*%d' % rid)  # o botão é montado pelo chat.js a partir deste campo
        # o clique: marca como entregue e redireciona ao laudo, com destaque e âncora
        r = self.post(rec, '/laudos/%d/entregar' % rid, {})
        self.assertEqual(r.status_code, 302)
        self.assertIn('destaque=%d' % rid, r.headers['Location'])
        self.assertTrue(r.headers['Location'].endswith('#laudo-%d' % rid))
        self.assertEqual(self._linha(rid)['laudo_situacao'], 'ENTREGUE')
        pagina = self.texto(rec.get(r.headers['Location']))
        self.assertIn('laudo-cartao destaque', pagina)
        # clicar de novo não quebra
        r2 = self.post(rec, '/laudos/%d/entregar' % rid, {})
        self.assertEqual(r2.status_code, 302)
        self.assertEqual(self._linha(rid)['laudo_situacao'], 'ENTREGUE')


class AtualizacaoTestes(Base):
    def setUp(self):
        con = dbmod.conectar(self.app.config['DATABASE'])
        con.execute('DELETE FROM atualizacao_avisos')
        con.commit()
        con.close()

    def test_instalador_dispara_aviso_de_3_minutos_e_nao_duplica(self):
        agora = datetime(2026, 10, 16, 10, 0, 0)
        con = dbmod.conectar(self.app.config['DATABASE'])
        try:
            segundos = atualizacao.iniciar_pelo_instalador(con, agora)
            self.assertTrue(180 <= segundos <= 181)
            n1 = con.execute("SELECT COUNT(*) FROM chat_mensagens WHERE corpo LIKE 'Aviso de atualização%'").fetchone()[0]
            self.assertGreater(n1, 0)
            # um segundo pedido (aviso ainda no prazo) aproveita o mesmo aviso: não manda mensagem repetida
            depois = atualizacao.iniciar_pelo_instalador(con, agora + timedelta(seconds=60))
            self.assertTrue(120 <= depois <= 121)
            n2 = con.execute("SELECT COUNT(*) FROM chat_mensagens WHERE corpo LIKE 'Aviso de atualização%'").fetchone()[0]
            self.assertEqual(n1, n2)
            self.assertEqual(atualizacao.estado_aviso(con, agora + timedelta(seconds=100)), 80)
        finally:
            con.close()

    def test_rota_do_instalador_exige_chave_e_local(self):
        c = self.app.test_client()
        base = {'REMOTE_ADDR': '127.0.0.1'}
        self.assertEqual(c.post('/atualizacao/iniciar', environ_base=base).status_code, 403)
        self.assertEqual(c.post('/atualizacao/iniciar', headers={'X-Chave': 'errada'}, environ_base=base).status_code, 403)
        chave = self.app.config['SECRET_KEY']
        self.assertEqual(c.post('/atualizacao/iniciar', headers={'X-Chave': chave}, environ_base={'REMOTE_ADDR': '192.168.0.9'}).status_code, 403)
        ok = c.post('/atualizacao/iniciar', headers={'X-Chave': chave}, environ_base=base)
        self.assertEqual(ok.status_code, 200)
        self.assertTrue(180 <= int(ok.get_data(as_text=True)) <= 181)
        estado = c.get('/atualizacao/estado').get_json()
        self.assertGreater(estado['aviso'], 0)
        self.assertEqual(estado['atualizando'], 0)

    def test_tela_de_espera_depois_da_atualizacao(self):
        pasta = self.app.config['PASTA_DADOS']
        marca = os.path.join(pasta, atualizacao.MARCA)
        atualizacao.marcar_atualizacao(pasta)
        try:
            # servidor "novo": iniciou depois da marca
            self.app.config['INICIO_SERVIDOR'] = time.time() + 1
            c = self.app.test_client()
            r = c.get('/')
            self.assertEqual(r.status_code, 503)
            texto = r.get_data(as_text=True)
            self.assertIn('atualizando o sistema', texto)
            self.assertIn('aguarde.js', texto)
            self.assertEqual(c.get('/atualizacao/estado').get_json()['atualizando'] > 0, True)
            self.assertEqual(c.get('/static/js/aguarde.js').status_code, 200)  # a animação carrega durante a espera
            # passado 1 minuto, o sistema é liberado e a marca é apagada
            self.app.config['INICIO_SERVIDOR'] = time.time() - atualizacao.ESPERA_S - 5
            self.assertNotEqual(c.get('/login').status_code, 503)
            self.assertFalse(os.path.exists(marca))
        finally:
            if os.path.exists(marca):
                os.remove(marca)

    def test_marca_de_instalacao_cancelada_nao_prende_o_sistema(self):
        pasta = self.app.config['PASTA_DADOS']
        atualizacao.marcar_atualizacao(pasta)
        # servidor que já estava no ar quando a marca foi gravada (instalação interrompida): ignora e apaga
        self.assertEqual(atualizacao.espera_restante(pasta, time.time() - 600), 0)
        self.assertFalse(os.path.exists(os.path.join(pasta, atualizacao.MARCA)))

    def test_paginas_logadas_trazem_a_contagem_e_a_animacao(self):
        pagina = self.texto(self.cliente().get('/', headers={'Referer': 'http://localhost/'}))
        self.assertIn('js/atualizacao.js', pagina)
        self.assertIn('js/aguarde.js', pagina)


if __name__ == '__main__':
    unittest.main()
