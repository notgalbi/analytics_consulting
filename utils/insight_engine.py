"""
insight_engine.py — Structured insight generation from analyzed data.

Combines KPI results, financial impact, and operational impact into
executive-ready insights that answer: what happened, why it matters,
what the business impact is, what the financial impact is, and what
leadership should do next.

Public API:
    generate_insights(domain, calc_kpis, profile, financial_impact, operational_impact) -> list[Insight]
"""
from __future__ import annotations

from dataclasses import dataclass, field

from utils.financial_impact_engine import FinancialImpact
from utils.operational_impact_engine import OperationalImpact


@dataclass
class Insight:
    title: str
    priority: str           # "High" | "Medium" | "Low"
    category: str           # "Revenue" | "Cost" | "Risk" | "Efficiency" | "Customer Experience" | "Growth" | "Operations" | "Data Quality"
    finding: str            # What happened — specific, data-driven
    so_what: str            # Why it matters to the business
    business_impact: str    # Qualitative business consequence
    financial_impact: str   # Dollar amount or "Not quantified"
    recommended_action: str # Specific, time-bound action
    expected_outcome: str   # What success looks like
    confidence_score: float # 0.0–1.0
    supporting_evidence: list[str] = field(default_factory=list)
    evidence_type: str = ""  # "OBSERVED" | "INFERRED" | "BENCHMARK" | "HYPOTHESIS"


# ── Public function ───────────────────────────────────────────────────────────

