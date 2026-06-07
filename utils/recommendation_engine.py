"""
recommendation_engine.py — Structured recommendations from insights.

Translates insights into prioritized, time-bound, owner-assigned
action plans.

Public API:
    generate_recommendations(insights, domain) -> list[Recommendation]
"""
from __future__ import annotations

from dataclasses import dataclass

from utils.insight_engine import Insight


@dataclass
class Recommendation:
    action: str
    owner: str
    timeline: str
    priority: str           # "Critical" | "High" | "Medium" | "Low"
    expected_outcome: str
    estimated_benefit: str
    confidence: float
    related_insight_title: str


# ── Owner map by domain + insight category ────────────────────────────────────
_OWNERS: dict[str, dict[str, str]] = {
    "healthcare": {
        "Revenue":              "Practice Manager",
        "Efficiency":           "Operations Director",
        "Customer Experience":  "Patient Services Director",
        "Data Quality":         "Data & Systems Manager",
        "Risk":                 "Clinical Director",
        "Operations":           "Operations Manager",
        "Cost":                 "Finance Director",
        "Growth":               "Practice Manager",
    },
    "hospitality": {
        "Revenue":              "General Manager",
        "Cost":                 "Executive Chef / General Manager",
        "Efficiency":           "Operations Manager",
        "Customer Experience":  "Front-of-House Manager",
        "Risk":                 "General Manager",
        "Operations":           "Operations Manager",
        "Data Quality":         "GM / Head of Reporting",
        "Growth":               "General Manager",
    },
    "marketing": {
        "Revenue":              "Marketing Director",
        "Cost":                 "Media Manager",
        "Efficiency":           "Campaign Manager",
        "Customer Experience":  "Brand Manager",
        "Risk":                 "Marketing Director",
        "Growth":               "Growth Lead",
        "Operations":           "Marketing Ops",
        "Data Quality":         "Marketing Analytics Lead",
    },
    "saas": {
        "Revenue":              "VP Customer Success",
        "Risk":                 "VP Customer Success",
        "Growth":               "VP Product / Growth Lead",
        "Efficiency":           "Engineering / Product Manager",
        "Customer Experience":  "VP Customer Success",
        "Cost":                 "Finance Director",
        "Operations":           "VP Engineering",
        "Data Quality":         "Data Engineering Lead",
    },
    "sales": {
        "Revenue":              "Sales Director",
        "Growth":               "VP Sales",
        "Cost":                 "VP Sales / Finance",
        "Efficiency":           "Sales Operations Manager",
        "Customer Experience":  "Account Management Lead",
        "Risk":                 "VP Sales",
        "Operations":           "Sales Operations Manager",
        "Data Quality":         "Sales Ops / CRM Admin",
    },
    "retail": {
        "Revenue":              "Merchandising Manager",
        "Cost":                 "Supply Chain Manager",
        "Efficiency":           "Store / Inventory Manager",
        "Operations":           "Warehouse Manager",
        "Risk":                 "Supply Chain Director",
        "Customer Experience":  "Store Manager",
        "Growth":               "Merchandising Director",
        "Data Quality":         "Inventory Systems Manager",
    },
    "ecommerce": {
        "Revenue":              "E-commerce Director",
        "Cost":                 "Fulfillment Manager",
        "Efficiency":           "Operations Manager",
        "Customer Experience":  "CX Director",
        "Risk":                 "E-commerce Director",
        "Growth":               "Growth Marketing Lead",
        "Operations":           "Fulfillment Manager",
        "Data Quality":         "Data / Analytics Manager",
    },
    "real_estate": {
        "Revenue":              "Brokerage Manager",
        "Efficiency":           "Operations Manager",
        "Customer Experience":  "Client Services Director",
        "Risk":                 "Managing Broker",
        "Operations":           "Operations Manager",
        "Growth":               "Managing Broker",
        "Cost":                 "Finance / Operations Manager",
        "Data Quality":         "Admin / MLS Manager",
    },
    "hr": {
        "Revenue":              "CHRO",
        "Operations":           "HR Operations Manager",
        "Risk":                 "CHRO",
        "Efficiency":           "HR Manager",
        "Customer Experience":  "Employee Experience Lead",
        "Cost":                 "Compensation & Benefits Manager",
        "Growth":               "Talent Acquisition Director",
        "Data Quality":         "HRIS Manager",
    },
    "operations": {
        "Backlog":              "Operations Manager",
        "Throughput":           "VP Operations",
        "Operations":           "Operations Manager",
        "Efficiency":           "Process Improvement Lead",
        "Risk":                 "VP Operations",
        "Quality":              "Quality Assurance Manager",
        "Customer Experience":  "Customer Success Manager",
        "Data Quality":         "Operations Analyst",
    },
    "finance": {
        "Revenue":              "CFO",
        "Cost":                 "Finance Director",
        "Risk":                 "CFO",
        "Efficiency":           "Finance Operations Manager",
        "Operations":           "Finance Director",
        "Data Quality":         "Financial Controller",
        "Growth":               "CFO",
        "Customer Experience":  "Finance Director",
    },
}

