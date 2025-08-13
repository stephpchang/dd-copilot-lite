# app/funding_lookup.py
import re
from typing import Callable, Dict, List, Any, Optional

# ----- Seed demo data -----
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
    }
}

# ----- Regex -----
_ROUND_PAT = re.compile(r"\b(pre[-\s]?seed|seed|series\s+[a-k]|growth|mezzanine|bridge|venture|angel)\b", re.I)

_AMOUNT_PAT = re.compile(
    r"""
    (?:
        \$\s*(?P<num_commas>\d{1,3}(?:,\d{3})+(?:\.\d+)?)\s*(?P<unit_commas>trillion|tn|t|billion|bn|b|million|mm|m|thousand|k)?
    )
    |
    (?:
        \$?\s*(?P<num_unit>\d+(?:\.\d+)?)\s*(?P<unit_only>trillion|tn|t|billion|bn|b|million|mm|m|thousand|k)
    )
    """,
    re.I | re.X,
)

_POSITIVE_CONTEXT = re.compile(
    r"\b(raised?|funding|round|series|financing|led by|investment round|fundraise|round of)\b",
    re.I,
)
_NEGATIVE_CONTEXT = re.compile(r"\b(valuation|valued|market size|tam|sam|som|revenue|arr|sales|market cap|budget|capex|forecast)\b", re.I)
_MONTH_NEAR_NUM = re.compile(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\$?\d{1,2}\b", re.I)
_LEAD_PAT = re.compile(r"\bled\s+by\s+([^.;,\n]+)", re.I)
_DATE_PAT = re.compile(
    r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?)\s+\d{1,2},\s+\d{4}|\b\d{4}\b|\b\d{4}-\d{2}-\d{2}\b"
)

def _norm_round(s: str) -> str:
    s = s.lower().strip().replace("series ", "Series ").replace("seed", "Seed")
    if s.startswith("series "):
        parts = s.split()
        if len(parts) == 2:
            return f"Series {parts[1].upper()}"
    if s in ("pre seed", "pre-seed"): return "Pre-Seed"
    if s == "seed": return "Seed"
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
    val = int(round(amt * mult))
    # Venture rounds usually < $10B
    if val <= 0 or val > 10_000_000_000:
        return None
    if val < 1_000_000:  # drop tiny amounts like $23
        return None
    return val

def _near(text: str, start: int, end: int, radius: int = 80) -> str:
    a = max(0, start - radius)
    b = min(len(text), end + radius)
    return text[a:b]

def _clean_lead_chunk(s: str) -> str:
    s = re.sub(r"\bwith participation from\b.*$", "", s, flags=re.I).strip()
    s = re.split(r"\band\b|,|;", s)[0].strip()
    return s

def _parse_amounts(text: str) -> Optional[int]:
    best = None
    for m in _AMOUNT_PAT.finditer(text):
        start, end = m.span()
        window = _near(text, start, end)
        if _NEGATIVE_CONTEXT.search(window):
            continue
        if not _POSITIVE_CONTEXT.search(window):
            continue
        if _MONTH_NEAR_NUM.search(window):
            continue
        if m.group("num_commas"):
            amt = _to_usd(m.group("num_commas"), m.group("unit_commas"))
        else:
            amt = _to_usd(m.group("num_unit"), m.group("unit_only"))
        if amt:
            best = max(best or 0, amt)
    return best

def _parse_snippet(snippet: str, title: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    text = f"{title} {snippet}"

    r = _ROUND_PAT.search(text)
    if r:
        out["round"] = _norm_round(r.group(1))

    amt = _parse_amounts(text)
    if amt:
        out["amount_usd"] = amt

    # If we found a round but no amount, try looser nearby amount capture
    if out.get("round") and "amount_usd" not in out:
        for m in _AMOUNT_PAT.finditer(text):
            window = _near(text, *m.span(), radius=120)
            if re.search(r"\b(series|round)\b", window, re.I):
                if m.group("num_commas"):
                    a2 = _to_usd(m.group("num_commas"), m.group("unit_commas"))
                else:
                    a2 = _to_usd(m.group("num_unit"), m.group("unit_only"))
                if a2:
                    out["amount_usd"] = a2
                    break

    l = _LEAD_PAT.search(text)
    if l:
        lead = _clean_lead_chunk(l.group(1))
        if lead:
            out["lead_investors"] = [lead]

    d = _DATE_PAT.search(text)
    if d:
        out["date"] = d.group(0)

    return out

def _merge_round(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(a)
    for k, v in b.items():
        if v in (None, "", [], {}):
            continue
        if k == "lead_investors":
            existing = out.get("lead_investors") or []
            for x in v:
                if x and x not in existing:
                    existing.append(x)
            out["lead_investors"] = existing
        else:
            if isinstance(v, str) and v.strip().lower() == "unknown":
                continue
            out[k] = v
    return out

def _dedupe_rounds(rounds: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rounds = [r for r in rounds if any(r.get(k) for k in ("round", "amount_usd", "date", "lead_investors"))]
    buckets: Dict[str, Dict[str, Any]] = {}
    for r in rounds:
        key = r.get("round") or (str(r.get("amount_usd")) if r.get("amount_usd") else r.get("date") or "unknown")
        buckets[key] = _merge_round(buckets.get(key, {}), r)
    out = list(buckets.values())
    out.sort(key=lambda x: (x.get("amount_usd") or 0), reverse=True)
    return out

def get_funding_data(
    company_name: str,
    serp_func: Optional[Callable[[str, int], List[Dict[str, str]]]] = None
) -> Dict[str, Any]:
    name_key = (company_name or "").strip().lower()
    result: Dict[str, Any] = {"rounds": [], "investors": [], "sources": []}

    if name_key in _SEED:
        rounds = _SEED[name_key]["rounds"]
        result["rounds"].extend(rounds)
        for r in rounds:
            for inv in r.get("lead_investors", []) + r.get("other_investors", []):
                if inv and inv not in result["investors"]:
                    result["investors"].append(inv)
            if r.get("source") and r["source"] not in result["sources"]:
                result["sources"].append(r["source"])

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
                hits.extend(serp_func(q, num=3))
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
                    seen.add(x); uniq.append(x)
            result["investors"] = uniq or result["investors"]

    return result
