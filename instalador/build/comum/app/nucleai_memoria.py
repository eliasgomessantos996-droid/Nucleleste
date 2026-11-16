"""Memória da NucleAI IA: GEMINI.md (aprendizado geral e preferências de cada usuário) e TREINAMENTO.txt (o que ela
aprendeu com cada treinador).

O banco é a fonte: assim a memória entra no backup, volta numa restauração e passa por todas as atualizações (o
instalador nunca mexe no banco). Uma cópia em arquivo fica na pasta de dados, ao lado do sistema.db, para quem quiser ler
ou editar à mão; se o arquivo for editado depois da última gravação, a edição é importada na próxima leitura.

Toda gravação guarda a versão anterior (para reverter). As anotações passam por um filtro que recusa dados pessoais e
segredos, e a memória é sempre usada como preferência, nunca como regra acima das regras do sistema.
"""
from __future__ import annotations

import os
import re
from datetime import datetime

from .db import agora

FMT = '%Y-%m-%d %H:%M:%S'
GEMINI, TREINAMENTO = 'GEMINI.md', 'TREINAMENTO.txt'
ARQUIVOS = (GEMINI, TREINAMENTO)
MAX_BYTES = 60_000          # tamanho máximo de cada arquivo
MAX_ANOTACAO = 400          # tamanho máximo de uma anotação
MAX_POR_SECAO = 40          # anotações guardadas por seção (as mais antigas saem)
VERSOES_GUARDADAS = 60
SECOES_FIXAS = ('Quem sou', 'Ferramentas e como usar', 'Como agir', 'Preferências de usuários')


def texto_ferramentas_padrao():
    """Gera automaticamente a documentação das ferramentas reais registradas no sistema."""
    from . import nucleai_ferramentas as ferr
    linhas = [
        'Regras gerais de uso das ferramentas do sistema:',
        '- Consulta e fidelidade aos dados: Use sempre as ferramentas para buscar informações reais (agenda, atendimentos, etc.). Nunca invente números, datas, horários ou nomes.',
        '- Confirmação prévia de alterações: Ferramentas que gravam ou alteram dados (escrita) realizam primeiro apenas uma proposta e exigem confirmação explícita (Sim/Não) do usuário. NUNCA diga que algo foi alterado antes do usuário responder Sim.',
        '- Ilustrar (`ilustrar`): Gera blocos visuais ricos fora do balão de texto comum (planilha, grafico, cartao_info, cartao_decisao, cartao_permissao). Use planilha para dados tabulares com mais de 3 linhas e gráfico para dados comparativos/evolutivos. Quando o usuário pedir para reordenar ou filtrar uma ilustração já enviada, use `ilustracao_atual` e depois `ilustrar` com `substitui=<id_anterior>`.',
        '',
        'Lista de ferramentas disponíveis no sistema:'
    ]
    for f in ferr.FERRAMENTAS.values():
        regras = [f'Nível {ferr.NOMES_NIVEL.get(f.nivel, f.nivel)}']
        if f.escrita:
            regras.append('alteração (exige confirmação Sim/Não)')
        if f.so_treino:
            regras.append('chat de teste')
        if f.modulos:
            mods = f.modulos if isinstance(f.modulos, (list, tuple)) else [f.modulos]
            regras.append(f'módulos: {", ".join(mods)}')
        linhas.append(f'- {f.nome}: {f.descricao} [Regras: {"; ".join(regras)}]')
    return '\n'.join(linhas)


def texto_secao_padrao(titulo):
    """Texto padrão inicial para as seções fixas do manual compartilhado."""
    if titulo == 'Quem sou':
        return (
            'Identidade: Você é a NucleAI, assistente virtual inteligente da clínica de medicina nuclear Nucleleste (Governador Valadares - MG).\n'
            'Tom e idioma: Responda sempre em português do Brasil (pt-BR), de forma profissional, prestativa, clara e objetiva.\n'
            'Urgência e concisão: A rotina da clínica é corrida e urgente; forneça respostas curtas, diretas e rápidas, sem enrolação.\n'
            'Regra de identidade: Você é sempre a NucleAI perante qualquer usuário. Não diga ao usuário qual modelo está respondendo nem revele detalhes técnicos do provedor.'
        )
    if titulo == 'Ferramentas e como usar':
        return texto_ferramentas_padrao()
    if titulo == 'Como agir':
        return (
            'Regras práticas e condutas ensinadas pela gerência no chat de teste:\n'
            '- Consultar a base de ajuda do sistema para dúvidas de procedimentos antes de responder.\n'
            '- Manter o foco no fluxo de trabalho da clínica e na segurança dos dados.'
        )
    if titulo == 'Preferências de usuários':
        return (
            'Preferências de atendimento registradas para os usuários da clínica:\n'
            '- Padrão geral: respostas concisas, tratamento profissional e foco na necessidade imediata.'
        )
    return ''


