# app/due_diligence_app.py
# Main Streamlit entrypoint that puts the Founder Potential module front-and-center.

import streamlit as st
from founder_scoring import founder_scoring_module  # assumes founder_scoring.py is in the same folder

st.set_page_config(page_title="Due Diligence — Founder Potential First", page_icon="🧭", layout="wide")

st.title("Company Due Diligence")
st.markdown("**USV-style Founder Potential (Low-Data Mode)** — score first, then dive into details.")

# --- Founder Potential FIRST ---
result = founder_scoring_module(persist_path="app/data/founder_scores.csv")

# Optional: lightweight routing based on evaluation
if result and result.get("evaluation", "").startswith(("Outstanding", "Strong")):
    st.success("Flagged for partner review based on Founder Potential Score.")
elif result and result.get("evaluation", "").startswith("Moderate"):
    st.info("Moderate signal — gather more evidence or run a quick customer/ref check.")
elif result and result.get("evaluation", "").startswith("Low"):
    st.warning("Low signal — proceed only if there’s another compelling wedge.")

st.divider()

# --- Your existing DD sections go below (examples / placeholders) ---
st.header("Company Overview")
st.write("Paste your snapshot, round info, and key facts here.")

st.header("Market & Competitors")
st.write("Add market map, competitors, and why-now notes here.")

st.header("Product & Technology")
st.write("Add screenshots, product notes, tech deep-dive here.")

st.header("Risks & Open Questions")
st.write("Track known risks, regulatory flags, and unknowns here.")
