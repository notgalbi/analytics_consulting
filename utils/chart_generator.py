"""
chart_generator.py — Produces Plotly figures from a sanitized DataFrame.
No raw PII data reaches this layer — caller must pass a sanitized df.
"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots


_MAX_CATEGORIES = 15   # cap bar chart categories to keep charts readable
_MAX_CHARTS = 8        # max charts generated per run


def generate_charts(df: pd.DataFrame, profile: dict, dataset_type: str) -> dict[str, go.Figure]:
    """
    Return a dict of { chart_title: plotly Figure }.
    Charts generated:
      - KPI indicator cards
      - Time series (if date columns exist)
      - Bar charts (categorical columns)
      - Histograms (numeric columns)
    """
    figures: dict[str, go.Figure] = {}

    date_cols  = profile.get("date_columns", [])
    numeric    = list(profile.get("numeric", {}).keys())
    categorical = list(profile.get("categorical", {}).keys())

    # KPI cards — always first
    kpi_fig = _kpi_cards(profile)
    if kpi_fig:
        figures["KPI Overview"] = kpi_fig

    # Time series
    for date_col in date_cols:
        if len(figures) >= _MAX_CHARTS:
            break
        if date_col not in df.columns:
            continue
        fig = _time_series(df, date_col, numeric)
        if fig:
            figures[f"Trend Over Time ({date_col})"] = fig
            break  # one time-series chart is enough

    # Bar charts for categorical columns
    for col in categorical:
        if len(figures) >= _MAX_CHARTS:
            break
        fig = _bar_chart(df, col)
        if fig:
            figures[f"Distribution: {col}"] = fig

    # Histograms for numeric columns
    for col in numeric:
        if len(figures) >= _MAX_CHARTS:
            break
        fig = _histogram(df, col)
        if fig:
            figures[f"Histogram: {col}"] = fig

    return figures


# ── Chart builders ────────────────────────────────────────────────────────────

def _kpi_cards(profile: dict) -> go.Figure | None:
    """Create indicator cards for key numeric aggregates."""
    numeric = profile.get("numeric", {})
    if not numeric:
        return None

    # Pick up to 4 numeric columns for cards
    cols = list(numeric.keys())[:4]
    fig = make_subplots(
        rows=1, cols=len(cols),
        specs=[[{"type": "indicator"}] * len(cols)],
    )

    for i, col in enumerate(cols, start=1):
        stats = numeric[col]
        fig.add_trace(
            go.Indicator(
                mode="number+delta",
                value=stats["mean"],
                title={"text": f"{col}<br><span style='font-size:0.7em'>mean</span>"},
                number={"font": {"size": 28}},
            ),
            row=1, col=i,
        )

    fig.update_layout(
        height=200,
        margin=dict(l=20, r=20, t=40, b=20),
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def _time_series(df: pd.DataFrame, date_col: str, numeric_cols: list[str]) -> go.Figure | None:
    """Line chart of numeric columns over the date column."""
    if not numeric_cols:
        return None

    tmp = df[[date_col] + numeric_cols[:3]].copy()
    # Coerce to datetime
    tmp[date_col] = pd.to_datetime(tmp[date_col], errors="coerce")
    tmp = tmp.dropna(subset=[date_col]).sort_values(date_col)
    if tmp.empty:
        return None

    # Aggregate by date so duplicate dates don't create noise
    tmp = tmp.groupby(date_col)[numeric_cols[:3]].sum().reset_index()

    fig = px.line(
        tmp,
        x=date_col,
        y=numeric_cols[:3],
        title=f"Trends Over Time",
        labels={"value": "Value", "variable": "Metric"},
    )
    fig.update_layout(hovermode="x unified", legend_title="Metric")
    return fig


def _bar_chart(df: pd.DataFrame, col: str) -> go.Figure | None:
    """Horizontal bar chart of top categories in a column."""
    if col not in df.columns:
        return None

    vc = df[col].astype(str).value_counts().head(_MAX_CATEGORIES)
    if vc.empty:
        return None

    fig = px.bar(
        x=vc.values,
        y=vc.index,
        orientation="h",
        title=f"Top Values: {col}",
        labels={"x": "Count", "y": col},
        color=vc.values,
        color_continuous_scale="Blues",
    )
    fig.update_layout(
        coloraxis_showscale=False,
        yaxis={"categoryorder": "total ascending"},
    )
    return fig


def _histogram(df: pd.DataFrame, col: str) -> go.Figure | None:
    """Histogram for a numeric column."""
    if col not in df.columns:
        return None

    series = df[col].dropna()
    if series.empty or not pd.api.types.is_numeric_dtype(series):
        return None

    fig = px.histogram(
        df,
        x=col,
        nbins=30,
        title=f"Distribution: {col}",
        color_discrete_sequence=["#636EFA"],
    )
    fig.update_layout(bargap=0.05)
    return fig
