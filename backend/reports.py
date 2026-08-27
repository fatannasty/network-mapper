"""Executive report generation: HTML (printable) + PDF + optional SMTP email.

Scheduled by a background loop in main.py; also callable on demand.
"""

from __future__ import annotations

import os
import smtplib
import ssl
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

REPORTS_DIR = os.environ.get(
    "EXEC_REPORT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reports"))

STATE_LABEL = {"healthy": "Healthy", "warning": "Needs review", "critical": "Attention required"}
STATE_COLOR = {"healthy": "#16a34a", "warning": "#d97706", "critical": "#dc2626"}


def _fmt(value: str | None) -> str:
    if not value:
        return "\u2014"
    d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return d.astimezone().strftime("%b %d, %Y %I:%M %p")


def _esc(value) -> str:
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_exec_html(summary: dict) -> str:
    k = summary.get("kpis", {})
    state = summary.get("state", "healthy")
    rows = []
    for s in summary.get("sites", []):
        freshness = "no data" if s.get("freshness_days") is None \
            else ("today" if s["freshness_days"] == 0 else f"{s['freshness_days']}d ago")
        rows.append(
            f"<tr><td>{_esc(s['site'])}</td><td class='num'>{s['devices']}</td>"
            f"<td class='num ok'>{s['up']}</td><td class='num bad'>{s['down']}</td>"
            f"<td class='num warn'>{s['flapping']}</td><td class='num'>{freshness}</td></tr>")

    risk_rows = "".join(
        f"<tr><td>{_esc(r.get('hostname') or r.get('ip'))}</td><td class='mono'>{_esc(r.get('ip',''))}</td>"
        f"<td>{_esc(r.get('site') or '')}</td><td class='bad'>{_esc(r.get('status',''))}</td></tr>"
        for r in summary.get("risks", []))
    spof_rows = "".join(
        f"<tr><td>{_esc(s.get('hostname') or s.get('ip'))}</td><td class='mono'>{_esc(s.get('ip',''))}</td>"
        f"<td>{_esc(s.get('site') or '')}</td></tr>"
        for s in summary.get("spof_devices", []))

    color = STATE_COLOR.get(state, "#16a34a")
    generated = datetime.now(timezone.utc).astimezone().strftime("%B %d, %Y %I:%M %p %Z")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Executive Network Health Report</title>
