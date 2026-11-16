"""Sistema de Recepção - Nucleleste (substitui a planilha VERSÃO 2.1 RECEPÇÃO)."""
import gzip
import json
import os
import secrets
import time
from functools import wraps

from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from markupsafe import Markup

from . import ajuda, atualizacao, auditoria, campanhas, chat, modulos, presenca, tutorial
from . import db as dbmod
from . import util

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def carregar_config():
    cfg = {'pasta_dados': 'dados', 'porta': 8080}
    caminho = os.path.join(RAIZ, 'config.json')
    if os.path.exists(caminho):
        with open(caminho, encoding='utf-8') as fh:
            cfg.update(json.load(fh))
    pasta = os.environ.get('NUCLELESTE_DADOS') or cfg['pasta_dados']
    if not os.path.isabs(pasta):
        pasta = os.path.join(RAIZ, pasta)
    # a configuração da instalação (porta etc.) fica junto dos dados, que são graváveis
    local = os.path.join(pasta, 'config.json')
    if os.path.exists(local):
        try:
            with open(local, encoding='utf-8-sig') as fh:
                cfg.update({k: v for k, v in json.load(fh).items() if k == 'porta'})
        except (OSError, ValueError):
            pass
    if os.environ.get('NUCLELESTE_PORTA', '').isdigit():
        cfg['porta'] = int(os.environ['NUCLELESTE_PORTA'])
    cfg['pasta_dados'] = pasta
    return cfg


def versao():
    try:
        with open(os.path.join(RAIZ, 'VERSION'), encoding='utf-8') as fh:
            return fh.read().strip()
    except OSError:
        return 'dev'


def _chave_secreta(pasta):
    caminho = os.path.join(pasta, 'chave_secreta.txt')
    if not os.path.exists(caminho):
        os.makedirs(pasta, exist_ok=True)
        with open(caminho, 'w') as fh:
            fh.write(secrets.token_hex(32))
    with open(caminho) as fh:
        return fh.read().strip()


def resposta_login(motivo=None):
    destino = url_for('auth.login', motivo=motivo) if motivo else url_for('auth.login', proximo=request.full_path)
    if request.headers.get('X-Passivo') or request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes.best == 'application/json':
        return {'erro': 'Sua sessão foi encerrada.', 'login': destino}, 401, {'X-Login-URL': destino}
    return redirect(destino)


def campanha_segura():
    """Campanha do mês para o contexto; erro de banco vira None para nunca derrubar a página."""
    try:
        return campanhas.atual()
    except Exception:
        return None


def sessao_substituida(u):
    # sessões anteriores à migração continuam válidas até o próximo login do usuário
    return bool(u['sessao_id']) and session.get('sessao_id') != u['sessao_id']


def encerrar_sessao_substituida():
    session.clear()
    g.usuario = None
    g.modulos = set()
    return resposta_login('outro_login')


def login_obrigatorio(view):
    @wraps(view)
    def inner(*a, **kw):
        if not g.get('usuario'):
            return resposta_login()
        return view(*a, **kw)
    return inner


def _lembretes_na_entrada(u, tutorial_abre):
    """A janela de lembretes abre uma vez por login (marca `lembretes_mostrados` na sessão, zerada no login).
    Não abre em telas sem sentido: troca de senha provisória, rotas /api, respostas JSON e enquanto o tutorial abre."""
    if not u or u['trocar_senha'] or tutorial_abre or session.get('lembretes_mostrados', True):
        return False
    if (request.endpoint or '').startswith('auth.') or request.path.startswith('/api') or request.is_json:
        return False
    session['lembretes_mostrados'] = True
    from . import lembretes
    return lembretes.tem_pendentes(dbmod.get_db(), u)


