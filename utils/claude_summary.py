"""
claude_summary.py — Claude API integration for executive summary generation.

PRIVACY GUARANTEE: Only aggregate statistics and metadata are sent to Claude.
Raw rows, PII column values, and individual records are never included.

Public API:
    build_safe_summary_payload(profile, domain, kpis, pii_report) → dict
    generate_executive_summary(payload)                            → str
    regenerate_summary(payload, current_summary, instruction)      → str
"""
from __future__ import annotations

import json
import os
from dotenv import load_dotenv

load_dotenv()

_MODEL      = "claude-sonnet-4-6"
_MAX_TOKENS = 2000


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
    return _template_summary(payload)


def stream_executive_summary(payload: dict):
    """
    Stream the executive summary token-by-token.
    Yields text chunks as Claude generates them.
    Falls back to yielding the full template at once if no API key.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        yield _template_summary(payload)
        return

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        with client.messages.stream(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            messages=[{"role": "user", "content": _build_prompt(payload)}],
        ) as stream:
            for text in stream.text_stream:
                yield text
    except ImportError:
        yield _template_summary(payload)
    except Exception as e:
        yield f"**[Claude API error: {e}]**\n\n"
        yield _template_summary(payload)


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
    return f"""You are a senior data analyst and business consultant producing a client-ready analytics report identical in quality to a top consulting firm deliverable.

The dataset profile below contains only aggregate statistics — no raw data or individual records.

Dataset context:
{json.dumps(payload, indent=2, default=str)}

Transform this data into a high-quality, actionable report using exactly the following markdown structure.

RULES — follow strictly:
- Never use generic phrases like "this dataset suggests", "further analysis is needed", or "it appears that"
- Every insight must state the business impact and the action to take
- Write in a confident, executive tone — the reader is a non-technical decision-maker
- Only reference numbers that exist in the dataset context above — do not invent figures
- Keep each section tight and direct — no filler sentences

---

## Executive Summary
Write 3–4 sentences that sound like a consulting deliverable. Lead with the single most important finding. Communicate what matters most for decision-making, not what the data contains. Close with the highest-priority action.

## Key Insights
Provide 3–5 high-impact bullet points. Each bullet must follow this structure: **[Finding]** — why it matters and what to do about it. Focus on risks, opportunities, and anomalies visible in the data.

## Business Insights
Rewrite the data patterns as business narratives. Be specific — reference actual column names, top values, and numeric summaries from the profile. Explain what each pattern means commercially and what decision it should drive. Minimum 3 insights.

## KPI Performance
For each KPI in the kpi_names list, write one sentence: what it measures, what the data indicates about it, and whether it warrants immediate attention or is in good shape.

## Data Quality Assessment
State the completeness rate, flag any missing-value columns that could distort analysis, and call out duplicate rows if present. If data quality issues could affect business decisions, say so directly.

## Recommended Actions
List 3–5 numbered, concrete next steps. Each must be specific enough to assign to a person — no vague recommendations. Prioritise by business impact.

## Assumptions & Limitations
One short paragraph. Be direct about what cannot be determined from aggregate statistics alone and what additional data would unlock deeper insight.

---

Chart-Level Insights (include only if date_summary or categorical_summary data is present):
For each major column or time dimension visible in the data, write one sentence describing the trend or distribution in plain business language and what action it suggests."""


# ── Admin revision ───────────────────────────────────────────────────────────

def regenerate_summary(payload: dict, current_summary: str, instruction: str) -> str:
    """
    Revise an existing executive summary based on an admin instruction.

    Only the safe payload (aggregates) + the current summary text + the
    admin's instruction are sent to Claude — no raw data ever leaves the app.

    Falls back gracefully when ANTHROPIC_API_KEY is not set.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return (
            f"> **[ANTHROPIC_API_KEY not set — revision not applied]**\n\n"
            f"Instruction received: *{instruction}*\n\n"
            "Add your API key to `.env` to enable Claude-powered revisions.\n\n"
            "---\n\n"
            + current_summary
        )

    prompt = f"""You are a senior data analyst and business consultant revising a client-facing analytics report.

Dataset context (aggregate statistics only — no raw data):
{json.dumps(payload, indent=2, default=str)}

Current summary:
{current_summary}

Admin revision instruction:
{instruction}

Rewrite the summary following the instruction exactly. Maintain consulting-firm quality throughout:
- Every insight must be actionable and business-focused
- Never use generic phrases like "further analysis is needed" or "this dataset suggests"
- Keep the same markdown section structure (##) unless the instruction says otherwise
- Do not invent numbers or facts not present in the dataset context

Return only the revised summary — no preamble."""

    try:
        import anthropic
        client  = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text
    except Exception as e:
        return (
            f"> **[Claude API error: {e}]**\n\n"
            + current_summary
        )


def generate_kpi_narrative(
    domain: str,
    calculated_kpis: dict[str, str],
    profile: dict,
) -> str:
    """
    Generate a 3–5 sentence AI interpretation of the calculated KPIs.
    Returns empty string gracefully when ANTHROPIC_API_KEY is not set.
    Only aggregate stats and formatted KPI values are sent — no raw data.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key or not calculated_kpis:
        return ""

    kpi_lines = "\n".join(f"  {k}: {v}" for k, v in calculated_kpis.items())
    prompt = f"""You are a senior business consultant interpreting KPI results for a {domain} business. Your analysis will appear in a client-facing report.

Calculated KPIs from {profile.get('row_count', 0):,} records:
{kpi_lines}

Write 4–5 sentences of executive-quality analysis:
- Open by naming the standout metric — is it a strength or a warning sign?
- Reference specific industry benchmarks where you know them (e.g. SaaS churn <5%, retail margin >40%)
- Identify any metric that demands immediate management attention and say why
- Close with the single highest-priority action the business should take this quarter

Rules: flowing prose only, no bullet points, no "Here is" or "Based on" opener. Be direct, specific, and confident. Never use the phrase "further analysis is needed"."""

    try:
        import anthropic
        client  = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=_MODEL,
            max_tokens=350,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text
    except Exception:
        return ""


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
