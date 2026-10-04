"""Run SQL against the local DuckDB store (build it first: python -m mql.store --duckdb).

    python scripts/sql.py notebooks/sql_practice.sql      # run every query in a file
    python scripts/sql.py "SELECT * FROM series LIMIT 5"   # run one query
"""
import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mql.store import split_sql  # noqa: E402

DB = Path(__file__).resolve().parents[1] / "data" / "mql.duckdb"

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    arg = sys.argv[1]
    text = Path(arg).read_text(encoding="utf-8") if arg.endswith(".sql") else arg
    if not DB.exists():
        sys.exit(f"{DB} not found. Build it first:  python -m mql.store --duckdb")
    con = duckdb.connect(str(DB), read_only=True)
    failed = 0
    for title, q in split_sql(text):
        print(f"\n=== {title}")
        try:
            print(con.sql(q))
        except duckdb.Error as e:  # one bad query should not hide the rest
            failed += 1
            print(f"Error: {e}")
    con.close()
    if failed:
        sys.exit(f"\n{failed} query(ies) failed.")
