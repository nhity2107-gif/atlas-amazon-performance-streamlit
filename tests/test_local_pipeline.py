from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

import pandas as pd
from cryptography.fernet import Fernet

from scripts.local_data_pipeline import export_snapshot, ingest_order_report
from snapshot_store import SnapshotError, decrypt_snapshot_bytes


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

    def test_weekly_report_replaces_period_and_snapshot_is_encrypted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            database = root / "atlas.db"
            key_file = root / "dashboard.key"
            snapshot = root / "dashboard.enc"
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

            key = Fernet.generate_key()
            key_file.write_bytes(key)
            result = export_snapshot(
                database,
                snapshot,
                key_file,
                "2026-07-01",
                "2026-07-31",
            )
            self.assertEqual(result["rows"], 1)
            frame, metadata = decrypt_snapshot_bytes(snapshot.read_bytes(), key)
            self.assertEqual(frame.iloc[0]["ASIN"], "B000000003")
            self.assertEqual(frame.iloc[0]["Revenue"], 35)
            self.assertEqual(metadata["row_count"], 1)
            with self.assertRaises(SnapshotError):
                decrypt_snapshot_bytes(snapshot.read_bytes(), Fernet.generate_key())


if __name__ == "__main__":
    unittest.main()
