"""Busca da NucleAI: entende uma dúvida escrita com as palavras do usuário (sem IA externa, sem internet).

Como funciona:
1. O texto é normalizado (sem acentos, minúsculo), as palavras vazias saem e cada palavra vira um radical
   ("fechei", "fecho" e "fechamento" viram "fech").
2. Palavras com o mesmo sentido ("imprimir", "impressão", "reimprimir") compartilham um conceito, e erros de digitação
   são corrigidos pela palavra mais parecida da própria base de ajuda.
3. Cada área de ajuda é pontuada (BM25 com pesos: título da área e frases de exemplo valem mais que o texto).
4. A confiança decide a resposta: uma área clara é respondida direto; várias possíveis viram uma lista curta para o
   usuário escolher; sem confiança, a NucleAI diz que não entendeu e volta para a lista.
"""
from __future__ import annotations

import difflib
import math
import re
import unicodedata
from collections import Counter

# ------------------------------------------------------------------ texto
PALAVRAS_VAZIAS = set(
    'a o as os um uma uns umas de do da dos das em no na nos nas por pra pro para com sem sob sobre e ou mas que se como '
    'qual quais quando onde eu me meu minha meus minhas voce voces vc vcs ele ela eles elas isso isto aquilo esse essa '
    'esses essas este esta estes estas aqui ali la ja so muito muita muitos mais menos tambem ainda nao sim ter tem tenho '
    'temos tinha fazer faco faz fazemos fiz preciso precisa precisamos precisar quero quer queria queremos gostaria '
    'poderia pode posso podemos consigo consegue conseguir consegui ser sou eh foi era sera estou estao estar estava '
    'ficou fica ficar ir vou vai vamos ver vejo veja saber sei sabe tipo coisa coisas ajuda ajudar ajude ajudou oi ola '
    'bom boa dia tarde noite obrigado obrigada favor tudo bem entao agora depois antes ate toda todo todos todas outra '
    'outro outros outras pq porque porquê duvida duvidas queria nesse nessa neste nesta desse dessa deste desta num numa '
    'ao aos pelo pela pelos pelas dele dela sistema programa tela pagina opcao onde aonde quanto quanta algum alguma '
    'alguns algumas ninguem nada nenhum nenhuma cade tbm vez vezes'.split())

SUFIXOS = sorted((
    'amentos', 'imentos', 'amento', 'imento', 'mentos', 'mento', 'mente', 'acoes', 'icoes', 'acao', 'icao', 'coes', 'cao', 'oes',
    'adores', 'adoras', 'ador', 'antes', 'ando', 'endo', 'indo', 'avam', 'iam', 'aram', 'eram', 'iram', 'assem', 'essem',
    'ados', 'adas', 'ado', 'ada', 'idos', 'idas', 'ido', 'ida', 'ario', 'aria', 'ais', 'eis', 'ois', 'res', 'zes', 'ismo',
    'ista', 'istas', 'ar', 'er', 'ir', 'ou', 'am', 'em', 'ei', 'ia', 'as', 'es', 'os', 'ao', 's'), key=len, reverse=True)


def normalizar(texto):
    t = unicodedata.normalize('NFKD', str(texto or ''))
    t = ''.join(c for c in t if not unicodedata.combining(c)).lower()
    return re.sub(r'[^a-z0-9]+', ' ', t).strip()


def radical(palavra):
    """Radical simples da palavra (tira terminação e vogal final). Palavras curtas ficam como estão."""
    p = palavra
    if len(p) <= 3 or p.isdigit():
        return p
    for suf in SUFIXOS:
        if p.endswith(suf) and len(p) - len(suf) >= 3:
            p = p[:-len(suf)]
            break
    if len(p) > 3 and p[-1] in 'aeo':
        p = p[:-1]
    return p


def fonetica(palavra):
    """Chave por som, para comparar erros comuns de escrita ("fexar" ~ "fechar", "empressao" ~ "impressao")."""
    p = re.sub(r'ch', 'x', palavra)
    p = re.sub(r'c(?=[ei])', 's', p)
    p = re.sub(r'ss|sc|xc', 's', p)
    p = re.sub(r'rr', 'r', p)
    p = re.sub(r'qu', 'k', p)
    p = p.replace('y', 'i').replace('w', 'v').replace('ç', 's')
    return re.sub(r'(.)\1+', r'\1', p)


