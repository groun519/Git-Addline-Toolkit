import unittest
from pathlib import Path
import sys
from unittest.mock import patch


APP_DIR = Path(__file__).resolve().parents[1] / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from line_tracker import (
    classify_text_language,
    get_project_language_lines,
    merge_language_totals,
    parse_numstat_insertions_by_language,
)


class LanguageLineTests(unittest.TestCase):
    def test_classify_text_language_groups_cpp_headers_and_unreal_json_files(self) -> None:
        self.assertEqual(classify_text_language("Source/Player.cpp"), "C++")
        self.assertEqual(classify_text_language("Source/Player.h"), "C++")
        self.assertEqual(classify_text_language("Config/data.json"), "JSON")
        self.assertEqual(classify_text_language("Project.uproject"), "JSON")
        self.assertEqual(classify_text_language("Unknown/file.xyz"), "Other")

    def test_parse_numstat_insertions_by_language_groups_text_changes(self) -> None:
        result = parse_numstat_insertions_by_language(
            "12\t2\tSource/Player.cpp\n"
            "3\t0\tSource/Player.h\n"
            "8\t1\tData/config.json\n"
            "5\t0\tmisc.xyz\n"
            "40\t0\tContent/Asset.uasset\n"
            "-\t-\tContent/Binary.bin\n"
        )

        self.assertEqual(result, {"C++": 15, "JSON": 8, "Other": 5})

    def test_merge_language_totals_preserves_display_order(self) -> None:
        result = merge_language_totals(
            {"Python": 4, "C++": 7},
            {"C++": 3, "Other": 2},
        )

        self.assertEqual(result, {"C++": 10, "Python": 4, "Other": 2})

    @patch("line_tracker.count_text_lines")
    @patch("line_tracker.run_git")
    def test_get_project_language_lines_returns_only_present_text_groups(self, mock_run_git, mock_count_lines) -> None:
        mock_run_git.return_value = (
            "Source/Player.cpp\0Source/Player.h\0Data/config.json\0"
            "Docs/readme.md\0Content/Asset.uasset\0misc.xyz\0"
        )
        line_counts = {
            ".cpp": 120,
            ".h": 30,
            ".json": 20,
            ".md": 10,
            ".xyz": 5,
        }
        mock_count_lines.side_effect = lambda path: line_counts.get(path.suffix.lower(), 0)

        result = get_project_language_lines(Path("C:/repo"))

        self.assertEqual(
            result,
            {
                "C++": 150,
                "JSON": 20,
                "Docs": 10,
                "Other": 5,
            },
        )
        self.assertNotIn("Content/Asset.uasset", [str(call.args[0]) for call in mock_count_lines.call_args_list])


if __name__ == "__main__":
    unittest.main()
