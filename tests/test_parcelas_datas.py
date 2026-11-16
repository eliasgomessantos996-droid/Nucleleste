"""Compra parcelada: vencimento de cada parcela editável (qualquer intervalo, não só mensal)."""
import unittest

from app import db as dbmod
from app import fornecedores as forn
from tests.test_chat_blindagens import Base


class DatasDasParcelas(Base):
    def _contas(self, descricao):
        con = dbmod.conectar(self.app.config["DATABASE"])
        try:
            return con.execute("SELECT * FROM contas WHERE descricao=? ORDER BY parcela_n", (descricao,)).fetchall()
        finally:
            con.close()

    def test_planejar_com_datas_manuais_e_padrao_mensal_nas_vazias(self):
        p = forn.planejar_parcelas(90, "2026-10-30", 3, True, ["2026-10-30", "2026-11-14", ""])
        self.assertEqual([x[1] for x in p], ["2026-10-30", "2026-11-14", "2026-12-30"])
        self.assertEqual([x[2] for x in p], [30.0, 30.0, 30.0])
        for ruim in (["", "31/31/2026", ""], ["2026-10-30", "xx", ""]):
            with self.assertRaises(forn.ErroFornecedor):
                forn.planejar_parcelas(90, "2026-10-30", 3, True, ruim)

    def test_tela_lanca_as_datas_digitadas(self):
        c = self.cliente()
        dados = {"descricao": "geladeira", "categoria": "Material de escritório", "vencimento": "2026-10-30", "valor": "300,00",
                 "parcelar": "1", "parcelas": "3", "parcela_tipo": "total",
                 "venc_parcela_1": "2026-10-30", "venc_parcela_2": "2026-11-14", "venc_parcela_3": "2026-12-01"}
        self.post(c, "/contas/nova", dados)
        ps = self._contas("GELADEIRA")
        self.assertEqual([p["vencimento"] for p in ps], ["2026-10-30", "2026-11-14", "2026-12-01"])    # 15 dias e depois 17: livres
        self.assertEqual([p["parcela_n"] for p in ps], [1, 2, 3])

    def test_sem_datas_continua_mensal(self):
        c = self.cliente()
        self.post(c, "/contas/nova", {"descricao": "mensal", "categoria": "Material de escritório", "vencimento": "2026-10-30",
                                      "valor": "200,00", "parcelar": "1", "parcelas": "2", "parcela_tipo": "total"})
        self.assertEqual([p["vencimento"] for p in self._contas("MENSAL")], ["2026-10-30", "2026-11-30"])

    def test_data_invalida_nao_lanca_nada_e_formulario_traz_o_calendario(self):
        c = self.cliente()
        r = self.post(c, "/contas/nova", {"descricao": "invalida", "categoria": "Material de escritório", "vencimento": "2026-10-30",
                                          "valor": "200,00", "parcelar": "1", "parcelas": "2", "parcela_tipo": "total",
                                          "venc_parcela_1": "2026-10-30", "venc_parcela_2": "data errada"})
        self.assertEqual(self._contas("INVALIDA"), [])
        self.assertIn("A data da parcela 2 é inválida", self.texto(r))
        pagina = self.texto(c.get("/contas/nova"))
        for esperado in ('id="f-grade"', "Vencimento de cada parcela", "Refazer datas mensais"):
            self.assertIn(esperado, pagina)


if __name__ == "__main__":
    unittest.main()
