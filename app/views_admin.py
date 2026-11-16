"""Administração: usuários, log de acessos, backup, pastas e configurações."""
import json
import os
import secrets
import sqlite3
import time
from datetime import datetime
from functools import wraps

from flask import (Blueprint, Response, abort, current_app, flash, g, redirect, render_template, request, send_from_directory,
                   session, url_for)
from werkzeug.security import generate_password_hash

from . import admin_obrigatorio, backup_pacote, enfermagem, hierarquia, laudos, login_obrigatorio, usuarios_arquivo, mensagens_whats as mw, modulos, presenca, util, versao
from .auth import registrar_acesso
from .db import agora, config_get, config_set, get_db

bp = Blueprint('admin', __name__)


# ---------------------------------------------------------------- usuários e perfis
def _gerir_ou_nao(db, alvo):
    """Bloqueia (com aviso) quem tenta mexer em alguém acima do seu nível."""
    if alvo is not None and not hierarquia.pode_gerir(db, g.usuario, alvo):
        flash('Você não tem permissão para alterar este perfil: ele está acima do seu nível.', 'erro')
        return False
    return True


def _modulos_do_form():
    return [m for m in request.form.getlist('modulos') if m in modulos.CHAVES]


@bp.route('/usuarios')
@login_obrigatorio
def usuarios():
    arquivados = bool(request.args.get('arquivados'))
    rows = get_db().execute(
        'SELECT u.*, (SELECT MAX(data_hora) FROM acessos a WHERE a.usuario=u.usuario '
        "AND a.evento='Logado') AS ultimo, (SELECT COUNT(*) FROM auditoria r WHERE r.usuario=u.usuario) AS n_acoes "
        'FROM usuarios u WHERE COALESCE(u.sistema,0)=0 AND u.arquivado_em %s ORDER BY ativo DESC, usuario'
        % ('IS NOT NULL' if arquivados else 'IS NULL')).fetchall()
    db = get_db()
    lista = [{'u': u, 'modulos': sorted(modulos.modulos_do_usuario(u), key=modulos.CHAVES.index), 'nivel': hierarquia.ROTULOS[hierarquia.nivel(db, u)],
              'pode': hierarquia.pode_gerir(db, g.usuario, u)} for u in rows
             if hierarquia.nivel(db, g.usuario) > hierarquia.USUARIO or hierarquia.nivel(db, u) == hierarquia.USUARIO]
    return render_template('usuarios.html', arquivados=arquivados, lista=lista, nomes=modulos.NOMES, total=len(modulos.CHAVES),
                           situacao=presenca.situacao(get_db()))


