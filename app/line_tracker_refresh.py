from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

from line_tracker import (
    TrackerConfig,
    TrackerResult,
    compute_metrics,
    get_commit_active_day_count,
    get_commit_active_day_count_combined,
    get_commit_count,
    get_commit_counts_by_date_combined,
    get_committed_insertions_by_language_combined,
    get_committed_deletions,
    get_committed_deletions_by_date_combined,
    get_committed_insertions,
    get_committed_insertions_by_date_combined,
    get_committed_insertions_for_date_combined,
    get_project_language_lines,
    get_total_deletions_up_to,
    get_total_insertions_up_to,
    get_uncommitted_deletions,
    get_uncommitted_insertions_by_language,
    merge_language_totals,
    resolve_base_commit,
    resolve_current_ref,
    resolve_ref,
)


@dataclass(frozen=True)
class RefreshSnapshot:
    result: TrackerResult
    today_done: int
    today_target: int
    points: list[tuple[dt.date, int]]
    graph_added_points: list[tuple[dt.date, int]]
    graph_deleted_points: list[tuple[dt.date, int]]
    graph_commit_points: list[tuple[dt.date, int]]
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
    overall_active_days: int
    overall_deletions: int
    project_total_lines: int
    project_language_lines: dict[str, int]
    overall_progress_language_lines: dict[str, int]
    daily_progress_language_lines: dict[str, int]
    share_text: str
    uncommitted_deletions: int


def get_grass_date_range(day: dt.date) -> tuple[dt.date, dt.date]:
    return dt.date(day.year, 1, 1), dt.date(day.year, 12, 31)


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
    result: TrackerResult,
    config: TrackerConfig,
    tracked_ref: str,
    current_ref: str,
) -> int:
    base_commit = resolve_base_commit(repo, result.today, config.base_commit, tracked_ref)
    all_base_total = get_total_insertions_up_to(repo, base_commit, "")
    all_committed = get_committed_insertions(repo, base_commit, "", tracked_ref)
    if config.include_local and current_ref != tracked_ref:
        all_committed += get_committed_insertions(repo, tracked_ref, "", current_ref)
    return all_base_total + all_committed


def _compute_overall_committed_deletions(
    repo: Path,
    result: TrackerResult,
    config: TrackerConfig,
    author: str,
    tracked_ref: str,
    current_ref: str,
) -> int:
    base_commit = resolve_base_commit(repo, result.today, config.base_commit, tracked_ref)
    base_deletions = get_total_deletions_up_to(repo, base_commit, author)
    committed_deletions = base_deletions + get_committed_deletions(repo, base_commit, author, tracked_ref)
    if config.include_local and current_ref != tracked_ref:
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


def build_refresh_snapshot(repo: Path, author: str, config: TrackerConfig, graph_days: int) -> RefreshSnapshot:
    result = compute_metrics(config)
    tracked_ref = resolve_ref(repo, config.ref)
    current_ref = resolve_current_ref(repo)
    branch_total = _compute_branch_total(repo, author, tracked_ref, current_ref)
    branch_deletions = _compute_branch_deletions(repo, author, tracked_ref, current_ref)
    branch_active_days = _compute_branch_active_days(repo, author, tracked_ref, current_ref)
    uncommitted_deletions = get_uncommitted_deletions(repo)
    daily_commit_count = _compute_daily_commit_count(repo, author, result.today, tracked_ref, current_ref, config.include_local)
    branch_commit_count = _compute_branch_commit_count(repo, author, tracked_ref, current_ref)
    overall_commit_count = _compute_overall_commit_count(repo, author, tracked_ref, current_ref, config.include_local)
    overall_active_days = _compute_overall_active_days(repo, author, tracked_ref, current_ref, config.include_local)
    all_committed_total = _compute_all_committed_total(repo, result, config, tracked_ref, current_ref)
    overall_deletions = _compute_overall_committed_deletions(repo, result, config, author, tracked_ref, current_ref)
    project_language_lines = get_project_language_lines(repo)
    project_total_lines = sum(project_language_lines.values())
    next_day = result.today + dt.timedelta(days=1)
    daily_committed_language_lines = get_committed_insertions_by_language_combined(
        repo,
        author,
        tracked_ref,
        config.include_local,
        since=result.today,
        until=next_day,
    )
    uncommitted_language_lines = (
        {} if config.assume_uncommitted_zero else get_uncommitted_insertions_by_language(repo)
    )
    overall_progress_language_lines = dict(project_language_lines)
    daily_progress_language_lines = merge_language_totals(
        daily_committed_language_lines,
        uncommitted_language_lines,
    )
    committed_today = get_committed_insertions_for_date_combined(
        repo,
        result.today,
        author,
        tracked_ref,
        config.include_local,
    )
    today_done = committed_today + result.uncommitted_insertions
    graph_start_day = result.today - dt.timedelta(days=graph_days - 1)
    grass_start_day, grass_end_day = get_grass_date_range(result.today)
    window_start_day = min(graph_start_day, grass_start_day)
    window_end_day = grass_end_day
    added_by_date = get_committed_insertions_by_date_combined(
        repo,
        window_start_day,
        window_end_day,
        author,
        tracked_ref,
        config.include_local,
    )
    deleted_by_date = get_committed_deletions_by_date_combined(
        repo,
        window_start_day,
        window_end_day,
        author,
        tracked_ref,
        config.include_local,
    )
    commit_counts_by_date = get_commit_counts_by_date_combined(
        repo,
        window_start_day,
        window_end_day,
        author,
        tracked_ref,
        config.include_local,
    )
    all_added_points = _build_points_window(
        result,
        added_by_date,
        window_start_day,
        window_end_day,
        today_extra=result.uncommitted_insertions,
    )
    all_deleted_points = _build_points_window(
        result,
        deleted_by_date,
        window_start_day,
        window_end_day,
        today_extra=uncommitted_deletions,
    )
    all_commit_points = _build_points_window(
        result,
        commit_counts_by_date,
        window_start_day,
        window_end_day,
    )
    graph_start_index = (graph_start_day - window_start_day).days
    graph_end_index = (result.today - window_start_day).days + 1
    grass_start_index = (grass_start_day - window_start_day).days
    grass_end_index = (grass_end_day - window_start_day).days + 1
    points = all_added_points[graph_start_index:graph_end_index]
    graph_deleted_points = all_deleted_points[graph_start_index:graph_end_index]
    graph_commit_points = all_commit_points[graph_start_index:graph_end_index]
    grass_points = all_added_points[grass_start_index:grass_end_index]
    graph_avg, graph_max = _summarize_points(points)
    share_percent = (result.committed_total / all_committed_total) * 100.0 if all_committed_total > 0 else 0.0

    return RefreshSnapshot(
        result=result,
        today_done=today_done,
        today_target=result.need_today,
        points=points,
        graph_added_points=points,
        graph_deleted_points=graph_deleted_points,
        graph_commit_points=graph_commit_points,
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
        overall_active_days=overall_active_days,
        overall_deletions=overall_deletions,
        project_total_lines=project_total_lines,
        project_language_lines=project_language_lines,
        overall_progress_language_lines=overall_progress_language_lines,
        daily_progress_language_lines=daily_progress_language_lines,
        share_text=f"{share_percent:.1f}%",
        uncommitted_deletions=uncommitted_deletions,
    )