class _ModelosDict(dict):
    def __getitem__(self, chave):
        if chave == GEMINI:
            return (
                '# GEMINI.md: manual e memória compartilhada da NucleAI\n\n'
                'Este arquivo é a memória concreta e o manual de conduta da NucleAI, compartilhado entre todos os modelos.\n'
                'Aqui ficam a identidade, manual de ferramentas, regras ensinadas e preferências dos usuários.\n'
                'Regras: nunca anotar dados sensíveis de pacientes, senhas, chaves ou documentos. Preferência não muda permissão.\n\n'
                '## Quem sou\n' + texto_secao_padrao('Quem sou') + '\n\n'
                '## Ferramentas e como usar\n' + texto_secao_padrao('Ferramentas e como usar') + '\n\n'
                '## Como agir\n' + texto_secao_padrao('Como agir') + '\n\n'
                '## Preferências de usuários\n' + texto_secao_padrao('Preferências de usuários') + '\n\n'
                '## Geral\n'
            )
        return super().__getitem__(chave)

    def get(self, chave, padrao=None):
        if chave in self:
            return self[chave]
        return padrao


MODELOS = _ModelosDict({
    TREINAMENTO: (
        '# TREINAMENTO.txt: aprendizado com os treinadores\n\n'
        'Escrito pela NucleAI durante os testes controlados no Fake Chat (aba IA online).\n'
        'Cada treinador tem a sua seção. Em conflito, vale o treinador com maior força.\n\n'
    ),
})

# o que nunca pode ser gravado na memória
_PROIBIDOS = (
    re.compile(r'\d{3}\.?\d{3}\.?\d{3}-?\d{2}'),                 # CPF
    re.compile(r'\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}'),          # CNPJ
    re.compile(r'\(?\d{2}\)?\s?9?\d{4}-?\d{4}'),                 # telefone
    re.compile(r'\d{8,}'),                                       # números longos (documentos, cartões)
    re.compile(r'[\w.+-]+@[\w-]+\.[\w.]+'),                      # e-mail
    re.compile(r'\b(senha|password|token|api[\s_-]?key|chave\s+(da\s+)?api)\b', re.I),
)


class ErroMemoria(ValueError):
    """Erro mostrado à gerência ou devolvido à IA."""


# ------------------------------------------------------------------ arquivo espelho
def _pasta_dados(db):
    try:
        caminho = db.execute('PRAGMA database_list').fetchone()[2]
    except Exception:
        return None
    return os.path.dirname(os.path.abspath(caminho)) if caminho else None


def caminho_arquivo(db, nome):
    pasta = _pasta_dados(db)
    return os.path.join(pasta, nome) if pasta else None


def _escrever_arquivo(db, nome, conteudo):
    """Atualiza a cópia em arquivo. Devolve False se não deu (o banco continua sendo a fonte)."""
    caminho = caminho_arquivo(db, nome)
    if not caminho:
        return False
    try:
        tmp = caminho + '.tmp'
        with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
            f.write(conteudo)
        os.replace(tmp, caminho)
        return True
    except OSError:
        return False


def _ler_arquivo(db, nome):
    caminho = caminho_arquivo(db, nome)
    if not caminho or not os.path.isfile(caminho):
        return None, None
    try:
        if os.path.getsize(caminho) > MAX_BYTES * 2:
            return None, None
        with open(caminho, encoding='utf-8') as f:
            return f.read(), os.path.getmtime(caminho)
    except (OSError, UnicodeDecodeError):
        return None, None


