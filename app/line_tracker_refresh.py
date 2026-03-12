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
)


@dataclass(frozen=True)
class RefreshSnapshot:
    result: TrackerResult
    today_done: int
    today_target: int
    points: list[tuple[dt.date, int]]
    graph_days: int
    graph_avg: float
    graph_max: int
    branch_total: int
    share_text: str
    uncommitted_deletions: int


def _compute_branch_total(repo: Path, author: str, tracked_ref: str, current_ref: str) -> int:
    if current_ref == tracked_ref:
        return 0
    return get_committed_insertions(repo, tracked_ref, author, current_ref)


def _compute_all_committed_total(repo: Path, result: TrackerResult, config: TrackerConfig, current_ref: str) -> int:
    base_commit = resolve_base_commit(repo, result.today, config.base_commit, config.ref)
    all_base_total = get_total_insertions_up_to(repo, base_commit, "")
    all_committed = get_committed_insertions(repo, base_commit, "", config.ref)
    if config.include_local and current_ref != config.ref:
        all_committed += get_committed_insertions(repo, config.ref, "", current_ref)
    return all_base_total + all_committed


def _build_graph_points(
    repo: Path,
    author: str,
    result: TrackerResult,
    config: TrackerConfig,
    graph_days: int,
) -> tuple[list[tuple[dt.date, int]], float, int]:
    end_day = result.today
    start_day = end_day - dt.timedelta(days=graph_days - 1)
    committed_by_date = get_committed_insertions_by_date_combined(
        repo,
        start_day,
        end_day,
        author,
        config.ref,
        config.include_local,
    )
    today_real = dt.date.today()
    points: list[tuple[dt.date, int]] = []
    for i in range(graph_days):
        day = start_day + dt.timedelta(days=i)
        value = committed_by_date.get(day, 0)
        if day == end_day and day == today_real:
            value += result.uncommitted_insertions
        points.append((day, value))

    values = [value for _, value in points]
    graph_max = max(values) if values else 0
    graph_avg = (sum(values) / len(values)) if values else 0.0
    return points, graph_avg, graph_max


def build_refresh_snapshot(repo: Path, author: str, config: TrackerConfig, graph_days: int) -> RefreshSnapshot:
    result = compute_metrics(config)
    current_ref = resolve_current_ref(repo)
    branch_total = _compute_branch_total(repo, author, config.ref, current_ref)
    all_committed_total = _compute_all_committed_total(repo, result, config, current_ref)
    committed_today = get_committed_insertions_for_date_combined(
        repo,
        result.today,
        author,
        config.ref,
        config.include_local,
    )
    today_done = committed_today + result.uncommitted_insertions
    points, graph_avg, graph_max = _build_graph_points(repo, author, result, config, graph_days)
    share_percent = (result.committed_total / all_committed_total) * 100.0 if all_committed_total > 0 else 0.0

    return RefreshSnapshot(
        result=result,
        today_done=today_done,
        today_target=result.need_today,
        points=points,
        graph_days=graph_days,
        graph_avg=graph_avg,
        graph_max=graph_max,
        branch_total=branch_total,
        share_text=f"{share_percent:.1f}%",
        uncommitted_deletions=get_uncommitted_deletions(repo),
    )
