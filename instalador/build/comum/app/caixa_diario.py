"""Caixa diário da empresa: o controle de caixa em planilha (MOVIMENTO DE CAIXA), dentro do sistema.

Regras (as mesmas da planilha):
- Quatro contas, cada uma com saldo que passa de um dia para o outro: Banco do Brasil, Banco Unicred,
  Caixa Econômica Federal e Movimento de caixa (dinheiro em espécie).
- Receita e despesa são lançadas em uma conta. O saldo de cada conta do dia = saldo do dia anterior
  + receitas da conta − despesas da conta. O Saldo Total é a soma das quatro contas.
- Saldo inicial: a partir de uma data-base (saldo de fechamento da planilha do dia anterior), informada uma vez.
- Retiradas retidas (valores separados, fora das contas): o TOTAL é o Saldo Total menos as retidas.
- Tudo é recalculado em cadeia: alterar um lançamento antigo ajusta os dias seguintes.

As cores são as da planilha: Banco do Brasil amarelo, Unicred verde, Caixa azul e Movimento de caixa cinza.
"""
from __future__ import annotations

import datetime as _dt
import io
import re

from .db import agora

TIPOS = {'RECEITA': 'Receita', 'DESPESA': 'Despesa'}
# (código, nome, cor de fundo da planilha)
CONTAS = (
    ('BB', 'Banco do Brasil', 'FFFF99'),
    ('UNICRED', 'Banco Unicred', 'C5E0B4'),
    ('CAIXA', 'Caixa Econômica Federal', 'B4C6E7'),
    ('DINHEIRO', 'Movimento de caixa (dinheiro)', 'D0CECE'),
)
NOMES_CONTA = {c: n for c, n, _ in CONTAS}
COR_CONTA = {c: cor for c, _, cor in CONTAS}


class ErroCaixaDiario(ValueError):
    """Erro de validação mostrado ao usuário."""


def garantir(db):
    """Cria as tabelas do módulo se ainda não existirem (não mexe nas tabelas do resto do sistema)."""
    db.executescript('''
        CREATE TABLE IF NOT EXISTS cxd_inicio (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            data TEXT NOT NULL,
            bb REAL NOT NULL DEFAULT 0, unicred REAL NOT NULL DEFAULT 0,
            caixa REAL NOT NULL DEFAULT 0, dinheiro REAL NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS cxd_lancamentos (
            id INTEGER PRIMARY KEY,
            data TEXT NOT NULL,
            tipo TEXT NOT NULL,
            descricao TEXT NOT NULL,
            valor REAL NOT NULL,
            conta TEXT NOT NULL,
            nf TEXT NOT NULL DEFAULT '',
            obs TEXT NOT NULL DEFAULT '',
            criado_por TEXT, criado_em TEXT, atualizado_por TEXT, atualizado_em TEXT
        );
        CREATE INDEX IF NOT EXISTS ix_cxd_data ON cxd_lancamentos(data);
        CREATE TABLE IF NOT EXISTS cxd_retidas (
            id INTEGER PRIMARY KEY,
            descricao TEXT NOT NULL,
            valor REAL NOT NULL
        );
    ''')


def _dinheiro(txt):
    """Valor digitado (ex.: 1.290,50 ou 1290.5) em reais, com 2 casas. Erro se não for positivo."""
    s = (txt or '').strip().replace('R$', '').replace(' ', '')
    if not s:
        raise ErroCaixaDiario('Informe o valor.')
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    if not re.fullmatch(r'\d+(\.\d{1,2})?', s):
        raise ErroCaixaDiario('Valor inválido: use números, por exemplo 1290,50.')
    valor = round(float(s), 2)
    if valor <= 0:
        raise ErroCaixaDiario('O valor precisa ser maior que zero.')
    return valor


def _data(txt):
    try:
        return _dt.date.fromisoformat((txt or '').strip()).isoformat()
    except ValueError:
        raise ErroCaixaDiario('Data inválida.')


def dados_do_formulario(form):
    """Valida o formulário de um lançamento e devolve os dados prontos para gravar."""
    tipo = (form.get('tipo') or '').upper()
    if tipo not in TIPOS:
        raise ErroCaixaDiario('Escolha receita ou despesa.')
    conta = (form.get('conta') or '').upper()
    if conta not in NOMES_CONTA:
        raise ErroCaixaDiario('Escolha a conta (Banco do Brasil, Unicred, Caixa ou Movimento de caixa).')
    descricao = (form.get('descricao') or '').strip().upper()
    if not descricao:
        raise ErroCaixaDiario('Informe a descrição.')
    return {'data': _data(form.get('data')), 'tipo': tipo, 'descricao': descricao[:200], 'valor': _dinheiro(form.get('valor')),
            'conta': conta, 'nf': (form.get('nf') or '').strip()[:40], 'obs': (form.get('obs') or '').strip()[:300]}


