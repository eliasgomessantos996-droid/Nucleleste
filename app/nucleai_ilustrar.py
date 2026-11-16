"""Blocos visuais ("Ilustrar") gerados exclusivamente pela NucleAI no chat.

Tipos suportados:
- planilha: tabela ordenável no navegador e exportável em Excel (.xlsx).
- grafico: barras, linhas, pizza ou rosca em SVG puro animado.
- cartao_info: cartão informativo com ícone do sprite e pares rótulo/valor.
- cartao_decisao: pergunta Sim/Não vinculada ao mecanismo de pendente/confirmação.
- cartao_permissao: resumo do que vai mudar e de quem precisa autorizar.
Qualquer tipo desconhecido cai em texto simples seguro.
"""
import html
import json
import math
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from . import relatorio_base

TIPOS_SUPORTADOS = ('planilha', 'grafico', 'cartao_info', 'cartao_decisao', 'cartao_permissao')
MODOS_GRAFICO = ('barras', 'linhas', 'pizza', 'rosca')

MAX_LINHAS = 500
MAX_COLUNAS = 30
MAX_TITULO = 200
MAX_SUBTITULO = 300
MAX_RODAPE = 400
MAX_CAB = 120
MAX_CELULA = 500
MAX_SERIES = 6
MAX_PONTOS = 60
MAX_ITENS = 50
MAX_AUTORIZADORES = 20
MAX_TEXTO_FALLBACK = 2000

ICONES_VALIDOS = frozenset({
    'atom', 'award', 'badge-check', 'badge-dollar-sign', 'banknote', 'book-user', 'bot',
    'bug', 'calculator', 'calendar', 'calendar-days', 'calendar-range', 'calendar-x',
    'chart-column', 'check', 'circle-check', 'circle-help', 'circle-x', 'clipboard-check',
    'clipboard-list', 'clipboard-plus', 'clock', 'cloud-upload', 'contact', 'credit-card',
    'database-backup', 'file-chart-column', 'file-down', 'file-text', 'files',
    'flask-conical', 'folder-archive', 'folder-open', 'folder-tree', 'gauge', 'git-branch',
    'grid-2x2', 'handshake', 'heart-pulse', 'history', 'house', 'inbox', 'kanban',
    'layout-dashboard', 'layout-grid', 'lightbulb', 'list-checks', 'log-in',
    'message-square', 'network', 'notebook-pen', 'palette', 'pen-line', 'pill',
    'radiation', 'receipt', 'refresh-cw', 'repeat', 'rotate-ccw', 'scroll-text', 'send',
    'settings', 'settings-2', 'shield', 'shield-check', 'shield-half', 'shield-plus',
    'star', 'stethoscope', 'syringe', 'timer', 'trending-up', 'triangle-alert', 'undo-2',
    'upload', 'user-cog', 'user-round', 'users', 'wallet', 'workflow', 'x',
})

_ALIAS_MODO = {
    'barra': 'barras',
    'barras': 'barras',
    'bar': 'barras',
    'coluna': 'barras',
    'colunas': 'barras',
    'linha': 'linhas',
    'linhas': 'linhas',
    'line': 'linhas',
    'pizza': 'pizza',
    'pie': 'pizza',
    'torta': 'pizza',
    'rosca': 'rosca',
    'donut': 'rosca',
    'anel': 'rosca',
}

_BORDA_CEL_XLSX = Border(
    left=Side('thin', color='D8DFDA'),
    right=Side('thin', color='D8DFDA'),
    bottom=Side('thin', color='D8DFDA'),
)


def _agora():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _texto(valor, limite=MAX_CELULA):
    """Converte em texto plano seguro: corta no limite e escapa HTML."""
    if valor is None:
        return ''
    s = str(valor).replace('\r\n', '\n').replace('\r', '\n').strip()
    if len(s) > limite:
        s = s[:limite]
    return html.escape(s, quote=True)


