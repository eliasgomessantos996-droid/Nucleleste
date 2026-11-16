"""Motor da NucleAI IA: monta a conversa, chama o OpenRouter, executa ferramentas e grava respostas.

Serve aos dois chats:
- o do time (Mensagens, contato NucleAI), depois que a gerência libera a IA (`talvez_responder`, chamado por ajuda.responder);
- o de treinamento (aba IA online), só para a gerência (`responder_treino`).

Sem internet, sem cota ou com o serviço fora do ar, a conversa do time passa para o modo automático (por regras),
com um aviso. A cada nova mensagem a conexão é testada; quando volta, a resposta automática é cancelada, a IA avisa
que voltou, lê a conversa e responde.
"""
from __future__ import annotations

import json
import re
import threading
import time

from . import llm
from . import nucleai_conhecimento as conh
from . import nucleai_ferramentas as ferr
from . import nucleai_ia as ia
from . import nucleai_ilustrar as ilustrar_mod
from .ajuda_busca import normalizar
from .db import agora

MAX_PASSOS = 4             # rodadas de ferramentas por pergunta
HISTORICO = 14             # mensagens anteriores enviadas ao modelo
SIMULTANEAS = 3            # chamadas à IA ao mesmo tempo (o servidor atende muita gente com poucas threads)
ESPERA_VAGA_S = 8
_vagas = threading.BoundedSemaphore(SIMULTANEAS)

# Pontos de injeção para os testes (None = rede de verdade)
BAIXAR = None
BAIXAR_CONEXAO = None

AVISOS_QUEDA = {
    'rede': 'Não consegui me conectar à internet agora. 📡 Vou continuar no modo automático, com as respostas programadas, '
            'e volto assim que a conexão voltar.',
    'cota': 'Atingi o limite de uso da IA por enquanto. Vou continuar no modo automático, com as respostas programadas, '
            'e volto quando o limite for renovado.',
    'servidor': 'O serviço de IA está fora do ar no momento. Vou continuar no modo automático, com as respostas programadas.',
    'sem_chave': 'A IA ainda não foi configurada neste computador (falta a chave). Vou responder no modo automático.',
    'resposta': 'A IA não conseguiu responder agora. Vou continuar no modo automático, com as respostas programadas.',
}
AVISOS_COTA = {
    'conta_dia': 'Atingi o limite de uso diário dos modelos gratuitos da IA (o limite vale para a conta toda, não para '
                 'cada modelo). Vou continuar no modo automático, com as respostas programadas.',
    'conta_min': 'Recebi pedidos demais em pouco tempo e atingi o limite de uso por minuto da IA. Vou continuar no modo '
                 'automático, com as respostas programadas, por um instante.',
    'credito': 'O saldo da conta da IA acabou, então atingi o limite de uso por enquanto. Vou continuar no modo '
               'automático, com as respostas programadas.',
}


def aviso_queda(e):
    """Texto de aviso para a queda da IA; na cota, diz qual limite estourou e quando volta a tentar."""
    base = AVISOS_QUEDA.get(e.tipo, AVISOS_QUEDA['resposta'])
    if e.tipo == 'cota':
        base = AVISOS_COTA.get(getattr(e, 'escopo', ''), base)
        if getattr(e, 'retorno', ''):
            base += ' Volto a tentar %s.' % e.retorno
    return base


def _detalhe_queda(e):
    """Motivo dado pela OpenRouter, para os registros (nunca contém a chave)."""
    d = getattr(e, 'detalhe', '')
    return ' · %s' % d if d else ''


AVISO_VOLTEI = 'A conexão voltou! Sou eu de novo, a NucleAI com IA. Li a nossa conversa e vou continuar daqui.'
OCUPADA = 'Estou atendendo muitas pessoas ao mesmo tempo. Tente de novo em alguns segundos, por favor.'

_SIM = {'sim', 's', 'pode', 'confirmo', 'confirma', 'confirmar', 'ok', 'isso', 'manda', 'aplica', 'aplicar', 'claro', 'certo'}
_NAO = {'nao', 'n', 'cancela', 'cancelar', 'cancele', 'desisto', 'pare', 'deixa'}


def sim_ou_nao(texto):
    p = normalizar(texto).replace(',', ' ').replace('.', ' ').replace('!', ' ').split()
    if not p or len(p) > 5:
        return None
    if set(p) & _NAO:
        return False
    if set(p) & _SIM:
        return True
    return None