def inicio(db):
    return db.execute('SELECT * FROM cxd_inicio WHERE id=1').fetchone()


def definir_inicio(db, form, usuario):
    """Saldos de cada conta no fim do dia anterior à data-base (vêm da planilha do dia anterior)."""
    data = _data(form.get('data'))
    valores = {}
    for campo in ('bb', 'unicred', 'caixa', 'dinheiro'):
        bruto = (form.get(campo) or '0').strip() or '0'
        bruto = bruto.replace('R$', '').replace(' ', '')
        if ',' in bruto:
            bruto = bruto.replace('.', '').replace(',', '.')
        try:
            valores[campo] = round(float(bruto), 2)
        except ValueError:
            raise ErroCaixaDiario('Saldo inválido em %s.' % campo)
    db.execute('INSERT INTO cxd_inicio (id, data, bb, unicred, caixa, dinheiro) VALUES (1,?,?,?,?,?) '
               'ON CONFLICT(id) DO UPDATE SET data=excluded.data, bb=excluded.bb, unicred=excluded.unicred, '
               'caixa=excluded.caixa, dinheiro=excluded.dinheiro',
               (data, valores['bb'], valores['unicred'], valores['caixa'], valores['dinheiro']))
    db.commit()
    return data


def lancar(db, dados, usuario):
    ini = inicio(db)
    if ini is None:
        raise ErroCaixaDiario('Informe primeiro os saldos iniciais (botão Saldos iniciais).')
    if dados['data'] < ini['data']:
        raise ErroCaixaDiario('A data é anterior ao saldo inicial (%s).' % _br(ini['data']))
    agora_txt = agora()
    cur = db.execute('INSERT INTO cxd_lancamentos (data, tipo, descricao, valor, conta, nf, obs, criado_por, criado_em, '
                     'atualizado_por, atualizado_em) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                     (dados['data'], dados['tipo'], dados['descricao'], dados['valor'], dados['conta'], dados['nf'], dados['obs'],
                      usuario, agora_txt, usuario, agora_txt))
    db.commit()
    return cur.lastrowid


def atualizar(db, lid, dados, usuario):
    existe = db.execute('SELECT id FROM cxd_lancamentos WHERE id=?', (lid,)).fetchone()
    if existe is None:
        raise ErroCaixaDiario('Lançamento não encontrado.')
    db.execute('UPDATE cxd_lancamentos SET data=?, tipo=?, descricao=?, valor=?, conta=?, nf=?, obs=?, atualizado_por=?, atualizado_em=? '
               'WHERE id=?', (dados['data'], dados['tipo'], dados['descricao'], dados['valor'], dados['conta'], dados['nf'], dados['obs'],
                              usuario, agora(), lid))
    db.commit()


def excluir(db, lid):
    db.execute('DELETE FROM cxd_lancamentos WHERE id=?', (lid,))
    db.commit()


def lancamentos_do_dia(db, dia):
    return [dict(r) for r in db.execute('SELECT * FROM cxd_lancamentos WHERE data=? ORDER BY tipo, id', (dia,))]


def _movimentos(db, de, ate_excl):
    """Soma (receitas − despesas) de cada conta entre `de` (incl.) e `ate_excl` (excl.)."""
    saldo = {c: 0.0 for c, _, _ in CONTAS}
    for r in db.execute("SELECT conta, SUM(CASE WHEN tipo='RECEITA' THEN valor ELSE -valor END) AS s FROM cxd_lancamentos "
                        "WHERE data>=? AND data<? GROUP BY conta", (de, ate_excl)):
        saldo[r['conta']] = round(r['s'], 2)
    return saldo


