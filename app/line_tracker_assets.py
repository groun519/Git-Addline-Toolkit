from __future__ import annotations

import sys
from pathlib import Path


def get_asset_path(name: str) -> Path | None:
    if getattr(sys, "frozen", False):
        bundle_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    else:
        bundle_root = Path(__file__).resolve().parents[1]
    candidate = bundle_root / "assets" / name
    return candidate if candidate.is_file() else None


def get_app_icon_path() -> Path | None:
    return get_asset_path("line_tracker.ico")
