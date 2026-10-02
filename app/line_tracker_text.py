from __future__ import annotations

import datetime as dt
from pathlib import Path


BINARY_EXTENSIONS = frozenset(
    {
        ".uasset", ".umap", ".png", ".jpg", ".jpeg", ".bmp", ".tga", ".gif",
        ".dds", ".wav", ".mp3", ".ogg", ".mp4", ".mov", ".avi", ".zip",
        ".7z", ".rar", ".bin", ".exe", ".dll", ".so", ".dylib", ".pdb",
        ".lib", ".a",
    }
)
LANGUAGE_EXTENSION_GROUPS: tuple[tuple[str, frozenset[str]], ...] = (
    ("C++", frozenset({".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx", ".inl"})),
    ("C#", frozenset({".cs"})),
    ("Python", frozenset({".py", ".pyw"})),
    ("TypeScript", frozenset({".ts", ".tsx"})),
    ("JavaScript", frozenset({".js", ".jsx", ".mjs", ".cjs"})),
    ("JSON", frozenset({".json", ".jsonc", ".uplugin", ".uproject"})),
    ("Shader", frozenset({".usf", ".ush", ".hlsl", ".glsl", ".vert", ".frag"})),
    ("Config", frozenset({".ini", ".cfg", ".conf", ".toml", ".yaml", ".yml"})),
    ("Scripts", frozenset({".ps1", ".bat", ".cmd", ".sh"})),
    ("Docs", frozenset({".md", ".mdx", ".rst", ".txt"})),
)
LANGUAGE_NAMES = tuple(language for language, _extensions in LANGUAGE_EXTENSION_GROUPS) + ("Other",)


def is_probably_binary_path(path_text: str) -> bool:
    return Path(path_text).suffix.lower() in BINARY_EXTENSIONS


def is_probably_binary_bytes(sample: bytes) -> bool:
    return b"\x00" in sample


def count_text_lines(path: Path) -> int:
    try:
        data = path.read_bytes()
    except OSError:
        return 0
    if not data or is_probably_binary_bytes(data[:8192]):
        return 0
    return data.count(b"\n") + (0 if data.endswith(b"\n") else 1)


def classify_text_language(path_text: str) -> str:
    suffix = Path(path_text).suffix.lower()
    for language, extensions in LANGUAGE_EXTENSION_GROUPS:
        if suffix in extensions:
            return language
    return "Other"


def order_language_totals(totals: dict[str, int]) -> dict[str, int]:
    ordered = {
        language: int(totals[language])
        for language, _extensions in LANGUAGE_EXTENSION_GROUPS
        if totals.get(language, 0) > 0
    }
    if totals.get("Other", 0) > 0:
        ordered["Other"] = int(totals["Other"])
    return ordered


def merge_language_totals(*language_totals: dict[str, int]) -> dict[str, int]:
    merged: dict[str, int] = {}
    for totals in language_totals:
        for language, value in totals.items():
            if value > 0:
                merged[language] = merged.get(language, 0) + int(value)
    return order_language_totals(merged)


def parse_numstat_insertions(text: str) -> int:
    return _parse_numstat_column(text, 0)


def parse_numstat_deletions(text: str) -> int:
    return _parse_numstat_column(text, 1)


def parse_numstat_insertions_by_language(text: str) -> dict[str, int]:
    totals: dict[str, int] = {}
    for line in text.splitlines():
        parts = line.split("\t", 2)
        if len(parts) < 3 or not parts[0].isdigit():
            continue
        path_text = parts[2].strip()
        if not path_text or is_probably_binary_path(path_text):
            continue
        language = classify_text_language(path_text)
        totals[language] = totals.get(language, 0) + int(parts[0])
    return order_language_totals(totals)


def parse_numstat_insertions_by_date_and_language(text: str) -> dict[dt.date, dict[str, int]]:
    daily: dict[dt.date, dict[str, int]] = {}
    current_day: dt.date | None = None
    for line in text.splitlines():
        if line.startswith("@@DATE@@"):
            try:
                current_day = dt.date.fromisoformat(line.removeprefix("@@DATE@@").strip())
            except ValueError:
                current_day = None
            if current_day is not None:
                daily.setdefault(current_day, {})
            continue
        if current_day is None:
            continue
        parts = line.split("\t", 2)
        if len(parts) < 3 or not parts[0].isdigit():
            continue
        path_text = parts[2].strip()
        if not path_text or is_probably_binary_path(path_text):
            continue
        language = classify_text_language(path_text)
        totals = daily.setdefault(current_day, {})
        totals[language] = totals.get(language, 0) + int(parts[0])
    return {day: order_language_totals(totals) for day, totals in daily.items()}


def _parse_numstat_column(text: str, column: int) -> int:
    total = 0
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3 and parts[column].isdigit():
            total += int(parts[column])
    return total
