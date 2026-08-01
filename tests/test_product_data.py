from __future__ import annotations

import unittest

import pandas as pd

from product_data import (
    fulfillment_revenue_frame,
    records_from_order_hints,
    revenue_milestone_counts,
    top_record_id_frame,
)


class ProductDataTests(unittest.TestCase):
    def test_revenue_milestones_count_unique_owned_record_ids(self) -> None:
        records = pd.DataFrame([
            {"record_id": "rec1", "owner": "Alice", "Revenue": 700},
            {"record_id": "rec1", "owner": "Alice", "Revenue": 400},
            {"record_id": "rec2", "owner": "Alice", "Revenue": 3000},
            {"record_id": "rec3", "owner": "Alice", "Revenue": 5000},
            {"record_id": "rec4", "owner": "Bob", "Revenue": 999.99},
            {"record_id": "rec5", "owner": "Bob", "Revenue": 5000},
            {"record_id": "rec6", "owner": "Bob", "Revenue": 10000},
            {"record_id": "rec7", "owner": "Bob", "Revenue": 15000},
            {"record_id": "rec8", "owner": "Bob", "Revenue": 20000},
        ])

        result = revenue_milestone_counts(records, "owner").set_index("Nhân sự")

        self.assertEqual(result.loc["Alice", "Portfolio_Records_1000_Revenue"], 3)
        self.assertEqual(result.loc["Alice", "Portfolio_Records_3000_Revenue"], 2)
        self.assertEqual(result.loc["Alice", "Portfolio_Records_5000_Revenue"], 1)
        self.assertEqual(result.loc["Bob", "Portfolio_Records_1000_Revenue"], 4)
        self.assertEqual(result.loc["Bob", "Portfolio_Records_5000_Revenue"], 4)
        self.assertEqual(result.loc["Bob", "Portfolio_Records_10000_Revenue"], 3)
        self.assertEqual(result.loc["Bob", "Portfolio_Records_15000_Revenue"], 2)
        self.assertEqual(result.loc["Bob", "Portfolio_Records_20000_Revenue"], 1)

    def test_revenue_is_grouped_and_all_employee_roles_are_mapped(self) -> None:
        records = pd.DataFrame(
            [
                {
                    "record_id": "recA",
                    "idea_by": "Ivy",
                    "managed_by": "Alice",
                    "custom_by": "Carol",
                    "ads_by": "Adam",
                    "Revenue": 100,
                    "Orders": 2,
                    "Units": 3,
                    "asin_count": 1,
                },
                {"record_id": "recA", "managed_by": "", "Revenue": 50, "Orders": 1, "Units": 1, "asin_count": 1},
                {"record_id": "recB", "managed_by": "", "Revenue": 80, "Orders": 1, "Units": 1, "asin_count": 1},
            ]
        )

        result = top_record_id_frame(records, total_revenue=230)

        self.assertEqual(result["Record ID"].tolist(), ["recA", "recB"])
        self.assertEqual(result["Revenue"].tolist(), [150, 80])
        self.assertEqual(result["ASIN count"].tolist(), [2, 1])
        self.assertEqual(result["Idea By"].tolist(), ["Ivy", ""])
        self.assertEqual(result["Managed By"].tolist(), ["Alice", ""])
        self.assertEqual(result["Custom By"].tolist(), ["Carol", ""])
        self.assertEqual(result["Ads By"].tolist(), ["Adam", ""])

    def test_only_top_50_record_ids_are_returned(self) -> None:
        records = pd.DataFrame(
            [
                {"record_id": f"rec{index:02d}", "Revenue": index, "Orders": 1, "Units": 1, "asin_count": 1}
                for index in range(60)
            ]
        )

        result = top_record_id_frame(records, total_revenue=float(records["Revenue"].sum()))

        self.assertEqual(len(result), 50)
        self.assertEqual(result.iloc[0]["Record ID"], "rec59")
        self.assertEqual(result.iloc[-1]["Record ID"], "rec10")

    def test_order_hints_create_records_without_employee_names(self) -> None:
        performance = pd.DataFrame(
            [
                {"ASIN": "A1", "record_id_hint": "recA", "Revenue": 10, "Orders": 1, "Units": 1},
                {"ASIN": "A2", "record_id_hint": "recA", "Revenue": 20, "Orders": 1, "Units": 2},
            ]
        )

        result = top_record_id_frame(
            records_from_order_hints(performance),
            total_revenue=30,
        )

        self.assertEqual(result.loc[0, "Record ID"], "recA")
        self.assertEqual(result.loc[0, "Revenue"], 30)
        self.assertEqual(result.loc[0, "ASIN count"], 2)
        self.assertEqual(result.loc[0, "Idea By"], "")
        self.assertEqual(result.loc[0, "Managed By"], "")
        self.assertEqual(result.loc[0, "Custom By"], "")
        self.assertEqual(result.loc[0, "Ads By"], "")

    def test_fulfillment_revenue_uses_asin_then_record_hint(self) -> None:
        performance = pd.DataFrame([
            {"ASIN": "B000000001", "record_id_hint": "rec1", "Revenue": 100, "Orders": 2, "Units": 3},
            {"ASIN": "B000000099", "record_id_hint": "rec2", "Revenue": 50, "Orders": 1, "Units": 1},
        ])
        total = pd.DataFrame([
            {"asin": "B000000001", "record_id": "rec1", "fulfill_by": "FBA"},
            {"asin": "B000000002", "record_id": "rec2", "fulfill_by": "FBM"},
        ])
        result = fulfillment_revenue_frame(performance, total).set_index("Fulfill By")
        self.assertEqual(result.loc["FBA", "Revenue"], 100)
        self.assertEqual(result.loc["FBM", "Revenue"], 50)
        self.assertNotIn("Unmapped", result.index)

    def test_confirmed_fba_asin_override_corrects_bad_total_asin_value(self) -> None:
        performance = pd.DataFrame([
            {
                "ASIN": "B0F1XPZ1JX",
                "record_id_hint": "rec_bad_fbm",
                "Revenue": 100,
                "Orders": 2,
                "Units": 3,
            }
        ])
        total = pd.DataFrame([
            {
                "asin": "B0F1XPZ1JX",
                "record_id": "rec_bad_fbm",
                "fulfill_by": "FBM",
            }
        ])

        result = fulfillment_revenue_frame(performance, total).set_index("Fulfill By")

        self.assertEqual(result.loc["FBA", "Revenue"], 100)
        self.assertNotIn("FBM", result.index)


if __name__ == "__main__":
    unittest.main()
