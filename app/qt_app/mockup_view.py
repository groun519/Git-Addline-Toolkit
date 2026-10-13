from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QSplitter,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from line_tracker_mockups import MockupCatalog, MockupDocument
from qt_app.theme import PANEL_PADDING, PANEL_SPACING, QtThemeTokens
from qt_app.widgets import IconButton, ThemedComboBox


class MockupView(QWidget):
    reload_requested = Signal()
    sync_requested = Signal()
    location_requested = Signal()
    document_requested = Signal(object)
    open_requested = Signal(object)

    def __init__(self, translate) -> None:
        super().__init__()
        self.t = translate
        self.tokens: QtThemeTokens | None = None
        self.catalog: MockupCatalog | None = None
        self.selected_document: MockupDocument | None = None
        self.source_path: Path | None = None
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
        self.title_label = QLabel(self.t("mockup_title"))
        self.title_label.setObjectName("PanelTitle")
        self.source_label = QLabel()
        self.source_label.setObjectName("MutedLabel")
        titles.addWidget(self.title_label)
        titles.addWidget(self.source_label)
        header.addLayout(titles, 1)
        self.reload_button = IconButton("refresh", self.t("mockup_reload"), size=32)
        self.sync_button = IconButton("download", self.t("mockup_sync"), size=32)
        self.location_button = IconButton("folder", self.t("mockup_open_worktree"), size=32)
        self.reload_button.clicked.connect(self.reload_requested.emit)
        self.sync_button.clicked.connect(self.sync_requested.emit)
        self.location_button.clicked.connect(self.location_requested.emit)
        header.addWidget(self.reload_button)
        header.addWidget(self.sync_button)
        header.addWidget(self.location_button)
        layout.addLayout(header)

        self.summary = QFrame()
        self.summary.setObjectName("SummaryStrip")
        summary_layout = QHBoxLayout(self.summary)
        summary_layout.setContentsMargins(10, 6, 10, 6)
        self.summary_label = QLabel()
        self.summary_label.setObjectName("SummaryMetric")
        self.state_label = QLabel()
        self.state_label.setObjectName("MockupStatus")
        summary_layout.addWidget(self.summary_label)
        summary_layout.addStretch(1)
        summary_layout.addWidget(self.state_label)
        layout.addWidget(self.summary)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(7)
        self.search = QLineEdit()
        self.search.setPlaceholderText(self.t("mockup_search"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._populate_tree)
        self.section_filter = ThemedComboBox()
        self.section_filter.addItem(self.t("mockup_filter_all"), "all")
        self.section_filter.addItem(self.t("mockup_filter_wip"), "wip")
        self.section_filter.addItem(self.t("mockup_filter_archive"), "archive")
        self.section_filter.setMinimumWidth(104)
        self.section_filter.currentIndexChanged.connect(self._populate_tree)
        filter_row.addWidget(self.search, 1)
        filter_row.addWidget(self.section_filter)
        layout.addLayout(filter_row)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setObjectName("MockupSplitter")
        self.tree = QTreeWidget()
        self.tree.setObjectName("MockupTree")
        self.tree.setColumnCount(2)
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(13)
        self.tree.setRootIsDecorated(True)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tree.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.tree.header().resizeSection(1, 82)
        self.tree.currentItemChanged.connect(self._on_current_item_changed)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.splitter.addWidget(self.tree)

        preview_host = QFrame()
        preview_host.setObjectName("MockupPreviewHost")
        preview_layout = QVBoxLayout(preview_host)
        preview_layout.setContentsMargins(10, 8, 10, 10)
        preview_layout.setSpacing(6)
        preview_header = QHBoxLayout()
        preview_header.setSpacing(6)
        preview_titles = QVBoxLayout()
        preview_titles.setSpacing(1)
        self.preview_title = QLabel(self.t("mockup_preview_empty"))
        self.preview_title.setObjectName("MockupPreviewTitle")
        self.preview_path = QLabel()
        self.preview_path.setObjectName("MutedLabel")
        preview_titles.addWidget(self.preview_title)
        preview_titles.addWidget(self.preview_path)
        preview_header.addLayout(preview_titles, 1)
        self.open_button = IconButton("open", self.t("mockup_open_document"), size=30)
        self.open_button.clicked.connect(self._request_open)
        preview_header.addWidget(self.open_button)
        preview_layout.addLayout(preview_header)
        self.preview = QTextBrowser()
        self.preview.setObjectName("MockupPreview")
        self.preview.setOpenExternalLinks(True)
        preview_layout.addWidget(self.preview, 1)
        self.splitter.addWidget(preview_host)
        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 5)
        self.splitter.setSizes([220, 520])
        layout.addWidget(self.splitter, 1)

    def set_theme_tokens(self, tokens: QtThemeTokens) -> None:
        self.tokens = tokens
        for button in (self.reload_button, self.sync_button, self.location_button, self.open_button):
            button.set_icon_color(tokens.text)
        self.section_filter.set_chevron_color(tokens.text)
        self.preview.document().setDefaultStyleSheet(
            "body { color: %s; } h1, h2, h3 { color: %s; } "
            "a { color: %s; } code { color: %s; background: %s; } "
            "blockquote { color: %s; border-left: 3px solid %s; padding-left: 10px; } "
            "table { border-collapse: collapse; } th, td { border: 1px solid %s; padding: 4px 7px; }"
            % (
                tokens.text,
                tokens.text,
                tokens.accent,
                tokens.text,
                tokens.raised,
                tokens.muted,
                tokens.accent,
                tokens.border,
            )
        )

    def show_unconfigured(self) -> None:
        self.catalog = None
        self.selected_document = None
        self.source_path = None
        self.source_label.clear()
        self.summary.hide()
        self.search.setEnabled(False)
        self.section_filter.setEnabled(False)
        self.reload_button.setEnabled(False)
        self.sync_button.setEnabled(False)
        self.location_button.setEnabled(False)
        self.open_button.setEnabled(False)
        self.tree.clear()
        self._show_preview_message(self.t("mockup_source_missing"))

    def show_loading(self) -> None:
        self.source_label.setText(self.t("mockup_syncing"))
        self.reload_button.setEnabled(False)
        self.sync_button.setEnabled(False)
        self.location_button.setEnabled(False)
        self.open_button.setEnabled(False)

    def show_error(self, message: str) -> None:
        source = self.source_label.text()
        self.catalog = None
        self.selected_document = None
        self.source_path = None
        self.source_label.setText(source)
        self.summary.hide()
        self.search.setEnabled(False)
        self.section_filter.setEnabled(False)
        self.reload_button.setEnabled(True)
        self.sync_button.setEnabled(False)
        self.location_button.setEnabled(False)
        self.open_button.setEnabled(False)
        self.tree.clear()
        self._show_preview_message(message)

    def show_catalog(self, catalog: MockupCatalog) -> None:
        self.catalog = catalog
        self.selected_document = None
        self.source_path = None
        source = catalog.branch
        if catalog.head:
            source = f"{source}  ·  {catalog.head}"
        self.source_label.setText(source)
        self.summary_label.setText(
            self.t(
                "mockup_summary",
                documents=len(catalog.documents),
                workspaces=catalog.workspace_count,
            )
        )
        self.state_label.setText(self._catalog_state_text(catalog))
        self.summary.show()
        self.search.setEnabled(True)
        self.section_filter.setEnabled(True)
        self.reload_button.setEnabled(True)
        can_sync = catalog.worktree_path is not None and catalog.dirty_count == 0
        self.sync_button.setEnabled(can_sync)
        self.sync_button.setToolTip(
            self.t("mockup_sync") if can_sync else self.t("mockup_sync_disabled")
        )
        self.location_button.setEnabled(catalog.worktree_path is not None)
        self.open_button.setEnabled(False)
        self._populate_tree()

    def show_document(
        self,
        document: MockupDocument,
        content: str,
        source_path: Path | None,
    ) -> None:
        self.selected_document = document
        self.source_path = source_path
        self.preview_title.setText(document.title)
        self.preview_path.setText(document.path)
        if source_path is not None:
            self.preview.document().setBaseUrl(QUrl.fromLocalFile(str(source_path.parent) + "/"))
        else:
            self.preview.document().setBaseUrl(QUrl())
        self.preview.setMarkdown(content)
        self.preview.verticalScrollBar().setValue(0)
        self.open_button.setEnabled(source_path is not None)

    def show_document_error(self, document: MockupDocument, message: str) -> None:
        self.selected_document = document
        self.source_path = None
        self.preview_title.setText(document.title)
        self.preview_path.setText(document.path)
        self.preview.setPlainText(message)
        self.open_button.setEnabled(False)

    def set_syncing(self, syncing: bool) -> None:
        if syncing:
            self.show_loading()
            return
        if self.catalog is not None:
            self.reload_button.setEnabled(True)
            self.sync_button.setEnabled(
                self.catalog.worktree_path is not None and self.catalog.dirty_count == 0
            )
            self.location_button.setEnabled(self.catalog.worktree_path is not None)
            self.open_button.setEnabled(self.source_path is not None)

    def _populate_tree(self, *_args) -> None:
        selected_path = self.selected_document.path if self.selected_document is not None else ""
        self.tree.blockSignals(True)
        self.tree.clear()
        catalog = self.catalog
        if catalog is None:
            self.tree.blockSignals(False)
            return
        query = self.search.text().strip().casefold()
        section = str(self.section_filter.currentData() or "all")
        groups: dict[str, list[MockupDocument]] = defaultdict(list)
        for document in catalog.documents:
            if section != "all" and document.section != section:
                continue
            haystack = "\n".join(
                (document.title, document.path, document.status, document.search_text)
            ).casefold()
            if query and query not in haystack:
                continue
            groups[document.workspace].append(document)

        selected_item: QTreeWidgetItem | None = None
        first_item: QTreeWidgetItem | None = None
        for workspace in sorted(groups, key=lambda value: (value != "overview", value.casefold())):
            label = self.t("mockup_workspace_overview") if workspace == "overview" else workspace
            group_item = QTreeWidgetItem([f"{label}  {len(groups[workspace])}", ""])
            group_item.setFlags(group_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.tree.addTopLevelItem(group_item)
            for document in groups[workspace]:
                item = QTreeWidgetItem([document.title, document.status])
                item.setData(0, Qt.ItemDataRole.UserRole, document)
                item.setToolTip(0, self._document_tooltip(document, query))
                group_item.addChild(item)
                first_item = first_item or item
                if document.path == selected_path:
                    selected_item = item
            group_item.setExpanded(bool(query) or workspace == "overview" or len(groups) == 1)
        self.tree.blockSignals(False)

        target = selected_item or first_item
        if target is not None:
            self.tree.setCurrentItem(target)
            self._on_current_item_changed(target, None)
        else:
            self.selected_document = None
            self.source_path = None
            self.open_button.setEnabled(False)
            self._show_preview_message(self.t("mockup_empty"))

    @staticmethod
    def _document_tooltip(document: MockupDocument, query: str) -> str:
        if not query:
            return document.path
        position = document.search_text.find(query)
        if position < 0:
            return document.path
        start = max(0, position - 55)
        end = min(len(document.search_text), position + len(query) + 75)
        excerpt = " ".join(document.search_text[start:end].split())
        if start:
            excerpt = f"…{excerpt}"
        if end < len(document.search_text):
            excerpt = f"{excerpt}…"
        return f"{document.path}\n\n{excerpt}"

    def _on_current_item_changed(
        self,
        current: QTreeWidgetItem | None,
        _previous: QTreeWidgetItem | None,
    ) -> None:
        if current is None:
            return
        document = current.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(document, MockupDocument):
            self.selected_document = document
            self.document_requested.emit(document)

    def _on_item_double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        document = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(document, MockupDocument):
            self.open_requested.emit(document)

    def _request_open(self) -> None:
        if self.selected_document is not None:
            self.open_requested.emit(self.selected_document)

    def _show_preview_message(self, message: str) -> None:
        self.preview_title.setText(self.t("mockup_title"))
        self.preview_path.clear()
        self.preview.setPlainText(message)

    def _catalog_state_text(self, catalog: MockupCatalog) -> str:
        states: list[str] = []
        if catalog.dirty_count:
            states.append(self.t("mockup_state_dirty", count=catalog.dirty_count))
        if catalog.ahead:
            states.append(self.t("mockup_state_ahead", count=catalog.ahead))
        if catalog.behind:
            states.append(self.t("mockup_state_behind", count=catalog.behind))
        return "  ·  ".join(states) if states else self.t("mockup_state_clean")
