"""Data-quality checks. A PM trusts a number only after it passes these.

Each series gets status ok / warn / fail with plain-English issues:
- fail: download error, no data, or values outside a sane range
- warn: stale (older than its normal update lag), a suspicious jump, or a recent gap
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

SANE = {"pct": (-5.0, 40.0), "spread": (-10.0, 30.0), "level": (0.0, 500.0)}


def infer_frequency(s: pd.Series) -> str:
    if len(s) < 3:
        return "unknown"
    gaps = s.index.to_series().diff().dt.days.dropna().tail(30)
    med = gaps.median()
    if med <= 4:
        return "daily"
    if med <= 10:
        return "weekly"
    return "monthly"


def business_days_between(a: date, b: date) -> int:
    return int(np.busday_count(a, b)) if b > a else 0


def check_series(s: pd.Series, unit: str, today: date, error: str | None = None) -> dict:
    sid = str(s.name)
    issues: list[str] = []
    status = "ok"
    if error:
        return {"id": sid, "status": "fail", "issues": [f"download failed: {error}"], "last_date": None}
    if s.empty:
        return {"id": sid, "status": "fail", "issues": ["no data stored"], "last_date": None}

    last_date = s.index.max().date()
    freq = infer_frequency(s)
    lag = business_days_between(last_date, today)
    limit = {"daily": 4, "weekly": 10, "monthly": 100}.get(freq, 10)  # monthly OECD series lag ~3 months
    if lag > limit:
        issues.append(f"stale: last value {last_date} is {lag} business days old ({freq} series)")
        status = "warn"

    lo, hi = SANE.get(unit, (0.0, float("inf")))
    if unit == "price":
        lo, hi = 0.0, float("inf")
    bad = s[(s < lo) | (s > hi)]
    if not bad.empty:
        issues.append(f"{len(bad)} values outside the sane range {lo}..{hi} (latest {bad.index.max().date()})")
        status = "fail"

    recent = s[s.index >= s.index.max() - pd.Timedelta(days=365)]
    if freq == "daily" and len(recent) > 60:
        chg = recent.pct_change() if unit == "price" else recent.diff()
        chg = chg.dropna()
        mad = (chg - chg.median()).abs().median()
        scale = 1.4826 * mad if mad > 0 else chg.std()
        if scale and scale > 0:
            last_move = chg.iloc[-1]
            if abs(last_move) > 8 * scale:
                issues.append(f"latest move is {abs(last_move) / scale:.0f}x a normal day: check the source before using it")
                status = "fail" if status == "fail" else "warn"
        window = recent[recent.index >= recent.index.max() - pd.Timedelta(days=90)]
        if len(window) > 2:
            biggest_gap = window.index.to_series().diff().dt.days.max()
            if biggest_gap and biggest_gap > 14:
                issues.append(f"gap of {int(biggest_gap)} days in the last 90 days")
                status = "fail" if status == "fail" else "warn"

    return {"id": sid, "status": status, "issues": issues, "last_date": str(last_date), "frequency": freq}


def run_checks(panel: pd.DataFrame, watchlist, today: date, errors: dict[str, str] | None = None) -> dict:
    errors = errors or {}
    results = []
    for s in watchlist.series:
        col = panel[s.id].dropna() if s.id in panel else pd.Series(dtype=float, name=s.id)
        col.name = s.id
        results.append(check_series(col, s.unit, today, errors.get(s.id)))
    counts = {k: sum(1 for r in results if r["status"] == k) for k in ("ok", "warn", "fail")}
    return {"asof": str(today), "counts": counts, "series": results}


def summary_line(report: dict) -> str:
    c = report["counts"]
    flagged = [r["id"] for r in report["series"] if r["status"] != "ok"]
    tail = f" Check: {', '.join(flagged[:8])}{'…' if len(flagged) > 8 else ''}." if flagged else ""
    return f"Data quality: {c['ok']} ok, {c['warn']} warnings, {c['fail']} failures.{tail}"
