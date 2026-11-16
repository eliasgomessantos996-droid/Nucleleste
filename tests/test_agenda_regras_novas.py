"""Agenda: copiar com a pergunta de apagar o dia, troca Repouso/Estresse no MIBI, bloqueio do remarcado e financeiro por etapa do MIBI."""
from datetime import date, timedelta

from app import agenda as ag
from app import db as dbmod
from tests.test_chat_blindagens import Base


def dia(n):
    return (date.today() + timedelta(days=700 + n * 4)).isoformat()


class RegrasNovas(Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        con = dbmod.conectar(cls.app.config["DATABASE"])
        try:
            con.execute("INSERT OR IGNORE INTO convenios (nome, gera_caixa, ativo) VALUES ('UNIMED',0,1)")
            con.commit()
        finally:
            con.close()

    def criar(self, c, d, exame, qtd="3"):
        self.post(c, "/agenda/criar", {"data": d, "exame": exame, "inicio": "08:00", "intervalo": "30", "qtd": qtd, "vagas": "1"})
        return c.get(f"/agenda/dia/{d}").get_json()["agendas"][0]["linhas"]

    def campo(self, c, hid, campo, valor):
        return self.post(c, f"/agenda/horario/{hid}/campo", {"campo": campo, "valor": valor})

    def linhas(self, c, d):
        return c.get(f"/agenda/dia/{d}").get_json()["agendas"]

    def test_copiar_sim_move_e_troca_repouso_estresse_no_mibi(self):
        c = self.cliente()
        d1, d2 = dia(1), dia(2)
        ls = self.criar(c, d1, "MIBI")
        self.campo(c, ls[0]["id"], "paciente", "Ana")
        self.campo(c, ls[0]["id"], "senha", "Repouso")
        self.campo(c, ls[1]["id"], "paciente", "Bia")
        self.campo(c, ls[1]["id"], "senha", "Estresse")
        self.campo(c, ls[2]["id"], "paciente", "Cris")
        self.campo(c, ls[2]["id"], "senha", "Protocolo")
        r = self.post(c, "/agenda/copiar", {"origem": d1, "destino": d2, "com_pacientes": "1", "apagar_origem": "1"})
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual(self.linhas(c, d1), [])                                  # o dia copiado foi apagado
        novo = self.linhas(c, d2)[0]["linhas"]
        self.assertEqual([(l["paciente"], l["senha"]) for l in novo], [("Ana", "Estresse"), ("Bia", "Repouso"), ("Cris", "Protocolo")])

    def test_copiar_nao_grava_nas_duas_datas_e_so_troca_no_mibi(self):
        c = self.cliente()
        d1, d2 = dia(3), dia(4)
        ls = self.criar(c, d1, "CINTILOGRAFIA OSSEA", "2")
        self.campo(c, ls[0]["id"], "paciente", "Davi")
        self.campo(c, ls[0]["id"], "senha", "Repouso")                            # fora do MIBI: não troca
        r = self.post(c, "/agenda/copiar", {"origem": d1, "destino": d2, "com_pacientes": "1", "apagar_origem": "0"})
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual(self.linhas(c, d1)[0]["linhas"][0]["paciente"], "Davi")
        copia = self.linhas(c, d2)[0]["linhas"][0]
        self.assertEqual((copia["paciente"], copia["senha"]), ("Davi", "Repouso"))

    def test_remarcado_para_outra_data_trava_o_status(self):
        c = self.cliente()
        d1, d2 = dia(5), dia(6)
        origem = self.criar(c, d1, "CINTILOGRAFIA")[0]["id"]
        destino = self.criar(c, d2, "CINTILOGRAFIA")[1]["id"]
        self.campo(c, origem, "paciente", "Edu")
        self.assertEqual(self.post(c, f"/agenda/horario/{origem}/remarcar", {"destino": str(destino)}).status_code, 200)
        self.criar_usuario("RECEP_AG", ["agenda"])   # usuário comum: não pode mudar a linha remarcada
        rec = self.cliente("RECEP_AG", "senha123")
        r = self.post(rec, f"/agenda/horario/{origem}/status", {"status": "VEIO"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("remarcado", r.get_json()["erro"].lower())
        self.assertEqual(self.linhas(c, d1)[0]["linhas"][0]["status"], "RETORNO")
        # a nova marcação continua livre para mudar de status
        self.assertEqual(self.post(c, f"/agenda/horario/{destino}/status", {"status": "VEIO"}).status_code, 200)

    def test_gerencia_altera_status_do_remarcado(self):
        c = self.cliente()
        d1, d2 = dia(15), dia(16)
        origem = self.criar(c, d1, "CINTILOGRAFIA")[0]["id"]
        destino = self.criar(c, d2, "CINTILOGRAFIA")[1]["id"]
        self.campo(c, origem, "paciente", "Lia")
        self.assertEqual(self.post(c, f"/agenda/horario/{origem}/remarcar", {"destino": str(destino)}).status_code, 200)
        self.criar_usuario("GER_AG", ["agenda", "gerencia"])
        ger = self.cliente("GER_AG", "senha123")
        self.assertEqual(self.post(ger, f"/agenda/horario/{origem}/status", {"status": "VEIO"}).status_code, 200)
        o = self.linhas(c, d1)[0]["linhas"][0]
        self.assertEqual((o["status"], o["remarcado_para"]), ("VEIO", ""))
        n = self.linhas(c, d2)[0]["linhas"][1]
        self.assertEqual((n["paciente"], n["status"]), ("Lia", "AGENDADO"))

    def _relatorio(self, de, ate):
        db = dbmod.conectar(self.app.config["DATABASE"])
        try:
            return ag.relatorio(db, date.fromisoformat(de), date.fromisoformat(ate))
        finally:
            db.close()

    def test_reagendar_grava_reagendado_por_no_historico(self):
        c = self.cliente()
        d1, d2 = dia(95), dia(96)
        origem = self.criar(c, d1, "CINTILOGRAFIA")[0]["id"]
        destino = self.criar(c, d2, "CINTILOGRAFIA")[1]["id"]
        self.campo(c, origem, "paciente", "Rita")
        self.assertEqual(self.post(c, f"/agenda/horario/{origem}/status", {"status": "FALTOU"}).status_code, 200)
        self.assertEqual(self.post(c, f"/agenda/horario/{origem}/reagendar", {"destino": str(destino)}).status_code, 200)
        db = dbmod.conectar(self.app.config["DATABASE"])
        try:
            hist = ag.historico(db, origem)
        finally:
            db.close()
        self.assertIn(("Reagendado por ADMIN", "ADMIN"), [(h["acao"], h["usuario"]) for h in hist])
        self.assertEqual(self.linhas(c, d1)[0]["linhas"][0]["status"], "RESGATADO")

    def test_remarcado_que_veio_na_nova_data_conta_uma_vez(self):
        c = self.cliente()
        d1, d2 = dia(17), dia(18)
        origem = self.criar(c, d1, "CINTILOGRAFIA")[0]["id"]
        destino = self.criar(c, d2, "CINTILOGRAFIA")[1]["id"]
        self.campo(c, origem, "paciente", "Nina")
        self.assertEqual(self.post(c, f"/agenda/horario/{origem}/remarcar", {"destino": str(destino)}).status_code, 200)
        g = self._relatorio(d1, d2)["geral"]
        self.assertEqual((g["VEIO"], g["RETORNO"], g["AGENDADO"]), (1, 1, 1))
        self.assertEqual(self.post(c, f"/agenda/horario/{destino}/status", {"status": "VEIO"}).status_code, 200)
        rel = self._relatorio(d1, d2)
        g = rel["geral"]
        self.assertEqual((g["marcados"], g["VEIO"], g["RETORNO"], g["AGENDADO"]), (2, 1, 1, 0))
        por_dia = {p["nome"]: p for p in rel["por_dia"]}
        self.assertEqual((por_dia[d1]["VEIO"], por_dia[d1]["RETORNO"]), (0, 1))
        self.assertEqual(por_dia[d2]["VEIO"], 1)
        so_d1 = self._relatorio(d1, d1)["geral"]
        self.assertEqual((so_d1["VEIO"], so_d1["RETORNO"]), (0, 1))

    def test_remarcado_em_cadeia_conta_uma_vez(self):
        c = self.cliente()
        d1, d2, d3 = dia(22), dia(23), dia(24)
        origem = self.criar(c, d1, "CINTILOGRAFIA")[0]["id"]
        meio = self.criar(c, d2, "CINTILOGRAFIA")[1]["id"]
        fim = self.criar(c, d3, "CINTILOGRAFIA")[1]["id"]
        self.campo(c, origem, "paciente", "Oto")
        self.assertEqual(self.post(c, f"/agenda/horario/{origem}/remarcar", {"destino": str(meio)}).status_code, 200)
        self.assertEqual(self.post(c, f"/agenda/horario/{meio}/remarcar", {"destino": str(fim)}).status_code, 200)
        self.assertEqual(self.post(c, f"/agenda/horario/{fim}/status", {"status": "VEIO"}).status_code, 200)
        g = self._relatorio(d1, d3)["geral"]
        self.assertEqual((g["VEIO"], g["RETORNO"]), (1, 2))

    def test_remarcado_que_faltou_na_nova_data_segue_como_veio(self):
        c = self.cliente()
        d1, d2 = dia(25), dia(26)
        origem = self.criar(c, d1, "CINTILOGRAFIA")[0]["id"]
        destino = self.criar(c, d2, "CINTILOGRAFIA")[1]["id"]
        self.campo(c, origem, "paciente", "Vito")
        self.assertEqual(self.post(c, f"/agenda/horario/{origem}/remarcar", {"destino": str(destino)}).status_code, 200)
        self.assertEqual(self.post(c, f"/agenda/horario/{destino}/status", {"status": "FALTOU"}).status_code, 200)
        g = self._relatorio(d1, d2)["geral"]
        self.assertEqual((g["VEIO"], g["RETORNO"], g["FALTOU"]), (1, 1, 1))

    def test_outra_etapa_do_mibi_conta_nos_dois_dias(self):
        c = self.cliente()
        d1, d2 = dia(27), dia(28)
        origem = self.criar(c, d1, "MIBI", "3")[0]["id"]
        destino = self.criar(c, d2, "MIBI", "3")[1]["id"]
        self.campo(c, origem, "paciente", "Yara")
        self.campo(c, origem, "senha", "Repouso")
        self.assertEqual(self.post(c, f"/agenda/horario/{origem}/remarcar", {"destino": str(destino)}).status_code, 200)
        self.campo(c, destino, "senha", "Estresse")
        self.assertEqual(self.post(c, f"/agenda/horario/{destino}/status", {"status": "VEIO"}).status_code, 200)
        rel = self._relatorio(d1, d2)
        g = rel["geral"]
        self.assertEqual((g["marcados"], g["VEIO"]), (1, 1))
        por_dia = {p["nome"]: p for p in rel["por_dia"]}
        self.assertEqual(por_dia[d1]["VEIO"], 1)
        self.assertEqual(por_dia[d2]["VEIO"], 1)

    def test_financeiro_por_etapa_do_mibi(self):
        c = self.cliente()
        d = dia(7)
        ls = self.criar(c, d, "MIBI", "3")
        for l, (nome, etapa) in zip(ls, (("F1", "Estresse"), ("F2", "Repouso"), ("F3", "Protocolo"))):
            self.campo(c, l["id"], "paciente", nome)
            self.campo(c, l["id"], "senha", etapa)
            self.post(c, f"/agenda/horario/{l['id']}/status", {"status": "VEIO"})
            con = dbmod.conectar(self.app.config["DATABASE"])
            con.execute("INSERT INTO atendimentos (cliente_nome, data, exame, convenio, criado_em) VALUES (?,?,'MIBI','',?)", (nome, d, d + " 09:00:00"))
            con.commit()
            con.close()
        db = dbmod.conectar(self.app.config["DATABASE"])
        de = date.fromisoformat(d)
        try:
            todos = ag.financeiro(db, de, de, 30, "MIBI")
            so_repouso = ag.financeiro(db, de, de, 30, "MIBI", ["Repouso"])
            dois = ag.financeiro(db, de, de, 30, "MIBI", ["Estresse", "Protocolo"])
        finally:
            db.close()
        self.assertEqual(todos["qtd"], 3)
        self.assertEqual([i["paciente"] for i in so_repouso["itens"]], ["F2"])
        self.assertEqual(sorted(i["paciente"] for i in dois["itens"]), ["F1", "F3"])
        pagina = self.texto(c.get(f"/agenda/financeiro?de={d}&ate={d}&pct=30&exame=MIBI&tipo=Repouso&tipo=Estresse"))
        self.assertIn("Etapas do MIBI", pagina)
        self.assertIn("F1", pagina)
        self.assertNotIn("F3", pagina)
        self.assertEqual(c.get(f"/agenda/financeiro.pdf?de={d}&ate={d}&pct=30&exame=MIBI&tipo=Repouso").status_code, 200)

    def test_recortar_leva_o_paciente_e_libera_o_horario(self):
        c = self.cliente()
        d1, d2 = dia(8), dia(9)
        origem = self.criar(c, d1, "CINTILOGRAFIA")[0]["id"]
        destino = self.criar(c, d2, "CINTILOGRAFIA")[1]["id"]
        self.campo(c, origem, "paciente", "Fabi")
        self.campo(c, origem, "contato", "33988887777")
        self.campo(c, origem, "observacao", "alérgica")
        self.assertEqual(self.post(c, f"/agenda/horario/{origem}/recortar", {"destino": str(destino)}).status_code, 200)
        o = self.linhas(c, d1)[0]["linhas"][0]
        self.assertEqual((o["paciente"], o["contato"], o["observacao"], o["status"]), ("", "", "", "AGENDADO"))
        n = self.linhas(c, d2)[0]["linhas"][1]
        self.assertEqual(n["paciente"], "Fabi")
        self.assertIn("Recortado de", n["observacao"])
        self.assertIn("alérgica", n["observacao"])
        # linha vazia e destino ocupado não passam
        self.assertEqual(self.post(c, f"/agenda/horario/{origem}/recortar", {"destino": str(destino)}).status_code, 400)
        self.assertEqual(self.post(c, f"/agenda/horario/{destino}/recortar", {"destino": str(destino)}).status_code, 400)

    def test_agenda_vinculada_a_exame_cadastrado_e_relatorios_pela_agenda(self):
        c = self.cliente()
        d = dia(10)
        con = dbmod.conectar(self.app.config["DATABASE"])
        osso = con.execute("SELECT id FROM exames WHERE nome LIKE '%SSEA'").fetchone()[0]
        con.close()
        # o vínculo é obrigatório: nome de agenda que não casa com nenhum exame e sem escolha é recusado
        r = self.post(c, "/agenda/criar", {"data": d, "exame": "AGENDA NOME LIVRE XYZ", "exame_id": "", "inicio": "08:00", "intervalo": "30", "qtd": "2", "vagas": "1"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("vinculada", r.get_json()["erro"])
        r = self.post(c, "/agenda/criar", {"data": d, "exame": "AGENDA NOME LIVRE XYZ", "exame_id": str(osso), "inicio": "08:00", "intervalo": "30", "qtd": "2", "vagas": "1"})
        self.assertEqual(r.status_code, 200, r.get_json())
        a = c.get(f"/agenda/dia/{d}").get_json()["agendas"][0]
        self.assertEqual(a["exame"], "AGENDA NOME LIVRE XYZ")
        self.assertIn("SSEA", a["exame_cadastrado"])
        l0, l1 = a["linhas"]
        self.campo(c, l0["id"], "paciente", "Gil")
        self.post(c, f"/agenda/horario/{l0['id']}/status", {"status": "VEIO"})
        self.campo(c, l1["id"], "paciente", "Hana")
        self.post(c, f"/agenda/horario/{l1['id']}/status", {"status": "FALTOU"})
        for rota in ("relatorio", "financeiro"):
            pagina = self.texto(c.get(f"/agenda/{rota}?de={d}&ate={d}&pct=30"))
            self.assertNotIn("AGENDA NOME LIVRE XYZ", pagina)                     # o filtro lista só os exames cadastrados
            self.assertRegex(pagina, r"<option[^>]*>MIBI</option>")
        pagina = self.texto(c.get(f"/agenda/relatorio?de={d}&ate={d}"))
        self.assertIn("Painel de todos os exames no período", pagina)
        db = dbmod.conectar(self.app.config["DATABASE"])
        try:
            rel = ag.relatorio(db, date.fromisoformat(d), date.fromisoformat(d), "")
            fin = ag.financeiro(db, date.fromisoformat(d), date.fromisoformat(d), 30, "")
            fin_osso = ag.financeiro(db, date.fromisoformat(d), date.fromisoformat(d), 30, [e for e in ag.exames_do_cadastro(db) if "SSEA" in e][0])
            fin_mibi = ag.financeiro(db, date.fromisoformat(d), date.fromisoformat(d), 30, "MIBI")
        finally:
            db.close()
        self.assertEqual((rel["geral"]["marcados"], rel["geral"]["VEIO"], rel["geral"]["FALTOU"]), (2, 1, 1))
        card = [e for e in rel["dashboard"]["por_exame"] if "SSEA" in e["nome"]][0]
        self.assertEqual((card["marcados"], card["VEIO"], card["FALTOU"], card["RETORNO"]), (2, 1, 1, 0))
        self.assertEqual([i["paciente"] for i in fin["itens"]], ["Gil"])               # só status Veio
        self.assertEqual([i["paciente"] for i in fin_osso["itens"]], ["Gil"])          # exame pelo vínculo, não pelo nome da agenda
        self.assertEqual(fin_mibi["itens"], [])

    def test_financeiro_mibi_nao_duplica_repouso_e_estresse(self):
        c = self.cliente()
        d1, d2 = dia(11), dia(12)
        for d, etapas in ((d1, [("Paula", "Repouso"), ("Quiteria", "Protocolo")]), (d2, [("Paula", "Estresse")])):
            ls = self.criar(c, d, "MIBI", str(len(etapas)))
            for l, (nome, etapa) in zip(ls, etapas):
                self.campo(c, l["id"], "paciente", nome)
                self.campo(c, l["id"], "senha", etapa)
                self.post(c, f"/agenda/horario/{l['id']}/status", {"status": "VEIO"})
        db = dbmod.conectar(self.app.config["DATABASE"])
        try:
            todos = ag.financeiro(db, date.fromisoformat(d1), date.fromisoformat(d2), 30, "MIBI")
            so_estresse = ag.financeiro(db, date.fromisoformat(d1), date.fromisoformat(d2), 30, "MIBI", ["Estresse"])
        finally:
            db.close()
        self.assertEqual(sorted(i["paciente"] for i in todos["itens"]), ["Paula", "Quiteria"])   # Paula (repouso + estresse) = 1 exame; protocolo = 1 MIBI
        self.assertEqual([i["paciente"] for i in so_estresse["itens"]], ["Paula"])               # com o filtro de etapa, cada etapa é vista separada

    def test_renomear_agenda_muda_so_o_nome(self):
        c = self.cliente()
        d = dia(13)
        a = self.criar(c, d, "MIBI", "2")
        aid = c.get(f"/agenda/dia/{d}").get_json()["agendas"][0]["id"]
        antes = c.get(f"/agenda/dia/{d}").get_json()["agendas"][0]
        r = self.post(c, f"/agenda/{aid}/nome", {"nome": "MIBI Manhã Especial"})
        self.assertEqual(r.status_code, 200, r.get_json())
        depois = c.get(f"/agenda/dia/{d}").get_json()["agendas"][0]
        self.assertEqual(depois["exame"], "MIBI Manhã Especial")
        self.assertEqual(depois["exame_cadastrado"], antes["exame_cadastrado"])       # o vínculo com o exame cadastrado não muda
        self.assertTrue(depois["mibi"])
        self.assertEqual(self.post(c, f"/agenda/{aid}/nome", {"nome": "  "}).status_code, 400)
        from app import mensagens_whats as mw
        self.assertIn("{agenda}", [v[0] for v in mw.VARIAVEIS])

    def test_chegou_compartilhado_conta_no_relatorio_e_fica_no_historico(self):
        c = self.cliente()
        d = dia(14)
        ls = self.criar(c, d, "MIBI", "3")
        self.campo(c, ls[0]["id"], "paciente", "Rita")
        self.campo(c, ls[1]["id"], "paciente", "Saulo")
        self.assertEqual(self.post(c, f"/agenda/horario/{ls[2]['id']}/chegou", {"valor": "1"}).status_code, 400)     # sem paciente
        self.assertEqual(self.post(c, f"/agenda/horario/{ls[0]['id']}/chegou", {"valor": "1"}).status_code, 200)
        self.post(c, f"/agenda/horario/{ls[0]['id']}/status", {"status": "VEIO"})
        # outro usuário vê a marcação na hora e a contagem do resumo
        self.criar_usuario("CHEGOU_B", ["agenda", "agenda_relatorios"])
        b = self.cliente("CHEGOU_B", "senha123")
        a = b.get(f"/agenda/dia/{d}").get_json()["agendas"][0]
        self.assertTrue(a["linhas"][0]["chegou"])
        self.assertFalse(a["linhas"][1]["chegou"])
        self.assertEqual(a["resumo"]["chegou"], 1)
        pagina = self.texto(b.get(f"/agenda/relatorio?de={d}&ate={d}"))
        self.assertIn("chegaram (caixa Chegou marcada)", pagina)
        db = dbmod.conectar(self.app.config["DATABASE"])
        try:
            rel = ag.relatorio(db, date.fromisoformat(d), date.fromisoformat(d), "MIBI")
        finally:
            db.close()
        self.assertEqual((rel["geral"]["marcados"], rel["geral"]["chegou"]), (2, 1))
        # histórico: chegada, status e edição de campo, com quem fez
        self.campo(b, ls[0]["id"], "observacao", "chegou cedo")
        itens = b.get(f"/agenda/horario/{ls[0]['id']}/historico").get_json()["itens"]
        acoes = [(i["acao"], i["usuario"]) for i in itens]
        self.assertIn(("Chegada", "ADMIN"), acoes)
        self.assertIn(("Status", "ADMIN"), acoes)
        self.assertIn(("Campo alterado", "CHEGOU_B"), acoes)
        # tirar o nome do paciente zera a chegada
        self.campo(c, ls[1]["id"], "paciente", "")
        self.post(c, f"/agenda/horario/{ls[0]['id']}/chegou", {"valor": "0"})
        self.assertEqual(b.get(f"/agenda/dia/{d}").get_json()["agendas"][0]["resumo"]["chegou"], 0)


class ResumoContas(Base):
    def test_segunda_feira_envia_contas_dos_proximos_sete_dias_uma_vez(self):
        from app import avisos
        self.criar_usuario("CONTAS_OK", ["contas"])
        self.criar_usuario("CONTAS_NAO", ["agenda"])
        con = dbmod.conectar(self.app.config["DATABASE"])
        segunda = date(2031, 3, 3)                                    # uma segunda-feira
        for desc, venc, st in (("Energia ELEKTRO", "2031-03-05", "ABERTO"), ("Internet", "2031-03-10", "ABERTO"),
                               ("Longe demais", "2031-03-20", "ABERTO"), ("Já paga", "2031-03-06", "PAGO")):
            con.execute("INSERT INTO contas (descricao, vencimento, valor, status) VALUES (?,?,?,?)", (desc, venc, 1500.5, st))
        con.commit()
        self.assertEqual(avisos.verificar(con, date(2031, 3, 4)), 0)   # terça: nada do resumo
        antes = con.execute("SELECT COUNT(*) FROM chat_mensagens WHERE corpo LIKE 'Resumo da semana%'").fetchone()[0]
        self.assertEqual(antes, 0)
        avisos.verificar(con, segunda)
        msgs = con.execute("SELECT para_id, corpo FROM chat_mensagens WHERE corpo LIKE 'Resumo da semana%'").fetchall()
        ids = {r["para_id"] for r in msgs}
        ok = con.execute("SELECT id FROM usuarios WHERE usuario='CONTAS_OK'").fetchone()[0]
        nao = con.execute("SELECT id FROM usuarios WHERE usuario='CONTAS_NAO'").fetchone()[0]
        self.assertIn(ok, ids)
        self.assertNotIn(nao, ids)
        corpo = [r["corpo"] for r in msgs if r["para_id"] == ok][0]
        self.assertIn("Energia ELEKTRO", corpo)
        self.assertIn("Internet", corpo)
        self.assertNotIn("Longe demais", corpo)
        self.assertNotIn("Já paga", corpo)
        self.assertIn("2 conta(s)", corpo)
        self.assertIn("R$ 3.001,00", corpo)
        total = len(msgs)
        avisos.verificar(con, segunda)                                  # na mesma segunda não repete
        self.assertEqual(con.execute("SELECT COUNT(*) FROM chat_mensagens WHERE corpo LIKE 'Resumo da semana%'").fetchone()[0], total)
        con.close()


class StatusRetorno(Base):
    def test_retorno_do_mibi_pergunta_o_horario_na_cor_do_veio_e_nao_conta_falta(self):
        c = self.cliente()
        d1, d2 = dia(20), dia(21)
        for d in (d1, d2):
            self.post(c, "/agenda/criar", {"data": d, "exame": "MIBI", "inicio": "08:00", "intervalo": "30", "qtd": "2", "vagas": "1"})
        origem = c.get(f"/agenda/dia/{d1}").get_json()["agendas"][0]["linhas"][0]["id"]
        destino = c.get(f"/agenda/dia/{d2}").get_json()["agendas"][0]["linhas"][1]["id"]
        self.post(c, f"/agenda/horario/{origem}/campo", {"campo": "paciente", "valor": "Tais"})
        self.post(c, f"/agenda/horario/{origem}/campo", {"campo": "senha", "valor": "Repouso"})
        self.assertEqual(self.post(c, f"/agenda/horario/{origem}/status", {"status": "REMARCOU"}).status_code, 400)   # o status antigo não existe mais
        self.assertEqual(self.post(c, f"/agenda/horario/{origem}/remarcar", {"destino": str(destino)}).status_code, 200)
        o = c.get(f"/agenda/dia/{d1}").get_json()["agendas"][0]
        self.assertEqual(o["linhas"][0]["status"], "RETORNO")
        self.assertIn("08:30", o["linhas"][0]["remarcado_para"])
        self.assertEqual(o["resumo"]["RETORNO"], 1)
        self.assertEqual(o["resumo"]["FALTOU"], 0)
        n = c.get(f"/agenda/dia/{d2}").get_json()["agendas"][0]["linhas"][1]
        self.assertEqual((n["paciente"], n["status"]), ("Tais", "AGENDADO"))
        self.assertIn("Retorno marcado a partir de", n["observacao"])
        self.criar_usuario("RECEP_AG2", ["agenda"])   # usuário comum: travado (administrador e gerência podem mudar)
        rec = self.cliente("RECEP_AG2", "senha123")
        self.assertEqual(self.post(rec, f"/agenda/horario/{origem}/status", {"status": "FALTOU"}).status_code, 400)
        # relatório: o paciente não aparece como falta, o retorno conta como veio, e o status virou Retorno na tela e nas cores
        db = dbmod.conectar(self.app.config["DATABASE"])
        try:
            rel = ag.relatorio(db, date.fromisoformat(d1), date.fromisoformat(d1), "MIBI")
        finally:
            db.close()
        self.assertEqual((rel["geral"]["FALTOU"], rel["geral"]["VEIO"], rel["geral"]["RETORNO"], rel["geral"]["taxa_falta"]), (0, 1, 1, 0.0))
        css = self.texto(c.get("/static/css/agenda.css"))
        self.assertIn("st-retorno", css)
        self.assertNotIn("st-remarcou", css)
        self.assertIn("Retorno", self.texto(c.get("/agenda")))


class ColunaPersonalizavel(Base):
    def _criar(self, c, d, exame, **extra):
        dados = {"data": d, "exame": exame, "inicio": "08:00", "intervalo": "30", "qtd": "3", "vagas": "1"}
        dados.update(extra)
        r = self.post(c, "/agenda/criar", dados)
        return r, (c.get(f"/agenda/dia/{d}").get_json()["agendas"] or [None])[0]

    def test_mibi_traz_etapa_em_todas_as_linhas_e_titulo_etapa(self):
        c = self.cliente()
        d = dia(30)
        r, a = self._criar(c, d, "MIBI manhã", etapa="estresse", coluna_titulo="Qualquer")
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual(a["coluna_titulo"], "Etapa")                                   # no MIBI o título é sempre Etapa
        self.assertEqual({l["senha"] for l in a["linhas"]}, {"Estresse"})
        hid = a["linhas"][1]["id"]
        self.post(c, f"/agenda/horario/{hid}/campo", {"campo": "paciente", "valor": "Ugo"})
        antes = "Estresse"
        for nova in ("Repouso", "Protocolo"):                                            # continua dando para trocar a etapa
            self.assertEqual(self.post(c, f"/agenda/horario/{hid}/campo", {"campo": "senha", "valor": nova, "antes": antes}).status_code, 200)
            antes = nova
        self.assertEqual(self.post(c, f"/agenda/horario/{hid}/campo", {"campo": "senha", "valor": "Outra", "antes": antes}).status_code, 400)
        self.assertEqual(self._criar(c, dia(31), "MIBI", etapa="Lixo")[0].status_code, 400)
        # + Horário e cópia do dia seguem o padrão; na cópia a etapa se inverte
        self.post(c, f"/agenda/{a['id']}/horario", {"qtd": "1"})
        novas = c.get(f"/agenda/dia/{d}").get_json()["agendas"][0]["linhas"]
        self.assertEqual(novas[-1]["senha"], "Estresse")
        d2 = dia(32)
        self.post(c, "/agenda/copiar", {"origem": d, "destino": d2, "com_pacientes": "0", "apagar_origem": "0"})
        copia = c.get(f"/agenda/dia/{d2}").get_json()["agendas"][0]
        self.assertEqual(copia["coluna_titulo"], "Etapa")
        self.assertEqual({l["senha"] for l in copia["linhas"]}, {"Repouso"})

    def test_outros_exames_trazem_o_exame_vinculado_e_titulo_editavel(self):
        c = self.cliente()
        d = dia(33)
        con = dbmod.conectar(self.app.config["DATABASE"])
        osso = con.execute("SELECT id, nome FROM exames WHERE nome LIKE '%SSEA'").fetchone()
        con.close()
        r, a = self._criar(c, d, "Agenda do osso", exame_id=str(osso["id"]))
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual(a["coluna_titulo"], "Exame")                                    # título padrão
        self.assertEqual({l["senha"] for l in a["linhas"]}, {osso["nome"]})
        r, b = self._criar(c, dia(34), "Outra agenda", exame_id=str(osso["id"]), coluna_titulo="Procedimento")
        self.assertEqual(b["coluna_titulo"], "Procedimento")
        hid = b["linhas"][0]["id"]
        self.assertEqual(self.post(c, f"/agenda/horario/{hid}/campo", {"campo": "senha", "valor": "AUT 12345", "antes": osso["nome"]}).status_code, 200)
        self.assertIn("Observação/Senha", self.texto(c.get("/static/js/agenda.js")))
