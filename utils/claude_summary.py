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
    """Route to the appropriate domain-specific prompt."""
    domain = payload.get("domain", "general")
    ctx = json.dumps(payload, indent=2, default=str)
    builder = _DOMAIN_PROMPTS.get(domain, _prompt_general)
    return builder(ctx, payload)


# ── Shared rules block ────────────────────────────────────────────────────────

_RULES = """
RULES — follow strictly:
- Never use generic phrases like "this dataset suggests", "further analysis is needed", or "it appears that"
- Every insight must state the business impact and the action to take
- Write in a confident, executive tone — the reader is a non-technical decision-maker
- Only reference numbers that exist in the dataset context above — do not invent figures
- Keep each section tight and direct — no filler sentences
"""

_STANDARD_SECTIONS = """
## Executive Summary
3–4 sentences. Lead with the single most important finding. Communicate what matters most for decision-making. Close with the highest-priority action.

## Key Insights
4–5 bullet points. Each: **[Finding]** — why it matters and what to do. Focus on risks, opportunities, and anomalies.

## Business Insights
Minimum 3 insights written as business narratives. Reference actual column names, top values, and numeric summaries. Explain commercial impact and the decision each pattern should drive.

## KPI Performance
One sentence per KPI in kpi_names: what it measures, what the data shows, and whether it needs immediate attention.

## Data Quality Assessment
Completeness rate, missing-value columns that could distort analysis, duplicate rows. State directly if any issue could affect business decisions.

## Recommended Actions
3–5 numbered steps. Each specific enough to assign to a person. Prioritise by business impact.

## Assumptions & Limitations
One short paragraph. What cannot be determined from aggregate stats alone and what additional data would unlock deeper insight.

## Chart-Level Insights
For each major column or time dimension in the data, one sentence: the trend or distribution in plain business language and what action it suggests.
"""


# ── Domain-specific prompts ───────────────────────────────────────────────────

def _prompt_real_estate(ctx: str, payload: dict) -> str:
    return f"""You are a senior real estate data analyst and business consultant producing a high-value, client-ready market report.

Focus specifically on: market performance, pricing dynamics, listing efficiency, and agent/property segmentation.

Dataset context (aggregate statistics only — no raw data):
{ctx}
{_RULES}
Use exactly this structure:

## Executive Summary
Highlight market strength or weakness. Identify risks (data gaps, pricing skew, listing inefficiencies). Provide clear business implications in 3–4 sentences.

## Key Insights
4–5 bullets covering: demand signals (sale rate, days on market), pricing distribution (avg vs median gap), data quality risks (missing sale_price), concentration risks (property types or agents). Each: **[Finding]** — business impact + action.

## Market & Pricing Analysis
Analyse sale price vs asking price spread, days on market distribution, and sale rate. Identify which property types or neighbourhoods are outperforming. Explain what each pattern means for pricing strategy and inventory decisions.

## Agent & Segment Performance
Which agents or property segments drive the most volume and fastest sales? Where is concentration risk? What operational changes would improve performance across the board?

## KPI Performance
One sentence per KPI in kpi_names: what it measures, what the data shows, and whether it needs immediate attention.

## Data Quality Assessment
Flag missing sale_price entries and explain how they distort conversion rate calculations. State completeness rate and any columns with gaps that affect pricing or performance analysis.

## Recommended Actions
3–5 numbered steps specific to real estate operations — pricing adjustments, agent coaching, listing strategy, data collection improvements.

## Assumptions & Limitations
What cannot be concluded without individual transaction records, buyer data, or market comparables.

## Chart-Level Insights
For each distribution or time trend visible in the data, one sentence: what pattern exists, what anomaly stands out, and what action it suggests."""


