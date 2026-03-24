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
from line_tracker_version import format_app_title

AUTO_REFRESH_MS = 60_000
GRAPH_CANVAS_WIDTH = 420
GRAPH_CANVAS_HEIGHT = 140
BAR_LENGTH = 420
GRAPH_CARD_WIDTH = GRAPH_CANVAS_WIDTH + 24
NOTE_CARD_WIDTH = 420
NOTE_CARD_FIT_PADDING = 8
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
        "grass_uncommitted_legend": "미커밋(같은 구간)",
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
        "grass_uncommitted_legend": "Uncommitted (same bands)",
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
FONT_SUBTITLE = ("Bahnschrift", 10)
FONT_BODY = ("Bahnschrift", 10)
FONT_SECTION = ("Bahnschrift", 11, "bold")
FONT_TILE_LABEL = ("Bahnschrift", 9)
FONT_TILE_VALUE = ("Bahnschrift", 12, "bold")
FONT_CHIP = ("Bahnschrift", 9)
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
    legacy_note_title: str = ""
    legacy_note_items: object = None
    legacy_note_done: str = ""
    legacy_note_todo: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> UISettings:
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

    def _build_header(self, container: ttk.Frame) -> None:
        header_frame = ttk.Frame(container, style="App.TFrame")
        header_frame.grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 10))
        header_frame.columnconfigure(2, weight=1)
        self.header_accent_bar = tk.Frame(header_frame, bg=self.theme.accent, width=6, height=34)
        self.header_accent_bar.grid(row=0, column=0, rowspan=2, sticky="ns", padx=(0, 10))
        self.title_label = ttk.Label(header_frame, text=format_app_title(self.t("window_title")), style="Title.TLabel")
        self.title_label.grid(row=0, column=1, sticky="w")
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

        self.refresh_button = ttk.Button(footer_right, text=self.t("refresh"), command=self.refresh, style="Accent.TButton")
        self.refresh_button.grid(row=0, column=1, sticky="e")

        self.copy_button = ttk.Button(footer_right, text=self.t("copy"), command=self.copy_output)
        self.copy_button.grid(row=0, column=2, sticky="e", padx=(8, 0))

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
        self.title_label.configure(text=format_app_title(self.t("window_title")))
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
        self.refresh_button.configure(text=self.t("refresh"))
        self.copy_button.configure(text=self.t("copy"))
        self.apply_layout_for_language()

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
        self.style.configure("Title.TLabel", background=palette.app_bg, foreground=palette.text, font=FONT_TITLE)
        self.style.configure("Subtitle.TLabel", background=palette.app_bg, foreground=palette.muted_text, font=FONT_SUBTITLE)
        self.style.configure("Section.TLabel", background=palette.app_bg, foreground=palette.text, font=FONT_SECTION)
        self.style.configure("CardTitle.TLabel", background=palette.card_bg, foreground=palette.text, font=FONT_BODY)
        self.style.configure("CardLabel.TLabel", background=palette.card_bg, foreground=palette.muted_text, font=FONT_BODY)
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

    def set_loading_state(self, loading: bool) -> None:
        if loading:
            self.loading_var.set(self.t("loading"))
            self.loading_detail_var.set(self.t("loading_detail"))
            self.loading_detail_label.grid()
            self.loading_bar.grid()
            self.loading_bar.start(10)
            self.refresh_button.configure(state="disabled")
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
        self.status_var.set(self.t("status_updated", time=dt.datetime.now().strftime("%H:%M:%S")) + status_suffix)
        if self.auto_refresh_var.get():
            self.schedule_auto_refresh()

    def _on_refresh_error(self, request_id: int, error_message: str) -> None:
        if request_id != self.refresh_request_id:
            return

        self.refresh_in_progress = False
        self.set_loading_state(False)
        self.status_var.set(self.t("status_error"))
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
            self.update_repo_dependent_controls()
            self.save_settings()
            return
        self.save_settings()
        if self.auto_refresh_var.get():
            self.refresh()
            return
        self.cancel_auto_refresh()
        self.status_var.set(self.t("status_auto_off"))

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
