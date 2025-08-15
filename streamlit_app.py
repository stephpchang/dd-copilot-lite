# streamlit_app.py
import os, json, time, requests
import streamlit as st
from datetime import datetime
import openai  # for catching RateLimitError
from openai import OpenAI

# -------------------------
# Page config
# -------------------------
st.set_page_config(page_title="Due Diligence Co‑Pilot (Lite)", layout="wide")
st.title("Due Diligence Co‑Pilot (Lite)")
st.caption(f"OpenAI key loaded: {'yes' if os.getenv('OPENAI_API_KEY') else 'no'} • "
           f"Google CSE key loaded: {'yes' if os.getenv('GOOGLE_API_KEY') and os.getenv('GOOGLE_CSE_ID') else 'no'}")
st.info("First‑pass diligence profile in minutes: funding, investors, market context, competitors, and founder bios — with sources.")

# -------------------------
# Helpers: formatting & safe UI
# -------------------------
def money_fmt(n):
    try:
        if n is None: return "—"
        n = float(n)
        if n >= 1_000_000_000: return f"${n/1_000_000_000:.1f}B"
        return f"${n/1_000_000:.1f}M"
    except Exception:
        return "—"

def date_fmt(s):
    if not s: return "—"
    # Accept "YYYY-MM-DD", "YYYY-MM", "YYYY", or already printable
    try:
        parts = str(s).strip().split("-")
        if len(parts) == 3:
            dt = datetime.strptime(s[:10], "%Y-%m-%d")
            return dt.strftime("%b %Y")
        if len(parts) == 2:
            dt = datetime.strptime(s[:7], "%Y-%m")
            return dt.strftime("%b %Y")
        if len(parts) == 1 and len(parts[0]) == 4:
            return datetime.strptime(parts[0], "%Y").strftime("%Y")
    except Exception:
        pass
    return str(s)

def linkify(url, label="link"):
    if not url: return ""
    return f"[{label}]({url})"

def bullets_from_text(txt):
    """Render any multi-line text as bullets; fallback to a single line."""
    if not txt: 
        return ["Not publicly available."]
    lines = [ln.strip("-• ").strip() for ln in str(txt).splitlines() if ln.strip()]
    if not lines: 
        return ["Not publicly available."]
    return lines

# -------------------------
# Google search helper (cached)
# -------------------------
@st.cache_data(show_spinner=False, ttl=3600)
def serp(q, num=6):
    cx = os.getenv("GOOGLE_CSE_ID")
    key = os.getenv("GOOGLE_API_KEY")
    if not cx or not key:
        return []
    num = min(num, 10)
    try:
        resp = requests.get(
            "https://www.googleapis.com/customsearch/v1",
            params={"q": q, "cx": cx, "key": key, "num": num},
            timeout=15,
        )
        if resp.status_code != 200:
            return []
        items = (resp.json().get("items") or [])[:num]
        return [{"title": it.get("title",""), "snippet": it.get("snippet",""), "url": it.get("link","")} for it in items]
    except Exception:
        return []

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

def render_links_section(title, items, empty_hint):
    st.subheader(title)
    if not items:
        st.caption(empty_hint)
        return
    for it in items:
        ttl = it.get("title") or "(no title)"
        url = it.get("url") or ""
        snip = it.get("snippet") or ""
        if url:
            st.markdown(f"- [{ttl}]({url}) — {snip}")
        else:
            st.markdown(f"- {ttl} — {snip}")

