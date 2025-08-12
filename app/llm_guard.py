# app/llm_guard.py
import json, os, time, threading
from typing import Dict, Any
import streamlit as st
from openai import OpenAI

@st.cache_resource
def _rate_limit_lock() -> threading.BoundedSemaphore:
    # Shared across all users and sessions on the server
    return threading.BoundedSemaphore(value=1)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")  # set in .env

SYSTEM = "You are a concise analyst. Respond with strict JSON only."

def _retry_after_seconds(exc) -> int | None:
    try:
        h = getattr(exc, "response", None).headers  # OpenAI SDK Error has .response
        ra = h.get("retry-after") if h else None
        return int(ra) if ra and ra.isdigit() else None
    except Exception:
        return None

@st.cache_data(ttl=3600, show_spinner=False)
def generate_once(prompt: str, json_schema: Dict[str, Any]) -> Dict[str, Any]:
    # Cached by prompt+schema. Safe because we always return pure data.
    lock = _rate_limit_lock()
    with lock:  # serialize to avoid bursts from concurrent sessions
        attempt, max_attempts, sleep = 0, 5, 1
        while True:
            attempt += 1
            try:
                r = client.chat.completions.create(
                    model=MODEL,
                    messages=[{"role": "system", "content": SYSTEM},
                              {"role": "user", "content": prompt}],
                    response_format={"type": "json_schema", "json_schema": json_schema},
                    temperature=0.2,
                )
                return json.loads(r.choices[0].message.content)
            except Exception as e:
                # Handle 429 and transient errors with backoff
                retry_after = _retry_after_seconds(e)
                wait = retry_after if retry_after is not None else sleep
                if attempt >= max_attempts:
                    raise
                time.sleep(wait)
                sleep = min(sleep * 2, 20)  # exponential backoff
