"""
Streamlit demo for SignalGuard (Capability 5 -- UI).

Talks to the FastAPI service over HTTP, not by importing pipeline
functions directly -- this is a genuine API client, demonstrating the
API layer's value rather than bypassing it. The FastAPI server must be
running separately:

    uv run uvicorn signalguard.api.app:app --reload

Then:

    uv run streamlit run app/streamlit_app.py

The synthetic benchmark is generated locally (fast, deterministic, no
API cost) -- only the actual detection work goes through the FastAPI
service, requiring VOYAGE_API_KEY and ANTHROPIC_API_KEY to be configured
in .secrets. Without them, the Baseline QC workspace still works (no
external API needed); only AI Investigation requires live keys.

Structure: a compact header (brand + live API-connection status) rather
than a permanent sidebar info panel, three metric cards summarizing the
loaded benchmark, and each capability inside its own bordered workspace
container (st.container(border=True) -- native Streamlit, so the action
button lives genuinely inside the card rather than floating below raw
HTML). Deterministic-vs-AI-assisted framing is a small badge on each
workspace, since it is real categorical information, not decoration.
Developer-oriented technical detail is moved into a "How this works"
disclosure rather than sitting in the primary copy.
"""

from __future__ import annotations

from typing import Any, Dict, List

import requests
import streamlit as st

from signalguard.data.generator import generate_clean_dataset
from signalguard.data.injector import inject_defects

INVESTIGABLE_TYPES = ["session.completed", "session.no_show", "task.completed", "followup.required"]

_SHIELD_ICON = (
    '<svg width="34" height="34" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">'
    '<path d="M12 2L4 5v6c0 5.25 3.4 9.74 8 11 4.6-1.26 8-5.75 8-11V5l-8-3z" fill="#1a5c3a"/>'
    '<path d="M9.3 12.4l1.9 1.9 3.8-4.2" stroke="#F7F5F0" stroke-width="1.7" '
    'stroke-linecap="round" stroke-linejoin="round" fill="none"/>'
    "</svg>"
)

