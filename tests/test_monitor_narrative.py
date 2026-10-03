import json
import unittest
from datetime import date

from mql import monitor, narrative
from tests.helpers import mini_panel, mini_watchlist


def snap():
    return monitor.build_snapshot(mini_panel(), mini_watchlist(), date(2026, 10, 2))


class TestMonitor(unittest.TestCase):
    def test_change_units(self):
        self.assertEqual(monitor.change("pct", 4.20, 4.13), 7.0)
        self.assertEqual(monitor.change("price", 110, 100), 10.0)
        self.assertEqual(monitor.change("level", 17.5, 16.0), 1.5)
        self.assertIsNone(monitor.change("pct", 4.2, None))

    def test_snapshot_fields(self):
        s = snap()
        self.assertEqual({r["id"] for r in s["series"]}, {"UST_2Y", "UST_10Y", "SPX", "VIX", "US_HY_OAS", "US_2S10S"})
        r = next(r for r in s["series"] if r["id"] == "UST_10Y")
        for k in ("last", "date", "chg_1d", "chg_1w", "chg_1m", "z_1y", "move_z"):
            self.assertIn(k, r)
        json.dumps(s)  # serialisable

    def test_format(self):
        self.assertEqual(monitor.fmt_level("pct", 4.2051), "4.21%")
        self.assertEqual(monitor.fmt_level("spread", 0.351), "35 bp")
        self.assertEqual(monitor.fmt_change("pct", 7.0), "+7 bp")
        self.assertEqual(monitor.fmt_change("price", -1.234), "-1.23%")

    def test_table_and_movers(self):
        s = snap()
        self.assertIn("| **US rates** |", monitor.table_markdown(s))
        self.assertLessEqual(len(monitor.top_movers(s, 3)), 3)


class TestNarrative(unittest.TestCase):
    def test_template_is_grounded(self):
        s = snap()
        n = narrative.template_narrative(s, "Data quality: fine.")
        text = " ".join([n["headline"]] + n["bullets"] + n["context"])
        ok, unknown = narrative.check_grounding(text, s)
        self.assertTrue(ok, unknown)

    def test_invented_number_rejected(self):
        s = snap()
        ok, unknown = narrative.check_grounding("The US 10y Treasury yield jumped 37 bp to 9.87%.", s)
        self.assertFalse(ok)
        self.assertIn(9.87, unknown)

    def test_tenors_and_names_are_not_numbers(self):
        s = snap()
        ok, _ = narrative.check_grounding("The 2-year and 10y yields, the 2s10s curve and the S&P 500 in 2026.", s)
        self.assertTrue(ok)

    def test_llm_accept_and_reject(self):
        s = snap()
        r = next(r for r in s["series"] if r["id"] == "UST_10Y")
        good = json.dumps({"headline": f"US 10y Treasury at {monitor.fmt_level('pct', r['last'])}",
                           "bullets": ["Rates drifted."], "context": "Calm."})
        n, audit = narrative.llm_narrative(s, lambda p: good)
        self.assertIsNotNone(n)
        self.assertTrue(audit["accepted"])
        bad = json.dumps({"headline": "Yields rose 55 bp to 7.77%", "bullets": [], "context": ""})
        n, audit = narrative.llm_narrative(s, lambda p: bad)
        self.assertIsNone(n)
        self.assertFalse(audit["accepted"])

    def test_write_falls_back(self):
        s = snap()

        def boom(p):
            raise RuntimeError("no quota")

        n, audit = narrative.write(s, "q", boom)
        self.assertEqual(n["writer"], "template")
        self.assertIn("no quota", audit["error"])


if __name__ == "__main__":
    unittest.main()
