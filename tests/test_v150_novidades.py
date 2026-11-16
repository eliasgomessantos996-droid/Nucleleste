"""Versão 1.5.0: caixa só de quem lançou, reabrir caixa e desfazer geral, pesquisa de satisfação (QR Code), comandos da NucleAI,
valores de exame por convênio e menu com telas em botões."""
import json
import re
import sqlite3
import unittest
from datetime import date

from app import desfazer, modulos, movimento, pesquisa
from app import db as dbmod
from app import nucleai_comandos as cmds
from tests.test_chat_blindagens import Base


def _sql(app, sql, params=()):
    con = dbmod.conectar(app.config["DATABASE"])
    try:
        r = con.execute(sql, params).fetchall()
        con.commit()
        return r
    finally:
        con.close()


class CaixaDonoReabrirDesfazer(Base):
    def lanca(self, cliente, usuario):
        _sql(self.app, "INSERT INTO caixa (data, cliente, procedimento, convenio, status, usuario, valor) VALUES (?,?,?,?,?,?,?)",
             (date.today().isoformat(), cliente, "MIBI", "PARTICULAR", "ABERTO", usuario, 100))
        return _sql(self.app, "SELECT id FROM caixa WHERE cliente=?", (cliente,))[0]["id"]

    def test_so_quem_lancou_ve_e_recebe(self):
        self.criar_usuario("DONO_A", ["movimento_caixa", "caixa"])
        self.criar_usuario("DONO_B", ["movimento_caixa", "caixa"])
        ida, idb = self.lanca("PACIENTE DA A", "DONO_A"), self.lanca("PACIENTE DA B", "DONO_B")
        a, b = self.cliente("DONO_A", "senha123"), self.cliente("DONO_B", "senha123")
        self.post(a, "/movimento-caixa/abrir", {"fundo": "0"})
        pa = self.texto(a.get("/movimento-caixa"))
        self.assertIn("PACIENTE DA A", pa)
        self.assertNotIn("PACIENTE DA B", pa)   # o atendimento do colega não aparece
        self.post(a, "/movimento-caixa/receber/%d" % idb, {"valor": "100", "forma": "PIX", "nota_fiscal": "1"})   # tentativa direta
        self.assertEqual(_sql(self.app, "SELECT status FROM caixa WHERE id=?", (idb,))[0]["status"], "ABERTO")
        self.post(a, "/movimento-caixa/receber/%d" % ida, {"valor": "100", "forma": "PIX", "nota_fiscal": "2"})
        self.assertEqual(_sql(self.app, "SELECT status FROM caixa WHERE id=?", (ida,))[0]["status"], "PAGO")
        # a tela Caixa também mostra só os lançamentos da própria pessoa, mesmo pedindo outro usuário na barra de endereço
        self.assertNotIn("PACIENTE DA B", self.texto(a.get("/caixa?usuario=DONO_B")))
        self.post(a, "/caixa/%d" % idb, {"valor": "1", "status": "PAGO"})
        self.assertEqual(_sql(self.app, "SELECT status FROM caixa WHERE id=?", (idb,))[0]["status"], "ABERTO")
        # a gerência vê só os próprios por padrão e todos (para conferir e excluir) quando pede
        adm = self.cliente()
        self.assertNotIn("PACIENTE DA B", self.texto(adm.get("/movimento-caixa")))
        self.assertIn("PACIENTE DA B", self.texto(adm.get("/movimento-caixa?usuarios=todos")))

    def test_reabrir_caixa_e_desfazer_o_fechamento(self):
        self.criar_usuario("FECHA_X", ["movimento_caixa"])
        c = self.cliente("FECHA_X", "senha123")
        self.post(c, "/movimento-caixa/abrir", {"fundo": "5"})
        sid = _sql(self.app, "SELECT id FROM caixa_sessoes WHERE usuario='FECHA_X'")[0]["id"]
        self.post(c, "/movimento-caixa/fechar", {"sessao": sid})
        self.assertEqual(_sql(self.app, "SELECT status FROM caixa_sessoes WHERE id=?", (sid,))[0]["status"], "FECHADO")
        # quem não é da gerência não reabre
        self.post(c, "/movimento-caixa/reabrir/%d" % sid)
        self.assertEqual(_sql(self.app, "SELECT status FROM caixa_sessoes WHERE id=?", (sid,))[0]["status"], "FECHADO")
        adm = self.cliente()
        self.assertIn("Reabrir caixa", self.texto(adm.get("/movimento-caixa")))
        self.post(adm, "/movimento-caixa/reabrir/%d" % sid)
        self.assertEqual(_sql(self.app, "SELECT status FROM caixa_sessoes WHERE id=?", (sid,))[0]["status"], "ABERTO")
        self.assertEqual(_sql(self.app, "SELECT COUNT(*) AS n FROM chat_mensagens WHERE corpo LIKE '%reaberto por ADMIN%'")[0]["n"], 1)
        # o registro de atividades oferece "Desfazer" para o fechamento (volta o caixa para aberto) em qualquer ação
        self.post(c, "/movimento-caixa/fechar", {"sessao": sid})
        reg = _sql(self.app, "SELECT id FROM auditoria WHERE acao='Fechou o caixa do dia' AND desfazer IS NOT NULL AND desfeito_em IS NULL ORDER BY id DESC")[0]["id"]
        self.assertIn("Desfazer", self.texto(adm.get("/registros")))
        self.post(adm, "/registros/%d/desfazer" % reg, {"voltar": "/registros"})
        self.assertEqual(_sql(self.app, "SELECT status FROM caixa_sessoes WHERE id=?", (sid,))[0]["status"], "ABERTO")

    def test_desfazer_geral_cadastro_e_bloqueio_se_mudou(self):
        adm = self.cliente()
        self.post(adm, "/convenios", {"nome": "CONV DESFAZ", "ativo": "1"})
        cid = _sql(self.app, "SELECT id FROM convenios WHERE nome='CONV DESFAZ'")[0]["id"]
        reg = _sql(self.app, "SELECT id FROM auditoria WHERE acao='Salvou convênio' AND desfazer IS NOT NULL ORDER BY id DESC")[0]["id"]
        self.post(adm, "/convenios", {"id": cid, "nome": "CONV DESFAZ", "ativo": "1", "gera_caixa": "1"})   # alteração posterior
        self.post(adm, "/registros/%d/desfazer" % reg, {"voltar": "/registros"})
        self.assertEqual(len(_sql(self.app, "SELECT id FROM convenios WHERE id=?", (cid,))), 1)   # mudou depois: não desfaz
        reg2 = _sql(self.app, "SELECT id FROM auditoria WHERE acao='Salvou convênio' AND desfazer IS NOT NULL ORDER BY id DESC")[0]["id"]
        self.post(adm, "/registros/%d/desfazer" % reg2, {"voltar": "/registros"})   # a última ação volta ao estado anterior
        self.assertEqual(_sql(self.app, "SELECT gera_caixa FROM convenios WHERE id=?", (cid,))[0]["gera_caixa"], 0)

    def test_usuarios_e_registro_nao_entram_no_desfazer(self):
        con = dbmod.conectar(self.app.config["DATABASE"])
        nomes = {t for t, _ in desfazer._tabelas(con)}
        con.close()
        self.assertNotIn("usuarios", nomes)
        self.assertNotIn("auditoria", nomes)
        self.assertIn("caixa_sessoes", nomes)


