# streamlit_app.py
# Due Diligence Co-Pilot (Lite)
# v0.12.6 — revert headline score to /35; bonus shown separately; coverage=signals with score>0
#            keep clearer Founder Potential legend + context-first Founder Brief

import os
import re
import json
import html
import requests
import streamlit as st
from urllib.parse import urlparse, parse_qs
from datetime import datetime

# ---------------------------
# Local modules (unchanged)
# ---------------------------
from app.llm_guard import generate_once
from app.public_provider import wiki_enrich
from app.funding_lookup import get_funding_data
from app.market_size import get_market_size

# Founder Potential auto panel
try:
    from app.founder_scoring import auto_founder_scoring_panel
except Exception as e:
    auto_founder_scoring_panel = None
    _fp_import_err = str(e)

# ---------------------------
# Streamlit config + layout
# ---------------------------
st.set_page_config(page_title="Due Diligence Co-Pilot (Lite)", layout="wide")
st.markdown(
    """
    <style>
      .block-container { max-width: 980px; margin: auto; }
      .stCaption { opacity: .75 }
      div.streamlit-expanderContent { padding-top: .5rem; }
    </style>
    """,
    unsafe_allow_html=True,
)
st.title("Due Diligence Co-Pilot (Lite)")
st.caption(f"OpenAI key loaded: {'yes' if os.getenv('OPENAI_API_KEY') else 'no'}")
st.caption("Build: v0.12.6 — headline score back to /35; bonus separate; clearer legend")

