"""
pdf_generator.py — Executive consulting-grade PDF report.

Card-based, 12-page layout modelled on McKinsey / Bain / BCG board reports.
Every page answers "What matters most?" in under 15 seconds of scanning.

Page layout:
  1  Cover
  2  Executive Summary
  3  Top Findings (insight cards)
  4  KPI Scorecard
  5  Financial Impact
  6  Operational Impact
  7  Recommendations
  8  Decision Matrix
  9  Scenario Modelling
  10 Data Quality
  11 Appendix

Public API:
    generate_pdf(data) → bytes
"""
from __future__ import annotations

import re
from datetime import date

from fpdf import FPDF


# ── Design tokens ──────────────────────────────────────────────────────────────
NAVY      = (27,  42,  74)
ACCENT    = (45, 125, 210)
GREEN     = (22, 163,  74)
AMBER     = (202, 138,   4)
RED       = (220,  38,  38)
LIGHT     = (248, 250, 252)
DARK      = (15,  23,  42)
BODY      = (51,  65,  85)
MUTED     = (100, 116, 139)
WHITE     = (255, 255, 255)
BORDER    = (226, 232, 240)
CARD_BG   = (248, 250, 252)
ALT_ROW   = (241, 245, 249)

PAGE_W    = 210
PAGE_H    = 297
MARGIN    = 20          # ≈ 0.79 inches — within 0.75-1.0 spec
CONTENT_W = PAGE_W - 2 * MARGIN   # 170 mm
CARD_PAD  = 5           # internal card padding mm
CARD_GAP  = 7           # vertical gap between cards mm
LINE_H    = 5.5         # body line height mm
LABEL_H   = 4.5         # small label line height mm

# Y position where body content starts (below running header)
BODY_TOP  = MARGIN + 10


# ── Public entry point ─────────────────────────────────────────────────────────

def generate_pdf(data: dict) -> bytes:
    meta            = data.get("metadata", {})
    profile         = data.get("profile", {})
    kpis_data       = data.get("kpis", {})
    summary         = data.get("summary", "")
    domain          = data.get("domain", "general")
    calc_kpis       = data.get("calc_kpis") or kpis_data.get("calculated", {})
    insights        = data.get("insights", []) or []
    financial       = data.get("financial_impact")
    operational     = data.get("operational_impact")
    recommendations = data.get("recommendations", []) or []
    opportunities   = data.get("opportunities", []) or []
    scenarios       = data.get("scenarios", []) or []
    filename        = meta.get("filename", "Dataset")

    pdf = _ReportPDF()
    pdf._domain   = domain.title()
    pdf._filename = filename
    pdf._date     = date.today().strftime("%B %d, %Y")
    pdf.set_auto_page_break(auto=True, margin=MARGIN + 8)
    pdf.set_margins(MARGIN, BODY_TOP, MARGIN)

    total_fi = 0
    if financial:
        total_fi = (
            getattr(financial, "total_revenue_at_risk", 0)
            + getattr(financial, "total_revenue_opportunity", 0)
            + getattr(financial, "total_cost_savings", 0)
        )

    _cover_page(pdf, filename, domain, profile, total_fi, len(insights))
    _exec_summary_page(pdf, summary, financial, insights, total_fi)

    if insights:
        _top_findings_page(pdf, insights)

    if calc_kpis:
        _kpi_scorecard_page(pdf, calc_kpis)

    fin_findings = getattr(financial, "findings", []) if financial else []
    if fin_findings:
        _financial_impact_page(pdf, financial, total_fi)

    op_findings = getattr(operational, "findings", []) if operational else []
    if op_findings:
        _operational_impact_page(pdf, operational)

    if recommendations:
        _recommendations_page(pdf, recommendations)

    if opportunities:
        _decision_matrix_page(pdf, opportunities)

    if scenarios:
        _scenario_page(pdf, scenarios)

    _data_quality_page(pdf, profile, meta)
    _appendix_page(pdf, kpis_data.get("recommended", []), calc_kpis)

    return bytes(pdf.output())


# ── PDF class — running header + footer ───────────────────────────────────────

class _ReportPDF(FPDF):
    _domain:   str = ""
    _filename: str = ""
    _date:     str = ""

    def header(self):
        if self.page_no() <= 1:
            return
        self.set_fill_color(*NAVY)
        self.rect(0, 0, PAGE_W, 10, "F")
        self.set_font("Helvetica", "B", 7.5)
        self.set_text_color(*WHITE)
        self.set_xy(MARGIN, 2.5)
        self.cell(CONTENT_W * 0.6, 5, _safe(self._filename), align="L")
        self.set_font("Helvetica", "", 7.5)
        self.set_xy(MARGIN, 2.5)
        self.cell(CONTENT_W, 5, _safe(self._domain + "  |  " + self._date), align="R")

    def footer(self):
        if self.page_no() <= 1:
            return
        self.set_y(-(MARGIN - 2))
        self.set_draw_color(*BORDER)
        self.set_line_width(0.2)
        self.line(MARGIN, self.get_y(), PAGE_W - MARGIN, self.get_y())
        self.set_font("Helvetica", "", 7)
        self.set_text_color(*MUTED)
        self.set_x(MARGIN)
        self.cell(CONTENT_W / 2, 5, "CONFIDENTIAL", align="L")
        self.cell(CONTENT_W / 2, 5, f"Page {self.page_no()}", align="R")


# ── Page 1: Cover ─────────────────────────────────────────────────────────────

