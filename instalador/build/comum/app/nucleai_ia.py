"""NucleAI IA (OpenRouter): estado, níveis, limites, registro de uso e treinadores.

Só lógica, sem rotas. A configuração fica na tabela `config` (chave/valor), como em `ajuda.py`.
Estados: TREINO (só a gerência testa), LIBERADA (todos com nível >= 1) e DESATIVADA (desligada).
"""
from __future__ import annotations

import json
import re
import secrets
from datetime import date, datetime, timedelta, timezone

from .db import agora

FMT = '%Y-%m-%d %H:%M:%S'
TREINO, LIBERADA, DESATIVADA = 'TREINO', 'LIBERADA', 'DESATIVADA'
ESTADOS = (TREINO, LIBERADA, DESATIVADA)
NIVEL_MAX = 4
CODIGO_VALIDADE_MIN = 10
NOME_TREINADOR = re.compile(r'[A-Za-zÀ-ÿ0-9_ ]{1,30}#\d{4}')

# ------------------------------------------------------------------ configuração (tabela config)
PADROES = {
    'nucleai_llm_estado': TREINO,
    'nucleai_llm_ativo': '0',
    'nucleai_llm_modelo': 'google/gemini-2.5-flash',  # legado, migrado na primeira leitura
    'nucleai_llm_modelos': '[]',
    'nucleai_llm_pausas': '{}',
    'nucleai_llm_falhas': '{}',        # falhas seguidas por modelo (a pausa cresce a cada falha; zera quando responde)
    'nucleai_llm_ultimo_erro': '',     # JSON: o último motivo de cota/indisponibilidade dado pela OpenRouter
    'nucleai_llm_pausa_min': '15',
    'nucleai_llm_timeout_s': '12',
    'nucleai_llm_desde': '',
    'nucleai_llm_limite_dia_n1': '30',
    'nucleai_llm_limite_dia_n2': '60',
    'nucleai_llm_limite_dia_n3': '120',
    'nucleai_llm_limite_dia_n4': '300',
    'nucleai_llm_limite_min': '6',
    'nucleai_llm_padrao_nivel': '0',
    'nucleai_llm_codigo': '',
    'nucleai_llm_codigo_em': '',
    'nucleai_llm_dados_pacientes': '1',   # a gerência pode desligar o envio dos nomes reais à IA
    'nucleai_llm_tolerancia_remarcacao': '60',
    'nucleai_llm_treino_real': '0',       # '1': no Fake Chat, as alterações são feitas de verdade (senão só simuladas)
}
TREINADOR_PADRAO = 'Treinador#0001'
TESTE_PADRAO = 'Teste#0001'


def cfg(db, chave):
    r = db.execute('SELECT valor FROM config WHERE chave=?', (chave,)).fetchone()
    return r['valor'] if r and r['valor'] is not None else PADROES[chave]


def cfg_int(db, chave, minimo, maximo):
    try:
        v = int(cfg(db, chave))
    except (TypeError, ValueError):
        v = int(PADROES[chave])
    return max(minimo, min(maximo, v))


def definir(db, chave, valor):
    db.execute('INSERT INTO config (chave, valor) VALUES (?,?) ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor',
               (chave, str(valor)))


# ------------------------------------------------------------------ estado e liberação
def estado(db):
    e = cfg(db, 'nucleai_llm_estado')
    return e if e in ESTADOS else TREINO


def definir_estado(db, novo):
    if novo not in ESTADOS:
        raise ValueError(f'Estado inválido da NucleAI IA: {novo}.')
    atual = estado(db)
    if novo == LIBERADA and atual != LIBERADA:
        definir(db, 'nucleai_llm_desde', agora())
    elif novo != LIBERADA and atual == LIBERADA:
        definir(db, 'nucleai_llm_desde', '')
    definir(db, 'nucleai_llm_estado', novo)


def ia_ligada(db):
    return cfg(db, 'nucleai_llm_ativo') == '1' and estado(db) != DESATIVADA


def liberada_para_time(db):
    return estado(db) == LIBERADA


