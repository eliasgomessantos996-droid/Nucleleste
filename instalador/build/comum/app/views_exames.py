"""Lançamento de exames conforme a planilha EXAMES.xlsx: controle de realização (rádio-fármaco, lote, atividade...).

Reaproveita os cadastros de clientes, médicos e convênios; o restante é digitado. A lista e a impressão pintam cada
linha pela cor do tipo do exame, como a planilha (regras editáveis em "Cores dos exames").
"""
import csv
import io
import re
from datetime import date, datetime

from flask import (Blueprint, Response, abort, flash, g, jsonify, redirect, render_template, request, url_for)

from . import admin_obrigatorio, exames_cores, exames_import, login_obrigatorio, util
from .db import agora, get_db

bp = Blueprint('lanc', __name__, url_prefix='/exames-realizados')

LIMITE = 1500
MESES_PT = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro',
            'novembro', 'dezembro']


# ------------------------------------------------------------------ utilidades
def classificador(db=None):
    db = db or get_db()
    return exames_cores.Classificador(db.execute('SELECT * FROM exame_cores WHERE ativo=1 ORDER BY ordem, id').fetchall())


def _tipo_de(cl, exame):
    t = cl.tipo(exame)
    return t[0] if t else 'outros'


def _filtros():
    a = request.args
    mes = (a.get('mes') or '').strip()
    if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])|todos', mes or ''):
        mes = date.today().strftime('%Y-%m')
    de, ate = (a.get('de') or '').strip(), (a.get('ate') or '').strip()
    return {'mes': mes, 'de': de, 'ate': ate, 'q': (a.get('q') or '').strip(), 'tipo': (a.get('tipo') or '').strip(),
            'convenio': (a.get('convenio') or '').strip(), 'medico': (a.get('medico') or '').strip()}


def _where(f, incluir_tipo=True, cl=None, db=None):
    onde, p = ['1=1'], []
    if f['de'] or f['ate']:
        if f['de']:
            onde.append('data>=?'); p.append(f['de'])
        if f['ate']:
            onde.append('data<=?'); p.append(f['ate'])
    elif f['mes'] != 'todos':
        onde.append('substr(data,1,7)=?'); p.append(f['mes'])
    if f['q']:
        q = f['q'].upper()
        onde.append("(UPPER(paciente) LIKE ? OR COALESCE(codigo,'') LIKE ? OR UPPER(COALESCE(lote,'')) LIKE ?)")
        p += ['%' + q + '%', '%' + f['q'] + '%', '%' + q + '%']
    if f['convenio']:
        onde.append('UPPER(COALESCE(convenio,""))=?'); p.append(f['convenio'].upper())
    if f['medico']:
        onde.append('UPPER(COALESCE(medico,"")) LIKE ?'); p.append('%' + f['medico'].upper() + '%')
    if incluir_tipo and f['tipo']:
        db = db or get_db()
        exames = [r[0] for r in db.execute('SELECT DISTINCT COALESCE(exame,"") FROM realizacoes')]
        do_tipo = [e for e in exames if _tipo_de(cl, e) == f['tipo']]
        if not do_tipo:
            onde.append('0=1')
        else:
            onde.append('COALESCE(exame,"") IN (%s)' % ','.join('?' * len(do_tipo))); p += do_tipo
    return ' AND '.join(onde), p


def _linhas(f, cl, limite=LIMITE):
    db = get_db()
    onde, p = _where(f, True, cl, db)
    total = db.execute('SELECT COUNT(*) FROM realizacoes WHERE ' + onde, p).fetchone()[0]
    rows = db.execute('SELECT * FROM realizacoes WHERE %s ORDER BY data DESC, COALESCE(numero,0) DESC, id DESC LIMIT %d'
                      % (onde, limite), p).fetchall()
    return rows, total


