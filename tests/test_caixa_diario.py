"""Caixa diário da empresa: saldos em cadeia iguais à planilha MOVIMENTO DE CAIXA (dia 01/10/2026), edição e relatório."""
import io
import unittest

from openpyxl import load_workbook

from app import caixa_diario as cx
from app import db as dbmod
from app import util
from tests.test_chat_blindagens import Base


class CaixaDiario(Base):
    def token(self, c):
        with c.session_transaction() as s:
            return s["csrf"]

    def setUp(self):
        con = dbmod.conectar(self.app.config["DATABASE"])
        cx.garantir(con)
        con.executescript("DELETE FROM cxd_lancamentos; DELETE FROM cxd_retidas; DELETE FROM cxd_inicio;")
        con.commit()
        con.close()

    def _db(self):
        con = dbmod.conectar(self.app.config["DATABASE"])
        cx.garantir(con)
        return con

    def _inicio_setembro(self, con):
        # fechamento de 30/09/2026 na planilha de setembro: BB 325.514,03 | Unicred 106.248,24 | Caixa 36.677,24 | dinheiro 23.800,08
        cx.definir_inicio(con, {"data": "2026-10-01", "bb": "325514,03", "unicred": "106248,24", "caixa": "36677,24",
                                "dinheiro": "23800,08"}, "teste")

    def _lancar(self, con, dia, tipo, descricao, valor, conta, nf=""):
        cx.lancar(con, cx.dados_do_formulario({"data": dia, "tipo": tipo, "descricao": descricao, "valor": valor,
                                               "conta": conta, "nf": nf}), "teste")

    def _outubro_01(self, con):
        # lançamentos do dia 01/10/2026 da planilha: amarelo = Banco do Brasil; os demais = movimento de caixa (dinheiro)
        for nome, valor, nf in (("ROSANGELA DOS SANTOS RENAL", "1290", "735"), ("JANETE RODRIGUES RENAL", "1290", "734"),
                                ("ALCIDES PEREIRA MIBI", "1295", "737")):
            self._lancar(con, "2026-10-01", "RECEITA", nome, valor, "BB", nf)
        self._lancar(con, "2026-10-01", "RECEITA", "FARIDE ALVES MIBI", "1295", "DINHEIRO", "738")
        self._lancar(con, "2026-10-01", "RECEITA", "MARIA DE LOURDES", "950", "DINHEIRO", "736")
        for nome, valor in (("GV INFORMATICA (COMPUTADOR ) 1/3", "715"), ("RESTAURANTE", "3348"), ("PAPEL FOTO", "950"),
                            ("PAGAMENTO MOTOTAX MENSAL (REF 09/2026)", "350")):
            self._lancar(con, "2026-10-01", "DESPESA", nome, valor, "DINHEIRO")

    def test_dia_01_10_bate_com_a_planilha(self):
        con = self._db()
        self._inicio_setembro(con)
        self._outubro_01(con)
        s = cx.saldos_do_dia(con, "2026-10-01")
        self.assertAlmostEqual(s["abertura_total"], 492239.59, places=2)      # Subtotal (B37) da planilha
        self.assertAlmostEqual(s["receitas"], 6120.00, places=2)              # Total de Receitas (B14)
        self.assertAlmostEqual(s["despesas"], 5363.00, places=2)              # soma das despesas (B35)
        self.assertAlmostEqual(s["contas"]["BB"]["fechamento"], 329389.03, places=2)       # B42
        self.assertAlmostEqual(s["contas"]["UNICRED"]["fechamento"], 106248.24, places=2)  # B43
        self.assertAlmostEqual(s["contas"]["CAIXA"]["fechamento"], 36677.24, places=2)     # B44
        self.assertAlmostEqual(s["contas"]["DINHEIRO"]["fechamento"], 20682.08, places=2)  # B45
        self.assertAlmostEqual(s["saldo_total"], 492996.59, places=2)         # Saldo Total (B47)
        con.close()

    def test_alterar_um_dia_antigo_ajusta_os_seguintes(self):
        con = self._db()
        self._inicio_setembro(con)
        self._outubro_01(con)
        self._lancar(con, "2026-10-02", "RECEITA", "PACIENTE NOVO", "100", "BB")
        antes = cx.saldos_do_dia(con, "2026-10-02")["saldo_total"]
        lid = con.execute("SELECT id FROM cxd_lancamentos WHERE descricao='RESTAURANTE'").fetchone()["id"]
        cx.atualizar(con, lid, cx.dados_do_formulario({"data": "2026-10-01", "tipo": "DESPESA", "descricao": "RESTAURANTE",
                                                       "valor": "3248", "conta": "DINHEIRO"}), "teste")
        depois = cx.saldos_do_dia(con, "2026-10-02")["saldo_total"]
        self.assertAlmostEqual(depois - antes, 100.00, places=2)
        con.close()

    def test_retidas_descontam_no_total_final(self):
        con = self._db()
        self._inicio_setembro(con)
        cx.adicionar_retida(con, {"descricao": "Laert Pita", "valor": "1000"})
        s = cx.saldos_do_dia(con, "2026-10-01")
        self.assertAlmostEqual(s["total_final"], s["saldo_total"] - 1000, places=2)
        con.close()

    def test_validacoes(self):
        con = self._db()
        self._inicio_setembro(con)
        with self.assertRaises(cx.ErroCaixaDiario):
            cx.dados_do_formulario({"data": "2026-10-01", "tipo": "RECEITA", "descricao": "x", "valor": "0", "conta": "BB"})
        with self.assertRaises(cx.ErroCaixaDiario):
            cx.dados_do_formulario({"data": "2026-10-01", "tipo": "RECEITA", "descricao": "x", "valor": "10", "conta": "PIX"})
        with self.assertRaises(cx.ErroCaixaDiario):
            cx.dados_do_formulario({"data": "2026-10-01", "tipo": "SAIDA", "descricao": "x", "valor": "10", "conta": "BB"})
        with self.assertRaises(cx.ErroCaixaDiario):
            cx.lancar(con, cx.dados_do_formulario({"data": "2026-09-30", "tipo": "RECEITA", "descricao": "x", "valor": "10",
                                                   "conta": "BB"}), "teste")
        self.assertEqual(cx.dados_do_formulario({"data": "2026-10-01", "tipo": "RECEITA", "descricao": "x", "valor": "1.290,50",
                                                 "conta": "BB"})["valor"], 1290.50)
        con.close()

    def test_planilha_do_dia_tem_as_cores_das_contas(self):
        con = self._db()
        self._inicio_setembro(con)
        self._outubro_01(con)
        buf = cx.relatorio_xlsx(con, "2026-10-01")
        ws = load_workbook(io.BytesIO(buf.getvalue())).active
        cores = {}
        for row in ws.iter_rows(min_col=1, max_col=1):
            cel = row[0]
            if cel.value == "ROSANGELA DOS SANTOS RENAL":
                cores["BB"] = cel.fill.fgColor.rgb
            if cel.value == "FARIDE ALVES MIBI":
                cores["DINHEIRO"] = cel.fill.fgColor.rgb
        self.assertEqual(cores["BB"][-6:], "FFFF99")
        self.assertEqual(cores["DINHEIRO"][-6:], "D0CECE")
        con.close()

    def test_tela_mostra_o_dia_com_as_cores(self):
        c = self.cliente()
        c.post("/caixa-diario/inicio", data={"data": "2026-10-01", "bb": "325514,03", "unicred": "106248,24", "caixa": "36677,24",
                                             "dinheiro": "23800,08", "_csrf": self.token(c)})
        c.post("/caixa-diario/lancar", data={"data": "2026-10-01", "tipo": "RECEITA", "descricao": "ALCIDES PEREIRA MIBI",
                                             "valor": "1295", "conta": "BB", "nf": "737", "_csrf": self.token(c)})
        r = c.get("/caixa-diario?data=2026-10-01")
        html = r.get_data(as_text=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn("ALCIDES PEREIRA MIBI", html)
        self.assertIn("#FFFF99", html)
        self.assertIn(util.moeda(326809.03), html)   # Banco do Brasil: abertura 325.514,03 + 1.295,00 lançados

    def test_tela_e_permissao(self):
        self.criar_usuario("sem_modulo", modulos=["dashboard"])
        c = self.cliente()
        self.assertEqual(c.get("/caixa-diario").status_code, 200)
        self.assertEqual(c.get("/caixa-diario/relatorio.xlsx?data=2026-10-01").status_code, 302)  # sem saldo inicial: volta
        c2 = self.cliente("sem_modulo", "senha123")
        self.assertNotEqual(c2.get("/caixa-diario").status_code, 200)
        c2.get("/")


if __name__ == "__main__":
    unittest.main()
