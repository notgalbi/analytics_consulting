"""
app.py — Main entry point for the Data Dashboard MVP.
Handles file upload, the full analysis pipeline, and dashboard saving.
"""

import streamlit as st
from pathlib import Path

from utils.data_loader              import load_file, load_from_bytes
from utils.pii_detector             import sanitize_dataframe, generate_pii_report
from utils                          import drive_client as dc
from utils.profiler                 import profile_dataframe
from utils.kpi_detector             import detect_business_domain, recommend_kpis, calculate_available_kpis, get_kpi_status
from utils.chart_generator          import generate_dashboard_charts
from utils.chart_intelligence       import score_and_select_charts
from utils.semantic_layer           import get_industry_context
from utils.financial_impact_engine  import estimate_financial_impact
from utils.operational_impact_engine import estimate_operational_impact
from utils.insight_engine           import generate_insights
from utils.recommendation_engine    import generate_recommendations
from utils.qa_validator             import validate_report
from utils.opportunity_scorer       import score_opportunities
from utils.scenario_modeler         import model_scenarios
from utils.claude_summary           import build_safe_summary_payload, generate_executive_summary, generate_kpi_narrative, stream_executive_summary
from utils                          import storage


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
    st.divider()
    st.selectbox(
        "Report Audience",
        ["Business Owner", "Manager/Director", "VP/C-Suite"],
        key="audience_level",
    )


# ── Session state init ────────────────────────────────────────────────────────
for key in ("df", "metadata", "profile_data", "pii", "sanitized_df",
            "dataset_type", "kpis", "figures", "summary", "dashboard_id",
            "kpi_narrative", "drive_content", "drive_filename",
            "client_drive_folder_id", "industry_context", "calc_kpis",
            "chart_specs", "financial_impact", "operational_impact",
            "insights", "recommendations", "qa_result",
            "opportunities", "scenarios"):
    if key not in st.session_state:
        st.session_state[key] = None


# ── Step 1: File source ───────────────────────────────────────────────────────
st.header("Step 1 — Upload your data file")

# ── Sample dataset loader ─────────────────────────────────────────────────────
_sample_dir = Path(__file__).parent / "sample_data"
_sample_files = sorted(p.name for p in _sample_dir.glob("*.csv")) if _sample_dir.exists() else []

if _sample_files:
    with st.expander("🗂 Load a sample dataset (demo)", expanded=False):
        _sel_sample = st.selectbox("Choose a sample file", ["— select —"] + _sample_files, key="sample_sel")
        if _sel_sample != "— select —":
            if st.button("⚡ Load sample", key="btn_load_sample"):
                _content = (_sample_dir / _sel_sample).read_bytes()
                st.session_state.drive_content          = _content
                st.session_state.drive_filename         = _sel_sample
                st.session_state.client_drive_folder_id = None
                st.rerun()

# ── Google Drive import (only shown when Drive is configured) ─────────────────
if dc.is_configured():
    with st.expander("📁 Import from a client's Google Drive folder", expanded=False):
        st.caption(
            "Paste the URL of the Drive folder the client shared with your service account. "
            "The app will list all CSV/Excel files so you can select one."
        )
        folder_url = st.text_input(
            "Drive folder URL",
            placeholder="https://drive.google.com/drive/folders/...",
            key="drive_folder_url_input",
        )
        if folder_url:
            folder_id = dc.folder_id_from_url(folder_url)
            if not folder_id:
                st.warning("Could not extract a folder ID from that URL.")
            else:
                try:
                    _svc = dc.get_service()
                    _files = dc.list_files(_svc, folder_id)
                    _data_files = [
                        f for f in _files
                        if f["name"].lower().endswith((".csv", ".xlsx", ".xls"))
                    ]
                    if not _data_files:
                        st.info("No CSV or Excel files found in that folder.")
                    else:
                        _sel_name = st.selectbox(
                            "Select file to load",
                            [f["name"] for f in _data_files],
                            key="drive_file_sel",
                        )
                        if st.button("⬇ Load from Drive", key="btn_load_drive"):
                            _sel = next(f for f in _data_files if f["name"] == _sel_name)
                            with st.spinner(f"Downloading {_sel_name} from Drive…"):
                                _content = dc.download_bytes(_svc, _sel["id"])
                            st.session_state.drive_content          = _content
                            st.session_state.drive_filename         = _sel_name
                            st.session_state.client_drive_folder_id = folder_id
                            st.rerun()
                except Exception as _e:
                    st.error(f"Drive error: {_e}")

    if st.session_state.drive_content is not None:
        st.success(f"Drive file loaded: **{st.session_state.drive_filename}**")
        if st.button("✖ Clear Drive file", key="btn_clear_drive"):
            for _k in ("drive_content", "drive_filename", "client_drive_folder_id"):
                st.session_state[_k] = None
            st.rerun()

