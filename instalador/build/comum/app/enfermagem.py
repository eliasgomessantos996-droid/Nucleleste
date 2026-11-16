"""Módulo Enfermagem e Segurança: profissionais com assinatura, carrinho de emergência, medicamentos e insumos, equipamentos médicos,
esterilização e radioproteção da enfermagem, com avisos de vencimento enviados ao responsável de cada área.

O profissional é o mesmo funcionário/usuário que o sistema já tem (módulo de ponto → usuário): aqui só se guarda a assinatura e o conselho
(`enf_profissionais`), sem cadastro paralelo de pessoas. As tabelas têm o prefixo `enf_` e são criadas por `garantir(db)`."""
from __future__ import annotations

import io
import json
from datetime import date, datetime, timedelta

from . import anexos
from .db import agora

AREAS = (('carrinho', 'Carrinho de emergência'), ('medicamentos', 'Medicamentos e insumos'), ('equipamentos', 'Equipamentos médicos'),
         ('esterilizacao', 'Esterilização'), ('radioprotecao', 'Radioproteção da enfermagem'))
ROTULO_AREA = dict(AREAS)
CONSELHOS = ('COREN', 'CRM', 'CRF', 'CRBM', 'CREFITO', 'CRTR', 'Outro')
UFS = ('AC', 'AL', 'AP', 'AM', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 'MT', 'MS', 'MG', 'PA', 'PB', 'PR', 'PE', 'PI', 'RJ', 'RN', 'RS', 'RO', 'RR', 'SC', 'SP', 'SE', 'TO')
FASES = (0, 1, 7, 15, 30, 60)          # mesmos dias do aviso de documentos de fiscalização
ESCALA_DIAS = 3                        # vencido há tantos dias sem providência: o aviso sobe para a gerência
ASSINATURA_MAX = 2 * 1024 * 1024
CHECKLIST_CARRINHO = ('Lacre íntegro e número conferido', 'Itens organizados e identificados', 'Validades conferidas', 'Carrinho limpo',
                      'Cardioversor/desfibrilador conectado e com bateria', 'Oxigênio, máscara e aspirador funcionando')
CHECKLIST_KIT = ('Kit completo e no lugar indicado', 'Absorventes, luvas e sobrecalçados disponíveis', 'Sinalização e fita de isolamento', 'Sacos de rejeito identificados',
                 'Validades conferidas')
TIPOS_EQUIP = ('Cardioversor/desfibrilador', 'Monitor multiparamétrico', 'ECG', 'Oxímetro', 'Bomba de infusão', 'Aspirador', 'Outro')
CHECKLIST_CARDIOVERSOR = (('carga', 'Carga (teste de descarga)'), ('bateria', 'Bateria carregada'), ('pas', 'Pás / eletrodos em bom estado'), ('fita', 'Fita impressa e papel'))
MEDICAMENTOS_MN = (('Adenosina', 'Sala de estresse', 5), ('Dipiridamol', 'Sala de estresse', 5), ('Dobutamina', 'Sala de estresse', 3), ('Regadenoson', 'Sala de estresse', 2),
                   ('Aminofilina', 'Carrinho de emergência', 3), ('Atropina', 'Carrinho de emergência', 5), ('Nitroglicerina', 'Carrinho de emergência', 3),
                   ('Glicose', 'Carrinho de emergência', 3), ('Soro fisiológico', 'Sala de estresse', 10), ('Adrenalina', 'Carrinho de emergência', 5))
LOCAIS_MED = ('Carrinho de emergência', 'Sala de estresse', 'Geladeira', 'Sala de dose', 'Almoxarifado')
TIPOS_RP = ('Extravasamento de radiofármaco', 'Reação adversa', 'Intercorrência clínica')
DIAS_VALIDADE_PACOTE = 30

