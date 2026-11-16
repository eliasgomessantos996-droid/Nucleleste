"""Mensagens livres (estilo WhatsApp) e controle de blindagens (cliente de teste do Flask)."""
import gc
import io
import json
import os
import re
import shutil
import tempfile
import time
import unittest
from datetime import date, timedelta

from werkzeug.security import generate_password_hash

from app import create_app
from app import db as dbmod


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pasta = tempfile.TemporaryDirectory()
        cls.app = create_app(os.path.join(cls.pasta.name, "t.db"))
        cls.app.config["TESTING"] = True

    @classmethod
    def tearDownClass(cls):
        # no Windows o banco pode ficar aberto por uma conexão que ainda não foi coletada: tenta de novo antes de desistir
        gc.collect()
        try:
            cls.pasta.cleanup()
        except PermissionError:
            shutil.rmtree(cls.pasta.name, ignore_errors=True)

    def criar_usuario(self, nome, modulos=None, admin=0):
        con = dbmod.conectar(self.app.config["DATABASE"])
        con.execute("INSERT OR REPLACE INTO usuarios (usuario, senha_hash, admin, ativo, modulos) VALUES (?,?,?,1,?)",
                    (nome, generate_password_hash("senha123"), admin, json.dumps(modulos or [])))
        con.commit()
        uid = con.execute("SELECT id FROM usuarios WHERE usuario=?", (nome,)).fetchone()["id"]
        con.close()
        return uid

    def cliente(self, usuario="ADMIN", senha="admin"):
        c = self.app.test_client()
        c.get("/login")
        with c.session_transaction() as s:
            token = s["csrf"]
        r = c.post("/login", data={"usuario": usuario, "senha": senha, "_csrf": token})
        self.assertEqual(r.status_code, 302, r.get_data(as_text=True)[:300])
        c.get("/saude-inexistente")
        return c

    def post(self, c, url, data=None, **kw):
        with c.session_transaction() as s:
            token = s["csrf"]
        dados = dict(data or {})
        dados["_csrf"] = token
        if url == "/agenda/criar" and "exame_id" not in dados:
            # a agenda exige o exame cadastrado: nos testes, quando o nome não casa com nenhum, usa o primeiro exame do cadastro
            from app import agenda as _ag
            con = dbmod.conectar(self.app.config["DATABASE"])
            try:
                cad = con.execute("SELECT id, nome FROM exames WHERE ativo=1 ORDER BY ordem, nome").fetchall()
            finally:
                con.close()
            if not _ag.exame_do_nome(dados.get("exame"), cad):
                dados["exame_id"] = str(next(e for e in cad if "MIBI" not in e["nome"])["id"])
        return c.post(url, data=dados, **kw)

    def texto(self, r):
        return r.get_data(as_text=True)


