"""Hierarquia de perfis: Desenvolvedor > Gestão > Outros usuários.

- Desenvolvedor (perfil DESENVOLVEDOR): edita a gestão e os demais usuários, e é o único que mexe nele mesmo e libera o módulo do suporte.
- Gestão (administradores): edita os outros usuários e a própria gestão, mas nunca o desenvolvedor.
- Outros usuários: só editam usuários comuns se a gestão liberar o módulo "Gerenciar usuários" e, mesmo assim, só entregam o que eles próprios têm."""
from __future__ import annotations

from . import suporte

DEV, GESTAO, USUARIO = 3, 2, 1
ROTULOS = {DEV: 'Desenvolvedor', GESTAO: 'Gestão', USUARIO: 'Usuário'}
MOD_GERIR = 'usuarios_gerir'
SO_DEV = ('suporte_dev',)                 # só o desenvolvedor concede ou retira
SO_GESTAO = (MOD_GERIR, 'enfermagem')     # um usuário comum nunca concede (a gestão libera)


def nivel(db, u):
    if u is None:
        return USUARIO
    if suporte.usuario_dev_id(db) == u['id']:
        return DEV
    return GESTAO if u['admin'] else USUARIO


def pode_gerir(db, ator, alvo):
    """`ator` pode editar o perfil, a senha, a situação ou o arquivamento de `alvo`?"""
    na, nb = nivel(db, ator), nivel(db, alvo)
    if na == DEV:
        return True
    if nb == DEV:
        return False
    if na == GESTAO:
        return True
    return MOD_GERIR in _mods(ator) and nb == USUARIO and alvo['id'] != ator['id']


def _mods(u):
    from . import modulos
    return modulos.modulos_do_usuario(u)


def ajustar_marcados(db, ator, alvo, marcados, admin_flag):
    """Aplica os limites da hierarquia ao que o formulário pediu. Devolve (módulos, administrador, erros)."""
    na = nivel(db, ator)
    atual = set(_mods(alvo)) if alvo is not None and not alvo['admin'] else set()
    marcados = set(marcados)
    erros = []
    if na < DEV:                                              # módulos do desenvolvedor ficam como estavam
        marcados = (marcados - set(SO_DEV)) | (atual & set(SO_DEV))
    if na == USUARIO:
        marcados = (marcados - set(SO_GESTAO)) | (atual & set(SO_GESTAO))
        novos = marcados - atual
        if novos - _mods(ator):
            erros.append('Você só pode liberar módulos que você mesmo possui.')
        if admin_flag and not (alvo is not None and alvo['admin']):
            erros.append('Só a gestão pode criar administradores.')
        admin_flag = bool(alvo['admin']) if alvo is not None else False
    return marcados, admin_flag, erros


# ------------------------------------------------------------------ login
SEM_HISTORICO = ('auditoria', 'acessos')   # o registro do que aconteceu continua com o login que a pessoa tinha na hora


def pode_mudar_login(db, ator):
    """Só o desenvolvedor e a gestão trocam o login (nome de usuário) de um perfil; o nome da pessoa não muda."""
    return nivel(db, ator) >= GESTAO


def validar_login(db, uid, novo):
    """Devolve a mensagem de erro (ou None) para o novo login do perfil `uid`."""
    if not 3 <= len(novo) <= 80:
        return 'O login deve ter entre 3 e 80 caracteres.'
    if db.execute('SELECT 1 FROM usuarios WHERE usuario=? AND id<>?', (novo, uid)).fetchone():
        return 'Já existe outro usuário com o login %s.' % novo
    return None


def renomear_login(db, uid, novo):
    """Troca o login e leva junto os registros que se ligam ao usuário pelo nome (ex.: caixa aberto). Devolve o login antigo."""
    antigo = db.execute('SELECT usuario FROM usuarios WHERE id=?', (uid,)).fetchone()[0]
    db.execute('UPDATE usuarios SET usuario=? WHERE id=?', (novo, uid))
    for (tabela,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall():
        if tabela in SEM_HISTORICO or tabela == 'usuarios':
            continue
        if any(c[1] == 'usuario' for c in db.execute('PRAGMA table_info("%s")' % tabela).fetchall()):
            db.execute('UPDATE "%s" SET usuario=? WHERE usuario=? COLLATE NOCASE' % tabela, (novo, antigo))
    return antigo
