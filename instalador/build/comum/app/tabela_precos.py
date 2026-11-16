"""Tabelas de preços dos exames (particular e outras): regra de negócio, sem rotas nem PDF.
Quem chama confirma a transação (db.commit) e desfaz (db.rollback) quando recebe ErroTabela."""
from datetime import date
import math
import re
import unicodedata

from . import util
from .db import agora

# Convênios exibidos lado a lado na pesquisa rápida de valores.
CONVENIOS_CONSULTA = (
    ('sms', 'SMS'),
    ('particular', 'Particular'),
    ('maismed', 'MAISMED'),
)


def _sem_acento(txt):
    s = unicodedata.normalize('NFD', str(txt or ''))
    return ''.join(c for c in s if unicodedata.category(c) != 'Mn').upper().strip()


def _chave_convenio(nome, extras=None):
    """Identifica se o nome do convênio ou da tabela de preços corresponde a SMS, Particular ou MAISMED."""
    s = _sem_acento(nome)
    if not s:
        return None
    if extras and s in extras:
        return extras[s]
    comp = re.sub(r'[^A-Z0-9]', '', s)
    palavras = set(re.findall(r'[A-Z0-9]+', s))
    if 'MAISMED' in comp or ('MAIS' in palavras and 'MED' in palavras):
        return 'maismed'
    if 'PARTICULAR' in comp or 'PART' in palavras:
        return 'particular'
    if 'SMS' in palavras or comp in ('SMS', 'TABELASMS', 'PRECOSMS', 'CONVENIOSMS') or comp.startswith('SMS') or comp.endswith('SMS'):
        return 'sms'
    if extras:
        for nome_conv, ch in extras.items():
            if nome_conv and nome_conv in s:
                return ch
    return None


class ErroTabela(Exception):
    pass


def _valor(bruto, linha=None):
    """Valor digitado ('1.250,00', '1250', '1.250' como milhar) -> float, ou None se vazio. Texto inválido levanta ErroTabela."""
    s = (str(bruto) if bruto is not None else '').replace('R$', '').strip()
    if not s:
        return None
    if re.fullmatch(r'\d{1,3}(\.\d{3})+', s):   # "1.250" é milhar no padrão brasileiro
        s = s.replace('.', '')
    v = util.para_valor(s)
    if v is None or v < 0:
        raise ErroTabela('Valor inválido%s: "%s".' % (' na linha %d' % linha if linha else '', bruto))
    return round(v, 2)


def listar(db):
    return db.execute('SELECT t.*, (SELECT COUNT(*) FROM tabela_preco_itens i WHERE i.tabela_id=t.id) AS n_itens, '
                      '(SELECT COUNT(*) FROM tabela_preco_itens i WHERE i.tabela_id=t.id AND i.valor IS NULL) AS sem_valor '
                      'FROM tabelas_preco t ORDER BY t.ativa DESC, t.vigencia DESC, t.nome').fetchall()


def obter(db, tid):
    """(tabela, itens) em ordem, ou None se a tabela não existe."""
    tabela = db.execute('SELECT * FROM tabelas_preco WHERE id=?', (tid,)).fetchone()
    if not tabela:
        return None
    itens = db.execute('SELECT * FROM tabela_preco_itens WHERE tabela_id=? ORDER BY ordem, descricao, id', (tid,)).fetchall()
    return tabela, itens


def salvar_tabela(db, dados, usuario, tid=None):
    """Grava nome, vigência, ativa e observação. Sem `tid` cria a tabela e devolve o id novo."""
    nome = util.maiusculas(dados.get('nome'))
    if not nome:
        raise ErroTabela('Informe o nome da tabela.')
    vig_bruta = (dados.get('vigencia') or '').strip()
    vigencia = None
    if vig_bruta:
        d = util.para_data(vig_bruta)
        if not d:
            raise ErroTabela('Vigência inválida. Use a data no formato dd/mm/aaaa.')
        vigencia = d.isoformat()
    ativa = 1 if str(dados.get('ativa', '1')) in ('1', 'on', 'true') else 0
    obs = (dados.get('obs') or '').strip() or None
    if tid is None:
        cur = db.execute('INSERT INTO tabelas_preco (nome, vigencia, obs, ativa, criado_em, criado_por, atualizado_em, atualizado_por) '
                         'VALUES (?,?,?,?,?,?,?,?)', (nome, vigencia, obs, ativa, agora(), usuario, agora(), usuario))
        return cur.lastrowid
    existe = db.execute('SELECT 1 FROM tabelas_preco WHERE id=?', (tid,)).fetchone()
    if not existe:
        raise ErroTabela('Tabela não encontrada.')
    db.execute('UPDATE tabelas_preco SET nome=?, vigencia=?, obs=?, ativa=?, atualizado_em=?, atualizado_por=? WHERE id=?',
               (nome, vigencia, obs, ativa, agora(), usuario, tid))
    return tid