class Mensagens(Base):
    def test_conversa_completa_e_nao_lidas(self):
        ana = self.criar_usuario("ANA")
        bia = self.criar_usuario("BIA")
        a, b = self.cliente("ANA", "senha123"), self.cliente("BIA", "senha123")
        # todos aparecem na lista de contatos, inclusive a gestão (admin)
        pagina = self.texto(a.get("/mensagens"))
        self.assertIn("BIA", pagina)
        self.assertIn("ADMIN", pagina)
        self.assertIn("Gestão", pagina)
        # envio
        r = self.post(a, "/mensagens/enviar", {"para": bia, "corpo": "Oi Bia, tudo bem?"}, headers={"Accept": "application/json"})
        self.assertEqual(r.status_code, 200, self.texto(r))
        mid = r.get_json()["mensagem"]["id"]
        self.assertFalse(r.get_json()["mensagem"]["lida"])
        # Bia recebe o aviso sem recarregar: a consulta periódica traz a mensagem nova e o contador
        n = b.get("/mensagens/novas?depois=0", headers={"X-Passivo": "1"}).get_json()
        self.assertEqual(n["nao_lidas"], 1)
        self.assertEqual(n["novas"][0]["de_nome"], "ANA")
        self.assertEqual(n["novas"][0]["id"], mid)
        # o menu mostra o selo mesmo se ela só abrir o sistema depois (a mensagem ficou gravada)
        self.assertIn('data-msg-badge>1<', self.texto(b.get("/")).replace('\n', '').replace(' hidden', ''))
        # ao abrir a conversa a mensagem é marcada como lida e aparece na tela
        pg = self.texto(b.get(f"/mensagens?com={ana}"))
        self.assertIn("Oi Bia, tudo bem?", pg)
        self.assertEqual(b.get("/mensagens/novas?depois=0").get_json()["nao_lidas"], 0)
        # a Ana vê o "lida" (dois tiques) na próxima consulta da conversa
        ana_poll = a.get(f"/mensagens/novas?depois={mid}&com={bia}&depois_conv={mid}&desde={mid}").get_json()
        self.assertEqual(ana_poll["lidas"], [mid])
        # resposta e consulta incremental da conversa
        self.post(b, "/mensagens/enviar", {"para": ana, "corpo": "Tudo!"}, headers={"Accept": "application/json"})
        inc = a.get(f"/mensagens/novas?depois={mid}&com={bia}&depois_conv={mid}&visivel=1").get_json()
        self.assertEqual([m["corpo"] for m in inc["conversa"]], ["Tudo!"])
        self.assertEqual(inc["nao_lidas"], 0)  # estava com a conversa aberta e visível

    def test_mensagem_ausente_aparece_no_resumo_ao_entrar(self):
        carlos = self.criar_usuario("CARLOS")
        dora = self.criar_usuario("DORA")
        c = self.cliente("CARLOS", "senha123")
        self.post(c, "/mensagens/enviar", {"para": dora, "corpo": "Reunião às 14h"}, headers={"Accept": "application/json"})
        d = self.cliente("DORA", "senha123")  # só entra depois
        r = d.get("/mensagens/novas?depois=999999&resumo=1").get_json()
        self.assertEqual(r["nao_lidas"], 1)
        self.assertEqual([i["de_nome"] for i in r["resumo"]], ["CARLOS"])
        self.assertEqual(carlos, r["resumo"][0]["de_id"])

    def test_validacoes(self):
        eva = self.criar_usuario("EVA")
        e = self.cliente("EVA", "senha123")
        h = {"Accept": "application/json"}
        self.assertEqual(self.post(e, "/mensagens/enviar", {"para": eva, "corpo": "x"}, headers=h).status_code, 400)  # consigo mesma
        self.assertEqual(self.post(e, "/mensagens/enviar", {"para": 99999, "corpo": "x"}, headers=h).status_code, 400)
        self.assertEqual(self.post(e, "/mensagens/enviar", {"para": 1, "corpo": "   "}, headers=h).status_code, 400)
        self.assertEqual(self.post(e, "/mensagens/enviar", {"para": 1, "corpo": "a" * 2001}, headers=h).status_code, 400)
        self.assertEqual(e.get("/mensagens?com=99999").status_code, 404)

    def test_exige_login(self):
        c = self.app.test_client()
        self.assertEqual(c.get("/mensagens").status_code, 302)
        self.assertEqual(c.get("/mensagens/novas").status_code, 302)

    def test_dashboard_sem_caixa(self):
        c = self.cliente()
        r = c.get("/dashboard")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("lançamentos de caixa em aberto", self.texto(r))
        self.assertNotIn("kpi-rotulo\">Caixa<", self.texto(r))


