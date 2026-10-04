"""Model Portfolio Lab (Project 3): paper NAV, risk metrics, Brinson-Fachler attribution, factsheet.

Files
  config/portfolio.yaml            sleeves, ETF proxies, strategic weights, benchmark, costs
  data/portfolio/decisions.csv     date,sleeve,target_weight,rationale  (one full target vector per date)
  data/portfolio/prices.csv        adjusted closes (total-return proxies), written by --update-prices
  data/portfolio/nav.csv           daily NAV and weights, portfolio and benchmark
  docs/portfolio/factsheet-YYYY-MM.md

Usage
  python -m mql.portfolio --update-prices
  python -m mql.portfolio --run                # NAV to date (after inception)
  python -m mql.portfolio --factsheet 2027-01  # monthly factsheet
  python -m mql.portfolio --backtest 2019-01-01  # strategic mix only; never publish as a track record
"""
from __future__ import annotations

import argparse
import csv
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from . import config

TRADING_DAYS = 252


# ---------------------------------------------------------------- config and decisions
def load_cfg() -> dict:
    return config.load_yaml("portfolio.yaml")


def strategic(cfg: dict) -> dict[str, float]:
    return {s["id"]: float(s["strategic"]) for s in cfg["sleeves"]}


def validate_weights(w: dict[str, float], cfg: dict, tol: float = 1e-6) -> list[str]:
    errs = []
    ids = {s["id"] for s in cfg["sleeves"]}
    unknown = set(w) - ids
    if unknown:
        errs.append(f"unknown sleeves: {sorted(unknown)}")
    if abs(sum(w.values()) - 1) > tol:
        errs.append(f"weights sum to {sum(w.values()):.4f}, not 1")
    if any(v < -tol for v in w.values()):
        errs.append("negative weight (long-only portfolio)")
    lim = float(cfg.get("tilt_limit", 1))
    base = strategic(cfg)
    for k, v in w.items():
        if k in base and abs(v - base[k]) > lim + tol:
            errs.append(f"{k}: {v:.2%} is more than {lim:.0%} from strategic {base[k]:.2%}")
    return errs


def load_decisions(path: Path | None = None) -> list[tuple[pd.Timestamp, dict[str, float], str]]:
    path = path or (config.PORTFOLIO_DATA / "decisions.csv")
    if not path.exists():
        return []
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    by: dict[str, dict] = {}
    notes: dict[str, str] = {}
    for r in rows:
        by.setdefault(r["date"], {})[r["sleeve"]] = float(r["target_weight"])
        if r.get("rationale"):
            notes[r["date"]] = (notes.get(r["date"], "") + " " + r["rationale"]).strip()
    return [(pd.Timestamp(d), w, notes.get(d, "")) for d, w in sorted(by.items())]


# ---------------------------------------------------------------- prices
def parse_adjclose(payload: dict) -> pd.Series:
    res = payload["chart"]["result"][0]
    ts = res.get("timestamp") or []
    adj = (res["indicators"].get("adjclose") or [{}])[0].get("adjclose") or res["indicators"]["quote"][0]["close"]
    idx = pd.to_datetime(ts, unit="s").normalize()
    s = pd.Series(adj, index=idx, dtype=float).dropna()
    return s[~s.index.duplicated(keep="last")]


def update_prices(cfg: dict, start: str = "2018-01-01", out: Path | None = None) -> pd.DataFrame:
    import time as _t
    from datetime import datetime, timezone

    from .sources import _get

    out = out or (config.PORTFOLIO_DATA / "prices.csv")
    tickers = sorted({s["ticker"] for s in cfg["sleeves"]} | {b["ticker"] for b in cfg["benchmark"].values()})
    p1 = int(datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
    cols = {}
    for t in tickers:
        r = _get(f"https://query1.finance.yahoo.com/v8/finance/chart/{t}",
                 {"period1": p1, "period2": int(_t.time()) + 86400, "interval": "1d", "events": "div,splits"})
        cols[t] = parse_adjclose(r.json())
        _t.sleep(0.3)
    df = pd.DataFrame(cols).sort_index()
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, date_format="%Y-%m-%d", float_format="%.6f", index_label="date")
    return df


def load_prices(path: Path | None = None) -> pd.DataFrame:
    path = path or (config.PORTFOLIO_DATA / "prices.csv")
    return pd.read_csv(path, parse_dates=["date"], index_col="date").sort_index()


# ---------------------------------------------------------------- simulation
def _first_on_or_after(index: pd.DatetimeIndex, when: pd.Timestamp) -> pd.Timestamp | None:
    pos = index.searchsorted(when)
    return index[pos] if pos < len(index) else None


