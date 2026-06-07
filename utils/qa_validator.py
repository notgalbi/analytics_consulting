"""
qa_validator.py — Report quality validation and delivery readiness scoring.

Scores the generated report on insight quality, chart quality, KPI relevance,
and completeness. Returns a delivery readiness verdict and actionable feedback.

Public API:
    validate_report(insights, charts, calc_kpis, summary, financial_impact, operational_impact) -> QAResult
"""
from __future__ import annotations

from dataclasses import dataclass, field

from utils.insight_engine import Insight
from utils.financial_impact_engine import FinancialImpact
from utils.operational_impact_engine import OperationalImpact


@dataclass
class QAIssue:
    severity: str       # "blocking" | "warning" | "suggestion"
    category: str
    description: str


@dataclass
class QAResult:
    overall_score: float
    insight_quality_score: float    # 0–25
    chart_quality_score: float      # 0–25
    kpi_relevance_score: float      # 0–25
    completeness_score: float       # 0–25
    delivery_readiness: str         # "Ready to Deliver" | "Needs Minor Review" | "Needs Major Review"
    issues: list[QAIssue] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


# ── Public function ───────────────────────────────────────────────────────────

def validate_report(
    insights: list[Insight],
    charts: dict,
    calc_kpis: dict[str, str],
    summary: str,
    financial_impact: FinancialImpact,
    operational_impact: OperationalImpact,
) -> QAResult:
    """
    Score report quality and return delivery readiness verdict.
    Overall score is the sum of four 0–25 subscores.
    """
    issues: list[QAIssue] = []
    strengths: list[str] = []
    improvement_recs: list[str] = []

    # ── Insight quality (0–25) ────────────────────────────────────────────────
    insight_count = len(insights)
    if insight_count == 0:
        insight_score = 0.0
        issues.append(QAIssue("blocking", "Insights", "No insights generated — report cannot be delivered without business insights."))
    elif insight_count <= 2:
        insight_score = 10.0
        improvement_recs.append("Generate more insights: aim for at least 4 structured insights with prioritized findings.")
    elif insight_count <= 4:
        insight_score = 18.0
    else:
        insight_score = 22.0
        strengths.append(f"Strong insight depth — {insight_count} structured insights generated.")

    has_high_priority = any(i.priority == "High" for i in insights)
    if has_high_priority:
        insight_score = min(insight_score + 3, 25)

    if financial_impact.has_quantifiable_impact:
        insight_score = min(insight_score + 3, 25)
        strengths.append(f"Financial impact quantified — {_fmt_total(financial_impact)} identified.")

    # ── Chart quality (0–25) ──────────────────────────────────────────────────
    chart_count = len(charts) if charts else 0
    if chart_count == 0:
        chart_score = 0.0
        issues.append(QAIssue("blocking", "Charts", "No charts generated — visual evidence is required for client delivery."))
    elif chart_count <= 2:
        chart_score = 10.0
        improvement_recs.append("Add more charts: aim for 4–6 charts that each answer a specific business question.")
    elif chart_count <= 4:
        chart_score = 17.0
    else:
        chart_score = 22.0
        strengths.append(f"Good visual coverage — {chart_count} charts generated.")

    # Domain-specific charts are more relevant
    if chart_count > 0 and len(calc_kpis) > 0:
        chart_score = min(chart_score + 3, 25)

    # ── KPI relevance (0–25) ──────────────────────────────────────────────────
    kpi_count = len(calc_kpis)
    if kpi_count == 0:
        kpi_score = 0.0
        issues.append(QAIssue("blocking", "KPIs", "No KPIs calculated — domain detection may have failed or dataset is too sparse."))
    elif kpi_count <= 3:
        kpi_score = 10.0
        improvement_recs.append("KPI coverage is thin — consider verifying domain detection or enriching the dataset.")
    elif kpi_count <= 6:
        kpi_score = 18.0
    else:
        kpi_score = 22.0
        strengths.append(f"Comprehensive KPI coverage — {kpi_count} metrics calculated.")

    # Benchmark violations found = richer analysis
    has_violation = any(i.category in ("Revenue", "Cost", "Efficiency") for i in insights)
    if has_violation:
        kpi_score = min(kpi_score + 3, 25)

    # ── Completeness (0–25) ───────────────────────────────────────────────────
    completeness_score = 0.0

    if summary and len(summary.strip()) > 10:
        completeness_score += 10
        if len(summary) > 500:
            completeness_score += 5
            if len(summary) > 2000:
                strengths.append("Executive summary is comprehensive and detailed.")
        else:
            issues.append(QAIssue("warning", "Summary", "Executive summary is very short — expand with domain-specific analysis for client delivery."))
    else:
        issues.append(QAIssue("blocking", "Summary", "No executive summary — generate the executive summary before delivering to the client."))
        improvement_recs.append("Generate the executive summary using the 'Generate Executive Summary' button.")

    if financial_impact.findings:
        completeness_score += 5
    else:
        issues.append(QAIssue("suggestion", "Financial Impact", "No financial impact findings — consider quantifying at least one insight in dollar terms."))
        improvement_recs.append("Quantify at least one insight in dollar terms to strengthen the financial impact section.")

    if operational_impact.findings:
        completeness_score += 5

    completeness_score = min(completeness_score, 25)

    # ── Overall score & delivery readiness ────────────────────────────────────
    overall = insight_score + chart_score + kpi_score + completeness_score
    has_blocking = any(i.severity == "blocking" for i in issues)

    if has_blocking:
        readiness = "Needs Major Review"
    elif overall >= 80:
        readiness = "Ready to Deliver"
    elif overall >= 60:
        readiness = "Needs Minor Review"
    else:
        readiness = "Needs Major Review"

    return QAResult(
        overall_score=round(overall, 1),
        insight_quality_score=round(insight_score, 1),
        chart_quality_score=round(chart_score, 1),
        kpi_relevance_score=round(kpi_score, 1),
        completeness_score=round(completeness_score, 1),
        delivery_readiness=readiness,
        issues=issues,
        strengths=strengths,
        recommendations=improvement_recs,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_total(fi: FinancialImpact) -> str:
    total = fi.total_revenue_at_risk + fi.total_revenue_opportunity + fi.total_cost_savings
    if total >= 1_000_000:
        return f"${total / 1_000_000:.1f}M"
    if total >= 1_000:
        return f"${total / 1_000:.0f}K"
    return f"${total:,.0f}"


__all__ = ["QAIssue", "QAResult", "validate_report"]
