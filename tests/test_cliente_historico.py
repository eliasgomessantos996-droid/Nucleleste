"""Histórico do paciente: atendimentos do cliente (por código e por CPF sem código), filtro de período, PDF e 404."""
import unittest

from app import db as dbmod
from tests.test_chat_blindagens import Base

CPF_A = "529.982.247-25"
CPF_B = "111.444.777-35"


class HistoricoClienteTestes(Base):
    def setUp(self):
        # o banco é compartilhado pela classe: limpa os atendimentos dos testes anteriores
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            con.execute("DELETE FROM atendimentos")
            con.commit()
        finally:
            con.close()
        self.c = self.cliente()
        self.cid = self._criar_cliente("ANA HISTORICO", CPF_A)
        self.outro = self._criar_cliente("BIA OUTRA", CPF_B)

    def _criar_cliente(self, nome, cpf):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            cur = con.execute("INSERT INTO clientes (nome, cpf, data_nasc, sexo) VALUES (?,?,?,?)", (nome, cpf, "1980-05-17", "F"))
            con.commit()
            return cur.lastrowid
        finally:
            con.close()

    def _atendimento(self, cliente_id, cpf, data, exame, medico, cliente_nome="ANA HISTORICO"):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            con.execute("INSERT INTO atendimentos (cliente_id, cliente_nome, cpf, medico, data, exame, convenio) VALUES (?,?,?,?,?,?,?)",
                        (cliente_id, cliente_nome, cpf, medico, data, exame, "PARTICULAR"))
            con.commit()
        finally:
            con.close()

    def _preparar(self):
        self._atendimento(self.cid, CPF_A, "2024-01-10", "TIREOIDE", "DR. UM")
        self._atendimento(self.cid, CPF_A, "2024-03-05", "OSSEO", "")
        # lançado sem código, mas com o mesmo CPF: entra no histórico
        self._atendimento(None, CPF_A, "2024-02-20", "RIM", "DRA. DOIS")
        # de outro paciente: não entra
        self._atendimento(self.outro, CPF_B, "2024-02-21", "PULMAO", "DR. TRES", "BIA OUTRA")
        # sem código e sem CPF: não entra
        self._atendimento(None, "", "2024-02-22", "CORACAO", "DR. QUATRO", "ANA HISTORICO")

    def test_lista_do_cliente_em_ordem_decrescente(self):
        self._preparar()
        r = self.c.get("/clientes/%d/historico" % self.cid)
        self.assertEqual(r.status_code, 200)
        texto = self.texto(r)
        self.assertIn("ANA HISTORICO", texto)
        self.assertNotIn("PULMAO", texto)
        self.assertNotIn("CORACAO", texto)
        # ordem: 05/03 (OSSEO), 20/02 (RIM), 10/01 (TIREOIDE)
        self.assertLess(texto.index("OSSEO"), texto.index("RIM"))
        self.assertLess(texto.index("RIM"), texto.index("TIREOIDE"))
        self.assertIn("Não informado", texto)
        self.assertIn("3 atendimento(s)", texto)

    def test_inclui_atendimento_sem_cliente_id_com_mesmo_cpf(self):
        self._preparar()
        r = self.c.get("/clientes/%d/historico" % self.cid)
        self.assertIn("DRA. DOIS", self.texto(r))

    def test_filtro_de_periodo(self):
        self._preparar()
        r = self.c.get("/clientes/%d/historico?de=2024-02-01&ate=2024-02-28" % self.cid)
        texto = self.texto(r)
        self.assertIn("RIM", texto)
        self.assertNotIn("OSSEO", texto)
        self.assertNotIn("TIREOIDE", texto)
        self.assertIn("1 atendimento(s) no período", texto)

    def test_pdf_do_historico(self):
        self._preparar()
        r = self.c.get("/clientes/%d/historico.pdf" % self.cid)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.mimetype, "application/pdf")
        self.assertTrue(r.get_data().startswith(b"%PDF"))

    def test_pdf_com_periodo(self):
        self._preparar()
        r = self.c.get("/clientes/%d/historico.pdf?de=2024-02-01&ate=2024-02-28" % self.cid)
        self.assertTrue(r.get_data().startswith(b"%PDF"))

    def test_cliente_inexistente_da_404(self):
        self.assertEqual(self.c.get("/clientes/999999/historico").status_code, 404)
        self.assertEqual(self.c.get("/clientes/999999/historico.pdf").status_code, 404)

    def test_link_no_cadastro_e_na_lista(self):
        self.assertIn("/clientes/%d/historico" % self.cid, self.texto(self.c.get("/clientes/%d" % self.cid)))
        self.assertIn("/clientes/%d/historico" % self.cid, self.texto(self.c.get("/clientes")))


if __name__ == "__main__":
    unittest.main()