def salvar_itens(db, tid, itens):
    """Substitui todos os itens da tabela pela lista recebida. Cada item é um dicionário com codigo, descricao, valor, obs e
    exame_id (opcional). Linha sem descrição é ignorada. Sem exame_id válido, a descrição que bate com um exame cadastrado
    grava o exame. A ordem é a posição na lista."""
    exames = {e['nome'].upper(): e['id'] for e in db.execute('SELECT id, nome FROM exames')}
    ids_validos = set(exames.values())
    linhas = []
    for n, it in enumerate(itens, start=1):
        descricao = util.maiusculas(it.get('descricao'))
        if not descricao:
            continue
        exame_id = None
        if str(it.get('exame_id') or '').isdigit() and int(it['exame_id']) in ids_validos:
            exame_id = int(it['exame_id'])
        else:
            exame_id = exames.get(descricao)
        linhas.append((tid, exame_id, (it.get('codigo') or '').strip() or None, descricao,
                       _valor(it.get('valor'), n), (it.get('obs') or '').strip() or None, len(linhas)))
    db.execute('DELETE FROM tabela_preco_itens WHERE tabela_id=?', (tid,))
    db.executemany('INSERT INTO tabela_preco_itens (tabela_id, exame_id, codigo, descricao, valor, obs, ordem) '
                   'VALUES (?,?,?,?,?,?,?)', linhas)
    db.execute('UPDATE tabelas_preco SET atualizado_em=? WHERE id=?', (agora(), tid))
    return len(linhas)


def _proxima_ordem(db, tid):
    return db.execute('SELECT COALESCE(MAX(ordem), -1) + 1 FROM tabela_preco_itens WHERE tabela_id=?', (tid,)).fetchone()[0]


def adicionar_exames(db, tid):
    """Acrescenta os exames ativos que ainda não estão na tabela, sem valor. Devolve quantos entraram."""
    ordem = _proxima_ordem(db, tid)
    faltam = db.execute('SELECT id, nome FROM exames WHERE ativo=1 AND id NOT IN '
                        '(SELECT exame_id FROM tabela_preco_itens WHERE tabela_id=? AND exame_id IS NOT NULL) ORDER BY ordem, nome',
                        (tid,)).fetchall()
    for e in faltam:
        db.execute('INSERT INTO tabela_preco_itens (tabela_id, exame_id, codigo, descricao, valor, obs, ordem) VALUES (?,?,?,?,?,?,?)',
                   (tid, e['id'], None, util.maiusculas(e['nome']), None, None, ordem))
        ordem += 1
    return len(faltam)


def copiar_convenio(db, tid, convenio_id):
    """Copia o valor de cada exame que o convênio tem preenchido: atualiza o item do mesmo exame ou acrescenta o item.
    Devolve quantos valores foram copiados."""
    if not db.execute('SELECT 1 FROM convenios WHERE id=?', (convenio_id,)).fetchone():
        raise ErroTabela('Convênio não encontrado.')
    valores = db.execute('SELECT e.id, e.nome, cv.valor FROM convenio_valores cv JOIN exames e ON e.id=cv.exame_id '
                         'WHERE cv.convenio_id=? ORDER BY e.ordem, e.nome', (convenio_id,)).fetchall()
    ordem = _proxima_ordem(db, tid)
    for v in valores:
        cur = db.execute('UPDATE tabela_preco_itens SET valor=? WHERE tabela_id=? AND exame_id=?', (v['valor'], tid, v['id']))
        if cur.rowcount == 0:
            db.execute('INSERT INTO tabela_preco_itens (tabela_id, exame_id, codigo, descricao, valor, obs, ordem) VALUES (?,?,?,?,?,?,?)',
                       (tid, v['id'], None, util.maiusculas(v['nome']), v['valor'], None, ordem))
            ordem += 1
    return len(valores)


def _arredondar(valor, arredondar):
    if arredondar == '':
        return math.floor(valor * 100 + 0.5) / 100
    m = int(arredondar)
    return math.floor(valor / m + 0.5) * m


def reajustar(db, tid, percentual, arredondar):
    """Multiplica cada valor por (1 + percentual/100). `arredondar`: '' = centavos; '1', '5' ou '10' = múltiplo mais próximo.
    Itens sem valor ficam sem valor. Devolve quantos valores mudaram."""
    p = util.para_valor(str(percentual).replace('%', '').strip()) if str(percentual or '').strip() else None
    if p is None:
        raise ErroTabela('Informe o percentual do reajuste (pode ser negativo).')
    if arredondar not in ('', '1', '5', '10'):
        raise ErroTabela('Arredondamento inválido.')
    mudou = 0
    for it in db.execute('SELECT id, valor FROM tabela_preco_itens WHERE tabela_id=? AND valor IS NOT NULL', (tid,)).fetchall():
        novo = max(0.0, _arredondar(it['valor'] * (1 + p / 100), arredondar))
        if round(novo, 2) != round(it['valor'], 2):
            db.execute('UPDATE tabela_preco_itens SET valor=? WHERE id=?', (round(novo, 2), it['id']))
            mudou += 1
    return mudou


