"""
pdf_generator.py — Generates a styled, client-ready PDF report.

Layout:
  Page 1  — Cover (dark navy, white text, dataset metadata)
  Page 2+ — Running header + footer on every page, then:
             Executive Summary · KPI Cards · Data Quality · Charts · KPI List

Public API:
    generate_pdf(data) → bytes
"""
from __future__ import annotations

import io
import re
import textwrap
from datetime import date

from fpdf import FPDF


# ── Design tokens ─────────────────────────────────────────────────────────────
NAVY    = (27,  42,  74)      # cover bg, strong headers
ACCENT  = (45, 125, 210)      # section headers, KPI bar, links
LIGHT   = (248, 250, 252)     # alternating table rows
DARK    = (30,  41,  59)      # body text
MUTED   = (100, 116, 139)     # captions, footer text
WHITE   = (255, 255, 255)
BORDER  = (226, 232, 240)     # table / card borders
CARD_BG = (241, 245, 249)     # KPI card background

PAGE_W  = 210   # A4 mm
PAGE_H  = 297
MARGIN  = 15
CONTENT_W = PAGE_W - 2 * MARGIN


# ── Public entry point ────────────────────────────────────────────────────────

def generate_pdf(data: dict) -> bytes:
    """Build the full PDF and return it as a bytes object."""
    pdf = _ReportPDF()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.set_margins(MARGIN, 18, MARGIN)

    meta     = data.get("metadata", {})
    profile  = data.get("profile", {})
    kpis     = data.get("kpis", {})
    summary  = data.get("summary", "")
    charts   = data.get("charts", {})
    pii_rpt  = meta.get("pii_report", {})
    domain   = data.get("domain", "general").title()
    filename = meta.get("filename", "Dataset")
    approved = data.get("approved_charts", None)

    # Filter charts to admin-approved selection
    if approved is not None:
        charts = {t: s for t, s in charts.items() if t in approved}

    _cover_page(pdf, filename, domain, profile)
    _summary_section(pdf, summary)
    _kpi_section(pdf, kpis)
    _quality_section(pdf, profile, pii_rpt)
    _charts_section(pdf, charts)
    _kpi_list_section(pdf, kpis.get("recommended", []))
    _disclaimer_page(pdf, filename)

    return bytes(pdf.output())


# ── Cover page ────────────────────────────────────────────────────────────────

def _cover_page(pdf: FPDF, filename: str, domain: str, profile: dict):
    pdf.add_page()

    # Full navy background
    pdf.set_fill_color(*NAVY)
    pdf.rect(0, 0, PAGE_W, PAGE_H, "F")

    # Accent bar — top
    pdf.set_fill_color(*ACCENT)
    pdf.rect(0, 0, PAGE_W, 6, "F")

    # Accent bar — bottom
    pdf.rect(0, PAGE_H - 6, PAGE_W, 6, "F")

    # Report type label
    pdf.set_text_color(150, 180, 220)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_xy(0, 68)
    pdf.cell(PAGE_W, 8, "ANALYTICS REPORT", align="C")

    # Main title
    pdf.set_text_color(*WHITE)
    pdf.set_font("Helvetica", "B", 28)
    display_name = filename if len(filename) <= 35 else filename[:32] + "..."
    pdf.set_xy(0, 82)
    pdf.cell(PAGE_W, 14, _safe(display_name), align="C")

    # Divider line
    pdf.set_draw_color(*ACCENT)
    pdf.set_line_width(0.8)
    pdf.line(55, 102, PAGE_W - 55, 102)

    # Metadata pills
    row_count    = profile.get("row_count", 0)
    completeness = profile.get("completeness_pct", 0)
    today        = date.today().strftime("%B %d, %Y")

    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(185, 210, 240)

    for i, (label, value) in enumerate([
        ("Domain",       domain),
        ("Records",      f"{row_count:,}"),
        ("Completeness", f"{completeness}%"),
        ("Prepared",     today),
    ]):
        y = 112 + i * 14
        pdf.set_xy(0, y)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(120, 155, 195)
        pdf.cell(PAGE_W, 5, _safe(label.upper()), align="C")
        pdf.set_xy(0, y + 5)
        pdf.set_font("Helvetica", "", 12)
        pdf.set_text_color(210, 228, 248)
        pdf.cell(PAGE_W, 7, _safe(str(value)), align="C")

    # Bottom confidentiality note
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(100, 130, 165)
    pdf.set_xy(0, PAGE_H - 20)
    pdf.cell(PAGE_W, 6, "Confidential - Prepared for review only. Not for external distribution.", align="C")


