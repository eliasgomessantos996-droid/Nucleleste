"""Dashboard: indicadores e gráficos de atendimentos, guias, medicamentos e contas."""
import json
from datetime import date, datetime, timedelta

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from . import campanhas, login_obrigatorio, util
from .db import config_get, config_set, get_db

bp = Blueprint('dash', __name__)

# painéis escolhidos pela gerência: (chave, rótulo); a chave também é a do dicionário 'dados' quando há dados
PAINEIS = [
    ('kpis', 'Números do período (cartões do topo)'), ('serie', 'Atendimentos por dia/mês'), ('exames', 'Por exame'),
    ('convenios', 'Convênios'), ('medicos', 'Médicos solicitantes'), ('faixas', 'Faixa etária'), ('semana', 'Dia da semana'),
    ('doze_meses', 'Últimos 12 meses'), ('atencao', 'Atenção (contas e doses)'), ('recentes', 'Últimos atendimentos'),
    ('doses', 'Próximas doses'),
]
CHAVE_PAINEIS_OCULTOS = 'dashboard_paineis_ocultos'

PERIODOS = [
    ('hoje', 'Hoje'), ('7d', '7 dias'), ('30d', '30 dias'), ('mes', 'Este mês'),
    ('mes_ant', 'Mês anterior'), ('ano', 'Este ano'), ('tudo', 'Tudo'),
]
DIAS_SEMANA = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom']
MESES_ABREV = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez']
FAIXAS = [(0, 17, '0–17'), (18, 29, '18–29'), (30, 39, '30–39'), (40, 49, '40–49'), (50, 59, '50–59'),
          (60, 69, '60–69'), (70, 79, '70–79'), (80, 200, '80+')]
SERIE_DIARIA_MAX_DIAS = 62  # acima disso a série diária vira mensal
CACHE_SEGUNDOS = 30


def _cache_dashboard(db, chave, calcular):
    """Contas pesadas guardadas por CACHE_SEGUNDOS e calculadas uma vez só, mesmo com várias pessoas abrindo juntas
    (ver cache_curto). Períodos longos (mais de um ano) ficam 2 minutos: quase não mudam e são os mais caros."""
    from . import cache_curto
    from .anexos import caminho_do_banco
    longo = chave[0] in ('tudo', 'ano')
    return cache_curto.obter(('dashboard', caminho_do_banco(db)) + tuple(chave), calcular, 120 if longo else CACHE_SEGUNDOS)


def _pode_gerir_paineis():
    """Administração e gerência veem todos os painéis e são os únicos que escolhem quais os usuários veem."""
    return bool(g.usuario['admin']) or 'gerencia' in (g.get('modulos') or ())


def _paineis_ocultos():
    """Chaves de painéis ocultos para os usuários comuns; chaves desconhecidas na configuração são ignoradas."""
    try:
        valor = json.loads(config_get(CHAVE_PAINEIS_OCULTOS, '[]') or '[]')
    except ValueError:
        return set()
    if not isinstance(valor, list):
        return set()
    conhecidas = {k for k, _ in PAINEIS}
    return {k for k in valor if k in conhecidas}


def _saudacao():
    h = datetime.now().hour
    return 'Bom dia' if h < 12 else 'Boa tarde' if h < 18 else 'Boa noite'


def _intervalo(db):
    hoje = date.today()
    a = request.args
    de, ate = util.para_data(a.get('de')), util.para_data(a.get('ate'))
    p = a.get('p') or ('custom' if de and ate else 'mes')
    if p == 'custom' and de and ate:
        if de > ate:
            de, ate = ate, de
    elif p == 'hoje':
        de = ate = hoje
    elif p == '7d':
        de, ate = hoje - timedelta(days=6), hoje
    elif p == '30d':
        de, ate = hoje - timedelta(days=29), hoje
    elif p == 'mes_ant':
        ate = hoje.replace(day=1) - timedelta(days=1)
        de = ate.replace(day=1)
    elif p == 'ano':
        de, ate = date(hoje.year, 1, 1), hoje
    elif p == 'tudo':
        primeiro = db.execute("SELECT MIN(data) FROM atendimentos WHERE data LIKE '____-__-__'").fetchone()[0]
        de, ate = util.para_data(primeiro) or hoje.replace(day=1), hoje
    else:
        p, de, ate = 'mes', hoje.replace(day=1), hoje
    return p, de, ate


