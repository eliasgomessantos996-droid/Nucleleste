"""Suporte ao desenvolvedor, pasta dos backups, idade do cadastro nos exames realizados, PNT do Gálio e quadro de fichas recolhido."""
import json
import os
import shutil
import tempfile
import unittest
from datetime import date, datetime

from app import backup_pacote, fichas, suporte, suporte_docs
from app import db as dbmod
from tests.test_chat_blindagens import Base


class Suporte(Base):
    """Suporte ao desenvolvedor: formulários de sugestão e de correção de bug, caixa do desenvolvedor, pasta de aceitos e relatório."""

    def _dev(self):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            return con.execute("SELECT id, usuario, trocar_senha, admin, ativo, modulos FROM usuarios WHERE id=(SELECT CAST(valor AS INTEGER) FROM config WHERE chave=?)",
                               (suporte.CHAVE_CONFIG,)).fetchone()
        finally:
            con.close()

    def _itens(self, **filtro):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            sql, params = "SELECT * FROM suporte_itens", []
            if filtro:
                sql += " WHERE " + " AND ".join("%s=?" % k for k in filtro)
                params = list(filtro.values())
            return [dict(r) for r in con.execute(sql + " ORDER BY id", params)]
        finally:
            con.close()

    def _enviar(self, c, tipo, titulo, descricao, **extra):
        rota = "/suporte/bug" if tipo == "BUG" else "/suporte/sugestao"
        dados = {"titulo": titulo, "descricao": descricao}
        dados.update(extra)
        return self.post(c, rota, dados)

    def _dev_cliente(self):
        nome = "DEV_TESTE"
        if not self._usuario_existe(nome):
            self.criar_usuario(nome, ["suporte_dev"])
        return self.cliente(nome, "senha123")

    def _usuario_existe(self, nome):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            return con.execute("SELECT 1 FROM usuarios WHERE usuario=?", (nome,)).fetchone() is not None
        finally:
            con.close()

    # ------------------------------------------------------------ perfil
    def test_perfil_desenvolvedor_nasce_com_senha_provisoria_e_so_o_modulo_do_suporte(self):
        d = self._dev()
        self.assertEqual((d["usuario"], d["admin"], d["ativo"], d["trocar_senha"], json.loads(d["modulos"])), ("DESENVOLVEDOR", 1, 1, 1, ["suporte_dev"]))
        c = self.cliente("DESENVOLVEDOR", "123")                     # a senha padrão é 123 (a troca é pedida no primeiro acesso)
        self.assertEqual(c.get("/").status_code, 302)

    def test_perfil_com_o_nome_antigo_e_renomeado_sem_mexer_na_senha(self):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            d = self._dev()
            antes = con.execute("SELECT senha_hash FROM usuarios WHERE id=?", (d["id"],)).fetchone()[0]
            con.execute("UPDATE usuarios SET usuario=?, modulos='[]' WHERE id=?", (suporte.NOME_ANTIGO, d["id"]))
            con.commit()
            suporte.garantir(con)
            con.commit()
            r = con.execute("SELECT usuario, modulos, senha_hash FROM usuarios WHERE id=?", (d["id"],)).fetchone()
            self.assertEqual((r["usuario"], json.loads(r["modulos"]), r["senha_hash"]), ("DESENVOLVEDOR", ["suporte_dev"], antes))
            self.assertEqual(con.execute("SELECT COUNT(*) FROM usuarios WHERE usuario LIKE '%DESENVOLVEDOR%'").fetchone()[0], 1)
        finally:
            con.close()

    # ------------------------------------------------------------ usuários comuns
    def test_usuario_comum_ve_as_duas_opcoes_e_nao_ve_a_area_do_desenvolvedor(self):
        self.criar_usuario("SUP_A", ["atendimentos"])
        c = self.cliente("SUP_A", "senha123")
        self.assertIn("Suporte ao desenvolvedor", self.texto(c.get("/")))              # item no menu, logo abaixo de Início
        pagina = self.texto(c.get("/suporte"))
        self.assertIn("Sugestão", pagina)
        self.assertIn("Correção de bug", pagina)
        self.assertNotIn("Formulários recebidos", pagina)
        self.assertNotIn("Pasta de aceitos", pagina)
        self.assertEqual(c.get("/suporte/bug").status_code, 200)
        for rota in ("/suporte/recebidos", "/suporte/pasta", "/suporte/relatorio.pdf"):
            self.assertEqual(c.get(rota).status_code, 302, rota)                        # bloqueado mesmo digitando o endereço
        self.assertEqual(self.post(c, "/suporte/1/decidir", {"decisao": "aceitar"}).status_code, 302)

    def test_enviar_sugestao_e_bug_aparecem_em_seus_envios(self):
        self.criar_usuario("SUP_B", ["atendimentos"])
        c = self.cliente("SUP_B", "senha123")
        self._enviar(c, "SUGESTAO", "Exportar a agenda", "Gostaria de um botão para exportar a agenda do dia em Excel.", tela="Agenda de exames")
        self._enviar(c, "BUG", "Botão Receber não abre", "Na tela do caixa o botão Receber não faz nada.", passos="Abro o caixa e clico", gravidade="IMPEDE")
        itens = {i["tipo"]: i for i in self._itens(usuario="SUP_B")}
        self.assertEqual((itens["SUGESTAO"]["status"], itens["SUGESTAO"]["tela"], itens["SUGESTAO"]["gravidade"]), ("NOVA", "Agenda de exames", None))
        self.assertEqual((itens["BUG"]["gravidade"], itens["BUG"]["passos"]), ("IMPEDE", "Abro o caixa e clico"))
        self.assertIn("Exportar a agenda", self.texto(c.get("/suporte")))                  # cada tela mostra os envios do seu tipo
        self.assertNotIn("Botão Receber", self.texto(c.get("/suporte")))
        self.assertIn("Botão Receber não abre", self.texto(c.get("/suporte/bug")))

    def test_validacao_mantem_o_que_foi_digitado(self):
        self.criar_usuario("SUP_C", ["atendimentos"])
        c = self.cliente("SUP_C", "senha123")
        r = self._enviar(c, "BUG", "ab", "Descrição suficientemente longa para passar.")
        self.assertEqual(r.status_code, 200)                                                  # volta o formulário, não redireciona
        self.assertIn("Escreva um pouco mais", self.texto(r))
        self.assertIn("Descrição suficientemente longa", self.texto(r))
        self._enviar(c, "SUGESTAO", "Título bom", "curta")
        self.assertEqual(self._itens(usuario="SUP_C"), [])

    def test_gravidade_invalida_vira_atrapalha_e_sugestao_nao_guarda_gravidade(self):
        self.criar_usuario("SUP_D", ["atendimentos"])
        c = self.cliente("SUP_D", "senha123")
        self._enviar(c, "BUG", "Erro estranho", "Aparece um erro estranho quando salvo.", gravidade="QUALQUER")
        self._enviar(c, "SUGESTAO", "Ideia nova", "Uma ideia nova para a clínica toda.", gravidade="IMPEDE", passos="x")
        itens = {i["tipo"]: i for i in self._itens(usuario="SUP_D")}
        self.assertEqual(itens["BUG"]["gravidade"], "ATRAPALHA")
        self.assertEqual((itens["SUGESTAO"]["gravidade"], itens["SUGESTAO"]["passos"]), (None, None))

    def test_cada_pessoa_ve_so_os_proprios_envios(self):
        self.criar_usuario("SUP_E", ["atendimentos"])
        self.criar_usuario("SUP_F", ["atendimentos"])
        self._enviar(self.cliente("SUP_E", "senha123"), "SUGESTAO", "Segredo do E", "Uma sugestão que só o E deve enxergar.")
        self.assertNotIn("Segredo do E", self.texto(self.cliente("SUP_F", "senha123").get("/suporte")))

    # ------------------------------------------------------------ desenvolvedor
    def test_bugs_ficam_acima_das_sugestoes_e_os_mais_graves_primeiro(self):
        base = [{"id": 1, "tipo": "SUGESTAO", "gravidade": None, "criado_em": "2026-01-01 08:00:00"},
                {"id": 2, "tipo": "BUG", "gravidade": "PEQUENO", "criado_em": "2026-01-01 09:00:00"},
                {"id": 3, "tipo": "BUG", "gravidade": "IMPEDE", "criado_em": "2026-01-02 09:00:00"},
                {"id": 4, "tipo": "BUG", "gravidade": "IMPEDE", "criado_em": "2026-01-01 10:00:00"},
                {"id": 5, "tipo": "SUGESTAO", "gravidade": None, "criado_em": "2025-12-31 08:00:00"}]
        self.assertEqual([i["id"] for i in suporte._ordenar(base)], [4, 3, 2, 5, 1])

    def test_desenvolvedor_ve_todos_os_formularios_com_os_bugs_primeiro(self):
        self.criar_usuario("SUP_G", ["atendimentos"])
        c = self.cliente("SUP_G", "senha123")
        self._enviar(c, "SUGESTAO", "Sugestão do G", "Uma sugestão do G para a próxima versão.")
        self._enviar(c, "BUG", "Bug do G", "Um bug do G que atrapalha bastante.", gravidade="ATRAPALHA")
        dev = self._dev_cliente()
        pagina = self.texto(dev.get("/suporte/recebidos"))
        self.assertIn("Bug do G", pagina)
        self.assertIn("Sugestão do G", pagina)
        self.assertLess(pagina.index("Bug do G"), pagina.index("Sugestão do G"))             # bug acima da sugestão
        self.assertIn("Sim, aceitar", pagina)
        self.assertIn("Não aceitar", pagina)
        self.assertIn("Formulários recebidos", self.texto(dev.get("/suporte")))             # a aba extra só para ele
        self.assertIn("selo-suporte", self.texto(dev.get("/")))                             # e o contador no menu
        self.assertIn("Bug do G", self.texto(self.cliente().get("/suporte/recebidos")))      # o administrador também

    def test_aceitar_vai_para_a_pasta_e_recusar_fica_guardado(self):
        self.criar_usuario("SUP_H", ["atendimentos"])
        c = self.cliente("SUP_H", "senha123")
        self._enviar(c, "BUG", "Bug aceito H", "Um bug que vai ser aceito pelo desenvolvedor.", gravidade="IMPEDE")
        self._enviar(c, "SUGESTAO", "Ideia recusada H", "Uma ideia que não vai ser aceita agora.")
        ids = {i["tipo"]: i["id"] for i in self._itens(usuario="SUP_H")}
        dev = self._dev_cliente()
        self.post(dev, "/suporte/%d/decidir" % ids["BUG"], {"decisao": "aceitar"})
        self.post(dev, "/suporte/%d/decidir" % ids["SUGESTAO"], {"decisao": "recusar"})
        estado = {i["tipo"]: i["status"] for i in self._itens(usuario="SUP_H")}
        self.assertEqual(estado, {"BUG": "ACEITA", "SUGESTAO": "RECUSADA"})
        self.assertIn("Bug aceito H", self.texto(dev.get("/suporte/pasta")))
        self.assertNotIn("Ideia recusada H", self.texto(dev.get("/suporte/pasta")))
        self.assertNotIn("Ideia recusada H", self.texto(dev.get("/suporte/recebidos")).split("Não aceitos")[0])
        self.assertIn("Ideia recusada H", self.texto(dev.get("/suporte/recebidos?mostrar=recusados")))
        # mudar de ideia: aceitar o que foi recusado, e devolver um aceito para análise
        self.post(dev, "/suporte/%d/decidir" % ids["SUGESTAO"], {"decisao": "aceitar", "mostrar": "recusados"})
        self.post(dev, "/suporte/%d/situacao" % ids["BUG"], {"acao": "voltar"})
        estado = {i["tipo"]: i["status"] for i in self._itens(usuario="SUP_H")}
        self.assertEqual(estado, {"BUG": "NOVA", "SUGESTAO": "ACEITA"})
        # quem enviou vê a situação
        self.assertIn("Aceito", self.texto(c.get("/suporte")))

    def test_pasta_texto_didatico_aplicar_e_desfazer(self):
        self.criar_usuario("SUP_I", ["atendimentos"])
        c = self.cliente("SUP_I", "senha123")
        self._enviar(c, "SUGESTAO", "Pasta I", "Texto original do usuário I sobre a sugestão.")
        iid = self._itens(usuario="SUP_I")[0]["id"]
        dev = self._dev_cliente()
        self.post(dev, "/suporte/%d/decidir" % iid, {"decisao": "aceitar"})
        self.post(dev, "/suporte/%d/texto" % iid, {"texto": "Agora é possível exportar a agenda do dia em Excel, pelo botão novo."})
        self.assertEqual(self._itens(id=iid)[0]["texto_atualizacao"], "Agora é possível exportar a agenda do dia em Excel, pelo botão novo.")
        self.post(dev, "/suporte/%d/texto" % iid, {"texto": "Texto original do usuário I sobre a sugestão."})     # igual ao original: não guarda cópia
        self.assertIsNone(self._itens(id=iid)[0]["texto_atualizacao"])
        self.post(dev, "/suporte/%d/situacao" % iid, {"acao": "aplicada", "versao": "1.6.0"})
        i = self._itens(id=iid)[0]
        self.assertEqual((i["status"], i["versao"]), ("APLICADA", "1.6.0"))
        self.assertIn("Versão 1.6.0", self.texto(dev.get("/suporte/pasta")))
        self.assertIn("Entrou na versão 1.6.0", self.texto(c.get("/suporte")))             # o autor vê que entrou
        self.post(dev, "/suporte/%d/situacao" % iid, {"acao": "desfazer"})
        self.assertEqual(self._itens(id=iid)[0]["status"], "ACEITA")
        self.post(dev, "/suporte/aplicar-todas", {"versao": "1.6.1"})
        self.assertEqual(self._itens(id=iid)[0]["versao"], "1.6.1")

    def test_relatorio_pdf_da_proxima_atualizacao(self):
        self.criar_usuario("SUP_J", ["atendimentos"])
        c = self.cliente("SUP_J", "senha123")
        self._enviar(c, "BUG", "Bug relatório", "Um bug para entrar no relatório da atualização.", gravidade="ATRAPALHA")
        self._enviar(c, "SUGESTAO", "Sugestão relatório", "Uma sugestão para entrar no relatório da atualização.")
        dev = self._dev_cliente()
        for i in self._itens(usuario="SUP_J"):
            self.post(dev, "/suporte/%d/decidir" % i["id"], {"decisao": "aceitar"})
        r = dev.get("/suporte/relatorio.pdf")
        self.assertEqual((r.status_code, r.data[:4]), (200, b"%PDF"))
        self.assertIn("inline", r.headers.get("Content-Disposition", "inline"))
        baixar = dev.get("/suporte/relatorio.pdf?baixar=1")
        self.assertIn("attachment", baixar.headers["Content-Disposition"])
        # o gerador também funciona sem nenhum item
        self.assertEqual(suporte_docs.relatorio_pdf([], "CLÍNICA", "1.5.0")[:4], b"%PDF")

    def test_limite_de_envios_por_hora(self):
        self.criar_usuario("SUP_K", ["atendimentos"])
        c = self.cliente("SUP_K", "senha123")
        for n in range(suporte.MAX_POR_HORA + 2):
            self._enviar(c, "SUGESTAO", "Muitos envios %d" % n, "Uma sugestão repetida de número %d para testar." % n)
        self.assertEqual(len(self._itens(usuario="SUP_K")), suporte.MAX_POR_HORA)


