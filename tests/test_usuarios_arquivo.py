"""Arquivar perfil, desarquivar e desligar funcionário (sem apagar nada)."""
from app import db as dbmod
from app import novidades
from tests.test_chat_blindagens import Base


class Arquivo(Base):
    def _uid(self, nome):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            return con.execute("SELECT id FROM usuarios WHERE usuario=?", (nome,)).fetchone()["id"]
        finally:
            con.close()

    def _linha(self, sql, args=()):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            return con.execute(sql, args).fetchone()
        finally:
            con.close()

    def test_arquivar_tira_da_lista_bloqueia_e_nao_apaga(self):
        self.criar_usuario("SAIU1", ["agenda"])
        c = self.cliente()
        self.assertIn("<strong>SAIU1</strong>", self.texto(c.get("/usuarios")))
        self.post(c, "/usuarios/%d/arquivar" % self._uid("SAIU1"))
        self.assertNotIn("<strong>SAIU1</strong>", self.texto(c.get("/usuarios")))
        self.assertIn("<strong>SAIU1</strong>", self.texto(c.get("/usuarios?arquivados=1")))
        r = self._linha("SELECT ativo, arquivado_em FROM usuarios WHERE usuario='SAIU1'")
        self.assertEqual(r["ativo"], 0)
        self.assertTrue(r["arquivado_em"])

    def test_desarquivar_volta_para_a_lista(self):
        self.criar_usuario("VOLTA1", ["agenda"])
        c = self.cliente()
        uid = self._uid("VOLTA1")
        self.post(c, "/usuarios/%d/arquivar" % uid)
        self.post(c, "/usuarios/%d/desarquivar" % uid)
        self.assertIn("<strong>VOLTA1</strong>", self.texto(c.get("/usuarios")))

    def test_nao_arquiva_a_si_mesmo(self):
        c = self.cliente()
        self.post(c, "/usuarios/%d/arquivar" % self._uid("ADMIN"))
        self.assertIn("<strong>ADMIN</strong>", self.texto(c.get("/usuarios")))

    def test_desligar_funcionario_encerra_o_ponto_e_arquiva_o_perfil(self):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            con.execute("INSERT INTO bh_employees (clock_id, name, active, start_date, opening_balance_date, created_at, updated_at) "
                        "VALUES ('777','FUNC TESTE',1,'2025-01-01','2025-01-01','2025-01-01','2025-01-01')")
            emp = con.execute("SELECT id FROM bh_employees WHERE clock_id='777'").fetchone()["id"]
            con.commit()
        finally:
            con.close()
        self.criar_usuario("FUNC1", ["bh_portal"])
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            con.execute("UPDATE usuarios SET bh_funcionario_id=? WHERE usuario='FUNC1'", (emp,))
            con.commit()
        finally:
            con.close()
        c = self.cliente()
        self.post(c, "/usuarios/%d/desligar" % self._uid("FUNC1"))
        e = self._linha("SELECT active, end_date, archived_at FROM bh_employees WHERE id=?", (emp,))
        self.assertEqual(e["active"], 0)
        self.assertTrue(e["end_date"])
        self.assertTrue(e["archived_at"])
        self.assertEqual(self._linha("SELECT arquivado_em FROM usuarios WHERE usuario='FUNC1'")["arquivado_em"] is not None, True)
        self.assertNotIn("FUNC TESTE", self.texto(c.get("/banco-horas/funcionarios")))
        self.assertIn("FUNC TESTE", self.texto(c.get("/banco-horas/funcionarios?arquivados=1")))

    def test_log_da_versao_traz_as_novidades(self):
        titulos = " ".join(i[1] for v in novidades.VERSOES if v["versao"] == "1.5.0" for i in v["itens"])
        for trecho in ("Tutorial animado", "Prazo de entrega", "Arquivar perfil", "Laudos entregues", "Atendimentos do dia",
                       "Mensagens do WhatsApp", "acesso por usuário"):
            self.assertIn(trecho, titulos)
