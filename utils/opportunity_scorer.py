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
    domain: str = "general",
) -> list[OpportunityScore]:
    """
    Score and rank every recommendation as a business opportunity.
    Formula: weighted sum of impact (45%), confidence (35%), ease (20%).
    Returns list sorted by opportunity_score descending.
    """
    scores: list[OpportunityScore] = []

    insight_map: dict[str, Insight] = {i.title: i for i in insights}

    total_financial = (
        financial_impact.total_revenue_at_risk
        + financial_impact.total_revenue_opportunity
        + financial_impact.total_cost_savings
    )

    for rec in recommendations:
        insight = insight_map.get(rec.related_insight_title)

        # ── Impact score (0–100) ──────────────────────────────────────────────
        if insight:
            base_impact = {"High": 80.0, "Medium": 55.0, "Low": 30.0}.get(insight.priority, 55.0)
        else:
            base_impact = {"Critical": 85.0, "High": 70.0, "Medium": 50.0, "Low": 30.0}.get(rec.priority, 50.0)

        # Small uplift for quantified financial impact — bounded to avoid inflating all scores
        if total_financial > 500_000:
            base_impact = min(base_impact + 8, 100)
        elif total_financial > 50_000:
            base_impact = min(base_impact + 5, 100)
        elif total_financial > 5_000:
            base_impact = min(base_impact + 2, 100)

        impact_score = base_impact

        # ── Confidence (0–100) ────────────────────────────────────────────────
        confidence = (insight.confidence_score * 100) if insight else (rec.confidence * 100)

        # ── Effort score (0–100, higher = harder) ────────────────────────────
        effort_score = _effort_from_text(rec.timeline + " " + rec.action)
        timeline = _canonical_timeline(effort_score)

        # ── Ease score (inverse of effort, 0–100) ────────────────────────────
        ease_score = 100 - effort_score

        # ── Opportunity score — weighted sum, stays in 0–100 naturally ────────
        # Impact 45% · Confidence 35% · Ease 20%
        opportunity_score = round(
            impact_score * 0.45 + confidence * 0.35 + ease_score * 0.20,
            1,
        )

        rank = _rank(opportunity_score)
        category = insight.category if insight else "Operations"
        owner = _owner_from_category(category, domain)
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


def _owner_from_category(category: str, domain: str = "general") -> str:
    """Return a domain-specific functional owner for the given insight category."""
    domain_owners: dict[str, dict[str, str]] = {
        "healthcare": {
            "Revenue":             "Practice Manager",
            "Cost":                "Finance/Billing Manager",
            "Risk":                "Clinical Director",
            "Efficiency":          "Scheduling Coordinator",
            "Customer Experience": "Patient Experience Lead",
            "Data Quality":        "Billing/IT Team",
            "Growth":              "Practice Manager",
            "Operations":          "Scheduling Coordinator",
        },
        "saas": {
            "Revenue":             "VP of Revenue",
            "Cost":                "Finance Manager",
            "Risk":                "VP of Customer Success",
            "Efficiency":          "Product/Engineering Lead",
            "Customer Experience": "Head of Customer Success",
            "Data Quality":        "Data Engineering",
            "Growth":              "Head of Growth",
            "Operations":          "Head of Operations",
        },
        "marketing": {
            "Revenue":             "Head of Performance Marketing",
            "Cost":                "Marketing Manager",
            "Risk":                "Marketing Director",
            "Efficiency":          "Campaign Manager",
            "Customer Experience": "Brand Manager",
            "Data Quality":        "Marketing Ops",
            "Growth":              "Growth Lead",
            "Operations":          "Marketing Ops",
        },
        "retail": {
            "Revenue":             "Head of Merchandising",
            "Cost":                "Supply Chain Manager",
            "Risk":                "Inventory Manager",
            "Efficiency":          "Operations Manager",
            "Customer Experience": "Head of Retail Experience",
            "Data Quality":        "Data/IT Team",
            "Growth":              "Commercial Director",
            "Operations":          "Store Operations Manager",
        },
        "ecommerce": {
            "Revenue":             "Head of eCommerce",
            "Cost":                "Fulfilment Manager",
            "Risk":                "eCommerce Manager",
            "Efficiency":          "Operations Manager",
            "Customer Experience": "CX Manager",
            "Data Quality":        "Data/IT Team",
            "Growth":              "Growth Lead",
            "Operations":          "Fulfilment Manager",
        },
        "hr": {
            "Revenue":             "HR Director",
            "Cost":                "HR Manager",
            "Risk":                "HR Business Partner",
            "Efficiency":          "Talent Acquisition Lead",
            "Customer Experience": "Employee Experience Lead",
            "Data Quality":        "HR Operations",
            "Growth":              "HR Director",
            "Operations":          "HR Operations Manager",
        },
        "hospitality": {
            "Revenue":             "General Manager",
            "Cost":                "F&B Director",
            "Risk":                "Operations Manager",
            "Efficiency":          "Front-of-House Manager",
            "Customer Experience": "Guest Experience Manager",
            "Data Quality":        "Operations/IT",
            "Growth":              "Revenue Manager",
            "Operations":          "Operations Manager",
        },
        "real_estate": {
            "Revenue":             "Sales Director",
            "Cost":                "Office Manager",
            "Risk":                "Principal Agent",
            "Efficiency":          "Operations Manager",
            "Customer Experience": "Client Relations Lead",
            "Data Quality":        "Operations/IT",
            "Growth":              "Business Development Lead",
            "Operations":          "Operations Manager",
        },
        "operations": {
            "Revenue":             "Operations Director",
            "Cost":                "Operations Manager",
            "Risk":                "Risk & Compliance Lead",
            "Efficiency":          "Process Improvement Lead",
            "Customer Experience": "Service Delivery Manager",
            "Data Quality":        "Data/IT Team",
            "Growth":              "Operations Director",
            "Operations":          "Operations Manager",
        },
    }

    domain_map = domain_owners.get(domain, {})
    if domain_map and category in domain_map:
        return domain_map[category]

    # Generic fallback
    generic = {
        "Revenue":             "Revenue/Sales Team",
        "Cost":                "Finance/Operations",
        "Risk":                "Risk & Compliance",
        "Efficiency":          "Operations Manager",
        "Customer Experience": "Customer Success",
        "Data Quality":        "Data/IT Team",
        "Growth":              "Revenue/Sales Team",
        "Operations":          "Operations Manager",
    }
    return generic.get(category, "Business Owner")


__all__ = ["OpportunityScore", "score_opportunities"]
