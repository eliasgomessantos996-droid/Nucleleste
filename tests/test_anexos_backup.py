"""Anexos em banco separado, migração, backup .zip, restauração (inclusive de outra pasta), permissões e laudos em Word."""
import io
import os
import re
import shutil
import sqlite3
import tempfile
import unittest
import zipfile
from datetime import date
from unittest import mock

from app import anexos, backup_pacote, laudos_word, migracoes
from app import db as dbmod
from app.bh import core, documents
from tests.test_chat_blindagens import Base

PDF = b"%PDF-1.4 conteudo de teste"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def doc_upload(self, c, nome, conteudo=PDF, tipo="CONTRATO"):
    return self.post(c, "/documentos-arquivo/novo", {"tipo": tipo, "nome": nome, "arquivo": (io.BytesIO(conteudo), "a.pdf")})


class Util(Base):
    def banco(self):
        return self.app.config["DATABASE"]

    def pasta_dados(self):
        return self.app.config["PASTA_DADOS"]

    def con(self):
        return dbmod.conectar(self.banco())

    def contar_anexos(self):
        con = anexos.conectar(anexos.caminho_ao_lado(self.banco()))
        try:
            return con.execute("SELECT COUNT(*) FROM anexos").fetchone()[0]
        finally:
            con.close()

    def contar_docs(self):
        con = self.con()
        try:
            return con.execute("SELECT COUNT(*) FROM arquivos_docs").fetchone()[0]
        finally:
            con.close()

    def backups(self, sufixo=".zip", prefixo="BACKUP_"):
        pasta = os.path.join(self.pasta_dados(), "backups")
        return sorted(os.path.join(pasta, f) for f in os.listdir(pasta) if f.startswith(prefixo) and f.endswith(sufixo)) if os.path.isdir(pasta) else []


class AnexosSeparados(Util):
    def test_documentos_grava_no_anexos_db_e_le_de_la(self):
        c = self.cliente()
        doc_upload(self, c, "contrato anexos")
        con = self.con()
        try:
            r = con.execute("SELECT * FROM arquivos_docs WHERE nome='CONTRATO ANEXOS'").fetchone()
        finally:
            con.close()
        self.assertIsNotNone(r["anexo_id"])
        self.assertEqual(bytes(r["conteudo"]), b"")           # o sistema.db não guarda o arquivo
        self.assertEqual(r["sha256"], anexos.sha256(PDF))
        self.assertEqual(anexos.ler(anexos.caminho_ao_lado(self.banco()), r["anexo_id"]), PDF)
        resp = c.get(f"/documentos-arquivo/{r['id']}/arquivo?baixar=1")
        self.assertEqual((resp.status_code, resp.data), (200, PDF))
        antes = self.contar_anexos()
        self.post(c, f"/documentos-arquivo/{r['id']}/excluir")
        self.assertEqual(self.contar_anexos(), antes - 1)       # o conteúdo sai junto

    def test_formato_invalido_nao_deixa_conteudo_orfao(self):
        c = self.cliente()
        antes = self.contar_anexos()
        self.post(c, "/documentos-arquivo/novo", {"tipo": "CONTRATO", "nome": "x", "arquivo": (io.BytesIO(PDF), "virus.exe")})
        self.assertEqual(self.contar_anexos(), antes)

    def test_dp_grava_e_le_pelo_anexo_id(self):
        con = self.con()
        try:
            eid = core.save_employee(con, {"clock_id": "9001", "name": "Func Anexo", "start_date": "2026-01-01"}, "T")["id"]
            did = documents.add_document(con, eid, "identidade", "RG", "", "rg.png", PNG, "", "T")
            linha = con.execute("SELECT anexo_id, content, size_bytes FROM bh_employee_documents WHERE id=?", (did,)).fetchone()
            self.assertIsNotNone(linha["anexo_id"])
            self.assertEqual(bytes(linha["content"]), b"")
            self.assertEqual(documents.get_document(con, did, True)["content"], PNG)
            with self.assertRaises(ValueError):                  # repetido: a regra do SHA-256 continua
                documents.add_document(con, eid, "identidade", "RG", "", "rg.png", PNG, "", "T")
            self.assertEqual(self.contar_anexos(), self.contar_anexos())
        finally:
            con.close()

    def test_falha_no_metadado_apaga_o_conteudo(self):
        con = self.con()
        try:
            eid = core.save_employee(con, {"clock_id": "9002", "name": "Func Falha", "start_date": "2026-01-01"}, "T")["id"]
            antes = self.contar_anexos()
            with mock.patch.object(core, "log_audit", side_effect=RuntimeError("falhou")):
                with self.assertRaises(RuntimeError):
                    documents.add_document(con, eid, "cpf", "CPF", "", "cpf.png", PNG + b"1", "", "T")
            self.assertEqual(self.contar_anexos(), antes)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM bh_employee_documents WHERE employee_id=?", (eid,)).fetchone()[0], 0)
        finally:
            con.close()


