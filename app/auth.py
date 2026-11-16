"""Login, logout e troca de senha."""
import secrets
import time
from urllib.parse import quote, unquote

from flask import Blueprint, flash, g, get_flashed_messages, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from . import login_obrigatorio, pagina_inicial_do_usuario, presenca
from .db import agora, get_db

bp = Blueprint('auth', __name__)

# Logins lembrados na tela de entrada (só nomes; a senha nunca entra no cookie)
COOKIE_LEMBRADOS = 'nuc_usuarios'
LEMBRADOS_MAX = 8
LEMBRADOS_DIAS = 365


def ler_lembrados_cookie(valor):
    """Lê o cookie de logins lembrados. Valor vazio ou corrompido vira lista vazia."""
    if not valor:
        return []
    try:
        texto = unquote(valor)
    except Exception:
        return []
    return [n.strip() for n in texto.split('\n') if n.strip()][:LEMBRADOS_MAX]


def lembrar_usuario(resposta, nome):
    """Põe o login (grafia do banco) no topo do cookie, sem repetir e sem diferenciar maiúsculas."""
    atuais = ler_lembrados_cookie(request.cookies.get(COOKIE_LEMBRADOS))
    lista = [nome] + [n for n in atuais if n.casefold() != nome.casefold()]
    resposta.set_cookie(COOKIE_LEMBRADOS, quote('\n'.join(lista[:LEMBRADOS_MAX])),
                        max_age=LEMBRADOS_DIAS * 86400, httponly=True, samesite='Lax', path='/')
    return resposta


def usuarios_lembrados():
    """Mantém só os nomes do cookie que existem como usuários ativos no banco (grafia do banco, sem repetir)."""
    vistos, lembrados = set(), []
    for nome in ler_lembrados_cookie(request.cookies.get(COOKIE_LEMBRADOS)):
        if nome.casefold() in vistos:
            continue
        u = get_db().execute('SELECT usuario FROM usuarios WHERE usuario=? AND ativo=1', (nome,)).fetchone()
        if u:
            vistos.add(nome.casefold())
            lembrados.append(u['usuario'])
    return lembrados[:LEMBRADOS_MAX]


def registrar_acesso(usuario, evento, detalhe=''):
    db = get_db()
    db.execute('INSERT INTO acessos (data_hora, usuario, evento, computador, detalhe) VALUES (?,?,?,?,?)',
               (agora(), usuario, evento, request.remote_addr, detalhe[:200]))
    db.commit()


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        nome = (request.form.get('usuario') or '').strip().upper()
        senha = request.form.get('senha') or ''
        if not nome or not senha:
            flash('Preencha usuário e senha.', 'erro')
        else:
            u = get_db().execute('SELECT * FROM usuarios WHERE usuario=?', (nome,)).fetchone()
            if not u:
                flash('Usuário não encontrado.', 'erro')
            elif not u['ativo']:
                flash('Usuário desativado.', 'erro')
            elif not check_password_hash(u['senha_hash'], senha):
                registrar_acesso(nome, 'Senha incorreta')
                flash('Senha incorreta!', 'erro')
            else:
                identificador = secrets.token_hex(32)
                db = get_db()
                db.execute('UPDATE usuarios SET sessao_id=? WHERE id=?', (identificador, u['id']))
                db.execute('DELETE FROM presenca WHERE usuario_id=?', (u['id'],))
                db.commit()
                session.clear()
                session['uid'] = u['id']
                session['sessao_id'] = identificador
                session['ultima'] = time.time()
                session['menu_recolher'] = True
                session['lembretes_mostrados'] = False   # a janela de lembretes abre de novo neste login
                registrar_acesso(u['usuario'], 'Logado', request.user_agent.string)
                destino = request.args.get('proximo') or ''
                # sem destino ou só a raiz ('/?', que o login_obrigatorio manda): vai para a tela inicial de cada usuário
                if destino in ('', '/', '/?') or not destino.startswith('/') or destino.startswith('//'):
                    destino = pagina_inicial_do_usuario(u)
                return lembrar_usuario(redirect(destino), u['usuario'])
    return render_template('login.html', lembrados=usuarios_lembrados())


@bp.route('/apostila.pdf')
def apostila():
    """Endereço antigo da apostila: leva ao Log de atualizações (exige entrar)."""
    return redirect(url_for('nov.apostila'))


@bp.route('/sessao/batida', methods=['POST'])
def batida():
    """Batida de presença de uma aba (a cada BATIDA_S segundos). Não renova a sessão: é X-Passivo."""
    aba = presenca.aba_valida(request.form.get('aba'))
    if not g.get('usuario') or not aba:
        return {'ok': False}, 401
    presenca.bater(get_db(), g.usuario['id'], aba)
    return {'ok': True}


@bp.route('/sessao/saida', methods=['POST'])
def saida():
    """A aba foi fechada ou trocada de página (sendBeacon): some da presença na hora."""
    aba = presenca.aba_valida(request.form.get('aba'))
    if g.get('usuario') and aba:
        presenca.sair(get_db(), g.usuario['id'], aba)
    return ('', 204)


@bp.route('/logout', methods=['POST'])
def logout():
    if g.get('usuario'):
        registrar_acesso(g.usuario['usuario'], 'Saiu')
        presenca.sair(get_db(), g.usuario['id'])
    session.clear()
    return redirect(url_for('auth.login'))


@bp.route('/minha-senha', methods=['GET', 'POST'])
@login_obrigatorio
def minha_senha():
    if request.method == 'POST':
        atual = request.form.get('atual') or ''
        nova = request.form.get('nova') or ''
        conf = request.form.get('confirmar') or ''
        if not check_password_hash(g.usuario['senha_hash'], atual):
            flash('Senha atual incorreta.', 'erro')
        elif len(nova) < 3:
            flash('A nova senha deve ter pelo menos 3 caracteres.', 'erro')
        elif nova != conf:
            flash('A confirmação não confere com a nova senha.', 'erro')
        else:
            db = get_db()
            db.execute('UPDATE usuarios SET senha_hash=?, trocar_senha=0 WHERE id=?', (generate_password_hash(nova), g.usuario['id']))
            db.commit()
            registrar_acesso(g.usuario['usuario'], 'Alterou a senha')
            flash('Senha alterada com sucesso!', 'ok')
            # relê o usuário: o g.usuario ainda está com trocar_senha=1 e mandaria para o Início
            return redirect(pagina_inicial_do_usuario(db.execute('SELECT * FROM usuarios WHERE id=?', (g.usuario['id'],)).fetchone()))
    from . import temas
    return render_template('minha_senha.html', temas=temas.TEMAS, brilhos=temas.BRILHOS)


@bp.route('/meu-tema', methods=['POST'])
@login_obrigatorio
def meu_tema():
    """Grava a aparência escolhida pelo próprio usuário: tema (cor) e/ou brilho (claro ou escuro). Fica no perfil, não no computador."""
    from . import temas
    db = get_db()
    if 'tema' in request.form:
        db.execute('UPDATE usuarios SET tema=? WHERE id=?', (temas.valido(request.form.get('tema', '')), g.usuario['id']))
    if 'brilho' in request.form:
        db.execute('UPDATE usuarios SET brilho=? WHERE id=?', (temas.brilho_valido(request.form.get('brilho', '')), g.usuario['id']))
    if 'cor_calendario' in request.form:
        db.execute('UPDATE usuarios SET cor_calendario=? WHERE id=?', (temas.cor_calendario_valida(request.form.get('cor_calendario', '')), g.usuario['id']))
    db.commit()
    return {'ok': True}