ESQUEMA = """
CREATE TABLE IF NOT EXISTS enf_profissionais (
    usuario_id INTEGER PRIMARY KEY, cargo TEXT NOT NULL DEFAULT '', conselho TEXT NOT NULL DEFAULT '', numero TEXT NOT NULL DEFAULT '', uf TEXT NOT NULL DEFAULT '',
    assinatura_id INTEGER, assinatura_em TEXT, assinatura_por TEXT
);
CREATE TABLE IF NOT EXISTS enf_areas (chave TEXT PRIMARY KEY, titular_id INTEGER, substituto_id INTEGER);
CREATE TABLE IF NOT EXISTS enf_carrinhos (
    id INTEGER PRIMARY KEY, nome TEXT NOT NULL, tipo TEXT NOT NULL DEFAULT 'CARRINHO', local TEXT NOT NULL DEFAULT '', lacre_atual TEXT NOT NULL DEFAULT '',
    periodicidade TEXT NOT NULL DEFAULT 'SEMANAL', ativo INTEGER NOT NULL DEFAULT 1, criado_em TEXT
);
CREATE TABLE IF NOT EXISTS enf_carrinho_itens (
    id INTEGER PRIMARY KEY, carrinho_id INTEGER NOT NULL, nome TEXT NOT NULL, qtd INTEGER NOT NULL DEFAULT 0, qtd_min INTEGER NOT NULL DEFAULT 1,
    lote TEXT NOT NULL DEFAULT '', validade TEXT
);
CREATE INDEX IF NOT EXISTS ix_enf_citem ON enf_carrinho_itens(carrinho_id);
CREATE TABLE IF NOT EXISTS enf_conferencias (
    id INTEGER PRIMARY KEY, carrinho_id INTEGER NOT NULL, tipo TEXT NOT NULL, data_hora TEXT NOT NULL, profissional_id INTEGER NOT NULL,
    lacre_quebrado TEXT NOT NULL DEFAULT '', lacre_novo TEXT NOT NULL DEFAULT '', checklist TEXT NOT NULL DEFAULT '[]', itens TEXT NOT NULL DEFAULT '[]',
    problemas INTEGER NOT NULL DEFAULT 0, obs TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_enf_conf ON enf_conferencias(carrinho_id, data_hora);
CREATE TABLE IF NOT EXISTS enf_medicamentos (
    id INTEGER PRIMARY KEY, nome TEXT NOT NULL, lote TEXT NOT NULL DEFAULT '', validade TEXT, qtd INTEGER NOT NULL DEFAULT 0, qtd_min INTEGER NOT NULL DEFAULT 1,
    local TEXT NOT NULL DEFAULT '', ativo INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS enf_reposicao (
    id INTEGER PRIMARY KEY, medicamento_id INTEGER NOT NULL, qtd INTEGER NOT NULL, motivo TEXT NOT NULL DEFAULT '', criado_em TEXT, criado_por INTEGER,
    status TEXT NOT NULL DEFAULT 'PENDENTE', reposto_em TEXT
);
CREATE TABLE IF NOT EXISTS enf_temperaturas (
    id INTEGER PRIMARY KEY, data TEXT NOT NULL, hora TEXT NOT NULL, local TEXT NOT NULL, temperatura REAL NOT NULL, ok INTEGER NOT NULL DEFAULT 1, profissional_id INTEGER, obs TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_enf_temp ON enf_temperaturas(data);
CREATE TABLE IF NOT EXISTS enf_equipamentos (
    id INTEGER PRIMARY KEY, tipo TEXT NOT NULL, nome TEXT NOT NULL, patrimonio TEXT NOT NULL DEFAULT '', local TEXT NOT NULL DEFAULT '', teste_diario INTEGER NOT NULL DEFAULT 0,
    ultima_manutencao TEXT, proxima_manutencao TEXT, laudo_id INTEGER, laudo_nome TEXT, ativo INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS enf_testes (
    id INTEGER PRIMARY KEY, equipamento_id INTEGER NOT NULL, data_hora TEXT NOT NULL, profissional_id INTEGER NOT NULL, checklist TEXT NOT NULL DEFAULT '{}',
    ok INTEGER NOT NULL DEFAULT 1, obs TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_enf_teste ON enf_testes(equipamento_id, data_hora);
CREATE TABLE IF NOT EXISTS enf_pacotes (
    id INTEGER PRIMARY KEY, codigo TEXT NOT NULL UNIQUE, descricao TEXT NOT NULL, data_esteril TEXT NOT NULL, validade TEXT NOT NULL, autoclave TEXT NOT NULL DEFAULT '',
    ciclo TEXT NOT NULL DEFAULT '', quimico TEXT NOT NULL DEFAULT 'CONFORME', biologico TEXT NOT NULL DEFAULT 'AGUARDANDO', operador_id INTEGER, criado_em TEXT, usado_em TEXT
);
CREATE TABLE IF NOT EXISTS enf_rp_testes (
    id INTEGER PRIMARY KEY, data_hora TEXT NOT NULL, profissional_id INTEGER NOT NULL, equipamento TEXT NOT NULL DEFAULT 'Monitor de contaminação', fundo TEXT NOT NULL DEFAULT '',
    fonte TEXT NOT NULL DEFAULT '', ok INTEGER NOT NULL DEFAULT 1, obs TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS enf_ocorrencias (
    id INTEGER PRIMARY KEY, tipo TEXT NOT NULL, data_hora TEXT NOT NULL, referencia TEXT NOT NULL DEFAULT '', radiofarmaco TEXT NOT NULL DEFAULT '', local TEXT NOT NULL DEFAULT '',
    gravidade TEXT NOT NULL DEFAULT 'Leve', conduta TEXT NOT NULL DEFAULT '', profissional_id INTEGER, qualidade_id INTEGER
);
CREATE TABLE IF NOT EXISTS enf_avisos (
    chave TEXT NOT NULL, referencia TEXT NOT NULL, fase TEXT NOT NULL, enviado_em TEXT, PRIMARY KEY (chave, referencia, fase)
);
"""
_GARANTIDOS = set()


class ErroEnfermagem(ValueError):
    """Erro de validação mostrado ao usuário."""


def garantir(db):
    from .anexos import caminho_do_banco
    chave = caminho_do_banco(db) or id(db)
    if chave in _GARANTIDOS:
        return
    db.executescript(ESQUEMA)
    db.commit()
    _GARANTIDOS.add(chave)


# ------------------------------------------------------------------ utilidades
def _txt(valor, limite=300, obrigatorio=False, rotulo=''):
    t = str(valor or '').strip()[:limite]
    if obrigatorio and not t:
        raise ErroEnfermagem('Preencha %s.' % (rotulo or 'o campo'))
    return t


def _data(valor, obrigatorio=False, rotulo='a data'):
    v = str(valor or '').strip()
    if not v:
        if obrigatorio:
            raise ErroEnfermagem('Informe %s.' % rotulo)
        return None
    try:
        return date.fromisoformat(v).isoformat()
    except ValueError:
        raise ErroEnfermagem('Data inválida.')


def _int(valor, minimo=0, rotulo='a quantidade', padrao=None):
    v = str(valor if valor is not None else '').strip()
    if v == '' and padrao is not None:
        return padrao
    try:
        n = int(v)
    except ValueError:
        raise ErroEnfermagem('Informe %s com um número inteiro.' % rotulo)
    if n < minimo:
        raise ErroEnfermagem('Informe %s (mínimo %d).' % (rotulo, minimo))
    return n


def situacao_validade(validade, hoje=None):
    """('vencido'|'vence'|'ok'|'sem', dias) para uma validade ISO. 'vence' = dentro dos 60 dias dos avisos."""
    if not validade:
        return 'sem', None
    dias = (date.fromisoformat(validade) - (hoje or date.today())).days
    if dias < 0:
        return 'vencido', dias
    return ('vence' if dias <= FASES[-1] else 'ok'), dias


def nome_profissional(db, uid):
    r = db.execute('SELECT COALESCE(e.name, u.usuario) AS nome FROM usuarios u LEFT JOIN bh_employees e ON e.id=u.bh_funcionario_id WHERE u.id=?', (uid,)).fetchone()
    return r['nome'] if r else ''


# ------------------------------------------------------------------ profissional e assinatura
def profissional(db, uid):
    r = db.execute('SELECT * FROM enf_profissionais WHERE usuario_id=?', (uid,)).fetchone()
    return dict(r) if r else None


def assinatura_valida(db, uid):
    p = profissional(db, uid)
    return bool(p and p['assinatura_id'])


