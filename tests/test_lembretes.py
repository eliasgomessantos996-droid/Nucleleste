"""Lembretes em checklist: criação, marcações por usuário, reset diário, desativação, "para todos" e a janela ao entrar."""
from datetime import date, timedelta

from app import db as dbmod
from tests.test_chat_blindagens import Base

# no destino, GET '/' sem Referer manda para a agenda; a janela de lembretes testa-se no Início
DE_SISTEMA = {"Referer": "http://localhost/"}


class Lembretes(Base):
    def setUp(self):
        self.ana = self.criar_usuario("LEM_ANA")
        self.bia = self.criar_usuario("LEM_BIA")
        self.marcar_tutorial_visto(self.ana, self.bia)

    def marcar_tutorial_visto(self, *uids):
        con = dbmod.conectar(self.app.config["DATABASE"])
        for uid in uids:
            con.execute("UPDATE usuarios SET tutorial_visto=1 WHERE id=?", (uid,))
        con.commit()
        con.close()

    def sql(self, texto, args=()):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            cur = con.execute(texto, args)
            con.commit()
            return cur.fetchall()
        finally:
            con.close()

    def criar(self, c, titulo, itens="Item um\nItem dois", **extra):
        dados = {"titulo": titulo, "itens": itens, "data_inicio": date.today().isoformat()}
        dados.update(extra)
        r = self.post(c, "/lembretes/salvar", dados)
        self.assertEqual(r.status_code, 302, self.texto(r)[:300])
        return self.sql("SELECT id FROM lembretes WHERE titulo=? ORDER BY id DESC", (titulo,))[0]["id"]

    def pendentes(self, c):
        r = c.get("/lembretes/pendentes")
        self.assertEqual(r.status_code, 200)
        return {l["titulo"]: l for l in r.get_json()["lembretes"]}

    def itens_de(self, lid):
        return [r["id"] for r in self.sql("SELECT id FROM lembrete_itens WHERE lembrete_id=? ORDER BY ordem, id", (lid,))]

    def test_criar_e_aparece_nos_pendentes(self):
        c = self.cliente("LEM_ANA", "senha123")
        lid = self.criar(c, "Abrir a clínica")
        pend = self.pendentes(c)
        self.assertIn("Abrir a clínica", pend)
        self.assertEqual([i["texto"] for i in pend["Abrir a clínica"]["itens"]], ["Item um", "Item dois"])
        self.assertEqual(len(self.itens_de(lid)), 2)

    def test_limite_de_itens_e_texto(self):
        c = self.cliente("LEM_ANA", "senha123")
        muitos = "\n".join("item %d" % i for i in range(31))
        r = self.post(c, "/lembretes/salvar", {"titulo": "Muitos", "itens": muitos, "data_inicio": date.today().isoformat()})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.sql("SELECT COUNT(*) AS n FROM lembretes WHERE titulo='Muitos'")[0]["n"], 0)
        r = self.post(c, "/lembretes/salvar", {"titulo": "Longo", "itens": "x" * 201, "data_inicio": date.today().isoformat()})
        self.assertEqual(self.sql("SELECT COUNT(*) AS n FROM lembretes WHERE titulo='Longo'")[0]["n"], 0)

    def test_marcar_item_persiste(self):
        c = self.cliente("LEM_ANA", "senha123")
        lid = self.criar(c, "Conferir estoque")
        iid = self.itens_de(lid)[0]
        r = self.post(c, "/lembretes/%d/item/%d/marcar" % (lid, iid), {"valor": "1"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(self.pendentes(c)["Conferir estoque"]["itens"][0]["marcado"])
        self.post(c, "/lembretes/%d/item/%d/marcar" % (lid, iid), {"valor": "0"})
        self.assertFalse(self.pendentes(c)["Conferir estoque"]["itens"][0]["marcado"])

    def test_marcacao_e_de_cada_usuario(self):
        ana = self.cliente("LEM_ANA", "senha123")
        bia = self.cliente("LEM_BIA", "senha123")
        self.criar(ana, "Só da Ana", reset_diario="", para_todos="")
        lid = self.sql("SELECT id FROM lembretes WHERE titulo='Só da Ana'")[0]["id"]
        self.post(ana, "/lembretes/%d/item/%d/marcar" % (lid, self.itens_de(lid)[0]), {"valor": "1"})
        # a Bia não enxerga o lembrete da Ana e não consegue marcar nele
        self.assertNotIn("Só da Ana", self.pendentes(bia))
        r = self.post(bia, "/lembretes/%d/item/%d/marcar" % (lid, self.itens_de(lid)[0]), {"valor": "1"})
        self.assertEqual(r.status_code, 400)

    def test_reset_diario_apaga_marcas_de_outro_dia(self):
        c = self.cliente("LEM_ANA", "senha123")
        lid = self.criar(c, "Reset do dia", reset_diario="1")
        iid = self.itens_de(lid)[0]
        self.post(c, "/lembretes/%d/item/%d/marcar" % (lid, iid), {"valor": "1"})
        self.assertTrue(self.pendentes(c)["Reset do dia"]["itens"][0]["marcado"])
        # marca de ontem: ao carregar, o item volta desmarcado e a marca some do banco
        self.sql("UPDATE lembrete_marcas SET data=? WHERE lembrete_id=?", ((date.today() - timedelta(days=1)).isoformat(), lid))
        self.assertFalse(self.pendentes(c)["Reset do dia"]["itens"][0]["marcado"])
        self.assertEqual(self.sql("SELECT COUNT(*) AS n FROM lembrete_marcas WHERE lembrete_id=?", (lid,))[0]["n"], 0)

    def test_sem_reset_a_marca_continua_no_outro_dia(self):
        c = self.cliente("LEM_ANA", "senha123")
        lid = self.criar(c, "Sem reset")
        self.post(c, "/lembretes/%d/item/%d/marcar" % (lid, self.itens_de(lid)[0]), {"valor": "1"})
        self.sql("UPDATE lembrete_marcas SET data=? WHERE lembrete_id=?", ((date.today() - timedelta(days=3)).isoformat(), lid))
        self.assertTrue(self.pendentes(c)["Sem reset"]["itens"][0]["marcado"])

    def test_desativar_some_dos_pendentes(self):
        c = self.cliente("LEM_ANA", "senha123")
        lid = self.criar(c, "Desativar eu")
        r = self.post(c, "/lembretes/%d/desativar" % lid, {}, headers={"X-Requested-With": "XMLHttpRequest"})
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("Desativar eu", self.pendentes(c))
        r = self.post(c, "/lembretes/%d/ativar" % lid, {})
        self.assertIn("Desativar eu", self.pendentes(c))

    def test_para_todos_so_a_gestao_cria(self):
        ana = self.cliente("LEM_ANA", "senha123")
        self.criar(ana, "Tentativa geral", para_todos="1")
        self.assertEqual(self.sql("SELECT para_todos FROM lembretes WHERE titulo='Tentativa geral'")[0]["para_todos"], 0)
        admin = self.cliente("ADMIN", "admin")
        self.criar(admin, "Aviso geral", para_todos="1")
        self.assertEqual(self.sql("SELECT para_todos FROM lembretes WHERE titulo='Aviso geral'")[0]["para_todos"], 1)
        # a Bia (usuária comum) enxerga o "para todos", marca as próprias caixinhas e não consegue desativá-lo
        bia = self.cliente("LEM_BIA", "senha123")
        pend = self.pendentes(bia)
        self.assertIn("Aviso geral", pend)
        self.assertFalse(pend["Aviso geral"]["pode_editar"])
        lid = self.sql("SELECT id FROM lembretes WHERE titulo='Aviso geral'")[0]["id"]
        self.assertEqual(self.post(bia, "/lembretes/%d/item/%d/marcar" % (lid, self.itens_de(lid)[0]), {"valor": "1"}).status_code, 200)
        self.assertEqual(self.post(bia, "/lembretes/%d/desativar" % lid, {}, headers={"X-Requested-With": "XMLHttpRequest"}).status_code, 400)
        self.assertEqual(self.sql("SELECT ativo FROM lembretes WHERE id=?", (lid,))[0]["ativo"], 1)

    def test_usuario_nao_mexe_em_lembrete_alheio(self):
        ana = self.cliente("LEM_ANA", "senha123")
        bia = self.cliente("LEM_BIA", "senha123")
        lid = self.criar(ana, "Da Ana só")
        self.assertEqual(self.post(bia, "/lembretes/%d/desmarcar" % lid, {}).status_code, 400)
        self.assertEqual(self.post(bia, "/lembretes/%d/excluir" % lid, {}).status_code, 302)
        self.assertEqual(self.sql("SELECT COUNT(*) AS n FROM lembretes WHERE id=?", (lid,))[0]["n"], 1)
        self.assertEqual(bia.get("/lembretes/%d/editar" % lid).status_code, 302)

    def test_data_futura_nao_aparece(self):
        c = self.cliente("LEM_ANA", "senha123")
        amanha = (date.today() + timedelta(days=1)).isoformat()
        self.criar(c, "Começa amanhã", data_inicio=amanha)
        self.assertNotIn("Começa amanhã", self.pendentes(c))

    def test_pagina_de_gestao_mostra_os_meus(self):
        c = self.cliente("LEM_ANA", "senha123")
        self.criar(c, "Minha lista da tela")
        r = c.get("/lembretes")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Minha lista da tela", self.texto(r))
        self.assertIn('data-confirmar', self.texto(r))
        # a opção "para todos" só aparece para a gestão
        self.assertNotIn('name="para_todos"', self.texto(c.get("/lembretes/novo")))
        self.assertIn('name="para_todos"', self.texto(self.cliente("ADMIN", "admin").get("/lembretes/novo")))

    def test_janela_abre_uma_vez_por_login(self):
        c = self.cliente("LEM_ANA", "senha123")
        self.criar(c, "Janela do login")
        primeira = self.texto(c.get("/", headers=DE_SISTEMA))
        self.assertIn('id="dlg-lembretes"', primeira)
        self.assertNotIn('id="dlg-lembretes"', self.texto(c.get("/lembretes")))
        # novo login: a marca é zerada e a janela volta a abrir
        c2 = self.cliente("LEM_ANA", "senha123")
        self.assertIn('id="dlg-lembretes"', self.texto(c2.get("/", headers=DE_SISTEMA)))

    def test_janela_espera_o_tutorial(self):
        self.sql("UPDATE usuarios SET tutorial_visto=0 WHERE id=?", (self.bia,))
        c = self.cliente("LEM_BIA", "senha123")
        self.criar(c, "Depois do tutorial")
        self.assertNotIn('id="dlg-lembretes"', self.texto(c.get("/", headers=DE_SISTEMA)))   # o tutorial abre nesta página
        self.marcar_tutorial_visto(self.bia)
        self.assertIn('id="dlg-lembretes"', self.texto(c.get("/lembretes")))

    def test_sem_lembrete_nao_abre_janela(self):
        # os "para todos" criados pelos outros testes são desativados aqui (o banco é compartilhado pela classe)
        self.sql("UPDATE lembretes SET ativo=0")
        c = self.cliente("LEM_BIA", "senha123")
        self.assertNotIn('id="dlg-lembretes"', self.texto(c.get("/", headers=DE_SISTEMA)))
