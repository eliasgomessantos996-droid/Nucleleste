"""Mapa de laudos: permissões por usuário (ver / avançar), data real de liberação e previsão na ficha impressa."""
import json
from datetime import date, datetime, timedelta

from app import db as dbmod
from app import laudos
from tests.test_chat_blindagens import Base


class Permissoes(Base):
    def setUp(self):
        super().setUp()
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            con.execute("DELETE FROM realizacoes")
            con.execute("DELETE FROM chat_mensagens")
            hoje = date.today().isoformat()
            for nome, sit in (("PAC PROC", "PROCESSANDO"), ("PAC LAUD", "LAUDANDO"), ("PAC LIB", "LIBERADO")):
                con.execute("INSERT INTO realizacoes (data, paciente, exame, hora_exame, laudo_situacao, laudo_atualizado_em) "
                            "VALUES (?,?,?,?,?,?)", (hoje, nome, "MIBI", "08:00", sit, hoje + " 08:00:00"))
            con.commit()
        finally:
            con.close()

    def _id(self, nome):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            return con.execute("SELECT id FROM realizacoes WHERE paciente=?", (nome,)).fetchone()["id"]
        finally:
            con.close()

    def _situacao(self, nome):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            return con.execute("SELECT laudo_situacao, laudo_liberado_em FROM realizacoes WHERE paciente=?", (nome,)).fetchone()
        finally:
            con.close()

    def _restringir(self, usuario, ver, mover):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            con.execute("UPDATE usuarios SET laudo_perm=? WHERE usuario=?", (json.dumps({"ver": ver, "mover": mover}), usuario))
            con.commit()
        finally:
            con.close()

    def test_restrito_so_ve_e_avanca_o_que_a_gerencia_liberou(self):
        self.criar_usuario("TEC1", ["laudos"])
        self._restringir("TEC1", ["PROCESSANDO"], ["PROCESSANDO"])
        c = self.cliente("TEC1", "senha123")
        pagina = self.texto(c.get("/laudos"))
        self.assertIn("PAC PROC", pagina)
        self.assertNotIn("PAC LAUD", pagina)
        self.assertNotIn("PAC LIB", pagina)
        self.post(c, "/laudos/%d/situacao" % self._id("PAC PROC"), {"situacao": "LAUDANDO"})
        self.assertEqual(self._situacao("PAC PROC")["laudo_situacao"], "LAUDANDO")

    def test_restrito_nao_pula_etapa_nem_mexe_em_outra_situacao(self):
        self.criar_usuario("TEC2", ["laudos"])
        self._restringir("TEC2", ["PROCESSANDO"], ["PROCESSANDO"])
        c = self.cliente("TEC2", "senha123")
        self.post(c, "/laudos/%d/situacao" % self._id("PAC PROC"), {"situacao": "LIBERADO"})
        self.assertEqual(self._situacao("PAC PROC")["laudo_situacao"], "PROCESSANDO")
        self.post(c, "/laudos/%d/situacao" % self._id("PAC LAUD"), {"situacao": "LIBERADO"})
        self.assertEqual(self._situacao("PAC LAUD")["laudo_situacao"], "LAUDANDO")

    def test_so_liberado_para_entregue(self):
        self.criar_usuario("REC1", ["laudos"])
        self._restringir("REC1", ["LIBERADO"], ["LIBERADO"])
        c = self.cliente("REC1", "senha123")
        self.assertNotIn("PAC PROC", self.texto(c.get("/laudos")))
        self.post(c, "/laudos/%d/situacao" % self._id("PAC LIB"), {"situacao": "ENTREGUE"})
        self.assertEqual(self._situacao("PAC LIB")["laudo_situacao"], "ENTREGUE")

    def test_gerencia_define_pelo_perfil_do_usuario(self):
        uid = self.criar_usuario("TEC3", ["laudos"])
        c = self.cliente()
        self.post(c, "/usuarios/%d" % uid, {"perfil": "usuario", "modulos": ["laudos"], "laudo_acesso": "restrito",
                                            "ver_PROCESSANDO": "on", "mover_PROCESSANDO": "on"})
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            bruto = con.execute("SELECT laudo_perm FROM usuarios WHERE id=?", (uid,)).fetchone()[0]
        finally:
            con.close()
        self.assertEqual(json.loads(bruto), {"ver": ["PROCESSANDO"], "mover": ["PROCESSANDO"]})
        self.post(c, "/usuarios/%d" % uid, {"perfil": "usuario", "modulos": ["laudos"], "laudo_acesso": "completo"})
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            self.assertIsNone(con.execute("SELECT laudo_perm FROM usuarios WHERE id=?", (uid,)).fetchone()[0])
        finally:
            con.close()

    def test_data_real_de_liberacao(self):
        c = self.cliente()
        ontem = (datetime.now() - timedelta(days=1)).replace(microsecond=0)
        # a data não pode ser anterior ao dia do exame (hoje) -> o exame de hoje recusa ontem
        self.post(c, "/laudos/%d/situacao" % self._id("PAC LAUD"), {"situacao": "LIBERADO", "liberado_em": ontem.strftime("%Y-%m-%dT%H:%M")})
        self.assertEqual(self._situacao("PAC LAUD")["laudo_situacao"], "LAUDANDO")
        # exame de ontem pode ser liberado com a data de ontem
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            con.execute("UPDATE realizacoes SET data=? WHERE paciente='PAC LAUD'", (ontem.date().isoformat(),))
            con.commit()
        finally:
            con.close()
        informado = ontem.replace(hour=15, minute=30)
        self.post(c, "/laudos/%d/situacao" % self._id("PAC LAUD"), {"situacao": "LIBERADO", "liberado_em": informado.strftime("%Y-%m-%dT%H:%M")})
        r = self._situacao("PAC LAUD")
        self.assertEqual(r["laudo_situacao"], "LIBERADO")
        self.assertTrue(r["laudo_liberado_em"].startswith(informado.strftime("%Y-%m-%d 15:30")))

    def test_data_futura_recusada(self):
        c = self.cliente()
        amanha = datetime.now() + timedelta(days=2)
        self.post(c, "/laudos/%d/situacao" % self._id("PAC LAUD"), {"situacao": "LIBERADO", "liberado_em": amanha.strftime("%Y-%m-%dT%H:%M")})
        self.assertEqual(self._situacao("PAC LAUD")["laudo_situacao"], "LAUDANDO")

    def test_ficha_impressa_traz_a_previsao(self):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            con.execute("INSERT OR REPLACE INTO clientes (id, nome, cpf) VALUES (902, 'ZE TESTE', '')")
            aid = con.execute("INSERT INTO atendimentos (cliente_id, cliente_nome, medico, data, exame, usuario, criado_em, previsao_laudo) "
                              "VALUES (902, 'ZE TESTE', 'DR X', '2026-10-19', 'MIBI', 'ADMIN', '2026-10-19 08:00:00', '2026-10-27')").lastrowid
            con.commit()
        finally:
            con.close()
        pagina = self.texto(self.cliente().get("/atendimentos/%d/imprimir" % aid))
        self.assertIn("Previsão de entrega do laudo: 27/10/2026", pagina)

    def test_unidade_permissoes(self):
        self.assertIsNone(laudos.permissoes({"admin": 1, "laudo_perm": "{}"}))
        self.assertIsNone(laudos.permissoes({"admin": 0, "laudo_perm": None}))
        p = laudos.permissoes({"admin": 0, "laudo_perm": json.dumps({"ver": [], "mover": ["LAUDANDO"]})})
        self.assertEqual(p["ver"], {"LAUDANDO"})
        self.assertTrue(laudos.pode_mudar(p, "LAUDANDO", "LIBERADO"))
        self.assertFalse(laudos.pode_mudar(p, "LAUDANDO", "PROCESSANDO"))
