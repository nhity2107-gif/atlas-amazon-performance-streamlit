from __future__ import annotations

import importlib
from pathlib import Path
import unittest

from streamlit.testing.v1 import AppTest

import target_data


class StreamlitHotReloadTests(unittest.TestCase):
    def test_app_recovers_when_target_module_was_cached_without_new_api(self) -> None:
        original = target_data.daily_targets_for_month
        delattr(target_data, "daily_targets_for_month")
        try:
            app_path = Path(__file__).resolve().parents[1] / "streamlit_app.py"
            app = AppTest.from_file(str(app_path)).run(timeout=60)
            self.assertEqual([str(error.value) for error in app.exception], [])
            self.assertTrue(hasattr(target_data, "daily_targets_for_month"))
        finally:
            if not hasattr(target_data, "daily_targets_for_month"):
                target_data.daily_targets_for_month = original
            importlib.reload(target_data)


if __name__ == "__main__":
    unittest.main()