def processar_assinatura(conteudo):
    """Recebe PNG ou JPG, remove o fundo branco (fica transparente), recorta e limita o tamanho. Devolve bytes PNG."""
    if not conteudo or len(conteudo) > ASSINATURA_MAX:
        raise ErroEnfermagem('A imagem da assinatura pode ter no máximo 2 MB.')
    if not (conteudo[:8] == b'\x89PNG\r\n\x1a\n' or conteudo[:3] == b'\xff\xd8\xff'):
        raise ErroEnfermagem('Envie a assinatura em PNG ou JPG.')
    from PIL import Image
    try:
        img = Image.open(io.BytesIO(conteudo))
        img.load()
    except Exception:
        raise ErroEnfermagem('Não foi possível ler a imagem da assinatura.')
    img = img.convert('RGBA')
    img.thumbnail((600, 600))
    pixels = img.load()
    for y in range(img.height):
        for x in range(img.width):
            r, g, b, a = pixels[x, y]
            claro = min(r, g, b)
            if claro >= 235:
                pixels[x, y] = (255, 255, 255, 0)           # fundo branco some
            elif claro >= 185:
                pixels[x, y] = (r, g, b, int(a * (235 - claro) / 50.0))   # bordas suaves
    caixa = img.getbbox()
    if caixa is None or not img.getchannel('A').getbbox():
        raise ErroEnfermagem('A imagem parece estar em branco. Envie uma foto ou digitalização da assinatura.')
    img = img.crop(caixa)
    img.thumbnail((420, 160))
    saida = io.BytesIO()
    img.save(saida, 'PNG', optimize=True)
    return saida.getvalue()


def salvar_profissional(db, uid, cargo, conselho, numero, uf, conteudo, por, manter_atual=False):
    """Grava cargo, conselho e (se enviada) a assinatura. Devolve 'nova', 'trocada' ou 'mantida'."""
    cargo = _txt(cargo, 80, True, 'o cargo')
    conselho = _txt(conselho, 20, True, 'o conselho profissional')
    numero = _txt(numero, 20, True, 'o número do conselho')
    uf = _txt(uf, 2, True, 'a UF').upper()
    if uf not in UFS:
        raise ErroEnfermagem('UF inválida.')
    atual = profissional(db, uid)
    if conteudo:
        png = processar_assinatura(conteudo)
        caminho = anexos.caminho_de(db)
        if not caminho:
            raise ErroEnfermagem('Anexos indisponíveis neste banco.')
        novo = anexos.gravar(caminho, 'enf_assinatura', png)
        anexos.vincular(caminho, novo, uid)
        antigo = atual['assinatura_id'] if atual else None
        resultado = 'trocada' if antigo else 'nova'
    elif atual and atual['assinatura_id'] and manter_atual:
        novo, antigo, resultado = atual['assinatura_id'], None, 'mantida'
    else:
        raise ErroEnfermagem('Importe a imagem da assinatura (PNG ou JPG).')
    db.execute('INSERT INTO enf_profissionais (usuario_id, cargo, conselho, numero, uf, assinatura_id, assinatura_em, assinatura_por) VALUES (?,?,?,?,?,?,?,?) '
               'ON CONFLICT(usuario_id) DO UPDATE SET cargo=excluded.cargo, conselho=excluded.conselho, numero=excluded.numero, uf=excluded.uf, '
               'assinatura_id=excluded.assinatura_id, assinatura_em=CASE WHEN ?=\'mantida\' THEN assinatura_em ELSE excluded.assinatura_em END, '
               'assinatura_por=CASE WHEN ?=\'mantida\' THEN assinatura_por ELSE excluded.assinatura_por END',
               (uid, cargo, conselho, numero, uf, novo, agora(), por, resultado, resultado))
    db.commit()
    if antigo:
        anexos.apagar(anexos.caminho_de(db), antigo)
    return resultado


def assinatura_png(db, uid):
    p = profissional(db, uid)
    if not p or not p['assinatura_id']:
        return None
    return anexos.ler(anexos.caminho_de(db), p['assinatura_id'])


def bloco_assinatura(db, uid):
    """Dados para imprimir a assinatura sobre a linha, com nome, cargo e conselho. Só tem `assinatura` se o profissional tem a imagem cadastrada."""
    p = profissional(db, uid)
    nome = nome_profissional(db, uid)
    if not p:
        return {'nome': nome, 'cargo': '', 'conselho': '', 'assinatura': False, 'uid': uid}
    return {'nome': nome, 'cargo': p['cargo'], 'conselho': '%s-%s %s' % (p['conselho'], p['uf'], p['numero']), 'assinatura': bool(p['assinatura_id']), 'uid': uid}


def profissionais(db):
    return [dict(r) for r in db.execute('SELECT p.*, COALESCE(e.name, u.usuario) AS nome, u.usuario FROM enf_profissionais p JOIN usuarios u ON u.id=p.usuario_id '
                                        'LEFT JOIN bh_employees e ON e.id=u.bh_funcionario_id ORDER BY nome')]


# ------------------------------------------------------------------ responsáveis por área
def responsaveis(db):
    r = {a: {'titular_id': None, 'substituto_id': None} for a, _ in AREAS}
    for x in db.execute('SELECT * FROM enf_areas'):
        if x['chave'] in r:
            r[x['chave']] = {'titular_id': x['titular_id'], 'substituto_id': x['substituto_id']}
    return r


def salvar_responsaveis(db, form):
    for chave, _n in AREAS:
        def _uid(campo):
            v = str(form.get('%s_%s' % (campo, chave)) or '').strip()
            return int(v) if v.isdigit() else None
        db.execute('INSERT INTO enf_areas (chave, titular_id, substituto_id) VALUES (?,?,?) ON CONFLICT(chave) DO UPDATE SET titular_id=excluded.titular_id, '
                   'substituto_id=excluded.substituto_id', (chave, _uid('titular'), _uid('substituto')))
    db.commit()


# ------------------------------------------------------------------ carrinhos e kits
def carrinhos(db, tipo='CARRINHO'):
    saida = []
    for c in db.execute('SELECT * FROM enf_carrinhos WHERE tipo=? AND ativo=1 ORDER BY nome', (tipo,)):
        saida.append(estado_carrinho(db, dict(c)))
    return saida


def estado_carrinho(db, c, hoje=None):
    hoje = hoje or date.today()
    itens = [dict(i) for i in db.execute('SELECT * FROM enf_carrinho_itens WHERE carrinho_id=? ORDER BY nome', (c['id'],))]
    problemas = []
    for i in itens:
        i['situacao'], i['dias'] = situacao_validade(i['validade'], hoje)
        i['vermelho'] = i['situacao'] == 'vencido' or i['qtd'] < i['qtd_min']
        if i['situacao'] == 'vencido':
            problemas.append('%s vencido' % i['nome'])
        if i['qtd'] < i['qtd_min']:
            problemas.append('%s: %d (mínimo %d)' % (i['nome'], i['qtd'], i['qtd_min']))
    ultima = db.execute('SELECT * FROM enf_conferencias WHERE carrinho_id=? ORDER BY data_hora DESC, id DESC LIMIT 1', (c['id'],)).fetchone()
    c['itens'], c['problemas'], c['vermelho'] = itens, problemas, bool(problemas)
    c['ultima'] = dict(ultima) if ultima else None
    limite = 1 if c['periodicidade'] == 'DIARIA' else 7
    c['atrasada'] = (not ultima) or (hoje - date.fromisoformat(ultima['data_hora'][:10])).days > limite
    return c


