"""
pages/01_Admin_Review.py — Admin review interface with full editing controls.

Option C feature set:
  Summary tab  — edit text directly, OR send a prompt to Claude to revise it
  Charts tab   — toggle individual charts on/off for the client view
  Delivery tab — status flow + delete
"""

import streamlit as st
import plotly.io as pio
import pandas as pd
from utils import storage
from utils import drive_client as dc
from utils.claude_summary import build_safe_summary_payload, regenerate_summary, generate_kpi_narrative
from utils.kpi_detector import get_kpi_status
from utils.pdf_generator import generate_pdf

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

# ── Dashboard selector ────────────────────────────────────────────────────────
dashboards = storage.list_saved_dashboards()

if not dashboards:
    st.info("No saved dashboards yet. Upload a file on the main page first.")
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

# ── Per-dashboard session state keys ─────────────────────────────────────────
# Scoped to selected_id so switching dashboards resets all edits.
_SK_SUMMARY  = f"edit_summary_{selected_id}"   # current text in the edit box
_SK_PREVIEW  = f"claude_preview_{selected_id}" # Claude's latest revision draft
_SK_CHARTS   = f"chart_sel_{selected_id}"      # checkbox state dict

# Initialise summary edit buffer from disk (once per dashboard selection)
if _SK_SUMMARY not in st.session_state:
    st.session_state[_SK_SUMMARY] = data.get("summary", "")

# Initialise chart selection from saved metadata (once per dashboard selection)
if _SK_CHARTS not in st.session_state:
    charts_json     = data.get("charts", {})
    saved_approved  = data.get("approved_charts", None)   # None = all approved
    all_titles      = list(charts_json.keys())
    st.session_state[_SK_CHARTS] = {
        t: (t in saved_approved if saved_approved is not None else True)
        for t in all_titles
    }

# ── Header metrics ────────────────────────────────────────────────────────────
meta    = data.get("metadata", {})
profile = data.get("profile", {})
pii_rpt = meta.get("pii_report", {})
status  = data.get("delivery_status", "Needs Review")

qa_score     = data.get("qa_score")
qa_readiness = data.get("qa_readiness", "—")

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("File",       meta.get("filename", "—"))
c2.metric("Domain",     data.get("domain", "—").title())
c3.metric("Rows",       f"{profile.get('row_count', 0):,}")
c4.metric("PII Risk",   pii_rpt.get("risk_level", "none").upper())
c5.metric("Status",     status)
c6.metric("QA Score",   f"{qa_score:.0f}/100" if qa_score is not None else "—",
          help=qa_readiness)

st.divider()

# ── PDF Export ────────────────────────────────────────────────────────────────
with st.spinner("Preparing PDF export…") if False else st.empty():
    pass  # no-op context; export happens on button click below

col_pdf, col_spacer = st.columns([1, 4])
with col_pdf:
    if st.button("📥 Export PDF Report", use_container_width=True):
        with st.spinner("Generating PDF…"):
            try:
                pdf_bytes = generate_pdf(data)
                fname     = f"{selected_id}.pdf"
                st.download_button(
                    label="⬇ Download PDF",
                    data=pdf_bytes,
                    file_name=fname,
                    mime="application/pdf",
                    use_container_width=True,
                )
            except Exception as e:
                st.error(f"PDF generation failed: {e}")

st.divider()

# ── Tabs ──────────────────────────────────────────────────────────────────────
tabs = st.tabs(["📝 Summary", "📋 Profile", "🔒 PII", "🎯 KPIs", "📊 Charts", "🔍 QA Report", "✅ Delivery"])

