"""Integração Medcloud (motor sem telas): cifra, identificador, fila, robô falso e migração. Nunca toca na Medcloud real."""
import unittest

from app import db as dbmod
from app import medcloud as mc
from tests.test_chat_blindagens import Base


class Fake:
    """Robô falso: devolve o acesso pedido ou levanta a exceção indicada."""

    def __init__(self, acesso=None, erro=None, erro_estudo=None, estudo="9001"):
        self.acesso = acesso
        self.erro = erro
        self.erro_estudo = erro_estudo
        self.estudo = estudo
        self.chamadas = 0          # criações de acesso do paciente
        self.estudos = []          # estudos pedidos: (nome, nascimento, data do estudo, exame)
        self.fechado = False
        self.progresso = None

    def criar_acesso(self, nome, identificador, cidade, uf):
        self.chamadas += 1
        if self.erro:
            raise self.erro
        return self.acesso

    def obter_acesso(self, nome, identificador, cidade, uf):
        return self.criar_acesso(nome, identificador, cidade, uf)

    def criar_estudo(self, nome, nascimento, data_estudo, exame):
        self.estudos.append((nome, nascimento, data_estudo, exame))
        if self.erro_estudo:
            raise self.erro_estudo
        return self.estudo

    def compartilhar_estudo(self, estudo_id, nome, usuario):
        self.compartilhados = getattr(self, "compartilhados", [])
        self.compartilhados.append((estudo_id, nome, usuario))
        erro = getattr(self, "erro_compartilhar", None)
        if erro:
            raise erro

    def fechar(self):
        self.fechado = True


def fabrica(robo):
    return lambda login, senha, url: robo


def conexao(app):
    return dbmod.conectar(app.config["DATABASE"])


def configurar(con, ativo=True):
    valores = {"medcloud_ativo": "1" if ativo else "0", "medcloud_login": "operador",
               "medcloud_senha": mc.cifrar("segredo-da-clinica"), "medcloud_url": "https://medcloud.co"}
    for chave, valor in valores.items():
        con.execute("INSERT INTO config (chave, valor) VALUES (?,?) ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor",
                    (chave, valor))
    con.commit()


def convenio(con, nome, marcado):
    con.execute("INSERT OR IGNORE INTO convenios (nome, gera_caixa, ativo, medcloud) VALUES (?,0,1,?)", (nome, marcado))
    con.execute("UPDATE convenios SET medcloud=? WHERE nome=? COLLATE NOCASE", (marcado, nome))
    con.commit()


def cliente(con, nome, cpf="", contato="", cidade="Governador Valadares", uf="MG", data_nasc="1980-05-20"):
    cur = con.execute("INSERT INTO clientes (nome, cpf, contato, cidade, uf, data_nasc, criado_em) VALUES (?,?,?,?,?,?,?)",
                      (nome, cpf, contato, cidade, uf, data_nasc, "2026-01-01 08:00:00"))
    con.commit()
    return cur.lastrowid


def atendimento(con, cliente_id, convenio_nome):
    cur = con.execute("INSERT INTO atendimentos (cliente_id, cliente_nome, data, exame, convenio, criado_em) "
                      "VALUES (?,?,?,?,?,?)", (cliente_id, "PACIENTE", "2026-02-01", "MIBI", convenio_nome,
                                              "2026-02-01 09:00:00"))
    con.commit()
    return cur.lastrowid


def limpar_fila(con):
    con.execute("DELETE FROM medcloud_fila")
    con.execute("DELETE FROM medcloud_acessos")
    con.commit()