def _cover_page(pdf, filename, domain, profile, total_fi, n_insights):
    pdf.add_page()

    # Full navy background
    pdf.set_fill_color(*NAVY)
    pdf.rect(0, 0, PAGE_W, PAGE_H, "F")

    # Top accent bar
    pdf.set_fill_color(*ACCENT)
    pdf.rect(0, 0, PAGE_W, 5, "F")
    # Bottom accent bar
    pdf.rect(0, PAGE_H - 5, PAGE_W, 5, "F")

    # Report type label
    pdf.set_text_color(140, 170, 210)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_xy(0, 60)
    pdf.cell(PAGE_W, 6, "EXECUTIVE ANALYTICS REPORT", align="C")

    # Dataset name
    pdf.set_text_color(*WHITE)
    pdf.set_font("Helvetica", "B", 24)
    display = _safe(filename[:38] + ("..." if len(filename) > 38 else ""))
    pdf.set_xy(MARGIN, 72)
    pdf.multi_cell(CONTENT_W, 13, display, align="C")

    # Divider
    pdf.set_draw_color(*ACCENT)
    pdf.set_line_width(0.6)
    pdf.line(MARGIN + 20, 100, PAGE_W - MARGIN - 20, 100)

    # Domain badge
    pdf.set_fill_color(*ACCENT)
    badge_w = 50
    badge_x = (PAGE_W - badge_w) / 2
    pdf.rect(badge_x, 106, badge_w, 8, "F")
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(*WHITE)
    pdf.set_xy(badge_x, 107)
    pdf.cell(badge_w, 6, _safe(domain.upper()), align="C")

    # 3 stat boxes
    row_count    = profile.get("row_count", 0)
    completeness = profile.get("completeness_pct", 0)
    today        = date.today().strftime("%b %d, %Y")

    stats = [
        ("RECORDS ANALYSED", f"{row_count:,}"),
        ("DATA COMPLETENESS", f"{completeness}%"),
        ("PREPARED", today),
    ]
    box_w = 46
    gap   = (CONTENT_W - 3 * box_w) / 2
    start_x = MARGIN
    box_y = 124

    for i, (label, value) in enumerate(stats):
        bx = start_x + i * (box_w + gap)
        pdf.set_fill_color(40, 60, 100)
        pdf.rect(bx, box_y, box_w, 24, "F")
        pdf.set_font("Helvetica", "", 7)
        pdf.set_text_color(140, 170, 210)
        pdf.set_xy(bx, box_y + 4)
        pdf.cell(box_w, 4, label, align="C")
        pdf.set_font("Helvetica", "B", 14)
        pdf.set_text_color(*WHITE)
        pdf.set_xy(bx, box_y + 10)
        pdf.cell(box_w, 9, _safe(str(value)), align="C")

    # Financial impact teaser (if any)
    if total_fi > 0:
        fi_str = _fmt_money(total_fi)
        pdf.set_fill_color(45, 65, 110)
        pdf.rect(MARGIN, 160, CONTENT_W, 22, "F")
        pdf.set_fill_color(*ACCENT)
        pdf.rect(MARGIN, 160, 3, 22, "F")
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(140, 170, 210)
        pdf.set_xy(MARGIN + 8, 164)
        pdf.cell(CONTENT_W - 8, 5, "TOTAL FINANCIAL IMPACT IDENTIFIED")
        pdf.set_font("Helvetica", "B", 18)
        pdf.set_text_color(*WHITE)
        pdf.set_xy(MARGIN + 8, 170)
        pdf.cell(CONTENT_W - 8, 9, _safe(fi_str))

    # Insights teaser
    if n_insights > 0:
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(140, 170, 210)
        pdf.set_xy(0, 192)
        pdf.cell(PAGE_W, 5, f"{n_insights} structured insights  |  Decision matrix  |  Scenario modelling", align="C")

    # Footer note
    pdf.set_font("Helvetica", "I", 7.5)
    pdf.set_text_color(80, 110, 150)
    pdf.set_xy(0, PAGE_H - 16)
    pdf.cell(PAGE_W, 5, "Confidential -- prepared for internal review only.", align="C")


# ── Page 2: Executive Summary ─────────────────────────────────────────────────

def _exec_summary_page(pdf, summary, financial, insights, total_fi):
    pdf.add_page()
    _page_title(pdf, "Executive Summary")

    # 3 headline stat boxes
    high_count  = sum(1 for i in insights if i.priority == "High")
    top_insight = next((i.title for i in insights if i.priority == "High"), "See findings below")
    stats = [
        ("FINANCIAL IMPACT", _fmt_money(total_fi) if total_fi else "See report"),
        ("HIGH-PRIORITY FINDINGS", str(high_count)),
        ("TOTAL INSIGHTS", str(len(insights))),
    ]
    y = pdf.get_y()
    box_w = (CONTENT_W - 8) / 3
    for i, (label, value) in enumerate(stats):
        bx = MARGIN + i * (box_w + 4)
        color = RED if i == 0 and total_fi > 0 else ACCENT
        pdf.set_fill_color(*NAVY)
        pdf.rect(bx, y, box_w, 20, "F")
        pdf.set_fill_color(*color)
        pdf.rect(bx, y, box_w, 2.5, "F")
        pdf.set_font("Helvetica", "", 7)
        pdf.set_text_color(*MUTED)
        pdf.set_xy(bx, y + 4)
        pdf.cell(box_w, 4, label, align="C")
        pdf.set_font("Helvetica", "B", 15)
        pdf.set_text_color(*WHITE)
        pdf.set_xy(bx, y + 9)
        pdf.cell(box_w, 8, _safe(str(value)), align="C")

    pdf.set_y(y + 26)

    # Opening paragraph — extract first substantive block from Claude summary
    opening = _extract_opening(summary, max_chars=700)
    if opening:
        pdf.set_font("Helvetica", "", 11)
        pdf.set_text_color(*BODY)
        pdf.set_x(MARGIN)
        pdf.multi_cell(CONTENT_W, 6.5, _safe(opening))
        pdf.ln(6)

    # Top priority callout
    if top_insight and top_insight != "See findings below":
        _callout_box(
            pdf, MARGIN, pdf.get_y(), CONTENT_W,
            f"TOP PRIORITY: {top_insight}",
            NAVY
        )
        pdf.ln(CARD_GAP)

    # Second paragraph from summary (if space)
    second = _extract_second_para(summary)
    if second and pdf.get_y() < PAGE_H - 60:
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(*BODY)
        pdf.set_x(MARGIN)
        pdf.multi_cell(CONTENT_W, 6, _safe(second))