# ══════════════════════════════════════════════════════════════════════════════
# Tab 1 — Summary (edit + Claude revision)
# ══════════════════════════════════════════════════════════════════════════════
with tabs[0]:
    st.subheader("Executive Summary")
    st.caption("Edit the text directly, or use Claude to revise it based on your instruction.")

    # ── Direct edit ───────────────────────────────────────────────────────────
    edited = st.text_area(
        "Summary text (editable)",
        value=st.session_state[_SK_SUMMARY],
        height=400,
        key=f"ta_{selected_id}",
    )
    # Keep session state in sync with what's in the text area
    st.session_state[_SK_SUMMARY] = edited

    if st.button("💾 Save Summary", type="primary", key="save_summary"):
        if storage.update_summary(selected_id, edited):
            st.success("Summary saved.")
        else:
            st.error("Save failed.")

    st.divider()

    # ── Claude revision ───────────────────────────────────────────────────────
    st.markdown("#### Revise with Claude")
    st.caption(
        "Describe what needs changing. Claude will rewrite the summary "
        "using only your dataset's aggregate statistics — no raw data is sent."
    )

    instruction = st.text_area(
        "Revision instruction",
        placeholder=(
            'e.g. "Focus on regional performance and remove the histogram section."\n'
            '"Shorten to 3 paragraphs and use a more formal tone."\n'
            '"Highlight the low data completeness as a risk."'
        ),
        height=100,
        key=f"instr_{selected_id}",
    )

    if st.button("✨ Revise with Claude", key="revise_claude"):
        if not instruction.strip():
            st.warning("Enter an instruction first.")
        else:
            with st.spinner("Claude is revising…"):
                # Build safe payload from saved profile + domain + KPIs + PII report
                kpis_data = data.get("kpis", {})
                payload   = build_safe_summary_payload(
                    profile,
                    data.get("domain", "general"),
                    kpis_data.get("recommended", []),
                    pii_rpt,
                )
                revised = regenerate_summary(
                    payload,
                    st.session_state[_SK_SUMMARY],
                    instruction,
                )
                st.session_state[_SK_PREVIEW] = revised

    # Show Claude's draft if one exists
    if st.session_state.get(_SK_PREVIEW):
        st.markdown("##### Claude's Revision Draft")
        st.markdown(st.session_state[_SK_PREVIEW])
        col_apply, col_discard = st.columns([1, 1])
        with col_apply:
            if st.button("✅ Apply this version", key="apply_revision"):
                st.session_state[_SK_SUMMARY] = st.session_state[_SK_PREVIEW]
                st.session_state[_SK_PREVIEW]  = None
                if storage.update_summary(selected_id, st.session_state[_SK_SUMMARY]):
                    st.success("Revision applied and saved.")
                st.rerun()
        with col_discard:
            if st.button("✖ Discard draft", key="discard_revision"):
                st.session_state[_SK_PREVIEW] = None
                st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# Tab 2 — Profile (read-only)
# ══════════════════════════════════════════════════════════════════════════════
with tabs[1]:
    st.subheader("Data Quality Profile")

    q1, q2, q3, q4 = st.columns(4)
    q1.metric("Rows",         f"{profile.get('row_count', 0):,}")
    q2.metric("Columns",      profile.get("col_count", 0))
    q3.metric("Completeness", f"{profile.get('completeness_pct', 0)}%")
    dup = profile.get("duplicate_report", {})
    q4.metric("Duplicates",   dup.get("duplicate_rows", 0))

    validation_warnings = profile.get("validation_warnings", [])
    if validation_warnings:
        st.divider()
        st.markdown("#### ⚠️ Data Validation Warnings")
        sev_icon = {"high": "🔴", "medium": "🟡", "low": "🔵"}
        for w in validation_warnings:
            icon = sev_icon.get(w["severity"], "⚪")
            st.warning(f"{icon} **{w['column']}** — {w['issue']}: {w['detail']}")

    missing = profile.get("missing_values", {})
    if missing:
        st.markdown("#### Missing Values")
        st.dataframe(
            pd.DataFrame([{"Column": c, **v} for c, v in missing.items()]),
            use_container_width=True,
        )
    else:
        st.success("No missing values.")

    num = profile.get("numeric_summary", {})
    if num:
        st.markdown("#### Numeric Summaries")
        st.dataframe(
            pd.DataFrame(num).T.reset_index().rename(columns={"index": "Column"}),
            use_container_width=True,
        )

    cat = profile.get("categorical_summary", {})
    if cat:
        st.markdown("#### Categorical Summaries")
        for col, stats in cat.items():
            with st.expander(f"{col} — {stats.get('unique_count', 0)} unique values"):
                st.dataframe(
                    pd.DataFrame([{"Value": k, "Count": v}
                                  for k, v in stats.get("top_values", {}).items()]),
                    use_container_width=True,
                )

    dates = profile.get("date_summary", {})
    if dates:
        st.markdown("#### Date Ranges")
        st.dataframe(
            pd.DataFrame([{"Column": c, **v} for c, v in dates.items()]),
            use_container_width=True,
        )

# ══════════════════════════════════════════════════════════════════════════════
# Tab 3 — PII (read-only)
# ══════════════════════════════════════════════════════════════════════════════
with tabs[2]:
    st.subheader("PII Detection Report")
    risk     = pii_rpt.get("risk_level", "none")
    detected = pii_rpt.get("detected", [])

    risk_icons = {"high": "🔴", "medium": "🟡", "low": "🟢", "none": "✅"}
    st.markdown(f"**Risk Level:** {risk_icons.get(risk, '')} {risk.upper()}")

    if detected:
        if pii_rpt.get("admin_warning"):
            st.code(pii_rpt["admin_warning"], language=None)
        st.dataframe(pd.DataFrame(detected), use_container_width=True)
    else:
        st.success("No PII columns detected.")

