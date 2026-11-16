"""Ícones SVG (Lucide) do menu, da barra do topo e dos favoritos."""
import json
import os
import re
import unittest

from app import modulos, views_favoritos
from tests.test_chat_blindagens import Base

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPRITE = os.path.join(RAIZ, "app", "static", "img", "icones.svg")


class Icones(unittest.TestCase):
    def test_sprite_tem_todos_os_desenhos_com_traco_fino_e_currentcolor(self):
        s = open(SPRITE, encoding="utf-8").read()
        simbolos = set(re.findall(r'<symbol id="i-([a-z0-9-]+)"', s))
        for nome in modulos.NOMES_ICONES:
            self.assertIn(nome, simbolos, nome)
        self.assertIn('stroke="currentColor"', s)
        self.assertIn('stroke-width="1.75"', s)
        self.assertNotIn("http://", s.replace("http://www.w3.org/2000/svg", ""))       # nada de recurso externo
        self.assertTrue(os.path.exists(os.path.join(RAIZ, "app", "static", "img", "LICENSE-lucide.txt")))

    def test_toda_tela_do_menu_tem_icone_e_todo_tema_tambem(self):
        for grupo, itens in modulos.MENU:
            for _mod, rotulo, ep, _pref in itens:
                self.assertIn(ep, modulos.ICONES, rotulo)
            if grupo:
                self.assertIn(grupo, modulos.TEMA_ICONES, grupo)
        for nome in list(modulos.ICONES.values()) + list(modulos.TEMA_ICONES.values()):
            self.assertRegex(nome, r"^[a-z0-9-]+$")                          # nome de desenho, não emoji

    def test_favoritos_aceitam_so_desenhos_do_sprite(self):
        validos = {"agenda.pagina"}
        r = views_favoritos.normalizar(json.dumps({"itens": [{"ep": "agenda.pagina", "ico": "calendar-days"}]}), validos)
        self.assertEqual(r["itens"][0]["ico"], "calendar-days")
        for ruim in ("📅", "inexistente", "<script>"):
            r = views_favoritos.normalizar(json.dumps({"itens": [{"ep": "agenda.pagina", "ico": ruim}]}), validos)
            self.assertEqual(r["itens"][0]["ico"], "")


class IconesNasTelas(Base):
    def test_menu_barra_do_topo_e_favoritos_usam_svg(self):
        c = self.cliente()
        pagina = self.texto(c.get("/agenda"))
        # o endereço do sprite leva ?v=<versão do arquivo> (cache longo no navegador)
        self.assertRegex(pagina, r"img/icones\.svg(\?v=\d+)?#i-calendar-days")   # item do menu e barra do topo
        self.assertRegex(pagina, r"img/icones\.svg(\?v=\d+)?#i-calendar")         # tema Agenda
        self.assertNotIn("📅", pagina)
        self.assertIn('class="ico-item"', pagina)
        fav = self.texto(c.get("/favoritos"))
        self.assertIn('"icone": "calendar-days"', fav)
        self.assertEqual(c.get("/static/img/icones.svg").status_code, 200)


if __name__ == "__main__":
    unittest.main()
