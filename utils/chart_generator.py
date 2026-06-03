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


_MAX_CHARTS     = 10   # hard cap on total charts returned
_MAX_CATEGORIES = 15   # max bars / groups in a bar chart
_CHART_TEMPLATE = "plotly_white"

# Colour palette used across charts
_PALETTE = px.colors.qualitative.Set2


def generate_dashboard_charts(
    df: pd.DataFrame,
    domain: str,
) -> dict[str, go.Figure]:
    """
    Generate an executive-friendly chart set from a sanitized DataFrame.
    Returns at most _MAX_CHARTS figures in priority order.
    """
    figures: dict[str, go.Figure] = {}

    date_cols = _detect_date_columns(df)
    num_cols  = [c for c in df.select_dtypes(include="number").columns if not _is_id_col(c)]
    # Exclude date-like columns from categorical to avoid date bars / box plots
    cat_cols  = [
        c for c in df.select_dtypes(include=["object", "category", "string"]).columns
        if df[c].nunique() <= 50 and c not in date_cols
    ]

    # ── 1. Grouped time series (date + category + numeric) ────────────────────
    if date_cols and cat_cols and num_cols:
        group_cats = [c for c in cat_cols if df[c].nunique() <= 8]
        if group_cats:
            fig = _grouped_time_series(df, date_cols[0], group_cats[0], num_cols[0])
            if fig:
                title = f"{num_cols[0]} by {group_cats[0]} Over Time"
                figures[title] = fig

    # ── 2. Simple time series ─────────────────────────────────────────────────
    if date_cols and num_cols and len(figures) < _MAX_CHARTS:
        fig = generate_time_series_chart(df, date_cols[0], num_cols)
        if fig:
            figures[f"Trend Over Time ({date_cols[0]})"] = fig

    # ── 3. Scatter plot (correlation between two numeric columns) ─────────────
    if len(num_cols) >= 2 and len(figures) < _MAX_CHARTS:
        color_col = cat_cols[0] if (cat_cols and df[cat_cols[0]].nunique() <= 8) else None
        fig = _scatter_chart(df, num_cols, color_col)
        if fig:
            x, y = _pick_scatter_pair(num_cols)
            figures[f"{y} vs {x}"] = fig

    # ── 4. Bar charts for categorical columns ─────────────────────────────────
    for col in cat_cols:
        if len(figures) >= _MAX_CHARTS:
            break
        # Skip column if it's already used as color grouping in grouped time series
        fig = _bar_chart(df, col, num_cols)
        if fig:
            figures[f"Top Values: {col}"] = fig

    # ── 5. Box plots (distribution of numeric by category) ───────────────────
    box_cats = [c for c in cat_cols if df[c].nunique() <= 8]
    for cat_col in box_cats:
        if len(figures) >= _MAX_CHARTS:
            break
        for num_col in num_cols[:2]:
            if len(figures) >= _MAX_CHARTS:
                break
            fig = _box_chart(df, cat_col, num_col)
            if fig:
                figures[f"{num_col} by {cat_col}"] = fig

    # ── 6. Histograms for remaining numeric columns ───────────────────────────
    for col in num_cols:
        if len(figures) >= _MAX_CHARTS:
            break
        fig = _histogram(df, col)
        if fig:
            key = f"Distribution: {col}"
            if key not in figures:
                figures[key] = fig

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
    rows  = -(-len(items) // cols)

    fig = make_subplots(
        rows=rows, cols=cols,
        specs=[[{"type": "indicator"}] * cols for _ in range(rows)],
        vertical_spacing=0.1,
    )

    for i, (name, value) in enumerate(items):
        row = i // cols + 1
        col = i % cols + 1
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
        numeric_cols = [c for c in df.select_dtypes(include="number").columns if not _is_id_col(c)]

    if not numeric_cols:
        return None

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
        color_discrete_sequence=_PALETTE,
    )
    fig.update_traces(mode="lines+markers", marker_size=4)
    fig.update_layout(hovermode="x unified", legend_title="Metric")
    return fig


def generate_bar_charts(df: pd.DataFrame) -> dict[str, go.Figure]:
    """Generate one bar chart per low-cardinality categorical column."""
    figures = {}
    num_cols = [c for c in df.select_dtypes(include="number").columns if not _is_id_col(c)]
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
        if _is_id_col(col):
            continue
        fig = _histogram(df, col)
        if fig:
            figures[f"Distribution: {col}"] = fig
    return figures


# ── Internal chart builders ───────────────────────────────────────────────────

