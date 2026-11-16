"""Telas da pesquisa de satisfação: questionário impresso, lançamento manual, tipos de pergunta e respostas."""
import unittest
from datetime import date, timedelta

from app import pesquisa as pesq
from app.db import get_db
from tests.test_chat_blindagens import Base


class TelasPesquisa(Base):
    PERGUNTAS = ['Atendimento geral', 'Confirmou seu nome e data de nascimento?', 'Recomendaria a clínica?']
    TIPOS = ['ESCALA', 'SIMNAO', 'NPS']

    def setUp(self):
        self.adm = self.cliente()
        self.post(self.adm, "/qualidade/satisfacao/perguntas", {"pergunta": self.PERGUNTAS, "tipo": self.TIPOS})

    def ids(self):
        with self.app.app_context():
            return [p["id"] for p in pesq.perguntas(get_db())]

    def respostas(self):
        with self.app.app_context():
            return pesq.lista_respostas(get_db(), "2000-01-01", "2100-01-01")

    def test_impresso_tem_perguntas_e_legenda_nps(self):
        r = self.adm.get("/qualidade/satisfacao/impresso")
        self.assertEqual(r.status_code, 200)
        t = self.texto(r)
        for texto in self.PERGUNTAS:
            self.assertIn(texto, t)
        self.assertIn("0 = nada provável", t)

    def test_tela_de_perguntas_com_tipo_e_impressao(self):
        r = self.adm.get("/qualidade/satisfacao")
        self.assertEqual(r.status_code, 200)
        t = self.texto(r)
        self.assertIn('name="tipo"', t)
        self.assertIn("Imprimir questionário", t)

    def test_tela_de_lancar_abre(self):
        r = self.adm.get("/qualidade/satisfacao/lancar")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Lançar questionário impresso", self.texto(r))

    def test_lancar_grava_resposta_impressa_do_usuario(self):
        p1, p2, p3 = self.ids()
        antes = len(self.respostas())
        r = self.post(self.adm, "/qualidade/satisfacao/lancar", {
            "data": date.today().isoformat(), "exame": "", "atendimento": "Particular", "respondente": "Paciente",
            "p%d" % p1: "Ótimo", "p%d" % p2: "Sim", "p%d" % p3: "",
        })
        self.assertEqual(r.status_code, 302)
        rs = self.respostas()
        self.assertEqual(len(rs), antes + 1)
        nova = rs[0]
        self.assertEqual(nova["origem"], "IMPRESSO")
        self.assertEqual(nova["lancado_por"], "ADMIN")

    def test_lancar_com_data_futura_mostra_erro(self):
        p1, p2, p3 = self.ids()
        antes = len(self.respostas())
        amanha = (date.today() + timedelta(days=1)).isoformat()
        r = self.post(self.adm, "/qualidade/satisfacao/lancar", {"data": amanha, "p%d" % p1: "Bom"})
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("Pode lançar o próximo", self.texto(r))
        self.assertEqual(len(self.respostas()), antes)

    def test_pesquisa_publica_mostra_opcoes_novas(self):
        t = self.texto(self.app.test_client().get("/pesquisa"))
        self.assertIn("Prefiro não informar", t)
        self.assertIn(">Sim<", t)
        self.assertIn(">Não<", t)
        self.assertIn('value="10"', t)
        self.assertIn('value="0"', t)

    def test_salvar_tipos_das_perguntas(self):
        with self.app.app_context():
            tipos = [p["tipo"] for p in pesq.perguntas(get_db())]
        self.assertEqual(tipos, self.TIPOS)

    def test_respostas_mostram_seguranca_do_paciente(self):
        p1, p2, p3 = self.ids()
        self.post(self.adm, "/qualidade/satisfacao/lancar", {
            "data": date.today().isoformat(), "p%d" % p2: "Sim",
        })
        t = self.texto(self.adm.get("/qualidade/satisfacao/respostas"))
        self.assertIn("Segurança do paciente", t)
        self.assertIn("Impresso", t)


if __name__ == "__main__":
    unittest.main()
