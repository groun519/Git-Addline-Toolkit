import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


APP_DIR = Path(__file__).resolve().parents[1] / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from line_tracker_activity_index import CommitActivityIndex
from line_tracker import get_uncommitted_stats
from line_tracker_workspace_index import WorkspaceLineIndex


class WorkspaceLineIndexTests(unittest.TestCase):
    def test_unchanged_file_is_read_once_and_persists(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            repo.mkdir()
            source = repo / "source.py"
            source.write_text("one\ntwo\n", encoding="utf-8")
            cache_path = root / "workspace.json"
            index = WorkspaceLineIndex(cache_path)

            with patch(
                "line_tracker_workspace_index.count_text_lines",
                wraps=lambda path: len(path.read_text(encoding="utf-8").splitlines()),
            ) as counter:
                self.assertEqual(index.line_count(repo, "source.py"), 2)
                self.assertEqual(index.line_count(repo, "source.py"), 2)
                self.assertEqual(counter.call_count, 1)
                index.save()

                restored = WorkspaceLineIndex(cache_path)
                self.assertEqual(restored.line_count(repo, "source.py"), 2)
                self.assertEqual(counter.call_count, 1)

                source.write_text("one\ntwo\nthree\n", encoding="utf-8")
                self.assertEqual(restored.line_count(repo, "source.py"), 3)
                self.assertEqual(counter.call_count, 2)

    def test_uncommitted_stats_share_one_diff_and_untracked_scan(self) -> None:
        outputs = {
            "diff": "4\t2\tsource.py\n-\t-\tasset.uasset\n",
            "ls-files": "new.json\nimage.png\n",
        }

        def run_git(_repo: Path, args: list[str]) -> str:
            return outputs[args[0]]

        with patch("line_tracker.run_git", side_effect=run_git) as git_runner, patch(
            "line_tracker._WORKSPACE_LINE_INDEX.line_count",
            return_value=3,
        ) as line_count:
            result = get_uncommitted_stats(Path("C:/repo"))

        self.assertEqual(result.additions, 7)
        self.assertEqual(result.deletions, 2)
        self.assertEqual(result.languages, {"Python": 4, "JSON": 3})
        self.assertEqual(git_runner.call_count, 2)
        line_count.assert_called_once_with(Path("C:/repo"), "new.json")

    def test_save_keeps_dirty_state_when_index_changes_during_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            repo.mkdir()
            first = repo / "first.py"
            second = repo / "second.py"
            first.write_text("first\n", encoding="utf-8")
            second.write_text("second\n", encoding="utf-8")
            index = WorkspaceLineIndex(root / "workspace.json")
            index.line_count(repo, "first.py")
            writes: list[str] = []

            def write(_path: Path, payload: str) -> None:
                writes.append(payload)
                if len(writes) == 1:
                    index.line_count(repo, "second.py")

            with patch("line_tracker_workspace_index.write_text_atomic", side_effect=write):
                index.save()
                index.save()

        self.assertEqual(len(writes), 2)
        self.assertNotIn("second.py", writes[0])
        self.assertIn("second.py", writes[1])


class CommitActivityIndexTests(unittest.TestCase):
    def test_only_new_commit_is_parsed_on_next_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            repo.mkdir()
            index = CommitActivityIndex(root / "activity.json")
            fetched_chunks: list[list[str]] = []

            def run_git(_repo: Path, args: list[str]) -> str:
                if args[0] == "rev-list":
                    return "\n".join(["hash-c", "hash-b", "hash-a"])
                self.assertEqual(args[0], "log")
                hashes = [value for value in args if value.startswith("hash-")]
                if not hashes:
                    hashes = ["hash-b", "hash-a"]
                    fetched_chunks.append(["bootstrap"])
                else:
                    fetched_chunks.append(hashes)
                return "\n".join(
                    f"@@COMMIT@@{commit_hash}\t2026-10-0{position + 1}\tAlice\talice@example.com\n"
                    f"{position + 1}\t{position}\tsource{position}.py"
                    for position, commit_hash in enumerate(hashes)
                )

            first = index.activity_for_refs(
                repo,
                ("main",),
                exclude_ref=None,
                run_git=run_git,
            )
            index.save()
            restored = CommitActivityIndex(root / "activity.json")
            second = restored.activity_for_refs(
                repo,
                ("main",),
                exclude_ref=None,
                run_git=run_git,
            )

            self.assertEqual(set(first), {"hash-a", "hash-b"})
            self.assertEqual(set(second), {"hash-a", "hash-b", "hash-c"})
            self.assertEqual(fetched_chunks, [["bootstrap"], ["hash-c"]])

    def test_save_keeps_dirty_state_when_activity_changes_during_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            repo.mkdir()
            index = CommitActivityIndex(root / "activity.json")

            def run_git(_repo: Path, _args: list[str]) -> str:
                return "@@COMMIT@@hash-a\t2026-10-13\tAlice\talice@example.com\n1\t0\tfile.py"

            index.activity_for_refs(repo, ("main",), exclude_ref=None, run_git=run_git)
            writes: list[str] = []

            def write(_path: Path, payload: str) -> None:
                writes.append(payload)
                if len(writes) == 1:
                    index.clear_repo(repo)

            with patch("line_tracker_activity_index.write_text_atomic", side_effect=write):
                index.save()
                index.save()

        self.assertEqual(len(writes), 2)
        self.assertIn("hash-a", writes[0])
        self.assertNotIn("hash-a", writes[1])


if __name__ == "__main__":
    unittest.main()
