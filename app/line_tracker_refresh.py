from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

from line_tracker import (
    TrackerConfig,
    TrackerResult,
    compute_metrics,
    get_committed_insertions,
    get_committed_insertions_by_date_combined,
    get_committed_insertions_for_date_combined,
    get_total_insertions_up_to,
    get_uncommitted_deletions,
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
    grass_points: list[tuple[dt.date, int]]
    graph_days: int
    graph_avg: float
    graph_max: int
    branch_total: int
    share_text: str
    uncommitted_deletions: int


def get_grass_date_range(day: dt.date) -> tuple[dt.date, dt.date]:
    return dt.date(day.year, 1, 1), dt.date(day.year, 12, 31)


def _compute_branch_total(repo: Path, author: str, tracked_ref: str, current_ref: str) -> int:
    if current_ref == tracked_ref:
        return 0
    return get_committed_insertions(repo, tracked_ref, author, current_ref)


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


def _build_points_window(
    repo: Path,
    author: str,
    result: TrackerResult,
    config: TrackerConfig,
    tracked_ref: str,
    start_day: dt.date,
    end_day: dt.date,
) -> list[tuple[dt.date, int]]:
    committed_by_date = get_committed_insertions_by_date_combined(
        repo,
        start_day,
        end_day,
        author,
        tracked_ref,
        config.include_local,
    )
    today_real = dt.date.today()
    points: list[tuple[dt.date, int]] = []
    day_count = (end_day - start_day).days + 1
    for i in range(day_count):
        day = start_day + dt.timedelta(days=i)
        value = committed_by_date.get(day, 0)
        if day == result.today and day == today_real:
            value += result.uncommitted_insertions
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
    all_committed_total = _compute_all_committed_total(repo, result, config, tracked_ref, current_ref)
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
    all_points = _build_points_window(
        repo,
        author,
        result,
        config,
        tracked_ref,
        window_start_day,
        window_end_day,
    )
    graph_start_index = (graph_start_day - window_start_day).days
    graph_end_index = (result.today - window_start_day).days + 1
    grass_start_index = (grass_start_day - window_start_day).days
    grass_end_index = (grass_end_day - window_start_day).days + 1
    points = all_points[graph_start_index:graph_end_index]
    grass_points = all_points[grass_start_index:grass_end_index]
    graph_avg, graph_max = _summarize_points(points)
    share_percent = (result.committed_total / all_committed_total) * 100.0 if all_committed_total > 0 else 0.0

    return RefreshSnapshot(
        result=result,
        today_done=today_done,
        today_target=result.need_today,
        points=points,
        grass_points=grass_points,
        graph_days=graph_days,
        graph_avg=graph_avg,
        graph_max=graph_max,
        branch_total=branch_total,
        share_text=f"{share_percent:.1f}%",
        uncommitted_deletions=get_uncommitted_deletions(repo),
    )
