# app/founder_scoring.py
# Founder Potential — LLM-driven rubric with 7 original signals (base /35, standout bonus separate).
# Signals:
#   DD  = Domain Depth
#   UJ  = Unconventional / Rigorous Journey
#   HFT = High-Fidelity Thinking
#   MMM = Magnetism & Movement-Building
#   VWC = Velocity Without Capital
#   NC  = Narrative Control
#   TLI = Technology Literacy + Imagination
#
# What changed in this version:
# - Renames UI wording from "Spike" → "Standout" (clearer to non-technical users).
# - Headline score is BASE ONLY (/35). Standout bonus is shown separately.
# - Per-trait table is clean (no index) with short trait definitions.
# - Banding unchanged: Strong / Moderate / Weak.

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import json

import streamlit as st
try:
    import pandas as pd
except Exception:
    pd = None

from app.llm_guard import generate_once  # guarded OpenAI wrapper

# ----------------------------- Config -----------------------------

TRAITS: List[Tuple[str, str]] = [
    ("DD",  "Domain Depth"),
    ("UJ",  "Unconventional / Rigorous Journey"),
    ("HFT", "High-Fidelity Thinking"),
    ("MMM", "Magnetism & Movement-Building"),
    ("VWC", "Velocity Without Capital"),
    ("NC",  "Narrative Control"),
    ("TLI", "Technology Literacy + Imagination"),
]

TRAIT_DEFS: Dict[str, str] = {
    "Domain Depth": "Relevant experience & clarity in the problem space.",
    "Unconventional / Rigorous Journey": "Evidence of grit via non-linear or demanding paths.",
    "High-Fidelity Thinking": "Causal reasoning, testable hypotheses, product taste.",
    "Magnetism & Movement-Building": "Ability to attract talent, users, partners, press.",
    "Velocity Without Capital": "Visible progress with minimal spend.",
    "Narrative Control": "Frames and owns the story credibly; influences the discourse.",
    "Technology Literacy + Imagination": "Comfort with tech and creative application.",
}

STANDOUT_MULTIPLIER = 1.5  # used to compute BONUS only (headline stays base)
BANDS = {
    "strong":   {"min": 26.0, "max": 35.0, "label": "Strong Signal",
                 "explain": "Likely **Bring to Partner**. Early traits align with USV Core pre-PMF winners."},
    "moderate": {"min": 18.0, "max": 25.9, "label": "Moderate Signal",
                 "explain": "Promising, but **needs more evidence** (customer proof, talent magnetism, or sharper causality)."},
    "weak":     {"min":  0.0, "max": 17.9, "label": "Weak Signal",
                 "explain": "Probably **Pass for now**, unless there is a compelling wedge."},
}

# ------------------------- JSON schema ----------------------------

def _auto_schema() -> dict:
    valid_keys   = [k for k, _ in TRAITS]
    valid_labels = [lbl for _, lbl in TRAITS]
    properties = {
        "founder_names": {"type": "array", "items": {"type": "string"}},
        "coverage_pct":  {"type": "integer", "minimum": 0, "maximum": 100},
        "traits": {
            "type": "array",
            "minItems": len(valid_keys), "maxItems": len(valid_keys),
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "key":   {"type": "string", "enum": valid_keys},
                    "label": {"type": "string", "enum": valid_labels},
                    "score": {"type": "integer", "minimum": 1, "maximum": 5},
                    "spike": {"type": "boolean"},  # keep JSON key as 'spike' for compatibility
                    "evidence": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 3},
                },
                "required": ["key", "label", "score", "spike", "evidence"],
            },
        },
        "overall_summary": {"type": "string"},
        "methodology":     {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 8},
        "flags":           {"type": "array", "items": {"type": "string"}},
    }
    return {
        "name": "FounderAutoScore",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": properties,
            "required": list(properties.keys()),
        },
    }

# ---------------------- Prompt builder ----------------------------

def _auto_prompt(company: str,
                 founder_hint: Optional[str],
                 sources: List[str],
                 wiki_summary: str,
                 funding_stats: dict,
                 market_size: dict) -> str:
    total_usd = funding_stats.get("total_usd")
    largest   = funding_stats.get("largest") or {}
    lr_round  = largest.get("round") or "unknown"
    lr_amt    = largest.get("amount_usd")
    lr_date   = largest.get("date") or "unknown"
    leads     = funding_stats.get("lead_investors") or []

    ms_estimates = (market_size or {}).get("estimates") or []
    if ms_estimates:
        best = ms_estimates[0]
        ms_hint = f"- Most relevant market size: ${best.get('amount_usd','?')} ({best.get('year','n/a')}) from {best.get('url','source')}."
    else:
        ms_hint = "- No credible market size found."

    trait_help = """
Score each trait 1–5 (5 is best). Be conservative when evidence is thin:
- DD: domain expertise or relevant experience.
- UJ: grit via unconventional/rigorous paths.
- HFT: clear causal reasoning and testable hypotheses; product taste.
- MMM: attracts talent/users/partners/press; movement-building.
- VWC: progress with very little spend.
- NC: frames and owns the narrative credibly.
- TLI: deep technical literacy and imaginative use.
Mark "spike": true ONLY if evidence is clearly exceptional for seed/Series A (we'll label it "Standout" in the UI).
"""

    return f"""
You are scoring founders for a seed/Series A low-data workflow. Use ONLY the inputs below.
Company: {company}
Founder hint (may be empty): {founder_hint or "(none)"}

Public sources to rely on (top 12 max):
{json.dumps(sources, indent=2)}

Optional background (Wikipedia snippet):
{(wiki_summary or "").strip()[:900]}

Known funding facts (do not guess beyond these):
- Total USD: {total_usd if total_usd else "unknown"}
- Largest round: {lr_round}
- Largest round amount: {lr_amt if lr_amt else "unknown"}
- Largest round date: {lr_date}
- Lead investors: {", ".join(leads) if leads else "unknown"}

Market context hints:
{ms_hint}

{trait_help}

Rules:
- Return the strict JSON schema provided (no extra keys).
- Each trait must include 1–3 short evidence bullets; include short host names where possible.
- coverage_pct = estimated % of ideal pre–Series A evidence found from provided inputs (0–100).
- methodology = 3–8 short bullets explaining the rubric in plain English.
- overall_summary = 3–6 sentences explaining why the score/band was assigned.

Return ONLY the JSON object.
""".strip()