uploaded_file = st.file_uploader(
    "Or drag & drop / browse from your computer",
    type=["csv", "xlsx", "xls"],
    help="Max size: 1 GB. PII columns will be detected and masked.",
)

# Determine active file source
_drive_active = st.session_state.drive_content is not None

if not _drive_active and uploaded_file is None:
    st.info("Upload a CSV or Excel file to get started.")
    st.stop()

# Load once per file (keyed by name+size to avoid re-processing on rerun)
if _drive_active:
    file_key = f"drive_{st.session_state.drive_filename}_{len(st.session_state.drive_content)}"
else:
    file_key = f"{uploaded_file.name}_{uploaded_file.size}"

if st.session_state.get("_file_key") != file_key:
    with st.spinner("Reading file…"):
        try:
            if _drive_active:
                df, metadata = load_from_bytes(
                    st.session_state.drive_content,
                    st.session_state.drive_filename,
                )
            else:
                df, metadata = load_file(uploaded_file)
            st.session_state.df       = df
            st.session_state.metadata = metadata
            for key in ("profile_data", "pii", "sanitized_df", "dataset_type",
                        "kpis", "figures", "summary", "dashboard_id",
                        "industry_context", "calc_kpis", "chart_specs",
                        "financial_impact", "operational_impact",
                        "insights", "recommendations", "qa_result",
                        "opportunities", "scenarios"):
                st.session_state[key] = None
            st.session_state._file_key = file_key
        except (ValueError, RuntimeError) as e:
            st.error(str(e))
            st.stop()

df       = st.session_state.df
metadata = st.session_state.metadata

st.success(f"Loaded **{metadata['filename']}** — {metadata['row_count']:,} rows × {metadata['col_count']} columns")

# ── Tabs ──────────────────────────────────────────────────────────────────────
tabs = st.tabs(["👀 Preview", "🔒 PII Report", "📋 Data Quality", "🎯 KPIs",
                "📊 Charts", "💡 Insights", "💰 Impact", "📝 Summary",
                "🎯 Opportunities", "📐 Scenarios"])

# ── Tab 1: Preview ────────────────────────────────────────────────────────────
with tabs[0]:
    st.subheader("First 20 rows (raw upload)")
    st.dataframe(df.head(20), use_container_width=True)
    st.caption(f"Columns: {', '.join(df.columns)}")

# ── Run pipeline (lazy, cached in session) ────────────────────────────────────
if st.session_state.profile_data is None:
    progress = st.progress(0, text="Starting analysis…")

    progress.progress(10, text="Scanning for sensitive data…")
    sanitized_df, sensitive_cols, pii_warning = sanitize_dataframe(df)
    pii_report_temp = generate_pii_report(df)

    progress.progress(25, text="Profiling data quality…")
    profile_temp = profile_dataframe(df)

    progress.progress(40, text="Detecting business domain…")
    domain = detect_business_domain(df)

    progress.progress(45, text="Loading industry context…")
    industry_context_temp = get_industry_context(domain)

    progress.progress(55, text="Computing KPIs…")
    calculated_kpis = calculate_available_kpis(df, domain)

    progress.progress(65, text="Generating and scoring charts…")
    chart_specs_temp, figures_temp = score_and_select_charts(sanitized_df, domain)

    progress.progress(72, text="Estimating financial impact…")
    financial_impact_temp = estimate_financial_impact(domain, calculated_kpis, profile_temp)

    progress.progress(78, text="Estimating operational impact…")
    operational_impact_temp = estimate_operational_impact(domain, calculated_kpis, profile_temp)

    progress.progress(84, text="Generating insights…")
    insights_temp = generate_insights(
        domain, calculated_kpis, profile_temp,
        financial_impact_temp, operational_impact_temp,
    )

    progress.progress(88, text="Building recommendations…")
    recommendations_temp = generate_recommendations(insights_temp, domain)

    progress.progress(90, text="Scoring opportunities…")
    opportunities_temp = score_opportunities(insights_temp, recommendations_temp, financial_impact_temp)
    scenarios_temp = model_scenarios(opportunities_temp, financial_impact_temp)

    progress.progress(93, text="Running AI KPI analysis…")
    narrative_temp = generate_kpi_narrative(domain, calculated_kpis, profile_temp)

    progress.progress(97, text="Running QA validation…")
    qa_result_temp = validate_report(
        insights_temp,
        figures_temp,
        calculated_kpis,
        "",  # summary not generated yet
        financial_impact_temp,
        operational_impact_temp,
        opportunities=opportunities_temp,
    )

    progress.progress(100, text="Analysis complete.")
    progress.empty()

    st.session_state.profile_data        = profile_temp
    st.session_state.pii                 = pii_report_temp
    st.session_state.sanitized_df        = sanitized_df
    st.session_state.pii_warning         = pii_warning
    st.session_state.dataset_type        = domain
    st.session_state.industry_context    = industry_context_temp
    st.session_state.kpis                = recommend_kpis(df, domain)
    st.session_state.calc_kpis           = calculated_kpis
    st.session_state.chart_specs         = chart_specs_temp
    st.session_state.figures             = figures_temp
    st.session_state.financial_impact    = financial_impact_temp
    st.session_state.operational_impact  = operational_impact_temp
    st.session_state.insights            = insights_temp
    st.session_state.recommendations     = recommendations_temp
    st.session_state.opportunities       = opportunities_temp
    st.session_state.scenarios           = scenarios_temp
    st.session_state.kpi_narrative       = narrative_temp
    st.session_state.qa_result           = qa_result_temp

