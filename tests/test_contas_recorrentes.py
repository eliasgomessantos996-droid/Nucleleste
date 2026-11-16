"""Contas a pagar recorrentes: geração mensal, dia 31 em fevereiro, idempotência, pausa, quitada, tela e permissão."""
import unittest
from datetime import date

from app import contas_recorrentes as rec
from app import db as dbmod
from tests.test_chat_blindagens import Base


class ContasRecorrentes(Base):
    def banco(self):
        return dbmod.conectar(self.app.config["DATABASE"])

    def datas(self, rid):
        con = self.banco()
        try:
            return [r["vencimento"] for r in con.execute(
                "SELECT vencimento FROM contas WHERE recorrente_id=? ORDER BY vencimento", (rid,)).fetchall()]
        finally:
            con.close()

    def criar(self, primeiro, dia, descricao="ALUGUEL TESTE", ativo=None):
        con = self.banco()
        try:
            rid = rec.salvar(con, {"descricao": descricao, "categoria": "Aluguel e condomínio", "valor": 100.0,
                                   "dia": str(dia), "obs": None}, "TESTE", primeiro_venc=primeiro)
            if ativo is not None:
                con.execute("UPDATE contas_recorrentes SET ativo=? WHERE id=?", (ativo, rid))
                con.commit()
            return rid
        finally:
            con.close()

    def test_gera_mes_atual_e_seguinte(self):
        rid = self.criar("2026-01-05", 5)              # cria jan e fev de 2026
        con = self.banco()
        try:
            rec.gerar(con, date(2026, 10, 27))          # hoje: out/2026 e nov/2026
        finally:
            con.close()
        self.assertEqual(self.datas(rid), ["2026-01-05", "2026-02-05", "2026-10-05", "2026-11-05"])

    def test_dia_31_em_fevereiro_vira_ultimo_dia(self):
        r1 = self.criar("2027-02-01", 31, "FEV COMUM")
        r2 = self.criar("2028-02-01", 31, "FEV BISSEXTO")
        self.assertEqual(self.datas(r1), ["2027-02-28", "2027-03-31"])
        self.assertEqual(self.datas(r2), ["2028-02-29", "2028-03-31"])

    def test_idempotente_e_quitada_nao_duplica(self):
        rid = self.criar("2026-10-01", 15, "IDEMPOTENTE")
        con = self.banco()
        try:
            self.assertEqual(rec.gerar(con, date(2026, 10, 27)), 0)   # já existem out e nov
            con.execute("UPDATE contas SET status='PAGO', banco_pagamento='CAIXA' WHERE recorrente_id=? AND vencimento='2026-10-15'", (rid,))
            con.commit()
            self.assertEqual(rec.gerar(con, date(2026, 10, 27)), 0)
            self.assertEqual(rec.gerar(con, date(2026, 10, 28)), 0)
        finally:
            con.close()
        self.assertEqual(self.datas(rid), ["2026-10-15", "2026-11-15"])

    def test_servidor_e_bandeja_geram_so_uma_conta_do_mes(self):
        # o laço de fundo (servidor e bandeja) e a tela abrem conexões separadas: cada uma roda a geração
        rid = self.criar("2026-10-01", 20, "DUPLA GERACAO")
        con_servidor, con_bandeja = self.banco(), self.banco()
        try:
            con_servidor.execute("DELETE FROM contas WHERE recorrente_id=? AND recorrente_mes='2026-10'", (rid,))
            con_servidor.commit()
            rec.gerar(con_servidor, date(2026, 10, 27))
            rec.gerar(con_bandeja, date(2026, 10, 27))
            linhas = con_bandeja.execute("SELECT lote_id, status FROM contas WHERE recorrente_id=? AND recorrente_mes='2026-10'",
                                         (rid,)).fetchall()
        finally:
            con_servidor.close()
            con_bandeja.close()
        self.assertEqual(len(linhas), 1)
        self.assertIsNone(linhas[0]["lote_id"])
        self.assertEqual(linhas[0]["status"], "ABERTO")

    def test_editar_vencimento_nao_duplica(self):
        rid = self.criar("2026-10-01", 15, "EDITADA")
        con = self.banco()
        try:
            con.execute("UPDATE contas SET vencimento='2026-10-22' WHERE recorrente_id=? AND recorrente_mes='2026-10'", (rid,))
            con.commit()
            rec.gerar(con, date(2026, 10, 27))
            rec.gerar(con, date(2026, 10, 28))
            n_out = con.execute("SELECT COUNT(*) FROM contas WHERE recorrente_id=? AND recorrente_mes='2026-10'", (rid,)).fetchone()[0]
        finally:
            con.close()
        self.assertEqual(n_out, 1)
        self.assertEqual(self.datas(rid), ["2026-10-22", "2026-11-15"])

    def test_pausada_nao_gera(self):
        rid = self.criar("2026-12-01", 10, "PAUSADA")
        con = self.banco()
        try:
            con.execute("UPDATE contas_recorrentes SET ativo=0 WHERE id=?", (rid,))
            con.execute("DELETE FROM contas WHERE recorrente_id=?", (rid,))   # limpa o que a criação já lançou
            con.commit()
            rec.gerar(con, date(2026, 12, 3))   # outras recorrências do teste podem gerar; esta não
        finally:
            con.close()
        self.assertEqual(self.datas(rid), [])

    def test_validacao(self):
        con = self.banco()
        try:
            for dados in ({"descricao": "", "categoria": "X", "valor": 1, "dia": "5"},
                          {"descricao": "A", "categoria": "X", "valor": 0, "dia": "5"},
                          {"descricao": "A", "categoria": "X", "valor": 1, "dia": "32"},
                          {"descricao": "A", "categoria": "X", "valor": 1, "dia": ""}):
                with self.assertRaises(rec.ErroRecorrente):
                    rec.salvar(con, dados, "TESTE", primeiro_venc="2026-10-01")
        finally:
            con.close()

    def test_tela_cria_recorrencia_e_contas(self):
        c = self.cliente()
        with c.session_transaction() as s:
            token = s["csrf"]
        r = c.post("/contas/nova", data={"_csrf": token, "descricao": "internet tela", "categoria": "Água, energia e internet",
                                         "vencimento": "2026-11-05", "valor": "1.200,00", "recorrente": "1",
                                         "dia_vencimento": "5", "fornecedor": "", "fornecedor_id": "", "obs": "",
                                         "nota_fiscal": ""})
        self.assertEqual(r.status_code, 302)
        con = self.banco()
        try:
            r_id = con.execute("SELECT id FROM contas_recorrentes WHERE descricao='INTERNET TELA'").fetchone()["id"]
        finally:
            con.close()
        self.assertEqual(self.datas(r_id), ["2026-11-05", "2026-12-05"])

    def test_permissao_sem_modulo_contas(self):
        self.criar_usuario("REC_SEM_CONTAS", modulos=[])
        self.assertEqual(self.cliente("REC_SEM_CONTAS", "senha123").get("/contas/recorrentes").status_code, 302)


if __name__ == "__main__":
    unittest.main()
