"""
chart_intelligence.py — Chart selection and scoring layer.

Wraps chart_generator to add business-question-first chart selection,
chart scoring, and metadata generation for admin review and QA.

Public API:
    score_and_select_charts(df, domain) -> tuple[list[ChartSpec], dict[str, Figure]]
    get_chart_metadata(figures, domain) -> list[ChartSpec]
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import pandas as pd
import plotly.graph_objects as go

from utils.chart_generator import generate_dashboard_charts


@dataclass
class ChartSpec:
    chart_id: str
    chart_type: str         # "line" | "bar" | "scatter" | "box" | "histogram" | "indicator"
    title: str
    description: str
    business_question: str
    x_column: str
    y_column: str
    aggregation: str        # "sum" | "mean" | "count" | "none"
    score: int              # 0–100
    include_in_pdf: bool
    include_in_dashboard: bool
    priority: int           # 1 = highest


# ── Domain business question mapping ─────────────────────────────────────────
_DOMAIN_QUESTIONS: dict[str, list[tuple[str, str]]] = {
    "healthcare": [
        ("Over Time",     "How has appointment volume and billing trended over the reporting period?"),
        ("Department",    "Which departments drive the most appointment volume and revenue?"),
        ("Wait Time",     "How does wait time vary across departments and appointment types?"),
        ("Satisfaction",  "What is the distribution of patient satisfaction scores?"),
        ("Status",        "What is the breakdown of appointment completion vs. no-show rates?"),
        ("Billing",       "What is the distribution of billing amounts across appointment types?"),
    ],
    "hospitality": [
        ("Over Time",     "How has daily revenue trended over the reporting period?"),
        ("Food Cost",     "How does food cost percentage vary over time?"),
        ("Covers",        "What is the distribution of daily cover counts?"),
        ("Revenue",       "What drives daily revenue variation?"),
        ("Labor",         "How does labor cost vary relative to cover volume?"),
    ],
    "restaurant": [
        ("Over Time",     "How has daily revenue trended over the reporting period?"),
        ("Food Cost",     "How does food cost percentage vary over time?"),
        ("Covers",        "What is the distribution of daily cover counts?"),
    ],
    "marketing": [
        ("Over Time",     "How have impressions, clicks, and conversions trended over time?"),
        ("Campaign",      "Which campaigns are generating the most revenue and conversions?"),
        ("Platform",      "Which platforms deliver the best ROAS and conversion rates?"),
        ("Spend",         "How is media spend distributed across campaigns and channels?"),
        ("Conversion",    "What is the conversion rate distribution across campaigns?"),
    ],
    "sales": [
        ("Over Time",     "How has revenue trended month over month?"),
        ("Region",        "Which regions are driving the most revenue?"),
        ("Product",       "Which products or categories are top revenue contributors?"),
        ("Customer",      "How does revenue break down by customer segment?"),
        ("Discount",      "What is the distribution of discounts applied?"),
    ],
    "saas": [
        ("Over Time",     "How has MRR trended over the reporting period?"),
        ("Plan",          "Which plan types drive the most MRR?"),
        ("Churn",         "What is the distribution of active vs churned accounts?"),
        ("NPS",           "What is the distribution of NPS scores?"),
        ("Seats",         "How does seat count vary across accounts?"),
    ],
    "ecommerce": [
        ("Over Time",     "How has order volume and revenue trended over time?"),
        ("Category",      "Which product categories generate the most revenue?"),
        ("Return",        "What is the distribution of returns across categories or channels?"),
        ("Ship",          "What is the distribution of days-to-ship?"),
        ("Discount",      "How are discounts distributed across orders?"),
    ],
    "retail": [
        ("Margin",        "What is the distribution of gross margin across SKUs?"),
        ("Stock",         "Which SKUs are at risk of stockout?"),
        ("Turnover",      "What is the inventory turnover distribution by product?"),
        ("Revenue",       "Which products or categories drive 30-day estimated revenue?"),
    ],
    "real_estate": [
        ("Price",         "What is the distribution of sale prices?"),
        ("DOM",           "How does days-on-market vary across property types and neighborhoods?"),
        ("Agent",         "Which agents are driving the most listing volume?"),
        ("Type",          "How does sale price vary by property type?"),
        ("Neighborhood",  "How does performance vary by neighborhood?"),
    ],
    "hr": [
        ("Department",    "How is headcount distributed across departments?"),
        ("Salary",        "What is the salary distribution across the workforce?"),
        ("Tenure",        "What is the tenure distribution?"),
        ("Performance",   "What is the distribution of performance scores?"),
        ("Attrition",     "How does attrition vary across departments?"),
    ],
    "operations": [
        ("Over Time",     "How has ticket volume trended over the reporting period?"),
        ("Team",          "Which teams handle the most ticket volume?"),
        ("Type",          "What is the breakdown of ticket types?"),
        ("Resolution",    "What is the distribution of resolution times?"),
        ("Status",        "What is the current breakdown of open vs closed tickets?"),
    ],
    "finance": [
        ("Over Time",     "How has revenue vs expenses trended over time?"),
        ("Category",      "What is the expense breakdown by category?"),
        ("Profit",        "What is the profit margin distribution?"),
    ],
}

_CHART_TYPE_MAP: dict[str, str] = {
    "scatter":   "line",
    "bar":       "bar",
    "box":       "box",
    "histogram": "histogram",
    "indicator": "indicator",
    "pie":       "bar",
}


# ── Public functions ──────────────────────────────────────────────────────────

def score_and_select_charts(
    df: pd.DataFrame,
    domain: str,
) -> tuple[list[ChartSpec], dict[str, go.Figure]]:
    """
    Generate charts and score them for business relevance.
    Returns (specs, figures) — only charts scoring >= 60 are included.
    """
    all_figures = generate_dashboard_charts(df, domain)
    specs = get_chart_metadata(all_figures, domain)

    # Filter and sort
    passing = [s for s in specs if s.score >= 60]
    passing.sort(key=lambda s: s.score, reverse=True)
    passing = passing[:8]

    # Assign final priority ranks
    for i, spec in enumerate(passing):
        spec.priority = i + 1
        spec.include_in_pdf = spec.score >= 70
        spec.include_in_dashboard = True

    # Return only the figures that passed
    filtered_figures = {s.title: all_figures[s.title] for s in passing if s.title in all_figures}

    return passing, filtered_figures


def get_chart_metadata(
    figures: dict[str, go.Figure],
    domain: str,
) -> list[ChartSpec]:
    """
    Create ChartSpec metadata for already-generated figures.
    Infers chart type, columns, and scores from title and figure structure.
    """
    domain_questions = _DOMAIN_QUESTIONS.get(domain, _DOMAIN_QUESTIONS.get("general", []))
    specs: list[ChartSpec] = []

    for title, fig in figures.items():
        chart_type = _infer_chart_type(fig)
        x_col, y_col = _infer_columns_from_title(title)
        aggregation = _infer_aggregation(chart_type)
        bq = _match_business_question(title, domain_questions)
        score = _score_chart(title, chart_type, bq, domain, domain_questions)
        description = _build_description(title, chart_type, bq)

        specs.append(ChartSpec(
            chart_id=str(uuid.uuid4())[:8],
            chart_type=chart_type,
            title=title,
            description=description,
            business_question=bq,
            x_column=x_col,
            y_column=y_col,
            aggregation=aggregation,
            score=score,
            include_in_pdf=score >= 70,
            include_in_dashboard=score >= 60,
            priority=0,
        ))

    return specs


# ── Helpers ───────────────────────────────────────────────────────────────────

def _infer_chart_type(fig: go.Figure) -> str:
    if not fig.data:
        return "unknown"
    trace_type = type(fig.data[0]).__name__.lower()
    if "scatter" in trace_type:
        mode = getattr(fig.data[0], "mode", "")
        return "line" if mode and "lines" in str(mode) else "scatter"
    if "bar" in trace_type:
        return "bar"
    if "box" in trace_type:
        return "box"
    if "histogram" in trace_type:
        return "histogram"
    if "indicator" in trace_type:
        return "indicator"
    return "chart"


def _infer_columns_from_title(title: str) -> tuple[str, str]:
    parts = title.lower()
    if " vs " in parts:
        halves = parts.split(" vs ")
        return halves[0].strip(), halves[1].strip()
    if " by " in parts:
        halves = parts.split(" by ")
        return halves[1].strip(), halves[0].strip()
    if "distribution of " in parts:
        col = parts.replace("distribution of ", "").strip()
        return col, "count"
    if "trend" in parts or "over time" in parts:
        return "date", "value"
    return "x", "y"


def _infer_aggregation(chart_type: str) -> str:
    return {"bar": "sum", "line": "sum", "scatter": "none", "histogram": "none", "box": "none"}.get(chart_type, "sum")


def _match_business_question(title: str, domain_questions: list[tuple[str, str]]) -> str:
    title_lower = title.lower()
    for keyword, question in domain_questions:
        if keyword.lower() in title_lower:
            return question
    # Generic fallback based on chart title
    if "trend" in title_lower or "over time" in title_lower:
        return "How has this metric trended over the reporting period?"
    if "distribution" in title_lower:
        return "What is the distribution shape of this metric?"
    if " by " in title_lower:
        return "How does this metric break down across categories?"
    if " vs " in title_lower:
        return "What is the relationship between these two metrics?"
    return "What does this metric reveal about business performance?"


def _score_chart(title: str, chart_type: str, bq: str, domain: str, domain_questions: list) -> int:
    score = 0
    title_lower = title.lower()

    # Business relevance (0–40)
    domain_keywords = [kw.lower() for kw, _ in domain_questions]
    if any(kw in title_lower for kw in domain_keywords):
        score += 30
    elif any(word in title_lower for word in ["revenue", "cost", "profit", "rate", "time", "count", "trend"]):
        score += 20
    else:
        score += 10

    if "trend" in title_lower or "over time" in title_lower:
        score += 10  # Time series always executive-relevant

    # Executive usefulness (0–20)
    if chart_type in ("line", "bar"):
        score += 20
    elif chart_type in ("scatter", "box"):
        score += 15
    elif chart_type == "histogram":
        score += 10

    # Readability (0–20)
    if chart_type != "scatter":
        score += 15  # Most charts readable
    else:
        score += 10

    # Data quality (0–20) — assume reasonable data if chart was generated
    score += 15

    return min(score, 100)


def _build_description(title: str, chart_type: str, bq: str) -> str:
    type_descriptions = {
        "line":      "Trend line showing change over time",
        "bar":       "Comparison of values across categories",
        "scatter":   "Correlation analysis between two metrics",
        "box":       "Distribution spread across categories",
        "histogram": "Frequency distribution of values",
        "indicator": "KPI summary card",
    }
    base = type_descriptions.get(chart_type, "Data visualization")
    return f"{base}. Business question: {bq}"


__all__ = ["ChartSpec", "score_and_select_charts", "get_chart_metadata"]
