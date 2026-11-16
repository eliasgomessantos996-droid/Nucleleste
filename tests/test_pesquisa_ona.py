"""Pesquisa de satisfação (exigências da ONA): tipos de pergunta, questionário impresso, perfil do respondente e indicadores novos."""
import unittest
from datetime import date, timedelta

from app import pesquisa
from app import db as dbmod
from tests.test_chat_blindagens import Base


def _conexao(app):
    return dbmod.conectar(app.config["DATABASE"])


class PerguntasOna(Base):
    def setUp(self):
        self.db = _conexao(self.app)
        self.addCleanup(self.db.close)

    def test_perguntas_iniciais_com_os_tipos_certos(self):
        ps = pesquisa.perguntas(self.db)
        self.assertEqual(len(ps), 13)
        self.assertEqual([(p["texto"], p["tipo"]) for p in ps], list(pesquisa.PERGUNTAS_SUGERIDAS))
        self.assertEqual(ps[10]["opcoes"], ["Sim", "Não"])
        self.assertEqual(ps[12]["opcoes"], [str(i) for i in range(11)])

    def test_salvar_perguntas_grava_os_tipos(self):
        pesquisa.salvar_perguntas(self.db, ["Pergunta A", "", "Pergunta B", "Pergunta C"], ["SIMNAO", "NPS", "ESCALA", "XYZ"])
        ps = pesquisa.perguntas(self.db)
        # a pergunta em branco leva o próprio tipo (NPS) embora ignorada; tipo inválido vira ESCALA
        self.assertEqual([(p["texto"], p["tipo"]) for p in ps], [("Pergunta A", "SIMNAO"), ("Pergunta B", "ESCALA"), ("Pergunta C", "ESCALA")])
        pesquisa.restaurar_sugestoes(self.db)
        self.assertEqual(len(pesquisa.perguntas(self.db)), 13)


class RegistroOna(Base):
    def setUp(self):
        self.db = _conexao(self.app)
        self.addCleanup(self.db.close)
        pesquisa._ULTIMA.clear()

    def _preenchido(self, ps, **extra):
        """Responde todas as perguntas: escala 'Bom', Sim/Não 'Sim' e NPS '9'."""
        form = {}
        for p in ps:
            form["p%d" % p["id"]] = {"ESCALA": "Bom", "SIMNAO": "Sim", "NPS": "9"}[p["tipo"]]
        form.update(extra)
        return form

    def _linha(self, rid):
        return self.db.execute("SELECT * FROM cq_sat_respostas WHERE id=?", (rid,)).fetchone()

    def test_qrcode_completo_grava_nota_so_da_escala_e_nps(self):
        ps = pesquisa.perguntas(self.db)
        rid = pesquisa.registrar_resposta(self.db, self._preenchido(ps, nome="Ana"), "192.168.0.50")
        r = self._linha(rid)
        self.assertEqual((r["nota"], r["nps"], r["origem"], r["ip"]), (7.0, 9, "QRCODE", "192.168.0.50"))
        tipos = [i["tipo"] for i in self.db.execute("SELECT tipo FROM cq_sat_itens WHERE resposta_id=?", (rid,))]
        self.assertEqual(sorted(tipos), sorted(p["tipo"] for p in ps))
        self.assertEqual(self.db.execute("SELECT COUNT(*) AS n FROM cq_pesquisas WHERE criado_por='PESQUISA QR CODE' AND nota=7").fetchone()["n"], 1)

    def test_qrcode_faltando_pergunta_da_erro(self):
        ps = pesquisa.perguntas(self.db)
        form = self._preenchido(ps)
        del form["p%d" % ps[0]["id"]]
        with self.assertRaisesRegex(pesquisa.ErroPesquisa, "Responda todas as perguntas \\(falta a 1\\)"):
            pesquisa.registrar_resposta(self.db, form, "192.168.0.51")

    def test_impresso_com_duas_respostas_e_data_de_ontem(self):
        ps = pesquisa.perguntas(self.db)
        ontem = (date.today() - timedelta(days=1)).isoformat()
        form = {"p%d" % ps[0]["id"]: "Ótimo", "p%d" % ps[10]["id"]: "Sim", "data": ontem, "exame": "RM CRÂNIO",
                "atendimento": "Convênio", "respondente": "Acompanhante"}
        rid = pesquisa.registrar_resposta(self.db, form, None, origem="IMPRESSO", usuario="RECEPCAO")
        r = self._linha(rid)
        self.assertEqual((r["origem"], r["lancado_por"], r["data"], r["ip"]), ("IMPRESSO", "RECEPCAO", ontem, None))
        self.assertEqual((r["exame"], r["atendimento"], r["respondente"]), ("RM CRÂNIO", "Convênio", "Acompanhante"))
        self.assertEqual(r["nota"], 10.0)   # só a escala: a única escala marcada é Ótimo
        self.assertEqual(self.db.execute("SELECT COUNT(*) AS n FROM cq_sat_itens WHERE resposta_id=?", (rid,)).fetchone()[0], 2)
        self.assertEqual(self.db.execute("SELECT data, criado_por FROM cq_pesquisas WHERE nota=10 AND criado_por='PESQUISA IMPRESSA'").fetchone()[0], ontem)

    def test_impresso_com_data_futura_da_erro(self):
        ps = pesquisa.perguntas(self.db)
        amanha = (date.today() + timedelta(days=1)).isoformat()
        with self.assertRaisesRegex(pesquisa.ErroPesquisa, "até 1 ano atrás"):
            pesquisa.registrar_resposta(self.db, {"p%d" % ps[0]["id"]: "Bom", "data": amanha}, None, origem="IMPRESSO", usuario="RECEPCAO")

    def test_impresso_sem_nenhuma_resposta_da_erro(self):
        with self.assertRaisesRegex(pesquisa.ErroPesquisa, "Marque pelo menos uma resposta"):
            pesquisa.registrar_resposta(self.db, {"data": ""}, None, origem="IMPRESSO", usuario="RECEPCAO")

    def test_nps_11_da_erro(self):
        ps = pesquisa.perguntas(self.db)
        n_nps = [k for k, p in enumerate(ps, 1) if p["tipo"] == "NPS"][0]
        form = {"p%d" % ps[-1]["id"]: "11"}
        with self.assertRaisesRegex(pesquisa.ErroPesquisa, "Resposta inválida na pergunta %d\\." % n_nps):
            pesquisa.registrar_resposta(self.db, form, None, origem="IMPRESSO", usuario="RECEPCAO")


