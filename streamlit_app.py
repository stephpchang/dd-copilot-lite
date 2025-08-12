import os
import json
import requests
import streamlit as st

from app.llm_guard import generate_once
from app.public_provider import wiki_enrich          # public enrichment (no keys)
from app.funding_lookup import get_funding_data      # funding + investors (public/search-based)

# ---- JSON schema for single-call output ----
# NOTE: For OpenAI json_schema, any object with "properties" must have "required" listing ALL those props.
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
            "market_size": {
                "type": "string",
                "description": "TAM in USD + region + source + year (plain text). If unknown: 'Not found from public sources.'"
            },
            "estimated_revenue": {
                "type": "string",
                "description": "Latest public estimate or guidance in USD with year/source if possible; else 'Not found'."
            },
            "monetization": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "business_model": {"type": "string"},  # e.g., SaaS subscription, usage-based, ads, marketplace take-rate
                    "revenue_streams": {"type": "array", "items": {"type": "string"}}  # e.g., 'Enterprise SaaS', 'API usage fees'
                },
                "required": ["business_model", "revenue_streams"]
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
        "required": [
            "investor_summary",
            "founder_brief",
            "market_map",
            "market_size",
            "estimated_revenue",
            "monetization",
            "sources"
        ]
    }
}

# -------------------------
# Google Custom Search helper (cached)
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
st.caption("Build: v0.4.0-market-revenue-monetization")

# Persist inputs
for key, default in [
    ("company", ""),
    ("gen_summary", True),
    ("gen_founder_brief", True),
    ("gen_market_map", True),
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

    # Gather web signals (no keys required)
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

    # Public-data enrichment (Wikipedia)
    wiki = wiki_enrich(name)  # {"title","url","summary"} or None

    # ---- Funding & Investors (public/search-based) ----
    funding = get_funding_data(name, serp_func=lambda q, num=6: serp(q, num))

    st.subheader("Funding & Investors")
    rounds = funding.get("rounds") or []
    investors = funding.get("investors") or []

    if rounds:
        rows = []
        for r in rounds[:6]:  # keep compact
            rows.append({
                "Round": r.get("round") or "",
                "Date": r.get("date") or "",
                "Amount": "${:,}".format(r["amount_usd"]) if r.get("amount_usd") else "",
                "Lead": ", ".join(r.get("lead_investors") or []),
            })
        st.table(rows)
    else:
        st.caption("No funding data found yet (public sources).")

    if investors:
        st.markdown("**Notable investors**")
        st.write(", ".join(investors[:10]))

    # Build a concise list of source URLs from signals + funding to anchor the model
    sources_list = []
    for coll in (overview_results, team_results, market_results, competition_results):
        for it in coll:
            if it.get("url"):
                sources_list.append(it["url"])
    # add wiki + funding sources
    if wiki and wiki.get("url"):
        sources_list.insert(0, wiki["url"])
    for s in (funding.get("sources") or []):
        if s:
            sources_list.append(s)
    sources_list = list(dict.fromkeys(sources_list))[:10]  # de-dup & trim

    # Single guarded OpenAI call (only if any AI section is requested)
    data = None
    if gen_summary or gen_founder or gen_mmap:
        if not os.getenv("OPENAI_API_KEY"):
            st.info("Set OPENAI_API_KEY in Streamlit Secrets to enable AI sections.")
        else:
            st.session_state._busy = True
            try:
                # include short background from Wikipedia if available
                wiki_hint = (wiki.get("summary")[:600] if wiki and wiki.get("summary") else "").strip()

                prompt = f"""
Return ONE JSON object that matches the provided schema.
Company: {name}
Website: null
User-provided sources: {sources_list}

Background (optional, from Wikipedia):
{wiki_hint}

Instructions:
- Only use fields defined in the schema and keep them concise.
- For investor_summary: return 3–7 bullets as plain text, each starting with "- " on a NEW LINE (no numbering).
- For founder_brief: concise lists only; omit anything not supported by public references.
- For market_map: keep to 1–2 axes, 3–5 competitors, and 2–4 differentiators.
- For market_size: give the most recent credible TAM figure with USD amount, region (global/region), source name, and year.
  If not found, return "Not found from public sources."
- For estimated_revenue: return the most recent public revenue/gross bookings/ARR estimate in USD (state metric),
  with year and source; if not found, return "Not found".
- For monetization:
  - business_model: 1–2 lines (e.g., "SaaS subscription with usage-based pricing").
  - revenue_streams: 2–5 concise bullets (e.g., "Enterprise SaaS", "API usage fees", "Professional services").
- For sources: include up to 10 URLs with a short note; notes can be empty strings.

Return ONLY the JSON object; no markdown, no commentary.
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
        ms  = (data.get("market_size") or "").strip()
        rev = (data.get("estimated_revenue") or "").strip()
        mon = (data.get("monetization") or {}) or {}

        # Investor Summary as bullets
        st.subheader("Investor Summary")
        if inv:
            lines = [ln.strip() for ln in inv.replace("\r", "").split("\n") if ln.strip()]
            if not lines:
                lines = [b.strip() for b in inv.split(". ") if b.strip()]
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

        # Market Size & Revenue & Monetization
        st.subheader("Market Size (TAM)")
        st.write(ms or "Not found from public sources.")

        st.subheader("Estimated Revenue")
        st.write(rev or "Not found")

        st.subheader("Monetization")
        bm  = mon.get("business_model") or ""
        rvs = mon.get("revenue_streams") or []
        if bm:
            st.markdown("**Business model**")
            st.write(bm)
        if rvs:
            st.markdown("**Revenue streams**")
            for item in rvs[:6]:
                st.write(f"- {item}")

        # Export + Raw JSON tucked away
        st.download_button(
            "Download JSON",
            json.dumps(data, indent=2),
            file_name=f"{name}_ddlite.json",
            use_container_width=True,
        )
        with st.expander("Show raw JSON"):
            st.code(json.dumps(data, indent=2), language="json")

    # Optional: show the public enrichment match
    if wiki:
        st.markdown("**Wikipedia match**")
        st.write(wiki.get("title") or "")
        if wiki.get("url"):
            st.write(wiki["url"])

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
        return "\n".join(f"- {item}" for item in items)
