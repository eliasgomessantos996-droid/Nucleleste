"""Base de ajuda da NucleAI: temas -> módulos -> áreas -> instruções (três arquivos de conteúdo, na ordem do menu)."""
from .ajuda_conteudo_a import TEMAS_A
from .ajuda_conteudo_b import TEMAS_B
from .ajuda_conteudo_c import TEMAS_C

# tema = (título, [módulo]); módulo = (título, [(área, instruções)])
TEMAS = TEMAS_A + TEMAS_B + TEMAS_C