def _resumo_tipos(f, cl):
    """Quantos exames de cada tipo no filtro atual (sem o filtro de tipo), para as etiquetas coloridas."""
    db = get_db()
    onde, p = _where(f, False, cl, db)
    cont = {}
    for r in db.execute('SELECT COALESCE(exame,"") e, COUNT(*) n FROM realizacoes WHERE %s GROUP BY e' % onde, p):
        cont[_tipo_de(cl, r['e'])] = cont.get(_tipo_de(cl, r['e']), 0) + r['n']
    saida = []
    for c in cl.cats:
        if cont.get(c[0]):
            saida.append({'chave': c[0], 'rotulo': c[1], 'cor': c[2], 'texto': exames_cores.cor_do_texto(c[2]), 'n': cont[c[0]]})
    if cont.get('outros'):
        saida.append({'chave': 'outros', 'rotulo': 'Outros', 'cor': '', 'texto': '', 'n': cont['outros']})
    return saida


def _idade(r, do_cadastro=None):
    """Idade na data do exame: pelo nascimento da linha; sem ele, pela idade digitada; sem ela, pelo cadastro do paciente."""
    if r['data_nasc']:
        return util.idade_texto(r['data_nasc'], r['data'])
    if r['idade']:
        return r['idade'] + ' anos'
    nasc = (do_cadastro or {}).get(r['id'])
    return util.idade_texto(nasc, r['data']) if nasc else ''


def _nascimentos_do_cadastro(db, rows):
    """{id da realização: data de nascimento do cadastro} das linhas sem nascimento nem idade. Acha o paciente pelo vínculo
    (`cliente_id`) ou, sem vínculo, pelo nome exato quando só há um cadastro com esse nome e nascimento."""
    faltam = [r for r in rows if not r['data_nasc'] and not r['idade']]
    if not faltam:
        return {}
    por_id, por_nome = {}, {}
    ids = sorted({r['cliente_id'] for r in faltam if r['cliente_id']})
    for i in range(0, len(ids), 500):
        parte = ids[i:i + 500]
        for c in db.execute("SELECT id, data_nasc FROM clientes WHERE COALESCE(data_nasc,'')<>'' AND id IN (%s)" % ','.join('?' * len(parte)), parte):
            por_id[c['id']] = c['data_nasc']
    nomes = sorted({(r['paciente'] or '').strip().upper() for r in faltam if not r['cliente_id'] and (r['paciente'] or '').strip()})
    for i in range(0, len(nomes), 500):
        parte = nomes[i:i + 500]
        achados = {}
        for c in db.execute("SELECT UPPER(TRIM(nome)) AS n, data_nasc FROM clientes WHERE COALESCE(data_nasc,'')<>'' "
                            "AND UPPER(TRIM(nome)) IN (%s)" % ','.join('?' * len(parte)), parte):
            achados.setdefault(c['n'], set()).add(c['data_nasc'])
        por_nome.update({n: next(iter(v)) for n, v in achados.items() if len(v) == 1})
    saida = {}
    for r in faltam:
        nasc = por_id.get(r['cliente_id']) if r['cliente_id'] else por_nome.get((r['paciente'] or '').strip().upper())
        if nasc:
            saida[r['id']] = nasc
    return saida


def _decorar(rows, cl, db=None):
    cadastro = _nascimentos_do_cadastro(db, rows) if db is not None else {}
    out = []
    for r in rows:
        chave, rotulo, cor, texto = cl.cor(r['exame'], r['cor_planilha'])
        out.append({'r': r, 'tipo': chave, 'tipo_rotulo': rotulo, 'cor': cor, 'texto': texto, 'idade': _idade(r, cadastro)})
    return out


def _lista_convenios(db):
    return [r['nome'] for r in db.execute('SELECT nome FROM convenios WHERE ativo=1 ORDER BY nome')]


# ------------------------------------------------------------------ lista
@bp.route('')
@login_obrigatorio
def lista():
    db = get_db()
    cl = classificador(db)
    f = _filtros()
    rows, total = _linhas(f, cl)
    convenios = [r[0] for r in db.execute("SELECT DISTINCT UPPER(TRIM(convenio)) c FROM realizacoes "
                                          "WHERE TRIM(COALESCE(convenio,''))<>'' ORDER BY c")]
    meses = [r[0] for r in db.execute('SELECT DISTINCT substr(data,1,7) m FROM realizacoes ORDER BY m DESC LIMIT 36')]
    return render_template('realizacoes.html', itens=_decorar(rows, cl, db), total=total, f=f, tipos=_resumo_tipos(f, cl),
                           convenios=convenios, meses=meses, limite=LIMITE, hoje=date.today().isoformat(),
                           titulo_periodo=_titulo_periodo(f), n_realizacoes=db.execute('SELECT COUNT(*) FROM realizacoes').fetchone()[0])


