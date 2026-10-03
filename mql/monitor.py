"""The daily snapshot: what moved, by how much, and how unusual it is.

Conventions
- pct and spread series: levels in percent; changes in basis points (bp)
- price series: changes in percent
- level series (VIX, MOVE): changes in points
- z_1y: where today's level sits versus the last year (standard deviations from the mean)
- move_z: today's move versus a normal day over the last year
"""
from __future__ import annotations

import math
from datetime import date

import pandas as pd


def _value_on_or_before(s: pd.Series, when: pd.Timestamp) -> float | None:
    sub = s[s.index <= when]
    return None if sub.empty else float(sub.iloc[-1])


def change(unit: str, new: float | None, old: float | None) -> float | None:
    if new is None or old is None or (isinstance(old, float) and math.isnan(old)):
        return None
    if unit in ("pct", "spread"):
        return round((new - old) * 100, 1)  # bp
    if unit == "price":
        return round((new / old - 1) * 100, 2) if old else None  # %
    return round(new - old, 2)  # points


def series_stats(s: pd.Series, unit: str) -> dict | None:
    s = s.dropna()
    if len(s) < 2:
        return None
    last_date = s.index[-1]
    last = float(s.iloc[-1])
    prev = float(s.iloc[-2])
    wk = _value_on_or_before(s, last_date - pd.Timedelta(days=7))
    mo = _value_on_or_before(s, last_date - pd.DateOffset(months=1))
    yr = s[s.index > last_date - pd.Timedelta(days=365)]
    z = None
    if len(yr) > 20 and yr.std() > 0:
        z = round(float((last - yr.mean()) / yr.std()), 2)
    move_z = None
    if len(yr) > 40:
        daily = (yr.pct_change() * 100 if unit == "price" else yr.diff() * (100 if unit in ("pct", "spread") else 1)).dropna()
        sd = daily.iloc[:-1].std()
        c1 = change(unit, last, prev)
        if sd and sd > 0 and c1 is not None:
            move_z = round(float(c1 / sd), 2)
    return {
        "last": round(last, 4), "date": last_date.strftime("%Y-%m-%d"),
        "chg_1d": change(unit, last, prev), "chg_1w": change(unit, last, wk), "chg_1m": change(unit, last, mo),
        "z_1y": z, "move_z": move_z,
        "hi_1y": round(float(yr.max()), 4) if len(yr) else None, "lo_1y": round(float(yr.min()), 4) if len(yr) else None,
    }


def build_snapshot(panel: pd.DataFrame, watchlist, asof: date) -> dict:
    rows = []
    for s in watchlist.series:
        if not s.show or s.id not in panel:
            continue
        st = series_stats(panel[s.id], s.unit)
        if st is None:
            continue
        rows.append({"id": s.id, "name": s.name, "group": s.group, "unit": s.unit, **st})
    return {"asof": str(asof), "units": {"pct": "level %, change bp", "spread": "level and change bp",
                                         "price": "change %", "level": "change points"},
            "series": rows}


# ---------------------------------------------------------------- formatting
def fmt_level(unit: str, v: float | None) -> str:
    if v is None:
        return "–"
    if unit == "pct":
        return f"{v:.2f}%"
    if unit == "spread":
        return f"{v * 100:.0f} bp"
    if unit == "price":
        return f"{v:,.4f}" if abs(v) < 10 else f"{v:,.2f}" if abs(v) < 1000 else f"{v:,.0f}"
    return f"{v:.2f}"


def fmt_change(unit: str, c: float | None) -> str:
    if c is None:
        return "–"
    if unit in ("pct", "spread"):
        return f"{c:+.0f} bp" if abs(c) >= 1 or c == 0 else f"{c:+.1f} bp"
    if unit == "price":
        return f"{c:+.2f}%"
    return f"{c:+.2f}"


