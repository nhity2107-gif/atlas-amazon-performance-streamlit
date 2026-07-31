from __future__ import annotations

import unittest

from lark_data import (
    asset_points,
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


if __name__ == "__main__":
    unittest.main()