def palavras(texto):
    """Palavras úteis do texto (sem vazias e sem números soltos), na forma normalizada."""
    return [p for p in normalizar(texto).split() if p not in PALAVRAS_VAZIAS and not p.isdigit() and len(p) > 1]


# ------------------------------------------------------------------ conceitos (sinônimos); cada grupo é um conceito
_GRUPOS = [
    'imprimir impressao imprimo impresso impressora reimprimir reimpressao',
    'senha password',
    'faltar faltou falta faltas faltoso ausente ausencia',
    'remarcar remarcacao reagendar reagendamento reagendado remarcou resgatar resgate desistiu',
    'cliente clientes paciente pacientes',
    'cadastrar cadastro cadastrado registrar novo nova criar adicionar incluir',
    'excluir apagar deletar remover exclusao',
    'editar alterar mudar corrigir modificar trocar atualizar ajustar',
    'pesquisar buscar procurar achar localizar encontrar filtrar consultar',
    'relatorio relatorios',
    'exportar baixar download excel pdf xlsx planilha',
    'laudo laudos laudar laudando laudado',
    'entregar entregue entrega entregar',
    'liberar liberado liberacao',
    'convenio convenios plano planos seguradora',
    'medico medicos doutor doutora solicitante crm',
    'fatura faturas faturamento faturar notafiscal tributo tributos imposto',
    'conta contas despesa despesas boleto fornecedor pagar',
    'quitar quitacao quitado comprovante recibo',
    'caixa',
    'fechar fechamento fecho fechado',
    'abrir abertura aberto',
    'agenda agendar agendamento agendado marcar marcado horario',
    'espera fila encaixe',
    'usuario usuarios login acesso perfil permissao permissoes',
    'backup copia restaurar',
    'atualizacao atualizar versao novidade novidades',
    'guia guias protocolo',
    'ficha fichas formulario termo',
    'exame exames procedimento',
    'dose doses medicamento medicamentos iodo galio pci radiofarmaco',
    'blindagem blindagens',
    'devolucao devolver devolvida',
    'vencimento vencer vencido vence validade',
    'documento documentos arquivo arquivos contrato contratos anexo anexar',
    'horas ponto escala jornada folga saldo',
    'mensagem mensagens chat conversa recado',
    'tema cor cores aparencia visual',
    'dashboard painel grafico graficos indicador indicadores',
    'saude erro erros disco',
    'clinica cnpj empresa',
    'whatsapp zap contato telefone celular',
    'troco dinheiro pix',
    'sexo genero',
    'cpf documento identidade',
]

CONCEITO = {}
for _i, _g in enumerate(_GRUPOS):
    for _p in _g.split():
        CONCEITO.setdefault(radical(_p), []).append('@%d' % _i)

# ------------------------------------------------------------------ índice
PESO_AREA, PESO_ALIAS, PESO_MODULO, PESO_TEMA, PESO_TEXTO = 4.0, 3.0, 3.0, 1.0, 1.0
K1, B = 1.2, 0.5
PESO_CONCEITO = 0.7


def _tokens(texto):
    """Radicais do texto, sem repetir a palavra vazia."""
    return [radical(p) for p in palavras(texto)]


