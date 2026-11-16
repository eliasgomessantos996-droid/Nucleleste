"""Prontuário do paciente: número automático, SBAR de paciente interno, documento, conclusão, impressão e permissão."""
import json
import unittest

from app import db as dbmod
from app import prontuario
from tests.test_chat_blindagens import Base

EXAME = "RENAL"   # exame sem questionário e sem medicamentos obrigatórios
NAO_INFORMADO = "NÃO INFORMADO"


def _completo(**extra):
    """Campos obrigatórios do SBAR preenchidos (mais o que vier em `extra`)."""
    dados = {"exame": EXAME, "estado_geral": "Consciente, orientado, colaborativo", "intercorrencias": "Sem intercorrências",
             "cuidados": "Liberado para dieta habitual", "profissional_nome": "ENF. TESTE", "profissional_registro": "COREN 12345"}
    dados.update(extra)
    return dados


class ProntuarioTestes(Base):
    def setUp(self):
        self.c = self.cliente()
        self.seq = 0

    def _db(self):
        return dbmod.conectar(self.app.config["DATABASE"])

    def _cliente(self, nome="PACIENTE PRONTUARIO"):
        self.seq += 1
        nome = "%s %d" % (nome, self.seq)
        con = self._db()
        try:
            cur = con.execute("INSERT INTO clientes (nome, data_nasc, sexo, convenio) VALUES (?,?,?,?)", (nome, "1960-02-03", "M", "UNIMED"))
            con.commit()
            return cur.lastrowid, nome
        finally:
            con.close()

    def _lancar(self, cid, interno=False, local="", c=None):
        # o RENAL tem questionário da ficha PNT: "manual" dispensa as respostas, como na ficha impressa à mão
        dados = {"cliente_id": str(cid), "exame": EXAME, "data": "2026-11-10", "medico": "DR TESTE", "convenio": "",
                 "medicamentos": "", "exame_anterior": NAO_INFORMADO, "interno_local": local, "manual": "1"}
        if interno:
            dados["interno"] = "1"
        return self.post(c or self.c, "/atendimentos/novo", dados)

    def _sbar_pendente(self, local="HOSPITAL TESTE - UTI, LEITO 3"):
        cid, nome = self._cliente()
        self._lancar(cid, interno=True, local=local)
        con = self._db()
        try:
            did = con.execute("SELECT id FROM prontuario_docs WHERE cliente_id=? AND tipo='sbar'", (cid,)).fetchone()["id"]
        finally:
            con.close()
        return cid, nome, did

    def _linha_doc(self, did):
        con = self._db()
        try:
            return con.execute("SELECT * FROM prontuario_docs WHERE id=?", (did,)).fetchone()
        finally:
            con.close()

    def _numero(self, cid):
        con = self._db()
        try:
            return con.execute("SELECT numero FROM prontuarios WHERE cliente_id=?", (cid,)).fetchone()["numero"]
        finally:
            con.close()

    def test_lancar_sem_interno_cria_prontuario_e_nenhum_documento(self):
        cid, _ = self._cliente()
        self.assertEqual(self._lancar(cid).status_code, 302)
        numero = self._numero(cid)
        self.assertEqual(len(numero), 6)
        self.assertTrue(numero.isdigit())
        con = self._db()
        try:
            docs = con.execute("SELECT COUNT(*) FROM prontuario_docs WHERE cliente_id=?", (cid,)).fetchone()[0]
            interno = con.execute("SELECT interno FROM atendimentos WHERE cliente_id=?", (cid,)).fetchone()["interno"]
        finally:
            con.close()
        self.assertEqual(docs, 0)
        self.assertEqual(interno, 0)

    def test_interno_sem_local_nao_grava(self):
        cid, _ = self._cliente()
        r = self._lancar(cid, interno=True, local="")
        self.assertEqual(r.status_code, 200)
        con = self._db()
        try:
            atend = con.execute("SELECT COUNT(*) FROM atendimentos WHERE cliente_id=?", (cid,)).fetchone()[0]
            prontuarios = con.execute("SELECT COUNT(*) FROM prontuarios WHERE cliente_id=?", (cid,)).fetchone()[0]
        finally:
            con.close()
        self.assertEqual(atend, 0)
        self.assertEqual(prontuarios, 0)

    def test_interno_com_local_cria_sbar_pendente_ligado_ao_atendimento(self):
        cid, _ = self._cliente()
        self.assertEqual(self._lancar(cid, interno=True, local="HOSPITAL TESTE - UTI, LEITO 3").status_code, 302)
        con = self._db()
        try:
            at = con.execute("SELECT id, interno, interno_local FROM atendimentos WHERE cliente_id=?", (cid,)).fetchone()
            docs = con.execute("SELECT * FROM prontuario_docs WHERE cliente_id=?", (cid,)).fetchall()
        finally:
            con.close()
        self.assertEqual(at["interno"], 1)
        self.assertEqual(at["interno_local"], "HOSPITAL TESTE - UTI, LEITO 3")
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0]["tipo"], "sbar")
        self.assertEqual(docs[0]["situacao"], "PENDENTE")
        self.assertEqual(docs[0]["atendimento_id"], at["id"])
        dados = json.loads(docs[0]["dados"])
        self.assertEqual(dados["hospital_setor"], "HOSPITAL TESTE - UTI, LEITO 3")
        self.assertEqual(dados["exame"], EXAME)

    def test_mesmo_paciente_mantem_o_mesmo_numero(self):
        cid, _ = self._cliente()
        self._lancar(cid)
        numero = self._numero(cid)
        self._lancar(cid, interno=True, local="OUTRO HOSPITAL")
        self.assertEqual(self._numero(cid), numero)
        con = self._db()
        try:
            total = con.execute("SELECT COUNT(*) FROM prontuarios WHERE cliente_id=?", (cid,)).fetchone()[0]
        finally:
            con.close()
        self.assertEqual(total, 1)

    def test_lista_mostra_a_pendencia(self):
        _, nome, _ = self._sbar_pendente(local="HOSP LISTA")
        texto = self.texto(self.c.get("/prontuario"))
        self.assertIn("Documentos pendentes", texto)
        self.assertIn("HOSP LISTA", texto)
        self.assertIn(nome, texto)

    def test_abrir_documento_mostra_etapas_e_sugestoes(self):
        _, _, did = self._sbar_pendente()
        r = self.c.get("/prontuario/doc/%d" % did)
        self.assertEqual(r.status_code, 200)
        texto = self.texto(r)
        for trecho in ("Situação", "Breve histórico", "Avaliação", "Recomendação", "Nega alergias"):
            self.assertIn(trecho, texto)

    def test_salvar_rascunho_grava_os_dados(self):
        _, _, did = self._sbar_pendente()
        r = self.post(self.c, "/prontuario/doc/%d" % did, {"acao": "rascunho", "estado_geral": "Sonolento, responde a estímulos",
                                                           "exame": EXAME})
        self.assertEqual(r.status_code, 302)
        doc = self._linha_doc(did)
        self.assertEqual(doc["situacao"], "RASCUNHO")
        self.assertEqual(json.loads(doc["dados"])["estado_geral"], "Sonolento, responde a estímulos")

    def test_concluir_sem_nome_do_profissional_nao_conclui(self):
        _, _, did = self._sbar_pendente()
        r = self.post(self.c, "/prontuario/doc/%d" % did, _completo(profissional_nome="", acao="concluir"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self._linha_doc(did)["situacao"], "RASCUNHO")

    def test_concluir_com_nome_e_obrigatorios_fecha_e_nao_altera_depois(self):
        _, _, did = self._sbar_pendente()
        r = self.post(self.c, "/prontuario/doc/%d" % did, _completo(acao="concluir"))
        self.assertEqual(r.status_code, 302)
        doc = self._linha_doc(did)
        self.assertEqual(doc["situacao"], "CONCLUIDO")
        self.assertEqual(doc["profissional_nome"], "ENF. TESTE")
        antes = doc["dados"]
        r = self.post(self.c, "/prontuario/doc/%d" % did, _completo(estado_geral="Outro estado", acao="rascunho"))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self._linha_doc(did)["dados"], antes)

    def test_impressao_tem_logo_numero_e_profissional(self):
        cid, _, did = self._sbar_pendente()
        self.post(self.c, "/prontuario/doc/%d" % did, _completo(acao="concluir"))
        r = self.c.get("/prontuario/doc/%d/imprimir" % did)
        self.assertEqual(r.status_code, 200)
        texto = self.texto(r)
        self.assertIn("image1.jpeg", texto)
        self.assertIn("Prontuário nº %s" % self._numero(cid), texto)
        self.assertIn("ENF. TESTE", texto)
        self.assertIn("Assinatura do profissional", texto)

    def test_impressao_em_branco(self):
        _, _, did = self._sbar_pendente()
        r = self.c.get("/prontuario/doc/%d/imprimir?branco=1" % did)
        self.assertEqual(r.status_code, 200)
        self.assertIn("image1.jpeg", self.texto(r))

    def test_permissao_pelo_modulo_prontuario(self):
        self.criar_usuario("PRONT_SEM", modulos=["atendimentos"])
        sem = self.cliente("PRONT_SEM", "senha123")
        self.assertEqual(sem.get("/prontuario").status_code, 302)
        self.criar_usuario("PRONT_COM", modulos=["prontuario"])
        com = self.cliente("PRONT_COM", "senha123")
        self.assertEqual(com.get("/prontuario").status_code, 200)

    def test_historico_do_paciente_lista_o_atendimento(self):
        cid, _ = self._cliente()
        self._lancar(cid)
        r = self.c.get("/prontuario/paciente/%d" % cid)
        self.assertEqual(r.status_code, 200)
        self.assertIn(EXAME, self.texto(r))
        self.assertEqual(self.c.get("/prontuario/paciente/999999").status_code, 404)


