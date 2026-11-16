"""Anexos e laudos dos estudos da Medcloud: pendências por atendimento e fila de envio do robô.

Todo atendimento que gerou um estudo na Medcloud (`medcloud_fila.estado='OK'` com `estudo`) tem duas pendências: ANEXOS e
LAUDOS. A equipe escolhe os arquivos no Nucleleste; o robô os leva ao estudo (Anexos > Anexar novos arquivos > "Anexar arquivo
como anexo"; o laudo em arquivo vai pelo mesmo botão). Mandar o arquivo NÃO resolve a pendência: cada paciente tem uma
quantidade diferente de anexos e laudos, então quem marca "enviados" / "entregues" é a equipe (qualquer usuário com acesso).
Enquanto o arquivo espera o robô, o conteúdo fica no anexos.db (ver anexos.py). Depois de ENVIADO à Medcloud ele é apagado daqui
(`liberar_conteudo`): a Medcloud é quem guarda. Para baixar de novo o robô busca o arquivo na Medcloud (`processar_download`).
"""
from __future__ import annotations

import os
import re
import sqlite3
import time

from . import anexos
from .db import agora

TIPOS = {'ANEXO': 'Anexo', 'LAUDO': 'Laudo'}
MAX_BYTES = 25 * 1024 * 1024
EXTENSOES = {'.pdf': 'application/pdf', '.doc': 'application/msword',
             '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
             '.xls': 'application/vnd.ms-excel',
             '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
             '.txt': 'text/plain', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png'}
EM_ANDAMENTO = ('PENDENTE', 'PROCESSANDO')
# coluna de marcação na fila por tipo de pendência
_COLUNAS = {'ANEXO': 'anexos', 'LAUDO': 'laudos'}


class ErroEnvio(ValueError):
    """Erro de validação mostrado ao usuário."""


def nome_seguro(nome):
    """Nome do arquivo sem pasta nem caracteres estranhos (é o nome que aparece no portal do paciente)."""
    base = os.path.basename((nome or '').replace('\\', '/')).strip()
    base = re.sub(r'[^\w .()\-]', '_', base, flags=re.UNICODE)
    return re.sub(r'\s+', ' ', base)[:150].strip(' .') or 'arquivo'


def estudo_do_atendimento(db, aid):
    """Pedido da fila do atendimento quando o estudo já foi criado na Medcloud; senão None."""
    return db.execute("SELECT * FROM medcloud_fila WHERE atendimento_id=? AND estado='OK' AND IFNULL(estudo,'')<>''",
                      (aid,)).fetchone()


def adicionar(db, aid, tipo, arquivo_nome, conteudo, usuario):
    """Guarda o arquivo e o põe na fila do robô. Devolve o id do envio. Faz commit."""
    if tipo not in TIPOS:
        raise ErroEnvio('Escolha se o arquivo é um anexo ou um laudo.')
    if not estudo_do_atendimento(db, aid):
        raise ErroEnvio('Este atendimento ainda não tem estudo criado na Medcloud.')
    ext = os.path.splitext(arquivo_nome or '')[1].lower()
    if ext not in EXTENSOES:
        raise ErroEnvio('Formato não aceito. Envie PDF, Word, Excel, TXT ou imagem (JPG/PNG).')
    if not conteudo:
        raise ErroEnvio('O arquivo está vazio.')
    if len(conteudo) > MAX_BYTES:
        raise ErroEnvio('O arquivo deve ter no máximo 25 MB.')
    nome = nome_seguro(arquivo_nome)
    sha = anexos.sha256(conteudo)
    destino = anexos.caminho_de(db)
    anexo_id = anexos.gravar(destino, 'medcloud_envios', conteudo, sha) if destino else None   # conteúdo primeiro
    try:
        cur = db.execute('INSERT INTO medcloud_envios (atendimento_id, tipo, arquivo_nome, content_type, tamanho, sha256, anexo_id, '
                         'conteudo, criado_por, criado_em, atualizado_em) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                         (aid, tipo, nome, EXTENSOES[ext], len(conteudo), sha, anexo_id,
                          None if anexo_id is not None else conteudo, usuario, agora(), agora()))
        db.commit()
    except Exception:   # sem metadado, o conteúdo não pode sobrar
        db.rollback()
        anexos.apagar(destino, anexo_id)
        raise
    if anexo_id is not None:
        anexos.vincular(destino, anexo_id, cur.lastrowid)
    return cur.lastrowid


