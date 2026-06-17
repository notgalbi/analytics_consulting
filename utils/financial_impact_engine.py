"""
financial_impact_engine.py — Rule-based financial impact estimation.

Estimates revenue at risk, revenue opportunity, and cost savings from
computed KPIs without requiring the Claude API.

Public API:
    estimate_financial_impact(domain, calc_kpis, profile) -> FinancialImpact
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ImpactFinding:
    title: str
    category: str        # "Revenue at Risk" | "Revenue Opportunity" | "Cost Savings" | "Capacity Recovery"
    amount: float | None
    amount_formatted: str
    description: str
    assumption: str
    confidence: float    # 0.0–1.0
    priority: str        # "High" | "Medium" | "Low"
    source_kpi: str = ""  # KPI name this finding is derived from, used for insight dedup


@dataclass
class FinancialImpact:
    domain: str
    total_revenue_at_risk: float
    total_revenue_opportunity: float
    total_cost_savings: float
    findings: list[ImpactFinding] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    has_quantifiable_impact: bool = False
    summary_statement: str = ""


# ── Public function ───────────────────────────────────────────────────────────

def estimate_financial_impact(
    domain: str,
    calc_kpis: dict[str, str],
    profile: dict,
) -> FinancialImpact:
    """Estimate financial impact from computed KPIs using domain-specific rules."""
    _calculators = {
        "healthcare":   _impact_healthcare,
        "hospitality":  _impact_hospitality,
        "restaurant":   _impact_hospitality,
        "marketing":    _impact_marketing,
        "saas":         _impact_saas,
        "sales":        _impact_sales,
        "retail":       _impact_retail,
        "ecommerce":    _impact_ecommerce,
        "real_estate":  _impact_real_estate,
        "hr":           _impact_hr,
        "operations":   _impact_operations,
        "finance":      _impact_finance,
    }

    findings: list[ImpactFinding] = []
    assumptions: list[str] = []

    calc_fn = _calculators.get(domain)
    if calc_fn:
        findings, assumptions = calc_fn(calc_kpis, profile)

    at_risk     = sum(f.amount for f in findings if f.amount and "Risk" in f.category)
    opportunity = sum(f.amount for f in findings if f.amount and "Opportunity" in f.category)
    savings     = sum(f.amount for f in findings if f.amount and "Savings" in f.category)

    return FinancialImpact(
        domain=domain,
        total_revenue_at_risk=at_risk,
        total_revenue_opportunity=opportunity,
        total_cost_savings=savings,
        findings=findings,
        assumptions=assumptions,
        has_quantifiable_impact=any(f.amount is not None and f.amount > 0 for f in findings),
        summary_statement=_build_summary(findings, at_risk, opportunity, savings),
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_kpi(value: str) -> float | None:
    """Strip formatting and return a float, or None on failure."""
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


def _fmt(val: float) -> str:
    if abs(val) >= 1_000_000:
        return f"${val / 1_000_000:.1f}M"
    if abs(val) >= 1_000:
        return f"${val / 1_000:.0f}K"
    return f"${val:,.0f}"


def _finding(
    title: str,
    category: str,
    amount: float | None,
    description: str,
    assumption: str,
    confidence: float = 0.7,
    priority: str = "Medium",
    source_kpi: str = "",
) -> ImpactFinding:
    return ImpactFinding(
        title=title,
        category=category,
        amount=amount,
        amount_formatted=_fmt(amount) if amount else "Not quantified",
        description=description,
        assumption=assumption,
        confidence=confidence,
        priority=priority,
        source_kpi=source_kpi,
    )


def _build_summary(findings: list[ImpactFinding], at_risk: float, opportunity: float, savings: float) -> str:
    if not findings:
        return "No significant financial impact estimated from available KPI data."
    parts = []
    if at_risk > 0:
        parts.append(f"{_fmt(at_risk)} revenue at risk")
    if opportunity > 0:
        parts.append(f"{_fmt(opportunity)} revenue opportunity identified")
    if savings > 0:
        parts.append(f"{_fmt(savings)} in potential cost savings")
    if parts:
        return f"Financial analysis identified: {'; '.join(parts)}."
    high = [f for f in findings if f.priority == "High"]
    if high:
        return f"{high[0].title} — financial impact not fully quantified but warrants immediate attention."
    return f"{findings[0].title} identified. Review recommendations for estimated impact."


# ── Domain calculators ────────────────────────────────────────────────────────

def _impact_healthcare(calc_kpis: dict, profile: dict) -> tuple[list[ImpactFinding], list[str]]:
    findings, assumptions = [], []
    row_count = profile.get("row_count", 0)

    no_show_rate  = _parse_kpi(calc_kpis.get("No-Show Rate", ""))
    total_billing = _parse_kpi(calc_kpis.get("Total Billing", ""))
    avg_billing   = _parse_kpi(calc_kpis.get("Avg Billing per Appt", ""))
    wait_time     = _parse_kpi(calc_kpis.get("Avg Wait Time", ""))

    if no_show_rate is not None and no_show_rate > 8:
        revenue_lost: float | None = None
        if avg_billing and row_count:
            no_show_n = no_show_rate / 100 * row_count
            revenue_lost = no_show_n * avg_billing
        elif total_billing and row_count:
            completion_rate = max(1 - no_show_rate / 100, 0.01)
            revenue_per_appt = total_billing / (completion_rate * row_count)
            no_show_n = no_show_rate / 100 * row_count
            revenue_lost = no_show_n * revenue_per_appt

        assumption = f"Revenue per completed appointment applied to no-show count at {no_show_rate:.1f}% vs 8% benchmark"
        assumptions.append(assumption)
        findings.append(_finding(
            title=f"No-Show Revenue Loss at {no_show_rate:.1f}%",
            category="Revenue at Risk",
            amount=revenue_lost,
            description=f"At {no_show_rate:.1f}% no-show rate, the practice loses billable slots that cannot be backfilled without a structured cancellation and waitlist protocol.",
            assumption=assumption,
            confidence=0.75,
            priority="High" if no_show_rate > 15 else "Medium",
            source_kpi="No-Show Rate",
        ))

    completion_rate = _parse_kpi(calc_kpis.get("Completion Rate", ""))
    if completion_rate is not None and completion_rate < 90 and avg_billing and row_count:
        gap_pct = (90 - completion_rate) / 100
        missed_slots = row_count * gap_pct
        lost_revenue = missed_slots * avg_billing
        assumption = f"Completion gap {90 - completion_rate:.1f}pp × {int(row_count)} appointments × ${avg_billing:,.0f} avg billing"
        assumptions.append(assumption)
        findings.append(_finding(
            title=f"Completion Rate {completion_rate:.0f}% — Unbilled Appointment Gap",
            category="Revenue at Risk",
            amount=lost_revenue,
            description=f"Completion rate of {completion_rate:.0f}% vs 90% benchmark means ~{int(missed_slots):,} appointment slots per period generate no billing. At ${avg_billing:,.0f} average billing, this represents a ${lost_revenue:,.0f} revenue gap that can be recovered through scheduling and follow-up improvements.",
            assumption=assumption,
            confidence=0.75,
            priority="High" if (90 - completion_rate) > 15 else "Medium",
            source_kpi="Completion Rate",
        ))

    satisfaction = _parse_kpi(calc_kpis.get("Patient Satisfaction", ""))
    if satisfaction is not None and satisfaction < 3.5 and avg_billing and row_count:
        sat_gap = 3.5 - satisfaction
        non_return_rate = min(sat_gap * 0.35, 0.25)
        at_risk_patients = row_count * non_return_rate
        lost_revenue = at_risk_patients * avg_billing * 2
        assumption = f"Satisfaction gap {sat_gap:.2f}pts × {non_return_rate:.0%} non-return rate × {int(row_count)} patients × 2 annual visits × ${avg_billing:,.0f}"
        assumptions.append(assumption)
        findings.append(_finding(
            title=f"Low Satisfaction {satisfaction:.1f}/5 — Patient Retention Risk",
            category="Revenue at Risk",
            amount=lost_revenue,
            description=f"Patient satisfaction of {satisfaction:.1f}/5 is {sat_gap:.1f} points below the 3.5 retention threshold. Patients rating below this level return at significantly lower rates, putting ~{int(at_risk_patients):,} patient relationships at risk. Lost revisit revenue estimated at ${lost_revenue:,.0f}.",
            assumption=assumption,
            confidence=0.65,
            priority="High",
            source_kpi="Patient Satisfaction",
        ))

    if wait_time is not None and wait_time > 30:
        findings.append(_finding(
            title=f"Patient Attrition Risk — {wait_time:.0f}-Minute Average Wait",
            category="Revenue at Risk",
            amount=None,
            description=f"Average wait time of {wait_time:.0f} minutes is {wait_time - 15:.0f} minutes above the 15-minute clinical standard, creating retention and referral risk.",
            assumption="Patient retention impact not quantifiable without longitudinal tracking data",
            confidence=0.6,
            priority="Medium",
            source_kpi="Avg Wait Time",
        ))

    return findings, assumptions


def _impact_hospitality(calc_kpis: dict, profile: dict) -> tuple[list[ImpactFinding], list[str]]:
    findings, assumptions = [], []
    row_count = profile.get("row_count", 0)

    food_cost_pct     = _parse_kpi(calc_kpis.get("Food Cost %", ""))
    total_revenue     = _parse_kpi(calc_kpis.get("Total Revenue", ""))
    no_show_rate      = _parse_kpi(calc_kpis.get("No-Show Rate", ""))
    avg_check         = _parse_kpi(calc_kpis.get("Avg Check Size", ""))
    avg_daily_covers  = _parse_kpi(calc_kpis.get("Avg Daily Covers", ""))

    if food_cost_pct is not None and food_cost_pct > 32 and total_revenue:
        savings = (food_cost_pct / 100 - 0.30) * total_revenue
        assumption = f"Reduction from {food_cost_pct:.1f}% to 30% benchmark food cost"
        assumptions.append(assumption)
        findings.append(_finding(
            title=f"Food Cost {food_cost_pct:.1f}% — Recoverable Margin",
            category="Cost Savings",
            amount=savings,
            description=f"Food cost running {food_cost_pct - 30:.1f} percentage points above the 30% efficient benchmark, compressing gross margin on every cover served.",
            assumption=assumption,
            confidence=0.8,
            priority="High" if food_cost_pct > 38 else "Medium",
            source_kpi="Food Cost %",
        ))

    if no_show_rate is not None and no_show_rate > 5 and avg_check and avg_daily_covers and row_count:
        est_reservations_per_day = avg_daily_covers * 0.6
        no_shows_per_day = est_reservations_per_day * (no_show_rate / 100)
        total_loss = no_shows_per_day * avg_check * row_count
        assumption = f"Reservations at 60% of covers; no-show {no_show_rate:.1f}% vs 5% benchmark; avg check ${avg_check:.2f}"
        assumptions.append(assumption)
        findings.append(_finding(
            title=f"No-Show Revenue Leakage at {no_show_rate:.1f}%",
            category="Revenue at Risk",
            amount=total_loss,
            description=f"At {no_show_rate:.1f}% no-show rate, the operation loses covers that cannot be resold without a credit card hold or confirmation protocol.",
            assumption=assumption,
            confidence=0.65,
            priority="High" if no_show_rate > 10 else "Medium",
            source_kpi="No-Show Rate",
        ))

    return findings, assumptions


def _impact_marketing(calc_kpis: dict, profile: dict) -> tuple[list[ImpactFinding], list[str]]:
    findings, assumptions = [], []

    roas            = _parse_kpi(calc_kpis.get("ROAS", ""))
    total_spend     = _parse_kpi(calc_kpis.get("Total Spend", ""))
    conversion_rate = _parse_kpi(calc_kpis.get("Conversion Rate", ""))

    if roas is not None and total_spend:
        target_roas = 5.5
        if roas < 4.0:
            opportunity = (4.0 - roas) * total_spend
            assumption = f"4x ROAS as minimum viable target; current ROAS {roas:.2f}x"
            assumptions.append(assumption)
            findings.append(_finding(
                title=f"ROAS {roas:.2f}x Below 4x Target",
                category="Revenue Opportunity",
                amount=opportunity,
                description=f"Every $1 in spend generates ${roas:.2f} in revenue vs the $4.00 target — closing this gap is pure revenue expansion at the same budget level.",
                assumption=assumption,
                confidence=0.7,
                priority="High" if roas < 2.0 else "Medium",
                source_kpi="ROAS",
            ))
        elif roas < target_roas:
            opportunity = (target_roas - roas) * total_spend
            assumption = f"5.5x ROAS as optimisation target; current ROAS {roas:.2f}x"
            assumptions.append(assumption)
            findings.append(_finding(
                title=f"ROAS {roas:.2f}x — Optimisation Opportunity to {target_roas}x",
                category="Revenue Opportunity",
                amount=opportunity,
                description=f"ROAS of {roas:.2f}x exceeds the 4x floor but sits below the {target_roas}x top-quartile target. Budget reallocation from low-converting campaign-days to top-performers closes this gap.",
                assumption=assumption,
                confidence=0.6,
                priority="Medium",
                source_kpi="ROAS",
            ))

    if conversion_rate is not None and conversion_rate < 5.0 and total_spend:
        total_revenue = _parse_kpi(calc_kpis.get("Total Revenue", ""))
        if total_revenue:
            revenue_per_pct_point = total_revenue / conversion_rate
            gap = 5.0 - conversion_rate
            opportunity = gap * revenue_per_pct_point * 0.5
            assumption = f"5% conversion rate as top-performer target; each point worth ~${revenue_per_pct_point:,.0f} in revenue"
            assumptions.append(assumption)
            findings.append(_finding(
                title=f"Conversion Rate {conversion_rate:.1f}% Below 5% Top-Performer Benchmark",
                category="Revenue Opportunity",
                amount=opportunity,
                description=f"Conversion rate of {conversion_rate:.1f}% leaves revenue on the table. Top-performing campaigns achieve 5%+. Closing half the gap through landing page and audience optimisation recovers material revenue.",
                assumption=assumption,
                confidence=0.6,
                priority="High" if conversion_rate < 2.0 else "Medium",
                source_kpi="Conversion Rate",
            ))

    return findings, assumptions


def _impact_saas(calc_kpis: dict, profile: dict) -> tuple[list[ImpactFinding], list[str]]:
    findings, assumptions = [], []

    churn_rate = _parse_kpi(calc_kpis.get("Churn Rate", ""))
    total_mrr  = _parse_kpi(calc_kpis.get("Total MRR", ""))
    nps        = _parse_kpi(calc_kpis.get("Avg NPS Score", ""))

    if churn_rate is not None and churn_rate > 2 and total_mrr:
        excess_churn = churn_rate / 100 - 0.02
        revenue_at_risk = excess_churn * total_mrr * 12
        assumption = f"Excess churn above 2% monthly benchmark applied to {_fmt(total_mrr)}/month MRR"
        assumptions.append(assumption)
        findings.append(_finding(
            title=f"Churn {churn_rate:.1f}% — Annual Revenue at Risk",
            category="Revenue at Risk",
            amount=revenue_at_risk,
            description=f"Monthly churn of {churn_rate:.1f}% vs the 2% SaaS benchmark represents compounding revenue erosion — the gap widens every month without intervention.",
            assumption=assumption,
            confidence=0.8,
            priority="High" if churn_rate > 5 else "Medium",
            source_kpi="Churn Rate",
        ))

    if nps is not None and nps < 5:
        findings.append(_finding(
            title=f"NPS {nps:.1f} — Product-Market Fit Risk",
            category="Revenue at Risk",
            amount=None,
            description=f"NPS of {nps:.1f} is below the 5.0 passive/promoter threshold, signaling that expansion revenue and referral growth are not reliably available.",
            assumption="Revenue impact not quantifiable without expansion/contraction MRR data",
            confidence=0.65,
            priority="High" if nps < 3 else "Medium",
            source_kpi="Avg NPS Score",
        ))

    return findings, assumptions


def _impact_sales(calc_kpis: dict, profile: dict) -> tuple[list[ImpactFinding], list[str]]:
    findings, assumptions = [], []

    avg_discount  = _parse_kpi(calc_kpis.get("Avg Discount", ""))
    total_revenue = _parse_kpi(calc_kpis.get("Total Revenue", ""))
    mom_growth    = _parse_kpi(calc_kpis.get("MoM Revenue Growth", ""))

    if avg_discount is not None and avg_discount > 15 and total_revenue:
        opportunity = (avg_discount / 100 - 0.10) * total_revenue
        assumption = f"Reduction from {avg_discount:.1f}% to 10% average discount benchmark"
        assumptions.append(assumption)
        findings.append(_finding(
            title=f"Avg Discount {avg_discount:.1f}% — Revenue Recovery Opportunity",
            category="Revenue Opportunity",
            amount=opportunity,
            description=f"Average discount of {avg_discount:.1f}% exceeds the 10% pricing discipline benchmark — closing this gap recovers margin without requiring additional volume.",
            assumption=assumption,
            confidence=0.75,
            priority="High" if avg_discount > 25 else "Medium",
            source_kpi="Avg Discount",
        ))

    if mom_growth is not None and mom_growth < 0:
        findings.append(_finding(
            title=f"Revenue Declining {abs(mom_growth):.1f}% MoM",
            category="Revenue at Risk",
            amount=None,
            description=f"Month-over-month revenue contraction of {abs(mom_growth):.1f}% signals a demand or execution problem requiring immediate commercial review.",
            assumption="Run-rate impact depends on trajectory — requires multi-month trend analysis",
            confidence=0.8,
            priority="High",
            source_kpi="MoM Revenue Growth",
        ))

    return findings, assumptions


def _impact_retail(calc_kpis: dict, profile: dict) -> tuple[list[ImpactFinding], list[str]]:
    findings, assumptions = [], []

    stockout_rate   = _parse_kpi(calc_kpis.get("Stockout Rate", ""))
    est_30d_revenue = _parse_kpi(calc_kpis.get("Est. 30d Revenue", ""))
    avg_margin      = _parse_kpi(calc_kpis.get("Avg Gross Margin", ""))

    if stockout_rate is not None and stockout_rate > 5 and est_30d_revenue:
        lost_sales = (stockout_rate / 100) * est_30d_revenue
        assumption = f"Stockout rate {stockout_rate:.1f}% applied to estimated 30-day revenue"
        assumptions.append(assumption)
        findings.append(_finding(
            title=f"Stockout Rate {stockout_rate:.1f}% — Lost Sales",
            category="Revenue at Risk",
            amount=lost_sales,
            description=f"{stockout_rate:.1f}% of SKUs at or below reorder point — active stockouts are turning away buyers and pushing revenue to competitors.",
            assumption=assumption,
            confidence=0.7,
            priority="High" if stockout_rate > 10 else "Medium",
            source_kpi="Stockout Rate",
        ))

    if avg_margin is not None and avg_margin < 30:
        findings.append(_finding(
            title=f"Gross Margin {avg_margin:.1f}% Below 30% Floor",
            category="Cost Savings",
            amount=None,
            description=f"Average gross margin of {avg_margin:.1f}% falls below the 30% retail floor, indicating pricing, product mix, or cost structure problems.",
            assumption="Full dollar impact requires product-level P&L not available in this dataset",
            confidence=0.7,
            priority="High",
            source_kpi="Avg Gross Margin",
        ))

    days_cover     = _parse_kpi(calc_kpis.get("Avg Days Cover", ""))
    inv_value      = _parse_kpi(calc_kpis.get("Inventory Value", ""))
    if days_cover is not None and days_cover > 60 and inv_value:
        excess_days = days_cover - 60
        # Industry standard carrying cost: 20–25% of inventory value per year
        # (storage, insurance, obsolescence, opportunity cost)
        carrying_cost_annual_rate = 0.22
        carrying_cost = inv_value * carrying_cost_annual_rate * (excess_days / 365)
        assumption = (
            f"Excess {excess_days:.0f} days of cover above 60-day target × "
            f"${inv_value:,.0f} inventory value × 22% annual carrying cost rate "
            f"(NRF: storage, insurance, obsolescence, opportunity cost)"
        )
        assumptions.append(assumption)
        findings.append(_finding(
            title=f"Overstock {days_cover:.0f}-Day Cover — Carrying Cost Exposure",
            category="Cost Savings",
            amount=carrying_cost,
            description=(
                f"Average days cover of {days_cover:.0f} days is {excess_days:.0f} days above "
                f"the 60-day upper target, tying up ${inv_value / 1_000_000:.1f}M in inventory "
                f"value beyond what sell-through supports. At a 22% annual carrying cost rate "
                f"(NRF benchmark: storage, insurance, obsolescence, opportunity cost), the excess "
                f"stock generates {_fmt(carrying_cost)} in avoidable holding costs."
            ),
            assumption=assumption,
            confidence=0.70,
            priority="High" if excess_days > 60 else "Medium",
            source_kpi="Avg Days Cover",
        ))

    return findings, assumptions


def _impact_ecommerce(calc_kpis: dict, profile: dict) -> tuple[list[ImpactFinding], list[str]]:
    findings, assumptions = [], []

    return_rate    = _parse_kpi(calc_kpis.get("Return Rate", ""))
    total_revenue  = _parse_kpi(calc_kpis.get("Total Revenue", ""))
    avg_days_ship  = _parse_kpi(calc_kpis.get("Avg Days to Ship", ""))

    if return_rate is not None and return_rate > 10 and total_revenue:
        net_loss = (return_rate / 100 - 0.10) * total_revenue * 0.7
        assumption = "Net return cost at 70% of item value (handling + restocking + margin loss); excess above 10% benchmark"
        assumptions.append(assumption)
        findings.append(_finding(
            title=f"Return Rate {return_rate:.1f}% — Net Revenue Impact",
            category="Revenue at Risk",
            amount=net_loss,
            description=f"Return rate of {return_rate:.1f}% exceeds the 10% benchmark, incurring handling, restocking, and margin costs on every returned order.",
            assumption=assumption,
            confidence=0.75,
            priority="High" if return_rate > 20 else "Medium",
            source_kpi="Return Rate",
        ))

    if avg_days_ship is not None and avg_days_ship > 3 and total_revenue:
        days_over = avg_days_ship - 3
        repeat_risk = total_revenue * 0.03 * days_over
        assumption = "3% repeat-purchase risk per day above 3-day benchmark (industry churn proxy)"
        assumptions.append(assumption)
        findings.append(_finding(
            title=f"Fulfillment Lead Time {avg_days_ship:.1f} Days — Repeat Purchase Risk",
            category="Revenue at Risk",
            amount=repeat_risk,
            description=f"Shipping time of {avg_days_ship:.1f} days exceeds the 3-day customer expectation by {days_over:.1f} days, increasing repeat-purchase churn risk.",
            assumption=assumption,
            confidence=0.65,
            priority="High" if avg_days_ship > 7 else "Medium",
            source_kpi="Avg Days to Ship",
        ))

    return findings, assumptions


def _impact_real_estate(calc_kpis: dict, profile: dict) -> tuple[list[ImpactFinding], list[str]]:
    findings, assumptions = [], []

    dom              = _parse_kpi(calc_kpis.get("Avg Days on Market", ""))
    avg_sale_price   = _parse_kpi(calc_kpis.get("Avg Sale Price", ""))
    median_sale_price= _parse_kpi(calc_kpis.get("Median Sale Price", ""))
    total_listings   = _parse_kpi(calc_kpis.get("Total Listings", ""))
    sale_rate        = _parse_kpi(calc_kpis.get("Sale Rate", ""))
    list_to_sale     = _parse_kpi(calc_kpis.get("List-to-Sale Ratio", ""))

    if dom is not None and dom > 30 and avg_sale_price and total_listings:
        carrying_cost = (dom - 30) * total_listings * avg_sale_price * 0.0003
        assumption = "Carrying cost at 0.03% per day per listing above 30-day hot-market benchmark"
        assumptions.append(assumption)
        findings.append(_finding(
            title=f"Avg DOM {dom:.0f} Days — Seller Carrying Cost",
            category="Revenue at Risk",
            amount=carrying_cost,
            description=f"Properties averaging {dom:.0f} days on market incur {dom - 30:.0f} extra days of carrying cost above the 30-day hot-market benchmark, signalling pricing or marketing execution gaps.",
            assumption=assumption,
            confidence=0.65,
            priority="High" if dom > 60 else "Medium",
            source_kpi="Avg Days on Market",
        ))

    # Fires for any sale rate below 92% — the 8%+ unconverted listing rate
    # represents a real commission revenue gap, not just a benchmark miss.
    if sale_rate is not None and sale_rate < 92 and avg_sale_price and total_listings:
        commission_rate = 0.03  # standard 3% agency side
        unsold_count = (1 - sale_rate / 100) * total_listings
        commission_gap = unsold_count * avg_sale_price * commission_rate
        assumption = (
            f"{unsold_count:.0f} unconverted listings × ${avg_sale_price:,.0f} avg price "
            f"× 3% agency commission rate"
        )
        assumptions.append(assumption)
        findings.append(_finding(
            title=f"Listing Conversion Gap — {unsold_count:.0f} Unsold Properties",
            category="Revenue Opportunity",
            amount=commission_gap,
            description=(
                f"Sale rate of {sale_rate:.1f}% means {unsold_count:.0f} of {total_listings:.0f} listings "
                f"did not close, representing {_fmt(commission_gap)} in uncaptured commission revenue. "
                f"Pricing audits on stale listings, professional staging, and expanded buyer outreach "
                f"are the highest-leverage interventions to close this gap."
            ),
            assumption=assumption,
            confidence=0.65,
            priority="High" if sale_rate < 80 else "Medium",
            source_kpi="Sale Rate",
        ))

    # Price distribution skew: avg materially above median signals premium-tier
    # concentration — those properties typically take longer to sell, inflating DOM
    # and carrying costs beyond what the average alone reveals.
    if (avg_sale_price and median_sale_price and total_listings and dom
            and avg_sale_price > median_sale_price * 1.04):
        spread_pct = (avg_sale_price - median_sale_price) / median_sale_price * 100
        # Premium tier (est. top 25%) likely has ~50% longer DOM than the median listing
        premium_count = total_listings * 0.25
        premium_avg = avg_sale_price + (avg_sale_price - median_sale_price)
        extra_dom = dom * 0.5  # premium properties typically take 50% longer
        premium_carrying = premium_count * premium_avg * 0.0003 * extra_dom
        assumption = (
            f"Top 25% of listings (~{premium_count:.0f} properties) estimated at "
            f"${premium_avg:,.0f} avg price taking {extra_dom:.0f} extra days to sell "
            f"at 0.03% daily carrying cost (NAR liquidity model)"
        )
        assumptions.append(assumption)
        findings.append(_finding(
            title=f"Price Distribution Skew — Premium Tier Liquidity Risk",
            category="Revenue at Risk",
            amount=premium_carrying,
            description=(
                f"Avg sale price of {_fmt(avg_sale_price)} is {spread_pct:.1f}% above the "
                f"{_fmt(median_sale_price)} median, indicating a right-skewed portfolio where "
                f"premium properties are pulling the average up. Premium listings typically take "
                f"30–50% longer to sell than median-priced properties, compounding DOM and "
                f"carrying costs across the top tier of the book."
            ),
            assumption=assumption,
            confidence=0.60,
            priority="Medium",
            source_kpi="Avg Sale Price",
        ))

    return findings, assumptions


def _impact_hr(calc_kpis: dict, profile: dict) -> tuple[list[ImpactFinding], list[str]]:
    findings, assumptions = [], []

    attrition_rate = _parse_kpi(calc_kpis.get("Attrition Rate", ""))
    avg_salary     = _parse_kpi(calc_kpis.get("Avg Salary", ""))
    headcount      = _parse_kpi(calc_kpis.get("Headcount", ""))

    if attrition_rate is not None and attrition_rate > 10 and avg_salary and headcount:
        excess_rate = (attrition_rate - 10) / 100
        headcount_at_risk = excess_rate * headcount
        replacement_cost = headcount_at_risk * avg_salary * 0.5
        assumption = "Replacement cost at 50% of annual salary per departed employee (industry standard)"
        assumptions.append(assumption)
        findings.append(_finding(
            title=f"Excess Attrition Cost at {attrition_rate:.1f}% Rate",
            category="Cost Savings",
            amount=replacement_cost,
            description=f"Attrition of {attrition_rate:.1f}% vs 10% benchmark means ~{headcount_at_risk:.0f} excess departures annually, each carrying recruitment, onboarding, and ramp costs.",
            assumption=assumption,
            confidence=0.75,
            priority="High" if attrition_rate > 20 else "Medium",
            source_kpi="Attrition Rate",
        ))

    return findings, assumptions


def _impact_operations(calc_kpis: dict, profile: dict) -> tuple[list[ImpactFinding], list[str]]:
    findings, assumptions = [], []

    open_tickets    = _parse_kpi(calc_kpis.get("Open Tickets", ""))
    total_tickets   = _parse_kpi(calc_kpis.get("Total Tickets", ""))
    avg_resolution  = _parse_kpi(calc_kpis.get("Avg Resolution Time", ""))

    if open_tickets and total_tickets and total_tickets > 0:
        backlog_pct = open_tickets / total_tickets * 100
        if backlog_pct > 20:
            findings.append(_finding(
                title=f"Backlog at {backlog_pct:.0f}% of Total Volume",
                category="Revenue at Risk",
                amount=None,
                description=f"{open_tickets:.0f} open tickets ({backlog_pct:.0f}% of total) represent unresolved work impacting SLA compliance and customer satisfaction.",
                assumption="Dollar impact requires per-ticket revenue or SLA penalty contract data",
                confidence=0.7,
                priority="High" if backlog_pct > 40 else "Medium",
                source_kpi="Open Tickets",
            ))

    if avg_resolution is not None and avg_resolution > 48:
        findings.append(_finding(
            title=f"Resolution Time {avg_resolution:.0f}hrs — SLA Breach Risk",
            category="Revenue at Risk",
            amount=None,
            description=f"Average resolution time of {avg_resolution:.0f} hours likely breaches 24-48 hour SLA commitments, creating penalty exposure and churn risk.",
            assumption="Penalty amounts not calculable without contract terms data",
            confidence=0.65,
            priority="High" if avg_resolution > 96 else "Medium",
            source_kpi="Avg Resolution Time",
        ))

    return findings, assumptions


def _impact_finance(calc_kpis: dict, profile: dict) -> tuple[list[ImpactFinding], list[str]]:
    findings, assumptions = [], []

    margin     = _parse_kpi(calc_kpis.get("Margin", ""))
    net_profit = _parse_kpi(calc_kpis.get("Net Profit", ""))

    if margin is not None and margin < 0:
        findings.append(_finding(
            title="Negative Net Margin — Structural Profitability Problem",
            category="Revenue at Risk",
            amount=abs(net_profit) if net_profit and net_profit < 0 else None,
            description="Negative profit margin indicates expenses exceed revenue — the business is consuming capital with each period of operation.",
            assumption="Net profit calculated from revenue minus recorded expenses in this dataset",
            confidence=0.85,
            priority="High",
        ))
    elif margin is not None and 0 <= margin < 5:
        findings.append(_finding(
            title=f"Thin Margin at {margin:.1f}% — Structural Fragility",
            category="Revenue Opportunity",
            amount=None,
            description=f"Net margin of {margin:.1f}% leaves minimal buffer against cost increases or revenue disruptions.",
            assumption="Industry margin benchmarks vary — compare against sector-specific target",
            confidence=0.7,
            priority="Medium",
        ))

    return findings, assumptions
