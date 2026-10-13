from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.line_tracker_mockups import (
    MOCKUP_BRANCH,
    MockupCatalogError,
    MockupSource,
    load_mockup_catalog,
    sync_mockup_worktree,
)


class MockupCatalogTests(unittest.TestCase):
    def test_source_normalization_keeps_paths_inside_repository(self) -> None:
        source = MockupSource(
            branch="--upload-pack=bad",
            wip_root="../outside",
            archive_root="C:/outside",
        ).normalized()

        self.assertEqual(source.branch, "codex/mockups")
        self.assertEqual(source.wip_root, "docs/wip")
        self.assertEqual(source.archive_root, "docs/archive")

    def test_load_catalog_indexes_worktree_metadata_and_full_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            repo = root / "repo"
            worktree = root / "mockups"
            repo.mkdir()
            document = worktree / "docs" / "wip" / "combat" / "README.md"
            document.parent.mkdir(parents=True)
            document.write_text(
                "# Combat Mockup\n\n> Status: **Design draft**\n\nUnique needle text.\n",
                encoding="utf-8",
            )
            overview = worktree / "docs" / "wip" / "ROADMAP.md"
            overview.write_text("# Roadmap\n", encoding="utf-8")
            archive = worktree / "docs" / "archive" / "old" / "notes.md"
            archive.parent.mkdir(parents=True)
            archive.write_text("# Old Notes\n", encoding="utf-8")

            calls: list[tuple[Path, tuple[str, ...]]] = []

            def run(command_repo: Path, args: list[str]) -> str:
                calls.append((command_repo, tuple(args)))
                if args[:2] == ["rev-parse", "--verify"]:
                    return "a" * 40
                if args == ["worktree", "list", "--porcelain"]:
                    return f"worktree {worktree}\nHEAD {'a' * 40}\nbranch refs/heads/{MOCKUP_BRANCH}\n\n"
                if args == ["status", "--porcelain"]:
                    return " M docs/wip/combat/README.md\n"
                if args[:2] == ["rev-parse", "--short"]:
                    return "abc1234\n"
                if args[:3] == ["rev-list", "--left-right", "--count"]:
                    return "2 3\n"
                raise AssertionError(args)

            catalog = load_mockup_catalog(repo, run=run)

        self.assertEqual(catalog.head, "abc1234")
        self.assertEqual(catalog.worktree_path, worktree)
        self.assertEqual(catalog.dirty_count, 1)
        self.assertEqual((catalog.ahead, catalog.behind), (2, 3))
        self.assertEqual(len(catalog.documents), 3)
        self.assertEqual(catalog.workspace_count, 1)
        combat = next(item for item in catalog.documents if item.title == "Combat Mockup")
        self.assertEqual(combat.workspace, "combat")
        self.assertEqual(combat.status, "Design draft")
        self.assertIn("unique needle", combat.search_text)
        roadmap = next(item for item in catalog.documents if item.title == "Roadmap")
        self.assertEqual(roadmap.workspace, "overview")
        self.assertTrue(any(args == ("status", "--porcelain") for _, args in calls))

    def test_sync_refuses_to_overwrite_dirty_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            repo = root / "repo"
            worktree = root / "mockups"
            repo.mkdir()
            worktree.mkdir()
            calls: list[tuple[str, ...]] = []

            def run(_repo: Path, args: list[str]) -> str:
                calls.append(tuple(args))
                if args == ["worktree", "list", "--porcelain"]:
                    return f"worktree {worktree}\nbranch refs/heads/{MOCKUP_BRANCH}\n\n"
                if args == ["status", "--porcelain"]:
                    return "?? draft.md\n"
                raise AssertionError(args)

            with self.assertRaisesRegex(MockupCatalogError, "uncommitted changes"):
                sync_mockup_worktree(repo, run=run)

        self.assertNotIn(("fetch", "origin", MOCKUP_BRANCH), calls)

    def test_sync_fast_forwards_clean_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            repo = root / "repo"
            worktree = root / "mockups"
            repo.mkdir()
            worktree.mkdir()
            calls: list[tuple[str, ...]] = []

            def run(_repo: Path, args: list[str]) -> str:
                calls.append(tuple(args))
                if args == ["worktree", "list", "--porcelain"]:
                    return f"worktree {worktree}\nbranch refs/heads/{MOCKUP_BRANCH}\n\n"
                if args == ["status", "--porcelain"]:
                    return ""
                if args[0] in {"fetch", "merge"}:
                    return ""
                raise AssertionError(args)

            result = sync_mockup_worktree(repo, run=run)

        self.assertEqual(result, worktree)
        self.assertIn(
            (
                "fetch",
                "origin",
                "+refs/heads/codex/mockups:refs/remotes/origin/codex/mockups",
            ),
            calls,
        )
        self.assertIn(("merge", "--ff-only", "origin/codex/mockups"), calls)

    def test_remote_catalog_searches_full_text_with_custom_source(self) -> None:
        repo = Path("C:/repo")
        source = MockupSource("design/mockups", "notes/wip", "notes/archive")
        calls: list[tuple[str, ...]] = []

        def run(_repo: Path, args: list[str]) -> str:
            calls.append(tuple(args))
            if args == ["rev-parse", "--verify", "design/mockups"]:
                raise RuntimeError("missing local branch")
            if args == ["rev-parse", "--verify", "origin/design/mockups"]:
                return "a" * 40
            if args == ["worktree", "list", "--porcelain"]:
                return ""
            if args[:3] == ["ls-tree", "-r", "--name-only"]:
                return "notes/wip/audio/README.md\nnotes/archive/old.md\n"
            if args[:4] == ["grep", "-n", "-I", "-e"]:
                return (
                    "origin/design/mockups:notes/wip/audio/README.md:1:# Audio Workspace\n"
                    "origin/design/mockups:notes/wip/audio/README.md:3:Unique fallback needle\n"
                    "origin/design/mockups:notes/archive/old.md:1:# Old Draft\n"
                )
            if args[:2] == ["rev-parse", "--short"]:
                return "def5678\n"
            raise AssertionError(args)

        catalog = load_mockup_catalog(repo, source=source, run=run)

        self.assertEqual(catalog.branch, "origin/design/mockups")
        self.assertEqual(catalog.source, source)
        self.assertEqual(catalog.workspace_count, 1)
        audio = next(document for document in catalog.documents if document.title == "Audio Workspace")
        self.assertEqual(audio.workspace, "audio")
        self.assertIn("unique fallback needle", audio.search_text)
        self.assertIn(
            (
                "ls-tree",
                "-r",
                "--name-only",
                "origin/design/mockups",
                "--",
                "notes/wip",
                "notes/archive",
            ),
            calls,
        )


if __name__ == "__main__":
    unittest.main()
