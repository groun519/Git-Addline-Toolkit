from __future__ import annotations

from pathlib import Path

from line_tracker import find_repo_root, run_git


def resolve_valid_repo(path: Path) -> Path | None:
    try:
        candidate = find_repo_root(path).resolve()
        run_git(candidate, ["rev-parse", "--is-inside-work-tree"])
    except (OSError, RuntimeError):
        return None
    return candidate
