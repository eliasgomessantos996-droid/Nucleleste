"""Robô do PDCA: motor de regras (sem inteligência artificial externa, totalmente previsível e testável).

1. Detecta: compara cada indicador com a meta e com o período anterior de mesmo tamanho; ignora taxas com base pequena.
2. Analisa: usa o Pareto dos dados do próprio sistema para achar onde o problema se concentra (exame, convênio, dia, motivo).
3. Prioriza: calcula a matriz GUT (gravidade pelo desvio da meta e pelo risco ao paciente, urgência pela piora e pelo prazo,
   tendência pela persistência nos últimos meses).
4. Planeja: abre o problema como RASCUNHO com PDCA, Ishikawa (6M), 5 Porquês e plano 5W2H, a partir da biblioteca de causas e
   ações (qualidade_modelos.BIBLIOTECA). Cada afirmação traz a evidência em números.
5. Pergunta: quando falta dado para medir, diz o que lançar e onde.
A gerência aceita (o problema passa a ABERTO), edita ou descarta (não volta a ser sugerido por 30 dias).
"""
from __future__ import annotations

import json
from datetime import date, timedelta

from . import qualidade, qualidade_dados as qd
from .db import agora
from .qualidade_modelos import BIBLIOTECA

MIN_BASE = 20            # taxas com menos casos que isso não geram problema (ruído)
PIORA_RELATIVA = 0.20    # piora de 20% em relação ao período anterior conta como tendência ruim
DIAS_DESCARTE = 30
RASCUNHO = 'RASCUNHO'

# indicador -> (tipo de problema na biblioteca, base mínima: (tema, campo) ou None, ligado à segurança do paciente?)
REGRAS = {
    'faltas': ('faltas', ('agenda', 'base'), False),
    'comparecimento': ('faltas', ('agenda', 'base'), False),
    'resgate': ('faltas', ('agenda', 'faltas_total'), False),
    'laudo_24h': ('laudo', ('laudos', 'liberados'), True),
    'laudo_horas': ('laudo', ('laudos', 'liberados'), True),
    'laudos_pendentes': ('laudo', None, True),
    'identificacao': ('cadastro', ('cadastro', 'total'), True),
    'registro_completo': ('cadastro', ('cadastro', 'total'), False),
    'desvio_atividade': ('atividade', ('atividade', 'base'), True),
    'retrabalho': ('retrabalho', ('retrabalho', 'total'), True),
    'glosa': ('glosa', ('financeiro', 'faturas'), False),
    'recebimento_atrasado': ('glosa', ('financeiro', 'faturas'), False),
    'contas_atrasadas': ('financeiro', None, False),
    'documentos_vencidos': ('vencimentos', None, True),
    'chamados_horas': ('chamados', ('chamados', 'atendidos'), False),
    'ocorrencias_graves': ('ocorrencias', None, True),
    'satisfacao': ('satisfacao', ('ocorrencias', 'pesquisas'), False),
    'fornecedores_avaliados': ('fornecedores', ('fornecedores', 'fornecedores'), False),
}
TITULOS = {
    'faltas': 'Faltas na agenda acima da meta', 'laudo': 'Laudos fora do prazo de 24 horas', 'cadastro': 'Cadastro e identificação incompletos',
    'atividade': 'Desvio entre atividade prescrita e administrada', 'retrabalho': 'Retrabalho e repetição de exames',
    'glosa': 'Perdas no recebimento dos convênios', 'financeiro': 'Contas a pagar vencidas', 'vencimentos': 'Itens vencidos sem providência',
    'chamados': 'Demora no atendimento dos pedidos de ajuda', 'ocorrencias': 'Ocorrências graves registradas',
    'satisfacao': 'Satisfação do paciente abaixo da meta', 'fornecedores': 'Fornecedores sem avaliação em dia',
}
# Pareto usado para achar a concentração de cada tipo de problema
PARETOS = {
    'faltas': ('faltas_exame', 'faltas_convenio', 'faltas_dia_semana', 'faltas_motivo'),
    'laudo': ('laudo_atraso_exame',),
    'glosa': ('glosa_convenio',),
    'ocorrencias': ('ocorrencias_tipo', 'ocorrencias_setor'),
    'retrabalho': ('ocorrencias_tipo',),
}
NOMES = {c[0]: c[1] for c in qd.DEFINICOES}
UNIDADES = {c[0]: c[2] for c in qd.DEFINICOES}


def _fmt(v, un):
    if v is None:
        return 'sem dado'
    if un == '%':
        return ('%.1f%%' % v).replace('.', ',')
    if un == 'h':
        return ('%.1f h' % v).replace('.', ',')
    if un == 'nota':
        return ('%.1f' % v).replace('.', ',')
    return '%d' % v


