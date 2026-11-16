"""Agregações, registro de tokens e gráficos da NucleAI IA."""
from __future__ import annotations

import html
from datetime import date, datetime, timedelta

from .db import agora

FMT = '%Y-%m-%d %H:%M:%S'
FMT_DIA = '%Y-%m-%d'


def _formatar_num(n):
    try:
        return f'{int(n):,}'.replace(',', '.')
    except (ValueError, TypeError):
        return '0'


def registrar(db, usuario, modelo, tokens_entrada, tokens_saida, tokens_total=None,
              tempo_ms=0, teste=False, criado_em=None, usuario_id=None):
    """Registra uma requisição de IA na tabela nucleai_tokens."""
    entrada = max(0, int(tokens_entrada or 0))
    saida = max(0, int(tokens_saida or 0))
    total = int(tokens_total) if tokens_total is not None else (entrada + saida)
    tempo = max(0, int(tempo_ms or 0))
    teste_int = 1 if teste else 0
    momento = criado_em or agora()
    uid = int(usuario_id) if usuario_id is not None else None

    db.execute(
        'INSERT INTO nucleai_tokens (criado_em, usuario_id, usuario, modelo, '
        'tokens_entrada, tokens_saida, tokens_total, tempo_ms, teste) '
        'VALUES (?,?,?,?,?,?,?,?,?)',
        (momento, uid, str(usuario or ''), str(modelo or ''), entrada, saida, total, tempo, teste_int)
    )
    db.commit()


def _clausula_periodo(periodo):
    """Devolve (where_sql, params) com base no filtro de período."""
    if not periodo or str(periodo).strip() in ('todos', 'todas', 'tudo', ''):
        return '', []
    p = str(periodo).strip().lower()
    hoje = date.today()
    if p in ('hoje', 'dia', '1'):
        return 'criado_em >= ?', [hoje.strftime('%Y-%m-%d 00:00:00')]
    elif p in ('7d', '7', 'semana'):
        limite = (hoje - timedelta(days=7)).strftime('%Y-%m-%d 00:00:00')
        return 'criado_em >= ?', [limite]
    elif p in ('30d', '30', 'mes'):
        limite = (hoje - timedelta(days=30)).strftime('%Y-%m-%d 00:00:00')
        return 'criado_em >= ?', [limite]
    else:
        return 'criado_em LIKE ?', [p + '%']


def resumo_geral(db, periodo=None):
    """Cartões de gasto geral no período selecionado."""
    cond, params = _clausula_periodo(periodo)
    where = f'WHERE {cond}' if cond else ''
    row = db.execute(f'''
        SELECT
            COALESCE(SUM(tokens_total), 0) AS tokens_total,
            COALESCE(SUM(tokens_entrada), 0) AS tokens_entrada,
            COALESCE(SUM(tokens_saida), 0) AS tokens_saida,
            COUNT(*) AS pedidos,
            COALESCE(AVG(tempo_ms), 0) AS tempo_medio_ms,
            COUNT(DISTINCT usuario) AS usuarios
        FROM nucleai_tokens
        {where}
    ''', params).fetchone()
    return {
        'tokens_total': int(row['tokens_total']),
        'tokens_entrada': int(row['tokens_entrada']),
        'tokens_saida': int(row['tokens_saida']),
        'pedidos': int(row['pedidos']),
        'tempo_medio_ms': round(float(row['tempo_medio_ms']), 1),
        'usuarios': int(row['usuarios']),
    }


def por_modelo(db, periodo=None):
    """Gasto de tokens e pedidos agrupados por modelo."""
    cond, params = _clausula_periodo(periodo)
    where = f'WHERE {cond}' if cond else ''
    rows = db.execute(f'''
        SELECT
            modelo,
            COALESCE(SUM(tokens_total), 0) AS tokens_total,
            COALESCE(SUM(tokens_entrada), 0) AS tokens_entrada,
            COALESCE(SUM(tokens_saida), 0) AS tokens_saida,
            COUNT(*) AS pedidos,
            COALESCE(AVG(tempo_ms), 0) AS tempo_medio_ms
        FROM nucleai_tokens
        {where}
        GROUP BY modelo
        ORDER BY tokens_total DESC, pedidos DESC
    ''', params).fetchall()
    return [dict(r) for r in rows]


def por_dia(db, periodo=None):
    """Gasto de tokens agrupado por dia (YYYY-MM-DD)."""
    cond, params = _clausula_periodo(periodo)
    where = f'WHERE {cond}' if cond else ''
    rows = db.execute(f'''
        SELECT
            substr(criado_em, 1, 10) AS dia,
            COALESCE(SUM(tokens_total), 0) AS tokens_total,
            COALESCE(SUM(tokens_entrada), 0) AS tokens_entrada,
            COALESCE(SUM(tokens_saida), 0) AS tokens_saida,
            COUNT(*) AS pedidos,
            COALESCE(AVG(tempo_ms), 0) AS tempo_medio_ms
        FROM nucleai_tokens
        {where}
        GROUP BY substr(criado_em, 1, 10)
        ORDER BY dia ASC
    ''', params).fetchall()
    return [dict(r) for r in rows]