def _numero(valor):
    """Devolve int/float finito ou None (ignora bool)."""
    if isinstance(valor, bool) or valor is None:
        return None
    if isinstance(valor, (int, float)):
        return valor if math.isfinite(valor) else None
    if isinstance(valor, str):
        bruto = valor.strip().replace(' ', '')
        if not bruto:
            return None
        # aceita formato brasileiro simples (1.234,56) ou ponto (1234.56)
        if ',' in bruto and '.' in bruto:
            bruto = bruto.replace('.', '').replace(',', '.')
        elif ',' in bruto:
            bruto = bruto.replace(',', '.')
        try:
            n = float(bruto)
        except ValueError:
            return None
        if not math.isfinite(n):
            return None
        return int(n) if n.is_integer() else n
    return None


def _celula_planilha(valor):
    if isinstance(valor, bool):
        return _texto('Sim' if valor else 'Não', MAX_CELULA)
    if isinstance(valor, (int, float)) and math.isfinite(valor):
        return int(valor) if isinstance(valor, float) and valor.is_integer() else valor
    return _texto(valor, MAX_CELULA)


def _icone_seguro(nome, padrao='clipboard-list'):
    n = str(nome or '').strip().lower()
    if n.startswith('i-'):
        n = n[2:]
    return n if n in ICONES_VALIDOS else padrao


def _preparar_planilha(args):
    cols_brutas = args.get('colunas')
    linhas_brutas = args.get('linhas')
    if not isinstance(linhas_brutas, list):
        linhas_brutas = []
    linhas_brutas = linhas_brutas[:MAX_LINHAS]

    chaves_orig = []
    colunas = []
    if isinstance(cols_brutas, list) and cols_brutas:
        for idx, c in enumerate(cols_brutas[:MAX_COLUNAS]):
            if isinstance(c, dict):
                chave = c.get('chave') or c.get('campo') or c.get('rotulo') or c.get('nome') or f'Coluna {idx + 1}'
                rot = c.get('rotulo') or c.get('nome') or c.get('titulo') or chave
            else:
                chave = c
                rot = c
            chaves_orig.append(str(chave))
            colunas.append(_texto(rot, MAX_CAB) or f'Col {idx + 1}')
    elif linhas_brutas:
        primeiro = linhas_brutas[0]
        if isinstance(primeiro, dict):
            for k in list(primeiro.keys())[:MAX_COLUNAS]:
                chaves_orig.append(str(k))
                colunas.append(_texto(k, MAX_CAB) or 'Coluna')
        elif isinstance(primeiro, (list, tuple)):
            n_cols = min(MAX_COLUNAS, max((len(r) for r in linhas_brutas if isinstance(r, (list, tuple))), default=0))
            for i in range(n_cols):
                colunas.append(f'Coluna {i + 1}')

    n_cols = len(colunas)
    linhas = []
    if n_cols > 0:
        for r in linhas_brutas:
            if isinstance(r, dict):
                row = [_celula_planilha(r.get(k, '')) for k in chaves_orig[:n_cols]]
            elif isinstance(r, (list, tuple)):
                row = [_celula_planilha(r[i]) if i < len(r) else '' for i in range(n_cols)]
            else:
                row = [_celula_planilha(r)] + [''] * (n_cols - 1)
            linhas.append(row)

    return {'colunas': colunas, 'linhas': linhas}


