# Due Diligence Co-Pilot (Lite)

Provides profiles of a company’s **team**, **market**, and **competition** to accelerate early-stage investment assessments.

## Features
- **Company Overview** – Summarizes the company’s focus and positioning.
- **Founding Team** – Lists key founders and leadership.
- **Market Insights** – Highlights market trends and positioning.
- **Competition** – Identifies top competitors and alternatives.
- **Investor Summary** *(optional)* – Generates a concise, 5-bullet investor brief.

## How It Works
1. Enter a company name or website.
2. The app fetches and cleans data from multiple trusted sources.
3. Results are displayed in four main sections, with optional AI summarization.

## Setup Instructions
1. **Clone the repo**:
   ```bash
   git clone https://github.com/stephpchang/dd-copilot-lite.git
   cd dd-copilot-lite
## Install Dependencies 
pip install -r requirements.txt
## Add your OpenAI API key:
In Streamlit Cloud: go to Settings → Secrets and add:
OPENAI_API_KEY = "your_api_key_here"
## Run Locally
streamlit run app.py
