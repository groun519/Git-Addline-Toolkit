#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import math
import re
import subprocess
import sys
import threading
import tkinter as tk
from typing import Iterable
from pathlib import Path
from tkinter import messagebox, ttk

from line_tracker import (
    DEFAULT_AUTHOR,
    DEFAULT_BASE_COMMIT,
    DEFAULT_BASE_TOTAL,
    DEFAULT_GOAL,
    TrackerConfig,
    TrackerResult,
    compute_metrics,
    format_output_lines,
    get_committed_insertions_by_date,
    get_committed_insertions_for_date,
    get_committed_insertions_by_date_combined,
    get_committed_insertions_for_date_combined,
    get_committed_insertions,
    clear_cache_for_repo,
    find_repo_root,
    get_total_insertions_up_to,
    get_uncommitted_deletions,
    run_git,
    resolve_author,
    resolve_base_commit,
    resolve_current_ref,
    resolve_ref,
)

AUTO_REFRESH_MS = 60_000
GRAPH_CANVAS_WIDTH = 420
GRAPH_CANVAS_HEIGHT = 140
BAR_LENGTH = 420
GRAPH_CARD_WIDTH = GRAPH_CANVAS_WIDTH + 24
SETTINGS_FILE_NAME = "line_tracker_ui_settings.json"

COLOR_BG = "#151a18"
COLOR_CARD = "#1f2522"
COLOR_BORDER = "#2e3833"
COLOR_TEXT = "#e8ebe7"
COLOR_MUTED = "#b0b8b2"
COLOR_ACCENT = "#6bb29a"
COLOR_ACCENT_DARK = "#5aa18a"
COLOR_ACCENT_LIGHT = "#8cc7b3"
COLOR_ACCENT2 = "#d4a261"
COLOR_ACCENT2_DARK = "#c69254"
COLOR_GREEN = "#76c7a1"
COLOR_RED = "#d36f6f"
COLOR_CANVAS_BG = "#1a201d"

FONT_TITLE = ("Bahnschrift", 18, "bold")
FONT_SUBTITLE = ("Bahnschrift", 10)
FONT_BODY = ("Bahnschrift", 10)
FONT_SECTION = ("Bahnschrift", 11, "bold")
FONT_TILE_LABEL = ("Bahnschrift", 9)
FONT_TILE_VALUE = ("Bahnschrift", 12, "bold")
FONT_CHIP = ("Bahnschrift", 9)
FONT_MONO = ("Cascadia Mono", 10)


def parse_date(value: str) -> dt.date:
    return dt.date.fromisoformat(value)


