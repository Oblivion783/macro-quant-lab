"""Run SQL against the local DuckDB store (build it first: python -m mql.store --duckdb).

    python scripts/sql.py notebooks/sql_practice.sql      # run every query in a file
    python scripts/sql.py "SELECT * FROM series LIMIT 5"   # run one query
"""
import sys
from pathlib import Path

import duckdb

DB = Path(__file__).resolve().parents[1] / "data" / "mql.duckdb"

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    arg = sys.argv[1]
    text = Path(arg).read_text(encoding="utf-8") if arg.endswith(".sql") else arg
    con = duckdb.connect(str(DB), read_only=True)
    for q in [q.strip() for q in text.split(";") if q.strip() and not all(l.strip().startswith("--") for l in q.strip().splitlines())]:
        title = next((l.strip("- ").strip() for l in q.splitlines() if l.strip().startswith("--")), q.splitlines()[0])
        print(f"\n=== {title}")
        print(con.sql(q))
