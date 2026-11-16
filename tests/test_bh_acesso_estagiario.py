"""Banco de Horas: acesso automático (primeiro nome + senha padrão, sistema travado até trocar a senha), perfil Usuário/Administrador
e o perfil de estagiário (lança fichas e só consulta/imprime a agenda)."""
import json
import re
import unittest

from app import db as dbmod
from app import modulos
from app.bh import portal
from tests.test_chat_blindagens import Base


class AcessoAutomatico(Base):
    def _novo(self, c, nome, clock, **extra):
        dados = {"clock_id": clock, "name": nome, "start_date": "2026-09-01", "opening_balance_date": "2026-09-01", "active": "1"}
        dados.update(extra)
        return self.post(c, "/banco-horas/funcionarios/novo", dados)

    def _usuario(self, login):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            return con.execute("SELECT * FROM usuarios WHERE usuario=?", (login,)).fetchone()
        finally:
            con.close()

    def test_cadastro_cria_usuario_com_primeiro_nome_e_senha_padrao(self):
        c = self.cliente()
        r = self._novo(c, "Maria Aparecida Souza", "801")
        self.assertEqual(r.status_code, 302)
        u = self._usuario("MARIA")
        self.assertIsNotNone(u)
        self.assertEqual((u["trocar_senha"], u["admin"], u["ativo"]), (1, 0, 1))
        self.assertIsNotNone(u["bh_funcionario_id"])
        aviso = self.texto(c.get(r.headers["Location"]))                              # a gestão vê o login e a senha padrão
        self.assertIn("MARIA", aviso)
        self.assertIn("senha padrão %s" % portal.SENHA_PADRAO, aviso)

    def test_login_com_acento_repetido_e_curto(self):
        c = self.cliente()
        self._novo(c, "José Carlos", "802")
        self.assertIsNotNone(self._usuario("JOSE"))
        self._novo(c, "Jose Pereira", "803")           # primeiro nome já usado: junta o último nome
        self.assertIsNotNone(self._usuario("JOSE.PEREIRA"))
        self._novo(c, "Jo Lima", "804")                # curto demais: usa nome.sobrenome
        self.assertIsNotNone(self._usuario("JO.LIMA"))

    def test_estagiario_e_inativo_do_banco_de_horas_nao_ganham_acesso(self):
        c = self.cliente()
        self._novo(c, "Estagio Teste", "805", is_intern="1")
        self.assertIsNone(self._usuario("ESTAGIO"))

    def test_primeiro_login_trava_tudo_ate_trocar_a_senha(self):
        c = self.cliente()
        self._novo(c, "Helena Prado", "806")
        f = self.cliente("HELENA", "123")
        for url in ("/", "/agenda", "/mensagens", "/banco-horas/minha-area", "/favoritos", "/atualizacoes"):
            r = f.get(url)
            self.assertEqual(r.status_code, 302, url)
            self.assertIn("/minha-senha", r.headers["Location"], url)
        pagina = self.texto(f.get("/minha-senha"))
        self.assertIn("Defina uma nova senha", pagina)
        self.assertNotIn('id="busca-menu"', pagina)            # sem menu, sem pesquisa
        self.assertNotIn("Lançamentos", pagina)
        self.assertNotIn('id="op-temas"', pagina)
        self.post(f, "/minha-senha", {"atual": "123", "nova": "novaSenha9", "confirmar": "novaSenha9"})
        self.assertEqual(self._usuario("HELENA")["trocar_senha"], 0)
        self.assertEqual(f.get("/banco-horas/minha-area").status_code, 200)         # liberou


class FuncionarioComModulosDeRecepcao(Base):
    def test_sem_o_modulo_minha_area_nao_ha_redirecionamento_em_circulo(self):
        adm = self.cliente()
        self.post(adm, "/banco-horas/funcionarios/novo", {"clock_id": "850", "name": "Priscila Rocha", "start_date": "2026-09-01",
                                                          "opening_balance_date": "2026-09-01", "active": "1"})
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:      # a gestão deu módulos de recepção ao funcionário e tirou a "Minha área"
            con.execute("UPDATE usuarios SET modulos=? WHERE usuario='PRISCILA'", (json.dumps(["dashboard", "atendimentos", "agenda"]),))
            con.commit()
        finally:
            con.close()
        f = self.cliente("PRISCILA", "123")
        self.post(f, "/minha-senha", {"atual": "123", "nova": "novaSenha9", "confirmar": "novaSenha9"})
        f = self.cliente("PRISCILA", "novaSenha9")
        r = f.get("/", headers={"Referer": "http://localhost/"})   # clique em Início no menu
        self.assertEqual(r.status_code, 200)                       # tela inicial normal, sem redirecionar
        self.assertEqual(f.get("/atendimentos/novo").status_code, 200)

    def test_com_o_modulo_minha_area_continua_indo_para_ela(self):
        adm = self.cliente()
        self.post(adm, "/banco-horas/funcionarios/novo", {"clock_id": "851", "name": "Rita Souza", "start_date": "2026-09-01",
                                                          "opening_balance_date": "2026-09-01", "active": "1"})
        f = self.cliente("RITA", "123")
        self.post(f, "/minha-senha", {"atual": "123", "nova": "novaSenha9", "confirmar": "novaSenha9"})
        f = self.cliente("RITA", "novaSenha9")
        self.assertIn("/banco-horas/minha-area", f.get("/").headers["Location"])