def simulate(prices: pd.DataFrame, schedule: list[tuple[pd.Timestamp, dict[str, float]]], cost_bps: float = 0.0,
             monthly: bool = True, start_nav: float = 100.0) -> pd.DataFrame:
    """Daily NAV of a long-only portfolio.

    prices: adjusted closes, columns = sleeve ids. schedule: [(date, target weights)], sorted.
    Rebalances at the close of the first trading day on/after each decision date and, if monthly,
    on the first trading day of each month (back to the latest target). Costs = traded value x bps.
    """
    if not schedule:
        raise ValueError("empty schedule")
    px = prices.ffill().dropna(how="all")
    start = _first_on_or_after(px.index, schedule[0][0])
    if start is None:
        raise ValueError("no prices on or after the first decision date")
    px = px[px.index >= start]
    sleeves = sorted({k for _, w in schedule for k in w})
    missing = [s for s in sleeves if s not in px]
    if missing:
        raise ValueError(f"no prices for {missing}")
    rets = px[sleeves].pct_change().fillna(0.0)

    targets: dict[pd.Timestamp, dict[str, float]] = {}
    for d, w in schedule:
        td = _first_on_or_after(px.index, d)
        if td is not None:
            targets[td] = {s: float(w.get(s, 0.0)) for s in sleeves}
    month_starts = set(px.index.to_series().groupby(px.index.to_period("M")).min()) if monthly else set()

    nav = start_nav
    w = np.zeros(len(sleeves))
    current_target = None
    rows = []
    for d in px.index:
        r = rets.loc[d].to_numpy()
        if w.sum() > 0:
            grown = w * (1 + r)
            nav *= grown.sum() / w.sum()
            w = grown / grown.sum()
        cost = turnover = 0.0
        if d in targets:
            current_target = targets[d]
        if current_target is not None and (d in targets or d in month_starts or w.sum() == 0):
            tgt = np.array([current_target[s] for s in sleeves])
            turnover = float(np.abs(tgt - w).sum())
            cost = nav * turnover * cost_bps / 1e4
            nav -= cost
            w = tgt.copy()
        rows.append({"date": d, "nav": nav, "cost": cost, "turnover": turnover, **{f"w_{s}": w[i] for i, s in enumerate(sleeves)}})
    return pd.DataFrame(rows).set_index("date")


