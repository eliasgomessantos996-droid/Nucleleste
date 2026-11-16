"""Agenda de exames: um calendário, e em cada dia uma agenda por exame com linhas de horário (como uma planilha).

É independente do cadastro de clientes: a agenda guarda o nome e o contato digitados, sem vínculo com outros módulos.
Linha sem paciente = horário livre. Status: AGENDADO, VEIO, FALTOU, RETORNO (retorno marcado para outro dia, ex.: 2ª etapa do MIBI), RESGATADO, DESISTIU.
"""
from __future__ import annotations

import calendar
import logging
import re
import unicodedata
from datetime import date, timedelta

from flask import g, has_request_context

from . import util
from .db import agora

STATUS = ('AGENDADO', 'VEIO', 'FALTOU', 'RETORNO', 'RESGATADO', 'DESISTIU')
ROTULOS = {'AGENDADO': 'Agendado', 'VEIO': 'Veio', 'FALTOU': 'Faltou', 'RETORNO': 'Retorno',
           'RESGATADO': 'Reagendado', 'DESISTIU': 'Desistiu'}
# resgate de quem faltou: reagendado (voltou em outro dia) ou desistiu. Guarda quem resgatou e quando.
RESGATES = ('RESGATADO', 'DESISTIU')
# campos editáveis na grade e o tamanho máximo de cada um
CAMPOS = {'hora': 5, 'paciente': 120, 'convenio': 60, 'contato': 80, 'senha': 40, 'observacao': 300, 'idade': 3}
MAX_QTD = 200          # horários por agenda na criação
MAX_LINHAS = 600       # linhas por agenda (criação + acréscimos)
MAX_VAGAS = 10         # pacientes simultâneos por horário
MAX_SEMANAS = 26       # repetições semanais
OBSERVACAO_MAX = 200   # lembrete que aparece em vermelho ao lado da data
# no exame MIBI, o campo "senha" (autorização) é uma escolha; Protocolo pinta a linha de verde (se ainda agendado)
SENHAS_MIBI = ('Estresse', 'Repouso', 'Protocolo')


def mesmo_convenio(a, b):
    return bool((a or '').strip()) and (a or '').strip().casefold() == (b or '').strip().casefold()


def msg_reserva(convenio):
    return 'Este horário está reservado para o convênio %s.' % (convenio or '')


MSG_SEM_RESERVA = ('Esta agenda não tem reserva para convênio. Ao criar a agenda, abra a aba “Reservar horários para um convênio”.')


class ErroAgenda(ValueError):
    """Erro de validação mostrado ao usuário."""


class ErroConfirmacao(ErroAgenda):
    """A ação precisa de uma confirmação do usuário para prosseguir."""


class ErroConflito(ErroAgenda):
    """Outra pessoa alterou o mesmo campo antes."""

    def __init__(self, atual, por):
        super().__init__('Este campo foi alterado por %s agora há pouco.' % (por or 'outra pessoa'))
        self.atual, self.por = atual, por


# ------------------------------------------------------------------ desfazer (registro de atividades)
# Cada ação da agenda que dá para reverter guarda, junto do seu registro de atividades, uma fotografia das linhas
# que mexeu (antes e depois). O botão "Desfazer" só funciona se as linhas continuam como a ação as deixou.
TABELAS_DESFAZER = ('agenda_exames', 'agenda_horarios', 'agenda_espera')
IGNORAR_NA_CONFERENCIA = ('atualizado_por', 'atualizado_em')


def _tirar(db, tabela, ids):
    ids = [int(i) for i in ids]
    if not ids:
        return {}
    marcas = ','.join('?' * len(ids))
    return {r['id']: dict(r) for r in db.execute('SELECT * FROM %s WHERE id IN (%s)' % (tabela, marcas), ids)}


def _guardar_desfazer(payload):
    if has_request_context():
        g.desfazer = payload


class _Desfazer:
    """Fotografia das linhas que a ação vai mexer (`tabela=[ids]`, pais antes dos filhos); `concluir` guarda a volta."""

    def __init__(self, db, **ids):
        self.db = db
        self.ids = {t: set(v) for t, v in ids.items()}
        self.antes = {t: _tirar(db, t, v) for t, v in self.ids.items()}

    def concluir(self, **novos):
        for t, v in novos.items():
            self.ids.setdefault(t, set()).update(v)
        tabelas = {}
        for t, ids in self.ids.items():
            depois, antes = _tirar(self.db, t, ids), self.antes.get(t, {})
            tabelas[t] = {'antes': {str(i): antes.get(i) for i in sorted(ids)}, 'depois': {str(i): depois.get(i) for i in sorted(ids)}}
        _guardar_desfazer({'tabelas': tabelas})


def _conferivel(linha):
    # números com vírgula perdem as últimas casas ao passar pelo JSON do desfazer: compara com folga
    return None if linha is None else {k: (round(v, 6) if isinstance(v, float) else v) for k, v in linha.items()
                                       if k not in IGNORAR_NA_CONFERENCIA}


def aplicar_desfazer(db, payload):
    """Volta atrás numa ação. Levanta ErroAgenda se os dados mudaram depois dela (nada é alterado nesse caso)."""
    if payload.get('apagar_agendas'):
        ids = [int(i) for i in payload['apagar_agendas']]
        existentes = _tirar(db, 'agenda_exames', ids)
        if not existentes:
            raise ErroAgenda('Essas agendas já não existem.')
        marcas = ','.join('?' * len(existentes))
        com_gente = db.execute("SELECT COUNT(*) FROM agenda_horarios WHERE agenda_id IN (%s) AND (TRIM(paciente)<>'' )" % marcas,
                               list(existentes)).fetchone()[0]
        if com_gente:
            raise ErroAgenda('Não dá para desfazer: já há paciente marcado nessas agendas.')
        db.execute('DELETE FROM agenda_horarios WHERE agenda_id IN (%s)' % marcas, list(existentes))
        db.execute('DELETE FROM agenda_exames WHERE id IN (%s)' % marcas, list(existentes))
        db.commit()
        return
    tabelas = payload.get('tabelas') or {}
    from . import desfazer as geral
    if not tabelas or any(t not in TABELAS_DESFAZER and not geral.tabela_permitida(db, t) for t in tabelas):
        raise ErroAgenda('Esta ação não pode ser desfeita.')
    for t, d in tabelas.items():
        atuais = _tirar(db, t, d['depois'])
        for i, esperado in d['depois'].items():
            if _conferivel(atuais.get(int(i))) != _conferivel(esperado):
                raise ErroAgenda('Não dá para desfazer: esse registro foi alterado depois desta ação.')
    for t, d in tabelas.items():
        colunas = {r[1] for r in db.execute('PRAGMA table_info(%s)' % t)}
        for i, antes in d['antes'].items():
            if antes is None or not set(antes) <= colunas:
                continue
            cols = [c for c in antes if c != 'id']
            if db.execute('SELECT 1 FROM %s WHERE id=?' % t, (int(i),)).fetchone():
                db.execute('UPDATE %s SET %s WHERE id=?' % (t, ', '.join('%s=?' % c for c in cols)), [antes[c] for c in cols] + [int(i)])
            else:
                db.execute('INSERT INTO %s (id, %s) VALUES (?,%s)' % (t, ', '.join(cols), ','.join('?' * len(cols))),
                           [int(i)] + [antes[c] for c in cols])
    for t, d in reversed(list(tabelas.items())):
        for i, antes in d['antes'].items():
            if antes is None:
                db.execute('DELETE FROM %s WHERE id=?' % t, (int(i),))
    db.commit()


# ------------------------------------------------------------------ horas e textos
def hora_valida(txt):
    m = re.fullmatch(r'\s*(\d{1,2})[:hH.]?(\d{2})\s*', str(txt or ''))
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    if h > 23 or mi > 59:
        return None
    return '%02d:%02d' % (h, mi)


def minutos(hhmm):
    return int(hhmm[:2]) * 60 + int(hhmm[3:5])


def para_hhmm(m):
    return '%02d:%02d' % divmod(m, 60)


def _inteiro(v):
    s = str(v if v is not None else '').strip()
    return int(s) if s.isdigit() else 0


def _limpar(v, limite):
    return re.sub(r'\s+', ' ', str(v or '')).strip()[:limite]


def contato_padrao(texto):
    """Telefone no padrão (XX)9XXXX-XXXX (celular, 11 dígitos); fixo de 10 dígitos vira (XX)XXXX-XXXX.
    Vários contatos vêm separados por "/" e são guardados como "contato1 / contato2".
    Sem número de telefone (ex.: só um nome), o texto digitado é mantido."""
    partes = [p.strip() for p in re.split(r'[/;]', texto or '') if p.strip()]
    if len(partes) <= 1:
        return util.telefone_padrao(texto)
    return ' / '.join(util.telefone_padrao(p) for p in partes)


def primeiro_telefone(texto):
    """Só o primeiro número com DDD (para o WhatsApp de faltas), quando há mais de um contato."""
    for p in re.split(r'[/;]', texto or ''):
        if util.telefone_valido(p):
            return util.so_digitos(p)
    return ''


def vincular_antigas(db):
    """Liga ao exame cadastrado as agendas que ainda não têm vínculo, pelo nome (ex.: MIOCARDIO = MIBI). As que não casam ficam sem vínculo."""
    cad = db.execute('SELECT id, nome FROM exames').fetchall()
    for r in db.execute('SELECT id, exame FROM agenda_exames WHERE exame_id IS NULL').fetchall():
        achado = exame_do_nome(r['exame'], cad)
        if achado:
            db.execute('UPDATE agenda_exames SET exame_id=? WHERE id=?', (achado[0], r['id']))


def _log(db, r, acao, campo='', antes='', depois='', usuario=None, hid=None):
    """Registra uma alteração na linha da agenda (`r` é a linha lida por _linha, antes da mudança, ou None)."""
    if usuario is None and has_request_context() and g.get('usuario'):
        usuario = g.usuario['usuario']
    db.execute('INSERT INTO agenda_log (criado_em, usuario, horario_id, agenda_id, data, hora, paciente, acao, campo, antes, depois) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
               (agora(), usuario, hid or (r['id'] if r else None), r['agenda_id'] if r else None, r['dia'] if r else None, r['hora'] if r else None,
                (r['paciente'] or '') if r else '', acao, campo, str(antes or '')[:300], str(depois or '')[:300]))


def historico(db, hid, limite=100):
    return [dict(x) for x in db.execute('SELECT criado_em, usuario, acao, campo, antes, depois FROM agenda_log WHERE horario_id=? ORDER BY id DESC LIMIT ?', (hid, limite))]


