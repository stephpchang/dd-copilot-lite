# streamlit_app.py
# Due Diligence Co-Pilot (Lite) + Founder Potential (Low-Data Mode) up front

import os
import sys
import json
import requests
import streamlit as st
from urllib.parse import urlparse
from datetime import datetime

# --- Founder Potential module (root-level file: founder_scoring.py) ---
# If you keep founder_scoring.py elsewhere, adjust the import accordingly.
try:
    from founder_scoring import founder_scoring_module
except Exception as e:
    founder_scoring_module = None
    _fp_import_err = str(e)

# Existing app modules
from app.llm_guard import generate_once
from app.public_provider import wiki_enrich
from app.funding_lookup import get_funding_data
from app.market_size import get_market_size

# -------------------------------------------------
# App config
# -------------------------------------------------
st.set_page_config(page_title="Due Diligence Co-Pilot (Lite)", layout="centered")
st.title("Due Diligence Co-Pilot (Lite)")
st.caption(f"OpenAI key loaded: {'yes' if os.getenv('OPENAI_API_KEY') else 'no'}")
st.caption("Build: v0.9.3 — Founder Potential module added up front; tabs unchanged")

# -------------------------------------------------
# Founder Potential — Low-Data Mode (front and center)
# -------------------------------------------------
st.subheader("Founder Potential — Low-Data Mode (Score First)")
if founder_scoring_module is None:
    st.warning(
        "Founder scoring module not found. "
        "Place **founder_scoring.py** at the repo root (same folder as this file). "
        f"Import error: {_fp_import_err if '_fp_import_err' in globals() else 'unknown'}"
    )
    result = {}
else:
    # Toggle CSV persistence via env var; keep OFF on Streamlit Cloud initially.
    PERSIST = os.environ.get("FOUNDER_PERSIST", "false").lower() == "true"
    persist_path = os.path.join("data", "founder_scores.csv") if PERSIST else None
    # Render the scoring UI
    result = founder_scoring_module(persist_path=persist_path)

    # Lightweight guidance banner based on evaluation
    ev = (result or {}).get("evaluation", "")
    if ev.startswith(("Outstanding", "Strong")):
        st.success("Flagged for partner review based on Founder Potential Score.")
    elif ev.startswith("Moderate"):
        st.info("Moderate signal — gather more evidence or run quick ref checks.")
    elif ev.startswith("Low"):
        st.warning("Low signal — proceed only if there’s another compelling wedge.")

st.divider()

