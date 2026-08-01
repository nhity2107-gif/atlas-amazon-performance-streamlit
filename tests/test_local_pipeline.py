from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.local_data_pipeline import (
    export_snapshot,
    ingest_order_report,
    prepare_order_rows,
)
from snapshot_store import load_snapshot, load_snapshot_metadata


COLUMNS = [
    "amazon-order-id",
    "order-item-id",
    "purchase-date",
    "order-status",
    "fulfillment-channel",
    "currency",
    "asin",
    "sku",
    "quantity",
    "item-price",
    "shipping-price",
]


class LocalPipelineTests(unittest.TestCase):
    def write_report(self, path: Path, rows: list[list[object]]) -> None:
        pd.DataFrame(rows, columns=COLUMNS).to_csv(path, sep="\t", index=False)

    def test_weekly_report_replaces_period_and_snapshot_is_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            database = root / "atlas.db"
            snapshot = root / "dashboard.csv"
            daily = root / "daily.txt"
            weekly = root / "weekly.txt"
            self.write_report(
                daily,
                [
                    ["o1", "i1", "2026-07-01T08:00:00Z", "Shipped", "MFN", "USD", "B000000001", "sku-recuABC1", 1, 10, 2],
                    ["o2", "i2", "2026-07-01T09:00:00Z", "Pending", "AFN", "USD", "B000000002", "sku-recvABC2", 2, 20, 0],
                ],
            )
            ingest_order_report(database, daily, "Wrappiness", "daily")
            self.write_report(
                weekly,
                [
                    ["o1", "i1", "2026-07-01T08:00:00Z", "Cancelled", "MFN", "USD", "B000000001", "sku-recuABC1", 1, 10, 2],
                    ["o3", "i3", "2026-07-01T10:00:00Z", "Shipped", "MFN", "USD", "B000000003", "sku-recjABC3", 1, 30, 5],
                ],
            )
            ingest_order_report(database, weekly, "Wrappiness", "weekly")
            connection = sqlite3.connect(database)
            try:
                stored = connection.execute(
                    "SELECT order_item_id, order_status FROM order_items ORDER BY order_item_id"
                ).fetchall()
            finally:
                connection.close()
            self.assertEqual(stored, [("i1", "Cancelled"), ("i3", "Shipped")])

            result = export_snapshot(
                database,
                snapshot,
                "2026-07-01",
                "2026-07-31",
            )
            self.assertEqual(result["rows"], 1)
            frame = load_snapshot(snapshot)
            self.assertEqual(frame.iloc[0]["ASIN"], "B000000003")
            self.assertEqual(frame.iloc[0]["Date"], "2026-07-01")
            self.assertEqual(frame.iloc[0]["Revenue"], 35)
            metadata = load_snapshot_metadata(snapshot)
            self.assertEqual(metadata["timezone"], "America/Los_Angeles")
            self.assertEqual(metadata["date_min"], "2026-07-01")
            self.assertEqual(metadata["date_max"], "2026-07-01")
            self.assertTrue(metadata["source_updated_at"])

    def test_purchase_time_is_converted_to_los_angeles_before_date_grouping(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = Path(temp_dir) / "orders.txt"
            self.write_report(
                report,
                [
                    [
                        "o1",
                        "i1",
                        "2026-07-01T06:30:00Z",
                        "Shipped",
                        "MFN",
                        "USD",
                        "B000000001",
                        "sku-1",
                        1,
                        10,
                        0,
                    ]
                ],
            )
            rows = prepare_order_rows(report, "Wrappiness", "daily")
            self.assertEqual(rows.iloc[0]["purchase_date_pacific"], "2026-06-30")
            self.assertTrue(rows.iloc[0]["purchase_at_pacific"].endswith("-0700"))

    def test_explicit_weekly_window_removes_orders_missing_at_report_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            database = root / "atlas.db"
            daily = root / "daily.txt"
            weekly = root / "weekly.txt"
            self.write_report(
                daily,
                [
                    ["o1", "i1", "2026-07-01T08:00:00Z", "Shipped", "MFN", "USD", "B000000001", "sku-1", 1, 10, 0],
                    ["o2", "i2", "2026-07-03T08:00:00Z", "Shipped", "MFN", "USD", "B000000002", "sku-2", 1, 20, 0],
                    ["o3", "i3", "2026-07-07T08:00:00Z", "Shipped", "MFN", "USD", "B000000003", "sku-3", 1, 30, 0],
                ],
            )
            ingest_order_report(database, daily, "Wrappiness", "daily")
            self.write_report(
                weekly,
                [
                    ["o2", "i2", "2026-07-03T08:00:00Z", "Shipped", "MFN", "USD", "B000000002", "sku-2", 1, 20, 0],
                ],
            )

            result = ingest_order_report(
                database,
                weekly,
                "Wrappiness",
                "weekly",
                "2026-07-01",
                "2026-07-07",
            )

            connection = sqlite3.connect(database)
            try:
                stored = connection.execute(
                    "SELECT order_item_id FROM order_items ORDER BY order_item_id"
                ).fetchall()
                imported_period = connection.execute(
                    "SELECT period_start, period_end FROM imports ORDER BY import_id DESC LIMIT 1"
                ).fetchone()
            finally:
                connection.close()
            self.assertEqual(stored, [("i2",)])
            self.assertEqual(imported_period, ("2026-07-01", "2026-07-07"))
            self.assertEqual(result["replaced_period"], "2026-07-01 to 2026-07-07")

    def test_replacement_window_rejects_report_rows_outside_period(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report = root / "weekly.txt"
            self.write_report(
                report,
                [["o1", "i1", "2026-07-09T08:00:00Z", "Shipped", "MFN", "USD", "B000000001", "sku-1", 1, 10, 0]],
            )
            with self.assertRaisesRegex(ValueError, "nằm ngoài khoảng thay thế"):
                ingest_order_report(
                    root / "atlas.db",
                    report,
                    "Wrappiness",
                    "weekly",
                    "2026-07-01",
                    "2026-07-07",
                )


if __name__ == "__main__":
    unittest.main()