# ══════════════════════════════════════════════════════════════════════════════
# Tab 4 — KPIs (read-only)
# ══════════════════════════════════════════════════════════════════════════════
with tabs[3]:
    kpis_data  = data.get("kpis", {})
    calculated = kpis_data.get("calculated", {})
    recommended= kpis_data.get("recommended", [])
    narrative  = kpis_data.get("narrative", "")
    domain     = data.get("domain", "general")

    if calculated:
        st.subheader("Calculated KPIs")
        cols = st.columns(min(len(calculated), 3))
        for i, (name, val) in enumerate(calculated.items()):
            emoji, bench_note = get_kpi_status(domain, name, val)
            label = f"{emoji} {name}" if emoji else name
            cols[i % 3].metric(label, val, help=bench_note or None)
        st.divider()

    # ── AI KPI Analysis ───────────────────────────────────────────────────────
    st.subheader("🤖 AI KPI Analysis")
    if narrative:
        st.markdown(narrative)
        col_regen, _ = st.columns([1, 3])
        with col_regen:
            if st.button("🔄 Regenerate", key="regen_narrative"):
                with st.spinner("Claude is analysing KPIs…"):
                    new = generate_kpi_narrative(domain, calculated, profile)
                    if new:
                        storage.update_kpi_narrative(selected_id, new)
                        st.success("Updated.")
                        st.rerun()
                    else:
                        st.warning("Add ANTHROPIC_API_KEY to .env to enable AI analysis.")
    else:
        col_gen, _ = st.columns([1, 3])
        with col_gen:
            if st.button("🤖 Generate AI Analysis", key="gen_narrative"):
                with st.spinner("Claude is analysing KPIs…"):
                    new = generate_kpi_narrative(domain, calculated, profile)
                    if new:
                        storage.update_kpi_narrative(selected_id, new)
                        st.success("Generated.")
                        st.rerun()
                    else:
                        st.warning("Add ANTHROPIC_API_KEY to .env to enable AI analysis.")

    if recommended:
        st.divider()
        st.subheader("Recommended KPIs")
        for i, kpi in enumerate(recommended, 1):
            st.markdown(f"**{i}. {kpi['name']}** — {kpi['description']}")

# ══════════════════════════════════════════════════════════════════════════════
# Tab 5 — Charts (toggle + preview)
# ══════════════════════════════════════════════════════════════════════════════
with tabs[4]:
    st.subheader("Chart Selection")
    st.caption(
        "Toggle charts on or off. Only checked charts appear on the client dashboard. "
        "Click **Save Chart Selection** to apply."
    )

    charts_json = data.get("charts", {})

    if not charts_json:
        st.info("No charts saved for this dashboard.")
    else:
        chart_sel = st.session_state[_SK_CHARTS]

        for title, spec in charts_json.items():
            col_check, col_chart = st.columns([1, 8])
            with col_check:
                st.write("")  # vertical spacing
                st.write("")
                chart_sel[title] = st.checkbox(
                    "Include",
                    value=chart_sel.get(title, True),
                    key=f"chk_{selected_id}_{title}",
                )
            with col_chart:
                try:
                    fig = pio.from_json(spec)
                    # Dim the chart if deselected
                    if not chart_sel[title]:
                        fig.update_layout(paper_bgcolor="#f0f0f0", plot_bgcolor="#f0f0f0")
                    st.markdown(
                        f"{'✅' if chart_sel[title] else '⬜'} **{title}**"
                        + ("" if chart_sel[title] else "  *(hidden from client)*")
                    )
                    st.plotly_chart(fig, use_container_width=True)
                except Exception as e:
                    st.warning(f"Could not render '{title}': {e}")

        st.divider()
        approved_count = sum(1 for v in chart_sel.values() if v)
        st.caption(f"{approved_count} of {len(charts_json)} charts selected for client view.")

        if st.button("💾 Save Chart Selection", type="primary", key="save_charts"):
            approved = [t for t, on in chart_sel.items() if on]
            if storage.update_approved_charts(selected_id, approved):
                st.success(f"Saved — {len(approved)} chart(s) will appear on the client dashboard.")
            else:
                st.error("Save failed.")

