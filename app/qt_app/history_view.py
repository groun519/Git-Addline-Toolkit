from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from line_tracker import CommitChangeEntry
from qt_app.theme import LIST_ROW_MIN_HEIGHT, PANEL_PADDING, PANEL_SPACING
from qt_app.widgets import ElidedLabel


class CommitHistoryView(QFrame):
    load_more_requested = Signal()
    entry_activated = Signal(object)

    def __init__(self, translate) -> None:
        super().__init__()
        self.setObjectName("Panel")
        self.t = translate
        self.entries: list[CommitChangeEntry] = []
        self.loading = False
        self.exhausted = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(PANEL_PADDING, PANEL_PADDING, PANEL_PADDING, PANEL_PADDING)
        layout.setSpacing(PANEL_SPACING)
        title = QLabel(self.t("commit_history_section"))
        title.setObjectName("PanelTitle")
        layout.addWidget(title)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.host = QWidget()
        self.items_layout = QVBoxLayout(self.host)
        self.items_layout.setContentsMargins(0, 0, 5, 0)
        self.items_layout.setSpacing(3)
        self.items_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinAndMaxSize)
        self.scroll.setWidget(self.host)
        self.scroll.verticalScrollBar().valueChanged.connect(self._on_scroll)
        layout.addWidget(self.scroll, 1)
        self.status = QLabel(self.t("commit_history_empty"))
        self.status.setObjectName("MutedLabel")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status)

    def reset(self) -> None:
        self.entries.clear()
        self.loading = False
        self.exhausted = False
        self._render()

    def set_loading(self, loading: bool) -> None:
        self.loading = loading
        if loading and not self.entries:
            self.status.setText(self.t("loading"))
            self.status.show()

    def append_entries(self, entries: list[CommitChangeEntry], *, exhausted: bool) -> None:
        seen = {entry.commit_hash for entry in self.entries}
        self.entries.extend(entry for entry in entries if entry.commit_hash not in seen)
        self.loading = False
        self.exhausted = exhausted
        self._render()

    def show_error(self, message: str) -> None:
        self.entries.clear()
        self.loading = False
        self.exhausted = True
        self._clear_rows()
        self.status.setText(message or self.t("commit_history_empty"))
        self.status.show()

    def _render(self) -> None:
        self._clear_rows()
        if not self.entries:
            self.status.setText(self.t("commit_history_empty"))
            self.status.show()
            self.items_layout.addStretch(1)
            return
        self.status.hide()
        for entry in self.entries:
            self.items_layout.addWidget(self._make_row(entry))
        self.items_layout.addStretch(1)

    def _clear_rows(self) -> None:
        while self.items_layout.count():
            item = self.items_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _make_row(self, entry: CommitChangeEntry) -> QFrame:
        row = _CommitHistoryRow(entry)
        row.activated.connect(self.entry_activated.emit)
        row.setMinimumHeight(LIST_ROW_MIN_HEIGHT)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(7)
        date_text = entry.date.isoformat()[5:] if entry.date is not None else "--"
        meta = QLabel(f"{date_text}  {entry.short_hash}")
        meta.setObjectName("MutedLabel")
        meta.setMinimumWidth(92)
        subject = ElidedLabel(entry.subject or entry.short_hash)
        subject.setObjectName("HistorySubject")
        layout.addWidget(meta)
        layout.addWidget(subject, 1)
        added = QLabel(f"+{entry.insertions:,}")
        added.setObjectName("DeltaAdd")
        added.setMinimumWidth(54)
        added.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        removed = QLabel(f"-{entry.deletions:,}")
        removed.setObjectName("DeltaRemove")
        removed.setMinimumWidth(54)
        removed.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(added)
        layout.addWidget(removed)
        for label in (meta, subject, added, removed):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        return row

    def _on_scroll(self, value: int) -> None:
        bar = self.scroll.verticalScrollBar()
        threshold = max(0, bar.maximum() - max(40, bar.pageStep() // 3))
        if value >= threshold and not self.loading and not self.exhausted:
            self.load_more_requested.emit()


class _CommitHistoryRow(QFrame):
    activated = Signal(object)

    def __init__(self, entry: CommitChangeEntry) -> None:
        super().__init__()
        self.entry = entry
        self.setObjectName("HistoryRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(entry.subject or entry.short_hash)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            self.activated.emit(self.entry)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.activated.emit(self.entry)
            event.accept()
            return
        super().keyPressEvent(event)
