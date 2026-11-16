"""Registros de atividades: quem fez o quê e quando."""
import json
import sqlite3
from datetime import date, timedelta

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from . import agenda, login_obrigatorio
from .db import agora, get_db

bp = Blueprint('reg', __name__)


@bp.route('/registros')
@login_obrigatorio
def registros():
    db = get_db()
    a = request.args
    hoje = date.today()
    de = a.get('de') or (hoje - timedelta(days=6)).isoformat()
    ate = a.get('ate') or hoje.isoformat()
    usuario, modulo, q = (a.get('usuario') or '').strip(), (a.get('modulo') or '').strip(), (a.get('q') or '').strip()
    # data_hora >= de e < dia seguinte a ate: mesmo resultado de substr(...) BETWEEN, mas usa o índice de data_hora
    try:
        ate_mais = (date.fromisoformat(ate) + timedelta(days=1)).isoformat()
    except ValueError:
        ate_mais = ate + '~'
    where, params = ['data_hora >= ? AND data_hora < ?'], [de, ate_mais]
    if usuario:
        where.append('usuario=?'); params.append(usuario)
    if modulo:
        where.append('modulo=?'); params.append(modulo)
    if q:
        where.append("(UPPER(COALESCE(detalhe,'')) LIKE ? OR UPPER(COALESCE(acao,'')) LIKE ?)")
        params += ['%' + q.upper() + '%'] * 2
    w = ' AND '.join(where)
    rows = db.execute("SELECT id, data_hora, usuario, modulo, acao, detalhe, (instr(COALESCE(acao,''), 'Feito com auxílio da NucleAI') > 0) AS com_nucleai, "
                      '(desfazer IS NOT NULL) AS tem_desfazer, desfeito_em, '
                      'desfeito_por FROM auditoria WHERE %s ORDER BY id DESC LIMIT 1500' % w, params).fetchall()
    por_usuario = db.execute('SELECT COALESCE(usuario,\'(sistema)\') AS rotulo, COUNT(*) AS qtd FROM auditoria WHERE %s '
                             'GROUP BY 1 ORDER BY 2 DESC LIMIT 8' % w, params).fetchall()
    por_modulo = db.execute('SELECT COALESCE(modulo,\'-\') AS rotulo, COUNT(*) AS qtd FROM auditoria WHERE %s '
                            'GROUP BY 1 ORDER BY 2 DESC LIMIT 8' % w, params).fetchall()
    total = db.execute('SELECT COUNT(*) FROM auditoria WHERE ' + w, params).fetchone()[0]
    usuarios = [r[0] for r in db.execute("SELECT DISTINCT usuario FROM auditoria WHERE COALESCE(usuario,'')<>'' ORDER BY 1")]
    modulos_lista = [r[0] for r in db.execute("SELECT DISTINCT modulo FROM auditoria WHERE COALESCE(modulo,'')<>'' ORDER BY 1")]
    return render_template('registros.html', rows=rows, total=total, de=de, ate=ate, usuario=usuario, modulo=modulo, q=q,
                           por_usuario=por_usuario, por_modulo=por_modulo, usuarios=usuarios, modulos_lista=modulos_lista,
                           pode_desfazer=_pode_desfazer())


def _pode_desfazer():
    return bool(g.usuario['admin']) or 'gerencia' in (g.get('modulos') or ())


@bp.route('/registros/<int:rid>/desfazer', methods=['POST'])
@login_obrigatorio
def desfazer(rid):
    """Desfaz uma ação do registro (só administrador e gerência). Só funciona se os dados ainda estão como a ação os deixou."""
    voltar = request.form.get('voltar') or ''
    destino = voltar if voltar.startswith('/registros') else url_for('reg.registros')
    if not _pode_desfazer():
        flash('Somente o administrador e a gerência podem desfazer ações.', 'erro')
        return redirect(destino)
    db = get_db()
    r = db.execute('SELECT id, acao, desfazer, desfeito_em FROM auditoria WHERE id=?', (rid,)).fetchone()
    if not r or not r['desfazer']:
        flash('Esta ação não pode ser desfeita.', 'erro')
    elif r['desfeito_em']:
        flash('Esta ação já foi desfeita.', 'erro')
    else:
        try:
            from . import nucleai_ferramentas
            payload = json.loads(r['desfazer'])
            if not nucleai_ferramentas.aplicar_desfazer(db, payload):   # acessos e perfis mudados pelo chat da NucleAI
                agenda.aplicar_desfazer(db, payload)
        except (agenda.ErroAgenda, sqlite3.Error, ValueError, KeyError) as e:
            db.rollback()
            flash(str(e) if isinstance(e, agenda.ErroAgenda) else 'Não foi possível desfazer esta ação.', 'erro')
        else:
            db.execute('UPDATE auditoria SET desfeito_em=?, desfeito_por=? WHERE id=?', (agora(), g.usuario['usuario'], rid))
            db.commit()
            flash('Desfeito: %s.' % r['acao'], 'ok')
    return redirect(destino)
