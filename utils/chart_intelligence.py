"""
chart_intelligence.py — Insight-driven chart selection.

Charts are selected based on which metrics the analytics surface as significant,
not from a fixed domain template. High/Medium insights, financial findings, and
operational findings each contribute "signals" that boost chart scores for the
columns that matter.

Public API:
    score_and_select_charts(df, domain, insights, calc_kpis, financial_impact,
                            operational_impact) -> tuple[list[ChartSpec], dict[str, Figure]]
    get_chart_metadata(figures, domain) -> list[ChartSpec]
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import pandas as pd
import plotly.graph_objects as go

from utils.chart_generator import generate_dashboard_charts, _detect_date_columns


@dataclass
class ChartSpec:
    chart_id: str
    chart_type: str
    title: str
    description: str
    business_question: str
    x_column: str
    y_column: str
    aggregation: str
    score: int
    include_in_pdf: bool
    include_in_dashboard: bool
    priority: int


# ── Public functions ──────────────────────────────────────────────────────────

def score_and_select_charts(
    df: pd.DataFrame,
    domain: str,
    insights: list | None = None,
    calc_kpis: dict | None = None,
    financial_impact=None,
    operational_impact=None,
) -> tuple[list[ChartSpec], dict[str, go.Figure]]:
    """
    Generate, score, and select charts driven by what the analytics surface.

    When insights are provided, charts that visualise a significant metric
    (High/Medium priority insight, quantified financial finding, or operational
    finding) score much higher than charts that merely match domain keywords.
    This ensures the dashboard shows what actually matters in the data.
    """
    signals = _extract_metric_signals(
        insights or [], calc_kpis or {}, financial_impact, operational_impact
    )

    all_figures = generate_dashboard_charts(df, domain)

    # Add targeted charts for High insights not yet covered
    if insights:
        targeted = _generate_targeted_charts(df, insights, all_figures, signals)
        all_figures.update(targeted)

    specs = _build_specs(all_figures, domain, signals)

    passing = [s for s in specs if s.score >= 55]
    passing.sort(key=lambda s: s.score, reverse=True)
    passing = passing[:8]

    for i, spec in enumerate(passing):
        spec.priority = i + 1
        spec.include_in_pdf = spec.score >= 70
        spec.include_in_dashboard = True

    filtered_figures = {s.title: all_figures[s.title] for s in passing if s.title in all_figures}
    return passing, filtered_figures


def get_chart_metadata(
    figures: dict[str, go.Figure],
    domain: str,
) -> list[ChartSpec]:
    """Create ChartSpec metadata for already-generated figures (no insight context)."""
    return _build_specs(figures, domain, signals={})


# ── Signal extraction ─────────────────────────────────────────────────────────

def _extract_metric_signals(
    insights: list,
    calc_kpis: dict,
    financial_impact,
    operational_impact,
) -> dict[str, int]:
    """
    Build a {keyword: weight} map from all analytics findings.

    Weight scale:
        3 — High-priority insight or quantified financial finding
        2 — Medium-priority insight or operational finding
        1 — Low-priority or data-quality insight
    """
    signals: dict[str, int] = {}

    def _add(text: str, weight: int) -> None:
        for word in _tokenise(text):
            if word and len(word) > 2:
                signals[word] = max(signals.get(word, 0), weight)

    for ins in insights:
        w = {"High": 3, "Medium": 2}.get(ins.priority, 1)
        _add(ins.title, w)
        # Also add individual KPI words that appear in the finding
        for kpi_name in calc_kpis:
            if any(kw in ins.title.lower() for kw in _tokenise(kpi_name)):
                _add(kpi_name, w)

    if financial_impact:
        for f in getattr(financial_impact, "findings", []):
            w = 3 if (getattr(f, "amount", None) and f.amount > 0) else 2
            if getattr(f, "source_kpi", ""):
                _add(f.source_kpi, w)
            _add(getattr(f, "title", ""), w)

    if operational_impact:
        for op in getattr(operational_impact, "findings", []):
            if getattr(op, "severity", "") in ("High", "Medium"):
                w = 3 if op.severity == "High" else 2
                if getattr(op, "metric_name", ""):
                    _add(op.metric_name, w)
                _add(getattr(op, "title", ""), w)

    return signals


def _tokenise(text: str) -> list[str]:
    """Lower-case words, strip punctuation — used for signal matching."""
    import re
    return re.findall(r"[a-z]+", text.lower())


# ── Targeted chart generation ─────────────────────────────────────────────────

_STOP_WORDS = {
    "the", "and", "for", "not", "are", "with", "has", "this", "that",
    "will", "but", "into", "from", "have", "more", "than", "below",
    "above", "rate", "avg", "total", "mean", "count", "data", "issue",
    "high", "low", "risk", "need", "score", "value", "level", "quality",
}

# Broader stop-word set used only for the "already covered?" check in
# _generate_targeted_charts — prevents generic words like "time" (in
# "Over Time" chart titles) from falsely marking an insight as covered.
_COVERAGE_STOP_WORDS = _STOP_WORDS | {
    "time", "over", "trend", "focus", "top", "values", "distribution",
    "metric", "period", "business",
}


def _generate_targeted_charts(
    df: pd.DataFrame,
    insights: list,
    existing_figures: dict,
    signals: dict[str, int],
) -> dict[str, go.Figure]:
    """
    For each High-priority insight, check whether an existing chart already covers
    its key metric. If not, generate a targeted chart for the metric.
    """
    import plotly.express as px

    extra: dict[str, go.Figure] = {}
    covered_signals = _covered_signal_words(existing_figures, signals)

    for ins in insights:
        if ins.priority not in ("High", "Medium"):
            continue

        # Find columns that match this insight's metric
        target_cols = _find_columns_for_insight(ins, df)
        if not target_cols:
            continue

        # Check if already covered — use stricter stop words so generic terms
        # like "time" in "Over Time" don't falsely mark an insight as covered.
        coverage_words = set(_tokenise(ins.title)) - _COVERAGE_STOP_WORDS
        if coverage_words & covered_signals:
            continue

        col = target_cols[0]
        title_prefix = "Focus: "

        try:
            if pd.api.types.is_numeric_dtype(df[col]):
                # Distribution chart for the key metric
                chart_title = f"{title_prefix}{col} Distribution"
                if chart_title not in existing_figures and chart_title not in extra:
                    fig = px.histogram(
                        df, x=col, nbins=25,
                        title=chart_title,
                        template="plotly_white",
                        color_discrete_sequence=["#EF553B"],
                    )
                    fig.update_layout(bargap=0.05)
                    extra[chart_title] = fig

            elif df[col].nunique() <= 20:
                # Category breakdown for the key metric — find a numeric to aggregate
                num_cols = [
                    c for c in df.select_dtypes(include="number").columns
                    if not c.lower().endswith(("_id", "_key")) and c.lower() != "id"
                ]
                if num_cols:
                    agg_col = num_cols[0]
                    grouped = (
                        df.groupby(col, observed=True)[agg_col]
                        .sum()
                        .sort_values(ascending=False)
                        .head(15)
                    )
                    chart_title = f"{title_prefix}{col} Breakdown"
                    if grouped.empty or chart_title in existing_figures or chart_title in extra:
                        continue
                    fig = px.bar(
                        x=grouped.values,
                        y=grouped.index.astype(str),
                        orientation="h",
                        title=chart_title,
                        labels={"x": f"Total {agg_col}", "y": col},
                        template="plotly_white",
                        color=grouped.values,
                        color_continuous_scale="Reds",
                    )
                    fig.update_layout(
                        coloraxis_showscale=False,
                        yaxis={"categoryorder": "total ascending"},
                    )
                    extra[chart_title] = fig
        except Exception:
            pass

    return extra


def _find_columns_for_insight(insight, df: pd.DataFrame) -> list[str]:
    """Match DataFrame columns to an insight's key metric words."""
    insight_words = set(_tokenise(insight.title)) - _STOP_WORDS
    scores: dict[str, int] = {}
    for col in df.columns:
        col_words = set(_tokenise(col))
        overlap = len(insight_words & col_words)
        if overlap > 0:
            scores[col] = overlap
    return sorted(scores, key=scores.__getitem__, reverse=True)[:3]


