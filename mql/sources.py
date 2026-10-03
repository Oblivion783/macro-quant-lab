"""Downloaders for free public data sources.

Every fetcher returns a float pandas Series indexed by date (no time zone) and named
after the watchlist id. Parsing is kept separate from downloading so it can be tested
without a network connection.

Sources (all free, no API key):
- FRED (St. Louis Fed) graph CSV endpoint
- Bank of England Interactive Statistical Database (IADB) CSV export
- ECB Data Portal SDMX REST API (CSV)
- Yahoo Finance chart API (falls back to the yfinance package if installed)
"""
from __future__ import annotations

import io
import logging
import time
from datetime import date, datetime, timezone

import pandas as pd
import requests

log = logging.getLogger(__name__)

UA = {"User-Agent": "Mozilla/5.0 (macro-quant-lab; personal research; +https://github.com/Oblivion783/macro-quant-lab)"}
TIMEOUT = 30


def _get(url: str, params: dict | None = None, retries: int = 3) -> requests.Response:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=TIMEOUT)
            if r.status_code == 200:
                return r
            last = RuntimeError(f"HTTP {r.status_code} from {r.url}")
        except requests.RequestException as e:  # network hiccup
            last = e
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Download failed: {url}: {last}")


def _clean(s: pd.Series, name: str) -> pd.Series:
    s = pd.to_numeric(s, errors="coerce")
    s.index = pd.to_datetime(s.index).normalize()
    if getattr(s.index, "tz", None) is not None:
        s.index = s.index.tz_localize(None)
    s = s[~s.index.duplicated(keep="last")].sort_index().dropna()
    s.name = name
    s.index.name = "date"
    return s.astype(float)


# ---------------------------------------------------------------- FRED
def parse_fred_csv(text: str, name: str) -> pd.Series:
    df = pd.read_csv(io.StringIO(text), na_values=["."])
    date_col = df.columns[0]  # "observation_date" (current) or "DATE" (older)
    return _clean(df.set_index(date_col).iloc[:, 0], name)


def fetch_fred(code: str, name: str, start: str) -> pd.Series:
    r = _get("https://fred.stlouisfed.org/graph/fredgraph.csv", {"id": code, "cosd": start})
    return parse_fred_csv(r.text, name)


# ---------------------------------------------------------------- Bank of England
def parse_boe_csv(text: str) -> pd.DataFrame:
    df = pd.read_csv(io.StringIO(text))
    df.columns = [c.strip() for c in df.columns]
    df["DATE"] = pd.to_datetime(df["DATE"], format="%d %b %Y", errors="coerce")
    df = df.dropna(subset=["DATE"]).set_index("DATE")
    return df.apply(pd.to_numeric, errors="coerce")


def fetch_boe(codes: list[str], start: str) -> pd.DataFrame:
    d = datetime.strptime(start, "%Y-%m-%d").strftime("%d/%b/%Y")
    params = {"csv.x": "yes", "Datefrom": d, "Dateto": "now", "SeriesCodes": ",".join(codes),
              "CSVF": "TN", "UsingCodes": "Y", "VPD": "Y", "VFD": "N"}
    r = _get("https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp", params)
    if "DATE" not in r.text[:200]:
        raise RuntimeError("Bank of England returned a page instead of CSV (check the series codes)")
    return parse_boe_csv(r.text)


# ---------------------------------------------------------------- ECB
def parse_ecb_csv(text: str, name: str) -> pd.Series:
    df = pd.read_csv(io.StringIO(text))
    return _clean(df.set_index("TIME_PERIOD")["OBS_VALUE"], name)


def fetch_ecb(code: str, name: str, start: str) -> pd.Series:
    flow, key = code.split("/", 1)
    r = _get(f"https://data-api.ecb.europa.eu/service/data/{flow}/{key}",
             {"format": "csvdata", "startPeriod": start})
    return parse_ecb_csv(r.text, name)


# ---------------------------------------------------------------- Yahoo Finance
def parse_yahoo_chart(payload: dict, name: str) -> pd.Series:
    res = payload["chart"]["result"][0]
    ts = res.get("timestamp") or []
    closes = res["indicators"]["quote"][0].get("close") or []
    gmtoffset = res.get("meta", {}).get("gmtoffset", 0)
    idx = [datetime.fromtimestamp(t + gmtoffset, tz=timezone.utc).date() for t in ts]
    return _clean(pd.Series(closes, index=pd.to_datetime(idx)), name)


def fetch_yahoo(code: str, name: str, start: str) -> pd.Series:
    p1 = int(datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
    p2 = int(time.time()) + 86400
    try:
        r = _get(f"https://query1.finance.yahoo.com/v8/finance/chart/{code}",
                 {"period1": p1, "period2": p2, "interval": "1d", "events": "history"})
        return parse_yahoo_chart(r.json(), name)
    except Exception as first:  # fall back to yfinance if it is installed
        try:
            import yfinance as yf  # type: ignore
        except ImportError:
            raise first
        hist = yf.Ticker(code).history(start=start, auto_adjust=False)
        if hist.empty:
            raise first
        return _clean(hist["Close"], name)


# ---------------------------------------------------------------- dispatcher
def fetch_all(watchlist, start_for: dict[str, str]) -> tuple[dict[str, pd.Series], dict[str, str]]:
    """Download every non-derived series. Returns (data, errors).

    start_for maps series id -> first date to request (so daily runs only fetch the tail).
    A failure in one series never stops the others; it is recorded in errors.
    """
    out: dict[str, pd.Series] = {}
    errors: dict[str, str] = {}
    boe = [s for s in watchlist.downloadable() if s.source == "boe"]
    if boe:
        start = min(start_for.get(s.id, watchlist.history_start) for s in boe)
        try:
            df = fetch_boe([s.code for s in boe], start)
            for s in boe:
                if s.code in df.columns:
                    out[s.id] = _clean(df[s.code], s.id)
                else:
                    errors[s.id] = f"BoE code {s.code} not in response"
        except Exception as e:
            for s in boe:
                errors[s.id] = str(e)
    for s in watchlist.downloadable():
        if s.source == "boe":
            continue
        start = start_for.get(s.id, watchlist.history_start)
        try:
            if s.source == "fred":
                out[s.id] = fetch_fred(s.code, s.id, start)
            elif s.source == "ecb":
                out[s.id] = fetch_ecb(s.code, s.id, start)
            elif s.source == "yahoo":
                out[s.id] = fetch_yahoo(s.code, s.id, start)
            if s.id in out and out[s.id].empty:
                errors[s.id] = "no observations returned"
        except Exception as e:
            errors[s.id] = str(e)[:300]
        time.sleep(0.3)  # be polite to free endpoints
    return out, errors


def today() -> date:
    return datetime.now(timezone.utc).date()
