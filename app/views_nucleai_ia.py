"""Aba IA online da NucleAI (gerência e administração): chat de treinamento, painel, níveis por usuário, memória,
configurações e o botão Liberar (com código) / Desativar."""
from __future__ import annotations

from datetime import datetime, timedelta

from flask import Blueprint, flash, g, jsonify, redirect, render_template, request, url_for

from . import llm, login_obrigatorio, modulos
from . import nucleai_ferramentas as ferr
from . import nucleai_ia as ia
from . import nucleai_memoria as mem
from . import nucleai_motor as motor
from . import nucleai_tokens
from . import nucleai_trocas
from .db import get_db

bp = Blueprint('nucleaiia', __name__, url_prefix='/nucleai/ia')


def _usuarios(db):
    saida = []
    for u in db.execute("SELECT id, usuario, admin, modulos FROM usuarios WHERE ativo=1 AND COALESCE(sistema,0)=0 ORDER BY usuario").fetchall():
        saida.append({'id': u['id'], 'usuario': u['usuario'], 'admin': bool(u['admin']),
                      'gerencia': 'gerencia' in modulos.modulos_do_usuario(u), 'nivel': ia.nivel(db, u['id']),
                      'hoje': ia.usos_hoje(db, u['id'])})
    return saida


def _tempo(segundos):
    if not segundos:
        return '—'
    d, resto = divmod(int(segundos), 86400)
    h, resto = divmod(resto, 3600)
    m = resto // 60
    return ('%d dia(s), %d h' % (d, h)) if d else ('%d h %d min' % (h, m)) if h else '%d min' % m


def _codigo_pendente(db):
    codigo, em = ia.cfg(db, 'nucleai_llm_codigo'), ia.cfg(db, 'nucleai_llm_codigo_em')
    if not codigo or not em:
        return None
    try:
        validade = datetime.strptime(em, ia.FMT) + timedelta(minutes=ia.CODIGO_VALIDADE_MIN)
    except ValueError:
        return None
    return {'codigo': codigo, 'ate': validade.strftime('%H:%M')} if validade > datetime.now() else None


@bp.route('')
@login_obrigatorio
def pagina():
    db = get_db()
    arquivo = request.args.get('arquivo') if request.args.get('arquivo') in mem.ARQUIVOS else mem.GEMINI
    log = [dict(r) for r in db.execute("SELECT * FROM nucleai_llm_log ORDER BY id DESC LIMIT 60").fetchall()]
    hoje = datetime.now().strftime('%Y-%m-%d')
    uso = db.execute('SELECT COALESCE(SUM(qtd),0) AS qtd, COALESCE(SUM(tokens),0) AS tokens FROM nucleai_llm_uso WHERE dia=?', (hoje,)).fetchone()
    conteudo = mem.ler(db, arquivo)
    modelos = ia.modelos(db)
    try:
        resumo_chave = llm.resumo_chave(db)
        tem_chave = bool(llm.chave(db))
    except llm.ErroLLM:
        resumo_chave, tem_chave = 'não foi possível ler a chave', False
    filtro_periodo = request.args.get('periodo', '').strip()
    filtro_modelo = request.args.get('modelo', '').strip()
    filtro_classificacao = request.args.get('classificacao', '').strip()
    trocas_lista = nucleai_trocas.listar(db, periodo=filtro_periodo, modelo=filtro_modelo, classificacao=filtro_classificacao)
    trocas_cont = nucleai_trocas.contadores(db)
    modelos_troca = sorted(set([m['slug'] for m in modelos] +
                               [t['de'] for t in trocas_lista if t.get('de')] +
                               [t['para'] for t in trocas_lista if t.get('para')]))
    saude = nucleai_tokens.indicadores_saude(db)
    tokens_resumo = nucleai_tokens.resumo_geral(db, 'hoje')
    db.commit()
    return render_template(
        'nucleai_ia.html', estado=ia.estado(db), ligada=ia.cfg(db, 'nucleai_llm_ativo') == '1', contadores=ia.contadores(db),
        tempo_ativa=_tempo(ia.contadores(db)['tempo_ativa_s']), auto=ia.autoavaliacao(db), uso=dict(uso),
        tem_chave=tem_chave, resumo_chave=resumo_chave, var_chave=llm.VAR_CHAVE,
        modelos=modelos, pausas=ia.pausas(db), ultimo_erro=ia.ultimo_erro(db), codigo=_codigo_pendente(db),
        cfg={k: ia.cfg(db, k) for k in ia.PADROES}, usuarios=_usuarios(db), niveis=ferr.NOMES_NIVEL, descricoes=ferr.DESCRICAO_NIVEL,
        treinador=ia.treinador_atual(db, g.usuario['id']), treinadores=ia.listar_treinadores(db),
        conversa=motor.conversa_treino(db, g.usuario['id'], treinador=ia.treinador_atual(db, g.usuario['id'])['nome']), arquivo=arquivo, arquivos=mem.ARQUIVOS, conteudo=conteudo,
        caminho=mem.caminho_arquivo(db, arquivo), versoes=mem.versoes(db, arquivo), log=log, max_memoria=mem.MAX_BYTES,
        trocas=trocas_lista, trocas_contadores=trocas_cont, filtro_periodo=filtro_periodo, filtro_modelo=filtro_modelo,
        filtro_classificacao=filtro_classificacao, modelos_troca=modelos_troca,
        saude=saude, tokens_resumo=tokens_resumo)


