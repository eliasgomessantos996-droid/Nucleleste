"""Telas e permissões do módulo Banco de Horas dentro da Nucleleste (cliente de teste do Flask)."""
import io
import os
import struct
import tempfile
import unittest

from app import create_app
from app import db as dbmod
from tests.test_bh_core import REGULAR, workbook

PNG = (b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
       + b"\x00\x00\x00\x00" + struct.pack(">I", 0) + b"IEND" + b"\x00\x00\x00\x00")


class TelasBH(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pasta = tempfile.TemporaryDirectory()
        cls.app = create_app(os.path.join(cls.pasta.name, "t.db"))
        cls.app.config["TESTING"] = True

    @classmethod
    def tearDownClass(cls):
        cls.pasta.cleanup()

    def cliente(self, usuario="ADMIN", senha="admin"):
        c = self.app.test_client()
        c.get("/login")
        with c.session_transaction() as s:
            token = s["csrf"]
        r = c.post("/login", data={"usuario": usuario, "senha": senha, "_csrf": token})
        self.assertEqual(r.status_code, 302, r.get_data(as_text=True)[:300])
        c.get("/saude-inexistente")  # qualquer requisição renova o token CSRF da sessão
        return c

    def post(self, c, url, data=None, **kw):
        with c.session_transaction() as s:
            token = s["csrf"]
        dados = dict(data or {})
        dados["_csrf"] = token
        return c.post(url, data=dados, **kw)

    def texto(self, r):
        return r.get_data(as_text=True)

    def criar_usuario(self, nome, senha, modulos, admin=0):
        from werkzeug.security import generate_password_hash
        import json
        con = dbmod.conectar(self.app.config["DATABASE"])
        con.execute("INSERT OR REPLACE INTO usuarios (usuario, senha_hash, admin, ativo, modulos) VALUES (?,?,?,1,?)",
                    (nome, generate_password_hash(senha), admin, json.dumps(modulos)))
        con.commit(); con.close()

    # ------------------------------------------------------------------ fluxo completo da equipe
    def test_fluxo_completo(self):
        c = self.cliente()
        # menu e painel vazios
        r = c.get("/banco-horas")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Seu banco de horas começa aqui", self.texto(r))
        self.assertIn("Banco de Horas", self.texto(c.get("/", headers={"Referer": "http://localhost/"})))

        # cadastro do funcionário
        r = self.post(c, "/banco-horas/funcionarios/novo", {"clock_id": "7", "name": "Maria Teste", "start_date": "2026-09-01",
                                                          "opening_balance_date": "2026-09-01", "opening_balance": "00:00", "active": "1"})
        self.assertEqual(r.status_code, 302)
        eid = int(r.headers["Location"].rstrip("/").split("/")[-1])
        # jornada
        dados = {"effective_date": "2026-09-01", "two_punch_policy": "review", "break_minutes": "01:00", "reason": "Contratual"}
        dados.update({f"weekday_{i}": ("08:00" if i < 5 else "04:00" if i == 5 else "00:00") for i in range(7)})
        r = self.post(c, f"/banco-horas/funcionarios/{eid}/jornada", dados)
        self.assertEqual(r.status_code, 302)
        self.assertIn("Maria Teste", self.texto(c.get("/banco-horas/funcionarios")))
        self.assertIn("Vigências registradas", self.texto(c.get(f"/banco-horas/funcionarios/{eid}")))

        # importação do relógio de ponto
        xls = workbook([("7", "Maria do Relogio", {1: REGULAR, 2: ["08:00", "12:00", "13:00", "18:00"]}), ("9", "Sem cadastro", {})])
        r = self.post(c, "/banco-horas/importacoes/enviar", {"file": (io.BytesIO(xls), "ponto.xls")}, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 302, self.texto(r)[:300])
        det = c.get(r.headers["Location"])
        self.assertIn("Aguardando cadastro", self.texto(det))
        self.assertIn("ponto.xls", self.texto(c.get("/banco-horas/importacoes")))
        # duplicado
        r2 = self.post(c, "/banco-horas/importacoes/enviar", {"file": (io.BytesIO(xls), "outro.xls")}, content_type="multipart/form-data")
        self.assertEqual(r2.headers["Location"], r.headers["Location"])

        # painel, extrato, relatório
        self.assertIn("Maria Teste", self.texto(c.get("/banco-horas?month=2026-09")))
        ext = self.texto(c.get(f"/banco-horas/funcionarios/{eid}/extrato?month=2026-09"))
        self.assertIn("08:00", ext)
        self.assertIn("Pronto para emitir relatório", ext)  # dias importados sem batida viram folga automática
        rel = c.get(f"/banco-horas/funcionarios/{eid}/relatorio?month=2026-09")
        self.assertEqual(rel.status_code, 200)
        self.assertIn("Emitir PDF para assinatura", self.texto(rel))

        # correção de dia + ajuste
        self.assertEqual(c.get(f"/banco-horas/funcionarios/{eid}/dia/2026-09-03").status_code, 200)
        r = self.post(c, f"/banco-horas/funcionarios/{eid}/dia/2026-09-03",
                      {"punches": "08:00 12:00 13:00 17:00", "kind": "normal", "reason": "Esquecimento de batida"})
        self.assertEqual(r.status_code, 302)
        r = self.post(c, f"/banco-horas/funcionarios/{eid}/ajuste", {"date": "2026-09-04", "minutes": "+01:30", "reason": "Compensação"})
        self.assertEqual(r.status_code, 302)
        self.assertIn("+01:30", self.texto(c.get(f"/banco-horas/funcionarios/{eid}/extrato?month=2026-09")))

        # erro de validação volta com mensagem e sem quebrar
        r = self.post(c, f"/banco-horas/funcionarios/{eid}/ajuste", {"date": "2026-09-04", "minutes": "xx", "reason": ""},
                      headers={"Referer": f"/banco-horas/funcionarios/{eid}/extrato"})
        self.assertEqual(r.status_code, 302)
        self.assertIn("formato HH:MM", self.texto(c.get(r.headers["Location"])))

        # emissão do PDF para assinatura (versão 1) e idempotência
        r = self.post(c, f"/banco-horas/funcionarios/{eid}/relatorio/pdf", {"month": "2026-09"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data.startswith(b"%PDF"))
        r = self.post(c, f"/banco-horas/funcionarios/{eid}/relatorio/pdf", {"month": "2026-09"})  # idempotente
        self.assertEqual(r.status_code, 200)
        self.assertIn("versão 1", self.texto(c.get(f"/banco-horas/funcionarios/{eid}/extrato?month=2026-09")))
        self.assertEqual(c.get("/banco-horas/relatorios/1/baixar").status_code, 200)

        # escala
        self.assertIn("Maria Teste", self.texto(c.get("/banco-horas/escala?month=2026-09")))
        r = self.post(c, "/banco-horas/escala/salvar", {"month": "2026-09", "employee_id": eid, "kind": "ferias", "start": "2026-09-10",
                                                       "end": "2026-09-12", "break_duration": "00:00", "note": "Férias"})
        self.assertEqual(r.status_code, 302)
        pdf = c.get("/banco-horas/escala/pdf?month=2026-09")
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.data.startswith(b"%PDF"))

        # Departamento Pessoal
        self.assertIn("Maria Teste", self.texto(c.get("/banco-horas/pessoal")))
        r = self.post(c, f"/banco-horas/pessoal/{eid}/documentos",
                      {"category": "identidade", "title": "RG", "file": (io.BytesIO(PNG), "rg.png")}, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 302, self.texto(r)[:300])
        self.assertIn("RG", self.texto(c.get(f"/banco-horas/pessoal/{eid}")))
        arq = c.get("/banco-horas/pessoal/documentos/1/arquivo")
        self.assertEqual(arq.status_code, 200)
        self.assertEqual(arq.data, PNG)
        self.assertEqual(c.get("/banco-horas/pessoal/documentos/1/imprimir").status_code, 200)
        r = self.post(c, "/banco-horas/pessoal/documentos/1/arquivar", {"reason": "Substituído"})
        self.assertEqual(r.status_code, 302)
        self.assertIn("Arquivados", self.texto(c.get(f"/banco-horas/pessoal/{eid}")))

        # pesquisa e histórico
        self.assertIn("Maria Teste", self.texto(c.get("/banco-horas/pesquisar?q=maria")))
        hist = self.texto(c.get("/banco-horas/historico"))
        self.assertIn("Planilha importada", hist)
        self.assertIn("Ajuste de saldo", hist)
        # registro geral da Nucleleste
        reg = self.texto(c.get("/registros"))
        self.assertIn("Cadastrou funcionário", reg)

        # acesso do funcionário e a "Minha área"
        # o próprio cadastro já criou o acesso: primeiro nome (MARIA) e a senha padrão 123
        f = self.cliente("MARIA", "123")
        # senha provisória: tudo redireciona para a troca
        self.assertIn("/minha-senha", f.get("/banco-horas/minha-area").headers["Location"])
        r = self.post(f, "/minha-senha", {"atual": "123", "nova": "novasenha", "confirmar": "novasenha"})
        self.assertEqual(r.status_code, 302)
        f = self.cliente("MARIA", "novasenha")
        self.assertIn("/banco-horas/minha-area", f.get("/").headers["Location"])
        area = f.get("/banco-horas/minha-area?month=2026-09")
        self.assertEqual(area.status_code, 200)
        self.assertIn("Olá, Maria", self.texto(area))
        self.assertIn("Pendente", self.texto(area))  # o RG foi arquivado, então não conta como "no sistema"
        # nada além da própria área
        for url in ("/banco-horas", f"/banco-horas/funcionarios/{eid}/extrato", "/banco-horas/pessoal", "/atendimentos", "/clientes",
                    "/banco-horas/importacoes", "/faturamento"):
            resp = f.get(url)
            self.assertEqual(resp.status_code, 302, url)

        # mensagens: funcionário escreve, equipe responde
        r = self.post(f, "/banco-horas/mensagens/enviar", {"body": "Bom dia, tenho uma dúvida"}, headers={"Accept": "application/json"})
        self.assertEqual(r.status_code, 200, self.texto(r))
        self.assertEqual(r.get_json()["message"]["body"], "Bom dia, tenho uma dúvida")
        novas = c.get(f"/banco-horas/mensagens/novas?employee={eid}&list=1", headers={"Accept": "application/json"}).get_json()
        self.assertEqual(novas["unread"], 1)
        self.assertEqual(novas["conversations"][0]["unread"], 1)
        pagina = self.texto(c.get(f"/banco-horas/mensagens?employee={eid}"))
        self.assertIn("Bom dia, tenho uma dúvida", pagina)
        r = self.post(c, "/banco-horas/mensagens/enviar", {"employee_id": eid, "body": "Pode falar"}, headers={"Accept": "application/json"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(c.get("/banco-horas/mensagens/novas", headers={"Accept": "application/json"}).get_json()["unread"], 0)
        self.assertEqual(f.get("/banco-horas/mensagens/novas", headers={"Accept": "application/json"}).get_json()["unread"], 1)
        self.assertIn("Pode falar", self.texto(f.get("/banco-horas/mensagens")))
        # o funcionário não consegue falar com outro funcionário informando o id
        r = self.post(f, "/banco-horas/mensagens/enviar", {"employee_id": 9999, "body": "x"}, headers={"Accept": "application/json"})
        self.assertEqual(r.get_json()["message"]["label"], "Maria Teste")

    # ------------------------------------------------------------------ permissões
    def test_permissoes_por_modulo(self):
        self.criar_usuario("SOCONSULTA", "abc123", ["bh_consulta"])
        self.criar_usuario("SEMBH", "abc123", ["clientes"])
        adm = self.cliente()
        r = self.post(adm, "/banco-horas/funcionarios/novo", {"clock_id": "55", "name": "Pessoa Perm", "start_date": "2026-09-01",
                                                              "opening_balance_date": "2026-09-01", "active": "1"})
        eid = int(r.headers["Location"].rstrip("/").split("/")[-1])
        cons = self.cliente("SOCONSULTA", "abc123")
        self.assertEqual(cons.get("/banco-horas").status_code, 200)
        self.assertEqual(cons.get(f"/banco-horas/funcionarios/{eid}/extrato").status_code, 200)
        self.assertNotIn("Corrigir", self.texto(cons.get(f"/banco-horas/funcionarios/{eid}/extrato?month=2026-09")))
        for url in ("/banco-horas/funcionarios/novo", f"/banco-horas/funcionarios/{eid}", "/banco-horas/pessoal", "/banco-horas/mensagens",
                    "/banco-horas/minha-area", f"/banco-horas/funcionarios/{eid}/dia/2026-09-02"):
            self.assertEqual(cons.get(url).status_code, 302, url)
        r = self.post(cons, f"/banco-horas/funcionarios/{eid}/ajuste", {"date": "2026-09-04", "minutes": "+01:00", "reason": "x"})
        self.assertEqual(r.status_code, 302)
        self.assertNotIn("Compensação", self.texto(adm.get(f"/banco-horas/funcionarios/{eid}/extrato?month=2026-09")))
        sem = self.cliente("SEMBH", "abc123")
        self.assertEqual(sem.get("/banco-horas").status_code, 302)
        self.assertNotIn("Painel de saldos", self.texto(sem.get("/clientes")))

    def test_sessao_nao_expira_por_inatividade(self):
        import time
        # cookie de sessão não permanente: sem "Expires"/"Max-Age", some ao fechar o navegador
        c2 = self.app.test_client()
        c2.get("/login")
        with c2.session_transaction() as s:
            tok = s["csrf"]
        r = c2.post("/login", data={"usuario": "ADMIN", "senha": "admin", "_csrf": tok})
        # só o cookie da sessão: o "lembrar usuário" (nuc_usuarios) tem validade de propósito
        cookie = " ".join(h for h in r.headers.getlist("Set-Cookie") if h.lower().startswith("session=")).lower()
        self.assertIn("session=", cookie)
        self.assertNotIn("expires=", cookie)
        self.assertNotIn("max-age", cookie)
        c = self.cliente()   # o login de c2 (mesmo usuário) encerrou uma sessão anterior
        # sem limite de inatividade: parado por horas, a sessão continua valendo (só o logoff ou o navegador fechado encerram)
        with c.session_transaction() as s:
            s["ultima"] = time.time() - 100000
        self.assertEqual(c.get("/banco-horas?month=2026-09").status_code, 200)

    def test_fichas_personalizadas_no_atendimento(self):
        c = self.cliente()
        r = self.post(c, "/exames/fichas/nova", {"titulo": "Termo X", "conteudo": "# TERMO\nPaciente: **{nome}** <script>alert(1)</script>\n[ ] ok {linha}",
                                                  "cabecalho": "1", "ativa": "1"})
        self.assertEqual(r.status_code, 302)
        self.assertIn("Termo X", self.texto(c.get("/exames/fichas")))
        con = dbmod.conectar(self.app.config["DATABASE"])
        xid = con.execute("SELECT id FROM fichas_extras WHERE titulo='Termo X'").fetchone()[0]
        con.execute("INSERT INTO clientes (nome, cpf) VALUES ('JOANA TESTE', '111.111.111-11')")
        cid = con.execute("SELECT id FROM clientes WHERE nome='JOANA TESTE'").fetchone()[0]
        con.execute("INSERT INTO atendimentos (cliente_id, cliente_nome, cpf, exame, convenio, data) VALUES (?,?,?,?,?,?)",
                    (cid, "JOANA TESTE", "111.111.111-11", "MIBI", "PARTICULAR", "2026-09-01"))
        aid = con.execute("SELECT id FROM atendimentos WHERE cliente_nome='JOANA TESTE'").fetchone()[0]
        con.commit(); con.close()
        # a ficha aparece como opção (desmarcada) e imprime com os dados do paciente, sem executar HTML digitado
        pag = self.texto(c.get(f"/atendimentos/{aid}/imprimir"))
        self.assertIn(f'value="x{xid}"', pag)
        pag = self.texto(c.get(f"/atendimentos/{aid}/imprimir?d=x{xid}:2"))
        self.assertEqual(pag.count("<strong>JOANA TESTE</strong>"), 2)
        self.assertNotIn("<script>alert(1)</script>", pag)
        self.assertIn("&lt;script&gt;", pag)
        # pode ser associada a um exame e sai junto
        con = dbmod.conectar(self.app.config["DATABASE"])
        exid = con.execute("SELECT id FROM exames WHERE nome='MIBI'").fetchone()[0]
        con.close()
        form = {"nome": "MIBI", "titulo_ficha": "MIBI", "ordem": "1", "ativo": "1", f"doc_x{xid}": "1", f"copias_x{xid}": "1", "doc_ficha_geral": "1", "copias_ficha_geral": "1"}
        self.assertEqual(self.post(c, f"/exames/{exid}", form).status_code, 302)
        self.assertIn("Paciente:", self.texto(c.get(f"/atendimentos/{aid}/imprimir")))
        # desativar tira das opções; prévia ao vivo responde
        self.post(c, f"/exames/fichas/{xid}", {"titulo": "Termo X", "conteudo": "oi", "cabecalho": "1"})
        self.assertNotIn(f'value="x{xid}"', self.texto(c.get(f"/atendimentos/{aid}/imprimir")))
        self.assertIn("MARIA DA SILVA", self.post(c, "/exames/fichas/previa", {"conteudo": "{nome}"}).get_json()["html"])
        self.assertEqual(self.post(c, f"/exames/fichas/{xid}/excluir").status_code, 302)

    def test_pastas_abrir_no_computador_do_usuario(self):
        c = self.cliente()
        pag = self.texto(c.get("/pastas"))
        self.assertIn('href="nucleleste-pasta:', pag)
        self.assertIn("Configurar este computador", pag)
        reg = c.get("/pastas/configurar-computador.reg")
        self.assertEqual(reg.status_code, 200)
        txt = reg.data.decode("utf-16")
        self.assertIn("[HKEY_CURRENT_USER\\Software\\Classes\\nucleleste-pasta\\shell\\open\\command]", txt)
        self.assertIn("-PathType Container", txt)

    def _planilha_exames(self):
        import datetime as dt
        import openpyxl
        from openpyxl.styles import PatternFill
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "SETEMBRO 2026"
        ws.append(["Nº", "DATA", "CODIGO", "NOME PACIENTE", "SEXO ( M / F)", "DATA DE NASCIMENTO", "PESO", "ALTURA", "CONVÊNIO",
                   "MÉDICO SOLICITANTE", "CID", "RADIO", "ELUIÇÃO", "FÁRMACO", "LOTE", "ATIVIDADE PRESCRITA", "ATIVIDADE ADIMINISTRADA",
                   "EXAME", "HORA DA INJEÇÃO", "HORA DO EXAME", "RESPONSAVEL"])
        linhas = [
            (1, dt.datetime(2026, 9, 1), 82405, "JOAO AVELINO FILHO", "M", dt.datetime(1945, 9, 3), 82, 1.7, "MAISMED", "AGASSI AMORIM ARRUDA", "I20", "TC99", 570, "MIBI", "S1208", 15, 15, "MIBI", dt.time(8, 10), dt.time(9, 10), "PRISCILA", "FF0000"),
            (2, dt.datetime(2026, 9, 1), 82406, "MARIA OSSO", "F", "04 / 09 / 1953", 64, 1.61, "UNIMED", "CARLOS NOGUEIRA PIRES", "M79", "TC99", 570, "MDP", "M0858", 20, 20, "ÓSSEA", dt.time(8, 20), dt.time(10, 20), "PRISCILA", "00FFFF"),
            (3, dt.datetime(2026, 9, 2), 82407, "ANA LINFO", "F", dt.datetime(1970, 1, 2), 70, 1.6, "SUS", "DR X", "C50", "TC99", 100, "FITATO", "F1200", 2, 2, "LINF. SENT", dt.time(8, 0), dt.time(10, 0), "PRISCILA", "D9D9D9"),
            (4, dt.datetime(2026, 9, 2), 82408, "SEM COR NA PLANILHA", "M", dt.datetime(1960, 5, 5), 80, 1.7, "SUS", "DR X", "N13", "TC99", 100, "DTPA", "A0629", 15, 15, "DTPA", dt.time(9, 0), dt.time(9, 30), "PRISCILA", None),
        ]
        for l in linhas:
            ws.append(list(l[:-1]))
            if l[-1]:
                for c in ws[ws.max_row]:
                    c.fill = PatternFill("solid", fgColor="FF" + l[-1])
        buf = io.BytesIO(); wb.save(buf)
        return buf.getvalue()

    def test_exames_realizados_conforme_a_planilha(self):
        c = self.cliente()
        # importação da planilha (como administrador)
        r = self.post(c, "/exames-realizados/importar", {"arquivo": (io.BytesIO(self._planilha_exames()), "EXAMES.xlsx")}, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 302)
        lista = self.texto(c.get("/exames-realizados?mes=2026-09"))
        self.assertIn("JOAO AVELINO FILHO", lista)
        self.assertIn("4 exame(s)", lista)
        # cada linha usa a cor do tipo do exame, inclusive a que não tinha cor na planilha
        self.assertIn("--c:#FF0000", lista)       # MIBI
        self.assertIn("--c:#00FFFF", lista)       # óssea
        self.assertIn("--c:#D9D9D9", lista)       # linfonodo sentinela
        self.assertIn("--c:#B6D7A8", lista)       # DTPA (a planilha não tinha cor nesta linha)
        # formatos de data da planilha e idade calculada
        self.assertTrue("72 Anos" in lista)  # nascimento 04/09/1953 (texto da planilha), exame em 01/09/2026
        # filtros por tipo
        so_mibi = self.texto(c.get("/exames-realizados?mes=2026-09&tipo=mibi"))
        self.assertIn("JOAO AVELINO FILHO", so_mibi)
        self.assertNotIn("MARIA OSSO", so_mibi)
        self.assertIn("MARIA OSSO", self.texto(c.get("/exames-realizados?mes=2026-09&q=osso")))
        # CSV e impressão
        csv_ = c.get("/exames-realizados/exportar.csv?mes=todos")
        self.assertEqual(csv_.status_code, 200)
        self.assertIn("JOAO AVELINO FILHO", csv_.data.decode("utf-8-sig"))
        self.assertIn("--c:#FF0000", self.texto(c.get("/exames-realizados/imprimir?mes=2026-09")))
        # lançamento manual reaproveitando cliente e médico cadastrados
        con = dbmod.conectar(self.app.config["DATABASE"])
        con.execute("INSERT INTO clientes (nome, cpf, data_nasc, convenio) VALUES ('PACIENTE CADASTRADO', '222.222.222-22', '1980-02-03', 'UNIMED')")
        cid = con.execute("SELECT id FROM clientes WHERE nome='PACIENTE CADASTRADO'").fetchone()[0]
        con.execute("INSERT INTO medicos (nome) VALUES ('DRA. CADASTRADA')")
        con.commit(); con.close()
        self.assertEqual(self.post(c, "/exames-realizados/novo", {"cliente_id": cid, "paciente": "paciente cadastrado", "data": "2026-09-03",
            "exame": "dtpa", "medico": "dra. cadastrada", "convenio": "unimed", "farmaco": "dtpa", "lote": "a1", "peso": "70,5", "altura": "1,65",
            "hora_injecao": "0930", "responsavel": "priscila", "sexo": "f", "data_nasc": "1980-02-03"}).status_code, 302)
        con = dbmod.conectar(self.app.config["DATABASE"])
        reg = con.execute("SELECT * FROM realizacoes WHERE paciente='PACIENTE CADASTRADO'").fetchone()
        con.close()
        self.assertEqual((reg["cliente_id"], reg["peso"], reg["altura"], reg["hora_injecao"], reg["lote"], reg["sexo"]), (cid, 70.5, 1.65, "09:30", "A1", None))  # sexo saiu do lançamento de exame: fica no cadastro do cliente
        self.assertIsNotNone(reg["medico_id"])
        self.assertEqual(reg["numero"], 5)   # próximo número do mês (a planilha tinha 4)
        self.assertEqual(reg["codigo"], None)
        # erro de validação não grava
        r = self.post(c, "/exames-realizados/novo", {"paciente": "X", "data": "2026-09-03", "exame": "MIBI", "hora_injecao": "99:99"})
        self.assertIn("Hora inválida", self.texto(r))
        # sugestão a partir do último exame do mesmo tipo
        sug = c.get("/exames-realizados/sugestao?exame=MIBI").get_json()
        self.assertEqual((sug["tipo"], sug["lote"], sug["farmaco"]), ("mibi", "S1208", "MIBI"))
        # edição e exclusão
        rid = reg["id"]
        self.assertEqual(self.post(c, f"/exames-realizados/{rid}", {"paciente": "PACIENTE CADASTRADO", "data": "2026-09-03", "exame": "DMSA"}).status_code, 302)
        self.assertEqual(self.post(c, f"/exames-realizados/{rid}/excluir").status_code, 302)
        # trazer atendimentos do dia
        con = dbmod.conectar(self.app.config["DATABASE"])
        con.execute("INSERT INTO atendimentos (cliente_id, cliente_nome, cpf, exame, convenio, medico, data) VALUES (?,?,?,?,?,?,?)",
                    (cid, "PACIENTE CADASTRADO", "222.222.222-22", "ÓSSEA", "UNIMED", "DRA. CADASTRADA", "2026-09-10"))
        con.commit(); con.close()
        self.assertEqual(self.post(c, "/exames-realizados/atendimentos-do-dia", {"data": "2026-09-10"}).status_code, 302)
        self.assertEqual(self.post(c, "/exames-realizados/atendimentos-do-dia", {"data": "2026-09-10"}).status_code, 302)  # sem duplicar
        con = dbmod.conectar(self.app.config["DATABASE"])
        self.assertEqual(con.execute("SELECT COUNT(*) FROM realizacoes WHERE data='2026-09-10'").fetchone()[0], 1)
        con.close()
        # editar as cores muda a exibição
        con = dbmod.conectar(self.app.config["DATABASE"])
        linhas = con.execute("SELECT id, rotulo, padroes, ordem FROM exame_cores WHERE chave='mibi'").fetchone()
        con.close()
        form = {"id": [str(linhas["id"])], "ativo": [str(linhas["id"])], "cor": ["#123456"], "rotulo": ["MIBI"], "padroes": ["MIBI"], "ordem": [str(linhas["ordem"])]}
        self.assertEqual(self.post(c, "/exames-realizados/cores", form).status_code, 302)
        self.assertIn("--c:#123456", self.texto(c.get("/exames-realizados?mes=2026-09")))

    def test_exames_realizados_permissoes(self):
        self.criar_usuario("TECNICO", "abc123", ["exames_lanc"])
        self.criar_usuario("RECEP", "abc123", ["atendimentos"])
        t = self.cliente("TECNICO", "abc123")
        self.assertEqual(t.get("/exames-realizados").status_code, 200)
        self.assertEqual(t.get("/exames-realizados/cores").status_code, 302)    # cores: módulo "Exames e fichas"
        self.assertEqual(self.post(t, "/exames-realizados/importar", {}).status_code, 302)  # importar: só administrador
        self.assertIn("Lançar exame realizado", self.texto(t.get("/exames-realizados")))
        r = self.cliente("RECEP", "abc123")
        self.assertEqual(r.get("/exames-realizados").status_code, 302)
        self.assertNotIn("Exames realizados", self.texto(r.get("/clientes")))

    def test_migracao_do_programa_autonomo(self):
        import sqlite3
        from app.bh import migracao
        origem = os.path.join(self.pasta.name, "origem.sqlite3")
        o = sqlite3.connect(origem)
        o.executescript("""
        CREATE TABLE employees (id INTEGER PRIMARY KEY, clock_id TEXT, name TEXT, active INTEGER, start_date TEXT, end_date TEXT,
            opening_balance_minutes INTEGER, opening_balance_date TEXT, notes TEXT, created_at TEXT, updated_at TEXT, is_intern INTEGER DEFAULT 0);
        CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, password_hash TEXT, role TEXT, active INTEGER, employee_id INTEGER, must_change INTEGER);
        CREATE TABLE messages (id INTEGER PRIMARY KEY, employee_id INTEGER, sender_user_id INTEGER, sender_role TEXT, sender_label TEXT,
            sender_name TEXT, body TEXT, created_at TEXT);
        INSERT INTO employees VALUES (3,'30','Fulano Migrado',1,'2026-01-01',NULL,60,'2026-01-01','','2026-01-01','2026-01-01',0);
        INSERT INTO users VALUES (1,'Gestora','pbkdf2:sha256:1$x$y','manager',1,NULL,0),(2,'fulano','pbkdf2:sha256:1$x$z','employee',1,3,1);
        INSERT INTO messages VALUES (1,3,2,'employee','Fulano Migrado','fulano','oi','2026-01-02T10:00:00+00:00');
        """)
        o.commit(); o.close()
        # banco novo, sem dados de BH
        destino = os.path.join(self.pasta.name, "dest.db")
        dbmod.inicializar(destino)
        con = dbmod.conectar(destino)
        with con:
            resumo = migracao.importar(con, origem, dbmod.agora())
        self.assertEqual(resumo["tabelas"]["employees"], 1)
        self.assertEqual(resumo["tabelas"]["messages"], 1)
        self.assertEqual(sorted(resumo["usuarios_criados"]), ["FULANO", "GESTORA"])
        u = con.execute("SELECT * FROM usuarios WHERE usuario='FULANO'").fetchone()
        self.assertEqual(u["bh_funcionario_id"], 3)
        self.assertEqual(u["trocar_senha"], 1)
        self.assertEqual(con.execute("SELECT modulos FROM usuarios WHERE usuario='GESTORA'").fetchone()[0].count("bh_gestao"), 1)
        with self.assertRaises(ValueError):
            with con:
                migracao.importar(con, origem, dbmod.agora())
        con.close()


if __name__ == "__main__":
    unittest.main()



