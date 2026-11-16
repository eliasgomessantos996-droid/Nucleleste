"""Indicadores de gestão calculados com os dados que o sistema já grava (agenda, exames realizados, laudos, faturamento,
contas, blindagens, documentos, chamados da NucleAI) e com os dados que a própria Qualidade coleta (ocorrências,
pesquisa de satisfação, motivos de falta, avaliação de fornecedores).

Cada indicador devolve: chave, nome, valor, unidade, numerador/denominador (quando é taxa), meta, sentido, situação
(ok, atenção, crítico ou sem dado), série mensal dos últimos meses, de onde vem o dado e o que falta para medir melhor.
Os relatórios de gestão trazem só números agregados (nada de nome de paciente).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from . import qualidade

PRAZO_LAUDO_H = 24
DESVIO_ATIVIDADE = 0.10      # 10% entre prescrita e administrada conta como desvio


def _dia(d):
    return d if isinstance(d, str) else d.isoformat()


def _pct(n, d):
    return round(100.0 * n / d, 1) if d else None


def _num(txt):
    """Número de um texto livre ("10 mCi", "8,5"); None se não houver."""
    if txt is None:
        return None
    s = ''.join(c if (c.isdigit() or c in ',.') else ' ' for c in str(txt)).split()
    if not s:
        return None
    v = s[0].replace(',', '.')
    try:
        return float(v)
    except ValueError:
        return None


def _horas(inicio, fim):
    return (fim - inicio).total_seconds() / 3600.0


def _ts(txt):
    try:
        return datetime.fromisoformat(str(txt)[:19])
    except (TypeError, ValueError):
        return None


def meses_ate(ate, n=6):
    """Lista de (primeiro dia, último dia, rótulo mm/aa) dos n meses que terminam no mês de `ate`."""
    ate = date.fromisoformat(_dia(ate))
    saida = []
    ano, mes = ate.year, ate.month
    for _ in range(n):
        ini = date(ano, mes, 1)
        prox = date(ano + (mes // 12), mes % 12 + 1, 1)
        saida.append((ini, prox - timedelta(days=1), '%02d/%02d' % (mes, ano % 100)))
        mes -= 1
        if mes == 0:
            mes, ano = 12, ano - 1
    return list(reversed(saida))


# ------------------------------------------------------------------ cálculos por tema (todos em SQL agregado)
# Cada tema tem uma consulta que pode agrupar por mês (substr(data,1,7)): o período escolhido é uma passada só e a série
# dos últimos meses é outra passada só, em vez de repetir tudo mês a mês.
_SQL_AGENDA = (
    "SELECT {g} AS g, SUM(h.status='VEIO') AS veio, SUM(h.status='FALTOU') AS faltou, "
    "SUM(h.status IN ('RESGATADO','DESISTIU') AND COALESCE(h.resgatado_por,'')<>'') AS tratadas, SUM(h.status='RESGATADO' AND COALESCE(h.resgatado_por,'')<>'') AS resgatadas, COUNT(*) AS marcados "
    "FROM agenda_horarios h JOIN agenda_exames a ON a.id=h.agenda_id WHERE a.data BETWEEN ? AND ? AND TRIM(h.paciente)<>'' GROUP BY g")
# exames realizados: laudo (exame -> liberado -> entregue), identificação, registro completo, atividade e edições, numa passada
_SQL_REAL = (
    "SELECT g, COUNT(*) AS total, SUM(TRIM(COALESCE(paciente,''))<>'' AND COALESCE(data_nasc,'')<>'') AS ident, "
    "SUM(COALESCE(convenio,'')<>'' AND COALESCE(medico,'')<>'' AND COALESCE(hora_exame,'')<>'') AS completo, "
    "SUM(atualizado_em IS NOT NULL AND criado_em IS NOT NULL AND substr(atualizado_em,1,16)<>substr(criado_em,1,16)) AS editados, "
    "SUM(t IS NOT NULL) AS liberados, SUM(t IS NOT NULL AND t <= :prazo) AS no_prazo, AVG(t) AS media, AVG(e) AS entrega, "
    "SUM(t IS NULL AND lib IS NULL AND i IS NOT NULL AND (julianday('now','localtime') - i) * 24 > :prazo) AS pendentes, "
    "SUM(p > 0 AND a > 0) AS base_ativ, SUM(p > 0 AND a > 0 AND ABS(a - p) / p > :desvio) AS desvios "
    "FROM (SELECT g, paciente, data_nasc, convenio, medico, hora_exame, atualizado_em, criado_em, i, lib, "
    "             CASE WHEN lib >= i THEN (lib - i) * 24 END AS t, CASE WHEN lib >= i AND ent >= lib THEN (ent - lib) * 24 END AS e, "
    "             CASE WHEN COALESCE(ativ_prescrita,'')<>'' AND COALESCE(ativ_administrada,'')<>'' "
    "                  THEN CAST(REPLACE(TRIM(ativ_prescrita), ',', '.') AS REAL) END AS p, "
    "             CASE WHEN COALESCE(ativ_prescrita,'')<>'' AND COALESCE(ativ_administrada,'')<>'' "
    "                  THEN CAST(REPLACE(TRIM(ativ_administrada), ',', '.') AS REAL) END AS a "
    "      FROM (SELECT {g} AS g, paciente, data_nasc, convenio, medico, hora_exame, atualizado_em, criado_em, ativ_prescrita, "
    "                   ativ_administrada, julianday(data || ' ' || CASE WHEN COALESCE(hora_exame,'')<>'' THEN hora_exame ELSE '00:00' END) AS i, "
    "                   julianday(substr(laudo_liberado_em,1,19)) AS lib, julianday(substr(laudo_entregue_em,1,19)) AS ent "
    "            FROM realizacoes WHERE data BETWEEN :de AND :ate)) GROUP BY g")
_SQL_FAT = (
    "SELECT {g} AS g, COUNT(*) AS n, COALESCE(SUM(CASE WHEN status='RECEBIDO' OR valor_recebido IS NOT NULL THEN valor_liquido ELSE 0 END),0) "
    "AS liq_rec, COALESCE(SUM(valor_recebido),0) AS recebido, "
    "SUM(data_recebimento IS NOT NULL AND previsao IS NOT NULL AND data_recebimento>previsao) AS atrasadas, "
    "SUM(data_recebimento IS NOT NULL) AS recebidas FROM faturas WHERE COALESCE(previsao, substr(criado_em,1,10)) BETWEEN ? AND ? GROUP BY g")
_SQL_OCOR = ("SELECT {g} AS g, COUNT(*) AS n, SUM(gravidade='Grave') AS graves, SUM(status<>'ENCERRADA') AS abertas, "
             "SUM(tipo IN ('Retrabalho / repetição de exame','Laudo retificado')) AS repeticoes FROM cq_ocorrencias "
             "WHERE data BETWEEN ? AND ? GROUP BY g")
_SQL_PESQ = ("SELECT {g} AS g, COUNT(*) AS n, AVG(nota) AS media, SUM(nota>=9) AS prom, SUM(nota<=6) AS detr FROM cq_pesquisas "
             "WHERE data BETWEEN ? AND ? GROUP BY g")
_VAZIO = {}


def _por_grupo(db, sql, col, de, ate, mensal, nomeados=False):
    g = "substr(%s,1,7)" % col if mensal else "'p'"
    if nomeados:
        linhas = db.execute(sql.format(g=g), {'de': _dia(de), 'ate': _dia(ate), 'prazo': PRAZO_LAUDO_H, 'desvio': DESVIO_ATIVIDADE})
    else:
        linhas = db.execute(sql.format(g=g), (_dia(de), _dia(ate)))
    return {r['g']: r for r in linhas}


def _v(r, k):
    return (r[k] if r is not None else None) or 0


def _t_agenda(r):
    veio, faltou = _v(r, 'veio'), _v(r, 'faltou')
    resg, trat = _v(r, 'resgatadas'), _v(r, 'tratadas')
    return {'veio': veio, 'faltou': faltou, 'marcados': _v(r, 'marcados'), 'base': veio + faltou,
            'comparecimento': _pct(veio, veio + faltou), 'faltas': _pct(faltou, veio + faltou),
            # faltas que viraram reagendamento (resgate) entre as faltas já tratadas
            'resgate': _pct(resg, faltou + trat), 'resgatadas': resg, 'faltas_total': faltou + trat}


def _t_laudos(r):
    liberados = _v(r, 'liberados')
    media = r['media'] if r is not None else None
    entrega = r['entrega'] if r is not None else None
    pend = _v(r, 'pendentes')
    return {'exames': _v(r, 'total'), 'liberados': liberados, 'no_prazo': _v(r, 'no_prazo'), 'laudo_24h': _pct(_v(r, 'no_prazo'), liberados),
            'laudo_horas': round(media, 1) if media is not None else None, 'entrega_horas': round(entrega, 1) if entrega is not None else None,
            'pendentes': pend, 'laudos_pendentes': pend}


def _t_cadastro(r):
    total = _v(r, 'total')
    return {'total': total, 'identificacao': _pct(_v(r, 'ident'), total), 'registro_completo': _pct(_v(r, 'completo'), total),
            'ident': _v(r, 'ident'), 'completo': _v(r, 'completo')}


def _t_atividade(r):
    base = _v(r, 'base_ativ')
    return {'base': base, 'desvios': _v(r, 'desvios'), 'desvio_atividade': _pct(_v(r, 'desvios'), base)}


def _t_retrabalho(r, o):
    total, rep = _v(r, 'total'), _v(o, 'repeticoes')
    return {'total': total, 'editados': _v(r, 'editados'), 'repeticoes': rep, 'retrabalho': _pct(rep, total)}


def _t_financeiro(f, contas):
    glosa_valor = max(0.0, _v(f, 'liq_rec') - _v(f, 'recebido'))
    return {'faturas': _v(f, 'n'), 'glosa': _pct(glosa_valor, _v(f, 'liq_rec')), 'glosa_valor': round(glosa_valor, 2),
            'recebimento_atrasado': _pct(_v(f, 'atrasadas'), _v(f, 'recebidas')), 'contas_atrasadas': contas}


def _t_ocorrencias(o, p):
    n = _v(p, 'n')
    media = p['media'] if p is not None else None
    return {'ocorrencias': _v(o, 'n'), 'ocorrencias_graves': _v(o, 'graves'), 'ocorrencias_abertas': _v(o, 'abertas'),
            'pesquisas': n, 'satisfacao': round(media, 1) if media is not None else None,
            'nps': round(100.0 * (_v(p, 'prom') - _v(p, 'detr')) / n) if n else None}


def _t_chamados(linhas):
    tempos = []
    for r in linhas:
        a, b = _ts(r['criado_em']), _ts(r['atendido_em']) if r['atendido_em'] else None
        if a and b and b >= a:
            tempos.append(_horas(a, b))
    return {'chamados': len(linhas), 'atendidos': len(tempos), 'chamados_horas': round(sum(tempos) / len(tempos), 1) if tempos else None}


def _contas_atrasadas(db):
    return db.execute("SELECT COUNT(*) FROM contas WHERE status='ABERTO' AND vencimento IS NOT NULL AND vencimento<?",
                      (date.today().isoformat(),)).fetchone()[0]


def _chamados_linhas(db, de, ate):
    return db.execute("SELECT criado_em, atendido_em FROM ajuda_chamados WHERE substr(criado_em,1,10) BETWEEN ? AND ?",
                      (_dia(de), _dia(ate))).fetchall()


# funções de um tema só (as telas e o robô usam coletar(); estas continuam para quem precisa de um número isolado)
def agenda(db, de, ate):
    return _t_agenda(_por_grupo(db, _SQL_AGENDA, 'a.data', de, ate, False).get('p'))


def laudos(db, de, ate):
    """Tempo até o laudo (exame -> liberado), entrega (liberado -> entregue) e laudos atrasados, tudo calculado no banco."""
    return _t_laudos(_por_grupo(db, _SQL_REAL, 'data', de, ate, False, True).get('p'))


def cadastro(db, de, ate):
    return _t_cadastro(_por_grupo(db, _SQL_REAL, 'data', de, ate, False, True).get('p'))


def atividade(db, de, ate):
    """Desvio entre atividade prescrita e administrada (texto como "10 mCi" ou "10,5 mCi"), calculado no banco."""
    return _t_atividade(_por_grupo(db, _SQL_REAL, 'data', de, ate, False, True).get('p'))


def retrabalho(db, de, ate):
    """Exames alterados depois de lançados (aproximação) e ocorrências de retrabalho/repetição registradas."""
    return _t_retrabalho(_por_grupo(db, _SQL_REAL, 'data', de, ate, False, True).get('p'), _por_grupo(db, _SQL_OCOR, 'data', de, ate, False).get('p'))


def financeiro(db, de, ate):
    return _t_financeiro(_por_grupo(db, _SQL_FAT, "COALESCE(previsao, substr(criado_em,1,10))", de, ate, False).get('p'), _contas_atrasadas(db))


def vencimentos(db):
    hoje = date.today().isoformat()
    from .blindagens import TRAVADAS   # em devolução ou já devolvida não conta como vencida
    b = db.execute('SELECT COUNT(*) FROM blindagens WHERE validade<? AND status NOT IN (%s)' % ','.join('?' * len(TRAVADAS)),
                   (hoje,) + tuple(TRAVADAS)).fetchone()[0]
    d = db.execute("SELECT COUNT(*) FROM arquivos_docs WHERE vencimento IS NOT NULL AND vencimento<>'' AND vencimento<?", (hoje,)).fetchone()[0]
    return {'blindagens_vencidas': b, 'documentos_vencidos': d}


def chamados(db, de, ate):
    return _t_chamados(_chamados_linhas(db, de, ate))


def ocorrencias(db, de, ate):
    return _t_ocorrencias(_por_grupo(db, _SQL_OCOR, 'data', de, ate, False).get('p'), _por_grupo(db, _SQL_PESQ, 'data', de, ate, False).get('p'))


def fornecedores(db):
    ativos = db.execute('SELECT COUNT(*) FROM fornecedores WHERE ativo=1').fetchone()[0]
    em_dia = db.execute("SELECT COUNT(DISTINCT a.fornecedor_id) FROM cq_forn_avaliacoes a JOIN fornecedores f ON f.id=a.fornecedor_id "
                        "WHERE f.ativo=1 AND (a.proxima IS NULL OR a.proxima>=?)", (date.today().isoformat(),)).fetchone()[0]
    reprov = db.execute("SELECT COUNT(*) FROM (SELECT fornecedor_id, classificacao, MAX(data) FROM cq_forn_avaliacoes GROUP BY fornecedor_id) "
                        "WHERE classificacao='REPROVADO'").fetchone()[0]
    return {'fornecedores': ativos, 'avaliados_em_dia': em_dia, 'fornecedores_avaliados': _pct(em_dia, ativos), 'reprovados': reprov}


def _temas(db, de, ate, mensal=False, chaves=None):
    """Temas de um período (mensal=False) ou de cada mês do período (mensal=True: {'AAAA-MM': temas})."""
    ag = _por_grupo(db, _SQL_AGENDA, 'a.data', de, ate, mensal)
    re_ = _por_grupo(db, _SQL_REAL, 'data', de, ate, mensal, True)
    fa = _por_grupo(db, _SQL_FAT, "COALESCE(previsao, substr(criado_em,1,10))", de, ate, mensal)
    oc = _por_grupo(db, _SQL_OCOR, 'data', de, ate, mensal)
    pq = _por_grupo(db, _SQL_PESQ, 'data', de, ate, mensal)
    ch = {}
    for r in _chamados_linhas(db, de, ate):
        ch.setdefault((r['criado_em'] or '')[:7] if mensal else 'p', []).append(r)
    contas = _contas_atrasadas(db)
    venc, forn = vencimentos(db), fornecedores(db)
    saida = {}
    for k in (chaves if mensal else ['p']):
        saida[k] = {'agenda': _t_agenda(ag.get(k)), 'laudos': _t_laudos(re_.get(k)), 'cadastro': _t_cadastro(re_.get(k)),
                    'atividade': _t_atividade(re_.get(k)), 'retrabalho': _t_retrabalho(re_.get(k), oc.get(k)),
                    'financeiro': _t_financeiro(fa.get(k), contas), 'vencimentos': dict(venc), 'chamados': _t_chamados(ch.get(k, [])),
                    'ocorrencias': _t_ocorrencias(oc.get(k), pq.get(k)), 'fornecedores': dict(forn)}
    return saida if mensal else saida['p']


# ------------------------------------------------------------------ painel de indicadores
DEFINICOES = (
    # chave, nome, unidade, fonte, onde ver, o que falta coletar para medir melhor
    ('comparecimento', 'Comparecimento na agenda', '%', 'agenda', 'agenda.relatorio', ''),
    ('faltas', 'Taxa de faltas', '%', 'agenda', 'agenda.faltas', 'Classifique o motivo de cada falta no Pareto para achar a causa.'),
    ('resgate', 'Faltas resgatadas (reagendadas)', '%', 'agenda', 'agenda.faltas', ''),
    ('laudo_24h', 'Laudos liberados em até 24 h', '%', 'laudos', 'laudo.quadro', ''),
    ('laudo_horas', 'Tempo médio até o laudo', 'h', 'laudos', 'laudo.quadro', ''),
    ('laudos_pendentes', 'Laudos atrasados (mais de 24 h, sem liberar)', 'n', 'laudos', 'laudo.quadro', ''),
    ('identificacao', 'Identificação do paciente (nome e nascimento)', '%', 'cadastro', 'ona.pagina', ''),
    ('registro_completo', 'Registro completo do exame', '%', 'cadastro', 'ona.pagina', ''),
    ('desvio_atividade', 'Desvio de atividade administrada (>10%)', '%', 'atividade', 'lanc.lista', ''),
    ('retrabalho', 'Retrabalho / repetição de exame', '%', 'retrabalho', 'qual.ocorrencias',
     'Registre repetições e laudos retificados em Ocorrências.'),
    ('glosa', 'Glosa / diferença no recebimento', '%', 'financeiro', 'fat.lista', ''),
    ('recebimento_atrasado', 'Faturas recebidas com atraso', '%', 'financeiro', 'fat.lista', ''),
    ('contas_atrasadas', 'Contas a pagar vencidas em aberto', 'n', 'financeiro', 'fin.contas', ''),
    ('documentos_vencidos', 'Documentos e licenças vencidos', 'n', 'vencimentos', 'arq.lista', ''),
    ('chamados_horas', 'Tempo de resposta aos pedidos de ajuda', 'h', 'chamados', 'nucleai.painel', ''),
    ('ocorrencias_graves', 'Ocorrências graves', 'n', 'ocorrencias', 'qual.ocorrencias', 'Registre não conformidades e eventos em Ocorrências.'),
    ('satisfacao', 'Satisfação do paciente (nota média 0 a 10)', 'nota', 'ocorrencias', 'qual.ocorrencias',
     'Lance as pesquisas de satisfação em Ocorrências e satisfação.'),
    ('fornecedores_avaliados', 'Fornecedores com avaliação em dia', '%', 'fornecedores', 'qual.forn', ''),
)


def _situacao(valor, meta, sentido):
    if valor is None:
        return 'sem_dado'
    if sentido == 'min':
        if valor >= meta:
            return 'ok'
        return 'atencao' if valor >= meta * 0.9 else 'critico'
    if valor <= meta:
        return 'ok'
    folga = max(abs(meta) * 0.2, 1.0)
    return 'atencao' if valor <= meta + folga else 'critico'


def _plano(temas):
    return {chave: temas[fonte].get(chave) for chave, _nome, _un, fonte, _onde, _falta in DEFINICOES}


def coletar(db, de, ate):
    """Todos os números do período (um dicionário plano, chave -> valor), mais os detalhes por tema."""
    qualidade.garantir(db)
    temas = _temas(db, de, ate)
    return _plano(temas), temas


def coletar_meses(db, ate, meses=6):
    """[(rótulo mm/aa, plano)] dos últimos `meses` meses até `ate`, com uma consulta por tema para todos os meses."""
    qualidade.garantir(db)
    lista = meses_ate(ate, meses)
    por_mes = _temas(db, lista[0][0], lista[-1][1], mensal=True, chaves=[ini.isoformat()[:7] for ini, _fim, _rot in lista])
    return [(rot, _plano(por_mes[ini.isoformat()[:7]])) for ini, _fim, rot in lista]


def _marca(db):
    """Muda quando entra um horário de agenda ou um exame realizado novo (usada no cache curto). O restante (ocorrências,
    pesquisas, faturas, avaliações, mudança de status) aparece em até 1 minuto, o tempo do cache."""
    return tuple(db.execute('SELECT (SELECT MAX(id) FROM agenda_horarios), (SELECT MAX(id) FROM realizacoes)').fetchone())


def painel(db, de, ate, meses=6):
    """Indicadores com meta, situação e série mensal (os últimos `meses` meses até `ate`). As contas ficam 60 s em cache
    e são feitas uma vez só quando várias pessoas abrem o painel juntas; um lançamento novo aparece na hora."""
    from flask import url_for
    from . import cache_curto
    from .anexos import caminho_do_banco
    qualidade.garantir(db)

    def calcular():
        db.execute('PRAGMA cache_size=-65536')
        return coletar(db, de, ate), coletar_meses(db, ate, meses)
    (plano, temas), meses_lista = cache_curto.obter(('kpi', caminho_do_banco(db), _dia(de), _dia(ate), meses, _marca(db)), calcular, 60)
    mts = qualidade.metas(db)
    series = {c[0]: [] for c in DEFINICOES}
    for rot, p in meses_lista:
        for chave in series:
            series[chave].append({'rotulo': rot, 'valor': p.get(chave)})
    saida = []
    for chave, nome, un, fonte, onde, falta in DEFINICOES:
        meta, sentido = mts[chave]
        valor = plano.get(chave)
        try:
            link = url_for(onde)
        except Exception:
            link = ''
        saida.append({'chave': chave, 'nome': nome, 'valor': valor, 'unidade': un, 'meta': meta, 'sentido': sentido,
                      'situacao': _situacao(valor, meta, sentido), 'serie': series[chave], 'fonte': fonte, 'link': link,
                      'falta': falta if valor is None or chave in ('faltas', 'retrabalho', 'satisfacao') else ''})
    resumo = {s: sum(1 for i in saida if i['situacao'] == s) for s in ('ok', 'atencao', 'critico', 'sem_dado')}
    return {'de': _dia(de), 'ate': _dia(ate), 'indicadores': saida, 'resumo': resumo, 'temas': temas}


# ------------------------------------------------------------------ Pareto (fontes)
FONTES_PARETO = (
    ('faltas_exame', 'Faltas por exame'),
    ('faltas_convenio', 'Faltas por convênio'),
    ('faltas_motivo', 'Faltas por motivo'),
    ('faltas_dia_semana', 'Faltas por dia da semana'),
    ('ocorrencias_tipo', 'Ocorrências por tipo'),
    ('ocorrencias_setor', 'Ocorrências por setor'),
    ('laudo_atraso_exame', 'Laudos fora do prazo por exame'),
    ('glosa_convenio', 'Diferença de recebimento (glosa) por convênio (R$)'),
    ('exames_volume', 'Exames realizados por tipo'),
)
DIAS_SEMANA = ('Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo')


def _contagem_pareto(db, fonte, de, ate):
    d1, d2 = _dia(de), _dia(ate)
    base_falta = ("FROM agenda_horarios h JOIN agenda_exames a ON a.id=h.agenda_id WHERE a.data BETWEEN ? AND ? "
                  "AND h.status='FALTOU' AND TRIM(h.paciente)<>''")
    if fonte == 'faltas_exame':
        return db.execute('SELECT a.exame AS k, COUNT(*) AS v ' + base_falta + ' GROUP BY a.exame', (d1, d2)).fetchall()
    if fonte == 'faltas_convenio':
        return db.execute("SELECT COALESCE(NULLIF(TRIM(h.convenio),''),'(sem convênio)') AS k, COUNT(*) AS v " + base_falta +
                          " GROUP BY k", (d1, d2)).fetchall()
    if fonte == 'faltas_motivo':
        return db.execute("SELECT COALESCE(m.motivo,'(motivo não informado)') AS k, COUNT(*) AS v FROM agenda_horarios h "
                          "JOIN agenda_exames a ON a.id=h.agenda_id LEFT JOIN cq_falta_motivos m ON m.horario_id=h.id "
                          "WHERE a.data BETWEEN ? AND ? AND h.status='FALTOU' AND TRIM(h.paciente)<>'' GROUP BY k", (d1, d2)).fetchall()
    if fonte == 'faltas_dia_semana':
        linhas = db.execute("SELECT CAST(strftime('%w', a.data) AS INTEGER) AS w, COUNT(*) AS v " + base_falta + ' GROUP BY w',
                            (d1, d2)).fetchall()
        return [{'k': DIAS_SEMANA[(r['w'] - 1) % 7], 'v': r['v']} for r in linhas]
    if fonte == 'ocorrencias_tipo':
        return db.execute('SELECT tipo AS k, COUNT(*) AS v FROM cq_ocorrencias WHERE data BETWEEN ? AND ? GROUP BY tipo', (d1, d2)).fetchall()
    if fonte == 'ocorrencias_setor':
        return db.execute("SELECT COALESCE(NULLIF(setor,''),'(sem setor)') AS k, COUNT(*) AS v FROM cq_ocorrencias "
                          "WHERE data BETWEEN ? AND ? GROUP BY k", (d1, d2)).fetchall()
    if fonte == 'laudo_atraso_exame':
        return db.execute(
            "SELECT COALESCE(NULLIF(exame,''),'(sem exame)') AS k, COUNT(*) AS v FROM ("
            " SELECT exame, julianday(data || ' ' || CASE WHEN COALESCE(hora_exame,'')<>'' THEN hora_exame ELSE '00:00' END) AS i, "
            "        COALESCE(julianday(substr(laudo_liberado_em,1,19)), julianday('now','localtime')) AS f "
            " FROM realizacoes WHERE data BETWEEN ? AND ?) WHERE i IS NOT NULL AND (f - i) * 24 > ? GROUP BY k",
            (d1, d2, PRAZO_LAUDO_H)).fetchall()
    if fonte == 'glosa_convenio':
        return db.execute("SELECT convenio AS k, ROUND(SUM(MAX(valor_liquido - valor_recebido, 0)),2) AS v FROM faturas "
                          "WHERE valor_recebido IS NOT NULL AND COALESCE(previsao, substr(criado_em,1,10)) BETWEEN ? AND ? "
                          "GROUP BY convenio", (d1, d2)).fetchall()
    if fonte == 'exames_volume':
        return db.execute("SELECT COALESCE(NULLIF(exame,''),'(sem exame)') AS k, COUNT(*) AS v FROM realizacoes "
                          "WHERE data BETWEEN ? AND ? GROUP BY k", (d1, d2)).fetchall()
    raise qualidade.ErroQualidade('Escolha uma fonte de dados para o Pareto.')


def pareto(db, fonte, de, ate):
    """Itens em ordem decrescente com % e % acumulado; classe A até 80%, B até 95%, C o resto. `vitais`: os itens da classe A."""
    qualidade.garantir(db)
    itens = [{'rotulo': str(r['k']), 'valor': float(r['v'] or 0)} for r in _contagem_pareto(db, fonte, de, ate)]
    itens = [i for i in itens if i['valor'] > 0]
    itens.sort(key=lambda i: (-i['valor'], i['rotulo']))
    total = sum(i['valor'] for i in itens)
    acum = 0.0
    for i in itens:
        anterior = acum
        acum += i['valor']
        i['pct'] = round(100.0 * i['valor'] / total, 1) if total else 0
        i['acum'] = round(100.0 * acum / total, 1) if total else 0
        # o item entra na classe A se o acumulado ANTES dele ainda não passou de 80%
        i['classe'] = 'A' if 100.0 * anterior / total < 80 else ('B' if 100.0 * anterior / total < 95 else 'C')
    nome = dict(FONTES_PARETO).get(fonte, fonte)
    return {'fonte': fonte, 'nome': nome, 'de': _dia(de), 'ate': _dia(ate), 'itens': itens, 'total': total,
            'vitais': [i for i in itens if i['classe'] == 'A']}


def faltas_sem_motivo(db, de, ate, limite=200):
    return [dict(r) for r in db.execute(
        "SELECT h.id, a.data, h.hora, a.exame, h.convenio FROM agenda_horarios h JOIN agenda_exames a ON a.id=h.agenda_id "
        "LEFT JOIN cq_falta_motivos m ON m.horario_id=h.id WHERE a.data BETWEEN ? AND ? AND h.status='FALTOU' "
        "AND TRIM(h.paciente)<>'' AND m.horario_id IS NULL ORDER BY a.data DESC, h.hora LIMIT ?", (_dia(de), _dia(ate), limite))]
