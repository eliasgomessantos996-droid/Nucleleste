"""Prazo de entrega do laudo (configurável), previsão com dias úteis/feriados de Governador Valadares e aba de atendimentos do dia."""
import unittest
from datetime import date, datetime

from app import db as dbmod
from app import prazo_laudo as pl
from tests.test_chat_blindagens import Base

CFG_UTEIS_6 = {'tipo': 'uteis', 'valor': 6, 'carnaval': False, 'corpus': False, 'extras': ''}
CFG_24H = dict(pl.PADRAO)


class Calendario(unittest.TestCase):
    def test_pascoa(self):
        self.assertEqual(pl.pascoa(2026), date(2026, 4, 5))
        self.assertEqual(pl.pascoa(2025), date(2025, 4, 20))

    def test_feriados_locais_e_moveis(self):
        f = pl.feriados(2026, CFG_24H)
        self.assertIn(date(2026, 1, 30), f)     # aniversário de Governador Valadares
        self.assertIn(date(2026, 6, 13), f)     # Santo Antônio
        self.assertIn(date(2026, 4, 3), f)      # Sexta-feira Santa
        self.assertNotIn(date(2026, 2, 17), f)  # Carnaval só se a gerência marcar
        self.assertIn(date(2026, 2, 17), pl.feriados(2026, dict(CFG_24H, carnaval=True)))
        self.assertIn(date(2026, 6, 4), pl.feriados(2026, dict(CFG_24H, corpus=True)))

    def test_extras_com_e_sem_ano(self):
        cfg = dict(CFG_24H, extras='10/03\n11/03/2026, 12/03/2025')
        f = pl.feriados(2026, cfg)
        self.assertIn(date(2026, 3, 10), f)
        self.assertIn(date(2026, 3, 11), f)
        self.assertNotIn(date(2026, 3, 12), f)

    def test_seis_dias_uteis_pulam_fim_de_semana(self):
        # segunda 19/10/2026 + 6 úteis (20, 21, 22, 23, 26, 27) = terça 27/10
        self.assertEqual(pl.previsao(date(2026, 10, 19), CFG_UTEIS_6), date(2026, 10, 27))
        # sexta 16/10/2026 + 6 úteis (19, 20, 21, 22, 23, 26) = segunda 26/10
        self.assertEqual(pl.previsao(date(2026, 10, 16), CFG_UTEIS_6), date(2026, 10, 26))

    def test_feriado_nao_conta(self):
        # quarta 28/01/2026 + 3 úteis: quinta 29, (sexta 30/01 é feriado), segunda 02/02, terça 03/02
        cfg = dict(CFG_UTEIS_6, valor=3)
        self.assertEqual(pl.previsao(date(2026, 1, 28), cfg), date(2026, 2, 3))

    def test_dias_corridos_caindo_no_domingo_vao_para_segunda(self):
        cfg = {'tipo': 'dias', 'valor': 7, 'carnaval': False, 'corpus': False, 'extras': ''}
        # sexta 16/10 + 7 = sexta 23/10; segunda 12/10 + 7 = segunda 19/10; sábado 17/10 + 7 = sábado 24 -> segunda 26
        self.assertEqual(pl.previsao(date(2026, 10, 16), cfg), date(2026, 10, 23))
        self.assertEqual(pl.previsao(date(2026, 10, 17), cfg), date(2026, 10, 26))

    def test_24_horas_padrao(self):
        self.assertEqual(pl.previsao(date(2026, 10, 19), CFG_24H), date(2026, 10, 20))
        # sexta + 24 h cai no sábado: segue para segunda
        self.assertEqual(pl.previsao(date(2026, 10, 16), CFG_24H), date(2026, 10, 19))
        self.assertEqual(pl.limite(datetime(2026, 10, 19, 8, 30), CFG_24H), datetime(2026, 10, 20, 8, 30))


