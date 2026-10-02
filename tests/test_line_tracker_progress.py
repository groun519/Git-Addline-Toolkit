import unittest
from pathlib import Path
import sys


APP_DIR = Path(__file__).resolve().parents[1] / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from line_tracker_presenters import build_progress_presentation, format_progress_percent


class ProgressPresentationTests(unittest.TestCase):
    @staticmethod
    def translate(key: str, **kwargs: object) -> str:
        translations = {
            "progress_breakdown": "Main {main} + Branch {branch} + Uncommitted {uncommitted}",
            "lines_suffix": " lines",
            "progress_goal_reached": "Goal reached",
        }
        return translations[key].format(**kwargs)

    def test_incomplete_progress_does_not_round_up_to_100_percent(self) -> None:
        presentation = build_progress_presentation(
            main_committed=89_647,
            branch_committed=0,
            uncommitted=0,
            goal=90_000,
            today_done=352,
            today_target=353,
            translate=self.translate,
        )

        self.assertEqual(presentation.overall_bar_text, "89,647 / 90,000 [99.6%]")
        self.assertEqual(presentation.daily_bar_text, "352 / 353 [99.7%]")

    def test_zero_daily_target_uses_goal_reached_text(self) -> None:
        presentation = build_progress_presentation(
            main_committed=30,
            branch_committed=10,
            uncommitted=5,
            goal=40,
            today_done=5,
            today_target=0,
            translate=self.translate,
        )

        self.assertEqual(presentation.overall_percent, 100.0)
        self.assertEqual(presentation.daily_percent, 100.0)
        self.assertEqual(presentation.overall_bar_text, "45 / 40 [100%]")
        self.assertEqual(presentation.daily_bar_text, "5 lines · Goal reached")
        self.assertEqual(presentation.breakdown_text, "Main 30 + Branch 10 + Uncommitted 5")

    def test_progress_percent_only_reports_100_for_complete_values(self) -> None:
        self.assertEqual(format_progress_percent(99.96, complete=False), "99.9")
        self.assertEqual(format_progress_percent(100.0, complete=True), "100")


if __name__ == "__main__":
    unittest.main()
