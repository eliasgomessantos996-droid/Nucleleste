"""Suporte: tema, dados do envio, cartão em cápsulas nas Mensagens ao não aceitar e relatório de pendências em PDF por tema."""
import json

from app import db as dbmod
from tests.test_chat_blindagens import Base


class SuporteCartao(Base):
    def _linhas(self, sql, params=()):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            return [dict(r) for r in con.execute(sql, params)]
        finally:
            con.close()

    def _id(self, nome):
        return self._linhas("SELECT id FROM usuarios WHERE usuario=?", (nome,))[0]["id"]

    def _enviar(self, c, tipo, titulo, descricao, **extra):
        dados = {"titulo": titulo, "descricao": descricao, "cl_tela": "1920x1080", "cl_fuso": "America/Sao_Paulo", "cl_pagina": "http://x/agenda"}
        dados.update(extra)
        return self.post(c, "/suporte/bug" if tipo == "BUG" else "/suporte/sugestao", dados)

    def test_envio_guarda_tema_e_dados_do_aparelho(self):
        self.criar_usuario("CART_A", ["atendimentos"])
        c = self.cliente("CART_A", "senha123")
        self.assertIn("Segurança", self.texto(c.get("/suporte")))
        self._enviar(c, "SUGESTAO", "Trocar a senha mais fácil", "Quero poder trocar a senha sem pedir à gerência.", tema="Segurança")
        self._enviar(c, "BUG", "Tema invalido", "Descrição longa o bastante para o teste.", tema="Inventado")
        itens = self._linhas("SELECT * FROM suporte_itens WHERE usuario='CART_A' ORDER BY id")
        self.assertEqual([i["tema"] for i in itens], ["Segurança", "Outro"])
        meta = json.loads(itens[0]["meta"])
        self.assertEqual(meta["usuario"], "CART_A")
        self.assertEqual(meta["cliente"]["tela"], "1920x1080")
        self.assertTrue(meta["ip"] and meta["navegador"] and meta["sistema"] and meta["dispositivo"] and meta["versao_sistema"])
        self.assertIn("ultimas_acoes", meta)

    def test_nao_aceitar_abre_conversa_com_cartao_e_ninguem_imita(self):
        uid = self.criar_usuario("CART_B", ["atendimentos"])
        c = self.cliente("CART_B", "senha123")
        self._enviar(c, "SUGESTAO", "Relatório por médico", "Gostaria de um relatório de exames por médico solicitante.", tema="Organização")
        iid = self._linhas("SELECT id FROM suporte_itens WHERE usuario='CART_B'")[0]["id"]
        self.criar_usuario("DEV_CART", ["suporte_dev"])
        dev = self.cliente("DEV_CART", "senha123")
        r = self.post(dev, "/suporte/%d/decidir" % iid, {"decisao": "recusar"})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers["Location"].endswith("/mensagens?com=%d" % uid))
        self.assertEqual(self._linhas("SELECT status FROM suporte_itens WHERE id=?", (iid,))[0]["status"], "RECUSADA")
        # o cartão está na conversa do usuário, com a citação e o nome de quem enviou, e chega como não lido
        msg = self._linhas("SELECT * FROM chat_mensagens WHERE para_id=? AND cartao IS NOT NULL", (uid,))
        self.assertEqual(len(msg), 1)
        cartao = json.loads(msg[0]["cartao"])
        self.assertEqual((cartao["tipo"], cartao["autor"], cartao["tema"]), ("SUPORTE_RECUSA", "CART_B", "Organização"))
        self.assertIn("relatório de exames por médico", cartao["citacao"])
        pagina = self.texto(c.get("/mensagens?com=%d" % self._id("DEV_CART")))
        self.assertIn("SUPORTE_RECUSA", pagina)
        self.assertIn("chat-cartao-sis", self.texto(c.get("/static/css/chat.css")))
        # texto comum, mesmo parecido, nunca vira cartão: o campo cartao só é gravado pelo servidor
        self.post(c, "/mensagens/enviar", {"para": self._id("DEV_CART"), "corpo": "**NÃO ACEITA**", "cartao": '{"tipo":"SUPORTE_RECUSA"}'},
                  headers={"Accept": "application/json"})
        falsas = self._linhas("SELECT cartao FROM chat_mensagens WHERE de_id=? AND cartao IS NOT NULL", (uid,))
        self.assertEqual(falsas, [])

    def test_aceitar_nao_envia_mensagem(self):
        uid = self.criar_usuario("CART_C", ["atendimentos"])
        c = self.cliente("CART_C", "senha123")
        self._enviar(c, "BUG", "Erro ao salvar", "Ao salvar a ficha aparece uma tela branca.", tema="Desempenho")
        iid = self._linhas("SELECT id FROM suporte_itens WHERE usuario='CART_C'")[0]["id"]
        self.criar_usuario("DEV_CART", ["suporte_dev"])
        dev = self.cliente("DEV_CART", "senha123")
        self.post(dev, "/suporte/%d/decidir" % iid, {"decisao": "aceitar"})
        self.assertEqual(self._linhas("SELECT COUNT(*) AS n FROM chat_mensagens WHERE para_id=? AND cartao IS NOT NULL", (uid,))[0]["n"], 0)

    def test_relatorio_pdf_por_tema_com_capa_e_sumario(self):
        self.criar_usuario("CART_D", ["atendimentos"])
        c = self.cliente("CART_D", "senha123")
        self.criar_usuario("DEV_CART", ["suporte_dev"])
        dev = self.cliente("DEV_CART", "senha123")
        for titulo, tipo, tema in (("Backup mais claro", "SUGESTAO", "Segurança"), ("Lista lenta", "BUG", "Desempenho"), ("Menu confuso", "SUGESTAO", "Organização")):
            self._enviar(c, tipo, titulo, "Descrição do item %s para a próxima atualização." % titulo, tema=tema)
            iid = self._linhas("SELECT id FROM suporte_itens WHERE titulo=?", (titulo,))[0]["id"]
            self.post(dev, "/suporte/%d/decidir" % iid, {"decisao": "aceitar"})
        r = dev.get("/suporte/relatorio.pdf")
        self.assertEqual(r.status_code, 200)
        corpo = r.get_data()
        self.assertTrue(corpo.startswith(b"%PDF"))
        self.assertEqual(dev.get("/suporte/relatorio.pdf?baixar=1").headers["Content-Disposition"].startswith("attachment"), True)
        from app import suporte
        itens = suporte.pasta(dbmod.conectar(self.app.config["DATABASE"]))["pendentes"]
        grupos = [t for t, _ in suporte.por_tema(itens)]
        self.assertEqual(grupos, ["Segurança", "Organização", "Desempenho"])      # ordem fixa dos temas