_CUSTOM_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@600;700&family=Outfit:wght@300;400;500;600;700&family=DM+Mono:wght@400;500&display=swap');

    :root {
        --sg-green: #1a5c3a;
        --sg-green-dark: #14472e;
        --sg-ink: #0e0e0d;
        --sg-canvas: #f7f5f0;
        --sg-surface: #ffffff;
        --sg-soft: #ece8df;
        --sg-muted: #6d706b;
        --sg-border: #ddd9d0;
        --sg-radius: 14px;
    }

    #MainMenu, footer { visibility: hidden; }

    .stApp, [data-testid="stAppViewContainer"], body {
        background: var(--sg-canvas) !important;
        color: var(--sg-ink) !important;
        font-family: 'Outfit', -apple-system, sans-serif !important;
    }

    [data-testid="stMainBlockContainer"], .block-container {
        max-width: 1180px !important;
        padding-top: 2.2rem;
        padding-bottom: 4rem;
        margin: 0 auto;
    }

    [data-testid="stMarkdownContainer"] p, [data-testid="stMarkdownContainer"] li {
        font-family: 'Outfit', sans-serif !important;
        font-size: 17px !important;
        line-height: 1.7 !important;
        color: #2B2E29 !important;
    }

    .sg-brand-row { display: flex; align-items: center; gap: 0.7rem; }
    .sg-brand-name {
        font-family: 'Cormorant Garamond', serif !important;
        font-size: 34px !important; font-weight: 700 !important;
        color: var(--sg-ink) !important; margin: 0 !important; line-height: 1;
    }
    .sg-tagline {
        font-family: 'Outfit', sans-serif !important; font-weight: 400 !important;
        color: var(--sg-muted) !important; font-size: 16px !important; margin-top: 0.35rem !important;
    }

    .sg-metric-card {
        background: var(--sg-surface); border: 1px solid var(--sg-border);
        border-radius: var(--sg-radius); padding: 1.1rem 1.3rem;
    }
    .sg-metric-label {
        font-family: 'Outfit', sans-serif !important; font-size: 13px !important;
        font-weight: 600 !important; letter-spacing: 0.03em; color: var(--sg-muted) !important;
        margin-bottom: 0.3rem !important;
    }
    .sg-metric-value {
        font-family: 'DM Mono', monospace !important; font-size: 30px !important;
        font-weight: 600 !important; color: var(--sg-ink) !important; line-height: 1.15;
    }
    .sg-metric-sublabel {
        font-family: 'Outfit', sans-serif !important; font-size: 14px !important;
        color: var(--sg-muted) !important; margin-top: 0.2rem !important;
    }

    .sg-workspace-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.2rem; }
    .sg-workspace-title {
        font-family: 'Outfit', sans-serif !important; font-size: 20px !important;
        font-weight: 700 !important; color: var(--sg-ink) !important;
    }
    .sg-workspace-subtitle {
        font-family: 'Outfit', sans-serif !important; font-size: 15px !important;
        font-weight: 500 !important; color: var(--sg-muted) !important; margin-bottom: 0.7rem !important;
    }
    .sg-section-title {
        font-family: 'Outfit', sans-serif !important; font-weight: 700 !important;
        font-size: 20px !important; color: var(--sg-ink) !important; margin: 1.6rem 0 0.9rem 0 !important;
    }

    .sg-badge {
        display: inline-block; padding: 0.3rem 0.85rem; border-radius: 5px;
        font-family: 'Outfit', sans-serif !important; font-size: 13px !important;
        font-weight: 600 !important; white-space: nowrap;
    }
    .sg-badge-deterministic { background: var(--sg-soft); color: #5B5E58 !important; border: 1px solid var(--sg-border); }
    .sg-badge-ai { background: #EAF2EC; color: var(--sg-green-dark) !important; border: 1px solid var(--sg-green); }
    .sg-badge-fact { background: var(--sg-soft); color: #5B5E58 !important; border: 1px solid var(--sg-border); }
    .sg-badge-documented { background: #EAF2EC; color: var(--sg-green-dark) !important; border: 1px solid var(--sg-green); }
    .sg-badge-interpretation { background: #FBF3E3; color: #8A6A1E !important; border: 1px solid #B8923A; }

    .sg-mono { font-family: 'DM Mono', monospace !important; font-size: 16px !important; color: var(--sg-ink) !important; }

    .sg-card {
        border: 1px solid var(--sg-border); border-left: 4px solid var(--sg-green); background: var(--sg-surface);
        padding: 1.5rem 1.7rem; border-radius: 10px; margin-bottom: 1rem;
        box-shadow: 0 2px 8px rgba(14,14,13,0.06);
    }
    .sg-card-violation { border-left-color: #8B3A3A; }
    .sg-card-clean { border-left-color: #7A9B7E; }
    .sg-card-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.9rem; }
    .sg-field-label {
        font-family: 'Outfit', sans-serif !important; color: var(--sg-muted) !important;
        font-size: 14px !important; font-weight: 500 !important; margin-bottom: 0.25rem !important;
    }
    .sg-field-value {
        font-family: 'Outfit', sans-serif !important; font-size: 16px !important;
        margin-bottom: 0.9rem !important; color: var(--sg-ink) !important;
    }
    .sg-record-panel {
        border: 1px solid var(--sg-border); background: var(--sg-soft); padding: 1.1rem 1.4rem;
        border-radius: 10px; margin: 0.6rem 0 1rem 0;
    }

    div[data-testid="stVerticalBlockBorderWrapper"] {
        background: var(--sg-surface); border-radius: var(--sg-radius) !important;
        border-color: var(--sg-border) !important;
    }

    .stButton > button, .stButton > button p, .stButton > button span, .stButton > button div {
        font-family: 'Outfit', sans-serif !important; font-weight: 600 !important;
        font-size: 16px !important; color: #FFFFFF !important;
    }
    .stButton > button {
        background: var(--sg-green) !important; border: none !important; border-radius: 8px !important;
        padding: 0.7rem 1.5rem !important; transition: background 0.15s ease, transform 0.15s ease;
    }
    .stButton > button:hover { background: var(--sg-green-dark) !important; transform: translateY(-1px); }

    [data-baseweb="select"] > div {
        font-family: 'Outfit', sans-serif !important; font-size: 16px !important;
        border-radius: 8px !important; border-color: var(--sg-border) !important;
    }
    [data-baseweb="select"] * { font-size: 16px !important; }

    [data-testid="stTextInput"] input {
        font-family: 'DM Mono', monospace !important; font-size: 15px !important; border-radius: 8px !important;
    }

    [data-baseweb="tab-list"] { gap: 2rem; border-bottom: 1px solid var(--sg-border); }
    [data-baseweb="tab"] {
        font-family: 'Outfit', sans-serif !important; font-size: 17px !important;
        font-weight: 600 !important; color: var(--sg-muted) !important; padding: 0.8rem 0.1rem;
    }
    [data-baseweb="tab"] p { font-size: 17px !important; font-weight: 600 !important; }
    [aria-selected="true"][data-baseweb="tab"], [aria-selected="true"][data-baseweb="tab"] p { color: var(--sg-green) !important; }
    [data-baseweb="tab-highlight"] { background-color: var(--sg-green) !important; height: 3px; }

    [data-testid="stCaptionContainer"] p {
        font-family: 'Outfit', sans-serif !important; font-size: 15px !important; color: var(--sg-muted) !important;
    }
</style>
"""


def _check_api_connected(base_url: str) -> bool:
    try:
        response = requests.get(f"{base_url}/health", timeout=2)
        return response.status_code == 200
    except requests.RequestException:
        return False


def _badge(label: str, css_class: str) -> str:
    return f'<span class="sg-badge {css_class}">{label}</span>'


def _reasoning_badge(category: str) -> str:
    labels = {
        "fact": ("Fact", "sg-badge-fact"),
        "documented_rule": ("Documented rule", "sg-badge-documented"),
        "ai_interpretation": ("AI interpretation", "sg-badge-interpretation"),
    }
    label, css_class = labels.get(category, (category, "sg-badge-fact"))
    return _badge(label, css_class)


def _metric_card(label: str, value: str, sublabel: str) -> str:
    return (
        '<div class="sg-metric-card">'
        f'<div class="sg-metric-label">{label}</div>'
        f'<div class="sg-metric-value">{value}</div>'
        f'<div class="sg-metric-sublabel">{sublabel}</div>'
        "</div>"
    )


def _record_panel(record: Dict[str, Any]) -> str:
    rows = "".join(
        f'<div class="sg-field-label">{key}</div><div class="sg-mono sg-field-value">{value}</div>'
        for key, value in record.items()
        if value is not None
    )
    return f'<div class="sg-record-panel">{rows}</div>'


def _finding_card(finding: Dict[str, Any]) -> str:
    badge = _reasoning_badge(finding.get("reasoning_category", "fact"))
    return (
        '<div class="sg-card sg-card-violation">'
        '<div class="sg-card-row">'
        f'<span class="sg-mono">{finding.get("defect_type", "")}</span>'
        f"{badge}"
        "</div>"
        '<div class="sg-field-label">Evidence</div>'
        f'<div class="sg-field-value">{finding.get("evidence", "")}</div>'
        '<div class="sg-field-label">Affected event ID(s)</div>'
        f'<div class="sg-mono sg-field-value">{", ".join(finding.get("affected_event_ids", []))}</div>'
        '<div class="sg-field-label">Recommended action</div>'
        f'<div class="sg-field-value">{finding.get("recommended_action", "")}</div>'
        "</div>"
    )


def _clean_card(message: str) -> str:
    return f'<div class="sg-card sg-card-clean sg-field-value" style="margin-bottom:0;">{message}</div>'


st.set_page_config(page_title="SignalGuard", layout="wide")
st.markdown(_CUSTOM_CSS, unsafe_allow_html=True)

if "api_base_url" not in st.session_state:
    st.session_state.api_base_url = "http://127.0.0.1:8000"


@st.cache_data
def load_benchmark():
    events = generate_clean_dataset(num_accounts=80, seed=42)
    records, answer_key = inject_defects(events, seed=7, instances_per_defect_type=5)
    return records, answer_key


records, answer_key = load_benchmark()

header_left, header_right = st.columns([5, 1])
with header_left:
    brand_html = (
        '<div class="sg-brand-row">'
        f"{_SHIELD_ICON}"
        '<p class="sg-brand-name">SignalGuard</p>'
        "</div>"
        '<p class="sg-tagline">Documentation-grounded data quality for event streams</p>'
    )
    st.markdown(brand_html, unsafe_allow_html=True)
with header_right:
    connected = _check_api_connected(st.session_state.api_base_url)
    status_label = "\U0001f7e2 API connected" if connected else "\U0001f534 API unreachable"
    with st.popover(status_label):
        st.text_input("API base URL", key="api_base_url")

api_base_url = st.session_state.api_base_url

st.divider()

m1, m2, m3 = st.columns(3)
with m1:
    st.markdown(_metric_card("Records", str(len(records)), "Dataset loaded"), unsafe_allow_html=True)
with m2:
    st.markdown(_metric_card("Seeded defects", str(len(answer_key)), "Hidden from pipeline"), unsafe_allow_html=True)
with m3:
    st.markdown(
        _metric_card("Detection mode", "Deterministic + AI", "Baseline QC and AI investigation"),
        unsafe_allow_html=True,
    )

st.write("")

tab_baseline, tab_investigate = st.tabs(["Baseline QC", "AI Investigation"])

with tab_baseline:
    with st.container(border=True):
        head_l, head_r = st.columns([4, 1])
        with head_l:
            st.markdown('<p class="sg-workspace-title">Baseline QC</p>', unsafe_allow_html=True)
        with head_r:
            st.markdown(_badge("Deterministic", "sg-badge-deterministic"), unsafe_allow_html=True)
        st.markdown('<p class="sg-workspace-subtitle">Schema &amp; structural validation</p>', unsafe_allow_html=True)
        st.write(
            "Detects duplicate IDs, missing required fields, and invalid event types "
            "using deterministic validation rules."
        )
        st.caption("No AI reasoning \u00b7 No documentation lookup")
        with st.expander("How this works"):
            st.write(
                "Runs Tier-1 schema and structural checks only. No LLM, no external API call, "
                "and no knowledge of the documented business rules -- by design, so this represents "
                "what schema validation alone can catch."
            )
        run_baseline = st.button("Run baseline QC", key="run_baseline")

    st.markdown('<p class="sg-section-title">Results</p>', unsafe_allow_html=True)
    if run_baseline:
        with st.spinner("Running deterministic checks..."):
            response = requests.post(f"{api_base_url}/qc/baseline", json={"records": records})
        if response.status_code != 200:
            st.error(f"Request failed: {response.status_code} {response.text}")
        else:
            findings: List[Dict[str, Any]] = response.json()["findings"]
            if not findings:
                st.markdown(_clean_card("No issues detected."), unsafe_allow_html=True)
            else:
                st.caption(f"{len(findings)} finding(s)")
                for finding in findings:
                    st.markdown(_finding_card(finding), unsafe_allow_html=True)
    else:
        st.caption("Run the baseline validation to inspect detected issues.")

with tab_investigate:
    with st.container(border=True):
        head_l, head_r = st.columns([4, 1])
        with head_l:
            st.markdown('<p class="sg-workspace-title">AI Investigation</p>', unsafe_allow_html=True)
        with head_r:
            st.markdown(_badge("AI-assisted", "sg-badge-ai"), unsafe_allow_html=True)
        st.markdown(
            '<p class="sg-workspace-subtitle">Evidence-grounded record investigation</p>', unsafe_allow_html=True
        )
        st.write(
            "Retrieves relevant documentation, extracts a structured rule (or abstains if "
            "nothing is documented), and executes a bounded tool to check for a violation."
        )
        st.caption("Documentation retrieval \u00b7 Claude reasoning \u00b7 Deterministic tool execution")
        with st.expander("How this works"):
            st.write(
                "The LLM never performs the check itself -- it selects which bounded tool "
                "applies and supplies rule-specific arguments; the actual pass/fail verdict "
                "is always computed by deterministic Python."
            )

        candidates = [r for r in records if r["event_type"] in INVESTIGABLE_TYPES]
        options = {
            f"{r['event_type']}  |  ref_id={r['ref_id']}  |  event_id={r['event_id']}": r for r in candidates
        }
        selected_label = st.selectbox("Choose a record to investigate", list(options.keys()))
        selected_record = options[selected_label]
        st.markdown(_record_panel(selected_record), unsafe_allow_html=True)

        run_investigate = st.button("Investigate this record", key="run_investigate")

    st.markdown('<p class="sg-section-title">Results</p>', unsafe_allow_html=True)
    if run_investigate:
        with st.spinner("Retrieving documentation, extracting rule, selecting tool... (live LLM call, ~5-10s)"):
            response = requests.post(
                f"{api_base_url}/qc/investigate",
                json={"candidate": selected_record, "all_records": records},
            )
        if response.status_code != 200:
            st.error(f"Request failed: {response.status_code} {response.text}")
        else:
            finding = response.json()["finding"]
            if finding is None:
                st.markdown(
                    _clean_card(
                        "No violation reported -- either the rule was satisfied, or the model "
                        "correctly found no documented rule for this question (abstention rather "
                        "than a fabricated answer)."
                    ),
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(_finding_card(finding), unsafe_allow_html=True)
                with st.expander("Full Finding (raw)"):
                    st.json(finding)
    else:
        st.caption("Select a record and run the investigation to see a result here.")