# ------------------------------------------------------------------ conversa
def _historico_time(db, uid):
    from . import ajuda
    bot = ajuda.bot_id(db)
    linhas = db.execute('SELECT id, de_id, corpo, cartao, anexo_id, anexo_nome, anexo_tipo FROM chat_mensagens '
                        'WHERE (de_id=? AND para_id=?) OR (de_id=? AND para_id=?) '
                        'ORDER BY id DESC LIMIT ?', (uid, bot, bot, uid, HISTORICO)).fetchall()
    return [{'role': 'assistant' if r['de_id'] == bot else 'user',
             'content': _texto_msg(r['corpo'], r['cartao'], r['id'], r['anexo_id'], r['anexo_nome'], r['anexo_tipo'])}
            for r in reversed(linhas)]


def _historico_treino(db, uid, treinador=None):
    if treinador:
        linhas = db.execute(
            'SELECT papel, texto, cartao FROM nucleai_treino_msgs '
            'WHERE usuario_id=? AND (treinador=? OR (?=? AND treinador IS NULL)) '
            'ORDER BY id DESC LIMIT ?',
            (uid, treinador, treinador, ia.TREINADOR_PADRAO, HISTORICO)
        ).fetchall()
    else:
        linhas = db.execute('SELECT papel, texto, cartao FROM nucleai_treino_msgs WHERE usuario_id=? ORDER BY id DESC LIMIT ?',
                            (uid, HISTORICO)).fetchall()
    return [{'role': 'assistant' if r['papel'] == 'ia' else 'user', 'content': _texto_msg(r['texto'], r['cartao'])}
            for r in reversed(linhas) if r['papel'] in ('ia', 'treinador')]


def _texto_msg(corpo, cartao, msg_id=None, anexo_id=None, anexo_nome=None, anexo_tipo=None):
    t = corpo or ''
    if anexo_id and anexo_tipo and anexo_tipo != 'APAGADA':
        t += ' [arquivo anexado #%s: %s]' % (msg_id or '?', anexo_nome or 'arquivo')
    if cartao:
        try:
            c = json.loads(cartao)
            if c.get('tipo') == 'IA_ILUSTRACAO':
                t += ' [ilustração #%s (%s): %s]' % (c.get('id', '?'), c.get('subtipo', '?'), c.get('titulo') or 'sem título')
            else:
                t += ' [cartão mostrado: %s]' % (c.get('titulo') or c.get('tipo'))
        except ValueError:
            pass
    return t or '(vazio)'


# ------------------------------------------------------------------ proteção contra dados inventados
# Ferramentas que NÃO trazem dados do sistema: chamar só estas não autoriza falar de agenda, contas, números...
NAO_TRAZEM_DADOS = {'buscar_ajuda', 'abrir_tela', 'anotar_preferencia', 'anotar_aprendizado', 'anotar_regra_geral',
                    'ajustar_perfil_treinador', 'ilustrar'}
_MARCAS_COPIADAS = re.compile(r'\s*\[(?:ilustra[cç][aã]o|cart[aã]o mostrado|arquivo anexado)[^\]]*\]', re.I)
_PROMETE_CARTAO = re.compile(r'(gr[aá]fico|planilha|tabela|cart[aã]o|ilustra[cç][aã]o)[^.\n]{0,70}\b(acima|em cima|abaixo)\b|'
                             r'\b(acima|em cima|abaixo)\b[^.\n]{0,40}(gr[aá]fico|planilha|tabela)', re.I)
_PERGUNTA_DE_DADOS = re.compile(
    r'\b(agenda\w*|paciente\w*|atendiment\w*|conta\w*|vencim\w*|vence\w*|pagar|receber|caixa|faturament\w*|quant[oa]s?|'
    r'grafico\w*|projec\w*|projet\w*|indicador\w*|ona|relatorio\w*|planilha\w*|falt\w*|veio|vieram|resgat\w*|marcad\w*|'
    r'horario\w*|exames?)\b')
