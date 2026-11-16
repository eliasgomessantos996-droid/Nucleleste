"""Monthly planning, independent from attendance and financial balances."""
from datetime import date, timedelta
import html
import io
from pathlib import Path

from . import core

KINDS = {"trabalho": "Trabalho", "ferias": "Férias", "folga": "Folga",
         "feriado": "Feriado", "afastamento": "Afastamento", "falta": "Falta", "outro": "Outra ausência"}
CODES = {"trabalho": "T", "ferias": "FE", "folga": "FO", "feriado": "FD",
         "afastamento": "AF", "falta": "FA", "outro": "OU", "fora": "-"}


def _minute(value):
    punches = core._validate_punches([value])
    return int(punches[0][:2]) * 60 + int(punches[0][3:])


def _time(minutes):
    return f"{minutes // 60:02}:{minutes % 60:02}"


def monthly_roster(conn, month):
    start, end = core._month_bounds(month)
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    staff = []
    pending = 0
    for record in core.list_employees(conn):
        # Inactive people with a dated termination still appear in their historical month.
        if (not record["active"] and not record["end_date"]) or record["start_date"] > end.isoformat() or (record["end_date"] and record["end_date"] < start.isoformat()):
            continue
        employee = core.get_employee(conn, record["id"])
        overrides = {r["date"]: dict(r) for r in conn.execute(
            "SELECT * FROM bh_roster_days WHERE employee_id=? AND date BETWEEN ? AND ?",
            (employee["id"], start.isoformat(), end.isoformat()))}
        rows = []
        for day in days:
            iso = day.isoformat()
            row = {"date": iso, "kind": "fora", "start_time": "", "end_time": "", "break_minutes": 0, "note": "", "pending": False}
            if core._within_employment(employee, iso):
                schedule = next((s for s in reversed(employee["schedules"]) if s["effective_date"] <= iso), None)
                row["kind"] = "trabalho" if day.weekday() < 5 else "folga"
                if row["kind"] == "trabalho":
                    minutes = schedule["weekdays"][str(day.weekday())] if schedule else 0
                    rest = schedule["required_break_minutes"] if schedule else 0
                    if minutes <= 0 or 480 + minutes + rest >= 1440:
                        row["pending"] = True
                    else:
                        row.update(start_time="08:00", end_time=_time(480 + minutes + rest), break_minutes=rest)
                if iso in overrides:
                    row.update(overrides[iso], pending=False)
            row['work_minutes'] = None if row['pending'] else 0
            if row['kind'] == 'trabalho' and not row['pending']:
                row['work_minutes'] = _minute(row['end_time']) - _minute(row['start_time']) - row['break_minutes']
            row["label"] = KINDS.get(row["kind"], "Fora do vínculo")
            row["code"] = CODES[row["kind"]]
            row["hours"] = (f"{row['start_time']}-{row['end_time']}" if row["kind"] == "trabalho" and not row["pending"] else "Jornada pendente" if row["pending"] else row["label"])
            pending += int(row["pending"])
            rows.append(row)
        staff.append({"employee": employee, "rows": rows, 'planned_minutes': sum(r['work_minutes'] or 0 for r in rows)})
    return {"month": month, "days": days, "staff": staff, "pending_count": pending}