def definir_chegou(db, hid, chegou, usuario):
    """Marca (ou desmarca) que o paciente chegou à clínica. Vale para todos os usuários e entra na contagem do relatório."""
    r = _linha(db, hid)
    if not (r['paciente'] or '').strip():
        raise ErroAgenda('Preencha o nome do paciente antes de marcar que chegou.')
    chegou = 1 if chegou else 0
    if chegou == (1 if r['chegou'] else 0):
        return {'data': r['dia'], 'chegou': bool(chegou)}
    db.execute('UPDATE agenda_horarios SET chegou=?, chegou_por=?, chegou_em=?, atualizado_por=?, atualizado_em=? WHERE id=?',
               (chegou, usuario if chegou else None, agora() if chegou else None, usuario, agora(), hid))
    _log(db, r, 'Chegada', 'chegou', 'sim' if r['chegou'] else 'não', 'sim' if chegou else 'não', usuario)
    db.commit()
    return {'data': r['dia'], 'chegou': bool(chegou)}


def eh_mibi(exame):
    """Exames de cintilografia do miocárdio (MIBI) têm a autorização em escolha: Estresse, Repouso ou Protocolo."""
    s = unicodedata.normalize('NFKD', exame or '').encode('ascii', 'ignore').decode().upper()
    return 'MIBI' in s or 'MIOCARD' in s


def _senha_mibi(valor):
    """Converte o texto para uma das opções do MIBI (sem diferenciar maiúsculas); vazio é permitido."""
    if not valor:
        return ''
    for op in SENHAS_MIBI:
        if op.casefold() == valor.casefold():
            return op
    raise ErroAgenda('No MIBI, a senha de autorização é Estresse, Repouso ou Protocolo.')


def gerar_horas(inicio, intervalo, qtd):
    base = minutos(inicio)
    horas = []
    for k in range(qtd):
        m = base + k * intervalo
        if m >= 24 * 60:
            raise ErroAgenda('Os horários passam da meia-noite. Reduza a quantidade ou o intervalo.')
        horas.append(para_hhmm(m))
    return horas


def fim_da_agenda(inicio, intervalo, ultima_hora):
    m = minutos(ultima_hora or inicio) + intervalo
    return para_hhmm(min(m, 24 * 60 - 1))


# ------------------------------------------------------------------ dias bloqueados
def bloqueio(db, data_iso):
    r = db.execute('SELECT motivo FROM agenda_bloqueios WHERE data=?', (data_iso,)).fetchone()
    return None if r is None else (r['motivo'] or 'Dia bloqueado')


def bloquear(db, data_iso, motivo, usuario):
    if db.execute('SELECT 1 FROM agenda_exames WHERE data=?', (data_iso,)).fetchone():
        raise ErroAgenda('Este dia já tem agenda criada. Exclua as agendas do dia antes de bloqueá-lo.')
    db.execute('INSERT OR REPLACE INTO agenda_bloqueios (data, motivo, criado_por, criado_em) VALUES (?,?,?,?)',
               (data_iso, _limpar(motivo, 120), usuario, agora()))
    db.commit()


def desbloquear(db, data_iso):
    db.execute('DELETE FROM agenda_bloqueios WHERE data=?', (data_iso,))
    db.commit()


# ------------------------------------------------------------------ criar agendas
def _nome_exame(db, bruto):
    nome = _limpar(bruto, 80)
    if not nome:
        raise ErroAgenda('Informe o nome da agenda.')
    r = db.execute('SELECT nome FROM exames WHERE nome=?', (nome,)).fetchone()
    if r:
        return r['nome']
    r = db.execute('SELECT exame FROM agenda_exames WHERE exame=? COLLATE NOCASE LIMIT 1', (nome,)).fetchone()
    return r['exame'] if r else nome


def validar_nova(f, db):
    """Valida o formulário de criação e devolve os dados normalizados (ou levanta ErroAgenda com todos os problemas)."""
    erros = []
    d = util.para_data(f.get('data'))
    if not d:
        erros.append('Escolha a data.')
    cad = db.execute('SELECT id, nome FROM exames WHERE ativo=1').fetchall()
    exame_id = _inteiro(f.get('exame_id'))
    vinculo = next((e for e in cad if e['id'] == exame_id), None)
    if vinculo is None and not exame_id:   # sem o campo (outros programas): tenta ligar pelo nome da agenda
        achado = exame_do_nome(f.get('exame'), cad)
        vinculo = next((e for e in cad if achado and e['id'] == achado[0]), None)
    if vinculo is None:
        erros.append('Escolha o exame cadastrado ao qual a agenda será vinculada.')
    nome_agenda = _limpar(f.get('exame'), 80)
    try:
        exame = _nome_exame(db, nome_agenda)
    except ErroAgenda as e:
        exame = ''
        erros.append(str(e))
    # 6ª coluna: MIBI = "Etapa" (Estresse ou Repouso já preenchido em todas as linhas); demais exames = o título escolhido (padrão "Exame") e o exame vinculado preenchido
    etapa = _limpar(f.get('etapa'), 20).capitalize()
    if etapa and etapa not in ('Estresse', 'Repouso'):
        erros.append('A etapa do MIBI é Estresse ou Repouso.')
    if vinculo is not None and eh_mibi(vinculo['nome']):
        coluna_titulo, senha_padrao = 'Etapa', etapa
    else:
        coluna_titulo = _limpar(f.get('coluna_titulo'), 30) or 'Exame'
        senha_padrao = _limpar(vinculo['nome'], CAMPOS['senha']) if vinculo is not None else ''
    inicio = hora_valida(f.get('inicio'))
    if not inicio:
        erros.append('Informe o horário de início (exemplo: 08:00).')
    intervalo = _inteiro(f.get('intervalo'))
    if not 1 <= intervalo <= 240:
        erros.append('O intervalo deve ficar entre 1 e 240 minutos.')
    qtd = _inteiro(f.get('qtd'))
    fim = hora_valida(f.get('fim')) if (f.get('fim') or '').strip() else None
    if not qtd and fim and inicio and 1 <= intervalo <= 240:
        qtd = max(0, (minutos(fim) - minutos(inicio)) // intervalo)
    if qtd < 1:
        erros.append('Informe quantos exames serão feitos (ou o horário de término).')
    elif qtd > MAX_QTD:
        erros.append('No máximo %d horários por agenda.' % MAX_QTD)
    vagas = _inteiro(f.get('vagas')) if (f.get('vagas') or '').strip() else 1
    if not 1 <= vagas <= MAX_VAGAS:
        erros.append('Pacientes por horário: de 1 a %d.' % MAX_VAGAS)
    semanas = _inteiro(f.get('semanas'))
    if semanas > MAX_SEMANAS:
        erros.append('Repetir por no máximo %d semanas.' % MAX_SEMANAS)
    reserva = None
    if f.get('reserva_ativa'):
        conv = convenio_canonico(db, _limpar(f.get('reserva_convenio'), 60))
        r_ini = hora_valida(f.get('reserva_inicio')) or inicio
        r_qtd, r_passo = _inteiro(f.get('reserva_qtd')), _inteiro(f.get('reserva_passo')) or 1
        if not conv:
            erros.append('Reserva: escolha o convênio (cadastrado em Convênios).')
        if not 1 <= r_qtd <= MAX_QTD:
            erros.append('Reserva: informe quantos horários reservar (de 1 a %d).' % MAX_QTD)
        if not 1 <= r_passo <= 50:
            erros.append('Reserva: o intervalo entre os horários reservados vai de 1 a 50.')
        if conv and r_ini and 1 <= r_qtd <= MAX_QTD and 1 <= r_passo <= 50:
            reserva = {'convenio': conv, 'inicio': r_ini, 'qtd': r_qtd, 'passo': r_passo}
    if not erros and qtd * vagas > MAX_LINHAS:
        erros.append('A agenda teria mais de %d linhas. Reduza a quantidade ou os pacientes por horário.' % MAX_LINHAS)
    if not erros:
        try:
            gerar_horas(inicio, intervalo, qtd)
        except ErroAgenda as e:
            erros.append(str(e))
    if erros:
        raise ErroAgenda(' '.join(erros))
    modelo = _limpar(f.get('nome_modelo'), 60) if f.get('salvar_modelo') else ''
    if f.get('salvar_modelo') and not modelo:
        raise ErroAgenda('Dê um nome ao modelo para salvá-lo.')
    return {'data': d, 'exame': exame, 'exame_id': vinculo['id'] if vinculo else None, 'coluna_titulo': coluna_titulo, 'senha_padrao': senha_padrao, 'inicio': inicio, 'intervalo': intervalo, 'qtd': qtd, 'vagas': vagas,
            'semanas': semanas, 'modelo': modelo, 'observacao': _limpar(f.get('observacao'), OBSERVACAO_MAX),
            'reserva': reserva}


def _inserir_agenda(db, dia_iso, exame, inicio, intervalo, qtd, vagas, usuario, observacao='', reserva=None, exame_id=None, coluna_titulo=None, senha_padrao=''):
    cur = db.execute('INSERT INTO agenda_exames (data, exame, inicio, intervalo, vagas, observacao, reserva_unacon, reserva_convenio, '
                     'criado_por, criado_em, exame_id, coluna_titulo, senha_padrao) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                     (dia_iso, exame, inicio, intervalo, vagas, observacao, 1 if reserva else 0, reserva['convenio'] if reserva else '',
                      usuario, agora(), exame_id, coluna_titulo, senha_padrao or ''))
    aid = cur.lastrowid
    ordem = 0
    for hora in gerar_horas(inicio, intervalo, qtd):
        for _ in range(vagas):
            ordem += 1
            db.execute('INSERT INTO agenda_horarios (agenda_id, hora, ordem, senha) VALUES (?,?,?,?)', (aid, hora, ordem, senha_padrao or ''))
    if reserva:
        _reservar_na_criacao(db, aid, reserva)
    return aid


def _reservar_na_criacao(db, aid, reserva):
    """Reserva `qtd` horários para o convênio, a partir de `inicio`, pulando de `passo` em `passo` (1 = horários seguidos)."""
    horas = [r[0] for r in db.execute('SELECT DISTINCT hora FROM agenda_horarios WHERE agenda_id=? AND hora>=? ORDER BY hora',
                                      (aid, reserva['inicio']))]
    escolhidas = horas[::reserva['passo']][:reserva['qtd']]
    if escolhidas:
        db.execute('UPDATE agenda_horarios SET reservado_unacon=1, reservado_convenio=?, convenio=? WHERE agenda_id=? AND hora IN (%s)'
                   % ','.join('?' * len(escolhidas)), [reserva['convenio'], reserva['convenio'], aid] + escolhidas)