class Migracao(Util):
    def _legado(self, nome, conteudo):
        con = self.con()
        try:
            cur = con.execute("INSERT INTO arquivos_docs (tipo, nome, arquivo_nome, content_type, tamanho, conteudo, criado_em) "
                              "VALUES ('CONTRATO',?,'a.pdf','application/pdf',?,?,'2026-01-01')", (nome, len(conteudo), conteudo))
            con.commit()
            return cur.lastrowid
        finally:
            con.close()

    def test_migra_confere_limpa_e_e_idempotente(self):
        grande = PDF + b"0" * 2_000_000
        a, b = self._legado("LEGADO A", grande), self._legado("LEGADO B", PDF)
        tamanho_antes = os.path.getsize(self.banco())
        con = self.con()
        try:
            r = migracoes.migrar_anexos(con, self.banco())
            self.assertEqual((r["migrados"], r["falhas"]), (2, []))
            for rid, esperado in ((a, grande), (b, PDF)):
                linha = con.execute("SELECT anexo_id, sha256, conteudo FROM arquivos_docs WHERE id=?", (rid,)).fetchone()
                self.assertEqual(bytes(linha["conteudo"]), b"")
                self.assertEqual(linha["sha256"], anexos.sha256(esperado))
                self.assertEqual(anexos.ler(anexos.caminho_ao_lado(self.banco()), linha["anexo_id"]), esperado)
            self.assertTrue(os.path.exists(r["copia"]))                        # cópia antes de mexer
            self.assertIsNone(migracoes.migrar_anexos(con, self.banco()))       # nada mais a fazer
        finally:
            con.close()
        self.assertLess(os.path.getsize(self.banco()), tamanho_antes)           # VACUUM encolheu o sistema.db
        c = self.cliente()
        self.assertEqual(c.get(f"/documentos-arquivo/{a}/arquivo").data, grande)

    def test_falha_na_conferencia_mantem_o_arquivo_onde_esta(self):
        rid = self._legado("LEGADO C", PDF + b"zzz")
        con = self.con()
        try:
            with mock.patch.object(anexos, "ler", return_value=b"corrompido"):
                r = migracoes.migrar_anexos(con, self.banco())
            self.assertEqual(r["migrados"], 0)
            self.assertEqual(len(r["falhas"]), 1)
            linha = con.execute("SELECT anexo_id, conteudo FROM arquivos_docs WHERE id=?", (rid,)).fetchone()
            self.assertIsNone(linha["anexo_id"])
            self.assertEqual(bytes(linha["conteudo"]), PDF + b"zzz")           # nada foi limpo
        finally:
            con.close()
        c = self.cliente()
        self.assertEqual(c.get(f"/documentos-arquivo/{rid}/arquivo").data, PDF + b"zzz")   # o sistema segue funcionando
        con = self.con()
        try:                                                                    # na próxima vez, migra
            self.assertEqual(migracoes.migrar_anexos(con, self.banco())["migrados"], 1)
        finally:
            con.close()


