"""
pii_detector.py — Detects sensitive columns in a pandas DataFrame using
column-name heuristics and value-level regex sampling.

Public API:
    detect_pii_columns(df)   → list of detected PII column dicts
    sanitize_dataframe(df)   → (sanitized_df, sensitive_col_names, warning_msg)
    generate_pii_report(df)  → structured report dict for admin review
"""
from __future__ import annotations

import re
import pandas as pd


# ── Column-name keyword lookup ────────────────────────────────────────────────
# Maps PII type → substrings that indicate that type in a column name.
# Order matters: more specific entries should come first.
_COLUMN_KEYWORDS: dict[str, list[str]] = {
    "ssn":         ["ssn", "social_security", "social security", "sin", "tax_id", "taxid"],
    "email":       ["email", "e-mail", "e_mail"],
    "phone":       ["phone", "mobile", "cell", "tel", "fax"],
    "dob":         ["dob", "date_of_birth", "birthdate", "birthday", "birth_date"],
    "address":     ["address", "addr", "street", "city", "zip", "postal", "state", "country"],
    "name":        ["firstname", "first_name", "lastname", "last_name", "fullname",
                    "full_name", "customer_name", "employee_name", "contact_name"],
    "employee_id": ["employee_id", "emp_id", "staff_id", "worker_id", "personnel_id"],
    "customer_id": ["customer_id", "cust_id", "client_id", "user_id", "account_id"],
}

# Standalone "name" keyword is intentionally last — it's a common false-positive
# (e.g. "product_name", "company_name") so we only match it when no other type
# claimed the column first.
_STANDALONE_NAME_KEYWORDS = ["name"]

# ── Value regex patterns ──────────────────────────────────────────────────────
# DOB is intentionally absent — ISO date strings are indistinguishable from
# any other date column by value alone. DOB is detected via column name only.
_VALUE_REGEXES: dict[str, re.Pattern] = {
    "email": re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"),
    "phone": re.compile(r"^\+?1?[\s.\-(]?\(?\d{3}\)?[\s.\-)]?\d{3}[\s.\-]?\d{4}$"),
    "ssn":   re.compile(r"^\d{3}-\d{2}-\d{4}$"),
}

# Per-type redaction labels used in sanitize_dataframe
_REDACTION_LABELS: dict[str, str] = {
    "email":       "EMAIL_REDACTED",
    "phone":       "PHONE_REDACTED",
    "ssn":         "SSN_REDACTED",
    "name":        "NAME_REDACTED",
    "address":     "ADDRESS_REDACTED",
    "dob":         "DOB_REDACTED",
    "employee_id": "EMPLOYEE_ID_REDACTED",
    "customer_id": "CUSTOMER_ID_REDACTED",
}

# Types that trigger a high-severity warning
_HIGH_RISK_TYPES = {"ssn", "dob"}
_MEDIUM_RISK_TYPES = {"email", "phone", "name", "address"}

_SAMPLE_SIZE = 30  # number of non-null values to sample for regex checks


# ── Public functions ──────────────────────────────────────────────────────────

def detect_pii_columns(df: pd.DataFrame) -> list[dict]:
    """
    Scan df for PII columns using column-name keywords and value-level regexes.

    Returns a list of dicts:
        {
            "column":           str,   # column name in df
            "pii_type":         str,   # e.g. "email", "ssn", "name"
            "detection_method": str,   # "column_name" | "value_pattern"
            "redaction_label":  str,   # e.g. "EMAIL_REDACTED"
        }
    """
    detections: list[dict] = []
    flagged: set[str] = set()

    # Pass 1: column-name matching (specific keywords first)
    for col in df.columns:
        pii_type = _match_column_name(col)
        if pii_type:
            detections.append(_make_detection(col, pii_type, "column_name"))
            flagged.add(col)

    # Pass 2: value-level regex scan on unflagged object/string columns
    for col in df.columns:
        if col in flagged:
            continue
        if df[col].dtype not in (object, "string"):
            continue
        sample = df[col].dropna().astype(str).head(_SAMPLE_SIZE)
        pii_type = _match_values(sample)
        if pii_type:
            detections.append(_make_detection(col, pii_type, "value_pattern"))
            flagged.add(col)

    return detections


