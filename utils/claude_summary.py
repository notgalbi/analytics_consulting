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
_MAX_TOKENS = 6000


# ── Public functions ──────────────────────────────────────────────────────────

def build_safe_summary_payload(
    profile: dict,
    domain: str,
    kpis: list[dict],
    pii_report: dict,
    calc_kpis: dict | None = None,
) -> dict:
    """
    Construct a payload from safe aggregate data only.
    Nothing here contains raw rows or PII values.
    """
    payload = {
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
    if calc_kpis:
        payload["calculated_kpis"] = calc_kpis
    return payload


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
- Avoid passive language — every sentence must have a clear subject taking a clear action
- Every insight must answer two questions: "Why does this matter?" and "What should be done?"
- Quantify business impact wherever possible — revenue loss, efficiency gap, cost exposure
- Write in a confident, decisive, executive tone — the reader is a non-technical decision-maker paying for this insight
- Only reference numbers that exist in the dataset context above — do not invent figures
- Keep each section tight and direct — no filler sentences
- End every report with a Callout Insights section (3 single-sentence statements: one on revenue loss or opportunity, one on an operational efficiency gap, one on customer/client experience risk)
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
## Callout Insights
Write exactly 3 single-sentence statements — punchy, specific, and strong enough to use as report preview bullets or marketing copy:
- Revenue: one sentence on revenue loss or revenue opportunity (include a dollar figure or percentage if the data supports it)
- Efficiency: one sentence on the most critical operational efficiency gap
- Experience: one sentence on customer, patient, or client experience risk
"""


# ── Few-shot style examples ───────────────────────────────────────────────────
# Each entry shows two high-quality examples per domain:
#   "insight" — a strong Key Insight bullet in the expected format
#   "exec"    — a strong Executive Summary opening sentence
# These anchor Claude to the consulting quality and language expected.
# Style drawn from McKinsey, Bain, Gartner, and KPMG advisory report conventions.

_FEW_SHOT_EXAMPLES: dict[str, dict[str, str]] = {
    "healthcare": {
        "insight": (
            "**[No-Show Rate 13.7% — $23K Revenue at Risk]** — At 5.7 percentage points above "
            "the 8% MGMA benchmark, 82 billable slots per period go unbilled with no opportunity "
            "to backfill. Implementing a 48-hour SMS confirmation with one-click cancellation "
            "reduces no-shows 30–40% within 90 days in comparable practices (MGMA 2023); "
            "assign the front-desk coordinator to pilot this by end of quarter."
        ),
        "exec": (
            "With a completion rate of 69% — 21 points below the 90% HFMA benchmark — this "
            "practice is leaving $35K in billable appointment revenue uncaptured each period "
            "while simultaneously running a 13.7% no-show rate that compounds the revenue gap; "
            "the highest-priority action is a same-day cancellation and waitlist protocol that "
            "converts empty slots into revenue before the appointment window closes."
        ),
    },
    "saas": {
        "insight": (
            "**[Churn Rate 19.5% — MRR Base Eroding at 4× Benchmark Rate]** — Monthly churn "
            "nearly 10× the 2% Bessemer Cloud Index benchmark means the customer base turns over "
            "completely in approximately 5 months, making sustainable ARR growth structurally "
            "impossible without simultaneous churn intervention. Deploy an in-app health score "
            "tracking login frequency and feature adoption depth; flag accounts below threshold "
            "for proactive CSM outreach within the first 30 days post-signup."
        ),
        "exec": (
            "A monthly churn rate of 19.5% is eroding MRR faster than new customer acquisition "
            "can replace it — at current rates, every $100K in new MRR booked is offset by $195K "
            "in contracted revenue lost; reducing churn to the 5% SaaS watch-zone threshold must "
            "be treated as a higher priority than growth investment this quarter."
        ),
    },
    "marketing": {
        "insight": (
            "**[ROAS 4.61x — Sitting Just Above Profitability Threshold with 30% Efficiency Gap]** "
            "— ROAS is above the 4x break-even but well below the 6x top-quartile benchmark "
            "(WordStream 2024), indicating the current channel mix is generating revenue at above "
            "cost but leaving meaningful efficiency on the table. Reallocating 25% of budget from "
            "the lowest-ROAS channel to the highest performer typically improves blended ROAS "
            "15–20% within one billing cycle without increasing total spend."
        ),
        "exec": (
            "The campaign portfolio is generating positive ROAS at 4.61x but operating "
            "inefficiently — the spread between best and worst performing channels represents "
            "a budget reallocation opportunity estimated at 15–20% revenue improvement at "
            "identical spend levels; the single highest-impact action is a channel audit and "
            "budget shift this month before the next campaign planning cycle."
        ),
    },
    "ecommerce": {
        "insight": (
            "**[Avg Days to Ship 4.0 — Fulfilment Gap Driving Repeat Purchase Attrition]** "
            "— Delivery time 1 day above the 3-day customer expectation threshold set by "
            "Amazon Prime is the most actionable lever for repeat purchase rate; Shopify Merchant "
            "data (2024) shows repeat purchase rate increases 15–20% when delivery time drops "
            "from 4 to 2 days. Negotiate a next-day handoff SLA with the fulfilment partner "
            "for orders placed before 2 PM, targeting a 2-day average within 30 days."
        ),
        "exec": (
            "Revenue growth of +12.8% MoM is strong, but a 4-day average shipping time "
            "is quietly suppressing repeat purchase rate — the most capital-efficient growth "
            "lever available — and a return rate approaching the 10% amber threshold indicates "
            "product-description or sizing accuracy issues that, if uncorrected, will compound "
            "as volume scales; both gaps have identified fixes with 30-day implementation timelines."
        ),
    },
    "retail": {
        "insight": (
            "**[Stockout Rate 10% — Double the NRF 5% Target, Demand Being Lost to Competitors]** "
            "— 1 in 10 SKUs is at or below reorder point, meaning the business is turning away "
            "demand in its highest-velocity lines; NRF data shows each percentage point of "
            "stockout costs approximately 1–2% of annual revenue in missed sales. Prioritise "
            "emergency replenishment for the 15 highest-velocity SKUs currently below reorder "
            "point and adjust safety stock thresholds for the top 20% of SKUs by units sold."
        ),
        "exec": (
            "A stockout rate of 10% and inventory turnover of 0.19x per month signals the "
            "business has both a supply gap in fast-moving lines and a working capital trap in "
            "slow-moving stock — the dual fix is tighter reorder triggers on velocity leaders "
            "and a structured markdown programme for the bottom 20% by days-in-stock, which "
            "together can recover 3–5% of annual revenue within one planning cycle."
        ),
    },
    "hr": {
        "insight": (
            "**[Attrition Rate X% — Replacement Cost Exposure $1.75M+ Annually]** — At SHRM's "
            "replacement cost estimate of 1.5–2× annual salary per departing employee, current "
            "attrition represents a material and recurring expense that is largely invisible in "
            "the P&L because it flows through recruiting, onboarding, and lost productivity line "
            "items. Exit interview data segmented by department and tenure band will identify "
            "whether the driver is compensation compression, management quality, or role fit."
        ),
        "exec": (
            "Attrition is the primary financial risk in this workforce dataset — each percentage "
            "point of turnover above the 10% SHRM benchmark translates directly to replacement "
            "costs exceeding $100K per point at median salary levels; the immediate priority is "
            "identifying the two or three departments driving disproportionate attrition and "
            "intervening with targeted retention programmes before the talent gap widens further."
        ),
    },
    "real_estate": {
        "insight": (
            "**[Avg Days on Market 43 Days — 13 Days Above NAR Median, Pricing or Presentation Gap]** "
            "— Properties sitting 43 days on average — vs the 2024 NAR national median of 30 days "
            "— indicate that listings are either priced above comparable market demand or lack "
            "the presentation quality to compete. A pricing review on the 10 longest-sitting "
            "listings (targeting within 2% of current comps) combined with professional staging "
            "reduces time-to-sale 20–25% in comparable markets and improves list-to-sale ratio."
        ),
        "exec": (
            "Listings averaging 43 days on market and a sale rate below the 85% NAR benchmark "
            "signal a pipeline and pricing alignment issue — the portfolio is generating listings "
            "but not closing them at the rate needed to sustain volume targets; a structured "
            "pricing review on stale listings and a buyer pipeline audit by agent would identify "
            "whether this is a demand, pricing, or conversion quality problem within two weeks."
        ),
    },
    "hospitality": {
        "insight": (
            "**[Prime Cost X% — Above 65% NRA Benchmark, Margin Structurally at Risk]** "
            "— Prime cost above 65% means food and labor alone are consuming more than two-thirds "
            "of every revenue dollar, leaving insufficient margin to cover occupancy, utilities, "
            "and debt service at current volume. Menu engineering — eliminating the 20% of dishes "
            "with the worst combined margin-and-velocity score — typically reduces food cost 2–3 "
            "percentage points within one menu cycle without reducing cover satisfaction scores."
        ),
        "exec": (
            "The operation faces a prime cost structure that is financially unsustainable at "
            "current revenue levels — with food and labor costs consuming the majority of each "
            "revenue dollar before fixed costs, the path to profitability runs through cost "
            "reduction rather than volume growth; the three highest-leverage interventions are "
            "menu rationalisation, scheduling optimisation, and a reservation deposit policy "
            "to eliminate the no-show revenue drain."
        ),
    },
    "operations": {
        "insight": (
            "**[Avg Resolution Time 81 hrs — 69% Above 48-hr HDI Benchmark, CSAT at Risk]** "
            "— Customers waiting 3.4 days on average for ticket resolution are experiencing a "
            "service level that Zendesk CX Trends (2024) correlates with a 15–20% increase "
            "in churn probability at next renewal. Each 10-hour reduction in mean resolution "
            "time is associated with a 3–5% CSAT improvement; routing optimisation to match "
            "ticket type to specialist skill set is the fastest lever to close the gap."
        ),
        "exec": (
            "With average resolution time at 81 hours — nearly double the 48-hour HDI benchmark "
            "— and a meaningful backlog of open tickets, the operations team is operating in a "
            "reactive capacity-constrained mode that is eroding customer satisfaction scores and "
            "increasing renewal risk; the first intervention must be triaging the open backlog "
            "by severity and age, then addressing the routing and skill-gap issues driving the "
            "resolution time overage."
        ),
    },
    "sales": {
        "insight": (
            "**[Revenue Declining 59% MoM — Pipeline Collapse or Seasonality Requires Diagnosis]** "
            "— A single-period revenue decline of this magnitude — unless fully attributable to "
            "known seasonality — signals either a pipeline failure from 60–90 days prior, a "
            "loss of a major account, or a pricing or competitive event that closed deals are "
            "not yet reflecting. The first action is a deal-by-deal review of every opportunity "
            "in the pipeline from that period to identify whether the issue is conversion rate, "
            "average deal size, or sales cycle compression."
        ),
        "exec": (
            "Revenue is declining at a rate that cannot be absorbed by the current business model "
            "without structural intervention — with average discount already at 20% consuming margin "
            "headroom, the path to recovery requires simultaneous pipeline acceleration and discount "
            "discipline, not one or the other; the two highest-priority actions are a full pipeline "
            "audit and a 15% discount threshold requiring manager approval for any exceptions."
        ),
    },
    "finance": {
        "insight": (
            "**[Net Margin X% — Below D&B 5–15% Industry Range, Cost Structure Review Required]** "
            "— A margin below the Dun & Bradstreet industry median indicates the current cost "
            "structure is consuming an above-market share of revenue, which compounds over time "
            "as revenue growth fails to outpace fixed cost inflation. The highest-leverage "
            "intervention is a line-by-line variance analysis between actual spend and the "
            "budget plan to identify the two or three cost lines driving the margin underperformance."
        ),
        "exec": (
            "The financial picture shows a margin structure that is below industry benchmarks, "
            "creating structural fragility — any revenue softness or cost increase at current "
            "margins moves the business from thin profitability to loss; the priority is not "
            "top-line growth but cost-line discipline, with a named owner and monthly accountability "
            "for the three largest variance line items in the budget."
        ),
    },
    "general": {
        "insight": (
            "**[High-Variance Column Identified — Revenue or Efficiency Impact Requires Segmentation]** "
            "— Columns with coefficient of variation above 100% typically contain the business's "
            "most important performance signals, as the spread between best and worst performers "
            "represents the gap between current and potential performance. Segment the "
            "highest-variance column by the primary categorical dimension to identify which "
            "sub-group is driving the extremes and whether intervention or scaling is the "
            "appropriate response."
        ),
        "exec": (
            "The dataset contains meaningful performance variation that aggregate averages are "
            "masking — the business's most impactful decisions will come from understanding what "
            "drives the difference between top and bottom performers, not from optimising the mean; "
            "the first priority is identifying the two or three variables most correlated with "
            "outcome variance and assigning accountable owners to close the gap."
        ),
    },
}


def _few_shot_block(domain: str) -> str:
    """Return a formatted few-shot style guide block for the given domain."""
    ex = _FEW_SHOT_EXAMPLES.get(domain, _FEW_SHOT_EXAMPLES["general"])
    return f"""
STYLE EXAMPLES — match this quality, specificity, and tone in your output:

Key Insight example:
{ex['insight']}

Executive Summary opening example:
{ex['exec']}

Apply this standard throughout: lead with the number, name the benchmark and source, quantify the business impact, give a specific action with a timeframe. Never write a finding without all four elements.
"""


# ── Domain-specific prompts ───────────────────────────────────────────────────

def _prompt_real_estate(ctx: str, payload: dict) -> str:
    return f"""You are a senior real estate data analyst and business consultant producing a high-value, client-ready market report.

Focus specifically on: market performance, pricing dynamics, listing efficiency, and agent/property segmentation.

Dataset context (aggregate statistics only — no raw data):
{ctx}
{_RULES}
{_few_shot_block("real_estate")}
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
For each distribution or time trend visible in the data, one sentence: what pattern exists, what anomaly stands out, and what action it suggests.

## Callout Insights
Write exactly 3 single-sentence statements — punchy, specific, and strong enough to use as report preview bullets or marketing copy:
- Revenue: one sentence on revenue loss or revenue opportunity (include a dollar figure or percentage if the data supports it)
- Efficiency: one sentence on the most critical operational efficiency gap
- Experience: one sentence on customer, patient, or client experience risk
"""


def _prompt_hospitality(ctx: str, payload: dict) -> str:
    return f"""You are a senior hospitality and restaurant business consultant producing a client-ready operations report.

Focus specifically on: revenue performance, cost control (food cost, labor cost, prime cost), cover volume, and reservation efficiency.

Dataset context (aggregate statistics only — no raw data):
{ctx}
{_RULES}
{_few_shot_block("hospitality")}
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
For each day-of-week, cost trend, or revenue distribution visible in the data, one sentence: pattern, anomaly, and action.

## Callout Insights
Write exactly 3 single-sentence statements — punchy, specific, and strong enough to use as report preview bullets or marketing copy:
- Revenue: one sentence on revenue loss or revenue opportunity (include a dollar figure or percentage if the data supports it)
- Efficiency: one sentence on the most critical operational efficiency gap
- Experience: one sentence on customer, patient, or client experience risk
"""


def _prompt_saas(ctx: str, payload: dict) -> str:
    return f"""You are a senior SaaS business analyst and growth consultant producing a client-ready metrics report.

Focus specifically on: revenue health (MRR, churn, LTV), growth trajectory, customer retention, and expansion opportunity.

Dataset context (aggregate statistics only — no raw data):
{ctx}
{_RULES}
{_few_shot_block("saas")}
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
For each plan distribution, churn trend, or MRR movement visible in the data, one sentence: pattern, anomaly, and action.

## Callout Insights
Write exactly 3 single-sentence statements — punchy, specific, and strong enough to use as report preview bullets or marketing copy:
- Revenue: one sentence on revenue loss or revenue opportunity (include a dollar figure or percentage if the data supports it)
- Efficiency: one sentence on the most critical operational efficiency gap
- Experience: one sentence on customer, patient, or client experience risk
"""


def _prompt_ecommerce(ctx: str, payload: dict) -> str:
    return f"""You are a senior ecommerce and retail analyst producing a client-ready performance report.

Focus specifically on: revenue performance, conversion and return rates, product and category mix, discount impact, and fulfilment efficiency.

Dataset context (aggregate statistics only — no raw data):
{ctx}
{_RULES}
{_few_shot_block("ecommerce")}
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
For each category distribution, return trend, or revenue pattern visible in the data, one sentence: pattern, anomaly, and action.

## Callout Insights
Write exactly 3 single-sentence statements — punchy, specific, and strong enough to use as report preview bullets or marketing copy:
- Revenue: one sentence on revenue loss or revenue opportunity (include a dollar figure or percentage if the data supports it)
- Efficiency: one sentence on the most critical operational efficiency gap
- Experience: one sentence on customer, patient, or client experience risk
"""


def _prompt_sales(ctx: str, payload: dict) -> str:
    return f"""You are a senior sales performance analyst and revenue consultant producing a client-ready sales report.

Focus specifically on: revenue attainment, pipeline velocity, rep performance, product mix, and discount discipline.

Dataset context (aggregate statistics only — no raw data):
{ctx}
{_RULES}
{_few_shot_block("sales")}
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
For each rep, region, product, or time trend visible in the data, one sentence: pattern, anomaly, and action.

## Callout Insights
Write exactly 3 single-sentence statements — punchy, specific, and strong enough to use as report preview bullets or marketing copy:
- Revenue: one sentence on revenue loss or revenue opportunity (include a dollar figure or percentage if the data supports it)
- Efficiency: one sentence on the most critical operational efficiency gap
- Experience: one sentence on customer, patient, or client experience risk
"""


def _prompt_hr(ctx: str, payload: dict) -> str:
    return f"""You are a senior HR analytics consultant producing a client-ready workforce report.

Focus specifically on: headcount health, attrition risk, compensation equity, performance distribution, and hiring pipeline efficiency.

Dataset context (aggregate statistics only — no raw data):
{ctx}
{_RULES}
{_few_shot_block("hr")}
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
For each department, tenure band, or compensation distribution visible in the data, one sentence: pattern, anomaly, and action.

## Callout Insights
Write exactly 3 single-sentence statements — punchy, specific, and strong enough to use as report preview bullets or marketing copy:
- Revenue: one sentence on revenue loss or revenue opportunity (include a dollar figure or percentage if the data supports it)
- Efficiency: one sentence on the most critical operational efficiency gap
- Experience: one sentence on customer, patient, or client experience risk
"""


def _prompt_healthcare(ctx: str, payload: dict) -> str:
    return f"""You are a senior healthcare operations analyst producing a client-ready clinical performance report.

Focus specifically on: appointment efficiency, no-show impact, patient satisfaction, wait time performance, and billing yield.

Dataset context (aggregate statistics only — no raw data):
{ctx}
{_RULES}
{_few_shot_block("healthcare")}
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
For each department, appointment type, or time trend visible in the data, one sentence: pattern, anomaly, and action.

## Callout Insights
Write exactly 3 single-sentence statements — punchy, specific, and strong enough to use as report preview bullets or marketing copy:
- Revenue: one sentence on revenue loss or revenue opportunity (include a dollar figure or percentage if the data supports it)
- Efficiency: one sentence on the most critical operational efficiency gap
- Experience: one sentence on customer, patient, or client experience risk
"""


def _prompt_marketing(ctx: str, payload: dict) -> str:
    return f"""You are a senior marketing analytics consultant producing a client-ready campaign performance report.

Focus specifically on: campaign ROI, channel efficiency, conversion performance, audience quality, and budget allocation.

Dataset context (aggregate statistics only — no raw data):
{ctx}
{_RULES}
{_few_shot_block("marketing")}
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
For each channel, campaign, or conversion trend visible in the data, one sentence: pattern, anomaly, and action.

## Callout Insights
Write exactly 3 single-sentence statements — punchy, specific, and strong enough to use as report preview bullets or marketing copy:
- Revenue: one sentence on revenue loss or revenue opportunity (include a dollar figure or percentage if the data supports it)
- Efficiency: one sentence on the most critical operational efficiency gap
- Experience: one sentence on customer, patient, or client experience risk
"""


def _prompt_retail(ctx: str, payload: dict) -> str:
    return f"""You are a senior retail and inventory analyst producing a client-ready operations report.

Focus specifically on: inventory health, stock turnover, margin performance, supplier concentration, and demand forecasting signals.

Dataset context (aggregate statistics only — no raw data):
{ctx}
{_RULES}
{_few_shot_block("retail")}
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
For each category, stock level, or turnover trend visible in the data, one sentence: pattern, anomaly, and action.

## Callout Insights
Write exactly 3 single-sentence statements — punchy, specific, and strong enough to use as report preview bullets or marketing copy:
- Revenue: one sentence on revenue loss or revenue opportunity (include a dollar figure or percentage if the data supports it)
- Efficiency: one sentence on the most critical operational efficiency gap
- Experience: one sentence on customer, patient, or client experience risk
"""


def _prompt_general(ctx: str, payload: dict) -> str:
    return f"""You are a senior data analyst and business consultant producing a client-ready analytics report identical in quality to a top consulting firm deliverable.

Dataset context (aggregate statistics only — no raw data):
{ctx}
{_RULES}
{_few_shot_block("general")}
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
For each major column or time dimension in the data, one sentence: trend or distribution in plain business language and the action it suggests.

## Callout Insights
Write exactly 3 single-sentence statements — punchy, specific, and strong enough to use as report preview bullets or marketing copy:
- Revenue: one sentence on revenue loss or revenue opportunity (include a dollar figure or percentage if the data supports it)
- Efficiency: one sentence on the most critical operational efficiency gap
- Experience: one sentence on customer, patient, or client experience risk
"""


def _prompt_operations(ctx: str, payload: dict) -> str:
    return f"""You are a senior operations and service delivery analyst producing a client-ready performance report.

Focus specifically on: ticket volume and backlog health, response and resolution time, SLA compliance, team efficiency, and customer satisfaction risk.

Dataset context (aggregate statistics only — no raw data):
{ctx}
{_RULES}
{_few_shot_block("operations")}
Use exactly this structure:

## Executive Summary
Lead with the most critical service metric — resolution time breach, backlog size, or SLA compliance rate. Quantify the customer satisfaction and retention risk from current performance. Close with the single highest-priority operational action.

## Key Insights
4–5 bullets covering: resolution time vs benchmark (<48 hrs HDI target), response time SLA compliance, open backlog exposure, resolution rate, and ticket volume trend. Each: **[Finding]** — business impact + action.

## Volume & Backlog Analysis
Total ticket volume, open backlog size, and trend. Is the team keeping up with inflow or is the backlog growing? Quantify how many days at current resolution rate it would take to clear the backlog.

## Response & Resolution Performance
Average response time vs SLA target. Average resolution time vs benchmark. Identify the ticket categories or time periods with the worst performance and what is driving each gap.

## Team Efficiency & Routing
Resolution rate and first-contact resolution signals. Are tickets being routed to the right skill set? Where is rework or escalation creating capacity drag?

## KPI Performance
One sentence per KPI in kpi_names: what it measures, what the data shows, and whether it needs immediate attention.

## Data Quality Assessment
Completeness, missing resolution time or status fields, and how gaps affect SLA and CSAT analysis.

## Recommended Actions
3–5 numbered steps specific to operations — SLA rule configuration, routing optimisation, specialist skill-gap training, backlog triage, tooling improvement.

## Chart-Level Insights
For each status distribution, resolution time trend, or volume pattern visible in the data, one sentence: pattern, anomaly, and action.

## Callout Insights
Write exactly 3 single-sentence statements — punchy, specific, and strong enough to use as report preview bullets or marketing copy:
- Revenue: one sentence on revenue loss or revenue opportunity (include a dollar figure or percentage if the data supports it)
- Efficiency: one sentence on the most critical operational efficiency gap
- Experience: one sentence on customer, patient, or client experience risk
"""


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
    "operations":   _prompt_operations,
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
    ex = _FEW_SHOT_EXAMPLES.get(domain, _FEW_SHOT_EXAMPLES["general"])
    prompt = f"""You are a senior business consultant interpreting KPI results for a {domain} business. Your analysis will appear in a client-facing report.

Calculated KPIs from {profile.get('row_count', 0):,} records:
{kpi_lines}

Style example — match this quality and tone:
"{ex['exec']}"

Write 4–5 sentences of executive-quality analysis:
- Open by naming the standout metric — is it a strength or a warning sign?
- Compare to the specific industry benchmark and name the source (e.g. MGMA, Bessemer, NRF, SHRM)
- Quantify the business impact in dollars or percentage points where the data supports it
- Identify the metric demanding immediate management attention and explain the consequence of inaction
- Close with the single highest-priority action the business should take this quarter

Rules: flowing prose only, no bullet points, no "Here is" or "Based on" opener. Be direct, specific, and confident. Never use "further analysis is needed" or "it appears that"."""

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
