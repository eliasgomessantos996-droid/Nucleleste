"""Observação da agenda, módulo Documentos (contratos e fiscalização) e avisos de vencimento pelo contato do sistema."""
import io
import unittest
from datetime import date, timedelta

from app import arquivos, avisos, chat
from app import db as dbmod
from tests.test_chat_blindagens import Base
from tests.test_agenda import dia


class ObservacaoAgenda(Base):
    def test_observacao_aparece_no_dia_e_nas_copias(self):
        c = self.cliente()
        d1, d2 = dia(40), dia(41)
        self.post(c, "/agenda/criar", {"data": d1, "exame": "PET-CT", "inicio": "08:00", "intervalo": "30", "qtd": "2",
                                        "vagas": "1", "observacao": "  levar jejum de 4 horas  "})
        ag = c.get(f"/agenda/dia/{d1}").get_json()["agendas"][0]
        self.assertEqual(ag["observacao"], "levar jejum de 4 horas")  # espaços sobrando são tirados
        # repetição semanal e cópia para outro dia levam a observação junto
        self.post(c, "/agenda/criar", {"data": d2, "exame": "PET-CT", "inicio": "08:00", "intervalo": "30", "qtd": "1",
                                        "vagas": "1", "semanas": "1", "observacao": "PRIMEIRO DIA"})
        self.assertEqual(c.get(f"/agenda/dia/{d2}").get_json()["agendas"][0]["observacao"], "PRIMEIRO DIA")
        proxima = (date.fromisoformat(d2) + timedelta(days=7)).isoformat()
        self.assertEqual(c.get(f"/agenda/dia/{proxima}").get_json()["agendas"][0]["observacao"], "PRIMEIRO DIA")
        self.post(c, "/agenda/copiar", {"origem": d1, "destino": dia(42), "com_pacientes": ""})
        self.assertEqual(c.get(f"/agenda/dia/{dia(42)}").get_json()["agendas"][0]["observacao"], "levar jejum de 4 horas")


class DocumentosModulo(Base):
    def upload(self, c, tipo, nome, nome_arq="arquivo.pdf", conteudo=b"%PDF-1.4 teste", **extra):
        dados = {"tipo": tipo, "nome": nome, "arquivo": (io.BytesIO(conteudo), nome_arq)}
        dados.update(extra)
        return self.post(c, "/documentos-arquivo/novo", dados)

    def test_contrato_upload_listagem_download_e_exclusao(self):
        c = self.cliente()
        self.assertEqual(self.upload(c, "CONTRATO", "contrato de manutenção").status_code, 302)
        db = dbmod.conectar(self.app.config["DATABASE"])
        try:
            doc = db.execute("SELECT * FROM arquivos_docs WHERE tipo='CONTRATO'").fetchone()
        finally:
            db.close()
        self.assertEqual(doc["nome"], "CONTRATO DE MANUTENÇÃO")  # nome em maiúsculas, como no resto do sistema
        self.assertIsNone(doc["vencimento"])
        self.assertIn("CONTRATO DE MANUTENÇÃO", self.texto(c.get("/documentos-arquivo?aba=contratos")))
        r = c.get(f"/documentos-arquivo/{doc['id']}/arquivo?baixar=1")
        self.assertEqual((r.status_code, r.data), (200, b"%PDF-1.4 teste"))
        self.assertEqual(self.post(c, f"/documentos-arquivo/{doc['id']}/excluir").status_code, 302)
        self.assertEqual(c.get(f"/documentos-arquivo/{doc['id']}/arquivo").status_code, 404)

    def test_fiscalizacao_exige_vencimento_e_formato(self):
        c = self.cliente()
        self.upload(c, "FISCALIZACAO", "alvará sem data")  # sem vencimento: não grava
        self.upload(c, "CONTRATO", "programa executável", nome_arq="virus.exe")  # formato não aceito
        db = dbmod.conectar(self.app.config["DATABASE"])
        try:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM arquivos_docs").fetchone()[0], 0)
        finally:
            db.close()
        venc = (date.today() + timedelta(days=90)).isoformat()
        self.upload(c, "FISCALIZACAO", "alvará de funcionamento", vencimento=venc)
        pagina = self.texto(c.get("/documentos-arquivo?aba=fiscalizacao"))
        self.assertIn("ALVARÁ DE FUNCIONAMENTO", pagina)
        self.assertIn("em dia", pagina)

    def test_permissao_do_modulo(self):
        self.criar_usuario("DOC_NADA", ["agenda"])
        self.criar_usuario("DOC_OK", ["arquivo_documentos"])
        n = self.cliente("DOC_NADA", "senha123")
        self.assertEqual(n.get("/documentos-arquivo").status_code, 302)
        self.assertEqual(self.upload(n, "CONTRATO", "x").status_code, 302)
        ok = self.cliente("DOC_OK", "senha123")
        self.assertEqual(ok.get("/documentos-arquivo").status_code, 200)