class CifraTestes(Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

    def test_ida_e_volta(self):
        for texto in ("senha-simples", "Ação & çãõ 123", ""):
            self.assertEqual(mc.decifrar(mc.cifrar(texto)), texto)

    def test_token_tem_prefixo_e_nao_guarda_texto_claro(self):
        token = mc.cifrar("minha-senha")
        self.assertTrue(token.startswith("v1:"))
        self.assertNotIn("minha-senha", token)

    def test_cifras_diferentes_para_o_mesmo_texto(self):
        self.assertNotEqual(mc.cifrar("x"), mc.cifrar("x"))

    def test_token_invalido_devolve_vazio(self):
        self.assertEqual(mc.decifrar(""), "")
        self.assertEqual(mc.decifrar(None), "")
        self.assertEqual(mc.decifrar("lixo-sem-prefixo"), "")
        self.assertEqual(mc.decifrar("v1:abc"), "")
        token = mc.cifrar("abc")
        trocado = token[:12] + ("A" if token[12] != "A" else "B") + token[13:]   # caractere do meio: altera bytes de verdade
        self.assertEqual(mc.decifrar(trocado), "")


class IdentificadorTestes(unittest.TestCase):
    def test_cpf_formatado(self):
        self.assertEqual(mc.identificador_do_cliente({"cpf": "123.456.789-09", "contato": "(33) 99999-1234"}), "12345678909")

    def test_sem_cpf_usa_contato(self):
        self.assertEqual(mc.identificador_do_cliente({"cpf": "", "contato": "(33) 99999-1234"}), "33999991234")
        self.assertEqual(mc.identificador_do_cliente({"cpf": "123", "contato": "33 99999-1234"}), "33999991234")

    def test_sem_cpf_nem_contato_devolve_none(self):
        self.assertIsNone(mc.identificador_do_cliente({"cpf": "", "contato": ""}))
        self.assertIsNone(mc.identificador_do_cliente({"cpf": "12", "contato": "sem numero"}))


class EnfileirarTestes(Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        con = conexao(cls.app)
        try:
            convenio(con, "MC_SIM", 1)
            convenio(con, "MC_NAO", 0)
        finally:
            con.close()

    def setUp(self):
        self.con = conexao(self.app)
        limpar_fila(self.con)

    def tearDown(self):
        self.con.close()

    def test_desativado(self):
        configurar(self.con, ativo=False)
        at = atendimento(self.con, cliente(self.con, "A", cpf="11122233344"), "MC_SIM")
        self.assertEqual(mc.enfileirar(self.con, at), "desativado")

    def test_nao_se_aplica_convenio_sem_marca(self):
        configurar(self.con, ativo=True)
        at = atendimento(self.con, cliente(self.con, "B", cpf="11122233355"), "MC_NAO")
        self.assertEqual(mc.enfileirar(self.con, at), "nao_se_aplica")
        self.assertIsNone(self.con.execute("SELECT 1 FROM medcloud_fila WHERE atendimento_id=?", (at,)).fetchone())

    def test_cliente_que_ja_tem_acesso_ainda_gera_estudo_novo(self):
        configurar(self.con, ativo=True)
        cid = cliente(self.con, "C", cpf="11122233366")
        self.con.execute("INSERT INTO medcloud_acessos (cliente_id, usuario, senha, qr, criado_em) VALUES (?,?,?,?,?)",
                         (cid, "USR-C", mc.cifrar("sen-c"), None, "2026-01-01"))
        self.con.commit()
        at = atendimento(self.con, cid, "MC_SIM")
        self.assertEqual(mc.enfileirar(self.con, at), "pendente")   # entra na fila mesmo com acesso: falta o estudo
        self.con.commit()
        # com acesso mas sem estudo criado, NÃO há protocolo na ficha
        st = mc.status_atendimento(self.con, at)
        self.assertEqual((st["estado"], st["senha"]), ("pendente", None))

    def test_so_hoje_nao_cria_estudo_ao_reimprimir_atendimento_antigo(self):
        configurar(self.con, ativo=True)
        at = atendimento(self.con, cliente(self.con, "Antigo", cpf="11122233399"), "MC_SIM")   # criado em 2026-02-01
        self.assertEqual(mc.enfileirar(self.con, at, apenas_hoje=True), "nao_se_aplica")
        self.assertIsNone(self.con.execute("SELECT 1 FROM medcloud_fila WHERE atendimento_id=?", (at,)).fetchone())

    def test_pendente_cria_fila_sem_duplicar(self):
        configurar(self.con, ativo=True)
        at = atendimento(self.con, cliente(self.con, "D", cpf="11122233377"), "MC_SIM")
        self.assertEqual(mc.enfileirar(self.con, at), "pendente")
        self.con.commit()
        self.assertEqual(mc.enfileirar(self.con, at), "pendente")
        self.con.commit()
        n = self.con.execute("SELECT COUNT(*) FROM medcloud_fila WHERE atendimento_id=?", (at,)).fetchone()[0]
        self.assertEqual(n, 1)

    def test_status_de_atendimento_antigo_e_nao_se_aplica(self):
        configurar(self.con, ativo=True)
        at = atendimento(self.con, cliente(self.con, "E", cpf="11122233388"), "MC_SIM")
        self.assertEqual(mc.status_atendimento(self.con, at)["estado"], "nao_se_aplica")
        self.assertEqual(mc.status_atendimento(self.con, at)["link"], "https://medcloud.co?page=nucleleste")


class FilaTestes(Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        con = conexao(cls.app)
        try:
            convenio(con, "MC_FILA", 1)
        finally:
            con.close()

    def setUp(self):
        self.con = conexao(self.app)
        limpar_fila(self.con)
        configurar(self.con, ativo=True)

    def tearDown(self):
        self.con.close()

    def fila(self, at):
        return self.con.execute("SELECT estado, tentativas, erro FROM medcloud_fila WHERE atendimento_id=?", (at,)).fetchone()

    def pedido(self, nome="F", cpf="55566677788"):
        at = atendimento(self.con, cliente(self.con, nome, cpf=cpf), "MC_FILA")
        self.assertEqual(mc.enfileirar(self.con, at), "pendente")
        self.con.commit()
        return at

    def test_sucesso_grava_acesso_com_senha_cifrada_e_cria_o_estudo(self):
        at = self.pedido()
        robo = Fake({"usuario": "USR-OK", "senha": "SEN-OK", "qr": "data:image/png;base64,AAA"})
        self.assertTrue(mc.processar_proxima(self.con, fabrica(robo)))
        self.assertEqual(self.fila(at)["estado"], "OK")
        # estudo: nome do cliente, nascimento e data do atendimento em dd/mm/aaaa, e o exame (a modalidade NM é fixa no robô)
        self.assertEqual(robo.estudos, [("F", "20/05/1980", "01/02/2026", "MIBI")])
        self.assertEqual(self.con.execute("SELECT estudo FROM medcloud_fila WHERE atendimento_id=?", (at,)).fetchone()["estudo"], "9001")
        bruto = self.con.execute("SELECT senha FROM medcloud_acessos").fetchone()["senha"]
        self.assertNotEqual(bruto, "SEN-OK")
        self.assertTrue(bruto.startswith("v1:"))
        st = mc.status_atendimento(self.con, at)
        self.assertEqual((st["estado"], st["usuario"], st["senha"]), ("pronto", "USR-OK", "SEN-OK"))
        self.assertEqual(st["qr"], "data:image/png;base64,AAA")

    def test_falha_tres_vezes_vira_erro(self):
        at = self.pedido("G", "55566677799")
        robo = Fake(erro=Exception("Login recusado pela Medcloud"))
        for esperado in ("PENDENTE", "PENDENTE", "ERRO"):
            self.assertTrue(mc.processar_proxima(self.con, fabrica(robo)))
            self.con.commit()
            self.assertEqual(self.fila(at)["estado"], esperado)
        self.assertEqual(self.fila(at)["tentativas"], 3)
        self.assertEqual(self.fila(at)["erro"], "Login recusado pela Medcloud")
        self.assertTrue(robo.fechado)
        self.assertFalse(mc.processar_proxima(self.con, fabrica(robo)))
        self.assertEqual(mc.status_atendimento(self.con, at)["estado"], "erro")

    def test_cliente_sem_identificador_vai_direto_para_erro(self):
        at = atendimento(self.con, cliente(self.con, "H"), "MC_FILA")
        self.assertEqual(mc.enfileirar(self.con, at), "pendente")
        self.con.commit()
        robo = Fake({"usuario": "X", "senha": "Y", "qr": None})
        self.assertTrue(mc.processar_proxima(self.con, fabrica(robo)))
        self.assertEqual(self.fila(at)["estado"], "ERRO")
        self.assertEqual(self.fila(at)["erro"], "Cliente sem CPF nem celular")
        self.assertEqual(robo.chamadas, 0)

    def test_tentar_de_novo_volta_para_a_fila(self):
        at = self.pedido("I", "55566677700")
        robo = Fake(erro=Exception("Falha de rede"))
        for _ in range(3):
            mc.processar_proxima(self.con, fabrica(robo))
            self.con.commit()
        self.assertEqual(self.fila(at)["estado"], "ERRO")
        self.assertTrue(mc.tentar_de_novo(self.con, at))
        self.con.commit()
        f = self.fila(at)
        self.assertEqual((f["estado"], f["erro"], f["tentativas"]), ("PENDENTE", None, 0))
        self.assertFalse(mc.tentar_de_novo(self.con, at))

    def test_falha_no_estudo_nao_recadastra_o_paciente_e_sem_estudo_nao_ha_protocolo(self):
        at = self.pedido("J", "55566677711")
        robo = Fake({"usuario": "USR-J", "senha": "SEN-J", "qr": None}, erro_estudo=Exception("A Medcloud não confirmou a criação do estudo"))
        mc.processar_proxima(self.con, fabrica(robo))
        self.con.commit()
        self.assertEqual(self.fila(at)["estado"], "PENDENTE")
        self.assertEqual(robo.chamadas, 1)
        # o acesso já ficou gravado, mas sem estudo o protocolo NÃO sai
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM medcloud_acessos").fetchone()[0], 1)
        self.assertEqual(mc.status_atendimento(self.con, at)["senha"], None)
        # nova tentativa: só refaz o estudo; criar o paciente de novo geraria outra senha na Medcloud
        robo.erro_estudo = None
        mc.processar_proxima(self.con, fabrica(robo))
        self.assertEqual(self.fila(at)["estado"], "OK")
        self.assertEqual(robo.chamadas, 1)
        self.assertEqual(len(robo.estudos), 2)
        st = mc.status_atendimento(self.con, at)
        self.assertEqual((st["estado"], st["senha"]), ("pronto", "SEN-J"))

    def test_falha_tres_vezes_no_estudo_vira_erro_sem_protocolo(self):
        at = self.pedido("K", "55566677722")
        robo = Fake({"usuario": "USR-K", "senha": "SEN-K", "qr": None}, erro_estudo=Exception("A Medcloud não confirmou a criação do estudo"))
        for _ in range(3):
            mc.processar_proxima(self.con, fabrica(robo))
            self.con.commit()
        st = mc.status_atendimento(self.con, at)
        self.assertEqual((st["estado"], st["senha"], st["erro"]), ("erro", None, "A Medcloud não confirmou a criação do estudo"))

    def test_paciente_ja_cadastrado_e_cadastrado_de_novo_a_cada_atendimento(self):
        a1 = self.pedido("L", "55566677733")
        cid = self.con.execute("SELECT cliente_id FROM atendimentos WHERE id=?", (a1,)).fetchone()["cliente_id"]
        a2 = atendimento(self.con, cid, "MC_FILA")
        robo = Fake({"usuario": "USR-L", "senha": "SEN-L", "qr": None})
        mc.processar_proxima(self.con, fabrica(robo))
        self.assertEqual(mc.enfileirar(self.con, a2), "pendente")
        self.con.commit()
        robo.acesso = {"usuario": "USR-L", "senha": "SEN-L2", "qr": None}   # a Medcloud devolve a senha da hora
        mc.processar_proxima(self.con, fabrica(robo))
        self.assertEqual((robo.chamadas, len(robo.estudos)), (2, 2))   # um cadastro e um estudo para cada atendimento
        self.assertEqual(self.fila(a2)["estado"], "OK")
        self.assertEqual(mc.status_atendimento(self.con, a2)["senha"], "SEN-L2")
        self.assertEqual(mc.status_atendimento(self.con, a1)["senha"], "SEN-L")   # a ficha antiga mantém a senha antiga

    def test_cliente_sem_data_de_nascimento_vai_direto_para_erro(self):
        at = atendimento(self.con, cliente(self.con, "M", cpf="55566677744", data_nasc=""), "MC_FILA")
        mc.enfileirar(self.con, at)
        self.con.commit()
        robo = Fake({"usuario": "X", "senha": "Y", "qr": None})
        mc.processar_proxima(self.con, fabrica(robo))
        self.assertEqual(self.fila(at)["estado"], "ERRO")
        self.assertIn("data de nascimento", self.fila(at)["erro"])
        self.assertEqual((robo.chamadas, len(robo.estudos)), (0, 0))

    def test_fila_vazia_devolve_falso(self):
        self.assertFalse(mc.processar_proxima(self.con, fabrica(Fake({"usuario": "a", "senha": "b"}))))

    def test_testar_conexao_so_faz_login(self):
        class RoboLogin(Fake):
            def __init__(self, ok):
                super().__init__()
                self.ok = ok
                self.entrou = False

            def entrar(self):
                self.entrou = True
                if not self.ok:
                    raise Exception("Login recusado pela Medcloud")

            def criar_acesso(self, *a):
                raise AssertionError("testar_conexao não cria cadastro")

        ok = RoboLogin(True)
        self.assertEqual(mc.testar_conexao("u", "s", "https://x", criar_robo=lambda l, s, u: ok), (True, "Login realizado na Medcloud."))
        self.assertTrue(ok.fechado)
        ruim = RoboLogin(False)
        self.assertEqual(mc.testar_conexao("u", "s", "https://x", criar_robo=lambda l, s, u: ruim),
                         (False, "Login recusado pela Medcloud"))


class MigracaoTestes(Base):
    def test_coluna_convenios_medcloud_existe_com_padrao_zero(self):
        con = conexao(self.app)
        try:
            colunas = {r[1]: r for r in con.execute("PRAGMA table_info(convenios)")}
            self.assertIn("medcloud", colunas)
            con.execute("INSERT INTO convenios (nome, gera_caixa, ativo) VALUES ('MC_PADRAO',0,1)")
            self.assertEqual(con.execute("SELECT medcloud FROM convenios WHERE nome='MC_PADRAO'").fetchone()[0], 0)
            tabelas = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertTrue({"medcloud_acessos", "medcloud_fila"} <= tabelas)
        finally:
            con.close()


class FluxoTelasTestes(Base):
    """Tela da gerência, lançamento de atendimento, fila e impressão com o protocolo (robô falso; nada sai da máquina)."""

    def setUp(self):
        self.con = conexao(self.app)
        self.addCleanup(self.con.close)
        limpar_fila(self.con)
        self.con.execute("UPDATE convenios SET medcloud=0")
        self.con.execute("DELETE FROM config WHERE chave LIKE 'medcloud_%'")
        self.con.commit()

    def _lancar(self, c, cid, conv, exame="MIBI"):
        r = self.post(c, "/atendimentos/novo", {"cliente_id": cid, "data": "2026-11-15", "exame": exame, "medico": "DR TESTE",
                                                "convenio": conv, "medicamentos": "NÃO SE APLICA", "exame_anterior": "NÃO INFORMADO",
                                                "manual": "1"})
        self.assertEqual(r.status_code, 302, r.get_data(as_text=True)[:500])
        return int(r.headers["Location"].split("/atendimentos/")[1].split("/")[0])

    def test_pagina_exige_gerencia_e_nunca_mostra_a_senha(self):
        self.criar_usuario("RECEP", ["atendimentos"])
        negado = self.cliente("RECEP", "senha123").get("/medcloud")
        self.assertEqual(negado.status_code, 302)   # sem o módulo "gerencia" o sistema redireciona e não mostra a tela
        self.assertNotIn("/medcloud", negado.headers["Location"])
        c = self.cliente()
        self.post(c, "/medcloud", {"acao": "salvar", "ativo": "1", "login": "op@clinica", "senha": "senha-secreta-xyz"})
        pagina = c.get("/medcloud").get_data(as_text=True)
        self.assertEqual(c.get("/medcloud").status_code, 200)
        self.assertNotIn("senha-secreta-xyz", pagina)
        self.assertIn("op@clinica", pagina)
        guardada = self.con.execute("SELECT valor FROM config WHERE chave='medcloud_senha'").fetchone()["valor"]
        self.assertNotIn("senha-secreta-xyz", guardada)
        self.assertEqual(mc.decifrar(guardada), "senha-secreta-xyz")

    def test_senha_em_branco_mantem_e_nova_troca(self):
        c = self.cliente()
        self.post(c, "/medcloud", {"acao": "salvar", "ativo": "1", "login": "a", "senha": "um"})
        self.post(c, "/medcloud", {"acao": "salvar", "ativo": "1", "login": "b", "senha": ""})
        cfg = {r["chave"]: r["valor"] for r in self.con.execute("SELECT chave, valor FROM config WHERE chave LIKE 'medcloud_%'")}
        self.assertEqual(cfg["medcloud_login"], "b")
        self.assertEqual(mc.decifrar(cfg["medcloud_senha"]), "um")
        self.post(c, "/medcloud", {"acao": "salvar", "ativo": "1", "login": "b", "senha": "dois"})
        self.assertEqual(mc.decifrar(self.con.execute("SELECT valor FROM config WHERE chave='medcloud_senha'").fetchone()["valor"]), "dois")

    def test_escolha_dos_convenios_e_desligar(self):
        convenio(self.con, "CONV A", 0)
        convenio(self.con, "CONV B", 0)
        ida = self.con.execute("SELECT id FROM convenios WHERE nome='CONV A'").fetchone()["id"]
        c = self.cliente()
        self.post(c, "/medcloud", {"acao": "salvar", "ativo": "1", "login": "a", "senha": "x", "convenio": [str(ida)]})
        self.assertTrue(mc.convenio_envia(self.con, "conv a"))
        self.assertFalse(mc.convenio_envia(self.con, "CONV B"))
        self.post(c, "/medcloud", {"acao": "salvar", "login": "a"})   # sem "ativo" e sem convênios
        self.assertFalse(mc.ativo(self.con))
        self.assertFalse(mc.convenio_envia(self.con, "CONV A"))

    def test_atendimento_de_convenio_marcado_entra_na_fila_e_imprime_o_protocolo(self):
        convenio(self.con, "CONV MC", 1)
        configurar(self.con)
        cid = cliente(self.con, "MARIA TESTE", cpf="123.456.789-09")
        c = self.cliente()
        aid = self._lancar(c, cid, "CONV MC")
        fila = self.con.execute("SELECT estado FROM medcloud_fila WHERE atendimento_id=?", (aid,)).fetchone()
        self.assertEqual(fila["estado"], "PENDENTE")
        # pendente: o lançamento passa pela tela de carregamento; reimprimir abre a ficha direto (sem protocolo ainda, sem fila nova)
        self.assertIn("Gerando o acesso do paciente", c.get(f"/atendimentos/{aid}/medcloud/aguarde").get_data(as_text=True))
        r = c.get(f"/atendimentos/{aid}/imprimir")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("Acesso ao portal de exames", r.get_data(as_text=True))
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM medcloud_fila WHERE atendimento_id=?", (aid,)).fetchone()[0], 1)
        self.assertEqual(c.get(f"/atendimentos/{aid}/medcloud/status").get_json(),
                         {"estado": "pendente", "fase": "Na fila", "erro": None, "tentativas": 0, "tem_acesso": False})
        robo = Fake(acesso={"usuario": "12345678909", "senha": "Abc123xyz", "qr": "data:image/png;base64,AAAA"})
        self.assertTrue(mc.processar_proxima(self.con, fabrica(robo)))
        pagina = c.get(f"/atendimentos/{aid}/imprimir").get_data(as_text=True)
        self.assertIn("Acesso ao portal de exames", pagina)
        self.assertIn("12345678909", pagina)
        self.assertIn("Abc123xyz", pagina)
        self.assertIn("data:image/png;base64,AAAA", pagina)
        # folha personalizada: logo e dados da clínica, e a data de entrega do laudo é só uma linha em branco (preenchida à mão)
        folha = pagina[pagina.index('data-ficha="medcloud"'):]
        self.assertIn("fichas/image1.jpeg", folha)
        self.assertIn("Data de entrega do laudo", folha)
        self.assertIn('class="mp-data-linha"', folha)
        self.assertNotIn("<input", folha)
        self.assertEqual(c.get(f"/atendimentos/{aid}/medcloud/status").get_json(),
                         {"estado": "pronto", "fase": None, "erro": None, "tentativas": None, "tem_acesso": True})
        # terminou: a tela de carregamento manda direto para as fichas
        self.assertEqual(c.get(f"/atendimentos/{aid}/medcloud/aguarde").status_code, 302)

    def test_robo_grava_a_etapa_em_que_esta(self):
        convenio(self.con, "CONV FASE", 1)
        configurar(self.con)
        cid = cliente(self.con, "ETAPA TESTE", cpf="22233344455")
        aid = atendimento(self.con, cid, "CONV FASE")
        mc.enfileirar(self.con, aid)
        self.con.commit()
        etapas = []

        class Comeu(Fake):
            def criar_acesso(self_, nome, identificador, cidade, uf):
                self_.progresso("Entrando na Medcloud")
                etapas.append(self.con.execute("SELECT fase FROM medcloud_fila WHERE atendimento_id=?", (aid,)).fetchone()["fase"])
                return {"usuario": identificador, "senha": "x1", "qr": None}

        mc.processar_proxima(self.con, fabrica(Comeu()))
        self.assertEqual(etapas, ["Entrando na Medcloud"])

    def test_convenio_nao_marcado_ou_funcao_desligada_nao_envia(self):
        convenio(self.con, "CONV SEM", 0)
        configurar(self.con)
        cid = cliente(self.con, "JOAO TESTE", cpf="98765432100")
        c = self.cliente()
        aid = self._lancar(c, cid, "CONV SEM")
        self.assertIsNone(self.con.execute("SELECT 1 FROM medcloud_fila WHERE atendimento_id=?", (aid,)).fetchone())
        self.assertNotIn("Acesso ao portal de exames", c.get(f"/atendimentos/{aid}/imprimir").get_data(as_text=True))
        convenio(self.con, "CONV SEM", 1)
        configurar(self.con, ativo=False)
        aid2 = self._lancar(c, cid, "CONV SEM")
        self.assertIsNone(self.con.execute("SELECT 1 FROM medcloud_fila WHERE atendimento_id=?", (aid2,)).fetchone())

    def test_erro_no_estudo_mostra_mensagem_e_tentar_de_novo_e_so_entao_traz_o_protocolo(self):
        convenio(self.con, "CONV MC", 1)
        configurar(self.con)
        cid = cliente(self.con, "ANA TESTE", cpf="11122233344")
        c = self.cliente()
        a1 = self._lancar(c, cid, "CONV MC")
        falha = Fake({"usuario": "11122233344", "senha": "s1", "qr": None}, erro_estudo=Exception("A Medcloud não confirmou a criação do estudo"))
        for _ in range(3):
            mc.processar_proxima(self.con, fabrica(falha))
        # erro: a tela de carregamento do lançamento mostra o erro e o "Tentar de novo"
        tela = c.get(f"/atendimentos/{a1}/medcloud/aguarde").get_data(as_text=True)
        self.assertIn("Tentar de novo", tela)
        self.assertEqual(c.get(f"/atendimentos/{a1}/medcloud/status").get_json()["erro"], "A Medcloud não confirmou a criação do estudo")
        r = self.post(c, f"/atendimentos/{a1}/medcloud/tentar")
        self.assertIn(f"/atendimentos/{a1}/medcloud/aguarde", r.headers["Location"])   # volta para a tela de carregamento
        self.assertEqual(self.con.execute("SELECT estado FROM medcloud_fila WHERE atendimento_id=?", (a1,)).fetchone()["estado"], "PENDENTE")
        falha.erro_estudo = None
        mc.processar_proxima(self.con, fabrica(falha))
        self.assertIn("Acesso ao portal de exames", c.get(f"/atendimentos/{a1}/imprimir").get_data(as_text=True))
        # paciente já cadastrado: o segundo atendimento cadastra de novo (senha da hora) e gera outro estudo
        a2 = self._lancar(c, cid, "CONV MC")
        self.assertEqual(self.con.execute("SELECT estado FROM medcloud_fila WHERE atendimento_id=?", (a2,)).fetchone()["estado"], "PENDENTE")
        mc.processar_proxima(self.con, fabrica(falha))
        self.assertIn("Acesso ao portal de exames", c.get(f"/atendimentos/{a2}/imprimir").get_data(as_text=True))
        self.assertEqual(falha.chamadas, 2)
        self.assertEqual(len(falha.estudos), 5)   # 3 falhas + 1 sucesso do primeiro atendimento + 1 do segundo


class SemEstudoTestes(Base):
    """Estudo não gerado: a ficha não abre sozinha; a pessoa escolhe entre tentar de novo e imprimir sem o estudo."""

    def setUp(self):
        self.con = conexao(self.app)
        self.addCleanup(self.con.close)
        limpar_fila(self.con)
        convenio(self.con, "CONV SE", 1)
        configurar(self.con)

    def _lancar(self, c, cid):
        r = self.post(c, "/atendimentos/novo", {"cliente_id": cid, "data": "2026-11-15", "exame": "MIBI", "medico": "DR TESTE",
                                                "convenio": "CONV SE", "medicamentos": "NÃO SE APLICA",
                                                "exame_anterior": "NÃO INFORMADO", "manual": "1"})
        self.assertEqual(r.status_code, 302)
        return int(r.headers["Location"].split("/atendimentos/")[1].split("/")[0]), r.headers["Location"]

    def _falhar_estudo(self, cid_acesso=True):
        robo = Fake({"usuario": "12312312312", "senha": "SenhaSE1", "qr": None},
                    erro=None if cid_acesso else Exception("Login recusado pela Medcloud"),
                    erro_estudo=Exception("A Medcloud não confirmou a criação do estudo"))
        for _ in range(3):
            mc.processar_proxima(self.con, fabrica(robo))
        return robo

    def test_sem_estudo_imprime_com_o_protocolo_quando_o_paciente_tem_acesso(self):
        cid = cliente(self.con, "PACIENTE SE", cpf="12312312312")
        c = self.cliente()
        aid, _ = self._lancar(c, cid)
        self._falhar_estudo()
        st = c.get(f"/atendimentos/{aid}/medcloud/status").get_json()
        self.assertEqual((st["estado"], st["tem_acesso"]), ("erro", True))
        tela = c.get(f"/atendimentos/{aid}/medcloud/aguarde").get_data(as_text=True)
        self.assertIn("Tentar de novo", tela)
        self.assertIn("Imprimir sem o estudo", tela)
        # escolhe imprimir sem o estudo: já imprime, COM o protocolo de acesso
        r = self.post(c, f"/atendimentos/{aid}/medcloud/sem-estudo", {"qs": "novo=1"})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers["Location"].endswith(f"/atendimentos/{aid}/imprimir?novo=1"))
        pagina = c.get(r.headers["Location"]).get_data(as_text=True)
        self.assertIn("Acesso ao portal de exames", pagina)
        self.assertIn("12312312312", pagina)
        self.assertIn("SenhaSE1", pagina)
        self.assertIn("sem o estudo", pagina)
        self.assertEqual(self.con.execute("SELECT estado FROM medcloud_fila WHERE atendimento_id=?", (aid,)).fetchone()["estado"], "SEM_ESTUDO")
        self.assertEqual(c.get(f"/atendimentos/{aid}/medcloud/aguarde").status_code, 302)   # a escolha vale: sem nova espera
        # depois ainda dá para gerar o estudo: volta para a fila
        r = self.post(c, f"/atendimentos/{aid}/medcloud/tentar")
        self.assertIn("/medcloud/aguarde", r.headers["Location"])
        self.assertEqual(self.con.execute("SELECT estado FROM medcloud_fila WHERE atendimento_id=?", (aid,)).fetchone()["estado"], "PENDENTE")

    def test_sem_estudo_e_sem_acesso_imprime_sem_o_protocolo(self):
        cid = cliente(self.con, "PACIENTE SE2", cpf="45645645645")
        c = self.cliente()
        aid, _ = self._lancar(c, cid)
        self._falhar_estudo(cid_acesso=False)
        st = c.get(f"/atendimentos/{aid}/medcloud/status").get_json()
        self.assertEqual((st["estado"], st["tem_acesso"]), ("erro", False))
        self.post(c, f"/atendimentos/{aid}/medcloud/sem-estudo", {"qs": ""})
        pagina = c.get(f"/atendimentos/{aid}/imprimir").get_data(as_text=True)
        self.assertNotIn("Acesso ao portal de exames", pagina)
        self.assertIn("sem o protocolo de acesso", pagina)

    def test_escolha_durante_a_espera_cancela_o_pedido_e_vale_mesmo_se_o_robo_terminar(self):
        cid = cliente(self.con, "PACIENTE SE3", cpf="78978978978")
        c = self.cliente()
        aid, _ = self._lancar(c, cid)
        robo = Fake({"usuario": "78978978978", "senha": "SenhaSE3", "qr": None})

        class DemoraEEscolhe(Fake):
            def criar_estudo(self_, nome, nascimento, data_estudo, exame):
                self.post(c, f"/atendimentos/{aid}/medcloud/sem-estudo", {"qs": ""})   # a pessoa clica no meio do processo
                return "5555"

        robo = DemoraEEscolhe({"usuario": "78978978978", "senha": "SenhaSE3", "qr": None})
        mc.processar_proxima(self.con, fabrica(robo))
        self.assertEqual(self.con.execute("SELECT estado FROM medcloud_fila WHERE atendimento_id=?", (aid,)).fetchone()["estado"], "SEM_ESTUDO")
        self.assertEqual(c.get(f"/atendimentos/{aid}/medcloud/status").get_json()["estado"], "sem_estudo")

    def test_nao_aceita_escolha_para_pedido_ja_concluido(self):
        cid = cliente(self.con, "PACIENTE SE4", cpf="32132132132")
        c = self.cliente()
        aid, _ = self._lancar(c, cid)
        mc.processar_proxima(self.con, fabrica(Fake({"usuario": "32132132132", "senha": "s", "qr": None})))
        self.post(c, f"/atendimentos/{aid}/medcloud/sem-estudo", {"qs": ""})
        self.assertEqual(self.con.execute("SELECT estado FROM medcloud_fila WHERE atendimento_id=?", (aid,)).fetchone()["estado"], "OK")


class ObterAcessoTestes(Base):
    """Paciente que já existe na Medcloud: reenvia os dados de login (senha nova, mesmo usuário). Só cadastra se não existe."""

    class Roteiro(mc.RoboPlaywright):
        def __init__(self, existe):
            super().__init__("l", "s", "https://medcloud.co")
            self.existe = existe
            self.chamadas = []

        def reenviar_acesso(self, nome, identificador):
            self.chamadas.append("reenviar")
            return {"usuario": identificador, "senha": "SENHA-REENVIADA", "qr": None} if self.existe else None

        def criar_acesso(self, nome, identificador, cidade, uf):
            self.chamadas.append("criar")
            return {"usuario": identificador, "senha": "SENHA-CADASTRO", "qr": None}

    def test_paciente_existente_so_reenvia_e_nao_cadastra(self):
        robo = self.Roteiro(existe=True)
        acesso = robo.obter_acesso("ELIAS SANTOS", "02156673608", "GV", "MG")
        self.assertEqual(robo.chamadas, ["reenviar"])
        self.assertEqual((acesso["usuario"], acesso["senha"]), ("02156673608", "SENHA-REENVIADA"))

    def test_paciente_novo_e_cadastrado_depois_de_nao_achar(self):
        robo = self.Roteiro(existe=False)
        acesso = robo.obter_acesso("PACIENTE NOVO", "11122233344", "GV", "MG")
        self.assertEqual(robo.chamadas, ["reenviar", "criar"])
        self.assertEqual(acesso["senha"], "SENHA-CADASTRO")


class SenhaPorAtendimentoTestes(Base):
    """Cada atendimento novo cadastra o paciente de novo e a ficha traz a senha da hora; a ficha antiga mantém a antiga."""

    def setUp(self):
        self.con = conexao(self.app)
        self.addCleanup(self.con.close)
        limpar_fila(self.con)
        convenio(self.con, "CONV SP", 1)
        configurar(self.con)

    def _acesso_antigo(self, cid, usuario, senha):
        self.con.execute("INSERT OR REPLACE INTO medcloud_acessos (cliente_id, usuario, senha, qr, criado_em) VALUES (?,?,?,?,?)",
                         (cid, usuario, mc.cifrar(senha), None, "2026-01-01"))
        self.con.commit()

    def _lancar(self, c, cid):
        r = self.post(c, "/atendimentos/novo", {"cliente_id": cid, "data": "2026-11-15", "exame": "MIBI", "medico": "DR X",
                                                "convenio": "CONV SP", "medicamentos": "NÃO SE APLICA",
                                                "exame_anterior": "NÃO INFORMADO", "manual": "1"})
        return int(r.headers["Location"].split("/atendimentos/")[1].split("/")[0])

    def test_acesso_antigo_do_cliente_nao_e_reaproveitado_no_atendimento_novo(self):
        cid = cliente(self.con, "ANTIGO SP", cpf="30030030030")
        self._acesso_antigo(cid, "30030030030", "SENHA-VELHA")
        c = self.cliente()
        aid = self._lancar(c, cid)
        # ainda sem o robô: a ficha NÃO pode mostrar a senha velha
        self.assertNotIn("SENHA-VELHA", c.get(f"/atendimentos/{aid}/imprimir").get_data(as_text=True))
        self.assertIsNone(mc.protocolo_do_atendimento(self.con, aid))
        robo = Fake({"usuario": "30030030030", "senha": "SENHA-NOVA", "qr": None})
        mc.processar_proxima(self.con, fabrica(robo))
        self.assertEqual(robo.chamadas, 1)   # cadastrou o paciente de novo, mesmo tendo acesso salvo
        pagina = c.get(f"/atendimentos/{aid}/imprimir").get_data(as_text=True)
        self.assertIn("SENHA-NOVA", pagina)
        self.assertNotIn("SENHA-VELHA", pagina)

    def test_ficha_antiga_mantem_a_senha_antiga_e_a_nova_traz_a_nova(self):
        cid = cliente(self.con, "DOIS SP", cpf="30030030041")
        c = self.cliente()
        a1 = self._lancar(c, cid)
        mc.processar_proxima(self.con, fabrica(Fake({"usuario": "30030030041", "senha": "SENHA-1", "qr": None})))
        a2 = self._lancar(c, cid)
        mc.processar_proxima(self.con, fabrica(Fake({"usuario": "30030030041", "senha": "SENHA-2", "qr": None})))
        p1 = c.get(f"/atendimentos/{a1}/imprimir").get_data(as_text=True)
        p2 = c.get(f"/atendimentos/{a2}/imprimir").get_data(as_text=True)
        self.assertIn("SENHA-1", p1)
        self.assertNotIn("SENHA-2", p1)
        self.assertIn("SENHA-2", p2)
        self.assertNotIn("SENHA-1", p2)

    def test_cadastro_que_falha_nao_cai_no_acesso_antigo(self):
        cid = cliente(self.con, "FALHA SP", cpf="30030030052")
        self._acesso_antigo(cid, "30030030052", "SENHA-VELHA2")
        c = self.cliente()
        aid = self._lancar(c, cid)
        falha = Fake(erro=Exception("Login recusado pela Medcloud"))
        for _ in range(3):
            mc.processar_proxima(self.con, fabrica(falha))
        st = c.get(f"/atendimentos/{aid}/medcloud/status").get_json()
        self.assertEqual((st["estado"], st["tem_acesso"]), ("erro", False))   # não oferece o protocolo velho
        self.post(c, f"/atendimentos/{aid}/medcloud/sem-estudo", {"qs": ""})
        pagina = c.get(f"/atendimentos/{aid}/imprimir").get_data(as_text=True)
        self.assertNotIn("SENHA-VELHA2", pagina)
        self.assertNotIn("Acesso ao portal de exames", pagina)

    def test_novo_estudo_tentado_de_novo_no_mesmo_atendimento_nao_recadastra(self):
        cid = cliente(self.con, "RETRY SP", cpf="30030030063")
        c = self.cliente()
        aid = self._lancar(c, cid)
        robo = Fake({"usuario": "30030030063", "senha": "SENHA-R", "qr": None}, erro_estudo=Exception("falhou"))
        for _ in range(3):
            mc.processar_proxima(self.con, fabrica(robo))
        self.assertEqual(robo.chamadas, 1)   # as 3 tentativas do estudo reaproveitam o cadastro deste atendimento
        mc.tentar_de_novo(self.con, aid)
        self.con.commit()
        robo.erro_estudo = None
        mc.processar_proxima(self.con, fabrica(robo))
        self.assertEqual(robo.chamadas, 1)
        self.assertIn("SENHA-R", c.get(f"/atendimentos/{aid}/imprimir").get_data(as_text=True))

    def test_pedido_antigo_sem_acesso_proprio_continua_usando_o_acesso_do_cliente(self):
        cid = cliente(self.con, "LEGADO SP", cpf="30030030074")
        self._acesso_antigo(cid, "30030030074", "SENHA-LEGADO")
        aid = atendimento(self.con, cid, "CONV SP")
        self.con.execute("INSERT INTO medcloud_fila (atendimento_id, cliente_id, estado, criado_em, atualizado_em) "
                         "VALUES (?,?,'OK','2026-02-01','2026-02-01')", (aid, cid))   # pedido de antes desta regra: acesso_modo NULL
        self.con.commit()
        self.assertEqual(mc.status_atendimento(self.con, aid)["senha"], "SENHA-LEGADO")


class EnvioArquivosTestes(Base):
    """Anexos e laudos do estudo: pendências por atendimento, envio pelo robô e marcação manual."""

    PDF = b"%PDF-1.1\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"

    def setUp(self):
        from app import medcloud_envios as env
        self.env = env
        self.con = conexao(self.app)
        self.addCleanup(self.con.close)
        limpar_fila(self.con)
        self.con.execute("DELETE FROM medcloud_envios")
        self.con.commit()
        convenio(self.con, "CONV EA", 1)
        configurar(self.con)

    def _estudo(self, nome="PACIENTE EA", cpf="40040040040", estudo="8001"):
        cid = cliente(self.con, nome, cpf=cpf)
        aid = atendimento(self.con, cid, "CONV EA")
        mc.enfileirar(self.con, aid)
        self.con.commit()
        mc.processar_proxima(self.con, fabrica(Fake({"usuario": cpf, "senha": "S1", "qr": None}, estudo=estudo)))
        return aid

    def _fila(self, aid):
        return self.con.execute("SELECT anexos_ok, laudos_ok FROM medcloud_fila WHERE atendimento_id=?", (aid,)).fetchone()

    class RoboArquivo(Fake):
        def __init__(self):
            super().__init__()
            self.enviados = []
            self.erro_envio = None

        def enviar_anexo(self, estudo_id, nome, conteudo, content_type=None):
            self.enviados.append((estudo_id, nome, conteudo, content_type))
            if self.erro_envio:
                raise self.erro_envio

    def test_estudo_criado_comeca_com_anexos_e_laudos_pendentes(self):
        aid = self._estudo()
        self.assertEqual(tuple(self._fila(aid)), (0, 0))
        item = self.env.pendencias(self.con)[0]
        self.assertEqual((item["cliente_nome"], item["anexos_pend"], item["laudos_pend"]), ("PACIENTE", True, True))
        self.assertEqual(self.env.resumo(self.con, [aid]), {aid: (True, True)})

    def test_atendimento_sem_estudo_nao_tem_pendencia_nem_aceita_arquivo(self):
        cid = cliente(self.con, "SEM ESTUDO", cpf="40040040051")
        aid = atendimento(self.con, cid, "CONV EA")
        self.assertEqual(self.env.pendencias(self.con, "todos"), [])
        with self.assertRaises(self.env.ErroEnvio):
            self.env.adicionar(self.con, aid, "ANEXO", "a.pdf", self.PDF, "ANA")

    def test_validacoes_do_arquivo(self):
        aid = self._estudo(cpf="40040040062")
        for tipo, nome, conteudo in (("OUTRO", "a.pdf", self.PDF), ("ANEXO", "a.exe", self.PDF), ("ANEXO", "a.pdf", b""),
                                     ("ANEXO", "a.pdf", b"x" * (self.env.MAX_BYTES + 1))):
            with self.assertRaises(self.env.ErroEnvio, msg=(tipo, nome)):
                self.env.adicionar(self.con, aid, tipo, nome, conteudo, "ANA")
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM medcloud_envios").fetchone()[0], 0)

    def test_nome_do_arquivo_e_higienizado(self):
        self.assertEqual(self.env.nome_seguro("C:\\pasta\\..\\laudo final?.pdf"), "laudo final_.pdf")
        self.assertEqual(self.env.nome_seguro("../../etc/passwd"), "passwd")
        self.assertEqual(self.env.nome_seguro(""), "arquivo")

    def test_robo_leva_o_arquivo_ao_estudo_e_a_pendencia_continua_ate_a_equipe_marcar(self):
        aid = self._estudo(cpf="40040040073", estudo="8003")
        eid = self.env.adicionar(self.con, aid, "ANEXO", "exame.pdf", self.PDF, "ANA")
        robo = self.RoboArquivo()
        self.assertTrue(self.env.processar_proximo(self.con, fabrica(robo)))
        self.assertEqual(robo.enviados, [("8003", "exame.pdf", self.PDF, "application/pdf")])
        e = self.con.execute("SELECT estado, enviado_em FROM medcloud_envios WHERE id=?", (eid,)).fetchone()
        self.assertEqual(e["estado"], "OK")
        self.assertTrue(e["enviado_em"])
        self.assertEqual(tuple(self._fila(aid)), (0, 0))   # enviar NÃO resolve a pendência
        self.assertFalse(self.env.processar_proximo(self.con, fabrica(robo)))   # nada mais na fila

    def test_envio_com_erro_tenta_tres_vezes_e_volta_pelo_tentar_de_novo(self):
        aid = self._estudo(cpf="40040040084", estudo="8004")
        eid = self.env.adicionar(self.con, aid, "LAUDO", "laudo.pdf", self.PDF, "ANA")
        robo = self.RoboArquivo()
        robo.erro_envio = Exception("A Medcloud recusou o arquivo laudo.pdf")
        for esperado in ("PENDENTE", "PENDENTE", "ERRO"):
            self.env.processar_proximo(self.con, fabrica(robo))
            self.assertEqual(self.con.execute("SELECT estado FROM medcloud_envios WHERE id=?", (eid,)).fetchone()["estado"], esperado)
        self.assertTrue(robo.fechado)
        self.assertFalse(self.env.processar_proximo(self.con, fabrica(robo)))
        self.assertTrue(self.env.tentar_de_novo(self.con, eid))
        robo.erro_envio = None
        self.env.processar_proximo(self.con, fabrica(robo))
        self.assertEqual(self.con.execute("SELECT estado FROM medcloud_envios WHERE id=?", (eid,)).fetchone()["estado"], "OK")
        self.assertFalse(self.env.tentar_de_novo(self.con, eid))

    def test_arquivo_sumido_do_banco_de_anexos_vai_para_erro_sem_chamar_o_robo(self):
        aid = self._estudo(cpf="40040040095", estudo="8005")
        eid = self.env.adicionar(self.con, aid, "ANEXO", "a.pdf", self.PDF, "ANA")
        self.con.execute("UPDATE medcloud_envios SET anexo_id=987654 WHERE id=?", (eid,))
        self.con.commit()
        robo = self.RoboArquivo()
        self.env.processar_proximo(self.con, fabrica(robo))
        self.assertEqual(robo.enviados, [])
        self.assertEqual(self.con.execute("SELECT estado FROM medcloud_envios WHERE id=?", (eid,)).fetchone()["estado"], "ERRO")

    def test_marcar_anexos_e_laudos_de_forma_independente(self):
        aid = self._estudo(cpf="40040040106", estudo="8006")
        self.env.marcar(self.con, aid, "ANEXO", "ANA")
        item = self.env.pendencias(self.con)[0]
        self.assertEqual((item["anexos_pend"], item["laudos_pend"], item["anexos_ok_por"]), (False, True, "ANA"))
        self.assertEqual(self.env.resumo(self.con, [aid]), {aid: (False, True)})
        self.env.marcar(self.con, aid, "LAUDO", "BIA")
        self.assertEqual(self.env.pendencias(self.con), [])                 # tudo resolvido: sai da lista de pendentes
        self.assertEqual(len(self.env.pendencias(self.con, "todos")), 1)    # mas continua em "todos"
        self.env.marcar(self.con, aid, "LAUDO", "BIA", feito=False)          # reabrir
        self.assertEqual(len(self.env.pendencias(self.con)), 1)

    def test_nao_marca_enquanto_ha_arquivo_esperando_o_robo(self):
        aid = self._estudo(cpf="40040040117", estudo="8007")
        self.env.adicionar(self.con, aid, "ANEXO", "a.pdf", self.PDF, "ANA")
        with self.assertRaises(self.env.ErroEnvio):
            self.env.marcar(self.con, aid, "ANEXO", "ANA")
        self.env.marcar(self.con, aid, "LAUDO", "ANA")   # o outro tipo não é afetado
        self.assertEqual(tuple(self._fila(aid)), (0, 1))

    def test_remover_so_o_que_ainda_nao_foi_enviado(self):
        aid = self._estudo(cpf="40040040128", estudo="8008")
        a = self.env.adicionar(self.con, aid, "ANEXO", "a.pdf", self.PDF, "ANA")
        b = self.env.adicionar(self.con, aid, "ANEXO", "b.pdf", self.PDF, "ANA")
        self.env.processar_proximo(self.con, fabrica(self.RoboArquivo()))   # envia o "a"
        self.assertFalse(self.env.remover(self.con, a))
        self.assertTrue(self.env.remover(self.con, b))
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM medcloud_envios").fetchone()[0], 1)

    def test_conteudo_fica_no_banco_de_anexos_e_volta_inteiro(self):
        aid = self._estudo(cpf="40040040139", estudo="8009")
        eid = self.env.adicionar(self.con, aid, "ANEXO", "a.pdf", self.PDF, "ANA")
        e = self.con.execute("SELECT * FROM medcloud_envios WHERE id=?", (eid,)).fetchone()
        self.assertIsNotNone(e["anexo_id"])
        self.assertIsNone(e["conteudo"])
        self.assertEqual(self.env.conteudo_do_envio(self.con, e), self.PDF)

    def test_tela_lista_envia_marca_e_baixa(self):
        import io
        aid = self._estudo(nome="TELA EA", cpf="40040040140", estudo="8010")
        c = self.cliente()
        pagina = c.get("/medcloud/pendencias").get_data(as_text=True)
        self.assertEqual(c.get("/medcloud/pendencias").status_code, 200)
        self.assertIn("Pendências Medcloud", pagina)
        self.assertIn("Enviar anexo", pagina)
        self.assertIn("Enviar laudo", pagina)
        r = self.post(c, f"/medcloud/pendencias/{aid}/enviar",
                      {"tipo": "LAUDO", "arquivo": (io.BytesIO(self.PDF), "laudo-tela.pdf")}, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 302)
        eid = self.con.execute("SELECT id FROM medcloud_envios WHERE arquivo_nome='laudo-tela.pdf'").fetchone()["id"]
        self.assertIn("laudo-tela.pdf", c.get("/medcloud/pendencias").get_data(as_text=True))
        baixou = c.get(f"/medcloud/envios/{eid}/arquivo")
        self.assertEqual((baixou.status_code, baixou.data), (200, self.PDF))
        self.post(c, f"/medcloud/pendencias/{aid}/marcar", {"tipo": "LAUDO"})   # ainda na fila: não deixa
        self.assertEqual(tuple(self._fila(aid)), (0, 0))
        self.env.processar_proximo(self.con, fabrica(self.RoboArquivo()))
        self.post(c, f"/medcloud/pendencias/{aid}/marcar", {"tipo": "LAUDO"})
        self.assertEqual(tuple(self._fila(aid)), (0, 1))
        self.assertEqual(c.get("/medcloud/pendencias/andamento").get_json()["assinatura"].split("|")[1], "0")

    def test_tela_recusa_arquivo_invalido_sem_criar_envio(self):
        import io
        aid = self._estudo(nome="RUIM EA", cpf="40040040151", estudo="8011")
        c = self.cliente()
        self.post(c, f"/medcloud/pendencias/{aid}/enviar", {"tipo": "ANEXO", "arquivo": (io.BytesIO(b"MZ"), "virus.exe")},
                  content_type="multipart/form-data")
        self.post(c, f"/medcloud/pendencias/{aid}/enviar", {"tipo": "ANEXO"}, content_type="multipart/form-data")   # sem arquivo
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM medcloud_envios").fetchone()[0], 0)

    def test_lista_de_atendimentos_avisa_a_pendencia(self):
        aid = self._estudo(nome="AVISO EA", cpf="40040040162", estudo="8012")
        c = self.cliente()
        pagina = c.get("/atendimentos?de=2026-01-01&ate=2026-12-31").get_data(as_text=True)
        self.assertIn("Medcloud: pendente anexos e laudos", pagina)
        self.env.marcar(self.con, aid, "ANEXO", "ANA")
        self.assertIn("Medcloud: pendente laudos", c.get("/atendimentos?de=2026-01-01&ate=2026-12-31").get_data(as_text=True))
        self.env.marcar(self.con, aid, "LAUDO", "ANA")
        self.assertNotIn("Medcloud: pendente", c.get("/atendimentos?de=2026-01-01&ate=2026-12-31").get_data(as_text=True))

    def test_menu_so_para_quem_tem_atendimentos_ou_laudos(self):
        from app import modulos
        self.assertEqual(modulos.modulo_do_endpoint("mpend.lista"), ("atendimentos", "laudos"))
        self.assertEqual(modulos.modulo_do_endpoint("mpend.enviar"), ("atendimentos", "laudos"))

    # ---------------------------------------------------- arquivo enviado sai do banco de anexos; download vem da Medcloud
    def _anexos_do_envio(self):
        from app import anexos
        con = anexos.conectar(anexos.caminho_de(self.con))
        try:
            return con.execute("SELECT COUNT(*) FROM anexos WHERE origem='medcloud_envios'").fetchone()[0]
        finally:
            con.close()

    class RoboDownload(Fake):
        def __init__(self, conteudo=None, erro=None):
            super().__init__()
            self.conteudo, self.erro_download, self.baixados = conteudo, erro, []

        def baixar_anexo(self, estudo_id, nome):
            self.baixados.append((estudo_id, nome))
            if self.erro_download:
                raise self.erro_download
            return self.conteudo

    def test_depois_de_enviado_o_conteudo_sai_do_banco_de_anexos(self):
        aid = self._estudo(cpf="40040040201", estudo="8101")
        base = self._anexos_do_envio()
        eid = self.env.adicionar(self.con, aid, "ANEXO", "a.pdf", self.PDF, "ANA")
        self.assertEqual(self._anexos_do_envio(), base + 1)          # esperando o robô: fica guardado
        self.env.processar_proximo(self.con, fabrica(self.RoboArquivo()))
        e = self.con.execute("SELECT * FROM medcloud_envios WHERE id=?", (eid,)).fetchone()
        self.assertEqual((e["estado"], e["anexo_id"], e["conteudo"]), ("OK", None, None))
        self.assertTrue(e["local_apagado_em"])
        self.assertEqual((e["arquivo_nome"], e["tamanho"], e["sha256"] is not None), ("a.pdf", len(self.PDF), True))
        self.assertEqual(self._anexos_do_envio(), base)               # o conteúdo saiu do anexos.db

    def test_envio_com_erro_continua_guardado(self):
        aid = self._estudo(cpf="40040040212", estudo="8102")
        base = self._anexos_do_envio()
        eid = self.env.adicionar(self.con, aid, "LAUDO", "l.pdf", self.PDF, "ANA")
        robo = self.RoboArquivo()
        robo.erro_envio = Exception("falhou")
        for _ in range(3):
            self.env.processar_proximo(self.con, fabrica(robo))
        e = self.con.execute("SELECT estado, anexo_id FROM medcloud_envios WHERE id=?", (eid,)).fetchone()
        self.assertEqual(e["estado"], "ERRO")
        self.assertIsNotNone(e["anexo_id"])
        self.assertEqual(self._anexos_do_envio(), base + 1)

    def test_limpar_enviados_libera_os_antigos_e_remove_orfaos(self):
        from app import anexos
        aid = self._estudo(cpf="40040040223", estudo="8103")
        base = self._anexos_do_envio()
        eid = self.env.adicionar(self.con, aid, "ANEXO", "antigo.pdf", self.PDF, "ANA")
        # simula um envio feito antes da mudança: estado OK com o conteúdo ainda guardado
        self.con.execute("UPDATE medcloud_envios SET estado='OK', enviado_em='2026-01-01 10:00:00' WHERE id=?", (eid,))
        self.con.commit()
        orfao = anexos.gravar(anexos.caminho_de(self.con), "medcloud_envios", b"sobra")
        self.assertEqual(self.env.resumo_enviados(self.con), (1, len(self.PDF)))
        qtd, liberados = self.env.limpar_enviados(self.con)
        self.assertEqual((qtd, liberados), (1, len(self.PDF)))
        self.assertEqual(self._anexos_do_envio(), 0)                  # o antigo, o órfão e as sobras de outros testes saíram
        self.assertIsNone(anexos.ler(anexos.caminho_de(self.con), orfao))
        self.assertEqual(self.env.resumo_enviados(self.con), (0, 0))
        self.assertEqual(self.con.execute("SELECT arquivo_nome FROM medcloud_envios WHERE id=?", (eid,)).fetchone()[0], "antigo.pdf")

    def test_processar_download_grava_o_arquivo_temporario(self):
        import os
        aid = self._estudo(cpf="40040040234", estudo="8104")
        eid = self.env.adicionar(self.con, aid, "ANEXO", "nuvem.pdf", self.PDF, "ANA")
        self.env.processar_proximo(self.con, fabrica(self.RoboArquivo()))
        self.assertFalse(self.env.processar_download(self.con, fabrica(self.RoboDownload(self.PDF))))   # ninguém pediu
        self.assertTrue(self.env.pedir_download(self.con, eid))
        robo = self.RoboDownload(self.PDF)
        self.assertTrue(self.env.processar_download(self.con, fabrica(robo)))
        self.assertEqual(robo.baixados, [("8104", "nuvem.pdf")])
        self.assertEqual(self.con.execute("SELECT download_estado FROM medcloud_envios WHERE id=?", (eid,)).fetchone()[0], "PRONTO")
        with open(self.env.arquivo_baixado(self.con, eid), "rb") as f:
            self.assertEqual(f.read(), self.PDF)
        os.remove(self.env.arquivo_baixado(self.con, eid))

    def test_processar_download_com_erro_e_vazio(self):
        aid = self._estudo(cpf="40040040245", estudo="8105")
        eid = self.env.adicionar(self.con, aid, "ANEXO", "x.pdf", self.PDF, "ANA")
        self.env.processar_proximo(self.con, fabrica(self.RoboArquivo()))
        for robo, trecho in ((self.RoboDownload(erro=Exception("não achei")), "não achei"), (self.RoboDownload(b""), "vazio")):
            self.env.pedir_download(self.con, eid)
            self.env.processar_download(self.con, fabrica(robo))
            r = self.con.execute("SELECT download_estado, download_erro FROM medcloud_envios WHERE id=?", (eid,)).fetchone()
            self.assertEqual(r["download_estado"], "ERRO")
            self.assertIn(trecho, r["download_erro"])

    def test_pedir_download_so_vale_para_enviado_sem_conteudo_local(self):
        aid = self._estudo(cpf="40040040256", estudo="8106")
        eid = self.env.adicionar(self.con, aid, "ANEXO", "y.pdf", self.PDF, "ANA")
        self.assertFalse(self.env.pedir_download(self.con, eid))     # ainda na fila e com conteúdo local

    def test_tela_baixa_da_medcloud_quando_o_arquivo_ja_saiu_do_banco(self):
        from unittest import mock
        from app import medcloud
        aid = self._estudo(nome="NUVEM EA", cpf="40040040267", estudo="8107")
        eid = self.env.adicionar(self.con, aid, "ANEXO", "nuvem.pdf", self.PDF, "ANA")
        self.env.processar_proximo(self.con, fabrica(self.RoboArquivo()))
        c = self.cliente()
        robo = self.RoboDownload(self.PDF)

        def acordar_e_processar():   # no sistema real o laço do robô faz isto em segundo plano
            con2 = conexao(self.app)
            try:
                self.env.processar_download(con2, fabrica(robo))
            finally:
                con2.close()
        with mock.patch.object(medcloud, "operando", return_value=True), mock.patch.object(medcloud, "acordar", acordar_e_processar):
            r = c.get(f"/medcloud/envios/{eid}/arquivo")
        self.assertEqual((r.status_code, r.data), (200, self.PDF))
        self.assertIn("nuvem.pdf", r.headers["Content-Disposition"])
        self.assertEqual(robo.baixados, [("8107", "nuvem.pdf")])
        self.assertFalse(__import__("os").path.exists(self.env.arquivo_baixado(self.con, eid)))   # temporário apagado
        self.assertIsNone(self.con.execute("SELECT download_estado FROM medcloud_envios WHERE id=?", (eid,)).fetchone()[0])

    def test_tela_baixar_com_robo_desligado_nao_pede_nada(self):
        from unittest import mock
        from app import medcloud
        aid = self._estudo(nome="OFF EA", cpf="40040040278", estudo="8108")
        eid = self.env.adicionar(self.con, aid, "ANEXO", "off.pdf", self.PDF, "ANA")
        self.env.processar_proximo(self.con, fabrica(self.RoboArquivo()))
        c = self.cliente()
        with mock.patch.object(medcloud, "operando", return_value=False):
            r = c.get(f"/medcloud/envios/{eid}/arquivo")
        self.assertEqual(r.status_code, 302)
        self.assertIsNone(self.con.execute("SELECT download_estado FROM medcloud_envios WHERE id=?", (eid,)).fetchone()[0])

    def test_tela_baixar_mostra_erro_do_robo_e_estouro_de_tempo(self):
        from unittest import mock
        from app import medcloud
        aid = self._estudo(nome="ERR EA", cpf="40040040289", estudo="8109")
        eid = self.env.adicionar(self.con, aid, "ANEXO", "err.pdf", self.PDF, "ANA")
        self.env.processar_proximo(self.con, fabrica(self.RoboArquivo()))
        c = self.cliente()

        def falhar():
            con2 = conexao(self.app)
            try:
                self.env.processar_download(con2, fabrica(self.RoboDownload(erro=Exception("sem permissão"))))
            finally:
                con2.close()
        with mock.patch.object(medcloud, "operando", return_value=True), mock.patch.object(medcloud, "acordar", falhar):
            r = c.get(f"/medcloud/envios/{eid}/arquivo", follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn("sem permissão", r.get_data(as_text=True))
        with mock.patch.object(medcloud, "operando", return_value=True), mock.patch.object(medcloud, "acordar", lambda: None), \
                mock.patch.object(self.env, "ESPERA_DOWNLOAD_S", 1):
            r = c.get(f"/medcloud/envios/{eid}/arquivo", follow_redirects=True)
        self.assertIn("demorou", r.get_data(as_text=True))
        self.assertIsNone(self.con.execute("SELECT download_estado FROM medcloud_envios WHERE id=?", (eid,)).fetchone()[0])

    def test_so_o_administrador_limpa_os_enviados(self):
        aid = self._estudo(nome="LIMPA EA", cpf="40040040290", estudo="8110")
        eid = self.env.adicionar(self.con, aid, "ANEXO", "l.pdf", self.PDF, "ANA")
        self.con.execute("UPDATE medcloud_envios SET estado='OK' WHERE id=?", (eid,))
        self.con.commit()
        c = self.cliente()          # admin dos testes
        self.assertIn("Liberar espaço", c.get("/medcloud/pendencias").get_data(as_text=True))
        self.post(c, "/medcloud/envios/limpar-enviados", {})
        self.assertEqual(self.env.resumo_enviados(self.con), (0, 0))
        self.assertNotIn("Liberar espaço", c.get("/medcloud/pendencias").get_data(as_text=True))

    # ---------------------------------------------------- laudos entregues na pendência levam o mapa de laudos junto
    def _exame_no_mapa(self, aid, situacao, paciente="MAPA EA"):
        cur = self.con.execute("INSERT INTO realizacoes (data, paciente, atendimento_id, laudo_situacao, laudo_atualizado_em) "
                               "VALUES ('2026-11-10', ?, ?, ?, '2026-11-10 10:00:00')", (paciente, aid, situacao))
        self.con.commit()
        return cur.lastrowid

    def _situacao(self, rid):
        return self.con.execute("SELECT laudo_situacao, laudo_entregue_por FROM realizacoes WHERE id=?", (rid,)).fetchone()

    def test_marcar_laudos_entregues_leva_o_mapa_para_entregue(self):
        aid = self._estudo(cpf="40040040301", estudo="8201")
        outro = self._estudo(nome="OUTRO EA", cpf="40040040312", estudo="8202")
        a = self._exame_no_mapa(aid, "LAUDANDO")
        b = self._exame_no_mapa(aid, "LIBERADO")
        de_outro = self._exame_no_mapa(outro, "LAUDANDO", "OUTRO EA")
        sem_mapa = self._exame_no_mapa(aid, None)
        self.assertEqual(self.env.marcar(self.con, aid, "ANEXO", "ANA"), 0)       # anexos não mexem no mapa
        self.assertEqual(self._situacao(a)["laudo_situacao"], "LAUDANDO")
        self.assertEqual(self.env.marcar(self.con, aid, "LAUDO", "BIA"), 2)
        for rid in (a, b):
            r = self._situacao(rid)
            self.assertEqual((r["laudo_situacao"], r["laudo_entregue_por"]), ("ENTREGUE", "BIA"))
        self.assertEqual(self._situacao(de_outro)["laudo_situacao"], "LAUDANDO")   # outro atendimento: intacto
        self.assertIsNone(self._situacao(sem_mapa)["laudo_situacao"])             # fora do mapa: continua fora

    def test_reabrir_laudos_nao_mexe_no_mapa_e_remarcar_nao_repete(self):
        aid = self._estudo(cpf="40040040323", estudo="8203")
        rid = self._exame_no_mapa(aid, "PROCESSANDO")
        self.env.marcar(self.con, aid, "LAUDO", "ANA")
        self.assertEqual(self.env.marcar(self.con, aid, "LAUDO", "ANA", feito=False), 0)
        self.assertEqual(self._situacao(rid)["laudo_situacao"], "ENTREGUE")
        self.assertEqual(self.env.marcar(self.con, aid, "LAUDO", "ANA"), 0)       # já estava entregue

    def test_tela_avisa_quantos_exames_foram_para_entregue(self):
        aid = self._estudo(nome="MAPA TELA", cpf="40040040334", estudo="8204")
        self._exame_no_mapa(aid, "LIBERADO", "MAPA TELA")
        c = self.cliente()
        r = self.post(c, f"/medcloud/pendencias/{aid}/marcar", {"tipo": "LAUDO"})
        self.assertEqual(r.status_code, 302)
        self.assertIn("1 exame(s) no mapa de laudos passaram para Entregue", c.get("/medcloud/pendencias").get_data(as_text=True))


class CompartilharTestes(Base):
    """Depois do estudo, o robô vincula o estudo ao acesso do paciente (Compartilhar), em segundo plano e sem travar a ficha."""

    def setUp(self):
        self.con = conexao(self.app)
        self.addCleanup(self.con.close)
        limpar_fila(self.con)
        convenio(self.con, "CONV CP", 1)
        configurar(self.con)

    def _criar_estudo(self, nome="PACIENTE CP", cpf="10120230344", estudo="7001"):
        cid = cliente(self.con, nome, cpf=cpf)
        aid = atendimento(self.con, cid, "CONV CP")
        mc.enfileirar(self.con, aid)
        self.con.commit()
        robo = Fake({"usuario": cpf, "senha": "SenhaCP1", "qr": None}, estudo=estudo)
        mc.processar_proxima(self.con, fabrica(robo))
        return aid, robo

    def _comp(self, aid):
        return self.con.execute("SELECT compartilhado, comp_tentativas, comp_erro FROM medcloud_fila WHERE atendimento_id=?",
                                (aid,)).fetchone()

    def test_estudo_criado_deixa_o_vinculo_pendente_e_a_ficha_ja_sai(self):
        aid, robo = self._criar_estudo()
        self.assertEqual(self._comp(aid)["compartilhado"], "PENDENTE")
        self.assertEqual(getattr(robo, "compartilhados", []), [])        # criar o estudo NÃO compartilha: fica para depois
        st = mc.status_atendimento(self.con, aid)
        self.assertEqual((st["estado"], st["senha"]), ("pronto", "SenhaCP1"))   # a ficha não espera o vínculo

    def test_vincula_o_estudo_ao_acesso_do_paciente(self):
        aid, robo = self._criar_estudo(nome="MARIA CP", cpf="10120230355", estudo="7002")
        self.assertTrue(mc.compartilhar_proximo(self.con, fabrica(robo)))
        self.assertEqual(robo.compartilhados, [("7002", "MARIA CP", "10120230355")])
        self.assertEqual(self._comp(aid)["compartilhado"], "OK")
        self.assertFalse(mc.compartilhar_proximo(self.con, fabrica(robo)))   # já feito: não compartilha de novo
        self.assertEqual(len(robo.compartilhados), 1)

    def test_erro_tenta_tres_vezes_e_nao_derruba_a_ficha(self):
        aid, robo = self._criar_estudo(nome="ERRO CP", cpf="10120230366", estudo="7003")
        robo.erro_compartilhar = Exception("A Medcloud não achou o paciente")
        mc.compartilhar_proximo(self.con, fabrica(robo))
        self.assertEqual(self._comp(aid)["compartilhado"], "PENDENTE")
        mc.compartilhar_proximo(self.con, fabrica(robo))
        mc.compartilhar_proximo(self.con, fabrica(robo))
        c = self._comp(aid)
        self.assertEqual((c["compartilhado"], c["comp_tentativas"]), ("ERRO", 3))
        self.assertIn("não achou", c["comp_erro"])
        self.assertEqual(mc.status_atendimento(self.con, aid)["estado"], "pronto")
        self.assertFalse(mc.compartilhar_proximo(self.con, fabrica(robo)))   # esgotou: só volta com "Tentar de novo"
        # a gerência recoloca na fila e dá certo
        self.assertTrue(mc.tentar_compartilhar_de_novo(self.con, aid))
        self.con.commit()
        robo.erro_compartilhar = None
        mc.compartilhar_proximo(self.con, fabrica(robo))
        self.assertEqual(self._comp(aid)["compartilhado"], "OK")
        self.assertFalse(mc.tentar_compartilhar_de_novo(self.con, aid))

    def test_sem_acesso_vai_direto_para_erro_sem_chamar_o_robo(self):
        aid, robo = self._criar_estudo(nome="SEM CP", cpf="10120230377", estudo="7004")
        self.con.execute("UPDATE medcloud_fila SET acesso_usuario=NULL, acesso_senha=NULL WHERE atendimento_id=?", (aid,))
        self.con.commit()
        mc.compartilhar_proximo(self.con, fabrica(robo))
        self.assertEqual(self._comp(aid)["compartilhado"], "ERRO")
        self.assertEqual(getattr(robo, "compartilhados", []), [])

    def test_estudo_que_falhou_nao_tem_vinculo(self):
        cid = cliente(self.con, "FALHA CP", cpf="10120230388")
        aid = atendimento(self.con, cid, "CONV CP")
        mc.enfileirar(self.con, aid)
        self.con.commit()
        falha = Fake({"usuario": "10120230388", "senha": "s", "qr": None}, erro_estudo=Exception("falhou"))
        for _ in range(3):
            mc.processar_proxima(self.con, fabrica(falha))
        self.assertIsNone(self._comp(aid)["compartilhado"])
        self.assertFalse(mc.compartilhar_proximo(self.con, fabrica(falha)))

    def test_tela_da_gerencia_mostra_o_vinculo_e_recoloca_na_fila(self):
        aid, robo = self._criar_estudo(nome="TELA CP", cpf="10120230399", estudo="7005")
        robo.erro_compartilhar = Exception("sem sugestão")
        for _ in range(3):
            mc.compartilhar_proximo(self.con, fabrica(robo))
        c = self.cliente()
        pagina = c.get("/medcloud").get_data(as_text=True)
        self.assertIn("estudo não vinculado ao paciente", pagina)
        self.assertIn("sem sugestão", pagina)
        self.post(c, "/medcloud", {"acao": "tentar", "atendimento_id": str(aid)})
        self.assertEqual(self._comp(aid)["compartilhado"], "PENDENTE")


class ReimpressaoTestes(Base):
    """Reimprimir a ficha NÃO cria estudo nem fila: só traz o protocolo que o paciente já tem."""

    def setUp(self):
        self.con = conexao(self.app)
        self.addCleanup(self.con.close)
        limpar_fila(self.con)
        convenio(self.con, "CONV RE", 1)
        convenio(self.con, "CONV NAO", 0)
        configurar(self.con)

    def _dar_acesso(self, cid, usuario="99988877766", senha="SenhaRE1"):
        self.con.execute("INSERT INTO medcloud_acessos (cliente_id, usuario, senha, qr, criado_em) VALUES (?,?,?,?,?)",
                         (cid, usuario, mc.cifrar(senha), None, "2026-01-01"))
        self.con.commit()

    def _fila(self, aid):
        return self.con.execute("SELECT COUNT(*) FROM medcloud_fila WHERE atendimento_id=?", (aid,)).fetchone()[0]

    def test_reimprimir_atendimento_antigo_traz_o_protocolo_sem_criar_fila(self):
        cid = cliente(self.con, "ANTIGO RE", cpf="99988877766")
        self._dar_acesso(cid)
        aid = atendimento(self.con, cid, "CONV RE")   # lançado antes: nunca passou pela fila
        c = self.cliente()
        r = c.get(f"/atendimentos/{aid}/imprimir")
        self.assertEqual(r.status_code, 200)
        pagina = r.get_data(as_text=True)
        self.assertIn("Acesso ao portal de exames", pagina)
        self.assertIn("99988877766", pagina)
        self.assertIn("SenhaRE1", pagina)
        self.assertEqual(self._fila(aid), 0)

    def test_reimprimir_nao_cria_estudo_nem_depende_do_horario_ou_da_funcao_ligada(self):
        cid = cliente(self.con, "ANTIGO RE2", cpf="99988877755")
        self._dar_acesso(cid, "99988877755", "SenhaRE2")
        aid = atendimento(self.con, cid, "CONV RE")
        configurar(self.con, ativo=False)
        c = self.cliente()
        pagina = c.get(f"/atendimentos/{aid}/imprimir").get_data(as_text=True)
        self.assertIn("SenhaRE2", pagina)
        self.assertEqual(self._fila(aid), 0)
        self.assertEqual(c.get(f"/atendimentos/{aid}/imprimir?novo=1").status_code, 200)

    def test_sem_acesso_nao_ha_protocolo_e_nada_entra_na_fila(self):
        cid = cliente(self.con, "SEM ACESSO RE", cpf="99988877744")
        aid = atendimento(self.con, cid, "CONV RE")
        c = self.cliente()
        r = c.get(f"/atendimentos/{aid}/imprimir")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("Acesso ao portal de exames", r.get_data(as_text=True))
        self.assertEqual(self._fila(aid), 0)
        self.assertIsNone(mc.protocolo_do_atendimento(self.con, aid))

    def test_convenio_nao_marcado_e_sem_fila_nao_traz_protocolo(self):
        cid = cliente(self.con, "OUTRO CONV RE", cpf="99988877733")
        self._dar_acesso(cid, "99988877733", "SenhaRE4")
        aid = atendimento(self.con, cid, "CONV NAO")
        self.assertIsNone(mc.protocolo_do_atendimento(self.con, aid))
        self.assertNotIn("Acesso ao portal de exames", self.cliente().get(f"/atendimentos/{aid}/imprimir").get_data(as_text=True))

    def test_protocolo_do_atendimento_usa_o_acesso_do_paciente(self):
        cid = cliente(self.con, "PROT RE", cpf="99988877722")
        self._dar_acesso(cid, "99988877722", "SenhaRE5")
        aid = atendimento(self.con, cid, "CONV RE")
        self.assertEqual(mc.protocolo_do_atendimento(self.con, aid), {"usuario": "99988877722", "senha": "SenhaRE5", "qr": None})
        self.assertIsNone(mc.protocolo_do_atendimento(self.con, 999999))


class InstantaneoTestes(Base):
    """O robô é acordado na hora e o lançamento espera o protocolo (robô falso, laço real em segundo plano)."""

    class RoboRapido:
        entradas = 0
        compartilhados = []
        fechado = False

        def __init__(self, login, senha, url):
            pass

        def entrar(self):
            type(self).entradas += 1

        def obter_acesso(self, nome, identificador, cidade, uf):
            return {"usuario": identificador, "senha": "Rapida123", "qr": None}

        def criar_estudo(self, nome, nascimento, data_estudo, exame):
            return "4242"

        def compartilhar_estudo(self, estudo_id, nome, usuario):
            type(self).compartilhados.append((estudo_id, nome, usuario))

        def fechar(self):
            self.fechado = True

    def setUp(self):
        self.con = conexao(self.app)
        self.addCleanup(self.con.close)
        limpar_fila(self.con)
        convenio(self.con, "CONV RAPIDO", 1)
        configurar(self.con)
        self.original = mc.RoboPlaywright
        mc.RoboPlaywright = self.RoboRapido
        self.RoboRapido.entradas = 0
        self.RoboRapido.compartilhados = []
        mc.iniciar(self.app.config["DATABASE"])
        self.addCleanup(self._desfazer)

    def _desfazer(self):
        mc.parar()
        mc.RoboPlaywright = self.original

    def test_lancamento_ja_traz_o_protocolo_sem_esperar_o_intervalo_da_fila(self):
        import time
        cid = cliente(self.con, "PACIENTE NA CLINICA", cpf="55566677788")
        c = self.cliente()
        inicio = time.monotonic()
        r = self.post(c, "/atendimentos/novo", {"cliente_id": cid, "data": "2026-11-15", "exame": "MIBI", "medico": "DR X",
                                                "convenio": "CONV RAPIDO", "medicamentos": "NÃO SE APLICA",
                                                "exame_anterior": "NÃO INFORMADO", "manual": "1"})
        gasto = time.monotonic() - inicio
        self.assertEqual(r.status_code, 302)
        self.assertIn("/medcloud/aguarde", r.headers["Location"])   # vai para a tela de carregamento
        aid = int(r.headers["Location"].split("/atendimentos/")[1].split("/")[0])
        for _ in range(40):   # o robô (laço real, acordado na hora) termina muito antes do intervalo da fila
            if c.get(f"/atendimentos/{aid}/medcloud/status").get_json()["estado"] == "pronto":
                break
            time.sleep(0.1)
        self.assertLess(time.monotonic() - inicio, mc.INTERVALO_FILA, "o robô esperou a conferência periódica da fila")
        # pronto: a tela de carregamento redireciona direto para as fichas, que já trazem o protocolo
        r2 = c.get(r.headers["Location"])
        self.assertEqual(r2.status_code, 302)
        pagina = c.get(r2.headers["Location"]).get_data(as_text=True)
        self.assertIn("Rapida123", pagina)
        self.assertIn("55566677788", pagina)
        # depois da ficha, o robô vincula o estudo ao paciente em segundo plano
        for _ in range(60):
            if self.RoboRapido.compartilhados:
                break
            time.sleep(0.1)
        self.assertEqual(self.RoboRapido.compartilhados, [("4242", "PACIENTE NA CLINICA", "55566677788")])
        self.assertNotIn("Gerando o acesso do paciente", pagina)

    def test_abrir_a_tela_de_lancar_esquenta_o_navegador(self):
        import time
        c = self.cliente()
        self.assertEqual(c.get("/atendimentos/novo").status_code, 200)
        for _ in range(30):
            if self.RoboRapido.entradas:
                break
            time.sleep(0.1)
        self.assertEqual(self.RoboRapido.entradas, 1)


class HorarioTestes(Base):
    """Horário de funcionamento: janela, dias da semana, virada da meia-noite e a tela da gerência."""

    def setUp(self):
        self.con = conexao(self.app)
        self.addCleanup(self.con.close)
        self.con.execute("DELETE FROM config WHERE chave LIKE 'medcloud_%'")
        self.con.commit()
        configurar(self.con)

    def _horario(self, ligado, inicio="05:50", fim="19:00", dias="0123456"):
        for k, v in (("medcloud_horario", "1" if ligado else "0"), ("medcloud_inicio", inicio), ("medcloud_fim", fim),
                     ("medcloud_dias", dias)):
            self.con.execute("INSERT INTO config (chave, valor) VALUES (?,?) ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor", (k, v))
        self.con.commit()

    def test_janela_do_dia(self):
        from datetime import datetime
        self._horario(True)
        seg = lambda h, m: datetime(2026, 11, 16, h, m)   # 16/11/2026 é segunda-feira
        self.assertFalse(mc.operando(self.con, seg(5, 49)))
        self.assertTrue(mc.operando(self.con, seg(5, 50)))
        self.assertTrue(mc.operando(self.con, seg(18, 59)))
        self.assertFalse(mc.operando(self.con, seg(19, 0)))

    def test_dias_da_semana(self):
        from datetime import datetime
        self._horario(True, dias="01234")   # segunda a sexta
        self.assertTrue(mc.operando(self.con, datetime(2026, 11, 20, 10, 0)))    # sexta
        self.assertFalse(mc.operando(self.con, datetime(2026, 11, 21, 10, 0)))   # sábado

    def test_janela_que_atravessa_a_meia_noite(self):
        from datetime import datetime
        self._horario(True, inicio="19:00", fim="05:00")
        self.assertTrue(mc.operando(self.con, datetime(2026, 11, 16, 23, 0)))
        self.assertTrue(mc.operando(self.con, datetime(2026, 11, 16, 4, 59)))
        self.assertFalse(mc.operando(self.con, datetime(2026, 11, 16, 12, 0)))

    def test_horario_desligado_ou_invalido_vale_o_dia_todo(self):
        from datetime import datetime
        self._horario(False)
        self.assertTrue(mc.operando(self.con, datetime(2026, 11, 16, 3, 0)))
        self._horario(True, inicio="25:99", fim="abc")
        self.assertTrue(mc.operando(self.con, datetime(2026, 11, 16, 3, 0)))

    def test_fora_do_horario_o_atendimento_nao_entra_na_fila(self):
        from datetime import datetime
        convenio(self.con, "CONV HOR", 1)
        cid = cliente(self.con, "FORA DO HORARIO", cpf="12312312312")
        aid = atendimento(self.con, cid, "CONV HOR")
        agora_ = datetime.now()
        # janela de 1 minuto que já passou: hoje, fora do horário
        passado = (agora_.hour * 60 + agora_.minute - 30) % 1440
        self._horario(True, inicio="%02d:%02d" % divmod(passado, 60), fim="%02d:%02d" % divmod((passado + 1) % 1440, 60))
        self.assertEqual(mc.enfileirar(self.con, aid), "desativado")
        self._horario(False)
        self.assertEqual(mc.enfileirar(self.con, aid), "pendente")

    def test_tela_salva_o_horario_e_recusa_dados_invalidos(self):
        c = self.cliente()
        self.post(c, "/medcloud", {"acao": "salvar", "ativo": "1", "login": "a", "senha": "x", "horario": "1",
                                   "inicio": "05:50", "fim": "19:00", "dia": ["0", "1", "2", "3", "4"]})
        cfg = lambda k: self.con.execute("SELECT valor FROM config WHERE chave=?", (k,)).fetchone()["valor"]
        self.assertEqual((cfg("medcloud_horario"), cfg("medcloud_inicio"), cfg("medcloud_fim"), cfg("medcloud_dias")),
                         ("1", "05:50", "19:00", "01234"))
        pagina = c.get("/medcloud").get_data(as_text=True)
        self.assertIn('value="05:50"', pagina)
        self.post(c, "/medcloud", {"acao": "salvar", "login": "a", "horario": "1", "inicio": "10:00", "fim": "10:00", "dia": ["1"]})
        self.assertEqual(cfg("medcloud_horario"), "0")   # início igual ao fim: recusado, horário desligado
        self.post(c, "/medcloud", {"acao": "salvar", "login": "a", "horario": "1", "inicio": "05:50", "fim": "19:00"})
        self.assertEqual(cfg("medcloud_horario"), "0")   # nenhum dia marcado: recusado


if __name__ == "__main__":
    unittest.main()