def salvar_carrinho(db, form, tipo='CARRINHO'):
    nome = _txt(form.get('nome'), 80, True, 'o nome')
    per = form.get('periodicidade') if form.get('periodicidade') in ('DIARIA', 'SEMANAL') else 'SEMANAL'
    cur = db.execute('INSERT INTO enf_carrinhos (nome, tipo, local, lacre_atual, periodicidade, criado_em) VALUES (?,?,?,?,?,?)',
                     (nome, tipo, _txt(form.get('local'), 80), _txt(form.get('lacre'), 40), per, agora()))
    db.commit()
    return cur.lastrowid


def carrinho(db, cid):
    r = db.execute('SELECT * FROM enf_carrinhos WHERE id=? AND ativo=1', (cid,)).fetchone()
    if r is None:
        raise ErroEnfermagem('Carrinho não encontrado.')
    return estado_carrinho(db, dict(r))


def salvar_item(db, cid, form, iid=None):
    carrinho(db, cid)
    dados = (_txt(form.get('nome'), 100, True, 'o nome do item'), _int(form.get('qtd'), 0, 'a quantidade', 0), _int(form.get('qtd_min'), 0, 'a quantidade mínima', 1),
             _txt(form.get('lote'), 40), _data(form.get('validade')))
    if iid:
        db.execute('UPDATE enf_carrinho_itens SET nome=?, qtd=?, qtd_min=?, lote=?, validade=? WHERE id=? AND carrinho_id=?', dados + (iid, cid))
    else:
        db.execute('INSERT INTO enf_carrinho_itens (carrinho_id, nome, qtd, qtd_min, lote, validade) VALUES (?,?,?,?,?,?)', (cid,) + dados)
    db.commit()


def excluir_item(db, cid, iid):
    db.execute('DELETE FROM enf_carrinho_itens WHERE id=? AND carrinho_id=?', (iid, cid))
    db.commit()


def conferir(db, cid, form, uid):
    """Registra a conferência (checklist, itens e lacre). O profissional é quem está logado. Atualiza as quantidades e o lacre do carrinho."""
    c = carrinho(db, cid)
    tipo = form.get('tipo') if form.get('tipo') in ('DIARIA', 'SEMANAL', 'APOS_USO') else 'SEMANAL'
    lista = CHECKLIST_KIT if c['tipo'] == 'KIT' else CHECKLIST_CARRINHO
    checklist = [{'item': t, 'ok': form.get('chk_%d' % n) == '1'} for n, t in enumerate(lista)]
    lacre_novo, quebrado = _txt(form.get('lacre_novo'), 40), _txt(form.get('lacre_quebrado'), 40)
    if c['tipo'] == 'CARRINHO' and tipo == 'APOS_USO' and not (quebrado and lacre_novo):
        raise ErroEnfermagem('Após o uso, informe o número do lacre que foi quebrado e o do novo lacre.')
    if lacre_novo and lacre_novo == c['lacre_atual'] and not quebrado:
        quebrado = c['lacre_atual']
    itens, problemas = [], 0
    for i in c['itens']:
        qtd = _int(form.get('qtd_%d' % i['id']), 0, 'a quantidade de "%s"' % i['nome'], i['qtd'])
        lote = _txt(form.get('lote_%d' % i['id']), 40) or i['lote']
        validade = _data(form.get('validade_%d' % i['id'])) or i['validade']
        sit, _d = situacao_validade(validade)
        ok = qtd >= i['qtd_min'] and sit != 'vencido'
        problemas += 0 if ok else 1
        itens.append({'id': i['id'], 'nome': i['nome'], 'qtd': qtd, 'qtd_min': i['qtd_min'], 'lote': lote, 'validade': validade, 'ok': ok})
        db.execute('UPDATE enf_carrinho_itens SET qtd=?, lote=?, validade=? WHERE id=?', (qtd, lote, validade, i['id']))
    problemas += sum(1 for k in checklist if not k['ok'])
    cur = db.execute('INSERT INTO enf_conferencias (carrinho_id, tipo, data_hora, profissional_id, lacre_quebrado, lacre_novo, checklist, itens, problemas, obs) VALUES (?,?,?,?,?,?,?,?,?,?)',
                     (cid, tipo, agora(), uid, quebrado, lacre_novo, json.dumps(checklist, ensure_ascii=False), json.dumps(itens, ensure_ascii=False), problemas, _txt(form.get('obs'), 500)))
    if lacre_novo:
        db.execute('UPDATE enf_carrinhos SET lacre_atual=? WHERE id=?', (lacre_novo, cid))
    db.commit()
    return cur.lastrowid


def conferencia(db, conf_id):
    r = db.execute('SELECT * FROM enf_conferencias WHERE id=?', (conf_id,)).fetchone()
    if r is None:
        raise ErroEnfermagem('Conferência não encontrada.')
    x = dict(r)
    x['checklist'], x['itens'] = json.loads(x['checklist']), json.loads(x['itens'])
    return x


def historico_conferencias(db, cid, limite=10):
    return [dict(r, profissional=nome_profissional(db, r['profissional_id'])) for r in
            db.execute('SELECT * FROM enf_conferencias WHERE carrinho_id=? ORDER BY data_hora DESC, id DESC LIMIT ?', (cid, limite))]


# ------------------------------------------------------------------ medicamentos e insumos
def medicamentos(db):
    saida = []
    for m in db.execute('SELECT * FROM enf_medicamentos WHERE ativo=1 ORDER BY nome'):
        x = dict(m)
        x['situacao'], x['dias'] = situacao_validade(x['validade'])
        x['abaixo'] = x['qtd'] < x['qtd_min']
        x['vermelho'] = x['situacao'] == 'vencido' or x['abaixo']
        x['pendente'] = db.execute("SELECT COALESCE(SUM(qtd),0) FROM enf_reposicao WHERE medicamento_id=? AND status='PENDENTE'", (x['id'],)).fetchone()[0]
        saida.append(x)
    return saida


