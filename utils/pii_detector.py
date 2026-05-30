"""
pii_detector.py — Identifies columns that likely contain PII using
column-name heuristics and regex sampling on actual values.
"""
from __future__ import annotations

import re
import pandas as pd


# Column-name fragments mapped to PII category
_NAME_PATTERNS: dict[str, list[str]] = {
    "email":   ["email", "e-mail", "e_mail", "mail"],
    "phone":   ["phone", "mobile", "cell", "tel", "fax"],
    "name":    ["name"],
    "address": ["address", "street", "addr", "city", "zip", "postal", "state", "country"],
    "ssn":     ["ssn", "social_security", "sin", "tax_id", "taxid"],
    "dob":     ["dob", "birth", "birthday", "date_of_birth", "birthdate"],
}

# Regex patterns used to scan sample values
_VALUE_REGEXES: dict[str, re.Pattern] = {
    "email": re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"),
    "phone": re.compile(r"^\+?1?[\s.\-]?\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}$"),
    "ssn":   re.compile(r"^\d{3}-\d{2}-\d{4}$"),
}

_SAMPLE_SIZE = 20  # rows to sample for value-based detection


def detect_pii(df: pd.DataFrame) -> list[dict]:
    """
    Return a list of dicts, one per detected PII column:
      { "column": str, "pii_type": str, "detection_method": "name_pattern" | "value_regex" }
    """
    results: list[dict] = []
    seen_columns: set[str] = set()

    for col in df.columns:
        pii_type = _check_column_name(col)
        if pii_type:
            results.append({"column": col, "pii_type": pii_type, "detection_method": "name_pattern"})
            seen_columns.add(col)

    # Value-level scan only on string/object columns not already flagged
    for col in df.columns:
        if col in seen_columns:
            continue
        if df[col].dtype not in (object, "string"):
            continue
        sample = df[col].dropna().astype(str).head(_SAMPLE_SIZE)
        pii_type = _check_values(sample)
        if pii_type:
            results.append({"column": col, "pii_type": pii_type, "detection_method": "value_regex"})
            seen_columns.add(col)

    return results


def sanitize(df: pd.DataFrame, pii_detections: list[dict]) -> pd.DataFrame:
    """
    Return a copy of df with PII columns masked.
    Keeps column structure intact so downstream stats still work on shape.
    """
    sanitized = df.copy()
    for item in pii_detections:
        col = item["column"]
        pii_type = item["pii_type"]
        if col not in sanitized.columns:
            continue
        sanitized[col] = f"[REDACTED:{pii_type.upper()}]"
    return sanitized


# ── Helpers ──────────────────────────────────────────────────────────────────

def _check_column_name(col: str) -> str | None:
    """Return the first matching PII category for a column name, or None."""
    col_lower = col.lower().replace(" ", "_")
    for pii_type, fragments in _NAME_PATTERNS.items():
        for fragment in fragments:
            if fragment in col_lower:
                return pii_type
    return None


def _check_values(sample: pd.Series) -> str | None:
    """Return the first matching PII category found in the sample values, or None."""
    for pii_type, pattern in _VALUE_REGEXES.items():
        matches = sample.apply(lambda v: bool(pattern.match(str(v).strip())))
        # Flag if >50% of non-null sample rows match the pattern
        if matches.mean() > 0.5:
            return pii_type
    return None