def criar(db, dados, usuario):
    """Cria a agenda no dia escolhido e, se pedido, repete no mesmo dia da semana nas semanas seguintes."""
    primeiro = dados['data']
    if bloqueio(db, primeiro.isoformat()) is not None:
        raise ErroAgenda('Este dia está bloqueado. Desbloqueie o dia para criar agendas.')
    ids, pulados = [], []
    for k in range(dados['semanas'] + 1):
        dia = primeiro + timedelta(days=7 * k)
        if bloqueio(db, dia.isoformat()) is not None:
            pulados.append(dia.isoformat())
            continue
        ids.append(_inserir_agenda(db, dia.isoformat(), dados['exame'], dados['inicio'], dados['intervalo'], dados['qtd'],
                                   dados['vagas'], usuario, dados['observacao'], dados['reserva'], dados.get('exame_id'),
                                   dados.get('coluna_titulo'), dados.get('senha_padrao')))
    if dados['modelo']:
        db.execute('INSERT OR REPLACE INTO agenda_modelos (nome, exame, inicio, intervalo, qtd, vagas, exame_id) VALUES (?,?,?,?,?,?,?)',
                   (dados['modelo'], dados['exame'], dados['inicio'], dados['intervalo'], dados['qtd'], dados['vagas'], dados.get('exame_id')))
    db.commit()
    if ids:
        _guardar_desfazer({'apagar_agendas': ids})
    return {'ids': ids, 'pulados': pulados, 'data': primeiro.isoformat()}


def modelos(db):
    return [dict(r) for r in db.execute('SELECT id, nome, exame, exame_id, inicio, intervalo, qtd, vagas FROM agenda_modelos ORDER BY nome')]


def renomear_agenda(db, aid, nome):
    """Muda só o NOME da agenda (o texto das mensagens de WhatsApp usa esse nome); o exame cadastrado vinculado continua o mesmo."""
    nome = _limpar(nome, 80)
    if not nome:
        raise ErroAgenda('Informe o nome da agenda.')
    a = db.execute('SELECT * FROM agenda_exames WHERE id=?', (aid,)).fetchone()
    if not a:
        raise ErroAgenda('Esta agenda não existe mais. Atualize a página.')
    db.execute('UPDATE agenda_exames SET exame=? WHERE id=?', (nome, aid))
    db.commit()
    return {'data': a['data'], 'nome': nome}


def excluir_agenda(db, aid, confirmar=False):
    ag = db.execute('SELECT * FROM agenda_exames WHERE id=?', (aid,)).fetchone()
    if not ag:
        raise ErroAgenda('Esta agenda não existe mais. Atualize a página.')
    n = db.execute("SELECT COUNT(*) FROM agenda_horarios WHERE agenda_id=? AND TRIM(paciente)<>''", (aid,)).fetchone()[0]
    if n and not confirmar:
        raise ErroConfirmacao('Esta agenda tem %d paciente(s) marcado(s). Excluir mesmo assim?' % n)
    d = _Desfazer(db, agenda_exames=[aid],
                  agenda_horarios=[r[0] for r in db.execute('SELECT id FROM agenda_horarios WHERE agenda_id=?', (aid,))])
    db.execute('DELETE FROM agenda_horarios WHERE agenda_id=?', (aid,))
    db.execute('DELETE FROM agenda_exames WHERE id=?', (aid,))
    d.concluir()
    db.commit()
    return {'data': ag['data']}


# ------------------------------------------------------------------ leitura do dia
def resumo(linhas):
    r = {'vagas': len(linhas), 'marcados': 0, 'livres': 0, 'reservados': 0, 'AGENDADO': 0, 'VEIO': 0, 'FALTOU': 0, 'RETORNO': 0,
         'RESGATADO': 0, 'DESISTIU': 0, 'chegou': 0}
    for l in linhas:
        if (l['paciente'] or '').strip():
            r['marcados'] += 1
            r['chegou'] += 1 if l.get('chegou') else 0
            r[l['status'] if l['status'] in STATUS else 'AGENDADO'] += 1
        elif l.get('reservado'):
            r['reservados'] += 1   # guardado para um convênio: não conta como livre
        else:
            r['livres'] += 1
    return r


def _linha_json(r):
    return {'id': r['id'], 'hora': r['hora'], 'paciente': r['paciente'], 'convenio': r['convenio'], 'contato': r['contato'],
            'senha': r['senha'], 'idade': r['idade'] or '', 'observacao': r['observacao'], 'status': r['status'], 'remarcado_para': r['remarcado_para'] or '',
            'chegou': bool(r['chegou']), 'chegou_por': r['chegou_por'] or '', 'por': r['atualizado_por'] or '', 'resgatado_por': r['resgatado_por'] or '', 'reservado': bool(r['reservado_unacon']),
            'reservado_convenio': (r['reservado_convenio'] or '') if r['reservado_unacon'] else ''}


def tipo_da_agenda(db, a):
    """Nome do exame cadastrado ao qual a agenda está vinculada (sem vínculo, vale o nome da agenda)."""
    if a['exame_id']:
        r = db.execute('SELECT nome FROM exames WHERE id=?', (a['exame_id'],)).fetchone()
        if r:
            return r['nome']
    return a['exame']


def _ordem_exames(db):
    """Nomes de exame na ordem da lista da agenda: primeiro os que a recepção posicionou; os demais seguem a hora da primeira agenda."""
    posicoes = {r['exame']: r['posicao'] for r in db.execute('SELECT exame, posicao FROM agenda_ordem_exames')}
    primeiros = db.execute('SELECT exame, MIN(inicio) AS ini, MIN(id) AS primeiro FROM agenda_exames GROUP BY exame').fetchall()
    chave = {r['exame']: (0, posicoes[r['exame']], '', 0) if r['exame'] in posicoes else (1, 0, r['ini'], r['primeiro'])
             for r in primeiros}
    return sorted(chave, key=lambda nome: chave[nome])


def ordem_exames(db):
    """Posição escolhida de cada exame (só os que a recepção ordenou); os demais ficam depois, pela hora."""
    return {r['exame']: r['posicao'] for r in db.execute('SELECT exame, posicao FROM agenda_ordem_exames')}


def mover_exame(db, exame, direcao):
    """Sobe ('cima') ou desce ('baixo') o exame na lista. Grava a ordem inteira, para não haver empates."""
    nomes = _ordem_exames(db)
    if exame not in nomes:
        raise ErroAgenda('Exame não encontrado nas agendas.')
    i = nomes.index(exame)
    j = i - 1 if direcao == 'cima' else i + 1 if direcao == 'baixo' else None
    if j is None:
        raise ErroAgenda('Direção inválida.')
    if 0 <= j < len(nomes):
        nomes[i], nomes[j] = nomes[j], nomes[i]
    db.execute('DELETE FROM agenda_ordem_exames')
    db.executemany('INSERT INTO agenda_ordem_exames (exame, posicao) VALUES (?,?)', [(n, k + 1) for k, n in enumerate(nomes)])
    db.commit()
    return {'ordem': nomes}


def listar_dia(db, data_iso):
    rank = ordem_exames(db)
    ags = sorted(db.execute('SELECT * FROM agenda_exames WHERE data=? ORDER BY inicio, id', (data_iso,)).fetchall(),
                 key=lambda a: (rank.get(a['exame'], 10 ** 6), a['inicio'], a['id']))
    por_agenda = {a['id']: [] for a in ags}
    for r in db.execute('SELECT h.* FROM agenda_horarios h JOIN agenda_exames a ON a.id=h.agenda_id WHERE a.data=? '
                        'ORDER BY h.agenda_id, h.hora, h.ordem, h.id', (data_iso,)):
        por_agenda[r['agenda_id']].append(_linha_json(r))
    saida = []
    for a in ags:
        linhas = por_agenda[a['id']]
        tipo = tipo_da_agenda(db, a)
        saida.append({'id': a['id'], 'exame': a['exame'], 'exame_cadastrado': tipo, 'mibi': eh_mibi(tipo), 'coluna_titulo': a['coluna_titulo'] or ('Etapa' if eh_mibi(tipo) else 'Senha de autorização'), 'observacao': a['observacao'] or '',
                      'reserva_convenio': (a['reserva_convenio'] or '') or next((l['reservado_convenio'] for l in linhas if l['reservado']), ''),
                      'reserva_unacon': bool(a['reserva_unacon']) or any(l['reservado'] for l in linhas),
                      'inicio': a['inicio'], 'intervalo': a['intervalo'], 'vagas': a['vagas'],
                      'fim': fim_da_agenda(a['inicio'], a['intervalo'], linhas[-1]['hora'] if linhas else None),
                      'resumo': resumo(linhas), 'linhas': linhas})
    return saida


def marcas_do_mes(db, ano, mes):
    """Dias do mês com agenda e dias bloqueados (o calendário só destaca; não mostra números)."""
    ini = date(ano, mes, 1).isoformat()
    fim = date(ano, mes, calendar.monthrange(ano, mes)[1]).isoformat()
    dias = sorted({r['data'] for r in db.execute('SELECT data FROM agenda_exames WHERE data BETWEEN ? AND ?', (ini, fim))})
    bloq = {r['data']: r['motivo'] for r in db.execute('SELECT data, motivo FROM agenda_bloqueios WHERE data BETWEEN ? AND ?', (ini, fim))}
    return {'dias': dias, 'bloqueados': bloq}


# ------------------------------------------------------------------ linhas de horário
def _linha(db, hid):
    r = db.execute('SELECT h.*, a.data AS dia, a.exame AS exame_agenda, COALESCE(ex.nome, a.exame) AS exame_tipo, a.intervalo, a.vagas, '
                   'a.reserva_convenio AS agenda_reserva FROM agenda_horarios h '
                   'JOIN agenda_exames a ON a.id=h.agenda_id LEFT JOIN exames ex ON ex.id=a.exame_id WHERE h.id=?', (hid,)).fetchone()
    if not r:
        raise ErroAgenda('Esta linha não existe mais. Atualize a página.')
    return r


def adicionar_horario(db, aid, usuario, depois=None, qtd=1):
    """Sem `depois`: acrescenta horários no fim da agenda (último + intervalo). Com `depois`: mais uma vaga no mesmo horário."""
    ag = db.execute('SELECT * FROM agenda_exames WHERE id=?', (aid,)).fetchone()
    if not ag:
        raise ErroAgenda('Esta agenda não existe mais. Atualize a página.')
    qtd = max(1, min(qtd, 50))
    total = db.execute('SELECT COUNT(*) FROM agenda_horarios WHERE agenda_id=?', (aid,)).fetchone()[0]
    if depois:
        ref = db.execute('SELECT * FROM agenda_horarios WHERE id=? AND agenda_id=?', (depois, aid)).fetchone()
        if not ref:
            raise ErroAgenda('A linha de referência não existe mais. Atualize a página.')
        novas = [(ref['hora'], ref['ordem'])] * qtd
    else:
        ult = db.execute('SELECT hora FROM agenda_horarios WHERE agenda_id=? ORDER BY hora DESC, ordem DESC LIMIT 1', (aid,)).fetchone()
        ordem = db.execute('SELECT COALESCE(MAX(ordem), 0) FROM agenda_horarios WHERE agenda_id=?', (aid,)).fetchone()[0]
        base = minutos(ult['hora']) + ag['intervalo'] if ult else minutos(ag['inicio'])
        novas = []
        for k in range(qtd):
            m = base + k * ag['intervalo']
            if m >= 24 * 60:
                raise ErroAgenda('Os horários passam da meia-noite.')
            for _ in range(ag['vagas']):
                ordem += 1
                novas.append((para_hhmm(m), ordem))
    if total + len(novas) > MAX_LINHAS:
        raise ErroAgenda('Esta agenda já está no limite de %d linhas.' % MAX_LINHAS)
    d = _Desfazer(db)
    criadas = [db.execute('INSERT INTO agenda_horarios (agenda_id, hora, ordem, senha) VALUES (?,?,?,?)', (aid, hora, ordem, ag['senha_padrao'] or '')).lastrowid
               for hora, ordem in novas]
    d.concluir(agenda_horarios=criadas)
    db.commit()
    return {'data': ag['data'], 'novas': len(novas)}


