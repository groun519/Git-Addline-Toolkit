#!/usr/bin/env python3
from __future__ import annotations

import argparse
import calendar
import datetime as dt
import json
import math
import re
import sys
import threading
import tkinter as tk
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from line_tracker_memo import (
    MemoLabels,
    coerce_saved_memo_text,
    default_memo_text,
    get_placeholder_titles,
)
from line_tracker_memo_panel import MemoPanel, MemoPanelBindings
from line_tracker_grass_panel import GrassPanel, GrassPanelBindings
from line_tracker import (
    DEFAULT_AUTHOR,
    DEFAULT_BASE_COMMIT,
    DEFAULT_BASE_TOTAL,
    DEFAULT_GOAL,
    TrackerConfig,
    TrackerResult,
    compute_metrics,
    format_output_lines,
    get_app_state_path,
    get_legacy_state_path,
    clear_cache_for_repo,
    encode_author_patterns,
    find_repo_root,
    get_git_info,
    run_git,
    resolve_author,
    resolve_current_ref,
    resolve_ref,
)
from line_tracker_theme import (
    DEFAULT_THEME_NAME,
    ThemePalette,
    get_theme_names,
    get_theme_palette,
    resolve_theme_name,
)
from line_tracker_refresh import RefreshSnapshot, build_refresh_snapshot
from line_tracker_version import APP_VERSION, format_app_title

AUTO_REFRESH_MS = 60_000
GRAPH_CANVAS_WIDTH = 420
GRAPH_CANVAS_HEIGHT = 140
BAR_LENGTH = 420
GRAPH_CARD_WIDTH = GRAPH_CANVAS_WIDTH + 24
NOTE_CARD_WIDTH = 420
NOTE_CARD_FIT_PADDING = 8
COMPACT_WINDOW_MIN_WIDTH = 360
COMPACT_WINDOW_MIN_HEIGHT = 156
COMPACT_STRIP_MIN_WIDTH = 300
COMPACT_STRIP_MIN_HEIGHT = 42
COMPACT_WINDOW_MARGIN = 0
COMPACT_WINDOW_ALPHA = 0.88
COMPACT_WINDOW_ALPHA_MIN = 0.45
COMPACT_WINDOW_ALPHA_MAX = 1.0
COMPACT_LAUNCH_BUTTON_SIZE = 32
CARD_SCROLLBAR_STYLE = "Card.Vertical.TScrollbar"
FOOTER_LOADING_STYLE = "Loading.Horizontal.TProgressbar"
BASE_WINDOW_WIDTH = 1440
BASE_WINDOW_HEIGHT = 675
MIN_WINDOW_WIDTH = 1100
MIN_WINDOW_HEIGHT = 675
BASE_TILE_MIN_WIDTH = 250
BASE_TILE_LABEL_WRAP = 240
SETTINGS_FILE_NAME = "line_tracker_ui_settings.json"
WINDOW_SCREEN_MARGIN = 80
GEOMETRY_RE = re.compile(r"^(?P<width>\d+)x(?P<height>\d+)(?:(?P<x>[+-]\d+)(?P<y>[+-]\d+))?$")
AUTHOR_IDENTITY_RE = re.compile(r"^(?P<name>.+?)\s*<(?P<email>[^<>]+)>$")
AUTHOR_HANDLE_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$")
GITHUB_NOREPLY_DOMAIN = "users.noreply.github.com"

LANG_OPTIONS = {"한국어": "ko", "English": "en"}
LANG_DISPLAY = {"ko": "한국어", "en": "English"}
TEXT = {
    "ko": {
        "window_title": "Line Tracker",
        "lang_label": "언어",
        "theme_label": "테마",
        "theme_forest": "포레스트",
        "theme_cream": "크림",
        "theme_slate": "슬레이트",
        "theme_dark": "다크",
        "theme_vs": "VS",
        "theme_neon": "네온",
        "theme_cherry": "체리",
        "theme_discord": "디스코드",
        "theme_mc": "MC",
        "theme_cyberpunk": "사이버펑크",
        "repo_label": "리포 경로",
        "repo_select": "리포 선택",
        "graph_title": "일별 추가줄 그래프",
        "graph_period": "기간",
        "commit_memo": "커밋 메모",
        "tab_memo": "커밋 메모",
        "tab_grass": "Git 잔디",
        "memo_editor": "메모 원문",
        "memo_preview": "자동 분리 미리보기",
        "memo_hint": "첫 줄은 제목, 나머지는 DONE/TODO 항목으로 자동 분리됩니다.",
        "memo_template_title": "[제목 입력]",
        "memo_title": "제목",
        "memo_empty": "(비어 있음)",
        "done": "DONE",
        "todo": "TODO",
        "move_to_done": "DONE로 이동",
        "move_to_todo": "TODO로 이동",
        "copy_summary": "제목 복사",
        "copy_description": "설명 복사",
        "grass_hint": "칸 하나가 하루입니다. 진할수록 그날 추가한 줄 수가 많고, 테두리는 오늘입니다.",
        "grass_summary": "활동 {active}일 | 총 {total}줄 | 평균 {avg}줄/활동일",
        "grass_empty": "표시할 기록이 없습니다.",
        "grass_day_mon": "월",
        "grass_day_wed": "수",
        "grass_day_fri": "금",
        "grass_legend_zero": "0줄",
        "grass_legend_range": "{start}~{end}줄",
        "grass_legend_open": "{start}줄+",
        "grass_uncommitted_legend": "오늘",
        "settings": "설정",
        "custom_date": "커스텀 날짜 사용",
        "apply_date": "날짜 적용",
        "goal_label": "목표 줄수",
        "apply_goal": "목표 적용",
        "author_label": "유저 선택",
        "apply_author": "유저 적용",
        "author_auto": "자동(내 계정)",
        "author_all": "전체",
        "auto_refresh": "1분마다 자동 업데이트",
        "progress": "진행률",
        "overall_progress": "전체 진행률",
        "daily_progress": "일일 진행률",
        "current_changes": "현재 변경",
        "refresh": "새로고침",
        "copy": "복사",
        "compact_toggle": "축소",
        "compact_toggle_short": "축소",
        "compact_restore": "복원",
        "compact_title": "축소 모드",
        "compact_mode_to_strip": "최소화",
        "compact_mode_to_card": "카드",
        "compact_opacity": "투명도",
        "compact_opacity_value": "{value}",
        "compact_today_progress": "오늘 진행",
        "compact_progress_complete": "오늘 목표 달성",
        "compact_progress_value_text": "{percent}% ({done}/{target})",
        "compact_progress_inline_complete": "달성",
        "compact_progress_inline_text": "{percent}% · {done}/{target}",
        "compact_progress_remaining": "{remaining}줄 남음",
        "compact_progress_over": "목표 초과 +{extra}줄",
        "compact_delta": "추가줄",
        "compact_clock": "날짜 및 시간",
        "compact_datetime_text": "{date} | {time}",
        "compact_refresh_short": "새로고침",
        "compact_restore_short": "복원",
        "loading": "새로고침 중...",
        "loading_detail": "사용자 정보를 불러오는 중...",
        "status_updated": "업데이트: {time}",
        "status_auto_suffix": " (자동 1분 ON)",
        "status_clipboard": "클립보드에 복사됨",
        "status_summary_copied": "커밋 제목이 클립보드에 복사됨",
        "status_description_copied": "커밋 설명이 클립보드에 복사됨",
        "status_error": "오류 발생",
        "status_auto_off": "자동 업데이트 OFF",
        "status_repo_needed": "리포 경로를 선택한 뒤 새로고침하세요.",
        "error_date_format": "날짜 형식은 YYYY-MM-DD 로 입력하세요.",
        "error_goal": "목표 줄수는 1 이상의 정수로 입력하세요.",
        "error_repo_missing": "리포 경로가 존재하지 않습니다.",
        "error_repo_invalid": "유효한 Git 리포가 아닙니다.",
        "error_need_title": "제목을 입력하세요.",
        "repo_not_selected": "리포 미선택",
        "today_label": "오늘 날짜",
        "days_left_label": "남은 날짜({month})",
        "day_suffix": "일",
        "daily_required_label": "일일 필요 추가줄",
        "after_commit_prefix": "커밋 후",
        "after_commit_daily_label": "커밋 후 일일 필요 추가줄",
        "per_day_suffix": "줄/일",
        "current_uncommitted_label": "현재 추가줄(미커밋)",
        "lines_suffix": "줄",
        "branch_only_label": "현재 브랜치 단독 추가줄(커밋)",
        "share_label": "내 추가줄 비중(전체 대비)",
        "progress_breakdown": "메인 {main} + 브랜치 {branch} + 미커밋 {uncommitted}",
        "overall_progress_text": "전체 진행률(커밋+미커밋): {current}/{goal} ({percent}%)\n{breakdown}",
        "daily_progress_text": "일일 진행률: {done}/{target} ({percent}%)",
        "graph_summary": "최근 {days}일 평균 {avg}줄/일 | 최대 {max}줄",
        "repo_dialog_title": "리포 선택",
        "setup_title": "환경 점검",
        "git_missing": "Git을 찾을 수 없습니다.\nGit for Windows를 설치하거나, 설치본에 PortableGit을 함께 포함하세요.\n지금 다운로드 페이지를 여시겠습니까?",
    },
    "en": {
        "window_title": "Line Tracker",
        "lang_label": "Language",
        "theme_label": "Theme",
        "theme_forest": "Forest",
        "theme_cream": "Cream",
        "theme_slate": "Slate",
        "theme_dark": "Dark",
        "theme_vs": "VS",
        "theme_neon": "Neon",
        "theme_cherry": "Cherry",
        "theme_discord": "Discord",
        "theme_mc": "MC",
        "theme_cyberpunk": "Cyberpunk",
        "repo_label": "Repository",
        "repo_select": "Browse",
        "graph_title": "Daily Additions Graph",
        "graph_period": "Range",
        "commit_memo": "Commit Memo",
        "tab_memo": "Commit Memo",
        "tab_grass": "Git Grass",
        "memo_editor": "Memo Text",
        "memo_preview": "Parsed Preview",
        "memo_hint": "The first line becomes the title. Remaining lines are split into DONE/TODO items.",
        "memo_template_title": "[Enter title]",
        "memo_title": "Title",
        "memo_empty": "(Empty)",
        "done": "DONE",
        "todo": "TODO",
        "move_to_done": "Move to DONE",
        "move_to_todo": "Move to TODO",
        "copy_summary": "Copy Summary",
        "copy_description": "Copy Description",
        "grass_hint": "Each cell is a day. Darker cells mean more added lines, and the outline marks today.",
        "grass_summary": "{active} active days | {total} total lines | {avg} avg lines/active day",
        "grass_empty": "No history to display.",
        "grass_day_mon": "Mon",
        "grass_day_wed": "Wed",
        "grass_day_fri": "Fri",
        "grass_legend_zero": "0 lines",
        "grass_legend_range": "{start}-{end} lines",
        "grass_legend_open": "{start}+ lines",
        "grass_uncommitted_legend": "Today",
        "settings": "Settings",
        "custom_date": "Use Custom Date",
        "apply_date": "Apply Date",
        "goal_label": "Goal Lines",
        "apply_goal": "Apply Goal",
        "author_label": "User",
        "apply_author": "Apply User",
        "author_auto": "Auto (me)",
        "author_all": "All",
        "auto_refresh": "Auto refresh (1 min)",
        "progress": "Progress",
        "overall_progress": "Overall Progress",
        "daily_progress": "Daily Progress",
        "current_changes": "Current Changes",
        "refresh": "Refresh",
        "copy": "Copy",
        "compact_toggle": "Compact",
        "compact_toggle_short": "Compact",
        "compact_restore": "Restore",
        "compact_title": "Compact Mode",
        "compact_mode_to_strip": "Minimize",
        "compact_mode_to_card": "Card",
        "compact_opacity": "Opacity",
        "compact_opacity_value": "{value}",
        "compact_today_progress": "Today's Status",
        "compact_progress_complete": "Goal complete today",
        "compact_progress_value_text": "{percent}% ({done}/{target})",
        "compact_progress_inline_complete": "Done",
        "compact_progress_inline_text": "{percent}% · {done}/{target}",
        "compact_progress_remaining": "{remaining} lines left",
        "compact_progress_over": "Exceeded by +{extra} lines",
        "compact_delta": "Delta",
        "compact_clock": "Date & Time",
        "compact_datetime_text": "{date} | {time}",
        "compact_refresh_short": "Refresh",
        "compact_restore_short": "Restore",
        "loading": "Refreshing...",
        "loading_detail": "Loading user information...",
        "status_updated": "Updated: {time}",
        "status_auto_suffix": " (auto 1 min ON)",
        "status_clipboard": "Copied to clipboard",
        "status_summary_copied": "Commit summary copied to clipboard",
        "status_description_copied": "Commit description copied to clipboard",
        "status_error": "Error",
        "status_auto_off": "Auto refresh OFF",
        "status_repo_needed": "Choose a repository path, then refresh.",
        "error_date_format": "Date must be YYYY-MM-DD.",
        "error_goal": "Goal lines must be a positive integer.",
        "error_repo_missing": "Repository path does not exist.",
        "error_repo_invalid": "Not a valid Git repository.",
        "error_need_title": "Please enter a title.",
        "repo_not_selected": "No repository selected",
        "today_label": "Today",
        "days_left_label": "Days left ({month})",
        "day_suffix": " days",
        "daily_required_label": "Daily required additions",
        "after_commit_prefix": "After commit",
        "after_commit_daily_label": "Daily required (after commit)",
        "per_day_suffix": " lines/day",
        "current_uncommitted_label": "Current additions (uncommitted)",
        "lines_suffix": " lines",
        "branch_only_label": "Current branch additions (committed)",
        "share_label": "My additions share",
        "progress_breakdown": "Main {main} + Branch {branch} + Uncommitted {uncommitted}",
        "overall_progress_text": "Overall progress (committed+uncommitted): {current}/{goal} ({percent}%)\n{breakdown}",
        "daily_progress_text": "Daily progress: {done}/{target} ({percent}%)",
        "graph_summary": "Last {days} days avg {avg} lines/day | max {max} lines",
        "repo_dialog_title": "Select Repository",
        "setup_title": "Environment Check",
        "git_missing": "Git was not found.\nInstall Git for Windows or bundle PortableGit with the app.\nOpen the download page now?",
    },
}

FONT_TITLE = ("Bahnschrift", 18, "bold")
FONT_VERSION = ("Bahnschrift", 9)
FONT_SUBTITLE = ("Bahnschrift", 10)
FONT_BODY = ("Bahnschrift", 10)
FONT_SECTION = ("Bahnschrift", 11, "bold")
FONT_COMPACT_VALUE = ("Bahnschrift", 14, "bold")
FONT_COMPACT_TOOL = ("Bahnschrift", 9)
FONT_COMPACT_CLOCK = ("Bahnschrift", 11)
FONT_TILE_LABEL = ("Bahnschrift", 9)
FONT_TILE_VALUE = ("Bahnschrift", 12, "bold")
FONT_CHIP = ("Bahnschrift", 9)
FONT_COMPACT_META = ("Bahnschrift", 10)
FONT_COMPACT_BAR_VALUE = ("Bahnschrift", 9, "bold")
FONT_MONO = ("Cascadia Mono", 10)


def get_app_icon_path() -> Path | None:
    if getattr(sys, "frozen", False):
        bundle_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
        candidate = bundle_root / "assets" / "line_tracker.ico"
        if candidate.is_file():
            return candidate
    candidate = Path(__file__).resolve().parents[1] / "assets" / "line_tracker.ico"
    if candidate.is_file():
        return candidate
    return None