def _preparar_grafico(args):
    modo_raw = str(args.get('modo') or args.get('formato') or 'barras').strip().lower()
    modo = _ALIAS_MODO.get(modo_raw, 'barras')
    unidade = _texto(args.get('unidade') or '', 30)

    rotulos_raw = args.get('rotulos') or args.get('categorias')
    series_raw = args.get('series')
    itens_raw = args.get('itens') or args.get('pontos')

    rotulos = []
    series = []

    if isinstance(series_raw, list) and series_raw:
        if isinstance(rotulos_raw, list):
            rotulos = [_texto(r, MAX_CAB) or f'#{i + 1}' for i, r in enumerate(rotulos_raw[:MAX_PONTOS])]
        for s_idx, s in enumerate(series_raw[:MAX_SERIES]):
            if not isinstance(s, dict):
                continue
            nome = _texto(s.get('nome') or s.get('rotulo') or f'Série {s_idx + 1}', MAX_CAB)
            vals_raw = s.get('valores') if isinstance(s.get('valores'), list) else []
            vals = []
            for v in vals_raw[:MAX_PONTOS]:
                n = _numero(v)
                vals.append(n if n is not None else 0)
            series.append({'nome': nome, 'valores': vals})
        if not rotulos and series:
            max_pts = max((len(s['valores']) for s in series), default=0)
            rotulos = [f'#{i + 1}' for i in range(max_pts)]
        for s in series:
            while len(s['valores']) < len(rotulos):
                s['valores'].append(0)
            s['valores'] = s['valores'][:len(rotulos)]
    elif isinstance(itens_raw, list) and itens_raw:
        vals = []
        for idx, it in enumerate(itens_raw[:MAX_PONTOS]):
            if isinstance(it, dict):
                rot = _texto(it.get('rotulo') or it.get('nome') or it.get('label') or f'#{idx + 1}', MAX_CAB)
                n = _numero(it.get('valor') if 'valor' in it else it.get('total'))
            elif isinstance(it, (list, tuple)) and len(it) >= 2:
                rot = _texto(it[0], MAX_CAB) or f'#{idx + 1}'
                n = _numero(it[1])
            else:
                continue
            rotulos.append(rot)
            vals.append(n if n is not None else 0)
        series.append({'nome': _texto(args.get('serie_nome') or 'Valor', MAX_CAB), 'valores': vals})
    elif isinstance(rotulos_raw, list) and isinstance(args.get('valores'), list):
        rotulos = [_texto(r, MAX_CAB) or f'#{i + 1}' for i, r in enumerate(rotulos_raw[:MAX_PONTOS])]
        vals_raw = args.get('valores')[:len(rotulos)]
        vals = [(_numero(v) if _numero(v) is not None else 0) for v in vals_raw]
        while len(vals) < len(rotulos):
            vals.append(0)
        series.append({'nome': _texto(args.get('serie_nome') or 'Valor', MAX_CAB), 'valores': vals})

    if modo in ('pizza', 'rosca') and len(series) > 1:
        series = series[:1]

    return {'modo': modo, 'unidade': unidade, 'rotulos': rotulos, 'series': series}


def _pares_itens(brutos, limite=MAX_ITENS):
    itens = []
    if isinstance(brutos, dict):
        brutos = [{'rotulo': k, 'valor': v} for k, v in brutos.items()]
    if not isinstance(brutos, list):
        return itens
    for it in brutos[:limite]:
        if isinstance(it, dict):
            rot = _texto(it.get('rotulo') or it.get('chave') or it.get('nome') or it.get('label') or '', MAX_CAB)
            val = _texto(it.get('valor') if 'valor' in it else it.get('texto', ''), MAX_CELULA)
            destaque = bool(it.get('destaque'))
            if rot or val:
                itens.append({'rotulo': rot, 'valor': val, 'destaque': destaque})
        elif isinstance(it, (list, tuple)) and len(it) >= 2:
            rot = _texto(it[0], MAX_CAB)
            val = _texto(it[1], MAX_CELULA)
            if rot or val:
                itens.append({'rotulo': rot, 'valor': val, 'destaque': False})
        else:
            t = _texto(it, MAX_CELULA)
            if t:
                itens.append({'rotulo': '', 'valor': t, 'destaque': False})
    return itens


def _preparar_cartao_info(args):
    icone = _icone_seguro(args.get('icone'), 'clipboard-list')
    destaque = _texto(args.get('destaque') or args.get('status') or '', 80)
    itens = _pares_itens(args.get('itens') or args.get('campos') or args.get('pares'))
    return {'icone': icone, 'destaque': destaque, 'itens': itens}