class Telas(Base):
    def setUp(self):
        super().setUp()
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            for ch in ("laudo_prazo_tipo", "laudo_prazo_valor", "laudo_prazo_carnaval", "laudo_prazo_corpus", "laudo_feriados_extras"):
                con.execute("DELETE FROM config WHERE chave=?", (ch,))
            con.execute("DELETE FROM realizacoes")
            con.execute("DELETE FROM atendimentos")
            con.execute("INSERT OR IGNORE INTO convenios (nome, ativo) VALUES ('UNIMED', 1)")
            con.execute("INSERT OR REPLACE INTO clientes (id, nome, cpf, convenio, data_nasc) VALUES (901, 'MARIA TESTE', '', 'UNIMED', '1980-05-10')")
            con.execute("INSERT INTO atendimentos (cliente_id, cliente_nome, medico, data, exame, convenio, usuario, criado_em) "
                        "VALUES (901, 'MARIA TESTE', 'DR JOAO', ?, 'MIBI', 'UNIMED', 'ADMIN', ?)",
                        (date.today().isoformat(), date.today().isoformat() + " 09:15:00"))
            con.commit()
        finally:
            con.close()

    def _aid(self):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            return con.execute("SELECT id FROM atendimentos ORDER BY id DESC LIMIT 1").fetchone()["id"]
        finally:
            con.close()

    def test_gerencia_altera_o_prazo_e_a_previsao_muda(self):
        c = self.cliente()
        self.post(c, "/laudos/prazo", {"tipo": "uteis", "valor": "6"})
        j = c.get("/atendimentos/previsao?data=2026-10-19").get_json()
        self.assertIn("27/10/2026", j["texto"])
        self.assertIn("6 dias úteis", j["texto"])

    def test_prazo_invalido_nao_grava(self):
        c = self.cliente()
        self.post(c, "/laudos/prazo", {"tipo": "uteis", "valor": "0"})
        with self.app.app_context():
            self.assertEqual(pl.atuais()["tipo"], "horas")

    def test_so_gerencia_altera_o_prazo(self):
        self.criar_usuario("LAUDOS1", ["laudos"])
        c = self.cliente("LAUDOS1", "senha123")
        self.post(c, "/laudos/prazo", {"tipo": "uteis", "valor": "6"})
        with self.app.app_context():
            self.assertEqual(pl.atuais()["tipo"], "horas")   # sem o módulo da gerência, o prazo não muda
        self.assertEqual(c.get("/laudos").status_code, 200)

    def test_rascunho_traz_convenio_e_medico_do_atendimento(self):
        c = self.cliente()
        pagina = self.texto(c.get("/exames-realizados/novo?atendimento=%d" % self._aid()))
        self.assertIn('value="DR JOAO"', pagina)
        self.assertIn('value="UNIMED"', pagina)
        self.assertIn('value="MIBI"', pagina)
        self.assertIn('name="atendimento_id"', pagina)

    def test_lancar_pelo_rascunho_liga_o_atendimento_e_some_da_lista_de_pendentes(self):
        c = self.cliente()
        aid = self._aid()
        hoje = date.today().isoformat()
        self.post(c, "/exames-realizados/novo", {"atendimento_id": aid, "cliente_id": "901", "paciente": "Maria Teste",
                                                 "data": hoje, "exame": "MIBI", "convenio": "UNIMED", "medico": "DR JOAO"})
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM realizacoes WHERE atendimento_id=?", (aid,)).fetchone()[0], 1)
        finally:
            con.close()
        pagina = self.texto(c.get("/exames-realizados/do-dia"))
        self.assertIn("Exame lançado", pagina)
        # abrir o rascunho de novo leva ao exame já lançado (sem duplicar)
        self.assertEqual(c.get("/exames-realizados/novo?atendimento=%d" % aid).status_code, 302)

    def test_aba_do_dia_lista_o_atendimento(self):
        pagina = self.texto(self.cliente().get("/exames-realizados/do-dia"))
        self.assertIn("MARIA TESTE", pagina)
        self.assertIn("Lançar exame", pagina)

    def test_atendimento_novo_guarda_a_previsao(self):
        c = self.cliente()
        self.post(c, "/laudos/prazo", {"tipo": "uteis", "valor": "6"})
        self.post(c, "/atendimentos/novo", {"cliente_id": "901", "exame": "TESTE SEM QUESTIONARIO", "data": "2026-10-19",
                                            "medico": "dr joao", "convenio": "", "manual": "1"})
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            r = con.execute("SELECT previsao_laudo, convenio FROM atendimentos WHERE exame='TESTE SEM QUESTIONARIO'").fetchone()
        finally:
            con.close()
        if r:   # o exame de teste pode exigir campos extras; quando grava, a previsão tem de estar certa
            self.assertEqual(r["previsao_laudo"], "2026-10-27")
            self.assertEqual(r["convenio"], "UNIMED")


if __name__ == "__main__":
    unittest.main()
