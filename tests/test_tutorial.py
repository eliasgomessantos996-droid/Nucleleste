"""Tutorial animado da NucleAI: roteiro personalizado pelos módulos, abertura no primeiro acesso e botão para rever."""
import json
import re
import unittest

from app import db as dbmod
from app import tutorial as t
from tests.test_chat_blindagens import Base

# Referer do próprio sistema: clicar em Início no menu manda esse cabeçalho (sem ele, a raiz leva à agenda)
DE_SISTEMA = {"Referer": "http://localhost/"}

def _menu(*grupos):
    return [(None, [{"rotulo": "Início"}, {"rotulo": "Mensagens"}])] + [(g, [{"rotulo": g + " x"}]) for g in grupos]


def _grupos(passos):
    return [p["valor"] for p in passos if p["tipo"] == "grupo"]


class Roteiro(unittest.TestCase):
    def test_financeiro_sem_agenda_comeca_pelo_financeiro(self):
        self.assertEqual(_grupos(t.montar(_menu("Cadastros", "Financeiro")))[0], "Financeiro")

    def test_recepcao_comeca_por_lancamentos_e_agenda(self):
        self.assertEqual(_grupos(t.montar(_menu("Financeiro", "Agenda", "Lançamentos", "Cadastros")))[:2], ["Lançamentos", "Agenda"])

    def test_quem_ve_tudo_segue_a_ordem_padrao(self):
        grupos = ("Lançamentos", "Agenda", "Cadastros", "Financeiro", "Documentos", "Qualidade", "Configuração")
        self.assertEqual(_grupos(t.montar(_menu(*grupos))), list(grupos))

    def test_so_aparece_o_que_o_usuario_tem(self):
        passos = t.montar(_menu("Banco de Horas"))
        self.assertEqual(_grupos(passos), ["Banco de Horas"])
        self.assertNotIn("Financeiro", json.dumps(passos, ensure_ascii=False))

    def test_abre_e_fecha_com_conversa(self):
        passos = t.montar(_menu("Financeiro"), "maria souza")
        self.assertEqual(passos[0]["tipo"], "centro")
        self.assertIn("Maria", passos[0]["titulo"])
        self.assertNotIn("Souza", passos[0]["titulo"])
        self.assertEqual(passos[-1]["tipo"], "centro")


class Telas(Base):
    def _auto(self, pagina):
        return json.loads(re.search(r'id="tutorial-dados">(.*?)</script>', pagina, re.S).group(1))

    def test_primeiro_acesso_abre_sozinho_e_depois_nao(self):
        self.criar_usuario("NOVO1", ["atendimentos", "agenda"])
        c = self.cliente("NOVO1", "senha123")
        dados = self._auto(self.texto(c.get("/", headers=DE_SISTEMA)))
        self.assertTrue(dados["auto"])
        self.assertIn("Agenda", [p.get("valor") for p in dados["passos"]])
        self.assertEqual(c.post("/ajuda/tutorial-visto", headers={"X-CSRF-Token": self._token(c)}).status_code, 204)
        self.assertFalse(self._auto(self.texto(c.get("/", headers=DE_SISTEMA)))["auto"])

    def _token(self, c):
        with c.session_transaction() as s:
            return s["csrf"]

    def test_botao_de_rever_em_minha_conta_e_no_menu(self):
        c = self.cliente()
        self.assertIn("data-tutorial-iniciar", self.texto(c.get("/minha-senha")))
        self.assertIn("Rever o tutorial", self.texto(c.get("/", headers=DE_SISTEMA)))

    def test_usuario_sem_modulo_financeiro_nao_ve_passo_financeiro(self):
        self.criar_usuario("REC9", ["atendimentos"])
        dados = self._auto(self.texto(self.cliente("REC9", "senha123").get("/")))
        self.assertNotIn("Financeiro", [p.get("valor") for p in dados["passos"]])

    def test_coluna_nova_existe(self):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            colunas = [r[1] for r in con.execute("PRAGMA table_info(usuarios)")]
        finally:
            con.close()
        self.assertIn("tutorial_visto", colunas)


if __name__ == "__main__":
    unittest.main()