# ── Page 3: Top Findings ──────────────────────────────────────────────────────

def _top_findings_page(pdf, insights):
    pdf.add_page()
    _page_title(pdf, "Top Findings")

    for insight in insights[:6]:
        _ensure_space(pdf, 52)
        _insight_card(pdf, insight)
        pdf.ln(CARD_GAP)


# ── Page 4: KPI Scorecard ─────────────────────────────────────────────────────

def _kpi_scorecard_page(pdf, calc_kpis):
    pdf.add_page()
    _page_title(pdf, "KPI Scorecard")

    items   = list(calc_kpis.items())
    col_n   = 3
    card_w  = (CONTENT_W - (col_n - 1) * 6) / col_n
    card_h  = 30
    row_gap = 6
    y_start = pdf.get_y()

    for i, (name, value) in enumerate(items):
        col = i % col_n
        row = i // col_n
        bx  = MARGIN + col * (card_w + 6)
        by  = y_start + row * (card_h + row_gap)

        if by + card_h > PAGE_H - MARGIN - 10:
            _ensure_space(pdf, card_h + row_gap)
            y_start = pdf.get_y()
            by      = y_start + (row - (i // col_n)) * (card_h + row_gap)

        # Card background
        pdf.set_fill_color(*CARD_BG)
        pdf.set_draw_color(*BORDER)
        pdf.set_line_width(0.2)
        pdf.rect(bx, by, card_w, card_h, "FD")

        # Accent top strip — color by implied status
        val_str = str(value).lower()
        strip_color = ACCENT
        if any(k in val_str for k in ["🔴", "[high]"]):
            strip_color = RED
        elif any(k in val_str for k in ["🟡", "[med]"]):
            strip_color = AMBER
        elif any(k in val_str for k in ["🟢", "[low]"]):
            strip_color = GREEN

        pdf.set_fill_color(*strip_color)
        pdf.rect(bx, by, card_w, 2.5, "F")

        # Value
        clean_val = _strip_inline(_safe(str(value)))[:18]
        pdf.set_font("Helvetica", "B", 14)
        pdf.set_text_color(*DARK)
        pdf.set_xy(bx, by + 4)
        pdf.cell(card_w, 9, clean_val, align="C")

        # Name label
        short_name = _safe(name)[:22]
        pdf.set_font("Helvetica", "", 7.5)
        pdf.set_text_color(*MUTED)
        pdf.set_xy(bx, by + 14)
        pdf.cell(card_w, 5, short_name, align="C")

        # KPI source note (very small)
        pdf.set_font("Helvetica", "", 6.5)
        pdf.set_text_color(180, 190, 200)
        pdf.set_xy(bx, by + 22)
        pdf.cell(card_w, 4, "Calculated from dataset", align="C")

    rows_used = -(-len(items) // col_n)
    pdf.set_y(y_start + rows_used * (card_h + row_gap) + 4)


# ── Page 5: Financial Impact ──────────────────────────────────────────────────

def _financial_impact_page(pdf, financial, total_fi):
    pdf.add_page()
    _page_title(pdf, "Financial Impact Analysis")

    # Summary banner
    _callout_box(
        pdf, MARGIN, pdf.get_y(), CONTENT_W,
        f"Total identified financial exposure: {_fmt_money(total_fi)}",
        NAVY,
    )
    pdf.ln(CARD_GAP)

    for finding in financial.findings:
        _ensure_space(pdf, 48)
        _financial_card(pdf, finding)
        pdf.ln(CARD_GAP)


# ── Page 6: Operational Impact ────────────────────────────────────────────────

def _operational_impact_page(pdf, operational):
    pdf.add_page()
    _page_title(pdf, "Operational Impact")

    if getattr(operational, "summary_statement", ""):
        pdf.set_font("Helvetica", "I", 10)
        pdf.set_text_color(*MUTED)
        pdf.set_x(MARGIN)
        pdf.multi_cell(CONTENT_W, 6, _safe(operational.summary_statement))
        pdf.ln(CARD_GAP)

    for finding in operational.findings:
        _ensure_space(pdf, 45)
        _op_card(pdf, finding)
        pdf.ln(CARD_GAP)


# ── Page 7: Recommendations ───────────────────────────────────────────────────

def _recommendations_page(pdf, recommendations):
    pdf.add_page()
    _page_title(pdf, "Recommendations")

    for i, rec in enumerate(recommendations[:8], 1):
        _ensure_space(pdf, 46)
        _rec_card(pdf, rec, i)
        pdf.ln(CARD_GAP)


# ── Page 8: Decision Matrix ───────────────────────────────────────────────────

def _decision_matrix_page(pdf, opportunities):
    pdf.add_page()
    _page_title(pdf, "Decision Matrix")

    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*MUTED)
    pdf.set_x(MARGIN)
    pdf.cell(CONTENT_W, 5, "Ranked by opportunity score (Impact x Confidence / Effort). Action the top rows first.", ln=True)
    pdf.ln(4)

    cols   = ["Score", "Priority", "Initiative", "Impact", "Difficulty", "Owner", "Timeline"]
    widths = [14,       18,         58,            18,        20,           24,       18]

    # Header row
    pdf.set_fill_color(*NAVY)
    pdf.set_text_color(*WHITE)
    pdf.set_font("Helvetica", "B", 7.5)
    x = MARGIN
    for col, w in zip(cols, widths):
        pdf.set_xy(x, pdf.get_y())
        pdf.cell(w, 7, f" {col}", fill=True, border=0)
        x += w
    pdf.ln(7)

    priority_colors = {"High": RED, "Medium": AMBER, "Low": GREEN}

    for idx, o in enumerate(opportunities):
        _ensure_space(pdf, 10)
        alt   = idx % 2 == 0
        row_y = pdf.get_y()
        x     = MARGIN

        pdf.set_fill_color(*(ALT_ROW if alt else WHITE))
        pdf.rect(MARGIN, row_y, CONTENT_W, 8, "F")

        values = [
            f"{o.opportunity_score:.0f}",
            o.rank,
            o.initiative[:45] + ("..." if len(o.initiative) > 45 else ""),
            o.expected_impact,
            o.implementation_difficulty,
            o.owner[:18] + ("..." if len(o.owner) > 18 else ""),
            o.timeline,
        ]

        for vi, (val, w) in enumerate(zip(values, widths)):
            pdf.set_xy(x, row_y)
            if vi == 1:
                color = priority_colors.get(o.rank, MUTED)
                pdf.set_text_color(*color)
                pdf.set_font("Helvetica", "B", 7.5)
            elif vi == 0:
                pdf.set_text_color(*ACCENT)
                pdf.set_font("Helvetica", "B", 8)
            else:
                pdf.set_text_color(*DARK)
                pdf.set_font("Helvetica", "", 7.5)
            pdf.cell(w, 8, f" {_safe(str(val))}", border=0)
            x += w
        pdf.ln(8)

    pdf.ln(4)

    # Border around whole table
    pdf.set_draw_color(*BORDER)
    pdf.set_line_width(0.3)


# ── Page 9: Scenario Modelling ────────────────────────────────────────────────

def _scenario_page(pdf, scenarios):
    pdf.add_page()
    _page_title(pdf, "Scenario Modelling")

    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*MUTED)
    pdf.set_x(MARGIN)
    pdf.cell(CONTENT_W, 5, "Best, Expected, and Worst case projections for each top initiative.", ln=True)
    pdf.ln(4)

    for sm in scenarios[:4]:
        _ensure_space(pdf, 55)
        _scenario_card(pdf, sm)
        pdf.ln(CARD_GAP)


# ── Page 10: Data Quality ─────────────────────────────────────────────────────

def _data_quality_page(pdf, profile, meta):
    pdf.add_page()
    _page_title(pdf, "Data Quality Assessment")

    dup  = profile.get("duplicate_report", {})
    pii  = meta.get("pii_report", {})

    # Top-line metric cards
    metrics = [
        ("TOTAL RECORDS",   f"{profile.get('row_count', 0):,}"),
        ("COLUMNS",         str(profile.get("col_count", 0))),
        ("COMPLETENESS",    f"{profile.get('completeness_pct', 0)}%"),
        ("DUPLICATE ROWS",  str(dup.get("duplicate_rows", 0))),
        ("PII RISK",        (pii.get("risk_level", "none")).upper()),
        ("PII COLUMNS",     str(pii.get("total_pii_columns", 0))),
    ]
    y0     = pdf.get_y()
    box_w  = (CONTENT_W - 10) / 3
    box_h  = 22
    for i, (label, value) in enumerate(metrics):
        col = i % 3
        row = i // 3
        bx  = MARGIN + col * (box_w + 5)
        by  = y0 + row * (box_h + 5)

        pdf.set_fill_color(*CARD_BG)
        pdf.set_draw_color(*BORDER)
        pdf.set_line_width(0.2)
        pdf.rect(bx, by, box_w, box_h, "FD")

        pdf.set_fill_color(*ACCENT)
        pdf.rect(bx, by, box_w, 2, "F")

        pdf.set_font("Helvetica", "", 6.5)
        pdf.set_text_color(*MUTED)
        pdf.set_xy(bx, by + 3.5)
        pdf.cell(box_w, 4, label, align="C")

        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(*DARK)
        pdf.set_xy(bx, by + 9)
        pdf.cell(box_w, 8, _safe(str(value)), align="C")

    pdf.set_y(y0 + 2 * (box_h + 5) + 6)

    # Missing values table
    missing = profile.get("missing_values", {})
    if missing:
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*DARK)
        pdf.set_x(MARGIN)
        pdf.cell(0, 7, "Columns with Missing Values", ln=True)
        _table_header_row(pdf, ["Column", "Missing Count", "Missing %"], [85, 45, 40])
        for i, (col, vals) in enumerate(list(missing.items())[:8]):
            _table_data_row(pdf, [col, str(vals.get("missing_count", 0)), f"{vals.get('missing_pct', 0)}%"],
                            [85, 45, 40], alt=(i % 2 == 0))
        pdf.ln(6)

    # Numeric summary
    num = profile.get("numeric_summary", {})
    if num:
        _ensure_space(pdf, 50)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*DARK)
        pdf.set_x(MARGIN)
        pdf.cell(0, 7, "Numeric Column Summary", ln=True)
        _table_header_row(pdf, ["Column", "Min", "Max", "Mean", "Median"], [55, 27, 27, 32, 29])
        for i, (col, s) in enumerate(list(num.items())[:6]):
            _table_data_row(pdf,
                [col, _fmt(s.get("min")), _fmt(s.get("max")), _fmt(s.get("mean")), _fmt(s.get("median"))],
                [55, 27, 27, 32, 29], alt=(i % 2 == 0))


