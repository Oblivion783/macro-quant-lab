"""Synthetic data for tests (no network)."""
import numpy as np
import pandas as pd

from mql.config import Series, Watchlist


def bdays(n=400, end="2026-10-02"):
    return pd.bdate_range(end=end, periods=n)


def random_walk(n=400, start=4.0, step=0.05, seed=1, end="2026-10-02", name="X"):
    rng = np.random.default_rng(seed)
    s = pd.Series(start + np.cumsum(rng.normal(0, step, n)), index=bdays(n, end), name=name)
    return s


def mini_watchlist():
    return Watchlist(series=[
        Series("UST_2Y", "fred", "DGS2", "US 2y Treasury", "pct", "rates_us"),
        Series("UST_10Y", "fred", "DGS10", "US 10y Treasury", "pct", "rates_us"),
        Series("SPX", "yahoo", "^GSPC", "S&P 500", "price", "equity"),
        Series("VIX", "yahoo", "^VIX", "VIX", "level", "vol"),
        Series("US_HY_OAS", "fred", "BAMLH0A0HYM2", "US high-yield spread", "spread", "credit"),
        Series("US_2S10S", "derived", "UST_10Y-UST_2Y", "US 2s10s curve", "spread", "rates_us", a="UST_10Y", b="UST_2Y"),
    ])


def mini_panel():
    p = pd.DataFrame({
        "UST_2Y": random_walk(start=3.6, seed=1),
        "UST_10Y": random_walk(start=4.1, seed=2),
        "SPX": random_walk(start=6000, step=30, seed=3),
        "VIX": random_walk(start=16, step=0.5, seed=4).clip(lower=9),
        "US_HY_OAS": random_walk(start=3.0, step=0.03, seed=5),
    })
    p["US_2S10S"] = p["UST_10Y"] - p["UST_2Y"]
    return p
