"""Protocolos operacionais padrão (POPs) da Qualidade: cadastro, versões, aprovação e aplicação dos modelos prontos."""
from __future__ import annotations

from datetime import date, timedelta

from . import qualidade_pops as pops
from .db import agora
from .qualidade import ErroQualidade, _data, _txt

CAMPOS_LISTA = ('definicoes', 'materiais', 'passos', 'registros', 'referencias', 'cuidados')
STATUS_POP = ('RASCUNHO', 'APROVADO')


def linhas(texto):
    return [x.strip() for x in str(texto or '').replace('\r', '').split('\n') if x.strip()]


def _unir(lista):
    return '\n'.join(str(x).strip() for x in lista if str(x).strip())


def protocolos(db):
    saida = []
    hoje = date.today().isoformat()
    for r in db.execute('SELECT id, codigo, titulo, setor, versao, status, aprovado_por, aprovado_em, proxima_revisao, modelo, atualizado_em '
                        'FROM cq_protocolos ORDER BY codigo, id'):
        x = dict(r)
        x['vencido'] = bool(x['status'] == 'APROVADO' and x['proxima_revisao'] and x['proxima_revisao'] < hoje)
        saida.append(x)
    return saida


def protocolo(db, pid):
    r = db.execute('SELECT * FROM cq_protocolos WHERE id=?', (pid,)).fetchone()
    if r is None:
        raise ErroQualidade('Protocolo não encontrado.')
    x = dict(r)
    for c in CAMPOS_LISTA:
        x[c + '_lista'] = linhas(x[c])
    return x


def proximo_codigo(db):
    maior = 0
    for r in db.execute('SELECT codigo FROM cq_protocolos'):
        resto = ''.join(ch for ch in str(r['codigo']).rsplit('-', 1)[-1] if ch.isdigit())
        if resto:
            maior = max(maior, int(resto))
    return 'POP-%03d' % (maior + 1)


def _dados(form, usuario, atual=None):
    atual = atual or {}
    dados = {'titulo': _txt(form, 'titulo', 200, True, 'o título do protocolo'),
             'codigo': _txt(form, 'codigo', 30) or atual.get('codigo') or '',
             'setor': _txt(form, 'setor', 120), 'objetivo': _txt(form, 'objetivo', 1000), 'abrangencia': _txt(form, 'abrangencia', 600),
             'responsaveis': _txt(form, 'responsaveis', 1200)}
    for c in CAMPOS_LISTA:
        dados[c] = _unir(linhas(_txt(form, c, 8000)))
    dados['fluxo_modelo'] = _txt(form, 'fluxo_modelo', 40)
    fid = str(form.get('fluxo_id') or '').strip()
    dados['fluxo_id'] = int(fid) if fid.isdigit() else None
    dados['elaborado_por'] = _txt(form, 'elaborado_por', 120) or atual.get('elaborado_por') or usuario
    dados['revisado_por'] = _txt(form, 'revisado_por', 120)
    dados['proxima_revisao'] = _data(form, 'proxima_revisao')
    return dados


def criar(db, form, usuario):
    d = _dados(form, usuario)
    if not d['codigo']:
        d['codigo'] = proximo_codigo(db)
    return _inserir(db, d, usuario, '')


def _inserir(db, d, usuario, modelo):
    colunas = ('codigo', 'titulo', 'setor', 'objetivo', 'abrangencia', 'responsaveis') + CAMPOS_LISTA + ('fluxo_modelo', 'fluxo_id', 'elaborado_por',
                                                                                                      'revisado_por', 'proxima_revisao')
    pid = db.execute('INSERT INTO cq_protocolos (%s, modelo, criado_por, criado_em, atualizado_por, atualizado_em) VALUES (%s)' %
                     (', '.join(colunas), ','.join('?' * (len(colunas) + 5))),
                     tuple(d.get(c) for c in colunas) + (modelo, usuario, agora(), usuario, agora())).lastrowid
    db.commit()
    return pid


def salvar(db, pid, form, usuario):
    atual = protocolo(db, pid)
    d = _dados(form, usuario, atual)
    nova_versao = atual['versao'] + 1 if atual['status'] == 'APROVADO' else atual['versao']
    colunas = ('codigo', 'titulo', 'setor', 'objetivo', 'abrangencia', 'responsaveis') + CAMPOS_LISTA + ('fluxo_modelo', 'fluxo_id', 'elaborado_por',
                                                                                                      'revisado_por', 'proxima_revisao')
    db.execute('UPDATE cq_protocolos SET %s, versao=?, status=?, aprovado_por=?, aprovado_em=?, atualizado_por=?, atualizado_em=? WHERE id=?' %
               ', '.join(c + '=?' for c in colunas),
               tuple(d.get(c) for c in colunas) + (nova_versao, 'RASCUNHO', None if atual['status'] == 'APROVADO' else atual['aprovado_por'],
                                                   None if atual['status'] == 'APROVADO' else atual['aprovado_em'], usuario, agora(), pid))
    db.commit()
    return nova_versao != atual['versao']


def aprovar(db, pid, form, usuario):
    protocolo(db, pid)
    quem = _txt(form, 'aprovado_por', 120) or usuario
    revisao = _data(form, 'proxima_revisao') or (date.today() + timedelta(days=365)).isoformat()
    db.execute("UPDATE cq_protocolos SET status='APROVADO', aprovado_por=?, aprovado_em=?, proxima_revisao=?, atualizado_por=?, atualizado_em=? WHERE id=?",
               (quem, agora(), revisao, usuario, agora(), pid))
    db.commit()


def excluir(db, pid):
    db.execute('DELETE FROM cq_protocolos WHERE id=?', (pid,))
    db.commit()


def aplicar_modelo(db, chave, usuario):
    """Cria o protocolo a partir do modelo. Devolve (id, criado): se o modelo já foi aplicado, devolve o que existe."""
    if chave not in pops.POPS:
        raise ErroQualidade('Modelo de protocolo desconhecido.')
    existente = db.execute('SELECT id FROM cq_protocolos WHERE modelo=? ORDER BY id LIMIT 1', (chave,)).fetchone()
    if existente:
        return existente['id'], False
    m = pops.POPS[chave]
    codigo = m['codigo']
    if db.execute('SELECT 1 FROM cq_protocolos WHERE codigo=?', (codigo,)).fetchone():
        codigo = proximo_codigo(db)
    d = {'codigo': codigo, 'titulo': m['titulo'], 'setor': m['setor'], 'objetivo': m['objetivo'], 'abrangencia': m['abrangencia'],
         'responsaveis': m['responsaveis'], 'fluxo_modelo': m['fluxo_modelo'], 'fluxo_id': None, 'elaborado_por': usuario, 'revisado_por': '',
         'proxima_revisao': None}
    for c in CAMPOS_LISTA:
        d[c] = _unir(m[c])
    return _inserir(db, d, usuario, chave), True


def aplicar_todos(db, usuario):
    novos = 0
    for chave in pops.POPS:
        if aplicar_modelo(db, chave, usuario)[1]:
            novos += 1
    return novos


def galeria(db):
    aplicados = {r['modelo']: r['id'] for r in db.execute("SELECT modelo, MIN(id) AS id FROM cq_protocolos WHERE modelo<>'' GROUP BY modelo")}
    return [{'chave': k, 'codigo': m['codigo'], 'titulo': m['titulo'], 'setor': m['setor'], 'objetivo': m['objetivo'], 'passos': len(m['passos']),
             'id': aplicados.get(k)} for k, m in pops.POPS.items()]
