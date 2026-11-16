"""Planilhas das vagas reservadas para um convênio: uma planilha por dia reservado, em branco com os campos da agenda;
o convênio preenche e devolve, e a importação preenche a agenda. Cada linha leva o código da vaga, que é como o sistema a encontra.
Nada é guardado no sistema: a planilha é gerada na hora e o arquivo devolvido só é lido e descartado."""
from __future__ import annotations

import io
import re
import zipfile
from datetime import date, datetime

from . import agenda as ag
from . import util

COLUNAS = ['Data', 'Hora', 'Exame', 'Nome do paciente', 'Contato', 'Convênio', 'Código da vaga (não mexer)']
COLUNAS_PREENCHIVEIS = (4, 5)          # só Nome do paciente e Contato ficam liberados; o resto da planilha é bloqueado
COLUNA_CODIGO = len(COLUNAS)           # a última, oculta e bloqueada: é como o sistema acha a vaga na importação
# Proteção da planilha (impede mexer nas colunas bloqueadas e reexibir o código sem desproteger). Não é segurança forte: a
# importação confere data, hora e exame de cada linha com a vaga da agenda, então um código alterado é recusado do mesmo jeito.
SENHA_PROTECAO = 'nucleleste-reservas'
LINHA_CAB = 4
MAX_BYTES = 5 * 1024 * 1024
DIAS = ('segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado', 'domingo')


def convenios_com_reserva(db):
    return [r[0] for r in db.execute("SELECT DISTINCT reservado_convenio FROM agenda_horarios WHERE reservado_unacon=1 "
                                     "AND TRIM(COALESCE(reservado_convenio,''))<>'' ORDER BY 1 COLLATE NOCASE")]


def dias_com_reserva(db, de, ate):
    """Dias do período (datas ISO) que ainda têm vaga reservada sem paciente."""
    return [r[0] for r in db.execute("SELECT DISTINCT a.data FROM agenda_horarios h JOIN agenda_exames a ON a.id=h.agenda_id "
                                     "WHERE h.reservado_unacon=1 AND TRIM(h.paciente)='' AND a.data BETWEEN ? AND ? ORDER BY 1", (de, ate))]


def vagas(db, convenio, de, ate):
    """Vagas reservadas, ainda sem paciente, no período (datas ISO). Sem `convenio`, de todos os convênios."""
    filtro, params = '', [de, ate]
    if (convenio or '').strip():
        filtro = ' AND h.reservado_convenio=? COLLATE NOCASE'
        params = [convenio.strip()] + params
    sql = ("SELECT h.id, a.data, h.hora, a.exame, h.convenio, h.reservado_convenio FROM agenda_horarios h "
           "JOIN agenda_exames a ON a.id=h.agenda_id WHERE h.reservado_unacon=1 AND TRIM(h.paciente)=''" + filtro +
           " AND a.data BETWEEN ? AND ? ORDER BY a.data, h.reservado_convenio COLLATE NOCASE, h.hora, a.exame, h.id")
    return db.execute(sql, params).fetchall()


def grupos(db, convenio, de, ate):
    """Vagas agrupadas por dia e convênio: [{'dia', 'convenio', 'vagas': [linhas]}], na ordem das datas."""
    saida, indice = [], {}
    for v in vagas(db, convenio, de, ate):
        nome = (v['reservado_convenio'] or convenio or '').strip()
        chave = (v['data'], nome.casefold())
        if chave not in indice:
            indice[chave] = {'dia': v['data'], 'convenio': nome, 'vagas': []}
            saida.append(indice[chave])
        indice[chave]['vagas'].append(v)
    return saida


def _data_br(iso):
    return iso[8:10] + '/' + iso[5:7] + '/' + iso[:4]