def top_movers(snapshot: dict, n: int = 6, max_age_days: int = 4) -> list[dict]:
    """Largest moves relative to normal, among series updated recently."""
    asof = pd.Timestamp(snapshot["asof"])
    fresh = [r for r in snapshot["series"]
             if r.get("move_z") is not None and (asof - pd.Timestamp(r["date"])).days <= max_age_days]
    return sorted(fresh, key=lambda r: abs(r["move_z"]), reverse=True)[:n]


def table_markdown(snapshot: dict, groups: list[str] | None = None) -> str:
    order = groups or ["rates_us", "rates_uk", "rates_eur", "inflation", "credit",
                       "equity", "vol", "fx", "commodities", "india"]
    labels = {"rates_us": "US rates", "rates_uk": "UK rates", "rates_eur": "Euro rates",
              "inflation": "Inflation", "credit": "Credit", "equity": "Equities", "vol": "Volatility",
              "fx": "FX", "commodities": "Commodities", "india": "India"}
    lines = ["| | Level | 1d | 1w | 1m | z (1y) | As of |", "|---|---:|---:|---:|---:|---:|---|"]
    for g in order:
        rows = [r for r in snapshot["series"] if r["group"] == g]
        if not rows:
            continue
        lines.append(f"| **{labels.get(g, g)}** | | | | | | |")
        for r in rows:
            z = "–" if r["z_1y"] is None else f"{r['z_1y']:+.1f}"
            lines.append(f"| {r['name']} | {fmt_level(r['unit'], r['last'])} | {fmt_change(r['unit'], r['chg_1d'])} | "
                         f"{fmt_change(r['unit'], r['chg_1w'])} | {fmt_change(r['unit'], r['chg_1m'])} | {z} | {r['date']} |")
    return "\n".join(lines)


def regime(snapshot: dict) -> dict:
    """A deliberately simple, explainable read of the backdrop. Not a signal to trade on."""
    by = {r["id"]: r for r in snapshot["series"]}
    out = {}
    c = by.get("US_2S10S")
    if c:
        out["curve"] = "inverted" if c["last"] < 0 else "flat" if c["last"] < 0.25 else "positively sloped"
    hy = by.get("US_HY_OAS")
    if hy and hy.get("z_1y") is not None:
        out["credit"] = "spreads wide versus the past year" if hy["z_1y"] > 1 else "spreads tight versus the past year" if hy["z_1y"] < -1 else "spreads near their one-year average"
    vix = by.get("VIX")
    if vix:
        out["equity_vol"] = "stressed" if vix["last"] >= 25 else "calm" if vix["last"] < 15 else "normal"
    be = by.get("US_10Y_BE")
    if be:
        out["inflation_pricing"] = "above 2.5%" if be["last"] > 2.5 else "below 2%" if be["last"] < 2 else "between 2% and 2.5%"
    return out


def numbers_in_snapshot(snapshot: dict) -> set[float]:
    """Every number a narrative is allowed to quote, in the units it would be written in."""
    allowed: set[float] = set()
    for r in snapshot["series"]:
        u = r["unit"]
        for k in ("last", "hi_1y", "lo_1y"):
            v = r.get(k)
            if v is None:
                continue
            allowed.add(round(v, 2))
            if u == "spread":
                allowed.add(round(v * 100, 0))
            if u == "price":
                allowed.add(round(v, 0))
                allowed.add(round(v, 1))
        for k in ("chg_1d", "chg_1w", "chg_1m", "z_1y", "move_z"):
            v = r.get(k)
            if v is None:
                continue
            for x in (v, abs(v)):
                allowed.add(round(x, 2))
                allowed.add(round(x, 1))
                allowed.add(round(x, 0))
    return allowed


def finite(x) -> bool:
    return x is not None and not (isinstance(x, float) and (math.isnan(x) or math.isinf(x)))


__all__ = ["build_snapshot", "series_stats", "change", "fmt_level", "fmt_change", "top_movers",
           "table_markdown", "regime", "numbers_in_snapshot"]