def excluir_horario(db, hid, confirmar=False):
    r = _linha(db, hid)
    if (r['paciente'] or '').strip() and not confirmar:
        raise ErroConfirmacao('Este horário tem paciente marcado (%s). Retirar mesmo assim?' % r['paciente'])
    _log(db, r, 'Horário retirado', 'paciente', r['paciente'], '')
    d = _Desfazer(db, agenda_horarios=[hid])
    db.execute('DELETE FROM agenda_horarios WHERE id=?', (hid,))
    d.concluir()
    db.commit()
    return {'data': r['dia']}


def _duplicado(db, r, paciente):
    chave = re.sub(r'\s+', ' ', paciente).casefold()
    for o in db.execute('SELECT h.id, h.hora, h.paciente FROM agenda_horarios h JOIN agenda_exames a ON a.id=h.agenda_id '
                        'WHERE a.data=? AND a.exame=? COLLATE NOCASE AND h.id<>?', (r['dia'], r['exame_agenda'], r['id'])):
        if re.sub(r'\s+', ' ', o['paciente'] or '').casefold() == chave:
            return 'Atenção: %s já está marcado(a) neste dia para %s, às %s.' % (paciente, r['exame_agenda'], o['hora'])
    return None


def _avisar_mibi(db, hid):
    try:
        from . import chat
        chat.avisar_agendamento_mibi(db, _linha(db, hid))
    except Exception:
        logging.getLogger(__name__).exception('Falha ao enviar aviso de MIBI do horário %s; o agendamento foi mantido.', hid)


def salvar_campo(db, hid, campo, valor, antes, usuario):
    """Grava uma célula da grade. `antes` é o valor que a tela tinha: se mudou no banco, avisa o conflito em vez de sobrescrever."""
    if campo not in CAMPOS:
        raise ErroAgenda('Campo inválido.')
    r = _linha(db, hid)
    if antes is not None and (antes or '').strip() != (r[campo] or '').strip():
        raise ErroConflito(r[campo] or '', r['atualizado_por'])
    if campo == 'hora':
        novo = hora_valida(valor)
        if not novo:
            raise ErroAgenda('Horário inválido. Use o formato 08:30.')
    elif campo == 'senha' and eh_mibi(r['exame_tipo']):
        novo = _senha_mibi(_limpar(valor, CAMPOS[campo]))
    elif campo == 'contato':
        novo = contato_padrao(_limpar(valor, CAMPOS[campo]))
    elif campo == 'idade':
        novo = re.sub(r'\D', '', str(valor or ''))[:CAMPOS[campo]]   # só dígitos, até 3; vazio é permitido
    elif campo == 'convenio':
        novo = convenio_canonico(db, _limpar(valor, CAMPOS[campo]))
        if novo is None:
            raise ErroAgenda('Escolha um convênio da lista (cadastrado em Convênios).')
    else:
        novo = _limpar(valor, CAMPOS[campo])
    sets, params = ['%s=?' % campo], [novo]
    aviso = None
    if campo == 'paciente':
        if not novo:
            sets += ["status='AGENDADO'", 'remarcado_para=NULL', "idade=''"]
        else:
            if r['reservado_unacon'] and not mesmo_convenio(r['convenio'], r['reservado_convenio']):
                raise ErroAgenda(msg_reserva(r['reservado_convenio']))
            aviso = _duplicado(db, r, novo)
    elif campo == 'convenio':
        if novo and mesmo_convenio(novo, r['agenda_reserva']):
            sets += ['reservado_unacon=1', 'reservado_convenio=?']   # marcou o convênio da reserva: o horário fica reservado
            params.append(r['agenda_reserva'])
        elif novo and r['reservado_unacon'] and not mesmo_convenio(novo, r['reservado_convenio']):
            if not (r['paciente'] or '').strip():
                raise ErroAgenda(msg_reserva(r['reservado_convenio']) + ' Para liberar, use “Liberar reserva” da agenda.')
            sets += ['reservado_unacon=0', 'reservado_convenio=NULL']   # corrigiu o convênio de quem já está marcado
    sets += ['atualizado_por=?', 'atualizado_em=?']
    params += [usuario, agora(), hid]
    db.execute('UPDATE agenda_horarios SET %s WHERE id=?' % ', '.join(sets), params)
    if campo == 'paciente' and not novo:
        db.execute('UPDATE agenda_horarios SET chegou=0, chegou_por=NULL, chegou_em=NULL WHERE id=?', (hid,))
    if (r[campo] or '') != (novo or ''):
        _log(db, r, 'Campo alterado', campo, r[campo], novo, usuario)
    db.commit()
    atual = _linha(db, hid)
    if campo in ('paciente', 'senha', 'hora') and (r[campo] or '') != novo:
        _avisar_mibi(db, hid)
    return {'valor': novo, 'aviso': aviso, 'status': atual['status'], 'data': r['dia'], 'reservado': bool(atual['reservado_unacon'])}


def _checar_remarcado(r):
    """Quem foi remarcado para uma nova data fica travado: o status só muda na nova marcação, exceto para administrador e gerência (que passam por definir_status com liberar_remarcado)."""
    if r['status'] == 'RETORNO' and (r['remarcado_para'] or '').strip():
        raise ErroAgenda('Este paciente foi remarcado para %s. O status desta linha não pode mais ser alterado; use a nova marcação.' % r['remarcado_para'])


def definir_status(db, hid, status, usuario, liberar_remarcado=False):
    if status not in STATUS:
        raise ErroAgenda('Status inválido.')
    r = _linha(db, hid)
    if not (r['paciente'] or '').strip():
        raise ErroAgenda('Preencha o nome do paciente antes de mudar o status.')
    if not liberar_remarcado:
        _checar_remarcado(r)
    resgate = status in RESGATES and r['status'] == 'FALTOU'   # resgate só quando sai de Faltou
    d = _Desfazer(db, agenda_horarios=[hid])
    db.execute('UPDATE agenda_horarios SET status=?, remarcado_para=CASE WHEN ?=\'RETORNO\' THEN remarcado_para END, '
               'resgatado_por=?, resgatado_em=?, atualizado_por=?, atualizado_em=? WHERE id=?',
               (status, status, usuario if resgate else None, agora() if resgate else None, usuario, agora(), hid))
    acao = 'Reagendado por ' + usuario if resgate and status == 'RESGATADO' else 'Status'
    _log(db, r, acao, 'status', r['status'], status, usuario)
    d.concluir()
    db.commit()
    return {'data': r['dia'], 'status': status}


def horarios_livres(db, data_iso, convenio=''):
    """Linhas sem paciente do dia (para remarcar e encaixar), com o nome do exame.
    Horário reservado para um convênio só aparece para pacientes desse convênio (`convenio`)."""
    linhas = db.execute("SELECT h.id, h.hora, a.exame, a.id AS aid, h.reservado_unacon AS reservado, "
                        "COALESCE(h.reservado_convenio,'') AS reservado_convenio FROM agenda_horarios h "
                        "JOIN agenda_exames a ON a.id=h.agenda_id "
                        "WHERE a.data=? AND TRIM(h.paciente)='' AND (h.reservado_unacon=0 OR (?<>'' AND h.reservado_convenio=? COLLATE NOCASE)) "
                        "ORDER BY a.exame, h.hora, h.id", (data_iso, convenio or '', convenio or '')).fetchall()
    return [dict(r) for r in linhas]


# ------------------------------------------------------------------ reserva de horários para um convênio
def _reservar_linhas(db, ids, reservar, convenio):
    """Reserva (ou libera) horários sem paciente para o convênio da agenda. Reservado fica com o convênio preenchido."""
    nome = convenio_canonico(db, convenio)
    if not nome:
        raise ErroAgenda('O convênio %s não está mais cadastrado em Convênios.' % convenio)
    if not ids:
        raise ErroAgenda('Nenhum horário livre encontrado para alterar.')
    d = _Desfazer(db, agenda_horarios=ids)
    marcas = ','.join('?' * len(ids))
    if reservar:
        db.execute("UPDATE agenda_horarios SET reservado_unacon=1, reservado_convenio=?, convenio=? WHERE id IN (%s) AND TRIM(paciente)=''" % marcas,
                   [nome, nome] + list(ids))
    else:
        db.execute("UPDATE agenda_horarios SET reservado_unacon=0, reservado_convenio=NULL, "
                   "convenio=CASE WHEN convenio=? COLLATE NOCASE THEN '' ELSE convenio END "
                   "WHERE id IN (%s) AND TRIM(paciente)=''" % marcas, [nome] + list(ids))
    d.concluir()
    db.commit()
    return len(ids)


def reservar_linha(db, hid, reservar):
    r = _linha(db, hid)
    if not (r['agenda_reserva'] or '').strip():
        raise ErroAgenda(MSG_SEM_RESERVA)
    if (r['paciente'] or '').strip():
        raise ErroAgenda('Este horário já tem paciente: o convênio dele define a reserva.')
    _reservar_linhas(db, [hid], reservar, r['agenda_reserva'])
    return {'data': r['dia'], 'qtd': 1}


def reservar_faixa(db, aid, de, ate, reservar):
    """Reserva (ou libera) todos os horários sem paciente de `de` até `ate` (inclusive) em uma agenda."""
    ag = db.execute('SELECT * FROM agenda_exames WHERE id=?', (aid,)).fetchone()
    if not ag:
        raise ErroAgenda('Esta agenda não existe mais. Atualize a página.')
    convenio = (ag['reserva_convenio'] or '').strip()
    if not convenio:
        raise ErroAgenda(MSG_SEM_RESERVA)
    h1, h2 = hora_valida(de), hora_valida(ate)
    if not h1 or not h2 or h2 < h1:
        raise ErroAgenda('Informe o horário inicial e o final (exemplo: 07:00 e 10:10).')
    ids = [r[0] for r in db.execute("SELECT id FROM agenda_horarios WHERE agenda_id=? AND hora BETWEEN ? AND ? AND TRIM(paciente)='' "
                                    'ORDER BY hora, ordem', (aid, h1, h2))]
    return {'data': ag['data'], 'qtd': _reservar_linhas(db, ids, reservar, convenio)}


