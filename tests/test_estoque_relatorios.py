"""Relatórios do estoque, escrituração e estudo de preços: contas, páginas, PDF/Excel e permissão."""
import unittest

from app import db as dbmod
from app import estoque_relatorios as er
from tests.test_chat_blindagens import Base

SEM_MOD = "REL_SEM_MODULO"
COM_MOD = "REL_COM_MODULO"


class RelatoriosEstoqueTestes(Base):
    def banco(self):
        return dbmod.conectar(self.app.config["DATABASE"])

    def criar_item(self, c, nome, saldo=None, minimo="0", tipo="MATERIAL"):
        dados = {"nome": nome, "tipo": tipo, "unidade": "UN", "estoque_minimo": minimo}
        if saldo is not None:
            dados["saldo_inicial"] = saldo
        r = self.post(c, "/estoque/item", dados)
        self.assertEqual(r.status_code, 302, self.texto(r)[:200])
        con = self.banco()
        try:
            return con.execute("SELECT id FROM est_itens WHERE nome=?", (nome,)).fetchone()["id"]
        finally:
            con.close()

    def criar_fornecedor(self, nome):
        con = self.banco()
        con.execute("INSERT INTO fornecedores (nome, ativo) VALUES (?, 1)", (nome,))
        con.commit()
        fid = con.execute("SELECT id FROM fornecedores WHERE nome=?", (nome,)).fetchone()["id"]
        con.close()
        return fid

    def movs(self, iid):
        con = self.banco()
        try:
            return [r["id"] for r in con.execute("SELECT id FROM est_movimentos WHERE item_id=? ORDER BY id", (iid,))]
        finally:
            con.close()

    def data_mov(self, mid, dh):
        con = self.banco()
        con.execute("UPDATE est_movimentos SET data_hora=? WHERE id=?", (dh, mid))
        con.commit()
        con.close()

    def consulta(self, sql, params=()):
        con = self.banco()
        try:
            return [dict(r) for r in con.execute(sql, params)]
        finally:
            con.close()

    # ------------------------------------------------------------ posição
    def test_posicao_e_valor_em_estoque(self):
        c = self.cliente()
        a = self.criar_item(c, "REL POSICAO A", saldo="10")
        self.criar_item(c, "REL POSICAO ZERO")
        r = self.post(c, "/estoque/%d/entrada" % a, {"qtd": "5", "valor_unitario": "2,00"})
        self.assertEqual(r.status_code, 302)
        con = self.banco()
        try:
            linhas, total = er.posicao(con)
        finally:
            con.close()
        pos = {l["nome"]: l for l in linhas}
        self.assertEqual(pos["REL POSICAO A"]["saldo"], 15)
        self.assertEqual(pos["REL POSICAO A"]["valor"], 30.0)            # 15 x 2,00
        self.assertEqual(pos["REL POSICAO ZERO"]["situacao"], "zerado")
        self.assertEqual(pos["REL POSICAO ZERO"]["valor"], 0)
        self.assertGreaterEqual(total, 30.0)

    def test_abaixo_do_minimo_mostra_o_que_falta(self):
        c = self.cliente()
        iid = self.criar_item(c, "REL MINIMO", saldo="3", minimo="10")
        con = self.banco()
        try:
            abaixo = {i["id"]: i for i in er.abaixo_minimo(con)}
        finally:
            con.close()
        self.assertIn(iid, abaixo)
        self.assertEqual(abaixo[iid]["falta"], 7)

    # ------------------------------------------------------------ movimentação
    def test_movimentacao_por_periodo_e_motivo(self):
        c = self.cliente()
        iid = self.criar_item(c, "REL MOVIMENTO", saldo="10")
        m_inicial = self.movs(iid)[0]
        self.data_mov(m_inicial, "2026-01-05 08:00:00")
        self.assertEqual(self.post(c, "/estoque/%d/entrada" % iid, {"qtd": "5", "valor_unitario": "1"}).status_code, 302)
        self.assertEqual(self.post(c, "/estoque/%d/saida" % iid, {"qtd": "3", "motivo": "Uso"}).status_code, 302)
        self.assertEqual(self.post(c, "/estoque/%d/saida" % iid, {"qtd": "1", "motivo": "Perda"}).status_code, 302)
        m = self.movs(iid)
        self.data_mov(m[1], "2026-02-10 09:00:00")      # entrada de fevereiro
        self.data_mov(m[2], "2026-02-11 09:00:00")      # uso
        self.data_mov(m[3], "2026-02-12 09:00:00")      # perda
        con = self.banco()
        try:
            fev = er.movimentacao(con, "2026-02-01", "2026-02-28")
            tudo = er.movimentacao(con, "", "")
        finally:
            con.close()
        linha = [i for i in fev["itens"] if i["id"] == iid][0]
        self.assertEqual((linha["entradas"], linha["saidas"], linha["saldo"]), (5, 4, 1))
        self.assertEqual(linha["motivos"]["Uso"], 3)
        self.assertEqual(linha["motivos"]["Perda"], 1)
        linha_tudo = [i for i in tudo["itens"] if i["id"] == iid][0]
        self.assertEqual((linha_tudo["entradas"], linha_tudo["saidas"]), (15, 4))

    # ------------------------------------------------------------ escrituração
    def test_escrituracao_fecha_com_ajustes_e_periodo_apos_movimentos_antigos(self):
        c = self.cliente()
        iid = self.criar_item(c, "REL ESCRITURA", saldo="10")
        self.data_mov(self.movs(iid)[0], "2026-01-05 08:00:00")          # saldo inicial de janeiro
        self.post(c, "/estoque/%d/entrada" % iid, {"qtd": "5"})                # fevereiro: entrada 5
        self.post(c, "/estoque/%d/ajuste" % iid, {"contagem": "17", "obs": "Contagem a mais"})   # +2
        self.post(c, "/estoque/%d/saida" % iid, {"qtd": "4", "motivo": "Uso"})                  # saída 4
        self.post(c, "/estoque/%d/ajuste" % iid, {"contagem": "9", "obs": "Quebra de frasco"})   # -4
        m = self.movs(iid)
        for mid, dh in zip(m[1:], ["2026-02-10 08:00:00", "2026-02-11 08:00:00", "2026-02-12 08:00:00", "2026-02-13 08:00:00"]):
            self.data_mov(mid, dh)
        con = self.banco()
        try:
            blocos = er.escrituracao(con, "2026-02-01", "2026-02-28", iid)
            todo = er.escrituracao(con, "", "", iid)
        finally:
            con.close()
        b = blocos[0]
        self.assertEqual(b["inicial"], 10)                 # o que existia antes de fevereiro
        self.assertEqual((b["entradas"], b["saidas"]), (7, 8))   # entrada 5 + ajuste +2 ; saída 4 + ajuste -4
        self.assertEqual(b["final"], 9)
        self.assertEqual(b["inicial"] + b["entradas"] - b["saidas"], b["final"])
        self.assertTrue(b["confere"])
        self.assertEqual([l["entrada"] for l in b["linhas"]], [5, 2, 0, 0])
        self.assertEqual([l["saida"] for l in b["linhas"]], [0, 0, 4, 4])
        self.assertEqual([l["saldo"] for l in b["linhas"]], [15, 17, 13, 9])
        self.assertEqual(todo[0]["inicial"], 0)            # sem De, começa do zero
        self.assertEqual(todo[0]["final"], 9)

    # ------------------------------------------------------------ preços
    def test_estudo_de_precos_com_dois_fornecedores(self):
        c = self.cliente()
        f1 = self.criar_fornecedor("REL FORNECEDOR UM")
        f2 = self.criar_fornecedor("REL FORNECEDOR DOIS")
        iid = self.criar_item(c, "REL PRECO")
        self.post(c, "/estoque/%d/entrada" % iid, {"qtd": "10", "valor_unitario": "5,00", "fornecedor_id": str(f1)})
        self.post(c, "/estoque/%d/entrada" % iid, {"qtd": "10", "valor_unitario": "4,00", "fornecedor_id": str(f2)})
        self.post(c, "/estoque/%d/entrada" % iid, {"qtd": "10", "valor_unitario": "6,00", "fornecedor_id": str(f1)})
        m = self.movs(iid)
        for mid, dh in zip(m, ["2026-01-05 08:00:00", "2026-02-10 08:00:00", "2026-02-20 08:00:00"]):
            self.data_mov(mid, dh)
        con = self.banco()
        try:
            item = [a for a in er.estudo(con) if a["iid"] == iid][0]
            so_f2 = [a for a in er.estudo(con, fornecedor="f:%d" % f2) if a["iid"] == iid][0]
        finally:
            con.close()
        self.assertEqual(item["ultimo"], 6.0)
        self.assertEqual(item["ultimo_fornecedor"], "REL FORNECEDOR UM")
        self.assertEqual((item["menor"], item["maior"]), (4.0, 6.0))
        self.assertEqual(item["media"], 5.0)               # (5 + 4 + 6) / 3
        self.assertEqual(item["variacao"], 50.0)           # de 4,00 para 6,00
        self.assertEqual(item["compras"], 3)
        self.assertEqual(item["mais_barato"]["nome"], "REL FORNECEDOR DOIS")
        self.assertEqual(item["mais_barato"]["ultimo"], 4.0)
        self.assertEqual(len(item["comparativo"]), 2)
        self.assertEqual(so_f2["compras"], 1)
        self.assertEqual(so_f2["ultimo"], 4.0)

    # ------------------------------------------------------------ páginas, PDF e Excel
    def test_paginas_pdf_e_excel_respondem(self):
        c = self.cliente()
        iid = self.criar_item(c, "REL PAGINAS", saldo="4", minimo="6")
        self.assertEqual(self.post(c, "/estoque/%d/entrada" % iid, {"qtd": "1", "valor_unitario": "3", "validade": "2026-11-10",
                                                                    "lote": "L1"}).status_code, 302)
        for url in ["/estoque/relatorios", "/estoque/escrituracao", "/estoque/precos"]:
            self.assertEqual(c.get(url).status_code, 200, url)
        for url in ["/estoque/relatorios.pdf", "/estoque/escrituracao.pdf", "/estoque/precos.pdf"]:
            r = c.get(url)
            self.assertEqual(r.status_code, 200, url)
            self.assertTrue(r.data.startswith(b"%PDF"), url)
        for url in ["/estoque/relatorios.xlsx", "/estoque/escrituracao.xlsx", "/estoque/precos.xlsx"]:
            r = c.get(url)
            self.assertEqual(r.status_code, 200, url)
            self.assertTrue(r.data.startswith(b"PK"), url)
        self.assertEqual(c.get("/estoque/precos?item=%d" % iid).status_code, 200)
        self.assertIn("REL PAGINAS", self.texto(c.get("/estoque/relatorios")))

    def test_validade_proxima_entra_no_relatorio(self):
        c = self.cliente()
        iid = self.criar_item(c, "REL VALIDADE", saldo="2")
        self.post(c, "/estoque/%d/entrada" % iid, {"qtd": "1", "validade": "2000-01-01", "lote": "VENCIDO1"})
        con = self.banco()
        try:
            venc = [v for v in er.validades(con) if v["id"] == iid]
        finally:
            con.close()
        self.assertEqual(len(venc), 1)
        self.assertTrue(venc[0]["vencido"])

    # ------------------------------------------------------------ permissão
    def test_permissao_do_modulo(self):
        self.criar_usuario(SEM_MOD, ["dashboard"])
        self.criar_usuario(COM_MOD, ["estoque"])
        sem = self.cliente(SEM_MOD, "senha123")
        com = self.cliente(COM_MOD, "senha123")
        for url in ["/estoque/relatorios", "/estoque/relatorios.pdf", "/estoque/relatorios.xlsx", "/estoque/escrituracao",
                    "/estoque/escrituracao.pdf", "/estoque/precos", "/estoque/precos.pdf", "/estoque/precos.xlsx"]:
            self.assertEqual(sem.get(url).status_code, 302, url)
            self.assertEqual(com.get(url).status_code, 200, url)


if __name__ == "__main__":
    unittest.main()
