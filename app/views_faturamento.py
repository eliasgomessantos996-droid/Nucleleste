"""Faturamento em três abas (faturamento, emissão da nota fiscal e recebidas, com a glosa), protocolo em PDF e o dashboard financeiro."""
import io
from datetime import date, timedelta

from flask import Blueprint, abort, flash, g, redirect, render_template, request, send_file, url_for

from . import faturamento as fatu
from . import login_obrigatorio, util
from .db import agora, config_get, get_db
from .views_financeiro import BANCOS

bp = Blueprint('fat', __name__)

MESES = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez']


def _convenios(db):
    return [r['nome'] for r in db.execute('SELECT nome FROM convenios WHERE ativo=1 ORDER BY nome')]


def _usuario():
    return g.usuario['usuario']


def _voltar(padrao):
    """Volta para a tela de onde veio (só caminhos do próprio sistema, dentro de /faturamento)."""
    alvo = request.form.get('voltar') or ''
    return alvo if alvo.startswith('/faturamento') and not alvo.startswith('//') else padrao


def _filtros():
    a = request.args
    return {'status': (a.get('status') or '').strip(), 'convenio': (a.get('convenio') or '').strip(),
            'de': (a.get('de') or '').strip(), 'ate': (a.get('ate') or '').strip(), 'q': (a.get('q') or '').strip()}


def _fatura_ou_404(db, fid):
    try:
        return fatu.obter(db, fid)
    except fatu.ErroFatura:
        abort(404)


# ---------------------------------------------------------------- aba 1: faturamento
@bp.route('/faturamento')
@login_obrigatorio
def lista():
    db = get_db()
    f = _filtros()
    rows = fatu.listar(db, **f)
    return render_template('faturamento.html', rows=rows, tot=fatu.totais(rows), f=f, convenios=_convenios(db), hoje=date.today().isoformat(),
                           rotulos=fatu.ROTULOS)


