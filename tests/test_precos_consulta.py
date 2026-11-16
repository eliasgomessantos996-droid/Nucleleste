"""Pesquisa rápida de valores por exame nos convênios SMS, Particular e MAISMED."""
import json
import unittest

from app import db as dbmod, modulos
from tests.test_chat_blindagens import Base


def _con(app):
    return dbmod.conectar(app.config["DATABASE"])


class PrecosConsultaRapida(Base):
    def setUp(self):
        con = _con(self.app)
        try:
            con.execute("DELETE FROM tabela_preco_itens")
            con.execute("DELETE FROM tabelas_preco")
            con.execute("DELETE FROM convenio_valores")
            con.execute("DELETE FROM convenios")
            con.commit()
        finally:
            con.close()

    def criar_tabela(self, c, nome, itens, vigencia="01/01/2026", ativa="1"):
        r = self.post(c, "/precos/nova", {
            "nome": nome,
            "vigencia": vigencia,
            "ativa": ativa,
            "obs": "",
            "codigo[]": [i[0] for i in itens],
            "descricao[]": [i[1] for i in itens],
            "valor[]": [i[2] for i in itens],
            "obs[]": [i[3] for i in itens],
            "exame_id[]": ["" for _ in itens],
        })
        self.assertEqual(r.status_code, 302, self.texto(r)[:300])

    def test_link_na_lista_e_entrada_em_modulos(self):
        c = self.cliente()
        html_lista = self.texto(c.get("/precos"))
        self.assertIn("/precos/consulta", html_lista)
        self.assertIn("Consulta rápida", html_lista)
        self.assertIn("preco.consulta", modulos.ICONES)
        endpoints_telas = [t[3] for t in modulos.telas()]
        self.assertIn("preco.consulta", endpoints_telas)

    def test_consulta_valores_vigentes_sms_particular_maismed_e_traco_quando_ausente(self):
        c = self.cliente()
        con = _con(self.app)
        try:
            for nome in ("SMS", "PARTICULAR", "MAIS MED"):
                con.execute("INSERT INTO convenios (nome, gera_caixa, ativo) VALUES (?, 1, 1)", (nome,))
            con.commit()
        finally:
            con.close()

        # Tabela antiga e tabela inativa não devem prevalecer sobre a tabela ativa e vigente
        self.criar_tabela(c, "PARTICULAR", [("40801012", "CINTILOGRAFIA DO MIOCÁRDIO", "900,00", "")], vigencia="01/01/2025", ativa="1")
        self.criar_tabela(c, "PARTICULAR", [("40801012", "CINTILOGRAFIA DO MIOCÁRDIO", "1.350,00", ""),
                                            ("40801020", "CINTILOGRAFIA ÓSSEA", "980,00", "")], vigencia="01/03/2026", ativa="1")
        self.criar_tabela(c, "PARTICULAR INATIVA", [("40801012", "CINTILOGRAFIA DO MIOCÁRDIO", "9.999,00", "")], vigencia="01/06/2026", ativa="0")

        self.criar_tabela(c, "SMS", [("40801012", "CINTILOGRAFIA DO MIOCÁRDIO", "620,50", "")], vigencia="01/02/2026", ativa="1")
        self.criar_tabela(c, "MAIS MED", [("40801012", "CINTILOGRAFIA DO MIOCÁRDIO", "1.100,00", ""),
                                          ("40801099", "PESQUISA DE CORPO INTEIRO", "750,00", "")], vigencia="01/02/2026", ativa="1")

        r = c.get("/precos/consulta")
        self.assertEqual(r.status_code, 200)
        html = self.texto(r)
        self.assertIn("Consulta rápida de valores", html)
        self.assertIn("SMS", html)
        self.assertIn("Particular", html)
        self.assertIn("MAISMED", html)
        self.assertIn("1.350,00", html)
        self.assertIn("620,50", html)
        self.assertIn("1.100,00", html)
        self.assertNotIn("9.999,00", html)
        self.assertNotIn("900,00", html)
        self.assertIn("—", html)

        dados = json.loads(self.texto(c.get("/precos/consulta.json")))
        por_cod = {d["codigo"]: d for d in dados}
        self.assertEqual(por_cod["40801012"]["sms"], 620.5)
        self.assertEqual(por_cod["40801012"]["particular"], 1350.0)
        self.assertEqual(por_cod["40801012"]["maismed"], 1100.0)
        # Exame sem preço no SMS e no MAISMED deve ficar None no JSON e mostrar "—" no HTML
        self.assertIsNone(por_cod["40801020"]["sms"])
        self.assertEqual(por_cod["40801020"]["particular"], 980.0)
        self.assertIsNone(por_cod["40801020"]["maismed"])

    def test_busca_por_nome_ou_codigo_e_fallback_convenio_valores(self):
        c = self.cliente()
        con = _con(self.app)
        try:
            cur_sms = con.execute("INSERT INTO convenios (nome, gera_caixa, ativo) VALUES ('SMS', 1, 1)")
            sms_id = cur_sms.lastrowid
            cur_mm = con.execute("INSERT INTO convenios (nome, gera_caixa, ativo) VALUES ('MAIS MED', 1, 1)")
            mm_id = cur_mm.lastrowid
            mibi = con.execute("SELECT id FROM exames WHERE nome='MIBI'").fetchone()
            ossea = con.execute("SELECT id FROM exames WHERE nome='ÓSSEA'").fetchone()
            con.execute("INSERT INTO convenio_valores (convenio_id, exame_id, valor) VALUES (?,?,?)", (sms_id, mibi["id"], 510.0))
            con.execute("INSERT INTO convenio_valores (convenio_id, exame_id, valor) VALUES (?,?,?)", (mm_id, mibi["id"], 890.0))
            con.execute("INSERT INTO convenio_valores (convenio_id, exame_id, valor) VALUES (?,?,?)", (mm_id, ossea["id"], 640.0))
            con.commit()
        finally:
            con.close()

        self.criar_tabela(c, "PARTICULAR", [("40801012", "MIBI", "1.200,00", ""), ("40801020", "ÓSSEA", "850,00", "")])

        # Filtra por código
        achados_cod = json.loads(self.texto(c.get("/precos/consulta.json?q=40801012")))
        self.assertEqual(len(achados_cod), 1)
        self.assertEqual(achados_cod[0]["descricao"], "MIBI")
        self.assertEqual(achados_cod[0]["sms"], 510.0)
        self.assertEqual(achados_cod[0]["particular"], 1200.0)
        self.assertEqual(achados_cod[0]["maismed"], 890.0)

        # Filtra por parte do nome sem acento
        html_ossea = self.texto(c.get("/precos/consulta?q=ossea"))
        self.assertIn("ÓSSEA", html_ossea)
        self.assertIn("850,00", html_ossea)
        self.assertIn("640,00", html_ossea)
        self.assertNotIn("1.200,00", html_ossea)

    def test_permissao_consulta_rapida(self):
        self.criar_usuario("CONSULTA_SEM_MOD", ["dashboard"])
        sem = self.cliente("CONSULTA_SEM_MOD", "senha123")
        self.assertEqual(sem.get("/precos/consulta").status_code, 302)
        self.assertEqual(sem.get("/precos/consulta.json").status_code, 302)

        self.criar_usuario("CONSULTA_COM_MOD", ["tabela_precos"])
        com = self.cliente("CONSULTA_COM_MOD", "senha123")
        self.assertEqual(com.get("/precos/consulta").status_code, 200)
        self.assertEqual(com.get("/precos/consulta.json").status_code, 200)


if __name__ == "__main__":
    unittest.main()