def _preparar_cartao_decisao(args, titulo):
    pergunta = _texto(args.get('pergunta') or titulo or 'Deseja confirmar esta ação?', 500)
    detalhes = _pares_itens(args.get('detalhes') or args.get('itens'), limite=12)
    rotulo_sim = _texto(args.get('rotulo_sim') or 'Sim', 40) or 'Sim'
    rotulo_nao = _texto(args.get('rotulo_nao') or 'Não', 40) or 'Não'
    risco_raw = str(args.get('risco') or 'medio').strip().lower()
    risco = risco_raw if risco_raw in ('baixo', 'medio', 'alto') else 'medio'
    return {
        'pergunta': pergunta,
        'detalhes': detalhes,
        'rotulo_sim': rotulo_sim,
        'rotulo_nao': rotulo_nao,
        'risco': risco,
    }


def _preparar_cartao_permissao(args):
    alvo = _texto(args.get('alvo') or args.get('usuario') or '', 120)
    acao = _texto(args.get('acao') or '', 200)

    aut_bruto = args.get('autorizadores') or args.get('quem_autoriza') or args.get('aprovadores') or []
    if isinstance(aut_bruto, str):
        aut_bruto = [aut_bruto]
    autorizadores = []
    if isinstance(aut_bruto, list):
        for a in aut_bruto[:MAX_AUTORIZADORES]:
            if isinstance(a, dict):
                nome = _texto(a.get('nome') or a.get('cargo') or a.get('papel') or '', MAX_CAB)
                cargo = _texto(a.get('cargo') or a.get('papel') or '', MAX_CAB) if a.get('nome') else ''
                if nome:
                    autorizadores.append({'nome': nome, 'cargo': cargo})
            else:
                nome = _texto(a, MAX_CAB)
                if nome:
                    autorizadores.append({'nome': nome, 'cargo': ''})

    mudancas = []
    grupos_raw = args.get('grupos') or args.get('mudancas') or args.get('alteracoes') or args.get('o_que_muda') or []
    if isinstance(grupos_raw, str):
        grupos_raw = [grupos_raw]
    restante = MAX_ITENS
    if isinstance(grupos_raw, list):
        # aceita lista plana de mudanças OU grupos {titulo, itens}
        tem_grupo = any(isinstance(g, dict) and isinstance(g.get('itens'), list) for g in grupos_raw)
        if tem_grupo:
            for g in grupos_raw:
                if restante <= 0:
                    break
                if not isinstance(g, dict):
                    continue
                gtit = _texto(g.get('titulo') or 'Alterações', MAX_CAB)
                itens_g = []
                for it in (g.get('itens') or [])[:restante]:
                    norm = _normalizar_item_permissao(it)
                    if norm:
                        itens_g.append(norm)
                        restante -= 1
                if itens_g:
                    mudancas.append({'titulo': gtit, 'itens': itens_g})
        else:
            itens_g = []
            for it in grupos_raw[:restante]:
                norm = _normalizar_item_permissao(it)
                if norm:
                    itens_g.append(norm)
            if itens_g:
                mudancas.append({'titulo': 'O que muda', 'itens': itens_g})

    return {
        'alvo': alvo,
        'acao': acao,
        'autorizadores': autorizadores,
        'grupos': mudancas,
    }


def _normalizar_item_permissao(it):
    if isinstance(it, dict):
        nome = _texto(it.get('nome') or it.get('item') or it.get('campo') or it.get('rotulo') or '', MAX_CAB)
        det = _texto(it.get('detalhe') or it.get('valor') or it.get('descricao') or '', MAX_CELULA)
        tipo_raw = str(it.get('tipo') or it.get('modo') or 'altera').strip().lower()
        if tipo_raw in ('mais', 'add', 'adicionar', 'adiciona', 'libera', '+'):
            tipo = 'mais'
        elif tipo_raw in ('menos', 'rem', 'remover', 'remove', 'bloqueia', 'revoga', '-'):
            tipo = 'menos'
        else:
            tipo = 'altera'
        if not nome and not det:
            return None
        return {'nome': nome or det, 'detalhe': det if nome else '', 'tipo': tipo}
    txt = _texto(it, MAX_CELULA)
    return {'nome': txt, 'detalhe': '', 'tipo': 'altera'} if txt else None