def _checar_reserva(destino, convenio):
    """Horário reservado para um convênio só recebe paciente desse convênio."""
    if destino['reservado_unacon'] and not mesmo_convenio(convenio, destino['reservado_convenio']):
        raise ErroAgenda(msg_reserva(destino['reservado_convenio']))


def _reserva_do_destino(d, convenio):
    """(reservado, convenio da reserva) que o horário de destino passa a ter ao receber um paciente do `convenio`."""
    if mesmo_convenio(convenio, d['agenda_reserva']):
        return 1, d['agenda_reserva']
    return d['reservado_unacon'], d['reservado_convenio']


def remarcar(db, hid, destino_hid, usuario, status_origem='RETORNO'):
    """Leva o paciente para um horário livre (outra data/exame) com todas as informações e marca a origem com
    `status_origem` (RETORNO na grade; RESGATADO no reagendamento de falta), com o novo horário anotado."""
    r = _linha(db, hid)
    if not (r['paciente'] or '').strip():
        raise ErroAgenda('Não há paciente neste horário para remarcar.')
    _checar_remarcado(r)
    if destino_hid == hid:
        raise ErroAgenda('Escolha um horário diferente do atual.')
    d = _linha(db, destino_hid)
    if (d['paciente'] or '').strip():
        raise ErroAgenda('O horário escolhido já foi preenchido por outra pessoa. Escolha outro.')
    _checar_reserva(d, r['convenio'])
    quando = '%s %s · %s' % (util.data_br(d['dia']), d['hora'], d['exame_agenda'])
    origem_txt = 'Retorno marcado a partir de %s %s' % (util.data_br(r['dia']), r['hora'])
    obs = _limpar((origem_txt + ' | ' + r['observacao']) if r['observacao'] else origem_txt, CAMPOS['observacao'])
    obs = _anotar_outra_etapa(db, r, obs, {hid, destino_hid})
    agora_ts = agora()
    desf = _Desfazer(db, agenda_horarios=[hid, destino_hid])
    db.execute("UPDATE agenda_horarios SET paciente=?, convenio=?, contato=?, senha=?, idade=?, observacao=?, status='AGENDADO', "
               'remarcado_para=NULL, reservado_unacon=?, reservado_convenio=?, atualizado_por=?, atualizado_em=? WHERE id=?',
               (r['paciente'], r['convenio'], r['contato'], r['senha'], r['idade'] or '', obs, *_reserva_do_destino(d, r['convenio']),
                usuario, agora_ts, destino_hid))
    resgate = status_origem in RESGATES and r['status'] == 'FALTOU'   # de Agendado para Reagendado não é resgate
    db.execute('UPDATE agenda_horarios SET status=?, remarcado_para=?, resgatado_por=?, resgatado_em=?, atualizado_por=?, '
               'atualizado_em=? WHERE id=?',
               (status_origem, quando, usuario if resgate else None, agora_ts if resgate else None, usuario, agora_ts, hid))
    acao = 'Retorno marcado' if status_origem == 'RETORNO' else ('Reagendado por ' + usuario if status_origem == 'RESGATADO' else 'Reagendado')
    _log(db, r, acao, 'status', r['status'], status_origem + ' → ' + quando, usuario)
    _log(db, d, 'Recebeu paciente de retorno', 'paciente', '', r['paciente'] + ' (de %s %s)' % (util.data_br(r['dia']), r['hora']), usuario, hid=destino_hid)
    desf.concluir()
    db.commit()
    _avisar_mibi(db, destino_hid)
    return {'data': r['dia'], 'destino': d['dia'], 'quando': quando}


def copiar_linha(db, hid, destino_hid, usuario):
    """Copia o paciente para outro horário livre (outro dia ou exame), para quem precisa de mais de um agendamento
    (ida e retorno). A linha de origem não muda."""
    r = _linha(db, hid)
    if not (r['paciente'] or '').strip():
        raise ErroAgenda('Não há paciente neste horário para copiar.')
    if destino_hid == hid:
        raise ErroAgenda('Escolha um horário diferente do atual.')
    d = _linha(db, destino_hid)
    if (d['paciente'] or '').strip():
        raise ErroAgenda('O horário escolhido já foi preenchido por outra pessoa. Escolha outro.')
    _checar_reserva(d, r['convenio'])
    quando = '%s %s · %s' % (util.data_br(d['dia']), d['hora'], d['exame_agenda'])
    origem_txt = 'Copiado de %s %s' % (util.data_br(r['dia']), r['hora'])
    obs = _limpar((origem_txt + ' | ' + r['observacao']) if r['observacao'] else origem_txt, CAMPOS['observacao'])
    senha = r['senha']
    if eh_mibi(d['exame_tipo']) and senha not in SENHAS_MIBI:
        senha = ''  # no MIBI a senha só aceita as opções da lista
    desf = _Desfazer(db, agenda_horarios=[destino_hid])
    db.execute("UPDATE agenda_horarios SET paciente=?, convenio=?, contato=?, senha=?, idade=?, observacao=?, status='AGENDADO', "
               'remarcado_para=NULL, reservado_unacon=?, reservado_convenio=?, atualizado_por=?, atualizado_em=? WHERE id=?',
               (r['paciente'], r['convenio'], r['contato'], senha, r['idade'] or '', obs, *_reserva_do_destino(d, r['convenio']),
                usuario, agora(), destino_hid))
    _log(db, r, 'Copiado para outro horário', 'paciente', '', quando, usuario)
    _log(db, d, 'Recebeu cópia', 'paciente', '', r['paciente'] + ' (de %s %s)' % (util.data_br(r['dia']), r['hora']), usuario, hid=destino_hid)
    desf.concluir()
    db.commit()
    _avisar_mibi(db, destino_hid)
    return {'data': r['dia'], 'destino': d['dia'], 'quando': quando}


def recortar_linha(db, hid, destino_hid, usuario):
    """Recorta o paciente: leva todos os dados para outro horário livre (outro dia ou exame) e esvazia a linha de origem, liberando o horário."""
    r = _linha(db, hid)
    if not (r['paciente'] or '').strip():
        raise ErroAgenda('Não há paciente neste horário para recortar.')
    if destino_hid == hid:
        raise ErroAgenda('Escolha um horário diferente do atual.')
    d = _linha(db, destino_hid)
    if (d['paciente'] or '').strip():
        raise ErroAgenda('O horário escolhido já foi preenchido por outra pessoa. Escolha outro.')
    _checar_reserva(d, r['convenio'])
    quando = '%s %s · %s' % (util.data_br(d['dia']), d['hora'], d['exame_agenda'])
    origem_txt = 'Recortado de %s %s' % (util.data_br(r['dia']), r['hora'])
    obs = _limpar((origem_txt + ' | ' + r['observacao']) if r['observacao'] else origem_txt, CAMPOS['observacao'])
    senha = r['senha']
    if eh_mibi(d['exame_tipo']) and senha not in SENHAS_MIBI:
        senha = ''
    agora_ts = agora()
    desf = _Desfazer(db, agenda_horarios=[hid, destino_hid])
    db.execute("UPDATE agenda_horarios SET paciente=?, convenio=?, contato=?, senha=?, idade=?, observacao=?, status=?, "
               'remarcado_para=NULL, reservado_unacon=?, reservado_convenio=?, atualizado_por=?, atualizado_em=? WHERE id=?',
               (r['paciente'], r['convenio'], r['contato'], senha, r['idade'] or '', obs, r['status'] if r['status'] in ('AGENDADO', 'VEIO') else 'AGENDADO',
                *_reserva_do_destino(d, r['convenio']), usuario, agora_ts, destino_hid))
    db.execute("UPDATE agenda_horarios SET paciente='', convenio=?, contato='', senha='', idade='', observacao='', status='AGENDADO', remarcado_para=NULL, "
               'resgatado_por=NULL, resgatado_em=NULL, atualizado_por=?, atualizado_em=? WHERE id=?',
               ((r['reservado_convenio'] or '') if r['reservado_unacon'] else '', usuario, agora_ts, hid))
    db.execute('UPDATE agenda_horarios SET chegou=0, chegou_por=NULL, chegou_em=NULL WHERE id=?', (hid,))
    _log(db, r, 'Recortado para outro horário', 'paciente', r['paciente'], '', usuario)
    _log(db, d, 'Recebeu paciente recortado', 'paciente', '', r['paciente'] + ' (de %s %s)' % (util.data_br(r['dia']), r['hora']), usuario, hid=destino_hid)
    desf.concluir()
    db.commit()
    _avisar_mibi(db, destino_hid)
    return {'data': r['dia'], 'destino': d['dia'], 'quando': quando}


def marcar_retorno(db, hid, usuario):
    return definir_status(db, hid, 'RETORNO', usuario)


# ------------------------------------------------------------------ copiar para outro dia
def _trocar_etapa(senha):
    """Na cópia da agenda MIBI, Repouso vira Estresse e Estresse vira Repouso (a segunda etapa do exame)."""
    return {'repouso': 'Estresse', 'estresse': 'Repouso'}.get((senha or '').strip().casefold(), senha)