def sleeve_prices(prices: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    return pd.DataFrame({s["id"]: prices[s["ticker"]] for s in cfg["sleeves"] if s["ticker"] in prices})


def benchmark_prices(prices: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    return pd.DataFrame({k: prices[b["ticker"]] for k, b in cfg["benchmark"].items() if b["ticker"] in prices})


def run(prices: pd.DataFrame, cfg: dict, decisions=None) -> tuple[pd.DataFrame, pd.DataFrame]:
    decisions = decisions if decisions is not None else load_decisions()
    inception = pd.Timestamp(cfg["inception"])
    if not decisions:
        decisions = [(inception, strategic(cfg), "Strategic weights at inception")]
    for d, w, _ in decisions:
        errs = validate_weights(w, cfg)
        if errs:
            raise ValueError(f"decision {d.date()}: {'; '.join(errs)}")
    sched = [(d, w) for d, w, _ in decisions]
    port = simulate(sleeve_prices(prices, cfg), sched, float(cfg.get("cost_bps", 0)))
    bw = {k: float(b["weight"]) for k, b in cfg["benchmark"].items()}
    bench = simulate(benchmark_prices(prices, cfg), [(sched[0][0], bw)], 0.0)
    return port, bench


# ---------------------------------------------------------------- metrics
def metrics(nav: pd.Series, bench: pd.Series | None = None, rf_daily: pd.Series | None = None) -> dict:
    r = nav.pct_change().dropna()
    n = len(r)
    if n == 0:
        return {}
    cum = float(nav.iloc[-1] / nav.iloc[0] - 1)
    ann = float((1 + cum) ** (TRADING_DAYS / n) - 1) if n >= TRADING_DAYS // 4 else None
    vol = float(r.std() * np.sqrt(TRADING_DAYS))
    ex = r - (rf_daily.reindex(r.index).fillna(0) if rf_daily is not None else 0)
    sharpe = float(ex.mean() * TRADING_DAYS / vol) if vol > 0 else None
    dd = float((nav / nav.cummax() - 1).min())
    out = {"days": n, "cum_return": cum, "ann_return": ann, "ann_vol": vol, "sharpe": sharpe, "max_drawdown": dd}
    if bench is not None:
        rb = bench.pct_change().reindex(r.index).fillna(0)
        active = r - rb
        te = float(active.std() * np.sqrt(TRADING_DAYS))
        out.update({"bench_cum_return": float(bench.reindex(nav.index).ffill().iloc[-1] / bench.reindex(nav.index).ffill().iloc[0] - 1),
                    "tracking_error": te, "info_ratio": float(active.mean() * TRADING_DAYS / te) if te > 0 else None})
    return out


# ---------------------------------------------------------------- attribution
def brinson_fachler(wp: dict, wb: dict, rp: dict, rb: dict) -> dict:
    """Single-period Brinson-Fachler by segment. Segments absent from the benchmark use rb = rp,
    so holding an off-benchmark asset class shows up as allocation. Effects sum to Rp - Rb when
    portfolio and benchmark weights each sum to 1."""
    segs = sorted(set(wp) | set(wb))
    rb_full = {s: (rb[s] if wb.get(s, 0) > 0 and s in rb else rp.get(s, 0.0)) for s in segs}
    Rb = sum(wb.get(s, 0) * rb_full[s] for s in segs)
    Rp = sum(wp.get(s, 0) * rp.get(s, 0.0) for s in segs)
    rows = {}
    for s in segs:
        dw = wp.get(s, 0) - wb.get(s, 0)
        rows[s] = {"wp": wp.get(s, 0), "wb": wb.get(s, 0), "rp": rp.get(s, 0.0), "rb": rb_full[s],
                   "allocation": dw * (rb_full[s] - Rb),
                   "selection": wb.get(s, 0) * (rp.get(s, 0.0) - rb_full[s]),
                   "interaction": dw * (rp.get(s, 0.0) - rb_full[s])}
    tot = {k: sum(v[k] for v in rows.values()) for k in ("allocation", "selection", "interaction")}
    return {"segments": rows, "total": tot, "Rp": Rp, "Rb": Rb, "active": Rp - Rb}


def period_attribution(port: pd.DataFrame, prices: pd.DataFrame, cfg: dict, start: pd.Timestamp, end: pd.Timestamp) -> dict:
    """Asset-class attribution between two dates using start-of-period weights (buy and hold)."""
    sp = sleeve_prices(prices, cfg).ffill()
    bp = benchmark_prices(prices, cfg).ffill()
    p0 = port[port.index <= start].iloc[-1]
    s0, s1 = sp[sp.index <= start].iloc[-1], sp[sp.index <= end].iloc[-1]
    sleeve_r = (s1 / s0 - 1).to_dict()
    cls = {s["id"]: s["asset_class"] for s in cfg["sleeves"]}
    wp: dict[str, float] = {}
    contrib: dict[str, float] = {}
    for sid, c in cls.items():
        w = float(p0.get(f"w_{sid}", 0.0))
        wp[c] = wp.get(c, 0) + w
        contrib[c] = contrib.get(c, 0) + w * sleeve_r.get(sid, 0.0)
    rp = {c: (contrib[c] / wp[c] if wp[c] else 0.0) for c in wp}
    b0, b1 = bp[bp.index <= start].iloc[-1], bp[bp.index <= end].iloc[-1]
    rb = (b1 / b0 - 1).to_dict()
    wb = {k: float(b["weight"]) for k, b in cfg["benchmark"].items()}
    res = brinson_fachler(wp, wb, rp, rb)
    nav0, nav1 = port["nav"][port.index <= start].iloc[-1], port["nav"][port.index <= end].iloc[-1]
    res["Rp_actual"] = float(nav1 / nav0 - 1)
    res["residual"] = res["Rp_actual"] - res["Rp"]  # intra-period rebalancing and costs
    return res


# ---------------------------------------------------------------- factsheet
def pct(x, d=2):
    return "–" if x is None else f"{x * 100:+.{d}f}%"


def factsheet(month: str, port: pd.DataFrame, bench: pd.DataFrame, prices: pd.DataFrame, cfg: dict,
              decisions=None) -> str:
    m = pd.Period(month, "M")
    idx = port.index
    in_month = idx[(idx >= m.start_time) & (idx <= m.end_time)]
    if in_month.empty:
        raise ValueError(f"no NAV in {month}")
    end = in_month[-1]
    prev = idx[idx < m.start_time]
    start = prev[-1] if len(prev) else idx[0]
    ytd_prev = idx[idx < pd.Timestamp(f"{m.year}-01-01")]
    ytd_start = ytd_prev[-1] if len(ytd_prev) else idx[0]

    def ret(nav, a, b):
        nav = nav.ffill()
        return float(nav[nav.index <= b].iloc[-1] / nav[nav.index <= a].iloc[-1] - 1)

    pn, bn = port["nav"], bench["nav"]
    mt = metrics(pn[pn.index <= end], bn[bn.index <= end])
    att = period_attribution(port, prices, cfg, start, end)
    names = {s["id"]: s["name"] for s in cfg["sleeves"]}
    base = strategic(cfg)
    ir_txt = "–" if mt.get("info_ratio") is None else format(mt["info_ratio"], ".2f")
    last = port.loc[end]
    lines = [f"# Model portfolio factsheet · {m.strftime('%B %Y')}", "",
             "*Paper portfolio for personal research. Not investment advice; no real money.*", "",
             "## Performance", "", "| | Portfolio | Benchmark (60/40) | Active |", "|---|---:|---:|---:|"]
    for label, a in (("Month", start), ("Year to date", ytd_start), ("Since inception", idx[0])):
        rp_, rb_ = ret(pn, a, end), ret(bn, a, end)
        lines.append(f"| {label} | {pct(rp_)} | {pct(rb_)} | {pct(rp_ - rb_)} |")
    lines += ["", "## Risk (since inception)", "", "| Metric | Value |", "|---|---:|",
              f"| Annualised volatility | {pct(mt.get('ann_vol'), 1).lstrip('+')} |",
              f"| Maximum drawdown | {pct(mt.get('max_drawdown'), 1)} |",
              f"| Tracking error | {pct(mt.get('tracking_error'), 1).lstrip('+')} |",
              f"| Information ratio | {ir_txt} |", "",
              "## Positioning (month end)", "", "| Sleeve | Weight | Strategic | Active |", "|---|---:|---:|---:|"]
    for sid in base:
        w = float(last.get(f"w_{sid}", 0))
        active = round((w - base[sid]) * 100, 1) + 0.0  # avoid "-0.0"
        lines.append(f"| {names[sid]} | {w:.1%} | {base[sid]:.1%} | {active:+.1f} pts |")
    lines += ["", "## Attribution by asset class (Brinson-Fachler, month)", "",
              "| Asset class | Port. weight | Bench. weight | Allocation | Selection | Interaction |", "|---|---:|---:|---:|---:|---:|"]
    for c, v in att["segments"].items():
        lines.append(f"| {c.replace('_', ' ').capitalize()} | {v['wp']:.1%} | {v['wb']:.1%} | {pct(v['allocation'])} | "
                     f"{pct(v['selection'])} | {pct(v['interaction'])} |")
    t = att["total"]
    lines.append(f"| **Total** | | | {pct(t['allocation'])} | {pct(t['selection'])} | {pct(t['interaction'])} |")
    lines += ["", f"Active return {pct(att['active'])} (buy-and-hold over the month); residual from rebalancing and "
              f"costs {pct(att['residual'])}.", "", "## Decisions this month", ""]
    dec = [d for d in (decisions or load_decisions()) if m.start_time <= d[0] <= m.end_time]
    lines += [f"- {d.date()}: {note or 'rebalance'}" for d, _, note in dec] or ["- None; monthly rebalance to target only."]
    lines += ["", "## Commentary", "", "_Write 150 words: what drove returns, what you changed and why, what would make you change your mind._", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Model Portfolio Lab")
    ap.add_argument("--update-prices", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--factsheet", metavar="YYYY-MM")
    ap.add_argument("--backtest", metavar="START")
    a = ap.parse_args()
    cfg = load_cfg()
    if a.update_prices:
        update_prices(cfg)
    if a.backtest:
        px = load_prices()
        port, bench = run(px, {**cfg, "inception": a.backtest}, [(pd.Timestamp(a.backtest), strategic(cfg), "backtest")])
        print("BACKTEST of the strategic mix only. Not a track record.")
        print({k: (round(v, 4) if isinstance(v, float) else v) for k, v in metrics(port["nav"], bench["nav"]).items()})
    if a.run or a.factsheet:
        if date.today() < date.fromisoformat(cfg["inception"]):
            print(f"Portfolio goes live on {cfg['inception']}; nothing to run yet.")
        else:
            px = load_prices()
            port, bench = run(px, cfg)
            out = port.join(bench[["nav"]].rename(columns={"nav": "bench_nav"}))
            out.to_csv(config.PORTFOLIO_DATA / "nav.csv", float_format="%.6f", date_format="%Y-%m-%d")
            if a.factsheet:
                p = config.DOCS / "portfolio" / f"factsheet-{a.factsheet}.md"
                p.write_text(factsheet(a.factsheet, port, bench, px, cfg), encoding="utf-8")
                print(p)
