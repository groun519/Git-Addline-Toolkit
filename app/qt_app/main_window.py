from __future__ import annotations

import argparse
import datetime as dt
import subprocess
import threading
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QAbstractButton,
    QAbstractSpinBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from line_tracker import (
    TrackerConfig,
    get_commit_change_entries,
    resolve_base_commit,
    resolve_author,
    resolve_current_ref,
    resolve_ref,
    run_git,
)
from line_tracker_assets import get_app_icon_path
from line_tracker_controller import RefreshCoordinator
from line_tracker_graph import summarize_graph_values
from line_tracker_authors import build_author_option_entries, parse_shortlog_identities
from line_tracker_presenters import build_dashboard_presentation, build_progress_presentation
from line_tracker_refresh import RefreshSnapshot
from line_tracker_repository import resolve_valid_repo
from line_tracker_schedule import (
    DirectiveScheduleParser,
    ScheduleParseError,
    load_schedule_document,
    make_portable_schedule_path,
    resolve_schedule_path,
)
from line_tracker_settings import SETTINGS_FILE_NAME, UISettings, load_ui_settings, save_ui_settings
from line_tracker_theme import ThemePalette, get_theme_palette, resolve_theme_name
from line_tracker_ui_resources import TEXT
from line_tracker import get_app_state_path, get_legacy_state_path
from line_tracker_version import APP_NAME, APP_VERSION, format_app_title
from qt_app.grass_view import GrassView
from qt_app.history_view import CommitHistoryView
from qt_app.icons import make_icon
from qt_app.overlay import CompactOverlay
from qt_app.schedule_view import ScheduleView
from qt_app.settings_dialog import SettingsDialog
from qt_app.theme import QtThemeTokens, build_stylesheet, build_theme_tokens
from qt_app.widgets import ActivityGraph, IconButton, LanguageProgressBar, StatsSection, WindowTitleBar


class _CallbackDispatcher(QObject):
    callback_requested = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.callback_requested.connect(self._run_callback, Qt.ConnectionType.QueuedConnection)

    def dispatch(self, callback) -> None:
        self.callback_requested.emit(callback)

    @staticmethod
    def _run_callback(callback) -> None:
        callback()


