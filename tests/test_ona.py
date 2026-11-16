"""Relatório ONA: os indicadores batem com os dados, e PDF, Excel e permissão funcionam."""
import unittest
from datetime import date, timedelta

from app import ona
from app import db as dbmod
from tests.test_chat_blindagens import Base


class OnaTestes(Base):
    def test_indicadores_conferem_com_os_dados(self):
        hoje = date(2026, 11, 9)   # segunda-feira fixa: o prazo do laudo conta dias úteis (num sábado, +2 dias ainda caberia no prazo)
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            cid = con.execute("INSERT INTO clientes (nome, cpf, sexo) VALUES ('ANA', '52998224725', 'F')").lastrowid
            # exame 1: completo, identificado, cliente com CPF e sexo, laudo em 6 horas
            con.execute("INSERT INTO realizacoes (data, paciente, data_nasc, convenio, medico, hora_exame, cliente_id, exame, "
                        "laudo_situacao, laudo_liberado_em) VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (hoje.isoformat(), 'ANA', '1980-01-01', 'UNIMED', 'DR. X', '08:00', cid, 'PET-CT', 'LIBERADO',
                         hoje.isoformat() + ' 14:00:00'))
            # exame 2: sem nascimento nem convênio, laudo só depois de 2 dias
            con.execute("INSERT INTO realizacoes (data, paciente, hora_exame, exame, laudo_situacao, laudo_liberado_em) "
                        "VALUES (?,?,?,?,?,?)", (hoje.isoformat(), 'BIA', '09:00', 'SPECT', 'LIBERADO',
                                                 (hoje + timedelta(days=2)).isoformat() + ' 09:00:00'))
            con.commit()
            r = ona.indicadores(con, hoje, hoje)
        finally:
            con.close()
        self.assertEqual(r["total_exames"], 2)
        por_nome = {i["nome"]: i for i in r["indicadores"]}
        self.assertEqual((por_nome["Identificação do paciente"]["numerador"], por_nome["Identificação do paciente"]["denominador"]), (1, 2))
        self.assertEqual(por_nome["Identificação do paciente"]["percentual"], 50.0)
        self.assertEqual(por_nome["Registro completo do exame"]["numerador"], 1)
        self.assertEqual(por_nome["Cadastro com CPF"]["numerador"], 1)
        self.assertEqual(por_nome["Cadastro com sexo informado"]["numerador"], 1)
        self.assertEqual((por_nome["Laudo entregue no prazo"]["numerador"], por_nome["Laudo entregue no prazo"]["denominador"]), (1, 2))
        self.assertIn(("PET-CT", 1), r["por_exame"])
        self.assertIn(("Feminino", 1), r["por_sexo"])

    def test_pagina_pdf_excel_e_permissao(self):
        self.criar_usuario("ONA_NADA", ["atendimentos"])
        self.assertEqual(self.cliente("ONA_NADA", "senha123").get("/ona").status_code, 302)
        c = self.cliente()
        self.assertEqual(c.get("/ona").status_code, 200)
        pdf = c.get("/ona/relatorio.pdf")
        self.assertEqual(pdf.data[:4], b"%PDF")
        xlsx = c.get("/ona/relatorio.xlsx")
        self.assertTrue(xlsx.data.startswith(b"PK"))

    def test_dossie_completo_em_pdf_com_capa_sumario_e_contracapa(self):
        import re
        c = self.cliente()
        self.assertIn("PDF completo", self.texto(c.get("/ona")))
        r = c.get("/ona/relatorio.pdf?de=2020-01-01&ate=2020-01-31")          # período sem nenhum dado: nada pode quebrar
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.mimetype, "application/pdf")
        self.assertEqual(r.data[:4], b"%PDF")
        paginas = len(re.findall(rb"/Type\s*/Page[^s]", r.data))
        self.assertGreaterEqual(paginas, 14)                                 # capa, sumário, 10 seções, validação e contracapa
        self.assertIn(b"/Outlines", r.data)                                  # marcadores para navegar pelo painel do leitor
        self.assertTrue(c.get("/ona/relatorio.pdf?baixar=1").headers["Content-Disposition"].startswith("attachment"))
        self.assertEqual(c.get("/ona/relatorio-resumido.pdf").data[:4], b"%PDF")
        self.criar_usuario("ONA_SEM", ["atendimentos"])
        self.assertEqual(self.cliente("ONA_SEM", "senha123").get("/ona/relatorio.pdf").status_code, 302)


if __name__ == "__main__":
    unittest.main()
