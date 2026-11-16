"""Restauração de backup (administrador + código de verificação) e menu recolhido logo após o login."""
import os
import re
import unittest

from app import db as dbmod
from app.views_admin import PREFIXO_SEGURANCA
from tests.test_chat_blindagens import Base


class RestaurarBackup(Base):
    def _backup(self, c):
        self.post(c, "/backup")
        pasta = os.path.join(self.app.config["PASTA_DADOS"], "backups")
        return sorted(f for f in os.listdir(pasta) if f.startswith("BACKUP_"))[-1]

    def _contar(self):
        con = dbmod.conectar(self.app.config["DATABASE"])
        n = con.execute("SELECT COUNT(*) FROM clientes").fetchone()[0]
        con.close()
        return n

    def _incluir_cliente(self, nome):
        con = dbmod.conectar(self.app.config["DATABASE"])
        con.execute("INSERT INTO clientes (nome) VALUES (?)", (nome,))
        con.commit()
        con.close()

    def test_codigo_errado_nao_restaura_e_certo_restaura(self):
        c = self.cliente()
        nome = self._backup(c)
        antes = self._contar()
        self._incluir_cliente("POSTERIOR AO BACKUP")
        pagina = self.texto(c.get("/backup/restaurar?nome=" + nome))
        codigo = re.search(r"letter-spacing:\.2em\">(\d{6})<", pagina).group(1)
        errado = "000000" if codigo != "000000" else "111111"
        r = self.post(c, "/backup/restaurar", {"nome": nome, "codigo": errado})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self._contar(), antes + 1)
        # o código é de uso único: depois de errar, é preciso pedir outro
        c.get("/backup/restaurar?nome=" + nome)
        with c.session_transaction() as s:
            certo = s["restaurar"]["codigo"]
        self.post(c, "/backup/restaurar", {"nome": nome, "codigo": certo})
        self.assertEqual(self._contar(), antes)
        pasta = os.path.join(self.app.config["PASTA_DADOS"], "backups")
        self.assertTrue(any(f.startswith(PREFIXO_SEGURANCA) for f in os.listdir(pasta)))

    def test_sem_pedido_previo_nada_acontece(self):
        c = self.cliente()
        nome = self._backup(c)
        self._incluir_cliente("NAO PODE SUMIR")
        n = self._contar()
        self.post(c, "/backup/restaurar", {"nome": nome, "codigo": "123456"})
        self.assertEqual(self._contar(), n)

    def test_so_administrador(self):
        self.criar_usuario("GERENTE", ["backup"])
        c = self.cliente("GERENTE", "senha123")
        r = c.get("/backup/restaurar")
        self.assertEqual(r.status_code, 302)
        self.assertNotIn("Restaurar backup", self.texto(c.get("/backup")))


class MenuRecolhido(Base):
    def test_marca_so_logo_apos_o_login(self):
        c = self.app.test_client()
        c.get("/login")
        with c.session_transaction() as s:
            token = s["csrf"]
        c.post("/login", data={"usuario": "ADMIN", "senha": "admin", "_csrf": token})
        self.assertIn("data-menu-recolher", self.texto(c.get("/", follow_redirects=True)))
        self.assertNotIn("data-menu-recolher", self.texto(c.get("/", follow_redirects=True)))


if __name__ == "__main__":
    unittest.main()
