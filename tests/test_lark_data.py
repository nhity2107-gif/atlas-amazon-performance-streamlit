from __future__ import annotations

import unittest

from lark_data import (
    asset_points,
    clipart_frame,
    find_field_name,
    first_url,
    idea_frame,
    is_launched_status,
    numeric_value,
    total_asin_frame,
    workflow_idea_frame,
    workflow_total_frame,
)


class LarkDataTests(unittest.TestCase):
    def test_lark_formula_numeric_value(self) -> None:
        self.assertEqual(numeric_value({"type": 2, "value": [7.5]}), 7.5)

    def test_total_asin_mapping_and_explode(self) -> None:
        records = [
            {
                "fields": {
                    "Record ID": "recuABC123",
                    "ASIN": "B0ABCDEFGH, B0H1234567",
                    "Managed By": [{"name": "Sammie"}],
                    "Ads By": [{"name": "Domi"}],
                    "Fulfill By": "FBA",
                    "Ads Status": "Main Test",
                    "Listing Lead Time": {"type": 2, "value": [4.25]},
                    "Custom Lead Time": {"type": 2, "value": [2]},
                }
            }
        ]
        frame, mapping = total_asin_frame(records)
        self.assertEqual(mapping["managed_by"], "Managed By")
        self.assertEqual(len(frame), 2)
        self.assertEqual(set(frame["asin"]), {"B0ABCDEFGH", "B0H1234567"})
        self.assertTrue(frame["ads_launched"].all())
        self.assertEqual(frame.loc[0, "listing_lead_time"], 4.25)
        self.assertEqual(frame.loc[0, "custom_lead_time"], 2)
        self.assertEqual(frame.loc[0, "fulfill_by"], "FBA")

    def test_workflow_frames_keep_one_row_per_lark_record(self) -> None:
        total_mapping = {
            "listing_done_date": "Listing Done",
            "custom_check_done_date": "Custom Check Done",
            "testing_start_date": "Testing Start Date",
            "listing_lead_time": "Listing Lead Time",
            "custom_lead_time": "Custom Lead Time",
        }
        total_records = [
            {
                "record_id": "recTotal1",
                "fields": {
                    "Listing Done": 1785456000000,
                    "Listing Lead Time": 4.25,
                },
            },
            {"record_id": "recTotal2", "fields": {}},
        ]
        workflow = workflow_total_frame(total_records, total_mapping)
        self.assertEqual(len(workflow), 2)
        self.assertEqual(workflow.loc[0, "listing_lead_time"], 4.25)

        ideas = workflow_idea_frame(
            [
                {"record_id": "recIdea1", "fields": {"Date Pickup": 1785456000000}},
                {"record_id": "recIdea2", "fields": {}},
            ],
            {"handover_date": "Date Pickup"},
        )
        self.assertEqual(len(ideas), 2)
        self.assertEqual(str(ideas.loc[0, "handover_date"].date()), "2026-07-31")

    def test_idea_people_field(self) -> None:
        frame, mapping = idea_frame(
            [
                {
                    "fields": {
                        "Record ID": "recuABC123",
                        "Idea By": [{"name": "Gary"}],
                        "Date Pickup": 1785456000000,
                        "Idea Handover Date": 1785542400000,
                    }
                }
            ]
        )
        self.assertEqual(frame.loc[0, "idea_by"], "Gary")
        self.assertEqual(mapping["handover_date"], "Date Pickup")
        self.assertEqual(str(frame.loc[0, "handover_date"].date()), "2026-07-31")

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

    def test_lark_record_ids_support_all_rec_prefixes(self) -> None:
        records = [
            {"record_id": "recjAlpha123", "fields": {"ASIN": "B0ABCDEFGH"}},
            {"record_id": "recvBeta456", "fields": {"ASIN": "B0H1234567"}},
        ]
        mapping = {
            key: None
            for key in (
                "record_id", "internal_record_id", "asin", "product_name", "image",
                "managed_by", "custom_by", "ads_by", "ads_status", "date_pickup",
                "listing_done_date", "ps_pickup_date", "custom_done_date",
                "custom_check_done_date", "testing_start_date",
            )
        }
        mapping["asin"] = "ASIN"
        frame, _ = total_asin_frame(records, mapping)
        self.assertEqual(set(frame["record_id"]), {"recjAlpha123", "recvBeta456"})

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

    def test_internal_record_id_and_lark_image_fallback(self) -> None:
        mapping = {
            key: None
            for key in (
                "record_id", "internal_record_id", "asin", "product_name", "image",
                "managed_by", "custom_by", "ads_by", "ads_status", "date_pickup",
                "listing_done_date", "ps_pickup_date", "custom_done_date",
                "custom_check_done_date", "testing_start_date",
            )
        }
        mapping.update({"asin": "ASIN", "image": "Image"})
        frame, _ = total_asin_frame(
            [
                {
                    "record_id": "recuFallback123",
                    "fields": {
                        "ASIN": "B0ABCDEFGH",
                        "Image": [{"tmp_url": "https://example.com/product.png"}],
                    },
                }
            ],
            mapping,
        )
        self.assertEqual(frame.loc[0, "record_id"], "recuFallback123")
        self.assertEqual(frame.loc[0, "image_url"], "https://example.com/product.png")
        self.assertEqual(first_url({"url": "https://example.com/x.png"}), "https://example.com/x.png")


if __name__ == "__main__":
    unittest.main()