# ------------------------------------------------------------------ leitura e gravação
def _validar_nome(nome):
    if nome not in ARQUIVOS:
        raise ErroMemoria('Arquivo de memória desconhecido.')


def garantir_secoes_fixas(db):
    """Garante que as seções fixas do manual compartilhado existam no GEMINI.md."""
    conteudo = ler(db, GEMINI)
    alterou = False
    for sec in SECOES_FIXAS:
        alvo = _titulo(sec)
        if alvo not in conteudo:
            conteudo = conteudo.rstrip() + '\n\n' + alvo + '\n' + texto_secao_padrao(sec) + '\n'
            alterou = True
    if alterou:
        salvar(db, GEMINI, conteudo, 'sistema', 'Criação das seções fixas do manual')
    return conteudo


def ler(db, nome):
    """Conteúdo atual. Cria a partir do modelo na primeira vez; importa a edição manual do arquivo se for mais nova."""
    _validar_nome(nome)
    r = db.execute('SELECT conteudo, atualizado_em FROM nucleai_memoria WHERE arquivo=?', (nome,)).fetchone()
    if r is None:
        texto, _ = _ler_arquivo(db, nome)   # arquivo deixado por uma instalação anterior: aproveita
        conteudo = texto if texto and texto.strip() else MODELOS[nome]
        if nome == GEMINI:
            for sec in SECOES_FIXAS:
                alvo = _titulo(sec)
                if alvo not in conteudo:
                    conteudo = conteudo.rstrip() + '\n\n' + alvo + '\n' + texto_secao_padrao(sec) + '\n'
        db.execute('INSERT INTO nucleai_memoria (arquivo, conteudo, atualizado_em, atualizado_por) VALUES (?,?,?,?)',
                   (nome, conteudo[:MAX_BYTES], agora(), 'sistema'))
        _escrever_arquivo(db, nome, conteudo[:MAX_BYTES])
        return conteudo[:MAX_BYTES]
    conteudo = r['conteudo']
    if nome == GEMINI and any(_titulo(sec) not in conteudo for sec in SECOES_FIXAS):
        for sec in SECOES_FIXAS:
            alvo = _titulo(sec)
            if alvo not in conteudo:
                conteudo = conteudo.rstrip() + '\n\n' + alvo + '\n' + texto_secao_padrao(sec) + '\n'
        salvar(db, GEMINI, conteudo, 'sistema', 'Criação das seções fixas do manual')
    texto, mtime = _ler_arquivo(db, nome)
    if texto is None:
        _escrever_arquivo(db, nome, conteudo)
        return conteudo
    if texto != conteudo:
        try:
            gravado = datetime.strptime(r['atualizado_em'] or '', FMT).timestamp()
        except ValueError:
            gravado = 0
        if mtime and mtime > gravado + 1:
            salvar(db, nome, texto, 'edição manual do arquivo', 'Importado do arquivo na pasta de dados')
            return texto[:MAX_BYTES]
        _escrever_arquivo(db, nome, conteudo)
    return conteudo


