"""Faturamento por convênio em três momentos, cada um na sua aba:

1. FATURAMENTO: cadastro da fatura (convênio, data de referência, valor faturado, protocolo, quantidade de guias; a nota fiscal NÃO é
   obrigatória). Sem nota, a fatura fica com a situação FATURADO.
2. EMISSÃO DA NOTA FISCAL: informa o número e a data da nota e a situação passa para NF_EMITIDA.
3. RECEBIDAS: lança o que foi recebido (bruto recebido, tributos e líquido) e compara com o faturado; a diferença é a GLOSA.
   A situação passa para RECEBIDO.

O protocolo de faturamento (PDF) pode ser importado para consulta, aberto dentro do sistema e baixado depois (fica no anexos.db).

Os campos antigos continuam coerentes para o dashboard e a qualidade: `valor_bruto` = faturado, `tributos` e `valor_liquido` = bruto − tributos
(tributos informados no recebimento) e `valor_recebido` = líquido recebido. Glosa = bruto faturado − bruto recebido."""
from __future__ import annotations

from datetime import date

from . import anexos, util
from .db import agora

FATURADO, NF_EMITIDA, RECEBIDO = 'FATURADO', 'NF_EMITIDA', 'RECEBIDO'
STATUS = (FATURADO, NF_EMITIDA, RECEBIDO)
ROTULOS = {FATURADO: 'Faturado (sem nota)', NF_EMITIDA: 'Nota fiscal emitida', RECEBIDO: 'Recebido'}
MAX_PDF = 20 * 1024 * 1024
LIMITES = {'protocolo': 40, 'nota_fiscal': 30, 'obs': 300, 'convenio': 80}


class ErroFatura(ValueError):
    """Erro de validação mostrado ao usuário."""


def _num(texto):
    v = util.para_valor(texto)
    return round(v, 2) if v is not None else None


def _inteiro(texto):
    s = str(texto if texto is not None else '').strip()
    return int(s) if s.isdigit() else None


# ------------------------------------------------------------------ leitura
def obter(db, fid):
    r = db.execute('SELECT * FROM faturas WHERE id=?', (fid,)).fetchone()
    if not r:
        raise ErroFatura('Esta fatura não existe mais. Atualize a página.')
    return r


def glosa(r):
    """{'valor', 'pct', 'sentido'} de uma fatura recebida: valor = bruto faturado − bruto recebido (positivo = recebeu menos).
    `sentido`: 'glosa' (recebeu menos), 'sem' (igual) ou 'acima' (recebeu mais). Fatura ainda não recebida: None."""
    if r['status'] != RECEBIDO:
        return None
    bruto_rec = r['bruto_recebido']
    if bruto_rec is None:   # recebimento antigo (só tinha o líquido)
        bruto_rec = (r['valor_recebido'] or 0) + (r['tributos'] or 0)
    valor = round((r['valor_bruto'] or 0) - bruto_rec, 2)
    pct = round(100 * valor / r['valor_bruto'], 2) if r['valor_bruto'] else 0.0
    return {'valor': valor, 'pct': pct, 'sentido': 'glosa' if valor > 0.004 else ('acima' if valor < -0.004 else 'sem'), 'bruto_recebido': round(bruto_rec, 2)}


def _atrasada(r, hoje):
    return r['status'] != RECEBIDO and bool(r['previsao']) and r['previsao'] < hoje


