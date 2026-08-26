from __future__ import annotations

import importlib
from pathlib import Path
import unittest

from streamlit.testing.v1 import AppTest

import target_data
import lark_snapshot_store
import ads_data


class StreamlitHotReloadTests(unittest.TestCase):
    def test_team_kpi_has_no_password_gate(self) -> None:
        app_path = Path(__file__).resolve().parents[1] / "streamlit_app.py"
        source = app_path.read_text(encoding="utf-8")
        self.assertNotIn("DASHBOARD_PASSWORD", source)
        self.assertNotIn("Mật khẩu Team KPI", source)
        self.assertNotIn("Mở Team KPI", source)

    def test_overview_uses_local_or_published_lark_snapshot(self) -> None:
        app_path = Path(__file__).resolve().parents[1] / "streamlit_app.py"
        source = app_path.read_text(encoding="utf-8")

        self.assertIn("def saved_lark_frames()", source)
        self.assertIn("overview_lark = saved_lark_frames()", source)

    def test_app_recovers_when_snapshot_modules_were_cached_without_new_api(self) -> None:
        original_target = target_data.daily_targets_for_month
        original_lark = lark_snapshot_store.load_encrypted_lark_snapshot
        original_ads = ads_data.load_encrypted_ads_snapshot_with_keys
        delattr(target_data, "daily_targets_for_month")
        delattr(lark_snapshot_store, "load_encrypted_lark_snapshot")
        delattr(ads_data, "load_encrypted_ads_snapshot_with_keys")
        try:
            app_path = Path(__file__).resolve().parents[1] / "streamlit_app.py"
            app = AppTest.from_file(str(app_path)).run(timeout=60)
            self.assertEqual([str(error.value) for error in app.exception], [])
            self.assertTrue(hasattr(target_data, "daily_targets_for_month"))
            self.assertTrue(
                hasattr(lark_snapshot_store, "load_encrypted_lark_snapshot")
            )
            self.assertTrue(
                hasattr(ads_data, "load_encrypted_ads_snapshot_with_keys")
            )
        finally:
            if not hasattr(target_data, "daily_targets_for_month"):
                target_data.daily_targets_for_month = original_target
            if not hasattr(lark_snapshot_store, "load_encrypted_lark_snapshot"):
                lark_snapshot_store.load_encrypted_lark_snapshot = original_lark
            if not hasattr(ads_data, "load_encrypted_ads_snapshot_with_keys"):
                ads_data.load_encrypted_ads_snapshot_with_keys = original_ads
            importlib.reload(target_data)
            importlib.reload(lark_snapshot_store)
            importlib.reload(ads_data)


if __name__ == "__main__":
    unittest.main()