class BackupZip(Util):
    def _backup(self, c):
        self.post(c, "/backup")
        return self.backups()[-1]

    def test_zip_tem_os_dois_bancos_e_leia_me(self):
        c = self.cliente()
        doc_upload(self, c, "para o zip")
        caminho = self._backup(c)
        with zipfile.ZipFile(caminho) as z:
            self.assertEqual(sorted(z.namelist()), ["LEIA-ME.txt", "anexos.db", "sistema.db"])
            texto = z.read("LEIA-ME.txt").decode("utf-8")
            for trecho in ("Versão do sistema", "sistema.db", "anexos.db", "Pelo próprio sistema", "Manualmente", "JUNTOS", "FORA DO COMPUTADOR"):
                self.assertIn(trecho, texto)
            pasta = tempfile.mkdtemp()
            try:
                z.extract("sistema.db", pasta)
                z.extract("anexos.db", pasta)
                for nome in ("sistema.db", "anexos.db"):
                    con = sqlite3.connect(os.path.join(pasta, nome))
                    try:
                        self.assertEqual(con.execute("PRAGMA quick_check").fetchone()[0], "ok")
                    finally:
                        con.close()
                con = sqlite3.connect(os.path.join(pasta, "anexos.db"))
                try:
                    self.assertGreaterEqual(con.execute("SELECT COUNT(*) FROM anexos").fetchone()[0], 1)
                finally:
                    con.close()
            finally:
                shutil.rmtree(pasta, ignore_errors=True)
        self.assertFalse([f for f in os.listdir(os.path.dirname(caminho)) if f.endswith(".parcial")])   # nunca fica zip incompleto
        self.assertIn(os.path.basename(caminho), self.texto(c.get("/backup")))
        self.assertIn("sistema + anexos", self.texto(c.get("/backup")))

    def test_reconhecimento_pelo_conteudo(self):
        c = self.cliente()
        bom = self._backup(c)
        pasta = tempfile.mkdtemp()
        try:
            self.assertTrue(backup_pacote.eh_zip_de_backup(bom))
            lixo = os.path.join(pasta, "BACKUP_lixo.zip")
            open(lixo, "wb").write(b"isto nao e um zip")
            incompleto = os.path.join(pasta, "BACKUP_incompleto.zip")
            with zipfile.ZipFile(incompleto, "w") as z:
                z.writestr("sistema.db", b"x")
            travessia = os.path.join(pasta, "BACKUP_travessia.zip")
            with zipfile.ZipFile(travessia, "w") as z:
                z.writestr("../sistema.db", b"x")
                z.writestr("anexos.db", b"x")
            falso = os.path.join(pasta, "BACKUP_falso.zip")        # nomes certos, mas não são bancos SQLite
            with zipfile.ZipFile(falso, "w") as z:
                z.writestr("sistema.db", b"nao sou sqlite")
                z.writestr("anexos.db", b"nem eu")
            for ruim in (lixo, incompleto, travessia):
                self.assertFalse(backup_pacote.eh_zip_de_backup(ruim), ruim)
                with self.assertRaises(backup_pacote.ErroBackup):
                    backup_pacote.preparar(ruim)
            with self.assertRaises(backup_pacote.ErroBackup):
                backup_pacote.preparar(falso)
            # com outro nome, mas conteúdo certo, vale (o reconhecimento não é pelo nome)
            renomeado = os.path.join(pasta, "qualquer-coisa.zip")
            shutil.copy(bom, renomeado)
            pacote = backup_pacote.preparar(renomeado)
            shutil.rmtree(pacote["tmp"], ignore_errors=True)
            self.assertEqual([i["nome"] for i in backup_pacote.listar_pasta(pasta)], ["qualquer-coisa.zip"])   # o "falso" tem os nomes certos, mas não é SQLite
        finally:
            shutil.rmtree(pasta, ignore_errors=True)

    def test_cli_gera_zip(self):
        pasta = tempfile.mkdtemp()
        try:
            dbmod.inicializar(os.path.join(pasta, "sistema.db"))
            with mock.patch.dict(os.environ, {"NUCLELESTE_DADOS": pasta}):
                from app import cli
                destino = cli.backup()
            self.assertTrue(destino.endswith(".zip"))
            self.assertTrue(backup_pacote.eh_zip_de_backup(destino))
        finally:
            shutil.rmtree(pasta, ignore_errors=True)

    def test_saude_enxerga_o_zip(self):
        c = self.cliente()
        nome = os.path.basename(self._backup(c))
        pagina = self.texto(c.get("/saude"))
        self.assertIn("Último backup", pagina)
        self.assertIn("hoje", pagina)
        from app import views_saude
        with self.app.test_request_context():
            self.assertTrue(views_saude._ultimo_backup()["nome"].endswith(".zip"))
        self.assertTrue(nome.endswith(".zip"))


