import datetime as dt
import unittest
from pathlib import Path
import sys
from unittest.mock import call, patch

APP_DIR = Path(__file__).resolve().parents[1] / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from line_tracker import TrackerConfig, TrackerResult
from line_tracker_refresh import build_refresh_snapshot


class RefreshSnapshotTests(unittest.TestCase):
    @patch("line_tracker_refresh.get_uncommitted_deletions", return_value=4)
    @patch(
        "line_tracker_refresh.get_committed_insertions_by_date_combined",
        return_value={},
    )
    @patch("line_tracker_refresh.get_committed_insertions_for_date_combined", return_value=3)
    @patch("line_tracker_refresh.get_total_insertions_up_to", return_value=60)
    @patch("line_tracker_refresh.resolve_base_commit", return_value="basehash")
    @patch("line_tracker_refresh.get_committed_insertions", side_effect=[5, 40, 20])
    @patch("line_tracker_refresh.resolve_current_ref", return_value="feature")
    @patch("line_tracker_refresh.compute_metrics")
    def test_build_refresh_snapshot_aggregates_metrics(
        self,
        mock_compute_metrics,
        _mock_current_ref,
        _mock_committed_insertions,
        _mock_base_commit,
        _mock_total_up_to,
        _mock_for_date,
        mock_by_date,
        _mock_uncommitted_deletions,
    ) -> None:
        today = dt.date.today()
        result = TrackerResult(
            today=today,
            month_end=today,
            days_left_including_today=1,
            days_left_after_today=0,
            committed_total=90,
            uncommitted_insertions=7,
            need_today=10,
            need_after_commit=0,
        )
        mock_compute_metrics.return_value = result
        mock_by_date.return_value = {
            today - dt.timedelta(days=2): 1,
            today - dt.timedelta(days=1): 2,
            today: 3,
        }
        config = TrackerConfig(
            repo=Path("C:/repo"),
            goal=200,
            base_total=100,
            base_commit="auto",
            author="me",
            ref="origin/main",
            include_local=True,
            today=today,
            month_end=today,
        )

        snapshot = build_refresh_snapshot(Path("C:/repo"), "me", config, graph_days=3)

        self.assertEqual(snapshot.result, result)
        self.assertEqual(snapshot.branch_total, 5)
        self.assertEqual(snapshot.today_done, 10)
        self.assertEqual(snapshot.today_target, 10)
        self.assertEqual(snapshot.uncommitted_deletions, 4)
        self.assertEqual(snapshot.points, [(today - dt.timedelta(days=2), 1), (today - dt.timedelta(days=1), 2), (today, 10)])
        self.assertEqual(snapshot.graph_max, 10)
        self.assertAlmostEqual(snapshot.graph_avg, 13 / 3)
        self.assertEqual(snapshot.share_text, "75.0%")

    @patch("line_tracker_refresh.get_uncommitted_deletions", return_value=0)
    @patch(
        "line_tracker_refresh.get_committed_insertions_by_date_combined",
        return_value={},
    )
    @patch("line_tracker_refresh.get_committed_insertions_for_date_combined", return_value=3)
    @patch("line_tracker_refresh.get_total_insertions_up_to", return_value=60)
    @patch("line_tracker_refresh.resolve_base_commit", return_value="basehash")
    @patch("line_tracker_refresh.get_committed_insertions", side_effect=[5, 40, 20])
    @patch("line_tracker_refresh.resolve_current_ref", return_value="feature")
    @patch("line_tracker_refresh.resolve_ref", return_value="origin/main")
    @patch("line_tracker_refresh.compute_metrics")
    def test_build_refresh_snapshot_resolves_auto_ref_before_git_calls(
        self,
        mock_compute_metrics,
        mock_resolve_ref,
        _mock_current_ref,
        mock_committed_insertions,
        _mock_base_commit,
        _mock_total_up_to,
        mock_for_date,
        mock_by_date,
        _mock_uncommitted_deletions,
    ) -> None:
        today = dt.date.today()
        result = TrackerResult(
            today=today,
            month_end=today,
            days_left_including_today=1,
            days_left_after_today=0,
            committed_total=90,
            uncommitted_insertions=7,
            need_today=10,
            need_after_commit=0,
        )
        mock_compute_metrics.return_value = result
        config = TrackerConfig(
            repo=Path("C:/repo"),
            goal=200,
            base_total=100,
            base_commit="auto",
            author="me",
            ref="auto",
            include_local=True,
            today=today,
            month_end=today,
        )

        snapshot = build_refresh_snapshot(Path("C:/repo"), "me", config, graph_days=3)

        self.assertEqual(snapshot.branch_total, 5)
        self.assertEqual(snapshot.today_done, 10)
        self.assertEqual(snapshot.share_text, "75.0%")
        mock_resolve_ref.assert_called_once_with(Path("C:/repo"), "auto")
        self.assertEqual(
            mock_committed_insertions.call_args_list,
            [
                call(Path("C:/repo"), "origin/main", "me", "feature"),
                call(Path("C:/repo"), "basehash", "", "origin/main"),
                call(Path("C:/repo"), "origin/main", "", "feature"),
            ],
        )
        mock_for_date.assert_called_once_with(
            Path("C:/repo"),
            today,
            "me",
            "origin/main",
            True,
        )
        mock_by_date.assert_called_once_with(
            Path("C:/repo"),
            today - dt.timedelta(days=2),
            today,
            "me",
            "origin/main",
            True,
        )
