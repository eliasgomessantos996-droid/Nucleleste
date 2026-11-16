"""Painel inicial e APIs de busca usadas pelos formulários."""
from datetime import date, timedelta
from urllib.parse import urlsplit

from flask import Blueprint, jsonify, redirect, render_template, request, url_for

from . import login_obrigatorio, pagina_inicial_do_usuario, util
from .db import get_db

bp = Blueprint('inicio', __name__)


@bp.route('/')
@login_obrigatorio
def painel():
    # abrir o endereço do sistema (favorito, digitado, sem Referer) leva à tela inicial de cada usuário (agenda, se ele tem acesso).
    # Clicar em "Início" no próprio menu manda o Referer do sistema, então mostra o Início de verdade.
    vem_do_sistema = bool(request.referrer) and urlsplit(request.referrer).netloc == request.host
    if not vem_do_sistema:
        destino = pagina_inicial_do_usuario()
        if destino != url_for('inicio.painel'):
            return redirect(destino)
    db = get_db()
    hoje = date.today().isoformat()
    em7 = (date.today() + timedelta(days=7)).isoformat()
    resumo = {
        'atend_hoje': db.execute('SELECT COUNT(*) FROM atendimentos WHERE data=?', (hoje,)).fetchone()[0],
        'clientes': db.execute('SELECT COUNT(*) FROM clientes').fetchone()[0],
        'caixa_aberto': db.execute("SELECT COUNT(*) FROM caixa WHERE status='ABERTO'").fetchone()[0],
        'contas_abertas': db.execute("SELECT COUNT(*), COALESCE(SUM(valor),0) FROM contas WHERE status='ABERTO'").fetchone(),
    }
    atend = db.execute('SELECT * FROM atendimentos WHERE data=? ORDER BY id DESC', (hoje,)).fetchall()
    doses = db.execute("SELECT * FROM doses WHERE status='AGENDADO' AND data_dose BETWEEN ? AND ? ORDER BY data_dose",
                       (hoje, em7)).fetchall()
    contas = db.execute("SELECT * FROM contas WHERE status='ABERTO' AND vencimento <= ? ORDER BY vencimento LIMIT 31",
                        (em7,)).fetchall()
    return render_template('painel.html', resumo=resumo, atend=atend, doses=doses, contas=contas, hoje=hoje)


@bp.route('/api/clientes')
@login_obrigatorio
def api_clientes():
    q = (request.args.get('q') or '').strip()
    db = get_db()
    if not q:
        return jsonify([])
    digitos = util.so_digitos(q)
    cpf_limpo = "REPLACE(REPLACE(REPLACE(cpf,'.',''),'-',''),' ','')"
    if digitos and not any(ch.isalpha() for ch in q):
        # Só números: código do cliente (exato) ou início do CPF
        rows = db.execute('SELECT * FROM clientes WHERE id=? OR %s LIKE ? ORDER BY nome LIMIT 30' % cpf_limpo,
                          (int(digitos), digitos + '%')).fetchall()
    else:
        termos = q.upper().split()
        where = ' AND '.join(['UPPER(nome) LIKE ?'] * len(termos))
        rows = db.execute('SELECT * FROM clientes WHERE %s ORDER BY nome LIMIT 30' % where,
                          ['%' + t + '%' for t in termos]).fetchall()
    return jsonify([cliente_json(r) for r in rows])


def cliente_json(r):
    return {
        'id': r['id'], 'nome': r['nome'], 'cpf': r['cpf'] or '', 'data_nasc': util.data_br(r['data_nasc']),
        'idade': util.idade_texto(r['data_nasc']), 'convenio': r['convenio'] or '', 'contato': r['contato'] or '',
        'nome_mae': r['nome_mae'] or '', 'endereco': ' '.join(x for x in [(r['rua'] or '').strip(), (r['numero'] or '').strip()] if x),
        'bairro': r['bairro'] or '', 'cidade': r['cidade'] or '', 'profissao': r['profissao'] or '',
        'cartao_convenio': r['cartao_convenio'] or '',
    }


@bp.route('/api/clientes/<int:cid>')
@login_obrigatorio
def api_cliente(cid):
    db = get_db()
    r = db.execute('SELECT * FROM clientes WHERE id=?', (cid,)).fetchone()
    if not r:
        return jsonify({'erro': 'Cliente não encontrado'}), 404
    dados = cliente_json(r)
    anteriores = db.execute(
        'SELECT id, data, exame, medico FROM atendimentos WHERE cliente_id=? '
        "OR (COALESCE(cpf,'')<>'' AND cpf=?) ORDER BY data DESC, id DESC",
        (cid, r['cpf'] or '-')).fetchall()
    dados['anteriores'] = [{'id': a['id'], 'data': util.data_br(a['data']), 'data_iso': a['data'] or '', 'exame': a['exame'] or '',
                            'medico': a['medico'] or ''} for a in anteriores]
    return jsonify(dados)


@bp.route('/api/cpf')
@login_obrigatorio
def api_cpf():
    cpf = util.cpf_formatado(request.args.get('cpf'))
    ignorar = request.args.get('ignorar', type=int) or 0
    r = get_db().execute('SELECT id, nome FROM clientes WHERE cpf=? AND id<>?', (cpf, ignorar)).fetchone()
    return jsonify({'valido': util.cpf_valido(cpf), 'formatado': cpf,
                    'existente': dict(r) if r else None})


@bp.route('/api/medicos')
@login_obrigatorio
def api_medicos():
    rows = get_db().execute("SELECT DISTINCT TRIM(nome) AS nome FROM medicos WHERE TRIM(COALESCE(nome,''))<>'' "
                            'ORDER BY TRIM(nome)').fetchall()
    return jsonify([r['nome'] for r in rows])
