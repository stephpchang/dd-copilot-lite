import os
import requests
import streamlit as st
from openai import OpenAI

# Initialize OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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

# Helper: clean results
def dedupe_and_limit(results, max_items=3):
    seen = set()
    cleaned = []
    for r in results:
        if r["url"] not in seen:
            seen.add(r["url"])
            cleaned.append(r)
        if len(cleaned) >= max_items:
            break
    return cleaned

# Helper: render a section
def render_section(title, results, empty_message):
    st.subheader(title)
    if not results:
        st.write(empty_message)
    else:
        for item in results:
            st.write(f"[{item['title']}]({item['url']}) — {item['snippet']}")

# Helper: generate investor summary
def synthesize_snapshot(name, overview, team, market, competition):
    prompt = f"""
    You are an investor analyzing a startup.
    Summarize the following information into a concise, professional investment snapshot.

    Company: {name}

    Overview:
    {overview}

    Founding Team:
    {team}

    Market:
    {market}

    Competition:
    {competition}

    Output a single, tight paragraph highlighting the company's key strengths, risks, and opportunities.
    """
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
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
    if company.strip() == "":
        st.warning("Please enter a company name.")
    else:
        st.success(f"Profile for {company}")

        # Run searches & clean results
        overview_results = dedupe_and_limit(serp(f"{company} company overview", num=5))
        team_results = dedupe_and_limit(serp(f"{company} founding team", num=5))
        market_results = dedupe_and_limit(serp(f"{company} market size trends", num=5))
        competition_results = dedupe_and_limit(serp(f"{company} competitors", num=5))

        # Display results
        render_section("Company Overview", overview_results, "No overview found.")
        render_section("Founding Team", team_results, "No team info found.")
        render_section("Market", market_results, "No market info found.")
        render_section("Competition", competition_results, "No competition info found.")

        # Investor summary toggle
        generate_summary = st.checkbox("Generate Investor Summary", value=True)
        if generate_summary:
            st.subheader("Investor Summary")
            summary = synthesize_snapshot(
                company,
                overview_results,
                team_results,
                market_results,
                competition_results
            )
            st.write(summary)
