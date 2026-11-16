"""Tela da gerência para a integração com a Medcloud: ligar/desligar, login e senha, convênios e fila do robô."""
from flask import Blueprint, flash, redirect, render_template, request, url_for

from . import login_obrigatorio, medcloud
from .db import agora, config_get, config_set, get_db

bp = Blueprint('medc', __name__)


def _fila_recente(db):
    return db.execute(
        'SELECT f.id, f.atendimento_id, f.estado, f.tentativas, f.erro, f.atualizado_em, f.compartilhado, f.comp_erro, a.cliente_nome, a.convenio, a.exame, a.data '
        'FROM medcloud_fila f LEFT JOIN atendimentos a ON a.id=f.atendimento_id ORDER BY f.id DESC LIMIT 30').fetchall()


@bp.route('/medcloud', methods=['GET', 'POST'])
@login_obrigatorio
def pagina():
    db = get_db()
    if request.method == 'POST':
        acao = request.form.get('acao', 'salvar')
        if acao == 'tentar':
            aid = request.form.get('atendimento_id', type=int)
            if aid and (medcloud.tentar_de_novo(db, aid) | medcloud.tentar_compartilhar_de_novo(db, aid)):
                db.commit()
                medcloud.acordar()
                flash('Pedido recolocado na fila do robô.', 'ok')
            return redirect(url_for('medc.pagina'))
        login = (request.form.get('login') or '').strip()
        senha = request.form.get('senha') or ''
        if acao == 'testar':
            # testa o que está no formulário; senha em branco usa a que já está gravada
            senha_teste = senha or medcloud.decifrar(config_get('medcloud_senha', ''))
            if not login or not senha_teste:
                flash('Informe o login e a senha da Medcloud para testar.', 'erro')
            else:
                ok, msg = medcloud.testar_conexao(login, senha_teste, config_get('medcloud_url', 'https://medcloud.co'))
                flash(msg, 'ok' if ok else 'erro')
            return redirect(url_for('medc.pagina'))
        # salvar
        config_set('medcloud_ativo', '1' if request.form.get('ativo') == '1' else '0')
        if login:
            config_set('medcloud_login', login)
        if senha:   # senha em branco mantém a atual; nunca é exibida de volta
            config_set('medcloud_senha', medcloud.cifrar(senha))
        # horário de funcionamento: início e fim (HH:MM) e dias da semana (0 = segunda ... 6 = domingo)
        inicio = (request.form.get('inicio') or '').strip()
        fim = (request.form.get('fim') or '').strip()
        dias = ''.join(sorted({d for d in request.form.getlist('dia') if d in '0123456' and len(d) == 1}))
        horario = request.form.get('horario') == '1'
        if horario and (medcloud._minutos(inicio) is None or medcloud._minutos(fim) is None or inicio == fim):
            flash('Horário de funcionamento não salvo: informe um início e um fim diferentes (ex.: 05:50 e 19:00).', 'erro')
            horario = False
        elif horario and not dias:
            flash('Horário de funcionamento não salvo: marque pelo menos um dia da semana.', 'erro')
            horario = False
        config_set('medcloud_horario', '1' if horario else '0')
        if medcloud._minutos(inicio) is not None:
            config_set('medcloud_inicio', inicio)
        if medcloud._minutos(fim) is not None:
            config_set('medcloud_fim', fim)
        if dias:
            config_set('medcloud_dias', dias)
        marcados = {int(x) for x in request.form.getlist('convenio') if x.isdigit()}
        db.execute('UPDATE convenios SET medcloud=0')
        for cid in marcados:
            db.execute('UPDATE convenios SET medcloud=1 WHERE id=?', (cid,))
        db.commit()
        if request.form.get('ativo') == '1' and not medcloud.ativo(db):
            flash('Salvo, mas a função só funciona depois que o login e a senha da Medcloud forem informados.', 'aviso')
        else:
            flash('Configuração da Medcloud salva.', 'ok')
        return redirect(url_for('medc.pagina'))
    convenios = db.execute('SELECT id, nome, medcloud FROM convenios WHERE ativo=1 ORDER BY nome').fetchall()
    return render_template('medcloud.html', ativo=config_get('medcloud_ativo', '0') == '1',
                           login=config_get('medcloud_login', ''), tem_senha=bool(config_get('medcloud_senha', '')),
                           convenios=convenios, fila=_fila_recente(db), agora=agora(),
                           horario=config_get('medcloud_horario', '0') == '1',
                           inicio=config_get('medcloud_inicio', '05:50'), fim=config_get('medcloud_fim', '19:00'),
                           dias=config_get('medcloud_dias', '0123456'),
                           dias_nomes=[('0', 'Seg'), ('1', 'Ter'), ('2', 'Qua'), ('3', 'Qui'), ('4', 'Sex'), ('5', 'Sáb'), ('6', 'Dom')],
                           operando=medcloud.operando(db))
