# System Architecture

## Core Philosophy

> Data → Information → Insight → Recommendation → Decision

This platform never stops at descriptive. Every chart answers a business question. Every KPI is benchmarked. Every finding is connected to a financial or operational consequence. Every recommendation has an owner and a timeline.

Charts are not the product. Business decisions are the product.

---

## Pipeline Overview

```
Upload CSV
    │
    ▼
[1] Data Intake          — Load, validate, detect delimiter/encoding
    │
    ▼
[2] PII Scan             — Flag and redact columns matching PII patterns
    │
    ▼
[3] Data Profiling       — Row count, column types, missing %, cardinality, outliers
    │
    ▼
[4] Domain Detection     — Classify industry domain from column names and distributions
    │
    ▼
[5] Semantic Layer       — Load industry templates (objectives, KPIs, risk indicators)
    │
    ▼
[6] KPI Engine           — Compute domain-specific KPIs and apply benchmark comparisons
    │
    ▼
[7] Benchmark Engine     — Compare KPIs against industry thresholds (good/warn/critical)
    │
    ▼
[8] Chart Intelligence   — Score and select charts; assign business questions and priorities
    │
    ▼
[9] Financial Impact Engine  — Estimate revenue at risk, opportunity, and cost savings
    │
    ▼
[10] Operational Impact Engine — Assess capacity, throughput, backlog, and efficiency gaps
    │
    ▼
[11] Insight Engine      — Generate ranked insights with so_what, impact, and actions
    │
    ▼
[12] Recommendation Engine — Assign owners, timelines, and expected outcomes
    │
    ▼
[13] Executive Summary   — Claude-powered narrative synthesis (6000 token budget)
    │
    ▼
[14] PDF Generator       — Branded PDF export with KPIs, charts, insights, recommendations
    │
    ▼
[15] QA Validator        — Score report completeness and delivery readiness (0–100)
    │
    ▼
[16] Delivery            — Dashboard display + PDF download + optional Drive upload
```

---

## Module Inventory

### Core Pipeline (utils/)

| Module | Role | Public API |
|--------|------|------------|
| `data_loader.py` | Load and validate CSV uploads | `load_dataframe()` |
| `pii_scanner.py` | Detect and redact PII columns | `scan_for_pii()`, `redact_pii()` |
| `data_profiler.py` | Statistical profiling of all columns | `profile_dataframe()` |
| `domain_detector.py` | Classify industry domain | `detect_domain()`, `detect_domain_with_confidence()` |
| `semantic_layer.py` | Load industry context templates | `get_industry_context()`, `list_supported_domains()` |
| `kpi_engine.py` | Compute domain KPIs | `calculate_kpis()`, `get_kpi_benchmark_status()` |
| `benchmark_engine.py` | Apply benchmark thresholds | `compare_to_benchmark()`, `get_benchmark_violations()` |
| `chart_generator.py` | Generate Plotly figures | `generate_dashboard_charts()` |
| `chart_intelligence.py` | Score and select charts | `score_and_select_charts()`, `get_chart_metadata()` |
| `financial_impact_engine.py` | Rule-based financial estimates | `estimate_financial_impact()` |
| `operational_impact_engine.py` | Rule-based operational assessment | `estimate_operational_impact()` |
| `insight_engine.py` | Generate structured insights | `generate_insights()` |
| `recommendation_engine.py` | Generate prioritized recommendations | `generate_recommendations()` |
| `executive_summary.py` | Claude-powered narrative | `generate_summary()`, `stream_summary()` |
| `pdf_generator.py` | PDF report export | `generate_pdf()` |
| `qa_validator.py` | Validate report completeness | `validate_report()` |
| `kpi_detector.py` | Domain KPI definitions and benchmarks | (used by kpi_engine) |
| `claude_summary.py` | Claude API wrapper | (used by executive_summary) |
| `drive_uploader.py` | Google Drive export | `upload_to_drive()` |

### Agent Specifications (agents/)

| File | Role |
|------|------|
| `analytics_consultant_agent.md` | Defines the prompt, behavioral rules, and domain expertise for Claude's executive summary generation |
| `chart_intelligence_agent.md` | Defines chart scoring logic, selection rules, and business question mapping |
| `qa_review_agent.md` | Defines QA scoring rubric, issue severity levels, and delivery readiness thresholds |

### Configuration (config/)