class AvisosVencimento(Base):
    def setUp(self):
        self.db = dbmod.conectar(self.app.config["DATABASE"])

    def tearDown(self):
        self.db.close()

    def mensagens_para(self, uid):
        return [m["corpo"] for m in self.db.execute("SELECT corpo FROM chat_mensagens WHERE para_id=? ORDER BY id", (uid,))]

    def test_fases_do_aviso(self):
        self.assertEqual(avisos.fase(90), None)
        self.assertEqual(avisos.fase(60), "60")
        self.assertEqual(avisos.fase(45), "60")
        self.assertEqual(avisos.fase(7), "7")
        self.assertEqual(avisos.fase(0), "0")
        self.assertEqual(avisos.fase(-3), "VENCIDO")

    def test_avisos_em_periodos_diferentes_so_para_a_gerencia(self):
        gerente = self.criar_usuario("GER_AVISO", ["gerencia"])
        comum = self.criar_usuario("COMUM_AVISO", ["arquivo_documentos"])
        venc = date.today() + timedelta(days=5)
        arquivos.adicionar(self.db, "FISCALIZACAO", "Licença sanitária", venc.isoformat(), "licenca.pdf", b"x", "TESTE")
        hoje = venc - timedelta(days=5)  # faltam 5 dias: fase de 7 dias
        self.assertGreater(avisos.verificar(self.db, hoje), 0)
        msgs = self.mensagens_para(gerente)
        self.assertEqual(len(msgs), 1)
        self.assertIn("vence em 5 dias", msgs[0])
        self.assertIn("LICENÇA SANITÁRIA", msgs[0])
        self.assertEqual(self.mensagens_para(comum), [])  # quem não é gerência não recebe
        # a mesma fase não repete
        self.assertEqual(avisos.verificar(self.db, hoje), 0)
        self.assertEqual(len(self.mensagens_para(gerente)), 1)
        # fases seguintes: amanhã, e depois do vencimento
        avisos.verificar(self.db, venc - timedelta(days=1))
        avisos.verificar(self.db, venc + timedelta(days=1))
        msgs = self.mensagens_para(gerente)
        self.assertEqual(len(msgs), 3)
        self.assertIn("vence AMANHÃ", msgs[1])
        self.assertIn("vencido", msgs[2].lower())
        self.assertEqual(avisos.verificar(self.db, venc + timedelta(days=2)), 0)

    def test_contato_do_sistema_so_para_gerencia_e_somente_leitura(self):
        gerente = self.criar_usuario("GER_CONTATO", ["gerencia"])
        comum = self.criar_usuario("COMUM_CONTATO", ["arquivo_documentos", "atendimentos"])
        sid = avisos.sistema_id(self.db)
        self.assertIsNotNone(sid)
        nomes_gerente = [c["usuario"] for c in chat.contatos(self.db, gerente)]
        nomes_comum = [c["usuario"] for c in chat.contatos(self.db, comum)]
        self.assertIn(dbmod.SISTEMA_USUARIO, nomes_gerente)
        # funcionários veem o contato, mas só as mensagens de atualização (ver test_avisos_visibilidade)
        self.assertIn(dbmod.SISTEMA_USUARIO, nomes_comum)
        with self.assertRaises(chat.ErroChat):
            chat.enviar(self.db, gerente, sid, "oi")
        # o usuário do sistema não entra com senha (ninguém conhece a senha dele)
        anonimo = self.app.test_client()
        anonimo.get("/login")
        with anonimo.session_transaction() as s:
            token = s["csrf"]
        anonimo.post("/login", data={"usuario": dbmod.SISTEMA_USUARIO, "senha": "x", "_csrf": token})
        self.assertIn("/login", anonimo.get("/").headers.get("Location", ""))


if __name__ == "__main__":
    unittest.main()