<style>
  body {{ font-family: 'Segoe UI', Arial, sans-serif; color: #1f2937; margin: 32px; }}
  h1 {{ font-size: 22px; margin: 0 0 2px; }} .sub {{ color: #6b7280; font-size: 12px; margin-bottom: 20px; }}
  .banner {{ border-left: 6px solid {color}; background: {color}14; padding: 12px 16px; border-radius: 8px; margin-bottom: 20px; }}
  .banner .lbl {{ font-size: 18px; font-weight: 700; color: {color}; }}
  .score {{ float: right; text-align: center; font-size: 26px; font-weight: 800; color: {color}; }}
  .kpis {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 20px; }}
  .kpi {{ border: 1px solid #e5e7eb; border-radius: 8px; padding: 10px 12px; }}
  .kpi .l {{ font-size: 10px; text-transform: uppercase; color: #6b7280; }}
  .kpi .v {{ font-size: 20px; font-weight: 700; margin-top: 2px; }}
  h2 {{ font-size: 14px; margin: 22px 0 8px; text-transform: uppercase; letter-spacing: .03em; color: #374151; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  th {{ text-align: left; font-size: 10px; text-transform: uppercase; color: #6b7280; border-bottom: 2px solid #e5e7eb; padding: 6px 8px; }}
  td {{ border-bottom: 1px solid #f3f4f6; padding: 6px 8px; }}
  .num {{ text-align: right; }} .mono {{ font-family: monospace; }}
  .ok {{ color: #16a34a; }} .warn {{ color: #d97706; }} .bad {{ color: #dc2626; }}
  .footer {{ margin-top: 28px; color: #9ca3af; font-size: 11px; }}
</style></head><body>
  <h1>Executive Network Health Report</h1>
  <div class="sub">Generated {generated} &middot; {summary.get('total_devices', 0)} devices tracked</div>
  <div class="banner">
    <span class="score">{summary.get('score', 0)}</span>
    <div class="lbl">{STATE_LABEL.get(state, state.title())}</div>
    <div style="font-size:12px;color:#374151;margin-top:2px">
      {k.get('devices_up', 0)} up &middot; {k.get('devices_down', 0)} down &middot;
      {k.get('devices_flapping', 0)} flapping &middot; {k.get('spof_count', 0)} single points of failure &middot;
      {k.get('stale_devices', 0)} stale
    </div>
  </div>
  <div class="kpis">
    <div class="kpi"><div class="l">Operational</div><div class="v">{k.get('up_pct', 0)}%</div></div>
    <div class="kpi"><div class="l">Config coverage</div><div class="v">{k.get('config_coverage', 0)}%</div></div>
    <div class="kpi"><div class="l">Site coverage</div><div class="v">{k.get('site_coverage', 0)}%</div></div>
    <div class="kpi"><div class="l">Link validation</div><div class="v">{k.get('link_validation', 0)}%</div></div>
  </div>
  <h2>Site freshness</h2>
  <table><thead><tr><th>Site</th><th class="num">Devices</th><th class="num">Up</th>
    <th class="num">Down</th><th class="num">Flap</th><th class="num">Last seen</th></tr></thead>
    <tbody>{rows or '<tr><td colspan=6>No sites recorded.</td></tr>'}</tbody></table>
  <h2>Risks &amp; issues</h2>
  <table><thead><tr><th>Device</th><th>IP</th><th>Site</th><th>Status</th></tr></thead>
    <tbody>{risk_rows or '<tr><td colspan=4>No down, flapping, or degraded devices.</td></tr>'}</tbody></table>
  <h2>Single points of failure</h2>
  <table><thead><tr><th>Device</th><th>IP</th><th>Site</th></tr></thead>
    <tbody>{spof_rows or '<tr><td colspan=3>No single points of failure detected.</td></tr>'}</tbody></table>
  <div class="footer">Auto-generated by Network Mapper. {generated}</div>
</body></html>"""


def _status_donut(summary):
    """Donut chart of device operational status."""
    from reportlab.graphics.charts.piecharts import Pie
    from reportlab.graphics.shapes import Drawing, String
    from reportlab.lib import colors

    k = summary.get("kpis", {})
    pairs = [
        ("up", k.get("devices_up", 0), colors.green),
        ("degraded", k.get("devices_degraded", 0), colors.orange),
        ("down", k.get("devices_down", 0), colors.red),
        ("flapping", k.get("devices_flapping", 0), colors.HexColor("#f97316")),
        ("unknown", k.get("devices_unknown", 0), colors.grey),
    ]
    pairs = [(l, v, c) for l, v, c in pairs if v]
    if not pairs:
        return None
    total = sum(v for _, v, _ in pairs)
    d = Drawing(300, 150)
    pie = Pie()
    pie.x = 30
    pie.y = 10
    pie.width = 110
    pie.height = 110
    pie.data = [v for _, v, _ in pairs]
    pie.labels = ["" for _ in pairs]
    pie.slices.strokeWidth = 0
    for i, (_, _, color) in enumerate(pairs):
        pie.slices[i].fillColor = color
    pie.innerRadiusFraction = 0.5
    d.add(pie)
    y = 140
    for label, value, color in pairs:
        d.add(String(165, y, f"{label}: {value} ({round(100.0 * value / total, 1)}%)",
                     fontSize=9, fillColor=color))
        y -= 13
    return d


def _coverage_bars(summary):
    """Grouped bar chart: coverage actuals vs targets."""
    from reportlab.graphics.charts.barcharts import VerticalBarChart
    from reportlab.graphics.shapes import Drawing, String
    from reportlab.lib import colors

    k = summary.get("kpis", {})
    items = [("Site", k.get("site_coverage", 0), 90),
             ("Interfaces", k.get("interface_coverage", 0), 95),
             ("Configs", k.get("config_coverage", 0), 90),
             ("Links", k.get("link_validation", 0), 80)]
    d = Drawing(300, 150)
    chart = VerticalBarChart()
    chart.x = 40
    chart.y = 20
    chart.width = 240
    chart.height = 110
    chart.data = [[it[1] for it in items], [it[2] for it in items]]
    chart.categoryAxis.categoryNames = [it[0] for it in items]
    chart.categoryAxis.labels.fontSize = 8
    chart.valueAxis.valueMin = 0
    chart.valueAxis.valueMax = 100
    chart.bars[0].fillColor = colors.HexColor("#22d3ee")
    chart.bars[1].fillColor = colors.HexColor("#cbd5e1")
    chart.groupSpacing = 3
    chart.barSpacing = 1
    d.add(chart)
    d.add(String(40, 5, "actual (teal) vs target (grey)", fontSize=7))
    return d


def _score_line(history):
    """Line chart of the executive health score over time."""
    from reportlab.graphics.charts.linecharts import HorizontalLineChart
    from reportlab.graphics.shapes import Drawing, String
    from reportlab.lib import colors

    pts = [(i, h.get("score", 0)) for i, h in enumerate(history)
           if h.get("score") is not None]
    if len(pts) < 2:
        return None
    d = Drawing(300, 130)
    lp = HorizontalLineChart()
    lp.x = 40
    lp.y = 20
    lp.width = 240
    lp.height = 90
    lp.data = [[s for _, s in pts]]
    lp.joinedLines = 1
    lp.lines[0].strokeColor = colors.HexColor("#22d3ee")
    lp.lines[0].strokeWidth = 2
    lp.valueAxis.valueMin = 0
    lp.valueAxis.valueMax = 100
    d.add(lp)
    d.add(String(40, 4, f"health score over {len(history)} snapshots", fontSize=7))
    return d


def _util_bars(top_util):
    """Horizontal bars of busiest interfaces (avg bits/sec)."""
    from reportlab.graphics.charts.barcharts import HorizontalBarChart
    from reportlab.graphics.shapes import Drawing, String
    from reportlab.lib import colors

    items = top_util[:6]
    if not items:
        return None
    d = Drawing(300, 150)
    chart = HorizontalBarChart()
    chart.x = 110
    chart.y = 10
    chart.width = 180
    chart.height = 120
    chart.data = [[(t.get("avg_in_rate", 0) + t.get("avg_out_rate", 0)) for t in items]]
    chart.categoryAxis.categoryNames = [
        f"{t.get('hostname') or t.get('ip')}:{t.get('if_name', '')}"[:24] for t in items]
    chart.categoryAxis.labels.fontSize = 7
    chart.bars[0].fillColor = colors.HexColor("#22d3ee")
    d.add(chart)
    d.add(String(6, 12, "avg bits/sec", fontSize=7))
    return d


def build_exec_pdf(summary: dict, path: str, history: list | None = None,
                   top_util: list | None = None) -> None:
    """Render the executive report to PDF via reportlab.

    Charts (status donut, coverage bars, health trend, busiest links) are
    best-effort: any single chart failing is skipped, never fatal.
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer, Table,
                                    TableStyle)

    k = summary.get("kpis", {})
    state = summary.get("state", "healthy")
    state_color = {"healthy": colors.green, "warning": colors.orange,
                   "critical": colors.red}.get(state, colors.green)

    styles = getSampleStyleSheet()
    title = ParagraphStyle("Title2", parent=styles["Title"], fontSize=18, spaceAfter=2)
    sub = ParagraphStyle("Sub", parent=styles["Normal"], fontSize=9, textColor=colors.grey,
                         spaceAfter=14)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=12, spaceBefore=14,
                        spaceAfter=6)
    banner = ParagraphStyle("Banner", parent=styles["Normal"], fontSize=13,
                            textColor=state_color, spaceBefore=4, spaceAfter=10)

    generated = datetime.now(timezone.utc).astimezone().strftime("%B %d, %Y %I:%M %p")
    story = [
        Paragraph("Executive Network Health Report", title),
        Paragraph(f"Generated {generated} &middot; {summary.get('total_devices', 0)} devices tracked", sub),
        Paragraph(f"{STATE_LABEL.get(state, state.title())} &mdash; health score {summary.get('score', 0)} / 100", banner),
        Paragraph(f"{k.get('devices_up', 0)} up &middot; {k.get('devices_down', 0)} down &middot; "
                  f"{k.get('devices_flapping', 0)} flapping &middot; {k.get('spof_count', 0)} SPOF &middot; "
                  f"{k.get('stale_devices', 0)} stale", sub),
        Paragraph("Key metrics", h2),
    ]
    kpi_data = [["Operational", f"{k.get('up_pct', 0)}%", "Config coverage", f"{k.get('config_coverage', 0)}%"],
                ["Site coverage", f"{k.get('site_coverage', 0)}%", "Link validation", f"{k.get('link_validation', 0)}%"]]
    kpi_table = Table(kpi_data, colWidths=[1.4 * inch, 1.4 * inch, 1.4 * inch, 1.4 * inch])
    kpi_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ("BACKGROUND", (0, 0), (-1, -1), colors.whitesmoke),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(kpi_table)

    # Charts (best-effort; a chart failure is skipped, never fatal).
    charts = [
        ("Network composition", lambda: _status_donut(summary),
         "No device status data available."),
        ("Coverage vs targets", lambda: _coverage_bars(summary),
         "No coverage data available."),
        ("Health trend", lambda: _score_line(history or []),
         "Not enough health history yet for a trend."),
        ("Busiest links (avg)", lambda: _util_bars(top_util or []),
         "No utilization data yet."),
    ]
    for chart_title, builder, note in charts:
        story.append(Paragraph(chart_title, h2))
        try:
            drawing = builder()
        except Exception:  # a chart must never break the whole report
            drawing = None
        if drawing is None:
            story.append(Paragraph(note, sub))
        else:
            story.append(drawing)

    def section(title_text: str, header: list[str], rows: list[list], empty: str):
        story.append(Paragraph(title_text, h2))
        if not rows:
            story.append(Paragraph(empty, sub))
            return
        body = [header] + rows
        t = Table(body, colWidths=[2.2 * inch, 2.2 * inch, 1.6 * inch, 1.2 * inch][:len(header)])
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.whitesmoke]),
        ]))
        story.append(t)

    section("Site freshness", ["Site", "Devices", "Up", "Down"],
            [[s["site"], str(s["devices"]), str(s["up"]), str(s["down"])]
             for s in summary.get("sites", [])],
            "No sites recorded.")
    section("Risks &amp; issues", ["Device", "IP", "Site", "Status"],
            [[r.get("hostname") or r.get("ip"), r.get("ip", ""), r.get("site", ""), r.get("status", "")]
             for r in summary.get("risks", [])],
            "No down, flapping, or degraded devices.")
    section("Single points of failure", ["Device", "IP", "Site"],
            [[s.get("hostname") or s.get("ip"), s.get("ip", ""), s.get("site", "")]
             for s in summary.get("spof_devices", [])],
            "No single points of failure detected.")

    story.append(Spacer(1, 20))
    story.append(Paragraph(f"Auto-generated by Network Mapper. {generated}", sub))
    doc = SimpleDocTemplate(path, pagesize=letter)
    doc.build(story)


def pdf_path(report_id: int) -> str:
    return os.path.join(REPORTS_DIR, f"exec-{report_id}.pdf")


def save_exec_report(db, summary: dict, title: str = "",
                     history: list | None = None,
                     top_util: list | None = None) -> object:
    """Build HTML + PDF and persist an ExecReport row. Returns the row."""
    from models import ExecReport

    html = build_exec_html(summary)
    os.makedirs(REPORTS_DIR, exist_ok=True)
    row = ExecReport(title=title or "Executive Network Health Report",
                     html=html, summary=summary)
    db.add(row)
    db.flush()  # assign id for the filename
    try:
        build_exec_pdf(summary, pdf_path(row.id), history=history, top_util=top_util)
    except Exception as exc:  # PDF is best-effort; HTML always kept
        row.error = f"pdf: {exc}"
    db.commit()
    db.refresh(row)
    return row


def send_email(subject: str, html: str, to: str | None = None,
               attachments: list[tuple[str, bytes, str]] | None = None) -> bool:
    """Send an HTML email (optionally with attachments) via SMTP when configured."""
    host = os.environ.get("SMTP_HOST", "")
    recipients = to or os.environ.get("REPORT_TO", "")
    if not host or not recipients:
        return False
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER", "")
    password = os.environ.get("SMTP_PASSWORD", "")
    sender = os.environ.get("SMTP_FROM", user or "network-mapper")

    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipients
    msg.attach(MIMEText(html, "html", "utf-8"))
    for filename, data, subtype in attachments or []:
        part = MIMEApplication(data, _subtype=subtype)
        part["Content-Disposition"] = f'attachment; filename="{filename}"'
        msg.attach(part)

    context = ssl.create_default_context()
    with smtplib.SMTP(host, port, timeout=30) as server:
        server.starttls(context=context)
        if user:
            server.login(user, password)
        server.sendmail(sender, [t.strip() for t in recipients.split(",") if t.strip()], msg.as_string())
    return True


def email_exec_report(row, summary: dict) -> bool:
    """Send the report via SMTP when configured. Returns True if sent."""
    attachments: list[tuple[str, bytes, str]] = []
    try:
        with open(pdf_path(row.id), "rb") as fh:
            attachments.append((f"exec-report-{row.id}.pdf", fh.read(), "pdf"))
    except OSError:
        pass
    subject = (f"Executive Network Health Report — "
               f"{datetime.now(timezone.utc).astimezone().strftime('%b %d, %Y')}")
    return send_email(subject, row.html, attachments=attachments)


def run_exec_report_job(db) -> dict:
    """Generate, persist, and (optionally) email an executive report."""
    from models import ExecReport, HealthSnapshot
    import repositories
    import utilization

    summary = repositories.exec_health_summary(db)
    history = [{"t": r.recorded_at.isoformat(), "score": r.score}
               for r in db.query(HealthSnapshot)
               .order_by(HealthSnapshot.recorded_at.asc()).all()]
    top_util = utilization.top_utilization(db, days=7, limit=8).get("top", [])
    row = save_exec_report(db, summary, history=history, top_util=top_util)
    try:
        row.emailed = email_exec_report(row, summary)
        db.commit()
    except Exception as exc:  # never fail the report because email broke
        row.error = f"email: {exc}"
        db.commit()
    db.refresh(row)
    return row.to_dict()