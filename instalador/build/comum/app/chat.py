"""Mensagens livres entre usuários (estilo WhatsApp).

Qualquer usuário ativo conversa com qualquer outro (funcionários, recepção, gestão). A mensagem fica gravada no
banco até ser lida: quem estava ausente a vê assim que abrir o sistema. A tela se atualiza por consultas curtas
(o servidor não mantém conexões abertas).
"""
from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta

from . import anexos, modulos, nucleai_arquivos, nucleai_formato, nucleai_ilustrar, presenca
from .db import agora

MAX_CORPO = 2000
MAX_POR_MINUTO = 40
LIMITE_CONVERSA = 300
LIMITE_NOVAS = 30
CORES = 8  # quantidade de cores de avatar definidas em chat.css
AVATAR_NUCLEAI = '/static/img/nucleai.svg'  # foto de perfil da assistente NucleAI
# imagens: o conteúdo fica no anexos.db e é apagado IMAGEM_HORAS depois do envio (a mensagem fica, sem a imagem)
IMAGEM_MAX = 5 * 1024 * 1024
IMAGEM_HORAS = 24
SO_IMAGEM = '📷 Imagem'   # texto da mensagem quando só a imagem foi enviada (prévia e avisos usam o texto)
IMAGEM_APAGADA = 'APAGADA'        # anexo_tipo depois que a imagem foi apagada


def tipo_imagem(conteudo):
    """Tipo da imagem pelo conteúdo (não pelo nome do arquivo). None se não for uma imagem aceita."""
    c = conteudo or b''
    if c[:3] == b'\xff\xd8\xff':
        return 'image/jpeg'
    if c[:8] == b'\x89PNG\r\n\x1a\n':
        return 'image/png'
    if c[:6] in (b'GIF87a', b'GIF89a'):
        return 'image/gif'
    if c[:4] == b'RIFF' and c[8:12] == b'WEBP':
        return 'image/webp'
    return None


class ErroChat(ValueError):
    """Erro de validação mostrado ao usuário."""


def _nome_sql(alias='u', emp='e'):
    return 'COALESCE(%s.name, %s.usuario)' % (emp, alias)


def iniciais(nome):
    partes = [p for p in (nome or '?').split() if p]
    if not partes:
        return '?'
    if len(partes) == 1:
        return partes[0][:2].upper()
    return (partes[0][0] + partes[-1][0]).upper()


def rotulo_tempo(ts):
    """'14:32' se for de hoje, 'Ontem' ou 'dd/mm' nos outros dias (lista de conversas)."""
    if not ts:
        return ''
    hoje = date.today()
    dia = ts[:10]
    if dia == hoje.isoformat():
        return ts[11:16]
    if dia == (hoje - timedelta(days=1)).isoformat():
        return 'Ontem'
    return '%s/%s' % (dia[8:10], dia[5:7])


def usuario_ativo(db, uid):
    return db.execute(
        'SELECT u.id, u.usuario, u.admin, %s AS nome FROM usuarios u LEFT JOIN bh_employees e ON e.id=u.bh_funcionario_id '
        'WHERE u.id=? AND u.ativo=1' % _nome_sql(), (uid,)).fetchone()


def ve_contato_do_sistema(db, eu):
    """Gerência (administradores e quem tem o módulo gerência) vê todas as mensagens do AVISOS DO SISTEMA."""
    u = db.execute('SELECT admin, modulos FROM usuarios WHERE id=?', (eu,)).fetchone()
    return u is not None and 'gerencia' in modulos.modulos_do_usuario(u)


def _visivel(ger, p=''):
    """Filtro das mensagens do AVISOS DO SISTEMA: funcionários só veem as de atualização do sistema (tipo ATUALIZACAO);
    os avisos de vencimento e de caixa são só da gerência. `p` é o prefixo da tabela (ex.: 'm.')."""
    return ("((%sde_id NOT IN (SELECT id FROM usuarios WHERE sistema=1) OR %stipo IN ('ATUALIZACAO','ENFERMAGEM') OR %d=1) "
            "AND (%sde_id NOT IN (SELECT id FROM usuarios WHERE sistema=4) OR %d=1))"
            % (p, p, 1 if ger else 0, p, 1 if ger else 0))


