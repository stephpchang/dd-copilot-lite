# streamlit_app.py
# DD Copilot Lite — simple one-file app with tabs, exports, and caching

import json
from typing import Dict, Any, List
import streamlit as st

# -------- Page setup --------
st.set_page_config(page_title="DD Copilot Lite", layout="wide")

# -------- Simple config --------
CONFIG = {
    "cache_ttl_seconds": 86400,   # 24 hours
    "enable_tabs": True,
    "enable_markdown_export": True,
    "enable_json_export": True,
}

# -------- Helpers --------
def _fmt_usd(n):
    try:
        return "${:,.0f}".format(float(n))
    except Exception:
        return str(n)

def to_markdown(report: Dict[str, Any]) -> str:
    """Build a reviewer-friendly Markdown brief from the unified report dict."""
    md: List[str] = []

    # Snapshot
    company = report.get("company", {})
    founders = report.get("founders", [])
    md.append(f"# {company.get('name','Company Brief')}")
    snapshot_lines = []
    if company.get("website"): snapshot_lines.append(f"- **Website:** {company['website']}")
    if company.get("hq"): snapshot_lines.append(f"- **HQ:** {company['hq']}")
    if company.get("stage"): snapshot_lines.append(f"- **Stage:** {company['stage']}")
    if company.get("business_model"): snapshot_lines.append(f"- **Business model:** {company['business_model']}")
    if company.get("icp"): snapshot_lines.append(f"- **ICP:** {company['icp']}")
    if founders:
        fnames = ", ".join([f.get("name","") for f in founders if f.get("name")])
        if fnames: snapshot_lines.append(f"- **Founders:** {fnames}")
    if snapshot_lines:
        md.append("## Snapshot")
        md.append("\n".join(snapshot_lines))

    # Funding
    funding = report.get("funding", {})
    rounds: List[Dict[str, Any]] = funding.get("rounds", [])
    if funding or rounds:
        md.append("## Funding")
        if funding.get("total_usd") is not None:
            md.append(f"- **Total raised:** {_fmt_usd(funding['total_usd'])}")
        if rounds:
            md.append("**Rounds**")
            for r in rounds:
                line = f"- {r.get('date','')} • {r.get('type','')} • "
                if r.get("amount_usd") is not None:
                    line += _fmt_usd(r.get("amount_usd"))
                leads = r.get("lead_investors", []) or r.get("investors", [])
                if leads:
                    line += f" • Leads: {', '.join(leads)}"
                md.append(line)

    # Market Map
    market_map = report.get("market_map", {})
    competitors = market_map.get("competitors", [])
    if market_map or competitors:
        md.append("## Market Map")
        axes = market_map.get("axes")
        if axes: md.append(f"- **Axes:** {', '.join([str(a) for a in axes])}")
        if competitors:
            md.append("**Competitors**")
            for c in competitors:
                name = c.get("name","")
                note = c.get("note") or c.get("positioning") or ""
                md.append(f"- {name}" + (f": {note}" if note else ""))

    # Differentiators
    diffs = report.get("differentiators", [])
    if diffs:
        md.append("## Differentiators")
        for d in diffs:
            md.append(f"- {d}")

    # Key Questions
    qs = report.get("key_questions", [])
    if qs:
        md.append("## Key Diligence Questions")
        for q in qs:
            md.append(f"- {q}")

    # Sources
    sources = report.get("sources", [])
    if sources:
        md.append("## Sources")
        for s in sources:
            label = s.get("label") or s.get("title") or s.get("url","Source")
            url = s.get("url") or ""
            if url:
                md.append(f"- [{label}]({url})")
            else:
                md.append(f"- {label}")

    # Notes
    if report.get("notes"):
        md.append("## Notes")
        md.append(str(report["notes"]).strip())

    return "\n\n".join([x for x in md if x])

def json_bytes(report: Dict[str, Any]) -> bytes:
    return json.dumps(report, indent=2, ensure_ascii=False).encode("utf-8")

