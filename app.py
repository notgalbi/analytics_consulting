"""
app.py — Main entry point for the Data Dashboard MVP.
Handles file upload, the full analysis pipeline, and dashboard saving.
"""

import streamlit as st
from pathlib import Path

from utils.data_loader     import load_file
from utils.pii_detector    import sanitize_dataframe, generate_pii_report
from utils.profiler        import profile_dataframe
from utils.kpi_detector    import detect_business_domain, recommend_kpis, calculate_available_kpis
from utils.chart_generator import generate_dashboard_charts
from utils.claude_summary  import build_safe_summary_payload, generate_executive_summary
from utils import storage


st.set_page_config(
    page_title="Data Dashboard MVP",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("📊 Data Dashboard MVP")
    st.markdown("Upload a CSV or Excel file to generate a complete analysis and dashboard.")
    st.divider()
    st.page_link("app.py",                      label="🏠 Upload & Analyse")
    st.page_link("pages/01_Admin_Review.py",    label="🔍 Admin Review")
    st.page_link("pages/02_Client_Dashboard.py",label="📈 Client Dashboard")


# ── Session state init ────────────────────────────────────────────────────────
for key in ("df", "metadata", "profile_data", "pii", "sanitized_df",
            "dataset_type", "kpis", "figures", "summary", "dashboard_id"):
    if key not in st.session_state:
        st.session_state[key] = None


# ── Upload ────────────────────────────────────────────────────────────────────
st.header("Step 1 — Upload your data file")
uploaded_file = st.file_uploader(
    "Drag & drop or browse",
    type=["csv", "xlsx", "xls"],
    help="Max size: 200 MB. PII columns will be detected and masked.",
)

if uploaded_file is None:
    st.info("Upload a CSV or Excel file to get started.")
    st.stop()

# Load once per upload (cache by filename + size)
file_key = f"{uploaded_file.name}_{uploaded_file.size}"
if st.session_state.get("_file_key") != file_key:
    with st.spinner("Reading file…"):
        try:
            df, metadata = load_file(uploaded_file)
            st.session_state.df       = df
            st.session_state.metadata = metadata
            # Reset downstream state
            for key in ("profile_data", "pii", "sanitized_df", "dataset_type",
                        "kpis", "figures", "summary", "dashboard_id"):
                st.session_state[key] = None
            st.session_state._file_key = file_key
        except (ValueError, RuntimeError) as e:
            st.error(str(e))
            st.stop()

df       = st.session_state.df
metadata = st.session_state.metadata

st.success(f"Loaded **{metadata['filename']}** — {metadata['row_count']:,} rows × {metadata['col_count']} columns")

# ── Tabs ──────────────────────────────────────────────────────────────────────
tabs = st.tabs(["👀 Preview", "🔒 PII Report", "📋 Data Quality", "🎯 KPIs", "📊 Charts", "📝 Summary"])

# ── Tab 1: Preview ────────────────────────────────────────────────────────────
with tabs[0]:
    st.subheader("First 20 rows (raw upload)")
    st.dataframe(df.head(20), use_container_width=True)
    st.caption(f"Columns: {', '.join(df.columns)}")

# ── Run pipeline (lazy, cached in session) ────────────────────────────────────
if st.session_state.profile_data is None:
    with st.spinner("Profiling data…"):
        sanitized_df, sensitive_cols, pii_warning = sanitize_dataframe(df)
        domain = detect_business_domain(df)
        calculated_kpis = calculate_available_kpis(df, domain)

        st.session_state.profile_data = profile_dataframe(df)
        st.session_state.pii          = generate_pii_report(df)
        st.session_state.sanitized_df = sanitized_df
        st.session_state.pii_warning  = pii_warning
        st.session_state.dataset_type = domain
        st.session_state.kpis         = recommend_kpis(df, domain)
        st.session_state.calc_kpis    = calculated_kpis
        st.session_state.figures      = generate_dashboard_charts(sanitized_df, domain)

prof         = st.session_state.profile_data
pii_report   = st.session_state.pii
pii_warning  = st.session_state.pii_warning
sanitized_df = st.session_state.sanitized_df
dataset_type = st.session_state.dataset_type
kpis         = st.session_state.kpis
calc_kpis    = st.session_state.calc_kpis
figures      = st.session_state.figures

# ── Tab 2: PII Report ─────────────────────────────────────────────────────────
with tabs[1]:
    st.subheader("PII Detection Report")
    risk = pii_report.get("risk_level", "none")
    total_pii = pii_report.get("total_pii_columns", 0)
    detected = pii_report.get("detected", [])

    if detected:
        badge = {"high": "🔴 HIGH", "medium": "🟡 MEDIUM", "low": "🟢 LOW"}.get(risk, "")
        st.warning(f"{badge} Risk — {total_pii} sensitive column(s) detected and masked.")
        st.code(pii_warning, language=None)
    else:
        st.success("No PII columns detected.")

    st.divider()
    st.subheader("Sanitized Preview (first 20 rows)")
    st.dataframe(sanitized_df.head(20), use_container_width=True)

# ── Tab 3: Data Quality ───────────────────────────────────────────────────────
with tabs[2]:
    st.subheader("Data Quality Report")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Rows",        f"{prof['row_count']:,}")
    col2.metric("Columns",     prof["col_count"])
    col3.metric("Duplicates",  prof["duplicate_rows"])
    col4.metric("Completeness", f"{prof['completeness_pct']}%")

    st.divider()

    # Missing values table
    st.markdown("#### Missing Values by Column")
    missing_rows = [
        {"Column": col, **vals}
        for col, vals in prof.get("missing_values", {}).items()
        if vals["missing_count"] > 0
    ]
    if missing_rows:
        import pandas as pd
        st.dataframe(pd.DataFrame(missing_rows), use_container_width=True)
    else:
        st.success("No missing values found.")

    # Numeric summaries
    if prof.get("numeric_summary"):
        st.markdown("#### Numeric Column Summaries")
        import pandas as pd
        num_df = pd.DataFrame(prof["numeric_summary"]).T.reset_index().rename(columns={"index": "Column"})
        st.dataframe(num_df, use_container_width=True)

    # Categorical summaries
    if prof.get("categorical_summary"):
        st.markdown("#### Categorical Column Summaries")
        for col, stats in prof["categorical_summary"].items():
            with st.expander(f"{col} — {stats['unique_count']} unique values"):
                import pandas as pd
                vc_df = pd.DataFrame(
                    [{"Value": k, "Count": v} for k, v in stats["top_values"].items()]
                )
                st.dataframe(vc_df, use_container_width=True)

# ── Tab 4: KPIs ───────────────────────────────────────────────────────────────
with tabs[3]:
    st.subheader(f"Detected Domain: **{dataset_type.title()}**")

    if calc_kpis:
        st.markdown("#### Calculated KPIs (from your data)")
        cols = st.columns(min(len(calc_kpis), 3))
        for i, (name, value) in enumerate(calc_kpis.items()):
            cols[i % 3].metric(name, value)
        st.divider()

    st.markdown("#### All Recommended KPIs")
    for i, kpi in enumerate(kpis, 1):
        st.markdown(f"**{i}. {kpi['name']}** — {kpi['description']}")

# ── Tab 5: Charts ─────────────────────────────────────────────────────────────
with tabs[4]:
    st.subheader("Auto-generated Charts")
    if not figures:
        st.info("No charts could be generated from this dataset.")
    for title, fig in figures.items():
        st.markdown(f"#### {title}")
        st.plotly_chart(fig, use_container_width=True)

# ── Tab 6: Summary ────────────────────────────────────────────────────────────
with tabs[5]:
    st.subheader("Executive Summary")
    if st.session_state.summary is None:
        if st.button("Generate Executive Summary", type="primary"):
            with st.spinner("Generating summary…"):
                payload = build_safe_summary_payload(prof, dataset_type, kpis, pii_report)
                st.session_state.summary = generate_executive_summary(payload)
    if st.session_state.summary:
        st.markdown(st.session_state.summary)

# ── Save Dashboard ────────────────────────────────────────────────────────────
st.divider()
st.header("Step 2 — Save Dashboard")

if st.session_state.summary is None:
    st.info("Generate the executive summary above before saving.")
else:
    if st.session_state.dashboard_id:
        st.success(f"Dashboard already saved. ID: `{st.session_state.dashboard_id}`")
    else:
        if st.button("💾 Save Dashboard", type="primary"):
            with st.spinner("Saving…"):
                did = storage.create_dashboard_id()
                storage.save_processed_output(
                    dashboard_id=did,
                    profile=prof,
                    kpis={"recommended": kpis, "calculated": calc_kpis},
                    charts_metadata={"titles": list(figures.keys())},
                    summary=st.session_state.summary,
                    extra={
                        "metadata":    metadata,
                        "pii_report":  pii_report,
                        "domain":      dataset_type,
                        "figures":     {t: __import__("plotly.io", fromlist=["to_json"]).to_json(f)
                                        for t, f in figures.items()},
                        "sanitized_csv": sanitized_df.to_csv(index=False),
                    },
                )
                st.session_state.dashboard_id = did
            st.success(f"Dashboard saved! ID: `{did}`")
            st.info("Go to the **Admin Review** page to review before sending to your client.")