_PERGUNTA_COMO_FAZER = re.compile(r'^\s*(como|onde|qual tela|o que e|o que sao|para que|por que|porque|quem pode|posso|d[aá] pra)\b|\bcomo (eu )?(faco|fazer|marco|lanco|cadastro)\b')
NUDGE_SEM_CONSULTA = ('Aviso do sistema (não escreva isto na resposta): você respondeu com dados sem chamar nenhuma ferramenta '
                      'que os traga. Dados de mensagens anteriores não valem. Chame agora a ferramenta certa e responda só com o que '
                      'ela devolver. Se não existir ferramenta para esse assunto, diga com franqueza que não consegue consultar isso e '
                      'ofereça abrir a tela (abrir_tela).')
SEM_CONSULTA = ('Não consegui consultar isso no sistema agora, e não vou arriscar números de cabeça. '
                'Me diga a data ou o paciente com mais detalhe, ou peça para eu abrir a tela certa.')


def _ultima_pergunta(conversa):
    for m in reversed(conversa):
        if m.get('role') == 'user' and isinstance(m.get('content'), str):
            return m['content']
    return ''


def respondeu_sem_consultar(pergunta, texto, chamadas, cartoes):
    """True quando a resposta traz dados mas nenhuma ferramenta de dados foi chamada nesta resposta (invenção provável).

    Vale para: números/ilustração falsa em pergunta sobre agenda, contas, atendimentos etc.; marcas copiadas do histórico
    ("[ilustração #2 ...]") ou promessa de gráfico/tabela "acima" sem cartão gerado; e `ilustrar` com dados que ninguém consultou."""
    nomes = [c['nome'] for c in chamadas]
    if any(n not in NAO_TRAZEM_DADOS for n in nomes):
        return False   # consultou o sistema nesta resposta
    if _MARCAS_COPIADAS.search(texto or '') or _PROMETE_CARTAO.search(texto or ''):
        return not cartoes
    q = normalizar(pergunta)
    if not _PERGUNTA_DE_DADOS.search(q) or _PERGUNTA_COMO_FAZER.search(q):
        return False   # conversa, saudação ou "como faço": responder sem ferramenta de dados é normal
    return bool(re.search(r'\d', texto or '')) or 'ilustrar' in nomes


def _juntar(historico):
    """Compacta mensagens de texto consecutivas do mesmo papel."""
    saida = []
    for h in historico:
        if saida and saida[-1]['role'] == h['role']:
            saida[-1]['content'] += '\n' + h['content']
        else:
            saida.append(dict(h))
    while saida and saida[0]['role'] != 'user':
        saida.pop(0)
    return saida