def listar(db, status='', convenio='', de='', ate='', q='', limite=1500):
    """Faturas do filtro, da referência mais nova para a mais antiga, já com a glosa e a marca de atraso."""
    onde, params = ['1=1'], []
    if status in STATUS:
        onde.append('status=?')
        params.append(status)
    if convenio:
        onde.append('convenio=?')
        params.append(convenio)
    if de:
        onde.append('referencia>=?')
        params.append(de)
    if ate:
        onde.append('referencia<=?')
        params.append(ate)
    if q:
        onde.append("(UPPER(COALESCE(nota_fiscal,'')) LIKE ? OR UPPER(COALESCE(protocolo,'')) LIKE ? OR UPPER(convenio) LIKE ?)")
        params += ['%' + q.upper() + '%'] * 3
    hoje = date.today().isoformat()
    saida = []
    for r in db.execute('SELECT * FROM faturas WHERE %s ORDER BY referencia DESC, id DESC LIMIT %d' % (' AND '.join(onde), limite), params):
        d = dict(r)
        d['glosa'] = glosa(r)
        d['atrasada'] = _atrasada(r, hoje)
        d['status_rotulo'] = ROTULOS.get(d['status'], d['status'])
        saida.append(d)
    return saida


def totais(faturas):
    t = {'n': len(faturas), 'guias': 0, 'faturado': 0.0, 'recebido_bruto': 0.0, 'tributos': 0.0, 'liquido': 0.0, 'glosa': 0.0, 'a_receber': 0.0}
    for f in faturas:
        t['guias'] += f['qtd_guias'] or 0
        t['faturado'] += f['valor_bruto'] or 0
        if f['status'] == RECEBIDO and f['glosa']:
            t['recebido_bruto'] += f['glosa']['bruto_recebido']
            t['tributos'] += f['tributos'] or 0
            t['liquido'] += f['valor_recebido'] or 0
            t['glosa'] += f['glosa']['valor']
        else:
            t['a_receber'] += f['valor_bruto'] or 0
    return {k: (round(v, 2) if isinstance(v, float) else v) for k, v in t.items()}


# ------------------------------------------------------------------ 1. faturamento (cadastro)
def validar(db, d, fid=None):
    """Confere os campos do cadastro. Devolve (dados limpos, avisos). Só a nota fiscal é opcional."""
    convenio = util.maiusculas((d.get('convenio') or '').strip())
    referencia = util.para_data(d.get('referencia'))
    valor = _num(d.get('valor_bruto'))
    protocolo = (d.get('protocolo') or '').strip()
    guias = _inteiro(d.get('qtd_guias'))
    nota = (d.get('nota_fiscal') or '').strip()
    previsao = util.para_data(d.get('previsao')) if (d.get('previsao') or '').strip() else None
    obs = (d.get('obs') or '').strip()
    erros = []
    if not convenio:
        erros.append('Selecione o convênio (ou PARTICULAR).')
    if not referencia:
        erros.append('Informe a data de referência.')
    if valor is None or valor <= 0:
        erros.append('Informe o valor faturado.')
    if not protocolo:
        erros.append('Informe o protocolo do faturamento.')
    if not guias:
        erros.append('Informe a quantidade de guias faturadas (um número maior que zero).')
    if (d.get('previsao') or '').strip() and not previsao:
        erros.append('Data de previsão inválida.')
    for campo, valor_campo in (('protocolo', protocolo), ('nota_fiscal', nota), ('obs', obs)):
        if len(valor_campo) > LIMITES[campo]:
            erros.append('O campo “%s” aceita no máximo %d caracteres.' % (campo.replace('_', ' '), LIMITES[campo]))
    if erros:
        raise ErroFatura(' '.join(erros))
    avisos = []
    if db.execute('SELECT 1 FROM faturas WHERE convenio=? AND UPPER(protocolo)=? AND id<>?', (convenio, protocolo.upper(), fid or 0)).fetchone():
        avisos.append('Já existe outra fatura de %s com o protocolo %s. Confira se não é duplicada.' % (convenio, protocolo))
    return {'convenio': convenio, 'referencia': referencia.isoformat(), 'valor_bruto': valor, 'protocolo': protocolo, 'qtd_guias': guias,
            'nota_fiscal': nota or None, 'previsao': previsao.isoformat() if previsao else None, 'obs': obs or None}, avisos


