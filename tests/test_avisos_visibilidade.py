"""AVISOS DO SISTEMA: funcionários veem só os avisos de atualização; vencimentos e caixa são só da gerência."""
import unittest

from app import atualizacao, chat
from app import db as dbmod
from tests.test_chat_blindagens import Base


class VisibilidadeAvisos(Base):
    def setUp(self):
        self.criar_usuario("AV_FUNC", ["atendimentos"])
        self.criar_usuario("AV_GER", ["gerencia"])
        con = dbmod.conectar(self.app.config["DATABASE"])
        self.sistema = con.execute("SELECT id FROM usuarios WHERE sistema=1").fetchone()["id"]
        self.func = con.execute("SELECT id FROM usuarios WHERE usuario='AV_FUNC'").fetchone()["id"]
        self.ger = con.execute("SELECT id FROM usuarios WHERE usuario='AV_GER'").fetchone()["id"]
        con.execute("DELETE FROM chat_mensagens WHERE de_id=?", (self.sistema,))
        for para in (self.func, self.ger):  # aviso de vencimento: chega à gerência e aos funcionários, mas só a gerência vê
            con.execute("INSERT INTO chat_mensagens (de_id, para_id, corpo, criado_em) VALUES (?,?,?,?)",
                        (self.sistema, para, "Vencimento: a conta X vence amanhã.", "2026-10-16 08:00:00"))
        con.commit()
        con.close()
        con = dbmod.conectar(self.app.config["DATABASE"])
        atualizacao.disparar(con, "ADMIN", 10)  # aviso de atualização (tipo ATUALIZACAO)
        con.close()

    def test_funcionario_ve_so_o_aviso_de_atualizacao(self):
        c = self.cliente("AV_FUNC", "senha123")
        lista = self.texto(c.get("/mensagens"))
        self.assertIn("AVISOS DO SISTEMA", lista)  # o contato aparece para todos
        conversa = self.texto(c.get("/mensagens?com=%d" % self.sistema))
        self.assertIn("Aviso de atualização", conversa)
        self.assertNotIn("Vencimento: a conta X", conversa)

    def test_contador_e_toasts_do_funcionario_ignoram_vencimentos(self):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            self.assertEqual(chat.nao_lidas_total(con, self.func), 1)
            novas = chat.novas_para(con, self.func, 0)
            self.assertTrue(all("Vencimento" not in n["previa"] for n in novas))
            self.assertTrue(any("atualização" in n["previa"] for n in novas))
        finally:
            con.close()

    def test_gerencia_ve_os_vencimentos(self):
        c = self.cliente("AV_GER", "senha123")
        conversa = self.texto(c.get("/mensagens?com=%d" % self.sistema))
        self.assertIn("Vencimento: a conta X", conversa)
        self.assertIn("Aviso de atualização", conversa)

    def test_funcionario_nao_consegue_responder_ao_sistema(self):
        c = self.cliente("AV_FUNC", "senha123")
        r = self.post(c, "/mensagens/enviar", {"para": self.sistema, "corpo": "oi"})
        self.assertNotEqual(r.status_code, 500)
        con = dbmod.conectar(self.app.config["DATABASE"])
        n = con.execute("SELECT COUNT(*) FROM chat_mensagens WHERE para_id=? AND de_id=?", (self.sistema, self.func)).fetchone()[0]
        con.close()
        self.assertEqual(n, 0)


if __name__ == "__main__":
    unittest.main()
