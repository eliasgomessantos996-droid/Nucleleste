"""Presença: quem está online agora, em qualquer tela do sistema.

Cada aba aberta bate no servidor a cada BATIDA_S segundos. A pessoa conta como online enquanto tiver alguma aba
com batida recente (ONLINE_S); não há limite de inatividade, então quem deixa a aba aberta continua online. Ao fechar
a aba ou o navegador, ela avisa na hora (sendBeacon no pagehide). O logoff derruba todas as abas da pessoa. Quedas de
rede ou travamentos são cobertas pelo prazo de ONLINE_S.
"""
import re
import time
from datetime import date, timedelta

from .db import agora

BATIDA_S = 20   # intervalo da batida em cada aba (o navegador usa o mesmo valor, em chat.js)
ONLINE_S = 90   # sem batida por esse tempo, a aba deixa de contar (navegador em segundo plano pode atrasar a batida)
ABA_MAX = 40


def aba_valida(bruto):
    """Identificador da aba: só letras, números, _ e -, com no máximo ABA_MAX caracteres. None se vier vazio."""
    limpo = re.sub(r'[^A-Za-z0-9_-]', '', str(bruto or ''))[:ABA_MAX]
    return limpo or None


def bater(db, uid, aba):
    agora_ts = time.time()
    db.execute('INSERT INTO presenca (usuario_id, aba, visto) VALUES (?,?,?) '
               'ON CONFLICT(usuario_id, aba) DO UPDATE SET visto=excluded.visto', (uid, aba, agora_ts))
    db.execute('DELETE FROM presenca WHERE visto<?', (agora_ts - 3 * ONLINE_S,))  # limpeza de abas antigas
    db.commit()


def sair(db, uid, aba=None):
    """Tira a presença de uma aba (aba informada) ou de todas as abas da pessoa (sem aba: logoff/sessão encerrada)."""
    if aba:
        db.execute('DELETE FROM presenca WHERE usuario_id=? AND aba=?', (uid, aba))
    else:
        db.execute('DELETE FROM presenca WHERE usuario_id=?', (uid,))
    db.execute('UPDATE usuarios SET visto_em=? WHERE id=?', (agora(), uid))
    db.commit()


def quando(ts):
    """Frase para 'visto por último': 'às 14:32', 'ontem às 14:32' ou 'em 12/10 às 14:32'."""
    if not ts:
        return ''
    dia, hora = ts[:10], ts[11:16]
    hoje = date.today()
    if dia == hoje.isoformat():
        return 'às ' + hora
    if dia == (hoje - timedelta(days=1)).isoformat():
        return 'ontem às ' + hora
    return 'em %s/%s às %s' % (dia[8:10], dia[5:7], hora)


def situacao(db):
    """{id do usuário: {'online': bool, 'visto': frase}} para todos os usuários ativos."""
    limite = time.time() - ONLINE_S
    linhas = db.execute(
        'SELECT u.id, u.visto_em, (EXISTS(SELECT 1 FROM presenca p WHERE p.usuario_id=u.id AND p.visto>=?) '
        'OR COALESCE(u.sistema,0)=3) AS online '  # a NucleAI está sempre online
        'FROM usuarios u WHERE u.ativo=1', (limite,)).fetchall()
    return {r['id']: {'online': bool(r['online']), 'visto': quando(r['visto_em'])} for r in linhas}