@bp.route('/treino', methods=['POST'])
@login_obrigatorio
def treino():
    db = get_db()
    dados = request.get_json(silent=True) or request.form
    try:
        novas = motor.responder_treino(db, g.usuario['id'], dados.get('texto', ''))
    except ValueError as e:
        return jsonify({'ok': False, 'erro': str(e)}), 400
    return jsonify({'ok': True, 'mensagens': novas, 'treinador': ia.treinador_atual(db, g.usuario['id'])['nome']})


@bp.route('/treino/novo', methods=['POST'])
@login_obrigatorio
def novo_teste():
    db = get_db()
    novo_nome = ia.iniciar_conversa_teste(db, g.usuario['id'])
    db.commit()
    flash(f'Nova conversa de teste iniciada ({novo_nome}). A IA verá você com este usuário.', 'ok')
    return redirect(url_for('nucleaiia.pagina'))


@bp.route('/treino/limpar', methods=['POST'])
@login_obrigatorio
def limpar_teste():
    db = get_db()
    t = ia.treinador_atual(db, g.usuario['id'])
    motor.apagar_conversa_treino(db, g.usuario['id'], t['nome'])
    db.commit()
    flash(f'Histórico da conversa de teste ({t["nome"]}) apagado. O contexto foi limpo.', 'ok')
    return redirect(url_for('nucleaiia.pagina'))


@bp.route('/config', methods=['POST'])
@login_obrigatorio
def config():
    db = get_db()
    f = request.form
    acao = f.get('acao_ia')
    if acao:
        try:
            if acao in ('chave_salvar', 'chave_apagar'):
                llm.salvar_chave(None if acao == 'chave_apagar' else f.get('openrouter_chave', ''), db)
                mensagem = 'Chave da IA atualizada.'
            else:
                lista = ia.modelos(db)
                if acao == 'modelo_adicionar':
                    lista.append({'slug': f.get('modelo_slug', '').strip(), 'ativo': True})
                else:
                    slug = f.get('modelo_slug')
                    indice = next((i for i, m in enumerate(lista) if m['slug'] == slug), None)
                    if indice is None:
                        raise ValueError('Modelo não encontrado.')
                    if acao == 'modelo_alternar':
                        lista[indice]['ativo'] = not lista[indice]['ativo']
                    elif acao == 'modelo_remover':
                        lista.pop(indice)
                    elif acao in ('modelo_subir', 'modelo_descer'):
                        destino = indice + (-1 if acao == 'modelo_subir' else 1)
                        if 0 <= destino < len(lista):
                            lista[indice], lista[destino] = lista[destino], lista[indice]
                    else:
                        raise ValueError('Ação de configuração inválida.')
                ia.salvar_modelos(db, lista)
                mensagem = 'Lista de modelos atualizada.'
            db.commit()
            # Detalhe fixo; o formulário da chave nunca é reproduzido na auditoria.
            g.detalhe_auditoria = mensagem
            flash(mensagem, 'ok')
        except ValueError as e:
            db.rollback()
            flash(str(e), 'erro')
        return redirect(url_for('nucleaiia.pagina') + '#config')
    try:
        limites = {n: int(f.get('limite_n%d' % n, '')) for n in range(1, 5)}
        por_min = int(f.get('limite_min', ''))
        padrao = int(f.get('padrao_nivel', '0'))
        timeout = int(f.get('timeout_s', ia.cfg(db, 'nucleai_llm_timeout_s')))
        pausa = int(f.get('pausa_min', ia.cfg(db, 'nucleai_llm_pausa_min')))
        tolerancia = int(f.get('tolerancia_remarcacao', ia.cfg(db, 'nucleai_llm_tolerancia_remarcacao')))
    except ValueError:
        flash('Informe os limites em números.', 'erro')
        return redirect(url_for('nucleaiia.pagina') + '#config')
    if (any(not 0 <= v <= 5000 for v in limites.values()) or not 1 <= por_min <= 60 or not 0 <= padrao <= 4
            or not 1 <= timeout <= 120 or not 1 <= pausa <= 1440 or not 0 <= tolerancia <= 240):
        flash('Limites fora da faixa: dia 0–5000, minuto 1–60, nível 0–4, timeout 1–120 s, pausa 1–1440 min.', 'erro')
        return redirect(url_for('nucleaiia.pagina') + '#config')
    if ia.estado(db) != ia.DESATIVADA:
        ia.definir(db, 'nucleai_llm_ativo', '1' if f.get('ativo') else '0')
    ia.definir(db, 'nucleai_llm_timeout_s', timeout)
    ia.definir(db, 'nucleai_llm_pausa_min', pausa)
    ia.definir(db, 'nucleai_llm_tolerancia_remarcacao', tolerancia)
    for n, v in limites.items():
        ia.definir(db, 'nucleai_llm_limite_dia_n%d' % n, v)
    ia.definir(db, 'nucleai_llm_limite_min', por_min)
    ia.definir(db, 'nucleai_llm_padrao_nivel', padrao)
    ia.definir(db, 'nucleai_llm_dados_pacientes', '1' if f.get('dados_pacientes') else '0')
    ia.definir(db, 'nucleai_llm_treino_real', '1' if f.get('treino_real') else '0')
    db.commit()
    flash('Configurações da IA salvas.', 'ok')
    return redirect(url_for('nucleaiia.pagina') + '#config')


