#!/usr/bin/env python3
from __future__ import annotations

import argparse
import calendar
import datetime as dt
import math
import os
import re
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from line_tracker_args import make_ui_parser, parse_date as parse_ui_date
from line_tracker_authors import (
    build_author_option_entries,
    parse_author_identity,
    parse_shortlog_identities,
)
from line_tracker_controller import RefreshCoordinator
from line_tracker_graph import (
    flatten_graph_points as flatten_graph_screen_points,
    smooth_graph_points as smooth_graph_screen_points,
    summarize_graph_values as summarize_graph_point_values,
)
from line_tracker_grass_panel import GrassPanel, GrassPanelBindings
from line_tracker_presenters import (
    build_progress_presentation,
    format_progress_percent as format_progress_percent_value,
)
from line_tracker_repository import resolve_valid_repo
from line_tracker_schedule import (
    DirectiveScheduleParser,
    load_schedule_document,
    make_portable_schedule_path,
    resolve_schedule_path,
)
from line_tracker_schedule_panel import SchedulePanel, SchedulePanelBindings
from line_tracker_scroll_panel import ScrollPanel
from line_tracker import (
    CommitChangeEntry,
    DEFAULT_AUTHOR,
    DEFAULT_BASE_COMMIT,
    DEFAULT_BASE_TOTAL,
    DEFAULT_GOAL,
    LANGUAGE_EXTENSION_GROUPS,
    TrackerConfig,
    TrackerResult,
    compute_metrics,
    format_output_lines,
    get_app_state_path,
    get_legacy_state_path,
    get_commit_change_entries,
    clear_cache_for_repo,
    find_repo_root,
    get_git_info,
    run_git,
    resolve_author,
    resolve_base_commit,
    resolve_current_ref,
    resolve_ref,
)
from line_tracker_theme import (
    ThemePalette,
    get_theme_names,
    get_theme_palette,
    resolve_theme_name,
)
from line_tracker_refresh import RefreshSnapshot
from line_tracker_settings import (
    COMPACT_WINDOW_ALPHA,
    COMPACT_WINDOW_ALPHA_MAX,
    COMPACT_WINDOW_ALPHA_MIN,
    GRAPH_CURVE_DEFAULT,
    SETTINGS_FILE_NAME,
    UISettings,
    load_ui_settings,
    save_ui_settings,
)
from line_tracker_ui_resources import (
    FONT_BODY,
    FONT_CHIP,
    FONT_COMPACT_BAR_VALUE,
    FONT_COMPACT_CLOCK,
    FONT_COMPACT_META,
    FONT_COMPACT_TOOL,
    FONT_COMPACT_VALUE,
    FONT_MONO,
    FONT_SECTION,
    FONT_SUBTITLE,
    FONT_TILE_LABEL,
    FONT_TILE_VALUE,
    FONT_TITLE,
    FONT_VERSION,
    LANG_DISPLAY,
    LANG_OPTIONS,
    TEXT,
    _hex_to_colorref,
    LayoutMetrics,
    build_layout_metrics,
    blend_hex,
    contrast_text_color,
)
from line_tracker_version import APP_VERSION, format_app_title

AUTO_REFRESH_MS = 60_000
SCHEDULE_POLL_MS = 1_500
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
COMPACT_LAUNCH_BUTTON_SIZE = 32
GRAPH_SETTINGS_BUTTON_SIZE = 28
APP_SETTINGS_BUTTON_SIZE = 32
CUSTOM_TITLEBAR_HEIGHT = 34
CARD_SCROLLBAR_STYLE = "Card.Vertical.TScrollbar"
FOOTER_LOADING_STYLE = "Loading.Horizontal.TProgressbar"
BASE_WINDOW_WIDTH = 1440
BASE_WINDOW_HEIGHT = 675
MIN_WINDOW_WIDTH = 1100
MIN_WINDOW_HEIGHT = 675
BASE_TILE_MIN_WIDTH = 250
BASE_TILE_LABEL_WRAP = 240
WINDOW_SCREEN_MARGIN = 80
WINDOW_FIT_SAFETY = 24
LEFT_PANEL_SCROLLBAR_ALLOWANCE = 18
GEOMETRY_RE = re.compile(r"^(?P<width>\d+)x(?P<height>\d+)(?:(?P<x>[+-]\d+)(?P<y>[+-]\d+))?$")
RESPONSIVE_REPO_ENTRY_WIDTH = 52
GRAPH_DAY_OPTIONS = ("7", "14", "21", "30", "60", "90", "180")
COMMIT_HISTORY_PAGE_SIZE = 20
PROGRESS_BAR_HEIGHT = 18
PROJECT_LANGUAGE_ORDER = tuple(language for language, _ in LANGUAGE_EXTENSION_GROUPS) + ("Other",)


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


def parse_date(value: str) -> dt.date:
    return parse_ui_date(value)

def make_parser() -> argparse.ArgumentParser:
    return make_ui_parser()


