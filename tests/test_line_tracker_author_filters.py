from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import line_tracker
from line_tracker import decode_author_patterns, encode_author_patterns


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
                return "3\t0\tfoo.py\n"
            if author_arg == "--author=bob@example.com":
                return "5\t0\tbar.py\n"
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


if __name__ == "__main__":
    unittest.main()
