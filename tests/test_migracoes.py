"""Migrações únicas: relatório sem gravar, aplicação uma vez só, telefones padronizados e sexo dos clientes."""
import os
import tempfile
import unittest

from app import db as dbmod
from app import migracoes


class MigracoesTestes(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.caminho = os.path.join(self.pasta.name, "teste.db")
        dbmod.inicializar(self.caminho)
        con = dbmod.conectar(self.caminho)
        con.execute("INSERT INTO clientes (nome, contato) VALUES ('ANA', '33999991234')")
        con.execute("INSERT INTO clientes (nome, contato) VALUES ('BIA', '3333334444')")
        con.execute("INSERT INTO clientes (nome, contato) VALUES ('CARLA', 'sem telefone')")
        con.execute("INSERT INTO realizacoes (data, paciente, cliente_id, sexo) VALUES ('2026-01-05', 'ANA', 1, 'F')")
        con.execute("INSERT INTO agenda_exames (data, exame, inicio, intervalo) VALUES ('2026-02-01', 'PET-CT', '08:00', 30)")
        con.execute("INSERT INTO agenda_horarios (agenda_id, hora, paciente, contato) VALUES (1, '08:00', 'DORA', '5533988887777')")
        con.execute("INSERT INTO agenda_espera (exame, nome, contato) VALUES ('PET-CT', 'EVA', '(33)9 9999-1111')")
        con.commit()
        con.close()

    def tearDown(self):
        self.pasta.cleanup()

    def conectar(self):
        return dbmod.conectar(self.caminho)

    def test_relatorio_nao_grava_nada(self):
        con = self.conectar()
        try:
            rel = migracoes.relatorio(con)
            self.assertEqual(rel[migracoes.TELEFONES]["total"], 4)  # dois clientes, a agenda e a lista de espera
            self.assertEqual(rel[migracoes.SEXO]["total"], 1)  # ANA ganha o sexo do exame realizado
            # a tabela de controle já existe (1.4.4 registra ali o zeramento do caixa), mas o relatório não marca nada
            self.assertEqual([r[0] for r in con.execute("SELECT nome FROM migracoes_aplicadas")], [migracoes.ZERAR_MOVIMENTO])
            self.assertEqual(con.execute("SELECT contato FROM clientes WHERE id=1").fetchone()[0], "33999991234")
        finally:
            con.close()

    def test_aplica_uma_vez_e_so_no_que_muda(self):
        con = self.conectar()
        try:
            migracoes.aplicar(con, migracoes.TELEFONES)
            migracoes.aplicar(con, migracoes.SEXO)
            self.assertEqual(con.execute("SELECT contato FROM clientes WHERE id=1").fetchone()[0], "(33)99999-1234")
            self.assertEqual(con.execute("SELECT contato FROM clientes WHERE id=2").fetchone()[0], "(33)3333-4444")
            self.assertEqual(con.execute("SELECT contato FROM clientes WHERE id=3").fetchone()[0], "sem telefone")  # não mexe
            self.assertEqual(con.execute("SELECT contato FROM agenda_horarios WHERE id=1").fetchone()[0], "(33)98888-7777")
            self.assertEqual(con.execute("SELECT contato FROM agenda_espera WHERE id=1").fetchone()[0], "(33)99999-1111")
            self.assertEqual(con.execute("SELECT sexo FROM clientes WHERE id=1").fetchone()[0], "F")
            with self.assertRaises(migracoes.ErroMigracao):
                migracoes.aplicar(con, migracoes.TELEFONES)  # não roda de novo
        finally:
            con.close()

    def test_relatorio_depois_de_aplicada_mostra_que_ja_foi(self):
        con = self.conectar()
        try:
            migracoes.aplicar(con, migracoes.TELEFONES)
            self.assertTrue(migracoes.relatorio(con)[migracoes.TELEFONES]["ja_aplicada"])
        finally:
            con.close()

    def test_copia_antes_de_aplicar(self):
        destino = migracoes.copia_do_banco(self.caminho)
        self.assertTrue(os.path.exists(destino))
        c = dbmod.conectar(destino)
        try:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM clientes").fetchone()[0], 3)
        finally:
            c.close()


if __name__ == "__main__":
    unittest.main()
