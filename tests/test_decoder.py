import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mql import config, decoder

OLD = ("Recent indicators suggest that economic activity has continued to expand at a solid pace. "
       "Inflation remains elevated. The Committee decided to maintain the target range for the federal funds rate "
       "at 4-1/4 to 4-1/2 percent. The Committee is strongly committed to returning inflation to its 2 percent objective.")
NEW = ("Recent indicators suggest that economic activity has moderated. Job gains have slowed. "
       "The Committee decided to lower the target range for the federal funds rate to 4 to 4-1/4 percent. "
       "The Committee is strongly committed to returning inflation to its 2 percent objective.")
CFG = {"banks": {"fed": {"name": "Federal Reserve (FOMC)"}},
       "lexicon": {"hawkish": {"inflation remains elevated": 2, "solid pace": 1},
                   "dovish": {"lower the target range": 3, "job gains have slowed": 2, "moderated": 1}}}


class TestDecoder(unittest.TestCase):
    def test_sentences(self):
        self.assertEqual(len(decoder.split_sentences(OLD)), 4)

    def test_redline(self):
        ops = decoder.redline(decoder.split_sentences(OLD), decoder.split_sentences(NEW))
        kinds = [o["op"] for o in ops]
        self.assertIn("same", kinds)
        self.assertIn("changed", kinds)
        changed = [o for o in ops if o["op"] == "changed"]
        self.assertTrue(any("~~" in o["diff"] and "**" in o["diff"] for o in changed))

    def test_tone(self):
        t_old = decoder.tone(OLD, CFG["lexicon"])
        t_new = decoder.tone(NEW, CFG["lexicon"])
        self.assertGreater(t_old["score"], 0)
        self.assertLess(t_new["score"], 0)
        self.assertEqual(decoder.label_from_delta(t_new["score"] - t_old["score"]), "dovish")

    def test_decode_end_to_end(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(config, "STATEMENTS", Path(d) / "statements"):
                decoder.decode("fed", "2026-07-29", "https://example.org/old", OLD, CFG, Path(d) / "docs")
                res = decoder.decode("fed", "2026-09-16", "https://example.org/new", NEW, CFG, Path(d) / "docs")
                self.assertEqual(res["previous"], "2026-07-29")
                self.assertLess(res["delta"], 0)
                md = (Path(d) / "docs" / "fed-2026-09-16.md").read_text()
                self.assertIn("What changed", md)
                self.assertIn("fed-2026-09-16", (Path(d) / "docs" / "index.md").read_text())

    def test_feed_parse(self):
        xml = ("<rss><channel><item><title>Federal Reserve issues FOMC statement</title>"
               "<link>https://www.federalreserve.gov/x.htm</link><pubDate>Wed, 16 Sep 2026 18:00:00 GMT</pubDate></item>"
               "</channel></rss>")
        items = decoder.parse_feed(xml)
        self.assertEqual(items[0]["date"], "2026-09-16")

    def test_clean_html_bytes_keeps_dashes(self):
        html = ("<html><head><meta charset='utf-8'></head><body><div id='article'><p>The Committee decided to maintain "
                "the target range at 3‑1/2 to 3‑3/4 percent — by a 12–0 vote today.</p></div></body></html>").encode("utf-8")
        text = decoder.clean_html(html)
        self.assertIn("12–0", text)
        self.assertNotIn("â", text)

    def test_clean_html(self):
        html = ("<html><nav>menu</nav><div id='article'><p>Short</p><p>" + OLD + "</p></div>"
                "<footer><p>footer text that is long enough to count as a paragraph here</p></footer></html>")
        text = decoder.clean_html(html)
        self.assertIn("solid pace", text)
        self.assertNotIn("footer", text)


if __name__ == "__main__":
    unittest.main()