def por_hora(db, periodo=None):
    """Gasto de tokens agrupado por hora do dia (0 a 23)."""
    cond, params = _clausula_periodo(periodo)
    where = f'WHERE {cond}' if cond else ''
    rows = db.execute(f'''
        SELECT
            CAST(substr(criado_em, 12, 2) AS INTEGER) AS hora,
            COALESCE(SUM(tokens_total), 0) AS tokens_total,
            COUNT(*) AS pedidos
        FROM nucleai_tokens
        {where}
        GROUP BY CAST(substr(criado_em, 12, 2) AS INTEGER)
        ORDER BY hora ASC
    ''', params).fetchall()
    mapa = {int(r['hora']): dict(r) for r in rows if r['hora'] is not None}
    saida = []
    for h in range(24):
        if h in mapa:
            saida.append(mapa[h])
        else:
            saida.append({'hora': h, 'tokens_total': 0, 'pedidos': 0})
    return saida


def por_usuario(db, periodo=None):
    """Gasto de tokens agrupado por usuário."""
    cond, params = _clausula_periodo(periodo)
    where = f'WHERE {cond}' if cond else ''
    rows = db.execute(f'''
        SELECT
            usuario,
            COALESCE(SUM(tokens_total), 0) AS tokens_total,
            COALESCE(SUM(tokens_entrada), 0) AS tokens_entrada,
            COALESCE(SUM(tokens_saida), 0) AS tokens_saida,
            COUNT(*) AS pedidos,
            COALESCE(AVG(tempo_ms), 0) AS tempo_medio_ms
        FROM nucleai_tokens
        {where}
        GROUP BY usuario
        ORDER BY tokens_total DESC, pedidos DESC
    ''', params).fetchall()
    return [dict(r) for r in rows]


def maiores_pedidos(db, periodo=None, limite=10):
    """Lista dos maiores pedidos de tokens no período."""
    cond, params = _clausula_periodo(periodo)
    where = f'WHERE {cond}' if cond else ''
    params_query = list(params) + [limite]
    rows = db.execute(f'''
        SELECT
            id,
            criado_em,
            usuario,
            modelo,
            tokens_total,
            tokens_entrada,
            tokens_saida,
            tempo_ms,
            teste
        FROM nucleai_tokens
        {where}
        ORDER BY tokens_total DESC, id DESC
        LIMIT ?
    ''', params_query).fetchall()
    return [dict(r) for r in rows]


def histograma_pedidos(db, periodo=None):
    """Distribuição de pedidos por faixa de gasto de tokens."""
    cond, params = _clausula_periodo(periodo)
    where = f'WHERE {cond}' if cond else ''
    rows = db.execute(f'''
        SELECT
            tokens_total
        FROM nucleai_tokens
        {where}
    ''', params).fetchall()
    faixas = [
        ('Até 100', 0, 100),
        ('101–300', 101, 300),
        ('301–600', 301, 600),
        ('601–1200', 601, 1200),
        ('1201–2500', 1201, 2500),
        ('> 2500', 2501, 999999999)
    ]
    contagens = {f[0]: {'faixa': f[0], 'pedidos': 0, 'tokens_total': 0} for f in faixas}
    for r in rows:
        t = int(r['tokens_total'] or 0)
        for nome, ini, fim in faixas:
            if ini <= t <= fim:
                contagens[nome]['pedidos'] += 1
                contagens[nome]['tokens_total'] += t
                break
    return list(contagens.values())


