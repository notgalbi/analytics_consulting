"""
chart_generator.py — Automatic Plotly chart generation for Streamlit dashboards.
Caller must pass a sanitized DataFrame — no raw PII reaches this layer.

Public API:
    generate_dashboard_charts(df, domain) → dict[title, Figure]
    generate_kpi_cards(df, calculated_kpis)
    generate_time_series_chart(df)
    generate_bar_charts(df)
    generate_numeric_histograms(df)
"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots


_MAX_CHARTS      = 8    # hard cap on total charts returned
_MAX_CATEGORIES  = 15   # max bars in a bar chart
_CHART_TEMPLATE  = "plotly_white"


def generate_dashboard_charts(
    df: pd.DataFrame,
    domain: str,
) -> dict[str, go.Figure]:
    """
    Generate an executive-friendly chart set from a sanitized DataFrame.
    Returns at most _MAX_CHARTS figures, ordered for readability.
    """
    figures: dict[str, go.Figure] = {}

    date_cols  = _detect_date_columns(df)
    num_cols   = list(df.select_dtypes(include="number").columns)
    cat_cols   = list(df.select_dtypes(include=["object", "category", "string"]).columns)
    # Drop columns that look like free-text (very high cardinality)
    cat_cols = [c for c in cat_cols if df[c].nunique() <= 50]

    # Time series comes first when a date column exists
    if date_cols and num_cols:
        fig = generate_time_series_chart(df, date_cols[0], num_cols)
        if fig:
            figures[f"Trend Over Time ({date_cols[0]})"] = fig

    # Bar charts for categorical columns
    for col in cat_cols:
        if len(figures) >= _MAX_CHARTS - 1:
            break
        fig = _bar_chart(df, col, num_cols)
        if fig:
            figures[f"Top Values: {col}"] = fig

    # Histograms for numeric columns
    for col in num_cols:
        if len(figures) >= _MAX_CHARTS - 1:
            break
        fig = _histogram(df, col)
        if fig:
            figures[f"Distribution: {col}"] = fig

    return figures


def generate_kpi_cards(
    df: pd.DataFrame,
    calculated_kpis: dict[str, str],
) -> go.Figure | None:
    """
    Render calculated KPI values as Plotly indicator cards.
    Returns None if no KPIs were calculated.
    """
    if not calculated_kpis:
        return None

    items = list(calculated_kpis.items())[:6]
    cols  = min(len(items), 3)
    rows  = -(-len(items) // cols)   # ceiling division

    fig = make_subplots(
        rows=rows, cols=cols,
        specs=[[{"type": "indicator"}] * cols for _ in range(rows)],
        vertical_spacing=0.1,
    )

    for i, (name, value) in enumerate(items):
        row = i // cols + 1
        col = i % cols + 1
        # Strip currency/percent for the numeric display; show label as title
        fig.add_trace(
            go.Indicator(
                mode="number",
                value=_parse_kpi_value(value),
                number={"suffix": _kpi_suffix(value), "font": {"size": 30}},
                title={"text": name, "font": {"size": 14}},
            ),
            row=row, col=col,
        )

    fig.update_layout(
        height=150 * rows,
        margin=dict(l=20, r=20, t=30, b=10),
        template=_CHART_TEMPLATE,
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def generate_time_series_chart(
    df: pd.DataFrame,
    date_col: str | None = None,
    numeric_cols: list[str] | None = None,
) -> go.Figure | None:
    """
    Line chart of up to 3 numeric columns over a date axis.
    Auto-detects date column if not provided.
    """
    if date_col is None:
        candidates = _detect_date_columns(df)
        if not candidates:
            return None
        date_col = candidates[0]

    if numeric_cols is None:
        numeric_cols = list(df.select_dtypes(include="number").columns)

    if not numeric_cols:
        return None

    # Coerce dates, drop unparseable rows, aggregate to remove duplicates
    tmp = df[[date_col] + numeric_cols[:3]].copy()
    tmp[date_col] = pd.to_datetime(tmp[date_col], errors="coerce")
    tmp = tmp.dropna(subset=[date_col]).sort_values(date_col)
    if tmp.empty:
        return None

    tmp = tmp.groupby(date_col)[numeric_cols[:3]].sum().reset_index()

    fig = px.line(
        tmp,
        x=date_col,
        y=numeric_cols[:3],
        title="Trends Over Time",
        labels={"value": "Value", "variable": "Metric"},
        template=_CHART_TEMPLATE,
    )
    fig.update_traces(mode="lines+markers", marker_size=4)
    fig.update_layout(hovermode="x unified", legend_title="Metric")
    return fig


def generate_bar_charts(df: pd.DataFrame) -> dict[str, go.Figure]:
    """
    Generate one bar chart per low-cardinality categorical column.
    Returns a dict of { chart_title: Figure }.
    """
    figures = {}
    num_cols = list(df.select_dtypes(include="number").columns)
    cat_cols = [
        c for c in df.select_dtypes(include=["object", "category", "string"]).columns
        if df[c].nunique() <= 50
    ]
    for col in cat_cols:
        fig = _bar_chart(df, col, num_cols)
        if fig:
            figures[f"Top Values: {col}"] = fig
    return figures


def generate_numeric_histograms(df: pd.DataFrame) -> dict[str, go.Figure]:
    """Generate one histogram per numeric column."""
    figures = {}
    for col in df.select_dtypes(include="number").columns:
        fig = _histogram(df, col)
        if fig:
            figures[f"Distribution: {col}"] = fig
    return figures


# ── Internal chart builders ───────────────────────────────────────────────────

def _bar_chart(
    df: pd.DataFrame,
    cat_col: str,
    num_cols: list[str],
) -> go.Figure | None:
    """Horizontal bar chart: top categories by count or by a numeric sum."""
    if cat_col not in df.columns:
        return None

    # If a matching numeric column exists, aggregate it; otherwise use counts
    if num_cols:
        agg_col = num_cols[0]
        grouped = (
            df.groupby(cat_col, observed=True)[agg_col]
            .sum()
            .sort_values(ascending=False)
            .head(_MAX_CATEGORIES)
        )
        x_label = f"Total {agg_col}"
    else:
        grouped = (
            df[cat_col].value_counts()
            .head(_MAX_CATEGORIES)
        )
        x_label = "Count"

    if grouped.empty:
        return None

    fig = px.bar(
        x=grouped.values,
        y=grouped.index.astype(str),
        orientation="h",
        title=f"{cat_col} Breakdown",
        labels={"x": x_label, "y": cat_col},
        template=_CHART_TEMPLATE,
        color=grouped.values,
        color_continuous_scale="Blues",
    )
    fig.update_layout(
        coloraxis_showscale=False,
        yaxis={"categoryorder": "total ascending"},
    )
    return fig


def _histogram(df: pd.DataFrame, col: str) -> go.Figure | None:
    """Histogram for a single numeric column."""
    if col not in df.columns:
        return None
    s = df[col].dropna()
    if s.empty or not pd.api.types.is_numeric_dtype(s):
        return None

    fig = px.histogram(
        df,
        x=col,
        nbins=30,
        title=f"Distribution of {col}",
        template=_CHART_TEMPLATE,
        color_discrete_sequence=["#636EFA"],
    )
    fig.update_layout(bargap=0.05)
    return fig


# ── Helpers ───────────────────────────────────────────────────────────────────

def _detect_date_columns(df: pd.DataFrame) -> list[str]:
    """Return column names that are or look like dates."""
    date_cols = list(df.select_dtypes(include=["datetime", "datetimetz"]).columns)
    for col in df.select_dtypes(include="object").columns:
        if any(kw in col.lower() for kw in ["date", "time", "dt", "created", "updated", "timestamp"]):
            date_cols.append(col)
    return list(dict.fromkeys(date_cols))


def _parse_kpi_value(value: str) -> float:
    """Extract a numeric value from a formatted KPI string."""
    clean = value.replace("$", "").replace(",", "").replace("%", "").replace("x", "")
    if "K" in clean:
        return float(clean.replace("K", "")) * 1_000
    if "M" in clean:
        return float(clean.replace("M", "")) * 1_000_000
    try:
        return float(clean)
    except ValueError:
        return 0.0


def _kpi_suffix(value: str) -> str:
    if "%" in value:
        return "%"
    if "x" in value:
        return "x"
    return ""