def criar(db, usuario, d):
    """Cadastra a fatura. Sem nota fiscal fica FATURADO; com nota fiscal informada já nasce com a nota emitida. Devolve (id, avisos)."""
    dados, avisos = validar(db, d)
    status = NF_EMITIDA if dados['nota_fiscal'] else FATURADO
    cur = db.execute('INSERT INTO faturas (convenio, referencia, nota_fiscal, valor_bruto, tributos, valor_liquido, previsao, obs, status, protocolo, '
                     'qtd_guias, nf_emitida_em, nf_emitida_por, usuario, criado_em) VALUES (?,?,?,?,0,?,?,?,?,?,?,?,?,?,?)',
                     (dados['convenio'], dados['referencia'], dados['nota_fiscal'], dados['valor_bruto'], dados['valor_bruto'], dados['previsao'],
                      dados['obs'], status, dados['protocolo'], dados['qtd_guias'],
                      date.today().isoformat() if dados['nota_fiscal'] else None, usuario if dados['nota_fiscal'] else None, usuario, agora()))
    db.commit()
    return cur.lastrowid, avisos


def atualizar(db, usuario, fid, d):
    """Corrige o cadastro. Em fatura já recebida, refaz o líquido esperado e a glosa com o novo valor faturado."""
    atual = obter(db, fid)
    dados, avisos = validar(db, d, fid)
    status = atual['status']
    if dados['nota_fiscal'] and status == FATURADO:
        status = NF_EMITIDA                       # informar a nota no cadastro equivale a emitir
    elif not dados['nota_fiscal'] and status == NF_EMITIDA:
        status = FATURADO
    emitida_em = atual['nf_emitida_em'] if dados['nota_fiscal'] else None
    if dados['nota_fiscal'] and not emitida_em:
        emitida_em = date.today().isoformat()
    db.execute('UPDATE faturas SET convenio=?, referencia=?, nota_fiscal=?, valor_bruto=?, previsao=?, obs=?, protocolo=?, qtd_guias=?, status=?, '
               'nf_emitida_em=?, nf_emitida_por=?, atualizado_por=?, atualizado_em=? WHERE id=?',
               (dados['convenio'], dados['referencia'], dados['nota_fiscal'], dados['valor_bruto'], dados['previsao'], dados['obs'], dados['protocolo'],
                dados['qtd_guias'], status, emitida_em, usuario if dados['nota_fiscal'] else None, usuario, agora(), fid))
    if status == RECEBIDO:
        _refazer_recebida(db, fid)
    else:   # ainda não recebida: o líquido esperado acompanha o novo valor (tributos antigos, se houver, continuam)
        db.execute('UPDATE faturas SET valor_liquido=ROUND(valor_bruto - COALESCE(tributos, 0), 2) WHERE id=?', (fid,))
    db.commit()
    return avisos


def _refazer_recebida(db, fid):
    r = obter(db, fid)
    trib = r['tributos_recebidos'] or 0
    db.execute('UPDATE faturas SET tributos=?, valor_liquido=?, glosa=? WHERE id=?',
               (trib, round(r['valor_bruto'] - trib, 2), round(r['valor_bruto'] - (r['bruto_recebido'] or 0), 2), fid))


def excluir(db, fid):
    r = obter(db, fid)
    if r['anexo_id'] is not None:
        anexos.apagar(anexos.caminho_de(db), r['anexo_id'])
    db.execute('DELETE FROM faturas WHERE id=?', (fid,))
    db.commit()