class Indice:
    """Índice de busca de uma árvore de ajuda: temas -> módulos -> áreas (título, texto)."""

    def __init__(self, temas, aliases=None):
        aliases = aliases or {}
        self.docs = []      # (ti, mi, ai)
        self.pesos = []     # Counter por documento
        self.tam = []
        self.vocab = set()
        conhecidas = {p for g in _GRUPOS for p in g.split()}   # palavras inteiras conhecidas (para corrigir digitação)
        for ti, (tema, mods) in enumerate(temas):
            for mi, (modulo, areas) in enumerate(mods):
                for ai, (area, texto) in enumerate(areas):
                    c = Counter()
                    self._somar(c, area, PESO_AREA)
                    for frase in aliases.get((modulo, area), ()):
                        self._somar(c, frase, PESO_ALIAS)
                        conhecidas.update(palavras(frase))
                    self._somar(c, modulo, PESO_MODULO)
                    self._somar(c, tema, PESO_TEMA)
                    self._somar(c, texto, PESO_TEXTO)
                    for t in (area, modulo, tema, texto):
                        conhecidas.update(palavras(t))
                    self.docs.append((ti, mi, ai))
                    self.pesos.append(c)
                    self.tam.append(sum(c.values()))
        n = len(self.docs) or 1
        self.media = (sum(self.tam) / n) or 1.0
        df = Counter()
        for c in self.pesos:
            for t in c:
                df[t] += 1
        self.idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}
        self.vocab = {t for t in df if not t.startswith('@')}
        self.conhecidas = sorted((p, fonetica(p)) for p in conhecidas if len(p) >= 4)

    @staticmethod
    def _somar(c, texto, peso):
        for t in _tokens(texto):
            c[t] += peso
            for conc in CONCEITO.get(t, ()):
                c[conc] += peso * PESO_CONCEITO

    # ---------------------------------------------------------------- consulta
    def _corrigir(self, palavra):
        """Radical da palavra conhecida mais parecida (erro de digitação), ou None. Conservador: mesma letra inicial e
        parecença alta, para não "entender" assuntos que não têm relação com o sistema."""
        fon = fonetica(palavra)
        melhor, nota = None, 0.0
        for cand, fcand in self.conhecidas:
            if fcand[0] != fon[0] or abs(len(fcand) - len(fon)) > 2:
                continue
            r = difflib.SequenceMatcher(None, fon, fcand).ratio()
            if r > nota:
                melhor, nota = cand, r
        return radical(melhor) if melhor is not None and nota > 0.8 else None

    def _consulta(self, texto):
        """{token: peso} da consulta, com correção de digitação e conceitos."""
        q = {}
        for palavra in palavras(texto):
            t = radical(palavra)
            if t not in self.vocab and t not in CONCEITO and len(palavra) >= 4:
                # erro de digitação: troca pela palavra inteira mais parecida da base ("fexar" -> "fechar")
                t = self._corrigir(palavra) or t
            if t in self.vocab or t in CONCEITO:
                q[t] = max(q.get(t, 0), 1.0)
            for conc in CONCEITO.get(t, ()):
                q[conc] = max(q.get(conc, 0), PESO_CONCEITO)
        return {t: p for t, p in q.items() if t in self.idf}

    def buscar(self, texto, permitido=None, limite=5):
        """Lista de resultados [{ti, mi, ai, score, cobertura}] do melhor para o pior.
        `permitido(ti, mi)` filtra os módulos que o usuário pode ver."""
        q = self._consulta(texto)
        if not q:
            return []
        total_q = sum(self.idf[t] * p for t, p in q.items())
        saida = []
        for (ti, mi, ai), c, tam in zip(self.docs, self.pesos, self.tam):
            if permitido is not None and not permitido(ti, mi):
                continue
            score, achado = 0.0, 0.0
            for t, p in q.items():
                w = c.get(t)
                if not w:
                    continue
                idf = self.idf[t]
                score += p * idf * (w * (K1 + 1)) / (w + K1 * (1 - B + B * tam / self.media))
                achado += idf * p
            if score > 0:
                saida.append({'ti': ti, 'mi': mi, 'ai': ai, 'score': score, 'cobertura': achado / total_q if total_q else 0.0})
        saida.sort(key=lambda r: (-r['score'], -r['cobertura'], r['ti'], r['mi'], r['ai']))
        return saida[:limite]


# ------------------------------------------------------------------ decisão
CERTO, TALVEZ, NADA = 'certo', 'talvez', 'nada'


def decidir(resultados):
    """('certo', [r]) | ('talvez', [até 3 r]) | ('nada', []). A confiança vem da cobertura da dúvida e da folga sobre o 2º lugar."""
    if not resultados:
        return NADA, []
    top = resultados[0]
    seg = resultados[1] if len(resultados) > 1 else None
    folga = (top['score'] / seg['score']) if seg and seg['score'] else 99.0
    cob = top['cobertura']
    if (cob >= 0.72 and folga >= 1.22) or (cob >= 0.55 and folga >= 1.6) or (cob >= 0.9 and folga >= 1.1):
        return CERTO, [top]
    if cob >= 0.34:
        corte = top['score'] * 0.5
        lista = [r for r in resultados if r['score'] >= corte and r['cobertura'] >= 0.25][:3]
        return TALVEZ, lista or [top]
    return NADA, []
