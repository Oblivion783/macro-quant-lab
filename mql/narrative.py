"""Turn the snapshot into words.

Two writers:
1. template_narrative: deterministic sentences built from the numbers. Always available.
2. llm_narrative: an optional AI draft (Gemini free tier). It is accepted only if every number
   it states can be found in the snapshot (the grounding check); otherwise the template is used.

The point of the grounding check: an AI may draft, but it may not invent a number.
"""
from __future__ import annotations

import json
import re

from . import monitor
from .monitor import fmt_change, fmt_level

AREA = {"rates_us": "rates", "rates_uk": "rates", "rates_eur": "rates", "rates_in": "rates", "inflation": "inflation",
        "credit": "credit", "equity": "equities", "vol": "volatility", "fx": "FX", "commodities": "commodities"}


def _verb(unit: str, c: float) -> str:
    if unit in ("pct", "spread"):
        return "rose" if c > 0 else "fell" if c < 0 else "was unchanged"
    return "gained" if c > 0 else "lost" if c < 0 else "was flat"


def describe(r: dict) -> str:
    c = r.get("chg_1d")
    if c is None:
        return f"{r['name']} at {fmt_level(r['unit'], r['last'])}."
    mag = fmt_change(r["unit"], abs(c)).lstrip("+")
    tail = ""
    if r.get("move_z") is not None and abs(r["move_z"]) >= 1.5:
        tail = f", about {abs(r['move_z']):.1f}x a normal day's move"
    if c == 0:
        return f"{r['name']} was unchanged at {fmt_level(r['unit'], r['last'])}."
    return f"{r['name']} {_verb(r['unit'], c)} {mag} to {fmt_level(r['unit'], r['last'])}{tail}."


def template_narrative(snapshot: dict, quality_line: str = "") -> dict:
    movers = monitor.top_movers(snapshot, n=6)
    by = {r["id"]: r for r in snapshot["series"]}
    reg = monitor.regime(snapshot)
    headline = describe(movers[0]).rstrip(".") if movers else "A quiet session across the watchlist"
    bullets = [describe(r) for r in movers[1:]]
    key = [by[k] for k in ("UST_10Y", "UK_10Y", "EUR_10Y", "SPX", "USDINR") if k in by and by[k] not in movers]
    bullets += [describe(r) for r in key[:3]]
    context = []
    if "curve" in reg:
        context.append(f"The US 2s10s curve is {reg['curve']} at {fmt_level('spread', by['US_2S10S']['last'])}.")
    if "credit" in reg:
        context.append(f"Credit: {reg['credit']}.")
    if "equity_vol" in reg:
        context.append(f"Equity volatility looks {reg['equity_vol']}.")
    if "inflation_pricing" in reg:
        context.append(f"US 10-year breakeven inflation is {reg['inflation_pricing']}.")
    return {"writer": "template", "headline": headline, "bullets": bullets, "context": context,
            "quality": quality_line}


# ---------------------------------------------------------------- grounding check
_TENOR = re.compile(r"\b\d+(?:\.\d+)?\s*(?:y|yr|year|years|m|mo|month|months|-year|-month)\b(?:s?\b)?", re.I)
_CURVE = re.compile(r"\b\d+s\d+s\b|\b\d+y\d+y\b", re.I)
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_DATE = re.compile(r"\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\b", re.I)
_NUM = re.compile(r"(?<![\w.])[-+]?\d[\d,]*(?:\.\d+)?")


def extract_numbers(text: str, names: list[str]) -> list[float]:
    t = text
    for n in sorted(names, key=len, reverse=True):
        t = t.replace(n, " ")
    for pat in (_CURVE, _TENOR, _YEAR, _DATE):
        t = pat.sub(" ", t)
    nums = []
    for m in _NUM.finditer(t):
        try:
            nums.append(float(m.group(0).replace(",", "")))
        except ValueError:
            pass
    return nums


def check_grounding(text: str, snapshot: dict) -> tuple[bool, list[float]]:
    allowed = monitor.numbers_in_snapshot(snapshot)
    names = [r["name"] for r in snapshot["series"]]
    unknown = []
    for x in extract_numbers(text, names):
        ax = abs(x)
        if ax <= 3 and float(ax).is_integer():
            continue  # small counts ("two", "3 questions") are not market data
        tol = 0.6 if ax >= 100 else 0.011
        if not any(abs(ax - a) <= tol for a in allowed):
            unknown.append(x)
    return (len(unknown) == 0, unknown)


PROMPT = """You are a sell-side style macro strategist writing a short morning note for a multi-asset portfolio manager.
Use ONLY the numbers in the table below, written exactly as shown (bp for rates, % for prices). Do not state any other number,
date, forecast or level. If you are unsure of a cause, say "likely" or leave it out. No investment advice.

Write JSON with keys:
 "headline": one line, the single most important move and why it matters,
 "bullets": 4 to 6 short bullets, each "move, level, likely driver",
 "context": 1 to 3 sentences on what this means for rates, credit, equities and FX together.

Regime read (rule-based): {regime}

Table (as of {asof}):
{table}
"""


def llm_narrative(snapshot: dict, generate) -> tuple[dict | None, dict]:
    """generate(prompt) -> str. Returns (narrative or None, audit record)."""
    prompt = PROMPT.format(regime=json.dumps(monitor.regime(snapshot)), asof=snapshot["asof"],
                           table=monitor.table_markdown(snapshot))
    audit: dict = {"writer": "llm", "accepted": False}
    try:
        raw = generate(prompt)
    except Exception as e:  # no key, quota, network: fall back quietly
        audit["error"] = str(e)[:300]
        return None, audit
    if not raw:
        audit["error"] = "empty response"
        return None, audit
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        data = json.loads(m.group(0) if m else raw)
        text = " ".join([data.get("headline", "")] + list(data.get("bullets", [])) + [data.get("context", "")])
    except Exception:
        audit["error"] = "response was not valid JSON"
        return None, audit
    ok, unknown = check_grounding(text, snapshot)
    audit.update({"accepted": ok, "unknown_numbers": unknown})
    if not ok:
        return None, audit
    ctx = data.get("context", "")
    return {"writer": "llm", "headline": data.get("headline", "").strip(),
            "bullets": [b.strip() for b in data.get("bullets", []) if b.strip()],
            "context": [ctx] if isinstance(ctx, str) else list(ctx)}, audit


def write(snapshot: dict, quality_line: str, generate=None) -> tuple[dict, dict]:
    """Best available narrative plus an audit record of what happened."""
    base = template_narrative(snapshot, quality_line)
    if generate is None:
        return base, {"writer": "template", "reason": "no LLM configured"}
    n, audit = llm_narrative(snapshot, generate)
    if n is None:
        return base, audit
    n["quality"] = quality_line
    return n, audit