def save_days(conn, employee_id, start, end, kind, start_time, end_time, rest, note, actor, reset=False):
    employee = core.get_employee(conn, employee_id)
    start, end = core._date(start), core._date(end)
    if end < start or (date.fromisoformat(end) - date.fromisoformat(start)).days > 365:
        raise ValueError("Informe um período de até 366 dias, com término após o início.")
    if not core._within_employment(employee, start) or not core._within_employment(employee, end):
        raise ValueError("O período deve estar dentro do vínculo do colaborador.")
    note = core._reason(note)
    if kind not in KINDS:
        raise ValueError("Marcação da escala inválida.")
    rest = core._integer(rest, "Intervalo", 0, 1439)
    if kind == "trabalho" and not reset:
        first, last = _minute(start_time), _minute(end_time)
        if last <= first or last - first <= rest:
            raise ValueError("O horário final deve ser maior que o início e permitir o intervalo informado.")
    else:
        start_time, end_time, rest = "", "", 0
    before = [dict(r) for r in conn.execute("SELECT * FROM bh_roster_days WHERE employee_id=? AND date BETWEEN ? AND ?", (employee_id, start, end))]
    with conn:
        cursor = date.fromisoformat(start)
        while cursor.isoformat() <= end:
            if reset:
                conn.execute("DELETE FROM bh_roster_days WHERE employee_id=? AND date=?", (employee_id, cursor.isoformat()))
            else:
                conn.execute("""INSERT INTO bh_roster_days VALUES (?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(employee_id,date) DO UPDATE SET kind=excluded.kind,start_time=excluded.start_time,
                    end_time=excluded.end_time,break_minutes=excluded.break_minutes,note=excluded.note,
                    actor=excluded.actor,updated_at=excluded.updated_at""",
                    (employee_id, cursor.isoformat(), kind, start_time, end_time, rest, note, actor, core._now()))
            cursor += timedelta(days=1)
        core.log_audit(conn, actor, "roster_updated", note, employee_id=employee_id, before=before,
                       after={"start": start, "end": end, "kind": kind, "start_time": start_time, "end_time": end_time, "break_minutes": rest, "reset": reset})


