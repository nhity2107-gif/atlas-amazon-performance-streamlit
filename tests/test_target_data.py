from __future__ import annotations

from datetime import date
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from target_data import (
    TARGET_SHEET,
    TARGET_SOURCE_COLUMN,
    TargetError,
    load_fbm_target_snapshot,
    normalize_fbm_target,
    read_fbm_target_workbook,
    save_fbm_target_snapshot,
    target_for_month,
    target_progress,
)


class TargetDataTests(unittest.TestCase):
    def test_normalize_uses_monthly_forecast_and_ignores_separator_rows(self) -> None:
        source = pd.DataFrame(
            {
                "Month": [1, 7, "H1", "H2", 12],
                TARGET_SOURCE_COLUMN: [140000, 320000, 900000, 800000, 1500000],
            }
        )
        result = normalize_fbm_target(source)
        self.assertEqual(result["Month"].tolist(), ["2026-01", "2026-07", "2026-12"])
        self.assertEqual(target_for_month(result, "2026-07"), 320000.0)

    def test_snapshot_round_trip(self) -> None:
        source = normalize_fbm_target(
            pd.DataFrame({"Month": [7], TARGET_SOURCE_COLUMN: [320000]})
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fbm_target.csv"
            save_fbm_target_snapshot(path, source, source_name="forecast.xlsx")
            result = load_fbm_target_snapshot(path)
        pd.testing.assert_frame_equal(result, source)

    def test_workbook_reads_only_the_named_forecast_sheet(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "forecast.xlsx"
            with pd.ExcelWriter(path, engine="openpyxl") as writer:
                pd.DataFrame(
                    {"Month": [7], TARGET_SOURCE_COLUMN: [999999]}
                ).to_excel(writer, sheet_name="Output Plan", index=False)
                pd.DataFrame(
                    {"Month": [7], TARGET_SOURCE_COLUMN: [320000]}
                ).to_excel(writer, sheet_name=TARGET_SHEET, index=False)
            result = read_fbm_target_workbook(path)
        self.assertEqual(target_for_month(result, "2026-07"), 320000.0)

    def test_prorates_current_month_by_report_as_of_date(self) -> None:
        result = target_progress("2026-08", 300000, 160000, date(2026, 8, 16))
        self.assertEqual(result["elapsed_days"], 16)
        self.assertAlmostEqual(result["target_mtd"], 300000 * 16 / 31)
        self.assertAlmostEqual(result["gap"], 160000 - 300000 * 16 / 31)

    def test_completed_month_uses_full_target(self) -> None:
        result = target_progress("2026-07", 320000, 181763, date(2026, 8, 16))
        self.assertEqual(result["elapsed_days"], 31)
        self.assertEqual(result["target_mtd"], 320000)

    def test_rejects_missing_source_column(self) -> None:
        with self.assertRaises(TargetError):
            normalize_fbm_target(pd.DataFrame({"Month": [7], "Other": [1]}))


if __name__ == "__main__":
    unittest.main()