class Restauracao(Util):
    def _codigo(self, c, **params):
        c.get("/backup/restaurar", query_string=params)
        with c.session_transaction() as s:
            return s["restaurar"]["codigo"]

    def _restaurar(self, c, nome, **params):
        codigo = self._codigo(c, nome=nome, **params)
        return self.post(c, "/backup/restaurar", {"nome": nome, "codigo": codigo})

    def test_restaura_zip_com_os_dois_bancos(self):
        c = self.cliente()
        doc_upload(self, c, "ficava", PDF + b"A")
        self.post(c, "/backup")
        nome = os.path.basename(self.backups()[-1])
        docs_no_backup, anexos_no_backup = self.contar_docs(), self.contar_anexos()
        doc_upload(self, c, "depois do backup", PDF + b"B")
        self.assertEqual(self.contar_docs(), docs_no_backup + 1)
        self._restaurar(c, nome)
        self.assertEqual(self.contar_docs(), docs_no_backup)              # sistema.db voltou
        self.assertEqual(self.contar_anexos(), anexos_no_backup)          # anexos.db voltou junto
        con = self.con()
        try:
            r = con.execute("SELECT id FROM arquivos_docs WHERE nome='FICAVA'").fetchone()
        finally:
            con.close()
        self.assertEqual(c.get(f"/documentos-arquivo/{r['id']}/arquivo").data, PDF + b"A")
        self.assertTrue(self.backups(prefixo=backup_pacote.PREFIXO_SEGURANCA))   # cópia de segurança em .zip

    def test_restaura_db_antigo_so_o_sistema(self):
        c = self.cliente()
        doc_upload(self, c, "continua", PDF + b"C")
        pasta_bkp = os.path.join(self.pasta_dados(), "backups")
        os.makedirs(pasta_bkp, exist_ok=True)
        antigo = os.path.join(pasta_bkp, "BACKUP_antigo.db")
        backup_pacote._copiar_banco(self.banco(), antigo)
        con = self.con()
        try:
            con.execute("INSERT INTO clientes (nome) VALUES ('SO NO ATUAL')")
            con.commit()
        finally:
            con.close()
        r = self._restaurar(c, "BACKUP_antigo.db")
        self.assertEqual(r.status_code, 302)
        con = self.con()
        try:
            self.assertIsNone(con.execute("SELECT 1 FROM clientes WHERE nome='SO NO ATUAL'").fetchone())
            rid = con.execute("SELECT id FROM arquivos_docs WHERE nome='CONTINUA'").fetchone()["id"]
        finally:
            con.close()
        self.assertEqual(c.get(f"/documentos-arquivo/{rid}/arquivo").data, PDF + b"C")   # os anexos atuais foram mantidos
        self.assertIn("formato antigo", self.texto(c.get("/backup")))

    def test_falha_na_segunda_parte_volta_a_primeira(self):
        c = self.cliente()
        self.post(c, "/backup")
        nome = os.path.basename(self.backups()[-1])
        con = self.con()
        try:
            con.execute("INSERT INTO clientes (nome) VALUES ('ANTES DA FALHA')")
            con.commit()
        finally:
            con.close()
        real = backup_pacote._copiar_banco
        chamadas = []

        def instavel(origem, destino):
            chamadas.append(destino)
            if len(chamadas) == 4:       # criar_zip usa 2; depois sistema (3) e anexos (4)
                raise sqlite3.Error("disco cheio")
            return real(origem, destino)

        codigo = self._codigo(c, nome=nome)
        with mock.patch.object(backup_pacote, "_copiar_banco", side_effect=instavel):
            r = self.post(c, "/backup/restaurar", {"nome": nome, "codigo": codigo})
        self.assertEqual(r.status_code, 302)
        con = self.con()
        try:                              # o estado de antes da tentativa continua valendo
            self.assertIsNotNone(con.execute("SELECT 1 FROM clientes WHERE nome='ANTES DA FALHA'").fetchone())
        finally:
            con.close()
        self.assertIn("O estado anterior foi mantido", self.texto(c.get("/backup")))

    def test_codigo_errado_nao_restaura(self):
        c = self.cliente()
        self.post(c, "/backup")
        nome = os.path.basename(self.backups()[-1])
        con = self.con()
        try:
            con.execute("INSERT INTO clientes (nome) VALUES ('NAO PODE SUMIR')")
            con.commit()
        finally:
            con.close()
        self._codigo(c, nome=nome)
        self.post(c, "/backup/restaurar", {"nome": nome, "codigo": "000000" if self._ultimo_codigo(c) != "000000" else "111111"})
        con = self.con()
        try:
            self.assertIsNotNone(con.execute("SELECT 1 FROM clientes WHERE nome='NAO PODE SUMIR'").fetchone())
        finally:
            con.close()

    def _ultimo_codigo(self, c):
        with c.session_transaction() as s:
            return (s.get("restaurar") or {}).get("codigo")


