"""Arquivar o perfil de um usuário e desligar o funcionário da empresa.

Arquivar tira o usuário da lista de Usuários e perfis (e o bloqueia: ele não entra mais), mas nada é apagado: o perfil, as
conversas e o histórico continuam disponíveis em "Ver arquivados", de onde dá para desarquivar. Desligar funcionário faz o
mesmo e encerra o cadastro dele no Banco de Horas (inativo, com data de desligamento, saindo da lista de funcionários e
indo para os arquivados); o histórico de ponto é mantido, porque é registro trabalhista.
"""
from __future__ import annotations

from datetime import date

from .db import agora


class ErroUsuario(ValueError):
    """Motivo pelo qual a ação não pode ser feita (mostrado ao usuário)."""


def _validar(db, uid, quem_id):
    u = db.execute('SELECT * FROM usuarios WHERE id=?', (uid,)).fetchone()
    if not u:
        raise ErroUsuario('Usuário não encontrado.')
    if u['id'] == quem_id:
        raise ErroUsuario('Você não pode arquivar o seu próprio perfil.')
    if u['sistema']:
        raise ErroUsuario('Este é um contato interno do sistema e não pode ser arquivado.')
    if u['admin'] and not db.execute('SELECT 1 FROM usuarios WHERE admin=1 AND ativo=1 AND id<>? AND COALESCE(sistema,0)=0',
                                     (uid,)).fetchone():
        raise ErroUsuario('Este é o único administrador ativo: crie outro administrador antes de arquivar.')
    return u


def arquivar(db, uid, quem_id):
    """Desativa e arquiva o perfil. Devolve o nome do usuário."""
    u = _validar(db, uid, quem_id)
    db.execute('UPDATE usuarios SET ativo=0, arquivado_em=? WHERE id=?', (agora(), uid))
    db.commit()
    return u['usuario']


def desarquivar(db, uid):
    """Volta o perfil para a lista (continua desativado até a administração reativar)."""
    u = db.execute('SELECT usuario, bh_funcionario_id FROM usuarios WHERE id=?', (uid,)).fetchone()
    if not u:
        raise ErroUsuario('Usuário não encontrado.')
    db.execute('UPDATE usuarios SET arquivado_em=NULL WHERE id=?', (uid,))
    if u['bh_funcionario_id']:
        db.execute('UPDATE bh_employees SET archived_at=NULL WHERE id=?', (u['bh_funcionario_id'],))
    db.commit()
    return u['usuario']


def desligar_funcionario(db, uid, quem_id):
    """Encerra o funcionário no Banco de Horas (inativo, com data de desligamento) e arquiva o perfil de acesso."""
    u = _validar(db, uid, quem_id)
    emp = u['bh_funcionario_id']
    if not emp:
        raise ErroUsuario('Este usuário não está ligado a um funcionário do Banco de Horas.')
    db.execute("UPDATE bh_employees SET active=0, end_date=COALESCE(NULLIF(end_date,''), ?), archived_at=?, updated_at=? WHERE id=?",
               (date.today().isoformat(), agora(), agora(), emp))
    return arquivar(db, uid, quem_id)