class PerfilUsuarioEstagiario(Base):
    def _criar_pela_tela(self, c, nome, **extra):
        dados = {"usuario": nome, "senha": "abc123", "perfil": "usuario"}
        dados.update(extra)
        return self.post(c, "/admin/usuarios/novo" if False else "/usuarios/novo", dados)

    def test_formulario_tem_perfil_usuario_e_administrador_e_o_preset(self):
        c = self.cliente()
        pagina = self.texto(c.get("/usuarios/novo"))
        for esperado in ('name="perfil" value="usuario"', 'name="perfil" value="admin"', "Estagiário (lança fichas e vê a agenda)",
                         "Agenda: só consulta e impressão"):
            self.assertIn(esperado, pagina)
        self.assertEqual(modulos.PRESETS["estagiario"][1], ["atendimentos", "agenda_leitura"])

    def test_perfil_define_administrador(self):
        c = self.cliente()
        self.post(c, "/usuarios/novo", {"usuario": "COMUM1", "senha": "abc123", "perfil": "usuario", "modulos": ["atendimentos"]})
        self.post(c, "/usuarios/novo", {"usuario": "CHEFE1", "senha": "abc123", "perfil": "admin", "modulos": ["atendimentos"]})
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            self.assertEqual(con.execute("SELECT admin FROM usuarios WHERE usuario='COMUM1'").fetchone()[0], 0)
            self.assertEqual(con.execute("SELECT admin FROM usuarios WHERE usuario='CHEFE1'").fetchone()[0], 1)
        finally:
            con.close()

    def test_estagiario_lanca_fichas_e_so_ve_e_imprime_a_agenda(self):
        adm = self.cliente()
        self.criar_usuario("ESTAG", modulos.PRESETS["estagiario"][1])
        # a agenda do dia existe
        self.post(adm, "/agenda/criar", {"data": "2031-05-05", "exame": "OSSEA", "inicio": "08:00", "intervalo": "30", "qtd": "3", "vagas": "1"})
        e = self.cliente("ESTAG", "senha123")
        pagina = self.texto(e.get("/agenda?data=2031-05-05"))
        self.assertIn('data-somente-leitura="1"', pagina)
        self.assertIn("Agenda de exames", self.texto(e.get("/", headers={"Referer": "http://localhost/"})))   # aparece no menu
        self.assertEqual(e.get("/agenda/dia/2031-05-05").status_code, 200)           # consulta
        self.assertEqual(e.get("/agenda/mes?mes=2031-05").status_code, 200)
        self.assertEqual(e.get("/agenda/imprimir/2031-05-05.pdf").status_code, 200)    # imprimir
        # nada de alterar
        for rota, dados in (("/agenda/criar", {"data": "2031-05-06", "exame": "X", "inicio": "08:00", "intervalo": "30", "qtd": "2"}),
                            ("/agenda/horario/1/campo", {"campo": "paciente", "valor": "FULANO"}),
                            ("/agenda/horario/1/status", {"status": "VEIO"}),
                            ("/agenda/copiar", {"origem": "2031-05-05", "destino": "2031-05-09"}),
                            ("/agenda/bloquear", {"data": "2031-05-10"}), ("/agenda/espera", {"nome": "X"})):
            r = self.post(e, rota, dados)
            self.assertEqual(r.status_code, 302, rota)                               # recusado e devolvido ao início
        self.assertEqual(adm.get("/agenda/dia/2031-05-06").get_json()["agendas"], [])
        self.assertEqual(e.get("/agenda/relatorio").status_code, 302)
        # lança atendimento (fichas)
        self.assertEqual(e.get("/atendimentos/novo").status_code, 200)
        # e quem tem só consulta não vê "Criar agenda": o servidor recusa, a tela esconde
        self.assertIn("ag-leitura", open("app/static/css/agenda.css", encoding="utf-8").read())


if __name__ == "__main__":
    unittest.main()