# --------------------- Scoring utilities --------------------------

@dataclass
class ScorePack:
    base_total: float    # headline /35 (no multiplier)
    bonus: float         # visibility from 'standout' traits
    max_base: float
    band_key: str
    band_label: str
    band_explain: str

def _band_for(base_total: float) -> Tuple[str, str, str]:
    for k, meta in BANDS.items():
        if meta["min"] <= base_total <= meta["max"]:
            return k, meta["label"], meta["explain"]
    return ("strong" if base_total > 35 else "weak",
            BANDS["strong" if base_total > 35 else "weak"]["label"],
            BANDS["strong" if base_total > 35 else "weak"]["explain"])

def _score_from_traits(traits: List[dict]) -> ScorePack:
    """Headline score is BASE ONLY. 'Standout' bonus is computed from spiking traits."""
    max_base = 5.0 * len(TRAITS)  # 35
    base = 0.0
    bonus = 0.0
    for t in traits:
        s = float(t.get("score", 1))
        base += s
        if t.get("spike"):
            bonus += s * (STANDOUT_MULTIPLIER - 1.0)
    base = min(round(base, 1), 35.0)
    bonus = round(bonus, 1)
    band_key, band_label, band_explain = _band_for(base)
    return ScorePack(base, bonus, max_base, band_key, band_label, band_explain)

# --------------------- Render: Auto Panel -------------------------

def auto_founder_scoring_panel(
    company_name: str,
    founder_hint: Optional[str],
    sources_list: List[str],
    wiki_summary: str,
    funding_stats: dict,
    market_size: dict,
    persist_path: Optional[str] = None,
):
    st.markdown("### Founder Potential")
    st.caption("Scores are computed from public signals. No manual inputs required.")

    schema = _auto_schema()
    prompt = _auto_prompt(company_name, founder_hint, sources_list, wiki_summary, funding_stats, market_size)

    try:
        with st.spinner("Scoring founder potential from public signals…"):
            result = generate_once(prompt, schema)
    except Exception as e:
        st.error("Automatic scoring failed. You can still use the rest of the app.")
        st.caption(str(e))
        return

    # Defensive parsing
    traits        = result.get("traits") or []
    coverage      = int(result.get("coverage_pct") or 0)
    founder_names = result.get("founder_names") or []
    overall_sum   = (result.get("overall_summary") or "").strip()
    methodology   = result.get("methodology") or []
    flags         = result.get("flags") or []

    pack = _score_from_traits(traits)

    # Header: founders + standout chips
    headline = ", ".join(founder_names) if founder_names else "Founder(s): not detected"
    st.markdown(f"**{headline}**")

    standout = [t for t in traits if t.get("spike")]
    st.caption("Standout signals (exceptional for stage): " + (" ".join(f"`{t.get('label','?')}`" for t in standout) if standout else "none"))

    # Score cards
    c1, c2, c3 = st.columns(3)
    c1.metric("Score (out of 35)", f"{pack.base_total}")
    c2.metric("Coverage", f"{coverage}%")
    c3.metric("Standout bonus (separate)", f"+{pack.bonus}")

    # Band explanation
    st.info(f"**{pack.band_label}** — {pack.band_explain}")

    # Per-trait table (no index) + brief definitions
    rows = []
    for t in traits:
        label = t.get("label", "?")
        rows.append({
            "Trait": label,
            "What it means": TRAIT_DEFS.get(label, ""),
            "Score (0–5)": t.get("score", ""),
            "Standout?": "Yes" if t.get("spike") else "No",
            "Why we gave this score": " | ".join((t.get("evidence") or [])[:3]) or "—",
        })

    st.markdown("#### Per-trait breakdown (skim)")
    if pd is not None:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.table(rows)

    # Full evidence (optional)
    with st.expander("See full evidence per trait"):
        for t in traits:
            label = t.get("label", "?")
            st.markdown(f"**{label}** — {TRAIT_DEFS.get(label, '')}")
            st.write(f"Score: {t.get('score','?')} / 5" + ("  ·  **Standout**" if t.get("spike") else ""))
            for e in (t.get("evidence") or []):
                st.write(f"- {e}")

    # Analyst summary (editable)
    st.markdown("#### Analyst Summary (auto-generated; edit if needed)")
    st.text_area("", value=overall_sum, height=120)

    # Methodology + transparent rules
    with st.expander("How this grading works (methodology)"):
        if methodology:
            for m in methodology:
                st.write(f"- {m}")
            st.markdown("---")
        st.write("**Rubric bands (transparent):**")
        st.write("- **Strong Signal (26–35):** Bring to Partner likely.")
        st.write("- **Moderate Signal (18–25.9):** Promising; needs more evidence.")
        st.write("- **Weak Signal (<18):** Probably pass for now unless there’s a compelling wedge.")
        st.write(f"**Standout weighting:** shown separately (×{STANDOUT_MULTIPLIER} on standout traits).")

    if flags:
        with st.expander("Auto-detected flags / caveats"):
            for f in flags:
                st.write(f"- {f}")
