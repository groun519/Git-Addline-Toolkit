from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from line_tracker import CommitChangeEntry, CommitDetail, CommitFileChange, get_commit_detail
from line_tracker_version import APP_VERSION
from qt_app.theme import QtThemeTokens
from qt_app.widgets import ElidedLabel, WindowTitleBar


class CommitDetailDialog(QDialog):
    detail_loaded = Signal(object)
    detail_failed = Signal(str)

    def __init__(
        self,
        parent,
        *,
        repo: Path,
        entry: CommitChangeEntry,
        translate,
        tokens: QtThemeTokens,
    ) -> None:
        super().__init__(parent)
        self.repo = repo
        self.entry = entry
        self.t = translate
        self.tokens = tokens
        self._loading_started = False
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setModal(True)
        self.setMinimumSize(620, 500)
        self.resize(720, 620)
        self.setWindowTitle(self.t("commit_detail_title"))

        root = QVBoxLayout(self)
        root.setContentsMargins(1, 1, 1, 1)
        root.setSpacing(0)
        self.titlebar = WindowTitleBar(self.t("commit_detail_title"), APP_VERSION)
        self.titlebar.minimize_button.hide()
        self.titlebar.close_requested.connect(self.reject)
        root.addWidget(self.titlebar)

        content = QFrame()
        content.setObjectName("DialogContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(18, 16, 18, 16)
        content_layout.setSpacing(12)

        self.subject = QLabel(entry.subject or entry.short_hash)
        self.subject.setObjectName("CommitDetailSubject")
        self.subject.setWordWrap(True)
        content_layout.addWidget(self.subject)

        metadata = QFrame()
        metadata.setObjectName("CommitDetailMeta")
        metadata_layout = QVBoxLayout(metadata)
        metadata_layout.setContentsMargins(12, 10, 12, 10)
        metadata_layout.setSpacing(5)
        self.author = self._metadata_row(self.t("commit_detail_author"), "-")
        date_text = entry.date.isoformat() if entry.date is not None else "-"
        self.authored_at = self._metadata_row(self.t("commit_detail_date"), date_text)
        self.commit_hash = self._metadata_row(self.t("commit_detail_hash"), entry.commit_hash)
        metadata_layout.addLayout(self.author[0])
        metadata_layout.addLayout(self.authored_at[0])
        metadata_layout.addLayout(self.commit_hash[0])
        content_layout.addWidget(metadata)

        body_title = QLabel(self.t("commit_detail_body"))
        body_title.setObjectName("SectionTitle")
        content_layout.addWidget(body_title)
        self.body = QLabel(self.t("commit_detail_no_body"))
        self.body.setObjectName("MutedLabel")
        self.body.setWordWrap(True)
        self.body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        content_layout.addWidget(self.body)

        file_header = QHBoxLayout()
        files_title = QLabel(self.t("commit_detail_files"))
        files_title.setObjectName("SectionTitle")
        self.file_count = QLabel()
        self.file_count.setObjectName("MutedLabel")
        self.total_added = QLabel(f"+{entry.insertions:,}")
        self.total_added.setObjectName("DeltaAdd")
        self.total_removed = QLabel(f"-{entry.deletions:,}")
        self.total_removed.setObjectName("DeltaRemove")
        file_header.addWidget(files_title)
        file_header.addWidget(self.file_count)
        file_header.addStretch(1)
        file_header.addWidget(self.total_added)
        file_header.addWidget(self.total_removed)
        content_layout.addLayout(file_header)

        self.file_scroll = QScrollArea()
        self.file_scroll.setWidgetResizable(True)
        self.file_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.file_host = QWidget()
        self.file_layout = QVBoxLayout(self.file_host)
        self.file_layout.setContentsMargins(0, 0, 5, 0)
        self.file_layout.setSpacing(2)
        self.file_scroll.setWidget(self.file_host)
        content_layout.addWidget(self.file_scroll, 1)

        self.loading = QLabel(self.t("commit_detail_loading"))
        self.loading.setObjectName("MutedLabel")
        self.loading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content_layout.addWidget(self.loading)

        actions = QHBoxLayout()
        actions.addStretch(1)
        close_button = QPushButton(self.t("commit_detail_close"))
        close_button.setObjectName("PrimaryButton")
        close_button.clicked.connect(self.accept)
        actions.addWidget(close_button)
        content_layout.addLayout(actions)
        root.addWidget(content, 1)

        self.detail_loaded.connect(self._show_detail)
        self.detail_failed.connect(self._show_error)
        self.setStyleSheet(parent.styleSheet())
        self.titlebar.set_icon_color(tokens.text)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if not self._loading_started:
            self._loading_started = True
            threading.Thread(target=self._load_detail, daemon=True).start()

    def _load_detail(self) -> None:
        try:
            detail = get_commit_detail(self.repo, self.entry.commit_hash)
        except (OSError, RuntimeError) as exc:
            self.detail_failed.emit(str(exc))
            return
        self.detail_loaded.emit(detail)

    def _show_detail(self, detail: CommitDetail) -> None:
        self.subject.setText(detail.subject or detail.short_hash)
        author = detail.author_name
        if detail.author_email:
            author = f"{author} <{detail.author_email}>" if author else detail.author_email
        self.author[1].setText(author or "-")
        authored_at = detail.authored_at.astimezone().strftime("%Y-%m-%d %H:%M") if detail.authored_at else "-"
        self.authored_at[1].setText(authored_at)
        self.commit_hash[1].setText(detail.commit_hash)
        self.body.setText(detail.body or self.t("commit_detail_no_body"))
        self.file_count.setText(f"{len(detail.files):,}")
        self.total_added.setText(f"+{detail.insertions:,}")
        self.total_removed.setText(f"-{detail.deletions:,}")
        self._set_files(detail.files)
        self.loading.hide()

    def _show_error(self, message: str) -> None:
        self.loading.setText(f"{self.t('commit_detail_error')}\n{message}")

    def _set_files(self, files: tuple[CommitFileChange, ...]) -> None:
        while self.file_layout.count():
            item = self.file_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for change in files:
            self.file_layout.addWidget(self._make_file_row(change))
        self.file_layout.addStretch(1)

    def _make_file_row(self, change: CommitFileChange) -> QFrame:
        row = QFrame()
        row.setObjectName("CommitFileRow")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(9, 6, 9, 6)
        layout.setSpacing(8)
        path = ElidedLabel(change.path)
        path.setObjectName("CommitFilePath")
        path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(path, 1)
        if change.is_binary:
            binary = QLabel(self.t("commit_detail_binary"))
            binary.setObjectName("MutedLabel")
            binary.setMinimumWidth(116)
            binary.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            layout.addWidget(binary)
        else:
            added = QLabel(f"+{change.insertions:,}")
            added.setObjectName("DeltaAdd")
            added.setMinimumWidth(54)
            added.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            removed = QLabel(f"-{change.deletions:,}")
            removed.setObjectName("DeltaRemove")
            removed.setMinimumWidth(54)
            removed.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            layout.addWidget(added)
            layout.addWidget(removed)
        return row

    @staticmethod
    def _metadata_row(label: str, value: str) -> tuple[QHBoxLayout, QLabel]:
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        name = QLabel(label)
        name.setObjectName("CommitDetailField")
        name.setFixedWidth(72)
        content = QLabel(value)
        content.setObjectName("CommitDetailValue")
        content.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(name)
        layout.addWidget(content, 1)
        return layout, content