@dataclass(frozen=True)
class UISettings:
    repo_path: str = ""
    lang: str = "ko"
    theme: str = DEFAULT_THEME_NAME
    geometry: str = ""
    goal: object = None
    graph_days: str = "14"
    author: str = ""
    author_display: str = ""
    custom_today_enabled: object = None
    custom_today: str = ""
    auto_refresh: object = False
    memo_text: object = None
    compact_variant: str = "card"
    compact_alpha: float = COMPACT_WINDOW_ALPHA
    legacy_note_title: str = ""
    legacy_note_items: object = None
    legacy_note_done: str = ""
    legacy_note_todo: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> UISettings:
        compact_alpha_raw = data.get("compact_alpha", COMPACT_WINDOW_ALPHA)
        try:
            compact_alpha = float(compact_alpha_raw)
        except (TypeError, ValueError):
            compact_alpha = COMPACT_WINDOW_ALPHA
        if compact_alpha > 1.0:
            compact_alpha /= 100.0
        compact_alpha = min(max(compact_alpha, COMPACT_WINDOW_ALPHA_MIN), COMPACT_WINDOW_ALPHA_MAX)
        return cls(
            repo_path=str(data.get("repo_path", "")).strip(),
            lang=str(data.get("lang", "ko")).strip() or "ko",
            theme=resolve_theme_name(str(data.get("theme", DEFAULT_THEME_NAME)).strip()),
            geometry=str(data.get("geometry", "")).strip(),
            goal=data.get("goal"),
            graph_days=str(data.get("graph_days", "14")),
            author=str(data.get("author", "")).strip(),
            author_display=str(data.get("author_display", "")).strip(),
            custom_today_enabled=data.get("custom_today_enabled"),
            custom_today=str(data.get("custom_today", "")).strip(),
            auto_refresh=data.get("auto_refresh", False),
            memo_text=data.get("memo_text"),
            compact_variant="strip" if str(data.get("compact_variant", "card")).strip() == "strip" else "card",
            compact_alpha=compact_alpha,
            legacy_note_title=str(data.get("note_title", "")).strip(),
            legacy_note_items=data.get("note_items"),
            legacy_note_done=str(data.get("note_done", "")),
            legacy_note_todo=str(data.get("note_todo", "")),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "goal": self.goal,
            "custom_today_enabled": self.custom_today_enabled,
            "custom_today": self.custom_today,
            "graph_days": self.graph_days,
            "auto_refresh": self.auto_refresh,
            "author": self.author,
            "author_display": self.author_display,
            "memo_text": self.memo_text,
            "compact_variant": self.compact_variant,
            "compact_alpha": round(self.compact_alpha, 2),
            "repo_path": self.repo_path,
            "lang": self.lang,
            "theme": self.theme,
            "geometry": self.geometry,
        }


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    cleaned = value.strip().lstrip("#")
    if len(cleaned) != 6:
        raise ValueError(f"Expected #RRGGBB color, got {value!r}")
    return tuple(int(cleaned[index:index + 2], 16) for index in (0, 2, 4))


def blend_hex(base: str, overlay: str, ratio: float) -> str:
    mix_ratio = min(max(ratio, 0.0), 1.0)
    base_rgb = _hex_to_rgb(base)
    overlay_rgb = _hex_to_rgb(overlay)
    blended = tuple(
        round(base_channel + (overlay_channel - base_channel) * mix_ratio)
        for base_channel, overlay_channel in zip(base_rgb, overlay_rgb)
    )
    return "#" + "".join(f"{channel:02x}" for channel in blended)


def contrast_text_color(background: str) -> str:
    red, green, blue = _hex_to_rgb(background)
    luminance = ((red * 299) + (green * 587) + (blue * 114)) / 1000
    return "#10161c" if luminance >= 150 else "#f5f8fb"


def parse_date(value: str) -> dt.date:
    return dt.date.fromisoformat(value)

def make_parser() -> argparse.ArgumentParser:
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