# ── Page 11: Appendix ─────────────────────────────────────────────────────────

def _appendix_page(pdf, recommended_kpis, calc_kpis):
    pdf.add_page()
    _page_title(pdf, "Appendix -- Full KPI List")

    if calc_kpis:
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*DARK)
        pdf.set_x(MARGIN)
        pdf.cell(0, 7, "Calculated KPIs", ln=True)
        _table_header_row(pdf, ["KPI Name", "Value"], [100, 70])
        for i, (name, value) in enumerate(calc_kpis.items()):
            _table_data_row(pdf, [name, str(value)], [100, 70], alt=(i % 2 == 0))
        pdf.ln(8)

    if recommended_kpis:
        _ensure_space(pdf, 40)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*DARK)
        pdf.set_x(MARGIN)
        pdf.cell(0, 7, "Recommended KPIs to Track", ln=True)
        for i, kpi in enumerate(recommended_kpis[:10], 1):
            _ensure_space(pdf, 12)
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_text_color(*ACCENT)
            pdf.set_x(MARGIN)
            pdf.cell(8, 6, str(i) + ".")
            pdf.set_text_color(*DARK)
            pdf.cell(0, 6, _safe(kpi.get("name", "")), ln=True)
            pdf.set_x(MARGIN + 8)
            pdf.set_font("Helvetica", "", 8.5)
            pdf.set_text_color(*MUTED)
            pdf.multi_cell(CONTENT_W - 8, 5, _safe(kpi.get("description", "")))
            pdf.ln(2)

    # Disclaimer
    _ensure_space(pdf, 40)
    pdf.ln(4)
    pdf.set_draw_color(*BORDER)
    pdf.set_line_width(0.2)
    pdf.line(MARGIN, pdf.get_y(), PAGE_W - MARGIN, pdf.get_y())
    pdf.ln(4)
    today = date.today().strftime("%B %d, %Y")
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(*MUTED)
    pdf.set_x(MARGIN)
    pdf.multi_cell(CONTENT_W, 5,
        f"Report generated {today}. All analysis derived from aggregate statistics only. "
        "No individual records or PII were used. Verify all figures against source systems "
        "before making business decisions.")


