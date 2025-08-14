import streamlit as st
import pandas as pd
from io import BytesIO
from datetime import datetime

st.set_page_config(page_title="USV Thematic Deal Radar (MVP)", layout="wide")

st.title("🚀 USV Thematic Deal Radar (MVP)")
st.caption("Public-data demo: filter by thesis, stage, and amount; export results for outreach.")

# ------------------------
# Sample thematic data (curated for demo; replace/extend freely)
# ------------------------
data = [
    # AI Infrastructure & Agentic Stack
    {
        "Company": "GigaIO",
        "Theme": "AI Infrastructure & Agentic Stack",
        "Description": "Composable AI inferencing hardware; edge 'suitcase' supercomputers.",
        "Stage": "Series B",
        "Funding": 21_000_000,
        "HQ": "San Diego, CA",
        "Date": "2025-07-18",
        "Sources": ["https://gigaio.com/"],
    },
    {
        "Company": "fal",
        "Theme": "AI Infrastructure & Agentic Stack",
        "Description": "Hosted inference + infra for production AI workloads.",
        "Stage": "Series C",
        "Funding": 125_000_000,
        "HQ": "Remote / US",
        "Date": "2025-07-31",
        "Sources": ["https://fal.ai/"],
    },
    {
        "Company": "TensorWave",
        "Theme": "AI Infrastructure & Agentic Stack",
        "Description": "AMD‑accelerated GPU clusters for model training.",
        "Stage": "Series A",
        "Funding": 100_000_000,
        "HQ": "Austin, TX",
        "Date": "2025-05-14",
        "Sources": ["https://www.tensorwave.com/"],
    },

    # Vertical / Niche AI
    {
        "Company": "Hume AI",
        "Theme": "Vertical/Niche AI",
        "Description": "Affective models for more natural human‑AI interaction.",
        "Stage": "Series B",
        "Funding": 50_000_000,
        "HQ": "New York, NY",
        "Date": "2025-01-22",
        "Sources": ["https://www.hume.ai/"],
    },
    {
        "Company": "Endex",
        "Theme": "Vertical/Niche AI",
        "Description": "Agentic workflows inside spreadsheets for analysts.",
        "Stage": "Series A",
        "Funding": 14_000_000,
        "HQ": "San Francisco, CA",
        "Date": "2025-08-01",
        "Sources": ["https://endex.ai/"],
    },

    # Climate & Real‑World Systems
    {
        "Company": "Amogy",
        "Theme": "Climate & Real‑World Systems",
        "Description": "Ammonia‑to‑power tech for ships and data centers.",
        "Stage": "Growth",
        "Funding": 23_000_000,
        "HQ": "Brooklyn, NY",
        "Date": "2025-07-15",
        "Sources": ["https://amogy.co/"],
    },
    {
        "Company": "Pano AI",
        "Theme": "Climate & Real‑World Systems",
        "Description": "AI wildfire detection network covering millions of acres.",
        "Stage": "Series B",
        "Funding": 44_000_000,
        "HQ": "San Francisco, CA",
        "Date": "2025-07-10",
        "Sources": ["https://www.pano.ai/"],
    },

    # Open Data / Ownership / Crypto-as-Rails (for agents)
    {
        "Company": "Privy",
        "Theme": "Open Data / Ownership / Crypto-as-Rails",
        "Description": "Identity + wallet infra for consumer apps and agents.",
        "Stage": "Series A",
        "Funding": 18_000_000,
        "HQ": "Remote / US",
        "Date": "2025-06-30",
        "Sources": ["https://www.privy.io/"],
    },
    {
        "Company": "Farcaster",
        "Theme": "Open Data / Ownership / Crypto-as-Rails",
        "Description": "Open social protocol and data portability primitives.",
        "Stage": "Series A",
        "Funding": 30_000_000,
        "HQ": "San Francisco, CA",
        "Date": "2025-05-20",
        "Sources": ["https://www.farcaster.xyz/"],
    },

    # Bonus: Dev tools / learning (USV-adjacent themes)
    {
        "Company": "Zed",
        "Theme": "Developer Tools",
        "Description": "High‑performance collaborative code editor.",
        "Stage": "Series A",
        "Funding": 12_000_000,
        "HQ": "San Francisco, CA",
        "Date": "2024-07-20",
        "Sources": ["https://zed.dev/"],
    },
]

