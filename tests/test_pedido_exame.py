"""Pedido de exame: formulário, impressão no modelo Word e gravação em pedidos_exame."""
import unittest

from app import db as dbmod
from tests.test_chat_blindagens import Base

DADOS = {
    "paciente": "Maria da Silva",
    "exames": "- TOMOGRAFIA PARA PESQUISA DE ESCORE DE CÁLCIO\n- cintilografia óssea\n\n",
    "data": "2026-11-14",
    "cliente_id": "",
    "medico": "Dr. Fulano de Tal",
    "especialidade": "Médico Nuclear",
    "registro": "CRM/MG 00.000",
}


class PedidoExame(Base):
    def contar(self):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            return con.execute("SELECT COUNT(*) FROM pedidos_exame").fetchone()[0]
        finally:
            con.close()

    def test_formulario_abre(self):
        c = self.cliente()
        r = c.get("/documentos/pedido-exame")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Pedido de exame", self.texto(r))

    def test_pedido_imprime_e_grava(self):
        c = self.cliente()
        r = self.post(c, "/documentos/pedido-exame", DADOS)
        self.assertEqual(r.status_code, 200)
        t = self.texto(r)
        self.assertIn("PEDIDO MÉDICO", t)
        self.assertIn("MARIA DA SILVA", t)
        self.assertIn("TOMOGRAFIA PARA PESQUISA DE ESCORE DE CÁLCIO", t)
        self.assertIn("CINTILOGRAFIA ÓSSEA", t)
        self.assertIn("14/11/2026", t)
        self.assertIn("Dr. Fulano de Tal", t)
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            linha = con.execute("SELECT paciente, exames, medico, usuario FROM pedidos_exame ORDER BY id DESC LIMIT 1").fetchone()
        finally:
            con.close()
        self.assertEqual(linha["paciente"], "MARIA DA SILVA")
        self.assertEqual(linha["exames"], "TOMOGRAFIA PARA PESQUISA DE ESCORE DE CÁLCIO\nCINTILOGRAFIA ÓSSEA")
        self.assertEqual(linha["medico"], "Dr. Fulano de Tal")
        self.assertEqual(linha["usuario"], "ADMIN")

    def test_sem_exame_nao_grava(self):
        c = self.cliente()
        antes = self.contar()
        r = self.post(c, "/documentos/pedido-exame", dict(DADOS, exames="  \n- \n"))
        self.assertEqual(r.status_code, 200)
        self.assertIn("pelo menos um exame", self.texto(r))
        self.assertEqual(self.contar(), antes)

    def test_segundo_formulario_traz_ultimo_medico(self):
        c = self.cliente()
        self.post(c, "/documentos/pedido-exame", DADOS)
        r = c.get("/documentos/pedido-exame")
        t = self.texto(r)
        self.assertEqual(r.status_code, 200)
        self.assertIn('value="Dr. Fulano de Tal"', t)
        self.assertIn('value="Médico Nuclear"', t)
        self.assertIn('value="CRM/MG 00.000"', t)

    def test_reimprimir(self):
        c = self.cliente()
        self.post(c, "/documentos/pedido-exame", DADOS)
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            pid = con.execute("SELECT MAX(id) FROM pedidos_exame").fetchone()[0]
        finally:
            con.close()
        r = c.get("/documentos/pedido-exame/%d" % pid)
        self.assertEqual(r.status_code, 200)
        self.assertIn("PEDIDO MÉDICO", self.texto(r))
        self.assertEqual(c.get("/documentos/pedido-exame/999999").status_code, 404)


if __name__ == "__main__":
    unittest.main()
