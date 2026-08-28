from __future__ import annotations

import unittest

import pandas as pd

from reporting_period import period_bounds, period_label, period_months


class ReportingPeriodTests(unittest.TestCase):
    def test_month_remains_a_single_month(self) -> None:
        self.assertEqual(period_months("2026-08"), ["2026-08"])
        self.assertEqual(period_label("2026-08"), "Tháng 08/2026")

    def test_h2_2026_covers_july_through_december(self) -> None:
        self.assertEqual(
            period_months("H2/2026"),
            ["2026-07", "2026-08", "2026-09", "2026-10", "2026-11", "2026-12"],
        )
        self.assertEqual(
            period_bounds("H2/2026"),
            (pd.Timestamp("2026-07-01"), pd.Timestamp("2026-12-31")),
        )
        self.assertEqual(period_label("H2/2026"), "H2/2026")


if __name__ == "__main__":
    unittest.main()