def conteudo_do_envio(db, envio):
    """Bytes do arquivo (do anexos.db ou da coluna), ou None se não foram encontrados."""
    if envio['anexo_id'] is not None:
        return anexos.ler(anexos.caminho_de(db), envio['anexo_id'])
    bruto = db.execute('SELECT conteudo FROM medcloud_envios WHERE id=?', (envio['id'],)).fetchone()
    return None if not bruto or bruto[0] is None else bytes(bruto[0])


def liberar_conteudo(con, envio_id):
    """Apaga o conteúdo de um envio já levado à Medcloud (do anexos.db e da coluna), guardando só os metadados. Faz commit.
    Falha ao apagar do anexos.db não derruba nada: sobra um órfão que `limpar_enviados` remove."""
    r = con.execute('SELECT anexo_id FROM medcloud_envios WHERE id=?', (envio_id,)).fetchone()
    if not r:
        return
    con.execute('UPDATE medcloud_envios SET anexo_id=NULL, conteudo=NULL, local_apagado_em=? WHERE id=?', (agora(), envio_id))
    con.commit()
    try:
        anexos.apagar(anexos.caminho_de(con), r['anexo_id'])
    except (sqlite3.Error, OSError):
        pass


def _com_conteudo_local(db):
    return db.execute("SELECT id, anexo_id, tamanho FROM medcloud_envios WHERE estado='OK' "
                      "AND (anexo_id IS NOT NULL OR conteudo IS NOT NULL)").fetchall()


def resumo_enviados(db):
    """(quantidade, bytes) de arquivos já enviados à Medcloud que ainda ocupam o banco de anexos."""
    linhas = _com_conteudo_local(db)
    return len(linhas), sum(r['tamanho'] or 0 for r in linhas)


def limpar_enviados(db):
    """Tira do banco os arquivos que já estão na Medcloud (feitos antes de o envio passar a apagar sozinho), remove órfãos do
    anexos.db e encolhe o arquivo (VACUUM). Devolve (quantidade, bytes liberados). Faz commit."""
    linhas = _com_conteudo_local(db)
    for r in linhas:
        liberar_conteudo(db, r['id'])
    caminho = anexos.caminho_de(db)
    if caminho and os.path.exists(caminho):
        con = sqlite3.connect(caminho, timeout=30, isolation_level=None)
        try:
            con.execute('PRAGMA busy_timeout=30000')
            usados = {r[0] for r in db.execute('SELECT anexo_id FROM medcloud_envios WHERE anexo_id IS NOT NULL')}
            for aid, in con.execute("SELECT id FROM anexos WHERE origem='medcloud_envios'").fetchall():
                if aid not in usados:
                    con.execute('DELETE FROM anexos WHERE id=?', (aid,))
            con.execute('VACUUM')
        finally:
            con.close()
    return len(linhas), sum(r['tamanho'] or 0 for r in linhas)


def marcar(db, aid, tipo, usuario, feito=True):
    """Marca a pendência (ANEXO ou LAUDO) do atendimento como resolvida, ou a reabre. Faz commit.
    Não deixa marcar enquanto ainda há arquivo desse tipo esperando o robô. Ao marcar LAUDOS entregues, os exames do atendimento
    no mapa de laudos passam para "Entregue"; devolve quantos passaram (reabrir não mexe no mapa)."""
    if tipo not in _COLUNAS:
        raise ErroEnvio('Tipo de pendência inválido.')
    if not estudo_do_atendimento(db, aid):
        raise ErroEnvio('Este atendimento não tem estudo na Medcloud.')
    col = _COLUNAS[tipo]
    if feito and db.execute("SELECT 1 FROM medcloud_envios WHERE atendimento_id=? AND tipo=? AND estado IN ('PENDENTE','PROCESSANDO')",
                            (aid, tipo)).fetchone():
        raise ErroEnvio('Ainda há %s esperando o robô enviar. Aguarde terminar antes de marcar.' %
                        ('anexo' if tipo == 'ANEXO' else 'laudo'))
    db.execute('UPDATE medcloud_fila SET %s_ok=?, %s_ok_por=?, %s_ok_em=? WHERE atendimento_id=?' % (col, col, col),
               (1 if feito else 0, usuario if feito else None, agora() if feito else None, aid))
    db.commit()
    if tipo == 'LAUDO' and feito:
        return _entregar_no_mapa(db, aid, usuario)
    return 0


