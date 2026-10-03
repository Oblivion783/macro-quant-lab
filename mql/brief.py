"""Render the daily brief into the site (docs/), the archive and the README."""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from . import config, monitor

DISCLAIMER = ("*Personal research on public data. Not investment advice. Views are my own and not those of any "
              "employer. Numbers can be wrong; check the source before relying on them.*")

CHART_ORDER = [("ust_curve", "US Treasury curve"), ("rates_10y", "10-year yields"), ("curves", "Curve slopes"),
               ("inflation", "Market-implied inflation"), ("credit", "Credit spreads"),
               ("equities", "Equities"), ("fx", "FX"), ("india", "India")]


def brief_markdown(day: date, narrative: dict, snapshot: dict, charts_rel: str | None = "assets/charts") -> str:
    """charts_rel=None leaves the chart out (archive pages: charts always show the latest data)."""
    out = [f"# Daily Macro Desk · {day:%a %d %b %Y}", "", f"## {narrative['headline']}", "", "### Global markets", ""]
    out += [f"- {b}" for b in narrative.get("bullets", [])]
    if narrative.get("context"):
        out += ["", " ".join(narrative["context"])]
    if narrative.get("india"):
        out += ["", "### India", ""] + [f"- {b}" for b in narrative["india"]]
    if charts_rel:
        out += ["", f"![US Treasury curve]({charts_rel}/ust_curve.png)", "", "[All charts →](monitor.md)"]
    out += ["", "## The table", "", monitor.table_markdown(snapshot), ""]
    if narrative.get("quality"):
        out += [f"<small>{narrative['quality']} Written by: {narrative.get('writer', 'template')}.</small>", ""]
    out += [DISCLAIMER, ""]
    return "\n".join(out)


def monitor_markdown(day: date, charts: dict[str, str]) -> str:
    out = ["# Monitor", "", f"Charts updated {day:%d %b %Y}. All data free and public; see the "
           "[watchlist](https://github.com/Oblivion783/macro-quant-lab/blob/main/config/series.yaml).", ""]
    for key, title in CHART_ORDER:
        if key in charts and not str(charts[key]).startswith("error"):
            out += [f"## {title}", "", f"![{title}](assets/charts/{key}.png)", ""]
    out += [DISCLAIMER, ""]
    return "\n".join(out)


def archive_index(brief_dir: Path) -> str:
    files = sorted((p for p in brief_dir.glob("20*.md")), reverse=True)
    lines = ["# Archive", "", "Every daily brief, newest first.", ""]
    for p in files[:400]:
        first = p.read_text(encoding="utf-8").splitlines()
        head = next((l[3:] for l in first if l.startswith("## ")), "")
        lines.append(f"- [{p.stem}]({p.name}) · {head}")
    return "\n".join(lines) + "\n"


def update_readme(readme: Path, day: date, narrative: dict) -> None:
    text = readme.read_text(encoding="utf-8")
    block = [f"**{day:%a %d %b %Y} · {narrative['headline']}**", ""]
    block += [f"- {b}" for b in narrative.get("bullets", [])[:5]]
    if narrative.get("india"):
        block += ["", "**India**", ""] + [f"- {b}" for b in narrative["india"][:4]]
    block += ["", f"[Full brief, charts and table →]({config.SITE_URL}/) · "
                  f"[Archive]({config.SITE_URL}/brief/)"]
    new = "\n".join(block)
    pat = re.compile(r"(<!-- BRIEF:START -->)(.*?)(<!-- BRIEF:END -->)", re.S)
    if pat.search(text):
        text = pat.sub(lambda m: f"{m.group(1)}\n{new}\n{m.group(3)}", text)
        readme.write_text(text, encoding="utf-8")


def publish(day: date, narrative: dict, snapshot: dict, charts: dict[str, str], docs: Path | None = None,
            readme: Path | None = None) -> list[Path]:
    docs = docs or config.DOCS
    written = []
    md = brief_markdown(day, narrative, snapshot)
    (docs / "index.md").write_text(md, encoding="utf-8")
    written.append(docs / "index.md")
    bdir = docs / "brief"
    bdir.mkdir(parents=True, exist_ok=True)
    arch = bdir / f"{day.isoformat()}.md"
    arch.write_text(brief_markdown(day, narrative, snapshot, charts_rel=None), encoding="utf-8")
    (bdir / "index.md").write_text(archive_index(bdir), encoding="utf-8")
    (docs / "monitor.md").write_text(monitor_markdown(day, charts), encoding="utf-8")
    written += [arch, bdir / "index.md", docs / "monitor.md"]
    if readme and readme.exists():
        update_readme(readme, day, narrative)
        written.append(readme)
    return written
