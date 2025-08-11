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

# Helper to deduplicate results and optionally prefer certain sources
def tidy(results, prefer=()):
    """Deduplicate, optionally prefer certain domains, and limit to top 3."""
    seen, cleaned = set(), []
    for item in results:
        if item["url"] in seen:
            continue
        seen.add(item["url"])
        cleaned.append(item)
    if prefer:
        cleaned.sort(key=lambda x: any(p in x["url"] for p in prefer), reverse=True)
    return cleaned[:3]

# Helper to display section results cleanly
def render_section(title, items, empty_hint):
    st.subheader(title)
    if not items:
        st.write(empty_hint)
    else:
        for item in items:
            st.write(f"[{item['title']}]({item['url']}) — {item['snippet']}")

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
        overview_results = tidy(serp(f"{company} company overview", num=5), prefer=("crunchbase.com", "linkedin.com"))
        team_results = tidy(serp(f"{company} founding team", num=5), prefer=("linkedin.com",))
        market_results = tidy(serp(f"{company} market size trends", num=5))
        competition_results = tidy(serp(f"{company} competitors", num=5))

        # Display results
        render_section("Company Overview", overview_results, "No overview found.")
        render_section("Founding Team", team_results, "No team info found.")
        render_section("Market", market_results, "No market info found.")
        render_section("Competition", competition_results, "No competition info found.")
