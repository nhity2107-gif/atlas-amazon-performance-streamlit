from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd
from cryptography.fernet import Fernet

from lark_snapshot_store import (
    load_encrypted_lark_snapshot,
    load_lark_snapshot,
    newest_lark_snapshot,
    save_encrypted_lark_snapshot,
    save_lark_snapshot,
)


class LarkSnapshotStoreTests(unittest.TestCase):
    @staticmethod
    def sample_payload() -> dict:
        return {
            "total": pd.DataFrame(
                [
                    {
                        "record_id": "recuABC123",
                        "asin": "B0ABCDEFGH",
                        "listing_done_date": pd.Timestamp("2026-07-31"),
                        "listing_lead_time": 4.25,
                        "custom_lead_time": 2.0,
                        "ads_launched": True,
                    }
                ]
            ),
            "workflow": pd.DataFrame(
                [
                    {
                        "lark_record_id": "recTotal1",
                        "listing_done_date": pd.Timestamp("2026-07-31"),
                        "custom_check_done_date": pd.Timestamp("2026-07-30"),
                        "testing_start_date": pd.Timestamp("2026-07-29"),
                        "listing_lead_time": 4.25,
                        "custom_lead_time": 2.0,
                    }
                ]
            ),
            "workflow_ideas": pd.DataFrame(
                [
                    {
                        "lark_record_id": "recIdea1",
                        "handover_date": pd.Timestamp("2026-07-31"),
                    }
                ]
            ),
            "ideas": pd.DataFrame(
                [
                    {
                        "record_id": "recuABC123",
                        "handover_date": pd.Timestamp("2026-07-31"),
                    }
                ]
            ),
            "cliparts": pd.DataFrame(
                [
                    {
                        "employee": "Alice",
                        "created_date": pd.Timestamp("2026-07-31"),
                        "asset_points": 5,
                    }
                ]
            ),
            "record_counts": {"TOTAL ASIN": 1, "MRND IDEA": 1, "CLIPARTS": 1},
            "field_mapping": {"TOTAL ASIN": {"asin": "ASIN"}},
            "available_fields": {"TOTAL ASIN": ["ASIN"]},
        }

    def test_round_trip_preserves_kpi_types_and_metadata(self) -> None:
        payload = self.sample_payload()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            save_lark_snapshot(root, payload)
            restored = load_lark_snapshot(root)

        self.assertIsNotNone(restored)
        assert restored is not None
        self.assertEqual(restored["total"].loc[0, "listing_lead_time"], 4.25)
        self.assertEqual(restored["workflow"].loc[0, "custom_lead_time"], 2.0)
        self.assertEqual(
            str(restored["workflow_ideas"].loc[0, "handover_date"].date()),
            "2026-07-31",
        )
        self.assertTrue(restored["total"].loc[0, "ads_launched"])
        self.assertEqual(
            str(restored["ideas"].loc[0, "handover_date"].date()), "2026-07-31"
        )
        self.assertEqual(restored["record_counts"]["TOTAL ASIN"], 1)
        self.assertTrue(restored["snapshot_updated_at"])
        self.assertEqual(
            restored["snapshot_date_semantics"],
            "lark_calendar_date_no_timezone_conversion",
        )
        self.assertEqual(
            set(restored["snapshot_frames"]),
            {"total", "workflow", "workflow_ideas", "ideas", "cliparts"},
        )

    def test_encrypted_round_trip_and_wrong_key_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "plain"
            encrypted = Path(temp_dir) / "published.enc"
            save_lark_snapshot(root, self.sample_payload())
            key = Fernet.generate_key().decode("utf-8")
            save_encrypted_lark_snapshot(root, encrypted, key)
            restored = load_encrypted_lark_snapshot(encrypted, key)
            wrong_key = Fernet.generate_key().decode("utf-8")
            rejected = load_encrypted_lark_snapshot(encrypted, wrong_key)

        self.assertIsNotNone(restored)
        assert restored is not None
        self.assertEqual(restored["record_counts"]["TOTAL ASIN"], 1)
        self.assertEqual(restored["total"].loc[0, "listing_lead_time"], 4.25)
        self.assertTrue(restored["total"].loc[0, "ads_launched"])
        self.assertIsNone(rejected)

    def test_newest_snapshot_beats_stale_local_snapshot(self) -> None:
        local = {"snapshot_updated_at": "2026-08-12T00:51:00+00:00"}
        published = {"snapshot_updated_at": "2026-08-17T07:17:00+00:00"}

        self.assertIs(newest_lark_snapshot(local, published), published)

    def test_newest_snapshot_handles_missing_candidates(self) -> None:
        published = {"snapshot_updated_at": "2026-08-17T07:17:00+00:00"}

        self.assertIs(newest_lark_snapshot(None, published), published)
        self.assertIsNone(newest_lark_snapshot(None, None))


if __name__ == "__main__":
    unittest.main()