def salvar(db, nome, conteudo, por, motivo=''):
    _validar_nome(nome)
    conteudo = str(conteudo or '').replace('\r\n', '\n').replace('\r', '\n')
    if len(conteudo.encode('utf-8')) > MAX_BYTES:
        raise ErroMemoria('O arquivo passou do tamanho máximo (%d KB). Apague anotações antigas.' % (MAX_BYTES // 1000))
    atual = db.execute('SELECT conteudo FROM nucleai_memoria WHERE arquivo=?', (nome,)).fetchone()
    if atual is not None and atual['conteudo'] == conteudo:
        return False
    if atual is not None:
        db.execute('INSERT INTO nucleai_memoria_versoes (arquivo, conteudo, criado_em, por, motivo) VALUES (?,?,?,?,?)',
                   (nome, atual['conteudo'], agora(), por, motivo or 'Alteração'))
        sobra = db.execute('SELECT id FROM nucleai_memoria_versoes WHERE arquivo=? ORDER BY id DESC LIMIT -1 OFFSET ?',
                           (nome, VERSOES_GUARDADAS)).fetchall()
        for v in sobra:
            db.execute('DELETE FROM nucleai_memoria_versoes WHERE id=?', (v['id'],))
    db.execute('INSERT INTO nucleai_memoria (arquivo, conteudo, atualizado_em, atualizado_por) VALUES (?,?,?,?) '
               'ON CONFLICT(arquivo) DO UPDATE SET conteudo=excluded.conteudo, atualizado_em=excluded.atualizado_em, '
               'atualizado_por=excluded.atualizado_por', (nome, conteudo, agora(), por))
    _escrever_arquivo(db, nome, conteudo)
    return True


def versoes(db, nome, limite=30):
    _validar_nome(nome)
    return [dict(r) for r in db.execute('SELECT id, criado_em, por, motivo, LENGTH(conteudo) AS tamanho FROM nucleai_memoria_versoes '
                                        'WHERE arquivo=? ORDER BY id DESC LIMIT ?', (nome, limite)).fetchall()]


def reverter(db, versao_id, por):
    v = db.execute('SELECT arquivo, conteudo, criado_em FROM nucleai_memoria_versoes WHERE id=?', (versao_id,)).fetchone()
    if v is None:
        raise ErroMemoria('Versão não encontrada.')
    salvar(db, v['arquivo'], v['conteudo'], por, 'Revertido para a versão de %s' % v['criado_em'])
    return v['arquivo']


# ------------------------------------------------------------------ seções e anotações
def _titulo(secao):
    return '## %s' % str(secao).strip()


def secao(db, nome, titulo):
    """Linhas da seção `## titulo` (sem o título)."""
    linhas = ler(db, nome).split('\n')
    alvo = _titulo(titulo)
    saida, dentro = [], False
    for ln in linhas:
        if ln.startswith('## '):
            dentro = ln.strip() == alvo
            continue
        if dentro and ln.strip():
            saida.append(ln)
    return '\n'.join(saida)


def conferir_texto(texto):
    """Texto de uma anotação limpo; levanta ErroMemoria se tiver dado pessoal ou segredo."""
    t = ' '.join(str(texto or '').split())
    if not t:
        raise ErroMemoria('Anotação vazia.')
    for p in _PROIBIDOS:
        if p.search(t):
            raise ErroMemoria('A anotação parece ter dado pessoal ou segredo e não foi gravada.')
    return t[:MAX_ANOTACAO]


def anotar(db, nome, titulo, texto, por):
    """Acrescenta `- [data] texto` na seção (criada no fim se não existir). Mantém só as MAX_POR_SECAO mais novas."""
    t = conferir_texto(texto)
    titulo = ' '.join(str(titulo or '').split())[:80]
    if not titulo or '\n' in titulo:
        raise ErroMemoria('Seção inválida.')
    linhas = ler(db, nome).rstrip('\n').split('\n')
    alvo = _titulo(titulo)
    item = '- [%s] %s' % (agora()[:16], t)
    try:
        ini = next(i for i, ln in enumerate(linhas) if ln.strip() == alvo)
    except StopIteration:
        linhas += ['', alvo, item]
    else:
        fim = next((i for i in range(ini + 1, len(linhas)) if linhas[i].startswith('## ')), len(linhas))
        itens = [ln for ln in linhas[ini + 1:fim] if ln.strip()]
        if any(ln.split('] ', 1)[-1] == t for ln in itens):
            return False   # já anotado
        itens = (itens + [item])[-MAX_POR_SECAO:]
        linhas = linhas[:ini + 1] + itens + ([''] if fim < len(linhas) else []) + linhas[fim:]
    novo = '\n'.join(linhas).rstrip('\n') + '\n'
    while len(novo.encode('utf-8')) > MAX_BYTES:   # cheio: tira a anotação mais antiga do arquivo
        idx = next((i for i, ln in enumerate(novo.split('\n')) if ln.startswith('- [')), None)
        if idx is None:
            raise ErroMemoria('A memória está cheia.')
        partes = novo.split('\n')
        del partes[idx]
        novo = '\n'.join(partes)
    salvar(db, nome, novo, por, 'Anotação em «%s»' % titulo)
    return True


def secao_usuario(usuario):
    return 'Usuário: %s' % usuario


def secao_treinador(nome):
    return 'Treinador: %s' % nome