def render_roster(report, company):
    """Escala mensal com identificação da clínica e carga líquida por dia."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    if report["pending_count"] or not report["staff"]:
        raise ValueError("Cadastre a equipe e resolva as jornadas pendentes antes de imprimir a escala.")
    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=landscape(A4), leftMargin=12*mm,
                            rightMargin=12*mm, topMargin=36*mm, bottomMargin=16*mm,
                            title=f"Escala de trabalho - {report['month']}", author=company)
    styles = getSampleStyleSheet()
    small = ParagraphStyle("RosterCell", fontName="Helvetica", fontSize=7, leading=9)
    cabecalho = ParagraphStyle('EscalaCabecalho', parent=small, textColor=colors.white, fontName='Helvetica-Bold')
    nome_clinica = ParagraphStyle('EscalaClinica', parent=small, fontSize=9, leading=11, textColor=colors.HexColor('#475569'))
    styles['Heading2'].textColor = colors.HexColor('#255f39')
    title = f"Escala de trabalho - {report['month'][5:]}/{report['month'][:4]}"
    logo = Path(__file__).resolve().parents[1] / 'static' / 'img' / 'logo' / 'verde-claro.png'
    story = [Paragraph('Visão mensal da equipe', styles['Heading2']),
             Paragraph("Segunda a sexta com trabalho previsto; sábados e domingos por exceção. Os horários sugeridos começam às 08h e seguem a jornada vigente. Estagiários sem cálculo de banco de horas.", styles["Normal"]), Spacer(1, 5*mm)]
    header = ["Colaborador"] + [f"{d.day:02}\n{core.WEEKDAYS[d.weekday()]}" for d in report["days"]]
    data = [header]
    for item in report["staff"]:
        e = item["employee"]
        data.append([Paragraph(html.escape(e["name"] + (" (Estágio)" if e["is_intern"] else "")), small)] + [r["code"] for r in item["rows"]])
    widths = [55*mm] + [(doc.width - 55*mm)/len(report["days"])]*len(report["days"])
    table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    instructions = [("BACKGROUND", (0,0), (-1,0), colors.HexColor("#255f39")), ("TEXTCOLOR", (0,0), (-1,0), colors.white),
                    ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"), ("FONTSIZE", (0,0), (-1,-1), 7),
                    ("ALIGN", (1,0), (-1,-1), "CENTER"), ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
                    ("LINEBELOW", (0,0), (-1,-1), .3, colors.HexColor("#d5e1e5")),
                    ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor('#f5f8f6')]),
                    ("LEFTPADDING", (1,0), (-1,-1), 1), ("RIGHTPADDING", (1,0), (-1,-1), 1),
                    ("TOPPADDING", (0,0), (-1,-1), 6), ("BOTTOMPADDING", (0,0), (-1,-1), 6)]
    for i, day in enumerate(report["days"], 1):
        if day.weekday() >= 5:
            instructions.append(("BACKGROUND", (i,1), (i,-1), colors.HexColor("#edf4f6")))
    table.setStyle(TableStyle(instructions))
    story += [table, Spacer(1,4*mm), Paragraph("<b>Legenda</b> - T: Trabalho | FE: Férias | FO: Folga | FD: Feriado | AF: Afastamento | FA: Falta | OU: Outra ausência | -: Fora do vínculo", small),
              Spacer(1, 2*mm), Paragraph('Horários, intervalos e carga diária estão detalhados nas páginas de cada colaborador.', small)]
    for item in report["staff"]:
        e = item["employee"]
        story += [PageBreak(), Paragraph(html.escape(e["name"]) + (" - Estágio (sem banco de horas)" if e["is_intern"] else ""), styles["Heading2"]),
                  Paragraph(f"Número I: {html.escape(e['clock_id'])} | Carga planejada no mês: {_time(item['planned_minutes'])}", nome_clinica), Spacer(1, 3*mm)]
        detail = [[Paragraph(c, cabecalho) for c in ["Data", "Dia", "Marcação", "Entrada", "Saída", "Intervalo", "Carga diária", "Observação"]]]
        for row, day in zip(item["rows"], report["days"]):
            if row["kind"] == "fora":
                continue
            detail.append([day.strftime("%d/%m"), core.WEEKDAYS[day.weekday()], row["label"], row["start_time"] or "-",
                           row["end_time"] or "-", _time(row['break_minutes']), _time(row['work_minutes']), Paragraph(html.escape(row["note"]), small)])
        details = Table(detail, colWidths=[18*mm,14*mm,28*mm,20*mm,20*mm,22*mm,22*mm,doc.width-144*mm], repeatRows=1)
        details.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#255f39")), ("TEXTCOLOR",(0,0),(-1,0),colors.white), ("FONTSIZE",(0,0),(-1,-1),8),
                                    ("LEADING",(0,0),(-1,-1),9),
                                    ("VALIGN",(0,0),(-1,-1),"TOP"), ("LINEBELOW",(0,0),(-1,-1),.3,colors.HexColor("#d5e1e5")),
                                    ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white, colors.HexColor('#f5f8f6')]),
                                    ("TOPPADDING",(0,0),(-1,-1),4), ("BOTTOMPADDING",(0,0),(-1,-1),4)]))
        story += [details, Spacer(1, 3*mm), Paragraph('<b>Carga diária</b> = saída - entrada - intervalo. Folgas e ausências: carga planejada zero. Intervalos expressos em duração (HH:MM).', small)]
    def footer(canvas, document):
        canvas.saveState()
        if logo.is_file():
            canvas.drawImage(str(logo), 12*mm, 183*mm, width=40*mm, height=40*mm*.396,
                             mask='auto', preserveAspectRatio=True)
        canvas.setFillColor(colors.HexColor('#255f39'))
        canvas.setFont('Helvetica-Bold', 17)
        canvas.drawString(60*mm, 196*mm, title)
        clinica = Paragraph(html.escape(company), nome_clinica)
        _, altura = clinica.wrap(225*mm, 40*mm)
        clinica.drawOn(canvas, 60*mm, 191*mm - altura)
        canvas.setStrokeColor(colors.HexColor('#cdd6d1'))
        canvas.line(12*mm, 179*mm, 285*mm, 179*mm)
        canvas.setFillColor(colors.HexColor('#475569'))
        canvas.setFont("Helvetica",8)
        canvas.drawString(12*mm, 7*mm, "Escala planejada. Marcações não alteram o ponto ou os saldos.")
        canvas.drawRightString(285*mm, 7*mm, f"Página {document.page}")
        canvas.restoreState()
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()
