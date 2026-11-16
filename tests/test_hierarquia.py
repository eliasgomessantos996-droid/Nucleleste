"""Hierarquia Desenvolvedor > Gestão > Outros usuários."""
from app import db as dbmod
from app import suporte
from tests.test_chat_blindagens import Base


class Hierarquia(Base):
    def _con(self):
        return dbmod.conectar(self.app.config["DATABASE"])

    def _id(self, nome):
        con = self._con()
        try:
            return con.execute("SELECT id FROM usuarios WHERE usuario=?", (nome,)).fetchone()[0]
        finally:
            con.close()

    def _linha(self, uid):
        con = self._con()
        try:
            return dict(con.execute("SELECT * FROM usuarios WHERE id=?", (uid,)).fetchone())
        finally:
            con.close()

    def _montar(self):
        con = self._con()
        suporte.garantir(con)
        con.commit()
        dev = suporte.usuario_dev_id(con)
        con.execute("UPDATE usuarios SET trocar_senha=0, senha_hash=? WHERE id=?",
                    (__import__("werkzeug.security", fromlist=["x"]).generate_password_hash("senha123"), dev))
        con.commit()
        nome_dev = con.execute("SELECT usuario FROM usuarios WHERE id=?", (dev,)).fetchone()[0]
        con.close()
        self.criar_usuario("H_GESTAO", [], admin=True)
        self.criar_usuario("H_COMUM", ["atendimentos", "agenda"])
        self.criar_usuario("H_GERIR", ["usuarios_gerir", "atendimentos"])
        return dev, nome_dev

    def test_gestao_nao_edita_desenvolvedor_mas_edita_comum(self):
        dev, _ = self._montar()
        g = self.cliente("H_GESTAO", "senha123")
        r = self.post(g, "/usuarios/%d" % dev, {"modulos": ["agenda"], "perfil": ""})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self._linha(dev)["admin"], 1)
        self.assertIn("suporte_dev", self._linha(dev)["modulos"])
        self.post(g, "/usuarios/%d/senha" % dev, {"senha": "trocada"})
        self.assertNotEqual(self._linha(dev)["senha_hash"], None)
        antes = self._linha(dev)["senha_hash"]
        self.post(g, "/usuarios/%d/senha" % dev, {"senha": "outra123"})
        self.assertEqual(self._linha(dev)["senha_hash"], antes)
        self.post(g, "/usuarios/%d/situacao" % dev, {})
        self.assertEqual(self._linha(dev)["ativo"], 1)
        comum = self._id("H_COMUM")
        self.post(g, "/usuarios/%d" % comum, {"modulos": ["agenda"]})
        self.assertIn("agenda", self._linha(comum)["modulos"])
        self.assertNotIn("atendimentos", self._linha(comum)["modulos"])

    def test_gestao_nao_concede_modulo_do_desenvolvedor(self):
        self._montar()
        g = self.cliente("H_GESTAO", "senha123")
        comum = self._id("H_COMUM")
        self.post(g, "/usuarios/%d" % comum, {"modulos": ["agenda", "suporte_dev"]})
        self.assertNotIn("suporte_dev", self._linha(comum)["modulos"])

    def test_desenvolvedor_edita_gestao_e_comum(self):
        dev, nome_dev = self._montar()
        d = self.cliente(nome_dev, "senha123")
        gest = self._id("H_GESTAO")
        r = self.post(d, "/usuarios/%d" % gest, {"modulos": ["agenda"], "perfil": ""})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self._linha(gest)["admin"], 0)
        comum = self._id("H_COMUM")
        self.post(d, "/usuarios/%d" % comum, {"modulos": ["agenda", "suporte_dev"]})
        self.assertIn("suporte_dev", self._linha(comum)["modulos"])
        self.assertIn("Desenvolvedor", self.texto(d.get("/usuarios")))

    def test_usuario_com_permissao_so_edita_comuns_e_so_o_que_tem(self):
        dev, _ = self._montar()
        c = self.cliente("H_GERIR", "senha123")
        self.assertEqual(c.get("/usuarios").status_code, 200)
        comum = self._id("H_COMUM")
        self.post(c, "/usuarios/%d" % comum, {"modulos": ["agenda", "atendimentos", "faturamento"]})
        mods = self._linha(comum)["modulos"]
        self.assertNotIn("faturamento", mods)          # ele não possui o módulo, então não entrega
        self.post(c, "/usuarios/%d" % comum, {"modulos": ["atendimentos"], "perfil": "admin"})
        self.assertEqual(self._linha(comum)["admin"], 0)
        self.assertIn("atendimentos", self._linha(comum)["modulos"])
        gest = self._id("H_GESTAO")
        self.post(c, "/usuarios/%d" % gest, {"modulos": ["agenda"]})
        self.assertEqual(self._linha(gest)["admin"], 1)
        self.post(c, "/usuarios/%d" % dev, {"modulos": ["agenda"]})
        self.assertIn("suporte_dev", self._linha(dev)["modulos"])
        self.post(c, "/usuarios/%d" % self._id("H_GERIR"), {"modulos": ["usuarios_gerir", "atendimentos", "agenda"]})
        self.assertNotIn("agenda", self._linha(self._id("H_GERIR"))["modulos"])      # nem a si mesmo

    def test_usuario_sem_permissao_nao_entra(self):
        self._montar()
        c = self.cliente("H_COMUM", "senha123")
        self.assertEqual(c.get("/usuarios").status_code, 302)
        self.assertEqual(self.post(c, "/usuarios/%d" % self._id("H_COMUM"), {"modulos": ["agenda"]}).status_code, 302)

    def test_gestao_e_desenvolvedor_trocam_o_login_sem_mexer_no_nome(self):
        dev, nome_dev = self._montar()
        con = self._con()
        con.execute("INSERT INTO caixa_sessoes (data, usuario, status) VALUES ('2026-01-01', 'H_COMUM', 'ABERTO')")
        con.commit()
        con.close()
        g = self.cliente("H_GESTAO", "senha123")
        comum = self._id("H_COMUM")
        pagina = self.texto(g.get("/usuarios/%d" % comum))
        self.assertIn('name="usuario"', pagina)
        self.post(g, "/usuarios/%d" % comum, {"usuario": "novo.login", "modulos": ["agenda"]})
        self.assertEqual(self._linha(comum)["usuario"], "NOVO.LOGIN")
        con = self._con()
        self.assertEqual(con.execute("SELECT COUNT(*) FROM caixa_sessoes WHERE usuario='NOVO.LOGIN'").fetchone()[0], 1)
        con.close()
        self.cliente("NOVO.LOGIN", "senha123")                       # entra com o login novo e a mesma senha
        # login repetido e curto demais são recusados
        self.post(g, "/usuarios/%d" % comum, {"usuario": "H_GESTAO", "modulos": ["agenda"]})
        self.assertEqual(self._linha(comum)["usuario"], "NOVO.LOGIN")
        self.post(g, "/usuarios/%d" % comum, {"usuario": "ab", "modulos": ["agenda"]})
        self.assertEqual(self._linha(comum)["usuario"], "NOVO.LOGIN")
        # a gestão não troca o login do desenvolvedor; o desenvolvedor troca o de qualquer um
        self.post(g, "/usuarios/%d" % dev, {"usuario": "OUTRO", "modulos": ["agenda"]})
        self.assertEqual(self._linha(dev)["usuario"], nome_dev)
        d = self.cliente(nome_dev, "senha123")
        self.post(d, "/usuarios/%d" % self._id("H_GESTAO"), {"usuario": "GESTAO2", "perfil": "admin", "modulos": []})
        self.assertEqual(self._linha(self._id("GESTAO2"))["usuario"], "GESTAO2")

    def test_usuario_com_permissao_nao_troca_login(self):
        self._montar()
        c = self.cliente("H_GERIR", "senha123")
        comum = self._id("H_COMUM")
        self.assertNotIn('name="usuario"', self.texto(c.get("/usuarios/%d" % comum)))
        self.post(c, "/usuarios/%d" % comum, {"usuario": "TROCADO", "modulos": ["atendimentos"]})
        self.assertEqual(self._linha(comum)["usuario"], "H_COMUM")
