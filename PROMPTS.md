# Prompt Library — Data Dashboard MVP

Reusable prompts for rebuilding or extending each module.
Copy-paste any prompt directly into Claude to regenerate or modify that component.

---

## 1. Master MVP Build Prompt

```
Build a cost-effective MVP for an AI-assisted data analysis and dashboard automation tool.

Goal:
A client uploads a CSV or Excel file. The app profiles the data, detects sensitive fields,
creates summary statistics, recommends KPIs, generates charts, creates an executive summary,
and outputs a dashboard I can review before sending to a client.

Tech stack:
- Python
- Streamlit
- pandas
- plotly
- openpyxl
- python-dotenv
- Local file storage
- Claude API via ANTHROPIC_API_KEY (optional — app must work without it)

Project structure:
- app.py
- pages/01_Admin_Review.py
- pages/02_Client_Dashboard.py
- utils/data_loader.py
- utils/pii_detector.py
- utils/profiler.py
- utils/kpi_detector.py
- utils/chart_generator.py
- utils/claude_summary.py
- utils/storage.py
- sample_data/
- outputs/
- requirements.txt
- .env.example

Rules:
- Write clean modular code with minimal comments.
- Never send raw client rows to Claude — only aggregates and metadata.
- PII columns must be detected and masked before any downstream processing.
- The app must work fully without an API key using a template fallback.
- Do not build Stripe, user login, SaaS billing, or a permanent database.
- Add error handling at system boundaries only.
```

---

## 2. Data Profiler Prompt

```
Create utils/profiler.py.

Build a reusable pandas data profiling module.

Functions needed:
- profile_dataframe(df)        → full profile dict
- get_column_summary(df)       → list of {column, dtype, sample_value}
- get_missing_value_report(df) → {column: {missing_count, missing_pct}} for columns with gaps
- get_duplicate_report(df)     → {duplicate_rows, duplicate_pct}
- get_numeric_summary(df)      → {column: {min, max, mean, median, std, q25, q75, zeros, negatives}}
- get_categorical_summary(df)  → {column: {unique_count, most_common, top_values}}
- get_date_summary(df)         → {column: {min, max, span_days}}

profile_dataframe must return a single dict with keys:
  row_count, col_count, completeness_pct, column_summary,
  missing_values, duplicate_report, numeric_summary,
  categorical_summary, date_summary

Rules:
- No raw row data in the output — aggregates only.
- Date detection should check dtype first, then column name hints
  (date, time, dt, created, updated, timestamp).
- Return plain Python dicts that can be JSON-serialised and passed to Claude.
- Add from __future__ import annotations for Python 3.9 compatibility.
```

---

## 3. PII Safety Prompt

```
Create utils/pii_detector.py.

Build functions that detect sensitive columns in a pandas DataFrame.

Detect:
- email
- phone numbers
- names
- addresses
- SSNs
- dates of birth
- employee IDs
- customer IDs

Use both column-name keyword matching and value-level regex sampling.

Functions needed:
- detect_pii_columns(df)   → list of detection dicts
- sanitize_dataframe(df)   → (sanitized_df, sensitive_col_names, warning_message)
- generate_pii_report(df)  → structured report dict

Detection dict shape:
  { column, pii_type, detection_method, redaction_label }

Redaction labels:
  email → EMAIL_REDACTED
  phone → PHONE_REDACTED
  ssn   → SSN_REDACTED
  name  → NAME_REDACTED
  address → ADDRESS_REDACTED
  dob   → DOB_REDACTED
  employee_id → EMPLOYEE_ID_REDACTED
  customer_id → CUSTOMER_ID_REDACTED

PII report dict shape:
  { total_pii_columns, detected, pii_types_found, risk_level, admin_warning }

Risk levels: none / low / medium / high
  high   = SSN or DOB found
  medium = email, phone, name, or address found
  low    = only IDs found

Rules:
- Check specific multi-word keywords before generic ones to avoid false positives.
- The standalone "name" keyword should only match at word boundaries
  (start or end of column name) to avoid flagging product_name, company_name.
- DOB detection by value regex is forbidden — ISO date strings are
  indistinguishable from other date columns. Use column name only.
- Value regex match threshold: >50% of sampled rows.
- Sample size: 30 rows.
- Add from __future__ import annotations for Python 3.9 compatibility.
```