# ------------------------------------------------------------------ níveis
def nivel(db, uid):
    r = db.execute('SELECT nivel FROM nucleai_llm_nivel WHERE usuario_id=?', (uid,)).fetchone()
    if r is not None:
        return int(r['nivel'])
    return cfg_int(db, 'nucleai_llm_padrao_nivel', 0, NIVEL_MAX)


def definir_nivel(db, uid, nivel_novo, por):
    if not isinstance(nivel_novo, int) or isinstance(nivel_novo, bool) or not 0 <= nivel_novo <= NIVEL_MAX:
        raise ValueError(f'O nível da NucleAI IA deve estar entre 0 e {NIVEL_MAX}.')
    db.execute('INSERT INTO nucleai_llm_nivel (usuario_id, nivel, atualizado_em, atualizado_por) VALUES (?,?,?,?) '
               'ON CONFLICT(usuario_id) DO UPDATE SET nivel=excluded.nivel, atualizado_em=excluded.atualizado_em, '
               'atualizado_por=excluded.atualizado_por', (uid, nivel_novo, agora(), por))


def pode_usar_ia(db, uid, treino=False):
    """Em treino só passa quem chama com treino=True (chat Treinador; a gerência já é garantida por quem chama).
    Fora do treino exige estado LIBERADA e nível >= 1."""
    if not ia_ligada(db):
        return False
    if treino:
        return True
    return liberada_para_time(db) and nivel(db, uid) >= 1


# ------------------------------------------------------------------ limites e uso
def limite_dia(db, nivel_usuario):
    if nivel_usuario < 1:
        return 0
    n = min(nivel_usuario, NIVEL_MAX)
    return cfg_int(db, f'nucleai_llm_limite_dia_n{n}', 0, 100000)


def usos_hoje(db, uid):
    r = db.execute('SELECT qtd FROM nucleai_llm_uso WHERE usuario_id=? AND dia=?',
                   (uid, date.today().isoformat())).fetchone()
    return int(r['qtd']) if r else 0


def registrar_uso(db, uid, tokens):
    db.execute('INSERT INTO nucleai_llm_uso (usuario_id, dia, qtd, tokens) VALUES (?,?,1,?) '
               'ON CONFLICT(usuario_id, dia) DO UPDATE SET qtd = qtd + 1, '
               'tokens = nucleai_llm_uso.tokens + excluded.tokens',
               (uid, date.today().isoformat(), int(tokens or 0)))


def dentro_do_limite(db, uid):
    """Devolve (True, '') ou (False, motivo). Confere o limite diário pelo nível e o limite por minuto."""
    n = nivel(db, uid)
    if n < 1:
        return False, 'Você ainda não tem acesso à NucleAI IA.'
    if usos_hoje(db, uid) >= limite_dia(db, n):
        return False, 'Você atingiu o limite diário de perguntas da NucleAI IA. Tente de novo amanhã.'
    minuto = (datetime.now() - timedelta(minutes=1)).strftime(FMT)
    r = db.execute("SELECT COUNT(*) FROM nucleai_llm_log WHERE usuario_id=? AND modo<>'EVENTO' AND criado_em>=?",
                   (uid, minuto)).fetchone()
    if r[0] >= cfg_int(db, 'nucleai_llm_limite_min', 1, 60):
        return False, 'Muitas perguntas em pouco tempo. Espere um minuto e tente de novo.'
    return True, ''


# ------------------------------------------------------------------ registro
def registrar_log(db, uid, usuario, pergunta, resposta, ferramentas=None, tokens=0, modo='IA', treinador=None):
    if ferramentas is not None and not isinstance(ferramentas, str):
        ferramentas = json.dumps(ferramentas, ensure_ascii=False)
    cur = db.execute('INSERT INTO nucleai_llm_log (criado_em, usuario_id, usuario, treinador, pergunta, resposta, '
                     'ferramentas, tokens, modo) VALUES (?,?,?,?,?,?,?,?,?)',
                     (agora(), uid, usuario, treinador, pergunta, resposta, ferramentas, int(tokens or 0), modo))
    return cur.lastrowid


