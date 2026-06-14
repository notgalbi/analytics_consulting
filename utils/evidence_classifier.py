"""
evidence_classifier.py — Classify insight findings by evidence type.

Every insight finding is classified as one of:
  OBSERVED  — directly computable from uploaded data rows
  INFERRED  — derived from ratios or cross-KPI comparisons
  BENCHMARK — based on industry averages, not the client's own data
  HYPOTHESIS — speculative, requires validation

Public API:
    classify_evidence(insight, calc_kpis, financial_impact) -> str
"""
from __future__ import annotations

from utils.insight_engine import Insight
from utils.financial_impact_engine import FinancialImpact


# ── Public function ───────────────────────────────────────────────────────────

def classify_evidence(
    insight: Insight,
    calc_kpis: dict[str, str],
    financial_impact: FinancialImpact,
) -> str:
    """
    Classify an insight's evidence type.
    Returns one of "OBSERVED" | "INFERRED" | "BENCHMARK" | "HYPOTHESIS".
    """
    # Rule 1: Data Quality insights are always OBSERVED (computable directly from rows)
    if insight.category == "Data Quality":
        return "OBSERVED"

    # Rule 2: Low confidence → HYPOTHESIS
    if insight.confidence_score < 0.65:
        return "HYPOTHESIS"

    # Rule 3: Benchmark-named insights
    benchmark_keywords = ("Benchmark", "Below Benchmark", "Exceeds Benchmark")
    if any(kw in insight.title for kw in benchmark_keywords):
        return "BENCHMARK"

    # Rule 4: Check if a financial impact finding backs this insight
    has_dollar_amount = _has_dollar_amount(insight.financial_impact)
    has_source_kpi = _has_matching_financial_finding(insight, financial_impact)

    if has_dollar_amount and has_source_kpi:
        return "INFERRED"

    # Rule 5: Category + no dollar amount → benchmark-derived
    benchmark_categories = {"Revenue", "Cost", "Efficiency", "Customer Experience"}
    if insight.category in benchmark_categories and not has_dollar_amount:
        return "BENCHMARK"

    # Rule 6: Default for High-priority financial findings
    if insight.priority == "High" and insight.category in {"Revenue", "Cost", "Growth"}:
        return "INFERRED"

    # Default fallback
    return "OBSERVED"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _has_dollar_amount(financial_impact_str: str) -> bool:
    """Return True if the financial_impact field contains a dollar amount."""
    if not financial_impact_str:
        return False
    s = financial_impact_str.strip()
    return "$" in s and s not in ("Not quantified", "Not quantified — requires additional data")


def _has_matching_financial_finding(
    insight: Insight,
    financial_impact: FinancialImpact,
) -> bool:
    """
    Return True if the financial_impact engine produced a finding whose
    title or source_kpi is referenced in this insight.
    """
    if not financial_impact.findings:
        return False
    insight_title_lower = insight.title.lower()
    for f in financial_impact.findings:
        if f.source_kpi and f.source_kpi.lower() in insight_title_lower:
            return True
        if f.title and f.title.lower() in insight_title_lower:
            return True
        # Also match if the insight title appears in the finding title
        if insight_title_lower and f.title and insight_title_lower in f.title.lower():
            return True
    return False


__all__ = ["classify_evidence"]