def _prompt_hospitality(ctx: str, payload: dict) -> str:
    return f"""You are a senior hospitality and restaurant business consultant producing a client-ready operations report.

Focus specifically on: revenue performance, cost control (food cost, labor cost, prime cost), cover volume, and reservation efficiency.

Dataset context (aggregate statistics only — no raw data):
{ctx}
{_RULES}
Use exactly this structure:

## Executive Summary
Lead with the most critical operational finding — prime cost position, revenue trend, or margin risk. State whether the operation is structurally profitable at current volume. Close with the single highest-priority action.

## Key Insights
4–5 bullets covering: prime cost vs benchmark (target <65%), food and labor cost variance, no-show revenue leakage, check size vs potential, revenue volatility. Each: **[Finding]** — business impact + action.

## Revenue & Volume Analysis
Daily revenue range, mean vs median gap, cover count trends. Identify high and low performance days. Quantify the revenue ceiling and floor and explain what drives each.

## Cost & Margin Analysis
Break down food cost %, labor cost %, and prime cost % against industry benchmarks. Identify which cost is the primary margin threat. Quantify the dollar impact of bringing costs to benchmark.

## Reservation & Guest Flow
No-show rate, walk-in vs reservation split, cover variability. Calculate the daily and annual revenue cost of no-shows. Recommend specific operational fixes.

## KPI Performance
One sentence per KPI in kpi_names: what it measures, what the data shows, and whether it needs immediate attention.

## Data Quality Assessment
Completeness rate, any missing cost or revenue fields, and how gaps affect profitability analysis.

## Recommended Actions
3–5 numbered steps specific to restaurant operations — scheduling, menu engineering, reservation policy, upsell training.

## Chart-Level Insights
For each day-of-week, cost trend, or revenue distribution visible in the data, one sentence: pattern, anomaly, and action."""


def _prompt_saas(ctx: str, payload: dict) -> str:
    return f"""You are a senior SaaS business analyst and growth consultant producing a client-ready metrics report.

Focus specifically on: revenue health (MRR, churn, LTV), growth trajectory, customer retention, and expansion opportunity.

Dataset context (aggregate statistics only — no raw data):
{ctx}
{_RULES}
Use exactly this structure:

## Executive Summary
Lead with the state of the revenue engine — is MRR growing or contracting, and is churn threatening the base? State the net revenue position and close with the single most critical action to protect or accelerate growth.

## Key Insights
4–5 bullets covering: churn rate vs benchmark (<5% monthly is critical), MRR growth trend, LTV:CAC health, plan mix concentration risk, NPS signal. Each: **[Finding]** — business impact + action.

## Revenue & Retention Analysis
MRR trends, churn rate, and net revenue retention. Quantify monthly revenue at risk from current churn. Identify which plans or cohorts churn fastest and what that means for pricing strategy.

## Growth & Expansion Analysis
MoM growth rate, upsell signals, plan distribution. Is growth coming from new customers or expansion? Which plan tier offers the best LTV and should be prioritised in acquisition.

## Customer Health & NPS
NPS distribution, satisfaction scores, usage signals. Identify the customer profile most likely to churn vs expand. Recommend interventions for at-risk segments.

## KPI Performance
One sentence per KPI in kpi_names: what it measures, what the data shows, and whether it needs immediate attention.

## Data Quality Assessment
Completeness, missing MRR or churn fields, and how gaps affect cohort and retention analysis.

## Recommended Actions
3–5 numbered steps specific to SaaS operations — churn intervention, pricing strategy, onboarding improvement, expansion plays.

## Chart-Level Insights
For each plan distribution, churn trend, or MRR movement visible in the data, one sentence: pattern, anomaly, and action."""