@bp.route('/usuarios/novo', methods=['GET', 'POST'])
@bp.route('/usuarios/<int:uid>', methods=['GET', 'POST'])
@login_obrigatorio
def usuario_editar(uid=None):
    db = get_db()
    u = db.execute('SELECT * FROM usuarios WHERE id=?', (uid,)).fetchone() if uid else None
    if uid and not u:
        abort(404)
    if not _gerir_ou_nao(db, u):
        return redirect(url_for('admin.usuarios'))
    marcados = set(modulos.modulos_do_usuario(u)) if u else set(modulos.PRESETS['recepcao'][1])
    admin_flag = bool(u and u['admin'])
    pode_login = bool(u) and hierarquia.pode_mudar_login(db, g.usuario)
    if request.method == 'GET':
        session.pop('enf_pendente', None)   # saiu da página de assinatura sem concluir: a mudança de permissão não vale
    if request.method == 'POST':
        nome = util.maiusculas(request.form.get('usuario')) if not u else u['usuario']
        senha = request.form.get('senha') or ''
        admin_flag = request.form.get('perfil') == 'admin' or bool(request.form.get('admin'))   # perfil: Usuário (padrão) ou Administrador
        marcados, admin_flag, erros = hierarquia.ajustar_marcados(db, g.usuario, u, _modulos_do_form(), admin_flag)
        novo_login = util.maiusculas(request.form.get('usuario')) if pode_login else None
        if novo_login and novo_login != u['usuario']:
            erro_login = hierarquia.validar_login(db, u['id'], novo_login)
            if erro_login:
                erros.append(erro_login)
        else:
            novo_login = None
        if not nome:
            erros.append('Informe o nome de usuário.')
        if not u:
            if len(senha) < 3:
                erros.append('A senha deve ter pelo menos 3 caracteres.')
            if db.execute('SELECT 1 FROM usuarios WHERE usuario=?', (nome,)).fetchone():
                erros.append('Nome de usuário já cadastrado.')
        elif u['id'] == g.usuario['id'] and not admin_flag:
            erros.append('Você não pode retirar o seu próprio acesso de administrador.')
        if not admin_flag and not marcados:
            erros.append('Marque pelo menos um módulo (ou torne o usuário administrador).')
        if not erros and u and not admin_flag and 'enfermagem' in marcados and 'enfermagem' not in modulos.modulos_do_usuario(u):
            # liberar Enfermagem e Segurança exige a assinatura do profissional: nada é salvo agora; a página de importação conclui (ou cancela) a mudança
            enfermagem.garantir(db)
            if not enfermagem.assinatura_valida(db, u['id']):
                session['enf_pendente'] = {'uid': u['id'], 'admin': 1 if admin_flag else 0, 'modulos': sorted(marcados, key=modulos.CHAVES.index),
                                           'laudo_perm': laudos.perm_do_form(request.form), 'senha_hash': generate_password_hash(senha) if len(senha) >= 3 else None,
                                           'login': novo_login}
                flash('Para liberar Enfermagem e Segurança, importe a assinatura do profissional. Nada foi salvo ainda.', 'aviso')
                return redirect(url_for('enf.assinatura', uid=u['id']))
        if erros:
            for e in erros:
                flash(e, 'erro')
        else:
            mods_json = json.dumps(sorted(marcados, key=modulos.CHAVES.index))
            if not u:
                mods_json = json.dumps(sorted(marcados - {'enfermagem'}, key=modulos.CHAVES.index))   # usuário novo: Enfermagem entra depois, com a assinatura
                if 'enfermagem' in marcados:
                    flash('Enfermagem e Segurança não foi liberada: depois de criar o usuário, edite-o e marque o módulo para importar a assinatura.', 'aviso')
            if u:
                db.execute('UPDATE usuarios SET admin=?, modulos=?, laudo_perm=? WHERE id=?',
                           (1 if admin_flag else 0, mods_json, laudos.perm_do_form(request.form), uid))
                if novo_login:
                    antigo = hierarquia.renomear_login(db, uid, novo_login)
                    registrar_acesso(g.usuario['usuario'], 'Login alterado', '%s → %s' % (antigo, novo_login))
                    flash('Login alterado de %s para %s.' % (antigo, novo_login), 'ok')
                if senha:
                    if len(senha) < 3:
                        flash('A senha deve ter pelo menos 3 caracteres; as permissões foram salvas.', 'aviso')
                    else:
                        db.execute('UPDATE usuarios SET senha_hash=? WHERE id=?', (generate_password_hash(senha), uid))
                flash('Perfil de %s salvo.' % u['usuario'], 'ok')
            else:
                db.execute('INSERT INTO usuarios (usuario, senha_hash, admin, modulos, criado_em, criado_por, laudo_perm) VALUES (?,?,?,?,?,?,?)',
                           (nome, generate_password_hash(senha), 1 if admin_flag else 0, mods_json, agora(), g.usuario['usuario'],
                            laudos.perm_do_form(request.form)))
                flash('Usuário %s criado. Ele pode trocar a própria senha em "Alterar senha".' % nome, 'ok')
            db.commit()
            return redirect(url_for('admin.usuarios'))
    grupos = {}
    for chave, nome_mod, grupo, desc in modulos.MODULOS:
        grupos.setdefault(grupo, []).append({'chave': chave, 'nome': nome_mod, 'desc': desc, 'marcado': chave in marcados})
    perm = laudos.permissoes(u) if u else None
    return render_template('usuario_form.html', u=u, pode_login=pode_login, grupos=grupos, admin_flag=admin_flag,
                           laudo_situacoes=laudos.SITUACOES, laudo_situacoes_nomes=laudos.ROTULOS, laudo_perm=perm, laudo_proximas={c: laudos.proxima(c) for c in laudos.CHAVES},
                           presets={k: v[1] for k, v in modulos.PRESETS.items()},
                           preset_nomes={k: v[0] for k, v in modulos.PRESETS.items()})


@bp.route('/usuarios/<int:uid>/senha', methods=['POST'])
@login_obrigatorio
def usuario_senha(uid):
    alvo = get_db().execute('SELECT * FROM usuarios WHERE id=?', (uid,)).fetchone()
    if alvo is None or not _gerir_ou_nao(get_db(), alvo):
        return redirect(url_for('admin.usuarios'))
    senha = request.form.get('senha') or ''
    if len(senha) < 3:
        flash('A senha deve ter pelo menos 3 caracteres.', 'erro')
    else:
        db = get_db()
        db.execute('UPDATE usuarios SET senha_hash=? WHERE id=?', (generate_password_hash(senha), uid))
        db.commit()
        flash('Senha redefinida.', 'ok')
    return redirect(url_for('admin.usuarios'))


