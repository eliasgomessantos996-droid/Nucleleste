"""Banco de Horas: ponto, importações imutáveis e saldos progressivos.

Porte do programa autônomo "Banco de Horas" para dentro da Nucleleste: as mesmas regras de cálculo,
agora sobre as tabelas bh_* do banco da Nucleleste (a conexão vem de app.db.get_db).

All durations are signed integer minutes. Clock identifiers, never employee names,
associate imported attendance with registrations. Rules apply from their explicit
effective dates; uncertain attendance contributes no debit or credit.
"""

from __future__ import annotations

import calendar
import hashlib
import json
import re
import sqlite3
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


KINDS = {"normal", "falta", "abono", "folga", "feriado"}
WEEKDAYS = ("Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom")
STATUS_LABELS = {
    "ok": "Conferido", "missing_schedule": "Sem jornada vigente",
    "missing_punches": "Sem batidas: classificar o dia",
    "review": "Batidas precisam de revisão", "conflict": "Importações divergentes",
    "not_employed": "Fora do vínculo", "before_balance": "Anterior ao saldo inicial",
    "ocorrencia_pendente": "Ocorrência de ponto pendente",
    "falta": "Falta confirmada", "abono": "Abono", "folga": "Folga", "feriado": "Feriado",
}


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _date(value, label="Data"):
    try:
        parsed = date.fromisoformat(str(value))
    except (ValueError, TypeError):
        raise ValueError(f"{label} deve estar no formato AAAA-MM-DD.") from None
    if not 1900 <= parsed.year <= 2200:
        raise ValueError(f"{label} fora do intervalo permitido (1900–2200).")
    return parsed.isoformat()


def _integer(value, label, minimum=None, maximum=None):
    if isinstance(value, bool):
        raise ValueError(f"{label} deve ser um número inteiro de minutos.")
    try:
        number = int(value)
        if isinstance(value, float) and not value.is_integer():
            raise ValueError
        if isinstance(value, str) and not re.fullmatch(r"[+-]?\d+", value.strip()):
            raise ValueError
    except (ValueError, TypeError, OverflowError):
        raise ValueError(f"{label} deve ser um número inteiro de minutos.") from None
    if minimum is not None and number < minimum or maximum is not None and number > maximum:
        raise ValueError(f"{label} fora do intervalo permitido.")
    return number


def normalize_clock_id(value):
    if isinstance(value, float):
        if not value.is_integer():
            raise ValueError("Número I inválido.")
        value = str(int(value))
    identifier = str(value or "").strip()
    if identifier.isdigit():
        identifier = str(int(identifier))
    if not identifier or len(identifier) > 64 or not re.fullmatch(r"[\w.-]+", identifier):
        raise ValueError("Informe um Número I válido, sem espaços.")
    return identifier


def _audit(conn, actor, action, entity_type, entity_id, employee_id=None,
           before=None, after=None, reason=""):
    conn.execute("""INSERT INTO bh_audit_log
        (occurred_at,actor,action,entity_type,entity_id,employee_id,reason,before_json,after_json)
        VALUES (?,?,?,?,?,?,?,?,?)""", (_now(), str(actor), action, entity_type,
        entity_id, employee_id, reason, _json(before) if before is not None else None,
        _json(after) if after is not None else None))


def log_audit(conn, actor, action, reason, before=None, after=None,
              employee_id=None, entity_type="system", entity_id=None):
    """Append audit data inside the caller's transaction; do not commit it."""
    _audit(conn, actor, action, entity_type, entity_id, employee_id, before, after, reason)


def _schedule_dict(row):
    result = dict(row)
    result["weekdays"] = json.loads(result["weekdays_json"])
    result["weekly_minutes"] = sum(result["weekdays"].values())
    hours, minutes = divmod(result["weekly_minutes"], 60)
    result["weekly_label"] = f"{hours:02}:{minutes:02}"
    return result


def list_employees(conn, include_inactive=True):
    query = "SELECT * FROM bh_employees"
    if not include_inactive:
        query += " WHERE active = 1"
    return [dict(row) for row in conn.execute(query + " ORDER BY name COLLATE NOCASE,id")]