def _titulo_periodo(f):
    if f['de'] or f['ate']:
        return '%s a %s' % (util.data_br(f['de']) or '…', util.data_br(f['ate']) or '…')
    if f['mes'] == 'todos':
        return 'todos os períodos'
    return '%s de %s' % (MESES_PT[int(f['mes'][5:]) - 1], f['mes'][:4])


@bp.route('/imprimir')
@login_obrigatorio
def imprimir():
    cl = classificador()
    f = _filtros()
    rows, total = _linhas(f, cl, 5000)
    return render_template('realizacoes_imprimir.html', itens=_decorar(rows, cl, get_db()), total=total, f=f, tipos=_resumo_tipos(f, cl),
                           titulo_periodo=_titulo_periodo(f))


@bp.route('/exportar.csv')
@login_obrigatorio
def exportar():
    cl = classificador()
    f = _filtros()
    rows, _ = _linhas(f, cl, 100000)
    cadastro = _nascimentos_do_cadastro(get_db(), rows)
    saida = io.StringIO()
    w = csv.writer(saida, delimiter=';')
    w.writerow(['Nº', 'Data', 'Código', 'Paciente', 'Nascimento', 'Idade', 'Peso', 'Altura', 'Convênio', 'Médico solicitante',
                'CID', 'Rádio', 'Eluição', 'Fármaco', 'Lote', 'Ativ. prescrita', 'Ativ. administrada', 'Exame', 'Tipo',
                'Hora da injeção', 'Hora do exame', 'Responsável', 'Observação'])
    for r in reversed(rows):
        w.writerow([r['numero'] or '', util.data_br(r['data']), r['codigo'] or '', r['paciente'],
                    util.data_br(r['data_nasc'] or cadastro.get(r['id'])), _idade(r, cadastro), r['peso'] if r['peso'] is not None else '',
                    r['altura'] if r['altura'] is not None else '', r['convenio'] or '', r['medico'] or '', r['cid'] or '',
                    r['radio'] or '', r['eluicao'] or '', r['farmaco'] or '', r['lote'] or '', r['ativ_prescrita'] or '',
                    r['ativ_administrada'] or '', r['exame'] or '', cl.cor(r['exame'], r['cor_planilha'])[1],
                    r['hora_injecao'] or '', r['hora_exame'] or '', r['responsavel'] or '', r['obs'] or ''])
    resp = Response('﻿' + saida.getvalue(), mimetype='text/csv; charset=utf-8')
    resp.headers['Content-Disposition'] = 'attachment; filename="exames-realizados-%s.csv"' % date.today().isoformat()
    return resp


# ------------------------------------------------------------------ cadastro / edição
CAMPOS_TEXTO = ['paciente', 'convenio', 'medico', 'cid', 'radio', 'farmaco', 'lote', 'exame', 'responsavel']


def _hora_ok(txt):
    txt = (txt or '').strip()
    if not txt:
        return None
    m = re.fullmatch(r'(\d{1,2}):?(\d{2})', txt)
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        raise ValueError('Hora inválida: use HH:MM.')
    return '%02d:%02d' % (int(m.group(1)), int(m.group(2)))


def _num(txt, rotulo):
    txt = (txt or '').strip()
    if not txt:
        return None
    v = util.para_valor(txt)
    if v is None:
        raise ValueError('%s deve ser um número.' % rotulo)
    return v


def _proximos(db, data):
    ult = db.execute("SELECT codigo, responsavel FROM realizacoes ORDER BY data DESC, COALESCE(numero,0) DESC, id DESC LIMIT 1").fetchone()
    codigo = ''
    if ult and ult['codigo'] and str(ult['codigo']).isdigit():
        codigo = str(int(ult['codigo']) + 1)
    n = db.execute("SELECT COALESCE(MAX(numero),0)+1 FROM realizacoes WHERE substr(data,1,7)=?", (data[:7],)).fetchone()[0]
    return codigo, n, (ult['responsavel'] if ult else '') or ''


