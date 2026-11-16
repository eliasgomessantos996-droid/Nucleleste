"""Faturamento em três etapas: faturado (nota fiscal opcional) → nota fiscal emitida → recebido, com a glosa; e o protocolo em PDF."""
import io
import unittest
from datetime import date

from app import anexos, faturamento as fatu
from app import db as dbmod
from tests.test_chat_blindagens import Base

PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n"


class Fluxo(Base):
    def _sql(self, sql, params=()):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            cur = con.execute(sql, params)
            con.commit()
            return [dict(r) for r in cur.fetchall()] if cur.description else cur.lastrowid
        finally:
            con.close()

    def _fatura(self, fid):
        return self._sql("SELECT * FROM faturas WHERE id=?", (fid,))[0]

    def _nova(self, c, **extra):
        dados = {"convenio": "UNIMED", "referencia": "2026-09-30", "valor_bruto": "1.000,00", "protocolo": "PR-%d" % self._n,
                 "qtd_guias": "12", "nota_fiscal": "", "previsao": "", "obs": ""}
        dados.update(extra)
        self.post(c, "/faturamento/nova", dados)
        return self._sql("SELECT id FROM faturas ORDER BY id DESC LIMIT 1")[0]["id"]

    def setUp(self):
        super().setUp()
        self._n = getattr(self, "_n", 0) + 1
        self._sql("INSERT OR IGNORE INTO convenios (nome, ativo) VALUES ('UNIMED', 1)")
        self._sql("DELETE FROM faturas")
        self.adm = self.cliente()

    # ------------------------------------------------------------ 1. faturamento
    def test_cadastro_sem_nota_fiscal_fica_faturado(self):
        fid = self._nova(self.adm)
        f = self._fatura(fid)
        self.assertEqual((f["status"], f["nota_fiscal"], f["valor_bruto"], f["qtd_guias"], f["protocolo"], f["referencia"]),
                         ("FATURADO", None, 1000.0, 12, "PR-%d" % self._n, "2026-09-30"))
        self.assertEqual((f["tributos"], f["valor_liquido"]), (0, 1000.0))

    def test_cadastro_com_nota_ja_nasce_com_nota_emitida(self):
        f = self._fatura(self._nova(self.adm, nota_fiscal="NF-77"))
        self.assertEqual((f["status"], f["nota_fiscal"], f["nf_emitida_em"]), ("NF_EMITIDA", "NF-77", date.today().isoformat()))

    def test_so_a_nota_fiscal_e_opcional(self):
        for faltando in ("protocolo", "qtd_guias", "valor_bruto", "convenio", "referencia"):
            self._sql("DELETE FROM faturas")
            vazio = {"convenio": "UNIMED", "referencia": "2026-09-30", "valor_bruto": "100,00", "protocolo": "X1", "qtd_guias": "3"}
            vazio[faltando] = ""
            self.post(self.adm, "/faturamento/nova", vazio)
            self.assertEqual(self._sql("SELECT COUNT(*) AS n FROM faturas")[0]["n"], 0, faltando)
        self.post(self.adm, "/faturamento/nova", {"convenio": "UNIMED", "referencia": "2026-09-30", "valor_bruto": "100,00", "protocolo": "X1", "qtd_guias": "0"})
        self.assertEqual(self._sql("SELECT COUNT(*) AS n FROM faturas")[0]["n"], 0)               # guias precisa ser maior que zero

    def test_protocolo_repetido_no_mesmo_convenio_avisa_mas_salva(self):
        self._nova(self.adm, protocolo="REP-1")
        self._nova(self.adm, protocolo="REP-1")
        self.assertEqual(self._sql("SELECT COUNT(*) AS n FROM faturas")[0]["n"], 2)
        self.assertIn("Já existe outra fatura", self.texto(self.adm.get("/faturamento")))

    def test_editar_a_fatura_refaz_o_liquido_esperado(self):
        fid = self._nova(self.adm)
        self.post(self.adm, "/faturamento/%d" % fid, {"convenio": "UNIMED", "referencia": "2026-09-30", "valor_bruto": "1.500,00", "protocolo": "PR-X",
                                                      "qtd_guias": "15", "nota_fiscal": "", "previsao": "", "obs": ""})
        f = self._fatura(fid)
        self.assertEqual((f["valor_bruto"], f["valor_liquido"], f["qtd_guias"], f["protocolo"]), (1500.0, 1500.0, 15, "PR-X"))

    # ------------------------------------------------------------ 2. emissão da nota fiscal
    def test_emitir_a_nota_muda_a_situacao_e_pode_ser_desfeita(self):
        fid = self._nova(self.adm)
        self.post(self.adm, "/faturamento/%d/emitir" % fid, {"nota_fiscal": "", "data_emissao": "2026-10-02"})
        self.assertEqual(self._fatura(fid)["status"], "FATURADO")                              # sem número, nada muda
        self.post(self.adm, "/faturamento/%d/emitir" % fid, {"nota_fiscal": "NF-123", "data_emissao": "2026-10-02"})
        f = self._fatura(fid)
        self.assertEqual((f["status"], f["nota_fiscal"], f["nf_emitida_em"], f["nf_emitida_por"]), ("NF_EMITIDA", "NF-123", "2026-10-02", "ADMIN"))
        self.post(self.adm, "/faturamento/%d/emitir" % fid, {"nota_fiscal": "NF-124", "data_emissao": "2026-10-02"})   # corrige o número
        self.assertEqual(self._fatura(fid)["nota_fiscal"], "NF-124")
        self.post(self.adm, "/faturamento/%d/desfazer-emissao" % fid, {})
        f = self._fatura(fid)
        self.assertEqual((f["status"], f["nota_fiscal"], f["nf_emitida_em"]), ("FATURADO", None, None))

    # ------------------------------------------------------------ 3. recebidas e glosa
    def _emitida(self, **extra):
        return self._nova(self.adm, nota_fiscal="NF-1", **extra)

    def _receber(self, fid, **campos):
        dados = {"data_recebimento": "2026-10-10", "banco": "BANCO DO BRASIL"}
        dados.update(campos)
        self.post(self.adm, "/faturamento/%d/quitar" % fid, dados)
        return self._fatura(fid)

    def test_so_recebe_depois_de_emitir_a_nota(self):
        fid = self._nova(self.adm)                                                              # sem nota
        self.assertEqual(self._receber(fid, bruto_recebido="1.000,00")["status"], "FATURADO")

    def test_recebimento_com_glosa_e_tributos(self):
        fid = self._emitida()
        f = self._receber(fid, bruto_recebido="900,00", informar_tributos="1", tributos="50,00")
        self.assertEqual(f["status"], "RECEBIDO")
        self.assertEqual((f["bruto_recebido"], f["tributos_recebidos"], f["valor_recebido"], f["glosa"]), (900.0, 50.0, 850.0, 100.0))
        self.assertEqual((f["tributos"], f["valor_liquido"]), (50.0, 950.0))                    # campos antigos coerentes (dashboard e qualidade)
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            g = fatu.glosa(con.execute("SELECT * FROM faturas WHERE id=?", (fid,)).fetchone())
        finally:
            con.close()
        self.assertEqual((g["valor"], g["pct"], g["sentido"], g["bruto_recebido"]), (100.0, 10.0, "glosa", 900.0))
        pagina = self.texto(self.adm.get("/faturamento/recebidas"))
        self.assertIn("10,0%", pagina)
        self.assertIn("100,00", pagina)

    def test_recebimento_sem_tributos_o_liquido_e_o_bruto(self):
        f = self._receber(self._emitida(), bruto_recebido="1.000,00")
        self.assertEqual((f["tributos"], f["valor_recebido"], f["glosa"]), (0, 1000.0, 0.0))
        self.assertEqual(self._sql("SELECT status FROM faturas WHERE id=?", (f["id"],))[0]["status"], "RECEBIDO")

    def test_tributos_so_valem_se_a_opcao_for_marcada(self):
        f = self._receber(self._emitida(), bruto_recebido="1.000,00", tributos="80,00")          # opção não marcada: o campo é ignorado
        self.assertEqual((f["tributos"], f["valor_recebido"]), (0, 1000.0))

    def test_liquido_informado_refaz_o_bruto_e_inconsistente_e_recusado(self):
        fid = self._emitida()
        f = self._receber(fid, bruto_recebido="900,00", informar_tributos="1", tributos="50,00", liquido="800,00")   # 900 - 50 != 800
        self.assertEqual(f["status"], "NF_EMITIDA")
        f = self._receber(fid, bruto_recebido="900,00", informar_tributos="1", tributos="50,00", liquido="850,00")
        self.assertEqual((f["status"], f["valor_recebido"]), ("RECEBIDO", 850.0))

    def test_recebido_a_mais_nao_e_glosa(self):
        fid = self._emitida()
        f = self._receber(fid, bruto_recebido="1.100,00")
        self.assertEqual(f["glosa"], -100.0)
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            self.assertEqual(fatu.glosa(con.execute("SELECT * FROM faturas WHERE id=?", (fid,)).fetchone())["sentido"], "acima")
        finally:
            con.close()

    def test_banco_e_data_obrigatorios_e_tributos_nao_passam_do_bruto(self):
        fid = self._emitida()
        self.assertEqual(self._receber(fid, bruto_recebido="1.000,00", banco="")["status"], "NF_EMITIDA")
        self.assertEqual(self._receber(fid, bruto_recebido="1.000,00", data_recebimento="")["status"], "NF_EMITIDA")
        self.assertEqual(self._receber(fid, bruto_recebido="100,00", informar_tributos="1", tributos="500,00")["status"], "NF_EMITIDA")

    def test_reabrir_o_recebimento_volta_para_nota_emitida(self):
        fid = self._emitida()
        self._receber(fid, bruto_recebido="900,00")
        self.post(self.adm, "/faturamento/%d/reabrir" % fid, {})
        f = self._fatura(fid)
        self.assertEqual((f["status"], f["valor_recebido"], f["bruto_recebido"], f["glosa"], f["valor_liquido"]), ("NF_EMITIDA", None, None, None, 1000.0))

    def test_dashboard_e_qualidade_enxergam_a_glosa(self):
        self._receber(self._emitida(), bruto_recebido="900,00")
        pagina = self.texto(self.adm.get("/faturamento/dashboard"))
        self.assertEqual(self.adm.get("/faturamento/dashboard").status_code, 200)
        self.assertIn("100,00", pagina)

    # ------------------------------------------------------------ dados antigos
    def test_migracao_das_faturas_antigas(self):
        self._sql("INSERT INTO faturas (convenio, referencia, nota_fiscal, valor_bruto, tributos, valor_liquido, status, criado_em) "
                  "VALUES ('UNIMED','2026-01-31','NF-OLD',1000,100,900,'ABERTO','2026-02-01 10:00:00')")
        self._sql("INSERT INTO faturas (convenio, referencia, valor_bruto, tributos, valor_liquido, status) VALUES ('UNIMED','2026-01-31',500,0,500,'ABERTO')")
        self._sql("INSERT INTO faturas (convenio, referencia, nota_fiscal, valor_bruto, tributos, valor_liquido, status, data_recebimento, valor_recebido, banco_recebimento) "
                  "VALUES ('UNIMED','2026-01-31','NF-R',1000,100,900,'RECEBIDO','2026-02-20',800,'UNICRED')")
        self._sql("DELETE FROM config WHERE chave='faturas_status_v2'")
        dbmod.inicializar(self.app.config["DATABASE"])
        linhas = {f["nota_fiscal"] or "sem": f for f in self._sql("SELECT * FROM faturas")}
        self.assertEqual(linhas["NF-OLD"]["status"], "NF_EMITIDA")
        self.assertEqual(linhas["sem"]["status"], "FATURADO")
        r = linhas["NF-R"]
        self.assertEqual((r["status"], r["bruto_recebido"], r["tributos_recebidos"], r["glosa"]), ("RECEBIDO", 900.0, 100.0, 100.0))   # glosa antiga: 900 - 800
        self.assertTrue(self.adm.get("/faturamento/recebidas").status_code == 200)
        dbmod.inicializar(self.app.config["DATABASE"])                                           # roda de novo sem mexer em nada
        self.assertEqual({f["status"] for f in self._sql("SELECT status FROM faturas")}, {"NF_EMITIDA", "FATURADO", "RECEBIDO"})

    # ------------------------------------------------------------ protocolo em PDF
    def _enviar_pdf(self, fid, nome="protocolo.pdf", conteudo=PDF):
        return self.post(self.adm, "/faturamento/%d/protocolo/enviar" % fid, {"protocolo_pdf": (io.BytesIO(conteudo), nome)}, content_type="multipart/form-data")

    def test_importar_ver_dentro_do_sistema_e_baixar(self):
        fid = self._nova(self.adm)
        self._enviar_pdf(fid)
        f = self._fatura(fid)
        self.assertIsNotNone(f["anexo_id"])
        self.assertEqual((f["protocolo_nome"], f["protocolo_tamanho"], f["protocolo_por"]), ("protocolo.pdf", len(PDF), "ADMIN"))
        aberto = self.adm.get("/faturamento/%d/protocolo.pdf" % fid)
        self.assertEqual((aberto.status_code, aberto.mimetype, aberto.data), (200, "application/pdf", PDF))
        self.assertNotIn("attachment", aberto.headers.get("Content-Disposition", ""))              # abre no sistema, sem baixar
        baixar = self.adm.get("/faturamento/%d/protocolo.pdf?baixar=1" % fid)
        self.assertIn("attachment", baixar.headers["Content-Disposition"])
        self.assertIn("protocolo.pdf", baixar.headers["Content-Disposition"])
        pagina = self.adm.get("/faturamento/%d/protocolo" % fid).data.decode("utf-8")
        self.assertIn("<iframe", pagina)
        self.assertIn("/protocolo.pdf", pagina)
        self.assertIn("Ver PDF", self.texto(self.adm.get("/faturamento")))                         # botões na lista
        # o conteúdo mora no anexos.db, não no sistema.db
        self.assertEqual(anexos.ler(anexos.caminho_ao_lado(self.app.config["DATABASE"]), f["anexo_id"]), PDF)

    def test_so_aceita_pdf_de_verdade(self):
        fid = self._nova(self.adm)
        self._enviar_pdf(fid, nome="planilha.xlsx")
        self._enviar_pdf(fid, nome="falso.pdf", conteudo=b"isto nao e um pdf")
        self._enviar_pdf(fid, nome="vazio.pdf", conteudo=b"")
        self.assertIsNone(self._fatura(fid)["anexo_id"])
        self.assertEqual(self.adm.get("/faturamento/%d/protocolo.pdf" % fid).status_code, 404)

    def test_trocar_remove_o_pdf_antigo_e_remover_limpa(self):
        fid = self._nova(self.adm)
        self._enviar_pdf(fid)
        primeiro = self._fatura(fid)["anexo_id"]
        self._enviar_pdf(fid, nome="novo.pdf", conteudo=PDF + b"% segunda versao\n")
        segundo = self._fatura(fid)["anexo_id"]
        self.assertNotEqual(primeiro, segundo)
        caminho = anexos.caminho_ao_lado(self.app.config["DATABASE"])
        self.assertIsNone(anexos.ler(caminho, primeiro))
        self.assertIsNotNone(anexos.ler(caminho, segundo))
        self.post(self.adm, "/faturamento/%d/protocolo/remover" % fid, {})
        f = self._fatura(fid)
        self.assertEqual((f["anexo_id"], f["protocolo_nome"]), (None, None))
        self.assertIsNone(anexos.ler(caminho, segundo))

    def test_excluir_a_fatura_apaga_o_pdf(self):
        fid = self._nova(self.adm)
        self._enviar_pdf(fid)
        anexo = self._fatura(fid)["anexo_id"]
        self.post(self.adm, "/faturamento/%d/excluir" % fid, {})
        self.assertEqual(self._sql("SELECT COUNT(*) AS n FROM faturas")[0]["n"], 0)
        self.assertIsNone(anexos.ler(anexos.caminho_ao_lado(self.app.config["DATABASE"]), anexo))

    def test_pdf_junto_com_o_cadastro_e_pdf_ruim_nao_perde_a_fatura(self):
        dados = {"convenio": "UNIMED", "referencia": "2026-09-30", "valor_bruto": "10,00", "protocolo": "COM-PDF", "qtd_guias": "1",
                 "protocolo_pdf": (io.BytesIO(PDF), "p.pdf")}
        self.post(self.adm, "/faturamento/nova", dados, content_type="multipart/form-data")
        self.assertIsNotNone(self._sql("SELECT anexo_id FROM faturas WHERE protocolo='COM-PDF'")[0]["anexo_id"])
        ruim = dict(dados, protocolo="PDF-RUIM", protocolo_pdf=(io.BytesIO(b"nao e pdf"), "p.pdf"))
        self.post(self.adm, "/faturamento/nova", ruim, content_type="multipart/form-data")
        linha = self._sql("SELECT anexo_id FROM faturas WHERE protocolo='PDF-RUIM'")[0]
        self.assertIsNone(linha["anexo_id"])                                                       # fatura salva; só o PDF foi recusado

    def test_resumo_da_fatura_em_pdf(self):
        fid = self._emitida()
        self._receber(fid, bruto_recebido="900,00", informar_tributos="1", tributos="50,00")
        r = self.adm.get("/faturamento/%d/resumo.pdf" % fid)
        self.assertEqual((r.status_code, r.data[:4]), (200, b"%PDF"))

    # ------------------------------------------------------------ telas e permissões
    def test_abas_e_telas(self):
        for rota in ("/faturamento", "/faturamento/nova", "/faturamento/emissao", "/faturamento/recebidas"):
            self.assertEqual(self.adm.get(rota).status_code, 200, rota)
        pagina = self.texto(self.adm.get("/faturamento"))
        self.assertIn("Emissão da nota fiscal", pagina)
        self.assertIn("Recebidas", pagina)

    def test_quem_nao_tem_o_modulo_nao_entra_em_nenhuma_aba(self):
        self.criar_usuario("FAT_SEM", ["atendimentos"])
        c = self.cliente("FAT_SEM", "senha123")
        fid = self._nova(self.adm)
        for rota in ("/faturamento", "/faturamento/emissao", "/faturamento/recebidas", "/faturamento/%d/protocolo" % fid, "/faturamento/%d/protocolo.pdf" % fid):
            self.assertEqual(c.get(rota).status_code, 302, rota)
        self.assertEqual(self.post(c, "/faturamento/%d/emitir" % fid, {"nota_fiscal": "X"}).status_code, 302)
        self.assertEqual(self._fatura(fid)["status"], "FATURADO")

    def test_voltar_so_aceita_caminho_do_proprio_faturamento(self):
        fid = self._nova(self.adm)
        r = self.post(self.adm, "/faturamento/%d/emitir" % fid, {"nota_fiscal": "NF-9", "voltar": "https://exemplo.com/roubo"})
        self.assertIn("/faturamento/emissao", r.headers["Location"])


if __name__ == "__main__":
    unittest.main()
