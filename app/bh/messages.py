"""Mensagens entre funcionários e a gerência/gestão, com atualização ao vivo.

Cada funcionário tem uma única conversa, compartilhada por todos os usuários com o módulo "Banco de Horas:
mensagens" (equipe). Funcionários nunca enxergam conversas uns dos outros.
A tela se atualiza por consultas curtas e frequentes (não por conexão aberta).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import core

MAX_BODY = 2000
MAX_PER_MINUTE = 10
THREAD_LIMIT = 200
POLL_LIMIT = 500


def eh_funcionario(user):
    """Conta de funcionário: vinculada a um cadastro do banco de horas e sem perfil de administrador."""
    return bool(user) and bool(user["bh_funcionario_id"]) and not user["admin"]


def has_active_account(conn, employee_id):
    return conn.execute("""SELECT 1 FROM usuarios u JOIN bh_employees e ON e.id=u.bh_funcionario_id
        WHERE u.bh_funcionario_id=? AND u.ativo=1 AND e.active=1 AND u.admin=0""", (employee_id,)).fetchone() is not None


def thread(conn, employee_id, after=0):
    if after:
        rows = conn.execute("SELECT * FROM bh_messages WHERE employee_id=? AND id>? ORDER BY id LIMIT ?",
                            (employee_id, after, POLL_LIMIT))
    else:
        rows = conn.execute("SELECT * FROM (SELECT * FROM bh_messages WHERE employee_id=? ORDER BY id DESC LIMIT ?) ORDER BY id",
                            (employee_id, THREAD_LIMIT))
    return [dict(r) for r in rows]


def _minute_ago():
    return (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(timespec="microseconds")


def send(conn, user, employee_id, body):
    """`user` é a linha de usuarios; a equipe precisa ter o módulo de mensagens (conferido na rota)."""
    body = str(body or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not body:
        raise ValueError("Escreva uma mensagem.")
    if len(body) > MAX_BODY:
        raise ValueError(f"A mensagem pode ter no máximo {MAX_BODY} caracteres.")
    if eh_funcionario(user):
        employee_id = user["bh_funcionario_id"]
        label = core.get_employee(conn, employee_id)["name"]
        role = "employee"
    else:
        core.get_employee(conn, employee_id)
        if not has_active_account(conn, employee_id):
            raise ValueError("Este funcionário não tem acesso ativo ao sistema e não receberia a mensagem. "
                             "Crie ou reative o acesso na ficha dele.")
        label = "Gerência" if user["admin"] else "Gestão"
        role = "staff"
    recent = conn.execute("SELECT COUNT(*) FROM bh_messages WHERE sender_user_id=? AND created_at>?",
                          (user["id"], _minute_ago())).fetchone()[0]
    if recent >= MAX_PER_MINUTE:
        raise ValueError("Muitas mensagens em pouco tempo. Aguarde um instante e envie de novo.")
    with conn:
        cursor = conn.execute("""INSERT INTO bh_messages(employee_id,sender_user_id,sender_role,sender_label,sender_name,body,created_at)
            VALUES (?,?,?,?,?,?,?)""", (employee_id, user["id"], role, label, user["usuario"], body, core._now()))
    return dict(conn.execute("SELECT * FROM bh_messages WHERE id=?", (cursor.lastrowid,)).fetchone())


def mark_read(conn, employee_id, side, up_to_id):
    column = "staff_read_id" if side == "staff" else "employee_read_id"
    with conn:
        conn.execute(f"""INSERT INTO bh_message_threads(employee_id,{column}) VALUES (?,?)
            ON CONFLICT(employee_id) DO UPDATE SET {column}=MAX({column},excluded.{column})""", (employee_id, up_to_id))


def unread_total(conn, user, equipe=False):
    """Mensagens não lidas: do funcionário (respostas da equipe) ou da equipe (mensagens dos funcionários)."""
    if not user:
        return 0
    if eh_funcionario(user):
        return conn.execute("""SELECT COUNT(*) FROM bh_messages m LEFT JOIN bh_message_threads t ON t.employee_id=m.employee_id
            WHERE m.employee_id=? AND m.sender_role='staff' AND m.id>COALESCE(t.employee_read_id,0)""",
                            (user["bh_funcionario_id"],)).fetchone()[0]
    if not equipe:
        return 0
    return conn.execute("""SELECT COUNT(*) FROM bh_messages m LEFT JOIN bh_message_threads t ON t.employee_id=m.employee_id
        WHERE m.sender_role='employee' AND m.id>COALESCE(t.staff_read_id,0)""").fetchone()[0]


def conversations(conn):
    """Funcionários com acesso ativo ou com histórico, as conversas mais recentes primeiro."""
    rows = conn.execute("""
        SELECT e.id,e.name,e.clock_id,
          (SELECT COUNT(*) FROM bh_messages m WHERE m.employee_id=e.id AND m.sender_role='employee'
             AND m.id>COALESCE(t.staff_read_id,0)) AS unread,
          (SELECT MAX(id) FROM bh_messages m WHERE m.employee_id=e.id) AS last_id,
          EXISTS(SELECT 1 FROM usuarios u WHERE u.bh_funcionario_id=e.id AND u.ativo=1 AND u.admin=0) AS has_account
        FROM bh_employees e LEFT JOIN bh_message_threads t ON t.employee_id=e.id
        WHERE e.active=1 AND has_account=1 OR last_id IS NOT NULL
        ORDER BY last_id IS NULL, last_id DESC, e.name COLLATE NOCASE""").fetchall()
    result = []
    for row in rows:
        item = dict(row)
        last = conn.execute("SELECT body,created_at FROM bh_messages WHERE id=?", (row["last_id"],)).fetchone() if row["last_id"] else None
        item["preview"] = " ".join(last["body"].split())[:80] if last else "Sem mensagens"
        item["last_at"] = last["created_at"] if last else ""
        result.append(item)
    return result


def serialize(message, user, datetime_br):
    return {"id": message["id"], "mine": message["sender_user_id"] == user["id"], "from_employee": message["sender_role"] == "employee",
            "label": message["sender_label"], "name": message["sender_name"], "body": message["body"],
            "at": datetime_br(message["created_at"])}
