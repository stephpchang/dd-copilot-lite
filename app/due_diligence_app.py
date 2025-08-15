# app/due_diligence_app.py
# Main Streamlit entrypoint — shows the Founder Potential module first.

import os
import sys
import streamlit as st

# Ensure local imports work whether you run `streamlit run app/due_diligence_app.py`
# or `streamlit run due_diligence_app.py`
APP_DIR = os.path.dirname(__file__)
if APP_DIR not in sys.path:
    sys.path.append(APP_DIR)

from founder_scoring import founder_scoring_module  # noqa: E402


# ---------- Page setup ----------
st.set_page_config(
    page_title="Due Diligence — Founder Potential First",
    page_icon="🧭",
    layout="wide",
)

st.title("Company Due Diligence")
st.markdown(
    "**USV-style Founder Potential (Low-Data Mode)** — "
    "score the founder first (pre-PMF), then dive into the rest."
)

# Toggle CSV persistence via env var (recommended OFF for first Cloud deploy)
# In Streamlit Cloud, set App → Settings → Environment variable:
#   FOUNDER_PERSIST=true
PERSIST = os.environ.get("FOUNDER_PERSIST", "false").lower() == "true"
persist_path = os.path.join(APP_DIR, "data", "founder_scores.csv") if PERSIST else None

# ---------- Founder Potential FIRST ----------
result = founder_scoring_module(persist_path=persist_path)

# Lightweight guidance banner based on evaluation
if result and result.get("evaluation"):
    ev = result["evaluation"]
    if ev.startswith(("Outstanding", "Strong")):
        st.success("Flagged for partner review based on Founder Potential Score.")
    elif ev.startswith("Moderate"):
        st.info("Moderate signal — gather more evidence or run 1–2 quick ref checks.")
    elif ev.startswith("Low"):
        st.warning("Low signal — proceed only if there’s another compelling wedge.")

st.divider()

# ---------- Your existing diligence sections (placeholders) ----------
st.header("Company Overview")
st.write("Add snapshot, round info, cap table basics, key facts...")

st.header("Market & Competitors")
st.write("Add market map, adjacent comps, why-now factors...")

st.header("Product & Technology")
st.write("Add product notes, screenshots, architecture highlights...")

st.header("Risks & Open Questions")
st.write("List key risks, regulatory flags, and unknowns to resolve...")

# ---------- Sidebar help ----------
with st.sidebar:
    st.caption("Founder Potential Module")
    st.write(
        "Use **1–5** scores for each trait. Tick **Spike** if the founder is "
        "exceptional on that trait — this applies extra weight in low-data cases."
    )
    st.write(
        "- **Coverage %** reflects how much pre-Series A evidence you found.\n"
        "- The score is shown out of 35 (base), with a separate **Spike Bonus**."
    )
    st.write(
        "To persist scores to CSV (ephemeral on Streamlit Cloud), set "
        "`FOUNDER_PERSIST=true` in app environment and redeploy."
    )
