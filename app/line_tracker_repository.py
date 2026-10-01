from __future__ import annotations

from pathlib import Path

from line_tracker import find_repo_root, run_git


def find_repo_root_from_metadata(path: Path) -> Path | None:
    """Find a normal Git worktree without spawning Git during application startup."""
    try:
        candidate = path.expanduser().resolve()
    except OSError:
        return None
    if candidate.is_file():
        candidate = candidate.parent
    if not candidate.is_dir():
        return None
    for directory in (candidate, *candidate.parents):
        if (directory / ".git").exists():
            return directory
    return None


def resolve_valid_repo(path: Path) -> Path | None:
    try:
        candidate = find_repo_root(path).resolve()
        run_git(candidate, ["rev-parse", "--is-inside-work-tree"])
    except (OSError, RuntimeError):
        return None
    return candidate