def duplicar(db, tid, novo_nome, usuario):
    """Cria outra tabela com os mesmos itens (sem vigência, para preencher na próxima). Devolve o id da nova."""
    origem = obter(db, tid)
    if not origem:
        raise ErroTabela('Tabela não encontrada.')
    tabela, itens = origem
    nid = salvar_tabela(db, {'nome': novo_nome, 'vigencia': '', 'obs': tabela['obs'], 'ativa': 1}, usuario)
    db.executemany('INSERT INTO tabela_preco_itens (tabela_id, exame_id, codigo, descricao, valor, obs, ordem) VALUES (?,?,?,?,?,?,?)',
                   [(nid, i['exame_id'], i['codigo'], i['descricao'], i['valor'], i['obs'], i['ordem']) for i in itens])
    return nid


def excluir(db, tid):
    db.execute('DELETE FROM tabela_preco_itens WHERE tabela_id=?', (tid,))
    db.execute('DELETE FROM tabelas_preco WHERE id=?', (tid,))


def buscar_itens(db, termo, limite=20):
    """Itens das tabelas ativas cujo código ou descrição contém o termo (para as guias SP/SADT)."""
    t = util.maiusculas(termo)
    if not t:
        return []
    padrao = '%' + t + '%'
    linhas = db.execute('SELECT i.codigo, i.descricao, i.valor, t.nome AS tabela FROM tabela_preco_itens i '
                        'JOIN tabelas_preco t ON t.id=i.tabela_id WHERE t.ativa=1 AND (UPPER(i.codigo) LIKE ? OR UPPER(i.descricao) LIKE ?) '
                        'ORDER BY i.descricao, t.nome LIMIT ?', (padrao, padrao, int(limite))).fetchall()
    return [dict(r) for r in linhas]


def _convenios_cadastrados(db):
    """Descobre como SMS, Particular e MAISMED (ex.: 'MAIS MED' ou 'MAISMED') estão na tabela `convenios`."""
    por_chave = {ch: None for ch, _rot in CONVENIOS_CONSULTA}
    extras = {}
    linhas = db.execute('SELECT id, nome, ativo, valor_mibi, valor_ossea, valor_tgi, valor_paratgi, valor_galio '
                        'FROM convenios ORDER BY ativo DESC, id DESC').fetchall()
    for r in linhas:
        ch = _chave_convenio(r['nome'])
        if ch in por_chave:
            extras[_sem_acento(r['nome'])] = ch
            if por_chave[ch] is None:
                por_chave[ch] = dict(r)
    return por_chave, extras


def tabelas_vigentes(db, data_ref=None):
    """Para cada convênio da pesquisa rápida (sms, particular, maismed), devolve a tabela de preços ativa e vigente."""
    hoje = (data_ref or date.today()).isoformat() if hasattr(data_ref or date.today(), 'isoformat') else str(data_ref)
    _convs, extras = _convenios_cadastrados(db)
    candidatas = {ch: [] for ch, _rot in CONVENIOS_CONSULTA}
    ativas = db.execute('SELECT t.*, (SELECT COUNT(*) FROM tabela_preco_itens i WHERE i.tabela_id=t.id) AS n_itens '
                        'FROM tabelas_preco t WHERE t.ativa=1').fetchall()
    for t in ativas:
        ch = _chave_convenio(t['nome'], extras)
        if ch in candidatas:
            candidatas[ch].append(dict(t))

    def _chave_ordem(t):
        vig = (t.get('vigencia') or '').strip()
        tem_itens = 1 if (t.get('n_itens') or 0) > 0 else 0
        if vig and vig <= hoje:
            cat = 2
        elif not vig:
            cat = 1
        else:
            cat = 0
        return (tem_itens, cat, vig, t['id'])

    escolhidas = {}
    for ch, _rot in CONVENIOS_CONSULTA:
        lista = candidatas[ch]
        escolhidas[ch] = max(lista, key=_chave_ordem) if lista else None
    return escolhidas