def _preparar_texto_fallback(tipo_orig, args):
    partes = []
    if args.get('texto'):
        partes.append(str(args['texto']))
    elif args.get('pergunta'):
        partes.append(str(args['pergunta']))
    elif args.get('dados') is not None:
        if isinstance(args['dados'], (dict, list)):
            partes.append(json.dumps(args['dados'], ensure_ascii=False))
        else:
            partes.append(str(args['dados']))
    elif args.get('itens'):
        partes.append(json.dumps(args['itens'], ensure_ascii=False))
    elif args.get('linhas'):
        partes.append(json.dumps(args['linhas'], ensure_ascii=False))
    conteudo = _texto('\n'.join(partes) or f'Conteúdo ({tipo_orig})', MAX_TEXTO_FALLBACK)
    return {'texto': conteudo, 'tipo_original': _texto(tipo_orig, 60)}


def preparar(tipo, args):
    """Valida, limita tamanho e escapa HTML de uma ilustração antes de salvar."""
    args = args if isinstance(args, dict) else {}
    tipo_limpo = str(tipo or '').strip().lower()
    titulo = _texto(args.get('titulo') or '', MAX_TITULO)
    subtitulo = _texto(args.get('subtitulo') or '', MAX_SUBTITULO)
    rodape = _texto(args.get('rodape') or '', MAX_RODAPE)

    if tipo_limpo == 'planilha':
        return 'planilha', titulo or 'Planilha', subtitulo, rodape, _preparar_planilha(args)
    if tipo_limpo == 'grafico':
        return 'grafico', titulo or 'Gráfico', subtitulo, rodape, _preparar_grafico(args)
    if tipo_limpo == 'cartao_info':
        return 'cartao_info', titulo or 'Informações', subtitulo, rodape, _preparar_cartao_info(args)
    if tipo_limpo == 'cartao_decisao':
        dados = _preparar_cartao_decisao(args, args.get('titulo') or '')
        return 'cartao_decisao', titulo or 'Confirmação', subtitulo, rodape, dados
    if tipo_limpo == 'cartao_permissao':
        return 'cartao_permissao', titulo or 'Autorização necessária', subtitulo, rodape, _preparar_cartao_permissao(args)
    return 'texto', titulo or 'Resumo', subtitulo, rodape, _preparar_texto_fallback(tipo_limpo, args)


def montar_cartao(iid, subtipo, titulo, subtitulo, rodape, dados, substitui=None, decisao_resp=None):
    cartao = {
        'tipo': 'IA_ILUSTRACAO',
        'id': iid,
        'subtipo': subtipo,
        'titulo': titulo,
        'subtitulo': subtitulo,
        'rodape': rodape,
        'dados': dados,
    }
    if substitui:
        cartao['substitui'] = substitui
    if subtipo == 'cartao_decisao':
        cartao['decisao_resp'] = decisao_resp
    return cartao


def salvar(db, uid, treino, subtipo, titulo, subtitulo, rodape, dados, substitui=None):
    """Persiste a ilustração no banco, vincula eventual substituição e devolve (id, cartao)."""
    sub_id = None
    if substitui is not None and substitui != '':
        try:
            sub_id = int(substitui)
        except (TypeError, ValueError):
            raise ValueError('O campo substitui precisa ser o id numérico do bloco anterior.')
        ant = db.execute(
            'SELECT id FROM nucleai_ilustracoes WHERE id=? AND usuario_id=? AND treino=?',
            (sub_id, uid, 1 if treino else 0),
        ).fetchone()
        if ant is None:
            raise ValueError(f'Não encontrei a ilustração #{sub_id} nesta conversa para substituir.')

    envelope = json.dumps({'subtitulo': subtitulo, 'rodape': rodape, 'dados': dados}, ensure_ascii=False)
    cur = db.execute(
        'INSERT INTO nucleai_ilustracoes (criado_em, usuario_id, treino, tipo, titulo, dados, substitui_id) '
        'VALUES (?,?,?,?,?,?,?)',
        (_agora(), uid, 1 if treino else 0, subtipo, titulo, envelope, sub_id),
    )
    novo_id = cur.lastrowid
    if sub_id:
        db.execute('UPDATE nucleai_ilustracoes SET substituido_por=? WHERE id=?', (novo_id, sub_id))
    db.commit()
    return novo_id, montar_cartao(novo_id, subtipo, titulo, subtitulo, rodape, dados, substitui=sub_id)


