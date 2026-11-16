"""Estoque de materiais e medicamentos: itens, entradas, baixas, ajuste, histórico de compras, estoque mínimo e permissões."""
import unittest

from app import estoque
from app import db as dbmod
from tests.test_chat_blindagens import Base


class EstoqueTestes(Base):
    def banco(self):
        return dbmod.conectar(self.app.config["DATABASE"])

    def criar(self, c, nome, minimo="0", saldo=None, tipo="MATERIAL", unidade="UN"):
        dados = {"nome": nome, "tipo": tipo, "unidade": unidade, "estoque_minimo": minimo, "codigo": "", "local": "", "obs": ""}
        if saldo is not None:
            dados["saldo_inicial"] = saldo
        r = self.post(c, "/estoque/item", dados)
        self.assertEqual(r.status_code, 302, r.get_data(as_text=True)[:200])
        con = self.banco()
        try:
            return con.execute("SELECT id FROM est_itens WHERE nome=?", (nome,)).fetchone()["id"]
        finally:
            con.close()

    def item(self, iid):
        con = self.banco()
        try:
            return dict(con.execute("SELECT * FROM est_itens WHERE id=?", (iid,)).fetchone())
        finally:
            con.close()

    def movimentos(self, iid):
        con = self.banco()
        try:
            return [dict(r) for r in con.execute("SELECT * FROM est_movimentos WHERE item_id=? ORDER BY id", (iid,))]
        finally:
            con.close()

    def alertas(self, nome):
        con = self.banco()
        try:
            return con.execute("SELECT COUNT(*) FROM chat_mensagens WHERE corpo LIKE ?", ("Estoque baixo: " + nome + " %",)).fetchone()[0]
        finally:
            con.close()

    def test_criar_item_com_saldo_inicial_gera_entrada(self):
        c = self.cliente()
        iid = self.criar(c, "LUVA TESTE SALDO", minimo="5", saldo="10")
        self.assertEqual(self.item(iid)["saldo"], 10)
        mov = self.movimentos(iid)
        self.assertEqual([(m["tipo"], m["qtd"], m["obs"]) for m in mov], [("ENTRADA", 10, "Saldo inicial")])
        self.assertEqual(mov[0]["saldo_apos"], 10)

    def test_nome_unico_sem_diferenciar_maiusculas(self):
        c = self.cliente()
        self.criar(c, "SERINGA UNICA")
        r = self.post(c, "/estoque/item", {"nome": "seringa unica", "tipo": "MATERIAL", "unidade": "UN", "estoque_minimo": "0"})
        self.assertEqual(r.status_code, 200)                       # nome repetido: volta ao formulário com o erro
        self.assertIn("Já existe um item", self.texto(r))
        con = self.banco()
        try:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM est_itens WHERE nome='SERINGA UNICA'").fetchone()[0], 1)
        finally:
            con.close()
        # o mesmo nome em outro tipo é outro item
        self.criar(c, "SERINGA UNICA", tipo="MEDICAMENTO")

    def test_entrada_atualiza_ultimo_valor_e_historico(self):
        c = self.cliente()
        iid = self.criar(c, "GAZE TESTE ENTRADA")
        self.post(c, "/estoque/%d/entrada" % iid, {"qtd": "4", "valor_unitario": "2,50", "fornecedor_nome": "Forn A",
                                                   "documento": "NF 1", "data_documento": "2026-10-01", "lote": "L1", "validade": "2028-01-31"})
        self.post(c, "/estoque/%d/entrada" % iid, {"qtd": "3", "valor_unitario": "3", "fornecedor_nome": "Forn B", "data_documento": "2026-10-10"})
        self.post(c, "/estoque/%d/entrada" % iid, {"qtd": "1"})   # sem valor: não mexe no último valor
        it = self.item(iid)
        self.assertEqual(it["saldo"], 8)
        self.assertEqual(it["ultimo_valor"], 3)
        self.assertEqual(it["ultima_compra"], "2026-10-10")
        compras = estoque.historico_compras(self.banco(), iid)
        self.assertEqual([x["fornecedor_nome"] for x in compras], ["FORN B", "FORN A"])   # mais recente primeiro
        self.assertEqual(len(estoque.ultimos_valores(self.banco(), iid, 1)), 1)
        pagina = self.texto(c.get("/estoque/%d/historico" % iid))
        self.assertIn("Últimos valores comprados", pagina)
        self.assertIn("NF 1", pagina)

    def test_entrada_com_fornecedor_cadastrado(self):
        c = self.cliente()
        con = self.banco()
        con.execute("INSERT INTO fornecedores (nome, ativo) VALUES ('FORNECEDOR CADASTRADO', 1)")
        con.commit()
        fid = con.execute("SELECT id FROM fornecedores WHERE nome='FORNECEDOR CADASTRADO'").fetchone()["id"]
        con.close()
        iid = self.criar(c, "CATETER TESTE FORN")
        self.post(c, "/estoque/%d/entrada" % iid, {"qtd": "2", "valor_unitario": "10", "fornecedor_id": str(fid)})
        mov = self.movimentos(iid)[-1]
        self.assertEqual(mov["fornecedor_id"], fid)
        self.assertEqual(mov["fornecedor_nome"], "FORNECEDOR CADASTRADO")

    def test_saida_reduz_e_recusa_saldo_negativo(self):
        c = self.cliente()
        iid = self.criar(c, "AGULHA TESTE SAIDA", saldo="5")
        self.post(c, "/estoque/%d/saida" % iid, {"qtd": "2", "motivo": "Uso", "obs": "paciente 1"})
        self.assertEqual(self.item(iid)["saldo"], 3)
        r = self.post(c, "/estoque/%d/saida" % iid, {"qtd": "4", "motivo": "Perda"})
        self.assertEqual(r.status_code, 302)                       # volta à lista com a mensagem de erro
        self.assertEqual(self.item(iid)["saldo"], 3)               # nada foi gravado
        self.assertEqual(len(self.movimentos(iid)), 2)
        with c.session_transaction() as s:
            self.assertTrue(any("Saldo insuficiente" in m for _cat, m in s.get("_flashes", [])))

    def test_saida_exige_motivo_da_lista(self):
        c = self.cliente()
        iid = self.criar(c, "SORO TESTE MOTIVO", saldo="2")
        self.post(c, "/estoque/%d/saida" % iid, {"qtd": "1", "motivo": "Sumiço"})
        self.assertEqual(self.item(iid)["saldo"], 2)

    def test_ajuste_de_inventario(self):
        c = self.cliente()
        iid = self.criar(c, "LUVA TESTE AJUSTE", saldo="10")
        self.post(c, "/estoque/%d/ajuste" % iid, {"contagem": "7", "obs": ""})   # sem motivo: recusa
        self.assertEqual(self.item(iid)["saldo"], 10)
        self.post(c, "/estoque/%d/ajuste" % iid, {"contagem": "7", "obs": "contagem de fim de mês"})
        it = self.item(iid)
        self.assertEqual(it["saldo"], 7)
        ajuste = self.movimentos(iid)[-1]
        self.assertEqual((ajuste["tipo"], ajuste["sentido"], ajuste["qtd"], ajuste["saldo_apos"]), ("AJUSTE", -1, 3, 7))
        self.post(c, "/estoque/%d/ajuste" % iid, {"contagem": "9", "obs": "sobra"})
        self.assertEqual(self.item(iid)["saldo"], 9)
        self.assertEqual(self.movimentos(iid)[-1]["sentido"], 1)

    def test_situacao_abaixo_e_zerado(self):
        c = self.cliente()
        zerado = self.criar(c, "ITEM SITUACAO ZERADO", minimo="2")
        abaixo = self.criar(c, "ITEM SITUACAO ABAIXO", minimo="5", saldo="5")
        ok = self.criar(c, "ITEM SITUACAO OK", minimo="2", saldo="9")
        sem_minimo = self.criar(c, "ITEM SITUACAO SEM MINIMO", saldo="1")
        mapa = {i["id"]: i["situacao"] for i in estoque.itens(self.banco(), busca="ITEM SITUACAO")}
        self.assertEqual(mapa[zerado], "zerado")
        self.assertEqual(mapa[abaixo], "abaixo")
        self.assertEqual(mapa[ok], "ok")
        self.assertEqual(mapa[sem_minimo], "ok")
        # zerado com mínimo também está no mínimo ou abaixo, então entra no filtro "só abaixo do mínimo"
        abaixo_lista = {i["id"] for i in estoque.itens(self.banco(), busca="ITEM SITUACAO", so_abaixo=True)}
        self.assertEqual(abaixo_lista, {zerado, abaixo})
        self.assertIn("abaixo do mínimo", self.texto(c.get("/estoque")))

    def test_alerta_enviado_uma_vez_e_reenviado_so_depois_de_repor(self):
        c = self.cliente()
        iid = self.criar(c, "COMPRESSA ALERTA", minimo="3", saldo="6")
        self.assertEqual(self.alertas("COMPRESSA ALERTA"), 0)
        self.post(c, "/estoque/%d/saida" % iid, {"qtd": "3", "motivo": "Uso"})       # 3 = mínimo: avisa
        self.assertEqual(self.alertas("COMPRESSA ALERTA"), 1)
        con = self.banco()
        admin = con.execute("SELECT id FROM usuarios WHERE usuario='ADMIN'").fetchone()["id"]
        msg = con.execute("SELECT corpo, para_id FROM chat_mensagens WHERE corpo LIKE 'Estoque baixo: COMPRESSA ALERTA%'").fetchone()
        con.close()
        self.assertEqual(msg["para_id"], admin)
        self.assertIn("(mínimo 3)", msg["corpo"])
        self.post(c, "/estoque/%d/saida" % iid, {"qtd": "1", "motivo": "Uso"})       # continua baixo: não repete
        self.assertEqual(self.alertas("COMPRESSA ALERTA"), 1)
        self.post(c, "/estoque/%d/entrada" % iid, {"qtd": "5"})                       # reposto acima do mínimo
        self.post(c, "/estoque/%d/saida" % iid, {"qtd": "4", "motivo": "Uso"})       # caiu de novo: avisa outra vez
        self.assertEqual(self.alertas("COMPRESSA ALERTA"), 2)

    def test_permissoes_do_modulo(self):
        self.criar_usuario("ESTQ_SEM_MODULO", ["dashboard"])
        self.criar_usuario("ESTQ_COM_MODULO", ["estoque"])
        sem = self.cliente("ESTQ_SEM_MODULO", "senha123")
        com = self.cliente("ESTQ_COM_MODULO", "senha123")
        self.assertEqual(sem.get("/estoque").status_code, 302)
        self.assertEqual(sem.get("/estoque/movimentos").status_code, 302)
        self.assertEqual(com.get("/estoque").status_code, 200)
        self.assertEqual(com.get("/estoque/movimentos").status_code, 200)

    def test_paginas_respondem(self):
        c = self.cliente()
        iid = self.criar(c, "PAGINA TESTE ESTOQUE", minimo="1", saldo="4")
        self.assertEqual(c.get("/estoque").status_code, 200)
        self.assertEqual(c.get("/estoque?tipo=MEDICAMENTO&busca=PAGINA&abaixo=1&inativos=1").status_code, 200)
        self.assertEqual(c.get("/estoque/item").status_code, 200)
        self.assertEqual(c.get("/estoque/item/%d" % iid).status_code, 200)
        self.assertEqual(c.get("/estoque/%d/historico" % iid).status_code, 200)
        self.assertEqual(c.get("/estoque/movimentos?de=2026-01-01&ate=2026-12-31&item=%d&tipo=SAIDA" % iid).status_code, 200)
        self.assertEqual(c.get("/estoque/item/999999").status_code, 404)

    def test_desativar_e_excluir(self):
        c = self.cliente()
        com_mov = self.criar(c, "ITEM COM MOVIMENTO")
        self.post(c, "/estoque/%d/entrada" % com_mov, {"qtd": "1"})
        self.post(c, "/estoque/item/%d/excluir" % com_mov, {})
        self.assertIsNotNone(self.item(com_mov))                  # tem histórico: não exclui
        sem_mov = self.criar(c, "ITEM SEM MOVIMENTO")
        self.post(c, "/estoque/item/%d/excluir" % sem_mov, {})
        con = self.banco()
        try:
            self.assertIsNone(con.execute("SELECT id FROM est_itens WHERE id=?", (sem_mov,)).fetchone())
        finally:
            con.close()
        # item desativado não recebe movimento
        self.post(c, "/estoque/item/%d" % com_mov, {"nome": "ITEM COM MOVIMENTO", "tipo": "MATERIAL", "unidade": "UN", "estoque_minimo": "0"})
        self.assertEqual(self.item(com_mov)["ativo"], 0)
        self.post(c, "/estoque/%d/entrada" % com_mov, {"qtd": "1"})
        self.assertEqual(self.item(com_mov)["saldo"], 1)


if __name__ == "__main__":
    unittest.main()