def salvar_medicamento(db, form, mid=None):
    dados = (_txt(form.get('nome'), 100, True, 'o nome'), _txt(form.get('lote'), 40), _data(form.get('validade')), _int(form.get('qtd'), 0, 'a quantidade', 0),
             _int(form.get('qtd_min'), 0, 'o estoque mínimo', 1), _txt(form.get('local'), 60))
    if mid:
        db.execute('UPDATE enf_medicamentos SET nome=?, lote=?, validade=?, qtd=?, qtd_min=?, local=? WHERE id=?', dados + (mid,))
    else:
        db.execute('INSERT INTO enf_medicamentos (nome, lote, validade, qtd, qtd_min, local) VALUES (?,?,?,?,?,?)', dados)
    db.commit()


def carregar_medicamentos_mn(db):
    n = 0
    for nome, local, minimo in MEDICAMENTOS_MN:
        if not db.execute('SELECT 1 FROM enf_medicamentos WHERE nome=? AND ativo=1', (nome,)).fetchone():
            db.execute('INSERT INTO enf_medicamentos (nome, local, qtd_min, qtd) VALUES (?,?,?,0)', (nome, local, minimo))
            n += 1
    db.commit()
    return n


def usar_medicamento(db, mid, qtd, motivo, uid):
    """Dá baixa no estoque e coloca o item na lista de reposição (somando se já houver pedido pendente)."""
    m = db.execute('SELECT * FROM enf_medicamentos WHERE id=? AND ativo=1', (mid,)).fetchone()
    if m is None:
        raise ErroEnfermagem('Item não encontrado.')
    qtd = _int(qtd, 1, 'a quantidade usada')
    if qtd > m['qtd']:
        raise ErroEnfermagem('O estoque de %s tem só %d.' % (m['nome'], m['qtd']))
    db.execute('UPDATE enf_medicamentos SET qtd=qtd-? WHERE id=?', (qtd, mid))
    pend = db.execute("SELECT id FROM enf_reposicao WHERE medicamento_id=? AND status='PENDENTE'", (mid,)).fetchone()
    if pend:
        db.execute('UPDATE enf_reposicao SET qtd=qtd+?, motivo=? WHERE id=?', (qtd, _txt(motivo, 200) or 'Uso', pend['id']))
    else:
        db.execute('INSERT INTO enf_reposicao (medicamento_id, qtd, motivo, criado_em, criado_por) VALUES (?,?,?,?,?)', (mid, qtd, _txt(motivo, 200) or 'Uso', agora(), uid))
    db.commit()


def reposicao(db):
    return [dict(r) for r in db.execute("SELECT r.*, m.nome, m.local FROM enf_reposicao r JOIN enf_medicamentos m ON m.id=r.medicamento_id WHERE r.status='PENDENTE' ORDER BY m.local, m.nome")]


def repor(db, rid, form):
    r = db.execute("SELECT * FROM enf_reposicao WHERE id=? AND status='PENDENTE'", (rid,)).fetchone()
    if r is None:
        raise ErroEnfermagem('Pedido de reposição não encontrado.')
    qtd = _int(form.get('qtd'), 1, 'a quantidade reposta', r['qtd'])
    db.execute('UPDATE enf_medicamentos SET qtd=qtd+?, lote=COALESCE(NULLIF(?,\'\'), lote), validade=COALESCE(?, validade) WHERE id=?',
               (qtd, _txt(form.get('lote'), 40), _data(form.get('validade')), r['medicamento_id']))
    db.execute("UPDATE enf_reposicao SET status='REPOSTO', reposto_em=? WHERE id=?", (agora(), rid))
    db.commit()


def limites_temperatura(db):
    def cfg(chave, padrao):
        r = db.execute('SELECT valor FROM config WHERE chave=?', (chave,)).fetchone()
        try:
            return float(str(r['valor']).replace(',', '.')) if r else padrao
        except ValueError:
            return padrao
    return cfg('enf_temp_min', 2.0), cfg('enf_temp_max', 8.0)


def salvar_limites(db, form):
    for chave in ('enf_temp_min', 'enf_temp_max'):
        bruto = str(form.get(chave) or '').strip().replace(',', '.')
        try:
            float(bruto)
        except ValueError:
            raise ErroEnfermagem('Informe os limites de temperatura com números.')
        db.execute('INSERT INTO config (chave, valor) VALUES (?,?) ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor', (chave, bruto))
    if float(str(form.get('enf_temp_min')).replace(',', '.')) >= float(str(form.get('enf_temp_max')).replace(',', '.')):
        raise ErroEnfermagem('O limite mínimo precisa ser menor que o máximo.')
    db.commit()


def registrar_temperatura(db, form, uid):
    local = _txt(form.get('local'), 60, True, 'o local')
    try:
        t = float(str(form.get('temperatura') or '').replace(',', '.'))
    except ValueError:
        raise ErroEnfermagem('Informe a temperatura (ex.: 4,5).')
    mn, mx = limites_temperatura(db)
    ok = 1 if mn <= t <= mx else 0
    agora_dt = datetime.now()
    db.execute('INSERT INTO enf_temperaturas (data, hora, local, temperatura, ok, profissional_id, obs) VALUES (?,?,?,?,?,?,?)',
               (agora_dt.date().isoformat(), agora_dt.strftime('%H:%M'), local, t, ok, uid, _txt(form.get('obs'), 200)))
    db.commit()
    return bool(ok)


def temperaturas(db, dias=14):
    desde = (date.today() - timedelta(days=dias)).isoformat()
    return [dict(r, profissional=nome_profissional(db, r['profissional_id'])) for r in
            db.execute('SELECT * FROM enf_temperaturas WHERE data>=? ORDER BY data DESC, hora DESC', (desde,))]


def temperatura_pendente_hoje(db):
    """Locais de geladeira cadastrados em medicamentos que ainda não tiveram a temperatura registrada hoje."""
    hoje = date.today().isoformat()
    locais = {m['local'] for m in db.execute("SELECT DISTINCT local FROM enf_medicamentos WHERE ativo=1 AND local LIKE '%elad%'")} or {'Geladeira'}
    feitos = {r['local'] for r in db.execute('SELECT DISTINCT local FROM enf_temperaturas WHERE data=?', (hoje,))}
    return sorted(locais - feitos)


# ------------------------------------------------------------------ equipamentos
def hora_teste(db):
    r = db.execute("SELECT valor FROM config WHERE chave='enf_hora_teste'").fetchone()
    return (r['valor'] if r and r['valor'] else '09:00')


