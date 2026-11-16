"""Versão 1.4.4: agenda do dia em uma página, exclusão de lançamento do caixa (gerência), caixa zerado uma vez,
fornecedores (CNPJ, cadastro), parcelamento de compras e relatório de contas por fornecedor."""
import io
import os
import re
import sqlite3
import tempfile
import unittest
import urllib.error
from datetime import date
from unittest import mock

from app import agenda_docs, fornecedores as forn, migracoes
from app import db as dbmod
from tests.test_chat_blindagens import Base

CNPJ_OK = "11.222.333/0001-81"   # dígitos verificadores corretos


def paginas(pdf):
    return len(re.findall(rb"/Type\s*/Page(?!s)", pdf))


def agenda_falsa(exame, n):
    linhas = [{"hora": "%02d:%02d" % (7 + i // 4, (i % 4) * 15), "paciente": ("PACIENTE %d COM NOME BEM COMPRIDO DA SILVA" % i) if i % 3 else "",
               "convenio": "UNIMED" if i % 2 else "PARTICULAR", "status": "AGENDADO", "senha": "", "observacao": "", "contato": "",
               "remarcado_para": ""} for i in range(n)]
    return {"id": 1, "exame": exame, "inicio": "07:00", "fim": "17:00", "intervalo": 15, "vagas": n, "linhas": linhas,
            "resumo": {"marcados": n, "vagas": n}, "mibi": False}


class AgendaUmaPagina(unittest.TestCase):
    def test_sempre_cabe_em_uma_pagina(self):
        for agendas in ([agenda_falsa("MIBI", 12)],
                        [agenda_falsa("MIBI", 40), agenda_falsa("PET", 60), agenda_falsa("CINTILOGRAFIA", 90)],
                        [agenda_falsa("MUITOS", 220)],
                        []):
            pdf = agenda_docs.dia_pdf("2026-10-20", agendas, "Nucleleste")
            self.assertTrue(pdf.startswith(b"%PDF"))
            self.assertEqual(paginas(pdf), 1, [len(a["linhas"]) for a in agendas])

    def test_colunas_do_dia(self):
        pdf = agenda_docs.dia_pdf("2026-10-20", [agenda_falsa("MIBI", 5)], "Nucleleste")
        self.assertEqual(agenda_docs.CAB_DIA, ("Nº", "Horário", "Paciente", "Convênio"))
        self.assertGreater(len(pdf), 1000)

    def test_so_linhas_com_paciente(self):
        a = agenda_falsa("MIBI", 12)
        filtradas = agenda_docs._so_preenchidas([a])[0]["linhas"]
        self.assertTrue(filtradas)
        self.assertTrue(all((l["paciente"] or "").strip() for l in filtradas))
        self.assertEqual(len(filtradas), sum(1 for l in a["linhas"] if l["paciente"]))
        self.assertEqual(len(a["linhas"]), 12)   # a agenda original não muda
        pdf = agenda_docs.dia_pdf("2026-10-20", [a], "Nucleleste")
        self.assertEqual(paginas(pdf), 1)

    def test_resumo_do_dia(self):
        a = agenda_falsa("MIBI", 12)   # i % 3 == 0 sem paciente; convênio alterna UNIMED / PARTICULAR
        b = agenda_falsa("OSSEA", 5)
        b["linhas"][1]["convenio"] = "  unimed "   # com paciente (i=1)
        b["linhas"][2]["convenio"] = ""           # com paciente (i=2): vira "Sem convênio"
        r = agenda_docs._resumo_dia(agenda_docs._so_preenchidas([a, b]))
        self.assertEqual(r["total"], 8 + 3)
        self.assertEqual(r["por_exame"], [("MIBI", 8), ("OSSEA", 3)])
        convenios = dict(r["por_convenio"])
        self.assertEqual(sum(convenios.values()), 11)
        self.assertEqual(convenios["UNIMED"], sum(1 for l in a["linhas"] if l["paciente"] and l["convenio"] == "UNIMED") + 1)
        self.assertEqual(convenios["Sem convênio"], 1)
        self.assertEqual(r["por_convenio"], sorted(r["por_convenio"], key=lambda x: (-x[1], x[0])))

    def test_pdf_com_resumo_cabe_em_uma_pagina(self):
        agendas = [agenda_falsa("MIBI", 40), agenda_falsa("PET", 60), agenda_falsa("CINTILOGRAFIA", 90)]
        for a in agendas:
            for i, l in enumerate(a["linhas"]):
                l["convenio"] = "CONVENIO NUMERO %d" % (i % 14)   # muitos convênios: o quadro quebra em linhas
        self.assertEqual(paginas(agenda_docs.dia_pdf("2026-10-20", agendas, "Nucleleste")), 1)

    def test_exame_sem_paciente_gera_uma_pagina(self):
        a = agenda_falsa("PET", 6)
        for l in a["linhas"]:
            l["paciente"] = ""
        pdf = agenda_docs.dia_pdf("2026-10-20", [a], "Nucleleste")
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertEqual(paginas(pdf), 1)


class MovimentoExcluirEZerar(Base):
    def caixa(self, cliente="ANA", status="ABERTO"):
        con = dbmod.conectar(self.app.config["DATABASE"])
        cur = con.execute("INSERT INTO caixa (data, cliente, status, valor) VALUES (?,?,?,?)",
                          (date.today().isoformat(), cliente, status, 40))
        con.commit()
        con.close()
        return cur.lastrowid

    def existe(self, cid):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            return con.execute("SELECT 1 FROM caixa WHERE id=?", (cid,)).fetchone() is not None
        finally:
            con.close()

    def test_so_a_gerencia_exclui(self):
        self.criar_usuario("MOV_RECEP", ["movimento_caixa"])
        self.criar_usuario("MOV_GER", ["movimento_caixa", "gerencia"])
        cid = self.caixa()
        r = self.cliente("MOV_RECEP", "senha123")
        self.post(r, f"/movimento-caixa/excluir/{cid}")
        self.assertTrue(self.existe(cid))
        self.assertNotIn("Excluir", self.texto(r.get("/movimento-caixa")))
        g = self.cliente("MOV_GER", "senha123")
        self.assertIn("Excluir", self.texto(g.get("/movimento-caixa")))
        self.post(g, f"/movimento-caixa/excluir/{cid}")
        self.assertFalse(self.existe(cid))
        self.assertEqual(self.post(g, "/movimento-caixa/excluir/99999").status_code, 302)  # inexistente: só avisa

    def test_zerar_movimento_antigo_uma_unica_vez(self):
        pasta = tempfile.TemporaryDirectory()
        try:
            caminho = os.path.join(pasta.name, "z.db")
            dbmod.inicializar(caminho)
            con = dbmod.conectar(caminho)
            con.execute("INSERT INTO caixa_sessoes (usuario, data, status) VALUES ('X','2026-01-01','FECHADO')")
            con.execute("INSERT INTO caixa (cliente, status, valor) VALUES ('PAGA','PAGO',10)")
            con.execute("INSERT INTO caixa (cliente, status, valor) VALUES ('PENDENTE','ABERTO',20)")
            con.execute("DELETE FROM migracoes_aplicadas WHERE nome=?", (migracoes.ZERAR_MOVIMENTO,))
            con.commit()
            r = migracoes.zerar_movimento_antigo(con, caminho)
            self.assertEqual((r["sessoes"], r["recebimentos"]), (1, 1))
            self.assertTrue(os.path.exists(r["copia"]))
            self.assertEqual(con.execute("SELECT COUNT(*) FROM caixa_sessoes").fetchone()[0], 0)
            self.assertEqual([x["cliente"] for x in con.execute("SELECT cliente FROM caixa")], ["PENDENTE"])
            self.assertIsNone(migracoes.zerar_movimento_antigo(con, caminho))   # não roda de novo
            con.close()
            # a cópia de segurança guarda o que foi apagado
            copia = sqlite3.connect(r["copia"])
            self.assertEqual(copia.execute("SELECT COUNT(*) FROM caixa_sessoes").fetchone()[0], 1)
            copia.close()
            dbmod.inicializar(caminho)   # reiniciar o servidor não apaga mais nada
            novo = dbmod.conectar(caminho)
            self.assertEqual(novo.execute("SELECT COUNT(*) FROM caixa").fetchone()[0], 1)
            novo.close()
        finally:
            pasta.cleanup()


class Cnpj(unittest.TestCase):
    def test_validacao(self):
        self.assertTrue(forn.cnpj_valido(CNPJ_OK))
        self.assertTrue(forn.cnpj_valido("11222333000181"))
        for ruim in ("", "123", "11.222.333/0001-82", "00000000000000", "abc"):
            self.assertFalse(forn.cnpj_valido(ruim), ruim)
        self.assertEqual(forn.cnpj_formatado("11222333000181"), CNPJ_OK)

    def test_consulta_brasilapi(self):
        def baixar(url):
            self.assertIn("brasilapi", url)
            return {"razao_social": "Radiofarmácia Alfa Ltda", "nome_fantasia": "Alfa", "ddd_telefone_1": "1133334444",
                    "email": "CONTATO@ALFA.COM", "logradouro": "Rua A", "numero": "10", "bairro": "Centro", "cep": "01000000",
                    "municipio": "São Paulo", "uf": "sp", "descricao_situacao_cadastral": "ATIVA"}
        d = forn.consultar_cnpj(CNPJ_OK, baixar)
        self.assertEqual((d["nome"], d["fantasia"], d["uf"], d["email"], d["cnpj"]), ("Radiofarmácia Alfa Ltda", "Alfa", "SP", "contato@alfa.com", CNPJ_OK))
        self.assertIn("Rua A 10", d["endereco"])

    def test_fallback_e_erros(self):
        chamadas = []

        def cai_na_primeira(url):
            chamadas.append(url)
            if "brasilapi" in url:
                raise urllib.error.URLError("sem rede")
            return {"nome": "BETA SA", "fantasia": "", "telefone": "(11) 9999-8888 / (11) 3333-4444", "municipio": "Rio", "uf": "RJ", "situacao": "ATIVA"}
        d = forn.consultar_cnpj(CNPJ_OK, cai_na_primeira)
        self.assertEqual((d["nome"], d["fonte"], d["telefone"]), ("BETA SA", "ReceitaWS", "(11) 9999-8888"))
        self.assertEqual(len(chamadas), 2)

        def sem_internet(url):
            raise urllib.error.URLError("sem rede")
        with self.assertRaises(forn.ErroFornecedor) as e:
            forn.consultar_cnpj(CNPJ_OK, sem_internet)
        self.assertIn("internet", str(e.exception))

        def nao_achou(url):
            raise urllib.error.HTTPError(url, 404, "nf", {}, io.BytesIO())
        with self.assertRaises(forn.ErroFornecedor) as e:
            forn.consultar_cnpj(CNPJ_OK, nao_achou)
        self.assertIn("não encontrado", str(e.exception))
        with self.assertRaises(forn.ErroFornecedor):
            forn.consultar_cnpj("123", sem_internet)


class Parcelas(unittest.TestCase):
    def test_divisao_e_vencimentos(self):
        self.assertEqual(forn.dividir(100, 3), [33.33, 33.33, 33.34])
        self.assertAlmostEqual(sum(forn.dividir(1234.57, 7)), 1234.57, places=2)
        p = forn.planejar_parcelas(100, "2026-01-31", 3)
        self.assertEqual([x[1] for x in p], ["2026-01-31", "2026-02-28", "2026-03-31"])
        self.assertEqual([x[0] for x in p], [1, 2, 3])
        cada = forn.planejar_parcelas(50, "2026-11-10", 2, valor_e_total=False)
        self.assertEqual([x[2] for x in cada], [50.0, 50.0])
        self.assertEqual(forn.planejar_parcelas(10, "2026-12-15", 2)[1][1], "2027-01-15")
        for n in (1, 61):
            with self.assertRaises(forn.ErroFornecedor):
                forn.planejar_parcelas(10, "2026-01-01", n)


class ContasFornecedores(Base):
    def conta(self, c, **extra):
        dados = {"descricao": "compra de material", "categoria": "Material de escritório", "vencimento": "2026-11-10", "valor": "300,00"}
        dados.update(extra)
        return self.post(c, "/contas/nova", dados)

    def consulta(self, sql, params=()):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            return [dict(r) for r in con.execute(sql, params)]
        finally:
            con.close()

    def test_cadastro_vinculo_parcelas_e_relatorio(self):
        self.criar_usuario("FIN_A", ["contas"])
        self.criar_usuario("FIN_SEM", ["agenda"])
        c = self.cliente("FIN_A", "senha123")
        self.assertEqual(self.cliente("FIN_SEM", "senha123").get("/contas/fornecedores").status_code, 302)
        # cadastro manual, com validações
        self.post(c, "/contas/fornecedores/novo", {"nome": "", "cnpj": ""})
        self.post(c, "/contas/fornecedores/novo", {"nome": "ruim", "cnpj": "11.222.333/0001-82"})
        self.assertEqual(self.consulta("SELECT * FROM fornecedores"), [])
        self.post(c, "/contas/fornecedores/novo", {"nome": "papelaria central", "cnpj": CNPJ_OK, "telefone": "11988887777"})
        self.post(c, "/contas/fornecedores/novo", {"nome": "outro", "cnpj": CNPJ_OK})   # CNPJ repetido
        self.post(c, "/contas/fornecedores/novo", {"nome": "limpeza sem cnpj"})
        self.post(c, "/contas/fornecedores/novo", {"nome": "limpeza sem cnpj 2"})        # sem CNPJ pode repetir o vazio
        fs = self.consulta("SELECT * FROM fornecedores ORDER BY id")
        self.assertEqual([f["nome"] for f in fs], ["PAPELARIA CENTRAL", "LIMPEZA SEM CNPJ", "LIMPEZA SEM CNPJ 2"])
        self.assertEqual(fs[0]["telefone"], "(11)98888-7777")
        fid = fs[0]["id"]
        self.assertIn("PAPELARIA CENTRAL", self.texto(c.get("/contas/fornecedores?q=central")))
        self.assertIn("PAPELARIA CENTRAL", self.texto(c.get("/contas/fornecedores?q=11222333")))
        # consulta pela rota (com a internet desligada nos testes: devolve o erro, sem quebrar)
        with mock.patch.object(forn, "_baixar_json", side_effect=urllib.error.URLError("x")):
            j = c.get("/contas/fornecedores/consulta?cnpj=" + CNPJ_OK).get_json()
            self.assertFalse(j["ok"])
            self.assertIn("internet", j["erro"])
            self.assertFalse(c.get("/contas/fornecedores/consulta?cnpj=1").get_json()["ok"])
        with mock.patch.object(forn, "_baixar_json", return_value={"razao_social": "GAMA LTDA", "uf": "MG"}):
            j = c.get("/contas/fornecedores/consulta?cnpj=" + CNPJ_OK).get_json()
            self.assertEqual((j["ok"], j["dados"]["nome"], j["dados"]["uf"]), (True, "GAMA LTDA", "MG"))
        # conta comum vinculada
        self.conta(c, fornecedor_id=str(fid))
        simples = self.consulta("SELECT * FROM contas")[-1]
        self.assertEqual((simples["fornecedor"], simples["fornecedor_id"], simples["parcela_total"]), ("PAPELARIA CENTRAL", fid, None))
        # compra parcelada em 3x
        self.conta(c, descricao="notebook", valor="100,00", fornecedor_id=str(fid), parcelar="1", parcelas="3", parcela_tipo="total", vencimento="2026-12-31")
        ps = self.consulta("SELECT * FROM contas WHERE descricao='NOTEBOOK' ORDER BY parcela_n")
        self.assertEqual([(p["parcela_n"], p["parcela_total"], p["vencimento"], p["valor"]) for p in ps],
                         [(1, 3, "2026-12-31", 33.33), (2, 3, "2027-01-31", 33.33), (3, 3, "2027-02-28", 33.34)])
        self.assertEqual(len({p["parcela_grupo"] for p in ps}), 1)
        lista = self.texto(c.get("/contas?status="))
        for rotulo in ("1/3", "2/3", "3/3"):
            self.assertIn(rotulo, lista)
        self.assertIn("1/3", self.texto(c.get(f"/contas/{ps[0]['id']}")))
        # parcelamento inválido não grava nada
        antes = len(self.consulta("SELECT id FROM contas"))
        self.conta(c, descricao="x", parcelar="1", parcelas="1")
        self.assertEqual(len(self.consulta("SELECT id FROM contas")), antes)
        # conta sem cadastro, com o nome digitado
        self.conta(c, descricao="lanche", fornecedor="padaria da esquina", valor="20,00")
        # relatório por fornecedor
        r = c.get("/contas/fornecedores/relatorio?de=2026-01-01&ate=2027-12-31")
        t = self.texto(r)
        self.assertIn("PAPELARIA CENTRAL", t)
        self.assertIn("PADARIA DA ESQUINA", t)
        rel = forn.relatorio(dbmod.conectar(self.app.config["DATABASE"]), date(2026, 1, 1), date(2027, 12, 31))
        nomes = [g["nome"] for g in rel["grupos"]]
        self.assertEqual(nomes, ["PADARIA DA ESQUINA", "PAPELARIA CENTRAL"])
        papelaria = [g for g in rel["grupos"] if g["nome"] == "PAPELARIA CENTRAL"][0]
        self.assertEqual((papelaria["total"], len(papelaria["contas"])), (400.0, 4))
        self.assertEqual(rel["total"], 420.0)
        pdf = c.get("/contas/fornecedores/relatorio.pdf?de=2026-01-01&ate=2027-12-31")
        self.assertTrue(pdf.data.startswith(b"%PDF"))
        xlsx = c.get(f"/contas/fornecedores/relatorio.xlsx?de=2026-01-01&ate=2027-12-31&fornecedor={fid}")
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(xlsx.data))
        self.assertEqual(wb.sheetnames, ["Resumo", "Contas"])
        self.assertEqual(wb["Resumo"].cell(row=5, column=1).value, "PAPELARIA CENTRAL")
        # excluir as parcelas em aberto da compra
        self.post(c, f"/contas/{ps[1]['id']}/excluir-parcelas")
        self.assertEqual(self.consulta("SELECT id FROM contas WHERE descricao='NOTEBOOK'"), [])
        # excluir o fornecedor mantém as contas, sem vínculo
        self.post(c, f"/contas/fornecedores/{fid}/excluir")
        restante = self.consulta("SELECT fornecedor, fornecedor_id FROM contas WHERE fornecedor='PAPELARIA CENTRAL'")
        self.assertEqual(restante, [{"fornecedor": "PAPELARIA CENTRAL", "fornecedor_id": None}])


if __name__ == "__main__":
    unittest.main()