@bp.route('/niveis', methods=['POST'])
@login_obrigatorio
def niveis():
    db = get_db()
    mudou = 0
    for u in _usuarios(db):
        v = request.form.get('nivel_%d' % u['id'])
        if v is None or not v.isdigit():
            continue
        n = int(v)
        if 0 <= n <= 4 and n != u['nivel']:
            ia.definir_nivel(db, u['id'], n, g.usuario['usuario'])
            mudou += 1
    db.commit()
    g.detalhe_auditoria = '%d nível(is) alterado(s)' % mudou
    flash('Níveis salvos (%d alteração(ões)).' % mudou, 'ok')
    return redirect(url_for('nucleaiia.pagina') + '#niveis')


@bp.route('/teste', methods=['POST'])
@login_obrigatorio
def teste():
    db = get_db()
    try:
        ia.gerar_com_troca(db, 'Responda somente: OK', [{'role': 'user', 'content': 'Teste de conexão'}], baixar=motor.BAIXAR)
        flash('Conexão com a IA funcionando.', 'ok')
    except llm.ErroLLM as e:
        flash('Falha no teste: %s' % e, 'erro')
    return redirect(url_for('nucleaiia.pagina'))


@bp.route('/codigo', methods=['POST'])
@login_obrigatorio
def codigo():
    db = get_db()
    ia.gerar_codigo_liberacao(db)
    db.commit()
    flash('Código de liberação gerado. Digite-o abaixo para confirmar.', 'ok')
    return redirect(url_for('nucleaiia.pagina') + '#liberar')


@bp.route('/liberar', methods=['POST'])
@login_obrigatorio
def liberar():
    db = get_db()
    try:
        tem_chave = bool(llm.chave(db))
    except llm.ErroLLM:
        tem_chave = False
    if not tem_chave:
        flash('Configure a chave da IA antes de liberar para o time.', 'erro')
        return redirect(url_for('nucleaiia.pagina') + '#saude')

    codigo = request.form.get('codigo', '').strip()
    if not codigo and (request.form.get('confirmar') == '1' or request.form.get('direto') == '1'):
        codigo = ia.gerar_codigo_liberacao(db)

    if ia.liberar(db, codigo, g.usuario['usuario']):
        db.commit()
        flash('A NucleAI com IA está ligada para os usuários (conforme o nível de cada usuário).', 'ok')
    else:
        db.commit()
        flash('Código errado ou vencido. Gere um novo código.', 'erro')
    return redirect(url_for('nucleaiia.pagina') + '#saude')


@bp.route('/desativar', methods=['POST'])
@login_obrigatorio
def desativar():
    db = get_db()
    ia.desativar(db, g.usuario['usuario'])
    db.execute("UPDATE nucleai_llm_sessao SET modo='IA', pendente=NULL")
    db.commit()
    flash('IA desativada. Todos voltam à NucleAI automática. Para testar de novo, use "Voltar ao teste".', 'ok')
    return redirect(url_for('nucleaiia.pagina') + '#saude')


@bp.route('/treinar', methods=['POST'])
@login_obrigatorio
def treinar():
    db = get_db()
    ia.definir_estado(db, ia.TREINO)
    ia.definir(db, 'nucleai_llm_ativo', '1')
    ia.registrar_log(db, None, g.usuario['usuario'], 'IA voltou ao treino', None, modo='EVENTO')
    db.commit()
    flash('A IA voltou ao modo de teste: só a gerência conversa com ela, pelo Fake Chat (chat de teste).', 'ok')
    return redirect(url_for('nucleaiia.pagina') + '#saude')


