from __future__ import annotations

import datetime as dt

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from line_tracker_presenters import ProgressPresentation
from line_tracker_refresh import RefreshSnapshot
from line_tracker_settings import COMPACT_WINDOW_ALPHA_MAX, COMPACT_WINDOW_ALPHA_MIN
from qt_app.theme import QtThemeTokens, build_stylesheet
from qt_app.widgets import LanguageProgressBar


class CompactOverlay(QWidget):
    restore_requested = Signal()
    refresh_requested = Signal()
    state_changed = Signal(str, float)

    def __init__(self, *, translate, tokens: QtThemeTokens, variant: str, alpha: float) -> None:
        super().__init__()
        self.t = translate
        self.tokens = tokens
        self.variant = "strip" if variant == "strip" else "card"
        self.alpha = min(max(float(alpha), COMPACT_WINDOW_ALPHA_MIN), COMPACT_WINDOW_ALPHA_MAX)
        self._drag_offset: QPoint | None = None
        self.snapshot: RefreshSnapshot | None = None
        self.progress: ProgressPresentation | None = None
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowOpacity(self.alpha)
        self.clock_timer = QTimer(self)
        self.clock_timer.setInterval(1000)
        self.clock_timer.timeout.connect(self._update_clock)
        self._build_ui()
        self._apply_theme()
        self._apply_variant()
        self.clock_timer.start()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.panel = QFrame()
        self.panel.setObjectName("OverlayPanel")
        outer.addWidget(self.panel)
        self.root_layout = QVBoxLayout(self.panel)
        self.root_layout.setContentsMargins(10, 8, 10, 8)
        self.root_layout.setSpacing(7)

        self.card_content = QWidget()
        card = QVBoxLayout(self.card_content)
        card.setContentsMargins(0, 0, 0, 0)
        card.setSpacing(7)
        top = QHBoxLayout()
        self.card_title = QLabel("Line Tracker")
        self.card_title.setObjectName("OverlayTitle")
        self.card_refresh = QPushButton(self.t("compact_refresh_short"))
        self.card_refresh.setObjectName("OverlayTextButton")
        self.card_refresh.clicked.connect(self.refresh_requested.emit)
        self.card_restore = QPushButton(self.t("compact_restore_short"))
        self.card_restore.setObjectName("OverlayTextButton")
        self.card_restore.clicked.connect(self.restore_requested.emit)
        top.addWidget(self.card_title)
        top.addStretch(1)
        top.addWidget(self.card_refresh)
        top.addWidget(self.card_restore)
        card.addLayout(top)
        self.card_progress_label = QLabel(self.t("compact_today_progress"))
        self.card_progress_label.setObjectName("MutedLabel")
        card.addWidget(self.card_progress_label)
        self.card_progress = LanguageProgressBar()
        self.card_progress.setFixedHeight(20)
        card.addWidget(self.card_progress)
        delta = QHBoxLayout()
        delta.addWidget(QLabel(self.t("compact_delta")))
        self.card_added = QLabel("+0")
        self.card_added.setObjectName("DeltaAdd")
        self.card_removed = QLabel("-0")
        self.card_removed.setObjectName("DeltaRemove")
        delta.addWidget(self.card_added)
        delta.addWidget(self.card_removed)
        delta.addStretch(1)
        self.to_strip = QPushButton(self.t("compact_mode_to_strip"))
        self.to_strip.setObjectName("OverlayTextButton")
        self.to_strip.clicked.connect(lambda: self.set_variant("strip"))
        delta.addWidget(self.to_strip)
        card.addLayout(delta)
        self.clock = QLabel()
        self.clock.setObjectName("OverlayClock")
        card.addWidget(self.clock)
        alpha_row = QHBoxLayout()
        alpha_row.addStretch(1)
        self.card_alpha = self._make_alpha_slider(Qt.Orientation.Horizontal)
        self.card_alpha.setFixedWidth(82)
        alpha_row.addWidget(self.card_alpha)
        card.addLayout(alpha_row)

        self.strip_content = QWidget()
        strip = QHBoxLayout(self.strip_content)
        strip.setContentsMargins(0, 0, 0, 0)
        strip.setSpacing(7)
        self.strip_alpha = self._make_alpha_slider(Qt.Orientation.Vertical)
        self.strip_alpha.setFixedSize(12, 32)
        strip.addWidget(self.strip_alpha)
        self.strip_progress = LanguageProgressBar()
        self.strip_progress.setFixedHeight(20)
        strip.addWidget(self.strip_progress, 1)
        self.to_card = QPushButton(self.t("compact_mode_to_card"))
        self.to_card.setObjectName("OverlaySmallButton")
        self.to_card.clicked.connect(lambda: self.set_variant("card"))
        self.strip_restore = QPushButton(self.t("compact_restore_short"))
        self.strip_restore.setObjectName("OverlaySmallButton")
        self.strip_restore.clicked.connect(self.restore_requested.emit)
        strip.addWidget(self.to_card)
        strip.addWidget(self.strip_restore)

        self.root_layout.addWidget(self.card_content)
        self.root_layout.addWidget(self.strip_content)
        self._update_clock()

    def _make_alpha_slider(self, orientation: Qt.Orientation) -> QSlider:
        slider = QSlider(orientation)
        slider.setRange(round(COMPACT_WINDOW_ALPHA_MIN * 100), round(COMPACT_WINDOW_ALPHA_MAX * 100))
        slider.setValue(round(self.alpha * 100))
        slider.setToolTip(self.t("compact_opacity"))
        slider.valueChanged.connect(self._on_alpha_changed)
        return slider

    def _apply_theme(self) -> None:
        self.setStyleSheet(build_stylesheet(self.tokens))
        self.card_progress.set_theme_tokens(self.tokens)
        self.strip_progress.set_theme_tokens(self.tokens)

    def set_data(self, snapshot: RefreshSnapshot, progress: ProgressPresentation) -> None:
        self.snapshot = snapshot
        self.progress = progress
        result = snapshot.result
        self.card_added.setText(f"+{result.uncommitted_insertions:,}")
        self.card_removed.setText(f"-{snapshot.uncommitted_deletions:,}")
        self.card_progress.set_progress(
            progress.daily_percent,
            progress.daily_bar_text.replace(" / ", "/"),
            snapshot.daily_progress_language_lines,
        )
        self.strip_progress.set_progress(
            progress.daily_percent,
            progress.daily_bar_text.replace(" / ", "/"),
            snapshot.daily_progress_language_lines,
        )

    def set_variant(self, variant: str) -> None:
        self.variant = "strip" if variant == "strip" else "card"
        self._apply_variant()
        self.state_changed.emit(self.variant, self.alpha)

    def _apply_variant(self) -> None:
        is_strip = self.variant == "strip"
        self.card_content.setVisible(not is_strip)
        self.strip_content.setVisible(is_strip)
        self.root_layout.setContentsMargins(7 if is_strip else 10, 5 if is_strip else 8, 7 if is_strip else 10, 5 if is_strip else 8)
        self.setFixedSize(440 if is_strip else 360, 44 if is_strip else 176)

    def place_bottom_right(self) -> None:
        screen = self.screen()
        if screen is None and self.parentWidget() is not None:
            screen = self.parentWidget().screen()
        if screen is None:
            return
        area = screen.availableGeometry()
        self.move(area.right() - self.width() - 14, area.bottom() - self.height() - 14)

    def _on_alpha_changed(self, value: int) -> None:
        self.alpha = value / 100.0
        self.setWindowOpacity(self.alpha)
        other = self.strip_alpha if self.sender() is self.card_alpha else self.card_alpha
        other.blockSignals(True)
        other.setValue(value)
        other.blockSignals(False)
        self.state_changed.emit(self.variant, self.alpha)

    def _update_clock(self) -> None:
        now = dt.datetime.now()
        self.clock.setText(now.strftime("%Y-%m-%d | %H:%M:%S"))

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._drag_offset = None
        super().mouseReleaseEvent(event)