def generate_insights(
    domain: str,
    calc_kpis: dict[str, str],
    profile: dict,
    financial_impact: FinancialImpact,
    operational_impact: OperationalImpact,
) -> list[Insight]:
    """
    Generate structured insights from all analyzed data.
    Returns at most 7 insights, sorted High → Medium → Low priority.
    """
    insights: list[Insight] = []

    # KPIs covered by financial findings that will actually become insights (quantified OR High priority).
    # Medium-priority unquantified findings don't block operational insights — they won't become insights either.
    fin_kpi_coverage: set[str] = {
        f.source_kpi for f in financial_impact.findings
        if f.source_kpi and ((f.amount is not None and f.amount > 0) or f.priority == "High")
    }

    # 1. Financial impact findings → insights
    for f in financial_impact.findings:
        if f.amount is not None and f.amount > 0:
            cat = "Revenue" if "Risk" in f.category else ("Cost" if "Savings" in f.category else "Growth")
            insights.append(Insight(
                title=f.title,
                priority=f.priority,
                category=cat,
                finding=f.description,
                so_what=f"This finding has a direct, quantifiable impact on {cat.lower()} performance.",
                business_impact=f"Directly affects the bottom line. {f.description[:120]}",
                financial_impact=f.amount_formatted,
                recommended_action=_financial_action(domain, f.category, f.title),
                expected_outcome=f"Recovering {f.amount_formatted} in {f.category.lower()} within 90 days if actioned immediately.",
                confidence_score=f.confidence,
                supporting_evidence=[f"KPI analysis: {f.assumption}"],
            ))
        elif f.priority == "High":
            # Include high-priority non-quantified findings
            insights.append(Insight(
                title=f.title,
                priority="High",
                category="Risk",
                finding=f.description,
                so_what="This issue carries material business risk even without a precise dollar estimate.",
                business_impact=f.description,
                financial_impact="Not quantified — requires additional data",
                recommended_action=_financial_action(domain, f.category, f.title),
                expected_outcome="Risk mitigation and improved operational health within 60 days.",
                confidence_score=f.confidence,
                supporting_evidence=[f.assumption],
            ))

    # 2. Operational impact findings → insights (High + Medium)
    ops_kpi_coverage: set[str] = set()
    for op in operational_impact.findings:
        if op.severity in ("High", "Medium"):
            # Skip if financial engine already quantified this same KPI
            if op.metric_name and op.metric_name in fin_kpi_coverage:
                continue
            cat = _ops_category(op.category)
            priority = "High" if op.severity == "High" else "Medium"
            if op.metric_name:
                ops_kpi_coverage.add(op.metric_name)
            insights.append(Insight(
                title=op.title,
                priority=priority,
                category=cat,
                finding=op.finding,
                so_what=op.impact,
                business_impact=op.impact,
                financial_impact="Not quantified",
                recommended_action=op.recommendation,
                expected_outcome=f"Resolved {op.title.lower()} with measurable improvement within 30-60 days.",
                confidence_score=0.75,
                supporting_evidence=[
                    f"{op.metric_name}: {op.metric_value}" if op.metric_name else "Operational metrics analysis",
                    f"Benchmark: {op.benchmark}" if op.benchmark else "",
                ],
            ))

    # 3. KPI benchmark violations not already captured
    violations = _find_benchmark_violations(domain, calc_kpis)
    seen_titles = {i.title for i in insights}
    all_kpi_coverage = fin_kpi_coverage | ops_kpi_coverage
    for v in violations:
        if v["name"] not in seen_titles and v["name"] not in all_kpi_coverage and len(insights) < 7:
            direction = v.get("direction", "higher")
            if direction == "lower":
                perf_label = "Exceeds Benchmark"
                finding_text = (
                    f"{v['name']} is {v['value']}, which exceeds the industry benchmark — "
                    f"higher values mean worse performance here. {v['note']}"
                )
            else:
                perf_label = "Below Benchmark"
                finding_text = (
                    f"{v['name']} is {v['value']}, which is below the industry benchmark. {v['note']}"
                )
            insights.append(Insight(
                title=f"{v['name']} {perf_label}",
                priority="Medium" if v["severity"] == "medium" else "High",
                category=_kpi_category(domain, v["name"]),
                finding=finding_text,
                so_what=f"Benchmark violations in {v['name']} indicate underperformance relative to peers and acceptable operating standards.",
                business_impact=f"Continued underperformance in {v['name']} will compound over time into larger operational and financial gaps.",
                financial_impact="Not quantified",
                recommended_action=_benchmark_action(domain, v["name"]),
                expected_outcome=f"{v['name']} improved to benchmark level within one business quarter.",
                confidence_score=0.7,
                supporting_evidence=[f"Current value: {v['value']}", v["note"]],
            ))

    # 4. Data quality insights
    completeness = profile.get("completeness_pct", 100)
    if completeness < 80:
        insights.append(Insight(
            title=f"Data Completeness at {completeness:.0f}%",
            priority="Medium",
            category="Data Quality",
            finding=f"Dataset completeness is {completeness:.0f}%, meaning {100 - completeness:.0f}% of data cells contain missing values.",
            so_what="Missing data reduces the confidence of every KPI, insight, and recommendation in this report.",
            business_impact="Decisions made on incomplete data carry higher risk of being directionally wrong.",
            financial_impact="Not quantified — depends on which fields are missing",
            recommended_action="Identify the columns with highest missing rates and trace back to the data capture process to resolve at source.",
            expected_outcome="Data completeness above 98% within 60 days, improving report confidence scores.",
            confidence_score=0.9,
            supporting_evidence=[f"Overall completeness: {completeness:.1f}%"],
        ))

    validation_warnings = profile.get("validation_warnings", [])
    high_warnings = [w for w in validation_warnings if w.get("severity") == "high"]
    if high_warnings and len(insights) < 7:
        w = high_warnings[0]
        insights.append(Insight(
            title=f"Data Validation Issue: {w.get('column', 'Unknown')}",
            priority="High",
            category="Data Quality",
            finding=f"{w.get('issue', 'Validation error')} in column '{w.get('column')}': {w.get('detail', '')}",
            so_what="Data validation errors in key columns can silently corrupt KPI calculations and lead to incorrect business decisions.",
            business_impact=f"Column '{w.get('column')}' may be producing unreliable values that propagate into multiple downstream metrics.",
            financial_impact="Not quantified",
            recommended_action=f"Investigate data entry and transformation logic for column '{w.get('column')}' and correct upstream before re-running analysis.",
            expected_outcome="Clean, validated data in affected columns; recalculated KPIs with higher confidence scores.",
            confidence_score=0.85,
            supporting_evidence=[f"Column: {w.get('column')}", f"Issue: {w.get('issue')}", f"Detail: {w.get('detail', '')}"],
        ))

    # Classify evidence type for each insight
    from utils.evidence_classifier import classify_evidence
    for ins in insights:
        ins.evidence_type = classify_evidence(ins, calc_kpis, financial_impact)

    # Sort: High first, then Medium, then Low; cap at 7
    priority_order = {"High": 0, "Medium": 1, "Low": 2}
    insights.sort(key=lambda i: priority_order.get(i.priority, 3))
    return insights[:7]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_kpi(value: str) -> float | None:
    if not isinstance(value, str):
        return None
    v = value.strip()
    if v.startswith("$"):
        v = v[1:]
    for unit in ["/ 5", " days", " hrs", " min", " yrs", " mo"]:
        v = v.replace(unit, "")
    v = v.replace("%", "").replace("x", "").replace(",", "").strip().lstrip("+")
    if v.upper().endswith("K"):
        try:
            return float(v[:-1]) * 1_000
        except ValueError:
            return None
    if v.upper().endswith("M"):
        try:
            return float(v[:-1]) * 1_000_000
        except ValueError:
            return None
    try:
        return float(v)
    except ValueError:
        return None


