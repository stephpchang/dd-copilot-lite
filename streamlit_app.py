import os
import re
import sys
import json
import html
import time
import requests
import streamlit as st
from urllib.parse import urlparse as _up, urlparse, parse_qs

# ---------------------------
# Founder Potential module
# ---------------------------
try:
    APP_ROOT = os.path.dirname(__file__)
    if APP_ROOT not in sys.path:
        sys.path.append(APP_ROOT)
    from app.founder_scoring import auto_founder_scoring_panel
except Exception as e:
    auto_founder_scoring_panel = None
    _fp_import_err = str(e)

# ---------------------------
# Streamlit config
# ---------------------------
st.set_page_config(page_title="Due Diligence Co-Pilot (Lite)", layout="wide")
st.title("Due Diligence Co-Pilot (Lite)")
st.caption(f"OpenAI key loaded: {'yes' if os.getenv('OPENAI_API_KEY') else 'no'}")
st.caption("Build: v0.11.2 — Accordion UX + smarter founder detection + public search fallback")

# ===============================================================
# SEARCH: Google CSE (preferred) -> DuckDuckGo HTML (fallback)
# ===============================================================
@st.cache_data(show_spinner=False, ttl=86400)
def serp(query: str, num: int = 3):
    """
    Returns a list of {title, snippet, url}.
    Prefers Google CSE if GOOGLE_CSE_ID and GOOGLE_API_KEY are set.
    Falls back to DuckDuckGo HTML parsing (no API key required).
    """
    num = max(1, min(int(num or 3), 5))

    # --- Preferred: Google CSE ---
    cx = os.getenv("GOOGLE_CSE_ID")
    key = os.getenv("GOOGLE_API_KEY")
    if cx and key:
        try:
            resp = requests.get(
                "https://www.googleapis.com/customsearch/v1",
                params={"q": query, "cx": cx, "key": key, "num": num},
                timeout=15,
            )
            if resp.status_code == 200:
                items = (resp.json().get("items") or [])[:num]
                out = []
                for it in items:
                    out.append({
                        "title": it.get("title", "") or "",
                        "snippet": it.get("snippet", "") or "",
                        "url": it.get("link", "") or "",
                    })
                if out:
                    return out
        except Exception:
            pass  # fall through to DDG

    # --- Fallback: DuckDuckGo HTML (no API key) ---
    try:
        r = requests.get("https://duckduckgo.com/html/", params={"q": query}, timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123 Safari/537.36"
        })
        html_text = r.text

        # Find result blocks: links in /l/?uddg=... form
        link_re = re.compile(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
        snip_re = re.compile(r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)

        links = link_re.findall(html_text)
        snips = snip_re.findall(html_text)

        results = []
        for i, (href, title_html) in enumerate(links[:num]):
            # Extract final URL from DuckDuckGo redirect (/l/?uddg=<encoded_url>)
            url = href
            try:
                if href.startswith("/l/?"):
                    q = parse_qs(urlparse(href).query)
                    if "uddg" in q and q["uddg"]:
                        url = q["uddg"][0]
                    else:
                        url = "https://duckduckgo.com" + href
                elif href.startswith("//"):
                    url = "https:" + href
                elif href.startswith("/"):
                    url = "https://duckduckgo.com" + href
            except Exception:
                pass

            # Clean title/snippet
            title = html.unescape(re.sub("<.*?>", "", title_html)).strip()
            snippet = ""
            if i < len(snips):
                snippet = html.unescape(re.sub("<.*?>", "", snips[i])).strip()

            results.append({"title": title, "snippet": snippet, "url": url})
        return results[:num]
    except Exception:
        return []

# ===============================================================
# NAME EXTRACTION (with location filter)
# ===============================================================
NAME_RE = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\b")

def _extract_names(text: str) -> list[str]:
    if not text:
        return []

    # Disqualifying tokens
    blacklist = {
        "Inc","LLC","Ltd","Series","Founder","CEO","Co",
        "Cofounder","Co-founder","Founder/CEO"
    }

    # Common non-person phrases (expand as needed)
    location_blacklist = {
        "San Francisco","New York","London","Boston","Los Angeles","Silicon Valley",
        "United States","USA","California","Texas","Paris","Berlin","Toronto","Chicago","Miami","Seattle"
    }

    out = []
    for m in NAME_RE.findall(text):
        candidate = m.strip()
        parts = candidate.split()

        if any(p in blacklist for p in parts):
            continue
        if candidate in location_blacklist:
            continue
        if len(parts) > 3:
            continue

        out.append(candidate)
    return out

# ===============================================================
# FOUNDER DETECTION with evidence (free)
# ===============================================================
@st.cache_data(show_spinner=False, ttl=86400)
def detect_founders_with_evidence(company: str):
    """
    Returns (top_names, evidence_dict)
      top_names: list[str]
      evidence_dict: { name -> { score:int, sources:list[str] } }
    """
    if not company:
        return [], {}

    queries = [
        f"{company} founder",
        f"{company} cofounder",
        f"{company} founders",
        f"{company} CEO",
        f"{company} leadership",
        f"site:linkedin.com/in {company} founder",
        f"site:linkedin.com/company {company} about",
        f"site:wikipedia.org {company} founder",
        f"site:github.com {company} founder",
        f"{company} press release founder",
    ]

    from collections import Counter, defaultdict
    scores = Counter()
    evidence = defaultdict(lambda: {"score": 0, "sources": set()})

    for q in queries:
        items = serp(q, num=3)
        for item in items:
            ttl = item.get("title", "") or ""
            sn  = item.get("snippet", "") or ""
            url = item.get("url", "") or ""
            dom = _up(url).netloc if url else ""
            text = f"{ttl}. {sn}"

            names = _extract_names(text)

            boost = 3 if "founder" in q.lower() else 1
            if "linkedin.com/in" in url: boost += 2
            if "wikipedia.org"   in url: boost += 2
            if "techcrunch.com"  in url or "press" in url: boost += 1

            for n in names:
                scores[n] += boost
                evidence[n]["score"] += boost
                if dom:
                    evidence[n]["sources"].add(dom)

    ranked = sorted(
        scores.items(),
        key=lambda kv: (kv[1], len(evidence[kv[0]]["sources"])),
        reverse=True
    )
    top_names = [nm for nm, _ in ranked][:3]

    ev_dict = {
        nm: {
            "score": evidence[nm]["score"],
            "sources": sorted(list(evidence[nm]["sources"]))[:3]
        } for nm in top_names
    }
    return top_names, ev_dict

# ===============================================================
# SIMPLE UI (Accordion + Evidence + Auto Scoring)
# ===============================================================
with st.form("company_form", clear_on_submit=False):
    name = st.text_input("Company name", "")
    submitted = st.form_submit_button("Run")

if submitted and not name:
    st.warning("Please enter a company name to continue.")

if submitted and name:
    # --- Founder detection (only after submit) ---
    detected, ev_dict = detect_founders_with_evidence(name)
    founder_hint = ", ".join(detected) if detected else ""
    if not detected:
        st.warning("No founders confidently detected from public snippets. You can type a founder name to guide scoring.")

    founder_hint = st.text_input("Founder (optional — override or confirm)",
                                 value=founder_hint,
                                 help="Comma-separated if multiple.")

    if ev_dict:
        st.caption("Founder detection evidence (public sources):")
        rows = []
        for nm, ev in ev_dict.items():
            rows.append({
                "Name": nm,
                "Score": ev.get("score", 0),
                "Sources": ", ".join(ev.get("sources", []))
            })
        st.table(rows)

    # --- Founder Potential (automatic) ---
    st.markdown("## Founder Potential")
    if auto_founder_scoring_panel:
        # Pass minimal empty structures for now (your upstream modules can enrich later)
        auto_founder_scoring_panel(
            company_name=name,
            founder_hint=(founder_hint or None),
            sources_list=[],       # you can wire in search sources later
            wiki_summary="",       # optional: feed wiki snippet
            funding_stats={},      # optional: feed funding summary
            market_size=None,      # optional: feed TAM hints
            persist_path=None
        )
    else:
        st.error(f"Founder scoring module not found: {_fp_import_err}")

    # --- Accordion sections (placeholders to keep your structure) ---
    with st.expander("Funding & Investors", expanded=False):
        st.caption("Wire in your funding parser here (rounds, investors, ‘at a glance’).")
    with st.expander("Investor Summary", expanded=False):
        st.caption("Your structured LLM brief (investor summary) can render here.")
    with st.expander("Founder Brief", expanded=False):
        st.caption("Founder bios/highlights/open questions (from LLM brief).")
    with st.expander("Market Map", expanded=False):
        st.caption("Axes, competitors, differentiators (from LLM brief).")
    with st.expander("Market Size & Revenue", expanded=False):
        st.caption("Most recent TAM and revenue estimates (from public sources).")
    with st.expander("Signals (public sources)", expanded=False):
        st.caption("Render raw search results here if desired (overview/team/market/competition).")