def saldos_do_dia(db, dia):
    """Por conta: abertura (saldo do dia anterior), receitas, despesas e fechamento. Mais os totais do dia."""
    ini = inicio(db)
    if ini is None:
        return None
    if dia < ini['data']:
        raise ErroCaixaDiario('Este dia é anterior ao saldo inicial.')
    base = {'BB': ini['bb'], 'UNICRED': ini['unicred'], 'CAIXA': ini['caixa'], 'DINHEIRO': ini['dinheiro']}
    antes = _movimentos(db, ini['data'], dia)
    do_dia = {c: {'RECEITA': 0.0, 'DESPESA': 0.0} for c, _, _ in CONTAS}
    for r in db.execute('SELECT conta, tipo, SUM(valor) AS s FROM cxd_lancamentos WHERE data=? GROUP BY conta, tipo', (dia,)):
        do_dia[r['conta']][r['tipo']] = round(r['s'], 2)
    contas = {}
    for c, nome, cor in CONTAS:
        abertura = round(base[c] + antes[c], 2)
        receitas = do_dia[c]['RECEITA']
        despesas = do_dia[c]['DESPESA']
        contas[c] = {'nome': nome, 'cor': cor, 'abertura': abertura, 'receitas': receitas, 'despesas': despesas,
                     'fechamento': round(abertura + receitas - despesas, 2)}
    total_receitas = round(sum(v['receitas'] for v in contas.values()), 2)
    total_despesas = round(sum(v['despesas'] for v in contas.values()), 2)
    abertura_total = round(sum(v['abertura'] for v in contas.values()), 2)
    saldo_total = round(sum(v['fechamento'] for v in contas.values()), 2)
    retidas = retidas_lista(db)
    total_retidas = round(sum(r['valor'] for r in retidas), 2)
    return {'contas': contas, 'abertura_total': abertura_total, 'receitas': total_receitas, 'despesas': total_despesas,
            'saldo_total': saldo_total, 'retidas': retidas, 'total_retidas': total_retidas,
            'total_final': round(saldo_total - total_retidas, 2)}


def retidas_lista(db):
    return [dict(r) for r in db.execute('SELECT * FROM cxd_retidas ORDER BY id')]


def adicionar_retida(db, form):
    descricao = (form.get('descricao') or '').strip().upper()
    if not descricao:
        raise ErroCaixaDiario('Informe a descrição da retirada retida.')
    db.execute('INSERT INTO cxd_retidas (descricao, valor) VALUES (?,?)', (descricao[:200], _dinheiro(form.get('valor'))))
    db.commit()


def excluir_retida(db, rid):
    db.execute('DELETE FROM cxd_retidas WHERE id=?', (rid,))
    db.commit()


def _br(iso):
    return '%s/%s/%s' % (iso[8:10], iso[5:7], iso[:4])


