"""Log de atualizações: botão em Alterar senha, lista de versões e PDF de cada versão."""
import re
import unittest

from app import novidades
from tests.test_chat_blindagens import Base


class LogDeAtualizacoes(Base):
    def test_botao_em_alterar_senha_e_lista(self):
        c = self.cliente()
        self.assertIn("Log de atualizações", self.texto(c.get("/minha-senha")))
        self.assertIn("Minha conta", self.texto(c.get("/minha-senha")))
        pagina = self.texto(c.get("/atualizacoes"))
        self.assertIn("Abrir log da atualização", pagina)
        self.assertIn("1.4.7", pagina)

    def test_pdf_da_versao(self):
        c = self.cliente()
        r = c.get("/atualizacoes/1.4.7.pdf")
        self.assertEqual((r.status_code, r.mimetype), (200, "application/pdf"))
        self.assertTrue(r.data.startswith(b"%PDF"))
        self.assertGreaterEqual(len(re.findall(rb"/Type\s*/Page\b", r.data)), 3)     # capa, sumário e as atualizações
        self.assertEqual(c.get("/atualizacoes/9.9.9.pdf").status_code, 404)

    def test_todas_as_versoes_geram_pdf(self):
        for v in novidades.versoes():
            self.assertTrue(novidades.pdf_versao(v["versao"], "Clínica", "maria").startswith(b"%PDF"), v["versao"])

    def test_exige_login(self):
        self.assertEqual(self.app.test_client().get("/atualizacoes").status_code, 302)


if __name__ == "__main__":
    unittest.main()