def contatos(db, eu):
    """Todos os outros usuários ativos, com a última mensagem e as não lidas; conversas recentes primeiro."""
    from . import ajuda
    ajuda.limpar(db)  # despedidas vencidas e conversas de ajuda abandonadas
    ger = ve_contato_do_sistema(db, eu)
    linhas = db.execute(
        'SELECT u.id, u.usuario, u.admin, u.sistema, %s AS nome, '
        '(SELECT MAX(m.id) FROM chat_mensagens m WHERE ((m.de_id=u.id AND m.para_id=:eu) OR (m.de_id=:eu AND m.para_id=u.id)) AND %s) AS ultima_id, '
        '(SELECT COUNT(*) FROM chat_mensagens m WHERE m.de_id=u.id AND m.para_id=:eu AND m.lida_em IS NULL AND %s) AS nao_lidas '
        'FROM usuarios u LEFT JOIN bh_employees e ON e.id=u.bh_funcionario_id '
        # os contatos do sistema (avisos e laudos) aparecem para todos; o conteúdo dos avisos é filtrado em _visivel.
        # A NucleAI (sistema=3) só existe na lista enquanto há uma conversa de ajuda do próprio usuário, ou mensagens dela
        # para ele (a gerência recebe os pedidos de ajuda e os detalhes pela NucleAI).
        'WHERE u.ativo=1 AND u.id<>:eu AND (COALESCE(u.sistema,0)<>3 OR EXISTS '
        '(SELECT 1 FROM ajuda_sessoes s WHERE s.usuario_id=:eu) OR EXISTS '
        '(SELECT 1 FROM chat_mensagens x WHERE (x.de_id=u.id AND x.para_id=:eu) OR (x.de_id=:eu AND x.para_id=u.id)))' % (_nome_sql(), _visivel(ger, 'm.'), _visivel(ger, 'm.')),
        {'eu': eu}).fetchall()
    saida = []
    situacoes = presenca.situacao(db)
    for r in linhas:
        if r['sistema'] == 4 and not ger:
            continue
        pres = situacoes.get(r['id'], {'online': False, 'visto': ''})
        item = {'id': r['id'], 'nome': r['nome'], 'usuario': r['usuario'], 'gestao': bool(r['admin']),
                'nao_lidas': r['nao_lidas'], 'ultima_id': r['ultima_id'], 'previa': '', 'ultima_em': '', 'ultima_minha': False,
                'iniciais': iniciais(r['nome']), 'cor': r['id'] % CORES, 'online': pres['online'], 'visto': pres['visto'],
                'avatar': AVATAR_NUCLEAI if r['sistema'] == 3 else '', 'sistema': r['sistema'] or 0}
        if r['ultima_id']:
            m = db.execute('SELECT de_id, corpo, criado_em FROM chat_mensagens WHERE id=?', (r['ultima_id'],)).fetchone()
            corpo = nucleai_formato.texto_simples(m['corpo']) if r['sistema'] == 3 and m['de_id'] == r['id'] else m['corpo']
            item['previa'] = ' '.join(corpo.split())[:70]   # a prévia da NucleAI não mostra as marcas (**, ##...)
            item['ultima_em'] = rotulo_tempo(m['criado_em'])
            item['ultima_minha'] = m['de_id'] == eu
        saida.append(item)
    saida.sort(key=lambda c: (c['ultima_id'] is None, -(c['ultima_id'] or 0), c['nome'].casefold()))
    return saida


