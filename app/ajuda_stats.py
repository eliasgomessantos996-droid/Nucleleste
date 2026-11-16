"""Estatísticas da NucleAI: o chat é apagado, mas cada consulta fica registrada (quem, assunto, dúvida, se resolveu, nota).
Tudo aqui lê `ajuda_registros`, `ajuda_chamados` e `ajuda_nao_entendidas`."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta

from . import util

RESULTADOS = {
    'RESOLVEU': 'Resolveu',
    'RESOLVEU_E_NOVA': 'Resolveu e perguntou de novo',
    'NAO_RESOLVEU': 'Não resolveu',
    'SEM_AVALIACAO': 'Sem resposta',
    'ABANDONOU': 'Abandonou',
    None: 'Em andamento',
}
STATUS_CHAMADO = {'ABERTO': 'Aberto', 'EM_ATENDIMENTO': 'Em atendimento', 'RESOLVIDO': 'Resolvido'}


def _faixa(de, ate):
    return de + ' 00:00:00', ate + ' 23:59:59'


def _pct(a, b):
    return round(100.0 * a / b, 1) if b else None


def consultas(db, de, ate):
    """Todas as consultas do período, da mais nova para a mais antiga."""
    ini, fim = _faixa(de, ate)
    return [dict(r) for r in db.execute('SELECT * FROM ajuda_registros WHERE criado_em BETWEEN ? AND ? ORDER BY id DESC', (ini, fim))]


def chamados(db, de, ate, status=None):
    ini, fim = _faixa(de, ate)
    sql = 'SELECT * FROM ajuda_chamados WHERE criado_em BETWEEN ? AND ?'
    args = [ini, fim]
    if status in STATUS_CHAMADO:
        sql += ' AND status=?'
        args.append(status)
    return [dict(r) for r in db.execute(sql + ' ORDER BY id DESC', args)]


def painel(db, de, ate):
    regs = consultas(db, de, ate)
    cham = chamados(db, de, ate)
    total = len(regs)
    por_res = Counter(r['resultado'] for r in regs)
    resolveu = por_res['RESOLVEU'] + por_res['RESOLVEU_E_NOVA']
    nao = por_res['NAO_RESOLVEU']
    avaliadas = resolveu + nao
    notas = [r['nota'] for r in regs if r['nota']]
    distribuicao = [(n, notas.count(n)) for n in range(5, 0, -1)]

    # consultas por dia (todos os dias do período, mesmo os vazios)
    d0, d1 = util.para_data(de), util.para_data(ate)
    por_dia = Counter(r['criado_em'][:10] for r in regs)
    dias = []
    d = d0
    while d <= d1 and len(dias) < 400:
        dias.append((d.isoformat(), por_dia.get(d.isoformat(), 0)))
        d += timedelta(days=1)

    def agrupar(chave):
        g = defaultdict(lambda: {'n': 0, 'resolveu': 0, 'nao': 0})
        for r in regs:
            k = chave(r)
            g[k]['n'] += 1
            if r['resultado'] in ('RESOLVEU', 'RESOLVEU_E_NOVA'):
                g[k]['resolveu'] += 1
            elif r['resultado'] == 'NAO_RESOLVEU':
                g[k]['nao'] += 1
        saida = []
        for k, v in g.items():
            aval = v['resolveu'] + v['nao']
            saida.append(dict(chave=k, **v, taxa_nao=_pct(v['nao'], aval), taxa_resolveu=_pct(v['resolveu'], aval)))
        return saida

    temas = sorted(agrupar(lambda r: r['tema'] or '—'), key=lambda x: (-x['n'], x['chave']))
    modulos_ = sorted(agrupar(lambda r: '%s › %s' % (r['tema'] or '—', r['modulo'] or '—')), key=lambda x: (-x['n'], x['chave']))
    areas = agrupar(lambda r: '%s › %s › %s' % (r['tema'] or '—', r['modulo'] or '—', r['area'] or '—'))
    mais_consultadas = sorted(areas, key=lambda x: (-x['n'], x['chave']))[:12]
    nao_ajudou = sorted([a for a in areas if a['nao']], key=lambda x: (-x['nao'], -(x['taxa_nao'] or 0), x['chave']))[:12]

    # dúvidas escritas que a NucleAI não entendeu (o que falta na base de ajuda)
    ini, fim = _faixa(de, ate)
    nao_ent = Counter()
    for r in db.execute('SELECT texto FROM ajuda_nao_entendidas WHERE criado_em BETWEEN ? AND ?', (ini, fim)):
        nao_ent[(r['texto'] or '').strip().lower()] += 1
    nao_entendidas = [{'texto': t, 'n': n} for t, n in sorted(nao_ent.items(), key=lambda x: (-x[1], x[0]))[:30]]

    por_usuario = Counter(r['usuario'] or '—' for r in regs)
    usuarios = [{'usuario': u, 'n': n} for u, n in por_usuario.most_common(10)]
    texto_n = sum(1 for r in regs if r['origem'] == 'TEXTO')

    cham_status = Counter(c['status'] for c in cham)
    return {
        'de': de, 'ate': ate, 'total': total,
        'resolveu': resolveu, 'resolveu_e_nova': por_res['RESOLVEU_E_NOVA'], 'nao_resolveu': nao,
        'sem_resposta': por_res['SEM_AVALIACAO'] + por_res['ABANDONOU'], 'em_andamento': por_res[None],
        'taxa_resolucao': _pct(resolveu, avaliadas), 'taxa_nao': _pct(nao, avaliadas),
        'nota_media': round(sum(notas) / len(notas), 2) if notas else None, 'n_notas': len(notas), 'distribuicao_notas': distribuicao,
        'por_lista': total - texto_n, 'por_texto': texto_n, 'pct_texto': _pct(texto_n, total),
        'chamados': len(cham), 'chamados_status': {k: cham_status.get(k, 0) for k in STATUS_CHAMADO},
        'chamados_confirmados': sum(1 for c in cham if c['confirmou'] == 'SIM'),
        'chamados_negados': sum(1 for c in cham if c['confirmou'] == 'NAO'),
        'chamados_sem_gerencia_online': sum(1 for c in cham if not c['gerencia_online']),
        'por_dia': dias, 'maior_dia': max([n for _d, n in dias] or [0]),
        'temas': temas[:10], 'modulos': modulos_[:12], 'mais_consultadas': mais_consultadas, 'nao_ajudou': nao_ajudou,
        'nao_entendidas': nao_entendidas, 'usuarios': usuarios,
    }


def periodo_padrao(hoje=None):
    hoje = hoje or date.today()
    return hoje.replace(day=1), hoje