# ------------------------------------------------------------------ núcleo
def _conversar(ctx, historico):
    """Roda o modelo com as ferramentas. Devolve {'texto', 'cartoes', 'pendente', 'chamadas', 'tokens', 'confianca'}.
    Levanta llm.ErroLLM em falha de rede, cota, serviço ou resposta."""
    db = ctx.db
    db.commit()   # nada de transação aberta enquanto se espera o OpenRouter
    sistema = conh.instrucao_sistema(ctx)
    decl = ferr.declaracoes(ctx)
    conversa = _juntar(historico)
    cartoes, chamadas, pendente, tokens = [], [], None, 0
    tokens_entrada, tokens_saida, tokens_total = 0, 0, 0
    texto, modelo_usado = '', None
    pergunta = _ultima_pergunta(conversa)
    corrigida = False      # a IA só é corrigida uma vez por pergunta (cada tentativa gasta o limite da OpenRouter)
    t0 = time.perf_counter()
    if not _vagas.acquire(timeout=ESPERA_VAGA_S):
        return {'texto': OCUPADA, 'cartoes': [], 'pendente': None, 'chamadas': [], 'tokens': 0,
                'tokens_entrada': 0, 'tokens_saida': 0, 'tokens_total': 0, 'modelo': '', 'tempo_ms': 0,
                'confianca': None, 'ocupada': True}
    try:
        for _ in range(MAX_PASSOS):
            r = ia.gerar_com_troca(db, sistema, conversa, decl or None, baixar=BAIXAR, modelo_inicial=modelo_usado)
            modelo_usado = r.get('modelo_configurado') or r.get('modelo')
            tokens += r.get('tokens', 0)
            tokens_entrada += r.get('tokens_entrada', 0)
            tokens_saida += r.get('tokens_saida', 0)
            tokens_total += r.get('tokens_total', r.get('tokens', 0))
            texto = r['texto']
            if not r['chamadas']:
                if respondeu_sem_consultar(pergunta, conh.separar_confianca(texto)[0], chamadas, cartoes):
                    if not corrigida:
                        # respondeu com dados sem consultar o sistema: devolve a resposta e pede para consultar de verdade
                        corrigida = True
                        conversa.append({'role': 'assistant', 'content': texto or '(sem texto)'})
                        conversa.append({'role': 'user', 'content': NUDGE_SEM_CONSULTA})
                        continue
                    texto, cartoes = SEM_CONSULTA, []   # insistiu: melhor admitir do que inventar
                break
            conversa.append(r['mensagem'])
            for c in r['chamadas']:
                res = ferr.chamar(ctx, c['nome'], c['args'])
                chamadas.append({'nome': c['nome'], 'args': c['args'], 'recusado': bool(res.get('recusado'))})
                if res.get('cartao'):
                    cartoes.append(res['cartao'])
                if res.get('pendente'):
                    pendente = res['pendente']
                conversa.append({'role': 'tool', 'tool_call_id': c['id'],
                                 'content': json.dumps({'resultado': res.get('resumo', '')}, ensure_ascii=False)})
            db.commit()   # anotações de memória feitas pelas ferramentas
        else:
            texto = texto or 'Desculpe, me enrolei nessa. Pode repetir de outro jeito?'
            if respondeu_sem_consultar(pergunta, conh.separar_confianca(texto)[0], chamadas, cartoes):
                texto, cartoes = SEM_CONSULTA, []
    finally:
        _vagas.release()
    tempo_ms = int((time.perf_counter() - t0) * 1000)
    texto, confianca = conh.separar_confianca(texto)
    texto = _MARCAS_COPIADAS.sub('', texto).strip()   # as marcas do histórico são do sistema: o modelo nunca as escreve
    if not texto:
        texto = 'Pronto.' if cartoes else 'Não consegui formular uma resposta. Pode perguntar de outro jeito?'
    return {
        'texto': texto,
        'cartoes': cartoes[-3:],
        'pendente': pendente,
        'chamadas': chamadas,
        'tokens': tokens_total or tokens,
        'tokens_entrada': tokens_entrada,
        'tokens_saida': tokens_saida,
        'tokens_total': tokens_total or tokens,
        'modelo': modelo_usado or '',
        'tempo_ms': tempo_ms,
        'confianca': confianca
    }


def _registrar(ctx, pergunta, r, modo='IA'):
    db = ctx.db
    lid = ia.registrar_log(db, ctx.uid, ctx.usuario, pergunta, r.get('texto'), r.get('chamadas') or None, r.get('tokens', 0),
                           modo=modo, treinador=ctx.treinador if ctx.treino else None)
    if r.get('confianca'):
        db.execute('UPDATE nucleai_llm_log SET autoavaliacao=? WHERE id=?', (str(r['confianca']), lid))
    if modo == 'IA':
        ia.registrar_uso(db, ctx.uid, r.get('tokens', 0))
        from . import nucleai_tokens
        nucleai_tokens.registrar(
            db,
            usuario=ctx.usuario,
            modelo=r.get('modelo') or ia.modelo(db) or 'desconhecido',
            tokens_entrada=r.get('tokens_entrada', 0),
            tokens_saida=r.get('tokens_saida', 0),
            tokens_total=r.get('tokens_total', r.get('tokens', 0)),
            tempo_ms=r.get('tempo_ms', 0),
            teste=bool(ctx.treino),
            usuario_id=ctx.uid
        )
        try:
            db.execute('UPDATE nucleai_llm_log SET modelo=?, tokens_entrada=?, tokens_saida=?, tempo_ms=?, teste=? WHERE id=?',
                       (r.get('modelo') or ia.modelo(db) or '', r.get('tokens_entrada', 0), r.get('tokens_saida', 0),
                        r.get('tempo_ms', 0), 1 if ctx.treino else 0, lid))
        except Exception:
            pass
    return lid