def conversa(db, eu, outro, depois=0):
    """Mensagens entre os dois. Sem `depois`: as últimas LIMITE_CONVERSA; com `depois`: só as mais novas."""
    par = '((de_id=:eu AND para_id=:o) OR (de_id=:o AND para_id=:eu)) AND ' + _visivel(ve_contato_do_sistema(db, eu))
    if depois:
        linhas = db.execute('SELECT * FROM chat_mensagens WHERE %s AND id>:d ORDER BY id LIMIT 500' % par,
                            {'eu': eu, 'o': outro, 'd': depois}).fetchall()
    else:
        linhas = db.execute('SELECT * FROM (SELECT * FROM chat_mensagens WHERE %s ORDER BY id DESC LIMIT :l) ORDER BY id' % par,
                            {'eu': eu, 'o': outro, 'l': LIMITE_CONVERSA}).fetchall()
    return [dict(r) for r in linhas]


def enviar(db, eu, para, corpo, responde_id=None, imagem=None, imagem_nome='', arquivo=None, arquivo_nome=''):
    """Grava a mensagem. `responde_id`: mensagem citada (precisa ser da mesma conversa; senão é ignorada).
    `imagem`: bytes de uma imagem (JPEG, PNG, GIF ou WebP, até 5 MB), apagada IMAGEM_HORAS depois do envio.
    `arquivo`: bytes de planilha/texto (.xlsx, .xls, .csv, .txt, até 5 MB) enviado para a NucleAI (apagado com a conversa)."""
    corpo = str(corpo or '').replace('\r\n', '\n').replace('\r', '\n').strip()
    tipo_img = None
    tipo_arq = None
    if imagem is not None:
        if len(imagem) > IMAGEM_MAX:
            raise ErroChat('A imagem pode ter no máximo 5 MB.')
        tipo_img = tipo_imagem(imagem)
        if not tipo_img:
            raise ErroChat('Envie uma imagem JPG, PNG, GIF ou WebP.')
        if not corpo:
            corpo = SO_IMAGEM
    if arquivo is not None:
        if imagem is not None:
            raise ErroChat('Envie apenas um anexo por mensagem.')
        try:
            tipo_arq = nucleai_arquivos.validar_arquivo(arquivo, arquivo_nome)
        except nucleai_arquivos.ErroArquivo as e:
            raise ErroChat(str(e)) from None
        if not corpo:
            corpo = '📎 ' + (str(arquivo_nome or 'Arquivo').strip()[:100] or 'Arquivo')
    if not corpo:
        raise ErroChat('Escreva uma mensagem.')
    if len(corpo) > MAX_CORPO:
        raise ErroChat('A mensagem pode ter no máximo %d caracteres.' % MAX_CORPO)
    if para == eu or not usuario_ativo(db, para):
        raise ErroChat('Escolha uma pessoa válida para conversar.')
    sis = db.execute('SELECT COALESCE(sistema,0) AS s FROM usuarios WHERE id=?', (para,)).fetchone()['s']
    if sis in (1, 2, 4):
        raise ErroChat('As mensagens do sistema são só de leitura.')
    if sis == 3 and tipo_img:
        raise ErroChat('A NucleAI não lê imagens. Descreva a dúvida por escrito.')
    if sis != 3 and tipo_arq:
        raise ErroChat('Envio de arquivos só está disponível na conversa com a NucleAI.')
    if sis == 3:  # NucleAI: só responde dentro de uma conversa de ajuda iniciada pelo botão
        from . import ajuda
        if not ajuda.sessao(db, eu):
            raise ErroChat('Clique no botão redondo da NucleAI para começar uma conversa de ajuda.')
    recentes = db.execute("SELECT COUNT(*) FROM chat_mensagens WHERE de_id=? AND criado_em>=datetime('now','localtime','-1 minute')",
                          (eu,)).fetchone()[0]
    if recentes >= MAX_POR_MINUTO:
        raise ErroChat('Muitas mensagens em pouco tempo. Aguarde um instante e envie de novo.')
    if responde_id:
        citada = db.execute('SELECT id FROM chat_mensagens WHERE id=? AND ((de_id=? AND para_id=?) OR (de_id=? AND para_id=?))',
                            (responde_id, eu, para, para, eu)).fetchone()
        responde_id = citada['id'] if citada else None
    anexo_id = None
    caminho = None
    tipo_anexo = tipo_img or tipo_arq
    dados_anexo = imagem if tipo_img else arquivo
    nome_anexo = imagem_nome if tipo_img else arquivo_nome
    if tipo_anexo:
        caminho = anexos.caminho_de(db)
        if not caminho:
            raise ErroChat('Envio de anexo indisponível neste banco.')
        origem = 'chat' if tipo_img else nucleai_arquivos.ORIGEM_ANEXO
        anexo_id = anexos.gravar(caminho, origem, dados_anexo)   # conteúdo antes do registro (desfeito se o registro falhar)
    try:
        expira = (datetime.now() + timedelta(hours=IMAGEM_HORAS)).strftime('%Y-%m-%d %H:%M:%S') if tipo_img else None
        cur = db.execute('INSERT INTO chat_mensagens (de_id, para_id, corpo, criado_em, responde_id, expira_em, anexo_id, anexo_tipo, '
                         'anexo_nome) VALUES (?,?,?,?,?,?,?,?,?)',
                         (eu, para, corpo, agora(), responde_id or None, expira, anexo_id, tipo_anexo,
                          (str(nome_anexo or '')[:120] or None) if tipo_anexo else None))
    except Exception:
        if anexo_id:
            anexos.apagar(caminho, anexo_id)
        raise
    if anexo_id:
        anexos.vincular(caminho, anexo_id, cur.lastrowid)
    msg = dict(db.execute('SELECT * FROM chat_mensagens WHERE id=?', (cur.lastrowid,)).fetchone())
    if sis == 3:
        resposta = ajuda.responder(db, eu, corpo)
        msg['_respostas'] = resposta['mensagens']
        msg['_encerrado'] = resposta['encerrado']
    db.commit()
    return msg


