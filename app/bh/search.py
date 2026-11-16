"""Pesquisa do Banco de Horas: telas, funcionários e importações. Só lê o banco; respeita as permissões.

(endpoint, rótulo, palavras-chave, módulo exigido)
"""
from __future__ import annotations

import unicodedata

from . import core

LIMIT = 20

PAGES = [
    ("bh.painel", "Banco de Horas: painel e saldos", "inicio resumo saldo mes totais pendencias", "bh_consulta"),
    ("bh.funcionarios", "Funcionários do ponto", "colaborador cadastro pessoa numero id relogio", "bh_consulta"),
    ("bh.funcionario_novo", "Cadastrar funcionário do ponto", "novo colaborador admissao incluir", "bh_gestao"),
    ("bh.dp_indice", "Departamento Pessoal", "documentos pasta rg cpf ctps contrato atestado folha ponto assinada", "bh_dp"),
    ("bh.importacoes", "Importar planilha do relógio", "xls planilha relatorio arquivo enviar upload ponto", "bh_consulta"),
    ("bh.historico", "Banco de Horas: histórico de alterações", "auditoria log registro quem alterou", "bh_consulta"),
    ("bh.escala", "Escala mensal", "turno planejamento ferias folga falta afastamento", "bh_consulta"),
]


def _norm(value):
    return "".join(c for c in unicodedata.normalize("NFKD", str(value)).lower() if c.isalnum())


def _matches(haystack, tokens):
    return all(token in haystack for token in tokens)


def _tokens(query):
    return [t for t in (_norm(part) for part in str(query).split()) if t]


def search(conn, query, modulos):
    """Retorna grupos de resultados; `modulos` é o conjunto de módulos do usuário."""
    tokens = _tokens(query)[:8]
    groups = {"pages": [], "employees": [], "imports": []}

    for endpoint, label, keywords, modulo in PAGES:
        if modulo not in modulos:
            continue
        if not tokens or _matches(_norm(f"{label} {keywords}"), tokens):
            groups["pages"].append({"label": label, "endpoint": endpoint, "params": {}})

    if "bh_consulta" not in modulos:
        return groups

    for employee in core.list_employees(conn):
        if tokens and not _matches(_norm(f"{employee['name']} {employee['clock_id']}"), tokens):
            continue
        detail = "Estagiário · somente escala" if employee["is_intern"] else f"Número I {employee['clock_id']}"
        if not employee["active"]:
            detail += " · inativo"
        target = ({"endpoint": "bh.escala", "params": {}} if employee["is_intern"]
                  else {"endpoint": "bh.extrato", "params": {"employee_id": employee["id"]}})
        groups["employees"].append({"label": employee["name"], "detail": detail, **target})
        if len(groups["employees"]) >= LIMIT:
            break

    if tokens:
        for batch in core.list_imports(conn):
            if not _matches(_norm(batch["filename"]), tokens):
                continue
            groups["imports"].append({"label": batch["filename"], "detail": f"{batch['period_start']} a {batch['period_end']}",
                                      "endpoint": "bh.importacao", "params": {"batch_id": batch["id"]}})
            if len(groups["imports"]) >= LIMIT:
                break
    return groups
