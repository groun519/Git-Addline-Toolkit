from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLayout, QScrollArea, QVBoxLayout, QWidget

from line_tracker import CommitChangeEntry


class CommitHistoryView(QFrame):
    load_more_requested = Signal()

    def __init__(self, translate) -> None:
        super().__init__()
        self.setObjectName("Panel")
        self.t = translate
        self.entries: list[CommitChangeEntry] = []
        self.loading = False
        self.exhausted = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(9)
        title = QLabel(self.t("commit_history_section"))
        title.setObjectName("SectionTitle")
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

    def _render(self) -> None:
        while self.items_layout.count():
            item = self.items_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        if not self.entries:
            self.status.setText(self.t("commit_history_empty"))
            self.status.show()
            self.items_layout.addStretch(1)
            return
        self.status.hide()
        for entry in self.entries:
            self.items_layout.addWidget(self._make_row(entry))
        self.items_layout.addStretch(1)

    def _make_row(self, entry: CommitChangeEntry) -> QFrame:
        row = QFrame()
        row.setObjectName("HistoryRow")
        row.setMinimumHeight(30)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(9, 7, 9, 7)
        layout.setSpacing(8)
        date_text = entry.date.isoformat()[5:] if entry.date is not None else "--"
        meta = QLabel(f"{date_text}  {entry.short_hash}")
        meta.setObjectName("MutedLabel")
        meta.setMinimumWidth(92)
        subject = QLabel(entry.subject or entry.short_hash)
        subject.setObjectName("HistorySubject")
        subject.setToolTip(entry.subject)
        layout.addWidget(meta)
        layout.addWidget(subject, 1)
        added = QLabel(f"+{entry.insertions:,}")
        added.setObjectName("DeltaAdd")
        removed = QLabel(f"-{entry.deletions:,}")
        removed.setObjectName("DeltaRemove")
        layout.addWidget(added)
        layout.addWidget(removed)
        return row

    def _on_scroll(self, value: int) -> None:
        bar = self.scroll.verticalScrollBar()
        threshold = max(0, bar.maximum() - max(40, bar.pageStep() // 3))
        if value >= threshold and not self.loading and not self.exhausted:
            self.load_more_requested.emit()
