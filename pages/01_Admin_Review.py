"""
pages/01_Admin_Review.py — Admin review interface.
Lists saved dashboards, shows full analysis, and lets the admin approve/reject.
"""

import streamlit as st
import plotly.io as pio
from utils import storage

st.set_page_config(
    page_title="Admin Review — Data Dashboard MVP",
    page_icon="🔍",
    layout="wide",
)

with st.sidebar:
    st.title("📊 Data Dashboard MVP")
    st.divider()
    st.page_link("app.py",                      label="🏠 Upload & Analyse")
    st.page_link("pages/01_Admin_Review.py",    label="🔍 Admin Review")
    st.page_link("pages/02_Client_Dashboard.py",label="📈 Client Dashboard")

st.header("🔍 Admin Review")

# ── Dashboard list ────────────────────────────────────────────────────────────
dashboards = storage.list_dashboards()

if not dashboards:
    st.info("No saved dashboards yet. Upload a file on the main page and save a dashboard first.")
    st.stop()

# Build selection labels
label_map = {
    f"{d['filename']}  |  {d['created_at'][:19].replace('T', ' ')}  |  {d['review_status'].upper()}  (ID: {d['dashboard_id']})": d["dashboard_id"]
    for d in dashboards
}

selected_label = st.selectbox("Select a dashboard to review", list(label_map.keys()))
selected_id = label_map[selected_label]

data = storage.load_dashboard(selected_id)
if data is None:
    st.error(f"Dashboard `{selected_id}` could not be loaded.")
    st.stop()

# ── Header info ───────────────────────────────────────────────────────────────
col_a, col_b, col_c, col_d = st.columns(4)
col_a.metric("File",          data["metadata"].get("filename", "—"))
col_b.metric("Dataset Type",  data.get("dataset_type", "—").title())
col_c.metric("Rows",          f"{data['profile'].get('row_count', 0):,}")
col_d.metric("Status",        data.get("review_status", "pending").upper())

st.divider()

# ── Tabs ──────────────────────────────────────────────────────────────────────
tabs = st.tabs(["📝 Summary", "🔒 PII Report", "📋 Data Quality", "🎯 KPIs", "📊 Charts", "✅ Review"])

# Tab: Summary
with tabs[0]:
    st.subheader("Executive Summary")
    st.markdown(data.get("summary", "No summary available."))

# Tab: PII
with tabs[1]:
    st.subheader("PII Detection Report")
    pii = data.get("pii_detections", [])
    if pii:
        st.warning(f"⚠️  {len(pii)} PII column(s) detected and masked.")
        for item in pii:
            st.markdown(
                f"- **{item['column']}** → `{item['pii_type'].upper()}` "
                f"*(via {item['detection_method'].replace('_', ' ')})*"
            )
    else:
        st.success("No PII columns detected.")

# Tab: Data Quality
with tabs[2]:
    prof = data.get("profile", {})
    st.subheader("Data Quality Report")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Rows",         f"{prof.get('row_count', 0):,}")
    c2.metric("Columns",      prof.get("col_count", 0))
    c3.metric("Duplicates",   prof.get("duplicate_rows", 0))
    c4.metric("Completeness", f"{prof.get('completeness_pct', 0)}%")

    missing_rows = [
        {"Column": col, **vals}
        for col, vals in prof.get("missing", {}).items()
        if vals.get("missing_count", 0) > 0
    ]
    if missing_rows:
        import pandas as pd
        st.markdown("#### Missing Values")
        st.dataframe(pd.DataFrame(missing_rows), use_container_width=True)

    if prof.get("numeric"):
        import pandas as pd
        st.markdown("#### Numeric Summaries")
        num_df = pd.DataFrame(prof["numeric"]).T.reset_index().rename(columns={"index": "Column"})
        st.dataframe(num_df, use_container_width=True)

# Tab: KPIs
with tabs[3]:
    st.subheader("Recommended KPIs")
    for i, kpi in enumerate(data.get("kpis", []), 1):
        st.markdown(f"**{i}. {kpi['name']}** — {kpi['description']}")

# Tab: Charts
with tabs[4]:
    st.subheader("Dashboard Charts")
    charts_json = data.get("charts", {})
    if not charts_json:
        st.info("No charts available for this dashboard.")
    else:
        for title, spec in charts_json.items():
            try:
                fig = pio.from_json(spec)
                st.markdown(f"#### {title}")
                st.plotly_chart(fig, use_container_width=True)
            except Exception as e:
                st.warning(f"Could not render chart '{title}': {e}")

# Tab: Review
with tabs[5]:
    st.subheader("Admin Review & Approval")

    current_status = data.get("review_status", "pending")
    current_notes  = data.get("review_notes", "")

    status = st.selectbox(
        "Review Status",
        options=["pending", "approved", "rejected"],
        index=["pending", "approved", "rejected"].index(current_status),
    )
    notes = st.text_area("Review Notes (visible to you only)", value=current_notes, height=150)

    col_save, col_link = st.columns([1, 2])
    with col_save:
        if st.button("Save Review", type="primary"):
            if storage.update_review(selected_id, status, notes):
                st.success("Review saved.")
                st.rerun()
            else:
                st.error("Failed to save review.")

    with col_link:
        if status == "approved":
            client_url = f"?dashboard_id={selected_id}"
            st.info(
                f"**Client dashboard link:** share the Client Dashboard page with query param "
                f"`?dashboard_id={selected_id}`"
            )
            st.code(f"pages/02_Client_Dashboard?dashboard_id={selected_id}", language=None)