@bp.route('/usuarios/<int:uid>/situacao', methods=['POST'])
@login_obrigatorio
def usuario_status(uid):
    alvo = get_db().execute('SELECT * FROM usuarios WHERE id=?', (uid,)).fetchone()
    if alvo is None or not _gerir_ou_nao(get_db(), alvo):
        return redirect(url_for('admin.usuarios'))
    if uid == g.usuario['id']:
        flash('Você não pode desativar o próprio acesso.', 'erro')
    else:
        db = get_db()
        db.execute('UPDATE usuarios SET ativo = 1 - ativo WHERE id=?', (uid,))
        db.commit()
        flash('Situação do usuário atualizada.', 'ok')
    return redirect(url_for('admin.usuarios'))


def _acao_usuario(funcao, rotulo, uid):
    alvo = get_db().execute('SELECT * FROM usuarios WHERE id=?', (uid,)).fetchone()
    if alvo is None or not _gerir_ou_nao(get_db(), alvo):
        return
    try:
        nome = funcao(get_db(), uid)
        registrar_acesso(g.usuario['usuario'], rotulo, nome)
        flash('%s: %s.' % (rotulo, nome), 'ok')
    except usuarios_arquivo.ErroUsuario as e:
        flash(str(e), 'erro')


@bp.route('/usuarios/<int:uid>/arquivar', methods=['POST'])
@login_obrigatorio
def usuario_arquivar(uid):
    _acao_usuario(lambda db, i: usuarios_arquivo.arquivar(db, i, g.usuario['id']), 'Perfil arquivado', uid)
    return redirect(url_for('admin.usuarios'))


@bp.route('/usuarios/<int:uid>/desligar', methods=['POST'])
@login_obrigatorio
def usuario_desligar(uid):
    _acao_usuario(lambda db, i: usuarios_arquivo.desligar_funcionario(db, i, g.usuario['id']),
                  'Funcionário desligado e perfil arquivado', uid)
    return redirect(url_for('admin.usuarios'))


@bp.route('/usuarios/<int:uid>/desarquivar', methods=['POST'])
@login_obrigatorio
def usuario_desarquivar(uid):
    _acao_usuario(usuarios_arquivo.desarquivar, 'Perfil desarquivado', uid)
    return redirect(url_for('admin.usuarios', arquivados=1))


@bp.route('/acessos')
@login_obrigatorio
def acessos():
    rows = get_db().execute('SELECT * FROM acessos ORDER BY id DESC LIMIT 1000').fetchall()
    return render_template('acessos.html', rows=rows)


# ---------------------------------------------------------------- backup
# Cada backup é um .zip com sistema.db + anexos.db + LEIA-ME.txt (ver backup_pacote.py). Os .db antigos (só o sistema)
# continuam aparecendo e podendo ser restaurados. Fazer e baixar backup: quem tem o módulo Backup. Restaurar: só a
# administração e a gerência.
CODIGO_VALIDADE = 300
PREFIXO_SEGURANCA = backup_pacote.PREFIXO_SEGURANCA


def pode_restaurar():
    return bool(g.usuario['admin']) or 'gerencia' in (g.get('modulos') or ())


def gerencia_obrigatoria(view):
    @wraps(view)
    @login_obrigatorio
    def inner(*a, **kw):
        if not pode_restaurar():
            flash('A restauração de backup é só para a administração e a gerência.', 'erro')
            return redirect(url_for('admin.backup'))
        return view(*a, **kw)
    return inner


def pasta_backup():
    """Pasta local dos backups (`backups/`, ao lado do banco). O backup é sempre gravado aqui; a pasta externa (Drive, rede)
    recebe uma cópia (ver `backup_pacote.sincronizar_externa`)."""
    p = backup_pacote.pasta_padrao(current_app.config['DATABASE'])
    os.makedirs(p, exist_ok=True)
    return p


def fazer_backup(prefixo='BACKUP'):
    """Gera o .zip com os dois bancos e devolve o nome do arquivo."""
    return os.path.basename(backup_pacote.criar_zip(current_app.config['DATABASE'], prefixo, versao()))


