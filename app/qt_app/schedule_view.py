from __future__ import annotations

import datetime as dt
from collections import defaultdict
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from line_tracker_schedule import (
    SCHEDULE_STATUS_DONE,
    SCHEDULE_STATUS_HOLD,
    SCHEDULE_STATUS_IN_PROGRESS,
    SCHEDULE_STATUS_NEXT,
    SCHEDULE_STATUS_REVIEW,
    ScheduleDocument,
    ScheduleItem,
)
from qt_app.theme import PANEL_PADDING, PANEL_SPACING, QtThemeTokens
from qt_app.widgets import ExpandableText, IconButton


class ScheduleView(QWidget):
    select_requested = Signal()
    reload_requested = Signal()
    location_requested = Signal()
    edit_requested = Signal(object)
    delete_requested = Signal(object)
    complete_requested = Signal(object)

    def __init__(self, translate) -> None:
        super().__init__()
        self.t = translate
        self.tokens: QtThemeTokens | None = None
        self.today = dt.date.today()
        self.document: ScheduleDocument | None = None
        self.source_path: Path | None = None
        self.state = "unconfigured"
        self.error_message = ""
        self.filter_mode = "total"
        self._build_ui()
        self.show_unconfigured()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(PANEL_PADDING, PANEL_PADDING, PANEL_PADDING, PANEL_PADDING)
        layout.setSpacing(PANEL_SPACING)

        header = QHBoxLayout()
        header.setSpacing(7)
        titles = QVBoxLayout()
        titles.setSpacing(1)
        self.title_label = QLabel(self.t("schedule_title"))
        self.title_label.setObjectName("PanelTitle")
        self.source_label = QLabel()
        self.source_label.setObjectName("MutedLabel")
        titles.addWidget(self.title_label)
        titles.addWidget(self.source_label)
        header.addLayout(titles, 1)
        self.select_button = IconButton("file", self.t("schedule_select"), size=32)
        self.reload_button = IconButton("refresh", self.t("schedule_reload"), size=32)
        self.location_button = IconButton("folder", self.t("schedule_open_location"), size=32)
        self.select_button.clicked.connect(self.select_requested.emit)
        self.reload_button.clicked.connect(self.reload_requested.emit)
        self.location_button.clicked.connect(self.location_requested.emit)
        header.addWidget(self.select_button)
        header.addWidget(self.reload_button)
        header.addWidget(self.location_button)
        layout.addLayout(header)

        self.summary = QFrame()
        self.summary.setObjectName("SummaryStrip")
        summary_layout = QHBoxLayout(self.summary)
        summary_layout.setContentsMargins(10, 6, 10, 6)
        summary_layout.setSpacing(4)
        self.summary_values: dict[str, QPushButton] = {}
        for name in ("total", "active", "done"):
            button = QPushButton()
            button.setObjectName("ScheduleFilterButton")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, mode=name: self._set_filter(mode))
            self.summary_values[name] = button
            summary_layout.addWidget(button)
        summary_layout.addStretch(1)
        layout.addWidget(self.summary)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_host = QWidget()
        self.list_layout = QVBoxLayout(self.list_host)
        self.list_layout.setContentsMargins(0, 0, 5, 0)
        self.list_layout.setSpacing(6)
        self.scroll.setWidget(self.list_host)
        layout.addWidget(self.scroll, 1)

    def set_theme_tokens(self, tokens: QtThemeTokens) -> None:
        self.tokens = tokens
        for button in (self.select_button, self.reload_button, self.location_button):
            button.set_icon_color(tokens.text)
        self.refresh()

    def show_unconfigured(self) -> None:
        self.state = "unconfigured"
        self.document = None
        self.source_path = None
        self.error_message = ""
        self.refresh()

    def show_error(self, source_path: Path | None, message: str) -> None:
        self.state = "error"
        self.document = None
        self.source_path = source_path
        self.error_message = message
        self.refresh()

    def show_document(self, document: ScheduleDocument, today: dt.date) -> None:
        self.state = "loaded"
        self.document = document
        self.source_path = document.source_path
        self.today = today
        self.error_message = ""
        self.refresh()

    def refresh(self) -> None:
        self._clear_items()
        has_source = self.source_path is not None
        self.reload_button.setEnabled(has_source)
        self.location_button.setEnabled(has_source)

        if self.state == "unconfigured":
            self.title_label.setText(self.t("schedule_title"))
            self.source_label.setText(self.t("schedule_no_file"))
            self.summary.hide()
            self._add_empty_state(
                self.t("schedule_unconfigured_title"),
                self.t("schedule_unconfigured_hint"),
                show_select=True,
            )
            return
        if self.state == "error":
            self.title_label.setText(self.t("schedule_title"))
            self.source_label.setText(self._source_text())
            self.summary.hide()
            self._add_empty_state(self.t("schedule_error_title"), self.error_message)
            return

        document = self.document
        if document is None:
            self.show_unconfigured()
            return
        self.title_label.setText(document.title or self.t("schedule_title"))
        self.source_label.setText(self._source_text())
        total = len(document.items)
        done = document.completed_count
        self._set_summary(total, total - done, done)
        self.summary.show()
        if not document.items:
            self._add_empty_state(self.t("schedule_empty_title"), self.t("schedule_empty_hint"))
            return
        visible_items = self._filtered_items(document.items)
        if not visible_items:
            self._add_empty_state(self.t("schedule_filter_empty_title"), self.t("schedule_filter_empty_hint"))
            return
        for group_label, items in self._group_items(visible_items):
            group = QLabel(group_label)
            group.setObjectName("ScheduleGroup")
            self.list_layout.addWidget(group)
            for item in items:
                self.list_layout.addWidget(self._make_item_card(item))
        self.list_layout.addStretch(1)

    def _clear_items(self) -> None:
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _add_empty_state(self, title: str, hint: str, *, show_select: bool = False) -> None:
        state = QWidget()
        state_layout = QVBoxLayout(state)
        state_layout.setContentsMargins(24, 70, 24, 24)
        state_layout.setSpacing(8)
        state_layout.addStretch(1)
        title_label = QLabel(title)
        title_label.setObjectName("EmptyTitle")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint_label = QLabel(hint)
        hint_label.setObjectName("MutedLabel")
        hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint_label.setWordWrap(True)
        state_layout.addWidget(title_label)
        state_layout.addWidget(hint_label)
        if show_select:
            button = QPushButton(self.t("schedule_select"))
            button.setObjectName("PrimaryButton")
            button.clicked.connect(self.select_requested.emit)
            button_row = QHBoxLayout()
            button_row.addStretch(1)
            button_row.addWidget(button)
            button_row.addStretch(1)
            state_layout.addLayout(button_row)
        state_layout.addStretch(2)
        self.list_layout.addWidget(state, 1)

    def _make_item_card(self, item: ScheduleItem) -> QFrame:
        status_key, status_color = self._status_appearance(item)
        card = QFrame()
        card.setObjectName("ScheduleCard")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)
        accent = QFrame()
        accent.setFixedWidth(4)
        accent.setStyleSheet(f"background: {status_color}; border: 0; border-radius: 2px;")
        layout.addWidget(accent)

        content = QVBoxLayout()
        content.setSpacing(3)
        title = QLabel(item.title)
        title.setObjectName("ScheduleItemTitleDone" if item.is_done else "ScheduleItemTitle")
        title.setWordWrap(True)
        content.addWidget(title)
        meta_parts = [item.item_id]
        if item.time_range:
            meta_parts.append(item.time_range)
        if item.is_done and item.date is not None:
            meta_parts.append(item.date.isoformat())
        meta = QLabel("  |  ".join(meta_parts))
        meta.setObjectName("MutedLabel")
        content.addWidget(meta)
        if item.description:
            description = ExpandableText(
                item.description,
                expand_text=self.t("schedule_expand"),
                collapse_text=self.t("schedule_collapse"),
                collapsed_lines=3,
            )
            content.addWidget(description)
        layout.addLayout(content, 1)
        side = QVBoxLayout()
        side.setContentsMargins(0, 0, 0, 0)
        side.setSpacing(5)
        status = QLabel(self.t(status_key))
        status.setObjectName("ScheduleStatus")
        status.setStyleSheet(f"color: {status_color};")
        status.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
        side.addWidget(status, 0, Qt.AlignmentFlag.AlignRight)
        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(2)
        edit_button = IconButton("edit", self.t("schedule_edit"), size=24)
        edit_button.setObjectName("ScheduleCardAction")
        delete_button = IconButton("trash", self.t("schedule_delete"), size=24)
        delete_button.setObjectName("ScheduleCardAction")
        if self.tokens is not None:
            edit_button.set_icon_color(self.tokens.muted)
            delete_button.set_icon_color(self.tokens.danger)
        if not item.is_done:
            complete_button = IconButton("check", self.t("schedule_complete"), size=24)
            complete_button.setObjectName("ScheduleCardAction")
            if self.tokens is not None:
                complete_button.set_icon_color(self.tokens.success)
            complete_button.clicked.connect(
                lambda _checked=False, selected=item: self.complete_requested.emit(selected)
            )
            actions.addWidget(complete_button)
        edit_button.clicked.connect(lambda _checked=False, selected=item: self.edit_requested.emit(selected))
        delete_button.clicked.connect(lambda _checked=False, selected=item: self.delete_requested.emit(selected))
        actions.addWidget(edit_button)
        actions.addWidget(delete_button)
        side.addLayout(actions)
        side.addStretch(1)
        layout.addLayout(side)
        return card

    def _filtered_items(self, items: tuple[ScheduleItem, ...]) -> tuple[ScheduleItem, ...]:
        if self.filter_mode == "active":
            return tuple(item for item in items if not item.is_done)
        if self.filter_mode == "done":
            return tuple(item for item in items if item.is_done)
        return items

    def _set_filter(self, mode: str) -> None:
        if mode not in self.summary_values:
            return
        self.filter_mode = mode
        for name, button in self.summary_values.items():
            button.setChecked(name == mode)
        if self.state == "loaded":
            self.refresh()

    def _group_items(self, items: tuple[ScheduleItem, ...]) -> list[tuple[str, list[ScheduleItem]]]:
        active_by_date: dict[dt.date, list[ScheduleItem]] = defaultdict(list)
        backlog: list[ScheduleItem] = []
        completed: list[ScheduleItem] = []
        for item in items:
            if item.is_done:
                completed.append(item)
            elif item.date is None:
                backlog.append(item)
            else:
                active_by_date[item.date].append(item)

        groups: list[tuple[str, list[ScheduleItem]]] = []
        for item_date in sorted(active_by_date):
            key = "schedule_group_date"
            if item_date < self.today:
                key = "schedule_group_overdue"
            elif item_date == self.today:
                key = "schedule_group_today"
            groups.append((self.t(key, date=item_date.isoformat()), active_by_date[item_date]))
        if backlog:
            groups.append((self.t("schedule_group_unscheduled"), backlog))
        if completed:
            completed.sort(key=lambda item: (item.date or dt.date.max, item.title.casefold()))
            groups.append((self.t("schedule_group_completed"), completed))
        return groups

    def _status_appearance(self, item: ScheduleItem) -> tuple[str, str]:
        tokens = self.tokens
        if tokens is None:
            return "schedule_status_planned", "#6bb29a"
        if item.status == SCHEDULE_STATUS_DONE:
            return "schedule_status_done", tokens.muted
        if item.status == SCHEDULE_STATUS_IN_PROGRESS:
            return "schedule_status_in_progress", tokens.accent
        if item.status == SCHEDULE_STATUS_REVIEW:
            return "schedule_status_review", tokens.success
        if item.status == SCHEDULE_STATUS_NEXT:
            return "schedule_status_next", tokens.warning
        if item.status == SCHEDULE_STATUS_HOLD:
            return "schedule_status_hold", tokens.muted
        if item.date is not None and item.date < self.today:
            return "schedule_status_overdue", tokens.danger
        return "schedule_status_planned", tokens.warning

    def _source_text(self) -> str:
        if self.source_path is None:
            return self.t("schedule_no_file")
        parts = self.source_path.parts
        return f"{parts[-2]}/{parts[-1]}" if len(parts) >= 2 else self.source_path.name

    def _set_summary(self, total: int, active: int, done: int) -> None:
        for name, value in (("total", total), ("active", active), ("done", done)):
            self.summary_values[name].setText(f"{self.t(f'schedule_summary_{name}')}  {value:,}")
            self.summary_values[name].setChecked(name == self.filter_mode)
