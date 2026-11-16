"""Tabela de preços dos exames: criação, grade, ferramentas (exames, convênio, reajuste, duplicar), PDF, busca e permissão."""
import json
import unittest

from app import db as dbmod
from tests.test_chat_blindagens import Base


def _con(app):
    return dbmod.conectar(app.config["DATABASE"])


class TabelaPrecos(Base):
    def criar(self, c, nome, itens, vigencia="01/01/2026", ativa="1"):
        """Cria uma tabela pela tela e devolve o id gravado."""
        r = self.post(c, "/precos/nova", {"nome": nome, "vigencia": vigencia, "ativa": ativa, "obs": "PAGAMENTO EM DINHEIRO",
                                          "codigo[]": [i[0] for i in itens], "descricao[]": [i[1] for i in itens],
                                          "valor[]": [i[2] for i in itens], "obs[]": [i[3] for i in itens],
                                          "exame_id[]": ["" for _ in itens]})
        self.assertEqual(r.status_code, 302, self.texto(r)[:300])
        con = _con(self.app)
        try:
            return con.execute("SELECT id FROM tabelas_preco WHERE nome=?", (nome,)).fetchone()["id"]
        finally:
            con.close()

    def itens(self, tid):
        con = _con(self.app)
        try:
            return [dict(r) for r in con.execute("SELECT * FROM tabela_preco_itens WHERE tabela_id=? ORDER BY ordem", (tid,))]
        finally:
            con.close()

    def test_criar_tabela_com_itens_e_valores_brasileiros(self):
        c = self.cliente()
        tid = self.criar(c, "PARTICULAR TESTE CRIAR", [("40101010", "CINTILOGRAFIA TESTE", "1.250,00", "obs a"),
                                                       ("40101020", "PET TESTE", "80", ""),
                                                       ("", "   ", "99", "linha sem descrição é ignorada")])
        itens = self.itens(tid)
        self.assertEqual(len(itens), 2)
        self.assertEqual(itens[0]["codigo"], "40101010")
        self.assertEqual(itens[0]["valor"], 1250.0)
        self.assertEqual(itens[0]["descricao"], "CINTILOGRAFIA TESTE")   # descrição em maiúsculas
        self.assertEqual(itens[1]["valor"], 80.0)
        self.assertEqual(itens[1]["ordem"], 1)
        pagina = self.texto(c.get("/precos/%d" % tid))
        self.assertIn("PARTICULAR TESTE CRIAR", pagina)
        self.assertIn('name="codigo[]"', pagina)

    def test_valor_invalido_nao_grava_nada(self):
        c = self.cliente()
        r = self.post(c, "/precos/nova", {"nome": "TABELA ERRADA", "codigo[]": ["1"], "descricao[]": ["X"], "valor[]": ["abc"],
                                          "obs[]": [""], "exame_id[]": [""]})
        self.assertEqual(r.status_code, 400)
        con = _con(self.app)
        try:
            self.assertIsNone(con.execute("SELECT id FROM tabelas_preco WHERE nome='TABELA ERRADA'").fetchone())
        finally:
            con.close()

    def test_adicionar_exames_cadastrados(self):
        c = self.cliente()
        tid = self.criar(c, "TABELA EXAMES TESTE", [("", "ITEM INICIAL", "10", "")])
        self.post(c, "/precos/%d/acao" % tid, {"acao": "exames"})
        con = _con(self.app)
        try:
            ativos = con.execute("SELECT COUNT(*) FROM exames WHERE ativo=1").fetchone()[0]
        finally:
            con.close()
        com_exame = {i["exame_id"] for i in self.itens(tid) if i["exame_id"]}
        self.assertEqual(len(com_exame), ativos)
        self.assertTrue(any(i["valor"] is None for i in self.itens(tid) if i["exame_id"]))   # os acrescentados saem sem valor

    def test_reajuste_de_10_por_cento_arredondado_em_1_real(self):
        c = self.cliente()
        tid = self.criar(c, "TABELA REAJUSTE TESTE", [("", "ITEM A", "100", ""), ("", "ITEM B", "50", ""), ("", "ITEM C", "", "")])
        r = self.post(c, "/precos/%d/acao" % tid, {"acao": "reajuste", "percentual": "10", "arredondar": "1"})
        self.assertEqual(r.status_code, 302)
        valores = {i["descricao"]: i["valor"] for i in self.itens(tid)}
        self.assertEqual(valores["ITEM A"], 110.0)
        self.assertEqual(valores["ITEM B"], 55.0)
        self.assertIsNone(valores["ITEM C"])   # item sem valor continua sem valor

    def test_copiar_valores_do_convenio(self):
        c = self.cliente()
        con = _con(self.app)
        try:
            cur = con.execute("INSERT INTO convenios (nome, gera_caixa, ativo) VALUES ('CONVENIO TABELA TESTE', 0, 1)")
            cid = cur.lastrowid
            exame = con.execute("SELECT id FROM exames WHERE ativo=1 ORDER BY id LIMIT 1").fetchone()
            con.execute("INSERT INTO convenio_valores (convenio_id, exame_id, valor) VALUES (?,?,?)", (cid, exame["id"], 77.5))
            con.commit()
        finally:
            con.close()
        tid = self.criar(c, "TABELA CONVENIO TESTE", [("", "OUTRO", "1", "")])
        self.post(c, "/precos/%d/acao" % tid, {"acao": "convenio", "convenio_id": str(cid)})
        marcado = [i for i in self.itens(tid) if i["exame_id"] == exame["id"]]
        self.assertEqual(len(marcado), 1)
        self.assertEqual(marcado[0]["valor"], 77.5)

    def test_duplicar_copia_os_itens(self):
        c = self.cliente()
        tid = self.criar(c, "TABELA ORIGEM TESTE", [("T1", "ITEM X", "10", ""), ("T2", "ITEM Y", "20", "")])
        r = self.post(c, "/precos/%d/acao" % tid, {"acao": "duplicar", "nome": "TABELA COPIA TESTE"})
        self.assertEqual(r.status_code, 302)
        con = _con(self.app)
        try:
            nova = con.execute("SELECT id, vigencia FROM tabelas_preco WHERE nome='TABELA COPIA TESTE'").fetchone()
        finally:
            con.close()
        self.assertIsNotNone(nova)
        self.assertIsNone(nova["vigencia"])
        self.assertEqual([(i["codigo"], i["valor"]) for i in self.itens(nova["id"])], [("T1", 10.0), ("T2", 20.0)])

    def test_pdf_inline_e_anexo(self):
        c = self.cliente()
        tid = self.criar(c, "TABELA PDF TESTE", [("40101010", "CINTILOGRAFIA", "1.250,00", "")])
        r = c.get("/precos/%d/pdf" % tid)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.mimetype, "application/pdf")
        self.assertTrue(r.data.startswith(b"%PDF"))
        anexo = c.get("/precos/%d/pdf?baixar=1" % tid)
        self.assertIn("tabela-de-precos-%d.pdf" % tid, anexo.headers.get("Content-Disposition", ""))

    def test_busca_por_codigo_nas_tabelas_ativas(self):
        c = self.cliente()
        self.criar(c, "TABELA BUSCA TESTE", [("99887766", "EXAME DE BUSCA UNICO", "42", "")])
        achados = json.loads(self.texto(c.get("/precos/itens.json?q=99887766")))
        self.assertTrue(any(a["codigo"] == "99887766" and a["valor"] == 42.0 for a in achados))
        inativa = self.criar(c, "TABELA INATIVA BUSCA", [("55443322", "EXAME INATIVO BUSCA", "9", "")], ativa="0")
        self.assertEqual(json.loads(self.texto(c.get("/precos/itens.json?q=55443322"))), [])
        self.assertIsNotNone(inativa)

    def test_excluir_remove_tabela_e_itens(self):
        c = self.cliente()
        tid = self.criar(c, "TABELA EXCLUIR TESTE", [("", "ITEM Z", "5", "")])
        self.post(c, "/precos/%d/acao" % tid, {"acao": "excluir"})
        con = _con(self.app)
        try:
            self.assertIsNone(con.execute("SELECT 1 FROM tabelas_preco WHERE id=?", (tid,)).fetchone())
            self.assertEqual(con.execute("SELECT COUNT(*) FROM tabela_preco_itens WHERE tabela_id=?", (tid,)).fetchone()[0], 0)
        finally:
            con.close()

    def test_permissao_por_modulo(self):
        self.criar_usuario("PRECO_SEM_MODULO", ["dashboard"])
        sem = self.cliente("PRECO_SEM_MODULO", "senha123")
        self.assertEqual(sem.get("/precos").status_code, 302)
        self.assertEqual(sem.get("/precos/itens.json?q=1").status_code, 302)
        self.criar_usuario("PRECO_COM_MODULO", ["tabela_precos"])
        com = self.cliente("PRECO_COM_MODULO", "senha123")
        self.assertEqual(com.get("/precos").status_code, 200)
        self.assertEqual(com.get("/precos/itens.json?q=1").status_code, 200)


if __name__ == "__main__":
    unittest.main()
