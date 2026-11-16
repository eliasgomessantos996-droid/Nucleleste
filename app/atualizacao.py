"""Aviso antes da atualização: a gestão dispara, pelo contato do sistema, um aviso com prazo para todos os usuários
salvarem o trabalho antes de o programa ser encerrado para instalar a nova versão.

O instalador (ou um script de atualização) consulta, pela rota local /atualizacao/pendente, se há aviso em andamento.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timedelta

from . import avisos
from .db import agora

PRAZO_PADRAO = 10   # minutos
PRAZO_MAX = 60


class ErroAtualizacao(ValueError):
    """Erro de validação mostrado ao usuário."""


def disparar(db, usuario, prazo_min=PRAZO_PADRAO, agora_dt=None):
    try:
        prazo = int(prazo_min)
    except (TypeError, ValueError):
        raise ErroAtualizacao('Informe o prazo em minutos.') from None
    if not 1 <= prazo <= PRAZO_MAX:
        raise ErroAtualizacao('O prazo deve ficar entre 1 e %d minutos.' % PRAZO_MAX)
    inicio = agora_dt or datetime.now()
    ate = inicio + timedelta(minutes=prazo)
    de = avisos.sistema_id(db)
    if de is None:
        raise ErroAtualizacao('O contato do sistema não está disponível. Reinicie o programa.')
    corpo = ('Aviso de atualização: o sistema será atualizado às %s (em %d minutos). Salve o seu trabalho agora e '
             'feche o que estiver aberto. O programa será encerrado nesse horário e voltará logo em seguida.'
             % (ate.strftime('%H:%M'), prazo))
    destinos = [r['id'] for r in db.execute('SELECT id FROM usuarios WHERE ativo=1 AND COALESCE(sistema,0)=0')]
    for uid in destinos:
        db.execute("INSERT INTO chat_mensagens (de_id, para_id, corpo, criado_em, tipo) VALUES (?,?,?,?,'ATUALIZACAO')",
                   (de, uid, corpo, agora()))
    cur = db.execute('INSERT INTO atualizacao_avisos (criado_em, criado_por, prazo_min, ate, destinatarios) VALUES (?,?,?,?,?)',
                     (agora(), usuario, prazo, ate.strftime('%Y-%m-%d %H:%M:%S'), len(destinos)))
    db.commit()
    return {'id': cur.lastrowid, 'ate': ate.strftime('%H:%M'), 'destinatarios': len(destinos)}


PRAZO_INSTALADOR = 3   # minutos de aviso quando o instalador de uma atualização é aberto no computador-base
ESPERA_S = 60          # depois da atualização, quem acessar vê a tela de espera por este tempo
MARCA = 'atualizando.txt'
MARCA_VALIDADE_S = 900  # marca esquecida por uma instalação interrompida deixa de valer


def iniciar_pelo_instalador(db, agora_dt=None):
    """Chamado pelo instalador: dispara o aviso de 3 minutos (ou aproveita um aviso já em andamento).
    Devolve quantos segundos o instalador deve esperar antes de encerrar o sistema."""
    agora_dt = agora_dt or datetime.now()
    aviso = pendente(db, agora_dt)
    if not aviso:
        disparar(db, 'INSTALADOR', PRAZO_INSTALADOR, agora_dt)
        aviso = pendente(db, agora_dt)
    ate = datetime.strptime(aviso['ate'], '%Y-%m-%d %H:%M:%S')
    return max(0, int((ate - agora_dt).total_seconds()) + 1)


def estado_aviso(db, agora_dt=None):
    """Segundos que faltam para a atualização anunciada (0 se não há aviso)."""
    agora_dt = agora_dt or datetime.now()
    aviso = pendente(db, agora_dt)
    if not aviso:
        return 0
    return max(0, int((datetime.strptime(aviso['ate'], '%Y-%m-%d %H:%M:%S') - agora_dt).total_seconds()))


def marcar_atualizacao(pasta):
    """O instalador faz isto antes de encerrar o programa; o servidor novo mostra a tela de espera ao iniciar."""
    with open(os.path.join(pasta, MARCA), 'w', encoding='utf-8') as fh:
        fh.write(str(time.time()))


def espera_restante(pasta, inicio_servidor, agora=None):
    """Segundos de tela de espera que ainda restam depois de uma atualização (0 = sistema liberado)."""
    caminho = os.path.join(pasta, MARCA)
    if not os.path.exists(caminho):
        return 0
    agora = agora if agora is not None else time.time()
    try:
        marca = os.path.getmtime(caminho)
    except OSError:
        return 0
    restante = ESPERA_S - (agora - inicio_servidor)
    if inicio_servidor < marca or restante <= 0 or agora - marca > MARCA_VALIDADE_S:
        try:  # servidor anterior à marca (instalação cancelada), tempo esgotado ou marca velha: libera
            os.remove(caminho)
        except OSError:
            pass
        return 0
    return int(restante) + 1


def pendente(db, agora_dt=None):
    """Aviso de atualização ainda no prazo (ou None). Usado pelo instalador e pelo script de atualização."""
    agora_dt = agora_dt or datetime.now()
    r = db.execute('SELECT * FROM atualizacao_avisos WHERE ate>? ORDER BY id DESC LIMIT 1',
                   (agora_dt.strftime('%Y-%m-%d %H:%M:%S'),)).fetchone()
    return dict(r) if r else None
