"""Acesso do funcionário ("Minha área"): cada pessoa vê só o próprio banco de horas e a situação dos documentos.

As contas são criadas pela equipe na ficha do funcionário e ficam na própria tabela de usuários da Nucleleste
(coluna bh_funcionario_id). O funcionário nunca vê o conteúdo, o título ou a observação de um documento.
"""
from __future__ import annotations

import json
import re
import sqlite3

from werkzeug.security import generate_password_hash

from ..db import agora
from . import core

MODULOS_FUNCIONARIO = ["bh_portal"]
MIN_SENHA = 6
SENHA_PADRAO = '123'   # acesso criado automaticamente: o funcionário é obrigado a trocar no primeiro login


def filtrar_relatorio(relatorio):
    """Restringe os lançamentos ao vínculo, preservando dias anteriores ao saldo inicial."""
    resultado = dict(relatorio)
    funcionario = resultado['employee']
    resultado['rows'] = [r for r in resultado['rows']
                         if r.get('status') != 'not_employed' and r.get('kind') != 'not_employed'
                         and core._within_employment(funcionario, r['date'])]
    resultado['adjustments'] = [a for a in resultado.get('adjustments', [])
                                if core._within_employment(funcionario, a['date'])]
    return resultado


def relatorio_funcionario(conn, employee_id, month):
    return filtrar_relatorio(core.monthly_report(conn, employee_id, month))


def get_account(conn, employee_id):
    row = conn.execute("SELECT id,usuario,ativo,trocar_senha FROM usuarios WHERE bh_funcionario_id=?", (employee_id,)).fetchone()
    return dict(row) if row else None


def create_account(conn, employee_id, username, password, confirm, actor):
    employee = core.get_employee(conn, employee_id)
    if employee["is_intern"]:
        raise ValueError("Estagiários participam apenas da escala e não têm banco de horas para consultar.")
    if not employee["active"]:
        raise ValueError("Ative o cadastro do funcionário antes de criar o acesso.")
    username = str(username or "").strip().upper()
    if not 3 <= len(username) <= 80:
        raise ValueError("Informe um usuário de 3 a 80 caracteres.")
    if len(password or "") < MIN_SENHA or len(password) > 256 or password != confirm:
        raise ValueError(f"Use uma senha de {MIN_SENHA} a 256 caracteres e confirme a mesma senha.")
    if get_account(conn, employee_id):
        raise ValueError("Este funcionário já possui um acesso.")
    try:
        with conn:
            cursor = conn.execute(
                "INSERT INTO usuarios (usuario,senha_hash,ativo,admin,criado_em,modulos,criado_por,bh_funcionario_id,trocar_senha) "
                "VALUES (?,?,1,0,?,?,?,?,1)",
                (username, generate_password_hash(password), agora(), json.dumps(MODULOS_FUNCIONARIO), actor, employee_id))
            core.log_audit(conn, actor, "employee_access_created", "Acesso do funcionário criado pela equipe",
                           employee_id=employee_id, entity_type="user", entity_id=cursor.lastrowid,
                           after={"user_id": cursor.lastrowid, "username": username})
    except sqlite3.IntegrityError:
        raise ValueError("Este nome de usuário já está cadastrado.") from None


def update_account(conn, employee_id, active, password, confirm, reason, actor):
    account = get_account(conn, employee_id)
    if account is None:
        raise ValueError("Este funcionário ainda não possui acesso.")
    reason = core._reason(reason)
    if password:
        if len(password) < MIN_SENHA or len(password) > 256 or password != confirm:
            raise ValueError(f"Use uma senha de {MIN_SENHA} a 256 caracteres e confirme a mesma senha.")
    with conn:
        conn.execute("UPDATE usuarios SET ativo=? WHERE id=?", (int(active), account["id"]))
        if password:
            conn.execute("UPDATE usuarios SET senha_hash=?,trocar_senha=1 WHERE id=?",
                         (generate_password_hash(password), account["id"]))
        core.log_audit(conn, actor, "employee_access_updated", reason, employee_id=employee_id,
                       entity_type="user", entity_id=account["id"],
                       before={"active": account["ativo"]}, after={"active": int(active), "password_reset": bool(password)})


def _sem_acento(texto):
    import unicodedata
    return unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().upper()


def _login_disponivel(conn, nome):
    return not conn.execute("SELECT 1 FROM usuarios WHERE usuario=?", (nome,)).fetchone()


def login_sugerido(conn, nome_completo):
    """Primeiro nome (sem acento) como login; se já existir ou for curto demais, junta o último nome e, por fim, um número."""
    partes = [p for p in re.findall(r"[A-Z]+", _sem_acento(nome_completo))]
    if not partes:
        return None
    primeiro, ultimo = partes[0], partes[-1]
    candidatos = [primeiro] if len(primeiro) >= 3 else []
    if len(partes) > 1:
        candidatos.append(f"{primeiro}.{ultimo}")
    base = candidatos[-1] if candidatos else primeiro.ljust(3, "X")
    for c in candidatos:
        if _login_disponivel(conn, c):
            return c
    for n in range(2, 100):
        c = f"{base}{n}"
        if _login_disponivel(conn, c):
            return c
    return None


def create_default_account(conn, employee_id, actor):
    """Cadastro novo no Banco de Horas: cria o usuário com o primeiro nome como login e a senha padrão. O funcionário fica
    travado na troca de senha até definir a dele. Devolve o login criado, ou None (estagiário, inativo, já tem acesso)."""
    employee = core.get_employee(conn, employee_id)
    if employee["is_intern"] or not employee["active"] or get_account(conn, employee_id):
        return None
    login = login_sugerido(conn, employee["name"])
    if not login:
        return None
    with conn:
        cursor = conn.execute(
            "INSERT INTO usuarios (usuario,senha_hash,ativo,admin,criado_em,modulos,criado_por,bh_funcionario_id,trocar_senha) "
            "VALUES (?,?,1,0,?,?,?,?,1)",
            (login, generate_password_hash(SENHA_PADRAO), agora(), json.dumps(MODULOS_FUNCIONARIO), actor, employee_id))
        core.log_audit(conn, actor, "employee_access_created", "Acesso criado automaticamente no cadastro do funcionário",
                       employee_id=employee_id, entity_type="user", entity_id=cursor.lastrowid,
                       after={"user_id": cursor.lastrowid, "username": login})
    return login