def sanitize_dataframe(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str], str]:
    """
    Detect PII columns and return a masked copy of df.

    Returns:
        sanitized_df      — copy of df with sensitive values replaced
        sensitive_columns — list of column names that were masked
        warning_message   — plain-text warning for admin review
    """
    detections = detect_pii_columns(df)
    sanitized = df.copy()

    for item in detections:
        col = item["column"]
        label = item["redaction_label"]
        if col in sanitized.columns:
            sanitized[col] = label

    sensitive_columns = [d["column"] for d in detections]
    warning_message = _build_warning(detections)

    return sanitized, sensitive_columns, warning_message


def generate_pii_report(df: pd.DataFrame) -> dict:
    """
    Return a structured PII report dict suitable for admin review display.

        {
            "total_pii_columns": int,
            "detected":          list[dict],   # full detection records
            "pii_types_found":   list[str],    # unique types present
            "risk_level":        str,           # "none" | "low" | "medium" | "high"
            "admin_warning":     str,
        }
    """
    detections = detect_pii_columns(df)
    types_found = list({d["pii_type"] for d in detections})

    if any(t in _HIGH_RISK_TYPES for t in types_found):
        risk_level = "high"
    elif any(t in _MEDIUM_RISK_TYPES for t in types_found):
        risk_level = "medium"
    elif types_found:
        risk_level = "low"
    else:
        risk_level = "none"

    return {
        "total_pii_columns": len(detections),
        "detected":          detections,
        "pii_types_found":   types_found,
        "risk_level":        risk_level,
        "admin_warning":     _build_warning(detections),
    }


# ── Internal helpers ──────────────────────────────────────────────────────────

def _match_column_name(col: str) -> str | None:
    """
    Return the PII type whose keywords match this column name, or None.
    Checks specific multi-word keywords before the generic 'name' fallback.
    """
    normalized = col.lower().replace(" ", "_").replace("-", "_")

    for pii_type, keywords in _COLUMN_KEYWORDS.items():
        for kw in keywords:
            if kw in normalized:
                return pii_type

    # Generic standalone "name" check — only after specific keywords failed.
    # Skips columns like "product_name" or "company_name" by requiring the
    # match to appear at the start or after an underscore boundary.
    for kw in _STANDALONE_NAME_KEYWORDS:
        if re.search(r"(^|_)" + re.escape(kw) + r"(_|$)", normalized):
            return "name"

    return None


def _match_values(sample: pd.Series) -> str | None:
    """Return the first PII type whose regex matches >50% of sample values."""
    for pii_type, pattern in _VALUE_REGEXES.items():
        hit_rate = sample.apply(lambda v: bool(pattern.match(str(v).strip()))).mean()
        if hit_rate > 0.5:
            return pii_type
    return None


def _make_detection(col: str, pii_type: str, method: str) -> dict:
    return {
        "column":           col,
        "pii_type":         pii_type,
        "detection_method": method,
        "redaction_label":  _REDACTION_LABELS.get(pii_type, "REDACTED"),
    }


def _build_warning(detections: list[dict]) -> str:
    if not detections:
        return "No PII columns detected."

    lines = ["⚠️  Sensitive columns detected — review before sharing with clients:\n"]
    for d in detections:
        lines.append(
            f"  • {d['column']} ({d['pii_type'].upper()}) "
            f"— detected via {d['detection_method'].replace('_', ' ')} "
            f"→ masked as {d['redaction_label']}"
        )

    high_risk = [d for d in detections if d["pii_type"] in _HIGH_RISK_TYPES]
    if high_risk:
        lines.append(
            f"\n🔴 HIGH RISK: {len(high_risk)} column(s) contain SSN or date-of-birth data. "
            "Verify legal basis for processing before proceeding."
        )

    return "\n".join(lines)