def salvar_hora_teste(db, valor):
    v = str(valor or '').strip()
    try:
        datetime.strptime(v, '%H:%M')
    except ValueError:
        raise ErroEnfermagem('Informe o horário no formato HH:MM.')
    db.execute("INSERT INTO config (chave, valor) VALUES ('enf_hora_teste', ?) ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor", (v,))
    db.commit()


def equipamentos(db, agora_dt=None):
    agora_dt = agora_dt or datetime.now()
    hoje = agora_dt.date()
    limite_hora = hora_teste(db)
    saida = []
    for e in db.execute('SELECT * FROM enf_equipamentos WHERE ativo=1 ORDER BY tipo, nome'):
        x = dict(e)
        x['manutencao'], x['dias_manut'] = situacao_validade(x['proxima_manutencao'], hoje)
        x['teste_hoje'] = db.execute('SELECT * FROM enf_testes WHERE equipamento_id=? AND substr(data_hora,1,10)=? ORDER BY id DESC LIMIT 1', (x['id'], hoje.isoformat())).fetchone()
        x['teste_atrasado'] = bool(x['teste_diario'] and not x['teste_hoje'] and agora_dt.strftime('%H:%M') >= limite_hora)
        x['vermelho'] = x['manutencao'] == 'vencido' or x['teste_atrasado'] or bool(x['teste_hoje'] and not x['teste_hoje']['ok'])
        saida.append(x)
    return saida


def salvar_equipamento(db, form, arquivo=None, nome_arquivo='', eid=None):
    tipo = form.get('tipo') if form.get('tipo') in TIPOS_EQUIP else 'Outro'
    dados = [tipo, _txt(form.get('nome'), 100, True, 'o nome'), _txt(form.get('patrimonio'), 40), _txt(form.get('local'), 80),
             1 if (form.get('teste_diario') or tipo == 'Cardioversor/desfibrilador') else 0, _data(form.get('ultima_manutencao')), _data(form.get('proxima_manutencao'))]
    laudo_id = laudo_nome = None
    if arquivo:
        if arquivo[:5] != b'%PDF-':
            raise ErroEnfermagem('O laudo precisa ser um arquivo PDF.')
        if len(arquivo) > 10 * 1024 * 1024:
            raise ErroEnfermagem('O laudo pode ter no máximo 10 MB.')
        caminho = anexos.caminho_de(db)
        if not caminho:
            raise ErroEnfermagem('Anexos indisponíveis neste banco.')
        laudo_id = anexos.gravar(caminho, 'enf_laudo', arquivo)
        laudo_nome = (nome_arquivo or 'laudo.pdf')[:120]
    if eid:
        db.execute('UPDATE enf_equipamentos SET tipo=?, nome=?, patrimonio=?, local=?, teste_diario=?, ultima_manutencao=?, proxima_manutencao=? WHERE id=?', tuple(dados) + (eid,))
        if laudo_id:
            db.execute('UPDATE enf_equipamentos SET laudo_id=?, laudo_nome=? WHERE id=?', (laudo_id, laudo_nome, eid))
    else:
        db.execute('INSERT INTO enf_equipamentos (tipo, nome, patrimonio, local, teste_diario, ultima_manutencao, proxima_manutencao, laudo_id, laudo_nome) VALUES (?,?,?,?,?,?,?,?,?)',
                   tuple(dados) + (laudo_id, laudo_nome))
    db.commit()


def laudo_pdf(db, eid):
    r = db.execute('SELECT laudo_id, laudo_nome FROM enf_equipamentos WHERE id=?', (eid,)).fetchone()
    if not r or not r['laudo_id']:
        return None, None
    return anexos.ler(anexos.caminho_de(db), r['laudo_id']), r['laudo_nome']


def registrar_teste(db, eid, form, uid):
    e = db.execute('SELECT * FROM enf_equipamentos WHERE id=? AND ativo=1', (eid,)).fetchone()
    if e is None:
        raise ErroEnfermagem('Equipamento não encontrado.')
    cheques = {k: form.get('t_' + k) == '1' for k, _r in CHECKLIST_CARDIOVERSOR}
    if e['tipo'] != 'Cardioversor/desfibrilador':
        cheques = {'funcionando': form.get('t_funcionando') == '1'}
    ok = all(cheques.values())
    cur = db.execute('INSERT INTO enf_testes (equipamento_id, data_hora, profissional_id, checklist, ok, obs) VALUES (?,?,?,?,?,?)',
                     (eid, agora(), uid, json.dumps(cheques), 1 if ok else 0, _txt(form.get('obs'), 300)))
    db.commit()
    return cur.lastrowid


def teste(db, tid):
    r = db.execute('SELECT t.*, e.nome AS equipamento, e.tipo, e.patrimonio, e.local FROM enf_testes t JOIN enf_equipamentos e ON e.id=t.equipamento_id WHERE t.id=?', (tid,)).fetchone()
    if r is None:
        raise ErroEnfermagem('Teste não encontrado.')
    x = dict(r)
    x['checklist'] = json.loads(x['checklist'])
    return x


def testes_recentes(db, eid, limite=8):
    return [dict(r, profissional=nome_profissional(db, r['profissional_id'])) for r in
            db.execute('SELECT * FROM enf_testes WHERE equipamento_id=? ORDER BY data_hora DESC, id DESC LIMIT ?', (eid, limite))]


# ------------------------------------------------------------------ esterilização
def _codigo_pacote(db):
    n = (db.execute('SELECT COALESCE(MAX(id),0)+1 FROM enf_pacotes').fetchone()[0])
    return 'EST-%s-%04d' % (date.today().strftime('%y%m%d'), n)


def pacotes(db, hoje=None):
    saida = []
    for p in db.execute('SELECT * FROM enf_pacotes WHERE usado_em IS NULL ORDER BY validade, id'):
        x = dict(p)
        x['situacao'], x['dias'] = situacao_validade(x['validade'], hoje)
        x['reprovado'] = x['quimico'] != 'CONFORME' or x['biologico'] == 'NÃO CONFORME'
        x['vermelho'] = x['situacao'] == 'vencido' or x['reprovado']
        x['operador'] = nome_profissional(db, x['operador_id']) if x['operador_id'] else ''
        saida.append(x)
    return saida