| File | Contents |
|------|----------|
| `industry_templates.yaml` | 23 industry templates with executive_objectives, critical_kpis, value_drivers, risk_indicators, recommended_actions, financial_levers |
| `benchmark_rules.yaml` | Numeric benchmarks (good/warn/critical) for KPIs across 11 domains |
| `chart_rules.yaml` | Chart type rules, scoring criteria, quality gates, and PII/ID skip patterns |

---

## Data Flow: Key Objects

### `DataProfile` (data_profiler)
```python
{
  "row_count": int,
  "column_count": int,
  "columns": {
    "col_name": {
      "dtype": str,
      "missing_pct": float,
      "unique_count": int,
      "sample_values": list,
      "mean": float | None,
      "std": float | None,
      "min": float | None,
      "max": float | None,
    }
  },
  "date_columns": list[str],
  "numeric_columns": list[str],
  "categorical_columns": list[str],
}
```

### `ChartSpec` (chart_intelligence)
```python
{
  "chart_id": str,        # 8-char UUID prefix
  "chart_type": str,      # line | bar | scatter | box | histogram | indicator
  "title": str,
  "description": str,     # one sentence + business question
  "business_question": str,
  "x_column": str,
  "y_column": str,
  "aggregation": str,     # sum | mean | count | none
  "score": int,           # 0–100
  "include_in_pdf": bool, # score >= 70
  "include_in_dashboard": bool,  # score >= 60
  "priority": int,        # 1 = highest
}
```

### `FinancialImpact` (financial_impact_engine)
```python
{
  "domain": str,
  "total_revenue_at_risk": float,
  "total_revenue_opportunity": float,
  "total_cost_savings": float,
  "findings": [ImpactFinding],
  "has_quantifiable_impact": bool,
  "summary_statement": str,
}
```

### `OperationalImpact` (operational_impact_engine)
```python
{
  "domain": str,
  "capacity_utilization_pct": float | None,
  "throughput_gap_description": str | None,
  "backlog_risk_level": str | None,  # "High" | "Medium" | "Low" | None
  "findings": [OperationalFinding],
  "summary_statement": str,
}
```

### `Insight` (insight_engine)
```python
{
  "title": str,
  "priority": str,          # High | Medium | Low
  "category": str,          # Revenue | Cost | Risk | Efficiency | ...
  "finding": str,           # What the data shows
  "so_what": str,           # Why it matters to the business
  "business_impact": str,   # Operational or strategic consequence
  "financial_impact": str,  # Dollar figure or directional estimate
  "recommended_action": str,
  "expected_outcome": str,
  "confidence_score": float,
  "supporting_evidence": list[str],
}
```

### `Recommendation` (recommendation_engine)
```python
{
  "action": str,
  "owner": str,
  "timeline": str,
  "priority": str,          # Critical | High | Medium | Low
  "expected_outcome": str,
  "estimated_benefit": str,
  "confidence": float,
  "related_insight_title": str,
}
```

### `QAResult` (qa_validator)
```python
{
  "overall_score": float,           # 0–100
  "insight_quality_score": float,   # 0–25
  "chart_quality_score": float,     # 0–25
  "kpi_relevance_score": float,     # 0–25
  "completeness_score": float,      # 0–25
  "delivery_readiness": str,        # Ready to Deliver | Needs Minor Review | Needs Major Review
  "issues": [QAIssue],
  "strengths": list[str],
  "recommendations": list[str],
}
```

---

## App Layer (app.py)

### Session State Keys
```python
st.session_state["df"]                  # Raw DataFrame after load
st.session_state["profile"]             # DataProfile dict
st.session_state["domain"]              # Detected domain string
st.session_state["industry_context"]    # Semantic layer context dict
st.session_state["calc_kpis"]           # Computed KPI dict
st.session_state["benchmark_status"]    # Benchmark comparison dict
st.session_state["chart_specs"]         # list[ChartSpec]
st.session_state["figures"]             # dict[title, Figure]
st.session_state["financial_impact"]    # FinancialImpact
st.session_state["operational_impact"]  # OperationalImpact
st.session_state["insights"]            # list[Insight]
st.session_state["recommendations"]     # list[Recommendation]
st.session_state["summary"]             # Executive summary string
st.session_state["qa_result"]           # QAResult
```