def listar_backups():
    """Backups da pasta (.zip reconhecidos e .db antigos), do mais recente para o mais antigo."""
    pasta = pasta_backup()
    itens = []
    for f in os.listdir(pasta):
        baixo = f.lower()
        caminho = os.path.join(pasta, f)
        if not baixo.endswith(('.zip', '.db')) or baixo.endswith('_anexos.db') or not os.path.isfile(caminho):
            continue
        if baixo.endswith('.zip') and not backup_pacote.eh_zip_de_backup(caminho):
            continue
        itens.append(backup_pacote.info_arquivo(caminho))
    return sorted(itens, key=lambda i: i['mtime'], reverse=True)


def _ultimo_backup():
    """Backup mais recente, sem contar as cópias de segurança que a própria restauração cria."""
    return next((b for b in listar_backups() if not b['nome'].startswith(PREFIXO_SEGURANCA)), None)


@bp.route('/backup', methods=['GET', 'POST'])
@login_obrigatorio
def backup():
    banco = current_app.config['DATABASE']
    if request.method == 'POST':
        try:
            nome = fazer_backup()
        except backup_pacote.ErroBackup as e:
            flash(str(e), 'erro')
            return redirect(url_for('admin.backup'))
        registrar_acesso(g.usuario['usuario'], 'Backup', nome)
        msg = 'Backup realizado com sucesso! Arquivo: %s (sistema + anexos)' % nome
        if backup_pacote.lista_pastas(banco):
            copiados = backup_pacote.sincronizar_externa(banco, 'servidor')
            msg += (' Copiado para as pastas externas.' if copiados is not None else
                    ' A cópia para as pastas externas será feita em alguns minutos pela bandeja do Windows (o ícone verde perto do relógio).')
        flash(msg, 'ok')
        return redirect(url_for('admin.backup'))
    lista = listar_backups()
    externa = backup_pacote.estado_externa(banco)
    externos = _backups_das_pastas(banco)
    if externos:   # a restauração pela pasta externa só aceita o que está nesta lista (mapa nome -> pasta); 30 bastam (cookie pequeno)
        origens = {}
        for i in externos[:30]:
            origens.setdefault(i['nome'], i['pasta'])
        session['restaurar_pasta'] = {'pasta': None, 'nomes': list(origens), 'origens': origens, 'ate': time.time() + 2 * CODIGO_VALIDADE}
    return render_template('backup.html', lista=lista, pasta=pasta_backup(), banco=banco, ultimo=_ultimo_backup(),
                           pode_restaurar=pode_restaurar(), externa=externa, backups_externos=externos[:30],
                           auto=backup_pacote.agenda_automatica(banco, datetime.now()),
                           opcoes_minutos=OPCOES_MINUTOS_BACKUP, max_pastas=backup_pacote.MAX_PASTAS)


@bp.route('/backup/pasta-destino', methods=['POST'])
@gerencia_obrigatoria
def backup_destino():
    """Adiciona uma pasta que recebe cópia dos backups (Google Drive, pendrive, rede). Até MAX_PASTAS pastas, sem repetir.
    Não exige que o servidor enxergue a pasta: ele roda como conta SYSTEM, que não vê o Drive do usuário; a bandeja do Windows copia."""
    banco = current_app.config['DATABASE']
    caminho, erro = backup_pacote.caminho_externo_valido(request.form.get('pasta'))
    if erro:
        flash(erro, 'erro')
        return redirect(url_for('admin.backup'))
    atuais = backup_pacote.lista_pastas(banco, migrar=True)
    if backup_pacote._normaliza(caminho) in {backup_pacote._normaliza(p) for p in atuais}:
        flash('Essa pasta já está na lista de cópias.', 'erro')
        return redirect(url_for('admin.backup'))
    if len(atuais) >= backup_pacote.MAX_PASTAS:
        flash('Já há %d pastas de cópia. Remova uma antes de adicionar outra.' % backup_pacote.MAX_PASTAS, 'erro')
        return redirect(url_for('admin.backup'))
    backup_pacote.salvar_pastas(banco, atuais + [caminho])
    g.detalhe_auditoria = 'pasta externa incluída=%s' % caminho
    flash('Pasta de cópia adicionada: %s. Os backups continuam sendo feitos neste computador e uma cópia dos backups dos últimos 7 dias vai para essa pasta '
          'em alguns minutos, feita pela bandeja do Windows do PC onde a pasta existe.' % caminho, 'ok')
    return redirect(url_for('admin.backup'))


