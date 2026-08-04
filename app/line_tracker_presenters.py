from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from line_tracker_refresh import RefreshSnapshot


Translator = Callable[..., str]


@dataclass(frozen=True)
class ProgressPresentation:
    overall_percent: float
    daily_percent: float
    overall_bar_text: str
    daily_bar_text: str
    breakdown_text: str


@dataclass(frozen=True)
class StatCardPresentation:
    label: str
    value: str


@dataclass(frozen=True)
class StatSectionPresentation:
    title: str
    added: str = ""
    removed: str = ""
    commits: str = ""
    cards: tuple[StatCardPresentation, ...] = ()


@dataclass(frozen=True)
class DashboardPresentation:
    date_text: str
    daily: StatSectionPresentation
    branch: StatSectionPresentation
    overall: StatSectionPresentation
    user: StatSectionPresentation


def build_progress_presentation(
    *,
    main_committed: int,
    branch_committed: int,
    uncommitted: int,
    goal: int,
    today_done: int,
    today_target: int,
    translate: Translator,
) -> ProgressPresentation:
    current_total = main_committed + branch_committed + uncommitted
    overall_percent = _bounded_percent(current_total, goal, zero_target_complete=False)
    overall_percent_text = format_progress_percent(
        overall_percent,
        complete=goal > 0 and current_total >= goal,
    )
    breakdown = translate(
        "progress_breakdown",
        main=f"{main_committed:,}",
        branch=f"{branch_committed:,}",
        uncommitted=f"{uncommitted:,}",
    )

    daily_percent = _bounded_percent(today_done, today_target, zero_target_complete=True)
    if today_target <= 0:
        daily_bar_text = (
            f"{today_done:,}{translate('lines_suffix')} \u00b7 "
            f"{translate('progress_goal_reached')}"
        )
    else:
        daily_percent_text = format_progress_percent(
            daily_percent,
            complete=today_done >= today_target,
        )
        daily_bar_text = f"{today_done:,} / {today_target:,} [{daily_percent_text}%]"

    return ProgressPresentation(
        overall_percent=overall_percent,
        daily_percent=daily_percent,
        overall_bar_text=f"{current_total:,} / {goal:,} [{overall_percent_text}%]",
        daily_bar_text=daily_bar_text,
        breakdown_text=breakdown,
    )


def format_progress_percent(percent: float, *, complete: bool) -> str:
    if complete:
        return "100"
    rounded = min(round(max(0.0, min(100.0, percent)), 1), 99.9)
    return f"{rounded:.1f}".rstrip("0").rstrip(".")


def build_dashboard_presentation(
    snapshot: RefreshSnapshot,
    *,
    translate: Translator,
) -> DashboardPresentation:
    result = snapshot.result
    lines_suffix = translate("lines_suffix")
    day_suffix = translate("day_suffix")
    per_day_suffix = translate("per_day_suffix")
    user_total = result.committed_total + result.uncommitted_insertions

    return DashboardPresentation(
        date_text=result.today.isoformat(),
        daily=StatSectionPresentation(
            title=translate("daily_stats_section"),
            added=f"+{result.uncommitted_insertions:,}",
            removed=f"-{snapshot.uncommitted_deletions:,}",
            commits=f"{snapshot.daily_commit_count:,} commit",
            cards=(
                StatCardPresentation(
                    translate("daily_required_label"),
                    f"{result.need_today}{per_day_suffix}",
                ),
                StatCardPresentation(
                    translate("after_commit_daily_label"),
                    f"{result.need_after_commit}{per_day_suffix}",
                ),
            ),
        ),
        branch=StatSectionPresentation(
            title=translate("branch_stats_section"),
            added=f"+{snapshot.branch_total:,}",
            removed=f"-{snapshot.branch_deletions:,}",
            commits=f"{snapshot.branch_commit_count:,} commit",
            cards=(
                StatCardPresentation(
                    translate("branch_only_label"),
                    f"{snapshot.branch_total:,}{lines_suffix}",
                ),
                StatCardPresentation(
                    translate("branch_active_days_label"),
                    f"{snapshot.branch_active_days:,}{day_suffix}",
                ),
            ),
        ),
        overall=StatSectionPresentation(
            title=translate("overall_stats_section"),
            added=f"+{user_total:,}",
            removed=f"-{snapshot.overall_deletions + snapshot.uncommitted_deletions:,}",
            commits=f"{snapshot.overall_commit_count:,} commit",
            cards=(
                StatCardPresentation(
                    translate("project_total_label"),
                    f"{snapshot.project_total_lines:,}{lines_suffix}",
                ),
                StatCardPresentation(translate("share_label"), snapshot.share_text),
            ),
        ),
        user=StatSectionPresentation(
            title=translate("user_stats_section"),
            cards=(
                StatCardPresentation(translate("user_total_label"), f"{user_total:,}{lines_suffix}"),
                StatCardPresentation(
                    translate("user_active_days_label"),
                    f"{snapshot.overall_active_days:,}{day_suffix}",
                ),
            ),
        ),
    )


def _bounded_percent(current: int, target: int, *, zero_target_complete: bool) -> float:
    if target <= 0:
        return 100.0 if zero_target_complete else 0.0
    return max(0.0, min(100.0, (current / target) * 100.0))