# Each benchmark entry: (threshold, direction, source_note)
# direction "higher" = higher is better; "lower" = lower is better.
# source_note is appended to the insight's supporting evidence.
_BENCHMARKS: dict[str, dict[str, tuple]] = {
    "healthcare": {
        "No-Show Rate":         (8,    "lower",  "MGMA 2024: >8% no-show rate = actionable scheduling and revenue integrity issue"),
        "Avg Wait Time":        (15,   "lower",  "AHRQ: >15 min average wait = patient satisfaction and abandonment risk"),
        "Patient Satisfaction": (4.0,  "higher", "CMS HCAHPS: <4.0/5 = patient non-return risk; top quartile practices score >4.5"),
        "Completion Rate":      (90,   "higher", "HFMA 2024: <90% completion rate = unbilled appointment revenue gap"),
    },
    "marketing": {
        "ROAS":            (4.0,  "higher", "Google/Meta 2024: <4x ROAS is unprofitable for most margin profiles; top campaigns >6x"),
        "CTR":             (2.0,  "higher", "WordStream 2024: industry avg CTR 2–5%; <2% = ad creative or targeting issue"),
        "Conversion Rate": (3.0,  "higher", "HubSpot 2024: top quartile >5%; avg 2–5%; <3% = landing page or offer gap"),
        "CPC":             (8.0,  "lower",  "WordStream 2024: avg CPC $2–4 (Google Search); >$8 = inefficient paid traffic"),
    },
    "saas": {
        "Churn Rate":          (2.0,  "lower",  "Bessemer Cloud Index 2024: <2% monthly churn = healthy; >5% = product-market fit risk"),
        "Avg NPS Score":       (7.0,  "higher", "NPS scale 0–10: Promoters ≥9, Passives 7–8; <7 = detractor-heavy base"),
        "MoM MRR Growth":      (5.0,  "higher", "Bessemer T2D3: early-stage SaaS target ≥10% MoM; <5% = growth concern"),
        "Avg Contract Length": (12,   "higher", "OpenView 2024: annual contracts (≥12 mo) materially reduce churn exposure vs month-to-month"),
    },
    "ecommerce": {
        "Return Rate":        (10,  "lower",  "Shopify 2024: industry avg 17%; <10% = strong product-fit; >20% = margin erosion risk"),
        "Avg Days to Ship":   (3,   "lower",  "Amazon effect 2024: customers expect ≤3 days; >7 days = cart abandonment and churn driver"),
        "MoM Revenue Growth": (0,   "higher", "Flat or declining MoM revenue = demand, retention, or market share issue"),
        "Avg Discount":       (20,  "lower",  "IRP Commerce 2024: avg discount >20% = systematic margin erosion; review promo strategy"),
    },
    "retail": {
        "Stockout Rate":      (5,    "lower",  "NRF 2024: >8% stockout rate costs retailers ~4% of annual sales; target <5%"),
        "Avg Gross Margin":   (30,   "higher", "NRF 2024: specialty retail target 45–65%; <30% = commodity pricing pressure"),
        "Inventory Turnover": (0.3,  "higher", "Monthly basis: <0.3x = dead stock risk and working capital tied up; target >0.5x"),
    },
    "hr": {
        "Attrition Rate":  (10,  "lower",  "SHRM 2024: avg voluntary turnover 17% all industries; target <10%; >20% = culture or pay gap"),
        "Avg Performance": (3.5, "higher", "5-point scale: >3.5 = meeting expectations; <2.5 = systemic performance or management issue"),
        "Avg Tenure":      (2.0, "higher", "LinkedIn 2024: avg employee tenure 3.7 yrs; <2 yrs = high early attrition or onboarding gap"),
    },
    "hospitality": {
        "Food Cost %":        (30,  "lower",  "NRA 2024: target 28–35%; >38% = menu pricing, portion control, or waste issue"),
        "Labor Cost %":       (32,  "lower",  "Toast 2024: target 25–35%; >38% = overstaffing or wage pressure vs revenue"),
        "Prime Cost %":       (65,  "lower",  "NRA: target <65%; 65–70% = watch zone; >70% = financially unsustainable"),
        "No-Show Rate":       (5,   "lower",  "Toast 2024: >5% no-shows = covers and revenue lost; deposit policy recommended"),
        "MoM Revenue Growth": (0,   "higher", "NRA: flat or declining revenue = demand, pricing, or competitive positioning issue"),
    },
    "restaurant": {
        "Food Cost %":        (30,  "lower",  "NRA 2024: target 28–35%; >38% = menu pricing, portion control, or waste issue"),
        "Labor Cost %":       (32,  "lower",  "Toast 2024: target 25–35%; >38% = overstaffing or wage pressure vs revenue"),
        "Prime Cost %":       (65,  "lower",  "NRA: target <65%; 65–70% = watch zone; >70% = financially unsustainable"),
        "No-Show Rate":       (5,   "lower",  "Toast 2024: >5% no-shows = covers and revenue lost; deposit policy recommended"),
    },
    "real_estate": {
        "Avg Days on Market": (30,  "lower",  "NAR 2024: national median 26 days; >60 days = buyer's market or pricing above demand"),
        "List-to-Sale Ratio": (97,  "higher", "NAR: 100% = full asking price; >97% = strong demand; <93% = price reductions common"),
        "Sale Rate":          (85,  "higher", "NAR: >85% listing close rate = healthy pipeline; <70% = qualification or inventory issue"),
    },
    "operations": {
        "Avg Response Time":   (8,   "lower",  "HDI 2024: top quartile first response <4 hrs; >24 hrs = SLA breach and CSAT risk"),
        "Avg Resolution Time": (48,  "lower",  "Zendesk 2024: top quartile resolution <24 hrs; >72 hrs = customer churn signal"),
        "Resolution Rate":     (85,  "higher", "HDI 2024: >85% resolution rate = efficient team; <70% = escalation or routing problem"),
    },
    "sales": {
        "MoM Revenue Growth": (0,   "higher", "Flat or declining MoM revenue = demand, retention, or pipeline health issue"),
        "Avg Discount":       (15,  "lower",  "SMA 2024: >15% average discount = systematic margin compression; review pricing strategy"),
    },
    "finance": {
        "Margin": (5, "higher", "D&B industry median net margin 5–15%; <5% = thin or at-risk profitability; review cost structure"),
    },
}