@bp.route('/tokens')
@login_obrigatorio
def tokens():
    db = get_db()
    periodo = request.args.get('periodo', '30d').strip()

    geral = nucleai_tokens.resumo_geral(db, periodo)
    modelos = nucleai_tokens.por_modelo(db, periodo)
    dias = nucleai_tokens.por_dia(db, periodo)
    horas = nucleai_tokens.por_hora(db, periodo)
    usuarios = nucleai_tokens.por_usuario(db, periodo)
    pedidos = nucleai_tokens.maiores_pedidos(db, periodo, limite=20)
    histograma = nucleai_tokens.histograma_pedidos(db, periodo)

    svg_modelo = nucleai_tokens.svg_grafico_barras(modelos, 'modelo', 'tokens_total', 'Gasto por Modelo', sufixo='tokens')
    svg_dia = nucleai_tokens.svg_grafico_linhas(dias, 'dia', 'tokens_total', 'Gasto por Dia', sufixo='tokens')
    svg_hora = nucleai_tokens.svg_grafico_barras(horas, 'hora', 'tokens_total', 'Gasto por Hora do Dia', sufixo='tokens', max_larg_barra=18)
    svg_hist = nucleai_tokens.svg_grafico_barras(histograma, 'faixa', 'pedidos', 'Distribuição por Tamanho de Pedido', sufixo='pedidos')
    svg_usuario = nucleai_tokens.svg_grafico_barras(usuarios, 'usuario', 'tokens_total', 'Gasto por Usuário', sufixo='tokens')

    if request.headers.get('Accept') == 'application/json' or request.args.get('formato') == 'json':
        return jsonify({
            'periodo': periodo,
            'geral': geral,
            'modelos': modelos,
            'dias': dias,
            'horas': horas,
            'usuarios': usuarios,
            'pedidos': pedidos,
            'histograma': histograma,
        })

    db.commit()
    return render_template(
        'nucleai_tokens.html',
        periodo=periodo,
        geral=geral,
        modelos=modelos,
        dias=dias,
        horas=horas,
        usuarios=usuarios,
        pedidos=pedidos,
        histograma=histograma,
        svg_modelo=svg_modelo,
        svg_dia=svg_dia,
        svg_hora=svg_hora,
        svg_hist=svg_hist,
        svg_usuario=svg_usuario,
    )


@bp.route('/memoria', methods=['POST'])
@login_obrigatorio
def memoria():
    db = get_db()
    arquivo = request.form.get('arquivo')
    try:
        mem.salvar(db, arquivo, request.form.get('conteudo', ''), g.usuario['usuario'], 'Editado na aba IA online')
        db.commit()
        flash('%s salvo.' % arquivo, 'ok')
    except mem.ErroMemoria as e:
        flash(str(e), 'erro')
    return redirect(url_for('nucleaiia.pagina', arquivo=arquivo) + '#memoria')


@bp.route('/memoria/reverter', methods=['POST'])
@login_obrigatorio
def reverter():
    db = get_db()
    try:
        arquivo = mem.reverter(db, request.form.get('versao', type=int), g.usuario['usuario'])
        db.commit()
        flash('Versão restaurada em %s.' % arquivo, 'ok')
    except mem.ErroMemoria as e:
        arquivo = mem.GEMINI
        flash(str(e), 'erro')
    return redirect(url_for('nucleaiia.pagina', arquivo=arquivo) + '#memoria')


@bp.route('/log/<int:lid>/nota', methods=['POST'])
@login_obrigatorio
def nota(lid):
    db = get_db()
    n = request.form.get('nota', type=int)
    if n is None or not 1 <= n <= 5:
        return jsonify({'ok': False, 'erro': 'Nota de 1 a 5.'}), 400
    db.execute("UPDATE nucleai_llm_log SET nota=? WHERE id=? AND modo='IA'", (n, lid))
    db.commit()
    return jsonify({'ok': True})


@bp.route('/trocas/classificar', methods=['POST'])
@login_obrigatorio
def classificar_troca():
    db = get_db()
    tid = request.form.get('id', '').strip()
    valor = request.form.get('valor', '').strip()
    try:
        nucleai_trocas.classificar(db, tid, valor, g.usuario['usuario'])
        db.commit()
        flash('Classificação da troca atualizada.', 'ok')
    except ValueError as e:
        flash(str(e), 'erro')
    periodo = request.form.get('periodo', '').strip()
    modelo = request.form.get('modelo', '').strip()
    classificacao = request.form.get('classificacao', '').strip()
    params = {}
    if periodo:
        params['periodo'] = periodo
    if modelo:
        params['modelo'] = modelo
    if classificacao:
        params['classificacao'] = classificacao
    return redirect(url_for('nucleaiia.pagina', **params) + '#trocas')

