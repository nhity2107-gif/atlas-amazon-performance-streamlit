from __future__ import annotations

import unittest

import pandas as pd

from team_kpi import (
    asin_new_revenue_from_custom_cohort,
    asin_portfolio_revenue,
    fbm_asin_rows,
    workflow_kpi_window_end,
)


class TeamKpiTests(unittest.TestCase):
    def test_workflow_window_uses_mtd_input_date_not_last_order_date(self) -> None:
        result = workflow_kpi_window_end(
            "2026-08",
            {"report_as_of_date": "2026-08-05"},
            pd.Timestamp("2026-08-03"),
        )
        self.assertEqual(result, pd.Timestamp("2026-08-05 23:59:59"))

    def test_historical_workflow_window_uses_month_end(self) -> None:
        result = workflow_kpi_window_end(
            "2026-07",
            {"report_as_of_date": "2026-08-05"},
            pd.Timestamp("2026-07-30"),
        )
        self.assertEqual(result, pd.Timestamp("2026-07-31 23:59:59"))

    def test_fbm_asin_rows_excludes_fba_and_unmapped(self) -> None:
        attributed = pd.DataFrame(
            [
                {"asin": "fbm", "fulfill_by": " FBM ", "Revenue": 100},
                {"asin": "fba", "fulfill_by": "FBA", "Revenue": 200},
                {"asin": "unknown", "fulfill_by": "", "Revenue": 300},
            ]
        )
        result = fbm_asin_rows(attributed)
        self.assertEqual(result["asin"].tolist(), ["fbm"])
        self.assertEqual(result["Revenue"].sum(), 100)

    def test_new_revenue_only_counts_each_asin_inside_custom_done_cohort(self) -> None:
        attributed = pd.DataFrame(
            [
                {
                    "record_id": "rec1",
                    "asin": "asin-old",
                    "ads_by": "Owner A",
                    "custom_check_done_date": pd.Timestamp("2026-06-10"),
                    "Revenue": 100.0,
                },
                {
                    "record_id": "rec1",
                    "asin": "asin-new",
                    "ads_by": "Owner A",
                    "custom_check_done_date": pd.Timestamp("2026-07-15"),
                    "Revenue": 50.0,
                },
                {
                    "record_id": "rec2",
                    "asin": "asin-before",
                    "ads_by": "Owner A",
                    "custom_check_done_date": pd.Timestamp("2026-06-19"),
                    "Revenue": 200.0,
                },
                {
                    "record_id": "rec3",
                    "asin": "asin-boundary",
                    "ads_by": "Owner B",
                    "custom_check_done_date": pd.Timestamp("2026-06-20 23:59:00"),
                    "Revenue": 75.0,
                },
            ]
        )

        result = asin_new_revenue_from_custom_cohort(
            attributed,
            "ads_by",
            pd.Timestamp("2026-06-20"),
            pd.Timestamp("2026-07-31"),
        ).set_index("Nhân sự")

        self.assertEqual(result.loc["Owner A", "New_Revenue_ASINs"], 1)
        self.assertEqual(result.loc["Owner A", "New_Revenue"], 50)
        self.assertEqual(result.loc["Owner B", "New_Revenue_ASINs"], 1)
        self.assertEqual(result.loc["Owner B", "New_Revenue"], 75)

    def test_portfolio_revenue_sums_all_owned_asins(self) -> None:
        attributed = pd.DataFrame(
            [
                {"asin": "a1", "managed_by": "Owner A", "Revenue": 100.0},
                {"asin": "a2", "managed_by": "Owner A", "Revenue": 50.0},
                {"asin": "b1", "managed_by": "Owner B", "Revenue": 75.0},
                {"asin": "x1", "managed_by": "", "Revenue": 999.0},
            ]
        )
        result = asin_portfolio_revenue(attributed, "managed_by").set_index("Nhân sự")

        self.assertEqual(result.loc["Owner A", "Portfolio_ASINs"], 2)
        self.assertEqual(result.loc["Owner A", "Portfolio_Revenue"], 150)
        self.assertEqual(result.loc["Owner B", "Portfolio_ASINs"], 1)
        self.assertEqual(result.loc["Owner B", "Portfolio_Revenue"], 75)


if __name__ == "__main__":
    unittest.main()
