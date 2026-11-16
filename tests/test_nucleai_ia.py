"""NucleAI IA (OpenRouter): estado, liberação com código, níveis, limites, registro e treinadores."""
import unittest
from datetime import datetime, timedelta

from app import db as dbmod
from app import nucleai_ia as ia
from tests.test_chat_blindagens import Base


class NucleaiIA(Base):
    def setUp(self):
        self.u = self.criar_usuario("IA_FUNC", ["agenda"])
        self.con = dbmod.conectar(self.app.config["DATABASE"])
        for tabela in ("nucleai_llm_nivel", "nucleai_llm_uso", "nucleai_llm_log", "nucleai_treinadores"):
            self.con.execute("DELETE FROM %s" % tabela)
        self.con.execute("DELETE FROM config WHERE chave LIKE 'nucleai_llm_%'")
        self.con.commit()

    def tearDown(self):
        self.con.close()

    def ligar(self):
        ia.definir(self.con, "nucleai_llm_ativo", "1")

    # ---------------------------------------------------------------- estado
    def test_padrao_em_treino_e_desligada(self):
        self.assertEqual(ia.estado(self.con), ia.TREINO)
        self.assertFalse(ia.ia_ligada(self.con))
        self.assertFalse(ia.pode_usar_ia(self.con, self.u, treino=True))

    def test_em_treino_so_o_chat_treinador_usa(self):
        self.ligar()
        ia.definir_nivel(self.con, self.u, 4, "ADMIN")
        self.assertTrue(ia.pode_usar_ia(self.con, self.u, treino=True))
        self.assertFalse(ia.pode_usar_ia(self.con, self.u))

    def test_estado_invalido(self):
        with self.assertRaises(ValueError):
            ia.definir_estado(self.con, "QUALQUER")

    # ---------------------------------------------------------------- liberação
    def test_liberar_com_codigo_certo(self):
        codigo = ia.gerar_codigo_liberacao(self.con)
        self.assertRegex(codigo, r"^\d{6}$")
        self.assertTrue(ia.liberar(self.con, codigo, "ADMIN"))
        self.assertEqual(ia.estado(self.con), ia.LIBERADA)
        self.assertTrue(ia.ia_ligada(self.con))
        self.assertTrue(ia.cfg(self.con, "nucleai_llm_desde"))
        # com nível 0 o usuário continua na versão por regras; com nível 1 passa
        self.assertFalse(ia.pode_usar_ia(self.con, self.u))
        ia.definir_nivel(self.con, self.u, 1, "ADMIN")
        self.assertTrue(ia.pode_usar_ia(self.con, self.u))
        eventos = self.con.execute("SELECT COUNT(*) FROM nucleai_llm_log WHERE modo='EVENTO'").fetchone()[0]
        self.assertEqual(eventos, 1)

    def test_codigo_errado_nao_libera(self):
        codigo = ia.gerar_codigo_liberacao(self.con)
        errado = "000000" if codigo != "000000" else "111111"
        self.assertFalse(ia.liberar(self.con, errado, "ADMIN"))
        self.assertEqual(ia.estado(self.con), ia.TREINO)
        self.assertFalse(ia.liberar(self.con, "", "ADMIN"))

    def test_codigo_nao_reutilizavel(self):
        codigo = ia.gerar_codigo_liberacao(self.con)
        self.assertTrue(ia.liberar(self.con, codigo, "ADMIN"))
        ia.desativar(self.con, "ADMIN")
        self.assertFalse(ia.liberar(self.con, codigo, "ADMIN"))

    def test_codigo_expira(self):
        codigo = ia.gerar_codigo_liberacao(self.con)
        velho = (datetime.now() - timedelta(minutes=ia.CODIGO_VALIDADE_MIN + 1)).strftime(ia.FMT)
        ia.definir(self.con, "nucleai_llm_codigo_em", velho)
        self.assertFalse(ia.liberar(self.con, codigo, "ADMIN"))
        self.assertEqual(ia.cfg(self.con, "nucleai_llm_codigo"), "")

    def test_desativar_devolve_todos_as_regras(self):
        self.assertTrue(ia.liberar(self.con, ia.gerar_codigo_liberacao(self.con), "ADMIN"))
        ia.definir_nivel(self.con, self.u, 4, "ADMIN")
        ia.desativar(self.con, "ADMIN")
        self.assertEqual(ia.estado(self.con), ia.DESATIVADA)
        self.assertFalse(ia.pode_usar_ia(self.con, self.u))
        self.assertFalse(ia.pode_usar_ia(self.con, self.u, treino=True))
        self.assertEqual(ia.cfg(self.con, "nucleai_llm_desde"), "")

    # ---------------------------------------------------------------- níveis
    def test_niveis(self):
        self.assertEqual(ia.nivel(self.con, self.u), 0)
        for n in range(5):
            ia.definir_nivel(self.con, self.u, n, "ADMIN")
            self.assertEqual(ia.nivel(self.con, self.u), n)
        for ruim in (-1, 5, "2", True):
            with self.assertRaises(ValueError):
                ia.definir_nivel(self.con, self.u, ruim, "ADMIN")

    def test_nivel_padrao_da_config(self):
        ia.definir(self.con, "nucleai_llm_padrao_nivel", "2")
        self.assertEqual(ia.nivel(self.con, self.u), 2)

    # ---------------------------------------------------------------- limites
    def test_sem_nivel_fora_do_limite(self):
        ok, motivo = ia.dentro_do_limite(self.con, self.u)
        self.assertFalse(ok)
        self.assertIn("acesso", motivo)

    def test_limite_diario(self):
        ia.definir_nivel(self.con, self.u, 1, "ADMIN")
        ia.definir(self.con, "nucleai_llm_limite_dia_n1", "2")
        ia.definir(self.con, "nucleai_llm_limite_min", "60")
        self.assertTrue(ia.dentro_do_limite(self.con, self.u)[0])
        ia.registrar_uso(self.con, self.u, 100)
        ia.registrar_uso(self.con, self.u, 50)
        self.assertEqual(ia.usos_hoje(self.con, self.u), 2)
        tokens = self.con.execute("SELECT tokens FROM nucleai_llm_uso WHERE usuario_id=?", (self.u,)).fetchone()[0]
        self.assertEqual(tokens, 150)
        ok, motivo = ia.dentro_do_limite(self.con, self.u)
        self.assertFalse(ok)
        self.assertIn("diário", motivo)

    def test_limite_por_minuto(self):
        ia.definir_nivel(self.con, self.u, 4, "ADMIN")
        ia.definir(self.con, "nucleai_llm_limite_min", "2")
        ia.registrar_log(self.con, self.u, "IA_FUNC", "p1", "r1")
        self.assertTrue(ia.dentro_do_limite(self.con, self.u)[0])
        ia.registrar_log(self.con, self.u, "IA_FUNC", "p2", "r2")
        ok, motivo = ia.dentro_do_limite(self.con, self.u)
        self.assertFalse(ok)
        self.assertIn("minuto", motivo)

    # ---------------------------------------------------------------- registro e contadores
    def test_contadores(self):
        ia.registrar_log(self.con, self.u, "IA_FUNC", "p", "r", ferramentas=[{"nome": "x"}], tokens=10)
        ia.registrar_log(self.con, self.u, "IA_FUNC", "p", "r", modo="REGRAS")
        c = ia.contadores(self.con)
        self.assertEqual(c["respostas"], 1)
        self.assertEqual(c["tempo_ativa_s"], 0)
        ia.definir_estado(self.con, ia.LIBERADA)
        ia.definir(self.con, "nucleai_llm_desde", (datetime.now() - timedelta(hours=1)).strftime(ia.FMT))
        self.assertGreaterEqual(ia.contadores(self.con)["tempo_ativa_s"], 3590)
        f = self.con.execute("SELECT ferramentas FROM nucleai_llm_log WHERE modo='IA'").fetchone()[0]
        self.assertIn('"nome"', f)

    # ---------------------------------------------------------------- treinadores e conversas de teste
    def test_treinador_criado_com_padroes(self):
        t = ia.treinador(self.con, "Treinador#0001")
        self.assertEqual((t["formalidade"], t["tamanho"], t["forca"]), (3, 3, 3))
        self.assertEqual(ia.treinador(self.con, "Treinador#0001")["id"], t["id"])
        self.assertEqual(len(ia.listar_treinadores(self.con)), 1)
        # Teste#XXXX também é aceito e criado com padrões
        t2 = ia.treinador(self.con, "Teste#1234")
        self.assertEqual(t2["nome"], "Teste#1234")
        self.assertEqual(len(ia.listar_treinadores(self.con)), 2)

    def test_gerar_nome_teste(self):
        nome = ia.novo_nome_teste()
        self.assertRegex(nome, r"^Teste#\d{4}$")
        self.assertTrue(ia.NOME_TREINADOR.fullmatch(nome))

    def test_nome_de_treinador_invalido(self):
        for ruim in ("Treinador", "Treinador#1", "#0001", "a" * 31 + "#0001", "Tre;inador#0001"):
            with self.assertRaises(ValueError):
                ia.treinador(self.con, ruim)

    def test_config_treinador_limites(self):
        t = ia.config_treinador(self.con, "Ana#0002", tratamento="Dra. Ana", formalidade=9, tamanho=0, forca=4,
                                desconhecido="x")
        self.assertEqual(t["tratamento"], "Dra. Ana")
        self.assertEqual((t["formalidade"], t["tamanho"], t["forca"]), (5, 1, 4))


if __name__ == "__main__":
    unittest.main()
