"""Escolha dos painéis do Início: a gerência esconde painéis para os usuários comuns (cliente de teste do Flask)."""
import json
import os
import tempfile
import unittest

from app import create_app
from app import db as dbmod


class PaineisDashboard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pasta = tempfile.TemporaryDirectory()
        cls.app = create_app(os.path.join(cls.pasta.name, "t.db"))
        cls.app.config["TESTING"] = True
        cls.criar_usuario("comum_paineis", "senha1", ["dashboard"])
        cls.criar_usuario("gerente_paineis", "senha2", ["dashboard", "gerencia"])

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

    def ocultos_gravados(self):
        con = dbmod.conectar(self.app.config["DATABASE"])
        row = con.execute("SELECT valor FROM config WHERE chave='dashboard_paineis_ocultos'").fetchone()
        con.close()
        return json.loads(row[0]) if row else None

    def gravar_ocultos(self, lista):
        con = dbmod.conectar(self.app.config["DATABASE"])
        con.execute("INSERT INTO config (chave, valor) VALUES ('dashboard_paineis_ocultos', ?) "
                    "ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor", (json.dumps(lista),))
        con.commit()
        con.close()

    def setUp(self):
        con = dbmod.conectar(self.app.config["DATABASE"])
        con.execute("DELETE FROM config WHERE chave='dashboard_paineis_ocultos'")
        con.commit()
        con.close()

    def test_usuario_comum_nao_ve_painel_oculto(self):
        self.gravar_ocultos(["medicos"])
        r = self.cliente("comum_paineis", "senha1").get("/dashboard")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("Médicos solicitantes", self.texto(r))
        self.assertNotIn("g-medicos", self.texto(r))
        self.assertIn("Por exame", self.texto(r))  # os demais continuam
        self.assertNotIn("Escolher painéis", self.texto(r))

    def test_painel_oculto_sai_do_json_da_pagina(self):
        self.gravar_ocultos(["medicos", "kpis"])
        r = self.cliente("comum_paineis", "senha1").get("/dashboard")
        self.assertNotIn('"medicos"', self.texto(r).split('id="dados"')[1].split("</script>")[0])
        self.assertNotIn('"kpis"', self.texto(r).split('id="dados"')[1].split("</script>")[0])

    def test_gerencia_ve_tudo_e_ve_link(self):
        self.gravar_ocultos(["medicos", "faixas", "kpis"])
        r = self.cliente("gerente_paineis", "senha2").get("/dashboard")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Médicos solicitantes", self.texto(r))
        self.assertIn("Faixa etária", self.texto(r))
        self.assertIn("Escolher painéis", self.texto(r))

    def test_usuario_comum_nao_acessa_a_tela_de_escolha(self):
        # o bloqueio por módulo (before_request) redireciona antes da view; a view também faz abort(403)
        c = self.cliente("comum_paineis", "senha1")
        r = c.get("/dashboard/paineis")
        self.assertEqual(r.status_code, 302)
        self.assertNotIn("Escolha o que os usuários veem", self.texto(r))
        r = self.post(c, "/dashboard/paineis", {"mostrar": ["serie"]})
        self.assertEqual(r.status_code, 302)
        self.assertIsNone(self.ocultos_gravados())

    def test_gerencia_salva_e_grava_a_chave(self):
        c = self.cliente("gerente_paineis", "senha2")
        r = c.get("/dashboard/paineis")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Escolha o que os usuários veem no Início. Administrador e gerência sempre veem todos os painéis.",
                      self.texto(r))
        r = self.post(c, "/dashboard/paineis", {"mostrar": ["serie", "exames", "recentes"]})
        self.assertEqual(r.status_code, 302)
        ocultos = self.ocultos_gravados()
        self.assertIn("medicos", ocultos)
        self.assertNotIn("serie", ocultos)
        self.assertEqual(len(ocultos), 8)
        # o usuário comum passa a não ver o que foi escondido
        r = self.cliente("comum_paineis", "senha1").get("/dashboard")
        self.assertNotIn("Médicos solicitantes", self.texto(r))
        self.assertIn("Atendimentos por dia", self.texto(r))

    def test_chave_desconhecida_e_ignorada(self):
        self.gravar_ocultos(["medicos", "chave_inventada"])
        r = self.cliente("comum_paineis", "senha1").get("/dashboard")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("Médicos solicitantes", self.texto(r))


if __name__ == "__main__":
    unittest.main()
