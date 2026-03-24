from __future__ import annotations

import unittest

from line_tracker_version import APP_VERSION, DEFAULT_APP_VERSION, format_app_title


class VersionTests(unittest.TestCase):
    def test_app_version_uses_expected_v_format(self) -> None:
        self.assertRegex(APP_VERSION, r"^V\d+\.\d+\.\d{3}$")

    def test_default_version_matches_current_version_format(self) -> None:
        self.assertRegex(DEFAULT_APP_VERSION, r"^V\d+\.\d+\.\d{3}$")

    def test_formatted_title_appends_version(self) -> None:
        self.assertEqual(format_app_title("Line Tracker"), f"Line Tracker {APP_VERSION}")


if __name__ == "__main__":
    unittest.main()
