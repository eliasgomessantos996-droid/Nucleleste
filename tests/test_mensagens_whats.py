"""Mensagens do WhatsApp editáveis pela gerência, aviso de avaliação da pesquisa e tela de agradecimento."""
import json
import unittest

from app import db as dbmod
from app import mensagens_whats as mw
from app import pesquisa as pesq
from tests.test_chat_blindagens import Base


class Textos(unittest.TestCase):
    def test_marcas_trocadas_pelos_dados(self):
        self.assertEqual(mw.montar("{saudacao}! Seu exame ({exame}) é dia {data} às {hora}.", nome="maria da silva",
                                   exame="MIBI", data="20/10/2026", hora="08:30"),
                         "Olá, Maria! Seu exame (MIBI) é dia 20/10/2026 às 08:30.")

    def test_sem_nome_a_saudacao_fica_so_ola(self):
        self.assertEqual(mw.montar("{saudacao}! Tudo bem?", nome=""), "Olá! Tudo bem?")

    def test_marca_desconhecida_fica_como_esta(self):
        self.assertEqual(mw.montar("Oi {desconhecida}", nome="Ana"), "Oi {desconhecida}")



def respostas_validas(con):
    """Uma resposta aceita para cada pergunta, conforme o tipo: escala, Sim/Não ou nota de 0 a 10 (NPS)."""
    valor = {'SIMNAO': 'Sim', 'NPS': '10'}
    return {"p%d" % r["id"]: valor.get(r["tipo"], pesq.OPCOES[0]) for r in pesq.perguntas(con)}


class Banco(Base):
    def setUp(self):
        super().setUp()
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            con.execute("DELETE FROM config WHERE chave=?", (mw.CHAVE,))
            con.commit()
        finally:
            con.close()

    def test_texto_igual_ao_padrao_nao_fica_guardado(self):
        with self.app.app_context():
            mw.salvar({"falta": mw.TIPOS["falta"][1]})
            self.assertEqual(mw.atuais()["falta"], mw.TIPOS["falta"][1])
            con = dbmod.conectar(self.app.config["DATABASE"])
            try:
                self.assertEqual(json.loads(con.execute("SELECT valor FROM config WHERE chave=?", (mw.CHAVE,)).fetchone()[0]), {})
            finally:
                con.close()

    def test_gerencia_salva_e_restaura(self):
        c = self.cliente()
        self.post(c, "/mensagens-whatsapp", {"falta": "Oi {nome}, sentimos sua falta no {exame}.", "lembrete": "", "reagendamento": ""})
        with self.app.app_context():
            self.assertEqual(mw.atuais()["falta"], "Oi {nome}, sentimos sua falta no {exame}.")
            self.assertEqual(mw.atuais()["lembrete"], mw.TIPOS["lembrete"][1])
        self.post(c, "/mensagens-whatsapp", {"acao": "restaurar"})
        with self.app.app_context():
            self.assertEqual(mw.atuais()["falta"], mw.TIPOS["falta"][1])

    def test_so_gerencia_acessa(self):
        self.criar_usuario("AGENDA1", ["agenda"])
        c = self.cliente("AGENDA1", "senha123")
        self.assertNotEqual(c.get("/mensagens-whatsapp").status_code, 200)

    def test_agenda_recebe_os_textos_editados(self):
        self.post(self.cliente(), "/mensagens-whatsapp", {"lembrete": "Lembrete personalizado {exame}"})
        pagina = self.texto(self.cliente().get("/agenda"))
        self.assertIn("Lembrete personalizado {exame}", pagina)

    def test_agenda_leva_so_o_primeiro_nome_de_quem_envia(self):
        self.criar_usuario("ANA LUIZA SOUZA", ["agenda"])
        pagina = self.texto(self.cliente("ANA LUIZA SOUZA", "senha123").get("/agenda"))
        self.assertIn('id="ag-usuario">"Ana"</script>', pagina)
        self.assertNotIn("Luiza", pagina.split('id="ag-usuario"')[1][:40])

    def test_avaliacao_avisa_a_gerencia_sem_o_comentario(self):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            pesq.garantir(con)
            pesq.definir_ativa(con, True)
            form = respostas_validas(con)
            form["sugestao"] = "TEXTO SECRETO DO CLIENTE"
            con.commit()
        finally:
            con.close()
        self.post_publico(form)
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            corpos = [r["corpo"] for r in con.execute("SELECT corpo FROM chat_mensagens WHERE corpo LIKE 'Nova avaliação%'")]
        finally:
            con.close()
        self.assertTrue(corpos)
        self.assertNotIn("TEXTO SECRETO", " ".join(corpos))

    def test_aviso_traz_sim_nao_que_leva_a_avaliacao(self):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            pesq.garantir(con)
            pesq.definir_ativa(con, True)
            form = respostas_validas(con)
            con.commit()
        finally:
            con.close()
        self.post_publico(form)
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            aviso = con.execute("SELECT id, acao, acao_url, para_id FROM chat_mensagens WHERE acao='AVALIACAO_VER' "
                                "ORDER BY id DESC LIMIT 1").fetchone()
        finally:
            con.close()
        self.assertIsNotNone(aviso)
        self.assertIn("/qualidade/satisfacao/respostas#resposta-", aviso["acao_url"])
        # o destinatário responde Sim: fica registrado e o endereço volta para abrir a tela
        c = self.cliente()
        r = self.post(c, "/mensagens/%d/acao" % aviso["id"], {"resposta": "SIM"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["resposta"], "SIM")
        self.assertEqual(r.get_json()["url"], aviso["acao_url"])
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            self.assertEqual(con.execute("SELECT acao_resp FROM chat_mensagens WHERE id=?", (aviso["id"],)).fetchone()[0], "SIM")
        finally:
            con.close()

    def test_outro_usuario_nao_responde_o_aviso(self):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            cid = con.execute("INSERT INTO chat_mensagens (de_id, para_id, corpo, criado_em, acao, acao_url) "
                              "VALUES (1, 1, 'teste', '2026-10-18 10:00:00', 'AVALIACAO_VER', '/x')").lastrowid
            con.commit()
        finally:
            con.close()
        self.criar_usuario("OUTRO1", ["agenda"])
        c = self.cliente("OUTRO1", "senha123")
        self.assertEqual(self.post(c, "/mensagens/%d/acao" % cid, {"resposta": "NAO"}).status_code, 404)

    def post_publico(self, form):
        cli = self.app.test_client()
        return cli.post("/pesquisa", data=form, environ_base={"REMOTE_ADDR": "127.0.0.1"})

    def test_obrigado_tem_logo_e_fecha_sozinho(self):
        cli = self.app.test_client()
        pagina = cli.get("/pesquisa/obrigado", environ_base={"REMOTE_ADDR": "127.0.0.1"}).get_data(as_text=True)
        self.assertIn("logo-atomo", pagina)
        self.assertIn("about:blank", pagina)


if __name__ == "__main__":
    unittest.main()