@bp.route('/novo', methods=['GET', 'POST'])
@bp.route('/<int:rid>', methods=['GET', 'POST'])
@login_obrigatorio
def editar(rid=None):
    db = get_db()
    r = db.execute('SELECT * FROM realizacoes WHERE id=?', (rid,)).fetchone() if rid else None
    if rid and not r:
        abort(404)
    erro = None
    if request.method == 'POST':
        try:
            f = request.form
            dados = {k: util.maiusculas(f.get(k)) if f.get(k) else None for k in CAMPOS_TEXTO}
            if not dados['paciente']:
                raise ValueError('Informe o paciente.')
            if not dados['exame']:
                raise ValueError('Informe o exame.')
            data = (f.get('data') or '').strip()
            try:
                date.fromisoformat(data)
            except ValueError:
                raise ValueError('Informe a data do exame.') from None
            cliente_id = f.get('cliente_id', type=int)
            if cliente_id and not db.execute('SELECT 1 FROM clientes WHERE id=?', (cliente_id,)).fetchone():
                cliente_id = None
            nasc = (f.get('data_nasc') or '').strip() or None
            if nasc:
                try:
                    date.fromisoformat(nasc)
                except ValueError:
                    raise ValueError('Data de nascimento inválida.') from None
            medico_id = None
            if dados['medico']:
                m = db.execute('SELECT id FROM medicos WHERE UPPER(TRIM(nome))=? LIMIT 1', (dados['medico'].strip(),)).fetchone()
                medico_id = m['id'] if m else None
            numero = f.get('numero', type=int)
            if not numero:
                numero = _proximos(db, data)[1]
            valores = dict(
                data=data, numero=numero, codigo=(f.get('codigo') or '').strip() or None, cliente_id=cliente_id,
                paciente=dados['paciente'], data_nasc=nasc,
                idade=(f.get('idade') or '').strip() or None if not nasc else None,
                peso=_num(f.get('peso'), 'Peso'), altura=_num(f.get('altura'), 'Altura'), convenio=dados['convenio'],
                medico_id=medico_id, medico=dados['medico'], cid=dados['cid'], radio=dados['radio'],
                eluicao=(f.get('eluicao') or '').strip() or None, farmaco=dados['farmaco'], lote=dados['lote'],
                ativ_prescrita=(f.get('ativ_prescrita') or '').strip() or None,
                ativ_administrada=(f.get('ativ_administrada') or '').strip() or None, exame=dados['exame'],
                hora_injecao=_hora_ok(f.get('hora_injecao')), hora_exame=_hora_ok(f.get('hora_exame')),
                responsavel=dados['responsavel'], obs=(f.get('obs') or '').strip() or None)
            quem, quando = g.usuario['usuario'], agora()
            if r:
                sets = ', '.join('%s=?' % k for k in valores)
                db.execute('UPDATE realizacoes SET %s, atualizado_por=?, atualizado_em=? WHERE id=?' % sets,
                           list(valores.values()) + [quem, quando, rid])
            else:
                # exame novo entra no mapa de laudos como "Processando imagem"
                valores.update(origem=None, criado_por=quem, criado_em=quando, laudo_situacao='PROCESSANDO',
                               laudo_atualizado_em=quando)
                aid = f.get('atendimento_id', type=int)   # exame lançado a partir de um atendimento do dia
                if aid and db.execute('SELECT 1 FROM atendimentos WHERE id=?', (aid,)).fetchone() \
                        and not _exame_do_atendimento(db, aid):
                    valores['atendimento_id'] = aid
                db.execute('INSERT INTO realizacoes (%s) VALUES (%s)' % (','.join(valores), ','.join('?' * len(valores))),
                           list(valores.values()))
            db.commit()
            flash('Exame salvo com sucesso!', 'ok')
            if f.get('continuar') and not r:
                return redirect(url_for('lanc.editar', data=data))
            return redirect(url_for('lanc.lista', mes=data[:7]))
        except ValueError as e:
            db.rollback()
            erro = str(e)
            flash(erro, 'erro')
    # valores do formulário
    if request.method == 'POST':
        v = {k: request.form.get(k, '') for k in ('data', 'numero', 'codigo', 'cliente_id', 'paciente', 'data_nasc', 'idade', 'peso',
                                                   'altura', 'convenio', 'medico', 'cid', 'radio', 'eluicao', 'farmaco', 'lote',
                                                   'ativ_prescrita', 'ativ_administrada', 'exame', 'hora_injecao', 'hora_exame',
                                                   'responsavel', 'obs')}
    elif r:
        v = {k: ('' if r[k] is None else r[k]) for k in r.keys()}
    else:
        data = request.args.get('data') or date.today().isoformat()
        codigo, n, resp = _proximos(db, data)
        v = {k: '' for k in ('cliente_id', 'paciente', 'data_nasc', 'idade', 'peso', 'altura', 'convenio', 'medico', 'cid',
                             'radio', 'eluicao', 'farmaco', 'lote', 'ativ_prescrita', 'ativ_administrada', 'exame', 'hora_injecao',
                             'hora_exame', 'obs')}
        v.update(data=data, numero=n, codigo=codigo, responsavel=resp)
        rascunho = _rascunho_do_atendimento(db, request.args.get('atendimento', type=int))
        if rascunho == 'ja_lancado':
            return redirect(url_for('lanc.editar', rid=_exame_do_atendimento(db, request.args.get('atendimento', type=int))))
        if rascunho:
            v.update(rascunho)
    if v.get('data_nasc'):   # com nascimento, a idade é calculada na data do exame (o formulário também recalcula na tela)
        i = util.idade(v['data_nasc'], v.get('data'))
        v['idade'] = '' if i is None else '%d %s' % (i, 'ano' if i == 1 else 'anos')
    cl = classificador(db)
    cats = [{'chave': c[0], 'rotulo': c[1], 'cor': c[2], 'texto': exames_cores.cor_do_texto(c[2]), 'palavras': c[3]} for c in cl.cats]
    medicos = [x[0] for x in db.execute("SELECT DISTINCT TRIM(nome) FROM medicos WHERE TRIM(COALESCE(nome,''))<>'' ORDER BY 1")]
    exames = [x[0] for x in db.execute('SELECT nome FROM exames WHERE ativo=1 ORDER BY ordem, nome')]
    exames += [x[0] for x in db.execute("SELECT exame FROM realizacoes WHERE TRIM(COALESCE(exame,''))<>'' GROUP BY exame "
                                        'ORDER BY COUNT(*) DESC LIMIT 40') if x[0] not in exames]
    atendimento_id = None
    if not r:
        atendimento_id = (request.form.get('atendimento_id') if request.method == 'POST' else request.args.get('atendimento')) or ''
        atendimento_id = int(atendimento_id) if str(atendimento_id).isdigit() else None
    return render_template('realizacao_form.html', r=r, v=v, medicos=medicos, exames=exames, convenios=_lista_convenios(db),
                           cats=cats, cor_atual=cl.cor(v.get('exame'), None)[2] if v.get('exame') else '',
                           atendimento_id=atendimento_id)


