import streamlit as st

st.set_page_config(page_title="Due Diligence Co-Pilot (Lite)")
st.title("Due Diligence Co-Pilot (Lite)")

st.write("Provides profiles of a company’s team, market, and competition to accelerate early-stage investment assessments.")

company = st.text_input("Enter company name or website")

if st.button("Run"):
    if company.strip() == "":
        st.warning("Please enter a company name.")
    else:
        st.success(f"Placeholder output: Profile for {company}")
        st.write({
            "Company Overview": "Example description of the company.",
            "Team": ["Founder Name (ex-Google)", "CTO Name (ex-Amazon)"],
            "Market": "Example market size and trends.",
            "Competition": ["Competitor A", "Competitor B"]
        })