def _br(iso):
    return '%s/%s/%s' % (iso[8:10], iso[5:7], iso[:4])


def _desvio(valor, meta, sentido):
    """Quanto o valor está pior que a meta (0 = na meta; 1 = 100% pior). Para metas zero, cada caso conta 0,5."""
    if valor is None:
        return 0.0
    if sentido == 'min':
        return max(0.0, (meta - valor) / meta) if meta else 0.0
    if meta == 0:
        return max(0.0, valor * 0.5)
    return max(0.0, (valor - meta) / abs(meta))


def _piorou(atual, anterior, sentido):
    if atual is None or anterior is None:
        return False, 0.0
    delta = (anterior - atual) if sentido == 'min' else (atual - anterior)
    base = abs(anterior) if anterior else 1.0
    rel = delta / base
    return delta > 0 and rel >= PIORA_RELATIVA, rel


def periodo_anterior(de, ate):
    d1, d2 = date.fromisoformat(qd._dia(de)), date.fromisoformat(qd._dia(ate))
    n = (d2 - d1).days + 1
    return d1 - timedelta(days=n), d1 - timedelta(days=1)


def _persistencia(db, chave, ate, meta, sentido, meses=3):
    """Em quantos dos últimos `meses` meses o indicador ficou fora da meta."""
    fora = 0
    for ini, fim, _rot in qd.meses_ate(ate, meses):
        plano, _ = qd.coletar(db, ini, fim)
        v = plano.get(chave)
        if v is not None and qd._situacao(v, meta, sentido) != 'ok':
            fora += 1
    return fora


def detectar(db, de, ate):
    """Achados agrupados por tipo de problema, cada um com evidências, concentração (Pareto), GUT e indicadores envolvidos."""
    qualidade.garantir(db)
    plano, temas = qd.coletar(db, de, ate)
    a_de, a_ate = periodo_anterior(de, ate)
    plano_ant, _ = qd.coletar(db, a_de, a_ate)
    metas = qualidade.metas(db)
    achados, perguntas = {}, []
    for chave, (tipo, base_ref, seguranca) in REGRAS.items():
        valor = plano.get(chave)
        meta, sentido = metas[chave]
        if valor is None:
            falta = next((c[5] for c in qd.DEFINICOES if c[0] == chave), '')
            if falta:
                perguntas.append({'indicador': chave, 'nome': NOMES[chave], 'texto': falta})
            continue
        if base_ref:
            base = temas[base_ref[0]].get(base_ref[1]) or 0
            if base < MIN_BASE:
                continue
        situ = qd._situacao(valor, meta, sentido)
        piorou, rel = _piorou(valor, plano_ant.get(chave), sentido)
        if situ == 'ok':
            continue
        desvio = _desvio(valor, meta, sentido)
        a = achados.setdefault(tipo, {'tipo': tipo, 'titulo': TITULOS[tipo], 'indicadores': [], 'evidencias': [], 'desvio': 0.0,
                                      'piora': 0.0, 'seguranca': False, 'critico': False})
        un = UNIDADES[chave]
        comp = '≥' if sentido == 'min' else '≤'
        ev = '%s: %s (meta %s %s) de %s a %s' % (NOMES[chave], _fmt(valor, un), comp, _fmt(meta, un), _br(qd._dia(de)), _br(qd._dia(ate)))
        if plano_ant.get(chave) is not None:
            ev += '; período anterior %s' % _fmt(plano_ant.get(chave), un)
        a['evidencias'].append(ev)
        a['indicadores'].append(chave)
        a['desvio'] = max(a['desvio'], desvio)
        a['piora'] = max(a['piora'], rel if piorou else 0.0)
        a['seguranca'] = a['seguranca'] or seguranca
        a['critico'] = a['critico'] or situ == 'critico'
        a.setdefault('meta_texto', '%s %s %s' % (NOMES[chave], comp, _fmt(meta, un)))
    # faltas sem motivo: sem isso o Pareto por motivo fica cego
    sem_motivo = len(qd.faltas_sem_motivo(db, de, ate, limite=10000))
    if sem_motivo >= 5:
        perguntas.append({'indicador': 'faltas', 'nome': 'Motivo das faltas',
                          'texto': '%d faltas do período estão sem motivo. Classifique no Gráfico de Pareto (fonte "Faltas por motivo").' % sem_motivo})
    for tipo, a in achados.items():
        a['concentracao'] = []
        for fonte in PARETOS.get(tipo, ()):
            p = qd.pareto(db, fonte, de, ate)
            if p['itens'] and p['total'] >= 5:
                top = p['itens'][0]
                if top['rotulo'].startswith('(') and len(p['itens']) > 1:
                    top = p['itens'][1]
                if top['pct'] >= 30:
                    a['concentracao'].append('%s: "%s" responde por %s do total (%s de %s)' % (
                        p['nome'], top['rotulo'], ('%.0f%%' % top['pct']), _num(top['valor']), _num(p['total'])))
        a['gut'] = _gut(db, a, ate, metas)
    ordem = sorted(achados.values(), key=lambda x: (-(x['gut']['g'] * x['gut']['u'] * x['gut']['t']), x['tipo']))
    return {'de': qd._dia(de), 'ate': qd._dia(ate), 'achados': ordem, 'perguntas': perguntas}


