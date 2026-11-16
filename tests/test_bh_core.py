"""Testes de regressão do núcleo do Banco de Horas (portados do programa autônomo, rodando sobre o banco da Nucleleste).

Synthetic BIFF5 workbooks exercise the actual XLS reader without committing any
employee information or requiring an XLS writer dependency.
"""

import sqlite3
import struct
import tempfile
import unittest
from pathlib import Path

from app import db as dbmod
from app.bh import core


def workbook(employees, start=1, end=30, year=2026, month=9, title="Registro de Presenca"):
    """Build a valid .xls workbook with (clock ID,name,{day:marks}) employees."""
    def record(code, content):
        return struct.pack("<HH", code, len(content)) + content

    def bof(kind):
        return record(0x0809, struct.pack("<HHHH", 0x0500, kind, 0x096C, 0x07C9))

    name = title.encode("cp1252")

    def boundsheet(offset):
        return record(0x0085, struct.pack("<IBBB", offset, 0, 0, len(name)) + name)

    prefix = bof(0x0005) + record(0x0042, struct.pack("<H", 1252))
    globals_length = len(prefix + boundsheet(0) + record(0x000A, b""))
    globals_stream = prefix + boundsheet(globals_length) + record(0x000A, b"")
    sheet = bof(0x0010) + record(0x0200, struct.pack("<HHHHH", 0, 2 + len(employees)*3, 0, max(end-start+1,4), 0))
    cells = [(0,0,"Registro de presenca"), (1,0,f"{year:04}/{month:02}/{start:02} ~ {month:02}/{end:02}")]
    for offset, (identifier, employee_name, punches) in enumerate(employees):
        row = 2 + offset*3
        cells += [(row,column,day) for column,day in enumerate(range(start,end+1))]
        cells += [(row+1,0,"Namero I:"),(row+1,1,identifier),
                  (row+1,2,"NOME:"),(row+1,3,employee_name)]
        for day, marks in punches.items():
            if start <= day <= end:
                marks = "\n".join(marks) if isinstance(marks,list) else marks
                cells.append((row+2,day-start,marks))
    for row,column,value in cells:
        if isinstance(value,str):
            encoded = value.encode("cp1252")
            sheet += record(0x0204, struct.pack("<HHHH",row,column,0,len(encoded)) + encoded)
        else:
            sheet += record(0x0203, struct.pack("<HHHd",row,column,0,value))
    return globals_stream + sheet + record(0x000A,b"")


