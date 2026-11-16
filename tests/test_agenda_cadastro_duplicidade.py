"""Botão de cadastrar da agenda, aviso de duplicidade (AVISOS DO SISTEMA) e blindagens fora da ONA."""
from datetime import date

from app import agenda as ag
from app import db as dbmod
from app import qualidade_dados
from tests.test_chat_blindagens import Base


class Agenda2(Base):
    def setUp(self):
        super().setUp()
        self.dia = date.today().isoformat()
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            con.execute("DELETE FROM chat_mensagens")
            con.execute("DELETE FROM agenda_horarios")
            con.execute("DELETE FROM agenda_exames")
            aid = con.execute("INSERT INTO agenda_exames (data, exame, inicio, intervalo, vagas) VALUES (?, 'MIBI', '08:00', 60, 1)", (self.dia,)).lastrowid
            self.ids = []
            for hora, nome, tel in (("08:00", "Ana Souza", "(33) 99999-1111"), ("09:00", "ana  souza", "(33) 98888-2222"),
                                    ("10:00", "Maria X", "33 97777-3333"), ("11:00", "Joao Y", "(33) 97777-3333")):
                self.ids.append(con.execute("INSERT INTO agenda_horarios (agenda_id, hora, paciente, contato, status) VALUES (?,?,?,?, 'AGENDADO')",
                                            (aid, hora, nome, tel)).lastrowid)
            con.commit()
        finally:
            con.close()

    def test_duplicados_por_nome_e_telefone(self):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            grupos = ag.duplicados(con, self.dia)
        finally:
            con.close()
        motivos = sorted(g[0].rsplit("(", 1)[1] for g in grupos)
        self.assertEqual(motivos, ["mesmo nome)", "mesmo telefone)"])

    def test_aviso_com_sim_nao_leva_a_agenda_e_nao_repete(self):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            self.assertEqual(ag.avisar_duplicados(con, self.dia), 2)
            self.assertEqual(ag.avisar_duplicados(con, self.dia), 0)   # mesmo caso não é avisado de novo
            m = con.execute("SELECT id, acao_url FROM chat_mensagens WHERE acao='AGENDA_VER' AND para_id=(SELECT id FROM usuarios WHERE usuario='ADMIN') LIMIT 1").fetchone()
        finally:
            con.close()
        self.assertIn("/agenda?data=%s&destacar=" % self.dia, m["acao_url"])
        r = self.post(self.cliente(), "/mensagens/%d/acao" % m["id"], {"resposta": "SIM"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["url"], m["acao_url"])

    def test_agenda_recebe_os_ids_para_destacar(self):
        pagina = self.texto(self.cliente().get("/agenda?data=%s&destacar=%d,%d" % (self.dia, self.ids[0], self.ids[1])))
        self.assertIn('id="ag-destacar">[%d, %d]' % (self.ids[0], self.ids[1]), pagina)

    def test_status_veio_diz_se_o_cliente_esta_cadastrado(self):
        c = self.cliente()
        r = self.post(c, "/agenda/horario/%d/status" % self.ids[2], {"status": "VEIO"})
        self.assertIs(r.get_json()["cadastrado"], False)

    def test_cadastro_de_cliente_vem_preenchido(self):
        pagina = self.texto(self.cliente().get("/clientes/novo?nome=maria+x&contato=33+97777-3333&convenio=UNIMED"))
        self.assertIn('value="MARIA X"', pagina)
        self.assertIn("33 97777-3333", pagina)

    def test_blindagem_vencida_nao_e_indicador(self):
        self.assertNotIn("blindagens_vencidas", [i[0] for i in qualidade_dados.DEFINICOES])


class Resgate(Agenda2):
    def _destino(self):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            aid = con.execute("SELECT agenda_id FROM agenda_horarios WHERE id=?", (self.ids[0],)).fetchone()[0]
            return con.execute("INSERT INTO agenda_horarios (agenda_id, hora, paciente, status) VALUES (?, '15:00', '', 'AGENDADO')", (aid,)).lastrowid
        finally:
            con.commit()
            con.close()

    def _resgatou(self, hid):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            return con.execute("SELECT status, resgatado_por FROM agenda_horarios WHERE id=?", (hid,)).fetchone()
        finally:
            con.close()

    def test_de_agendado_para_reagendado_nao_e_resgate(self):
        c = self.cliente()
        self.post(c, "/agenda/horario/%d/reagendar" % self.ids[0], {"destino": self._destino()})
        r = self._resgatou(self.ids[0])
        self.assertEqual(r["status"], "RESGATADO")
        self.assertFalse(r["resgatado_por"])

    def test_de_faltou_para_reagendado_e_resgate(self):
        c = self.cliente()
        self.post(c, "/agenda/horario/%d/status" % self.ids[1], {"status": "FALTOU"})
        self.post(c, "/agenda/horario/%d/reagendar" % self.ids[1], {"destino": self._destino()})
        r = self._resgatou(self.ids[1])
        self.assertEqual(r["status"], "RESGATADO")
        self.assertTrue(r["resgatado_por"])