# ── Executive Summary ─────────────────────────────────────────────────────────

def _summary_section(pdf: FPDF, summary: str):
    pdf.add_page()
    _section_header(pdf, "Executive Summary")
    _render_markdown(pdf, summary)


# ── KPI Cards ─────────────────────────────────────────────────────────────────

def _kpi_section(pdf: FPDF, kpis: dict):
    calculated = kpis.get("calculated", {})
    if not calculated:
        return

    _maybe_new_page(pdf, needed=70)
    _section_header(pdf, "Key Performance Indicators")

    items    = list(calculated.items())[:6]
    cols     = 3
    card_w   = (CONTENT_W - (cols - 1) * 5) / cols
    card_h   = 28
    start_y  = pdf.get_y()

    for i, (name, value) in enumerate(items):
        col = i % cols
        row = i // cols
        x   = MARGIN + col * (card_w + 5)
        y   = start_y + row * (card_h + 5)

        # Card shadow / border
        pdf.set_draw_color(*BORDER)
        pdf.set_fill_color(*CARD_BG)
        pdf.set_line_width(0.3)
        pdf.rect(x, y, card_w, card_h, "FD")

        # Accent top strip
        pdf.set_fill_color(*ACCENT)
        pdf.rect(x, y, card_w, 2.5, "F")

        # Value
        pdf.set_font("Helvetica", "B", 17)
        pdf.set_text_color(*NAVY)
        pdf.set_xy(x, y + 4)
        pdf.cell(card_w, 11, _safe(str(value)), align="C")

        # Label
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(*MUTED)
        pdf.set_xy(x, y + 15)
        label = name if len(name) <= 22 else name[:19] + "..."
        pdf.cell(card_w, 8, _safe(label), align="C")

    rows_used = -(-len(items) // cols)   # ceiling
    pdf.set_y(start_y + rows_used * (card_h + 5) + 4)


# ── Data Quality ──────────────────────────────────────────────────────────────

def _quality_section(pdf: FPDF, profile: dict, pii_rpt: dict):
    _maybe_new_page(pdf, needed=80)
    _section_header(pdf, "Data Quality Overview")

    # Top-line stats table
    dup        = profile.get("duplicate_report", {})
    stats_rows = [
        ("Total Records",   f"{profile.get('row_count', 0):,}"),
        ("Total Columns",   str(profile.get("col_count", 0))),
        ("Completeness",    f"{profile.get('completeness_pct', 0)}%"),
        ("Duplicate Rows",  str(dup.get("duplicate_rows", 0))),
        ("PII Risk Level",  pii_rpt.get("risk_level", "none").upper()),
        ("PII Columns Found", str(pii_rpt.get("total_pii_columns", 0))),
    ]
    _two_col_table(pdf, stats_rows)
    pdf.ln(6)

    # Missing values (if any)
    missing = profile.get("missing_values", {})
    if missing:
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*DARK)
        pdf.cell(0, 7, "Columns with Missing Values", ln=True)
        pdf.ln(1)
        col_w = CONTENT_W / 3
        _table_header(pdf, ["Column", "Missing Count", "Missing %"], [col_w * 1.4, col_w * 0.8, col_w * 0.8])
        for i, (col, vals) in enumerate(missing.items()):
            _table_row(pdf, [col, str(vals["missing_count"]), f"{vals['missing_pct']}%"],
                       [col_w * 1.4, col_w * 0.8, col_w * 0.8], shade=(i % 2 == 0))
        pdf.ln(6)

    # Numeric summary (top 5 columns)
    num = profile.get("numeric_summary", {})
    if num:
        _maybe_new_page(pdf, needed=50)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*DARK)
        pdf.cell(0, 7, "Numeric Column Summaries", ln=True)
        pdf.ln(1)

        show_cols  = list(num.items())[:5]
        col_labels = ["Column", "Min", "Max", "Mean", "Median"]
        col_widths = [52, 30, 30, 34, 34]
        _table_header(pdf, col_labels, col_widths)
        for i, (col, s) in enumerate(show_cols):
            _table_row(pdf,
                [col, _fmt(s["min"]), _fmt(s["max"]), _fmt(s["mean"]), _fmt(s["median"])],
                col_widths, shade=(i % 2 == 0))
        pdf.ln(4)