# ===============================================================
# SEARCH: Google CSE (preferred) → DuckDuckGo HTML (fallback)
# ===============================================================
@st.cache_data(show_spinner=False, ttl=86400)
def serp(query: str, num: int = 3):
    """Return a list of dicts: {title, snippet, url}."""
    num = max(1, min(int(num or 3), 5))

    # Try Google CSE if configured
    cx = os.getenv("GOOGLE_CSE_ID")
    key = os.getenv("GOOGLE_API_KEY")
    if cx and key:
        try:
            r = requests.get(
                "https://www.googleapis.com/customsearch/v1",
                params={"q": query, "cx": cx, "key": key, "num": num},
                timeout=15,
            )
            if r.status_code == 200:
                items = (r.json().get("items") or [])[:num]
                return [{
                    "title": it.get("title", "") or "",
                    "snippet": it.get("snippet", "") or "",
                    "url": it.get("link", "") or ""
                } for it in items]
        except Exception:
            pass  # fall through

    # Fallback: DuckDuckGo HTML (no API key)
    try:
        r = requests.get(
            "https://duckduckgo.com/html/",
            params={"q": query},
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        html_text = r.text
        link_re = re.compile(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.I | re.S)
        snip_re = re.compile(r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>', re.I | re.S)
        links = link_re.findall(html_text)
        snips = snip_re.findall(html_text)

        out = []
        for i, (href, title_html) in enumerate(links[:num]):
            url = href
            try:
                if href.startswith("/l/?"):
                    q = parse_qs(urlparse(href).query)
                    url = q.get("uddg", [f"https://duckduckgo.com{href}"])[0]
                elif href.startswith("//"):
                    url = "https:" + href
                elif href.startswith("/"):
                    url = "https://duckduckgo.com" + href
            except Exception:
                pass

            title = html.unescape(re.sub("<.*?>", "", title_html)).strip()
            snippet = ""
            if i < len(snips):
                snippet = html.unescape(re.sub("<.*?>", "", snips[i])).strip()
            out.append({"title": title, "snippet": snippet, "url": url})
        return out[:num]
    except Exception:
        return []

# ===============================================================
# Helpers
# ===============================================================
def _domain(u: str) -> str:
    try:
        return urlparse(u).netloc.lower()
    except Exception:
        return ""

def _abbr_usd(n):
    try:
        n = int(n)
    except Exception:
        return ""
    if n >= 1_000_000_000_000: s = f"{n/1_000_000_000_000:.1f}T"
    elif n >= 1_000_000_000:   s = f"{n/1_000_000_000:.1f}B"
    elif n >= 1_000_000:       s = f"{n/1_000_000:.1f}M"
    elif n >= 1_000:           s = f"{n/1_000:.0f}K"
    else: return f"${n:,}"
    return f"${s.rstrip('0').rstrip('.')}"

def _fmt_date(s: str | None) -> str:
    if not s: return ""
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%b %d, %Y", "%B %d, %Y", "%b %d %Y", "%B %d %Y", "%Y"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.strftime("%Y") if fmt == "%Y" else dt.strftime("%b %d, %Y")
        except Exception:
            pass
    return s

def _dedup_list(items):
    seen=set(); out=[]
    for x in items or []:
        if x and x not in seen:
            seen.add(x); out.append(x)
    return out

def tidy(results, prefer=(), limit=3):
    seen=set(); cleaned=[]
    for r in results or []:
        url=r.get("url") or ""
        ttl=(r.get("title") or "").lower()
        if "search error" in ttl and not url:
            cleaned.append(r); continue
        if not url or url in seen: continue
        seen.add(url); cleaned.append(r)
    if prefer:
        cleaned.sort(key=lambda x: any(p in (x.get("url") or "") for p in prefer), reverse=True)
    return cleaned[:limit]

# ===============================================================
# Funding helpers (unchanged)
# ===============================================================
def _funding_stats(funding: dict) -> dict:
    rounds = (funding or {}).get("rounds") or []
    total = 0; largest=None; leads_all=[]
    for r in rounds:
        amt = r.get("amount_usd")
        if isinstance(amt, int):
            total += amt
            if not largest or amt > (largest.get("amount_usd") or 0):
                largest = {
                    "round": r.get("round"),
                    "date": r.get("date"),
                    "amount_usd": amt,
                    "lead": (", ".join(r.get("lead_investors") or []) or None),
                }
        leads_all.extend(r.get("lead_investors") or [])
        leads_all.extend(r.get("other_investors") or [])
    return {"total_usd": total if total>0 else None, "largest": largest, "lead_investors": _dedup_list(leads_all)[:6]}

def funding_glance_sentence(stats: dict) -> str:
    if not stats or not any(stats.values()): return "No public funding details found."
    parts=[]; total=stats.get("total_usd")
    if total: parts.append(f"Total {_abbr_usd(total)}")
    largest = stats.get("largest") or {}
    lr_round, lr_amt, lr_date = largest.get("round"), largest.get("amount_usd"), largest.get("date")
    if lr_amt:
        if lr_round and lr_date: parts.append(f"Largest {lr_round} {_abbr_usd(lr_amt)} ({_fmt_date(lr_date)})")
        elif lr_round:           parts.append(f"Largest {lr_round} {_abbr_usd(lr_amt)}")
        else:                    parts.append(f"Largest {_abbr_usd(lr_amt)}")
    leads = stats.get("lead_investors") or []
    if leads: parts.append("Leads " + ", ".join(leads[:5]))
    return " · ".join(parts) if parts else "No public funding details found."

# ===============================================================
# Founder detection (robust)
# ===============================================================
NAME_RE = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\b")

BLACKLIST_TOKENS = {
    "Inc","LLC","Ltd","Series","Founder","CEO","Co",
    "Cofounder","Co-founder","Founder/CEO","University","College",
    "Institute","Lab","Labs","School","Center","Research","Foundation",
    "Holdings","Capital","Ventures","Official","Profile","View","Press"
}

LOCATION_BLACKLIST = {
    "San Francisco","New York","London","Boston","Los Angeles","Silicon Valley",
    "United States","USA","California","Texas","Paris","Berlin","Toronto",
    "Chicago","Miami","Seattle","Austin","Dublin","Bengaluru","Tokyo"
}

def _extract_names(text: str) -> list[str]:
    if not text:
        return []
    out = []
    for m in NAME_RE.findall(text):
        candidate = m.strip()
        parts = candidate.split()
        if any(len(p) < 2 or not p.isalpha() for p in parts):
            continue
        if any(p in BLACKLIST_TOKENS for p in parts):
            continue
        if candidate in LOCATION_BLACKLIST:
            continue
        if len(parts) > 3:
            continue
        out.append(candidate)
    return out

@st.cache_data(show_spinner=False, ttl=86400)
def detect_founders_with_evidence(company: str):
    """Return (top_names, evidence_dict[name] -> {score, sources}, all_urls)"""
    if not company:
        return [], {}, []

    queries = [
        f"{company} founder",
        f"{company} cofounder",
        f"{company} founders",
        f"{company} CEO",
        f"{company} leadership",
        f"site:linkedin.com/in {company} founder",
        f"site:linkedin.com/company {company} about",
        f"site:wikipedia.org {company} founder",
        f"{company} press release founder",
    ]

    from collections import Counter, defaultdict
    scores = Counter()
    evidence = defaultdict(lambda: {"score": 0, "sources": set()})
    all_urls = []

    for q in queries:
        for item in serp(q, num=3):
            ttl = item.get("title","") or ""
            sn  = item.get("snippet","") or ""
            url = item.get("url","") or ""
            dom = _domain(url)
            if url: all_urls.append(url)

            text = f"{ttl}. {sn}"
            names = _extract_names(text)

            boost = 3 if "founder" in q.lower() else 1
            if "linkedin.com/in" in url: boost += 2
            if "wikipedia.org"   in url: boost += 2
            if "techcrunch.com"  in url or "press" in url: boost += 1

            for n in names:
                scores[n] += boost
                evidence[n]["score"] += boost
                if dom: evidence[n]["sources"].add(dom)

    ranked = sorted(scores.items(), key=lambda kv: (kv[1], len(evidence[kv[0]]["sources"])), reverse=True)
    top = [nm for nm, _ in ranked][:3]
    ev = {nm: {"score": evidence[nm]["score"], "sources": sorted(list(evidence[nm]["sources"]))[:3]} for nm in top}
    return top, ev, _dedup_list(all_urls)[:10]

# ===============================================================
# JSON schema for the guarded OpenAI brief (unchanged)
# ===============================================================
JSON_SCHEMA = {
    "name": "DDLite",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "investor_summary": {"type": "string"},
            "founder_brief": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "founders": {"type": "array", "items": {"type": "string"}},
                    "highlights": {"type": "array", "items": {"type": "string"}},
                    "open_questions": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["founders", "highlights", "open_questions"]
            },
            "market_map": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "axes": {"type": "array", "items": {"type": "string"}},
                    "competitors": {"type": "array", "items": {"type": "string"}},
                    "differentiators": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["axes", "competitors", "differentiators"]
            },
            "market_size": {"type": "string"},
            "estimated_revenue": {"type": "string"},
            "monetization": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "business_model": {"type": "string"},
                    "revenue_streams": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["business_model", "revenue_streams"]
            },
            "sources": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "url": {"type": "string"},
                        "note": {"type": "string"}
                    },
                    "required": ["url", "note"]
                }
            }
        },
        "required": [
            "investor_summary",
            "founder_brief",
            "market_map",
            "market_size",
            "estimated_revenue",
            "monetization",
            "sources"
        ]
    }
}