def avisar_agendamento_mibi(db, linha):
    """Aviso do contato Agenda para quem pode vê-lo. O agendamento já deve estar confirmado no banco."""
    from . import agenda, util
    opcao = db.execute("SELECT valor FROM config WHERE chave='agenda_aviso_mibi'").fetchone()
    if opcao is not None and opcao['valor'] == '0':
        return 0
    if not (linha['paciente'] or '').strip() or not agenda.eh_mibi(linha['exame_tipo']):
        return 0
    de = db.execute('SELECT id FROM usuarios WHERE sistema=4 AND ativo=1').fetchone()
    if de is None:
        raise ErroChat('O contato Agenda não está disponível para enviar o aviso de MIBI.')
    etapa = linha['senha'] if linha['senha'] in agenda.SENHAS_MIBI else 'Não informada'
    corpo = 'MIBI agendado\nPaciente: %s\nData: %s às %s\nEtapa: %s' % (
        linha['paciente'], util.data_br(linha['dia']), linha['hora'], etapa)
    destinos = [u['id'] for u in db.execute('SELECT id FROM usuarios WHERE ativo=1 AND COALESCE(sistema,0)=0')
                if ve_contato_do_sistema(db, u['id'])]
    with db:
        db.executemany('INSERT INTO chat_mensagens (de_id, para_id, corpo, criado_em, tipo) VALUES (?,?,?,?,?)',
                       [(de['id'], uid, corpo, agora(), 'AGENDA_MIBI') for uid in destinos])
    return len(destinos)


def pode_transmitir(db, eu):
    from . import hierarquia
    u = db.execute('SELECT * FROM usuarios WHERE id=? AND ativo=1 AND COALESCE(sistema,0)=0', (eu,)).fetchone()
    return u is not None and hierarquia.nivel(db, u) >= hierarquia.GESTAO


def _exigir_transmissao(db, eu):
    if not pode_transmitir(db, eu):
        raise ErroChat('Só a gestão pode usar grupos de transmissão.')