class PastaDosBackups(Base):
    """O backup é sempre local; a pasta externa (Drive, rede) recebe uma cópia. O backup automático roda uma vez por dia."""

    def banco(self):
        return self.app.config["DATABASE"]

    def _config(self, chave, valor):
        con = dbmod.conectar(self.banco())
        try:
            con.execute("INSERT INTO config (chave, valor) VALUES (?,?) ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor", (chave, valor))
            con.commit()
        finally:
            con.close()

    # ------------------------------------------------------------ helpers (várias pastas de cópia)
    def _pastas(self, lista):
        self._config(backup_pacote.CHAVE_PASTAS, json.dumps(lista))
        self._config(backup_pacote.CHAVE_PASTA, "")

    def _valor(self, chave):
        con = dbmod.conectar(self.banco())
        try:
            r = con.execute("SELECT valor FROM config WHERE chave=?", (chave,)).fetchone()
            return r[0] if r else None
        finally:
            con.close()

    def _zerar_auto(self):
        chaves = (backup_pacote.CHAVE_AUTO_INICIO, backup_pacote.CHAVE_AUTO_FIM, backup_pacote.CHAVE_AUTO_MINUTOS, backup_pacote.CHAVE_AUTO_ULTIMO,
                  backup_pacote.CHAVE_AUTO_ARQUIVO, backup_pacote.CHAVE_AUTO_SUBSTITUIDOS, backup_pacote.CHAVE_AUTO_DATA)
        con = dbmod.conectar(self.banco())
        try:
            con.execute("DELETE FROM config WHERE chave IN (%s)" % ",".join("?" * len(chaves)), chaves)
            con.commit()
        finally:
            con.close()
        self._config(backup_pacote.CHAVE_AUTO, "1")

    def _auto_em(self, dia, hora, minuto):
        return backup_pacote.backup_automatico(self.banco(), datetime(2031, 3, dia, hora, minuto))

    def _limpar(self):
        """Sem pastas de cópia, sem situação guardada e com a rotina automática no padrão."""
        self._pastas([])
        self._config(backup_pacote.CHAVE_ESTADO, "{}")
        self._zerar_auto()

    def test_salva_a_pasta_externa_mesmo_sem_enxergar_a_pasta(self):
        self._limpar()
        inexistente = os.path.join(tempfile.gettempdir(), "nuc_pasta_externa_que_nao_existe_agora")
        adm = self.cliente()
        self.post(adm, "/backup/pasta-destino", {"pasta": '"%s"' % inexistente})   # aspas coladas do Explorador são retiradas
        estado = backup_pacote.estado_externa(self.banco())
        self.assertEqual([os.path.normpath(e["pasta"]) for e in estado], [os.path.normpath(inexistente)])
        pagina = self.texto(adm.get("/backup"))
        self.assertIn("Cópia em outras pastas", pagina)
        self.assertIn("Atrasada", pagina)
        self.post(adm, "/backup/pasta-destino/remover", {"pasta": inexistente})
        self.assertEqual(backup_pacote.estado_externa(self.banco()), [])
        self.assertIn("Desligada", self.texto(adm.get("/backup")))

    def test_recusa_caminho_incompleto_e_so_a_gestao_muda(self):
        self._limpar()
        adm = self.cliente()
        self.post(adm, "/backup/pasta-destino", {"pasta": ""})
        self.post(adm, "/backup/pasta-destino", {"pasta": "relativa/pasta"})
        self.assertEqual(backup_pacote.estado_externa(self.banco()), [])
        self.criar_usuario("BKP_A", ["backup"])
        c = self.cliente("BKP_A", "senha123")
        with tempfile.TemporaryDirectory() as pasta:
            self.post(c, "/backup/pasta-destino", {"pasta": pasta})
            self.assertEqual(backup_pacote.estado_externa(self.banco()), [])

    def test_backup_fica_local_e_a_copia_vai_para_a_pasta_externa(self):
        self._limpar()
        adm = self.cliente()
        with tempfile.TemporaryDirectory() as externa:
            self.post(adm, "/backup/pasta-destino", {"pasta": externa})
            self.post(adm, "/backup", {})                                   # faz o backup (e tenta copiar na hora)
            locais = backup_pacote.backups_locais(self.banco())
            self.assertTrue(locais)                                          # o backup é sempre local
            self.assertIn(locais[0], os.listdir(externa))                    # e foi copiado
            estado = backup_pacote.estado_externa(self.banco())
            self.assertEqual(len(estado), 1)
            self.assertTrue(estado[0]["em_dia"])
            self.assertEqual(estado[0]["ultimo"], locais[0])
            self.assertEqual(backup_pacote.sincronizar_externa(self.banco(), "teste"), [])   # nada novo para copiar
            self.assertIn("Em dia", self.texto(adm.get("/backup")))
            self.assertFalse([f for f in os.listdir(externa) if f.endswith(".parcial")])
        self._limpar()

    def test_falha_na_copia_registra_o_motivo_sem_quebrar_o_backup(self):
        self._limpar()
        adm = self.cliente()
        with tempfile.NamedTemporaryFile() as arquivo:
            ruim = os.path.join(arquivo.name, "dentro")                      # "pasta" dentro de um arquivo: impossível
            self.post(adm, "/backup/pasta-destino", {"pasta": ruim})
            self.post(adm, "/backup", {})
            self.assertTrue(backup_pacote.backups_locais(self.banco()))      # o backup local saiu do mesmo jeito
            self.assertIsNone(backup_pacote.sincronizar_externa(self.banco(), "bandeja"))
            estado = backup_pacote.estado_externa(self.banco())
            self.assertFalse(estado[0]["em_dia"])
            self.assertIn("bandeja", estado[0]["erro"])
            self.assertIn("bandeja", self.texto(adm.get("/backup")))
        self._limpar()

    def test_externa_nao_recebe_backups_com_mais_de_7_dias(self):
        self._limpar()
        self.post(self.cliente(), "/backup", {})
        with tempfile.TemporaryDirectory() as externa:
            self._pastas([externa])
            pasta_local = backup_pacote.pasta_padrao(self.banco())
            antigos = []
            for n in range(4):                                               # backups de 2020 na pasta local
                antigo = os.path.join(pasta_local, "BACKUP_01-01-2020_00-00-%02d.zip" % n)
                with open(antigo, "wb") as fh:
                    fh.write(b"x")
                os.utime(antigo, (1577836800 + n, 1577836800 + n))
                antigos.append(os.path.basename(antigo))
            copiados = backup_pacote.sincronizar_externa(self.banco())
            nomes = os.listdir(externa)
            for nome in antigos:
                self.assertNotIn(nome, nomes)                                # com mais de 7 dias: não vai para a externa
            self.assertIn(backup_pacote.backups_locais(self.banco())[0], nomes)   # o de hoje vai
            self.assertIsNotNone(copiados)
        self._limpar()

    def test_duas_pastas_recebem_a_copia_e_a_lista_mostra_a_origem(self):
        self._limpar()
        adm = self.cliente()
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            self.post(adm, "/backup/pasta-destino", {"pasta": a})
            self.post(adm, "/backup/pasta-destino", {"pasta": b})
            self.post(adm, "/backup", {})
            ultimo = backup_pacote.backups_locais(self.banco())[0]
            self.assertIn(ultimo, os.listdir(a))
            self.assertIn(ultimo, os.listdir(b))
            estado = backup_pacote.estado_externa(self.banco())
            self.assertEqual(sorted(os.path.normpath(e["pasta"]) for e in estado), sorted([os.path.normpath(a), os.path.normpath(b)]))
            self.assertTrue(all(e["em_dia"] for e in estado))
            pagina = self.texto(adm.get("/backup"))
            self.assertIn(ultimo, pagina)
            self.assertIn(os.path.normpath(b), pagina)     # a lista de backups mostra de qual pasta cada um vem
        self._limpar()

    def test_pasta_invalida_nao_impede_a_outra(self):
        self._limpar()
        with tempfile.TemporaryDirectory() as boa, tempfile.NamedTemporaryFile() as arquivo:
            ruim = os.path.join(arquivo.name, "dentro")
            self._pastas([ruim, boa])
            self.post(self.cliente(), "/backup", {})
            ultimo = backup_pacote.backups_locais(self.banco())[0]
            self.assertIn(ultimo, os.listdir(boa))                           # a pasta boa recebeu a cópia
            self.assertIsNotNone(backup_pacote.sincronizar_externa(self.banco(), "bandeja"))
            estado = {os.path.normpath(e["pasta"]): e for e in backup_pacote.estado_externa(self.banco())}
            self.assertIn("bandeja", estado[os.path.normpath(ruim)]["erro"])  # o erro fica só na pasta que falhou
            self.assertEqual(estado[os.path.normpath(boa)]["erro"], "")
            self.assertTrue(estado[os.path.normpath(boa)]["ok_em"])
        self._limpar()

    def test_dois_automaticos_no_mesmo_dia_geram_dois_arquivos_nas_duas_pastas(self):
        self._limpar()
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            self._pastas([a, b])
            primeiro = os.path.basename(self._auto_em(4, 8, 0))
            segundo = os.path.basename(self._auto_em(4, 8, 30))
            self.assertNotEqual(primeiro, segundo)
            self.assertIsNotNone(backup_pacote.sincronizar_externa(self.banco()))
            for pasta in (a, b):
                self.assertIn(primeiro, os.listdir(pasta))                  # o de 8h continua existindo
                self.assertIn(segundo, os.listdir(pasta))
        self._limpar()

    def test_reter_backups_apaga_so_os_antigos_e_guarda_os_3_mais_recentes(self):
        self._zerar_auto()
        pasta = backup_pacote.pasta_padrao(self.banco())
        os.makedirs(pasta, exist_ok=True)
        for f in os.listdir(pasta):                                          # começa sem BACKUP_ de outros testes
            if f.startswith("BACKUP_"):
                os.remove(os.path.join(pasta, f))
        def cria(dia):
            nome = "BACKUP_%02d-03-2031_08-00-00.zip" % dia
            caminho = os.path.join(pasta, nome)
            with open(caminho, "wb") as fh:
                fh.write(b"x")
            t = datetime(2031, 3, dia, 8, 0).timestamp()
            os.utime(caminho, (t, t))
            return nome
        antigos = [cria(d) for d in (1, 2, 3, 4, 5, 10)]                     # hoje = 20/03: com mais de 7 dias
        recentes = [cria(d) for d in (14, 16, 18, 19)]                       # de 1 a 6 dias
        apagados = backup_pacote.reter_backups(self.banco(), hoje=date(2031, 3, 20))
        # os 3 mais recentes (19, 18, 16) nunca saem; 14 fica por ter menos de 7 dias; os 6 antigos (incluindo 10/03) saem
        self.assertEqual(apagados, 6)
        restantes = sorted(n for n in os.listdir(pasta) if n.startswith("BACKUP_"))
        self.assertEqual(restantes, sorted(recentes))
        for f in os.listdir(pasta):
            if f.startswith("BACKUP_"):
                os.remove(os.path.join(pasta, f))
        self._limpar()

    def test_sincronizar_externa_apaga_os_com_mais_de_7_dias_e_guarda_os_3_mais_recentes(self):
        self._zerar_auto()
        with tempfile.TemporaryDirectory() as externa:
            self._pastas([externa])
            for dia in (1, 2, 3, 4, 5, 19):                                  # hoje = 20/03/2031
                caminho = os.path.join(externa, "BACKUP_%02d-03-2031_08-00-00.zip" % dia)
                with open(caminho, "wb") as fh:
                    fh.write(b"x")
                t = datetime(2031, 3, dia, 8, 0).timestamp()
                os.utime(caminho, (t, t))
            outro = os.path.join(externa, "outro_arquivo.txt")
            with open(outro, "w", encoding="utf-8") as fh:
                fh.write("x")
            backup_pacote.sincronizar_externa(self.banco(), hoje=date(2031, 3, 20))
            nomes = os.listdir(externa)
            # 01, 02 e 03 têm mais de 7 dias, mas 19, 05 e 04 são os 3 mais recentes e ficam
            self.assertEqual(sorted(n for n in nomes if n.startswith("BACKUP_")),
                             ["BACKUP_04-03-2031_08-00-00.zip", "BACKUP_05-03-2031_08-00-00.zip", "BACKUP_19-03-2031_08-00-00.zip"])
            self.assertIn("outro_arquivo.txt", nomes)                        # o que não é BACKUP_ não é apagado
        self._limpar()

    def test_migracao_da_chave_antiga(self):
        self._limpar()
        with tempfile.TemporaryDirectory() as antiga, tempfile.TemporaryDirectory() as nova:
            self._config(backup_pacote.CHAVE_PASTA, antiga)
            # só ler (tela) não grava: a chave antiga continua como está
            self.assertEqual([os.path.normpath(e["pasta"]) for e in backup_pacote.estado_externa(self.banco())], [os.path.normpath(antiga)])
            self.assertEqual(self._valor(backup_pacote.CHAVE_PASTA), antiga)
            # adicionar outra pasta faz a migração, uma vez: a antiga vira o primeiro item e a chave antiga é esvaziada
            self.post(self.cliente(), "/backup/pasta-destino", {"pasta": nova})
            self.assertEqual(self._valor(backup_pacote.CHAVE_PASTA), "")
            lista = json.loads(self._valor(backup_pacote.CHAVE_PASTAS))
            self.assertEqual([os.path.normpath(p) for p in lista], [os.path.normpath(antiga), os.path.normpath(nova)])
        self._limpar()

    def test_adicionar_e_remover_pela_tela_com_gerencia(self):
        self._limpar()
        adm = self.cliente()
        with tempfile.TemporaryDirectory() as a:
            self.post(adm, "/backup/pasta-destino", {"pasta": a})
            self.assertEqual([os.path.normpath(e["pasta"]) for e in backup_pacote.estado_externa(self.banco())], [os.path.normpath(a)])
            self.assertIn("Remover", self.texto(adm.get("/backup")))
            self.post(adm, "/backup/pasta-destino/remover", {"pasta": a})
            self.assertEqual(backup_pacote.estado_externa(self.banco()), [])
            self.assertTrue(os.path.isdir(a))                               # tirar da lista não apaga a pasta nem os arquivos
        self._limpar()

    def test_pasta_repetida_nao_entra_duas_vezes(self):
        self._limpar()
        adm = self.cliente()
        with tempfile.TemporaryDirectory() as a:
            self.post(adm, "/backup/pasta-destino", {"pasta": a})
            self.post(adm, "/backup/pasta-destino", {"pasta": a + os.sep})
            self.assertEqual(len(backup_pacote.estado_externa(self.banco())), 1)
        self._limpar()

    def test_limite_de_cinco_pastas(self):
        self._limpar()
        adm = self.cliente()
        pastas = [tempfile.mkdtemp(prefix="nuc_pasta_") for _ in range(6)]
        try:
            for p in pastas[:5]:
                self.post(adm, "/backup/pasta-destino", {"pasta": p})
            self.assertEqual(len(backup_pacote.estado_externa(self.banco())), 5)
            self.post(adm, "/backup/pasta-destino", {"pasta": pastas[5]})
            self.assertEqual(len(backup_pacote.estado_externa(self.banco())), 5)
            self.assertIn("Já há 5 pastas de cópia", self.texto(adm.get("/backup")))
        finally:
            for p in pastas:
                shutil.rmtree(p, ignore_errors=True)
            self._limpar()

    # ------------------------------------------------------------ backup automático: janela e frequência
    def test_padrao_e_janela_das_8_as_18_a_cada_30_min(self):
        self._zerar_auto()
        a = backup_pacote.agenda_automatica(self.banco(), datetime(2031, 3, 4, 10, 0))
        self.assertEqual((a["ligado"], a["inicio"], a["fim"], a["minutos"]), (True, "08:00", "18:00", 30))

    def test_fora_da_janela_nao_faz(self):
        self._zerar_auto()
        self.assertIsNone(self._auto_em(4, 7, 59))
        self.assertIsNone(self._auto_em(4, 18, 1))
        self.assertEqual(backup_pacote.agenda_automatica(self.banco(), datetime(2031, 3, 4, 7, 0))["ultimo"], "")

    def test_as_8h_faz_e_as_8h10_nao_faz(self):
        self._zerar_auto()
        primeiro = self._auto_em(4, 8, 0)
        self.assertTrue(primeiro and os.path.isfile(primeiro))
        self.assertIsNone(self._auto_em(4, 8, 10))     # só passaram 10 min
        self.assertIsNone(self._auto_em(4, 8, 29))

    def test_as_8h30_faz_arquivo_novo_e_mantem_o_de_8h(self):
        self._zerar_auto()
        primeiro = self._auto_em(4, 8, 0)
        segundo = self._auto_em(4, 8, 30)
        self.assertTrue(segundo and os.path.isfile(segundo))
        self.assertTrue(os.path.isfile(primeiro))
        a = backup_pacote.agenda_automatica(self.banco(), datetime(2031, 3, 4, 9, 0))
        self.assertEqual((a["ultimo"], a["arquivo"]), ("04/03/2031 08:30", os.path.basename(segundo)))
        self.assertEqual(a["proximo"], "04/03/2031 09:00")
        self.assertIsNotNone(self._auto_em(4, 18, 0))  # o último horário da janela também faz
        self.assertIsNone(self._auto_em(4, 18, 30))

    def test_backup_manual_do_mesmo_dia_nao_e_apagado(self):
        self._zerar_auto()
        manual = backup_pacote.criar_zip(self.banco(), "BACKUP", "", None, datetime(2031, 3, 4, 8, 15))
        self._auto_em(4, 8, 0)
        self._auto_em(4, 8, 30)
        self.assertTrue(os.path.isfile(manual))

    def test_dia_seguinte_comeca_arquivo_novo_e_o_do_dia_anterior_fica(self):
        self._zerar_auto()
        do_dia_4 = self._auto_em(4, 8, 30)
        do_dia_5 = self._auto_em(5, 8, 0)
        self.assertTrue(os.path.isfile(do_dia_4))
        self.assertTrue(os.path.isfile(do_dia_5))

    def test_frequencia_invalida_volta_a_30(self):
        self._zerar_auto()
        self._config(backup_pacote.CHAVE_AUTO_MINUTOS, "7")
        self.assertEqual(backup_pacote.agenda_automatica(self.banco(), datetime(2031, 3, 4, 10, 0))["minutos"], 30)
        self.assertIsNotNone(self._auto_em(4, 8, 0))
        self.assertIsNone(self._auto_em(4, 8, 20))
        self.assertIsNotNone(self._auto_em(4, 8, 30))
        adm = self.cliente()   # a tela recusa frequência fora da lista e não grava nada
        self.post(adm, "/backup/automatico", {"ligado": "1", "inicio": "08:00", "fim": "18:00", "minutos": "7"})
        self.assertEqual(self._valor(backup_pacote.CHAVE_AUTO_MINUTOS), "7")

    def test_desligado_nao_faz(self):
        self._zerar_auto()
        self._config(backup_pacote.CHAVE_AUTO, "0")
        self.assertIsNone(self._auto_em(4, 8, 0))
        self.assertEqual(backup_pacote.agenda_automatica(self.banco(), datetime(2031, 3, 4, 9, 0))["proximo"], "")

    def test_janelas_fixas_com_segundos(self):
        """Janelas fixas (08:00, 08:30, ... 18:00): o atraso não se acumula; a janela de 08:30 começa exatamente às 08:30."""
        self._zerar_auto()
        def faz(h, m, s=0):
            return backup_pacote.backup_automatico(self.banco(), datetime(2031, 3, 4, h, m, s))
        self.assertIsNotNone(faz(8, 0, 40))    # janela 08:00
        self.assertIsNone(faz(8, 29))          # ainda é a janela de 08:00, que já teve backup
        self.assertIsNotNone(faz(8, 30, 5))    # janela de 08:30
        self.assertIsNone(faz(8, 31))          # janela de 08:30, que já teve backup
        self.assertIsNotNone(faz(18, 0))       # último horário da janela (inclusive)
        self.assertIsNone(faz(18, 1))          # fora da janela

    def test_so_um_processo_faz_o_backup_do_horario(self):
        self._zerar_auto()
        agora = datetime(2032, 5, 6, 12, 0)
        primeiro = backup_pacote.backup_automatico(self.banco(), agora)
        segundo = backup_pacote.backup_automatico(self.banco(), agora)     # outro processo, no mesmo instante
        self.assertTrue(primeiro)
        self.assertIsNone(segundo)

    def test_ligar_e_desligar_o_automatico_pela_tela(self):
        adm = self.cliente()
        self.post(adm, "/backup/automatico", {"ligado": "1", "inicio": "09:00", "fim": "17:00", "minutos": "60"})
        self.assertEqual((self._valor(backup_pacote.CHAVE_AUTO), self._valor(backup_pacote.CHAVE_AUTO_INICIO),
                          self._valor(backup_pacote.CHAVE_AUTO_FIM), self._valor(backup_pacote.CHAVE_AUTO_MINUTOS)),
                         ("1", "09:00", "17:00", "60"))
        pagina = adm.get("/backup").data.decode("utf-8")
        self.assertIn('value="09:00"', pagina)
        self.assertIn('<option value="60" selected>', pagina)
        self.post(adm, "/backup/automatico", {"ligado": "1", "inicio": "25:00", "fim": "17:00", "minutos": "60"})   # hora inválida: nada muda
        self.post(adm, "/backup/automatico", {"ligado": "1", "inicio": "18:00", "fim": "08:00", "minutos": "60"})   # início não menor que o fim
        self.post(adm, "/backup/automatico", {"ligado": "1", "inicio": "08:00", "fim": "18:00", "minutos": "45"})   # fora da lista
        self.assertEqual(self._valor(backup_pacote.CHAVE_AUTO_INICIO), "09:00")
        self.assertEqual(self._valor(backup_pacote.CHAVE_AUTO_MINUTOS), "60")
        self.post(adm, "/backup/automatico", {"inicio": "08:00", "fim": "18:00", "minutos": "30"})                  # sem marcar "ligado": desliga
        self.assertEqual(self._valor(backup_pacote.CHAVE_AUTO), "0")
        self.assertIn("Desligado", self.texto(adm.get("/backup")))
        self.post(adm, "/backup/automatico", {"ligado": "1", "inicio": "08:00", "fim": "18:00", "minutos": "30"})
        self.assertIn("Próximo backup automático previsto", self.texto(adm.get("/backup")))


