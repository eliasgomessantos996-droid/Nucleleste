"""Formatação de horas e datas e o PDF do relatório mensal para assinatura."""
from __future__ import annotations

import html
import io
from datetime import date, datetime
from typing import Any, Mapping

MONTHS = (
    "", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
)




def format_minutes(value: int | None, signed: bool = False) -> str:
    if value is None:
        return "—"
    minutes = int(value)
    prefix = "-" if minutes < 0 else "+" if signed and minutes > 0 else ""
    hours, remainder = divmod(abs(minutes), 60)
    return f"{prefix}{hours:02d}:{remainder:02d}"


def date_br(value: str | date | datetime | None) -> str:
    if not value:
        return "—"
    if isinstance(value, (date, datetime)):
        return value.strftime("%d/%m/%Y")
    try:
        return date.fromisoformat(str(value)[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return str(value)


def _text(value: Any) -> str:
    return html.escape(str(value if value is not None else "")).replace("\n", "<br/>")


def _punches(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return " · ".join(str(item) for item in value)
    return str(value or "—")


def _issued_label(value: str | datetime | None) -> str:
    if isinstance(value, datetime):
        instant = value.astimezone() if value.tzinfo else value
        return instant.strftime("%d/%m/%Y às %H:%M")
    if not value:
        return datetime.now().strftime("%d/%m/%Y às %H:%M")
    try:
        instant = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if instant.tzinfo:
            instant = instant.astimezone()
        return instant.strftime("%d/%m/%Y às %H:%M")
    except ValueError:
        return str(value)


def render_report(
    report: Mapping[str, Any], company_name: str, version: int, issued_at: str | datetime
) -> bytes:
    """Render a monthly statement without exposing technical or credential data."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    buffer = io.BytesIO()
    page_width, page_height = A4
    styles = getSampleStyleSheet()
    body = ParagraphStyle("StatementBody", parent=styles["Normal"], fontName="Helvetica", fontSize=8, leading=11)
    small = ParagraphStyle("StatementSmall", parent=body, fontSize=7, leading=9)
    centered = ParagraphStyle("StatementCentered", parent=body, alignment=TA_CENTER)
    heading = ParagraphStyle("StatementHeading", parent=body, fontName="Helvetica-Bold", fontSize=10, leading=13)
    muted = ParagraphStyle("StatementMuted", parent=body, textColor=colors.HexColor("#475569"))
    employee = report.get("employee") or {}
    employee_name = employee.get("name", report.get("employee_name", ""))
    employee_id = employee.get("clock_id", report.get("clock_id", ""))
    month = str(report.get("month", ""))
    try:
        year, month_number = map(int, month.split("-"))
        period = f"{MONTHS[month_number]} de {year}"
    except (ValueError, IndexError):
        period = month
    pending_count = int(report.get("pending_count", 0))
    complete = bool(report.get("complete", pending_count == 0))
    status = "Relatório definitivo" if complete else "Rascunho — pendências de conferência"
    timestamp = _issued_label(issued_at)
    company = Paragraph(f"<b>{_text(company_name)}</b>", body)
    identity = Paragraph(f"<b>Funcionário:</b> {_text(employee_name)} &nbsp; <b>Número I:</b> {_text(employee_id)}", body)
    _, company_height = company.wrap(page_width - 30 * mm, page_height)
    _, identity_height = identity.wrap(page_width - 30 * mm, page_height)
    company_y = page_height - 16 * mm - 14 - company_height
    identity_y = company_y - 3 - identity_height
    metadata_y = identity_y - 12
    separator_y = metadata_y - 6

    def page_header(canvas: Any, document: Any) -> None:
        canvas.saveState()
        canvas.setTitle(f"Banco de Horas — {employee_name} — {period}")
        canvas.setAuthor(company_name or "Banco de Horas")
        if not complete:
            canvas.saveState()
            canvas.translate(page_width / 2, page_height / 2)
            canvas.rotate(35)
            canvas.setFillColor(colors.HexColor("#eeeeee"))
            canvas.setFont("Helvetica-Bold", 64)
            canvas.drawCentredString(0, 0, "RASCUNHO")
            canvas.restoreState()
        y = page_height - 16 * mm
        canvas.setFillColor(colors.HexColor("#0f172a"))
        canvas.setFont("Helvetica-Bold", 15)
        canvas.drawString(15 * mm, y, "Banco de Horas")
        canvas.setFont("Helvetica", 9)
        canvas.drawRightString(page_width - 15 * mm, y, period)
        # Wrapping and a matching frame margin preserve long names without
        # colliding with the status line or silently truncating company names.
        company.drawOn(canvas, 15 * mm, company_y)
        identity.drawOn(canvas, 15 * mm, identity_y)
        canvas.setFont("Helvetica", 8)
        canvas.drawString(15 * mm, metadata_y, f"{status} • Versão {version} • Emitido em {timestamp}")
        canvas.setStrokeColor(colors.HexColor("#cbd5e1"))
        canvas.line(15 * mm, separator_y, page_width - 15 * mm, separator_y)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(15 * mm, 12 * mm, f"Número I: {employee_id} • {month} • Versão {version}")
        canvas.drawRightString(page_width - 15 * mm, 12 * mm, f"Página {document.page}")
        canvas.restoreState()

    document = SimpleDocTemplate(
        buffer, pagesize=A4, rightMargin=15 * mm, leftMargin=15 * mm,
        topMargin=page_height - separator_y + 8, bottomMargin=20 * mm,
        title=f"Banco de Horas — {employee_name} — {period}", author=company_name,
    )
    story: list[Any] = []
    if not complete:
        story.append(Paragraph(
            f"<b>Conferência necessária:</b> {pending_count} dia(s) pendente(s). "
            "Os totais abaixo são provisórios; dias pendentes não compõem o saldo.", muted,
        ))
        story.append(Spacer(1, 3 * mm))
    columns = ["Dia", "Marcações", "Prevista", "Trabalhada", "Saldo", "Situação / justificativa"]
    data: list[list[Any]] = [[Paragraph(_text(item), centered) for item in columns]]
    for row in report.get("rows", []):
        marks = _punches(row.get("punches"))
        original = row.get("original_punches")
        marks_html = _text(marks)
        if original is not None and _punches(original) != marks:
            marks_html += f"<br/><font color='#64748b'>Original: {_text(_punches(original))}</font>"
        detail = str(row.get("status_label") or "")
        if row.get("status_detail"):
            detail += "\n" + str(row["status_detail"])
        if row.get("reason"):
            detail += "\n" + str(row["reason"])
        data.append([
            Paragraph(_text(date_br(row.get("date"))), centered),
            Paragraph(marks_html, small),
            Paragraph(format_minutes(row.get("expected_minutes")), centered),
            Paragraph(format_minutes(row.get("worked_minutes")), centered),
            Paragraph(format_minutes(row.get("delta_minutes"), signed=True), centered),
            Paragraph(_text(detail), small),
        ])
    if len(data) == 1:
        data.append([Paragraph("Sem lançamentos no período.", body), "", "", "", "", ""])
    table = Table(data, colWidths=[23 * mm, 48 * mm, 19 * mm, 22 * mm, 19 * mm, 49 * mm], repeatRows=1, splitByRow=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#cbd5e1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
    ]))
    story.append(table)
    adjustments = report.get("adjustments") or []
    if adjustments:
        story += [Spacer(1, 4 * mm), Paragraph("Ajustes do período", heading)]
        for adjustment in adjustments:
            description = (f"{date_br(adjustment.get('date'))}: "
                           f"{format_minutes(adjustment.get('minutes', adjustment.get('delta_minutes')), signed=True)} — "
                           f"{adjustment.get('reason', '')}")
            story.append(Paragraph(_text(description), body))
    summary = Table([
        [Paragraph("Saldo anterior", centered), Paragraph("Movimento do mês", centered), Paragraph("Saldo acumulado", centered)],
        [Paragraph(f"<b>{format_minutes(report.get('previous_balance', 0), signed=True)}</b>", centered),
         Paragraph(f"<b>{format_minutes(report.get('movement', 0), signed=True)}</b>", centered),
         Paragraph(f"<b>{format_minutes(report.get('final_balance', 0), signed=True)}</b>", centered)],
    ], colWidths=[60 * mm] * 3)
    summary.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f1f5f9")),
        ("BOX", (0, 0), (-1, -1), .5, colors.HexColor("#cbd5e1")),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    signatures = Table([
        ["________________________", "________________________", "________________________"],
        [Paragraph("Funcionário", centered), Paragraph("Gerência", centered), Paragraph("Administração", centered)],
    ], colWidths=[60 * mm] * 3)
    signatures.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("FONTNAME", (0, 0), (-1, 0), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, 0), 9), ("TOPPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(KeepTogether([
        Spacer(1, 4 * mm), Paragraph("Resumo para assinatura", heading), Spacer(1, 2 * mm), summary,
        Spacer(1, 3 * mm), Paragraph("Declaro ter conferido as marcações e os ajustes apresentados neste relatório.", muted),
        Spacer(1, 10 * mm), signatures, Spacer(1, 4 * mm),
        Paragraph("Data da assinatura: ______ / ______ / __________", body),
    ]))
    document.build(story, onFirstPage=page_header, onLaterPages=page_header)
    return buffer.getvalue()