class OutraPasta(Util):
    def _preparar_pasta(self):
        c = self.cliente()
        self.post(c, "/backup")
        origem = self.backups()[-1]
        pasta = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, pasta, True)
        shutil.copy(origem, os.path.join(pasta, "BACKUP_pendrive.zip"))
        open(os.path.join(pasta, "BACKUP_lixo.zip"), "wb").write(b"nao e zip")
        open(os.path.join(pasta, "notas.txt"), "w").write("nada")
        os.makedirs(os.path.join(pasta, "sub"))
        shutil.copy(origem, os.path.join(pasta, "sub", "BACKUP_dentro_de_sub.zip"))
        return c, pasta

    def test_lista_so_validos_sem_recursao_e_restaura_o_mais_recente(self):
        c, pasta = self._preparar_pasta()
        con = self.con()
        try:
            con.execute("INSERT INTO clientes (nome) VALUES ('POSTERIOR AO PENDRIVE')")
            con.commit()
        finally:
            con.close()
        r = self.post(c, "/backup/restaurar-pasta", {"pasta": pasta})
        pagina = self.texto(r)
        self.assertIn("BACKUP_pendrive.zip", pagina)
        self.assertNotIn("BACKUP_lixo.zip", pagina)
        self.assertNotIn("BACKUP_dentro_de_sub.zip", pagina)
        self.assertNotIn("notas.txt", pagina)
        self.assertIn("Restaurar o mais recente desta pasta", pagina)
        # lembra a pasta e registra a busca
        self.assertIn(pasta, self.texto(c.get("/backup/restaurar-pasta")))
        self.assertIn("Buscou backups em outra pasta", self.texto(c.get("/registros")))
        escolher = self.post(c, "/backup/restaurar-pasta/escolher", {"mais_recente": "1"})
        self.assertEqual(escolher.status_code, 302)
        self.assertIn("origem=pasta", escolher.headers["Location"])
        confirmacao = self.texto(c.get(escolher.headers["Location"]))
        self.assertIn("BACKUP_pendrive.zip", confirmacao)
        self.assertIn("código de verificação", confirmacao)
        with c.session_transaction() as s:
            codigo = s["restaurar"]["codigo"]
        self.post(c, "/backup/restaurar", {"nome": "BACKUP_pendrive.zip", "codigo": codigo})
        con = self.con()
        try:
            self.assertIsNone(con.execute("SELECT 1 FROM clientes WHERE nome='POSTERIOR AO PENDRIVE'").fetchone())
        finally:
            con.close()

    def test_caminhos_invalidos_com_mensagem_amigavel(self):
        c = self.cliente()
        arquivo = tempfile.NamedTemporaryFile(delete=False)
        arquivo.close()
        self.addCleanup(os.remove, arquivo.name)
        vazia = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, vazia, True)
        for bruto, trecho in (("", "Informe o caminho"), ("pasta\\relativa", "caminho completo"),
                              (os.path.join(tempfile.gettempdir(), "nao-existe-xyz"), "não existe"), (arquivo.name, "não é uma pasta"),
                              (vazia, "Nenhum backup válido")):
            pagina = self.texto(self.post(c, "/backup/restaurar-pasta", {"pasta": bruto}))
            self.assertIn(trecho, pagina, bruto)

    def test_so_restaura_arquivo_da_lista_encontrada(self):
        c, pasta = self._preparar_pasta()
        outra = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, outra, True)
        shutil.copy(os.path.join(pasta, "BACKUP_pendrive.zip"), os.path.join(outra, "BACKUP_fora_da_lista.zip"))
        self.post(c, "/backup/restaurar-pasta", {"pasta": pasta})
        # nome fora da lista
        r = self.post(c, "/backup/restaurar-pasta/escolher", {"nome": "BACKUP_fora_da_lista.zip"})
        self.assertNotIn("origem=pasta", r.headers["Location"])
        r = self.post(c, "/backup/restaurar-pasta/escolher", {"nome": "..\\..\\BACKUP_pendrive.zip"})   # caminho livre: só vale o nome puro
        self.assertTrue(r.headers["Location"].startswith("/backup/restaurar?nome=BACKUP_pendrive.zip"))
        # POST final forjado, apontando para outra pasta
        import time
        with c.session_transaction() as s:
            s["restaurar"] = {"nome": "BACKUP_fora_da_lista.zip", "codigo": "123456", "ate": time.time() + 100, "pasta": outra}
        con = self.con()
        try:
            con.execute("INSERT INTO clientes (nome) VALUES ('FICA')")
            con.commit()
        finally:
            con.close()
        self.post(c, "/backup/restaurar", {"nome": "BACKUP_fora_da_lista.zip", "codigo": "123456"})
        con = self.con()
        try:
            self.assertIsNotNone(con.execute("SELECT 1 FROM clientes WHERE nome='FICA'").fetchone())
        finally:
            con.close()


