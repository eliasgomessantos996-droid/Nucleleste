"""Pedidos de compra do estoque: criar e salvar, numeração, sugestão pelo mínimo, enviar, receber (parcial e total),
cancelar, duplicar, PDF, impressão e permissão."""
import unittest

from app import db as dbmod
from tests.test_chat_blindagens import Base


class PedidosTestes(Base):
    def banco(self):
        return dbmod.conectar(self.app.config["DATABASE"])

    def consulta(self, sql, args=()):
        con = self.banco()
        try:
            return [dict(r) for r in con.execute(sql, args)]
        finally:
            con.close()

    def criar_item(self, c, nome, minimo="0", saldo=None, valor=None):
        dados = {"nome": nome, "tipo": "MATERIAL", "unidade": "UN", "estoque_minimo": minimo, "codigo": "", "local": "", "obs": ""}
        if saldo is not None:
            dados["saldo_inicial"] = saldo
        self.assertEqual(self.post(c, "/estoque/item", dados).status_code, 302)
        iid = self.consulta("SELECT id FROM est_itens WHERE nome=?", (nome,))[0]["id"]
        if valor is not None:
            self.post(c, "/estoque/%d/entrada" % iid, {"qtd": "1", "valor_unitario": valor})
        return iid

    def dados_pedido(self, linhas, fornecedor_nome="Forn Pedido", fornecedor_id=""):
        """linhas = [(item_id, qtd, valor)]: o formulário manda listas paralelas."""
        return {"fornecedor_id": fornecedor_id, "fornecedor_nome": fornecedor_nome, "condicoes": "30 dias", "observacao": "obs teste",
                "solicitante": "", "item_id": [str(i) for i, _q, _v in linhas], "qtd": [q for _i, q, _v in linhas],
                "valor_unitario": [v for _i, _q, v in linhas], "item_obs": [""] * len(linhas)}

    def novo_pedido(self, c, linhas, **kw):
        r = self.post(c, "/estoque/pedidos/novo", self.dados_pedido(linhas, **kw))
        self.assertEqual(r.status_code, 302, r.get_data(as_text=True)[:200])
        return self.consulta("SELECT * FROM est_pedidos ORDER BY id DESC LIMIT 1")[0]["id"]

    def pedido(self, pid):
        return self.consulta("SELECT * FROM est_pedidos WHERE id=?", (pid,))[0]

    def linhas(self, pid):
        return self.consulta("SELECT * FROM est_pedido_itens WHERE pedido_id=? ORDER BY id", (pid,))

    def item(self, iid):
        return self.consulta("SELECT * FROM est_itens WHERE id=?", (iid,))[0]

    def criar_fornecedor(self, nome):
        con = self.banco()
        con.execute("INSERT INTO fornecedores (nome, ativo) VALUES (?, 1)", (nome,))
        con.commit()
        fid = con.execute("SELECT id FROM fornecedores WHERE nome=?", (nome,)).fetchone()["id"]
        con.close()
        return fid

    def test_criar_salvar_reabrir_e_editar(self):
        c = self.cliente()
        iid = self.criar_item(c, "LUVA PEDIDO SALVAR")
        pid = self.novo_pedido(c, [(iid, "10", "2,50")])
        ped = self.pedido(pid)
        self.assertEqual(ped["status"], "RASCUNHO")
        self.assertEqual(ped["fornecedor_nome"], "FORN PEDIDO")
        self.assertEqual((self.linhas(pid)[0]["qtd"], self.linhas(pid)[0]["valor_unitario"]), (10, 2.5))
        pagina = self.texto(c.get("/estoque/pedidos/%d" % pid))
        self.assertIn(ped["numero"], pagina)
        self.assertIn("Rascunho", pagina)
        # edita o rascunho: troca a quantidade
        self.post(c, "/estoque/pedidos/%d" % pid, self.dados_pedido([(iid, "12", "2,50")]))
        self.assertEqual(self.linhas(pid)[0]["qtd"], 12)
        self.assertEqual(len(self.linhas(pid)), 1)

    def test_numeracao_sequencial_por_ano(self):
        c = self.cliente()
        iid = self.criar_item(c, "COMPRESSA PEDIDO NUM")
        p1 = self.pedido(self.novo_pedido(c, [(iid, "1", "1")]))["numero"]
        p2 = self.pedido(self.novo_pedido(c, [(iid, "1", "1")]))["numero"]
        ano, seq1 = p1.split("-")
        self.assertEqual(len(seq1), 4)
        self.assertEqual(p2, "%s-%04d" % (ano, int(seq1) + 1))

    def test_validacoes_do_pedido(self):
        c = self.cliente()
        iid = self.criar_item(c, "SORO PEDIDO VALIDA")
        r = self.post(c, "/estoque/pedidos/novo", self.dados_pedido([(iid, "1", "1"), (iid, "2", "1")]))
        self.assertEqual(r.status_code, 200)
        self.assertIn("Item repetido no pedido", self.texto(r))
        r = self.post(c, "/estoque/pedidos/novo", self.dados_pedido([(iid, "0", "1")]))
        self.assertIn("deve ser maior que zero", self.texto(r))
        r = self.post(c, "/estoque/pedidos/novo", self.dados_pedido([]))
        self.assertIn("Inclua pelo menos um item", self.texto(r))

    def test_sugerir_itens_abaixo_do_minimo(self):
        c = self.cliente()
        abaixo = self.criar_item(c, "SUGESTAO PEDIDO ABAIXO", minimo="5", saldo="3", valor="4")   # saldo 3 + entrada 1 = 4
        self.criar_item(c, "SUGESTAO PEDIDO OK", minimo="2", saldo="9")
        self.criar_item(c, "SUGESTAO PEDIDO SEM MINIMO", saldo="1")
        lista = {s["item_id"]: s for s in c.get("/estoque/pedidos/sugestoes").get_json()}
        self.assertIn(abaixo, lista)
        self.assertEqual(lista[abaixo]["qtd"], 6)               # 2 x 5 - 4
        self.assertEqual(lista[abaixo]["valor_unitario"], 4)    # último valor comprado
        nomes = {s["nome"] for s in lista.values()}
        self.assertNotIn("SUGESTAO PEDIDO OK", nomes)
        self.assertNotIn("SUGESTAO PEDIDO SEM MINIMO", nomes)

    def test_enviar_recebimento_parcial_e_total(self):
        c = self.cliente()
        fid = self.criar_fornecedor("FORN PEDIDO REC")
        a = self.criar_item(c, "PEDIDO REC A")
        b = self.criar_item(c, "PEDIDO REC B")
        pid = self.novo_pedido(c, [(a, "4", "2,50"), (b, "2", "10")], fornecedor_id=str(fid), fornecedor_nome="")
        self.post(c, "/estoque/pedidos/%d/enviar" % pid, {})
        self.assertEqual(self.pedido(pid)["status"], "ENVIADO")
        # parcial: chegam 3 de A e nada de B
        self.post(c, "/estoque/pedidos/%d/receber" % pid, {"item_id": [str(a), str(b)], "qtd": ["3", ""],
                                                           "valor_unitario": ["2,60", ""], "documento": "NF 77"})
        self.assertEqual(self.pedido(pid)["status"], "ENVIADO")
        self.assertEqual(self.item(a)["saldo"], 3)
        self.assertEqual(self.item(b)["saldo"], 0)
        self.assertEqual(self.item(a)["ultimo_valor"], 2.6)
        linha_a = [x for x in self.linhas(pid) if x["item_id"] == a][0]
        self.assertEqual(linha_a["qtd_recebida"], 3)
        # o que chegou volta ao pedido como entrada com pedido, fornecedor e nota
        mov = self.consulta("SELECT * FROM est_movimentos WHERE pedido_id=? ORDER BY id", (pid,))
        self.assertEqual([(m["item_id"], m["tipo"], m["qtd"]) for m in mov], [(a, "ENTRADA", 3)])
        self.assertEqual((mov[0]["fornecedor_id"], mov[0]["fornecedor_nome"], mov[0]["documento"]), (fid, "FORN PEDIDO REC", "NF 77"))
        # recebe mais que o que falta: recusa
        r = self.post(c, "/estoque/pedidos/%d/receber" % pid, {"item_id": [str(a)], "qtd": ["5"], "valor_unitario": ["2,60"]})
        self.assertEqual(self.item(a)["saldo"], 3)
        # total: chega o resto de A e todo o B
        self.post(c, "/estoque/pedidos/%d/receber" % pid, {"item_id": [str(a), str(b)], "qtd": ["1", "2"],
                                                           "valor_unitario": ["2,70", "10"], "documento": "NF 78"})
        self.assertEqual(self.pedido(pid)["status"], "RECEBIDO")
        self.assertEqual(self.item(a)["saldo"], 4)
        self.assertEqual(self.item(b)["saldo"], 2)
        self.assertEqual(self.item(a)["ultimo_valor"], 2.7)
        self.assertEqual(len(self.consulta("SELECT id FROM est_movimentos WHERE pedido_id=?", (pid,))), 3)
        # pedido recebido: não recebe de novo, não edita e não cancela
        self.post(c, "/estoque/pedidos/%d/receber" % pid, {"item_id": [str(a)], "qtd": ["1"], "valor_unitario": ["2,70"]})
        self.assertEqual(self.item(a)["saldo"], 4)
        self.post(c, "/estoque/pedidos/%d" % pid, self.dados_pedido([(a, "99", "1")]))
        self.assertEqual(self.linhas(pid)[0]["qtd"], 4)
        self.post(c, "/estoque/pedidos/%d/cancelar" % pid, {})
        self.assertEqual(self.pedido(pid)["status"], "RECEBIDO")

    def test_nao_edita_pedido_enviado_com_recebimento(self):
        c = self.cliente()
        iid = self.criar_item(c, "PEDIDO PARCIAL EDITA")
        pid = self.novo_pedido(c, [(iid, "5", "1")])
        self.post(c, "/estoque/pedidos/%d/enviar" % pid, {})
        self.post(c, "/estoque/pedidos/%d/receber" % pid, {"item_id": [str(iid)], "qtd": ["2"], "valor_unitario": ["1"]})
        self.post(c, "/estoque/pedidos/%d" % pid, self.dados_pedido([(iid, "9", "1")]))
        self.assertEqual(self.linhas(pid)[0]["qtd"], 5)

    def test_cancelar_e_duplicar(self):
        c = self.cliente()
        a = self.criar_item(c, "PEDIDO CANCELA A")
        b = self.criar_item(c, "PEDIDO CANCELA B")
        pid = self.novo_pedido(c, [(a, "2", "3"), (b, "1", "")])
        dup = self.novo_pedido(c, [(a, "1", "1")])
        self.post(c, "/estoque/pedidos/%d/cancelar" % pid, {})
        self.assertEqual(self.pedido(pid)["status"], "CANCELADO")
        self.post(c, "/estoque/pedidos/%d/cancelar" % pid, {})   # já cancelado: nada muda
        self.assertEqual(self.pedido(pid)["status"], "CANCELADO")
        # duplicar cria um rascunho novo com os mesmos itens
        self.post(c, "/estoque/pedidos/%d/duplicar" % dup, {})
        novo = self.consulta("SELECT * FROM est_pedidos ORDER BY id DESC LIMIT 1")[0]
        self.assertEqual(novo["status"], "RASCUNHO")
        self.assertNotEqual(novo["numero"], self.pedido(dup)["numero"])
        self.assertEqual([(x["item_id"], x["qtd"]) for x in self.linhas(novo["id"])], [(a, 1)])
        self.post(c, "/estoque/pedidos/%d/duplicar" % pid, {})
        novo2 = self.consulta("SELECT * FROM est_pedidos ORDER BY id DESC LIMIT 1")[0]
        self.assertEqual(sorted((x["item_id"], x["qtd"]) for x in self.linhas(novo2["id"])), sorted([(a, 2), (b, 1)]))

    def test_pdf_e_impressao(self):
        c = self.cliente()
        iid = self.criar_item(c, "PEDIDO PDF ITEM")
        pid = self.novo_pedido(c, [(iid, "3", "1,50")], fornecedor_nome="Forn PDF")
        r = c.get("/estoque/pedidos/%d.pdf" % pid)
        self.assertEqual((r.status_code, r.mimetype), (200, "application/pdf"))
        self.assertTrue(r.data.startswith(b"%PDF"))
        self.assertIn("inline", r.headers.get("Content-Disposition", ""))
        r = c.get("/estoque/pedidos/%d.pdf?baixar=1" % pid)
        self.assertIn("attachment", r.headers.get("Content-Disposition", ""))
        r = c.get("/estoque/pedidos/%d/imprimir" % pid)
        self.assertEqual(r.status_code, 200)
        self.assertIn("Pedido de compra", self.texto(r))
        self.assertIn("PEDIDO PDF ITEM", self.texto(r))
        self.assertEqual(c.get("/estoque/pedidos/999999.pdf").status_code, 404)
        self.assertEqual(c.get("/estoque/pedidos/999999/imprimir").status_code, 404)

    def test_lista_com_filtro(self):
        c = self.cliente()
        iid = self.criar_item(c, "PEDIDO LISTA ITEM")
        pid = self.novo_pedido(c, [(iid, "1", "1")])
        self.assertIn(self.pedido(pid)["numero"], self.texto(c.get("/estoque/pedidos")))
        self.assertEqual(c.get("/estoque/pedidos?status=CANCELADO").status_code, 200)
        self.assertEqual(c.get("/estoque/pedidos/novo").status_code, 200)

    def test_permissoes_do_modulo(self):
        self.criar_usuario("PED_SEM_MODULO", ["dashboard"])
        self.criar_usuario("PED_COM_MODULO", ["estoque"])
        sem = self.cliente("PED_SEM_MODULO", "senha123")
        com = self.cliente("PED_COM_MODULO", "senha123")
        self.assertEqual(sem.get("/estoque/pedidos").status_code, 302)
        self.assertEqual(sem.get("/estoque/pedidos/sugestoes").status_code, 302)
        self.assertEqual(sem.get("/estoque/pedidos/1.pdf").status_code, 302)
        self.assertEqual(com.get("/estoque/pedidos").status_code, 200)


if __name__ == "__main__":
    unittest.main()
