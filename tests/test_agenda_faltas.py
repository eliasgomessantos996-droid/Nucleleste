"""Faltas e reagendamento: lista de quem faltou, contato no padrão (XX)9XXXX-XXXX e mudança para resgatado/reagendado."""
import unittest
from datetime import date

from app import agenda as ag
from app import db as dbmod
from tests.test_chat_blindagens import Base
from tests.test_agenda import dia


class ContatoPadrao(unittest.TestCase):
    def test_formatacao(self):
        self.assertEqual(ag.contato_padrao("33999991234"), "(33)99999-1234")
        self.assertEqual(ag.contato_padrao("(33) 9 9999-1234"), "(33)99999-1234")
        self.assertEqual(ag.contato_padrao("5533999991234"), "(33)99999-1234")  # com o código do Brasil
        self.assertEqual(ag.contato_padrao("3332224444"), "(33)3222-4444")       # fixo
        self.assertEqual(ag.contato_padrao("João da Silva"), "João da Silva")    # sem número, mantém o texto
        self.assertEqual(ag.contato_padrao(""), "")
        # dois contatos no mesmo campo, separados por barra
        self.assertEqual(ag.contato_padrao("33999991234 / 3332224444"), "(33)99999-1234 / (33)3222-4444")
        self.assertEqual(ag.contato_padrao("33999991234/João"), "(33)99999-1234 / João")
        self.assertEqual(ag.primeiro_telefone("João / (33)99999-1234 / 3332224444"), "33999991234")