def render_tabs(report: Dict[str, Any]) -> None:
    """Render the unified report dict into tabs. Only shows tabs for sections that exist."""
    tabs = []
    has_snapshot = bool(report.get("company") or report.get("founders"))
    has_funding  = bool(report.get("funding"))
    has_market   = bool(report.get("market_map"))
    has_diffs    = bool(report.get("differentiators"))
    has_qs       = bool(report.get("key_questions"))
    has_sources  = bool(report.get("sources"))
    if has_snapshot: tabs.append("Snapshot")
    if has_funding:  tabs.append("Funding")
    if has_market:   tabs.append("Market Map")
    if has_diffs:    tabs.append("Differentiators")
    if has_qs:       tabs.append("Key Questions")
    if has_sources:  tabs.append("Sources")
    tabs.append("JSON")

    t = st.tabs(tabs)
    i = 0

    if has_snapshot:
        with t[i]:
            company = report.get("company", {})
            founders = report.get("founders", [])
            st.subheader(company.get("name","Snapshot"))
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"**Website:** {company.get('website','—')}")
                st.markdown(f"**HQ:** {company.get('hq','—')}")
                st.markdown(f"**Stage:** {company.get('stage','—')}")
            with c2:
                st.markdown(f"**Business model:** {company.get('business_model','—')}")
                st.markdown(f"**ICP:** {company.get('icp','—')}")
            if founders:
                st.markdown("**Founders**")
                for f in founders:
                    name = f.get("name","")
                    role = f.get("roles") or f.get("title") or ""
                    st.markdown(f"- **{name}**" + (f" — {role}" if role else ""))
        i += 1

    if has_funding:
        with t[i]:
            st.subheader("Funding")
            funding = report.get("funding", {})
            rounds = funding.get("rounds", [])
            if funding.get("total_usd") is not None:
                st.markdown(f"**Total raised:** {_fmt_usd(funding['total_usd'])}")
            if rounds:
                st.dataframe(
                    [{
                        "Date": r.get("date",""),
                        "Type": r.get("type",""),
                        "Amount (USD)": r.get("amount_usd"),
                        "Lead Investors": ", ".join(r.get("lead_investors", []) or r.get("investors", []) or [])
                    } for r in rounds],
                    use_container_width=True
                )
        i += 1

    if has_market:
        with t[i]:
            st.subheader("Market Map")
            mm = report.get("market_map", {})
            axes = mm.get("axes")
            if axes: st.markdown(f"**Axes:** {', '.join([str(a) for a in axes])}")
            competitors = mm.get("competitors", [])
            if competitors:
                st.dataframe(
                    [{
                        "Name": c.get("name",""),
                        "Positioning": c.get("note") or c.get("positioning",""),
                        "URL": c.get("url","")
                    } for c in competitors],
                    use_container_width=True
                )
        i += 1

    if has_diffs:
        with t[i]:
            st.subheader("Differentiators")
            for d in report.get("differentiators", []):
                st.markdown(f"- {d}")
        i += 1

    if has_qs:
        with t[i]:
            st.subheader("Key Diligence Questions")
            for q in report.get("key_questions", []):
                st.markdown(f"- {q}")
        i += 1

    if has_sources:
        with t[i]:
            st.subheader("Sources")
            for s in report.get("sources", []):
                label = s.get("label") or s.get("title") or s.get("url","Source")
                url = s.get("url") or ""
                st.markdown(f"- [{label}]({url})" if url else f"- {label}")
        i += 1

    with t[i]:
        st.subheader("JSON")
        st.code(json.dumps(report, indent=2, ensure_ascii=False), language="json")

# -------- Demo generator --------
def demo_report(query: str) -> Dict[str, Any]:
    """Fallback demo report so the app runs even before you wire your generator."""
    return {
        "company": {
            "name": query.title(),
            "website": f"https://{query.lower().replace(' ', '')}.com",
            "hq": "New York, NY",
            "stage": "Series A",
            "business_model": "SaaS",
            "icp": "Mid-market product teams",
        },
        "founders": [
            {"name": "Alex Kim", "roles": "CEO", "bio": "Ex Stripe", "notables": ["YC alum"]},
            {"name": "Priya Desai", "roles": "CTO", "bio": "Ex Google", "notables": ["PhD ML"]},
        ],
        "funding": {
            "total_usd": 24000000,
            "rounds": [
                {"date": "2023-06-01", "type": "Seed", "amount_usd": 4000000, "lead_investors": ["Homebrew"]},
                {"date": "2024-11-15", "type": "Series A", "amount_usd": 20000000, "lead_investors": ["USV"]},
            ],
            "sources": [
                {"label": "Press release", "url": "https://example.com/series-a"},
            ]
        },
        "market_map": {
            "axes": ["Self-serve vs Enterprise", "Horizontal vs Vertical"],
            "competitors": [
                {"name": "CompetitorOne", "positioning": "Enterprise workflow", "url": "https://competitor1.com"},
                {"name": "CompetitorTwo", "positioning": "Self-serve analytics", "url": "https://competitor2.com"},
            ]
        },
        "differentiators": [
            "Faster deployment than incumbents",
            "Built-in governance and audit",
        ],
        "key_questions": [
            "How painful is the current workflow for target users",
            "Is procurement a blocker at ACV below 30k",
        ],
        "sources": [
            {"label": "Company site", "url": "https://example.com"},
            {"label": "Blog post", "url": "https://example.com/blog"},
        ],
        "notes": "Replace demo_report with your real generator.",
    }

# -------- Your generator hook --------
@st.cache_data(ttl=CONFIG["cache_ttl_seconds"])
def generate_report(company_input: str) -> Dict[str, Any]:
    """
    If you already have a function that returns the final `report` dict,
    replace the demo call below with it, for example:
        return run_company_report(company_input)
    The cached wrapper keeps repeat runs fast for 24 hours.
    """
    try:
        # Uncomment and adjust this to call your real function:
        # return run_company_report(company_input)
        return demo_report(company_input)
    except Exception:
        # As a last resort still show the demo so the UI works
        return demo_report(company_input)

# -------- Sidebar controls --------
with st.sidebar:
    st.header("Controls")
    company_input = st.text_input("Company or domain", placeholder="acme.com or Acme Robotics")
    run_clicked = st.button("Run Search", use_container_width=True)

    st.markdown("---")
    st.caption("Exports")
    md_btn_placeholder = st.empty()
    json_btn_placeholder = st.empty()

# -------- Main area --------
st.title("DD Copilot Lite")

if not company_input:
    st.info("Enter a company name or domain in the sidebar, then click Run Search.")

if run_clicked and company_input:
    try:
        report = generate_report(company_input)

        # Tabs
        if CONFIG["enable_tabs"]:
            render_tabs(report)
        else:
            st.write(report)

        # Exports
        if CONFIG["enable_markdown_export"]:
            md_btn_placeholder.download_button(
                label="Download Markdown",
                data=to_markdown(report).encode("utf-8"),
                file_name=f"{report.get('company',{}).get('name','company')}.md",
                mime="text/markdown",
                use_container_width=True
            )

        if CONFIG["enable_json_export"]:
            json_btn_placeholder.download_button(
                label="Download JSON",
                data=json_bytes(report),
                file_name=f"{report.get('company',{}).get('name','company')}.json",
                mime="application/json",
                use_container_width=True
            )

    except Exception as e:
        st.error("Something went wrong while generating the report.")
        st.exception(e)
