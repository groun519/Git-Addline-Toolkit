from __future__ import annotations

import datetime as dt
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from line_tracker import (
    LANGUAGE_NAMES,
    TrackerConfig,
    TrackerResult,
    classify_text_language,
    compute_metrics,
    decode_author_patterns,
    get_commit_active_day_count,
    get_commit_active_day_count_combined,
    get_commit_count,
    get_commit_counts_by_date_combined,
    get_committed_deletions,
    get_committed_deletions_by_date_combined,
    get_committed_insertions,
    get_committed_insertions_by_date_and_language_combined,
    get_committed_insertions_for_date_combined,
    get_project_language_lines,
    get_total_deletions_up_to,
    get_total_insertions_up_to,
    get_uncommitted_deletions,
    get_uncommitted_insertions_by_language,
    is_probably_binary_path,
    list_branch_refs,
    merge_language_totals,
    resolve_author,
    resolve_base_commit,
    resolve_current_ref,
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
    uncommitted_deletions: int
    selected_branches: tuple[str, ...] = ()
    progress_branch_total: int = 0
    daily_removed: int = 0
    graph_uncommitted_insertions: int = 0
    branch_stats: tuple[BranchStats, ...] = ()


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


def get_branch_union_activity(
    repo: Path,
    author: str,
    branch_refs: tuple[str, ...],
    exclude_ref: str | None = None,
    start_day: dt.date | None = None,
    end_day: dt.date | None = None,
) -> dict[str, BranchCommitActivity]:
    if not branch_refs:
        return {}
    commits: dict[str, BranchCommitActivity] = {}
    for pattern in decode_author_patterns(author) or [""]:
        args = [
            "log", "--date=short", "--format=@@COMMIT@@%H%x09%ad", "--numstat", "--no-renames",
        ]
        if start_day is not None:
            args.append(f"--since={start_day.isoformat()} 00:00:00")
        if end_day is not None:
            args.append(f"--until={(end_day + dt.timedelta(days=1)).isoformat()} 00:00:00")
        if pattern:
            args.append(f"--author={pattern}")
        args.extend(branch_refs)
        if exclude_ref:
            args.extend(["--not", exclude_ref])
        current_hash = ""
        current_date: dt.date | None = None
        additions = deletions = 0
        languages: dict[str, int] = {}
        for line in run_git(repo, args).splitlines():
            match = re.fullmatch(r"@@COMMIT@@([0-9a-f]{40,64})\t(\d{4}-\d{2}-\d{2})", line)
            if match:
                if current_hash and current_date is not None:
                    commits[current_hash] = BranchCommitActivity(current_date, additions, deletions, languages)
                current_hash = match.group(1)
                current_date = dt.date.fromisoformat(match.group(2))
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
            commits[current_hash] = BranchCommitActivity(current_date, additions, deletions, languages)
    return {
        commit_hash: activity
        for commit_hash, activity in commits.items()
        if (start_day is None or activity.day >= start_day)
        and (end_day is None or activity.day <= end_day)
    }


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


def _compute_daily_commit_count(
    repo: Path,
    author: str,
    day: dt.date,
    tracked_ref: str,
    current_ref: str,
    include_local: bool,
) -> int:
    next_day = day + dt.timedelta(days=1)
    count = get_commit_count(repo, author, tracked_ref, since=day, until=next_day)
    if include_local and current_ref != tracked_ref:
        count += get_commit_count(repo, author, current_ref, exclude_ref=tracked_ref, since=day, until=next_day)
    return count


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
    return min(dates) if dates else None


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
    resolved_config = replace(config, repo=repo, author=author, ref=tracked_ref)
    _report_progress(progress, 15, "monthly")
    result = compute_metrics(resolved_config)
    current_ref = resolve_current_ref(repo)
    base_ref = resolve_base_commit(repo, result.today, config.base_commit, tracked_ref)
    _report_progress(progress, 35, "branch")
    available_branches = set(list_branch_refs(repo)) if config.selected_branches else set()
    selected_branches = tuple(
        branch for branch in dict.fromkeys(config.selected_branches)
        if branch in available_branches
    )
    current_selected = not selected_branches or current_ref in selected_branches or any(
        branch.endswith(f"/{current_ref}") for branch in selected_branches
    )
    tracked_selected = includes_tracked_branch(tracked_ref, selected_branches)
    if selected_branches:
        unique_activity = get_branch_union_activity(
            repo, author, selected_branches, base_ref if tracked_selected else tracked_ref
        )
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
        progress_branch_total = _compute_branch_total(repo, author, tracked_ref, current_ref)
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
    uncommitted_deletions = get_uncommitted_deletions(repo)
    daily_commit_count = _compute_daily_commit_count(repo, author, result.today, tracked_ref, current_ref, config.include_local)
    _report_progress(progress, 50, "overall")
    overall_commit_count = _compute_overall_commit_count(repo, author, tracked_ref, current_ref, config.include_local)
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
    overall_active_days = _compute_overall_active_days(repo, author, tracked_ref, current_ref, config.include_local)
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
        {} if config.assume_uncommitted_zero else get_uncommitted_insertions_by_language(repo)
    )
    graph_uncommitted_insertions = result.uncommitted_insertions if current_selected else 0
    graph_uncommitted_deletions = uncommitted_deletions if current_selected else 0
    graph_uncommitted_languages = uncommitted_language_lines if current_selected else {}
    overall_progress_language_lines = dict(project_language_lines)
    committed_today = get_committed_insertions_for_date_combined(
        repo,
        result.today,
        author,
        tracked_ref,
        config.include_local,
    )
    _report_progress(progress, 80, "activity")
    today_done = committed_today + result.uncommitted_insertions
    graph_start_day = result.today - dt.timedelta(days=graph_days - 1)
    graph_available_start_day = result.today - dt.timedelta(days=GRAPH_AVAILABLE_DAYS - 1)
    grass_start_day, grass_end_day = get_grass_date_range(result.today)
    window_start_day = min(graph_available_start_day, grass_start_day)
    window_end_day = grass_end_day
    if selected_branches:
        selected_activity = get_branch_union_activity(
            repo,
            author,
            selected_branches,
            None if tracked_selected else tracked_ref,
            window_start_day,
            window_end_day,
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
        daily_language_by_date = get_committed_insertions_by_date_and_language_combined(
            repo, result.today, result.today, author, tracked_ref, config.include_local
        )
        daily_deleted_by_date = get_committed_deletions_by_date_combined(
            repo, result.today, result.today, author, tracked_ref, config.include_local
        )
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
    added_by_date = {
        day: sum(language_totals.values())
        for day, language_totals in language_added_by_date.items()
    }
    daily_progress_language_lines = merge_language_totals(
        daily_language_by_date.get(result.today, {}),
        uncommitted_language_lines,
    )
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
    share_percent = (
        (result.committed_total / project_history.additions) * 100.0
        if project_history.additions > 0
        else 0.0
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
        uncommitted_deletions=uncommitted_deletions,
        selected_branches=selected_branches or (current_ref,),
        progress_branch_total=progress_branch_total,
        daily_removed=daily_removed,
        graph_uncommitted_insertions=graph_uncommitted_insertions,
        branch_stats=branch_stats,
    )


def _report_progress(progress: RefreshProgress | None, value: int, stage: str) -> None:
    if progress is not None:
        progress(value, stage)