class IdadeDoCadastro(Base):
    def test_exame_sem_nascimento_puxa_a_idade_do_cadastro(self):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            cid = con.execute("INSERT INTO clientes (nome, data_nasc) VALUES ('MARIA CADASTRADA', '1970-05-10')").lastrowid
            con.execute("INSERT INTO clientes (nome, data_nasc) VALUES ('JOAO REPETIDO', '1980-01-01')")
            con.execute("INSERT INTO clientes (nome, data_nasc) VALUES ('JOAO REPETIDO', '1990-01-01')")
            hoje = date.today().isoformat()
            con.execute("INSERT INTO realizacoes (data, numero, cliente_id, paciente, exame) VALUES (?,1,?,?,?)", (hoje, cid, "MARIA CADASTRADA", "MIBI"))
            con.execute("INSERT INTO realizacoes (data, numero, paciente, exame) VALUES (?,2,?,?)", (hoje, "MARIA CADASTRADA", "ÓSSEA"))
            con.execute("INSERT INTO realizacoes (data, numero, paciente, exame) VALUES (?,3,?,?)", (hoje, "JOAO REPETIDO", "RENAL"))
            con.execute("INSERT INTO realizacoes (data, numero, paciente, idade, exame) VALUES (?,4,?,?,?)", (hoje, "SEM CADASTRO", "33", "TGI"))
            con.commit()
        finally:
            con.close()
        esperada = date.today().year - 1970 - ((date.today().month, date.today().day) < (5, 10))
        pagina = self.texto(self.cliente().get("/exames-realizados?mes=todos"))
        self.assertEqual(pagina.count("%d Anos" % esperada), 2)      # com vínculo e pelo nome único
        self.assertIn("33 anos", pagina)                              # idade digitada continua valendo
        csv = self.cliente().get("/exames-realizados/exportar.csv?mes=todos").data.decode("utf-8-sig")
        self.assertEqual(csv.count("%d Anos" % esperada), 2)
        # nome repetido com nascimentos diferentes: não chuta
        linha_joao = next(l for l in csv.splitlines() if "JOAO REPETIDO" in l)
        self.assertNotIn("Anos", linha_joao)