def _exame_do_atendimento(db, aid):
    r = db.execute('SELECT id FROM realizacoes WHERE atendimento_id=? ORDER BY id LIMIT 1', (aid,)).fetchone()
    return r['id'] if r else None


def _rascunho_do_atendimento(db, aid):
    """Dados do atendimento da recepção para adiantar o lançamento do exame (continuam sendo registros separados).
    Devolve um dict de campos do formulário, 'ja_lancado' se o atendimento já virou exame, ou None."""
    if not aid:
        return None
    a = db.execute('SELECT * FROM atendimentos WHERE id=?', (aid,)).fetchone()
    if not a:
        return None
    if _exame_do_atendimento(db, aid):
        return 'ja_lancado'
    cli = db.execute('SELECT * FROM clientes WHERE id=?', (a['cliente_id'] or 0,)).fetchone()
    flash('Dados trazidos do atendimento de %s. Complete rádio, lote, atividade e horários.' % a['cliente_nome'], 'aviso')
    return {'data': a['data'] or '', 'cliente_id': a['cliente_id'] or '', 'paciente': a['cliente_nome'] or '',
            'data_nasc': (cli['data_nasc'] if cli and cli['data_nasc'] else ''),
            'convenio': a['convenio'] or (cli['convenio'] if cli else '') or '', 'medico': a['medico'] or '',
            'exame': a['exame'] or ''}


