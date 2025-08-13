# app/market_size.py
import re
from typing import Dict, List, Any, Optional, Callable
from urllib.parse import urlparse

_AMOUNT = re.compile(r"(?:USD|\$)\s*([0-9][0-9,\.]*)\s*(trillion|tn|t|billion|bn|b|million|mm|m|thousand|k)?", re.I)
_YEAR = re.compile(r"\b(20[0-3]\d|19\d{2})\b")
_SCOPE = re.compile(r"\b(TAM|SAM|SOM|total addressable market|serviceable available market|serviceable obtainable market|market size|market value)\b", re.I)

_TRUSTED = (
    "mckinsey.com","bain.com","bcg.com","gartner.com","forrester.com",
    "deloitte.com","statista.com","idc.com","ibisworld.com",
    "ft.com","wsj.com","bloomberg.com","reuters.com","economist.com",
)

def _norm_amount(num: str, unit: Optional[str]) -> Optional[int]:
    try:
        n = float(num.replace(",", ""))
    except Exception:
        return None
    mult = 1
    if unit:
        u = unit.lower()
        if u in ("trillion","tn","t"): mult = 1_000_000_000_000
        elif u in ("billion","bn","b"): mult = 1_000_000_000
        elif u in ("million","mm","m"): mult = 1_000_000
        elif u in ("thousand","k"):     mult = 1_000
    v = int(n * mult)
    if v <= 0: return None
    return v

def _scope(text: str) -> str:
    m = _SCOPE.search(text or "")
    if not m: return "Market size"
    t = m.group(0).lower()
    if "total addressable" in t or t == "tam": return "TAM"
    if "serviceable available" in t or t == "sam": return "SAM"
    if "serviceable obtainable" in t or t == "som": return "SOM"
    return "Market size"

def _is_trusted(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return False
    return any(d in host for d in _TRUSTED)

def _parse_hit(h: Dict[str, str]) -> Dict[str, Any]:
    t = h.get("title") or ""
    s = h.get("snippet") or ""
    url = h.get("url") or ""
    m = _AMOUNT.search(s) or _AMOUNT.search(t)
    y = _YEAR.search(s) or _YEAR.search(t)
    out: Dict[str, Any] = {}
    if m:
        amt = _norm_amount(m.group(1), m.group(2))
        if amt:
            out["amount_usd"] = amt
    if y:
        out["year"] = y.group(1)
    out["scope"] = _scope(f"{t} {s}")
    out["url"] = url
    return out

def get_market_size(company_name: str, serp_func: Callable[[str, int], List[Dict[str, str]]]) -> Dict[str, Any]:
    queries = [
        f"{company_name} TAM market size",
        f"{company_name} total addressable market",
        f"{company_name} industry market size report",
        f"{company_name} SAM SOM",
    ]
    hits: List[Dict[str, str]] = []
    for q in queries:
        try:
            hits.extend(serp_func(q, 3))
        except Exception:
            pass

    estimates = []
    sources = []
    for h in hits:
        p = _parse_hit(h)
        if p.get("amount_usd"):
            estimates.append(p)
        if h.get("url"):
            sources.append(h["url"])

    # Dedup sources
    seen = set(); uniq = []
    for s in sources:
        if s and s not in seen:
            seen.add(s); uniq.append(s)

    # Prefer trusted sources; then sort by (year, amount)
    trusted = [e for e in estimates if _is_trusted(e.get("url",""))]
    picked = (trusted or estimates)
    picked.sort(key=lambda x: (x.get("year") or "0000", x.get("amount_usd") or 0), reverse=True)

    return {"estimates": picked[:5], "sources": uniq[:10]}
