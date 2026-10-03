import tempfile
import unittest
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

from mql import brief, compliance, monitor, narrative, podcast
from tests.helpers import mini_panel, mini_watchlist


class TestCompliance(unittest.TestCase):
    def test_patterns_allow_and_private_masking(self):
        rules = compliance.compile_rules({"patterns": ["confidential"]}, ["Acme Capital"])
        text = "line one\nThis is confidential.\nI met someone from acme capital today\nnot those of any employer, confidential"
        hits = compliance.scan_text(text, rules, ["not those of any employer"])
        self.assertEqual(hits, [(2, "pattern 'confidential'"), (3, "private term #1")])

    def test_repo_is_clean(self):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = compliance.main([])
        self.assertEqual(code, 0, buf.getvalue())


class TestPodcast(unittest.TestCase):
    def test_speakable(self):
        s = podcast.speakable("US 10y rose 7 bp to 4.21%; 2s10s at 35 bp; USD/INR up 0.2%.")
        self.assertIn("10-year", s)
        self.assertIn("7 basis points", s)
        self.assertIn("4.21 percent", s)
        self.assertIn("two-tens", s)
        self.assertIn("dollar-rupee", s)

    def test_rss_is_valid_xml(self):
        xml = podcast.rss([{"date": "2026-10-05", "title": "Yields & dollar", "summary": "x < y", "bytes": 123}],
                          "https://example.org/mql")
        root = ET.fromstring(xml)
        self.assertEqual(root.find("channel/item/enclosure").get("url"), "https://example.org/mql/audio/2026-10-05.mp3")

    def test_script(self):
        n = {"headline": "Calm day", "bullets": ["US 10y Treasury rose 3 bp to 4.20%."], "context": []}
        s = podcast.script(date(2026, 10, 5), n)
        self.assertTrue(s.startswith("This is Macro Quant Lab, the daily markets brief for Monday 5 October."))


class TestBrief(unittest.TestCase):
    def test_publish_writes_pages_and_readme(self):
        s = monitor.build_snapshot(mini_panel(), mini_watchlist(), date(2026, 10, 2))
        n = narrative.template_narrative(s, "Data quality: ok.")
        with tempfile.TemporaryDirectory() as d:
            docs = Path(d) / "docs"
            docs.mkdir()
            readme = Path(d) / "README.md"
            readme.write_text("# X\n<!-- BRIEF:START -->\nold\n<!-- BRIEF:END -->\nrest\n")
            brief.publish(date(2026, 10, 5), n, s, {"ust_curve": "x"}, docs=docs, readme=readme)
            self.assertIn("Daily Macro Desk", (docs / "index.md").read_text())
            self.assertIn("2026-10-05", (docs / "brief" / "index.md").read_text())
            r = readme.read_text()
            self.assertIn(n["headline"], r)
            self.assertNotIn("old", r)
            self.assertIn("rest", r)


if __name__ == "__main__":
    unittest.main()
