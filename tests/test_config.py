import unittest

from mql import config


class TestConfig(unittest.TestCase):
    def test_watchlist_loads_and_is_consistent(self):
        wl = config.load_watchlist()
        ids = [s.id for s in wl.series]
        self.assertGreaterEqual(len(wl.downloadable()), 25)
        self.assertEqual(len(ids), len(set(ids)))
        for d in wl.derived():
            self.assertIn(d.a, ids)
            self.assertIn(d.b, ids)

    def test_portfolio_strategic_weights_sum_to_one(self):
        from mql import portfolio
        cfg = portfolio.load_cfg()
        self.assertAlmostEqual(sum(portfolio.strategic(cfg).values()), 1.0, places=9)
        self.assertAlmostEqual(sum(b["weight"] for b in cfg["benchmark"].values()), 1.0, places=9)
        self.assertEqual(portfolio.validate_weights(portfolio.strategic(cfg), cfg), [])

    def test_decoder_config(self):
        cfg = config.load_yaml("decoder.yaml")
        self.assertIn("fed", cfg["banks"])
        self.assertTrue(cfg["lexicon"]["hawkish"])
        self.assertTrue(cfg["lexicon"]["dovish"])


if __name__ == "__main__":
    unittest.main()