### Pipeline Progress Steps
| Stage | Progress % |
|-------|-----------|
| Loading data | 10% |
| Scanning for PII | 20% |
| Profiling data | 30% |
| Detecting domain | 40% |
| Loading industry context | 45% |
| Computing KPIs | 55% |
| Generating charts | 65% |
| Estimating financial impact | 72% |
| Estimating operational impact | 78% |
| Generating insights | 84% |
| Building recommendations | 88% |
| Generating executive summary | 93% |
| Running QA validation | 97% |
| Complete | 100% |

### Dashboard Tabs
1. **📊 Dashboard** — KPI cards + filtered charts
2. **💡 Insights** — Insight cards sorted by priority, with financial impact callouts
3. **💰 Impact** — Financial and operational impact summaries
4. **📝 Summary** — Streaming executive summary
5. **📄 Export** — PDF download + Drive upload

---

## Admin Review (pages/01_Admin_Review.py)

### Header Metrics Row
- Total rows
- Columns detected
- Domain
- KPIs computed
- Charts scored
- **QA Score** (new: overall_score from QAResult, colored by delivery_readiness)

### Tabs
1. **📊 Charts** — ChartSpec table with score, type, business question, PDF/dashboard flags
2. **🔑 KPIs** — KPI values with benchmark status badges
3. **🔍 QA Report** — (new) Full QAResult display: subscores, issues, strengths, recommendations
4. **📋 Profile** — Column-by-column data profile
5. **🤖 Raw Summary** — Raw Claude summary text for editing

---

## Design Principles

### Rule-Based First, AI-Enhanced
The financial_impact_engine and operational_impact_engine are fully rule-based — they produce useful estimates with no Claude API calls. Claude is only used for narrative synthesis (executive summary).

### Graceful Degradation
Every engine has a fallback:
- domain_detector → "general" if confidence is low
- semantic_layer → hardcoded fallback dict if YAML missing
- financial_impact_engine → returns empty FinancialImpact with explanation if no matching columns
- executive_summary → returns error message if Claude unavailable

### Clean Import Paths
All utils are importable as `from utils.module import function`. Thin wrappers (domain_detector, kpi_engine, etc.) re-export from underlying modules to keep app.py clean.

### No Side Effects in Engines
Engines are pure functions: same inputs always produce the same outputs. No randomness, no caching, no external calls (except executive_summary which calls Claude).

---

## Supported Domains

| Domain | Key KPIs |
|--------|----------|
| healthcare | no_show_rate, completion_rate, avg_wait_time, patient_satisfaction, avg_billing_per_appt |
| hospitality | food_cost_pct, labor_cost_pct, prime_cost_pct, no_show_rate, mom_revenue_growth |
| restaurant | food_cost_pct, labor_cost_pct, prime_cost_pct |
| marketing | ctr, roas, conversion_rate, cpc, cpa |
| sales | mom_revenue_growth, avg_discount |
| saas | churn_rate, avg_nps_score, mom_mrr_growth |
| ecommerce | return_rate, avg_discount, avg_days_to_ship, mom_revenue_growth |
| retail | avg_gross_margin, stockout_rate, inventory_turnover |
| real_estate | avg_days_on_market, list_to_sale_ratio, sale_rate |
| hr | attrition_rate, avg_performance, remote_pct |
| operations | avg_response_time, avg_resolution_time |
| finance | margin |
| general | (generic profiling only) |

---

## Sample Datasets (sample_data/)

| File | Domain | Rows | Key Columns |
|------|--------|------|-------------|
| `healthcare_sample.csv` | healthcare | 600 | appointment_date, department, appointment_type, status, wait_time_mins, duration_mins, billing_amount, patient_satisfaction |
| `restaurant_sample.csv` | hospitality | 180 | date, covers, food_cost, labor_cost, revenue |
| `real_estate_sample.csv` | real_estate | 300 | list_date, sale_date, list_price, sale_price, property_type, neighborhood, agent |

---

## Deployment

### Local
```bash
pip install -r requirements.txt
streamlit run app.py
```

### Streamlit Cloud
- Set `ANTHROPIC_API_KEY` in app secrets
- Optionally set `GOOGLE_SERVICE_ACCOUNT_JSON` for Drive integration
- Python 3.10+

### Environment Variables
| Variable | Required | Purpose |
|----------|----------|---------|
| `ANTHROPIC_API_KEY` | Yes | Executive summary generation |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | No | Google Drive upload |
| `DRIVE_FOLDER_ID` | No | Specific Drive folder for uploads |
