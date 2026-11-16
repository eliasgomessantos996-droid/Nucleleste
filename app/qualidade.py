"""Gestão da Qualidade: problemas e ciclo PDCA, Ishikawa, 5 Porquês, GUT, 5W2H, matriz de risco, SWOT, fluxogramas,
organograma, ocorrências, pesquisa de satisfação e avaliação de fornecedores (ONA).

As tabelas ficam no próprio sistema.db com o prefixo cq_ e são criadas por `garantir(db)` (não mexe nas tabelas dos
outros módulos). A cadeia de trabalho é Indicador -> Problema -> Causas (Ishikawa, 5 Porquês) -> Plano (5W2H) -> PDCA.
"""
from __future__ import annotations

import json
from datetime import date

from .db import agora

SEIS_M = ('Método', 'Máquina', 'Mão de obra', 'Material', 'Meio ambiente', 'Medição')
STATUS_PROBLEMA = ('RASCUNHO', 'ABERTO', 'EM ANDAMENTO', 'CONCLUÍDO', 'DESCARTADO')   # RASCUNHO: sugerido pelo robô
FASES_PDCA = (('P', 'Planejar'), ('D', 'Fazer'), ('C', 'Checar'), ('A', 'Agir'))
STATUS_ACAO = ('A FAZER', 'EM ANDAMENTO', 'CONCLUÍDA', 'CANCELADA')
RESPOSTAS_RISCO = ('Mitigar', 'Evitar', 'Transferir', 'Aceitar')
QUADRANTES_SWOT = (('F', 'Forças'), ('FR', 'Fraquezas'), ('O', 'Oportunidades'), ('A', 'Ameaças'))
TIPOS_OCORRENCIA = ('Não conformidade', 'Evento adverso', 'Quase falha', 'Reclamação', 'Elogio', 'Retrabalho / repetição de exame',
                    'Laudo retificado', 'Equipamento parado')
GRAVIDADES = ('Leve', 'Moderada', 'Grave')
STATUS_OCORRENCIA = ('ABERTA', 'EM TRATAMENTO', 'ENCERRADA')
MOTIVOS_FALTA = ('Esqueceu / não avisou', 'Doença / internação', 'Transporte', 'Sem preparo adequado', 'Autorização do convênio',
                 'Remarcou por conta própria', 'Contato não atendido', 'Óbito', 'Outro')
# classificação do fornecedor pelo percentual da nota máxima
CLASSES_FORNECEDOR = ((80, 'APROVADO'), (60, 'APROVADO COM RESTRIÇÕES'), (0, 'REPROVADO'))
CRITERIOS_PADRAO = (
    ('Qualidade do produto ou serviço', 'Atende às especificações, sem defeitos, devoluções ou retrabalho.', 3),
    ('Prazo de entrega', 'Entrega no prazo combinado; atrasos e entregas parciais reduzem a nota.', 2),
    ('Atendimento e comunicação', 'Responde às solicitações, resolve problemas e informa mudanças.', 1),
    ('Preço e condições comerciais', 'Preço compatível com o mercado, condições de pagamento e cumprimento do acordado.', 1),
    ('Documentação e licenças', 'Notas fiscais corretas, alvarás, licenças sanitárias/CNEN quando aplicável, certificados e laudos.', 2),
    ('Segurança e conformidade legal', 'Cumpre normas de segurança, biossegurança e radioproteção; rastreabilidade de lotes.', 2),
)
# metas iniciais dos indicadores (a gerência muda na tela de indicadores). sentido: 'min' = quanto maior melhor
METAS_PADRAO = {
    'comparecimento': (85.0, 'min'), 'faltas': (15.0, 'max'), 'laudo_24h': (90.0, 'min'), 'laudo_horas': (24.0, 'max'),
    'laudos_pendentes': (0, 'max'), 'identificacao': (98.0, 'min'), 'registro_completo': (95.0, 'min'), 'desvio_atividade': (5.0, 'max'),
    'glosa': (3.0, 'max'), 'recebimento_atrasado': (10.0, 'max'), 'contas_atrasadas': (0, 'max'),
    'documentos_vencidos': (0, 'max'), 'chamados_horas': (4.0, 'max'), 'ocorrencias_graves': (0, 'max'), 'satisfacao': (9.0, 'min'),
    'fornecedores_avaliados': (100.0, 'min'), 'retrabalho': (2.0, 'max'), 'resgate': (50.0, 'min'),
}


class ErroQualidade(ValueError):
    """Erro de validação mostrado ao usuário."""