def indicadores_saude(db):
    """Indicadores de saúde da NucleAI para o painel de gerência."""
    from . import nucleai_ia as ia, nucleai_trocas, llm
    est = ia.estado(db)
    ativo = ia.cfg(db, 'nucleai_llm_ativo') == '1'
    ligada = ia.ia_ligada(db)

    if est == ia.DESATIVADA or not ativo:
        estado_rotulo = 'Desligada'
    elif est == ia.LIBERADA:
        estado_rotulo = 'Ligada para os usuários'
    else:
        estado_rotulo = 'Em teste — só gerência'

    hoje_str = date.today().strftime('%Y-%m-%d')
    hoje_inicio = hoje_str + ' 00:00:00'

    # 1. Última resposta OK
    r_ok = db.execute('''
        SELECT criado_em FROM nucleai_llm_log
        WHERE modo='IA' AND resposta NOT LIKE 'Erro:%' AND resposta NOT LIKE 'Queda:%'
        ORDER BY id DESC LIMIT 1
    ''').fetchone()
    if not r_ok:
        r_ok = db.execute('SELECT criado_em FROM nucleai_tokens ORDER BY id DESC LIMIT 1').fetchone()
    ult_ok = r_ok['criado_em'] if r_ok else '—'

    # 2. Tempo médio de resposta (hoje)
    t_hoje = db.execute('''
        SELECT AVG(tempo_ms) as media_ms FROM nucleai_tokens
        WHERE criado_em >= ?
    ''', (hoje_inicio,)).fetchone()
    if t_hoje and t_hoje['media_ms'] is not None and t_hoje['media_ms'] > 0:
        ms = round(float(t_hoje['media_ms']))
        tempo_medio_hoje = f'{ms} ms' if ms < 1000 else f'{ms/1000:.1f} s'
    else:
        tempo_medio_hoje = '—'

    # 3. Taxa de erro (hoje)
    tot_logs = db.execute('''
        SELECT COUNT(*) FROM nucleai_llm_log
        WHERE criado_em >= ? AND modo IN ('IA', 'REGRAS')
    ''', (hoje_inicio,)).fetchone()[0]
    erros_logs = db.execute('''
        SELECT COUNT(*) FROM nucleai_llm_log
        WHERE criado_em >= ? AND (modo='REGRAS' OR resposta LIKE 'Erro:%' OR resposta LIKE 'Queda:%')
    ''', (hoje_inicio,)).fetchone()[0]
    if tot_logs > 0:
        taxa_erro = f'{(erros_logs / tot_logs) * 100:.1f}%'
    else:
        taxa_erro = '0%'

    # 4. Modelos em pausa por cota
    pausados = ia.pausas(db)
    qtd_pausa = len(pausados)

    # 5. Trocas de hoje (usando nucleai_trocas.listar)
    trocas_hoje_lista = nucleai_trocas.listar(db, periodo='hoje')
    qtd_trocas_hoje = len(trocas_hoje_lista)

    # 6. Chave configurada sim/não
    try:
        tem_chave = bool(llm.chave(db))
    except Exception:
        tem_chave = False

    return {
        'estado': est,
        'estado_rotulo': estado_rotulo,
        'ativo': ativo,
        'ligada': ligada,
        'ultima_resposta_ok': ult_ok,
        'tempo_medio_hoje': tempo_medio_hoje,
        'taxa_erro': taxa_erro,
        'modelos_pausa': qtd_pausa,
        'pausas_detalhe': pausados,
        'trocas_hoje': qtd_trocas_hoje,
        'tem_chave': tem_chave,
    }


# ------------------------------------------------------------------ Gráficos em SVG puro animado