def _tratar_pendente(ctx, chave, texto):
    """Se havia uma ação esperando o Sim/Não: confirma, cancela ou descarta. Devolve a resposta pronta ou None."""
    escolha = sim_ou_nao(texto)
    if escolha is not None:
        ilustrar_mod.responder_decisao(ctx.db, ctx.uid, ctx.treino, escolha)
    sess = ia.sessao(ctx.db, chave)
    pend = sess['pendente']
    if not pend:
        return None
    ia.salvar_sessao(ctx.db, chave, pendente=None)
    if escolha is True:
        r = ferr.confirmar(ctx, pend)
        saida = {'texto': r['texto'], 'cartoes': [r['cartao']] if r.get('cartao') else [], 'chamadas': [{'nome': pend['ferramenta'], 'confirmado': True}],
                 'tokens': 0, 'confianca': None}
        _registrar(ctx, texto, saida, modo='ACAO')
        return saida
    if escolha is False:
        saida = {'texto': 'Tudo bem, cancelei. Nada foi alterado.', 'cartoes': [], 'chamadas': [], 'tokens': 0, 'confianca': None}
        _registrar(ctx, texto, saida, modo='ACAO')
        return saida
    return None   # mudou de assunto: a proposta é descartada e a conversa segue


# ------------------------------------------------------------------ chat do time
def saudacao(db, uid, nome):
    if not ia.pode_usar_ia(db, uid):
        return None
    ia.salvar_sessao(db, uid, modo='IA', pendente=None)
    n = ia.nivel(db, uid)
    return ('Oi, %s! Sou a NucleAI, agora com inteligência artificial. 💚 Pode me perguntar com as suas palavras. '
            'No seu nível (%s) eu posso %s.' % (nome, ferr.NOMES_NIVEL.get(n, '?'), ferr.DESCRICAO_NIVEL.get(n, 'ajudar com dúvidas')))


def _gravar_time(db, uid, texto, cartoes):
    from . import ajuda
    msgs = []
    if texto:
        msgs.append(ajuda._bot_diz(db, uid, texto))
    for c in cartoes:
        cur = db.execute('INSERT INTO chat_mensagens (de_id, para_id, corpo, criado_em, cartao) VALUES (?,?,?,?,?)',
                         (ajuda.bot_id(db), uid, str(c.get('titulo') or 'Resultado')[:300], agora(), json.dumps(c, ensure_ascii=False)))
        msgs.append(dict(db.execute('SELECT * FROM chat_mensagens WHERE id=?', (cur.lastrowid,)).fetchone()))
    return msgs


def talvez_responder(db, uid, texto):
    """Resposta da IA para o chat do time, ou None (segue a resposta automática), ou {'seguir_regras': True, ...}
    (avisa a queda e deixa a resposta automática responder em seguida)."""
    if not ia.pode_usar_ia(db, uid):
        return None
    from . import ajuda
    ctx = ferr.contexto(db, uid)
    sess = ia.sessao(db, uid)
    voltou = False
    if sess['modo'] == 'REGRAS':
        if not llm.conectado(baixar=BAIXAR_CONEXAO):
            ia.registrar_log(db, uid, ctx.usuario, texto, None, modo='REGRAS')
            return None
        voltou = True
        ia.salvar_sessao(db, uid, modo='IA')
    pronta = _tratar_pendente(ctx, uid, texto)
    if pronta is not None:
        return {'mensagens': _gravar_time(db, uid, pronta['texto'], pronta['cartoes']), 'encerrado': False}
    ok, motivo = ia.dentro_do_limite(db, uid)
    if not ok:
        return {'mensagens': [ajuda._bot_diz(db, uid, motivo + ' Enquanto isso, sigo com as respostas automáticas.')],
                'encerrado': False, 'seguir_regras': True}
    try:
        r = _conversar(ctx, _historico_time(db, uid))
    except llm.ErroLLM as e:
        ia.salvar_sessao(db, uid, modo='REGRAS', pendente=None)
        ia.registrar_log(db, uid, ctx.usuario, texto, 'Queda: %s%s' % (e.tipo, _detalhe_queda(e)), modo='REGRAS')
        return {'mensagens': [ajuda._bot_diz(db, uid, aviso_queda(e))],
                'encerrado': False, 'seguir_regras': True}
    if r.get('ocupada'):
        return {'mensagens': [ajuda._bot_diz(db, uid, r['texto'])], 'encerrado': False}
    if r['pendente']:
        ia.salvar_sessao(db, uid, pendente=r['pendente'])
    _registrar(ctx, texto, r)
    msgs = _gravar_time(db, uid, AVISO_VOLTEI, []) if voltou else []
    msgs += _gravar_time(db, uid, r['texto'], r['cartoes'])
    return {'mensagens': msgs, 'encerrado': False}


