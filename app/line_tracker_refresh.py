from __future__ import annotations

import atexit
import datetime as dt
import json
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from line_tracker import (
    LANGUAGE_NAMES,
    TrackerConfig,
    TrackerResult,
    classify_text_language,
    compute_metrics,
    daily_needed,
    decode_author_patterns,
    get_commit_active_day_count,
    get_commit_active_day_count_combined,
    get_commit_count,
    get_commit_counts_by_date_combined,
    get_committed_deletions,
    get_committed_deletions_by_date_combined,
    get_committed_insertions,
    get_committed_insertions_by_date_and_language_combined,
    get_project_language_lines,
    get_app_state_path,
    get_ref_hash,
    get_total_deletions_up_to,
    get_total_insertions_up_to,
    get_uncommitted_deletions,
    get_uncommitted_insertions,
    get_uncommitted_insertions_by_language,
    is_probably_binary_path,
    list_branch_refs,
    merge_language_totals,
    resolve_author,
    resolve_base_commit,
    resolve_current_ref,
    resolve_month_end,
    resolve_ref,
    run_git,
)


RefreshProgress = Callable[[int, str], None]
GRAPH_AVAILABLE_DAYS = 180


@dataclass(frozen=True)
class RefreshSnapshot:
    author: str
    tracked_ref: str
    current_ref: str
    base_ref: str
    result: TrackerResult
    today_done: int
    today_target: int
    points: list[tuple[dt.date, int]]
    graph_added_points: list[tuple[dt.date, int]]
    graph_deleted_points: list[tuple[dt.date, int]]
    graph_commit_points: list[tuple[dt.date, int]]
    graph_language_points: dict[str, list[tuple[dt.date, int]]]
    graph_available_added_points: list[tuple[dt.date, int]]
    graph_available_deleted_points: list[tuple[dt.date, int]]
    graph_available_commit_points: list[tuple[dt.date, int]]
    graph_available_language_points: dict[str, list[tuple[dt.date, int]]]
    grass_points: list[tuple[dt.date, int]]
    graph_days: int
    graph_avg: float
    graph_max: int
    branch_total: int
    branch_deletions: int
    branch_active_days: int
    daily_commit_count: int
    branch_commit_count: int
    overall_commit_count: int
    project_commit_count: int
    project_active_days: int
    repository_birth_date: dt.date | None
    overall_active_days: int
    overall_deletions: int
    project_total_lines: int
    project_cumulative_lines: int
    project_cumulative_deletions: int
    project_language_lines: dict[str, int]
    overall_progress_language_lines: dict[str, int]
    daily_progress_language_lines: dict[str, int]
    share_text: str
    user_cumulative_lines: int
    user_cumulative_deletions: int
    uncommitted_deletions: int
    selected_branches: tuple[str, ...] = ()
    progress_branch_total: int = 0
    daily_removed: int = 0
    graph_uncommitted_insertions: int = 0
    branch_stats: tuple[BranchStats, ...] = ()
    history_refs: tuple[str, ...] = ()
    history_exclude_ref: str = ""


@dataclass(frozen=True)
class BranchStats:
    ref: str
    additions: int
    deletions: int
    commits: int
    active_days: int
    started_on: dt.date | None = None


def get_grass_date_range(day: dt.date) -> tuple[dt.date, dt.date]:
    return dt.date(day.year, 1, 1), dt.date(day.year, 12, 31)


@dataclass(frozen=True)
class BranchCommitActivity:
    day: dt.date
    additions: int
    deletions: int
    languages: dict[str, int]
    author_name: str = ""
    author_email: str = ""


_BRANCH_UNION_CACHE_VERSION = 1
_BRANCH_UNION_CACHE_MAX = 24
_BRANCH_UNION_CACHE_PATH = get_app_state_path("line_tracker_branch_union_cache.json")
_BRANCH_UNION_CACHE: dict[str, dict[str, BranchCommitActivity]] = {}
_BRANCH_UNION_CACHE_LOCK = threading.RLock()
_BRANCH_UNION_CACHE_LOADED = False
_BRANCH_UNION_CACHE_DIRTY = False


@dataclass(frozen=True)
class ProjectHistoryStats:
    additions: int
    deletions: int
    commits: int
    active_days: int
    birth_date: dt.date | None


