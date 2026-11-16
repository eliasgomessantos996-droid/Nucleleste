"""Aplicação dos modelos prontos da Qualidade: cada função cria os registros no sistema a partir de `qualidade_catalogo*` e devolve o
que precisa para abrir a tela. Nada é aplicado sem o clique do usuário, e repetir o clique não duplica o que já existe."""
from __future__ import annotations

import json
from datetime import date, timedelta

from . import pesquisa as pesq
from . import qualidade as q
from . import qualidade_catalogo as cat
from . import qualidade_catalogo_outros as cat2
from .db import agora

ABERTOS = ('RASCUNHO', 'ABERTO', 'EM ANDAMENTO')


def _prazo(dias):
    return (date.today() + timedelta(days=int(dias))).isoformat()


# ------------------------------------------------------------------ problemas (PDCA + Ishikawa + 5 porquês + GUT + 5W2H)
def galeria_problemas():
    return [{'chave': k, 'titulo': m['titulo'], 'area': m['area'], 'gut': m['gut'][0] * m['gut'][1] * m['gut'][2], 'acoes': len(m['acoes']),
             'causas': sum(len(v) for v in m['causas'].values()), 'descricao': m['descricao']} for k, m in cat.PROBLEMAS.items()]


def aplicar_problema(db, chave, usuario):
    """Abre o problema com causas (Ishikawa), cinco porquês, GUT, meta, padronização e plano 5W2H. Devolve (id, criado)."""
    if chave not in cat.PROBLEMAS:
        raise q.ErroQualidade('Modelo desconhecido.')
    m = cat.PROBLEMAS[chave]
    r = db.execute("SELECT id FROM cq_problemas WHERE titulo=? AND origem='MODELO' AND status IN ('RASCUNHO','ABERTO','EM ANDAMENTO') ORDER BY id LIMIT 1",
                   (m['titulo'],)).fetchone()
    if r:
        return r['id'], False
    g, u, t = m['gut']
    pid = q.criar_problema(db, {'titulo': m['titulo'], 'descricao': m['descricao'], 'gut_g': g, 'gut_u': u, 'gut_t': t, 'plan_meta': m['meta'],
                                'plan_causa': m['causa_raiz'], 'plan_indicador': '', 'act_padrao': m['padrao'], 'responsavel': ''}, usuario, origem='MODELO')
    for categoria, textos in m['causas'].items():
        for i, texto in enumerate(textos):
            db.execute('INSERT INTO cq_causas (problema_id, categoria, texto, principal, criado_em) VALUES (?,?,?,?,?)',
                       (pid, categoria, texto, 1 if i == 0 and categoria == 'Método' else 0, agora()))
    for n, texto in enumerate(m['porques'], 1):
        db.execute('INSERT INTO cq_porques (problema_id, nivel, resposta) VALUES (?,?,?)', (pid, n, texto))
    for o_que, por_que, onde, quem, como, prazo in m['acoes']:
        db.execute('INSERT INTO cq_acoes (problema_id, o_que, por_que, onde, quando, quem, como, status, criado_por, criado_em, atualizado_em) '
                   'VALUES (?,?,?,?,?,?,?,?,?,?,?)', (pid, o_que, por_que, onde, _prazo(prazo), quem, como, 'A FAZER', usuario, agora(), agora()))
    db.commit()
    return pid, True


# ------------------------------------------------------------------ planos 5W2H
def galeria_planos():
    return [{'chave': k, 'titulo': m['titulo'], 'area': m['area'], 'descricao': m['descricao'], 'acoes': len(m['acoes'])} for k, m in cat2.PLANOS.items()]


def aplicar_plano(db, chave, usuario, problema_id=None):
    """Inclui as ações do plano (sem repetir as que já existem). Devolve quantas foram incluídas."""
    if chave not in cat2.PLANOS:
        raise q.ErroQualidade('Modelo desconhecido.')
    if problema_id:
        q.problema(db, problema_id)
    novas = 0
    for o_que, por_que, onde, quem, como, prazo in cat2.PLANOS[chave]['acoes']:
        if db.execute('SELECT 1 FROM cq_acoes WHERE o_que=? AND COALESCE(problema_id,0)=?', (o_que, problema_id or 0)).fetchone():
            continue
        db.execute('INSERT INTO cq_acoes (problema_id, o_que, por_que, onde, quando, quem, como, status, criado_por, criado_em, atualizado_em) '
                   'VALUES (?,?,?,?,?,?,?,?,?,?,?)', (problema_id or None, o_que, por_que, onde, _prazo(prazo), quem, como, 'A FAZER', usuario, agora(), agora()))
        novas += 1
    db.commit()
    return novas


# ------------------------------------------------------------------ matriz de risco
def galeria_riscos():
    return [{'chave': k, 'titulo': m['titulo'], 'descricao': m['descricao'], 'itens': len(m['itens'])} for k, m in cat2.RISCOS.items()]


