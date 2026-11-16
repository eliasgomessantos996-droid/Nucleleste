"""Guias de convênio digitadas: SP/SADT Unimed e Pedido IPSEMG (formulário, gravação, impressão, exclusão)."""
import unittest

from app import db as dbmod
from tests.test_chat_blindagens import Base

UNIMED = {
    "10": "Maria da Silva",
    "8": "0001234567",
    "14": "CLINICA TESTE",
    "1": "123456",
    "13": "999",
    "31": "1234567",
    "15": "DR. FULANO DE TAL",
    "22": "2026-11-14",
    "36_1": "2026-11-14",
    "25_1": "40101010",
    "26_1": "TOMOGRAFIA DE TESTE",
    "27_1": "2",
    "40_1": "40101010",
    "41_1": "TOMOGRAFIA DE TESTE",
    "42_1": "2",
    "46_1": "150,00",
}

IPSEMG = {
    "3": "Joao Teste",
    "11": "E",
    "12": "N",
    "14": "Dor abdominal persistente",
    "4": "CLINICA TESTE",
    "5": "MAT99",
    "17_1": "41001010",
    "18_1": "EXAME DE TESTE",
    "19_1": "1",
}


class GuiasConvenio(Base):
    def ultimo_gid(self):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            return con.execute("SELECT MAX(id) FROM guias_convenio").fetchone()[0]
        finally:
            con.close()

    def cliente_id(self, nome):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            cur = con.execute("INSERT INTO clientes (nome, cartao_convenio) VALUES (?, ?)", (nome, "CARTAO-9"))
            con.commit()
            return cur.lastrowid
        finally:
            con.close()

    def salvar_e_imprimir(self, c, url, dados):
        r = self.post(c, url, dict(dados, acao="imprimir"))
        self.assertEqual(r.status_code, 302, self.texto(r)[:300])
        return c.get(r.headers["Location"])

    def test_formularios_abrem(self):
        c = self.cliente()
        self.assertEqual(c.get("/documentos/guias/unimed_sadt/nova").status_code, 200)
        self.assertEqual(c.get("/documentos/guias/ipsemg_pedido/nova").status_code, 200)
        self.assertEqual(c.get("/documentos/guias").status_code, 200)
        self.assertEqual(c.get("/documentos/guias/modelo_inexistente/nova").status_code, 404)
        self.assertEqual(c.get("/documentos/guia_unimed").status_code, 404)

    def test_unimed_salva_e_imprime(self):
        c = self.cliente()
        r = self.salvar_e_imprimir(c, "/documentos/guias/unimed_sadt/nova", UNIMED)
        self.assertEqual(r.status_code, 200)
        t = self.texto(r)
        self.assertIn("SP/SADT", t)
        self.assertIn("Unimed", t)
        self.assertIn("MARIA DA SILVA", t)
        self.assertIn("300,00", t)   # 2 x 150,00 (47, 59 e 65)
        cabecalho = t.split('class="g-topo"', 1)[1].split('class="g-faixa"', 1)[0]
        self.assertNotIn("Governador Valadares", cabecalho)
        self.assertIn("Unimed", cabecalho)

    def test_ipsemg_salva_e_imprime_com_x(self):
        c = self.cliente()
        r = self.salvar_e_imprimir(c, "/documentos/guias/ipsemg_pedido/nova", IPSEMG)
        t = self.texto(r)
        self.assertEqual(r.status_code, 200)
        self.assertIn("PEDIDO PARA DIAGNÓSTICO E TRATAMENTO", t)
        self.assertIn('<span class="g-x">X</span> Eletivo', t)
        self.assertIn('<span class="g-x"></span> Sim', t)
        self.assertIn("JOAO TESTE", t.upper())

    def test_dados_da_clinica_voltam_na_proxima_guia(self):
        c = self.cliente()
        self.salvar_e_imprimir(c, "/documentos/guias/unimed_sadt/nova", UNIMED)
        t = self.texto(c.get("/documentos/guias/unimed_sadt/nova"))
        self.assertIn('value="123456"', t)
        self.assertIn('value="CLINICA TESTE"', t)
        self.assertIn('value="1234567"', t)
        self.salvar_e_imprimir(c, "/documentos/guias/ipsemg_pedido/nova", IPSEMG)
        t = self.texto(c.get("/documentos/guias/ipsemg_pedido/nova"))
        self.assertIn('value="MAT99"', t)

    def test_cliente_na_url_preenche_nome(self):
        c = self.cliente()
        cid = self.cliente_id("JOANA CLIENTE TESTE")
        t = self.texto(c.get("/documentos/guias/unimed_sadt/nova?cliente=%d" % cid))
        self.assertIn('value="JOANA CLIENTE TESTE"', t)
        self.assertIn('value="CARTAO-9"', t)

    def test_excluir(self):
        c = self.cliente()
        self.post(c, "/documentos/guias/unimed_sadt/nova", dict(UNIMED, acao="salvar"))
        gid = self.ultimo_gid()
        self.assertEqual(c.get("/documentos/guias/%d/imprimir" % gid).status_code, 200)
        r = self.post(c, "/documentos/guias/%d/excluir" % gid, {})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(c.get("/documentos/guias/%d/imprimir" % gid).status_code, 404)


if __name__ == "__main__":
    unittest.main()
