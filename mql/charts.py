"""Static charts for the site and README (matplotlib, PNG).

Style rules: one y-axis per chart (small multiples when scales differ), thin 2 px lines,
at most three series per panel in a fixed colour order, a legend plus direct end labels,
recessive grid, and a source line under every chart.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
GRID = "#e4e3de"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]  # blue, orange, aqua (validated order)

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.spines.top": False,
    "axes.spines.right": False, "font.size": 10, "axes.titlesize": 12, "axes.titleweight": "bold",
    "axes.titlecolor": INK, "legend.frameon": False, "lines.linewidth": 2,
})


def _finish(fig, ax, title: str, subtitle: str, source: str, path: Path) -> Path:
    ax.set_title(title, loc="left", pad=22)
    ax.text(0, 1.02, subtitle, transform=ax.transAxes, color=INK2, fontsize=9, va="bottom")
    fig.text(0.01, 0.01, source, color=INK2, fontsize=8)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def _place_end_labels(ax, items: list[tuple]) -> None:
    """items: (x, y, text, color). Labels sit right of each line's last point, nudged apart so they never overlap."""
    if not items:
        return
    lo, hi = ax.get_ylim()
    height_pt = ax.get_window_extent().height * 72 / ax.figure.dpi
    pt_per_unit = height_pt / (hi - lo) if hi > lo else 1.0
    min_gap_pt = 11.0
    items = sorted(items, key=lambda t: t[1])
    pos = [t[1] * pt_per_unit for t in items]
    for k in range(1, len(pos)):
        pos[k] = max(pos[k], pos[k - 1] + min_gap_pt)
    for (x, y, text, color), p_lab in zip(items, pos):
        ax.plot([x], [y], marker="o", markersize=4, color=color)
        ax.annotate(text, xy=(x, y), xytext=(6, p_lab - y * pt_per_unit), textcoords="offset points",
                    color=INK, fontsize=8.5, va="center", ha="left", annotation_clip=False)


def lines(panel: pd.DataFrame, ids: list[str], labels: list[str], title: str, ylabel: str, path: Path,
          days: int = 365, scale: float = 1.0, index_to_100: bool = False, fmt: str = "{:.2f}",
          source: str = "Source: FRED, Bank of England, ECB, Yahoo Finance; Macro Quant Lab") -> Path | None:
    ids = [i for i in ids if i in panel and panel[i].dropna().size > 5][:3]
    if not ids:
        return None
    end = max(panel[i].dropna().index.max() for i in ids)
    start = end - pd.Timedelta(days=days)
    fig, ax = plt.subplots(figsize=(8, 4.2))
    ends = []
    for k, (i, lab) in enumerate(zip(ids, labels)):
        s = panel[i].dropna()
        s = s[s.index >= start] * scale
        if index_to_100 and not s.empty:
            s = s / s.iloc[0] * 100
        ax.plot(s.index, s.values, color=SERIES[k], label=lab)
        if not s.empty:
            ends.append((s.index[-1], float(s.iloc[-1]), f"{lab} {fmt.format(s.iloc[-1])}", SERIES[k]))
    ax.margins(x=0.12)
    _place_end_labels(ax, ends)
    ax.set_ylabel(ylabel)
    ax.legend(loc="lower right", bbox_to_anchor=(1.0, 1.0), fontsize=8.5, ncol=len(ids), borderaxespad=0.2)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    ax.margins(x=0.12)
    return _finish(fig, ax, title, f"Last {days // 30} months to {end:%d %b %Y}", source, path)


