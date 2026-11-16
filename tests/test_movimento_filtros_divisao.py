"""Movimento de caixa: lançamentos só do usuário e do dia (com outra data à escolha), pagamento dividido em duas formas
(dinheiro + PIX) e relatório de fechamento visível só para o dono (e para a gestão)."""
import unittest
from datetime import date, timedelta

from app import db as dbmod
from app import movimento
from tests.test_chat_blindagens import Base


class Ajudas(Base):
    def caixa(self, cliente, valor, convenio="PARTICULAR", usuario="ATENDENTE"):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            cur = con.execute("INSERT INTO caixa (data, cliente, procedimento, convenio, status, usuario, valor) "
                              "VALUES (?,?,?,?,?,?,?)", (date.today().isoformat(), cliente, "MIBI", convenio, "ABERTO", usuario, valor))
            con.commit()
            return cur.lastrowid
        finally:
            con.close()

    def linha(self, cid):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            return dict(con.execute("SELECT * FROM caixa WHERE id=?", (cid,)).fetchone())
        finally:
            con.close()

    def receber(self, c, cid, valor, forma, recebido=None, nf="1"):
        dados = {"valor": valor, "forma": forma, "nota_fiscal": nf}
        if recebido is not None:
            dados["recebido"] = recebido
        return self.post(c, f"/movimento-caixa/receber/{cid}", dados)

    def contar(self, sql, params=()):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            return con.execute(sql, params).fetchone()[0]
        finally:
            con.close()


class Filtros(Ajudas):
    def _caixa_em(self, cliente, valor, dia, usuario):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            cur = con.execute("INSERT INTO caixa (data, cliente, procedimento, convenio, status, usuario, valor) "
                              "VALUES (?,?,?,?,?,?,?)", (dia, cliente, "MIBI", "PARTICULAR", "ABERTO", usuario, valor))
            con.commit()
            return cur.lastrowid
        finally:
            con.close()

    def test_lista_so_do_usuario_e_so_do_dia_com_outra_data_a_escolha(self):
        self.criar_usuario("FIL_A", ["movimento_caixa"])
        self.criar_usuario("FIL_B", ["movimento_caixa"])
        hoje = date.today().isoformat()
        ontem = (date.today() - timedelta(days=1)).isoformat()
        self._caixa_em("CLIENTE DA ANA HOJE", 10, hoje, "FIL_A")
        self._caixa_em("CLIENTE DA ANA ONTEM", 10, ontem, "FIL_A")
        self._caixa_em("CLIENTE DO BETO HOJE", 10, hoje, "FIL_B")
        pagina = self.texto(self.cliente("FIL_A", "senha123").get("/movimento-caixa"))
        self.assertIn("CLIENTE DA ANA HOJE", pagina)
        self.assertNotIn("CLIENTE DA ANA ONTEM", pagina)       # só o dia
        self.assertNotIn("CLIENTE DO BETO HOJE", pagina)       # só o que ele lançou
        outra = self.texto(self.cliente("FIL_A", "senha123").get("/movimento-caixa?dia=" + ontem))
        self.assertIn("CLIENTE DA ANA ONTEM", outra)
        self.assertNotIn("CLIENTE DA ANA HOJE", outra)
        todas = self.texto(self.cliente("FIL_A", "senha123").get("/movimento-caixa?dia=todas"))
        self.assertIn("CLIENTE DA ANA ONTEM", todas)
        self.assertIn("CLIENTE DA ANA HOJE", todas)

    def test_gerencia_ve_so_os_proprios_ate_pedir_todos(self):
        self.criar_usuario("FIL_C", ["movimento_caixa"])
        hoje = date.today().isoformat()
        self._caixa_em("CLIENTE DA CLARA", 10, hoje, "FIL_C")
        adm = self.cliente()
        self.assertNotIn("CLIENTE DA CLARA", self.texto(adm.get("/movimento-caixa")))
        self.assertIn("CLIENTE DA CLARA", self.texto(adm.get("/movimento-caixa?usuarios=todos")))
        # quem não é da gestão não consegue ver os dos outros nem pedindo
        self.criar_usuario("FIL_D", ["movimento_caixa"])
        self.assertNotIn("CLIENTE DA CLARA", self.texto(self.cliente("FIL_D", "senha123").get("/movimento-caixa?usuarios=todos")))

    def test_relatorio_de_fechamento_e_so_do_dono_ou_da_gestao(self):
        self.criar_usuario("FIL_E", ["movimento_caixa"])
        self.criar_usuario("FIL_F", ["movimento_caixa"])
        dono = self.cliente("FIL_E", "senha123")
        self.post(dono, "/movimento-caixa/abrir", {"fundo": "0"})
        sid = self.contar("SELECT id FROM caixa_sessoes WHERE usuario='FIL_E'")
        self.assertEqual(dono.get(f"/movimento-caixa/relatorio/{sid}").status_code, 200)
        self.assertEqual(self.cliente("FIL_F", "senha123").get(f"/movimento-caixa/relatorio/{sid}").status_code, 404)
        self.assertEqual(self.cliente("FIL_F", "senha123").get(f"/movimento-caixa/relatorio/{sid}.pdf").status_code, 404)
        self.assertEqual(self.cliente().get(f"/movimento-caixa/relatorio/{sid}").status_code, 200)


