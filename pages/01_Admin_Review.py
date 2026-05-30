"""
pages/01_Admin_Review.py — Admin review interface.
Lists saved dashboards, shows the full analysis, and lets you set delivery status.

Delivery statuses: Needs Review → Approved → Delivered
"""

import streamlit as st
import plotly.io as pio
import pandas as pd
from utils import storage

st.set_page_config(
    page_title="Admin Review — Data Dashboard MVP",
    page_icon="🔍",
    layout="wide",
)

with st.sidebar:
    st.title("📊 Data Dashboard MVP")
    st.divider()
    st.page_link("app.py",                       label="🏠 Upload & Analyse")
    st.page_link("pages/01_Admin_Review.py",     label="🔍 Admin Review")
    st.page_link("pages/02_Client_Dashboard.py", label="📈 Client Dashboard")

st.header("🔍 Admin Review")

# ── Dashboard list ────────────────────────────────────────────────────────────
dashboards = storage.list_saved_dashboards()

if not dashboards:
    st.info("No saved dashboards yet. Upload a file on the main page and save a dashboard first.")
    st.stop()

STATUS_ICONS = {"Needs Review": "🟡", "Approved": "🟢", "Delivered": "✅"}

label_map = {
    (
        f"{STATUS_ICONS.get(d['delivery_status'], '⚪')} {d['delivery_status'].upper()}  "
        f"│  {d['filename']}  "
        f"│  {d.get('created_at', '')[:10]}  "
        f"│  ID: {d['dashboard_id']}"
    ): d["dashboard_id"]
    for d in dashboards
}

selected_label = st.selectbox("Select a dashboard to review", list(label_map.keys()))
selected_id    = label_map[selected_label]

data = storage.load_processed_output(selected_id)
if data is None:
    st.error(f"Dashboard `{selected_id}` could not be loaded.")
    st.stop()

# ── Header metrics ────────────────────────────────────────────────────────────
meta     = data.get("metadata", {})
profile  = data.get("profile", {})
pii_rpt  = meta.get("pii_report", {})
status   = data.get("delivery_status", "Needs Review")

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("File",        meta.get("filename", "—"))
c2.metric("Domain",      data.get("domain", "—").title())
c3.metric("Rows",        f"{profile.get('row_count', 0):,}")
c4.metric("PII Risk",    pii_rpt.get("risk_level", "none").upper())
c5.metric("Status",      status)

st.divider()

# ── Tabs ──────────────────────────────────────────────────────────────────────
tabs = st.tabs(["📝 Summary", "📋 Profile", "🔒 PII Report", "🎯 KPIs", "📊 Charts", "✅ Delivery"])

# ── Summary ───────────────────────────────────────────────────────────────────
with tabs[0]:
    st.subheader("Executive Summary")
    summary = data.get("summary", "No summary available.")
    st.markdown(summary)

# ── Profile ───────────────────────────────────────────────────────────────────
with tabs[1]:
    st.subheader("Data Quality Profile")

    q1, q2, q3, q4 = st.columns(4)
    q1.metric("Rows",         f"{profile.get('row_count', 0):,}")
    q2.metric("Columns",      profile.get("col_count", 0))
    q3.metric("Completeness", f"{profile.get('completeness_pct', 0)}%")
    dup = profile.get("duplicate_report", {})
    q4.metric("Duplicates",   dup.get("duplicate_rows", 0))

    missing = profile.get("missing_values", {})
    if missing:
        st.markdown("#### Missing Values")
        rows = [{"Column": c, **v} for c, v in missing.items()]
        st.dataframe(pd.DataFrame(rows), use_container_width=True)
    else:
        st.success("No missing values found.")

    num = profile.get("numeric_summary", {})
    if num:
        st.markdown("#### Numeric Summaries")
        num_df = pd.DataFrame(num).T.reset_index().rename(columns={"index": "Column"})
        st.dataframe(num_df, use_container_width=True)

    cat = profile.get("categorical_summary", {})
    if cat:
        st.markdown("#### Categorical Summaries")
        for col, stats in cat.items():
            with st.expander(f"{col} — {stats.get('unique_count', 0)} unique values"):
                vc = stats.get("top_values", {})
                st.dataframe(
                    pd.DataFrame([{"Value": k, "Count": v} for k, v in vc.items()]),
                    use_container_width=True,
                )

    dates = profile.get("date_summary", {})
    if dates:
        st.markdown("#### Date Ranges")
        rows = [{"Column": c, **v} for c, v in dates.items()]
        st.dataframe(pd.DataFrame(rows), use_container_width=True)