def contadores(db):
    respostas = db.execute("SELECT COUNT(*) FROM nucleai_llm_log WHERE modo='IA'").fetchone()[0]
    desde = cfg(db, 'nucleai_llm_desde') or ''
    tempo = 0
    if desde:
        try:
            tempo = max(0, int((datetime.now() - datetime.strptime(desde, FMT)).total_seconds()))
        except ValueError:
            tempo = 0
    return {'respostas': respostas, 'desde': desde, 'tempo_ativa_s': tempo}


# ------------------------------------------------------------------ liberação com código
def gerar_codigo_liberacao(db):
    codigo = f'{secrets.randbelow(1000000):06d}'
    definir(db, 'nucleai_llm_codigo', codigo)
    definir(db, 'nucleai_llm_codigo_em', agora())
    return codigo


def _apagar_codigo(db):
    definir(db, 'nucleai_llm_codigo', '')
    definir(db, 'nucleai_llm_codigo_em', '')


def liberar(db, codigo, por):
    """Libera a IA para o time se o código bater e não tiver expirado. O código é apagado ao ser usado."""
    guardado = cfg(db, 'nucleai_llm_codigo')
    em = cfg(db, 'nucleai_llm_codigo_em')
    if not guardado or not em:
        return False
    try:
        gerado = datetime.strptime(em, FMT)
    except ValueError:
        _apagar_codigo(db)
        return False
    if datetime.now() - gerado > timedelta(minutes=CODIGO_VALIDADE_MIN):
        _apagar_codigo(db)
        return False
    if not secrets.compare_digest(guardado, str(codigo or '').strip()):
        return False
    _apagar_codigo(db)
    definir_estado(db, LIBERADA)
    definir(db, 'nucleai_llm_ativo', '1')
    registrar_log(db, None, por, 'IA liberada para o time', None, modo='EVENTO')
    return True


def desativar(db, por):
    definir_estado(db, DESATIVADA)
    definir(db, 'nucleai_llm_ativo', '0')
    registrar_log(db, None, por, 'IA desativada', None, modo='EVENTO')


# ------------------------------------------------------------------ treinadores
def _validar_nome(nome):
    nome = (nome or '').strip()
    if not NOME_TREINADOR.fullmatch(nome):
        raise ValueError('Nome de treinador/teste inválido. Use o formato Nome#0001: letras, números, _ ou espaço, '
                         'até 30 caracteres antes do # e 4 dígitos depois.')
    return nome


def novo_nome_teste():
    """Gera um identificador de conversa de teste no formato Teste#XXXX (4 dígitos aleatórios)."""
    return f'Teste#{secrets.randbelow(10000):04d}'


def iniciar_conversa_teste(db, uid, nome=None):
    """Inicia ou alterna para uma conversa de teste. Se nome for None, gera um novo Teste#XXXX."""
    nome = _validar_nome(nome) if nome else novo_nome_teste()
    t = treinador(db, nome)
    definir(db, 'nucleai_llm_treinador_%d' % uid, t['nome'])
    salvar_sessao(db, -uid, pendente=None)
    return t['nome']


def treinador(db, nome):
    """Devolve o treinador com este nome, criando-o com os padrões se não existir."""
    nome = _validar_nome(nome)
    r = db.execute('SELECT * FROM nucleai_treinadores WHERE nome=?', (nome,)).fetchone()
    if r is None:
        agora_s = agora()
        db.execute('INSERT INTO nucleai_treinadores (nome, criado_em, atualizado_em) VALUES (?,?,?)',
                   (nome, agora_s, agora_s))
        r = db.execute('SELECT * FROM nucleai_treinadores WHERE nome=?', (nome,)).fetchone()
    return dict(r)


def _limite(valor):
    return max(1, min(5, int(valor)))


def config_treinador(db, nome, **campos):
    """Atualiza tratamento, tom, formalidade, tamanho e forca (níveis 1 a 5). Outras chaves são ignoradas."""
    atual = treinador(db, nome)
    novos = {}
    for chave in ('tratamento', 'tom'):
        if chave in campos:
            novos[chave] = (campos[chave] or '').strip() or None
    for chave in ('formalidade', 'tamanho', 'forca'):
        if chave in campos and campos[chave] is not None:
            novos[chave] = _limite(campos[chave])
    if not novos:
        return atual
    novos['atualizado_em'] = agora()
    sets = ', '.join(f'{c}=?' for c in novos)
    db.execute(f'UPDATE nucleai_treinadores SET {sets} WHERE nome=?', (*novos.values(), atual['nome']))
    return treinador(db, atual['nome'])


