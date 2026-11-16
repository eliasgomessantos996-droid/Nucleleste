"""PDFs da agenda de exames (agenda do dia, relatório) e planilha Excel do relatório."""
from __future__ import annotations

import io
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from . import util
from .agenda import ROTULOS

VERDE = colors.HexColor('#255f39')
COR_STATUS = {'VEIO': colors.HexColor('#bcd9f7'), 'FALTOU': colors.HexColor('#ffab91'), 'RETORNO': colors.HexColor('#bcd9f7'),
              'RESGATADO': colors.HexColor('#d4f1ea'), 'DESISTIU': colors.HexColor('#e3e6ea')}
COR_PROTOCOLO = colors.HexColor('#7ddf7d')
LARGURA = landscape(A4)[0] - 24 * mm


def _esc(v):
    return str(v or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _estilo(nome, **kw):
    base = dict(fontName='Helvetica', fontSize=9.5, leading=12)
    base.update(kw)
    return ParagraphStyle(nome, **base)


def _rodape(titulo, largura=None):
    largura = largura or landscape(A4)[0]

    def desenhar(c, d):
        c.setFont('Helvetica', 8)
        c.setFillColor(colors.HexColor('#666666'))
        c.drawString(12 * mm, 8 * mm, titulo)
        c.drawRightString(largura - 12 * mm, 8 * mm, 'Página %d' % d.page)
    return desenhar


def _dia_extenso(data_iso):
    d = util.para_data(data_iso)
    semana = ['segunda-feira', 'terça-feira', 'quarta-feira', 'quinta-feira', 'sexta-feira', 'sábado', 'domingo'][d.weekday()]
    return '%s, %s' % (semana, util.data_extenso(d))


# ------------------------------------------------------------------ agenda do dia
# Só o essencial para a recepção: Nº das linhas preenchidas (conta só as com paciente, recomeça em cada exame),
# horário, paciente e convênio. Horários sem paciente não são impressos (só as linhas preenchidas).
# O relatório cabe sempre em UMA página:
# a altura das linhas e a letra se ajustam à quantidade de horários e, se ainda assim ficar miúdo, cada exame
# passa a ser impresso em duas colunas lado a lado.
PAGINA = A4
MARGEM_X, MARGEM_TOPO, MARGEM_BASE = 12 * mm, 12 * mm, 14 * mm
CAB_DIA = ('Nº', 'Horário', 'Paciente', 'Convênio')
ALTURA_MAX, ALTURA_MIN = 17.0, 8.0     # altura da linha, em pontos
LETRA_MAX, LETRA_MIN = 10.5, 5.0


def _cortar(texto, fonte, tam, largura):
    """Corta o texto com reticências para caber em `largura` pontos (a linha nunca quebra, para não crescer)."""
    texto = (texto or '').strip()
    if stringWidth(texto, fonte, tam) <= largura:
        return texto
    while texto and stringWidth(texto + '…', fonte, tam) > largura:
        texto = texto[:-1]
    return texto.rstrip() + '…'


def _so_preenchidas(agendas):
    """Cópias das agendas com só as linhas que têm paciente. Não altera as agendas recebidas."""
    return [dict(a, linhas=[l for l in a['linhas'] if (l['paciente'] or '').strip()]) for a in agendas]


def _resumo_dia(agendas):
    """Totais do dia: pacientes no geral, por exame e por convênio (maiúsculas e espaços não diferenciam)."""
    total, por_exame, convenios = 0, [], {}
    for a in agendas:
        n = 0
        for l in a['linhas']:
            if not (l['paciente'] or '').strip():
                continue
            n += 1
            conv = ' '.join((l['convenio'] or '').split()).upper() or 'Sem convênio'
            convenios[conv] = convenios.get(conv, 0) + 1
        total += n
        por_exame.append((a['exame'], n))
    por_convenio = sorted(convenios.items(), key=lambda x: (-x[1], x[0]))
    return {'total': total, 'por_exame': por_exame, 'por_convenio': por_convenio}


def _quadro_resumo(resumo, largura):
    """Quadro compacto do cabeçalho (total, por exame, por convênio). Devolve (flowable, altura em pontos)."""
    textos = [('Total de pacientes: %d' % resumo['total'], True),
              ('Por exame: ' + (' · '.join('%s %d' % (n, q) for n, q in resumo['por_exame']) or 'nenhum exame'), False),
              ('Por convênio: ' + (' · '.join('%s %d' % (n, q) for n, q in resumo['por_convenio']) or 'nenhum paciente'), False)]
    tam, lin = 8.5, 11
    estilo = _estilo('q', fontSize=tam, leading=lin)
    estilo_negrito = _estilo('qn', fontName='Helvetica-Bold', fontSize=tam, leading=lin)
    linhas = sum(len(simpleSplit(t, 'Helvetica', tam, largura - 12)) for t, _ in textos)
    altura = linhas * lin + len(textos) * 4 + 4 + lin      # +1 linha de folga para a quebra do Paragraph
    quadro = Table([[Paragraph(_esc(t), estilo_negrito if negrito else estilo)] for t, negrito in textos],
                   colWidths=[largura])
    quadro.setStyle(TableStyle([('BOX', (0, 0), (-1, -1), .5, colors.HexColor('#9aa8a0')),
                                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f1f6f3')),
                                ('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                                ('LEFTPADDING', (0, 0), (-1, -1), 6), ('RIGHTPADDING', (0, 0), (-1, -1), 6)]))
    return quadro, altura


def _plano(agendas, altura_util):
    """(blocos de colunas por exame, altura da linha, tamanho da letra) que fazem tudo caber na página.
    Usa 1 bloco; se a letra ficar miúda demais, divide cada exame em 2 (ou 3) blocos lado a lado."""
    def medir(k):
        linhas = sum(-(-len(a['linhas']) // k) + 1 for a in agendas)   # +1: cabeçalho da tabela de cada exame
        livre = (altura_util - len(agendas) * 26) * 0.97
        altura = min(ALTURA_MAX, livre / max(linhas, 1))
        return altura, min(LETRA_MAX, max(LETRA_MIN, altura * .62))
    for k in (1, 2, 3):
        altura, letra = medir(k)
        if altura * .62 >= 7.5:
            break
    return k, max(altura, 3.0), letra


def dia_pdf(data_iso, agendas, empresa, separar=False):
    """`agendas`: as agendas a imprimir (todas ou só a do exame escolhido), cada uma com suas linhas.
    `separar` é aceito por compatibilidade e ignorado: o relatório é sempre de uma página só."""
    agendas = _so_preenchidas(agendas)
    buf = io.BytesIO()
    larg_total = PAGINA[0] - 2 * MARGEM_X
    quadro, altura_quadro = _quadro_resumo(_resumo_dia(agendas), larg_total)
    altura_util = PAGINA[1] - MARGEM_TOPO - MARGEM_BASE - 58 - altura_quadro - 12   # 58 pt: título, subtítulo e a folga interna; o quadro e o espaço abaixo dele são descontados
    doc = SimpleDocTemplate(buf, pagesize=PAGINA, leftMargin=MARGEM_X, rightMargin=MARGEM_X, topMargin=MARGEM_TOPO,
                            bottomMargin=MARGEM_BASE, title='Agenda de exames - %s' % util.data_br(data_iso),
                            author=empresa or 'Nucleleste')
    titulo = _estilo('t', fontName='Helvetica-Bold', fontSize=15, leading=19)
    sub = _estilo('s', fontSize=10, leading=13, textColor=colors.HexColor('#444444'))
    exame = _estilo('e', fontName='Helvetica-Bold', fontSize=11, leading=13, textColor=VERDE, keepWithNext=1, spaceBefore=7, spaceAfter=2)

    historia = [Paragraph('Agenda de exames', titulo),
                Paragraph('%s · %s' % (_esc(empresa) or 'Nucleleste', _dia_extenso(data_iso)), sub),
                Spacer(1, 6), quadro, Spacer(1, 6)]
    if not agendas:
        historia += [Spacer(1, 14), Paragraph('Não há agenda criada para este dia.', sub)]
    k, altura, letra = _plano(agendas, altura_util)
    pesos = (8, 17, 62, 31)                                  # proporções das 4 colunas (Nº, horário, paciente, convênio)
    folga = 8 if k > 1 else 0
    passo = len(CAB_DIA) + (1 if k > 1 else 0)               # colunas de cada bloco (+1 de espaço entre blocos)
    bloco = (larg_total - folga * (k - 1)) / k
    larg = [bloco * p / sum(pesos) for p in pesos]
    for a in agendas:
        r = a['resumo']
        historia.append(Paragraph('%s <font size="8.5" color="#555555">· %s às %s · %d marcado(s) de %d</font>' %
                                  (_esc(a['exame']), a['inicio'], a['fim'], r['marcados'], r['vagas']), exame))
        if not a['linhas']:
            historia.append(Paragraph('Nenhum paciente marcado.', sub))
            continue
        # Nº: numera as linhas com paciente na ordem da agenda (antes de dividir em blocos, para seguir contínuo)
        seq, n = [], 0
        for l in a['linhas']:
            tem = bool((l['paciente'] or '').strip())
            n += 1 if tem else 0
            seq.append((str(n) if tem else '', l))
        metade = -(-len(seq) // k) if seq else 0
        partes = [seq[i * metade:(i + 1) * metade] for i in range(k)] if k > 1 else [seq]
        cab = []
        for c in range(k):
            cab += list(CAB_DIA) + ([''] if k > 1 and c < k - 1 else [])
        dados = [cab]
        estilos = [('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', max(letra - 1, 5)), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                   ('FONT', (0, 1), (-1, -1), 'Helvetica', letra), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                   ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
                   ('LEFTPADDING', (0, 0), (-1, -1), 3), ('RIGHTPADDING', (0, 0), (-1, -1), 3)]
        for c in range(k):
            ini = c * passo
            fim = ini + len(CAB_DIA) - 1
            estilos += [('BACKGROUND', (ini, 0), (fim, 0), VERDE), ('GRID', (ini, 0), (fim, -1), .5, colors.HexColor('#9aa8a0')),
                        ('ALIGN', (ini, 0), (ini, -1), 'CENTER')]
        for i in range(metade):
            linha = []
            for c in range(k):
                ini = c * passo
                fim = ini + len(CAB_DIA) - 1
                if i < len(partes[c]):
                    num, l = partes[c][i]
                    tem = num != ''
                    linha += [num, _cortar(l['hora'], 'Helvetica', letra, larg[1] - 6), _cortar(l['paciente'], 'Helvetica', letra, larg[2] - 6),
                              _cortar(l['convenio'], 'Helvetica', letra, larg[3] - 6)]
                    if tem and l['status'] in COR_STATUS:
                        estilos.append(('BACKGROUND', (ini, i + 1), (fim, i + 1), COR_STATUS[l['status']]))
                    elif tem and a.get('mibi') and l['senha'] == 'Protocolo':
                        estilos.append(('BACKGROUND', (ini, i + 1), (fim, i + 1), COR_PROTOCOLO))
                else:
                    linha += [''] * len(CAB_DIA)
                if k > 1 and c < k - 1:
                    linha.append('')
            dados.append(linha)
        colunas = []
        for c in range(k):
            colunas += larg + ([folga] if k > 1 and c < k - 1 else [])
        t = Table(dados, colWidths=colunas, rowHeights=[altura] * len(dados))
        t.setStyle(TableStyle(estilos))
        historia.append(t)
    rodape = _rodape('Agenda de exames · %s' % util.data_br(data_iso), PAGINA[0])
    doc.build(historia, onFirstPage=rodape, onLaterPages=rodape)
    return buf.getvalue()
