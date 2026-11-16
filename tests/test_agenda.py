"""Agenda de exames: criação, grade, status, remarcar, copiar, lista de espera, bloqueio, relatórios e permissões."""
import io
import unittest
from datetime import date, timedelta

from app import agenda as ag
from app import db as dbmod
from tests.test_chat_blindagens import Base


def dia(n):
    """Uma data futura distinta por teste (o banco é compartilhado dentro da classe)."""
    return (date.today() + timedelta(days=200 + n * 15)).isoformat()


class AgendaTestes(Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # convênio na grade é escolha entre os cadastrados: estes nomes existem no cadastro de convênios
        con = dbmod.conectar(cls.app.config["DATABASE"])
        try:
            for nome in ("UNIMED", "SUS"):
                con.execute("INSERT OR IGNORE INTO convenios (nome, gera_caixa, ativo) VALUES (?,0,1)", (nome,))
            con.commit()
        finally:
            con.close()

    def criar(self, c, d, exame="CINTILOGRAFIA", **kw):
        dados = {"data": d, "exame": exame, "inicio": "08:00", "intervalo": "30", "qtd": "4", "vagas": "1"}
        dados.update(kw)
        return self.post(c, "/agenda/criar", dados)

    def lancar(self, d, exame, convenio, nome):
        """Atendimento lançado (é dele que o relatório e o financeiro tiram quem veio); o exame é o do cadastro."""
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            cad = ag.exame_do_nome(exame, con.execute("SELECT id, nome FROM exames").fetchall())
            con.execute("INSERT INTO atendimentos (cliente_nome, data, exame, convenio, criado_em) VALUES (?,?,?,?,?)",
                        (nome, d, cad[1] if cad else exame, convenio, d + " 09:00:00"))
            con.commit()
        finally:
            con.close()

    def dia_json(self, c, d):
        return c.get(f"/agenda/dia/{d}").get_json()

    def agendas(self, c, d):
        return self.dia_json(c, d)["agendas"]

    def campo(self, c, hid, campo, valor, antes=None):
        dados = {"campo": campo, "valor": valor}
        if antes is not None:
            dados["antes"] = antes
        return self.post(c, f"/agenda/horario/{hid}/campo", dados)

    def status(self, c, hid, st):
        return self.post(c, f"/agenda/horario/{hid}/status", {"status": st})

    # ------------------------------------------------------------ criar
    def test_criar_gera_os_horarios(self):
        c = self.cliente()
        d = dia(1)
        r = self.criar(c, d)
        self.assertEqual(r.status_code, 200)
        a = self.agendas(c, d)[0]
        self.assertEqual([l["hora"] for l in a["linhas"]], ["08:00", "08:30", "09:00", "09:30"])
        self.assertEqual((a["inicio"], a["fim"], a["intervalo"]), ("08:00", "10:00", 30))
        self.assertEqual(a["resumo"]["livres"], 4)
        # informando o término em vez da quantidade
        d2 = dia(2)
        self.assertEqual(self.criar(c, d2, qtd="", fim="10:00").status_code, 200)
        self.assertEqual(len(self.agendas(c, d2)[0]["linhas"]), 4)
        # dois pacientes por horário
        d3 = dia(3)
        self.criar(c, d3, vagas="2")
        horas = [l["hora"] for l in self.agendas(c, d3)[0]["linhas"]]
        self.assertEqual(horas, ["08:00", "08:00", "08:30", "08:30", "09:00", "09:00", "09:30", "09:30"])

    def test_validacoes_da_criacao(self):
        c = self.cliente()
        d = dia(4)
        for extra in ({"exame": ""}, {"intervalo": "0"}, {"intervalo": "300"}, {"qtd": "0"}, {"qtd": "999"}, {"inicio": ""},
                      {"inicio": "25:00"}, {"data": ""}, {"vagas": "0"}, {"vagas": "11"}, {"semanas": "40"},
                      {"inicio": "23:00", "intervalo": "60", "qtd": "3"}, {"salvar_modelo": "on", "nome_modelo": ""}):
            r = self.criar(c, d, **extra)
            self.assertEqual(r.status_code, 400, extra)
            self.assertTrue(r.get_json()["erro"])
        self.assertEqual(self.agendas(c, d), [])

    def test_varios_exames_no_mesmo_dia_e_a_pagina(self):
        c = self.cliente()
        d = dia(5)
        self.criar(c, d, "CINTILOGRAFIA MIOCARDICA", inicio="07:00")
        self.criar(c, d, "PET-CT", inicio="13:00", intervalo="60", qtd="3")
        nomes = [a["exame"] for a in self.agendas(c, d)]
        self.assertEqual(nomes, ["CINTILOGRAFIA MIOCARDICA", "PET-CT"])
        pagina = self.texto(c.get(f"/agenda?data={d}"))
        self.assertIn("Agenda de exames", pagina)
        self.assertIn('id="ag-inicial"', pagina)
        self.assertIn("PET-CT", pagina)
        self.assertIn("agenda.js", pagina)

    def test_repetir_semanas_bloqueio_e_calendario(self):
        c = self.cliente()
        d = date.fromisoformat(dia(6))
        d7 = (d + timedelta(days=7)).isoformat()
        d14 = (d + timedelta(days=14)).isoformat()
        r = self.post(c, "/agenda/bloquear", {"data": d7, "motivo": "Feriado"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.dia_json(c, d7)["bloqueado"], "Feriado")
        self.assertEqual(self.criar(c, d7).status_code, 400)  # dia bloqueado
        r = self.criar(c, d.isoformat(), semanas="2")
        self.assertEqual(r.get_json()["criadas"], 2)
        self.assertEqual(r.get_json()["pulados"], [d7])
        self.assertEqual(len(self.agendas(c, d.isoformat())), 1)
        self.assertEqual(self.agendas(c, d7), [])
        self.assertEqual(len(self.agendas(c, d14)), 1)
        marcas = c.get(f"/agenda/mes?mes={d.isoformat()[:7]}").get_json()
        self.assertIn(d.isoformat(), marcas["dias"])
        self.assertEqual(self.post(c, "/agenda/bloquear", {"data": d.isoformat()}).status_code, 400)  # já tem agenda
        self.post(c, "/agenda/desbloquear", {"data": d7})
        self.assertIsNone(self.dia_json(c, d7)["bloqueado"])
        self.assertEqual(self.criar(c, d7).status_code, 200)

    def test_modelo_salvo_e_reutilizavel(self):
        c = self.cliente()
        self.criar(c, dia(7), "RENAL DMSA", salvar_modelo="on", nome_modelo="Manhã renal")
        modelos = self.dia_json(c, dia(7))["modelos"]
        self.assertTrue(any(m["nome"] == "Manhã renal" and m["exame"] == "RENAL DMSA" and m["qtd"] == 4 for m in modelos))

    # ------------------------------------------------------------ grade
    def test_grade_campos_status_e_conflito(self):
        c = self.cliente()
        d = dia(8)
        self.criar(c, d)
        linhas = self.agendas(c, d)[0]["linhas"]
        h0, h1 = linhas[0]["id"], linhas[1]["id"]
        for campo, valor in (("paciente", "Maria da Silva"), ("convenio", "UNIMED"), ("contato", "(33) 99999-0000"),
                             ("senha", "123456"), ("observacao", "jejum de 4h")):
            antes = linhas[0]["senha"] if campo == "senha" else ""            # a 6ª coluna já vem com o exame vinculado
            r = self.campo(c, h0, campo, valor, antes=antes)
            self.assertEqual(r.status_code, 200, (campo, r.get_json()))
        l = self.agendas(c, d)[0]["linhas"][0]
        self.assertEqual((l["paciente"], l["convenio"], l["senha"], l["observacao"]), ("Maria da Silva", "UNIMED", "123456", "jejum de 4h"))
        # conflito: a tela achava que o campo estava vazio, mas outra pessoa já preencheu
        r = self.campo(c, h0, "paciente", "Outra Pessoa", antes="")
        self.assertEqual(r.status_code, 409)
        self.assertTrue(r.get_json()["conflito"])
        self.assertEqual(r.get_json()["atual"], "Maria da Silva")
        # campo e horário inválidos
        self.assertEqual(self.campo(c, h0, "status", "x").status_code, 400)
        self.assertEqual(self.campo(c, h0, "hora", "99:99").status_code, 400)
        self.assertEqual(self.campo(c, h0, "hora", "0845").get_json()["valor"], "08:45")
        # status só em linha com paciente
        self.assertEqual(self.status(c, h1, "VEIO").status_code, 400)
        self.assertEqual(self.status(c, h0, "VEIO").status_code, 200)
        self.assertEqual(self.status(c, h0, "FALTOU").status_code, 200)
        self.assertEqual(self.status(c, h0, "INVENTADO").status_code, 400)
        a = self.agendas(c, d)[0]
        self.assertEqual((a["resumo"]["marcados"], a["resumo"]["FALTOU"], a["resumo"]["livres"]), (1, 1, 3))
        # nome repetido no mesmo dia e exame: avisa, mas grava
        r = self.campo(c, h1, "paciente", "maria  da silva")
        self.assertEqual(r.status_code, 200)
        self.assertIn("já está marcado", r.get_json()["aviso"])
        # apagar o paciente volta a linha para livre
        self.campo(c, h0, "paciente", "")
        l = [x for x in self.agendas(c, d)[0]["linhas"] if x["id"] == h0][0]
        self.assertEqual((l["paciente"], l["status"]), ("", "AGENDADO"))

    def test_adicionar_e_retirar_horarios(self):
        c = self.cliente()
        d = dia(9)
        self.criar(c, d)
        a = self.agendas(c, d)[0]
        self.assertEqual(self.post(c, f"/agenda/{a['id']}/horario", {"qtd": "2"}).status_code, 200)
        horas = [l["hora"] for l in self.agendas(c, d)[0]["linhas"]]
        self.assertEqual(horas, ["08:00", "08:30", "09:00", "09:30", "10:00", "10:30"])
        # mais uma vaga no mesmo horário
        ref = self.agendas(c, d)[0]["linhas"][1]["id"]
        self.post(c, f"/agenda/{a['id']}/horario", {"depois": str(ref)})
        self.assertEqual([l["hora"] for l in self.agendas(c, d)[0]["linhas"]].count("08:30"), 2)
        # retirar horário vazio: direto; com paciente: pede confirmação
        linhas = self.agendas(c, d)[0]["linhas"]
        vazio, ocupado = linhas[-1]["id"], linhas[0]["id"]
        self.assertEqual(self.post(c, f"/agenda/horario/{vazio}/excluir").status_code, 200)
        self.campo(c, ocupado, "paciente", "João")
        r = self.post(c, f"/agenda/horario/{ocupado}/excluir")
        self.assertEqual(r.status_code, 409)
        self.assertTrue(r.get_json()["confirmar"])
        self.assertEqual(self.post(c, f"/agenda/horario/{ocupado}/excluir", {"confirmar": "1"}).status_code, 200)
        # agenda com paciente também pede confirmação para excluir
        self.campo(c, self.agendas(c, d)[0]["linhas"][0]["id"], "paciente", "Ana")
        self.assertEqual(self.post(c, f"/agenda/{a['id']}/excluir").status_code, 409)
        self.assertEqual(self.post(c, f"/agenda/{a['id']}/excluir", {"confirmar": "1"}).status_code, 200)
        self.assertEqual(self.agendas(c, d), [])

    # ------------------------------------------------------------ remarcar, copiar, espera
    def test_remarcar_leva_o_paciente_para_outro_horario(self):
        c = self.cliente()
        d1, d2 = dia(10), dia(11)
        self.criar(c, d1)
        self.criar(c, d2)
        origem = self.agendas(c, d1)[0]["linhas"][0]["id"]
        self.campo(c, origem, "paciente", "Carlos")
        self.campo(c, origem, "convenio", "UNIMED")
        self.campo(c, origem, "observacao", "alérgico")
        destino = self.agendas(c, d2)[0]["linhas"][1]["id"]
        r = self.post(c, f"/agenda/horario/{origem}/remarcar", {"destino": str(destino)})
        self.assertEqual(r.status_code, 200, r.get_json())
        o = self.agendas(c, d1)[0]["linhas"][0]
        self.assertEqual(o["status"], "RETORNO")
        self.assertIn("08:30", o["remarcado_para"])
        n = self.agendas(c, d2)[0]["linhas"][1]
        self.assertEqual((n["paciente"], n["convenio"], n["status"]), ("Carlos", "UNIMED", "AGENDADO"))
        self.assertIn("Retorno marcado a partir de", n["observacao"])
        self.assertIn("alérgico", n["observacao"])
        # destino já ocupado e remarcar para a mesma linha não passam
        self.assertEqual(self.post(c, f"/agenda/horario/{origem}/remarcar", {"destino": str(destino)}).status_code, 400)
        self.assertEqual(self.post(c, f"/agenda/horario/{origem}/remarcar", {"destino": str(origem)}).status_code, 400)
        self.assertEqual(c.get(f"/agenda/livres/{d2}").get_json()["livres"].__len__(), 3)

    def test_copiar_linha_para_outro_dia_mantem_a_origem(self):
        c = self.cliente()
        d1, d2 = dia(30), dia(31)
        self.criar(c, d1)
        self.criar(c, d2)
        origem = self.agendas(c, d1)[0]["linhas"][0]["id"]
        self.campo(c, origem, "paciente", "Paula")
        self.campo(c, origem, "contato", "(33) 99999-0000")
        destino = self.agendas(c, d2)[0]["linhas"][2]["id"]
        r = self.post(c, f"/agenda/horario/{origem}/copiar_linha", {"destino": str(destino)})
        self.assertEqual(r.status_code, 200, r.get_json())
        o = self.agendas(c, d1)[0]["linhas"][0]
        self.assertEqual((o["paciente"], o["status"]), ("Paula", "AGENDADO"))  # a origem continua como estava
        n = self.agendas(c, d2)[0]["linhas"][2]
        self.assertEqual((n["paciente"], n["contato"], n["status"]), ("Paula", "(33)99999-0000", "AGENDADO"))
        self.assertIn("Copiado de", n["observacao"])
        # horário já ocupado, mesma linha e linha sem paciente na origem não passam
        self.assertEqual(self.post(c, f"/agenda/horario/{origem}/copiar_linha", {"destino": str(destino)}).status_code, 400)
        self.assertEqual(self.post(c, f"/agenda/horario/{origem}/copiar_linha", {"destino": str(origem)}).status_code, 400)
        vazio = self.agendas(c, d1)[0]["linhas"][1]["id"]
        self.assertEqual(self.post(c, f"/agenda/horario/{vazio}/copiar_linha", {"destino": str(destino)}).status_code, 400)

    def test_idade_so_digitos_e_acompanha_a_copia(self):
        c = self.cliente()
        d1, d2 = dia(40), dia(41)
        self.criar(c, d1)
        self.criar(c, d2)
        origem = self.agendas(c, d1)[0]["linhas"][0]["id"]
        self.campo(c, origem, "paciente", "Idade Teste")
        r = self.campo(c, origem, "idade", "45a")
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual(self.agendas(c, d1)[0]["linhas"][0]["idade"], "45")
        destino = self.agendas(c, d2)[0]["linhas"][1]["id"]
        r = self.post(c, f"/agenda/horario/{origem}/copiar_linha", {"destino": str(destino)})
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual(self.agendas(c, d2)[0]["linhas"][1]["idade"], "45")
        # esvaziar o paciente zera a idade
        self.campo(c, origem, "paciente", "")
        self.assertEqual(self.agendas(c, d1)[0]["linhas"][0]["idade"], "")

    def test_mibi_senha_e_protocolo(self):
        c = self.cliente()
        d = dia(32)
        self.criar(c, d, "CINTILOGRAFIA MIOCARDICA ESTRESSE")
        self.criar(c, dia(33), "PET-CT")
        a = self.agendas(c, d)[0]
        self.assertTrue(a["mibi"])
        self.assertFalse(self.agendas(c, dia(33))[0]["mibi"])
        hid = a["linhas"][0]["id"]
        self.campo(c, hid, "paciente", "Rita")
        # no MIBI só aceita as três opções (sem diferenciar maiúsculas)
        self.assertEqual(self.campo(c, hid, "senha", "Qualquer").status_code, 400)
        self.assertEqual(self.campo(c, hid, "senha", "protocolo").get_json()["valor"], "Protocolo")
        self.assertEqual(self.agendas(c, d)[0]["linhas"][0]["senha"], "Protocolo")
        # fora do MIBI a senha continua livre
        outro = self.agendas(c, dia(33))[0]["linhas"][0]["id"]
        self.assertEqual(self.campo(c, outro, "senha", "Texto livre").get_json()["valor"], "Texto livre")
        # protocolo com o paciente ainda agendado pinta a linha de verde (classe no front); presença (VEIO) não
        self.assertEqual(self.status(c, hid, "VEIO").status_code, 200)
        self.assertEqual(self.agendas(c, d)[0]["linhas"][0]["status"], "VEIO")

    def test_copiar_para_outro_dia(self):
        c = self.cliente()
        d1, d2, d3 = dia(12), dia(13), dia(14)
        self.criar(c, d1)
        self.criar(c, d1, "PET-CT", inicio="13:00", qtd="2")
        a = self.agendas(c, d1)[0]
        l0 = a["linhas"][0]["id"]
        self.campo(c, l0, "paciente", "Paula")
        self.campo(c, l0, "contato", "33988887777")
        self.status(c, l0, "VEIO")
        l1 = a["linhas"][1]["id"]
        self.campo(c, l1, "paciente", "Remarcada")
        self.status(c, l1, "RETORNO")
        # só a estrutura
        r = self.post(c, "/agenda/copiar", {"origem": d1, "destino": d2})
        self.assertEqual((r.status_code, r.get_json()["criadas"]), (200, 2))
        copia = self.agendas(c, d2)
        self.assertEqual([x["exame"] for x in copia], ["CINTILOGRAFIA", "PET-CT"])
        self.assertTrue(all(not l["paciente"] for x in copia for l in x["linhas"]))
        # repetir a cópia não duplica
        r = self.post(c, "/agenda/copiar", {"origem": d1, "destino": d2})
        self.assertEqual(r.get_json()["criadas"], 0)
        self.assertEqual(len(r.get_json()["puladas"]), 2)
        # com pacientes (voltam como Agendado) e só uma agenda
        r = self.post(c, "/agenda/copiar", {"origem": d1, "destino": d3, "com_pacientes": "1", "agenda_id": str(a["id"])})
        self.assertEqual((r.get_json()["criadas"], r.get_json()["pacientes"]), (1, 1))
        l = self.agendas(c, d3)[0]["linhas"][0]
        self.assertEqual((l["paciente"], l["contato"], l["status"]), ("Paula", "(33)98888-7777", "AGENDADO"))
        self.assertEqual(self.agendas(c, d3)[0]["linhas"][1]["paciente"], "")  # a remarcada não é copiada
        # destino igual, vazio ou bloqueado
        self.assertEqual(self.post(c, "/agenda/copiar", {"origem": d1, "destino": d1}).status_code, 400)
        self.assertEqual(self.post(c, "/agenda/copiar", {"origem": d1}).status_code, 400)
        d4 = dia(15)
        self.post(c, "/agenda/bloquear", {"data": d4, "motivo": "x"})
        self.assertEqual(self.post(c, "/agenda/copiar", {"origem": d1, "destino": d4}).status_code, 400)

    def test_lista_de_espera_e_encaixe(self):
        c = self.cliente()
        d = dia(16)
        self.criar(c, d)
        self.assertEqual(self.post(c, "/agenda/espera", {"nome": ""}).status_code, 400)
        self.assertEqual(self.post(c, "/agenda/espera", {"nome": "Rita Souza", "exame": "CINTILOGRAFIA", "convenio": "SUS",
                                                           "contato": "33911112222", "observacao": "prefere manhã"}).status_code, 200)
        espera = self.dia_json(c, d)["espera"]
        e = [x for x in espera if x["nome"] == "Rita Souza"][0]
        livre = self.agendas(c, d)[0]["linhas"][2]["id"]
        r = self.post(c, f"/agenda/espera/{e['id']}/encaixar", {"destino": str(livre)})
        self.assertEqual(r.status_code, 200, r.get_json())
        l = self.agendas(c, d)[0]["linhas"][2]
        self.assertEqual((l["paciente"], l["convenio"], l["contato"]), ("Rita Souza", "SUS", "33911112222"))
        self.assertFalse(any(x["nome"] == "Rita Souza" for x in self.dia_json(c, d)["espera"]))
        self.assertEqual(self.post(c, f"/agenda/espera/{e['id']}/encaixar", {"destino": str(livre)}).status_code, 400)
        self.post(c, "/agenda/espera", {"nome": "Tiago"})
        t = [x for x in self.dia_json(c, d)["espera"] if x["nome"] == "Tiago"][0]
        self.assertEqual(self.post(c, f"/agenda/espera/{t['id']}/encaixar", {"destino": str(livre)}).status_code, 400)  # já ocupado
        self.assertEqual(self.post(c, f"/agenda/espera/{t['id']}/excluir").status_code, 200)
        self.assertFalse(any(x["nome"] == "Tiago" for x in self.dia_json(c, d)["espera"]))

    # ------------------------------------------------------------ impressão e relatórios
    def test_relatorio_numeros_pdf_e_excel(self):
        c = self.cliente()
        d = dia(17)
        self.criar(c, d, "CINTILOGRAFIA MIOCARDICA", qtd="5")
        ids = [l["id"] for l in self.agendas(c, d)[0]["linhas"]]
        casos = [("A", "UNIMED", "VEIO"), ("B", "UNIMED", "FALTOU"), ("C", "SUS", "RETORNO"), ("D", "SUS", "AGENDADO"), ("E", "", "VEIO")]
        for hid, (nome, conv, st) in zip(ids, casos):
            self.campo(c, hid, "paciente", nome)
            self.campo(c, hid, "convenio", conv)
            self.status(c, hid, st)
            if st == "VEIO":
                self.lancar(d, "MIBI", conv, nome)
        con = dbmod.conectar(self.app.config["DATABASE"])
        rel = ag.relatorio(con, date.fromisoformat(d), date.fromisoformat(d), "mibi")
        con.close()
        g = rel["geral"]
        self.assertEqual((g["marcados"], g["VEIO"], g["FALTOU"], g["RETORNO"], g["AGENDADO"], g["vagas"], g["livres"]), (5, 3, 1, 1, 1, 5, 0))
        self.assertEqual(g["taxa_falta"], 25.0)
        por_conv = {x["nome"]: x for x in rel["por_convenio"]}
        self.assertEqual(por_conv["UNIMED"]["marcados"], 2)
        self.assertEqual(por_conv["UNIMED"]["taxa_falta"], 50.0)
        self.assertIn("(sem convênio)", por_conv)
        # tela, PDF e Excel
        pagina = self.texto(c.get(f"/agenda/relatorio?de={d}&ate={d}&exame=MIBI"))
        self.assertIn("Relatórios da agenda", pagina)
        self.assertIn("25,0%", pagina)
        pdf = c.get(f"/agenda/relatorio.pdf?de={d}&ate={d}")
        self.assertTrue(pdf.data.startswith(b"%PDF"))
        xlsx = c.get(f"/agenda/relatorio.xlsx?de={d}&ate={d}")
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(xlsx.data))
        self.assertEqual(wb.sheetnames, ["Resumo", "Por exame", "Por convênio", "Por dia"])
        self.assertEqual(wb["Resumo"].cell(row=5, column=2).value, 5)

    def test_imprimir_o_dia(self):
        c = self.cliente()
        d = dia(18)
        self.criar(c, d, "IMPRESSAO-A")
        self.criar(c, d, "IMPRESSAO-B", inicio="14:00")
        self.campo(c, self.agendas(c, d)[0]["linhas"][0]["id"], "paciente", "Zeca <b>")
        r = c.get(f"/agenda/imprimir/{d}.pdf")
        self.assertEqual(r.mimetype, "application/pdf")
        self.assertTrue(r.data.startswith(b"%PDF"))
        self.assertNotIn("attachment", r.headers.get("Content-Disposition", ""))
        so_um = c.get(f"/agenda/imprimir/{d}.pdf?agenda={self.agendas(c, d)[1]['id']}&separar=1")
        self.assertTrue(so_um.data.startswith(b"%PDF"))
        vazio = c.get(f"/agenda/imprimir/{dia(19)}.pdf")
        self.assertTrue(vazio.data.startswith(b"%PDF"))
        self.assertEqual(c.get("/agenda/imprimir/xx.pdf").status_code, 404)

    # ------------------------------------------------------------ permissões
    def test_permissoes_por_modulo(self):
        self.criar_usuario("AG_NADA", [])
        self.criar_usuario("AG_USA", ["agenda"])
        self.criar_usuario("AG_REL", ["agenda_relatorios"])
        n = self.cliente("AG_NADA", "senha123")
        self.assertEqual(n.get("/agenda").status_code, 302)
        self.assertEqual(n.get(f"/agenda/dia/{dia(20)}").status_code, 302)
        self.assertEqual(self.post(n, "/agenda/criar", {"data": dia(20)}).status_code, 302)
        u = self.cliente("AG_USA", "senha123")
        self.assertEqual(u.get("/agenda").status_code, 200)
        self.assertEqual(u.get("/agenda/relatorio").status_code, 302)
        self.assertIn("Agenda de exames", self.texto(u.get("/", headers={"Referer": "http://localhost/"})))
        self.assertNotIn("Relatórios da agenda", self.texto(u.get("/", headers={"Referer": "http://localhost/"})))
        r = self.cliente("AG_REL", "senha123")
        self.assertEqual(r.get("/agenda/relatorio").status_code, 200)
        self.assertEqual(r.get("/agenda").status_code, 302)
        self.assertEqual(self.criar(u, dia(20)).status_code, 200)

    def test_exige_login(self):
        anonimo = self.app.test_client()
        self.assertEqual(anonimo.get("/agenda").status_code, 302)
        self.assertEqual(anonimo.get(f"/agenda/dia/{dia(21)}").status_code, 302)

    def test_mibi_repouso_e_estresse_contam_um_exame_no_periodo(self):
        c = self.cliente()
        d1, d2 = dia(60), dia(61)
        for d in (d1, d2):
            self.criar(c, d, "MIBI DUPLO", qtd="3")
        casos = {d1: [("Ana", "Repouso", "VEIO"), ("Bia", "Protocolo", "VEIO"), ("Cris", "Repouso", "VEIO")],
                 d2: [("Ana", "Estresse", "VEIO"), ("Bia", "Estresse", "VEIO"), ("Dora", "Estresse", "VEIO")]}
        for d, itens in casos.items():
            for l, (nome, senha, st) in zip(self.agendas(c, d)[0]["linhas"], itens):
                self.campo(c, l["id"], "paciente", nome)
                self.campo(c, l["id"], "senha", senha)
                self.status(c, l["id"], st)
                if st == "VEIO" and (nome, senha) != ("Ana", "Estresse"):   # Ana fez o exame de duas etapas: um atendimento só
                    self.lancar(d, "MIBI", "", nome)
        con = dbmod.conectar(self.app.config["DATABASE"])
        rel = ag.relatorio(con, date.fromisoformat(d1), date.fromisoformat(d2), "MIBI")
        con.close()
        # 6 linhas: Ana (repouso+estresse) = 1, Bia protocolo + Bia estresse isolado = 2, Cris = 1, Dora = 1 -> 5 exames
        self.assertEqual((rel["geral"]["marcados"], rel["geral"]["VEIO"]), (5, 5))
        # cada dia continua mostrando a agenda do dia, linha a linha
        self.assertEqual([x["marcados"] for x in rel["por_dia"]], [3, 3])
        # pendentes: quem tem só uma etapa marcada (Cris fez o repouso e Dora só o estresse; Bia estresse não tem repouso)
        self.assertEqual(rel["mibi"]["concluidos"], 1)
        self.assertEqual(sorted(p["paciente"] for p in rel["mibi"]["pendentes"]), ["Bia", "Cris", "Dora"])
        # remarcar o repouso da Cris: a observação diz que o estresse ainda não foi agendado, e continua editável
        l = self.agendas(c, d1)[0]["linhas"]
        self.criar(c, dia(62), "MIBI DUPLO", qtd="2")
        livre = self.agendas(c, dia(62))[0]["linhas"][0]["id"]
        self.assertEqual(self.post(c, f"/agenda/horario/{l[2]['id']}/remarcar", {"destino": str(livre)}).status_code, 200)
        obs = [x for x in self.agendas(c, dia(62))[0]["linhas"] if x["id"] == livre][0]["observacao"]
        self.assertIn("Estresse ainda não agendado", obs)
        self.assertEqual(self.campo(c, livre, "observacao", obs + " ok").status_code, 200)


if __name__ == "__main__":
    unittest.main()