def listar_treinadores(db):
    return [dict(r) for r in db.execute('SELECT * FROM nucleai_treinadores ORDER BY nome').fetchall()]


def treinador_atual(db, uid):
    """Treinador/perfil em uso no Fake Chat desta pessoa da gerência (criado com Teste#XXXX na primeira vez)."""
    r = db.execute('SELECT valor FROM config WHERE chave=?', ('nucleai_llm_treinador_%d' % uid,)).fetchone()
    nome = r['valor'] if r and r['valor'] else None
    if not nome:
        nome = novo_nome_teste()
        definir(db, 'nucleai_llm_treinador_%d' % uid, nome)
    try:
        return treinador(db, nome)
    except ValueError:
        return treinador(db, TREINADOR_PADRAO)


def trocar_treinador(db, uid, nome):
    t = treinador(db, nome)
    definir(db, 'nucleai_llm_treinador_%d' % uid, t['nome'])
    return t


def dados_pacientes(db):
    return cfg(db, 'nucleai_llm_dados_pacientes') == '1'


def treino_real(db):
    return cfg(db, 'nucleai_llm_treino_real') == '1'


def modelo(db):
    return next((m['slug'] for m in modelos(db) if m['ativo']), '')


def validar_slug(slug):
    if not isinstance(slug, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.:/-]+', slug) or len(slug) > 200:
        raise ValueError('Informe o slug do OpenRouter no formato provedor/modelo.')
    return slug


def salvar_modelos(db, lista):
    vistos, novos = set(), []
    for m in lista:
        slug = validar_slug(m['slug'])
        if slug in vistos:
            raise ValueError('Este modelo já está na lista.')
        vistos.add(slug)
        novos.append({'slug': slug, 'ativo': bool(m['ativo'])})
    definir(db, 'nucleai_llm_modelos', json.dumps(novos, ensure_ascii=False))


def modelos(db):
    """Lista ordenada. Migra uma única vez; lista vazia não ressuscita o legado."""
    r = db.execute("SELECT valor FROM config WHERE chave='nucleai_llm_modelos'").fetchone()
    if r is None:
        antigo = (cfg(db, 'nucleai_llm_modelo') or '').strip() or PADROES['nucleai_llm_modelo']
        # Os nomes do Gemini antigo não tinham o prefixo de provedor.
        if '/' not in antigo:
            antigo = 'google/' + antigo
        salvar_modelos(db, [{'slug': antigo, 'ativo': True}])
        return [{'slug': antigo, 'ativo': True}]
    try:
        lista = json.loads(r['valor'])
        if not isinstance(lista, list):
            raise ValueError
        return [{'slug': validar_slug(m['slug']), 'ativo': m['ativo'] is True} for m in lista]
    except (ValueError, KeyError, TypeError):
        return []


def pausas(db):
    try:
        valores = json.loads(cfg(db, 'nucleai_llm_pausas'))
        return {slug: ate for slug, ate in valores.items()
                if isinstance(ate, str) and ate > agora()}
    except (ValueError, TypeError, AttributeError):
        return {}


def _json_dict(db, chave):
    try:
        v = json.loads(cfg(db, chave))
        return v if isinstance(v, dict) else {}
    except (ValueError, TypeError):
        return {}


def _segundos_ate_meia_noite_utc():
    """A OpenRouter renova o limite diário dos modelos :free à meia-noite UTC."""
    agora_utc = datetime.now(timezone.utc)
    proxima = (agora_utc + timedelta(days=1)).replace(hour=0, minute=0, second=5, microsecond=0)
    return int((proxima - agora_utc).total_seconds())


