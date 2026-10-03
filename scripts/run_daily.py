"""Daily Macro Desk run: download → store → quality → snapshot → charts → narrative → brief.

    python scripts/run_daily.py                 # data only (safe before compliance clearance)
    python scripts/run_daily.py --publish       # also writes the site pages and the README brief
    python scripts/run_daily.py --offline       # no downloads; rebuild from stored history

GitHub Actions runs this every weekday at about 05:47 IST and adds --publish only when the
repository variable PUBLISH_ENABLED is "true".
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mql import brief, charts, config, llm, monitor, narrative, quality, sources, store  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--publish", action="store_true", help="write docs/ pages and the README brief")
    ap.add_argument("--offline", action="store_true", help="skip downloads")
    args = ap.parse_args()

    day = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    wl = config.load_watchlist()
    errors: dict[str, str] = {}

    if not args.offline:
        starts = store.fetch_starts(wl)
        fresh, errors = sources.fetch_all(wl, starts)
        for sid, s in fresh.items():
            store.save_series(store.merge(store.load_series(sid), s))
        print(f"Downloaded {len(fresh)} series; {len(errors)} failed.")
        for sid, e in errors.items():
            print(f"  {sid}: {e}")

    panel = store.load_panel(wl)
    if panel.empty:
        print("No data stored yet. Run without --offline first.")
        return 1

    config.LATEST.mkdir(parents=True, exist_ok=True)
    q = quality.run_checks(panel, wl, day, errors)
    (config.LATEST / "quality.json").write_text(json.dumps(q, indent=1))
    qline = quality.summary_line(q)
    print(qline)

    snap = monitor.build_snapshot(panel, wl, day)
    snap["quality"] = q["counts"]
    (config.LATEST / "snapshot.json").write_text(json.dumps(snap, indent=1))

    nar, audit = narrative.write(snap, qline, llm.gemini_generator())
    nar["date"] = day.isoformat()
    (config.LATEST / "narrative.json").write_text(json.dumps(nar, indent=1))
    (config.LATEST / "narrative_audit.json").write_text(json.dumps(audit, indent=1))
    print(f"Narrative by {nar['writer']}: {nar['headline']}")

    if args.publish:
        made = charts.build_all(panel, config.CHARTS)
        written = brief.publish(day, nar, snap, made, readme=config.ROOT / "README.md")
        print(f"Published {len(written)} pages; charts: {', '.join(k for k, v in made.items() if not str(v).startswith('error'))}")

    ok = q["counts"]["ok"] + q["counts"]["warn"]
    return 0 if ok > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
