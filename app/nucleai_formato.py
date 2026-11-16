"""Formatação das mensagens da NucleAI: o guia que a IA recebe e o texto sem marcas (prévias da lista de conversas).

O desenho das marcas na tela é feito por `static/js/nucleai_formatar.js` (negrito, itálico, listas, chamadas, tabelas...).
Aqui ficam só o texto que ensina a IA a usá-las e o espelho em Python que tira as marcas para prévias em uma linha.
"""
from __future__ import annotations

import re

GUIA = """# Como formatar suas mensagens
O chat só entende estas marcas (qualquer outra aparece como símbolo solto na tela, então não invente outras):
- **negrito** (2 asteriscos) · __itálico__ (2 sublinhados) · ~~riscado~~ · ++sublinhado++ · `código`.
- Título: "# Título" ou "## Subtítulo" no começo da linha. Lista: "- item". Lista numerada: "1. item". Citação: "> texto". Divisor: "---".
- Destaque colorido: "> [!aviso] texto", "> [!dica] texto", "> [!ok] texto", "> [!erro] texto" ou "> [!info] texto".
- Use negrito só no essencial (nomes, datas, horários, valores); frases curtas; pouco emoji. Nunca escreva HTML.
Quando o conteúdo pede um bloco visual, use a ferramenta `ilustrar` em vez de texto com símbolos:
- mais de 3 linhas de dados, ou o usuário pediu para ordenar/filtrar → `ilustrar` tipo planilha (nunca tabela com barras "|");
- comparar quantidades, evolução ou proporções → `ilustrar` tipo grafico;
- ficha de uma pessoa, agendamento ou resumo com rótulo/valor → `ilustrar` tipo cartao_info;
- pergunta de Sim/Não antes de alterar algo → `ilustrar` tipo cartao_decisao (e a alteração só depois do Sim);
- mudança de acessos de usuário → `ilustrar` tipo cartao_permissao.
O bloco aparece fora do balão: depois dele, comente só o essencial em poucas linhas."""

_PADROES = (
    re.compile(r'\*\*(?=\S)([^\n]*?\S)\*\*'), re.compile(r'__(?=\S)([^\n]*?\S)__'),
    re.compile(r'~~(?=\S)([^\n]*?\S)~~'), re.compile(r'\+\+(?=\S)([^\n]*?\S)\+\+'),
    re.compile(r'`([^`\n]+)`'), re.compile(r'\*([^\s*](?:[^*\n]*[^\s*])?)\*'),
)


def texto_simples(texto):
    """O texto sem as marcas de formatação (para prévias e notificações em uma linha)."""
    t = re.sub(r'```[^\n]*\n?', '', texto or '')
    t = re.sub(r'(?m)^\s*#{1,4}\s+', '', t)
    t = re.sub(r'(?m)^\s*>\s?(\[!\w+\]\s*)?', '', t)
    for _ in range(3):
        for p in _PADROES:
            t = p.sub(r'\1', t)
    t = re.sub(r'(?m)^\s*---+\s*$', '', t)
    return re.sub(r'\n{3,}', '\n\n', t).strip()