def copiar(db, origem_iso, destino_iso, com_pacientes, agenda_id, usuario, apagar_origem=False):
    """`apagar_origem` (resposta Sim da pergunta): o dia copiado é apagado e os dados, com os pacientes, passam para o novo dia."""
    if apagar_origem:
        com_pacientes = True
    if origem_iso == destino_iso:
        raise ErroAgenda('Escolha um dia diferente do atual.')
    if bloqueio(db, destino_iso) is not None:
        raise ErroAgenda('O dia de destino está bloqueado.')
    if agenda_id:
        ags = db.execute('SELECT * FROM agenda_exames WHERE id=? AND data=?', (agenda_id, origem_iso)).fetchall()
    else:
        ags = db.execute('SELECT * FROM agenda_exames WHERE data=? ORDER BY inicio, id', (origem_iso,)).fetchall()
    if not ags:
        raise ErroAgenda('Não há agenda neste dia para copiar.')
    criadas, puladas, pacientes, novas_ids, copiadas = 0, [], 0, [], []
    for a in ags:
        if db.execute('SELECT 1 FROM agenda_exames WHERE data=? AND exame=? COLLATE NOCASE AND inicio=?',
                      (destino_iso, a['exame'], a['inicio'])).fetchone():
            puladas.append('%s (%s)' % (a['exame'], a['inicio']))
            continue
        nova = db.execute('INSERT INTO agenda_exames (data, exame, inicio, intervalo, vagas, observacao, reserva_unacon, reserva_convenio, '
                          'criado_por, criado_em, exame_id, coluna_titulo, senha_padrao) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                          (destino_iso, a['exame'], a['inicio'], a['intervalo'], a['vagas'], a['observacao'], a['reserva_unacon'],
                           a['reserva_convenio'], usuario, agora(), a['exame_id'], a['coluna_titulo'],
                           _trocar_etapa(a['senha_padrao']) if eh_mibi(tipo_da_agenda(db, a)) else (a['senha_padrao'] or ''))).lastrowid
        for h in db.execute('SELECT * FROM agenda_horarios WHERE agenda_id=? ORDER BY hora, ordem, id', (a['id'],)).fetchall():
            # quem foi remarcado já está em outro horário: não volta duplicado na cópia
            if com_pacientes and (h['paciente'] or '').strip() and h['status'] != 'RETORNO':
                pacientes += 1
                senha = _trocar_etapa(h['senha']) if eh_mibi(tipo_da_agenda(db, a)) else h['senha']
                db.execute('INSERT INTO agenda_horarios (agenda_id, hora, ordem, paciente, convenio, contato, senha, idade, observacao, '
                           'reservado_unacon, reservado_convenio, atualizado_por, atualizado_em) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                           (nova, h['hora'], h['ordem'], h['paciente'], h['convenio'], h['contato'], senha, h['idade'] or '', h['observacao'],
                            h['reservado_unacon'], h['reservado_convenio'], usuario, agora()))
            else:
                # as reservas do UNACON seguem para o outro dia (o horário livre reservado continua reservado)
                livre_reservado = bool(h['reservado_unacon']) and not (h['paciente'] or '').strip()
                padrao = _trocar_etapa(a['senha_padrao']) if eh_mibi(tipo_da_agenda(db, a)) else (a['senha_padrao'] or '')
                db.execute('INSERT INTO agenda_horarios (agenda_id, hora, ordem, senha, convenio, reservado_unacon, reservado_convenio) VALUES (?,?,?,?,?,?,?)',
                           (nova, h['hora'], h['ordem'], padrao, h['convenio'] if livre_reservado else '', 1 if livre_reservado else 0,
                            h['reservado_convenio'] if livre_reservado else None))
        novas_ids.append(nova)
        copiadas.append(a['id'])
        criadas += 1
    db.commit()
    if apagar_origem:
        for aid in copiadas:
            excluir_agenda(db, aid, confirmar=True)
    if novas_ids and not pacientes:   # cópia com pacientes não tem volta automática (já há gente marcada nela)
        _guardar_desfazer({'apagar_agendas': novas_ids})
    for aid in novas_ids:
        for h in db.execute("SELECT id FROM agenda_horarios WHERE agenda_id=? AND TRIM(paciente)<>''", (aid,)).fetchall():
            _avisar_mibi(db, h['id'])
    return {'data': destino_iso, 'criadas': criadas, 'puladas': puladas, 'pacientes': pacientes, 'apagou': len(copiadas) if apagar_origem else 0}


# ------------------------------------------------------------------ convênios
# Palavras que, no nome de um exame da agenda, indicam um exame do cadastro (nome sem acento). Mais específico primeiro.
SINONIMOS_EXAME = [
    (('PARATGI', 'PARATIR'), 'PARATGI'),
    (('MIBI', 'MIOCARD'), 'MIBI'),
    (('OSSEA',), 'OSSEA'),
    (('GALIO',), 'GALIO'),
    (('TGI',), 'TGI'),
]


# colunas antigas do cadastro de convênios (exame sem acento -> coluna); servem de reserva quando não há valor na tabela nova
COLUNAS_ANTIGAS = {'MIBI': 'valor_mibi', 'OSSEA': 'valor_ossea', 'TGI': 'valor_tgi', 'PARATGI': 'valor_paratgi', 'GALIO': 'valor_galio'}


def _sem_acento(txt):
    return unicodedata.normalize('NFKD', txt or '').encode('ascii', 'ignore').decode().upper()


def exame_do_nome(nome, exames):
    """(id, nome) do exame cadastrado que corresponde ao nome do exame da agenda, ou None.
    `exames` é a lista de linhas (id, nome) da tabela exames. Vale o nome igual; depois os sinônimos conhecidos
    (ex.: MIOCARDIO = MIBI); por fim o maior nome de exame que aparece como palavra inteira (ex.: CONSULTA IODO = IODO)."""
    s = _sem_acento(nome).strip()
    por_nome = {_sem_acento(e['nome']).strip(): e for e in exames}
    if s in por_nome:
        e = por_nome[s]
        return e['id'], e['nome']
    for chaves, alvo in SINONIMOS_EXAME:
        if any(k in s for k in chaves) and alvo in por_nome:
            e = por_nome[alvo]
            return e['id'], e['nome']
    for chave in sorted(por_nome, key=len, reverse=True):
        if chave and re.search(r'(?<![A-Z0-9])%s(?![A-Z0-9])' % re.escape(chave), s):
            e = por_nome[chave]
            return e['id'], e['nome']
    return None


def convenios_ativos(db):
    return [r['nome'] for r in db.execute('SELECT nome FROM convenios WHERE ativo=1 ORDER BY nome COLLATE NOCASE')]


def convenio_canonico(db, valor):
    """Nome do convênio cadastrado (sem diferenciar maiúsculas), '' se vazio, ou None se não existe."""
    if not valor:
        return ''
    r = db.execute('SELECT nome FROM convenios WHERE ativo=1 AND nome=? COLLATE NOCASE', (valor,)).fetchone()
    return r['nome'] if r else None


# ------------------------------------------------------------------ financeiro da agenda (repasse médico)
ETAPAS_MIBI = ('Estresse', 'Repouso', 'Protocolo')


def financeiro(db, de, ate, pct, exame='', tipos=(), dias=()):
    """Pacientes atendidos no período (status VEIO ou RETORNO), com o valor do convênio para o tipo do exame e o valor a repassar (pct %).
    Quem foi remarcado e veio na nova data conta uma vez só (a linha de origem sai via _marcar_veio_na_nova_data).
    Com `exame`, só entram os pacientes daquele exame (o repasse é feito um exame por vez). No MIBI, `tipos` (Estresse, Repouso, Protocolo) limita
    o relatório às etapas marcadas. `dias` são os weekdays do Python (0=segunda ... 6=domingo) da data do exame; vazio = todos os dias."""
    cadastro = {r['nome'].casefold(): r for r in db.execute('SELECT * FROM convenios')}
    exames_cad = db.execute('SELECT id, nome FROM exames').fetchall()
    valores = {(r['convenio_id'], r['exame_id']): float(r['valor']) for r in db.execute('SELECT * FROM convenio_valores')}
    exame = _limpar(exame, 80)
    tipos = [t for t in ETAPAS_MIBI if t.casefold() in {str(x).strip().casefold() for x in (tipos or ())}] if eh_mibi(exame) else []
    dias = sorted({int(d) for d in (dias or ()) if str(d).strip().isdigit() and 0 <= int(d) <= 6})
    # entram pacientes atendidos: status VEIO ou RETORNO; o exame é o cadastrado e vinculado à agenda (o nome da agenda não conta)
    linhas = []
    for r in db.execute("SELECT h.paciente, h.convenio, h.senha, h.status, h.remarcado_para, a.exame, a.exame_id, a.data, h.hora FROM agenda_horarios h "
                        "JOIN agenda_exames a ON a.id=h.agenda_id WHERE a.data BETWEEN ? AND ? AND h.status IN ('VEIO','RETORNO') AND TRIM(h.paciente)<>'' "
                        "ORDER BY a.data, h.hora, a.exame, h.id", (de.isoformat(), ate.isoformat())):
        cad_ex = next(((e['id'], e['nome']) for e in exames_cad if e['id'] == r['exame_id']), None) or exame_do_nome(r['exame'], exames_cad)
        if exame and not (cad_ex and cad_ex[1].casefold() == exame.casefold()):
            continue
        if tipos and (r['senha'] or '').strip().casefold() not in {t.casefold() for t in tipos}:
            continue
        if dias and date.fromisoformat(r['data']).weekday() not in dias:
            continue
        linhas.append({'paciente': r['paciente'], 'convenio': r['convenio'], 'senha': r['senha'], 'status': r['status'], 'exame': r['exame'],
                       'remarcado_para': r['remarcado_para'], 'exame_cad': cad_ex[1] if cad_ex else '', 'tipo_cad': cad_ex, 'data': r['data'], 'hora': r['hora'],
                       'mibi': eh_mibi(cad_ex[1] if cad_ex else r['exame'])})
    _marcar_veio_na_nova_data(db, linhas)   # RETORNO remarcado que veio na nova data não conta de novo (veio_depois)
    linhas = [l for l in linhas if not l.get('veio_depois')]
    if not tipos:   # MIBI de duas etapas (Repouso e Estresse do mesmo paciente) é um exame só; o Protocolo já é um MIBI completo
        _unir_etapas_mibi(linhas)
        linhas = [l for l in linhas if not l.get('etapa2')]
    itens, grupos = [], {}
    for r in linhas:
        conv = (r['convenio'] or '').strip()
        tipo = r['tipo_cad']
        cad = cadastro.get(conv.casefold())
        valor = valores.get((cad['id'], tipo[0])) if cad and tipo else None
        if valor is None and cad and tipo and COLUNAS_ANTIGAS.get(_sem_acento(tipo[1])) and cad[COLUNAS_ANTIGAS[_sem_acento(tipo[1])]] is not None:
            valor = float(cad[COLUNAS_ANTIGAS[_sem_acento(tipo[1])]])   # valor antigo (importação do sistema anterior)
        v = valor or 0.0
        rep = round(v * pct / 100, 2)
        rotulo_tipo = tipo[1] if tipo else '—'
        # etapas MIBI realizadas por este paciente: a do lançamento e, no par Repouso+Estresse, a da outra linha unida
        marcadas = {(r['senha'] or '').strip().casefold(), (r.get('etapa_par') or '').strip().casefold()} if r['mibi'] else set()
        etapas = [t for t in ETAPAS_MIBI if t.casefold() in marcadas]
        itens.append({'n': len(itens) + 1, 'paciente': r['paciente'], 'convenio': conv or '—', 'exame': r['exame'],
                      'tipo': rotulo_tipo, 'etapa': (r['senha'] or '').strip(), 'etapas': etapas, 'mibi': r['mibi'], 'data': r['data'], 'hora': r['hora'],
                      'valor': v, 'repasse': rep, 'sem_valor': valor is None})
        g = grupos.setdefault((conv or '—', rotulo_tipo), {'convenio': conv or '—', 'tipo': rotulo_tipo, 'qtd': 0, 'valor': 0.0})
        g['qtd'] += 1
        g['valor'] += v
    resumo = [dict(g, valor=round(g['valor'], 2)) for _, g in sorted(grupos.items(), key=lambda kv: (kv[0][0].casefold(), kv[0][1]))]
    for n, i in enumerate(itens, 1):   # Nº = posição no relatório, 1..N, depois de todos os filtros e exclusões
        i['n'] = n
    return {'de': de.isoformat(), 'ate': ate.isoformat(), 'pct': pct, 'exame': exame, 'tipos': tipos, 'dias': dias, 'itens': itens, 'resumo': resumo,
            'tem_mibi': any(i['mibi'] for i in itens), 'qtd': len(itens), 'total_valor': round(sum(i['valor'] for i in itens), 2),
            'total_repasse': round(sum(i['repasse'] for i in itens), 2),
            'sem_valor': sum(1 for i in itens if i['sem_valor'])}


