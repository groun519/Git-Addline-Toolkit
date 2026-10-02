from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from line_tracker import LANGUAGE_NAMES
from line_tracker_io import write_text_atomic
from line_tracker_theme import DEFAULT_THEME_NAME, resolve_theme_name


SETTINGS_FILE_NAME = "line_tracker_ui_settings.json"
GRAPH_CURVE_DEFAULT = 35.0
COMPACT_WINDOW_ALPHA = 0.88
COMPACT_WINDOW_ALPHA_MIN = 0.45
COMPACT_WINDOW_ALPHA_MAX = 1.0
GRAPH_RENDER_SETTING_FIELDS = frozenset(
    {
        "graph_days",
        "graph_show_additions",
        "graph_show_deletions",
        "graph_show_commits",
        "graph_languages",
        "graph_curve",
    }
)


@dataclass(frozen=True)
class UISettings:
    repo_path: str = ""
    lang: str = "ko"
    theme: str = DEFAULT_THEME_NAME
    geometry: str = ""
    geometry_revision: int = 0
    goal: object = None
    graph_days: str = "14"
    graph_show_additions: object = True
    graph_show_deletions: object = False
    graph_show_commits: object = False
    graph_languages: tuple[str, ...] = ("C++",)
    graph_curve: object = GRAPH_CURVE_DEFAULT
    author: str = ""
    author_display: str = ""
    custom_today_enabled: object = None
    custom_today: str = ""
    auto_refresh: object = False
    compact_variant: str = "card"
    compact_alpha: float = COMPACT_WINDOW_ALPHA
    note_tab: str = "schedule"
    schedule_path: str = ""
    selected_branches: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> UISettings:
        compact_alpha = _coerce_float(data.get("compact_alpha"), COMPACT_WINDOW_ALPHA)
        if compact_alpha > 1.0:
            compact_alpha /= 100.0
        compact_alpha = min(max(compact_alpha, COMPACT_WINDOW_ALPHA_MIN), COMPACT_WINDOW_ALPHA_MAX)

        graph_curve = _coerce_float(data.get("graph_curve"), GRAPH_CURVE_DEFAULT)
        graph_curve = min(max(graph_curve, 0.0), 100.0)

        note_tab = str(data.get("note_tab", "schedule")).strip()
        if note_tab == "todo" or note_tab not in {"schedule", "grass"}:
            note_tab = "schedule"

        return cls(
            repo_path=str(data.get("repo_path", "")).strip(),
            lang=str(data.get("lang", "ko")).strip() or "ko",
            theme=resolve_theme_name(str(data.get("theme", DEFAULT_THEME_NAME)).strip()),
            geometry=str(data.get("geometry", "")).strip(),
            geometry_revision=_coerce_nonnegative_int(data.get("geometry_revision")),
            goal=data.get("goal"),
            graph_days=str(data.get("graph_days", "14")),
            graph_show_additions=data.get("graph_show_additions", True),
            graph_show_deletions=data.get("graph_show_deletions", False),
            graph_show_commits=data.get("graph_show_commits", False),
            graph_languages=_coerce_graph_languages(data.get("graph_languages")),
            graph_curve=graph_curve,
            author=str(data.get("author", "")).strip(),
            author_display=str(data.get("author_display", "")).strip(),
            custom_today_enabled=data.get("custom_today_enabled"),
            custom_today=str(data.get("custom_today", "")).strip(),
            auto_refresh=data.get("auto_refresh", False),
            compact_variant="strip" if str(data.get("compact_variant", "card")).strip() == "strip" else "card",
            compact_alpha=compact_alpha,
            note_tab=note_tab,
            schedule_path=str(data.get("schedule_path", "")).strip(),
            selected_branches=_coerce_selected_branches(data.get("selected_branches")),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "goal": self.goal,
            "custom_today_enabled": self.custom_today_enabled,
            "custom_today": self.custom_today,
            "graph_days": self.graph_days,
            "graph_show_additions": self.graph_show_additions,
            "graph_show_deletions": self.graph_show_deletions,
            "graph_show_commits": self.graph_show_commits,
            "graph_languages": list(self.graph_languages),
            "graph_curve": round(float(self.graph_curve), 1),
            "auto_refresh": self.auto_refresh,
            "author": self.author,
            "author_display": self.author_display,
            "compact_variant": self.compact_variant,
            "compact_alpha": round(self.compact_alpha, 2),
            "note_tab": self.note_tab,
            "schedule_path": self.schedule_path,
            "selected_branches": list(self.selected_branches),
            "repo_path": self.repo_path,
            "lang": self.lang,
            "theme": self.theme,
            "geometry": self.geometry,
            "geometry_revision": self.geometry_revision,
        }


def classify_settings_change(previous: UISettings, current: UISettings) -> str:
    changed_fields = {
        field_name
        for field_name in previous.__dataclass_fields__
        if getattr(previous, field_name) != getattr(current, field_name)
    }
    if not changed_fields:
        return "none"
    if changed_fields <= GRAPH_RENDER_SETTING_FIELDS:
        return "graph_render"
    return "application"


def load_ui_settings(settings_path: Path, legacy_settings_path: Path) -> UISettings:
    for candidate in (settings_path, legacy_settings_path):
        if not candidate.exists():
            continue
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            return UISettings.from_dict(data)
    return UISettings()


def save_ui_settings(settings_path: Path, settings: UISettings) -> bool:
    try:
        payload = json.dumps(settings.to_dict(), ensure_ascii=False, indent=2)
        write_text_atomic(settings_path, payload)
    except OSError:
        return False
    return True


def _coerce_float(value: object, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_nonnegative_int(value: object) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _coerce_graph_languages(value: object) -> tuple[str, ...]:
    if value is None:
        return ("C++",)
    if isinstance(value, str):
        selected = {value}
    elif isinstance(value, (list, tuple, set)):
        selected = {str(language) for language in value}
    else:
        return ("C++",)
    return tuple(language for language in LANGUAGE_NAMES if language in selected)


def _coerce_selected_branches(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(dict.fromkeys(branch.strip() for branch in value if isinstance(branch, str) and branch.strip()))
