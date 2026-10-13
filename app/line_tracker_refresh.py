from __future__ import annotations

import atexit
import datetime as dt
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from line_tracker_activity_index import CommitActivity, CommitActivityIndex
from line_tracker import (
    LANGUAGE_NAMES,
    TrackerConfig,
    TrackerResult,
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
    get_total_deletions_up_to,
    get_total_insertions_up_to,
    get_uncommitted_deletions,
    get_uncommitted_insertions,
    get_uncommitted_insertions_by_language,
    get_uncommitted_stats,
    list_branch_refs,
    merge_language_totals,
    resolve_author,
    resolve_base_commit,
    resolve_current_ref,
    resolve_month_end,
    resolve_ref,
    run_git,
    save_runtime_indexes,
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


BranchCommitActivity = CommitActivity
_ACTIVITY_INDEX = CommitActivityIndex(
    get_app_state_path("line_tracker_branch_union_cache.json")
)


@dataclass(frozen=True)
class ProjectHistoryStats:
    additions: int
    deletions: int
    commits: int
    active_days: int
    birth_date: dt.date | None
    activity: dict[str, BranchCommitActivity] | None = None


@dataclass(frozen=True)
class SelectedBranchMetrics:
    all_activity: dict[str, BranchCommitActivity]
    full_activity: dict[str, BranchCommitActivity]
    branch_stats: tuple[BranchStats, ...]
    branch_total: int
    branch_deletions: int
    branch_commit_count: int
    branch_active_days: int
    user_committed_total: int
    user_deletions: int
    user_commit_count: int
    user_active_days: int
    user_scope_total: int
    result: TrackerResult


@dataclass(frozen=True)
class ActivityMaps:
    languages_by_date: dict[dt.date, dict[str, int]]
    deletions_by_date: dict[dt.date, int]
    commits_by_date: dict[dt.date, int]


def includes_tracked_branch(tracked_ref: str, branch_refs: tuple[str, ...]) -> bool:
    local_name = tracked_ref.split("/", 1)[-1]
    return tracked_ref in branch_refs or local_name in branch_refs


atexit.register(_ACTIVITY_INDEX.save)


def get_branch_union_activity(
    repo: Path,
    author: str,
    branch_refs: tuple[str, ...],
    exclude_ref: str | None = None,
    start_day: dt.date | None = None,
    end_day: dt.date | None = None,
) -> dict[str, BranchCommitActivity]:
    activity = _ACTIVITY_INDEX.activity_for_refs(
        repo,
        branch_refs,
        exclude_ref=exclude_ref,
        run_git=run_git,
    )
    activity = _filter_activity_by_author(activity, author)
    return {
        commit_hash: item
        for commit_hash, item in activity.items()
        if (start_day is None or item.day >= start_day)
        and (end_day is None or item.day <= end_day)
    }


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
    activity = get_branch_union_activity(repo, author, branch_refs)
    return len(activity), len({item.day for item in activity.values()})


def _compute_project_history_stats(
    repo: Path,
    base_ref: str,
    tracked_ref: str,
    current_ref: str,
    include_local: bool,
) -> ProjectHistoryStats:
    refs = [tracked_ref]
    if include_local and current_ref != tracked_ref:
        refs.append(current_ref)
    activity = _ACTIVITY_INDEX.activity_for_refs(
        repo,
        tuple(refs),
        exclude_ref=None,
        run_git=run_git,
    )
    days = {item.day for item in activity.values()}
    return ProjectHistoryStats(
        additions=sum(item.additions for item in activity.values()),
        deletions=sum(item.deletions for item in activity.values()),
        commits=len(activity),
        active_days=len(days),
        birth_date=min(days) if days else None,
        activity=activity,
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


def _build_selected_branch_metrics(
    repo: Path,
    author: str,
    config: TrackerConfig,
    tracked_ref: str,
    base_ref: str,
    selected_branches: tuple[str, ...],
    tracked_selected: bool,
    result: TrackerResult,
) -> SelectedBranchMetrics:
    full_activity = get_branch_union_activity(repo, "", selected_branches)
    base_activity = get_branch_union_activity(repo, "", (base_ref,))
    unique_exclude_ref = base_ref if tracked_selected else tracked_ref
    all_activity = get_branch_union_activity(repo, "", selected_branches, unique_exclude_ref)
    user_activity = _filter_activity_by_author(all_activity, author)
    all_cumulative_activity = (
        all_activity
        if tracked_selected
        else get_branch_union_activity(repo, "", selected_branches, base_ref)
    )
    user_cumulative_activity = _filter_activity_by_author(all_cumulative_activity, author)

    branch_stats: list[BranchStats] = []
    for branch in selected_branches:
        exclude_ref = base_ref if includes_tracked_branch(tracked_ref, (branch,)) else tracked_ref
        branch_commits = set(run_git(repo, ["rev-list", branch, "--not", exclude_ref]).splitlines())
        activity = [
            item
            for commit_hash, item in user_activity.items()
            if commit_hash in branch_commits
        ]
        branch_stats.append(
            BranchStats(
                branch,
                sum(item.additions for item in activity),
                sum(item.deletions for item in activity),
                len(activity),
                len({item.day for item in activity}),
                _get_branch_activity_start(repo, branch, tracked_ref),
            )
        )

    branch_total = sum(item.additions for item in user_activity.values())
    branch_deletions = sum(item.deletions for item in user_activity.values())
    user_base_total = (
        config.base_total
        if config.base_total >= 0
        else sum(
            item.additions
            for item in _filter_activity_by_author(base_activity, author).values()
        )
    )
    user_committed_total = user_base_total + sum(
        item.additions for item in user_cumulative_activity.values()
    )
    user_deletions = sum(
        item.deletions
        for item in _filter_activity_by_author(base_activity, author).values()
    ) + sum(item.deletions for item in user_cumulative_activity.values())
    full_user_activity = _filter_activity_by_author(full_activity, author)
    user_commit_count = len(full_user_activity)
    user_active_days = len({item.day for item in full_user_activity.values()})
    all_author_base_total = (
        user_base_total
        if not author
        else sum(item.additions for item in base_activity.values())
    )
    user_scope_total = all_author_base_total + sum(
        item.additions for item in all_cumulative_activity.values()
    )
    updated_result = replace(
        result,
        committed_total=user_committed_total,
        need_today=daily_needed(
            config.goal,
            user_committed_total,
            result.days_left_including_today,
        ),
        need_after_commit=daily_needed(
            config.goal,
            user_committed_total + result.uncommitted_insertions,
            result.days_left_after_today,
        ),
    )
    return SelectedBranchMetrics(
        all_activity=all_activity,
        full_activity=full_activity,
        branch_stats=tuple(branch_stats),
        branch_total=branch_total,
        branch_deletions=branch_deletions,
        branch_commit_count=len(user_activity),
        branch_active_days=len({item.day for item in user_activity.values()}),
        user_committed_total=user_committed_total,
        user_deletions=user_deletions,
        user_commit_count=user_commit_count,
        user_active_days=user_active_days,
        user_scope_total=user_scope_total,
        result=updated_result,
    )


def _build_activity_maps(
    repo: Path,
    author: str,
    selected_branches: tuple[str, ...],
    tracked_selected: bool,
    all_selected_activity: dict[str, BranchCommitActivity],
    window_start_day: dt.date,
    window_end_day: dt.date,
    tracked_ref: str,
    include_local: bool,
    shared_activity: dict[str, BranchCommitActivity] | None = None,
) -> ActivityMaps:
    if shared_activity is not None:
        selected_activity = _filter_activity_by_author(
            _filter_activity_by_date(
                shared_activity,
                window_start_day,
                window_end_day,
            ),
            author,
        )
        languages_by_date: dict[dt.date, dict[str, int]] = {}
        deletions_by_date: dict[dt.date, int] = {}
        commits_by_date: dict[dt.date, int] = {}
        for activity in selected_activity.values():
            day = activity.day
            languages_by_date[day] = merge_language_totals(
                languages_by_date.get(day, {}),
                activity.languages,
            )
            deletions_by_date[day] = deletions_by_date.get(day, 0) + activity.deletions
            commits_by_date[day] = commits_by_date.get(day, 0) + 1
        return ActivityMaps(languages_by_date, deletions_by_date, commits_by_date)

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
                _filter_activity_by_date(
                    all_selected_activity,
                    window_start_day,
                    window_end_day,
                ),
                author,
            )
        )
        languages_by_date: dict[dt.date, dict[str, int]] = {}
        deletions_by_date: dict[dt.date, int] = {}
        commits_by_date: dict[dt.date, int] = {}
        for activity in selected_activity.values():
            day = activity.day
            languages_by_date[day] = merge_language_totals(
                languages_by_date.get(day, {}),
                activity.languages,
            )
            deletions_by_date[day] = deletions_by_date.get(day, 0) + activity.deletions
            commits_by_date[day] = commits_by_date.get(day, 0) + 1
        return ActivityMaps(languages_by_date, deletions_by_date, commits_by_date)

    return ActivityMaps(
        get_committed_insertions_by_date_and_language_combined(
            repo,
            window_start_day,
            window_end_day,
            author,
            tracked_ref,
            include_local,
        ),
        get_committed_deletions_by_date_combined(
            repo,
            window_start_day,
            window_end_day,
            author,
            tracked_ref,
            include_local,
        ),
        get_commit_counts_by_date_combined(
            repo,
            window_start_day,
            window_end_day,
            author,
            tracked_ref,
            include_local,
        ),
    )


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
    uncommitted_stats = (
        get_uncommitted_stats(repo)
        if selected_branches and include_uncommitted
        else None
    )
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
                uncommitted_stats.additions if uncommitted_stats is not None else 0
            ),
            need_today=0,
            need_after_commit=0,
        )
    else:
        result = compute_metrics(resolved_config)
    base_ref = resolve_base_commit(repo, result.today, config.base_commit, tracked_ref)
    _report_progress(progress, 35, "branch")
    user_scope_total = 0
    all_unique_activity: dict[str, BranchCommitActivity] = {}
    graph_activity: dict[str, BranchCommitActivity] | None = None
    if selected_branches:
        selected_metrics = _build_selected_branch_metrics(
            repo,
            author,
            config,
            tracked_ref,
            base_ref,
            selected_branches,
            tracked_selected,
            result,
        )
        all_unique_activity = selected_metrics.all_activity
        graph_activity = (
            selected_metrics.full_activity if tracked_selected else all_unique_activity
        )
        branch_stats = selected_metrics.branch_stats
        branch_total = selected_metrics.branch_total
        branch_deletions = selected_metrics.branch_deletions
        branch_commit_count = selected_metrics.branch_commit_count
        branch_active_days = selected_metrics.branch_active_days
        progress_branch_total = branch_total
        user_committed_total = selected_metrics.user_committed_total
        overall_deletions = selected_metrics.user_deletions
        overall_commit_count = selected_metrics.user_commit_count
        overall_active_days = selected_metrics.user_active_days
        user_scope_total = selected_metrics.user_scope_total
        result = selected_metrics.result
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
    uncommitted_deletions = (
        uncommitted_stats.deletions
        if uncommitted_stats is not None
        else get_uncommitted_deletions(repo) if include_uncommitted else 0
    )
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
    if graph_activity is None:
        graph_activity = project_history.activity
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
        uncommitted_stats.languages
        if uncommitted_stats is not None
        else get_uncommitted_insertions_by_language(repo) if include_uncommitted else {}
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
    activity_maps = _build_activity_maps(
        repo,
        author,
        selected_branches,
        tracked_selected,
        all_unique_activity,
        window_start_day,
        window_end_day,
        tracked_ref,
        config.include_local,
        graph_activity,
    )
    language_added_by_date = activity_maps.languages_by_date
    deleted_by_date = activity_maps.deletions_by_date
    commit_counts_by_date = activity_maps.commits_by_date
    daily_commit_count = commit_counts_by_date.get(result.today, 0)
    added_by_date = {
        day: sum(language_totals.values())
        for day, language_totals in language_added_by_date.items()
    }
    daily_progress_language_lines = merge_language_totals(
        language_added_by_date.get(result.today, {}),
        uncommitted_language_lines,
    )
    today_done = sum(language_added_by_date.get(result.today, {}).values()) + result.uncommitted_insertions
    daily_removed = deleted_by_date.get(result.today, 0) + uncommitted_deletions
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

    snapshot = RefreshSnapshot(
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
    _ACTIVITY_INDEX.save()
    save_runtime_indexes()
    return snapshot


def _report_progress(progress: RefreshProgress | None, value: int, stage: str) -> None:
    if progress is not None:
        progress(value, stage)
