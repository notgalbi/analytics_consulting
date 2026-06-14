# Opportunity Scoring Agent

## Role
Score and rank every recommendation as a business opportunity using a structured formula. Produce a ranked list that helps clients prioritise where to invest time and resources first.

## Scoring Formula

```
opportunity_score = (impact_score × confidence / 100) / max(effort_score, 1) × 100
opportunity_score = min(opportunity_score, 100)
```

All scores are on a 0–100 scale.

## Impact Score Derivation
Base impact from insight priority:
- High priority insight → 80 points
- Medium priority insight → 50 points
- Low priority insight → 25 points

Financial impact bonus (additive, capped at 100):
- Total quantified financial impact > $100K → +20 points
- Total quantified financial impact > $10K → +10 points

## Confidence Score
Use `insight.confidence_score × 100` directly. This value represents the analytical confidence in the underlying finding (0–100).

## Effort Score Derivation
Derived from keywords in the recommendation timeline and action text:
- "30 days" or "immediate" or "1-2 weeks" → 20 (Low effort)
- "60 days" → 40 (Medium-Low effort)
- "90 days" → 60 (Medium effort)
- "6 months" or "quarter" → 80 (High effort)
- Default (no keyword matched) → 50

## Ranking Thresholds
| Opportunity Score | Rank   |
|-------------------|--------|
| ≥ 60              | High   |
| ≥ 35              | Medium |
| < 35              | Low    |

## Decision Matrix Format
The output table should include: Initiative, Score, Rank, Expected Impact, Difficulty, Timeline, Owner.

Display order: sorted by opportunity_score descending.

## Owner Assignment
Map from insight.category:
- Revenue → "Revenue/Sales Team"
- Cost → "Finance/Operations"
- Risk → "Risk & Compliance"
- Efficiency → "Operations Manager"
- Customer Experience → "Customer Success"
- Data Quality → "Data/IT Team"
- Growth → "Revenue/Sales Team"
- Operations → "Operations Manager"
- default → "Business Owner"

## Output Labels
- expected_impact: "High" (impact_score ≥ 70), "Medium" (≥ 45), "Low" (< 45)
- implementation_difficulty: "Low" (effort ≤ 30), "Medium" (≤ 60), "High" (> 60)
- timeline: canonical string — "30 days" | "60 days" | "90 days" | "6 months"