def relatorio_xlsx(db, dia):
    """Planilha do dia no formato da planilha original: títulos, bordas, valores em R$, cores por conta e a mesma ordem de cálculo."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.worksheet.properties import PageSetupProperties

    sal = saldos_do_dia(db, dia)
    if sal is None:
        raise ErroCaixaDiario('Informe primeiro os saldos iniciais.')
    wb = Workbook()
    ws = wb.active
    ws.title = _br(dia).replace('/', '-')
    moeda = '"R$" #,##0.00;[Red]-"R$" #,##0.00'
    fino = Side(style='thin', color='8A948F')
    grosso = Side(style='medium', color='255F39')
    borda = Border(top=fino, bottom=fino, left=fino, right=fino)
    verde = PatternFill('solid', fgColor='FF255F39')
    cinza = PatternFill('solid', fgColor='FFE9EFEB')
    centro = Alignment(horizontal='center', vertical='center')
    direita = Alignment(horizontal='right', vertical='center')
    esquerda = Alignment(horizontal='left', vertical='center', wrap_text=True)

    def cel(linha, col, valor=None, fonte=None, preenche=None, alinha=None, formato=None, caixa=True):
        c = ws.cell(linha, col, valor)
        if fonte:
            c.font = fonte
        if preenche:
            c.fill = preenche
        c.alignment = alinha or esquerda
        if formato:
            c.number_format = formato
        if caixa:
            c.border = borda
        return c

    def cor(hexa):
        return PatternFill('solid', fgColor='FF' + hexa)

    def secao(linha, titulos):
        for i, t in enumerate(titulos, start=1):
            cel(linha, i, t, Font(bold=True, color='FF1D2522'), cinza, centro)

    # título
    ws.merge_cells('A1:E1')
    cel(1, 1, 'MOVIMENTO DE CAIXA', Font(bold=True, size=15, color='FFFFFFFF'), verde, centro, caixa=False)
    ws.row_dimensions[1].height = 28
    ws.merge_cells('A2:E2')
    cel(2, 1, 'Dia: ' + _br(dia), Font(bold=True, size=12), None, centro, caixa=False)
    ws.row_dimensions[2].height = 22
    cel(4, 1, 'Saldo inicial do dia (soma das contas)', Font(bold=True), cinza)
    cel(4, 2, sal['abertura_total'], Font(bold=True), cinza, direita, moeda)
    linha = 6
    itens_dia = lancamentos_do_dia(db, dia)
    for titulo, tipo, total in (('RECEITAS', 'RECEITA', sal['receitas']), ('DESPESAS', 'DESPESA', sal['despesas'])):
        ws.merge_cells(start_row=linha, start_column=1, end_row=linha, end_column=4)
        cel(linha, 1, titulo, Font(bold=True, color='FFFFFFFF'), verde, centro, caixa=False)
        linha += 1
        secao(linha, ['Descrição', 'Valor', 'Conta', 'NF'])
        linha += 1
        itens = [l for l in itens_dia if l['tipo'] == tipo]
        for l in itens:
            fundo = cor(COR_CONTA[l['conta']])
            cel(linha, 1, l['descricao'], None, fundo)
            cel(linha, 2, l['valor'], None, fundo, direita, moeda)
            cel(linha, 3, NOMES_CONTA[l['conta']], None, fundo, centro)
            cel(linha, 4, l['nf'], None, fundo, centro)
            linha += 1
        if not itens:
            ws.merge_cells(start_row=linha, start_column=1, end_row=linha, end_column=4)
            cel(linha, 1, '(sem lançamentos)', Font(italic=True, color='FF6F7D75'), None, centro)
            for col in range(2, 5):
                ws.cell(linha, col).border = borda
            linha += 1
        cel(linha, 1, 'Total de ' + ('Receitas' if tipo == 'RECEITA' else 'Despesas'), Font(bold=True), cinza)
        cel(linha, 2, total, Font(bold=True), cinza, direita, moeda)
        for col in (3, 4):
            cel(linha, col, None, None, cinza)
        linha += 2

    # contas (o saldo de cada uma passa para o dia seguinte)
    ws.merge_cells(start_row=linha, start_column=1, end_row=linha, end_column=5)
    cel(linha, 1, 'SALDO POR CONTA', Font(bold=True, color='FFFFFFFF'), verde, centro, caixa=False)
    linha += 1
    secao(linha, ['Conta', 'Abertura', 'Receitas', 'Despesas', 'Fechamento'])
    linha += 1
    for c, _, _ in CONTAS:
        v = sal['contas'][c]
        fundo = cor(v['cor'])
        cel(linha, 1, v['nome'], Font(bold=True), fundo)
        for col, chave in ((2, 'abertura'), (3, 'receitas'), (4, 'despesas'), (5, 'fechamento')):
            cel(linha, col, v[chave], Font(bold=(chave == 'fechamento')), fundo, direita, moeda)
        linha += 1
    cel(linha, 1, 'SALDO TOTAL', Font(bold=True, size=12), cinza)
    for col, valor in ((2, sal['abertura_total']), (3, sal['receitas']), (4, sal['despesas']), (5, sal['saldo_total'])):
        cel(linha, col, valor, Font(bold=True, size=12), cinza, direita, moeda)
    for col in range(1, 6):
        ws.cell(linha, col).border = Border(top=grosso, bottom=grosso, left=fino, right=fino)
    linha += 2

    # retiradas retidas
    ws.merge_cells(start_row=linha, start_column=1, end_row=linha, end_column=2)
    cel(linha, 1, 'OBS.: RETIRADAS RETIDAS TEMPORARIAMENTE', Font(bold=True, color='FFFFFFFF'), verde, centro, caixa=False)
    linha += 1
    for r in sal['retidas']:
        cel(linha, 1, r['descricao'])
        cel(linha, 2, r['valor'], None, None, direita, moeda)
        linha += 1
    if not sal['retidas']:
        cel(linha, 1, '(nenhuma retirada retida)', Font(italic=True, color='FF6F7D75'))
        cel(linha, 2, 0, None, None, direita, moeda)
        linha += 1
    cel(linha, 1, 'Total de retidas', Font(bold=True), cinza)
    cel(linha, 2, sal['total_retidas'], Font(bold=True), cinza, direita, moeda)
    linha += 1
    cel(linha, 1, 'TOTAL (Saldo Total − retidas)', Font(bold=True, size=12), cinza)
    cel(linha, 2, sal['total_final'], Font(bold=True, size=12), cinza, direita, moeda)
    for col in (1, 2):
        ws.cell(linha, col).border = Border(top=grosso, bottom=grosso, left=fino, right=fino)
    linha += 3

    # assinaturas
    ws.cell(linha, 1, '________________________').alignment = centro
    ws.cell(linha, 3, '________________________').alignment = centro
    ws.merge_cells(start_row=linha, start_column=3, end_row=linha, end_column=4)
    ws.cell(linha + 1, 1, 'Gerente Administrativo').alignment = centro
    ws.cell(linha + 1, 3, 'Sócio-Administrador').alignment = centro
    ws.merge_cells(start_row=linha + 1, start_column=3, end_row=linha + 1, end_column=4)

    for col, largura in zip('ABCDE', (46, 18, 30, 16, 18)):
        ws.column_dimensions[col].width = largura
    # impressão: A4 em pé, uma página de largura, centralizada
    ws.page_setup.orientation = 'portrait'
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.print_options.horizontalCentered = True
    ws.page_margins.left = ws.page_margins.right = 0.5
    ws.page_margins.top = ws.page_margins.bottom = 0.6
    ws.sheet_view.showGridLines = False
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
