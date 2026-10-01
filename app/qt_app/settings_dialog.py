from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from line_tracker import LANGUAGE_NAMES
from line_tracker_settings import UISettings
from line_tracker_theme import get_theme_names
from line_tracker_ui_resources import LANG_DISPLAY, LANG_OPTIONS
from line_tracker_version import APP_VERSION
from qt_app.theme import QtThemeTokens
from qt_app.widgets import IconButton, ThemedComboBox, ThemedDateEdit, WindowTitleBar, language_color


GRAPH_DAY_OPTIONS = ("7", "14", "21", "30", "60", "90", "180")


@dataclass(frozen=True)
class SettingsValues:
    lang: str
    theme: str
    repo_path: str
    custom_today_enabled: bool
    custom_today: str
    goal: int
    author_raw: str
    author_display: str
    auto_refresh: bool
    graph_days: str
    graph_show_additions: bool
    graph_show_deletions: bool
    graph_show_commits: bool
    graph_languages: tuple[str, ...]
    graph_curve: float
    schedule_path: str
    selected_branches: tuple[str, ...] = ()


class SettingsDialog(QDialog):
    def __init__(
        self,
        parent,
        *,
        translate,
        settings: UISettings,
        tokens: QtThemeTokens,
        author_options: list[str],
        author_filter_map: dict[str, str],
        author_display: str,
        language_order: tuple[str, ...] | None = None,
        branch_options: tuple[str, ...] = (),
        current_branch: str = "",
    ) -> None:
        super().__init__(parent)
        self.t = translate
        self.settings = settings
        self.tokens = tokens
        self.author_filter_map = author_filter_map
        self.language_order = language_order
        self.branch_options = branch_options
        self.current_branch = current_branch
        self.restart_requested = False
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setModal(True)
        self.setMinimumSize(620, 500)
        self.resize(680, 560)

        root = QVBoxLayout(self)
        root.setContentsMargins(1, 1, 1, 1)
        root.setSpacing(0)
        self.titlebar = WindowTitleBar(self.t("settings"), APP_VERSION)
        self.titlebar.minimize_button.hide()
        self.titlebar.close_requested.connect(self.reject)
        root.addWidget(self.titlebar)
        content = QFrame()
        content.setObjectName("DialogContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(16, 14, 16, 14)
        content_layout.setSpacing(12)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_general_tab(), self.t("settings_general_tab"))
        self.tabs.addTab(self._build_repository_tab(), self.t("settings_repo_tab"))
        self.tabs.addTab(self._build_tracking_tab(author_options, author_display), self.t("settings_tracking_tab"))
        self.tabs.addTab(self._build_graph_tab(), self.t("graph_settings_title"))
        self.tabs.addTab(self._build_schedule_tab(), self.t("settings_schedule_tab"))
        content_layout.addWidget(self.tabs, 1)
        actions = QHBoxLayout()
        self.restart_button = QPushButton(self.t("restart_app"))
        self.restart_button.clicked.connect(self._accept_restart)
        actions.addWidget(self.restart_button)
        actions.addStretch(1)
        cancel = QPushButton(self.t("cancel") if self.t("cancel") != "cancel" else "Cancel")
        cancel.clicked.connect(self.reject)
        apply_button = QPushButton(self.t("graph_apply"))
        apply_button.setObjectName("PrimaryButton")
        apply_button.clicked.connect(self.accept)
        actions.addWidget(cancel)
        actions.addWidget(apply_button)
        content_layout.addLayout(actions)
        root.addWidget(content, 1)
        self.setStyleSheet(parent.styleSheet())
        self.titlebar.set_icon_color(tokens.text)

    def _tab(self) -> tuple[QWidget, QFormLayout]:
        tab = QWidget()
        form = QFormLayout(tab)
        form.setContentsMargins(16, 18, 16, 16)
        form.setHorizontalSpacing(20)
        form.setVerticalSpacing(13)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        return tab, form

    def _build_general_tab(self) -> QWidget:
        tab, form = self._tab()
        self.lang_combo = self._combo()
        self.lang_combo.addItems(list(LANG_OPTIONS))
        self.lang_combo.setCurrentText(LANG_DISPLAY.get(self.settings.lang, "English"))
        self.theme_combo = self._combo()
        self.theme_names = list(get_theme_names())
        self.theme_labels = [self.t(f"theme_{name}") for name in self.theme_names]
        self.theme_combo.addItems(self.theme_labels)
        if self.settings.theme in self.theme_names:
            self.theme_combo.setCurrentIndex(self.theme_names.index(self.settings.theme))
        form.addRow(self.t("lang_label"), self.lang_combo)
        form.addRow(self.t("theme_label"), self.theme_combo)
        return tab

    def _build_repository_tab(self) -> QWidget:
        tab, form = self._tab()
        row = QHBoxLayout()
        self.repo_edit = QLineEdit(self.settings.repo_path)
        browse = IconButton("folder", self.t("repo_select"), size=34)
        browse.set_icon_color(self.tokens.text)
        browse.clicked.connect(self._browse_repo)
        row.addWidget(self.repo_edit, 1)
        row.addWidget(browse)
        form.addRow(self.t("repo_label"), row)
        return tab

    def _build_tracking_tab(self, author_options: list[str], author_display: str) -> QWidget:
        tab, form = self._tab()
        self.custom_date = QCheckBox(self.t("custom_date"))
        self.custom_date.setChecked(bool(self.settings.custom_today_enabled))
        self.date_edit = ThemedDateEdit()
        self.date_edit.set_chevron_color(self.tokens.muted)
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        saved_date = QDate.fromString(self.settings.custom_today, "yyyy-MM-dd")
        self.date_edit.setDate(saved_date if saved_date.isValid() else QDate.currentDate())
        self.date_edit.setEnabled(self.custom_date.isChecked())
        self.custom_date.toggled.connect(self.date_edit.setEnabled)
        self.goal_spin = QSpinBox()
        self.goal_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.goal_spin.setRange(1, 2_000_000_000)
        self.goal_spin.setValue(_positive_int(self.settings.goal, 100_000))
        self.goal_spin.setGroupSeparatorShown(True)
        self.author_combo = self._combo()
        self.author_combo.addItems(author_options)
        self.author_combo.setCurrentText(author_display if author_display in author_options else author_options[0])
        self.auto_refresh = QCheckBox(self.t("auto_refresh"))
        self.auto_refresh.setChecked(bool(self.settings.auto_refresh))
        form.addRow("", self.custom_date)
        form.addRow(self.t("today_label"), self.date_edit)
        form.addRow(self.t("goal_label"), self.goal_spin)
        form.addRow(self.t("author_label"), self.author_combo)
        branch_list = QWidget()
        branch_layout = QVBoxLayout(branch_list)
        branch_layout.setContentsMargins(4, 4, 4, 4)
        branch_layout.setSpacing(5)
        selected = set(self.settings.selected_branches or (self.current_branch,))
        self.branch_checks: dict[str, QCheckBox] = {}
        for branch in self.branch_options:
            checkbox = QCheckBox(branch)
            checkbox.setChecked(branch in selected)
            branch_layout.addWidget(checkbox)
            self.branch_checks[branch] = checkbox
        branch_layout.addStretch(1)
        branch_scroll = QScrollArea()
        branch_scroll.setWidgetResizable(True)
        branch_scroll.setWidget(branch_list)
        branch_scroll.setFixedHeight(118)
        form.addRow(self.t("selected_branches_label"), branch_scroll)
        branch_hint = QLabel(self.t("selected_branches_hint"))
        branch_hint.setObjectName("MutedLabel")
        branch_hint.setWordWrap(True)
        form.addRow("", branch_hint)
        form.addRow("", self.auto_refresh)
        return tab

    def _build_graph_tab(self) -> QWidget:
        tab, form = self._tab()
        self.graph_days = self._combo()
        self.graph_days.addItems(GRAPH_DAY_OPTIONS)
        self.graph_days.setCurrentText(self.settings.graph_days if self.settings.graph_days in GRAPH_DAY_OPTIONS else "30")
        flags = QHBoxLayout()
        self.graph_additions = QCheckBox(self.t("graph_show_additions"))
        self.graph_deletions = QCheckBox(self.t("graph_show_deletions"))
        self.graph_commits = QCheckBox(self.t("graph_show_commits"))
        self.graph_additions.setChecked(bool(self.settings.graph_show_additions))
        self.graph_deletions.setChecked(bool(self.settings.graph_show_deletions))
        self.graph_commits.setChecked(bool(self.settings.graph_show_commits))
        flags.addWidget(self.graph_additions)
        flags.addWidget(self.graph_deletions)
        flags.addWidget(self.graph_commits)
        languages = QGridLayout()
        languages.setHorizontalSpacing(16)
        languages.setVerticalSpacing(8)
        selected_languages = set(self.settings.graph_languages)
        self.graph_language_checks: dict[str, QCheckBox] = {}
        for index, language in enumerate(LANGUAGE_NAMES):
            checkbox = QCheckBox(language)
            checkbox.setChecked(language in selected_languages)
            checkbox.setStyleSheet(
                f"QCheckBox {{ color: {language_color(language, self.language_order)}; }}"
            )
            languages.addWidget(checkbox, index // 3, index % 3)
            self.graph_language_checks[language] = checkbox
        curve_row = QHBoxLayout()
        self.graph_curve = QSlider(Qt.Orientation.Horizontal)
        self.graph_curve.setRange(0, 100)
        self.graph_curve.setValue(round(float(self.settings.graph_curve)))
        self.graph_curve_value = QLabel(str(self.graph_curve.value()))
        self.graph_curve.valueChanged.connect(lambda value: self.graph_curve_value.setText(str(value)))
        curve_row.addWidget(self.graph_curve, 1)
        curve_row.addWidget(self.graph_curve_value)
        form.addRow(self.t("graph_period"), self.graph_days)
        form.addRow(self.t("graph_metrics"), flags)
        form.addRow(self.t("graph_languages"), languages)
        form.addRow(self.t("graph_curve"), curve_row)
        return tab

    def _build_schedule_tab(self) -> QWidget:
        tab, form = self._tab()
        row = QHBoxLayout()
        self.schedule_edit = QLineEdit(self.settings.schedule_path)
        browse = IconButton("file", self.t("schedule_select"), size=34)
        browse.set_icon_color(self.tokens.text)
        browse.clicked.connect(self._browse_schedule)
        row.addWidget(self.schedule_edit, 1)
        row.addWidget(browse)
        hint = QLabel(self.t("schedule_path_hint"))
        hint.setObjectName("MutedLabel")
        hint.setWordWrap(True)
        form.addRow(self.t("schedule_path_label"), row)
        form.addRow("", hint)
        return tab

    def values(self) -> SettingsValues:
        theme_index = max(0, self.theme_combo.currentIndex())
        date_value = self.date_edit.date().toPython()
        author_display = self.author_combo.currentText()
        selected_branches = tuple(
            branch for branch, checkbox in self.branch_checks.items() if checkbox.isChecked()
        )
        if selected_branches == (self.current_branch,):
            selected_branches = ()
        return SettingsValues(
            lang=LANG_OPTIONS.get(self.lang_combo.currentText(), "ko"),
            theme=self.theme_names[theme_index],
            repo_path=self.repo_edit.text().strip(),
            custom_today_enabled=self.custom_date.isChecked(),
            custom_today=date_value.isoformat() if isinstance(date_value, dt.date) else "",
            goal=self.goal_spin.value(),
            author_raw=self.author_filter_map.get(author_display, "auto"),
            author_display=author_display,
            auto_refresh=self.auto_refresh.isChecked(),
            graph_days=self.graph_days.currentText(),
            graph_show_additions=self.graph_additions.isChecked(),
            graph_show_deletions=self.graph_deletions.isChecked(),
            graph_show_commits=self.graph_commits.isChecked(),
            graph_languages=tuple(
                language
                for language in LANGUAGE_NAMES
                if self.graph_language_checks[language].isChecked()
            ),
            graph_curve=float(self.graph_curve.value()),
            schedule_path=self.schedule_edit.text().strip(),
            selected_branches=selected_branches,
        )

    def _browse_repo(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, self.t("repo_dialog_title"), self.repo_edit.text())
        if selected:
            self.repo_edit.setText(selected)

    def _browse_schedule(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            self.t("schedule_dialog_title"),
            self.repo_edit.text() or str(Path.home()),
            "Markdown (*.md)",
        )
        if selected:
            self.schedule_edit.setText(selected)

    def _accept_restart(self) -> None:
        self.restart_requested = True
        self.accept()

    def _combo(self) -> ThemedComboBox:
        combo = ThemedComboBox()
        combo.set_chevron_color(self.tokens.muted)
        return combo


def _positive_int(value: object, fallback: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed > 0 else fallback
