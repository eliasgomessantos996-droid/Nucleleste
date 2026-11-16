"""Gestão da Qualidade: telas, permissões, cálculos (Pareto, GUT, risco, SWOT, indicadores), fluxograma, organograma,
ocorrências, avaliação de fornecedores (ONA) e o robô do PDCA com problemas plantados nos dados."""
import io
import json
import unittest
from datetime import date, timedelta

from openpyxl import load_workbook

from app import db as dbmod
from app import qualidade as q
from app import qualidade_dados as qd
from app import qualidade_robo as robo
from tests.test_chat_blindagens import Base

HOJE = date.today()


def _dias(n):
    return (HOJE - timedelta(days=n)).isoformat()


class QualidadeBase(Base):
    def setUp(self):
        from app import cache_curto
        cache_curto.limpar()          # cada teste muda os dados: o cache curto dos indicadores não pode atravessar testes
        self.con = dbmod.conectar(self.app.config["DATABASE"])
        q.garantir(self.con)
        for t in ("cq_problemas", "cq_causas", "cq_porques", "cq_acoes", "cq_riscos", "cq_swot_analises", "cq_swot_itens", "cq_processos",
                  "cq_organograma", "cq_ocorrencias", "cq_pesquisas", "cq_falta_motivos", "cq_kpi_metas", "cq_forn_avaliacoes", "cq_forn_notas",
                  "cq_robo_execucoes", "cq_robo_descartes", "agenda_horarios", "agenda_exames", "realizacoes", "fornecedores", "chat_mensagens"):
            self.con.execute("DELETE FROM %s" % t)
        self.con.commit()

    def tearDown(self):
        self.con.close()

    def agenda(self, dia, exame, statuses, convenio="SUS"):
        aid = self.con.execute("INSERT INTO agenda_exames (data, exame, inicio, intervalo, vagas) VALUES (?,?,?,?,1)",
                               (dia, exame, "08:00", 20)).lastrowid
        for i, st in enumerate(statuses):
            self.con.execute("INSERT INTO agenda_horarios (agenda_id, hora, ordem, paciente, convenio, status) VALUES (?,?,?,?,?,?)",
                             (aid, "%02d:%02d" % (8 + i // 3, (i % 3) * 20), i, "PACIENTE %d" % i, convenio, st))
        self.con.commit()
        return aid


class Calculos(QualidadeBase):
    def test_pareto_ordena_acumula_e_marca_os_poucos_vitais(self):
        self.agenda(_dias(3), "CINTILOGRAFIA ÓSSEA", ["FALTOU"] * 8 + ["VEIO"] * 2)
        self.agenda(_dias(3), "PET-CT", ["FALTOU"] * 2)
        self.agenda(_dias(2), "TIREOIDE", ["FALTOU"] * 1)
        p = qd.pareto(self.con, "faltas_exame", _dias(10), _dias(0))
        self.assertEqual([i["rotulo"] for i in p["itens"]], ["CINTILOGRAFIA ÓSSEA", "PET-CT", "TIREOIDE"])
        self.assertEqual(p["total"], 11)
        self.assertEqual(p["itens"][0]["acum"], 72.7)
        self.assertEqual(p["itens"][-1]["acum"], 100.0)
        self.assertEqual([i["classe"] for i in p["itens"]], ["A", "A", "B"])   # o 3º começa em 90,9% (entre 80% e 95%)
        self.assertEqual([v["rotulo"] for v in p["vitais"]], ["CINTILOGRAFIA ÓSSEA", "PET-CT"])

    def test_gut_risco_e_swot(self):
        self.assertEqual(q.gut_pontos(5, 4, 3), 60)
        self.assertEqual(q.nivel_risco(5, 5)[1], "Crítico")
        self.assertEqual(q.nivel_risco(2, 5)[1], "Alto")
        self.assertEqual(q.nivel_risco(1, 5)[1], "Moderado")
        self.assertEqual(q.nivel_risco(1, 2)[1], "Baixo")
        aid = q.criar_swot(self.con, {"titulo": "Plano 2027"}, "t")
        for quad, texto, peso in (("F", "Equipe experiente", 5), ("FR", "Agenda manual", 3), ("O", "Novo convênio", 4), ("A", "Concorrente", 2)):
            q.adicionar_swot_item(self.con, aid, {"quadrante": quad, "texto": texto, "peso": peso})
        s = q.swot(self.con, aid)
        self.assertEqual(s["saldo_interno"], 2)
        self.assertEqual(s["saldo_externo"], 2)
        self.assertEqual([c["sigla"] for c in s["cruzamentos"]], ["FO", "FA", "DO", "DA"])
        with self.assertRaises(q.ErroQualidade):
            q.adicionar_swot_item(self.con, aid, {"quadrante": "X", "texto": "a"})

    def test_indicadores_com_dados_do_sistema(self):
        self.agenda(_dias(5), "MIBI", ["VEIO"] * 6 + ["FALTOU"] * 4)
        p = qd.painel(self.con, _dias(10), _dias(0))
        por = {i["chave"]: i for i in p["indicadores"]}
        self.assertEqual(por["comparecimento"]["valor"], 60.0)
        self.assertEqual(por["faltas"]["valor"], 40.0)
        self.assertEqual(por["faltas"]["situacao"], "critico")
        self.assertEqual(por["satisfacao"]["situacao"], "sem_dado")
        self.assertEqual(len(por["faltas"]["serie"]), 6)
        q.salvar_metas(self.con, {"meta_faltas": "45"}, "t")
        p2 = qd.painel(self.con, _dias(10), _dias(0))
        self.assertEqual({i["chave"]: i for i in p2["indicadores"]}["faltas"]["situacao"], "ok")

    def test_fluxograma_limpa_o_que_vem_do_navegador(self):
        fid = q.criar_processo(self.con, {"nome": "Recepção"}, "t", "agendamento")
        f = q.processo(self.con, fid)
        self.assertGreater(len(f["dados_obj"]["nos"]), 5)
        self.assertEqual(len(f["dados_obj"]["raias"]), 3)
        sujo = {"nos": [{"id": "a", "forma": "<script>", "texto": "x" * 999, "x": "1e99", "y": 10, "cor": "red"},
                        {"id": "b", "forma": "decisao", "texto": "ok?"}, {"id": "a", "forma": "processo"}],
                "ligacoes": [{"de": "a", "para": "b", "rotulo": "Sim"}, {"de": "a", "para": "zzz"}, {"de": "b", "para": "b"}],
                "modo_cor": "hackeado"}
        q.salvar_processo(self.con, fid, {"dados": json.dumps(sujo)}, "t")
        d = q.processo(self.con, fid)["dados_obj"]
        self.assertEqual([n["id"] for n in d["nos"]], ["a", "b"])
        self.assertEqual(d["nos"][0]["forma"], "processo")
        self.assertEqual(len(d["nos"][0]["texto"]), 200)
        self.assertEqual(d["nos"][0]["x"], 20000.0)
        self.assertEqual(d["nos"][0]["cor"], "")
        self.assertEqual(len(d["ligacoes"]), 1)
        self.assertEqual(d["modo_cor"], "tipo")
        # aprovar congela: a próxima alteração abre a versão 2 como rascunho
        q.aprovar_processo(self.con, fid, "gestor")
        q.salvar_processo(self.con, fid, {"dados": json.dumps(sujo)}, "t")
        f = q.processo(self.con, fid)
        self.assertEqual((f["versao"], f["status"]), (2, "RASCUNHO"))

    def test_organograma_impede_ciclo_e_religa_subordinados(self):
        dire = q.salvar_no_org(self.con, {"cargo": "Diretoria"})
        ger = q.salvar_no_org(self.con, {"cargo": "Gerência", "pai_id": dire})
        rec = q.salvar_no_org(self.con, {"cargo": "Recepção", "pai_id": ger})
        with self.assertRaises(q.ErroQualidade):
            q.salvar_no_org(self.con, {"cargo": "Diretoria", "pai_id": rec}, dire)
        q.excluir_no_org(self.con, ger)
        self.assertEqual({n["id"]: n["pai_id"] for n in q.organograma(self.con)}[rec], dire)

    def test_avaliacao_de_fornecedor(self):
        fid = self.con.execute("INSERT INTO fornecedores (nome, ativo) VALUES ('RADIOFARMACOS LTDA', 1)").lastrowid
        self.con.commit()
        crit = q.criterios(self.con)
        self.assertEqual(len(crit), len(q.CRITERIOS_PADRAO))
        notas = {"nota_%d" % c["id"]: 5 for c in crit}
        aid = q.avaliar_fornecedor(self.con, fid, dict(notas, data=HOJE.isoformat()), "qualidade")
        a = q.avaliacao(self.con, aid)
        self.assertEqual((a["percentual"], a["classificacao"]), (100.0, "APROVADO"))
        self.assertEqual(len(a["notas"]), len(crit))
        # nota baixa sem ação: recusado; com ação: reprovado e reavaliação em 6 meses
        ruins = {"nota_%d" % c["id"]: 2 for c in crit}
        with self.assertRaises(q.ErroQualidade):
            q.avaliar_fornecedor(self.con, fid, ruins, "qualidade")
        aid2 = q.avaliar_fornecedor(self.con, fid, dict(ruins, acao="Notificar e buscar alternativa", data="2026-01-10"), "qualidade")
        a2 = q.avaliacao(self.con, aid2)
        self.assertEqual((a2["percentual"], a2["classificacao"], a2["proxima"]), (40.0, "REPROVADO", "2026-07-10"))
        # faltou nota de um critério
        incompleto = dict(notas)
        incompleto.pop("nota_%d" % crit[0]["id"])
        with self.assertRaises(q.ErroQualidade):
            q.avaliar_fornecedor(self.con, fid, incompleto, "qualidade")
        situ = q.fornecedores_situacao(self.con)
        self.assertEqual(situ[0]["situacao"], "EM DIA")


class RoboDoPDCA(QualidadeBase):
    def _faltas_plantadas(self):
        # 60 marcados no período: 24 faltas (40%), quase todas no mesmo exame; período anterior com 10% de faltas
        for k in range(3):
            self.agenda(_dias(5 + k), "CINTILOGRAFIA ÓSSEA", ["FALTOU"] * 7 + ["VEIO"] * 3, convenio="UNIMED")
            self.agenda(_dias(5 + k), "PET-CT", ["FALTOU"] * 1 + ["VEIO"] * 9)
        for k in range(3):
            self.agenda(_dias(40 + k), "CINTILOGRAFIA ÓSSEA", ["FALTOU"] * 1 + ["VEIO"] * 9)

    def test_acha_o_problema_concentracao_gut_e_monta_o_plano(self):
        self._faltas_plantadas()
        r = robo.analisar(self.con, HOJE - timedelta(days=29), HOJE, usuario="gestor")
        tipos = [a["tipo"] for a in r["achados"]]
        self.assertIn("faltas", tipos)
        a = next(x for x in r["achados"] if x["tipo"] == "faltas")
        self.assertTrue(a["novo"])
        self.assertTrue(any("CINTILOGRAFIA ÓSSEA" in c for c in a["concentracao"]), a["concentracao"])
        self.assertTrue(any("UNIMED" in c for c in a["concentracao"]), a["concentracao"])
        self.assertGreaterEqual(a["gut"]["g"], 4)        # 26,7% de faltas contra meta de 15%
        self.assertGreaterEqual(a["gut"]["u"], 4)        # piorou muito em relação ao período anterior
        p = q.problema(self.con, a["problema_id"])
        self.assertEqual(p["status"], robo.RASCUNHO)
        self.assertEqual(p["origem"], "ROBÔ")
        self.assertTrue(p["plan_meta"].startswith("Atingir Taxa de faltas"))
        self.assertIn("CINTILOGRAFIA", p["plan_causa"])
        self.assertTrue(all(p["porques"]))
        self.assertGreaterEqual(len(p["acoes"]), 2)
        self.assertTrue(any(c["principal"] and c["texto"].startswith("Dado do sistema") for c in p["causas"]))
        self.assertTrue(any("Taxa de faltas" in e for e in p["evidencia_lista"]))
        # perguntas: faltas sem motivo pedem classificação
        self.assertTrue(any(x["nome"] == "Motivo das faltas" for x in r["perguntas"]))

    def test_nao_duplica_aceita_e_descarta(self):
        self._faltas_plantadas()
        r1 = robo.analisar(self.con, HOJE - timedelta(days=29), HOJE)
        pid = next(a["problema_id"] for a in r1["achados"] if a["tipo"] == "faltas")
        r2 = robo.analisar(self.con, HOJE - timedelta(days=29), HOJE)
        self.assertEqual(next(a["problema_id"] for a in r2["achados"] if a["tipo"] == "faltas"), pid)
        self.assertEqual(r2["novos"], 0)
        robo.aceitar(self.con, pid, "gestor")
        self.assertEqual(q.problema(self.con, pid)["status"], "ABERTO")
        robo.descartar(self.con, pid, "gestor")
        r3 = robo.analisar(self.con, HOJE - timedelta(days=29), HOJE)
        a3 = next(a for a in r3["achados"] if a["tipo"] == "faltas")
        self.assertTrue(a3.get("descartado"))
        self.assertIsNone(a3["problema_id"])

    def test_dados_saudaveis_e_volume_pequeno_nao_geram_problema(self):
        self.agenda(_dias(3), "MIBI", ["VEIO"] * 30 + ["FALTOU"] * 2)
        self.agenda(_dias(4), "PET-CT", ["FALTOU"] * 3)           # 3 faltas em 3, mas a base total é grande e saudável
        r = robo.analisar(self.con, HOJE - timedelta(days=29), HOJE)
        self.assertNotIn("faltas", [a["tipo"] for a in r["achados"]])
        self.con.execute("DELETE FROM agenda_horarios")
        self.con.execute("DELETE FROM agenda_exames")
        self.agenda(_dias(3), "MIBI", ["FALTOU"] * 5)              # 100% de faltas, mas só 5 casos: ruído
        r = robo.analisar(self.con, HOJE - timedelta(days=29), HOJE)
        self.assertNotIn("faltas", [a["tipo"] for a in r["achados"]])

    def test_rotina_diaria_roda_uma_vez_e_avisa_a_gerencia(self):
        self._faltas_plantadas()
        self.assertIsNotNone(robo.rotina_diaria(self.con))
        self.assertIsNone(robo.rotina_diaria(self.con))
        avisos = self.con.execute("SELECT corpo FROM chat_mensagens WHERE corpo LIKE 'Robô do PDCA%'").fetchall()
        self.assertGreaterEqual(len(avisos), 1)


class Telas(QualidadeBase):
    def test_todas_as_telas_abrem_e_exportam(self):
        c = self.cliente()
        self._dados_de_exemplo(c)
        for url in ("/qualidade", "/qualidade/indicadores", "/qualidade/robo", "/qualidade/pdca", "/qualidade/pareto",
                    "/qualidade/pareto?fonte=faltas_motivo", "/qualidade/ishikawa", "/qualidade/porques", "/qualidade/gut", "/qualidade/riscos",
                    "/qualidade/plano", "/qualidade/swot", "/qualidade/fluxogramas", "/qualidade/organograma", "/qualidade/ocorrencias",
                    "/qualidade/fornecedores", "/qualidade/fornecedores/criterios"):
            r = c.get(url)
            self.assertEqual(r.status_code, 200, url + " " + self.texto(r)[:300])
        pid = self.con.execute("SELECT id FROM cq_problemas LIMIT 1").fetchone()[0]
        self.assertEqual(c.get("/qualidade/pdca/%d" % pid).status_code, 200)
        fid = self.con.execute("SELECT id FROM cq_processos LIMIT 1").fetchone()[0]
        self.assertIn("fx-dados", self.texto(c.get("/qualidade/fluxogramas/%d" % fid)))
        for url in ("/qualidade/indicadores.pdf", "/qualidade/pdca/%d.pdf" % pid, "/qualidade/gut.pdf", "/qualidade/plano.pdf",
                    "/qualidade/riscos.pdf", "/qualidade/pareto.pdf", "/qualidade/ocorrencias.pdf", "/qualidade/fornecedores/relatorio.pdf"):
            r = c.get(url)
            self.assertEqual(r.status_code, 200, url)
            self.assertTrue(r.data.startswith(b"%PDF"), url)
        for url in ("/qualidade/indicadores.xlsx", "/qualidade/plano.xlsx", "/qualidade/riscos.xlsx", "/qualidade/pareto.xlsx",
                    "/qualidade/ocorrencias.xlsx", "/qualidade/fornecedores/relatorio.xlsx"):
            r = c.get(url)
            self.assertEqual(r.status_code, 200, url)
            load_workbook(io.BytesIO(r.data))

    def _dados_de_exemplo(self, c):
        self.agenda(_dias(2), "MIBI", ["VEIO", "FALTOU", "FALTOU"])
        self.post(c, "/qualidade/pdca/novo", {"titulo": "Pacientes sem preparo", "gut_g": 4, "gut_u": 3, "gut_t": 3})
        pid = self.con.execute("SELECT id FROM cq_problemas").fetchone()[0]
        self.post(c, "/qualidade/pdca/%d/causas" % pid, {"categoria": "Método", "texto": "Orientação confusa", "principal": "1"})
        self.post(c, "/qualidade/pdca/%d/porques" % pid, {"porque_1": "a", "porque_2": "b", "causa_raiz": "sem roteiro"})
        self.post(c, "/qualidade/acoes", {"problema_id": pid, "o_que": "Roteiro de confirmação", "quando": _dias(1), "quanto": "1.200,50"})
        self.post(c, "/qualidade/riscos/salvar", {"titulo": "Contaminação", "probabilidade": 2, "impacto": 5})
        self.post(c, "/qualidade/swot/nova", {"titulo": "2027"})
        self.post(c, "/qualidade/fluxogramas/novo", {"nome": "Laudo", "modelo": "laudo"})
        self.post(c, "/qualidade/organograma/salvar", {"cargo": "Diretoria"})
        self.post(c, "/qualidade/ocorrencias/salvar", {"tipo": "Reclamação", "descricao": "Demora na recepção", "gravidade": "Moderada"})
        self.post(c, "/qualidade/pesquisa", {"nota": 9})
        p = q.problema(self.con, pid)
        self.assertEqual(p["plan_causa"], "sem roteiro")
        self.assertEqual(p["acoes"][0]["quanto"], 1200.5)
        self.assertTrue(p["acoes"][0]["atrasada"])

    def test_salvar_fluxograma_pela_tela(self):
        c = self.cliente()
        r = self.post(c, "/qualidade/fluxogramas/novo", {"nome": "Compras", "modelo": "compras"})
        fid = int(r.headers["Location"].rstrip("/").split("/")[-1])
        dados = {"nos": [{"id": "n1", "forma": "inicio", "texto": "Início", "x": 0, "y": 0}], "ligacoes": [], "raias": []}
        r = self.post(c, "/qualidade/fluxogramas/%d/salvar" % fid, {"dados": json.dumps(dados)}, headers={"Accept": "application/json"})
        self.assertEqual(r.get_json()["etapas"], 1)
        r = self.post(c, "/qualidade/fluxogramas/%d/salvar" % fid, {"dados": "{quebrado"}, headers={"Accept": "application/json"})
        self.assertEqual(r.status_code, 400)

    def test_permissoes(self):
        self.criar_usuario("Q_SEM", modulos=["dashboard"])
        self.criar_usuario("Q_GESTAO", modulos=["qualidade_gestao"])
        self.criar_usuario("Q_FORN", modulos=["qualidade_fornecedores"])
        sem, ges, forn = self.cliente("Q_SEM", "senha123"), self.cliente("Q_GESTAO", "senha123"), self.cliente("Q_FORN", "senha123")
        self.assertEqual(sem.get("/qualidade/indicadores").status_code, 302)
        self.assertEqual(ges.get("/qualidade/indicadores").status_code, 200)
        self.assertEqual(ges.get("/qualidade/fornecedores").status_code, 302)
        self.assertEqual(forn.get("/qualidade/fornecedores").status_code, 200)
        self.assertEqual(forn.get("/qualidade/pdca").status_code, 302)
        menu = self.texto(ges.get("/qualidade/indicadores"))
        self.assertIn("Robô do PDCA", menu)
        self.assertNotIn(">Avaliação de fornecedores<", menu.replace("\n", ""))

    def test_motivo_de_falta_pela_tela(self):
        c = self.cliente()
        aid = self.agenda(_dias(1), "MIBI", ["FALTOU", "VEIO"])
        h_falta, h_veio = [r[0] for r in self.con.execute("SELECT id FROM agenda_horarios WHERE agenda_id=? ORDER BY id", (aid,))]
        self.post(c, "/qualidade/faltas/%d/motivo" % h_falta, {"motivo": "Transporte"})
        self.post(c, "/qualidade/faltas/%d/motivo" % h_veio, {"motivo": "Transporte"})   # não é falta: recusado
        motivos = dict(self.con.execute("SELECT horario_id, motivo FROM cq_falta_motivos").fetchall())
        self.assertEqual(motivos, {h_falta: "Transporte"})
        p = qd.pareto(self.con, "faltas_motivo", _dias(5), _dias(0))
        self.assertEqual(p["itens"][0]["rotulo"], "Transporte")


if __name__ == "__main__":
    unittest.main()
