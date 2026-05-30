"""
profiler.py — Generates a data quality report: missingness, duplicates,
numeric summaries, and categorical summaries.
"""

import pandas as pd


def profile(df: pd.DataFrame) -> dict:
    """
    Return a comprehensive quality report dict.
    No raw row data is included — only aggregated statistics.
    """
    report = {
        "row_count": len(df),
        "col_count": len(df.columns),
        "duplicate_rows": int(df.duplicated().sum()),
        "missing": _missing_report(df),
        "numeric": _numeric_report(df),
        "categorical": _categorical_report(df),
        "date_columns": _date_columns(df),
        "completeness_pct": _completeness(df),
    }
    return report


def _missing_report(df: pd.DataFrame) -> dict:
    """Per-column missing value counts and percentages."""
    missing_counts = df.isnull().sum()
    total = len(df)
    result = {}
    for col in df.columns:
        count = int(missing_counts[col])
        result[col] = {
            "missing_count": count,
            "missing_pct": round(count / total * 100, 2) if total else 0,
        }
    return result


def _numeric_report(df: pd.DataFrame) -> dict:
    """Descriptive stats for numeric columns."""
    numeric_cols = df.select_dtypes(include="number").columns
    result = {}
    for col in numeric_cols:
        series = df[col].dropna()
        if series.empty:
            continue
        result[col] = {
            "mean":   round(float(series.mean()), 4),
            "median": round(float(series.median()), 4),
            "std":    round(float(series.std()), 4),
            "min":    round(float(series.min()), 4),
            "max":    round(float(series.max()), 4),
            "q25":    round(float(series.quantile(0.25)), 4),
            "q75":    round(float(series.quantile(0.75)), 4),
            "zeros":  int((series == 0).sum()),
            "negatives": int((series < 0).sum()),
        }
    return result


def _categorical_report(df: pd.DataFrame) -> dict:
    """Top values and cardinality for object/string columns."""
    cat_cols = df.select_dtypes(include=["object", "category", "string"]).columns
    result = {}
    for col in cat_cols:
        series = df[col].dropna()
        if series.empty:
            continue
        vc = series.value_counts()
        result[col] = {
            "unique_count": int(series.nunique()),
            "top_values": vc.head(10).to_dict(),   # {value: count}
            "most_common": str(vc.index[0]) if not vc.empty else None,
        }
    return result


def _date_columns(df: pd.DataFrame) -> list[str]:
    """Return column names that look like dates (dtype or name heuristic)."""
    date_cols = list(df.select_dtypes(include=["datetime", "datetimetz"]).columns)
    # Also try to detect object columns that parse as dates
    for col in df.select_dtypes(include="object").columns:
        if any(kw in col.lower() for kw in ["date", "time", "dt", "created", "updated", "timestamp"]):
            date_cols.append(col)
    return list(dict.fromkeys(date_cols))  # deduplicated, order-preserving


def _completeness(df: pd.DataFrame) -> float:
    """Overall data completeness percentage (non-null cells / total cells)."""
    if df.empty:
        return 0.0
    total_cells = df.size
    non_null = int(df.notnull().sum().sum())
    return round(non_null / total_cells * 100, 2)
