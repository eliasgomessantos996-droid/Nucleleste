"""Fichas "Plano terapêutico MDN", menu (Caixa em Financeiro) e exclusão em lote no movimento de caixa."""
import unittest

from app import db as dbmod
from app import fichas, fichas_plano, modulos
from tests.test_chat_blindagens import Base


class FichasPlano(Base):
    def test_fichas_criadas_uma_vez_e_preenchidas(self):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            titulos = [r["titulo"] for r in con.execute("SELECT titulo FROM fichas_extras WHERE titulo LIKE 'Plano terapêutico MDN%'")]
            self.assertEqual(len(titulos), len(fichas_plano.FICHAS))
            # excluída pela clínica, não volta na próxima inicialização
            con.execute("DELETE FROM fichas_extras WHERE titulo=?", ("Plano terapêutico MDN - Gálio",))
            con.commit()
            dbmod.inicializar(self.app.config["DATABASE"])
            self.assertIsNone(con.execute("SELECT 1 FROM fichas_extras WHERE titulo='Plano terapêutico MDN - Gálio'").fetchone())
            self.assertEqual(con.execute("SELECT COUNT(*) FROM fichas_extras WHERE titulo LIKE 'Plano terapêutico MDN%'").fetchone()[0],
                             len(fichas_plano.FICHAS) - 1)
        finally:
            con.close()

    def test_sem_dados_de_pacientes_dos_modelos(self):
        texto = " ".join(c for _, c in fichas_plano.FICHAS)
        for sobra in ("PAULO PEDRO", "JOSE LUIZ", "EDILANE", "SÃO LUCAS", "1956", "2024"):
            self.assertNotIn(sobra, texto)
        self.assertIn("{nome}", texto)
        self.assertIn("{nascimento}", texto)

    def test_aparecem_como_opcao_no_cadastro_de_exame(self):
        c = self.cliente()
        pagina = self.texto(c.get("/exames/novo")) if c.get("/exames/novo").status_code == 200 else ""
        self.assertIn("Plano terapêutico MDN - Samário", pagina)

    def test_renderiza_com_os_dados_do_paciente(self):
        conteudo = dict(fichas_plano.FICHAS)["Plano terapêutico MDN - MIBG"]
        with self.app.app_context():
            html = str(fichas.renderizar_texto(conteudo, {"nome": "MARIA TESTE", "nascimento": "01/02/1980", "convenio": "UNIMED",
                                                          "data": "10/10/2026"}))
        for esperado in ("MARIA TESTE", "01/02/1980", "UNIMED", "10/10/2026"):
            self.assertIn(esperado, html)


class MenuFinanceiro(Base):
    def test_caixa_e_movimento_ficam_em_financeiro(self):
        grupos = {g: [i[1] for i in itens] for g, itens in modulos.MENU}
        self.assertNotIn("Caixa", grupos["Lançamentos"])
        self.assertNotIn("Movimento de caixa", grupos["Lançamentos"])
        self.assertEqual(grupos["Financeiro"][:2], ["Caixa", "Movimento de caixa"])


class ExclusaoEmLote(Base):
    def _lancar(self, n, status="ABERTO"):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            ids = [con.execute("INSERT INTO caixa (data, cliente, status, valor) VALUES ('2026-01-01',?,?,10)",
                               ("CLIENTE %d" % i, status)).lastrowid for i in range(n)]
            con.commit()
            return ids
        finally:
            con.close()

    def _restantes(self, ids):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            return [i for i in ids if con.execute("SELECT 1 FROM caixa WHERE id=?", (i,)).fetchone()]
        finally:
            con.close()

    def test_excluir_marcados(self):
        ids = self._lancar(4)
        c = self.cliente()
        pagina = self.texto(c.get("/movimento-caixa?dia=2026-01-01"))   # a tela mostra só o dia escolhido
        self.assertIn('form="form-pend" name="ids"', pagina)
        self.post(c, "/movimento-caixa/excluir-varios", {"ids": [str(ids[0]), str(ids[2])]})
        self.assertEqual(self._restantes(ids), [ids[1], ids[3]])

    def test_excluir_todos_os_a_receber(self):
        ids = self._lancar(3)
        c = self.cliente()
        self.post(c, "/movimento-caixa/excluir-varios", {"todos": "pendentes", "dia": "2026-01-01"})   # "todos" = os da lista do dia
        self.assertEqual(self._restantes(ids), [])

    def test_so_administracao_e_gerencia(self):
        ids = self._lancar(2)
        self.criar_usuario("CAIXA1", ["movimento_caixa"])
        c = self.cliente("CAIXA1", "senha123")
        self.assertNotIn('form="form-pend" name="ids"', self.texto(c.get("/movimento-caixa")))
        self.post(c, "/movimento-caixa/excluir-varios", {"ids": [str(i) for i in ids]})
        self.assertEqual(self._restantes(ids), ids)

    def test_nada_selecionado_nao_apaga(self):
        ids = self._lancar(2)
        c = self.cliente()
        self.post(c, "/movimento-caixa/excluir-varios", {})
        self.assertEqual(self._restantes(ids), ids)


if __name__ == "__main__":
    unittest.main()