def _xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def show_windows_toast(title: str, message: str) -> None:
    title = _xml_escape(title)
    message = _xml_escape(message)
    ps_script = f"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] > $null
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml('<toast><visual><binding template="ToastGeneric"><text>{title}</text><text>{message}</text></binding></visual></toast>')
$toast = New-Object Windows.UI.Notifications.ToastNotification $xml
$notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Line Tracker')
$notifier.Show($toast)
"""
    try:
        encoded = base64.b64encode(ps_script.encode("utf-16le")).decode("ascii")
        kwargs: dict[str, object] = {}
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        subprocess.Popen(
            ["powershell", "-NoProfile", "-EncodedCommand", encoded],
            **kwargs,
        )
    except Exception:
        pass


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
    def __init__(self, root: tk.Tk, args: argparse.Namespace) -> None:
        self.root = root
        self.repo = find_repo_root(Path(args.repo)).resolve()
        self.goal = args.goal
        self.base_total = args.base_total
        self.base_commit = args.base_commit
        self.author_raw = ""
        self.author_raw = args.author
        self.author = resolve_author(self.repo, args.author)
        self.ref = resolve_ref(self.repo, args.ref)
        self.today = args.today
        self.month_end = args.month_end
        self.settings_path = Path(__file__).resolve().with_name(SETTINGS_FILE_NAME)
        self.settings = self.load_settings()
        saved_geometry = str(self.settings.get("geometry", "")).strip()
        default_width = 1300
        default_height = 680
        min_height = 620
        width = default_width
        height = default_height
        if saved_geometry:
            try:
                size_part = saved_geometry.split("+", 1)[0]
                w_str, h_str = size_part.split("x", 1)
                width = min(max(int(w_str), default_width), default_width)
                height = min(max(int(h_str), min_height), default_height)
            except (ValueError, IndexError):
                width = default_width
                height = default_height
        else:
            screen_w = self.root.winfo_screenwidth()
            if screen_w:
                width = default_width
        self.root.geometry(f"{width}x{height}")
        self.root.minsize(default_width, min_height)

        saved_goal = self._coerce_positive_int(self.settings.get("goal"), self.goal)
        saved_graph_days = str(self.settings.get("graph_days", "14"))
        if saved_graph_days not in {"7", "14", "21", "30", "60", "90", "180"}:
            saved_graph_days = "14"
        saved_author = str(self.settings.get("author", args.author)).strip()
        saved_author_display = str(self.settings.get("author_display", "")).strip()
        saved_custom_today_enabled = bool(self.settings.get("custom_today_enabled", bool(args.today)))
        default_today_text = args.today.isoformat() if args.today else dt.date.today().isoformat()
        saved_today_text = str(self.settings.get("custom_today", default_today_text)).strip() or default_today_text
        saved_auto_refresh = bool(self.settings.get("auto_refresh", False))
        saved_notify_on_goal = bool(self.settings.get("notify_on_goal", False))
        saved_last_notify_date = str(self.settings.get("last_notify_date", "")).strip()
        saved_note_title = str(self.settings.get("note_title", "")).strip()
        saved_note_done = str(self.settings.get("note_done", ""))
        saved_note_todo = str(self.settings.get("note_todo", ""))
        saved_auto_stage = bool(self.settings.get("auto_stage", False))

        self.goal = saved_goal
        self.author_options, self.author_filter_map = self.build_author_options()
        display_value = saved_author_display or self.map_author_to_display(saved_author or args.author)
        self.author_raw = self.author_filter_map.get(display_value, saved_author or args.author)
        self.author_display = display_value
        self.author = resolve_author(self.repo, self.author_raw)

        self.root.title("PROJECT-MA Line Tracker")
        self.root.resizable(True, False)
        self.root.configure(bg=COLOR_BG)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        self.style = ttk.Style(self.root)
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass
        self.style.configure("App.TFrame", background=COLOR_BG)
        self.style.configure("Card.TFrame", background=COLOR_CARD, borderwidth=1, relief="solid")
        self.style.configure("CardInner.TFrame", background=COLOR_CARD, borderwidth=0, relief="flat")
        self.style.configure("DeltaBox.TFrame", background=COLOR_CARD, borderwidth=1, relief="solid")
        self.style.configure("Title.TLabel", background=COLOR_BG, foreground=COLOR_TEXT, font=FONT_TITLE)
        self.style.configure("Subtitle.TLabel", background=COLOR_BG, foreground=COLOR_MUTED, font=FONT_SUBTITLE)
        self.style.configure("Section.TLabel", background=COLOR_BG, foreground=COLOR_TEXT, font=FONT_SECTION)
        self.style.configure("CardTitle.TLabel", background=COLOR_CARD, foreground=COLOR_TEXT, font=FONT_BODY)
        self.style.configure("CardLabel.TLabel", background=COLOR_CARD, foreground=COLOR_MUTED, font=FONT_BODY)
        self.style.configure("Stat.TLabel", background=COLOR_CARD, foreground=COLOR_TEXT, font=FONT_MONO)
        self.style.configure("Muted.TLabel", background=COLOR_BG, foreground=COLOR_MUTED, font=FONT_BODY)
        self.style.configure("Tile.TFrame", background=COLOR_CARD, borderwidth=1, relief="solid")
        self.style.configure("TileLabel.TLabel", background=COLOR_CARD, foreground=COLOR_MUTED, font=FONT_TILE_LABEL)
        self.style.configure(
            "TileValue.TLabel",
            background=COLOR_CARD,
            foreground=COLOR_TEXT,
            font=FONT_TILE_VALUE,
        )
        self.style.configure("Chip.TFrame", background=COLOR_CARD, borderwidth=1, relief="solid")
        self.style.configure("ChipLabel.TLabel", background=COLOR_CARD, foreground=COLOR_MUTED, font=FONT_CHIP)
        self.style.configure("ChipValue.TLabel", background=COLOR_CARD, foreground=COLOR_TEXT, font=FONT_CHIP)
        self.style.configure("TCheckbutton", background=COLOR_CARD, foreground=COLOR_TEXT, font=FONT_BODY)
        self.style.map("TCheckbutton", background=[("active", COLOR_CARD)])
        self.style.configure("TEntry", fieldbackground=COLOR_CARD, foreground=COLOR_TEXT, font=FONT_BODY)
        self.style.configure(
            "TCombobox",
            fieldbackground=COLOR_CARD,
            background=COLOR_CARD,
            foreground=COLOR_TEXT,
            arrowcolor=COLOR_TEXT,
            font=FONT_BODY,
        )
        self.style.map(
            "TCombobox",
            fieldbackground=[("readonly", COLOR_CARD)],
            background=[("readonly", COLOR_CARD)],
            foreground=[("readonly", COLOR_TEXT)],
            arrowcolor=[("readonly", COLOR_TEXT)],
        )
        self.root.option_add("*TCombobox*Listbox*Background", COLOR_CARD)
        self.root.option_add("*TCombobox*Listbox*Foreground", COLOR_TEXT)
        self.root.option_add("*TCombobox*Listbox*selectBackground", COLOR_ACCENT_DARK)
        self.root.option_add("*TCombobox*Listbox*selectForeground", COLOR_TEXT)
        self.style.configure("TButton", font=FONT_BODY)
        self.style.configure(
            "Accent.TButton",
            font=FONT_BODY,
            foreground="#ffffff",
            background=COLOR_ACCENT,
            padding=(12, 6),
        )
        self.style.map(
            "Accent.TButton",
            background=[("active", COLOR_ACCENT_DARK), ("disabled", COLOR_ACCENT_LIGHT)],
            foreground=[("disabled", "#f0f0f0")],
        )
        self.style.configure(
            "Overall.Horizontal.TProgressbar",
            troughcolor="#27302b",
            background=COLOR_ACCENT,
            lightcolor=COLOR_ACCENT,
            darkcolor=COLOR_ACCENT,
        )
        self.style.configure(
            "Daily.Horizontal.TProgressbar",
            troughcolor="#2b2620",
            background=COLOR_ACCENT2,
            lightcolor=COLOR_ACCENT2,
            darkcolor=COLOR_ACCENT2,
        )

        container = ttk.Frame(self.root, padding=14, style="App.TFrame")
        container.grid(row=0, column=0, sticky="nsew")
        container.columnconfigure(0, weight=0)
        container.columnconfigure(1, weight=0)
        container.columnconfigure(2, weight=0)

        self.auto_refresh_job: str | None = None
        self.refresh_request_id = 0
        self.refresh_in_progress = False
        self.today_override: dt.date | None = args.today if saved_custom_today_enabled else None
        self.meta_label_vars = [tk.StringVar(value="") for _ in range(2)]
        self.meta_value_vars = [tk.StringVar(value="") for _ in range(2)]
        self.tile_label_vars = [tk.StringVar(value="") for _ in range(5)]
        self.tile_value_vars = [tk.StringVar(value="") for _ in range(5)]
        self.delta_var = tk.StringVar(value="+0 / -0")
        self.notify_var = tk.BooleanVar(value=saved_notify_on_goal)
        self.current_ref = resolve_current_ref(self.repo)
        self.last_notify_date = saved_last_notify_date
        self.main_total_committed = 0
        self.branch_total_committed = 0
        self.note_title_var = tk.StringVar(value=saved_note_title)
        self.note_done_initial = saved_note_done
        self.note_todo_initial = saved_note_todo
        self.auto_stage_var = tk.BooleanVar(value=saved_auto_stage)

        header_frame = ttk.Frame(container, style="App.TFrame")
        header_frame.grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 10))
        accent_bar = tk.Frame(header_frame, bg=COLOR_ACCENT, width=6, height=34)
        accent_bar.grid(row=0, column=0, rowspan=2, sticky="ns", padx=(0, 10))
        self.title_label = ttk.Label(header_frame, text="Line Tracker", style="Title.TLabel")
        self.title_label.grid(row=0, column=1, sticky="w")
        self.subtitle_label = ttk.Label(
            header_frame,
            text=self.format_ref_label(),
            style="Subtitle.TLabel",
        )
        self.subtitle_label.grid(row=1, column=1, sticky="w", pady=(2, 0))

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

        tile_grid = ttk.Frame(output_section, style="App.TFrame")
        tile_grid.grid(row=1, column=0, sticky="ew")
        tile_grid.columnconfigure(0, weight=1, uniform="tile")
        tile_grid.columnconfigure(1, weight=1, uniform="tile")

        tile_accents = [
            COLOR_ACCENT2,
            COLOR_ACCENT,
            COLOR_ACCENT_LIGHT,
            COLOR_ACCENT_DARK,
            COLOR_ACCENT2_DARK,
        ]
        tile_positions = [
            (0, 0, 1),
            (0, 1, 1),
            (1, 0, 1),
            (1, 1, 1),
            (2, 0, 2),
        ]
        for idx in range(5):
            row, col, colspan = tile_positions[idx]
            tile = ttk.Frame(tile_grid, style="Tile.TFrame", padding=(10, 8))
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

            label = ttk.Label(tile, textvariable=self.tile_label_vars[idx], style="TileLabel.TLabel", wraplength=200)
            label.grid(row=0, column=1, sticky="w")

            value = ttk.Label(tile, textvariable=self.tile_value_vars[idx], style="TileValue.TLabel")
            value.grid(row=1, column=1, sticky="w", pady=(2, 0))

        delta_card = ttk.Frame(output_section, style="Card.TFrame", padding=(10, 8))
        delta_card.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        delta_card.columnconfigure(1, weight=1)

        self.delta_label = ttk.Label(delta_card, text="현재 변경", style="CardTitle.TLabel")
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
        self.delta_added_label.configure(foreground=COLOR_GREEN)

        self.delta_removed_box = ttk.Frame(self.delta_value_frame, style="DeltaBox.TFrame", padding=(8, 4))
        self.delta_removed_box.grid(row=0, column=1)

        self.delta_removed_label = ttk.Label(
            self.delta_removed_box,
            textvariable=self.delta_removed_var,
            style="Stat.TLabel",
        )
        self.delta_removed_label.grid(row=0, column=0, sticky="e")
        self.delta_removed_label.configure(foreground=COLOR_RED)

        progress_section = ttk.Frame(container, style="App.TFrame")
        progress_section.grid(row=2, column=0, sticky="ew", padx=(0, 10), pady=(10, 0))
        progress_section.columnconfigure(0, weight=1)

        self.progress_title = ttk.Label(progress_section, text="진행률", style="Section.TLabel")
        self.progress_title.grid(row=0, column=0, sticky="w", pady=(0, 6))

        progress_card = ttk.Frame(progress_section, style="Card.TFrame", padding=(12, 10))
        progress_card.grid(row=1, column=0, sticky="ew")

        self.overall_progress_title = ttk.Label(progress_card, text="전체 진행률", style="CardTitle.TLabel")
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

        self.daily_progress_title = ttk.Label(progress_card, text="일일 진행률", style="CardTitle.TLabel")
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

        right_area = ttk.Frame(container, style="App.TFrame")
        right_area.grid(row=1, column=2, rowspan=2, sticky="nw", padx=(14, 0))
        right_area.columnconfigure(0, weight=0, minsize=GRAPH_CARD_WIDTH)
        right_area.columnconfigure(1, weight=0)

        graph_section = ttk.Frame(right_area, style="App.TFrame")
        graph_section.grid(row=0, column=0, sticky="nw", padx=(0, 10))
        graph_section.columnconfigure(0, weight=1)

        graph_header = ttk.Frame(graph_section, style="App.TFrame")
        graph_header.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        graph_header.columnconfigure(0, weight=1)

        self.graph_title = ttk.Label(graph_header, text="일별 추가줄 그래프", style="Section.TLabel")
        self.graph_title.grid(row=0, column=0, sticky="w")

        self.graph_days_var = tk.StringVar(value=saved_graph_days)
        self.graph_days_label = ttk.Label(graph_header, text="기간", style="Muted.TLabel")
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
            bg=COLOR_CANVAS_BG,
            highlightthickness=1,
            highlightbackground=COLOR_BORDER,
        )
        self.graph_canvas.grid(row=0, column=0, sticky="ew", pady=(2, 0))

        self.graph_summary_var = tk.StringVar(value="")
        self.graph_summary_label = ttk.Label(graph_card, textvariable=self.graph_summary_var, style="CardLabel.TLabel")
        self.graph_summary_label.grid(row=1, column=0, sticky="w", pady=(6, 0))

        note_section = ttk.Frame(right_area, style="App.TFrame")
        note_section.grid(row=0, column=1, rowspan=2, sticky="nw", padx=(10, 0))
        note_section.columnconfigure(0, weight=1)

        self.note_title_label = ttk.Label(note_section, text="커밋 메모", style="Section.TLabel")
        self.note_title_label.grid(row=0, column=0, sticky="w", pady=(0, 6))

        note_card = ttk.Frame(note_section, style="Card.TFrame", padding=(12, 10))
        note_card.grid(row=1, column=0, sticky="ew")
        note_card.columnconfigure(0, weight=1)

        self.note_title_text_label = ttk.Label(note_card, text="제목", style="CardLabel.TLabel")
        self.note_title_text_label.grid(row=0, column=0, sticky="w")

        self.note_title_entry = ttk.Entry(note_card, textvariable=self.note_title_var, width=34)
        self.note_title_entry.grid(row=1, column=0, sticky="ew", pady=(4, 6))

        self.note_done_label = ttk.Label(note_card, text="DONE", style="CardLabel.TLabel")
        self.note_done_label.grid(row=2, column=0, sticky="w")

        self.note_done_text = tk.Text(
            note_card,
            height=8,
            width=34,
            font=FONT_BODY,
            bg=COLOR_CARD,
            fg=COLOR_TEXT,
            insertbackground=COLOR_TEXT,
            relief="solid",
            bd=1,
            highlightthickness=1,
            highlightbackground=COLOR_BORDER,
        )
        self.note_done_text.grid(row=3, column=0, sticky="ew", pady=(4, 6))
        if self.note_done_initial:
            self.note_done_text.insert("1.0", self.note_done_initial)

        self.note_todo_label = ttk.Label(note_card, text="TODO", style="CardLabel.TLabel")
        self.note_todo_label.grid(row=4, column=0, sticky="w")

        self.note_todo_text = tk.Text(
            note_card,
            height=12,
            width=34,
            font=FONT_BODY,
            bg=COLOR_CARD,
            fg=COLOR_TEXT,
            insertbackground=COLOR_TEXT,
            relief="solid",
            bd=1,
            highlightthickness=1,
            highlightbackground=COLOR_BORDER,
        )
        self.note_todo_text.grid(row=5, column=0, sticky="ew", pady=(4, 8))
        if self.note_todo_initial:
            self.note_todo_text.insert("1.0", self.note_todo_initial)

        self.auto_stage_check = ttk.Checkbutton(
            note_card,
            text="자동 스테이지(git add -A)",
            variable=self.auto_stage_var,
            command=self.save_settings,
        )
        self.auto_stage_check.grid(row=6, column=0, sticky="w", pady=(0, 6))

        note_actions = ttk.Frame(note_card, style="Card.TFrame")
        note_actions.grid(row=7, column=0, sticky="e")

        self.note_save_button = ttk.Button(note_actions, text="메모 저장", command=self.save_settings)
        self.note_save_button.grid(row=0, column=0, sticky="e")

        self.commit_button = ttk.Button(note_actions, text="커밋", command=self.commit_notes, style="Accent.TButton")
        self.commit_button.grid(row=0, column=1, sticky="e", padx=(8, 0))


        self.custom_today_var = tk.BooleanVar(value=saved_custom_today_enabled)
        self.today_entry_var = tk.StringVar(value=saved_today_text)
        controls_section = ttk.Frame(right_area, style="App.TFrame")
        controls_section.grid(row=1, column=0, sticky="ew", padx=(0, 10), pady=(10, 0))
        controls_section.columnconfigure(0, weight=1, minsize=GRAPH_CARD_WIDTH)

        self.controls_title = ttk.Label(controls_section, text="설정", style="Section.TLabel")
        self.controls_title.grid(row=0, column=0, sticky="w", pady=(0, 6))

        controls_card = ttk.Frame(controls_section, style="Card.TFrame", padding=(12, 10))
        controls_card.grid(row=1, column=0, sticky="ew")

        self.custom_today_check = ttk.Checkbutton(
            controls_card,
            text="날짜 커스텀(YYYY-MM-DD)",
            variable=self.custom_today_var,
            command=self.on_custom_date_toggle,
        )
        self.custom_today_check.grid(row=0, column=0, columnspan=3, sticky="w", pady=(8, 0))
        controls_card.columnconfigure(0, weight=1)
        controls_card.columnconfigure(1, weight=0)

        self.today_entry = ttk.Entry(controls_card, textvariable=self.today_entry_var, width=14)
        self.today_entry.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self.today_entry.bind("<Return>", self.on_today_entry_enter)

        self.today_apply_button = ttk.Button(controls_card, text="날짜 적용", command=self.apply_custom_date)
        self.today_apply_button.grid(row=1, column=1, sticky="e", padx=(8, 0), pady=(4, 0))

        self.goal_entry_var = tk.StringVar(value=str(self.goal))
        self.goal_label = ttk.Label(controls_card, text="목표 줄수", style="CardLabel.TLabel")
        self.goal_label.grid(row=2, column=0, sticky="w", pady=(10, 0))

        self.goal_entry = ttk.Entry(controls_card, textvariable=self.goal_entry_var, width=14)
        self.goal_entry.grid(row=3, column=0, sticky="ew", pady=(4, 0))
        self.goal_entry.bind("<Return>", self.on_goal_entry_enter)

        self.goal_apply_button = ttk.Button(controls_card, text="목표 적용", command=self.apply_goal)
        self.goal_apply_button.grid(row=3, column=1, sticky="e", padx=(8, 0), pady=(4, 0))

        self.author_entry_var = tk.StringVar(value=self.author_display)
        self.author_label = ttk.Label(controls_card, text="저자 선택", style="CardLabel.TLabel")
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

        self.author_apply_button = ttk.Button(controls_card, text="저자 적용", command=self.apply_author)
        self.author_apply_button.grid(row=5, column=1, sticky="e", padx=(8, 0), pady=(4, 0))

        self.auto_refresh_var = tk.BooleanVar(value=saved_auto_refresh)
        self.auto_refresh_check = ttk.Checkbutton(
            controls_card,
            text="1분마다 자동 업데이트",
            variable=self.auto_refresh_var,
            command=self.on_auto_refresh_toggle,
        )
        self.auto_refresh_check.grid(row=6, column=0, columnspan=3, sticky="w", pady=(10, 0))

        self.notify_check = ttk.Checkbutton(
            controls_card,
            text="일일 목표 달성 알림",
            variable=self.notify_var,
            command=self.on_notify_toggle,
        )
        self.notify_check.grid(row=7, column=0, columnspan=3, sticky="w", pady=(6, 0))

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

        self.loading_var = tk.StringVar(value="새로고침 중...")
        self.loading_label = ttk.Label(footer_left, textvariable=self.loading_var, style="Muted.TLabel")
        self.loading_bar = ttk.Progressbar(
            footer_left,
            orient="horizontal",
            mode="indeterminate",
            length=180,
        )
        self.loading_label.grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.loading_bar.grid(row=1, column=1, sticky="w", padx=(6, 0), pady=(6, 0))
        self.loading_label.grid_remove()
        self.loading_bar.grid_remove()

        self.refresh_button = ttk.Button(footer_right, text="새로고침", command=self.refresh, style="Accent.TButton")
        self.refresh_button.grid(row=0, column=0, sticky="e")

        self.copy_button = ttk.Button(footer_right, text="복사", command=self.copy_output)
        self.copy_button.grid(row=0, column=1, sticky="e", padx=(8, 0))

        self.current_output = ""
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.apply_date_controls_state()
        if self.custom_today_var.get():
            try:
                self.today_override = self.parse_today_entry()
            except ValueError:
                self.today_override = args.today
                self.today_entry_var.set(default_today_text)
        self.refresh()
        self.save_settings()

    def build_config(self) -> TrackerConfig:
        return TrackerConfig(
            repo=self.repo,
            goal=self.goal,
            base_total=self.base_total,
            base_commit=self.base_commit,
            author=self.author,
            ref=self.ref,
            include_local=True,
            today=self.today_override if self.custom_today_var.get() else None,
            month_end=self.month_end,
            assume_uncommitted_zero=False,
        )

    def format_ref_label(self) -> str:
        label = f"{self.repo.name} • {self.ref}"
        current = resolve_current_ref(self.repo)
        self.current_ref = current
        if current != self.ref:
            return f"{self.repo.name} • {self.ref} + {current}"
        return label

    def build_author_options(self) -> tuple[list[str], dict[str, str]]:
        options = ["자동(내 계정)", "전체"]
        mapping = {"자동(내 계정)": "auto", "전체": ""}
        try:
            out = run_git(self.repo, ["shortlog", "-sne", "--all"])
        except RuntimeError:
            return options, mapping

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
            if not identity or identity in mapping:
                continue
            mapping[identity] = re.escape(identity)
            options.append(identity)
        return options, mapping

    def map_author_to_display(self, author_raw: str) -> str:
        if not author_raw:
            return "전체"
        if author_raw.lower() == "auto":
            return "자동(내 계정)"
        for display, filt in self.author_filter_map.items():
            if filt == author_raw:
                return display
        return author_raw

    def refresh_ref_label(self) -> None:
        self.subtitle_label.configure(text=self.format_ref_label())

    @staticmethod
    def _coerce_positive_int(value: object, default: int) -> int:
        try:
            parsed = int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return default
        return parsed if parsed > 0 else default

    def load_settings(self) -> dict[str, object]:
        if not self.settings_path.exists():
            return {}
        try:
            raw = self.settings_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            if isinstance(data, dict):
                return data
            return {}
        except (OSError, json.JSONDecodeError):
            return {}

    def save_settings(self) -> None:
        note_title = self.note_title_var.get().strip() if hasattr(self, "note_title_var") else ""
        note_done = ""
        note_todo = ""
        if hasattr(self, "note_done_text"):
            note_done = self.note_done_text.get("1.0", "end-1c")
        if hasattr(self, "note_todo_text"):
            note_todo = self.note_todo_text.get("1.0", "end-1c")
        data = {
            "goal": self.goal,
            "custom_today_enabled": self.custom_today_var.get(),
            "custom_today": self.today_entry_var.get().strip(),
            "graph_days": self.graph_days_var.get(),
            "auto_refresh": self.auto_refresh_var.get(),
            "notify_on_goal": self.notify_var.get(),
            "last_notify_date": self.last_notify_date,
            "author": self.author_raw,
            "author_display": self.author_display,
            "note_title": note_title,
            "note_done": note_done,
            "note_todo": note_todo,
            "auto_stage": self.auto_stage_var.get() if hasattr(self, "auto_stage_var") else False,
            "geometry": self.root.winfo_geometry(),
        }
        try:
            self.settings_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            # UI 동작은 계속 유지하고, 저장 실패만 무시한다.
            pass

    def set_output_lines(
        self,
        lines: list[str],
        branch_total: int | None = None,
        share_text: str = "",
    ) -> None:
        def split_line(raw: str) -> tuple[str, str]:
            text = raw.strip()
            if text.startswith("-"):
                text = text[1:].strip()
            if ":" in text:
                label, value = text.split(":", 1)
                return label.strip(), value.strip()
            return text, ""

        meta_lines = lines[:2]
        daily_line = lines[2] if len(lines) > 2 else ""
        current_line = lines[3] if len(lines) > 3 else ""

        for idx in range(2):
            if idx < len(meta_lines):
                label, value = split_line(meta_lines[idx])
            else:
                label, value = "", ""
            self.meta_label_vars[idx].set(label)
            self.meta_value_vars[idx].set(value)

        daily_label, daily_value_raw = split_line(daily_line)
        commit_value = ""
        daily_value = daily_value_raw
        if "[" in daily_value_raw and "]" in daily_value_raw:
            before, bracket = daily_value_raw.split("[", 1)
            daily_value = before.strip()
            bracket_text = bracket.split("]", 1)[0].strip()
            if bracket_text.startswith("커밋 후"):
                commit_value = bracket_text.replace("커밋 후", "", 1).strip()
            else:
                commit_value = bracket_text

        current_label, current_value = split_line(current_line)

        branch_value = f"{branch_total:,}줄" if branch_total is not None else ""
        tiles = [
            (daily_label, daily_value),
            ("커밋 후 일일 필요 추가줄", commit_value),
            ("현재 브랜치 단독 추가줄(커밋)", branch_value),
            (current_label, current_value),
            ("내 추가줄 비중(전체 대비)", share_text),
        ]

        for idx in range(5):
            label, value = tiles[idx] if idx < len(tiles) else ("", "")
            if idx == 1 and not value:
                label = ""
            self.tile_label_vars[idx].set(label)
            self.tile_value_vars[idx].set(value)

    def parse_today_entry(self) -> dt.date:
        value = self.today_entry_var.get().strip()
        try:
            return dt.date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("날짜 형식은 YYYY-MM-DD 로 입력하세요.") from exc

    def parse_goal_entry(self) -> int:
        value = self.goal_entry_var.get().strip().replace(",", "")
        if not value.isdigit():
            raise ValueError("목표 줄수는 1 이상의 정수로 입력하세요.")
        goal = int(value)
        if goal <= 0:
            raise ValueError("목표 줄수는 1 이상의 정수로 입력하세요.")
        return goal

    def apply_date_controls_state(self) -> None:
        state = "normal" if self.custom_today_var.get() else "disabled"
        self.today_entry.configure(state=state)
        self.today_apply_button.configure(state=state)

    def set_loading_state(self, loading: bool) -> None:
        if loading:
            self.loading_label.grid()
            self.loading_bar.grid()
            self.loading_bar.start(10)
            self.refresh_button.configure(state="disabled")
            self.status_var.set("새로고침 중...")
            return

        self.loading_bar.stop()
        self.loading_label.grid_remove()
        self.loading_bar.grid_remove()
        self.refresh_button.configure(state="normal")

    def refresh(self) -> None:
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
            result = compute_metrics(config)
            current_ref = resolve_current_ref(self.repo)
            branch_committed = 0
            if current_ref != config.ref:
                branch_committed = get_committed_insertions(
                    self.repo,
                    config.ref,
                    self.author,
                    current_ref,
                )
            branch_total = branch_committed

            base_commit = resolve_base_commit(self.repo, result.today, config.base_commit, config.ref)
            all_base_total = get_total_insertions_up_to(self.repo, base_commit, "")
            all_committed = get_committed_insertions(self.repo, base_commit, "", config.ref)
            if config.include_local and current_ref != config.ref:
                all_committed += get_committed_insertions(self.repo, config.ref, "", current_ref)
            all_committed_total = all_base_total + all_committed

            committed_today = get_committed_insertions_for_date_combined(
                self.repo,
                result.today,
                self.author,
                config.ref,
                config.include_local,
            )
            today_real = dt.date.today()
            today_done = committed_today + result.uncommitted_insertions

            today_target = result.need_today
            end_day = result.today
            start_day = end_day - dt.timedelta(days=graph_days - 1)
            committed_by_date = get_committed_insertions_by_date_combined(
                self.repo,
                start_day,
                end_day,
                self.author,
                config.ref,
                config.include_local,
            )
            points: list[tuple[dt.date, int]] = []
            for i in range(graph_days):
                day = start_day + dt.timedelta(days=i)
                value = committed_by_date.get(day, 0)
                if day == end_day and day == today_real:
                    value += result.uncommitted_insertions
                points.append((day, value))

            values = [v for _, v in points]
            graph_max = max(values) if values else 0
            graph_avg = (sum(values) / len(values)) if values else 0.0
            my_committed_total = result.committed_total
            if all_committed_total > 0:
                share_percent = (my_committed_total / all_committed_total) * 100.0
            else:
                share_percent = 0.0
            share_text = f"{share_percent:.1f}%"

            payload = {
                "result": result,
                "today_done": today_done,
                "today_target": today_target,
                "points": points,
                "graph_days": graph_days,
                "graph_avg": graph_avg,
                "graph_max": graph_max,
                "branch_total": branch_total,
                "share_text": share_text,
                "uncommitted_deletions": get_uncommitted_deletions(self.repo),
            }
            self.safe_after(lambda p=payload: self._on_refresh_success(request_id, p))
        except Exception as exc:  # pragma: no cover
            self.safe_after(lambda e=str(exc): self._on_refresh_error(request_id, e))

    def safe_after(self, callback) -> None:
        try:
            self.root.after(0, callback)
        except tk.TclError:
            pass

    def _on_refresh_success(self, request_id: int, payload: dict[str, object]) -> None:
        if request_id != self.refresh_request_id:
            return

        self.refresh_in_progress = False
        self.set_loading_state(False)

        result = payload["result"]
        today_done = int(payload["today_done"])
        today_target = int(payload["today_target"])
        points = payload["points"]
        graph_days = int(payload["graph_days"])
        graph_avg = float(payload["graph_avg"])
        graph_max = int(payload["graph_max"])
        branch_total = int(payload.get("branch_total", 0))
        share_text = str(payload.get("share_text", ""))
        uncommitted_deletions = int(payload.get("uncommitted_deletions", 0))
        self.branch_total_committed = branch_total
        self.main_total_committed = max(result.committed_total - branch_total, 0)

        lines = format_output_lines(result)  # type: ignore[arg-type]
        self.current_output = "\n".join(lines)
        self.set_output_lines(lines, branch_total, share_text)
        self.delta_added_var.set(f"+{result.uncommitted_insertions:,}")
        self.delta_removed_var.set(f"-{uncommitted_deletions:,}")
        self.update_progress(result, today_done, today_target)  # type: ignore[arg-type]
        self.update_graph(points, result.today, graph_days, graph_avg, graph_max)  # type: ignore[arg-type]
        self.maybe_notify(result, today_done, today_target)  # type: ignore[arg-type]

        status_suffix = " (자동 1분 ON)" if self.auto_refresh_var.get() else ""
        self.status_var.set(f"업데이트: {dt.datetime.now().strftime('%H:%M:%S')}{status_suffix}")
        if self.auto_refresh_var.get():
            self.schedule_auto_refresh()

    def _on_refresh_error(self, request_id: int, error_message: str) -> None:
        if request_id != self.refresh_request_id:
            return

        self.refresh_in_progress = False
        self.set_loading_state(False)
        self.status_var.set("오류 발생")
        messagebox.showerror("Line Tracker Error", error_message)

    def copy_output(self) -> None:
        if not self.current_output:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self.current_output)
        self.status_var.set("클립보드에 복사됨")

    def update_progress(self, result: TrackerResult, today_done: int, today_target: int) -> None:
        current_total = self.main_total_committed + self.branch_total_committed + result.uncommitted_insertions
        if self.goal <= 0:
            overall_percent = 0.0
        else:
            overall_percent = (current_total / self.goal) * 100.0
        overall_percent = max(0.0, min(100.0, overall_percent))
        self.overall_progress_var.set(overall_percent)
        breakdown = (
            f"메인 {self.main_total_committed:,} + 브랜치 {self.branch_total_committed:,} "
            f"+ 미커밋 {result.uncommitted_insertions:,}"
        )
        self.overall_progress_text_var.set(
            f"전체 진행률(커밋+미커밋): {current_total:,}/{self.goal:,} ({overall_percent:.1f}%)\n{breakdown}"
        )

        if today_target <= 0:
            daily_percent = 100.0
        else:
            daily_percent = (today_done / today_target) * 100.0
        daily_percent = max(0.0, min(100.0, daily_percent))

        self.daily_progress_var.set(daily_percent)
        self.daily_progress_text_var.set(
            f"일일 진행률: {today_done:,}/{today_target:,} ({daily_percent:.1f}%)"
        )

    def update_graph(
        self,
        points: list[tuple[dt.date, int]],
        highlight_day: dt.date,
        days: int,
        avg_value: float,
        max_value: int,
    ) -> None:
        self.draw_daily_graph(points, highlight_day)
        self.graph_summary_var.set(f"최근 {days}일 평균 {avg_value:.1f}줄/일 | 최대 {max_value:,}줄")

    def draw_daily_graph(self, points: list[tuple[dt.date, int]], highlight_day: dt.date) -> None:
        canvas = self.graph_canvas
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
            outline=COLOR_BORDER,
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
                fill="#2a322e",
                width=1,
            )
            label_value = int(round(y_top * i / grid_count))
            canvas.create_text(
                margin_left - 6,
                y,
                text=f"{label_value}",
                anchor="e",
                fill=COLOR_MUTED,
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
                fill=COLOR_ACCENT,
                width=2,
                smooth=False,
            )

        label_y = min(height - 2, y_base + 6)
        for idx, (day, value) in enumerate(points):
            x = margin_left + idx * slot_w + slot_w / 2
            y = y_base - (value / y_top) * chart_h if y_top > 0 else y_base
            radius = 4 if day == highlight_day else 3
            color = COLOR_ACCENT2 if day == highlight_day else COLOR_ACCENT
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
                    fill=COLOR_MUTED,
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

    @staticmethod
    def _normalize_bullets(lines: Iterable[str]) -> list[str]:
        cleaned: list[str] = []
        for raw in lines:
            text = raw.strip()
            if not text:
                continue
            if text.startswith(("-", "*", "•")):
                cleaned.append(text)
            else:
                cleaned.append(f"- {text}")
        return cleaned

    def build_commit_message(self) -> str:
        title = self.note_title_var.get().strip()
        done_raw = self.note_done_text.get("1.0", "end-1c") if hasattr(self, "note_done_text") else ""
        todo_raw = self.note_todo_text.get("1.0", "end-1c") if hasattr(self, "note_todo_text") else ""

        done_lines = self._normalize_bullets(done_raw.splitlines())
        todo_lines = self._normalize_bullets(todo_raw.splitlines())

        parts = [title, "", "DONE"]
        if done_lines:
            parts.extend(done_lines)
        parts.append("")
        parts.append("TODO")
        if todo_lines:
            parts.extend(todo_lines)
        return "\n".join(parts).strip() + "\n"

    def commit_notes(self) -> None:
        title = self.note_title_var.get().strip()
        if not title:
            messagebox.showerror("Line Tracker Error", "제목을 입력하세요.")
            return

        commit_message = self.build_commit_message()
        auto_stage = self.auto_stage_var.get() if hasattr(self, "auto_stage_var") else False

        def worker() -> None:
            try:
                kwargs: dict[str, object] = {
                    "cwd": self.repo,
                    "capture_output": True,
                    "text": True,
                    "encoding": "utf-8",
                    "errors": "replace",
                    "check": False,
                    "input": None,
                }
                if hasattr(subprocess, "CREATE_NO_WINDOW"):
                    kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

                if auto_stage:
                    add = subprocess.run(["git", "add", "-A"], **kwargs)
                    if add.returncode != 0:
                        raise RuntimeError(add.stderr.strip() or "git add failed")

                kwargs["input"] = commit_message
                commit = subprocess.run(["git", "commit", "-F", "-"], **kwargs)
                if commit.returncode != 0:
                    raise RuntimeError(commit.stderr.strip() or "git commit failed")

                self.safe_after(self._on_commit_success)
            except Exception as exc:  # pragma: no cover
                self.safe_after(lambda e=str(exc): self._on_commit_error(e))

        self.commit_button.configure(state="disabled")
        self.status_var.set("커밋 중...")
        threading.Thread(target=worker, daemon=True).start()

    def _on_commit_success(self) -> None:
        self.commit_button.configure(state="normal")
        self.status_var.set("커밋 완료")
        self.refresh()

    def _on_commit_error(self, error_message: str) -> None:
        self.commit_button.configure(state="normal")
        self.status_var.set("커밋 실패")
        messagebox.showerror("Line Tracker Error", error_message)

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
            messagebox.showerror("Line Tracker Error", str(exc))

    def apply_goal(self) -> None:
        try:
            self.goal = self.parse_goal_entry()
            self.save_settings()
            self.refresh()
        except ValueError as exc:
            messagebox.showerror("Line Tracker Error", str(exc))

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

    def on_auto_refresh_toggle(self) -> None:
        self.save_settings()
        if self.auto_refresh_var.get():
            self.refresh()
            return
        self.cancel_auto_refresh()
        self.status_var.set("자동 업데이트 OFF")

    def on_notify_toggle(self) -> None:
        self.save_settings()
        if self.notify_var.get():
            self.status_var.set("일일 목표 알림 ON")
        else:
            self.status_var.set("일일 목표 알림 OFF")

    def maybe_notify(self, result: TrackerResult, today_done: int, today_target: int) -> None:
        if not self.notify_var.get():
            return
        if result.today != dt.date.today():
            return
        if today_target <= 0:
            return
        if today_done < today_target:
            return
        notify_date = result.today.isoformat()
        if notify_date == self.last_notify_date:
            return
        self.last_notify_date = notify_date
        self.save_settings()
        title = "일일 목표 달성"
        message = f"{notify_date} {today_target:,}줄 달성 (현재 {today_done:,}줄)"
        show_windows_toast(title, message)

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
