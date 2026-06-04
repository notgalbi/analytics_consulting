# Automated Analytics Reporting — AI-Powered Insights for Business Owners

**Upload your data. Receive a professional consulting report in minutes.**

No spreadsheet expertise required. No manual analysis. No waiting days for a freelancer to email you back.
This system processes your data automatically — cleaning it, benchmarking your KPIs, generating charts, and writing a full executive summary using the same AI behind the world's most advanced consulting tools.

---

## What This Does

This is an automated analytics engine built for freelance consulting delivery. You provide a data file. The system handles everything else: detecting what kind of business data it is, calculating the KPIs that matter for your industry, generating visual charts, and writing a structured report with specific, actionable recommendations.

The output isn't a generic summary. It's a domain-specific report written in the tone of a senior analyst — with real numbers, identified risks, and prioritized next steps.

---

## Who This Is For

**Business owners** who have data but no time or team to analyze it.

**Operators** who want to know what their numbers actually mean — not just what they are.

**Fiverr clients** looking for a professional analytics report without hiring a full-time analyst.

**Industries covered:** Sales · Marketing · SaaS · E-commerce · Retail · Real Estate · Hospitality · Healthcare · HR · Finance

---

## What You Get

Every report includes:

- **Executive Summary** — a multi-section written report with insights, risks, and prioritized action items
- **KPI Performance Dashboard** — calculated metrics benchmarked against industry standards, with traffic-light indicators (above target / at risk / critical)
- **AI KPI Analysis** — plain-English interpretation of your key metrics and what they mean for your business
- **Auto-Generated Charts** — up to 10 data visualizations including time series, distributions, and comparisons
- **Data Quality Audit** — completeness scores, duplicate detection, outlier warnings, and validation flags
- **Callout Insights** — three punchy statements on revenue risk, operational efficiency gaps, and experience quality, suitable for executive briefings
- **Professional PDF Report** — formatted, branded, and ready to share with your team or board
- **Private Client Dashboard** — a shareable web link with a clean view of all charts and the full summary

---

## How It Works

**1. Upload your data**
Drag and drop a CSV or Excel file — or paste a Google Drive folder link if you've already shared your data there.

**2. The system analyzes everything automatically**
In under two minutes: PII is detected and masked, data quality is assessed, your business domain is identified, KPIs are calculated, and charts are generated.

**3. AI writes your report**
Claude produces a full consulting-grade executive summary — structured by section, backed by your actual numbers, and written for decision-makers, not data scientists.

**4. Review and deliver**
The admin review page lets you edit the summary, toggle charts, and approve the final output. One click exports a PDF and optionally uploads it directly to your client's Google Drive folder.

**5. Share the dashboard**
Send your client a private dashboard URL. They see their charts, insights, and full report — no login required.

---

## Service Tiers

| Tier | What's Included |
|---|---|
| **Entry** | Upload your data file and receive a professional report with insights, charts, and a written executive summary |
| **Standard** | Full AI-powered report with KPI benchmarking, industry comparisons, and prioritized business recommendations |
| **Premium** | Automated reporting with Google Drive integration — client shares a folder, you deliver back a PDF report, hands-free |

The Premium tier is built for recurring engagements: clients share a monthly export, the system processes it automatically, and you deliver a consistent report on a predictable schedule — no manual work per cycle.

---

## Features

| Capability | Details |
|---|---|
| File input | CSV, XLSX, XLS — upload directly or import from Google Drive |
| PII protection | Email, phone, name, address, SSN, date of birth — auto-detected and masked |
| Data quality | Completeness %, duplicates, missing values, outlier and validation warnings |
| Domain detection | 10 business domains — auto-detected from column structure |
| KPI benchmarks | Calculated KPIs with traffic-light status vs. industry standards |
| AI analysis | Claude-written KPI narrative and full executive summary by domain |
| Charts | Up to 10 auto-generated Plotly charts per dataset |
| Admin review | Edit summary, toggle charts, set status, approve before delivery |
| PDF export | Fully formatted report with all charts and sections |
| Google Drive | Import CSV from client folder, export PDF back to same folder |
| Client dashboard | Shareable `?dashboard_id=` URL — no client login required |
| Offline fallback | Template-based summary if no API key is configured |

---

## Sample Datasets

Ten portfolio-ready datasets are included in `sample_data/` for demos and testing:

| File | Domain | Rows |
|---|---|---|
| `sales_sample.csv` | Sales | 150 |
| `marketing_sample.csv` | Marketing | — |
| `ecommerce_orders.csv` | E-commerce | 1,000 |
| `saas_metrics.csv` | SaaS | 600 |
| `hr_workforce.csv` | HR | 300 |
| `retail_inventory.csv` | Retail | 400 |
| `real_estate_listings.csv` | Real Estate | 300 |
| `restaurant_daily.csv` | Hospitality | 550 |
| `gym_membership.csv` | Fitness / SaaS | 450 |
| `clinic_appointments.csv` | Healthcare | 600 |

---

## Privacy & Data Handling

- Raw row data is **never sent to Claude** — only aggregate statistics and column metadata
- PII columns are masked (`[REDACTED:EMAIL]`) before any processing or storage
- The sanitized CSV is what gets saved — original uploads stay in memory only
- Client Drive folders are accessed read-only for import; write access is used only to deliver the final PDF

---

## Technical Setup

### 1. Clone and install

```bash
git clone https://github.com/notgalbi/analytics_consulting
cd analytics_consulting
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure secrets

Create `.streamlit/secrets.toml`:

```toml
ANTHROPIC_API_KEY = "sk-ant-..."

[gcp_service_account]
type = "service_account"
project_id = "your-project-id"
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "your-sa@your-project.iam.gserviceaccount.com"
client_id = "..."
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "..."
universe_domain = "googleapis.com"
```

Both keys are optional — the app runs without them (no AI summaries, no Drive).

| Key | Where to get | Required |
|---|---|---|
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) | No — falls back to template summary |
| `gcp_service_account` | Google Cloud Console | No — Drive features hidden if absent |

### 3. Run

```bash
streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501).

---

## Google Drive Integration

Clients never need an account in your app. They share a Google Drive folder with your service account email — you paste the URL, select the file, and the system handles import and delivery.

### Setup

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a project → enable **Google Drive API**
3. IAM & Admin → Service Accounts → Create → download JSON key
4. Add the JSON fields to `.streamlit/secrets.toml` under `[gcp_service_account]`

### Client instructions

Ask the client to share their Drive folder with your service account email:
```
your-service-account@your-project.iam.gserviceaccount.com
```

---

## Deployment

1. Push to GitHub (`.streamlit/secrets.toml` is gitignored — safe to push)
2. Go to [share.streamlit.io](https://share.streamlit.io) → New app → select `app.py`
3. Settings → Secrets → paste the contents of your `secrets.toml`
4. Deploy

> Streamlit Cloud has an ephemeral filesystem — saved dashboards reset on restart. For persistent storage, the `outputs/` directory can be swapped for S3, GCS, or any cloud storage provider.

---

## Project Structure

```
analytics_consulting/
├── app.py                      # Main upload + analysis page
├── pages/
│   ├── 01_Admin_Review.py      # Review, edit, approve, export
│   └── 02_Client_Dashboard.py  # Clean client-facing view
├── utils/
│   ├── data_loader.py          # CSV/Excel reader + Drive bytes loader
│   ├── pii_detector.py         # PII detection and masking
│   ├── profiler.py             # Data quality + validation warnings
│   ├── kpi_detector.py         # Domain detection, KPIs, benchmarks
│   ├── chart_generator.py      # Plotly chart generation
│   ├── claude_summary.py       # Claude API integration + domain prompts
│   ├── pdf_generator.py        # PDF report generation
│   ├── drive_client.py         # Google Drive API wrapper
│   └── storage.py              # Local dashboard persistence
├── sample_data/                # Portfolio sample datasets
├── outputs/                    # Saved dashboards (auto-created, gitignored)
├── .streamlit/
│   └── secrets.toml            # API keys (gitignored — never commit)
└── requirements.txt
```

---

## Roadmap

- **Scheduled reporting** — trigger a new report automatically on a recurring schedule (weekly, monthly) without manual uploads
- **Email delivery** — send the PDF and dashboard link directly to the client on completion, with plan-based timing controls
- **White-label output** — swap branding, colors, and logo per client for agency-level delivery
- **Multi-file aggregation** — combine multiple monthly exports into a single trend report
- **Cloud storage** — persist dashboards to S3 or GCS for production-scale deployments