# ── Card drawing helpers ───────────────────────────────────────────────────────

def _insight_card(pdf, insight):
    """Full-width card for a business insight."""
    priority    = getattr(insight, "priority", "Medium")
    title       = getattr(insight, "title", "")
    finding     = getattr(insight, "finding", "") or ""
    fi          = getattr(insight, "financial_impact", "") or "Not quantified"
    action      = getattr(insight, "recommended_action", "") or ""
    outcome     = getattr(insight, "expected_outcome", "") or ""
    ev_type     = getattr(insight, "evidence_type", "") or ""
    category    = getattr(insight, "category", "") or ""
    confidence  = getattr(insight, "confidence_score", 0.7) or 0.7

    header_colors = {"High": RED, "Medium": AMBER, "Low": GREEN}
    header_color  = header_colors.get(priority, ACCENT)

    x     = MARGIN
    y     = pdf.get_y()
    w     = CONTENT_W
    pad   = CARD_PAD

    # Estimate height
    finding_lines = max(1, len(finding) // 90 + 1)
    action_lines  = max(1, len(action) // 90 + 1)
    h = 10 + finding_lines * LINE_H + action_lines * LINE_H + 28

    # Card background
    pdf.set_fill_color(*CARD_BG)
    pdf.set_draw_color(*BORDER)
    pdf.set_line_width(0.2)
    pdf.rect(x, y, w, h, "FD")

    # Left priority stripe
    pdf.set_fill_color(*header_color)
    pdf.rect(x, y, 3, h, "F")

    # Header bar
    pdf.set_fill_color(*header_color)
    pdf.rect(x, y, w, 9, "F")

    pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(*WHITE)
    pdf.set_xy(x + pad, y + 2)
    pdf.cell(w * 0.5, 5, f"{priority.upper()} PRIORITY  |  {category.upper()}", align="L")
    pdf.set_font("Helvetica", "", 7.5)
    if ev_type:
        pdf.set_xy(x + w * 0.55, y + 2)
        pdf.cell(w * 0.4, 5, f"EVIDENCE: {ev_type}", align="R")

    # Title
    pdf.set_font("Helvetica", "B", 10.5)
    pdf.set_text_color(*DARK)
    pdf.set_xy(x + pad, y + 11)
    pdf.multi_cell(w - pad * 2, 6, _safe(title))
    pdf.ln(2)

    # Finding / Impact / Action rows
    sections = [
        ("FINDING",             finding[:240]),
        ("FINANCIAL IMPACT",    fi),
        ("RECOMMENDED ACTION",  action[:220]),
    ]
    for label, text in sections:
        _ensure_space(pdf, 10)
        cy = pdf.get_y()
        pdf.set_font("Helvetica", "B", 7)
        pdf.set_text_color(*MUTED)
        pdf.set_xy(x + pad, cy)
        pdf.cell(w - pad * 2, 4, label, ln=True)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*BODY)
        pdf.set_x(x + pad)
        pdf.multi_cell(w - pad * 2, LINE_H, _safe(text))
        pdf.ln(2)

    # Confidence + outcome footer strip
    footer_y = pdf.get_y() + 1
    pdf.set_fill_color(235, 240, 248)
    footer_h = 7
    pdf.rect(x, footer_y, w, footer_h, "F")
    pdf.set_font("Helvetica", "", 7.5)
    pdf.set_text_color(*MUTED)
    pdf.set_xy(x + pad, footer_y + 1.5)
    pdf.cell(w * 0.4, 4, f"Confidence: {confidence * 100:.0f}%", align="L")
    if outcome:
        pdf.set_xy(x + w * 0.4, footer_y + 1.5)
        pdf.cell(w * 0.55, 4, _safe(("Expected: " + outcome)[:70]), align="L")

    pdf.set_y(footer_y + footer_h)


def _financial_card(pdf, finding):
    """Card for a financial impact finding."""
    title    = getattr(finding, "title", "")
    amount   = getattr(finding, "amount", None)
    category = getattr(finding, "category", "")
    priority = getattr(finding, "priority", "Medium")
    desc     = getattr(finding, "description", "") or ""
    assump   = getattr(finding, "assumption", "") or ""
    conf     = getattr(finding, "confidence", 0.7) or 0.7

    priority_colors = {"High": RED, "Medium": AMBER, "Low": GREEN}
    header_color    = priority_colors.get(priority, ACCENT)
    amt_str         = _fmt_money(amount) if amount is not None and amount > 0 else "Not quantified"

    x = MARGIN
    y = pdf.get_y()
    w = CONTENT_W

    # Card shell
    pdf.set_fill_color(*CARD_BG)
    pdf.set_draw_color(*BORDER)
    pdf.set_line_width(0.2)
    h_est = 55
    pdf.rect(x, y, w, h_est, "FD")
    pdf.set_fill_color(*header_color)
    pdf.rect(x, y, w, 8, "F")
    pdf.rect(x, y, 3, h_est, "F")

    pdf.set_font("Helvetica", "B", 7.5)
    pdf.set_text_color(*WHITE)
    pdf.set_xy(x + CARD_PAD, y + 1.5)
    pdf.cell(w * 0.5, 5, f"{priority.upper()}  |  {category.upper()}", align="L")
    pdf.set_xy(x + w * 0.5, y + 1.5)
    pdf.cell(w * 0.45, 5, f"Confidence: {conf*100:.0f}%", align="R")

    # Title
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*DARK)
    pdf.set_xy(x + CARD_PAD, y + 10)
    pdf.multi_cell(w - CARD_PAD * 2, 6, _safe(title))

    # Amount highlight box
    amt_y = pdf.get_y() + 2
    pdf.set_fill_color(*NAVY)
    pdf.rect(x + CARD_PAD, amt_y, 55, 13, "F")
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(*WHITE)
    pdf.set_xy(x + CARD_PAD, amt_y + 2)
    pdf.cell(55, 9, _safe(amt_str), align="C")

    # Description
    pdf.set_xy(x + CARD_PAD + 60, amt_y)
    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(*BODY)
    pdf.multi_cell(w - CARD_PAD * 2 - 62, 5, _safe(desc[:160]))

    pdf.set_y(amt_y + 15)

    # Assumption line
    if assump:
        pdf.set_font("Helvetica", "I", 7.5)
        pdf.set_text_color(*MUTED)
        pdf.set_x(x + CARD_PAD)
        pdf.multi_cell(w - CARD_PAD * 2, 4.5, _safe("How calculated: " + assump[:180]))

    pdf.ln(2)


