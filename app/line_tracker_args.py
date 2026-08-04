from __future__ import annotations

import argparse
import datetime as dt

from line_tracker import DEFAULT_AUTHOR, DEFAULT_BASE_COMMIT, DEFAULT_BASE_TOTAL, DEFAULT_GOAL


def parse_date(value: str) -> dt.date:
    return dt.date.fromisoformat(value)


def make_ui_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="UI launcher for monthly insertion-line tracker.")
    parser.add_argument("--repo", default=".", help="Git repository path.")
    parser.add_argument("--goal", type=int, default=DEFAULT_GOAL, help="Target total insertion lines.")
    parser.add_argument("--base-total", type=int, default=DEFAULT_BASE_TOTAL, help="Committed total at base commit.")
    parser.add_argument("--base-commit", default=DEFAULT_BASE_COMMIT, help="Base commit hash for line tracking.")
    parser.add_argument("--author", default=DEFAULT_AUTHOR, help="Author filter for committed insertions.")
    parser.add_argument("--ref", default="auto", help="Git ref/branch to track.")
    parser.add_argument("--today", type=parse_date, default=None, help="Override today's date (YYYY-MM-DD).")
    parser.add_argument("--month-end", type=parse_date, default=None, help="Month end date (YYYY-MM-DD).")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Print the 4-line output once and exit (for quick checks).",
    )
    return parser