def _linha_para_registro(r):
    if r is None:
        return None
    try:
        env = json.loads(r['dados'])
    except ValueError:
        env = {}
    return {
        'id': r['id'],
        'criado_em': r['criado_em'],
        'usuario_id': r['usuario_id'],
        'treino': bool(r['treino']),
        'subtipo': r['tipo'],
        'titulo': r['titulo'],
        'subtitulo': env.get('subtitulo', ''),
        'rodape': env.get('rodape', ''),
        'dados': env.get('dados') if isinstance(env.get('dados'), dict) else {},
        'substitui_id': r['substitui_id'],
        'substituido_por': r['substituido_por'],
        'decisao_resp': r['decisao_resp'],
        'decisao_em': r['decisao_em'],
    }


def atual(db, uid, treino=False, iid=None):
    """Devolve a última ilustração (ou uma específica) da conversa para reordenação/consulta."""
    t_flag = 1 if treino else 0
    if iid is not None and iid != '':
        try:
            iid = int(iid)
        except (TypeError, ValueError):
            return None
        r = db.execute(
            'SELECT * FROM nucleai_ilustracoes WHERE id=? AND usuario_id=? AND treino=?',
            (iid, uid, t_flag),
        ).fetchone()
    else:
        r = db.execute(
            'SELECT * FROM nucleai_ilustracoes WHERE usuario_id=? AND treino=? AND substituido_por IS NULL '
            'ORDER BY id DESC LIMIT 1',
            (uid, t_flag),
        ).fetchone()
        if r is None:
            r = db.execute(
                'SELECT * FROM nucleai_ilustracoes WHERE usuario_id=? AND treino=? ORDER BY id DESC LIMIT 1',
                (uid, t_flag),
            ).fetchone()
    return _linha_para_registro(r)


def responder_decisao(db, uid, treino, resposta):
    """Trava o cartão de decisão aberto mais recente com 'SIM' ou 'NAO' e retorna o id atualizado (ou None)."""
    resp_norm = 'SIM' if resposta is True or str(resposta).upper() == 'SIM' else 'NAO'
    t_flag = 1 if treino else 0
    r = db.execute(
        "SELECT id FROM nucleai_ilustracoes WHERE usuario_id=? AND treino=? AND tipo='cartao_decisao' "
        "AND decisao_resp IS NULL AND substituido_por IS NULL ORDER BY id DESC LIMIT 1",
        (uid, t_flag),
    ).fetchone()
    if r is None:
        return None
    iid = r['id']
    db.execute(
        'UPDATE nucleai_ilustracoes SET decisao_resp=?, decisao_em=? WHERE id=?',
        (resp_norm, _agora(), iid),
    )
    db.commit()
    return iid


def enriquecer_cartao(db, cartao):
    """Sincroniza estado salvo de cartão de decisão (travamento após resposta)."""
    if not isinstance(cartao, dict) or cartao.get('tipo') != 'IA_ILUSTRACAO':
        return cartao
    if cartao.get('subtipo') != 'cartao_decisao':
        return cartao
    iid = cartao.get('id')
    if not iid:
        return cartao
    r = db.execute('SELECT decisao_resp, substituido_por FROM nucleai_ilustracoes WHERE id=?', (iid,)).fetchone()
    if r is not None:
        cartao = dict(cartao)
        cartao['decisao_resp'] = r['decisao_resp']
        if r['substituido_por']:
            cartao['substituido_por'] = r['substituido_por']
    return cartao


