import os
import json
import time
import requests
import streamlit as st
import openai  # for catching RateLimitError
from openai import OpenAI

# -------------------------
# Google search helper
# -------------------------
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
# OpenAI: Investor Summary (cached + safe)
# -------------------------
@st.cache_data(show_spinner=False)
def synthesize_snapshot(company_name, overview_items, team_items, market_items, competition_items):
    if not os.getenv("OPENAI_API_KEY"):
        return "Set OPENAI_API_KEY to enable the investor summary."

    def _trim(items, max_items=3, max_snip=220):
        out = []
        for it in (items or [])[:max_items]:
            out.append({
                "title": (it.get("title") or "")[:100],
                "url": it.get("url") or "",
                "snippet": (it.get("snippet") or "")[:max_snip],
            })
        return out

    context = {
        "overview": _trim(overview_items),
        "team": _trim(team_items),
        "market": _trim(market_items),
        "competition": _trim(competition_items),
    }

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
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

    for _ in range(2):  # 2 tries
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

# -------------------------
# Streamlit app
# -------------------------
st.set_page_config(page_title="Due Diligence Co-Pilot (Lite)")
st.title("Due Diligence Co-Pilot (Lite)")
st.caption(f"OpenAI key loaded: {'yes' if os.getenv('OPENAI_API_KEY') else 'no'}")
st.write("Provides profiles of a company’s team, market, and competition to accelerate early-stage investment assessments.")

# Persistent defaults
if "company" not in st.session_state:
    st.session_state.company = ""
if "gen_summary" not in st.session_state:
    st.session_state.gen_summary = False

# Use a form so widgets don't rerun the whole app on each change
with st.form("search_form", clear_on_submit=False):
    company_input = st.text_input("Enter company name or website", value=st.session_state.company)
    gen_summary_input = st.checkbox("Generate Investor Summary (OpenAI)", value=st.session_state.gen_summary)
    submitted = st.form_submit_button("Run")

# Only update state when the form is submitted
if submitted:
    st.session_state.company = company_input.strip()
    st.session_state.gen_summary = gen_summary_input

# Use the persisted values
name = st.session_state.company
gen_summary = st.session_state.gen_summary

if submitted and not name:
    st.warning("Please enter a company name.")

if submitted and name:
    st.success(f"Profile for {name}")

    # Searches (smarter queries + preferred domains)
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

    # Optional summary (now stable; no spiral)
    if gen_summary:
        st.subheader("Investor Summary")
        summary = synthesize_snapshot(name, overview_results, team_results, market_results, competition_results)
        st.write(summary)
    else:
        st.caption("Tip: check the box in the form to generate a 5-bullet Investor Summary.")

    # Sections
    render_section("Company Overview", overview_results, "No overview found. Try pasting the official site.")
    render_section("Founding Team",    team_results,     "No team info found. Try 'founders' or 'team'.")
    render_section("Market",           market_results,   "No market info found. Try 'market size' or 'TAM'.")
    render_section("Competition",      competition_results, "No competition info found. Try 'alternatives'.")