def aplicar_riscos(db, chave, usuario):
    if chave not in cat2.RISCOS:
        raise q.ErroQualidade('Modelo desconhecido.')
    novos = 0
    for titulo, processo, causa, consequencia, prob, imp, resposta, acao, prazo in cat2.RISCOS[chave]['itens']:
        if db.execute('SELECT 1 FROM cq_riscos WHERE titulo=?', (titulo,)).fetchone():
            continue
        q.salvar_risco(db, {'titulo': titulo, 'processo': processo, 'causa': causa, 'consequencia': consequencia, 'probabilidade': prob, 'impacto': imp,
                            'resposta': resposta, 'acao': acao, 'prazo': _prazo(prazo)}, usuario)
        novos += 1
    return novos


# ------------------------------------------------------------------ SWOT
def galeria_swot():
    return [{'chave': k, 'titulo': m['titulo'], 'descricao': m['descricao'], 'itens': sum(len(v) for v in m['itens'].values())} for k, m in cat2.SWOT.items()]


def aplicar_swot(db, chave, usuario):
    if chave not in cat2.SWOT:
        raise q.ErroQualidade('Modelo desconhecido.')
    m = cat2.SWOT[chave]
    aid = q.criar_swot(db, {'titulo': m['titulo'], 'obs': m['descricao'] + ' Revise os itens e os pesos com a equipe antes de usar.'}, usuario)
    for quadrante, itens in m['itens'].items():
        for texto, peso in itens:
            db.execute('INSERT INTO cq_swot_itens (analise_id, quadrante, texto, peso) VALUES (?,?,?,?)', (aid, quadrante, texto, peso))
    db.commit()
    return aid


# ------------------------------------------------------------------ organograma
def galeria_organogramas():
    return [{'chave': k, 'titulo': m['titulo'], 'descricao': m['descricao'], 'cargos': len(m['nos'])} for k, m in cat2.ORGANOGRAMAS.items()]


def aplicar_organograma(db, chave, substituir=False):
    if chave not in cat2.ORGANOGRAMAS:
        raise q.ErroQualidade('Modelo desconhecido.')
    if db.execute('SELECT 1 FROM cq_organograma LIMIT 1').fetchone():
        if not substituir:
            raise q.ErroQualidade('Já existe um organograma. Marque "substituir o organograma atual" para trocar pelo modelo.')
        db.execute('DELETE FROM cq_organograma')
    ids = {}
    for ordem, (nid, cargo, setor, pai, cor) in enumerate(cat2.ORGANOGRAMAS[chave]['nos']):
        ids[nid] = db.execute('INSERT INTO cq_organograma (cargo, pessoa, setor, pai_id, cor, ordem) VALUES (?,?,?,?,?,?)',
                              (cargo, '', setor, ids.get(pai), cor, ordem)).lastrowid
    db.commit()
    return len(ids)


# ------------------------------------------------------------------ fornecedores
def galeria_criterios():
    return [{'chave': k, 'titulo': m['titulo'], 'descricao': m['descricao'], 'criterios': len(m['criterios'])} for k, m in cat2.CRITERIOS.items()]


def aplicar_criterios(db, chave, substituir=False):
    if chave not in cat2.CRITERIOS:
        raise q.ErroQualidade('Modelo desconhecido.')
    if substituir:
        db.execute('UPDATE cq_forn_criterios SET ativo=0')
    existentes = {r['nome']: r['id'] for r in db.execute('SELECT id, nome FROM cq_forn_criterios')}
    ordem = db.execute('SELECT COALESCE(MAX(ordem),0)+1 FROM cq_forn_criterios').fetchone()[0]
    novos = 0
    for nome, descricao, peso in cat2.CRITERIOS[chave]['criterios']:
        if nome in existentes:
            db.execute('UPDATE cq_forn_criterios SET ativo=1, descricao=?, peso=? WHERE id=?', (descricao, peso, existentes[nome]))
            continue
        db.execute('INSERT INTO cq_forn_criterios (nome, descricao, peso, ordem) VALUES (?,?,?,?)', (nome, descricao, peso, ordem))
        ordem += 1
        novos += 1
    db.commit()
    return novos


# ------------------------------------------------------------------ pesquisa de satisfação
def galeria_perguntas():
    return [{'chave': k, 'titulo': m['titulo'], 'descricao': m['descricao'], 'perguntas': m['perguntas']} for k, m in cat2.PERGUNTAS.items()]


def aplicar_perguntas(db, chave):
    if chave not in cat2.PERGUNTAS:
        raise q.ErroQualidade('Modelo desconhecido.')
    pesq.salvar_perguntas(db, cat2.PERGUNTAS[chave]['perguntas'])


# ------------------------------------------------------------------ ocorrências (preenchem o formulário no navegador)
def modelos_ocorrencia():
    return [{'nome': n, 'tipo': t, 'gravidade': g, 'setor': s, 'descricao': d, 'acao': a} for n, t, g, s, d, a in cat2.OCORRENCIAS]


def modelos_ocorrencia_json():
    return json.dumps(modelos_ocorrencia(), ensure_ascii=False)