def destinatarios_canal(db, eu):
    """Pessoas ativas com acesso de edição ou consulta à Agenda (sem contatos do sistema)."""
    _exigir_transmissao(db, eu)
    linhas = db.execute('SELECT u.*, %s AS nome FROM usuarios u LEFT JOIN bh_employees e ON e.id=u.bh_funcionario_id '
                        'WHERE u.ativo=1 AND COALESCE(u.sistema,0)=0 AND u.id<>? ORDER BY nome COLLATE NOCASE' % _nome_sql(), (eu,))
    return [dict(u) for u in linhas if {'agenda', 'agenda_leitura'} & modulos.modulos_do_usuario(u)]


def canais(db, eu):
    _exigir_transmissao(db, eu)
    lista = [dict(c) for c in db.execute('SELECT * FROM chat_canais WHERE usuario_id=? ORDER BY nome COLLATE NOCASE', (eu,))]
    for c in lista:
        c['membros'] = [r[0] for r in db.execute('SELECT usuario_id FROM chat_canal_membros WHERE canal_id=?', (c['id'],))]
    return lista


def _canal(db, eu, cid):
    _exigir_transmissao(db, eu)
    c = db.execute('SELECT * FROM chat_canais WHERE id=? AND usuario_id=?', (cid, eu)).fetchone()
    if c is None:
        raise ErroChat('Grupo de transmissão não encontrado.')
    return c


def salvar_canal(db, eu, cid, nome, membros):
    _exigir_transmissao(db, eu)
    if cid:
        _canal(db, eu, cid)
    nome = ' '.join(str(nome or '').split())
    if not nome or len(nome) > 80:
        raise ErroChat('Informe um nome de até 80 caracteres para o grupo.')
    try:
        ids = {int(i) for i in membros}
    except (TypeError, ValueError):
        raise ErroChat('Escolha pessoas válidas para o grupo.') from None
    permitidos = {u['id'] for u in destinatarios_canal(db, eu)}
    if not ids or not ids <= permitidos:
        raise ErroChat('Escolha ao menos uma pessoa ativa com acesso à Agenda.')
    with db:
        if cid:
            db.execute('UPDATE chat_canais SET nome=? WHERE id=?', (nome, cid))
            db.execute('DELETE FROM chat_canal_membros WHERE canal_id=?', (cid,))
        else:
            cid = db.execute('INSERT INTO chat_canais (usuario_id, nome, criado_em) VALUES (?,?,?)', (eu, nome, agora())).lastrowid
        db.executemany('INSERT INTO chat_canal_membros (canal_id, usuario_id) VALUES (?,?)', [(cid, uid) for uid in sorted(ids)])
    return cid


def excluir_canal(db, eu, cid):
    _canal(db, eu, cid)
    with db:
        db.execute('DELETE FROM chat_canal_membros WHERE canal_id=?', (cid,))
        db.execute('DELETE FROM chat_canais WHERE id=?', (cid,))


def transmitir(db, eu, cid, corpo):
    _canal(db, eu, cid)
    corpo = str(corpo or '').replace('\r\n', '\n').replace('\r', '\n').strip()
    if not corpo or len(corpo) > MAX_CORPO:
        raise ErroChat('Escreva uma mensagem de até %d caracteres.' % MAX_CORPO)
    permitidos = {u['id'] for u in destinatarios_canal(db, eu)}
    ids = [r[0] for r in db.execute('SELECT usuario_id FROM chat_canal_membros WHERE canal_id=?', (cid,)) if r[0] in permitidos]
    if not ids:
        raise ErroChat('O grupo não tem pessoas ativas com acesso à Agenda. Edite os membros.')
    recentes = db.execute("SELECT COUNT(*) FROM chat_mensagens WHERE de_id=? AND criado_em>=datetime('now','localtime','-1 minute')", (eu,)).fetchone()[0]
    if recentes >= MAX_POR_MINUTO:
        raise ErroChat('Muitas mensagens em pouco tempo. Aguarde um instante e envie de novo.')
    with db:
        db.executemany('INSERT INTO chat_mensagens (de_id, para_id, corpo, criado_em) VALUES (?,?,?,?)',
                       [(eu, uid, corpo, agora()) for uid in ids])
    return len(ids)


