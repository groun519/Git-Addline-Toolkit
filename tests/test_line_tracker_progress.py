import datetime as dt
import unittest
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock


APP_DIR = Path(__file__).resolve().parents[1] / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from line_tracker import TrackerResult
from line_tracker_ui import LineTrackerApp


class _ValueHolder:
    def __init__(self) -> None:
        self.value = ""

    def set(self, value: str) -> None:
        self.value = value


class ProgressBarTests(unittest.TestCase):
    def test_incomplete_progress_does_not_round_up_to_100_percent(self) -> None:
        translations = {
            "progress_breakdown": "Main {main} + Branch {branch} + Uncommitted {uncommitted}",
            "lines_suffix": " lines",
            "progress_goal_reached": "Goal reached",
        }
        app = SimpleNamespace(
            main_total_committed=89_647,
            branch_total_committed=0,
            goal=90_000,
            overall_progress_text_var=_ValueHolder(),
            progress_bar_percents={"overall": 0.0, "daily": 0.0},
            progress_bar_texts={"overall": "", "daily": ""},
            set_progress_language_lines=Mock(),
            redraw_progress_bars=Mock(),
            format_progress_percent=LineTrackerApp.format_progress_percent,
        )
        app.t = lambda key, **kwargs: translations[key].format(**kwargs)
        today = dt.date.today()
        result = TrackerResult(
            today=today,
            month_end=today,
            days_left_including_today=1,
            days_left_after_today=0,
            committed_total=89_647,
            uncommitted_insertions=0,
            need_today=353,
            need_after_commit=353,
        )

        LineTrackerApp.update_progress(app, result, 352, 353, {}, {})

        self.assertEqual(app.progress_bar_texts["overall"], "89,647 / 90,000 [99.6%]")
        self.assertEqual(app.progress_bar_texts["daily"], "352 / 353 [99.7%]")

    def test_hover_only_opens_tooltip_over_colored_segment(self) -> None:
        app = SimpleNamespace(
            progress_bar_segments={"daily": [(1, 40, "C++")]},
            progress_language_hover_key="",
            show_progress_language_tooltip=Mock(),
            hide_progress_language_tooltip=Mock(),
        )
        widget = object()

        LineTrackerApp.on_progress_bar_motion(app, SimpleNamespace(x=20, widget=widget), "daily")
        app.show_progress_language_tooltip.assert_called_once_with(widget, "daily", "C++")

        app.show_progress_language_tooltip.reset_mock()
        app.progress_language_hover_key = "daily:C++"
        LineTrackerApp.on_progress_bar_motion(app, SimpleNamespace(x=80, widget=widget), "daily")
        app.show_progress_language_tooltip.assert_not_called()
        app.hide_progress_language_tooltip.assert_called_once_with()

    def test_zero_daily_target_uses_goal_reached_text(self) -> None:
        translations = {
            "progress_breakdown": "Main {main} + Branch {branch} + Uncommitted {uncommitted}",
            "lines_suffix": " lines",
            "progress_goal_reached": "Goal reached",
        }
        app = SimpleNamespace(
            main_total_committed=30,
            branch_total_committed=10,
            goal=40,
            overall_progress_text_var=_ValueHolder(),
            progress_bar_percents={"overall": 0.0, "daily": 0.0},
            progress_bar_texts={"overall": "", "daily": ""},
            set_progress_language_lines=Mock(),
            redraw_progress_bars=Mock(),
            format_progress_percent=LineTrackerApp.format_progress_percent,
        )
        app.t = lambda key, **kwargs: translations[key].format(**kwargs)
        today = dt.date.today()
        result = TrackerResult(
            today=today,
            month_end=today,
            days_left_including_today=1,
            days_left_after_today=0,
            committed_total=40,
            uncommitted_insertions=5,
            need_today=0,
            need_after_commit=0,
        )

        LineTrackerApp.update_progress(app, result, 5, 0, {"C++": 45}, {"C++": 5})

        self.assertEqual(app.progress_bar_percents["overall"], 100.0)
        self.assertEqual(app.progress_bar_percents["daily"], 100.0)
        self.assertEqual(app.progress_bar_texts["overall"], "45 / 40 [100%]")
        self.assertEqual(app.progress_bar_texts["daily"], "5 lines · Goal reached")
        self.assertEqual(app.overall_progress_text_var.value, "Main 30 + Branch 10 + Uncommitted 5")
        app.set_progress_language_lines.assert_called_once_with({"C++": 45}, {"C++": 5})
        app.redraw_progress_bars.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
