"""Comandos da NucleAI: além de tirar dúvidas, ela cumpre pedidos escritos no chat ("imprimir a agenda do dia").

Regras de segurança:
- Todo comando que FAZ alguma coisa (abrir uma tela, imprimir, gerar um arquivo, alterar algo) só roda depois de a pessoa
  responder SIM. Consultas só de leitura ("quantos atendimentos hoje?") respondem direto.
- Cada comando tem um nível de risco fixo no código:
    baixo : a maioria das pessoas pode usar (a gerência pode restringir);
    médio : por padrão só quem a gerência escolher (e a própria gerência);
    alto  : só a gerência (administração ou módulo Gerência); ninguém mais, mesmo que alguém peça.
- A pessoa também precisa ter o módulo da tela que o comando usa, e a gerência pode desligar qualquer comando.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Callable, Optional

from flask import url_for

from . import modulos
from .ajuda_busca import normalizar
from .db import agora

BAIXO, MEDIO, ALTO = 'baixo', 'medio', 'alto'
ROTULO_RISCO = {BAIXO: 'Baixo risco', MEDIO: 'Médio risco', ALTO: 'Alto risco'}
MODOS = ('todos', 'escolhidos', 'ninguem')
MODO_PADRAO = {BAIXO: 'todos', MEDIO: 'escolhidos', ALTO: 'gerencia'}
VALIDADE_MIN = 30     # um pedido de confirmação esquecido perde a validade

ESQUEMA = """
CREATE TABLE IF NOT EXISTS nucleai_cmd_config (comando TEXT PRIMARY KEY, modo TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS nucleai_cmd_acesso (comando TEXT NOT NULL, usuario_id INTEGER NOT NULL, PRIMARY KEY (comando, usuario_id));
CREATE TABLE IF NOT EXISTS nucleai_cmd_pendentes (
    id INTEGER PRIMARY KEY, usuario_id INTEGER NOT NULL, comando TEXT NOT NULL, argumentos TEXT NOT NULL DEFAULT '{}',
    estado TEXT NOT NULL DEFAULT 'PENDENTE', criado_em TEXT NOT NULL, resolvido_em TEXT
);
"""
_garantido = set()


class ErroComando(ValueError):
    """Erro mostrado à pessoa no chat."""


def garantir(db):
    from .anexos import caminho_do_banco
    chave = caminho_do_banco(db) or id(db)
    if chave in _garantido:
        return
    db.executescript(ESQUEMA)
    db.commit()
    _garantido.add(chave)


# ------------------------------------------------------------------ contexto de quem pede
class Ctx:
    def __init__(self, db, uid):
        self.db, self.uid = db, uid
        self.usuario = db.execute('SELECT * FROM usuarios WHERE id=?', (uid,)).fetchone()
        self.admin = bool(self.usuario and self.usuario['admin'])
        self.mods = modulos.modulos_do_usuario(self.usuario) if self.usuario else set()
        self.hoje = date.today()

    @property
    def gerencia(self):
        return self.admin or 'gerencia' in self.mods

    @property
    def nome(self):
        return self.usuario['usuario'] if self.usuario else ''

    def tem_modulo(self, mod):
        if mod is None:
            return True
        if mod == '__admin__':
            return self.admin
        if isinstance(mod, str):
            return self.admin or mod in self.mods
        return self.admin or any(m in self.mods for m in mod)


@dataclass
class Comando:
    chave: str
    nome: str
    descricao: str               # "imprimir a agenda do dia": completa "Posso ...?"
    exemplo: str                 # frase de exemplo mostrada na lista
    risco: str
    modulo: object               # módulo exigido (str, tupla de "qualquer um", ou None = livre)
    chaves: tuple                # alternativas; cada uma é uma tupla de radicais que precisam aparecer
    executar: Callable
    preparar: Optional[Callable] = None
    nao: tuple = ()              # radicais que, se aparecerem, descartam o comando
    confirmar: bool = True       # consultas só de leitura respondem direto (False)
    abre: bool = False           # o resultado abre uma tela/impressão em outra aba


def _u(ep, **kw):
    return url_for(ep, **kw)


def _imprimir_pdf(caminho):
    return _u('ajuda.imprimir_pdf', u=caminho)


def _fmt_data(iso):
    return '%s/%s/%s' % (iso[8:10], iso[5:7], iso[:4])


def _moeda(v):
    from . import util
    return util.moeda(v or 0)


# ------------------------------------------------------------------ comandos (cada um devolve {'texto':..., 'url':...})
def c_agenda_imprimir(dias):
    def f(ctx, a):
        d = (ctx.hoje + timedelta(days=dias)).isoformat()
        return {'texto': 'Abrindo a agenda de %s para imprimir.' % _fmt_data(d), 'url': _imprimir_pdf(_u('agenda.imprimir', data=d))}
    return f


def c_agenda_abrir(ctx, a):
    return {'texto': 'Abrindo a agenda de exames.', 'url': _u('agenda.pagina')}


def c_agenda_resumo(ctx, a):
    d = ctx.hoje.isoformat()
    linhas = ctx.db.execute("SELECT h.status, COUNT(*) AS n FROM agenda_horarios h JOIN agenda_exames a ON a.id=h.agenda_id "
                            "WHERE a.data=? AND TRIM(h.paciente)<>'' GROUP BY h.status", (d,)).fetchall()
    n = {r['status']: r['n'] for r in linhas}
    total = sum(n.values())
    if not total:
        return {'texto': 'Hoje (%s) ainda não há pacientes marcados na agenda.' % _fmt_data(d)}
    return {'texto': 'Agenda de hoje (%s): %d paciente(s) marcado(s) · %d já vieram · %d faltaram · %d ainda agendados.'
            % (_fmt_data(d), total, n.get('VEIO', 0), n.get('FALTOU', 0), n.get('AGENDADO', 0))}


def c_guias_imprimir(ctx, a):
    d = ctx.hoje.isoformat()
    return {'texto': 'Abrindo o protocolo de guias de hoje para imprimir.', 'url': _u('atend.guias', de=d, ate=d, imprimir=1, auto=1)}


def c_caixa_imprimir(ctx, a):
    d = ctx.hoje.isoformat()
    return {'texto': 'Abrindo o caixa de hoje para imprimir.', 'url': _u('atend.caixa', de=d, ate=d, imprimir=1, auto=1)}


def c_movimento_total(ctx, a):
    from . import movimento
    s = movimento.sessao_de_hoje(ctx.db, ctx.nome, ctx.hoje.isoformat())
    if not s:
        return {'texto': 'Você ainda não abriu o seu caixa hoje.'}
    r = ctx.db.execute("SELECT COUNT(*) AS n, COALESCE(SUM(valor),0) AS total FROM caixa WHERE sessao_id=? AND status='PAGO'", (s['id'],)).fetchone()
    return {'texto': 'O seu caixa de hoje está %s: %d recebimento(s), total de R$ %s.' % ('aberto' if s['status'] == 'ABERTO' else 'fechado', r['n'], _moeda(r['total']))}


def c_atendimento_novo(ctx, a):
    return {'texto': 'Abrindo o lançamento de atendimento.', 'url': _u('atend.novo')}


def c_atendimentos_hoje(ctx, a):
    d = ctx.hoje.isoformat()
    return {'texto': 'Abrindo os atendimentos de hoje.', 'url': _u('atend.lista', de=d, ate=d)}


def c_atendimentos_contar(ctx, a):
    n = ctx.db.execute('SELECT COUNT(*) FROM atendimentos WHERE data=?', (ctx.hoje.isoformat(),)).fetchone()[0]
    return {'texto': 'Hoje (%s) foram lançados %d atendimento(s).' % (_fmt_data(ctx.hoje.isoformat()), n)}


def c_doses_imprimir(ctx, a):
    return {'texto': 'Abrindo as doses de hoje para imprimir.', 'url': _u('med.lista', dia=ctx.hoje.isoformat(), imprimir=1, auto=1)}


def c_dose_agendar(ctx, a):
    return {'texto': 'Abrindo o agendamento de medicamento.', 'url': _u('med.editar')}


def c_laudos_abrir(ctx, a):
    return {'texto': 'Abrindo o mapa de laudos.', 'url': _u('laudo.quadro')}


def c_laudos_pendentes(ctx, a):
    from . import qualidade_dados as qd
    d = qd.laudos(ctx.db, ctx.hoje - timedelta(days=30), ctx.hoje)
    return {'texto': 'Nos últimos 30 dias há %d laudo(s) atrasado(s) (mais de 24 h sem liberar) e %d já liberado(s).' % (d['pendentes'], d['liberados'])}


def c_exames_realizados(ctx, a):
    return {'texto': 'Abrindo os exames realizados.', 'url': _u('lanc.lista')}


def c_cliente_buscar(ctx, a):
    return {'texto': 'Procurando o cliente «%s».' % a['nome'], 'url': _u('cad.clientes', q=a['nome'])}


def p_cliente_buscar(ctx, texto):
    sobra = [p for p in normalizar(texto).split() if p not in {
        'buscar', 'busca', 'procurar', 'procura', 'achar', 'encontrar', 'localizar', 'pesquisar', 'cliente', 'clientes', 'paciente', 'pacientes',
        'de', 'da', 'do', 'o', 'a', 'por', 'pelo', 'pela', 'abrir', 'ver', 'mostrar', 'cadastro', 'nome', 'um', 'uma', 'quero', 'preciso',
        'favor', 'pode', 'me', 'para', 'pra', 'no', 'na', 'sistema'}]
    if not sobra:
        raise ErroComando('Qual é o nome do cliente? Escreva, por exemplo: buscar cliente Maria Silva.')
    nome = ' '.join(sobra).upper()
    return {'nome': nome}, 'Posso procurar o cliente «%s»?' % nome


def c_mensagens(ctx, a):
    return {'texto': 'Abrindo as mensagens.', 'url': _u('chat.conversa')}


def c_senha(ctx, a):
    return {'texto': 'Abrindo a troca de senha.', 'url': _u('auth.minha_senha')}


def c_documentos(ctx, a):
    return {'texto': 'Abrindo atestados e declarações.', 'url': _u('doc.indice')}


def c_contas_consulta(ctx, a):
    d = ctx.hoje.isoformat()
    v = ctx.db.execute("SELECT COUNT(*) AS n, COALESCE(SUM(valor),0) AS t FROM contas WHERE status='ABERTO' AND vencimento<?", (d,)).fetchone()
    h = ctx.db.execute("SELECT COUNT(*) AS n, COALESCE(SUM(valor),0) AS t FROM contas WHERE status='ABERTO' AND vencimento=?", (d,)).fetchone()
    return {'texto': 'Contas a pagar: %d vencida(s) em aberto (R$ %s) e %d vencendo hoje (R$ %s).' % (v['n'], _moeda(v['t']), h['n'], _moeda(h['t']))}


def c_contas_abrir(ctx, a):
    return {'texto': 'Abrindo as contas a pagar.', 'url': _u('fin.contas')}


def c_faturamento(ctx, a):
    return {'texto': 'Abrindo o faturamento.', 'url': _u('fat.lista')}


def c_faltas(ctx, a):
    return {'texto': 'Abrindo as faltas e o reagendamento.', 'url': _u('agenda.faltas')}


def c_relatorio_mes(ctx, a):
    return {'texto': 'Abrindo o relatório de atendimentos do mês.', 'url': _u('fin.relatorios', de=ctx.hoje.replace(day=1).isoformat(), ate=ctx.hoje.isoformat())}


def c_repasse(ctx, a):
    return {'texto': 'Abrindo o financeiro da agenda (escolha o exame e o percentual).',
            'url': _u('agenda.financeiro', de=ctx.hoje.replace(day=1).isoformat(), ate=ctx.hoje.isoformat())}


def c_caixa_diario(ctx, a):
    return {'texto': 'Abrindo o caixa diário da empresa.', 'url': _u('cxd.pagina')}


def c_kpi(ctx, a):
    return {'texto': 'Abrindo os indicadores da qualidade.', 'url': _u('qual.kpi')}


def c_satisfacao_resumo(ctx, a):
    from . import pesquisa as pesq
    de, ate = (ctx.hoje - timedelta(days=29)).isoformat(), ctx.hoje.isoformat()
    ind = pesq.indicadores(ctx.db, de, ate)
    if not ind['respostas']:
        return {'texto': 'Nos últimos 30 dias ainda não chegou nenhuma resposta na pesquisa de satisfação.'}
    sat = ind['geral']['satisfacao']
    return {'texto': 'Satisfação dos últimos 30 dias: %s de respostas Ótimo ou Bom, nota média %s, %d resposta(s), %d elogio(s), %d sugestão(ões); %d ainda sem avaliação.'
            % (('%.1f%%' % sat).replace('.', ',') if sat is not None else '—', ('%.1f' % ind['media']).replace('.', ',') if ind['media'] is not None else '—',
               ind['respostas'], ind['elogios'], ind['sugestoes'], ind['pendentes'])}


def c_pesquisa_cartaz(ctx, a):
    return {'texto': 'Abrindo o cartaz da pesquisa de satisfação para imprimir.', 'url': _u('qual.satisf_cartaz', auto=1)}


def c_pesquisa_encerrar(ctx, a):
    from . import pesquisa as pesq
    pesq.garantir(ctx.db)
    pesq.definir_ativa(ctx.db, False)
    return {'texto': 'Pronto: a pesquisa de satisfação foi encerrada e não recebe mais respostas.'}


def c_pesquisa_abrir(ctx, a):
    from . import pesquisa as pesq
    pesq.garantir(ctx.db)
    pesq.definir_ativa(ctx.db, True)
    return {'texto': 'Pronto: a pesquisa de satisfação voltou a receber respostas.'}


def c_saude(ctx, a):
    return {'texto': 'Abrindo a saúde do sistema.', 'url': _u('saude.pagina')}


def c_registros(ctx, a):
    return {'texto': 'Abrindo os registros de atividades.', 'url': _u('reg.registros', de=ctx.hoje.isoformat(), ate=ctx.hoje.isoformat())}


def c_usuarios(ctx, a):
    return {'texto': 'Abrindo usuários e perfis.', 'url': _u('admin.usuarios')}


def c_backup(ctx, a):
    from .auth import registrar_acesso
    from .views_admin import fazer_backup
    nome = fazer_backup()
    registrar_acesso(ctx.nome, 'Backup', nome)
    return {'texto': 'Backup concluído: %s (sistema e anexos).' % nome}


def c_caixa_reabrir(ctx, a):
    from . import avisos, movimento
    s = movimento.reabrir(ctx.db, True, a['sessao_id'])
    dono = ctx.db.execute('SELECT id FROM usuarios WHERE usuario=?', (s['usuario'],)).fetchone()
    de = avisos.sistema_id(ctx.db)
    if dono and de is not None and dono['id'] != ctx.uid:
        ctx.db.execute('INSERT INTO chat_mensagens (de_id, para_id, corpo, criado_em) VALUES (?,?,?,?)',
                       (de, dono['id'], 'O seu caixa de %s foi reaberto por %s. Feche-o novamente quando terminar.' % (_fmt_data(s['data'])[:5], ctx.nome), agora()))
    return {'texto': 'Pronto: o caixa de %s do dia %s foi reaberto.' % (s['usuario'], _fmt_data(s['data']))}


def p_caixa_reabrir(ctx, texto):
    tokens = normalizar(texto).split()
    proprio = bool({'meu', 'minha'} & set(tokens))
    sobra = [t for t in tokens if t not in {
        'reabrir', 'reabra', 'reabre', 'abrir', 'abra', 'de', 'da', 'do', 'dos', 'o', 'a', 'caixa', 'meu', 'minha', 'fechado', 'fechei', 'fechou', 'sem', 'querer',
        'por', 'favor', 'novamente', 'outra', 'vez', 'quero', 'preciso', 'pode', 'que', 'foi', 'ele', 'ela', 'o', 'usuario', 'operador', 'um', 'uma', 'para', 'pra'}]
    if proprio or not sobra:
        if not proprio:
            raise ErroComando('De quem é o caixa? Escreva, por exemplo: reabrir o caixa de MARIA.')
        alvo = ctx.usuario
    else:
        achados = []
        for r in ctx.db.execute("SELECT id, usuario FROM usuarios WHERE ativo=1 AND COALESCE(sistema,0)=0 ORDER BY usuario"):
            nome = normalizar(r['usuario'])
            if any(t == nome or t in nome.split() or (len(t) >= 3 and nome.startswith(t)) for t in sobra):
                achados.append(r)
        if not achados:
            raise ErroComando('Não encontrei esse usuário. Escreva o nome como aparece no sistema, por exemplo: reabrir o caixa de MARIA.')
        if len(achados) > 1:
            raise ErroComando('Encontrei mais de um usuário: %s. Escreva o nome completo.' % ', '.join(r['usuario'] for r in achados[:6]))
        alvo = achados[0]
    s = ctx.db.execute("SELECT * FROM caixa_sessoes WHERE usuario=? AND status='FECHADO' AND data>=? ORDER BY data DESC, id DESC LIMIT 1",
                       (alvo['usuario'], (ctx.hoje - timedelta(days=7)).isoformat())).fetchone()
    if not s:
        raise ErroComando('%s não tem caixa fechado nos últimos 7 dias.' % alvo['usuario'])
    return {'sessao_id': s['id']}, 'Posso reabrir o caixa de %s do dia %s? Ele(a) poderá voltar a receber e terá que fechar de novo.' % (alvo['usuario'], _fmt_data(s['data']))


def c_desfazer(ctx, a):
    from . import agenda
    r = ctx.db.execute('SELECT id, acao, desfazer, desfeito_em FROM auditoria WHERE id=?', (a['rid'],)).fetchone()
    if not r or not r['desfazer'] or r['desfeito_em']:
        raise ErroComando('Essa ação já não pode ser desfeita.')
    try:
        agenda.aplicar_desfazer(ctx.db, json.loads(r['desfazer']))
    except (agenda.ErroAgenda, ValueError, KeyError) as e:
        ctx.db.rollback()
        raise ErroComando(str(e) if isinstance(e, agenda.ErroAgenda) else 'Não foi possível desfazer esta ação.')
    ctx.db.execute('UPDATE auditoria SET desfeito_em=?, desfeito_por=? WHERE id=?', (agora(), ctx.nome, r['id']))
    return {'texto': 'Pronto: desfiz «%s».' % r['acao']}


def p_desfazer(ctx, texto):
    r = ctx.db.execute('SELECT id, acao, usuario, data_hora FROM auditoria WHERE desfazer IS NOT NULL AND desfeito_em IS NULL ORDER BY id DESC LIMIT 1').fetchone()
    if not r:
        raise ErroComando('Não há nenhuma ação recente que possa ser desfeita.')
    return {'rid': r['id']}, 'Posso desfazer a última ação registrada: «%s», feita por %s às %s?' % (r['acao'], r['usuario'] or 'sistema', r['data_hora'][11:16])


# ------------------------------------------------------------------ catálogo
def _C(*a, **k):
    return Comando(*a, **k)


COMANDOS = [
    # ---------------- baixo risco
    _C('agenda_imprimir_hoje', 'Imprimir a agenda do dia', 'imprimir a agenda de hoje', 'imprimir a agenda do dia', BAIXO, ('agenda', 'agenda_leitura'),
       (('impr', 'agenda', 'hoje'), ('impr', 'agenda', 'dia'), ('impr', 'agenda')), c_agenda_imprimir(0), nao=('medicament', 'dose', 'amanha', 'depois'), abre=True),
    _C('agenda_imprimir_amanha', 'Imprimir a agenda de amanhã', 'imprimir a agenda de amanhã', 'imprimir a agenda de amanhã', BAIXO, ('agenda', 'agenda_leitura'),
       (('impr', 'agenda', 'amanha'),), c_agenda_imprimir(1), abre=True),
    _C('agenda_abrir', 'Abrir a agenda', 'abrir a agenda de exames', 'abrir a agenda', BAIXO, ('agenda', 'agenda_leitura'),
       (('abr', 'agenda'), ('mostr', 'agenda'), ('ver', 'agenda')), c_agenda_abrir, nao=('medicament', 'dose', 'impr', 'faltas', 'financ', 'relatorio'), abre=True),
    _C('agenda_resumo_hoje', 'Resumo da agenda de hoje', 'consultar a agenda de hoje', 'quantos pacientes na agenda hoje', BAIXO, ('agenda', 'agenda_leitura'),
       (('quant', 'agenda'), ('resum', 'agenda'), ('quant', 'paciente', 'hoje'), ('quant', 'paciente', 'agenda')), c_agenda_resumo, confirmar=False),
    _C('guias_imprimir_hoje', 'Imprimir as guias de hoje', 'imprimir o protocolo de guias de hoje', 'imprimir as guias de hoje', BAIXO, 'guias',
       (('impr', 'guia'), ('impr', 'protocolo')), c_guias_imprimir, abre=True),
    _C('caixa_imprimir_hoje', 'Imprimir o caixa de hoje', 'imprimir o caixa de hoje', 'imprimir o caixa de hoje', BAIXO, 'caixa',
       (('impr', 'caixa'),), c_caixa_imprimir, nao=('diario', 'movimento'), abre=True),
    _C('movimento_meu_total', 'Meu total no caixa', 'consultar o seu caixa de hoje', 'quanto recebi hoje', BAIXO, 'movimento_caixa',
       (('quant', 'receb'), ('quant', 'caixa'), ('quant', 'tenho', 'caixa')), c_movimento_total, nao=('reabr', 'impr'), confirmar=False),
    _C('atendimento_novo', 'Lançar atendimento', 'abrir o lançamento de atendimento', 'lançar um atendimento', BAIXO, 'atendimentos',
       (('lanc', 'atendiment'), ('cadastr', 'atendiment'), ('registr', 'atendiment')), c_atendimento_novo, abre=True),
    _C('atendimentos_hoje', 'Atendimentos de hoje', 'abrir os atendimentos de hoje', 'ver os atendimentos de hoje', BAIXO, 'atendimentos',
       (('abr', 'atendiment'), ('mostr', 'atendiment'), ('list', 'atendiment'), ('ver', 'atendiment')), c_atendimentos_hoje, nao=('quant', 'lanc', 'novo'), abre=True),
    _C('atendimentos_contar_hoje', 'Quantos atendimentos hoje', 'contar os atendimentos de hoje', 'quantos atendimentos hoje', BAIXO, 'atendimentos',
       (('quant', 'atendiment'),), c_atendimentos_contar, confirmar=False),
    _C('doses_imprimir_hoje', 'Imprimir as doses de hoje', 'imprimir a agenda de medicamentos de hoje', 'imprimir a agenda de medicamentos', BAIXO, 'medicamentos',
       (('impr', 'medicament'), ('impr', 'dose')), c_doses_imprimir, abre=True),
    _C('dose_agendar', 'Agendar medicamento', 'abrir o agendamento de medicamento', 'agendar medicamento', BAIXO, 'medicamentos',
       (('agend', 'medicament'), ('agend', 'dose')), c_dose_agendar, nao=('impr',), abre=True),
    _C('laudos_abrir', 'Abrir o mapa de laudos', 'abrir o mapa de laudos', 'abrir o mapa de laudos', BAIXO, 'laudos',
       (('abr', 'laudo'), ('mostr', 'laudo'), ('ver', 'laudo'), ('mapa', 'laudo')), c_laudos_abrir, nao=('quant', 'pendent', 'atrasad'), abre=True),
    _C('laudos_pendentes', 'Laudos pendentes', 'consultar os laudos atrasados', 'quantos laudos pendentes', BAIXO, 'laudos',
       (('quant', 'laudo'), ('ver', 'laudo', 'pendent'), ('ver', 'laudo', 'atrasad'), ('mostr', 'laudo', 'pendent')), c_laudos_pendentes, confirmar=False),
    _C('exames_realizados_abrir', 'Abrir os exames realizados', 'abrir os exames realizados', 'abrir os exames realizados', BAIXO, 'exames_lanc',
       (('abr', 'exame', 'realizad'), ('ver', 'exame', 'realizad'), ('mostr', 'exame', 'realizad')), c_exames_realizados, abre=True),
    _C('cliente_buscar', 'Buscar um cliente', 'procurar o cliente', 'buscar cliente Maria Silva', BAIXO, 'clientes',
       (('busc', 'client'), ('procur', 'client'), ('achar', 'client'), ('localiz', 'client'), ('busc', 'paciente'), ('procur', 'paciente')),
       c_cliente_buscar, preparar=p_cliente_buscar, abre=True),
    _C('mensagens_abrir', 'Abrir as mensagens', 'abrir as mensagens', 'abrir as mensagens', BAIXO, None,
       (('abr', 'mensagen'), ('ver', 'mensagen'), ('mostr', 'mensagen')), c_mensagens, abre=True),
    _C('senha_trocar', 'Trocar a minha senha', 'abrir a troca de senha', 'trocar a minha senha', BAIXO, None,
       (('troc', 'senha'), ('alter', 'senha'), ('mud', 'senha')), c_senha, abre=True),
    _C('documentos_abrir', 'Atestados e declarações', 'abrir atestados e declarações', 'abrir atestados', BAIXO, 'documentos',
       (('abr', 'atestado'), ('abr', 'declarac'), ('emitir', 'atestado'), ('fazer', 'atestado')), c_documentos, abre=True),
    # ---------------- médio risco
    _C('contas_consulta', 'Contas a pagar vencidas', 'consultar as contas a pagar vencidas', 'quantas contas vencidas', MEDIO, 'contas',
       (('quant', 'conta'), ('ver', 'conta', 'vencid'), ('mostr', 'conta', 'vencid')), c_contas_consulta, confirmar=False),
    _C('contas_abrir', 'Abrir contas a pagar', 'abrir as contas a pagar', 'abrir as contas a pagar', MEDIO, 'contas',
       (('abr', 'conta'), ('ver', 'conta'), ('mostr', 'conta')), c_contas_abrir, nao=('quant', 'vencid', 'vencend'), abre=True),
    _C('faturamento_abrir', 'Abrir o faturamento', 'abrir o faturamento', 'abrir o faturamento', MEDIO, 'faturamento',
       (('abr', 'faturament'), ('ver', 'faturament'), ('mostr', 'faturament')), c_faturamento, abre=True),
    _C('faltas_abrir', 'Faltas e reagendamento', 'abrir as faltas e o reagendamento', 'abrir as faltas da agenda', MEDIO, 'agenda_faltas',
       (('abr', 'falta'), ('ver', 'falta'), ('mostr', 'falta'), ('abr', 'reagend')), c_faltas, abre=True),
    _C('relatorio_atendimentos_mes', 'Relatório de atendimentos do mês', 'abrir o relatório de atendimentos do mês', 'relatório de atendimentos do mês', MEDIO, 'relatorios',
       (('abr', 'relatorio', 'atendiment'), ('ver', 'relatorio', 'atendiment'), ('mostr', 'relatorio', 'atendiment'), ('abr', 'relatorio', 'mes'), ('abr', 'relatorio')), c_relatorio_mes, abre=True),
    _C('repasse_abrir', 'Financeiro da agenda (repasse)', 'abrir o financeiro da agenda', 'abrir o repasse médico', MEDIO, 'agenda_financeiro',
       (('abr', 'repass'), ('ver', 'repass'), ('mostr', 'repass'), ('abr', 'financeiro', 'agenda')), c_repasse, abre=True),
    _C('caixa_diario_abrir', 'Caixa diário da empresa', 'abrir o caixa diário da empresa', 'abrir o caixa diário', MEDIO, 'caixa_diario',
       (('abr', 'caixa', 'diario'), ('ver', 'caixa', 'diario')), c_caixa_diario, abre=True),
    _C('kpi_abrir', 'Indicadores da qualidade', 'abrir os indicadores da qualidade', 'abrir os indicadores', MEDIO, 'qualidade_gestao',
       (('abr', 'indicador'), ('ver', 'indicador'), ('mostr', 'indicador'), ('abr', 'kpi')), c_kpi, abre=True),
    _C('satisfacao_resumo', 'Resumo da satisfação', 'consultar a satisfação dos clientes', 'como está a satisfação dos clientes', MEDIO, 'qualidade_gestao',
       (('resum', 'satisfac'), ('ver', 'satisfac'), ('mostr', 'satisfac'), ('consult', 'satisfac'), ('ver', 'resultado', 'pesquisa')), c_satisfacao_resumo, nao=('encerr', 'cartaz', 'abr', 'imprim'), confirmar=False),
    _C('pesquisa_cartaz', 'Imprimir o cartaz da pesquisa', 'imprimir o cartaz do QR Code da pesquisa de satisfação', 'imprimir o cartaz da pesquisa', MEDIO, 'qualidade_gestao',
       (('impr', 'cartaz'), ('impr', 'qr'), ('impr', 'pesquisa')), c_pesquisa_cartaz, abre=True),
    _C('pesquisa_encerrar', 'Encerrar a pesquisa de satisfação', 'encerrar a pesquisa de satisfação (ela deixa de receber respostas)', 'encerrar a pesquisa de satisfação', MEDIO, 'qualidade_gestao',
       (('encerr', 'pesquisa'), ('parar', 'pesquisa'), ('desativ', 'pesquisa'), ('fech', 'pesquisa')), c_pesquisa_encerrar),
    _C('pesquisa_reabrir', 'Reabrir a pesquisa de satisfação', 'reabrir a pesquisa de satisfação (ela volta a receber respostas)', 'reabrir a pesquisa de satisfação', MEDIO, 'qualidade_gestao',
       (('reabr', 'pesquisa'), ('ativar', 'pesquisa'), ('liber', 'pesquisa'), ('abr', 'pesquisa')), c_pesquisa_abrir, nao=('encerr', 'desativ', 'impr')),
    # ---------------- alto risco (só a gerência)
    _C('backup_agora', 'Fazer backup agora', 'fazer um backup do sistema agora', 'fazer backup', ALTO, ('backup', 'gerencia'),
       (('faz', 'backup'), ('gerar', 'backup'), ('criar', 'backup'), ('realiz', 'backup')), c_backup, nao=('restaur', 'abr')),
    _C('caixa_reabrir', 'Reabrir um caixa fechado', 'reabrir um caixa fechado sem querer', 'reabrir o caixa de MARIA', ALTO, 'gerencia',
       (('reabr', 'caixa'),), c_caixa_reabrir, preparar=p_caixa_reabrir),
    _C('desfazer_ultima', 'Desfazer a última ação', 'desfazer a última ação registrada', 'desfazer a última ação', ALTO, 'gerencia',
       (('desfaz', 'ultima'), ('desfaz', 'acao')), c_desfazer, preparar=p_desfazer),
    _C('saude_abrir', 'Saúde do sistema', 'abrir a saúde do sistema', 'abrir a saúde do sistema', ALTO, 'gerencia',
       (('abr', 'saude'), ('ver', 'saude'), ('saude', 'sistema')), c_saude, abre=True),
    _C('registros_abrir', 'Registros de atividades de hoje', 'abrir os registros de atividades de hoje', 'abrir os registros de hoje', ALTO, 'registros',
       (('abr', 'registro'), ('ver', 'registro'), ('mostr', 'registro')), c_registros, abre=True),
    _C('usuarios_abrir', 'Usuários e perfis', 'abrir usuários e perfis', 'abrir usuários e perfis', ALTO, '__admin__',
       (('abr', 'usuario'), ('ver', 'usuario'), ('mostr', 'usuario'), ('abr', 'perfis')), c_usuarios, abre=True),
]
POR_CHAVE = {c.chave: c for c in COMANDOS}


# ------------------------------------------------------------------ configuração (quem pode usar o quê)
def modo_de(db, cmd):
    garantir(db)
    r = db.execute('SELECT modo FROM nucleai_cmd_config WHERE comando=?', (cmd.chave,)).fetchone()
    modo = r['modo'] if r else MODO_PADRAO[cmd.risco]
    if cmd.risco == ALTO:
        return modo if modo in ('gerencia', 'ninguem') else 'gerencia'
    return modo if modo in MODOS else MODO_PADRAO[cmd.risco]


def escolhidos(db, cmd):
    garantir(db)
    return {r['usuario_id'] for r in db.execute('SELECT usuario_id FROM nucleai_cmd_acesso WHERE comando=?', (cmd.chave,))}


def pode_usar(ctx, cmd):
    """Permissão da pessoa para o comando: módulo da tela + regra de risco + o que a gerência definiu."""
    if ctx.usuario is None or not ctx.tem_modulo(cmd.modulo):
        return False
    modo = modo_de(ctx.db, cmd)
    if modo == 'ninguem':
        return False
    if cmd.risco == ALTO:
        return ctx.gerencia
    if ctx.gerencia or modo == 'todos':
        return True
    return ctx.uid in escolhidos(ctx.db, cmd)


def salvar_config(db, cmd, modo, usuarios_ids):
    garantir(db)
    if cmd.risco == ALTO:
        modo = modo if modo in ('gerencia', 'ninguem') else 'gerencia'
    elif modo not in MODOS:
        raise ErroComando('Modo inválido para %s.' % cmd.nome)
    db.execute('INSERT INTO nucleai_cmd_config (comando, modo) VALUES (?,?) ON CONFLICT(comando) DO UPDATE SET modo=excluded.modo', (cmd.chave, modo))
    db.execute('DELETE FROM nucleai_cmd_acesso WHERE comando=?', (cmd.chave,))
    if cmd.risco != ALTO:
        db.executemany('INSERT OR IGNORE INTO nucleai_cmd_acesso (comando, usuario_id) VALUES (?,?)', [(cmd.chave, int(i)) for i in usuarios_ids])
    db.commit()


# ------------------------------------------------------------------ reconhecimento do que a pessoa escreveu
_PERGUNTA = {'como', 'onde', 'qual', 'quais', 'quando', 'porque', 'quem'}


def _e_pergunta(norm):
    p = norm.split()
    return bool(p) and (p[0] in _PERGUNTA or norm.startswith(('por que', 'o que', 'para que', 'pra que')))


def _casa(radical, tokens):
    return any(t.startswith(radical) for t in tokens)


def reconhecer(texto):
    """Comando que melhor combina com o texto (ou None). Perguntas ("como imprimo...") continuam sendo dúvidas de ajuda."""
    norm = normalizar(texto)
    if not norm or _e_pergunta(norm):
        return None
    tokens = norm.split()
    melhor, pontos = None, 0
    for c in COMANDOS:
        if any(_casa(n, tokens) for n in c.nao):
            continue
        for alt in c.chaves:
            if all(_casa(r, tokens) for r in alt) and len(alt) > pontos:
                melhor, pontos = c, len(alt)
    return melhor


def quer_lista(texto):
    n = normalizar(texto)
    return ('comandos' in n.split() or 'comando' in n.split() or n in ('o que voce faz', 'o que voce sabe fazer', 'o que voce pode fazer', 'o que posso pedir')
            or ('o que' in n and ('voce faz' in n or 'sabe fazer' in n or 'pode fazer' in n or 'posso pedir' in n)))


def texto_lista(ctx):
    por_risco = {BAIXO: [], MEDIO: [], ALTO: []}
    for c in COMANDOS:
        if pode_usar(ctx, c):
            por_risco[c.risco].append(c)
    partes = ['Além de tirar dúvidas, eu cumpro pedidos escritos. Antes de fazer qualquer coisa eu pergunto se pode (Sim ou Não). Você pode pedir, por exemplo:']
    for r in (BAIXO, MEDIO, ALTO):
        if por_risco[r]:
            partes.append('\n%s:' % ROTULO_RISCO[r])
            partes += ['• %s' % c.exemplo for c in por_risco[r]]
    if not any(por_risco.values()):
        return 'No momento nenhum comando está liberado para o seu perfil. Fale com a gerência se precisar.'
    partes.append('\nQuem decide o que cada pessoa pode pedir é a gerência.')
    return '\n'.join(partes)


# ------------------------------------------------------------------ fluxo (pedido -> confirmação -> execução)
def _diz(db, uid, corpo, acao=None, ref=None, resp=None):
    """Mensagem da NucleAI. `acao`/`ref`/`resp` usam as colunas dos botões do chat (acao, chamado_id, acao_resp)."""
    from . import ajuda
    m = ajuda._bot_diz(db, uid, corpo)
    if acao:
        db.execute('UPDATE chat_mensagens SET acao=?, chamado_id=?, acao_resp=? WHERE id=?', (acao, ref, resp, m['id']))
        m = dict(db.execute('SELECT * FROM chat_mensagens WHERE id=?', (m['id'],)).fetchone())
    return m


def _volta_ao_menu(db, uid, B=None):
    from . import ajuda
    B = B or ajuda.base(db)
    vt = ajuda.temas_visiveis(db, uid, B)
    s = ajuda.sessao(db, uid)
    if s and s['registro_id']:
        ajuda._registro_fechar(db, s['registro_id'], ajuda.SEM_AVALIACAO, so_se_pendente=True)
    ajuda._salvar(db, uid, estado=ajuda.TEMA, tema=None, modulo=None, area=None, candidatos=None, duvida=None, origem=None, seguinte=None, registro_id=None)
    return 'Posso ajudar em mais alguma coisa? Escreva outro pedido ou escolha o tema:\n\n' + ajuda.menu_temas(vt, B.temas)


def _res(msgs, encerrado=False):
    return {'mensagens': msgs, 'encerrado': encerrado}


def tratar(db, uid, texto, estado):
    """Ponto de entrada da NucleAI para texto livre. Devolve a resposta {'mensagens', 'encerrado'} ou None se não for um comando."""
    from . import ajuda
    garantir(db)
    ctx = Ctx(db, uid)
    if estado == ajuda.CMD:
        return _resposta_digitada(db, ctx, texto)
    if quer_lista(texto):
        return _res([_diz(db, uid, texto_lista(ctx))])
    cmd = reconhecer(texto)
    if cmd is None:
        return None
    return _pedir(db, ctx, cmd, texto)


def _pedir(db, ctx, cmd, texto):
    from . import ajuda
    if not pode_usar(ctx, cmd):
        return _res([_diz(db, ctx.uid, 'Esse pedido («%s») não está liberado para o seu perfil. 🔒 Se precisar dele, fale com a gerência.' % cmd.nome)])
    args, pergunta = {}, 'Posso %s?' % cmd.descricao
    try:
        if cmd.preparar:
            args, pergunta = cmd.preparar(ctx, texto)
    except ErroComando as e:
        return _res([_diz(db, ctx.uid, str(e))])
    if not cmd.confirmar:
        return _executar_e_responder(db, ctx, cmd, args, 'chat')
    db.execute("UPDATE nucleai_cmd_pendentes SET estado='SUBSTITUIDO', resolvido_em=? WHERE usuario_id=? AND estado='PENDENTE'", (agora(), ctx.uid))
    pid = db.execute('INSERT INTO nucleai_cmd_pendentes (usuario_id, comando, argumentos, criado_em) VALUES (?,?,?,?)',
                     (ctx.uid, cmd.chave, json.dumps(args, ensure_ascii=False), agora())).lastrowid
    ajuda._salvar(db, ctx.uid, estado=ajuda.CMD, candidatos=json.dumps({'pid': pid}))
    corpo = '%s\n\nResponda Sim para eu fazer, ou Não para cancelar. (%s)' % (pergunta, ROTULO_RISCO[cmd.risco])
    return _res([_diz(db, ctx.uid, corpo, 'CMD_CONFIRMA_ABRE' if cmd.abre else 'CMD_CONFIRMA', pid)])


def _sim_nao(texto):
    p = set(normalizar(texto).split())
    if not p or len(p) > 6:
        return None
    if p & {'nao', 'n', 'cancela', 'cancelar', 'cancele', 'negado', 'deixa', 'nunca', 'pare'}:
        return False
    if p & {'sim', 's', 'pode', 'autorizo', 'confirmo', 'ok', 'claro', 'faca', 'fazer', 'isso', 'yes', 'vai'}:
        return True
    return None


def _resposta_digitada(db, ctx, texto):
    from . import ajuda
    s = ajuda.sessao(db, ctx.uid)
    try:
        pid = int(json.loads(s['candidatos'] or '{}').get('pid'))
    except (TypeError, ValueError):
        pid = 0
    resp = _sim_nao(texto)
    if resp is None:
        novo = reconhecer(texto)   # a pessoa mudou de ideia e pediu outra coisa
        if novo is not None:
            return _pedir(db, ctx, novo, texto)
        return _res([_diz(db, ctx.uid, 'Preciso de uma resposta: Sim, para eu fazer, ou Não, para cancelar. 🙂')])
    try:
        return resolver(db, ctx.uid, pid, resp, 'chat')
    except ErroComando as e:
        return _res([_diz(db, ctx.uid, str(e) + '\n\n' + _volta_ao_menu(db, ctx.uid))])


def _executar_e_responder(db, ctx, cmd, args, origem):
    from . import auditoria
    try:
        r = cmd.executar(ctx, args)
    except ErroComando as e:
        db.rollback()
        return _res([_diz(db, ctx.uid, str(e))])
    except Exception as e:   # um comando nunca derruba o chat
        db.rollback()
        return _res([_diz(db, ctx.uid, 'Não consegui fazer isso agora. 😕 (%s)' % type(e).__name__)])
    msgs = [_diz(db, ctx.uid, r['texto'])]
    if r.get('url'):
        msgs.append(_diz(db, ctx.uid, 'Se a página não abriu sozinha, use o botão abaixo.', 'CMD_ABRIR', None, r['url']))
    from flask import g
    g.detalhe_auditoria = 'comando=%s; origem=%s' % (cmd.chave, origem)
    if origem == 'chat':
        try:
            auditoria.registrar('NucleAI', 'Comando da NucleAI: %s' % cmd.nome, g.detalhe_auditoria)
        except Exception:
            pass
    return {'mensagens': msgs, 'encerrado': False, 'url': r.get('url'), 'texto': r['texto']}


def resolver(db, uid, pid, sim, origem):
    """Resposta Sim/Não a um pedido (digitada no chat ou pelos botões). Devolve {'mensagens', 'encerrado', 'url'?}."""
    garantir(db)
    ctx = Ctx(db, uid)
    p = db.execute('SELECT * FROM nucleai_cmd_pendentes WHERE id=? AND usuario_id=?', (pid, uid)).fetchone()
    if not p or p['estado'] != 'PENDENTE':
        raise ErroComando('Este pedido já foi respondido ou perdeu a validade.')
    if datetime.now() - datetime.strptime(p['criado_em'], '%Y-%m-%d %H:%M:%S') > timedelta(minutes=VALIDADE_MIN):
        db.execute("UPDATE nucleai_cmd_pendentes SET estado='EXPIRADO', resolvido_em=? WHERE id=?", (agora(), pid))
        db.commit()
        raise ErroComando('Este pedido perdeu a validade. Peça de novo, por favor.')
    cmd = POR_CHAVE.get(p['comando'])
    db.execute('UPDATE chat_mensagens SET acao_resp=? WHERE chamado_id=? AND para_id=? AND acao LIKE ?',
               ('SIM' if sim else 'NAO', pid, uid, 'CMD_CONFIRMA%'))
    if not sim:
        db.execute("UPDATE nucleai_cmd_pendentes SET estado='NEGADO', resolvido_em=? WHERE id=?", (agora(), pid))
        from flask import g
        g.detalhe_auditoria = 'comando=%s; negado' % p['comando']
        msgs = [_diz(db, uid, 'Tudo bem, não vou fazer isso. 👍\n\n' + _volta_ao_menu(db, uid))]
        db.commit()
        return _res(msgs)
    if cmd is None or not pode_usar(ctx, cmd):   # confere de novo: a permissão pode ter mudado desde o pedido
        db.execute("UPDATE nucleai_cmd_pendentes SET estado='BLOQUEADO', resolvido_em=? WHERE id=?", (agora(), pid))
        db.commit()
        raise ErroComando('Esse pedido não está mais liberado para o seu perfil. 🔒')
    db.execute("UPDATE nucleai_cmd_pendentes SET estado='EXECUTADO', resolvido_em=? WHERE id=?", (agora(), pid))
    r = _executar_e_responder(db, ctx, cmd, json.loads(p['argumentos'] or '{}'), origem)
    r['mensagens'].append(_diz(db, uid, _volta_ao_menu(db, uid)))
    db.commit()
    return r
