# app/founder_scoring.py
# Auto (LLM-driven) Founder Potential scoring for Low-Data Mode.
# - No manual inputs: pulls from the caller (company name, sources, wiki, funding, market size).
# - Produces 7 trait scores (1–5), spike flags, coverage estimate, auto summary, and methodology.
# - Renders a compact, analyst-friendly UI with chips for spikes and an explanation of bands.

from __future__ import annotations
import json
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

import streamlit as st

# We call your guarded OpenAI wrapper
from app.llm_guard import generate_once

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

# Spike multiplier used in final score (transparent)
SPIKE_MULTIPLIER = 1.5

# Score banding (transparent, visible in UI)
BANDS = {
    "strong":   {"min": 26.0, "max": 35.0, "label": "Strong Signal",   "explain": "Likely **Bring to Partner**. Early traits align with USV Core pre-PMF winners."},
    "moderate": {"min": 18.0, "max": 25.9, "label": "Moderate Signal", "explain": "Promising, but **needs more evidence** (customer proof, talent magnetism, or sharper causality)."},
    "weak":     {"min":  0.0, "max": 17.9, "label": "Weak Signal",     "explain": "Probably **Pass for now**, unless there is one compelling wedge."},
}

# ------------------------- JSON schema ----------------------------

def _auto_schema() -> dict:
    """Strict schema the LLM must return for auto scoring."""
    valid_keys = [k for k, _ in TRAITS]
    valid_labels = [lbl for _, lbl in TRAITS]
    return {
        "name": "FounderAutoScore",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "founder_names": {"type": "array", "items": {"type": "string"}},
                "coverage_pct": {"type": "integer", "minimum": 0, "maximum": 100},
                "traits": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "key":   {"type": "string", "enum": valid_keys},
                            "label": {"type": "string", "enum": valid_labels},
                            "score": {"type": "integer", "minimum": 1, "maximum": 5},
                            "spike": {"type": "boolean"},
                            "evidence": {
                                "type": "array",
                                "items": {"type": "string"},
                                "minItems": 1, "maxItems": 3
                            }
                        },
                        "required": ["key", "label", "score", "spike", "evidence"]
                    },
                    "minItems": len(valid_keys), "maxItems": len(valid_keys)
                },
                "overall_summary": {"type": "string"},
                "methodology": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 8},
                "flags": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["coverage_pct", "traits", "overall_summary", "methodology"]
        }
    }

# ---------------------- Prompt builder ----------------------------

def _auto_prompt(company: str,
                 founder_hint: Optional[str],
                 sources: List[str],
                 wiki_summary: str,
                 funding_stats: dict,
                 market_size: dict) -> str:
    # Known funding facts (to anchor the model, avoid hallucination)
    total_usd = funding_stats.get("total_usd")
    largest = funding_stats.get("largest") or {}
    lr_round = largest.get("round") or "unknown"
    lr_amt   = largest.get("amount_usd")
    lr_date  = largest.get("date") or "unknown"
    leads    = funding_stats.get("lead_investors") or []

    # Market size quickline
    ms_estimates = (market_size or {}).get("estimates") or []
    if ms_estimates:
        best = ms_estimates[0]
        ms_hint = f"- Most relevant market size: ${best.get('amount_usd','?')} ({best.get('year','n/a')}) from {best.get('url','source')}."
    else:
        ms_hint = "- No credible market size found."

    trait_help = """
Traits to score (1–5):
- DD (Domain Depth): evidence of deep domain expertise or relevant experience.
- UJ (Unconventional/Rigorous Journey): grit via unusual or demanding paths.
- HFT (High-Fidelity Thinking): clear causal reasoning, testable hypotheses.
- MMM (Magnetism & Movement-Building): can attract talent/users/press.
- VWC (Velocity Without Capital): progress/traction with very little spend.
- NC (Narrative Control): frames category and company clearly and credibly.
- TLI (Tech Literacy + Imagination): deep tech understanding and non-obvious uses.
"""

    return f"""
You are scoring founders for a seed/Series A **Low-Data** workflow. Use ONLY the inputs below.
Company: {company}
Founder hint (may be empty): {founder_hint or "(none)"}

Public sources to rely on (top 12 max):
{json.dumps(sources, indent=2)}

Optional background (Wikipedia):
{(wiki_summary or "").strip()[:900]}

Known funding facts (do not guess beyond these):
- Total USD: {total_usd if total_usd else "unknown"}
- Largest round: {lr_round}
- Largest round amount: {lr_amt if lr_amt else "unknown"}
- Largest round date: {lr_date}
- Lead investors (if any): {", ".join(leads) if leads else "unknown"}

Market context hints:
{ms_hint}

{trait_help}

Rules:
- Return the strict JSON schema provided (no extra keys). Each trait must include 1–3 short evidence bullets with sources in-line if possible (short host names).
- Be conservative. If evidence is thin, lower the score and note the gap in evidence text.
- Mark a trait "spike": true ONLY when there is clear, exceptional evidence vs typical seed/Series A founders.
- coverage_pct = estimated % of ideal pre–Series A evidence you could find from the provided inputs (0–100).
- methodology = 3–8 short bullets explaining how the rubric works in plain English (not company-specific).
- overall_summary = 3–6 sentences, plain English, explaining the why behind the total signal.

Return ONLY the JSON object.
""".strip()