def get_employee(conn, employee_id):
    row = conn.execute("SELECT * FROM bh_employees WHERE id=?", (employee_id,)).fetchone()
    if row is None:
        raise ValueError("Funcionário não encontrado.")
    result = dict(row)
    result["schedules"] = [_schedule_dict(s) for s in conn.execute(
        "SELECT * FROM bh_schedules WHERE employee_id=? ORDER BY effective_date,id", (employee_id,))]
    return result


def _has_issued_history(conn, employee_id):
    """Ajustes ou relatórios emitidos impedem trocar o tipo do vínculo."""
    if conn.execute("SELECT 1 FROM bh_report_snapshots WHERE employee_id=? LIMIT 1", (employee_id,)).fetchone():
        return True
    return conn.execute("SELECT 1 FROM bh_adjustments WHERE employee_id=? LIMIT 1", (employee_id,)).fetchone() is not None


def save_employee(conn, data, actor, employee_id=None):
    before = get_employee(conn, employee_id) if employee_id is not None else None
    reason = _reason(data.get("reason")) if before else ""
    values = dict(before or {})
    values.update(data)
    clock_id = normalize_clock_id(values.get("clock_id"))
    name = str(values.get("name", "")).strip()
    if not name or len(name) > 200:
        raise ValueError("Informe um nome de até 200 caracteres.")
    start = _date(values.get("start_date"), "Data de admissão")
    end = _date(values["end_date"], "Data de desligamento") if values.get("end_date") else None
    if end and end < start:
        raise ValueError("Desligamento não pode ser anterior à admissão.")
    opening_date = _date(values.get("opening_balance_date") or start, "Data do saldo inicial")
    if opening_date < start or end and opening_date > end:
        raise ValueError("Data do saldo inicial deve estar dentro do vínculo.")
    opening = _integer(values.get("opening_balance_minutes", values.get("opening_balance", 0)),
                       "Saldo inicial", -100000000, 100000000)
    active = values.get("active", True)
    if isinstance(active, str):
        active = active.lower() in {"1", "true", "on", "yes"}
    active = int(bool(active))
    is_intern = int(bool(values.get("is_intern", False)))
    if before and is_intern != before["is_intern"]:
        if _has_issued_history(conn, employee_id):
            raise ValueError("O tipo do vínculo não pode mudar após ajustes ou relatórios emitidos. Cadastre outro vínculo.")
    if is_intern and opening:
        raise ValueError("Estagiários participam apenas da escala; o saldo inicial deve ser zero.")
    notes = str(values.get("notes", "")).strip()
    if before and clock_id != before["clock_id"]:
        raise ValueError("O Número I identifica o histórico e não pode ser alterado; cadastre outro vínculo.")
    if before:
        dates = [r[0] for r in conn.execute("SELECT date FROM bh_corrections WHERE employee_id=? UNION SELECT date FROM bh_adjustments WHERE employee_id=?", (employee_id, employee_id))]
        if any(d < start or end and d > end for d in dates):
            raise ValueError("O novo vínculo excluiria correções ou ajustes já registrados.")
        if any(s["effective_date"] < start or end and s["effective_date"] > end for s in before["schedules"]):
            raise ValueError("O novo vínculo excluiria uma jornada já registrada.")
    now = _now()
    try:
        with conn:
            if employee_id is None:
                cur = conn.execute("""INSERT INTO bh_employees
                    (clock_id,name,active,start_date,end_date,opening_balance_minutes,
                     opening_balance_date,notes,created_at,updated_at,is_intern) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (clock_id,name,active,start,end,opening,opening_date,notes,now,now,is_intern))
                employee_id = cur.lastrowid
            else:
                conn.execute("""UPDATE bh_employees SET name=?,active=?,start_date=?,end_date=?,
                    opening_balance_minutes=?,opening_balance_date=?,notes=?,updated_at=?,is_intern=? WHERE id=?""",
                    (name,active,start,end,opening,opening_date,notes,now,is_intern,employee_id))
            after = get_employee(conn, employee_id)
            _audit(conn, actor, "employee_updated" if before else "employee_created", "employee",
                   employee_id, employee_id, before, after, reason)
    except sqlite3.IntegrityError as error:
        raise ValueError("Este Número I já está cadastrado e não pode ser reutilizado.") from error
    return get_employee(conn, employee_id)


def save_schedule(conn, employee_id, data, actor):
    employee = get_employee(conn, employee_id)
    reason = _reason(data.get("reason"))
    effective = _date(data.get("effective_date"), "Vigência da jornada")
    if effective < employee["start_date"] or employee["end_date"] and effective > employee["end_date"]:
        raise ValueError("A vigência deve estar dentro do vínculo do funcionário.")
    supplied = data.get("weekdays", {})
    if not isinstance(supplied, dict):
        raise ValueError("Informe a jornada de cada dia da semana.")
    weekdays = {str(day): _integer(supplied.get(str(day), supplied.get(day, 0)),
                                  "Jornada diária", 0, 1440) for day in range(7)}
    break_min = _integer(data.get("required_break_minutes", 0), "Intervalo mínimo", 0, 1439)
    deduct = _integer(data.get("deduct_break_minutes", 0), "Intervalo descontado", 0, 1439)
    policy = data.get("two_punch_policy", "review")
    if policy not in {"review", "continuous", "deduct"}:
        raise ValueError("Regra para duas batidas inválida.")
    if policy == "deduct" and (deduct <= 0 or deduct < break_min):
        raise ValueError("O intervalo descontado deve ser positivo e atender ao intervalo mínimo.")
    existing = conn.execute("SELECT * FROM bh_schedules WHERE employee_id=? AND effective_date=?", (employee_id,effective)).fetchone()
    before = _schedule_dict(existing) if existing else None
    with conn:
        if before:
            schedule_id = before["id"]
            conn.execute("""UPDATE bh_schedules SET weekdays_json=?,required_break_minutes=?,
                two_punch_policy=?,deduct_break_minutes=?,actor=?,reason=? WHERE id=?""",
                (_json(weekdays),break_min,policy,deduct,str(actor),reason,schedule_id))
        else:
            cur = conn.execute("""INSERT INTO bh_schedules
                (employee_id,effective_date,weekdays_json,required_break_minutes,
                 two_punch_policy,deduct_break_minutes,created_at,actor,reason) VALUES (?,?,?,?,?,?,?,?,?)""",
                (employee_id,effective,_json(weekdays),break_min,policy,deduct,_now(),str(actor),reason))
            schedule_id = cur.lastrowid
        result = _schedule_dict(conn.execute("SELECT * FROM bh_schedules WHERE id=?", (schedule_id,)).fetchone())
        _audit(conn, actor, "schedule_updated" if before else "schedule_created", "schedule", schedule_id,
               employee_id, before=before, after=result, reason=reason)
    return result


def _norm(value):
    return "".join(c for c in unicodedata.normalize("NFKD", str(value)).lower() if c.isalnum())


def _cell_text(value):
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value or "").strip()


def _validate_punches(punches, strict=True):
    if not isinstance(punches, (list, tuple)) or len(punches) > 48:
        raise ValueError("Informe uma lista com até 48 batidas.")
    result = []
    for value in punches:
        text = str(value).strip()
        if not re.fullmatch(r"\d{2}:\d{2}" if strict else r"\d{1,2}:\d{2}", text):
            raise ValueError("Cada batida deve estar no formato HH:MM.")
        hour, minute = map(int, text.split(":"))
        if hour > 23 or minute > 59:
            raise ValueError("Horário inválido: use 00:00 a 23:59.")
        result.append(f"{hour:02}:{minute:02}")
    if strict and any(a >= b for a, b in zip(result, result[1:])):
        raise ValueError("As batidas devem estar em ordem e sem repetição. Jornada que cruza a meia-noite requer revisão específica.")
    return result


def _parse_punches(raw):
    raw = str(raw or "").strip()
    if not raw:
        return [], ""
    tokens = re.split(r"[\s;,]+", raw)
    try:
        punches = _validate_punches(tokens, strict=False)
    except ValueError as error:
        return [], str(error)
    if any(a >= b for a,b in zip(punches, punches[1:])):
        return punches, "Horários fora de ordem, repetidos ou jornada cruzando a meia-noite."
    return punches, ""


def _period(sheet):
    pattern = re.compile(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})\s*[~–—]\s*(?:(\d{4})[/-])?(\d{1,2})[/-](\d{1,2})")
    for row in sheet.get_rows():
        for cell in row:
            match = pattern.search(str(cell.value))
            if match:
                year, month, day, end_year, end_month, end_day = match.groups()
                try:
                    start = date(int(year), int(month), int(day))
                    end = date(int(end_year or year), int(end_month), int(end_day))
                except ValueError:
                    raise ValueError("A planilha contém um período inválido.") from None
                if end < start or (end-start).days > 61:
                    raise ValueError("Período da planilha inválido ou maior que 62 dias.")
                _date(start.isoformat()); _date(end.isoformat())
                return start, end
    raise ValueError("Não foi possível identificar o período da planilha.")


def _read_workbook(content):
    import xlrd  # só é necessário ao importar a planilha do relógio de ponto
    try:
        workbook = xlrd.open_workbook(file_contents=content, on_demand=True)
    except Exception as error:
        raise ValueError("Arquivo inválido. Envie o relatório original .XLS do relógio de ponto.") from error
    try:
        sheets = sorted(workbook.sheets(), key=lambda s: 0 if "registro" in _norm(s.name) else 1)
        selected = None
        for sheet in sheets:
            headers = [r for r in range(1, sheet.nrows)
                       if any(_norm(c.value) in {"numeroi", "nameroi", "nimeroi"} for c in sheet.row(r))
                       and any(_norm(c.value) == "nome" for c in sheet.row(r))
                       and sum(isinstance(c.value, (int,float)) and 1 <= c.value <= 31 for c in sheet.row(r-1)) >= 1]
            if headers:
                selected = (sheet, headers)
                break
        if selected is None:
            raise ValueError("Layout não reconhecido. É necessária a aba Registro de Presença, com Número I e dias em colunas.")
        sheet, headers = selected
        start, end = _period(sheet)
        all_dates = [start + timedelta(days=i) for i in range((end-start).days+1)]
        records = []
        seen = set()
        for rownum in headers:
            cells = sheet.row_values(rownum)
            idcol = next(i for i,v in enumerate(cells) if _norm(v) in {"numeroi", "nameroi", "nimeroi"})
            namecol = next(i for i,v in enumerate(cells) if _norm(v) == "nome")
            identifier = next((_cell_text(v) for v in cells[idcol+1:namecol] if _cell_text(v)), "")
            clock_id = normalize_clock_id(identifier)
            name = next((_cell_text(v) for v in cells[namecol+1:] if _cell_text(v)), "")
            if not name or _norm(name) in {"departamento"}:
                raise ValueError(f"Nome ausente no Número I {clock_id}.")
            last_date = start - timedelta(days=1)
            for col, day_value in enumerate(sheet.row_values(rownum-1)):
                if not isinstance(day_value,(int,float)) or not float(day_value).is_integer() or not 1 <= day_value <= 31:
                    continue
                matches = [d for d in all_dates if d.day == int(day_value) and d > last_date]
                if not matches:
                    raise ValueError("As colunas dos dias não correspondem ao período informado.")
                actual_date = matches[0]
                last_date = actual_date
                key = (clock_id, actual_date.isoformat())
                if key in seen:
                    raise ValueError(f"Número I {clock_id} repetido na aba de registros.")
                seen.add(key)
                # Excel may omit the final row when every cell is blank.
                raw = _cell_text(sheet.cell_value(rownum+1, col)) if rownum+1 < sheet.nrows else ""
                punches, error = _parse_punches(raw)
                records.append({"clock_id":clock_id,"imported_name":name,"date":actual_date.isoformat(),
                                "punches":punches,"raw_text":raw,"parse_error":error})
        if not records:
            raise ValueError("A planilha não contém registros de funcionários.")
        return start.isoformat(), end.isoformat(), records
    finally:
        workbook.release_resources()


def import_xls(conn, content, filename, actor):
    if not isinstance(content, bytes) or not content:
        raise ValueError("Selecione uma planilha .XLS não vazia.")
    if len(content) > 20 * 1024 * 1024:
        raise ValueError("A planilha deve ter até 20 MB.")
    sha = hashlib.sha256(content).hexdigest()
    existing = conn.execute("SELECT id FROM bh_imports WHERE sha256=?", (sha,)).fetchone()
    if existing:
        return {"id":existing["id"],"duplicate":True,"inserted":0,"ignored":0,"conflicts":0,"unknown_ids":[],"warnings":[]}
    start, end, records = _read_workbook(content)
    employees = {e["clock_id"]:e for e in list_employees(conn)}
    result = {"duplicate":False,"inserted":0,"ignored":0,"conflicts":0,"unknown_ids":[],"warnings":[],"period_start":start,"period_end":end,"total_rows":len(records),
              "record_count":len(records),"employee_count":len({r["clock_id"] for r in records})}
    unknown = set()
    warnings = set()
    with conn:
        cur = conn.execute("""INSERT INTO bh_imports
            (filename,sha256,period_start,period_end,created_at,actor,file_bytes,counters_json)
            VALUES (?,?,?,?,?,?,?,?)""", (Path(str(filename).replace("\\", "/")).name,sha,start,end,_now(),str(actor),content,"{}"))
        result["id"] = cur.lastrowid
        for record in records:
            identifier = record["clock_id"]
            employee = employees.get(identifier)
            if employee is None:
                unknown.add(identifier)
            elif _norm(employee["name"]) != _norm(record["imported_name"]):
                warnings.add(f"Número I {identifier}: nome na planilha difere do cadastro; associação realizada pelo ID.")
            old = conn.execute("SELECT * FROM bh_import_rows WHERE clock_id=? AND date=? AND accepted=1", (identifier, record["date"])).fetchone()
            identical = old and json.loads(old["punches_json"]) == record["punches"] and old["parse_error"] == record["parse_error"]
            if identical and record["parse_error"]:
                identical = old["raw_text"] == record["raw_text"]
            accepted = int(old is None)
            conflict = int(old is not None and not identical)
            result["inserted" if accepted else "conflicts" if conflict else "ignored"] += 1
            conn.execute("""INSERT INTO bh_import_rows
                (import_id,clock_id,imported_name,date,punches_json,raw_text,parse_error,accepted,is_conflict)
                VALUES (?,?,?,?,?,?,?,?,?)""", (result["id"],identifier,record["imported_name"],record["date"],
                _json(record["punches"]),record["raw_text"],record["parse_error"],accepted,conflict))
        result["unknown_ids"] = sorted(unknown, key=lambda v:(not v.isdigit(),int(v) if v.isdigit() else v))
        if result["conflicts"]:
            warnings.add(f"{result['conflicts']} dia(s) divergem de importação anterior. O original foi preservado; confirme os horários na correção do dia.")
        result["warnings"] = sorted(warnings)
        conn.execute("UPDATE bh_imports SET counters_json=? WHERE id=?", (_json(result),result["id"]))
        _audit(conn, actor, "file_imported", "import", result["id"], after=result)
    return result


def _import_dict(row):
    result = dict(row)
    result.pop("file_bytes", None)
    result["counters"] = json.loads(result["counters_json"])
    result.update({k:v for k,v in result["counters"].items() if k not in result})
    return result


def list_imports(conn):
    return [_import_dict(row) for row in conn.execute(
        "SELECT id,filename,sha256,period_start,period_end,created_at,actor,counters_json FROM bh_imports ORDER BY id DESC")]


def get_import(conn, import_id):
    row = conn.execute("SELECT id,filename,sha256,period_start,period_end,created_at,actor,counters_json FROM bh_imports WHERE id=?", (import_id,)).fetchone()
    if row is None:
        raise ValueError("Importação não encontrada.")
    result = _import_dict(row)
    result["rows"] = []
    employees = {}
    for row in conn.execute("""SELECT r.*,e.id employee_id,e.name employee_name FROM bh_import_rows r
        LEFT JOIN bh_employees e ON e.clock_id=r.clock_id WHERE import_id=? ORDER BY clock_id,date""", (import_id,)):
        record = dict(row)
        record["punches"] = json.loads(record["punches_json"])
        result["rows"].append(record)
        employees.setdefault(record["clock_id"], {"clock_id":record["clock_id"],"name":record["imported_name"],
                              "employee_id":record["employee_id"],"employee_name":record["employee_name"]})
    result["employees"] = list(employees.values())
    return result


def pending_ids(conn):
    return [dict(row) for row in conn.execute("""SELECT r.clock_id,MIN(r.imported_name) name,
        MIN(r.date) first_date,MAX(r.date) last_date,COUNT(*) days,
        GROUP_CONCAT(DISTINCT r.imported_name) imported_names
        FROM bh_import_rows r LEFT JOIN bh_employees e ON e.clock_id=r.clock_id
        WHERE e.id IS NULL AND r.accepted=1 GROUP BY r.clock_id ORDER BY r.clock_id""")]


def _within_employment(employee, day):
    return day >= employee["start_date"] and (not employee["end_date"] or day <= employee["end_date"])


def _reason(reason):
    result = str(reason or "").strip()
    if not result or len(result) > 2000:
        raise ValueError("Informe uma justificativa de até 2000 caracteres.")
    return result


def correct_day(conn, employee_id, day, punches, kind, reason, actor):
    employee = get_employee(conn, employee_id)
    if employee["is_intern"]:
        raise ValueError("Estagiários participam apenas da escala, sem correções de banco de horas.")
    day = _date(day)
    if not _within_employment(employee, day):
        raise ValueError("A correção deve estar dentro do vínculo do funcionário.")
    if kind not in KINDS:
        raise ValueError("Classificação do dia inválida.")
    punches = _validate_punches(punches)
    if kind in {"falta", "abono"} and punches:
        raise ValueError("Falta e abono integral devem ser classificados sem batidas.")
    reason = _reason(reason)
    before = _day_data(conn, employee, day)
    with conn:
        cur = conn.execute("""INSERT INTO bh_corrections
            (employee_id,date,punches_json,kind,reason,actor,created_at) VALUES (?,?,?,?,?,?,?)""",
            (employee_id,day,_json(punches),kind,reason,str(actor),_now()))
        after = {"id":cur.lastrowid,"employee_id":employee_id,"date":day,"punches":punches,"kind":kind,"reason":reason}
        _audit(conn, actor, "day_corrected", "correction", cur.lastrowid, employee_id, before, after, reason)
    return after


def add_adjustment(conn, employee_id, day, minutes, reason, actor):
    employee = get_employee(conn, employee_id)
    if employee["is_intern"]:
        raise ValueError("Estagiários não participam do cálculo do banco de horas.")
    day = _date(day)
    if not _within_employment(employee, day) or day < employee["opening_balance_date"]:
        raise ValueError("Ajuste deve estar dentro do vínculo e a partir da data do saldo inicial.")
    minutes = _integer(minutes, "Ajuste", -10000000, 10000000)
    if minutes == 0:
        raise ValueError("O ajuste deve ter valor diferente de zero.")
    reason = _reason(reason)
    with conn:
        now = _now()
        cur = conn.execute("""INSERT INTO bh_adjustments
            (employee_id,date,minutes,reason,actor,created_at) VALUES (?,?,?,?,?,?)""",
            (employee_id,day,minutes,reason,str(actor),now))
        after = {"id":cur.lastrowid,"employee_id":employee_id,"date":day,"minutes":minutes,"reason":reason,"actor":str(actor),"created_at":now}
        _audit(conn, actor, "balance_adjusted", "adjustment", cur.lastrowid, employee_id, after=after, reason=reason)
    return after


def audit_entries(conn, employee_id=None):
    query = "SELECT * FROM bh_audit_log"
    parameters = ()
    if employee_id is not None:
        query += " WHERE employee_id=?"
        parameters = (employee_id,)
    result = []
    for row in conn.execute(query + " ORDER BY id DESC", parameters):
        entry = dict(row)
        entry["before"] = json.loads(entry["before_json"]) if entry["before_json"] else None
        entry["after"] = json.loads(entry["after_json"]) if entry["after_json"] else None
        result.append(entry)
    return result


def _load_attendance(conn, employee):
    originals = {row["date"]:dict(row) for row in conn.execute(
        "SELECT * FROM bh_import_rows WHERE clock_id=? AND accepted=1", (employee["clock_id"],))}
    corrections = {}
    for row in conn.execute("SELECT * FROM bh_corrections WHERE employee_id=? ORDER BY id", (employee["id"],)):
        corrections[row["date"]] = dict(row)
    conflicts = {}
    for row in conn.execute("""SELECT r.date,MAX(i.created_at) conflict_at FROM bh_import_rows r
        JOIN bh_imports i ON i.id=r.import_id WHERE r.clock_id=? AND r.is_conflict=1 GROUP BY r.date""", (employee["clock_id"],)):
        conflicts[row["date"]] = row["conflict_at"]
    return originals, corrections, conflicts


def _day_data(conn, employee, day, loaded=None):
    originals, corrections, conflicts = loaded or _load_attendance(conn, employee)
    original = originals.get(day)
    correction = corrections.get(day)
    punches = json.loads(correction["punches_json"]) if correction else json.loads(original["punches_json"]) if original else []
    source_kind = correction["kind"] if correction else "normal"
    parse_error = original["parse_error"] if original and not correction else ""
    automatic_folga = bool((original or correction) and not punches and not parse_error and source_kind == "normal")
    return {"date":day,"punches":punches,
            "original_punches":json.loads(original["punches_json"]) if original else [],
            "original_raw_text":original["raw_text"] if original else "",
            "kind":"folga" if automatic_folga else source_kind,
            "source_kind":source_kind,"automatic_folga":automatic_folga,
            "reason":correction["reason"] if correction else "",
            "corrected":bool(correction),"correction_id":correction["id"] if correction else None,
            "parse_error":parse_error,
            "conflict":day in conflicts and (not correction or conflicts[day] > correction["created_at"]),
            "imported":bool(original)}


def _calculate_day(employee, day, data):
    result = dict(data)
    actual_date = date.fromisoformat(day)
    result.update(weekday=actual_date.weekday(), weekday_label=WEEKDAYS[actual_date.weekday()],
                  expected_minutes=0,worked_minutes=0,credited_minutes=0,delta_minutes=0,
                  break_minutes=0, pending=False,status="ok",status_detail="")
    if not _within_employment(employee, day):
        result["status"] = "not_employed"
        result["status_label"] = STATUS_LABELS[result["status"]]
        return result
    if day < employee["opening_balance_date"]:
        result.update(status="before_balance",delta_minutes=None,expected_minutes=None,worked_minutes=None)
        result["status_label"] = STATUS_LABELS[result["status"]]
        return result
    schedule = next((s for s in reversed(employee["schedules"]) if s["effective_date"] <= day), None)
    result["schedule_id"] = schedule["id"] if schedule else None
    if schedule is None:
        result.update(status="missing_schedule",expected_minutes=None,worked_minutes=None,delta_minutes=None,pending=True)
    else:
        expected = schedule["weekdays"][str(actual_date.weekday())]
        if data["kind"] in {"folga","feriado"}:
            expected = 0
        result["expected_minutes"] = expected
        if data["conflict"]:
            result.update(status="conflict",worked_minutes=None,delta_minutes=None,pending=True)
        elif data["parse_error"]:
            result.update(status="review",status_detail=data["parse_error"],worked_minutes=None,delta_minutes=None,pending=True)
        elif data["kind"] == "falta":
            result.update(status="falta",delta_minutes=-expected)
        elif data["kind"] == "abono":
            result.update(status="abono",credited_minutes=expected,delta_minutes=0)
        elif not data["punches"]:
            if expected:
                result.update(status="missing_punches",worked_minutes=None,delta_minutes=None,pending=True)
            elif data["kind"] in {"folga","feriado"}:
                result["status"] = data["kind"]
        else:
            punches = data["punches"]
            values = [int(p[:2])*60+int(p[3:]) for p in punches]
            detail = ""
            worked = None
            if len(values) % 2 or len(values) < 2:
                detail = "Quantidade ímpar de batidas: complete entrada e saída."
            elif any(a >= b for a,b in zip(values, values[1:])):
                detail = "Horários fora de ordem ou jornada cruzando a meia-noite."
            elif len(values) == 2:
                policy = schedule["two_punch_policy"]
                if policy == "review":
                    detail = "Duas batidas: confirme o intervalo ou configure uma regra explícita."
                else:
                    deducted = schedule["deduct_break_minutes"] if policy == "deduct" else 0
                    worked = values[1]-values[0]-deducted
                    result["break_minutes"] = deducted
                    if worked <= 0:
                        detail = "O intervalo descontado é maior ou igual à duração do dia."
            else:
                worked = sum(values[i+1]-values[i] for i in range(0,len(values),2))
                rest = sum(values[i+1]-values[i] for i in range(1,len(values)-1,2))
                result["break_minutes"] = rest
                if rest < schedule["required_break_minutes"]:
                    detail = "Intervalo registrado menor que o mínimo configurado."
            if detail:
                result.update(status="review",status_detail=detail,worked_minutes=worked,delta_minutes=None,pending=True)
            else:
                result.update(worked_minutes=worked,delta_minutes=worked-expected)
                if data["kind"] in {"folga","feriado"}:
                    result["status"] = data["kind"]
    result["status_label"] = "Folga (sem batidas)" if result["status"] == "folga" and data.get("automatic_folga") else STATUS_LABELS[result["status"]]
    return result


def _month_bounds(month):
    if not re.fullmatch(r"\d{4}-\d{2}", str(month)):
        raise ValueError("Informe um mês no formato AAAA-MM.")
    try:
        start = date.fromisoformat(month + "-01")
        end = start.replace(day=calendar.monthrange(start.year,start.month)[1])
    except ValueError:
        raise ValueError("Mês inválido.") from None
    _date(start.isoformat())
    return start, end


def monthly_report(conn, employee_id, month):
    employee = get_employee(conn, employee_id)
    if employee["is_intern"]:
        raise ValueError("Estagiários participam da escala e não possuem relatório de banco de horas.")
    start, end = _month_bounds(month)
    loaded = _load_attendance(conn, employee)
    anchor = date.fromisoformat(employee["opening_balance_date"])
    previous = employee["opening_balance_minutes"]
    movement = 0
    previous_pending = 0
    current_pending = 0
    rows = []
    cursor = min(start, anchor)
    ocorrencias = {r['data'] for r in conn.execute(
        "SELECT DISTINCT data FROM bh_ocorrencias WHERE employee_id=? AND status='PENDENTE' AND data<=?",
        (employee_id, end.isoformat())) if _within_employment(employee, r['data'])}
    previous_pending += sum(d < cursor.isoformat() for d in ocorrencias)
    while cursor <= end:
        day = cursor.isoformat()
        row = _calculate_day(employee,day,_day_data(conn,employee,day,loaded))
        if day in ocorrencias:
            row.update(pending=True, status='ocorrencia_pendente',
                       status_label=STATUS_LABELS['ocorrencia_pendente'],
                       status_detail='Aguardando análise da gerência.', delta_minutes=None)
        if cursor < start:
            previous += row["delta_minutes"] or 0
            previous_pending += int(row["pending"])
        else:
            rows.append(row)
            movement += row["delta_minutes"] or 0
            current_pending += int(row["pending"])
        cursor += timedelta(days=1)
    adjustments = []
    for record in conn.execute("SELECT * FROM bh_adjustments WHERE employee_id=? AND date<=? ORDER BY date,id", (employee_id,end.isoformat())):
        adjustment = dict(record)
        if adjustment["date"] < anchor.isoformat() or not _within_employment(employee,adjustment["date"]):
            continue
        if adjustment["date"] < start.isoformat():
            previous += adjustment["minutes"]
        else:
            movement += adjustment["minutes"]
            adjustments.append(adjustment)
    prior_to_opening = end < anchor
    return {"employee":employee,"month":month,"period_start":start.isoformat(),"period_end":end.isoformat(),
            "rows":rows,"adjustments":adjustments,"schedules":employee["schedules"],
            "previous_balance":previous,"movement":movement,"final_balance":previous+movement,
            "pending_count":previous_pending+current_pending,"current_pending_count":current_pending,
            "previous_pending_count":previous_pending,"complete":not (previous_pending+current_pending) and not prior_to_opening,
            "pending_occurrence_count":len(ocorrencias),
            "before_opening_balance":prior_to_opening,
            "worked_total":sum(r["worked_minutes"] or 0 for r in rows),
            "expected_total":sum(r["expected_minutes"] or 0 for r in rows),
            "credited_total":sum(r["credited_minutes"] or 0 for r in rows)}


def summary(conn, month):
    _month_bounds(month)
    result = []
    for employee in list_employees(conn):
        if employee["is_intern"]:
            continue
        report = monthly_report(conn,employee["id"],month)
        result.append({k:v for k,v in report.items() if k not in {"rows","schedules","adjustments"}})
    return result