ESQUEMA = """
CREATE TABLE IF NOT EXISTS cq_problemas (
    id INTEGER PRIMARY KEY, titulo TEXT NOT NULL, descricao TEXT NOT NULL DEFAULT '', origem TEXT NOT NULL DEFAULT 'MANUAL',
    indicador TEXT, evidencia TEXT, status TEXT NOT NULL DEFAULT 'ABERTO', fase TEXT NOT NULL DEFAULT 'P',
    gut_g INTEGER NOT NULL DEFAULT 3, gut_u INTEGER NOT NULL DEFAULT 3, gut_t INTEGER NOT NULL DEFAULT 3,
    plan_meta TEXT NOT NULL DEFAULT '', plan_causa TEXT NOT NULL DEFAULT '', plan_indicador TEXT NOT NULL DEFAULT '',
    do_execucao TEXT NOT NULL DEFAULT '', check_resultado TEXT NOT NULL DEFAULT '', check_data TEXT,
    act_padrao TEXT NOT NULL DEFAULT '', responsavel TEXT NOT NULL DEFAULT '', prazo TEXT, chave_robo TEXT,
    criado_por TEXT, criado_em TEXT, atualizado_por TEXT, atualizado_em TEXT
);
CREATE INDEX IF NOT EXISTS ix_cq_prob_status ON cq_problemas(status);
CREATE INDEX IF NOT EXISTS ix_cq_prob_robo ON cq_problemas(chave_robo);
CREATE TABLE IF NOT EXISTS cq_causas (
    id INTEGER PRIMARY KEY, problema_id INTEGER NOT NULL, categoria TEXT NOT NULL, texto TEXT NOT NULL,
    principal INTEGER NOT NULL DEFAULT 0, criado_em TEXT
);
CREATE INDEX IF NOT EXISTS ix_cq_causas_prob ON cq_causas(problema_id);
CREATE TABLE IF NOT EXISTS cq_porques (
    problema_id INTEGER NOT NULL, nivel INTEGER NOT NULL, resposta TEXT NOT NULL DEFAULT '', PRIMARY KEY (problema_id, nivel)
);
CREATE TABLE IF NOT EXISTS cq_acoes (
    id INTEGER PRIMARY KEY, problema_id INTEGER, o_que TEXT NOT NULL, por_que TEXT NOT NULL DEFAULT '', onde TEXT NOT NULL DEFAULT '',
    quando TEXT, quem TEXT NOT NULL DEFAULT '', como TEXT NOT NULL DEFAULT '', quanto REAL, status TEXT NOT NULL DEFAULT 'A FAZER',
    concluida_em TEXT, criado_por TEXT, criado_em TEXT, atualizado_em TEXT
);
CREATE INDEX IF NOT EXISTS ix_cq_acoes_prob ON cq_acoes(problema_id);
CREATE TABLE IF NOT EXISTS cq_riscos (
    id INTEGER PRIMARY KEY, titulo TEXT NOT NULL, processo TEXT NOT NULL DEFAULT '', causa TEXT NOT NULL DEFAULT '',
    consequencia TEXT NOT NULL DEFAULT '', probabilidade INTEGER NOT NULL DEFAULT 3, impacto INTEGER NOT NULL DEFAULT 3,
    resposta TEXT NOT NULL DEFAULT 'Mitigar', acao TEXT NOT NULL DEFAULT '', responsavel TEXT NOT NULL DEFAULT '', prazo TEXT,
    status TEXT NOT NULL DEFAULT 'ATIVO', criado_por TEXT, criado_em TEXT, atualizado_em TEXT
);
CREATE TABLE IF NOT EXISTS cq_swot_analises (
    id INTEGER PRIMARY KEY, titulo TEXT NOT NULL, data TEXT, obs TEXT NOT NULL DEFAULT '', criado_por TEXT, criado_em TEXT
);
CREATE TABLE IF NOT EXISTS cq_swot_itens (
    id INTEGER PRIMARY KEY, analise_id INTEGER NOT NULL, quadrante TEXT NOT NULL, texto TEXT NOT NULL, peso INTEGER NOT NULL DEFAULT 3
);
CREATE INDEX IF NOT EXISTS ix_cq_swot ON cq_swot_itens(analise_id);
CREATE TABLE IF NOT EXISTS cq_processos (
    id INTEGER PRIMARY KEY, nome TEXT NOT NULL, setor TEXT NOT NULL DEFAULT '', objetivo TEXT NOT NULL DEFAULT '',
    versao INTEGER NOT NULL DEFAULT 1, status TEXT NOT NULL DEFAULT 'RASCUNHO', dados TEXT NOT NULL DEFAULT '{}',
    aprovado_por TEXT, aprovado_em TEXT, criado_por TEXT, criado_em TEXT, atualizado_por TEXT, atualizado_em TEXT
);
CREATE TABLE IF NOT EXISTS cq_organograma (
    id INTEGER PRIMARY KEY, cargo TEXT NOT NULL, pessoa TEXT NOT NULL DEFAULT '', setor TEXT NOT NULL DEFAULT '',
    pai_id INTEGER, funcionario_id INTEGER, cor TEXT NOT NULL DEFAULT '', ordem INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS cq_ocorrencias (
    id INTEGER PRIMARY KEY, data TEXT NOT NULL, tipo TEXT NOT NULL, setor TEXT NOT NULL DEFAULT '', exame TEXT NOT NULL DEFAULT '',
    convenio TEXT NOT NULL DEFAULT '', descricao TEXT NOT NULL, gravidade TEXT NOT NULL DEFAULT 'Leve', acao_imediata TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'ABERTA', problema_id INTEGER, criado_por TEXT, criado_em TEXT, atualizado_em TEXT
);
CREATE INDEX IF NOT EXISTS ix_cq_ocor_data ON cq_ocorrencias(data);
CREATE TABLE IF NOT EXISTS cq_pesquisas (
    id INTEGER PRIMARY KEY, data TEXT NOT NULL, nota INTEGER NOT NULL, exame TEXT NOT NULL DEFAULT '', comentario TEXT NOT NULL DEFAULT '',
    criado_por TEXT, criado_em TEXT
);
CREATE INDEX IF NOT EXISTS ix_cq_pesq_data ON cq_pesquisas(data);
CREATE TABLE IF NOT EXISTS cq_falta_motivos (
    horario_id INTEGER PRIMARY KEY, motivo TEXT NOT NULL, registrado_por TEXT, registrado_em TEXT
);
CREATE TABLE IF NOT EXISTS cq_kpi_metas (
    chave TEXT PRIMARY KEY, meta REAL NOT NULL, sentido TEXT NOT NULL, atualizado_por TEXT, atualizado_em TEXT
);
CREATE TABLE IF NOT EXISTS cq_forn_criterios (
    id INTEGER PRIMARY KEY, nome TEXT NOT NULL, descricao TEXT NOT NULL DEFAULT '', peso INTEGER NOT NULL DEFAULT 1,
    ativo INTEGER NOT NULL DEFAULT 1, ordem INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS cq_forn_avaliacoes (
    id INTEGER PRIMARY KEY, fornecedor_id INTEGER NOT NULL, data TEXT NOT NULL, periodo TEXT NOT NULL DEFAULT '',
    avaliador TEXT, percentual REAL NOT NULL, classificacao TEXT NOT NULL, critico INTEGER NOT NULL DEFAULT 0,
    obs TEXT NOT NULL DEFAULT '', acao TEXT NOT NULL DEFAULT '', proxima TEXT, criado_em TEXT
);
CREATE INDEX IF NOT EXISTS ix_cq_forn_av ON cq_forn_avaliacoes(fornecedor_id, data);
CREATE TABLE IF NOT EXISTS cq_forn_notas (
    avaliacao_id INTEGER NOT NULL, criterio_id INTEGER NOT NULL, criterio TEXT NOT NULL, peso INTEGER NOT NULL, nota INTEGER NOT NULL,
    comentario TEXT NOT NULL DEFAULT '', PRIMARY KEY (avaliacao_id, criterio_id)
);
CREATE TABLE IF NOT EXISTS cq_protocolos (
    id INTEGER PRIMARY KEY, codigo TEXT NOT NULL, titulo TEXT NOT NULL, setor TEXT NOT NULL DEFAULT '', objetivo TEXT NOT NULL DEFAULT '',
    abrangencia TEXT NOT NULL DEFAULT '', responsaveis TEXT NOT NULL DEFAULT '', definicoes TEXT NOT NULL DEFAULT '', materiais TEXT NOT NULL DEFAULT '',
    passos TEXT NOT NULL DEFAULT '', registros TEXT NOT NULL DEFAULT '', referencias TEXT NOT NULL DEFAULT '', cuidados TEXT NOT NULL DEFAULT '',
    fluxo_modelo TEXT NOT NULL DEFAULT '', fluxo_id INTEGER, modelo TEXT NOT NULL DEFAULT '', versao INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'RASCUNHO', elaborado_por TEXT NOT NULL DEFAULT '', revisado_por TEXT NOT NULL DEFAULT '',
    aprovado_por TEXT, aprovado_em TEXT, proxima_revisao TEXT, criado_por TEXT, criado_em TEXT, atualizado_por TEXT, atualizado_em TEXT
);
CREATE TABLE IF NOT EXISTS cq_robo_execucoes (
    id INTEGER PRIMARY KEY, executado_em TEXT NOT NULL, de TEXT, ate TEXT, achados INTEGER NOT NULL DEFAULT 0,
    novos INTEGER NOT NULL DEFAULT 0, por TEXT, resumo TEXT
);
CREATE TABLE IF NOT EXISTS cq_robo_descartes (
    chave TEXT PRIMARY KEY, ate TEXT NOT NULL, por TEXT, em TEXT
);
"""
_GARANTIDOS = set()


