"""Lembretes em checklist: cada usuário cria os seus (ou a gestão cria um "para todos", que aparece a todos).

Um lembrete tem título, uma lista de itens (cada um com uma caixinha), data de início (antes dela não aparece) e,
opcionalmente, o reset diário das marcações. As marcações são de cada usuário (tabela `lembrete_marcas`).
Regras de edição: o dono edita o próprio lembrete; um "para todos" só a gestão edita (inclusive desativar e excluir).
Ao entrar no sistema, a janela de login lista os lembretes ativos de quem entrou (ver `pendentes`).
"""
from datetime import date

from . import hierarquia
from .db import agora

MAX_ITENS = 30
MAX_TEXTO = 200        # caracteres por item
MAX_TITULO = 120


class ErroLembrete(Exception):
    pass


def hoje():
    return date.today().isoformat()


def eh_gestao(db, u):
    """Gestão (Desenvolvedor ou Gestão, pela hierarquia): pode criar "para todos" e editar os "para todos"."""
    return hierarquia.nivel(db, u) >= hierarquia.GESTAO


def pode_editar(lembrete, uid, gestao):
    return bool(gestao) if lembrete['para_todos'] else lembrete['usuario_id'] == uid


def _buscar(db, lid):
    return db.execute('SELECT * FROM lembretes WHERE id=?', (lid,)).fetchone()


def _ler_itens(texto):
    itens = []
    for linha in (texto or '').replace('\r', '').split('\n'):
        linha = linha.strip()
        if not linha:
            continue
        if len(linha) > MAX_TEXTO:
            raise ErroLembrete('Cada item pode ter no máximo %d caracteres.' % MAX_TEXTO)
        itens.append(linha)
    if not itens:
        raise ErroLembrete('Informe pelo menos um item (um por linha).')
    if len(itens) > MAX_ITENS:
        raise ErroLembrete('Um lembrete pode ter no máximo %d itens.' % MAX_ITENS)
    return itens


def salvar(db, u, form, lid=None):
    """Cria (lid=None) ou altera um lembrete. Devolve o id. Levanta ErroLembrete com a mensagem para a tela."""
    gestao = eh_gestao(db, u)
    titulo = (form.get('titulo') or '').strip()
    if not titulo:
        raise ErroLembrete('Informe o título do lembrete.')
    if len(titulo) > MAX_TITULO:
        raise ErroLembrete('O título pode ter no máximo %d caracteres.' % MAX_TITULO)
    itens = _ler_itens(form.get('itens'))
    inicio = (form.get('data_inicio') or '').strip() or hoje()
    try:
        inicio = date.fromisoformat(inicio).isoformat()
    except ValueError:
        raise ErroLembrete('Data de início inválida.')
    reset = 1 if form.get('reset_diario') in ('1', 'on') else 0
    para_todos = 1 if gestao and form.get('para_todos') in ('1', 'on') else 0
    if lid is not None:
        atual = _buscar(db, lid)
        if not atual or not pode_editar(atual, u['id'], gestao):
            raise ErroLembrete('Lembrete não encontrado ou sem permissão para alterar.')
        # "para todos" só a gestão altera; quem não é gestão não transforma o próprio lembrete em "para todos"
        db.execute('UPDATE lembretes SET titulo=?, para_todos=?, data_inicio=?, reset_diario=? WHERE id=?',
                   (titulo, para_todos, inicio, reset, lid))
        existentes = db.execute('SELECT id FROM lembrete_itens WHERE lembrete_id=? ORDER BY ordem, id', (lid,)).fetchall()
        # os itens antigos são reaproveitados por posição: as marcações feitas continuam valendo
        for ordem, texto in enumerate(itens):
            if ordem < len(existentes):
                db.execute('UPDATE lembrete_itens SET ordem=?, texto=? WHERE id=?', (ordem, texto, existentes[ordem]['id']))
            else:
                db.execute('INSERT INTO lembrete_itens (lembrete_id, ordem, texto) VALUES (?,?,?)', (lid, ordem, texto))
        for sobra in existentes[len(itens):]:
            db.execute('DELETE FROM lembrete_marcas WHERE item_id=?', (sobra['id'],))
            db.execute('DELETE FROM lembrete_itens WHERE id=?', (sobra['id'],))
    else:
        cur = db.execute('INSERT INTO lembretes (usuario_id, titulo, para_todos, ativo, data_inicio, reset_diario, criado_em) '
                         'VALUES (?,?,?,1,?,?,?)', (u['id'], titulo, para_todos, inicio, reset, agora()))
        lid = cur.lastrowid
        for ordem, texto in enumerate(itens):
            db.execute('INSERT INTO lembrete_itens (lembrete_id, ordem, texto) VALUES (?,?,?)', (lid, ordem, texto))
    db.commit()
    return lid


def definir_ativo(db, u, lid, ativo):
    l = _buscar(db, lid)
    if not l or not pode_editar(l, u['id'], eh_gestao(db, u)):
        raise ErroLembrete('Lembrete não encontrado ou sem permissão para alterar.')
    db.execute('UPDATE lembretes SET ativo=? WHERE id=?', (1 if ativo else 0, lid))
    db.commit()