prof               = st.session_state.profile_data
pii_report         = st.session_state.pii
pii_warning        = st.session_state.pii_warning
sanitized_df       = st.session_state.sanitized_df
dataset_type       = st.session_state.dataset_type
industry_context   = st.session_state.industry_context
kpis               = st.session_state.kpis
calc_kpis          = st.session_state.calc_kpis
chart_specs        = st.session_state.chart_specs
figures            = st.session_state.figures
financial_impact   = st.session_state.financial_impact
operational_impact = st.session_state.operational_impact
insights           = st.session_state.insights
recommendations    = st.session_state.recommendations
opportunities      = st.session_state.opportunities
scenarios          = st.session_state.scenarios
qa_result          = st.session_state.qa_result

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
    col1.metric("Rows",         f"{prof['row_count']:,}")
    col2.metric("Columns",      prof["col_count"])
    col3.metric("Duplicates",   prof["duplicate_report"]["duplicate_rows"])
    col4.metric("Completeness", f"{prof['completeness_pct']}%")

    validation_warnings = prof.get("validation_warnings", [])
    if validation_warnings:
        st.divider()
        st.markdown("#### ⚠️ Data Validation Warnings")
        sev_icon = {"high": "🔴", "medium": "🟡", "low": "🔵"}
        for w in validation_warnings:
            icon = sev_icon.get(w["severity"], "⚪")
            st.warning(f"{icon} **{w['column']}** — {w['issue']}: {w['detail']}")

    st.divider()

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

    if prof.get("numeric_summary"):
        st.markdown("#### Numeric Column Summaries")
        import pandas as pd
        num_df = pd.DataFrame(prof["numeric_summary"]).T.reset_index().rename(columns={"index": "Column"})
        st.dataframe(num_df, use_container_width=True)

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

    if industry_context:
        obj = industry_context.get("executive_objectives", [])
        if obj:
            st.caption("Executive objectives: " + " · ".join(obj[:3]))

    if calc_kpis:
        st.markdown("#### Calculated KPIs")
        cols = st.columns(min(len(calc_kpis), 3))
        for i, (name, value) in enumerate(calc_kpis.items()):
            emoji, bench_note = get_kpi_status(dataset_type, name, value)
            label = f"{emoji} {name}" if emoji else name
            cols[i % 3].metric(label, value, help=bench_note or None)

        narrative = st.session_state.kpi_narrative
        if narrative:
            st.divider()
            st.markdown("#### 🤖 AI Analysis")
            st.markdown(narrative)
        st.divider()

    st.markdown("#### All Recommended KPIs")
    for i, kpi in enumerate(kpis, 1):
        st.markdown(f"**{i}. {kpi['name']}** — {kpi['description']}")