class PesquisaSatisfacao(Base):
    def test_formulario_publico_respostas_e_indicadores(self):
        adm = self.cliente()
        # editor: no máximo 15 perguntas, e a pergunta em branco é ignorada
        r = self.post(adm, "/qualidade/satisfacao/perguntas", {"pergunta": ["P%d" % i for i in range(16)]}, follow_redirects=True)
        self.assertIn("no máximo 15", self.texto(r))
        self.post(adm, "/qualidade/satisfacao/perguntas", {"pergunta": ["Atendimento?", "", "Limpeza?"]})
        self.assertEqual([p["texto"] for p in pesquisa.perguntas(self._db())], ["Atendimento?", "Limpeza?"])
        self.assertIn("Pesquisa de satisfação", self.texto(adm.get("/qualidade/satisfacao")))
        self.assertEqual(adm.get("/qualidade/satisfacao/qr.svg").mimetype, "image/svg+xml")
        # cliente anônimo, na rede interna, responde
        pub = self.app.test_client()
        pagina = self.texto(pub.get("/pesquisa"))
        self.assertIn("Atendimento?", pagina)
        for opcao in ("Ótimo", "Bom", "Ruim", "Péssimo"):
            self.assertIn(opcao, pagina)
        ids = sorted(set(re.findall(r'name="p(\d+)"', pagina)), key=int)
        pesquisa._ULTIMA.clear()
        faltando = pub.post("/pesquisa", data={"p%s" % ids[0]: "Bom"})
        self.assertIn("Responda todas", self.texto(faltando))
        dados = {"p%s" % ids[0]: "Ótimo", "p%s" % ids[1]: "Ruim", "elogio": "Equipe atenciosa", "sugestao": "Mais cadeiras", "nome": "Maria"}
        r = pub.post("/pesquisa", data=dados)
        self.assertEqual((r.status_code, r.headers["Location"]), (302, "/pesquisa/obrigado"))
        pesquisa._ULTIMA.clear()
        # fora da rede interna não abre
        self.assertEqual(self.app.test_client().get("/pesquisa", environ_base={"REMOTE_ADDR": "8.8.8.8"}).status_code, 403)
        # a gerência vê a resposta, o indicador e o relatório da ONA
        pagina = self.texto(adm.get("/qualidade/satisfacao/respostas"))
        self.assertIn("Maria", pagina)
        self.assertIn("Mais cadeiras", pagina)
        ind = pesquisa.indicadores(self._db(), "2000-01-01", "2999-12-31")
        self.assertEqual((ind["respostas"], ind["geral"]["satisfacao"], ind["geral"]["total"]), (1, 50.0, 2))
        self.assertEqual(adm.get("/qualidade/satisfacao/relatorio.pdf").mimetype, "application/pdf")
        self.assertEqual(adm.get("/qualidade/satisfacao/relatorio.xlsx").status_code, 200)
        # a nota também alimenta o indicador "Satisfação do paciente" e a gerência pode encerrar a pesquisa
        self.assertGreaterEqual(_sql(self.app, "SELECT COUNT(*) AS n FROM cq_pesquisas WHERE criado_por='PESQUISA QR CODE'")[0]["n"], 1)
        self.post(adm, "/qualidade/satisfacao/config", {"endereco": "", "ativa": ""})
        self.assertIn("Pesquisa encerrada", self.texto(pub.get("/pesquisa")))
        self.post(adm, "/qualidade/satisfacao/config", {"endereco": "192.168.0.7:8080", "ativa": "1"})
        self.assertEqual(pesquisa.link_publico(self._db(), 8080), "http://192.168.0.7:8080/pesquisa")

    def test_so_quem_tem_o_modulo_mexe_na_pesquisa(self):
        self.criar_usuario("SEM_QUAL", ["atendimentos"])
        c = self.cliente("SEM_QUAL", "senha123")
        self.assertEqual(c.get("/qualidade/satisfacao").status_code, 302)
        self.assertEqual(c.get("/qualidade/satisfacao/respostas").status_code, 302)

    def _db(self):
        return dbmod.conectar(self.app.config["DATABASE"])


