"""
opportunity_scorer.py — Score every recommendation by business opportunity.

Produces a ranked list of OpportunityScore objects combining impact, confidence,
and effort into a single prioritised score for executive decision-making.

Public API:
    score_opportunities(insights, recommendations, financial_impact) -> list[OpportunityScore]
"""
from __future__ import annotations

from dataclasses import dataclass

from utils.insight_engine import Insight
from utils.recommendation_engine import Recommendation
from utils.financial_impact_engine import FinancialImpact


@dataclass
class OpportunityScore:
    initiative: str
    impact_score: float           # 0–100
    confidence: float             # 0–100
    effort_score: float           # 0–100 (higher = harder)
    opportunity_score: float      # (impact * confidence / 100) / effort * 100, capped at 100
    rank: str                     # "High" | "Medium" | "Low"
    expected_impact: str          # "High" | "Medium" | "Low"
    implementation_difficulty: str  # "Low" | "Medium" | "High"
    owner: str                    # suggested function owner
    timeline: str                 # "30 days" | "60 days" | "90 days" | "6 months"


# ── Public function ───────────────────────────────────────────────────────────

def score_opportunities(
    insights: list[Insight],
    recommendations: list[Recommendation],
    financial_impact: FinancialImpact,
) -> list[OpportunityScore]:
    """
    Score and rank every recommendation as a business opportunity.
    Returns list sorted by opportunity_score descending.
    """
    scores: list[OpportunityScore] = []

    # Build a lookup: insight title → insight
    insight_map: dict[str, Insight] = {i.title: i for i in insights}

    # Compute the total quantifiable financial impact for the threshold check
    total_financial = (
        financial_impact.total_revenue_at_risk
        + financial_impact.total_revenue_opportunity
        + financial_impact.total_cost_savings
    )

    for rec in recommendations:
        # Resolve the linked insight (if any)
        insight = insight_map.get(rec.related_insight_title)

        # ── Impact score ─────────────────────────────────────────────────────
        if insight:
            base_impact = {"High": 80.0, "Medium": 50.0, "Low": 25.0}.get(insight.priority, 50.0)
        else:
            base_impact = {"Critical": 80.0, "High": 65.0, "Medium": 50.0, "Low": 25.0}.get(rec.priority, 50.0)

        # Bonus for large financial impact
        if total_financial > 100_000:
            base_impact = min(base_impact + 20, 100)
        elif total_financial > 10_000:
            base_impact = min(base_impact + 10, 100)

        impact_score = base_impact

        # ── Confidence ───────────────────────────────────────────────────────
        confidence = (insight.confidence_score * 100) if insight else (rec.confidence * 100)

        # ── Effort score (derived from timeline keywords) ─────────────────────
        effort_score = _effort_from_text(rec.timeline + " " + rec.action)
        timeline = _canonical_timeline(effort_score)

        # ── Opportunity score ─────────────────────────────────────────────────
        raw_opp = (impact_score * confidence / 100) / max(effort_score, 1) * 100
        opportunity_score = min(round(raw_opp, 1), 100.0)

        # ── Rank ──────────────────────────────────────────────────────────────
        rank = _rank(opportunity_score)

        # ── Owner ─────────────────────────────────────────────────────────────
        category = insight.category if insight else "Operations"
        owner = _owner_from_category(category)

        # ── Labels ───────────────────────────────────────────────────────────
        expected_impact = _expected_impact(impact_score)
        difficulty = _difficulty(effort_score)

        scores.append(OpportunityScore(
            initiative=rec.action,
            impact_score=round(impact_score, 1),
            confidence=round(confidence, 1),
            effort_score=round(effort_score, 1),
            opportunity_score=opportunity_score,
            rank=rank,
            expected_impact=expected_impact,
            implementation_difficulty=difficulty,
            owner=owner,
            timeline=timeline,
        ))

    scores.sort(key=lambda s: s.opportunity_score, reverse=True)
    return scores


# ── Helpers ───────────────────────────────────────────────────────────────────

def _effort_from_text(text: str) -> float:
    """Map timeline/action keywords to an effort score (0–100, higher = harder)."""
    text_lower = text.lower()
    if "6 month" in text_lower or "6-month" in text_lower or "quarter" in text_lower:
        return 80.0
    if "90 day" in text_lower or "90-day" in text_lower:
        return 60.0
    if "60 day" in text_lower or "60-day" in text_lower:
        return 40.0
    if "30 day" in text_lower or "30-day" in text_lower or "immediate" in text_lower or "1-2 week" in text_lower:
        return 20.0
    return 50.0


def _canonical_timeline(effort_score: float) -> str:
    """Convert an effort score back to a canonical timeline string."""
    if effort_score <= 20:
        return "30 days"
    if effort_score <= 40:
        return "60 days"
    if effort_score <= 60:
        return "90 days"
    return "6 months"


def _rank(score: float) -> str:
    if score >= 60:
        return "High"
    if score >= 35:
        return "Medium"
    return "Low"


def _expected_impact(impact_score: float) -> str:
    if impact_score >= 70:
        return "High"
    if impact_score >= 45:
        return "Medium"
    return "Low"


def _difficulty(effort_score: float) -> str:
    if effort_score <= 30:
        return "Low"
    if effort_score <= 60:
        return "Medium"
    return "High"


def _owner_from_category(category: str) -> str:
    mapping = {
        "Revenue":              "Revenue/Sales Team",
        "Cost":                 "Finance/Operations",
        "Risk":                 "Risk & Compliance",
        "Efficiency":           "Operations Manager",
        "Customer Experience":  "Customer Success",
        "Data Quality":         "Data/IT Team",
        "Growth":               "Revenue/Sales Team",
        "Operations":           "Operations Manager",
    }
    return mapping.get(category, "Business Owner")


__all__ = ["OpportunityScore", "score_opportunities"]