# ===============================================================
# UI state & form
# ===============================================================
for key, default in [
    ("company",""),
    ("gen_summary", True),
    ("gen_founder_brief", True),
    ("gen_market_map", True),
    ("_busy", False),
    ("llm_data", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default

with st.form("company_form", clear_on_submit=False):
    company_input = st.text_input("Company name", value=st.session_state.company)
    examples = ["", "Anthropic", "Plaid", "RunwayML", "Ramp", "Figma"]
    ex = st.selectbox("Or pick an example", examples, index=0)
    if ex: company_input = ex

    gen_summary_input   = st.checkbox("Generate Investor Summary (OpenAI)", value=st.session_state.gen_summary)
    gen_founder_input   = st.checkbox("Generate Founder Brief (OpenAI)", value=st.session_state.gen_founder_brief)
    gen_marketmap_input = st.checkbox("Generate Market Map (OpenAI)", value=st.session_state.gen_market_map)

    submitted = st.form_submit_button("Run", use_container_width=True)

if submitted:
    st.session_state.company = (company_input or "").strip()
    st.session_state.gen_summary = gen_summary_input
    st.session_state.gen_founder_brief = gen_founder_input
    st.session_state.gen_market_map = gen_marketmap_input
    st.session_state.llm_data = None  # reset last run

name = st.session_state.company
if submitted and not name:
    st.warning("Please enter a company name to continue.")

# ===============================================================
# Main flow after submit
# ===============================================================
if submitted and name:
    st.success(f"Profile for {name}")

    # --- Gather signals
    with st.spinner("Gathering public signals..."):
        overview_results = tidy(serp(f"{name} official site"), prefer=("about","wikipedia.org","crunchbase.com","linkedin.com"))
        team_results     = tidy(serp(f"{name} founders team leadership"), prefer=("about","team","wikipedia.org","linkedin.com","crunchbase.com"))
        market_results   = tidy(serp(f"{name} target market TAM customers industry"), prefer=("gartner.com","forrester.com","mckinsey.com","bain.com"))
        competition_results = tidy(serp(f"{name} competitors alternatives comparative"), prefer=("g2.com","capterra.com","crunchbase.com","wikipedia.org"))

    wiki = wiki_enrich(name)  # {"title","url","summary"} or None

    funding = get_funding_data(name, serp_func=lambda q, num=3: serp(q, num))
    funding_stats = _funding_stats(funding)

    market_size = get_market_size(name, serp_func=lambda q, num=3: serp(q, num))
    def _best_tam_line(ms: dict) -> str:
        ests = (ms or {}).get("estimates") or []
        if not ests: return "Market context: TAM not found from trusted public sources."
        best = ests[0]; amt = _abbr_usd(best.get("amount_usd")); year = best.get("year") or ""
        src = best.get("url") or ""; host = _domain(src)
        tail = f" ({year}, {host})" if (year or host) else ""
        return f"Market context: TAM of {amt}{tail}."
    market_context_line = _best_tam_line(market_size)

    # --- Build sources for LLM grounding
    sources_list=[]
    for coll in (overview_results, team_results, market_results, competition_results):
        for it in coll:
            if it.get("url"): sources_list.append(it["url"])
    if wiki and wiki.get("url"): sources_list.insert(0, wiki["url"])
    for s in (funding.get("sources") or []):       sources_list.append(s)
    for s in (market_size.get("sources") or []):   sources_list.append(s)
    sources_list = _dedup_list(sources_list)[:12]

    # --- Founder detection (robust) + evidence + manual override
    detected, evidence, founder_urls = detect_founders_with_evidence(name)
    founder_hint = ", ".join(detected) if detected else ""
    founder_hint = st.text_input("Founder (optional — override or confirm)", value=founder_hint, help="Comma-separated if multiple.")
    if evidence:
        st.caption("Founder detection evidence (public sources):")
        rows = [{"Name": nm, "Score": evidence[nm]["score"], "Sources": ", ".join(evidence[nm]["sources"])} for nm in evidence]
        st.table(rows)

    # --- Founder Potential (automatic) — /35 headline + separate bonus
    st.markdown("## Founder Potential (first-pass signals)")
    st.caption(
        "Quick, automated read from public sources — use this to **triage**, not decide. "
        "Add a founder’s LinkedIn or About page above and re-run for better coverage."
    )

    # Context chips
    summary_bits = []
    if detected:
        summary_bits.append(f"Founders: {', '.join(detected)}")
    else:
        summary_bits.append("Founders not confidently identified")
    if funding_stats.get("total_usd"):
        summary_bits.append(f"Public funding: {_abbr_usd(funding_stats['total_usd'])}")
    if wiki and wiki.get("summary"):
        summary_bits.append("Wikipedia summary found")

    chips = " ".join(
        f"<span style='background:#f1f5f9;border:1px solid #e2e8f0;border-radius:999px;"
        f"padding:2px 8px;font-size:12px;color:#334155'>{html.escape(bit)}</span>"
        for bit in summary_bits
    )
    st.markdown(chips, unsafe_allow_html=True)

    # Legend — base only in headline; bonus separate; coverage = score>0
    with st.expander("How this score works", expanded=False):
        st.markdown(
            "- **Score (out of 35):** 7 founder signals × up to 5 points each. This is the headline score.\n"
            "- **Bonus (0–5):** shown separately for standout traits from public sources "
            "(e.g., repeat founder, strong technical background, fast product cadence). **Not added** to the headline.\n"
            "- **Coverage:** % of signals with **score > 0** (evidence-based).\n"
            "- If you want a combined view, mentally add Score + Bonus (max 40), but we report /35 to avoid over-weighting sparse traits."
        )

    # Raw scoring UI (original panel) behind details
    with st.expander("Detailed scoring (show)", expanded=False):
        if auto_founder_scoring_panel:
            sources_for_scoring = _dedup_list(sources_list + founder_urls)[:15]
            auto_founder_scoring_panel(
                company_name=name,
                founder_hint=(founder_hint or None),
                sources_list=sources_for_scoring,
                wiki_summary=(wiki.get("summary") if wiki and wiki.get("summary") else ""),
                funding_stats=funding_stats,
                market_size=market_size,
                persist_path=None,
            )
        else:
            st.error(f"Founder scoring module not found: {_fp_import_err}")

    # -------------------------------
    # Investor Summary (generates JSON ONCE and saves it)
    # -------------------------------
    with st.expander("Investor Summary", expanded=True):
        data = st.session_state.llm_data
        if st.session_state.gen_summary or st.session_state.gen_founder_brief or st.session_state.gen_market_map:
            if not os.getenv("OPENAI_API_KEY"):
                st.info("Set OPENAI_API_KEY in Streamlit Secrets to enable AI sections.")
            else:
                if data is None:
                    try:
                        wiki_hint = (wiki.get("summary")[:600] if wiki and wiki.get("summary") else "").strip()
                        ms_hints = []
                        for e in (market_size.get("estimates") or [])[:3]:
                            amt = e.get("amount_usd"); year = e.get("year") or "n/a"; scope = e.get("scope") or "Market size"
                            if amt: ms_hints.append(f"- {scope}: {_abbr_usd(amt)} ({year})")
                        ms_hints_txt = "\n".join(ms_hints) if ms_hints else "- None found"

                        prompt = f"""
Return ONE JSON object that matches the provided schema.
Company: {name}
Website: null
User-provided sources: {sources_list}

Background (optional, from Wikipedia):
{wiki_hint}

Known funding facts (parsed from public sources; prefer these over guessing):
- Total funding (USD): {funding_stats.get('total_usd') if funding_stats.get('total_usd') else 'unknown'}
- Largest round: {((funding_stats.get('largest') or {}).get('round')) or 'unknown'}
- Largest round amount: {((funding_stats.get('largest') or {}).get('amount_usd')) or 'unknown'}
- Largest round date: {((funding_stats.get('largest') or {}).get('date')) or 'unknown'}
- Lead investor(s): {', '.join(funding_stats.get('lead_investors') or []) or 'unknown'}

Known market size indications (from public snippets):
{ms_hints_txt}

Instructions:
- Only use fields defined in the schema and keep them concise.
- For investor_summary: return 5 bullets as plain text, each starting with "- " on a NEW LINE (no numbering).
  The bullets MUST cover, in order:
  1) What the company does (one line).
  2) Funding to date in short format (e.g., "$1.0B"), and the largest round as:
     "Largest: <Round> <amount short> (<YYYY-MM-DD>)". Use the Known funding facts above verbatim when available.
  3) Lead investor(s).
  4) Market context (TAM/category positioning).
  5) 1–2 open diligence questions.
- For founder_brief: founders as "Name - 1–2 sentence bio (role + notable facts)"; plus highlights and open_questions.
- For market_map: 1–2 axes, 3–5 competitors, 2–4 differentiators.
- For market_size: most recent credible TAM (USD + region + source + year). If unknown, say "Not found from public sources."
- For estimated_revenue: most recent public revenue/ARR/gross bookings (USD + metric + year + source). If unknown, say "Not found".
- For monetization: short business_model + 2–5 revenue_streams.
- For sources: include up to 10 URLs with a short note; notes can be empty strings.
Return ONLY the JSON object; no markdown, no commentary.
""".strip()
                        with st.spinner("Generating structured brief..."):
                            data = generate_once(prompt, JSON_SCHEMA)
                        st.session_state.llm_data = data  # SAVE for other sections
                    except Exception:
                        st.error("There was a problem generating the brief. Showing public signals instead.")
                        data = None

        if data:
            inv = (data.get("investor_summary") or "").strip()
            src = data.get("sources") or []

            lines = [ln.strip() for ln in inv.replace("\r", "").split("\n") if ln.strip()] if inv else []
            bullets = []
            for b in (lines or []):
                b = b.lstrip("•- ").strip()
                if not b.endswith((".", "?", "!")): b += "."
                bullets.append(b)

            # ensure funding bullet is consistent with parsed stats
            try:
                total = funding_stats.get("total_usd")
                largest = funding_stats.get("largest") or {}
                lr_round = largest.get("round"); lr_amt = largest.get("amount_usd"); lr_date = largest.get("date")
                parts = [f"Funding to date: {_abbr_usd(total) or 'unknown'}."]
                if lr_amt:
                    if lr_round and lr_date: parts.append(f"Largest: {lr_round} {_abbr_usd(lr_amt)} ({_fmt_date(lr_date)}).")
                    elif lr_round:            parts.append(f"Largest: {lr_round} {_abbr_usd(lr_amt)}.")
                    else:                     parts.append(f"Largest: {_abbr_usd(lr_amt)}.")
                b2 = " ".join(parts)
                if len(bullets) >= 2: bullets[1] = b2
                elif bullets: bullets.insert(1, b2)
                else: bullets = [b2]
            except Exception:
                pass

            # force market context line
            if market_context_line:
                if len(bullets) >= 4: bullets[3] = market_context_line
                else: bullets.append(market_context_line)

            for b in bullets[:7]:
                st.write(f"- {b}")

            # Source links
            if src:
                links = []
                for s in src[:8]:
                    u = s.get("url",""); note = (s.get("note") or "").strip()
                    if not u: continue
                    label = note or _domain(u) or "source"
                    links.append(f"[{label}]({u})")
                if links:
                    st.markdown("**Sources:** " + " · ".join(links))
        else:
            st.caption("LLM summary unavailable. See Signals section for public sources.")

    # -------------------------------
    # Founder Brief — context-first skim view
    # -------------------------------
    with st.expander("Founder Brief", expanded=False):
        data = st.session_state.llm_data
        if not data or not isinstance(data, dict):
            st.info("No founder brief generated yet. Enable 'Generate Investor Summary' and run again.")
        else:
            fb = data.get("founder_brief") or {}
            founders_raw = [x for x in (fb.get("founders") or []) if x]
            highlights   = [x for x in (fb.get("highlights") or []) if x]
            open_qs      = [x for x in (fb.get("open_questions") or []) if x]

            # Parse founder lines into (name, role, blurb)
            founders = []
            for line in founders_raw:
                parts = re.split(r"\s+[-—]\s+", str(line), 1)
                name  = parts[0].strip()
                blurb = parts[1].strip() if len(parts) > 1 else ""
                role_match = re.search(
                    r"\b(CEO|CTO|COO|CFO|Chief [A-Za-z]+|[Cc]o-?founder|Founder|Head of [A-Za-z ]+)\b",
                    blurb
                )
                role = role_match.group(0) if role_match else "Founder"
                founders.append((name, role, blurb))

            # ---------- Context first ----------
            st.markdown("**How to read this**")
            st.caption(
                "This section supports first-pass founder assessment using a seven-signal rubric "
                "(domain insight, execution, hiring pull, communication, customer focus, learning speed, integrity). "
                "Start with the quick takeaways below, then scan the bios."
            )

            # Compact skim view
            compact = st.checkbox("Compact view", value=True, help="Show only at-a-glance + top takeaways.")

            cols = st.columns(2)
            with cols[0]:
                st.markdown("**Founders (at a glance)**")
                if founders:
                    chips = " ".join([
                        f"<span style='background:#eef2ff;border:1px solid #c7d2fe;"
                        f"border-radius:999px;padding:2px 8px;font-size:12px;color:#3730a3'>"
                        f"{html.escape(n)} · {html.escape(r)}</span>"
                        for (n, r, _) in founders[:6]
                    ])
                    st.markdown(chips, unsafe_allow_html=True)
                else:
                    st.caption("No founders parsed from the brief.")

            with cols[1]:
                st.markdown("**Read this first**")
                read_first = []
                read_first.extend(highlights[:2])
                if open_qs:
                    read_first.append(open_qs[0])
                if read_first:
                    for p in read_first:
                        st.write(f"- {p}")
                else:
                    st.caption("No highlights or open questions found in the brief.")

            if not compact:
                st.divider()
                # Full bios
                if founders:
                    st.markdown("**Founder bios**")
                    for name, role, blurb in founders:
                        if blurb:
                            st.write(f"- **{name}** ({role}) — {blurb}")
                        else:
                            st.write(f"- **{name}** ({role})")
                # Additional details
                if highlights:
                    st.markdown("**Additional highlights**")
                    for h in highlights[:8]:
                        st.write(f"- {h}")
                if open_qs:
                    st.markdown("**Open questions**")
                    for q in open_qs[:6]:
                        st.write(f"- {q}")
                if not any([founders, highlights, open_qs]):
                    st.caption("No structured founder details in the current JSON output.")

    # -------------------------------
    # Market Map — renders from saved JSON
    # -------------------------------
    with st.expander("Market Map", expanded=False):
        data = st.session_state.llm_data
        if not data or not isinstance(data, dict):
            st.info("No market map generated yet. Enable 'Generate Investor Summary' and run again.")
        else:
            mm = data.get("market_map") or {}
            axes = [x for x in (mm.get("axes") or []) if x]
            competitors = [x for x in (mm.get("competitors") or []) if x]
            diffs = [x for x in (mm.get("differentiators") or []) if x]

            if axes:
                st.markdown("**Positioning Axes**")
                st.write(", ".join(axes))
            if competitors:
                st.markdown("**Competitors**")
                for c in competitors[:10]:
                    st.write(f"- {c}")
            if diffs:
                st.markdown("**Differentiators**")
                for d in diffs[:8]:
                    st.write(f"- {d}")
            if not any([axes, competitors, diffs]):
                st.caption("No structured market map in the current JSON output.")

    # -------------------------------
    # Market Size & Revenue — prefer JSON if present; fall back to TAM line
    # -------------------------------
    with st.expander("Market Size & Revenue", expanded=False):
        data = st.session_state.llm_data
        if data and isinstance(data, dict):
            st.subheader("Market Size (from JSON)")
            st.write((data.get("market_size") or "").strip() or "Not found from public sources.")
            st.subheader("Estimated Revenue")
            st.write((data.get("estimated_revenue") or "").strip() or "Not found")
            mon = data.get("monetization") or {}
            if mon:
                bm = mon.get("business_model") or ""
                rvs = mon.get("revenue_streams") or []
                if bm:
                    st.markdown("**Business model**"); st.write(bm)
                if rvs:
                    st.markdown("**Revenue streams**")
                    for item in rvs[:8]:
                        st.write(f"- {item}")
        else:
            st.subheader("Market Size (from public sources)")
            st.write(market_context_line)

    # -------------------------------
    # Funding & Investors (unchanged)
    # -------------------------------
    with st.expander("Funding & Investors", expanded=False):
        rounds = funding.get("rounds") or []
        investors = funding.get("investors") or []
        st.subheader("Funding & Investors")
        if rounds:
            table_rows = []
            for r in rounds[:10]:
                table_rows.append({
                    "Round": r.get("round") or "",
                    "Date": _fmt_date(r.get("date")),
                    "Amount": _abbr_usd(r.get("amount_usd")) if r.get("amount_usd") else "",
                    "Lead": ", ".join(_dedup_list(r.get("lead_investors") or [])),
                })
            st.table(table_rows)
            st.text(f"Funding at a glance: {funding_glance_sentence(funding_stats)}")
            st.caption("Note: Public-source parse; amounts reflect reported round sizes (not valuations).")
        else:
            st.caption("No funding data found yet (public sources).")
        if investors:
            st.markdown("**Notable investors**")
            st.write(", ".join(_dedup_list(investors[:12])))

    # -------------------------------
    # Signals (public sources)
    # -------------------------------
    with st.expander("Signals (public sources)", expanded=False):
        def _render(title, items, empty_hint):
            st.subheader(title)
            if not items:
                st.caption(empty_hint); return
            for it in items:
                ttl=it.get("title") or "(no title)"; u=it.get("url") or ""; sn=it.get("snippet") or ""
                st.write(f"[{ttl}]({u}) - {sn}" if u else f"{ttl} - {sn}")
        _render("Company Overview", overview_results, "No overview found.")
        _render("Founding Team",    team_results,     "No team info found.")
        _render("Market",           market_results,   "No market info found.")
        _render("Competition",      competition_results, "No competition info found.")

        # Markdown snapshot export
        import datetime as dt
        def md_list(items):
            return "\n".join(f"- [{i.get('title','')}]({i.get('url','')}) - {i.get('snippet','')}" for i in (items or [])) or "_No items_"
        md = f"""# {name} — First-Pass Diligence
_Last updated: {dt.datetime.now().strftime('%Y-%m-%d %H:%M')}_

## Overview
{md_list(overview_results)}

## Founding Team
{md_list(team_results)}

## Market
{md_list(market_results)}

## Competition
{md_list(competition_results)}
"""
        st.download_button("Download snapshot (Markdown)", md, file_name=f"{name}_snapshot.md", use_container_width=True)