# ------------------------------------------------------------------ 2. emissão da nota fiscal
def emitir_nf(db, usuario, fid, numero, data_emissao=None):
    """Informa o número da nota e a data de emissão: FATURADO → NF_EMITIDA. Numa fatura com nota já emitida, corrige o número."""
    r = obter(db, fid)
    if r['status'] == RECEBIDO:
        raise ErroFatura('Esta fatura já foi recebida. Para mexer na nota, reabra o recebimento primeiro.')
    numero = (numero or '').strip()
    if not numero:
        raise ErroFatura('Informe o número da nota fiscal.')
    if len(numero) > LIMITES['nota_fiscal']:
        raise ErroFatura('O número da nota aceita no máximo %d caracteres.' % LIMITES['nota_fiscal'])
    quando = util.para_data(data_emissao) if (data_emissao or '').strip() else date.today()
    if not quando:
        raise ErroFatura('Data de emissão inválida.')
    db.execute("UPDATE faturas SET nota_fiscal=?, status='NF_EMITIDA', nf_emitida_em=?, nf_emitida_por=?, atualizado_por=?, atualizado_em=? WHERE id=?",
               (numero, quando.isoformat(), usuario, usuario, agora(), fid))
    db.commit()


def desfazer_emissao(db, usuario, fid):
    """NF_EMITIDA → FATURADO (a nota foi lançada por engano). Limpa o número e a data."""
    r = obter(db, fid)
    if r['status'] != NF_EMITIDA:
        raise ErroFatura('Só dá para desfazer a emissão de uma fatura com nota emitida e ainda não recebida.')
    db.execute("UPDATE faturas SET nota_fiscal=NULL, status='FATURADO', nf_emitida_em=NULL, nf_emitida_por=NULL, atualizado_por=?, atualizado_em=? WHERE id=?",
               (usuario, agora(), fid))
    db.commit()


# ------------------------------------------------------------------ 3. recebidas
def receber(db, usuario, fid, data_recebimento, banco, bancos, bruto_recebido=None, tributos=None, liquido=None, obs=''):
    """Lança o recebimento e calcula a glosa. `tributos` é opcional (0 se não informado). Bruto recebido − tributos = líquido recebido;
    se o líquido for informado, precisa bater. Devolve a glosa ({'valor','pct','sentido',...})."""
    r = obter(db, fid)
    if r['status'] != NF_EMITIDA:
        raise ErroFatura('Só dá para lançar o recebimento depois de emitir a nota fiscal.' if r['status'] == FATURADO else 'Esta fatura já foi recebida.')
    quando = util.para_data(data_recebimento)
    if not quando:
        raise ErroFatura('Informe a data do recebimento.')
    if banco not in bancos:
        raise ErroFatura('Escolha o banco ou a conta de entrada.')
    bruto = _num(bruto_recebido) if (bruto_recebido or '') != '' else r['valor_bruto']
    trib = (_num(tributos) or 0.0) if (tributos or '') != '' else 0.0
    if bruto is None or bruto < 0:
        raise ErroFatura('Informe o valor bruto recebido.')
    if trib < 0 or trib > bruto:
        raise ErroFatura('Os tributos não podem ser negativos nem maiores que o valor bruto recebido.')
    liq_calc = round(bruto - trib, 2)
    liq = _num(liquido) if (liquido or '') != '' else liq_calc
    if liq is None or abs(liq - liq_calc) > 0.01:
        raise ErroFatura('O valor bruto recebido menos os tributos precisa ser igual ao valor líquido (R$ %s).' % util.moeda(liq_calc))
    obs = (obs or '').strip()[:LIMITES['obs']]
    dif = round(r['valor_bruto'] - bruto, 2)
    db.execute("UPDATE faturas SET status='RECEBIDO', data_recebimento=?, banco_recebimento=?, bruto_recebido=?, tributos_recebidos=?, tributos=?, "
               "valor_liquido=?, valor_recebido=?, glosa=?, quitado_por=?, obs=CASE WHEN ?<>'' THEN ? ELSE obs END, atualizado_por=?, atualizado_em=? WHERE id=?",
               (quando.isoformat(), banco, bruto, trib, trib, round(r['valor_bruto'] - trib, 2), liq_calc, dif, usuario, obs, obs, usuario, agora(), fid))
    db.commit()
    return glosa(obter(db, fid))