class LineTrackerApp:
    @staticmethod
    def resolve_valid_repo(path: Path) -> Path | None:
        try:
            candidate = find_repo_root(path).resolve()
        except OSError:
            return None
        try:
            run_git(candidate, ["rev-parse", "--is-inside-work-tree"])
        except RuntimeError:
            return None
        return candidate

    def __init__(self, root: tk.Tk, args: argparse.Namespace) -> None:
        self.root = root
        self.settings_path = get_app_state_path(SETTINGS_FILE_NAME)
        self.legacy_settings_path = get_legacy_state_path(SETTINGS_FILE_NAME)
        self.settings = self.load_settings()
        saved_repo_path = self.settings.repo_path
        saved_lang = self.settings.lang
        self.lang = saved_lang if saved_lang in TEXT else "ko"
        self.theme_name = resolve_theme_name(self.settings.theme)
        self.theme: ThemePalette = get_theme_palette(self.theme_name)
        self.lang_var = tk.StringVar(value=LANG_DISPLAY[self.lang])
        self.theme_var = tk.StringVar(value=self.theme_display_label(self.theme_name))
        default_repo_seed = Path(args.repo).resolve()
        repo_candidate = self.resolve_valid_repo(Path(saved_repo_path)) if saved_repo_path else None
        if repo_candidate is None:
            repo_candidate = self.resolve_valid_repo(default_repo_seed)
        self.repo_selected = repo_candidate is not None
        self.repo = repo_candidate or default_repo_seed
        self.goal = args.goal
        self.base_total = args.base_total
        self.base_commit = args.base_commit
        self.author_raw = args.author
        self.author = resolve_author(self.repo, args.author)
        self.ref = resolve_ref(self.repo, args.ref)
        self.today = args.today
        self.month_end = args.month_end
        default_width = BASE_WINDOW_WIDTH
        default_height = BASE_WINDOW_HEIGHT
        min_height = MIN_WINDOW_HEIGHT
        initial_min_width = min(MIN_WINDOW_WIDTH, max(640, self.root.winfo_screenwidth() - WINDOW_SCREEN_MARGIN))
        default_geometry = f"{default_width}x{default_height}"
        saved_geometry = self.normalize_geometry(self.settings.geometry)
        self.last_window_geometry = saved_geometry or default_geometry
        self.root.geometry(self.last_window_geometry)
        self.root.minsize(initial_min_width, min_height)
        self.root.maxsize(default_width, self.root.winfo_screenheight())
        self.base_window_width = BASE_WINDOW_WIDTH
        self.min_height = min_height

        saved_goal = self._coerce_positive_int(self.settings.goal, self.goal)
        saved_graph_days = self.settings.graph_days
        if saved_graph_days not in {"7", "14", "21", "30", "60", "90", "180"}:
            saved_graph_days = "14"
        saved_author = self.settings.author or args.author
        saved_author_display = self.settings.author_display
        saved_custom_today_enabled = bool(self.settings.custom_today_enabled if self.settings.custom_today_enabled is not None else bool(args.today))
        default_today_text = args.today.isoformat() if args.today else dt.date.today().isoformat()
        saved_today_text = self.settings.custom_today or default_today_text
        saved_auto_refresh = bool(self.settings.auto_refresh)
        saved_memo_text = coerce_saved_memo_text(
            self.settings.memo_text,
            self.settings.legacy_note_title,
            self.settings.legacy_note_items,
            self.settings.legacy_note_done,
            self.settings.legacy_note_todo,
            self.memo_labels(),
        )
        self.goal = saved_goal
        self.author_options, self.author_filter_map, self.author_display_aliases = self.build_author_options()
        display_value = saved_author_display if saved_author_display in self.author_filter_map else ""
        if not display_value:
            display_value = self.map_author_to_display(saved_author or args.author)
        self.author_raw = self.author_filter_map.get(display_value, saved_author or args.author)
        self.author_display = display_value
        self.author = resolve_author(self.repo, self.author_raw)

        self.root.title(format_app_title())
        icon_path = get_app_icon_path()
        if icon_path is not None:
            try:
                self.root.iconbitmap(default=str(icon_path))
            except tk.TclError:
                pass
        self.root.resizable(False, False)
        self.root.configure(bg=self.theme.app_bg)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        self.root.bind("<Configure>", self.on_root_configure)

        self.style = ttk.Style(self.root)
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass
        self.apply_color_palette()

        container = ttk.Frame(self.root, padding=14, style="App.TFrame")
        container.grid(row=0, column=0, sticky="nsew")
        container.columnconfigure(0, weight=0)
        container.columnconfigure(1, weight=0)
        container.columnconfigure(2, weight=0)
        self.container = container

        self._initialize_runtime_state(args, saved_custom_today_enabled, saved_memo_text)
        self._build_header(container)
        self._build_output_section(container)
        self._build_progress_section(container)
        self._build_right_panel(
            container,
            saved_graph_days=saved_graph_days,
            saved_custom_today_enabled=saved_custom_today_enabled,
            saved_today_text=saved_today_text,
            saved_auto_refresh=saved_auto_refresh,
        )
        self._build_footer(container)
        self._build_compact_container()
        self.apply_color_palette()
        self._finish_startup(args, default_today_text)

    def _initialize_runtime_state(
        self,
        args: argparse.Namespace,
        saved_custom_today_enabled: bool,
        saved_memo_text: str,
    ) -> None:
        self.auto_refresh_job: str | None = None
        self.refresh_request_id = 0
        self.refresh_in_progress = False
        self.today_override: dt.date | None = args.today if saved_custom_today_enabled else None
        self.meta_label_vars = [tk.StringVar(value="") for _ in range(2)]
        self.meta_value_vars = [tk.StringVar(value="") for _ in range(2)]
        self.tile_label_vars = [tk.StringVar(value="") for _ in range(5)]
        self.tile_value_vars = [tk.StringVar(value="") for _ in range(5)]
        self.current_ref = resolve_current_ref(self.repo)
        self.main_total_committed = 0
        self.branch_total_committed = 0
        self.graph_points: list[tuple[dt.date, int]] = []
        self.graph_highlight_day: dt.date | None = None
        self.grass_panel_controller: GrassPanel | None = None
        self.active_note_tab = "memo"
        self.memo_text_value = saved_memo_text
        self.memo_panel_controller: MemoPanel | None = None
        self.repo_entry_var = tk.StringVar(value=str(self.repo) if self.repo_selected else "")
        self.compact_mode = False
        self.compact_clock_job: str | None = None
        self.compact_reposition_job: str | None = None
        self.compact_placing = False
        self.last_refresh_snapshot: RefreshSnapshot | None = None
        self.compact_reference_day: dt.date | None = None
        self.compact_progress_value = tk.DoubleVar(value=0.0)
        self.compact_progress_var = tk.StringVar(value="--")
        self.compact_strip_summary_var = tk.StringVar(value="--")
        self.compact_strip_progress_text = "--"
        self.compact_added_var = tk.StringVar(value="+0")
        self.compact_removed_var = tk.StringVar(value="-0")
        self.compact_datetime_var = tk.StringVar(value="")
        self.compact_status_var = tk.StringVar(value="")
        self.compact_variant = self.settings.compact_variant if self.settings.compact_variant in {"card", "strip"} else "card"
        self.compact_alpha = min(max(float(self.settings.compact_alpha), COMPACT_WINDOW_ALPHA_MIN), COMPACT_WINDOW_ALPHA_MAX)
        self.compact_alpha_var = tk.DoubleVar(value=round(self.compact_alpha * 100))
        self.compact_alpha_text_var = tk.StringVar(value="")

    def _build_header(self, container: ttk.Frame) -> None:
        header_frame = ttk.Frame(container, style="App.TFrame")
        header_frame.grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 10))
        header_frame.columnconfigure(2, weight=1)
        self.header_accent_bar = tk.Frame(header_frame, bg=self.theme.accent, width=6, height=34)
        self.header_accent_bar.grid(row=0, column=0, rowspan=2, sticky="ns", padx=(0, 10))
        title_row = ttk.Frame(header_frame, style="App.TFrame")
        title_row.grid(row=0, column=1, sticky="w")
        self.title_label = ttk.Label(title_row, text=self.t("window_title"), style="Title.TLabel")
        self.title_label.grid(row=0, column=0, sticky="w")
        self.version_badge = ttk.Frame(title_row, style="VersionBadge.TFrame", padding=(6, 2))
        self.version_badge.grid(row=0, column=1, sticky="sw", padx=(6, 0), pady=(3, 0))
        self.version_label = ttk.Label(self.version_badge, text=APP_VERSION, style="Version.TLabel")
        self.version_label.grid(row=0, column=0, sticky="w")
        self.subtitle_label = ttk.Label(
            header_frame,
            text=self.format_ref_label(),
            style="Subtitle.TLabel",
        )
        self.subtitle_label.grid(row=1, column=1, sticky="w", pady=(2, 0))

        right_header = ttk.Frame(header_frame, style="App.TFrame")
        right_header.grid(row=0, column=2, rowspan=2, sticky="e")
        right_header.columnconfigure(2, weight=1)

        lang_header = ttk.Frame(right_header, style="App.TFrame")
        lang_header.grid(row=0, column=0, rowspan=2, sticky="w", padx=(0, 10))

        self.lang_label = ttk.Label(lang_header, text=self.t("lang_label"), style="Subtitle.TLabel")
        self.lang_label.grid(row=0, column=0, sticky="w", pady=(0, 2))

        self.lang_combo = ttk.Combobox(
            lang_header,
            textvariable=self.lang_var,
            values=list(LANG_OPTIONS.keys()),
            width=10,
            state="readonly",
        )
        self.lang_combo.grid(row=1, column=0, sticky="w")
        self.lang_combo.bind("<<ComboboxSelected>>", self.on_language_select)

        theme_header = ttk.Frame(right_header, style="App.TFrame")
        theme_header.grid(row=0, column=1, rowspan=2, sticky="w", padx=(0, 10))

        self.theme_label = ttk.Label(theme_header, text=self.t("theme_label"), style="Subtitle.TLabel")
        self.theme_label.grid(row=0, column=0, sticky="w", pady=(0, 2))

        self.theme_combo = ttk.Combobox(
            theme_header,
            textvariable=self.theme_var,
            values=self.theme_display_values(),
            width=12,
            state="readonly",
        )
        self.theme_combo.grid(row=1, column=0, sticky="w")
        self.theme_combo.bind("<<ComboboxSelected>>", self.on_theme_select)

        repo_header = ttk.Frame(right_header, style="App.TFrame")
        repo_header.grid(row=0, column=2, rowspan=2, sticky="e")
        repo_header.columnconfigure(0, weight=1)

        self.repo_header_label = ttk.Label(repo_header, text=self.t("repo_label"), style="Subtitle.TLabel")
        self.repo_header_label.grid(row=0, column=0, sticky="w", pady=(0, 2))

        self.repo_entry = ttk.Entry(repo_header, textvariable=self.repo_entry_var, width=52)
        self.repo_entry.grid(row=1, column=0, sticky="ew")
        self.repo_entry.bind("<Return>", self.on_repo_entry_enter)

        self.repo_apply_button = ttk.Button(repo_header, text=self.t("repo_select"), command=self.browse_repo)
        self.repo_apply_button.grid(row=1, column=1, sticky="e", padx=(8, 0))

    def _build_output_section(self, container: ttk.Frame) -> None:
        output_section = ttk.Frame(container, style="App.TFrame")
        output_section.grid(row=1, column=0, sticky="ew", padx=(0, 10))
        output_section.columnconfigure(0, weight=1)

        meta_row = ttk.Frame(output_section, style="App.TFrame")
        meta_row.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        meta_row.columnconfigure(0, weight=1, uniform="meta")
        meta_row.columnconfigure(1, weight=1, uniform="meta")

        for idx in range(2):
            chip = ttk.Frame(meta_row, style="Chip.TFrame", padding=(8, 6))
            chip.grid(row=0, column=idx, sticky="ew", padx=(0, 10) if idx == 0 else (0, 0))
            chip.columnconfigure(1, weight=1)

            label = ttk.Label(chip, textvariable=self.meta_label_vars[idx], style="ChipLabel.TLabel")
            label.grid(row=0, column=0, sticky="w")

            value = ttk.Label(chip, textvariable=self.meta_value_vars[idx], style="ChipValue.TLabel")
            value.grid(row=0, column=1, sticky="w", padx=(6, 0))

        self.tile_grid = ttk.Frame(output_section, style="App.TFrame")
        self.tile_grid.grid(row=1, column=0, sticky="ew")
        tile_min_width = BASE_TILE_MIN_WIDTH
        self.tile_grid.columnconfigure(0, weight=1, uniform="tile", minsize=tile_min_width)
        self.tile_grid.columnconfigure(1, weight=1, uniform="tile", minsize=tile_min_width)

        tile_accents = self.theme.tile_accents
        tile_positions = [
            (0, 0, 1),
            (0, 1, 1),
            (1, 0, 1),
            (1, 1, 1),
            (2, 0, 2),
        ]
        self.tile_label_widgets: list[ttk.Label] = []
        self.tile_accent_widgets: list[tk.Frame] = []
        tile_wrap = BASE_TILE_LABEL_WRAP
        for idx in range(5):
            row, col, colspan = tile_positions[idx]
            tile = ttk.Frame(self.tile_grid, style="Tile.TFrame", padding=(10, 8))
            tile.grid(
                row=row,
                column=col,
                columnspan=colspan,
                sticky="ew",
                padx=(0, 10) if col == 0 and colspan == 1 else (0, 0),
                pady=(0, 12) if row < 2 else (0, 0),
            )
            tile.columnconfigure(1, weight=1)

            accent = tk.Frame(tile, bg=tile_accents[idx], width=4)
            accent.grid(row=0, column=0, rowspan=2, sticky="ns", padx=(0, 8))
            self.tile_accent_widgets.append(accent)

            label = ttk.Label(
                tile,
                textvariable=self.tile_label_vars[idx],
                style="TileLabel.TLabel",
                wraplength=tile_wrap,
            )
            label.grid(row=0, column=1, sticky="w")
            self.tile_label_widgets.append(label)

            value = ttk.Label(tile, textvariable=self.tile_value_vars[idx], style="TileValue.TLabel")
            value.grid(row=1, column=1, sticky="w", pady=(2, 0))

        delta_card = ttk.Frame(output_section, style="Card.TFrame", padding=(10, 8))
        delta_card.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        delta_card.columnconfigure(1, weight=1)

        self.delta_label = ttk.Label(delta_card, text=self.t("current_changes"), style="CardTitle.TLabel")
        self.delta_label.grid(row=0, column=0, sticky="w")

        self.delta_value_frame = ttk.Frame(delta_card, style="CardInner.TFrame")
        self.delta_value_frame.grid(row=0, column=1, sticky="e")

        self.delta_added_var = tk.StringVar(value="+0")
        self.delta_removed_var = tk.StringVar(value="-0")

        self.delta_added_box = ttk.Frame(self.delta_value_frame, style="DeltaBox.TFrame", padding=(8, 4))
        self.delta_added_box.grid(row=0, column=0, padx=(0, 8))

        self.delta_added_label = ttk.Label(
            self.delta_added_box,
            textvariable=self.delta_added_var,
            style="Stat.TLabel",
        )
        self.delta_added_label.grid(row=0, column=0, sticky="e")
        self.delta_added_label.configure(foreground=self.theme.success)

        self.delta_removed_box = ttk.Frame(self.delta_value_frame, style="DeltaBox.TFrame", padding=(8, 4))
        self.delta_removed_box.grid(row=0, column=1)

        self.delta_removed_label = ttk.Label(
            self.delta_removed_box,
            textvariable=self.delta_removed_var,
            style="Stat.TLabel",
        )
        self.delta_removed_label.grid(row=0, column=0, sticky="e")
        self.delta_removed_label.configure(foreground=self.theme.danger)

    def _build_progress_section(self, container: ttk.Frame) -> None:
        progress_section = ttk.Frame(container, style="App.TFrame")
        progress_section.grid(row=2, column=0, sticky="ew", padx=(0, 10), pady=(10, 0))
        progress_section.columnconfigure(0, weight=1)

        self.progress_title = ttk.Label(progress_section, text=self.t("progress"), style="Section.TLabel")
        self.progress_title.grid(row=0, column=0, sticky="w", pady=(0, 6))

        progress_card = ttk.Frame(progress_section, style="Card.TFrame", padding=(12, 10))
        progress_card.grid(row=1, column=0, sticky="ew")

        self.overall_progress_title = ttk.Label(progress_card, text=self.t("overall_progress"), style="CardTitle.TLabel")
        self.overall_progress_title.grid(row=0, column=0, sticky="w")

        self.overall_progress_var = tk.DoubleVar(value=0.0)
        self.overall_progress_bar = ttk.Progressbar(
            progress_card,
            orient="horizontal",
            mode="determinate",
            maximum=100.0,
            variable=self.overall_progress_var,
            length=BAR_LENGTH,
            style="Overall.Horizontal.TProgressbar",
        )
        self.overall_progress_bar.grid(row=1, column=0, sticky="ew", pady=(6, 0))

        self.overall_progress_text_var = tk.StringVar(value="")
        self.overall_progress_text_label = ttk.Label(
            progress_card,
            textvariable=self.overall_progress_text_var,
            style="CardLabel.TLabel",
        )
        self.overall_progress_text_label.grid(row=2, column=0, sticky="w", pady=(4, 0))

        self.daily_progress_title = ttk.Label(progress_card, text=self.t("daily_progress"), style="CardTitle.TLabel")
        self.daily_progress_title.grid(row=3, column=0, sticky="w", pady=(12, 0))

        self.daily_progress_var = tk.DoubleVar(value=0.0)
        self.daily_progress_bar = ttk.Progressbar(
            progress_card,
            orient="horizontal",
            mode="determinate",
            maximum=100.0,
            variable=self.daily_progress_var,
            length=BAR_LENGTH,
            style="Daily.Horizontal.TProgressbar",
        )
        self.daily_progress_bar.grid(row=4, column=0, sticky="ew", pady=(6, 0))

        self.daily_progress_text_var = tk.StringVar(value="")
        self.daily_progress_text_label = ttk.Label(
            progress_card,
            textvariable=self.daily_progress_text_var,
            style="CardLabel.TLabel",
        )
        self.daily_progress_text_label.grid(row=5, column=0, sticky="w", pady=(4, 0))

    def _build_right_panel(
        self,
        container: ttk.Frame,
        *,
        saved_graph_days: str,
        saved_custom_today_enabled: bool,
        saved_today_text: str,
        saved_auto_refresh: bool,
    ) -> None:
        right_area = ttk.Frame(container, style="App.TFrame")
        right_area.grid(row=1, column=2, rowspan=2, sticky="nw", padx=(14, 0))
        right_area.columnconfigure(0, weight=0, minsize=GRAPH_CARD_WIDTH)
        right_area.columnconfigure(1, weight=0, minsize=NOTE_CARD_WIDTH)

        self._build_graph_section(right_area, saved_graph_days)
        self._build_memo_section(right_area)
        self._build_controls_section(
            right_area,
            saved_custom_today_enabled=saved_custom_today_enabled,
            saved_today_text=saved_today_text,
            saved_auto_refresh=saved_auto_refresh,
        )

    def _build_graph_section(self, right_area: ttk.Frame, saved_graph_days: str) -> None:
        graph_section = ttk.Frame(right_area, style="App.TFrame")
        graph_section.grid(row=0, column=0, sticky="nw", padx=(0, 10))
        graph_section.columnconfigure(0, weight=1)

        graph_header = ttk.Frame(graph_section, style="App.TFrame")
        graph_header.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        graph_header.columnconfigure(0, weight=1)

        self.graph_title = ttk.Label(graph_header, text=self.t("graph_title"), style="Section.TLabel")
        self.graph_title.grid(row=0, column=0, sticky="w")

        self.graph_days_var = tk.StringVar(value=saved_graph_days)
        self.graph_days_label = ttk.Label(graph_header, text=self.t("graph_period"), style="Muted.TLabel")
        self.graph_days_label.grid(row=0, column=1, sticky="e", padx=(8, 4))

        self.graph_days_combo = ttk.Combobox(
            graph_header,
            values=["7", "14", "21", "30", "60", "90", "180"],
            textvariable=self.graph_days_var,
            width=6,
            state="readonly",
        )
        self.graph_days_combo.grid(row=0, column=2, sticky="e")
        self.graph_days_combo.bind("<<ComboboxSelected>>", self.on_graph_days_change)

        graph_card = ttk.Frame(graph_section, style="Card.TFrame", padding=(12, 10))
        graph_card.grid(row=1, column=0, sticky="ew")

        self.graph_canvas = tk.Canvas(
            graph_card,
            width=GRAPH_CANVAS_WIDTH,
            height=GRAPH_CANVAS_HEIGHT,
            bg=self.theme.canvas_bg,
            highlightthickness=1,
            highlightbackground=self.theme.border,
        )
        self.graph_canvas.grid(row=0, column=0, sticky="ew", pady=(2, 0))

        self.graph_summary_var = tk.StringVar(value="")
        self.graph_summary_label = ttk.Label(graph_card, textvariable=self.graph_summary_var, style="CardLabel.TLabel")
        self.graph_summary_label.grid(row=1, column=0, sticky="w", pady=(6, 0))

    def _build_memo_section(self, right_area: ttk.Frame) -> None:
        note_section = ttk.Frame(right_area, style="App.TFrame")
        note_section.grid(row=0, column=1, rowspan=2, sticky="nw", padx=(10, 0))
        note_section.columnconfigure(0, weight=1, minsize=NOTE_CARD_WIDTH)
        self.note_section = note_section
        self.note_section_column = 0
        self.right_area = right_area
        self.right_area_note_column = 1

        note_tabs = ttk.Frame(note_section, style="App.TFrame")
        note_tabs.grid(row=0, column=0, sticky="w", pady=(0, 6))

        self.memo_tab_button = ttk.Button(
            note_tabs,
            text=self.t("tab_memo"),
            command=lambda: self.set_note_tab("memo"),
            style="TabActive.TButton",
        )
        self.memo_tab_button.grid(row=0, column=0, sticky="w")

        self.grass_tab_button = ttk.Button(
            note_tabs,
            text=self.t("tab_grass"),
            command=lambda: self.set_note_tab("grass"),
            style="Tab.TButton",
        )
        self.grass_tab_button.grid(row=0, column=1, sticky="w", padx=(8, 0))

        note_card = ttk.Frame(note_section, style="Card.TFrame", padding=(12, 10))
        note_card.grid(row=1, column=0, sticky="ew")
        note_card.rowconfigure(0, weight=1)
        note_card.columnconfigure(0, weight=1)
        self.note_card = note_card

        self.memo_panel = ttk.Frame(note_card, style="CardInner.TFrame")
        self.memo_panel.grid(row=0, column=0, sticky="nsew")
        self.memo_panel.columnconfigure(0, weight=1)

        self.grass_panel = ttk.Frame(note_card, style="CardInner.TFrame")
        self.grass_panel.grid(row=0, column=0, sticky="nsew")
        self.grass_panel.columnconfigure(0, weight=1)

        self.memo_panel_controller = MemoPanel(
            MemoPanelBindings(
                root=self.root,
                translate=self.t,
                get_theme=lambda: self.theme,
                get_labels=self.memo_labels,
                get_placeholder_titles=self._placeholder_memo_titles,
                save_settings=self.save_settings,
                copy_to_clipboard=self.copy_to_clipboard,
                show_error=self.show_error,
                font_mono=FONT_MONO,
                scrollbar_style=CARD_SCROLLBAR_STYLE,
            ),
            initial_text=self.memo_text_value,
        )
        self.memo_panel_controller.build(self.memo_panel)
        self.grass_panel_controller = GrassPanel(
            GrassPanelBindings(
                translate=self.t,
                get_theme=lambda: self.theme,
                format_month_label=self.format_month_label,
            )
        )
        self.grass_panel_controller.build(self.grass_panel)
        self.grass_panel_controller.refresh()
        self.freeze_note_panel_size()
        self.set_note_tab(self.active_note_tab)

    def _build_controls_section(
        self,
        right_area: ttk.Frame,
        *,
        saved_custom_today_enabled: bool,
        saved_today_text: str,
        saved_auto_refresh: bool,
    ) -> None:
        self.custom_today_var = tk.BooleanVar(value=saved_custom_today_enabled)
        self.today_entry_var = tk.StringVar(value=saved_today_text)
        controls_section = ttk.Frame(right_area, style="App.TFrame")
        controls_section.grid(row=1, column=0, sticky="ew", padx=(0, 10), pady=(10, 0))
        controls_section.columnconfigure(0, weight=1, minsize=GRAPH_CARD_WIDTH)

        self.controls_title = ttk.Label(controls_section, text=self.t("settings"), style="Section.TLabel")
        self.controls_title.grid(row=0, column=0, sticky="w", pady=(0, 6))

        controls_card = ttk.Frame(controls_section, style="Card.TFrame", padding=(12, 10))
        controls_card.grid(row=1, column=0, sticky="ew")

        self.custom_today_check = ttk.Checkbutton(
            controls_card,
            text=self.t("custom_date"),
            variable=self.custom_today_var,
            command=self.on_custom_date_toggle,
        )
        self.custom_today_check.grid(row=0, column=0, columnspan=3, sticky="w", pady=(8, 0))
        controls_card.columnconfigure(0, weight=1)
        controls_card.columnconfigure(1, weight=0)

        self.today_entry = ttk.Entry(controls_card, textvariable=self.today_entry_var, width=14)
        self.today_entry.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self.today_entry.bind("<Return>", self.on_today_entry_enter)

        self.today_apply_button = ttk.Button(controls_card, text=self.t("apply_date"), command=self.apply_custom_date)
        self.today_apply_button.grid(row=1, column=1, sticky="e", padx=(8, 0), pady=(4, 0))

        self.goal_entry_var = tk.StringVar(value=str(self.goal))
        self.goal_label = ttk.Label(controls_card, text=self.t("goal_label"), style="CardLabel.TLabel")
        self.goal_label.grid(row=2, column=0, sticky="w", pady=(10, 0))

        self.goal_entry = ttk.Entry(controls_card, textvariable=self.goal_entry_var, width=14)
        self.goal_entry.grid(row=3, column=0, sticky="ew", pady=(4, 0))
        self.goal_entry.bind("<Return>", self.on_goal_entry_enter)

        self.goal_apply_button = ttk.Button(controls_card, text=self.t("apply_goal"), command=self.apply_goal)
        self.goal_apply_button.grid(row=3, column=1, sticky="e", padx=(8, 0), pady=(4, 0))

        self.author_entry_var = tk.StringVar(value=self.author_display)
        self.author_label = ttk.Label(controls_card, text=self.t("author_label"), style="CardLabel.TLabel")
        self.author_label.grid(row=4, column=0, sticky="w", pady=(10, 0))

        self.author_combo = ttk.Combobox(
            controls_card,
            textvariable=self.author_entry_var,
            values=self.author_options,
            width=22,
        )
        self.author_combo.grid(row=5, column=0, sticky="ew", pady=(4, 0))
        self.author_combo.bind("<Return>", self.on_author_entry_enter)
        self.author_combo.bind("<<ComboboxSelected>>", self.on_author_select)

        self.author_apply_button = ttk.Button(controls_card, text=self.t("apply_author"), command=self.apply_author)
        self.author_apply_button.grid(row=5, column=1, sticky="e", padx=(8, 0), pady=(4, 0))

        self.auto_refresh_var = tk.BooleanVar(value=saved_auto_refresh)
        self.auto_refresh_check = ttk.Checkbutton(
            controls_card,
            text=self.t("auto_refresh"),
            variable=self.auto_refresh_var,
            command=self.on_auto_refresh_toggle,
        )
        self.auto_refresh_check.grid(row=6, column=0, columnspan=3, sticky="w", pady=(10, 0))

    def _build_footer(self, container: ttk.Frame) -> None:
        footer_frame = ttk.Frame(container, style="App.TFrame")
        footer_frame.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        footer_frame.columnconfigure(0, weight=1)
        footer_frame.columnconfigure(1, weight=0)

        footer_left = ttk.Frame(footer_frame, style="App.TFrame")
        footer_left.grid(row=0, column=0, sticky="w")

        footer_right = ttk.Frame(footer_frame, style="App.TFrame")
        footer_right.grid(row=0, column=1, sticky="e")

        self.status_var = tk.StringVar(value="")
        self.status_label = ttk.Label(footer_left, textvariable=self.status_var, style="Muted.TLabel")
        self.status_label.grid(row=0, column=0, sticky="w")

        self.loading_var = tk.StringVar(value=" ")
        self.loading_label = ttk.Label(footer_left, textvariable=self.loading_var, style="Muted.TLabel")
        self.loading_bar = ttk.Progressbar(
            footer_left,
            orient="horizontal",
            mode="indeterminate",
            length=196,
            style=FOOTER_LOADING_STYLE,
        )
        self.loading_label.grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.loading_bar.grid(row=1, column=1, sticky="w", padx=(6, 0), pady=(6, 0))
        self.loading_bar.grid_remove()

        self.loading_detail_var = tk.StringVar(value="")
        self.loading_detail_label = ttk.Label(footer_right, textvariable=self.loading_detail_var, style="Muted.TLabel")
        self.loading_detail_label.grid(row=0, column=0, sticky="e", padx=(0, 10))
        self.loading_detail_label.grid_remove()

        self.compact_button_visual_state = "normal"
        self.compact_button = tk.Canvas(
            footer_right,
            width=COMPACT_LAUNCH_BUTTON_SIZE,
            height=COMPACT_LAUNCH_BUTTON_SIZE,
            highlightthickness=0,
            bd=0,
            relief="flat",
            cursor="hand2",
            takefocus=1,
        )
        self.compact_button.grid(row=0, column=1, sticky="e")
        self.compact_button.bind("<Enter>", lambda _: self.set_compact_launch_button_state("hover"))
        self.compact_button.bind("<Leave>", lambda _: self.set_compact_launch_button_state("normal"))
        self.compact_button.bind("<ButtonPress-1>", lambda _: self.set_compact_launch_button_state("pressed"))
        self.compact_button.bind("<ButtonRelease-1>", self.on_compact_launch_button_release)
        self.compact_button.bind("<Return>", self.on_compact_launch_button_keypress)
        self.compact_button.bind("<space>", self.on_compact_launch_button_keypress)
        self.redraw_compact_launch_button()

        self.refresh_button = ttk.Button(footer_right, text=self.t("refresh"), command=self.refresh, style="Accent.TButton")
        self.refresh_button.grid(row=0, column=2, sticky="e", padx=(8, 0))

        self.copy_button = ttk.Button(footer_right, text=self.t("copy"), command=self.copy_output)
        self.copy_button.grid(row=0, column=3, sticky="e", padx=(8, 0))

    def _build_compact_container(self) -> None:
        self.compact_container = ttk.Frame(self.root, padding=0, style="App.TFrame")
        self.compact_container.grid(row=0, column=0, sticky="nsew")
        self.compact_container.grid_remove()
        self.compact_container.columnconfigure(0, weight=1)

        self.compact_card = ttk.Frame(self.compact_container, style="Card.TFrame", padding=(10, 8))
        self.compact_card.grid(row=0, column=0, sticky="nsew")
        self.compact_card.columnconfigure(0, weight=1)
        self.compact_card.bind("<Double-Button-1>", lambda _: self.exit_compact_mode())

        compact_header = ttk.Frame(self.compact_card, style="CardInner.TFrame")
        compact_header.grid(row=0, column=0, sticky="ew")
        compact_header.columnconfigure(0, weight=1)

        self.compact_title_label = ttk.Label(compact_header, text=self.t("window_title"), style="CompactTitle.TLabel")
        self.compact_title_label.grid(row=0, column=0, sticky="w")

        compact_actions = ttk.Frame(compact_header, style="CardInner.TFrame")
        compact_actions.grid(row=0, column=1, sticky="e")

        self.compact_refresh_button = ttk.Button(
            compact_actions,
            text=self.t("compact_refresh_short"),
            command=self.refresh,
            style="CompactTool.TButton",
        )
        self.compact_refresh_button.grid(row=0, column=0, sticky="e")

        self.compact_restore_button = ttk.Button(
            compact_actions,
            text=self.t("compact_restore_short"),
            command=self.exit_compact_mode,
            style="CompactTool.TButton",
        )
        self.compact_restore_button.grid(row=0, column=1, sticky="e", padx=(6, 0))

        self.compact_progress_label = ttk.Label(
            self.compact_card,
            text=self.t("compact_today_progress"),
            style="CompactLabel.TLabel",
        )
        self.compact_progress_label.grid(row=1, column=0, sticky="w", pady=(12, 0))

        compact_progress_row = ttk.Frame(self.compact_card, style="CardInner.TFrame")
        compact_progress_row.grid(row=2, column=0, sticky="ew", pady=(4, 0))
        compact_progress_row.columnconfigure(0, weight=1)

        self.compact_progress_bar = ttk.Progressbar(
            compact_progress_row,
            orient="horizontal",
            mode="determinate",
            maximum=100.0,
            variable=self.compact_progress_value,
            style="Compact.Horizontal.TProgressbar",
        )
        self.compact_progress_bar.grid(row=0, column=0, sticky="ew")

        self.compact_progress_value_label = ttk.Label(
            compact_progress_row,
            textvariable=self.compact_progress_var,
            style="CompactBarValue.TLabel",
        )
        self.compact_progress_value_label.grid(row=0, column=1, sticky="e", padx=(8, 0))

        compact_delta_row = ttk.Frame(self.compact_card, style="CardInner.TFrame")
        compact_delta_row.grid(row=3, column=0, sticky="w", pady=(12, 0))

        self.compact_delta_label = ttk.Label(
            compact_delta_row,
            text=self.t("compact_delta"),
            style="CompactLabel.TLabel",
        )
        self.compact_delta_label.grid(row=0, column=0, sticky="w", padx=(0, 8))

        compact_delta_values = ttk.Frame(compact_delta_row, style="CardInner.TFrame")
        compact_delta_values.grid(row=0, column=1, sticky="w")

        self.compact_added_box = ttk.Frame(compact_delta_values, style="DeltaBox.TFrame", padding=(8, 4))
        self.compact_added_box.grid(row=0, column=0, sticky="w")

        self.compact_added_label = ttk.Label(
            self.compact_added_box,
            textvariable=self.compact_added_var,
            style="Stat.TLabel",
        )
        self.compact_added_label.grid(row=0, column=0, sticky="w")

        self.compact_removed_box = ttk.Frame(compact_delta_values, style="DeltaBox.TFrame", padding=(8, 4))
        self.compact_removed_box.grid(row=0, column=1, sticky="w", padx=(8, 0))

        self.compact_removed_label = ttk.Label(
            self.compact_removed_box,
            textvariable=self.compact_removed_var,
            style="Stat.TLabel",
        )
        self.compact_removed_label.grid(row=0, column=0, sticky="w")

        self.compact_datetime_label = ttk.Label(
            self.compact_card,
            textvariable=self.compact_datetime_var,
            style="CompactClock.TLabel",
        )
        self.compact_datetime_label.grid(row=4, column=0, sticky="w", pady=(12, 0))

        compact_footer = ttk.Frame(self.compact_card, style="CardInner.TFrame")
        compact_footer.grid(row=5, column=0, sticky="ew", pady=(10, 0))
        compact_footer.columnconfigure(0, weight=1)

        compact_footer_actions = ttk.Frame(compact_footer, style="CardInner.TFrame")
        compact_footer_actions.grid(row=0, column=1, sticky="e")

        self.compact_opacity_scale = tk.Scale(
            compact_footer_actions,
            orient="horizontal",
            from_=round(COMPACT_WINDOW_ALPHA_MIN * 100),
            to=round(COMPACT_WINDOW_ALPHA_MAX * 100),
            showvalue=False,
            sliderlength=12,
            width=6,
            borderwidth=0,
            highlightthickness=0,
            relief="flat",
            takefocus=False,
            variable=self.compact_alpha_var,
            command=self.on_compact_alpha_change,
            length=68,
        )
        self.compact_opacity_scale.grid(row=1, column=0, sticky="e", pady=(4, 0))

        self.compact_mode_button = ttk.Button(
            compact_footer_actions,
            text=self.t("compact_mode_to_strip"),
            command=self.toggle_compact_variant,
            style="CompactTool.TButton",
        )
        self.compact_mode_button.grid(row=0, column=0, sticky="e")

        self.compact_status_label = ttk.Label(
            self.compact_card,
            textvariable=self.compact_status_var,
            style="CompactMeta.TLabel",
            anchor="e",
            justify="right",
        )
        self.compact_status_label.place_forget()

        self.compact_strip = ttk.Frame(self.compact_container, style="Card.TFrame", padding=6)
        self.compact_strip.grid(row=0, column=0, sticky="nsew")
        self.compact_strip.grid_remove()
        self.compact_strip.columnconfigure(2, weight=1)
        self.compact_strip.bind("<Double-Button-1>", lambda _: self.exit_compact_mode())

        self.compact_strip_opacity_scale = tk.Scale(
            self.compact_strip,
            orient="vertical",
            from_=round(COMPACT_WINDOW_ALPHA_MIN * 100),
            to=round(COMPACT_WINDOW_ALPHA_MAX * 100),
            showvalue=False,
            sliderlength=8,
            width=4,
            borderwidth=0,
            highlightthickness=0,
            relief="flat",
            takefocus=False,
            variable=self.compact_alpha_var,
            command=self.on_compact_alpha_change,
            length=28,
        )
        self.compact_strip_opacity_scale.grid(row=0, column=0, rowspan=2, sticky="nsw", padx=(0, 6))

        self.compact_strip_summary_label = ttk.Label(
            self.compact_strip,
            textvariable=self.compact_strip_summary_var,
            style="CompactMeta.TLabel",
        )
        self.compact_strip_summary_label.grid(row=0, column=1, rowspan=2, sticky="w", padx=(0, 3))

        self.compact_strip_progress_canvas = tk.Canvas(
            self.compact_strip,
            width=112,
            height=16,
            highlightthickness=0,
            bd=0,
            relief="flat",
        )
        self.compact_strip_progress_canvas.grid(row=0, column=2, rowspan=2, sticky="ew", padx=(0, 3))
        self.compact_strip_progress_canvas.bind("<Configure>", lambda _: self.redraw_compact_strip_progress())

        compact_strip_actions = ttk.Frame(self.compact_strip, style="CardInner.TFrame")
        compact_strip_actions.grid(row=0, column=3, rowspan=2, sticky="e")

        self.compact_strip_mode_button = ttk.Button(
            compact_strip_actions,
            text=self.t("compact_mode_to_card"),
            command=self.toggle_compact_variant,
            style="CompactToolTiny.TButton",
        )
        self.compact_strip_mode_button.grid(row=0, column=0, sticky="e")

        self.compact_strip_restore_button = ttk.Button(
            compact_strip_actions,
            text=self.t("compact_restore_short"),
            command=self.exit_compact_mode,
            style="CompactToolTiny.TButton",
        )
        self.compact_strip_restore_button.grid(row=0, column=1, sticky="e", padx=(0, 0))

        self.apply_compact_variant_layout()

    def _finish_startup(self, args: argparse.Namespace, default_today_text: str) -> None:
        self.current_output = ""
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.apply_date_controls_state()
        self.update_repo_dependent_controls()
        if self.custom_today_var.get():
            try:
                self.today_override = self.parse_today_entry()
            except ValueError:
                self.today_override = args.today
                self.today_entry_var.set(default_today_text)
        self.apply_language()
        if not self.ensure_repo_ready():
            self.root.after(0, self.root.destroy)
            return
        if self.repo_selected:
            self.refresh()
        else:
            self.refresh_ref_label()
            self.status_var.set(self.t("status_repo_needed"))
        self.save_settings()

    def build_config(self) -> TrackerConfig:
        tracked_ref = resolve_ref(self.repo, self.ref)
        return TrackerConfig(
            repo=self.repo,
            goal=self.goal,
            base_total=self.base_total,
            base_commit=self.base_commit,
            author=self.author,
            ref=tracked_ref,
            include_local=True,
            today=self.today_override if self.custom_today_var.get() else None,
            month_end=self.month_end,
            assume_uncommitted_zero=False,
        )

    def format_ref_label(self) -> str:
        if not self.repo_selected:
            return self.t("repo_not_selected")
        tracked_ref = resolve_ref(self.repo, self.ref)
        label = f"{self.repo.name} • {tracked_ref}"
        current = resolve_current_ref(self.repo)
        self.current_ref = current
        if current != tracked_ref:
            return f"{self.repo.name} • {tracked_ref} + {current}"
        return label

    def t(self, key: str, **kwargs) -> str:
        text = TEXT.get(self.lang, TEXT["ko"]).get(key, key)
        try:
            return text.format(**kwargs)
        except (KeyError, ValueError):
            return text

    def show_error(self, message: str) -> None:
        messagebox.showerror(format_app_title(self.t("window_title")), message)

    def theme_display_label(self, theme_name: str) -> str:
        return self.t(f"theme_{theme_name}")

    def theme_display_values(self) -> list[str]:
        return [self.theme_display_label(theme_name) for theme_name in get_theme_names()]

    def refresh_theme_selector(self) -> None:
        if not hasattr(self, "theme_combo"):
            return
        self.theme_combo.configure(values=self.theme_display_values())
        self.theme_var.set(self.theme_display_label(self.theme_name))

    def resolve_selected_theme_name(self, selection: str) -> str:
        normalized = selection.strip()
        for theme_name in get_theme_names():
            if normalized == self.theme_display_label(theme_name):
                return theme_name
        return resolve_theme_name(normalized)

    def refresh_note_tab_buttons(self) -> None:
        if not hasattr(self, "memo_tab_button"):
            return
        self.memo_tab_button.configure(style="TabActive.TButton" if self.active_note_tab == "memo" else "Tab.TButton")
        self.grass_tab_button.configure(style="TabActive.TButton" if self.active_note_tab == "grass" else "Tab.TButton")

    def set_note_tab(self, tab_name: str) -> None:
        active_tab = "grass" if tab_name == "grass" else "memo"
        self.active_note_tab = active_tab
        if hasattr(self, "memo_panel"):
            if active_tab == "memo":
                self.grass_panel.grid_remove()
                self.memo_panel.grid()
            else:
                self.memo_panel.grid_remove()
                self.grass_panel.grid()
        self.refresh_note_tab_buttons()

    def freeze_note_panel_size(self) -> None:
        if not hasattr(self, "note_card"):
            return
        self.root.update_idletasks()
        panel_width = max(
            NOTE_CARD_WIDTH - 24,
            self.memo_panel.winfo_reqwidth(),
            self.grass_panel.winfo_reqwidth(),
        )
        panel_height = max(
            self.memo_panel.winfo_reqheight(),
            self.grass_panel.winfo_reqheight(),
        )
        card_width = panel_width + 24 + NOTE_CARD_FIT_PADDING
        card_height = panel_height + 20
        self.note_card.configure(width=card_width, height=card_height)
        self.note_card.grid_propagate(False)
        if hasattr(self, "note_section"):
            self.note_section.columnconfigure(self.note_section_column, minsize=card_width)
        if hasattr(self, "right_area"):
            self.right_area.columnconfigure(self.right_area_note_column, minsize=card_width)

    def format_month_label(self, month: int) -> str:
        if self.lang == "en":
            return calendar.month_abbr[month]
        return f"{month}월"

    def format_output_lines(self, result: TrackerResult) -> list[str]:
        month_label = self.format_month_label(result.month_end.month)
        return [
            f"- {self.t('today_label')}: {result.today.isoformat()}",
            f"- {self.t('days_left_label', month=month_label)}: "
            f"{result.days_left_including_today}{self.t('day_suffix')}",
            (
                f"- {self.t('daily_required_label')}: {result.need_today}{self.t('per_day_suffix')} "
                f"[{self.t('after_commit_prefix')} {result.need_after_commit}{self.t('per_day_suffix')}]"
            ),
            f"- {self.t('current_uncommitted_label')}: {result.uncommitted_insertions}{self.t('lines_suffix')}",
        ]

    def set_output_lines(self, result: TrackerResult, branch_total: int, share_text: str) -> None:
        month_label = self.format_month_label(result.month_end.month)
        self.meta_label_vars[0].set(self.t("today_label"))
        self.meta_value_vars[0].set(result.today.isoformat())
        self.meta_label_vars[1].set(self.t("days_left_label", month=month_label))
        self.meta_value_vars[1].set(f"{result.days_left_including_today}{self.t('day_suffix')}")

        branch_value = f"{branch_total:,}{self.t('lines_suffix')}" if branch_total is not None else ""
        tiles = [
            (self.t("daily_required_label"), f"{result.need_today}{self.t('per_day_suffix')}"),
            (self.t("after_commit_daily_label"), f"{result.need_after_commit}{self.t('per_day_suffix')}"),
            (self.t("branch_only_label"), branch_value),
            (self.t("current_uncommitted_label"), f"{result.uncommitted_insertions}{self.t('lines_suffix')}"),
            (self.t("share_label"), share_text),
        ]

        for idx in range(5):
            label, value = tiles[idx] if idx < len(tiles) else ("", "")
            if idx == 1 and not value:
                label = ""
            self.tile_label_vars[idx].set(label)
            self.tile_value_vars[idx].set(value)

    def apply_language(self) -> None:
        self.root.title(format_app_title(self.t("window_title")))
        self.title_label.configure(text=self.t("window_title"))
        self.lang_label.configure(text=self.t("lang_label"))
        self.theme_label.configure(text=self.t("theme_label"))
        self.repo_header_label.configure(text=self.t("repo_label"))
        self.repo_apply_button.configure(text=self.t("repo_select"))
        self.refresh_theme_selector()

        self.graph_title.configure(text=self.t("graph_title"))
        self.graph_days_label.configure(text=self.t("graph_period"))
        self.memo_tab_button.configure(text=self.t("tab_memo"))
        self.grass_tab_button.configure(text=self.t("tab_grass"))
        if self.memo_panel_controller is not None:
            self.memo_panel_controller.apply_language()
        if self.grass_panel_controller is not None:
            self.grass_panel_controller.apply_language()
        self.freeze_note_panel_size()

        self.controls_title.configure(text=self.t("settings"))
        self.custom_today_check.configure(text=self.t("custom_date"))
        self.today_apply_button.configure(text=self.t("apply_date"))
        self.goal_label.configure(text=self.t("goal_label"))
        self.goal_apply_button.configure(text=self.t("apply_goal"))
        self.author_label.configure(text=self.t("author_label"))
        self.author_apply_button.configure(text=self.t("apply_author"))
        self.auto_refresh_check.configure(text=self.t("auto_refresh"))

        self.progress_title.configure(text=self.t("progress"))
        self.overall_progress_title.configure(text=self.t("overall_progress"))
        self.daily_progress_title.configure(text=self.t("daily_progress"))
        self.delta_label.configure(text=self.t("current_changes"))
        self.redraw_compact_launch_button()
        self.refresh_button.configure(text=self.t("refresh"))
        self.copy_button.configure(text=self.t("copy"))
        self.compact_title_label.configure(text=self.t("window_title"))
        self.compact_refresh_button.configure(text=self.t("compact_refresh_short"))
        self.compact_restore_button.configure(text=self.t("compact_restore_short"))
        self.compact_mode_button.configure(text=self.current_compact_mode_button_text())
        self.compact_strip_mode_button.configure(text=self.current_compact_mode_button_text())
        self.compact_strip_restore_button.configure(text=self.t("compact_restore_short"))
        self.update_compact_alpha_text()
        self.compact_progress_label.configure(text=self.t("compact_today_progress"))
        self.compact_delta_label.configure(text=self.t("compact_delta"))
        self.apply_layout_for_language()
        self.refresh_compact_display()

        self.rebuild_author_controls(reset_invalid_to_auto=False)
        self.refresh_note_tab_buttons()

        if self.refresh_in_progress:
            self.loading_var.set(self.t("loading"))
            self.loading_detail_var.set(self.t("loading_detail"))
            self.loading_detail_label.grid()
        else:
            self.loading_var.set(" ")
            self.loading_detail_var.set("")
            self.loading_detail_label.grid_remove()

    def on_language_select(self, _: tk.Event) -> None:
        self.lang = LANG_OPTIONS.get(self.lang_var.get(), "ko")
        self.apply_language()
        self.save_settings()
        self.refresh()

    def on_theme_select(self, _: tk.Event) -> None:
        selected_theme_name = self.resolve_selected_theme_name(self.theme_var.get())
        if selected_theme_name == self.theme_name:
            self.theme_var.set(self.theme_display_label(self.theme_name))
            return
        self.theme_name = selected_theme_name
        self.theme = get_theme_palette(self.theme_name)
        self.theme_var.set(self.theme_display_label(self.theme_name))
        self.apply_color_palette()
        self.save_settings()

    def apply_layout_for_language(self) -> None:
        tile_min_width = BASE_TILE_MIN_WIDTH
        tile_wrap = BASE_TILE_LABEL_WRAP
        if hasattr(self, "tile_grid"):
            self.tile_grid.columnconfigure(0, minsize=tile_min_width)
            self.tile_grid.columnconfigure(1, minsize=tile_min_width)
        for label in getattr(self, "tile_label_widgets", []):
            label.configure(wraplength=tile_wrap)

        if self.compact_mode:
            return

        fitted_width = self.get_fitted_window_width()
        min_height = getattr(self, "min_height", MIN_WINDOW_HEIGHT)
        self.root.minsize(fitted_width, min_height)
        self.root.maxsize(fitted_width, self.root.winfo_screenheight())
        current_geometry = self.normalize_geometry(
            self.root.winfo_geometry(),
            min_width=fitted_width,
            width_override=fitted_width,
        )
        if not current_geometry:
            current_geometry = f"{fitted_width}x{min_height}"
        self.last_window_geometry = current_geometry
        self.root.geometry(current_geometry)

    def apply_color_palette(self) -> None:
        self.root.configure(bg=self.theme.app_bg)
        self._configure_style_palette()
        self._configure_widget_palette()

    def _configure_style_palette(self) -> None:
        palette = self.theme
        self.style.configure("App.TFrame", background=palette.app_bg)
        self.style.configure("Card.TFrame", background=palette.card_bg, borderwidth=1, relief="solid")
        self.style.configure("CardInner.TFrame", background=palette.card_bg, borderwidth=0, relief="flat")
        self.style.configure("DeltaBox.TFrame", background=palette.card_bg, borderwidth=1, relief="solid")
        self.style.configure("VersionBadge.TFrame", background=palette.card_bg, borderwidth=1, relief="solid")
        self.style.configure("Title.TLabel", background=palette.app_bg, foreground=palette.text, font=FONT_TITLE)
        self.style.configure("Version.TLabel", background=palette.card_bg, foreground=palette.muted_text, font=FONT_VERSION)
        self.style.configure("Subtitle.TLabel", background=palette.app_bg, foreground=palette.muted_text, font=FONT_SUBTITLE)
        self.style.configure("Section.TLabel", background=palette.app_bg, foreground=palette.text, font=FONT_SECTION)
        self.style.configure("CardTitle.TLabel", background=palette.card_bg, foreground=palette.text, font=FONT_BODY)
        self.style.configure("CompactTitle.TLabel", background=palette.card_bg, foreground=palette.text, font=FONT_SECTION)
        self.style.configure("CardLabel.TLabel", background=palette.card_bg, foreground=palette.muted_text, font=FONT_BODY)
        self.style.configure("CompactLabel.TLabel", background=palette.card_bg, foreground=palette.muted_text, font=FONT_CHIP)
        self.style.configure("CompactValue.TLabel", background=palette.card_bg, foreground=palette.text, font=FONT_COMPACT_VALUE)
        self.style.configure("CompactBarValue.TLabel", background=palette.card_bg, foreground=palette.text, font=FONT_COMPACT_BAR_VALUE)
        self.style.configure("CompactMeta.TLabel", background=palette.card_bg, foreground=palette.muted_text, font=FONT_COMPACT_META)
        self.style.configure("CompactClock.TLabel", background=palette.card_bg, foreground=palette.muted_text, font=FONT_COMPACT_CLOCK)
        self.style.configure(
            "CompactTool.TButton",
            font=FONT_COMPACT_TOOL,
            foreground=palette.text,
            background=palette.card_bg,
            bordercolor=palette.border,
            darkcolor=palette.card_bg,
            lightcolor=palette.card_bg,
            focuscolor=palette.card_bg,
            padding=(4, 2),
            relief="flat",
        )
        compact_tool_hover = blend_hex(palette.card_bg, palette.accent_light, 0.18)
        compact_tool_pressed = blend_hex(palette.card_bg, palette.accent, 0.28)
        self.style.map(
            "CompactTool.TButton",
            background=[
                ("active", compact_tool_hover),
                ("pressed", compact_tool_pressed),
                ("disabled", palette.card_bg),
            ],
            foreground=[
                ("disabled", blend_hex(palette.muted_text, palette.border, 0.5)),
            ],
            bordercolor=[
                ("active", blend_hex(palette.border, palette.accent_light, 0.45)),
                ("pressed", palette.accent_dark),
                ("disabled", palette.border),
            ],
            lightcolor=[
                ("active", compact_tool_hover),
                ("pressed", compact_tool_pressed),
                ("disabled", palette.card_bg),
            ],
            darkcolor=[
                ("active", compact_tool_hover),
                ("pressed", compact_tool_pressed),
                ("disabled", palette.card_bg),
            ],
        )
        self.style.configure(
            "CompactToolSmall.TButton",
            font=("Bahnschrift", 8),
            foreground=palette.text,
            background=palette.card_bg,
            bordercolor=palette.border,
            darkcolor=palette.card_bg,
            lightcolor=palette.card_bg,
            focuscolor=palette.card_bg,
            padding=(2, 1),
            relief="flat",
        )
        self.style.map(
            "CompactToolSmall.TButton",
            background=[
                ("active", compact_tool_hover),
                ("pressed", compact_tool_pressed),
                ("disabled", palette.card_bg),
            ],
            foreground=[
                ("disabled", blend_hex(palette.muted_text, palette.border, 0.5)),
            ],
            bordercolor=[
                ("active", blend_hex(palette.border, palette.accent_light, 0.45)),
                ("pressed", palette.accent_dark),
                ("disabled", palette.border),
            ],
            lightcolor=[
                ("active", compact_tool_hover),
                ("pressed", compact_tool_pressed),
                ("disabled", palette.card_bg),
            ],
            darkcolor=[
                ("active", compact_tool_hover),
                ("pressed", compact_tool_pressed),
                ("disabled", palette.card_bg),
            ],
        )
        self.style.configure(
            "CompactToolTiny.TButton",
            font=("Bahnschrift", 7, "bold"),
            foreground=palette.text,
            background=palette.card_bg,
            bordercolor=palette.border,
            darkcolor=palette.card_bg,
            lightcolor=palette.card_bg,
            focuscolor=palette.card_bg,
            padding=(0, 0),
            relief="flat",
        )
        self.style.map(
            "CompactToolTiny.TButton",
            background=[
                ("active", compact_tool_hover),
                ("pressed", compact_tool_pressed),
                ("disabled", palette.card_bg),
            ],
            foreground=[
                ("disabled", blend_hex(palette.muted_text, palette.border, 0.5)),
            ],
            bordercolor=[
                ("active", blend_hex(palette.border, palette.accent_light, 0.45)),
                ("pressed", palette.accent_dark),
                ("disabled", palette.border),
            ],
            lightcolor=[
                ("active", compact_tool_hover),
                ("pressed", compact_tool_pressed),
                ("disabled", palette.card_bg),
            ],
            darkcolor=[
                ("active", compact_tool_hover),
                ("pressed", compact_tool_pressed),
                ("disabled", palette.card_bg),
            ],
        )
        self.style.configure("Stat.TLabel", background=palette.card_bg, foreground=palette.text, font=FONT_MONO)
        self.style.configure("Muted.TLabel", background=palette.app_bg, foreground=palette.muted_text, font=FONT_BODY)
        self.style.configure("Tile.TFrame", background=palette.card_bg, borderwidth=1, relief="solid")
        self.style.configure("TileLabel.TLabel", background=palette.card_bg, foreground=palette.muted_text, font=FONT_TILE_LABEL)
        self.style.configure(
            "TileValue.TLabel",
            background=palette.card_bg,
            foreground=palette.text,
            font=FONT_TILE_VALUE,
        )
        self.style.configure("Chip.TFrame", background=palette.card_bg, borderwidth=1, relief="solid")
        self.style.configure("ChipLabel.TLabel", background=palette.card_bg, foreground=palette.muted_text, font=FONT_CHIP)
        self.style.configure("ChipValue.TLabel", background=palette.card_bg, foreground=palette.text, font=FONT_CHIP)
        self.style.configure("TCheckbutton", background=palette.card_bg, foreground=palette.text, font=FONT_BODY)
        self.style.map("TCheckbutton", background=[("active", palette.card_bg)])
        self.style.configure("TEntry", fieldbackground=palette.card_bg, foreground=palette.text, font=FONT_BODY)
        self.style.configure(
            "TCombobox",
            fieldbackground=palette.card_bg,
            background=palette.card_bg,
            foreground=palette.text,
            arrowcolor=palette.text,
            font=FONT_BODY,
        )
        self.style.map(
            "TCombobox",
            fieldbackground=[("readonly", palette.card_bg)],
            background=[("readonly", palette.card_bg)],
            foreground=[("readonly", palette.text)],
            arrowcolor=[("readonly", palette.text)],
        )
        self.root.option_add("*TCombobox*Listbox*Background", palette.card_bg)
        self.root.option_add("*TCombobox*Listbox*Foreground", palette.text)
        self.root.option_add("*TCombobox*Listbox*selectBackground", palette.accent_dark)
        self.root.option_add("*TCombobox*Listbox*selectForeground", palette.text)
        button_bg = blend_hex(palette.card_bg, palette.accent_light, 0.48)
        button_bg_active = blend_hex(palette.card_bg, palette.accent_light, 0.72)
        button_bg_pressed = blend_hex(palette.card_bg, palette.accent, 0.84)
        button_bg_disabled = blend_hex(palette.card_bg, palette.border, 0.9)
        button_border = blend_hex(palette.border, palette.accent_light, 0.58)
        button_border_active = blend_hex(palette.border, palette.accent, 0.82)
        button_border_disabled = blend_hex(palette.card_bg, palette.border, 0.98)
        button_text = contrast_text_color(button_bg)
        button_text_active = contrast_text_color(button_bg_active)
        button_text_pressed = contrast_text_color(button_bg_pressed)
        disabled_button_text = blend_hex(palette.button_disabled_text, palette.muted_text, 0.35)
        accent_hover = blend_hex(palette.accent, palette.accent_light, 0.3)
        accent_pressed = blend_hex(palette.accent, palette.accent_dark, 0.52)
        accent_disabled = blend_hex(palette.card_bg, palette.border, 0.92)
        tab_hover = blend_hex(palette.card_bg, palette.accent_light, 0.28)
        tab_disabled = blend_hex(palette.card_bg, palette.border, 0.86)
        self.style.configure(
            "TButton",
            font=FONT_BODY,
            foreground=button_text,
            background=button_bg,
            bordercolor=button_border,
            darkcolor=button_bg,
            lightcolor=button_bg,
            focuscolor=button_bg,
            padding=(12, 6),
            relief="flat",
        )
        self.style.map(
            "TButton",
            background=[
                ("active", button_bg_active),
                ("pressed", button_bg_pressed),
                ("disabled", button_bg_disabled),
            ],
            foreground=[
                ("active", button_text_active),
                ("pressed", button_text_pressed),
                ("disabled", disabled_button_text),
            ],
            bordercolor=[
                ("active", button_border_active),
                ("pressed", palette.accent_alt_dark),
                ("disabled", button_border_disabled),
            ],
            lightcolor=[
                ("active", button_bg_active),
                ("pressed", button_bg_pressed),
                ("disabled", button_bg_disabled),
            ],
            darkcolor=[
                ("active", button_bg_active),
                ("pressed", button_bg_pressed),
                ("disabled", button_bg_disabled),
            ],
        )
        self.style.configure(
            "Accent.TButton",
            font=FONT_BODY,
            foreground=palette.button_text,
            background=palette.accent,
            bordercolor=blend_hex(palette.accent_dark, palette.accent_light, 0.35),
            darkcolor=palette.accent,
            lightcolor=palette.accent,
            focuscolor=palette.accent,
            padding=(12, 6),
        )
        self.style.map(
            "Accent.TButton",
            background=[
                ("active", accent_hover),
                ("pressed", accent_pressed),
                ("disabled", accent_disabled),
            ],
            foreground=[("disabled", disabled_button_text)],
            bordercolor=[
                ("active", palette.accent_light),
                ("pressed", palette.accent_dark),
                ("disabled", button_border_disabled),
            ],
            lightcolor=[
                ("active", accent_hover),
                ("pressed", accent_pressed),
                ("disabled", accent_disabled),
            ],
            darkcolor=[
                ("active", accent_hover),
                ("pressed", accent_pressed),
                ("disabled", accent_disabled),
            ],
        )
        self.style.configure(
            "Tab.TButton",
            font=FONT_BODY,
            foreground=palette.text,
            background=palette.card_bg,
            bordercolor=palette.border,
            darkcolor=palette.card_bg,
            lightcolor=palette.card_bg,
            focuscolor=palette.card_bg,
            padding=(10, 6),
        )
        self.style.map(
            "Tab.TButton",
            background=[("active", tab_hover), ("disabled", tab_disabled)],
            foreground=[("disabled", disabled_button_text)],
            bordercolor=[
                ("active", blend_hex(palette.border, palette.accent_light, 0.45)),
                ("disabled", button_border_disabled),
            ],
            lightcolor=[("active", tab_hover), ("disabled", tab_disabled)],
            darkcolor=[("active", tab_hover), ("disabled", tab_disabled)],
        )
        self.style.configure(
            "TabActive.TButton",
            font=FONT_BODY,
            foreground=palette.button_text,
            background=palette.accent,
            bordercolor=blend_hex(palette.accent_dark, palette.accent_light, 0.35),
            darkcolor=palette.accent,
            lightcolor=palette.accent,
            focuscolor=palette.accent,
            padding=(10, 6),
        )
        self.style.map(
            "TabActive.TButton",
            background=[
                ("active", accent_hover),
                ("pressed", accent_pressed),
                ("disabled", accent_disabled),
            ],
            foreground=[("disabled", disabled_button_text)],
            bordercolor=[
                ("active", palette.accent_light),
                ("pressed", palette.accent_dark),
                ("disabled", button_border_disabled),
            ],
            lightcolor=[
                ("active", accent_hover),
                ("pressed", accent_pressed),
                ("disabled", accent_disabled),
            ],
            darkcolor=[
                ("active", accent_hover),
                ("pressed", accent_pressed),
                ("disabled", accent_disabled),
            ],
        )
        self.style.layout(
            CARD_SCROLLBAR_STYLE,
            [
                (
                    "Vertical.Scrollbar.trough",
                    {
                        "sticky": "ns",
                        "children": [
                            (
                                "Vertical.Scrollbar.thumb",
                                {
                                    "expand": "1",
                                    "sticky": "nswe",
                                },
                            )
                        ],
                    },
                )
            ],
        )
        self.style.configure(
            CARD_SCROLLBAR_STYLE,
            gripcount=0,
            background=palette.accent_dark,
            darkcolor=palette.accent_dark,
            lightcolor=palette.accent_light,
            troughcolor=palette.canvas_bg,
            bordercolor=palette.border,
            arrowcolor=palette.accent_dark,
            relief="flat",
            troughrelief="flat",
            borderwidth=0,
            arrowsize=12,
        )
        self.style.map(
            CARD_SCROLLBAR_STYLE,
            background=[("active", palette.accent), ("pressed", palette.accent_alt)],
            darkcolor=[("active", palette.accent), ("pressed", palette.accent_alt_dark)],
            lightcolor=[("active", palette.accent_light), ("pressed", palette.accent_alt)],
            bordercolor=[("active", palette.accent_dark)],
        )
        self.style.configure(
            "Overall.Horizontal.TProgressbar",
            troughcolor=palette.overall_progress_trough,
            background=palette.accent,
            lightcolor=palette.accent,
            darkcolor=palette.accent,
        )
        self.style.configure(
            "Daily.Horizontal.TProgressbar",
            troughcolor=palette.daily_progress_trough,
            background=palette.accent_alt,
            lightcolor=palette.accent_alt,
            darkcolor=palette.accent_alt,
        )
        self.style.configure(
            "Compact.Horizontal.TProgressbar",
            troughcolor=palette.graph_grid,
            background=palette.accent_alt,
            lightcolor=palette.accent_alt,
            darkcolor=palette.accent_alt,
            bordercolor=palette.border,
            thickness=10,
        )
        self.style.configure(
            FOOTER_LOADING_STYLE,
            troughcolor=palette.graph_grid,
            background=palette.accent,
            lightcolor=palette.accent_light,
            darkcolor=palette.accent_dark,
            bordercolor=palette.border,
            thickness=9,
        )

    def _configure_widget_palette(self) -> None:
        palette = self.theme
        if hasattr(self, "header_accent_bar"):
            self.header_accent_bar.configure(bg=palette.accent)
        for idx, widget in enumerate(getattr(self, "tile_accent_widgets", [])):
            widget.configure(bg=palette.tile_accents[idx % len(palette.tile_accents)])
        if hasattr(self, "delta_added_label"):
            self.delta_added_label.configure(foreground=palette.success)
        if hasattr(self, "delta_removed_label"):
            self.delta_removed_label.configure(foreground=palette.danger)
        if hasattr(self, "compact_added_label"):
            self.compact_added_label.configure(foreground=palette.success)
        if hasattr(self, "compact_removed_label"):
            self.compact_removed_label.configure(foreground=palette.danger)
        if hasattr(self, "compact_progress_value_label"):
            self.compact_progress_value_label.configure(foreground=palette.accent)
        if hasattr(self, "compact_opacity_scale"):
            self.compact_opacity_scale.configure(
                bg=palette.card_bg,
                troughcolor=palette.graph_grid,
                activebackground=palette.accent_light,
                highlightbackground=palette.card_bg,
                highlightcolor=palette.card_bg,
            )
        if hasattr(self, "compact_strip_opacity_scale"):
            self.compact_strip_opacity_scale.configure(
                bg=palette.card_bg,
                troughcolor=palette.graph_grid,
                activebackground=palette.accent_light,
                highlightbackground=palette.card_bg,
                highlightcolor=palette.card_bg,
            )
        if hasattr(self, "compact_strip_progress_canvas"):
            self.redraw_compact_strip_progress()
        if hasattr(self, "compact_button"):
            self.redraw_compact_launch_button()
        if hasattr(self, "graph_canvas"):
            self.graph_canvas.configure(bg=palette.canvas_bg, highlightbackground=palette.border)
        memo_panel_controller = getattr(self, "memo_panel_controller", None)
        if memo_panel_controller is not None:
            memo_panel_controller.apply_theme()
        grass_panel_controller = getattr(self, "grass_panel_controller", None)
        if grass_panel_controller is not None:
            grass_panel_controller.apply_theme()
        if hasattr(self, "memo_tab_button"):
            self.refresh_note_tab_buttons()
        graph_highlight_day = getattr(self, "graph_highlight_day", None)
        if graph_highlight_day is not None and hasattr(self, "graph_canvas"):
            self.draw_daily_graph(getattr(self, "graph_points", []), graph_highlight_day)

    def ensure_repo_ready(self) -> bool:
        git_version, _, _ = get_git_info()
        if git_version:
            return True
        open_download = messagebox.askyesno(self.t("setup_title"), self.t("git_missing"))
        if open_download:
            try:
                webbrowser.open("https://git-scm.com/download/win")
            except Exception:
                pass
        return False

    @staticmethod
    def _parse_author_identity(identity: str) -> tuple[str | None, str | None]:
        match = AUTHOR_IDENTITY_RE.fullmatch(identity.strip())
        if not match:
            cleaned = identity.strip()
            return (cleaned or None), None
        name = match.group("name").strip() or None
        email = match.group("email").strip() or None
        return name, email

    @staticmethod
    def _parse_email_parts(email: str | None) -> tuple[str | None, str | None]:
        if not email:
            return None, None
        if "@" not in email:
            return email.strip() or None, None
        local_part, domain = email.rsplit("@", 1)
        local = local_part.strip() or None
        normalized_domain = domain.strip().casefold() or None
        return local, normalized_domain

    @staticmethod
    def _normalize_author_handle(value: str | None) -> str | None:
        if not value:
            return None
        cleaned = value.strip()
        if not cleaned or not AUTHOR_HANDLE_RE.fullmatch(cleaned):
            return None
        return cleaned.casefold()

    @classmethod
    def _extract_author_merge_keys(
        cls,
        identity: str,
        name: str | None,
        email: str | None,
    ) -> list[str]:
        merge_keys: list[str] = []
        if email:
            merge_keys.append(f"email:{email.casefold()}")

        normalized_name = cls._normalize_author_handle(name)
        email_local, email_domain = cls._parse_email_parts(email)
        normalized_local = cls._normalize_author_handle(email_local)

        if normalized_name and normalized_local and normalized_name == normalized_local:
            merge_keys.append(f"handle:{normalized_name}")

        if email_domain == GITHUB_NOREPLY_DOMAIN and email_local:
            github_handle_source = email_local.rsplit("+", 1)[-1]
            github_handle = cls._normalize_author_handle(github_handle_source)
            if github_handle and (normalized_name is None or normalized_name == github_handle):
                merge_keys.append(f"handle:{github_handle}")

        if not email and normalized_name:
            merge_keys.append(f"name:{normalized_name}")

        if not merge_keys:
            merge_keys.append(f"identity:{identity.casefold()}")
        return list(dict.fromkeys(merge_keys))

    @classmethod
    def _author_display_priority(cls, name: str | None, email: str | None) -> tuple[int, int]:
        email_local, email_domain = cls._parse_email_parts(email)
        normalized_name = cls._normalize_author_handle(name)
        normalized_local = cls._normalize_author_handle(email_local)

        priority = 0
        if email:
            priority = 3
            if email_domain == GITHUB_NOREPLY_DOMAIN:
                priority = 1
            elif normalized_name and normalized_local and normalized_name == normalized_local:
                priority = 4
        elif normalized_name:
            priority = 2

        display_length = len((name or "") + (email or ""))
        return priority, -display_length

    @classmethod
    def _build_author_option_entries(
        cls,
        identities: list[str],
        auto_label: str,
        all_label: str,
    ) -> tuple[list[str], dict[str, str], dict[str, str]]:
        options = [auto_label, all_label]
        mapping = {auto_label: "auto", all_label: ""}
        aliases = {"auto": auto_label, "": all_label}

        parsed_identities: list[dict[str, object]] = []
        key_to_indices: dict[str, list[int]] = {}

        for raw_identity in identities:
            identity = raw_identity.strip()
            if not identity:
                continue

            name, email = cls._parse_author_identity(identity)
            merge_keys = cls._extract_author_merge_keys(identity, name, email)
            item = {
                "identity": identity,
                "name": name,
                "email": email,
                "merge_keys": merge_keys,
            }
            index = len(parsed_identities)
            parsed_identities.append(item)
            for key in merge_keys:
                key_to_indices.setdefault(key, []).append(index)

        groups: list[dict[str, object]] = []
        visited: set[int] = set()
        for start_index, item in enumerate(parsed_identities):
            if start_index in visited:
                continue

            stack = [start_index]
            component_indices: list[int] = []
            while stack:
                index = stack.pop()
                if index in visited:
                    continue
                visited.add(index)
                component_indices.append(index)
                for merge_key in parsed_identities[index]["merge_keys"]:
                    for linked_index in key_to_indices.get(str(merge_key), []):
                        if linked_index not in visited:
                            stack.append(linked_index)

            component_indices.sort()
            component = [parsed_identities[index] for index in component_indices]
            display_item = component[0]
            best_priority = cls._author_display_priority(
                display_item.get("name"),
                display_item.get("email"),
            )
            for candidate in component[1:]:
                candidate_priority = cls._author_display_priority(
                    candidate.get("name"),
                    candidate.get("email"),
                )
                if candidate_priority > best_priority:
                    display_item = candidate
                    best_priority = candidate_priority

            group = {
                "display": str(display_item["identity"]),
                "identities": [],
                "emails": [],
            }
            for candidate in component:
                identity = str(candidate["identity"])
                email = candidate.get("email")
                if identity not in group["identities"]:
                    group["identities"].append(identity)
                if email and email not in group["emails"]:
                    group["emails"].append(email)
            groups.append(group)

        for group in groups:
            display = str(group["display"])
            if display in mapping:
                continue

            emails = [value for value in group["emails"] if value]
            identities_for_filter = emails or [value for value in group["identities"] if value]
            if not identities_for_filter:
                continue

            escaped_patterns = [re.escape(value) for value in identities_for_filter]
            filter_value = encode_author_patterns(escaped_patterns)
            mapping[display] = filter_value
            options.append(display)
            aliases[filter_value] = display
            legacy_filter_value = "|".join(escaped_patterns)
            if legacy_filter_value:
                aliases[legacy_filter_value] = display

            for alias_source in group["identities"]:
                aliases[re.escape(alias_source)] = display
            for alias_source in group["emails"]:
                aliases[re.escape(alias_source)] = display

        return options, mapping, aliases

    def build_author_options(self) -> tuple[list[str], dict[str, str], dict[str, str]]:
        auto_label = self.t("author_auto")
        all_label = self.t("author_all")
        try:
            out = run_git(self.repo, ["shortlog", "-sne", "--all"])
        except RuntimeError:
            return self._build_author_option_entries([], auto_label, all_label)

        identities: list[str] = []
        for raw_line in out.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if "\t" in line:
                _, identity = line.split("\t", 1)
            else:
                parts = line.split(None, 1)
                if len(parts) < 2:
                    continue
                identity = parts[1]
            identity = identity.strip()
            if identity:
                identities.append(identity)
        return self._build_author_option_entries(identities, auto_label, all_label)

    def map_author_to_display(self, author_raw: str) -> str:
        if not author_raw:
            return self.t("author_all")
        if author_raw.lower() == "auto":
            return self.t("author_auto")
        alias_display = getattr(self, "author_display_aliases", {}).get(author_raw)
        if alias_display:
            return alias_display
        for display, filt in self.author_filter_map.items():
            if filt == author_raw:
                return display
        return author_raw

    def rebuild_author_controls(self, *, reset_invalid_to_auto: bool) -> None:
        self.author_options, self.author_filter_map, self.author_display_aliases = self.build_author_options()
        if hasattr(self, "author_combo"):
            self.author_combo.configure(values=self.author_options)

        if reset_invalid_to_auto and self.author_display not in self.author_filter_map:
            self.author_display = self.t("author_auto")
            self.author_raw = "auto"
        else:
            self.author_display = self.map_author_to_display(self.author_raw)
            self.author_raw = self.author_filter_map.get(self.author_display, self.author_raw)

        self.author = resolve_author(self.repo, self.author_raw)
        if hasattr(self, "author_entry_var"):
            self.author_entry_var.set(self.author_display)

    def refresh_ref_label(self) -> None:
        self.subtitle_label.configure(text=self.format_ref_label())

    @staticmethod
    def _coerce_positive_int(value: object, default: int) -> int:
        try:
            parsed = int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return default
        return parsed if parsed > 0 else default

    @staticmethod
    def _parse_geometry(value: str) -> tuple[int, int, int | None, int | None] | None:
        match = GEOMETRY_RE.fullmatch(value.strip())
        if not match:
            return None
        raw_width = int(match.group("width"))
        raw_height = int(match.group("height"))
        pos_x = int(match.group("x")) if match.group("x") is not None else None
        pos_y = int(match.group("y")) if match.group("y") is not None else None
        return raw_width, raw_height, pos_x, pos_y

    def get_fitted_window_width(self) -> int:
        screen_limit = max(640, self.root.winfo_screenwidth() - WINDOW_SCREEN_MARGIN)
        try:
            self.root.update_idletasks()
        except tk.TclError:
            return min(MIN_WINDOW_WIDTH, screen_limit)

        requested_width = 0
        for widget in (getattr(self, "container", None), self.root):
            if widget is None:
                continue
            try:
                requested_width = max(requested_width, int(widget.winfo_reqwidth()))
            except (tk.TclError, TypeError, ValueError):
                continue

        if requested_width <= 1:
            requested_width = min(BASE_WINDOW_WIDTH, screen_limit)

        return min(max(requested_width, MIN_WINDOW_WIDTH), screen_limit)

    def normalize_geometry(
        self,
        value: str,
        *,
        min_width: int | None = None,
        width_override: int | None = None,
    ) -> str | None:
        parsed = self._parse_geometry(value)
        if not parsed:
            return None
        raw_width, raw_height, pos_x, pos_y = parsed
        target_min_width = max(min_width or MIN_WINDOW_WIDTH, MIN_WINDOW_WIDTH)
        screen_limit = max(640, self.root.winfo_screenwidth() - WINDOW_SCREEN_MARGIN)
        width = width_override if width_override is not None else raw_width
        width = min(max(width, target_min_width), screen_limit)
        height = max(raw_height, MIN_WINDOW_HEIGHT)
        if pos_x is None or pos_y is None or raw_width < target_min_width or raw_height < MIN_WINDOW_HEIGHT:
            return f"{width}x{height}"
        return f"{width}x{height}{pos_x:+d}{pos_y:+d}"

    def get_persisted_geometry(self) -> str:
        default_geometry = f"{BASE_WINDOW_WIDTH}x{BASE_WINDOW_HEIGHT}"
        if self.compact_mode:
            return self.last_window_geometry or default_geometry
        try:
            if self.root.state() == "iconic":
                return self.last_window_geometry
        except tk.TclError:
            return self.last_window_geometry
        geometry = self.normalize_geometry(self.root.winfo_geometry())
        if geometry:
            self.last_window_geometry = geometry
            return geometry
        return self.last_window_geometry or default_geometry

    def _set_root_attribute(self, key: str, value: object) -> None:
        try:
            self.root.attributes(key, value)
        except tk.TclError:
            pass

    def _set_root_overrideredirect(self, enabled: bool) -> None:
        try:
            self.root.overrideredirect(enabled)
        except tk.TclError:
            pass

    def update_compact_alpha_text(self) -> None:
        alpha_percent = int(round(float(self.compact_alpha_var.get())))
        self.compact_alpha_text_var.set(self.t("compact_opacity_value", value=f"{alpha_percent}%"))

    def apply_compact_alpha(self) -> None:
        if self.compact_mode:
            self._set_root_attribute("-alpha", self.compact_alpha)

    def on_compact_alpha_change(self, value: str) -> None:
        try:
            alpha_percent = float(value)
        except (TypeError, ValueError):
            alpha_percent = float(self.compact_alpha_var.get())
        alpha_percent = min(max(alpha_percent, COMPACT_WINDOW_ALPHA_MIN * 100), COMPACT_WINDOW_ALPHA_MAX * 100)
        rounded_percent = round(alpha_percent)
        self.compact_alpha = rounded_percent / 100.0
        if int(round(float(self.compact_alpha_var.get()))) != rounded_percent:
            self.compact_alpha_var.set(rounded_percent)
        self.update_compact_alpha_text()
        self.apply_compact_alpha()
        self.save_settings()

    def current_compact_mode_button_text(self) -> str:
        return self.t("compact_mode_to_card" if self.compact_variant == "strip" else "compact_mode_to_strip")

    def apply_compact_variant_layout(self) -> None:
        if not hasattr(self, "compact_card") or not hasattr(self, "compact_strip"):
            return
        if self.compact_variant == "strip":
            self.compact_card.grid_remove()
            self.compact_strip.grid()
        else:
            self.compact_strip.grid_remove()
            self.compact_card.grid()
        if hasattr(self, "compact_mode_button"):
            self.compact_mode_button.configure(text=self.current_compact_mode_button_text())
        if hasattr(self, "compact_strip_mode_button"):
            self.compact_strip_mode_button.configure(text=self.current_compact_mode_button_text())

    def toggle_compact_variant(self) -> None:
        self.compact_variant = "card" if self.compact_variant == "strip" else "strip"
        self.apply_compact_variant_layout()
        self.refresh_compact_display()
        self.save_settings()
        if self.compact_mode:
            self.root.update_idletasks()
            self.place_compact_window()

    def set_compact_status(self, message: str) -> None:
        self.compact_status_var.set(message)
        if self.compact_variant == "strip":
            if message:
                self.compact_strip_summary_var.set(message)
            return
        if not hasattr(self, "compact_status_label"):
            return
        if message:
            self.compact_status_label.place(relx=1.0, rely=1.0, anchor="se", x=-10, y=-34)
        else:
            self.compact_status_label.place_forget()

    def get_compact_window_size(self) -> tuple[int, int]:
        self.root.update_idletasks()
        active_widget = self.compact_strip if self.compact_variant == "strip" else self.compact_card
        min_width = COMPACT_STRIP_MIN_WIDTH if self.compact_variant == "strip" else COMPACT_WINDOW_MIN_WIDTH
        min_height = COMPACT_STRIP_MIN_HEIGHT if self.compact_variant == "strip" else COMPACT_WINDOW_MIN_HEIGHT
        width = max(min_width, active_widget.winfo_reqwidth())
        height = max(min_height, active_widget.winfo_reqheight())
        return width, height

    def redraw_compact_strip_progress(self) -> None:
        if not hasattr(self, "compact_strip_progress_canvas"):
            return
        palette = self.theme
        canvas = self.compact_strip_progress_canvas
        canvas.configure(bg=palette.card_bg)
        width = max(1, int(canvas.winfo_width() or canvas.cget("width")))
        height = max(1, int(canvas.winfo_height() or canvas.cget("height")))
        progress = max(0.0, min(100.0, float(self.compact_progress_value.get())))
        fill_width = round((width - 2) * (progress / 100.0))
        canvas.delete("all")
        canvas.create_rectangle(1, 1, width - 1, height - 1, fill=palette.graph_grid, outline=palette.border, width=1)
        if fill_width > 0:
            canvas.create_rectangle(1, 1, min(width - 1, 1 + fill_width), height - 1, fill=palette.accent_alt, outline="")
        canvas.create_text(
            width // 2,
            height // 2,
            text=self.compact_strip_progress_text,
            fill=palette.text,
            font=("Bahnschrift", 8, "bold"),
        )

    def get_work_area(self) -> tuple[int, int, int, int]:
        if sys.platform == "win32":
            try:
                import ctypes
                from ctypes import wintypes

                class RECT(ctypes.Structure):
                    _fields_ = [
                        ("left", wintypes.LONG),
                        ("top", wintypes.LONG),
                        ("right", wintypes.LONG),
                        ("bottom", wintypes.LONG),
                    ]

                class MONITORINFO(ctypes.Structure):
                    _fields_ = [
                        ("cbSize", wintypes.DWORD),
                        ("rcMonitor", RECT),
                        ("rcWork", RECT),
                        ("dwFlags", wintypes.DWORD),
                    ]

                monitor = ctypes.windll.user32.MonitorFromWindow(self.root.winfo_id(), 2)
                info = MONITORINFO()
                info.cbSize = ctypes.sizeof(MONITORINFO)
                if ctypes.windll.user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
                    return info.rcWork.left, info.rcWork.top, info.rcWork.right, info.rcWork.bottom
            except Exception:
                pass

        return 0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight()

    def get_compact_geometry(self) -> str:
        width, height = self.get_compact_window_size()
        left, top, right, bottom = self.get_work_area()
        x = max(left + COMPACT_WINDOW_MARGIN, right - width - COMPACT_WINDOW_MARGIN)
        y = max(top + COMPACT_WINDOW_MARGIN, bottom - height - COMPACT_WINDOW_MARGIN)
        return f"{width}x{height}+{x}+{y}"

    def place_compact_window(self) -> None:
        if not self.compact_mode:
            return
        self.compact_reposition_job = None
        try:
            self.compact_placing = True
            width, height = self.get_compact_window_size()
            left, top, right, bottom = self.get_work_area()
            x = max(left + COMPACT_WINDOW_MARGIN, right - width - COMPACT_WINDOW_MARGIN)
            y = max(top + COMPACT_WINDOW_MARGIN, bottom - height - COMPACT_WINDOW_MARGIN)
            current_geometry = (self.root.winfo_width(), self.root.winfo_height(), self.root.winfo_x(), self.root.winfo_y())
            target_geometry = (width, height, x, y)
            if current_geometry == target_geometry:
                return
            self.root.minsize(width, height)
            self.root.maxsize(width, height)
            self.root.geometry(f"{width}x{height}+{x}+{y}")
        finally:
            self.compact_placing = False

    def schedule_compact_reposition(self) -> None:
        if not self.compact_mode or self.compact_reposition_job is not None:
            return
        self.compact_reposition_job = self.root.after_idle(self.place_compact_window)

    def on_root_configure(self, event: tk.Event) -> None:
        if event.widget is not self.root or not self.compact_mode or self.compact_placing:
            return
        self.schedule_compact_reposition()

    def update_compact_datetime(self) -> None:
        reference_day = self.compact_reference_day or (self.today_override or dt.date.today())
        now_text = dt.datetime.now().strftime("%H:%M:%S")
        self.compact_datetime_var.set(
            self.t(
                "compact_datetime_text",
                date=reference_day.isoformat(),
                time=now_text,
            )
        )

    def tick_compact_clock(self) -> None:
        self.compact_clock_job = None
        self.update_compact_datetime()
        if self.compact_mode:
            self.compact_clock_job = self.root.after(1000, self.tick_compact_clock)

    def schedule_compact_clock(self) -> None:
        self.cancel_compact_clock()
        self.tick_compact_clock()

    def cancel_compact_clock(self) -> None:
        if self.compact_clock_job is None:
            return
        try:
            self.root.after_cancel(self.compact_clock_job)
        except tk.TclError:
            pass
        self.compact_clock_job = None

    def refresh_compact_display(self) -> None:
        snapshot = self.last_refresh_snapshot
        if snapshot is None:
            self.compact_progress_value.set(0.0)
            self.compact_progress_var.set("--")
            self.compact_strip_summary_var.set(self.t("status_repo_needed") if not self.repo_selected else "")
            self.compact_strip_progress_text = "--"
            self.redraw_compact_strip_progress()
            self.compact_added_var.set("+0")
            self.compact_removed_var.set("-0")
            self.compact_reference_day = self.today_override or dt.date.today()
            self.set_compact_status(self.t("status_repo_needed") if not self.repo_selected else "")
            self.update_compact_datetime()
            return

        result = snapshot.result
        today_target = snapshot.today_target
        if today_target <= 0:
            daily_percent = 100.0
            compact_progress_text = self.t("compact_progress_complete")
            compact_strip_text = f"{snapshot.today_done:,}/{snapshot.today_done:,} [100%]"
        else:
            daily_percent = (snapshot.today_done / today_target) * 100.0
            compact_progress_text = self.t(
                "compact_progress_value_text",
                percent=f"{daily_percent:.0f}",
                done=f"{snapshot.today_done:,}",
                target=f"{today_target:,}",
            )
            compact_strip_text = f"{snapshot.today_done:,}/{today_target:,} [{daily_percent:.0f}%]"
        self.compact_progress_value.set(max(0.0, min(100.0, daily_percent)))
        self.compact_progress_var.set(compact_progress_text)
        self.compact_strip_summary_var.set("")
        self.compact_strip_progress_text = compact_strip_text
        self.redraw_compact_strip_progress()
        self.compact_added_var.set(f"+{result.uncommitted_insertions:,}")
        self.compact_removed_var.set(f"-{snapshot.uncommitted_deletions:,}")
        self.compact_reference_day = result.today
        self.set_compact_status("")
        self.update_compact_datetime()
        if self.compact_mode:
            self.schedule_compact_reposition()

    def enter_compact_mode(self) -> None:
        if self.compact_mode:
            return
        self.last_window_geometry = self.get_persisted_geometry()
        self.compact_mode = True
        self.root.withdraw()
        self.container.grid_remove()
        self.apply_compact_variant_layout()
        self.compact_container.grid()
        self.root.update_idletasks()
        self._set_root_overrideredirect(True)
        compact_width, compact_height = self.get_compact_window_size()
        self.root.minsize(compact_width, compact_height)
        self.root.maxsize(compact_width, compact_height)
        compact_geometry = self.get_compact_geometry()
        self.root.geometry(compact_geometry)
        self._set_root_attribute("-topmost", True)
        self.update_compact_alpha_text()
        self.apply_compact_alpha()
        self.root.deiconify()
        self.root.lift()
        self.place_compact_window()
        self.root.after(80, self.place_compact_window)
        self.refresh_compact_display()
        self.schedule_compact_clock()

    def exit_compact_mode(self) -> None:
        if not self.compact_mode:
            return
        self.compact_mode = False
        self.cancel_compact_clock()
        if self.compact_reposition_job is not None:
            try:
                self.root.after_cancel(self.compact_reposition_job)
            except tk.TclError:
                pass
            self.compact_reposition_job = None
        self.root.withdraw()
        self.compact_container.grid_remove()
        self.container.grid()
        self._set_root_overrideredirect(False)
        self._set_root_attribute("-alpha", 1.0)
        self._set_root_attribute("-topmost", False)
        fitted_width = self.get_fitted_window_width()
        min_height = getattr(self, "min_height", MIN_WINDOW_HEIGHT)
        self.root.minsize(fitted_width, min_height)
        self.root.maxsize(fitted_width, self.root.winfo_screenheight())
        restored_geometry = self.normalize_geometry(
            self.last_window_geometry,
            min_width=fitted_width,
            width_override=fitted_width,
        )
        if not restored_geometry:
            restored_geometry = f"{fitted_width}x{min_height}"
        self.last_window_geometry = restored_geometry
        self.root.deiconify()
        self.root.geometry(restored_geometry)

    def load_settings(self) -> UISettings:
        for candidate in (self.settings_path, self.legacy_settings_path):
            if not candidate.exists():
                continue
            try:
                raw = candidate.read_text(encoding="utf-8")
                data = json.loads(raw)
                if isinstance(data, dict):
                    return UISettings.from_dict(data)
            except (OSError, json.JSONDecodeError):
                continue
        return UISettings()

    def save_settings(self) -> None:
        memo_text = self.memo_panel_controller.get_text() if self.memo_panel_controller is not None else self.memo_text_value
        self.settings = UISettings(
            goal=self.goal,
            custom_today_enabled=self.custom_today_var.get(),
            custom_today=self.today_entry_var.get().strip(),
            graph_days=self.graph_days_var.get(),
            auto_refresh=self.auto_refresh_var.get(),
            author=self.author_raw,
            author_display=self.author_display,
            memo_text=memo_text,
            compact_variant=self.compact_variant,
            compact_alpha=self.compact_alpha,
            repo_path=str(self.repo) if self.repo_selected else "",
            lang=self.lang,
            theme=self.theme_name,
            geometry=self.get_persisted_geometry(),
        )
        try:
            self.settings_path.parent.mkdir(parents=True, exist_ok=True)
            self.settings_path.write_text(
                json.dumps(self.settings.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            # UI 동작은 계속 유지하고, 저장 실패만 무시한다.
            pass

    def parse_today_entry(self) -> dt.date:
        value = self.today_entry_var.get().strip()
        try:
            return dt.date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(self.t("error_date_format")) from exc

    def parse_goal_entry(self) -> int:
        value = self.goal_entry_var.get().strip().replace(",", "")
        if not value.isdigit():
            raise ValueError(self.t("error_goal"))
        goal = int(value)
        if goal <= 0:
            raise ValueError(self.t("error_goal"))
        return goal

    def apply_date_controls_state(self) -> None:
        state = "normal" if self.custom_today_var.get() else "disabled"
        self.today_entry.configure(state=state)
        self.today_apply_button.configure(state=state)

    def update_repo_dependent_controls(self) -> None:
        repo_state = "normal" if self.repo_selected else "disabled"
        if not self.repo_selected and self.auto_refresh_var.get():
            self.auto_refresh_var.set(False)
        if not self.repo_selected:
            self.cancel_auto_refresh()
        self.auto_refresh_check.configure(state=repo_state)
        refresh_state = "normal" if self.repo_selected and not self.refresh_in_progress else "disabled"
        self.refresh_button.configure(state=refresh_state)
        self.compact_refresh_button.configure(state=refresh_state)

    def redraw_compact_launch_button(self) -> None:
        if not hasattr(self, "compact_button"):
            return
        palette = self.theme
        size = COMPACT_LAUNCH_BUTTON_SIZE
        inset = 2
        state = getattr(self, "compact_button_visual_state", "normal")
        fill = palette.accent
        border = blend_hex(palette.accent_dark, palette.accent_light, 0.35)
        if state == "hover":
            fill = blend_hex(palette.accent, palette.accent_light, 0.3)
            border = palette.accent_light
        elif state == "pressed":
            fill = blend_hex(palette.accent, palette.accent_dark, 0.52)
            border = palette.accent_dark

        self.compact_button.configure(bg=palette.app_bg, width=size, height=size)
        self.compact_button.delete("all")
        self.compact_button.create_rectangle(
            inset,
            inset,
            size - inset,
            size - inset,
            fill=fill,
            outline=border,
            width=1,
        )
        self.compact_button.create_text(
            size // 2,
            size // 2,
            text=self.t("compact_toggle_short"),
            fill=palette.button_text,
            font=("Bahnschrift", 9, "bold"),
        )

    def set_compact_launch_button_state(self, state: str) -> None:
        self.compact_button_visual_state = state
        self.redraw_compact_launch_button()

    def on_compact_launch_button_release(self, event: tk.Event) -> str:
        if not hasattr(self, "compact_button"):
            return "break"
        inside = 0 <= event.x <= COMPACT_LAUNCH_BUTTON_SIZE and 0 <= event.y <= COMPACT_LAUNCH_BUTTON_SIZE
        self.set_compact_launch_button_state("hover" if inside else "normal")
        if inside:
            self.enter_compact_mode()
        return "break"

    def on_compact_launch_button_keypress(self, _: tk.Event) -> str:
        self.enter_compact_mode()
        return "break"

    def set_loading_state(self, loading: bool) -> None:
        if loading:
            self.loading_var.set(self.t("loading"))
            self.loading_detail_var.set(self.t("loading_detail"))
            self.loading_detail_label.grid()
            self.loading_bar.grid()
            self.loading_bar.start(10)
            self.refresh_button.configure(state="disabled")
            self.compact_refresh_button.configure(state="disabled")
            self.set_compact_status("")
            return

        self.loading_bar.stop()
        self.loading_var.set(" ")
        self.loading_detail_var.set("")
        self.loading_detail_label.grid_remove()
        self.loading_bar.grid_remove()
        self.update_repo_dependent_controls()

    def refresh(self) -> None:
        if not self.repo_selected:
            self.cancel_auto_refresh()
            self.refresh_ref_label()
            self.status_var.set(self.t("status_repo_needed"))
            self.set_compact_status(self.t("status_repo_needed"))
            self.update_repo_dependent_controls()
            return
        if self.refresh_in_progress:
            if self.auto_refresh_var.get():
                self.schedule_auto_refresh()
            return

        self.refresh_in_progress = True
        self.refresh_request_id += 1
        request_id = self.refresh_request_id
        self.refresh_ref_label()
        config = self.build_config()
        graph_days = int(self.graph_days_var.get())
        self.set_loading_state(True)

        worker = threading.Thread(
            target=self._refresh_worker,
            args=(request_id, config, graph_days),
            daemon=True,
        )
        worker.start()

    def _refresh_worker(self, request_id: int, config: TrackerConfig, graph_days: int) -> None:
        try:
            snapshot = build_refresh_snapshot(self.repo, self.author, config, graph_days)
            self.safe_after(lambda s=snapshot: self._on_refresh_success(request_id, s))
        except Exception as exc:  # pragma: no cover
            self.safe_after(lambda e=str(exc): self._on_refresh_error(request_id, e))

    def safe_after(self, callback) -> None:
        try:
            self.root.after(0, callback)
        except tk.TclError:
            pass

    def _on_refresh_success(self, request_id: int, snapshot: RefreshSnapshot) -> None:
        if request_id != self.refresh_request_id:
            return

        self.refresh_in_progress = False
        self.set_loading_state(False)
        self.last_refresh_snapshot = snapshot

        result = snapshot.result
        branch_total = snapshot.branch_total
        self.branch_total_committed = branch_total
        self.main_total_committed = max(result.committed_total - branch_total, 0)

        lines = self.format_output_lines(result)
        self.current_output = "\n".join(lines)
        self.set_output_lines(result, branch_total, snapshot.share_text)
        self.delta_added_var.set(f"+{result.uncommitted_insertions:,}")
        self.delta_removed_var.set(f"-{snapshot.uncommitted_deletions:,}")
        self.update_progress(result, snapshot.today_done, snapshot.today_target)
        self.update_graph(snapshot.points, result.today, snapshot.graph_days, snapshot.graph_avg, snapshot.graph_max)
        uncommitted_today = result.uncommitted_insertions if result.today == dt.date.today() else 0
        self.update_grass(snapshot.grass_points, result.today, uncommitted_today)

        status_suffix = self.t("status_auto_suffix") if self.auto_refresh_var.get() else ""
        update_time = dt.datetime.now().strftime("%H:%M:%S")
        self.status_var.set(self.t("status_updated", time=update_time) + status_suffix)
        self.refresh_compact_display()
        if self.auto_refresh_var.get():
            self.schedule_auto_refresh()

    def _on_refresh_error(self, request_id: int, error_message: str) -> None:
        if request_id != self.refresh_request_id:
            return

        self.refresh_in_progress = False
        self.set_loading_state(False)
        self.status_var.set(self.t("status_error"))
        self.set_compact_status(self.t("status_error"))
        self.show_error(error_message)

    def copy_output(self) -> None:
        if not self.current_output:
            return
        self.copy_to_clipboard(self.current_output, "status_clipboard")

    def copy_to_clipboard(self, text: str, status_key: str = "status_clipboard") -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status_var.set(self.t(status_key))

    def update_progress(self, result: TrackerResult, today_done: int, today_target: int) -> None:
        current_total = self.main_total_committed + self.branch_total_committed + result.uncommitted_insertions
        if self.goal <= 0:
            overall_percent = 0.0
        else:
            overall_percent = (current_total / self.goal) * 100.0
        overall_percent = max(0.0, min(100.0, overall_percent))
        self.overall_progress_var.set(overall_percent)
        breakdown = self.t(
            "progress_breakdown",
            main=f"{self.main_total_committed:,}",
            branch=f"{self.branch_total_committed:,}",
            uncommitted=f"{result.uncommitted_insertions:,}",
        )
        self.overall_progress_text_var.set(
            self.t(
                "overall_progress_text",
                current=f"{current_total:,}",
                goal=f"{self.goal:,}",
                percent=f"{overall_percent:.1f}",
                breakdown=breakdown,
            )
        )

        if today_target <= 0:
            daily_percent = 100.0
        else:
            daily_percent = (today_done / today_target) * 100.0
        daily_percent = max(0.0, min(100.0, daily_percent))

        self.daily_progress_var.set(daily_percent)
        self.daily_progress_text_var.set(
            self.t(
                "daily_progress_text",
                done=f"{today_done:,}",
                target=f"{today_target:,}",
                percent=f"{daily_percent:.1f}",
            )
        )

    def update_graph(
        self,
        points: list[tuple[dt.date, int]],
        highlight_day: dt.date,
        days: int,
        avg_value: float,
        max_value: int,
    ) -> None:
        self.graph_points = list(points)
        self.graph_highlight_day = highlight_day
        self.draw_daily_graph(points, highlight_day)
        self.graph_summary_var.set(
            self.t(
                "graph_summary",
                days=days,
                avg=f"{avg_value:.1f}",
                max=f"{max_value:,}",
            )
        )

    def update_grass(
        self,
        points: list[tuple[dt.date, int]],
        highlight_day: dt.date,
        uncommitted_today: int = 0,
    ) -> None:
        if self.grass_panel_controller is not None:
            self.grass_panel_controller.update(points, highlight_day, uncommitted_today)

    def draw_daily_graph(self, points: list[tuple[dt.date, int]], highlight_day: dt.date) -> None:
        canvas = self.graph_canvas
        palette = self.theme
        canvas.delete("all")

        width = GRAPH_CANVAS_WIDTH
        height = GRAPH_CANVAS_HEIGHT
        margin_left = 42
        margin_right = 10
        margin_top = 8
        margin_bottom = 34

        chart_w = width - margin_left - margin_right
        chart_h = height - margin_top - margin_bottom
        if chart_w <= 0 or chart_h <= 0:
            return

        canvas.create_rectangle(
            margin_left,
            margin_top,
            margin_left + chart_w,
            margin_top + chart_h,
            outline=palette.border,
            width=1,
        )

        values = [v for _, v in points]
        max_val = max(values) if values else 0
        y_top = max(max_val, 1)

        grid_count = 4
        for i in range(grid_count + 1):
            y = margin_top + chart_h - (chart_h * i / grid_count)
            canvas.create_line(
                margin_left,
                y,
                margin_left + chart_w,
                y,
                fill=palette.graph_grid,
                width=1,
            )
            label_value = int(round(y_top * i / grid_count))
            canvas.create_text(
                margin_left - 6,
                y,
                text=f"{label_value}",
                anchor="e",
                fill=palette.muted_text,
                font=("Consolas", 8),
            )

        if not points:
            return

        slot_w = chart_w / len(points)
        label_step = max(1, math.ceil(len(points) / 6))

        line_points: list[float] = []
        y_base = margin_top + chart_h
        for idx, (day, value) in enumerate(points):
            x = margin_left + idx * slot_w + slot_w / 2
            y = y_base - (value / y_top) * chart_h if y_top > 0 else y_base
            line_points.extend([x, y])

        if len(line_points) >= 4:
            canvas.create_line(
                *line_points,
                fill=palette.accent,
                width=2,
                smooth=False,
            )

        label_y = min(height - 2, y_base + 6)
        for idx, (day, value) in enumerate(points):
            x = margin_left + idx * slot_w + slot_w / 2
            y = y_base - (value / y_top) * chart_h if y_top > 0 else y_base
            radius = 4 if day == highlight_day else 3
            color = palette.accent_alt if day == highlight_day else palette.accent
            canvas.create_oval(
                x - radius,
                y - radius,
                x + radius,
                y + radius,
                fill=color,
                outline="",
            )

            if idx == 0 or idx == len(points) - 1 or idx % label_step == 0:
                canvas.create_text(
                    x,
                    label_y,
                    text=day.strftime("%m-%d"),
                    anchor="n",
                    fill=palette.muted_text,
                    font=("Consolas", 7),
                )

    def on_today_entry_enter(self, _: tk.Event) -> None:
        self.apply_custom_date()

    def on_goal_entry_enter(self, _: tk.Event) -> None:
        self.apply_goal()

    def on_author_entry_enter(self, _: tk.Event) -> None:
        self.apply_author()

    def on_author_select(self, _: tk.Event) -> None:
        self.apply_author()

    def on_repo_entry_enter(self, _: tk.Event) -> None:
        self.apply_repo_path()

    def memo_labels(self) -> MemoLabels:
        return MemoLabels(
            template_title=self.t("memo_template_title"),
            done_label=self.t("done"),
            todo_label=self.t("todo"),
        )

    def default_memo_text(self) -> str:
        return default_memo_text(self.memo_labels())

    @staticmethod
    def _placeholder_memo_titles() -> set[str]:
        return get_placeholder_titles(
            [
                str(lang_text.get("memo_template_title", "")).strip()
                for lang_text in TEXT.values()
            ]
        )

    def on_graph_days_change(self, _: tk.Event) -> None:
        self.save_settings()
        self.refresh()

    def on_custom_date_toggle(self) -> None:
        self.apply_date_controls_state()
        if not self.custom_today_var.get():
            self.today_override = None
            self.save_settings()
            self.refresh()
            return
        self.apply_custom_date()

    def apply_custom_date(self) -> None:
        if not self.custom_today_var.get():
            return
        try:
            self.today_override = self.parse_today_entry()
            self.save_settings()
            self.refresh()
        except ValueError as exc:
            self.show_error(str(exc))

    def apply_goal(self) -> None:
        try:
            self.goal = self.parse_goal_entry()
            self.save_settings()
            self.refresh()
        except ValueError as exc:
            self.show_error(str(exc))

    def apply_author(self) -> None:
        raw_input = self.author_entry_var.get().strip()
        self.author_display = raw_input
        if raw_input in self.author_filter_map:
            self.author_raw = self.author_filter_map[raw_input]
        else:
            self.author_raw = raw_input
        self.author = resolve_author(self.repo, self.author_raw)
        clear_cache_for_repo(self.repo)
        self.save_settings()
        self.refresh()

    def browse_repo(self) -> None:
        start_dir = self.repo_entry_var.get().strip() or str(self.repo)
        selected = filedialog.askdirectory(
            title=self.t("repo_dialog_title"),
            initialdir=start_dir if Path(start_dir).exists() else None,
        )
        if not selected:
            return
        self.repo_entry_var.set(selected)
        self.apply_repo_path()

    def apply_repo_path(self) -> None:
        raw_input = self.repo_entry_var.get().strip()
        if not raw_input:
            self.repo_selected = False
            self.refresh_ref_label()
            self.status_var.set(self.t("status_repo_needed"))
            self.set_compact_status(self.t("status_repo_needed"))
            self.update_repo_dependent_controls()
            self.save_settings()
            return
        path = Path(raw_input).expanduser()
        if not path.exists():
            self.show_error(self.t("error_repo_missing"))
            return
        repo = self.resolve_valid_repo(path)
        if repo is None:
            self.show_error(self.t("error_repo_invalid"))
            return
        if self.repo_selected and repo == self.repo:
            self.repo_entry_var.set(str(self.repo))
            return
        self.repo = repo
        self.repo_selected = True
        self.repo_entry_var.set(str(self.repo))
        self.ref = resolve_ref(self.repo, "auto")
        self.rebuild_author_controls(reset_invalid_to_auto=True)
        clear_cache_for_repo(self.repo)
        self.update_repo_dependent_controls()
        self.save_settings()
        self.refresh()

    def on_auto_refresh_toggle(self) -> None:
        if not self.repo_selected:
            self.auto_refresh_var.set(False)
            self.cancel_auto_refresh()
            self.status_var.set(self.t("status_repo_needed"))
            self.set_compact_status(self.t("status_repo_needed"))
            self.update_repo_dependent_controls()
            self.save_settings()
            return
        self.save_settings()
        if self.auto_refresh_var.get():
            self.refresh()
            return
        self.cancel_auto_refresh()
        self.status_var.set(self.t("status_auto_off"))
        self.set_compact_status(self.t("status_auto_off"))

    def schedule_auto_refresh(self) -> None:
        self.cancel_auto_refresh()
        self.auto_refresh_job = self.root.after(AUTO_REFRESH_MS, self.auto_refresh_tick)

    def cancel_auto_refresh(self) -> None:
        if self.auto_refresh_job is None:
            return
        self.root.after_cancel(self.auto_refresh_job)
        self.auto_refresh_job = None

    def auto_refresh_tick(self) -> None:
        self.auto_refresh_job = None
        if not self.auto_refresh_var.get():
            return
        self.refresh()

    def on_close(self) -> None:
        self.save_settings()
        self.cancel_auto_refresh()
        self.cancel_compact_clock()
        self.root.destroy()


def main() -> int:
    parser = make_parser()
    args = parser.parse_args()

    repo = find_repo_root(Path(args.repo))
    author = resolve_author(repo, args.author)
    ref = resolve_ref(repo, args.ref)
    config = TrackerConfig(
        repo=repo,
        goal=args.goal,
        base_total=args.base_total,
        base_commit=args.base_commit,
        author=author,
        ref=ref,
        include_local=True,
        today=args.today,
        month_end=args.month_end,
        assume_uncommitted_zero=False,
    )

    if args.once:
        result = compute_metrics(config)
        print("\n".join(format_output_lines(result)))
        return 0

    root = tk.Tk()
    LineTrackerApp(root, args)
    root.mainloop()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