def _entregar_no_mapa(db, aid, usuario):
    """Passa para "Entregue" no mapa de laudos os exames lançados a partir deste atendimento. Devolve quantos passaram."""
    from . import laudos
    passaram = 0
    for r in db.execute("SELECT id FROM realizacoes WHERE atendimento_id=? AND laudo_situacao IS NOT NULL "
                        "AND laudo_situacao<>'ENTREGUE'", (aid,)).fetchall():
        try:
            laudos.mudar(db, r['id'], 'ENTREGUE', usuario)
            passaram += 1
        except laudos.ErroLaudo:
            db.rollback()
    return passaram


def tentar_de_novo(db, eid):
    """Recoloca na fila um envio com erro (zera tentativas e erro). Faz commit. Devolve True se voltou."""
    cur = db.execute("UPDATE medcloud_envios SET estado='PENDENTE', tentativas=0, erro=NULL, fase=NULL, atualizado_em=? "
                     "WHERE id=? AND estado='ERRO'", (agora(), eid))
    db.commit()
    return cur.rowcount > 0


def remover(db, eid):
    """Tira da fila um arquivo que ainda não foi enviado (esperando ou com erro) e apaga o conteúdo. Faz commit.
    Devolve True se removeu."""
    envio = db.execute("SELECT id, anexo_id FROM medcloud_envios WHERE id=? AND estado IN ('PENDENTE','ERRO')", (eid,)).fetchone()
    if not envio:
        return False
    db.execute('DELETE FROM medcloud_envios WHERE id=?', (eid,))
    db.commit()
    anexos.apagar(anexos.caminho_de(db), envio['anexo_id'])
    return True


def pendencias(db, mostrar='pendentes', busca='', limite=300):
    """Atendimentos com estudo na Medcloud e o que falta de anexos e laudos em cada um.
    `mostrar`: 'pendentes' (falta anexos e/ou laudos) ou 'todos'. Cada item traz `anexos_pend`/`laudos_pend` (bool) e os
    arquivos de cada tipo em `envios['ANEXO']` / `envios['LAUDO']`."""
    onde = ["f.estado='OK'", "IFNULL(f.estudo,'')<>''"]
    params = []
    if mostrar != 'todos':
        onde.append('(f.anexos_ok=0 OR f.laudos_ok=0)')
    busca = (busca or '').strip()
    if busca:
        onde.append('(UPPER(a.cliente_nome) LIKE ? OR UPPER(a.exame) LIKE ?)')
        params += ['%' + busca.upper() + '%'] * 2
    linhas = db.execute(
        'SELECT f.atendimento_id, f.estudo, f.anexos_ok, f.anexos_ok_por, f.anexos_ok_em, f.laudos_ok, f.laudos_ok_por, '
        'f.laudos_ok_em, a.cliente_nome, a.exame, a.data, a.convenio FROM medcloud_fila f '
        'JOIN atendimentos a ON a.id=f.atendimento_id WHERE %s ORDER BY a.data DESC, f.id DESC LIMIT %d'
        % (' AND '.join(onde), int(limite)), params).fetchall()
    itens = [dict(r) for r in linhas]
    ids = [i['atendimento_id'] for i in itens]
    por_atendimento = {}
    if ids:
        marcas = ','.join('?' * len(ids))
        for e in db.execute('SELECT id, atendimento_id, tipo, arquivo_nome, tamanho, estado, tentativas, erro, fase, criado_por, '
                            'criado_em, enviado_em, local_apagado_em FROM medcloud_envios WHERE atendimento_id IN (%s) ORDER BY id' % marcas, ids):
            por_atendimento.setdefault(e['atendimento_id'], {'ANEXO': [], 'LAUDO': []})[e['tipo']].append(dict(e))
    for item in itens:
        item['envios'] = por_atendimento.get(item['atendimento_id'], {'ANEXO': [], 'LAUDO': []})
        item['anexos_pend'] = not item['anexos_ok']
        item['laudos_pend'] = not item['laudos_ok']
    return itens


