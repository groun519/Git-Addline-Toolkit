from __future__ import annotations

import datetime as dt
import re

from line_tracker_settings import UISettings


def coerce_positive_int(value: object, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def coerce_graph_days(value: object) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 30
    return min(max(parsed, 1), 365)


def parse_saved_today(settings: UISettings, fallback: dt.date | None) -> dt.date | None:
    if not settings.custom_today_enabled:
        return fallback
    try:
        return dt.date.fromisoformat(settings.custom_today)
    except ValueError:
        return fallback


def parse_geometry(value: str) -> tuple[int, int, int | None, int | None] | None:
    match = re.fullmatch(r"(\d+)x(\d+)(?:\+(-?\d+)\+(-?\d+))?", value.strip())
    if match is None:
        return None
    width, height, x_pos, y_pos = match.groups()
    return int(width), int(height), int(x_pos) if x_pos else None, int(y_pos) if y_pos else None
