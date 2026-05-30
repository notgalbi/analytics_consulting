"""
claude_summary.py — Generates an executive summary using Claude.

PRIVACY GUARANTEE: Only metadata and aggregate statistics are sent to Claude.
Raw row data, PII column values, and individual records are never included.
"""

import os
import json
from dotenv import load_dotenv

load_dotenv()

_CLAUDE_MODEL = "claude-sonnet-4-6"


def generate_summary(
    metadata: dict,
    profile: dict,
    pii_detections: list[dict],
    dataset_type: str,
    kpis: list[dict],
) -> str:
    """
    Build an executive summary.
    Returns a Claude-generated summary when CLAUDE_API_KEY is set,
    otherwise returns a well-structured template fallback.
    """
    prompt = _build_prompt(metadata, profile, pii_detections, dataset_type, kpis)
    api_key = os.getenv("CLAUDE_API_KEY", "").strip()

    if api_key:
        return _call_claude(prompt, api_key)
    else:
        return _template_summary(metadata, profile, dataset_type, kpis)


def _build_prompt(
    metadata: dict,
    profile: dict,
    pii_detections: list[dict],
    dataset_type: str,
    kpis: list[dict],
) -> str:
    """
    Construct a prompt from aggregate statistics only.
    NO raw rows are included.
    """
    numeric_summary = {
        col: {k: v for k, v in stats.items()}
        for col, stats in profile.get("numeric", {}).items()
    }
    categorical_summary = {
        col: {"unique_count": stats["unique_count"], "most_common": stats["most_common"]}
        for col, stats in profile.get("categorical", {}).items()
    }
    pii_types = [f"{p['column']} ({p['pii_type']})" for p in pii_detections]
    kpi_names = [k["name"] for k in kpis[:6]]

    context = {
        "filename": metadata.get("filename"),
        "row_count": profile.get("row_count"),
        "col_count": profile.get("col_count"),
        "completeness_pct": profile.get("completeness_pct"),
        "duplicate_rows": profile.get("duplicate_rows"),
        "dataset_type": dataset_type,
        "detected_pii_columns": pii_types,
        "numeric_aggregates": numeric_summary,
        "categorical_summaries": categorical_summary,
        "recommended_kpis": kpi_names,
    }

    return f"""You are a senior data analyst writing a concise executive summary for a client report.

Dataset context (aggregate statistics only — no raw data):
{json.dumps(context, indent=2)}

Write a professional executive summary (3–5 paragraphs) covering:
1. What this dataset appears to contain and its overall quality
2. Key patterns or insights from the numeric and categorical summaries
3. Data quality notes (missing values, duplicates, PII found)
4. Recommended KPIs to track and why they matter for this dataset type
5. Suggested next steps for the client

Keep the tone professional but accessible. Do not invent specific numbers beyond what is provided."""


def _call_claude(prompt: str, api_key: str) -> str:
    """Call Claude API with the prepared prompt."""
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=_CLAUDE_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text
    except Exception as e:
        return f"[Claude API error — falling back to template]\n\n{_template_summary_from_prompt(prompt)}\n\n(Error: {e})"


def _template_summary(
    metadata: dict,
    profile: dict,
    dataset_type: str,
    kpis: list[dict],
) -> str:
    """Offline template when no API key is configured."""
    filename    = metadata.get("filename", "Unknown")
    rows        = profile.get("row_count", 0)
    cols        = profile.get("col_count", 0)
    completeness = profile.get("completeness_pct", 0)
    duplicates  = profile.get("duplicate_rows", 0)
    kpi_names   = ", ".join(k["name"] for k in kpis[:5])

    return f"""## Executive Summary

**Dataset:** {filename}
**Type Detected:** {dataset_type.title()}

### Overview
This dataset contains **{rows:,} records** across **{cols} columns**, classified as a **{dataset_type}** dataset. \
Overall data completeness stands at **{completeness}%**, with **{duplicates} duplicate rows** identified.

### Data Quality
{"The dataset is in excellent shape with high completeness." if completeness >= 90 else f"Data completeness is {completeness}%, which may require attention before analysis." } \
{"Duplicate rows should be reviewed and removed prior to final analysis." if duplicates > 0 else "No duplicate rows were detected."}

### Recommended KPIs
Based on the column structure, the following KPIs are recommended for tracking: **{kpi_names}**. \
These metrics align with the {dataset_type} domain and will provide actionable insight to stakeholders.

### Next Steps
1. Review and confirm PII masking before sharing the dataset externally.
2. Validate the detected KPIs with the client to confirm business priorities.
3. Set up a recurring refresh schedule once the data pipeline is confirmed.
4. Consider enriching the dataset with additional context (e.g., benchmarks or targets).

---
*Summary generated from aggregate statistics only. No raw data was used in this analysis.*
*Add your CLAUDE_API_KEY to .env for AI-enhanced summaries.*"""


def _template_summary_from_prompt(prompt: str) -> str:
    """Minimal fallback when Claude call itself fails."""
    return "Summary generation failed. Please check your CLAUDE_API_KEY and retry."
