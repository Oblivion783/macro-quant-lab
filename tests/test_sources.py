import unittest

from mql import sources


class TestParsers(unittest.TestCase):
    def test_fred_new_header_and_missing(self):
        s = sources.parse_fred_csv("observation_date,DGS10\n2026-09-29,4.12\n2026-09-30,.\n2026-10-01,4.15\n", "UST_10Y")
        self.assertEqual(list(s.values), [4.12, 4.15])
        self.assertEqual(s.name, "UST_10Y")

    def test_fred_old_header(self):
        s = sources.parse_fred_csv("DATE,DGS2\n2026-10-01,3.61\n", "UST_2Y")
        self.assertEqual(s.iloc[0], 3.61)

    def test_boe(self):
        df = sources.parse_boe_csv("DATE,IUDMNZC,IUDSOIA\n01 Oct 2026,4.512,3.95\n02 Oct 2026,4.530,\n")
        self.assertAlmostEqual(df["IUDMNZC"].iloc[-1], 4.53)
        self.assertEqual(str(df.index[0].date()), "2026-10-01")

    def test_ecb(self):
        txt = "KEY,FREQ,TIME_PERIOD,OBS_VALUE\nYC.B,B,2026-10-01,2.41\nYC.B,B,2026-10-02,2.45\n"
        s = sources.parse_ecb_csv(txt, "EUR_10Y")
        self.assertEqual(len(s), 2)
        self.assertAlmostEqual(s.iloc[-1], 2.45)

    def test_yahoo(self):
        payload = {"chart": {"result": [{"meta": {"gmtoffset": -14400}, "timestamp": [1759411800, 1759498200],
                                         "indicators": {"quote": [{"close": [6700.5, None]}]}}]}}
        s = sources.parse_yahoo_chart(payload, "SPX")
        self.assertEqual(len(s), 1)
        self.assertEqual(s.iloc[0], 6700.5)


if __name__ == "__main__":
    unittest.main()