def resumo(db, ids):
    """{atendimento_id: (anexos_pendente, laudos_pendente)} só para os atendimentos que têm estudo na Medcloud (para o aviso
    na lista de atendimentos)."""
    ids = [i for i in ids if i is not None]
    saida = {}
    for inicio in range(0, len(ids), 500):
        parte = ids[inicio:inicio + 500]
        marcas = ','.join('?' * len(parte))
        for r in db.execute("SELECT atendimento_id, anexos_ok, laudos_ok FROM medcloud_fila WHERE estado='OK' AND IFNULL(estudo,'')<>'' "
                            "AND atendimento_id IN (%s)" % marcas, parte):
            saida[r['atendimento_id']] = (not r['anexos_ok'], not r['laudos_ok'])
    return saida


def assinatura_do_andamento(db):
    """Texto que muda quando algo anda na fila de envios (a tela recarrega sozinha quando ele muda)."""
    r = db.execute("SELECT COUNT(*), IFNULL(SUM(estado IN ('PENDENTE','PROCESSANDO')),0), IFNULL(MAX(atualizado_em),'') "
                   "FROM medcloud_envios").fetchone()
    return '%d|%d|%s' % (r[0], r[1], r[2])


def processar_proximo(con, criar_robo):
    """Segundo plano: leva ao estudo o próximo arquivo PENDENTE (o mais antigo). `criar_robo(login, senha, url)` devolve o robô
    (precisa de `enviar_anexo`). Faz commit. Devolve True se tentou algum envio, False se não há nenhum esperando.
    Só roda com a Medcloud ligada e o login salvo (quem chama confere)."""
    from . import medcloud as mc
    envio = con.execute("SELECT e.id, e.atendimento_id, e.arquivo_nome, e.content_type, e.anexo_id, f.estudo FROM medcloud_envios e "
                        "JOIN medcloud_fila f ON f.atendimento_id=e.atendimento_id AND f.estado='OK' "
                        "WHERE e.estado='PENDENTE' AND e.tentativas<? ORDER BY e.id LIMIT 1", (mc.TENTATIVAS_MAXIMAS,)).fetchone()
    if not envio:
        return False
    con.execute("UPDATE medcloud_envios SET estado='PROCESSANDO', fase='Iniciando', atualizado_em=? WHERE id=? AND estado='PENDENTE'",
                (agora(), envio['id']))
    con.commit()
    try:
        conteudo = conteudo_do_envio(con, envio)
        if conteudo is None:
            # o arquivo sumiu do banco de anexos: tentar de novo não resolve
            con.execute("UPDATE medcloud_envios SET estado='ERRO', erro=?, atualizado_em=? WHERE id=? AND estado='PROCESSANDO'",
                        ('O arquivo não foi encontrado no banco de anexos. Remova e envie de novo.', agora(), envio['id']))
            con.commit()
            return True
        login = mc._cfg(con, 'medcloud_login').strip()
        senha = mc.decifrar(mc._cfg(con, 'medcloud_senha'))
        url = mc._cfg(con, 'medcloud_url', 'https://medcloud.co').rstrip('/')
        if not login or not senha:
            raise Exception('Login ou senha da Medcloud não configurados')
        robo = criar_robo(login, senha, url)

        def gravar_fase(texto):
            con.execute('UPDATE medcloud_envios SET fase=?, atualizado_em=? WHERE id=?', (texto, agora(), envio['id']))
            con.commit()
        robo.progresso = gravar_fase
        try:
            robo.enviar_anexo(envio['estudo'], envio['arquivo_nome'], conteudo, envio['content_type'])
        except Exception:
            mc._fechar(robo)   # a sessão pode estar quebrada: a próxima tentativa abre outra
            raise
        con.execute("UPDATE medcloud_envios SET estado='OK', erro=NULL, fase=NULL, enviado_em=?, atualizado_em=? "
                    "WHERE id=? AND estado='PROCESSANDO'", (agora(), agora(), envio['id']))
        con.commit()
        liberar_conteudo(con, envio['id'])   # já está na Medcloud: não precisa ficar no banco de anexos
    except Exception as exc:
        con.rollback()
        con.execute("UPDATE medcloud_envios SET tentativas=tentativas+1, erro=?, atualizado_em=?, fase=NULL, "
                    "estado=CASE WHEN tentativas+1<? THEN 'PENDENTE' ELSE 'ERRO' END WHERE id=? AND estado='PROCESSANDO'",
                    (mc._mensagem_curta(exc), agora(), mc.TENTATIVAS_MAXIMAS, envio['id']))
        con.commit()
    return True


