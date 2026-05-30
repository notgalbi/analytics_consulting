"""
claude_summary.py — Claude API integration for executive summary generation.

PRIVACY GUARANTEE: Only aggregate statistics and metadata are sent to Claude.
Raw rows, PII column values, and individual records are never included.

Public API:
    build_safe_summary_payload(profile, domain, kpis, pii_report) → dict
    generate_executive_summary(payload)                            → str
"""
from __future__ import annotations

import json
import os
from dotenv import load_dotenv

load_dotenv()

_MODEL      = "claude-sonnet-4-6"
_MAX_TOKENS = 1500


# ── Public functions ──────────────────────────────────────────────────────────

def build_safe_summary_payload(
    profile: dict,
    domain: str,
    kpis: list[dict],
    pii_report: dict,
) -> dict:
    """
    Construct a payload from safe aggregate data only.
    Nothing here contains raw rows or PII values.
    """
    return {
        "domain":           domain,
        "row_count":        profile.get("row_count"),
        "col_count":        profile.get("col_count"),
        "completeness_pct": profile.get("completeness_pct"),
        "duplicate_report": profile.get("duplicate_report", {}),
        "missing_columns":  [
            {"column": col, **vals}
            for col, vals in profile.get("missing_values", {}).items()
        ],
        "numeric_summary":  profile.get("numeric_summary", {}),
        "categorical_summary": {
            col: {
                "unique_count": stats["unique_count"],
                "most_common":  stats["most_common"],
                "top_values":   dict(list(stats.get("top_values", {}).items())[:5]),
            }
            for col, stats in profile.get("categorical_summary", {}).items()
        },
        "date_summary":     profile.get("date_summary", {}),
        "kpi_names":        [k["name"] for k in kpis[:8]],
        "pii_risk_level":   pii_report.get("risk_level", "none"),
        "pii_types_found":  pii_report.get("pii_types_found", []),
        "pii_column_count": pii_report.get("total_pii_columns", 0),
    }


def generate_executive_summary(payload: dict) -> str:
    """
    Generate an executive summary using Claude.
    Falls back to a structured template if ANTHROPIC_API_KEY is not set.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()

    if api_key:
        return _call_claude(payload, api_key)
    else:
        return _template_summary(payload)


# ── Claude integration ────────────────────────────────────────────────────────

def _call_claude(payload: dict, api_key: str) -> str:
    """Send the safe payload to Claude and return the summary text."""
    try:
        import anthropic

        prompt = _build_prompt(payload)
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text

    except ImportError:
        return (
            "**[anthropic package not installed]**\n\n"
            + _template_summary(payload)
            + "\n\n*Install `anthropic` and add ANTHROPIC_API_KEY to .env for AI summaries.*"
        )
    except Exception as e:
        return (
            f"**[Claude API error: {e}]**\n\n"
            + _template_summary(payload)
        )


def _build_prompt(payload: dict) -> str:
    """Construct the Claude prompt from aggregate payload only."""
    return f"""You are a senior data analyst writing a concise executive summary for a client deliverable.

Below is a dataset profile containing only aggregate statistics — no raw data or individual records.

Dataset context:
{json.dumps(payload, indent=2, default=str)}

Write a professional executive summary in markdown covering exactly these sections:

## 1. Dataset Overview
What this dataset appears to contain, the domain ({payload.get('domain')}), scope, and time range if available.

## 2. Data Quality Notes
Completeness rate, missing value patterns, duplicate rows, and any concerns the client should be aware of.

## 3. KPI Highlights
The most important metrics available in this dataset. Reference the kpi_names list and explain why each matters.

## 4. Business Insights
2–3 meaningful patterns or observations you can infer from the aggregate summaries. Do not invent numbers not in the profile.

## 5. Recommended Next Steps
Concrete, actionable recommendations for the client (data cleanup, dashboarding, deeper analysis, data enrichment).

## 6. Assumptions & Limitations
What you cannot determine from aggregate statistics alone. Be honest about limitations.

Tone: professional but accessible. No jargon. Keep each section to 2–4 sentences."""


# ── Template fallback ─────────────────────────────────────────────────────────

def _template_summary(payload: dict) -> str:
    """Structured offline summary when no API key is configured."""
    domain       = payload.get("domain", "general").title()
    rows         = payload.get("row_count", 0)
    cols         = payload.get("col_count", 0)
    completeness = payload.get("completeness_pct", 0)
    dup_count    = payload.get("duplicate_report", {}).get("duplicate_rows", 0)
    kpi_names    = ", ".join(payload.get("kpi_names", [])[:5]) or "N/A"
    pii_risk     = payload.get("pii_risk_level", "none").upper()
    pii_count    = payload.get("pii_column_count", 0)
    missing_cols = payload.get("missing_columns", [])
    date_ranges  = payload.get("date_summary", {})
    date_info    = ""
    if date_ranges:
        first_date_col = next(iter(date_ranges))
        d = date_ranges[first_date_col]
        date_info = f" covering **{d['min']}** to **{d['max']}** ({d.get('span_days', 0)} days)"

    quality_note = (
        f"Data completeness is **{completeness}%**"
        + (f", with **{len(missing_cols)}** column(s) containing missing values" if missing_cols else "")
        + (f" and **{dup_count}** duplicate rows detected" if dup_count else "")
        + "."
    )

    pii_note = (
        f"**{pii_count}** sensitive column(s) were detected (PII risk: **{pii_risk}**) "
        "and have been masked in this report."
        if pii_count else
        "No sensitive columns (PII) were detected in this dataset."
    )

    return f"""## Executive Summary

## 1. Dataset Overview
This **{domain}** dataset contains **{rows:,} records** across **{cols} columns**{date_info}. \
The structure suggests it can support {domain.lower()}-focused analysis and reporting.

## 2. Data Quality Notes
{quality_note} {pii_note}

## 3. KPI Highlights
Based on the column structure, the following KPIs are recommended for tracking: \
**{kpi_names}**. These metrics align with typical {domain.lower()} reporting requirements.

## 4. Business Insights
The dataset appears complete enough for initial analysis. Categorical breakdowns and numeric \
distributions suggest there are meaningful patterns to surface. A deeper dive into high-variance \
numeric columns and the most common categorical values will yield actionable insight.

## 5. Recommended Next Steps
1. Confirm KPI definitions and targets with the client before finalising the dashboard.
2. Address missing values in flagged columns before running statistical models.
3. Set up a recurring data refresh schedule once the pipeline is validated.
4. Enrich the dataset with benchmark or target data for comparative analysis.

## 6. Assumptions & Limitations
This summary was generated from aggregate statistics only — no individual records were reviewed. \
Column name matching was used to infer domain and KPIs; client confirmation is recommended. \
Trend analysis requires time-series data that may not be fully represented here.

---
*Generated from profile metadata only. No raw data was used in this analysis.*
*Add `ANTHROPIC_API_KEY` to `.env` for Claude-powered summaries.*"""