def _find_benchmark_violations(domain: str, calc_kpis: dict[str, str]) -> list[dict]:
    violations = []
    benchmarks = _BENCHMARKS.get(domain, {})
    for kpi_name, bench in benchmarks.items():
        threshold, direction = bench[0], bench[1]
        note = bench[2] if len(bench) > 2 else f"Target: {'>' if direction == 'higher' else '<'}{threshold}"
        if kpi_name not in calc_kpis:
            continue
        val = _parse_kpi(calc_kpis[kpi_name])
        if val is None:
            continue
        below = (direction == "higher" and val < threshold) or (direction == "lower" and val > threshold)
        if below:
            gap = abs(val - threshold)
            severity = "high" if gap > threshold * 0.5 else "medium"
            violations.append({
                "name": kpi_name,
                "value": calc_kpis[kpi_name],
                "threshold": threshold,
                "direction": direction,
                "severity": severity,
                "note": note,
            })
    return violations


def _financial_action(domain: str, category: str, title: str) -> str:
    """Return a specific, time-bound recommended action matched to the finding title."""
    t = title.lower()

    # ── Healthcare ────────────────────────────────────────────────────────────
    if "no-show revenue loss" in t or ("no-show" in t and "healthcare" in domain.lower()):
        return "Implement automated SMS/email reminders 48 hrs and 2 hrs before appointments and introduce a cancellation fill list to recover no-show slots within 30 days."
    if "completion rate" in t and "unbilled" in t:
        return "Audit cancellation and 'incomplete' workflows by department; introduce a same-day rescheduling protocol and track weekly completion rate per provider."
    if "low satisfaction" in t and "retention" in t:
        return "Deploy a post-visit survey to surface the top 3 pain points; prioritise wait time and provider communication improvements and review results at 30 and 60 days."
    if "patient attrition" in t and "wait" in t:
        return "Audit appointment block lengths by type and department; stagger arrivals to reduce check-in queue congestion and target average wait under 15 minutes within 60 days."

    # ── Hospitality / Clinic ──────────────────────────────────────────────────
    if "no-show revenue leakage" in t:
        return "Introduce a deposit or prepayment policy for peak bookings; send confirmation reminders 24–48 hrs before and review cancellation policy with front-desk staff."
    if "food cost" in t and "recoverable margin" in t:
        return "Review supplier contracts and portion sizes against recipes; audit waste logs weekly and identify the top 3 contributors to excess food cost within 30 days."

    # ── Marketing ─────────────────────────────────────────────────────────────
    if "roas" in t and "below" in t:
        return "Pause the lowest-performing ad groups immediately; reallocate budget to the top 20% of campaigns by ROAS and test 2 new creative variants within 2 weeks."
    if "roas" in t and "optimisation" in t:
        return "Set a ROAS floor in campaign bidding at your target level; shift budget from below-floor ad sets to above-floor performers on a weekly review cycle."
    if "conversion rate" in t and "benchmark" in t:
        return "A/B test landing page headline and CTA within 2 weeks; audit checkout or form flow for friction points and review offer clarity and trust signals."

    # ── SaaS ─────────────────────────────────────────────────────────────────
    if "churn" in t and "revenue at risk" in t:
        return "Identify all accounts that churned in the last 90 days and conduct 5 exit interviews; implement a proactive health score alert for customers inactive for 60+ days."
    if "nps" in t and "product-market fit" in t:
        return "Segment detractors by cohort and usage tier; schedule discovery calls with the bottom 10% of accounts within 2 weeks to identify top churn risks early."

    # ── Sales ─────────────────────────────────────────────────────────────────
    if "avg discount" in t and "revenue recovery" in t:
        return "Set a discount approval floor — discounts above the identified threshold require manager sign-off; track discounting by rep monthly to identify coaching opportunities."
    if "revenue declining" in t:
        return "Identify the top 3 accounts driving the revenue decline and schedule retention calls this week; review pipeline conversion rates by stage for early warning signals."

    # ── Retail ───────────────────────────────────────────────────────────────
    if "stockout rate" in t and "lost sales" in t:
        return "Configure reorder point alerts at 2× lead time buffer for the top 20% of SKUs by sales velocity; review supplier lead time SLAs within 30 days."
    if "gross margin" in t and "floor" in t:
        return "Identify the bottom 10 SKUs by margin and review supplier cost, sell price, and shrinkage; renegotiate terms or delist underperformers within 60 days."
    if "overstock" in t and "carrying cost" in t:
        return "Run a markdown or clearance promotion for SKUs with cover days exceeding 90; freeze replenishment orders on overstocked items until cover normalises below 60 days."

    # ── Ecommerce ─────────────────────────────────────────────────────────────
    if "return rate" in t and "net revenue" in t:
        return "Analyse return reasons by product category; improve size guides and descriptions for the top 5 return SKUs and introduce a monthly 'returns by SKU' review."
    if "fulfillment lead time" in t and "repeat purchase" in t:
        return "Audit the warehouse pick-pack-ship cycle by carrier and zone; set a 3-day fulfillment SLA target and address the top 3 bottleneck steps within 30 days."

    # ── Real Estate ───────────────────────────────────────────────────────────
    if "avg dom" in t and "carrying cost" in t:
        return "Review pricing on all listings exceeding 45 DOM; schedule price reduction conversations with sellers within 1 week and track active-to-sold conversion by agent."
    if "listing conversion gap" in t:
        return "Review the top unsold listings for price positioning vs. comparables; implement a 30-day price review cadence for all active listings to reduce days-on-market."
    if "price distribution skew" in t:
        return "Prioritise marketing spend on premium-tier listings with DOM > 30 days; consider staging or photography refreshes to improve conversion on stale high-end listings."

    # ── HR ────────────────────────────────────────────────────────────────────
    if "attrition cost" in t:
        return "Conduct stay interviews with all employees in their first 12 months; identify the top 3 attrition drivers from exit data and assign HR ownership with a 30-day action plan."

    # ── Operations ────────────────────────────────────────────────────────────
    if "backlog" in t:
        return "Triage the backlog by priority and age; assign dedicated capacity to clear items older than 30 days within 2 weeks and establish a daily backlog burn metric."
    if "resolution time" in t and "sla breach" in t:
        return "Map the resolution workflow to identify the top handoff delays; set stage-by-stage SLA targets and implement escalation triggers for tickets breaching 24 hours."

    # ── Finance ───────────────────────────────────────────────────────────────
    if "negative net margin" in t:
        return "Identify the top 3 cost centres exceeding budget; freeze discretionary spend and schedule a P&L review with department heads within 2 weeks."
    if "thin margin" in t:
        return "Run a margin bridge analysis to identify the largest drag between gross and net margin; target one cost reduction initiative per quarter with measurable targets."

    # ── Generic fallbacks by category ─────────────────────────────────────────
    if "Revenue at Risk" in category:
        return "Identify the root cause of the revenue loss; assign a named owner and establish a 30-day recovery plan with weekly check-ins."
    if "Cost Savings" in category:
        return "Launch a cost reduction initiative targeting the identified savings; assign ownership and set a 60-day milestone review."
    if "Revenue Opportunity" in category:
        return "Develop and test a capture strategy for the identified revenue opportunity; pilot within 45 days and measure impact at 90 days."
    return "Review the identified issue with relevant team leads; assign ownership and establish a 30-day improvement target."