# ------------------------------------------------------------------ Fake Chat / chat de teste
COMANDOS_TREINO = ('/chanceperfil', '/changeperfil', '/trocarperfil', '/configperfil', '/limpar', '/novo', '/novoteste', '/ajuda')
AJUDA_TREINO = ('Comandos do Fake Chat (chat de teste):\n'
                '/novoteste: inicia uma nova conversa de teste (com um novo identificador Teste#XXXX).\n'
                '/limpar: apaga o histórico desta conversa de teste (o contexto some; o aprendizado no manual continua).\n'
                '/chanceperfil [Teste#XXXX]: troca para outra conversa de teste ou perfil existente.\n'
                '/configperfil: mostra o perfil de teste atual.\n'
                '/configperfil campo valor: muda o perfil (campos: tratamento, tom, formalidade, tamanho, forca; números de 1 a 5).\n'
                '/ajuda: exibe estes comandos.')


def _gravar_treino(db, uid, treinador, papel, texto, cartao=None):
    cur = db.execute('INSERT INTO nucleai_treino_msgs (criado_em, usuario_id, treinador, papel, texto, cartao) VALUES (?,?,?,?,?,?)',
                     (agora(), uid, treinador, papel, texto or '', json.dumps(cartao, ensure_ascii=False) if cartao else None))
    return {'id': cur.lastrowid, 'papel': papel, 'texto': texto or '', 'cartao': cartao, 'treinador': treinador, 'hora': agora()[11:16]}


def apagar_conversa_treino(db, uid, treinador=None):
    """Apaga as mensagens do chat de teste. Se treinador for informado, apaga só dessa conversa."""
    if treinador:
        db.execute(
            'DELETE FROM nucleai_treino_msgs WHERE usuario_id=? AND (treinador=? OR (?=? AND treinador IS NULL))',
            (uid, treinador, treinador, ia.TREINADOR_PADRAO)
        )
    else:
        db.execute('DELETE FROM nucleai_treino_msgs WHERE usuario_id=?', (uid,))
    ia.salvar_sessao(db, -uid, pendente=None)
    db.commit()


def conversa_treino(db, uid, limite=80, treinador=None):
    if treinador is None:
        t = ia.treinador_atual(db, uid)
        treinador = t['nome'] if t else None
    if treinador:
        linhas = db.execute(
            'SELECT * FROM nucleai_treino_msgs '
            'WHERE usuario_id=? AND (treinador=? OR (?=? AND treinador IS NULL)) '
            'ORDER BY id DESC LIMIT ?',
            (uid, treinador, treinador, ia.TREINADOR_PADRAO, limite)
        ).fetchall()
    else:
        linhas = db.execute('SELECT * FROM nucleai_treino_msgs WHERE usuario_id=? ORDER BY id DESC LIMIT ?', (uid, limite)).fetchall()
    saida = []
    for r in reversed(linhas):
        try:
            c = json.loads(r['cartao']) if r['cartao'] else None
        except ValueError:
            c = None
        if c:
            c = ilustrar_mod.enriquecer_cartao(db, c)
        saida.append({'id': r['id'], 'papel': r['papel'], 'texto': r['texto'], 'cartao': c, 'treinador': r['treinador'],
                      'hora': (r['criado_em'] or '')[11:16]})
    return saida


