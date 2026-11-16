"""Avisos de vencimento dos documentos de fiscalização.

O sistema envia, pelo contato próprio "AVISOS DO SISTEMA", uma mensagem por fase: 60, 30, 15, 7, 1 e 0 dias antes
do vencimento, e uma quando o documento já venceu. Cada fase é enviada uma única vez por data de vencimento
(tabela docs_avisos). Quem recebe são os usuários da gerência (administradores e quem tem o módulo "gerencia").
"""
from __future__ import annotations

import os
import threading
import time
from datetime import date

from . import chat, modulos
from .db import SISTEMA_USUARIO, agora, conectar

FASES = (0, 1, 7, 15, 30, 60)   # dias restantes em que o aviso é enviado (o maior que cobre os dias faltantes)
VENCIDO = 'VENCIDO'


def fase(dias):
    """Fase em que o documento está, para os dias restantes. None = ainda longe do vencimento."""
    if dias < 0:
        return VENCIDO
    for limite in FASES:
        if dias <= limite:
            return str(limite)
    return None


def texto(nome, vencimento, dias, fase_atual):
    data = '%s/%s/%s' % (vencimento[8:10], vencimento[5:7], vencimento[:4])
    if fase_atual == VENCIDO:
        return 'Documento vencido: “%s” venceu em %s. Providencie a renovação.' % (nome, data)
    if dias == 0:
        return 'Aviso de vencimento: “%s” vence HOJE (%s).' % (nome, data)
    if dias == 1:
        return 'Aviso de vencimento: “%s” vence AMANHÃ (%s).' % (nome, data)
    return 'Aviso de vencimento: “%s” vence em %d dias (%s).' % (nome, dias, data)


def sistema_id(db):
    r = db.execute('SELECT id FROM usuarios WHERE sistema=1 AND usuario=?', (SISTEMA_USUARIO,)).fetchone()
    return r['id'] if r else None


def gerentes(db):
    """Usuários ativos da gerência (administradores e quem tem o módulo gerência)."""
    from . import suporte
    dev = suporte.usuario_dev_id(db)   # o desenvolvedor é administrador, mas não faz parte da gerência da clínica
    saida = []
    for u in db.execute('SELECT id, admin, modulos, bh_funcionario_id FROM usuarios WHERE ativo=1 AND COALESCE(sistema,0)=0'):
        if u['id'] != dev and 'gerencia' in modulos.modulos_do_usuario(u):
            saida.append(u['id'])
    return saida


def _brl(v):
    return 'R$ ' + '{:,.2f}'.format(v or 0).replace(',', 'X').replace('.', ',').replace('X', '.')


def destinatarios_contas(db):
    """Quem recebe o resumo das contas: usuários ativos com o módulo Contas a pagar (administradores incluídos), sem o desenvolvedor."""
    from . import suporte
    dev = suporte.usuario_dev_id(db)
    saida = []
    for u in db.execute('SELECT id, admin, modulos, bh_funcionario_id FROM usuarios WHERE ativo=1 AND COALESCE(sistema,0)=0 AND arquivado_em IS NULL'):
        if u['id'] != dev and 'contas' in modulos.modulos_do_usuario(u):
            saida.append(u['id'])
    return saida


def resumo_semanal_contas(db, hoje, de_sistema):
    """Toda segunda-feira, uma mensagem (pela aba Mensagens) com as contas em aberto que vencem nos próximos 7 dias. Uma vez por semana."""
    from datetime import timedelta
    if hoje.weekday() != 0:
        return 0
    chave = 'contas_resumo_semana'
    ja = db.execute('SELECT valor FROM config WHERE chave=?', (chave,)).fetchone()
    if ja and ja['valor'] == hoje.isoformat():
        return 0
    fim = hoje + timedelta(days=7)
    contas = db.execute("SELECT descricao, fornecedor, vencimento, valor FROM contas WHERE status='ABERTO' AND vencimento BETWEEN ? AND ? "
                        'ORDER BY vencimento, descricao', (hoje.isoformat(), fim.isoformat())).fetchall()
    periodo = '%s a %s' % (hoje.strftime('%d/%m'), fim.strftime('%d/%m'))
    if contas:
        linhas = ['• %s · %s%s · %s' % (c['vencimento'][8:10] + '/' + c['vencimento'][5:7], c['descricao'], (' (' + c['fornecedor'] + ')') if c['fornecedor'] else '', _brl(c['valor']))
                  for c in contas[:40]]
        if len(contas) > 40:
            linhas.append('… e mais %d conta(s).' % (len(contas) - 40))
        corpo = ('Resumo da semana: %d conta(s) vencem nos próximos 7 dias (%s).\n%s\nTotal: %s.' %
                 (len(contas), periodo, '\n'.join(linhas), _brl(sum(c['valor'] or 0 for c in contas))))
    else:
        corpo = 'Resumo da semana: nenhuma conta em aberto vence nos próximos 7 dias (%s).' % periodo
    n = 0
    for para in destinatarios_contas(db):
        db.execute('INSERT INTO chat_mensagens (de_id, para_id, corpo, criado_em) VALUES (?,?,?,?)', (de_sistema, para, corpo, agora()))
        n += 1
    db.execute('INSERT INTO config (chave, valor) VALUES (?,?) ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor', (chave, hoje.isoformat()))
    db.commit()
    return n