class IndicadoresOna(Base):
    def test_indicadores_novos(self):
        db = _conexao(self.app)
        self.addCleanup(db.close)
        ps = pesquisa.perguntas(db)
        ontem = (date.today() - timedelta(days=1)).isoformat()
        escalas = [p for p in ps if p["tipo"] == "ESCALA"]
        sim_nao = [p for p in ps if p["tipo"] == "SIMNAO"]
        nps = [p for p in ps if p["tipo"] == "NPS"][0]
        # resposta A: tudo bem (promotora), convênio, paciente não informado
        a = {"data": ontem, "exame": "RM", "atendimento": "Convênio"}
        a.update({"p%d" % p["id"]: "Ótimo" for p in escalas})
        a.update({"p%d" % p["id"]: "Sim" for p in sim_nao})
        a["p%d" % nps["id"]] = "10"
        pesquisa.registrar_resposta(db, a, None, origem="IMPRESSO", usuario="RECEPCAO")
        # resposta B: tudo ruim (detratora), particular, acompanhante
        b = {"data": ontem, "exame": "RM", "atendimento": "Particular", "respondente": "Acompanhante"}
        b.update({"p%d" % p["id"]: "Ruim" for p in escalas})
        b.update({"p%d" % sim_nao[0]["id"]: "Não", "p%d" % sim_nao[1]["id"]: "Sim"})
        b["p%d" % nps["id"]] = "0"
        pesquisa.registrar_resposta(db, b, None, origem="IMPRESSO", usuario="RECEPCAO")
        ind = pesquisa.indicadores(db, "2000-01-01", "2999-12-31")
        self.assertEqual(ind["respostas"], 2)
        self.assertEqual(ind["geral"]["satisfacao"], 50.0)     # só escalas: 10 Ótimo e 10 Ruim
        self.assertEqual(ind["geral"]["total"], 20)
        self.assertEqual(ind["seguranca"][0]["texto"], sim_nao[0]["texto"])
        self.assertEqual(ind["seguranca"][0], {"texto": sim_nao[0]["texto"], "total": 2, "sim": 1, "nao": 1, "pct_sim": 50.0})
        self.assertEqual(ind["nps"], {"total": 2, "promotores": 1, "neutros": 0, "detratores": 1, "indice": 0.0, "media": 5.0})
        self.assertEqual(ind["por_exame"], [{"exame": "RM", "respostas": 2, "satisfacao": 50.0}])
        self.assertEqual(ind["por_origem"], {"QRCODE": 0, "IMPRESSO": 2})
        self.assertEqual(ind["por_atendimento"], {"Convênio": 1, "Particular": 1, "Não informado": 0})
        self.assertEqual(ind["por_respondente"], {"Paciente": 0, "Acompanhante": 1, "Não informado": 1})
        self.assertEqual(ind["meses"][0]["satisfacao"], 50.0)


class RelatoriosOna(Base):
    def test_pdf_e_excel_com_as_secoes_novas(self):
        import io
        import openpyxl
        from app import pesquisa_docs
        db = _conexao(self.app)
        self.addCleanup(db.close)
        pesquisa._ULTIMA.clear()
        ps = pesquisa.perguntas(db)
        preenchido = {"p%d" % p["id"]: {"ESCALA": "Bom", "SIMNAO": "Sim", "NPS": "9"}[p["tipo"]] for p in ps}
        pesquisa.registrar_resposta(db, dict(preenchido, exame="RM", atendimento="Convênio", respondente="Paciente"), "192.168.0.70")
        ontem = (date.today() - timedelta(days=1)).isoformat()
        impresso = {"p%d" % p["id"]: {"ESCALA": "Ruim", "SIMNAO": "Não", "NPS": "3"}[p["tipo"]] for p in ps}
        impresso.update({"data": ontem, "exame": "TC TÓRAX", "atendimento": "Particular", "respondente": "Acompanhante"})
        pesquisa.registrar_resposta(db, impresso, None, origem="IMPRESSO", usuario="RECEPCAO")
        de, ate = "2000-01-01", "2999-12-31"
        ind = pesquisa.indicadores(db, de, ate)
        respostas = pesquisa.lista_respostas(db, de, ate)
        pdf = pesquisa_docs.relatorio_pdf(ind, respostas, "Nucleleste", "Teste")
        self.assertTrue(pdf.startswith(b"%PDF"))
        xlsx = pesquisa_docs.relatorio_xlsx(ind, respostas, "Nucleleste")
        wb = openpyxl.load_workbook(io.BytesIO(xlsx))
        self.assertIn("Segurança e NPS", wb.sheetnames)
        self.assertIn("Por exame", wb.sheetnames)
        cab = [c.value for c in wb["Respostas"][4]]
        for col in ("Origem", "Exame", "Atendimento", "Quem respondeu", "NPS (0 a 10)", "Lançado por"):
            self.assertIn(col, cab)


if __name__ == "__main__":
    unittest.main()