def garantir(db):
    """Cria as tabelas da Qualidade (uma vez por banco em cada processo) e os critérios de fornecedor padrão."""
    from .anexos import caminho_do_banco
    chave = caminho_do_banco(db) or id(db)
    if chave in _GARANTIDOS:
        return
    db.executescript(ESQUEMA)
    if not db.execute('SELECT 1 FROM cq_forn_criterios LIMIT 1').fetchone():
        db.executemany('INSERT INTO cq_forn_criterios (nome, descricao, peso, ordem) VALUES (?,?,?,?)',
                       [(n, d, p, i) for i, (n, d, p) in enumerate(CRITERIOS_PADRAO)])
    db.commit()
    _GARANTIDOS.add(chave)


# ------------------------------------------------------------------ utilidades
def _txt(form, campo, limite=2000, obrigatorio=False, rotulo=''):
    v = str(form.get(campo) or '').strip()[:limite]
    if obrigatorio and not v:
        raise ErroQualidade('Preencha %s.' % (rotulo or campo))
    return v


def _nota(form, campo, minimo=1, maximo=5, padrao=3):
    try:
        v = int(str(form.get(campo, padrao)).strip())
    except ValueError:
        raise ErroQualidade('Use um número de %d a %d.' % (minimo, maximo))
    if not minimo <= v <= maximo:
        raise ErroQualidade('Use um número de %d a %d.' % (minimo, maximo))
    return v


def _data(form, campo, obrigatorio=False):
    v = str(form.get(campo) or '').strip()
    if not v:
        if obrigatorio:
            raise ErroQualidade('Informe a data.')
        return None
    try:
        return date.fromisoformat(v).isoformat()
    except ValueError:
        raise ErroQualidade('Data inválida.')


def _valor(form, campo):
    v = str(form.get(campo) or '').strip().replace('R$', '').replace(' ', '')
    if not v:
        return None
    if ',' in v:
        v = v.replace('.', '').replace(',', '.')
    try:
        return round(float(v), 2)
    except ValueError:
        raise ErroQualidade('Valor inválido.')


def gut_pontos(g, u, t):
    return int(g) * int(u) * int(t)


def nivel_risco(prob, imp):
    """Nível da matriz 5x5: (pontos, rótulo, cor)."""
    p = int(prob) * int(imp)
    if p >= 15:
        return p, 'Crítico', '#c62828'
    if p >= 10:
        return p, 'Alto', '#ef6c00'
    if p >= 5:
        return p, 'Moderado', '#f9a825'
    return p, 'Baixo', '#2e7d32'


# ------------------------------------------------------------------ problemas e PDCA
def problemas(db, status=None):
    sql = 'SELECT * FROM cq_problemas'
    args = ()
    if status:
        sql += ' WHERE status=?'
        args = (status,)
    linhas = [dict(r) for r in db.execute(sql + ' ORDER BY id DESC', args)]
    for p in linhas:
        p['gut'] = gut_pontos(p['gut_g'], p['gut_u'], p['gut_t'])
    return linhas


def problema(db, pid):
    r = db.execute('SELECT * FROM cq_problemas WHERE id=?', (pid,)).fetchone()
    if r is None:
        raise ErroQualidade('Problema não encontrado.')
    p = dict(r)
    p['gut'] = gut_pontos(p['gut_g'], p['gut_u'], p['gut_t'])
    p['evidencia_lista'] = json.loads(p['evidencia']) if p['evidencia'] else []
    p['causas'] = [dict(c) for c in db.execute('SELECT * FROM cq_causas WHERE problema_id=? ORDER BY categoria, id', (pid,))]
    porques = {r['nivel']: r['resposta'] for r in db.execute('SELECT nivel, resposta FROM cq_porques WHERE problema_id=?', (pid,))}
    p['porques'] = [porques.get(n, '') for n in range(1, 6)]
    p['acoes'] = acoes(db, pid)
    return p


def criar_problema(db, form, usuario, origem='MANUAL', evidencia=None, chave_robo=None):
    titulo = _txt(form, 'titulo', 200, True, 'o título do problema')
    agora_txt = agora()
    cur = db.execute(
        'INSERT INTO cq_problemas (titulo, descricao, origem, indicador, evidencia, gut_g, gut_u, gut_t, plan_meta, plan_causa, '
        'plan_indicador, do_execucao, check_resultado, check_data, act_padrao, responsavel, prazo, chave_robo, criado_por, criado_em, '
        'atualizado_por, atualizado_em) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
        (titulo, _txt(form, 'descricao'), origem, _txt(form, 'indicador', 60) or None,
         json.dumps(evidencia, ensure_ascii=False) if evidencia else None,
         _nota(form, 'gut_g'), _nota(form, 'gut_u'), _nota(form, 'gut_t'), _txt(form, 'plan_meta'), _txt(form, 'plan_causa'),
         _txt(form, 'plan_indicador'), _txt(form, 'do_execucao'), _txt(form, 'check_resultado'), _data(form, 'check_data'),
         _txt(form, 'act_padrao'), _txt(form, 'responsavel', 120), _data(form, 'prazo'), chave_robo, usuario, agora_txt, usuario, agora_txt))
    db.commit()
    return cur.lastrowid


