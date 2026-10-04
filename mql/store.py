"""History store: one CSV per series in data/history/, plus an optional DuckDB file for SQL.

CSV keeps the store readable on GitHub and diff-friendly. DuckDB (local only, git-ignored)
gives you SQL over the same data:  python -m mql.store --duckdb
"""
from __future__ import annotations

import argparse
from datetime import timedelta
from pathlib import Path

import pandas as pd

from . import config


def path_for(series_id: str, root: Path | None = None) -> Path:
    return (root or config.HISTORY) / f"{series_id}.csv"


def load_series(series_id: str, root: Path | None = None) -> pd.Series:
    p = path_for(series_id, root)
    if not p.exists():
        return pd.Series(dtype=float, name=series_id)
    df = pd.read_csv(p, parse_dates=["date"])
    s = df.set_index("date")["value"].astype(float)
    s.name = series_id
    return s


def merge(old: pd.Series, new: pd.Series) -> pd.Series:
    """Combine stored and fresh observations; fresh values win on overlapping dates (revisions)."""
    if old.empty:
        out = new.copy()
    elif new.empty:
        out = old.copy()
    else:
        out = pd.concat([old[~old.index.isin(new.index)], new])
    out = out[~out.index.duplicated(keep="last")].sort_index().dropna()
    out.name = new.name if new.name is not None else old.name
    return out


def save_series(s: pd.Series, root: Path | None = None) -> Path:
    p = path_for(str(s.name), root)
    p.parent.mkdir(parents=True, exist_ok=True)
    df = s.rename("value").to_frame()
    df.index.name = "date"
    df.to_csv(p, date_format="%Y-%m-%d", float_format="%.6g")
    return p


def fetch_starts(watchlist, overlap_days: int = 10, root: Path | None = None) -> dict[str, str]:
    """First date to request for each series: full history if new, else the stored tail minus an overlap."""
    starts = {}
    for s in watchlist.downloadable():
        cur = load_series(s.id, root)
        if cur.empty:
            starts[s.id] = watchlist.history_start
        else:
            starts[s.id] = (cur.index.max() - timedelta(days=overlap_days)).strftime("%Y-%m-%d")
    return starts


def compute_derived(panel: pd.DataFrame, watchlist) -> pd.DataFrame:
    """Add derived series (a - b) on dates where both legs exist."""
    out = panel.copy()
    for d in watchlist.derived():
        if d.a in out and d.b in out:
            out[d.id] = out[d.a] - out[d.b]
    return out


def load_panel(watchlist, root: Path | None = None, with_derived: bool = True) -> pd.DataFrame:
    cols = {s.id: load_series(s.id, root) for s in watchlist.downloadable()}
    panel = pd.DataFrame({k: v for k, v in cols.items() if not v.empty})
    panel = panel.sort_index()
    return compute_derived(panel, watchlist) if with_derived else panel


def to_duckdb(watchlist, db_path: Path | None = None, root: Path | None = None) -> Path:
    import duckdb  # optional dependency

    db_path = db_path or (config.DATA / "mql.duckdb")
    panel = load_panel(watchlist, root)
    long = panel.reset_index().melt(id_vars="date", var_name="series_id", value_name="value").dropna()
    meta = pd.DataFrame([{"series_id": s.id, "name": s.name, "source": s.source, "code": s.code,
                          "unit": s.unit, "grp": s.group} for s in watchlist.series])
    con = duckdb.connect(str(db_path))
    con.execute("CREATE OR REPLACE TABLE obs AS SELECT * FROM long")
    con.execute("CREATE OR REPLACE TABLE series AS SELECT * FROM meta")
    # a table, not a view: DuckDB cannot build a PIVOT view whose columns come from the data
    con.execute("CREATE OR REPLACE TABLE wide AS PIVOT obs ON series_id USING first(value) GROUP BY date ORDER BY date")
    con.close()
    return db_path


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="History store utilities")
    ap.add_argument("--duckdb", action="store_true", help="build data/mql.duckdb for SQL practice")
    args = ap.parse_args()
    wl = config.load_watchlist()
    if args.duckdb:
        print(f"Wrote {to_duckdb(wl)}. Try: duckdb data/mql.duckdb  then  SELECT * FROM series;")
