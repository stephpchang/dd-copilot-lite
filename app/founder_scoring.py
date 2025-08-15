# founder_scoring.py
# Low-Data Mode founder scoring with spike weighting and optional CSV persistence.

from __future__ import annotations
import streamlit as st
import pandas as pd
from datetime import datetime

TRAITS = [
    ("DD", "Domain Depth"),
    ("UJ", "Unconventional / Rigorous Journey"),
    ("HFT", "High-Fidelity Thinking"),
    ("MMM", "Magnetism & Movement-Building"),
    ("VWC", "Velocity Without Capital"),
    ("NC", "Narrative Control"),
    ("TLI", "Technology Literacy + Imagination"),
]

SPIKE_MULTIPLIER = 1.5  # bump for exceptional spikes
EVAL_THRESHOLDS = {     # percent of base (out of 35)
    "outstanding": 90,
    "strong": 75,
    "moderate": 60,
}

def _evaluate(percent_score: float) -> str:
    if percent_score >= EVAL_THRESHOLDS["outstanding"]:
        return "Outstanding — Bring to Partner"
    if percent_score >= EVAL_THRESHOLDS["strong"]:
        return "Strong Potential — Worth Partner Review"
    if percent_score >= EVAL_THRESHOLDS["moderate"]:
        return "Moderate — Needs More Context"
    return "Low — Likely Pass"

def founder_scoring_module(persist_path: str | None = None):
    st.subheader("Founder Potential — Low-Data Mode")

    # --- Inputs ---
    c1, c2, c3 = st.columns([2,2,1])
    with c1:
        founder_name = st.text_input("Founder Name", placeholder="e.g., Anton Osika")
    with c2:
        company_name = st.text_input("Company Name", placeholder="e.g., Lovable")
    with c3:
        stage = st.selectbox("Stage", ["Seed", "Series A", "Other"], index=0)

    coverage = st.slider("Evidence Coverage (estimated %)", 0, 100, 40,
                         help="Percent of ideal pre–Series A evidence you were able to find.")

    st.markdown("#### Score each trait (1–5). Tick **Spike** if this founder is exceptional on that trait.")
    scores, spikes, notes = {}, {}, {}
    for key, label in TRAITS:
        with st.expander(f"{label} ({key})", expanded=False):
            cL, cR = st.columns([4,1])
            with cL:
                scores[key] = st.slider("Score", 1, 5, 3, key=f"score_{key}")
                notes[key]  = st.text_area("Evidence notes (bullet points / links)",
                                           key=f"notes_{key}", height=90)
            with cR:
                spikes[key] = st.checkbox("Spike", value=False, key=f"spike_{key}")

    # --- Scoring ---
    base_max = len(TRAITS) * 5  # 35
    base_total = sum(scores.values())

    # spike-weighted total (we cap display at 35 for a clean %; show bonus separately)
    weighted_total = 0.0
    spike_bonus = 0.0
    for key, _ in TRAITS:
        s = scores[key]
        if spikes[key]:
            weighted_total += s * SPIKE_MULTIPLIER
            spike_bonus += (s * (SPIKE_MULTIPLIER - 1.0))
        else:
            weighted_total += s

    # Display “percent of base” for comparability; also show spike bonus.
    percent_base = round(min((weighted_total / base_max) * 100, 100), 1)

    evaluation = _evaluate(percent_base)

    # --- Output ---
    st.markdown("### Founder Potential Score")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Score (spike-weighted, shown as /35)", f"{min(round(weighted_total,1), 35)} / 35")
    with c2:
        st.metric("Coverage", f"{coverage}%")
    with c3:
        st.metric("Spike Bonus (raw)", f"+{round(spike_bonus,1)}")

    if any(spikes.values()):
        spiking = [label for (key, label) in TRAITS if spikes[key]]
        st.caption(f"Spiking Traits: {', '.join(spiking)}")

    st.markdown(f"**Evaluation:** {evaluation}")

    st.markdown("#### Analyst summary (optional)")
    summary = st.text_area("One-paragraph synopsis you’d say to a partner in 30 seconds.", height=100)

    # --- Optional persistence ---
    saved_path = None
    if persist_path:
        if st.button("Save to CSV"):
            row = {
                "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                "founder_name": founder_name,
                "company_name": company_name,
                "stage": stage,
                "coverage_pct": coverage,
                "score_base_max": base_max,
                "score_weighted_total": round(weighted_total, 2),
                "percent_base": percent_base,
                "evaluation": evaluation,
                "spike_bonus": round(spike_bonus, 2),
                "spike_multiplier": SPIKE_MULTIPLIER,
                "summary": summary,
            }
            for key, _ in TRAITS:
                row[f"{key}_score"] = scores[key]
                row[f"{key}_spike"] = spikes[key]
                row[f"{key}_notes"] = notes[key]

            try:
                df = pd.read_csv(persist_path)
                df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
            except Exception:
                df = pd.DataFrame([row])

            df.to_csv(persist_path, index=False)
            saved_path = persist_path
            st.success(f"Saved to {persist_path}")

    # Return a dict for callers who want to use the values downstream
    return {
        "founder": founder_name,
        "company": company_name,
        "stage": stage,
        "coverage_pct": coverage,
        "scores": scores,
        "spikes": spikes,
        "summary": summary,
        "weighted_total": weighted_total,
        "percent_base": percent_base,
        "evaluation": evaluation,
        "saved_path": saved_path,
    }
