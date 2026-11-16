"""Saúde do sistema: acesso só para administração e gerência, e os indicadores da tela."""
import unittest

from app import db as dbmod
from tests.test_chat_blindagens import Base


class SaudeTestes(Base):
    def test_gestao_ve_e_os_outros_nao(self):
        self.criar_usuario("SAU_NADA", ["atendimentos"])
        self.criar_usuario("SAU_GER", ["gerencia"])
        self.assertEqual(self.cliente("SAU_NADA", "senha123").get("/saude").status_code, 302)
        ger = self.cliente("SAU_GER", "senha123")
        self.assertEqual(ger.get("/saude").status_code, 200)
        self.assertEqual(self.cliente().get("/saude").status_code, 200)  # administrador

    def test_indicadores_e_erros_registrados(self):
        con = dbmod.conectar(self.app.config["DATABASE"])
        ctx = self.app.app_context()
        ctx.push()
        try:
            from app.views_saude import indicadores
            s = indicadores(con)
            self.assertIn("versao", s)
            self.assertGreater(s["disco_livre_gb"], 0)
            self.assertEqual(s["caixas_abertos"], 0)
            # um erro interno gravado no registro aparece na lista de erros
            con.execute("INSERT INTO auditoria (data_hora, usuario, modulo, acao, detalhe, rota, ip) VALUES "
                        "('2026-01-01 10:00:00', 'X', 'Sistema', 'Erro interno', 'ValueError: teste', '/x', '127.0.0.1')")
            con.commit()
            self.assertEqual(indicadores(con)["erros"][0]["detalhe"], "ValueError: teste")
        finally:
            ctx.pop()
            con.close()


class AvaliacaoTestes(unittest.TestCase):
    def test_espaco_livre_por_cores(self):
        from app import saude
        nec = saude.necessario_gb(50, 500)   # 11 GB com a regra de 20 vezes
        self.assertAlmostEqual(nec, 10.7, delta=.1)
        self.assertEqual(saude.nivel_disco(5, nec), saude.RUIM)      # menos do que o sistema precisa: vermelho
        self.assertEqual(saude.nivel_disco(20, nec), saude.MEDIO)    # pouca folga: amarelo
        self.assertEqual(saude.nivel_disco(60, nec), saude.BOM)      # verde
        self.assertEqual(saude.nivel_disco(200, nec), saude.OTIMO)   # azul
        self.assertEqual(saude.nivel_disco(0.5, 2), saude.RUIM)      # menos de 1 GB é sempre vermelho

    def test_demais_niveis(self):
        from app import saude as s
        self.assertEqual([s.nivel_backup(x) for x in (None, 0.5, 2, 6, 9)], [s.RUIM, s.OTIMO, s.BOM, s.MEDIO, s.RUIM])
        self.assertEqual([s.nivel_caixa(1, 0), s.nivel_caixa(0, 2), s.nivel_caixa(0, 0)], [s.RUIM, s.BOM, s.OTIMO])
        self.assertEqual([s.nivel_documentos(1, 0), s.nivel_documentos(0, 2), s.nivel_documentos(0, 0)], [s.RUIM, s.MEDIO, s.OTIMO])
        self.assertEqual([s.nivel_erros(5, 5), s.nivel_erros(1, 1), s.nivel_erros(0, 2), s.nivel_erros(0, 0)], [s.RUIM, s.MEDIO, s.BOM, s.OTIMO])
        self.assertEqual([s.nivel_geral(x) for x in (100, 75, 50, 20)], [s.OTIMO, s.BOM, s.MEDIO, s.RUIM])

    def test_nota_e_mensagem(self):
        from app import saude as s

        def bruto(**mudar):
            d = {"banco_mb": 10, "backups_mb": 50, "disco_livre_gb": 300, "disco_total_gb": 500, "backup": {"quando": "01/01/2026 10:00", "tamanho_mb": 9.0},
                 "backup_idade_dias": 0.2, "banco_integro": True, "caixas_abertos": 0, "caixas_antigos": 0, "docs_vencidos": 0,
                 "docs_a_vencer": 0, "dias_vencimento": 60, "erros_24h": 0, "erros_7d": 0}
            d.update(mudar)
            return d
        perfeito = s.avaliar(bruto())
        self.assertEqual((perfeito["nota"], perfeito["nivel"]), (100, s.OTIMO))
        ruim = s.avaliar(bruto(disco_livre_gb=1.5, backup=None, backup_idade_dias=None, banco_integro=False))
        self.assertEqual(ruim["nivel"], s.RUIM)
        self.assertEqual({i["chave"]: i["nivel"] for i in ruim["itens"]}["disco"], s.RUIM)
        self.assertLess(ruim["nota"], 45)


class PaginaSaude(Base):
    def test_pagina_mostra_cores_e_desenhos(self):
        r = self.cliente().get("/saude")
        t = self.texto(r)
        self.assertEqual(r.status_code, 200)
        for marca in ("sd-hero", "sd-card", "Espaço livre", "Último backup", "Azul · Ótimo", "Vermelho · Crítico", "saude.css", "saude.js"):
            self.assertIn(marca, t)
        self.assertEqual(t.count('class="sd-card'), 6)
        self.assertIn("<svg", t)
        self.assertIn("Nenhum erro interno registrado.", t)


if __name__ == "__main__":
    unittest.main()
