"""
scenario_modeler.py — Generate best/expected/worst scenarios per opportunity.

Models three financial scenarios for the top High-ranked opportunities to give
decision-makers a range of outcomes before committing resources.

Public API:
    model_scenarios(opportunities, financial_impact) -> list[ScenarioModel]
"""
from __future__ import annotations

from dataclasses import dataclass, field

from utils.opportunity_scorer import OpportunityScore
from utils.financial_impact_engine import FinancialImpact


@dataclass
class Scenario:
    name: str               # "Best Case" | "Expected Case" | "Worst Case"
    revenue_impact: float
    cost_impact: float
    efficiency_impact: str  # qualitative description
    assumptions: list[str] = field(default_factory=list)
    probability: str = ""   # "25%" | "55%" | "20%"


@dataclass
class ScenarioModel:
    initiative: str
    best_case: Scenario
    expected_case: Scenario
    worst_case: Scenario
    recommendation: str


# ── Public function ───────────────────────────────────────────────────────────

def model_scenarios(
    opportunities: list[OpportunityScore],
    financial_impact: FinancialImpact,
) -> list[ScenarioModel]:
    """
    Model 3 scenarios (best/expected/worst) for each of the top High-ranked
    opportunities (capped at 3 initiatives).
    Returns a list of ScenarioModel objects.
    """
    # Only model scenarios for High-ranked opportunities, top 3
    high_opps = [o for o in opportunities if o.rank == "High"][:3]

    if not high_opps:
        # Fall back to top 3 overall if no High-ranked ones exist
        high_opps = opportunities[:3]

    if not high_opps:
        return []

    # Resolve a base dollar amount from financial_impact
    base_amount = _resolve_base_amount(financial_impact)

    models: list[ScenarioModel] = []
    for opp in high_opps:
        model = _build_scenario_model(opp, base_amount, financial_impact)
        models.append(model)

    return models


# ── Helpers ───────────────────────────────────────────────────────────────────

def _resolve_base_amount(financial_impact: FinancialImpact) -> float:
    """Return the primary dollar base from available financial findings."""
    # Prefer the largest single quantified finding
    quantified = [f for f in financial_impact.findings if f.amount and f.amount > 0]
    if quantified:
        return max(f.amount for f in quantified)
    # Fall back to aggregates
    totals = [
        financial_impact.total_revenue_at_risk,
        financial_impact.total_revenue_opportunity,
        financial_impact.total_cost_savings,
    ]
    nonzero = [t for t in totals if t > 0]
    return max(nonzero) if nonzero else 0.0


def _build_scenario_model(
    opp: OpportunityScore,
    base_amount: float,
    financial_impact: FinancialImpact,
) -> ScenarioModel:
    """Build a ScenarioModel for a single opportunity."""
    # Scale base by the opportunity's impact score ratio (0–1)
    impact_ratio = opp.impact_score / 100.0
    confidence_ratio = opp.confidence / 100.0

    if base_amount > 0:
        # Adjust the base to this specific opportunity's relative impact
        opp_base = base_amount * impact_ratio * confidence_ratio

        best_revenue     = round(opp_base * 1.3, 2)
        expected_revenue = round(opp_base * 0.7, 2)
        worst_revenue    = round(opp_base * 0.3, 2)

        best_cost     = round(best_revenue * 0.15, 2)
        expected_cost = round(expected_revenue * 0.20, 2)
        worst_cost    = round(worst_revenue * 0.30, 2)

        best_eff     = "Significant efficiency gains — process runs at near-optimal capacity."
        expected_eff = "Moderate efficiency improvement — partial resolution within the period."
        worst_eff    = "Minimal efficiency gains — underlying issues persist, requiring further iteration."

        best_assumptions = [
            "Full team adoption within 30 days of initiative launch",
            "No external market disruptions during the implementation window",
            "All supporting data and tooling is available on day one",
        ]
        expected_assumptions = [
            "Partial adoption — 60–70% of stakeholders engaged",
            "Minor implementation delays of up to 2 weeks",
            "Conservative estimate based on industry-average execution rates",
        ]
        worst_assumptions = [
            "Low adoption or significant execution delays",
            "Competing priorities limit dedicated resource allocation",
            "Data quality or process constraints slow the initiative",
        ]
    else:
        # No dollar data — use qualitative descriptions
        best_revenue     = 0.0
        expected_revenue = 0.0
        worst_revenue    = 0.0
        best_cost        = 0.0
        expected_cost    = 0.0
        worst_cost       = 0.0

        best_eff     = "Substantial improvement — initiative achieves full intended scope."
        expected_eff = "Moderate improvement — initiative achieves 60–70% of intended scope."
        worst_eff    = "Limited improvement — initiative is partially completed or delayed."

        best_assumptions = [
            "Full resource commitment and cross-functional alignment",
            "No external constraints impeding delivery",
        ]
        expected_assumptions = [
            "Standard resource availability and typical implementation timelines",
            "Conservative assumptions based on comparable industry initiatives",
        ]
        worst_assumptions = [
            "Resource contention or competing priorities",
            "Partial implementation only within the stated timeline",
        ]

    return ScenarioModel(
        initiative=opp.initiative,
        best_case=Scenario(
            name="Best Case",
            revenue_impact=best_revenue,
            cost_impact=best_cost,
            efficiency_impact=best_eff,
            assumptions=best_assumptions,
            probability="25%",
        ),
        expected_case=Scenario(
            name="Expected Case",
            revenue_impact=expected_revenue,
            cost_impact=expected_cost,
            efficiency_impact=expected_eff,
            assumptions=expected_assumptions,
            probability="55%",
        ),
        worst_case=Scenario(
            name="Worst Case",
            revenue_impact=worst_revenue,
            cost_impact=worst_cost,
            efficiency_impact=worst_eff,
            assumptions=worst_assumptions,
            probability="20%",
        ),
        recommendation=(
            f"Pursue this initiative with a phased approach. "
            f"Assign a dedicated owner ({opp.owner}) and target completion within {opp.timeline}. "
            f"Plan for the Expected Case scenario and monitor leading indicators weekly."
        ),
    )


def _fmt(val: float) -> str:
    if val >= 1_000_000:
        return f"${val / 1_000_000:.1f}M"
    if val >= 1_000:
        return f"${val / 1_000:.0f}K"
    return f"${val:,.0f}"


__all__ = ["Scenario", "ScenarioModel", "model_scenarios"]