# ══════════════════════════════════════════════════════════════════════════════
# Tab 6 — QA Report
# ══════════════════════════════════════════════════════════════════════════════
with tabs[5]:
    st.subheader("QA Report")

    if qa_score is None:
        st.info("QA score not available for this dashboard. Re-run analysis to generate a score.")
    else:
        readiness_color = {
            "Ready to Deliver": "green",
            "Needs Minor Review": "orange",
            "Needs Major Review": "red",
        }.get(qa_readiness, "gray")

        st.markdown(
            f"### Overall Score: **{qa_score:.0f} / 100** — "
            f"<span style='color:{readiness_color}; font-weight:bold'>{qa_readiness}</span>",
            unsafe_allow_html=True,
        )
        st.divider()

        qa_data = data.get("qa_result_detail", {})

        if qa_data:
            sub1, sub2, sub3, sub4 = st.columns(4)
            sub1.metric("Insight Quality",  f"{qa_data.get('insight_quality_score', 0):.0f}/25")
            sub2.metric("Chart Quality",    f"{qa_data.get('chart_quality_score', 0):.0f}/25")
            sub3.metric("KPI Relevance",    f"{qa_data.get('kpi_relevance_score', 0):.0f}/25")
            sub4.metric("Completeness",     f"{qa_data.get('completeness_score', 0):.0f}/25")
            st.divider()

            if qa_data.get("strengths"):
                st.markdown("#### Strengths")
                for s in qa_data["strengths"]:
                    st.markdown(f"✅ {s}")

            if qa_data.get("issues"):
                st.divider()
                st.markdown("#### Issues")
                sev_icon = {"blocking": "🚫", "warning": "⚠️", "suggestion": "💡"}
                for issue in qa_data["issues"]:
                    icon = sev_icon.get(issue.get("severity", ""), "⚪")
                    st.markdown(
                        f"{icon} **[{issue.get('severity', '').upper()}]** "
                        f"*{issue.get('category', '')}* — {issue.get('description', '')}"
                    )

            if qa_data.get("recommendations"):
                st.divider()
                st.markdown("#### Recommendations Before Delivery")
                for r in qa_data["recommendations"]:
                    st.markdown(f"→ {r}")
        else:
            st.info("Detailed QA breakdown not available — re-run analysis with the new pipeline version.")

# ══════════════════════════════════════════════════════════════════════════════
# Tab 7 — Delivery
# ══════════════════════════════════════════════════════════════════════════════
with tabs[6]:
    st.subheader("Delivery Status")

    current_status = data.get("delivery_status", "Needs Review")
    current_notes  = data.get("review_notes", "")

    new_status = st.selectbox(
        "Status",
        options=list(storage.STATUSES),
        index=list(storage.STATUSES).index(current_status)
              if current_status in storage.STATUSES else 0,
    )
    notes = st.text_area(
        "Admin Notes (not shown to client)",
        value=current_notes,
        height=120,
    )

    col_save, col_del = st.columns([2, 1])
    with col_save:
        if st.button("Save Status", type="primary", key="save_status"):
            if storage.update_delivery_status(selected_id, new_status, notes):
                st.success(f"Status updated to **{new_status}**.")
                st.rerun()
            else:
                st.error("Save failed.")
    with col_del:
        if st.button("🗑 Delete Dashboard", type="secondary", key="delete_dash"):
            if storage.delete_dashboard(selected_id):
                st.success("Dashboard deleted.")
                st.rerun()
            else:
                st.error("Could not delete.")

    if new_status in ("Approved", "Delivered"):
        st.divider()
        st.markdown("#### Client Dashboard Link")
        st.info("Share the **Client Dashboard** page with this ID — clients only see the summary, approved charts, and KPIs.")
        st.code(f"?dashboard_id={selected_id}", language=None)

    # ── Google Drive PDF upload ───────────────────────────────────────────────
    client_folder_id = (
        meta.get("client_drive_folder_id")
        or data.get("client_drive_folder_id")
    )
    if client_folder_id and dc.is_configured():
        st.divider()
        st.markdown("#### Upload Report to Client's Google Drive")
        st.caption(
            "This will generate the PDF report and upload it directly to the "
            "client's shared Drive folder."
        )
        pdf_filename = f"{meta.get('filename', selected_id).rsplit('.', 1)[0]}_report.pdf"
        st.code(f"Destination: {pdf_filename}", language=None)

        if st.button("☁ Upload PDF to Client Drive", key="btn_drive_upload"):
            with st.spinner("Generating PDF and uploading to Drive…"):
                try:
                    svc       = dc.get_service()
                    pdf_bytes = generate_pdf(data)
                    dc.upload_bytes(
                        svc,
                        client_folder_id,
                        pdf_filename,
                        pdf_bytes,
                        mime_type="application/pdf",
                    )
                    st.success(
                        f"PDF uploaded to the client's Drive folder as **{pdf_filename}**."
                    )
                except Exception as _e:
                    st.error(f"Upload failed: {_e}")