@bp.route('/backup/pasta-destino/remover', methods=['POST'])
@gerencia_obrigatoria
def backup_destino_remover():
    """Tira uma pasta da lista de cópias. Os arquivos que já estão nela não são apagados."""
    banco = current_app.config['DATABASE']
    alvo = backup_pacote._normaliza(request.form.get('pasta') or '')
    atuais = backup_pacote.lista_pastas(banco, migrar=True)
    restantes = [p for p in atuais if backup_pacote._normaliza(p) != alvo]
    if len(restantes) == len(atuais):
        flash('Essa pasta não está na lista de cópias.', 'erro')
        return redirect(url_for('admin.backup'))
    backup_pacote.salvar_pastas(banco, restantes)
    g.detalhe_auditoria = 'pasta externa removida=%s' % request.form.get('pasta')
    flash('Pasta removida da lista de cópias. Os arquivos que já estão nela não foram apagados.', 'ok')
    return redirect(url_for('admin.backup'))


OPCOES_MINUTOS_BACKUP = ((15, '15 min'), (30, '30 min'), (60, '1 h'), (120, '2 h'), (180, '3 h'), (240, '4 h'))


@bp.route('/backup/automatico', methods=['POST'])
@gerencia_obrigatoria
def backup_automatico():
    """Liga ou desliga o backup automático e escolhe a janela do dia (das / até) e a frequência."""
    inicio = backup_pacote._hora_minuto((request.form.get('inicio') or '').strip())
    if inicio is None:
        flash('Informe o horário inicial (Das) no formato 08:00.', 'erro')
        return redirect(url_for('admin.backup'))
    fim = backup_pacote._hora_minuto((request.form.get('fim') or '').strip())
    if fim is None:
        flash('Informe o horário final (Até) no formato 18:00.', 'erro')
        return redirect(url_for('admin.backup'))
    if inicio >= fim:
        flash('O horário inicial (Das) precisa ser menor que o final (Até).', 'erro')
        return redirect(url_for('admin.backup'))
    minutos = backup_pacote.minutos_validos(request.form.get('minutos'))
    if minutos is None:
        flash('Escolha a frequência do backup automático na lista.', 'erro')
        return redirect(url_for('admin.backup'))
    ligado = request.form.get('ligado') == '1'
    inicio_txt, fim_txt = '%02d:%02d' % inicio, '%02d:%02d' % fim
    config_set(backup_pacote.CHAVE_AUTO, '1' if ligado else '0')
    config_set(backup_pacote.CHAVE_AUTO_INICIO, inicio_txt)
    config_set(backup_pacote.CHAVE_AUTO_FIM, fim_txt)
    config_set(backup_pacote.CHAVE_AUTO_MINUTOS, str(minutos))
    g.detalhe_auditoria = 'automático=%s; das %s às %s, a cada %d min' % ('ligado' if ligado else 'desligado', inicio_txt, fim_txt, minutos)
    flash('Backup automático %s.' % (('ligado: das %s às %s, a cada %d min' % (inicio_txt, fim_txt, minutos)) if ligado else 'desligado'), 'ok')
    return redirect(url_for('admin.backup'))


@bp.route('/backup/<path:nome>')
@login_obrigatorio
def backup_baixar(nome):
    return send_from_directory(pasta_backup(), os.path.basename(nome), as_attachment=True)


# Restauração (administração e gerência), em duas etapas: a tela de confirmação sorteia um código que precisa ser digitado
# para valer (5 minutos, uso único, só para o arquivo escolhido), evitando restauração por clique acidental.
def _backup_escolhido(nome):
    """Caminho do backup `nome` na pasta de backups do sistema, se existir; senão None."""
    nome = os.path.basename(nome or '')
    caminho = os.path.join(pasta_backup(), nome)
    return caminho if nome.lower().endswith(('.zip', '.db')) and os.path.isfile(caminho) else None


def _lista_da_pasta_externa():
    """Pasta e nomes encontrados na última busca (guardados na sessão; só o que está nessa lista pode ser restaurado)."""
    lista = session.get('restaurar_pasta')
    if not lista or time.time() > lista['ate']:
        return None
    return lista


def _pasta_de(lista, nome):
    """Pasta onde está `nome` na lista da sessão: pelo mapa de origens (várias pastas de cópia) ou a pasta da busca em outra pasta."""
    return (lista.get('origens') or {}).get(nome) or lista.get('pasta')


def _backups_das_pastas(banco):
    """Backups válidos de todas as pastas de cópia, do mais recente para o mais antigo, cada um com a pasta de origem.
    Pasta que não pode ser lida agora é pulada (a tela mostra o erro dela na situação da cópia)."""
    itens = []
    for pasta in backup_pacote.lista_pastas(banco):
        try:
            itens.extend(dict(i, pasta=pasta) for i in backup_pacote.listar_pasta(pasta))
        except OSError:
            continue
    return sorted(itens, key=lambda i: i['mtime'], reverse=True)