def svg_grafico_barras(itens, rotulo_chave, valor_chave, titulo='', max_h=230, larg_total=560,
                       sufixo='', max_larg_barra=46):
    """Gera string SVG de gráfico de barras animado com classes do tema."""
    if not itens:
        return ('<div class="ajuda" style="padding:32px 0;text-align:center">'
                'Nenhum dado registrado para este gráfico.</div>')

    W, H = larg_total, max_h
    ml, mr, mt, mb = 48, 16, 24, 44
    valores = [max(0, int(i.get(valor_chave, 0))) for i in itens]
    max_val = max(max(valores), 1)

    def escala_y(v):
        return mt + (H - mt - mb) * (1 - (v / max_val))

    partes = [
        f'<svg viewBox="0 0 {W} {H}" class="nia-graf" role="img" aria-label="{html.escape(titulo)}">'
    ]

    # Grade horizontal (4 níveis)
    for i in range(5):
        val_grade = int((max_val * i) / 4)
        y = escala_y(val_grade)
        partes.append(f'<line x1="{ml}" x2="{W - mr}" y1="{y:.1f}" y2="{y:.1f}" class="g-grade" />')
        partes.append(
            f'<text x="{ml - 8}" y="{y + 4:.1f}" class="g-eixo" text-anchor="end">'
            f'{_formatar_num(val_grade)}</text>'
        )

    # Barras
    qtd = len(itens)
    passo = (W - ml - mr) / qtd
    larg_barra = max(6, min(max_larg_barra, passo * 0.65))

    for idx, item in enumerate(itens):
        v = max(0, int(item.get(valor_chave, 0)))
        rotulo_bruto = str(item.get(rotulo_chave, ''))
        # Encurtar slugs longos como google/gemini-2.5-flash
        if '/' in rotulo_bruto and len(rotulo_bruto) > 16:
            rotulo_curto = rotulo_bruto.split('/')[-1]
        else:
            rotulo_curto = rotulo_bruto
        if len(rotulo_curto) > 14:
            rotulo_exib = rotulo_curto[:13] + '…'
        else:
            rotulo_exib = rotulo_curto

        x = ml + passo * idx + (passo - larg_barra) / 2
        y = escala_y(v)
        altura_barra = max(2, H - mb - y)
        delay = idx * 40

        partes.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{larg_barra:.1f}" height="{altura_barra:.1f}" '
            f'rx="4" class="g-barra" style="animation-delay:{delay}ms">'
            f'<title>{html.escape(rotulo_bruto)}: {_formatar_num(v)} {sufixo}</title>'
            f'</rect>'
        )

        # Rótulo de valor sobre a barra se houver espaço
        if v > 0 and passo >= 28:
            partes.append(
                f'<text x="{x + larg_barra / 2:.1f}" y="{max(mt + 10, y - 5):.1f}" '
                f'class="g-valor" text-anchor="middle">{_formatar_num(v)}</text>'
            )

        # Rótulo do eixo X
        pulo = max(1, qtd // 14)
        if idx % pulo == 0 or qtd <= 12:
            partes.append(
                f'<text x="{x + larg_barra / 2:.1f}" y="{H - mb + 16:.1f}" '
                f'class="g-eixo" text-anchor="middle">{html.escape(rotulo_exib)}</text>'
            )

    partes.append('</svg>')
    return '\n'.join(partes)


def svg_grafico_linhas(itens, rotulo_chave, valor_chave, titulo='', max_h=230, larg_total=560,
                       sufixo=''):
    """Gera string SVG de gráfico de linha com área sombreada animada."""
    if not itens:
        return ('<div class="ajuda" style="padding:32px 0;text-align:center">'
                'Nenhum dado registrado para este gráfico.</div>')

    W, H = larg_total, max_h
    ml, mr, mt, mb = 48, 16, 24, 44
    valores = [max(0, int(i.get(valor_chave, 0))) for i in itens]
    max_val = max(max(valores), 1)

    def escala_y(v):
        return mt + (H - mt - mb) * (1 - (v / max_val))

    partes = [
        f'<svg viewBox="0 0 {W} {H}" class="nia-graf" role="img" aria-label="{html.escape(titulo)}">'
    ]

    # Grade horizontal
    for i in range(5):
        val_grade = int((max_val * i) / 4)
        y = escala_y(val_grade)
        partes.append(f'<line x1="{ml}" x2="{W - mr}" y1="{y:.1f}" y2="{y:.1f}" class="g-grade" />')
        partes.append(
            f'<text x="{ml - 8}" y="{y + 4:.1f}" class="g-eixo" text-anchor="end">'
            f'{_formatar_num(val_grade)}</text>'
        )

    qtd = len(itens)
    passo = (W - ml - mr - 16) / max(1, qtd - 1) if qtd > 1 else 0

    pts_linha = []
    pts_pontos = []

    for idx, item in enumerate(itens):
        v = max(0, int(item.get(valor_chave, 0)))
        rotulo_bruto = str(item.get(rotulo_chave, ''))
        x = (ml + 8) if qtd == 1 else (ml + 8 + passo * idx)
        y = escala_y(v)

        pts_linha.append(f'{x:.1f},{y:.1f}')
        pts_pontos.append((x, y, rotulo_bruto, v, idx))

    # Polígono sombreado abaixo da linha
    if len(pts_linha) > 1:
        x_primeiro = pts_pontos[0][0]
        x_ultimo = pts_pontos[-1][0]
        y_base = H - mb
        faixa_pts = pts_linha + [f'{x_ultimo:.1f},{y_base:.1f}', f'{x_primeiro:.1f},{y_base:.1f}']
        partes.append(f'<polygon points="{" ".join(faixa_pts)}" class="g-faixa" />')

    # Polilinha da série
    partes.append(f'<polyline points="{" ".join(pts_linha)}" class="g-linha real" />')

    # Pontos circulares e rótulos do eixo X
    pulo = max(1, qtd // 10)
    for x, y, rot, v, idx in pts_pontos:
        delay = 200 + idx * 30
        partes.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" class="g-ponto real" style="animation-delay:{delay}ms">'
            f'<title>{html.escape(rot)}: {_formatar_num(v)} {sufixo}</title>'
            f'</circle>'
        )

        if idx % pulo == 0 or idx == qtd - 1:
            rot_curto = rot[5:] if len(rot) == 10 and rot[4] == '-' else rot
            partes.append(
                f'<text x="{x:.1f}" y="{H - mb + 16:.1f}" class="g-eixo" text-anchor="middle">'
                f'{html.escape(rot_curto)}</text>'
            )

    partes.append('</svg>')
    return '\n'.join(partes)