class Permissoes(Util):
    def test_so_administracao_e_gerencia_restauram(self):
        c = self.cliente()
        self.post(c, "/backup")
        nome = os.path.basename(self.backups()[-1])
        self.criar_usuario("GERENTE_BKP", ["gerencia"])
        self.criar_usuario("SO_BACKUP", ["backup"])
        ger = self.cliente("GERENTE_BKP", "senha123")
        for rota in ("/backup/restaurar", "/backup/restaurar-pasta"):
            self.assertEqual(ger.get(rota).status_code, 200, rota)        # gerência acessa
        # quem tem só "backup": faz e baixa, mas não vê nem acessa a restauração
        so = self.cliente("SO_BACKUP", "senha123")
        pagina = self.texto(so.get("/backup"))
        self.assertIn("Fazer backup agora", pagina)
        for escondido in ("Restaurar o último backup", "Buscar em outra pasta", "Restaurar</a>"):
            self.assertNotIn(escondido, pagina)
        self.assertEqual(so.get(f"/backup/{nome}").status_code, 200)       # baixar continua
        for rota in ("/backup/restaurar", "/backup/restaurar-pasta"):
            self.assertEqual(so.get(rota).status_code, 302, rota)
        for rota, dados in (("/backup/restaurar", {"nome": nome, "codigo": "000000"}), ("/backup/restaurar-pasta", {"pasta": self.pasta_dados()}),
                            ("/backup/restaurar-pasta/escolher", {"mais_recente": "1"})):
            self.assertEqual(self.post(so, rota, dados).status_code, 302, rota)
        # gerência vê os botões
        self.assertIn("Restaurar o último backup", self.texto(ger.get("/backup")) if ger.get("/backup").status_code == 200 else "")