def _segundos_de_pausa(db, slug, e):
    """Quanto tempo deixar o modelo de lado depois de uma falha de cota (ou de indisponibilidade).

    - limite diário da conta: até a renovação (dica da OpenRouter ou meia-noite UTC);
    - limite por minuto da conta: a dica da OpenRouter ou 1 minuto;
    - saldo (402): o teto configurado (esperar não traz saldo, mas evita martelar);
    - só aquele modelo/provedor: começa em 1 minuto e dobra a cada falha seguida, até o teto configurado
      ("Pausa por cota (min)"), em vez de travar tudo por 15 minutos por causa de um 429 passageiro."""
    teto = cfg_int(db, 'nucleai_llm_pausa_min', 1, 1440) * 60
    escopo = getattr(e, 'escopo', '')
    if escopo == 'conta_dia':
        return max(60, min(e.pausa_s or _segundos_ate_meia_noite_utc(), 86400))
    if escopo == 'conta_min':
        return max(15, min(e.pausa_s or 60, teto))
    if escopo == 'credito' or e.tipo == 'indisponivel':
        return teto
    seguidas = _json_dict(db, 'nucleai_llm_falhas').get(slug, 1)
    return min(max(e.pausa_s or 0, 60 * 2 ** max(0, int(seguidas) - 1)), teto)


def ultimo_erro(db):
    """O último motivo de cota/indisponibilidade registrado (dict) ou None."""
    d = _json_dict(db, 'nucleai_llm_ultimo_erro')
    return d or None


def _quando_amigavel(ate):
    """'2026-11-15 21:05:17' -> 'às 21:05' (hoje) ou 'em 16/11 às 21:05' (outro dia)."""
    hora = ate[11:16]
    if ate[:10] == date.today().isoformat():
        return 'às ' + hora
    return 'em %s/%s às %s' % (ate[8:10], ate[5:7], hora)


def retorno_previsto(db, slugs=None):
    """Quando o primeiro modelo pausado volta a ser tentado ('às 21:05' / 'em 16/11 às 21:05'), ou ''."""
    p = pausas(db)
    horas = [ate for slug, ate in p.items() if slugs is None or slug in slugs]
    return _quando_amigavel(min(horas)) if horas else ''


def gerar_com_troca(db, sistema, historico, ferramentas=None, baixar=None, modelo_inicial=None):
    """Tenta modelos ativos na ordem, pulando cotas pausadas. Sem repetir ferramentas.

    modelo_inicial mantém o modelo escolhido nas rodadas da mesma pergunta.
    Apenas cota, indisponibilidade do modelo, servidor e timeout permitem troca; falhas de
    autenticação/formato e rede sem timeout retornam ao tratamento normal do motor.

    Limite da CONTA (diário/por minuto) vale para todos os modelos :free ao mesmo tempo: nesse caso a
    pergunta não percorre os outros modelos gratuitos (cada tentativa também gastaria o limite).
    """
    from . import llm, nucleai_trocas
    lista = [m['slug'] for m in modelos(db) if m['ativo']]
    if modelo_inicial in lista:
        lista = lista[lista.index(modelo_inicial):]
    pausados = pausas(db)
    candidatos = [slug for slug in lista if slug not in pausados]
    db.commit()  # não manter escrita aberta durante chamadas externas
    anterior, erro = None, None
    for slug in candidatos:
        if erro is not None and slug in pausas(db):
            continue   # pausado nesta mesma pergunta (limite da conta): não gasta mais um pedido
        if anterior:
            nucleai_trocas.registrar_troca(db, anterior, slug, erro.tipo, 'tentativa')
            db.commit()
        try:
            r = llm.gerar(slug, sistema, historico, ferramentas, baixar=baixar,
                          timeout=cfg_int(db, 'nucleai_llm_timeout_s', 1, 120), db=db)
            # O provedor pode devolver um nome canônico diferente do slug solicitado.
            r['modelo_configurado'] = slug
            falhas = _json_dict(db, 'nucleai_llm_falhas')
            if slug in falhas:   # respondeu: zera a contagem de falhas seguidas
                falhas.pop(slug)
                definir(db, 'nucleai_llm_falhas', json.dumps(falhas))
                db.commit()
            return r
        except llm.ErroLLM as e:
            if e.tipo not in ('cota', 'indisponivel', 'servidor') and not (e.tipo == 'rede' and e.tempo_esgotado):
                raise
            if e.tipo in ('cota', 'indisponivel'):
                # Releitura evita apagar pausas de outras requisições.
                if e.escopo not in ('conta_dia', 'conta_min', 'credito'):
                    falhas = _json_dict(db, 'nucleai_llm_falhas')
                    falhas[slug] = int(falhas.get(slug, 0)) + 1
                    definir(db, 'nucleai_llm_falhas', json.dumps(falhas))
                seg = _segundos_de_pausa(db, slug, e)
                ate = (datetime.now() + timedelta(seconds=seg)).strftime(FMT)
                p = pausas(db)
                p[slug] = ate
                if e.escopo in ('conta_dia', 'conta_min') and slug.endswith(':free'):
                    for outro in lista:
                        if outro.endswith(':free'):
                            p[outro] = ate   # o limite é da conta: vale para todos os modelos gratuitos
                definir(db, 'nucleai_llm_pausas', json.dumps(p))
                definir(db, 'nucleai_llm_ultimo_erro', json.dumps(
                    {'quando': agora(), 'modelo': slug, 'tipo': e.tipo, 'escopo': e.escopo, 'detalhe': e.detalhe,
                     'ate': ate}, ensure_ascii=False))
                db.commit()
                e.retorno = _quando_amigavel(ate)
            anterior, erro = slug, e
    if erro:
        erro.retorno = retorno_previsto(db, lista) or erro.retorno
        raise erro
    if lista and not candidatos:
        ult = ultimo_erro(db) or {}
        raise llm.ErroLLM('cota', 'Os modelos da IA estão em pausa por limite de uso. Tente mais tarde.',
                          escopo=ult.get('escopo', ''), detalhe=ult.get('detalhe', ''), retorno=retorno_previsto(db, lista))
    raise llm.ErroLLM('resposta', 'Nenhum modelo da IA está ativo. Confira a configuração da NucleAI.')


