from __future__ import annotations

import argparse
import datetime as dt
import threading
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QGuiApplication
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from line_tracker import TrackerConfig, get_app_state_path, get_legacy_state_path
from line_tracker_repository import find_repo_root_from_metadata, resolve_valid_repo
from line_tracker_settings import SETTINGS_FILE_NAME, UISettings, load_ui_settings, save_ui_settings
from line_tracker_startup import StartupPayload, build_startup_payload
from line_tracker_theme import get_theme_palette, resolve_theme_name
from line_tracker_ui_resources import TEXT
from line_tracker_version import APP_NAME, APP_VERSION
from qt_app.theme import build_stylesheet, build_theme_tokens
from qt_app.widgets import WindowTitleBar


class StartupWindow(QFrame):
    ready = Signal(object)
    _progress_received = Signal(int, int, str)
    _load_completed = Signal(int, object)
    _load_failed = Signal(int, str)

    def __init__(
        self,
        args: argparse.Namespace,
        *,
        explicit_repo: bool = False,
        settings_override: UISettings | None = None,
    ) -> None:
        super().__init__()
        self.args = args
        self.explicit_repo = explicit_repo
        self.settings_path = get_app_state_path(SETTINGS_FILE_NAME)
        self.legacy_settings_path = get_legacy_state_path(SETTINGS_FILE_NAME)
        self.settings = settings_override or load_ui_settings(self.settings_path, self.legacy_settings_path)
        self.lang = self.settings.lang if self.settings.lang in TEXT else "ko"
        self.theme_name = resolve_theme_name(self.settings.theme)
        self.tokens = build_theme_tokens(get_theme_palette(self.theme_name))
        self.repo: Path | None = None
        self._generation = 0
        self._loading = False
        self._stage_text = ""
        self._dot_count = 0

        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setWindowTitle(APP_NAME)
        self.setFixedSize(560, 330)
        self._build_ui()
        self.setStyleSheet(build_stylesheet(self.tokens))
        self.title_bar.set_icon_color(self.tokens.text)
        self._center_on_screen()

        self._progress_received.connect(self._on_progress)
        self._load_completed.connect(self._on_completed)
        self._load_failed.connect(self._on_failed)
        self.activity_timer = QTimer(self)
        self.activity_timer.setInterval(420)
        self.activity_timer.timeout.connect(self._animate_status)

        configured_path = args.repo if explicit_repo else self.settings.repo_path
        self.repo = find_repo_root_from_metadata(Path(configured_path)) if configured_path else None
        if self.repo is None:
            self._show_repository_gate()
        else:
            self._show_repository(self.repo)
            QTimer.singleShot(0, self.start_loading)

    def t(self, key: str, **kwargs: object) -> str:
        text = TEXT.get(self.lang, TEXT["ko"]).get(key, key)
        try:
            return text.format(**kwargs)
        except (KeyError, ValueError):
            return text

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.title_bar = WindowTitleBar(APP_NAME, APP_VERSION)
        self.title_bar.minimize_requested.connect(self.showMinimized)
        self.title_bar.close_requested.connect(self.close)
        root.addWidget(self.title_bar)

        content = QWidget()
        content.setObjectName("AppContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(24, 22, 24, 24)
        card = QFrame()
        card.setObjectName("StartupCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(22, 20, 22, 20)
        card_layout.setSpacing(11)

        eyebrow = QLabel("LINE TRACKER")
        eyebrow.setObjectName("StartupEyebrow")
        self.heading = QLabel(self.t("startup_heading"))
        self.heading.setObjectName("StartupHeading")
        self.status = QLabel()
        self.status.setObjectName("StartupStatus")
        self.status.setWordWrap(True)

        self.path_card = QFrame()
        self.path_card.setObjectName("StartupPathCard")
        self.path_card.setMinimumHeight(50)
        path_layout = QVBoxLayout(self.path_card)
        path_layout.setContentsMargins(12, 9, 12, 9)
        path_layout.setSpacing(2)
        self.repo_name = QLabel()
        self.repo_name.setObjectName("StartupRepoName")
        self.repo_path = QLabel()
        self.repo_path.setObjectName("StartupRepoPath")
        self.repo_path.setMinimumHeight(14)
        self.repo_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        path_layout.addWidget(self.repo_name)
        path_layout.addWidget(self.repo_path)

        progress_row = QHBoxLayout()
        progress_row.setSpacing(10)
        self.progress = QProgressBar()
        self.progress.setObjectName("StartupProgress")
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        self.progress_value = QLabel("0%")
        self.progress_value.setObjectName("StartupProgressValue")
        progress_row.addWidget(self.progress, 1)
        progress_row.addWidget(self.progress_value)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.select_button = QPushButton(self.t("startup_select_repo"))
        self.select_button.setObjectName("PrimaryButton")
        self.select_button.clicked.connect(self.select_repository)
        self.retry_button = QPushButton(self.t("startup_retry"))
        self.retry_button.setObjectName("PrimaryButton")
        self.retry_button.clicked.connect(self.start_loading)
        button_row.addWidget(self.select_button)
        button_row.addWidget(self.retry_button)

        card_layout.addWidget(eyebrow)
        card_layout.addWidget(self.heading)
        card_layout.addWidget(self.status)
        card_layout.addWidget(self.path_card)
        card_layout.addLayout(progress_row)
        card_layout.addLayout(button_row)
        content_layout.addWidget(card)
        root.addWidget(content, 1)

    def _center_on_screen(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            self.move(screen.availableGeometry().center() - self.rect().center())

    def _show_repository_gate(self) -> None:
        self._loading = False
        self.heading.setText(self.t("startup_repo_required_title"))
        self.status.setText(self.t("startup_repo_required_hint"))
        self.path_card.hide()
        self.progress.hide()
        self.progress_value.hide()
        self.select_button.show()
        self.retry_button.hide()

    def _show_repository(self, repo: Path) -> None:
        self.path_card.show()
        self.repo_name.setText(repo.name)
        self.repo_path.setText(str(repo))
        self.repo_path.setToolTip(str(repo))

    def select_repository(self) -> None:
        start = str(self.repo or Path.home())
        selected = QFileDialog.getExistingDirectory(self, self.t("repo_dialog_title"), start)
        if not selected:
            return
        repo = resolve_valid_repo(Path(selected))
        if repo is None:
            self.heading.setText(self.t("startup_repo_required_title"))
            self.status.setText(self.t("startup_repo_invalid"))
            return
        self.repo = repo
        self.settings = replace(self.settings, repo_path=str(repo))
        if not save_ui_settings(self.settings_path, self.settings):
            QMessageBox.warning(
                self,
                self.t("settings_save_error_title"),
                self.t("settings_save_error", path=str(self.settings_path)),
            )
            return
        self._show_repository(repo)
        self.start_loading()

    def start_loading(self) -> None:
        if self.repo is None or self._loading:
            return
        self._generation += 1
        generation = self._generation
        self._loading = True
        self.heading.setText(self.t("startup_loading_title"))
        self.select_button.setEnabled(False)
        self.select_button.show()
        self.retry_button.hide()
        self.progress.show()
        self.progress_value.show()
        self.progress.setValue(0)
        self.progress_value.setText("0%")
        self._set_stage("repository")
        self.activity_timer.start()

        repo = self.repo
        settings = self.settings
        config = self._make_config(repo, settings)
        graph_days = _coerce_graph_days(settings.graph_days)

        def worker() -> None:
            try:
                payload = build_startup_payload(
                    repo,
                    settings,
                    config,
                    graph_days,
                    progress=lambda value, stage: self._progress_received.emit(generation, value, stage),
                )
            except Exception as exc:
                self._load_failed.emit(generation, str(exc))
                return
            self._load_completed.emit(generation, payload)

        threading.Thread(target=worker, daemon=True).start()

    def _make_config(self, repo: Path, settings: UISettings) -> TrackerConfig:
        return TrackerConfig(
            repo=repo,
            goal=_coerce_positive_int(settings.goal, self.args.goal),
            base_total=self.args.base_total,
            base_commit=self.args.base_commit,
            author=settings.author or self.args.author,
            ref=self.args.ref,
            selected_branches=settings.selected_branches,
            include_local=True,
            today=_parse_saved_today(settings, self.args.today),
            month_end=self.args.month_end,
            assume_uncommitted_zero=False,
        )

    def _on_progress(self, generation: int, value: int, stage: str) -> None:
        if generation != self._generation or not self._loading:
            return
        self.progress.setValue(value)
        self.progress_value.setText(f"{value}%")
        self._set_stage(stage)

    def _on_completed(self, generation: int, payload: StartupPayload) -> None:
        if generation != self._generation or not self._loading:
            return
        self._loading = False
        self.activity_timer.stop()
        self.progress.setValue(100)
        self.progress_value.setText("100%")
        self.heading.setText(self.t("startup_ready_title"))
        self.status.setText(self.t("startup_ready_hint"))
        QTimer.singleShot(120, lambda: self.ready.emit(payload))

    def _on_failed(self, generation: int, message: str) -> None:
        if generation != self._generation:
            return
        self._loading = False
        self.activity_timer.stop()
        self.heading.setText(self.t("startup_failed_title"))
        self.status.setText(self.t("startup_failed_hint", error=message))
        self.select_button.setEnabled(True)
        self.select_button.show()
        self.retry_button.show()

    def show_finalization_error(self, message: str) -> None:
        self._on_failed(self._generation, message)

    def _set_stage(self, stage: str) -> None:
        self._stage_text = self.t(f"startup_stage_{stage}")
        self._dot_count = 0
        self.status.setText(self._stage_text)

    def _animate_status(self) -> None:
        if not self._loading:
            return
        self._dot_count = (self._dot_count + 1) % 4
        self.status.setText(f"{self._stage_text}{'.' * self._dot_count}")

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self._generation += 1
        self._loading = False
        self.activity_timer.stop()
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
