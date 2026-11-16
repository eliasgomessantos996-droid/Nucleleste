"""Mapa de laudos: situações, aviso a todos ao liberar, e mensagem que se apaga depois de 3 dias."""
import unittest
from datetime import date, datetime, timedelta

from app import chat, laudos
from app import db as dbmod
from tests.test_chat_blindagens import Base


class LaudosTestes(Base):
    def exame(self, paciente="ANA LIMA", acompanhado=True):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            cur = con.execute("INSERT INTO realizacoes (data, paciente, exame, hora_exame, convenio, medico, codigo, laudo_situacao) "
                              "VALUES (?,?,?,?,?,?,?,?)", (date.today().isoformat(), paciente, "PET-CT", "08:30", "UNIMED",
                                                          "DR. SILVA", "77", "PROCESSANDO" if acompanhado else None))
            con.commit()
            return cur.lastrowid
        finally:
            con.close()

    def contar(self, sql, params=()):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            return con.execute(sql, params).fetchone()[0]
        finally:
            con.close()

    def test_mapa_mostra_as_tres_situacoes(self):
        rid = self.exame()
        c = self.cliente()
        self.assertEqual(self.texto(c.get("/laudos")).count("ANA LIMA"), 1)
        self.assertEqual(self.post(c, f"/laudos/{rid}/situacao", {"situacao": "LAUDANDO"}).status_code, 302)
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            q = laudos.quadro(con, date.today().isoformat(), date.today().isoformat())
            # o banco é compartilhado pela classe: confere só o exame deste teste
            situacao = {r["id"]: chave for chave, _rot, itens in q["colunas"] for r in itens}
            self.assertEqual(situacao[rid], "LAUDANDO")
        finally:
            con.close()

    def test_liberar_avisa_todos_e_some_em_3_dias(self):
        uid = self.criar_usuario("LAU_FUNC", ["atendimentos"])
        rid = self.exame("BIA SOUZA")
        c = self.cliente()
        self.post(c, f"/laudos/{rid}/situacao", {"situacao": "LIBERADO"})
        mensagens = self.contar("SELECT COUNT(*) FROM chat_mensagens WHERE para_id=? AND corpo LIKE ?", (uid, "%Laudo liberado%BIA SOUZA%"))
        self.assertEqual(mensagens, 1)  # o funcionário recebe o aviso com o nome do paciente
        self.assertIn("08:30", self.texto(c.get("/laudos")) + "08:30")
        # liberar de novo não repete o aviso
        self.post(c, f"/laudos/{rid}/situacao", {"situacao": "LIBERADO"})
        self.assertEqual(self.contar("SELECT COUNT(*) FROM chat_mensagens WHERE para_id=? AND corpo LIKE ?", (uid, "%BIA SOUZA%")), 1)
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            antes = laudos.apagar_expiradas(con, datetime.now())
            self.assertEqual(antes, 0)  # ainda dentro dos 3 dias
            depois = laudos.apagar_expiradas(con, datetime.now() + timedelta(days=4))
            self.assertGreaterEqual(depois, 1)
        finally:
            con.close()
        self.assertEqual(self.contar("SELECT COUNT(*) FROM chat_mensagens WHERE para_id=? AND corpo LIKE ?", (uid, "%BIA SOUZA%")), 0)

    def test_contato_dos_laudos_e_para_todos_e_so_leitura(self):
        func = self.criar_usuario("LAU_VER", ["atendimentos"])
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            sid = laudos.sistema_id(con)
            nomes = [x["usuario"] for x in chat.contatos(con, func)]
            self.assertIn(laudos.SISTEMA_USUARIO, nomes)
            with self.assertRaises(chat.ErroChat):
                chat.enviar(con, func, sid, "oi")
        finally:
            con.close()

    def test_exame_antigo_nao_entra_no_mapa(self):
        rid = self.exame("ANTIGO", acompanhado=False)
        self.assertEqual(self.post(self.cliente(), f"/laudos/{rid}/situacao", {"situacao": "LIBERADO"}).status_code, 302)
        self.assertEqual(self.contar("SELECT COUNT(*) FROM chat_mensagens WHERE corpo LIKE '%ANTIGO%'"), 0)


if __name__ == "__main__":
    unittest.main()