class ComandosNucleai(Base):
    def entrar(self, nome, mods):
        self.criar_usuario(nome, mods)
        c = self.cliente(nome, "senha123")
        self.post(c, "/ajuda/iniciar")
        self.bot = _sql(self.app, "SELECT id FROM usuarios WHERE sistema=3")[0]["id"]
        return c

    def falar(self, c, texto):
        r = self.post(c, "/mensagens/enviar?para=%d" % self.bot, {"corpo": texto}, headers={"Accept": "application/json"})
        return r.get_json()["respostas"]

    def test_catalogo_tem_mais_de_30_comandos_nos_tres_riscos(self):
        self.assertGreaterEqual(len(cmds.COMANDOS), 30)
        riscos = {c.risco for c in cmds.COMANDOS}
        self.assertEqual(riscos, {cmds.BAIXO, cmds.MEDIO, cmds.ALTO})
        self.assertEqual(len({c.chave for c in cmds.COMANDOS}), len(cmds.COMANDOS))

    def test_pede_confirmacao_e_so_faz_com_sim(self):
        c = self.entrar("CMD_REC", ["agenda", "atendimentos"])
        r = self.falar(c, "imprimir a agenda do dia")
        self.assertEqual(r[0]["acao"], "CMD_CONFIRMA_ABRE")
        self.assertIn("Posso", r[0]["corpo"])
        nao = self.falar(c, "não")
        self.assertIn("não vou fazer", nao[0]["corpo"])
        r = self.falar(c, "imprimir a agenda do dia")
        sim = self.falar(c, "sim")
        self.assertTrue(any(m["acao"] == "CMD_ABRIR" and "/ajuda/imprimir" in m["acao_resp"] for m in sim))
        # consulta só de leitura responde direto, sem pedir confirmação
        direto = self.falar(c, "quantos atendimentos hoje?")
        self.assertIn("atendimento", direto[0]["corpo"])
        self.assertFalse(direto[0]["acao"])
        # dúvida de ajuda ("como...") continua sendo ajuda, não comando
        ajuda = self.falar(c, "como imprimir a agenda do dia?")
        self.assertFalse(any((m["acao"] or "").startswith("CMD_") for m in ajuda))

    def test_botao_sim_abre_a_tela_e_nao_repete(self):
        c = self.entrar("CMD_BTN", ["guias"])
        pid = self.falar(c, "imprimir guias de hoje")[0]["chamado_id"]
        r = self.post(c, "/ajuda/comando/%d/responder" % pid, {"resposta": "SIM"})
        self.assertEqual(r.status_code, 302)
        self.assertIn("/guias", r.headers["Location"])
        again = self.post(c, "/ajuda/comando/%d/responder" % pid, {"resposta": "SIM"}, follow_redirects=True)
        self.assertIn("já foi respondido", self.texto(again))

    def test_risco_alto_so_para_a_gerencia(self):
        comum = self.entrar("CMD_COMUM", ["agenda", "backup", "movimento_caixa"])
        self.assertIn("não está liberado", self.falar(comum, "fazer backup agora")[0]["corpo"])
        self.assertIn("não está liberado", self.falar(comum, "reabrir o caixa de CMD_COMUM")[0]["corpo"])
        ger = self.entrar("CMD_GER", ["gerencia", "backup"])
        self.assertEqual(self.falar(ger, "fazer backup agora")[0]["acao"], "CMD_CONFIRMA")
        # não dá para liberar alto risco para outra pessoa pela tela da gerência
        adm = self.cliente()
        self.assertEqual(self.cliente("CMD_COMUM", "senha123").get("/ajuda/comandos").status_code, 302)
        comum = self.cliente("CMD_COMUM", "senha123")   # o login acima (mesmo usuário) encerrou a sessão anterior de `comum`
        form = {"modo_" + c.chave: ("gerencia" if c.risco == "alto" else "todos") for c in cmds.COMANDOS}
        form["usuarios_backup_agora"] = [str(_sql(self.app, "SELECT id FROM usuarios WHERE usuario='CMD_COMUM'")[0]["id"])]
        self.assertEqual(self.post(adm, "/ajuda/comandos", form).status_code, 302)
        self.assertIn("não está liberado", self.falar(comum, "fazer backup agora")[0]["corpo"])

    def test_gerencia_decide_quem_usa_comando_de_medio_risco(self):
        c = self.entrar("CMD_MED", ["contas", "agenda_faltas"])
        self.assertIn("não está liberado", self.falar(c, "quantas contas vencidas?")[0]["corpo"])   # médio: padrão só gerência e escolhidos
        adm = self.cliente()
        uid = _sql(self.app, "SELECT id FROM usuarios WHERE usuario='CMD_MED'")[0]["id"]
        form = {"modo_" + x.chave: ("gerencia" if x.risco == "alto" else "todos" if x.risco == "baixo" else "escolhidos") for x in cmds.COMANDOS}
        form["usuarios_contas_consulta"] = [str(uid)]
        self.post(adm, "/ajuda/comandos", form)
        self.assertIn("Contas a pagar", self.falar(c, "quantas contas vencidas?")[0]["corpo"])
        form["modo_contas_consulta"] = "ninguem"
        self.post(adm, "/ajuda/comandos", form)
        self.assertIn("não está liberado", self.falar(c, "quantas contas vencidas?")[0]["corpo"])

    def test_reabrir_caixa_pelo_chat(self):
        self.criar_usuario("ZECAIXA", ["movimento_caixa"])
        _sql(self.app, "INSERT INTO caixa_sessoes (usuario, data, fundo, status, aberto_em, fechado_em, fechado_por) VALUES "
                       "('ZECAIXA', ?, 0, 'FECHADO', '08:00', '12:00', 'ZECAIXA')", (date.today().isoformat(),))
        ger = self.entrar("CMD_GER2", ["gerencia"])
        r = self.falar(ger, "reabrir o caixa de zecaixa")
        self.assertIn("ZECAIXA", r[0]["corpo"])
        self.falar(ger, "sim")
        self.assertEqual(_sql(self.app, "SELECT status FROM caixa_sessoes WHERE usuario='ZECAIXA'")[0]["status"], "ABERTO")


