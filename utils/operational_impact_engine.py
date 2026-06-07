"""
operational_impact_engine.py — Rule-based operational impact estimation.

Estimates capacity utilization gaps, throughput constraints, and backlog
risks from computed KPIs without requiring the Claude API.

Public API:
    estimate_operational_impact(domain, calc_kpis, profile) -> OperationalImpact
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class OperationalFinding:
    title: str
    category: str    # "Capacity" | "Throughput" | "Backlog" | "Quality" | "Utilization" | "Risk"
    severity: str    # "High" | "Medium" | "Low"
    finding: str
    impact: str
    recommendation: str
    metric_name: str | None = None
    metric_value: str | None = None
    benchmark: str | None = None


@dataclass
class OperationalImpact:
    domain: str
    capacity_utilization_pct: float | None
    throughput_gap_description: str | None
    backlog_risk_level: str | None  # "High" | "Medium" | "Low" | None
    findings: list[OperationalFinding] = field(default_factory=list)
    summary_statement: str = ""


# ── Public function ───────────────────────────────────────────────────────────

def estimate_operational_impact(
    domain: str,
    calc_kpis: dict[str, str],
    profile: dict,
) -> OperationalImpact:
    """Estimate operational impact from computed KPIs using domain-specific rules."""
    _calculators = {
        "healthcare":   _ops_healthcare,
        "hospitality":  _ops_hospitality,
        "restaurant":   _ops_hospitality,
        "marketing":    _ops_marketing,
        "saas":         _ops_saas,
        "sales":        _ops_sales,
        "retail":       _ops_retail,
        "ecommerce":    _ops_ecommerce,
        "real_estate":  _ops_real_estate,
        "hr":           _ops_hr,
        "operations":   _ops_operations,
        "finance":      _ops_finance,
    }

    findings: list[OperationalFinding] = []
    capacity_pct: float | None = None
    throughput_gap: str | None = None
    backlog_risk: str | None = None

    calc_fn = _calculators.get(domain)
    if calc_fn:
        findings, capacity_pct, throughput_gap, backlog_risk = calc_fn(calc_kpis, profile)

    return OperationalImpact(
        domain=domain,
        capacity_utilization_pct=capacity_pct,
        throughput_gap_description=throughput_gap,
        backlog_risk_level=backlog_risk,
        findings=findings,
        summary_statement=_build_ops_summary(findings),
    )


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


def _op(
    title: str,
    category: str,
    severity: str,
    finding: str,
    impact: str,
    recommendation: str,
    metric_name: str | None = None,
    metric_value: str | None = None,
    benchmark: str | None = None,
) -> OperationalFinding:
    return OperationalFinding(
        title=title, category=category, severity=severity,
        finding=finding, impact=impact, recommendation=recommendation,
        metric_name=metric_name, metric_value=metric_value, benchmark=benchmark,
    )


def _build_ops_summary(findings: list[OperationalFinding]) -> str:
    if not findings:
        return "No significant operational constraints identified from available KPI data."
    high = [f for f in findings if f.severity == "High"]
    if high:
        return f"Critical operational issue: {high[0].finding}"
    return f"{findings[0].title} — review recommendations for remediation steps."


# ── Domain calculators ────────────────────────────────────────────────────────

def _ops_healthcare(calc_kpis: dict, profile: dict):
    findings = []
    capacity_pct: float | None = None
    throughput_gap: str | None = None
    backlog_risk: str | None = None

    no_show_rate  = _parse_kpi(calc_kpis.get("No-Show Rate", ""))
    wait_time     = _parse_kpi(calc_kpis.get("Avg Wait Time", ""))
    satisfaction  = _parse_kpi(calc_kpis.get("Patient Satisfaction", ""))
    completion    = _parse_kpi(calc_kpis.get("Completion Rate", ""))

    if no_show_rate is not None:
        capacity_pct = 100 - no_show_rate
        if no_show_rate > 15:
            findings.append(_op(
                title=f"No-Show Rate {no_show_rate:.1f}% — Capacity Waste",
                category="Utilization",
                severity="High",
                finding=f"{no_show_rate:.1f}% of scheduled appointment slots go unfilled each period.",
                impact="Provider time wasted, scheduling gaps create revenue holes that cannot be recovered same-day.",
                recommendation="Implement 48h and 24h automated SMS/email reminders; establish a same-day waitlist to backfill cancellations.",
                metric_name="No-Show Rate", metric_value=f"{no_show_rate:.1f}%", benchmark="< 8%",
            ))

    if wait_time is not None and wait_time > 20:
        sev = "High" if wait_time > 35 else "Medium"
        throughput_gap = f"Wait times averaging {wait_time:.0f} min indicate scheduling template misalignment"
        findings.append(_op(
            title=f"Wait Times {wait_time:.0f} Min — Scheduling Constraint",
            category="Throughput",
            severity=sev,
            finding=f"Average patient wait of {wait_time:.0f} minutes exceeds the 15-minute clinical standard by {wait_time - 15:.0f} minutes.",
            impact="Extended waits reduce same-day throughput, suppress satisfaction scores, and increase walk-out risk for non-emergency visits.",
            recommendation="Audit appointment block lengths by type and department; stagger arrivals to reduce check-in queue bottleneck.",
            metric_name="Avg Wait Time", metric_value=f"{wait_time:.0f} min", benchmark="< 15 min",
        ))

    if satisfaction is not None and satisfaction < 3.5:
        backlog_risk = "High"
        findings.append(_op(
            title=f"Patient Satisfaction {satisfaction:.1f}/5 — Retention Risk",
            category="Quality",
            severity="High",
            finding=f"Patient satisfaction of {satisfaction:.1f}/5 is below the 3.5 minimum threshold for reliable retention.",
            impact="Low satisfaction reduces return visit probability, online review scores, and referral volume.",
            recommendation="Conduct exit surveys for low-satisfaction encounters; identify top complaint categories and assign process owners.",
            metric_name="Patient Satisfaction", metric_value=f"{satisfaction:.1f}/5", benchmark="> 4.0/5",
        ))

    return findings, capacity_pct, throughput_gap, backlog_risk


def _ops_hospitality(calc_kpis: dict, profile: dict):
    findings = []
    capacity_pct: float | None = None
    throughput_gap: str | None = None
    backlog_risk: str | None = None

    food_cost    = _parse_kpi(calc_kpis.get("Food Cost %", ""))
    labor_cost   = _parse_kpi(calc_kpis.get("Labor Cost %", ""))
    prime_cost   = _parse_kpi(calc_kpis.get("Prime Cost %", ""))
    no_show_rate = _parse_kpi(calc_kpis.get("No-Show Rate", ""))

    if prime_cost is not None and prime_cost > 70:
        findings.append(_op(
            title=f"Prime Cost {prime_cost:.1f}% — Critical Margin Compression",
            category="Capacity",
            severity="High",
            finding=f"Combined food + labor cost of {prime_cost:.1f}% leaves less than 30% of revenue to cover all other operating costs.",
            impact="Negative or near-zero operating profit — the business cannot sustain profitability at this prime cost level.",
            recommendation="Launch immediate food cost review (menu engineering + waste audit) and labor scheduling restructure targeting prime cost below 65%.",
            metric_name="Prime Cost %", metric_value=f"{prime_cost:.1f}%", benchmark="< 65%",
        ))
    elif food_cost is not None and food_cost > 38:
        findings.append(_op(
            title=f"Food Cost {food_cost:.1f}% — Kitchen Cost Control Failure",
            category="Quality",
            severity="High" if food_cost > 42 else "Medium",
            finding=f"Food cost of {food_cost:.1f}% exceeds the 38% critical threshold — kitchen is operating without effective cost control.",
            impact="Every point above 30% food cost directly reduces gross margin; at 38%+ the operation is structurally unprofitable.",
            recommendation="Implement daily food cost reporting, conduct a full waste and portioning audit within 30 days.",
            metric_name="Food Cost %", metric_value=f"{food_cost:.1f}%", benchmark="28–35%",
        ))

    if labor_cost is not None and labor_cost > 38:
        findings.append(_op(
            title=f"Labor Cost {labor_cost:.1f}% — Scheduling Inefficiency",
            category="Utilization",
            severity="High" if labor_cost > 42 else "Medium",
            finding=f"Labor cost of {labor_cost:.1f}% indicates over-staffing relative to cover volume on low-demand days.",
            impact="Excess labor hours directly compress operating margin without producing proportional revenue.",
            recommendation="Build cover-volume-based scheduling templates (low/standard/peak) to flex staff levels with actual demand.",
            metric_name="Labor Cost %", metric_value=f"{labor_cost:.1f}%", benchmark="25–35%",
        ))

    if no_show_rate is not None and no_show_rate > 10:
        capacity_pct = 100 - no_show_rate
        findings.append(_op(
            title=f"No-Show Rate {no_show_rate:.1f}% — Seat Utilization Loss",
            category="Utilization",
            severity="High",
            finding=f"{no_show_rate:.1f}% of reserved covers are not arriving, leaving tables empty that cannot be walk-in filled on short notice.",
            impact="Lost cover revenue plus over-provisioned staff and food prep for covers that never arrive.",
            recommendation="Implement credit card hold for parties of 3+ with $15-$20/cover no-show fee and automated day-before confirmation.",
            metric_name="No-Show Rate", metric_value=f"{no_show_rate:.1f}%", benchmark="< 5%",
        ))

    return findings, capacity_pct, throughput_gap, backlog_risk


def _ops_marketing(calc_kpis: dict, profile: dict):
    findings = []

    roas            = _parse_kpi(calc_kpis.get("ROAS", ""))
    conversion_rate = _parse_kpi(calc_kpis.get("Conversion Rate", ""))

    if roas is not None and roas < 2.0:
        findings.append(_op(
            title=f"ROAS {roas:.2f}x — Media Budget Inefficiency",
            category="Throughput",
            severity="High",
            finding=f"Return on ad spend of {roas:.2f}x means media spend is generating less than $2 per dollar invested.",
            impact="Budget is being consumed without proportional revenue return — continuing at this ROAS will exhaust budget faster than it builds revenue.",
            recommendation="Pause lowest-performing campaigns, reallocate budget to highest-ROAS channels, and review creative and targeting parameters.",
            metric_name="ROAS", metric_value=f"{roas:.2f}x", benchmark="> 4x",
        ))

    if conversion_rate is not None and conversion_rate < 1.0:
        findings.append(_op(
            title=f"Conversion Rate {conversion_rate:.2f}% — Funnel Breakdown",
            category="Throughput",
            severity="High",
            finding=f"Conversion rate below 1% indicates a fundamental offer-audience-landing page misalignment.",
            impact="Traffic is being generated but not converting — every impression and click is wasted spend.",
            recommendation="Conduct landing page A/B test, review offer clarity, and audit conversion tracking accuracy.",
            metric_name="Conversion Rate", metric_value=f"{conversion_rate:.2f}%", benchmark="> 2%",
        ))

    return findings, None, None, None


def _ops_saas(calc_kpis: dict, profile: dict):
    findings = []
    backlog_risk: str | None = None

    churn_rate = _parse_kpi(calc_kpis.get("Churn Rate", ""))
    nps        = _parse_kpi(calc_kpis.get("Avg NPS Score", ""))

    if churn_rate is not None and churn_rate > 5:
        backlog_risk = "High"
        findings.append(_op(
            title=f"Churn {churn_rate:.1f}% — Revenue Base Erosion",
            category="Risk",
            severity="High",
            finding=f"Monthly churn of {churn_rate:.1f}% means the business loses {churn_rate:.1f}% of its MRR base every 30 days.",
            impact="At this rate, customer acquisition must run at {churn_rate:.1f}%+ MoM just to maintain flat revenue.",
            recommendation="Identify top churn segments, implement 60-day customer health monitoring, and launch proactive success intervention at churn-risk accounts.",
            metric_name="Churn Rate", metric_value=f"{churn_rate:.1f}%", benchmark="< 2% monthly",
        ))

    if nps is not None and nps < 5:
        findings.append(_op(
            title=f"NPS {nps:.1f} — Expansion Revenue Risk",
            category="Quality",
            severity="High" if nps < 3 else "Medium",
            finding=f"NPS of {nps:.1f} indicates more detractors and passives than promoters — expansion and referral revenue channels are severely constrained.",
            impact="Without promoters, the growth loop breaks — the business must rely entirely on paid acquisition to grow.",
            recommendation="Conduct NPS follow-up interviews with detractors; identify top product gaps and route them to engineering roadmap.",
            metric_name="Avg NPS Score", metric_value=f"{nps:.1f}", benchmark="> 7",
        ))

    return findings, None, None, backlog_risk


def _ops_sales(calc_kpis: dict, profile: dict):
    findings = []

    mom_growth   = _parse_kpi(calc_kpis.get("MoM Revenue Growth", ""))
    avg_discount = _parse_kpi(calc_kpis.get("Avg Discount", ""))

    if mom_growth is not None and mom_growth < 0:
        findings.append(_op(
            title=f"Revenue Contracting {abs(mom_growth):.1f}% MoM",
            category="Risk",
            severity="High",
            finding=f"Month-over-month revenue decline of {abs(mom_growth):.1f}% signals a demand softening or commercial execution problem.",
            impact="Revenue contraction directly reduces operating coverage and creates uncertainty for headcount and investment plans.",
            recommendation="Conduct pipeline review, identify top accounts at risk, and implement a revenue recovery sprint with defined weekly targets.",
            metric_name="MoM Revenue Growth", metric_value=f"{mom_growth:.1f}%", benchmark="> 5%",
        ))

    if avg_discount is not None and avg_discount > 25:
        findings.append(_op(
            title=f"Avg Discount {avg_discount:.1f}% — Pricing Discipline Breakdown",
            category="Quality",
            severity="Medium",
            finding=f"Average discount of {avg_discount:.1f}% indicates systematic price negotiation weakness or product-value misalignment.",
            impact="Excessive discounting trains buyers to expect concessions and permanently erodes average selling price.",
            recommendation="Implement tiered discount approval matrix; require VP sign-off for deals above 20% discount threshold.",
            metric_name="Avg Discount", metric_value=f"{avg_discount:.1f}%", benchmark="< 10%",
        ))

    return findings, None, None, None


def _ops_retail(calc_kpis: dict, profile: dict):
    findings = []
    throughput_gap: str | None = None

    stockout_rate = _parse_kpi(calc_kpis.get("Stockout Rate", ""))
    days_cover    = _parse_kpi(calc_kpis.get("Avg Days Cover", ""))
    turnover      = _parse_kpi(calc_kpis.get("Inventory Turnover", ""))

    if stockout_rate is not None and stockout_rate > 10:
        throughput_gap = f"{stockout_rate:.1f}% of SKUs below reorder point — active supply constraint"
        findings.append(_op(
            title=f"Stockout Rate {stockout_rate:.1f}% — Supply Chain Constraint",
            category="Capacity",
            severity="High",
            finding=f"{stockout_rate:.1f}% of SKUs are at or below their reorder point — the business is actively unable to fulfill demand on these items.",
            impact="Stockouts result in lost sales, customer frustration, and margin erosion as buyers substitute or leave.",
            recommendation="Flag at-risk SKUs for emergency replenishment order; review reorder point calculations and supplier lead time assumptions.",
            metric_name="Stockout Rate", metric_value=f"{stockout_rate:.1f}%", benchmark="< 5%",
        ))

    if days_cover is not None and days_cover < 7:
        findings.append(_op(
            title=f"Avg Days Cover {days_cover:.0f} Days — Replenishment Urgency",
            category="Risk",
            severity="High",
            finding=f"Average of {days_cover:.0f} days of stock remaining at current sell-through rate — replenishment orders must be placed immediately.",
            impact="At current velocity, a significant portion of SKUs will hit zero stock within the week without immediate reorder action.",
            recommendation="Issue emergency POs for all SKUs with <7 days cover; expedite supplier shipments where possible.",
            metric_name="Avg Days Cover", metric_value=f"{days_cover:.0f} days", benchmark="> 30 days",
        ))

    if turnover is not None and turnover < 0.2:
        findings.append(_op(
            title=f"Inventory Turnover {turnover:.2f}x — Slow-Moving Stock Risk",
            category="Utilization",
            severity="Medium",
            finding=f"Monthly turnover of {turnover:.2f}x indicates significant slow-moving inventory tying up capital.",
            impact="Slow inventory consumes working capital, occupies shelf space, and increases markdown risk as items age.",
            recommendation="Identify bottom-quartile SKUs by turnover rate and implement a clearance or returns-to-supplier strategy.",
            metric_name="Inventory Turnover", metric_value=f"{turnover:.2f}x", benchmark="> 0.5x monthly",
        ))

    return findings, None, throughput_gap, None


def _ops_ecommerce(calc_kpis: dict, profile: dict):
    findings = []

    return_rate   = _parse_kpi(calc_kpis.get("Return Rate", ""))
    days_to_ship  = _parse_kpi(calc_kpis.get("Avg Days to Ship", ""))
    mom_growth    = _parse_kpi(calc_kpis.get("MoM Revenue Growth", ""))

    if days_to_ship is not None and days_to_ship > 3:
        findings.append(_op(
            title=f"Fulfillment Time {days_to_ship:.1f} Days — Customer Experience Gap",
            category="Throughput",
            severity="High" if days_to_ship > 7 else "Medium",
            finding=f"Average shipping time of {days_to_ship:.1f} days is {days_to_ship - 3:.1f} days above the 3-day customer expectation.",
            impact="Slow fulfillment drives cart abandonment, reduces repeat purchase intent, and generates negative reviews.",
            recommendation="Audit warehouse pick-pack process for bottlenecks; evaluate 2-day shipping carrier upgrade on top SKUs.",
            metric_name="Avg Days to Ship", metric_value=f"{days_to_ship:.1f} days", benchmark="< 3 days",
        ))

    if return_rate is not None and return_rate > 20:
        findings.append(_op(
            title=f"Return Rate {return_rate:.1f}% — Fulfillment Quality Issue",
            category="Quality",
            severity="High",
            finding=f"Return rate of {return_rate:.1f}% is double the 10% benchmark — indicating product quality, description accuracy, or packaging problems.",
            impact="High returns consume warehouse capacity, increase per-order cost, and compress net margin significantly.",
            recommendation="Analyze return reason codes; identify top 3 SKUs by return rate and address root cause (size guide, product description, packaging).",
            metric_name="Return Rate", metric_value=f"{return_rate:.1f}%", benchmark="< 10%",
        ))

    return findings, None, None, None


def _ops_real_estate(calc_kpis: dict, profile: dict):
    findings = []

    dom       = _parse_kpi(calc_kpis.get("Avg Days on Market", ""))
    sale_rate = _parse_kpi(calc_kpis.get("Sale Rate", ""))

    if dom is not None and dom > 60:
        findings.append(_op(
            title=f"Avg DOM {dom:.0f} Days — Listing Velocity Problem",
            category="Throughput",
            severity="High",
            finding=f"Properties averaging {dom:.0f} days on market before sale, well above the 45-day efficient benchmark.",
            impact="Slow-moving listings tie up agent time, erode seller confidence, and signal pricing or marketing ineffectiveness.",
            recommendation="Implement automatic DOM review trigger at day 40: pricing analysis, marketing refresh, and broker open-house within 1 week.",
            metric_name="Avg Days on Market", metric_value=f"{dom:.0f} days", benchmark="< 45 days",
        ))

    if sale_rate is not None and sale_rate < 75:
        findings.append(_op(
            title=f"Sale Rate {sale_rate:.1f}% — Conversion Pipeline Gap",
            category="Capacity",
            severity="High" if sale_rate < 60 else "Medium",
            finding=f"Sale rate of {sale_rate:.1f}% means more than 1 in 4 listings is not converting to a closed transaction.",
            impact="Unconverted listings represent wasted agent time, marketing spend, and seller relationship erosion.",
            recommendation="Review pricing strategy on unsold listings; identify common objection patterns and build a structured re-engagement protocol.",
            metric_name="Sale Rate", metric_value=f"{sale_rate:.1f}%", benchmark="> 85%",
        ))

    return findings, None, None, None


def _ops_hr(calc_kpis: dict, profile: dict):
    findings = []
    backlog_risk: str | None = None

    attrition_rate = _parse_kpi(calc_kpis.get("Attrition Rate", ""))
    avg_performance = _parse_kpi(calc_kpis.get("Avg Performance", ""))
    avg_tenure = _parse_kpi(calc_kpis.get("Avg Tenure", ""))

    if attrition_rate is not None and attrition_rate > 15:
        backlog_risk = "High"
        findings.append(_op(
            title=f"Attrition {attrition_rate:.1f}% — Capacity Loss Risk",
            category="Risk",
            severity="High",
            finding=f"Attrition rate of {attrition_rate:.1f}% exceeds 15% — the organization is losing headcount faster than it can maintain operational continuity.",
            impact="Knowledge loss, over-burdened remaining staff, recruitment costs, and declining service quality.",
            recommendation="Conduct stay interviews with high-tenure employees; identify top 3 attrition drivers and build a targeted retention program.",
            metric_name="Attrition Rate", metric_value=f"{attrition_rate:.1f}%", benchmark="< 10%",
        ))

    if avg_tenure is not None and avg_tenure < 2:
        findings.append(_op(
            title=f"Avg Tenure {avg_tenure:.1f} Years — Knowledge Retention Risk",
            category="Risk",
            severity="Medium",
            finding=f"Average tenure of {avg_tenure:.1f} years indicates a predominantly junior or recently hired workforce.",
            impact="Low tenure correlates with lower productivity, higher training costs, and institutional knowledge gaps.",
            recommendation="Implement structured onboarding and 90-day performance reviews; pair new hires with senior mentors in each department.",
            metric_name="Avg Tenure", metric_value=f"{avg_tenure:.1f} yrs", benchmark="> 3 years",
        ))

    if avg_performance is not None and avg_performance < 3.0:
        findings.append(_op(
            title=f"Avg Performance {avg_performance:.1f}/5 — Workforce Effectiveness Gap",
            category="Quality",
            severity="High",
            finding=f"Average performance score of {avg_performance:.1f}/5 is below the 3.5 expected minimum — significant portion of workforce is underperforming.",
            impact="Below-standard performance directly reduces output quality, customer experience, and team productivity.",
            recommendation="Review performance management process; establish clear expectations, monthly check-ins, and development plans for bottom-quartile performers.",
            metric_name="Avg Performance", metric_value=f"{avg_performance:.1f}/5", benchmark="> 3.5/5",
        ))

    return findings, None, None, backlog_risk


def _ops_operations(calc_kpis: dict, profile: dict):
    findings = []
    backlog_risk: str | None = None

    open_tickets   = _parse_kpi(calc_kpis.get("Open Tickets", ""))
    total_tickets  = _parse_kpi(calc_kpis.get("Total Tickets", ""))
    avg_response   = _parse_kpi(calc_kpis.get("Avg Response Time", ""))
    avg_resolution = _parse_kpi(calc_kpis.get("Avg Resolution Time", ""))

    if open_tickets and total_tickets and total_tickets > 0:
        backlog_pct = open_tickets / total_tickets * 100
        if backlog_pct > 30:
            backlog_risk = "High"
            sev = "High"
        elif backlog_pct > 15:
            backlog_risk = "Medium"
            sev = "Medium"
        else:
            backlog_risk = "Low"
            sev = "Low"

        if backlog_pct > 15:
            findings.append(_op(
                title=f"Backlog at {backlog_pct:.0f}% of Volume",
                category="Backlog",
                severity=sev,
                finding=f"{open_tickets:.0f} tickets ({backlog_pct:.0f}% of total volume) are open and unresolved.",
                impact="Growing backlog signals that inbound volume exceeds team capacity — SLAs will breach if not addressed.",
                recommendation="Conduct triage review of open tickets; escalate aged items; assess whether temporary capacity addition is needed.",
                metric_name="Open Tickets", metric_value=f"{open_tickets:.0f}", benchmark="< 15% open",
            ))

    if avg_resolution is not None and avg_resolution > 48:
        findings.append(_op(
            title=f"Resolution Time {avg_resolution:.0f}hrs — SLA Exposure",
            category="Throughput",
            severity="High" if avg_resolution > 96 else "Medium",
            finding=f"Average resolution time of {avg_resolution:.0f} hours likely breaches standard 24-48 hour SLA commitments.",
            impact="SLA breaches generate penalty exposure, damage customer confidence, and increase escalation volume.",
            recommendation="Map top ticket types to resolution time; identify the 20% of categories driving 80% of resolution time and assign dedicated capacity.",
            metric_name="Avg Resolution Time", metric_value=f"{avg_resolution:.0f} hrs", benchmark="< 24 hrs",
        ))

    if avg_response is not None and avg_response > 4:
        findings.append(_op(
            title=f"Response Time {avg_response:.1f}hrs — Customer Experience Gap",
            category="Quality",
            severity="Medium",
            finding=f"Average first response of {avg_response:.1f} hours is above the 4-hour standard for professional support operations.",
            impact="Slow first response is the leading driver of customer satisfaction decline in support contexts.",
            recommendation="Review team shift coverage and triage process; consider auto-acknowledgement messages to set response expectations.",
            metric_name="Avg Response Time", metric_value=f"{avg_response:.1f} hrs", benchmark="< 4 hrs",
        ))

    return findings, None, None, backlog_risk


def _ops_finance(calc_kpis: dict, profile: dict):
    findings = []

    margin     = _parse_kpi(calc_kpis.get("Margin", ""))
    net_profit = _parse_kpi(calc_kpis.get("Net Profit", ""))

    if margin is not None and margin < 0:
        findings.append(_op(
            title="Negative Margin — Structural Profitability Crisis",
            category="Risk",
            severity="High",
            finding="Business is operating at a loss — total expenses exceed total revenue in this period.",
            impact="Negative margin requires capital consumption to sustain operations — unsustainable without revenue growth or cost reduction.",
            recommendation="Conduct immediate cost-line-by-line review; identify variable costs reducible within 30 days while longer-term revenue strategies are developed.",
            metric_name="Margin", metric_value=f"{margin:.1f}%", benchmark="> 5%",
        ))

    return findings, None, None, None