# --------------------- Scoring utilities --------------------------

@dataclass
class ScorePack:
    weighted_total: float
    spike_bonus: float
    max_base: float
    band_key: str
    band_label: str
    band_explain: str

def _band_for(total: float) -> Tuple[str, str, str]:
    for k, meta in BANDS.items():
        if meta["min"] <= total <= meta["max"]:
            return k, meta["label"], meta["explain"]
    return ("strong" if total > 35 else "weak",
            BANDS["strong" if total > 35 else "weak"]["label"],
            BANDS["strong" if total > 35 else "weak"]["explain"])

def _score_from_traits(traits: List[dict]) -> ScorePack:
    max_base = 5.0 * len(TRAITS)  # 35
    raw = 0.0
    bonus = 0.0
    for t in traits:
        s = float(t.get("score", 1))
        if t.get("spike"):
            raw += s * SPIKE_MULTIPLIER
            bonus += s * (SPIKE_MULTIPLIER - 1.0)
        else:
            raw += s
    shown = min(round(raw, 1), 35.0)
    band_key, band_label, band_explain = _band_for(shown)
    return ScorePack(shown, round(bonus, 1), max_base, band_key, band_label, band_explain)

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
    st.markdown("### Founder Potential — Auto (Low-Data Mode)")
    st.caption("Scores are computed from public signals. No manual inputs required.")

    schema = _auto_schema()
    prompt = _auto_prompt(company_name, founder_hint, sources_list, wiki_summary, funding_stats, market_size)

    result = None
    with st.spinner("Scoring founder potential from public signals…"):
        try:
            result = generate_once(prompt, schema)
        except Exception as e:
            st.error("Automatic scoring failed. You can still use the rest of the app.")
            st.caption(str(e))
            return

    # Defensive parsing
    traits = result.get("traits") or []
    coverage = int(result.get("coverage_pct") or 0)
    founder_names = result.get("founder_names") or []
    overall_summary = (result.get("overall_summary") or "").strip()
    methodology = result.get("methodology") or []
    flags = result.get("flags") or []

    # Score math & band
    pack = _score_from_traits(traits)

    # Header line: founders + spikes chips
    founder_line = ", ".join(founder_names) if founder_names else "Founder(s): not detected"
    st.markdown(f"**{founder_line}**")

    spiking = [t for t in traits if t.get("spike")]
    if spiking:
        chips = " ".join([f"`{t.get('label','?')}`" for t in spiking])
        st.caption(f"Spiking traits: {chips}")
    else:
        st.caption("Spiking traits: none detected")

    # Score cards
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Score (shown as /35)", f"{pack.weighted_total} / {int(pack.max_base)}")
    with c2:
        st.metric("Coverage", f"{coverage}%")
    with c3:
        st.metric("Spike Bonus (raw)", f"+{pack.spike_bonus}")

    # Band explanation (clear, always visible)
    st.info(f"**{pack.band_label}** — {pack.band_explain}")

    # Evidence table (compact)
    st.markdown("#### Evidence by Trait")
    for t in traits:
        st.markdown(f"**{t.get('label','?')}** — score {t.get('score','?')}" + (" · **Spike**" if t.get("spike") else ""))
        for e in (t.get("evidence") or [])[:3]:
            st.write(f"- {e}")
        st.markdown("")

    # Auto summary (editable)
    st.markdown("#### Analyst Summary (auto-generated; edit if needed)")
    summary_val = st.text_area("", value=overall_summary or "", height=120)

    # Methodology (LLM) + hard-coded rubric details for transparency
    with st.expander("How this grading works (methodology)"):
        if methodology:
            for m in methodology:
                st.write(f"- {m}")
            st.markdown("---")
        st.write("**Rubric bands (transparent):**")
        st.write("- **Strong Signal (26–35):** Bring to Partner likely.")
        st.write("- **Moderate Signal (18–25.9):** Promising; needs more evidence.")
        st.write("- **Weak Signal (<18):** Probably pass for now unless there’s a compelling wedge.")
        st.write(f"**Spike weighting:** each spiking trait ×{SPIKE_MULTIPLIER}.")

    if flags:
        with st.expander("Auto-detected flags / caveats"):
            for f in flags:
                st.write(f"- {f}")

    # Optional persistence
    if persist_path:
        try:
            import pandas as pd
            if st.button("Save auto-score to CSV"):
                row = {
                    "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                    "company_name": company_name,
                    "founder_names": ", ".join(founder_names),
                    "coverage_pct": coverage,
                    "score_weighted_total": pack.weighted_total,
                    "band": pack.band_key,
                    "band_label": pack.band_label,
                    "spike_bonus": pack.spike_bonus,
                    "summary": summary_val,
                }
                for t in traits:
                    k = t.get("key")
                    row[f"{k}_score"] = int(t.get("score", 0))
                    row[f"{k}_spike"] = bool(t.get("spike", False))
                import pandas as pd
                try:
                    df = pd.read_csv(persist_path)
                    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
                except Exception:
                    df = pd.DataFrame([row])
                df.to_csv(persist_path, index=False)
                st.success(f"Saved to {persist_path}")
        except Exception as e:
            st.warning(f"CSV save unavailable: {e}")
