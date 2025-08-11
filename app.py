import os
import json
import time
import requests
import streamlit as st
import openai  # for catching RateLimitError
from openai import OpenAI

# -------------------------
# Google search helper (now cached)
# -------------------------
@st.cache_data(show_spinner=False, ttl=3600)
def serp(q, num=6):
    cx = os.getenv("GOOGLE_CSE_ID")
    key = os.getenv("GOOGLE_API_KEY")
    if not cx or not key:
        return []
    num = min(num, 10)
    resp = requests.get(
        "https://www.googleapis.com/customsearch/v1",
        params={"q": q, "cx": cx, "key": key, "num": num},
        timeout=15,
    )
    if resp.status_code != 200:
        return [{"title": "Search error",
                 "snippet": f"HTTP {resp.status_code}: {resp.text[:120]}...",
                 "url": ""}]
    items = (resp.json().get("items") or [])[:num]
    return [{"title": it.get("title",""), "snippet": it.get("snippet",""), "url": it.get("link","")} for it in items]

# -------------------------
# Result cleanup + rendering
# -------------------------
def tidy(results, prefer=(), limit=3):
    """Deduplicate by URL, optionally prefer domains, return top N."""
    seen, cleaned = set(), []
    for r in results or []:
        url = r.get("url") or ""
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
        title = it.get("title") or "(no title)"
        url = it.get("url") or ""
        snip = it.get("snippet") or ""
        if url:
            st.write(f"[{title}]({url}) — {snip}")
        else:
            st.write(f"{title} — {snip}")

# -------------------------
# OpenAI helpers (still optional; ignore if rate-limited)
# -------------------------
def _openai_client():
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def _trim(items, max_items=3, max_snip=220):
    out = []
    for it in (items or [])[:max_items]:
        out.append({
            "title": (it.get("title") or "")[:100],
            "url": it.get("url") or "",
            "snippet": (it.get("snippet") or "")[:max_snip],
        })
    return out

@st.cache_data(show_spinner=False)
def synthesize_snapshot(company_name, overview_items, team_items, market_items, competition_items):
    if not os.getenv("OPENAI_API_KEY"):
        return "Set OPENAI_API_KEY to enable the investor summary."
    context = {
        "overview": _trim(overview_items),
        "team": _trim(team_items),
        "market": _trim(market_items),
        "competition": _trim(competition_items),
    }
    prompt = f"""
You are helping an early-stage VC. Using ONLY the JSON provided, write exactly 5 concise bullets for {company_name}:
- What they do (one line)
- Founders / leadership (if known)
- Market context
- Competitive positioning / key alternatives
- 1–2 open diligence questions

JSON context:
{json.dumps(context, ensure_ascii=False)}
"""
    client = _openai_client()
    for _ in range(2):
        try:
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
            )
            return resp.choices[0].message.content.strip()
        except openai.RateLimitError:
            time.sleep(1.5)
        except Exception as e:
            return f"(Investor Summary unavailable: {e})"
    return "(Investor Summary temporarily unavailable due to rate limits. Try again shortly.)"

@st.cache_data(show_spinner=False)
def founder_brief(company_name, team_items):
    if not os.getenv("OPENAI_API_KEY"):
        return {"founders": [], "sources": [], "note": "Set OPENAI_API_KEY for Founder Brief."}
    ctx = {"team": _trim(team_items, max_items=4)}
    prompt = f"""
From these search snippets about the team of {company_name}, extract concise JSON:
{{
  "founders":[
    {{"name": str, "role": str|null, "highlights": [str]}}
  ],
  "sources":[str]
}}
Only include what is supported by the snippets. If unknown, omit the field.

Snippets JSON:
{json.dumps(ctx, ensure_ascii=False)}
"""
    client = _openai_client()
    for _ in range(2):
        try:
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role":"user","content":prompt}],
                temperature=0,
            )
            txt = resp.choices[0].message.content.strip().strip("`")
            try:
                return json.loads(txt)
            except Exception:
                return {"founders": [], "sources": [], "note": txt[:500]}
        except openai.RateLimitError:
            time.sleep(1.5)
        except Exception as e:
            return {"founders": [], "sources": [], "note": f"Unavailable: {e}"}
    return {"founders": [], "sources": [], "note": "Rate limited. Try again shortly."}