# -------------------------------------------------
# JSON schema for the guarded single call (unchanged)
# -------------------------------------------------
JSON_SCHEMA = {
    "name": "DDLite",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "investor_summary": {"type": "string"},  # newline-bulleted text
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

# -------------------------------------------------
# Google Custom Search (cached)
# -------------------------------------------------
@st.cache_data(show_spinner=False, ttl=86400)  # 24h to preserve quota
def serp(q, num=3):
    cx = os.getenv("GOOGLE_CSE_ID")
    key = os.getenv("GOOGLE_API_KEY")
    if not cx or not key:
        return []
    num = min(num, 3)
    resp = requests.get(
        "https://www.googleapis.com/customsearch/v1",
        params={"q": q, "cx": cx, "key": key, "num": num},
        timeout=15,
    )
    if resp.status_code != 200:
        return [{
            "title": f"Search error {resp.status_code}",
            "snippet": resp.text[:200],
            "url": "https://developers.google.com/custom-search/v1/overview"
        }]
    items = (resp.json().get("items") or [])[:num]
    return [{"title": it.get("title",""), "snippet": it.get("snippet",""), "url": it.get("link","")} for it in items]

# -------------------------------------------------
# Helpers: formatting & utilities
# -------------------------------------------------
def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""

def _abbr_usd(n):
    try:
        n = int(n)
    except Exception:
        return ""
    if n >= 1_000_000_000_000:
        s = f"{n/1_000_000_000_000:.1f}T"
    elif n >= 1_000_000_000:
        s = f"{n/1_000_000_000:.1f}B"
    elif n >= 1_000_000:
        s = f"{n/1_000_000:.1f}M"
    elif n >= 1_000:
        s = f"{n/1_000:.0f}K"
    else:
        return f"${n:,}"
    s = s.rstrip("0").rstrip(".")
    return f"${s}"

def _fmt_usd_full(n):
    try:
        return f"${int(n):,}"
    except Exception:
        return ""

def _dedup_list(items):
    seen = set(); out=[]
    for x in items or []:
        if x and x not in seen:
            seen.add(x); out.append(x)
    return out

def _fmt_date(s: str | None) -> str:
    if not s:
        return ""
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%b %d, %Y", "%B %d, %Y", "%b %d %Y", "%B %d %Y", "%Y"):
        try:
            dt = datetime.strptime(s, fmt)
            if fmt == "%Y":
                return dt.strftime("%Y")
            return dt.strftime("%b %d, %Y")
        except Exception:
            continue
    return s

# -------------------------------------------------
# Funding helpers
# -------------------------------------------------
def _funding_stats(funding: dict) -> dict:
    rounds = (funding or {}).get("rounds") or []
    total = 0
    largest = None
    leads_all = []
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
    return {
        "total_usd": total if total > 0 else None,
        "largest": largest,
        "lead_investors": _dedup_list(leads_all)[:6],
    }

def funding_glance_sentence(stats: dict) -> str:
    if not stats or not any(stats.values()):
        return "No public funding details found."
    parts = []
    total = stats.get("total_usd")
    if total:
        parts.append(f"Total {_abbr_usd(total)}")
    largest = stats.get("largest") or {}
    lr_round = largest.get("round")
    lr_amt   = largest.get("amount_usd")
    lr_date  = largest.get("date")
    if lr_amt:
        if lr_round and lr_date:
            parts.append(f"Largest {lr_round} {_abbr_usd(lr_amt)} ({_fmt_date(lr_date)})")
        elif lr_round:
            parts.append(f"Largest {lr_round} {_abbr_usd(lr_amt)}")
        else:
            parts.append(f"Largest {_abbr_usd(lr_amt)}")
    leads = stats.get("lead_investors") or []
    if leads:
        parts.append("Leads " + ", ".join(leads[:5]))
    return " · ".join(parts) if parts else "No public funding details found."

# -------------------------------------------------
# Result cleanup + rendering
# -------------------------------------------------
def tidy(results, prefer=(), limit=3):
    seen, cleaned = set(), []
    for r in results or []:
        url = r.get("url") or ""
        title = (r.get("title") or "").lower()
        if "search error" in title and not url:
            cleaned.append(r)
            continue
        if not url or url in seen:
            continue
        seen.add(url)
        cleaned.append(r)
    if prefer:
        cleaned.sort(key=lambda x: any(p in (x.get("url") or "") for p in prefer), reverse=True)
    return cleaned[:limit]

def render_section(title, items, empty_hint):
    st.subheader(title)
    if not items:
        st.caption(empty_hint)
        return
    for it in items:
        ttl = it.get("title") or "(no title)"
        url = it.get("url") or ""
        snip = it.get("snippet") or ""
        if url:
            st.write(f"[{ttl}]({url}) - {snip}")
        else:
            st.write(f"{ttl} - {snip}")

# -------------------------------------------------
# UI state
# -------------------------------------------------
for key, default in [
    ("company", ""),
    ("gen_summary", True),
    ("gen_founder_brief", True),
    ("gen_market_map", True),
    ("_busy", False),
]:
    if key not in st.session_state:
        st.session_state[key] = default

examples = ["", "Anthropic", "Plaid", "RunwayML", "Ramp", "Figma"]

with st.form("search_form", clear_on_submit=False):
    company_input = st.text_input("Enter company name or website", value=st.session_state.company)
    example = st.selectbox("Or pick an example", examples, index=0)
    if example:
        company_input = example

    gen_summary_input   = st.checkbox("Generate Investor Summary (OpenAI)", value=st.session_state.gen_summary)
    gen_founder_input   = st.checkbox("Generate Founder Brief (OpenAI)", value=st.session_state.gen_founder_brief)
    gen_marketmap_input = st.checkbox("Generate Market Map (OpenAI)", value=st.session_state.gen_market_map)

    submitted = st.form_submit_button("Run", disabled=st.session_state.get("_busy", False))

if submitted:
    st.session_state.company = (company_input or "").strip()
    st.session_state.gen_summary = gen_summary_input
    st.session_state.gen_founder_brief = gen_founder_input
    st.session_state.gen_market_map = gen_marketmap_input

name = st.session_state.company
gen_summary = st.session_state.gen_summary
gen_founder = st.session_state.gen_founder_brief
gen_mmap = st.session_state.gen_market_map

if submitted and not name:
    st.warning("Please enter a company name.")

if submitted and name:
    st.success(f"Profile for {name}")

    # -------------------------------------------------
    # Gather web signals
    # -------------------------------------------------
    with st.spinner("Gathering signals..."):
        overview_results = tidy(
            serp(f"{name} official site"),
            prefer=("about", "wikipedia.org", "crunchbase.com", "linkedin.com")
        )
        team_results = tidy(
            serp(f"{name} founders team leadership"),
            prefer=("about", "team", "wikipedia.org", "linkedin.com", "crunchbase.com")
        )
        market_results = tidy(
            serp(f"{name} target market TAM customers industry"),
            prefer=("gartner.com", "forrester.com", "mckinsey.com", "bain.com")
        )
        competition_results = tidy(
            serp(f"{name} competitors alternatives comparative"),
            prefer=("g2.com", "capterra.com", "crunchbase.com", "wikipedia.org")
        )

    wiki = wiki_enrich(name)  # {"title","url","summary"} or None

    # -------------------------------------------------
    # Funding & Investors
    # -------------------------------------------------
    funding = get_funding_data(name, serp_func=lambda q, num=3: serp(q, num))
    funding_stats = _funding_stats(funding)

    # -------------------------------------------------
    # Market Size (TAM) for hints + deterministic market context line
    # -------------------------------------------------
    market_size = get_market_size(name, serp_func=lambda q, num=3: serp(q, num))

    def _best_tam_line(ms: dict) -> str:
        ests = (ms or {}).get("estimates") or []
        if not ests:
            return "Market context: TAM not found from trusted public sources."
        best = ests[0]
        amt = _abbr_usd(best.get("amount_usd"))
        year = best.get("year") or ""
        src = best.get("url") or ""
        host = urlparse(src).netloc if src else ""
        tail = f" ({year}, {host})" if (year or host) else ""
        return f"Market context: TAM of {amt}{tail}."
    market_context_line = _best_tam_line(market_size)

    # -------------------------------------------------
    # Build grounding sources for the LLM
    # -------------------------------------------------
    sources_list = []
    for coll in (overview_results, team_results, market_results, competition_results):
        for it in coll:
            if it.get("url"):
                sources_list.append(it["url"])
    if wiki and wiki.get("url"):
        sources_list.insert(0, wiki["url"])
    for s in (funding.get("sources") or []):
        if s:
            sources_list.append(s)
    for s in (market_size.get("sources") or []):
        if s:
            sources_list.append(s)
    sources_list = _dedup_list(sources_list)[:12]

    # -------------------------------------------------
    # Single guarded OpenAI call (only if any AI section is requested)
    # -------------------------------------------------
    data = None
    if gen_summary or gen_founder or gen_mmap:
        if not os.getenv("OPENAI_API_KEY"):
            st.info("Set OPENAI_API_KEY in Streamlit Secrets to enable AI sections.")
        else:
            st.session_state._busy = True
            try:
                wiki_hint = (wiki.get("summary")[:600] if wiki and wiki.get("summary") else "").strip()

                # short TAM hints
                ms_hints = []
                for e in (market_size.get("estimates") or [])[:3]:
                    amt = e.get("amount_usd")
                    year = e.get("year") or "n/a"
                    scope = e.get("scope") or "Market size"
                    if amt:
                        ms_hints.append(f"- {scope}: {_abbr_usd(amt)} ({year})")
                ms_hints_txt = "\n".join(ms_hints) if ms_hints else "- None found"

                prompt = f"""
Return ONE JSON object that matches the provided schema.
Company: {name}
Website: null
User-provided sources: {sources_list}

Background (optional, from Wikipedia):
{wiki_hint}

Known funding facts (parsed from public sources; prefer these over guessing):
- Total funding (USD): {_fmt_usd_full(funding_stats.get('total_usd')) or 'unknown'}
- Largest round: {((funding_stats.get('largest') or {}).get('round')) or 'unknown'}
- Largest round amount: {_fmt_usd_full((funding_stats.get('largest') or {}).get('amount_usd')) or 'unknown'}
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

            except Exception:
                st.error("There was a problem generating the brief. Showing public signals instead.")
                data = None
            finally:
                st.session_state._busy = False

    # -------------------------------------------------
    # Tabs
    # -------------------------------------------------
    tabs = st.tabs([
        "Funding",
        "Investor Summary",
        "Founder Brief",
        "Market Map",
        "Market Size & Revenue",
        "Signals",
        "JSON"
    ])

    # -------- Funding tab --------
    with tabs[0]:
        st.subheader("Funding & Investors")
        rounds = funding.get("rounds") or []
        investors = funding.get("investors") or []

        if rounds:
            rows = []
            for r in rounds[:8]:
                rows.append({
                    "Round": r.get("round") or "",
                    "Date": _fmt_date(r.get("date")),
                    "Amount": _abbr_usd(r.get("amount_usd")) if r.get("amount_usd") else "",
                    "Lead": ", ".join(_dedup_list(r.get("lead_investors") or [])),
                })
            st.table(rows)
            st.text(f"Funding at a glance: {funding_glance_sentence(funding_stats)}")
            st.caption("Note: Public-source parse; amounts reflect reported round sizes (not valuations).")
        else:
            st.caption("No funding data found yet (public sources).")

        if investors:
            st.markdown("**Notable investors**")
            st.write(", ".join(_dedup_list(investors[:10])))

    # -------- Investor Summary tab --------
    with tabs[1]:
        st.subheader("Investor Summary")
        if data:
            inv = (data.get("investor_summary") or "").strip()
            src = data.get("sources") or []

            lines = [ln.strip() for ln in inv.replace("\r", "").split("\n") if ln.strip()] if inv else []
            if not lines and inv:
                lines = [b.strip() for b in inv.split(". ") if b.strip()]
            bullets = []
            for b in lines:
                b = b.lstrip("•- ").strip()
                if not b.endswith((".", "?", "!")):
                    b += "."
                bullets.append(b)

            try:
                total = funding_stats.get("total_usd")
                largest = funding_stats.get("largest") or {}
                lr_round = largest.get("round")
                lr_amt = largest.get("amount_usd")
                lr_date = largest.get("date")
                parts = [f"Funding to date: {_abbr_usd(total) or 'unknown'}."]
                if lr_amt:
                    if lr_round and lr_date:
                        parts.append(f"Largest: {lr_round} {_abbr_usd(lr_amt)} ({_fmt_date(lr_date)}).")
                    elif lr_round:
                        parts.append(f"Largest: {lr_round} {_abbr_usd(lr_amt)}.")
                    else:
                        parts.append(f"Largest: {_abbr_usd(lr_amt)}.")
                force_b2 = " ".join(parts)
                if len(bullets) >= 2:
                    bullets[1] = force_b2
                elif bullets:
                    bullets.insert(1, force_b2)
                else:
                    bullets = [force_b2]
            except Exception:
                pass

            market_context_line = "Market context: TAM not found from trusted public sources."
            try:
                # reuse prior calc if exists
                pass
            except Exception:
                pass

            for b in bullets[:7]:
                st.write(f"- {b}")

            # Sources inline
            def render_sources(sources, limit=8):
                links = []
                for s in (sources or [])[:limit]:
                    url, note = s.get("url",""), (s.get("note") or "")
                    if not url:
                        continue
                    dom = _domain(url) or "source"
                    label = note.strip() or dom
                    links.append(f"[{label}]({url})")
                if links:
                    st.markdown("**Sources:** " + " · ".join(links))
            render_sources(src)
        else:
            st.caption("LLM summary unavailable. See Signals tab for public sources.")

    # -------- Founder Brief tab --------
    with tabs[2]:
        st.subheader("Founder Brief")
        if data:
            fb  = data.get("founder_brief") or {}
            src = data.get("sources") or []

            def _clean_items(items):
                out = []
                for x in items or []:
                    if not x:
                        continue
                    s = str(x).strip()
                    if not s:
                        continue
                    if s.lower() in ("unknown", "n/a", "na", "none"):
                        continue
                    out.append(s)
                return out

            founders        = _clean_items((fb.get("founders") or [])[:5])
            founder_points  = _clean_items((fb.get("highlights") or [])[:6])
            open_qs         = _clean_items((fb.get("open_questions") or [])[:4])

            if founders:
                for f in founders:
                    st.write(f"- {f}")
            else:
                st.caption("No founder bios found from public sources.")
            if founder_points:
                st.markdown("**Highlights**")
                for p in founder_points:
                    st.write(f"- {p}")
            if open_qs:
                st.markdown("**Open Questions**")
                for q in open_qs:
                    st.write(f"- {q}")

            def render_sources(sources, limit=8):
                links = []
                for s in (sources or [])[:limit]:
                    url, note = s.get("url",""), (s.get("note") or "")
                    if not url:
                        continue
                    dom = _domain(url) or "source"
                    label = note.strip() or dom
                    links.append(f"[{label}]({url})")
                if links:
                    st.markdown("**Sources:** " + " · ".join(links))
            render_sources(src)
        else:
            st.caption("LLM founder brief unavailable. See Signals tab for public sources.")

    # -------- Market Map tab --------
    with tabs[3]:
        st.subheader("Market Map")
        if data:
            mm  = data.get("market_map") or {}
            src = data.get("sources") or []

            axes            = (mm.get("axes") or [])[:3]
            competitors     = (mm.get("competitors") or [])[:6]
            differentiators = (mm.get("differentiators") or [])[:4]

            if not any([axes, competitors, differentiators]):
                st.caption("No clear market map from public sources.")
            else:
                if axes:
                    st.markdown("**Positioning Axes**"); st.write(", ".join(axes))
                if competitors:
                    st.markdown("**Competitors**")
                    for c in competitors: st.write(f"- {c}")
                if differentiators:
                    st.markdown("**Differentiators**")
                    for d in differentiators: st.write(f"- {d}")

            def render_sources(sources, limit=8):
                links = []
                for s in (sources or [])[:limit]:
                    url, note = s.get("url",""), (s.get("note") or "")
                    if not url:
                        continue
                    dom = _domain(url) or "source"
                    label = note.strip() or dom
                    links.append(f"[{label}]({url})")
                if links:
                    st.markdown("**Sources:** " + " · ".join(links))
            render_sources(src)
        else:
            st.caption("LLM market map unavailable. See Signals tab for public sources.")

    # -------- Market Size & Revenue tab --------
    with tabs[4]:
        st.subheader("Market Size (TAM)")
        if data:
            ms  = data.get("market_size") or ""
            rev = (data.get("estimated_revenue") or "").strip()
            mon = (data.get("monetization") or {}) or {}
            src = data.get("sources") or []

            st.write(ms or "Not found from public sources.")
            st.subheader("Estimated Revenue")
            st.write(rev or "Not found")
            st.subheader("Monetization")
            bm  = mon.get("business_model") or ""
            rvs = mon.get("revenue_streams") or []
            if bm:
                st.markdown("**Business model**"); st.write(bm)
            if rvs:
                st.markdown("**Revenue streams**")
                for item in rvs[:6]:
                    st.write(f"- {item}")

            def render_sources(sources, limit=8):
                links = []
                for s in (sources or [])[:limit]:
                    url, note = s.get("url",""), (s.get("note") or "")
                    if not url:
                        continue
                    dom = _domain(url) or "source"
                    label = note.strip() or dom
                    links.append(f"[{label}]({url})")
                if links:
                    st.markdown("**Sources:** " + " · ".join(links))
            render_sources(src)
        else:
            st.caption("LLM market size and revenue unavailable. See Signals tab for public sources.")

    # -------- Signals tab (always visible) --------
    with tabs[5]:
        st.subheader("Public Signals")
        render_section("Company Overview", overview_results, "No overview found.")
        render_section("Founding Team",    team_results,     "No team info found.")
        render_section("Market",           market_results,   "No market info found.")
        render_section("Competition",      competition_results, "No competition info found.")

        # Markdown snapshot export
        import datetime as dt
        def md_list(items):
            return "\n".join(
                f"- [{i.get('title','')}]({i.get('url','')}) - {i.get('snippet','')}"
                for i in (items or [])
            ) or "_No items_"
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

    # -------- JSON tab --------
    with tabs[6]:
        st.subheader("Raw JSON")
        if data:
            st.download_button(
                "Download JSON",
                json.dumps(data, indent=2),
                file_name=f"{name}_ddlite.json",
                use_container_width=True,
            )
            with st.expander("Show raw JSON"):
                st.code(json.dumps(data, indent=2), language="json")
        else:
            st.caption("No LLM output to show. Run with at least one AI section checked.")
