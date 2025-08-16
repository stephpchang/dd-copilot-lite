# app/founder_scoring.py
# Low-Data Mode founder scoring with simplified UX, banded explanations,
# and auto-generated analyst summary.

from __future__ import annotations
import streamlit as st
import pandas as pd
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Tuple, Optional

# ----------------------------- Config -----------------------------

TRAITS: List[Tuple[str, str, str]] = [
    ("DD",  "Domain Depth",                   "Has the founder shown expertise or meaningful experience in this domain?"),
    ("UJ",  "Unconventional / Rigorous Journey", "Has the founder demonstrated grit via unconventional or rigorous paths?"),
    ("HFT", "High-Fidelity Thinking",         "Does the founder articulate causal, testable reasoning (not vague vision)?"),
    ("MMM", "Magnetism & Movement-Building",  "Can they attract talent/users/press and create pull around the mission?"),
    ("VWC", "Velocity Without Capital",       "Any early traction or progress achieved with very little spend?"),
    ("NC",  "Narrative Control",              "Do they frame the category and company clearly, credibly, and consistently?"),
    ("TLI", "Technology Literacy + Imagination", "Do they understand the tech deeply and imagine non-obvious uses?"),
]

SPIKE_MULTIPLIER = 1.5
BANDS = {
    "strong":   {"min": 26, "max": 35, "label": "Strong Signal",   "explain": "Likely **Bring to Partner**. Early traits align with USV Core pattern of pre-PMF winners."},
    "moderate": {"min": 18, "max": 25, "label": "Moderate Signal", "explain": "Promising, but **needs more evidence** (customer proof, team magnets, or sharper causality)."},
    "weak":     {"min":  0, "max": 17, "label": "Weak Signal",     "explain": "Probably **Pass for now**, unless there is one compelling wedge to investigate."},
}

EVIDENCE_LEVELS = {
    "Low (<30%)": 20,
    "Medium (30–60%)": 45,
    "High (>60%)": 70,
}

@dataclass
class ScoreResult:
    weighted_total: float
    spike_bonus: float
    max_base: int
    band_key: str
    band_label: str
    band_explain: str
    percent_base: float


# ---------------------- Scoring Helpers ---------------------------

def _band_for(score: float) -> Tuple[str, str, str]:
    """Return (band_key, label, explain) given a score out of 35."""
    for key, meta in BANDS.items():
        if meta["min"] <= score <= meta["max"]:
            return key, meta["label"], meta["explain"]
    # clamp
    if score > 35: 
        return "strong", BANDS["strong"]["label"], BANDS["strong"]["explain"]
    return "weak", BANDS["weak"]["label"], BANDS["weak"]["explain"]

def _compute_weighted(scores: Dict[str, int], spikes: Dict[str, bool]) -> ScoreResult:
    max_base = len(TRAITS) * 5  # 35
    weighted_total = 0.0
    spike_bonus = 0.0
    for key, _, _ in TRAITS:
        s = int(scores.get(key, 1))
        if spikes.get(key):
            weighted_total += s * SPIKE_MULTIPLIER
            spike_bonus += s * (SPIKE_MULTIPLIER - 1.0)
        else:
            weighted_total += s
    # We still show score on a /35 scale for comparability
    shown_total = min(round(weighted_total, 1), 35.0)
    band_key, band_label, band_explain = _band_for(shown_total)
    percent_base = round((shown_total / max_base) * 100.0, 1)
    return ScoreResult(
        weighted_total=shown_total,
        spike_bonus=round(spike_bonus, 1),
        max_base=max_base,
        band_key=band_key,
        band_label=band_label,
        band_explain=band_explain,
        percent_base=percent_base,
    )

def _top_traits(scores: Dict[str, int], n=2) -> List[str]:
    ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return [k for k, _ in ordered[:n]]

def _bottom_traits(scores: Dict[str, int], n=2) -> List[str]:
    ordered = sorted(scores.items(), key=lambda kv: kv[1])
    return [k for k, _ in ordered[:n]]

def _label_for(key: str) -> str:
    for k, label, _ in TRAITS:
        if k == key:
            return label
    return key


# --------------------- Summary Generation -------------------------

def _auto_summary(founder: str, company: str, band_label: str, ev_level: str,
                  scores: Dict[str, int], spikes: Dict[str, bool]) -> str:
    strengths = _top_traits(scores, n=2)
    gaps      = _bottom_traits(scores, n=2)
    spike_list = [ _label_for(k) for k, v in spikes.items() if v ]
    strengths_txt = ", ".join(_label_for(k) for k in strengths) if strengths else "—"
    gaps_txt      = ", ".join(_label_for(k) for k in gaps) if gaps else "—"
    spike_txt     = ", ".join(spike_list) if spike_list else "—"

    # Light, partner-ready paragraph (edit-in-place by analyst)
    return (
        f"{founder or 'Founder'} ({company or 'Company'}) shows a **{band_label}** at a **{ev_level} evidence level**. "
        f"Strengths appear in **{strengths_txt}**; biggest gaps are **{gaps_txt}**. "
        f"Spiking traits: **{spike_txt}**. "
        f"Recommendation: if pipeline fit is strong, proceed to validate gaps with 1–2 quick references or user signals."
    )