@st.cache_data(show_spinner=False)
def market_map(company_name, competition_items):
    if not os.getenv("OPENAI_API_KEY"):
        return {"axes": [], "competitors": [], "sources": [], "note": "Set OPENAI_API_KEY for Market Map."}
    ctx = {"competition": _trim(competition_items, max_items=6)}
    prompt = f"""
From these competitor-related snippets for {company_name}, produce concise JSON:
{{
  "axes": [str],
  "competitors": [
    {{"name": str, "why_similar": str, "url": str|null}}
  ],
  "sources":[str]
}}
Keep it brief (3–6 competitors). Use only what appears in the snippets.

Snippets JSON:
{json.dumps(ctx, ensure_ascii=False)}
"""
    client = _openai_client()
    for _ in range(2):
        try:
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role":"user","content":prompt}],
                temperature=0,
            )
            txt = resp.choices[0].message.content.strip().strip("`")
            try:
                return json.loads(txt)
            except Exception:
                return {"axes": [], "competitors": [], "sources": [], "note": txt[:500]}
        except openai.RateLimitError:
            time.sleep(1.5)
        except Exception as e:
            return {"axes": [], "competitors": [], "sources": [], "note": f"Unavailable: {e}"}
    return {"axes": [], "competitors": [], "sources": [], "note": "Rate limited. Try again shortly."}

# -------------------------
# Streamlit app
# -------------------------
st.set_page_config(page_title="Due Diligence Co-Pilot (Lite)")
st.title("Due Diligence Co-Pilot (Lite)")
st.caption(f"OpenAI key loaded: {'yes' if os.getenv('OPENAI_API_KEY') else 'no'}")
st.write("Provides profiles of a company’s team, market, and competition to accelerate early-stage investment assessments.")

# Persist inputs
if "company" not in st.session_state:
    st.session_state.company = ""
if "gen_summary" not in st.session_state:
    st.session_state.gen_summary = False
if "gen_founder_brief" not in st.session_state:
    st.session_state.gen_founder_brief = False
if "gen_market_map" not in st.session_state:
    st.session_state.gen_market_map = False

examples = ["", "Anthropic", "Plaid", "RunwayML", "Ramp", "Figma"]

with st.form("search_form", clear_on_submit=False):
    company_input = st.text_input("Enter company name or website", value=st.session_state.company)
    example = st.selectbox("Or pick an example", examples, index=0)
    if example:
        company_input = example

    # Keep AI toggles (you can ignore if rate-limited)
    gen_summary_input    = st.checkbox("Generate Investor Summary (OpenAI)", value=st.session_state.gen_summary)
    gen_founder_input    = st.checkbox("Generate Founder Brief (OpenAI)", value=st.session_state.gen_founder_brief)
    gen_marketmap_input  = st.checkbox("Generate Market Map (OpenAI)", value=st.session_state.gen_market_map)

    submitted = st.form_submit_button("Run")

# Update state only on submit
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

    # (Optional) AI sections — will show rate-limit messages if quota hit
    if gen_summary:
        st.subheader("Investor Summary")
        st.write(synthesize_snapshot(name, overview_results, team_results, market_results, competition_results))

    if gen_founder:
        st.subheader("Founder Brief")
        st.json(founder_brief(name, team_results))

    if gen_mmap:
        st.subheader("Market Map")
        st.json(market_map(name, competition_results))

    # Always show the raw sections
    render_section("Company Overview", overview_results, "No overview found. Try pasting the official site.")
    render_section("Founding Team",    team_results,     "No team info found. Try 'founders' or 'team'.")
    render_section("Market",           market_results,   "No market info found. Try 'market size' or 'TAM'.")
    render_section("Competition",      competition_results, "No competition info found. Try 'alternatives'.")

    # -------------------------
    # NEW: Markdown export (no AI required)
    # -------------------------
    import datetime as dt
    def md_list(items):
        return "\n".join([f"- [{i['title']}]({i['url']}) — {i['snippet']}" for i in items]) or "_No items_"

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
    st.download_button("Download snapshot (Markdown)", md, file_name=f"{name}_snapshot.md")
