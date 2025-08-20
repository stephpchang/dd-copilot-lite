# app/founder_scoring.py
# Founder Potential panel — headline /35, bonus separate, coverage = score>0, no integrity floor.
# Adds: signal definitions + table view + per-signal relevant sources list.
# Directional triage aid; not a decision.

from __future__ import annotations

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

SIGNAL_DEFINITIONS: Dict[str, str] = {
    "Domain insight": "Founder’s depth in the problem space (prior work, writing, clarity of thesis).",
    "Execution": "Ability to ship and improve (changelogs, launches, docs, momentum).",
    "Hiring pull": "Ability to attract talent (team signals, active hiring).",
    "Communication": "Clarity + public communication (writing, talks, press).",
    "Customer focus": "Evidence of customer proof points (reviews, case studies, docs).",
    "Learning speed": "Cadence of iteration (visible updates, experiments, roadmaps).",
    "Integrity": "Basic trust signals (verified profiles, transparent practices).",
}

# Heuristic URL filters to surface *relevant* sources per signal in the breakdown
SIGNAL_SOURCE_FILTERS: Dict[str, List[str]] = {
    "Domain insight": ["wikipedia.org", "substack.com", "medium.com", "github.com", "readthedocs", "blog"],
    "Execution": ["github.com", "docs.", "changelog", "release", "producthunt.com", "notion.site", "roadmap"],
    "Hiring pull": ["linkedin.com/in", "jobs", "greenhouse.io", "lever.co", "careers"],
    "Communication": ["substack.com", "medium.com", "mirror.xyz", "twitter.com", "x.com", "press", "techcrunch.com"],
    "Customer focus": ["g2.com", "capterra.com", "case", "customers", "case-study", "docs."],
    "Learning speed": ["changelog", "release notes", "github.com", "notion.site", "trello"],
    "Integrity": ["wikipedia.org", "crunchbase.com", "linkedin.com", "open source", "license"],
}

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
    ev: List[str] = []
    score = 0
    domains = [_domain(u) for u in (sources_list or [])]

    # Domain insight
    if name == "Domain insight":
        if len(wiki_summary or "") > 300:
            score += 3; ev.append("Substantive bio/background visible (e.g., Wikipedia).")
        if any(d for d in domains if d.endswith(("substack.com","medium.com","github.com","readthedocs.io"))):
            score += 1; ev.append("Public writing/docs signal.")
        if funding_stats.get("total_usd"):
            score += 1; ev.append("External validation via funding.")
        score = min(score, 5)

    # Execution
    elif name == "Execution":
        if any(d for d in domains if "github.com" in d or "docs." in d or "changelog" in d):
            score += 2; ev.append("Code/docs/changelog present.")
        if any("release" in (u or "").lower() for u in (sources_list or [])):
            score += 1; ev.append("Release notes in sources.")
        if funding_stats.get("largest", {}).get("date"):
            score += 1; ev.append("Recent round suggests delivery momentum.")
        if any(d for d in domains if "producthunt.com" in d or "notion.site" in d):
            score += 1; ev.append("Public launches/roadmaps.")
        score = min(score, 5)

    # Hiring pull
    elif name == "Hiring pull":
        if any("linkedin.com/in" in (u or "") for u in (sources_list or [])):
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
        if any("customers" in (u or "").lower() or "case-study" in (u or "").lower() for u in (sources_list or [])):
            score += 1; ev.append("Customer content in sources.")
        if _has_any(wiki_summary, ["customer", "users", "clients"]):
            score += 1; ev.append("Customer orientation mentioned.")
        if any(d for d in domains if "docs." in d):
            score += 1; ev.append("Docs imply user empathy.")
        score = min(score, 5)

    # Learning speed
    elif name == "Learning speed":
        if any("changelog" in (u or "").lower() or "release notes" in (u or "").lower() for u in (sources_list or [])):
            score += 2; ev.append("Frequent updates implied.")
        if any(d for d in domains if "github.com" in d):
            score += 1; ev.append("Github present.")
        if _has_any(wiki_summary, ["iterate", "experiments", "rapid"]):
            score += 1; ev.append("Iteration signals in bio/summary.")
        if any(d for d in domains if "notion.site" in d or "trello" in d):
            score += 1; ev.append("Roadmap/iteration artifacts.")
        score = min(score, 5)

    # Integrity (NO floor; can be 0 if no evidence)
    elif name == "Integrity":
        if any(d for d in domains if "wikipedia.org" in d or "crunchbase.com" in d or "linkedin.com" in d):
            score += 2; ev.append("Verified public profiles.")
        if _has_any(wiki_summary, ["nonprofit","ethics","open source","license"]):
            score += 1; ev.append("Values/work transparency noted.")
        score = min(max(score, 0), 5)

    return score, ev

