from __future__ import annotations

import datetime as dt
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from line_tracker import CommitChangeEntry, TrackerConfig
from line_tracker_settings import UISettings
from line_tracker_startup import build_startup_payload
from qt_app.main import _has_explicit_repo


class StartupPayloadTests(unittest.TestCase):
    def test_explicit_repo_detection_accepts_split_and_inline_arguments(self) -> None:
        self.assertTrue(_has_explicit_repo(["--repo", "C:/repo"]))
        self.assertTrue(_has_explicit_repo(["--repo=C:/repo"]))
        self.assertFalse(_has_explicit_repo([]))

    def test_startup_payload_preloads_snapshot_schedule_and_history(self) -> None:
        repo = Path("C:/repo")
        settings = UISettings(schedule_path="work-plan.md")
        config = TrackerConfig(repo=repo, author="auto")
        snapshot = SimpleNamespace(
            author="resolved-author",
            tracked_ref="origin/main",
            current_ref="feature/startup",
            base_ref="basehash",
        )
        history = [
            CommitChangeEntry(
                commit_hash="hash",
                short_hash="abc1234",
                date=dt.date(2026, 8, 4),
                subject="Startup flow",
                insertions=10,
                deletions=2,
            )
        ]
        progress_events: list[tuple[int, str]] = []

        def build_snapshot(_repo, _author, _config, _days, progress=None):
            progress(50, "branch")
            return snapshot

        with (
            patch("line_tracker_startup.build_refresh_snapshot", side_effect=build_snapshot),
            patch("line_tracker_startup.resolve_schedule_path", return_value=None),
            patch("line_tracker_startup.get_commit_change_entries", return_value=history) as load_history,
        ):
            payload = build_startup_payload(
                repo,
                settings,
                config,
                30,
                lambda value, stage: progress_events.append((value, stage)),
            )

        self.assertIs(payload.snapshot, snapshot)
        self.assertEqual(payload.history_entries, tuple(history))
        self.assertTrue(payload.history_exhausted)
        load_history.assert_called_once_with(
            repo,
            "resolved-author",
            "feature/startup",
            exclude_ref="basehash",
            limit=40,
        )
        self.assertEqual(progress_events[0], (5, "repository"))
        self.assertEqual(progress_events[-1], (100, "ready"))
        self.assertEqual([value for value, _stage in progress_events], sorted(value for value, _stage in progress_events))


if __name__ == "__main__":
    unittest.main()
