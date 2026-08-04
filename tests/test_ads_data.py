from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd
from cryptography.fernet import Fernet

from ads_data import (
    build_ads_employee_summary,
    build_ads_employee_summary_from_reports,
    load_ads_snapshot,
    load_encrypted_ads_snapshot,
    save_ads_snapshot,
    save_encrypted_ads_snapshot,
    select_ads_summary,
)


class AdsDataTests(unittest.TestCase):
    def test_encrypted_ads_snapshot_round_trip_and_wrong_key_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "ads"
            encrypted = root / "published.enc"
            summary = pd.DataFrame(
                [{
                    "Nhân sự": "Owner A", "ASINs": 2, "Ads_Spend": 10.0,
                    "Ads_Sales": 25.0, "Ads_Orders": 3, "ACOS": 0.4,
                }]
            )
            save_ads_snapshot(
                source,
                summary,
                {"month": "2026-08", "store": "Wrappiness", "period_end": "2026-08-04"},
            )
            key = Fernet.generate_key().decode("utf-8")

            save_encrypted_ads_snapshot(source, encrypted, key)
            restored = load_encrypted_ads_snapshot(encrypted, key)

            self.assertIsNotNone(restored)
            assert restored is not None
            self.assertEqual(restored["imports"][0]["period_end"], "2026-08-04")
            self.assertEqual(restored["summary"].iloc[0]["Nhân sự"], "Owner A")
            wrong_key = Fernet.generate_key().decode("utf-8")
            self.assertIsNone(load_encrypted_ads_snapshot(encrypted, wrong_key))

    def test_any_campaign_containing_support_maps_to_nhi_support(self) -> None:
        reports = [pd.DataFrame([
            {
                "ASIN": "B000000001", "Campaign name": "Owner campaign",
                "Ads Type": "SP", "ad_spend": 100.0, "ad_sales": 400.0,
                "ad_orders": 8, "impressions": 1000, "clicks": 100,
            },
            {
                "ASIN": "B000000001", "Campaign name": "July NhiSupport campaign",
                "Ads Type": "SP", "ad_spend": 10.0, "ad_sales": 20.0,
                "ad_orders": 1, "impressions": 100, "clicks": 10,
            },
        ])]
        total = pd.DataFrame([{
            "asin": "B000000001", "record_id": "rec1", "ads_by": "Owner A",
            "custom_by": "", "fulfill_by": "FBM",
        }])

        summary, diagnostics = build_ads_employee_summary_from_reports(reports, total)
        indexed = summary.set_index("Nhân sự")

        self.assertEqual(indexed.loc["Owner A", "Ads_Spend"], 100)
        self.assertEqual(indexed.loc["Nhi-Support", "Ads_Spend"], 10)
        self.assertEqual(diagnostics["support_campaigns"], 1)

    def test_campaign_execution_markers_create_separate_rows(self) -> None:
        reports = [pd.DataFrame([
            {
                "ASIN": "B000000001", "Campaign name": "Owner campaign",
                "Ads Type": "SP", "ad_spend": 100.0, "ad_sales": 400.0,
                "ad_orders": 8, "impressions": 1000, "clicks": 100,
            },
            {
                "ASIN": "B000000001", "Campaign name": "Product-LINHAMZ-B000000001",
                "Ads Type": "SP", "ad_spend": 10.0, "ad_sales": 20.0,
                "ad_orders": 1, "impressions": 100, "clicks": 10,
            },
            {
                "ASIN": "B000000001", "Campaign name": "Product-HIEUAMZ-B000000001",
                "Ads Type": "SP", "ad_spend": 5.0, "ad_sales": 0.0,
                "ad_orders": 0, "impressions": 50, "clicks": 5,
            },
            {
                "ASIN": "B000000001", "Campaign name": "Product-HIEUMRND-B000000001",
                "Ads Type": "SP", "ad_spend": 6.0, "ad_sales": 12.0,
                "ad_orders": 1, "impressions": 60, "clicks": 6,
            },
            {
                "ASIN": "B000000001", "Campaign name": "Product-HAMRND-B000000001",
                "Ads Type": "SP", "ad_spend": 7.0, "ad_sales": 14.0,
                "ad_orders": 1, "impressions": 70, "clicks": 7,
            },
            {
                "ASIN": "B000000001", "Campaign name": "Product-Phrase-B000000001",
                "Ads Type": "SP", "ad_spend": 2.0, "ad_sales": 8.0,
                "ad_orders": 1, "impressions": 20, "clicks": 2,
            },
            {
                "ASIN": "B000000001", "Campaign name": "LINH Support-B000000001",
                "Ads Type": "SP", "ad_spend": 3.0, "ad_sales": 6.0,
                "ad_orders": 1, "impressions": 30, "clicks": 3,
            },
        ])]
        total = pd.DataFrame([{
            "asin": "B000000001", "record_id": "rec1", "ads_by": "Owner A",
            "custom_by": "", "fulfill_by": "FBM",
        }])

        summary, diagnostics = build_ads_employee_summary_from_reports(reports, total)
        indexed = summary.set_index("Nhân sự")

        self.assertEqual(indexed.loc["Owner A", "Ads_Spend"], 102)
        self.assertEqual(indexed.loc["Linh", "Ads_Spend"], 10)
        self.assertEqual(indexed.loc["Hieu", "Ads_Spend"], 11)
        self.assertEqual(indexed.loc["Ha", "Ads_Spend"], 7)
        self.assertEqual(indexed.loc["Nhi-Support", "Ads_Spend"], 3)
        self.assertAlmostEqual(summary["Ads_Spend"].sum(), 133)
        self.assertEqual(diagnostics["execution_by_assignee"]["Linh"]["campaigns"], 1)

    def test_complete_reports_map_support_fba_and_preserve_type_totals(self) -> None:
        reports = [
            pd.DataFrame([
                {
                    "ASIN": "B000000001", "Campaign name": "Owner campaign",
                    "Ads Type": "SP", "ad_spend": 100.0, "ad_sales": 400.0,
                    "ad_orders": 8, "impressions": 1000, "clicks": 100,
                },
                {
                    "ASIN": "B000000002", "Campaign name": "Nhi-Support-B000000002",
                    "Ads Type": "SP", "ad_spend": 10.0, "ad_sales": 20.0,
                    "ad_orders": 1, "impressions": 100, "clicks": 10,
                },
            ]),
            pd.DataFrame([
                {
                    "ASIN": "B000000003", "Campaign name": "FBA collection",
                    "Ads Type": "SB", "ad_spend": 20.0, "ad_sales": 80.0,
                    "ad_orders": 2, "impressions": 200, "clicks": 20,
                },
            ]),
        ]
        total = pd.DataFrame([
            {"asin": "B000000001", "record_id": "rec1", "ads_by": "Owner A", "custom_by": "", "fulfill_by": "FBM"},
            {"asin": "B000000002", "record_id": "rec2", "ads_by": "Owner B", "custom_by": "", "fulfill_by": "FBM"},
            {"asin": "B000000003", "record_id": "rec3", "ads_by": "Owner A", "custom_by": "Phương Linh/MRnD", "fulfill_by": "FBA"},
        ])

        summary, diagnostics = build_ads_employee_summary_from_reports(reports, total)
        indexed = summary.set_index("Nhân sự")

        self.assertEqual(indexed.loc["Owner A", "Ads_Spend"], 100)
        self.assertEqual(indexed.loc["Nhi-Support", "Ads_Spend"], 10)
        self.assertEqual(indexed.loc["Linh-FBA", "Ads_Spend"], 20)
        self.assertAlmostEqual(summary["Ads_Spend"].sum(), 130)
        self.assertEqual(diagnostics["by_type"]["SP"]["spend"], 110)
        self.assertEqual(diagnostics["by_type"]["SB"]["sales"], 80)

    def test_support_transfer_is_separate_and_preserves_totals(self) -> None:
        products = pd.DataFrame(
            [
                {"ASIN": "B000000001", "product_spend": 100.0, "product_sales": 400.0, "product_orders": 8},
                {"ASIN": "B000000002", "product_spend": 50.0, "product_sales": 100.0, "product_orders": 2},
                {"ASIN": "B000000003", "product_spend": 20.0, "product_sales": 80.0, "product_orders": 1},
            ]
        )
        support = pd.DataFrame(
            [
                {
                    "ASIN": "B000000001",
                    "Campaign name": "Nhi-Support-B000000001",
                    "support_spend": 10.0,
                    "support_sales": 20.0,
                    "support_orders": 1,
                },
                {
                    "ASIN": "B000000002",
                    "Campaign name": "Nhi-Support-B000000002",
                    "support_spend": 5.0,
                    "support_sales": 10.0,
                    "support_orders": 0,
                },
            ]
        )
        total = pd.DataFrame(
            [
                {"asin": "B000000001", "record_id": "rec1", "ads_by": "Owner A", "custom_by": "", "fulfill_by": "FBM"},
                {"asin": "B000000002", "record_id": "rec2", "ads_by": "Owner B", "custom_by": "", "fulfill_by": "FBM"},
                {"asin": "B000000003", "record_id": "rec3", "ads_by": "Owner B", "custom_by": "", "fulfill_by": "FBM"},
            ]
        )
        summary, diagnostics = build_ads_employee_summary(products, support, total)
        indexed = summary.set_index("Nhân sự")
        self.assertEqual(indexed.loc["Owner A", "Ads_Spend"], 90)
        self.assertEqual(indexed.loc["Owner B", "Ads_Sales"], 170)
        self.assertEqual(indexed.loc["Nhi-Support", "Ads_Spend"], 15)
        self.assertEqual(indexed.loc["Nhi-Support", "Ads_Sales"], 30)
        self.assertAlmostEqual(summary["Ads_Spend"].sum(), 170)
        self.assertAlmostEqual(summary["Ads_Sales"].sum(), 580)
        self.assertEqual(diagnostics["support_asins"], 2)

    def test_ads_snapshot_round_trip(self) -> None:
        summary = pd.DataFrame(
            [
                {
                    "Nhân sự": "Nhi-Support",
                    "ASINs": 2,
                    "Ads_Spend": 15.0,
                    "Ads_Sales": 30.0,
                    "Ads_Orders": 1,
                    "ACOS": 0.5,
                }
            ]
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            save_ads_snapshot(root, summary, {"month": "2026-07", "store": "Wrappiness"})
            restored = load_ads_snapshot(root)
        self.assertIsNotNone(restored)
        assert restored is not None
        self.assertEqual(restored["imports"][0]["month"], "2026-07")
        self.assertEqual(restored["summary"].loc[0, "Store"], "Wrappiness")
        self.assertEqual(restored["summary"].loc[0, "Ads_Spend"], 15)

    def test_fba_transfer_and_store_selection(self) -> None:
        products = pd.DataFrame([
            {"ASIN": "B000000001", "product_spend": 10.0, "product_sales": 25.0, "product_orders": 2},
            {"ASIN": "B000000002", "product_spend": 20.0, "product_sales": 100.0, "product_orders": 4},
        ])
        total = pd.DataFrame([
            {"asin": "B000000001", "record_id": "rec1", "ads_by": "Owner A", "custom_by": "Phương Linh/MRnD", "fulfill_by": "FBA"},
            {"asin": "B000000002", "record_id": "rec2", "ads_by": "Owner A", "custom_by": "Phương Linh/MRnD", "fulfill_by": "FBM"},
        ])
        empty_support = pd.DataFrame(columns=[
            "ASIN", "Campaign name", "support_spend", "support_sales", "support_orders"
        ])
        summary, diagnostics = build_ads_employee_summary(products, empty_support, total)
        indexed = summary.set_index("Nhân sự")
        self.assertEqual(indexed.loc["Linh-FBA", "Ads_Spend"], 10)
        self.assertEqual(indexed.loc["Owner A", "Ads_Spend"], 20)
        self.assertEqual(diagnostics["fba_asins"], 1)
        snapshot = {
            "summary": pd.concat([
                summary.assign(Month="2026-07", Store="Pawsionate"),
                summary.assign(Month="2026-07", Store="Wrappiness"),
            ], ignore_index=True),
            "imports": [
                {"month": "2026-07", "store": "Pawsionate"},
                {"month": "2026-07", "store": "Wrappiness"},
            ],
        }
        combined, imports = select_ads_summary(snapshot, "2026-07", "All Stores")
        self.assertEqual(combined.set_index("Nhân sự").loc["Linh-FBA", "Ads_Spend"], 20)
        self.assertEqual(len(imports), 2)

    def test_confirmed_fba_override_moves_ads_metrics_to_nhi_fba(self) -> None:
        products = pd.DataFrame([
            {
                "ASIN": "B0F1XZT333",
                "product_spend": 7.05,
                "product_sales": 33.98,
                "product_orders": 2,
            }
        ])
        total = pd.DataFrame([
            {
                "asin": "B0F1XZT333",
                "record_id": "rec_bad_fbm",
                "ads_by": "Trương Ý Nhi",
                "custom_by": "Trương Ý Nhi",
                "fulfill_by": "FBM",
            }
        ])
        empty_support = pd.DataFrame(columns=[
            "ASIN", "Campaign name", "support_spend", "support_sales", "support_orders"
        ])

        summary, diagnostics = build_ads_employee_summary(products, empty_support, total)
        indexed = summary.set_index("Nhân sự")

        self.assertEqual(indexed.loc["Nhi-FBA", "Ads_Spend"], 7.05)
        self.assertEqual(indexed.loc["Nhi-FBA", "Ads_Sales"], 33.98)
        self.assertEqual(diagnostics["fba_asins"], 1)


if __name__ == "__main__":
    unittest.main()
