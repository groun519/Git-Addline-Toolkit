import datetime as dt
import unittest
from pathlib import Path
import sys
from unittest.mock import call, patch

APP_DIR = Path(__file__).resolve().parents[1] / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from line_tracker import TrackerConfig, TrackerResult
from line_tracker_refresh import ProjectHistoryStats, build_refresh_snapshot, get_grass_date_range


class RefreshSnapshotTests(unittest.TestCase):
    @patch(
        "line_tracker_refresh._compute_project_history_stats",
        return_value=ProjectHistoryStats(120, 45, 240, 2, dt.date(2020, 1, 1)),
    )
    @patch("line_tracker_refresh._compute_overall_commit_count", return_value=98)
    @patch("line_tracker_refresh._compute_overall_active_days", return_value=12)
    @patch("line_tracker_refresh._compute_branch_active_days", return_value=3)
    @patch("line_tracker_refresh._get_branch_activity_start", return_value=dt.date.today())
    @patch("line_tracker_refresh._compute_branch_commit_count", return_value=4)
    @patch("line_tracker_refresh._compute_daily_commit_count", return_value=2)
    @patch("line_tracker_refresh.get_uncommitted_insertions_by_language", return_value={"Python": 7})
    @patch("line_tracker_refresh.get_project_language_lines", return_value={"C++": 4000, "JSON": 321})
    @patch("line_tracker_refresh.get_commit_counts_by_date_combined", return_value={})
    @patch("line_tracker_refresh.get_committed_deletions_by_date_combined", return_value={})
    @patch("line_tracker_refresh.get_committed_deletions", side_effect=[2, 6, 2])
    @patch("line_tracker_refresh.get_uncommitted_deletions", return_value=4)
    @patch(
        "line_tracker_refresh.get_committed_insertions_by_date_and_language_combined",
        return_value={},
    )
    @patch("line_tracker_refresh.get_committed_insertions_for_date_combined", return_value=3)
    @patch("line_tracker_refresh.get_total_deletions_up_to", return_value=12)
    @patch("line_tracker_refresh.resolve_base_commit", return_value="basehash")
    @patch("line_tracker_refresh.get_committed_insertions", return_value=5)
    @patch("line_tracker_refresh.resolve_current_ref", return_value="feature")
    @patch("line_tracker_refresh.compute_metrics")
    def test_build_refresh_snapshot_aggregates_metrics(
        self,
        mock_compute_metrics,
        _mock_current_ref,
        _mock_committed_insertions,
        _mock_base_commit,
        _mock_total_deletions_up_to,
        _mock_for_date,
        mock_by_date,
        _mock_uncommitted_deletions,
        _mock_committed_deletions,
        _mock_deletions_by_date,
        _mock_commit_counts_by_date,
        _mock_project_language_lines,
        _mock_uncommitted_language_lines,
        _mock_daily_commit_count,
        _mock_branch_commit_count,
        _mock_branch_activity_start,
        _mock_branch_active_days,
        _mock_overall_active_days,
        _mock_overall_commit_count,
        _mock_project_history_stats,
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
            today - dt.timedelta(days=2): {"C++": 1},
            today - dt.timedelta(days=1): {"JSON": 2},
            today: {"C++": 3},
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
        grass_start, grass_end = get_grass_date_range(today)
        grass_length = (grass_end - grass_start).days + 1

        self.assertEqual(snapshot.result, result)
        self.assertEqual(snapshot.author, "me")
        self.assertEqual(snapshot.tracked_ref, "origin/main")
        self.assertEqual(snapshot.current_ref, "feature")
        self.assertEqual(snapshot.base_ref, "basehash")
        self.assertEqual(snapshot.branch_total, 5)
        self.assertEqual(snapshot.branch_deletions, 2)
        self.assertEqual(snapshot.branch_active_days, 3)
        self.assertEqual(snapshot.daily_commit_count, 2)
        self.assertEqual(snapshot.branch_commit_count, 4)
        self.assertEqual(snapshot.overall_commit_count, 98)
        self.assertEqual(snapshot.project_commit_count, 240)
        self.assertEqual(snapshot.project_active_days, 2)
        self.assertEqual(snapshot.repository_birth_date, dt.date(2020, 1, 1))
        self.assertEqual(snapshot.overall_active_days, 12)
        self.assertEqual(snapshot.overall_deletions, 20)
        self.assertEqual(snapshot.project_total_lines, 4321)
        self.assertEqual(snapshot.project_cumulative_lines, 120)
        self.assertEqual(snapshot.project_cumulative_deletions, 45)
        self.assertEqual(snapshot.project_language_lines, {"C++": 4000, "JSON": 321})
        self.assertEqual(snapshot.overall_progress_language_lines, {"C++": 4000, "JSON": 321})
        self.assertEqual(snapshot.daily_progress_language_lines, {"C++": 3, "Python": 7})
        self.assertEqual(snapshot.today_done, 10)
        self.assertEqual(snapshot.today_target, 10)
        self.assertEqual(snapshot.uncommitted_deletions, 4)
        self.assertEqual(snapshot.points, [(today - dt.timedelta(days=2), 1), (today - dt.timedelta(days=1), 2), (today, 10)])
        self.assertEqual(snapshot.graph_added_points, snapshot.points)
        self.assertEqual(snapshot.graph_deleted_points, [(today - dt.timedelta(days=2), 0), (today - dt.timedelta(days=1), 0), (today, 4)])
        self.assertEqual(snapshot.graph_commit_points, [(today - dt.timedelta(days=2), 0), (today - dt.timedelta(days=1), 0), (today, 0)])
        self.assertEqual(
            snapshot.graph_language_points["C++"],
            [(today - dt.timedelta(days=2), 1), (today - dt.timedelta(days=1), 0), (today, 3)],
        )
        self.assertEqual(
            snapshot.graph_language_points["Python"],
            [(today - dt.timedelta(days=2), 0), (today - dt.timedelta(days=1), 0), (today, 7)],
        )
        self.assertEqual(len(snapshot.graph_available_added_points), 180)
        self.assertEqual(snapshot.graph_available_added_points[0][0], today - dt.timedelta(days=179))
        self.assertEqual(snapshot.graph_available_added_points[-1][0], today)
        self.assertEqual(dict(snapshot.graph_available_language_points["Python"])[today], 7)
        self.assertEqual(len(snapshot.grass_points), grass_length)
        self.assertEqual(snapshot.grass_points[0][0], grass_start)
        self.assertEqual(snapshot.grass_points[-1][0], grass_end)
        self.assertEqual(dict(snapshot.grass_points)[today], 10)
        self.assertEqual(snapshot.graph_max, 10)
        self.assertAlmostEqual(snapshot.graph_avg, 13 / 3)
        self.assertEqual(snapshot.share_text, "75.0%")

    @patch(
        "line_tracker_refresh._compute_project_history_stats",
        return_value=ProjectHistoryStats(120, 45, 240, 2, dt.date(2020, 1, 1)),
    )
    @patch("line_tracker_refresh._compute_overall_commit_count", return_value=98)
    @patch("line_tracker_refresh._compute_overall_active_days", return_value=12)
    @patch("line_tracker_refresh._compute_branch_active_days", return_value=3)
    @patch("line_tracker_refresh._get_branch_activity_start", return_value=dt.date.today())
    @patch("line_tracker_refresh._compute_branch_commit_count", return_value=4)
    @patch("line_tracker_refresh._compute_daily_commit_count", return_value=2)
    @patch("line_tracker_refresh.get_uncommitted_insertions_by_language", return_value={"Python": 7})
    @patch("line_tracker_refresh.get_project_language_lines", return_value={"C++": 4000, "JSON": 321})
    @patch("line_tracker_refresh.get_commit_counts_by_date_combined", return_value={})
    @patch("line_tracker_refresh.get_committed_deletions_by_date_combined", return_value={})
    @patch("line_tracker_refresh.get_committed_deletions", side_effect=[2, 6, 2])
    @patch("line_tracker_refresh.get_uncommitted_deletions", return_value=0)
    @patch(
        "line_tracker_refresh.get_committed_insertions_by_date_and_language_combined",
        return_value={},
    )
    @patch("line_tracker_refresh.get_committed_insertions_for_date_combined", return_value=3)
    @patch("line_tracker_refresh.get_total_deletions_up_to", return_value=12)
    @patch("line_tracker_refresh.resolve_base_commit", return_value="basehash")
    @patch("line_tracker_refresh.get_committed_insertions", return_value=5)
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
        _mock_total_deletions_up_to,
        mock_for_date,
        mock_by_date,
        _mock_uncommitted_deletions,
        _mock_committed_deletions,
        _mock_deletions_by_date,
        _mock_commit_counts_by_date,
        _mock_project_language_lines,
        _mock_uncommitted_language_lines,
        _mock_daily_commit_count,
        _mock_branch_commit_count,
        _mock_branch_activity_start,
        _mock_branch_active_days,
        _mock_overall_active_days,
        _mock_overall_commit_count,
        _mock_project_history_stats,
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
        mock_by_date.return_value = {today: {"C++": 3}}
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
        self.assertEqual(snapshot.branch_deletions, 2)
        self.assertEqual(snapshot.branch_active_days, 3)
        self.assertEqual(snapshot.daily_commit_count, 2)
        self.assertEqual(snapshot.branch_commit_count, 4)
        self.assertEqual(snapshot.overall_commit_count, 98)
        self.assertEqual(snapshot.project_commit_count, 240)
        self.assertEqual(snapshot.project_active_days, 2)
        self.assertEqual(snapshot.repository_birth_date, dt.date(2020, 1, 1))
        self.assertEqual(snapshot.overall_active_days, 12)
        self.assertEqual(snapshot.overall_deletions, 20)
        self.assertEqual(snapshot.project_total_lines, 4321)
        self.assertEqual(snapshot.project_cumulative_lines, 120)
        self.assertEqual(snapshot.project_cumulative_deletions, 45)
        self.assertEqual(snapshot.project_language_lines, {"C++": 4000, "JSON": 321})
        self.assertEqual(snapshot.overall_progress_language_lines, {"C++": 4000, "JSON": 321})
        self.assertEqual(snapshot.daily_progress_language_lines, {"C++": 3, "Python": 7})
        self.assertEqual(snapshot.today_done, 10)
        self.assertEqual(snapshot.share_text, "75.0%")
        mock_resolve_ref.assert_called_once_with(Path("C:/repo"), "auto")
        self.assertEqual(
            mock_committed_insertions.call_args_list,
            [
                call(Path("C:/repo"), "origin/main", "me", "feature"),
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
            min(today - dt.timedelta(days=2), dt.date(today.year, 1, 1)),
            dt.date(today.year, 12, 31),
            "me",
            "origin/main",
            True,
        )