def _covered_signal_words(figures: dict, signals: dict[str, int]) -> set[str]:
    """Return signal words that already appear in an existing chart title."""
    covered = set()
    for title in figures:
        title_words = set(_tokenise(title))
        for sig in signals:
            if sig in title_words:
                covered.add(sig)
    return covered


# ── Spec building and scoring ─────────────────────────────────────────────────

def _build_specs(
    figures: dict[str, go.Figure],
    domain: str,
    signals: dict[str, int],
) -> list[ChartSpec]:
    specs: list[ChartSpec] = []
    for title, fig in figures.items():
        chart_type = _infer_chart_type(fig)
        x_col, y_col = _infer_columns_from_title(title)
        aggregation = _infer_aggregation(chart_type)
        bq = _build_business_question(title, chart_type)
        score = _score_chart(title, chart_type, signals)
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
            include_in_dashboard=score >= 55,
            priority=0,
        ))
    return specs


def _score_chart(title: str, chart_type: str, signals: dict[str, int]) -> int:
    """
    Score a chart primarily on whether it visualises a metric that the
    analytics identified as significant.

    Insight-signal relevance  0–50  (primary criterion)
    Chart type usefulness     0–25
    Readability               0–15
    Data quality baseline        10
    """
    score = 0
    title_lower = title.lower()
    title_words = set(_tokenise(title_lower))

    # ── Insight-signal relevance (0–50) ──────────────────────────────────────
    max_weight = 0
    for sig, weight in signals.items():
        if sig in title_words:
            max_weight = max(max_weight, weight)

    if max_weight == 3:
        score += 50   # directly visualises a High-priority metric
    elif max_weight == 2:
        score += 38   # Medium-priority metric
    elif max_weight == 1:
        score += 25   # Low-priority or data-quality metric
    else:
        # No signal match — use generic business value heuristics
        generic_kws = {"revenue", "cost", "profit", "rate", "time", "trend",
                       "count", "spend", "sales", "churn", "margin", "return"}
        if title_words & generic_kws:
            score += 20
        elif "trend" in title_lower or "over time" in title_lower:
            score += 18
        elif "distribution" in title_lower or "by" in title_lower:
            score += 15
        else:
            score += 8

    # Time series always adds strategic value
    if "over time" in title_lower or "trend" in title_lower:
        score += 8

    # Targeted focus charts are high-value by definition
    if title.startswith("Focus:"):
        score += 12

    # ── Chart type usefulness (0–25) ──────────────────────────────────────────
    if chart_type in ("line", "bar"):
        score += 25
    elif chart_type in ("scatter", "box"):
        score += 18
    elif chart_type == "histogram":
        score += 12
    else:
        score += 8

    # ── Readability (0–15) ────────────────────────────────────────────────────
    score += 10 if chart_type == "scatter" else 15

    # ── Baseline (10) ────────────────────────────────────────────────────────
    score += 10

    return min(score, 100)


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
    if "distribution" in parts:
        return parts.replace("distribution of", "").replace("distribution:", "").strip(), "count"
    if "trend" in parts or "over time" in parts:
        return "date", "value"
    return "x", "y"