class LineTrackerQtWindow(QMainWindow):
    def __init__(self, args: argparse.Namespace, *, capture_mode: bool = False) -> None:
        super().__init__()
        self.args = args
        self.capture_mode = capture_mode
        self.settings_path = get_app_state_path(SETTINGS_FILE_NAME)
        self.legacy_settings_path = get_legacy_state_path(SETTINGS_FILE_NAME)
        self.settings = load_ui_settings(self.settings_path, self.legacy_settings_path)
        self.lang = self.settings.lang if self.settings.lang in TEXT else "ko"
        self.theme_name = resolve_theme_name(self.settings.theme)
        self.palette: ThemePalette = get_theme_palette(self.theme_name)
        self.tokens: QtThemeTokens = build_theme_tokens(self.palette)
        self.goal = _coerce_positive_int(self.settings.goal, args.goal)
        self.base_total = args.base_total
        self.base_commit = args.base_commit
        self.ref = args.ref
        self.month_end = args.month_end
        self.today_override = _parse_saved_today(self.settings, args.today)
        self.current_output = ""
        self.last_snapshot: RefreshSnapshot | None = None
        self.overlay: CompactOverlay | None = None
        self.schedule_parser = DirectiveScheduleParser()
        self.schedule_mtime_ns: int | None = None
        self.commit_history_generation = 0
        self.commit_history_ref = "HEAD"
        self.commit_history_exclude_ref = ""

        saved_repo = resolve_valid_repo(Path(self.settings.repo_path)) if self.settings.repo_path else None
        requested_repo = resolve_valid_repo(Path(args.repo).resolve())
        repo = saved_repo or requested_repo
        self.repo_selected = repo is not None
        self.repo = repo or Path(args.repo).resolve()
        self.author_raw = self.settings.author or args.author
        self.author = resolve_author(self.repo, self.author_raw) if self.repo_selected else self.author_raw

        self.dispatcher = _CallbackDispatcher()
        self.refresh_coordinator = RefreshCoordinator(self.dispatcher.dispatch)
        self.auto_refresh_timer = QTimer(self)
        self.auto_refresh_timer.setInterval(60_000)
        self.auto_refresh_timer.timeout.connect(self.refresh)
        self.schedule_poll_timer = QTimer(self)
        self.schedule_poll_timer.setInterval(1_000)
        self.schedule_poll_timer.timeout.connect(self._poll_schedule)

        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setWindowTitle(format_app_title())
        icon_path = get_app_icon_path()
        if icon_path is not None:
            self.setWindowIcon(QIcon(str(icon_path)))
            QApplication.instance().setWindowIcon(QIcon(str(icon_path)))
        self.setMinimumSize(860, 520)
        self._restore_window_geometry()
        self._build_ui()
        QApplication.instance().installEventFilter(self)
        self._apply_theme()
        self._update_repo_header()
        self._configure_timers()
        self._load_schedule(force=True)
        if self.repo_selected:
            QTimer.singleShot(0, self.refresh)
        else:
            self.status_label.setText(self.t("status_repo_needed"))

    def t(self, key: str, **kwargs: object) -> str:
        text = TEXT.get(self.lang, TEXT["ko"]).get(key, key)
        try:
            return text.format(**kwargs)
        except (KeyError, ValueError):
            return text

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.MouseButtonPress and isinstance(watched, QWidget):
            inside_main = watched is self or self.isAncestorOf(watched)
            interactive = isinstance(
                watched,
                (QLineEdit, QComboBox, QAbstractSpinBox, QAbstractButton, QSlider),
            )
            if inside_main and not interactive:
                focused = QApplication.focusWidget()
                if focused is not None and (focused is self or self.isAncestorOf(focused)):
                    focused.clearFocus()
        return super().eventFilter(watched, event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if hasattr(self, "repo_path"):
            self.repo_path.setVisible(self.width() >= 960)

    def _build_ui(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.title_bar = WindowTitleBar(APP_NAME, APP_VERSION)
        self.title_bar.minimize_requested.connect(self.showMinimized)
        self.title_bar.close_requested.connect(self.close)
        root_layout.addWidget(self.title_bar)

        content = QWidget()
        content.setObjectName("AppContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(16, 14, 16, 12)
        content_layout.setSpacing(12)
        content_layout.addWidget(self._build_header())
        content_layout.addLayout(self._build_dashboard(), 1)
        content_layout.addLayout(self._build_footer())
        root_layout.addWidget(content, 1)
        self.setCentralWidget(root)

    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setMinimumHeight(56)
        layout = QGridLayout(header)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(2)

        accent = QFrame()
        accent.setObjectName("HeaderAccent")
        accent.setFixedWidth(6)
        self.project_title = QLabel(APP_NAME)
        self.project_title.setObjectName("ProjectTitle")
        self.project_date = QLabel(dt.date.today().isoformat())
        self.project_date.setObjectName("ProjectDate")
        self.project_ref = QLabel()
        self.project_ref.setObjectName("ProjectRef")

        self.repo_path = QLineEdit()
        self.repo_path.setReadOnly(True)
        self.repo_path.setMinimumWidth(260)
        self.repo_path.setVisible(self.width() >= 960)
        self.repo_button = IconButton("folder", self.t("repo_select"), size=34)
        self.repo_button.clicked.connect(self.choose_repository)
        self.settings_button = IconButton("settings", self.t("settings"), size=34)
        self.settings_button.clicked.connect(self.open_settings)
        self.overlay_button = IconButton("overlay", self.t("compact_title"), size=34)
        self.overlay_button.clicked.connect(self.enter_compact_mode)
        self.refresh_button = QPushButton(self.t("refresh"))
        self.refresh_button.setObjectName("PrimaryButton")
        self.refresh_button.clicked.connect(self.refresh)
        self.copy_button = QPushButton(self.t("copy"))
        self.copy_button.clicked.connect(self.copy_output)
        self.copy_button.setEnabled(False)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(12)
        title_row.addWidget(self.project_title)
        title_row.addWidget(self.project_date)
        title_row.addStretch(1)

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(7)
        controls.addWidget(self.repo_path, 1)
        controls.addWidget(self.repo_button)
        controls.addWidget(self.settings_button)
        controls.addWidget(self.overlay_button)
        controls.addWidget(self.refresh_button)
        controls.addWidget(self.copy_button)

        layout.addWidget(accent, 0, 0, 2, 1)
        layout.addLayout(title_row, 0, 1)
        layout.addWidget(self.project_ref, 1, 1)
        layout.addLayout(controls, 0, 2, 2, 1)
        layout.setColumnStretch(1, 2)
        layout.setColumnStretch(2, 3)
        return header

    def _build_dashboard(self) -> QHBoxLayout:
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(12)

        self.stats_scroll = QScrollArea()
        self.stats_scroll.setWidgetResizable(True)
        self.stats_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.stats_scroll.setMaximumHeight(384)
        stats_content = QWidget()
        stats_layout = QVBoxLayout(stats_content)
        stats_layout.setContentsMargins(0, 0, 4, 0)
        stats_layout.setSpacing(12)

        accents = self.palette.tile_accents
        self.daily_section = StatsSection((accents[0], accents[1]))
        self.branch_section = StatsSection((accents[1], accents[2]))
        self.overall_section = StatsSection((accents[2], accents[3]))
        self.user_section = StatsSection((accents[3], accents[4]))
        for section in (self.daily_section, self.branch_section, self.overall_section, self.user_section):
            stats_layout.addWidget(section)
        stats_layout.addStretch(1)
        self.stats_scroll.setWidget(stats_content)

        self.stats_column = QWidget()
        self.stats_column.setMinimumWidth(320)
        self.stats_column.setMaximumWidth(480)
        stats_column_layout = QVBoxLayout(self.stats_column)
        stats_column_layout.setContentsMargins(0, 0, 0, 0)
        stats_column_layout.setSpacing(10)
        stats_column_layout.addWidget(self.stats_scroll, 1)
        self.progress_panel = self._build_progress_panel()
        stats_column_layout.addWidget(self.progress_panel)

        self.center_column = self._build_center_column()
        self.workspace_tabs = self._build_workspace_tabs()

        body.addWidget(self.stats_column, 4)
        body.addWidget(self.center_column, 4)
        body.addWidget(self.workspace_tabs, 5)
        return body

    def _build_center_column(self) -> QWidget:
        column = QWidget()
        column.setMinimumWidth(230)
        layout = QVBoxLayout(column)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.graph_panel = self._build_graph_panel()
        self.history_view = CommitHistoryView(self.t)
        self.history_view.setMinimumHeight(110)
        self.history_view.load_more_requested.connect(self.load_next_commit_history_page)
        layout.addWidget(self.graph_panel, 3)
        layout.addWidget(self.history_view, 2)
        return column

    def _build_graph_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("Panel")
        graph_layout = QVBoxLayout(panel)
        graph_layout.setContentsMargins(14, 12, 14, 12)
        graph_layout.setSpacing(8)
        graph_header = QHBoxLayout()
        graph_title = QLabel(self.t("graph_title"))
        graph_title.setObjectName("SectionTitle")
        self.graph_settings_button = IconButton("settings", self.t("graph_settings"), size=30)
        self.graph_settings_button.clicked.connect(lambda: self.open_settings(3))
        graph_header.addWidget(graph_title)
        graph_header.addStretch(1)
        graph_header.addWidget(self.graph_settings_button)
        self.activity_graph = ActivityGraph()
        self.graph_summary = QLabel(self.t("graph_summary_empty"))
        self.graph_summary.setObjectName("MutedLabel")
        self.graph_summary.setWordWrap(True)
        graph_layout.addLayout(graph_header)
        graph_layout.addWidget(self.activity_graph, 1)
        graph_layout.addWidget(self.graph_summary)
        return panel

    def _build_workspace_tabs(self) -> QTabWidget:
        tabs = QTabWidget()
        tabs.setObjectName("WorkspaceTabs")
        tabs.setMinimumWidth(240)
        self.schedule_view = ScheduleView(self.t)
        self.schedule_view.select_requested.connect(self.browse_schedule_file)
        self.schedule_view.reload_requested.connect(lambda: self._load_schedule(force=True))
        self.schedule_view.location_requested.connect(self.open_schedule_location)
        self.grass_view = GrassView(self.t, self.format_month_label)
        tabs.addTab(self.schedule_view, make_icon("calendar", self.tokens.text), self.t("tab_schedule"))
        tabs.addTab(self.grass_view, make_icon("grass", self.tokens.text), self.t("tab_grass"))
        if self.settings.note_tab == "grass":
            tabs.setCurrentIndex(1)
        tabs.currentChanged.connect(self._on_workspace_tab_changed)
        return tabs

    def _build_progress_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("Panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(7)
        title = QLabel(self.t("progress"))
        title.setObjectName("SectionTitle")
        self.overall_progress_label = QLabel(self.t("overall_progress"))
        self.overall_progress_label.setObjectName("MutedLabel")
        self.overall_progress = LanguageProgressBar()
        self.overall_breakdown = QLabel()
        self.overall_breakdown.setObjectName("MutedLabel")
        self.daily_progress_label = QLabel(self.t("daily_progress"))
        self.daily_progress_label.setObjectName("MutedLabel")
        self.daily_progress = LanguageProgressBar()
        layout.addWidget(title)
        layout.addWidget(self.overall_progress_label)
        layout.addWidget(self.overall_progress)
        layout.addWidget(self.overall_breakdown)
        layout.addSpacing(4)
        layout.addWidget(self.daily_progress_label)
        layout.addWidget(self.daily_progress)
        return panel

    def _build_footer(self) -> QHBoxLayout:
        footer = QHBoxLayout()
        footer.setContentsMargins(2, 0, 2, 0)
        self.status_label = QLabel()
        self.status_label.setObjectName("StatusLabel")
        footer.addWidget(self.status_label, 1)
        return footer

    def _apply_theme(self) -> None:
        self.setStyleSheet(build_stylesheet(self.tokens))
        self.title_bar.set_icon_color(self.tokens.text)
        self.repo_button.set_icon_color(self.tokens.text)
        self.settings_button.set_icon_color(self.tokens.text)
        self.overlay_button.set_icon_color(self.tokens.text)
        self.graph_settings_button.set_icon_color(self.tokens.text)
        self.overall_progress.set_theme_tokens(self.tokens)
        self.daily_progress.set_theme_tokens(self.tokens)
        self.activity_graph.set_theme_tokens(self.tokens)
        self.schedule_view.set_theme_tokens(self.tokens)
        self.grass_view.set_theme_tokens(self.tokens)
        for index, icon_name in enumerate(("calendar", "grass")):
            self.workspace_tabs.setTabIcon(index, make_icon(icon_name, self.tokens.text))

    def _update_repo_header(self) -> None:
        if not self.repo_selected:
            self.project_title.setText(APP_NAME)
            self.project_ref.setText(self.t("repo_not_selected"))
            self.repo_path.clear()
            return
        self.project_title.setText(self.repo.name)
        self.repo_path.setText(str(self.repo))
        tracked_ref = resolve_ref(self.repo, self.ref)
        current_ref = resolve_current_ref(self.repo)
        self.project_ref.setText(
            f"{self.repo.name} \u2022 {tracked_ref} + {current_ref}"
            if current_ref != tracked_ref
            else f"{self.repo.name} \u2022 {tracked_ref}"
        )

    def choose_repository(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, self.t("repo_dialog_title"), str(self.repo))
        if not selected:
            return
        repo = resolve_valid_repo(Path(selected))
        if repo is None:
            QMessageBox.warning(self, self.t("repo_dialog_title"), self.t("error_repo_invalid"))
            return
        self.refresh_coordinator.invalidate()
        self.repo = repo
        self.repo_selected = True
        self.author = resolve_author(repo, self.author_raw)
        self._update_repo_header()
        self._save_settings()
        self._load_schedule(force=True)
        self.refresh()

    def refresh(self) -> None:
        if not self.repo_selected:
            self.status_label.setText(self.t("status_repo_needed"))
            return
        if self.refresh_coordinator.is_running:
            return

        config = TrackerConfig(
            repo=self.repo,
            goal=self.goal,
            base_total=self.base_total,
            base_commit=self.base_commit,
            author=self.author,
            ref=resolve_ref(self.repo, self.ref),
            include_local=True,
            today=self.today_override,
            month_end=self.month_end,
            assume_uncommitted_zero=False,
        )
        self.status_label.setText(self.t("loading_detail"))
        self.refresh_button.setEnabled(False)
        request_id = self.refresh_coordinator.start(
            repo=self.repo,
            author=self.author,
            config=config,
            graph_days=_coerce_graph_days(self.settings.graph_days),
            on_success=self._on_refresh_success,
            on_failure=self._on_refresh_failure,
        )
        if request_id is None:
            self.refresh_button.setEnabled(True)

    def _on_refresh_success(self, _request_id: int, snapshot: RefreshSnapshot) -> None:
        self.last_snapshot = snapshot
        presentation = build_dashboard_presentation(snapshot, translate=self.t)
        self.project_date.setText(presentation.date_text)
        self.daily_section.set_presentation(presentation.daily)
        self.branch_section.set_presentation(presentation.branch)
        self.overall_section.set_presentation(presentation.overall)
        self.user_section.set_presentation(presentation.user)

        result = snapshot.result
        main_total = max(result.committed_total - snapshot.branch_total, 0)
        progress = build_progress_presentation(
            main_committed=main_total,
            branch_committed=snapshot.branch_total,
            uncommitted=result.uncommitted_insertions,
            goal=self.goal,
            today_done=snapshot.today_done,
            today_target=snapshot.today_target,
            translate=self.t,
        )
        self.overall_progress.set_progress(
            progress.overall_percent,
            progress.overall_bar_text,
            snapshot.overall_progress_language_lines,
        )
        self.daily_progress.set_progress(
            progress.daily_percent,
            progress.daily_bar_text,
            snapshot.daily_progress_language_lines,
        )
        self.overall_breakdown.setText(progress.breakdown_text)
        graph_series = [
            ("additions", self.tokens.accent, snapshot.graph_added_points, bool(self.settings.graph_show_additions)),
            ("deletions", self.tokens.danger, snapshot.graph_deleted_points, bool(self.settings.graph_show_deletions)),
            ("commits", self.tokens.warning, snapshot.graph_commit_points, bool(self.settings.graph_show_commits)),
        ]
        self.activity_graph.set_data(
            graph_series,
            result.today,
            float(self.settings.graph_curve),
        )
        summary_items = []
        for name, _color, points, enabled in graph_series:
            if not enabled:
                continue
            average, maximum = summarize_graph_values(points)
            summary_items.append(
                self.t(
                    "graph_summary_item",
                    label=self.t(f"graph_series_{name}"),
                    avg=f"{average:.1f}",
                    max=f"{maximum:,}",
                )
            )
        graph_summary = " | ".join(summary_items) if summary_items else self.t("graph_summary_empty")
        if self.activity_graph.uses_adaptive_axis:
            graph_summary = f"{graph_summary}  |  {self.t('graph_scale_adaptive')}"
        self.graph_summary.setText(graph_summary)
        uncommitted_today = result.uncommitted_insertions if result.today == dt.date.today() else 0
        self.grass_view.set_data(snapshot.grass_points, result.today, uncommitted_today)
        self.current_output = self._format_output(snapshot)
        self.copy_button.setEnabled(True)
        self.refresh_button.setEnabled(True)
        self.status_label.setText(self.t("status_updated", time=dt.datetime.now().strftime("%H:%M:%S")))
        self.reset_commit_history_loader(result.today)
        self._update_overlay()

    def _on_refresh_failure(self, _request_id: int, error_message: str) -> None:
        self.refresh_button.setEnabled(True)
        self.status_label.setText(self.t("status_error"))
        if not self.capture_mode:
            QMessageBox.critical(self, self.t("status_error"), error_message)

    def _format_output(self, snapshot: RefreshSnapshot) -> str:
        result = snapshot.result
        month = f"{result.month_end.month}"
        return "\n".join(
            (
                f"- {self.t('today_label')}: {result.today.isoformat()}",
                f"- {self.t('days_left_label', month=month)}: {result.days_left_including_today}{self.t('day_suffix')}",
                f"- {self.t('daily_required_label')}: {result.need_today}{self.t('per_day_suffix')}",
                f"- {self.t('current_uncommitted_label')}: {result.uncommitted_insertions}{self.t('lines_suffix')}",
            )
        )

    def copy_output(self) -> None:
        if not self.current_output:
            return
        QGuiApplication.clipboard().setText(self.current_output)
        self.status_label.setText(self.t("status_clipboard"))

    def format_month_label(self, month: int) -> str:
        if self.lang == "en":
            import calendar

            return calendar.month_abbr[month]
        return f"{month}\uc6d4"

    def _configure_timers(self) -> None:
        if bool(self.settings.auto_refresh):
            self.auto_refresh_timer.start()
        else:
            self.auto_refresh_timer.stop()
        self.schedule_poll_timer.start()

    def _on_workspace_tab_changed(self, index: int) -> None:
        note_tab = None
        if index == 0:
            note_tab = "schedule"
        elif index == 1:
            note_tab = "grass"
        if note_tab is not None and note_tab != self.settings.note_tab:
            self.settings = replace(self.settings, note_tab=note_tab)
            self._save_settings()

    def browse_schedule_file(self) -> None:
        start = str(self.repo if self.repo_selected else Path.home())
        selected, _ = QFileDialog.getOpenFileName(
            self,
            self.t("schedule_dialog_title"),
            start,
            "Markdown (*.md)",
        )
        if not selected:
            return
        path = Path(selected)
        if path.suffix.casefold() != ".md":
            QMessageBox.warning(self, self.t("schedule_dialog_title"), self.t("schedule_error_extension"))
            return
        stored_path = make_portable_schedule_path(self.repo, path) if self.repo_selected else str(path.resolve())
        self.settings = replace(self.settings, schedule_path=stored_path)
        self._save_settings()
        self._load_schedule(force=True)

    def _load_schedule(self, *, force: bool = False) -> None:
        if not hasattr(self, "schedule_view"):
            return
        if not self.repo_selected:
            self.schedule_view.show_unconfigured()
            return
        path = resolve_schedule_path(self.repo, self.settings.schedule_path)
        if path is None:
            self.schedule_mtime_ns = None
            self.schedule_view.show_unconfigured()
            return
        try:
            mtime_ns = path.stat().st_mtime_ns
            if not force and mtime_ns == self.schedule_mtime_ns:
                return
            document = load_schedule_document(path, self.schedule_parser)
        except FileNotFoundError:
            self.schedule_mtime_ns = None
            self.schedule_view.show_error(path, self.t("schedule_error_missing"))
            return
        except (OSError, ScheduleParseError) as exc:
            self.schedule_view.show_error(path, str(exc))
            return
        self.schedule_mtime_ns = mtime_ns
        today = self.last_snapshot.result.today if self.last_snapshot is not None else (self.today_override or dt.date.today())
        self.schedule_view.show_document(document, today)

    def _poll_schedule(self) -> None:
        self._load_schedule(force=False)

    def open_schedule_location(self) -> None:
        if not self.repo_selected:
            return
        path = resolve_schedule_path(self.repo, self.settings.schedule_path)
        if path is None:
            return
        try:
            subprocess.Popen(["explorer.exe", "/select,", str(path)])
        except OSError:
            QMessageBox.warning(self, self.t("schedule_title"), self.t("schedule_error_open_location"))

    def _build_author_options(self) -> tuple[list[str], dict[str, str], dict[str, str]]:
        auto_label = self.t("author_auto")
        all_label = self.t("author_all")
        if not self.repo_selected:
            return build_author_option_entries([], auto_label, all_label)
        try:
            output = run_git(self.repo, ["shortlog", "-sne", "--all"])
        except RuntimeError:
            output = ""
        return build_author_option_entries(parse_shortlog_identities(output), auto_label, all_label)

    def _author_display(self, mapping: dict[str, str], aliases: dict[str, str]) -> str:
        if self.settings.author_display in mapping:
            return self.settings.author_display
        if self.author_raw in aliases:
            return aliases[self.author_raw]
        for display, value in mapping.items():
            if value == self.author_raw:
                return display
        return self.author_raw or self.t("author_all")

    def open_settings(self, tab_index: int = 0) -> None:
        options, mapping, aliases = self._build_author_options()
        dialog = SettingsDialog(
            self,
            translate=self.t,
            settings=self.settings,
            tokens=self.tokens,
            author_options=options,
            author_filter_map=mapping,
            author_display=self._author_display(mapping, aliases),
        )
        dialog.tabs.setCurrentIndex(min(max(tab_index, 0), dialog.tabs.count() - 1))
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        requested_repo = Path(values.repo_path).expanduser() if values.repo_path else None
        repo = resolve_valid_repo(requested_repo) if requested_repo is not None else None
        if requested_repo is not None and repo is None:
            QMessageBox.warning(self, self.t("repo_dialog_title"), self.t("error_repo_invalid"))
            return
        schedule_path = values.schedule_path
        if schedule_path and repo is not None:
            schedule_candidate = Path(schedule_path).expanduser()
            if schedule_candidate.is_absolute():
                schedule_path = make_portable_schedule_path(repo, schedule_candidate)
        self.refresh_coordinator.invalidate()
        self.commit_history_generation += 1
        self.repo = repo or Path(values.repo_path or self.args.repo).resolve()
        self.repo_selected = repo is not None
        self.lang = values.lang
        self.theme_name = resolve_theme_name(values.theme)
        self.palette = get_theme_palette(self.theme_name)
        self.tokens = build_theme_tokens(self.palette)
        self.goal = values.goal
        self.author_raw = values.author_raw
        self.author = resolve_author(repo, self.author_raw) if repo is not None else self.author_raw
        try:
            self.today_override = (
                dt.date.fromisoformat(values.custom_today)
                if values.custom_today_enabled
                else self.args.today
            )
        except ValueError:
            self.today_override = None
        self.settings = replace(
            self.settings,
            lang=values.lang,
            theme=self.theme_name,
            repo_path=str(repo) if repo is not None else "",
            custom_today_enabled=values.custom_today_enabled,
            custom_today=values.custom_today,
            goal=values.goal,
            author=values.author_raw,
            author_display=values.author_display,
            auto_refresh=values.auto_refresh,
            graph_days=values.graph_days,
            graph_show_additions=values.graph_show_additions,
            graph_show_deletions=values.graph_show_deletions,
            graph_show_commits=values.graph_show_commits,
            graph_curve=values.graph_curve,
            schedule_path=schedule_path,
        )
        self._rebuild_ui()
        self._configure_timers()
        self._save_settings()
        self._load_schedule(force=True)
        if self.repo_selected:
            self.refresh()
        else:
            self.status_label.setText(self.t("status_repo_needed"))

    def _rebuild_ui(self) -> None:
        previous = self.takeCentralWidget()
        self._build_ui()
        if previous is not None:
            previous.deleteLater()
        self._apply_theme()
        self._update_repo_header()

    def reset_commit_history_loader(self, today: dt.date) -> None:
        self.commit_history_generation += 1
        self.history_view.reset()
        if not self.repo_selected:
            return
        try:
            tracked_ref = resolve_ref(self.repo, self.ref)
            current_ref = resolve_current_ref(self.repo)
            base_ref = resolve_base_commit(self.repo, today, self.base_commit, tracked_ref)
        except (OSError, RuntimeError):
            self.commit_history_ref = "HEAD"
            self.commit_history_exclude_ref = ""
            return
        self.commit_history_ref = current_ref or tracked_ref
        self.commit_history_exclude_ref = base_ref
        self.load_next_commit_history_page()

    def load_next_commit_history_page(self) -> None:
        if not self.repo_selected or self.history_view.loading or self.history_view.exhausted:
            return
        generation = self.commit_history_generation
        skip = len(self.history_view.entries)
        repo = self.repo
        author = self.author
        ref = self.commit_history_ref
        exclude_ref = self.commit_history_exclude_ref
        limit = 40
        self.history_view.set_loading(True)

        def worker() -> None:
            try:
                entries = get_commit_change_entries(
                    repo,
                    author,
                    ref,
                    exclude_ref=exclude_ref or None,
                    limit=limit,
                    skip=skip,
                )
            except (OSError, RuntimeError):
                entries = []
            self.dispatcher.dispatch(
                lambda: self._on_commit_history_page(generation, entries, len(entries) < limit)
            )

        threading.Thread(target=worker, daemon=True).start()

    def _on_commit_history_page(self, generation: int, entries, exhausted: bool) -> None:
        if generation != self.commit_history_generation:
            return
        self.history_view.append_entries(entries, exhausted=exhausted)

    def enter_compact_mode(self) -> None:
        if self.overlay is not None:
            return
        self.overlay = CompactOverlay(
            translate=self.t,
            tokens=self.tokens,
            variant=self.settings.compact_variant,
            alpha=self.settings.compact_alpha,
        )
        self.overlay.restore_requested.connect(self.exit_compact_mode)
        self.overlay.refresh_requested.connect(self.refresh)
        self.overlay.state_changed.connect(self._on_overlay_state_changed)
        self._update_overlay()
        self.overlay.show()
        self.overlay.place_bottom_right()
        self.hide()

    def _update_overlay(self) -> None:
        if self.overlay is None or self.last_snapshot is None:
            return
        snapshot = self.last_snapshot
        result = snapshot.result
        progress = build_progress_presentation(
            main_committed=max(result.committed_total - snapshot.branch_total, 0),
            branch_committed=snapshot.branch_total,
            uncommitted=result.uncommitted_insertions,
            goal=self.goal,
            today_done=snapshot.today_done,
            today_target=snapshot.today_target,
            translate=self.t,
        )
        self.overlay.set_data(snapshot, progress)

    def _on_overlay_state_changed(self, variant: str, alpha: float) -> None:
        self.settings = replace(self.settings, compact_variant=variant, compact_alpha=alpha)

    def exit_compact_mode(self) -> None:
        if self.overlay is not None:
            self.settings = replace(
                self.settings,
                compact_variant=self.overlay.variant,
                compact_alpha=self.overlay.alpha,
            )
            self.overlay.close()
            self.overlay.deleteLater()
            self.overlay = None
        self._save_settings()
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _restore_window_geometry(self) -> None:
        parsed = _parse_geometry(self.settings.geometry)
        screen = QGuiApplication.primaryScreen().availableGeometry()
        if parsed is None:
            width = min(1420, max(860, int(screen.width() * 0.9)))
            height = min(820, max(520, int(screen.height() * 0.86)))
            self.resize(width, height)
            self.move(screen.center() - self.rect().center())
            return
        width, height, x_pos, y_pos = parsed
        self.resize(min(max(width, 860), screen.width()), min(max(height, 520), screen.height()))
        if x_pos is not None and y_pos is not None:
            self.move(x_pos, y_pos)

    def _save_settings(self) -> None:
        if self.capture_mode:
            return
        geometry = f"{self.width()}x{self.height()}+{self.x()}+{self.y()}"
        self.settings = replace(
            self.settings,
            repo_path=str(self.repo) if self.repo_selected else "",
            lang=self.lang,
            theme=self.theme_name,
            goal=self.goal,
            geometry=geometry,
        )
        save_ui_settings(self.settings_path, self.settings)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self.refresh_coordinator.invalidate()
        self.commit_history_generation += 1
        self.auto_refresh_timer.stop()
        self.schedule_poll_timer.stop()
        if self.overlay is not None:
            self.overlay.close()
            self.overlay = None
        QApplication.instance().removeEventFilter(self)
        self._save_settings()
        super().closeEvent(event)


def _coerce_positive_int(value: object, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _coerce_graph_days(value: object) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 30
    return min(max(parsed, 1), 365)


def _parse_saved_today(settings: UISettings, fallback: dt.date | None) -> dt.date | None:
    if not settings.custom_today_enabled:
        return fallback
    try:
        return dt.date.fromisoformat(settings.custom_today)
    except ValueError:
        return fallback


def _parse_geometry(value: str) -> tuple[int, int, int | None, int | None] | None:
    import re

    match = re.fullmatch(r"(\d+)x(\d+)(?:\+(-?\d+)\+(-?\d+))?", value.strip())
    if match is None:
        return None
    width, height, x_pos, y_pos = match.groups()
    return int(width), int(height), int(x_pos) if x_pos else None, int(y_pos) if y_pos else None
