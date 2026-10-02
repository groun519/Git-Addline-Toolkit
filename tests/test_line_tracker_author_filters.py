from __future__ import annotations

import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import line_tracker
from line_tracker import (
    decode_author_patterns,
    encode_author_patterns,
    get_commit_change_entries,
    resolve_git_executable,
)


class AuthorFilterTests(unittest.TestCase):
    def test_encode_author_patterns_keeps_single_pattern_plain(self) -> None:
        self.assertEqual(encode_author_patterns(["alice@example\\.com"]), "alice@example\\.com")

    def test_encode_author_patterns_roundtrips_multiple_patterns(self) -> None:
        encoded = encode_author_patterns(["alice@example\\.com", "alice@users\\.noreply\\.github\\.com"])
        self.assertEqual(
            decode_author_patterns(encoded),
            ["alice@example\\.com", "alice@users\\.noreply\\.github\\.com"],
        )

    def test_get_committed_insertions_sums_multi_author_patterns(self) -> None:
        encoded = encode_author_patterns(["alice@example.com", "bob@example.com"])

        def fake_run_git(_: Path, args: list[str]) -> str:
            author_arg = next((value for value in args if value.startswith("--author=")), "")
            if author_arg == "--author=alice@example.com":
                return " 1 file changed, 3 insertions(+)\n"
            if author_arg == "--author=bob@example.com":
                return " 1 file changed, 5 insertions(+)\n"
            return ""

        with patch.dict(line_tracker._COMMITTED_INSERTIONS_CACHE, {}, clear=True):
            with patch.object(line_tracker, "get_ref_hash", return_value="hash"):
                with patch.object(line_tracker, "run_git", side_effect=fake_run_git):
                    total = line_tracker.get_committed_insertions(
                        Path("."),
                        "base",
                        encoded,
                        "HEAD",
                    )

        self.assertEqual(total, 8)

    def test_multi_author_history_paginates_in_global_git_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            git = resolve_git_executable()

            def run(*args: str, day: int = 1, author: tuple[str, str] | None = None) -> None:
                environment = os.environ.copy()
                environment["GIT_AUTHOR_DATE"] = f"2026-08-{day:02d}T12:00:00+09:00"
                environment["GIT_COMMITTER_DATE"] = environment["GIT_AUTHOR_DATE"]
                if author is not None:
                    environment["GIT_AUTHOR_NAME"], environment["GIT_AUTHOR_EMAIL"] = author
                subprocess.run(
                    [git, *args],
                    cwd=repo,
                    env=environment,
                    check=True,
                    capture_output=True,
                    text=True,
                )

            run("init", "-q")
            run("config", "user.name", "Committer")
            run("config", "user.email", "committer@example.com")
            source = repo / "data.txt"
            aliases = (("Alpha", "a@example.com"), ("Beta", "b@example.com"))
            for index in range(1, 5):
                source.write_text("x\n" * index, encoding="utf-8")
                run("add", "data.txt", day=index)
                run("commit", "-q", "-m", f"commit-{index}", day=index, author=aliases[(index - 1) % 2])

            author_filter = encode_author_patterns(
                [re.escape("a@example.com"), re.escape("b@example.com")]
            )
            first_page = get_commit_change_entries(repo, author_filter, ("HEAD",), limit=2)
            second_page = get_commit_change_entries(repo, author_filter, ("HEAD",), limit=2, skip=2)

        self.assertEqual([entry.subject for entry in first_page], ["commit-4", "commit-3"])
        self.assertEqual([entry.subject for entry in second_page], ["commit-2", "commit-1"])


if __name__ == "__main__":
    unittest.main()