def salvar_problema(db, pid, form, usuario):
    problema(db, pid)
    status = _txt(form, 'status', 30) or 'ABERTO'
    if status not in STATUS_PROBLEMA:
        raise ErroQualidade('Situação inválida.')
    fase = _txt(form, 'fase', 2) or 'P'
    if fase not in dict(FASES_PDCA):
        raise ErroQualidade('Fase do PDCA inválida.')
    db.execute(
        'UPDATE cq_problemas SET titulo=?, descricao=?, status=?, fase=?, gut_g=?, gut_u=?, gut_t=?, plan_meta=?, plan_causa=?, '
        'plan_indicador=?, do_execucao=?, check_resultado=?, check_data=?, act_padrao=?, responsavel=?, prazo=?, atualizado_por=?, '
        'atualizado_em=? WHERE id=?',
        (_txt(form, 'titulo', 200, True, 'o título do problema'), _txt(form, 'descricao'), status, fase, _nota(form, 'gut_g'),
         _nota(form, 'gut_u'), _nota(form, 'gut_t'), _txt(form, 'plan_meta'), _txt(form, 'plan_causa'), _txt(form, 'plan_indicador'),
         _txt(form, 'do_execucao'), _txt(form, 'check_resultado'), _data(form, 'check_data'), _txt(form, 'act_padrao'),
         _txt(form, 'responsavel', 120), _data(form, 'prazo'), usuario, agora(), pid))
    db.commit()


def salvar_gut(db, pid, form, usuario):
    problema(db, pid)
    db.execute('UPDATE cq_problemas SET gut_g=?, gut_u=?, gut_t=?, atualizado_por=?, atualizado_em=? WHERE id=?',
               (_nota(form, 'gut_g'), _nota(form, 'gut_u'), _nota(form, 'gut_t'), usuario, agora(), pid))
    db.commit()


def excluir_problema(db, pid):
    for tabela in ('cq_causas', 'cq_porques', 'cq_acoes'):
        db.execute('DELETE FROM %s WHERE problema_id=?' % tabela, (pid,))
    db.execute('UPDATE cq_ocorrencias SET problema_id=NULL WHERE problema_id=?', (pid,))
    db.execute('DELETE FROM cq_problemas WHERE id=?', (pid,))
    db.commit()


def ranking_gut(db):
    """Problemas abertos ou em andamento, do maior para o menor G x U x T."""
    lista = [p for p in problemas(db) if p['status'] in ('ABERTO', 'EM ANDAMENTO')]
    lista.sort(key=lambda p: (-p['gut'], p['id']))
    return lista


# ------------------------------------------------------------------ Ishikawa e 5 Porquês
def adicionar_causa(db, pid, form):
    problema(db, pid)
    categoria = _txt(form, 'categoria', 40)
    if categoria not in SEIS_M:
        raise ErroQualidade('Escolha uma das categorias do Ishikawa (6M).')
    db.execute('INSERT INTO cq_causas (problema_id, categoria, texto, principal, criado_em) VALUES (?,?,?,?,?)',
               (pid, categoria, _txt(form, 'texto', 300, True, 'a causa'), 1 if form.get('principal') else 0, agora()))
    db.commit()


def alternar_causa_principal(db, cid):
    db.execute('UPDATE cq_causas SET principal=1-principal WHERE id=?', (cid,))
    db.commit()


def excluir_causa(db, cid):
    r = db.execute('SELECT problema_id FROM cq_causas WHERE id=?', (cid,)).fetchone()
    db.execute('DELETE FROM cq_causas WHERE id=?', (cid,))
    db.commit()
    return r['problema_id'] if r else None


def ishikawa(db, pid):
    """Causas agrupadas pelos 6M (todas as categorias aparecem, mesmo vazias)."""
    p = problema(db, pid)
    grupos = {m: [] for m in SEIS_M}
    for c in p['causas']:
        grupos.setdefault(c['categoria'], []).append(c)
    return {'problema': p['titulo'], 'grupos': [{'categoria': m, 'causas': grupos[m]} for m in SEIS_M]}


def salvar_porques(db, pid, form):
    problema(db, pid)
    for n in range(1, 6):
        db.execute('INSERT INTO cq_porques (problema_id, nivel, resposta) VALUES (?,?,?) '
                   'ON CONFLICT(problema_id, nivel) DO UPDATE SET resposta=excluded.resposta', (pid, n, _txt(form, 'porque_%d' % n, 500)))
    raiz = _txt(form, 'causa_raiz', 500)
    if raiz:
        db.execute('UPDATE cq_problemas SET plan_causa=? WHERE id=?', (raiz, pid))
    db.commit()


# ------------------------------------------------------------------ 5W2H
def acoes(db, pid=None, status=None):
    sql = ('SELECT a.*, p.titulo AS problema FROM cq_acoes a LEFT JOIN cq_problemas p ON p.id=a.problema_id WHERE 1=1')
    args = []
    if pid is not None:
        sql += ' AND a.problema_id=?'
        args.append(pid)
    if status:
        sql += ' AND a.status=?'
        args.append(status)
    hoje = date.today().isoformat()
    saida = []
    for r in db.execute(sql + ' ORDER BY CASE WHEN a.quando IS NULL THEN 1 ELSE 0 END, a.quando, a.id', args):
        a = dict(r)
        a['atrasada'] = bool(a['quando'] and a['quando'] < hoje and a['status'] in ('A FAZER', 'EM ANDAMENTO'))
        saida.append(a)
    return saida


def _dados_acao(form):
    status = _txt(form, 'status', 20) or 'A FAZER'
    if status not in STATUS_ACAO:
        raise ErroQualidade('Situação inválida.')
    return (_txt(form, 'o_que', 300, True, 'o que será feito (What)'), _txt(form, 'por_que', 500), _txt(form, 'onde', 200),
            _data(form, 'quando'), _txt(form, 'quem', 120), _txt(form, 'como', 800), _valor(form, 'quanto'), status)


