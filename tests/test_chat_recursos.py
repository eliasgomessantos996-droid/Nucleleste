"""Recursos novos do chat: pesquisa na conversa, "digitando…", responder a uma mensagem e tempo real (consulta que espera)."""
import os
import threading
import time
import unittest
from unittest import mock

from app import chat, views_chat
from app import db as dbmod
from tests.test_chat_blindagens import Base

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class RecursosDoChat(Base):
    def setUp(self):
        self.a = self.criar_usuario("CH_ANA", ["atendimentos"])
        self.b = self.criar_usuario("CH_BIA", ["atendimentos"])
        self.c = self.criar_usuario("CH_CLO", ["atendimentos"])
        self.con = dbmod.conectar(self.app.config["DATABASE"])
        self.con.execute("DELETE FROM chat_mensagens")
        self.con.commit()
        chat._digitando.clear()

    def tearDown(self):
        self.con.close()

    def enviar(self, de, para, corpo, **kw):
        return chat.enviar(self.con, de, para, corpo, **kw)

    # ================================================================ responder a uma mensagem
    def test_resposta_cita_a_mensagem_da_mesma_conversa(self):
        m1 = self.enviar(self.a, self.b, "Qual é o horário do mibi?")
        m2 = self.enviar(self.b, self.a, "É às 8h.", responde_id=m1["id"])
        self.assertEqual(m2["responde_id"], m1["id"])
        s = chat.serializar_lista(self.con, [m1, m2], self.b)
        self.assertIsNone(s[0]["responde"])
        self.assertEqual(s[1]["responde"], {"id": m1["id"], "minha": False, "corpo": "Qual é o horário do mibi?"})
        # "minha" diz de quem é a mensagem citada, do ponto de vista de quem está vendo
        self.assertTrue(chat.serializar_lista(self.con, [m2], self.a)[0]["responde"]["minha"])     # Ana vê que Bia citou a mensagem dela
        self.assertFalse(chat.serializar_lista(self.con, [m2], self.b)[0]["responde"]["minha"])
        m3 = self.enviar(self.a, self.b, "Obrigada!", responde_id=m2["id"])
        self.assertFalse(chat.serializar_lista(self.con, [m3], self.a)[0]["responde"]["minha"])
        self.assertTrue(chat.serializar_lista(self.con, [m3], self.b)[0]["responde"]["minha"])
        m4 = self.enviar(self.a, self.b, "Mais uma", responde_id=m3["id"])
        self.assertTrue(chat.serializar_lista(self.con, [m4], self.a)[0]["responde"]["minha"])     # citou a própria mensagem

    def test_citacao_de_outra_conversa_e_ignorada(self):
        alheia = self.enviar(self.a, self.c, "Mensagem entre Ana e Clo")
        m = self.enviar(self.b, self.a, "Tentando citar o que não é da conversa", responde_id=alheia["id"])
        self.assertIsNone(m["responde_id"])
        for ruim in (0, 999999, -3, None):
            self.assertIsNone(self.enviar(self.b, self.a, "x%s" % ruim, responde_id=ruim)["responde_id"])

    def test_citacao_longa_e_cortada_e_apagada_nao_quebra(self):
        longa = self.enviar(self.a, self.b, "palavra " * 100)
        m = self.enviar(self.b, self.a, "ok", responde_id=longa["id"])
        corpo = chat.serializar_lista(self.con, [m], self.b)[0]["responde"]["corpo"]
        self.assertLessEqual(len(corpo), 110)
        self.con.execute("DELETE FROM chat_mensagens WHERE id=?", (longa["id"],))
        self.con.commit()
        self.assertIsNone(chat.serializar_lista(self.con, [m], self.b)[0]["responde"])    # a original sumiu: sem citação, sem erro

    def test_responder_pela_tela(self):
        m1 = self.enviar(self.a, self.b, "Posso fechar o caixa agora?")
        cb = self.cliente("CH_BIA", "senha123")
        r = self.post(cb, "/mensagens/enviar", {"para": self.a, "corpo": "Pode sim.", "responde_id": m1["id"]})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["mensagem"]["responde"]["corpo"], "Posso fechar o caixa agora?")
        r = self.post(cb, "/mensagens/enviar", {"para": self.a, "corpo": "Sem citação"})
        self.assertIsNone(r.get_json()["mensagem"]["responde"])
        # a conversa carregada na página e a consulta periódica trazem a citação
        pagina = self.texto(cb.get("/mensagens?com=%d" % self.a))
        self.assertIn("Posso fechar o caixa agora?", pagina)
        dados = cb.get("/mensagens/novas?com=%d&depois=0&depois_conv=0" % self.a).get_json()
        citadas = [m["responde"] for m in dados["conversa"] if m["responde"]]
        self.assertEqual(len(citadas), 1)

    def test_botao_de_responder_e_barra_na_tela(self):
        pagina = self.texto(self.cliente("CH_ANA", "senha123").get("/mensagens?com=%d" % self.b))
        for trecho in ('id="chat-resposta"', "data-resp-fechar", "data-resp-texto"):
            self.assertIn(trecho, pagina)
        js = open(os.path.join(RAIZ, "app", "static", "js", "chat.js"), encoding="utf-8").read()
        for trecho in ("responde_id", "chat-responder", "definirResposta", "chat-citacao"):
            self.assertIn(trecho, js)

    # ================================================================ pesquisa na conversa
    def test_busca_ignora_acentos_e_maiusculas(self):
        self.enviar(self.a, self.b, "O laudo do João está pronto")
        self.enviar(self.b, self.a, "Vou buscar a QUITAÇÃO amanhã")
        self.enviar(self.a, self.b, "Bom dia")
        for termo in ("joao", "JOÃO", "Joao", "laudo do jo"):
            self.assertEqual(len(chat.buscar(self.con, self.a, self.b, termo)), 1, termo)
        achadas = chat.buscar(self.con, self.a, self.b, "quitacao")
        self.assertEqual([x["corpo"] for x in achadas], ["Vou buscar a QUITAÇÃO amanhã"])
        self.assertFalse(achadas[0]["minha"])
        self.assertTrue(chat.buscar(self.con, self.b, self.a, "quitacao")[0]["minha"])

    def test_busca_da_mais_nova_para_a_mais_antiga_e_so_da_conversa(self):
        self.enviar(self.a, self.b, "caixa primeiro")
        self.enviar(self.b, self.a, "caixa segundo")
        self.enviar(self.a, self.c, "caixa com outra pessoa")
        achadas = chat.buscar(self.con, self.a, self.b, "caixa")
        self.assertEqual([x["corpo"] for x in achadas], ["caixa segundo", "caixa primeiro"])
        self.assertEqual(chat.buscar(self.con, self.b, self.c, "caixa"), [])       # conversa que não existe

    def test_busca_exige_2_letras_e_limita_o_resultado(self):
        for i in range(chat.LIMITE_BUSCA + 15):   # direto no banco: o envio normal tem limite de mensagens por minuto
            self.con.execute("INSERT INTO chat_mensagens (de_id, para_id, corpo, criado_em) VALUES (?,?,?,?)",
                             (self.a, self.b, "mensagem repetida %d" % i, dbmod.agora()))
        self.con.commit()
        self.assertEqual(chat.buscar(self.con, self.a, self.b, ""), [])
        self.assertEqual(chat.buscar(self.con, self.a, self.b, "m "), [])      # espaços não contam
        self.assertEqual(chat.buscar(self.con, self.a, self.b, "m"), [])
        self.assertEqual(len(chat.buscar(self.con, self.a, self.b, "repetida")), chat.LIMITE_BUSCA)

    def test_busca_nao_mostra_avisos_da_gerencia_para_funcionarios(self):
        sistema = self.con.execute("SELECT id FROM usuarios WHERE sistema=1").fetchone()["id"]
        self.con.execute("INSERT INTO chat_mensagens (de_id, para_id, corpo, criado_em) VALUES (?,?,?,?)",
                         (sistema, self.a, "Vencimento secreto da licença", dbmod.agora()))
        self.con.execute("INSERT INTO chat_mensagens (de_id, para_id, corpo, criado_em, tipo) VALUES (?,?,?,?,'ATUALIZACAO')",
                         (sistema, self.a, "Aviso de atualização do sistema", dbmod.agora()))
        self.con.commit()
        self.assertEqual(chat.buscar(self.con, self.a, sistema, "vencimento"), [])
        self.assertEqual(len(chat.buscar(self.con, self.a, sistema, "atualização")), 1)

    def test_busca_pela_tela(self):
        self.enviar(self.a, self.b, "Lembrete: reunião às 15h")
        ca = self.cliente("CH_ANA", "senha123")
        d = ca.get("/mensagens/buscar?com=%d&q=reuniao" % self.b).get_json()
        self.assertEqual(len(d["resultados"]), 1)
        self.assertEqual(d["resultados"][0]["corpo"], "Lembrete: reunião às 15h")
        self.assertEqual(ca.get("/mensagens/buscar?com=%d&q=a" % self.b).get_json()["resultados"], [])
        self.assertEqual(ca.get("/mensagens/buscar?com=abc&q=reuniao").get_json()["resultados"], [])
        self.assertEqual(self.app.test_client().get("/mensagens/buscar?com=1&q=oi").status_code, 302)     # sem login
        pagina = self.texto(ca.get("/mensagens?com=%d" % self.b))
        for trecho in ("data-chat-buscar-abrir", 'id="chat-busca-conv"', "data-busca-resultados"):
            self.assertIn(trecho, pagina)

    # ================================================================ digitando…
    def test_digitando_aparece_para_a_outra_pessoa_e_some(self):
        ca, cb = self.cliente("CH_ANA", "senha123"), self.cliente("CH_BIA", "senha123")
        base = "/mensagens/novas?com=%d&depois=0&depois_conv=0"
        self.assertFalse(cb.get(base % self.a).get_json()["digitando"])
        r = self.post(ca, "/mensagens/digitando", {"para": self.b})
        self.assertEqual(r.status_code, 204)
        self.assertTrue(cb.get(base % self.a).get_json()["digitando"])
        self.assertFalse(ca.get(base % self.b).get_json()["digitando"])      # quem digita não vê o próprio aviso
        self.assertFalse(cb.get("/mensagens/novas?com=%d&depois=0&depois_conv=0" % self.c).get_json()["digitando"])
        # passados alguns segundos sem novo aviso, some
        chat._digitando[(self.a, self.b)] -= chat.DIGITANDO_S + 1
        self.assertFalse(cb.get(base % self.a).get_json()["digitando"])

    def test_digitando_exige_login_e_nao_vaza_entre_conversas(self):
        self.assertEqual(self.app.test_client().post("/mensagens/digitando", data={"para": 1}).status_code, 400)  # sem token
        ca = self.cliente("CH_ANA", "senha123")
        self.post(ca, "/mensagens/digitando", {"para": self.b})
        self.assertFalse(chat.esta_digitando(self.a, self.c))
        self.assertTrue(chat.esta_digitando(self.a, self.b))
        self.assertFalse(chat.esta_digitando(self.b, self.a))

    def test_memoria_do_digitando_nao_cresce_sem_limite(self):
        for i in range(700):
            chat._digitando[(10_000 + i, 1)] = time.time() - 3600
        chat.digitando_agora(self.a, self.b)
        self.assertLess(len(chat._digitando), 20)

    # ================================================================ tempo real (consulta que espera)
    def poll(self, cliente, com, espera, **extra):
        q = "/mensagens/novas?com=%d&depois=%s&depois_conv=%s&espera=%d" % (com, extra.pop("depois", 0), extra.pop("depois_conv", 0), espera)
        for k, v in extra.items():
            q += "&%s=%s" % (k, v)
        t0 = time.monotonic()
        r = cliente.get(q)
        return r.get_json(), time.monotonic() - t0

    def depois(self, atraso, fn):
        def tarefa():
            time.sleep(atraso)
            con = dbmod.conectar(self.app.config["DATABASE"])
            try:
                fn(con)
            finally:
                con.close()
        t = threading.Thread(target=tarefa, daemon=True)
        t.start()
        return t

    def test_sem_espera_responde_na_hora(self):
        cb = self.cliente("CH_BIA", "senha123")
        d, tempo = self.poll(cb, self.a, 0)
        self.assertLess(tempo, 0.8)
        self.assertIsNone(d["espera"])

    def test_com_espera_e_sem_novidade_volta_no_prazo(self):
        cb = self.cliente("CH_BIA", "senha123")
        d, tempo = self.poll(cb, self.a, 1, lidas_n=0, dig=0)
        self.assertTrue(d["espera"])
        self.assertGreaterEqual(tempo, 0.9)
        self.assertLess(tempo, 3.0)

    def test_mensagem_nova_acorda_a_espera(self):
        cb = self.cliente("CH_BIA", "senha123")
        t = self.depois(0.5, lambda con: chat.enviar(con, self.a, self.b, "Chegou!"))
        d, tempo = self.poll(cb, self.a, 10, lidas_n=0, dig=0)
        t.join()
        self.assertLess(tempo, 3.0)
        self.assertEqual([m["corpo"] for m in d["conversa"]], ["Chegou!"])
        self.assertEqual(d["novas"][0]["previa"], "Chegou!")

    def test_mensagem_de_outra_pessoa_acorda_a_espera_em_qualquer_tela(self):
        cb = self.cliente("CH_BIA", "senha123")
        t = self.depois(0.5, lambda con: chat.enviar(con, self.a, self.b, "Aviso em outra tela"))
        started = time.monotonic()
        d = cb.get("/mensagens/novas?depois=0&espera=10").get_json()      # sem conversa aberta
        t.join()
        self.assertLess(time.monotonic() - started, 3.0)
        self.assertEqual(d["novas"][0]["previa"], "Aviso em outra tela")

    def test_leitura_acorda_a_espera_de_quem_enviou(self):
        m = self.enviar(self.a, self.b, "Leia isto")
        ca = self.cliente("CH_ANA", "senha123")
        t = self.depois(0.5, lambda con: chat.marcar_lidas(con, self.b, self.a))
        d, tempo = self.poll(ca, self.b, 10, depois_conv=m["id"], lidas_n=0, dig=0)
        t.join()
        self.assertLess(tempo, 3.0)
        self.assertEqual(d["lidas_n"], 1)
        self.assertIn(m["id"], d["lidas"])

    def test_digitando_acorda_a_espera(self):
        cb = self.cliente("CH_BIA", "senha123")
        t = self.depois(0.5, lambda con: chat.digitando_agora(self.a, self.b))
        d, tempo = self.poll(cb, self.a, 10, lidas_n=0, dig=0)
        t.join()
        self.assertLess(tempo, 3.0)
        self.assertTrue(d["digitando"])

    def test_estado_igual_ao_do_navegador_nao_acorda_a_toa(self):
        # o navegador devolve lidas_n e dig que recebeu: sem mudança real, a espera vai até o fim (não vira laço rápido)
        m = self.enviar(self.a, self.b, "Já lida")
        chat.marcar_lidas(self.con, self.b, self.a)
        ca = self.cliente("CH_ANA", "senha123")
        d, tempo = self.poll(ca, self.b, 1, depois_conv=m["id"], lidas_n=1, dig=0)
        self.assertGreaterEqual(tempo, 0.9)
        self.assertEqual(d["lidas_n"], 1)

    def test_sem_vaga_de_espera_responde_na_hora_e_avisa(self):
        cheio = threading.BoundedSemaphore(1)
        cheio.acquire()
        cb = self.cliente("CH_BIA", "senha123")
        with mock.patch.object(views_chat, "_vagas_de_espera", cheio):
            d, tempo = self.poll(cb, self.a, 10)
        self.assertLess(tempo, 1.0)
        self.assertIs(d["espera"], False)

    def test_vagas_de_espera_sao_devolvidas(self):
        cb = self.cliente("CH_BIA", "senha123")
        pequeno = threading.BoundedSemaphore(2)
        with mock.patch.object(views_chat, "_vagas_de_espera", pequeno):
            for _ in range(3):
                self.poll(cb, self.a, 1, lidas_n=0, dig=0)
            self.assertTrue(pequeno.acquire(blocking=False))
            self.assertTrue(pequeno.acquire(blocking=False))   # as duas vagas continuam livres

    def test_um_usuario_nao_ocupa_todas_as_esperas(self):
        # abas abandonadas ficam esperando até o prazo: cada pessoa só segura ESPERAS_POR_USUARIO esperas por vez
        liberar = [views_chat._reservar_espera(self.a) for _ in range(views_chat.ESPERAS_POR_USUARIO)]
        self.assertTrue(all(liberar))
        self.assertIsNone(views_chat._reservar_espera(self.a))                  # a próxima não espera
        outra = views_chat._reservar_espera(self.b)                              # outra pessoa não é afetada
        self.assertIsNotNone(outra)
        cb = self.cliente("CH_ANA", "senha123")                                 # (Ana) já está no limite
        d, tempo = self.poll(cb, self.b, 10)
        self.assertLess(tempo, 1.0)
        self.assertIs(d["espera"], False)
        outra()
        for f in liberar:
            f()
        self.assertEqual(views_chat._esperas_do_usuario, {})
        self.assertIsNotNone(views_chat._reservar_espera(self.a))               # liberou: volta a poder esperar
        views_chat._esperas_do_usuario.clear()

    def test_espera_maxima_e_limitada(self):
        self.assertLessEqual(views_chat.ESPERA_MAX, 15)
        cb = self.cliente("CH_BIA", "senha123")
        self.enviar(self.a, self.b, "Pendente")
        d, tempo = self.poll(cb, self.a, 9999)                         # há mensagem pendente: volta na hora mesmo com espera enorme
        self.assertLess(tempo, 1.5)
        self.assertEqual(len(d["conversa"]), 1)

    def test_resposta_traz_o_necessario_para_o_proximo_pedido(self):
        cb = self.cliente("CH_BIA", "senha123")
        d, _ = self.poll(cb, self.a, 0)
        for chave in ("novas", "ultimo", "conversa", "lidas", "lidas_n", "digitando", "nao_lidas", "presenca", "espera"):
            self.assertIn(chave, d)

    def test_pagina_entrega_o_marcador_de_leitura(self):
        m = self.enviar(self.a, self.b, "Marcador")
        chat.marcar_lidas(self.con, self.b, self.a)
        pagina = self.texto(self.cliente("CH_ANA", "senha123").get("/mensagens?com=%d" % self.b))
        self.assertIn('data-lidas-n="1"', pagina)
        self.assertIn('data-leitura="0"', pagina)
        self.assertIn('data-nome="CH_BIA"', pagina)
        # contato do sistema: sem botões de responder
        sistema = self.con.execute("SELECT id FROM usuarios WHERE sistema=2").fetchone()["id"]
        self.assertIn('data-leitura="1"', self.texto(self.cliente("CH_ANA", "senha123").get("/mensagens?com=%d" % sistema)))

    # ================================================================ cliente (JS) e servidor
    def test_cliente_usa_tempo_real_com_protecoes(self):
        js = open(os.path.join(RAIZ, "app", "static", "js", "chat.js"), encoding="utf-8").read()
        for trecho in ("ESPERA_S", "AbortController", "'espera'", "lidas_n", "d.espera === false", "/mensagens/digitando",
                       "/mensagens/buscar", "digitando…", "AbortError"):
            self.assertIn(trecho, js, trecho)

    def test_servidor_tem_threads_para_as_esperas(self):
        for arquivo in ("servidor.py", "tray.pyw"):
            texto = open(os.path.join(RAIZ, arquivo), encoding="utf-8").read()
            self.assertNotIn("threads=8", texto, arquivo)
            self.assertIn("threads=48", texto, arquivo)
        self.assertLess(views_chat._vagas_de_espera._value, 48)      # as esperas nunca ocupam todas as threads


if __name__ == "__main__":
    unittest.main()
