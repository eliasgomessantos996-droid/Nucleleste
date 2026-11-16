"""Campanhas de saúde do mês: laço e mensagem no sistema, e a gerência liga ou desliga em Painéis do Início."""
import json
import os
import tempfile
import unittest
from datetime import date

from app import campanhas, create_app
from app import db as dbmod


class CampanhasSaude(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pasta = tempfile.TemporaryDirectory()
        cls.app = create_app(os.path.join(cls.pasta.name, "t.db"))
        cls.app.config["TESTING"] = True
        cls.criar_usuario("comum_campanhas", "senha1", ["dashboard"])
        cls.criar_usuario("gerente_campanhas", "senha2", ["dashboard", "gerencia"])

    @classmethod
    def tearDownClass(cls):
        cls.pasta.cleanup()

    @classmethod
    def criar_usuario(cls, nome, senha, modulos, admin=0):
        from werkzeug.security import generate_password_hash
        con = dbmod.conectar(cls.app.config["DATABASE"])
        con.execute("INSERT OR REPLACE INTO usuarios (usuario, senha_hash, admin, ativo, modulos) VALUES (?,?,?,1,?)",
                    (nome, generate_password_hash(senha), admin, json.dumps(modulos)))
        con.commit()
        con.close()

    def cliente(self, usuario, senha):
        c = self.app.test_client()
        c.get("/login")
        with c.session_transaction() as s:
            token = s["csrf"]
        r = c.post("/login", data={"usuario": usuario, "senha": senha, "_csrf": token})
        self.assertEqual(r.status_code, 302, r.get_data(as_text=True)[:300])
        c.get("/saude-inexistente")  # renova o token CSRF da sessão
        return c

    def post(self, c, url, data=None):
        with c.session_transaction() as s:
            token = s["csrf"]
        dados = dict(data or {})
        dados["_csrf"] = token
        return c.post(url, data=dados)

    def texto(self, r):
        return r.get_data(as_text=True)

    def gravar_ligado(self, valor):
        con = dbmod.conectar(self.app.config["DATABASE"])
        con.execute("INSERT INTO config (chave, valor) VALUES (?,?) ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor",
                    (campanhas.CHAVE, valor))
        con.commit()
        con.close()

    def test_todos_os_meses_tem_campanha_completa(self):
        for mes in range(1, 13):
            lista = campanhas.CAMPANHAS[mes]
            self.assertTrue(lista, mes)
            for c in lista:
                self.assertTrue(c["nome"], mes)
                self.assertTrue(c["cor"].startswith("#"), mes)
                self.assertTrue(c["mensagem"], mes)

    def test_lista_do_mes_usa_a_data_informada(self):
        self.assertEqual(campanhas.do_mes(date(2026, 10, 5))[0]["nome"], "Outubro Rosa")
        self.assertEqual(campanhas.do_mes(date(2026, 1, 20))[0]["nome"], "Janeiro Branco")

    def test_campanha_do_mes_aparece_no_inicio_e_no_login(self):
        self.gravar_ligado("1")
        nome = campanhas.do_mes()[0]["nome"]
        c = self.cliente("comum_campanhas", "senha1")
        self.assertIn(nome, self.texto(c.get("/")))
        self.assertIn(nome, self.texto(self.app.test_client().get("/login")))

    def test_gerencia_desliga_e_inicio_some_a_campanha(self):
        self.gravar_ligado("1")
        nome = campanhas.do_mes()[0]["nome"]
        g = self.cliente("gerente_campanhas", "senha2")
        r = self.post(g, "/dashboard/paineis", {"acao": "campanhas"})  # sem o checkbox: desliga
        self.assertEqual(r.status_code, 302)
        con = dbmod.conectar(self.app.config["DATABASE"])
        valor = con.execute("SELECT valor FROM config WHERE chave=?", (campanhas.CHAVE,)).fetchone()[0]
        con.close()
        self.assertEqual(valor, "0")
        c = self.cliente("comum_campanhas", "senha1")
        self.assertNotIn("Campanha do mês", self.texto(c.get("/")))
        self.assertNotIn(nome, self.texto(self.app.test_client().get("/login")))
        self.gravar_ligado("1")  # volta ao padrão para os demais testes

    def test_gerencia_liga_de_novo(self):
        self.gravar_ligado("0")
        g = self.cliente("gerente_campanhas", "senha2")
        self.post(g, "/dashboard/paineis", {"acao": "campanhas", "campanhas": "1"})
        with self.app.app_context():
            self.assertIsNotNone(campanhas.atual())

    def test_usuario_comum_nao_altera_campanhas(self):
        self.gravar_ligado("1")
        c = self.cliente("comum_campanhas", "senha1")
        r = self.post(c, "/dashboard/paineis", {"acao": "campanhas"})
        self.assertIn(r.status_code, (302, 403))
        with self.app.app_context():
            self.assertTrue(campanhas.ligado())


if __name__ == "__main__":
    unittest.main()