def _prompt_ecommerce(ctx: str, payload: dict) -> str:
    return f"""You are a senior ecommerce and retail analyst producing a client-ready performance report.

Focus specifically on: revenue performance, conversion and return rates, product and category mix, discount impact, and fulfilment efficiency.

Dataset context (aggregate statistics only — no raw data):
{ctx}
{_RULES}
Use exactly this structure:

## Executive Summary
Lead with the top-line revenue position and the single biggest risk to margin — return rate, discount dependency, or category concentration. Close with the highest-priority commercial action.

## Key Insights
4–5 bullets covering: average order value vs benchmark, return rate impact on net revenue, discount rate and margin erosion, top category concentration risk, fulfilment speed. Each: **[Finding]** — business impact + action.

## Revenue & Order Analysis
Revenue distribution, AOV trends, order volume. Identify which categories or channels drive the most revenue and profit. Quantify the margin cost of current discount levels.

## Returns & Fulfilment
Return rate by category or product. Calculate the gross revenue lost to returns. Identify fulfilment speed patterns and their relationship to customer satisfaction.

## Product & Category Mix
Which products or categories dominate volume vs margin? Where is concentration risk? What assortment changes would improve blended margin?

## KPI Performance
One sentence per KPI in kpi_names: what it measures, what the data shows, and whether it needs immediate attention.

## Data Quality Assessment
Completeness, missing price or return fields, and how gaps affect net revenue and margin calculations.

## Recommended Actions
3–5 numbered steps specific to ecommerce — discount policy, returns reduction, category investment, fulfilment improvement.

## Chart-Level Insights
For each category distribution, return trend, or revenue pattern visible in the data, one sentence: pattern, anomaly, and action."""


def _prompt_sales(ctx: str, payload: dict) -> str:
    return f"""You are a senior sales performance analyst and revenue consultant producing a client-ready sales report.

Focus specifically on: revenue attainment, pipeline velocity, rep performance, product mix, and discount discipline.

Dataset context (aggregate statistics only — no raw data):
{ctx}
{_RULES}
Use exactly this structure:

## Executive Summary
Lead with revenue position — is the team hitting target, and where is the biggest drag? State whether the pipeline is healthy or at risk. Close with the single most impactful action to accelerate revenue.

## Key Insights
4–5 bullets covering: revenue trend and MoM growth, average deal size vs target, discount rate and margin risk, rep or region concentration, win rate signals. Each: **[Finding]** — business impact + action.

## Revenue Performance
Total revenue, trend, average order value, and volume. Identify which reps, regions, or products are outperforming. Quantify the revenue gap from underperforming segments.

## Pipeline & Deal Velocity
Deal size distribution, close rate signals, and sales cycle indicators. Where is revenue being left on the table and why?

## Discount & Margin Discipline
Average discount rate and its impact on gross margin. Identify whether discounting is driving volume or just eroding margin without incremental deals.

## KPI Performance
One sentence per KPI in kpi_names: what it measures, what the data shows, and whether it needs immediate attention.

## Data Quality Assessment
Completeness, missing deal or rep fields, and how gaps affect performance ranking and forecasting accuracy.

## Recommended Actions
3–5 numbered steps specific to sales operations — quota setting, coaching priorities, discount governance, territory rebalancing.

## Chart-Level Insights
For each rep, region, product, or time trend visible in the data, one sentence: pattern, anomaly, and action."""


def _prompt_hr(ctx: str, payload: dict) -> str:
    return f"""You are a senior HR analytics consultant producing a client-ready workforce report.

Focus specifically on: headcount health, attrition risk, compensation equity, performance distribution, and hiring pipeline efficiency.

Dataset context (aggregate statistics only — no raw data):
{ctx}
{_RULES}
Use exactly this structure:

## Executive Summary
Lead with the most critical workforce risk — attrition rate, compensation gaps, or headcount imbalance. State the business cost of current attrition and close with the single most important HR action.

## Key Insights
4–5 bullets covering: attrition rate vs benchmark (<15% annually is healthy), compensation spread and equity risk, tenure distribution and institutional knowledge risk, department or role concentration, performance distribution skew. Each: **[Finding]** — business impact + action.

## Attrition & Retention Analysis
Attrition rate, tenure distribution, and which departments or roles are most at risk. Quantify the cost of replacing employees at current attrition levels (typically 50–200% of annual salary per hire).

## Compensation & Equity Analysis
Salary distribution, mean vs median gap, and ranges by department or role. Flag any compression or inversion issues. Identify where compensation is likely driving attrition.

## Performance & Headcount
Performance distribution across departments. Is headcount allocated to highest-value functions? Where is there over or under-investment?

## KPI Performance
One sentence per KPI in kpi_names: what it measures, what the data shows, and whether it needs immediate attention.

## Data Quality Assessment
Completeness, missing salary or performance fields, and how gaps affect equity analysis and attrition modelling.

## Recommended Actions
3–5 numbered steps specific to HR — compensation review, retention programmes, hiring priorities, performance management.

## Chart-Level Insights
For each department, tenure band, or compensation distribution visible in the data, one sentence: pattern, anomaly, and action."""