# ── Tab 5: Charts ─────────────────────────────────────────────────────────────
with tabs[4]:
    st.subheader("Auto-generated Charts")
    if not figures:
        st.info("No charts could be generated from this dataset.")
    else:
        if chart_specs:
            st.caption(
                f"{len(chart_specs)} chart(s) selected from scoring "
                f"(min score 60, max 8). "
                f"{sum(1 for s in chart_specs if s.include_in_pdf)} qualify for PDF export."
            )
        for title, fig in figures.items():
            spec = next((s for s in (chart_specs or []) if s.title == title), None)
            if spec:
                st.markdown(
                    f"#### {title}  "
                    f"<span style='font-size:0.8em; color:gray'>Score: {spec.score} · {spec.chart_type}</span>",
                    unsafe_allow_html=True,
                )
                st.caption(f"_{spec.business_question}_")
            else:
                st.markdown(f"#### {title}")
            st.plotly_chart(fig, use_container_width=True)

# ── Tab 6: Insights ───────────────────────────────────────────────────────────
with tabs[5]:
    st.subheader("Business Insights")
    if not insights:
        st.info("No insights generated. Ensure domain KPIs are present in the dataset.")
    else:
        priority_colors = {"High": "🔴", "Medium": "🟡", "Low": "🟢"}
        _evidence_colors = {
            "OBSERVED":   ("green",  "OBSERVED"),
            "INFERRED":   ("blue",   "INFERRED"),
            "BENCHMARK":  ("orange", "BENCHMARK"),
            "HYPOTHESIS": ("gray",   "HYPOTHESIS"),
        }
        for insight in insights:
            icon = priority_colors.get(insight.priority, "⚪")
            ev_type = getattr(insight, "evidence_type", "") or ""
            ev_color, ev_label = _evidence_colors.get(ev_type, ("gray", ev_type or "—"))
            ev_badge = (
                f" <span style='background:{ev_color};color:white;padding:1px 6px;"
                f"border-radius:4px;font-size:0.75em;font-weight:bold'>{ev_label}</span>"
                if ev_type else ""
            )
            expander_label = f"{icon} **{insight.title}** — {insight.category}"
            with st.expander(expander_label, expanded=insight.priority == "High"):
                if ev_type:
                    st.markdown(
                        f"**Evidence type:** {ev_badge}",
                        unsafe_allow_html=True,
                    )
                col_a, col_b = st.columns([3, 2])
                with col_a:
                    st.markdown(f"**Finding:** {insight.finding}")
                    st.markdown(f"**Why it matters:** {insight.so_what}")
                    st.markdown(f"**Business impact:** {insight.business_impact}")
                with col_b:
                    st.metric("Financial Impact", insight.financial_impact)
                    st.metric("Priority", f"{icon} {insight.priority}")
                    st.caption(f"Confidence: {int(insight.confidence_score * 100)}%")
                st.divider()
                st.markdown(f"**Recommended Action:** {insight.recommended_action}")
                st.markdown(f"**Expected Outcome:** {insight.expected_outcome}")
                if insight.supporting_evidence:
                    st.caption("Supporting evidence: " + " · ".join(insight.supporting_evidence[:3]))

    if recommendations:
        st.divider()
        st.subheader("Top Recommendations")
        priority_rank = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
        for i, rec in enumerate(recommendations, 1):
            icon = {"Critical": "🚨", "High": "🔴", "Medium": "🟡", "Low": "🟢"}.get(rec.priority, "⚪")
            st.markdown(f"**{i}. {icon} {rec.action}**")
            r1, r2, r3 = st.columns(3)
            r1.caption(f"Owner: {rec.owner}")
            r2.caption(f"Timeline: {rec.timeline}")
            r3.caption(f"Benefit: {rec.estimated_benefit}")
            st.caption(f"Expected outcome: {rec.expected_outcome}")
            st.markdown("---")

