"""Aviso antes da atualização: mensagem a todos os usuários com prazo, consulta local do instalador e permissões."""
import unittest
from datetime import datetime

from app import atualizacao
from app import db as dbmod
from tests.test_chat_blindagens import Base


class AtualizacaoTestes(Base):
    def contar(self, sql, params=()):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            return con.execute(sql, params).fetchone()[0]
        finally:
            con.close()

    def test_disparo_avisa_todos_e_o_instalador_consulta(self):
        uid = self.criar_usuario("ATU_A", ["atendimentos"])
        c = self.cliente()
        self.assertEqual(self.post(c, "/atualizacao/avisar", {"prazo": "10"}).status_code, 302)
        self.assertGreaterEqual(self.contar("SELECT COUNT(*) FROM chat_mensagens WHERE para_id=? AND corpo LIKE '%atualizado%'", (uid,)), 1)
        self.assertEqual(self.contar("SELECT COUNT(*) FROM atualizacao_avisos"), 1)
        # o instalador (no próprio computador) vê o aviso pendente
        r = self.app.test_client().get("/atualizacao/pendente").get_json()
        self.assertTrue(r["pendente"])
        self.assertEqual(r["prazo_min"], 10)

    def test_prazo_invalido_e_sem_permissao(self):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            with self.assertRaises(atualizacao.ErroAtualizacao):
                atualizacao.disparar(con, "TESTE", 0)
            with self.assertRaises(atualizacao.ErroAtualizacao):
                atualizacao.disparar(con, "TESTE", 500)
        finally:
            con.close()
        self.criar_usuario("ATU_SEM", ["atendimentos"])
        # sem o módulo de backup nem de gerência, o sistema não deixa a rota rodar (volta ao início)
        self.assertEqual(self.post(self.cliente("ATU_SEM", "senha123"), "/atualizacao/avisar", {"prazo": "5"}).status_code, 302)

    def test_consulta_fora_do_computador_e_bloqueada(self):
        c = self.app.test_client()
        c.environ_base["REMOTE_ADDR"] = "10.0.0.5"
        self.assertEqual(c.get("/atualizacao/pendente").status_code, 403)

    def test_sem_aviso_em_andamento(self):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            self.assertIsNone(atualizacao.pendente(con, datetime(2999, 1, 1)))  # daqui a muito tempo, nenhum aviso ativo
        finally:
            con.close()


if __name__ == "__main__":
    unittest.main()
