from __future__ import annotations

import re
import sys
from pathlib import Path

VERSION_PATTERN = re.compile(r"^V\d+\.\d+\.\d{3}$")
DEFAULT_APP_VERSION = "V0.1.002"
APP_NAME = "Line Tracker"


def get_version_file_path() -> Path:
    if getattr(sys, "frozen", False):
        bundle_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
        return bundle_root / "VERSION"
    return Path(__file__).resolve().parents[1] / "VERSION"


def load_app_version(version_file: Path | None = None) -> str:
    target = version_file or get_version_file_path()
    try:
        version = target.read_text(encoding="utf-8").strip()
    except OSError:
        return DEFAULT_APP_VERSION
    return version if VERSION_PATTERN.fullmatch(version) else DEFAULT_APP_VERSION


APP_VERSION = load_app_version()


def format_app_title(base_title: str = APP_NAME) -> str:
    return f"{base_title} {APP_VERSION}"