class ValoresDeExameEMenu(Base):
    def test_valor_de_qualquer_exame_no_convenio_e_exame_novo_aparece(self):
        adm = self.cliente()
        exames = {r["nome"]: r["id"] for r in _sql(self.app, "SELECT id, nome FROM exames")}
        self.post(adm, "/convenios", {"nome": "UNIMED V", "ativo": "1", "valor_%d" % exames["RENAL"]: "350,50", "valor_%d" % exames["TGI"]: "1.200"})
        cid = _sql(self.app, "SELECT id FROM convenios WHERE nome='UNIMED V'")[0]["id"]
        vals = {r["exame_id"]: r["valor"] for r in _sql(self.app, "SELECT exame_id, valor FROM convenio_valores WHERE convenio_id=?", (cid,))}
        self.assertEqual((vals[exames["RENAL"]], vals[exames["TGI"]]), (350.5, 1200.0))
        _sql(self.app, "INSERT INTO exames (nome, ativo, ordem) VALUES ('EXAME NOVO XYZ', 1, 300)")
        self.assertIn("EXAME NOVO XYZ", self.texto(adm.get("/convenios")))   # aparece sozinho em todos os convênios

    def test_telas_viraram_botoes_e_permissao_continua(self):
        self.criar_usuario("BTN_A", ["atendimentos"])
        self.criar_usuario("BTN_B", ["agenda_financeiro"])
        a = self.cliente("BTN_A", "senha123")
        pagina = self.texto(a.get("/atendimentos"))
        self.assertIn("abas-modulo", pagina)
        self.assertIn("Lançar atendimento", pagina)
        self.assertEqual(a.get("/atendimentos/novo").status_code, 200)
        b = self.cliente("BTN_B", "senha123")
        self.assertEqual(b.get("/agenda/financeiro").status_code, 200)
        self.assertNotIn("Relatórios da agenda", self.texto(b.get("/agenda/financeiro")))   # sem o módulo, o botão não aparece
        self.assertEqual(b.get("/agenda/relatorio").status_code, 302)
        # a Qualidade é um módulo só, com um botão para cada ferramenta
        self.criar_usuario("BTN_Q", ["qualidade_gestao"])
        q = self.texto(self.cliente("BTN_Q", "senha123").get("/qualidade"))
        for rotulo in ("Indicadores (KPI)", "Robô do PDCA", "Gráfico de Pareto", "Matriz SWOT", "Organograma", "Pesquisa de satisfação (QR Code)"):
            self.assertIn(rotulo, q)
        self.assertNotIn("Avaliação de fornecedores", q)   # sem o módulo de fornecedores


if __name__ == "__main__":
    unittest.main()
