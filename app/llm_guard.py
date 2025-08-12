# app/llm_guard.py
import os
import time
import json
import threading
from typing import Dict, Any, Optional

import streamlit as st
from openai import OpenAI


@st.cache_resource
def _rate_limit_lock() -> threading.BoundedSemaphore:
    # Serialize calls across sessions to avoid bursts and 429s
    return threading.BoundedSemaphore(value=1)


def _get_model() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def _get_client() -> OpenAI:
    # Lazy-create the client so missing keys don't crash import time
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Add it in Streamlit Cloud → Manage app → Settings → Secrets."
        )
    return OpenAI(api_key=api_key)


def _retry_after_seconds(exc: Exception) -> Optional[int]:
    try:
        resp = getattr(exc, "response", None)
        headers = getattr(resp, "headers", None)
        val = headers.get("retry-after") if headers else None
        return int(str(val)) if val is not None else None
    except Exception:
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def generate_once(prompt: str, json_schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    One structured-output call with caching and retries.
    - Cache key: (prompt, json_schema)
    - Shared semaphore to prevent concurrent bursts
    - Exponential backoff; honors Retry-After when present
    """
    lock = _rate_limit_lock()
    with lock:
        attempt, max_attempts, sleep = 0, 5, 1
        while True:
            attempt += 1
            try:
                client = _get_client()
                resp = client.chat.completions.create(
                    model=_get_model(),
                    messages=[
                        {"role": "system", "content": "You are a concise analyst. Respond with strict JSON only."},
                        {"role": "user", "content": prompt},
                    ],
                    response_format={"type": "json_schema", "json_schema": json_schema},
                    temperature=0.2,
                )
                content = resp.choices[0].message.content
                return json.loads(content)
            except Exception as e:
                if attempt >= max_attempts:
                    raise
                wait = _retry_after_seconds(e) or sleep
                time.sleep(wait)
                sleep = min(sleep * 2, 20)