def marcar_lidas(db, eu, de_id):
    cur = db.execute('UPDATE chat_mensagens SET lida_em=? WHERE para_id=? AND de_id=? AND lida_em IS NULL', (agora(), eu, de_id))
    db.commit()
    return cur.rowcount


def nao_lidas_total(db, eu):
    return db.execute('SELECT COUNT(*) FROM chat_mensagens WHERE para_id=? AND lida_em IS NULL AND %s'
                      % _visivel(ve_contato_do_sistema(db, eu)), (eu,)).fetchone()[0]


def ultimo_id_recebido(db, eu):
    return db.execute('SELECT COALESCE(MAX(id),0) FROM chat_mensagens WHERE para_id=?', (eu,)).fetchone()[0]


def novas_para(db, eu, depois):
    """Mensagens recebidas depois do marcador (para os avisos na tela, em qualquer página)."""
    linhas = db.execute(
        'SELECT m.id, m.de_id, m.corpo, %s AS de_nome FROM chat_mensagens m JOIN usuarios u ON u.id=m.de_id '
        'LEFT JOIN bh_employees e ON e.id=u.bh_funcionario_id WHERE m.para_id=? AND m.id>? AND %s ORDER BY m.id LIMIT ?'
        % (_nome_sql(), _visivel(ve_contato_do_sistema(db, eu), 'm.')),
        (eu, depois, LIMITE_NOVAS)).fetchall()
    return [{'id': r['id'], 'de_id': r['de_id'], 'de_nome': r['de_nome'], 'previa': ' '.join(r['corpo'].split())[:90]} for r in linhas]


def resumo_nao_lidas(db, eu):
    """Quem escreveu e ainda não foi lido (aviso único ao abrir o sistema)."""
    linhas = db.execute(
        'SELECT m.de_id, %s AS de_nome, COUNT(*) AS n FROM chat_mensagens m JOIN usuarios u ON u.id=m.de_id '
        'LEFT JOIN bh_employees e ON e.id=u.bh_funcionario_id WHERE m.para_id=? AND m.lida_em IS NULL AND %s '
        'GROUP BY m.de_id ORDER BY MAX(m.id) DESC' % (_nome_sql(), _visivel(ve_contato_do_sistema(db, eu), 'm.')), (eu,)).fetchall()
    return [{'de_id': r['de_id'], 'de_nome': r['de_nome'], 'n': r['n']} for r in linhas]


def ids_lidos(db, eu, outro, desde):
    linhas = db.execute('SELECT id FROM chat_mensagens WHERE de_id=? AND para_id=? AND id>=? AND lida_em IS NOT NULL '
                        'ORDER BY id DESC LIMIT 400', (eu, outro, desde)).fetchall()
    return [r['id'] for r in linhas]


def enviar_cartao(db, de, para, cartao, resumo):
    """Mensagem especial do sistema (cartão em cápsulas). Só é criada pelo servidor; `enviar` nunca grava cartões, então o usuário não consegue imitar.
    `resumo`: texto simples que aparece na lista de conversas e nas notificações."""
    if not usuario_ativo(db, para):
        raise ErroChat('O destinatário não está ativo.')
    if isinstance(cartao, dict) and (cartao.get('tipo') == 'IA_ILUSTRACAO' or str(cartao.get('tipo', '')).startswith('IA_')):
        from . import ajuda
        if de != ajuda.bot_id(db):
            raise ErroChat('Somente a NucleAI pode enviar ilustrações.')
    cur = db.execute('INSERT INTO chat_mensagens (de_id, para_id, corpo, criado_em, cartao) VALUES (?,?,?,?,?)',
                     (de, para, str(resumo)[:300], agora(), json.dumps(cartao, ensure_ascii=False)))
    db.commit()
    return cur.lastrowid


def _campo(m, nome):
    return m[nome] if nome in m.keys() else None


