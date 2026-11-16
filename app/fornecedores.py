"""Fornecedores do contas a pagar: cadastro (manual ou pela consulta do CNPJ na internet), parcelamento de compras
e relatório de contas por fornecedor."""
from __future__ import annotations

import calendar
import json
import urllib.error
import urllib.request
import uuid
from datetime import date

from . import util
from .db import agora

TIMEOUT_S = 8
FONTES = (
    ('BrasilAPI', 'https://brasilapi.com.br/api/cnpj/v1/%s'),
    ('ReceitaWS', 'https://receitaws.com.br/v1/cnpj/%s'),
)
MAX_PARCELAS = 60


class ErroFornecedor(ValueError):
    """Erro de validação mostrado ao usuário."""


# ------------------------------------------------------------------ CNPJ
def cnpj_digitos(txt):
    return ''.join(c for c in str(txt or '') if c.isdigit())


def cnpj_valido(txt):
    d = cnpj_digitos(txt)
    if len(d) != 14 or len(set(d)) == 1:
        return False

    def dv(base):
        pesos = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2][-len(base):] if len(base) == 12 else [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        r = sum(int(a) * b for a, b in zip(base, pesos)) % 11
        return '0' if r < 2 else str(11 - r)
    return d[12] == dv(d[:12]) and d[13] == dv(d[:13])


def cnpj_formatado(txt):
    d = cnpj_digitos(txt)
    if len(d) != 14:
        return str(txt or '')
    return '%s.%s.%s/%s-%s' % (d[:2], d[2:5], d[5:8], d[8:12], d[12:])


def _texto(v):
    return str(v).strip() if v not in (None, 'None') else ''


def _normalizar(fonte, j):
    """Dados da consulta no formato do cadastro, qualquer que seja a fonte."""
    if fonte == 'BrasilAPI':
        rua = ' '.join(p for p in (_texto(j.get('logradouro')), _texto(j.get('numero')), _texto(j.get('complemento'))) if p)
        return {'nome': _texto(j.get('razao_social')), 'fantasia': _texto(j.get('nome_fantasia')),
                'telefone': _texto(j.get('ddd_telefone_1')), 'email': _texto(j.get('email')).lower(),
                'endereco': ', '.join(p for p in (rua, _texto(j.get('bairro')), _texto(j.get('cep'))) if p),
                'cidade': _texto(j.get('municipio')), 'uf': _texto(j.get('uf')).upper(),
                'situacao': _texto(j.get('descricao_situacao_cadastral'))}
    rua = ' '.join(p for p in (_texto(j.get('logradouro')), _texto(j.get('numero')), _texto(j.get('complemento'))) if p)
    return {'nome': _texto(j.get('nome')), 'fantasia': _texto(j.get('fantasia')),
            'telefone': _texto(j.get('telefone')).split('/')[0].strip(), 'email': _texto(j.get('email')).lower(),
            'endereco': ', '.join(p for p in (rua, _texto(j.get('bairro')), _texto(j.get('cep'))) if p),
            'cidade': _texto(j.get('municipio')), 'uf': _texto(j.get('uf')).upper(), 'situacao': _texto(j.get('situacao'))}


def _baixar_json(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Nucleleste/1.4', 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:   # noqa: S310 (endereços fixos acima)
        return json.loads(r.read().decode('utf-8'))


def consultar_cnpj(cnpj, baixar=None):
    """Busca o CNPJ na internet (BrasilAPI e, se falhar, ReceitaWS). `baixar` existe para os testes."""
    baixar = baixar or _baixar_json
    d = cnpj_digitos(cnpj)
    if not cnpj_valido(d):
        raise ErroFornecedor('CNPJ inválido. Confira os 14 números.')
    ultimo = None
    for fonte, modelo in FONTES:
        try:
            j = baixar(modelo % d)
        except urllib.error.HTTPError as e:
            ultimo = 'CNPJ não encontrado na consulta.' if e.code in (400, 404) else 'O serviço de consulta está indisponível.'
            if e.code in (400, 404):
                break
            continue
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            ultimo = 'Sem acesso à internet para consultar o CNPJ. Cadastre manualmente.'
            continue
        if isinstance(j, dict) and j.get('status') == 'ERROR':
            ultimo = _texto(j.get('message')) or 'CNPJ não encontrado na consulta.'
            continue
        dados = _normalizar(fonte, j if isinstance(j, dict) else {})
        if dados['nome']:
            dados['cnpj'] = cnpj_formatado(d)
            dados['fonte'] = fonte
            return dados
        ultimo = 'A consulta não devolveu dados deste CNPJ.'
    raise ErroFornecedor(ultimo or 'Não foi possível consultar o CNPJ agora. Cadastre manualmente.')


# ------------------------------------------------------------------ cadastro
CAMPOS = ('cnpj', 'nome', 'fantasia', 'telefone', 'email', 'endereco', 'cidade', 'uf', 'contato', 'obs')


def listar(db, busca='', so_ativos=False):
    where, params = ['1=1'], []
    if so_ativos:
        where.append('ativo=1')
    busca = (busca or '').strip()
    if busca:
        like = '%' + busca.upper() + '%'
        sem_pontuacao = "REPLACE(REPLACE(REPLACE(COALESCE(cnpj,''),'.',''),'/',''),'-','')"
        where.append("(UPPER(nome) LIKE ? OR UPPER(COALESCE(fantasia,'')) LIKE ? OR %s LIKE ?)" % sem_pontuacao)
        params += [like, like, '%' + cnpj_digitos(busca) + '%' if cnpj_digitos(busca) else like]
    return [dict(r) for r in db.execute(
        'SELECT f.*, (SELECT COUNT(*) FROM contas c WHERE c.fornecedor_id=f.id) AS contas, '
        "(SELECT COALESCE(SUM(c.valor),0) FROM contas c WHERE c.fornecedor_id=f.id AND c.status='ABERTO') AS em_aberto "
        'FROM fornecedores f WHERE %s ORDER BY UPPER(nome)' % ' AND '.join(where), params)]


def obter(db, fid):
    r = db.execute('SELECT * FROM fornecedores WHERE id=?', (fid,)).fetchone()
    return dict(r) if r else None


def salvar(db, dados, usuario, fid=None):
    """Cria ou altera. O CNPJ é opcional (fornecedor sem CNPJ), mas, se informado, precisa ser válido e único."""
    f = {k: _texto(dados.get(k)) for k in CAMPOS}
    f['nome'] = util.maiusculas(f['nome'])
    f['fantasia'] = util.maiusculas(f['fantasia'])
    f['uf'] = f['uf'].upper()[:2]
    f['email'] = f['email'].lower()
    if not f['nome']:
        raise ErroFornecedor('Informe o nome (razão social) do fornecedor.')
    if f['cnpj']:
        if not cnpj_valido(f['cnpj']):
            raise ErroFornecedor('CNPJ inválido. Confira os 14 números ou deixe em branco.')
        f['cnpj'] = cnpj_formatado(f['cnpj'])
        outro = db.execute('SELECT id, nome FROM fornecedores WHERE cnpj=? AND id<>?', (f['cnpj'], fid or 0)).fetchone()
        if outro:
            raise ErroFornecedor('Este CNPJ já está cadastrado para %s.' % outro['nome'])
    else:
        f['cnpj'] = None
    if f['telefone']:
        f['telefone'] = util.telefone_padrao(f['telefone'])
    ativo = 0 if str(dados.get('ativo', '1')) in ('0', 'false') else 1
    if fid:
        if not obter(db, fid):
            raise ErroFornecedor('Este fornecedor não existe mais.')
        db.execute('UPDATE fornecedores SET cnpj=?, nome=?, fantasia=?, telefone=?, email=?, endereco=?, cidade=?, uf=?, '
                   'contato=?, obs=?, ativo=? WHERE id=?',
                   (f['cnpj'], f['nome'], f['fantasia'], f['telefone'], f['email'], f['endereco'], f['cidade'], f['uf'],
                    f['contato'], f['obs'], ativo, fid))
        # o nome gravado nas contas acompanha o cadastro
        db.execute('UPDATE contas SET fornecedor=? WHERE fornecedor_id=?', (f['nome'], fid))
    else:
        cur = db.execute('INSERT INTO fornecedores (cnpj, nome, fantasia, telefone, email, endereco, cidade, uf, contato, obs, ativo, '
                         'criado_em, criado_por) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                         (f['cnpj'], f['nome'], f['fantasia'], f['telefone'], f['email'], f['endereco'], f['cidade'], f['uf'],
                          f['contato'], f['obs'], ativo, agora(), usuario))
        fid = cur.lastrowid
    db.commit()
    return fid


def excluir(db, fid):
    """Remove o cadastro. As contas continuam com o nome do fornecedor (só perdem o vínculo)."""
    f = obter(db, fid)
    if not f:
        raise ErroFornecedor('Este fornecedor não existe mais.')
    db.execute('UPDATE contas SET fornecedor_id=NULL WHERE fornecedor_id=?', (fid,))
    db.execute('DELETE FROM fornecedores WHERE id=?', (fid,))
    db.commit()
    return f


# ------------------------------------------------------------------ parcelamento
def somar_meses(base, n):
    """Mesmo dia `n` meses depois; se o mês não tiver o dia (ex.: 31), usa o último dia do mês."""
    mes = base.month - 1 + n
    ano, mes = base.year + mes // 12, mes % 12 + 1
    return date(ano, mes, min(base.day, calendar.monthrange(ano, mes)[1]))


def dividir(valor, n):
    """Divide em `n` parcelas de centavos exatos; a diferença de arredondamento fica na última."""
    cada = round(valor / n, 2)
    parcelas = [cada] * n
    parcelas[-1] = round(valor - cada * (n - 1), 2)
    return parcelas


def planejar_parcelas(valor, vencimento, n, valor_e_total=True, datas=None):
    """[(número, vencimento ISO, valor)] de uma compra parcelada. Por padrão uma parcela por mês; `datas` (uma por parcela,
    texto vazio = padrão mensal) permite escolher manualmente o vencimento de cada uma, em qualquer intervalo."""
    if not 2 <= n <= MAX_PARCELAS:
        raise ErroFornecedor('O número de parcelas deve ficar entre 2 e %d.' % MAX_PARCELAS)
    base = util.para_data(vencimento)
    if not base or valor is None or valor <= 0:
        raise ErroFornecedor('Informe um valor e um vencimento válidos para parcelar.')
    valores = dividir(valor, n) if valor_e_total else [round(valor, 2)] * n
    saida = []
    for i in range(n):
        texto = (datas[i] if datas and i < len(datas) else '') or ''
        if str(texto).strip():
            d = util.para_data(texto)
            if not d:
                raise ErroFornecedor('A data da parcela %d é inválida.' % (i + 1))
        else:
            d = somar_meses(base, i)
        saida.append((i + 1, d.isoformat(), valores[i]))
    return saida


def criar_parcelas(db, dados_base, parcelas, usuario):
    """Lança uma conta por parcela, todas ligadas pelo mesmo grupo. `dados_base`: descricao, categoria, obs, fornecedor,
    fornecedor_id, nota_fiscal. Devolve os ids criados."""
    grupo = uuid.uuid4().hex
    ids = []
    for numero, venc, valor in parcelas:
        cur = db.execute(
            'INSERT INTO contas (descricao, categoria, vencimento, valor, obs, fornecedor, fornecedor_id, nota_fiscal, status, usuario, '
            "parcela_n, parcela_total, parcela_grupo) VALUES (?,?,?,?,?,?,?,?,'ABERTO',?,?,?,?)",
            (dados_base['descricao'], dados_base['categoria'], venc, valor, dados_base.get('obs'), dados_base.get('fornecedor'),
             dados_base.get('fornecedor_id'), dados_base.get('nota_fiscal'), usuario, numero, len(parcelas), grupo))
        ids.append(cur.lastrowid)
    db.commit()
    return ids


def excluir_parcelas_abertas(db, conta_id):
    """Apaga as parcelas ainda em aberto da compra a que a conta pertence. Devolve quantas foram."""
    c = db.execute('SELECT parcela_grupo FROM contas WHERE id=?', (conta_id,)).fetchone()
    if not c or not c['parcela_grupo']:
        raise ErroFornecedor('Esta conta não faz parte de uma compra parcelada.')
    from . import contas_lotes   # parcela que estava em lote de pagamento: sai do lote também
    for r in db.execute("SELECT id FROM contas WHERE parcela_grupo=? AND status='ABERTO'", (c['parcela_grupo'],)).fetchall():
        contas_lotes.ao_excluir(db, r['id'])
    cur = db.execute("DELETE FROM contas WHERE parcela_grupo=? AND status='ABERTO'", (c['parcela_grupo'],))
    db.commit()
    return cur.rowcount


def rotulo_parcela(c):
    """'1/3' para parcelas; vazio para contas comuns."""
    try:
        if c['parcela_total']:
            return '%d/%d' % (c['parcela_n'], c['parcela_total'])
    except (KeyError, IndexError, TypeError):
        pass
    return ''


# ------------------------------------------------------------------ relatório por fornecedor
def relatorio(db, de, ate, status='', fornecedor_id=None):
    """Contas do período (por vencimento) agrupadas por fornecedor, com o total em aberto e o total pago."""
    where, params = ['c.vencimento BETWEEN ? AND ?'], [de.isoformat(), ate.isoformat()]
    if status in ('ABERTO', 'PAGO'):
        where.append('c.status=?')
        params.append(status)
    if fornecedor_id:
        where.append('c.fornecedor_id=?')
        params.append(fornecedor_id)
    linhas = db.execute(
        'SELECT c.*, f.nome AS f_nome, f.cnpj AS f_cnpj FROM contas c LEFT JOIN fornecedores f ON f.id=c.fornecedor_id '
        'WHERE %s ORDER BY c.vencimento, c.id' % ' AND '.join(where), params).fetchall()
    grupos = {}
    for c in linhas:
        nome = c['f_nome'] or util.maiusculas(c['fornecedor']) or 'SEM FORNECEDOR'
        g = grupos.setdefault(nome, {'nome': nome, 'cnpj': c['f_cnpj'] or '', 'contas': [], 'aberto': 0.0, 'pago': 0.0})
        item = dict(c)
        item['parcela'] = rotulo_parcela(c)
        g['contas'].append(item)
        g['pago' if c['status'] == 'PAGO' else 'aberto'] += c['valor'] or 0
    lista = sorted(grupos.values(), key=lambda g: (g['nome'] == 'SEM FORNECEDOR', g['nome']))
    for g in lista:
        g['aberto'], g['pago'] = round(g['aberto'], 2), round(g['pago'], 2)
        g['total'] = round(g['aberto'] + g['pago'], 2)
    return {'de': de.isoformat(), 'ate': ate.isoformat(), 'status': status, 'grupos': lista,
            'aberto': round(sum(g['aberto'] for g in lista), 2), 'pago': round(sum(g['pago'] for g in lista), 2),
            'total': round(sum(g['total'] for g in lista), 2), 'quantidade': len(linhas)}
