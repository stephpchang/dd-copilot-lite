# app/llm_guard.py
import os
import time
import json
import threading
from typing import Dict, Any, Optional

import streamlit as st
from openai import OpenAI


# One shared semaphore to serialize outbound calls and avoid bursts
@st.cache_resource
def _rate_limit_lock() -> threading.BoundedSemaphore:
    return threading.BoundedSemaphore(value=1)


def _get_model() -> str:
    # Default to a low-cost model
    return os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def _get_client() -> OpenAI:
    """
    Lazy-create the OpenAI client so missing keys do not crash import time.
    Raises a RuntimeError with a friendly message if the key is not set.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Add it in Streamlit Cloud → Manage app → Settings → Secrets."
        )
    return OpenAI(api_key=api_key)


def _retry_after_seconds(exc: Exception) -> Optional[int]:
    """
    Try to read Retry-After from the SDK error response, if present.
    """
    try:
        resp = getattr(exc, "response", None)
        headers = getattr(resp, "headers", None)
        val = headers.get("retry-after") if headers else None
        if val is None:
            return None
        # Some environments give str, some int-like
        return int(str(val))
    except Exception:
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def generate_once(prompt: str, json_schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Make a single structured-output call with caching and retries.
    - Caches by (prompt, json_schema) for 1 hour
    - Serializes calls across sessions via a semaphore
    - Respects Retry-After and uses exponential backoff on transient errors
    """
    lock = _rate_limit_lock()
    with lock:
        attempt = 0
        max_attempts = 5
        sleep = 1

        while True:
            attempt += 1
            try:
                client = _get_client()  # lazy create here
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
                try:
                    return json.loads(content)
                except Exception as parse_err:
                    # Surface a clearer error so the UI can show it
                    raise ValueError(f"Model returned non-JSON content: {str(parse_err)}") from parse_err

            except Exception as e:
                # On last attempt, re-raise immediately
                if attempt >= max_attempts:
                    raise

                # Respect server-provided backoff when available
                retry_after = _retry_after_seconds(e)
                wait = retry_after if retry_after is not None else sleep
                time.sleep(wait)

                # Exponential backoff with a reasonable cap
                sleep = min(sleep * 2, 20)
