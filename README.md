# Data Dashboard MVP

An AI-powered data analytics tool built with Python and Streamlit. Upload a client's CSV or Excel file and get a fully formatted analytics report — PII detection, data quality audit, domain-specific KPIs, auto-generated charts, and a Claude-written executive summary — ready to review and deliver.

Built for freelance analytics consulting on Fiverr.

---

## Features

| Feature | Details |
|---|---|
| File upload | CSV, XLSX, XLS — drag & drop or Google Drive import |
| PII detection | Email, phone, name, address, SSN, date of birth — auto-masked |
| Data quality | Completeness, duplicates, missing values, outlier warnings |
| Domain detection | Sales, marketing, SaaS, ecommerce, retail, HR, real estate, hospitality, healthcare, finance |
| KPI benchmarks | Calculated KPIs with traffic-light indicators (🟢🟡🔴) vs industry benchmarks |
| AI KPI analysis | Claude-written 3–5 sentence interpretation of key metrics |
| Auto charts | Time series, bar, histogram, scatter, box plots — up to 10 per dataset |
| Executive summary | Claude API (offline template fallback if no key) |
| Admin review | Edit summary, toggle charts, approve before sending |
| PDF export | Branded PDF report with all charts and summary |
| Google Drive | Import CSV from client's shared folder, upload PDF report back |
| Client dashboard | Clean shareable view via `?dashboard_id=` URL |

---

## Sample Datasets

Portfolio-ready sample datasets included in `sample_data/`:

| File | Domain | Rows |
|---|---|---|
| `sales_sample.csv` | Sales | 150 |
| `marketing_sample.csv` | Marketing | — |
| `ecommerce_orders.csv` | Ecommerce | 1,000 |
| `saas_metrics.csv` | SaaS | 600 |
| `hr_workforce.csv` | HR | 300 |
| `retail_inventory.csv` | Retail | 400 |
| `real_estate_listings.csv` | Real Estate | 300 |
| `restaurant_daily.csv` | Hospitality | 550 |
| `gym_membership.csv` | SaaS / Fitness | 450 |
| `clinic_appointments.csv` | Healthcare | 600 |

---

## Local Setup

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

### 3. Run

```bash
streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501).

---

## Workflow

```
Client shares Drive folder  →  Paste URL in app  →  Select CSV
              or
         Upload CSV/Excel directly
                    ↓
         PII Detection + Masking
                    ↓
         Data Quality Report
                    ↓
       Domain Detection + KPI Benchmarks
                    ↓
         AI KPI Narrative (Claude)
                    ↓
           Auto-generated Charts
                    ↓
       Executive Summary (Claude)
                    ↓
           Save Dashboard
                    ↓
           Admin Review Page
         ┌──────────────────┐
         │ Edit summary     │
         │ Toggle charts    │
         │ Export PDF       │
         │ Upload to Drive  │
         │ Set status       │
         └──────────────────┘
                    ↓
        Share Client Dashboard URL
```

---

## Google Drive Integration

Clients never need an account in your app — they just share a Google Drive folder with your service account.

### Setup

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a project → enable **Google Drive API**
3. IAM & Admin → Service Accounts → Create → download JSON key
4. Add the JSON fields to `.streamlit/secrets.toml` under `[gcp_service_account]`

### Client instructions

Ask the client to share their Drive folder with:
```
your-service-account@your-project.iam.gserviceaccount.com
```

### What it does

- **Import:** Paste the shared folder URL → select CSV → loads instantly
- **Export:** After review, one click uploads the PDF report back to the client's folder

---

## Project Structure

```
data_dashboard_mvp/
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
│   ├── claude_summary.py       # Claude API integration
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

## Privacy & Data Handling

- Raw row data is **never sent to Claude** — only aggregate statistics and column metadata
- PII columns are masked (`[REDACTED:EMAIL]` etc.) before any processing
- The sanitised CSV is what gets saved to disk — original uploads stay in memory only
- Client Drive folders are accessed read-only for CSV import; write access is used only to upload the final PDF

---

## Streamlit Cloud Deployment

1. Push to GitHub (`.streamlit/secrets.toml` is gitignored — safe to push)
2. Go to [share.streamlit.io](https://share.streamlit.io) → New app → select `app.py`
3. Settings → Secrets → paste the contents of your `secrets.toml`
4. Deploy

> **Note:** Streamlit Cloud has an ephemeral filesystem — saved dashboards reset on restart. For persistent storage, the `outputs/` directory can be swapped for cloud storage (S3, GCS, etc.).

---

## API Keys

| Key | Where to get | Required |
|---|---|---|
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) | No — falls back to template summary |
| `gcp_service_account` | Google Cloud Console | No — Drive features hidden if absent |