def _delta(atual, anterior):
    if anterior in (None, 0):
        return None
    return round((atual - anterior) * 100 / anterior, 1)


def _mes_chave(d):
    return '%04d-%02d' % (d.year, d.month)


def _meses_entre(de, ate):
    meses, d = [], de.replace(day=1)
    while d <= ate:
        meses.append(d)
        d = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
    return meses


def _ranking(db, expr, where, params, limite=8, vazio='(NÃO INFORMADO)'):
    rows = db.execute(
        "SELECT COALESCE(NULLIF(%s,''),?) AS rotulo, COUNT(*) AS qtd FROM atendimentos WHERE %s "
        'GROUP BY 1 ORDER BY 2 DESC, 1' % (expr, where), [vazio] + params).fetchall()
    return _ranking_itens([(r['rotulo'], r['qtd']) for r in rows], limite)


def _como_sqlite(valor):
    """UPPER(TRIM(x)) exatamente como o SQLite faz: tira só espaços e põe em maiúscula só as letras sem acento."""
    return ''.join(c.upper() if 'a' <= c <= 'z' else c for c in (valor or '').strip(' '))


def _rankings_de_uma_vez(db, where, params):
    """Os quatro rankings (exame, convênio, médico, usuário) numa passada só pelo índice do painel. Usado nos períodos
    longos, onde quatro consultas separadas custam o dobro (3,6 milhões de atendimentos: 28 s contra 14 s)."""
    somas = [{}, {}, {}, {}]
    vazios = ('(NÃO INFORMADO)', '(NÃO INFORMADO)', '(NÃO INFORMADO)', '(importado)')
    for r in db.execute('SELECT exame, convenio, medico, usuario, COUNT(*) FROM atendimentos WHERE ' + where + ' GROUP BY 1, 2, 3, 4', params):
        for i in range(4):
            chave = _como_sqlite(r[i]) or vazios[i]
            somas[i][chave] = somas[i].get(chave, 0) + r[4]
    ordem = [sorted(s.items(), key=lambda kv: (-kv[1], kv[0])) for s in somas]
    return (_ranking_itens(ordem[0], 8), _ranking_itens(ordem[1], 8), _ranking_itens(ordem[2], 10), _ranking_itens(ordem[3], 6))


def _ranking_itens(pares, limite):
    itens = [{'rotulo': rotulo, 'valor': qtd} for rotulo, qtd in pares]
    if len(itens) > limite:
        cauda = itens[limite - 1:]
        # 'resto' vira nota de rodapé nas barras horizontais e fatia "Outros" na rosca
        itens = itens[:limite - 1] + [{'rotulo': 'Outros', 'valor': sum(i['valor'] for i in cauda), 'resto': True,
                                       'qtd_itens': len(cauda)}]
    return itens


@bp.route('/dashboard/paineis', methods=['GET', 'POST'])
@login_obrigatorio
def paineis():
    if not _pode_gerir_paineis():
        abort(403)
    if request.method == 'POST':
        if request.form.get('acao') == 'campanhas':
            ligar = bool(request.form.get('campanhas'))
            config_set(campanhas.CHAVE, '1' if ligar else '0')
            flash('Campanhas de saúde ligadas.' if ligar else 'Campanhas de saúde desligadas.', 'ok')
            return redirect(url_for('dash.paineis'))
        marcados = set(request.form.getlist('mostrar'))
        config_set(CHAVE_PAINEIS_OCULTOS, json.dumps([k for k, _ in PAINEIS if k not in marcados]))
        flash('Painéis do Início atualizados.', 'ok')
        return redirect(url_for('dash.paineis'))
    visiveis = {k for k, _ in PAINEIS} - _paineis_ocultos()
    meses = [(n, campanhas.NOMES_MES[n - 1], campanhas.CAMPANHAS[n]) for n in range(1, 13)]
    return render_template('dashboard_paineis.html', paineis=PAINEIS, visiveis=visiveis,
                           ligado=campanhas.ligado(), meses=meses)


