"""Versão 1.5.9: lotes de pagamento do contas a pagar (marcar contas, gerar lote, quitar, devolver e reabrir)."""
import re
import unittest

from app import db as dbmod
from tests.test_chat_blindagens import Base


class LotesPagamento(Base):
    def conta(self, c, descricao, valor="100,00"):
        self.post(c, "/contas/nova", {"descricao": descricao, "categoria": "Material de escritório",
                                      "vencimento": "2026-11-10", "valor": valor})
        return self.consulta("SELECT id FROM contas WHERE descricao=?", (descricao,))[0]["id"]

    def consulta(self, sql, params=()):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            return [dict(r) for r in con.execute(sql, params)]
        finally:
            con.close()

    def gerar_lote(self, c, ids, banco="UNICRED"):
        r = self.post(c, "/contas/imprimir", {"ids": [str(i) for i in ids], "banco": banco})
        self.assertEqual(r.status_code, 302)
        return int(re.search(r"/contas/lotes/(\d+)", r.headers["Location"]).group(1))

    def acao_lote(self, c, lote_id, dados, follow=False):
        return self.post(c, "/contas/lotes/%d/acao" % lote_id, dados, follow_redirects=follow)

    def test_lote_tira_contas_da_lista_normal(self):
        c = self.cliente()
        a, b, d = (self.conta(c, nome) for nome in ("LOTE UM ALFA", "LOTE UM BETA", "LOTE UM DELTA"))
        fora = self.conta(c, "LOTE UM FORA")
        lote = self.gerar_lote(c, [a, b, d])
        self.assertNotIn("LOTE UM ALFA", self.texto(c.get("/contas?status=ABERTO")))
        self.assertIn("LOTE UM FORA", self.texto(c.get("/contas?status=ABERTO")))
        em_lote = self.texto(c.get("/contas?status=LOTE"))
        self.assertIn("LOTE UM ALFA", em_lote)
        self.assertIn("Lote nº %d" % lote, em_lote)
        self.assertNotIn("LOTE UM FORA", em_lote)
        cab = self.consulta("SELECT * FROM contas_lotes WHERE id=?", (lote,))[0]
        self.assertEqual((cab["banco"], cab["status"]), ("UNICRED", "ABERTO"))
        itens = self.consulta("SELECT situacao FROM contas_lote_itens WHERE lote_id=?", (lote,))
        self.assertEqual([i["situacao"] for i in itens], ["EM PAGAMENTO"] * 3)
        self.assertEqual(self.consulta("SELECT lote_id FROM contas WHERE id=?", (fora,))[0]["lote_id"], None)

    def test_conta_ja_em_lote_nao_entra_em_outro(self):
        c = self.cliente()
        a = self.conta(c, "OUTRO LOTE ALFA")
        lote = self.gerar_lote(c, [a])
        r = self.post(c, "/contas/imprimir", {"ids": [str(a)], "banco": "CAIXA"}, follow_redirects=True)
        self.assertIn("Nenhuma das contas marcadas está disponível", self.texto(r))
        self.assertEqual(self.consulta("SELECT lote_id FROM contas WHERE id=?", (a,))[0]["lote_id"], lote)
        self.assertEqual(len(self.consulta("SELECT id FROM contas_lote_itens WHERE conta_id=?", (a,))), 1)

    def test_quitar_marcadas_e_devolver(self):
        c = self.cliente()
        x, y, z = (self.conta(c, nome) for nome in ("QUITA XIS", "QUITA IPSILON", "QUITA ZETA"))
        lote = self.gerar_lote(c, [x, y, z])
        self.acao_lote(c, lote, {"acao": "quitar_marcadas", "ids": [str(x)], "banco": "UNICRED",
                                 "data_pagamento": "2026-11-12", "forma_pagamento": "PIX"})
        pago = self.consulta("SELECT * FROM contas WHERE id=?", (x,))[0]
        self.assertEqual((pago["status"], pago["banco_pagamento"], pago["data_pagamento"], pago["forma_pagamento"]),
                         ("PAGO", "UNICRED", "2026-11-12", "PIX"))
        self.assertEqual(self.consulta("SELECT situacao FROM contas_lote_itens WHERE conta_id=?", (x,))[0]["situacao"], "PAGA")
        self.assertEqual(self.consulta("SELECT status FROM contas_lotes WHERE id=?", (lote,))[0]["status"], "ABERTO")
        # devolve uma das pendentes: volta para a lista normal
        self.acao_lote(c, lote, {"acao": "devolver", "ids": [str(y)]})
        self.assertEqual(self.consulta("SELECT situacao FROM contas_lote_itens WHERE conta_id=?", (y,))[0]["situacao"], "DEVOLVIDA")
        self.assertIsNone(self.consulta("SELECT lote_id FROM contas WHERE id=?", (y,))[0]["lote_id"])
        self.assertEqual(self.consulta("SELECT status FROM contas WHERE id=?", (y,))[0]["status"], "ABERTO")
        self.assertIn("QUITA IPSILON", self.texto(c.get("/contas?status=ABERTO")))
        self.assertNotIn("QUITA IPSILON", self.texto(c.get("/contas?status=LOTE")))
        # não há mais marcada pendente: a ação responde com erro e nada muda
        self.acao_lote(c, lote, {"acao": "devolver", "ids": [str(x)]})
        self.assertEqual(self.consulta("SELECT status FROM contas WHERE id=?", (x,))[0]["status"], "PAGO")

    def test_quitar_todas_conclui_o_lote(self):
        c = self.cliente()
        p, q = self.conta(c, "TODAS UM"), self.conta(c, "TODAS DOIS")
        lote = self.gerar_lote(c, [p, q])
        self.acao_lote(c, lote, {"acao": "quitar_todas", "banco": "DINHEIRO", "data_pagamento": "2026-11-13"})
        for cid in (p, q):
            conta = self.consulta("SELECT status, banco_pagamento FROM contas WHERE id=?", (cid,))[0]
            self.assertEqual((conta["status"], conta["banco_pagamento"]), ("PAGO", "DINHEIRO"))
        cab = self.consulta("SELECT status, concluido_em FROM contas_lotes WHERE id=?", (lote,))[0]
        self.assertEqual(cab["status"], "CONCLUIDO")
        self.assertTrue(cab["concluido_em"])
        r = self.texto(c.get("/contas/lotes?status=CONCLUIDO"))
        self.assertIn("Lote nº %d" % lote, r)

    def test_reabrir_conta_paga_volta_para_lista(self):
        c = self.cliente()
        k = self.conta(c, "REABRIR KAPPA")
        lote = self.gerar_lote(c, [k])
        self.post(c, "/contas/%d/quitar" % k, {"banco": "CAIXA", "data_pagamento": "2026-11-14", "forma_pagamento": ""})
        self.assertEqual(self.consulta("SELECT status FROM contas WHERE id=?", (k,))[0]["status"], "PAGO")
        self.post(c, "/contas/%d/reabrir" % k)
        conta = self.consulta("SELECT status, lote_id FROM contas WHERE id=?", (k,))[0]
        self.assertEqual((conta["status"], conta["lote_id"]), ("ABERTO", None))
        self.assertEqual(self.consulta("SELECT situacao FROM contas_lote_itens WHERE conta_id=?", (k,))[0]["situacao"], "DEVOLVIDA")
        self.assertEqual(self.consulta("SELECT status FROM contas_lotes WHERE id=?", (lote,))[0]["status"], "CONCLUIDO")
        self.assertIn("REABRIR KAPPA", self.texto(c.get("/contas?status=ABERTO")))

    def test_banco_invalido_nao_quita(self):
        c = self.cliente()
        m = self.conta(c, "BANCO ERRADO")
        lote = self.gerar_lote(c, [m])
        r = self.acao_lote(c, lote, {"acao": "quitar_todas", "banco": "BANCO INVENTADO"}, follow=True)
        self.assertIn("É obrigatório selecionar o banco para a quitação!", self.texto(r))
        self.assertEqual(self.consulta("SELECT status FROM contas WHERE id=?", (m,))[0]["status"], "ABERTO")
        self.assertEqual(self.consulta("SELECT situacao FROM contas_lote_itens WHERE conta_id=?", (m,))[0]["situacao"], "EM PAGAMENTO")

    def test_telas_e_impressao_do_lote(self):
        c = self.cliente()
        n = self.conta(c, "IMPRESSAO NU")
        lote = self.gerar_lote(c, [n])
        self.assertEqual(c.get("/contas/lotes").status_code, 200)
        self.assertEqual(c.get("/contas/lotes/%d" % lote).status_code, 200)
        self.assertEqual(c.get("/contas/lotes/999999").status_code, 404)
        imp = c.get("/contas/lotes/%d/imprimir" % lote)
        self.assertEqual(imp.status_code, 200)
        self.assertIn("Lote nº %d" % lote, self.texto(imp))
        self.assertIn("IMPRESSAO NU", self.texto(imp))


if __name__ == "__main__":
    unittest.main()