# ---------------------- Main UI Component -------------------------

def founder_scoring_module(persist_path: Optional[str] = None):
    st.markdown("### Founder Potential — Low-Data Mode")
    st.caption(
        "Score the founder on 7 traits USV cares about at Seed/Series A. "
        "Use **Spike** for any trait that is unusually strong; this applies extra weight in low-data situations."
    )

    # Inputs
    c1, c2, c3 = st.columns([2,2,1])
    with c1:
        founder_name = st.text_input("Founder Name", placeholder="e.g., Anton Osika")
    with c2:
        company_name = st.text_input("Company Name", placeholder="e.g., Lovable")
    with c3:
        ev_label = st.selectbox("Stage", ["Seed", "Series A", "Other"], index=0)

    # Evidence level (friendlier than a raw percentage slider)
    ev_col1, ev_col2 = st.columns([2,1])
    with ev_col1:
        ev_level = st.selectbox("How much public evidence is available?",
                                list(EVIDENCE_LEVELS.keys()), index=1,
                                help="A quick gauge of how much pre-Series A signal you could find.")
    with ev_col2:
        coverage_pct = st.number_input("Coverage %", min_value=0, max_value=100,
                                       value=EVIDENCE_LEVELS[ev_level],
                                       help="You can override this if needed.")

    st.markdown("#### Score each trait (1–5). Tick **Spike** for standout performance.")
    scores: Dict[str, int] = {}
    spikes: Dict[str, bool] = {}
    notes:  Dict[str, str]  = {}
    # Inline grid — simpler than 7 expanders
    for key, label, expl in TRAITS:
        colL, colM, colR = st.columns([5,2,1])
        with colL:
            st.write(f"**{label}** – {expl}")
            notes[key] = st.text_input(f"Evidence (links / short notes) — {label}", key=f"notes_{key}", placeholder="Optional evidence…")
        with colM:
            scores[key] = st.radio("Score", options=[1,2,3,4,5], horizontal=True, index=2, key=f"score_{key}",
                                   label_visibility="collapsed")
        with colR:
            spikes[key] = st.checkbox("Spike", value=False, key=f"spike_{key}", help="Exceptional vs. peers? Check to weight more.")

        st.divider()

    # Scoring
    result = _compute_weighted(scores, spikes)

    # Output — clear interpretation
    st.markdown("### Founder Potential Score & Interpretation")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Score (shown as /35)", f"{result.weighted_total} / {result.max_base}")
    with col2:
        st.metric("Coverage", f"{coverage_pct}%")
    with col3:
        st.metric("Spike Bonus (raw)", f"+{result.spike_bonus}")

    # Band explanation box
    st.info(f"**{result.band_label}** — {result.band_explain}")

    # Auto-generated Analyst Summary (editable)
    st.markdown("#### Analyst Summary (auto-generated; edit if needed)")
    default_summary = _auto_summary(
        founder=founder_name, company=company_name, band_label=result.band_label,
        ev_level=ev_level, scores=scores, spikes=spikes
    )
    summary = st.text_area("", value=default_summary, height=110)

    # Optional persistence
    saved_path = None
    if persist_path:
        if st.button("Save to CSV"):
            row = {
                "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                "founder_name": founder_name,
                "company_name": company_name,
                "stage": ev_label,
                "evidence_level": ev_level,
                "coverage_pct": int(coverage_pct),
                "score_weighted_total": float(result.weighted_total),
                "percent_base": float(result.percent_base),
                "band": result.band_key,
                "band_label": result.band_label,
                "spike_bonus": float(result.spike_bonus),
                "spike_multiplier": SPIKE_MULTIPLIER,
                "summary": summary,
            }
            for key, label, _ in TRAITS:
                row[f"{key}_score"] = int(scores[key])
                row[f"{key}_spike"] = bool(spikes[key])
                row[f"{key}_notes"] = notes[key]

            try:
                df = pd.read_csv(persist_path)
                df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
            except Exception:
                df = pd.DataFrame([row])
            df.to_csv(persist_path, index=False)
            saved_path = persist_path
            st.success(f"Saved to {persist_path}")

    # Return for callers
    return {
        "founder": founder_name,
        "company": company_name,
        "stage": ev_label,
        "coverage_pct": int(coverage_pct),
        "scores": scores,
        "spikes": spikes,
        "summary": summary,
        "weighted_total": float(result.weighted_total),
        "percent_base": float(result.percent_base),
        "evaluation": f"{result.band_label} — {BANDS[result.band_key]['explain']}",
        "saved_path": saved_path,
    }