class LaudoWord(Util):
    def _montar(self):
        pasta = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, pasta, True)
        for nome in ("3F DEG - ANA CELIA DA FONSECA SERAFIM.doc", "3F RAD - LUANA KARINE RUAS DE OLIVEIRA.docx", "3F NORMAL.doc", "4.docx",
                     "08.03.2023 JANIA NÚBIA SANTOS MENDES.docx", "04.04.2024 - RITA PEREIRA RIBEIRO -RAD 2.docx",
                     "3F RAD - MARIA DE LURDES SILVA.docx", "10.01.2022 - MARIA SILVA.docx", "anotacoes.txt"):
            open(os.path.join(pasta, nome), "wb").write(("conteudo de " + nome).encode("utf-8"))
        os.makedirs(os.path.join(pasta, "2021"))
        open(os.path.join(pasta, "2021", "05.05.2021 JANIA NUBIA SANTOS MENDES.doc"), "wb").write(b"antigo")
        return pasta

    def _cliente(self, nome):
        con = self.con()
        try:
            cur = con.execute("INSERT INTO clientes (nome) VALUES (?)", (nome,))
            con.commit()
            return cur.lastrowid
        finally:
            con.close()

    def test_entende_nomes_de_arquivo(self):
        i = laudos_word.interpretar("3F DEG - ANA CELIA DA FONSECA SERAFIM.doc")
        self.assertEqual((i["nome"], i["codigos"], i["data"]), ("ANA CELIA DA FONSECA SERAFIM", ["3F", "DEG"], None))
        i = laudos_word.interpretar("08.03.2023 JANIA NÚBIA SANTOS MENDES.docx")
        self.assertEqual((i["nome"], i["data"]), ("JANIA NUBIA SANTOS MENDES", date(2023, 3, 8)))
        i = laudos_word.interpretar("04.04.202 - RITA PEREIRA RIBEIRO -RAD 2.docx")      # data truncada: não vira nome nem data
        self.assertEqual((i["nome"], i["data"]), ("RITA PEREIRA RIBEIRO", None))
        for sem_nome in ("3F NORMAL.doc", "4.docx"):
            self.assertEqual(laudos_word.interpretar(sem_nome)["nome"], "")
        self.assertIsNone(laudos_word.pontuar("Ana Célia Serafim", "3F NORMAL.doc"))

    def test_configuracao_abre_unico_e_lista_varios(self):
        pasta = self._montar()
        c = self.cliente()
        r = self.post(c, "/configuracoes", {"clinica_nome": "X", "clinica_cidade": "Y", "clinica_cnpj": "Z", "laudos_pasta_word": pasta})
        self.assertEqual(r.status_code, 302)
        # nome único: abre direto o arquivo Word
        cid = self._cliente("Ana Célia da Fonseca Serafim")
        r = c.get(f"/atendimentos/laudo/{cid}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data, "conteudo de 3F DEG - ANA CELIA DA FONSECA SERAFIM.doc".encode("utf-8"))
        # mesma pessoa em duas pastas: lista para escolher (a mais próxima da data do exame primeiro)
        cid = self._cliente("Jânia Núbia Santos Mendes")
        pagina = self.texto(c.get(f"/atendimentos/laudo/{cid}?data=2021-05-05"))
        self.assertIn("08.03.2023 JANIA", pagina)
        self.assertIn("05.05.2021 JANIA", pagina)
        self.assertLess(pagina.index("05.05.2021 JANIA"), pagina.index("08.03.2023 JANIA"))
        link = re.search(r'href="([^"]*abrir=[^"]*2021[^"]*)"', pagina).group(1).replace("&amp;", "&")
        self.assertEqual(c.get(link).data, b"antigo")
        # nome parecido não confunde: MARIA SILVA tem um arquivo de nome igual, o outro tem nomes a mais
        cid = self._cliente("Maria Silva")
        r = c.get(f"/atendimentos/laudo/{cid}")
        self.assertEqual(r.data, b"conteudo de 10.01.2022 - MARIA SILVA.docx")
        # sem laudo
        cid = self._cliente("Fulano Inexistente")
        self.assertIn("Nenhum laudo em Word", self.texto(c.get(f"/atendimentos/laudo/{cid}")))

    def test_sem_pasta_e_fora_da_pasta(self):
        pasta = self._montar()
        c = self.cliente()
        cid = self._cliente("Rita Pereira Ribeiro")
        self.post(c, "/configuracoes", {"clinica_nome": "X", "clinica_cidade": "Y", "clinica_cnpj": "Z", "laudos_pasta_word": ""})
        self.assertIn("ainda não foi definida", self.texto(c.get(f"/atendimentos/laudo/{cid}")))
        self.post(c, "/configuracoes", {"clinica_nome": "X", "clinica_cidade": "Y", "clinica_cnpj": "Z", "laudos_pasta_word": pasta})
        fora = os.path.join(os.path.dirname(pasta), "segredo.docx")
        open(fora, "wb").write(b"segredo")
        self.addCleanup(os.remove, fora)
        for abrir in ("..\\segredo.docx", "../segredo.docx", os.path.abspath(fora), "anotacoes.txt", "nao-existe.doc"):
            self.assertEqual(c.get(f"/atendimentos/laudo/{cid}", query_string={"abrir": abrir}).status_code, 404, abrir)

    def test_botao_aparece_na_ficha_de_exames_anteriores(self):
        c = self.cliente()
        pagina = self.texto(c.get("/atendimentos/novo"))
        self.assertIn("Abrir laudo (Word)", pagina)


class AgendaReservaNaCriacao(Util):
    def test_aba_de_reserva_na_criacao(self):
        c = self.cliente()
        con = self.con()
        try:
            con.execute("INSERT OR IGNORE INTO convenios (nome, gera_caixa, ativo) VALUES ('UNACON',0,1)")
            con.commit()
        finally:
            con.close()
        d1, d2 = "2031-03-10", "2031-03-11"
        base = {"exame": "RAIO X", "inicio": "07:00", "intervalo": "10", "qtd": "4", "vagas": "1"}
        self.post(c, "/agenda/criar", dict(base, data=d1, reserva_ativa="1", reserva_convenio="UNACON", reserva_inicio="07:10",
                                           reserva_qtd="2", reserva_passo="1"))
        self.post(c, "/agenda/criar", dict(base, data=d2))
        a1 = c.get(f"/agenda/dia/{d1}").get_json()["agendas"][0]
        self.assertEqual((a1["reserva_convenio"], [l["hora"] for l in a1["linhas"] if l["reservado"]]), ("UNACON", ["07:10", "07:20"]))
        self.assertEqual(c.get(f"/agenda/dia/{d2}").get_json()["agendas"][0]["reserva_convenio"], "")      # qualquer exame, não só óssea
        pagina = self.texto(c.get("/agenda"))
        for esperado in ('id="c-reserva-aba"', 'id="r-convenio"', 'id="r-passo"', "Reservar horários para um convênio"):
            self.assertIn(esperado, pagina)
        js = open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "app", "static", "js", "agenda.js"), encoding="utf-8").read()
        self.assertIn("if (a.reserva_convenio) acoes.append(botao('Reservar ' + a.reserva_convenio", js)
        self.assertNotIn("data-reserva", js)           # o botão "U" por linha foi retirado

    def test_reserva_antiga_do_unacon_ganha_o_convenio(self):
        con = self.con()
        try:
            cur = con.execute("INSERT INTO agenda_exames (data, exame, inicio, intervalo, vagas, reserva_unacon) VALUES ('2032-01-01','OSSEA','07:00',10,1,1)")
            con.execute("INSERT INTO agenda_horarios (agenda_id, hora, ordem, reservado_unacon) VALUES (?,?,?,1)", (cur.lastrowid, "07:00", 1))
            con.commit()
        finally:
            con.close()
        dbmod.inicializar(self.banco())      # a inicialização completa o convênio das reservas antigas
        con = self.con()
        try:
            self.assertEqual(con.execute("SELECT reserva_convenio FROM agenda_exames WHERE data='2032-01-01'").fetchone()[0], "UNACON")
            self.assertEqual(con.execute("SELECT reservado_convenio FROM agenda_horarios WHERE agenda_id=?", (cur.lastrowid,)).fetchone()[0], "UNACON")
        finally:
            con.close()


if __name__ == "__main__":
    unittest.main()
