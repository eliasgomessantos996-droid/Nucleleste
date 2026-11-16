"""Regras do prontuário: número do paciente, documentos (criar, salvar, concluir, reabrir, excluir), histórico e pendências.

As funções não fazem commit: quem chama (rota ou lançamento do atendimento) confirma a transação.
"""
import json
import secrets
import sqlite3

from . import fichas
from . import prontuario_modelos as pm
from .db import agora

ROTULO_SITUACAO = {'PENDENTE': 'Pendente', 'RASCUNHO': 'Em preenchimento', 'CONCLUIDO': 'Concluído'}


class ErroProntuario(Exception):
    """Operação recusada (documento concluído, tipo desconhecido...). A mensagem vai para a tela."""


def garantir(db, cliente_id, usuario):
    """Devolve o prontuário do cliente, criando-o na primeira vez. O número tem 6 dígitos a partir do id (único)."""
    row = db.execute('SELECT * FROM prontuarios WHERE cliente_id=?', (cliente_id,)).fetchone()
    if row:
        return row
    # o número depende do id gerado: grava um provisório único e troca logo em seguida, na mesma transação
    cur = db.execute('INSERT INTO prontuarios (cliente_id, numero, criado_em, criado_por) VALUES (?,?,?,?)',
                     (cliente_id, 'tmp-' + secrets.token_hex(8), agora(), usuario))
    db.execute('UPDATE prontuarios SET numero=? WHERE id=?', ('%06d' % cur.lastrowid, cur.lastrowid))
    return db.execute('SELECT * FROM prontuarios WHERE id=?', (cur.lastrowid,)).fetchone()


def _consulta(db, sql, params):
    """Tabelas de outros módulos podem não existir em bancos antigos: nesse caso a seção sai vazia."""
    try:
        return db.execute(sql, params).fetchall()
    except sqlite3.OperationalError:
        return []


def _perguntas_do_exame(exame):
    """(slug da ficha PNT, [[texto, rótulo], ...]) do exame. Sem ficha PNT: slug vazio e lista vazia."""
    slug, perguntas = fichas.questionario_do_exame(exame)
    if not slug:
        return '', []
    return slug, [list(p) for p in perguntas]


def _alergias(perguntas, respostas):
    """Justificativa da pergunta de alergia do questionário, quando a resposta é SIM. Senão, vazio."""
    for i, (texto, _rotulo) in enumerate(perguntas, 1):
        if texto == fichas.ALERGIA[0] and respostas.get('r%d' % i) == 'SIM':
            return (respostas.get('o%d' % i) or '').strip()
    return ''


def contexto_atendimento(db, atendimento_id):
    """Valores que os modelos copiam do atendimento: exame, medicamentos, exame anterior, local de origem, alergias,
    questionário PNT e respostas, e o registro do radiofármaco do mesmo dia."""
    if not atendimento_id:
        return {}
    at = db.execute('SELECT * FROM atendimentos WHERE id=?', (atendimento_id,)).fetchone()
    if not at:
        return {}
    exame = db.execute('SELECT * FROM exames WHERE nome=?', ((at['exame'] or '').strip(),)).fetchone()
    slug, perguntas = _perguntas_do_exame(exame)
    try:
        respostas = json.loads(at['respostas'] or '{}')
    except ValueError:
        respostas = {}
    if respostas.get('manual'):
        respostas = {}
    ctx = {
        'exame': at['exame'] or '',
        'data': at['data'] or '',
        'medicamentos': at['medicamentos'] or '',
        'exame_anterior': at['exame_anterior'] or '',
        'hospital_setor': at['interno_local'] or '',
        'alergias': _alergias(perguntas, respostas),
        '_slug': slug,
        '_perguntas': perguntas,
        'respostas': respostas,
    }
    real = _consulta(db, 'SELECT farmaco, radio, lote, ativ_prescrita, ativ_administrada FROM realizacoes '
                         'WHERE cliente_id=? AND data=? ORDER BY id DESC LIMIT 1', (at['cliente_id'], at['data']))
    if real:
        r = real[0]
        ctx.update({'radiofarmaco': r['farmaco'] or r['radio'] or '', 'lote': r['lote'] or '',
                    'ativ_prescrita': r['ativ_prescrita'] or '', 'ativ_administrada': r['ativ_administrada'] or ''})
    return ctx