# ── Tab 7: Impact ─────────────────────────────────────────────────────────────
with tabs[6]:
    st.subheader("Financial & Operational Impact")

    if financial_impact and financial_impact.has_quantifiable_impact:
        st.markdown("### 💰 Financial Impact")
        fi_col1, fi_col2, fi_col3 = st.columns(3)
        fi_col1.metric(
            "Revenue at Risk",
            f"${financial_impact.total_revenue_at_risk:,.0f}" if financial_impact.total_revenue_at_risk else "—",
        )
        fi_col2.metric(
            "Revenue Opportunity",
            f"${financial_impact.total_revenue_opportunity:,.0f}" if financial_impact.total_revenue_opportunity else "—",
        )
        fi_col3.metric(
            "Cost Savings",
            f"${financial_impact.total_cost_savings:,.0f}" if financial_impact.total_cost_savings else "—",
        )
        st.caption(financial_impact.summary_statement)

        if financial_impact.findings:
            st.markdown("#### Impact Breakdown")
            for finding in financial_impact.findings:
                cat_icon = {"Revenue at Risk": "🔴", "Revenue Opportunity": "🟢",
                            "Cost Savings": "🔵", "Capacity Recovery": "🟡"}.get(finding.category, "⚪")
                with st.expander(f"{cat_icon} {finding.title} — {finding.amount_formatted}"):
                    st.markdown(finding.description)
                    st.caption(f"Assumption: {finding.assumption}")
                    st.caption(f"Confidence: {int(finding.confidence * 100)}% · Priority: {finding.priority}")
    elif financial_impact:
        st.info(financial_impact.summary_statement or "Financial impact could not be quantified for this dataset.")
    else:
        st.info("Financial impact analysis not available.")

    st.divider()

    if operational_impact and operational_impact.findings:
        st.markdown("### ⚙️ Operational Impact")
        op_cols = st.columns(3)
        if operational_impact.capacity_utilization_pct is not None:
            op_cols[0].metric("Capacity Utilization", f"{operational_impact.capacity_utilization_pct:.0f}%")
        if operational_impact.throughput_gap_description:
            op_cols[1].metric("Throughput Gap", operational_impact.throughput_gap_description)
        if operational_impact.backlog_risk_level:
            op_cols[2].metric("Backlog Risk", operational_impact.backlog_risk_level)

        st.caption(operational_impact.summary_statement)

        for finding in operational_impact.findings:
            sev_icon = {"High": "🔴", "Medium": "🟡", "Low": "🟢"}.get(finding.severity, "⚪")
            with st.expander(f"{sev_icon} {finding.title} [{finding.category}]"):
                st.markdown(f"**Finding:** {finding.finding}")
                st.markdown(f"**Impact:** {finding.impact}")
                st.markdown(f"**Recommendation:** {finding.recommendation}")
                if finding.metric_name and finding.metric_value:
                    cols2 = st.columns(2)
                    cols2[0].caption(f"Metric: {finding.metric_name} = {finding.metric_value}")
                    if finding.benchmark:
                        cols2[1].caption(f"Benchmark: {finding.benchmark}")
    elif operational_impact:
        st.info(operational_impact.summary_statement or "No operational issues detected.")
    else:
        st.info("Operational impact analysis not available.")

# ── Tab 8: Summary ────────────────────────────────────────────────────────────
with tabs[7]:
    st.subheader("Executive Summary")

    if qa_result:
        qa_color = {"Ready to Deliver": "green", "Needs Minor Review": "orange", "Needs Major Review": "red"}.get(
            qa_result.delivery_readiness, "gray"
        )
        st.markdown(
            f"**QA Score:** {qa_result.overall_score:.0f}/100 — "
            f"<span style='color:{qa_color}'>{qa_result.delivery_readiness}</span>",
            unsafe_allow_html=True,
        )

    if st.session_state.summary is None:
        if st.button("Generate Executive Summary", type="primary"):
            payload = build_safe_summary_payload(prof, dataset_type, kpis, pii_report, calc_kpis)
            st.caption("Claude is writing your report — text will appear below as it generates.")
            full = st.write_stream(stream_executive_summary(payload))
            st.session_state.summary = full
            # Re-run QA now that summary exists
            st.session_state.qa_result = validate_report(
                insights, figures, calc_kpis, full,
                financial_impact, operational_impact,
                opportunities=opportunities,
            )
            st.rerun()
    if st.session_state.summary:
        st.markdown(st.session_state.summary)