@bp.route('/backup/restaurar', methods=['GET', 'POST'])
@gerencia_obrigatoria
def backup_restaurar():
    if request.method == 'GET':
        externo = request.args.get('origem') == 'pasta'
        pasta = None
        if externo:
            lista = _lista_da_pasta_externa()
            nome = os.path.basename(request.args.get('nome') or '')
            if not lista or nome not in lista['nomes']:
                flash('A busca na outra pasta expirou. Busque de novo.', 'erro')
                return redirect(url_for('admin.backup_pasta'))
            pasta = _pasta_de(lista, nome)
            if not pasta:
                flash('A busca na outra pasta expirou. Busque de novo.', 'erro')
                return redirect(url_for('admin.backup'))
            caminho = os.path.join(pasta, nome)
            if not os.path.isfile(caminho) or os.path.islink(caminho):
                flash('O arquivo não está mais na pasta. Busque de novo.', 'erro')
                return redirect(url_for('admin.backup_pasta'))
            e_ultimo = nome == lista['nomes'][0]
        else:
            nome = request.args.get('nome') or (_ultimo_backup() or {'nome': ''})['nome']
            caminho = _backup_escolhido(nome)
            if not caminho:
                flash('Nenhum backup encontrado para restaurar.', 'erro')
                return redirect(url_for('admin.backup'))
            e_ultimo = os.path.basename(caminho) == (_ultimo_backup() or {}).get('nome')
        codigo = '%06d' % secrets.randbelow(10 ** 6)
        session['restaurar'] = {'nome': os.path.basename(caminho), 'codigo': codigo, 'ate': time.time() + CODIGO_VALIDADE, 'pasta': pasta}
        return render_template('backup_restaurar.html', b=backup_pacote.info_arquivo(caminho), codigo=codigo,
                               banco=current_app.config['DATABASE'], e_ultimo=e_ultimo, pasta=pasta)
    pedido = session.pop('restaurar', None)   # uso único: errou o código, precisa pedir outro
    digitado = (request.form.get('codigo') or '').strip()
    if not pedido or time.time() > pedido['ate'] or request.form.get('nome') != pedido['nome']:
        flash('A confirmação expirou. Peça a restauração novamente.', 'erro')
        return redirect(url_for('admin.backup'))
    volta = url_for('admin.backup_restaurar', nome=pedido['nome'], **({'origem': 'pasta'} if pedido['pasta'] else {}))
    if not secrets.compare_digest(digitado, pedido['codigo']):
        flash('Código de verificação incorreto. Nada foi restaurado.', 'erro')
        return redirect(volta)
    if pedido['pasta']:   # só vale arquivo da lista da busca feita nesta sessão, na mesma pasta
        lista = _lista_da_pasta_externa()
        if not lista or _pasta_de(lista, pedido['nome']) != pedido['pasta'] or pedido['nome'] not in lista['nomes']:
            flash('A busca na outra pasta expirou. Busque de novo.', 'erro')
            return redirect(url_for('admin.backup_pasta'))
        caminho = os.path.join(pedido['pasta'], pedido['nome'])
    else:
        caminho = _backup_escolhido(pedido['nome'])
    if not caminho or not os.path.isfile(caminho):
        flash('O arquivo de backup não foi encontrado. Nada foi restaurado.', 'erro')
        return redirect(url_for('admin.backup'))
    try:
        r = backup_pacote.restaurar(current_app.config['DATABASE'], caminho, versao())
    except backup_pacote.ErroBackup as e:
        flash(str(e), 'erro')
        return redirect(url_for('admin.backup'))
    from . import db as dbmod
    dbmod.inicializar(current_app.config['DATABASE'])   # backups de versões anteriores recebem as colunas novas
    g.detalhe_auditoria = 'arquivo=%s%s' % (pedido['nome'], '; pasta=%s' % pedido['pasta'] if pedido['pasta'] else '')
    registrar_acesso(g.usuario['usuario'], 'Restaurou backup', pedido['nome'])
    msg = 'Backup %s restaurado. O estado anterior ficou salvo em %s. Peça aos usuários para recarregar a página.' % (pedido['nome'], r['seguranca'])
    if not r['com_anexos']:
        msg += ' Atenção: esse backup é do formato antigo (.db) e não contém os anexos; os anexos atuais foram mantidos.'
    flash(msg, 'ok')
    return redirect(url_for('admin.backup'))