class LineTrackerApp:
    @staticmethod
    def resolve_valid_repo(path: Path) -> Path | None:
        return resolve_valid_repo(path)

    def __init__(self, root: tk.Tk, args: argparse.Namespace, *, capture_mode: bool = False) -> None:
        self.root = root
        self.capture_mode = capture_mode
        self.use_custom_titlebar = sys.platform == "win32"
        self.content_row = 1 if self.use_custom_titlebar else 0
        self.custom_titlebar_drag_x = 0
        self.custom_titlebar_drag_y = 0
        self.custom_titlebar_restore_pending = False
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
        self.screen_limit_width = max(640, self.root.winfo_screenwidth() - WINDOW_SCREEN_MARGIN - WINDOW_FIT_SAFETY)
        default_width = min(BASE_WINDOW_WIDTH, self.screen_limit_width)
        default_height = BASE_WINDOW_HEIGHT
        min_height = MIN_WINDOW_HEIGHT
        initial_min_width = min(MIN_WINDOW_WIDTH, self.screen_limit_width)
        default_geometry = f"{default_width}x{default_height}"
        saved_geometry = self.normalize_geometry(self.settings.geometry)
        self.last_window_geometry = saved_geometry or default_geometry
        self.root.geometry(self.last_window_geometry)
        self.root.minsize(initial_min_width, min_height)
        self.root.maxsize(self.screen_limit_width, self.root.winfo_screenheight())
        self.base_window_width = BASE_WINDOW_WIDTH
        self.min_height = min_height

        saved_goal = self._coerce_positive_int(self.settings.goal, self.goal)
        saved_graph_days = self.settings.graph_days
        if saved_graph_days not in GRAPH_DAY_OPTIONS:
            saved_graph_days = "14"
        saved_graph_show_additions = bool(self.settings.graph_show_additions if self.settings.graph_show_additions is not None else True)
        saved_graph_show_deletions = bool(self.settings.graph_show_deletions)
        saved_graph_show_commits = bool(self.settings.graph_show_commits)
        if not (saved_graph_show_additions or saved_graph_show_deletions or saved_graph_show_commits):
            saved_graph_show_additions = True
        try:
            saved_graph_curve = float(self.settings.graph_curve)
        except (TypeError, ValueError):
            saved_graph_curve = GRAPH_CURVE_DEFAULT
        saved_graph_curve = min(max(saved_graph_curve, 0.0), 100.0)
        saved_author = self.settings.author or args.author
        saved_author_display = self.settings.author_display
        saved_custom_today_enabled = bool(self.settings.custom_today_enabled if self.settings.custom_today_enabled is not None else bool(args.today))
        default_today_text = args.today.isoformat() if args.today else dt.date.today().isoformat()
        saved_today_text = self.settings.custom_today or default_today_text
        saved_auto_refresh = bool(self.settings.auto_refresh)
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
        if self.use_custom_titlebar:
            self.root.withdraw()
        self.root.columnconfigure(0, weight=1)
        if self.use_custom_titlebar:
            self.root.rowconfigure(0, weight=0)
            self.root.rowconfigure(1, weight=1)
            self.root.bind("<Map>", self.on_root_map, add="+")
        else:
            self.root.rowconfigure(0, weight=1)
        self.root.bind("<Configure>", self.on_root_configure)

        self.style = ttk.Style(self.root)
        self.app_settings_window: ttk.Frame | None = None
        self.app_settings_card: ttk.Frame | None = None
        self.app_settings_notebook: ttk.Notebook | None = None
        self.app_settings_button_state = "normal"
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass
        self.apply_color_palette()

        if self.use_custom_titlebar:
            self._build_custom_titlebar()

        container = ttk.Frame(self.root, padding=(14, 11), style="App.TFrame")
        container.grid(row=self.content_row, column=0, sticky="nsew")
        container.columnconfigure(0, weight=0)
        container.columnconfigure(1, weight=0)
        container.columnconfigure(2, weight=0)
        container.rowconfigure(1, weight=1)
        container.rowconfigure(2, weight=0)
        self.container = container

        self._initialize_runtime_state(
            args,
            saved_graph_show_additions,
            saved_graph_show_deletions,
            saved_graph_show_commits,
            saved_graph_curve,
            saved_custom_today_enabled,
            self.settings.note_tab,
        )
        self._build_header(container)
        self._build_stats_scroll_section(container)
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
        saved_graph_show_additions: bool,
        saved_graph_show_deletions: bool,
        saved_graph_show_commits: bool,
        saved_graph_curve: float,
        saved_custom_today_enabled: bool,
        saved_note_tab: str,
    ) -> None:
        self.auto_refresh_job: str | None = None
        self.schedule_poll_job: str | None = None
        self.refresh_request_id = 0
        self.refresh_in_progress = False
        self.refresh_coordinator = RefreshCoordinator(self.safe_after)
        self.today_override: dt.date | None = args.today if saved_custom_today_enabled else None
        initial_today = self.today_override or args.today or dt.date.today()
        self.meta_label_vars = [tk.StringVar(value="") for _ in range(2)]
        self.meta_value_vars = [tk.StringVar(value="") for _ in range(2)]
        self.title_date_var = tk.StringVar(value=initial_today.isoformat())
        self.tile_label_vars = [tk.StringVar(value="") for _ in range(8)]
        self.tile_value_vars = [tk.StringVar(value="") for _ in range(8)]
        self.daily_stats_added_var = tk.StringVar(value="+0")
        self.daily_stats_removed_var = tk.StringVar(value="-0")
        self.daily_stats_commit_var = tk.StringVar(value="0 commit")
        self.branch_stats_added_var = tk.StringVar(value="+0")
        self.branch_stats_removed_var = tk.StringVar(value="-0")
        self.branch_stats_commit_var = tk.StringVar(value="0 commit")
        self.overall_stats_added_var = tk.StringVar(value="+0")
        self.overall_stats_removed_var = tk.StringVar(value="-0")
        self.overall_stats_commit_var = tk.StringVar(value="0 commit")
        self.current_ref = resolve_current_ref(self.repo)
        self.main_total_committed = 0
        self.branch_total_committed = 0
        self.graph_points: list[tuple[dt.date, int]] = []
        self.graph_highlight_day: dt.date | None = None
        self.grass_panel_controller: GrassPanel | None = None
        self.schedule_panel_controller: SchedulePanel | None = None
        self.commit_history_entries: list[CommitChangeEntry] = []
        self.commit_history_loading = False
        self.commit_history_exhausted = False
        self.commit_history_generation = 0
        self.commit_history_refs = ("HEAD",)
        self.commit_history_exclude_ref = ""
        self.repo_entry_var = tk.StringVar(value=str(self.repo) if self.repo_selected else "")
        self.schedule_path = self.settings.schedule_path
        self.schedule_path_var = tk.StringVar(value=self.schedule_path)
        self.schedule_parser = DirectiveScheduleParser()
        self.schedule_signature: tuple[object, ...] | None = None
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
        self.graph_show_additions_var = tk.BooleanVar(value=saved_graph_show_additions)
        self.graph_show_deletions_var = tk.BooleanVar(value=saved_graph_show_deletions)
        self.graph_show_commits_var = tk.BooleanVar(value=saved_graph_show_commits)
        self.graph_curve_var = tk.DoubleVar(value=saved_graph_curve)
        self.graph_curve_text_var = tk.StringVar(value="")
        self.graph_settings_window: tk.Toplevel | None = None
        self.graph_settings_days_var: tk.StringVar | None = None
        self.graph_settings_show_additions_var: tk.BooleanVar | None = None
        self.graph_settings_show_deletions_var: tk.BooleanVar | None = None
        self.graph_settings_show_commits_var: tk.BooleanVar | None = None
        self.graph_settings_curve_var: tk.DoubleVar | None = None
        self.graph_settings_flags_frame: tk.Frame | None = None
        self.graph_settings_flag_buttons: dict[str, tk.Button] = {}
        self.graph_settings_range_label: ttk.Label | None = None
        self.graph_settings_metrics_label: ttk.Label | None = None
        self.graph_settings_curve_label: ttk.Label | None = None
        self.graph_settings_apply_button: ttk.Button | None = None
        self.graph_settings_curve_value_label: ttk.Label | None = None
        self.graph_settings_days_combo: ttk.Combobox | None = None
        self.graph_settings_curve_scale: tk.Scale | None = None
        self.base_required_width = 0
        self.layout_scale = 1.0
        self.layout_metrics = build_layout_metrics(self.layout_scale)
        self.graph_canvas_width = GRAPH_CANVAS_WIDTH
        self.progress_bar_length = BAR_LENGTH
        self.tile_min_width = BASE_TILE_MIN_WIDTH
        self.tile_wrap = BASE_TILE_LABEL_WRAP
        self.repo_entry_width = RESPONSIVE_REPO_ENTRY_WIDTH
        self.graph_added_points: list[tuple[dt.date, int]] = []
        self.active_note_tab = saved_note_tab if saved_note_tab in {"schedule", "grass"} else "schedule"
        self.progress_language_lines: dict[str, dict[str, int]] = {"overall": {}, "daily": {}}
        self.progress_bar_segments: dict[str, list[tuple[int, int, str]]] = {"overall": [], "daily": []}
        self.progress_bar_percents: dict[str, float] = {"overall": 0.0, "daily": 0.0}
        self.progress_bar_texts: dict[str, str] = {"overall": "", "daily": ""}
        self.progress_language_tooltip: tk.Toplevel | None = None
        self.progress_language_hover_key = ""
        self.graph_deleted_points: list[tuple[dt.date, int]] = []
        self.graph_commit_points: list[tuple[dt.date, int]] = []

    def _build_custom_titlebar(self) -> None:
        titlebar = ttk.Frame(self.root, style="TitleBar.TFrame", height=CUSTOM_TITLEBAR_HEIGHT, padding=(10, 6))
        titlebar.grid(row=0, column=0, sticky="ew")
        titlebar.grid_propagate(False)
        titlebar.columnconfigure(1, weight=1)
        self.custom_titlebar = titlebar

        self.custom_titlebar_accent = tk.Frame(titlebar, bg=self.theme.accent, width=4, height=16)
        self.custom_titlebar_accent.grid(row=0, column=0, sticky="nsw", padx=(0, 8))

        titlebar_left = ttk.Frame(titlebar, style="TitleBar.TFrame")
        titlebar_left.grid(row=0, column=1, sticky="w")
        self.custom_titlebar_left = titlebar_left

        self.custom_titlebar_title = ttk.Label(titlebar_left, text=format_app_title(self.t("window_title")), style="TitleBar.TLabel")
        self.custom_titlebar_title.grid(row=0, column=0, sticky="w")

        self.custom_titlebar_subtitle = ttk.Label(titlebar_left, text=APP_VERSION, style="TitleBarMeta.TLabel")
        self.custom_titlebar_subtitle.grid(row=0, column=1, sticky="w", padx=(8, 0))

        titlebar_actions = ttk.Frame(titlebar, style="TitleBar.TFrame")
        titlebar_actions.grid(row=0, column=2, sticky="e")
        self.custom_titlebar_actions = titlebar_actions

        self.titlebar_minimize_button = ttk.Button(
            titlebar_actions,
            text="_",
            command=self.minimize_main_window,
            style="TitleBarButton.TButton",
            width=3,
        )
        self.titlebar_minimize_button.grid(row=0, column=0, sticky="e")

        self.titlebar_close_button = ttk.Button(
            titlebar_actions,
            text="X",
            command=self.on_close,
            style="TitleBarClose.TButton",
            width=3,
        )
        self.titlebar_close_button.grid(row=0, column=1, sticky="e", padx=(6, 0))

        for widget in (
            titlebar,
            titlebar_left,
            self.custom_titlebar_title,
            self.custom_titlebar_subtitle,
            self.custom_titlebar_accent,
        ):
            self._bind_titlebar_drag(widget)

    def _bind_titlebar_drag(self, widget: tk.Misc) -> None:
        widget.bind("<ButtonPress-1>", self.on_titlebar_drag_start, add="+")
        widget.bind("<B1-Motion>", self.on_titlebar_drag_motion, add="+")

    def _build_header(self, container: ttk.Frame) -> None:
        m = self.layout_metrics
        header_frame = ttk.Frame(container, style="App.TFrame")
        header_frame.grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, m.header_gap))
        header_frame.columnconfigure(1, weight=1)
        header_frame.columnconfigure(2, weight=1)
        self.header_frame = header_frame
        self.header_accent_bar = tk.Frame(header_frame, bg=self.theme.accent, width=6, height=34)
        self.header_accent_bar.grid(row=0, column=0, rowspan=2, sticky="ns", padx=(0, m.header_group_gap))
        title_row = ttk.Frame(header_frame, style="App.TFrame")
        title_row.grid(row=0, column=1, sticky="w")
        self.title_label = ttk.Label(title_row, text=self.get_header_project_title(), style="Title.TLabel")
        self.title_label.grid(row=0, column=0, sticky="w")
        self.title_date_label = ttk.Label(title_row, textvariable=self.title_date_var, style="Subtitle.TLabel")
        self.title_date_label.grid(row=0, column=1, sticky="w", padx=(m.header_group_gap, 0), pady=(3, 0))
        self.subtitle_label = ttk.Label(
            header_frame,
            text=self.format_ref_label(),
            style="Subtitle.TLabel",
        )
        self.subtitle_label.grid(row=1, column=1, sticky="w", pady=(m.header_subtitle_gap, 0))

        right_header = ttk.Frame(header_frame, style="App.TFrame")
        right_header.grid(row=0, column=2, rowspan=2, sticky="e")
        self.right_header = right_header

        self.app_settings_button = tk.Canvas(
            right_header,
            width=APP_SETTINGS_BUTTON_SIZE,
            height=APP_SETTINGS_BUTTON_SIZE,
            highlightthickness=0,
            bd=0,
            relief="flat",
            cursor="hand2",
            takefocus=1,
        )
        self.app_settings_button.grid(row=0, column=0, rowspan=2, sticky="e")
        self.app_settings_button.bind("<Enter>", lambda _: self.set_app_settings_button_state("hover"))
        self.app_settings_button.bind("<Leave>", lambda _: self.set_app_settings_button_state("normal"))
        self.app_settings_button.bind("<ButtonPress-1>", lambda _: self.set_app_settings_button_state("pressed"))
        self.app_settings_button.bind("<ButtonRelease-1>", self.on_app_settings_button_release)
        self.app_settings_button.bind("<Return>", self.on_app_settings_button_keypress)
        self.app_settings_button.bind("<space>", self.on_app_settings_button_keypress)
        self.redraw_app_settings_button()

    def _build_stats_scroll_section(self, container: ttk.Frame) -> None:
        m = self.layout_metrics
        stats_scroll_panel = ScrollPanel(
            container,
            canvas_bg=self.theme.app_bg,
            scrollbar_style=CARD_SCROLLBAR_STYLE,
        )
        stats_scroll_host = stats_scroll_panel.build()
        stats_scroll_host.grid(row=1, column=0, sticky="nsew", padx=(0, m.header_group_gap))
        self.stats_scroll_panel = stats_scroll_panel
        self.stats_scroll_host = stats_scroll_host
        self.stats_canvas = stats_scroll_panel.canvas
        self.stats_scrollbar = stats_scroll_panel.scrollbar
        self.stats_container = stats_scroll_panel.content
        self.stats_canvas_window = stats_scroll_panel.canvas_window
        if self.stats_canvas is not None:
            self.stats_canvas.configure(height=1)

        if self.stats_container is not None:
            self._build_output_section(self.stats_container)
            self.stats_scroll_panel.bind_content_tree()
            self.stats_scroll_panel.update_scroll_region()

    def _build_output_section(self, container: ttk.Frame) -> None:
        m = self.layout_metrics
        output_section = ttk.Frame(container, style="App.TFrame")
        output_section.grid(row=0, column=0, sticky="ew")
        output_section.columnconfigure(0, weight=1)
        self.output_section = output_section

        tile_min_width = BASE_TILE_MIN_WIDTH
        tile_accents = self.theme.tile_accents
        self.tile_label_widgets: list[ttk.Label] = []
        self.tile_accent_widgets: list[tk.Frame] = []
        self.tile_grids: list[ttk.Frame] = []
        tile_wrap = BASE_TILE_LABEL_WRAP

        daily_stats_section = ttk.Frame(output_section, style="App.TFrame")
        daily_stats_section.grid(row=0, column=0, sticky="ew")
        self.daily_stats_section = daily_stats_section
        daily_stats_header = ttk.Frame(daily_stats_section, style="App.TFrame")
        daily_stats_header.grid(row=0, column=0, sticky="w", pady=(0, m.section_title_gap))
        self.daily_stats_header = daily_stats_header

        self.daily_stats_label = ttk.Label(
            daily_stats_header,
            text=self.t("daily_stats_section"),
            style="Section.TLabel",
        )
        self.daily_stats_label.grid(row=0, column=0, sticky="w")

        self.daily_stats_added_label = ttk.Label(
            daily_stats_header,
            textvariable=self.daily_stats_added_var,
            style="SectionDeltaAdd.TLabel",
        )
        self.daily_stats_added_label.grid(row=0, column=1, sticky="w", padx=(10, 0))

        self.daily_stats_removed_label = ttk.Label(
            daily_stats_header,
            textvariable=self.daily_stats_removed_var,
            style="SectionDeltaRemove.TLabel",
        )
        self.daily_stats_removed_label.grid(row=0, column=2, sticky="w", padx=(8, 0))

        self.daily_stats_commit_label = ttk.Label(
            daily_stats_header,
            textvariable=self.daily_stats_commit_var,
            style="SectionCommit.TLabel",
        )
        self.daily_stats_commit_label.grid(row=0, column=3, sticky="w", padx=(10, 0))

        self.daily_tile_grid = ttk.Frame(daily_stats_section, style="App.TFrame")
        self.daily_tile_grid.grid(row=1, column=0, sticky="ew")
        self.daily_tile_grid.columnconfigure(0, weight=1, uniform="tile", minsize=tile_min_width)
        self.daily_tile_grid.columnconfigure(1, weight=1, uniform="tile", minsize=tile_min_width)
        self.tile_grids.append(self.daily_tile_grid)

        daily_tile_positions = {
            0: (0, 0, 1),
            1: (0, 1, 1),
        }
        for idx in (0, 1):
            row, col, colspan = daily_tile_positions[idx]
            self._build_summary_tile(self.daily_tile_grid, idx, row, col, colspan, tile_wrap, tile_accents)

        lower_stats_stack = ttk.Frame(output_section, style="App.TFrame")
        lower_stats_stack.grid(row=1, column=0, sticky="ew", pady=(m.section_gap, 0))
        lower_stats_stack.columnconfigure(0, weight=1)
        self.lower_stats_stack = lower_stats_stack

        branch_stats_section = ttk.Frame(lower_stats_stack, style="App.TFrame")
        branch_stats_section.grid(row=0, column=0, sticky="ew")
        self.branch_stats_section = branch_stats_section
        branch_stats_header = ttk.Frame(branch_stats_section, style="App.TFrame")
        branch_stats_header.grid(row=0, column=0, sticky="w", pady=(0, m.section_title_gap))
        self.branch_stats_header = branch_stats_header

        self.branch_stats_label = ttk.Label(
            branch_stats_header,
            text=self.t("branch_stats_section"),
            style="Section.TLabel",
        )
        self.branch_stats_label.grid(row=0, column=0, sticky="w")

        self.branch_stats_added_label = ttk.Label(
            branch_stats_header,
            textvariable=self.branch_stats_added_var,
            style="SectionDeltaAdd.TLabel",
        )
        self.branch_stats_added_label.grid(row=0, column=1, sticky="w", padx=(10, 0))

        self.branch_stats_removed_label = ttk.Label(
            branch_stats_header,
            textvariable=self.branch_stats_removed_var,
            style="SectionDeltaRemove.TLabel",
        )
        self.branch_stats_removed_label.grid(row=0, column=2, sticky="w", padx=(8, 0))

        self.branch_stats_commit_label = ttk.Label(
            branch_stats_header,
            textvariable=self.branch_stats_commit_var,
            style="SectionCommit.TLabel",
        )
        self.branch_stats_commit_label.grid(row=0, column=3, sticky="w", padx=(10, 0))

        self.branch_tile_grid = ttk.Frame(branch_stats_section, style="App.TFrame")
        self.branch_tile_grid.grid(row=1, column=0, sticky="ew")
        self.branch_tile_grid.columnconfigure(0, weight=1, uniform="tile", minsize=tile_min_width)
        self.branch_tile_grid.columnconfigure(1, weight=1, uniform="tile", minsize=tile_min_width)
        self.tile_grids.append(self.branch_tile_grid)

        branch_tile_positions = {
            2: (0, 0, 1),
            3: (0, 1, 1),
        }
        for idx in (2, 3):
            row, col, colspan = branch_tile_positions[idx]
            self._build_summary_tile(self.branch_tile_grid, idx, row, col, colspan, tile_wrap, tile_accents)

        overall_stats_section = ttk.Frame(lower_stats_stack, style="App.TFrame")
        overall_stats_section.grid(row=1, column=0, sticky="ew", pady=(m.section_gap, 0))
        self.overall_stats_section = overall_stats_section
        overall_stats_header = ttk.Frame(overall_stats_section, style="App.TFrame")
        overall_stats_header.grid(row=0, column=0, sticky="w", pady=(0, m.section_title_gap))
        self.overall_stats_header = overall_stats_header

        self.overall_stats_label = ttk.Label(
            overall_stats_header,
            text=self.t("overall_stats_section"),
            style="Section.TLabel",
        )
        self.overall_stats_label.grid(row=0, column=0, sticky="w")

        self.overall_stats_added_label = ttk.Label(
            overall_stats_header,
            textvariable=self.overall_stats_added_var,
            style="SectionDeltaAdd.TLabel",
        )
        self.overall_stats_added_label.grid(row=0, column=1, sticky="w", padx=(10, 0))

        self.overall_stats_removed_label = ttk.Label(
            overall_stats_header,
            textvariable=self.overall_stats_removed_var,
            style="SectionDeltaRemove.TLabel",
        )
        self.overall_stats_removed_label.grid(row=0, column=2, sticky="w", padx=(8, 0))

        self.overall_stats_commit_label = ttk.Label(
            overall_stats_header,
            textvariable=self.overall_stats_commit_var,
            style="SectionCommit.TLabel",
        )
        self.overall_stats_commit_label.grid(row=0, column=3, sticky="w", padx=(10, 0))

        self.overall_tile_grid = ttk.Frame(overall_stats_section, style="App.TFrame")
        self.overall_tile_grid.grid(row=1, column=0, sticky="ew")
        self.overall_tile_grid.columnconfigure(0, weight=1, uniform="tile", minsize=tile_min_width)
        self.overall_tile_grid.columnconfigure(1, weight=1, uniform="tile", minsize=tile_min_width)
        self.tile_grids.append(self.overall_tile_grid)

        overall_tile_positions = {
            4: (0, 0, 1),
            5: (0, 1, 1),
        }
        for idx in (4, 5):
            row, col, colspan = overall_tile_positions[idx]
            tile = self._build_summary_tile(self.overall_tile_grid, idx, row, col, colspan, tile_wrap, tile_accents)
            tile.grid_configure(pady=(0, 0))

        user_stats_section = ttk.Frame(lower_stats_stack, style="App.TFrame")
        user_stats_section.grid(row=2, column=0, sticky="ew", pady=(m.section_gap, 0))
        self.user_stats_section = user_stats_section
        user_stats_header = ttk.Frame(user_stats_section, style="App.TFrame")
        user_stats_header.grid(row=0, column=0, sticky="w", pady=(0, m.section_title_gap))
        self.user_stats_header = user_stats_header

        self.user_stats_label = ttk.Label(
            user_stats_header,
            text=self.t("user_stats_section"),
            style="Section.TLabel",
        )
        self.user_stats_label.grid(row=0, column=0, sticky="w")

        self.user_tile_grid = ttk.Frame(user_stats_section, style="App.TFrame")
        self.user_tile_grid.grid(row=1, column=0, sticky="ew")
        self.user_tile_grid.columnconfigure(0, weight=1, uniform="tile", minsize=tile_min_width)
        self.user_tile_grid.columnconfigure(1, weight=1, uniform="tile", minsize=tile_min_width)
        self.tile_grids.append(self.user_tile_grid)

        user_tile_positions = {
            6: (0, 0, 1),
            7: (0, 1, 1),
        }
        for idx in (6, 7):
            row, col, colspan = user_tile_positions[idx]
            tile = self._build_summary_tile(self.user_tile_grid, idx, row, col, colspan, tile_wrap, tile_accents)
            tile.grid_configure(pady=(0, 0))

    def _build_summary_tile(
        self,
        parent: ttk.Frame,
        idx: int,
        row: int,
        col: int,
        colspan: int,
        tile_wrap: int,
        tile_accents: tuple[str, ...] | list[str],
    ) -> ttk.Frame:
        m = self.layout_metrics
        tile = ttk.Frame(parent, style="Tile.TFrame", padding=(m.tile_pad_x, m.tile_pad_y))
        tile.grid(
            row=row,
            column=col,
            columnspan=colspan,
            sticky="ew",
            padx=(0, m.tile_gap_x) if col == 0 and colspan == 1 else (0, 0),
            pady=(0, m.tile_gap_y) if row == 0 else (0, 0),
        )
        tile.columnconfigure(1, weight=1)
        if not hasattr(self, "tile_frames"):
            self.tile_frames = []
        self.tile_frames.append(tile)

        accent_color = tile_accents[idx % len(tile_accents)] if tile_accents else self.theme.accent
        accent = tk.Frame(tile, bg=accent_color, width=4)
        accent.grid(row=0, column=0, rowspan=2, sticky="ns", padx=(0, m.tile_gap_x))
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
        value.grid(row=1, column=1, sticky="w", pady=(m.tile_value_gap, 0))
        return tile

    def _build_progress_section(self, container: ttk.Frame) -> None:
        m = self.layout_metrics
        progress_section = ttk.Frame(container, style="App.TFrame")
        progress_section.grid(row=2, column=0, sticky="ew", pady=(m.section_gap, 0))
        progress_section.columnconfigure(0, weight=1)
        progress_section.rowconfigure(0, minsize=20)
        self.progress_section = progress_section

        self.progress_title = ttk.Label(progress_section, text=self.t("progress"), style="Section.TLabel")
        self.progress_title.grid(row=0, column=0, sticky="w", pady=(0, m.section_title_gap + 1))

        progress_card = ttk.Frame(progress_section, style="Card.TFrame", padding=(m.card_pad_x, m.card_pad_y))
        progress_card.grid(row=1, column=0, sticky="ew")
        progress_card.columnconfigure(0, weight=1)
        self.progress_card = progress_card

        self.overall_progress_title = ttk.Label(progress_card, text=self.t("overall_progress"), style="CardTitle.TLabel")
        self.overall_progress_title.grid(row=0, column=0, sticky="w")

        self.overall_progress_bar = tk.Canvas(
            progress_card,
            width=self.progress_bar_length,
            height=PROGRESS_BAR_HEIGHT,
            highlightthickness=0,
            bd=0,
            relief="flat",
            cursor="hand2",
        )
        self.overall_progress_bar.grid(row=1, column=0, sticky="ew", pady=(m.card_inner_gap, 0))
        self.overall_progress_bar.bind("<Configure>", lambda _: self.redraw_progress_bar("overall"))
        self.overall_progress_bar.bind("<Motion>", lambda event: self.on_progress_bar_motion(event, "overall"))
        self.overall_progress_bar.bind("<Leave>", lambda _: self.hide_progress_language_tooltip())

        self.overall_progress_text_var = tk.StringVar(value="")
        self.overall_progress_text_label = ttk.Label(
            progress_card,
            textvariable=self.overall_progress_text_var,
            style="CardLabel.TLabel",
        )
        self.overall_progress_text_label.grid(row=2, column=0, sticky="w", pady=(m.control_small_gap, 0))

        self.daily_progress_title = ttk.Label(progress_card, text=self.t("daily_progress"), style="CardTitle.TLabel")
        self.daily_progress_title.grid(row=3, column=0, sticky="w", pady=(m.progress_block_gap, 0))

        self.daily_progress_bar = tk.Canvas(
            progress_card,
            width=self.progress_bar_length,
            height=PROGRESS_BAR_HEIGHT,
            highlightthickness=0,
            bd=0,
            relief="flat",
            cursor="hand2",
        )
        self.daily_progress_bar.grid(row=4, column=0, sticky="ew", pady=(m.card_inner_gap, 2))
        self.daily_progress_bar.bind("<Configure>", lambda _: self.redraw_progress_bar("daily"))
        self.daily_progress_bar.bind("<Motion>", lambda event: self.on_progress_bar_motion(event, "daily"))
        self.daily_progress_bar.bind("<Leave>", lambda _: self.hide_progress_language_tooltip())

    def update_left_panel_width(self) -> None:
        m = self.layout_metrics
        stats_content_width = max(
            (self.tile_min_width * 2) + m.tile_gap_x,
            self.progress_bar_length + (m.card_pad_x * 2),
        )
        host_width = stats_content_width + LEFT_PANEL_SCROLLBAR_ALLOWANCE

        if hasattr(self, "container"):
            self.container.columnconfigure(0, minsize=host_width)
        stats_scroll_panel = getattr(self, "stats_scroll_panel", None)
        if stats_scroll_panel is not None:
            stats_scroll_panel.configure_width(stats_content_width)
            stats_scroll_panel.update_scroll_region()
        if hasattr(self, "output_section"):
            self.output_section.columnconfigure(0, minsize=stats_content_width)

    def _build_commit_history_section(self, right_area: ttk.Frame) -> None:
        m = self.layout_metrics
        commit_history_section = ttk.Frame(right_area, style="App.TFrame")
        commit_history_section.grid(row=1, column=0, sticky="new", padx=(0, m.header_group_gap), pady=(m.section_gap, 0))
        commit_history_section.columnconfigure(0, weight=1, minsize=GRAPH_CARD_WIDTH)
        self.commit_history_section = commit_history_section

        self.commit_history_title = ttk.Label(
            commit_history_section,
            text=self.t("commit_history_section"),
            style="Section.TLabel",
        )
        self.commit_history_title.grid(row=0, column=0, sticky="w", pady=(0, m.section_title_gap + 1))

        commit_history_card = ttk.Frame(commit_history_section, style="Card.TFrame", padding=(m.card_pad_x, m.card_pad_y))
        commit_history_card.grid(row=1, column=0, sticky="ew")
        commit_history_card.columnconfigure(0, weight=1)
        commit_history_card.rowconfigure(0, weight=1)
        self.commit_history_card = commit_history_card

        commit_scroll_panel = ScrollPanel(
            commit_history_card,
            canvas_bg=self.theme.card_bg,
            scrollbar_style=CARD_SCROLLBAR_STYLE,
            content_style="CardInner.TFrame",
        )
        commit_scroll_host = commit_scroll_panel.build()
        commit_scroll_host.grid(row=0, column=0, sticky="nsew")
        self.commit_history_scroll_panel = commit_scroll_panel
        self.commit_history_scroll_panel.set_scroll_callback(self.on_commit_history_scroll)
        self.commit_history_scroll_host = commit_scroll_host
        self.commit_history_container = commit_scroll_panel.content
        if self.commit_history_container is not None:
            self.commit_history_container.columnconfigure(0, weight=1)
            commit_scroll_panel.bind_content_tree()

        self.update_commit_history([])

    def _build_right_panel(
        self,
        container: ttk.Frame,
        *,
        saved_graph_days: str,
        saved_custom_today_enabled: bool,
        saved_today_text: str,
        saved_auto_refresh: bool,
    ) -> None:
        m = self.layout_metrics
        right_area = ttk.Frame(container, style="App.TFrame")
        right_area.grid(row=1, column=2, rowspan=2, sticky="nw", padx=(m.panel_gap_x, 0))
        right_area.columnconfigure(0, weight=0, minsize=GRAPH_CARD_WIDTH)
        right_area.columnconfigure(1, weight=0, minsize=NOTE_CARD_WIDTH)
        self.right_area = right_area

        self._initialize_settings_vars(
            saved_custom_today_enabled=saved_custom_today_enabled,
            saved_today_text=saved_today_text,
            saved_auto_refresh=saved_auto_refresh,
        )
        self._build_graph_section(right_area, saved_graph_days)
        self._build_commit_history_section(right_area)
        self._build_grass_section(right_area)

    def _initialize_settings_vars(
        self,
        *,
        saved_custom_today_enabled: bool,
        saved_today_text: str,
        saved_auto_refresh: bool,
    ) -> None:
        self.custom_today_var = tk.BooleanVar(value=saved_custom_today_enabled)
        self.today_entry_var = tk.StringVar(value=saved_today_text)
        self.goal_entry_var = tk.StringVar(value=str(self.goal))
        self.author_entry_var = tk.StringVar(value=self.author_display)
        self.auto_refresh_var = tk.BooleanVar(value=saved_auto_refresh)

    def _build_graph_section(self, right_area: ttk.Frame, saved_graph_days: str) -> None:
        m = self.layout_metrics
        graph_section = ttk.Frame(right_area, style="App.TFrame")
        graph_section.grid(row=0, column=0, sticky="nw", padx=(0, m.header_group_gap))
        graph_section.columnconfigure(0, weight=1)
        self.graph_section = graph_section

        graph_header = ttk.Frame(graph_section, style="App.TFrame")
        graph_header.grid(row=0, column=0, sticky="ew", pady=(0, m.note_tab_gap))
        graph_header.columnconfigure(0, weight=1)
        self.graph_header = graph_header

        self.graph_title = ttk.Label(graph_header, text=self.t("graph_title"), style="Section.TLabel")
        self.graph_title.grid(row=0, column=0, sticky="w")

        self.graph_days_var = tk.StringVar(value=saved_graph_days)
        self.graph_settings_button_state = "normal"
        self.graph_settings_button = tk.Canvas(
            graph_header,
            width=GRAPH_SETTINGS_BUTTON_SIZE,
            height=GRAPH_SETTINGS_BUTTON_SIZE,
            highlightthickness=0,
            bd=0,
            relief="flat",
            cursor="hand2",
            takefocus=1,
        )
        self.graph_settings_button.grid(row=0, column=1, sticky="e")
        self.graph_settings_button.bind("<Enter>", lambda _: self.set_graph_settings_button_state("hover"))
        self.graph_settings_button.bind("<Leave>", lambda _: self.set_graph_settings_button_state("normal"))
        self.graph_settings_button.bind("<ButtonPress-1>", lambda _: self.set_graph_settings_button_state("pressed"))
        self.graph_settings_button.bind("<ButtonRelease-1>", self.on_graph_settings_button_release)
        self.graph_settings_button.bind("<Return>", self.on_graph_settings_button_keypress)
        self.graph_settings_button.bind("<space>", self.on_graph_settings_button_keypress)
        self.redraw_graph_settings_button()

        graph_card = ttk.Frame(graph_section, style="Card.TFrame", padding=(m.card_pad_x, m.card_pad_y))
        graph_card.grid(row=1, column=0, sticky="ew")
        graph_card.columnconfigure(0, weight=1)
        self.graph_card = graph_card

        self.graph_canvas = tk.Canvas(
            graph_card,
            width=GRAPH_CANVAS_WIDTH,
            height=GRAPH_CANVAS_HEIGHT,
            bg=self.theme.canvas_bg,
            highlightthickness=1,
            highlightbackground=self.theme.border,
        )
        self.graph_canvas.grid(row=0, column=0, sticky="ew", pady=(max(1, m.tile_value_gap), 0))

        self.graph_summary_var = tk.StringVar(value="")
        self.graph_summary_label = ttk.Label(graph_card, textvariable=self.graph_summary_var, style="CardLabel.TLabel")
        self.graph_summary_label.grid(row=1, column=0, sticky="w", pady=(m.card_inner_gap, 0))

    def _build_grass_section(self, right_area: ttk.Frame) -> None:
        m = self.layout_metrics
        note_section = ttk.Frame(right_area, style="App.TFrame")
        note_section.grid(row=0, column=1, rowspan=2, sticky="nw", padx=(m.header_group_gap, 0))
        note_section.columnconfigure(0, weight=1, minsize=NOTE_CARD_WIDTH)
        self.note_section = note_section
        self.note_section_column = 0
        self.right_area = right_area
        self.right_area_note_column = 1

        note_tabs = ttk.Frame(note_section, style="App.TFrame")
        note_tabs.grid(row=0, column=0, sticky="w", pady=(0, m.note_tab_gap))
        note_tabs.columnconfigure(0, weight=0)
        note_tabs.columnconfigure(1, weight=0)
        self.note_tabs = note_tabs

        self.schedule_tab_button = ttk.Button(note_tabs, command=lambda: self.show_note_tab("schedule"))
        self.schedule_tab_button.grid(row=0, column=0, sticky="w")
        self.grass_tab_button = ttk.Button(note_tabs, command=lambda: self.show_note_tab("grass"))
        self.grass_tab_button.grid(row=0, column=1, sticky="w", padx=(m.note_tab_gap, 0))

        note_card = ttk.Frame(note_section, style="Card.TFrame", padding=(m.card_pad_x, m.card_pad_y))
        note_card.grid(row=1, column=0, sticky="ew")
        note_card.rowconfigure(0, weight=1)
        note_card.columnconfigure(0, weight=1)
        self.note_card = note_card

        self.schedule_panel = ttk.Frame(note_card, style="CardInner.TFrame")
        self.schedule_panel.grid(row=0, column=0, sticky="nsew")
        self.schedule_panel.columnconfigure(0, weight=1)

        self.grass_panel = ttk.Frame(note_card, style="CardInner.TFrame")
        self.grass_panel.grid(row=0, column=0, sticky="nsew")
        self.grass_panel.columnconfigure(0, weight=1)

        self.schedule_panel_controller = SchedulePanel(
            SchedulePanelBindings(
                translate=self.t,
                get_theme=lambda: self.theme,
                select_file=self.browse_schedule_file,
                reload=lambda: self.refresh_schedule(force=True),
                open_location=self.open_schedule_location,
            )
        )
        self.schedule_panel_controller.build(self.schedule_panel)

        self.grass_panel_controller = GrassPanel(
            GrassPanelBindings(
                translate=self.t,
                get_theme=lambda: self.theme,
                format_month_label=self.format_month_label,
            )
        )
        self.grass_panel_controller.build(self.grass_panel)
        self.grass_panel_controller.refresh()
        self.show_note_tab(self.active_note_tab, persist=False)
        self.freeze_note_panel_size()

    def _build_controls_section(
        self,
        right_area: ttk.Frame,
        *,
        saved_custom_today_enabled: bool,
        saved_today_text: str,
        saved_auto_refresh: bool,
    ) -> None:
        m = self.layout_metrics
        self.custom_today_var = tk.BooleanVar(value=saved_custom_today_enabled)
        self.today_entry_var = tk.StringVar(value=saved_today_text)
        controls_section = ttk.Frame(right_area, style="App.TFrame")
        controls_section.grid(row=1, column=0, sticky="ew", padx=(0, m.header_group_gap), pady=(0, 0))
        controls_section.columnconfigure(0, weight=1, minsize=GRAPH_CARD_WIDTH)
        self.controls_section = controls_section

        self.controls_title = ttk.Label(controls_section, text=self.t("settings"), style="Section.TLabel")
        self.controls_title.grid(row=0, column=0, sticky="w", pady=(0, m.section_title_gap + 1))

        controls_card = ttk.Frame(controls_section, style="Card.TFrame", padding=(m.card_pad_x, m.card_pad_y))
        controls_card.grid(row=1, column=0, sticky="ew")
        self.controls_card = controls_card

        self.custom_today_check = ttk.Checkbutton(
            controls_card,
            text=self.t("custom_date"),
            variable=self.custom_today_var,
            command=self.on_custom_date_toggle,
        )
        self.custom_today_check.grid(row=0, column=0, columnspan=3, sticky="w", pady=(m.control_large_gap, 0))
        controls_card.columnconfigure(0, weight=1)
        controls_card.columnconfigure(1, weight=0)

        self.today_entry = ttk.Entry(controls_card, textvariable=self.today_entry_var, width=14, style="Tracker.TEntry")
        self.today_entry.grid(row=1, column=0, sticky="ew", pady=(m.control_small_gap, 0))
        self.today_entry.bind("<Return>", self.on_today_entry_enter)

        self.today_apply_button = ttk.Button(controls_card, text=self.t("apply_date"), command=self.apply_custom_date)
        self.today_apply_button.grid(row=1, column=1, sticky="e", padx=(m.control_large_gap, 0), pady=(m.control_small_gap, 0))

        self.goal_entry_var = tk.StringVar(value=str(self.goal))
        self.goal_label = ttk.Label(controls_card, text=self.t("goal_label"), style="CardLabel.TLabel")
        self.goal_label.grid(row=2, column=0, sticky="w", pady=(m.control_large_gap, 0))

        self.goal_entry = ttk.Entry(controls_card, textvariable=self.goal_entry_var, width=14, style="Tracker.TEntry")
        self.goal_entry.grid(row=3, column=0, sticky="ew", pady=(m.control_small_gap, 0))
        self.goal_entry.bind("<Return>", self.on_goal_entry_enter)

        self.goal_apply_button = ttk.Button(controls_card, text=self.t("apply_goal"), command=self.apply_goal)
        self.goal_apply_button.grid(row=3, column=1, sticky="e", padx=(m.control_large_gap, 0), pady=(m.control_small_gap, 0))

        self.author_entry_var = tk.StringVar(value=self.author_display)
        self.author_label = ttk.Label(controls_card, text=self.t("author_label"), style="CardLabel.TLabel")
        self.author_label.grid(row=4, column=0, sticky="w", pady=(m.control_large_gap, 0))

        self.author_combo = ttk.Combobox(
            controls_card,
            textvariable=self.author_entry_var,
            values=self.author_options,
            width=22,
            style="Tracker.TCombobox",
        )
        self.author_combo.grid(row=5, column=0, sticky="ew", pady=(m.control_small_gap, 0))
        self.author_combo.bind("<Return>", self.on_author_entry_enter)
        self.author_combo.bind("<<ComboboxSelected>>", self.on_author_select)
        self._bind_combobox_text_selection_clear(self.author_combo)

        self.author_apply_button = ttk.Button(controls_card, text=self.t("apply_author"), command=self.apply_author)
        self.author_apply_button.grid(row=5, column=1, sticky="e", padx=(m.control_large_gap, 0), pady=(m.control_small_gap, 0))

        self.auto_refresh_var = tk.BooleanVar(value=saved_auto_refresh)
        self.auto_refresh_check = ttk.Checkbutton(
            controls_card,
            text=self.t("auto_refresh"),
            variable=self.auto_refresh_var,
            command=self.on_auto_refresh_toggle,
        )
        self.auto_refresh_check.grid(row=6, column=0, columnspan=3, sticky="w", pady=(m.control_large_gap, 0))

    def _build_footer(self, container: ttk.Frame) -> None:
        m = self.layout_metrics
        footer_frame = ttk.Frame(container, style="App.TFrame")
        footer_frame.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(m.footer_gap, 0))
        footer_frame.columnconfigure(0, weight=1)
        footer_frame.columnconfigure(1, weight=0)
        self.footer_frame = footer_frame

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
        self.loading_label.grid(row=1, column=0, sticky="w", pady=(m.section_gap, 0))
        self.loading_bar.grid(row=1, column=1, sticky="w", padx=(m.section_gap, 0), pady=(m.section_gap, 0))
        self.loading_bar.grid_remove()

        self.loading_detail_var = tk.StringVar(value="")
        self.loading_detail_label = ttk.Label(footer_right, textvariable=self.loading_detail_var, style="Muted.TLabel")
        self.loading_detail_label.grid(row=0, column=0, sticky="e", padx=(0, m.header_group_gap))
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
        self.refresh_button.grid(row=0, column=2, sticky="e", padx=(m.tile_gap_x, 0))

        self.copy_button = ttk.Button(footer_right, text=self.t("copy"), command=self.copy_output)
        self.copy_button.grid(row=0, column=3, sticky="e", padx=(m.tile_gap_x, 0))

    def _build_compact_container(self) -> None:
        self.compact_container = ttk.Frame(self.root, padding=0, style="App.TFrame")
        self.compact_container.grid(row=self.content_row, column=0, sticky="nsew")
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

        self.compact_mode_button = ttk.Button(
            compact_actions,
            text=self.t("compact_mode_to_strip"),
            command=self.toggle_compact_variant,
            style="CompactTool.TButton",
        )
        self.compact_mode_button.grid(row=0, column=2, sticky="e", padx=(6, 0))

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

        self.compact_added_box = ttk.Frame(compact_delta_values, style="CardInner.TFrame", padding=(0, 0))
        self.compact_added_box.grid(row=0, column=0, sticky="w")

        self.compact_added_label = ttk.Label(
            self.compact_added_box,
            textvariable=self.compact_added_var,
            style="Stat.TLabel",
        )
        self.compact_added_label.grid(row=0, column=0, sticky="w")

        self.compact_removed_box = ttk.Frame(compact_delta_values, style="CardInner.TFrame", padding=(0, 0))
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
        self.compact_opacity_scale.grid(row=0, column=0, sticky="e")

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
        self.install_background_focus_clear_bindings()
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
        self.enable_main_window_chrome()
        self.show_main_window()
        self.refresh_schedule(force=True)
        self.start_schedule_poll()
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

    def get_header_project_title(self) -> str:
        if self.repo_selected:
            return self.repo.name
        return self.t("window_title")

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

    def current_schedule_today(self) -> dt.date:
        return self.today_override or dt.date.today()

    def browse_schedule_file(self) -> None:
        try:
            resolved = resolve_schedule_path(self.repo, self.schedule_path)
        except (OSError, ValueError):
            resolved = None
        start_dir = resolved.parent if resolved is not None else self.repo
        selected = filedialog.askopenfilename(
            title=self.t("schedule_dialog_title"),
            initialdir=str(start_dir) if start_dir.exists() else None,
            filetypes=(("Markdown", "*.md"), ("All files", "*.*")),
        )
        if not selected:
            return
        selected_path = Path(selected)
        if selected_path.suffix.casefold() != ".md":
            self.show_error(self.t("schedule_error_extension"))
            return
        self.schedule_path = make_portable_schedule_path(self.repo, selected_path)
        self.schedule_path_var.set(self.schedule_path)
        self.schedule_signature = None
        self.save_settings()
        self.refresh_schedule(force=True)

    def apply_schedule_path(self) -> None:
        configured_path = self.schedule_path_var.get().strip()
        if configured_path and Path(configured_path).suffix.casefold() != ".md":
            self.show_error(self.t("schedule_error_extension"))
            return
        try:
            resolved = resolve_schedule_path(self.repo, configured_path)
        except (OSError, ValueError):
            self.show_error(self.t("schedule_error_missing"))
            return
        if configured_path and (resolved is None or not resolved.is_file()):
            self.show_error(self.t("schedule_error_missing"))
            return
        self.schedule_path = configured_path
        self.schedule_signature = None
        self.save_settings()
        self.refresh_schedule(force=True)

    def open_schedule_location(self) -> None:
        try:
            source_path = resolve_schedule_path(self.repo, self.schedule_path)
        except (OSError, ValueError):
            source_path = None
        if source_path is None:
            self.show_error(self.t("schedule_error_missing"))
            return
        folder = source_path.parent
        if not folder.is_dir():
            self.show_error(self.t("schedule_error_missing"))
            return
        try:
            os.startfile(str(folder))
        except OSError:
            self.show_error(self.t("schedule_error_open_location"))

    def refresh_schedule(self, *, force: bool = False) -> None:
        controller = self.schedule_panel_controller
        if controller is None:
            return
        try:
            source_path = resolve_schedule_path(self.repo, self.schedule_path)
        except (OSError, ValueError) as exc:
            signature = ("path-error", self.schedule_path, str(exc))
            if not force and signature == self.schedule_signature:
                return
            self.schedule_signature = signature
            controller.show_error(None, str(exc))
            return
        if source_path is None:
            signature = ("unconfigured",)
            if not force and signature == self.schedule_signature:
                return
            self.schedule_signature = signature
            controller.show_unconfigured()
            return
        try:
            stat = source_path.stat()
        except FileNotFoundError:
            signature = ("missing", str(source_path))
            if not force and signature == self.schedule_signature:
                return
            self.schedule_signature = signature
            controller.show_error(source_path, self.t("schedule_error_missing"))
            return
        except OSError as exc:
            signature = ("stat-error", str(source_path), str(exc))
            if not force and signature == self.schedule_signature:
                return
            self.schedule_signature = signature
            controller.show_error(source_path, str(exc))
            return

        signature = ("loaded", str(source_path), stat.st_mtime_ns, stat.st_size, self.current_schedule_today())
        if not force and signature == self.schedule_signature:
            return
        load_error_prefix = ("load-error", str(source_path), stat.st_mtime_ns, stat.st_size)
        if not force and self.schedule_signature is not None and self.schedule_signature[:4] == load_error_prefix:
            return
        try:
            document = load_schedule_document(source_path, self.schedule_parser)
        except (OSError, UnicodeError, ValueError) as exc:
            error_signature = ("load-error", *signature[1:4], str(exc))
            if not force and error_signature == self.schedule_signature:
                return
            self.schedule_signature = error_signature
            controller.show_error(source_path, str(exc))
            return
        self.schedule_signature = signature
        controller.show_document(document, self.current_schedule_today())
        self.freeze_note_panel_size()

    def start_schedule_poll(self) -> None:
        self.cancel_schedule_poll()
        self.schedule_poll_job = self.root.after(SCHEDULE_POLL_MS, self.schedule_poll_tick)

    def cancel_schedule_poll(self) -> None:
        if self.schedule_poll_job is None:
            return
        try:
            self.root.after_cancel(self.schedule_poll_job)
        except tk.TclError:
            pass
        self.schedule_poll_job = None

    def schedule_poll_tick(self) -> None:
        self.schedule_poll_job = None
        self.refresh_schedule()
        self.start_schedule_poll()

    def show_note_tab(self, tab_name: str, *, persist: bool = True) -> None:
        selected_tab = tab_name if tab_name in {"schedule", "grass"} else "schedule"
        self.active_note_tab = selected_tab
        if hasattr(self, "schedule_panel"):
            if selected_tab == "schedule":
                self.schedule_panel.grid()
                self.refresh_schedule()
            else:
                self.schedule_panel.grid_remove()
        if hasattr(self, "grass_panel"):
            if selected_tab == "grass":
                self.grass_panel.grid()
            else:
                self.grass_panel.grid_remove()
        if hasattr(self, "schedule_tab_button"):
            self.schedule_tab_button.configure(
                text=self.t("tab_schedule"),
                style="TabActive.TButton" if selected_tab == "schedule" else "Tab.TButton",
            )
        if hasattr(self, "grass_tab_button"):
            self.grass_tab_button.configure(
                text=self.t("tab_grass"),
                style="TabActive.TButton" if selected_tab == "grass" else "Tab.TButton",
            )
        if persist:
            self.save_settings()

    def _bind_combobox_text_selection_clear(self, widget: ttk.Combobox) -> None:
        widget.bind("<<ComboboxSelected>>", lambda event, target=widget: self._clear_combobox_text_selection(target), add="+")
        widget.bind("<FocusIn>", lambda event, target=widget: self._clear_combobox_text_selection(target), add="+")
        widget.bind("<ButtonRelease-1>", lambda event, target=widget: self._clear_combobox_text_selection(target), add="+")

    def _clear_combobox_text_selection(self, widget: ttk.Combobox) -> None:
        try:
            self.root.after_idle(lambda target=widget: target.selection_clear())
        except tk.TclError:
            return

    def resolve_selected_theme_name(self, selection: str) -> str:
        normalized = selection.strip()
        for theme_name in get_theme_names():
            if normalized == self.theme_display_label(theme_name):
                return theme_name
        return resolve_theme_name(normalized)

    def freeze_note_panel_size(self) -> None:
        if not hasattr(self, "note_card"):
            return
        self.root.update_idletasks()
        panel_width = max(
            int((NOTE_CARD_WIDTH - 24) * self.layout_scale),
            self.grass_panel.winfo_reqwidth(),
            self.schedule_panel.winfo_reqwidth() if hasattr(self, "schedule_panel") else 0,
        )
        panel_height = max(
            self.grass_panel.winfo_reqheight(),
            self.schedule_panel.winfo_reqheight() if hasattr(self, "schedule_panel") else 0,
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

    def project_language_color(self, language: str) -> str:
        palette = self.theme
        colors = (
            palette.accent,
            palette.accent_alt,
            palette.success,
            palette.accent_light,
            palette.accent_dark,
            palette.accent_alt_dark,
            blend_hex(palette.accent, palette.accent_alt, 0.5),
            blend_hex(palette.success, palette.accent_alt, 0.42),
            blend_hex(palette.accent_light, palette.danger, 0.34),
            palette.muted_text,
            blend_hex(palette.muted_text, palette.card_bg, 0.28),
        )
        try:
            color_index = PROJECT_LANGUAGE_ORDER.index(language)
        except ValueError:
            color_index = len(PROJECT_LANGUAGE_ORDER) - 1
        return colors[color_index % len(colors)]

    @staticmethod
    def project_language_extensions(language: str) -> str:
        for group_name, extensions in LANGUAGE_EXTENSION_GROUPS:
            if group_name == language:
                return ", ".join(sorted(extensions))
        return "*"

    def set_progress_language_lines(
        self,
        overall_lines: dict[str, int],
        daily_lines: dict[str, int],
    ) -> None:
        self.progress_language_lines = {
            "overall": {
                language: int(line_count)
                for language, line_count in overall_lines.items()
                if int(line_count) > 0
            },
            "daily": {
                language: int(line_count)
                for language, line_count in daily_lines.items()
                if int(line_count) > 0
            },
        }
        self.hide_progress_language_tooltip()

    def redraw_progress_bars(self) -> None:
        self.redraw_progress_bar("overall")
        self.redraw_progress_bar("daily")

    def redraw_progress_bar(self, bar_kind: str) -> None:
        canvas = getattr(self, f"{bar_kind}_progress_bar", None)
        if canvas is None:
            return
        try:
            width = max(2, int(canvas.winfo_width()))
            height = max(2, int(canvas.winfo_height()))
        except tk.TclError:
            return

        palette = self.theme
        trough_color = palette.overall_progress_trough if bar_kind == "overall" else palette.daily_progress_trough
        fallback_color = palette.accent if bar_kind == "overall" else palette.accent_alt
        canvas.configure(bg=palette.card_bg)
        canvas.delete("all")
        canvas.create_rectangle(0, 0, width - 1, height - 1, fill=trough_color, outline=palette.border)

        percent = min(max(self.progress_bar_percents.get(bar_kind, 0.0), 0.0), 100.0)
        inner_left = 1
        inner_right = max(inner_left, width - 1)
        inner_width = max(0, inner_right - inner_left)
        fill_right = inner_left + round(inner_width * percent / 100.0)
        language_lines = self.progress_language_lines.get(bar_kind, {})
        items = [
            (name, language_lines[name])
            for name in PROJECT_LANGUAGE_ORDER
            if language_lines.get(name, 0) > 0
        ]
        total = sum(value for _, value in items)
        segments: list[tuple[int, int, str]] = []

        if fill_right > inner_left and total > 0:
            cumulative = 0
            left = inner_left
            for index, (language, value) in enumerate(items):
                cumulative += value
                right = fill_right if index == len(items) - 1 else inner_left + round((cumulative / total) * (fill_right - inner_left))
                right = min(fill_right, max(left, right))
                if right <= left:
                    continue
                color = self.project_language_color(language)
                canvas.create_rectangle(left, 1, right, height - 1, fill=color, outline="")
                segments.append((left, right, language))
                left = right
        elif fill_right > inner_left:
            canvas.create_rectangle(inner_left, 1, fill_right, height - 1, fill=fallback_color, outline="")

        self.progress_bar_segments[bar_kind] = segments
        canvas.create_rectangle(0, 0, width - 1, height - 1, outline=palette.border)

        text_value = self.progress_bar_texts.get(bar_kind, "")
        if text_value:
            center_x = width // 2
            text_background = trough_color
            if inner_left <= center_x < fill_right:
                text_background = fallback_color
                for left, right, language in segments:
                    if left <= center_x < right:
                        text_background = self.project_language_color(language)
                        break
            canvas.create_text(
                width / 2,
                height / 2,
                text=text_value,
                fill=contrast_text_color(text_background),
                font=("Bahnschrift", 9, "bold"),
            )

    def on_progress_bar_motion(self, event: tk.Event, bar_kind: str) -> None:
        language = ""
        for left, right, segment_language in self.progress_bar_segments.get(bar_kind, []):
            if left <= event.x < right:
                language = segment_language
                break
        hover_key = f"{bar_kind}:{language}" if language else ""
        if hover_key == self.progress_language_hover_key:
            return
        if not language:
            self.hide_progress_language_tooltip()
            return
        self.show_progress_language_tooltip(event.widget, bar_kind, language)

    def show_progress_language_tooltip(self, widget: tk.Misc, bar_kind: str, language: str) -> None:
        language_lines = self.progress_language_lines.get(bar_kind, {})
        value = language_lines.get(language, 0)
        total = sum(language_lines.values())
        if value <= 0 or total <= 0:
            return

        self.hide_progress_language_tooltip()
        self.progress_language_hover_key = f"{bar_kind}:{language}"
        palette = self.theme
        tooltip = tk.Toplevel(self.root)
        tooltip.withdraw()
        tooltip.overrideredirect(True)
        try:
            tooltip.attributes("-topmost", True)
        except tk.TclError:
            pass
        tooltip.configure(bg=palette.border)
        self.progress_language_tooltip = tooltip

        card = tk.Frame(tooltip, bg=palette.card_bg, padx=10, pady=8)
        card.pack(padx=1, pady=1)
        scope = self.t("project_language_breakdown") if bar_kind == "overall" else self.t("daily_progress")
        title = tk.Label(
            card,
            text=f"{scope} · {language}",
            bg=palette.card_bg,
            fg=palette.text,
            font=("Bahnschrift", 10, "bold"),
            anchor="w",
        )
        title.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))

        swatch = tk.Frame(card, bg=self.project_language_color(language), width=9, height=28)
        swatch.grid(row=1, column=0, sticky="nsw", padx=(0, 8), pady=2)
        swatch.grid_propagate(False)
        percent = (value / total) * 100.0
        extensions = self.project_language_extensions(language)
        detail = tk.Label(
            card,
            text=f"{value:,}{self.t('lines_suffix')} ({percent:.1f}%)\n{extensions}",
            bg=palette.card_bg,
            fg=palette.text,
            justify="left",
            anchor="w",
            font=("Bahnschrift", 9),
        )
        detail.grid(row=1, column=1, sticky="w", pady=2)

        try:
            x_pos = widget.winfo_pointerx() + 12
            y_pos = widget.winfo_pointery() + 14
            tooltip.geometry(f"+{x_pos}+{y_pos}")
            tooltip.deiconify()
            tooltip.lift()
        except tk.TclError:
            self.hide_progress_language_tooltip()

    def hide_progress_language_tooltip(self) -> None:
        tooltip = getattr(self, "progress_language_tooltip", None)
        self.progress_language_tooltip = None
        self.progress_language_hover_key = ""
        if tooltip is not None:
            try:
                tooltip.destroy()
            except tk.TclError:
                pass

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

    def set_output_lines(
        self,
        result: TrackerResult,
        branch_total: int,
        branch_deletions: int,
        branch_active_days: int,
        overall_active_days: int,
        overall_deletions: int,
        uncommitted_deletions: int,
        daily_commit_count: int,
        branch_commit_count: int,
        overall_commit_count: int,
        project_total_lines: int,
        share_text: str,
        user_cumulative_lines: int,
        user_cumulative_deletions: int,
    ) -> None:
        self.title_date_var.set(result.today.isoformat())
        self.daily_stats_added_var.set(f"+{result.uncommitted_insertions:,}")
        self.daily_stats_removed_var.set(f"-{uncommitted_deletions:,}")
        self.daily_stats_commit_var.set(f"{daily_commit_count:,} commit")
        self.branch_stats_added_var.set(f"+{branch_total:,}")
        self.branch_stats_removed_var.set(f"-{branch_deletions:,}")
        self.branch_stats_commit_var.set(f"{branch_commit_count:,} commit")
        self.overall_stats_added_var.set(f"+{user_cumulative_lines:,}")
        self.overall_stats_removed_var.set(f"-{user_cumulative_deletions:,}")
        self.overall_stats_commit_var.set(f"{overall_commit_count:,} commit")

        branch_value = f"{branch_total:,}{self.t('lines_suffix')}" if branch_total is not None else ""
        tiles = [
            (self.t("daily_required_label"), f"{result.need_today}{self.t('per_day_suffix')}"),
            (self.t("after_commit_daily_label"), f"{result.need_after_commit}{self.t('per_day_suffix')}"),
            (self.t("branch_only_label"), branch_value),
            (self.t("branch_active_days_label"), f"{branch_active_days:,}{self.t('day_suffix')}"),
            (self.t("project_total_label"), f"{project_total_lines:,}{self.t('lines_suffix')}"),
            (self.t("share_label"), share_text),
            (self.t("user_total_label"), f"{user_cumulative_lines:,}{self.t('lines_suffix')}"),
            (self.t("user_active_days_label"), f"{overall_active_days:,}{self.t('day_suffix')}"),
        ]

        for idx in range(8):
            label, value = tiles[idx] if idx < len(tiles) else ("", "")
            if idx == 1 and not value:
                label = ""
            self.tile_label_vars[idx].set(label)
            self.tile_value_vars[idx].set(value)

    def apply_language(self) -> None:
        self.root.title(format_app_title(self.t("window_title")))
        self.hide_progress_language_tooltip()
        self.refresh_custom_titlebar()
        self.title_label.configure(text=self.get_header_project_title())
        self.title_date_label.grid_configure(padx=(self.layout_metrics.header_group_gap, 0))
        if hasattr(self, "lang_label"):
            self.lang_label.configure(text=self.t("lang_label"))
        if hasattr(self, "theme_label"):
            self.theme_label.configure(text=self.t("theme_label"))
        if hasattr(self, "repo_header_label"):
            self.repo_header_label.configure(text=self.t("repo_label"))
        if hasattr(self, "repo_apply_button"):
            self.repo_apply_button.configure(text=self.t("repo_select"))
        self.refresh_theme_selector()
        self.refresh_ref_label()
        self.redraw_app_settings_button()

        self.graph_title.configure(text=self.t("graph_title"))
        self.redraw_graph_settings_button()
        self.commit_history_title.configure(text=self.t("commit_history_section"))
        self.show_note_tab(self.active_note_tab, persist=False)
        self.daily_stats_label.configure(text=self.t("daily_stats_section"))
        self.branch_stats_label.configure(text=self.t("branch_stats_section"))
        self.overall_stats_label.configure(text=self.t("overall_stats_section"))
        self.user_stats_label.configure(text=self.t("user_stats_section"))
        if self.grass_panel_controller is not None:
            self.grass_panel_controller.apply_language()
        if self.schedule_panel_controller is not None:
            self.schedule_panel_controller.apply_language()
        self.freeze_note_panel_size()

        if hasattr(self, "controls_title"):
            self.controls_title.configure(text=self.t("settings"))
        if hasattr(self, "custom_today_check"):
            self.custom_today_check.configure(text=self.t("custom_date"))
        if hasattr(self, "today_apply_button"):
            self.today_apply_button.configure(text=self.t("apply_date"))
        if hasattr(self, "goal_label"):
            self.goal_label.configure(text=self.t("goal_label"))
        if hasattr(self, "goal_apply_button"):
            self.goal_apply_button.configure(text=self.t("apply_goal"))
        if hasattr(self, "author_label"):
            self.author_label.configure(text=self.t("author_label"))
        if hasattr(self, "author_apply_button"):
            self.author_apply_button.configure(text=self.t("apply_author"))
        if hasattr(self, "auto_refresh_check"):
            self.auto_refresh_check.configure(text=self.t("auto_refresh"))

        self.progress_title.configure(text=self.t("progress"))
        self.overall_progress_title.configure(text=self.t("overall_progress"))
        self.daily_progress_title.configure(text=self.t("daily_progress"))
        self.redraw_progress_bars()
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
        self.refresh_graph_settings_window()
        self.refresh_app_settings_window()
        self.redraw_graph()

        if self.refresh_in_progress:
            self.loading_var.set(self.t("loading"))
            self.loading_detail_var.set(self.t("loading_detail"))
            self.loading_detail_label.grid()
        else:
            self.loading_var.set(" ")
            self.loading_detail_var.set("")
            self.loading_detail_label.grid_remove()

    def refresh_custom_titlebar(self) -> None:
        if not getattr(self, "use_custom_titlebar", False):
            return
        if hasattr(self, "custom_titlebar_title"):
            self.custom_titlebar_title.configure(text=self.t("window_title"))
        if hasattr(self, "custom_titlebar_subtitle"):
            self.custom_titlebar_subtitle.configure(text=APP_VERSION)

    def minimize_main_window(self) -> None:
        if self.compact_mode:
            return
        self.save_settings()
        self.custom_titlebar_restore_pending = True
        if self.use_custom_titlebar and self._minimize_window_native():
            return
        try:
            self.root.iconify()
        except tk.TclError:
            pass

    def _minimize_window_native(self) -> bool:
        if not self.use_custom_titlebar:
            return False
        try:
            import ctypes
        except Exception:
            return False
        try:
            self.root.update_idletasks()
            user32 = ctypes.windll.user32
            hwnd = user32.GetAncestor(self.root.winfo_id(), 2)
        except Exception:
            return False
        if not hwnd:
            return False
        try:
            user32.ShowWindow(hwnd, 6)
        except Exception:
            return False
        return True

    def on_titlebar_drag_start(self, event: tk.Event) -> str | None:
        if not self.use_custom_titlebar or self.compact_mode:
            return None
        self.custom_titlebar_drag_x = event.x_root - self.root.winfo_x()
        self.custom_titlebar_drag_y = event.y_root - self.root.winfo_y()
        return "break"

    def on_titlebar_drag_motion(self, event: tk.Event) -> str | None:
        if not self.use_custom_titlebar or self.compact_mode:
            return None
        target_x = event.x_root - self.custom_titlebar_drag_x
        target_y = event.y_root - self.custom_titlebar_drag_y
        try:
            self.root.geometry(f"+{target_x}+{target_y}")
        except tk.TclError:
            return None
        return "break"

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
        self.apply_responsive_layout()
        tile_min_width = self.tile_min_width
        tile_wrap = self.tile_wrap
        for tile_grid in getattr(self, "tile_grids", []):
            tile_grid.columnconfigure(0, minsize=tile_min_width)
            tile_grid.columnconfigure(1, minsize=tile_min_width)
        for label in getattr(self, "tile_label_widgets", []):
            label.configure(wraplength=tile_wrap)
        self.freeze_note_panel_size()

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

    def refresh_layout_metrics(self) -> None:
        m = self.layout_metrics
        if hasattr(self, "header_frame"):
            self.header_frame.grid_configure(pady=(0, m.header_gap))
        if hasattr(self, "header_accent_bar"):
            self.header_accent_bar.grid_configure(padx=(0, m.header_group_gap))
        if hasattr(self, "subtitle_label"):
            self.subtitle_label.grid_configure(pady=(m.header_subtitle_gap, 0))
        if hasattr(self, "lang_header"):
            self.lang_header.grid_configure(padx=(0, m.header_group_gap))
        if hasattr(self, "theme_header"):
            self.theme_header.grid_configure(padx=(0, m.header_group_gap))
        if hasattr(self, "repo_apply_button"):
            self.repo_apply_button.grid_configure(padx=(m.control_large_gap, 0))
        if hasattr(self, "stats_scroll_host"):
            self.stats_scroll_host.grid_configure(padx=(0, m.header_group_gap))
        if hasattr(self, "output_section"):
            self.output_section.grid_configure(padx=(0, 0))
        if hasattr(self, "daily_stats_header"):
            self.daily_stats_header.grid_configure(pady=(0, m.section_title_gap))
        if hasattr(self, "lower_stats_stack"):
            self.lower_stats_stack.grid_configure(pady=(m.section_gap, 0))
        if hasattr(self, "branch_stats_header"):
            self.branch_stats_header.grid_configure(pady=(0, m.section_title_gap))
        if hasattr(self, "overall_stats_section"):
            self.overall_stats_section.grid_configure(pady=(m.section_gap, 0))
        if hasattr(self, "overall_stats_header"):
            self.overall_stats_header.grid_configure(pady=(0, m.section_title_gap))
        if hasattr(self, "user_stats_section"):
            self.user_stats_section.grid_configure(pady=(m.section_gap, 0))
        if hasattr(self, "user_stats_header"):
            self.user_stats_header.grid_configure(pady=(0, m.section_title_gap))
        for tile in getattr(self, "tile_frames", []):
            tile.configure(padding=(m.tile_pad_x, m.tile_pad_y))
            info = tile.grid_info()
            row = int(info.get("row", 0))
            col = int(info.get("column", 0))
            colspan = int(info.get("columnspan", 1))
            tile.grid_configure(
                padx=(0, m.tile_gap_x) if col == 0 and colspan == 1 else (0, 0),
                pady=(0, m.tile_gap_y) if row == 0 else (0, 0),
            )
        if hasattr(self, "progress_section"):
            self.progress_section.grid_configure(padx=(0, 0), pady=(m.section_gap, 0))
        if hasattr(self, "title_date_label"):
            self.title_date_label.grid_configure(padx=(m.header_group_gap, 0))
        if hasattr(self, "progress_title"):
            self.progress_title.grid_configure(pady=(0, m.section_title_gap + 1))
        if hasattr(self, "progress_card"):
            self.progress_card.configure(padding=(m.card_pad_x, m.card_pad_y))
        if hasattr(self, "overall_progress_bar"):
            self.overall_progress_bar.grid_configure(pady=(m.card_inner_gap, 0))
        if hasattr(self, "overall_progress_text_label"):
            self.overall_progress_text_label.grid_configure(pady=(m.control_small_gap, 0))
        if hasattr(self, "daily_progress_title"):
            self.daily_progress_title.grid_configure(pady=(m.progress_block_gap, 0))
        if hasattr(self, "daily_progress_bar"):
            self.daily_progress_bar.grid_configure(pady=(m.card_inner_gap, 2))
        if hasattr(self, "right_area"):
            self.right_area.grid_configure(padx=(m.panel_gap_x, 0))
        if hasattr(self, "commit_history_section"):
            self.commit_history_section.grid_configure(padx=(0, m.header_group_gap), pady=(m.section_gap, 0))
        if hasattr(self, "commit_history_title"):
            self.commit_history_title.grid_configure(pady=(0, m.section_title_gap + 1))
        if hasattr(self, "commit_history_card"):
            self.commit_history_card.configure(padding=(m.card_pad_x, m.card_pad_y))
        if hasattr(self, "graph_section"):
            self.graph_section.grid_configure(padx=(0, m.header_group_gap))
        if hasattr(self, "graph_header"):
            self.graph_header.grid_configure(pady=(0, m.note_tab_gap))
        if hasattr(self, "graph_card"):
            self.graph_card.configure(padding=(m.card_pad_x, m.card_pad_y))
        if hasattr(self, "graph_canvas"):
            self.graph_canvas.grid_configure(pady=(max(1, m.tile_value_gap), 0))
        if hasattr(self, "graph_summary_label"):
            self.graph_summary_label.grid_configure(pady=(m.card_inner_gap, 0))
        if hasattr(self, "note_section"):
            self.note_section.grid_configure(padx=(m.header_group_gap, 0))
        if hasattr(self, "note_tabs"):
            self.note_tabs.grid_configure(pady=(0, m.note_tab_gap))
        if hasattr(self, "grass_tab_button"):
            self.grass_tab_button.grid_configure(padx=(m.note_tab_gap, 0))
        if hasattr(self, "note_card"):
            self.note_card.configure(padding=(m.card_pad_x, m.card_pad_y))
        if hasattr(self, "controls_section"):
            self.controls_section.grid_configure(padx=(0, m.header_group_gap))
        if hasattr(self, "controls_title"):
            self.controls_title.grid_configure(pady=(0, m.section_title_gap + 1))
        if hasattr(self, "controls_card"):
            self.controls_card.configure(padding=(m.card_pad_x, m.card_pad_y))
        if hasattr(self, "custom_today_check"):
            self.custom_today_check.grid_configure(pady=(m.control_large_gap, 0))
        if hasattr(self, "today_entry"):
            self.today_entry.grid_configure(pady=(m.control_small_gap, 0))
        if hasattr(self, "today_apply_button"):
            self.today_apply_button.grid_configure(padx=(m.control_large_gap, 0), pady=(m.control_small_gap, 0))
        if hasattr(self, "goal_label"):
            self.goal_label.grid_configure(pady=(m.control_large_gap, 0))
        if hasattr(self, "goal_entry"):
            self.goal_entry.grid_configure(pady=(m.control_small_gap, 0))
        if hasattr(self, "goal_apply_button"):
            self.goal_apply_button.grid_configure(padx=(m.control_large_gap, 0), pady=(m.control_small_gap, 0))
        if hasattr(self, "author_label"):
            self.author_label.grid_configure(pady=(m.control_large_gap, 0))
        if hasattr(self, "author_combo"):
            self.author_combo.grid_configure(pady=(m.control_small_gap, 0))
        if hasattr(self, "author_apply_button"):
            self.author_apply_button.grid_configure(padx=(m.control_large_gap, 0), pady=(m.control_small_gap, 0))
        if hasattr(self, "auto_refresh_check"):
            self.auto_refresh_check.grid_configure(pady=(m.control_large_gap, 0))
        if hasattr(self, "footer_frame"):
            self.footer_frame.grid_configure(pady=(m.footer_gap, 0))
        if hasattr(self, "loading_label"):
            self.loading_label.grid_configure(pady=(m.section_gap, 0))
        if hasattr(self, "loading_bar"):
            self.loading_bar.grid_configure(padx=(m.section_gap, 0), pady=(m.section_gap, 0))
        if hasattr(self, "loading_detail_label"):
            self.loading_detail_label.grid_configure(padx=(0, m.header_group_gap))
        if hasattr(self, "refresh_button"):
            self.refresh_button.grid_configure(padx=(m.tile_gap_x, 0))
        if hasattr(self, "copy_button"):
            self.copy_button.grid_configure(padx=(m.tile_gap_x, 0))

    def apply_responsive_layout(self) -> None:
        try:
            self.root.update_idletasks()
        except tk.TclError:
            return

        if self.base_required_width <= 0:
            try:
                self.base_required_width = max(BASE_WINDOW_WIDTH, int(self.container.winfo_reqwidth()))
            except (tk.TclError, TypeError, ValueError):
                self.base_required_width = BASE_WINDOW_WIDTH

        screen_limit = max(640, self.root.winfo_screenwidth() - WINDOW_SCREEN_MARGIN)
        self.screen_limit_width = screen_limit
        target_width = screen_limit
        scale = min(1.0, target_width / max(self.base_required_width, 1))
        self._apply_responsive_scale(scale)

        try:
            self.root.update_idletasks()
            current_required_width = max(1, int(self.container.winfo_reqwidth()))
        except (tk.TclError, TypeError, ValueError):
            current_required_width = 0

        if current_required_width > screen_limit:
            correction = (target_width / current_required_width) * 0.99
            self._apply_responsive_scale(max(0.55, self.layout_scale * correction))

    def _apply_responsive_scale(self, scale: float) -> None:
        self.layout_scale = min(max(scale, 0.55), 1.0)
        self.layout_metrics = build_layout_metrics(self.layout_scale)
        self.graph_canvas_width = max(300, int(round(GRAPH_CANVAS_WIDTH * self.layout_scale)))
        self.progress_bar_length = max(300, int(round(BAR_LENGTH * self.layout_scale)))
        self.tile_min_width = max(180, int(round(BASE_TILE_MIN_WIDTH * self.layout_scale)))
        self.tile_wrap = max(170, int(round(BASE_TILE_LABEL_WRAP * self.layout_scale)))
        self.repo_entry_width = max(28, int(round(RESPONSIVE_REPO_ENTRY_WIDTH * self.layout_scale)))
        self.refresh_layout_metrics()
        self.update_left_panel_width()

        if hasattr(self, "repo_entry"):
            self.repo_entry.configure(width=self.repo_entry_width)
        if hasattr(self, "overall_progress_bar"):
            self.overall_progress_bar.configure(width=self.progress_bar_length)
        if hasattr(self, "daily_progress_bar"):
            self.daily_progress_bar.configure(width=self.progress_bar_length)
        if hasattr(self, "graph_canvas"):
            self.graph_canvas.configure(width=self.graph_canvas_width, height=GRAPH_CANVAS_HEIGHT)

        graph_column_width = self.graph_canvas_width + 24
        if hasattr(self, "right_area"):
            self.right_area.columnconfigure(0, minsize=graph_column_width)
        if hasattr(self, "controls_section"):
            self.controls_section.columnconfigure(0, minsize=graph_column_width)

        grass_panel_controller = getattr(self, "grass_panel_controller", None)
        if grass_panel_controller is not None:
            grass_panel_controller.set_layout_scale(self.layout_scale)

        if getattr(self, "graph_highlight_day", None) is not None and hasattr(self, "graph_canvas"):
            self.redraw_graph()

    def apply_color_palette(self) -> None:
        self.root.configure(bg=self.theme.app_bg)
        self._configure_style_palette()
        self._configure_widget_palette()
        self.apply_window_chrome_theme()

    def enable_main_window_chrome(self) -> None:
        if not self.use_custom_titlebar:
            return
        if getattr(self, "compact_mode", False):
            return
        if hasattr(self, "custom_titlebar"):
            self.custom_titlebar.grid()
        self._set_root_overrideredirect(True)
        self.promote_appwindow_style()

    def promote_appwindow_style(self) -> None:
        if not self.use_custom_titlebar:
            return
        try:
            import ctypes
        except Exception:
            return
        try:
            self.root.update_idletasks()
        except tk.TclError:
            return
        try:
            user32 = ctypes.windll.user32
            hwnd = user32.GetAncestor(self.root.winfo_id(), 2)
        except Exception:
            hwnd = 0
        if not hwnd:
            return
        try:
            current_style = user32.GetWindowLongW(hwnd, -20)
            updated_style = (current_style | 0x00040000) & ~0x00000080
            user32.SetWindowLongW(hwnd, -20, updated_style)
            user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0027)
        except Exception:
            return

    def show_main_window(self) -> None:
        if self.capture_mode:
            self._show_capture_window_no_activate()
            return
        try:
            self.root.deiconify()
            self.root.lift()
        except tk.TclError:
            return
        if self.use_custom_titlebar:
            self.root.after(20, self.promote_appwindow_style)

    def _show_capture_window_no_activate(self) -> None:
        """Render the real window on an isolated desktop without taking focus."""
        if sys.platform != "win32":
            return
        try:
            import ctypes

            self.root.update_idletasks()
            user32 = ctypes.windll.user32
            hwnd = user32.GetAncestor(self.root.winfo_id(), 2)
            if not hwnd:
                return

            width = max(1, self.root.winfo_width())
            height = max(1, self.root.winfo_height())
            x_pos = 0
            y_pos = 0
            self.root.geometry(f"{width}x{height}{x_pos:+d}{y_pos:+d}")
            self.root.update_idletasks()

            ex_style = user32.GetWindowLongW(hwnd, -20)
            ex_style = (ex_style | 0x08000000 | 0x00000080) & ~0x00040000
            user32.SetWindowLongW(hwnd, -20, ex_style)
            self.root.deiconify()
            user32.SetWindowPos(
                hwnd,
                1,  # HWND_BOTTOM
                x_pos,
                y_pos,
                width,
                height,
                0x0010 | 0x0040 | 0x0020,  # NOACTIVATE | SHOWWINDOW | FRAMECHANGED
            )
            user32.ShowWindow(hwnd, 4)  # SW_SHOWNOACTIVATE
            user32.UpdateWindow(hwnd)
            self.root.update()
        except (AttributeError, OSError, tk.TclError):
            return

    def apply_window_chrome_theme(self) -> None:
        if self.use_custom_titlebar:
            return
        if sys.platform != "win32":
            return
        if getattr(self, "compact_mode", False):
            return

        try:
            self.root.update_idletasks()
        except tk.TclError:
            return

        try:
            import ctypes
            from ctypes import wintypes
        except Exception:
            return

        try:
            hwnd = ctypes.windll.user32.GetAncestor(self.root.winfo_id(), 2)
        except Exception:
            hwnd = 0
        if not hwnd:
            return

        caption_color = blend_hex(self.theme.app_bg, self.theme.card_bg, 0.2)
        text_color = contrast_text_color(caption_color)
        border_color = self.theme.border
        use_dark_mode = 0 if text_color == "#10161c" else 1

        try:
            dwmapi = ctypes.windll.dwmapi
        except Exception:
            return

        def set_dwm_attr(attribute: int, value: int) -> None:
            data = wintypes.DWORD(int(value))
            try:
                dwmapi.DwmSetWindowAttribute(
                    wintypes.HWND(hwnd),
                    ctypes.c_uint(attribute),
                    ctypes.byref(data),
                    ctypes.sizeof(data),
                )
            except Exception:
                pass

        for attribute in (20, 19):
            set_dwm_attr(attribute, use_dark_mode)
        set_dwm_attr(35, _hex_to_colorref(caption_color))
        set_dwm_attr(36, _hex_to_colorref(text_color))
        set_dwm_attr(34, _hex_to_colorref(border_color))

    def on_root_map(self, event: tk.Event) -> None:
        if event.widget is not self.root:
            return
        if not self.use_custom_titlebar or self.compact_mode:
            return
        if not self.custom_titlebar_restore_pending:
            return
        try:
            if self.root.state() == "iconic":
                return
        except tk.TclError:
            return
        self.custom_titlebar_restore_pending = False
        self.root.after(10, self.enable_main_window_chrome)

    def _configure_style_palette(self) -> None:
        palette = self.theme
        titlebar_bg = blend_hex(palette.app_bg, palette.card_bg, 0.45)
        titlebar_hover = blend_hex(titlebar_bg, palette.accent_light, 0.2)
        titlebar_pressed = blend_hex(titlebar_bg, palette.accent, 0.28)
        titlebar_close_hover = blend_hex(palette.danger, titlebar_bg, 0.18)
        titlebar_close_pressed = blend_hex(palette.danger, titlebar_bg, 0.32)
        self.style.configure("App.TFrame", background=palette.app_bg)
        self.style.configure("Card.TFrame", background=palette.card_bg, borderwidth=1, relief="solid")
        self.style.configure("CardInner.TFrame", background=palette.card_bg, borderwidth=0, relief="flat")
        self.style.configure("DeltaBox.TFrame", background=palette.card_bg, borderwidth=1, relief="solid")
        self.style.configure("VersionBadge.TFrame", background=palette.card_bg, borderwidth=1, relief="solid")
        self.style.configure("TitleBar.TFrame", background=titlebar_bg, borderwidth=0, relief="flat")
        self.style.configure("TitleBar.TLabel", background=titlebar_bg, foreground=palette.text, font=("Bahnschrift", 10, "bold"))
        self.style.configure("TitleBarMeta.TLabel", background=titlebar_bg, foreground=palette.muted_text, font=("Bahnschrift", 9))
        self.style.configure("Title.TLabel", background=palette.app_bg, foreground=palette.text, font=FONT_TITLE)
        self.style.configure("Version.TLabel", background=palette.card_bg, foreground=palette.muted_text, font=FONT_VERSION)
        self.style.configure("Subtitle.TLabel", background=palette.app_bg, foreground=palette.muted_text, font=FONT_SUBTITLE)
        self.style.configure("Section.TLabel", background=palette.app_bg, foreground=palette.text, font=FONT_SECTION)
        self.style.configure("SectionDeltaAdd.TLabel", background=palette.app_bg, foreground=palette.success, font=FONT_SUBTITLE)
        self.style.configure("SectionDeltaRemove.TLabel", background=palette.app_bg, foreground=palette.danger, font=FONT_SUBTITLE)
        self.style.configure("SectionCommit.TLabel", background=palette.app_bg, foreground=palette.muted_text, font=FONT_SUBTITLE)
        self.style.configure("CardTitle.TLabel", background=palette.card_bg, foreground=palette.text, font=FONT_BODY)
        self.style.configure("CardDeltaAdd.TLabel", background=palette.card_bg, foreground=palette.success, font=FONT_BODY)
        self.style.configure("CardDeltaRemove.TLabel", background=palette.card_bg, foreground=palette.danger, font=FONT_BODY)
        self.style.configure("SettingsTitle.TLabel", background=palette.card_bg, foreground=palette.text, font=FONT_SECTION)
        self.style.configure("SettingsLabel.TLabel", background=palette.card_bg, foreground=palette.muted_text, font=FONT_BODY)
        self.style.configure("CompactTitle.TLabel", background=palette.card_bg, foreground=palette.text, font=FONT_SECTION)
        self.style.configure("CardLabel.TLabel", background=palette.card_bg, foreground=palette.muted_text, font=FONT_BODY)
        self.style.configure("CompactLabel.TLabel", background=palette.card_bg, foreground=palette.muted_text, font=FONT_CHIP)
        self.style.configure("CompactValue.TLabel", background=palette.card_bg, foreground=palette.text, font=FONT_COMPACT_VALUE)
        self.style.configure("CompactBarValue.TLabel", background=palette.card_bg, foreground=palette.text, font=FONT_COMPACT_BAR_VALUE)
        self.style.configure("CompactMeta.TLabel", background=palette.card_bg, foreground=palette.muted_text, font=FONT_COMPACT_META)
        self.style.configure("CompactClock.TLabel", background=palette.card_bg, foreground=palette.muted_text, font=FONT_COMPACT_CLOCK)
        self.style.configure(
            "TitleBarButton.TButton",
            font=("Bahnschrift", 9, "bold"),
            foreground=palette.text,
            background=titlebar_bg,
            bordercolor=blend_hex(palette.border, palette.card_bg, 0.35),
            darkcolor=titlebar_bg,
            lightcolor=titlebar_bg,
            focuscolor=titlebar_bg,
            padding=(6, 1),
            relief="flat",
        )
        self.style.map(
            "TitleBarButton.TButton",
            background=[
                ("active", titlebar_hover),
                ("pressed", titlebar_pressed),
            ],
            bordercolor=[
                ("active", blend_hex(palette.border, palette.accent_light, 0.5)),
                ("pressed", palette.accent_dark),
            ],
            foreground=[
                ("active", palette.text),
                ("pressed", palette.text),
            ],
            lightcolor=[
                ("active", titlebar_hover),
                ("pressed", titlebar_pressed),
            ],
            darkcolor=[
                ("active", titlebar_hover),
                ("pressed", titlebar_pressed),
            ],
        )
        self.style.configure(
            "TitleBarClose.TButton",
            font=("Bahnschrift", 9, "bold"),
            foreground=palette.text,
            background=titlebar_bg,
            bordercolor=blend_hex(palette.border, palette.danger, 0.28),
            darkcolor=titlebar_bg,
            lightcolor=titlebar_bg,
            focuscolor=titlebar_bg,
            padding=(6, 1),
            relief="flat",
        )
        self.style.map(
            "TitleBarClose.TButton",
            background=[
                ("active", titlebar_close_hover),
                ("pressed", titlebar_close_pressed),
            ],
            bordercolor=[
                ("active", blend_hex(palette.border, palette.danger, 0.65)),
                ("pressed", palette.danger),
            ],
            foreground=[
                ("active", palette.text),
                ("pressed", palette.text),
            ],
            lightcolor=[
                ("active", titlebar_close_hover),
                ("pressed", titlebar_close_pressed),
            ],
            darkcolor=[
                ("active", titlebar_close_hover),
                ("pressed", titlebar_close_pressed),
            ],
        )
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
        self.style.configure(
            "Settings.TNotebook",
            background=palette.card_bg,
            borderwidth=0,
            tabmargins=(0, 4, 0, 0),
        )
        self.style.configure(
            "Settings.TNotebook.Tab",
            background=blend_hex(palette.card_bg, palette.app_bg, 0.16),
            foreground=palette.muted_text,
            bordercolor=palette.border,
            lightcolor=palette.card_bg,
            darkcolor=palette.card_bg,
            focuscolor=palette.card_bg,
            padding=(12, 6),
            font=FONT_BODY,
        )
        self.style.map(
            "Settings.TNotebook.Tab",
            background=[
                ("selected", blend_hex(palette.card_bg, palette.accent_light, 0.16)),
                ("active", blend_hex(palette.card_bg, palette.accent_light, 0.1)),
            ],
            foreground=[
                ("selected", palette.text),
                ("active", palette.text),
            ],
        )
        entry_bg = blend_hex(palette.card_bg, palette.app_bg, 0.18)
        entry_focus_bg = blend_hex(palette.card_bg, palette.accent_light, 0.1)
        entry_border = blend_hex(palette.border, palette.accent_light, 0.32)
        entry_border_focus = blend_hex(palette.border, palette.accent_light, 0.62)
        self.style.configure(
            "Tracker.TEntry",
            fieldbackground=entry_bg,
            foreground=palette.text,
            bordercolor=entry_border,
            darkcolor=entry_bg,
            lightcolor=entry_bg,
            insertcolor=palette.text,
            padding=(6, 4),
            relief="flat",
            font=FONT_BODY,
        )
        self.style.map(
            "Tracker.TEntry",
            fieldbackground=[
                ("focus", entry_focus_bg),
                ("disabled", blend_hex(entry_bg, palette.border, 0.55)),
            ],
            foreground=[
                ("disabled", blend_hex(palette.muted_text, palette.border, 0.35)),
            ],
            bordercolor=[
                ("focus", entry_border_focus),
                ("disabled", blend_hex(entry_border, palette.border, 0.4)),
            ],
            lightcolor=[
                ("focus", entry_focus_bg),
                ("disabled", blend_hex(entry_bg, palette.border, 0.55)),
            ],
            darkcolor=[
                ("focus", entry_focus_bg),
                ("disabled", blend_hex(entry_bg, palette.border, 0.55)),
            ],
        )
        self.style.configure("TEntry", fieldbackground=entry_bg, foreground=palette.text, font=FONT_BODY)
        combo_bg = blend_hex(palette.card_bg, palette.app_bg, 0.18)
        combo_hover = blend_hex(palette.card_bg, palette.accent_light, 0.12)
        combo_focus = blend_hex(palette.card_bg, palette.accent_light, 0.2)
        combo_border = blend_hex(palette.border, palette.accent_light, 0.32)
        combo_border_focus = blend_hex(palette.border, palette.accent_light, 0.62)
        combo_arrow = blend_hex(palette.text, palette.accent_light, 0.15)
        self.style.configure(
            "Tracker.TCombobox",
            fieldbackground=combo_bg,
            background=combo_bg,
            foreground=palette.text,
            arrowcolor=combo_arrow,
            bordercolor=combo_border,
            darkcolor=combo_bg,
            lightcolor=combo_bg,
            insertcolor=palette.text,
            padding=(6, 4, 4, 4),
            relief="flat",
            font=FONT_BODY,
        )
        self.style.map(
            "Tracker.TCombobox",
            fieldbackground=[
                ("readonly", combo_bg),
                ("focus", combo_focus),
                ("active", combo_hover),
                ("disabled", blend_hex(combo_bg, palette.border, 0.55)),
            ],
            background=[
                ("readonly", combo_bg),
                ("focus", combo_focus),
                ("active", combo_hover),
                ("disabled", blend_hex(combo_bg, palette.border, 0.55)),
            ],
            foreground=[
                ("disabled", blend_hex(palette.muted_text, palette.border, 0.35)),
                ("readonly", palette.text),
            ],
            arrowcolor=[
                ("active", palette.accent_light),
                ("focus", palette.accent_light),
                ("disabled", blend_hex(palette.muted_text, palette.border, 0.35)),
                ("readonly", combo_arrow),
            ],
            bordercolor=[
                ("focus", combo_border_focus),
                ("active", combo_border_focus),
                ("readonly", combo_border),
                ("disabled", blend_hex(combo_border, palette.border, 0.4)),
            ],
            lightcolor=[
                ("focus", combo_focus),
                ("active", combo_hover),
                ("readonly", combo_bg),
                ("disabled", blend_hex(combo_bg, palette.border, 0.55)),
            ],
            darkcolor=[
                ("focus", combo_focus),
                ("active", combo_hover),
                ("readonly", combo_bg),
                ("disabled", blend_hex(combo_bg, palette.border, 0.55)),
            ],
        )
        self.root.option_add("*TCombobox*Listbox*Background", palette.card_bg)
        self.root.option_add("*TCombobox*Listbox*Foreground", palette.text)
        self.root.option_add("*TCombobox*Listbox*selectBackground", palette.accent_dark)
        self.root.option_add("*TCombobox*Listbox*selectForeground", palette.text)
        self.root.option_add("*TCombobox*Listbox*BorderWidth", 0)
        self.root.option_add("*TCombobox*Listbox*HighlightThickness", 0)
        self.root.option_add("*TCombobox*Listbox*Font", "Bahnschrift 10")
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
        if hasattr(self, "custom_titlebar_accent"):
            self.custom_titlebar_accent.configure(bg=palette.accent)
        if hasattr(self, "header_accent_bar"):
            self.header_accent_bar.configure(bg=palette.accent)
        for idx, widget in enumerate(getattr(self, "tile_accent_widgets", [])):
            widget.configure(bg=palette.tile_accents[idx % len(palette.tile_accents)])
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
        if hasattr(self, "app_settings_button"):
            self.redraw_app_settings_button()
        if hasattr(self, "graph_settings_button"):
            self.redraw_graph_settings_button()
        if hasattr(self, "graph_canvas"):
            self.graph_canvas.configure(bg=palette.canvas_bg, highlightbackground=palette.border)
        if hasattr(self, "overall_progress_bar"):
            self.redraw_progress_bars()
        stats_scroll_panel = getattr(self, "stats_scroll_panel", None)
        if stats_scroll_panel is not None:
            stats_scroll_panel.apply_theme(canvas_bg=palette.app_bg)
        commit_history_scroll_panel = getattr(self, "commit_history_scroll_panel", None)
        if commit_history_scroll_panel is not None:
            commit_history_scroll_panel.apply_theme(canvas_bg=palette.card_bg)
        grass_panel_controller = getattr(self, "grass_panel_controller", None)
        if grass_panel_controller is not None:
            grass_panel_controller.apply_theme()
        schedule_panel_controller = getattr(self, "schedule_panel_controller", None)
        if schedule_panel_controller is not None:
            schedule_panel_controller.apply_theme()
        self.refresh_graph_settings_window()
        self.refresh_app_settings_window()
        graph_highlight_day = getattr(self, "graph_highlight_day", None)
        if graph_highlight_day is not None and hasattr(self, "graph_canvas"):
            self.redraw_graph()

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
        return parse_author_identity(identity)

    @staticmethod
    def _build_author_option_entries(
        identities: list[str],
        auto_label: str,
        all_label: str,
    ) -> tuple[list[str], dict[str, str], dict[str, str]]:
        return build_author_option_entries(identities, auto_label, all_label)

    def build_author_options(self) -> tuple[list[str], dict[str, str], dict[str, str]]:
        auto_label = self.t("author_auto")
        all_label = self.t("author_all")
        try:
            out = run_git(self.repo, ["shortlog", "-sne", "--all"])
        except RuntimeError:
            return self._build_author_option_entries([], auto_label, all_label)

        identities = parse_shortlog_identities(out)
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
        self.title_label.configure(text=self.get_header_project_title())
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
            daily_percent_text = self.format_progress_percent(
                daily_percent,
                complete=snapshot.today_done >= today_target,
            )
            compact_progress_text = self.t(
                "compact_progress_value_text",
                percent=daily_percent_text,
                done=f"{snapshot.today_done:,}",
                target=f"{today_target:,}",
            )
            compact_strip_text = f"{snapshot.today_done:,}/{today_target:,} [{daily_percent_text}%]"
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
        if self.use_custom_titlebar and hasattr(self, "custom_titlebar"):
            self.custom_titlebar.grid_remove()
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
        if self.use_custom_titlebar and hasattr(self, "custom_titlebar"):
            self.custom_titlebar.grid()
        self.container.grid()
        if self.use_custom_titlebar:
            self._set_root_overrideredirect(True)
        else:
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
        if self.use_custom_titlebar:
            self.enable_main_window_chrome()
        else:
            self.apply_window_chrome_theme()

    def load_settings(self) -> UISettings:
        return load_ui_settings(self.settings_path, self.legacy_settings_path)

    def save_settings(self) -> None:
        if self.capture_mode:
            return
        self.settings = UISettings(
            goal=self.goal,
            custom_today_enabled=self.custom_today_var.get(),
            custom_today=self.today_entry_var.get().strip(),
            graph_days=self.graph_days_var.get(),
            graph_show_additions=self.graph_show_additions_var.get(),
            graph_show_deletions=self.graph_show_deletions_var.get(),
            graph_show_commits=self.graph_show_commits_var.get(),
            graph_curve=float(self.graph_curve_var.get()),
            auto_refresh=self.auto_refresh_var.get(),
            author=self.author_raw,
            author_display=self.author_display,
            compact_variant=self.compact_variant,
            compact_alpha=self.compact_alpha,
            note_tab=self.active_note_tab,
            schedule_path=self.schedule_path,
            repo_path=str(self.repo) if self.repo_selected else "",
            lang=self.lang,
            theme=self.theme_name,
            geometry=self.get_persisted_geometry(),
        )
        if not save_ui_settings(self.settings_path, self.settings):
            messagebox.showerror(
                self.t("settings_save_error_title"),
                self.t("settings_save_error", path=str(self.settings_path)),
            )

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
        if hasattr(self, "today_entry"):
            self.today_entry.configure(state=state)
        if hasattr(self, "today_apply_button"):
            self.today_apply_button.configure(state=state)

    def update_repo_dependent_controls(self) -> None:
        repo_state = "normal" if self.repo_selected else "disabled"
        if not self.repo_selected and self.auto_refresh_var.get():
            self.auto_refresh_var.set(False)
        if not self.repo_selected:
            self.cancel_auto_refresh()
        if hasattr(self, "auto_refresh_check"):
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
        icon = palette.button_text
        self.compact_button.create_rectangle(
            8,
            8,
            size - 7,
            size - 7,
            outline=icon,
            width=1,
        )
        self.compact_button.create_rectangle(
            size - 14,
            size - 14,
            size - 9,
            size - 9,
            fill=icon,
            outline=icon,
        )

    def redraw_graph_settings_button(self) -> None:
        if not hasattr(self, "graph_settings_button"):
            return
        palette = self.theme
        size = GRAPH_SETTINGS_BUTTON_SIZE
        inset = 2
        state = getattr(self, "graph_settings_button_state", "normal")

        fill = blend_hex(palette.card_bg, palette.accent_light, 0.08)
        border = blend_hex(palette.border, palette.accent_light, 0.18)
        icon = palette.accent_light
        if state == "hover":
            fill = blend_hex(palette.card_bg, palette.accent_light, 0.18)
            border = blend_hex(palette.border, palette.accent_light, 0.42)
            icon = palette.text
        elif state == "pressed":
            fill = blend_hex(palette.card_bg, palette.accent, 0.26)
            border = blend_hex(palette.border, palette.accent, 0.55)
            icon = palette.text

        canvas = self.graph_settings_button
        canvas.configure(bg=palette.app_bg, width=size, height=size)
        canvas.delete("all")
        canvas.create_rectangle(
            inset,
            inset,
            size - inset,
            size - inset,
            fill=fill,
            outline=border,
            width=1,
        )

        left = 8
        right = size - 8
        rows = ((9, 18), (14, 11), (19, 20))
        knob_radius = 2
        for y, knob_x in rows:
            canvas.create_line(left, y, right, y, fill=icon, width=2)
            canvas.create_oval(
                knob_x - knob_radius,
                y - knob_radius,
                knob_x + knob_radius,
                y + knob_radius,
                fill=icon,
                outline="",
            )

    def redraw_app_settings_button(self) -> None:
        if not hasattr(self, "app_settings_button"):
            return
        palette = self.theme
        size = APP_SETTINGS_BUTTON_SIZE
        inset = 2
        state = getattr(self, "app_settings_button_state", "normal")

        fill = blend_hex(palette.card_bg, palette.accent_light, 0.08)
        border = blend_hex(palette.border, palette.accent_light, 0.2)
        icon = palette.accent_light
        if state == "hover":
            fill = blend_hex(palette.card_bg, palette.accent_light, 0.18)
            border = blend_hex(palette.border, palette.accent_light, 0.45)
            icon = palette.text
        elif state == "pressed":
            fill = blend_hex(palette.card_bg, palette.accent, 0.28)
            border = blend_hex(palette.border, palette.accent, 0.58)
            icon = palette.text

        canvas = self.app_settings_button
        canvas.configure(bg=palette.app_bg, width=size, height=size)
        canvas.delete("all")
        canvas.create_rectangle(
            inset,
            inset,
            size - inset,
            size - inset,
            fill=fill,
            outline=border,
            width=1,
        )

        cx = cy = size / 2
        for idx in range(8):
            angle = math.tau * idx / 8
            inner = 8.5
            outer = 11.5
            canvas.create_line(
                cx + math.cos(angle) * inner,
                cy + math.sin(angle) * inner,
                cx + math.cos(angle) * outer,
                cy + math.sin(angle) * outer,
                fill=icon,
                width=2,
            )
        canvas.create_oval(cx - 8, cy - 8, cx + 8, cy + 8, outline=icon, width=2)
        canvas.create_oval(cx - 2.5, cy - 2.5, cx + 2.5, cy + 2.5, fill=icon, outline="")

    def set_app_settings_button_state(self, state: str) -> None:
        self.app_settings_button_state = state
        self.redraw_app_settings_button()

    def on_app_settings_button_release(self, event: tk.Event) -> str:
        if not hasattr(self, "app_settings_button"):
            return "break"
        inside = 0 <= event.x <= APP_SETTINGS_BUTTON_SIZE and 0 <= event.y <= APP_SETTINGS_BUTTON_SIZE
        self.set_app_settings_button_state("hover" if inside else "normal")
        if inside:
            self.open_app_settings_window()
        return "break"

    def on_app_settings_button_keypress(self, _: tk.Event) -> str:
        self.open_app_settings_window()
        return "break"

    def set_graph_settings_button_state(self, state: str) -> None:
        self.graph_settings_button_state = state
        self.redraw_graph_settings_button()

    def on_graph_settings_button_release(self, event: tk.Event) -> str:
        if not hasattr(self, "graph_settings_button"):
            return "break"
        inside = 0 <= event.x <= GRAPH_SETTINGS_BUTTON_SIZE and 0 <= event.y <= GRAPH_SETTINGS_BUTTON_SIZE
        self.set_graph_settings_button_state("hover" if inside else "normal")
        if inside:
            self.open_graph_settings_window()
        return "break"

    def on_graph_settings_button_keypress(self, _: tk.Event) -> str:
        self.open_graph_settings_window()
        return "break"

    def open_app_settings_window(self) -> None:
        existing_window = self.app_settings_window
        if existing_window is not None:
            try:
                if existing_window.winfo_exists():
                    self.refresh_app_settings_window()
                    existing_window.lift()
                    existing_window.focus_set()
                    return
            except tk.TclError:
                self.close_app_settings_window()

        window = ttk.Frame(self.root, style="Card.TFrame", padding=(16, 14), takefocus=True)
        window.place(relx=0.5, rely=0.5, anchor="center", width=480)
        window.columnconfigure(0, weight=1)
        window.bind("<Escape>", lambda _: self.close_app_settings_window())
        self.app_settings_window = window
        self.app_settings_card = window

        title_row = ttk.Frame(window, style="CardInner.TFrame")
        title_row.grid(row=0, column=0, sticky="ew")
        title_row.columnconfigure(0, weight=1)

        self.app_settings_title_label = ttk.Label(title_row, text=self.t("settings"), style="SettingsTitle.TLabel")
        self.app_settings_title_label.grid(row=0, column=0, sticky="w")

        self.app_settings_close_button = ttk.Button(
            title_row,
            text="X",
            command=self.close_app_settings_window,
            style="CompactTool.TButton",
            width=3,
        )
        self.app_settings_close_button.grid(row=0, column=1, sticky="e")

        notebook = ttk.Notebook(window, style="Settings.TNotebook")
        notebook.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        self.app_settings_notebook = notebook

        general_tab = ttk.Frame(notebook, style="CardInner.TFrame", padding=(12, 12))
        repo_tab = ttk.Frame(notebook, style="CardInner.TFrame", padding=(12, 12))
        tracking_tab = ttk.Frame(notebook, style="CardInner.TFrame", padding=(12, 12))
        schedule_tab = ttk.Frame(notebook, style="CardInner.TFrame", padding=(12, 12))
        for tab in (general_tab, repo_tab, tracking_tab, schedule_tab):
            tab.columnconfigure(0, weight=1)
        notebook.add(general_tab, text=self.t("settings_general_tab"))
        notebook.add(repo_tab, text=self.t("settings_repo_tab"))
        notebook.add(tracking_tab, text=self.t("settings_tracking_tab"))
        notebook.add(schedule_tab, text=self.t("settings_schedule_tab"))

        self._build_general_settings_tab(general_tab)
        self._build_repo_settings_tab(repo_tab)
        self._build_tracking_settings_tab(tracking_tab)
        self._build_schedule_settings_tab(schedule_tab)

        self.refresh_app_settings_window()
        window.update_idletasks()
        window.lift()
        window.focus_set()

    def _build_general_settings_tab(self, parent: ttk.Frame) -> None:
        m = self.layout_metrics
        self.lang_label = ttk.Label(parent, text=self.t("lang_label"), style="SettingsLabel.TLabel")
        self.lang_label.grid(row=0, column=0, sticky="w")
        self.lang_combo = ttk.Combobox(
            parent,
            textvariable=self.lang_var,
            values=list(LANG_OPTIONS.keys()),
            width=18,
            state="readonly",
            style="Tracker.TCombobox",
        )
        self.lang_combo.grid(row=1, column=0, sticky="ew", pady=(m.control_small_gap, m.control_large_gap))
        self.lang_combo.bind("<<ComboboxSelected>>", self.on_language_select)
        self._bind_combobox_text_selection_clear(self.lang_combo)

        self.theme_label = ttk.Label(parent, text=self.t("theme_label"), style="SettingsLabel.TLabel")
        self.theme_label.grid(row=2, column=0, sticky="w")
        self.theme_combo = ttk.Combobox(
            parent,
            textvariable=self.theme_var,
            values=self.theme_display_values(),
            width=18,
            state="readonly",
            style="Tracker.TCombobox",
        )
        self.theme_combo.grid(row=3, column=0, sticky="ew", pady=(m.control_small_gap, 0))
        self.theme_combo.bind("<<ComboboxSelected>>", self.on_theme_select)
        self._bind_combobox_text_selection_clear(self.theme_combo)

    def _build_repo_settings_tab(self, parent: ttk.Frame) -> None:
        m = self.layout_metrics
        parent.columnconfigure(0, minsize=300, weight=1)
        self.repo_header_label = ttk.Label(parent, text=self.t("repo_label"), style="SettingsLabel.TLabel")
        self.repo_header_label.grid(row=0, column=0, sticky="w")
        self.repo_entry = ttk.Entry(parent, textvariable=self.repo_entry_var, width=48, style="Tracker.TEntry")
        self.repo_entry.grid(row=1, column=0, sticky="ew", pady=(m.control_small_gap, 0))
        self.repo_entry.bind("<Return>", self.on_repo_entry_enter)
        self.repo_apply_button = ttk.Button(parent, text=self.t("repo_select"), command=self.browse_repo)
        self.repo_apply_button.grid(row=1, column=1, sticky="e", padx=(m.control_large_gap, 0), pady=(m.control_small_gap, 0))

    def _build_tracking_settings_tab(self, parent: ttk.Frame) -> None:
        m = self.layout_metrics
        parent.columnconfigure(0, minsize=260, weight=1)

        self.custom_today_check = ttk.Checkbutton(
            parent,
            text=self.t("custom_date"),
            variable=self.custom_today_var,
            command=self.on_custom_date_toggle,
        )
        self.custom_today_check.grid(row=0, column=0, columnspan=2, sticky="w")

        self.today_entry = ttk.Entry(parent, textvariable=self.today_entry_var, width=14, style="Tracker.TEntry")
        self.today_entry.grid(row=1, column=0, sticky="ew", pady=(m.control_small_gap, 0))
        self.today_entry.bind("<Return>", self.on_today_entry_enter)
        self.today_apply_button = ttk.Button(parent, text=self.t("apply_date"), command=self.apply_custom_date)
        self.today_apply_button.grid(row=1, column=1, sticky="e", padx=(m.control_large_gap, 0), pady=(m.control_small_gap, 0))

        self.goal_label = ttk.Label(parent, text=self.t("goal_label"), style="SettingsLabel.TLabel")
        self.goal_label.grid(row=2, column=0, sticky="w", pady=(m.control_large_gap, 0))
        self.goal_entry = ttk.Entry(parent, textvariable=self.goal_entry_var, width=14, style="Tracker.TEntry")
        self.goal_entry.grid(row=3, column=0, sticky="ew", pady=(m.control_small_gap, 0))
        self.goal_entry.bind("<Return>", self.on_goal_entry_enter)
        self.goal_apply_button = ttk.Button(parent, text=self.t("apply_goal"), command=self.apply_goal)
        self.goal_apply_button.grid(row=3, column=1, sticky="e", padx=(m.control_large_gap, 0), pady=(m.control_small_gap, 0))

        self.author_label = ttk.Label(parent, text=self.t("author_label"), style="SettingsLabel.TLabel")
        self.author_label.grid(row=4, column=0, sticky="w", pady=(m.control_large_gap, 0))
        self.author_combo = ttk.Combobox(
            parent,
            textvariable=self.author_entry_var,
            values=self.author_options,
            width=28,
            style="Tracker.TCombobox",
        )
        self.author_combo.grid(row=5, column=0, sticky="ew", pady=(m.control_small_gap, 0))
        self.author_combo.bind("<Return>", self.on_author_entry_enter)
        self.author_combo.bind("<<ComboboxSelected>>", self.on_author_select)
        self._bind_combobox_text_selection_clear(self.author_combo)
        self.author_apply_button = ttk.Button(parent, text=self.t("apply_author"), command=self.apply_author)
        self.author_apply_button.grid(row=5, column=1, sticky="e", padx=(m.control_large_gap, 0), pady=(m.control_small_gap, 0))

        self.auto_refresh_check = ttk.Checkbutton(
            parent,
            text=self.t("auto_refresh"),
            variable=self.auto_refresh_var,
            command=self.on_auto_refresh_toggle,
        )
        self.auto_refresh_check.grid(row=6, column=0, columnspan=2, sticky="w", pady=(m.control_large_gap, 0))
        self.apply_date_controls_state()
        self.update_repo_dependent_controls()

    def _build_schedule_settings_tab(self, parent: ttk.Frame) -> None:
        m = self.layout_metrics
        parent.columnconfigure(0, minsize=300, weight=1)

        self.schedule_path_label = ttk.Label(
            parent,
            text=self.t("schedule_path_label"),
            style="SettingsLabel.TLabel",
        )
        self.schedule_path_label.grid(row=0, column=0, columnspan=2, sticky="w")

        self.schedule_path_entry = ttk.Entry(
            parent,
            textvariable=self.schedule_path_var,
            style="Tracker.TEntry",
        )
        self.schedule_path_entry.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(m.control_small_gap, 0),
        )
        self.schedule_path_entry.bind("<Return>", lambda _: self.apply_schedule_path())

        self.schedule_path_hint = ttk.Label(
            parent,
            text=self.t("schedule_path_hint"),
            style="CardLabel.TLabel",
            wraplength=390,
            justify="left",
        )
        self.schedule_path_hint.grid(row=2, column=0, columnspan=2, sticky="w", pady=(m.control_large_gap, 0))

        actions = ttk.Frame(parent, style="CardInner.TFrame")
        actions.grid(row=3, column=0, columnspan=2, sticky="e", pady=(m.control_large_gap, 0))
        self.schedule_settings_browse_button = ttk.Button(
            actions,
            text=self.t("schedule_select"),
            command=self.browse_schedule_file,
        )
        self.schedule_settings_browse_button.grid(row=0, column=0, sticky="e")
        self.schedule_path_apply_button = ttk.Button(
            actions,
            text=self.t("schedule_path_apply"),
            command=self.apply_schedule_path,
        )
        self.schedule_path_apply_button.grid(row=0, column=1, sticky="e", padx=(m.control_large_gap, 0))

    def close_app_settings_window(self) -> None:
        window = self.app_settings_window
        self.app_settings_window = None
        self.app_settings_card = None
        self.app_settings_notebook = None
        for attr_name in (
            "app_settings_title_label",
            "app_settings_close_button",
            "lang_label",
            "lang_combo",
            "theme_label",
            "theme_combo",
            "repo_header_label",
            "repo_entry",
            "repo_apply_button",
            "custom_today_check",
            "today_entry",
            "today_apply_button",
            "goal_label",
            "goal_entry",
            "goal_apply_button",
            "author_label",
            "author_combo",
            "author_apply_button",
            "auto_refresh_check",
            "schedule_path_label",
            "schedule_path_entry",
            "schedule_path_hint",
            "schedule_settings_browse_button",
            "schedule_path_apply_button",
        ):
            if hasattr(self, attr_name):
                delattr(self, attr_name)
        if window is not None:
            try:
                window.destroy()
            except tk.TclError:
                pass

    def refresh_app_settings_window(self) -> None:
        window = self.app_settings_window
        if window is None:
            return
        try:
            if not window.winfo_exists():
                self.close_app_settings_window()
                return
        except tk.TclError:
            self.close_app_settings_window()
            return

        window.configure(style="Card.TFrame")
        if hasattr(self, "app_settings_title_label"):
            self.app_settings_title_label.configure(text=self.t("settings"))
        if self.app_settings_notebook is not None:
            self.app_settings_notebook.tab(0, text=self.t("settings_general_tab"))
            self.app_settings_notebook.tab(1, text=self.t("settings_repo_tab"))
            self.app_settings_notebook.tab(2, text=self.t("settings_tracking_tab"))
            self.app_settings_notebook.tab(3, text=self.t("settings_schedule_tab"))
        if hasattr(self, "lang_label"):
            self.lang_label.configure(text=self.t("lang_label"))
        if hasattr(self, "theme_label"):
            self.theme_label.configure(text=self.t("theme_label"))
        if hasattr(self, "repo_header_label"):
            self.repo_header_label.configure(text=self.t("repo_label"))
        if hasattr(self, "repo_apply_button"):
            self.repo_apply_button.configure(text=self.t("repo_select"))
        if hasattr(self, "custom_today_check"):
            self.custom_today_check.configure(text=self.t("custom_date"))
        if hasattr(self, "today_apply_button"):
            self.today_apply_button.configure(text=self.t("apply_date"))
        if hasattr(self, "goal_label"):
            self.goal_label.configure(text=self.t("goal_label"))
        if hasattr(self, "goal_apply_button"):
            self.goal_apply_button.configure(text=self.t("apply_goal"))
        if hasattr(self, "author_label"):
            self.author_label.configure(text=self.t("author_label"))
        if hasattr(self, "author_apply_button"):
            self.author_apply_button.configure(text=self.t("apply_author"))
        if hasattr(self, "auto_refresh_check"):
            self.auto_refresh_check.configure(text=self.t("auto_refresh"))
        if hasattr(self, "schedule_path_label"):
            self.schedule_path_label.configure(text=self.t("schedule_path_label"))
        if hasattr(self, "schedule_path_hint"):
            self.schedule_path_hint.configure(text=self.t("schedule_path_hint"))
        if hasattr(self, "schedule_settings_browse_button"):
            self.schedule_settings_browse_button.configure(text=self.t("schedule_select"))
        if hasattr(self, "schedule_path_apply_button"):
            self.schedule_path_apply_button.configure(text=self.t("schedule_path_apply"))
        if hasattr(self, "lang_combo"):
            self.lang_combo.configure(values=list(LANG_OPTIONS.keys()))
        self.refresh_theme_selector()
        self.apply_date_controls_state()
        self.update_repo_dependent_controls()

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
        self.refresh_schedule()
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
        self.refresh_ref_label()
        config = self.build_config()
        graph_days = int(self.graph_days_var.get())
        self.set_loading_state(True)
        request_id = self.refresh_coordinator.start(
            repo=self.repo,
            author=self.author,
            config=config,
            graph_days=graph_days,
            on_success=self._on_refresh_success,
            on_failure=self._on_refresh_error,
        )
        if request_id is None:
            self.refresh_in_progress = False
            self.set_loading_state(False)
            return
        self.refresh_request_id = request_id

    def safe_after(self, callback) -> None:
        try:
            self.root.after(0, callback)
        except (RuntimeError, tk.TclError):
            pass

    def install_background_focus_clear_bindings(self) -> None:
        roots: list[tk.Misc] = [self.root]
        for attr_name in ("stats_scroll_host", "stats_canvas", "stats_container", "container", "compact_container"):
            widget = getattr(self, attr_name, None)
            if widget is not None:
                roots.append(widget)
        for root_widget in roots:
            self._bind_background_focus_clear(root_widget)

    def _bind_background_focus_clear(self, widget: tk.Misc) -> None:
        if isinstance(widget, (tk.Frame, ttk.Frame, tk.Label, ttk.Label, tk.Canvas)):
            widget.bind("<Button-1>", self.on_background_click_clear_focus, add="+")
        for child in widget.winfo_children():
            self._bind_background_focus_clear(child)

    def on_background_click_clear_focus(self, event: tk.Event) -> None:
        widget = event.widget
        widget_class = widget.winfo_class()
        if widget_class in {"Entry", "TEntry", "Text", "TCombobox", "Combobox", "Listbox", "Menu", "Scale"}:
            return
        try:
            self.root.after_idle(self.root.focus_set)
        except tk.TclError:
            return

    def _bind_stats_scroll(self) -> None:
        self.root.bind_all("<MouseWheel>", self.on_main_content_mousewheel, add="+")
        self.root.bind_all("<Button-4>", self.on_main_content_mousewheel, add="+")
        self.root.bind_all("<Button-5>", self.on_main_content_mousewheel, add="+")

    def on_stats_container_configure(self, _: tk.Event) -> None:
        self.update_stats_scroll_region()

    def on_stats_canvas_configure(self, event: tk.Event) -> None:
        if hasattr(self, "stats_canvas_window"):
            self.stats_canvas.itemconfigure(self.stats_canvas_window, width=event.width)
        self.update_stats_scroll_region()

    def update_stats_scroll_region(self) -> None:
        if not hasattr(self, "stats_canvas"):
            return
        try:
            bbox = self.stats_canvas.bbox("all")
            if bbox is not None:
                self.stats_canvas.configure(scrollregion=bbox)
        except tk.TclError:
            return

    def on_main_content_mousewheel(self, event: tk.Event) -> str | None:
        if self.compact_mode or not hasattr(self, "stats_canvas"):
            return None

        widget = event.widget
        try:
            if widget.winfo_toplevel() is not self.root:
                return None
        except tk.TclError:
            return None

        stats_root = getattr(self, "stats_scroll_host", None)
        if stats_root is None or not self._is_descendant_widget(widget, stats_root):
            return None

        widget_class = widget.winfo_class()
        if widget_class in {"Text", "TCombobox", "Combobox", "Entry", "TEntry", "Scale", "Listbox"}:
            return None

        try:
            bbox = self.stats_canvas.bbox("all")
            viewport_height = int(self.stats_canvas.winfo_height())
        except tk.TclError:
            return None
        if not bbox or (bbox[3] - bbox[1]) <= viewport_height:
            return None

        delta = 0
        event_num = getattr(event, "num", None)
        if event_num == 4:
            delta = -1
        elif event_num == 5:
            delta = 1
        else:
            raw_delta = int(getattr(event, "delta", 0))
            if raw_delta == 0:
                return None
            delta = -max(1, abs(raw_delta) // 120) if raw_delta > 0 else max(1, abs(raw_delta) // 120)

        try:
            self.stats_canvas.yview_scroll(delta, "units")
        except tk.TclError:
            return None
        return "break"

    @staticmethod
    def _is_descendant_widget(widget: tk.Misc, ancestor: tk.Misc) -> bool:
        current: tk.Misc | None = widget
        while current is not None:
            if current is ancestor:
                return True
            current = getattr(current, "master", None)
        return False

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
        self.set_output_lines(
            result,
            branch_total,
            snapshot.branch_deletions,
            snapshot.branch_active_days,
            snapshot.overall_active_days,
            snapshot.overall_deletions,
            snapshot.uncommitted_deletions,
            snapshot.daily_commit_count,
            snapshot.branch_commit_count,
            snapshot.overall_commit_count,
            snapshot.project_total_lines,
            snapshot.share_text,
            snapshot.user_cumulative_lines,
            snapshot.user_cumulative_deletions,
        )
        self.update_progress(
            result,
            snapshot.today_done,
            snapshot.today_target,
            snapshot.overall_progress_language_lines,
            snapshot.daily_progress_language_lines,
        )
        self.update_graph(
            snapshot.graph_added_points,
            snapshot.graph_deleted_points,
            snapshot.graph_commit_points,
            result.today,
        )
        uncommitted_today = result.uncommitted_insertions if result.today == dt.date.today() else 0
        self.update_grass(snapshot.grass_points, result.today, uncommitted_today)
        self.reset_commit_history_loader(result.today)

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
        if not self.capture_mode:
            self.show_error(error_message)

    def copy_output(self) -> None:
        if not self.current_output:
            return
        self.copy_to_clipboard(self.current_output, "status_clipboard")

    def copy_to_clipboard(self, text: str, status_key: str = "status_clipboard") -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status_var.set(self.t(status_key))

    def update_progress(
        self,
        result: TrackerResult,
        today_done: int,
        today_target: int,
        overall_language_lines: dict[str, int],
        daily_language_lines: dict[str, int],
    ) -> None:
        presentation = build_progress_presentation(
            main_committed=self.main_total_committed,
            branch_committed=self.branch_total_committed,
            uncommitted=result.uncommitted_insertions,
            goal=self.goal,
            today_done=today_done,
            today_target=today_target,
            translate=self.t,
        )
        self.overall_progress_text_var.set(presentation.breakdown_text)
        self.progress_bar_percents["overall"] = presentation.overall_percent
        self.progress_bar_percents["daily"] = presentation.daily_percent
        self.progress_bar_texts["overall"] = presentation.overall_bar_text
        self.progress_bar_texts["daily"] = presentation.daily_bar_text
        self.set_progress_language_lines(overall_language_lines, daily_language_lines)
        self.redraw_progress_bars()

    @staticmethod
    def format_progress_percent(percent: float, *, complete: bool) -> str:
        return format_progress_percent_value(percent, complete=complete)

    def graph_series_definitions(self) -> list[tuple[str, str, str, list[tuple[dt.date, int]], bool]]:
        return [
            (
                "additions",
                self.t("graph_series_additions"),
                self.theme.accent,
                self.graph_added_points,
                self.graph_show_additions_var.get(),
            ),
            (
                "deletions",
                self.t("graph_series_deletions"),
                self.theme.danger,
                self.graph_deleted_points,
                self.graph_show_deletions_var.get(),
            ),
            (
                "commits",
                self.t("graph_series_commits"),
                self.theme.accent_alt,
                self.graph_commit_points,
                self.graph_show_commits_var.get(),
            ),
        ]

    @staticmethod
    def summarize_graph_values(points: list[tuple[dt.date, int]]) -> tuple[float, int]:
        return summarize_graph_point_values(points)

    def refresh_graph_summary(self) -> None:
        summary_items: list[str] = []
        for _, label, _, points, enabled in self.graph_series_definitions():
            if not enabled:
                continue
            avg_value, max_value = self.summarize_graph_values(points)
            summary_items.append(
                self.t(
                    "graph_summary_item",
                    label=label,
                    avg=f"{avg_value:.1f}",
                    max=f"{max_value:,}",
                )
            )
        self.graph_summary_var.set(" | ".join(summary_items) if summary_items else self.t("graph_summary_empty"))

    def redraw_graph(self) -> None:
        self.refresh_graph_summary()
        self.draw_daily_graph(self.graph_highlight_day)

    def update_graph(
        self,
        added_points: list[tuple[dt.date, int]],
        deleted_points: list[tuple[dt.date, int]],
        commit_points: list[tuple[dt.date, int]],
        highlight_day: dt.date,
    ) -> None:
        self.graph_points = list(added_points)
        self.graph_added_points = list(added_points)
        self.graph_deleted_points = list(deleted_points)
        self.graph_commit_points = list(commit_points)
        self.graph_highlight_day = highlight_day
        self.redraw_graph()

    def update_grass(
        self,
        points: list[tuple[dt.date, int]],
        highlight_day: dt.date,
        uncommitted_today: int = 0,
    ) -> None:
        if self.grass_panel_controller is not None:
            self.grass_panel_controller.update(points, highlight_day, uncommitted_today)

    def update_commit_history(self, entries: list[CommitChangeEntry]) -> None:
        container = getattr(self, "commit_history_container", None)
        if container is None:
            return
        empty_label = getattr(self, "commit_history_empty_label", None)
        if empty_label is not None:
            empty_label.destroy()
            self.commit_history_empty_label = None
        for child in container.winfo_children():
            child.destroy()

        if not entries:
            empty_label = ttk.Label(
                self.commit_history_scroll_host,
                text=self.t("commit_history_empty"),
                style="CardLabel.TLabel",
            )
            empty_label.place(relx=0.5, rely=0.5, anchor="center")
            self.commit_history_empty_label = empty_label
            self.commit_history_scroll_panel.update_scroll_region()
            return

        for row_index, entry in enumerate(entries):
            row = ttk.Frame(container, style="CardInner.TFrame", padding=(0, 6))
            row.grid(row=row_index, column=0, sticky="ew", pady=(0, 2))
            row.columnconfigure(1, weight=1)

            date_text = entry.date.isoformat()[5:] if entry.date is not None else "--"
            meta_label = ttk.Label(row, text=f"{date_text} {entry.short_hash}", style="CardLabel.TLabel")
            meta_label.grid(row=0, column=0, sticky="w", padx=(0, 8))

            subject = entry.subject if entry.subject else entry.short_hash
            subject_label = ttk.Label(row, text=subject, style="CardTitle.TLabel", wraplength=170)
            subject_label.grid(row=0, column=1, sticky="ew", padx=(0, 8))

            add_label = ttk.Label(row, text=f"+{entry.insertions:,}", style="CardDeltaAdd.TLabel")
            add_label.grid(row=0, column=2, sticky="e", padx=(0, 6))

            delete_label = ttk.Label(row, text=f"-{entry.deletions:,}", style="CardDeltaRemove.TLabel")
            delete_label.grid(row=0, column=3, sticky="e")

        self.commit_history_scroll_panel.bind_content_tree()
        self.commit_history_scroll_panel.update_scroll_region()

    def reset_commit_history_loader(self, today: dt.date) -> None:
        try:
            tracked_ref = resolve_ref(self.repo, self.ref)
            current_ref = resolve_current_ref(self.repo)
            base_ref = resolve_base_commit(self.repo, today, self.base_commit, tracked_ref)
        except (OSError, RuntimeError):
            self.commit_history_refs = ("HEAD",)
            self.commit_history_exclude_ref = ""
            self.update_commit_history([])
            return

        snapshot = self.last_refresh_snapshot
        self.commit_history_refs = (
            snapshot.history_refs
            if snapshot is not None and snapshot.history_refs
            else (current_ref or tracked_ref,)
        )
        self.commit_history_exclude_ref = (
            snapshot.history_exclude_ref
            if snapshot is not None and snapshot.history_exclude_ref
            else base_ref
        )
        self.commit_history_entries = []
        self.commit_history_loading = False
        self.commit_history_exhausted = False
        self.commit_history_generation += 1
        self.update_commit_history([])
        self.load_next_commit_history_page()

    def on_commit_history_scroll(self, _first: float, last: float) -> None:
        if last >= 0.82:
            self.load_next_commit_history_page()

    def load_next_commit_history_page(self) -> None:
        if self.commit_history_loading or self.commit_history_exhausted or not self.repo_selected:
            return
        generation = self.commit_history_generation
        skip = len(self.commit_history_entries)
        self.commit_history_loading = True
        worker = threading.Thread(
            target=self._commit_history_worker,
            args=(generation, skip, COMMIT_HISTORY_PAGE_SIZE, self.commit_history_refs, self.commit_history_exclude_ref),
            daemon=True,
        )
        worker.start()

    def _commit_history_worker(
        self,
        generation: int,
        skip: int,
        limit: int,
        refs: tuple[str, ...],
        exclude_ref: str,
    ) -> None:
        try:
            entries = get_commit_change_entries(
                self.repo,
                self.author,
                refs,
                exclude_ref=exclude_ref or None,
                limit=limit,
                skip=skip,
            )
        except (OSError, RuntimeError):
            entries = []
        self.safe_after(lambda e=entries, g=generation: self._on_commit_history_page(g, e))

    def _on_commit_history_page(self, generation: int, entries: list[CommitChangeEntry]) -> None:
        if generation != self.commit_history_generation:
            return
        self.commit_history_loading = False
        if len(entries) < COMMIT_HISTORY_PAGE_SIZE:
            self.commit_history_exhausted = True
        if entries:
            seen = {entry.commit_hash for entry in self.commit_history_entries}
            self.commit_history_entries.extend(entry for entry in entries if entry.commit_hash not in seen)
        self.update_commit_history(self.commit_history_entries)

    def open_graph_settings_window(self) -> None:
        existing_window = self.graph_settings_window
        if existing_window is not None:
            try:
                if existing_window.winfo_exists():
                    self.refresh_graph_settings_window()
                    existing_window.deiconify()
                    existing_window.lift()
                    existing_window.focus_force()
                    return
            except tk.TclError:
                pass

        window = tk.Toplevel(self.root)
        window.resizable(False, False)
        window.transient(self.root)
        window.configure(bg=self.theme.border, padx=1, pady=1)
        if sys.platform == "win32":
            window.overrideredirect(True)
        window.protocol("WM_DELETE_WINDOW", self.close_graph_settings_window)
        window.bind("<Escape>", lambda _: self.close_graph_settings_window())
        window.columnconfigure(0, weight=1)
        window.rowconfigure(1, weight=1)
        self.graph_settings_window = window

        titlebar = ttk.Frame(window, style="TitleBar.TFrame", height=30, padding=(10, 5))
        titlebar.grid(row=0, column=0, sticky="ew")
        titlebar.grid_propagate(False)
        titlebar.columnconfigure(1, weight=1)
        self.graph_settings_titlebar = titlebar

        self.graph_settings_titlebar_accent = tk.Frame(titlebar, bg=self.theme.accent, width=4, height=16)
        self.graph_settings_titlebar_accent.grid(row=0, column=0, sticky="nsw", padx=(0, 8))

        self.graph_settings_title_label = ttk.Label(
            titlebar,
            text=self.t("graph_settings_title"),
            style="TitleBar.TLabel",
        )
        self.graph_settings_title_label.grid(row=0, column=1, sticky="w")

        self.graph_settings_close_button = ttk.Button(
            titlebar,
            text="X",
            command=self.close_graph_settings_window,
            style="TitleBarClose.TButton",
            width=3,
        )
        self.graph_settings_close_button.grid(row=0, column=2, sticky="e")
        for widget in (titlebar, self.graph_settings_titlebar_accent, self.graph_settings_title_label):
            widget.bind("<ButtonPress-1>", self.on_graph_settings_drag_start, add="+")
            widget.bind("<B1-Motion>", self.on_graph_settings_drag_motion, add="+")

        self.graph_settings_days_var = tk.StringVar(value=self.graph_days_var.get())
        self.graph_settings_show_additions_var = tk.BooleanVar(value=self.graph_show_additions_var.get())
        self.graph_settings_show_deletions_var = tk.BooleanVar(value=self.graph_show_deletions_var.get())
        self.graph_settings_show_commits_var = tk.BooleanVar(value=self.graph_show_commits_var.get())
        self.graph_settings_curve_var = tk.DoubleVar(value=self.graph_curve_var.get())

        card = ttk.Frame(window, style="App.TFrame", padding=(14, 12))
        card.grid(row=1, column=0, sticky="nsew")
        card.columnconfigure(1, weight=1)

        self.graph_settings_range_label = ttk.Label(card, style="CardLabel.TLabel")
        self.graph_settings_range_label.grid(row=0, column=0, sticky="w", padx=(0, 12))

        self.graph_settings_days_combo = ttk.Combobox(
            card,
            values=list(GRAPH_DAY_OPTIONS),
            textvariable=self.graph_settings_days_var,
            width=8,
            state="readonly",
            style="Tracker.TCombobox",
        )
        self.graph_settings_days_combo.grid(row=0, column=1, sticky="ew")
        self._bind_combobox_text_selection_clear(self.graph_settings_days_combo)

        self.graph_settings_metrics_label = ttk.Label(card, style="CardLabel.TLabel")
        self.graph_settings_metrics_label.grid(row=1, column=0, sticky="nw", padx=(0, 12), pady=(12, 0))

        flags_frame = tk.Frame(card, bd=0, highlightthickness=0, bg=self.theme.app_bg)
        flags_frame.grid(row=1, column=1, sticky="ew", pady=(12, 0))
        self.graph_settings_flags_frame = flags_frame
        for idx, series_name in enumerate(("additions", "deletions", "commits")):
            button = tk.Button(
                flags_frame,
                relief="flat",
                bd=0,
                highlightthickness=1,
                cursor="hand2",
                command=lambda name=series_name: self.toggle_graph_settings_series(name),
                padx=10,
                pady=4,
            )
            button.grid(row=0, column=idx, sticky="w", padx=(0, 8 if idx < 2 else 0))
            self.graph_settings_flag_buttons[series_name] = button

        self.graph_settings_curve_label = ttk.Label(card, style="CardLabel.TLabel")
        self.graph_settings_curve_label.grid(row=2, column=0, sticky="w", padx=(0, 12), pady=(12, 0))

        curve_row = ttk.Frame(card, style="App.TFrame")
        curve_row.grid(row=2, column=1, sticky="ew", pady=(12, 0))
        curve_row.columnconfigure(0, weight=1)

        self.graph_settings_curve_scale = tk.Scale(
            curve_row,
            orient="horizontal",
            from_=0,
            to=100,
            showvalue=False,
            sliderlength=14,
            width=7,
            borderwidth=0,
            highlightthickness=0,
            relief="flat",
            variable=self.graph_settings_curve_var,
            command=self.update_graph_curve_text,
        )
        self.graph_settings_curve_scale.grid(row=0, column=0, sticky="ew")

        self.graph_settings_curve_value_label = ttk.Label(curve_row, textvariable=self.graph_curve_text_var, style="Muted.TLabel")
        self.graph_settings_curve_value_label.grid(row=0, column=1, sticky="e", padx=(10, 0))

        self.graph_settings_apply_button = ttk.Button(card, command=self.apply_graph_settings)
        self.graph_settings_apply_button.grid(row=3, column=0, columnspan=2, sticky="e", pady=(14, 0))

        self.refresh_graph_settings_window()
        self.update_graph_curve_text(self.graph_settings_curve_var.get())
        try:
            self.root.update_idletasks()
            x = self.root.winfo_rootx() + 140
            y = self.root.winfo_rooty() + 110
            window.geometry(f"+{x}+{y}")
        except tk.TclError:
            pass
        window.lift()
        window.focus_force()

    def on_graph_settings_drag_start(self, event: tk.Event) -> str:
        window = self.graph_settings_window
        if window is not None:
            self.graph_settings_drag_x = event.x_root - window.winfo_x()
            self.graph_settings_drag_y = event.y_root - window.winfo_y()
        return "break"

    def on_graph_settings_drag_motion(self, event: tk.Event) -> str:
        window = self.graph_settings_window
        if window is not None:
            x = event.x_root - getattr(self, "graph_settings_drag_x", 0)
            y = event.y_root - getattr(self, "graph_settings_drag_y", 0)
            window.geometry(f"+{x}+{y}")
        return "break"

    def close_graph_settings_window(self) -> None:
        window = self.graph_settings_window
        self.graph_settings_window = None
        self.graph_settings_days_var = None
        self.graph_settings_show_additions_var = None
        self.graph_settings_show_deletions_var = None
        self.graph_settings_show_commits_var = None
        self.graph_settings_curve_var = None
        self.graph_settings_flags_frame = None
        self.graph_settings_flag_buttons = {}
        self.graph_settings_range_label = None
        self.graph_settings_metrics_label = None
        self.graph_settings_curve_label = None
        self.graph_settings_apply_button = None
        self.graph_settings_curve_value_label = None
        self.graph_settings_days_combo = None
        self.graph_settings_curve_scale = None
        if window is not None:
            try:
                window.destroy()
            except tk.TclError:
                pass

    def refresh_graph_settings_window(self) -> None:
        window = getattr(self, "graph_settings_window", None)
        if window is None:
            return
        try:
            if not window.winfo_exists():
                self.close_graph_settings_window()
                return
        except tk.TclError:
            self.close_graph_settings_window()
            return

        palette = self.theme
        window.title(self.t("graph_settings_title"))
        window.configure(bg=palette.border)
        if hasattr(self, "graph_settings_titlebar_accent"):
            self.graph_settings_titlebar_accent.configure(bg=palette.accent)
        if hasattr(self, "graph_settings_title_label"):
            self.graph_settings_title_label.configure(text=self.t("graph_settings_title"))
        if self.graph_settings_flags_frame is not None:
            self.graph_settings_flags_frame.configure(bg=palette.app_bg)
        if self.graph_settings_range_label is not None:
            self.graph_settings_range_label.configure(text=self.t("graph_period"))
        if self.graph_settings_metrics_label is not None:
            self.graph_settings_metrics_label.configure(text=self.t("graph_metrics"))
        if self.graph_settings_curve_label is not None:
            self.graph_settings_curve_label.configure(text=self.t("graph_curve"))
        if self.graph_settings_apply_button is not None:
            self.graph_settings_apply_button.configure(text=self.t("graph_apply"))
        if self.graph_settings_days_combo is not None:
            self.graph_settings_days_combo.configure(values=list(GRAPH_DAY_OPTIONS))
        if self.graph_settings_curve_scale is not None:
            self.graph_settings_curve_scale.configure(
                bg=palette.app_bg,
                troughcolor=palette.graph_grid,
                activebackground=palette.accent_light,
                highlightbackground=palette.app_bg,
                highlightcolor=palette.app_bg,
                fg=palette.text,
            )
        self.update_graph_curve_text(
            self.graph_settings_curve_var.get() if self.graph_settings_curve_var is not None else self.graph_curve_var.get()
        )
        self.refresh_graph_settings_flags()

    def refresh_graph_settings_flags(self) -> None:
        if not self.graph_settings_flag_buttons:
            return
        flag_config = {
            "additions": (
                self.t("graph_show_additions"),
                self.graph_settings_show_additions_var.get() if self.graph_settings_show_additions_var is not None else self.graph_show_additions_var.get(),
                self.theme.accent,
            ),
            "deletions": (
                self.t("graph_show_deletions"),
                self.graph_settings_show_deletions_var.get() if self.graph_settings_show_deletions_var is not None else self.graph_show_deletions_var.get(),
                self.theme.danger,
            ),
            "commits": (
                self.t("graph_show_commits"),
                self.graph_settings_show_commits_var.get() if self.graph_settings_show_commits_var is not None else self.graph_show_commits_var.get(),
                self.theme.accent_alt,
            ),
        }
        for series_name, button in self.graph_settings_flag_buttons.items():
            text, enabled, color = flag_config[series_name]
            bg = color if enabled else self.theme.card_bg
            fg = self.theme.button_text if enabled else self.theme.text
            active_bg = blend_hex(color, self.theme.accent_light, 0.18) if enabled else blend_hex(self.theme.card_bg, color, 0.18)
            border = blend_hex(color, self.theme.border, 0.25) if enabled else blend_hex(self.theme.border, color, 0.3)
            button.configure(
                text=text,
                bg=bg,
                fg=fg,
                activebackground=active_bg,
                activeforeground=fg,
                highlightcolor=border,
                highlightbackground=border,
                highlightthickness=1,
                disabledforeground=fg,
            )

    def toggle_graph_settings_series(self, series_name: str) -> None:
        if series_name == "additions" and self.graph_settings_show_additions_var is not None:
            self.graph_settings_show_additions_var.set(not self.graph_settings_show_additions_var.get())
        elif series_name == "deletions" and self.graph_settings_show_deletions_var is not None:
            self.graph_settings_show_deletions_var.set(not self.graph_settings_show_deletions_var.get())
        elif series_name == "commits" and self.graph_settings_show_commits_var is not None:
            self.graph_settings_show_commits_var.set(not self.graph_settings_show_commits_var.get())
        self.refresh_graph_settings_flags()

    def update_graph_curve_text(self, value: object) -> None:
        try:
            curve_value = float(value)
        except (TypeError, ValueError):
            curve_value = float(self.graph_curve_var.get())
        self.graph_curve_text_var.set(f"{int(round(curve_value))}%")

    def apply_graph_settings(self) -> None:
        days_var = self.graph_settings_days_var
        additions_var = self.graph_settings_show_additions_var
        deletions_var = self.graph_settings_show_deletions_var
        commits_var = self.graph_settings_show_commits_var
        curve_var = self.graph_settings_curve_var
        if days_var is None or additions_var is None or deletions_var is None or commits_var is None or curve_var is None:
            return

        next_days = days_var.get().strip()
        if next_days not in GRAPH_DAY_OPTIONS:
            next_days = self.graph_days_var.get()

        show_additions = additions_var.get()
        show_deletions = deletions_var.get()
        show_commits = commits_var.get()
        if not (show_additions or show_deletions or show_commits):
            self.show_error(self.t("graph_summary_empty"))
            return

        next_curve = min(max(float(curve_var.get()), 0.0), 100.0)
        refresh_required = next_days != self.graph_days_var.get()

        self.graph_days_var.set(next_days)
        self.graph_show_additions_var.set(show_additions)
        self.graph_show_deletions_var.set(show_deletions)
        self.graph_show_commits_var.set(show_commits)
        self.graph_curve_var.set(next_curve)
        self.update_graph_curve_text(next_curve)
        self.save_settings()
        self.redraw_graph()
        if refresh_required:
            self.refresh()

    @staticmethod
    def _flatten_graph_points(points: list[tuple[float, float]]) -> list[float]:
        return flatten_graph_screen_points(points)

    @staticmethod
    def _smooth_graph_points(points: list[tuple[float, float]], curve_strength: float) -> list[tuple[float, float]]:
        return smooth_graph_screen_points(points, curve_strength)

    def draw_daily_graph(self, highlight_day: dt.date | None) -> None:
        canvas = self.graph_canvas
        palette = self.theme
        canvas.delete("all")

        width = max(1, int(canvas.winfo_width() or canvas.cget("width")))
        height = max(1, int(canvas.winfo_height() or canvas.cget("height")))
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

        active_series = [
            (series_name, label, color, points)
            for series_name, label, color, points, enabled in self.graph_series_definitions()
            if enabled
        ]
        if not active_series:
            canvas.create_text(
                width / 2,
                height / 2,
                text=self.t("graph_summary_empty"),
                fill=palette.muted_text,
                font=("Bahnschrift", 10),
            )
            return

        values = [value for _, _, _, points in active_series for _, value in points]
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

        points = active_series[0][3]
        slot_w = chart_w / max(len(points), 1)
        label_step = max(1, math.ceil(len(points) / 6)) if points else 1
        y_base = margin_top + chart_h
        label_y = min(height - 2, y_base + 6)
        curve_strength = min(max(float(self.graph_curve_var.get()), 0.0), 100.0)

        for series_name, _, color, series_points in active_series:
            point_pairs: list[tuple[float, float]] = []
            for idx, (_, value) in enumerate(series_points):
                x = margin_left + idx * slot_w + slot_w / 2
                y = y_base - (value / y_top) * chart_h if y_top > 0 else y_base
                point_pairs.append((x, y))

            draw_pairs = self._smooth_graph_points(point_pairs, curve_strength)
            draw_points = self._flatten_graph_points(draw_pairs)

            if len(draw_points) >= 4:
                line_kwargs = {
                    "fill": color,
                    "width": 2,
                    "capstyle": tk.ROUND,
                    "joinstyle": tk.ROUND,
                }
                if series_name == "commits":
                    line_kwargs["dash"] = (4, 2)
                canvas.create_line(*draw_points, **line_kwargs)

            for idx, (day, value) in enumerate(series_points):
                x = margin_left + idx * slot_w + slot_w / 2
                y = y_base - (value / y_top) * chart_h if y_top > 0 else y_base
                radius = 4 if day == highlight_day else 2
                outline = palette.canvas_bg if day == highlight_day else ""
                outline_width = 1 if day == highlight_day else 0
                canvas.create_oval(
                    x - radius,
                    y - radius,
                    x + radius,
                    y + radius,
                    fill=color,
                    outline=outline,
                    width=outline_width,
                )

        for idx, (day, _value) in enumerate(points):
            x = margin_left + idx * slot_w + slot_w / 2
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
        self.schedule_signature = None
        self.ref = resolve_ref(self.repo, "auto")
        self.rebuild_author_controls(reset_invalid_to_auto=True)
        clear_cache_for_repo(self.repo)
        self.update_repo_dependent_controls()
        self.save_settings()
        self.refresh_schedule(force=True)
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
        self.refresh_coordinator.invalidate()
        self.save_settings()
        self.cancel_auto_refresh()
        self.cancel_schedule_poll()
        self.cancel_compact_clock()
        self.hide_progress_language_tooltip()
        self.close_app_settings_window()
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