@bp.route('/faturamento/nova', methods=['GET', 'POST'])
@bp.route('/faturamento/<int:fid>', methods=['GET', 'POST'])
@login_obrigatorio
def editar(fid=None):
    db = get_db()
    fat = _fatura_ou_404(db, fid) if fid else None
    campos = ['convenio', 'referencia', 'valor_bruto', 'protocolo', 'qtd_guias', 'nota_fiscal', 'previsao', 'obs']
    if fat:
        f = {k: (fat[k] if fat[k] is not None else '') for k in campos}
        f['valor_bruto'] = util.moeda(fat['valor_bruto'])
    else:
        f = {k: '' for k in campos}
        f['referencia'] = date.today().replace(day=1).isoformat()
        f['convenio'] = request.args.get('convenio', '')
    if request.method == 'POST':
        f = {k: (request.form.get(k) or '').strip() for k in campos}
        try:
            if fat:
                avisos = fatu.atualizar(db, _usuario(), fid, f)
            else:
                fid, avisos = fatu.criar(db, _usuario(), f)
        except fatu.ErroFatura as e:
            db.rollback()
            flash(str(e), 'erro')
        else:
            for a in avisos:
                flash(a, 'aviso')
            pdf = request.files.get('protocolo_pdf')
            if pdf and pdf.filename:   # o PDF é opcional; se ele falhar, a fatura já está salva e a tela de edição mostra o motivo
                try:
                    fatu.anexar_protocolo(db, _usuario(), fid, pdf.filename, pdf.read(fatu.MAX_PDF + 1))
                except fatu.ErroFatura as e:
                    flash('Fatura salva, mas o PDF não foi importado: %s' % e, 'erro')
                    return redirect(url_for('fat.editar', fid=fid))
            nova = fatu.obter(db, fid)
            flash('Fatura salva: %s.' % ('nota fiscal emitida' if nova['status'] == fatu.NF_EMITIDA else 'faturada, aguardando a emissão da nota fiscal'), 'ok')
            if request.form.get('continuar'):
                return redirect(url_for('fat.editar', convenio=f['convenio']))
            return redirect(url_for('fat.lista'))
    return render_template('fatura_form.html', f=f, fat=fat, convenios=_convenios(db), rotulos=fatu.ROTULOS, max_mb=fatu.MAX_PDF // 1048576)


@bp.route('/faturamento/<int:fid>/excluir', methods=['POST'])
@login_obrigatorio
def excluir(fid):
    db = get_db()
    try:
        fatu.excluir(db, fid)
        flash('Fatura excluída.', 'ok')
    except fatu.ErroFatura as e:
        flash(str(e), 'erro')
    return redirect(url_for('fat.lista'))


# ---------------------------------------------------------------- aba 2: emissão da nota fiscal
@bp.route('/faturamento/emissao')
@login_obrigatorio
def emissao():
    db = get_db()
    f = _filtros()
    pendentes = fatu.listar(db, status=fatu.FATURADO, convenio=f['convenio'], q=f['q'])
    pendentes.sort(key=lambda r: (r['referencia'], r['id']))   # as mais antigas primeiro: são as que esperam há mais tempo
    emitidas = fatu.listar(db, status=fatu.NF_EMITIDA, convenio=f['convenio'], q=f['q'], limite=60)
    return render_template('faturamento_emissao.html', pendentes=pendentes, emitidas=emitidas, f=f, convenios=_convenios(db), hoje=date.today().isoformat(),
                           tot=fatu.totais(pendentes))


@bp.route('/faturamento/<int:fid>/emitir', methods=['POST'])
@login_obrigatorio
def emitir(fid):
    db = get_db()
    try:
        fatu.emitir_nf(db, _usuario(), fid, request.form.get('nota_fiscal'), request.form.get('data_emissao'))
        flash('Nota fiscal emitida: a fatura passou para “Nota fiscal emitida” e já pode receber o pagamento em “Recebidas”.', 'ok')
    except fatu.ErroFatura as e:
        db.rollback()
        flash(str(e), 'erro')
    return redirect(_voltar(url_for('fat.emissao')))


@bp.route('/faturamento/<int:fid>/desfazer-emissao', methods=['POST'])
@login_obrigatorio
def desfazer_emissao(fid):
    db = get_db()
    try:
        fatu.desfazer_emissao(db, _usuario(), fid)
        flash('Emissão desfeita: a fatura voltou para “Faturado (sem nota)”.', 'ok')
    except fatu.ErroFatura as e:
        db.rollback()
        flash(str(e), 'erro')
    return redirect(_voltar(url_for('fat.emissao')))


# ---------------------------------------------------------------- aba 3: recebidas (comparação e glosa)
@bp.route('/faturamento/recebidas')
@login_obrigatorio
def recebidas():
    db = get_db()
    f = _filtros()
    a_receber = fatu.listar(db, status=fatu.NF_EMITIDA, convenio=f['convenio'], de=f['de'], ate=f['ate'], q=f['q'])
    recebidas_ = fatu.listar(db, status=fatu.RECEBIDO, convenio=f['convenio'], de=f['de'], ate=f['ate'], q=f['q'])
    sem_nota = db.execute("SELECT COUNT(*) FROM faturas WHERE status='FATURADO'").fetchone()[0]
    return render_template('faturamento_recebidas.html', a_receber=a_receber, recebidas=recebidas_, f=f, convenios=_convenios(db), bancos=BANCOS,
                           hoje=date.today().isoformat(), tot_receber=fatu.totais(a_receber), tot=fatu.totais(recebidas_), sem_nota=sem_nota)


@bp.route('/faturamento/<int:fid>/quitar', methods=['POST'])
@login_obrigatorio
def quitar(fid):
    db = get_db()
    r = request.form
    try:
        gl = fatu.receber(db, _usuario(), fid, r.get('data_recebimento'), r.get('banco') or '', BANCOS, r.get('bruto_recebido', ''),
                          r.get('tributos', '') if r.get('informar_tributos') else '', r.get('liquido', ''), r.get('obs', ''))
    except fatu.ErroFatura as e:
        db.rollback()
        flash(str(e), 'erro')
    else:
        if gl['sentido'] == 'glosa':
            flash('Recebimento registrado. Glosa: R$ %s (%s%% do faturado).' % (util.moeda(gl['valor']), str(gl['pct']).replace('.', ',')), 'ok')
        elif gl['sentido'] == 'acima':
            flash('Recebimento registrado. Recebido R$ %s a mais que o faturado.' % util.moeda(-gl['valor']), 'ok')
        else:
            flash('Recebimento registrado. Sem glosa: o bruto recebido é igual ao faturado.', 'ok')
    return redirect(_voltar(url_for('fat.recebidas')))


@bp.route('/faturamento/<int:fid>/reabrir', methods=['POST'])
@login_obrigatorio
def reabrir(fid):
    db = get_db()
    try:
        fatu.reabrir(db, _usuario(), fid)
        flash('Recebimento desfeito: a fatura voltou para “A receber”.', 'ok')
    except fatu.ErroFatura as e:
        db.rollback()
        flash(str(e), 'erro')
    return redirect(_voltar(url_for('fat.recebidas')))


# ---------------------------------------------------------------- protocolo em PDF (ver no sistema, baixar, trocar, remover) e resumo da fatura
@bp.route('/faturamento/<int:fid>/protocolo')
@login_obrigatorio
def protocolo(fid):
    db = get_db()
    return render_template('faturamento_protocolo.html', fat=_fatura_ou_404(db, fid), glosa=fatu.glosa(fatu.obter(db, fid)), rotulos=fatu.ROTULOS,
                           max_mb=fatu.MAX_PDF // 1048576)


@bp.route('/faturamento/<int:fid>/protocolo.pdf')
@login_obrigatorio
def protocolo_pdf(fid):
    """O PDF do protocolo: abre dentro do sistema (padrão) ou baixa (`?baixar=1`)."""
    try:
        nome, conteudo = fatu.ler_protocolo(get_db(), fid)
    except fatu.ErroFatura:
        abort(404)
    return send_file(io.BytesIO(conteudo), mimetype='application/pdf', as_attachment=request.args.get('baixar') == '1', download_name=nome)


@bp.route('/faturamento/<int:fid>/protocolo/enviar', methods=['POST'])
@login_obrigatorio
def protocolo_enviar(fid):
    db = get_db()
    _fatura_ou_404(db, fid)
    pdf = request.files.get('protocolo_pdf')
    try:
        if not pdf or not pdf.filename:
            raise fatu.ErroFatura('Escolha o arquivo PDF do protocolo.')
        fatu.anexar_protocolo(db, _usuario(), fid, pdf.filename, pdf.read(fatu.MAX_PDF + 1))
        flash('PDF do protocolo importado.', 'ok')
    except fatu.ErroFatura as e:
        db.rollback()
        flash(str(e), 'erro')
    return redirect(_voltar(url_for('fat.protocolo', fid=fid)))


@bp.route('/faturamento/<int:fid>/protocolo/remover', methods=['POST'])
@login_obrigatorio
def protocolo_remover(fid):
    db = get_db()
    _fatura_ou_404(db, fid)
    fatu.remover_protocolo(db, _usuario(), fid)
    flash('PDF do protocolo removido.', 'ok')
    return redirect(_voltar(url_for('fat.protocolo', fid=fid)))


@bp.route('/faturamento/<int:fid>/resumo.pdf')
@login_obrigatorio
def resumo_pdf(fid):
    """Resumo da fatura gerado pelo sistema (dados, nota, recebimento e glosa), para consulta ou impressão."""
    from . import faturamento_docs
    db = get_db()
    r = _fatura_ou_404(db, fid)
    pdf = faturamento_docs.resumo_pdf(dict(r), fatu.glosa(r), config_get('clinica_nome', ''))
    return send_file(io.BytesIO(pdf), mimetype='application/pdf', as_attachment=request.args.get('baixar') == '1',
                     download_name='fatura-%s-%s.pdf' % (r['protocolo'] or r['id'], r['referencia']))


# ---------------------------------------------------------------- dashboard financeiro
def _meses(de, ate):
    meses, d = [], de.replace(day=1)
    while d <= ate and len(meses) < 60:
        meses.append(d)
        d = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
    return meses


@bp.route('/faturamento/dashboard')
@login_obrigatorio
def dashboard():
    db = get_db()
    hoje = date.today()
    a = request.args
    p = a.get('p') or 'ano'
    de, ate = util.para_data(a.get('de')), util.para_data(a.get('ate'))
    if p == 'custom' and de and ate:
        if de > ate:
            de, ate = ate, de
    elif p == '12m':
        de, ate = (hoje.replace(day=1) - timedelta(days=335)).replace(day=1), hoje
    elif p == 'mes':
        de, ate = hoje.replace(day=1), hoje
    elif p == 'tudo':
        pri = db.execute('SELECT MIN(referencia) FROM faturas').fetchone()[0]
        de, ate = util.para_data(pri) or hoje.replace(month=1, day=1), hoje
    else:
        p, de, ate = 'ano', date(hoje.year, 1, 1), hoje
    convenio = (a.get('convenio') or '').strip()
    where, params = 'referencia BETWEEN ? AND ?', [de.isoformat(), ate.isoformat()]
    if convenio:
        where += ' AND convenio=?'
        params.append(convenio)
    rows = db.execute('SELECT * FROM faturas WHERE ' + where + ' ORDER BY referencia', params).fetchall()

    bruto = sum(r['valor_bruto'] or 0 for r in rows)
    trib = sum(r['tributos'] or 0 for r in rows)
    liquido = sum(r['valor_liquido'] or 0 for r in rows)
    rec_rows = [r for r in rows if r['status'] == 'RECEBIDO']
    ab_rows = [r for r in rows if r['status'] != 'RECEBIDO']
    recebido = sum((r['valor_recebido'] if r['valor_recebido'] is not None else r['valor_liquido']) or 0 for r in rec_rows)
    liquido_rec = sum(r['valor_liquido'] or 0 for r in rec_rows)
    aberto = sum(r['valor_liquido'] or 0 for r in ab_rows)
    glosa = sum(max(0, (r['valor_liquido'] or 0) - (r['valor_recebido'] if r['valor_recebido'] is not None else r['valor_liquido']))
                for r in rec_rows)
    prazos = []
    for r in rec_rows:
        d1, d2 = util.para_data(r['referencia']), util.para_data(r['data_recebimento'])
        if d1 and d2:
            prazos.append((d2 - d1).days)
    prazo_medio = round(sum(prazos) / len(prazos)) if prazos else None
    atrasadas = [r for r in ab_rows if r['previsao'] and r['previsao'] < hoje.isoformat()]

    # por convênio: recebido x em aberto
    por_conv = {}
    for r in rows:
        c = por_conv.setdefault(r['convenio'], {'rotulo': r['convenio'], 'recebido': 0.0, 'aberto': 0.0, 'bruto': 0.0, 'tributos': 0.0, 'n': 0})
        c['n'] += 1
        c['bruto'] += r['valor_bruto'] or 0
        c['tributos'] += r['tributos'] or 0
        if r['status'] == 'RECEBIDO':
            c['recebido'] += (r['valor_recebido'] if r['valor_recebido'] is not None else r['valor_liquido']) or 0
        else:
            c['aberto'] += r['valor_liquido'] or 0
    convenios_lista = sorted(por_conv.values(), key=lambda c: -(c['recebido'] + c['aberto']))
    for c in convenios_lista:
        c['pct_trib'] = round(100 * c['tributos'] / c['bruto'], 1) if c['bruto'] else 0
        for k in ('recebido', 'aberto', 'bruto', 'tributos'):
            c[k] = round(c[k], 2)
    maiores = convenios_lista[:10]
    resto = convenios_lista[10:]
    if resto:
        maiores.append({'rotulo': 'Outros (%d)' % len(resto), 'recebido': round(sum(c['recebido'] for c in resto), 2),
                        'aberto': round(sum(c['aberto'] for c in resto), 2), 'bruto': round(sum(c['bruto'] for c in resto), 2),
                        'tributos': round(sum(c['tributos'] for c in resto), 2), 'n': sum(c['n'] for c in resto), 'resto': True,
                        'pct_trib': 0})

    # evolução mensal: faturado (líquido, pelo mês de referência) x recebido (pelo mês do recebimento)
    meses = _meses(de, ate)
    fat_m, rec_m, trib_m = {}, {}, {}
    for r in rows:
        k = (r['referencia'] or '')[:7]
        fat_m[k] = fat_m.get(k, 0) + (r['valor_liquido'] or 0)
        trib_m[k] = trib_m.get(k, 0) + (r['tributos'] or 0)
        if r['status'] == 'RECEBIDO' and r['data_recebimento']:
            kr = r['data_recebimento'][:7]
            rec_m[kr] = rec_m.get(kr, 0) + ((r['valor_recebido'] if r['valor_recebido'] is not None else r['valor_liquido']) or 0)
    mensal = []
    for m in meses:
        k = '%04d-%02d' % (m.year, m.month)
        mensal.append({'rotulo': '%s/%02d' % (MESES[m.month - 1], m.year % 100), 'dica': '%s de %d' % (MESES[m.month - 1], m.year),
                       'valores': [round(fat_m.get(k, 0), 2), round(rec_m.get(k, 0), 2)]})

    # envelhecimento do que está em aberto (dias desde a referência)
    faixas = [('Até 30 dias', 0, 30), ('31–60 dias', 31, 60), ('61–90 dias', 61, 90), ('Mais de 90 dias', 91, 99999)]
    aging = []
    for nome, lo, hi in faixas:
        v = 0.0
        for r in ab_rows:
            d1 = util.para_data(r['referencia'])
            dias = (hoje - d1).days if d1 else 0
            if lo <= max(dias, 0) <= hi:
                v += r['valor_liquido'] or 0
        aging.append({'rotulo': nome, 'valor': round(v, 2), 'dica': nome})

    abertos_top = sorted(ab_rows, key=lambda r: -(r['valor_liquido'] or 0))[:8]
    dados = {
        'convenios': maiores, 'mensal': mensal, 'aging': aging,
        'composicao': [{'rotulo': 'Recebido', 'valor': round(recebido, 2)}, {'rotulo': 'A receber', 'valor': round(aberto, 2)}],
        'tributos': [{'rotulo': c['rotulo'], 'valor': c['pct_trib']} for c in convenios_lista[:8] if c['bruto']],
    }
    return render_template(
        'faturamento_dashboard.html', dados=dados, p=p, de=de.isoformat(), ate=ate.isoformat(), convenio=convenio,
        convenios=_convenios(db), n=len(rows), bruto=bruto, trib=trib, liquido=liquido, recebido=recebido, aberto=aberto,
        glosa=glosa, prazo_medio=prazo_medio, atrasadas=atrasadas,
        taxa=round(100 * liquido_rec / liquido, 1) if liquido else 0, pct_trib=round(100 * trib / bruto, 1) if bruto else 0,
        abertos_top=abertos_top, hoje=hoje.isoformat(), qtd_rec=len(rec_rows), qtd_ab=len(ab_rows))