def criar_doc(db, cliente_id, tipo, usuario, atendimento_id=None, situacao='PENDENTE'):
    """Cria um documento do tipo dado no prontuário do cliente. Devolve o id do documento."""
    if tipo not in pm.MODELOS:
        raise ErroProntuario('Tipo de documento desconhecido.')
    pront = garantir(db, cliente_id, usuario)
    dados = pm.valores_iniciais(tipo, contexto_atendimento(db, atendimento_id))
    momento = agora()
    cur = db.execute(
        'INSERT INTO prontuario_docs (prontuario_id, cliente_id, atendimento_id, tipo, titulo, dados, situacao, '
        'criado_em, criado_por, atualizado_em, atualizado_por) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
        (pront['id'], cliente_id, atendimento_id, tipo, pm.obter(tipo)['titulo'], json.dumps(dados, ensure_ascii=False),
         situacao, momento, usuario, momento, usuario))
    return cur.lastrowid


def obter_doc(db, doc_id):
    """Documento com os dados do paciente, do prontuário e do atendimento vinculado (ou None)."""
    return db.execute(
        'SELECT d.*, p.numero, c.nome AS cliente_nome, c.nome_mae, c.data_nasc, c.cpf, c.convenio AS convenio_cliente, '
        'a.data AS at_data, a.exame AS at_exame, a.convenio AS at_convenio, a.interno, a.interno_local '
        'FROM prontuario_docs d JOIN prontuarios p ON p.id=d.prontuario_id '
        'LEFT JOIN clientes c ON c.id=d.cliente_id LEFT JOIN atendimentos a ON a.id=d.atendimento_id '
        'WHERE d.id=?', (doc_id,)).fetchone()


def _doc(db, doc_id):
    doc = db.execute('SELECT * FROM prontuario_docs WHERE id=?', (doc_id,)).fetchone()
    if doc is None:
        raise ErroProntuario('Documento não encontrado.')
    return doc


def _base(doc):
    return json.loads(doc['dados'] or '{}')


def _gravar_respostas_atendimento(db, doc, dados):
    """PNT digital ligado a atendimento: grava as respostas no mesmo formato do lançamento (sem a marca 'manual'),
    para a ficha PNT impressa do atendimento sair preenchida."""
    if doc['tipo'] != 'pnt' or not doc['atendimento_id'] or not dados.get('_pnt_slug'):
        return
    saida = {}
    for i in range(1, len(dados.get('_pnt_perguntas') or []) + 1):
        r = dados.get('r%d' % i) or ''
        if r in ('SIM', 'NÃO'):
            saida['r%d' % i] = r
        if r == 'SIM' and (dados.get('o%d' % i) or ''):
            saida['o%d' % i] = dados['o%d' % i]
    db.execute('UPDATE atendimentos SET respostas=? WHERE id=?',
               (json.dumps(saida, ensure_ascii=False) if saida else None, doc['atendimento_id']))


