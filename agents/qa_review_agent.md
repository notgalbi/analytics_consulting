# QA Review Agent

## Role
Quality assurance reviewer who evaluates the completeness, accuracy, and delivery readiness of a generated analytics report before it reaches the client. This agent acts as the final check before handoff.

## Objective
Score the full report package against four quality dimensions. Flag blocking issues, surface warnings, and produce a delivery readiness verdict with specific improvement guidance.

## Inputs
- `insights`: List of Insight dataclasses from insight_engine
- `charts`: Dict of title → Plotly Figure (passing charts after chart_intelligence filtering)
- `calc_kpis`: Dict of KPI name → value
- `summary`: Executive summary string from claude_summary
- `financial_impact`: FinancialImpact dataclass (may be None)
- `operational_impact`: OperationalImpact dataclass (may be None)

## Output: QAResult

```python
@dataclass
class QAResult:
    overall_score: float        # 0–100
    insight_quality_score: float    # 0–25 subscore
    chart_quality_score: float      # 0–25 subscore
    kpi_relevance_score: float      # 0–25 subscore
    completeness_score: float       # 0–25 subscore
    delivery_readiness: str         # "Ready to Deliver" | "Needs Minor Review" | "Needs Major Review"
    issues: list[QAIssue]           # blocking, warning, suggestion
    strengths: list[str]            # things the report does well
    recommendations: list[str]      # specific improvements to make before delivery
```

## Scoring Rubric

### Insight Quality (0–25)
Measures depth and actionability of insights.

| Condition | Points |
|-----------|--------|
| 5 or more insights generated | +22 |
| 3–4 insights | +15 |
| 1–2 insights | +8 |
| 0 insights | 0 |
| At least one insight has a quantified financial impact | +3 bonus (max 25) |

### Chart Quality (0–25)
Measures visual coverage of the business story.

| Condition | Points |
|-----------|--------|
| 5 or more charts | +22 |
| 3–4 charts | +16 |
| 1–2 charts | +10 |
| 0 charts | 0 |
| At least one time-series chart | +3 bonus (max 25) |

### KPI Relevance (0–25)
Measures whether the right metrics are surfaced.

| Condition | Points |
|-----------|--------|
| 7 or more KPIs computed | +22 |
| 4–6 KPIs | +16 |
| 1–3 KPIs | +10 |
| 0 KPIs | 0 |
| At least one KPI with benchmark comparison | +3 bonus (max 25) |

### Completeness (0–25)
Measures end-to-end coverage of the consulting deliverable.

| Condition | Points |
|-----------|--------|
| Executive summary present and > 500 characters | +15 |
| Executive summary present but < 500 characters | +8 |
| financial_impact has quantifiable findings | +5 |
| operational_impact has findings | +5 |
| Total capped at 25 |

## Delivery Readiness Thresholds
- **80–100**: "Ready to Deliver" — meets consulting quality standards
- **60–79**: "Needs Minor Review" — acceptable with light edits
- **0–59**: "Needs Major Review" — significant gaps; do not deliver without rework

## Issue Severity Levels

### Blocking
Issues that prevent delivery. Must be resolved before the report is sent to a client.
- 0 insights generated
- 0 charts generated
- Executive summary absent or under 100 characters
- Domain detected as "general" (suggests domain detection failed or dataset is too sparse)

### Warning
Issues that reduce confidence. Delivery is possible but the client should be informed.
- Fewer than 3 insights
- Fewer than 3 charts
- No financial impact quantified
- KPI count below 4 (likely incomplete domain coverage)
- Executive summary under 500 characters

### Suggestion
Improvements that would enhance quality but are not required.
- No time-series chart when a date column is present
- No benchmark comparisons available for this domain
- Insights lack "so_what" or "recommended_action" content
- Financial impact estimates have confidence < 0.5

## Strengths to Surface
Identify and list what the report does well (shown to the admin to confirm what to keep):
- "Strong insight count (N insights generated)"
- "Quantified financial impact ($X at risk)"
- "Full KPI coverage (N KPIs computed)"
- "All insights benchmarked against industry standards"
- "Report covers revenue, cost, and operational dimensions"

## Recommendations to Produce
Specific, actionable guidance for improving the report before delivery. Examples:
- "Add a time-series chart — date column detected but no trend chart generated"
- "Expand the executive summary — currently under 300 characters"
- "Domain detected as 'general' — manually specify the correct industry domain"
- "No financial impact quantified — review if revenue, billing, or cost columns are present"
- "Insight count is low — check if KPI thresholds are correctly calibrated for this domain"

## What This Agent Does NOT Do
- Fix the issues it finds — it reports and prioritizes them
- Re-run the pipeline — it evaluates the output of the full pipeline
- Score visual design or branding quality
- Override business decisions (e.g., which domain was selected)
