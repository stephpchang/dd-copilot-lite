# app/funding_lookup.py
import re
import math
from typing import Callable, Dict, List, Any, Optional
import streamlit as st

# ----- Seed demo data so the feature works even with no live hits -----
# Add/adjust companies as you like. Dates use ISO YYYY-MM-DD.
_SEED: Dict[str, Dict[str, Any]] = {
    "anthropic": {
        "rounds": [
            {
                "round": "Series C",
                "date": "2023-05-23",
                "amount_usd": 450_000_000,
                "lead_investors": ["Spark Capital"],
                "other_investors": ["Google", "Salesforce Ventures"],
                "source": "https://techcrunch.com/"
            },
            {
                "round": "Series B",
                "date": "2022-04-01",
                "amount_usd": 580_000_000,
                "lead_investors": ["Sam Bankman-Fried (FTX)"],
                "other_investors": ["Others"],
                "source": "https://www.theinformation.com/"
            }
        ],
    },
    "figma": {
        "rounds": [
            {
                "round": "Series E",
                "date": "2021-06-24",
                "amount_usd": 200_000_000,
                "lead_investors": ["Durable Capital Partners"],
                "other_investors": ["Sequoia", "a16z", "Index"],
                "source": "https://www.figma.com/blog/"
            }
        ],
    },
    "ramp": {
        "rounds": [
            {
                "round": "Series D",
                "date": "2024-05-01",
                "amount_usd": 150_000_000,
                "lead_investors": ["Khosla Ventures"],
                "other_investors": ["Founders Fund", "Stripe"],
                "source": "https://techcrunch.com/"
            }
        ],
    },
}

# ----- Parsing regexes -----
_ROUND_PAT = re.compile(
    r"\b(pre[-\s]?seed|seed|series\s+[a-k]|growth|mezzanine|bridge|venture|angel)\b",
    re.I,
)
_AMOUNT_PAT = re.compile(
    r"\$?\s?([0-9][0-9,\.]*)\s*(billion|bn|b|million|mm|m|thousand|k)?",
    re.I,
)
_LEAD_PAT = re.compile(r"\bled\s+by\s+([^.;,\n]+)", re.I)
_DATE_PAT = re.compile(
    r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?)\s+\d{1,2},\s+\d{4}|\b\d{4}\b"
)

def _norm_round(s: str) -> str:
    s = s.lower().strip()
    s = s.replace("series ", "Series ").replace("seed", "Seed")
    if s.startswith("series "):
        parts = s.split()
        if len(parts) == 2:
            return f"Series {parts[1].upper()}"
    if s in ("pre seed", "pre-seed"):
        return "Pre-Seed"
    if s == "seed":
        return "Seed"
    return s.title()

def _to_usd(amount: str, unit: Optional[str]) -> Optional[int]:
    try:
        amt = float(amount.replace(",", ""))
    except Exception:
        return None
    factor = 1.0
    if unit:
        u = unit.lower()
        if u in ("billion", "bn", "b"):
            factor = 1_000_000_000
        elif u in ("million", "mm", "m"):
            factor = 1_000_000
        elif u in ("thousand", "k"):
            factor = 1_000
    return int(math.floor(amt * factor))

def _fmt_usd(n: Optional[int]) -> str:
    if not n:
        return ""
    return "${:,}".format(n)

def _parse_snippet(snippet: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    # Round
    r = _ROUND_PAT.search(snippet or "")
    if r:
        out["round"] = _norm_round(r.group(1))
    # Amount
    a = _AMOUNT_PAT.search(snippet or "")  # <-- fixed: use the ALL-CAPS name
    if a:
        out["amount_usd"] = _to_usd(a.group(1), a.group(2))
    # Lead investor
    l = _LEAD_PAT.search(snippet or "")
    if l:
        lead = l.group(1).strip()
        lead = re.split(r"\band\b|,|;", lead)[0].strip()
        out["lead_investors"] = [lead]
    # Date (loose; prefer YYYY if that's all we have)
    d = _DATE_PAT.search(snippet or "")
    if d:
        out["date"] = d.group(0)
    return out

def _merge_round(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(a)
    for k, v in b.items():
        if v in (None, "", [], {}):
            continue
        if k == "lead_investors":
            existing = set(out.get("lead_investors") or [])
            for x in (v or []):
                if x not in existing:
                    existing.add(x)
            out["lead_investors"] = list(existing)
        else:
            out[k] = v
    return out

def _dedupe_rounds(rounds: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # naive: group by round label if present, else by amount
    buckets: Dict[str, Dict[str, Any]] = {}
    for r in rounds:
        key = r.get("round") or _fmt_usd(r.get("amount_usd")) or "unknown"
        if key in buckets:
            buckets[key] = _merge_round(buckets[key], r)
        else:
            buckets[key] = r
    out = list(buckets.values())
    out.sort(key=lambda x: (x.get("amount_usd") or 0), reverse=True)
    return out

def get_funding_data(
    company_name: str,
    serp_func: Optional[Callable[[str, int], List[Dict[str, str]]]] = None
) -> Dict[str, Any]:
    """
    Returns:
    {
      "rounds": [
        {"round": str, "date": str|None, "amount_usd": int|None,
         "lead_investors": [str], "other_investors": [str], "source": str|None}
      ],
      "investors": [str],
      "sources": [str]
    }
    """
    name_key = (company_name or "").strip().lower()
    result: Dict[str, Any] = {"rounds": [], "investors": [], "sources": []}

    # 1) Seed data
    if name_key in _SEED:
        rounds = _SEED[name_key]["rounds"]
        result["rounds"].extend(rounds)
        for r in rounds:
            for inv in r.get("lead_investors", []) + r.get("other_investors", []):
                if inv and inv not in result["investors"]:
                    result["investors"].append(inv)
            if r.get("source") and r["source"] not in result["sources"]:
                result["sources"].append(r["source"])

    # 2) Search-based extraction
    if serp_func:
        queries = [
            f"{company_name} raises funding round led by",
            f"{company_name} funding Series",
            f"{company_name} investment round amount",
            f"{company_name} lead investor funding",
        ]
        hits: List[Dict[str, str]] = []
        for q in queries:
            try:
                hits.extend(serp_func(q, num=6))  # serp returns [{title,snippet,url}]
            except Exception:
                pass

        parsed_rounds: List[Dict[str, Any]] = []
        for h in hits:
            snip = h.get("snippet") or ""
            url = h.get("url") or ""
            if not snip:
                continue
            parsed = _parse_snippet(snip)
            if parsed:
                parsed["source"] = url
                parsed_rounds.append(parsed)
            if url and url not in result["sources"]:
                result["sources"].append(url)

        if parsed_rounds:
            merged = _dedupe_rounds(parsed_rounds)
            existing_labels = {r.get("round") for r in result["rounds"]}
            for r in merged:
                if r.get("round") in existing_labels:
                    for i, ex in enumerate(result["rounds"]):
                        if ex.get("round") == r.get("round"):
                            result["rounds"][i] = _merge_round(ex, r)
                            break
                else:
                    result["rounds"].append(r)

            invs: List[str] = []
            for r in result["rounds"]:
                invs.extend(r.get("lead_investors") or [])
                invs.extend(r.get("other_investors") or [])
            seen = set()
            uniq: List[str] = []
            for x in invs:
                if x and x not in seen:
                    seen.add(x)
                    uniq.append(x)
            result["investors"] = uniq or result["investors"]

    return result