def salvar_doc(db, doc_id, form, usuario, concluir=False):
    """Grava os campos do formulário. Com `concluir`, fecha o documento (CONCLUIDO) só se não faltar nada.
    Se faltar algo, grava como rascunho e devolve a lista de pendências (rótulos). Sem faltas devolve []."""
    doc = _doc(db, doc_id)
    if doc['situacao'] == 'CONCLUIDO':
        raise ErroProntuario('Documento concluído não pode ser alterado. A administração pode reabri-lo para correção.')
    tipo = doc['tipo']
    dados = pm.calcular_campos(tipo, pm.ler_form(tipo, form, _base(doc)))
    nome = (form.get('profissional_nome') or '').strip()
    conselho = (form.get('profissional_conselho') or form.get('conselho') or '').strip()
    if conselho not in pm.CONSELHOS_PROFISSIONAL:
        conselho = (doc['profissional_conselho'] or '') if (doc['profissional_conselho'] in pm.CONSELHOS_PROFISSIONAL) else ''
    registro = (form.get('profissional_registro') or '').strip()
    faltas = pm.faltando(tipo, dados)
    if not nome:
        faltas.insert(0, 'Nome do profissional')
    momento = agora()
    if concluir and not faltas:
        situacao, concluido_em, concluido_por = 'CONCLUIDO', momento, usuario
    else:
        situacao, concluido_em, concluido_por = 'RASCUNHO', None, None
    db.execute(
        'UPDATE prontuario_docs SET dados=?, situacao=?, profissional_nome=?, profissional_conselho=?, profissional_registro=?, '
        'atualizado_em=?, atualizado_por=?, concluido_em=?, concluido_por=? WHERE id=?',
        (json.dumps(dados, ensure_ascii=False), situacao, nome, conselho, registro, momento, usuario, concluido_em, concluido_por, doc_id))
    _gravar_respostas_atendimento(db, doc, dados)
    return faltas if concluir else []


def chaves_pendentes(form, doc):
    """Chaves dos campos que impedem concluir (para destacar na tela), inclusive o nome do profissional."""
    dados = pm.calcular_campos(doc['tipo'], pm.ler_form(doc['tipo'], form, _base(doc)))
    chaves = pm.chaves_faltando(doc['tipo'], dados)
    if not (form.get('profissional_nome') or '').strip():
        chaves.insert(0, 'profissional_nome')
    return chaves


def reabrir_doc(db, doc_id, usuario):
    doc = _doc(db, doc_id)
    if doc['situacao'] != 'CONCLUIDO':
        raise ErroProntuario('Este documento não está concluído.')
    db.execute("UPDATE prontuario_docs SET situacao='RASCUNHO', atualizado_em=?, atualizado_por=? WHERE id=?",
               (agora(), usuario, doc_id))


def excluir_doc(db, doc_id):
    _doc(db, doc_id)
    db.execute('DELETE FROM prontuario_docs WHERE id=?', (doc_id,))


def sugeridos(db, atendimento):
    """Documentos sugeridos para um atendimento que ainda não existem nele: SAE sempre; PNT quando o exame tem ficha PNT;
    Ficha MIBI e NEWS quando o exame é MIBI (NEWS também no PULMONAR); radiofármaco sempre."""
    exame = db.execute('SELECT * FROM exames WHERE nome=?', ((atendimento['exame'] or '').strip(),)).fetchone()
    slug, _ = _perguntas_do_exame(exame)
    nome = (atendimento['exame'] or '').upper()
    tipos = ['sae']
    if slug:
        tipos.append('pnt')
    if 'MIBI' in nome:
        tipos += ['ficha_mibi', 'news']
    if 'PULMONAR' in nome and 'news' not in tipos:
        tipos.append('news')
    tipos.append('radiofarmaco')
    existentes = {d['tipo'] for d in atendimento['docs']}
    return [{'tipo': t, 'titulo': pm.obter(t)['titulo'], 'sigla': pm.obter(t)['sigla']} for t in tipos if t not in existentes]


