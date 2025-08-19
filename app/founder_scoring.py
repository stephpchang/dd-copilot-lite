# app/founder_scoring.py
# Founder Potential panel (clarified labels)
# Computes a coarse, first-pass score from public signals passed in by the app.
# Score = Base (out of 35; 7 signals × 5) + Bonus (0–5) for standout traits.
# This is a directional triage aid — not a decision.

from __future__ import annotations

import re
import html
import streamlit as st
from urllib.parse import urlparse
from typing import List, Dict, Any

SEVEN_SIGNALS = [
    "Domain insight",
    "Execution",
    "Hiring pull",
    "Communication",
    "Customer focus",
    "Learning speed",
    "Integrity",
]

def _domain(u: str) -> str:
    try:
        return urlparse(u).netloc.lower()
    except Exception:
        return ""

def _has_any(s: str, needles: List[str]) -> bool:
    s = (s or "").lower()
    return any(n.lower() in s for n in needles)

def _score_signal(
    name: str,
    wiki_summary: str,
    founder_hint: str | None,
    sources_list: List[str],
    funding_stats: Dict[str, Any],
) -> tuple[int, List[str]]:
    """Return (score_0_to_5, evidence_lines) using light-touch heuristics."""
    ev = []
    score = 0
    domains = [_domain(u) for u in (sources_list or [])]

    # Domain insight
    if name == "Domain insight":
        if len(wiki_summary or "") > 300:
            score += 3; ev.append("Substantive background (Wikipedia summary present).")
        if any(d for d in domains if d.endswith(("substack.com","medium.com","github.com","readthedocs.io"))):
            score += 1; ev.append("Public writing/docs signal.")
        if funding_stats.get("total_usd"):
            score += 1; ev.append("External validation via funding.")
        score = min(score, 5)

    # Execution
    elif name == "Execution":
        if any(d for d in domains if "github.com" in d or "docs." in d or "changelog" in d):
            score += 2; ev.append("Code/docs/changelog present.")
        if any("release" in u.lower() for u in (sources_list or [])):
            score += 1; ev.append("Release notes in sources.")
        if funding_stats.get("largest", {}).get("date"):
            score += 1; ev.append("Recent round suggests delivery momentum.")
        if any(d for d in domains if "producthunt.com" in d or "notion.site" in d):
            score += 1; ev.append("Public launches/roadmaps.")
        score = min(score, 5)

    # Hiring pull
    elif name == "Hiring pull":
        if any("linkedin.com/in" in u for u in (sources_list or [])):
            score += 2; ev.append("Founder LinkedIn signals team magnetism.")
        if any(d for d in domains if "jobs" in d or "greenhouse.io" in d or "lever.co" in d):
            score += 1; ev.append("Active hiring page.")
        if (funding_stats.get("total_usd") or 0) >= 5_000_000:
            score += 1; ev.append("Capital to hire.")
        if founder_hint and ("," in founder_hint or " & " in founder_hint):
            score += 1; ev.append("Multiple founders indicated.")
        score = min(score, 5)

    # Communication
    elif name == "Communication":
        if any(d for d in domains if d.endswith(("substack.com","medium.com","mirror.xyz"))):
            score += 2; ev.append("Public writing channel.")
        if any(d for d in domains if "twitter.com" in d or "x.com" in d):
            score += 1; ev.append("Public comms/social present.")
        if _has_any(wiki_summary, ["spoke", "talk", "conference", "keynote"]):
            score += 1; ev.append("Speaking/history in public record.")
        if any(d for d in domains if "press" in d or "techcrunch.com" in d):
            score += 1; ev.append("Press references.")
        score = min(score, 5)

    # Customer focus
    elif name == "Customer focus":
        if any(d for d in domains if "g2.com" in d or "capterra.com" in d or "case" in d):
            score += 2; ev.append("Customer reviews/case studies.")
        if any("customers" in u.lower() or "case-study" in u.lower() for u in (sources_list or [])):
            score += 1; ev.append("Customer content in sources.")
        if _has_any(wiki_summary, ["customer", "users", "clients"]):
            score += 1; ev.append("Customer orientation mentioned.")
        if any(d for d in domains if "docs." in d):
            score += 1; ev.append("Docs imply user empathy.")
        score = min(score, 5)

    # Learning speed
    elif name == "Learning speed":
        if any("changelog" in u.lower() or "release notes" in u.lower() for u in (sources_list or [])):
            score += 2; ev.append("Frequent updates implied.")
        if any(d for d in domains if "github.com" in d):
            score += 1; ev.append("Github present.")
        if _has_any(wiki_summary, ["iterate", "experiments", "rapid"]):
            score += 1; ev.append("Iteration signals in bio/summary.")
        if any(d for d in domains if "notion.site" in d or "trello" in d):
            score += 1; ev.append("Roadmap/iteration artifacts.")
        score = min(score, 5)

    # Integrity (very conservative / proxy-based)
    elif name == "Integrity":
        if any(d for d in domains if "wikipedia.org" in d or "crunchbase.com" in d or "linkedin.com" in d):
            score += 2; ev.append("Verified public profiles.")
        if _has_any(wiki_summary, ["nonprofit","ethics","open source","license"]):
            score += 1; ev.append("Values/work transparency noted.")
        # No negative-signal scraping; keep this as a light positive prior
        score = min(max(score, 1), 5)  # ensure non-zero baseline if any evidence gathered

    return score, ev

