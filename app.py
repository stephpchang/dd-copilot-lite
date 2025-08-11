import os
import requests
import streamlit as st

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

# Helper: deduplicate, optionally prefer certain domains, limit to top 3
def tidy(results, prefer=()):
    """Deduplicate, optionally prefer certain domains, and limit to top 3."""
    seen = set()
    out = []
    for r in results:
        key = (r.get("title", "").strip().lower(), r.get("url", ""))
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    if prefer:
        out.sort(key=lambda x: 0 if any(p in (x.get("url") or "") for p in prefer) else 1)
    return out[:3]

# Helper: render a section or show fallback text
def render_section(title, items, empty_hint):
    st.subheader(title)
    if items:
        for it in items:
            st.write(f"[{it['title']}]({it['url']}) — {it['snippet']}")
    else:
        st.caption(empty_hint)

# Streamlit app setup
st.set_page_config(page_title="Due Diligence Co-Pilot (Lite)")
st.title("Due Diligence Co-Pilot (Lite)")
st.write("Provides profiles of a company’s team, market, and competition to accelerate early-stage investment assessments.")

# Input
company = st.text_input("Enter company name or website")

# Run
if st.button("Run"):
    if company.strip() == "":
        st.warning("Please enter a company name.")
    else:
        st.success(f"Profile for {company}")

        # Search queries
        overview_results = tidy(serp(f"{company} company overview", num=5), prefer=("wikipedia.org", "crunchbase.com"))
        team_results = tidy(serp(f"{company} founding team", num=5), prefer=("linkedin.com", "crunchbase.com"))
        market_results = tidy(serp(f"{company} market size trends", num=5))
        competition_results = tidy(serp(f"{company} competitors", num=5))

        # Display results
        render_section("Company Overview", overview_results, "No overview found.")
        render_section("Founding Team", team_results, "No team info found.")
        render_section("Market", market_results, "No market info found.")
        render_section("Competition", competition_results, "No competitors found.")