class IdadeNoFormulario(Base):
    def test_formulario_mostra_a_idade_calculada_pelo_nascimento(self):
        hoje = date.today()
        nasc = date(hoje.year - 45, 1, 1)
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            rid = con.execute("INSERT INTO realizacoes (data, numero, paciente, data_nasc, exame) VALUES (?,1,'PACIENTE IDADE',?,'MIBI')",
                              (hoje.isoformat(), nasc.isoformat())).lastrowid
            con.commit()
        finally:
            con.close()
        pagina = self.cliente().get("/exames-realizados/%d" % rid).data.decode("utf-8")
        self.assertIn('id="idade" value="45 anos" inputmode="numeric" readonly', pagina)    # já vem calculada e travada
        self.assertIn("calcularIdade", pagina)                                              # e recalcula ao mudar a data
        # sem nascimento, o campo continua livre para digitar
        livre = self.cliente().get("/exames-realizados/novo").data.decode("utf-8")
        self.assertNotIn('id="idade" value="" inputmode="numeric" readonly', livre)

    def test_salvar_com_nascimento_ignora_a_idade_enviada(self):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            con.execute("DELETE FROM realizacoes WHERE paciente='SALVA IDADE'")
            con.commit()
        finally:
            con.close()
        self.post(self.cliente(), "/exames-realizados/novo", {"data": date.today().isoformat(), "paciente": "SALVA IDADE", "exame": "MIBI",
                                                             "data_nasc": "1980-11-03", "idade": "45 anos"})
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            r = con.execute("SELECT data_nasc, idade FROM realizacoes WHERE paciente='SALVA IDADE'").fetchone()
        finally:
            con.close()
        self.assertEqual((r["data_nasc"], r["idade"]), ("1980-11-03", None))


