from __future__ import annotations

import importlib
from pathlib import Path
import unittest

from streamlit.testing.v1 import AppTest

import target_data
import lark_snapshot_store


class StreamlitHotReloadTests(unittest.TestCase):
    def test_app_recovers_when_snapshot_modules_were_cached_without_new_api(self) -> None:
        original_target = target_data.daily_targets_for_month
        original_lark = lark_snapshot_store.load_encrypted_lark_snapshot
        delattr(target_data, "daily_targets_for_month")
        delattr(lark_snapshot_store, "load_encrypted_lark_snapshot")
        try:
            app_path = Path(__file__).resolve().parents[1] / "streamlit_app.py"
            app = AppTest.from_file(str(app_path)).run(timeout=60)
            self.assertEqual([str(error.value) for error in app.exception], [])
            self.assertTrue(hasattr(target_data, "daily_targets_for_month"))
            self.assertTrue(
                hasattr(lark_snapshot_store, "load_encrypted_lark_snapshot")
            )
        finally:
            if not hasattr(target_data, "daily_targets_for_month"):
                target_data.daily_targets_for_month = original_target
            if not hasattr(lark_snapshot_store, "load_encrypted_lark_snapshot"):
                lark_snapshot_store.load_encrypted_lark_snapshot = original_lark
            importlib.reload(target_data)
            importlib.reload(lark_snapshot_store)


if __name__ == "__main__":
    unittest.main()