def adicionar_acao(db, pid, form, usuario):
    if pid:
        problema(db, pid)
    dados = _dados_acao(form)
    cur = db.execute('INSERT INTO cq_acoes (problema_id, o_que, por_que, onde, quando, quem, como, quanto, status, concluida_em, '
                     'criado_por, criado_em, atualizado_em) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                     (pid or None,) + dados + (agora() if dados[-1] == 'CONCLUÍDA' else None, usuario, agora(), agora()))
    db.commit()
    return cur.lastrowid


def salvar_acao(db, aid, form):
    r = db.execute('SELECT problema_id, status FROM cq_acoes WHERE id=?', (aid,)).fetchone()
    if r is None:
        raise ErroQualidade('Ação não encontrada.')
    dados = _dados_acao(form)
    concluida = agora() if dados[-1] == 'CONCLUÍDA' and r['status'] != 'CONCLUÍDA' else None
    db.execute('UPDATE cq_acoes SET o_que=?, por_que=?, onde=?, quando=?, quem=?, como=?, quanto=?, status=?, '
               'concluida_em=COALESCE(?, CASE WHEN ?=\'CONCLUÍDA\' THEN concluida_em END), atualizado_em=? WHERE id=?',
               dados + (concluida, dados[-1], agora(), aid))
    db.commit()
    return r['problema_id']


def excluir_acao(db, aid):
    r = db.execute('SELECT problema_id FROM cq_acoes WHERE id=?', (aid,)).fetchone()
    db.execute('DELETE FROM cq_acoes WHERE id=?', (aid,))
    db.commit()
    return r['problema_id'] if r else None


# ------------------------------------------------------------------ matriz de risco
def riscos(db):
    saida = []
    for r in db.execute("SELECT * FROM cq_riscos ORDER BY probabilidade*impacto DESC, id"):
        x = dict(r)
        x['pontos'], x['nivel'], x['cor'] = nivel_risco(x['probabilidade'], x['impacto'])
        saida.append(x)
    return saida


def salvar_risco(db, form, usuario, rid=None):
    resposta = _txt(form, 'resposta', 20) or 'Mitigar'
    if resposta not in RESPOSTAS_RISCO:
        raise ErroQualidade('Resposta ao risco inválida.')
    status = _txt(form, 'status', 20) or 'ATIVO'
    dados = (_txt(form, 'titulo', 200, True, 'o risco'), _txt(form, 'processo', 120), _txt(form, 'causa', 500), _txt(form, 'consequencia', 500),
             _nota(form, 'probabilidade'), _nota(form, 'impacto'), resposta, _txt(form, 'acao', 800), _txt(form, 'responsavel', 120),
             _data(form, 'prazo'), status if status in ('ATIVO', 'TRATADO', 'ENCERRADO') else 'ATIVO')
    if rid:
        db.execute('UPDATE cq_riscos SET titulo=?, processo=?, causa=?, consequencia=?, probabilidade=?, impacto=?, resposta=?, acao=?, '
                   'responsavel=?, prazo=?, status=?, atualizado_em=? WHERE id=?', dados + (agora(), rid))
    else:
        rid = db.execute('INSERT INTO cq_riscos (titulo, processo, causa, consequencia, probabilidade, impacto, resposta, acao, responsavel, '
                         'prazo, status, criado_por, criado_em, atualizado_em) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                         dados + (usuario, agora(), agora())).lastrowid
    db.commit()
    return rid


def excluir_risco(db, rid):
    db.execute('DELETE FROM cq_riscos WHERE id=?', (rid,))
    db.commit()


def matriz_risco(lista):
    """Grade 5x5 (impacto nas colunas, probabilidade nas linhas, de 5 a 1) com os riscos ativos de cada célula."""
    grade = []
    for prob in range(5, 0, -1):
        linha = []
        for imp in range(1, 6):
            pontos, nivel, cor = nivel_risco(prob, imp)
            linha.append({'prob': prob, 'imp': imp, 'pontos': pontos, 'nivel': nivel, 'cor': cor,
                          'riscos': [r for r in lista if r['probabilidade'] == prob and r['impacto'] == imp and r['status'] != 'ENCERRADO']})
        grade.append(linha)
    return grade


# ------------------------------------------------------------------ SWOT
def swot_analises(db):
    return [dict(r) for r in db.execute('SELECT * FROM cq_swot_analises ORDER BY id DESC')]


def criar_swot(db, form, usuario):
    aid = db.execute('INSERT INTO cq_swot_analises (titulo, data, obs, criado_por, criado_em) VALUES (?,?,?,?,?)',
                     (_txt(form, 'titulo', 200, True, 'o título da análise'), _data(form, 'data') or date.today().isoformat(),
                      _txt(form, 'obs'), usuario, agora())).lastrowid
    db.commit()
    return aid


def swot(db, aid):
    a = db.execute('SELECT * FROM cq_swot_analises WHERE id=?', (aid,)).fetchone()
    if a is None:
        raise ErroQualidade('Análise não encontrada.')
    itens = [dict(r) for r in db.execute('SELECT * FROM cq_swot_itens WHERE analise_id=? ORDER BY peso DESC, id', (aid,))]
    quad = {q: [i for i in itens if i['quadrante'] == q] for q, _ in QUADRANTES_SWOT}
    # cruzamentos (estratégias): o item de maior peso de cada quadrante combinado com o do outro
    def topo(q):
        return quad[q][0]['texto'] if quad[q] else None
    cruz = []
    for sigla, a1, a2, frase in (('FO', 'F', 'O', 'Usar a força "%s" para aproveitar a oportunidade "%s".'),
                                 ('FA', 'F', 'A', 'Usar a força "%s" para reduzir a ameaça "%s".'),
                                 ('DO', 'FR', 'O', 'Corrigir a fraqueza "%s" aproveitando a oportunidade "%s".'),
                                 ('DA', 'FR', 'A', 'Proteger-se: a fraqueza "%s" diante da ameaça "%s" pede plano de contingência.')):
        if topo(a1) and topo(a2):
            cruz.append({'sigla': sigla, 'texto': frase % (topo(a1), topo(a2))})
    return {'analise': dict(a), 'quadrantes': quad, 'cruzamentos': cruz,
            'saldo_interno': sum(i['peso'] for i in quad['F']) - sum(i['peso'] for i in quad['FR']),
            'saldo_externo': sum(i['peso'] for i in quad['O']) - sum(i['peso'] for i in quad['A'])}


def adicionar_swot_item(db, aid, form):
    swot(db, aid)
    q = _txt(form, 'quadrante', 3)
    if q not in dict(QUADRANTES_SWOT):
        raise ErroQualidade('Quadrante inválido.')
    db.execute('INSERT INTO cq_swot_itens (analise_id, quadrante, texto, peso) VALUES (?,?,?,?)',
               (aid, q, _txt(form, 'texto', 300, True, 'o item'), _nota(form, 'peso')))
    db.commit()


def excluir_swot_item(db, iid):
    r = db.execute('SELECT analise_id FROM cq_swot_itens WHERE id=?', (iid,)).fetchone()
    db.execute('DELETE FROM cq_swot_itens WHERE id=?', (iid,))
    db.commit()
    return r['analise_id'] if r else None


def excluir_swot(db, aid):
    db.execute('DELETE FROM cq_swot_itens WHERE analise_id=?', (aid,))
    db.execute('DELETE FROM cq_swot_analises WHERE id=?', (aid,))
    db.commit()


# ------------------------------------------------------------------ fluxogramas
FORMAS = ('inicio', 'processo', 'decisao', 'documento', 'dados', 'subprocesso', 'conector', 'espera')
STATUS_IMPLANTACAO = ('a_implantar', 'em_implantacao', 'implantado', 'revisao')
LIMITE_NOS = 400


def processos(db):
    saida = []
    for r in db.execute('SELECT id, nome, setor, versao, status, aprovado_por, aprovado_em, atualizado_por, atualizado_em, dados '
                        'FROM cq_processos ORDER BY nome COLLATE NOCASE'):
        x = dict(r)
        try:
            d = json.loads(x.pop('dados') or '{}')
        except ValueError:
            d = {}
        x['etapas'] = len(d.get('nos', []))
        saida.append(x)
    return saida


def processo(db, fid):
    r = db.execute('SELECT * FROM cq_processos WHERE id=?', (fid,)).fetchone()
    if r is None:
        raise ErroQualidade('Fluxograma não encontrado.')
    x = dict(r)
    try:
        x['dados_obj'] = json.loads(x['dados'] or '{}')
    except ValueError:
        x['dados_obj'] = {}
    return x


def _limpar_fluxo(bruto):
    """Valida o desenho enviado pelo editor: só os campos conhecidos, textos curtos e números finitos."""
    try:
        d = json.loads(bruto) if isinstance(bruto, str) else (bruto or {})
    except ValueError:
        raise ErroQualidade('Desenho inválido.')
    if not isinstance(d, dict):
        raise ErroQualidade('Desenho inválido.')

    def num(v, padrao=0.0):
        try:
            f = float(v)
        except (TypeError, ValueError):
            return padrao
        return max(-20000.0, min(20000.0, f)) if f == f else padrao

    def cor(v):
        v = str(v or '')
        return v if len(v) == 7 and v.startswith('#') and all(c in '0123456789abcdefABCDEF' for c in v[1:]) else ''

    nos = []
    ids = set()
    for n in (d.get('nos') or [])[:LIMITE_NOS]:
        if not isinstance(n, dict):
            continue
        nid = str(n.get('id') or '')[:20]
        if not nid or nid in ids:
            continue
        ids.add(nid)
        forma = n.get('forma') if n.get('forma') in FORMAS else 'processo'
        nos.append({'id': nid, 'forma': forma, 'texto': str(n.get('texto') or '')[:200], 'x': num(n.get('x')), 'y': num(n.get('y')),
                    'l': max(40.0, min(600.0, num(n.get('l'), 160))), 'a': max(30.0, min(400.0, num(n.get('a'), 60))),
                    'cor': cor(n.get('cor')), 'raia': str(n.get('raia') or '')[:20], 'responsavel': str(n.get('responsavel') or '')[:80],
                    'status': n.get('status') if n.get('status') in STATUS_IMPLANTACAO else '', 'obs': str(n.get('obs') or '')[:300]})
    ligacoes = []
    for e in (d.get('ligacoes') or [])[:LIMITE_NOS * 3]:
        if not isinstance(e, dict):
            continue
        de, para = str(e.get('de') or ''), str(e.get('para') or '')
        if de in ids and para in ids and de != para:
            ligacoes.append({'de': de, 'para': para, 'rotulo': str(e.get('rotulo') or '')[:40], 'cor': cor(e.get('cor'))})
    raias = []
    for i, r in enumerate((d.get('raias') or [])[:20]):
        if isinstance(r, dict):
            raias.append({'id': str(r.get('id') or 'r%d' % i)[:20], 'nome': str(r.get('nome') or '')[:60], 'cor': cor(r.get('cor'))})
    modo = d.get('modo_cor') if d.get('modo_cor') in ('tipo', 'raia', 'status', 'livre') else 'tipo'
    return {'nos': nos, 'ligacoes': ligacoes, 'raias': raias, 'modo_cor': modo}


def criar_processo(db, form, usuario, modelo=None):
    from . import qualidade_modelos
    dados = qualidade_modelos.fluxo(modelo) if modelo else {'nos': [], 'ligacoes': [], 'raias': [], 'modo_cor': 'tipo'}
    fid = db.execute('INSERT INTO cq_processos (nome, setor, objetivo, dados, criado_por, criado_em, atualizado_por, atualizado_em) '
                     'VALUES (?,?,?,?,?,?,?,?)',
                     (_txt(form, 'nome', 160, True, 'o nome do processo'), _txt(form, 'setor', 80), _txt(form, 'objetivo', 500),
                      json.dumps(_limpar_fluxo(dados), ensure_ascii=False), usuario, agora(), usuario, agora())).lastrowid
    db.commit()
    return fid


def salvar_processo(db, fid, form, usuario):
    atual = processo(db, fid)
    dados = _limpar_fluxo(form.get('dados') or '{}')
    nova_versao = atual['versao'] + 1 if atual['status'] == 'APROVADO' else atual['versao']
    db.execute('UPDATE cq_processos SET nome=?, setor=?, objetivo=?, dados=?, versao=?, status=?, atualizado_por=?, atualizado_em=? WHERE id=?',
               (_txt(form, 'nome', 160) or atual['nome'], _txt(form, 'setor', 80) if 'setor' in form else atual['setor'],
                _txt(form, 'objetivo', 500) if 'objetivo' in form else atual['objetivo'], json.dumps(dados, ensure_ascii=False),
                nova_versao, 'RASCUNHO' if atual['status'] == 'APROVADO' else atual['status'], usuario, agora(), fid))
    db.commit()
    return dados


def aprovar_processo(db, fid, usuario):
    processo(db, fid)
    db.execute("UPDATE cq_processos SET status='APROVADO', aprovado_por=?, aprovado_em=? WHERE id=?", (usuario, agora(), fid))
    db.commit()


def excluir_processo(db, fid):
    db.execute('DELETE FROM cq_processos WHERE id=?', (fid,))
    db.commit()


# ------------------------------------------------------------------ organograma
def organograma(db):
    nos = [dict(r) for r in db.execute('SELECT o.*, e.name AS funcionario FROM cq_organograma o LEFT JOIN bh_employees e '
                                       'ON e.id=o.funcionario_id ORDER BY o.ordem, o.id')]
    ids = {n['id'] for n in nos}
    for n in nos:
        if n['pai_id'] not in ids:
            n['pai_id'] = None
        if not n['pessoa'] and n.get('funcionario'):
            n['pessoa'] = n['funcionario']
    return nos


def salvar_no_org(db, form, nid=None):
    pai = form.get('pai_id') or None
    pai = int(pai) if pai and str(pai).isdigit() else None
    func = form.get('funcionario_id') or None
    func = int(func) if func and str(func).isdigit() else None
    if nid and pai:
        # impede ciclo: o novo chefe não pode estar abaixo deste cargo
        filhos = {nid}
        mudou = True
        todos = db.execute('SELECT id, pai_id FROM cq_organograma').fetchall()
        while mudou:
            mudou = False
            for r in todos:
                if r['pai_id'] in filhos and r['id'] not in filhos:
                    filhos.add(r['id'])
                    mudou = True
        if pai in filhos:
            raise ErroQualidade('O cargo superior não pode estar abaixo deste cargo.')
    cor = str(form.get('cor') or '')
    cor = cor if len(cor) == 7 and cor.startswith('#') else ''
    dados = (_txt(form, 'cargo', 120, True, 'o cargo'), _txt(form, 'pessoa', 120), _txt(form, 'setor', 80), pai, func, cor,
             int(form.get('ordem') or 0) if str(form.get('ordem') or '0').lstrip('-').isdigit() else 0)
    if nid:
        db.execute('UPDATE cq_organograma SET cargo=?, pessoa=?, setor=?, pai_id=?, funcionario_id=?, cor=?, ordem=? WHERE id=?', dados + (nid,))
    else:
        nid = db.execute('INSERT INTO cq_organograma (cargo, pessoa, setor, pai_id, funcionario_id, cor, ordem) VALUES (?,?,?,?,?,?,?)',
                         dados).lastrowid
    db.commit()
    return nid


def excluir_no_org(db, nid):
    r = db.execute('SELECT pai_id FROM cq_organograma WHERE id=?', (nid,)).fetchone()
    # os subordinados passam para o superior de quem saiu
    db.execute('UPDATE cq_organograma SET pai_id=? WHERE pai_id=?', (r['pai_id'] if r else None, nid))
    db.execute('DELETE FROM cq_organograma WHERE id=?', (nid,))
    db.commit()


# ------------------------------------------------------------------ ocorrências, pesquisa e motivos de falta
def ocorrencias(db, de=None, ate=None):
    sql, args = 'SELECT * FROM cq_ocorrencias WHERE 1=1', []
    if de:
        sql += ' AND data>=?'
        args.append(de)
    if ate:
        sql += ' AND data<=?'
        args.append(ate)
    return [dict(r) for r in db.execute(sql + ' ORDER BY data DESC, id DESC LIMIT 2000', args)]


def salvar_ocorrencia(db, form, usuario, oid=None):
    tipo = _txt(form, 'tipo', 60)
    if tipo not in TIPOS_OCORRENCIA:
        raise ErroQualidade('Escolha o tipo da ocorrência.')
    grav = _txt(form, 'gravidade', 20) or 'Leve'
    if grav not in GRAVIDADES:
        raise ErroQualidade('Gravidade inválida.')
    status = _txt(form, 'status', 20) or 'ABERTA'
    if status not in STATUS_OCORRENCIA:
        raise ErroQualidade('Situação inválida.')
    dados = (_data(form, 'data') or date.today().isoformat(), tipo, _txt(form, 'setor', 80), _txt(form, 'exame', 120),
             _txt(form, 'convenio', 120), _txt(form, 'descricao', 1500, True, 'a descrição'), grav, _txt(form, 'acao_imediata', 800), status)
    if oid:
        db.execute('UPDATE cq_ocorrencias SET data=?, tipo=?, setor=?, exame=?, convenio=?, descricao=?, gravidade=?, acao_imediata=?, status=?, '
                   'atualizado_em=? WHERE id=?', dados + (agora(), oid))
    else:
        oid = db.execute('INSERT INTO cq_ocorrencias (data, tipo, setor, exame, convenio, descricao, gravidade, acao_imediata, status, '
                         'criado_por, criado_em, atualizado_em) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)', dados + (usuario, agora(), agora())).lastrowid
    db.commit()
    return oid


def excluir_ocorrencia(db, oid):
    db.execute('DELETE FROM cq_ocorrencias WHERE id=?', (oid,))
    db.commit()


def abrir_problema_da_ocorrencia(db, oid, usuario):
    o = db.execute('SELECT * FROM cq_ocorrencias WHERE id=?', (oid,)).fetchone()
    if o is None:
        raise ErroQualidade('Ocorrência não encontrada.')
    if o['problema_id']:
        return o['problema_id']
    g = {'Leve': 2, 'Moderada': 4, 'Grave': 5}[o['gravidade']]
    pid = criar_problema(db, {'titulo': '%s: %s' % (o['tipo'], o['descricao'][:120]), 'descricao': o['descricao'],
                              'gut_g': g, 'gut_u': g, 'gut_t': 3}, usuario, origem='OCORRÊNCIA')
    db.execute("UPDATE cq_ocorrencias SET problema_id=?, status=CASE WHEN status='ABERTA' THEN 'EM TRATAMENTO' ELSE status END WHERE id=?",
               (pid, oid))
    db.commit()
    return pid


def registrar_pesquisa(db, form, usuario):
    db.execute('INSERT INTO cq_pesquisas (data, nota, exame, comentario, criado_por, criado_em) VALUES (?,?,?,?,?,?)',
               (_data(form, 'data') or date.today().isoformat(), _nota(form, 'nota', 0, 10, 10), _txt(form, 'exame', 120),
                _txt(form, 'comentario', 800), usuario, agora()))
    db.commit()


def registrar_motivo_falta(db, hid, motivo, usuario):
    if motivo not in MOTIVOS_FALTA:
        raise ErroQualidade('Escolha um motivo da lista.')
    if not db.execute("SELECT 1 FROM agenda_horarios WHERE id=? AND status='FALTOU'", (hid,)).fetchone():
        raise ErroQualidade('Este horário não está marcado como falta.')
    db.execute('INSERT INTO cq_falta_motivos (horario_id, motivo, registrado_por, registrado_em) VALUES (?,?,?,?) '
               'ON CONFLICT(horario_id) DO UPDATE SET motivo=excluded.motivo, registrado_por=excluded.registrado_por, '
               'registrado_em=excluded.registrado_em', (hid, motivo, usuario, agora()))
    db.commit()


# ------------------------------------------------------------------ metas dos indicadores
def metas(db):
    salvas = {r['chave']: (r['meta'], r['sentido']) for r in db.execute('SELECT chave, meta, sentido FROM cq_kpi_metas')}
    return {k: salvas.get(k, v) for k, v in METAS_PADRAO.items()}


def salvar_metas(db, form, usuario):
    for chave, (_meta, sentido) in METAS_PADRAO.items():
        bruto = str(form.get('meta_' + chave) or '').strip().replace(',', '.')
        if not bruto:
            continue
        try:
            valor = float(bruto)
        except ValueError:
            raise ErroQualidade('Meta inválida em %s.' % chave)
        db.execute('INSERT INTO cq_kpi_metas (chave, meta, sentido, atualizado_por, atualizado_em) VALUES (?,?,?,?,?) '
                   'ON CONFLICT(chave) DO UPDATE SET meta=excluded.meta, atualizado_por=excluded.atualizado_por, '
                   'atualizado_em=excluded.atualizado_em', (chave, valor, sentido, usuario, agora()))
    db.commit()


# ------------------------------------------------------------------ avaliação de fornecedores (ONA)
def criterios(db, so_ativos=True):
    sql = 'SELECT * FROM cq_forn_criterios' + (' WHERE ativo=1' if so_ativos else '') + ' ORDER BY ordem, id'
    return [dict(r) for r in db.execute(sql)]


def salvar_criterios(db, form):
    for c in criterios(db, False):
        k = str(c['id'])
        if form.get('nome_' + k) is None:
            continue
        db.execute('UPDATE cq_forn_criterios SET nome=?, descricao=?, peso=?, ativo=? WHERE id=?',
                   (_txt(form, 'nome_' + k, 120, True, 'o nome do critério'), _txt(form, 'descricao_' + k, 400),
                    _nota(form, 'peso_' + k, 1, 5, 1), 1 if form.get('ativo_' + k) else 0, c['id']))
    novo = _txt(form, 'novo_nome', 120)
    if novo:
        ordem = (db.execute('SELECT COALESCE(MAX(ordem),0)+1 FROM cq_forn_criterios').fetchone()[0])
        db.execute('INSERT INTO cq_forn_criterios (nome, descricao, peso, ordem) VALUES (?,?,?,?)',
                   (novo, _txt(form, 'novo_descricao', 400), _nota(form, 'novo_peso', 1, 5, 1), ordem))
    db.commit()


def classificar(percentual):
    for minimo, rotulo in CLASSES_FORNECEDOR:
        if percentual >= minimo:
            return rotulo
    return CLASSES_FORNECEDOR[-1][1]


def avaliar_fornecedor(db, fid, form, usuario):
    f = db.execute('SELECT id FROM fornecedores WHERE id=?', (fid,)).fetchone()
    if f is None:
        raise ErroQualidade('Fornecedor não encontrado.')
    lista = criterios(db)
    if not lista:
        raise ErroQualidade('Cadastre ao menos um critério de avaliação.')
    notas = []
    for c in lista:
        nota = _nota(form, 'nota_%d' % c['id'], 1, 5, 0) if form.get('nota_%d' % c['id']) not in (None, '') else None
        if nota is None:
            raise ErroQualidade('Dê uma nota de 1 a 5 para "%s".' % c['nome'])
        notas.append((c, nota, _txt(form, 'coment_%d' % c['id'], 300)))
    pontos = sum(c['peso'] * n for c, n, _ in notas)
    maximo = sum(c['peso'] * 5 for c, _, _ in notas)
    percentual = round(100.0 * pontos / maximo, 1)
    classe = classificar(percentual)
    if classe != 'APROVADO' and not _txt(form, 'acao', 1000):
        raise ErroQualidade('Fornecedor %s: descreva a ação (o que será cobrado ou feito) antes de gravar.' % classe.lower())
    data_av = _data(form, 'data') or date.today().isoformat()
    proxima = _data(form, 'proxima')
    if not proxima:
        meses = 6 if classe != 'APROVADO' else 12
        d = date.fromisoformat(data_av)
        m = d.month - 1 + meses
        ano, mes = d.year + m // 12, m % 12 + 1
        proxima = date(ano, mes, min(d.day, 28)).isoformat()
    aid = db.execute('INSERT INTO cq_forn_avaliacoes (fornecedor_id, data, periodo, avaliador, percentual, classificacao, critico, obs, acao, '
                     'proxima, criado_em) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                     (fid, data_av, _txt(form, 'periodo', 60), usuario, percentual, classe, 1 if form.get('critico') else 0,
                      _txt(form, 'obs', 1000), _txt(form, 'acao', 1000), proxima, agora())).lastrowid
    db.executemany('INSERT INTO cq_forn_notas (avaliacao_id, criterio_id, criterio, peso, nota, comentario) VALUES (?,?,?,?,?,?)',
                   [(aid, c['id'], c['nome'], c['peso'], n, com) for c, n, com in notas])
    db.commit()
    return aid


def avaliacao(db, aid):
    a = db.execute('SELECT a.*, f.nome AS fornecedor, f.cnpj FROM cq_forn_avaliacoes a JOIN fornecedores f ON f.id=a.fornecedor_id '
                   'WHERE a.id=?', (aid,)).fetchone()
    if a is None:
        raise ErroQualidade('Avaliação não encontrada.')
    x = dict(a)
    x['notas'] = [dict(r) for r in db.execute('SELECT * FROM cq_forn_notas WHERE avaliacao_id=? ORDER BY criterio_id', (aid,))]
    return x


def fornecedores_situacao(db):
    """Cada fornecedor ativo com a última avaliação, se está em dia e o movimento no contas a pagar (12 meses)."""
    hoje = date.today().isoformat()
    um_ano = date(date.today().year - 1, date.today().month, min(date.today().day, 28)).isoformat()
    saida = []
    for f in db.execute('SELECT id, nome, fantasia, cnpj FROM fornecedores WHERE ativo=1 ORDER BY nome COLLATE NOCASE'):
        ult = db.execute('SELECT * FROM cq_forn_avaliacoes WHERE fornecedor_id=? ORDER BY data DESC, id DESC LIMIT 1', (f['id'],)).fetchone()
        mov = db.execute("SELECT COUNT(*) AS n, COALESCE(SUM(valor),0) AS total, "
                         "SUM(CASE WHEN status='PAGO' AND data_pagamento IS NOT NULL AND vencimento IS NOT NULL AND data_pagamento>vencimento "
                         "THEN 1 ELSE 0 END) AS pagos_atrasados FROM contas WHERE fornecedor_id=? AND COALESCE(vencimento,'')>=?",
                         (f['id'], um_ano)).fetchone()
        situ = 'SEM AVALIAÇÃO'
        if ult:
            situ = 'VENCIDA' if (ult['proxima'] and ult['proxima'] < hoje) else 'EM DIA'
        saida.append({'id': f['id'], 'nome': f['nome'], 'fantasia': f['fantasia'], 'cnpj': f['cnpj'], 'ultima': dict(ult) if ult else None,
                      'situacao': situ, 'contas_12m': mov['n'], 'valor_12m': mov['total'] or 0})
    return saida


def avaliacoes_periodo(db, de, ate):
    return [dict(r) for r in db.execute(
        'SELECT a.*, f.nome AS fornecedor, f.cnpj FROM cq_forn_avaliacoes a JOIN fornecedores f ON f.id=a.fornecedor_id '
        'WHERE a.data BETWEEN ? AND ? ORDER BY a.data DESC, a.id DESC', (de, ate))]
