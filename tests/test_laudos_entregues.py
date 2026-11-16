"""Limpar entregues do mapa, página Laudos entregues e retificação (indicador da ONA)."""
from datetime import date, datetime, timedelta

from app import db as dbmod
from app import ona
from tests.test_chat_blindagens import Base


class Entregues(Base):
    def setUp(self):
        super().setUp()
        hoje = date.today().isoformat()
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            con.execute("DELETE FROM realizacoes")
            for nome, sit in (("PAC ENTREGUE", "ENTREGUE"), ("PAC LIBERADO", "LIBERADO")):
                con.execute("INSERT INTO realizacoes (data, paciente, exame, hora_exame, laudo_situacao, laudo_liberado_em, laudo_atualizado_em) "
                            "VALUES (?,?,?,?,?,?,?)", (hoje, nome, "MIBI", "08:00", sit, hoje + " 10:00:00", hoje + " 10:00:00"))
            con.commit()
        finally:
            con.close()

    def _id(self, nome):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            return con.execute("SELECT id FROM realizacoes WHERE paciente=?", (nome,)).fetchone()["id"]
        finally:
            con.close()

    def test_limpar_tira_do_mapa_e_leva_para_entregues(self):
        c = self.cliente()
        hoje = date.today().isoformat()
        self.assertIn("PAC ENTREGUE", self.texto(c.get("/laudos")))
        self.post(c, "/laudos/limpar", {"de": hoje, "ate": hoje})
        mapa = self.texto(c.get("/laudos"))
        self.assertNotIn("PAC ENTREGUE", mapa)
        self.assertIn("PAC LIBERADO", mapa)          # só os entregues saem
        self.assertIn("PAC ENTREGUE", self.texto(c.get("/laudos/entregues")))

    def test_voltar_de_entregue_traz_de_volta_ao_mapa(self):
        c = self.cliente()
        hoje = date.today().isoformat()
        self.post(c, "/laudos/limpar", {"de": hoje, "ate": hoje})
        self.post(c, "/laudos/%d/situacao" % self._id("PAC ENTREGUE"), {"situacao": "LIBERADO"})
        self.assertIn("PAC ENTREGUE", self.texto(c.get("/laudos")))

    def test_retificar_entra_no_indicador_da_ona(self):
        c = self.cliente()
        hoje = date.today()
        self.post(c, "/laudos/%d/retificar" % self._id("PAC ENTREGUE"), {"motivo": "Erro de lateralidade"})
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            res = ona.indicadores(con, hoje - timedelta(days=1), hoje)
        finally:
            con.close()
        linha = next(i for i in res["indicadores"] if i["nome"] == "Laudos retificados")
        self.assertEqual((linha["numerador"], linha["denominador"]), (1, 2))
        self.assertIn("Erro de lateralidade", self.texto(c.get("/laudos/entregues")))
        self.post(c, "/laudos/%d/retificar" % self._id("PAC ENTREGUE"), {"desfazer": "1"})
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            res = ona.indicadores(con, hoje - timedelta(days=1), hoje)
        finally:
            con.close()
        self.assertEqual(next(i for i in res["indicadores"] if i["nome"] == "Laudos retificados")["numerador"], 0)

    def test_so_laudo_entregue_pode_ser_retificado(self):
        c = self.cliente()
        self.post(c, "/laudos/%d/retificar" % self._id("PAC LIBERADO"), {"motivo": "x"})
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            self.assertIsNone(con.execute("SELECT laudo_retificado_em FROM realizacoes WHERE paciente='PAC LIBERADO'").fetchone()[0])
        finally:
            con.close()

    def test_so_gerencia_acessa_entregues_e_botoes(self):
        self.criar_usuario("LAUDOS2", ["laudos"])
        c = self.cliente("LAUDOS2", "senha123")
        self.assertEqual(c.get("/laudos/entregues").status_code, 302)
        self.post(c, "/laudos/limpar", {})
        self.assertIn("PAC ENTREGUE", self.texto(c.get("/laudos")))
        self.assertNotIn("Limpar entregues", self.texto(c.get("/laudos")))

    def test_botoes_aparecem_para_a_gerencia(self):
        pagina = self.texto(self.cliente().get("/laudos"))
        self.assertIn("Limpar entregues do período", pagina)
        self.assertIn("Laudos entregues", pagina)
        self.assertIn("Retificar laudo", pagina)
