"""Mapa de laudos: acompanha após o atendimento a situação de cada exame realizado.

Situações: Processando imagem -> Laudando -> Liberado para entrega.
Ao liberar, o LAUDOS DO SISTEMA avisa todos os funcionários (nome do paciente, data e hora do exame, tipo do exame).
Essa mensagem se apaga sozinha depois de DIAS_MENSAGEM dias.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

from . import util
from .db import agora

SITUACOES = (('PROCESSANDO', 'Processando imagem'), ('LAUDANDO', 'Laudando'), ('LIBERADO', 'Liberado para entrega'),
             ('ENTREGUE', 'Entregue'))
ROTULOS = dict(SITUACOES)
SISTEMA_USUARIO = 'LAUDOS DO SISTEMA'
DIAS_MENSAGEM = 3


class ErroLaudo(ValueError):
    """Erro de validação mostrado ao usuário."""


def sistema_id(db):
    r = db.execute('SELECT id FROM usuarios WHERE sistema=2 AND usuario=?', (SISTEMA_USUARIO,)).fetchone()
    return r['id'] if r else None


CHAVES = [c for c, _ in SITUACOES]


def proxima(chave):
    """Situação seguinte à informada (None na última)."""
    i = CHAVES.index(chave)
    return CHAVES[i + 1] if i + 1 < len(CHAVES) else None


def permissoes(usuario, modulos=()):
    """None = acesso completo (administração, gerência ou usuário sem restrição definida).
    Senão {'ver': set, 'mover': set}: situações que enxerga e situações de onde pode passar para a próxima etapa."""
    if usuario is None or usuario['admin'] or 'gerencia' in modulos:
        return None
    try:
        bruto = json.loads(usuario['laudo_perm'] or 'null')
    except (ValueError, KeyError, IndexError):
        bruto = None
    if not isinstance(bruto, dict):
        return None
    mover = {c for c in bruto.get('mover', []) if c in CHAVES and proxima(c)}
    ver = {c for c in bruto.get('ver', []) if c in CHAVES} | mover
    return {'ver': ver, 'mover': mover}


def pode_mudar(perm, antes, nova):
    """Restrito: só avança uma etapa a partir de uma situação liberada. Também vale corrigir a data na mesma situação."""
    if perm is None:
        return True
    if antes == nova:
        return antes in perm['ver']
    return antes in perm['mover'] and proxima(antes) == nova


def perm_do_form(form):
    """JSON gravado no usuário a partir do formulário do perfil (None = acesso completo)."""
    if form.get('laudo_acesso') != 'restrito':
        return None
    mover = [c for c in CHAVES if form.get('mover_' + c) and proxima(c)]
    ver = [c for c in CHAVES if form.get('ver_' + c) or c in mover]
    return json.dumps({'ver': ver, 'mover': mover})


def quadro(db, de, ate):
    """Exames do período com laudo acompanhado, agrupados por situação (exames antigos, sem acompanhamento, não entram)."""
    linhas = db.execute("SELECT id, data, numero, codigo, paciente, convenio, medico, exame, hora_exame, laudo_situacao, "
                        "laudo_atualizado_em, laudo_liberado_em, laudo_liberado_por, laudo_entregue_em, laudo_entregue_por, "
                        "laudo_retificado_em, laudo_retificado_motivo "
                        "FROM realizacoes "
                        "WHERE laudo_situacao IS NOT NULL AND laudo_arquivado_em IS NULL AND data BETWEEN ? AND ? "
                        "ORDER BY data, COALESCE(hora_exame,''), id", (de, ate)).fetchall()
    colunas = {chave: [] for chave, _ in SITUACOES}
    for r in linhas:
        colunas.setdefault(r['laudo_situacao'], []).append(dict(r))
    return {'colunas': [(chave, rotulo, colunas[chave]) for chave, rotulo in SITUACOES], 'total': len(linhas)}


def mensagem_liberado(r):
    data = util.data_br(r['data'])
    hora = r['hora_exame'] or '—'
    partes = ['Laudo liberado para entrega: %s.' % r['paciente'],
              'Exame: %s, realizado em %s às %s.' % (r['exame'] or '—', data, hora)]
    if r['convenio']:
        partes.append('Convênio: %s.' % r['convenio'])
    if r['medico']:
        partes.append('Médico solicitante: %s.' % r['medico'])
    if r['codigo']:
        partes.append('Código: %s.' % r['codigo'])
    partes.append('Ao entregar ao paciente, use o botão abaixo para marcar como entregue.')
    return ' '.join(partes)


def mudar(db, rid, nova, usuario, agora_dt=None, liberado_em_informado=None, perm=None):
    if nova not in ROTULOS:
        raise ErroLaudo('Situação inválida.')
    r = db.execute('SELECT * FROM realizacoes WHERE id=?', (rid,)).fetchone()
    if not r:
        raise ErroLaudo('Este exame não existe mais. Atualize a página.')
    if r['laudo_situacao'] is None:
        raise ErroLaudo('Este exame não está no mapa de laudos (foi lançado antes do acompanhamento).')
    agora_s = agora()
    antes = r['laudo_situacao']
    if not pode_mudar(perm, antes, nova):
        raise ErroLaudo('Seu perfil não permite esta mudança de situação.')
    liberado_antes = antes in ('LIBERADO', 'ENTREGUE')
    liberado_em, liberado_por = r['laudo_liberado_em'], r['laudo_liberado_por']
    entregue_em, entregue_por = r['laudo_entregue_em'], r['laudo_entregue_por']
    avisar = False
    if nova in ('LIBERADO', 'ENTREGUE'):
        if liberado_em_informado:   # data real da liberação, informada por quem esqueceu de marcar na hora
            liberado_em = _validar_liberacao(liberado_em_informado, r, agora_s)
            if liberado_antes:
                liberado_por = liberado_por or usuario
        if not liberado_antes:  # primeira liberação (a entrega direta também conta como liberação)
            liberado_em, liberado_por = liberado_em or agora_s, usuario
            avisar = nova == 'LIBERADO'
        if nova == 'ENTREGUE' and antes != 'ENTREGUE':
            entregue_em, entregue_por = agora_s, usuario
        elif nova == 'LIBERADO':
            entregue_em = entregue_por = None
    else:  # voltou para uma etapa anterior à liberação
        liberado_em = liberado_por = entregue_em = entregue_por = None
    if nova != 'ENTREGUE':   # voltou de "Entregue": sai do arquivo de entregues
        db.execute('UPDATE realizacoes SET laudo_arquivado_em=NULL, laudo_arquivado_por=NULL WHERE id=?', (rid,))
    db.execute('UPDATE realizacoes SET laudo_situacao=?, laudo_atualizado_em=?, laudo_liberado_em=?, laudo_liberado_por=?, '
               'laudo_entregue_em=?, laudo_entregue_por=? WHERE id=?',
               (nova, agora_s, liberado_em, liberado_por, entregue_em, entregue_por, rid))
    if avisar:
        avisar_liberacao(db, dict(r), agora_dt)
    db.commit()
    return ROTULOS[nova]


def _validar_liberacao(texto, r, agora_s):
    """Aceita 'AAAA-MM-DDTHH:MM' ou 'AAAA-MM-DD HH:MM[:SS]'; não pode ser futura nem anterior ao dia do exame."""
    try:
        dt = datetime.fromisoformat(texto.strip().replace('T', ' ')[:19])
    except ValueError:
        raise ErroLaudo('Data de liberação inválida.') from None
    if dt > datetime.fromisoformat(agora_s[:19]) + timedelta(minutes=1):
        raise ErroLaudo('A data de liberação não pode ser no futuro.')
    if r['data'] and dt.date().isoformat() < r['data']:
        raise ErroLaudo('A data de liberação não pode ser anterior ao dia do exame.')
    return dt.strftime('%Y-%m-%d %H:%M:%S')


def entregar(db, rid, usuario, perm=None):
    """Marca como entregue (botão da mensagem de aviso). Devolve (texto, data do exame) para a tela do mapa."""
    r = db.execute('SELECT laudo_situacao, data, paciente FROM realizacoes WHERE id=?', (rid,)).fetchone()
    if not r:
        raise ErroLaudo('Este exame não existe mais.')
    if r['laudo_situacao'] == 'ENTREGUE':
        return 'O laudo de %s já estava marcado como entregue.' % r['paciente'], r['data']
    mudar(db, rid, 'ENTREGUE', usuario, perm=perm)
    return 'Laudo de %s marcado como entregue.' % r['paciente'], r['data']


def avisar_liberacao(db, r, agora_dt=None):
    """Mensagem de liberação para todos os funcionários; apaga-se sozinha depois de DIAS_MENSAGEM dias."""
    de = sistema_id(db)
    if de is None:
        return 0
    inicio = agora_dt or datetime.now()
    expira = (inicio + timedelta(days=DIAS_MENSAGEM)).strftime('%Y-%m-%d %H:%M:%S')
    corpo = mensagem_liberado(r)
    destinos = [x['id'] for x in db.execute('SELECT id FROM usuarios WHERE ativo=1 AND COALESCE(sistema,0)=0')]
    for uid in destinos:
        db.execute('INSERT INTO chat_mensagens (de_id, para_id, corpo, criado_em, expira_em, laudo_id) VALUES (?,?,?,?,?,?)',
                   (de, uid, corpo, agora(), expira, r['id']))
    return len(destinos)


def apagar_expiradas(db, agora_dt=None):
    """Remove as mensagens do sistema cujo prazo de 3 dias passou. Devolve quantas foram apagadas."""
    limite = (agora_dt or datetime.now()).strftime('%Y-%m-%d %H:%M:%S')
    # mensagens com imagem são tratadas por chat.apagar_imagens_expiradas (apaga a imagem e mantém o texto)
    cur = db.execute("DELETE FROM chat_mensagens WHERE expira_em IS NOT NULL AND expira_em<>'' AND expira_em<? AND anexo_tipo IS NULL",
                     (limite,))
    db.commit()
    return cur.rowcount


# ------------------------------------------------------------------ laudos entregues: limpar o mapa e retificação
def arquivar_entregues(db, de, ate, usuario):
    """Tira do mapa os laudos entregues do período (continuam na página Laudos entregues). Devolve quantos."""
    cur = db.execute("UPDATE realizacoes SET laudo_arquivado_em=?, laudo_arquivado_por=? WHERE laudo_situacao='ENTREGUE' "
                     "AND laudo_arquivado_em IS NULL AND data BETWEEN ? AND ?", (agora(), usuario, de, ate))
    db.commit()
    return cur.rowcount


def entregues(db, de, ate, busca=''):
    onde, params = ["laudo_situacao='ENTREGUE'", 'data BETWEEN ? AND ?'], [de, ate]
    if busca.strip():
        onde.append('UPPER(paciente) LIKE ?')
        params.append('%' + busca.strip().upper() + '%')
    sql = ("SELECT id, data, hora_exame, paciente, exame, convenio, medico, codigo, laudo_liberado_em, laudo_entregue_em, "
           "laudo_entregue_por, laudo_arquivado_em, laudo_retificado_em, laudo_retificado_por, laudo_retificado_motivo "
           "FROM realizacoes WHERE %s ORDER BY data DESC, COALESCE(hora_exame,'') DESC, id DESC LIMIT 1500")
    return [dict(r) for r in db.execute(sql % ' AND '.join(onde), params)]


def retificar(db, rid, motivo, usuario):
    """Marca o laudo entregue como retificado (corrigido). Entra no indicador de retificação da ONA."""
    r = db.execute('SELECT laudo_situacao, paciente FROM realizacoes WHERE id=?', (rid,)).fetchone()
    if not r:
        raise ErroLaudo('Este exame não existe mais.')
    if r['laudo_situacao'] != 'ENTREGUE':
        raise ErroLaudo('Só laudos entregues podem ser marcados como retificados.')
    motivo = (motivo or '').strip()[:300]
    db.execute('UPDATE realizacoes SET laudo_retificado_em=?, laudo_retificado_por=?, laudo_retificado_motivo=? WHERE id=?',
               (agora(), usuario, motivo or None, rid))
    db.commit()
    return r['paciente']


def desfazer_retificacao(db, rid):
    db.execute('UPDATE realizacoes SET laudo_retificado_em=NULL, laudo_retificado_por=NULL, laudo_retificado_motivo=NULL WHERE id=?', (rid,))
    db.commit()