---

## 4. KPI Detector Prompt

```
Create utils/kpi_detector.py.

Build a rule-based KPI recommendation and calculation engine.

Functions needed:
- detect_business_domain(df)            → domain string
- recommend_kpis(df, domain)            → list of KPI definition dicts
- calculate_available_kpis(df, domain)  → {kpi_name: formatted_value}

Domains: marketing, sales, operations, finance, hr, general

Domain detection:
  Score each domain by weighted keyword matches in column names.
  Use specific multi-word fragments (impression, ticket, attrition) with
  higher weights than generic ones (cost, date). Return the highest scorer.

KPI definitions per domain (name + formula description + explanation):
  Marketing: CTR, CPC, CPA, ROAS, Conversion Rate, Total Spend, Total Revenue
  Sales:     Total Revenue, Avg Order Value, Total Orders, Units Sold,
             Revenue by Region, Revenue by Product, Avg Discount
  Operations: Total Tickets, Open Tickets, Avg Response Time,
              Avg Resolution Time, Resolution Rate
  Finance:   Total Revenue, Total Expenses, Net Profit, Margin, Budget Variance
  HR:        Headcount, Attrition Count, Avg Salary, Department Count, Avg Tenure

calculate_available_kpis:
  - Use a column alias map so "spend" also matches "cost", "ad_spend", "media_spend"
  - Only compute KPIs where the required columns are present and numeric
  - Format values: currency as $X.XXK / $X.XXM, percentages as X.XX%, ratios as Xx
  - Return an empty dict rather than raising an error when no columns match

Add from __future__ import annotations for Python 3.9 compatibility.
```

---

## 5. Chart Generator Prompt

```
Create utils/chart_generator.py.

Build automatic Plotly chart generation for a Streamlit dashboard.
Input must be a sanitized DataFrame — no raw PII reaches this layer.

Functions needed:
- generate_dashboard_charts(df, domain) → dict[title, Figure]
- generate_kpi_cards(df, calculated_kpis) → Figure | None
- generate_time_series_chart(df, date_col, numeric_cols) → Figure | None
- generate_bar_charts(df) → dict[title, Figure]
- generate_numeric_histograms(df) → dict[title, Figure]

Rules:
- Maximum 8 charts total from generate_dashboard_charts.
- Order: time series first (if date column exists), then bar charts, then histograms.
- Bar charts: horizontal, top 15 categories, aggregate numeric column if available.
- Skip categorical columns with more than 50 unique values (free-text noise).
- Time series: aggregate duplicate dates with sum before plotting.
- KPI cards: use plotly Indicator type, support up to 6 cards in a grid.
- Use template="plotly_white" for all charts.
- Return None instead of raising when a chart cannot be generated.
- Add from __future__ import annotations for Python 3.9 compatibility.
```

---

## 6. Claude Summary Prompt

```
Create utils/claude_summary.py.

Build a Claude API integration for generating executive summaries.

PRIVACY RULE: Never send raw DataFrame rows to Claude.
Only send: dataset profile, detected domain, KPI results,
aggregate summaries, data quality issues.

Functions needed:
- build_safe_summary_payload(profile, domain, kpis, pii_report) → dict
- generate_executive_summary(payload) → str

Payload must include only:
  domain, row_count, col_count, completeness_pct, duplicate_report,
  missing_columns (column + count only), numeric_summary (aggregates),
  categorical_summary (unique_count + top 5 values only),
  date_summary, kpi_names (names only), pii_risk_level,
  pii_types_found, pii_column_count

Executive summary sections (in this order):
  1. Dataset Overview
  2. Data Quality Notes
  3. KPI Highlights
  4. Business Insights
  5. Recommended Next Steps
  6. Assumptions & Limitations

API config:
  Model:      claude-sonnet-4-6
  Max tokens: 1500
  API key:    ANTHROPIC_API_KEY env variable

Fallback:
  If ANTHROPIC_API_KEY is not set, return a structured template summary
  that covers all 6 sections using the payload data.
  The template must look professional and be immediately usable.

Error handling:
  If the API call fails, prepend the error message and fall back to the template.
  Never raise — always return a string.
```