# ------------------------------------------------------------------ lista de espera
def espera_listar(db):
    return [dict(r) for r in db.execute("SELECT id, exame, nome, convenio, contato, observacao, criado_em, criado_por "
                                        "FROM agenda_espera WHERE status='AGUARDANDO' ORDER BY id")]


def espera_adicionar(db, f, usuario):
    nome = _limpar(f.get('nome'), 120)
    if not nome:
        raise ErroAgenda('Informe o nome do paciente da lista de espera.')
    d = _Desfazer(db)
    novo = db.execute('INSERT INTO agenda_espera (exame, nome, convenio, contato, observacao, criado_por, criado_em) VALUES (?,?,?,?,?,?,?)',
                      (_limpar(f.get('exame'), 80), nome, _limpar(f.get('convenio'), 60), _limpar(f.get('contato'), 40),
                       _limpar(f.get('observacao'), 300), usuario, agora())).lastrowid
    d.concluir(agenda_espera=[novo])
    db.commit()


def espera_excluir(db, eid):
    d = _Desfazer(db, agenda_espera=[eid])
    db.execute('DELETE FROM agenda_espera WHERE id=?', (eid,))
    d.concluir()
    db.commit()


def espera_encaixar(db, eid, hid, usuario):
    e = db.execute("SELECT * FROM agenda_espera WHERE id=? AND status='AGUARDANDO'", (eid,)).fetchone()
    if not e:
        raise ErroAgenda('Esta pessoa já saiu da lista de espera. Atualize a página.')
    d = _linha(db, hid)
    if (d['paciente'] or '').strip():
        raise ErroAgenda('O horário escolhido já foi preenchido. Escolha outro.')
    _checar_reserva(d, e['convenio'])
    desf = _Desfazer(db, agenda_horarios=[hid], agenda_espera=[eid])
    db.execute("UPDATE agenda_horarios SET paciente=?, convenio=?, contato=?, observacao=?, status='AGENDADO', remarcado_para=NULL, "
               'reservado_unacon=?, reservado_convenio=?, atualizado_por=?, atualizado_em=? WHERE id=?',
               (e['nome'], e['convenio'], e['contato'], e['observacao'], *_reserva_do_destino(d, e['convenio']),
                usuario, agora(), hid))
    db.execute("UPDATE agenda_espera SET status='ENCAIXADO', encaixado_em=? WHERE id=?", (agora(), eid))
    desf.concluir()
    db.commit()
    return {'data': d['dia']}


# ------------------------------------------------------------------ relatório
def faltas(db, de, ate, exame=''):
    """Pacientes que faltaram no período, agrupados por exame, com o número para contato (WhatsApp)."""
    params = [de.isoformat(), ate.isoformat()]
    filtro = ''
    if exame:
        filtro = ' AND a.exame=? COLLATE NOCASE'
        params.append(exame)
    linhas = db.execute("SELECT h.id, h.hora, h.paciente, h.convenio, h.contato, h.observacao, a.exame, a.data "
                        "FROM agenda_horarios h JOIN agenda_exames a ON a.id=h.agenda_id "
                        "WHERE a.data BETWEEN ? AND ? AND h.status='FALTOU' AND TRIM(h.paciente)<>''" + filtro +
                        " ORDER BY a.exame COLLATE NOCASE, a.data, h.hora, h.id", params).fetchall()
    grupos = {}
    for r in linhas:
        digitos = primeiro_telefone(r['contato'])
        if digitos.startswith('55') and len(digitos) == 13:
            digitos = digitos[2:]
        grupos.setdefault(r['exame'], []).append({
            'id': r['id'], 'data': r['data'], 'hora': r['hora'], 'paciente': r['paciente'], 'convenio': r['convenio'] or '—',
            'contato': r['contato'] or '', 'wa': ('55' + digitos) if len(digitos) in (10, 11) else '', 'exame': r['exame']})
    return {'de': de.isoformat(), 'ate': ate.isoformat(), 'exame': exame, 'total': len(linhas),
            'grupos': [{'exame': e, 'itens': itens, 'total': len(itens)} for e, itens in grupos.items()]}


def resgates(db, de, ate):
    """Quantos pacientes cada usuário resgatou no período (reagendados e desistências), com a lista de cada um."""
    linhas = db.execute("SELECT h.resgatado_por AS usuario, h.status, h.resgatado_em, h.paciente, h.hora, a.exame, a.data "
                        "FROM agenda_horarios h JOIN agenda_exames a ON a.id=h.agenda_id "
                        "WHERE h.resgatado_por IS NOT NULL AND h.resgatado_por<>'' AND h.status IN ('RESGATADO','DESISTIU') "
                        "AND substr(h.resgatado_em,1,10) BETWEEN ? AND ? "
                        "ORDER BY h.resgatado_por COLLATE NOCASE, h.resgatado_em, h.id", (de.isoformat(), ate.isoformat())).fetchall()
    por_usuario = {}
    for r in linhas:
        u = por_usuario.setdefault(r['usuario'], {'usuario': r['usuario'], 'total': 0, 'reagendados': 0, 'desistiram': 0, 'itens': []})
        u['total'] += 1
        if r['status'] == 'RESGATADO':
            u['reagendados'] += 1
        else:
            u['desistiram'] += 1
        u['itens'].append({'paciente': r['paciente'], 'exame': r['exame'], 'data': r['data'], 'hora': r['hora'],
                           'status': ROTULOS[r['status']], 'em': r['resgatado_em'] or ''})
    usuarios = sorted(por_usuario.values(), key=lambda x: (-x['total'], x['usuario'].casefold()))
    return {'de': de.isoformat(), 'ate': ate.isoformat(), 'total': len(linhas),
            'reagendados': sum(u['reagendados'] for u in usuarios), 'desistiram': sum(u['desistiram'] for u in usuarios),
            'usuarios': usuarios}


def _unir_etapas_mibi(linhas, janela_dias=30):
    """No MIBI o exame de duas etapas (Repouso e Estresse, em dias diferentes) é UM exame no relatório do período: a segunda etapa do mesmo
    paciente (até `janela_dias` depois) recebe `etapa2` e não entra nos totais; vale VEIO se qualquer etapa veio. Protocolo (as duas etapas no mesmo
    dia) já é um exame só e não é unido a nada. As linhas precisam estar em ordem de data."""
    abertas = {}   # (exame, paciente) -> {'Repouso'|'Estresse': linha ainda sem par}
    for l in linhas:
        etapa = (l.get('senha') or '').strip().casefold()
        tipo = l.get('exame_cad') or l['exame']
        if etapa not in ('repouso', 'estresse') or not eh_mibi(tipo):
            continue
        chave = (tipo.casefold(), _chave_nome(l['paciente']))
        outra = 'estresse' if etapa == 'repouso' else 'repouso'
        par = abertas.get(chave, {}).get(outra)
        if par and 0 <= (date.fromisoformat(l['data']) - date.fromisoformat(par['data'])).days <= janela_dias:
            l['etapa2'] = True
            par['par'] = True
            par['etapa_par'] = l.get('senha')   # a etapa da outra linha também conta no item principal (coluna R/E do relatório)
            if l['status'] in ('VEIO', 'RETORNO') or par['status'] in ('VEIO', 'RETORNO'):
                par['status_final'] = 'VEIO'
            abertas[chave].pop(outra)
        else:
            abertas.setdefault(chave, {})[etapa] = l


_ATIVOS = ('AGENDADO', 'VEIO', 'RETORNO')


def _etapas_ativas(db, desde_iso=None):
    """Linhas MIBI de Repouso/Estresse com paciente ainda valendo (agendado ou veio), em ordem de data."""
    sql = ("SELECT h.id, h.hora, h.paciente, h.contato, h.convenio, h.senha, h.status, a.data, a.exame, ex.nome AS exame_cad FROM agenda_horarios h "
           "JOIN agenda_exames a ON a.id=h.agenda_id LEFT JOIN exames ex ON ex.id=a.exame_id WHERE TRIM(h.paciente)<>'' AND h.senha IN ('Repouso','Estresse') "
           "AND h.status IN ('AGENDADO','VEIO','RETORNO')" + (' AND a.data>=?' if desde_iso else '') + ' ORDER BY a.data, h.hora, h.id')
    return [l for l in (dict(r) for r in db.execute(sql, (desde_iso,) if desde_iso else ())) if eh_mibi(l['exame_cad'] or l['exame'])]


def mibi_etapas(db, de, ate, exame='', quer=None, nome_cad=None):
    """Exames de duas etapas: quantos pacientes concluíram (Repouso e Estresse marcados) e quem ficou PENDENTE, isto é, só tem uma das etapas
    marcada, com os dados para o reagendamento. Só entram etapas cuja data cai no período."""
    linhas = _etapas_ativas(db, (de - timedelta(days=30)).isoformat())
    _unir_etapas_mibi(linhas)
    no_periodo = [l for l in linhas if de.isoformat() <= l['data'] <= ate.isoformat() and (not exame or (quer(l['exame_cad'] or nome_cad(l['exame'])) if quer else (l['exame_cad'] or l['exame']).casefold() == exame.casefold()))]
    concluidos = sum(1 for l in no_periodo if l.get('par'))
    pend = [{'id': l['id'], 'paciente': l['paciente'], 'etapa': l['senha'], 'falta': 'Estresse' if l['senha'] == 'Repouso' else 'Repouso',
             'data': l['data'], 'hora': l['hora'], 'status': l['status'], 'contato': l['contato'] or '', 'convenio': l['convenio'] or '—', 'exame': l['exame']}
            for l in no_periodo if not l.get('par') and not l.get('etapa2')]
    return {'concluidos': concluidos, 'pendentes': pend}


def _anotar_outra_etapa(db, r, obs, ignorar):
    """Na observação da linha remarcada: quando é (ou que ainda não foi marcada) a outra etapa do MIBI. O texto continua editável."""
    etapa = (r['senha'] or '').strip().capitalize()
    if etapa not in ('Repouso', 'Estresse') or not eh_mibi(r['exame_tipo']):
        return obs
    outra = 'Estresse' if etapa == 'Repouso' else 'Repouso'
    chave = _chave_nome(r['paciente'])
    cand = [l for l in _etapas_ativas(db) if l['senha'] == outra and _chave_nome(l['paciente']) == chave and l['id'] not in ignorar]
    if cand:
        alvo = min(cand, key=lambda l: abs((date.fromisoformat(l['data']) - date.fromisoformat(r['dia'])).days))
        txt = '%s em %s %s' % (outra, util.data_br(alvo['data']), alvo['hora'])
    else:
        txt = '%s ainda não agendado' % outra
    return _limpar(txt + (' | ' + obs if obs else ''), CAMPOS['observacao'])


