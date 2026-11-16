"""Painel de favoritos: cada usuário escolhe os módulos que mais usa e organiza os atalhos (widgets) como quiser."""
import json

from flask import Blueprint, g, jsonify, render_template, request

from . import login_obrigatorio, modulos
from .db import get_db

bp = Blueprint('fav', __name__, url_prefix='/favoritos')

MODOS = ('grade', 'lista')
TAMANHOS = (1, 2)            # largura do widget na grade (1 ou 2 colunas)
CORES = ('', 'azul', 'laranja', 'roxo', 'vermelho', 'cinza')
MAX_ITENS = 40


def disponiveis(u, mods, endpoint=None):
    """Módulos que o usuário pode abrir (os mesmos do menu), sem a própria tela de favoritos."""
    lista = []
    for _grupo, itens in modulos.montar_menu(u, mods, endpoint, incluir_abas=True):
        lista += [{'ep': i['ep'], 'rotulo': i['rotulo'], 'grupo': i['grupo'], 'url': i['url'], 'icone': i['icone']}
                  for i in itens if i['ep'] != 'fav.painel']
    return lista


def normalizar(bruto, validos):
    """Aceita só módulos permitidos, sem repetir, com modo/tamanho/cor válidos. `validos` é o conjunto de endpoints liberados."""
    try:
        dados = json.loads(bruto) if isinstance(bruto, str) else dict(bruto or {})
    except (ValueError, TypeError):
        dados = {}
    itens, vistos = [], set()
    for it in (dados.get('itens') or [])[:MAX_ITENS * 2]:
        if not isinstance(it, dict):
            continue
        ep = it.get('ep')
        if ep not in validos or ep in vistos:
            continue
        vistos.add(ep)
        tam = it.get('tam') if it.get('tam') in TAMANHOS else 1
        cor = it.get('cor') if it.get('cor') in CORES else ''
        ico = str(it.get('ico') or '').strip()
        ico = ico if ico in modulos.NOMES_ICONES else ''   # só desenhos que existem no sprite
        itens.append({'ep': ep, 'tam': tam, 'cor': cor, 'ico': ico})
    modo = dados.get('modo') if dados.get('modo') in MODOS else 'grade'
    return {'modo': modo, 'itens': itens[:MAX_ITENS]}


def _atual(db):
    r = db.execute('SELECT favoritos FROM usuarios WHERE id=?', (g.usuario['id'],)).fetchone()
    return r['favoritos'] if r else None


@bp.route('')
@login_obrigatorio
def painel():
    lista = disponiveis(g.usuario, g.modulos, 'fav.painel')
    estado = normalizar(_atual(get_db()), {m['ep'] for m in lista})
    return render_template('favoritos.html', disponiveis=lista, estado=estado, cores=CORES, icones=modulos.ICONES_SUGERIDOS)


@bp.route('/salvar', methods=['POST'])
@login_obrigatorio
def salvar():
    validos = {m['ep'] for m in disponiveis(g.usuario, g.modulos)}
    estado = normalizar(request.form.get('dados'), validos)
    db = get_db()
    db.execute('UPDATE usuarios SET favoritos=? WHERE id=?', (json.dumps(estado, ensure_ascii=False), g.usuario['id']))
    db.commit()
    return jsonify(ok=True, **estado)