class PagamentoDividido(Ajudas):
    def _abrir(self, nome):
        self.criar_usuario(nome, ["movimento_caixa"])
        c = self.cliente(nome, "senha123")
        self.post(c, "/movimento-caixa/abrir", {"fundo": "10,00"})
        return c

    def test_dinheiro_mais_pix_num_so_recebimento(self):
        c = self._abrir("DIV_A")
        cid = self.caixa("DIVIDIDA", 100, usuario="DIV_A")
        self.post(c, f"/movimento-caixa/receber/{cid}", {"valor": "100,00", "forma": "DINHEIRO", "recebido": "50,00",
                                                         "nota_fiscal": "900", "forma2": "PIX", "valor2": "60,00"})
        r = self.linha(cid)
        self.assertEqual((r["status"], r["forma_pagamento"], r["forma_pagamento2"], r["valor_pagamento2"]), ("PAGO", "DINHEIRO", "PIX", 60.0))
        self.assertEqual((r["valor"], r["troco"]), (100.0, 10.0))      # 40 em dinheiro, 50 entregues
        sid = self.contar("SELECT id FROM caixa_sessoes WHERE usuario='DIV_A'")
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            rel = movimento.relatorio(con, sid)
        finally:
            con.close()
        self.assertEqual((rel["dinheiro_devido"], rel["dinheiro_recebido"], rel["troco"], rel["dinheiro_liquido"]), (40.0, 50.0, 10.0, 40.0))
        self.assertEqual((rel["pix_total"], rel["total"], rel["quantidade"]), (60.0, 100.0, 1))
        self.assertEqual(rel["esperado_dinheiro"], 50.0)                # fundo 10 + 40
        self.assertEqual(c.get(f"/movimento-caixa/relatorio/{sid}.pdf").data[:4], b"%PDF")
        q = self.texto(c.get(f"/movimento-caixa/quitacao/{cid}"))
        self.assertIn("Pix", q)
        self.assertIn("Dinheiro", q)

    def test_pix_primeiro_e_dinheiro_na_segunda_forma(self):
        c = self._abrir("DIV_B")
        cid = self.caixa("INVERTIDA", 100, usuario="DIV_B")
        self.post(c, f"/movimento-caixa/receber/{cid}", {"valor": "100,00", "forma": "PIX", "recebido": "50,00",
                                                         "nota_fiscal": "901", "forma2": "DINHEIRO", "valor2": "30,00"})
        r = self.linha(cid)
        self.assertEqual((r["status"], r["troco"]), ("PAGO", 20.0))     # 30 em dinheiro, 50 entregues
        sid = self.contar("SELECT id FROM caixa_sessoes WHERE usuario='DIV_B'")
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            rel = movimento.relatorio(con, sid)
        finally:
            con.close()
        self.assertEqual((rel["dinheiro_devido"], rel["pix_total"], rel["dinheiro_liquido"]), (30.0, 70.0, 30.0))

    def test_recusa_formas_iguais_e_valor_invalido(self):
        c = self._abrir("DIV_C")
        cid = self.caixa("RECUSADA", 100, usuario="DIV_C")
        base = {"valor": "100,00", "forma": "PIX", "nota_fiscal": "902"}
        for extra in ({"forma2": "PIX", "valor2": "10,00"}, {"forma2": "DINHEIRO", "valor2": "0"},
                      {"forma2": "DINHEIRO", "valor2": "100,00"}, {"forma2": "DINHEIRO", "valor2": ""},
                      {"forma2": "DINHEIRO", "valor2": "30,00", "recebido": "20,00"}):
            self.post(c, f"/movimento-caixa/receber/{cid}", dict(base, **extra))
            self.assertEqual(self.linha(cid)["status"], "ABERTO", extra)

    def test_pagamento_simples_continua_igual(self):
        c = self._abrir("DIV_D")
        cid = self.caixa("SIMPLES", 80, usuario="DIV_D")
        self.receber(c, cid, "80,00", "DINHEIRO", "100,00", nf="903")
        r = self.linha(cid)
        self.assertEqual((r["forma_pagamento2"], r["valor_pagamento2"], r["troco"]), (None, None, 20.0))


if __name__ == "__main__":
    unittest.main()