# ── Charts ────────────────────────────────────────────────────────────────────

def _charts_section(pdf: FPDF, charts: dict):
    if not charts:
        return

    charts_added = 0
    for title, spec in charts.items():
        img_bytes = _fig_to_png(spec)
        if img_bytes is None:
            continue

        _maybe_new_page(pdf, needed=110)
        if charts_added == 0:
            _section_header(pdf, "Data Visualisations")

        # Chart title
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*DARK)
        pdf.cell(0, 7, _safe(title), ln=True)

        # Light border box around chart
        chart_h = 85
        pdf.set_draw_color(*BORDER)
        pdf.set_line_width(0.3)
        y_before = pdf.get_y()
        pdf.rect(MARGIN, y_before, CONTENT_W, chart_h, "D")

        # Embed chart image
        pdf.image(io.BytesIO(img_bytes), x=MARGIN + 1, y=y_before + 1,
                  w=CONTENT_W - 2, h=chart_h - 2)
        pdf.set_y(y_before + chart_h + 5)
        charts_added += 1


# ── Recommended KPI list ──────────────────────────────────────────────────────

def _kpi_list_section(pdf: FPDF, recommended: list):
    if not recommended:
        return

    _maybe_new_page(pdf, needed=60)
    _section_header(pdf, "Recommended KPIs to Track")

    for i, kpi in enumerate(recommended[:8], 1):
        _maybe_new_page(pdf, needed=14)
        # Number badge
        badge_x = MARGIN
        badge_y = pdf.get_y()
        pdf.set_fill_color(*ACCENT)
        pdf.set_text_color(*WHITE)
        pdf.set_font("Helvetica", "B", 8)
        pdf.rect(badge_x, badge_y + 1, 7, 7, "F")
        pdf.set_xy(badge_x, badge_y + 1)
        pdf.cell(7, 7, str(i), align="C")

        # KPI name + description
        pdf.set_xy(MARGIN + 10, badge_y)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*DARK)
        pdf.cell(0, 6, _safe(kpi["name"]), ln=True)

        pdf.set_x(MARGIN + 10)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*MUTED)
        pdf.multi_cell(CONTENT_W - 10, 5, _safe(kpi.get("description", "")), ln=True)
        pdf.ln(2)


# ── Disclaimer ────────────────────────────────────────────────────────────────

def _disclaimer_page(pdf: FPDF, filename: str):
    _maybe_new_page(pdf, needed=60)
    _section_header(pdf, "Notes & Disclaimer")

    today = date.today().strftime("%B %d, %Y")
    text  = (
        f"This report was generated on {today} from the dataset '{filename}'. "
        "All analysis is based on aggregate statistics derived from the uploaded data. "
        "No individual records, personally identifiable information (PII), or raw row data "
        "was used in the generation of this document.\n\n"
        "Sensitive columns (email addresses, phone numbers, names, and similar fields) "
        "were detected automatically and masked before any processing. "
        "KPI recommendations are based on column-name pattern matching and should be "
        "validated against your specific business context.\n\n"
        "This report is intended for internal review and client delivery only. "
        "Please verify all figures against your source systems before making business decisions."
    )

    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*DARK)
    pdf.multi_cell(0, 6, _safe(text))


