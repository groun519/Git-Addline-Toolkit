#!/usr/bin/env python3
from __future__ import annotations

import argparse
import atexit
import calendar
import datetime as dt
import json
import math
import os
import re
import shutil
import subprocess
import sys
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


DEFAULT_GOAL = 20000
DEFAULT_BASE_TOTAL = -1
DEFAULT_BASE_COMMIT = "auto"
DEFAULT_AUTHOR = "auto"
CACHE_VERSION = 7
APP_STATE_DIR_NAME = "LineTracker"

BINARY_EXTENSIONS = {
    ".uasset",
    ".umap",
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".tga",
    ".gif",
    ".dds",
    ".wav",
    ".mp3",
    ".ogg",
    ".mp4",
    ".mov",
    ".avi",
    ".zip",
    ".7z",
    ".rar",
    ".bin",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".pdb",
    ".lib",
    ".a",
}
LANGUAGE_EXTENSION_GROUPS: tuple[tuple[str, frozenset[str]], ...] = (
    ("C++", frozenset({".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx", ".inl"})),
    ("C#", frozenset({".cs"})),
    ("Python", frozenset({".py", ".pyw"})),
    ("TypeScript", frozenset({".ts", ".tsx"})),
    ("JavaScript", frozenset({".js", ".jsx", ".mjs", ".cjs"})),
    ("JSON", frozenset({".json", ".jsonc", ".uplugin", ".uproject"})),
    ("Shader", frozenset({".usf", ".ush", ".hlsl", ".glsl", ".vert", ".frag"})),
    ("Config", frozenset({".ini", ".cfg", ".conf", ".toml", ".yaml", ".yml"})),
    ("Scripts", frozenset({".ps1", ".bat", ".cmd", ".sh"})),
    ("Docs", frozenset({".md", ".mdx", ".rst", ".txt"})),
)
LANGUAGE_NAMES = tuple(language for language, _extensions in LANGUAGE_EXTENSION_GROUPS) + ("Other",)
SHORTSTAT_INSERTIONS_RE = re.compile(r"(\d+)\s+insertions?\(\+\)")
SHORTSTAT_DELETIONS_RE = re.compile(r"(\d+)\s+deletions?\(-\)")

_COMMITTED_INSERTIONS_CACHE: dict[tuple[str, str, str, str, str, str, str], int] = {}
_COMMITTED_DELETIONS_CACHE: dict[tuple[str, str, str, str, str, str, str], int] = {}
_BY_DATE_CACHE: dict[tuple[str, str, str, str, str, str, str, str], dict[dt.date, int]] = {}
_DELETIONS_BY_DATE_CACHE: dict[tuple[str, str, str, str, str, str, str, str], dict[dt.date, int]] = {}
_COMMITS_BY_DATE_CACHE: dict[tuple[str, str, str, str, str, str, str, str], dict[dt.date, int]] = {}
_FOR_DATE_CACHE: dict[tuple[str, str, str, str, str, str, str], int] = {}
_TOTAL_UP_TO_CACHE: dict[tuple[str, str, str, str], int] = {}
_TOTAL_DELETIONS_UP_TO_CACHE: dict[tuple[str, str, str, str], int] = {}
_PROJECT_TOTAL_LINES_CACHE: dict[tuple[str, str, str], int] = {}
_COMMIT_COUNT_CACHE: dict[tuple[str, str, str, str, str, str, str, str], int] = {}
_ACTIVE_COMMIT_DATES_CACHE: dict[tuple[str, str, str, str, str, str], tuple[str, ...]] = {}
_LANGUAGE_INSERTIONS_CACHE: dict[tuple[str, str, str, str, str, str, str, str], dict[str, int]] = {}
_LANGUAGE_BY_DATE_CACHE: dict[
    tuple[str, str, str, str, str, str, str, str],
    dict[dt.date, dict[str, int]],
] = {}
_CACHE_LOCK = threading.RLock()
_CACHE_LOADED = False
_CACHE_DIRTY = False
_GIT_EXECUTABLE: str | None = None
_GIT_SOURCE: str | None = None
MULTI_AUTHOR_PREFIX = "__LT_MULTI__:"


def _git_subprocess_kwargs() -> dict[str, object]:
    kwargs: dict[str, object] = {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "check": False,
    }
    create_no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if create_no_window:
        kwargs["creationflags"] = create_no_window
    return kwargs


def encode_author_patterns(patterns: list[str]) -> str:
    unique_patterns: list[str] = []
    for raw_pattern in patterns:
        pattern = str(raw_pattern).strip()
        if pattern and pattern not in unique_patterns:
            unique_patterns.append(pattern)
    if not unique_patterns:
        return ""
    if len(unique_patterns) == 1:
        return unique_patterns[0]
    return MULTI_AUTHOR_PREFIX + json.dumps(unique_patterns, ensure_ascii=False, separators=(",", ":"))


def decode_author_patterns(author: str) -> list[str]:
    cleaned = str(author).strip()
    if not cleaned:
        return []
    if not cleaned.startswith(MULTI_AUTHOR_PREFIX):
        return [cleaned]

    raw_payload = cleaned[len(MULTI_AUTHOR_PREFIX):]
    try:
        decoded = json.loads(raw_payload)
    except json.JSONDecodeError:
        return [cleaned]
    if not isinstance(decoded, list):
        return [cleaned]

    patterns: list[str] = []
    for value in decoded:
        pattern = str(value).strip()
        if pattern and pattern not in patterns:
            patterns.append(pattern)
    return patterns or [cleaned]


def get_app_state_dir() -> Path:
    local_appdata = os.environ.get("LOCALAPPDATA", "").strip()
    if local_appdata:
        return Path(local_appdata) / APP_STATE_DIR_NAME
    return Path.home() / "AppData" / "Local" / APP_STATE_DIR_NAME


def get_app_state_path(filename: str) -> Path:
    return get_app_state_dir() / filename


def get_legacy_state_path(filename: str) -> Path:
    return Path(__file__).resolve().with_name(filename)


_CACHE_PATH = get_app_state_path("line_tracker_cache.json")
_LEGACY_CACHE_PATH = get_legacy_state_path("line_tracker_cache.json")


def _iter_git_roots() -> list[Path]:
    roots: list[Path] = []
    if getattr(sys, "frozen", False):
        roots.append(Path(sys.executable).resolve().parent)

    module_dir = Path(__file__).resolve().parent
    roots.extend([module_dir, module_dir.parent])

    unique_roots: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root).lower()
        if key in seen:
            continue
        seen.add(key)
        unique_roots.append(root)
    return unique_roots


def find_bundled_git() -> Path | None:
    relative_paths = (
        ("PortableGit", "cmd", "git.exe"),
        ("PortableGit", "bin", "git.exe"),
        ("runtime", "PortableGit", "cmd", "git.exe"),
        ("runtime", "PortableGit", "bin", "git.exe"),
        ("vendor", "PortableGit", "cmd", "git.exe"),
        ("vendor", "PortableGit", "bin", "git.exe"),
    )
    for root in _iter_git_roots():
        for parts in relative_paths:
            candidate = root.joinpath(*parts)
            if candidate.is_file():
                return candidate
    return None


def resolve_git_executable() -> str:
    global _GIT_EXECUTABLE, _GIT_SOURCE
    if _GIT_EXECUTABLE:
        return _GIT_EXECUTABLE

    override = os.environ.get("LINE_TRACKER_GIT", "").strip()
    if override:
        override_path = Path(override).expanduser()
        if override_path.is_file():
            _GIT_EXECUTABLE = str(override_path)
            _GIT_SOURCE = "env"
            return _GIT_EXECUTABLE
        override_which = shutil.which(override)
        if override_which:
            _GIT_EXECUTABLE = override_which
            _GIT_SOURCE = "env"
            return _GIT_EXECUTABLE

    bundled_git = find_bundled_git()
    if bundled_git is not None:
        _GIT_EXECUTABLE = str(bundled_git)
        _GIT_SOURCE = "bundled"
        return _GIT_EXECUTABLE

    path_git = shutil.which("git")
    if path_git:
        _GIT_EXECUTABLE = path_git
        _GIT_SOURCE = "path"
        return _GIT_EXECUTABLE

    raise FileNotFoundError("git executable not found")


