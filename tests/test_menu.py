"""Barra lateral: ordem dos temas, pesquisa no topo e temas recolhíveis."""
import unittest

from app import modulos
from tests.test_chat_blindagens import Base

# Referer do próprio sistema: clicar em Início no menu manda esse cabeçalho (sem ele, a raiz leva à agenda)
DE_SISTEMA = {"Referer": "http://localhost/"}


class MenuTestes(Base):
    def test_ordem_dos_temas_por_relevancia(self):
        ordem = [g for g, _ in modulos.MENU]
        self.assertEqual(ordem[0], None)  # início, mensagens e dashboard no topo
        self.assertEqual(ordem[1:4], ["Agenda", "Lançamentos", "Cadastros"])
        self.assertEqual(ordem[-1], "Configuração")
        self.assertEqual(sorted(g for g in ordem if g), sorted(set(g for g in ordem if g)))  # nenhum tema repetido

    def test_nenhum_item_foi_perdido_na_reordenacao(self):
        itens = [t[1] for t in modulos.telas()]
        self.assertEqual(len(itens), 102)   # +1 Pendências Medcloud (anexos e laudos) | +1 Gasto de tokens (NucleAI) | +1 Medcloud (a contagem anterior, 98, já estava 1 abaixo do real) | 68 telas (menu + botões): inclui o Caixa diário, as telas da Qualidade e a pesquisa de satisfação; +1 Painéis do Início; +1 NucleAI: IA online; +1 Tabela de preços; +1 Prontuário do paciente; +1 Lembretes; +6 Estoque (Itens, Movimentações, Pedidos, Relatórios, Escrituração e Preços dos materiais)
        self.assertIn("arquivo_documentos", itens)
        self.assertIn("agenda_financeiro", itens)

    def test_nucleai_fica_logo_abaixo_de_inicio_e_so_para_administracao(self):
        rotulos = [i[1] for i in modulos.MENU[0][1]]
        self.assertEqual(rotulos[:2], ["Início", "NucleAI"])
        self.assertIn('href="/nucleai"', self.texto(self.cliente().get("/", headers=DE_SISTEMA)))
        self.criar_usuario("MENU_COMUM", list(modulos.CHAVES))   # tem todos os módulos, mas não é administrador
        comum = self.cliente("MENU_COMUM", "senha123")
        self.assertNotIn('href="/nucleai"', self.texto(comum.get("/")))
        self.assertEqual(comum.get("/nucleai").status_code, 302)   # bloqueado mesmo digitando o endereço
        for rota in ("/nucleai/conteudo", "/nucleai/config", "/nucleai/chamados", "/nucleai/relatorio.pdf"):
            self.assertEqual(comum.get(rota).status_code, 302, rota)

    def test_tema_do_perfil_e_gravado(self):
        self.criar_usuario("TEMA_USU", ["dashboard"])
        c = self.cliente("TEMA_USU", "senha123")
        self.assertEqual(self.post(c, "/meu-tema", {"tema": "azul"}).status_code, 200)
        self.assertIn('data-tema="azul"', self.texto(c.get("/")))
        # um tema que não existe volta ao padrão
        self.post(c, "/meu-tema", {"tema": "inexistente"})
        self.assertIn('data-tema="verde"', self.texto(c.get("/")))

    def test_barra_com_pesquisa_e_temas_recolhiveis(self):
        c = self.cliente()
        pagina = self.texto(c.get("/", headers=DE_SISTEMA))
        self.assertIn('id="busca-menu"', pagina)
        self.assertIn('data-tema-itens', pagina)
        self.assertIn('class="grupo"', pagina)
        self.assertIn("js/menu.js", pagina)
        self.assertIn('class="sem-resultado"', pagina)


if __name__ == "__main__":
    unittest.main()