REGULAR = ["08:00", "12:00", "13:00", "17:00"]
LONG = ["08:00", "12:00", "13:00", "18:00"]


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "banco.sqlite3"
        dbmod.inicializar(str(self.path))
        self.conn = dbmod.conectar(str(self.path))

    def tearDown(self):
        self.conn.close()
        self.temp.cleanup()

    def employee(self, identifier="1", name="Pessoa cadastrada", **extra):
        data = {"clock_id":identifier,"name":name,"start_date":"2026-09-01"}
        data.update(extra)
        return core.save_employee(self.conn,data,"gerencia")

    def schedule(self, employee, effective="2026-09-01", daily=480, **extra):
        data = {"effective_date":effective,"weekdays":{str(i):daily if i<5 else 240 if i==5 else 0 for i in range(7)},
                "reason":"Jornada contratual: 44 horas semanais"}
        data.update(extra)
        return core.save_schedule(self.conn,employee["id"],data,"gerencia")

    def import_file(self, data, filename="mensal.xls"):
        return core.import_xls(self.conn,data,filename,"gerencia")

    def report(self, employee, month="2026-09"):
        return core.monthly_report(self.conn,employee["id"],month)

    def row(self, employee, day, month="2026-09"):
        return next(r for r in self.report(employee,month)["rows"] if r["date"]==day)

    def test_unknown_ids_associate_on_registration_without_matching_names(self):
        data = workbook([("001","Nome do relógio",{1:REGULAR}),("2","Outra pessoa",{})])
        imported = self.import_file(data)
        self.assertEqual(imported["unknown_ids"],["1","2"])
        self.assertEqual(core.pending_ids(self.conn)[0]["first_date"],"2026-09-01")
        employee = self.employee("1","Nome corrigido pela gerência")
        self.schedule(employee)
        self.assertEqual(self.row(employee,"2026-09-01")["punches"],REGULAR)
        self.assertEqual([r["clock_id"] for r in core.pending_ids(self.conn)],["2"])
        batch = core.get_import(self.conn, imported["id"])
        self.assertEqual(batch["employees"][0]["employee_id"],employee["id"])
        self.assertEqual(batch["employee_count"],2)
        self.assertEqual(batch["record_count"],60)

    def test_sha_duplicate_does_not_change_data_or_audit(self):
        data = workbook([("1","Pessoa",{1:REGULAR})])
        first = self.import_file(data)
        second = self.import_file(data,"renomeado.xls")
        self.assertTrue(second["duplicate"])
        self.assertEqual(first["id"],second["id"])
        self.assertEqual(len(core.list_imports(self.conn)),1)
        self.assertEqual(len(core.audit_entries(self.conn)),1)
        self.assertEqual(self.conn.execute("SELECT file_bytes FROM bh_imports").fetchone()[0],data)

    def test_conflicting_overlap_keeps_original_and_requires_review(self):
        employee = self.employee()
        self.schedule(employee)
        self.import_file(workbook([("1","Pessoa",{1:REGULAR})]))
        second = self.import_file(workbook([("1","Pessoa diferente",{1:LONG})]))
        self.assertEqual(second["conflicts"],1)
        self.assertEqual(second["ignored"],29)
        self.assertTrue(any("nome" in warning for warning in second["warnings"]))
        row = self.row(employee,"2026-09-01")
        self.assertEqual(row["original_punches"],REGULAR)
        self.assertEqual(row["punches"],REGULAR)
        self.assertEqual(row["status"],"conflict")
        self.assertIsNone(row["delta_minutes"])
        core.correct_day(self.conn,employee["id"],"2026-09-01",LONG,"normal","Conferido com a gerência","gerencia")
        self.assertEqual(self.row(employee,"2026-09-01")["delta_minutes"],60)
        self.assertTrue(self.report(employee)["complete"])
        before = self.report(employee)["final_balance"]
        self.import_file(workbook([("1","Pessoa terceira versão",{1:LONG})]))
        self.assertEqual(self.row(employee,"2026-09-01")["status"],"conflict")
        self.assertNotEqual(self.report(employee)["final_balance"],before)

    def test_empty_covered_days_are_folga_but_uncovered_workdays_are_pending(self):
        employee = self.employee()
        self.schedule(employee)
        self.import_file(workbook([("1","Pessoa",{})],end=22))
        report = self.report(employee)
        covered = self.row(employee,"2026-09-22")
        self.assertEqual(covered["kind"],"folga")
        self.assertTrue(covered["automatic_folga"])
        self.assertEqual(covered["status_label"],"Folga (sem batidas)")
        self.assertEqual(covered["expected_minutes"],0)
        self.assertEqual(covered["delta_minutes"],0)
        self.assertEqual(self.row(employee,"2026-09-23")["status"],"missing_punches")
        self.assertFalse(self.row(employee,"2026-09-27")["pending"])
        self.assertEqual(report["current_pending_count"],7)
        self.assertFalse(report["complete"])
        self.assertEqual(report["movement"],0)

    def test_classification_can_replace_automatic_folga_without_erasing_original(self):
        employee = self.employee()
        self.schedule(employee)
        self.import_file(workbook([("1","Pessoa",{1:REGULAR})]))
        core.correct_day(self.conn,employee["id"],"2026-09-02",[],"falta","Falta confirmada","gerencia")
        row = self.row(employee,"2026-09-02")
        self.assertEqual(row["delta_minutes"],-480)
        self.assertFalse(row["automatic_folga"])
        core.correct_day(self.conn,employee["id"],"2026-09-02",[],"abono","Atestado","gerencia")
        row = self.row(employee,"2026-09-02")
        self.assertEqual(row["worked_minutes"],0)
        self.assertEqual(row["credited_minutes"],480)
        self.assertEqual(row["delta_minutes"],0)
        core.correct_day(self.conn,employee["id"],"2026-09-01",[],"normal","Batidas pertenciam a outro dia","gerencia")
        row = self.row(employee,"2026-09-01")
        self.assertEqual(row["kind"],"folga")
        self.assertEqual(row["original_punches"],REGULAR)
        self.assertEqual(row["punches"],[])
        entry = core.audit_entries(self.conn,employee["id"])[0]
        self.assertEqual(entry["before"]["original_punches"],REGULAR)
        self.assertEqual(entry["after"]["punches"],[])
        self.assertEqual(entry["reason"],"Batidas pertenciam a outro dia")

    def test_corrections_and_adjustments_recalculate_following_month_balance(self):
        employee = self.employee(opening_balance_minutes=120)
        self.schedule(employee)
        self.import_file(workbook([("1","Pessoa",{1:REGULAR,2:LONG})]))
        report = self.report(employee)
        self.assertEqual((report["previous_balance"],report["movement"],report["final_balance"]),(120,60,180))
        core.correct_day(self.conn,employee["id"],"2026-09-01",LONG,"normal","Saída conferida","gerencia")
        core.add_adjustment(self.conn,employee["id"],"2026-09-10",-30,"Compensação","gerencia")
        report = self.report(employee)
        self.assertEqual((report["movement"],report["final_balance"]),(90,210))
        self.assertEqual(report["adjustments"][0]["minutes"],-30)
        following = self.report(employee,"2026-10")
        self.assertEqual(following["previous_balance"],210)
        self.assertEqual(following["previous_pending_count"],0)
        self.assertGreater(following["current_pending_count"],0)

    def test_previous_uncovered_days_prevent_finalizing_later_month(self):
        employee = self.employee()
        self.schedule(employee)
        self.import_file(workbook([("1","Pessoa",{})],end=22))
        self.import_file(workbook([("1","Pessoa",{})],month=10,end=31))
        following = self.report(employee,"2026-10")
        self.assertEqual(following["current_pending_count"],0)
        self.assertEqual(following["previous_pending_count"],7)
        self.assertFalse(following["complete"])

    def test_effective_schedule_changes_and_same_date_corrections_keep_audit(self):
        employee = self.employee()
        initial = self.schedule(employee)
        self.import_file(workbook([("1","Pessoa",{1:REGULAR,15:REGULAR})]))
        self.schedule(employee,effective="2026-09-15",daily=240,
                      weekdays={str(i):240 if i<5 else 0 for i in range(7)},reason="Contrato de 20 horas")
        self.assertEqual(self.row(employee,"2026-09-01")["delta_minutes"],0)
        self.assertEqual(self.row(employee,"2026-09-15")["delta_minutes"],240)
        corrected = self.schedule(employee,daily=420,reason="Correção de jornada cadastrada")
        self.assertEqual(corrected["id"],initial["id"])
        self.assertEqual(self.row(employee,"2026-09-01")["delta_minutes"],60)
        self.assertEqual(self.row(employee,"2026-09-15")["delta_minutes"],240)
        audit = core.audit_entries(self.conn,employee["id"])[0]
        self.assertEqual(audit["action"],"schedule_updated")
        self.assertEqual(audit["before"]["weekdays"]["0"],480)
        self.assertEqual(audit["after"]["weekdays"]["0"],420)
        self.assertEqual(audit["reason"],"Correção de jornada cadastrada")

    def test_two_punch_policies_require_explicit_rule_and_preserve_break_validation(self):
        employee = self.employee()
        self.schedule(employee)
        self.import_file(workbook([("1","Pessoa",{1:["08:00","18:00"],2:["08:00","12:00","12:30","17:00"]})]))
        self.assertIsNone(self.row(employee,"2026-09-01")["delta_minutes"])
        self.schedule(employee,two_punch_policy="continuous",reason="Jornada contínua confirmada")
        self.assertEqual(self.row(employee,"2026-09-01")["worked_minutes"],600)
        self.schedule(employee,two_punch_policy="deduct",required_break_minutes=60,deduct_break_minutes=60,
                      reason="Intervalo fixo de uma hora")
        self.assertEqual(self.row(employee,"2026-09-01")["worked_minutes"],540)
        self.assertIsNone(self.row(employee,"2026-09-02")["delta_minutes"])
        self.assertEqual(self.row(employee,"2026-09-02")["break_minutes"],30)
        self.schedule(employee,two_punch_policy="deduct",required_break_minutes=30,deduct_break_minutes=60,
                      reason="Intervalo mínimo ajustado")
        self.assertEqual(self.row(employee,"2026-09-02")["delta_minutes"],30)

    def test_malformed_and_overnight_imports_remain_pending_not_folga(self):
        employee = self.employee()
        self.schedule(employee,two_punch_policy="continuous")
        self.import_file(workbook([("1","Pessoa",{1:"08:XX\n17:00",2:["22:00","06:00"],3:["08:00"]})]))
        for day in ("2026-09-01","2026-09-02","2026-09-03"):
            row = self.row(employee,day)
            self.assertEqual(row["status"],"review")
            self.assertFalse(row["automatic_folga"])
            self.assertIsNone(row["delta_minutes"])

    def test_no_schedule_does_not_invent_credit_or_debit(self):
        employee = self.employee()
        self.import_file(workbook([("1","Pessoa",{1:REGULAR})]))
        report = self.report(employee)
        self.assertEqual(report["movement"],0)
        self.assertEqual(report["current_pending_count"],30)
        self.assertEqual(self.row(employee,"2026-09-01")["status"],"missing_schedule")

    def test_inactive_employee_preserves_history_and_cannot_reuse_identifier(self):
        employee = self.employee()
        self.schedule(employee)
        self.import_file(workbook([("1","Pessoa",{1:LONG,15:LONG})]))
        updated = core.save_employee(self.conn,{"active":False,"end_date":"2026-09-10","reason":"Desligamento"},"gerencia",employee["id"])
        self.assertFalse(updated["active"])
        self.assertEqual(core.list_employees(self.conn,False),[])
        self.assertEqual(len(core.list_employees(self.conn)),1)
        self.assertEqual(self.row(employee,"2026-09-15")["status"],"not_employed")
        self.assertEqual(self.report(employee)["final_balance"],60)
        with self.assertRaises(ValueError):
            self.employee("001","Outra pessoa")
        with self.assertRaises(ValueError):
            core.save_employee(self.conn,{"clock_id":"2","reason":"Alteração"},"gerencia",employee["id"])
        self.assertEqual(core.audit_entries(self.conn,employee["id"])[0]["reason"],"Desligamento")

    def test_correction_validation_rejects_invalid_changes_atomically(self):
        employee = self.employee()
        for punches, kind, reason in [(["24:00"],"normal","Motivo"),
                                      (["08:00","08:00"],"normal","Motivo"),
                                      (["17:00","08:00"],"normal","Motivo"),
                                      (REGULAR,"normal",""),(REGULAR,"falta","Motivo"),
                                      ([],"classificacao_invalida","Motivo")]:
            with self.subTest(punches=punches,kind=kind,reason=reason), self.assertRaises(ValueError):
                core.correct_day(self.conn,employee["id"],"2026-09-01",punches,kind,reason,"gerencia")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM bh_corrections").fetchone()[0],0)
        with self.assertRaises(ValueError):
            core.save_employee(self.conn,{"name":"Novo nome"},"gerencia",employee["id"])
        with self.assertRaises(ValueError):
            self.schedule(employee,reason="")

    def test_failed_import_rolls_back_original_file_rows_and_audit(self):
        self.conn.execute("""CREATE TRIGGER reject_second_employee BEFORE INSERT ON bh_import_rows
            WHEN NEW.clock_id='2' BEGIN SELECT RAISE(ABORT,'simulated failure'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            self.import_file(workbook([("1","Primeira",{1:REGULAR}),("2","Segunda",{})]))
        for table in ("bh_imports","bh_import_rows","bh_audit_log"):
            self.assertEqual(self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0],0)

    def test_invalid_workbook_and_duplicate_employee_block_before_saving(self):
        for data in (b"not an XLS file",workbook([("1","Pessoa",{}),("1","Pessoa repetida",{})])):
            with self.assertRaises(ValueError):
                self.import_file(data)
        self.assertEqual(core.list_imports(self.conn),[])

    def test_public_audit_participates_in_callers_transaction(self):
        core.log_audit(self.conn,"gerencia","setting_updated","Alteração local",before={"name":"A"},after={"name":"B"})
        self.conn.rollback()
        self.assertEqual(core.audit_entries(self.conn),[])
        with self.conn:
            core.log_audit(self.conn,"gerencia","setting_updated","Alteração local",before={"name":"A"},after={"name":"B"})
        self.assertEqual(core.audit_entries(self.conn)[0]["after"],{"name":"B"})

    def test_uploaded_example_when_available(self):
        source = Path("/workspace/attachments/dc0f7799-dc29-49d0-b7cb-743876901116/001_2026_9_MON.XLS")
        if not source.exists():
            self.skipTest("Arquivo de exemplo somente disponível no ambiente de desenvolvimento")
        imported = self.import_file(source.read_bytes(),source.name)
        self.assertEqual(imported["inserted"],132)
        self.assertEqual(imported["unknown_ids"],["1","2","3","4","7","9"])
        self.assertEqual(imported["period_end"],"2026-09-22")
        employee = self.employee("7","Nome ajustado")
        self.schedule(employee)
        self.assertEqual(self.row(employee,"2026-09-01")["worked_minutes"],534)
        self.assertIsNone(self.row(employee,"2026-09-02")["delta_minutes"])
        self.assertEqual(self.row(employee,"2026-09-03")["status_label"],"Folga (sem batidas)")


if __name__ == "__main__":
    unittest.main()