def _bonus_and_traits(wiki_summary: str, founder_hint: str | None, sources_list: List[str]) -> tuple[int, List[str]]:
    """Return (bonus_0_to_5, traits_list).  Bonus is NOT added to headline score."""
    traits: List[str] = []
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

    return min(bonus, 5), traits

def _relevant_domains_for_signal(sig: str, sources_list: List[str]) -> List[str]:
    needles = [n.lower() for n in SIGNAL_SOURCE_FILTERS.get(sig, [])]
    hits = []
    for u in (sources_list or []):
        ul = (u or "").lower()
        if any(n in ul for n in needles):
            hits.append(_domain(u))
    # Dedup while keeping order
    seen = set(); out = []
    for d in hits:
        if d and d not in seen:
            seen.add(d); out.append(d)
    return out[:6]

def auto_founder_scoring_panel(
    company_name: str,
    founder_hint: str | None,
    sources_list: List[str],
    wiki_summary: str,
    funding_stats: Dict[str, Any],
    market_size: Dict[str, Any] | None = None,
    persist_path: str | None = None,
):
    """Render the Founder Potential panel with /35 headline score and separate bonus."""
    st.markdown("### Detailed scoring")
    st.caption("Directional, first-pass signals compiled from public sources.")

    per_signal: Dict[str, Dict[str, Any]] = {}
    coverage_hits = 0
    base_total = 0

    # Per-signal scoring
    for sig in SEVEN_SIGNALS:
        sc, ev = _score_signal(sig, wiki_summary, founder_hint, sources_list, funding_stats)
        per_signal[sig] = {"score": sc, "evidence": ev}
        if sc > 0:  # coverage counts signals with score>0
            coverage_hits += 1
        base_total += sc

    coverage_pct = int(round((coverage_hits / len(SEVEN_SIGNALS)) * 100)) if SEVEN_SIGNALS else 0
    bonus, traits = _bonus_and_traits(wiki_summary, founder_hint, sources_list)
    combined = min(base_total + bonus, 40)

    # Headline metrics — /35 main, bonus separate, combined shown as reference
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Score (out of 35)", f"{base_total:.1f}")
    c2.metric("Signal coverage", f"{coverage_pct}%")
    c3.metric("Bonus (0–5)", f"+{bonus:.1f}")
    c4.metric("Score+Bonus (max 40)", f"{combined:.1f}")

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

    # --- New: tabular breakdown with brief descriptions and top sources ---
    rows = []
    for sig in SEVEN_SIGNALS:
        row = per_signal[sig]
        short_ev = " | ".join(row["evidence"][:2]) if row["evidence"] else "—"
        srcs = _relevant_domains_for_signal(sig, sources_list)
        src_badges = " ".join(
            f"<span style='background:#f1f5f9;border:1px solid #e2e8f0;border-radius:999px;"
            f"padding:2px 8px;font-size:11px;color:#334155'>{html.escape(d)}</span>"
            for d in srcs
        )
        rows.append({
            "Signal": sig,
            "What it means": SIGNAL_DEFINITIONS.get(sig, ""),
            "Score (0–5)": row["score"],
            "Why we gave this score": short_ev,
            "Top sources": src_badges or "—",
        })
    st.markdown("#### Per-signal breakdown (skim)")
    # Render as table; allow HTML in Top sources via unsafe markdown below each row
    # Use st.table for the main columns except sources, then render sources underneath
    st.table([{k: (v if k != "Top sources" else "") for k, v in r.items()} for r in rows])
    # print sources line-by-line to keep badges
    for r in rows:
        if r["Top sources"]:
            st.markdown(f"*{r['Signal']} — top sources:* {r['Top sources']}", unsafe_allow_html=True)

    # Full evidence (optional)
    with st.expander("See full evidence per signal"):
        for sig in SEVEN_SIGNALS:
            row = per_signal[sig]
            st.markdown(f"**{sig}** — {SIGNAL_DEFINITIONS[sig]}")
            st.write(f"Score: {row['score']} / 5")
            if row["evidence"]:
                for ev in row["evidence"]:
                    st.write(f"• {ev}")
            else:
                st.caption("No specific evidence captured for this signal.")

    # (Optional) return structure for future use
    return {
        "score_base": base_total,
        "coverage_pct": coverage_pct,
        "bonus": bonus,
        "score_combined": combined,
        "traits": traits,
        "signals": per_signal,
    }
