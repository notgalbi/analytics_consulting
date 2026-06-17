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
                recommended_action=f"Review the processes driving {v['name']} and assign a named owner with a 30-day improvement target.",
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
    """Derive a recommended action string from domain and finding category."""
    if "Revenue at Risk" in category:
        return f"Assign a named owner to investigate and remediate the identified revenue risk within 30 days."
    if "Cost Savings" in category:
        return f"Launch a cost reduction initiative targeting the identified savings opportunity within 60 days."
    if "Revenue Opportunity" in category:
        return f"Develop and test a strategy to capture the identified revenue opportunity within 45 days."
    return "Review the identified issue with relevant team leads and establish a 30-day action plan."


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