def _num(v):
    return ('%.2f' % v).replace('.', ',') if v != int(v) else '%d' % v


def _gut(db, a, ate, metas):
    d = a['desvio']
    g = 5 if d >= 0.5 else 4 if d >= 0.25 else 3 if d >= 0.1 else 2
    if a['seguranca']:
        g = min(5, g + 1)
    if a['tipo'] in ('vencimentos', 'financeiro'):
        u = 5
    else:
        u = 5 if a['piora'] >= 0.5 else 4 if a['piora'] >= PIORA_RELATIVA else 3 if a['critico'] else 2
    chave = a['indicadores'][0]
    meta, sentido = metas[chave]
    fora = _persistencia(db, chave, ate, meta, sentido)
    t = {3: 5, 2: 4, 1: 3}.get(fora, 2)
    return {'g': g, 'u': u, 't': t, 'meses_fora': fora}


def _plano(a, hoje):
    lib = BIBLIOTECA.get(a['tipo'], {})
    prazo = (hoje + timedelta(days=60)).isoformat()
    hipotese = '; '.join(a['concentracao']) if a['concentracao'] else 'Concentração não identificada nos dados; investigar com a equipe.'
    acoes = lib.get('acoes', [])
    return {
        'titulo': a['titulo'],
        'descricao': 'Problema identificado pelo robô do PDCA com os dados do sistema.\n' + '\n'.join('• ' + e for e in a['evidencias']),
        'plan_meta': 'Atingir %s até %s e manter por dois meses seguidos.' % (a.get('meta_texto', 'a meta'), _br(prazo)),
        'plan_causa': 'Hipótese a confirmar: ' + hipotese,
        'plan_indicador': ', '.join(NOMES[c] for c in a['indicadores']) + ' (acompanhar no painel de Indicadores, mensalmente).',
        'do_execucao': '\n'.join('%d. %s' % (i + 1, x[0]) for i, x in enumerate(acoes)) or 'Definir as ações com a equipe.',
        'act_padrao': 'Se a meta for atingida por dois meses seguidos, incorporar as ações ao procedimento padrão e ao fluxograma do '
                      'processo. Se não, voltar ao Ishikawa e aos 5 Porquês com os novos dados.',
        'responsavel': acoes[0][3] if acoes else '', 'prazo': prazo, 'check_data': (hoje + timedelta(days=30)).isoformat(),
        'gut_g': a['gut']['g'], 'gut_u': a['gut']['u'], 'gut_t': a['gut']['t'], 'indicador': a['indicadores'][0],
    }


def _descartado(db, chave, hoje):
    r = db.execute('SELECT ate FROM cq_robo_descartes WHERE chave=?', (chave,)).fetchone()
    return bool(r and r['ate'] >= hoje.isoformat())


