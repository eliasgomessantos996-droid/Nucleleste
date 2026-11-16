"""Reserva de horários para o UNACON, excluir agenda restrito, desfazer nos registros, favoritos e barra lateral."""
import json
import unittest
from datetime import date, timedelta

from app import agenda as ag
from app import db as dbmod
from app import views_favoritos
from tests.test_chat_blindagens import Base


def dia(n):
    return (date.today() + timedelta(days=900 + n * 11)).isoformat()


class Util(Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        con = dbmod.conectar(cls.app.config["DATABASE"])
        try:
            for nome in ("UNACON", "UNIMED"):
                con.execute("INSERT OR IGNORE INTO convenios (nome, gera_caixa, ativo) VALUES (?,0,1)", (nome,))
            con.commit()
        finally:
            con.close()

    def criar(self, c, d, **kw):
        dados = {"data": d, "exame": "OSSEA", "inicio": "07:00", "intervalo": "10", "qtd": "6", "vagas": "1"}
        dados.update(kw)
        self.assertEqual(self.post(c, "/agenda/criar", dados).status_code, 200)
        return c.get(f"/agenda/dia/{d}").get_json()["agendas"][0]

    def campo(self, c, hid, campo, valor):
        return self.post(c, f"/agenda/horario/{hid}/campo", {"campo": campo, "valor": valor})

    def linhas(self, c, d):
        return c.get(f"/agenda/dia/{d}").get_json()["agendas"][0]["linhas"]

    def registro(self, acao):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            return con.execute("SELECT id FROM auditoria WHERE acao=? ORDER BY id DESC LIMIT 1", (acao,)).fetchone()["id"]
        finally:
            con.close()


RESERVA_UNACON = {"reserva_ativa": "1", "reserva_convenio": "UNACON", "reserva_inicio": "07:00", "reserva_qtd": "1", "reserva_passo": "1"}


class Unacon(Util):
    def test_reserva_na_criacao_some_dos_livres_e_so_serve_ao_convenio(self):
        c = self.cliente()
        d = dia(1)
        a = self.criar(c, d, **RESERVA_UNACON)
        h0, h1, h2 = a["linhas"][0]["id"], a["linhas"][1]["id"], a["linhas"][2]["id"]
        self.assertTrue(self.linhas(c, d)[0]["reservado"])
        self.assertEqual(self.linhas(c, d)[0]["convenio"], "UNACON")          # o horário já nasce com o convênio
        self.assertEqual(c.get(f"/agenda/dia/{d}").get_json()["agendas"][0]["reserva_convenio"], "UNACON")
        livres = c.get(f"/agenda/livres/{d}").get_json()["livres"]
        self.assertNotIn(h0, [x["id"] for x in livres])
        com = c.get(f"/agenda/livres/{d}?convenio=UNACON").get_json()["livres"]
        self.assertIn(h0, [x["id"] for x in com])
        self.assertNotIn(h0, [x["id"] for x in c.get(f"/agenda/livres/{d}?convenio=UNIMED").get_json()["livres"]])
        resumo = c.get(f"/agenda/dia/{d}").get_json()["agendas"][0]["resumo"]
        self.assertEqual((resumo["livres"], resumo["reservados"]), (5, 1))
        # horário reservado sem paciente não aceita outro convênio (a reserva só sai por "Liberar reserva")
        r = self.campo(c, h0, "convenio", "UNIMED")
        self.assertEqual(r.status_code, 400)
        self.assertIn("UNACON", r.get_json()["erro"])
        # paciente de outro convênio não pode ser remarcado para o horário reservado
        self.assertEqual(self.campo(c, h1, "paciente", "BELTRANO").status_code, 200)
        self.campo(c, h1, "convenio", "UNIMED")
        r = self.post(c, f"/agenda/horario/{h1}/remarcar", {"destino": h0})
        self.assertEqual(r.status_code, 400)
        self.assertIn("UNACON", r.get_json()["erro"])
        # marcar o convênio da reserva em outra linha também a reserva
        self.assertTrue(self.campo(c, h2, "convenio", "UNACON").get_json()["reservado"])
        # paciente já marcado que troca para outro convênio deixa de ocupar reserva
        self.assertEqual(self.campo(c, h0, "paciente", "FULANO").status_code, 200)
        self.assertFalse(self.campo(c, h0, "convenio", "UNIMED").get_json()["reservado"])

    def test_unacon_pode_remarcar_para_horario_reservado_e_leva_a_reserva(self):
        c = self.cliente()
        d = dia(2)
        a = self.criar(c, d, **dict(RESERVA_UNACON, reserva_inicio="07:30", reserva_qtd="3"))
        ids = [l["id"] for l in a["linhas"]]
        self.campo(c, ids[0], "paciente", "MARIA")
        self.campo(c, ids[0], "convenio", "UNACON")
        r = self.post(c, f"/agenda/horario/{ids[0]}/remarcar", {"destino": ids[3]})
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        linhas = {l["id"]: l for l in self.linhas(c, d)}
        self.assertEqual(linhas[ids[3]]["paciente"], "MARIA")
        self.assertTrue(linhas[ids[3]]["reservado"])

    def test_reservar_faixa_e_liberar(self):
        c = self.cliente()
        d = dia(3)
        a = self.criar(c, d, **RESERVA_UNACON)
        r = self.post(c, f"/agenda/{a['id']}/reservar", {"de": "07:10", "ate": "07:30", "valor": "1"}).get_json()
        self.assertEqual(r["qtd"], 3)
        self.assertEqual([l["reservado"] for l in self.linhas(c, d)], [True, True, True, True, False, False])
        self.assertEqual(self.linhas(c, d)[1]["convenio"], "UNACON")
        self.post(c, f"/agenda/{a['id']}/reservar", {"de": "07:00", "ate": "08:00", "valor": "0"})
        self.assertFalse(any(l["reservado"] for l in self.linhas(c, d)))
        self.assertEqual(self.linhas(c, d)[1]["convenio"], "")

    def test_copiar_agenda_leva_as_reservas(self):
        c = self.cliente()
        d, d2 = dia(4), dia(5)
        self.criar(c, d, **dict(RESERVA_UNACON, reserva_qtd="3"))
        self.post(c, "/agenda/copiar", {"origem": d, "destino": d2})
        self.assertEqual([l["reservado"] for l in self.linhas(c, d2)], [True, True, True, False, False, False])
        self.assertEqual(c.get(f"/agenda/dia/{d2}").get_json()["agendas"][0]["reserva_convenio"], "UNACON")

    def test_qualquer_convenio_quantos_horarios_e_intervalo(self):
        c = self.cliente()
        d = dia(10)
        a = self.criar(c, d, **dict(RESERVA_UNACON, reserva_convenio="UNIMED", reserva_inicio="07:10", reserva_qtd="2", reserva_passo="2"))
        # a partir de 07:10, de dois em dois horários, 2 horários: 07:10 e 07:30
        self.assertEqual([l["hora"] for l in self.linhas(c, d) if l["reservado"]], ["07:10", "07:30"])
        self.assertEqual({l["reservado_convenio"] for l in self.linhas(c, d) if l["reservado"]}, {"UNIMED"})
        ids = {l["hora"]: l["id"] for l in self.linhas(c, d)}
        self.assertIn(ids["07:10"], [x["id"] for x in c.get(f"/agenda/livres/{d}?convenio=UNIMED").get_json()["livres"]])
        self.assertNotIn(ids["07:10"], [x["id"] for x in c.get(f"/agenda/livres/{d}").get_json()["livres"]])

    def test_validacoes_da_reserva_e_agenda_sem_reserva(self):
        c = self.cliente()
        d = dia(11)
        for ruim in ({"reserva_convenio": "NAO EXISTE"}, {"reserva_qtd": "0"}, {"reserva_passo": "99"}):
            dados = {"data": d, "exame": "OSSEA", "inicio": "07:00", "intervalo": "10", "qtd": "6", "vagas": "1"}
            dados.update(RESERVA_UNACON)
            dados.update(ruim)
            self.assertEqual(self.post(c, "/agenda/criar", dados).status_code, 400, ruim)
        self.assertEqual(c.get(f"/agenda/dia/{d}").get_json()["agendas"], [])
        a = self.criar(c, d)       # sem a aba de reserva: nada reservado e o botão de reservar é recusado
        self.assertEqual(c.get(f"/agenda/dia/{d}").get_json()["agendas"][0]["reserva_convenio"], "")
        r = self.post(c, f"/agenda/{a['id']}/reservar", {"de": "07:00", "ate": "07:20", "valor": "1"})
        self.assertEqual(r.status_code, 400)


class ExcluirAgenda(Util):
    def test_so_administrador_e_gerencia_excluem(self):
        d = dia(6)
        admin = self.cliente()
        a = self.criar(admin, d)
        self.criar_usuario("RECEP", ["agenda"])
        recep = self.cliente("RECEP", "senha123")
        r = self.post(recep, f"/agenda/{a['id']}/excluir", {})
        self.assertEqual(r.status_code, 403)
        self.assertNotIn("data-pode-excluir", recep.get_data(as_text=True) if False else recep.get(f"/agenda?data={d}").get_data(as_text=True))
        self.criar_usuario("CHEFE", ["agenda", "gerencia"])
        chefe = self.cliente("CHEFE", "senha123")
        self.assertIn("data-pode-excluir", chefe.get(f"/agenda?data={d}").get_data(as_text=True))
        self.assertEqual(self.post(chefe, f"/agenda/{a['id']}/excluir", {}).status_code, 200)


class Desfazer(Util):
    def test_desfazer_status_e_exclusao_de_agenda(self):
        c = self.cliente()
        d = dia(7)
        a = self.criar(c, d)
        hid = a["linhas"][0]["id"]
        self.campo(c, hid, "paciente", "JOAO")
        self.post(c, f"/agenda/horario/{hid}/status", {"status": "VEIO"})
        rid = self.registro("Mudou o status na agenda")
        pagina = c.get("/registros").get_data(as_text=True)
        self.assertIn("Desfazer", pagina)
        r = self.post(c, f"/registros/{rid}/desfazer", {"voltar": "/registros"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.linhas(c, d)[0]["status"], "AGENDADO")
        # já desfeito: não repete
        self.post(c, f"/registros/{rid}/desfazer", {})
        self.assertIn("Desfeito por", c.get("/registros").get_data(as_text=True))
        # excluir a agenda inteira e recuperar
        self.post(c, f"/agenda/{a['id']}/excluir", {"confirmar": "1"})
        self.assertEqual(c.get(f"/agenda/dia/{d}").get_json()["agendas"], [])
        self.post(c, f"/registros/{self.registro('Excluiu agenda de exame')}/desfazer", {})
        volta = c.get(f"/agenda/dia/{d}").get_json()["agendas"][0]
        self.assertEqual(volta["linhas"][0]["paciente"], "JOAO")
        self.assertEqual(len(volta["linhas"]), 6)

    def test_nao_desfaz_se_os_dados_mudaram_depois(self):
        c = self.cliente()
        d = dia(8)
        a = self.criar(c, d)
        hid = a["linhas"][0]["id"]
        self.campo(c, hid, "paciente", "ANA")
        self.post(c, f"/agenda/horario/{hid}/status", {"status": "FALTOU"})
        rid = self.registro("Mudou o status na agenda")
        self.post(c, f"/agenda/horario/{hid}/status", {"status": "VEIO"})   # alguém mexeu depois
        self.post(c, f"/registros/{rid}/desfazer", {})
        self.assertEqual(self.linhas(c, d)[0]["status"], "VEIO")

    def test_desfazer_criar_agenda_vazia(self):
        c = self.cliente()
        d = dia(9)
        self.criar(c, d)
        self.post(c, f"/registros/{self.registro('Criou agenda de exame')}/desfazer", {})
        self.assertEqual(c.get(f"/agenda/dia/{d}").get_json()["agendas"], [])

    def test_so_administrador_ou_gerencia_desfazem(self):
        self.criar_usuario("CURIOSO", ["registros"])
        c = self.cliente("CURIOSO", "senha123")
        r = self.post(c, "/registros/1/desfazer", {})
        self.assertEqual(r.status_code, 302)


class Favoritos(Util):
    def test_normalizar_descarta_invalidos(self):
        validos = {"agenda.pagina", "cad.clientes"}
        bruto = json.dumps({"modo": "xx", "itens": [{"ep": "agenda.pagina", "tam": 2, "cor": "azul"}, {"ep": "agenda.pagina"},
                                                    {"ep": "admin.usuarios"}, {"ep": "cad.clientes", "tam": 9, "cor": "feio"}]})
        r = views_favoritos.normalizar(bruto, validos)
        self.assertEqual(r["modo"], "grade")
        self.assertEqual(r["itens"], [{"ep": "agenda.pagina", "tam": 2, "cor": "azul", "ico": ""}, {"ep": "cad.clientes", "tam": 1, "cor": "", "ico": ""}])

    def test_salvar_e_ler_por_perfil(self):
        self.criar_usuario("FAV1", ["agenda"])
        self.criar_usuario("FAV2", ["agenda"])
        a = self.cliente("FAV1", "senha123")
        dados = json.dumps({"modo": "lista", "itens": [{"ep": "agenda.pagina", "tam": 2, "cor": "roxo"}, {"ep": "admin.usuarios"}]})
        r = self.post(a, "/favoritos/salvar", {"dados": dados})
        self.assertEqual(r.get_json()["itens"], [{"ep": "agenda.pagina", "tam": 2, "cor": "roxo", "ico": ""}])   # admin.usuarios não é dele
        self.assertIn("Agenda de exames", a.get("/favoritos").get_data(as_text=True))
        b = self.cliente("FAV2", "senha123")
        self.assertIn('"itens": []', b.get("/favoritos").get_data(as_text=True))


class BarraLateral(Util):
    def test_botao_de_ocultar_na_pagina(self):
        c = self.cliente()
        self.assertIn('id="menu-alternar"', c.get("/favoritos").get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