@bp.route('/dashboard')
@login_obrigatorio
def dashboard():
    db = get_db()
    hoje = date.today()
    p, de, ate = _intervalo(db)
    n_dias = (ate - de).days + 1
    de_s, ate_s = de.isoformat(), ate.isoformat()
    where, params = 'data BETWEEN ? AND ?', [de_s, ate_s]

    # período anterior (mesma duração) para a comparação
    comparar = p != 'tudo'
    pa_ate = de - timedelta(days=1)
    pa_de = pa_ate - timedelta(days=n_dias - 1)

    def _calcular():
        """Contas pesadas do período (séries, rankings, faixas). Ficam em cache por pouco tempo: ver _cache_dashboard."""
        db.execute('PRAGMA cache_size=-65536')
        def total_atend(d1, d2):
            return db.execute('SELECT COUNT(*) FROM atendimentos WHERE data BETWEEN ? AND ?',
                              (d1.isoformat(), d2.isoformat())).fetchone()[0]

        atual = total_atend(de, ate)
        anterior = total_atend(pa_de, pa_ate) if comparar else None
        # pacientes distintos: os com cadastro pelo id e os sem cadastro pelo nome (duas contagens que usam os índices)
        # períodos longos: agrupar pela ordem do índice (cliente, data) é bem mais rápido que um DISTINCT de milhões de linhas
        if n_dias > 180:
            com_id = db.execute('SELECT COUNT(*) FROM (SELECT cliente_id FROM atendimentos INDEXED BY ix_atend_cli_data WHERE cliente_id IS NOT NULL '
                                'AND ' + where + ' GROUP BY cliente_id)', params).fetchone()[0]
        else:
            com_id = db.execute('SELECT COUNT(DISTINCT cliente_id) FROM atendimentos WHERE ' + where + ' AND cliente_id IS NOT NULL',
                                params).fetchone()[0]
        pacientes = com_id + db.execute(
            'SELECT COUNT(DISTINCT cliente_nome) FROM atendimentos WHERE ' + where + ' AND cliente_id IS NULL', params).fetchone()[0]
        primeira_vez = db.execute(
            'SELECT COUNT(*) FROM (SELECT cliente_id, MIN(data) AS d FROM atendimentos WHERE cliente_id IS NOT NULL '
            'GROUP BY cliente_id) WHERE d BETWEEN ? AND ?', (de_s, ate_s)).fetchone()[0]
        guias = db.execute('SELECT COUNT(*) FROM guias WHERE data BETWEEN ? AND ?', (de_s, ate_s)).fetchone()[0]
        dias_com_atend = db.execute('SELECT COUNT(DISTINCT data) FROM atendimentos WHERE ' + where, params).fetchone()[0]

        # --- séries temporais
        por_dia = {r['data']: r['qtd'] for r in db.execute(
            'SELECT data, COUNT(*) AS qtd FROM atendimentos WHERE %s GROUP BY data' % where, params)}
        if n_dias <= SERIE_DIARIA_MAX_DIAS:
            serie = []
            for i in range(n_dias):
                d = de + timedelta(days=i)
                serie.append({'rotulo': '%02d/%02d' % (d.day, d.month), 'valor': por_dia.get(d.isoformat(), 0),
                              'dica': util.data_br(d), 'fim_semana': d.weekday() >= 5})
            serie_titulo = 'Atendimentos por dia'
        else:
            por_mes = {}
            for k, v in por_dia.items():
                por_mes[k[:7]] = por_mes.get(k[:7], 0) + v
            serie = [{'rotulo': '%s/%02d' % (MESES_ABREV[m.month - 1], m.year % 100), 'valor': por_mes.get(_mes_chave(m), 0),
                      'dica': '%s de %d' % (MESES_ABREV[m.month - 1], m.year)} for m in _meses_entre(de, ate)]
            serie_titulo = 'Atendimentos por mês'

        inicio12 = (hoje.replace(day=1) - timedelta(days=330)).replace(day=1)
        m12 = {r['mes']: r['qtd'] for r in db.execute(
            "SELECT substr(data,1,7) AS mes, COUNT(*) AS qtd FROM atendimentos WHERE data >= ? GROUP BY 1",
            (inicio12.isoformat(),))}
        doze_meses = [{'rotulo': '%s/%02d' % (MESES_ABREV[m.month - 1], m.year % 100), 'valor': m12.get(_mes_chave(m), 0),
                       'dica': '%s de %d' % (MESES_ABREV[m.month - 1], m.year)} for m in _meses_entre(inicio12, hoje)]
        while len(doze_meses) > 1 and doze_meses[0]['valor'] == 0 and any(i['valor'] for i in doze_meses):
            doze_meses.pop(0)  # meses antes do início do histórico não acrescentam nada

        # --- rankings
        if n_dias > 500:
            exames, convenios, medicos, usuarios = _rankings_de_uma_vez(db, where, params)
        else:
            exames = _ranking(db, 'UPPER(TRIM(exame))', where, params)
            convenios = _ranking(db, 'UPPER(TRIM(convenio))', where, params)
            medicos = _ranking(db, 'UPPER(TRIM(medico))', where, params, limite=10)
            usuarios = _ranking(db, 'UPPER(TRIM(usuario))', where, params, limite=6, vazio='(importado)')

        # --- dia da semana e faixa etária
        # contagem por dia da semana direto no banco (%w: 0 = domingo; a lista começa na segunda)
        semana = [0] * 7
        for r in db.execute("SELECT CAST(strftime('%w', data) AS INTEGER) AS w, COUNT(*) AS n FROM atendimentos WHERE " + where +
                            " AND data LIKE '____-__-__' GROUP BY w", params):
            if r['w'] is not None:
                semana[(r['w'] + 6) % 7] += r['n']
        por_semana = [{'rotulo': DIAS_SEMANA[i], 'valor': semana[i], 'dica': DIAS_SEMANA[i]} for i in range(7)]

        faixas = {r[2]: 0 for r in FAIXAS}
        faixas['Sem data'] = 0

        def somar_faixa(idade, qtd):
            if idade is None or idade < 0:
                faixas['Sem data'] += qtd
                return
            for lo, hi, nome in FAIXAS:
                if lo <= idade <= hi:
                    faixas[nome] += qtd
                    return
            faixas['Sem data'] += qtd
        # uma passada só: com as duas datas no formato AAAA-MM-DD a idade (anos completos) é calculada no banco; as outras
        # combinações vêm agrupadas por (data, nascimento) e a idade é calculada aqui, como antes
        iso = "a.data LIKE '____-__-__' AND COALESCE(c.data_nasc,'') LIKE '____-__-__'"
        # períodos longos: percorrer pela ordem dos clientes lê o cadastro em sequência (no teste com 3,6 milhões de
        # atendimentos: 67 s pela data contra 17 s por cliente); períodos curtos continuam pela data
        indice_faixa = 'INDEXED BY ix_atend_cli_data' if n_dias > 500 else ''
        for r in db.execute(
                "SELECT CASE WHEN " + iso + " THEN CAST(substr(a.data,1,4) AS INTEGER) - CAST(substr(c.data_nasc,1,4) AS INTEGER) "
                "- (substr(a.data,6,5) < substr(c.data_nasc,6,5)) END AS idade, "
                "CASE WHEN " + iso + " THEN NULL ELSE a.data END AS d, CASE WHEN " + iso + " THEN NULL ELSE c.data_nasc END AS n, "
                "(" + iso + ") AS calculada, COUNT(*) AS qtd FROM atendimentos a " + indice_faixa + " LEFT JOIN clientes c ON c.id=a.cliente_id "
                "WHERE a." + where + " GROUP BY 1, 2, 3, 4", params):
            somar_faixa(r['idade'] if r['calculada'] else util.idade(r['n'], r['d']), r['qtd'])
        faixa_lista = [{'rotulo': k, 'valor': v, 'dica': k} for k, v in faixas.items() if k != 'Sem data' or v]
        return {'atual': atual, 'anterior': anterior, 'pacientes': pacientes, 'primeira_vez': primeira_vez, 'guias': guias, 'dias_com_atend': dias_com_atend, 'serie': serie, 'serie_titulo': serie_titulo, 'doze_meses': doze_meses, 'exames': exames, 'convenios': convenios, 'medicos': medicos, 'usuarios': usuarios, 'por_semana': por_semana, 'faixa_lista': faixa_lista}

    # cache curto: o mesmo período pedido por várias pessoas ao mesmo tempo é calculado uma vez; um atendimento novo
    # (id maior) invalida na hora
    marca = db.execute('SELECT MAX(id), COUNT(*) FROM atendimentos WHERE data BETWEEN ? AND ?', (de_s, ate_s)).fetchone()
    c = _cache_dashboard(db, (p, de_s, ate_s, hoje.isoformat(), marca[0], marca[1]), _calcular)
    atual = c['atual']
    anterior = c['anterior']
    pacientes = c['pacientes']
    primeira_vez = c['primeira_vez']
    guias = c['guias']
    dias_com_atend = c['dias_com_atend']
    serie = c['serie']
    serie_titulo = c['serie_titulo']
    doze_meses = c['doze_meses']
    exames = c['exames']
    convenios = c['convenios']
    medicos = c['medicos']
    usuarios = c['usuarios']
    por_semana = c['por_semana']
    faixa_lista = c['faixa_lista']

    # --- alertas operacionais e financeiros (independem do período)
    em7 = (hoje + timedelta(days=7)).isoformat()
    contas = db.execute(
        "SELECT COUNT(*) AS n, COALESCE(SUM(valor),0) AS total, "
        "SUM(CASE WHEN vencimento < ? THEN 1 ELSE 0 END) AS venc_n, "
        "COALESCE(SUM(CASE WHEN vencimento < ? THEN valor END),0) AS venc_total, "
        "SUM(CASE WHEN vencimento BETWEEN ? AND ? THEN 1 ELSE 0 END) AS prox_n, "
        "COALESCE(SUM(CASE WHEN vencimento BETWEEN ? AND ? THEN valor END),0) AS prox_total "
        "FROM contas WHERE status='ABERTO'",
        (hoje.isoformat(), hoje.isoformat(), hoje.isoformat(), em7, hoje.isoformat(), em7)).fetchone()
    pagas = db.execute("SELECT COUNT(*) AS n, COALESCE(SUM(valor),0) AS total FROM contas WHERE status='PAGO' "
                       'AND data_pagamento BETWEEN ? AND ?', (de_s, ate_s)).fetchone()
    doses = db.execute(
        "SELECT SUM(CASE WHEN data_dose BETWEEN ? AND ? THEN 1 ELSE 0 END) AS prox, "
        "SUM(CASE WHEN data_dose >= '2000-01-01' AND data_dose < ? THEN 1 ELSE 0 END) AS atrasadas "
        "FROM doses WHERE status='AGENDADO'", (hoje.isoformat(), em7, hoje.isoformat())).fetchone()

    proximas_doses = db.execute(
        "SELECT * FROM doses WHERE status='AGENDADO' AND data_dose BETWEEN ? AND ? ORDER BY data_dose, paciente LIMIT 6",
        (hoje.isoformat(), em7)).fetchall()
    recentes = db.execute('SELECT * FROM atendimentos ORDER BY data DESC, id DESC LIMIT 7').fetchall()

    media_dia = round(atual / dias_com_atend, 1) if dias_com_atend else 0
    dados = {
        'serie': {'titulo': serie_titulo, 'itens': serie},
        'doze_meses': doze_meses,
        'exames': exames, 'convenios': convenios, 'medicos': medicos, 'usuarios': usuarios,
        'semana': por_semana, 'faixas': faixa_lista,
        'kpis': {'atendimentos': atual, 'pacientes': pacientes, 'primeira_vez': primeira_vez, 'guias': guias,
                 'media_dia': media_dia},
    }
    # painéis ocultos para o usuário comum: saem também dos dados enviados à página (chaves iguais às de PAINEIS)
    ve_tudo = _pode_gerir_paineis()
    ocultos = set() if ve_tudo else _paineis_ocultos()
    for k in ocultos:
        dados.pop(k, None)
    visiveis = {k for k, _ in PAINEIS} - ocultos
    return render_template(
        'dashboard.html', dados=dados, visiveis=visiveis, ve_tudo=ve_tudo, periodos=PERIODOS, p=p, de=de_s, ate=ate_s, n_dias=n_dias,
        atual=atual, anterior=anterior, delta=_delta(atual, anterior) if comparar else None, pa_de=pa_de,
        pa_ate=pa_ate, comparar=comparar, pacientes=pacientes, primeira_vez=primeira_vez, guias=guias,
        media_dia=media_dia, contas=contas, pagas=pagas, doses=doses,
        proximas_doses=proximas_doses, recentes=recentes, hoje=hoje.isoformat(),
        ontem=(hoje - timedelta(days=1)).isoformat(), em7=em7, agora=datetime.now().strftime('%H:%M'),
        saudacao=_saudacao())
