from __future__ import annotations

import datetime as dt
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
    scope: str = ""
    added: str = ""
    removed: str = ""
    commits: str = ""
    cards: tuple[StatCardPresentation, ...] = ()


@dataclass(frozen=True)
class DashboardPresentation:
    date_text: str
    branches: tuple[StatSectionPresentation, ...]
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
    user_title: str,
) -> DashboardPresentation:
    result = snapshot.result
    lines_suffix = translate("lines_suffix")
    day_suffix = translate("day_suffix")
    user_total = result.committed_total + result.uncommitted_insertions

    return DashboardPresentation(
        date_text=result.today.isoformat(),
        branches=tuple(
            StatSectionPresentation(
                title=stats.ref,
                added=f"+{stats.additions:,}",
                removed=f"-{stats.deletions:,}",
                commits=f"{stats.commits:,} commit",
                cards=(
                    StatCardPresentation(
                        translate("branch_selected_additions_label"),
                        f"{stats.additions:,}{lines_suffix}",
                    ),
                    StatCardPresentation(
                        translate("branch_active_days_label"),
                        f"{stats.active_days:,}{day_suffix}",
                    ),
                    StatCardPresentation(
                        translate("branch_activity_period_label"),
                        (
                            f"{max(0, (result.today - stats.started_on).days + 1):,}{day_suffix}"
                            if stats.started_on is not None
                            else translate("branch_activity_period_unknown")
                        ),
                    ),
                ),
            )
            for stats in snapshot.branch_stats
        ),
        overall=StatSectionPresentation(
            title=translate("overall_stats_section"),
            added=f"+{snapshot.project_cumulative_lines:,}",
            removed=f"-{snapshot.project_cumulative_deletions:,}",
            commits=f"{snapshot.project_commit_count:,} commit",
            cards=(
                StatCardPresentation(
                    translate("project_total_label"),
                    f"{snapshot.project_total_lines:,}{lines_suffix}",
                ),
                StatCardPresentation(
                    translate("project_cumulative_lines_label"),
                    f"{snapshot.project_cumulative_lines:,}{lines_suffix}",
                ),
                StatCardPresentation(
                    translate("project_active_days_label"),
                    f"{snapshot.project_active_days:,}{day_suffix}",
                ),
                StatCardPresentation(
                    translate("repository_birth_date_label"),
                    snapshot.repository_birth_date.isoformat()
                    if snapshot.repository_birth_date is not None
                    else translate("repository_age_unknown"),
                ),
                StatCardPresentation(
                    translate("repository_age_label"),
                    format_repository_age(
                        snapshot.repository_birth_date,
                        result.today,
                        translate=translate,
                    ),
                ),
            ),
        ),
        user=StatSectionPresentation(
            title=user_title,
            added=f"+{user_total:,}",
            removed=f"-{snapshot.overall_deletions + snapshot.uncommitted_deletions:,}",
            commits=f"{snapshot.overall_commit_count:,} commit",
            cards=(
                StatCardPresentation(translate("user_total_label"), f"{user_total:,}{lines_suffix}"),
                StatCardPresentation(
                    translate("user_active_days_label"),
                    f"{snapshot.overall_active_days:,}{day_suffix}",
                ),
                StatCardPresentation(translate("share_label"), snapshot.share_text),
            ),
        ),
    )


def format_repository_age(
    birth_date: dt.date | None,
    today: dt.date,
    *,
    translate: Translator,
) -> str:
    if birth_date is None:
        return translate("repository_age_unknown")
    if today < birth_date:
        today = birth_date
    total_months = (today.year - birth_date.year) * 12 + today.month - birth_date.month
    if today.day < birth_date.day:
        total_months -= 1
    total_months = max(total_months, 0)
    years, months = divmod(total_months, 12)
    if years and months:
        return translate("repository_age_years_months", years=years, months=months)
    if years:
        return translate("repository_age_years", years=years)
    if months:
        return translate("repository_age_months", months=months)
    return translate("repository_age_days", days=max((today - birth_date).days, 0))


def _bounded_percent(current: int, target: int, *, zero_target_complete: bool) -> float:
    if target <= 0:
        return 100.0 if zero_target_complete else 0.0
    return max(0.0, min(100.0, (current / target) * 100.0))