def excluir(db, u, lid):
    l = _buscar(db, lid)
    if not l or not pode_editar(l, u['id'], eh_gestao(db, u)):
        raise ErroLembrete('Lembrete não encontrado ou sem permissão para excluir.')
    db.execute('DELETE FROM lembrete_marcas WHERE lembrete_id=?', (lid,))
    db.execute('DELETE FROM lembrete_itens WHERE lembrete_id=?', (lid,))
    db.execute('DELETE FROM lembretes WHERE id=?', (lid,))
    db.commit()


def _visivel(db, u, lid):
    """O usuário enxerga o lembrete (é dele ou é "para todos")? Devolve a linha ou levanta ErroLembrete."""
    l = _buscar(db, lid)
    if not l or not (l['para_todos'] or l['usuario_id'] == u['id']):
        raise ErroLembrete('Lembrete não encontrado.')
    return l


def marcar(db, u, lid, iid, marcado):
    """Marca ou desmarca uma caixinha. Cada usuário guarda as próprias marcações."""
    l = _visivel(db, u, lid)
    if not l['ativo']:
        raise ErroLembrete('Este lembrete está desativado.')
    item = db.execute('SELECT id FROM lembrete_itens WHERE id=? AND lembrete_id=?', (iid, lid)).fetchone()
    if not item:
        raise ErroLembrete('Item não encontrado.')
    if marcado:
        db.execute('INSERT OR REPLACE INTO lembrete_marcas (lembrete_id, item_id, usuario_id, marcado_em, data) VALUES (?,?,?,?,?)',
                   (lid, iid, u['id'], agora(), hoje()))
    else:
        db.execute('DELETE FROM lembrete_marcas WHERE item_id=? AND usuario_id=?', (iid, u['id']))
    db.commit()


def desmarcar_tudo(db, u, lid):
    _visivel(db, u, lid)
    db.execute('DELETE FROM lembrete_marcas WHERE lembrete_id=? AND usuario_id=?', (lid, u['id']))
    db.commit()


def pendentes(db, u, gestao):
    """Lembretes ativos que o usuário deve ver hoje, com os itens e as marcações dele.

    Com reset diário, as marcações de outro dia são apagadas aqui (o item volta a aparecer desmarcado)."""
    dia = hoje()
    rows = db.execute('SELECT * FROM lembretes WHERE ativo=1 AND data_inicio<=? AND (para_todos=1 OR usuario_id=?) ORDER BY id',
                      (dia, u['id'])).fetchall()
    saida = []
    for l in rows:
        if l['reset_diario']:
            db.execute('DELETE FROM lembrete_marcas WHERE lembrete_id=? AND usuario_id=? AND data<>?', (l['id'], u['id'], dia))
        marcadas = {r['item_id'] for r in db.execute(
            'SELECT item_id FROM lembrete_marcas WHERE lembrete_id=? AND usuario_id=?', (l['id'], u['id'])).fetchall()}
        itens = db.execute('SELECT id, texto FROM lembrete_itens WHERE lembrete_id=? ORDER BY ordem, id', (l['id'],)).fetchall()
        saida.append({'id': l['id'], 'titulo': l['titulo'], 'para_todos': bool(l['para_todos']), 'reset_diario': bool(l['reset_diario']),
                      'pode_editar': pode_editar(l, u['id'], gestao),
                      'itens': [{'id': i['id'], 'texto': i['texto'], 'marcado': i['id'] in marcadas} for i in itens]})
    db.commit()
    return saida


def tem_pendentes(db, u):
    """Há algum lembrete ativo para este usuário hoje? (usado para decidir se a janela de login abre)"""
    r = db.execute('SELECT 1 FROM lembretes WHERE ativo=1 AND data_inicio<=? AND (para_todos=1 OR usuario_id=?) LIMIT 1',
                   (hoje(), u['id'])).fetchone()
    return r is not None


def listar(db, u, gestao):
    """Tela de gestão: os meus lembretes e os "para todos" (ativos e desativados)."""
    rows = db.execute('SELECT l.*, u.usuario AS dono FROM lembretes l JOIN usuarios u ON u.id = l.usuario_id '
                      'WHERE l.usuario_id=? OR l.para_todos=1 ORDER BY l.ativo DESC, l.id DESC', (u['id'],)).fetchall()
    saida = []
    for l in rows:
        n = db.execute('SELECT COUNT(*) FROM lembrete_itens WHERE lembrete_id=?', (l['id'],)).fetchone()[0]
        saida.append({'id': l['id'], 'titulo': l['titulo'], 'para_todos': bool(l['para_todos']), 'ativo': bool(l['ativo']),
                      'data_inicio': l['data_inicio'], 'reset_diario': bool(l['reset_diario']), 'dono': l['dono'], 'itens': n,
                      'pode_editar': pode_editar(l, u['id'], gestao)})
    return saida


def dados_para_form(db, lid):
    """Valores do formulário de edição (itens em texto, um por linha)."""
    l = _buscar(db, lid)
    if not l:
        return None
    itens = db.execute('SELECT texto FROM lembrete_itens WHERE lembrete_id=? ORDER BY ordem, id', (lid,)).fetchall()
    return {'id': l['id'], 'titulo': l['titulo'], 'para_todos': bool(l['para_todos']), 'data_inicio': l['data_inicio'],
            'reset_diario': bool(l['reset_diario']), 'itens': '\n'.join(r['texto'] for r in itens), 'usuario_id': l['usuario_id']}