# -------------------------
# OpenAI helpers (optional; rate-limit‑safe)
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
        return "(Set OPENAI_API_KEY to enable the investor summary.)"
    context = {
        "overview": _trim(overview_items),
        "team": _trim(team_items),
        "market": _trim(market_items),
        "competition": _trim(competition_items),
    }
    prompt = f"""
You are helping an early-stage VC. Using ONLY the JSON provided, write exactly 5 concise bullets for {company_name}.
Bullet format: start each bullet with "- " and keep to one line each.
Bullets:
1) What they do
2) Founders / leadership (if known)
3) Market context
4) Competitive positioning / alternatives
5) 1–2 open diligence questions

JSON context:
{json.dumps(context, ensure_ascii=False)}
"""
    client = _openai_client()
    for _ in range(2):
        try:
            resp = client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL","gpt-4o-mini"),
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
    """Return a safe dict with founders, bios, and sources when possible."""
    if not os.getenv("OPENAI_API_KEY"):
        return {"founders": [], "bios": [], "sources": [], "note": "Set OPENAI_API_KEY for Founder Brief."}
    ctx = {"team": _trim(team_items, max_items=4)}
    prompt = f"""
From these search snippets about the team of {company_name}, extract concise JSON with founders and 1-line bios.
Respond with ONLY valid JSON in this shape:
{{
  "founders":[{{"name": str, "bio": str|null, "source": str|null}}]
}}
Use only what appears in the snippets. If unknown, omit the field.

Snippets JSON:
{json.dumps(ctx, ensure_ascii=False)}
"""
    client = _openai_client()
    for _ in range(2):
        try:
            resp = client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL","gpt-4o-mini"),
                messages=[{"role":"user","content":prompt}],
                temperature=0,
            )
            txt = resp.choices[0].message.content.strip().strip("`")
            try:
                data = json.loads(txt)
                f = data.get("founders") or []
                # Normalize to safe rows
                founders = []
                for it in f:
                    founders.append({
                        "name": (it.get("name") or "").strip() or "Unknown",
                        "bio": (it.get("bio") or "").strip(),
                        "source": it.get("source") or "",
                    })
                return {"founders": founders}
            except Exception:
                return {"founders": [], "note": txt[:300]}
        except openai.RateLimitError:
            time.sleep(1.5)
        except Exception as e:
            return {"founders": [], "note": f"Unavailable: {e}"}
    return {"founders": [], "note": "Rate limited. Try again shortly."}

@st.cache_data(show_spinner=False)
def market_outline(company_name, market_items):
    """Return TAM/revenue estimates when possible, with sources."""
    if not os.getenv("OPENAI_API_KEY"):
        return {"tam": None, "revenue": None, "sources": [], "note": "Set OPENAI_API_KEY for Market size."}
    ctx = {"market": _trim(market_items, max_items=6)}
    prompt = f"""
From these market snippets about {company_name}, extract concise JSON:
{{
  "tam": {{"value": number|null, "unit": "USD", "year": int|null, "source": str|null}},
  "revenue_estimate": {{"value": number|null, "unit": "USD", "year": int|null, "source": str|null}}
}}
Use ONLY what appears in the snippets; if unknown set fields to null. Return JSON only.
Snippets:
{json.dumps(ctx, ensure_ascii=False)}
"""
    client = _openai_client()
    for _ in range(2):
        try:
            resp = client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL","gpt-4o-mini"),
                messages=[{"role":"user","content":prompt}],
                temperature=0,
            )
            txt = resp.choices[0].message.content.strip().strip("`")
            try:
                data = json.loads(txt)
                return {
                    "tam": data.get("tam"),
                    "revenue_estimate": data.get("revenue_estimate"),
                }
            except Exception:
                return {"tam": None, "revenue_estimate": None, "note": txt[:300]}
        except openai.RateLimitError:
            time.sleep(1.5)
        except Exception as e:
            return {"tam": None, "revenue_estimate": None, "note": f"Unavailable: {e}"}
    return {"tam": None, "revenue_estimate": None, "note": "Rate limited. Try again shortly."}

# -------------------------
# Inputs
# -------------------------
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

    gen_summary_input    = st.checkbox("Generate Investor Summary (OpenAI)", value=st.session_state.gen_summary)
    gen_founder_input    = st.checkbox("Generate Founder Brief (OpenAI)", value=st.session_state.gen_founder_brief)
    gen_marketmap_input  = st.checkbox("Generate Market Size Snapshot (OpenAI)", value=st.session_state.gen_market_map)

    submitted = st.form_submit_button("Run")