def _infer_aggregation(chart_type: str) -> str:
    return {"bar": "sum", "line": "sum", "scatter": "none",
            "histogram": "none", "box": "none"}.get(chart_type, "sum")


def _build_business_question(title: str, chart_type: str) -> str:
    t = title.lower()
    if "focus:" in t:
        metric = title.replace("Focus:", "").strip()
        return f"Why is {metric} significant to the business right now?"
    if "declining" in t or "growing" in t:
        return "How is this metric trending, and what is driving the direction?"
    if "drive" in t and "%" in t:
        return "Which segments are disproportionately responsible for this outcome?"
    if "over time" in t or "trend" in t:
        return "How has this metric changed over the reporting period?"
    if "distribution" in t:
        return "What does the spread of this metric reveal about operational consistency?"
    if " by " in t:
        return "Which category is underperforming or outperforming relative to peers?"
    if " vs " in t:
        return "What is the relationship between these two metrics?"
    return "What does this metric reveal about current business performance?"


def _build_description(title: str, chart_type: str, bq: str) -> str:
    type_desc = {
        "line":      "Trend over time",
        "bar":       "Ranked comparison across categories",
        "scatter":   "Correlation between two metrics",
        "box":       "Distribution spread by group",
        "histogram": "Frequency distribution",
        "indicator": "KPI summary",
    }
    return f"{type_desc.get(chart_type, 'Visualisation')}. {bq}"


__all__ = ["ChartSpec", "score_and_select_charts", "get_chart_metadata"]