def _validar_pasta(bruto):
    """(caminho normalizado, None) ou (None, mensagem). Só pastas existentes, com caminho completo e que não sejam links."""
    bruto = (bruto or '').strip().strip('"')
    if not bruto or '\x00' in bruto:
        return None, 'Informe o caminho da pasta onde estão os backups.'
    if not os.path.isabs(bruto):
        return None, 'Informe o caminho completo da pasta (exemplo: E:\\Backups ou \\\\servidor\\pasta).'
    caminho = os.path.normpath(bruto)
    if not os.path.exists(caminho):
        return None, 'Essa pasta não existe neste computador (a busca é feita no computador onde o sistema está instalado).'
    if not os.path.isdir(caminho) or os.path.islink(caminho):
        return None, 'O caminho informado não é uma pasta comum.'
    return caminho, None


@bp.route('/backup/restaurar-pasta', methods=['GET', 'POST'])
@gerencia_obrigatoria
def backup_pasta():
    """Busca (só leitura) backups válidos em outra pasta: pendrive, outro disco ou pasta de rede."""
    sugestao = config_get('backup_pasta_externa', '')
    if request.method == 'GET':
        return render_template('backup_pasta.html', sugestao=sugestao, lista=None, pasta='')
    caminho, erro = _validar_pasta(request.form.get('pasta'))
    if erro:
        flash(erro, 'erro')
        return render_template('backup_pasta.html', sugestao=request.form.get('pasta') or sugestao, lista=None, pasta='')
    try:
        lista = backup_pacote.listar_pasta(caminho)
    except OSError:
        flash('Sem permissão para ler essa pasta.', 'erro')
        return render_template('backup_pasta.html', sugestao=caminho, lista=None, pasta='')
    config_set('backup_pasta_externa', caminho)   # lembra como sugestão
    g.detalhe_auditoria = 'pasta=%s; backups encontrados=%d' % (caminho, len(lista))
    if not lista:
        flash('Nenhum backup válido (.zip do sistema ou .db) foi encontrado nessa pasta.', 'erro')
    else:
        session['restaurar_pasta'] = {'pasta': caminho, 'nomes': [i['nome'] for i in lista], 'ate': time.time() + 2 * CODIGO_VALIDADE}
    return render_template('backup_pasta.html', sugestao=caminho, lista=lista, pasta=caminho)


@bp.route('/backup/restaurar-pasta/escolher', methods=['POST'])
@gerencia_obrigatoria
def backup_pasta_escolher():
    lista = _lista_da_pasta_externa()
    if not lista:
        flash('A busca na outra pasta expirou. Busque de novo.', 'erro')
        return redirect(url_for('admin.backup_pasta'))
    nome = lista['nomes'][0] if request.form.get('mais_recente') == '1' else os.path.basename(request.form.get('nome') or '')
    if nome not in lista['nomes']:   # nunca um caminho enviado livremente: só o que a busca listou
        flash('Esse arquivo não está na lista encontrada.', 'erro')
        return redirect(url_for('admin.backup_pasta'))
    return redirect(url_for('admin.backup_restaurar', nome=nome, origem='pasta'))


# ---------------------------------------------------------------- pastas
# O navegador não abre pastas do Windows por conta própria (e o servidor roda como serviço, sem janela).
# Solução: um "protocolo" nucleleste-pasta: registrado em cada computador (uma vez, pelo arquivo .reg abaixo) que
# abre a pasta no Explorador DAQUELE computador, onde o caminho (Z:\\..., \\\\servidor\\...) realmente existe.
PROTOCOLO = 'nucleleste-pasta'


def _hosts_unc(lista):
    hosts = set()
    for p in lista:
        c = (p.get('caminho') or '').strip()
        if c.startswith('\\\\'):
            hosts.add(c[2:].split('\\')[0].lower())
    return sorted(h for h in hosts if h)


def _comando_protocolo(hosts):
    """Linha de comando do protocolo: só abre PASTAS (nunca executa arquivos), em unidade mapeada ou servidor conhecido."""
    permitidos = ','.join("'%s'" % h.replace("'", '') for h in hosts) or "''"
    ps = ("$q=[char]34;$p=[uri]::UnescapeDataString('%1') -replace '^" + PROTOCOLO + ":/*','';$p=$p.Replace('/','\\').Trim();"
          "$ok=$false;if($p -match '^[A-Za-z]:\\\\'){$ok=$true}"
          "elseif($p -match '^\\\\\\\\([^\\\\]+)\\\\'){if(@(" + permitidos + ") -contains $Matches[1].ToLower()){$ok=$true}};"
          "if($ok -and (Test-Path -LiteralPath $p)){"
          "if(Test-Path -LiteralPath $p -PathType Container){Start-Process explorer.exe -ArgumentList ($q+$p+$q)}"
          "else{Start-Process explorer.exe -ArgumentList ('/select,'+$q+$p+$q)}}")
    return 'powershell.exe -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -Command "' + ps + '"'


