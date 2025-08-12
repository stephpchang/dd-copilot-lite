# app/public_provider.py
import requests
import streamlit as st

WIKI_TITLE_SEARCH = "https://en.wikipedia.org/w/rest.php/v1/search/title"
WIKI_PAGE_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary"

def _pick_best_page(results: dict) -> dict | None:
    pages = (results or {}).get("pages") or []
    if not pages:
        return None
    # prefer exact/startswith-ish matches
    def score(p):
        t = (p.get("title") or "").strip().lower()
        return (t,).__len__()  # dummy, keep list order; API already returns relevance
    return pages[0]

@st.cache_data(ttl=3600, show_spinner=False)
def wiki_enrich(organization_name: str) -> dict | None:
    """
    Public-data enrichment via Wikipedia REST (no API key).
    Returns: {"title", "url", "summary"} or None.
    """
    q = (organization_name or "").strip()
    if not q:
        return None
    try:
        # 1) search
        r = requests.get(WIKI_TITLE_SEARCH, params={"q": q, "limit": 3}, timeout=15)
        if r.status_code != 200:
            return None
        best = _pick_best_page(r.json())
        if not best:
            return None
        title = best.get("title")
        # 2) summary
        s = requests.get(f"{WIKI_PAGE_SUMMARY}/{title}", timeout=15)
        if s.status_code != 200:
            return None
        js = s.json()
        url = (js.get("content_urls") or {}).get("desktop", {}).get("page") or ""
        summary = js.get("extract") or ""
        return {"title": title, "url": url, "summary": summary}
    except Exception:
        return None
