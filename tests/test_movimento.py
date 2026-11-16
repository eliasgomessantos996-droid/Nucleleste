"""Movimento de caixa: abertura e fechamento diário, recebimentos com troco e quitação, bloqueio por caixa de outra data,
alerta pelo contato do sistema, relatório para assinatura e correção de caixa fechado só pela gestão."""
import unittest
from datetime import date, timedelta

from app import movimento
from app import db as dbmod
from tests.test_chat_blindagens import Base


class MovimentoTestes(Base):
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

    def test_recebe_com_troco_pix_e_quitacao(self):
        self.criar_usuario("MOV_A", ["movimento_caixa"])
        c = self.cliente("MOV_A", "senha123")
        cid1 = self.caixa("ANA", 80, usuario="MOV_A")
        cid2 = self.caixa("BIA", 50, usuario="MOV_A")
        self.receber(c, cid1, "80,00", "DINHEIRO", "100,00")  # sem caixa aberto, não recebe
        self.assertEqual(self.linha(cid1)["status"], "ABERTO")
        self.post(c, "/movimento-caixa/abrir", {"fundo": "50,00"})
        self.assertEqual(self.contar("SELECT COUNT(*) FROM caixa_sessoes WHERE usuario='MOV_A' AND status='ABERTO'"), 1)
        self.receber(c, cid1, "80,00", "DINHEIRO", "100,00", nf="")  # sem nota fiscal, não recebe
        self.assertEqual(self.linha(cid1)["status"], "ABERTO")
        self.receber(c, cid1, "80,00", "DINHEIRO", "100,00", nf="555")
        r1 = self.linha(cid1)
        self.assertEqual((r1["status"], r1["forma_pagamento"], r1["nota_fiscal"]), ("PAGO", "DINHEIRO", "555"))
        self.assertEqual((r1["valor_recebido"], r1["troco"]), (100.0, 20.0))
        self.assertIsNotNone(r1["sessao_id"])
        self.receber(c, cid2, "50,00", "PIX", nf="556")
        r2 = self.linha(cid2)
        self.assertEqual((r2["status"], r2["forma_pagamento"], r2["troco"]), ("PAGO", "PIX", 0.0))
        q = c.get(f"/movimento-caixa/quitacao/{cid1}")
        self.assertEqual(q.status_code, 200)
        self.assertIn("Quitação de pagamento", self.texto(q))
        self.assertIn("555", self.texto(q))

    def test_caixa_de_outra_data_bloqueia_e_avisa(self):
        uid = self.criar_usuario("MOV_B", ["movimento_caixa"])
        ontem = (date.today() - timedelta(days=1)).isoformat()
        con = dbmod.conectar(self.app.config["DATABASE"])
        con.execute("INSERT INTO caixa_sessoes (usuario, data, fundo, status, aberto_em) VALUES ('MOV_B', ?, 0, 'ABERTO', ?)",
                    (ontem, ontem + " 08:00:00"))
        con.commit()
        con.close()
        c = self.cliente("MOV_B", "senha123")
        cid = self.caixa("CARLA", 30, usuario="MOV_B")
        self.post(c, "/movimento-caixa/abrir", {"fundo": "0"})
        self.assertEqual(self.contar("SELECT COUNT(*) FROM caixa_sessoes WHERE usuario='MOV_B' AND data=?", (date.today().isoformat(),)), 0)
        self.receber(c, cid, "30,00", "PIX", nf="9")
        self.assertEqual(self.linha(cid)["status"], "ABERTO")
        # o aviso chega pelo contato do sistema, uma vez por dia
        aviso = "ainda está aberto"
        self.assertEqual(self.contar("SELECT COUNT(*) FROM chat_mensagens WHERE para_id=? AND corpo LIKE ?", (uid, "%" + aviso + "%")), 1)
        self.post(c, "/movimento-caixa/abrir", {"fundo": "0"})
        self.assertIn("aberto. Feche", self.texto(c.get("/movimento-caixa")))  # o bloqueio aparece na tela
        self.assertEqual(self.contar("SELECT COUNT(*) FROM chat_mensagens WHERE para_id=? AND corpo LIKE ?", (uid, "%" + aviso + "%")), 1)

    def test_fechar_relatorio_e_correcao_so_pela_gestao(self):
        self.criar_usuario("MOV_C", ["movimento_caixa"])
        c = self.cliente("MOV_C", "senha123")
        self.post(c, "/movimento-caixa/abrir", {"fundo": "20,00"})
        cid_din = self.caixa("DORA", 60, usuario="MOV_C")
        cid_pix = self.caixa("EVA", 30, usuario="MOV_C")
        self.receber(c, cid_din, "60,00", "DINHEIRO", "100,00", nf="71")
        self.receber(c, cid_pix, "30,00", "PIX", nf="72")
        sid = self.contar("SELECT id FROM caixa_sessoes WHERE usuario='MOV_C' AND data=?", (date.today().isoformat(),))
        r = self.post(c, "/movimento-caixa/fechar", {"sessao": str(sid)})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.contar("SELECT COUNT(*) FROM caixa_sessoes WHERE id=? AND status='FECHADO'", (sid,)), 1)

        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            rel = movimento.relatorio(con, sid)
        finally:
            con.close()
        self.assertEqual((rel["dinheiro_devido"], rel["dinheiro_recebido"], rel["troco"]), (60.0, 100.0, 40.0))
        self.assertEqual(rel["dinheiro_liquido"], 60.0)          # 100 entregues - 40 de troco
        self.assertEqual(rel["pix_total"], 30.0)
        self.assertEqual(rel["esperado_dinheiro"], 80.0)         # fundo 20 + líquido 60
        self.assertEqual(rel["total"], 90.0)
        self.assertEqual(c.get(f"/movimento-caixa/relatorio/{sid}").status_code, 200)
        self.assertEqual(c.get(f"/movimento-caixa/relatorio/{sid}.pdf").data[:4], b"%PDF")

        # o operador não corrige caixa fechado
        self.assertEqual(self.post(c, f"/movimento-caixa/editar/{cid_din}", {"valor": "60,00", "forma": "DINHEIRO",
                                                                             "recebido": "200,00", "nota_fiscal": "71"}).status_code, 302)
        self.assertEqual(self.linha(cid_din)["troco"], 40.0)
        # a gerência (administrador) corrige
        adm = self.cliente()
        self.post(adm, f"/movimento-caixa/editar/{cid_din}", {"valor": "60,00", "forma": "DINHEIRO",
                                                              "recebido": "200,00", "nota_fiscal": "71"})
        self.assertEqual(self.linha(cid_din)["troco"], 140.0)

    def test_lembrete_das_17h_para_fechar_o_caixa(self):
        from datetime import datetime
        uid = self.criar_usuario("MOV_D", ["movimento_caixa"])
        c = self.cliente("MOV_D", "senha123")
        self.post(c, "/movimento-caixa/abrir", {"fundo": "0"})
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            antes = datetime.combine(date.today(), datetime.min.time()).replace(hour=16, minute=50)
            depois = antes.replace(hour=17, minute=10)
            self.assertEqual(movimento.lembrar_fechamento(con, antes), 0)  # antes das 17h não lembra
            abertos = con.execute("SELECT COUNT(*) FROM caixa_sessoes WHERE status='ABERTO'").fetchone()[0]
            self.assertEqual(movimento.lembrar_fechamento(con, depois), abertos)  # às 17h lembra cada caixa aberto
            self.assertEqual(movimento.lembrar_fechamento(con, depois), 0)  # uma vez por dia
        finally:
            con.close()
        texto = "Lembrete das 17h"
        self.assertEqual(self.contar("SELECT COUNT(*) FROM chat_mensagens WHERE para_id=? AND corpo LIKE ?", (uid, "%" + texto + "%")), 1)

    def test_convenio_pago_na_clinica_aparece_sinalizado(self):
        con = dbmod.conectar(self.app.config["DATABASE"])
        con.execute("INSERT OR IGNORE INTO convenios (nome, gera_caixa, ativo) VALUES ('PARTICULAR', 1, 1)")
        con.commit()
        con.close()
        self.assertIn("Pago na clínica", self.texto(self.cliente().get("/convenios")))


if __name__ == "__main__":
    unittest.main()