# ── PDF class (running header + footer) ───────────────────────────────────────

class _ReportPDF(FPDF):
    def header(self):
        if self.page_no() == 1:
            return   # cover page has its own layout

        # Thin navy top bar
        self.set_fill_color(*NAVY)
        self.rect(0, 0, PAGE_W, 10, "F")

        self.set_font("Helvetica", "B", 8)
        self.set_text_color(*WHITE)
        self.set_xy(MARGIN, 2)
        self.cell(CONTENT_W / 2, 6, "ANALYTICS REPORT", align="L")
        self.set_xy(MARGIN, 2)
        self.set_font("Helvetica", "", 8)
        self.cell(CONTENT_W, 6, date.today().strftime("%B %d, %Y"), align="R")

    def footer(self):
        if self.page_no() == 1:
            return

        self.set_y(-12)
        self.set_draw_color(*BORDER)
        self.set_line_width(0.3)
        self.line(MARGIN, self.get_y(), PAGE_W - MARGIN, self.get_y())

        self.set_font("Helvetica", "", 7.5)
        self.set_text_color(*MUTED)
        self.cell(CONTENT_W / 2, 8, "Confidential - Internal Use Only", align="L")
        self.cell(CONTENT_W / 2, 8, f"Page {self.page_no()}", align="R")


# ── Shared layout helpers ─────────────────────────────────────────────────────

def _section_header(pdf: FPDF, title: str):
    """Coloured full-width section header band."""
    pdf.set_fill_color(*ACCENT)
    pdf.set_text_color(*WHITE)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 9, _safe(f"  {title}"), fill=True, ln=True)
    pdf.ln(4)
    pdf.set_text_color(*DARK)


def _table_header(pdf: FPDF, labels: list[str], widths: list[float]):
    pdf.set_fill_color(*NAVY)
    pdf.set_text_color(*WHITE)
    pdf.set_font("Helvetica", "B", 8.5)
    for label, w in zip(labels, widths):
        pdf.cell(w, 7, _safe(f"  {label}"), fill=True, border=0)
    pdf.ln()


def _table_row(pdf: FPDF, values: list[str], widths: list[float], shade: bool = False):
    pdf.set_fill_color(*(LIGHT if shade else WHITE))
    pdf.set_text_color(*DARK)
    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_draw_color(*BORDER)
    for val, w in zip(values, widths):
        display = _safe(str(val))[:30]
        pdf.cell(w, 6.5, f"  {display}", fill=True, border="B")
    pdf.ln()


def _two_col_table(pdf: FPDF, rows: list[tuple]):
    """Simple two-column label/value table."""
    label_w = 55
    value_w = CONTENT_W - label_w

    for i, (label, value) in enumerate(rows):
        shade = i % 2 == 0
        pdf.set_fill_color(*(LIGHT if shade else WHITE))
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*MUTED)
        pdf.cell(label_w, 7, _safe(f"  {label}"), fill=True, border=0)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*DARK)
        pdf.cell(value_w, 7, _safe(str(value)), fill=True, border=0)
        pdf.ln()

    pdf.ln(2)


def _maybe_new_page(pdf: FPDF, needed: float = 40):
    """Add a new page if there isn't enough vertical space left."""
    if pdf.get_y() + needed > PAGE_H - 22:
        pdf.add_page()


# ── Markdown renderer ─────────────────────────────────────────────────────────