def pagina_inicial_do_usuario(u=None, mods=None):
    """Tela que o usuário vê ao abrir o sistema: a agenda, se ele tem acesso a ela; senão o Início.
    Sem argumentos usa o usuário da requisição. No login passa `u` (g ainda não está carregado) e os módulos dele."""
    if u is None:
        u = g.get('usuario')
    if mods is None:
        mods = g.get('modulos') if (u is not None and u is g.get('usuario')) else modulos.modulos_do_usuario(u)
    if u and not u['trocar_senha'] and ({'agenda', 'agenda_leitura'} & set(mods or ())):
        return url_for('agenda.pagina')
    return url_for('inicio.painel')


def admin_obrigatorio(view):
    @wraps(view)
    @login_obrigatorio
    def inner(*a, **kw):
        if not g.usuario['admin']:
            flash('Acesso restrito ao administrador.', 'erro')
            return redirect(url_for('inicio.painel'))
        return view(*a, **kw)
    return inner


def create_app(database=None, avisos_automaticos=False):
    """`avisos_automaticos`: liga o envio de hora em hora dos avisos de vencimento (servidor e bandeja ligam; os testes não)."""
    cfg = carregar_config()
    app = Flask(__name__)
    app.config['DATABASE'] = database or os.path.join(cfg['pasta_dados'], 'sistema.db')
    app.config['PASTA_DADOS'] = os.path.dirname(app.config['DATABASE'])
    app.config['PORTA'] = cfg['porta']
    app.config['INICIO_SERVIDOR'] = time.time()
    app.config['SECRET_KEY'] = _chave_secreta(app.config['PASTA_DADOS'])
    from . import medcloud
    medcloud.definir_chave(app.config['SECRET_KEY'])   # chave da cifra das senhas do Medcloud
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    # cookie de sessão (não permanente): fechar o navegador encerra o login (sem limite por inatividade)
    app.config['PERMANENT_SESSION_LIFETIME'] = 60 * 60 * 12
    app.json.ensure_ascii = False

    dbmod.inicializar(app.config['DATABASE'])
    app.teardown_appcontext(dbmod.close_db)

    @app.before_request
    def carregar_usuario_e_csrf():
        g.usuario = None
        # arquivos estáticos não dependem de usuário, sessão nem CSRF: sai antes de tocar no banco
        if request.endpoint == 'static':
            g.modulos = set()
            return None
        # logo depois de uma atualização o sistema pede um tempo para receber tudo: todos veem a tela de espera
        if request.endpoint not in ('static', 'atu.estado', 'atu.iniciar'):
            espera = atualizacao.espera_restante(app.config['PASTA_DADOS'], app.config['INICIO_SERVIDOR'])
            if espera:
                return render_template('atualizando.html', espera=espera, versao=versao()), 503, {'Retry-After': str(espera)}
        uid = session.get('uid')
        if uid:
            u = dbmod.get_db().execute('SELECT * FROM usuarios WHERE id=? AND ativo=1', (uid,)).fetchone()
            if u:
                if request.endpoint != 'static' and not (request.endpoint == 'auth.login' and request.method == 'POST') and sessao_substituida(u):
                    if request.endpoint != 'auth.login':
                        return encerrar_sessao_substituida()
                    session.clear()
                    flash('Sua sessão foi encerrada porque você entrou em outro computador', 'aviso')
                    u = None
                g.usuario = u
            else:
                session.clear()
        if 'csrf' not in session:
            session['csrf'] = secrets.token_hex(16)
        # o instalador não tem sessão (usa a chave do servidor); a pesquisa de satisfação é pública (celular do cliente, sem login)
        if request.method == 'POST' and request.endpoint not in ('atu.iniciar', 'pesq.publica'):
            token = request.form.get('_csrf') or request.headers.get('X-CSRF-Token')
            if token != session['csrf']:
                abort(400, 'Sessão expirada. Recarregue a página e tente novamente.')
        g.modulos = modulos.modulos_do_usuario(g.usuario)
        if g.usuario and 'enfermagem' in g.modulos and not g.usuario['admin']:   # a permissão só vale depois que a assinatura for importada
            from . import enfermagem
            enfermagem.garantir(dbmod.get_db())
            if not enfermagem.assinatura_valida(dbmod.get_db(), g.usuario['id']):
                g.modulos = set(g.modulos) - {'enfermagem'}
        g._n_flashes = len(session.get('_flashes') or [])
        # senha provisória (ex.: acesso criado para funcionário): o sistema fica travado, só a troca de senha funciona até concluir
        if g.usuario and g.usuario['trocar_senha']:
            ep_atual = request.endpoint or ''
            if not (ep_atual == 'static' or ep_atual.startswith(('auth.', 'atu.'))):
                flash('Defina uma nova senha para continuar.', 'erro')
                return redirect(url_for('auth.minha_senha'))
        # permissão por módulo: bloqueia o endpoint mesmo que alguém digite o endereço na barra
        exigido = modulos.modulo_do_endpoint(request.endpoint)
        if g.usuario and exigido:
            if exigido == '__admin__':
                liberado = bool(g.usuario['admin'])
            elif isinstance(exigido, tuple):
                liberado = any(m in g.modulos for m in exigido)
            else:
                liberado = exigido in g.modulos
            if not liberado:
                flash('Você não tem acesso a este módulo.', 'erro')
                return redirect(url_for('inicio.painel'))
        if g.usuario:
            ep = request.endpoint or ''
            # conta de funcionário: a "casa" dele é a Minha área, nunca o painel da recepção. Só vale para quem TEM o módulo
            # Minha área; funcionário com módulos de recepção (sem esse módulo) usa a tela inicial normal (evita redirecionar em círculo)
            if g.usuario['bh_funcionario_id'] and not g.usuario['admin'] and 'bh_portal' in g.modulos and ep == 'inicio.painel':   # só a tela inicial; as buscas (/api/...) precisam continuar respondendo
                return redirect(url_for('bh.portal_home'))

    app.after_request(auditoria.depois_da_requisicao)

    # ?v=<mtime> nas URLs dos estáticos: ao mudar o arquivo, a URL muda e o navegador baixa de novo
    versoes_estaticos = {}

    @app.url_defaults
    def versionar_estatico(endpoint, values):
        if endpoint != 'static' or 'v' in values or 'filename' not in values:
            return
        nome = values['filename']
        if app.debug or nome not in versoes_estaticos:   # em desenvolvimento relê o arquivo (o CSS editado muda de versão na hora)
            caminho = os.path.join(app.static_folder, nome)
            if not os.path.isfile(caminho):
                return
            versoes_estaticos[nome] = int(os.path.getmtime(caminho))
        values['v'] = versoes_estaticos[nome]

    # tipos de resposta que valem a pena comprimir (HTML, CSS, JS, JSON, texto e SVG)
    TIPOS_COMPRIMIVEIS = ('text/html', 'text/css', 'application/javascript', 'text/javascript',
                          'application/json', 'text/plain', 'image/svg+xml')

    @app.after_request
    def cabecalhos_de_cache_e_compressao(resp):
        if request.endpoint == 'static':
            if resp.status_code in (200, 304):
                resp.headers['Cache-Control'] = ('public, max-age=31536000, immutable' if 'v' in request.args
                                                 else 'public, max-age=600')
            if resp.headers.get('Vary', '').strip().lower() == 'cookie':
                del resp.headers['Vary']
            return resp
        # gzip só para respostas normais (não streaming, não download) e quando o navegador aceita
        if (resp.status_code == 200 and not resp.direct_passthrough and not resp.is_streamed
                and 'Content-Encoding' not in resp.headers
                and 'attachment' not in resp.headers.get('Content-Disposition', '')
                and resp.mimetype in TIPOS_COMPRIMIVEIS and 'gzip' in request.headers.get('Accept-Encoding', '')):
            dados = resp.get_data()
            if len(dados) >= 1500:
                resp.set_data(gzip.compress(dados, compresslevel=5))
                resp.headers['Content-Encoding'] = 'gzip'
                resp.vary.add('Accept-Encoding')
        return resp

    @app.context_processor
    def contexto():
        token = session.get('csrf', '')
        u = g.get('usuario')
        mods = g.get('modulos') or set()
        menu = modulos.montar_menu(u, mods, request.endpoint) if u else []
        aba = next(({'grupo': grupo or 'Geral', 'rotulo': it['rotulo'], 'icone': it['icone']} for grupo, itens in menu for it in itens if it['ativo']), None)
        abas = modulos.montar_abas(u, mods, request.endpoint) if u and not u['trocar_senha'] else None
        if abas and abas['atual']:   # o título da barra do topo é o da aba aberta (ex.: Lançar atendimento)
            aba = {'grupo': abas['grupo'], 'rotulo': abas['atual']['rotulo'], 'icone': abas['atual']['icone']}
        atalho = url_for('agenda.pagina') if u and not u['trocar_senha'] and ({'agenda', 'agenda_leitura'} & set(mods)) else None
        passos = tutorial.montar(menu, u['usuario'], ajuda.ativa(dbmod.get_db())) if u and not u['trocar_senha'] and menu else []
        return {
            'atalho_agenda': atalho, 'atalho_agenda_ativo': (request.endpoint or '').startswith('agenda.'),
            'abas': abas,
            'usuario': u,
            'csrf_token': token,
            'versao': versao(),
            'csrf_input': Markup('<input type="hidden" name="_csrf" value="%s">' % token),
            'pode': lambda chave: bool(u) and (bool(u['admin']) or chave in mods),
            'menu': [] if (u and u['trocar_senha']) else menu,
            'aba_atual': aba,
            'temas_icones': modulos.TEMA_ICONES,
            'hoje_extenso': util.data_extenso() if u else '',
            # consulta das mensagens livres (contador do menu e avisos na hora, em qualquer tela)
            'chat_url': url_for('chat.novas') if u and not (u['trocar_senha']) else '',
            'travado': bool(u and u['trocar_senha']),   # senha provisória: nada do sistema aparece até trocar a senha
            'chat_ultimo': chat.ultimo_id_recebido(dbmod.get_db(), u['id']) if u else 0,
            'bh_poll_url': '',  # as mensagens do Banco de Horas foram substituídas pelas mensagens livres
            # tema de cor do próprio usuário (seletor no rodapé do menu)
            'tema_atual': temas.valido(u['tema'] if u else ''),
            'brilho_atual': temas.brilho_valido(u['brilho'] if u else ''),
            'cor_calendario': temas.cor_calendario_valida(u['cor_calendario'] if u else ''),
            'temas_lista': temas.LISTA,
            # logo após o login, todos os temas do menu aparecem recolhidos (a tela de login marca a sessão)
            'menu_recolher': bool(u) and bool(session.pop('menu_recolher', False)),
            # botão redondo da NucleAI (a administração pode desligar a assistente)
            'nucleai_ativa': bool(u) and ajuda.ativa(dbmod.get_db()),
            # tutorial animado da NucleAI: roteiro personalizado pelo menu do usuário; abre sozinho no primeiro acesso
            'tutorial_passos': passos,
            'tutorial_auto': bool(u) and not u['tutorial_visto'],
            # janela de lembretes em checklist: uma vez por login; se o tutorial abrir nesta página, ela fica para a próxima
            'lembretes_auto': _lembretes_na_entrada(u, bool(passos) and bool(u) and not u['tutorial_visto']),
            # campanha de saúde do mês (laço no menu, entrada e Início); None quando desligada
            'campanha': campanha_segura(),
        }

    from . import temas
    app.jinja_env.filters['data_br'] = util.data_br
    app.jinja_env.filters['moeda'] = util.moeda
    app.jinja_env.filters['idade'] = util.idade_texto
    app.jinja_env.filters['cpf'] = util.cpf_formatado

    from .auth import bp as auth_bp
    from .views_inicio import bp as inicio_bp
    from .views_cadastros import bp as cad_bp
    from .views_atendimentos import bp as atend_bp
    from .views_medicamentos import bp as med_bp
    from .views_financeiro import bp as fin_bp
    from .views_documentos import bp as doc_bp
    from .views_admin import bp as admin_bp
    from .views_dashboard import bp as dash_bp
    from .views_faturamento import bp as fat_bp
    from .views_registros import bp as reg_bp
    from .views_bh import bp as bh_bp
    from .views_exames import bp as lanc_bp
    from .views_chat import bp as chat_bp
    from .views_blindagens import bp as blind_bp
    from .views_agenda import bp as agenda_bp
    from .views_arquivos import bp as arq_bp
    from .views_movimento import bp as mov_bp
    from .views_atualizacao import bp as atu_bp
    from .views_saude import bp as saude_bp
    from .views_laudos import bp as laudo_bp
    from .views_ona import bp as ona_bp
    from .views_ajuda import bp as ajuda_bp
    from .views_nucleai import bp as nucleai_bp
    from .views_nucleai_ia import bp as nucleaiia_bp
    from .views_favoritos import bp as fav_bp
    from .views_novidades import bp as nov_bp
    from .views_caixa_diario import bp as cxd_bp
    from .views_qualidade import bp as qual_bp
    from .views_pesquisa import bp as pesq_bp
    from .views_suporte import bp as sup_bp
    from .views_enfermagem import bp as enf_bp
    from .views_precos import bp as preco_bp
    from .views_prontuario import bp as pront_bp
    from .views_lembretes import bp as lem_bp
    from .views_estoque import bp as est_bp
    from .views_medcloud import bp as medc_bp
    from .views_medcloud_pend import bp as mpend_bp
    for bp in (medc_bp, mpend_bp, auth_bp, inicio_bp, cad_bp, atend_bp, med_bp, fin_bp, doc_bp, admin_bp, dash_bp, fat_bp, reg_bp, bh_bp, lanc_bp,
               chat_bp, blind_bp, agenda_bp, arq_bp, mov_bp, atu_bp, saude_bp, laudo_bp, ona_bp, ajuda_bp, nucleai_bp, nucleaiia_bp, fav_bp, nov_bp, cxd_bp, qual_bp, pesq_bp, sup_bp, enf_bp, preco_bp, pront_bp, lem_bp, est_bp):
        app.register_blueprint(bp)
    if avisos_automaticos:
        from . import avisos
        avisos.iniciar(app.config['DATABASE'])
        medcloud.iniciar(app.config['DATABASE'])   # robô da Medcloud: processa a fila de acessos (só age com a função ativa)

    @app.errorhandler(500)
    def erro_interno(e):
        """Erro inesperado: grava no registro de atividades (aparece na Saúde do sistema) e mostra uma tela simples."""
        original = getattr(e, 'original_exception', None) or e
        try:
            db = dbmod.get_db()
            db.execute('INSERT INTO auditoria (data_hora, usuario, modulo, acao, detalhe, rota, ip) VALUES (?,?,?,?,?,?,?)',
                       (dbmod.agora(), g.usuario['usuario'] if g.get('usuario') else None, 'Sistema', 'Erro interno',
                        (type(original).__name__ + ': ' + str(original))[:300], request.path, request.remote_addr))
            db.commit()
        except Exception:  # se o próprio banco falhar, a tela de erro ainda aparece
            pass
        return ('<p style="font-family:sans-serif">Ocorreu um erro interno. O registro foi salvo para a gestão. '
                '<a href="javascript:history.back()">Voltar</a></p>'), 500

    @app.errorhandler(400)
    def erro_400(e):
        return (f'<p style="font-family:sans-serif">{e.description} '
                f'<a href="javascript:history.back()">Voltar</a></p>'), 400

    return app