def includes_tracked_branch(tracked_ref: str, branch_refs: tuple[str, ...]) -> bool:
    local_name = tracked_ref.split("/", 1)[-1]
    return tracked_ref in branch_refs or local_name in branch_refs


def _load_branch_union_cache() -> None:
    global _BRANCH_UNION_CACHE_LOADED
    if _BRANCH_UNION_CACHE_LOADED:
        return
    _BRANCH_UNION_CACHE_LOADED = True
    try:
        payload = json.loads(_BRANCH_UNION_CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(payload, dict) or payload.get("version") != _BRANCH_UNION_CACHE_VERSION:
        return
    entries = payload.get("entries")
    if not isinstance(entries, dict):
        return

    for cache_key, raw_activity in list(entries.items())[-_BRANCH_UNION_CACHE_MAX:]:
        if not isinstance(cache_key, str) or not isinstance(raw_activity, dict):
            continue
        activity: dict[str, BranchCommitActivity] = {}
        for commit_hash, raw_item in raw_activity.items():
            if not isinstance(commit_hash, str) or not isinstance(raw_item, dict):
                continue
            try:
                day = dt.date.fromisoformat(str(raw_item.get("day", "")))
                additions = int(raw_item.get("additions", 0))
                deletions = int(raw_item.get("deletions", 0))
            except (TypeError, ValueError):
                continue
            raw_languages = raw_item.get("languages", {})
            languages: dict[str, int] = {}
            if isinstance(raw_languages, dict):
                languages = {
                    str(language): int(value)
                    for language, value in raw_languages.items()
                    if isinstance(value, int)
                }
            activity[commit_hash] = BranchCommitActivity(
                day,
                additions,
                deletions,
                languages,
                str(raw_item.get("author_name", "")),
                str(raw_item.get("author_email", "")),
            )
        _BRANCH_UNION_CACHE[cache_key] = activity


def _save_branch_union_cache() -> None:
    global _BRANCH_UNION_CACHE_DIRTY
    if not _BRANCH_UNION_CACHE_DIRTY:
        return
    with _BRANCH_UNION_CACHE_LOCK:
        entries = {
            cache_key: {
                commit_hash: {
                    "day": item.day.isoformat(),
                    "additions": item.additions,
                    "deletions": item.deletions,
                    "languages": item.languages,
                    "author_name": item.author_name,
                    "author_email": item.author_email,
                }
                for commit_hash, item in activity.items()
            }
            for cache_key, activity in _BRANCH_UNION_CACHE.items()
        }
    try:
        _BRANCH_UNION_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _BRANCH_UNION_CACHE_PATH.write_text(
            json.dumps(
                {"version": _BRANCH_UNION_CACHE_VERSION, "entries": entries},
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
    except OSError:
        return
    _BRANCH_UNION_CACHE_DIRTY = False


atexit.register(_save_branch_union_cache)


def get_branch_union_activity(
    repo: Path,
    author: str,
    branch_refs: tuple[str, ...],
    exclude_ref: str | None = None,
    start_day: dt.date | None = None,
    end_day: dt.date | None = None,
) -> dict[str, BranchCommitActivity]:
    global _BRANCH_UNION_CACHE_DIRTY
    if not branch_refs:
        return {}
    branch_hashes = tuple((branch, get_ref_hash(repo, branch)) for branch in branch_refs)
    exclude_hash = get_ref_hash(repo, exclude_ref) if exclude_ref else ""
    cache_key = json.dumps(
        (
            str(repo.resolve()).casefold(),
            author,
            branch_hashes,
            exclude_ref or "",
            exclude_hash,
            start_day.isoformat() if start_day else "",
            end_day.isoformat() if end_day else "",
        ),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    _load_branch_union_cache()
    with _BRANCH_UNION_CACHE_LOCK:
        cached = _BRANCH_UNION_CACHE.get(cache_key)
    if cached is not None:
        return dict(cached)

    patterns = decode_author_patterns(author)
    args = [
        "log",
        "--date=short",
        "--format=@@COMMIT@@%H%x09%ad%x09%an%x09%ae",
        "--numstat",
        "--no-renames",
    ]
    if start_day is not None:
        args.append(f"--since={start_day.isoformat()} 00:00:00")
    if end_day is not None:
        args.append(f"--until={(end_day + dt.timedelta(days=1)).isoformat()} 00:00:00")
    if len(patterns) == 1:
        args.append(f"--author={patterns[0]}")
    elif patterns:
        args.extend(["--extended-regexp", f"--author=({'|'.join(patterns)})"])
    args.extend(branch_refs)
    if exclude_ref:
        args.extend(["--not", exclude_ref])

    commits: dict[str, BranchCommitActivity] = {}
    current_hash = ""
    current_date: dt.date | None = None
    current_author_name = ""
    current_author_email = ""
    additions = deletions = 0
    languages: dict[str, int] = {}
    for line in run_git(repo, args).splitlines():
        if line.startswith("@@COMMIT@@"):
            if current_hash and current_date is not None:
                commits[current_hash] = BranchCommitActivity(
                    current_date,
                    additions,
                    deletions,
                    languages,
                    current_author_name,
                    current_author_email,
                )
            fields = line.removeprefix("@@COMMIT@@").split("\t", 3)
            current_hash = fields[0].strip() if fields else ""
            try:
                current_date = dt.date.fromisoformat(fields[1].strip())
            except (IndexError, ValueError):
                current_date = None
            current_author_name = fields[2].strip() if len(fields) > 2 else ""
            current_author_email = fields[3].strip() if len(fields) > 3 else ""
            additions = deletions = 0
            languages = {}
            continue
        if current_hash:
            parts = line.split("\t", 2)
            if len(parts) != 3 or not parts[0].isdigit() or not parts[1].isdigit():
                continue
            path = parts[2].strip()
            if not path or is_probably_binary_path(path):
                continue
            added, removed = int(parts[0]), int(parts[1])
            additions += added
            deletions += removed
            language = classify_text_language(path)
            languages[language] = languages.get(language, 0) + added
    if current_hash and current_date is not None:
        commits[current_hash] = BranchCommitActivity(
            current_date,
            additions,
            deletions,
            languages,
            current_author_name,
            current_author_email,
        )
    filtered = {
        commit_hash: activity
        for commit_hash, activity in commits.items()
        if (start_day is None or activity.day >= start_day)
        and (end_day is None or activity.day <= end_day)
    }
    with _BRANCH_UNION_CACHE_LOCK:
        if len(_BRANCH_UNION_CACHE) >= _BRANCH_UNION_CACHE_MAX:
            _BRANCH_UNION_CACHE.pop(next(iter(_BRANCH_UNION_CACHE)))
        _BRANCH_UNION_CACHE[cache_key] = dict(filtered)
        _BRANCH_UNION_CACHE_DIRTY = True
    return filtered


def _filter_activity_by_author(
    activity: dict[str, BranchCommitActivity],
    author: str,
) -> dict[str, BranchCommitActivity]:
    patterns = decode_author_patterns(author)
    if not patterns:
        return dict(activity)
    return {
        commit_hash: item
        for commit_hash, item in activity.items()
        if _identity_matches_patterns(item.author_name, item.author_email, patterns)
    }


def _filter_activity_by_date(
    activity: dict[str, BranchCommitActivity],
    start_day: dt.date,
    end_day: dt.date,
) -> dict[str, BranchCommitActivity]:
    return {
        commit_hash: item
        for commit_hash, item in activity.items()
        if start_day <= item.day <= end_day
    }


def _identity_matches_patterns(name: str, email: str, patterns: list[str]) -> bool:
    identity = f"{name} <{email}>"
    for pattern in patterns:
        try:
            if re.search(pattern, identity):
                return True
        except re.error:
            if pattern in identity:
                return True
    return False


def _author_matches_current_identity(repo: Path, author: str) -> bool:
    patterns = decode_author_patterns(author)
    if not patterns:
        return True
    try:
        name = run_git(repo, ["config", "user.name"]).strip()
    except (OSError, RuntimeError):
        name = ""
    try:
        email = run_git(repo, ["config", "user.email"]).strip()
    except (OSError, RuntimeError):
        email = ""
    return bool(name or email) and _identity_matches_patterns(name, email, patterns)


def get_branch_union_stats(
    repo: Path, author: str, exclude_ref: str, branch_refs: tuple[str, ...]
) -> tuple[int, int, int, int]:
    commits = get_branch_union_activity(repo, author, branch_refs, exclude_ref)
    return (
        sum(item.additions for item in commits.values()),
        sum(item.deletions for item in commits.values()),
        len(commits),
        len({item.day for item in commits.values()}),
    )


def get_branch_union_commit_summary(
    repo: Path,
    author: str,
    branch_refs: tuple[str, ...],
) -> tuple[int, int]:
    commits: set[str] = set()
    active_days: set[dt.date] = set()
    for pattern in decode_author_patterns(author) or [""]:
        args = ["log", "--date=short", "--format=%H%x09%ad"]
        if pattern:
            args.append(f"--author={pattern}")
        args.extend(branch_refs)
        for line in run_git(repo, args).splitlines():
            commit_hash, separator, raw_day = line.partition("\t")
            if not separator or not commit_hash:
                continue
            try:
                day = dt.date.fromisoformat(raw_day.strip())
            except ValueError:
                continue
            commits.add(commit_hash)
            active_days.add(day)
    return len(commits), len(active_days)


def _compute_project_history_stats(
    repo: Path,
    base_ref: str,
    tracked_ref: str,
    current_ref: str,
    include_local: bool,
) -> ProjectHistoryStats:
    additions = _compute_all_committed_total(
        repo, base_ref, tracked_ref, current_ref, include_local
    )
    deletions = _compute_overall_committed_deletions(
        repo, base_ref, "", tracked_ref, current_ref, include_local
    )
    commits = _compute_overall_commit_count(repo, "", tracked_ref, current_ref, include_local)
    active_days = _compute_overall_active_days(repo, "", tracked_ref, current_ref, include_local)
    refs = [tracked_ref]
    if include_local and current_ref != tracked_ref:
        refs.append(current_ref)
    root_dates: list[dt.date] = []
    for line in run_git(
        repo,
        ["log", "--max-parents=0", "--date=short", "--format=%ad", *refs],
    ).splitlines():
        try:
            root_dates.append(dt.date.fromisoformat(line.strip()))
        except ValueError:
            continue
    return ProjectHistoryStats(
        additions=additions,
        deletions=deletions,
        commits=commits,
        active_days=active_days,
        birth_date=min(root_dates) if root_dates else None,
    )


def _compute_branch_total(repo: Path, author: str, tracked_ref: str, current_ref: str) -> int:
    if current_ref == tracked_ref:
        return 0
    return get_committed_insertions(repo, tracked_ref, author, current_ref)


def _compute_branch_deletions(repo: Path, author: str, tracked_ref: str, current_ref: str) -> int:
    if current_ref == tracked_ref:
        return 0
    return get_committed_deletions(repo, tracked_ref, author, current_ref)


def _compute_branch_commit_count(repo: Path, author: str, tracked_ref: str, current_ref: str) -> int:
    if current_ref == tracked_ref:
        return 0
    return get_commit_count(repo, author, current_ref, exclude_ref=tracked_ref)


def _compute_branch_active_days(repo: Path, author: str, tracked_ref: str, current_ref: str) -> int:
    if current_ref == tracked_ref:
        return 0
    return get_commit_active_day_count(repo, author, current_ref, exclude_ref=tracked_ref)


def _get_branch_activity_start(
    repo: Path,
    branch_ref: str,
    tracked_ref: str,
) -> dt.date | None:
    args = ["log", "--reverse", "--date=short", "--format=%ad", branch_ref]
    if not includes_tracked_branch(tracked_ref, (branch_ref,)):
        args.extend(["--not", tracked_ref])
    dates: list[dt.date] = []
    for value in run_git(repo, args).splitlines():
        try:
            dates.append(dt.date.fromisoformat(value.strip()))
        except ValueError:
            continue
    if dates:
        return min(dates)

    # Once a branch is merged, `branch --not tracked` becomes empty. The oldest
    # reflog state retains the branch point, allowing its first own commit to
    # remain stable after that merge.
    try:
        reflog_hashes = [
            value.strip()
            for value in run_git(repo, ["reflog", "show", "--format=%H", branch_ref]).splitlines()
            if value.strip()
        ]
    except RuntimeError:
        reflog_hashes = []
    if not reflog_hashes:
        return None

    creation_base = reflog_hashes[-1]
    fallback_dates: list[dt.date] = []
    for value in run_git(
        repo,
        ["log", "--reverse", "--date=short", "--format=%ad", branch_ref, "--not", creation_base],
    ).splitlines():
        try:
            fallback_dates.append(dt.date.fromisoformat(value.strip()))
        except ValueError:
            continue
    if fallback_dates:
        return min(fallback_dates)

    try:
        created_on = run_git(repo, ["show", "-s", "--date=short", "--format=%ad", creation_base]).strip()
        return dt.date.fromisoformat(created_on)
    except (RuntimeError, ValueError):
        return None


def _compute_overall_commit_count(
    repo: Path,
    author: str,
    tracked_ref: str,
    current_ref: str,
    include_local: bool,
) -> int:
    count = get_commit_count(repo, author, tracked_ref)
    if include_local and current_ref != tracked_ref:
        count += get_commit_count(repo, author, current_ref, exclude_ref=tracked_ref)
    return count


def _compute_overall_active_days(
    repo: Path,
    author: str,
    tracked_ref: str,
    current_ref: str,
    include_local: bool,
) -> int:
    if current_ref == tracked_ref:
        include_local = False
    return get_commit_active_day_count_combined(repo, author, tracked_ref, include_local)


def _compute_all_committed_total(
    repo: Path,
    base_commit: str,
    tracked_ref: str,
    current_ref: str,
    include_local: bool,
) -> int:
    all_base_total = get_total_insertions_up_to(repo, base_commit, "")
    all_committed = get_committed_insertions(repo, base_commit, "", tracked_ref)
    if include_local and current_ref != tracked_ref:
        all_committed += get_committed_insertions(repo, tracked_ref, "", current_ref)
    return all_base_total + all_committed


def _compute_overall_committed_deletions(
    repo: Path,
    base_commit: str,
    author: str,
    tracked_ref: str,
    current_ref: str,
    include_local: bool,
) -> int:
    base_deletions = get_total_deletions_up_to(repo, base_commit, author)
    committed_deletions = base_deletions + get_committed_deletions(repo, base_commit, author, tracked_ref)
    if include_local and current_ref != tracked_ref:
        committed_deletions += get_committed_deletions(repo, tracked_ref, author, current_ref)
    return committed_deletions


def _build_points_window(
    result: TrackerResult,
    values_by_date: dict[dt.date, int],
    start_day: dt.date,
    end_day: dt.date,
    today_extra: int = 0,
) -> list[tuple[dt.date, int]]:
    today_real = dt.date.today()
    points: list[tuple[dt.date, int]] = []
    day_count = (end_day - start_day).days + 1
    for i in range(day_count):
        day = start_day + dt.timedelta(days=i)
        value = values_by_date.get(day, 0)
        if today_extra and day == result.today and day == today_real:
            value += today_extra
        points.append((day, value))
    return points


def _summarize_points(points: list[tuple[dt.date, int]]) -> tuple[float, int]:
    values = [value for _, value in points]
    graph_max = max(values) if values else 0
    graph_avg = (sum(values) / len(values)) if values else 0.0
    return graph_avg, graph_max


def build_refresh_snapshot(
    repo: Path,
    author: str,
    config: TrackerConfig,
    graph_days: int,
    progress: RefreshProgress | None = None,
) -> RefreshSnapshot:
    _report_progress(progress, 5, "identity")
    author = resolve_author(repo, author)
    tracked_ref = resolve_ref(repo, config.ref)
    current_ref = resolve_current_ref(repo)
    available_branches = set(list_branch_refs(repo)) if config.selected_branches else set()
    selected_branches = tuple(
        branch for branch in dict.fromkeys(config.selected_branches)
        if branch in available_branches
    )
    current_selected = not selected_branches or current_ref in selected_branches or any(
        branch.endswith(f"/{current_ref}") for branch in selected_branches
    )
    tracked_selected = includes_tracked_branch(tracked_ref, selected_branches)
    include_uncommitted = (
        not config.assume_uncommitted_zero
        and current_selected
        and _author_matches_current_identity(repo, author)
    )
    resolved_config = replace(
        config,
        repo=repo,
        author=author,
        ref=tracked_ref,
        assume_uncommitted_zero=not include_uncommitted,
    )
    _report_progress(progress, 15, "monthly")
    if selected_branches:
        today = config.today or dt.date.today()
        month_end = resolve_month_end(today, config.month_end)
        days_left_including_today = max((month_end - today).days + 1, 0)
        result = TrackerResult(
            today=today,
            month_end=month_end,
            days_left_including_today=days_left_including_today,
            days_left_after_today=max(days_left_including_today - 1, 0),
            committed_total=0,
            uncommitted_insertions=(
                get_uncommitted_insertions(repo) if include_uncommitted else 0
            ),
            need_today=0,
            need_after_commit=0,
        )
    else:
        result = compute_metrics(resolved_config)
    base_ref = resolve_base_commit(repo, result.today, config.base_commit, tracked_ref)
    _report_progress(progress, 35, "branch")
    user_scope_total = 0
    if selected_branches:
        unique_exclude_ref = base_ref if tracked_selected else tracked_ref
        all_unique_activity = get_branch_union_activity(
            repo, "", selected_branches, unique_exclude_ref
        )
        unique_activity = _filter_activity_by_author(all_unique_activity, author)
        all_user_union_activity = (
            all_unique_activity
            if tracked_selected
            else get_branch_union_activity(repo, "", selected_branches, base_ref)
        )
        user_union_activity = _filter_activity_by_author(all_user_union_activity, author)
        branch_stats_list: list[BranchStats] = []
        for branch in selected_branches:
            exclude_ref = base_ref if includes_tracked_branch(tracked_ref, (branch,)) else tracked_ref
            branch_commits = set(run_git(repo, ["rev-list", branch, "--not", exclude_ref]).splitlines())
            activity = [item for commit_hash, item in unique_activity.items() if commit_hash in branch_commits]
            branch_stats_list.append(BranchStats(
                branch,
                sum(item.additions for item in activity),
                sum(item.deletions for item in activity),
                len(activity),
                len({item.day for item in activity}),
                _get_branch_activity_start(repo, branch, tracked_ref),
            ))
        branch_stats = tuple(branch_stats_list)
        branch_total = sum(item.additions for item in unique_activity.values())
        branch_deletions = sum(item.deletions for item in unique_activity.values())
        branch_commit_count = len(unique_activity)
        branch_active_days = len({item.day for item in unique_activity.values()})
        progress_branch_total = branch_total
        user_base_total = (
            config.base_total
            if config.base_total >= 0
            else get_total_insertions_up_to(repo, base_ref, author)
        )
        user_committed_total = user_base_total + sum(
            item.additions for item in user_union_activity.values()
        )
        overall_deletions = get_total_deletions_up_to(repo, base_ref, author) + sum(
            item.deletions for item in user_union_activity.values()
        )
        overall_commit_count, overall_active_days = get_branch_union_commit_summary(
            repo, author, selected_branches
        )
        all_author_base_total = (
            user_base_total if not author else get_total_insertions_up_to(repo, base_ref, "")
        )
        user_scope_total = all_author_base_total + sum(
            item.additions for item in all_user_union_activity.values()
        )
        result = replace(
            result,
            committed_total=user_committed_total,
            need_today=daily_needed(config.goal, user_committed_total, result.days_left_including_today),
            need_after_commit=daily_needed(
                config.goal,
                user_committed_total + result.uncommitted_insertions,
                result.days_left_after_today,
            ),
        )
    else:
        branch_total = _compute_branch_total(repo, author, tracked_ref, current_ref)
        progress_branch_total = branch_total
        branch_deletions = _compute_branch_deletions(repo, author, tracked_ref, current_ref)
        branch_active_days = _compute_branch_active_days(repo, author, tracked_ref, current_ref)
        branch_commit_count = _compute_branch_commit_count(repo, author, tracked_ref, current_ref)
        branch_stats = (
            BranchStats(
                current_ref,
                branch_total,
                branch_deletions,
                branch_commit_count,
                branch_active_days,
                _get_branch_activity_start(repo, current_ref, tracked_ref),
            ),
        )
        user_committed_total = result.committed_total
    uncommitted_deletions = get_uncommitted_deletions(repo) if include_uncommitted else 0
    _report_progress(progress, 50, "overall")
    if not selected_branches:
        overall_commit_count = _compute_overall_commit_count(
            repo, author, tracked_ref, current_ref, config.include_local
        )
    project_history = _compute_project_history_stats(
        repo,
        base_ref,
        tracked_ref,
        current_ref,
        config.include_local,
    )
    project_commit_count = project_history.commits
    project_active_days = project_history.active_days
    repository_birth_date = project_history.birth_date
    if not selected_branches:
        overall_active_days = _compute_overall_active_days(
            repo, author, tracked_ref, current_ref, config.include_local
        )
        overall_deletions = _compute_overall_committed_deletions(
            repo,
            base_ref,
            author,
            tracked_ref,
            current_ref,
            config.include_local,
        )
    _report_progress(progress, 65, "languages")
    project_language_lines = get_project_language_lines(repo)
    project_total_lines = sum(project_language_lines.values())
    uncommitted_language_lines = (
        get_uncommitted_insertions_by_language(repo) if include_uncommitted else {}
    )
    graph_uncommitted_insertions = result.uncommitted_insertions
    graph_uncommitted_deletions = uncommitted_deletions
    graph_uncommitted_languages = uncommitted_language_lines
    overall_progress_language_lines = dict(project_language_lines)
    _report_progress(progress, 80, "activity")
    graph_start_day = result.today - dt.timedelta(days=graph_days - 1)
    graph_available_start_day = result.today - dt.timedelta(days=GRAPH_AVAILABLE_DAYS - 1)
    grass_start_day, grass_end_day = get_grass_date_range(result.today)
    window_start_day = min(graph_available_start_day, grass_start_day)
    window_end_day = grass_end_day
    if selected_branches:
        selected_activity = (
            get_branch_union_activity(
                repo,
                author,
                selected_branches,
                None,
                window_start_day,
                window_end_day,
            )
            if tracked_selected
            else _filter_activity_by_author(
                _filter_activity_by_date(all_unique_activity, window_start_day, window_end_day),
                author,
            )
        )
        language_added_by_date: dict[dt.date, dict[str, int]] = {}
        deleted_by_date: dict[dt.date, int] = {}
        commit_counts_by_date: dict[dt.date, int] = {}
        for activity in selected_activity.values():
            day = activity.day
            language_added_by_date[day] = merge_language_totals(
                language_added_by_date.get(day, {}), activity.languages
            )
            deleted_by_date[day] = deleted_by_date.get(day, 0) + activity.deletions
            commit_counts_by_date[day] = commit_counts_by_date.get(day, 0) + 1
        daily_language_by_date = language_added_by_date
        daily_deleted_by_date = deleted_by_date
    else:
        language_added_by_date = get_committed_insertions_by_date_and_language_combined(
            repo, window_start_day, window_end_day, author, tracked_ref, config.include_local
        )
        deleted_by_date = get_committed_deletions_by_date_combined(
            repo, window_start_day, window_end_day, author, tracked_ref, config.include_local
        )
        commit_counts_by_date = get_commit_counts_by_date_combined(
            repo, window_start_day, window_end_day, author, tracked_ref, config.include_local
        )
        daily_language_by_date = language_added_by_date
        daily_deleted_by_date = deleted_by_date
    daily_commit_count = commit_counts_by_date.get(result.today, 0)
    added_by_date = {
        day: sum(language_totals.values())
        for day, language_totals in language_added_by_date.items()
    }
    daily_progress_language_lines = merge_language_totals(
        daily_language_by_date.get(result.today, {}),
        uncommitted_language_lines,
    )
    today_done = sum(daily_language_by_date.get(result.today, {}).values()) + result.uncommitted_insertions
    daily_removed = daily_deleted_by_date.get(result.today, 0) + uncommitted_deletions
    all_added_points = _build_points_window(
        result,
        added_by_date,
        window_start_day,
        window_end_day,
        today_extra=graph_uncommitted_insertions,
    )
    all_deleted_points = _build_points_window(
        result,
        deleted_by_date,
        window_start_day,
        window_end_day,
        today_extra=graph_uncommitted_deletions,
    )
    all_commit_points = _build_points_window(
        result,
        commit_counts_by_date,
        window_start_day,
        window_end_day,
    )
    graph_start_index = (graph_start_day - window_start_day).days
    graph_available_start_index = (graph_available_start_day - window_start_day).days
    graph_end_index = (result.today - window_start_day).days + 1
    grass_start_index = (grass_start_day - window_start_day).days
    grass_end_index = (grass_end_day - window_start_day).days + 1
    points = all_added_points[graph_start_index:graph_end_index]
    graph_deleted_points = all_deleted_points[graph_start_index:graph_end_index]
    graph_commit_points = all_commit_points[graph_start_index:graph_end_index]
    graph_available_added_points = all_added_points[graph_available_start_index:graph_end_index]
    graph_available_deleted_points = all_deleted_points[graph_available_start_index:graph_end_index]
    graph_available_commit_points = all_commit_points[graph_available_start_index:graph_end_index]
    graph_language_points: dict[str, list[tuple[dt.date, int]]] = {}
    graph_available_language_points: dict[str, list[tuple[dt.date, int]]] = {}
    for language in LANGUAGE_NAMES:
        language_values = {
            day: totals.get(language, 0)
            for day, totals in language_added_by_date.items()
        }
        language_all_points = _build_points_window(
            result,
            language_values,
            window_start_day,
            window_end_day,
            today_extra=graph_uncommitted_languages.get(language, 0),
        )
        graph_language_points[language] = language_all_points[graph_start_index:graph_end_index]
        graph_available_language_points[language] = language_all_points[
            graph_available_start_index:graph_end_index
        ]
    grass_points = all_added_points[grass_start_index:grass_end_index]
    graph_avg, graph_max = _summarize_points(points)
    user_uncommitted_insertions = result.uncommitted_insertions
    user_uncommitted_deletions = uncommitted_deletions
    user_cumulative_lines = user_committed_total + user_uncommitted_insertions
    user_cumulative_deletions = overall_deletions + user_uncommitted_deletions
    share_denominator = user_scope_total if selected_branches else project_history.additions
    share_percent = (
        (user_committed_total / share_denominator) * 100.0
        if share_denominator > 0
        else 0.0
    )
    history_refs = selected_branches or (current_ref or tracked_ref,)
    history_exclude_ref = (
        base_ref
        if not selected_branches or tracked_selected
        else tracked_ref
    )
    _report_progress(progress, 100, "complete")

    return RefreshSnapshot(
        author=author,
        tracked_ref=tracked_ref,
        current_ref=current_ref,
        base_ref=base_ref,
        result=result,
        today_done=today_done,
        today_target=result.need_today,
        points=points,
        graph_added_points=points,
        graph_deleted_points=graph_deleted_points,
        graph_commit_points=graph_commit_points,
        graph_language_points=graph_language_points,
        graph_available_added_points=graph_available_added_points,
        graph_available_deleted_points=graph_available_deleted_points,
        graph_available_commit_points=graph_available_commit_points,
        graph_available_language_points=graph_available_language_points,
        grass_points=grass_points,
        graph_days=graph_days,
        graph_avg=graph_avg,
        graph_max=graph_max,
        branch_total=branch_total,
        branch_deletions=branch_deletions,
        branch_active_days=branch_active_days,
        daily_commit_count=daily_commit_count,
        branch_commit_count=branch_commit_count,
        overall_commit_count=overall_commit_count,
        project_commit_count=project_commit_count,
        project_active_days=project_active_days,
        repository_birth_date=repository_birth_date,
        overall_active_days=overall_active_days,
        overall_deletions=overall_deletions,
        project_total_lines=project_total_lines,
        project_cumulative_lines=project_history.additions,
        project_cumulative_deletions=project_history.deletions,
        project_language_lines=project_language_lines,
        overall_progress_language_lines=overall_progress_language_lines,
        daily_progress_language_lines=daily_progress_language_lines,
        share_text=f"{share_percent:.1f}%",
        user_cumulative_lines=user_cumulative_lines,
        user_cumulative_deletions=user_cumulative_deletions,
        uncommitted_deletions=uncommitted_deletions,
        selected_branches=selected_branches or (current_ref,),
        progress_branch_total=progress_branch_total,
        daily_removed=daily_removed,
        graph_uncommitted_insertions=graph_uncommitted_insertions,
        branch_stats=branch_stats,
        history_refs=history_refs,
        history_exclude_ref=history_exclude_ref,
    )


def _report_progress(progress: RefreshProgress | None, value: int, stage: str) -> None:
    if progress is not None:
        progress(value, stage)