---

## 7. Storage Prompt

```
Create utils/storage.py.

Build local MVP file storage for processed dashboard outputs.

Functions needed:
- create_dashboard_id()                                              → str
- save_processed_output(dashboard_id, profile, kpis,
                        charts_metadata, summary, extra)            → Path
- load_processed_output(dashboard_id)                               → dict | None
- list_saved_dashboards()                                           → list[dict]
- delete_dashboard(dashboard_id)                                    → bool
- update_delivery_status(dashboard_id, status, notes)               → bool

Dashboard ID format: dashboard_YYYYMMDD_xxxxxx (date + 6 hex chars)

File layout per dashboard — outputs/{dashboard_id}/:
  metadata.json   → id, created_at, delivery_status, review_notes, domain,
                    filename, row_count, col_count, pii_risk_level,
                    pii_column_count, file_metadata, pii_report
  profile.json    → full data quality profile
  kpis.json       → {recommended: [...], calculated: {...}}
  summary.txt     → executive summary text
  charts.json     → {chart_title: plotly_figure_json_string}
  sanitized.csv   → sanitized DataFrame (optional)

Delivery statuses (in order): "Needs Review", "Approved", "Delivered"
Expose as module constant STATUSES = ("Needs Review", "Approved", "Delivered")

list_saved_dashboards returns lightweight index dicts sorted newest first:
  dashboard_id, filename, created_at, delivery_status, domain,
  row_count, pii_risk_level

load_processed_output merges metadata fields into the top-level result dict
for convenient access.

Add from __future__ import annotations for Python 3.9 compatibility.
```

---

## 8. Streamlit App Prompt

```
Create app.py — the main Streamlit entry point.

The app handles file upload and runs the full analysis pipeline.

Pipeline (run once per upload, cached in st.session_state):
  1. load_file(uploaded_file)                  → df, metadata
  2. sanitize_dataframe(df)                    → sanitized_df, sensitive_cols, pii_warning
  3. generate_pii_report(df)                   → pii_report
  4. profile_dataframe(df)                     → profile
  5. detect_business_domain(df)               → domain
  6. recommend_kpis(df, domain)               → kpis
  7. calculate_available_kpis(df, domain)     → calc_kpis
  8. generate_dashboard_charts(sanitized_df, domain) → figures

UI layout (6 tabs):
  Tab 1 — Preview:      first 20 rows of raw upload
  Tab 2 — PII Report:   risk badge, warning code block, sanitized preview
  Tab 3 — Data Quality: 4 metric cards + missing values + numeric + categorical tables
  Tab 4 — KPIs:         calculated KPI cards + full recommended KPI list
  Tab 5 — Charts:       all generated Plotly charts
  Tab 6 — Summary:      Generate button → calls build_safe_summary_payload then
                        generate_executive_summary → displays markdown

Below the tabs:
  Save Dashboard section — only shown after summary is generated.
  Calls storage.create_dashboard_id() then storage.save_processed_output().
  Shows the dashboard ID and links to Admin Review on success.

Sidebar: navigation links to all three pages.

Rules:
- Cache pipeline results in st.session_state keyed by filename+size.
- Reset all downstream state when a new file is uploaded.
- Never display raw data after the Preview tab.
- Use st.spinner for all long-running steps.
```

---

## 9. Admin Review Page Prompt

```
Create pages/01_Admin_Review.py.

This page lets you review saved dashboard outputs before sending to a client.

Features:
- Dropdown of all saved dashboards with status icon, filename, date, and ID.
- 5 header metric cards: filename, domain, row count, PII risk, current status.
- 6 tabs:
    Summary    — executive summary markdown
    Profile    — data quality metrics + missing values + numeric + categorical + date tables
    PII Report — risk level badge, admin_warning code block, detected columns dataframe
    KPIs       — calculated KPI metric cards + recommended KPI list
    Charts     — all saved Plotly charts rendered from stored JSON
    Delivery   — status selector + admin notes textarea + Save + Delete buttons

Delivery status flow: Needs Review → Approved → Delivered
Status icons: 🟡 Needs Review / 🟢 Approved / ✅ Delivered

On status save: call storage.update_delivery_status then st.rerun().
On delete: call storage.delete_dashboard then st.rerun().

When status is Approved or Delivered:
  Show a "Client Dashboard Link" section with the ?dashboard_id= query param.

Rules:
- Do not expose this page URL to clients.
- Show admin notes field — notes are never displayed on the client dashboard.
- Charts load from charts.json using plotly.io.from_json; wrap each in try/except.
```