# ── Tab 9: Opportunities ──────────────────────────────────────────────────────
with tabs[8]:
    st.subheader("Ranked Business Opportunities")
    if not opportunities:
        st.info("Run the analysis pipeline to generate scored opportunities.")
    else:
        import pandas as pd
        opp_rows = []
        for o in opportunities:
            opp_rows.append({
                "Initiative": o.initiative[:80] + ("…" if len(o.initiative) > 80 else ""),
                "Score": o.opportunity_score,
                "Rank": o.rank,
                "Expected Impact": o.expected_impact,
                "Difficulty": o.implementation_difficulty,
                "Timeline": o.timeline,
                "Owner": o.owner,
            })
        opp_df = pd.DataFrame(opp_rows)
        rank_icons = {"High": "🔴", "Medium": "🟡", "Low": "🟢"}
        st.dataframe(
            opp_df.style.format({"Score": "{:.1f}"}),
            use_container_width=True,
            hide_index=True,
        )
        st.divider()
        st.markdown("#### Opportunity Details")
        for o in opportunities:
            rank_icon = rank_icons.get(o.rank, "⚪")
            with st.expander(f"{rank_icon} [{o.rank}] {o.initiative[:100]}"):
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Opportunity Score", f"{o.opportunity_score:.1f}")
                c2.metric("Impact Score", f"{o.impact_score:.1f}")
                c3.metric("Confidence", f"{o.confidence:.0f}%")
                c4.metric("Effort Score", f"{o.effort_score:.1f}")
                st.caption(f"Owner: **{o.owner}** · Timeline: **{o.timeline}** · Difficulty: **{o.implementation_difficulty}**")

# ── Tab 10: Scenarios ─────────────────────────────────────────────────────────
with tabs[9]:
    st.subheader("Scenario Models — Top Opportunities")
    if not scenarios:
        st.info("No scenario models available. Run the analysis pipeline first.")
    else:
        for sm in scenarios:
            with st.expander(f"📐 {sm.initiative[:100]}", expanded=False):
                st.markdown(f"**Recommendation:** {sm.recommendation}")
                st.divider()
                sc1, sc2, sc3 = st.columns(3)

                def _fmt_scenario(s) -> None:
                    label_color = {"Best Case": "green", "Expected Case": "blue", "Worst Case": "red"}.get(s.name, "gray")
                    st.markdown(
                        f"<span style='color:{label_color};font-weight:bold'>{s.name}</span> "
                        f"<small>({s.probability} probability)</small>",
                        unsafe_allow_html=True,
                    )
                    if s.revenue_impact > 0:
                        rev = s.revenue_impact
                        rev_str = f"${rev/1_000_000:.1f}M" if rev >= 1_000_000 else (f"${rev/1_000:.0f}K" if rev >= 1_000 else f"${rev:,.0f}")
                        st.metric("Revenue Impact", rev_str)
                    if s.cost_impact > 0:
                        ci = s.cost_impact
                        ci_str = f"${ci/1_000_000:.1f}M" if ci >= 1_000_000 else (f"${ci/1_000:.0f}K" if ci >= 1_000 else f"${ci:,.0f}")
                        st.metric("Implementation Cost", ci_str)
                    st.caption(f"Efficiency: {s.efficiency_impact}")
                    if s.assumptions:
                        st.markdown("**Assumptions:**")
                        for a in s.assumptions:
                            st.caption(f"• {a}")

                with sc1:
                    _fmt_scenario(sm.best_case)
                with sc2:
                    _fmt_scenario(sm.expected_case)
                with sc3:
                    _fmt_scenario(sm.worst_case)

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
                    kpis={"recommended": kpis, "calculated": calc_kpis,
                          "narrative": st.session_state.kpi_narrative or ""},
                    charts_metadata={"titles": list(figures.keys())},
                    summary=st.session_state.summary,
                    extra={
                        "metadata":              metadata,
                        "pii_report":            pii_report,
                        "domain":                dataset_type,
                        "figures":               {t: __import__("plotly.io", fromlist=["to_json"]).to_json(f)
                                                  for t, f in figures.items()},
                        "sanitized_csv":         sanitized_df.to_csv(index=False),
                        "client_drive_folder_id": st.session_state.client_drive_folder_id,
                        "qa_score":              qa_result.overall_score if qa_result else None,
                        "qa_readiness":          qa_result.delivery_readiness if qa_result else None,
                        "qa_result_detail": {
                            "insight_quality_score": qa_result.insight_quality_score,
                            "chart_quality_score":   qa_result.chart_quality_score,
                            "kpi_relevance_score":   qa_result.kpi_relevance_score,
                            "completeness_score":    qa_result.completeness_score,
                            "strengths":             qa_result.strengths,
                            "issues": [
                                {"severity": i.severity, "category": i.category, "description": i.description}
                                for i in qa_result.issues
                            ],
                            "recommendations":       qa_result.recommendations,
                        } if qa_result else None,
                    },
                )
                st.session_state.dashboard_id = did
            st.success(f"Dashboard saved! ID: `{did}`")
            st.info("Go to the **Admin Review** page to review before sending to your client.")