def _prompt_healthcare(ctx: str, payload: dict) -> str:
    return f"""You are a senior healthcare operations analyst producing a client-ready clinical performance report.

Focus specifically on: appointment efficiency, no-show impact, patient satisfaction, wait time performance, and billing yield.

Dataset context (aggregate statistics only — no raw data):
{ctx}
{_RULES}
Use exactly this structure:

## Executive Summary
Lead with the single most critical operational metric — no-show rate, wait time breach, or satisfaction score. Quantify the revenue and capacity cost of current inefficiencies. Close with the highest-priority operational action.

## Key Insights
4–5 bullets covering: no-show rate vs benchmark (<8% is target), avg wait time vs standard (<15 min), patient satisfaction score, billing yield by insurance type, appointment completion rate. Each: **[Finding]** — business impact + action.

## Capacity & Scheduling Analysis
No-show rate, appointment volume, and completion rate. Calculate daily and annual revenue lost to no-shows. Identify which appointment types or departments have the worst attendance.

## Patient Experience Analysis
Wait time distribution and satisfaction scores. Where is the experience failing? Which departments are driving dissatisfaction and what is the retention risk?

## Billing & Revenue Analysis
Billing amounts by insurance type and appointment category. Identify which payer mix drives the most and least yield. Flag any billing gaps or collection risks.

## KPI Performance
One sentence per KPI in kpi_names: what it measures, what the data shows, and whether it needs immediate attention.

## Data Quality Assessment
Completeness, missing billing or satisfaction fields, and how gaps affect revenue and quality reporting.

## Recommended Actions
3–5 numbered steps specific to clinical operations — no-show reduction, scheduling optimisation, wait time reduction, billing improvement.

## Chart-Level Insights
For each department, appointment type, or time trend visible in the data, one sentence: pattern, anomaly, and action."""


def _prompt_marketing(ctx: str, payload: dict) -> str:
    return f"""You are a senior marketing analytics consultant producing a client-ready campaign performance report.

Focus specifically on: campaign ROI, channel efficiency, conversion performance, audience quality, and budget allocation.

Dataset context (aggregate statistics only — no raw data):
{ctx}
{_RULES}
Use exactly this structure:

## Executive Summary
Lead with overall marketing ROI position and the single biggest efficiency gap — is spend concentrated in underperforming channels? State the revenue impact and close with the highest-priority reallocation action.

## Key Insights
4–5 bullets covering: best and worst performing channels by ROI, conversion rate vs benchmark, cost per acquisition trend, campaign concentration risk, audience engagement signals. Each: **[Finding]** — business impact + action.

## Channel & Campaign Performance
Revenue, conversions, and ROI by channel and campaign. Identify which channels are scaling efficiently and which are producing diminishing returns. Quantify the revenue upside of reallocating budget from worst to best performers.

## Conversion & Funnel Analysis
Conversion rates across stages. Where is the funnel leaking most? What is the revenue cost of each percentage point of conversion lost?

## Audience & Engagement
Audience segments, engagement rates, and quality signals. Which segments convert best and at what cost? Where is budget being wasted on low-intent audiences?

## KPI Performance
One sentence per KPI in kpi_names: what it measures, what the data shows, and whether it needs immediate attention.

## Data Quality Assessment
Completeness, missing attribution or conversion fields, and how gaps affect ROI and channel comparison accuracy.

## Recommended Actions
3–5 numbered steps specific to marketing operations — budget reallocation, channel optimisation, creative testing, audience refinement.

## Chart-Level Insights
For each channel, campaign, or conversion trend visible in the data, one sentence: pattern, anomaly, and action."""


