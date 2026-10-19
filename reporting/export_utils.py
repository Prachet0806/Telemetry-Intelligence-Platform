# reporting/export_utils.py
"""Export & API helpers (#16): CSV/PDF report generation from a brief."""
from __future__ import annotations

import csv
import io


def brief_to_csv(brief: dict) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    def safe(value):
        text = str(value if value is not None else "")
        if text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
            return "'" + text
        return text

    w.writerow(["field", "value"])
    w.writerow(["Severity", safe(brief.get("Severity", ""))])
    w.writerow(["Exposure", safe(brief.get("Estimated Financial Exposure", ""))])
    w.writerow(["Confidence", safe(brief.get("Confidence Level", ""))])
    w.writerow(["Generated At", safe(brief.get("Generated At", ""))])
    for a in brief.get("Recommended Actions", []) or []:
        w.writerow(["Action", safe(a)])
    for k, v in (brief.get("Signal Summary", {}) or {}).items():
        w.writerow([safe(f"Signal:{k}"), safe(v)])
    return buf.getvalue()


def brief_to_pdf_bytes(brief: dict) -> bytes:
    """Generate a valid PDF report using the required reportlab dependency."""
    try:
        from reportlab.lib.pagesizes import letter  # type: ignore
        from reportlab.pdfgen import canvas  # type: ignore
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=letter)
        y = 750
        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, y, "Decision Intelligence Brief")
        y -= 24
        c.setFont("Helvetica", 10)
        for line in [f"Severity: {brief.get('Severity')}",
                     f"Exposure: {brief.get('Estimated Financial Exposure')}",
                     f"Confidence: {brief.get('Confidence Level')}",
                     f"Generated: {brief.get('Generated At')}",
                     "", "Recommended Actions:"] + \
                    [f"- {a}" for a in (brief.get("Recommended Actions", []) or [])]:
            c.drawString(50, y, str(line)[:100])
            y -= 14
            if y < 50:
                c.showPage()
                y = 750
        c.save()
        return buf.getvalue()
    except ImportError as exc:
        raise RuntimeError("PDF export requires reportlab") from exc