def _render_markdown(pdf: FPDF, text: str):
    """
    Lightweight markdown -> fpdf renderer.
    Handles: ## / # headings, --- dividers, bullet lists, body paragraphs.
    Strips inline ** bold ** and ` code ` markers.
    All text is passed through _safe() before rendering.
    """
    for line in text.split("\n"):
        stripped = line.strip()
        _maybe_new_page(pdf, needed=12)

        if stripped.startswith("## "):
            pdf.ln(2)
            pdf.set_font("Helvetica", "B", 11)
            pdf.set_text_color(*ACCENT)
            pdf.cell(0, 7, _safe(_strip_inline(stripped[3:])), ln=True)
            pdf.set_text_color(*DARK)

        elif stripped.startswith("# "):
            pdf.ln(3)
            pdf.set_font("Helvetica", "B", 13)
            pdf.set_text_color(*NAVY)
            pdf.cell(0, 8, _safe(_strip_inline(stripped[2:])), ln=True)
            pdf.set_text_color(*DARK)

        elif stripped == "---":
            pdf.set_draw_color(*BORDER)
            pdf.set_line_width(0.3)
            pdf.line(MARGIN, pdf.get_y() + 2, PAGE_W - MARGIN, pdf.get_y() + 2)
            pdf.ln(6)

        elif stripped.startswith(("- ", "* ", "- ")):
            pdf.set_font("Helvetica", "", 9.5)
            pdf.set_text_color(*DARK)
            clean = _safe(_strip_inline(stripped[2:]))
            pdf.set_x(MARGIN)
            pdf.cell(5, 5.5, "-")
            pdf.set_x(MARGIN + 5)
            pdf.multi_cell(CONTENT_W - 5, 5.5, clean)

        elif stripped and stripped[0].isdigit() and "." in stripped[:3]:
            pdf.set_font("Helvetica", "", 9.5)
            pdf.set_text_color(*DARK)
            clean = _safe(_strip_inline(stripped))
            pdf.set_x(MARGIN + 2)
            pdf.multi_cell(CONTENT_W - 2, 5.5, clean)

        elif stripped == "":
            pdf.ln(2)

        else:
            pdf.set_font("Helvetica", "", 9.5)
            pdf.set_text_color(*DARK)
            clean = _safe(_strip_inline(stripped))
            pdf.multi_cell(0, 5.5, clean)
            pdf.ln(1)


def _strip_inline(text: str) -> str:
    """Remove bold, italic, inline code markdown markers."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*",     r"\1", text)
    text = re.sub(r"`(.+?)`",       r"\1", text)
    text = re.sub(r"_(.+?)_",       r"\1", text)
    return text


# ── Chart image helper ────────────────────────────────────────────────────────

def _fig_to_png(spec: str) -> bytes | None:
    """Convert a stored Plotly JSON spec to PNG bytes via kaleido."""
    try:
        import plotly.io as pio
        fig      = pio.from_json(spec)
        fig.update_layout(
            paper_bgcolor="white",
            plot_bgcolor="white",
            margin=dict(l=40, r=30, t=40, b=40),
            font=dict(family="Arial, sans-serif", size=11),
        )
        return fig.to_image(format="png", width=860, height=360, scale=2)
    except Exception:
        return None


def _fmt(val) -> str:
    """Format a numeric value cleanly for tables."""
    try:
        f = float(val)
        if f == int(f):
            return f"{int(f):,}"
        return f"{f:,.2f}"
    except (TypeError, ValueError):
        return str(val)


def _safe(text: str) -> str:
    """
    Replace Unicode characters outside latin-1 with ASCII equivalents.
    Required because fpdf2's built-in Helvetica uses latin-1 encoding.
    """
    _MAP = {
        "—": "-",    # em dash
        "–": "-",    # en dash
        "‘": "'",    # left single quote
        "’": "'",    # right single quote
        "“": '"',    # left double quote
        "”": '"',    # right double quote
        "…": "...",  # ellipsis
        "•": "-",    # bullet
        "·": "-",    # middle dot
        " ": " ",    # non-breaking space
        "→": "->",   # right arrow
        "←": "<-",   # left arrow
    }
    for char, rep in _MAP.items():
        text = text.replace(char, rep)
    # Final fallback: drop anything still outside latin-1
    return text.encode("latin-1", errors="replace").decode("latin-1")