def reabrir(db, usuario, fid):
    """Desfaz o recebimento: volta para NF_EMITIDA (ou FATURADO se não houver número de nota)."""
    r = obter(db, fid)
    if r['status'] != RECEBIDO:
        raise ErroFatura('Esta fatura não está recebida.')
    novo = NF_EMITIDA if (r['nota_fiscal'] or '').strip() else FATURADO
    db.execute('UPDATE faturas SET status=?, data_recebimento=NULL, valor_recebido=NULL, banco_recebimento=NULL, bruto_recebido=NULL, tributos_recebidos=NULL, '
               'glosa=NULL, tributos=0, valor_liquido=valor_bruto, quitado_por=NULL, atualizado_por=?, atualizado_em=? WHERE id=?', (novo, usuario, agora(), fid))
    db.commit()


# ------------------------------------------------------------------ protocolo em PDF
def validar_pdf(nome, conteudo):
    if not (nome or '').lower().endswith('.pdf'):
        raise ErroFatura('O protocolo precisa ser um arquivo PDF (.pdf).')
    if not conteudo:
        raise ErroFatura('O arquivo está vazio.')
    if len(conteudo) > MAX_PDF:
        raise ErroFatura('O PDF é grande demais (máximo %d MB).' % (MAX_PDF // 1048576))
    if not conteudo[:1024].lstrip().startswith(b'%PDF-'):
        raise ErroFatura('Este arquivo não parece ser um PDF de verdade.')


def anexar_protocolo(db, usuario, fid, nome, conteudo):
    """Importa (ou troca) o PDF do protocolo da fatura. O conteúdo vai para o anexos.db; o sistema.db guarda só os dados do arquivo."""
    r = obter(db, fid)
    validar_pdf(nome, conteudo)
    caminho = anexos.caminho_de(db)
    if not caminho:
        raise ErroFatura('Importação de arquivos indisponível neste banco.')
    novo = anexos.gravar(caminho, 'faturas', conteudo, origem_id=fid)
    try:
        nome_limpo = ''.join(c for c in (nome or 'protocolo.pdf') if c not in '\\/:*?"<>|\r\n')[:120] or 'protocolo.pdf'
        db.execute('UPDATE faturas SET anexo_id=?, protocolo_nome=?, protocolo_tamanho=?, protocolo_em=?, protocolo_por=?, atualizado_por=?, atualizado_em=? WHERE id=?',
                   (novo, nome_limpo, len(conteudo), agora(), usuario, usuario, agora(), fid))
        db.commit()
    except Exception:
        db.rollback()
        anexos.apagar(caminho, novo)
        raise
    if r['anexo_id'] is not None:   # o PDF antigo sai do anexos.db só depois do novo estar registrado
        anexos.apagar(caminho, r['anexo_id'])


def ler_protocolo(db, fid):
    """(nome do arquivo, bytes) do protocolo, ou levanta ErroFatura se não houver."""
    r = obter(db, fid)
    if r['anexo_id'] is None:
        raise ErroFatura('Esta fatura ainda não tem o PDF do protocolo.')
    conteudo = anexos.ler(anexos.caminho_de(db), r['anexo_id'])
    if conteudo is None:
        raise ErroFatura('O PDF deste protocolo não foi encontrado no banco de anexos.')
    return r['protocolo_nome'] or 'protocolo.pdf', conteudo


def remover_protocolo(db, usuario, fid):
    r = obter(db, fid)
    if r['anexo_id'] is None:
        return
    db.execute('UPDATE faturas SET anexo_id=NULL, protocolo_nome=NULL, protocolo_tamanho=NULL, protocolo_em=NULL, protocolo_por=NULL, atualizado_por=?, atualizado_em=? WHERE id=?',
               (usuario, agora(), fid))
    db.commit()
    anexos.apagar(anexos.caminho_de(db), r['anexo_id'])