def _op_card(pdf, finding):
    """Card for an operational impact finding."""
    title  = getattr(finding, "title", "")
    sev    = getattr(finding, "severity", "Medium")
    cat    = getattr(finding, "category", "")
    f_text = getattr(finding, "finding", "") or ""
    impact = getattr(finding, "impact", "") or ""
    rec    = getattr(finding, "recommendation", "") or ""
    mname  = getattr(finding, "metric_name", "") or ""
    mval   = getattr(finding, "metric_value", "") or ""
    bench  = getattr(finding, "benchmark", "") or ""

    sev_colors = {"High": RED, "Medium": AMBER, "Low": GREEN}
    header_color = sev_colors.get(sev, ACCENT)

    x = MARGIN
    y = pdf.get_y()
    w = CONTENT_W

    desc_lines = max(1, (len(f_text) + len(impact) + len(rec)) // 90 + 3)
    h = max(40, desc_lines * LINE_H + 18)

    pdf.set_fill_color(*CARD_BG)
    pdf.set_draw_color(*BORDER)
    pdf.set_line_width(0.2)
    pdf.rect(x, y, w, h, "FD")
    pdf.set_fill_color(*header_color)
    pdf.rect(x, y, w, 8, "F")
    pdf.rect(x, y, 3, h, "F")

    pdf.set_font("Helvetica", "B", 7.5)
    pdf.set_text_color(*WHITE)
    pdf.set_xy(x + CARD_PAD, y + 1.5)
    pdf.cell(w - CARD_PAD * 2, 5, f"{sev.upper()} SEVERITY  |  {cat.upper()}", align="L")

    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*DARK)
    pdf.set_xy(x + CARD_PAD, y + 10)
    pdf.multi_cell(w - CARD_PAD * 2, 6, _safe(title))

    if mname and mval:
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(*ACCENT)
        pdf.set_x(x + CARD_PAD)
        pdf.cell(w - CARD_PAD * 2, 5, _safe(f"{mname}: {mval}" + (f"  (Benchmark: {bench})" if bench else "")), ln=True)

    for label, text in [("FINDING", f_text[:180]), ("BUSINESS IMPACT", impact[:120]), ("RECOMMENDATION", rec[:160])]:
        if not text:
            continue
        pdf.set_font("Helvetica", "B", 7)
        pdf.set_text_color(*MUTED)
        pdf.set_x(x + CARD_PAD)
        pdf.cell(w - CARD_PAD * 2, 4, label, ln=True)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*BODY)
        pdf.set_x(x + CARD_PAD)
        pdf.multi_cell(w - CARD_PAD * 2, LINE_H, _safe(text))
        pdf.ln(1.5)

    pdf.set_y(y + h)