def planilha_do_dia(convenio, dia, lista):
    """Bytes do .xlsx em branco de um dia: uma linha por vaga reservada, com os campos da agenda para preencher."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Protection, Side
    wb = Workbook()
    ws = wb.active
    ws.title = 'Reservas'
    ws.append(['Agenda reservada: %s · %s' % (convenio, _data_br(dia))])
    ws['A1'].font = Font(bold=True, size=14, color='1D4F30')
    ws.append(['Preencha somente o nome do paciente e o contato nas linhas em branco e devolva a planilha. '
               'As demais colunas estão bloqueadas (cinza).'])
    ws.append([])
    ws.append(COLUNAS)
    borda = Side(style='thin', color='9AA8A0')
    caixa = Border(left=borda, right=borda, top=borda, bottom=borda)
    for col in range(1, len(COLUNAS) + 1):
        c = ws.cell(row=LINHA_CAB, column=col)
        c.font = Font(bold=True, color='FFFFFF')
        c.fill = PatternFill('solid', fgColor='2F8A50')
        c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        c.border = caixa
    cinza = PatternFill('solid', fgColor='EEF2EF')
    for k, v in enumerate(lista):
        d = date.fromisoformat(v['data'])
        ws.append(['%s (%s)' % (d.strftime('%d/%m/%Y'), DIAS[d.weekday()]), v['hora'], v['exame'], '', '', v['convenio'] or convenio, v['id']])
        for col in range(1, len(COLUNAS) + 1):
            c = ws.cell(row=LINHA_CAB + 1 + k, column=col)
            c.border = caixa
            if col in COLUNAS_PREENCHIVEIS:
                c.protection = Protection(locked=False)
            else:
                c.fill = cinza
    for col, larg in zip('ABCDEFG', (20, 8, 24, 40, 24, 22, 14)):
        ws.column_dimensions[col].width = larg
    ws.column_dimensions['G'].hidden = True            # o código da vaga não aparece para quem preenche
    ws.protection.sheet = True                          # bloqueia tudo, menos as células liberadas acima
    ws.protection.set_password(SENHA_PROTECAO)
    ws.freeze_panes = ws.cell(row=LINHA_CAB + 1, column=1)
    ws.page_setup.orientation = 'landscape'
    ws.page_setup.fitToWidth = 1
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToHeight = 0
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _slug(texto):
    return re.sub(r'[^A-Za-z0-9]+', '-', texto or '').strip('-') or 'convenio'


def resumo(grupos_):
    """Linhas do relatório simples: dia, convênio, vagas por exame e total de vagas."""
    saida = []
    for g in grupos_:
        por_exame = {}
        for v in g['vagas']:
            por_exame[v['exame']] = por_exame.get(v['exame'], 0) + 1
        d = date.fromisoformat(g['dia'])
        saida.append({'dia': g['dia'], 'dia_semana': DIAS[d.weekday()], 'convenio': g['convenio'], 'por_exame': por_exame,
                      'vagas': len(g['vagas'])})
    return saida


def pacote(db, convenio, de, ate, empresa=''):
    """Planilhas do período. Um único dia/convênio: o próprio .xlsx. Vários: um .zip com uma planilha por dia reservado
    e o relatório simples em PDF (datas reservadas e quantidade de vagas). Devolve (nome, mimetype, bytes, quantidade) ou None."""
    lista = grupos(db, convenio, de, ate)
    if not lista:
        return None
    if len(lista) == 1:
        g = lista[0]
        nome = 'reserva-%s-%s.xlsx' % (_slug(g['convenio']), g['dia'])
        return nome, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', planilha_do_dia(g['convenio'], g['dia'], g['vagas']), 1
    from . import agenda_rel_docs
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for g in lista:
            z.writestr('reserva-%s-%s.xlsx' % (_slug(g['convenio']), g['dia']), planilha_do_dia(g['convenio'], g['dia'], g['vagas']))
        z.writestr('resumo-das-reservas.pdf', agenda_rel_docs.reservas_pdf(resumo(lista), empresa, de, ate))
    sufixo = _slug(convenio) if (convenio or '').strip() else 'todos'
    return 'reservas-%s-%s-a-%s.zip' % (sufixo, de, ate), 'application/zip', buf.getvalue(), len(lista)


def _data_da_celula(v):
    if isinstance(v, (datetime, date)):
        return v.date().isoformat() if isinstance(v, datetime) else v.isoformat()
    m = re.match(r'\s*(\d{2})/(\d{2})/(\d{4})', str(v or ''))
    return '%s-%s-%s' % (m.group(3), m.group(2), m.group(1)) if m else ''


def importar(db, conteudo, usuario):
    """Preenche a agenda com a planilha devolvida. Devolve {'preenchidas', 'ignoradas', 'problemas': [texto]}.
    Só preenche vagas ainda sem paciente; o que já foi preenchido na agenda não é sobrescrito."""
    from openpyxl import load_workbook
    if len(conteudo) > MAX_BYTES:
        raise ag.ErroAgenda('Arquivo grande demais (máximo 5 MB).')
    try:
        wb = load_workbook(io.BytesIO(conteudo), data_only=True)
    except Exception:
        raise ag.ErroAgenda('Não consegui abrir o arquivo. Envie a planilha .xlsx gerada pelo sistema.') from None
    ws = wb.active
    cab = [str(c.value or '').strip().lower() for c in ws[LINHA_CAB]]
    if 'código da vaga (não mexer)' not in cab or 'nome do paciente' not in cab:
        raise ag.ErroAgenda('Esta não parece ser a planilha de reservas gerada pelo sistema (faltam as colunas de nome e de código da vaga).')
    i_nome, i_cont, i_cod = cab.index('nome do paciente'), cab.index('contato') if 'contato' in cab else None, cab.index('código da vaga (não mexer)')
    i_data, i_hora, i_exame = cab.index('data'), cab.index('hora'), cab.index('exame')
    res = {'preenchidas': 0, 'ignoradas': 0, 'problemas': []}
    dias = set()
    for n, linha in enumerate(ws.iter_rows(min_row=LINHA_CAB + 1, values_only=True), LINHA_CAB + 1):
        nome = ' '.join(str(linha[i_nome] or '').upper().split())
        if not nome:
            res['ignoradas'] += 1
            continue
        try:
            hid = int(linha[i_cod])
        except (TypeError, ValueError):
            res['problemas'].append('Linha %d (%s): sem código da vaga.' % (n, nome))
            continue
        try:
            r = ag._linha(db, hid)
        except ag.ErroAgenda:
            res['problemas'].append('Linha %d (%s): a vaga não existe mais na agenda.' % (n, nome))
            continue
        if _data_da_celula(linha[i_data]) != r['dia'] or str(linha[i_hora] or '').strip() != (r['hora'] or '') \
                or str(linha[i_exame] or '').strip().upper() != (r['exame_agenda'] or '').strip().upper():
            res['problemas'].append('Linha %d (%s): data, hora ou exame não conferem com a vaga da agenda.' % (n, nome))
            continue
        if (r['paciente'] or '').strip():
            res['problemas'].append('Linha %d (%s): a vaga já está preenchida na agenda (%s); não foi alterada.' % (n, nome, r['paciente']))
            continue
        try:
            ag.salvar_campo(db, hid, 'paciente', nome, None, usuario)
        except ag.ErroAgenda as e:
            db.rollback()
            res['problemas'].append('Linha %d (%s): %s' % (n, nome, e))
            continue
        res['preenchidas'] += 1
        dias.add(r['dia'])
        contato = str(linha[i_cont] or '').strip() if i_cont is not None else ''
        if contato:
            try:
                ag.salvar_campo(db, hid, 'contato', contato, None, usuario)
            except ag.ErroAgenda as e:
                db.rollback()
                res['problemas'].append('Linha %d (%s): o contato não foi gravado (%s)' % (n, nome, e))
    for d in sorted(dias):   # a importação também confere nomes e telefones repetidos no dia
        try:
            ag.avisar_duplicados(db, d)
        except Exception:
            db.rollback()
    return res