def get_git_version() -> str | None:
    try:
        git_executable = resolve_git_executable()
    except FileNotFoundError:
        return None

    try:
        result = subprocess.run(
            [git_executable, "--version"],
            **_git_subprocess_kwargs(),
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def get_git_info() -> tuple[str | None, str | None, str | None]:
    try:
        git_executable = resolve_git_executable()
    except FileNotFoundError:
        return None, None, None
    return get_git_version(), git_executable, _GIT_SOURCE


@dataclass(frozen=True)
class TrackerConfig:
    repo: Path
    goal: int = DEFAULT_GOAL
    base_total: int = DEFAULT_BASE_TOTAL
    base_commit: str = DEFAULT_BASE_COMMIT
    author: str = DEFAULT_AUTHOR
    ref: str = "auto"
    include_local: bool = True
    today: dt.date | None = None
    month_end: dt.date | None = None
    assume_uncommitted_zero: bool = False
    selected_branches: tuple[str, ...] = ()


@dataclass(frozen=True)
class TrackerResult:
    today: dt.date
    month_end: dt.date
    days_left_including_today: int
    days_left_after_today: int
    committed_total: int
    uncommitted_insertions: int
    need_today: int
    need_after_commit: int


@dataclass(frozen=True)
class CommitChangeEntry:
    commit_hash: str
    short_hash: str
    date: dt.date | None
    subject: str
    insertions: int
    deletions: int


@dataclass(frozen=True)
class CommitFileChange:
    path: str
    insertions: int | None
    deletions: int | None

    @property
    def is_binary(self) -> bool:
        return self.insertions is None or self.deletions is None


@dataclass(frozen=True)
class CommitDetail:
    commit_hash: str
    short_hash: str
    authored_at: dt.datetime | None
    author_name: str
    author_email: str
    subject: str
    body: str
    files: tuple[CommitFileChange, ...]

    @property
    def insertions(self) -> int:
        return sum(change.insertions or 0 for change in self.files)

    @property
    def deletions(self) -> int:
        return sum(change.deletions or 0 for change in self.files)


def run_git(repo: Path, args: list[str]) -> str:
    git_executable = resolve_git_executable()
    result = subprocess.run(
        [git_executable, *args],
        cwd=repo,
        **_git_subprocess_kwargs(),
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {stderr}")
    return result.stdout


def list_branch_refs(repo: Path) -> tuple[str, ...]:
    output = run_git(repo, ["for-each-ref", "--format=%(refname:short)", "refs/heads", "refs/remotes"])
    return tuple(
        ref for ref in output.splitlines()
        if ref and not ref.endswith("/HEAD")
    )


def find_repo_root(start: Path) -> Path:
    try:
        git_executable = resolve_git_executable()
    except FileNotFoundError:
        return start
    try:
        result = subprocess.run(
            [git_executable, "-C", str(start), "rev-parse", "--show-toplevel"],
            **_git_subprocess_kwargs(),
        )
    except OSError:
        return start
    if result.returncode != 0:
        return start
    root = result.stdout.strip()
    return Path(root) if root else start


def _repo_key(repo: Path) -> str:
    return str(repo.resolve()).lower()


def _mark_cache_dirty() -> None:
    global _CACHE_DIRTY
    _CACHE_DIRTY = True


def _load_cache() -> None:
    global _CACHE_LOADED
    if _CACHE_LOADED:
        return
    _CACHE_LOADED = True
    cache_path = _CACHE_PATH if _CACHE_PATH.exists() else _LEGACY_CACHE_PATH
    if not cache_path.exists():
        return
    try:
        raw = cache_path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(data, dict) or data.get("version") != CACHE_VERSION:
        return

    def load_map(items: object, target: dict[tuple, object], convert_dates: bool = False) -> None:
        if not isinstance(items, list):
            return
        for entry in items:
            if not isinstance(entry, list) or len(entry) != 2:
                continue
            key_list, value = entry
            if not isinstance(key_list, list):
                continue
            key = tuple(str(part) for part in key_list)
            if convert_dates and isinstance(value, dict):
                converted: dict[dt.date, int] = {}
                for day_text, day_value in value.items():
                    try:
                        day = dt.date.fromisoformat(str(day_text))
                    except ValueError:
                        continue
                    if isinstance(day_value, int):
                        converted[day] = day_value
                    else:
                        try:
                            converted[day] = int(day_value)
                        except (TypeError, ValueError):
                            continue
                value = converted
            target[key] = value

    def load_language_date_map(items: object) -> None:
        if not isinstance(items, list):
            return
        for entry in items:
            if not isinstance(entry, list) or len(entry) != 2:
                continue
            key_list, value = entry
            if not isinstance(key_list, list) or not isinstance(value, dict):
                continue
            converted: dict[dt.date, dict[str, int]] = {}
            for day_text, language_values in value.items():
                if not isinstance(language_values, dict):
                    continue
                try:
                    day = dt.date.fromisoformat(str(day_text))
                except ValueError:
                    continue
                totals: dict[str, int] = {}
                for language, line_count in language_values.items():
                    try:
                        parsed_count = int(line_count)
                    except (TypeError, ValueError):
                        continue
                    if parsed_count > 0:
                        totals[str(language)] = parsed_count
                converted[day] = order_language_totals(totals)
            _LANGUAGE_BY_DATE_CACHE[tuple(str(part) for part in key_list)] = converted

    with _CACHE_LOCK:
        load_map(data.get("committed"), _COMMITTED_INSERTIONS_CACHE)
        load_map(data.get("committed_deletions"), _COMMITTED_DELETIONS_CACHE)
        load_map(data.get("for_date"), _FOR_DATE_CACHE)
        load_map(data.get("total"), _TOTAL_UP_TO_CACHE)
        load_map(data.get("total_deletions"), _TOTAL_DELETIONS_UP_TO_CACHE)
        load_map(data.get("project_total_lines"), _PROJECT_TOTAL_LINES_CACHE)
        load_map(data.get("commit_counts"), _COMMIT_COUNT_CACHE)
        load_map(data.get("active_commit_dates"), _ACTIVE_COMMIT_DATES_CACHE)
        load_map(data.get("language_insertions"), _LANGUAGE_INSERTIONS_CACHE)
        load_language_date_map(data.get("language_by_date"))
        load_map(data.get("by_date"), _BY_DATE_CACHE, convert_dates=True)
        load_map(data.get("deletions_by_date"), _DELETIONS_BY_DATE_CACHE, convert_dates=True)
        load_map(data.get("commits_by_date"), _COMMITS_BY_DATE_CACHE, convert_dates=True)


def _save_cache() -> None:
    global _CACHE_DIRTY
    if not _CACHE_DIRTY:
        return
    payload = {
        "version": CACHE_VERSION,
        "committed": [],
        "committed_deletions": [],
        "for_date": [],
        "total": [],
        "total_deletions": [],
        "project_total_lines": [],
        "commit_counts": [],
        "active_commit_dates": [],
        "language_insertions": [],
        "language_by_date": [],
        "by_date": [],
        "deletions_by_date": [],
        "commits_by_date": [],
    }
    with _CACHE_LOCK:
        for key, value in _COMMITTED_INSERTIONS_CACHE.items():
            payload["committed"].append([list(key), value])
        for key, value in _COMMITTED_DELETIONS_CACHE.items():
            payload["committed_deletions"].append([list(key), value])
        for key, value in _FOR_DATE_CACHE.items():
            payload["for_date"].append([list(key), value])
        for key, value in _TOTAL_UP_TO_CACHE.items():
            payload["total"].append([list(key), value])
        for key, value in _TOTAL_DELETIONS_UP_TO_CACHE.items():
            payload["total_deletions"].append([list(key), value])
        for key, value in _PROJECT_TOTAL_LINES_CACHE.items():
            payload["project_total_lines"].append([list(key), value])
        for key, value in _COMMIT_COUNT_CACHE.items():
            payload["commit_counts"].append([list(key), value])
        for key, value in _ACTIVE_COMMIT_DATES_CACHE.items():
            payload["active_commit_dates"].append([list(key), list(value)])
        for key, value in _LANGUAGE_INSERTIONS_CACHE.items():
            payload["language_insertions"].append([list(key), value])
        for key, value in _LANGUAGE_BY_DATE_CACHE.items():
            payload["language_by_date"].append(
                [
                    list(key),
                    {
                        day.isoformat(): dict(language_values)
                        for day, language_values in value.items()
                    },
                ]
            )
        for key, value in _BY_DATE_CACHE.items():
            payload["by_date"].append(
                [list(key), {day.isoformat(): val for day, val in value.items()}]
            )
        for key, value in _DELETIONS_BY_DATE_CACHE.items():
            payload["deletions_by_date"].append(
                [list(key), {day.isoformat(): val for day, val in value.items()}]
            )
        for key, value in _COMMITS_BY_DATE_CACHE.items():
            payload["commits_by_date"].append(
                [list(key), {day.isoformat(): val for day, val in value.items()}]
            )
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        _CACHE_DIRTY = False
    except OSError:
        pass


def clear_cache_for_repo(repo: Path) -> None:
    _load_cache()
    repo_key = _repo_key(repo)

    def clear_dict(target: dict[tuple, object]) -> None:
        for key in list(target.keys()):
            if key and key[0] == repo_key:
                del target[key]

    with _CACHE_LOCK:
        clear_dict(_COMMITTED_INSERTIONS_CACHE)
        clear_dict(_COMMITTED_DELETIONS_CACHE)
        clear_dict(_FOR_DATE_CACHE)
        clear_dict(_TOTAL_UP_TO_CACHE)
        clear_dict(_TOTAL_DELETIONS_UP_TO_CACHE)
        clear_dict(_PROJECT_TOTAL_LINES_CACHE)
        clear_dict(_COMMIT_COUNT_CACHE)
        clear_dict(_ACTIVE_COMMIT_DATES_CACHE)
        clear_dict(_LANGUAGE_INSERTIONS_CACHE)
        clear_dict(_LANGUAGE_BY_DATE_CACHE)
        clear_dict(_BY_DATE_CACHE)
        clear_dict(_DELETIONS_BY_DATE_CACHE)
        clear_dict(_COMMITS_BY_DATE_CACHE)
        _mark_cache_dirty()


def resolve_author(repo: Path, author: str) -> str:
    _load_cache()
    if not author:
        return ""
    if author.lower() != "auto":
        return author

    try:
        name = run_git(repo, ["config", "user.name"]).strip()
    except RuntimeError:
        name = ""
    try:
        email = run_git(repo, ["config", "user.email"]).strip()
    except RuntimeError:
        email = ""
    if name and email:
        return f"{re.escape(name)}|{re.escape(email)}"
    if name:
        return re.escape(name)
    if email:
        return re.escape(email)
    return ""


def resolve_current_ref(repo: Path) -> str:
    _load_cache()
    try:
        value = run_git(repo, ["symbolic-ref", "-q", "--short", "HEAD"]).strip()
        return value if value else "HEAD"
    except RuntimeError:
        return "HEAD"


def git_ref_exists(repo: Path, ref: str) -> bool:
    _load_cache()
    try:
        git_executable = resolve_git_executable()
    except FileNotFoundError:
        return False
    try:
        result = subprocess.run(
            [git_executable, "show-ref", "--verify", "--quiet", ref],
            cwd=repo,
            **_git_subprocess_kwargs(),
        )
    except OSError:
        return False
    return result.returncode == 0


def resolve_ref(repo: Path, ref: str) -> str:
    _load_cache()
    if ref and ref != "auto":
        return ref

    try:
        sym = run_git(repo, ["symbolic-ref", "-q", "refs/remotes/origin/HEAD"]).strip()
    except RuntimeError:
        sym = ""
    if sym.startswith("refs/remotes/origin/"):
        return sym.replace("refs/remotes/origin/", "origin/", 1)

    if git_ref_exists(repo, "refs/heads/main"):
        return "main"
    if git_ref_exists(repo, "refs/heads/master"):
        return "master"
    return "HEAD"


def resolve_base_commit(repo: Path, today: dt.date, base_commit: str, ref: str) -> str:
    _load_cache()
    if base_commit and base_commit != "auto":
        return base_commit
    month_start = today.replace(day=1)
    try:
        before = run_git(
            repo,
            ["rev-list", "-n", "1", f"--before={month_start.isoformat()} 00:00:00", ref],
        ).strip()
    except RuntimeError:
        before = ""
    if before:
        return before
    try:
        root = run_git(repo, ["rev-list", "--max-parents=0", ref]).splitlines()
    except RuntimeError:
        root = []
    return root[0] if root else "HEAD"


def get_ref_hash(repo: Path, ref: str = "HEAD") -> str:
    _load_cache()
    return run_git(repo, ["rev-parse", ref]).strip()


def is_probably_binary_path(path_text: str) -> bool:
    return Path(path_text).suffix.lower() in BINARY_EXTENSIONS


def is_probably_binary_bytes(sample: bytes) -> bool:
    return b"\x00" in sample


def count_text_lines(path: Path) -> int:
    try:
        with path.open("rb") as f:
            data = f.read()
    except OSError:
        return 0

    if not data:
        return 0
    if is_probably_binary_bytes(data[:8192]):
        return 0

    lines = data.count(b"\n")
    if not data.endswith(b"\n"):
        lines += 1
    return lines


def classify_text_language(path_text: str) -> str:
    suffix = Path(path_text).suffix.lower()
    for language, extensions in LANGUAGE_EXTENSION_GROUPS:
        if suffix in extensions:
            return language
    return "Other"


def order_language_totals(totals: dict[str, int]) -> dict[str, int]:
    ordered: dict[str, int] = {}
    for language, _ in LANGUAGE_EXTENSION_GROUPS:
        if totals.get(language, 0) > 0:
            ordered[language] = int(totals[language])
    if totals.get("Other", 0) > 0:
        ordered["Other"] = int(totals["Other"])
    return ordered


def merge_language_totals(*language_totals: dict[str, int]) -> dict[str, int]:
    merged: dict[str, int] = {}
    for totals in language_totals:
        for language, value in totals.items():
            if value > 0:
                merged[language] = merged.get(language, 0) + int(value)
    return order_language_totals(merged)


def get_project_language_lines(repo: Path) -> dict[str, int]:
    out = run_git(repo, ["ls-files", "-z", "--cached", "--others", "--exclude-standard"])
    totals: dict[str, int] = {}
    for path_text in (value for value in out.split("\0") if value):
        if is_probably_binary_path(path_text):
            continue
        line_count = count_text_lines(repo / path_text)
        if line_count <= 0:
            continue
        language = classify_text_language(path_text)
        totals[language] = totals.get(language, 0) + line_count

    return order_language_totals(totals)


def get_worktree_tracked_text_total(repo: Path) -> int:
    out = run_git(repo, ["ls-files", "-z"])
    files = [path_text for path_text in out.split("\0") if path_text]
    if not files:
        return 0

    total = 0
    for path_text in files:
        if is_probably_binary_path(path_text):
            continue
        total += count_text_lines(repo / path_text)
    return total


def parse_numstat_insertions(text: str) -> int:
    total = 0
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        added = parts[0]
        if added.isdigit():
            total += int(added)
    return total


def parse_numstat_deletions(text: str) -> int:
    total = 0
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        removed = parts[1]
        if removed.isdigit():
            total += int(removed)
    return total


def parse_numstat_insertions_by_language(text: str) -> dict[str, int]:
    totals: dict[str, int] = {}
    for line in text.splitlines():
        parts = line.split("\t", 2)
        if len(parts) < 3 or not parts[0].isdigit():
            continue
        path_text = parts[2].strip()
        if not path_text or is_probably_binary_path(path_text):
            continue
        language = classify_text_language(path_text)
        totals[language] = totals.get(language, 0) + int(parts[0])
    return order_language_totals(totals)


def parse_numstat_insertions_by_date_and_language(
    text: str,
) -> dict[dt.date, dict[str, int]]:
    daily: dict[dt.date, dict[str, int]] = {}
    current_day: dt.date | None = None
    for line in text.splitlines():
        if line.startswith("@@DATE@@"):
            try:
                current_day = dt.date.fromisoformat(line.removeprefix("@@DATE@@").strip())
            except ValueError:
                current_day = None
            if current_day is not None:
                daily.setdefault(current_day, {})
            continue
        if current_day is None:
            continue
        parts = line.split("\t", 2)
        if len(parts) < 3 or not parts[0].isdigit():
            continue
        path_text = parts[2].strip()
        if not path_text or is_probably_binary_path(path_text):
            continue
        language = classify_text_language(path_text)
        totals = daily.setdefault(current_day, {})
        totals[language] = totals.get(language, 0) + int(parts[0])
    return {day: order_language_totals(totals) for day, totals in daily.items()}


def get_committed_insertions_by_language(
    repo: Path,
    author: str,
    ref: str = "HEAD",
    exclude_ref: str | None = None,
    since: dt.date | None = None,
    until: dt.date | None = None,
) -> dict[str, int]:
    _load_cache()
    ref_hash = get_ref_hash(repo, ref)
    exclude_hash = get_ref_hash(repo, exclude_ref) if exclude_ref else ""
    cache_key = (
        _repo_key(repo),
        author,
        ref,
        ref_hash,
        exclude_ref or "",
        exclude_hash,
        since.isoformat() if since else "",
        until.isoformat() if until else "",
    )
    with _CACHE_LOCK:
        cached = _LANGUAGE_INSERTIONS_CACHE.get(cache_key)
    if cached is not None:
        return dict(cached)

    author_patterns = decode_author_patterns(author)
    if len(author_patterns) > 1:
        merged = merge_language_totals(
            *(
                get_committed_insertions_by_language(repo, pattern, ref, exclude_ref, since, until)
                for pattern in author_patterns
            )
        )
        with _CACHE_LOCK:
            _LANGUAGE_INSERTIONS_CACHE[cache_key] = dict(merged)
            _mark_cache_dirty()
        return merged

    args = ["log", "--no-renames", "--numstat", "--pretty=tformat:"]
    if since is not None:
        args.append(f"--since={since.isoformat()}")
    if until is not None:
        args.append(f"--until={until.isoformat()}")
    author_pattern = author_patterns[0] if author_patterns else ""
    if author_pattern:
        args.append(f"--author={author_pattern}")
    args.append(ref)
    if exclude_ref:
        args.extend(["--not", exclude_ref])

    totals = parse_numstat_insertions_by_language(run_git(repo, args))
    with _CACHE_LOCK:
        _LANGUAGE_INSERTIONS_CACHE[cache_key] = dict(totals)
        _mark_cache_dirty()
    return totals


def get_committed_insertions_by_language_combined(
    repo: Path,
    author: str,
    ref: str,
    include_local: bool,
    since: dt.date | None = None,
    until: dt.date | None = None,
) -> dict[str, int]:
    base = get_committed_insertions_by_language(repo, author, ref, since=since, until=until)
    if not include_local:
        return base
    current_ref = resolve_current_ref(repo)
    if current_ref == ref:
        return base
    extra = get_committed_insertions_by_language(
        repo,
        author,
        current_ref,
        exclude_ref=ref,
        since=since,
        until=until,
    )
    return merge_language_totals(base, extra)


def parse_shortstat_totals(text: str) -> tuple[int, int]:
    insertions = sum(int(match.group(1)) for match in SHORTSTAT_INSERTIONS_RE.finditer(text))
    deletions = sum(int(match.group(1)) for match in SHORTSTAT_DELETIONS_RE.finditer(text))
    return insertions, deletions


def get_commit_change_entries(
    repo: Path,
    author: str,
    ref: str | Sequence[str] = "HEAD",
    exclude_ref: str | None = None,
    limit: int = 80,
    skip: int = 0,
) -> list[CommitChangeEntry]:
    refs = _normalize_git_refs(ref)
    author_patterns = decode_author_patterns(author)
    if len(author_patterns) > 1:
        merged: dict[str, CommitChangeEntry] = {}
        candidate_count = max(limit + skip, 1)
        for pattern in author_patterns:
            for entry in get_commit_change_entries(
                repo,
                pattern,
                refs,
                exclude_ref,
                candidate_count,
                0,
            ):
                merged[entry.commit_hash] = entry
        if not merged:
            return []

        order_args = ["log", "--format=%H", *refs]
        if exclude_ref:
            order_args.extend(["--not", exclude_ref])
        commit_order = {
            commit_hash: index
            for index, commit_hash in enumerate(run_git(repo, order_args).splitlines())
        }
        ordered = sorted(
            merged.values(),
            key=lambda entry: commit_order.get(entry.commit_hash, len(commit_order)),
        )
        return ordered[skip : skip + limit]

    author_pattern = author_patterns[0] if author_patterns else ""
    pretty = "@@COMMIT@@%H%x09%h%x09%ad%x09%s"
    args = [
        "log",
        f"--max-count={max(limit, 1)}",
        f"--skip={max(skip, 0)}",
        "--no-renames",
        "--date=short",
        f"--pretty=tformat:{pretty}",
        "--numstat",
        *refs,
    ]
    if author_pattern:
        args.insert(3, f"--author={author_pattern}")
    if exclude_ref:
        args.extend(["--not", exclude_ref])

    out = run_git(repo, args)
    entries: list[CommitChangeEntry] = []
    current: dict[str, object] | None = None

    def flush_current() -> None:
        nonlocal current
        if current is None:
            return
        entries.append(
            CommitChangeEntry(
                commit_hash=str(current.get("commit_hash", "")),
                short_hash=str(current.get("short_hash", "")),
                date=current.get("date") if isinstance(current.get("date"), dt.date) else None,
                subject=str(current.get("subject", "")),
                insertions=int(current.get("insertions", 0)),
                deletions=int(current.get("deletions", 0)),
            )
        )
        current = None

    for line in out.splitlines():
        if line.startswith("@@COMMIT@@"):
            flush_current()
            meta = line.replace("@@COMMIT@@", "", 1).split("\t", 3)
            commit_hash = meta[0].strip() if len(meta) > 0 else ""
            short_hash = meta[1].strip() if len(meta) > 1 else commit_hash[:7]
            date_value: dt.date | None = None
            if len(meta) > 2:
                try:
                    date_value = dt.date.fromisoformat(meta[2].strip())
                except ValueError:
                    date_value = None
            subject = meta[3].strip() if len(meta) > 3 else ""
            current = {
                "commit_hash": commit_hash,
                "short_hash": short_hash,
                "date": date_value,
                "subject": subject,
                "insertions": 0,
                "deletions": 0,
            }
            continue

        if current is None:
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        if parts[0].isdigit():
            current["insertions"] = int(current.get("insertions", 0)) + int(parts[0])
        if parts[1].isdigit():
            current["deletions"] = int(current.get("deletions", 0)) + int(parts[1])

    flush_current()
    return entries[:limit]


def _normalize_git_refs(ref: str | Sequence[str]) -> tuple[str, ...]:
    if isinstance(ref, str):
        cleaned = ref.strip()
        return (cleaned or "HEAD",)
    refs = tuple(value.strip() for value in ref if value.strip())
    return refs or ("HEAD",)


def get_commit_detail(repo: Path, commit_hash: str) -> CommitDetail:
    metadata = run_git(
        repo,
        [
            "show",
            "-s",
            "--date=iso-strict",
            "--format=%H%x00%h%x00%aI%x00%an%x00%ae%x00%s%x00%b",
            commit_hash,
        ],
    ).rstrip("\r\n")
    fields = metadata.split("\x00", 6)
    if len(fields) != 7:
        raise RuntimeError("Git returned malformed commit metadata.")

    authored_at: dt.datetime | None = None
    try:
        authored_at = dt.datetime.fromisoformat(fields[2].strip())
    except ValueError:
        pass

    numstat = run_git(repo, ["show", "--numstat", "--format=", "--no-renames", commit_hash, "--"])
    files: list[CommitFileChange] = []
    for line in numstat.splitlines():
        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue
        raw_insertions, raw_deletions, path = parts
        files.append(
            CommitFileChange(
                path=path,
                insertions=int(raw_insertions) if raw_insertions.isdigit() else None,
                deletions=int(raw_deletions) if raw_deletions.isdigit() else None,
            )
        )

    return CommitDetail(
        commit_hash=fields[0].strip(),
        short_hash=fields[1].strip(),
        authored_at=authored_at,
        author_name=fields[3].strip(),
        author_email=fields[4].strip(),
        subject=fields[5].strip(),
        body=fields[6].strip(),
        files=tuple(files),
    )


def _populate_total_up_to_stats(repo: Path, ref: str, author: str) -> tuple[int, int]:
    author_patterns = decode_author_patterns(author)
    if len(author_patterns) > 1:
        insertions = 0
        deletions = 0
        for pattern in author_patterns:
            child_insertions, child_deletions = _populate_total_up_to_stats(repo, ref, pattern)
            insertions += child_insertions
            deletions += child_deletions
        return insertions, deletions

    author_pattern = author_patterns[0] if author_patterns else ""
    args = ["log", ref, "--no-renames", "--shortstat", "--pretty=tformat:"]
    if author_pattern:
        args.insert(2, f"--author={author_pattern}")
    out = run_git(repo, args)
    return parse_shortstat_totals(out)


def _populate_committed_range_stats(
    repo: Path,
    base_commit: str,
    author: str,
    ref: str = "HEAD",
    exclude_ref: str | None = None,
) -> tuple[int, int]:
    author_patterns = decode_author_patterns(author)
    if len(author_patterns) > 1:
        insertions = 0
        deletions = 0
        for pattern in author_patterns:
            child_insertions, child_deletions = _populate_committed_range_stats(
                repo,
                base_commit,
                pattern,
                ref,
                exclude_ref,
            )
            insertions += child_insertions
            deletions += child_deletions
        return insertions, deletions

    author_pattern = author_patterns[0] if author_patterns else ""
    args = ["log", f"{base_commit}..{ref}", "--no-renames", "--shortstat", "--pretty=tformat:"]
    if author_pattern:
        args.insert(2, f"--author={author_pattern}")
    if exclude_ref:
        args.extend(["--not", exclude_ref])
    out = run_git(repo, args)
    return parse_shortstat_totals(out)


def parse_date(value: str) -> dt.date:
    return dt.date.fromisoformat(value)


def daily_needed(goal: int, committed_total: int, days_left: int) -> int:
    remaining = max(goal - committed_total, 0)
    if days_left <= 0:
        return remaining
    return math.ceil(remaining / days_left)


def get_total_insertions_up_to(
    repo: Path,
    ref: str,
    author: str,
) -> int:
    _load_cache()
    ref_hash = get_ref_hash(repo, ref)
    cache_key = (_repo_key(repo), author, ref, ref_hash)
    with _CACHE_LOCK:
        cached = _TOTAL_UP_TO_CACHE.get(cache_key)
    if cached is not None:
        return cached

    value, deletions = _populate_total_up_to_stats(repo, ref, author)
    with _CACHE_LOCK:
        _TOTAL_UP_TO_CACHE[cache_key] = value
        _TOTAL_DELETIONS_UP_TO_CACHE[cache_key] = deletions
        _mark_cache_dirty()
    return value


def get_total_deletions_up_to(
    repo: Path,
    ref: str,
    author: str,
) -> int:
    _load_cache()
    ref_hash = get_ref_hash(repo, ref)
    cache_key = (_repo_key(repo), author, ref, ref_hash)
    with _CACHE_LOCK:
        cached = _TOTAL_DELETIONS_UP_TO_CACHE.get(cache_key)
    if cached is not None:
        return cached

    insertions, value = _populate_total_up_to_stats(repo, ref, author)
    with _CACHE_LOCK:
        _TOTAL_UP_TO_CACHE[cache_key] = insertions
        _TOTAL_DELETIONS_UP_TO_CACHE[cache_key] = value
        _mark_cache_dirty()
    return value

def get_committed_insertions(
    repo: Path,
    base_commit: str,
    author: str,
    ref: str = "HEAD",
    exclude_ref: str | None = None,
) -> int:
    _load_cache()
    ref_hash = get_ref_hash(repo, ref)
    exclude_hash = get_ref_hash(repo, exclude_ref) if exclude_ref else ""
    cache_key = (_repo_key(repo), base_commit, author, ref, ref_hash, exclude_ref or "", exclude_hash)
    with _CACHE_LOCK:
        cached = _COMMITTED_INSERTIONS_CACHE.get(cache_key)
    if cached is not None:
        return cached

    value, deletions = _populate_committed_range_stats(repo, base_commit, author, ref, exclude_ref)
    with _CACHE_LOCK:
        _COMMITTED_INSERTIONS_CACHE[cache_key] = value
        _COMMITTED_DELETIONS_CACHE[cache_key] = deletions
        _mark_cache_dirty()
    return value


def get_committed_deletions(
    repo: Path,
    base_commit: str,
    author: str,
    ref: str = "HEAD",
    exclude_ref: str | None = None,
) -> int:
    _load_cache()
    ref_hash = get_ref_hash(repo, ref)
    exclude_hash = get_ref_hash(repo, exclude_ref) if exclude_ref else ""
    cache_key = (_repo_key(repo), base_commit, author, ref, ref_hash, exclude_ref or "", exclude_hash)
    with _CACHE_LOCK:
        cached = _COMMITTED_DELETIONS_CACHE.get(cache_key)
    if cached is not None:
        return cached

    insertions, value = _populate_committed_range_stats(repo, base_commit, author, ref, exclude_ref)
    with _CACHE_LOCK:
        _COMMITTED_INSERTIONS_CACHE[cache_key] = insertions
        _COMMITTED_DELETIONS_CACHE[cache_key] = value
        _mark_cache_dirty()
    return value


def get_uncommitted_insertions(repo: Path) -> int:
    tracked_insertions = get_tracked_text_insertions(repo)
    untracked_insertions = get_untracked_text_insertions(repo)
    return tracked_insertions + untracked_insertions


def get_uncommitted_insertions_by_language(repo: Path) -> dict[str, int]:
    tracked_out = run_git(repo, ["diff", "--numstat", "--no-renames", "HEAD"])
    tracked = parse_numstat_insertions_by_language(tracked_out)

    untracked: dict[str, int] = {}
    untracked_out = run_git(repo, ["ls-files", "--others", "--exclude-standard"])
    for path_text in (line.strip() for line in untracked_out.splitlines() if line.strip()):
        if is_probably_binary_path(path_text):
            continue
        line_count = count_text_lines(repo / path_text)
        if line_count <= 0:
            continue
        language = classify_text_language(path_text)
        untracked[language] = untracked.get(language, 0) + line_count

    return merge_language_totals(tracked, untracked)


def get_uncommitted_deletions(repo: Path) -> int:
    return get_tracked_text_deletions(repo)


def get_tracked_text_insertions(repo: Path) -> int:
    names_out = run_git(repo, ["diff", "--name-only", "--no-renames", "HEAD"])
    changed_paths = [p.strip() for p in names_out.splitlines() if p.strip()]
    if not changed_paths:
        return 0

    text_paths = [p for p in changed_paths if not is_probably_binary_path(p)]
    if not text_paths:
        return 0

    args = ["diff", "--numstat", "--no-renames", "HEAD", "--", *text_paths]
    diff_out = run_git(repo, args)
    return parse_numstat_insertions(diff_out)


def get_tracked_text_deletions(repo: Path) -> int:
    names_out = run_git(repo, ["diff", "--name-only", "--no-renames", "HEAD"])
    changed_paths = [p.strip() for p in names_out.splitlines() if p.strip()]
    if not changed_paths:
        return 0

    text_paths = [p for p in changed_paths if not is_probably_binary_path(p)]
    if not text_paths:
        return 0

    args = ["diff", "--numstat", "--no-renames", "HEAD", "--", *text_paths]
    diff_out = run_git(repo, args)
    return parse_numstat_deletions(diff_out)


def get_untracked_text_insertions(repo: Path) -> int:
    out = run_git(repo, ["ls-files", "--others", "--exclude-standard"])
    files = [line.strip() for line in out.splitlines() if line.strip()]
    if not files:
        return 0

    total = 0

    for rel_path in files:
        if is_probably_binary_path(rel_path):
            continue
        total += count_text_lines(repo / rel_path)

    return total


def get_project_total_lines(repo: Path, ref: str = "HEAD") -> int:
    _load_cache()
    ref_hash = get_ref_hash(repo, ref)
    cache_key = (_repo_key(repo), ref, ref_hash)
    with _CACHE_LOCK:
        cached_head_total = _PROJECT_TOTAL_LINES_CACHE.get(cache_key)

    tracked_insertions = get_tracked_text_insertions(repo)
    tracked_deletions = get_tracked_text_deletions(repo)
    untracked_insertions = get_untracked_text_insertions(repo)

    if cached_head_total is None:
        current_tracked_total = get_worktree_tracked_text_total(repo)
        cached_head_total = max(current_tracked_total - tracked_insertions + tracked_deletions, 0)
        with _CACHE_LOCK:
            _PROJECT_TOTAL_LINES_CACHE[cache_key] = cached_head_total
            _mark_cache_dirty()

    return max(cached_head_total + tracked_insertions - tracked_deletions + untracked_insertions, 0)


def get_commit_count(
    repo: Path,
    author: str,
    ref: str = "HEAD",
    exclude_ref: str | None = None,
    since: dt.date | None = None,
    until: dt.date | None = None,
) -> int:
    _load_cache()
    ref_hash = get_ref_hash(repo, ref)
    exclude_hash = get_ref_hash(repo, exclude_ref) if exclude_ref else ""
    since_key = since.isoformat() if since else ""
    until_key = until.isoformat() if until else ""
    cache_key = (_repo_key(repo), author, ref, ref_hash, exclude_ref or "", exclude_hash, since_key, until_key)
    with _CACHE_LOCK:
        cached = _COMMIT_COUNT_CACHE.get(cache_key)
    if cached is not None:
        return cached

    author_patterns = decode_author_patterns(author)
    if len(author_patterns) > 1:
        value = sum(get_commit_count(repo, pattern, ref, exclude_ref, since, until) for pattern in author_patterns)
        with _CACHE_LOCK:
            _COMMIT_COUNT_CACHE[cache_key] = value
            _mark_cache_dirty()
        return value

    author_pattern = author_patterns[0] if author_patterns else ""
    args = ["rev-list", "--count"]
    if since is not None:
        args.append(f"--since={since.isoformat()}")
    if until is not None:
        args.append(f"--until={until.isoformat()}")
    if author_pattern:
        args.append(f"--author={author_pattern}")
    args.append(ref)
    if exclude_ref:
        args.extend(["--not", exclude_ref])
    out = run_git(repo, args).strip()
    value = int(out) if out else 0
    with _CACHE_LOCK:
        _COMMIT_COUNT_CACHE[cache_key] = value
        _mark_cache_dirty()
    return value


def get_commit_counts_by_date(
    repo: Path,
    start_day: dt.date,
    end_day: dt.date,
    author: str,
    ref: str = "HEAD",
    exclude_ref: str | None = None,
) -> dict[dt.date, int]:
    _load_cache()
    if end_day < start_day:
        return {}

    ref_hash = get_ref_hash(repo, ref)
    exclude_hash = get_ref_hash(repo, exclude_ref) if exclude_ref else ""
    cache_key = (
        _repo_key(repo),
        start_day.isoformat(),
        end_day.isoformat(),
        author,
        ref,
        ref_hash,
        exclude_ref or "",
        exclude_hash,
    )
    with _CACHE_LOCK:
        cached = _COMMITS_BY_DATE_CACHE.get(cache_key)
    if cached is not None:
        return dict(cached)

    author_patterns = decode_author_patterns(author)
    if len(author_patterns) > 1:
        merged: dict[dt.date, int] = {}
        for pattern in author_patterns:
            daily = get_commit_counts_by_date(repo, start_day, end_day, pattern, ref, exclude_ref)
            for day, value in daily.items():
                merged[day] = merged.get(day, 0) + value
        with _CACHE_LOCK:
            _COMMITS_BY_DATE_CACHE[cache_key] = dict(merged)
            _mark_cache_dirty()
        return merged

    until_day = end_day + dt.timedelta(days=1)
    author_pattern = author_patterns[0] if author_patterns else ""
    args = ["log"]
    args.extend(
        [
            f"--since={start_day.isoformat()} 00:00:00",
            f"--until={until_day.isoformat()} 00:00:00",
            "--date=short",
            "--pretty=tformat:@@DATE@@%ad",
            ref,
        ]
    )
    if author_pattern:
        args.insert(3, f"--author={author_pattern}")
    if exclude_ref:
        args.extend(["--not", exclude_ref])

    out = run_git(repo, args)
    daily: dict[dt.date, int] = {}

    for line in out.splitlines():
        if not line.startswith("@@DATE@@"):
            continue
        date_text = line.replace("@@DATE@@", "", 1).strip()
        try:
            day = dt.date.fromisoformat(date_text)
        except ValueError:
            continue
        daily[day] = daily.get(day, 0) + 1

    with _CACHE_LOCK:
        _COMMITS_BY_DATE_CACHE[cache_key] = dict(daily)
        _mark_cache_dirty()
    return daily



def get_committed_insertions_for_date(
    repo: Path,
    day: dt.date,
    author: str,
    ref: str = "HEAD",
    exclude_ref: str | None = None,
) -> int:
    _load_cache()
    ref_hash = get_ref_hash(repo, ref)
    exclude_hash = get_ref_hash(repo, exclude_ref) if exclude_ref else ""
    cache_key = (
        _repo_key(repo),
        day.isoformat(),
        author,
        ref,
        ref_hash,
        exclude_ref or "",
        exclude_hash,
    )
    with _CACHE_LOCK:
        cached = _FOR_DATE_CACHE.get(cache_key)
    if cached is not None:
        return cached

    author_patterns = decode_author_patterns(author)
    if len(author_patterns) > 1:
        value = sum(
            get_committed_insertions_for_date(repo, day, pattern, ref, exclude_ref)
            for pattern in author_patterns
        )
        with _CACHE_LOCK:
            _FOR_DATE_CACHE[cache_key] = value
            _mark_cache_dirty()
        return value

    next_day = day + dt.timedelta(days=1)
    author_pattern = author_patterns[0] if author_patterns else ""
    args = ["log"]
    args.extend(
        [
            f"--since={day.isoformat()}",
            f"--until={next_day.isoformat()}",
            "--no-renames",
            "--numstat",
            "--pretty=tformat:",
            ref,
        ]
    )
    if author_pattern:
        args.insert(3, f"--author={author_pattern}")
    if exclude_ref:
        args.extend(["--not", exclude_ref])
    out = run_git(repo, args)
    value = parse_numstat_insertions(out)
    with _CACHE_LOCK:
        _FOR_DATE_CACHE[cache_key] = value
        _mark_cache_dirty()
    return value


def get_committed_insertions_by_date_and_language(
    repo: Path,
    start_day: dt.date,
    end_day: dt.date,
    author: str,
    ref: str = "HEAD",
    exclude_ref: str | None = None,
) -> dict[dt.date, dict[str, int]]:
    _load_cache()
    if end_day < start_day:
        return {}

    ref_hash = get_ref_hash(repo, ref)
    exclude_hash = get_ref_hash(repo, exclude_ref) if exclude_ref else ""
    cache_key = (
        _repo_key(repo),
        start_day.isoformat(),
        end_day.isoformat(),
        author,
        ref,
        ref_hash,
        exclude_ref or "",
        exclude_hash,
    )
    with _CACHE_LOCK:
        cached = _LANGUAGE_BY_DATE_CACHE.get(cache_key)
    if cached is not None:
        return {day: dict(totals) for day, totals in cached.items()}

    author_patterns = decode_author_patterns(author)
    if len(author_patterns) > 1:
        merged: dict[dt.date, dict[str, int]] = {}
        for pattern in author_patterns:
            daily = get_committed_insertions_by_date_and_language(
                repo,
                start_day,
                end_day,
                pattern,
                ref,
                exclude_ref,
            )
            for day, totals in daily.items():
                merged[day] = merge_language_totals(merged.get(day, {}), totals)
        with _CACHE_LOCK:
            _LANGUAGE_BY_DATE_CACHE[cache_key] = {
                day: dict(totals) for day, totals in merged.items()
            }
            _BY_DATE_CACHE[cache_key] = {
                day: sum(totals.values()) for day, totals in merged.items()
            }
            _mark_cache_dirty()
        return merged

    repo_key = _repo_key(repo)
    with _CACHE_LOCK:
        for key, value in _LANGUAGE_BY_DATE_CACHE.items():
            if len(key) != 8:
                continue
            if (
                key[0] != repo_key
                or key[3] != author
                or key[4] != ref
                or key[5] != ref_hash
                or key[6] != (exclude_ref or "")
                or key[7] != exclude_hash
            ):
                continue
            try:
                cached_start = dt.date.fromisoformat(str(key[1]))
                cached_end = dt.date.fromisoformat(str(key[2]))
            except ValueError:
                continue
            if cached_start <= start_day and cached_end >= end_day:
                sliced = {
                    day: dict(totals)
                    for day, totals in value.items()
                    if start_day <= day <= end_day
                }
                _LANGUAGE_BY_DATE_CACHE[cache_key] = {
                    day: dict(totals) for day, totals in sliced.items()
                }
                _BY_DATE_CACHE[cache_key] = {
                    day: sum(totals.values()) for day, totals in sliced.items()
                }
                _mark_cache_dirty()
                return sliced

    until_day = end_day + dt.timedelta(days=1)
    author_pattern = author_patterns[0] if author_patterns else ""
    args = ["log"]
    args.extend(
        [
            f"--since={start_day.isoformat()} 00:00:00",
            f"--until={until_day.isoformat()} 00:00:00",
            "--no-renames",
            "--date=short",
            "--pretty=tformat:@@DATE@@%ad",
            "--numstat",
            ref,
        ]
    )
    if author_pattern:
        args.insert(3, f"--author={author_pattern}")
    if exclude_ref:
        args.extend(["--not", exclude_ref])

    daily = parse_numstat_insertions_by_date_and_language(run_git(repo, args))

    with _CACHE_LOCK:
        _LANGUAGE_BY_DATE_CACHE[cache_key] = {
            day: dict(totals) for day, totals in daily.items()
        }
        _BY_DATE_CACHE[cache_key] = {
            day: sum(totals.values()) for day, totals in daily.items()
        }
        _mark_cache_dirty()
    return daily


def get_committed_insertions_by_date(
    repo: Path,
    start_day: dt.date,
    end_day: dt.date,
    author: str,
    ref: str = "HEAD",
    exclude_ref: str | None = None,
) -> dict[dt.date, int]:
    daily = get_committed_insertions_by_date_and_language(
        repo,
        start_day,
        end_day,
        author,
        ref,
        exclude_ref,
    )
    return {day: sum(totals.values()) for day, totals in daily.items()}


def _get_commit_active_dates(
    repo: Path,
    author: str,
    ref: str = "HEAD",
    exclude_ref: str | None = None,
) -> tuple[str, ...]:
    _load_cache()
    ref_hash = get_ref_hash(repo, ref)
    exclude_hash = get_ref_hash(repo, exclude_ref) if exclude_ref else ""
    cache_key = (_repo_key(repo), author, ref, ref_hash, exclude_ref or "", exclude_hash)
    with _CACHE_LOCK:
        cached = _ACTIVE_COMMIT_DATES_CACHE.get(cache_key)
    if cached is not None:
        return cached

    author_patterns = decode_author_patterns(author)
    if len(author_patterns) > 1:
        merged_days: set[str] = set()
        for pattern in author_patterns:
            merged_days.update(_get_commit_active_dates(repo, pattern, ref, exclude_ref))
        merged_value = tuple(sorted(merged_days))
        with _CACHE_LOCK:
            _ACTIVE_COMMIT_DATES_CACHE[cache_key] = merged_value
            _mark_cache_dirty()
        return merged_value

    author_pattern = author_patterns[0] if author_patterns else ""
    args = ["log", "--date=short", "--pretty=tformat:%ad"]
    if author_pattern:
        args.append(f"--author={author_pattern}")
    args.append(ref)
    if exclude_ref:
        args.extend(["--not", exclude_ref])

    out = run_git(repo, args)
    active_days = tuple(sorted({line.strip() for line in out.splitlines() if line.strip()}))
    with _CACHE_LOCK:
        _ACTIVE_COMMIT_DATES_CACHE[cache_key] = active_days
        _mark_cache_dirty()
    return active_days


def get_commit_active_day_count(
    repo: Path,
    author: str,
    ref: str = "HEAD",
    exclude_ref: str | None = None,
) -> int:
    return len(_get_commit_active_dates(repo, author, ref, exclude_ref))


def get_commit_active_day_count_combined(
    repo: Path,
    author: str,
    ref: str,
    include_local: bool,
) -> int:
    merged_days = set(_get_commit_active_dates(repo, author, ref))
    if not include_local:
        return len(merged_days)
    current_ref = resolve_current_ref(repo)
    if current_ref == ref:
        return len(merged_days)
    merged_days.update(_get_commit_active_dates(repo, author, current_ref, exclude_ref=ref))
    return len(merged_days)


def get_committed_deletions_by_date(
    repo: Path,
    start_day: dt.date,
    end_day: dt.date,
    author: str,
    ref: str = "HEAD",
    exclude_ref: str | None = None,
) -> dict[dt.date, int]:
    _load_cache()
    if end_day < start_day:
        return {}

    ref_hash = get_ref_hash(repo, ref)
    exclude_hash = get_ref_hash(repo, exclude_ref) if exclude_ref else ""
    cache_key = (
        _repo_key(repo),
        start_day.isoformat(),
        end_day.isoformat(),
        author,
        ref,
        ref_hash,
        exclude_ref or "",
        exclude_hash,
    )
    with _CACHE_LOCK:
        cached = _DELETIONS_BY_DATE_CACHE.get(cache_key)
    if cached is not None:
        return dict(cached)

    author_patterns = decode_author_patterns(author)
    if len(author_patterns) > 1:
        merged: dict[dt.date, int] = {}
        for pattern in author_patterns:
            daily = get_committed_deletions_by_date(repo, start_day, end_day, pattern, ref, exclude_ref)
            for day, value in daily.items():
                merged[day] = merged.get(day, 0) + value
        with _CACHE_LOCK:
            _DELETIONS_BY_DATE_CACHE[cache_key] = dict(merged)
            _mark_cache_dirty()
        return merged

    repo_key = _repo_key(repo)
    with _CACHE_LOCK:
        for key, value in _DELETIONS_BY_DATE_CACHE.items():
            if len(key) != 8:
                continue
            if (
                key[0] != repo_key
                or key[3] != author
                or key[4] != ref
                or key[5] != ref_hash
                or key[6] != (exclude_ref or "")
                or key[7] != exclude_hash
            ):
                continue
            try:
                cached_start = dt.date.fromisoformat(str(key[1]))
                cached_end = dt.date.fromisoformat(str(key[2]))
            except ValueError:
                continue
            if cached_start <= start_day and cached_end >= end_day:
                sliced = {day: val for day, val in value.items() if start_day <= day <= end_day}
                _DELETIONS_BY_DATE_CACHE[cache_key] = dict(sliced)
                _mark_cache_dirty()
                return dict(sliced)

    until_day = end_day + dt.timedelta(days=1)
    author_pattern = author_patterns[0] if author_patterns else ""
    args = ["log"]
    args.extend(
        [
            f"--since={start_day.isoformat()} 00:00:00",
            f"--until={until_day.isoformat()} 00:00:00",
            "--no-renames",
            "--date=short",
            "--pretty=tformat:@@DATE@@%ad",
            "--numstat",
            ref,
        ]
    )
    if author_pattern:
        args.insert(3, f"--author={author_pattern}")
    if exclude_ref:
        args.extend(["--not", exclude_ref])

    out = run_git(repo, args)
    daily: dict[dt.date, int] = {}
    current_day: dt.date | None = None

    for line in out.splitlines():
        if line.startswith("@@DATE@@"):
            date_text = line.replace("@@DATE@@", "", 1).strip()
            try:
                current_day = dt.date.fromisoformat(date_text)
            except ValueError:
                current_day = None
            if current_day is not None and current_day not in daily:
                daily[current_day] = 0
            continue

        if current_day is None:
            continue

        parts = line.split("\t")
        if len(parts) < 3:
            continue
        if parts[1].isdigit():
            daily[current_day] = daily.get(current_day, 0) + int(parts[1])

    with _CACHE_LOCK:
        _DELETIONS_BY_DATE_CACHE[cache_key] = dict(daily)
        _mark_cache_dirty()
    return daily


def get_committed_insertions_for_date_combined(
    repo: Path,
    day: dt.date,
    author: str,
    ref: str,
    include_local: bool,
) -> int:
    total = get_committed_insertions_for_date(repo, day, author, ref)
    if not include_local:
        return total
    current_ref = resolve_current_ref(repo)
    if current_ref == ref:
        return total
    extra = get_committed_insertions_for_date(repo, day, author, current_ref, exclude_ref=ref)
    return total + extra


def get_committed_insertions_by_date_combined(
    repo: Path,
    start_day: dt.date,
    end_day: dt.date,
    author: str,
    ref: str,
    include_local: bool,
) -> dict[dt.date, int]:
    base = get_committed_insertions_by_date(repo, start_day, end_day, author, ref)
    if not include_local:
        return base
    current_ref = resolve_current_ref(repo)
    if current_ref == ref:
        return base
    extra = get_committed_insertions_by_date(repo, start_day, end_day, author, current_ref, exclude_ref=ref)
    merged = dict(base)
    for day, value in extra.items():
        merged[day] = merged.get(day, 0) + value
    return merged


def get_committed_insertions_by_date_and_language_combined(
    repo: Path,
    start_day: dt.date,
    end_day: dt.date,
    author: str,
    ref: str,
    include_local: bool,
) -> dict[dt.date, dict[str, int]]:
    base = get_committed_insertions_by_date_and_language(
        repo,
        start_day,
        end_day,
        author,
        ref,
    )
    if not include_local:
        return base
    current_ref = resolve_current_ref(repo)
    if current_ref == ref:
        return base
    extra = get_committed_insertions_by_date_and_language(
        repo,
        start_day,
        end_day,
        author,
        current_ref,
        exclude_ref=ref,
    )
    merged = {day: dict(totals) for day, totals in base.items()}
    for day, totals in extra.items():
        merged[day] = merge_language_totals(merged.get(day, {}), totals)
    return merged


def get_committed_deletions_by_date_combined(
    repo: Path,
    start_day: dt.date,
    end_day: dt.date,
    author: str,
    ref: str,
    include_local: bool,
) -> dict[dt.date, int]:
    base = get_committed_deletions_by_date(repo, start_day, end_day, author, ref)
    if not include_local:
        return base
    current_ref = resolve_current_ref(repo)
    if current_ref == ref:
        return base
    extra = get_committed_deletions_by_date(repo, start_day, end_day, author, current_ref, exclude_ref=ref)
    merged = dict(base)
    for day, value in extra.items():
        merged[day] = merged.get(day, 0) + value
    return merged


def get_commit_counts_by_date_combined(
    repo: Path,
    start_day: dt.date,
    end_day: dt.date,
    author: str,
    ref: str,
    include_local: bool,
) -> dict[dt.date, int]:
    base = get_commit_counts_by_date(repo, start_day, end_day, author, ref)
    if not include_local:
        return base
    current_ref = resolve_current_ref(repo)
    if current_ref == ref:
        return base
    extra = get_commit_counts_by_date(repo, start_day, end_day, author, current_ref, exclude_ref=ref)
    merged = dict(base)
    for day, value in extra.items():
        merged[day] = merged.get(day, 0) + value
    return merged


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Track monthly insertion-line target from git.")
    parser.add_argument("--repo", default=".", help="Git repository path.")
    parser.add_argument("--goal", type=int, default=DEFAULT_GOAL, help="Target total insertion lines.")
    parser.add_argument(
        "--base-total",
        type=int,
        default=DEFAULT_BASE_TOTAL,
        help="Committed total at base commit. Use -1 for auto.",
    )
    parser.add_argument(
        "--base-commit",
        default=DEFAULT_BASE_COMMIT,
        help="Base commit hash for line tracking. Use 'auto' for month start.",
    )
    parser.add_argument(
        "--ref",
        default="auto",
        help="Git ref/branch to track. Use 'auto' for default branch.",
    )
    parser.add_argument(
        "--include-local",
        action="store_true",
        help="Include local branch commits not in the default branch (default: on).",
    )
    parser.add_argument(
        "--no-include-local",
        action="store_true",
        help="Exclude local branch commits.",
    )
    parser.add_argument(
        "--author",
        default=DEFAULT_AUTHOR,
        help="Author filter for committed insertions. Default: git user.name.",
    )
    parser.add_argument(
        "--today",
        type=parse_date,
        default=None,
        help="Override today's date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--month-end",
        type=parse_date,
        default=None,
        help="Month end date for the target period (YYYY-MM-DD). Default: end of current month.",
    )
    parser.add_argument(
        "--assume-uncommitted-zero",
        action="store_true",
        help="Force uncommitted insertion lines to 0.",
    )
    return parser


def resolve_month_end(today: dt.date, month_end: dt.date | None) -> dt.date:
    if month_end is not None:
        return month_end
    last_day = calendar.monthrange(today.year, today.month)[1]
    return dt.date(today.year, today.month, last_day)


def compute_metrics(config: TrackerConfig) -> TrackerResult:
    repo = find_repo_root(config.repo).resolve()
    today = config.today or dt.date.today()
    month_end = resolve_month_end(today, config.month_end)
    days_left_including_today = max((month_end - today).days + 1, 0)
    days_left_after_today = max(days_left_including_today - 1, 0)

    author = resolve_author(repo, config.author)
    ref = resolve_ref(repo, config.ref)
    base_commit = resolve_base_commit(repo, today, config.base_commit, ref)
    committed_insertions = get_committed_insertions(repo, base_commit, author, ref)
    if config.include_local:
        current_ref = resolve_current_ref(repo)
        if current_ref != ref:
            committed_insertions += get_committed_insertions(
                repo,
                ref,
                author,
                current_ref,
            )
    if config.base_total < 0:
        base_total = get_total_insertions_up_to(repo, base_commit, author)
    else:
        base_total = config.base_total
    committed_total = base_total + committed_insertions

    uncommitted = 0 if config.assume_uncommitted_zero else get_uncommitted_insertions(repo)

    need_today = daily_needed(config.goal, committed_total, days_left_including_today)
    need_after_commit = daily_needed(config.goal, committed_total + uncommitted, days_left_after_today)

    return TrackerResult(
        today=today,
        month_end=month_end,
        days_left_including_today=days_left_including_today,
        days_left_after_today=days_left_after_today,
        committed_total=committed_total,
        uncommitted_insertions=uncommitted,
        need_today=need_today,
        need_after_commit=need_after_commit,
    )


def format_output_lines(result: TrackerResult) -> list[str]:
    return [
        f"- 오늘 날짜: {result.today.isoformat()}",
        f"- 남은 날짜({result.month_end.month}월): {result.days_left_including_today}일",
        (
            f"- 일일 필요 추가줄: {result.need_today}줄/일 "
            f"[커밋 후 {result.need_after_commit}줄/일]"
        ),
        f"- 현재 추가줄(미커밋): {result.uncommitted_insertions}줄",
    ]


atexit.register(_save_cache)


def main() -> int:
    parser = make_parser()
    args = parser.parse_args()
    repo = find_repo_root(Path(args.repo))
    author = resolve_author(repo, args.author)
    include_local = not args.no_include_local
    config = TrackerConfig(
        repo=repo,
        goal=args.goal,
        base_total=args.base_total,
        base_commit=args.base_commit,
        author=author,
        ref=args.ref,
        include_local=include_local,
        today=args.today,
        month_end=args.month_end,
        assume_uncommitted_zero=args.assume_uncommitted_zero,
    )
    result = compute_metrics(config)
    print("\n".join(format_output_lines(result)))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
