"""Financeiro da agenda: convênio por seleção, cálculo do repasse (veio ou retorno), relatórios e permissão."""
import unittest
from datetime import date, timedelta

from app import agenda as ag
from app import db as dbmod
from tests.test_chat_blindagens import Base


def dia(n):
    """Datas distintas por teste (o banco é compartilhado dentro da classe)."""
    return (date.today() + timedelta(days=400 + n * 3)).isoformat()


class FinanceiroTestes(Base):
    def convenio(self, nome, mibi=None, ossea=None, tgi=None, paratgi=None, galio=None):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            con.execute("INSERT OR REPLACE INTO convenios (nome, gera_caixa, valor_mibi, valor_ossea, valor_tgi, valor_paratgi, "
                        "valor_galio, ativo) VALUES (?,0,?,?,?,?,?,1)", (nome, mibi, ossea, tgi, paratgi, galio))
            con.commit()
        finally:
            con.close()

    def campo(self, c, hid, campo, valor):
        return self.post(c, f"/agenda/horario/{hid}/campo", {"campo": campo, "valor": valor})

    def lancar(self, d, exame, convenio, nome):
        """Atendimento lançado (é dele que o relatório e o financeiro tiram quem veio); o exame é o do cadastro."""
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            cad = ag.exame_do_nome(exame, con.execute("SELECT id, nome FROM exames").fetchall())
            con.execute("INSERT INTO atendimentos (cliente_nome, data, exame, convenio, criado_em) VALUES (?,?,?,?,?)",
                        (nome, d, cad[1] if cad else exame, convenio, d + " 09:00:00"))
            con.commit()
        finally:
            con.close()

    def preencher(self, c, d, exame, linhas):
        """Cria uma agenda de 30 min às 08:00 e preenche as linhas: (paciente, convênio, status)."""
        self.post(c, "/agenda/criar", {"data": d, "exame": exame, "inicio": "08:00", "intervalo": "30",
                                        "qtd": str(len(linhas)), "vagas": "1"})
        ids = [l["id"] for l in c.get(f"/agenda/dia/{d}").get_json()["agendas"][0]["linhas"]]
        for hid, (paciente, convenio, status) in zip(ids, linhas):
            self.campo(c, hid, "paciente", paciente)
            if convenio:
                self.assertEqual(self.campo(c, hid, "convenio", convenio).status_code, 200)
            if status != "AGENDADO":
                self.assertEqual(self.post(c, f"/agenda/horario/{hid}/status", {"status": status}).status_code, 200)
            if status == "VEIO":
                self.lancar(d, exame, convenio or "", paciente)

    def test_convenio_e_escolha_da_lista(self):
        self.convenio("UNIMED", mibi=1000)
        self.convenio("SUS", mibi=200)
        c = self.cliente()
        d = dia(1)
        self.post(c, "/agenda/criar", {"data": d, "exame": "CINTILOGRAFIA MIOCARDICA", "inicio": "08:00", "intervalo": "30",
                                        "qtd": "2", "vagas": "1"})
        dados = c.get(f"/agenda/dia/{d}").get_json()
        self.assertIn("UNIMED", dados["convenios"])
        self.assertIn("SUS", dados["convenios"])
        hid = dados["agendas"][0]["linhas"][0]["id"]
        self.campo(c, hid, "paciente", "Ana")
        # só aceita convênio cadastrado; sem diferenciar maiúsculas, grava o nome cadastrado
        self.assertEqual(self.campo(c, hid, "convenio", "Inventado").status_code, 400)
        self.assertEqual(self.campo(c, hid, "convenio", "unimed").get_json()["valor"], "UNIMED")
        self.assertEqual(self.campo(c, hid, "convenio", "").status_code, 200)

    def test_repasse_so_quem_veio(self):
        self.convenio("ORIGEM", mibi=1000, tgi=500)
        self.convenio("SUS", mibi=200)
        self.convenio("PARTICULAR")  # cadastrado, mas sem valores: conta como zero e aparece como "sem valor"
        c = self.cliente()
        d1, d2 = dia(2), dia(3)
        self.preencher(c, d1, "CINTILOGRAFIA MIOCARDICA", [("Ana", "ORIGEM", "VEIO"), ("Bia", "SUS", "VEIO"),
                                                          ("Caio", "ORIGEM", "AGENDADO")])
        self.preencher(c, d2, "TGI ESTOMAGO", [("Dora", "ORIGEM", "VEIO"), ("Eva", "PARTICULAR", "VEIO"),
                                              ("Fabio", "ORIGEM", "FALTOU")])
        db = dbmod.conectar(self.app.config["DATABASE"])
        rel = ag.financeiro(db, date.fromisoformat(d1), date.fromisoformat(d2), 30)
        db.close()
        nomes = [i["paciente"] for i in rel["itens"]]
        self.assertEqual(nomes, ["Ana", "Bia", "Dora", "Eva"])  # Caio (agendado) e Fabio (faltou) ficam de fora
        self.assertEqual([i["n"] for i in rel["itens"]], [1, 2, 3, 4])
        valores = {i["paciente"]: (i["valor"], i["repasse"]) for i in rel["itens"]}
        self.assertEqual(valores["Ana"], (1000.0, 300.0))   # MIBI
        self.assertEqual(valores["Bia"], (200.0, 60.0))
        self.assertEqual(valores["Dora"], (500.0, 150.0))   # TGI
        self.assertEqual(valores["Eva"], (0.0, 0.0))        # convênio sem cadastro: conta como zero
        self.assertEqual(rel["total_valor"], 1700.0)
        self.assertEqual(rel["total_repasse"], 510.0)
        self.assertEqual(rel["sem_valor"], 1)
        tipos = {(g["convenio"], g["tipo"]): g["valor"] for g in rel["resumo"]}
        self.assertEqual(tipos[("ORIGEM", "MIBI")], 1000.0)
        self.assertEqual(tipos[("ORIGEM", "TGI")], 500.0)

    def test_periodo_e_porcentagem(self):
        self.convenio("PER", mibi=100)
        c = self.cliente()
        d = dia(4)
        self.preencher(c, d, "MIBI REPOUSO", [("Gil", "PER", "VEIO")])
        db = dbmod.conectar(self.app.config["DATABASE"])
        # período que não inclui o dia: nada a repassar
        fora = ag.financeiro(db, date.fromisoformat(d) - timedelta(days=10), date.fromisoformat(d) - timedelta(days=5), 50)
        self.assertEqual((fora["qtd"], fora["total_repasse"]), (0, 0))
        # 0% e 100%
        zero = ag.financeiro(db, date.fromisoformat(d), date.fromisoformat(d), 0)
        cheio = ag.financeiro(db, date.fromisoformat(d), date.fromisoformat(d), 100)
        db.close()
        self.assertEqual((zero["total_repasse"], cheio["total_repasse"]), (0.0, 100.0))

    def test_tela_pdf_e_excel(self):
        self.convenio("TELA", mibi=300)
        c = self.cliente()
        d = dia(5)
        self.preencher(c, d, "CINTILOGRAFIA MIOCARDICA", [("Hugo", "TELA", "VEIO")])
        pagina = self.texto(c.get(f"/agenda/financeiro?de={d}&ate={d}&pct=30"))
        self.assertIn("faturado no período", pagina)
        self.assertIn("Hugo", pagina)
        self.assertIn("90,00", pagina)  # 30% de 300
        self.assertNotIn("faturado no período", self.texto(c.get(f"/agenda/financeiro?de={d}&ate={d}&pct=abc")))
        pdf = c.get(f"/agenda/financeiro.pdf?de={d}&ate={d}&pct=30")
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.data.startswith(b"%PDF"))
        xlsx = c.get(f"/agenda/financeiro.xlsx?de={d}&ate={d}&pct=30")
        self.assertEqual(xlsx.status_code, 200)
        self.assertTrue(xlsx.data.startswith(b"PK"))
        self.assertEqual(c.get(f"/agenda/financeiro.pdf?de={d}&ate={d}").status_code, 400)  # sem porcentagem não gera

    def test_permissao_do_modulo(self):
        self.criar_usuario("FIN_NADA", ["agenda"])
        self.criar_usuario("FIN_OK", ["agenda", "agenda_financeiro"])
        n = self.cliente("FIN_NADA", "senha123")
        self.assertEqual(n.get("/agenda").status_code, 200)
        self.assertEqual(n.get("/agenda/financeiro").status_code, 302)
        self.assertEqual(n.get("/agenda/financeiro.pdf?pct=10").status_code, 302)
        self.assertNotIn("financeiro da agenda", self.texto(n.get("/agenda")).lower())
        ok = self.cliente("FIN_OK", "senha123")
        self.assertEqual(ok.get("/agenda/financeiro").status_code, 200)
        self.assertIn("financeiro da agenda", self.texto(ok.get("/agenda")).lower())   # botão na barra da agenda
        self.assertIn("Financeiro da Agenda", self.texto(ok.get("/", headers={"Referer": "http://localhost/"})))


    def preencher_mibi(self, c, d, linhas):
        """Agenda MIBI com uma linha por paciente: (paciente, convênio, status, etapa). Quem veio é lançado no atendimento."""
        self.post(c, "/agenda/criar", {"data": d, "exame": "CINTILOGRAFIA MIOCARDICA", "inicio": "08:00", "intervalo": "30",
                                        "qtd": str(len(linhas)), "vagas": "1"})
        ids = [l["id"] for l in c.get(f"/agenda/dia/{d}").get_json()["agendas"][0]["linhas"]]
        for hid, (paciente, convenio, status, etapa) in zip(ids, linhas):
            self.campo(c, hid, "paciente", paciente)
            self.assertEqual(self.campo(c, hid, "convenio", convenio).status_code, 200)
            self.assertEqual(self.campo(c, hid, "senha", etapa).status_code, 200)
            if status != "AGENDADO":
                self.assertEqual(self.post(c, f"/agenda/horario/{hid}/status", {"status": status}).status_code, 200)
            if status == "VEIO":
                self.lancar(d, "CINTILOGRAFIA MIOCARDICA", convenio, paciente)

    def test_filtro_por_dias_da_semana(self):
        self.convenio("DIAS", mibi=100)
        c = self.cliente()
        inicio = date.fromisoformat(dia(30))
        for k in range(7):   # uma semana inteira, um paciente por dia
            d = (inicio + timedelta(days=k)).isoformat()
            self.preencher(c, d, "CINTILOGRAFIA MIOCARDICA", [(f"Dia {k} Teste", "DIAS", "VEIO")])
        fim = inicio + timedelta(days=6)
        db = dbmod.conectar(self.app.config["DATABASE"])
        sem_filtro = ag.financeiro(db, inicio, fim, 30)
        rel = ag.financeiro(db, inicio, fim, 30, dias=(1, 4, 9, "x"))   # 1=terça, 4=sexta; valores inválidos ignorados
        db.close()
        esperados = sorted(f"Dia {k} Teste" for k in range(7) if (inicio + timedelta(days=k)).weekday() in (1, 4))
        self.assertEqual(sem_filtro["qtd"], 7)
        self.assertEqual(rel["dias"], [1, 4])
        self.assertEqual(sorted(i["paciente"] for i in rel["itens"]), esperados)
        self.assertEqual(rel["qtd"], len(esperados))

    def test_etapas_marcadas_no_mibi(self):
        self.convenio("ETAPAS", mibi=100)
        self.convenio("TGI ETAPAS", tgi=100)
        c = self.cliente()
        d1, d2, d3 = dia(40), dia(41), dia(42)
        # Repouso no primeiro dia e Estresse dois dias depois: é o mesmo exame (unido), com as duas etapas no item
        self.preencher_mibi(c, d1, [("ETP Ivo", "ETAPAS", "VEIO", "Repouso"), ("ETP Jo", "ETAPAS", "VEIO", "Protocolo")])
        self.preencher_mibi(c, d3, [("ETP Ivo", "ETAPAS", "VEIO", "Estresse")])
        self.preencher(c, d2, "TGI ESTOMAGO", [("ETP Lia", "TGI ETAPAS", "VEIO")])
        db = dbmod.conectar(self.app.config["DATABASE"])
        rel = ag.financeiro(db, date.fromisoformat(d1), date.fromisoformat(d3), 30)
        nome_mibi = ag.exame_do_nome("CINTILOGRAFIA MIOCARDICA", db.execute("SELECT id, nome FROM exames").fetchall())[1]   # nome do cadastro
        so_mibi = ag.financeiro(db, date.fromisoformat(d1), date.fromisoformat(d3), 30, exame=nome_mibi)
        por_nome = {i["paciente"]: i for i in rel["itens"]}
        self.assertEqual(por_nome["ETP Ivo"]["etapas"], ["Estresse", "Repouso"])   # unido: Repouso + Estresse
        self.assertEqual(por_nome["ETP Jo"]["etapas"], ["Protocolo"])
        self.assertEqual(por_nome["ETP Lia"]["etapas"], [])                         # não MIBI: sem etapas
        self.assertEqual([i["paciente"] for i in rel["itens"] if i["paciente"] == "ETP Ivo"], ["ETP Ivo"])  # o par não vira outro item
        self.assertTrue(rel["tem_mibi"])
        self.assertEqual(sorted(i["paciente"] for i in so_mibi["itens"]), ["ETP Ivo", "ETP Jo"])
        # filtro de etapa continua igual: só Protocolo (Ivo some, pois o Repouso foi o que sobrou)
        so_protocolo = ag.financeiro(db, date.fromisoformat(d1), date.fromisoformat(d3), 30, exame=nome_mibi, tipos=["Protocolo"])
        db.close()
        self.assertEqual([i["paciente"] for i in so_protocolo["itens"]], ["ETP Jo"])

    def test_pdf_compacto_cabe_em_uma_pagina(self):
        import re
        from app import agenda_fin_docs as fdocs
        itens = []
        for n in range(1, 121):
            etapas = ["Repouso", "Estresse"] if n % 3 == 0 else (["Protocolo"] if n % 3 == 1 else [])
            itens.append({"n": n, "paciente": f"Paciente Sintetico {n:03d} da Silva", "convenio": f"CONVENIO {n % 4}",
                          "exame": "CINTILOGRAFIA MIOCARDICA", "tipo": "MIBI", "etapa": "", "etapas": etapas, "mibi": True,
                          "data": "2026-01-05", "hora": "08:00", "valor": 1000.0, "repasse": 300.0, "sem_valor": False})
        resumo = [{"convenio": f"CONVENIO {k}", "tipo": "MIBI", "qtd": 10, "valor": 10000.0} for k in range(12)]
        rel = {"de": "2026-01-01", "ate": "2026-01-31", "pct": 30.0, "exame": "CINTILOGRAFIA MIOCARDICA", "tipos": [], "dias": [1, 4],
               "itens": itens, "resumo": resumo, "tem_mibi": True, "qtd": len(itens), "total_valor": 120000.0,
               "total_repasse": 36000.0, "sem_valor": 0}
        pdf = fdocs.financeiro_pdf(rel, "Clinica Teste")
        self.assertTrue(pdf.startswith(b"%PDF"))
        paginas = len(re.findall(rb"/Type\s*/Page(?!s)", pdf))
        self.assertEqual(paginas, 1)

    def test_retorno_entra_no_financeiro(self):
        self.convenio("RET", mibi=100)
        c = self.cliente()
        d = dia(70)
        self.preencher(c, d, "CINTILOGRAFIA MIOCARDICA", [("Rui Retorno", "RET", "RETORNO")])   # retorno sem remarcação
        db = dbmod.conectar(self.app.config["DATABASE"])
        rel = ag.financeiro(db, date.fromisoformat(d), date.fromisoformat(d), 30)
        db.close()
        self.assertEqual([i["paciente"] for i in rel["itens"]], ["Rui Retorno"])
        self.assertEqual((rel["total_valor"], rel["total_repasse"]), (100.0, 30.0))

    def test_remarcado_que_veio_conta_uma_vez(self):
        self.convenio("REM", mibi=100)
        c = self.cliente()
        d1, d2 = dia(71), dia(72)
        for d in (d1, d2):
            self.post(c, "/agenda/criar", {"data": d, "exame": "CINTILOGRAFIA MIOCARDICA", "inicio": "08:00", "intervalo": "30",
                                            "qtd": "1", "vagas": "1"})
        origem = c.get(f"/agenda/dia/{d1}").get_json()["agendas"][0]["linhas"][0]["id"]
        destino = c.get(f"/agenda/dia/{d2}").get_json()["agendas"][0]["linhas"][0]["id"]
        self.campo(c, origem, "paciente", "Sol Remarcado")
        self.assertEqual(self.campo(c, origem, "convenio", "REM").status_code, 200)
        self.assertEqual(self.post(c, f"/agenda/horario/{origem}/remarcar", {"destino": str(destino)}).status_code, 200)
        self.assertEqual(self.post(c, f"/agenda/horario/{destino}/status", {"status": "VEIO"}).status_code, 200)
        self.lancar(d2, "CINTILOGRAFIA MIOCARDICA", "REM", "Sol Remarcado")
        db = dbmod.conectar(self.app.config["DATABASE"])
        rel = ag.financeiro(db, date.fromisoformat(d1), date.fromisoformat(d2), 30)
        db.close()
        self.assertEqual([i["paciente"] for i in rel["itens"]], ["Sol Remarcado"])   # RETORNO da origem não soma de novo
        self.assertEqual((rel["qtd"], rel["total_valor"]), (1, 100.0))

    def test_numero_do_item_segue_o_relatorio(self):
        """Nº = 1..N na ordem do relatório, mesmo com linha fora do relatório, RETORNO descartado e par Repouso+Estresse unido."""
        from app import agenda_fin_docs as fdocs
        self.convenio("NUM", mibi=100)
        c = self.cliente()
        d1, d2, d3, d4, d5 = dia(80), dia(81), dia(82), dia(83), dia(84)
        # linha que não entra no relatório (agendada): não pode deixar buraco no Nº
        self.preencher_mibi(c, d1, [("Num Um", "NUM", "VEIO", "Protocolo"), ("Num Dois", "NUM", "AGENDADO", "Repouso")])
        # par Repouso + Estresse do mesmo paciente: um item só
        self.preencher_mibi(c, d2, [("Num Tres", "NUM", "VEIO", "Repouso")])
        self.preencher_mibi(c, d3, [("Num Tres", "NUM", "VEIO", "Estresse")])
        # retorno remarcado que veio na nova data: a origem (RETORNO) é descartada
        for d in (d4, d5):
            self.post(c, "/agenda/criar", {"data": d, "exame": "CINTILOGRAFIA MIOCARDICA", "inicio": "08:00", "intervalo": "30",
                                            "qtd": "1", "vagas": "1"})
        origem = c.get(f"/agenda/dia/{d4}").get_json()["agendas"][0]["linhas"][0]["id"]
        destino = c.get(f"/agenda/dia/{d5}").get_json()["agendas"][0]["linhas"][0]["id"]
        self.campo(c, origem, "paciente", "Num Quatro")
        self.campo(c, origem, "convenio", "NUM")
        self.assertEqual(self.post(c, f"/agenda/horario/{origem}/remarcar", {"destino": str(destino)}).status_code, 200)
        self.assertEqual(self.post(c, f"/agenda/horario/{destino}/status", {"status": "VEIO"}).status_code, 200)
        self.lancar(d5, "CINTILOGRAFIA MIOCARDICA", "NUM", "Num Quatro")
        db = dbmod.conectar(self.app.config["DATABASE"])
        rel = ag.financeiro(db, date.fromisoformat(d1), date.fromisoformat(d5), 30)
        db.close()
        self.assertEqual([i["paciente"] for i in rel["itens"]], ["Num Um", "Num Tres", "Num Quatro"])
        self.assertEqual([i["n"] for i in rel["itens"]], list(range(1, len(rel["itens"]) + 1)))
        self.assertEqual(rel["qtd"], 3)
        self.assertTrue(fdocs.financeiro_pdf(rel, "Clinica Teste").startswith(b"%PDF"))
        self.assertTrue(fdocs.financeiro_xlsx(rel, "Clinica Teste").startswith(b"PK"))
        tela = self.texto(c.get(f"/agenda/financeiro?de={d1}&ate={d5}&pct=30"))
        self.assertIn("Num Quatro", tela)

    def test_rota_pdf_abrir_e_dias(self):
        self.convenio("ABRIR", mibi=300)
        c = self.cliente()
        d = dia(60)
        self.preencher(c, d, "CINTILOGRAFIA MIOCARDICA", [("Lia Abrir", "ABRIR", "VEIO")])
        r = c.get(f"/agenda/financeiro.pdf?de={d}&ate={d}&pct=30&abrir=1&dias=1&dias=4")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.mimetype, "application/pdf")
        self.assertIn("inline", r.headers.get("Content-Disposition", ""))   # abrir=1 não força o download
        self.assertTrue(r.data.startswith(b"%PDF"))
        baixar = c.get(f"/agenda/financeiro.pdf?de={d}&ate={d}&pct=30")
        self.assertIn("attachment", baixar.headers.get("Content-Disposition", ""))
        tela = self.texto(c.get(f"/agenda/financeiro?de={d}&ate={d}&pct=30&dias=1&dias=4"))
        self.assertIn("Dias: <strong>ter, sex</strong>", tela)   # resumo da tela mostra os dias filtrados
        self.assertIn("Imprimir", tela)


if __name__ == "__main__":
    unittest.main()