def analisar(db, de, ate, usuario='ROBÔ', gerar=True):
    """Roda o robô. Com `gerar`, abre (ou atualiza) os rascunhos de problema. Devolve o relatório da execução."""
    qualidade.garantir(db)
    hoje = date.today()
    r = detectar(db, de, ate)
    novos = 0
    for a in r['achados']:
        a['problema_id'] = None
        a['novo'] = False
        chave = 'robo:' + a['tipo']
        if _descartado(db, chave, hoje):
            a['descartado'] = True
            continue
        if not gerar:
            continue
        aberto = db.execute("SELECT id FROM cq_problemas WHERE chave_robo=? AND status IN ('RASCUNHO','ABERTO','EM ANDAMENTO') "
                            "ORDER BY id DESC LIMIT 1", (chave,)).fetchone()
        evid = a['evidencias'] + ['Concentração: ' + c for c in a['concentracao']]
        if aberto:
            # problema já existe: atualiza as evidências e a GUT, sem mexer no que a equipe escreveu
            db.execute('UPDATE cq_problemas SET evidencia=?, gut_g=?, gut_u=?, gut_t=?, atualizado_por=?, atualizado_em=? WHERE id=?',
                       (json.dumps(evid, ensure_ascii=False), a['gut']['g'], a['gut']['u'], a['gut']['t'], usuario, agora(), aberto['id']))
            a['problema_id'] = aberto['id']
            continue
        dados = _plano(a, hoje)
        pid = qualidade.criar_problema(db, dados, usuario, origem='ROBÔ', evidencia=evid, chave_robo=chave)
        db.execute('UPDATE cq_problemas SET status=? WHERE id=?', (RASCUNHO, pid))
        lib = BIBLIOTECA.get(a['tipo'], {})
        for cat, causas in lib.get('causas', {}).items():
            for c in causas:
                db.execute('INSERT INTO cq_causas (problema_id, categoria, texto, principal, criado_em) VALUES (?,?,?,0,?)', (pid, cat, c, agora()))
        for c in a['concentracao']:
            db.execute("INSERT INTO cq_causas (problema_id, categoria, texto, principal, criado_em) VALUES (?, 'Medição', ?, 1, ?)",
                       (pid, 'Dado do sistema: ' + c, agora()))
        for n, txt in enumerate(lib.get('porques', [])[:5], start=1):
            db.execute('INSERT OR REPLACE INTO cq_porques (problema_id, nivel, resposta) VALUES (?,?,?)', (pid, n, txt))
        for i, (o_que, por_que, onde, quem, como) in enumerate(lib.get('acoes', [])):
            db.execute("INSERT INTO cq_acoes (problema_id, o_que, por_que, onde, quando, quem, como, status, criado_por, criado_em, atualizado_em) "
                       "VALUES (?,?,?,?,?,?,?,'A FAZER',?,?,?)",
                       (pid, o_que, por_que, onde, (hoje + timedelta(days=15 * (i + 1))).isoformat(), quem, como, usuario, agora(), agora()))
        db.commit()
        a['problema_id'] = pid
        a['novo'] = True
        novos += 1
    resumo = {'achados': [{k: a.get(k) for k in ('tipo', 'titulo', 'evidencias', 'concentracao', 'gut', 'problema_id', 'novo', 'descartado')}
                          for a in r['achados']], 'perguntas': r['perguntas']}
    db.execute('INSERT INTO cq_robo_execucoes (executado_em, de, ate, achados, novos, por, resumo) VALUES (?,?,?,?,?,?,?)',
               (agora(), r['de'], r['ate'], len(r['achados']), novos, usuario, json.dumps(resumo, ensure_ascii=False)))
    db.commit()
    r['novos'] = novos
    return r


def ultima_execucao(db):
    qualidade.garantir(db)
    e = db.execute('SELECT * FROM cq_robo_execucoes ORDER BY id DESC LIMIT 1').fetchone()
    if e is None:
        return None
    x = dict(e)
    x['resumo_obj'] = json.loads(x['resumo'] or '{}')
    return x


def aceitar(db, pid, usuario):
    p = qualidade.problema(db, pid)
    if p['status'] != RASCUNHO:
        raise qualidade.ErroQualidade('Só rascunhos do robô podem ser aceitos.')
    db.execute("UPDATE cq_problemas SET status='ABERTO', atualizado_por=?, atualizado_em=? WHERE id=?", (usuario, agora(), pid))
    db.commit()


def descartar(db, pid, usuario, dias=DIAS_DESCARTE):
    p = qualidade.problema(db, pid)
    db.execute("UPDATE cq_problemas SET status='DESCARTADO', atualizado_por=?, atualizado_em=? WHERE id=?", (usuario, agora(), pid))
    if p['chave_robo']:
        db.execute('INSERT INTO cq_robo_descartes (chave, ate, por, em) VALUES (?,?,?,?) ON CONFLICT(chave) DO UPDATE SET ate=excluded.ate, '
                   'por=excluded.por, em=excluded.em', (p['chave_robo'], (date.today() + timedelta(days=dias)).isoformat(), usuario, agora()))
    db.commit()


def rotina_diaria(db, hoje=None):
    """Uma análise por dia (últimos 30 dias), chamada pelo laço de avisos. Avisa a gerência quando surge problema novo."""
    hoje = hoje or date.today()
    qualidade.garantir(db)
    ja = db.execute("SELECT 1 FROM cq_robo_execucoes WHERE substr(executado_em,1,10)=? AND por='ROBÔ'", (hoje.isoformat(),)).fetchone()
    if ja:
        return None
    r = analisar(db, hoje - timedelta(days=30), hoje, usuario='ROBÔ')
    if r['novos']:
        from .avisos import gerentes, sistema_id
        de = sistema_id(db)
        if de:
            titulos = [a['titulo'] for a in r['achados'] if a.get('novo')]
            corpo = ('Robô do PDCA: %d problema(s) novo(s) para analisar na Qualidade: %s. Abra "Robô do PDCA" para aceitar, editar ou '
                     'descartar.' % (r['novos'], '; '.join(titulos)))[:1900]
            for para in gerentes(db):
                db.execute('INSERT INTO chat_mensagens (de_id, para_id, corpo, criado_em) VALUES (?,?,?,?)', (de, para, corpo, agora()))
            db.commit()
    return r