def _bonus_and_traits(wiki_summary: str, founder_hint: str | None, sources_list: List[str]) -> tuple[int, List[str]]:
    """Return (bonus_0_to_5, traits_list)."""
    traits = []
    bonus = 0
    text = (wiki_summary or "") + " " + (founder_hint or "")
    text_l = text.lower()
    domains = [_domain(u) for u in (sources_list or [])]

    # Repeat founder / prior exits
    if any(k in text_l for k in ["repeat founder","serial founder","previously founded","acquired","exit","sold company"]):
        traits.append("Repeat founder / prior exit")
        bonus += 2

    # Strong technical background
    if any(k in text_l for k in ["phd","researcher","professor","ml engineer","systems engineer","cto","compiler","cryptography","distributed systems"]):
        traits.append("Strong technical background")
        bonus += 2

    # Fast product cadence / open-source activity
    if any("github.com" in d for d in domains) or any(k in " ".join(sources_list).lower() for k in ["changelog","release notes"]):
        traits.append("Visible product cadence")
        bonus += 1

    # Cap at 5
    bonus = min(bonus, 5)
    return bonus, traits

def auto_founder_scoring_panel(
    company_name: str,
    founder_hint: str | None,
    sources_list: List[str],
    wiki_summary: str,
    funding_stats: Dict[str, Any],
    market_size: Dict[str, Any] | None = None,
    persist_path: str | None = None,
):
    """Render the Founder Potential panel with clarified labels and breakdown."""
    st.markdown("### Detailed scoring")
    st.caption("Directional, first-pass signals compiled from public sources.")

    # Per-signal scoring
    per_signal = {}
    coverage_hits = 0
    base_total = 0
    for sig in SEVEN_SIGNALS:
        sc, ev = _score_signal(sig, wiki_summary, founder_hint, sources_list, funding_stats)
        per_signal[sig] = {"score": sc, "evidence": ev}
        if ev:
            coverage_hits += 1
        base_total += sc

    coverage_pct = int(round((coverage_hits / len(SEVEN_SIGNALS)) * 100)) if SEVEN_SIGNALS else 0
    bonus, traits = _bonus_and_traits(wiki_summary, founder_hint, sources_list)
    final_score = min(base_total + bonus, 40)

    # Headline metrics
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Score (out of 40)", f"{final_score:.1f}")
    c2.metric("Base (out of 35)", f"{base_total:.1f}")
    c3.metric("Signal coverage", f"{coverage_pct}%")
    c4.metric("Bonus (0–5)", f"+{bonus:.1f}")

    # Standout traits
    if traits:
        chips = " ".join(
            f"<span style='background:#ecfdf5;border:1px solid #a7f3d0;border-radius:999px;"
            f"padding:2px 8px;font-size:12px;color:#065f46'>{html.escape(t)}</span>"
            for t in traits
        )
        st.markdown(f"**Standout traits (public):** {chips}", unsafe_allow_html=True)
    else:
        st.caption("Standout traits (public): none detected")

    # Breakdown
    with st.expander("Per-signal breakdown", expanded=False):
        for sig in SEVEN_SIGNALS:
            row = per_signal[sig]
            st.write(f"- **{sig}:** {row['score']} / 5")
            for ev in row["evidence"]:
                st.write(f"   • {ev}")

    # (Optional) persist: left as a no-op to avoid side effects
    return {
        "score_final": final_score,
        "score_base": base_total,
        "coverage_pct": coverage_pct,
        "bonus": bonus,
        "traits": traits,
        "signals": per_signal,
    }