# ── PII Report ────────────────────────────────────────────────────────────────
with tabs[2]:
    st.subheader("PII Detection Report")
    detected = pii_rpt.get("detected", [])
    risk     = pii_rpt.get("risk_level", "none")

    risk_colours = {"high": "🔴", "medium": "🟡", "low": "🟢", "none": "✅"}
    st.markdown(f"**Risk Level:** {risk_colours.get(risk, '')} {risk.upper()}")

    if detected:
        warning = pii_rpt.get("admin_warning", "")
        if warning:
            st.code(warning, language=None)
        st.dataframe(pd.DataFrame(detected), use_container_width=True)
    else:
        st.success("No PII columns detected.")

# ── KPIs ──────────────────────────────────────────────────────────────────────
with tabs[3]:
    kpis_data    = data.get("kpis", {})
    recommended  = kpis_data.get("recommended", [])
    calculated   = kpis_data.get("calculated", {})

    if calculated:
        st.subheader("Calculated KPIs")
        cols = st.columns(min(len(calculated), 3))
        for i, (name, val) in enumerate(calculated.items()):
            cols[i % 3].metric(name, val)
        st.divider()

    if recommended:
        st.subheader("Recommended KPIs")
        for i, kpi in enumerate(recommended, 1):
            st.markdown(f"**{i}. {kpi['name']}** — {kpi['description']}")

# ── Charts ────────────────────────────────────────────────────────────────────
with tabs[4]:
    st.subheader("Dashboard Charts")
    charts_json = data.get("charts", {})
    if not charts_json:
        st.info("No charts saved for this dashboard.")
    else:
        for title, spec in charts_json.items():
            try:
                fig = pio.from_json(spec)
                st.markdown(f"#### {title}")
                st.plotly_chart(fig, use_container_width=True)
            except Exception as e:
                st.warning(f"Could not render '{title}': {e}")

# ── Delivery ──────────────────────────────────────────────────────────────────
with tabs[5]:
    st.subheader("Delivery Status")

    current_status = data.get("delivery_status", "Needs Review")
    current_notes  = data.get("review_notes", "")

    new_status = st.selectbox(
        "Status",
        options=list(storage.STATUSES),
        index=list(storage.STATUSES).index(current_status)
              if current_status in storage.STATUSES else 0,
    )
    notes = st.text_area("Admin Notes (not shown to client)", value=current_notes, height=120)

    col_save, col_del = st.columns([2, 1])

    with col_save:
        if st.button("Save Status", type="primary"):
            if storage.update_delivery_status(selected_id, new_status, notes):
                st.success(f"Status updated to **{new_status}**.")
                st.rerun()
            else:
                st.error("Failed to save status.")

    with col_del:
        if st.button("🗑 Delete Dashboard", type="secondary"):
            if storage.delete_dashboard(selected_id):
                st.success("Dashboard deleted.")
                st.rerun()
            else:
                st.error("Could not delete dashboard.")

    st.divider()

    if new_status in ("Approved", "Delivered"):
        st.markdown("#### Client Dashboard Link")
        st.info(
            "Share the **Client Dashboard** page with this dashboard ID. "
            "The client will only see the summary, KPIs, and charts."
        )
        st.code(f"?dashboard_id={selected_id}", language=None)