def _itens_do_convenio(db, ch, tabela, convenio):
    """Itens de preço de um convênio: prioriza a tabela de preços ativa/vigente; se não houver, usa `convenio_valores`."""
    if tabela:
        linhas = db.execute(
            'SELECT i.exame_id, i.codigo, i.descricao, i.valor, i.obs, i.ordem, e.nome AS exame_nome '
            'FROM tabela_preco_itens i LEFT JOIN exames e ON e.id=i.exame_id '
            'WHERE i.tabela_id=? ORDER BY i.ordem, i.descricao, i.id',
            (tabela['id'],),
        ).fetchall()
        return [dict(r) for r in linhas]
    if not convenio or not convenio.get('ativo'):
        return []
    linhas = db.execute(
        'SELECT e.id AS exame_id, NULL AS codigo, e.nome AS descricao, cv.valor, NULL AS obs, e.ordem, e.nome AS exame_nome '
        'FROM convenio_valores cv JOIN exames e ON e.id=cv.exame_id '
        'WHERE cv.convenio_id=? AND e.ativo=1 ORDER BY e.ordem, e.nome',
        (convenio['id'],),
    ).fetchall()
    if linhas:
        return [dict(r) for r in linhas]
    # Fallback para colunas legadas na própria tabela convenios
    saida = []
    for ordem, (col, nome_ex) in enumerate((('valor_mibi', 'MIBI'), ('valor_ossea', 'ÓSSEA'), ('valor_tgi', 'TGI'),
                                            ('valor_paratgi', 'PARATGI'), ('valor_galio', 'GALIO'))):
        val = convenio.get(col)
        if val is not None:
            ex = db.execute('SELECT id, nome FROM exames WHERE nome=? COLLATE NOCASE', (nome_ex,)).fetchone()
            saida.append({'exame_id': ex['id'] if ex else None, 'codigo': None,
                          'descricao': ex['nome'] if ex else nome_ex, 'valor': val, 'obs': None,
                          'ordem': ordem, 'exame_nome': ex['nome'] if ex else nome_ex})
    return saida


def consulta_rapida(db, termo=''):
    """Monta a grade comparativa de preços entre SMS, Particular e MAISMED a partir da tabela ativa/vigente de cada um.
    Quando um convênio não tem preço para o exame, o valor correspondente fica `None` (exibido como '—' na tela)."""
    convenios, _extras = _convenios_cadastrados(db)
    tabelas = tabelas_vigentes(db)
    linhas = []
    por_exame_id = {}
    por_desc = {}
    por_codigo = {}

    for ch, _rotulo in CONVENIOS_CONSULTA:
        for it in _itens_do_convenio(db, ch, tabelas.get(ch), convenios.get(ch)):
            desc_limpa = util.maiusculas(it.get('descricao'))
            if not desc_limpa:
                continue
            cod_limpo = (it.get('codigo') or '').strip() or None
            exame_id = it.get('exame_id')
            exame_nome = util.maiusculas(it.get('exame_nome')) or desc_limpa
            chave_desc = re.sub(r'\s+', ' ', _sem_acento(desc_limpa))
            chave_cod = _sem_acento(cod_limpo) if cod_limpo else None

            reg = (
                (por_exame_id.get(exame_id) if exame_id else None)
                or (por_desc.get(chave_desc) if chave_desc else None)
                or (por_codigo.get(chave_cod) if chave_cod else None)
            )
            if reg is None:
                reg = {
                    'codigo': cod_limpo or '',
                    'descricao': desc_limpa,
                    'exame_id': exame_id,
                    'exame_nome': exame_nome,
                    'sms': None,
                    'particular': None,
                    'maismed': None,
                    'valores': {'sms': None, 'particular': None, 'maismed': None},
                }
                linhas.append(reg)
            else:
                if not reg['codigo'] and cod_limpo:
                    reg['codigo'] = cod_limpo
                if not reg['exame_id'] and exame_id:
                    reg['exame_id'] = exame_id

            if exame_id and exame_id not in por_exame_id:
                por_exame_id[exame_id] = reg
            if chave_desc and chave_desc not in por_desc:
                por_desc[chave_desc] = reg
            if chave_cod and chave_cod not in por_codigo:
                por_codigo[chave_cod] = reg

            valor = it.get('valor')
            if reg[ch] is None and valor is not None:
                reg[ch] = round(float(valor), 2)
                reg['valores'][ch] = reg[ch]

    linhas.sort(key=lambda r: (_sem_acento(r['descricao']), _sem_acento(r['codigo'])))

    partes = _sem_acento(termo).split()
    if partes:
        filtradas = []
        for r in linhas:
            alvo = _sem_acento('%s %s %s' % (r['codigo'], r['descricao'], r.get('exame_nome') or ''))
            if all(p in alvo for p in partes):
                filtradas.append(r)
        linhas = filtradas

    return {
        'convenios': convenios,
        'tabelas': tabelas,
        'itens': linhas,
        'total': len(linhas),
    }


consultar_precos = consulta_rapida