def salvar_pacote(db, form, uid):
    desc = _txt(form.get('descricao'), 120, True, 'a descrição do pacote')
    data_e = _data(form.get('data_esteril'), True, 'a data da esterilização') if form.get('data_esteril') else date.today().isoformat()
    validade = _data(form.get('validade')) or (date.fromisoformat(data_e) + timedelta(days=DIAS_VALIDADE_PACOTE)).isoformat()
    quimico = form.get('quimico') if form.get('quimico') in ('CONFORME', 'NÃO CONFORME') else 'CONFORME'
    bio = form.get('biologico') if form.get('biologico') in ('CONFORME', 'NÃO CONFORME', 'AGUARDANDO') else 'AGUARDANDO'
    cur = db.execute('INSERT INTO enf_pacotes (codigo, descricao, data_esteril, validade, autoclave, ciclo, quimico, biologico, operador_id, criado_em) VALUES (?,?,?,?,?,?,?,?,?,?)',
                     (_codigo_pacote(db), desc, data_e, validade, _txt(form.get('autoclave'), 60), _txt(form.get('ciclo'), 40), quimico, bio, uid, agora()))
    db.commit()
    return cur.lastrowid


def pacote(db, pid):
    r = db.execute('SELECT * FROM enf_pacotes WHERE id=?', (pid,)).fetchone()
    if r is None:
        raise ErroEnfermagem('Pacote não encontrado.')
    return dict(r)


def atualizar_biologico(db, pid, resultado):
    if resultado not in ('CONFORME', 'NÃO CONFORME'):
        raise ErroEnfermagem('Resultado inválido.')
    pacote(db, pid)
    db.execute('UPDATE enf_pacotes SET biologico=? WHERE id=?', (resultado, pid))
    db.commit()


def marcar_usado(db, pid):
    pacote(db, pid)
    db.execute('UPDATE enf_pacotes SET usado_em=? WHERE id=?', (agora(), pid))
    db.commit()


# ------------------------------------------------------------------ radioproteção
def registrar_rp_teste(db, form, uid):
    ok = form.get('ok') == '1'
    db.execute('INSERT INTO enf_rp_testes (data_hora, profissional_id, equipamento, fundo, fonte, ok, obs) VALUES (?,?,?,?,?,?,?)',
               (agora(), uid, _txt(form.get('equipamento'), 80) or 'Monitor de contaminação', _txt(form.get('fundo'), 30), _txt(form.get('fonte'), 30), 1 if ok else 0, _txt(form.get('obs'), 300)))
    db.commit()
    return ok


def rp_testes(db, limite=10):
    return [dict(r, profissional=nome_profissional(db, r['profissional_id'])) for r in db.execute('SELECT * FROM enf_rp_testes ORDER BY data_hora DESC, id DESC LIMIT ?', (limite,))]


def rp_teste_hoje(db):
    return db.execute('SELECT * FROM enf_rp_testes WHERE substr(data_hora,1,10)=? ORDER BY id DESC LIMIT 1', (date.today().isoformat(),)).fetchone()


def registrar_ocorrencia_rp(db, form, uid):
    tipo = form.get('tipo') if form.get('tipo') in TIPOS_RP else None
    if not tipo:
        raise ErroEnfermagem('Escolha o tipo da ocorrência.')
    grav = form.get('gravidade') if form.get('gravidade') in ('Leve', 'Moderada', 'Grave') else 'Leve'
    cur = db.execute('INSERT INTO enf_ocorrencias (tipo, data_hora, referencia, radiofarmaco, local, gravidade, conduta, profissional_id) VALUES (?,?,?,?,?,?,?,?)',
                     (tipo, agora(), _txt(form.get('referencia'), 80), _txt(form.get('radiofarmaco'), 80), _txt(form.get('local'), 80), grav, _txt(form.get('conduta'), 800, True, 'a conduta'), uid))
    oid = cur.lastrowid
    if form.get('qualidade'):      # também entra nas ocorrências da Qualidade (sem nome de paciente)
        from . import qualidade as q
        q.garantir(db)
        tipo_q = 'Evento adverso'
        qid = q.salvar_ocorrencia(db, {'tipo': tipo_q, 'gravidade': grav, 'setor': 'Enfermagem', 'descricao': '%s. Radiofármaco: %s. Local: %s.' % (tipo, _txt(form.get('radiofarmaco'), 80) or '—', _txt(form.get('local'), 80) or '—'),
                                       'acao_imediata': _txt(form.get('conduta'), 800)}, nome_profissional(db, uid))
        db.execute('UPDATE enf_ocorrencias SET qualidade_id=? WHERE id=?', (qid, oid))
    db.commit()
    return oid


def ocorrencias_rp(db, limite=15):
    return [dict(r, profissional=nome_profissional(db, r['profissional_id']) if r['profissional_id'] else '') for r in
            db.execute('SELECT * FROM enf_ocorrencias ORDER BY data_hora DESC, id DESC LIMIT ?', (limite,))]


# ------------------------------------------------------------------ painel
def resumo(db, agora_dt=None):
    """Situação de cada área para o painel: {chave: {'vermelho': n, 'texto': ...}}."""
    agora_dt = agora_dt or datetime.now()
    carr = carrinhos(db)
    kits = carrinhos(db, 'KIT')
    meds = medicamentos(db)
    eqs = equipamentos(db, agora_dt)
    pacs = pacotes(db)
    teste_rp = rp_teste_hoje(db)
    return {
        'carrinho': {'vermelho': sum(1 for c in carr if c['vermelho']), 'atrasadas': sum(1 for c in carr if c['atrasada']), 'total': len(carr)},
        'medicamentos': {'vermelho': sum(1 for m in meds if m['vermelho']), 'reposicao': len(reposicao(db)), 'total': len(meds), 'temperatura': len(temperatura_pendente_hoje(db)) if meds else 0},
        'equipamentos': {'vermelho': sum(1 for e in eqs if e['vermelho']), 'total': len(eqs)},
        'esterilizacao': {'vermelho': sum(1 for p in pacs if p['vermelho']), 'total': len(pacs)},
        'radioprotecao': {'vermelho': sum(1 for k in kits if k['vermelho']) + (0 if teste_rp or agora_dt.strftime('%H:%M') < hora_teste(db) else 1), 'total': len(kits)},
    }


# ------------------------------------------------------------------ avisos para o responsável de cada área
def _destinos(db, area):
    r = responsaveis(db)[area]
    ids = [u for u in (r['titular_id'], r['substituto_id']) if u]
    ativos = [x['id'] for x in db.execute('SELECT id FROM usuarios WHERE ativo=1 AND COALESCE(sistema,0)=0 AND id IN (%s)' % ','.join('?' * len(ids)), ids)] if ids else []
    if not ativos:
        from . import avisos
        return avisos.gerentes(db), False
    return ativos, True


