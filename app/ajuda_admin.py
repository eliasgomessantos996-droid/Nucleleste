"""Edição do conteúdo da ajuda da NucleAI pela administração: corrigir um texto, criar áreas, módulos e temas.

A base original fica no código (ajuda_conteudo_*.py) e é atualizada a cada versão; as edições da administração ficam no
banco (`ajuda_conteudo`) e valem por cima dela. "Restaurar original" apaga a edição de uma área.
"""
from __future__ import annotations

from . import ajuda, modulos
from .ajuda_base import TEMAS
from .db import agora

MAX_TITULO = 70
MAX_TEXTO = 1800
MIN_TEXTO = 20


class ErroConteudo(ValueError):
    """Erro de validação mostrado à administração."""


def _limpo(s):
    return ' '.join(str(s or '').split())


def _texto(s):
    return str(s or '').replace('\r\n', '\n').replace('\r', '\n').strip()


def _original(tema, modulo, area):
    """Texto original (do código) da área, ou None se ela não existe na base."""
    for t, mods in TEMAS:
        if t != tema:
            continue
        for m, areas in mods:
            if m != modulo:
                continue
            for a, x in areas:
                if a == area:
                    return x
    return None


def _validar_texto(texto):
    if len(texto) < MIN_TEXTO:
        raise ErroConteudo('Escreva o texto da ajuda (pelo menos %d letras).' % MIN_TEXTO)
    if len(texto) > MAX_TEXTO:
        raise ErroConteudo('O texto pode ter no máximo %d caracteres (tem %d).' % (MAX_TEXTO, len(texto)))


def _validar_titulo(nome, rotulo):
    if not nome:
        raise ErroConteudo('Informe %s.' % rotulo)
    if len(nome) > MAX_TITULO:
        raise ErroConteudo('%s pode ter no máximo %d caracteres.' % (rotulo.capitalize(), MAX_TITULO))


def editar(db, usuario, tema, modulo, area, texto):
    """Troca o texto de uma área (da base ou criada pela administração)."""
    texto = _texto(texto)
    _validar_texto(texto)
    nova = db.execute("SELECT id FROM ajuda_conteudo WHERE tema=? AND modulo=? AND area=? AND estado='NOVA'",
                      (tema, modulo, area)).fetchone()
    if nova:
        db.execute('UPDATE ajuda_conteudo SET texto=?, atualizado_em=?, atualizado_por=? WHERE id=?', (texto, agora(), usuario, nova['id']))
    else:
        original = _original(tema, modulo, area)
        if original is None:
            raise ErroConteudo('Esta área não existe mais.')
        if texto == original.strip():
            db.execute("DELETE FROM ajuda_conteudo WHERE tema=? AND modulo=? AND area=? AND estado='EDITADA'", (tema, modulo, area))
        else:
            db.execute("INSERT INTO ajuda_conteudo (tema, modulo, area, texto, estado, atualizado_em, atualizado_por) VALUES (?,?,?,?,'EDITADA',?,?) "
                       "ON CONFLICT(tema, modulo, area) DO UPDATE SET texto=excluded.texto, estado='EDITADA', "
                       "atualizado_em=excluded.atualizado_em, atualizado_por=excluded.atualizado_por",
                       (tema, modulo, area, texto, agora(), usuario))
    db.commit()
    ajuda.invalidar()


def restaurar(db, tema, modulo, area):
    db.execute("DELETE FROM ajuda_conteudo WHERE tema=? AND modulo=? AND area=? AND estado='EDITADA'", (tema, modulo, area))
    db.commit()
    ajuda.invalidar()


def criar(db, usuario, tema, modulo, area, texto, chave_acesso=''):
    """Cria uma área; se o módulo ou o tema não existem, eles passam a existir. `chave_acesso`: módulo de permissão exigido
    (só vale para módulo novo; vazio = todos os usuários)."""
    tema, modulo, area = _limpo(tema), _limpo(modulo), _limpo(area)
    texto = _texto(texto)
    _validar_titulo(tema, 'o tema')
    _validar_titulo(modulo, 'o módulo')
    _validar_titulo(area, 'o título da área')
    _validar_texto(texto)
    chave_acesso = (chave_acesso or '').strip()
    if chave_acesso and chave_acesso != '__admin__' and chave_acesso not in modulos.CHAVES:
        raise ErroConteudo('Módulo de permissão inválido.')
    B = ajuda.base(db)
    if B.localizar(tema, modulo, area):
        raise ErroConteudo('Já existe uma área com este tema, módulo e título.')
    db.execute("INSERT INTO ajuda_conteudo (tema, modulo, area, texto, estado, chave_acesso, atualizado_em, atualizado_por) "
               "VALUES (?,?,?,?,'NOVA',?,?,?)", (tema, modulo, area, texto, chave_acesso or None, agora(), usuario))
    db.commit()
    ajuda.invalidar()


def excluir(db, cid):
    """Só áreas criadas pela administração podem ser excluídas (as da base são restauradas, não removidas)."""
    cur = db.execute("DELETE FROM ajuda_conteudo WHERE id=? AND estado='NOVA'", (cid,))
    db.commit()
    ajuda.invalidar()
    if not cur.rowcount:
        raise ErroConteudo('Só dá para excluir áreas criadas pela administração.')


def arvore_para_tela(db):
    """Árvore efetiva com o estado de cada área (Original, Editada ou Nova) e o id das criadas pela administração."""
    B = ajuda.base(db)
    linhas = {(r['tema'], r['modulo'], r['area']): r for r in db.execute('SELECT * FROM ajuda_conteudo')}
    saida = []
    for tema, mods in B.temas:
        t = {'titulo': tema, 'modulos': []}
        for modulo, areas in mods:
            m = {'titulo': modulo, 'areas': [], 'acesso': B.acesso.get((tema, modulo), 'livre')}
            for area, texto in areas:
                r = linhas.get((tema, modulo, area))
                m['areas'].append({'titulo': area, 'texto': texto, 'estado': r['estado'] if r else 'ORIGINAL',
                                   'id': r['id'] if r else None, 'por': r['atualizado_por'] if r else None,
                                   'em': r['atualizado_em'] if r else None, 'original': _original(tema, modulo, area)})
            t['modulos'].append(m)
        saida.append(t)
    return saida
