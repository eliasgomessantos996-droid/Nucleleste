"""Departamento pessoal: documentos dos funcionários e folhas de ponto assinadas.

O conteúdo dos arquivos fica no anexos.db (ver app/anexos.py); aqui ficam só os metadados e o anexo_id.
O backup .zip leva os dois bancos.
Documentos nunca são apagados: são arquivados com justificativa e continuam auditados.
"""
from __future__ import annotations

import hashlib
import io
from datetime import datetime, timezone
from pathlib import Path

from .. import anexos
from . import core

MAX_BYTES = 15 * 1024 * 1024

CATEGORIES = {
    "identidade": "Documento de identidade (RG/CNH)",
    "cpf": "CPF",
    "ctps": "Carteira de trabalho (CTPS)",
    "comprovante_residencia": "Comprovante de residência",
    "contrato": "Contrato de trabalho",
    "admissional": "Exame admissional (ASO)",
    "atestado": "Atestado médico",
    "ferias": "Férias",
    "rescisao": "Rescisão",
    "folha_ponto": "Folha de ponto assinada",
    "outros": "Outros",
}
# Documentos básicos que o painel confere para cada cadastro ativo.
REQUIRED = ("identidade", "cpf", "ctps", "comprovante_residencia", "contrato", "admissional")

FILE_TYPES = {
    "pdf": ("application/pdf", ".pdf"),
    "png": ("image/png", ".png"),
    "jpeg": ("image/jpeg", ".jpg"),
    "webp": ("image/webp", ".webp"),
}
LIST_COLUMNS = ("id,employee_id,category,title,month,filename,content_type,size_bytes,sha256,note,"
                "uploaded_at,actor,archived_at,archived_by,archive_reason")


def detect_type(content):
    """Identifica o formato pelo conteúdo, nunca pela extensão informada."""
    if content.startswith(b"%PDF-"):
        return "pdf"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if content.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "webp"
    return None


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _meta(row):
    return {k: row[k] for k in ("id", "employee_id", "category", "title", "month", "filename",
                                "size_bytes", "sha256")}