df = pd.DataFrame(data)
df["Date"] = pd.to_datetime(df["Date"])

# ------------------------
# Filters
# ------------------------
with st.sidebar:
    st.header("Filters")
    theme_opts = ["All"] + sorted(df["Theme"].unique())
    stage_opts = ["All"] + sorted(df["Stage"].unique())
    selected_theme = st.selectbox("Theme", theme_opts, index=0)
    selected_stage = st.selectbox("Stage", stage_opts, index=0)
    min_amt = st.slider("Min funding ($M)", 0, int(df["Funding"].max() / 1_000_000), 0)
    date_window = st.selectbox("Time window", ["All", "Last 30 days", "Last 90 days", "YTD"], index=1)

def _within_window(d: pd.Timestamp, window: str) -> bool:
    if window == "All": return True
    today = pd.Timestamp(datetime.utcnow().date())
    if window == "Last 30 days": return d >= today - pd.Timedelta(days=30)
    if window == "Last 90 days": return d >= today - pd.Timedelta(days=90)
    if window == "YTD": return d >= pd.Timestamp(year=today.year, month=1, day=1)
    return True

f = df.copy()
if selected_theme != "All":
    f = f[f["Theme"] == selected_theme]
if selected_stage != "All":
    f = f[f["Stage"] == selected_stage]
f = f[f["Funding"] >= (min_amt * 1_000_000)]
f = f[f["Date"].apply(lambda d: _within_window(d, date_window))]

# ------------------------
# Summary bar
# ------------------------
st.subheader("Summary")
c1, c2, c3 = st.columns(3)
c1.metric("Companies", len(f))
c2.metric("Total Funding", f"${f['Funding'].sum()/1_000_000:,.1f}M")
c3.metric("Avg Funding", f"${(f['Funding'].mean()/1_000_000) if len(f)>0 else 0:,.1f}M")

# ------------------------
# Results grid
# ------------------------
st.subheader("Results")
def money_fmt(n: int) -> str:
    if n >= 1_000_000_000: return f"${n/1_000_000_000:.1f}B"
    return f"${n/1_000_000:.1f}M"

if len(f) == 0:
    st.info("No results match your filters.")
else:
    for _, row in f.sort_values("Date", ascending=False).iterrows():
        with st.container(border=True):
            st.markdown(f"### {row['Company']}")
            st.write(row["Description"])
            colA, colB, colC, colD = st.columns([2,2,2,4])
            colA.write(f"**Theme:** {row['Theme']}")
            colB.write(f"**Stage:** {row['Stage']}")
            colC.write(f"**Funding:** {money_fmt(int(row['Funding']))}")
            colD.write(f"**Date:** {row['Date'].date().isoformat()}")
            if isinstance(row["Sources"], list) and row["Sources"]:
                srcs = " · ".join([f"[source]({u})" for u in row["Sources"]])
                st.markdown(f"**Sources:** {srcs}")

# ------------------------
# Export
# ------------------------
st.subheader("Export")
csv = f.to_csv(index=False)
st.download_button("Download CSV", csv, "usv_thematic_deals.csv", "text/csv", use_container_width=True)

buf = BytesIO()
with pd.ExcelWriter(buf, engine="XlsxWriter") as writer:
    f.to_excel(writer, index=False)
st.download_button(
    "Download Excel",
    buf.getvalue(),
    "usv_thematic_deals.xlsx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True,
)

st.caption("Demo data only. Real version can ingest press releases, SEC Form D, and job feeds to auto-refresh this list.")