def _enviar_aviso(db, destinos, corpo):
    from . import avisos
    de = avisos.sistema_id(db)
    if de is None:
        return 0
    n = 0
    for para in set(destinos):
        db.execute("INSERT INTO chat_mensagens (de_id, para_id, corpo, criado_em, tipo) VALUES (?,?,?,?,'ENFERMAGEM')", (de, para, corpo, agora()))
        n += 1
    return n


def _fase_validade(dias):
    if dias < 0:
        return 'VENCIDO'
    for limite in FASES:
        if dias <= limite:
            return str(limite)
    return None


def _texto_validade(nome, onde, validade, dias, fase):
    data = '%s/%s/%s' % (validade[8:10], validade[5:7], validade[:4])
    if fase == 'VENCIDO':
        return 'Enfermagem: %s (%s) VENCEU em %s. Providencie a troca.' % (nome, onde, data)
    if dias == 0:
        return 'Enfermagem: %s (%s) vence HOJE (%s).' % (nome, onde, data)
    if dias == 1:
        return 'Enfermagem: %s (%s) vence AMANHÃ (%s).' % (nome, onde, data)
    return 'Enfermagem: %s (%s) vence em %d dias (%s).' % (nome, onde, dias, data)


def verificar_avisos(db, hoje=None, agora_dt=None):
    """Envia os avisos de validade, de manutenção e de teste diário não feito ao responsável da área; vencido há mais de ESCALA_DIAS dias sobe para a gerência.
    Cada fase é enviada uma única vez por item e validade. Devolve quantas mensagens foram gravadas."""
    garantir(db)
    agora_dt = agora_dt or datetime.now()
    hoje = hoje or agora_dt.date()
    enviadas = 0

    def tentar(area, chave, ref, fase, corpo, dias_vencido=0):
        nonlocal enviadas
        if not db.execute('SELECT 1 FROM enf_avisos WHERE chave=? AND referencia=? AND fase=?', (chave, ref, fase)).fetchone():
            destinos, _tem = _destinos(db, area)
            enviadas += _enviar_aviso(db, destinos, corpo)
            db.execute('INSERT INTO enf_avisos (chave, referencia, fase, enviado_em) VALUES (?,?,?,?)', (chave, ref, fase, agora()))
        escalar(area, chave, ref, corpo, dias_vencido)

    def escalar(area, chave, ref, corpo, dias_vencido):
        """Vencido há ESCALA_DIAS dias ou mais sem providência: o aviso sobe para a gerência (uma vez), se a área tem responsável."""
        nonlocal enviadas
        if dias_vencido < ESCALA_DIAS or db.execute('SELECT 1 FROM enf_avisos WHERE chave=? AND referencia=? AND fase=?', (chave, ref, 'ESCALA')).fetchone():
            return
        if not _destinos(db, area)[1]:
            return
        from . import avisos
        enviadas += _enviar_aviso(db, avisos.gerentes(db), corpo + ' Sem providência há %d dias: aviso à gerência.' % dias_vencido)
        db.execute('INSERT INTO enf_avisos (chave, referencia, fase, enviado_em) VALUES (?,?,?,?)', (chave, ref, 'ESCALA', agora()))

    def validade(area, chave, item_id, nome, onde, val):
        if not val:
            return
        dias = (date.fromisoformat(val) - hoje).days
        fase = _fase_validade(dias)
        if fase is None:
            return
        tentar(area, chave, '%s:%s' % (item_id, val), fase, _texto_validade(nome, onde, val, dias, fase), -dias if dias < 0 else 0)

    for c in db.execute("SELECT c.id AS cid, c.nome AS cnome, c.tipo, i.id, i.nome, i.validade FROM enf_carrinho_itens i JOIN enf_carrinhos c ON c.id=i.carrinho_id WHERE c.ativo=1 AND i.validade IS NOT NULL"):
        validade('radioprotecao' if c['tipo'] == 'KIT' else 'carrinho', 'carrinho_item', c['id'], c['nome'], c['cnome'], c['validade'])
    for m in db.execute('SELECT * FROM enf_medicamentos WHERE ativo=1 AND validade IS NOT NULL'):
        validade('medicamentos', 'medicamento', m['id'], m['nome'], m['local'] or 'estoque', m['validade'])
    for p in db.execute('SELECT * FROM enf_pacotes WHERE usado_em IS NULL'):
        validade('esterilizacao', 'pacote', p['id'], p['descricao'], 'pacote ' + p['codigo'], p['validade'])
    for e in db.execute('SELECT * FROM enf_equipamentos WHERE ativo=1 AND proxima_manutencao IS NOT NULL'):
        dias = (date.fromisoformat(e['proxima_manutencao']) - hoje).days
        fase = _fase_validade(dias)
        if fase is not None:
            data = e['proxima_manutencao']
            texto = ('Enfermagem: a manutenção/calibração de %s %s' % (e['nome'], 'está ATRASADA desde %s/%s/%s.' % (data[8:10], data[5:7], data[:4]) if dias < 0 else
                                                                      'vence em %d dia(s) (%s/%s/%s).' % (dias, data[8:10], data[5:7], data[:4])))
            tentar('equipamentos', 'manutencao', '%s:%s' % (e['id'], data), fase, texto, -dias if dias < 0 else 0)
    # teste diário não feito até o horário configurado
    if agora_dt.strftime('%H:%M') >= hora_teste(db):
        for e in db.execute('SELECT * FROM enf_equipamentos WHERE ativo=1 AND teste_diario=1'):
            if not db.execute('SELECT 1 FROM enf_testes WHERE equipamento_id=? AND substr(data_hora,1,10)=?', (e['id'], hoje.isoformat())).fetchone():
                tentar('equipamentos', 'teste_diario', '%s:%s' % (e['id'], hoje.isoformat()), 'HOJE', 'Enfermagem: o teste diário de %s ainda não foi registrado hoje.' % e['nome'])
        if not rp_teste_hoje(db) and db.execute("SELECT 1 FROM enf_carrinhos WHERE tipo='KIT' AND ativo=1").fetchone():
            tentar('radioprotecao', 'teste_monitor', hoje.isoformat(), 'HOJE', 'Enfermagem: o teste diário do monitor de contaminação ainda não foi registrado hoje.')
    db.commit()
    return enviadas
