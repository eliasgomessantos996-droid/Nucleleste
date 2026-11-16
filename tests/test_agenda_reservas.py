"""Planilha das vagas reservadas para o convênio: gerar em branco e importar preenchida."""
import io
import zipfile
from datetime import date, timedelta

from openpyxl import load_workbook

from app import agenda_reservas as rv
from app import db as dbmod
from tests.test_chat_blindagens import Base


class Reservas(Base):
    def setUp(self):
        super().setUp()
        self.dia = date.today().isoformat()
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            con.execute("DELETE FROM agenda_horarios")
            con.execute("DELETE FROM agenda_exames")
            con.execute("INSERT OR IGNORE INTO convenios (nome, ativo) VALUES ('UNIMED', 1)")
            aid = con.execute("INSERT INTO agenda_exames (data, exame, inicio, intervalo, vagas) VALUES (?, 'MIBI', '08:00', 60, 1)", (self.dia,)).lastrowid
            self.ids = [con.execute("INSERT INTO agenda_horarios (agenda_id, hora, paciente, status, reservado_unacon, reservado_convenio, convenio) "
                                    "VALUES (?,?,?,'AGENDADO',1,'UNIMED','UNIMED')", (aid, h, p)).lastrowid
                        for h, p in (("08:00", ""), ("09:00", ""), ("10:00", "JA TEM"))]
            con.execute("INSERT INTO agenda_horarios (agenda_id, hora, paciente, status) VALUES (?, '11:00', '', 'AGENDADO')", (aid,))
            con.commit()
        finally:
            con.close()

    def _planilha(self):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            g = rv.grupos(con, "UNIMED", self.dia, self.dia)[0]
            return rv.planilha_do_dia(g["convenio"], g["dia"], g["vagas"])
        finally:
            con.close()

    def test_planilha_em_branco_so_com_vagas_do_convenio(self):
        ws = load_workbook(io.BytesIO(self._planilha())).active
        linhas = list(ws.iter_rows(min_row=rv.LINHA_CAB + 1, values_only=True))
        self.assertEqual(len(linhas), 2)                      # só as duas vagas livres reservadas
        self.assertEqual({l[6] for l in linhas}, {self.ids[0], self.ids[1]})
        self.assertTrue(all(not l[3] and l[5] == "UNIMED" for l in linhas))

    def test_sem_vaga_nao_gera(self):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            self.assertIsNone(rv.pacote(con, "OUTRO", self.dia, self.dia))
        finally:
            con.close()

    def test_importar_preenche_nome_e_contato_sem_sobrescrever(self):
        wb = load_workbook(io.BytesIO(self._planilha()))
        ws = wb.active
        ws.cell(row=5, column=4, value="maria da silva")
        ws.cell(row=5, column=5, value="33999991111")
        ws.cell(row=6, column=4, value="")                       # em branco: ignorada
        buf = io.BytesIO()
        wb.save(buf)
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            res = rv.importar(con, buf.getvalue(), "ADMIN")
            r = con.execute("SELECT paciente, contato, convenio FROM agenda_horarios WHERE id=?", (self.ids[0],)).fetchone()
            ja = con.execute("SELECT paciente FROM agenda_horarios WHERE id=?", (self.ids[2],)).fetchone()[0]
        finally:
            con.close()
        self.assertEqual((res["preenchidas"], res["ignoradas"], res["problemas"]), (1, 1, []))
        self.assertEqual(r["paciente"], "MARIA DA SILVA")
        self.assertIn("99999", r["contato"])
        self.assertEqual(r["convenio"], "UNIMED")
        self.assertEqual(ja, "JA TEM")

    def test_linha_que_nao_confere_e_recusada(self):
        wb = load_workbook(io.BytesIO(self._planilha()))
        ws = wb.active
        ws.cell(row=5, column=4, value="FULANO")
        ws.cell(row=5, column=2, value="23:59")                  # hora alterada
        buf = io.BytesIO()
        wb.save(buf)
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            res = rv.importar(con, buf.getvalue(), "ADMIN")
        finally:
            con.close()
        self.assertEqual(res["preenchidas"], 0)
        self.assertEqual(len(res["problemas"]), 1)

    def test_telas_baixar_e_importar(self):
        c = self.cliente()
        r = c.get("/agenda/reservas/planilha?convenio=UNIMED&de=%s&ate=%s" % (self.dia, self.dia))
        self.assertEqual(r.status_code, 200)
        self.assertIn("spreadsheetml", r.headers["Content-Type"])      # um dia só: a própria planilha
        pagina = self.texto(c.get("/agenda/reservas"))
        self.assertIn("Importar a planilha preenchida", pagina)
        self.assertIn("Reservas do convênio", self.texto(c.get("/agenda")))
        r = self.post(c, "/agenda/reservas/importar", {"planilha": (io.BytesIO(r.data), "p.xlsx")}, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Resultado da importação", self.texto(r))


class ReservasVariosDias(Base):
    """Período com mais de um dia reservado: .zip com uma planilha por dia e o resumo em PDF."""

    def setUp(self):
        super().setUp()
        self.dia = date.today().isoformat()
        self.amanha = (date.today() + timedelta(days=1)).isoformat()
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            con.execute("DELETE FROM agenda_horarios")
            con.execute("DELETE FROM agenda_exames")
            con.execute("INSERT OR IGNORE INTO convenios (nome, ativo) VALUES ('UNIMED', 1)")
            for dia, exame, horas in ((self.dia, "MIBI", ("08:00", "09:00")), (self.amanha, "ÓSSEA", ("08:00", "09:00", "10:00"))):
                aid = con.execute("INSERT INTO agenda_exames (data, exame, inicio, intervalo, vagas) VALUES (?,?,'08:00',60,1)", (dia, exame)).lastrowid
                for h in horas:
                    con.execute("INSERT INTO agenda_horarios (agenda_id, hora, paciente, status, reservado_unacon, reservado_convenio, convenio) "
                                "VALUES (?,?,'','AGENDADO',1,'UNIMED','UNIMED')", (aid, h))
            con.commit()
        finally:
            con.close()

    def test_periodo_maior_vem_em_zip_com_uma_planilha_por_dia_e_pdf(self):
        r = self.cliente().get("/agenda/reservas/planilha?convenio=UNIMED&de=%s&ate=%s" % (self.dia, self.amanha))
        self.assertEqual(r.status_code, 200)
        self.assertIn("zip", r.headers["Content-Type"])
        z = zipfile.ZipFile(io.BytesIO(r.data))
        nomes = sorted(z.namelist())
        self.assertEqual(nomes, ["reserva-UNIMED-%s.xlsx" % self.dia, "reserva-UNIMED-%s.xlsx" % self.amanha, "resumo-das-reservas.pdf"])
        self.assertEqual(z.read("resumo-das-reservas.pdf")[:4], b"%PDF")
        dia2 = load_workbook(io.BytesIO(z.read("reserva-UNIMED-%s.xlsx" % self.amanha))).active
        self.assertEqual(len(list(dia2.iter_rows(min_row=rv.LINHA_CAB + 1, values_only=True))), 3)

    def test_sem_convenio_escolhido_traz_todos(self):
        r = self.cliente().get("/agenda/reservas/planilha?de=%s&ate=%s" % (self.dia, self.amanha))
        self.assertEqual(r.status_code, 200)
        self.assertIn("zip", r.headers["Content-Type"])

    def test_importar_sem_reserva_nao_mostra_o_formulario(self):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            con.execute("UPDATE agenda_horarios SET reservado_unacon=0, reservado_convenio=NULL")
            con.commit()
        finally:
            con.close()
        self.assertNotIn("Importar a planilha preenchida", self.texto(self.cliente().get("/agenda/reservas")))


class PlanilhaTravada(Reservas):
    """A planilha só libera nome e contato; o código da vaga fica oculto e bloqueado, e senha/observação não existem mais."""

    def test_so_nome_e_contato_estao_liberados_e_o_codigo_fica_oculto(self):
        ws = load_workbook(io.BytesIO(self._planilha())).active
        self.assertEqual([c.value for c in ws[rv.LINHA_CAB]], rv.COLUNAS)
        self.assertNotIn("Senha / autorização", rv.COLUNAS)
        self.assertNotIn("Observação", rv.COLUNAS)
        self.assertTrue(ws.protection.sheet)                                   # planilha protegida
        self.assertTrue(ws.column_dimensions["G"].hidden)                      # código oculto
        for linha in ws.iter_rows(min_row=rv.LINHA_CAB + 1):
            liberadas = [c.column for c in linha if not c.protection.locked]
            self.assertEqual(liberadas, [4, 5])                                # só Nome do paciente e Contato
            self.assertTrue(linha[6].protection.locked)                        # o código é bloqueado

    def test_codigo_adulterado_nao_importa(self):
        wb = load_workbook(io.BytesIO(self._planilha()))
        ws = wb.active
        ws.cell(row=5, column=4, value="FULANO")
        ws.cell(row=5, column=7, value=self.ids[1])                            # código trocado para outra vaga (hora diferente)
        buf = io.BytesIO()
        wb.save(buf)
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            res = rv.importar(con, buf.getvalue(), "ADMIN")
            outra = con.execute("SELECT paciente FROM agenda_horarios WHERE id=?", (self.ids[1],)).fetchone()[0]
        finally:
            con.close()
        self.assertEqual(res["preenchidas"], 0)
        self.assertEqual(outra, "")                                            # a vaga errada não foi preenchida