def _prompt_retail(ctx: str, payload: dict) -> str:
    return f"""You are a senior retail and inventory analyst producing a client-ready operations report.

Focus specifically on: inventory health, stock turnover, margin performance, supplier concentration, and demand forecasting signals.

Dataset context (aggregate statistics only — no raw data):
{ctx}
{_RULES}
Use exactly this structure:

## Executive Summary
Lead with the most critical inventory or margin risk — stockout exposure, overstock cost, or turnover underperformance. Quantify the working capital impact. Close with the single highest-priority inventory action.

## Key Insights
4–5 bullets covering: stock turnover rate vs benchmark, stockout and overstock exposure, margin by category, supplier concentration risk, days of supply. Each: **[Finding]** — business impact + action.

## Inventory Health Analysis
Stock levels, turnover rates, and days of supply by category or SKU. Identify which categories are tying up capital in slow-moving stock and which are at stockout risk.

## Margin & Pricing Analysis
Margin distribution by category and supplier. Where is margin being compressed? Which categories or suppliers offer the best return on inventory investment?

## Supplier & Category Risk
Supplier concentration and category mix. Where is the business exposed to single-supplier risk? What assortment changes would improve resilience and margin?

## KPI Performance
One sentence per KPI in kpi_names: what it measures, what the data shows, and whether it needs immediate attention.

## Data Quality Assessment
Completeness, missing cost or stock fields, and how gaps affect turnover and margin calculations.

## Recommended Actions
3–5 numbered steps specific to retail operations — reorder point adjustment, supplier diversification, markdown strategy, category rationalisation.

## Chart-Level Insights
For each category, stock level, or turnover trend visible in the data, one sentence: pattern, anomaly, and action."""


def _prompt_general(ctx: str, payload: dict) -> str:
    return f"""You are a senior data analyst and business consultant producing a client-ready analytics report identical in quality to a top consulting firm deliverable.

Dataset context (aggregate statistics only — no raw data):
{ctx}
{_RULES}
Use exactly this structure:

## Executive Summary
3–4 sentences. Lead with the single most important finding. Communicate what matters most for decision-making. Close with the highest-priority action.

## Key Insights
4–5 bullet points. Each: **[Finding]** — why it matters and what to do. Focus on risks, opportunities, and anomalies.

## Business Insights
Minimum 3 insights as business narratives. Reference actual column names, top values, and numeric summaries. Explain commercial impact and the decision each pattern should drive.

## KPI Performance
One sentence per KPI in kpi_names: what it measures, what the data shows, and whether it needs immediate attention.

## Data Quality Assessment
Completeness rate, missing-value columns, duplicate rows. State directly if any issue could affect business decisions.

## Recommended Actions
3–5 numbered steps. Each specific enough to assign to a person. Prioritise by business impact.

## Assumptions & Limitations
One short paragraph. What cannot be determined from aggregate stats alone and what additional data would help.

## Chart-Level Insights
For each major column or time dimension in the data, one sentence: trend or distribution in plain business language and the action it suggests."""


_DOMAIN_PROMPTS = {
    "real_estate":  _prompt_real_estate,
    "hospitality":  _prompt_hospitality,
    "saas":         _prompt_saas,
    "ecommerce":    _prompt_ecommerce,
    "sales":        _prompt_sales,
    "hr":           _prompt_hr,
    "healthcare":   _prompt_healthcare,
    "marketing":    _prompt_marketing,
    "retail":       _prompt_retail,
    "finance":      _prompt_general,
    "general":      _prompt_general,
}


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