def _valor_xlsx(cel):
    if isinstance(cel, (int, float)) and not isinstance(cel, bool):
        return cel
    s = html.unescape(str(cel or ''))
    if s and s[0] in ('=', '+', '@'):
        return "'" + s
    return s


def gerar_excel(db, uid, iid, pode_treino=False):
    """Gera bytes .xlsx de uma planilha ilustrada pertencente ao usuário.

    Devolve `(bytes, nome_arquivo)` ou `None` se não existir/não pertencer/não for planilha.
    Lança `PermissionError` se for de conversa de treinamento e o usuário não tiver `gerencia`.
    """
    r = db.execute(
        'SELECT * FROM nucleai_ilustracoes WHERE id=? AND usuario_id=?',
        (iid, uid),
    ).fetchone()
    if r is None:
        return None
    if r['treino'] and not pode_treino:
        raise PermissionError('Sem permissão para baixar planilha do treinamento.')
    if r['tipo'] != 'planilha':
        return None

    reg = _linha_para_registro(r)
    dados = reg['dados']
    colunas = [html.unescape(str(c)) for c in (dados.get('colunas') or [])]
    linhas = dados.get('linhas') or []
    titulo = html.unescape(str(reg['titulo'] or 'Planilha'))
    subtitulo = html.unescape(str(reg['subtitulo'] or ''))

    wb = Workbook()
    ws = wb.active
    aba = ''.join(ch for ch in titulo if ch not in '[]:*?/\\').strip()[:31] or 'Planilha'
    ws.title = aba

    total_cols = max(len(colunas), 1)
    ult_col = get_column_letter(total_cols)

    ws['A1'] = _valor_xlsx(titulo)
    ws['A1'].font = Font(bold=True, size=13, color=relatorio_base.VERDE_XLSX)
    ws.merge_cells(f'A1:{ult_col}1')

    linha_cab = 3
    if subtitulo:
        ws['A2'] = _valor_xlsx(subtitulo)
        ws['A2'].font = Font(italic=True, size=10, color='5A645F')
        ws.merge_cells(f'A2:{ult_col}2')
        linha_cab = 4

    fill_cab = PatternFill('solid', fgColor=relatorio_base.VERDE_XLSX)
    fill_zebra = PatternFill('solid', fgColor=relatorio_base.ZEBRA_XLSX)
    font_cab = Font(bold=True, color='FFFFFF', size=10)
    font_dado = Font(size=10)

    for idx, col in enumerate(colunas, start=1):
        c = ws.cell(linha_cab, idx, _valor_xlsx(col))
        c.fill = fill_cab
        c.font = font_cab
        c.alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)

    larguras = [max(len(col) + 4, 12) for col in colunas] or [18]
    for r_idx, row in enumerate(linhas, start=1):
        y = linha_cab + r_idx
        zebra = r_idx % 2 == 0
        for c_idx in range(1, total_cols + 1):
            bruto = row[c_idx - 1] if (c_idx - 1) < len(row) else ''
            val = _valor_xlsx(bruto)
            cell = ws.cell(y, c_idx, val)
            cell.font = font_dado
            cell.border = _BORDA_CEL_XLSX
            if zebra:
                cell.fill = fill_zebra
            if isinstance(val, (int, float)):
                cell.alignment = Alignment(horizontal='right', vertical='center')
            else:
                cell.alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)
            larguras[c_idx - 1] = min(max(larguras[c_idx - 1], len(str(val)) + 3), 42)

    for idx, larg in enumerate(larguras, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = larg

    ws.freeze_panes = f'A{linha_cab + 1}'
    nome_arq = f'ilustracao_{iid}.xlsx'
    return relatorio_base.xlsx_bytes(wb), nome_arq
