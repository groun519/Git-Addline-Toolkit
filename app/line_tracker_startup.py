from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from line_tracker import CommitChangeEntry, TrackerConfig, get_commit_change_entries
from line_tracker_refresh import RefreshSnapshot, build_refresh_snapshot
from line_tracker_schedule import (
    DirectiveScheduleParser,
    ScheduleDocument,
    ScheduleParseError,
    load_schedule_document,
    resolve_schedule_path,
)
from line_tracker_settings import UISettings


STARTUP_HISTORY_LIMIT = 40
StartupProgress = Callable[[int, str], None]


@dataclass(frozen=True)
class StartupPayload:
    repo: Path
    settings: UISettings
    snapshot: RefreshSnapshot
    schedule_document: ScheduleDocument | None
    schedule_path: Path | None
    schedule_error: str
    history_entries: tuple[CommitChangeEntry, ...]
    history_exhausted: bool
    history_error: str


def build_startup_payload(
    repo: Path,
    settings: UISettings,
    config: TrackerConfig,
    graph_days: int,
    progress: StartupProgress | None = None,
) -> StartupPayload:
    _report(progress, 5, "repository")
    snapshot = build_refresh_snapshot(
        repo,
        config.author,
        config,
        graph_days,
        progress=lambda value, stage: _report(progress, 8 + int(value * 0.76), stage),
    )

    _report(progress, 88, "schedule")
    schedule_path = resolve_schedule_path(repo, settings.schedule_path)
    schedule_document: ScheduleDocument | None = None
    schedule_error = ""
    if schedule_path is not None:
        try:
            schedule_document = load_schedule_document(schedule_path, DirectiveScheduleParser())
        except (OSError, ScheduleParseError) as exc:
            schedule_error = str(exc)

    _report(progress, 94, "history")
    history_entries: tuple[CommitChangeEntry, ...] = ()
    history_error = ""
    history_refs = getattr(snapshot, "history_refs", ()) or (
        snapshot.current_ref or snapshot.tracked_ref,
    )
    history_exclude_ref = getattr(snapshot, "history_exclude_ref", "") or snapshot.base_ref
    try:
        history_entries = tuple(
            get_commit_change_entries(
                repo,
                snapshot.author,
                history_refs,
                exclude_ref=history_exclude_ref or None,
                limit=STARTUP_HISTORY_LIMIT,
            )
        )
    except (OSError, RuntimeError) as exc:
        history_error = str(exc)

    _report(progress, 100, "ready")
    return StartupPayload(
        repo=repo,
        settings=settings,
        snapshot=snapshot,
        schedule_document=schedule_document,
        schedule_path=schedule_path,
        schedule_error=schedule_error,
        history_entries=history_entries,
        history_exhausted=len(history_entries) < STARTUP_HISTORY_LIMIT,
        history_error=history_error,
    )


def _report(progress: StartupProgress | None, value: int, stage: str) -> None:
    if progress is not None:
        progress(min(max(value, 0), 100), stage)
