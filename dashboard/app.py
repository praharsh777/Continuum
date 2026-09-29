"""
Continuum — Streamlit Dashboard
Implements FR-9: Visualizing Incident Feed, Memory Recall, Diagnosis, Confidence Scoring, and Live Resolution.
"""

import json
import os
import sys
import time
from pathlib import Path
import streamlit as st

# Ensure project root is on sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv
load_dotenv()

from agent.db import (
    get_diagnosis,
    get_incident,
    get_incident_full_detail,
    get_postmortem,
    get_resolution,
    init_db,
    list_incidents,
    update_incident_status,
)
from agent.diagnosis import default_diagnosis_service
from agent.memory import default_memory_manager
from agent.postmortem import default_postmortem_service
from scripts.reset_demo_state import reset_and_seed

# Initialize DB if not created
init_db()

# Page configuration
st.set_page_config(
    page_title="Continuum — Incident Memory Agent",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for styling
st.markdown("""
<style>
    .reportview-container {
        background: #0f1117;
    }
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #f0f6fc;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #8b949e;
        margin-bottom: 1.5rem;
    }
    .badge-sev1 { background-color: #ff4b4b; color: white; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 0.8rem; }
    .badge-sev2 { background-color: #ff8c00; color: white; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 0.8rem; }
    .badge-sev3 { background-color: #e3b341; color: black; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 0.8rem; }
    .badge-sev4 { background-color: #58a6ff; color: white; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 0.8rem; }
    
    .badge-open { background-color: #f85149; color: white; padding: 3px 10px; border-radius: 12px; font-size: 0.85rem; font-weight: 600; }
    .badge-resolved { background-color: #238636; color: white; padding: 3px 10px; border-radius: 12px; font-size: 0.85rem; font-weight: 600; }
    
    .match-found-card {
        background-color: rgba(35, 134, 54, 0.15);
        border: 1px solid #238636;
        border-radius: 8px;
        padding: 14px;
        margin-bottom: 15px;
    }
    .match-none-card {
        background-color: rgba(110, 118, 129, 0.12);
        border: 1px solid #6e7681;
        border-radius: 8px;
        padding: 14px;
        margin-bottom: 15px;
    }
    .confidence-high { color: #3fb950; font-weight: bold; }
    .confidence-med { color: #d29922; font-weight: bold; }
    .confidence-none { color: #8b949e; font-style: italic; }
</style>
""", unsafe_allow_html=True)


# -------------------------------------------------------------
# Sidebar: Controls, Demo Script, and Rehearsal Reset
# -------------------------------------------------------------
with st.sidebar:
    st.image("https://ui.hindsight.vectorize.io/favicon.ico", width=36)
    st.title("Continuum")
    st.caption("Incident Response with Persistent Institutional Memory")
    st.markdown("---")

    st.subheader("⚙️ Memory Settings")
    recall_slider = st.slider(
        "Hindsight Recall Top-N Window",
        min_value=2,
        max_value=10,
        value=5,
        step=1,
        help="FR-3: Number of relevant historical incident postmortems to recall from Hindsight Cloud."
    )

    st.markdown("---")
    st.subheader("🎯 Demo Arc Quick-Select")
    st.markdown(
        """
        - **Incident A** (`INC-DEMO-A`): Novel incident (zero prior memory).
        - **Incident B** (`INC-DEMO-B`): Repeat of A (different phrasing).
        - **Incident C** (`INC-DEMO-C`): False-match distractor.
        """
    )
    demo_choice = st.selectbox(
        "Jump to Demo Incident:",
        options=["Select Demo Incident...", "Incident A (INC-DEMO-A)", "Incident B (INC-DEMO-B)", "Incident C (INC-DEMO-C)"]
    )
    if demo_choice != "Select Demo Incident...":
        selected_demo_id = demo_choice.split("(")[1].replace(")", "")
        st.session_state["selected_incident_id"] = selected_demo_id

    st.markdown("---")
    st.subheader("🔄 Demo State Reset (NFR-4)")
    st.caption("Resets SQLite tables, purges Hindsight demo memory bank, and reseeds the 50-incident dataset.")
    if st.button("Reset Demo State to Clean Arc", type="primary", use_container_width=True):
        with st.spinner("Purging Hindsight bank and reseeding SQLite dataset..."):
            reset_and_seed(retain_historical_in_hindsight=True, max_retained_history=10)
            st.success("Clean state restored! Demo arc ready.")
            st.rerun()

    st.markdown("---")
    st.caption(f"Bank: `{default_memory_manager.bank_id}`")
    st.caption(f"Primary LLM: `{default_diagnosis_service.primary_model}`")


# -------------------------------------------------------------
# Main View: Incident Feed & Deep Inspection
# -------------------------------------------------------------
st.markdown('<div class="main-header">Continuum Operations Dashboard</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Live incident triage and memory-grounded diagnosis powered by Hindsight Cloud</div>', unsafe_allow_html=True)

# Filters for Incident Feed
f_col1, f_col2, f_col3 = st.columns([2, 2, 3])
with f_col1:
    status_filter = st.selectbox("Status Filter", ["ALL", "OPEN", "RESOLVED"])
with f_col2:
    services_list = ["ALL"] + sorted(list({inc["service_name"] for inc in list_incidents(limit=200)}))
    service_filter = st.selectbox("Service Filter", services_list)

# Load Incidents from SQLite
filter_status = None if status_filter == "ALL" else status_filter
filter_svc = None if service_filter == "ALL" else service_filter
incidents = list_incidents(status=filter_status, service_name=filter_svc, limit=100)

if not incidents:
    st.warning("No incidents found matching current filters. Click 'Reset Demo State' in the sidebar to seed the dataset.")
    st.stop()

# Layout: Split into Incident Feed (Left) and Detail View (Right)
col_feed, col_detail = st.columns([4, 7])

with col_feed:
    st.subheader(f"Incident Feed ({len(incidents)})")
    
    # Store selected incident in session state
    if "selected_incident_id" not in st.session_state:
        st.session_state["selected_incident_id"] = incidents[0]["incident_id"]

    for inc in incidents:
        inc_id = inc["incident_id"]
        is_selected = (inc_id == st.session_state["selected_incident_id"])
        
        # Determine badges
        sev = inc["severity"]
        status = inc["status"]
        status_color = "badge-open" if status == "OPEN" else "badge-resolved"
        
        demo_tag = " 🌟 [DEMO]" if "DEMO" in inc_id else ""
        button_label = f"[{sev}] {inc_id} · {inc['service_name']}{demo_tag}"
        
        card_border = "2px solid #58a6ff" if is_selected else "1px solid #30363d"
        
        with st.container():
            btn_clicked = st.button(
                button_label,
                key=f"feed_btn_{inc_id}",
                help=inc["symptoms"][:100],
                use_container_width=True
            )
            if btn_clicked:
                st.session_state["selected_incident_id"] = inc_id
                st.rerun()


# -------------------------------------------------------------
# Right Panel: Detailed Incident Analysis & Diagnosis
# -------------------------------------------------------------
with col_detail:
    current_inc_id = st.session_state.get("selected_incident_id", incidents[0]["incident_id"])
    detail = get_incident_full_detail(current_inc_id)

    if not detail or not detail.get("incident"):
        st.error(f"Incident {current_inc_id} could not be loaded.")
        st.stop()

    inc = detail["incident"]
    diag = detail.get("diagnosis")
    res = detail.get("resolution")
    pm = detail.get("postmortem")

    # Header Row
    h_col1, h_col2 = st.columns([6, 3])
    with h_col1:
        st.markdown(f"### {inc['incident_id']} — `{inc['service_name']}`")
        sev = inc["severity"]
        status = inc["status"]
        st.markdown(
            f'<span class="badge-{sev.lower()}">{sev}</span> &nbsp;&nbsp; '
            f'<span class="{"badge-open" if status == "OPEN" else "badge-resolved"}">{status}</span> &nbsp;&nbsp; '
            f'<small style="color: #8b949e;">Reported: {inc["created_at"]}</small>',
            unsafe_allow_html=True
        )
    with h_col2:
        if "DEMO" in inc["incident_id"]:
            st.info(f"🎯 Demonstration Target: `{inc['incident_id']}`")

    st.markdown("---")

    # Symptoms and Logs
    st.markdown("**Symptoms Observed:**")
    st.info(inc["symptoms"])

    if inc.get("log_excerpt"):
        with st.expander("📄 Diagnostic Log Excerpts", expanded=True):
            st.code(inc["log_excerpt"], language="log")

    st.markdown("---")

    # ---------------------------------------------------------
    # Diagnosis Section
    # ---------------------------------------------------------
    st.subheader("🔍 Institutional Memory & Diagnosis")

    # Re-run or Run Diagnosis Button
    action_col1, action_col2 = st.columns([4, 5])
    with action_col1:
        run_diag_btn = st.button("Run Hindsight Memory Diagnosis", type="primary", use_container_width=True)

    if run_diag_btn:
        with st.spinner(f"Querying Hindsight Cloud (Top-{recall_slider}) and analyzing with Groq..."):
            diagnosis_result = default_diagnosis_service.diagnose_incident(
                incident=inc,
                recall_top_n=recall_slider
            )
            st.session_state[f"last_diag_{current_inc_id}"] = diagnosis_result
            st.rerun()

    # Load diagnosis from SQLite or session state
    active_diag = st.session_state.get(f"last_diag_{current_inc_id}") or diag

    if active_diag:
        # Visual Distinction: Matched vs Unmatched
        matches_pattern = active_diag.get("matches_known_pattern", False)
        cited_ids = active_diag.get("cited_incident_ids") or active_diag.get("cited_memory_ids") or []
        if isinstance(cited_ids, str):
            try:
                cited_ids = json.loads(cited_ids)
            except Exception:
                cited_ids = []

        if matches_pattern and len(cited_ids) > 0:
            st.markdown(
                f"""
                <div class="match-found-card">
                    <h4 style="margin: 0; color: #3fb950;">🟢 Matched to {len(cited_ids)} Historical Incident(s)</h4>
                    <p style="margin-top: 5px; margin-bottom: 0; font-size: 0.95rem;">
                        <strong>Historical Precedents Cited:</strong> <code>{', '.join(cited_ids)}</code>
                    </p>
                </div>
                """,
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                """
                <div class="match-none-card">
                    <h4 style="margin: 0; color: #8b949e;">⚪ No Relevant Historical Precedent Found</h4>
                    <p style="margin-top: 5px; margin-bottom: 0; font-size: 0.95rem;">
                        This incident appears novel to the institutional memory bank. No historical match was fabricated.
                    </p>
                </div>
                """,
                unsafe_allow_html=True
            )

        # Root Cause & Suggested Fix
        rc_col, fix_col = st.columns(2)
        with rc_col:
            st.markdown("##### 🧬 Root-Cause Hypothesis")
            st.markdown(active_diag.get("root_cause_hypothesis", "N/A"))
        with fix_col:
            st.markdown("##### 🛠️ Suggested Fix Remediation")
            st.markdown(active_diag.get("suggested_fix", "N/A"))

        # Confidence Score Panel (FR-5)
        st.markdown("##### 📊 Fix Confidence Score")
        conf_score = active_diag.get("confidence_score")
        conf_label = active_diag.get("confidence_label", "No prior track record")

        c_box1, c_box2 = st.columns([3, 6])
        with c_box1:
            if conf_score is not None:
                score_pct = int(conf_score * 100)
                st.metric("Confidence", f"{score_pct}%", delta=f"{conf_score:.2f}")
            else:
                st.metric("Confidence", "NULL", help="First time this fix is suggested — no prior track record in Hindsight.")
        with c_box2:
            st.markdown(f"**Track Record Assessment:**\n`{conf_label}`")
            if active_diag.get("supporting_records"):
                with st.expander("View Supporting Historical Precedents"):
                    for rec in active_diag["supporting_records"]:
                        st.markdown(f"- **{rec['incident_id']}**: Outcome `{rec['outcome']}` — *{rec.get('text_snippet', '')}*")

        # Telemetry / Latency info
        latency = active_diag.get("latency_seconds")
        model = active_diag.get("model_used", default_diagnosis_service.primary_model)
        if latency:
            st.caption(f"⏱️ Diagnosis generated in **{latency}s** using `{model}` (Target: ≤ 3.0s)")

        # Recalled Memories Accordion
        recalled = active_diag.get("recalled_memories", [])
        if recalled:
            with st.expander(f"📚 Recalled Hindsight Memories ({len(recalled)})", expanded=False):
                for idx, m in enumerate(recalled, 1):
                    doc_id = m.get("document_id") or m.get("metadata", {}).get("incident_id", "N/A")
                    st.markdown(f"**[{idx}] Source Document:** `{doc_id}` | Memory ID: `{m.get('id', 'N/A')}`")
                    st.markdown(f"> {m.get('text', '')}")
                    if m.get("scores"):
                        st.caption(f"Relevance: {m['scores']}")
                    st.markdown("---")
    else:
        st.info("No diagnosis generated yet. Click 'Run Hindsight Memory Diagnosis' above.")

    st.markdown("---")

    # ---------------------------------------------------------
    # Resolution & Live Postmortem Loop (FR-6)
    # ---------------------------------------------------------
    st.subheader("🏁 Incident Resolution & Memory Retention Loop")

    if inc["status"] == "RESOLVED":
        st.success(f"✅ Incident {current_inc_id} is marked RESOLVED.")
        if res:
            st.markdown(f"**Fix Applied:** `{res['fix_applied']}`")
            st.markdown(f"**Outcome:** `{res['outcome']}` | **Resolved At:** {res['resolved_at']}")
        if pm:
            st.markdown("##### 📝 Retained Postmortem Narrative")
            st.info(pm["narrative_summary"])
            st.caption(f"Retained in Hindsight Bank: `{default_memory_manager.bank_id}` (ID: `{pm.get('retained_memory_id')}`)")
    else:
        with st.form(key=f"resolve_form_{current_inc_id}"):
            suggested_default = active_diag.get("suggested_fix", "") if active_diag else ""
            fix_input = st.text_area(
                "Remediation / Fix Applied:",
                value=suggested_default,
                help="Enter the exact fix steps applied to resolve this incident."
            )
            outcome_input = st.selectbox(
                "Resolution Outcome:",
                ["RESOLVED", "DID_NOT_RESOLVE"],
                index=0
            )

            resolve_submit = st.form_submit_button("Mark Incident Resolved & Retain Postmortem", type="primary")

            if resolve_submit:
                if not fix_input.strip():
                    st.error("Please specify the fix applied before resolving.")
                else:
                    with st.spinner("Synthesizing postmortem and retaining memory in Hindsight Cloud..."):
                        start_res = time.time()
                        res_outcome = default_postmortem_service.resolve_incident(
                            incident_id=current_inc_id,
                            fix_applied=fix_input,
                            outcome=outcome_input,
                            time_to_resolve_seconds=int(time.time() - start_res)
                        )
                        st.success(f"Incident {current_inc_id} marked {outcome_input}! Postmortem retained into Hindsight Cloud live.")
                        time.sleep(1)
                        st.rerun()
