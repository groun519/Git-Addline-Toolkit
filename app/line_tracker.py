#!/usr/bin/env python3
from __future__ import annotations

import argparse
import atexit
import calendar
import datetime as dt
import json
import math
import re
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path


DEFAULT_GOAL = 20000
DEFAULT_BASE_TOTAL = -1
DEFAULT_BASE_COMMIT = "auto"
DEFAULT_AUTHOR = "auto"
CACHE_VERSION = 2

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

_COMMITTED_INSERTIONS_CACHE: dict[tuple[str, str, str, str, str, str, str], int] = {}
_BY_DATE_CACHE: dict[tuple[str, str, str, str, str, str, str, str], dict[dt.date, int]] = {}
_FOR_DATE_CACHE: dict[tuple[str, str, str, str, str, str, str], int] = {}
_TOTAL_UP_TO_CACHE: dict[tuple[str, str, str, str], int] = {}
_CACHE_LOCK = threading.RLock()
_CACHE_LOADED = False
_CACHE_DIRTY = False
_CACHE_PATH = Path(__file__).resolve().with_name("line_tracker_cache.json")


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


def run_git(repo: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {stderr}")
    return result.stdout


def find_repo_root(start: Path) -> Path:
    try:
        result = subprocess.run(
            ["git", "-C", str(start), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
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
    if not _CACHE_PATH.exists():
        return
    try:
        raw = _CACHE_PATH.read_text(encoding="utf-8")
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

    with _CACHE_LOCK:
        load_map(data.get("committed"), _COMMITTED_INSERTIONS_CACHE)
        load_map(data.get("for_date"), _FOR_DATE_CACHE)
        load_map(data.get("total"), _TOTAL_UP_TO_CACHE)
        load_map(data.get("by_date"), _BY_DATE_CACHE, convert_dates=True)


def _save_cache() -> None:
    global _CACHE_DIRTY
    if not _CACHE_DIRTY:
        return
    payload = {
        "version": CACHE_VERSION,
        "committed": [],
        "for_date": [],
        "total": [],
        "by_date": [],
    }
    with _CACHE_LOCK:
        for key, value in _COMMITTED_INSERTIONS_CACHE.items():
            payload["committed"].append([list(key), value])
        for key, value in _FOR_DATE_CACHE.items():
            payload["for_date"].append([list(key), value])
        for key, value in _TOTAL_UP_TO_CACHE.items():
            payload["total"].append([list(key), value])
        for key, value in _BY_DATE_CACHE.items():
            payload["by_date"].append(
                [list(key), {day.isoformat(): val for day, val in value.items()}]
            )
    try:
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
        clear_dict(_FOR_DATE_CACHE)
        clear_dict(_TOTAL_UP_TO_CACHE)
        clear_dict(_BY_DATE_CACHE)
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
        result = subprocess.run(
            ["git", "show-ref", "--verify", "--quiet", ref],
            cwd=repo,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
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

    args = ["log", ref, "--no-renames", "--numstat", "--pretty=tformat:"]
    if author:
        args.insert(2, f"--author={author}")
    out = run_git(repo, args)
    value = parse_numstat_insertions(out)
    with _CACHE_LOCK:
        _TOTAL_UP_TO_CACHE[cache_key] = value
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

    args = ["log", f"{base_commit}..{ref}", "--no-renames", "--numstat", "--pretty=tformat:"]
    if author:
        args.insert(2, f"--author={author}")
    if exclude_ref:
        args.extend(["--not", exclude_ref])
    out = run_git(repo, args)
    value = parse_numstat_insertions(out)
    with _CACHE_LOCK:
        _COMMITTED_INSERTIONS_CACHE[cache_key] = value
        _mark_cache_dirty()
    return value


def get_uncommitted_insertions(repo: Path) -> int:
    tracked_insertions = get_tracked_text_insertions(repo)
    untracked_insertions = get_untracked_text_insertions(repo)
    return tracked_insertions + untracked_insertions


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

    next_day = day + dt.timedelta(days=1)
    args = [
        "log",
        f"--since={day.isoformat()}",
        f"--until={next_day.isoformat()}",
        "--no-renames",
        "--numstat",
        "--pretty=tformat:",
        ref,
    ]
    if author:
        args.insert(3, f"--author={author}")
    if exclude_ref:
        args.extend(["--not", exclude_ref])
    out = run_git(repo, args)
    value = parse_numstat_insertions(out)
    with _CACHE_LOCK:
        _FOR_DATE_CACHE[cache_key] = value
        _mark_cache_dirty()
    return value


def get_committed_insertions_by_date(
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
        cached = _BY_DATE_CACHE.get(cache_key)
    if cached is not None:
        return dict(cached)

    repo_key = _repo_key(repo)
    with _CACHE_LOCK:
        for key, value in _BY_DATE_CACHE.items():
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
                _BY_DATE_CACHE[cache_key] = dict(sliced)
                _mark_cache_dirty()
                return dict(sliced)

    until_day = end_day + dt.timedelta(days=1)
    args = [
        "log",
        f"--since={start_day.isoformat()} 00:00:00",
        f"--until={until_day.isoformat()} 00:00:00",
        "--no-renames",
        "--date=short",
        "--pretty=tformat:@@DATE@@%ad",
        "--numstat",
        ref,
    ]
    if author:
        args.insert(3, f"--author={author}")
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
        if parts[0].isdigit():
            daily[current_day] = daily.get(current_day, 0) + int(parts[0])

    with _CACHE_LOCK:
        _BY_DATE_CACHE[cache_key] = dict(daily)
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
