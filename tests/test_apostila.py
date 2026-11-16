"""Apostila do sistema em PDF: fica no Log de atualizações (exige entrar), some da tela de entrada, traz as novidades da versão
e é refeita quando a ajuda da NucleAI é editada. O endereço antigo /apostila.pdf só redireciona."""
import re
import unittest

from app import ajuda_admin
from app.ajuda_base import TEMAS
from app.apostila import gerar_pdf
from app.db import get_db
from tests.test_chat_blindagens import Base


class ApostilaNoLogDeAtualizacoes(Base):
    def test_sem_login_redireciona_para_o_login(self):
        r = self.app.test_client().get("/atualizacoes/apostila.pdf")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r.headers["Location"])

    def test_logado_recebe_pdf_com_muitas_paginas(self):
        c = self.cliente()
        r = c.get("/atualizacoes/apostila.pdf")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.mimetype, "application/pdf")
        self.assertTrue(r.data.startswith(b"%PDF"))
        paginas = len(re.findall(rb"/Type\s*/Page[^s]", r.data))
        self.assertGreaterEqual(paginas, 30)

    def test_tela_de_login_nao_tem_a_apostila(self):
        r = self.app.test_client().get("/login")
        self.assertNotIn("apostila", r.get_data(as_text=True).lower())

    def test_endereco_antigo_redireciona_para_o_log(self):
        r = self.app.test_client().get("/apostila.pdf")
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers["Location"].endswith("/atualizacoes/apostila.pdf"))

    def test_tela_do_log_tem_o_link_da_apostila(self):
        r = self.cliente().get("/atualizacoes")
        self.assertEqual(r.status_code, 200)
        self.assertIn("/atualizacoes/apostila.pdf", r.get_data(as_text=True))

    def test_editar_a_ajuda_muda_o_pdf(self):
        tema, mods = TEMAS[0]
        modulo, areas = mods[0]
        area = areas[0][0]
        with self.app.app_context():
            db = get_db()
            antes = gerar_pdf(db, "9.9.9", "")
            ajuda_admin.editar(db, "ADMIN", tema, modulo, area, "APOSTILATESTEXYZ texto de teste com mais de vinte letras")
            depois = gerar_pdf(db, "9.9.9", "")
        self.assertNotEqual(antes, depois)


if __name__ == "__main__":
    unittest.main()
