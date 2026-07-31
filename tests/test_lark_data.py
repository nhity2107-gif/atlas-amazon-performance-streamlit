from __future__ import annotations

import unittest

from lark_data import (
    asset_points,
    clipart_frame,
    find_field_name,
    idea_frame,
    is_launched_status,
    total_asin_frame,
)


class LarkDataTests(unittest.TestCase):
    def test_total_asin_mapping_and_explode(self) -> None:
        records = [
            {
                "fields": {
                    "Record ID": "recuABC123",
                    "ASIN": "B0ABCDEFGH, B0H1234567",
                    "Managed By": [{"name": "Sammie"}],
                    "Ads By": [{"name": "Domi"}],
                    "Ads Status": "Main Test",
                }
            }
        ]
        frame, mapping = total_asin_frame(records)
        self.assertEqual(mapping["managed_by"], "Managed By")
        self.assertEqual(len(frame), 2)
        self.assertEqual(set(frame["asin"]), {"B0ABCDEFGH", "B0H1234567"})
        self.assertTrue(frame["ads_launched"].all())

    def test_idea_people_field(self) -> None:
        frame, _ = idea_frame(
            [{"fields": {"Record ID": "recuABC123", "Idea By": [{"name": "Gary"}]}}]
        )
        self.assertEqual(frame.loc[0, "idea_by"], "Gary")

    def test_asset_matrix(self) -> None:
        self.assertEqual(asset_points("New Multi-layer Clipart"), 10)
        self.assertEqual(asset_points("New 1-layer Clipart"), 5)
        self.assertEqual(asset_points("Update Multi-layer Clipart - Full"), 10)
        self.assertEqual(asset_points("Update Multi-layer Clipart - Partial"), 5)

    def test_launched_statuses(self) -> None:
        self.assertTrue(is_launched_status("Launched"))
        self.assertTrue(is_launched_status("Scale 2"))
        self.assertTrue(is_launched_status("Paused"))
        self.assertFalse(is_launched_status("Ready for Ads"))

    def test_visible_record_id_wins_over_internal_field(self) -> None:
        self.assertEqual(
            find_field_name(["Record ID", "_record_id"], ["Record ID"]),
            "Record ID",
        )

    def test_clipart_created_and_updated_contributions(self) -> None:
        mapping = {
            "created_by": "Created By",
            "new_asset_type": "New Created",
            "created_date": "Created Date",
            "updated_by": "Updated By",
            "update_type": "Update",
            "updated_date": "Updated Date",
        }
        frame, _ = clipart_frame(
            [
                {
                    "fields": {
                        "Created By": [{"name": "Alice"}],
                        "New Created": "New Multi-layer Clipart",
                        "Created Date": 1785456000000,
                        "Updated By": [{"name": "Bob"}],
                        "Update": "Update Multi-layer Clipart - Partial",
                        "Updated Date": 1785456000000,
                    }
                }
            ],
            mapping,
        )
        self.assertEqual(frame["employee"].tolist(), ["Alice", "Bob"])
        self.assertEqual(frame["asset_points"].tolist(), [10, 5])


if __name__ == "__main__":
    unittest.main()
