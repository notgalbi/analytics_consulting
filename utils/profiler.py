"""
profiler.py — Reusable pandas data profiling module.

Public API:
    profile_dataframe(df)        → full profile dict (used by Streamlit + Claude)
    get_column_summary(df)       → column names + dtypes
    get_missing_value_report(df) → per-column missingness
    get_duplicate_report(df)     → duplicate row stats
    get_numeric_summary(df)      → min/max/mean/median per numeric column
    get_categorical_summary(df)  → top values + cardinality per string column
    get_date_summary(df)         → min/max per date column
"""
from __future__ import annotations

import pandas as pd


def profile_dataframe(df: pd.DataFrame) -> dict:
    """
    Return a complete profile dict.
    Safe to pass directly to Claude — contains only aggregates, no raw rows.
    """
    return {
        "row_count":           len(df),
        "col_count":           len(df.columns),
        "completeness_pct":    _completeness(df),
        "column_summary":      get_column_summary(df),
        "missing_values":      get_missing_value_report(df),
        "duplicate_report":    get_duplicate_report(df),
        "numeric_summary":     get_numeric_summary(df),
        "categorical_summary": get_categorical_summary(df),
        "date_summary":        get_date_summary(df),
    }


def get_column_summary(df: pd.DataFrame) -> list[dict]:
    """Return a list of {column, dtype, sample_value} for every column."""
    rows = []
    for col in df.columns:
        sample = df[col].dropna().iloc[0] if df[col].notna().any() else None
        rows.append({
            "column":       col,
            "dtype":        str(df[col].dtype),
            "sample_value": str(sample) if sample is not None else "",
        })
    return rows


def get_missing_value_report(df: pd.DataFrame) -> dict[str, dict]:
    """
    Return per-column missing value counts and percentages.
    Only includes columns that have at least one missing value.
    """
    total = len(df)
    result = {}
    for col in df.columns:
        count = int(df[col].isnull().sum())
        if count > 0:
            result[col] = {
                "missing_count": count,
                "missing_pct":   round(count / total * 100, 2) if total else 0,
            }
    return result


def get_duplicate_report(df: pd.DataFrame) -> dict:
    """Return duplicate row stats."""
    dup_count = int(df.duplicated().sum())
    total = len(df)
    return {
        "duplicate_rows": dup_count,
        "duplicate_pct":  round(dup_count / total * 100, 2) if total else 0,
    }


def get_numeric_summary(df: pd.DataFrame) -> dict[str, dict]:
    """Descriptive stats for each numeric column."""
    result = {}
    for col in df.select_dtypes(include="number").columns:
        s = df[col].dropna()
        if s.empty:
            continue
        result[col] = {
            "min":       _fmt(s.min()),
            "max":       _fmt(s.max()),
            "mean":      _fmt(s.mean()),
            "median":    _fmt(s.median()),
            "std":       _fmt(s.std()),
            "q25":       _fmt(s.quantile(0.25)),
            "q75":       _fmt(s.quantile(0.75)),
            "zeros":     int((s == 0).sum()),
            "negatives": int((s < 0).sum()),
        }
    return result


def get_categorical_summary(df: pd.DataFrame) -> dict[str, dict]:
    """Cardinality and top values for object/string columns."""
    result = {}
    for col in df.select_dtypes(include=["object", "category", "string"]).columns:
        s = df[col].dropna()
        if s.empty:
            continue
        vc = s.value_counts()
        result[col] = {
            "unique_count": int(s.nunique()),
            "most_common":  str(vc.index[0]) if not vc.empty else None,
            "top_values":   {str(k): int(v) for k, v in vc.head(10).items()},
        }
    return result


def get_date_summary(df: pd.DataFrame) -> dict[str, dict]:
    """Min and max for date/datetime columns (detected by dtype or column name)."""
    result = {}
    date_cols = list(df.select_dtypes(include=["datetime", "datetimetz"]).columns)

    # Also try to coerce object columns whose name hints at dates
    for col in df.select_dtypes(include="object").columns:
        if any(kw in col.lower() for kw in ["date", "time", "dt", "created", "updated", "timestamp"]):
            try:
                parsed = pd.to_datetime(df[col], errors="coerce")
                if parsed.notna().mean() > 0.7:   # mostly parseable
                    date_cols.append(col)
                    df = df.copy()
                    df[col] = parsed
            except Exception:
                pass

    for col in dict.fromkeys(date_cols):   # deduplicated
        s = pd.to_datetime(df[col], errors="coerce").dropna()
        if s.empty:
            continue
        result[col] = {
            "min": str(s.min().date()),
            "max": str(s.max().date()),
            "span_days": (s.max() - s.min()).days,
        }
    return result


# ── Helpers ───────────────────────────────────────────────────────────────────

def _completeness(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0
    return round(df.notnull().sum().sum() / df.size * 100, 2)


def _fmt(val) -> float:
    """Round a numeric value to 4 decimal places."""
    try:
        return round(float(val), 4)
    except (TypeError, ValueError):
        return val
