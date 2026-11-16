"""Minha conta: tema (cor) e brilho (claro/escuro) por usuário, e faturamento sem a coluna "Registrado por"."""
import unittest

from app import db as dbmod
from tests.test_chat_blindagens import Base


class MinhaConta(Base):
    def _perfil(self, nome):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            r = con.execute("SELECT tema, brilho FROM usuarios WHERE usuario=?", (nome,)).fetchone()
            return r["tema"], r["brilho"]
        finally:
            con.close()

    def test_pagina_tem_senha_tema_e_brilho(self):
        c = self.cliente()
        pagina = self.texto(c.get("/minha-senha"))
        for esperado in ("Minha conta", "Alterar senha", 'id="op-temas"', 'id="op-brilhos"', "Escuro", "Claro", "Oceano", "Índigo",
                         "Log de atualizações"):
            self.assertIn(esperado, pagina)
        self.assertIn('data-brilho="claro"', pagina)

    def test_qualquer_cor_com_qualquer_brilho_e_vale_no_perfil(self):
        self.criar_usuario("APAR1", ["agenda"])
        c = self.cliente("APAR1", "senha123")
        self.post(c, "/meu-tema", {"tema": "roxo"})
        self.post(c, "/meu-tema", {"brilho": "escuro"})
        self.assertEqual(self._perfil("APAR1"), ("roxo", "escuro"))
        pagina = self.texto(c.get("/minha-senha"))
        self.assertIn('data-tema="roxo"', pagina)
        self.assertIn('data-brilho="escuro"', pagina)
        self.post(c, "/meu-tema", {"tema": "azul"})                 # mudar só a cor mantém o brilho
        self.assertEqual(self._perfil("APAR1"), ("azul", "escuro"))
        self.post(c, "/meu-tema", {"tema": "inexistente", "brilho": "neon"})   # valores inválidos voltam ao padrão
        self.assertEqual(self._perfil("APAR1"), ("verde", "claro"))
        # outro usuário não é afetado
        self.criar_usuario("APAR2", ["agenda"])
        self.assertEqual(self._perfil("APAR2"), ("verde", "claro"))

    def test_seletor_saiu_do_rodape_e_menu_leva_a_minha_conta(self):
        c = self.cliente()
        pagina = self.texto(c.get("/", headers={"Referer": "http://localhost/"}))   # clique em Início no menu
        self.assertNotIn('id="tema-escolha"', pagina)
        self.assertIn("Minha conta", pagina)

    def test_faturamento_sem_registrado_por(self):
        c = self.cliente()
        self.assertNotIn("Registrado por", self.texto(c.get("/faturamento")))


if __name__ == "__main__":
    unittest.main()