def verificar(db, hoje=None):
    """Envia os avisos que ainda não foram enviados. Devolve quantas mensagens foram gravadas."""
    hoje = hoje or date.today()
    # caixa aberto de outro dia: avisa o dono (o movimento de caixa tem a própria regra de um aviso por dia)
    from . import movimento
    movimento.alertar_caixas_abertos(db, hoje.isoformat())
    from . import enfermagem
    try:
        enfermagem.verificar_avisos(db, hoje)      # validades e testes da enfermagem: vão ao responsável de cada área
    except Exception:
        db.rollback()
    try:
        from . import contas_recorrentes
        contas_recorrentes.gerar(db, hoje)         # contas recorrentes: mês atual e seguinte, mesmo sem ninguém abrir a tela
    except Exception:
        db.rollback()
    try:
        from . import estoque
        estoque.verificar_alertas(db)              # estoque mínimo: uma mensagem à gerência por item (até repor)
        db.commit()
    except Exception:
        db.rollback()
    de_sistema = sistema_id(db)
    if de_sistema is None:
        return 0
    try:
        resumo_semanal_contas(db, hoje, de_sistema)     # segunda-feira: contas que vencem nos próximos 7 dias
    except Exception:
        db.rollback()
    destinos = gerentes(db)
    if not destinos:
        return 0
    docs = db.execute("SELECT id, nome, vencimento FROM arquivos_docs WHERE tipo='FISCALIZACAO' AND vencimento IS NOT NULL").fetchall()
    enviadas = 0
    for d in docs:
        dias = (date.fromisoformat(d['vencimento']) - hoje).days
        atual = fase(dias)
        if atual is None:
            continue
        ja = db.execute('SELECT 1 FROM docs_avisos WHERE documento_id=? AND vencimento=? AND fase=?',
                        (d['id'], d['vencimento'], atual)).fetchone()
        if ja:
            continue
        corpo = texto(d['nome'], d['vencimento'], dias, atual)
        for para in destinos:
            db.execute('INSERT INTO chat_mensagens (de_id, para_id, corpo, criado_em) VALUES (?,?,?,?)',
                       (de_sistema, para, corpo, agora()))
            enviadas += 1
        db.execute('INSERT INTO docs_avisos (documento_id, vencimento, fase, enviado_em) VALUES (?,?,?,?)',
                   (d['id'], d['vencimento'], atual, agora()))
    db.commit()
    return enviadas


PASSO_BACKUP = 60   # o laço acorda a cada 60 s para o backup automático (que tem janela e intervalo de minutos)


def iniciar(caminho_banco, intervalo=600):
    """Confere os avisos a cada 10 minutos, em segundo plano (o servidor não precisa de ninguém logado).
    Inclui o lembrete das 17h para fechar o caixa, que sai na primeira conferência depois das 17h.
    O backup automático e a cópia para a pasta externa são conferidos a cada minuto (ver PASSO_BACKUP)."""
    from datetime import datetime
    from . import movimento

    def laco():
        time.sleep(30)
        ultima = None   # quando as rotinas de `intervalo` segundos rodaram pela última vez
        while True:
            devido = ultima is None or time.monotonic() - ultima >= intervalo
            if devido:
                ultima = time.monotonic()
                try:
                    con = conectar(caminho_banco)
                    try:
                        verificar(con)
                        movimento.lembrar_fechamento(con, datetime.now())
                        from . import chat, laudos
                        chat.apagar_imagens_expiradas(con, datetime.now())  # imagens do chat: 24 h
                        from . import qualidade_robo
                        qualidade_robo.rotina_diaria(con)  # robô do PDCA: uma análise por dia (últimos 30 dias)
                        laudos.apagar_expiradas(con, datetime.now())  # mensagens de laudo liberado: 3 dias
                    finally:
                        con.close()
                except Exception:  # o aviso nunca pode derrubar o servidor; tenta de novo na próxima rodada
                    pass
            try:
                # backup automático (janela fixa e intervalo em minutos) e cópia para as pastas externas (Drive, rede): quem enxerga a pasta é que copia.
                # A cópia roda só quando saiu um backup novo, quando há automático substituído pendente, ou a cada `intervalo` (como antes).
                from . import backup_pacote, versao
                feito = backup_pacote.backup_automatico(caminho_banco, datetime.now(), versao())
                if feito or devido or backup_pacote.tem_substituidos_pendentes(caminho_banco):
                    backup_pacote.sincronizar_externa(caminho_banco, os.environ.get('USERNAME', ''))
            except Exception:  # idem: uma falha aqui não derruba o laço
                pass
            time.sleep(PASSO_BACKUP)
    threading.Thread(target=laco, name='avisos-vencimento', daemon=True).start()