class FaltasTestes(Base):
    def setUp(self):
        self.c = self.cliente()
        self.d = dia(50)
        self.post(self.c, "/agenda/criar", {"data": self.d, "exame": "CINTILOGRAFIA", "inicio": "08:00",
                                             "intervalo": "30", "qtd": "3", "vagas": "1"})
        self.linhas = self.c.get(f"/agenda/dia/{self.d}").get_json()["agendas"][0]["linhas"]
        self.ids = [l["id"] for l in self.linhas]

    def campo(self, hid, campo, valor):
        return self.post(self.c, f"/agenda/horario/{hid}/campo", {"campo": campo, "valor": valor})

    def faltas(self):
        db = dbmod.conectar(self.app.config["DATABASE"])
        try:
            return ag.faltas(db, date.fromisoformat(self.d), date.fromisoformat(self.d))
        finally:
            db.close()

    def test_lista_de_faltas_com_contato_e_mudanca_de_status(self):
        self.campo(self.ids[0], "paciente", "Ana Lima")
        self.assertEqual(self.campo(self.ids[0], "contato", "33 99999-1111").get_json()["valor"], "(33)99999-1111")
        self.campo(self.ids[1], "paciente", "Bento Reis")  # sem telefone
        self.campo(self.ids[2], "paciente", "Carla Dias")
        self.post(self.c, f"/agenda/horario/{self.ids[0]}/status", {"status": "FALTOU"})
        self.post(self.c, f"/agenda/horario/{self.ids[1]}/status", {"status": "FALTOU"})
        self.post(self.c, f"/agenda/horario/{self.ids[2]}/status", {"status": "VEIO"})
        rel = self.faltas()
        self.assertEqual(rel["total"], 2)
        self.assertEqual(len(rel["grupos"]), 1)
        por_nome = {i["paciente"]: i for i in rel["grupos"][0]["itens"]}
        self.assertEqual(por_nome["Ana Lima"]["wa"], "5533999991111")  # número pronto para o WhatsApp
        self.assertEqual(por_nome["Bento Reis"]["wa"], "")

        # mudar de falta para resgatado/reagendado: sai da lista de faltas e vira status próprio
        r = self.post(self.c, f"/agenda/horario/{self.ids[0]}/status", {"status": "RESGATADO"})
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual(self.faltas()["total"], 1)
        resumo = self.c.get(f"/agenda/dia/{self.d}").get_json()["agendas"][0]["resumo"]
        self.assertEqual(resumo["RESGATADO"], 1)
        self.assertEqual(resumo["FALTOU"], 1)

    def test_reagendado_copia_o_paciente_e_desistiu_registra_quem(self):
        self.campo(self.ids[0], "paciente", "Dora Melo")
        self.campo(self.ids[0], "convenio", "")
        self.campo(self.ids[0], "contato", "33988887777")
        self.campo(self.ids[0], "observacao", "alérgica a contraste")
        self.post(self.c, f"/agenda/horario/{self.ids[0]}/status", {"status": "FALTOU"})
        d2 = dia(51)
        self.post(self.c, "/agenda/criar", {"data": d2, "exame": "CINTILOGRAFIA", "inicio": "09:00", "intervalo": "30",
                                             "qtd": "2", "vagas": "1"})
        destino = self.c.get(f"/agenda/dia/{d2}").get_json()["agendas"][0]["linhas"][1]["id"]
        r = self.post(self.c, f"/agenda/horario/{self.ids[0]}/reagendar", {"destino": str(destino)})
        self.assertEqual(r.status_code, 200, r.get_json())
        novo = self.c.get(f"/agenda/dia/{d2}").get_json()["agendas"][0]["linhas"][1]
        self.assertEqual((novo["paciente"], novo["contato"], novo["status"]), ("Dora Melo", "(33)98888-7777", "AGENDADO"))
        self.assertIn("alérgica", novo["observacao"])  # as informações vão junto
        origem = self.c.get(f"/agenda/dia/{self.d}").get_json()["agendas"][0]["linhas"][0]
        self.assertEqual(origem["status"], "RESGATADO")
        self.assertEqual(origem["resgatado_por"], "ADMIN")  # registra quem resgatou

        # desistência: também registra quem resgatou
        self.campo(self.ids[1], "paciente", "Edu Nunes")
        self.post(self.c, f"/agenda/horario/{self.ids[1]}/status", {"status": "FALTOU"})
        self.post(self.c, f"/agenda/horario/{self.ids[1]}/status", {"status": "DESISTIU"})
        self.assertEqual(self.c.get(f"/agenda/dia/{self.d}").get_json()["agendas"][0]["linhas"][1]["resgatado_por"], "ADMIN")

        # relatório de resgate: quantos cada usuário resgatou
        db = dbmod.conectar(self.app.config["DATABASE"])
        try:
            hoje = date.today()  # o período do relatório é pela data em que foi resgatado (hoje)
            rel = ag.resgates(db, hoje, hoje)
            self.assertEqual((rel["total"], rel["reagendados"], rel["desistiram"]), (2, 1, 1))
            self.assertEqual(rel["usuarios"][0]["usuario"], "ADMIN")
            self.assertEqual(rel["usuarios"][0]["total"], 2)
        finally:
            db.close()
        self.assertEqual(self.c.get("/agenda/resgates").status_code, 200)

    def test_permissao_do_relatorio_de_resgate(self):
        self.criar_usuario("RES_NADA", ["agenda", "agenda_faltas"])
        self.criar_usuario("RES_OK", ["resgate_relatorio"])
        self.assertEqual(self.cliente("RES_NADA", "senha123").get("/agenda/resgates").status_code, 302)
        self.assertEqual(self.cliente("RES_OK", "senha123").get("/agenda/resgates").status_code, 200)

    def test_pagina_e_permissao(self):
        self.criar_usuario("FAL_NADA", ["agenda"])
        self.criar_usuario("FAL_OK", ["agenda", "agenda_faltas"])
        n = self.cliente("FAL_NADA", "senha123")
        self.assertEqual(n.get("/agenda/faltas").status_code, 302)
        ok = self.cliente("FAL_OK", "senha123")
        pagina = self.texto(ok.get(f"/agenda/faltas?de={self.d}&ate={self.d}"))
        self.assertEqual(ok.get(f"/agenda/faltas?de={self.d}&ate={self.d}").status_code, 200)
        self.assertIn("Faltas e reagendamento", pagina)


if __name__ == "__main__":
    unittest.main()
