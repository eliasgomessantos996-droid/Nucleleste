"""NucleAI: conteúdo, repertório, fluxo por lista e por texto, nota, "perguntar de novo", acesso por perfil,
chamado à gerência (botões, confirmação, detalhes com o LEIA-ME), conteúdo editável, configurações, painel e relatórios."""
import json
import re
import unittest
from datetime import datetime, timedelta

from app import ajuda, ajuda_admin, ajuda_base, ajuda_frases as F, ajuda_stats, chat, modulos, presenca
from app import db as dbmod
from app.ajuda_alias import ALIASES
from tests.test_chat_blindagens import Base

TEMAS = ajuda_base.TEMAS
NAO_ENTENDI = re.compile(r"n[ãa]o entendi", re.I)


def titulos(ti, mi, ai):
    m = TEMAS[ti][1][mi]
    return TEMAS[ti][0], m[0], m[1][ai][0]


class Nucleai(Base):
    def setUp(self):
        # funcionários de teste com acesso amplo (menos a gerência): veem todos os temas e quase todos os módulos
        amplo = [k for k in modulos.CHAVES if k != "gerencia"]
        self.func = self.criar_usuario("NA_FUNC", amplo)
        self.ger = self.criar_usuario("NA_GER", ["gerencia"])
        self.outro = self.criar_usuario("NA_OUTRO", amplo)
        self.con = dbmod.conectar(self.app.config["DATABASE"])
        self.admin = self.con.execute("SELECT id FROM usuarios WHERE usuario='ADMIN'").fetchone()["id"]
        self.bot = ajuda.bot_id(self.con)
        self.sistema = self.con.execute("SELECT id FROM usuarios WHERE sistema=1").fetchone()["id"]
        # banco de teste isolado: cada teste começa sem mensagens, conversas, registros nem configuração da NucleAI
        for tabela in ("chat_mensagens", "ajuda_sessoes", "ajuda_registros", "ajuda_chamados", "ajuda_nao_entendidas",
                       "ajuda_conteudo", "presenca"):
            self.con.execute("DELETE FROM %s" % tabela)
        self.con.execute("DELETE FROM config WHERE chave LIKE 'nucleai_%'")
        self.con.commit()
        ajuda.invalidar()

    def tearDown(self):
        ajuda.invalidar()
        self.con.close()

    # ---------------------------------------------------------------- utilitários
    def fala(self, texto, uid=None):
        r = ajuda.responder(self.con, uid or self.func, texto)
        self.con.commit()
        return r

    def textos(self, r):
        return [m["corpo"] for m in r["mensagens"]]

    def conversa(self, uid=None, com=None):
        return [m["corpo"] for m in chat.conversa(self.con, uid or self.func, com or self.bot)]

    def sessao(self, uid=None):
        return ajuda.sessao(self.con, uid or self.func)

    def ate_a_area(self, ti, mi, ai, uid=None):
        uid = uid or self.func
        ajuda.iniciar(self.con, uid)
        self.fala(str(ti + 1), uid)
        self.fala(str(mi + 1), uid)
        return self.fala(str(ai + 1), uid)

    def indices(self, modulo, area=None):
        for ti, (_t, mods) in enumerate(TEMAS):
            for mi, (m, areas) in enumerate(mods):
                if m == modulo:
                    for ai, (a, _x) in enumerate(areas):
                        if area is None or a == area:
                            return ti, mi, ai
        raise AssertionError("área não encontrada: %s %s" % (modulo, area))

    def ultimo_registro(self):
        return self.con.execute("SELECT * FROM ajuda_registros ORDER BY id DESC LIMIT 1").fetchone()

    def perfil(self, nome, mods, admin=0):
        return self.criar_usuario(nome, mods, admin=admin)

    def mm0(self, uid=None):
        """Lista de módulos do primeiro tema como a pessoa vê (o módulo NucleAI é só da administração)."""
        return ajuda.menu_modulos(0, ajuda.modulos_visiveis(self.con, uid or self.func, 0))

    def entende(self, texto, area, uid=None):
        """A busca leva à área esperada: direto (resposta) ou entre as possibilidades oferecidas."""
        uid = uid or self.func
        ajuda.iniciar(self.con, uid)
        self.fala(texto, uid)
        s = self.sessao(uid)
        if s["estado"] == ajuda.SATISFEITO:
            self.assertEqual(self.ultimo_registro()["area"], area, texto)
        else:
            self.assertEqual(s["estado"], ajuda.ESCOLHA, texto)
            B = ajuda.base(self.con)
            areas = [B.temas[ti][1][mi][1][ai][0] for ti, mi, ai in json.loads(s["candidatos"])]
            self.assertIn(area, areas, texto)

    # ================================================================ conteúdo
    def test_todo_o_menu_tem_ajuda(self):
        nomes = {t[0]: {m[0] for m in t[1]} for t in TEMAS}
        total = 0
        for grupo, _mod, rotulo, _ep in modulos.telas():
            tema = grupo or "Início e mensagens"
            self.assertIn(tema, nomes, "tema sem ajuda: %s" % tema)
            total += 1
            self.assertIn(rotulo, nomes[tema], "tela sem ajuda: %s › %s" % (tema, rotulo))
        self.assertEqual(total, 102)   # menu + botões: inclui também Escrituração do Estoque, Medcloud, Pendências Medcloud e Gasto de tokens (NucleAI)

    def test_conteudo_bem_formado(self):
        for ti, (tema, mods) in enumerate(TEMAS):
            self.assertTrue(tema and mods)
            self.assertEqual(len({m[0] for m in mods}), len(mods), "módulo repetido em %s" % tema)
            self.assertLess(len(ajuda.menu_modulos(ti)), 1900)
            for mi, (mod, areas) in enumerate(mods):
                self.assertTrue(areas, "módulo sem áreas: %s" % mod)
                self.assertEqual(len({a[0] for a in areas}), len(areas), "área repetida em %s" % mod)
                self.assertLess(len(ajuda.menu_areas(ti, mi)), 1900)
                for ai, (area, texto) in enumerate(areas):
                    self.assertGreater(len(texto.strip()), 40, "instrução curta: %s › %s" % (mod, area))
                    self.assertLess(len(ajuda.instrucoes(ti, mi, ai)), chat.MAX_CORPO, "instrução longa: %s › %s" % (mod, area))
                    for ruim in ("TODO", "lorem", "{{", "}}"):
                        self.assertNotIn(ruim, texto, "%s › %s" % (mod, area))
        self.assertGreaterEqual(sum(len(a) for _t, ms in TEMAS for _m, a in ms), 100)

    def test_todo_modulo_da_ajuda_tem_regra_de_acesso(self):
        for tema, mods in TEMAS:
            for mod, _areas in mods:
                self.assertIn((tema, mod), ajuda.ACESSO, "sem regra de acesso: %s › %s" % (tema, mod))

    def test_frases_de_exemplo_apontam_para_areas_que_existem(self):
        existentes = {(m, a) for _t, ms in TEMAS for m, areas in ms for a, _x in areas}
        for chave, frases in ALIASES.items():
            self.assertIn(chave, existentes, "frase de exemplo sem área: %s" % (chave,))
            self.assertTrue(frases)

    # ================================================================ repertório de frases
    def test_repertorio_com_20_de_cada(self):
        self.assertEqual(len(F.SAUDACOES), 20)
        self.assertEqual(len(F.NAO_ENTENDI), 20)
        self.assertEqual(len(F.AGRADECIMENTOS), 20)
        for lista in (F.SAUDACOES, F.NAO_ENTENDI, F.AGRADECIMENTOS, F.NAO_ENTENDI_DUVIDA, F.ENTENDI, F.DESPEDIDAS):
            self.assertEqual(len(set(lista)), len(lista), "frase repetida")

    def test_saudacoes(self):
        for s in F.SAUDACOES:
            self.assertIn("{nome}", s)
            self.assertIn("NucleAI", s)
            texto = ajuda.saudacao("Beatriz Maria Fernanda de Oliveira")
            self.assertLess(len(s.format(nome="Beatriz Maria Fernanda de Oliveira")), 600)
        self.assertLess(len(texto), 1900)

    def test_nao_entendi_sempre_diz_que_nao_entendeu(self):
        for s in F.NAO_ENTENDI + F.NAO_ENTENDI_DUVIDA:
            self.assertRegex(s, NAO_ENTENDI, s)
        # a dúvida escrita não entendida convida a reformular ou seguir a lista
        for s in F.NAO_ENTENDI_DUVIDA:
            self.assertRegex(s.lower(), r"lista")

    def test_agradecimentos_sempre_agradecem(self):
        for s in F.AGRADECIMENTOS:
            self.assertIn("obrigada", s.lower(), s)
            self.assertIn("{nome}", s)
            self.assertLess(len(s.format(nome="Beatriz")), 400)

    def test_o_sorteio_usa_todo_o_repertorio(self):
        vistas = {F.escolher(F.SAUDACOES, nome="X") for _ in range(2000)}
        self.assertEqual(len(vistas), 20)

    # ================================================================ interpretação das respostas
    def test_numero(self):
        for bruto, esperado in [("2", 2), (" 2 ", 2), ("2.", 2), ("2)", 2), ("2 -", 2), ("10", 10), ("0", 0), ("007", None)]:
            self.assertEqual(ajuda._numero(bruto), esperado, bruto)
        for ruim in ["", "  ", "abc", "1 2", "1.5", "-1", "um", "1a", "dois", "123", None]:
            self.assertIsNone(ajuda._numero(ruim), repr(ruim))

    # ================================================================ saudação e fluxo pela lista
    def test_saudacao_com_a_lista_de_temas(self):
        ajuda.iniciar(self.con, self.func)
        msgs = self.conversa()
        self.assertEqual(len(msgs), 1)
        nome = ajuda._primeiro_nome(self.con, self.func)
        self.assertIn(nome, msgs[0])
        self.assertIn("NucleAI", msgs[0])
        self.assertIn("escreva a sua dúvida", msgs[0])     # a pessoa pode escrever em vez de usar a lista
        for i, (tema, _m) in enumerate(TEMAS, 1):
            self.assertIn("%d - %s" % (i, tema), msgs[0])
        self.assertEqual(self.sessao()["estado"], ajuda.TEMA)

    def test_fluxo_de_todas_as_areas_entrega_a_instrucao_certa(self):
        combinacoes = 0
        for ti, (_t, mods) in enumerate(TEMAS):
            for mi, (_m, areas) in enumerate(mods):
                for ai in range(len(areas)):
                    ajuda.iniciar(self.con, self.admin)     # o administrador vê tudo: numeração da base completa
                    self.assertEqual(self.textos(self.fala(str(ti + 1), self.admin)), [ajuda.menu_modulos(ti)])
                    self.assertEqual(self.textos(self.fala(str(mi + 1), self.admin)), [ajuda.menu_areas(ti, mi)])
                    self.assertEqual(self.textos(self.fala(str(ai + 1), self.admin)), [ajuda.instrucoes(ti, mi, ai), ajuda.PERGUNTA_SATISFEITO])
                    self.assertEqual(self.sessao(self.admin)["estado"], ajuda.SATISFEITO)
                    combinacoes += 1
        self.assertEqual(combinacoes, sum(len(a) for _t, ms in TEMAS for _m, a in ms))

    def test_resposta_invalida_em_cada_etapa_repete_a_lista(self):
        ajuda.iniciar(self.con, self.func)
        etapas = [(ajuda.menu_temas(), "1"), (self.mm0(), "1"), (ajuda.menu_areas(0, 0), "1"),
                  (ajuda.PERGUNTA_SATISFEITO, "3"), (ajuda.MENU_POS, None)]
        for menu, avanca in etapas:
            estado_antes = self.sessao()["estado"]
            # números fora da lista, símbolos e textos sem sentido: nunca avançam
            for ruim in ["99", "42", "-1", "1 2", "1.5", "?????", "...", "😀", "zzzzzz", "qwxyz"]:
                r = self.fala(ruim)
                t = self.textos(r)
                self.assertEqual(len(t), 2, (estado_antes, ruim))
                self.assertRegex(t[0], NAO_ENTENDI, (estado_antes, ruim, t[0]))
                self.assertEqual(t[1], menu, (estado_antes, ruim))
                self.assertEqual(self.sessao()["estado"], estado_antes)
            if avanca:
                self.fala(avanca)
        ajuda.iniciar(self.con, self.func)
        self.assertRegex(self.textos(self.fala(str(len(TEMAS) + 1)))[0], NAO_ENTENDI)
        self.fala("1")
        self.assertRegex(self.textos(self.fala(str(len(TEMAS[0][1]) + 1)))[0], NAO_ENTENDI)

    def test_formatos_de_resposta_aceitos(self):
        for formato in ["1", " 1 ", "1.", "1)", "1 -"]:
            ajuda.iniciar(self.con, self.func)
            self.assertEqual(self.textos(self.fala(formato)), [self.mm0()], formato)

    def test_zero_volta_uma_etapa_ou_encerra(self):
        ajuda.iniciar(self.con, self.func)
        self.fala("2")
        self.fala("1")
        self.assertEqual(self.sessao()["estado"], ajuda.AREA)
        self.assertEqual(self.textos(self.fala("0")), [ajuda.menu_modulos(1)])
        self.assertEqual(self.textos(self.fala("0")), [ajuda.menu_temas()])
        r = self.fala("0")
        self.assertTrue(r["encerrado"])
        self.assertIn(self.textos(r)[0].replace(ajuda._primeiro_nome(self.con, self.func), "{nome}"), F.DESPEDIDAS)

    # ================================================================ "consegui te ajudar?", nota e registros
    def test_pergunta_de_satisfacao_tem_tres_opcoes(self):
        self.assertIn("1 - Sim, deu certo!", ajuda.PERGUNTA_SATISFEITO)
        self.assertIn("2 - Sim, ajudou, mas quero perguntar de novo", ajuda.PERGUNTA_SATISFEITO)
        self.assertIn("3 - Não, ainda preciso de ajuda", ajuda.PERGUNTA_SATISFEITO)

    def test_sim_pede_nota_agradece_encerra_e_apaga(self):
        ajuda.iniciar(self.con, self.func)
        self.ate_a_area(0, 0, 0)
        self.assertEqual(len(self.conversa()), 5)
        self.assertEqual(self.textos(self.fala("1")), [F.PEDIDO_NOTA])
        self.assertEqual(self.sessao()["estado"], ajuda.NOTA)
        r = self.fala("5")
        self.assertTrue(r["encerrado"])
        corpo = self.textos(r)[0]
        nome = ajuda._primeiro_nome(self.con, self.func)
        self.assertTrue(any(corpo.startswith(a.format(nome=nome)) for a in F.AGRADECIMENTOS), corpo)
        self.assertIn(F.SUFIXO_APAGAR, corpo)
        self.assertEqual(self.conversa(), [corpo])   # o resto do histórico foi apagado
        self.assertEqual(self.sessao()["estado"], ajuda.ENCERRADO)
        # a essência fica registrada
        reg = self.ultimo_registro()
        self.assertEqual((reg["resultado"], reg["nota"], reg["origem"], reg["usuario"]), ("RESOLVEU", 5, "LISTA", "NA_FUNC"))
        self.assertEqual((reg["tema"], reg["modulo"], reg["area"]), titulos(0, 0, 0))
        # a despedida some e a conversa deixa de existir; o registro continua
        ajuda.limpar(self.con, datetime.now() + timedelta(seconds=ajuda.DESPEDIDA_S + 5))
        self.assertEqual(self.conversa(), [])
        self.assertIsNone(self.sessao())
        self.assertNotIn("NucleAI", [c["nome"] for c in chat.contatos(self.con, self.func)])
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM ajuda_registros").fetchone()[0], 1)

    def test_nota_pode_ser_pulada_e_so_aceita_de_0_a_5(self):
        self.ate_a_area(0, 0, 0)
        self.fala("1")
        for ruim in ["6", "9", "abc", "-1", "1.5"]:
            t = self.textos(self.fala(ruim))
            self.assertRegex(t[0], NAO_ENTENDI)
            self.assertEqual(t[1], F.PEDIDO_NOTA)
            self.assertEqual(self.sessao()["estado"], ajuda.NOTA)
        r = self.fala("0")
        self.assertTrue(r["encerrado"])
        self.assertIsNone(self.ultimo_registro()["nota"])
        self.assertEqual(self.ultimo_registro()["resultado"], "RESOLVEU")

    def test_ajudou_mas_quero_perguntar_de_novo_nao_encerra(self):
        self.ate_a_area(0, 0, 0)
        self.assertEqual(self.textos(self.fala("2")), [F.PEDIDO_NOTA])
        r = self.fala("4")
        self.assertFalse(r["encerrado"])
        self.assertIn("Vamos lá de novo", self.textos(r)[0])
        self.assertIn(ajuda.menu_temas(), self.textos(r)[0])
        self.assertEqual(self.sessao()["estado"], ajuda.TEMA)
        reg = self.ultimo_registro()
        self.assertEqual((reg["resultado"], reg["nota"]), ("RESOLVEU_E_NOVA", 4))
        # a conversa continua e uma segunda consulta vira outro registro
        self.fala("2")
        self.fala("1")
        self.fala("1")
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM ajuda_registros").fetchone()[0], 2)
        self.assertEqual(self.sessao()["estado"], ajuda.SATISFEITO)

    def test_sim_e_nao_escritos_em_palavras(self):
        for texto, esperado in [("sim", ajuda.NOTA), ("Sim, resolveu!", ajuda.NOTA), ("não", ajuda.POS), ("nao ajudou", ajuda.POS),
                                ("sim mas quero perguntar de novo", ajuda.NOTA)]:
            self.ate_a_area(0, 0, 0)
            self.fala(texto)
            self.assertEqual(self.sessao()["estado"], esperado, texto)
        self.ate_a_area(0, 0, 0)
        self.fala("sim mas quero perguntar de novo")
        self.assertEqual(self.sessao()["seguinte"], "NOVA")

    def test_resposta_invalida_na_pergunta_de_satisfacao(self):
        self.ate_a_area(0, 0, 0)
        t = self.textos(self.fala("talvez"))
        self.assertRegex(t[0], NAO_ENTENDI)
        self.assertEqual(t[1], ajuda.PERGUNTA_SATISFEITO)

    def test_depois_de_encerrar_a_nucleai_avisa_que_acabou(self):
        self.ate_a_area(0, 0, 0)
        self.fala("1")
        self.fala("0")
        r = self.fala("1")
        self.assertTrue(r["encerrado"])
        self.assertIn("encerrada", self.textos(r)[0])

    def test_nao_ajudou_oferece_cinco_opcoes(self):
        self.ate_a_area(2, 1, 0)
        self.assertEqual(self.textos(self.fala("3")), [ajuda.MENU_POS])
        self.assertEqual(self.ultimo_registro()["resultado"], "NAO_RESOLVEU")
        for opcao in ["Ver outra área deste módulo", "Ver outro módulo deste tema", "Ver outro tema", "Chamar a gerência", "Encerrar o chat"]:
            self.assertIn(opcao, ajuda.MENU_POS)
        self.assertEqual(self.textos(self.fala("1")), [ajuda.menu_areas(2, 1)])
        self.fala("1")
        self.fala("3")
        self.assertEqual(self.textos(self.fala("2")), [ajuda.menu_modulos(2)])
        self.fala("1")
        self.fala("1")
        self.fala("3")
        self.assertEqual(self.textos(self.fala("3")), [ajuda.menu_temas()])
        self.assertEqual(self.textos(self.fala("1")), [self.mm0()])

    def test_encerrar_pelo_menu_pos(self):
        self.ate_a_area(0, 0, 0)
        self.fala("3")
        r = self.fala("5")
        self.assertTrue(r["encerrado"])
        self.assertEqual(len(self.conversa()), 1)
        self.assertEqual(self.ultimo_registro()["resultado"], "NAO_RESOLVEU")

    def test_consulta_sem_resposta_e_abandono_ficam_registradas(self):
        self.ate_a_area(0, 0, 0)
        # nova consulta sem ter respondido a pergunta: a anterior fica "sem resposta" e a nova, "em andamento"
        self.ate_a_area(0, 1, 0)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM ajuda_registros WHERE resultado='SEM_AVALIACAO'").fetchone()[0], 1)
        self.con.execute("UPDATE ajuda_sessoes SET atualizado_em=? WHERE usuario_id=?",
                         ((datetime.now() - timedelta(hours=ajuda.SESSAO_MAX_H + 1)).strftime("%Y-%m-%d %H:%M:%S"), self.func))
        self.con.commit()
        ajuda.limpar(self.con)
        self.assertIsNone(self.sessao())
        self.assertEqual(self.conversa(), [])
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM ajuda_registros WHERE resultado='ABANDONOU'").fetchone()[0], 1)

    # ================================================================ dúvida escrita (busca por texto)
    def assunto_do_registro(self):
        r = self.ultimo_registro()
        return r["modulo"], r["area"], r["origem"], r["duvida"]

    def test_duvida_escrita_clara_responde_direto(self):
        ajuda.iniciar(self.con, self.func)
        r = self.fala("como faço para fechar o caixa no fim do dia?")
        t = self.textos(r)
        self.assertEqual(len(t), 3)
        self.assertTrue(any(t[0].startswith(a) for a in F.ENTENDI), t[0])
        self.assertIn("Movimento de caixa › Fechar o caixa e assinar o relatório", t[0])
        ti, mi, ai = self.indices("Movimento de caixa", "Fechar o caixa e assinar o relatório")
        self.assertEqual(t[1], ajuda.instrucoes(ti, mi, ai))
        self.assertEqual(t[2], ajuda.PERGUNTA_SATISFEITO)
        self.assertEqual(self.sessao()["estado"], ajuda.SATISFEITO)
        self.assertEqual(self.assunto_do_registro(), ("Movimento de caixa", "Fechar o caixa e assinar o relatório", "TEXTO",
                                                      "como faço para fechar o caixa no fim do dia?"))

    def test_duvida_escrita_funciona_em_qualquer_lista(self):
        for passos in ([], ["1"], ["2", "1"]):
            ajuda.iniciar(self.con, self.func)
            for p in passos:
                self.fala(p)
            r = self.fala("esqueci minha senha")
            self.assertEqual(len(self.textos(r)), 3, passos)
            self.assertEqual(self.ultimo_registro()["area"], "Trocar a sua senha")

    def test_duvida_escrita_com_erros_de_digitacao_e_giria(self):
        casos = [("fexar o caixa", "Fechar o caixa e assinar o relatório"), ("cadastar cliente novo", "Cadastrar um novo cliente"),
                 ("nao consigo fechar o cx", "Fechar o caixa e assinar o relatório"),
                 ("paciente faltou e quero chamar no zap", "Chamar quem faltou"),
                 ("o telefone do cliente nao aceita", "Telefone no padrão")]
        for texto, area in casos:
            self.entende(texto, area)

    def test_duvida_vaga_mostra_possibilidades_para_escolher(self):
        ajuda.iniciar(self.con, self.func)
        t = self.textos(self.fala("exportar para excel"))
        self.assertEqual(len(t), 1)
        self.assertIn("Encontrei estas possibilidades", t[0])
        self.assertIn("Nenhuma dessas", t[0])
        self.assertEqual(self.sessao()["estado"], ajuda.ESCOLHA)
        cands = json.loads(self.sessao()["candidatos"])
        self.assertTrue(2 <= len(cands) <= 3)
        # número inválido volta a mostrar as possibilidades
        t = self.textos(self.fala("9"))
        self.assertRegex(t[0], NAO_ENTENDI)
        self.assertIn("Encontrei estas possibilidades", t[1])
        # escolher uma entrega a instrução dela
        r = self.fala("1")
        ti, mi, ai = cands[0]
        self.assertEqual(self.textos(r), [ajuda.instrucoes(ti, mi, ai), ajuda.PERGUNTA_SATISFEITO])
        self.assertEqual(self.ultimo_registro()["origem"], "TEXTO")

    def test_nenhuma_das_possibilidades_volta_para_a_lista(self):
        ajuda.iniciar(self.con, self.func)
        self.fala("exportar para excel")
        n = len(json.loads(self.sessao()["candidatos"]))
        t = self.textos(self.fala(str(n + 1)))
        self.assertIn(ajuda.menu_temas(), t[0])
        self.assertEqual(self.sessao()["estado"], ajuda.TEMA)

    def test_nova_duvida_escrita_dentro_das_possibilidades_faz_nova_busca(self):
        ajuda.iniciar(self.con, self.func)
        self.fala("exportar para excel")
        self.assertEqual(self.sessao()["estado"], ajuda.ESCOLHA)
        self.fala("na verdade quero saber como fechar o caixa no fim do dia")
        self.assertEqual(self.sessao()["estado"], ajuda.SATISFEITO)
        self.assertEqual(self.ultimo_registro()["area"], "Fechar o caixa e assinar o relatório")

    def test_duvida_sem_sentido_nao_entende_pede_reformular_e_volta_a_lista(self):
        for passos, menu in (([], ajuda.menu_temas()), (["1"], self.mm0()), (["1", "1"], ajuda.menu_areas(0, 0))):
            ajuda.iniciar(self.con, self.func)
            for p in passos:
                self.fala(p)
            antes = dict(self.sessao())
            for texto in ["qual a capital da frança", "quero comprar uma pizza", "asdfgh jklç", "vai chover amanhã?"]:
                t = self.textos(self.fala(texto))
                self.assertEqual(len(t), 2, texto)
                self.assertIn(t[0], F.NAO_ENTENDI_DUVIDA, texto)
                self.assertRegex(t[0], NAO_ENTENDI)
                self.assertEqual(t[1], menu)
            self.assertEqual(self.sessao()["estado"], antes["estado"])
        # o que não foi entendido fica guardado, para a administração melhorar a ajuda
        textos = {r["texto"] for r in self.con.execute("SELECT texto FROM ajuda_nao_entendidas")}
        self.assertIn("quero comprar uma pizza", textos)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM ajuda_registros").fetchone()[0], 0)   # sem área, sem consulta

    def test_duvida_escrita_respeita_o_acesso_do_perfil(self):
        uid = self.perfil("NA_SO_AGENDA", ["agenda"])
        ajuda.iniciar(self.con, uid)
        for pergunta in ["como quitar uma conta a pagar", "registrar uma fatura do convênio", "backup do banco", "corrigir batida de ponto"]:
            r = self.fala(pergunta, uid)
            tudo = "\n".join(self.textos(r))
            for proibido in ("Contas a pagar", "Faturamento", "Backup", "Painel de saldos"):
                self.assertNotIn(proibido, tudo, pergunta)
            self.assertIsNone(self.con.execute("SELECT 1 FROM ajuda_registros WHERE usuario_id=?", (uid,)).fetchone())
            self.con.execute("UPDATE ajuda_sessoes SET estado='TEMA', candidatos=NULL WHERE usuario_id=?", (uid,))
            self.con.commit()
        # mas o que é da agenda ela encontra
        self.fala("como bloquear um dia na agenda", uid)
        self.assertEqual(self.con.execute("SELECT area FROM ajuda_registros WHERE usuario_id=?", (uid,)).fetchone()["area"], "Criar a agenda do dia")

    def test_nova_duvida_escrita_na_pergunta_de_satisfacao(self):
        self.ate_a_area(0, 0, 0)
        self.fala("como fechar o caixa")
        self.assertEqual(self.ultimo_registro()["area"], "Fechar o caixa e assinar o relatório")
        # a consulta anterior não respondida fica "sem resposta"
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM ajuda_registros WHERE resultado='SEM_AVALIACAO'").fetchone()[0], 1)

    def test_texto_de_menu_nao_vira_busca_com_numeros_e_simbolos(self):
        ajuda.iniciar(self.con, self.func)
        for texto in ["1 2", "3.5", "99", "###", "   ", "\n", "123456"]:
            if not texto.strip():
                continue
            t = self.textos(self.fala(texto))
            self.assertRegex(t[0], NAO_ENTENDI, texto)
            self.assertEqual(self.sessao()["estado"], ajuda.TEMA)

    # ================================================================ acesso por perfil
    def temas_do(self, uid):
        T = ajuda.base(self.con).temas
        return [T[i][0] for i in ajuda.temas_visiveis(self.con, uid)]

    def modulos_do(self, uid, tema):
        T = ajuda.base(self.con).temas
        ti = [t[0] for t in T].index(tema)
        return [T[ti][1][i][0] for i in ajuda.modulos_visiveis(self.con, uid, ti)]

    def test_sem_acesso_ao_financeiro_o_tema_nao_aparece(self):
        uid = self.perfil("NA_RECEP", ["atendimentos", "clientes", "agenda"])
        temas = self.temas_do(uid)
        for oculto in ("Financeiro", "Banco de Horas", "Controle de Blindagens", "Qualidade"):
            self.assertNotIn(oculto, temas)
        for visivel in ("Lançamentos", "Agenda", "Cadastros"):
            self.assertIn(visivel, temas)
        ajuda.iniciar(self.con, uid)
        saudacao = self.conversa(uid)[0]
        self.assertNotIn("Financeiro", saudacao)
        for i, tema in enumerate(temas, 1):
            self.assertIn("%d - %s" % (i, tema), saudacao)

    def test_modulos_so_os_liberados(self):
        uid = self.perfil("NA_PARCIAL", ["atendimentos", "agenda", "contas"])
        self.assertEqual(self.modulos_do(uid, "Lançamentos"), ["Lançar atendimento", "Atendimentos", "Pendências Medcloud"])
        self.assertEqual(self.modulos_do(uid, "Agenda"), ["Agenda de exames", "Reservas do convênio"])
        self.assertEqual(self.modulos_do(uid, "Financeiro"), ["Contas a pagar"])
        self.assertEqual(self.modulos_do(uid, "Início e mensagens"), ["Início", "Mensagens", "Sugestão", "Correção de bug", "Meus favoritos", "Lembretes"])   # sem Dashboard e sem NucleAI

    def test_numeracao_segue_a_lista_mostrada(self):
        uid = self.perfil("NA_NUMERACAO", ["contas"])
        self.assertEqual(self.temas_do(uid), ["Início e mensagens", "Financeiro", "Configuração"])
        ajuda.iniciar(self.con, uid)
        t = self.textos(self.fala("2", uid))
        self.assertIn("Financeiro", t[0])
        self.assertIn("1 - Contas a pagar", t[0])
        self.assertNotIn("Faturamento", t[0])
        self.assertIn("Contas a pagar", self.textos(self.fala("1", uid))[0])
        self.assertIn("Cadastrar uma conta", self.textos(self.fala("1", uid))[0])

    def test_numero_de_item_inexistente_para_o_perfil_nao_e_entendido(self):
        uid = self.perfil("NA_LIMITADO", ["contas"])
        ajuda.iniciar(self.con, uid)
        t = self.textos(self.fala("4", uid))
        self.assertRegex(t[0], NAO_ENTENDI)
        self.assertEqual(t[1], ajuda.menu_temas(ajuda.temas_visiveis(self.con, uid)))
        self.fala("2", uid)
        self.assertRegex(self.textos(self.fala("2", uid))[0], NAO_ENTENDI)

    def test_perfil_sem_modulos_ve_so_o_que_e_livre(self):
        uid = self.perfil("NA_VAZIO", [])
        self.assertEqual(self.temas_do(uid), ["Início e mensagens", "Configuração"])
        self.assertEqual(self.modulos_do(uid, "Configuração"), ["Minha conta"])

    def test_nucleai_e_usuarios_e_perfis_so_para_administrador(self):
        comum = self.perfil("NA_COMUM2", [m for m in modulos.CHAVES if m != "usuarios_gerir"])
        self.assertNotIn("Usuários e perfis", self.modulos_do(comum, "Configuração"))
        self.assertNotIn("NucleAI", self.modulos_do(comum, "Início e mensagens"))
        self.assertIn("Usuários e perfis", self.modulos_do(self.admin, "Configuração"))
        self.assertIn("NucleAI", self.modulos_do(self.admin, "Início e mensagens"))
        self.assertIn("Saúde do sistema", self.modulos_do(comum, "Configuração"))
        sem = self.perfil("NA_SEM_GER", [k for k in modulos.CHAVES if k != "gerencia"])
        self.assertNotIn("Saúde do sistema", self.modulos_do(sem, "Configuração"))

    def test_banco_de_horas_respeita_consulta_e_portal(self):
        consulta = self.perfil("NA_BH1", ["bh_consulta"])
        self.assertEqual(self.modulos_do(consulta, "Banco de Horas"),
                         ["Painel de saldos", "Funcionários do ponto", "Importar ponto", "Escala mensal", "Histórico do ponto"])
        self.assertEqual(self.modulos_do(self.perfil("NA_BH2", ["bh_portal"]), "Banco de Horas"), ["Minha área"])
        self.assertEqual(self.modulos_do(self.perfil("NA_BH3", ["bh_dp"]), "Banco de Horas"), ["Departamento Pessoal"])

    def test_administrador_ve_tudo(self):
        self.assertEqual(len(ajuda.temas_visiveis(self.con, self.admin)), len(TEMAS))
        for ti, (tema, mods) in enumerate(TEMAS):
            self.assertEqual(len(ajuda.modulos_visiveis(self.con, self.admin, ti)), len(mods), tema)

    def test_o_que_o_perfil_nao_acessa_nao_aparece_na_conversa_inteira(self):
        uid = self.perfil("NA_ISOLADO", ["agenda"])
        ajuda.iniciar(self.con, uid)
        self.fala("2", uid)
        self.fala("1", uid)
        self.fala("1", uid)
        self.fala("3", uid)
        tudo = "\n".join(self.conversa(uid))
        for proibido in ("Faturamento", "Contas a pagar", "Banco de Horas", "Controle de Blindagens", "Relatório ONA", "Backup"):
            self.assertNotIn(proibido, tudo)

    def test_permissao_alterada_vale_na_proxima_lista(self):
        uid = self.perfil("NA_MUDOU", ["agenda"])
        self.assertNotIn("Financeiro", self.temas_do(uid))
        self.con.execute("UPDATE usuarios SET modulos=? WHERE id=?", ('["agenda","contas"]', uid))
        self.con.commit()
        self.assertIn("Financeiro", self.temas_do(uid))

    # ================================================================ chamar a gerência
    def chamar(self, uid=None, ti=1, mi=0, ai=1):
        self.ate_a_area(ti, mi, ai, uid)
        self.fala("3", uid)
        return self.fala("4", uid)

    def mensagens_da_nucleai_para(self, uid):
        return [dict(m) for m in self.con.execute(
            "SELECT * FROM chat_mensagens WHERE de_id=? AND para_id=? ORDER BY id", (self.bot, uid))]

    def test_chamar_a_gerencia_avisa_pela_nucleai_com_botao(self):
        presenca.bater(self.con, self.ger, "t1")
        r = self.chamar()
        t = self.textos(r)
        self.assertIn("Avisei", t[0])
        self.assertEqual(t[1], ajuda.MENU_POS)
        nome = ajuda._primeiro_nome(self.con, self.func)
        ti, mi, ai = 1, 0, 1
        onde = "%s › %s › %s" % titulos(ti, mi, ai)
        recebidas = [m for m in self.mensagens_da_nucleai_para(self.ger) if m["acao"] == "CHAMADO_FALAR"]
        self.assertEqual(len(recebidas), 1)
        m = recebidas[0]
        for trecho in ("NucleAI enviou por %s" % nome, "Olá, gestão!", "Infelizmente não consegui sanar as dúvidas", onde, "Aguardamos"):
            self.assertIn(trecho, m["corpo"])
        ch = self.con.execute("SELECT * FROM ajuda_chamados").fetchone()
        self.assertEqual(m["chamado_id"], ch["id"])
        self.assertEqual((ch["status"], ch["usuario"], ch["gerencia_online"], ch["confirmou"]), ("ABERTO", "NA_FUNC", 1, None))
        self.assertEqual(self.ultimo_registro()["chamou_gerencia"], 1)
        # o administrador também é gerência; funcionários e a própria pessoa não recebem
        self.assertEqual(len([x for x in self.mensagens_da_nucleai_para(self.admin) if x["acao"] == "CHAMADO_FALAR"]), 1)
        self.assertEqual([x for x in self.mensagens_da_nucleai_para(self.outro) if x["acao"]], [])
        self.assertEqual([x for x in self.mensagens_da_nucleai_para(self.func) if x["acao"]], [])
        # a gerência passa a ver o contato da NucleAI, com a mensagem
        self.assertIn("NucleAI", [c["nome"] for c in chat.contatos(self.con, self.ger)])
        self.assertEqual(chat.conversa(self.con, self.ger, self.bot)[0]["acao"], "CHAMADO_FALAR")
        # pedir de novo na mesma conversa não duplica o aviso
        self.fala("4")
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM ajuda_chamados").fetchone()[0], 1)
        self.assertIn("já avisei", self.textos(self.fala("4"))[0])

    def test_chamado_com_duvida_escrita_leva_o_texto(self):
        pergunta = "como faço para fechar o caixa no fim do dia?"
        ajuda.iniciar(self.con, self.func)
        self.fala(pergunta)
        self.assertEqual(self.sessao()["estado"], ajuda.SATISFEITO)
        self.fala("3")
        self.fala("4")
        corpo = [m for m in self.mensagens_da_nucleai_para(self.ger) if m["acao"] == "CHAMADO_FALAR"][0]["corpo"]
        self.assertIn('dúvida escrita: "%s"' % pergunta, corpo)
        self.assertIn("Movimento de caixa › Fechar o caixa e assinar o relatório", corpo)
        self.assertEqual(self.con.execute("SELECT duvida FROM ajuda_chamados").fetchone()["duvida"], pergunta)

    def test_gerencia_offline_a_nucleai_avisa_que_respondera_assim_que_possivel(self):
        r = self.chamar()          # ninguém está online
        t = self.textos(r)[0]
        self.assertIn("ninguém responsável está online", t)
        self.assertIn("não podem responder agora", t)
        self.assertIn("o mais rápido possível", t)
        self.assertEqual(self.con.execute("SELECT gerencia_online FROM ajuda_chamados").fetchone()[0], 0)
        # a mensagem para a gerência foi enviada do mesmo jeito (eles verão ao entrar)
        self.assertEqual(len([m for m in self.mensagens_da_nucleai_para(self.ger) if m["acao"] == "CHAMADO_FALAR"]), 1)

    def test_gerencia_online_a_nucleai_diz_que_avisou(self):
        presenca.bater(self.con, self.admin, "t1")
        t = self.textos(self.chamar())[0]
        self.assertIn("Avisei", t)
        self.assertNotIn("ninguém responsável", t)

    def test_administracao_escolhe_quem_recebe(self):
        ajuda.definir(self.con, "nucleai_destinatarios", json.dumps([self.ger]))
        self.con.commit()
        presenca.bater(self.con, self.ger, "t1")
        self.chamar()
        self.assertEqual(len([m for m in self.mensagens_da_nucleai_para(self.ger) if m["acao"] == "CHAMADO_FALAR"]), 1)
        self.assertEqual([m for m in self.mensagens_da_nucleai_para(self.admin) if m["acao"]], [])   # não foi escolhido
        self.assertEqual(self.con.execute("SELECT avisados FROM ajuda_chamados").fetchone()[0], 1)

    def test_status_online_considera_so_os_escolhidos(self):
        ajuda.definir(self.con, "nucleai_destinatarios", json.dumps([self.ger]))
        self.con.commit()
        presenca.bater(self.con, self.admin, "t1")     # o administrador está online, mas não foi escolhido
        self.assertIn("ninguém responsável está online", self.textos(self.chamar())[0])

    def test_destinatario_escolhido_sem_perfil_de_gerencia_tambem_ve_a_mensagem(self):
        comum = self.perfil("NA_ESCOLHIDO", ["atendimentos"])
        ajuda.definir(self.con, "nucleai_destinatarios", json.dumps([comum]))
        self.con.commit()
        self.chamar()
        self.assertEqual(chat.conversa(self.con, comum, self.bot)[0]["acao"], "CHAMADO_FALAR")
        self.assertIn("NucleAI", [c["nome"] for c in chat.contatos(self.con, comum)])

    def test_sem_ninguem_para_avisar(self):
        ajuda.definir(self.con, "nucleai_destinatarios", json.dumps([self.func]))   # só a própria pessoa: não conta
        self.con.commit()
        t = self.textos(self.chamar())[0]
        self.assertIn("Não encontrei ninguém", t)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM ajuda_chamados").fetchone()[0], 0)

    # ---- botão "Falar com o usuário" e confirmação Sim/Não
    def chamado_pronto(self, ti=5, mi=0, ai=0):
        presenca.bater(self.con, self.ger, "t1")
        self.chamar(ti=ti, mi=mi, ai=ai)
        return self.con.execute("SELECT id FROM ajuda_chamados").fetchone()["id"]

    def test_gerencia_clica_em_falar_com_o_usuario(self):
        cid = self.chamado_pronto()
        c = self.cliente("NA_GER", "senha123")
        r = self.post(c, "/ajuda/chamado/%d/contatar" % cid)
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers["Location"].endswith("/mensagens?com=%d" % self.func))
        ch = self.con.execute("SELECT * FROM ajuda_chamados WHERE id=?", (cid,)).fetchone()
        self.assertEqual((ch["status"], ch["atendido_por_id"]), ("EM_ATENDIMENTO", self.ger))
        # a pessoa recebe a pergunta pronta, vinda da própria gerência, com a ação de confirmação
        msgs = [m for m in chat.conversa(self.con, self.func, self.ger) if m["acao"] == "CHAMADO_CONFIRMA"]
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["de_id"], self.ger)
        onde = " › ".join(titulos(5, 0, 0))
        for trecho in ("Aqui é", "da gerência", onde, "A sua dúvida é sobre isso mesmo?"):
            self.assertIn(trecho, msgs[0]["corpo"])
        # clicar de novo não duplica a pergunta
        self.post(c, "/ajuda/chamado/%d/contatar" % cid)
        self.assertEqual(len([m for m in chat.conversa(self.con, self.func, self.ger) if m["acao"] == "CHAMADO_CONFIRMA"]), 1)

    def test_so_quem_recebeu_o_pedido_pode_contata_lo(self):
        cid = self.chamado_pronto()
        intruso = self.cliente("NA_OUTRO", "senha123")
        r = self.post(intruso, "/ajuda/chamado/%d/contatar" % cid)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.con.execute("SELECT status FROM ajuda_chamados").fetchone()[0], "ABERTO")
        self.assertEqual([m for m in chat.conversa(self.con, self.func, self.outro) if m["acao"]], [])

    def test_confirmar_sim_envia_o_detalhe_a_gerencia(self):
        cid = self.chamado_pronto(ti=4, mi=2, ai=0)   # Financeiro › Faturamento › Registrar uma fatura
        self.post(self.cliente("NA_GER", "senha123"), "/ajuda/chamado/%d/contatar" % cid)
        usuario = self.cliente("NA_FUNC", "senha123")
        r = self.post(usuario, "/ajuda/chamado/%d/confirmar" % cid, {"resposta": "SIM"})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers["Location"].endswith("/mensagens?com=%d" % self.ger))
        ch = self.con.execute("SELECT * FROM ajuda_chamados WHERE id=?", (cid,)).fetchone()
        self.assertEqual(ch["confirmou"], "SIM")
        detalhes = [m for m in self.mensagens_da_nucleai_para(self.ger) if not m["acao"]]
        self.assertTrue(2 <= len(detalhes) <= 3, len(detalhes))
        for m in detalhes:
            self.assertLessEqual(len(m["corpo"]), chat.MAX_CORPO)
            self.assertIsNotNone(m["expira_em"])      # some sozinha depois de alguns dias
        resumo, modulo = detalhes[0]["corpo"], detalhes[1]["corpo"]
        ti, mi, ai = 4, 2, 0
        self.assertIn("Resumo para a gerência", resumo)
        self.assertIn(ajuda.instrucoes(ti, mi, ai).split("\n\n", 1)[1][:80], resumo)   # o passo a passo completo da área
        self.assertIn("Assunto: " + " › ".join(titulos(ti, mi, ai)), resumo)
        self.assertIn('Sobre o módulo "Faturamento"', modulo)
        self.assertIn("O que faz:", modulo)
        self.assertIn("Quem acessa:", modulo)
        self.assertIn("Outras áreas deste módulo", modulo)
        self.assertIn("Se a pessoa continuar com dificuldade", modulo)
        # citação direta do LEIA-ME
        citacao = [m["corpo"] for m in detalhes if m["corpo"].startswith("📖 Do LEIA-ME")]
        self.assertEqual(len(citacao), 1)
        self.assertIn("Faturamento", citacao[0])
        # a pergunta da gerência mostra a resposta (sem botões) para quem abrir a conversa depois
        resp = [m for m in chat.conversa(self.con, self.func, self.ger) if m["acao"] == "CHAMADO_CONFIRMA"][0]
        self.assertEqual(resp["acao_resp"], "SIM")
        self.assertEqual(chat.serializar(resp, self.func)["acao_resp"], "SIM")
        # a NucleAI, para a gerência, fica visível como contato
        self.assertIn("NucleAI", [c["nome"] for c in chat.contatos(self.con, self.ger)])

    def test_confirmar_nao_avisa_a_gerencia_sem_detalhes(self):
        cid = self.chamado_pronto()
        self.post(self.cliente("NA_GER", "senha123"), "/ajuda/chamado/%d/contatar" % cid)
        self.post(self.cliente("NA_FUNC", "senha123"), "/ajuda/chamado/%d/confirmar" % cid, {"resposta": "NAO"})
        self.assertEqual(self.con.execute("SELECT confirmou FROM ajuda_chamados").fetchone()[0], "NAO")
        avisos = [m for m in self.mensagens_da_nucleai_para(self.ger) if not m["acao"]]
        self.assertEqual(len(avisos), 1)
        self.assertIn("NÃO é sobre", avisos[0]["corpo"])
        self.assertNotIn("Resumo para a gerência", avisos[0]["corpo"])

    def test_confirmacao_so_vale_uma_vez_e_so_para_o_dono(self):
        cid = self.chamado_pronto()
        self.post(self.cliente("NA_GER", "senha123"), "/ajuda/chamado/%d/contatar" % cid)
        outro = self.cliente("NA_OUTRO", "senha123")
        self.post(outro, "/ajuda/chamado/%d/confirmar" % cid, {"resposta": "SIM"})
        self.assertIsNone(self.con.execute("SELECT confirmou FROM ajuda_chamados").fetchone()[0])
        dono = self.cliente("NA_FUNC", "senha123")
        self.post(dono, "/ajuda/chamado/%d/confirmar" % cid, {"resposta": "SIM"})
        antes = len(self.mensagens_da_nucleai_para(self.ger))
        self.post(dono, "/ajuda/chamado/%d/confirmar" % cid, {"resposta": "NAO"})   # segunda resposta é ignorada
        self.assertEqual(self.con.execute("SELECT confirmou FROM ajuda_chamados").fetchone()[0], "SIM")
        self.assertEqual(len(self.mensagens_da_nucleai_para(self.ger)), antes)

    def test_serializacao_das_acoes_para_os_botoes(self):
        cid = self.chamado_pronto()
        falar = [m for m in chat.conversa(self.con, self.ger, self.bot) if m["acao"] == "CHAMADO_FALAR"][0]
        s = chat.serializar(falar, self.ger)
        self.assertEqual((s["acao"], s["chamado_id"], s["acao_resp"], s["minha"]), ("CHAMADO_FALAR", cid, None, False))
        # as respostas da NucleAI chegam pela tela de Mensagens com os campos que o chat.js usa
        c = self.cliente("NA_GER", "senha123")
        dados = c.get("/mensagens/novas?com=%d&depois=0&depois_conv=0" % self.bot).get_json()
        self.assertEqual(dados["conversa"][0]["acao"], "CHAMADO_FALAR")
        self.assertEqual(dados["conversa"][0]["chamado_id"], cid)

    def test_chamados_ficam_listados_e_podem_ser_resolvidos(self):
        cid = self.chamado_pronto()
        adm = self.cliente()
        pagina = self.texto(adm.get("/nucleai/chamados"))
        self.assertIn("NA_FUNC", pagina)
        self.assertIn("Marcar resolvido", pagina)
        self.post(adm, "/nucleai/chamados/%d/resolver" % cid)
        self.assertEqual(self.con.execute("SELECT status FROM ajuda_chamados").fetchone()[0], "RESOLVIDO")
        self.assertNotIn("Marcar resolvido", self.texto(adm.get("/nucleai/chamados")))
        self.assertIn("Resolvido", self.texto(adm.get("/nucleai/chamados?status=RESOLVIDO")))
        # um resolvido não abre conversa de novo
        r = self.post(self.cliente("NA_GER", "senha123"), "/ajuda/chamado/%d/contatar" % cid)
        self.assertEqual(r.status_code, 302)
        self.assertEqual([m for m in chat.conversa(self.con, self.func, self.ger) if m["acao"]], [])

    def test_readme_citado_pelo_assunto(self):
        achado = ajuda.trecho_readme("Financeiro", "Faturamento", "Registrar uma fatura")
        self.assertIsNotNone(achado)
        self.assertIn("atura", achado[0] + achado[1])
        self.assertLessEqual(len(achado[1]), 1200)
        self.assertIsNone(ajuda.trecho_readme("Zzzzz", "Wwwww", "Xqxqxq"))

    # ================================================================ chat temporário e segurança
    def test_contato_so_existe_durante_a_conversa(self):
        self.assertNotIn("NucleAI", [c["nome"] for c in chat.contatos(self.con, self.func)])
        ajuda.iniciar(self.con, self.func)
        contatos = {c["nome"]: c for c in chat.contatos(self.con, self.func)}
        self.assertIn("NucleAI", contatos)
        self.assertEqual(contatos["NucleAI"]["avatar"], "/static/img/nucleai.svg")
        self.assertTrue(contatos["NucleAI"]["online"])
        self.assertEqual(contatos["NucleAI"]["sistema"], 3)
        self.assertNotIn("NucleAI", [c["nome"] for c in chat.contatos(self.con, self.outro)])

    def test_nao_ha_resposta_sem_conversa_iniciada(self):
        with self.assertRaises(chat.ErroChat):
            chat.enviar(self.con, self.outro, self.bot, "1")
        self.assertEqual(ajuda.responder(self.con, self.outro, "1"), {"mensagens": [], "encerrado": False})

    def test_reiniciar_apaga_a_conversa_anterior(self):
        self.ate_a_area(0, 0, 0)
        ajuda.iniciar(self.con, self.func)
        self.assertEqual(len(self.conversa()), 1)
        s = self.sessao()
        self.assertEqual((s["estado"], s["tema"], s["gerencia_chamada"], s["registro_id"]), (ajuda.TEMA, None, 0, None))

    def test_conversas_de_pessoas_diferentes_nao_se_misturam(self):
        ajuda.iniciar(self.con, self.func)
        ajuda.iniciar(self.con, self.outro)
        self.fala("3", self.func)
        self.fala("5", self.outro)
        self.assertEqual(self.sessao(self.func)["tema"], 2)
        self.assertEqual(self.sessao(self.outro)["tema"], 4)
        self.assertEqual(self.conversa(self.func)[-1], ajuda.menu_modulos(2))
        self.assertEqual(self.conversa(self.outro)[-1], ajuda.menu_modulos(4))

    def test_nucleai_esta_sempre_online_e_nao_aparece_na_lista_de_usuarios(self):
        self.assertTrue(presenca.situacao(self.con)[self.bot]["online"])
        c = self.cliente()
        with self.app.test_request_context():
            from flask import url_for
            url = url_for("admin.usuarios")
        self.assertNotIn("<strong>NucleAI</strong>", self.texto(c.get(url)))   # o contato do sistema não é um usuário da lista

    def test_nucleai_nao_consegue_logar(self):
        anonimo = self.app.test_client()
        anonimo.get("/login")
        with anonimo.session_transaction() as s:
            token = s["csrf"]
        anonimo.post("/login", data={"usuario": "NucleAI", "senha": "x", "_csrf": token})
        self.assertIn("/login", anonimo.get("/").headers.get("Location", ""))

    def test_conteudo_mudado_no_meio_da_conversa_nao_quebra(self):
        ajuda.iniciar(self.con, self.func)
        self.fala("2")
        self.fala("1")
        self.con.execute("UPDATE ajuda_sessoes SET area=999 WHERE usuario_id=?", (self.func,))   # índice que deixou de existir
        self.con.execute("UPDATE ajuda_sessoes SET estado='SATISFEITO' WHERE usuario_id=?", (self.func,))
        self.con.commit()
        t = self.textos(self.fala("1"))
        self.assertIn("recomeçar", t[0])
        self.assertEqual(self.sessao()["estado"], ajuda.TEMA)

    # ================================================================ configurações
    def test_nucleai_desligada(self):
        ajuda.definir(self.con, "nucleai_ativa", "0")
        self.con.commit()
        self.assertFalse(ajuda.ativa(self.con))
        c = self.cliente("NA_FUNC", "senha123")
        self.assertNotIn("nucleai-flutuante", self.texto(c.get("/")))
        r = self.post(c, "/ajuda/iniciar")
        self.assertEqual(r.status_code, 302)
        self.assertNotIn("com=", r.headers["Location"])
        self.assertIsNone(self.sessao())
        # uma conversa em andamento é encerrada com um aviso
        ajuda.definir(self.con, "nucleai_ativa", "1")
        self.con.commit()
        ajuda.iniciar(self.con, self.func)
        ajuda.definir(self.con, "nucleai_ativa", "0")
        self.con.commit()
        r = self.fala("1")
        self.assertTrue(r["encerrado"])
        self.assertIn("desligada", self.textos(r)[0])

    def test_tempos_configuraveis(self):
        ajuda.definir(self.con, "nucleai_despedida_s", "30")
        ajuda.definir(self.con, "nucleai_abandono_h", "1")
        self.con.commit()
        self.assertEqual((ajuda.despedida_s(self.con), ajuda.abandono_h(self.con)), (30, 1))
        self.ate_a_area(0, 0, 0)
        self.fala("1")
        self.fala("0")
        expira = datetime.strptime(self.con.execute("SELECT expira_em FROM chat_mensagens WHERE de_id=?", (self.bot,)).fetchone()[0],
                                   "%Y-%m-%d %H:%M:%S")
        self.assertAlmostEqual((expira - datetime.now()).total_seconds(), 30, delta=3)
        # conversa parada há mais de 1 hora é apagada
        ajuda.iniciar(self.con, self.outro)
        self.con.execute("UPDATE ajuda_sessoes SET atualizado_em=? WHERE usuario_id=?",
                         ((datetime.now() - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S"), self.outro))
        self.con.commit()
        ajuda.limpar(self.con)
        self.assertIsNone(self.sessao(self.outro))
        # valores absurdos no banco caem nos limites
        ajuda.definir(self.con, "nucleai_abandono_h", "9999")
        ajuda.definir(self.con, "nucleai_despedida_s", "abc")
        self.con.commit()
        self.assertEqual((ajuda.abandono_h(self.con), ajuda.despedida_s(self.con)), (72, 60))

    def test_tela_de_configuracoes(self):
        adm = self.cliente()
        pagina = self.texto(adm.get("/nucleai/config"))
        for trecho in ("NucleAI ligada", "Apagar conversa abandonada", "A despedida some", "Quem recebe os pedidos de ajuda", "NA_GER"):
            self.assertIn(trecho, pagina)
        r = self.post(adm, "/nucleai/config", {"ativa": "1", "abandono_h": "3", "despedida_s": "45", "destinatarios": [str(self.ger), "999999", "x"]})
        self.assertEqual(r.status_code, 302)
        self.assertEqual((ajuda.abandono_h(self.con), ajuda.despedida_s(self.con), ajuda.destinatarios_escolhidos(self.con), ajuda.ativa(self.con)),
                         (3, 45, [self.ger], True))      # ids inexistentes são descartados
        self.post(adm, "/nucleai/config", {"abandono_h": "3", "despedida_s": "45"})              # sem "ativa": desliga
        self.assertFalse(ajuda.ativa(self.con))
        self.assertEqual(ajuda.destinatarios_escolhidos(self.con), [])
        # valores inválidos não gravam
        for ruim in ({"abandono_h": "0", "despedida_s": "45"}, {"abandono_h": "3", "despedida_s": "5"}, {"abandono_h": "x", "despedida_s": "45"},
                     {"abandono_h": "99", "despedida_s": "45"}):
            antes = (ajuda.abandono_h(self.con), ajuda.despedida_s(self.con))
            self.post(adm, "/nucleai/config", dict(ruim, ativa="1"))
            self.assertEqual((ajuda.abandono_h(self.con), ajuda.despedida_s(self.con)), antes, ruim)

    # ================================================================ conteúdo editável
    def test_editar_um_texto_vale_na_hora_e_pode_ser_restaurado(self):
        ti, mi, ai = self.indices("Movimento de caixa", "Fechar o caixa e assinar o relatório")
        tema, modulo, area = titulos(ti, mi, ai)
        novo = "1. Texto novo escrito pela administração para esta área.\n2. Segundo passo."
        ajuda_admin.editar(self.con, "ADMIN", tema, modulo, area, novo)
        B = ajuda.base(self.con)
        self.assertEqual(B.temas[ti][1][mi][1][ai][1], novo)
        self.assertNotEqual(TEMAS[ti][1][mi][1][ai][1], novo)     # a base do código não muda
        r = self.ate_a_area(ti, mi, ai)
        self.assertIn(novo, self.textos(r)[0])
        estados = {a["titulo"]: a["estado"] for t in ajuda_admin.arvore_para_tela(self.con) for m in t["modulos"] for a in m["areas"]
                   if m["titulo"] == modulo}
        self.assertEqual(estados[area], "EDITADA")
        ajuda_admin.restaurar(self.con, tema, modulo, area)
        self.assertEqual(ajuda.base(self.con).temas[ti][1][mi][1][ai][1], TEMAS[ti][1][mi][1][ai][1])
        # editar de volta para o texto original apaga a edição
        ajuda_admin.editar(self.con, "ADMIN", tema, modulo, area, novo)
        ajuda_admin.editar(self.con, "ADMIN", tema, modulo, area, TEMAS[ti][1][mi][1][ai][1])
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM ajuda_conteudo").fetchone()[0], 0)

    def test_validacao_do_conteudo(self):
        tema, modulo, area = titulos(*self.indices("Clientes", "Telefone no padrão"))
        for texto in ("", "curto", "x" * (ajuda_admin.MAX_TEXTO + 1)):
            with self.assertRaises(ajuda_admin.ErroConteudo):
                ajuda_admin.editar(self.con, "ADMIN", tema, modulo, area, texto)
        with self.assertRaises(ajuda_admin.ErroConteudo):
            ajuda_admin.editar(self.con, "ADMIN", tema, modulo, "Área que não existe", "x" * 40)
        with self.assertRaises(ajuda_admin.ErroConteudo):
            ajuda_admin.criar(self.con, "ADMIN", tema, modulo, area, "x" * 40)       # já existe
        with self.assertRaises(ajuda_admin.ErroConteudo):
            ajuda_admin.criar(self.con, "ADMIN", "", modulo, "Título novo", "x" * 40)
        with self.assertRaises(ajuda_admin.ErroConteudo):
            ajuda_admin.criar(self.con, "ADMIN", tema, modulo, "T" * 80, "x" * 40)
        with self.assertRaises(ajuda_admin.ErroConteudo):
            ajuda_admin.criar(self.con, "ADMIN", "Tema novo", "Módulo novo", "Área", "x" * 40, chave_acesso="modulo_que_nao_existe")
        with self.assertRaises(ajuda_admin.ErroConteudo):
            ajuda_admin.excluir(self.con, 999999)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM ajuda_conteudo").fetchone()[0], 0)

    def test_criar_area_em_modulo_existente_aparece_no_menu_e_na_busca(self):
        tema, modulo, _ = titulos(*self.indices("Convênios", "Cadastrar convênio e valores"))
        texto = "1. Abra o convênio XPTO.\n2. Peça a segunda via da guia ao atendente da operadora."
        ajuda_admin.criar(self.con, "ADMIN", tema, modulo, "Segunda via da guia do convênio XPTO", texto)
        B = ajuda.base(self.con)
        ti, mi, _ = B.localizar(tema, modulo)
        self.assertEqual(len(B.temas[ti][1][mi][1]), len(TEMAS[ti][1][mi][1]) + 1)
        self.assertIn("Segunda via da guia do convênio XPTO", ajuda.menu_areas(ti, mi, B.temas))
        # a busca por texto encontra a área nova
        ajuda.iniciar(self.con, self.func)
        self.fala("preciso da segunda via da guia do convenio xpto")
        self.assertEqual(self.ultimo_registro()["area"], "Segunda via da guia do convênio XPTO")

    def test_criar_modulo_e_tema_novos_com_acesso(self):
        ajuda_admin.criar(self.con, "ADMIN", "Rotinas internas", "Controle do estoque de seringas", "Contar o estoque",
                          "1. Conte as seringas na bancada.\n2. Anote no caderno de estoque.", chave_acesso="medicamentos")
        B = ajuda.base(self.con)
        self.assertEqual(B.temas[-1][0], "Rotinas internas")
        sem = self.perfil("NA_SEM_MED", ["atendimentos"])
        com = self.perfil("NA_COM_MED", ["medicamentos"])
        self.assertNotIn("Rotinas internas", self.temas_do(sem))
        self.assertIn("Rotinas internas", self.temas_do(com))
        self.assertIn("Rotinas internas", self.temas_do(self.admin))
        # o módulo novo sem permissão exigida aparece para todos
        ajuda_admin.criar(self.con, "ADMIN", "Rotinas internas", "Aviso geral da clínica", "Horário de funcionamento", "A clínica abre às 7h e fecha às 17h.")
        self.assertIn("Aviso geral da clínica", self.modulos_do(sem, "Rotinas internas"))
        # e a conversa chega até lá
        ajuda.iniciar(self.con, com)
        ti = [t[0] for t in B.temas].index("Rotinas internas")
        pos = ajuda.temas_visiveis(self.con, com).index(ti) + 1
        self.fala(str(pos), com)
        self.assertIn("Contar o estoque", self.textos(self.fala("1", com))[0])

    def test_excluir_so_area_criada_pela_administracao(self):
        ajuda_admin.criar(self.con, "ADMIN", "Rotinas internas", "Módulo", "Área nova", "Texto da área nova com mais de vinte letras.")
        cid = self.con.execute("SELECT id FROM ajuda_conteudo").fetchone()["id"]
        ajuda_admin.excluir(self.con, cid)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM ajuda_conteudo").fetchone()[0], 0)
        self.assertNotIn("Rotinas internas", [t[0] for t in ajuda.base(self.con).temas])
        tema, modulo, area = titulos(*self.indices("Clientes", "Telefone no padrão"))
        ajuda_admin.editar(self.con, "ADMIN", tema, modulo, area, "Texto editado de teste, com mais de vinte letras.")
        with self.assertRaises(ajuda_admin.ErroConteudo):
            ajuda_admin.excluir(self.con, self.con.execute("SELECT id FROM ajuda_conteudo").fetchone()["id"])   # editada: restaura, não exclui

    def test_telas_do_conteudo(self):
        adm = self.cliente()
        pagina = self.texto(adm.get("/nucleai/conteudo"))
        self.assertIn("Nova área", pagina)
        self.assertIn("Movimento de caixa", pagina)
        self.assertGreater(pagina.count("<textarea"), 100)       # uma por área
        tema, modulo, area = titulos(*self.indices("Pastas", "Se a pasta não abrir"))
        novo = "Texto novo para a área, escrito pela tela de conteúdo."
        self.post(adm, "/nucleai/conteudo/editar", {"tema": tema, "modulo": modulo, "area": area, "texto": novo})
        self.assertIn(novo, self.texto(adm.get("/nucleai/conteudo")))
        self.assertIn("editada por ADMIN", self.texto(adm.get("/nucleai/conteudo")))
        self.post(adm, "/nucleai/conteudo/editar", {"tema": tema, "modulo": modulo, "area": area, "texto": "curto"})   # inválido
        self.assertIn(novo, self.texto(adm.get("/nucleai/conteudo")))
        self.post(adm, "/nucleai/conteudo/restaurar", {"tema": tema, "modulo": modulo, "area": area})
        self.assertNotIn(novo, self.texto(adm.get("/nucleai/conteudo")))
        self.post(adm, "/nucleai/conteudo/nova", {"tema": tema, "modulo": modulo, "tema_novo": "", "modulo_novo": "",
                                                  "area": "Área criada pela tela", "texto": "Texto da área criada pela tela, com bastante conteúdo."})
        self.assertIn("Área criada pela tela", self.texto(adm.get("/nucleai/conteudo")))
        cid = self.con.execute("SELECT id FROM ajuda_conteudo WHERE estado='NOVA'").fetchone()["id"]
        self.post(adm, "/nucleai/conteudo/excluir", {"id": cid})
        self.assertNotIn("Área criada pela tela", self.texto(adm.get("/nucleai/conteudo")))

    # ================================================================ painel, relatórios e telas
    def registrar(self, uid, ti, mi, ai, final, nota=None):
        self.ate_a_area(ti, mi, ai, uid)
        if final == "sim":
            self.fala("1", uid)
            self.fala(str(nota or 0), uid)
        elif final == "sim_de_novo":
            self.fala("2", uid)
            self.fala(str(nota or 0), uid)
        elif final == "nao":
            self.fala("3", uid)

    def test_painel_com_estatisticas(self):
        self.registrar(self.func, 1, 0, 0, "sim", 5)
        self.registrar(self.func, 1, 0, 0, "sim", 3)
        self.registrar(self.outro, 1, 0, 1, "sim_de_novo", 4)
        self.registrar(self.outro, 2, 0, 0, "nao")
        self.registrar(self.outro, 2, 0, 0, "nao")
        ajuda.iniciar(self.con, self.func)
        self.fala("como fecho o caixa")                   # consulta por texto, ainda sem resposta
        self.fala("quero comprar uma pizza")             # não entendida (sem consulta)
        presenca.bater(self.con, self.ger, "t1")
        self.chamar(self.outro, 3, 0, 0)
        hoje = datetime.now().strftime("%Y-%m-%d")
        p = ajuda_stats.painel(self.con, hoje, hoje)
        self.assertEqual(p["total"], 7)
        self.assertEqual((p["resolveu"], p["resolveu_e_nova"], p["nao_resolveu"]), (3, 1, 3))
        self.assertEqual(p["em_andamento"], 1)
        self.assertEqual(p["taxa_resolucao"], 50.0)
        self.assertEqual((p["nota_media"], p["n_notas"]), (4.0, 3))
        self.assertEqual(dict(p["distribuicao_notas"])[5], 1)
        self.assertEqual((p["por_texto"], p["por_lista"]), (1, 6))
        self.assertEqual(p["chamados"], 1)
        self.assertEqual(p["chamados_status"]["ABERTO"], 1)
        self.assertEqual(p["temas"][0]["chave"], "Lançamentos")
        piores = {a["chave"]: a for a in p["nao_ajudou"]}
        ruim = "%s › %s › %s" % titulos(2, 0, 0)
        self.assertEqual((piores[ruim]["nao"], piores[ruim]["taxa_nao"]), (2, 100.0))
        self.assertEqual(p["nao_entendidas"][0]["texto"], "quero comprar uma pizza")
        self.assertEqual({u["usuario"]: u["n"] for u in p["usuarios"]}, {"NA_FUNC": 3, "NA_OUTRO": 4})
        self.assertEqual(len(p["por_dia"]), 1)
        # dia sem consultas
        vazio = ajuda_stats.painel(self.con, "2000-01-01", "2000-01-03")
        self.assertEqual((vazio["total"], vazio["taxa_resolucao"], vazio["nota_media"], len(vazio["por_dia"])), (0, None, None, 3))

    def test_o_registro_sobrevive_ao_fim_do_chat(self):
        self.registrar(self.func, 1, 0, 0, "sim", 5)
        ajuda.limpar(self.con, datetime.now() + timedelta(days=1))
        self.assertIsNone(self.sessao())
        hoje = datetime.now().strftime("%Y-%m-%d")
        self.assertEqual(ajuda_stats.painel(self.con, hoje, hoje)["total"], 1)

    def test_telas_e_relatorios_da_nucleai(self):
        self.registrar(self.func, 1, 0, 0, "sim", 5)
        self.registrar(self.func, 2, 0, 0, "nao")
        adm = self.cliente()
        for rota, trecho in (("/nucleai", "Consultas por dia"), ("/nucleai/chamados", "Chamados"), ("/nucleai/conteudo", "Nova área"),
                             ("/nucleai/config", "Quem recebe os pedidos de ajuda")):
            r = adm.get(rota)
            self.assertEqual(r.status_code, 200, rota)
            self.assertIn(trecho, self.texto(r), rota)
        painel = self.texto(adm.get("/nucleai"))
        self.assertIn("Áreas em que mais usuários disseram", painel)
        self.assertIn("Dúvidas escritas que a NucleAI não entendeu", painel)
        pdf = adm.get("/nucleai/relatorio.pdf")
        self.assertEqual(pdf.data[:4], b"%PDF")
        xlsx = adm.get("/nucleai/relatorio.xlsx")
        self.assertTrue(xlsx.data.startswith(b"PK"))
        from io import BytesIO
        from openpyxl import load_workbook
        wb = load_workbook(BytesIO(xlsx.data))
        self.assertEqual(wb.sheetnames, ["Resumo", "Temas e módulos", "Não ajudou", "Não entendidas", "Chamados", "Consultas"])
        self.assertEqual(wb["Consultas"].max_row, 4 + 2)       # cabeçalho na linha 4 + duas consultas
        # período inválido ou invertido não quebra
        self.assertEqual(adm.get("/nucleai?de=xx&ate=2020-13-45").status_code, 200)
        self.assertEqual(adm.get("/nucleai?de=2026-12-31&ate=2026-01-01").status_code, 200)

    def test_so_a_administracao_entra_no_modulo_nucleai(self):
        comum = self.cliente("NA_FUNC", "senha123")
        for rota in ("/nucleai", "/nucleai/chamados", "/nucleai/conteudo", "/nucleai/config", "/nucleai/relatorio.pdf", "/nucleai/relatorio.xlsx"):
            self.assertEqual(comum.get(rota).status_code, 302, rota)
        for rota, dados in (("/nucleai/config", {"abandono_h": "3", "despedida_s": "45"}),
                            ("/nucleai/conteudo/nova", {"tema": "x", "modulo": "y", "area": "z", "texto": "w" * 30}),
                            ("/nucleai/conteudo/editar", {"tema": "x", "modulo": "y", "area": "z", "texto": "w" * 30})):
            self.post(comum, rota, dados)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM ajuda_conteudo").fetchone()[0], 0)
        self.assertIsNone(self.con.execute("SELECT 1 FROM config WHERE chave='nucleai_abandono_h'").fetchone())
        self.assertEqual(self.app.test_client().get("/nucleai").status_code, 302)    # sem login

    # ================================================================ pela tela (HTTP)
    def test_botao_flutuante_nas_telas_e_nao_no_chat(self):
        c = self.cliente("NA_FUNC", "senha123")
        pagina = self.texto(c.get("/", headers={"Referer": "http://localhost/"}))
        self.assertIn("nucleai-flutuante", pagina)
        self.assertIn('action="/ajuda/iniciar"', pagina)
        self.assertIn("nucleai.svg", pagina)
        self.assertNotIn("nucleai-flutuante", self.texto(c.get("/mensagens")))
        self.assertEqual(self.app.test_client().get("/ajuda/iniciar").status_code, 405)

    def test_clicar_no_botao_abre_a_conversa(self):
        c = self.cliente("NA_FUNC", "senha123")
        r = self.post(c, "/ajuda/iniciar")
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers["Location"].endswith("/mensagens?com=%d" % self.bot))
        pagina = self.texto(c.get(r.headers["Location"]))
        self.assertIn("NucleAI", pagina)
        self.assertIn("chat-avatar-img", pagina)
        self.assertIn("Sobre qual tema", pagina)
        self.assertEqual(c.get("/static/img/nucleai.svg").status_code, 200)

    def test_sem_login_nao_inicia(self):
        anonimo = self.app.test_client()
        anonimo.get("/login")
        with anonimo.session_transaction() as s:
            token = s["csrf"]
        r = anonimo.post("/ajuda/iniciar", data={"_csrf": token})
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r.headers["Location"])
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM ajuda_sessoes").fetchone()[0], 0)
        for rota in ("/ajuda/chamado/1/contatar", "/ajuda/chamado/1/confirmar"):
            r = anonimo.post(rota, data={"_csrf": token})
            self.assertIn("/login", r.headers["Location"])

    def test_envio_pela_tela_devolve_as_respostas_junto(self):
        c = self.cliente("NA_FUNC", "senha123")
        self.post(c, "/ajuda/iniciar")
        r = self.post(c, "/mensagens/enviar", {"para": self.bot, "corpo": "1"}, headers={"Accept": "application/json"})
        self.assertEqual(r.status_code, 200)
        dados = r.get_json()
        self.assertEqual(dados["mensagem"]["corpo"], "1")
        self.assertEqual([m["corpo"] for m in dados["respostas"]], [self.mm0()])
        self.assertFalse(dados["encerrado"])
        r = self.post(c, "/mensagens/enviar", {"para": self.bot, "corpo": "?????"})
        self.assertEqual(len(r.get_json()["respostas"]), 2)
        # uma dúvida escrita também é respondida na hora
        r = self.post(c, "/mensagens/enviar", {"para": self.bot, "corpo": "como faço backup"})
        self.assertEqual(len(r.get_json()["respostas"]), 3)
        self.assertIn("Backup", r.get_json()["respostas"][1]["corpo"])
        # fim da conversa pela tela
        r = self.post(c, "/mensagens/enviar", {"para": self.bot, "corpo": "1"})
        r = self.post(c, "/mensagens/enviar", {"para": self.bot, "corpo": "5"})
        dados = r.get_json()
        self.assertTrue(dados["encerrado"])
        self.assertIn(F.SUFIXO_APAGAR, dados["respostas"][0]["corpo"])

    def test_envio_para_a_nucleai_sem_conversa_e_recusado(self):
        c = self.cliente("NA_OUTRO", "senha123")
        r = self.post(c, "/mensagens/enviar", {"para": self.bot, "corpo": "1"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("NucleAI", r.get_json()["erro"])

    def test_contatos_de_aviso_continuam_somente_leitura(self):
        c = self.cliente("NA_FUNC", "senha123")
        for contato in (self.sistema, self.con.execute("SELECT id FROM usuarios WHERE sistema=2").fetchone()["id"]):
            r = self.post(c, "/mensagens/enviar", {"para": contato, "corpo": "oi"})
            self.assertEqual(r.status_code, 400)

    def test_mensagem_da_nucleai_chega_na_consulta_periodica(self):
        c = self.cliente("NA_FUNC", "senha123")
        self.post(c, "/ajuda/iniciar")
        dados = c.get("/mensagens/novas?com=%d&depois=0&depois_conv=0&visivel=1&lista=1" % self.bot).get_json()
        self.assertEqual(len(dados["conversa"]), 1)
        item = [x for x in dados["contatos"] if x["nome"] == "NucleAI"][0]
        self.assertEqual(item["avatar"], "/static/img/nucleai.svg")


class BuscaDeDuvidas(unittest.TestCase):
    """A busca por texto, sozinha: o que o usuário escreve cai na área certa, e o que não tem relação não é "entendido"."""

    @classmethod
    def setUpClass(cls):
        from app.ajuda_busca import Indice
        cls.indice = Indice(TEMAS, ALIASES)

    def melhores(self, texto):
        from app.ajuda_busca import decidir
        nivel, achados = decidir(self.indice.buscar(texto))
        return nivel, [(TEMAS[r["ti"]][1][r["mi"]][0], TEMAS[r["ti"]][1][r["mi"]][1][r["ai"]][0]) for r in achados]

    CASOS = [
        ("como fecho o caixa", "Movimento de caixa", "Fechar o caixa e assinar o relatório"),
        ("nao consigo fechar o cx", "Movimento de caixa", "Fechar o caixa e assinar o relatório"),
        ("fexar o caixa", "Movimento de caixa", "Fechar o caixa e assinar o relatório"),
        ("abrir o caixa", "Movimento de caixa", "Abrir o caixa do dia"),
        ("como recebo pagamento em pix", "Movimento de caixa", "Receber um pagamento e imprimir a quitação"),
        ("preciso imprimir de novo a ficha do paciente", "Atendimentos", "Reimprimir as fichas"),
        ("paciente faltou e quero chamar no zap", "Faltas e reagendamento", "Chamar quem faltou"),
        ("paciente quer remarcar", "Faltas e reagendamento", "Marcar Reagendado ou Desistiu"),
        ("esqueci minha senha", "Minha conta", "Trocar a sua senha"),
        ("como cadastro um paciente novo", "Clientes", "Cadastrar um novo cliente"),
        ("cadastar cliente", "Clientes", "Cadastrar um novo cliente"),
        ("o telefone do cliente nao aceita", "Clientes", "Telefone no padrão"),
        ("como lanço um atendimento de convenio", "Lançar atendimento", "Passo a passo do lançamento"),
        ("liberar laudo", "Mapa de laudos", "Mudar a situação de um laudo"),
        ("entreguei o laudo para o paciente", "Mapa de laudos", "Marcar como entregue pela mensagem"),
        ("o que significa processando imagem", "Mapa de laudos", "Entender as colunas"),
        ("como faço backup", "Backup", "Fazer uma cópia de segurança"),
        ("avisar os usuarios que vai atualizar", "Backup", "Avisar os usuários antes de atualizar"),
        ("dar acesso para um funcionario novo", "Usuários e perfis", "Criar um usuário"),
        ("usuario nao ve o financeiro", "Usuários e perfis", "Escolher os módulos de cada pessoa"),
        ("quanto repassar pro medico", "Financeiro da Agenda", "Como o valor é calculado"),
        ("agendar paciente no mibi", "Agenda de exames", "MIBI, lista de espera e impressão"),
        ("lista de espera", "Agenda de exames", "MIBI, lista de espera e impressão"),
        ("bloquear um dia na agenda", "Agenda de exames", "Criar a agenda do dia"),
        ("copiar a agenda para outro dia", "Agenda de exames", "Preencher a grade de pacientes"),
        ("lançar conta a pagar", "Contas a pagar", "Cadastrar uma conta"),
        ("paguei uma conta e quero dar baixa", "Contas a pagar", "Quitar uma conta"),
        ("convenio pagou a nota fiscal", "Faturamento", "Quitar e reabrir"),
        ("relatorio de quantos pacientes faltaram", "Relatórios da agenda", "Gerar o relatório"),
        ("devolver blindagem vencida", "Solicitar devolução", "Marcar as vencidas"),
        ("cadastrar blindagem nova", "Novo cadastro", "Cadastrar uma blindagem"),
        ("fazer atestado", "Atestados e declarações", "Escolher o documento"),
        ("imprimir declaracao de comparecimento", "Atestados e declarações", "Preencher e imprimir"),
        ("importar o ponto do relogio", "Importar ponto", "Importar a planilha mensal"),
        ("corrigir uma batida de ponto", "Painel de saldos", "Corrigir um lançamento"),
        ("meu banco de horas", "Minha área", "Meu saldo e meus lançamentos"),
        ("cadastrar licenca sanitaria", "Documentos", "Documento de fiscalização"),
        ("documento vencendo", "Documentos", "Avisos de vencimento"),
        ("quem apagou um atendimento", "Registros de atividades", "Pesquisar quem fez o quê"),
        ("trocar a cor do sistema", "Início", "Usar o menu lateral"),
        ("como mando mensagem pra um colega", "Mensagens", "Enviar e receber mensagens"),
        ("agendar dose de iodo", "Agendar medicamento", "Preencher o agendamento"),
        ("criar uma ficha personalizada", "Exames e fichas", "Fichas personalizadas"),
        ("excluir um atendimento que lancei errado", "Atendimentos", "Excluir um atendimento"),
        ("o sistema esta com erro", "Saúde do sistema", "Quando agir"),
        ("quero desligar a nucleai", "NucleAI", "Configurações da NucleAI"),
        ("quantas duvidas a nucleai atendeu", "NucleAI", "Painel de estatísticas"),
    ]

    def test_bateria_de_duvidas_reais(self):
        erros = []
        for texto, modulo, area in self.CASOS:
            nivel, achados = self.melhores(texto)
            if (modulo, area) not in achados[:3]:
                erros.append((texto, nivel, achados))
        self.assertEqual(erros, [], "dúvidas que a busca não resolveu")

    def test_as_dúvidas_mais_claras_sao_respondidas_direto(self):
        diretas = 0
        for texto, modulo, area in self.CASOS:
            nivel, achados = self.melhores(texto)
            if nivel == "certo" and achados[0] == (modulo, area):
                diretas += 1
            # nunca responde direto uma área errada com confiança
            if nivel == "certo":
                self.assertEqual(achados[0], (modulo, area), texto)
        self.assertGreaterEqual(diretas, 30, "poucas dúvidas respondidas direto")

    def test_assuntos_sem_relacao_nao_sao_entendidos(self):
        for texto in ["asdfgh", "oi tudo bem", "qual a capital da frança", "quero comprar uma pizza", "vai chover amanhã",
                      "quanto custa um carro", "receita de bolo de cenoura", "futebol", "zzzz qqqq", "😀😀", "ok", "123 456"]:
            nivel, achados = self.melhores(texto)
            self.assertEqual(nivel, "nada", "%r foi entendido como %r" % (texto, achados))

    def test_busca_ignora_acentos_maiusculas_e_pontuacao(self):
        base = self.melhores("como fechar o caixa")
        for variante in ("COMO FECHAR O CAIXA!!!", "  como   fechar o caixa ? ", "Cômo fechár o caíxa", "como-fechar,o:caixa"):
            self.assertEqual(self.melhores(variante), base, variante)

    def test_busca_so_considera_os_modulos_permitidos(self):
        from app.ajuda_busca import decidir
        res = self.indice.buscar("fechar o caixa", permitido=lambda ti, mi: TEMAS[ti][1][mi][0] != "Movimento de caixa")
        self.assertTrue(all(TEMAS[r["ti"]][1][r["mi"]][0] != "Movimento de caixa" for r in res))
        self.assertEqual(self.indice.buscar("fechar o caixa", permitido=lambda ti, mi: False), [])

    def test_texto_vazio_e_gigante_nao_quebram(self):
        self.assertEqual(self.indice.buscar(""), [])
        self.assertEqual(self.indice.buscar("   "), [])
        self.indice.buscar("caixa " * 5000)
        self.assertEqual(self.melhores("\x00\x01 caixa")[0] in ("certo", "talvez"), True)

    def test_radical_e_conceitos(self):
        from app.ajuda_busca import radical
        for grupo in (("fechar", "fecho", "fechei", "fechado", "fecha"), ("cadastrar", "cadastro", "cadastrado", "cadastrou"),
                      ("agendar", "agenda", "agendamento", "agendado"), ("cliente", "clientes")):
            self.assertEqual(len({radical(p) for p in grupo}), 1, grupo)


if __name__ == "__main__":
    unittest.main()