def _grouped_time_series(
    df: pd.DataFrame,
    date_col: str,
    cat_col: str,
    num_col: str,
) -> go.Figure | None:
    """Line chart of a numeric metric broken down by category over time."""
    try:
        tmp = df[[date_col, cat_col, num_col]].copy()
        tmp[date_col] = pd.to_datetime(tmp[date_col], errors="coerce")
        tmp = tmp.dropna(subset=[date_col])
        if tmp.empty:
            return None

        # Aggregate to monthly to avoid noise on dense datasets
        tmp["_month"] = tmp[date_col].dt.to_period("M").dt.to_timestamp()
        grouped = (
            tmp.groupby(["_month", cat_col], observed=True)[num_col]
            .sum()
            .reset_index()
            .rename(columns={"_month": date_col})
        )
        if grouped.empty or grouped[cat_col].nunique() < 2:
            return None

        fig = px.line(
            grouped,
            x=date_col,
            y=num_col,
            color=cat_col,
            title=f"{num_col} by {cat_col} Over Time",
            labels={num_col: num_col, date_col: "Period"},
            template=_CHART_TEMPLATE,
            color_discrete_sequence=_PALETTE,
        )
        fig.update_traces(mode="lines+markers", marker_size=4)
        fig.update_layout(hovermode="x unified", legend_title=cat_col)
        return fig
    except Exception:
        return None


def _scatter_chart(
    df: pd.DataFrame,
    num_cols: list[str],
    color_col: str | None,
) -> go.Figure | None:
    """Scatter plot of the two most informative numeric columns."""
    x_col, y_col = _pick_scatter_pair(num_cols)
    if x_col == y_col:
        return None
    try:
        plot_df = df[[x_col, y_col]].dropna()
        if color_col:
            plot_df = df[[x_col, y_col, color_col]].dropna()
        if len(plot_df) < 10:
            return None

        fig = px.scatter(
            plot_df,
            x=x_col,
            y=y_col,
            color=color_col,
            title=f"{y_col} vs {x_col}",
            opacity=0.65,
            template=_CHART_TEMPLATE,
            color_discrete_sequence=_PALETTE,
        )
        fig.update_layout(legend_title=color_col or "")
        return fig
    except Exception:
        return None


def _box_chart(
    df: pd.DataFrame,
    cat_col: str,
    num_col: str,
) -> go.Figure | None:
    """Box plot showing distribution of a numeric column across categories."""
    try:
        plot_df = df[[cat_col, num_col]].dropna()
        if plot_df.empty or plot_df[cat_col].nunique() < 2:
            return None

        fig = px.box(
            plot_df,
            x=cat_col,
            y=num_col,
            color=cat_col,
            title=f"{num_col} Distribution by {cat_col}",
            template=_CHART_TEMPLATE,
            color_discrete_sequence=_PALETTE,
        )
        fig.update_layout(showlegend=False, xaxis_title=cat_col, yaxis_title=num_col)
        return fig
    except Exception:
        return None


def _bar_chart(
    df: pd.DataFrame,
    cat_col: str,
    num_cols: list[str],
) -> go.Figure | None:
    """Horizontal bar chart: top categories by count or by a numeric sum."""
    if cat_col not in df.columns:
        return None

    clean_num_cols = [c for c in num_cols if not _is_id_col(c)]

    if clean_num_cols:
        agg_col = clean_num_cols[0]
        grouped = (
            df.groupby(cat_col, observed=True)[agg_col]
            .sum()
            .sort_values(ascending=False)
            .head(_MAX_CATEGORIES)
        )
        x_label = f"Total {agg_col}"
    else:
        grouped = df[cat_col].value_counts().head(_MAX_CATEGORIES)
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
        if any(kw in col.lower() for kw in ["date", "month", "time", "dt", "created", "updated", "timestamp"]):
            date_cols.append(col)
    return list(dict.fromkeys(date_cols))


def _is_id_col(col_name: str) -> bool:
    """Heuristic: skip columns that look like ID fields."""
    lower = col_name.lower()
    return lower.endswith("_id") or lower == "id" or lower.endswith("_key")


def _pick_scatter_pair(num_cols: list[str]) -> tuple[str, str]:
    """Pick the best two numeric columns for a scatter plot."""
    if len(num_cols) < 2:
        return num_cols[0], num_cols[0]
    # Prefer columns that don't look like pure counters/flags
    preferred = [c for c in num_cols if not any(
        kw in c.lower() for kw in ["count", "flag", "id", "index"]
    )]
    cols = preferred if len(preferred) >= 2 else num_cols
    return cols[0], cols[1]


def _parse_kpi_value(value: str) -> float:
    """Extract a numeric value from a formatted KPI string."""
    clean = value.replace("$", "").replace(",", "").replace("%", "").replace("x", "")
    clean = clean.replace(" days", "").replace(" hrs", "").replace(" yrs", "").replace(" mo", "")
    if "K" in clean:
        return float(clean.replace("K", "")) * 1_000
    if "M" in clean:
        return float(clean.replace("M", "")) * 1_000_000
    try:
        return float(clean.strip("+"))
    except ValueError:
        return 0.0


def _kpi_suffix(value: str) -> str:
    if "%" in value:
        return "%"
    if value.endswith("x"):
        return "x"
    return ""