def _rec_card(pdf, rec, number):
    """Card for a recommendation."""
    action   = getattr(rec, "action", "") or ""
    owner    = getattr(rec, "owner", "") or ""
    timeline = getattr(rec, "timeline", "") or ""
    priority = getattr(rec, "priority", "Medium") or "Medium"
    outcome  = getattr(rec, "expected_outcome", "") or ""
    benefit  = getattr(rec, "estimated_benefit", "") or ""
    conf     = getattr(rec, "confidence", 0.7) or 0.7

    priority_colors = {"Critical": RED, "High": RED, "Medium": AMBER, "Low": GREEN}
    header_color    = priority_colors.get(priority, ACCENT)

    x = MARGIN
    y = pdf.get_y()
    w = CONTENT_W

    action_lines  = max(1, len(action) // 90 + 1)
    outcome_lines = max(1, len(outcome) // 90 + 1)
    h = max(40, (action_lines + outcome_lines) * LINE_H + 22)

    pdf.set_fill_color(*CARD_BG)
    pdf.set_draw_color(*BORDER)
    pdf.set_line_width(0.2)
    pdf.rect(x, y, w, h, "FD")

    # Number badge
    pdf.set_fill_color(*header_color)
    pdf.rect(x, y, 10, h, "F")
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*WHITE)
    pdf.set_xy(x, y + h / 2 - 4)
    pdf.cell(10, 8, str(number), align="C")

    # Priority label
    pdf.set_fill_color(*header_color)
    pdf.rect(x + 10, y, w - 10, 8, "F")
    pdf.set_font("Helvetica", "B", 7.5)
    pdf.set_text_color(*WHITE)
    pdf.set_xy(x + 14, y + 1.5)
    pdf.cell((w - 14) * 0.4, 5, f"{priority.upper()} PRIORITY", align="L")
    pdf.set_xy(x + 14 + (w - 14) * 0.4, y + 1.5)
    pdf.cell((w - 14) * 0.55, 5, f"Owner: {_safe(owner[:30])}  |  {_safe(timeline)}", align="R")

    # Action
    pdf.set_font("Helvetica", "", 9.5)
    pdf.set_text_color(*DARK)
    pdf.set_xy(x + 14, y + 11)
    pdf.multi_cell(w - 16, LINE_H, _safe(action[:240]))
    pdf.ln(2)

    # Outcome + benefit
    if outcome or benefit:
        cy = pdf.get_y()
        pdf.set_font("Helvetica", "B", 7)
        pdf.set_text_color(*MUTED)
        pdf.set_xy(x + 14, cy)
        pdf.cell(w - 16, 4, "EXPECTED OUTCOME", ln=True)
        pdf.set_font("Helvetica", "", 8.5)
        pdf.set_text_color(*BODY)
        pdf.set_x(x + 14)
        pdf.multi_cell(w - 16, 5, _safe((outcome or benefit)[:140]))

    pdf.set_y(y + h)


def _scenario_card(pdf, sm):
    """3-column best/expected/worst scenario card."""
    initiative  = getattr(sm, "initiative", "") or ""
    rec_text    = getattr(sm, "recommendation", "") or ""
    best        = getattr(sm, "best_case", None)
    expected    = getattr(sm, "expected_case", None)
    worst       = getattr(sm, "worst_case", None)

    x = MARGIN
    y = pdf.get_y()
    w = CONTENT_W
    h = 55

    # Outer card
    pdf.set_fill_color(*CARD_BG)
    pdf.set_draw_color(*BORDER)
    pdf.set_line_width(0.2)
    pdf.rect(x, y, w, h, "FD")

    # Header
    pdf.set_fill_color(*NAVY)
    pdf.rect(x, y, w, 9, "F")
    pdf.set_font("Helvetica", "B", 7.5)
    pdf.set_text_color(*WHITE)
    pdf.set_xy(x + CARD_PAD, y + 2)
    pdf.cell(w - CARD_PAD * 2, 5, "SCENARIO MODEL", align="L")

    # Initiative title
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*DARK)
    pdf.set_xy(x + CARD_PAD, y + 11)
    pdf.multi_cell(w - CARD_PAD * 2, 5.5, _safe((initiative or rec_text)[:130]))
    pdf.ln(3)

    # 3 scenario columns
    scen_y  = pdf.get_y()
    col_w   = (w - 4) / 3
    gap     = 2
    cases   = [
        (best,     "BEST CASE",     GREEN),
        (expected, "EXPECTED CASE", ACCENT),
        (worst,    "WORST CASE",    RED),
    ]

    for i, (case, label, color) in enumerate(cases):
        if not case:
            continue
        cx = x + i * (col_w + gap)
        pdf.set_fill_color(*(235, 248, 235) if color == GREEN else (235, 242, 252) if color == ACCENT else (252, 235, 235))
        pdf.rect(cx, scen_y, col_w, 30, "F")
        pdf.set_fill_color(*color)
        pdf.rect(cx, scen_y, col_w, 3, "F")

        pdf.set_font("Helvetica", "B", 7)
        pdf.set_text_color(*color)
        pdf.set_xy(cx + 2, scen_y + 4)
        pdf.cell(col_w - 4, 4, label, align="C")

        prob = getattr(case, "probability", "") or ""
        pdf.set_font("Helvetica", "", 7)
        pdf.set_text_color(*MUTED)
        pdf.set_xy(cx + 2, scen_y + 8.5)
        pdf.cell(col_w - 4, 4, _safe(prob), align="C")

        rev = getattr(case, "revenue_impact", 0) or 0
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(*DARK)
        pdf.set_xy(cx + 2, scen_y + 14)
        pdf.cell(col_w - 4, 8, _safe(_fmt_money(rev) if rev else "--"), align="C")

        eff = getattr(case, "efficiency_impact", "") or ""
        pdf.set_font("Helvetica", "", 6.5)
        pdf.set_text_color(*MUTED)
        pdf.set_xy(cx + 2, scen_y + 23)
        pdf.multi_cell(col_w - 4, 3.5, _safe(eff[:60]))

    pdf.set_y(scen_y + 33)


