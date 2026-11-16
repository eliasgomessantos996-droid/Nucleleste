"""Questionário das fichas PNT no lançamento do atendimento: perguntas por ficha, justificativa só com SIM e Preencher manual."""
import json
import unittest

from app import db as dbmod
from app import fichas, views_atendimentos
from tests.test_chat_blindagens import Base


class Perguntas(Base):
    def test_cada_pnt_tem_questionario_na_ordem_da_ficha(self):
        for slug in ("pnt_linfonodo", "pnt_mibi", "pnt_ossea", "pnt_renal", "pnt_pulmonar", "pnt_spect", "pnt_tgi", "pnt_paratgi"):
            self.assertTrue(fichas.QUESTIONARIOS[slug], slug)

    def test_exame_usa_a_ficha_pnt_que_imprime(self):
        with self.app.app_context():
            con = dbmod.conectar(self.app.config["DATABASE"])
            try:
                mibi = con.execute("SELECT * FROM exames WHERE nome='MIBI'").fetchone()
                linfo = con.execute("SELECT * FROM exames WHERE nome='LINFONODO'").fetchone()
                slug, perguntas = fichas.questionario_do_exame(mibi)
                self.assertEqual(slug, "pnt_mibi")
                self.assertEqual(len(perguntas), 8)
                self.assertEqual(fichas.questionario_do_exame(linfo)[0], "pnt_linfonodo")
                self.assertEqual(fichas.questionario_do_exame(None), (None, []))
            finally:
                con.close()

    def test_justificativa_so_nas_perguntas_que_pedem_detalhe(self):
        linfo = fichas.QUESTIONARIOS["pnt_linfonodo"]
        self.assertEqual(linfo[0][1], "Qual mama ou qual câncer?")
        self.assertEqual(linfo[2][1], "Qual(is)?")
        self.assertIsNone(linfo[3][1])                     # gravidez: sem campo extra


class Respostas(Base):
    def setUp(self):
        super().setUp()
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            con.execute("DELETE FROM atendimentos")
            con.execute("DELETE FROM guias")
            con.execute("DELETE FROM caixa")
            con.commit()
        finally:
            con.close()

    def test_justificativa_so_guardada_com_sim(self):
        lidas = {"manual": 0, "itens": [{"r": "SIM", "o": "MAMA ESQUERDA"}, {"r": "NÃO", "o": "ALGUMA COISA"}]}
        self.assertEqual(views_atendimentos._gravar_respostas(lidas, fichas.QUESTIONARIOS["pnt_linfonodo"][:2]),
                         {"r1": "SIM", "o1": "MAMA ESQUERDA", "r2": "NÃO"})

    def test_manual_fica_marcado(self):
        lidas = {"manual": 1, "itens": [{"r": "", "o": ""}] * 4}
        self.assertEqual(views_atendimentos._gravar_respostas(lidas, fichas.QUESTIONARIOS["pnt_linfonodo"]), {"manual": 1})

    def _lancar(self, **extra):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            cid = con.execute("INSERT INTO clientes (nome, convenio) VALUES ('PACIENTE PNT', 'UNIMED')").lastrowid   # convênio é obrigatório
            con.commit()
        finally:
            con.close()
        dados = {"cliente_id": str(cid), "exame": "LINFONODO", "data": "2026-10-10", "medico": "DR TESTE"}
        dados.update(extra)
        self.post(self.cliente(), "/atendimentos/novo", dados)

    def _atendimentos(self):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            return [dict(r) for r in con.execute("SELECT * FROM atendimentos WHERE exame='LINFONODO'")]
        finally:
            con.close()

    def test_sem_respostas_e_sem_manual_nao_libera(self):
        self._lancar()
        self.assertEqual(self._atendimentos(), [])

    def test_preencher_manual_libera_sem_respostas(self):
        self._lancar(manual="1")
        at = self._atendimentos()
        self.assertEqual(len(at), 1)
        self.assertEqual(json.loads(at[0]["respostas"]), {"manual": 1})

    def test_respostas_com_justificativa_gravadas(self):
        self._lancar(r1="SIM", o1="DIREITA", r2="NÃO", o2="IGNORADA", r3="NÃO", r4="NÃO")
        at = self._atendimentos()
        self.assertEqual(len(at), 1)
        self.assertEqual(json.loads(at[0]["respostas"]), {"r1": "SIM", "o1": "DIREITA", "r2": "NÃO", "r3": "NÃO", "r4": "NÃO"})

    def test_impressao_mostra_resposta_e_justificativa(self):
        self._lancar(r1="SIM", o1="DIREITA", r2="NÃO", r3="NÃO", r4="NÃO")
        aid = self._atendimentos()[0]["id"]
        pagina = self.texto(self.cliente().get("/atendimentos/%d/imprimir?d=pnt_linfonodo:1" % aid))
        self.assertIn("( X ) SIM", pagina)
        self.assertIn("DIREITA", pagina)

    def test_todas_as_fichas_pnt_imprimem_com_respostas(self):
        self._lancar(r1="NÃO", r2="NÃO", r3="NÃO", r4="NÃO")
        aid = self._atendimentos()[0]["id"]
        c = self.cliente()
        for slug in fichas.QUESTIONARIOS:
            self.assertEqual(c.get("/atendimentos/%d/imprimir?d=%s:1" % (aid, slug)).status_code, 200, slug)


if __name__ == "__main__":
    unittest.main()