def historico(db, cliente_id):
    """Tudo do prontuário de um paciente. None se o cliente não existir."""
    cliente = db.execute('SELECT * FROM clientes WHERE id=?', (cliente_id,)).fetchone()
    if cliente is None:
        return None
    prontuario = db.execute('SELECT * FROM prontuarios WHERE cliente_id=?', (cliente_id,)).fetchone()
    atendimentos = db.execute(
        "SELECT * FROM atendimentos WHERE cliente_id=? OR (COALESCE(cpf,'')<>'' AND cpf=?) ORDER BY data DESC, id DESC",
        (cliente_id, cliente['cpf'] or '-')).fetchall()
    docs = db.execute('SELECT * FROM prontuario_docs WHERE cliente_id=? ORDER BY criado_em, id', (cliente_id,)).fetchall()
    ids = {a['id'] for a in atendimentos}
    por_atendimento = {}
    for d in docs:
        if d['atendimento_id'] in ids:
            por_atendimento.setdefault(d['atendimento_id'], []).append(d)
    linhas = []
    for a in atendimentos:
        item = dict(a)
        item['docs'] = por_atendimento.get(a['id'], [])
        item['sugeridos'] = sugeridos(db, {'exame': a['exame'], 'docs': item['docs']})
        linhas.append(item)
    return {
        'cliente': cliente,
        'prontuario': prontuario,
        'atendimentos': linhas,
        'docs_avulsos': [d for d in docs if d['atendimento_id'] not in ids],
        'pendentes': [d for d in docs if d['situacao'] != 'CONCLUIDO'],
        'realizacoes': _consulta(db, 'SELECT data, exame, farmaco, radio, ativ_administrada, lote, laudo_situacao '
                                     'FROM realizacoes WHERE cliente_id=? ORDER BY data DESC, id DESC', (cliente_id,)),
        'doses': _consulta(db, 'SELECT data_dose, medicamento, mci, status FROM doses WHERE cliente_id=? '
                               'ORDER BY data_dose DESC, id DESC', (cliente_id,)),
        'pedidos': _consulta(db, 'SELECT data, exames, medico FROM pedidos_exame WHERE cliente_id=? ORDER BY data DESC, id DESC',
                             (cliente_id,)),
        'guias': _consulta(db, 'SELECT modelo, criado_em FROM guias_convenio WHERE cliente_id=? ORDER BY criado_em DESC, id DESC',
                           (cliente_id,)),
    }


_SQL_DOCS = ("SELECT d.id, d.tipo, d.titulo, d.situacao, d.criado_em, d.concluido_em, d.atendimento_id, "
             "c.id AS cliente_id, c.nome AS cliente_nome, p.numero, a.data AS atendimento_data, "
             "a.exame AS atendimento_exame, a.interno, a.interno_local "
             "FROM prontuario_docs d JOIN prontuarios p ON p.id=d.prontuario_id "
             "LEFT JOIN clientes c ON c.id=d.cliente_id LEFT JOIN atendimentos a ON a.id=d.atendimento_id ")


def pendencias(db, limite=200):
    """Documentos ainda não concluídos de todos os pacientes, mais antigos primeiro. Internos vêm com o local de origem."""
    return db.execute(_SQL_DOCS + "WHERE d.situacao<>'CONCLUIDO' "
                      "ORDER BY COALESCE(a.data, substr(d.criado_em,1,10)), d.id LIMIT ?", (limite,)).fetchall()


def ultimos_concluidos(db, limite=20):
    return db.execute(_SQL_DOCS + "WHERE d.situacao='CONCLUIDO' ORDER BY d.concluido_em DESC, d.id DESC LIMIT ?", (limite,)).fetchall()


def buscar_pacientes(db, termo, limite=50):
    """Pacientes pelo nome, CPF, código ou número do prontuário."""
    t = (termo or '').strip()
    numero = t.zfill(6) if t.isdigit() else '-'
    return db.execute(
        'SELECT c.id, c.nome, c.cpf, c.data_nasc, c.convenio, p.numero FROM clientes c '
        'LEFT JOIN prontuarios p ON p.cliente_id=c.id '
        'WHERE UPPER(c.nome) LIKE ? OR c.cpf LIKE ? OR p.numero=? OR CAST(c.id AS TEXT)=? ORDER BY c.nome LIMIT ?',
        ('%' + t.upper() + '%', t + '%', numero, t, limite)).fetchall()