def serializar(m, eu, citadas=None, bot_uid=None, db=None):
    """Mensagem para a tela. `citadas`: {id: mensagem} das mensagens respondidas (ver serializar_lista)."""
    criado = m['criado_em'] or ''
    saida = {'id': m['id'], 'minha': m['de_id'] == eu, 'corpo': m['corpo'], 'dia': criado[:10], 'hora': criado[11:16],
             'ia': bot_uid is not None and m['de_id'] == bot_uid,   # só o texto da NucleAI é formatado na tela

             'lida': bool(m['lida_em']), 'laudo_id': _campo(m, 'laudo_id'),
             'acao': _campo(m, 'acao'), 'chamado_id': _campo(m, 'chamado_id'), 'acao_resp': _campo(m, 'acao_resp'),
             'acao_url': _campo(m, 'acao_url'),
             'responde': None, 'imagem': None, 'imagem_apagada': False, 'so_imagem': False, 'cartao': None}
    if _campo(m, 'cartao'):
        try:
            c = json.loads(m['cartao'])
        except ValueError:
            c = None
        if isinstance(c, dict) and (c.get('tipo') == 'IA_ILUSTRACAO' or str(c.get('tipo', '')).startswith('IA_')):
            # Ilustrações e cartões de IA só podem vir da própria NucleAI (nunca de usuário humano).
            if (bot_uid is not None and m['de_id'] != bot_uid) or (bot_uid is None and saida['minha']):
                c = None
            elif db is not None:
                c = nucleai_ilustrar.enriquecer_cartao(db, c)
        saida['cartao'] = c
    tipo_anexo = _campo(m, 'anexo_tipo')
    if _campo(m, 'anexo_id') and tipo_anexo and tipo_anexo != IMAGEM_APAGADA:
        if tipo_anexo in nucleai_arquivos.TIPOS_ACEITOS:
            saida['arquivo'] = {'id': m['id'], 'nome': _campo(m, 'anexo_nome') or 'arquivo', 'tipo': tipo_anexo}
        else:
            saida['imagem'] = '/mensagens/anexo/%d' % m['id']
            saida['imagem_expira'] = (_campo(m, 'expira_em') or '')[11:16]
    elif tipo_anexo == IMAGEM_APAGADA:
        saida['imagem_apagada'] = True
    saida['so_imagem'] = bool(tipo_anexo) and (tipo_anexo not in nucleai_arquivos.TIPOS_ACEITOS) and m['corpo'] == SO_IMAGEM
    rid = _campo(m, 'responde_id')
    if rid and citadas and rid in citadas:
        c = citadas[rid]
        saida['responde'] = {'id': c['id'], 'minha': c['de_id'] == eu, 'corpo': ' '.join(c['corpo'].split())[:110]}
    return saida


def serializar_lista(db, mensagens, eu):
    """Serializa várias mensagens de uma vez, trazendo em uma só consulta as mensagens que elas respondem."""
    from . import ajuda
    ids = {_campo(m, 'responde_id') for m in mensagens} - {None, 0}
    citadas = {}
    if ids:
        marcas = ','.join('?' * len(ids))
        citadas = {r['id']: r for r in db.execute('SELECT id, de_id, corpo FROM chat_mensagens WHERE id IN (%s)' % marcas, tuple(ids))}
    bot_uid = ajuda.bot_id(db)
    return [serializar(m, eu, citadas, bot_uid=bot_uid, db=db) for m in mensagens]


# ------------------------------------------------------------------ pesquisa dentro da conversa
LIMITE_BUSCA = 60


def _dobrar(texto):
    import unicodedata
    t = unicodedata.normalize('NFKD', str(texto or ''))
    return ''.join(c for c in t if not unicodedata.combining(c)).lower()


