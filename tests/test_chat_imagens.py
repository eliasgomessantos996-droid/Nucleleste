"""Chat com imagens: envio, quem pode ver, tipos aceitos e apagamento depois de 24 horas (sem deixar arquivo órfão)."""
import io
import sqlite3
import unittest
from datetime import datetime, timedelta

from app import anexos
from app import chat
from app import db as dbmod
from tests.test_chat_blindagens import Base

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64          # cabeçalho de PNG (o tipo é conferido pelo conteúdo)
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


class ChatImagens(Base):
    def _con(self):
        return dbmod.conectar(self.app.config["DATABASE"])

    def _blobs_chat(self):
        caminho = anexos.caminho_ao_lado(self.app.config["DATABASE"])
        con = sqlite3.connect(caminho)
        try:
            return con.execute("SELECT COUNT(*) FROM anexos WHERE origem='chat'").fetchone()[0]
        finally:
            con.close()

    def _enviar(self, c, para, conteudo, corpo="", nome="foto.png"):
        return self.post(c, "/mensagens/enviar", {"para": para, "corpo": corpo, "imagem": (io.BytesIO(conteudo), nome)},
                         headers={"Accept": "application/json"}, content_type="multipart/form-data")

    def test_envio_visualizacao_e_permissao(self):
        ana = self.criar_usuario("IMG_ANA")
        bia = self.criar_usuario("IMG_BIA")
        self.criar_usuario("IMG_CAIO")
        a, b, c = (self.cliente(u, "senha123") for u in ("IMG_ANA", "IMG_BIA", "IMG_CAIO"))
        r = self._enviar(a, bia, PNG, corpo="olha isso")
        self.assertEqual(r.status_code, 200, self.texto(r))
        m = r.get_json()["mensagem"]
        self.assertTrue(m["imagem"].startswith("/mensagens/anexo/"))
        self.assertFalse(m["so_imagem"])
        # remetente e destinatário veem; um terceiro não
        self.assertEqual(a.get(m["imagem"]).data, PNG)
        rb = b.get(m["imagem"])
        self.assertEqual(rb.status_code, 200)
        self.assertEqual(rb.mimetype, "image/png")
        self.assertEqual(c.get(m["imagem"]).status_code, 404)
        # só imagem, sem texto: a prévia da conversa mostra "Imagem"
        r2 = self._enviar(a, bia, JPG, nome="x.jpg")
        self.assertTrue(r2.get_json()["mensagem"]["so_imagem"])
        n = b.get("/mensagens/novas?depois=0", headers={"X-Passivo": "1"}).get_json()
        self.assertIn("Imagem", n["novas"][-1]["previa"])
        con = self._con()
        self.assertEqual(con.execute("SELECT anexo_tipo FROM chat_mensagens WHERE id=?",
                                     (r2.get_json()["mensagem"]["id"],)).fetchone()[0], "image/jpeg")
        con.close()
        self.assertGreaterEqual(ana, 1)

    def test_tipos_e_tamanho(self):
        self.criar_usuario("IMG_DUDA")
        eva = self.criar_usuario("IMG_EVA")
        d = self.cliente("IMG_DUDA", "senha123")
        r = self._enviar(d, eva, b"%PDF-1.4 nao e imagem", nome="foto.png")    # extensão mentindo: recusado pelo conteúdo
        self.assertEqual(r.status_code, 400)
        r = self._enviar(d, eva, PNG + b"\x00" * (chat.IMAGEM_MAX + 10))
        self.assertEqual(r.status_code, 400)
        self.assertIn("5 MB", r.get_json()["erro"])

    def test_apaga_em_24_horas_sem_deixar_orfao(self):
        fab = self.criar_usuario("IMG_FAB")
        gil = self.criar_usuario("IMG_GIL")
        con = self._con()
        antes = self._blobs_chat()
        m = chat.enviar(con, fab, gil, "documento", imagem=PNG, imagem_nome="a.png")
        self.assertEqual(self._blobs_chat(), antes + 1)
        # antes do prazo nada muda
        self.assertEqual(chat.apagar_imagens_expiradas(con, datetime.now() + timedelta(hours=23)), 0)
        self.assertIsNotNone(chat.imagem_da_mensagem(con, gil, m["id"]))
        # depois de 24 h: a imagem some do anexos.db e a mensagem (com o texto) continua
        self.assertEqual(chat.apagar_imagens_expiradas(con, datetime.now() + timedelta(hours=25)), 1)
        self.assertEqual(self._blobs_chat(), antes)
        linha = con.execute("SELECT corpo, anexo_id, anexo_tipo FROM chat_mensagens WHERE id=?", (m["id"],)).fetchone()
        self.assertEqual((linha["corpo"], linha["anexo_id"], linha["anexo_tipo"]), ("documento", None, chat.IMAGEM_APAGADA))
        self.assertIsNone(chat.imagem_da_mensagem(con, gil, m["id"]))
        self.assertTrue(chat.serializar(con.execute("SELECT * FROM chat_mensagens WHERE id=?", (m["id"],)).fetchone(), gil)["imagem_apagada"])
        # a limpeza dos avisos de laudo não apaga a mensagem com imagem antes da hora
        m2 = chat.enviar(con, fab, gil, "", imagem=PNG)
        from app import laudos
        laudos.apagar_expiradas(con, datetime.now() + timedelta(hours=1))
        self.assertIsNotNone(con.execute("SELECT id FROM chat_mensagens WHERE id=?", (m2["id"],)).fetchone())
        con.close()

    def test_imagem_esquecida_no_anexos_db_e_removida(self):
        caminho = anexos.caminho_ao_lado(self.app.config["DATABASE"])
        orfa = anexos.gravar(caminho, "chat", PNG)
        con2 = sqlite3.connect(caminho)
        con2.execute("UPDATE anexos SET criado_em=? WHERE id=?", ((datetime.now() - timedelta(hours=30)).isoformat(timespec="seconds"), orfa))
        con2.commit()
        con2.close()
        con = self._con()
        chat.apagar_imagens_expiradas(con)
        con.close()
        self.assertIsNone(anexos.ler(caminho, orfa))

    def test_nucleai_nao_recebe_imagem(self):
        hugo = self.criar_usuario("IMG_HUGO")
        con = self._con()
        bot = con.execute("SELECT id FROM usuarios WHERE sistema=3").fetchone()
        if bot is None:
            con.close()
            self.skipTest("sem usuário da NucleAI neste banco")
        with self.assertRaises(chat.ErroChat):
            chat.enviar(con, hugo, bot["id"], "", imagem=PNG)
        con.close()


if __name__ == "__main__":
    unittest.main()