def recolocar_travados(con):
    """Envio que ficou 'PROCESSANDO' porque o servidor caiu no meio volta para a fila (chamado ao iniciar o robô)."""
    con.execute("UPDATE medcloud_envios SET estado='PENDENTE', fase=NULL WHERE estado='PROCESSANDO'")
    con.execute("UPDATE medcloud_envios SET download_estado=NULL WHERE download_estado='PEDIDO'")
    con.commit()


# ------------------------------------------------------------------ baixar de volta da Medcloud
PASTA_BAIXADOS = 'medcloud_baixados'
VALIDADE_TEMP_S = 3600
ESPERA_DOWNLOAD_S = 45


def pasta_baixados(db):
    """Pasta temporária (ao lado do banco) onde o robô deixa o arquivo baixado até a pessoa receber."""
    principal = anexos.caminho_do_banco(db)
    return os.path.join(os.path.dirname(os.path.abspath(principal)), PASTA_BAIXADOS) if principal else None


def arquivo_baixado(db, eid):
    return os.path.join(pasta_baixados(db), '%d.bin' % eid) if pasta_baixados(db) else None


def _limpar_temporarios(pasta):
    limite = time.time() - VALIDADE_TEMP_S
    try:
        for nome in os.listdir(pasta):
            caminho = os.path.join(pasta, nome)
            try:
                if os.path.getmtime(caminho) < limite:
                    os.remove(caminho)
            except OSError:
                pass
    except OSError:
        pass


def pedir_download(db, eid):
    """Pede ao robô que baixe da Medcloud o arquivo de um envio já enviado. Faz commit. Devolve False se não há o que pedir."""
    cur = db.execute("UPDATE medcloud_envios SET download_estado='PEDIDO', download_erro=NULL, atualizado_em=? "
                     "WHERE id=? AND estado='OK' AND anexo_id IS NULL AND conteudo IS NULL", (agora(), eid))
    db.commit()
    return cur.rowcount > 0


def processar_download(con, criar_robo):
    """Segundo plano: baixa da Medcloud o próximo arquivo pedido (há alguém esperando). `criar_robo(login, senha, url)` devolve
    o robô (precisa de `baixar_anexo`). Faz commit. Devolve True se tentou algum download, False se não há pedido."""
    from . import medcloud as mc
    envio = con.execute("SELECT e.id, e.arquivo_nome, f.estudo FROM medcloud_envios e "
                        "JOIN medcloud_fila f ON f.atendimento_id=e.atendimento_id AND f.estado='OK' "
                        "WHERE e.download_estado='PEDIDO' ORDER BY e.id LIMIT 1").fetchone()
    if not envio:
        return False
    try:
        pasta = pasta_baixados(con)
        if not pasta:
            raise Exception('Sem pasta de dados para guardar o arquivo baixado')
        os.makedirs(pasta, exist_ok=True)
        _limpar_temporarios(pasta)
        login = mc._cfg(con, 'medcloud_login').strip()
        senha = mc.decifrar(mc._cfg(con, 'medcloud_senha'))
        url = mc._cfg(con, 'medcloud_url', 'https://medcloud.co').rstrip('/')
        if not login or not senha:
            raise Exception('Login ou senha da Medcloud não configurados')
        robo = criar_robo(login, senha, url)
        try:
            conteudo = robo.baixar_anexo(envio['estudo'], envio['arquivo_nome'])
        except Exception:
            mc._fechar(robo)
            raise
        if not conteudo:
            raise Exception('A Medcloud devolveu o arquivo vazio')
        with open(os.path.join(pasta, '%d.bin' % envio['id']), 'wb') as f:
            f.write(conteudo)
        con.execute("UPDATE medcloud_envios SET download_estado='PRONTO', download_erro=NULL, atualizado_em=? WHERE id=?",
                    (agora(), envio['id']))
    except Exception as exc:
        con.rollback()
        con.execute("UPDATE medcloud_envios SET download_estado='ERRO', download_erro=?, atualizado_em=? WHERE id=?",
                    (mc._mensagem_curta(exc), agora(), envio['id']))
    con.commit()
    return True
