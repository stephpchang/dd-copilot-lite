# app/funding_lookup.py
import re
import math
from typing import Callable, Dict, List, Any, Optional
import streamlit as st

# ----- Seed demo data so the feature works even with no live hits -----
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
                "lead_investors": ["FTX (Sam Bankman-Fried)"],
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

# ----- Parsing regexes (tighter to avoid "$23" from dates like "May 23") -----
_ROUND_PAT = re.compile(
    r"\b(pre[-\s]?seed|seed|series\s+[a-k]|growth|mezzanine|bridge|venture|angel)\b",
    re.I,
)

# Accept either:
# 1) $ 1,234,567 (commas) with optional unit
# 2) $ 12.3 million/billion/etc.  OR  12.3 million/billion/etc.
_AMOUNT_PAT = re.compile(
    r"""
    (?:
        \$\s*
        (?P<num_commas>\d{1,3}(?:,\d{3})+(?:\.\d+)?)
        \s*(?P<unit_commas>billion|bn|b|million|mm|m|thousand|k)?
    )
    |
    (?:
        \$?\s*(?P<num_unit>\d+(?:\.\d+)?)
        \s*(?P<unit_only>billion|bn|b|million|mm|m|thousand|k)
    )
    """,
    re.I | re.X,
)

# Funding keywords to reduce false-positives (e.g., valuations, revenues)
_FUNDING_HINT = re.compile(r"\b(raised|raise|funding|round|series|financing|led by|investment)\b", re.I)

# Avoid amounts that are actually part of dates (e.g., "May 23")
_MONTH_NEAR_NUM = re.compile(
    r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\$?\d{1,2}\b", re.I
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

def _to_usd(num_str: str, unit: Optional[str]) -> Optional[int]:
    try:
        amt = float(num_str.replace(",", ""))
    except Exception:
        return None
    mult = 1
    if unit:
        u = unit.lower()
        if u in ("trillion", "tn", "t"): mult = 1_000_000_000_000
        elif u in ("billion", "bn", "b"): mult = 1_000_000_000
        elif u in ("million", "mm", "m"): mult = 1_000_000
        elif u in ("thousand", "k"):      mult = 1_000
    return int(round(amt * mult))

def _likely_funding_context(text: str) -> bool:
    return bool(_FUNDING_HINT.search(text or ""))

def _clean_lead_chunk(s: str) -> str:
    # Remove trailing "with participation from ..." if present
    s = re.sub(r"\bwith participation from\b.*$", "", s, flags=re.I).strip()
    # Take first entity before "and" or comma
    s = re.split(r"\band\b|,|;", s)[0].strip()
    return s

def _parse_amount(snippet: str, title: str) -> Optional[int]:
    text = f"{title} {snippet}"
    if not _likely_funding_context(text):
        return None
    if _MONTH_NEAR_NUM.search(text):
        # looks like a date; skip tiny numbers
        pass

    m = _AMOUNT_PAT.search(text)
    if not m:
        return None

    if m.group("num_commas"):
        amt = _to_usd(m.group("num_commas"), m.group("unit_commas"))
    else:
        amt = _to_usd(m.group("num_unit"), m.group("unit_only"))

    # Reject small amounts (< $1M) unless a unit made it >= 1M
    if not amt or amt < 1_000_000:
        return None
    return amt

def _parse_snippet(snippet: str, title: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    # Round (if present)
    r = _ROUND_PAT.search(snippet or "") or _ROUND_PAT.search(title or "")
    if r:
        out["round"] = _norm_round(r.group(1))

    # Amount (strict)
    amt = _parse_amount(snippet or "", title or "")
    if amt:
        out["amount_usd"] = amt

    # Lead investor
    l = _LEAD_PAT.search(snippet or "") or _LEAD_PAT.search(title or "")
    if l:
        lead = _clean_lead_chunk(l.group(1))
        if lead:
            out["lead_investors"] = [lead]

    # Date (loose; keep if present)
    d = _DATE_PAT.search(snippet or "") or _DATE_PAT.search(title or "")
    if d:
        out["date"] = d.group(0)

    return out

def _merge_round(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(a)
    for k, v in b.items():
        if v in (None, "", [], {}):
            continue
        if k == "lead_investors":
            existing = []
            for x in (out.get("lead_investors") or []):
                if x and x not in existing:
                    existing.append(x)
            for x in (v or []):
                if x and x not in existing:
                    existing.append(x)
            out["lead_investors"] = existing
        else:
            # don't let "unknown" overwrite a real value
            if isinstance(v, str) and v.strip().lower() == "unknown":
                continue
            out[k] = v
    return out

def _dedupe_rounds(rounds: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # drop completely empty parses
    rounds = [r for r in rounds if any(r.get(k) for k in ("round", "amount_usd", "date", "lead_investors"))]
    buckets: Dict[str, Dict[str, Any]] = {}
    for r in rounds:
        # group by round label if present; else by amount; else by date
        key = r.get("round") or (str(r.get("amount_usd")) if r.get("amount_usd") else r.get("date") or "unknown")
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
            f"{company_name} financing round led by",
        ]
        hits: List[Dict[str, str]] = []
        for q in queries:
            try:
                hits.extend(serp_func(q, num=6))  # serp returns [{title,snippet,url}]
            except Exception:
                pass

        parsed_rounds: List[Dict[str, Any]] = []
        for h in hits:
            title = h.get("title") or ""
            snip  = h.get("snippet") or ""
            url   = h.get("url") or ""
            if not (title or snip):
                continue
            parsed = _parse_snippet(snip, title)
            if parsed:
                parsed["source"] = url
                parsed_rounds.append(parsed)
            if url and url not in result["sources"]:
                result["sources"].append(url)

        if parsed_rounds:
            merged = _dedupe_rounds(parsed_rounds)
            existing_labels = {r.get("round") for r in result["rounds"] if r.get("round")}
            for r in merged:
                if r.get("round") and r.get("round") in existing_labels:
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
            # de-dup while preserving order
            seen = set()
            uniq: List[str] = []
            for x in invs:
                if x and x not in seen:
                    seen.add(x); uniq.append(x)
            result["investors"] = uniq or result["investors"]

    return result
