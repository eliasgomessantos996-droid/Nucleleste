"""Cadastro de cliente: sexo e convênio obrigatórios e telefone no padrão (XX)9XXXX-XXXX, como na agenda.
O convênio também é obrigatório ao lançar o atendimento (critério para o lançamento na Medcloud)."""
import unittest

from app import db as dbmod
from tests.test_chat_blindagens import Base

CPF_VALIDO = "529.982.247-25"


class CadastroClienteTestes(Base):
    def dados(self, **extra):
        d = {"nome": "maria teste", "cpf": CPF_VALIDO, "data_nasc": "1980-05-17", "sexo": "F", "contato": "33 99999 1234",
             "convenio": "unimed"}
        d.update(extra)
        return d

    def ultimo_cliente(self):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            return dict(con.execute("SELECT * FROM clientes ORDER BY id DESC LIMIT 1").fetchone())
        finally:
            con.close()

    def test_salva_com_sexo_e_telefone_padrao(self):
        c = self.cliente()
        r = self.post(c, "/clientes/novo", self.dados())
        self.assertEqual(r.status_code, 302, self.texto(r)[:200])
        cl = self.ultimo_cliente()
        self.assertEqual(cl["sexo"], "F")
        self.assertEqual(cl["contato"], "(33)99999-1234")
        self.assertEqual(cl["convenio"], "UNIMED")

    def total_clientes(self):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            return con.execute("SELECT COUNT(*) FROM clientes").fetchone()[0]
        finally:
            con.close()

    def test_recusa_cadastro_sem_convenio(self):
        c = self.cliente()
        antes = self.total_clientes()
        for vazio in ("", "   "):
            r = self.post(c, "/clientes/novo", self.dados(convenio=vazio))
            self.assertEqual(r.status_code, 200)
            self.assertIn("Informe o convênio do cliente", self.texto(r))
        self.assertEqual(self.total_clientes(), antes)
        # o formulário marca o campo como obrigatório
        self.assertRegex(self.texto(c.get("/clientes/novo")), r'<label class="obrig">Convênio</label>\s*<select name="convenio" required>')

    def test_recusa_editar_tirando_o_convenio(self):
        c = self.cliente()
        outro_cpf = "111.444.777-35"   # CPF próprio: o banco é compartilhado entre os testes da classe
        self.assertEqual(self.post(c, "/clientes/novo", self.dados(cpf=outro_cpf)).status_code, 302)
        cid = self.ultimo_cliente()["id"]
        r = self.post(c, "/clientes/%d" % cid, self.dados(cpf=outro_cpf, convenio=""))
        self.assertEqual(r.status_code, 200)
        self.assertIn("Informe o convênio do cliente", self.texto(r))
        self.assertEqual(self.ultimo_cliente()["convenio"], "UNIMED")

    def lancar(self, c, cid, **extra):
        dados = {"cliente_id": str(cid), "exame": "RENAL", "data": "2026-11-10", "medico": "DR TESTE", "convenio": "",
                 "medicamentos": "", "exame_anterior": "NÃO INFORMADO", "manual": "1"}
        dados.update(extra)
        return self.post(c, "/atendimentos/novo", dados)

    def novo_cliente_direto(self, convenio):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            cur = con.execute("INSERT INTO clientes (nome, data_nasc, sexo, convenio) VALUES (?,?,?,?)",
                              ("PACIENTE CONVENIO", "1960-02-03", "M", convenio))
            con.commit()
            return cur.lastrowid
        finally:
            con.close()

    def total_atendimentos(self):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            return con.execute("SELECT COUNT(*) FROM atendimentos").fetchone()[0]
        finally:
            con.close()

    def test_atendimento_exige_convenio(self):
        c = self.cliente()
        sem = self.novo_cliente_direto("")        # cadastro antigo, sem convênio
        antes = self.total_atendimentos()
        r = self.lancar(c, sem)                    # nem no cadastro nem no atendimento: recusa
        self.assertEqual(r.status_code, 200)
        self.assertIn("Informe o convênio do atendimento", self.texto(r))
        self.assertEqual(self.total_atendimentos(), antes)
        self.assertEqual(self.lancar(c, sem, convenio="unimed").status_code, 302)   # escolhido no atendimento
        com = self.novo_cliente_direto("SUS")
        self.assertEqual(self.lancar(c, com).status_code, 302)                      # em branco: vale o do cadastro
        self.assertEqual(self.total_atendimentos(), antes + 2)
        self.assertRegex(self.texto(c.get("/atendimentos/novo")), r'<label class="obrig">Convênio deste atendimento</label>')

    def test_recusa_sem_sexo_e_telefone_invalido(self):
        c = self.cliente()
        r = self.post(c, "/clientes/novo", self.dados(sexo="", contato="999"))
        texto = self.texto(r)
        # a tela volta ao formulário com os dois avisos (não grava)
        self.assertEqual(r.status_code, 200)
        self.assertIn("Informe o sexo", texto)
        self.assertIn("Telefone inválido", texto)


if __name__ == "__main__":
    unittest.main()
