"""Ao abrir o sistema, quem tem acesso à agenda cai direto nela; os demais continuam no Início."""
import json
import os
import tempfile
import unittest
from urllib.parse import quote

from app import create_app
from app import db as dbmod
from app import modulos


class AbrirNaAgenda(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pasta = tempfile.TemporaryDirectory()
        cls.app = create_app(os.path.join(cls.pasta.name, "t.db"))
        cls.app.config["TESTING"] = True
        cls.criar_usuario("ADMIN_AGENDA", "senha123", list(modulos.CHAVES), admin=1)
        cls.criar_usuario("AGENDA_USU", "senha123", ["agenda"])
        cls.criar_usuario("LEITOR_AGENDA", "senha123", ["agenda_leitura"])
        cls.criar_usuario("SEM_AGENDA", "senha123", ["dashboard"])

    @classmethod
    def tearDownClass(cls):
        cls.pasta.cleanup()

    @classmethod
    def criar_usuario(cls, nome, senha, modulos_lista, admin=0):
        from werkzeug.security import generate_password_hash
        con = dbmod.conectar(cls.app.config["DATABASE"])
        con.execute("INSERT OR REPLACE INTO usuarios (usuario, senha_hash, admin, ativo, modulos) VALUES (?,?,?,1,?)",
                    (nome, generate_password_hash(senha), admin, json.dumps(modulos_lista)))
        con.commit()
        con.close()

    def login(self, usuario, proximo=None):
        """Entra pelo formulário; `proximo` vai na URL, como o login_obrigatorio faz."""
        c = self.app.test_client()
        c.get("/login")
        with c.session_transaction() as s:
            token = s["csrf"]
        url = "/login" + ("?proximo=" + quote(proximo, safe="") if proximo is not None else "")
        r = c.post(url, data={"usuario": usuario, "senha": "senha123", "_csrf": token})
        self.assertEqual(r.status_code, 302, r.get_data(as_text=True)[:300])
        c.get("/saude-inexistente")  # renova o token CSRF da sessão
        return c, r.headers["Location"]

    def test_admin_sem_proximo_cai_na_agenda(self):
        _, destino = self.login("ADMIN_AGENDA")
        self.assertTrue(destino.endswith("/agenda") or "/agenda" in destino, destino)

    def test_proximo_raiz_vai_para_a_agenda(self):
        _, destino = self.login("ADMIN_AGENDA", proximo="/?")
        self.assertIn("/agenda", destino)

    def test_proximo_explicito_e_respeitado(self):
        _, destino = self.login("ADMIN_AGENDA", proximo="/contas")
        self.assertTrue(destino.endswith("/contas"), destino)

    def test_leitor_da_agenda_tambem_cai_nela(self):
        _, destino = self.login("LEITOR_AGENDA")
        self.assertIn("/agenda", destino)

    def test_raiz_sem_referer_redireciona_para_a_agenda(self):
        c, _ = self.login("AGENDA_USU")
        r = c.get("/")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/agenda", r.headers["Location"])

    def test_raiz_com_referer_do_proprio_sistema_mostra_o_inicio(self):
        c, _ = self.login("AGENDA_USU")
        r = c.get("/", headers={"Referer": "http://localhost/agenda/"})
        self.assertEqual(r.status_code, 200)

    def test_usuario_sem_agenda_cai_no_inicio(self):
        _, destino = self.login("SEM_AGENDA")
        self.assertNotIn("/agenda", destino)
        self.assertTrue(destino.endswith("/"), destino)

    def test_usuario_sem_agenda_raiz_sem_referer_mostra_o_inicio(self):
        c, _ = self.login("SEM_AGENDA")
        self.assertEqual(c.get("/").status_code, 200)


if __name__ == "__main__":
    unittest.main()