def _benchmark_action(domain: str, kpi_name: str) -> str:
    """Return a specific action for a KPI that breached its industry benchmark."""
    actions: dict[str, str] = {
        # Healthcare
        "No-Show Rate": "Implement automated SMS/email reminders 48 hrs and 2 hrs before appointments; introduce a cancellation fill list and track no-show rate weekly by provider.",
        "Avg Wait Time": "Audit appointment block lengths and stagger patient arrivals; target average wait under 15 minutes and review scheduling templates within 30 days.",
        "Patient Satisfaction": "Deploy a post-visit survey to surface the top 3 pain points; action the highest-impact item within 30 days and re-measure at 60 days.",
        "Completion Rate": "Audit incomplete appointment workflows by department; introduce a same-day rescheduling protocol and track weekly completion rate per provider.",
        # SaaS
        "Churn Rate": "Identify all churned accounts from the last 90 days and run 5 exit interviews; implement a customer health score with alerts for accounts inactive for 60+ days.",
        "Avg NPS Score": "Segment NPS detractors by cohort and usage; schedule calls with the bottom 10% of accounts within 2 weeks and address the top-cited complaint within 30 days.",
        "MoM MRR Growth": "Review pipeline conversion rates and time-to-close by stage; identify the top 3 growth levers (new logos, expansion, churn recovery) and set a 90-day MRR target.",
        "Avg Contract Length": "Offer a 10–15% annual prepay discount to convert month-to-month accounts; train sales on multi-year value framing and track annual contract rate monthly.",
        # Marketing
        "ROAS": "Pause the lowest-performing 20% of ad spend by ROAS immediately; reallocate to top performers and test 2 new creatives within 2 weeks.",
        "CTR": "Refresh ad creative for the lowest CTR campaigns; test 3 headline variants per ad set and review audience targeting overlap within 2 weeks.",
        "Conversion Rate": "A/B test the landing page headline and CTA button; audit the checkout flow for friction points and review trust signals within 2 weeks.",
        "CPC": "Tighten keyword match types to reduce irrelevant clicks; review bid strategies and add negative keywords weekly to drive CPC below the $8 threshold.",
        "CPA": "Identify the 3 highest-CPA campaigns and audit targeting, creative, and landing page alignment; pause or restructure within 1 week.",
        # Retail
        "Inventory Turnover": "Identify the bottom 20% of SKUs by turnover rate; run a clearance promotion and freeze replenishment on slow movers until stock normalises.",
        "Avg Days Cover": "Flag all SKUs with cover exceeding 60 days; initiate markdowns or bundle promotions and pause reorders until cover falls below the 60-day threshold.",
        "Stockout Rate": "Configure reorder alerts at 2× lead time buffer for top-velocity SKUs; review supplier lead time SLAs and safety stock levels within 30 days.",
        "Gross Margin": "Identify the bottom 10 SKUs by margin; review pricing, supplier cost, and shrinkage and renegotiate or delist underperformers within 60 days.",
        # Ecommerce
        "Return Rate": "Analyse return reasons by category; improve product descriptions and size guides for the top 5 return SKUs and introduce a monthly SKU-level returns review.",
        "Avg Days to Ship": "Audit the pick-pack-ship cycle by carrier zone; set a 3-day fulfillment SLA and address the top 3 bottleneck steps within 30 days.",
        "Avg Order Value": "Test bundle offers and upsell recommendations at checkout; introduce a free-shipping threshold 20% above current AOV and measure AOV lift at 30 days.",
        # HR
        "Attrition Rate": "Conduct stay interviews with employees in their first 12 months; identify the top 3 attrition drivers from exit data and assign HR ownership within 30 days.",
        "Avg Tenure": "Review onboarding and 90-day engagement programmes; introduce structured check-ins at 30, 60, and 90 days to improve early-tenure retention.",
        "Avg Time to Hire": "Audit the hiring funnel stage by stage; identify the top 2 bottlenecks, streamline interview rounds and target offer-to-accept within 3 business days.",
        # Hospitality / Restaurant
        "Table Turnover Rate": "Optimise reservation slot duration based on actual dining times; introduce a pacing strategy for peak hours to reduce idle table time.",
        "Food Cost %": "Conduct a weekly waste audit and review portion sizes against recipes; renegotiate supplier pricing on the top 5 ingredients by cost within 30 days.",
        "Labor Cost %": "Review scheduling against cover counts; reduce idle labour during off-peak hours and align shift patterns with historical demand data.",
        "Avg Check Size": "Train staff on suggestive selling for starters, sides, and beverages; introduce a daily specials briefing and track avg check size per server weekly.",
        # Real Estate
        "Avg DOM": "Review pricing on all listings exceeding 45 DOM; schedule price adjustment conversations with sellers within 1 week and track active-to-sold conversion by agent.",
        "Sale Rate": "Audit listings that expired without sale; review pricing strategy vs. comparables and implement a 30-day price review cadence for all active listings.",
        # Operations
        "Resolution Rate": "Identify the top 3 ticket categories with lowest resolution rates; build resolution playbooks for each and set a weekly resolution rate target per team.",
        "Avg Response Time": "Implement first-response SLA alerts; triage incoming volume by channel and assign dedicated coverage during peak hours to reduce response lag.",
        # Finance
        "Net Profit Margin": "Run a margin bridge analysis from gross to net; identify the top 3 cost centres over budget and freeze discretionary spend pending a P&L review.",
        "Gross Profit Margin": "Review the top 10 products or services by margin; renegotiate supplier terms or adjust pricing on the lowest-margin items within 60 days.",
    }
    action = actions.get(kpi_name)
    if action:
        return action
    return f"Investigate the root cause of underperformance in {kpi_name}; assign a named owner, set a target, and review progress at 30 and 60 days."


def _ops_category(ops_category: str) -> str:
    mapping = {
        "Capacity": "Efficiency",
        "Throughput": "Operations",
        "Backlog": "Operations",
        "Quality": "Customer Experience",
        "Utilization": "Efficiency",
        "Risk": "Risk",
    }
    return mapping.get(ops_category, "Operations")


def _kpi_category(domain: str, kpi_name: str) -> str:
    revenue_kpis = {"Total Revenue", "MoM Revenue Growth", "ROAS", "Total MRR", "Implied ARR", "Total Billing"}
    cost_kpis = {"Food Cost %", "Labor Cost %", "Prime Cost %", "Avg Discount", "CPC", "CPA"}
    exp_kpis = {"Patient Satisfaction", "Avg Wait Time", "Avg Days to Ship", "Avg Response Time"}
    if kpi_name in revenue_kpis:
        return "Revenue"
    if kpi_name in cost_kpis:
        return "Cost"
    if kpi_name in exp_kpis:
        return "Customer Experience"
    return "Efficiency"
