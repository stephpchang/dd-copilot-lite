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
st.set_page_config(page
