"""Paths and configuration loading."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(os.environ.get("MQL_ROOT", Path(__file__).resolve().parents[1]))
CONFIG = ROOT / "config"
DATA = ROOT / "data"
HISTORY = DATA / "history"
LATEST = DATA / "latest"
STATEMENTS = DATA / "statements"
PORTFOLIO_DATA = DATA / "portfolio"
DOCS = ROOT / "docs"
CHARTS = DOCS / "assets" / "charts"

SITE_URL = os.environ.get("MQL_SITE_URL", "https://oblivion783.github.io/macro-quant-lab")


@dataclass
class Series:
    id: str
    source: str
    code: str
    name: str
    unit: str
    group: str
    show: bool = True
    a: str | None = None  # derived: a - b
    b: str | None = None

    @property
    def is_derived(self) -> bool:
        return self.source == "derived"


@dataclass
class Watchlist:
    series: list[Series] = field(default_factory=list)
    history_start: str = "2018-01-01"

    def by_id(self) -> dict[str, Series]:
        return {s.id: s for s in self.series}

    def downloadable(self) -> list[Series]:
        return [s for s in self.series if not s.is_derived]

    def derived(self) -> list[Series]:
        return [s for s in self.series if s.is_derived]


VALID_UNITS = {"pct", "spread", "price", "level"}
VALID_SOURCES = {"fred", "boe", "ecb", "yahoo", "derived"}


def load_yaml(name: str) -> dict:
    with open(CONFIG / name, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_watchlist(path: Path | None = None) -> Watchlist:
    if path:
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    else:
        raw = load_yaml("series.yaml")
    items: list[Series] = []
    for s in raw.get("series", []):
        items.append(Series(id=s["id"], source=s["source"], code=str(s["code"]), name=s["name"],
                            unit=s["unit"], group=s["group"], show=s.get("show", True)))
    for d in raw.get("derived", []):
        items.append(Series(id=d["id"], source="derived", code=f"{d['a']}-{d['b']}", name=d["name"],
                            unit=d["unit"], group=d["group"], show=d.get("show", True), a=d["a"], b=d["b"]))
    ids = [s.id for s in items]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"Duplicate series ids in watchlist: {sorted(dupes)}")
    for s in items:
        if s.unit not in VALID_UNITS:
            raise ValueError(f"{s.id}: unit must be one of {sorted(VALID_UNITS)}")
        if s.source not in VALID_SOURCES:
            raise ValueError(f"{s.id}: source must be one of {sorted(VALID_SOURCES)}")
        if s.is_derived and (s.a not in ids or s.b not in ids):
            raise ValueError(f"{s.id}: derived from unknown series {s.a} or {s.b}")
    return Watchlist(series=items, history_start=str(raw.get("history_start", "2018-01-01")))