# ── Layout helpers ─────────────────────────────────────────────────────────────

def _page_title(pdf, title: str, subtitle: str = ""):
    """Draws a section title band at the current Y position."""
    y = pdf.get_y()
    pdf.set_fill_color(*NAVY)
    pdf.rect(MARGIN, y, CONTENT_W, 11, "F")
    pdf.set_fill_color(*ACCENT)
    pdf.rect(MARGIN, y, 4, 11, "F")
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(*WHITE)
    pdf.set_xy(MARGIN + 8, y + 2)
    pdf.cell(CONTENT_W - 8, 7, _safe(title), align="L")
    pdf.set_y(y + 17)
    if subtitle:
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(*MUTED)
        pdf.set_x(MARGIN)
        pdf.cell(CONTENT_W, 5, _safe(subtitle), ln=True)
        pdf.ln(2)


def _callout_box(pdf, x, y, w, text, bg_color):
    """Highlighted callout / pull-quote box."""
    h = max(12, len(text) // 60 * LINE_H + 10)
    pdf.set_fill_color(*bg_color)
    pdf.rect(x, y, w, h, "F")
    pdf.set_fill_color(*ACCENT)
    pdf.rect(x, y, 4, h, "F")
    pdf.set_font("Helvetica", "B", 9.5)
    pdf.set_text_color(*WHITE)
    pdf.set_xy(x + 9, y + (h - 6) / 2)
    pdf.multi_cell(w - 12, 6, _safe(text[:120]))
    pdf.set_y(y + h)


def _ensure_space(pdf, needed: float):
    """Add a new page if there is not enough vertical space."""
    if pdf.get_y() + needed > PAGE_H - MARGIN - 10:
        pdf.add_page()


def _table_header_row(pdf, labels, widths):
    pdf.set_fill_color(*NAVY)
    pdf.set_text_color(*WHITE)
    pdf.set_font("Helvetica", "B", 8)
    x = MARGIN
    y = pdf.get_y()
    for label, w in zip(labels, widths):
        pdf.rect(x, y, w, 7, "F")
        pdf.set_xy(x + 2, y + 1)
        pdf.cell(w - 2, 5, _safe(label))
        x += w
    pdf.set_y(y + 7)


def _table_data_row(pdf, values, widths, alt=False):
    pdf.set_fill_color(*(ALT_ROW if alt else WHITE))
    pdf.set_text_color(*DARK)
    pdf.set_font("Helvetica", "", 8.5)
    x = MARGIN
    y = pdf.get_y()
    pdf.rect(MARGIN, y, sum(widths), 7, "F")
    for val, w in zip(values, widths):
        pdf.set_xy(x + 2, y + 1)
        pdf.cell(w - 2, 5, _safe(str(val)[:35]))
        x += w
    pdf.set_draw_color(*BORDER)
    pdf.set_line_width(0.1)
    pdf.line(MARGIN, y + 7, MARGIN + sum(widths), y + 7)
    pdf.set_y(y + 7)


# ── Text helpers ───────────────────────────────────────────────────────────────

def _extract_opening(summary: str, max_chars: int = 700) -> str:
    """Pull the first substantive paragraph from the Claude summary."""
    if not summary:
        return ""
    text = re.sub(r"#+ ?.*", "", summary)           # strip headers
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)    # strip bold
    text = re.sub(r"\*(.+?)\*", r"\1", text)         # strip italic
    text = re.sub(r"---+", "", text)                  # strip dividers
    paras = [p.strip() for p in text.split("\n\n") if p.strip() and len(p.strip()) > 80]
    result = paras[0] if paras else ""
    return result[:max_chars]


def _extract_second_para(summary: str) -> str:
    """Pull the second substantive paragraph."""
    if not summary:
        return ""
    text = re.sub(r"#+ ?.*", "", summary)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"---+", "", text)
    paras = [p.strip() for p in text.split("\n\n") if p.strip() and len(p.strip()) > 80]
    return paras[1][:500] if len(paras) > 1 else ""


def _strip_inline(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*",     r"\1", text)
    text = re.sub(r"`(.+?)`",       r"\1", text)
    return text


def _fmt_money(val) -> str:
    try:
        v = float(val)
    except (TypeError, ValueError):
        return str(val)
    if v >= 1_000_000:
        return f"${v / 1_000_000:.1f}M"
    if v >= 1_000:
        return f"${v / 1_000:.0f}K"
    return f"${v:,.0f}"


def _fmt(val) -> str:
    try:
        f = float(val)
        return f"{int(f):,}" if f == int(f) else f"{f:,.2f}"
    except (TypeError, ValueError):
        return str(val) if val is not None else ""


def _safe(text: str) -> str:
    if not text:
        return ""
    text = str(text)
    _MAP = {
        "—": "--", "–": "-",
        "‘": "'",  "’": "'",
        "“": '"',  "”": '"',
        "…": "...", "•": "-", "·": "-",
        " ": " ",  "→": "->",
        "≥": ">=", "≤": "<=", "≠": "!=",
        "×": "x",  "÷": "/", "°": "deg",
        "✓": "OK", "✗": "X",
        "\U0001f534": "[HIGH]", "\U0001f7e1": "[MED]", "\U0001f7e2": "[LOW]",
        "✅": "[OK]", "❌": "[X]", "⚠": "[!]",
    }
    for ch, rep in _MAP.items():
        text = text.replace(ch, rep)
    return text.encode("latin-1", errors="replace").decode("latin-1")


__all__ = ["generate_pdf"]