class DocumentosNovosTestes(Base):
    """SAE, PNT, ficha MIBI, NEWS, radiofármaco, anamnese, evolução e checklist."""

    TIPOS = ["sae", "pnt", "ficha_mibi", "news", "radiofarmaco", "anamnese", "evolucao", "checklist"]

    def setUp(self):
        self.c = self.cliente()
        self.seq = 0

    def _db(self):
        return dbmod.conectar(self.app.config["DATABASE"])

    def _cliente(self):
        self.seq += 1
        con = self._db()
        try:
            cur = con.execute("INSERT INTO clientes (nome, data_nasc, sexo) VALUES (?,?,?)",
                              ("PACIENTE NOVO %d" % self.seq, "1958-03-02", "F"))
            con.commit()
            return cur.lastrowid
        finally:
            con.close()

    def _atendimento(self, cid, exame, medicamentos="LOSARTANA 50 MG"):
        con = self._db()
        try:
            cur = con.execute("INSERT INTO atendimentos (cliente_id, cliente_nome, medico, data, exame, convenio, medicamentos, "
                              "usuario, criado_em) VALUES (?,?,?,?,?,?,?,?,?)",
                              (cid, "PACIENTE", "DR TESTE", "2026-11-10", exame, "PARTICULAR", medicamentos, "ADMIN",
                               "2026-11-10 10:00:00"))
            con.commit()
            return cur.lastrowid
        finally:
            con.close()

    def _doc(self, cid, tipo, aid=None):
        con = self._db()
        try:
            did = prontuario.criar_doc(con, cid, tipo, "ADMIN", atendimento_id=aid, situacao="RASCUNHO")
            con.commit()
            return did
        finally:
            con.close()

    def _dados(self, did):
        con = self._db()
        try:
            return json.loads(con.execute("SELECT dados FROM prontuario_docs WHERE id=?", (did,)).fetchone()["dados"])
        finally:
            con.close()

    def test_tipos_novos_abrem_e_imprimem(self):
        cid = self._cliente()
        for tipo in self.TIPOS:
            did = self._doc(cid, tipo)
            self.assertEqual(self.c.get("/prontuario/doc/%d" % did).status_code, 200, tipo)
            self.assertEqual(self.c.get("/prontuario/doc/%d/imprimir" % did).status_code, 200, tipo)
            self.assertEqual(self.c.get("/prontuario/doc/%d/imprimir?branco=1" % did).status_code, 200, tipo)

    def test_news_calcula_risco_alto(self):
        did = self._doc(self._cliente(), "news")
        self.post(self.c, "/prontuario/doc/%d" % did, {"acao": "rascunho", "fr": "26", "spo2": "91", "o2": "Sim", "temp": "39,5",
                                                       "pas": "85", "fc": "135", "consciencia": "Voz"})
        dados = self._dados(did)
        self.assertEqual(dados["pontuacao"], "19")
        self.assertEqual(dados["risco"], "Alto")

    def test_news_normal_da_zero_e_baixo(self):
        did = self._doc(self._cliente(), "news")
        self.post(self.c, "/prontuario/doc/%d" % did, {"acao": "rascunho", "fr": "16", "spo2": "98", "temp": "36,5",
                                                       "pas": "120", "fc": "75", "consciencia": "Alerta"})
        dados = self._dados(did)
        self.assertEqual(dados["pontuacao"], "0")
        self.assertEqual(dados["risco"], "Baixo")

    def test_escore_de_calcio_soma(self):
        did = self._doc(self._cliente(), "ficha_mibi")
        self.post(self.c, "/prontuario/doc/%d" % did, {"acao": "rascunho", "da": "1", "cx": "2", "cd": "3"})
        self.assertEqual(self._dados(did)["escore_total"], "6")

    def test_sae_tem_tres_linhas_de_assinatura(self):
        did = self._doc(self._cliente(), "sae")
        texto = self.texto(self.c.get("/prontuario/doc/%d/imprimir" % did))
        self.assertEqual(texto.count("Técnico de Enfermagem/Enfermeiro"), 3)

    def test_pnt_grava_respostas_no_atendimento_e_ficha_sai_preenchida(self):
        cid = self._cliente()
        aid = self._atendimento(cid, "MIBI")
        did = self._doc(cid, "pnt", aid)
        self.assertIn("Imprimir na ficha original", self.texto(self.c.get("/prontuario/doc/%d" % did)))
        perguntas = self._dados(did)["_pnt_perguntas"]
        com_justificativa = next(i for i, (_t, rot) in enumerate(perguntas, 1) if rot)   # primeira pergunta com justificativa
        self.post(self.c, "/prontuario/doc/%d" % did, {"acao": "rascunho", "r1": "SIM", "r%d" % com_justificativa: "SIM",
                                                       "o%d" % com_justificativa: "ASMA LEVE"})
        con = self._db()
        try:
            respostas = json.loads(con.execute("SELECT respostas FROM atendimentos WHERE id=?", (aid,)).fetchone()["respostas"])
        finally:
            con.close()
        self.assertEqual(respostas.get("r1"), "SIM")
        self.assertEqual(respostas.get("o%d" % com_justificativa), "ASMA LEVE")
        self.assertNotIn("manual", respostas)
        self.assertIn("( X ) SIM", self.texto(self.c.get("/atendimentos/%d/imprimir" % aid)))

    def test_sugeridos_aparecem_para_mibi(self):
        cid = self._cliente()
        self._atendimento(cid, "MIBI")
        texto = self.texto(self.c.get("/prontuario/paciente/%d" % cid))
        for sigla in ("+ SAE", "+ PNT", "+ MIBI", "+ NEWS", "+ RADIO"):
            self.assertIn(sigla, texto)


if __name__ == "__main__":
    unittest.main()