def ust_curve(panel: pd.DataFrame, path: Path) -> Path | None:
    tenors = [("UST_1M", 1 / 12), ("UST_3M", 0.25), ("UST_6M", 0.5), ("UST_1Y", 1), ("UST_2Y", 2), ("UST_3Y", 3),
              ("UST_5Y", 5), ("UST_7Y", 7), ("UST_10Y", 10), ("UST_20Y", 20), ("UST_30Y", 30)]
    have = [(i, t) for i, t in tenors if i in panel and panel[i].dropna().size]
    if len(have) < 5:
        return None
    sub = panel[[i for i, _ in have]].dropna(how="all").ffill()
    end = sub.index.max()
    snaps = [("Today", end), ("1 month ago", end - pd.DateOffset(months=1)), ("1 year ago", end - pd.DateOffset(years=1))]
    fig, ax = plt.subplots(figsize=(8, 4.2))
    for k, (lab, when) in enumerate(snaps):
        row = sub[sub.index <= when]
        if row.empty:
            continue
        r = row.iloc[-1]
        xs = [t for _, t in have]
        ys = [r[i] for i, _ in have]
        ax.plot(xs, ys, color=SERIES[k], marker="o", markersize=3.5, label=f"{lab} ({row.index[-1]:%d %b %Y})")
    ax.set_xscale("log")
    ax.set_xticks([t for _, t in have])
    ax.set_xticklabels(["1m", "3m", "6m", "1y", "2y", "3y", "5y", "7y", "10y", "20y", "30y"][: len(have)]
                       if len(have) == 11 else [i.split("_")[1].lower() for i, _ in have])
    ax.minorticks_off()
    ax.set_ylabel("Yield, %")
    ax.legend(loc="best", fontsize=8.5)
    return _finish(fig, ax, "US Treasury curve", f"Constant-maturity yields to {end:%d %b %Y}",
                   "Source: US Treasury via FRED; Macro Quant Lab", path)


def small_multiples(panel: pd.DataFrame, ids: list[str], labels: list[str], title: str, ylabel: str, path: Path,
                    days: int = 365, scale: float = 1.0, fmt: str = "{:.0f}") -> Path | None:
    ids_l = [(i, l) for i, l in zip(ids, labels) if i in panel and panel[i].dropna().size > 5]
    if not ids_l:
        return None
    fig, axes = plt.subplots(1, len(ids_l), figsize=(8, 3.8), squeeze=False)
    end = max(panel[i].dropna().index.max() for i, _ in ids_l)
    for ax, (i, lab) in zip(axes[0], ids_l):
        s = panel[i].dropna()
        s = s[s.index >= end - pd.Timedelta(days=days)] * scale
        ax.plot(s.index, s.values, color=SERIES[0])
        ax.set_title(lab, loc="left", fontsize=10)
        ax.set_ylabel(ylabel)
        ax.annotate(fmt.format(s.iloc[-1]), xy=(s.index[-1], s.iloc[-1]), xytext=(4, 0), textcoords="offset points",
                    fontsize=8.5, color=INK, va="center")
        ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=(1, 4, 7, 10)))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
        ax.tick_params(axis="x", labelsize=8)
        ax.margins(x=0.1)
    fig.suptitle(title, x=0.01, ha="left", fontweight="bold", color=INK)
    fig.text(0.01, 0.01, "Source: ICE BofA via FRED; Macro Quant Lab", color=INK2, fontsize=8)
    fig.tight_layout(rect=(0, 0.03, 1, 0.97))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def build_all(panel: pd.DataFrame, out_dir: Path) -> dict[str, str]:
    made = {}
    jobs = {
        "ust_curve": lambda p: ust_curve(panel, p),
        "rates_10y": lambda p: lines(panel, ["UST_10Y", "UK_10Y", "EUR_10Y"], ["US", "UK", "Euro AAA"],
                                      "10-year government yields", "Yield, %", p),
        "curves": lambda p: lines(panel, ["US_2S10S", "UK_5S20S", "EUR_2S10S"], ["US 2s10s", "UK 5s20s", "Euro 2s10s"],
                                   "Curve slopes", "Basis points", p, scale=100, fmt="{:.0f}"),
        "inflation": lambda p: lines(panel, ["US_10Y_BE", "US_5Y5Y", "UK_10Y_BE"], ["US 10y BE", "US 5y5y", "UK 10y"],
                                      "Market-implied inflation", "Percent", p),
        "credit": lambda p: small_multiples(panel, ["US_IG_OAS", "US_HY_OAS"], ["US investment grade", "US high yield"],
                                            "Credit spreads (option-adjusted)", "Basis points", p, scale=100),
        "equities": lambda p: lines(panel, ["SPX", "SX5E", "NIFTY"], ["S&P 500", "Euro Stoxx 50", "Nifty 50"],
                                     "Equities, indexed to 100", "Index", p, index_to_100=True, fmt="{:.0f}"),
        "fx": lambda p: lines(panel, ["DXY", "USDINR", "EURUSD"], ["Dollar index", "USD/INR", "EUR/USD"],
                               "FX, indexed to 100", "Index", p, index_to_100=True, fmt="{:.1f}"),
    }
    for name, fn in jobs.items():
        try:
            p = fn(out_dir / f"{name}.png")
            if p:
                made[name] = str(p)
        except Exception as e:  # a broken chart must never stop the daily run
            made[name] = f"error: {e}"
    return made
