import datetime as dt
import os
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1] / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from line_tracker import TrackerConfig, encode_author_patterns, list_branch_refs, resolve_git_executable
from line_tracker_presenters import build_dashboard_presentation
from line_tracker_refresh import build_refresh_snapshot, get_branch_union_stats, includes_tracked_branch


class BranchUnionTests(unittest.TestCase):
    def test_other_remote_with_same_branch_name_is_not_the_tracked_branch(self) -> None:
        self.assertTrue(includes_tracked_branch("origin/develop", ("develop", "feature")))
        self.assertTrue(includes_tracked_branch("origin/develop", ("origin/develop",)))
        self.assertFalse(includes_tracked_branch("origin/develop", ("upstream/develop",)))

    def test_selected_develop_and_feature_drive_stats_and_graph(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            git = resolve_git_executable()

            def run(*args: str, day: str = "2026-08-31") -> str:
                environment = os.environ.copy()
                environment["GIT_AUTHOR_DATE"] = f"{day}T12:00:00+00:00"
                environment["GIT_COMMITTER_DATE"] = f"{day}T12:00:00+00:00"
                result = subprocess.run([git, *args], cwd=repo, env=environment, check=True, capture_output=True, text=True)
                return result.stdout.strip()

            run("init")
            run("config", "user.name", "Alice")
            run("config", "user.email", "alice@example.com")
            source = repo / "file.txt"
            source.write_text("one\n", encoding="utf-8")
            run("add", "file.txt")
            run("commit", "-m", "base")
            run("branch", "-M", "develop")
            base_hash = run("rev-parse", "HEAD")
            source.write_text("one\ntwo\n", encoding="utf-8")
            run("commit", "-am", "develop first", day="2026-09-01")
            run("switch", "-c", "feature")
            source.write_text("one\ntwo\nthree\n", encoding="utf-8")
            run("commit", "-am", "feature work", day="2026-09-02")
            run("switch", "develop")
            source.write_text("one\ntwo\nfour\n", encoding="utf-8")
            run("commit", "-am", "develop second", day="2026-09-03")
            run("update-ref", "refs/remotes/origin/develop", "develop")
            config = TrackerConfig(
                repo=repo,
                base_commit=base_hash,
                base_total=1,
                author="",
                ref="origin/develop",
                today=dt.date(2026, 9, 3),
                selected_branches=("develop", "feature"),
            )

            snapshot = build_refresh_snapshot(repo, "", config, graph_days=3)
            self.assertEqual(snapshot.branch_total, 3)
            self.assertEqual(snapshot.branch_commit_count, 3)
            self.assertEqual(snapshot.project_commit_count, 3)
            self.assertEqual(snapshot.project_active_days, 3)
            self.assertEqual(snapshot.repository_birth_date, dt.date(2026, 8, 31))
            self.assertEqual(snapshot.project_cumulative_lines, 3)
            self.assertEqual(snapshot.project_cumulative_deletions, 0)
            self.assertEqual(
                [(stat.ref, stat.additions, stat.deletions, stat.commits, stat.active_days, stat.started_on)
                 for stat in snapshot.branch_stats],
                [
                    ("develop", 2, 0, 2, 2, dt.date(2026, 8, 31)),
                    ("feature", 1, 0, 1, 1, dt.date(2026, 9, 2)),
                ],
            )
            presentation = build_dashboard_presentation(
                snapshot, translate=lambda key, **_kwargs: key, user_title="Alice"
            )
            self.assertEqual([section.title for section in presentation.branches], ["develop", "feature"])
            self.assertEqual([section.added for section in presentation.branches], ["+2", "+1"])
            self.assertEqual(
                [section.cards[2].value for section in presentation.branches],
                ["4day_suffix", "2day_suffix"],
            )
            self.assertEqual(presentation.user.title, "Alice")
            self.assertEqual(presentation.user.added, "+3")
            self.assertEqual(presentation.user.removed, "-0")
            self.assertEqual(presentation.user.commits, "3 commit")
            self.assertEqual(presentation.overall.added, "+3")
            self.assertEqual(presentation.overall.removed, "-0")
            self.assertEqual(presentation.overall.commits, "3 commit")
            self.assertEqual(len(presentation.overall.cards), 5)
            self.assertEqual(
                presentation.overall.cards[1].label,
                "project_cumulative_lines_label",
            )
            self.assertEqual(presentation.overall.cards[2].label, "project_active_days_label")
            self.assertEqual(presentation.overall.cards[3].label, "repository_birth_date_label")
            self.assertEqual(presentation.overall.cards[3].value, "2026-08-31")
            self.assertEqual(presentation.overall.cards[4].label, "repository_age_label")
            self.assertEqual(presentation.overall.cards[4].value, "repository_age_days")
            self.assertEqual(len(presentation.user.cards), 3)
            self.assertEqual(presentation.user.cards[2].label, "share_label")
            self.assertEqual([value for _, value in snapshot.graph_added_points], [1, 1, 1])
            self.assertEqual([value for _, value in snapshot.graph_commit_points], [1, 1, 1])
            self.assertEqual(snapshot.daily_progress_language_lines, {"Docs": 1})

            source.write_text("one\ntwo\nfour\nfive\n", encoding="utf-8")
            feature_snapshot = build_refresh_snapshot(
                repo, "", replace(config, selected_branches=("feature",)), graph_days=3
            )
            self.assertEqual(feature_snapshot.branch_total, 1)
            self.assertEqual(
                [(stat.ref, stat.additions, stat.commits) for stat in feature_snapshot.branch_stats],
                [("feature", 1, 1)],
            )
            self.assertEqual([value for _, value in feature_snapshot.graph_added_points], [0, 1, 0])
            self.assertEqual([value for _, value in feature_snapshot.graph_commit_points], [0, 1, 0])
            self.assertEqual(feature_snapshot.graph_uncommitted_insertions, 0)
            self.assertEqual(feature_snapshot.result.uncommitted_insertions, 1)

    def test_shared_branch_commits_are_counted_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            git = resolve_git_executable()

            def run(*args: str, day: str = "2026-09-01") -> None:
                environment = os.environ.copy()
                environment["GIT_AUTHOR_DATE"] = f"{day}T12:00:00+00:00"
                environment["GIT_COMMITTER_DATE"] = f"{day}T12:00:00+00:00"
                subprocess.run([git, *args], cwd=repo, env=environment, check=True, capture_output=True)

            run("init")
            run("config", "user.name", "Alice")
            run("config", "user.email", "alice@example.com")
            source = repo / "file.txt"
            source.write_text("one\n", encoding="utf-8")
            run("add", "file.txt")
            run("commit", "-m", "base")
            run("branch", "-M", "main")
            run("switch", "-c", "feature/a")
            source.write_text("one\ntwo\nthree\n", encoding="utf-8")
            run("commit", "-am", "first")
            run("switch", "-c", "feature/b")
            source.write_text("one\nchanged\nthree\nfour\n", encoding="utf-8")
            run("commit", "-am", "second", day="2026-09-02")

            self.assertIn("feature/a", list_branch_refs(repo))
            self.assertIn("feature/b", list_branch_refs(repo))
            self.assertEqual(get_branch_union_stats(repo, "", "main", ("feature/a", "feature/b")), (4, 1, 2, 2))
            aliases = encode_author_patterns(["Alice", "alice@example.com"])
            self.assertEqual(get_branch_union_stats(repo, aliases, "main", ("feature/a", "feature/b")), (4, 1, 2, 2))