@bp.route('/<int:rid>/excluir', methods=['POST'])
@login_obrigatorio
def excluir(rid):
    db = get_db()
    r = db.execute('SELECT data FROM realizacoes WHERE id=?', (rid,)).fetchone()
    if not r:
        abort(404)
    db.execute('DELETE FROM realizacoes WHERE id=?', (rid,))
    db.commit()
    flash('Lançamento excluído.', 'ok')
    return redirect(url_for('lanc.lista', mes=r['data'][:7]))


@bp.route('/sugestao')
@login_obrigatorio
def sugestao():
    """Dados do último exame do mesmo tipo (rádio, fármaco, lote, eluição, atividade, responsável) para agilizar o lançamento."""
    db = get_db()
    cl = classificador(db)
    exame = request.args.get('exame') or ''
    chave, rotulo, cor, texto = cl.cor(exame, None)
    saida = {'tipo': chave, 'rotulo': rotulo, 'cor': cor, 'texto': texto}
    if chave != 'outros':
        exames = [x[0] for x in db.execute('SELECT DISTINCT COALESCE(exame,"") FROM realizacoes') if _tipo_de(cl, x[0]) == chave]
        if exames:
            ult = db.execute('SELECT * FROM realizacoes WHERE COALESCE(exame,"") IN (%s) AND TRIM(COALESCE(farmaco,""))<>"" '
                             'ORDER BY data DESC, COALESCE(numero,0) DESC, id DESC LIMIT 1' % ','.join('?' * len(exames)), exames).fetchone()
            if ult:
                for k in ('radio', 'eluicao', 'farmaco', 'lote', 'ativ_prescrita', 'ativ_administrada', 'responsavel'):
                    saida[k] = ult[k] or ''
    return jsonify(saida)


# ------------------------------------------------------------------ aba: últimos atendimentos do dia
@bp.route('/do-dia')
@login_obrigatorio
def do_dia():
    """Atendimentos lançados na recepção no dia, do mais recente ao mais antigo. Cada um abre o lançamento do exame
    com os dados já preenchidos (rascunho); o exame continua sendo um registro separado."""
    db = get_db()
    dia = (request.args.get('data') or '').strip()
    try:
        date.fromisoformat(dia)
    except ValueError:
        dia = date.today().isoformat()
    itens = db.execute(
        'SELECT a.*, (SELECT r.id FROM realizacoes r WHERE r.atendimento_id=a.id ORDER BY r.id LIMIT 1) AS exame_id '
        'FROM atendimentos a WHERE a.data=? ORDER BY a.id DESC', (dia,)).fetchall()
    return render_template('realizacoes_do_dia.html', itens=itens, dia=dia, pendentes=sum(1 for a in itens if not a['exame_id']))


# ------------------------------------------------------------------ atendimentos do dia -> exames a realizar
@bp.route('/atendimentos-do-dia', methods=['POST'])
@login_obrigatorio
def atendimentos_dia():
    db = get_db()
    dia = (request.form.get('data') or '').strip()
    try:
        date.fromisoformat(dia)
    except ValueError:
        flash('Informe a data.', 'erro')
        return redirect(url_for('lanc.lista'))
    ats = db.execute('SELECT * FROM atendimentos WHERE data=? AND id NOT IN (SELECT atendimento_id FROM realizacoes '
                     'WHERE atendimento_id IS NOT NULL) ORDER BY id', (dia,)).fetchall()
    codigo, n, resp = _proximos(db, dia)
    criados = 0
    quem, quando = g.usuario['usuario'], agora()
    for a in ats:
        cli = db.execute('SELECT * FROM clientes WHERE id=?', (a['cliente_id'] or 0,)).fetchone()
        med = db.execute('SELECT id FROM medicos WHERE UPPER(TRIM(nome))=? LIMIT 1', ((a['medico'] or '').strip().upper(),)).fetchone()
        db.execute('INSERT INTO realizacoes (data, numero, cliente_id, paciente, data_nasc, convenio, medico_id, medico, exame, '
                   'responsavel, atendimento_id, criado_por, criado_em) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                   (dia, n + criados, a['cliente_id'], a['cliente_nome'], cli['data_nasc'] if cli else None,
                    a['convenio'] or (cli['convenio'] if cli else None), med['id'] if med else None, a['medico'], a['exame'],
                    resp or None, a['id'], quem, quando))
        criados += 1
    db.commit()
    if criados:
        flash('%d exame(s) trazido(s) dos atendimentos de %s. Complete rádio, lote e atividade em cada linha.' % (criados, util.data_br(dia)), 'ok')
    else:
        flash('Não há atendimentos novos em %s para trazer.' % util.data_br(dia), 'aviso')
    return redirect(url_for('lanc.lista', mes=dia[:7], de=dia, ate=dia))