---

## 10. Client Dashboard Page Prompt

```
Create pages/02_Client_Dashboard.py.

This page displays a clean, client-facing dashboard.

Loading logic:
  1. Check st.query_params for dashboard_id.
  2. If not present, show a dropdown of Approved/Delivered dashboards only.
  3. Block access to any dashboard with status "Needs Review".

Layout (top to bottom):
  - Title: filename + "Analytics Report"
  - Caption: domain + prepared date
  - Info banner: privacy note about sensitive fields being excluded
  - KPI cards (from calculated_kpis)
  - Data Overview: 3 metric cards (total records, fields analysed, completeness)
  - Visualisations: all charts from charts.json
  - Executive Summary: full markdown
  - Recommended KPIs: top 6 from recommended list

Rules:
- Never show: raw data, PII report, admin notes, review_notes, risk level.
- Never show dashboards with "Needs Review" status — show an error instead.
- initialSidebar: collapsed by default.
- Charts load from charts.json with try/except per chart.
- Privacy banner text: "This dashboard was generated from processed and
  summarised data. Sensitive fields are excluded from AI-generated analysis
  when detected."
```

---

## 11. Sample Data Prompt

```
Create three sample CSV files in sample_data/. Do not include real names,
emails, phone numbers, or addresses in any file.

1. marketing_sample.csv — 120 rows
Columns: date, campaign, platform, impressions, clicks, spend, conversions, revenue
  - date: daily entries spanning ~1 year from 2025-01-01
  - campaign: 5–6 named campaigns
  - platform: Google, Meta, TikTok, LinkedIn, Pinterest
  - Realistic ratios: CTR 1–8%, conversion rate 2–12%, CPC $0.40–$3.50

2. sales_sample.csv — 150 rows (no PII columns)
Columns: order_date, region, product, customer_type, quantity, revenue
  - Regions: North, South, East, West, Central
  - Products: 4–5 product names
  - customer_type: Enterprise, SMB, Individual, Reseller

3. operations_sample.csv — 130 rows
Columns: ticket_date, team, ticket_type, status, response_time_hours, resolution_time_hours
  - Teams: Support Tier 1, Support Tier 2, Engineering, Operations, DevOps
  - ticket_type: Bug, Feature Request, Access Request, Incident, Billing Issue
  - status: Open, In Progress, Resolved, Closed, Escalated
  - resolution_time_hours: blank for Open tickets

Generate in Python using only the csv and random stdlib modules.
Use random.seed() for reproducibility.
```

---

## 12. README Prompt

```
Create README.md for a Streamlit data dashboard MVP project.

Include these sections in order:

1. One-line description of what the tool does.
2. Features table: two columns — Feature | Details
3. Local Setup (numbered steps):
   - git clone + cd
   - python -m venv .venv + activate
   - pip install -r requirements.txt
   - cp .env.example .env with note that API key is optional
   - streamlit run app.py
4. Using the Sample Data: explain the three included CSV files and what
   each one tests (PII detection, domain classification, missing values).
5. Workflow diagram using ASCII arrows showing the full pipeline from
   upload to client delivery.
6. Project Structure: code block with annotated file tree.
7. Streamlit Cloud Deployment: step-by-step including where to add secrets.
   Note that outputs/ uses local disk and resets on redeploy.
8. Privacy & Data Handling: explain the no-raw-rows guarantee and
   how PII masking works.
9. Adding the Claude API Key: where to get it, how to set it,
   which model is used, and what happens without it.

Rules:
- No emojis in section headers.
- Keep each section concise — 3–5 sentences or a short list.
- Code blocks for all shell commands and config snippets.
```
