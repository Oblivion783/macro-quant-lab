import unittest

import numpy as np
import pandas as pd

from mql import portfolio

CFG = {
    "inception": "2026-01-01", "cost_bps": 10, "tilt_limit": 0.05,
    "benchmark": {"equity": {"ticker": "EQ", "weight": 0.6}, "fixed_income": {"ticker": "BD", "weight": 0.4}},
    "sleeves": [
        {"id": "eq", "ticker": "EQ", "name": "Equities", "asset_class": "equity", "strategic": 0.5},
        {"id": "bd", "ticker": "BD", "name": "Bonds", "asset_class": "fixed_income", "strategic": 0.4},
        {"id": "gold", "ticker": "GD", "name": "Gold", "asset_class": "real_assets", "strategic": 0.1},
    ],
}


def prices(n=300, seed=7):
    idx = pd.bdate_range("2026-01-01", periods=n)
    rng = np.random.default_rng(seed)
    data = {t: 100 * np.cumprod(1 + rng.normal(mu, sd, n)) for t, mu, sd in
            (("EQ", 0.0004, 0.01), ("BD", 0.0001, 0.004), ("GD", 0.0002, 0.008))}
    return pd.DataFrame(data, index=idx)


class TestPortfolio(unittest.TestCase):
    def test_constant_prices_only_costs(self):
        px = pd.DataFrame({"a": 1.0, "b": 1.0}, index=pd.bdate_range("2026-01-01", periods=60))
        out = portfolio.simulate(px, [(pd.Timestamp("2026-01-01"), {"a": 0.5, "b": 0.5})], cost_bps=10, monthly=True)
        # initial purchase costs 10 bp of NAV; no drift so later rebalances trade nothing
        self.assertAlmostEqual(out["nav"].iloc[-1], 100 * (1 - 0.001), places=9)

    def test_single_asset_tracks_price(self):
        px = prices()[["EQ"]].rename(columns={"EQ": "eq"})
        out = portfolio.simulate(px, [(pd.Timestamp("2026-01-01"), {"eq": 1.0})], cost_bps=0)
        self.assertAlmostEqual(out["nav"].iloc[-1] / 100, px["eq"].iloc[-1] / px["eq"].iloc[0], places=9)

    def test_weights_drift_and_rebalance_monthly(self):
        px = prices().rename(columns={"EQ": "eq", "BD": "bd", "GD": "gold"})
        out = portfolio.simulate(px, [(pd.Timestamp("2026-01-01"), {"eq": 0.5, "bd": 0.4, "gold": 0.1})], cost_bps=5)
        first_of_feb = out.index[out.index >= "2026-02-01"][0]
        self.assertAlmostEqual(out.loc[first_of_feb, "w_eq"], 0.5, places=12)
        self.assertGreater(out.loc[first_of_feb, "turnover"], 0)
        w = out[[c for c in out if c.startswith("w_")]].sum(axis=1)
        self.assertTrue(np.allclose(w, 1.0))

    def test_validate(self):
        self.assertEqual(portfolio.validate_weights({"eq": 0.5, "bd": 0.4, "gold": 0.1}, CFG), [])
        errs = portfolio.validate_weights({"eq": 0.6, "bd": 0.3, "gold": 0.1}, CFG)
        self.assertTrue(any("more than" in e for e in errs))
        self.assertTrue(portfolio.validate_weights({"eq": 0.5, "bd": 0.4}, CFG))

    def test_brinson_sums_to_active(self):
        wp = {"equity": 0.55, "fixed_income": 0.35, "real_assets": 0.10}
        wb = {"equity": 0.60, "fixed_income": 0.40}
        rp = {"equity": 0.031, "fixed_income": -0.004, "real_assets": 0.02}
        rb = {"equity": 0.028, "fixed_income": -0.006}
        res = portfolio.brinson_fachler(wp, wb, rp, rb)
        total = sum(res["total"].values())
        self.assertAlmostEqual(total, res["Rp"] - res["Rb"], places=12)
        self.assertAlmostEqual(res["segments"]["real_assets"]["selection"], 0.0)

    def test_run_metrics_attribution_factsheet(self):
        px = prices()
        port, bench = portfolio.run(px, CFG, decisions=[])
        m = portfolio.metrics(port["nav"], bench["nav"])
        for k in ("ann_vol", "max_drawdown", "tracking_error", "info_ratio"):
            self.assertIn(k, m)
        self.assertLessEqual(m["max_drawdown"], 0)
        att = portfolio.period_attribution(port, px, CFG, pd.Timestamp("2026-03-31"), pd.Timestamp("2026-04-30"))
        self.assertAlmostEqual(sum(att["total"].values()), att["active"], places=10)
        self.assertLess(abs(att["residual"]), 0.01)
        md = portfolio.factsheet("2026-04", port, bench, px, CFG, decisions=[])
        self.assertIn("Brinson-Fachler", md)
        self.assertIn("| Equities |", md)


if __name__ == "__main__":
    unittest.main()
