"""Usuário cadastrado no ponto (com Minha área) continua pesquisando clientes e médicos no lançamento; o atalho da agenda aparece no menu."""
from app import db as dbmod
from tests.test_chat_blindagens import Base


class BuscaFuncionario(Base):
    def test_api_de_busca_responde_para_quem_tem_conta_do_ponto(self):
        uid = self.criar_usuario("JULIA_T", ["atendimentos", "clientes", "bh_portal", "agenda"])
        con = dbmod.conectar(self.app.config["DATABASE"])
        con.execute("INSERT INTO clientes (nome) VALUES ('MARIA TESTE BUSCA')")
        con.execute("INSERT INTO bh_employees (clock_id, name, start_date, opening_balance_date, created_at, updated_at) VALUES ('T999', 'Julia Teste', '2026-01-01', '2026-01-01', '2026-01-01', '2026-01-01')")
        con.execute("UPDATE usuarios SET bh_funcionario_id=(SELECT MAX(id) FROM bh_employees) WHERE id=?", (uid,))
        con.commit()
        con.close()
        c = self.cliente("JULIA_T", "senha123")
        r = c.get("/api/clientes?q=maria teste")
        self.assertEqual(r.status_code, 200)
        self.assertIn("MARIA TESTE BUSCA", [x["nome"] for x in r.get_json()])
        self.assertEqual(c.get("/api/medicos?q=a").status_code, 200)
        self.assertEqual(c.get("/api/cpf?cpf=123").status_code, 200)
        self.assertEqual(c.get("/").status_code, 302)            # a tela inicial dela continua sendo a Minha área

    def test_atalho_da_agenda_no_topo_do_menu(self):
        self.criar_usuario("COM_AGENDA", ["agenda"])
        self.criar_usuario("SEM_AGENDA", ["atendimentos"])
        com = self.texto(self.cliente("COM_AGENDA", "senha123").get("/agenda"))
        self.assertIn('class="menu-agenda ativo"', com)
        self.assertLess(com.index("menu-agenda"), com.index("busca-menu"))
        sem = self.texto(self.cliente("SEM_AGENDA", "senha123").get("/atendimentos/novo"))
        self.assertNotIn('class="menu-agenda', sem)