_DEFAULT_OWNER = "Department Head"


# ── Timeline map by recommendation priority ───────────────────────────────────
_TIMELINES: dict[str, str] = {
    "Critical": "Immediate — within 1-2 weeks",
    "High":     "Short-term — within 30 days",
    "Medium":   "Medium-term — within 60-90 days",
    "Low":      "Long-term — within next quarter",
}


# ── Public function ───────────────────────────────────────────────────────────

def generate_recommendations(insights: list[Insight], domain: str) -> list[Recommendation]:
    """
    Translate insights into prioritized, time-bound recommendations.
    Returns at most 5 recommendations sorted by priority.
    """
    recs: list[Recommendation] = []

    for insight in insights:
        priority = _insight_to_rec_priority(insight.priority)
        owner    = _get_owner(domain, insight.category)
        timeline = _TIMELINES[priority]

        recs.append(Recommendation(
            action=_build_action(insight),
            owner=owner,
            timeline=timeline,
            priority=priority,
            expected_outcome=insight.expected_outcome,
            estimated_benefit=insight.financial_impact,
            confidence=insight.confidence_score,
            related_insight_title=insight.title,
        ))

    # Sort Critical → High → Medium → Low; cap at 5
    priority_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
    recs.sort(key=lambda r: priority_order.get(r.priority, 4))
    return recs[:5]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _insight_to_rec_priority(insight_priority: str) -> str:
    return {"High": "Critical", "Medium": "High", "Low": "Medium"}.get(insight_priority, "Medium")


def _get_owner(domain: str, category: str) -> str:
    domain_owners = _OWNERS.get(domain, {})
    return domain_owners.get(category, _DEFAULT_OWNER)


def _build_action(insight: Insight) -> str:
    """Build a specific, imperative action statement from an insight."""
    # Use recommended_action if it is already specific
    if len(insight.recommended_action) > 30 and not insight.recommended_action.startswith("Review"):
        return insight.recommended_action

    # Otherwise construct one from category
    category_actions: dict[str, str] = {
        "Revenue":             f"Launch a targeted revenue recovery initiative addressing: {insight.title.lower()}.",
        "Cost":                f"Initiate a cost reduction program targeting the margin gap identified in: {insight.title.lower()}.",
        "Risk":                f"Conduct a risk assessment and mitigation plan for: {insight.title.lower()}.",
        "Efficiency":          f"Redesign the process or workflow contributing to: {insight.title.lower()}.",
        "Customer Experience": f"Implement a customer experience improvement program to address: {insight.title.lower()}.",
        "Growth":              f"Develop and test a growth strategy to capture the opportunity in: {insight.title.lower()}.",
        "Operations":          f"Restructure the operational process driving: {insight.title.lower()}.",
        "Data Quality":        f"Investigate and remediate the data quality issue identified in: {insight.title.lower()}.",
    }
    return category_actions.get(insight.category, insight.recommended_action)


__all__ = ["Recommendation", "generate_recommendations"]