class Blindagens(Base):
    def hoje(self, dias=0):
        return (date.today() + timedelta(days=dias)).isoformat()

    def cadastrar(self, c, lote, validade, **extra):
        dados = {"lote": lote, "nota_fiscal": "1234", "serie": "1", "data_nota": self.hoje(-400), "cfop": "5949", "validade": validade}
        dados.update(extra)
        return self.post(c, "/blindagens/novo", dados)

    def linha(self, lote):
        con = dbmod.conectar(self.app.config["DATABASE"])
        r = con.execute("SELECT * FROM blindagens WHERE lote=?", (lote,)).fetchone()
        con.close()
        return r

    def test_cadastro_status_e_vencimento(self):
        c = self.cliente()
        r = self.cadastrar(c, "633IP1637", self.hoje(30))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.linha("633IP1637")["status"], "VÁLIDO")
        # já vencida na entrada: o controle troca para VENCIDO
        self.cadastrar(c, "634IP1629", self.hoje(-1))
        self.assertEqual(self.linha("634IP1629")["status"], "VENCIDO")
        # validade expirando com o tempo: simula vencimento do lote válido
        con = dbmod.conectar(self.app.config["DATABASE"])
        con.execute("UPDATE blindagens SET validade=? WHERE lote='633IP1637'", (self.hoje(-2),))
        con.commit(); con.close()
        self.assertIn("VENCIDO", self.texto(c.get("/blindagens")))
        self.assertEqual(self.linha("633IP1637")["status"], "VENCIDO")

    def test_validacoes_do_cadastro(self):
        c = self.cliente()
        for lote, cfop in (("AB-12", "5949"), ("AB 12!", "5949"), ("", "5949"), ("OKLOTE1", "59"), ("OKLOTE1", "abc")):
            r = self.cadastrar(c, lote, self.hoje(10), cfop=cfop)
            self.assertEqual(r.status_code, 200, (lote, cfop))  # volta ao formulário com erro
        self.assertIsNone(self.linha("OKLOTE1"))
        self.assertEqual(self.cadastrar(c, "dup001", self.hoje(10)).status_code, 302)
        self.assertEqual(self.linha("DUP001")["lote"], "DUP001")  # normaliza para maiúsculas
        self.assertEqual(self.cadastrar(c, "DUP001", self.hoje(10)).status_code, 200)  # lote duplicado
        r = self.cadastrar(c, "SEMDATA1", self.hoje(10), data_nota="")
        self.assertEqual(r.status_code, 200)
        r = self.cadastrar(c, "VALANT1", self.hoje(-500))  # validade antes da data da nota
        self.assertEqual(r.status_code, 200)

    def test_devolucao_completa_e_documentos(self):
        c = self.cliente()
        for lote, dias in (("DEV001", -5), ("DEV002", -3), ("VAL001", 90)):
            self.cadastrar(c, lote, self.hoje(dias))
        self.assertIn("DEV001", self.texto(c.get("/blindagens/devolucao")))
        ids = {l: self.linha(l)["id"] for l in ("DEV001", "DEV002", "VAL001")}
        # não aceita blindagem válida
        r = self.post(c, "/blindagens/devolucao", {"ids": [ids["DEV001"], ids["VAL001"]], "valor_unitario": "405,80"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("Só é possível solicitar", self.texto(r))
        self.assertEqual(self.linha("DEV001")["status"], "VENCIDO")
        # nada marcado
        self.assertEqual(self.post(c, "/blindagens/devolucao", {"valor_unitario": "405,80"}).status_code, 200)
        # solicitação correta
        r = self.post(c, "/blindagens/devolucao", {"ids": [ids["DEV001"], ids["DEV002"]], "valor_unitario": "405,80"})
        self.assertEqual(r.status_code, 302)
        did = int(r.headers["Location"].rstrip("/").split("/")[-1])
        self.assertEqual(self.linha("DEV001")["status"], "DEVOLUÇÃO SOLICITADA")
        self.assertEqual(self.linha("DEV002")["status"], "DEVOLUÇÃO SOLICITADA")
        self.assertEqual(self.linha("VAL001")["status"], "VÁLIDO")
        pagina = self.texto(c.get(f"/blindagens/devolucao/{did}"))
        self.assertIn("Baixar planilha (PDF)", pagina)
        self.assertIn("Baixar toda a documentação", pagina)
        # já solicitada: não pode alterar, excluir nem solicitar de novo
        self.assertEqual(self.post(c, f"/blindagens/{ids['DEV001']}", {"lote": "DEV001"}).status_code, 302)
        self.post(c, f"/blindagens/{ids['DEV001']}/excluir")
        self.assertIsNotNone(self.linha("DEV001"))
        r = self.post(c, "/blindagens/devolucao", {"ids": [ids["DEV001"]], "valor_unitario": "405,80"})
        self.assertEqual(r.status_code, 200)

        # planilha em PDF e Excel
        pdf = c.get(f"/blindagens/devolucao/{did}/planilha.pdf")
        self.assertEqual(pdf.mimetype, "application/pdf")
        self.assertTrue(pdf.data.startswith(b"%PDF"))
        self.assertIn("attachment", pdf.headers["Content-Disposition"])
        xlsx = c.get(f"/blindagens/devolucao/{did}/planilha.xlsx")
        from openpyxl import load_workbook
        ws = load_workbook(io.BytesIO(xlsx.data)).active
        valores = [[cel.value for cel in linha] for linha in ws.iter_rows(min_row=5)]
        self.assertEqual(valores[0], ["Item", "Lote", "Nota fiscal", "Série", "Data da nota fiscal", "CFOP", "Validade"])
        self.assertEqual({v[1] for v in valores[1:]}, {"DEV001", "DEV002"})
        self.assertEqual(valores[1][5], "5949")

        # documentos: PDF único (quantidades padrão) e cada documento individualmente
        todos = c.get(f"/blindagens/devolucao/{did}/documentos.pdf?baixar=1")
        self.assertEqual(todos.mimetype, "application/pdf")
        paginas = lambda d: len(re.findall(rb"/Type\s*/Page[^s]", d))
        # 2 declarações + 4 expedidor (2 pág. cada) + 2 etiquetas destinatário (1 folha) + 2 ONU (1 folha) + 2 material radioativo (1 folha)
        self.assertEqual(paginas(todos.data), 2 + 8 + 1 + 1 + 1)
        r = c.get(f"/blindagens/devolucao/{did}/documento/declaracao_transporte.pdf?qtd=3")
        self.assertEqual(paginas(r.data), 3)  # cada via cabe em uma página
        self.assertNotIn("attachment", r.headers.get("Content-Disposition", ""))
        r = c.get(f"/blindagens/devolucao/{did}/documento/etiqueta_2910.pdf?qtd=5")
        self.assertEqual(paginas(r.data), 3)  # 2 por folha
        r = c.get(f"/blindagens/devolucao/{did}/documento/material_radioativo.pdf?qtd=7")
        self.assertEqual(paginas(r.data), 3)  # 3 por folha
        r = c.get(f"/blindagens/devolucao/{did}/documento/etiqueta_destinatario.pdf?qtd=3")
        self.assertEqual(paginas(r.data), 2)
        r = c.get(f"/blindagens/devolucao/{did}/documento/declaracao_expedidor.pdf?qtd=1")
        self.assertEqual(paginas(r.data), 2)
        self.assertEqual(c.get(f"/blindagens/devolucao/{did}/documento/inexistente.pdf").status_code, 404)
        self.assertEqual(c.get("/blindagens/devolucao/99999/planilha.pdf").status_code, 404)

    def test_confirmar_devolvida_manual(self):
        c = self.cliente()
        for lote, dias in (("RET001", -6), ("RET002", -4), ("RET003", 20)):
            self.cadastrar(c, lote, self.hoje(dias))
        ids = {l: self.linha(l)["id"] for l in ("RET001", "RET002", "RET003")}
        self.post(c, "/blindagens/devolucao", {"ids": [ids["RET001"], ids["RET002"]], "valor_unitario": "405,80"})
        self.assertEqual(self.linha("RET001")["status"], "DEVOLUÇÃO SOLICITADA")
        # o sistema não muda para DEVOLVIDA sozinho, por mais que o tempo passe
        self.assertIn("RET001", self.texto(c.get("/blindagens/devolvidas")))
        self.assertEqual(self.linha("RET001")["status"], "DEVOLUÇÃO SOLICITADA")
        # validações: data futura, sem data, data anterior à solicitação, blindagem válida
        self.assertEqual(self.post(c, "/blindagens/devolvidas", {"ids": [ids["RET001"]], "data_devolvida": self.hoje(3)}).status_code, 200)
        self.assertEqual(self.post(c, "/blindagens/devolvidas", {"ids": [ids["RET001"]], "data_devolvida": ""}).status_code, 200)
        self.assertEqual(self.post(c, "/blindagens/devolvidas", {"ids": [ids["RET001"]], "data_devolvida": self.hoje(-30)}).status_code, 200)
        r = self.post(c, "/blindagens/devolvidas", {"ids": [ids["RET003"]], "data_devolvida": self.hoje(0)})
        self.assertIn("Só é possível confirmar", self.texto(r))
        self.assertEqual(self.linha("RET003")["status"], "VÁLIDO")
        self.assertEqual(self.linha("RET001")["status"], "DEVOLUÇÃO SOLICITADA")
        # confirmação de uma: a data e o responsável ficam registrados
        r = self.post(c, "/blindagens/devolvidas", {"ids": [ids["RET001"]], "data_devolvida": self.hoje(0)})
        self.assertEqual(r.status_code, 302)
        lin = self.linha("RET001")
        self.assertEqual(lin["status"], "DEVOLVIDA")
        self.assertEqual(lin["devolvida_em"], self.hoje(0))
        self.assertEqual(lin["devolvida_por"], "ADMIN")
        self.assertEqual(self.linha("RET002")["status"], "DEVOLUÇÃO SOLICITADA")
        # devolvida: não edita, não exclui, não entra de novo na confirmação
        self.post(c, f"/blindagens/{ids['RET001']}/excluir")
        self.assertIsNotNone(self.linha("RET001"))
        self.post(c, f"/blindagens/{ids['RET001']}", {"lote": "RET001", "nota_fiscal": "1", "serie": "1",
                                                     "data_nota": self.hoje(-400), "cfop": "5949", "validade": self.hoje(5)})
        self.assertEqual(self.linha("RET001")["status"], "DEVOLVIDA")
        pagina = self.texto(c.get("/blindagens/devolvidas"))
        self.assertIn("Devolvidas", pagina)
        self.assertIn("DEVOLVIDA", self.texto(c.get("/blindagens?status=DEVOLVIDA")))
        self.assertIn("RET001", self.texto(c.get("/blindagens?status=DEVOLVIDA")))

    def test_permissoes_por_modulo(self):
        self.criar_usuario("SEMACESSO", [])
        self.criar_usuario("CADASTRA", ["blind_cadastro"])
        self.criar_usuario("DEVOLVE", ["blind_devolucao"])
        s = self.cliente("SEMACESSO", "senha123")
        self.assertEqual(s.get("/blindagens").status_code, 302)
        self.assertEqual(s.get("/blindagens/devolucao").status_code, 302)
        a = self.cliente("CADASTRA", "senha123")
        self.assertEqual(a.get("/blindagens").status_code, 200)
        self.assertEqual(a.get("/blindagens/devolucao").status_code, 302)
        self.assertIn("Cadastro de blindagem", self.texto(a.get("/")))
        d = self.cliente("DEVOLVE", "senha123")
        self.assertEqual(d.get("/blindagens/devolucao").status_code, 200)
        self.assertEqual(d.get("/blindagens/novo").status_code, 302)
        self.assertIn("Solicitar devolução", self.texto(d.get("/")))
        self.criar_usuario("CONFIRMA", ["blind_devolvida"])
        f = self.cliente("CONFIRMA", "senha123")
        self.assertEqual(f.get("/blindagens/devolvidas").status_code, 200)
        self.assertEqual(f.get("/blindagens/devolucao").status_code, 302)
        self.assertIn("Confirmar devolução", self.texto(f.get("/")))


class Presenca(Base):
    def cliente_b(self):
        """Cliente da pessoa B (criada uma única vez: recriar trocaria o id e a sessão deixaria de valer)."""
        con = dbmod.conectar(self.app.config["DATABASE"])
        existe = con.execute("SELECT 1 FROM usuarios WHERE usuario='PRES_B'").fetchone()
        con.close()
        if not existe:
            self.criar_usuario("PRES_B")
        return self.cliente("PRES_B", "senha123")

    def online(self, visto_por, uid):
        """Situação de `uid` vista por `visto_por` (a mesma consulta que a tela faz a cada poucos segundos)."""
        r = visto_por.get("/mensagens/novas?lista=1&depois=0", headers={"X-Passivo": "1"})
        return r.get_json()["presenca"][str(uid)]["online"]

    def bater(self, c, aba):
        return self.post(c, "/sessao/batida", {"aba": aba})

    def sair(self, c, aba):
        return self.post(c, "/sessao/saida", {"aba": aba})

    def test_online_so_com_aba_aberta_e_sai_na_hora(self):
        a_id = self.criar_usuario("PRES_A")
        b_id = self.criar_usuario("PRES_B")
        a = self.cliente("PRES_A", "senha123")
        b = self.cliente_b()
        self.assertFalse(self.online(b, a_id))                 # sem batida: offline
        self.assertEqual(self.bater(a, "ABA1").status_code, 200)
        self.assertTrue(self.online(b, a_id))                  # aparece para os outros
        self.assertFalse(self.online(b, b_id))
        self.assertEqual(self.sair(a, "ABA1").status_code, 204)  # fechou a aba: sai na hora, sem esperar o prazo
        self.assertFalse(self.online(b, a_id))

    def test_duas_abas_so_saem_quando_a_ultima_fecha(self):
        a_id = self.criar_usuario("PRES_C")
        a = self.cliente("PRES_C", "senha123")
        b = self.cliente_b()
        self.bater(a, "X1")
        self.bater(a, "X2")
        self.sair(a, "X1")
        self.assertTrue(self.online(b, a_id))
        self.sair(a, "X2")
        self.assertFalse(self.online(b, a_id))

    def test_logoff_derruba_todas_as_abas(self):
        a_id = self.criar_usuario("PRES_D")
        a = self.cliente("PRES_D", "senha123")
        b = self.cliente_b()
        self.bater(a, "Y1")
        self.bater(a, "Y2")
        self.post(a, "/logout")
        self.assertFalse(self.online(b, a_id))

    def test_queda_sem_aviso_sai_depois_do_prazo(self):
        a_id = self.criar_usuario("PRES_E")
        a = self.cliente("PRES_E", "senha123")
        b = self.cliente_b()
        self.bater(a, "Z1")
        con = dbmod.conectar(self.app.config["DATABASE"])
        con.execute("UPDATE presenca SET visto=? WHERE usuario_id=?", (time.time() - 200, a_id))
        con.commit(); con.close()
        self.assertFalse(self.online(b, a_id))  # não bateu há mais que ONLINE_S: não está mais online

    def test_sem_logoff_por_inatividade(self):
        # a sessão não expira com o tempo parado: só o logoff ou o navegador fechado encerram o acesso
        self.criar_usuario("PRES_F")
        a = self.cliente("PRES_F", "senha123")
        with a.session_transaction() as s:
            s["ultima"] = time.time() - 100000
        self.assertEqual(a.get("/mensagens").status_code, 200)
        self.assertEqual(self.bater(a, "W1").status_code, 200)

    def test_batida_exige_login_e_aba(self):
        anonimo = self.app.test_client()
        anonimo.get("/login")
        self.assertEqual(self.post(anonimo, "/sessao/batida", {"aba": "Q1"}).status_code, 401)
        self.criar_usuario("PRES_G")
        a = self.cliente("PRES_G", "senha123")
        self.assertEqual(self.post(a, "/sessao/batida", {"aba": "!!!"}).status_code, 401)  # aba inválida


if __name__ == "__main__":
    unittest.main()