def _comando_treino(db, uid, ctx, texto):
    partes = texto.strip().split(None, 1)
    cmd = partes[0].lower()
    resto = partes[1].strip() if len(partes) > 1 else ''
    if cmd in ('/novo', '/novoteste'):
        novo_nome = ia.iniciar_conversa_teste(db, uid)
        return [_gravar_treino(db, uid, novo_nome, 'sistema',
                               f'Nova conversa de teste iniciada. A IA agora vê você como {novo_nome}. '
                               'O histórico da conversa anterior não é enviado; o aprendizado no manual continua valendo.')]
    if cmd in ('/chanceperfil', '/changeperfil', '/trocarperfil'):
        nome = resto.strip('[] ')
        if not nome:
            return [_gravar_treino(db, uid, ctx.treinador, 'sistema', 'Use: /chanceperfil [Nome#0001]')]
        try:
            t = ia.trocar_treinador(db, uid, nome)
        except ValueError as e:
            return [_gravar_treino(db, uid, ctx.treinador, 'sistema', str(e))]
        return [_gravar_treino(db, uid, t['nome'], 'sistema', 'Agora o perfil de teste é %s. A IA vai tratá-lo pelas preferências desse perfil.' % t['nome'],
                               ferr.cartao_perfil(t))]
    if cmd == '/configperfil':
        if not resto:
            return [_gravar_treino(db, uid, ctx.treinador, 'sistema', 'Perfil de teste atual:', ferr.cartao_perfil(ia.treinador(db, ctx.treinador)))]
        m = re.fullmatch(r'(\w+)\s+(.+)', resto)
        campo = normalizar(m[1]) if m else ''
        if not m or campo not in ferr.CAMPOS_PERFIL:
            return [_gravar_treino(db, uid, ctx.treinador, 'sistema', 'Use: /configperfil campo valor. Campos: ' + ', '.join(ferr.CAMPOS_PERFIL))]
        valor = m[2].strip()
        if campo in ('formalidade', 'tamanho', 'forca'):
            if not valor.isdigit() or not 1 <= int(valor) <= 5:
                return [_gravar_treino(db, uid, ctx.treinador, 'sistema', 'Use um número de 1 a 5.')]
            valor = int(valor)
        t = ferr.alterar_perfil(ctx, campo, valor)
        return [_gravar_treino(db, uid, ctx.treinador, 'sistema', 'Perfil atualizado (fica no registro de atividades, com Desfazer).',
                               ferr.cartao_perfil(t))]
    if cmd == '/limpar':
        apagar_conversa_treino(db, uid, ctx.treinador)
        return [_gravar_treino(db, uid, ctx.treinador, 'sistema',
                               f'Conversa de teste ({ctx.treinador}) apagada. O contexto foi limpo; o aprendizado anotado no manual continua guardado.')]
    return [_gravar_treino(db, uid, ctx.treinador, 'sistema', AJUDA_TREINO)]


def responder_treino(db, uid, texto):
    """Mensagem no Fake Chat (chat de teste). Devolve a lista de mensagens novas."""
    texto = str(texto or '').strip()[:2000]
    if not texto:
        raise ValueError('Escreva uma mensagem.')
    if not ia.pode_usar_ia(db, uid, treino=True):
        raise ValueError('A IA está desligada. Ligue em "IA ligada" na aba IA online (e confira a chave).')
    t = ia.treinador_atual(db, uid)
    ctx = ferr.contexto(db, uid, treino=True, treinador=t['nome'])
    novas = [_gravar_treino(db, uid, t['nome'], 'treinador', texto)]
    if texto.startswith('/') and texto.split()[0].lower() in COMANDOS_TREINO:
        novas += _comando_treino(db, uid, ctx, texto)
        db.commit()
        return novas
    pronta = _tratar_pendente(ctx, -uid, texto)
    if pronta is not None:
        novas.append(_gravar_treino(db, uid, t['nome'], 'ia', pronta['texto'], pronta['cartoes'][0] if pronta['cartoes'] else None))
        db.commit()
        return novas
    try:
        r = _conversar(ctx, _historico_treino(db, uid, treinador=t['nome']))
    except llm.ErroLLM as e:
        ia.registrar_log(db, uid, ctx.usuario, texto, 'Erro: %s%s' % (e.tipo, _detalhe_queda(e)), modo='REGRAS', treinador=t['nome'])
        # No Fake Chat (só a gerência) mostra também o motivo exato dado pela OpenRouter
        novas.append(_gravar_treino(db, uid, t['nome'], 'sistema', '%s (%s%s)' % (aviso_queda(e), e, ' | OpenRouter: %s' % e.detalhe if getattr(e, 'detalhe', '') else '')))
        db.commit()
        return novas
    if r['pendente']:
        ia.salvar_sessao(db, -uid, pendente=r['pendente'])
    _registrar(ctx, texto, r)
    cartoes = r['cartoes']
    novas.append(_gravar_treino(db, uid, t['nome'], 'ia', r['texto'], cartoes[0] if cartoes else None))
    for c in cartoes[1:]:
        novas.append(_gravar_treino(db, uid, t['nome'], 'ia', '', c))
    if r.get('confianca'):
        novas[-1]['confianca'] = r['confianca']
    db.commit()
    return novas