def exames_do_cadastro(db):
    """Nomes dos exames cadastrados (e ativos), na ordem do cadastro: é a lista do filtro dos relatórios, no lugar dos nomes das agendas."""
    return [r['nome'] for r in db.execute('SELECT nome FROM exames WHERE ativo=1 ORDER BY ordem, nome COLLATE NOCASE')]


SEM_CADASTRO = '(sem exame cadastrado)'


def _novo():
    return {'marcados': 0, 'AGENDADO': 0, 'VEIO': 0, 'FALTOU': 0, 'RETORNO': 0, 'RESGATADO': 0, 'DESISTIU': 0, 'chegou': 0}


def _com_taxas(b):
    base = b['VEIO'] + b['FALTOU']
    b['taxa_falta'] = round(100.0 * b['FALTOU'] / base, 1) if base else None
    b['taxa_comparecimento'] = round(100.0 * b['VEIO'] / base, 1) if base else None
    return b


def _marcar_veio_na_nova_data(db, linhas):
    """Quem foi remarcado e veio na nova marcação conta uma vez só: a presença fica na nova data e a linha de origem recebe `veio_depois`
    (segue em Retornos, mas não soma em Vieram). A ligação vem do texto de `remarcado_para` ('dd/mm/aaaa HH:MM · agenda') e do nome do paciente.
    Outra etapa do MIBI é outro exame e não entra aqui (quem cuida dela é _unir_etapas_mibi)."""
    origens = [l for l in linhas if l['status'] == 'RETORNO' and (l.get('remarcado_para') or '').strip()]
    if not origens:
        return
    por_dia = {}
    for r in db.execute("SELECT a.data, a.exame, h.hora, h.paciente, h.senha, h.status, h.remarcado_para FROM agenda_horarios h JOIN agenda_exames a ON a.id=h.agenda_id "
                        "WHERE a.data>=? AND TRIM(h.paciente)<>'' AND h.status IN ('VEIO','RETORNO')", (min(l['data'] for l in origens),)):
        por_dia.setdefault((r['data'], _chave_nome(r['paciente'])), []).append(dict(r))

    def veio_depois(l, saltos=10):
        quando, _, agenda = (l.get('remarcado_para') or '').partition(' · ')
        partes = quando.split()
        dia = util.para_data(partes[0]) if partes else None
        if not dia or not saltos:
            return False
        hora = partes[1] if len(partes) > 1 else ''
        etapa = (l.get('senha') or '').strip().casefold()
        for c in por_dia.get((dia.isoformat(), _chave_nome(l['paciente'])), ()):
            if (c['hora'] != hora and (c['exame'] or '').casefold() != agenda.strip().casefold()) or (c['senha'] or '').strip().casefold() != etapa:
                continue   # outro exame do mesmo paciente no dia, ou outra etapa do MIBI
            if c['status'] == 'VEIO' or (c['status'] == 'RETORNO' and veio_depois(c, saltos - 1)):
                return True
        return False

    for l in origens:
        l['veio_depois'] = veio_depois(l)


def _agregar(db, de, ate, exame=''):
    """Números do período por exame CADASTRADO (o vinculado à agenda), tudo vindo da agenda: marcados, vieram, faltaram, remarcaram e ainda agendados.
    Retorno conta como veio, uma vez só: se o paciente veio na nova marcação, a presença fica nela (RETORNO segue informando quantos são).
    No MIBI, Repouso e Estresse do mesmo paciente contam como um exame só e o Protocolo como um MIBI completo."""
    cad = db.execute('SELECT id, nome FROM exames').fetchall()
    ini, fim = de.isoformat(), ate.isoformat()
    alvo = _limpar(exame, 80).casefold()

    def nome_cad(exame_id, nome_agenda):
        for e in cad:
            if exame_id and e['id'] == exame_id:
                return e['nome']
        r = exame_do_nome(nome_agenda, cad)
        return r[1] if r else SEM_CADASTRO

    def quer(nome):
        return not alvo or nome.casefold() == alvo

    vagas = sum(r[2] for r in db.execute('SELECT a.exame, a.exame_id, COUNT(*) FROM agenda_horarios h JOIN agenda_exames a ON a.id=h.agenda_id '
                                          'WHERE a.data BETWEEN ? AND ? GROUP BY a.exame, a.exame_id', (ini, fim)) if quer(nome_cad(r[1], r[0])))
    linhas = [dict(r, exame_cad=nome_cad(r['exame_id'], r['exame'])) for r in db.execute(
        'SELECT a.data, a.exame, a.exame_id, h.convenio, h.status, h.paciente, h.senha, h.chegou, h.remarcado_para FROM agenda_horarios h JOIN agenda_exames a ON a.id=h.agenda_id '
        "WHERE a.data BETWEEN ? AND ? AND TRIM(h.paciente)<>'' ORDER BY a.data, h.hora, h.id", (ini, fim))]
    linhas = [l for l in linhas if quer(l['exame_cad'])]
    _unir_etapas_mibi(linhas)
    _marcar_veio_na_nova_data(db, linhas)
    geral, por_exame, por_convenio, por_dia = _novo(), {}, {}, {}
    for l in linhas:
        st = l['status'] if l['status'] in STATUS else 'AGENDADO'
        blocos = [(por_dia.setdefault(l['data'], _novo()), st)]   # o dia mostra a agenda do dia, linha a linha
        if not l.get('etapa2'):   # Repouso + Estresse do mesmo paciente contam como um exame só nos totais do período
            st = l.get('status_final', st)
            blocos += [(geral, st), (por_exame.setdefault(l['exame_cad'], _novo()), st),
                       (por_convenio.setdefault((l['convenio'] or '').strip() or '(sem convênio)', _novo()), st)]
        for bloco, s in blocos:
            bloco['marcados'] += 1
            bloco[s] += 1
            bloco['VEIO'] += 1 if s == 'RETORNO' and not l.get('veio_depois') else 0   # no relatório, retorno conta como veio, uma vez só; 'RETORNO' segue informando quantos são
            bloco['chegou'] += 1 if l.get('chegou') else 0

    def lista(mapa):
        return [dict(_com_taxas(v), nome=k) for k, v in sorted(mapa.items(), key=lambda kv: (-kv[1]['marcados'], str(kv[0])))]

    geral = _com_taxas(geral)
    geral['vagas'] = vagas
    geral['livres'] = max(0, vagas - geral['marcados'])
    return {'geral': geral, 'por_exame': lista(por_exame), 'por_convenio': lista(por_convenio),
            'por_dia': [dict(_com_taxas(v), nome=k) for k, v in sorted(por_dia.items())], 'nome_cad': lambda txt: nome_cad(None, txt), 'quer': quer}


def relatorio(db, de, ate, exame=''):
    """Totais do período por exame cadastrado: marcados, vieram, faltaram, remarcaram e ainda agendados.
    Traz também o painel (`dashboard`) com todos os exames do período, qualquer que seja o filtro."""
    exame = _limpar(exame, 80)
    a = _agregar(db, de, ate, exame)
    todos = a if not exame else _agregar(db, de, ate, '')
    pico = {}
    for r in db.execute('SELECT h.hora FROM agenda_horarios h JOIN agenda_exames a ON a.id=h.agenda_id '
                        "WHERE a.data BETWEEN ? AND ? AND TRIM(h.paciente)<>''", (de.isoformat(), ate.isoformat())):
        pico[(r['hora'] or '')[:2]] = pico.get((r['hora'] or '')[:2], 0) + 1
    dash = {'geral': todos['geral'], 'por_exame': todos['por_exame'], 'por_dia': todos['por_dia'], 'por_convenio': todos['por_convenio'][:8],
            'por_hora': [{'nome': h + ' h', 'n': n} for h, n in sorted(pico.items()) if h]}
    return {'de': de.isoformat(), 'ate': ate.isoformat(), 'exame': exame, 'mibi': mibi_etapas(db, de, ate, exame, a['quer'], a['nome_cad']),
            'geral': a['geral'], 'por_exame': a['por_exame'], 'por_convenio': a['por_convenio'], 'por_dia': a['por_dia'], 'dashboard': dash}


# ------------------------------------------------------------------ duplicidade de paciente no mesmo dia
def _chave_nome(txt):
    return ' '.join((txt or '').upper().split())


def duplicados(db, dia):
    """Grupos de linhas do dia com o mesmo nome ou o mesmo telefone (ignora remarcados e desistências).
    Devolve [(descrição, [ids])]."""
    linhas = db.execute("SELECT h.id, h.paciente, h.contato FROM agenda_horarios h JOIN agenda_exames a ON a.id=h.agenda_id "
                        "WHERE a.data=? AND TRIM(h.paciente)<>'' AND h.status NOT IN ('RETORNO','DESISTIU') ORDER BY h.id", (dia,)).fetchall()
    por_nome, por_tel = {}, {}
    for r in linhas:
        por_nome.setdefault(_chave_nome(r['paciente']), []).append(r)
        tel = primeiro_telefone(r['contato'])
        if tel:
            por_tel.setdefault(tel, []).append(r)
    saida = []
    for grupo in list(por_nome.values()) + list(por_tel.values()):
        if len(grupo) > 1:
            nomes = sorted({_chave_nome(x['paciente']) for x in grupo})
            motivo = 'mesmo nome' if len(nomes) == 1 else 'mesmo telefone'
            saida.append(('%s (%s)' % (' / '.join(nomes), motivo), [x['id'] for x in grupo]))
    return saida


def avisar_duplicados(db, dia):
    """Pelo AVISOS DO SISTEMA, pergunta (Sim/Não) a quem usa a agenda se quer abrir o dia para corrigir. Um aviso por caso."""
    from . import avisos, modulos
    de = avisos.sistema_id(db)
    if de is None:
        return 0
    destinos = [u['id'] for u in db.execute('SELECT id, admin, modulos, bh_funcionario_id FROM usuarios WHERE ativo=1 AND COALESCE(sistema,0)=0')
                if u['admin'] or 'agenda' in modulos.modulos_do_usuario(u)]
    enviados = 0
    for descricao, ids in duplicados(db, dia):
        url = '/agenda?data=%s&destacar=%s' % (dia, ','.join(str(i) for i in sorted(ids)))
        if db.execute("SELECT 1 FROM chat_mensagens WHERE acao='AGENDA_VER' AND acao_url=? LIMIT 1", (url,)).fetchone():
            continue   # esse caso já foi avisado
        corpo = ('Possível duplicidade na agenda de %s: %s, %d linhas. Quer abrir a agenda para corrigir?'
                 % (dia[8:10] + '/' + dia[5:7], descricao, len(ids)))
        for uid in destinos:
            db.execute('INSERT INTO chat_mensagens (de_id, para_id, corpo, criado_em, acao, acao_url) VALUES (?,?,?,?,?,?)',
                       (de, uid, corpo, agora(), 'AGENDA_VER', url))
        enviados += 1
    db.commit()
    return enviados
