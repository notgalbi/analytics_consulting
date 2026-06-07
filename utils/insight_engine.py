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
    for op in operational_impact.findings:
        if op.severity in ("High", "Medium"):
            cat = _ops_category(op.category)
            priority = "High" if op.severity == "High" else "Medium"
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
    for v in violations:
        if v["name"] not in seen_titles and len(insights) < 7:
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
    if completeness < 95:
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


_BENCHMARKS: dict[str, dict] = {
    "healthcare":   {"No-Show Rate": (8, "lower"), "Avg Wait Time": (15, "lower"), "Patient Satisfaction": (4.0, "higher"), "Completion Rate": (90, "higher")},
    "marketing":    {"ROAS": (5.5, "higher"), "CTR": (3.0, "higher"), "Conversion Rate": (5.0, "higher")},
    "saas":         {"Churn Rate": (2.0, "lower"), "Avg NPS Score": (7.0, "higher"), "MoM MRR Growth": (5.0, "higher")},
    "ecommerce":    {"Return Rate": (10, "lower"), "Avg Days to Ship": (3, "lower"), "MoM Revenue Growth": (0, "higher")},
    "retail":       {"Stockout Rate": (5, "lower"), "Avg Gross Margin": (30, "higher")},
    "hr":           {"Attrition Rate": (10, "lower"), "Avg Performance": (3.5, "higher")},
    "hospitality":  {"Food Cost %": (30, "lower"), "Labor Cost %": (32, "lower"), "Prime Cost %": (65, "lower"), "No-Show Rate": (5, "lower")},
    "restaurant":   {"Food Cost %": (30, "lower"), "Labor Cost %": (32, "lower"), "Prime Cost %": (65, "lower"), "No-Show Rate": (5, "lower")},
    "real_estate":  {"Avg Days on Market": (30, "lower"), "List-to-Sale Ratio": (97, "higher"), "Sale Rate": (85, "higher")},
    "operations":   {"Avg Response Time": (8, "lower"), "Avg Resolution Time": (48, "lower")},
    "sales":        {"MoM Revenue Growth": (0, "higher"), "Avg Discount": (15, "lower")},
    "finance":      {"Margin": (5, "higher")},
}


def _find_benchmark_violations(domain: str, calc_kpis: dict[str, str]) -> list[dict]:
    violations = []
    benchmarks = _BENCHMARKS.get(domain, {})
    for kpi_name, (threshold, direction) in benchmarks.items():
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
                "note": f"Target: {'>' if direction == 'higher' else '<'}{threshold}",
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
