import tempfile
import unittest
from datetime import date
from pathlib import Path

import pandas as pd

from mql import quality, store
from tests.helpers import mini_panel, mini_watchlist, random_walk


class TestStore(unittest.TestCase):
    def test_merge_prefers_fresh_values(self):
        old = pd.Series([1.0, 2.0, 3.0], index=pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-05"]), name="X")
        new = pd.Series([2.5, 4.0], index=pd.to_datetime(["2026-01-02", "2026-01-06"]), name="X")
        m = store.merge(old, new)
        self.assertEqual(list(m.values), [1.0, 2.5, 3.0, 4.0])

    def test_roundtrip_and_derived(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            p = mini_panel()
            for c in ["UST_2Y", "UST_10Y", "SPX", "VIX", "US_HY_OAS"]:
                store.save_series(p[c].rename(c), root)
            panel = store.load_panel(mini_watchlist(), root)
            self.assertIn("US_2S10S", panel)
            self.assertAlmostEqual(panel["US_2S10S"].iloc[-1], panel["UST_10Y"].iloc[-1] - panel["UST_2Y"].iloc[-1], places=4)
            starts = store.fetch_starts(mini_watchlist(), root=root)
            self.assertEqual(starts["UST_2Y"], "2026-09-22")


class TestQuality(unittest.TestCase):
    def test_ok_series(self):
        r = quality.check_series(random_walk(name="UST_10Y"), "pct", date(2026, 10, 5))
        self.assertEqual(r["status"], "ok", r["issues"])

    def test_stale(self):
        r = quality.check_series(random_walk(end="2026-09-01", name="UST_10Y"), "pct", date(2026, 10, 5))
        self.assertEqual(r["status"], "warn")
        self.assertIn("stale", r["issues"][0])

    def test_out_of_range_fails(self):
        s = random_walk(name="UST_10Y")
        s.iloc[-10] = 99.0
        r = quality.check_series(s, "pct", date(2026, 10, 5))
        self.assertEqual(r["status"], "fail")

    def test_jump_flagged(self):
        s = random_walk(name="UST_10Y", step=0.03)
        s.iloc[-1] = s.iloc[-2] + 1.5
        r = quality.check_series(s, "pct", date(2026, 10, 5))
        self.assertTrue(any("normal day" in i for i in r["issues"]))

    def test_download_error(self):
        r = quality.check_series(pd.Series(dtype=float, name="X"), "pct", date(2026, 10, 5), error="HTTP 500")
        self.assertEqual(r["status"], "fail")

    def test_report(self):
        rep = quality.run_checks(mini_panel(), mini_watchlist(), date(2026, 10, 5))
        self.assertEqual(sum(rep["counts"].values()), 6)
        self.assertTrue(quality.summary_line(rep).startswith("Data quality:"))


if __name__ == "__main__":
    unittest.main()


try:
    import duckdb
except ImportError:  # optional dependency
    duckdb = None


@unittest.skipIf(duckdb is None, "duckdb not installed")
class TestDuckDB(unittest.TestCase):
    def test_build_and_query(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            wl = mini_watchlist()
            panel = mini_panel()
            for c in ["UST_2Y", "UST_10Y", "SPX", "VIX", "US_HY_OAS"]:
                store.save_series(panel[c].rename(c), root)
            db = store.to_duckdb(wl, Path(d) / "t.duckdb", root)
            con = duckdb.connect(str(db))
            self.assertGreater(con.execute("SELECT count(*) FROM obs").fetchone()[0], 0)
            self.assertGreater(con.execute("SELECT count(*) FROM wide").fetchone()[0], 0)
            con.close()


class TestSplitSql(unittest.TestCase):
    def test_semicolon_in_comment_is_ignored(self):
        text = "-- note; with a semicolon\n-- 1. First\nSELECT 1;\n\n-- 2. Second\nSELECT\n  2\n;\n-- trailing\n"
        self.assertEqual(store.split_sql(text), [("1. First", "SELECT 1"), ("2. Second", "SELECT\n  2")])

    def test_practice_file(self):
        text = (Path(__file__).resolve().parents[1] / "notebooks" / "sql_practice.sql").read_text(encoding="utf-8")
        parts = store.split_sql(text)
        self.assertEqual([t.split(".")[0] for t, _ in parts], ["1", "2", "3", "4", "5"])
        for _, q in parts:
            self.assertTrue(q.lstrip().upper().startswith("SELECT"), q)