class FichasEGalio(Base):
    def test_galio_tem_pnt_e_questionario_proprios(self):
        self.assertIn("pnt_galio", fichas.QUESTIONARIOS)
        perguntas = fichas.QUESTIONARIOS["pnt_galio"]
        self.assertEqual(perguntas[0][1], "Qual região?")
        self.assertEqual(len(perguntas), 6)
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            galio = con.execute("SELECT * FROM exames WHERE nome='GALIO'").fetchone()
            self.assertEqual(fichas.questionario_do_exame(galio)[0], "pnt_galio")
        finally:
            con.close()

    def test_pnt_galio_imprime(self):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            cid = con.execute("INSERT INTO clientes (nome) VALUES ('PACIENTE GALIO')").lastrowid
            aid = con.execute("INSERT INTO atendimentos (cliente_id, cliente_nome, exame, data, medico, respostas) VALUES (?,?,?,?,?,?)",
                              (cid, "PACIENTE GALIO", "GALIO", "2026-10-10", "DR TESTE",
                               json.dumps({"r1": "SIM", "o1": "JOELHO", "r2": "NÃO"}))).lastrowid
            con.commit()
        finally:
            con.close()
        r = self.cliente().get("/atendimentos/%d/imprimir?d=pnt_galio:1" % aid)
        self.assertEqual(r.status_code, 200)
        pagina = self.texto(r)
        self.assertIn("GÁLIO-67", pagina)
        self.assertIn("melanoma", pagina)
        self.assertIn("JOELHO", pagina)
        self.assertIn("( X ) SIM", pagina)

    def test_quadro_de_fichas_da_impressao_fica_recolhido(self):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            cid = con.execute("INSERT INTO clientes (nome) VALUES ('PACIENTE FICHA')").lastrowid
            aid = con.execute("INSERT INTO atendimentos (cliente_id, cliente_nome, exame, data, medico) VALUES (?,?,?,?,?)",
                              (cid, "PACIENTE FICHA", "MIBI", "2026-10-10", "DR TESTE")).lastrowid
            con.commit()
        finally:
            con.close()
        pagina = self.cliente().get("/atendimentos/%d/imprimir" % aid).data.decode("utf-8")
        self.assertIn('<details class="docs-detalhe"', pagina)
        self.assertNotIn("<details class=\"docs-detalhe\" open", pagina)
        self.assertIn("Personalizar as fichas a imprimir", pagina)


if __name__ == "__main__":
    unittest.main()
