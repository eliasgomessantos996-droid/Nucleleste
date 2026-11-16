"""Testes do log de trocas de modelo da NucleAI IA: persistência, filtros, classificação, tolerância a falhas, permissões e backup."""
import json
import os
import shutil
import sqlite3
import tempfile
import unittest
import zipfile

from app import backup_pacote, db as dbmod, nucleai_trocas
from tests.test_chat_blindagens import Base


class TestNucleAITrocas(Base):
    def setUp(self):
        self.banco = self.app.config["DATABASE"]
        self.pasta_dados = self.app.config["PASTA_DADOS"]
        self.con = dbmod.conectar(self.banco)
        self.addCleanup(self.con.close)
        # Limpa o arquivo de trocas antes de cada teste
        caminho_trocas = nucleai_trocas.caminho_arquivo(self.con)
        if caminho_trocas and os.path.exists(caminho_trocas):
            os.remove(caminho_trocas)

    def test_gravar_e_listar(self):
        reg = nucleai_trocas.registrar_troca(
            self.con,
            de="google/gemini-2.5-flash",
            para="openai/gpt-4o-mini",
            motivo="cota",
            situacao="ADMIN, chat real, teste de limite",
        )
        self.assertIsNotNone(reg)
        self.assertTrue(reg["id"])
        self.assertTrue(reg["quando"])
        self.assertEqual(reg["de"], "google/gemini-2.5-flash")
        self.assertEqual(reg["para"], "openai/gpt-4o-mini")
        self.assertEqual(reg["motivo"], "cota")
        self.assertEqual(reg["situacao"], "ADMIN, chat real, teste de limite")
        self.assertEqual(reg["classificacao"], "")
        self.assertEqual(reg["classificado_por"], "")
        self.assertEqual(reg["classificado_em"], "")

        caminho = nucleai_trocas.caminho_arquivo(self.con)
        self.assertTrue(os.path.isfile(caminho))

        linhas = nucleai_trocas.listar(self.con)
        self.assertEqual(len(linhas), 1)
        self.assertEqual(linhas[0]["id"], reg["id"])
        self.assertEqual(linhas[0]["de"], "google/gemini-2.5-flash")

        cont = nucleai_trocas.contadores(self.con)
        self.assertEqual(cont["total"], 1)
        self.assertEqual(cont["pendentes"], 1)
        self.assertEqual(cont["naturais"], 0)
        self.assertEqual(cont["estranhas"], 0)

    def test_listar_e_filtrar(self):
        t1 = nucleai_trocas.registrar_troca(self.con, "google/m1", "openai/m2", "cota", "sit1")
        t2 = nucleai_trocas.registrar_troca(self.con, "openai/m2", "anthropic/m3", "servidor", "sit2")
        t3 = nucleai_trocas.registrar_troca(self.con, "anthropic/m3", "google/m1", "tempo", "sit3")

        nucleai_trocas.classificar(self.con, t1["id"], "Natural", "admin")
        nucleai_trocas.classificar(self.con, t2["id"], "Estranha", "admin")

        # Filtro por modelo (de ou para)
        m2_trocas = nucleai_trocas.listar(self.con, modelo="openai/m2")
        ids_m2 = {t["id"] for t in m2_trocas}
        self.assertEqual(ids_m2, {t1["id"], t2["id"]})

        m3_trocas = nucleai_trocas.listar(self.con, modelo="anthropic/m3")
        ids_m3 = {t["id"] for t in m3_trocas}
        self.assertEqual(ids_m3, {t2["id"], t3["id"]})

        # Filtro por classificação
        naturais = nucleai_trocas.listar(self.con, classificacao="Natural")
        self.assertEqual(len(naturais), 1)
        self.assertEqual(naturais[0]["id"], t1["id"])

        estranhas = nucleai_trocas.listar(self.con, classificacao="Estranha")
        self.assertEqual(len(estranhas), 1)
        self.assertEqual(estranhas[0]["id"], t2["id"])

        pendentes = nucleai_trocas.listar(self.con, classificacao="pendente")
        self.assertEqual(len(pendentes), 1)
        self.assertEqual(pendentes[0]["id"], t3["id"])

        # Filtro por período
        hoje_trocas = nucleai_trocas.listar(self.con, periodo="hoje")
        self.assertEqual(len(hoje_trocas), 3)

        semana_trocas = nucleai_trocas.listar(self.con, periodo="7d")
        self.assertEqual(len(semana_trocas), 3)

        # Filtros via dicionário
        comb = nucleai_trocas.listar(self.con, filtros={"modelo": "openai/m2", "classificacao": "Natural"})
        self.assertEqual(len(comb), 1)
        self.assertEqual(comb[0]["id"], t1["id"])

        # Contadores
        cont = nucleai_trocas.contadores(self.con)
        self.assertEqual(cont["total"], 3)
        self.assertEqual(cont["naturais"], 1)
        self.assertEqual(cont["estranhas"], 1)
        self.assertEqual(cont["pendentes"], 1)

    def test_classificar(self):
        t = nucleai_trocas.registrar_troca(self.con, "google/a", "google/b", "tempo", "teste")
        tid = t["id"]

        alterado = nucleai_trocas.classificar(self.con, tid, "Natural", "gestor")
        self.assertEqual(alterado["classificacao"], "Natural")
        self.assertEqual(alterado["classificado_por"], "gestor")
        self.assertTrue(alterado["classificado_em"])

        # Releitura do arquivo
        releitura = nucleai_trocas.listar(self.con)[0]
        self.assertEqual(releitura["classificacao"], "Natural")
        self.assertEqual(releitura["classificado_por"], "gestor")

        # Muda para Estranha
        nucleai_trocas.classificar(self.con, tid, "Estranha", "outro_gestor")
        releitura2 = nucleai_trocas.listar(self.con)[0]
        self.assertEqual(releitura2["classificacao"], "Estranha")
        self.assertEqual(releitura2["classificado_por"], "outro_gestor")

        # Limpa classificação
        nucleai_trocas.classificar(self.con, tid, "", "")
        releitura3 = nucleai_trocas.listar(self.con)[0]
        self.assertEqual(releitura3["classificacao"], "")
        self.assertEqual(releitura3["classificado_por"], "")

        # Valor inválido
        with self.assertRaises(ValueError):
            nucleai_trocas.classificar(self.con, tid, "Invalido", "gestor")

        # ID inexistente
        with self.assertRaises(ValueError):
            nucleai_trocas.classificar(self.con, "nao-existe", "Natural", "gestor")

    def test_linha_corrompida(self):
        t1 = nucleai_trocas.registrar_troca(self.con, "google/1", "google/2", "cota", "ok1")
        t2 = nucleai_trocas.registrar_troca(self.con, "google/2", "google/3", "servidor", "ok2")

        caminho = nucleai_trocas.caminho_arquivo(self.con)
        # Injeta linhas corrompidas no arquivo
        with open(caminho, "a", encoding="utf-8") as f:
            f.write("{linha json corrompida sem fechar\n")
            f.write("\n")
            f.write("123456\n")
            f.write('{"sem_id": true}\n')
            f.write("null\n")

        # A leitura ignora as linhas corrompidas e devolve os válidos
        lidos = nucleai_trocas.listar(self.con)
        self.assertEqual(len(lidos), 2)
        ids = {r["id"] for r in lidos}
        self.assertEqual(ids, {t1["id"], t2["id"]})

        # A classificação reescreve atomicamente mantendo a integridade
        nucleai_trocas.classificar(self.con, t1["id"], "Natural", "admin")
        lidos_apos = nucleai_trocas.listar(self.con)
        self.assertEqual(len(lidos_apos), 2)
        t1_atualizado = next(r for r in lidos_apos if r["id"] == t1["id"])
        self.assertEqual(t1_atualizado["classificacao"], "Natural")

    def test_rota_bloqueada_para_nao_gerencia(self):
        self.criar_usuario("RECEPCAO", ["atendimentos"])
        self.criar_usuario("GERENTE", ["gerencia"])

        t = nucleai_trocas.registrar_troca(self.con, "google/a", "openai/b", "cota", "teste perm")

        # Usuário sem gerência tenta acessar a página da IA
        c_rec = self.cliente("RECEPCAO", "senha123")
        r_get = c_rec.get("/nucleai/ia")
        self.assertEqual(r_get.status_code, 302)  # redirecionado (bloqueado)

        # Usuário sem gerência tenta classificar troca
        r_post = self.post(c_rec, "/nucleai/ia/trocas/classificar", {"id": t["id"], "valor": "Natural"})
        self.assertEqual(r_post.status_code, 302)
        # Confere que não classificou
        self.assertEqual(nucleai_trocas.listar(self.con)[0]["classificacao"], "")

        # Usuário com gerência acessa normalmente
        c_ger = self.cliente("GERENTE", "senha123")
        r_ger_get = c_ger.get("/nucleai/ia")
        self.assertEqual(r_ger_get.status_code, 200)
        self.assertIn("Trocas de modelo", self.texto(r_ger_get))

        # Usuário com gerência classifica a troca
        r_ger_post = self.post(c_ger, "/nucleai/ia/trocas/classificar", {"id": t["id"], "valor": "Natural"})
        self.assertEqual(r_ger_post.status_code, 302)
        self.assertIn("#trocas", r_ger_post.headers.get("Location", ""))
        self.assertEqual(nucleai_trocas.listar(self.con)[0]["classificacao"], "Natural")
        self.assertEqual(nucleai_trocas.listar(self.con)[0]["classificado_por"], "GERENTE")

    def test_backup_contendo_arquivo_e_restauracao(self):
        nucleai_trocas.registrar_troca(self.con, "google/gemini-2.5-flash", "openai/gpt-4o", "cota", "backup teste")
        caminho_trocas = nucleai_trocas.caminho_arquivo(self.con)
        self.assertTrue(os.path.isfile(caminho_trocas))
        with open(caminho_trocas, "r", encoding="utf-8") as f:
            conteudo_original = f.read()

        # Cria o backup
        zip_path = backup_pacote.criar_zip(self.banco, versao="1.5.0")
        self.assertTrue(os.path.isfile(zip_path))

        # Verifica que nucleai_trocas.jsonl está no zip
        with zipfile.ZipFile(zip_path, "r") as z:
            nomes = z.namelist()
            self.assertIn("nucleai_trocas.jsonl", nomes)
            self.assertIn("sistema.db", nomes)
            self.assertIn("anexos.db", nomes)
            self.assertIn("LEIA-ME.txt", nomes)
            leia_me = z.read("LEIA-ME.txt").decode("utf-8")
            self.assertIn("nucleai_trocas.jsonl", leia_me)

        # Altera / corrompe o arquivo local de trocas
        with open(caminho_trocas, "w", encoding="utf-8") as f:
            f.write('{"id": "modificado_depois_do_backup"}\n')

        # Restaura o backup
        res = backup_pacote.restaurar(self.banco, zip_path, versao="1.5.0")
        self.assertEqual(res["tipo"], "zip")
        self.assertTrue(res["com_anexos"])

        # Confere que o conteúdo original de trocas foi restaurado
        with open(caminho_trocas, "r", encoding="utf-8") as f:
            conteudo_restaurado = f.read()
        self.assertEqual(conteudo_restaurado, conteudo_original)

        # Testa restauração de backup antigo (sem nucleai_trocas.jsonl)
        # Cria um zip simulando backup de versão anterior sem trocas
        tmp_dir = tempfile.mkdtemp()
        try:
            zip_antigo = os.path.join(tmp_dir, "BACKUP_antigo.zip")
            with zipfile.ZipFile(zip_path, "r") as z_orig:
                with zipfile.ZipFile(zip_antigo, "w") as z_novo:
                    for nome in ("sistema.db", "anexos.db", "LEIA-ME.txt"):
                        z_novo.writestr(nome, z_orig.read(nome))
            # Restauração não pode falhar mesmo sem trocas no zip
            res_antigo = backup_pacote.restaurar(self.banco, zip_antigo, versao="1.5.0")
            self.assertEqual(res_antigo["tipo"], "zip")
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
