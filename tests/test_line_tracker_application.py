import datetime as dt
import tempfile
import unittest
from pathlib import Path
import sys
from unittest.mock import Mock, patch, sentinel


APP_DIR = Path(__file__).resolve().parents[1] / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from line_tracker import TrackerConfig, get_commit_detail
from line_tracker_authors import build_author_option_entries, parse_shortlog_identities
from line_tracker_controller import RefreshCoordinator
from line_tracker_graph import flatten_graph_points, smooth_graph_points, summarize_graph_values
from line_tracker_presenters import build_progress_presentation
from line_tracker_process import CommandCancelledError, raise_if_command_cancelled
from line_tracker_repository import find_repo_root_from_metadata
from line_tracker_settings import UISettings, load_ui_settings, save_ui_settings


class ApplicationBoundaryTests(unittest.TestCase):
    def test_commit_detail_parses_metadata_text_and_binary_file_changes(self) -> None:
        metadata = (
            "fullhash\x00abc1234\x002026-08-04T21:30:00+09:00\x00Groun\x00groun@example.com\x00"
            "Commit subject\x00Detailed body\n"
        )
        numstat = "12\t3\tapp/main.py\n-\t-\tassets/icon.png\n"

        with patch("line_tracker.run_git", side_effect=(metadata, numstat)) as run:
            detail = get_commit_detail(Path("C:/repo"), "fullhash")

        self.assertEqual(detail.subject, "Commit subject")
        self.assertEqual(detail.body, "Detailed body")
        self.assertEqual(detail.author_name, "Groun")
        self.assertEqual((detail.insertions, detail.deletions), (12, 3))
        self.assertEqual(len(detail.files), 2)
        self.assertTrue(detail.files[1].is_binary)
        self.assertEqual(run.call_count, 2)

    def test_find_repo_root_from_metadata_does_not_require_git_process(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = Path(tmp_dir) / "repo"
            nested = repo / "tools" / "app"
            nested.mkdir(parents=True)
            (repo / ".git").mkdir()

            self.assertEqual(find_repo_root_from_metadata(nested), repo.resolve())

            (repo / ".git").rmdir()
            (repo / ".git").write_text("gitdir: ../metadata", encoding="ascii")
            self.assertEqual(find_repo_root_from_metadata(nested), repo.resolve())

    def test_settings_roundtrip_without_ui_objects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings_path = Path(tmp_dir) / "settings.json"
            settings = UISettings(repo_path="C:/repo", lang="en", theme="slate", goal=321)

            self.assertTrue(save_ui_settings(settings_path, settings))
            loaded = load_ui_settings(settings_path, Path(tmp_dir) / "legacy.json")

        self.assertEqual(loaded, settings)

    def test_settings_replace_failure_preserves_previous_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings_path = Path(tmp_dir) / "settings.json"
            original = UISettings(repo_path="C:/original")
            updated = UISettings(repo_path="C:/updated")
            self.assertTrue(save_ui_settings(settings_path, original))

            with patch("line_tracker_io.os.replace", side_effect=OSError("locked")):
                saved = save_ui_settings(settings_path, updated)

            self.assertFalse(saved)
            self.assertEqual(
                load_ui_settings(settings_path, Path(tmp_dir) / "legacy.json"),
                original,
            )
            self.assertEqual(list(Path(tmp_dir).glob("*.tmp")), [])

    def test_author_options_parse_shortlog_without_ui_objects(self) -> None:
        identities = parse_shortlog_identities(
            "  2\tgroun519 <54619610+groun519@users.noreply.github.com>\n"
            "  5\tgroun519 <groun519@gmail.com>\n"
        )

        options, mapping, _aliases = build_author_option_entries(identities, "Auto", "All")

        self.assertEqual(options, ["Auto", "All", "groun519 <groun519@gmail.com>"])
        self.assertIn("groun519 <groun519@gmail.com>", mapping)

    def test_progress_presentation_is_framework_independent(self) -> None:
        translations = {
            "progress_breakdown": "Main {main} + Branch {branch} + Uncommitted {uncommitted}",
            "lines_suffix": " lines",
            "progress_goal_reached": "Goal reached",
        }
        translate = lambda key, **kwargs: translations[key].format(**kwargs)

        presentation = build_progress_presentation(
            main_committed=89_000,
            branch_committed=647,
            uncommitted=0,
            goal=90_000,
            today_done=352,
            today_target=353,
            translate=translate,
        )

        self.assertEqual(presentation.overall_bar_text, "89,647 / 90,000 [99.6%]")
        self.assertEqual(presentation.daily_bar_text, "352 / 353 [99.7%]")
        self.assertEqual(presentation.breakdown_text, "Main 89,000 + Branch 647 + Uncommitted 0")

    def test_graph_helpers_preserve_endpoints(self) -> None:
        points = [(0.0, 10.0), (10.0, 0.0), (20.0, 10.0)]

        smoothed = smooth_graph_points(points, 35.0)

        self.assertEqual(smoothed[0], points[0])
        self.assertEqual(smoothed[-1], points[-1])
        self.assertGreater(len(smoothed), len(points))
        self.assertEqual(len(flatten_graph_points(smoothed)), len(smoothed) * 2)
        graph_points = [(dt.date(2026, 8, 1), 10), (dt.date(2026, 8, 2), 20)]
        self.assertEqual(summarize_graph_values(graph_points), (15.0, 20))

    def test_refresh_coordinator_blocks_overlap_and_dispatches_success(self) -> None:
        pending: list[object] = []
        success = Mock()
        failure = Mock()
        builder = Mock(return_value=sentinel.snapshot)
        coordinator = RefreshCoordinator(
            pending.append,
            snapshot_builder=builder,
            thread_starter=lambda target: target(),
        )
        config = TrackerConfig(repo=Path("C:/repo"))

        request_id = coordinator.start(
            repo=config.repo,
            author="me",
            config=config,
            graph_days=14,
            on_success=success,
            on_failure=failure,
        )
        overlapping_id = coordinator.start(
            repo=config.repo,
            author="me",
            config=config,
            graph_days=14,
            on_success=success,
            on_failure=failure,
        )

        self.assertEqual(request_id, 1)
        self.assertIsNone(overlapping_id)
        self.assertTrue(coordinator.is_running)
        pending.pop(0)()
        self.assertFalse(coordinator.is_running)
        success.assert_called_once_with(1, sentinel.snapshot)
        failure.assert_not_called()

    def test_refresh_coordinator_drops_invalidated_result(self) -> None:
        pending: list[object] = []
        success = Mock()
        coordinator = RefreshCoordinator(
            pending.append,
            snapshot_builder=Mock(return_value=sentinel.snapshot),
            thread_starter=lambda target: target(),
        )
        config = TrackerConfig(repo=Path("C:/repo"))
        coordinator.start(
            repo=config.repo,
            author="me",
            config=config,
            graph_days=14,
            on_success=success,
            on_failure=Mock(),
        )

        coordinator.invalidate()
        pending.pop(0)()

        success.assert_not_called()
        self.assertFalse(coordinator.is_running)

    def test_refresh_coordinator_cancels_invalidated_worker_commands(self) -> None:
        worker_targets: list[object] = []
        pending: list[object] = []
        failure = Mock()
        cancellation_observed: list[bool] = []

        def builder(*_args: object) -> object:
            try:
                raise_if_command_cancelled()
            except CommandCancelledError:
                cancellation_observed.append(True)
                raise
            return sentinel.snapshot

        coordinator = RefreshCoordinator(
            pending.append,
            snapshot_builder=builder,
            thread_starter=worker_targets.append,
        )
        config = TrackerConfig(repo=Path("C:/repo"))
        coordinator.start(
            repo=config.repo,
            author="me",
            config=config,
            graph_days=14,
            on_success=Mock(),
            on_failure=failure,
        )

        coordinator.invalidate()
        with patch.object(coordinator, "_dispatch", side_effect=lambda callback: callback()):
            worker_targets.pop(0)()

        self.assertEqual(cancellation_observed, [True])
        failure.assert_not_called()
        self.assertFalse(coordinator.is_running)


if __name__ == "__main__":
    unittest.main()
