import os
import json
import requests
import streamlit as st
from app.llm_guard import generate_once

# ---- JSON schema for single-call output (OpenAI json_schema requires "required" to list all properties) ----
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
        "required": ["investor_summary", "founder_brief", "market_map", "sources"]
    }
}

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
    resp = requests.get(
        "https://www.googleapis.com/customsearch/v1",
        params={"q": q, "cx": cx, "key": key, "num": num},
        timeout=15,
    )
    if resp.status_code != 200:
        return [{
            "title": "Search error",
            "snippet": f"HTTP {resp.status_code}: {resp.text[:120]}...",
            "url": ""
        }]
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
        ttl = it.get("title") or "(no title)"
        url = it.get("url") or ""
        snip = it.get("snippet") or ""
        if url:
            st.write(f"[{ttl}]({url}) — {snip}")
        else:
            st.write(f"{ttl} — {snip}")

# -------------------------
# Streamlit app
# -------------------------
st.set_page_config(page_title="Due Diligence Co-Pilot (Lite)")
st.title("Due Diligence Co-Pilot (Lite)")
st.caption(f"OpenAI key loaded: {'yes' if os.getenv('OPENAI_API_KEY') else 'no'}")
st.caption("Build: v0.2.2-pretty-summaries")

# Persist inputs
for key, default in [
    ("company", ""),
    ("gen_summary", True),         # default ON since summaries look nice now
    ("gen_founder_brief", True),   # default ON
    ("gen_market_map", True),      # default ON
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

    # Gather web signals (no AI)
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

    # Build a concise list of source URLs from the signals to anchor the model
    sources_list = []
    for coll in (overview_results, team_results, market_results, competition_results):
        for it in coll:
            if it.get("url"):
                sources_list.append(it["url"])
    sources_list = list(dict.fromkeys(sources_list))[:10]

    # Single guarded OpenAI call (only if any AI section is requested)
    data = None
    if gen_summary or gen_founder or gen_mmap:
        if not os.getenv("OPENAI_API_KEY"):
            st.info("Set OPENAI_API_KEY in Streamlit Secrets to enable AI sections.")
        else:
            st.session_state._busy = True
            try:
                # --- Prompt tweak: investor_summary must be newline-bulleted (no numbers) ---
                prompt = f"""
Return ONE JSON object that matches the provided schema.
Company: {name}
Website: null
User-provided sources: {sources_list}

Rules:
- Only use fields defined in the schema.
- For investor_summary, return 3–7 bullets as plain text, each starting with "- " on a NEW LINE (no numbering).
  Example:
  - First concise point
  - Second concise point
  - Third concise point
- If unknown, set null or [].
- Keep answers concise and factual. Do not invent specifics.
                """.strip()

                with st.spinner("Generating structured brief..."):
                    data = generate_once(prompt, JSON_SCHEMA)

            except Exception as e:
                st.error("There was a problem generating the brief. Please try again.")
                st.exception(e)
            finally:
                st.session_state._busy = False

    # -------- Pretty summaries (with Raw JSON tucked away) --------
    if data:
        inv = (data.get("investor_summary") or "").strip()
        fb  = data.get("founder_brief") or {}
        mm  = data.get("market_map") or {}

        # Investor Summary as bullets
        st.subheader("Investor Summary")
        if inv:
            # Prefer newline bullets ("- "), fall back to sentence split
            lines = [ln.strip() for ln in inv.replace("\r", "").split("\n") if ln.strip()]
            if not lines:
                lines = [b.strip() for b in inv.split(". ") if b.strip()]
            # Normalize bullets
            bullets = []
            for b in lines:
                b = b.lstrip("•- ").strip()
                if not b.endswith("."):
                    b += "."
                bullets.append(b)
            for b in bullets[:7]:
                st.write(f"- {b}")
        else:
            st.caption("No summary available.")

        # Founder Brief (compact)
        st.subheader("Founder Brief")
        founders        = (fb.get("founders") or [])[:3]
        founder_points  = (fb.get("highlights") or [])[:5]
        open_qs         = (fb.get("open_questions") or [])[:5]

        if founders:
            st.markdown("**Founders**")
            st.write(", ".join(founders))
        if founder_points:
            st.markdown("**Highlights**")
            for p in founder_points:
                st.write(f"- {p}")
        if open_qs:
            st.markdown("**Open Questions**")
            for q in open_qs:
                st.write(f"- {q}")

        # Market Map (compact)
        st.subheader("Market Map")
        axes            = (mm.get("axes") or [])[:3]
        competitors     = (mm.get("competitors") or [])[:6]
        differentiators = (mm.get("differentiators") or [])[:4]

        if axes:
            st.markdown("**Positioning Axes**")
            st.write(", ".join(axes))
        if competitors:
            st.markdown("**Competitors**")
            for c in competitors:
                st.write(f"- {c}")
        if differentiators:
            st.markdown("**Differentiators**")
            for d in differentiators:
                st.write(f"- {d}")

        # Export + Raw JSON tucked away
        st.download_button(
            "Download JSON",
            json.dumps(data, indent=2),
            file_name=f"{name}_ddlite.json",
            use_container_width=True,
        )
        with st.expander("Show raw JSON"):
            st.code(json.dumps(data, indent=2), language="json")

    # Always show the raw web signal sections
    render_section("Company Overview", overview_results, "No overview found. Try pasting the official site.")
    render_section("Founding Team",    team_results,     "No team info found. Try 'founders' or 'team'.")
    render_section("Market",           market_results,   "No market info found. Try 'market size' or 'TAM'.")
    render_section("Competition",      competition_results, "No competition info found. Try 'alternatives'.")

    # -------------------------
    # Markdown export (no AI required)
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