def buscar(db, eu, outro, termo):
    """Mensagens da conversa que contêm o termo (sem diferenciar acentos nem maiúsculas), da mais nova para a mais antiga."""
    alvo = _dobrar(termo).strip()
    if len(alvo) < 2:
        return []
    par = '((de_id=:eu AND para_id=:o) OR (de_id=:o AND para_id=:eu)) AND ' + _visivel(ve_contato_do_sistema(db, eu))
    linhas = db.execute('SELECT id, de_id, corpo, criado_em FROM chat_mensagens WHERE %s ORDER BY id DESC LIMIT 5000' % par,
                        {'eu': eu, 'o': outro}).fetchall()
    achadas = []
    for r in linhas:
        if alvo in _dobrar(r['corpo']):
            achadas.append({'id': r['id'], 'minha': r['de_id'] == eu, 'dia': (r['criado_em'] or '')[:10],
                            'hora': (r['criado_em'] or '')[11:16], 'corpo': r['corpo']})
            if len(achadas) >= LIMITE_BUSCA:
                break
    return achadas


# ------------------------------------------------------------------ "digitando…" (só em memória: dura segundos)
DIGITANDO_S = 6
_digitando = {}


def digitando_agora(de_id, para_id):
    _digitando[(de_id, para_id)] = time.time()
    if len(_digitando) > 500:  # limpeza de entradas velhas
        limite = time.time() - 60
        for k in [k for k, v in _digitando.items() if v < limite]:
            _digitando.pop(k, None)


def esta_digitando(de_id, para_id):
    return time.time() - _digitando.get((de_id, para_id), 0) < DIGITANDO_S


def contar_lidas(db, eu, outro):
    """Quantas mensagens minhas a pessoa já leu (para saber quando os tracinhos mudam)."""
    return db.execute('SELECT COUNT(*) FROM chat_mensagens WHERE de_id=? AND para_id=? AND lida_em IS NOT NULL', (eu, outro)).fetchone()[0]


# ------------------------------------------------------------------ imagens: apagamento depois de 24 h
def imagem_da_mensagem(db, eu, mid):
    """(conteúdo, tipo) da imagem da mensagem, só para quem enviou ou recebeu; None se não houver ou já tiver sido apagada."""
    m = db.execute('SELECT anexo_id, anexo_tipo FROM chat_mensagens WHERE id=? AND (de_id=? OR para_id=?) AND anexo_id IS NOT NULL',
                   (mid, eu, eu)).fetchone()
    if m is None or not m['anexo_tipo'] or m['anexo_tipo'] == IMAGEM_APAGADA:
        return None
    conteudo = anexos.ler(anexos.caminho_de(db), m['anexo_id'])
    return (conteudo, m['anexo_tipo']) if conteudo is not None else None


def apagar_imagens_expiradas(db, agora_dt=None):
    """Apaga o conteúdo das imagens com mais de IMAGEM_HORAS e marca a mensagem (o texto continua). Também remove do
    anexos.db qualquer imagem do chat esquecida (ex.: queda no meio do envio). Devolve quantas imagens foram apagadas."""
    import os
    import sqlite3
    agora_dt = agora_dt or datetime.now()
    limite = agora_dt.strftime('%Y-%m-%d %H:%M:%S')
    caminho = anexos.caminho_de(db)
    vencidas = db.execute("SELECT id, anexo_id FROM chat_mensagens WHERE anexo_id IS NOT NULL AND anexo_tipo IS NOT NULL "
                          "AND anexo_tipo<>? AND expira_em IS NOT NULL AND expira_em<>'' AND expira_em<?",
                          (IMAGEM_APAGADA, limite)).fetchall()
    for r in vencidas:
        anexos.apagar(caminho, r['anexo_id'])
        db.execute('UPDATE chat_mensagens SET anexo_id=NULL, anexo_tipo=?, expira_em=NULL WHERE id=?', (IMAGEM_APAGADA, r['id']))
    db.commit()
    # rede de segurança: nenhuma imagem do chat fica no anexos.db além do prazo (+1 h de folga)
    if caminho and os.path.exists(caminho):
        corte = (agora_dt - timedelta(hours=IMAGEM_HORAS + 1)).isoformat(timespec='seconds')
        try:
            con = anexos.conectar(caminho)
            try:
                with con:
                    con.execute("DELETE FROM anexos WHERE origem='chat' AND criado_em<?", (corte,))
            finally:
                con.close()
        except sqlite3.Error:
            pass
    return len(vencidas)