@bp.route('/pastas/configurar-computador.reg')
@login_obrigatorio
def pastas_reg():
    try:
        lista = json.loads(config_get('pastas', '[]'))
    except ValueError:
        lista = []
    comando = _comando_protocolo(_hosts_unc(lista))
    valor = comando.replace('\\', '\\\\').replace('"', '\\"')
    reg = ('Windows Registry Editor Version 5.00\r\n\r\n'
           '[HKEY_CURRENT_USER\\Software\\Classes\\%(p)s]\r\n@="URL:Nucleleste - abrir pasta"\r\n"URL Protocol"=""\r\n\r\n'
           '[HKEY_CURRENT_USER\\Software\\Classes\\%(p)s\\shell\\open\\command]\r\n@="%(v)s"\r\n') % {'p': PROTOCOLO, 'v': valor}
    resp = Response(('\ufeff' + reg).encode('utf-16-le'), mimetype='application/octet-stream')
    resp.headers['Content-Disposition'] = 'attachment; filename="Nucleleste - abrir pastas neste computador.reg"'
    return resp


@bp.route('/pastas', methods=['GET', 'POST'])
@login_obrigatorio
def pastas():
    try:
        lista = json.loads(config_get('pastas', '[]'))
    except ValueError:
        lista = []
    if request.method == 'POST':
        if g.usuario['admin']:
            nomes = request.form.getlist('nome')
            caminhos = request.form.getlist('caminho')
            nova = [{'nome': n.strip(), 'caminho': c.strip()} for n, c in zip(nomes, caminhos) if n.strip() and c.strip()]
            config_set('pastas', json.dumps(nova, ensure_ascii=False))
            flash('Atalhos salvos.', 'ok')
        return redirect(url_for('admin.pastas'))
    return render_template('pastas.html', lista=lista, protocolo=PROTOCOLO)


# ---------------------------------------------------------------- mensagens do WhatsApp (só gerência)
@bp.route('/mensagens-whatsapp', methods=['GET', 'POST'])
@login_obrigatorio
def mensagens_whats():
    if request.method == 'POST':
        if request.form.get('acao') == 'restaurar':
            mw.restaurar()
            flash('Mensagens voltaram ao texto padrão.', 'ok')
        else:
            mw.salvar(request.form)
            flash('Mensagens salvas.', 'ok')
        return redirect(url_for('admin.mensagens_whats'))
    return render_template('mensagens_whats.html', textos=mw.atuais(), tipos=mw.TIPOS, variaveis=mw.VARIAVEIS)


# ---------------------------------------------------------------- configurações
@bp.route('/configuracoes', methods=['GET', 'POST'])
@login_obrigatorio
def configuracoes():
    chaves = [('clinica_nome', 'Nome da clínica'), ('clinica_cidade', 'Cidade - UF (usada nos documentos)'),
              ('clinica_cnpj', 'CNPJ'),
              ('clinica_endereco', 'Endereço da clínica (usado nos documentos)'),
              ('clinica_telefone', 'Telefone / contato da clínica (usado nos documentos)'),
              ('laudos_pasta_word', 'Pasta dos laudos em Word (o botão “Abrir laudo” dos exames anteriores, em Lançar atendimento, '
                                    'procura nela o arquivo com o nome do paciente)')]
    if request.method == 'POST':
        for k, _ in chaves:
            config_set(k, (request.form.get(k) or '').strip().strip('"'))
        config_set('agenda_aviso_mibi', '1' if request.form.get('agenda_aviso_mibi') == '1' else '0')
        config_set('laudo_previsao_ficha', '1' if request.form.get('laudo_previsao_ficha') == '1' else '0')
        pasta = config_get('laudos_pasta_word', '')
        if pasta and not os.path.isdir(pasta):
            flash('Configurações salvas, mas a pasta dos laudos não foi encontrada neste computador: confira o caminho.', 'aviso')
        else:
            flash('Configurações salvas.', 'ok')
            from . import laudos_word
            laudos_word.limpar_cache()
        return redirect(url_for('admin.configuracoes'))
    valores = {k: config_get(k, '') for k, _ in chaves}
    return render_template('configuracoes.html', chaves=chaves, valores=valores,
                           agenda_aviso_mibi=config_get('agenda_aviso_mibi', '1') != '0',
                           laudo_previsao_ficha=config_get('laudo_previsao_ficha', '1') != '0')
