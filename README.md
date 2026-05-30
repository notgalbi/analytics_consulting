# Data Dashboard MVP

An AI-assisted data analysis and dashboard automation tool built with Python + Streamlit.

Upload a CSV or Excel file and get: PII detection, data quality report, KPI recommendations, auto-generated charts, and an executive summary — all ready to review before sending to your Fiverr client.

---

## Features

| Feature | Details |
|---|---|
| File upload | CSV, XLSX, XLS |
| PII detection | email, phone, name, address, SSN, date of birth |
| Data quality | missingness, duplicates, numeric + categorical summaries |
| Dataset type | sales, marketing, operations, finance, HR, general |
| KPI recommendations | domain-specific KPI templates |
| Auto charts | time series, bar, histogram, KPI cards |
| Executive summary | Claude API (or offline template fallback) |
| Admin review | approve / reject before sharing |
| Client dashboard | clean view via `?dashboard_id=` URL param |

---

## Local Setup

### 1. Clone and install

```bash
git clone <repo>
cd data_dashboard_mvp
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Open .env and add your CLAUDE_API_KEY (optional — app works without it)
```

### 3. Run

```bash
streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

---

## Using the Sample Data

A realistic sales dataset is included at `sample_data/sales_sample.csv` (150 rows, 15 columns).
It contains PII columns (CustomerName, CustomerEmail, CustomerPhone) for testing the detection flow.

---

## Workflow

```
Upload CSV/Excel
      ↓
Preview + PII Detection
      ↓
Data Quality Report
      ↓
KPI Recommendations
      ↓
Auto Charts
      ↓
Executive Summary (Claude or template)
      ↓
Save Dashboard  →  Admin Review Page
                         ↓
                   Approve / Reject
                         ↓
               Share Client Dashboard URL
```

---

## Project Structure

```
data_dashboard_mvp/
├── app.py                    # Main Streamlit entry point
├── pages/
│   ├── 01_Admin_Review.py    # Admin review interface
│   └── 02_Client_Dashboard.py # Client-facing dashboard
├── utils/
│   ├── data_loader.py        # CSV/Excel file reader
│   ├── pii_detector.py       # PII column detection + sanitisation
│   ├── profiler.py           # Data quality report
│   ├── kpi_detector.py       # Dataset type + KPI recommendations
│   ├── chart_generator.py    # Plotly chart generation
│   ├── claude_summary.py     # Claude API executive summary
│   └── storage.py            # Local dashboard persistence
├── sample_data/
│   └── sales_sample.csv
├── outputs/                  # Saved dashboards (auto-created)
├── requirements.txt
├── .env.example
└── README.md
```

---

## Streamlit Cloud Deployment

1. Push this repo to GitHub.
2. Go to [share.streamlit.io](https://share.streamlit.io) → New app.
3. Set **Main file path** to `app.py`.
4. Add `CLAUDE_API_KEY` under **Secrets** (Settings → Secrets):
   ```toml
   CLAUDE_API_KEY = "sk-ant-..."
   ```
5. Deploy.

> **Note:** The `outputs/` directory uses local disk storage. On Streamlit Cloud this resets on each restart. For persistence, swap `storage.py` to write to an S3 bucket or a simple database.

---

## Privacy & Data Handling

- **Raw row data is never sent to Claude.** Only column names, aggregate statistics, and metadata are included in the prompt.
- PII columns are masked (`[REDACTED:EMAIL]` etc.) before any downstream processing.
- The sanitised CSV is the only file saved to disk — the original upload stays in memory only.

---

## Adding the Claude API Key

The app works fully without a key — the executive summary falls back to a structured template.

To enable Claude-powered summaries:
1. Get a key at [console.anthropic.com](https://console.anthropic.com)
2. Add it to `.env`: `CLAUDE_API_KEY=sk-ant-...`
3. Restart the app.

Model used: `claude-sonnet-4-6` (cost-effective, high quality).