def add_document(conn, employee_id, category, title, month, filename, content, note, actor):
    core.get_employee(conn, employee_id)
    if category not in CATEGORIES:
        raise ValueError("Escolha o tipo do documento.")
    if not content:
        raise ValueError("Selecione um arquivo.")
    if len(content) > MAX_BYTES:
        raise ValueError("O arquivo deve ter no máximo 15 MB.")
    kind = detect_type(content)
    if kind is None:
        raise ValueError("Formato não aceito. Envie PDF, PNG, JPEG ou WEBP.")
    content_type, extension = FILE_TYPES[kind]
    month = str(month or "").strip()
    if category == "folha_ponto":
        core._month_bounds(month)
    else:
        month = ""
    name = Path(str(filename or "").replace("\\", "/")).name[:200] or f"documento{extension}"
    title = str(title or "").strip()[:200] or CATEGORIES[category]
    note = str(note or "").strip()[:1000]
    sha = hashlib.sha256(content).hexdigest()
    if conn.execute("SELECT 1 FROM bh_employee_documents WHERE employee_id=? AND sha256=? AND archived_at IS NULL",
                    (employee_id, sha)).fetchone():
        raise ValueError("Este arquivo já foi enviado para este funcionário.")
    target = anexos.caminho_de(conn)
    anexo_id = anexos.gravar(target, "bh_employee_documents", content, sha) if target else None   # conteúdo primeiro
    try:
        with conn:
            cursor = conn.execute("""INSERT INTO bh_employee_documents
                (employee_id,category,title,month,filename,content_type,size_bytes,sha256,content,anexo_id,note,uploaded_at,actor)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (employee_id, category, title, month, name, content_type, len(content), sha,
                 b"" if anexo_id is not None else content, anexo_id, note, _now(), str(actor)))
            document_id = cursor.lastrowid
            core.log_audit(conn, actor, "document_added", "Documento anexado ao cadastro", employee_id=employee_id,
                           entity_type="document", entity_id=document_id,
                           after=_meta({"id": document_id, "employee_id": employee_id, "category": category, "title": title,
                                        "month": month, "filename": name, "size_bytes": len(content), "sha256": sha}))
    except Exception:   # sem metadado, o conteúdo não pode sobrar
        anexos.apagar(target, anexo_id)
        raise
    if anexo_id is not None:
        anexos.vincular(target, anexo_id, document_id)
    return document_id


def get_document(conn, document_id, with_content=False):
    columns = LIST_COLUMNS + ",anexo_id" + (",content" if with_content else "")
    row = conn.execute(f"SELECT {columns} FROM bh_employee_documents WHERE id=?", (document_id,)).fetchone()
    if row is None:
        raise LookupError("Documento não encontrado.")
    document = dict(row)
    if with_content and document["anexo_id"] is not None:   # migrado: o arquivo está no anexos.db
        content = anexos.ler(anexos.caminho_de(conn), document["anexo_id"])
        if content is None:
            raise LookupError("O arquivo deste documento não foi encontrado no banco de anexos.")
        document["content"] = content
    return document


def list_documents(conn, employee_id, archived=False):
    clause = "IS NOT NULL" if archived else "IS NULL"
    return [dict(r) for r in conn.execute(
        f"SELECT {LIST_COLUMNS} FROM bh_employee_documents WHERE employee_id=? AND archived_at {clause} "
        "ORDER BY month DESC, uploaded_at DESC, id DESC", (employee_id,))]


def set_archived(conn, document_id, archive, reason, actor):
    document = get_document(conn, document_id)
    reason = core._reason(reason)
    if bool(document["archived_at"]) == archive:
        raise ValueError("O documento já está nessa situação.")
    if not archive and conn.execute(
            "SELECT 1 FROM bh_employee_documents WHERE employee_id=? AND sha256=? AND archived_at IS NULL",
            (document["employee_id"], document["sha256"])).fetchone():
        raise ValueError("Já existe um documento idêntico ativo para este funcionário.")
    with conn:
        if archive:
            conn.execute("UPDATE bh_employee_documents SET archived_at=?,archived_by=?,archive_reason=? WHERE id=?",
                         (_now(), str(actor), reason, document_id))
        else:
            conn.execute("UPDATE bh_employee_documents SET archived_at=NULL,archived_by=NULL,archive_reason='' WHERE id=?",
                         (document_id,))
        core.log_audit(conn, actor, "document_archived" if archive else "document_restored", reason,
                       employee_id=document["employee_id"], entity_type="document", entity_id=document_id,
                       after=_meta(document))


def overview(conn):
    """Uma linha por funcionário, com quantidade de documentos e itens básicos ausentes."""
    present = {}
    for row in conn.execute("SELECT employee_id,category,COUNT(*) n,MAX(uploaded_at) last FROM bh_employee_documents "
                            "WHERE archived_at IS NULL GROUP BY employee_id,category"):
        entry = present.setdefault(row["employee_id"], {"categories": set(), "count": 0, "last": ""})
        entry["categories"].add(row["category"])
        entry["count"] += row["n"]
        entry["last"] = max(entry["last"], row["last"])
    result = []
    for employee in core.list_employees(conn):
        info = present.get(employee["id"], {"categories": set(), "count": 0, "last": ""})
        missing = [CATEGORIES[c] for c in REQUIRED if c not in info["categories"]]
        result.append({**employee, "document_count": info["count"], "last_upload": info["last"], "missing": missing})
    return result


def availability(conn, employee_id):
    """Situação dos documentos para o próprio funcionário: só tipos e meses, nunca títulos, notas ou arquivos."""
    counts, months = {}, []
    for row in conn.execute("SELECT category,month FROM bh_employee_documents WHERE employee_id=? AND archived_at IS NULL",
                            (employee_id,)):
        counts[row["category"]] = counts.get(row["category"], 0) + 1
        if row["category"] == "folha_ponto":
            months.append(row["month"])
    return {
        "required": [{"label": CATEGORIES[c], "available": c in counts} for c in REQUIRED],
        "others": [{"label": CATEGORIES[c], "count": n} for c, n in counts.items()
                   if c not in REQUIRED and c != "folha_ponto"],
        "timesheets": sorted(set(months), reverse=True),
    }