# ------------------------------------------------------------------ modo da conversa (IA ou regras) e ação pendente
def sessao(db, uid):
    r = db.execute('SELECT * FROM nucleai_llm_sessao WHERE usuario_id=?', (uid,)).fetchone()
    if r is None:
        return {'modo': 'IA', 'pendente': None}
    try:
        pend = json.loads(r['pendente']) if r['pendente'] else None
    except ValueError:
        pend = None
    return {'modo': r['modo'] or 'IA', 'pendente': pend}


def salvar_sessao(db, uid, modo=None, pendente=False):
    """`pendente=False` mantém o que estava; None apaga; dict grava."""
    atual = sessao(db, uid)
    novo_modo = modo or atual['modo']
    novo_pend = atual['pendente'] if pendente is False else pendente
    db.execute('INSERT INTO nucleai_llm_sessao (usuario_id, modo, pendente, atualizado_em) VALUES (?,?,?,?) '
               'ON CONFLICT(usuario_id) DO UPDATE SET modo=excluded.modo, pendente=excluded.pendente, '
               'atualizado_em=excluded.atualizado_em',
               (uid, novo_modo, json.dumps(novo_pend, ensure_ascii=False) if novo_pend else None, agora()))


def autoavaliacao(db, dias=30):
    """Média da confiança que a IA deu às próprias respostas (1 a 5) e as respostas de confiança baixa."""
    desde = (datetime.now() - timedelta(days=dias)).strftime(FMT)
    linhas = db.execute("SELECT id, criado_em, usuario, treinador, pergunta, autoavaliacao, nota FROM nucleai_llm_log "
                        "WHERE modo='IA' AND criado_em>=? ORDER BY id DESC", (desde,)).fetchall()
    notas = [int(r['autoavaliacao']) for r in linhas if str(r['autoavaliacao'] or '').isdigit()]
    baixas = [dict(r) for r in linhas if str(r['autoavaliacao'] or '').isdigit() and int(r['autoavaliacao']) <= 2][:15]
    dist = {n: notas.count(n) for n in range(1, 6)}
    return {'media': round(sum(notas) / len(notas), 2) if notas else None, 'qtd': len(notas), 'dist': dist, 'baixas': baixas}