# ------------------------------------------------------------------ cores dos exames
@bp.route('/cores', methods=['GET', 'POST'])
@login_obrigatorio
def cores():
    db = get_db()
    if request.method == 'POST':
        ids = request.form.getlist('id')
        rotulos = request.form.getlist('rotulo')
        cs = request.form.getlist('cor')
        pads = request.form.getlist('padroes')
        ordens = request.form.getlist('ordem')
        ativos = set(request.form.getlist('ativo'))
        for i, rid in enumerate(ids):
            rot, cor = rotulos[i].strip(), cs[i].strip().upper()
            if not rot or not exames_cores.cor_valida(cor):
                continue
            ordem = int(ordens[i]) if ordens[i].strip().lstrip('-').isdigit() else 100
            if rid.isdigit():
                db.execute('UPDATE exame_cores SET rotulo=?, cor=?, padroes=?, ordem=?, ativo=? WHERE id=?',
                           (rot, cor, pads[i].strip(), ordem, 1 if rid in ativos else 0, int(rid)))
            else:
                chave = 'x_' + re.sub(r'[^a-z0-9]+', '_', exames_cores.normalizar(rot).lower()).strip('_')[:40]
                if db.execute('SELECT 1 FROM exame_cores WHERE chave=?', (chave,)).fetchone():
                    chave += '_%d' % (db.execute('SELECT COUNT(*) FROM exame_cores').fetchone()[0] + 1)
                db.execute('INSERT INTO exame_cores (chave, rotulo, cor, padroes, ordem, ativo) VALUES (?,?,?,?,?,1)',
                           (chave, rot, cor, pads[i].strip(), ordem))
        db.commit()
        flash('Cores salvas. Elas já valem na lista, na impressão e na exportação.', 'ok')
        return redirect(url_for('lanc.cores'))
    cl = classificador(db)
    contagem = {}
    for r in db.execute('SELECT COALESCE(exame,"") e, COUNT(*) n FROM realizacoes GROUP BY e'):
        k = _tipo_de(cl, r['e'])
        contagem[k] = contagem.get(k, 0) + r['n']
    linhas = db.execute('SELECT * FROM exame_cores ORDER BY ativo DESC, ordem, id').fetchall()
    return render_template('realizacoes_cores.html', linhas=linhas, contagem=contagem, n_total=db.execute('SELECT COUNT(*) FROM realizacoes').fetchone()[0],
                           texto_de=exames_cores.cor_do_texto)


@bp.route('/importar', methods=['POST'])
@login_obrigatorio
def importar():
    arq = request.files.get('arquivo')
    if not arq or not arq.filename.lower().endswith(('.xlsx', '.xlsm')):
        flash('Escolha o arquivo EXAMES.xlsx.', 'erro')
        return redirect(url_for('lanc.cores'))
    try:
        res = exames_import.importar_xlsx(get_db(), io.BytesIO(arq.read()), g.usuario['usuario'])
    except ValueError as e:
        flash(str(e), 'erro')
        return redirect(url_for('lanc.cores'))
    except Exception as e:  # arquivo corrompido, formato inesperado...
        flash('Não foi possível ler a planilha: %s' % e, 'erro')
        return redirect(url_for('lanc.cores'))
    flash('Planilha importada: %d lançamentos de %d abas (%d ligados a clientes cadastrados, %d a médicos cadastrados).'
          % (res['linhas'], res['abas'], res['com_cliente'], res['com_medico']), 'ok')
    return redirect(url_for('lanc.lista', mes='todos'))
