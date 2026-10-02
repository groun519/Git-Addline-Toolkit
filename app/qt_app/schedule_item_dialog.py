from __future__ import annotations

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from line_tracker_schedule import (
    SCHEDULE_STATUS_DONE,
    SCHEDULE_STATUS_HOLD,
    SCHEDULE_STATUS_IN_PROGRESS,
    SCHEDULE_STATUS_NEXT,
    SCHEDULE_STATUS_PLANNED,
    SCHEDULE_STATUS_REVIEW,
    ScheduleItem,
)
from line_tracker_version import APP_VERSION
from qt_app.theme import QtThemeTokens
from qt_app.widgets import ThemedComboBox, ThemedDateEdit, WindowTitleBar


class ScheduleItemDialog(QDialog):
    def __init__(self, parent, *, item: ScheduleItem, translate, tokens: QtThemeTokens) -> None:
        super().__init__(parent)
        self.item = item
        self.t = translate
        self.tokens = tokens
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setModal(True)
        self.setMinimumSize(540, 500)
        self.resize(580, 540)
        self.setWindowTitle(self.t("schedule_edit_title"))

        root = QVBoxLayout(self)
        root.setContentsMargins(1, 1, 1, 1)
        root.setSpacing(0)
        self.titlebar = WindowTitleBar(self.t("schedule_edit_title"), APP_VERSION)
        self.titlebar.minimize_button.hide()
        self.titlebar.close_requested.connect(self.reject)
        root.addWidget(self.titlebar)

        content = QFrame()
        content.setObjectName("DialogContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(18, 16, 18, 16)
        content_layout.setSpacing(14)

        form = QFormLayout()
        form.setHorizontalSpacing(20)
        form.setVerticalSpacing(12)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.id_edit = QLineEdit(item.item_id)
        self.status_combo = ThemedComboBox()
        for status, label_key in (
            (SCHEDULE_STATUS_PLANNED, "schedule_status_planned"),
            (SCHEDULE_STATUS_IN_PROGRESS, "schedule_status_in_progress"),
            (SCHEDULE_STATUS_REVIEW, "schedule_status_review"),
            (SCHEDULE_STATUS_NEXT, "schedule_status_next"),
            (SCHEDULE_STATUS_HOLD, "schedule_status_hold"),
            (SCHEDULE_STATUS_DONE, "schedule_status_done"),
        ):
            self.status_combo.addItem(self.t(label_key), status)
        self.status_combo.setCurrentIndex(max(0, self.status_combo.findData(item.status)))
        self.status_combo.set_chevron_color(tokens.muted)

        self.backlog_check = QCheckBox(self.t("schedule_item_backlog"))
        self.backlog_check.setChecked(item.date is None)
        self.date_edit = ThemedDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setDate(QDate(item.date) if item.date is not None else QDate.currentDate())
        self.date_edit.setEnabled(item.date is not None)
        self.date_edit.set_chevron_color(tokens.muted)
        self.backlog_check.toggled.connect(lambda checked: self.date_edit.setEnabled(not checked))

        self.time_edit = QLineEdit(item.time_range)
        self.time_edit.setPlaceholderText("18:00~22:00")
        self.title_edit = QLineEdit(item.title)
        self.description_edit = QPlainTextEdit(item.description)
        self.description_edit.setMinimumHeight(150)

        form.addRow(self.t("schedule_item_id"), self.id_edit)
        form.addRow(self.t("schedule_item_status"), self.status_combo)
        form.addRow("", self.backlog_check)
        form.addRow(self.t("schedule_item_date"), self.date_edit)
        form.addRow(self.t("schedule_item_time"), self.time_edit)
        form.addRow(self.t("schedule_item_title"), self.title_edit)
        form.addRow(self.t("schedule_item_description"), self.description_edit)
        content_layout.addLayout(form, 1)

        actions = QHBoxLayout()
        actions.addStretch(1)
        cancel = QPushButton(self.t("cancel"))
        cancel.clicked.connect(self.reject)
        save = QPushButton(self.t("schedule_save"))
        save.setObjectName("PrimaryButton")
        save.clicked.connect(self._accept_if_valid)
        actions.addWidget(cancel)
        actions.addWidget(save)
        content_layout.addLayout(actions)
        root.addWidget(content, 1)

        self.setStyleSheet(parent.styleSheet())
        self.titlebar.set_icon_color(tokens.text)
        self.title_edit.setFocus()
        self.title_edit.selectAll()

    def result_item(self) -> ScheduleItem:
        selected_date = None if self.backlog_check.isChecked() else self.date_edit.date().toPython()
        return ScheduleItem(
            item_id=self.id_edit.text().strip(),
            title=self.title_edit.text().strip(),
            date=selected_date,
            description=self.description_edit.toPlainText().strip(),
            status=str(self.status_combo.currentData()),
            time_range=self.time_edit.text().strip(),
            section=self.item.section,
            source_start_line=self.item.source_start_line,
            source_end_line=self.item.source_end_line,
        )

    def _accept_if_valid(self) -> None:
        if not self.id_edit.text().strip() or not self.title_edit.text().strip():
            QMessageBox.warning(self, self.t("schedule_edit_error_title"), self.t("schedule_required_error"))
            return
        if "|" in self.id_edit.text() or "|" in self.title_edit.text() or "|" in self.time_edit.text():
            QMessageBox.warning(self, self.t("schedule_edit_error_title"), self.t("schedule_invalid_separator"))
            return
        self.accept()