class DadosProtegidos(Base):
    def test_desenvolvedor_exclui_resposta_sem_registrar_no_log(self):
        from app import pesquisa
        con = dbmod.conectar(self.app.config["DATABASE"])
        pesquisa.garantir(con)
        rid = con.execute("INSERT INTO cq_sat_respostas (data, criado_em, nome, nota) VALUES (date('now','localtime'), datetime('now','localtime'), 'Cliente X', 9)").lastrowid
        con.execute("INSERT INTO cq_sat_itens (resposta_id, ordem, pergunta, opcao) VALUES (?,1,'P','Bom')", (rid,))
        con.commit()
        self.criar_usuario("DEV_DADOS", ["suporte_dev"])
        dev = self.cliente("DEV_DADOS", "senha123")
        self.assertIn("Cliente X", self.texto(dev.get("/suporte/dados")))
        antes = con.execute("SELECT COUNT(*) FROM auditoria").fetchone()[0]
        r = self.post(dev, "/suporte/dados/excluir", {"id": str(rid)})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM cq_sat_respostas WHERE id=?", (rid,)).fetchone()[0], 0)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM auditoria").fetchone()[0], antes)
        con.close()
        self.criar_usuario("COMUM_DADOS", ["atendimentos"])
        self.assertIn(self.cliente("COMUM_DADOS", "senha123").get("/suporte/dados").status_code, (302, 403))
