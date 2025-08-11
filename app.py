import os
import requests
import streamlit as st
from openai import OpenAI

# Google search helper
def serp(q, num=6):
    cx = os.getenv("GOOGLE_CSE_ID")
    key = os.getenv("GOOGLE_API_KEY")
    if not cx or not key:
        return []
    num = min(num, 10)
    r = requests.get(
        "https://www.googleapis.com/customsearch/v1",
        params={"q": q, "cx": cx, "key": key, "num": num},
        timeout=15
    ).json()
    hits = []
    for it in r.get("items", [])[:num]:
        hits.append({
            "title": it.get("title", ""),
            "snippet": it.get("snippet", ""),
            "url": it.get("link", "")
        })
    return hits

# Helper to deduplicate results and optionally prefer certain sources
def tidy(results, prefer=()):
    """Deduplicate, optionally prefer certain domains, and limit to top 3."""
    seen, cleaned = set(), []
    for item in results:
        url = item.get("url", "")
        if not url or url in seen:
            continue
        seen.add(url)
        cleaned.append(item)
    if prefer:
        cleaned.sort(key=lambda x: any(p in x["url"] for p in prefer), reverse=True)
    return cleaned[:3]

# Helper to display section results cleanly
def render_section(title, items, empty_hint):
    st.subheader(title)
    if not items:
        st.caption(empty_hint)
    else:
        for item in items:
            st.write(f"[{item['title']}]({item['url']}) — {item['snippet']}")

# OpenAI investor summary
def synthesize_snapshot(company_name, overview_items, team_items, market_items, competition_items):
    """Return a 5-bullet investor summary from the search snippets."""
    if not os.getenv("OPENAI_API_KEY"):
        return "Set OPENAI_API_KEY to enable the investor summary."
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    context = {
        "overview": overview_items,
        "team": team_items,
        "market": market_items,
        "competition": competition_items
    }
    prompt = f"""
You are helping an early-stage VC. Using ONLY the JSON provided, write exactly 5 concise bullets for {company_name}:
- What they do (one line)
- Founders / leadership (if known)
- Market context
- Competitive positioning / key alternatives
- 1–2 open diligence questions

JSON context:
{context}
"""
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role":"user","content":prompt}],
        temperature=0.2
    )
    return resp.choices[0].message.content.strip()

# Streamlit app setup
st.set_page_config(page_title="Due Diligence Co-Pilot (Lite)")
st.title("Due Diligence Co-Pilot (Lite)")
st.write("Provides profiles of a company’s team, market, and competition to accelerate early-stage investment assessments.")

# Input
company = st.text_input("Enter company name or website")

# Run
if st.button("Run"):
    name = company.strip()
    if not name:
        st.warning("Please enter a company name.")
    else:
        st.success(f"Profile for {name}")

        # Smarter queries + preferred sources
        overview_results    = tidy(
            serp(f"{name} official site", 8),
            prefer=("about", "wikipedia.org", "crunchbase.com", "linkedin.com")
        )
        team_results        = tidy(
            serp(f"{name} founders team leadership", 8),
            prefer=("about", "team", "wikipedia.org", "linkedin.com", "crunchbase.com")
        )
        market_results      = tidy(
            serp(f"{name} target market TAM customers industry", 8),
            prefer=("gartner.com", "forrester.com", "mckinsey.com", "bain.com")
        )
        competition_results = tidy(
            serp(f"{name} competitors alternatives comparative", 8),
            prefer=("g2.com", "capterra.com", "crunchbase.com", "wikipedia.org")
        )

        # Investor Summary
        st.subheader("Investor Summary")
        summary = synthesize_snapshot(name, overview_results, team_results, market_results, competition_results)
        st.write(summary)

        # Sections
        render_section("Company Overview", overview_results, "No overview found. Try pasting the official site.")
        render_section("Founding Team",    team_results,     "No team info found. Try 'founders' or 'team'.")
        render_section("Market",           market_results,   "No market info found. Try 'market size' or 'TAM'.")
        render_section("Competition",      competition_results, "No competition info found. Try 'alternatives'.")