if submitted:
    st.session_state.company = (company_input or "").strip()
    st.session_state.gen_summary = gen_summary_input
    st.session_state.gen_founder_brief = gen_founder_input
    st.session_state.gen_market_map = gen_marketmap_input

name = st.session_state.company
gen_summary = st.session_state.gen_summary
gen_founder = st.session_state.gen_founder_brief
gen_market = st.session_state.gen_market_map

if submitted and not name:
    st.warning("Please enter a company name.")

# -------------------------
# Search + sections
# -------------------------
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

    # Investor Summary (bulleted)
    if gen_summary:
        st.subheader("Investor Summary")
        raw = synthesize_snapshot(name, overview_results, team_results, market_results, competition_results)
        for b in bullets_from_text(raw):
            st.markdown(f"- {b}")

    # Founder Brief (names + one-liners + sources)
    if gen_founder:
        st.subheader("Founder Brief")
        fb = founder_brief(name, team_results) or {}
        founders = fb.get("founders") or []
        if not founders:
            st.caption("Not publicly available.")
        else:
            for f in founders:
                nm = f.get("name") or "Unknown"
                bio = f.get("bio") or ""
                src = f.get("source") or ""
                line = f"**{nm}** — {bio}".strip(" —")
                if src:
                    line += f" {linkify(src,'source')}"
                st.markdown(f"- {line}")

    # Market Size Snapshot (TAM / Revenue)
    if gen_market:
        st.subheader("Market Snapshot")
        m = market_outline(name, market_results) or {}
        tam = m.get("tam")
        rev = m.get("revenue_estimate")
        if not tam and not rev:
            st.caption("No reliable public estimate available.")
        else:
            if tam:
                st.markdown(f"- **TAM:** {money_fmt(tam.get('value'))} ({tam.get('year') or '—'}) "
                            + (linkify(tam.get('source'), 'source') if tam.get('source') else ""))
            if rev:
                st.markdown(f"- **Revenue (est.):** {money_fmt(rev.get('value'))} ({rev.get('year') or '—'}) "
                            + (linkify(rev.get('source'), 'source') if rev.get('source') else ""))

    # Always show raw link sections (with helpful empty states)
    render_links_section("Company Overview", overview_results, 
                         "Not found. Try pasting the official site or add 'about'.")
    render_links_section("Founding Team", team_results, 
                         "Not found. Try searching '<company> founders' or 'team'.")
    render_links_section("Market Context", market_results, 
                         "Not found. Try 'market size', 'TAM', or a well-known analyst firm.")
    render_links_section("Competition", competition_results, 
                         "Not found. Try '<company> alternatives' or 'competitors'.")

    # Markdown export (snapshot)
    import datetime as dt
    def md_list(items):
        if not items: return "_No items_"
        return "\n".join([f"- [{i['title']}]({i['url']}) — {i['snippet']}" for i in items])

    md = f"""# {name} — First‑Pass Diligence
_Last updated: {dt.datetime.now().strftime('%Y-%m-%d %H:%M')}_

## Investor Summary
{os.linesep.join(['- ' + b for b in bullets_from_text(raw) ]) if gen_summary else '_Not generated_'}

## Founder Brief
{os.linesep.join(['- ' + ((f.get('name') or 'Unknown') + (' — ' + (f.get('bio') or '') if f.get('bio') else '')) for f in (fb.get('founders') or [])]) if gen_founder else '_Not generated_'}

## Market Snapshot
{('- TAM: ' + money_fmt(tam.get('value')) if gen_market and tam else '')}
{('- Revenue (est.): ' + money_fmt(rev.get('value')) if gen_market and rev else '')}

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
