from __future__ import annotations

import datetime as dt
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QDialog, QFrame, QLabel, QPushButton, QWidget
except ImportError:
    QApplication = None


@unittest.skipIf(QApplication is None, "PySide6 is not installed")
class QtApplicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_runtime_icons_render(self) -> None:
        from qt_app.icons import make_icon

        for name in ("settings", "refresh", "file", "folder", "overlay", "history", "edit", "trash", "check"):
            self.assertFalse(make_icon(name, "#ffffff", 20).isNull())

    def test_activity_graph_detects_dominant_peak_and_renders(self) -> None:
        from line_tracker_theme import get_theme_palette
        from qt_app.theme import build_theme_tokens
        from qt_app.widgets import ActivityGraph

        start = dt.date(2026, 8, 1)
        points = [(start + dt.timedelta(days=index), value) for index, value in enumerate((20, 30, 25, 40, 35, 22, 30, 900))]
        graph = ActivityGraph()
        graph.resize(640, 300)
        graph.set_theme_tokens(build_theme_tokens(get_theme_palette("forest")))
        graph.set_data([("additions", "#6bb29a", points, True)], points[-1][0], 35.0)
        self.assertTrue(graph.uses_adaptive_axis)
        self.assertFalse(graph.grab().isNull())

    def test_language_colors_preserve_current_project_display_order(self) -> None:
        from qt_app.widgets import LANGUAGE_COLORS, complete_language_order, language_color

        language_order = complete_language_order(("C++", "C#", "JSON", "Config", "Docs", "Other"))

        self.assertEqual(language_color("JSON", language_order), LANGUAGE_COLORS[2])
        self.assertEqual(language_color("JSON", language_order), "#6f9fd8")

    def test_language_progress_tooltip_only_opens_over_colored_segment(self) -> None:
        from line_tracker_theme import get_theme_palette
        from qt_app.theme import build_theme_tokens
        from qt_app.widgets import LanguageProgressBar

        progress = LanguageProgressBar()
        progress.resize(400, 24)
        progress.set_theme_tokens(build_theme_tokens(get_theme_palette("forest")))
        progress.set_progress(50.0, "50 / 100 [50%]", {"C++": 30, "JSON": 20})
        progress.show()
        progress.grab()
        self.app.processEvents()

        with (
            patch("qt_app.widgets.QToolTip.showText") as show_tooltip,
            patch("qt_app.widgets.QToolTip.hideText") as hide_tooltip,
        ):
            QTest.mouseMove(progress, QPoint(20, 12))
            show_tooltip.assert_called_once()
            QTest.mouseMove(progress, QPoint(350, 12))
            hide_tooltip.assert_called_once()

        progress.close()

    def test_schedule_location_opens_selected_file_in_explorer(self) -> None:
        from line_tracker_settings import UISettings
        from qt_app.main_window import LineTrackerQtWindow

        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = Path(tmp_dir)
            schedule_path = repo / "docs" / "SCHEDULE.md"
            schedule_path.parent.mkdir()
            schedule_path.write_text("@@BACKLOG", encoding="utf-8")
            window = SimpleNamespace(
                repo_selected=True,
                repo=repo,
                settings=UISettings(schedule_path="docs/SCHEDULE.md"),
                t=lambda key: key,
            )

            with patch("qt_app.main_window.subprocess.Popen") as open_location:
                LineTrackerQtWindow.open_schedule_location(window)
                open_location.assert_called_once()
                command = open_location.call_args.args[0]
                self.assertEqual(command[:2], ["explorer.exe", "/select,"])
                self.assertTrue(Path(command[2]).samefile(schedule_path))

    def test_schedule_view_renders_directive_document(self) -> None:
        from line_tracker_schedule import SCHEDULE_STATUS_DONE, ScheduleDocument, ScheduleItem
        from line_tracker_theme import get_theme_palette
        from qt_app.schedule_view import ScheduleView
        from qt_app.theme import build_theme_tokens
        from qt_app.widgets import ExpandableText

        translate = lambda key, **kwargs: key.format(**kwargs)
        view = ScheduleView(translate)
        view.set_theme_tokens(build_theme_tokens(get_theme_palette("forest")))
        document = ScheduleDocument(
            title="Work Plan",
            items=(
                ScheduleItem(
                    "ITEM-1",
                    "Inventory",
                    date=dt.date(2026, 8, 4),
                    description="A long schedule detail " * 80,
                ),
                ScheduleItem("ITEM-2", "Completed", date=dt.date(2026, 8, 3), status=SCHEDULE_STATUS_DONE),
            ),
            source_path=Path("work-plan.md"),
        )
        view.resize(520, 600)
        view.show()
        view.show_document(document, dt.date(2026, 8, 4))
        self.app.processEvents()
        self.assertEqual(view.title_label.text(), "Work Plan")
        self.assertTrue(view.summary.isVisibleTo(view))
        self.assertGreater(view.list_layout.count(), 1)
        self.assertTrue(view.summary_values["total"].isChecked())
        expandable = view.findChildren(ExpandableText)[-1]
        self.assertTrue(expandable.toggle_button.isVisible())
        self.assertFalse(expandable.expanded)
        expandable.toggle_button.click()
        self.assertTrue(expandable.expanded)

        completed: list[str] = []
        view.complete_requested.connect(lambda item: completed.append(item.item_id))
        complete_button = [
            button for button in view.findChildren(QPushButton) if button.toolTip() == "schedule_complete"
        ][-1]
        complete_button.click()
        self.assertEqual(completed, ["ITEM-1"])

        view.summary_values["done"].click()

        self.assertEqual(view.filter_mode, "done")
        self.assertTrue(view.summary_values["done"].isChecked())
        self.assertEqual([item.item_id for item in view._filtered_items(document.items)], ["ITEM-2"])
        self.app.processEvents()

        edited: list[str] = []
        view.edit_requested.connect(lambda item: edited.append(item.item_id))
        edit_button = [
            button for button in view.findChildren(QPushButton) if button.toolTip() == "schedule_edit"
        ][-1]
        edit_button.click()
        self.assertEqual(edited, ["ITEM-2"])

    def test_expandable_text_hides_toggle_for_short_content(self) -> None:
        from qt_app.widgets import ExpandableText

        text = ExpandableText("Short detail", expand_text="More", collapse_text="Less")
        text.resize(320, 60)
        text.show()
        self.app.processEvents()

        self.assertFalse(text.toggle_button.isVisible())
        self.assertFalse(text.expanded)
        text.close()

    def test_settings_dialog_returns_all_current_fields(self) -> None:
        from line_tracker_settings import UISettings
        from line_tracker_theme import get_theme_palette
        from qt_app.settings_dialog import SettingsDialog
        from qt_app.theme import build_stylesheet, build_theme_tokens

        parent = QWidget()
        tokens = build_theme_tokens(get_theme_palette("forest"))
        parent.setStyleSheet(build_stylesheet(tokens))
        translate = lambda key, **kwargs: key.format(**kwargs)
        dialog = SettingsDialog(
            parent,
            translate=translate,
            settings=UISettings(repo_path="C:/repo", goal=50000, author="auto"),
            tokens=tokens,
            author_options=["auto", "all"],
            author_filter_map={"auto": "auto", "all": ""},
            author_display="auto",
        )
        values = dialog.values()
        self.assertEqual(values.repo_path, "C:/repo")
        self.assertEqual(values.goal, 50000)
        self.assertEqual(values.author_raw, "auto")
        self.assertEqual(values.graph_languages, ("C++",))
        self.assertEqual(dialog.tabs.count(), 5)
        self.assertFalse(dialog.restart_requested)

        dialog.restart_button.click()

        self.assertTrue(dialog.restart_requested)
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)

    def test_restart_reuses_current_source_or_executable_arguments(self) -> None:
        import qt_app.main as qt_main

        source_argv = ["app/line_tracker_ui.pyw", "--repo", "C:/repo"]
        with (
            patch.object(qt_main.sys, "argv", source_argv),
            patch.object(qt_main.sys, "executable", "C:/Python/pythonw.exe"),
            patch.object(qt_main.sys, "frozen", False, create=True),
            patch.object(qt_main.QProcess, "startDetached", return_value=(True, 123)) as start,
        ):
            self.assertTrue(qt_main._restart_current_process())
        start.assert_called_once_with(
            "C:/Python/pythonw.exe",
            [str(Path(source_argv[0]).resolve()), "--repo", "C:/repo"],
            str(Path.cwd()),
        )

        with (
            patch.object(qt_main.sys, "argv", ["C:/LineTracker.exe", "--repo", "C:/repo"]),
            patch.object(qt_main.sys, "executable", "C:/LineTracker.exe"),
            patch.object(qt_main.sys, "frozen", True, create=True),
            patch.object(qt_main.QProcess, "startDetached", return_value=(True, 456)) as start,
        ):
            self.assertTrue(qt_main._restart_current_process())
        start.assert_called_once_with(
            "C:/LineTracker.exe",
            ["--repo", "C:/repo"],
            str(Path.cwd()),
        )

    def test_branch_selection_defaults_to_current_and_supports_multiple_refs(self) -> None:
        from line_tracker_settings import UISettings
        from line_tracker_theme import get_theme_palette
        from qt_app.settings_dialog import SettingsDialog
        from qt_app.theme import build_theme_tokens

        parent = QWidget()
        dialog = SettingsDialog(
            parent,
            translate=lambda key, **kwargs: key.format(**kwargs),
            settings=UISettings(),
            tokens=build_theme_tokens(get_theme_palette("forest")),
            author_options=["auto"],
            author_filter_map={"auto": "auto"},
            author_display="auto",
            branch_options=("main", "feature/a"),
            current_branch="main",
        )
        self.assertTrue(dialog.branch_checks["main"].isChecked())
        self.assertEqual(dialog.values().selected_branches, ())
        dialog.branch_checks["feature/a"].setChecked(True)
        self.assertEqual(dialog.values().selected_branches, ("main", "feature/a"))
        dialog.close()

    def test_graph_display_settings_redraw_without_refreshing_repository(self) -> None:
        from dataclasses import replace

        from line_tracker_args import make_ui_parser
        from qt_app.main_window import LineTrackerQtWindow
        from qt_app.settings_dialog import SettingsValues

        args = make_ui_parser().parse_args(["--repo", str(Path.cwd())])
        window = LineTrackerQtWindow(args, capture_mode=True)
        window.repo = Path.cwd().resolve()
        window.repo_selected = True
        window.settings = replace(
            window.settings,
            repo_path=str(window.repo),
            author=window.author_raw,
            author_display="auto",
        )
        snapshot = Mock()
        window.last_snapshot = snapshot
        values = SettingsValues(
            lang=window.settings.lang,
            theme=window.settings.theme,
            repo_path=window.settings.repo_path,
            custom_today_enabled=bool(window.settings.custom_today_enabled),
            custom_today=window.settings.custom_today,
            goal=window.goal,
            author_raw=window.author_raw,
            author_display="auto",
            auto_refresh=bool(window.settings.auto_refresh),
            graph_days="30" if window.settings.graph_days != "30" else "60",
            graph_show_additions=bool(window.settings.graph_show_additions),
            graph_show_deletions=bool(window.settings.graph_show_deletions),
            graph_show_commits=bool(window.settings.graph_show_commits),
            graph_languages=("C++", "Python"),
            graph_curve=70.0,
            schedule_path=window.settings.schedule_path,
            selected_branches=window.settings.selected_branches,
        )
        dialog = Mock()
        dialog.tabs = Mock()
        dialog.tabs.count.return_value = 5
        dialog.exec.return_value = QDialog.DialogCode.Accepted
        dialog.values.return_value = values

        with (
            patch("qt_app.main_window.SettingsDialog", return_value=dialog),
            patch("qt_app.main_window.resolve_valid_repo", return_value=window.repo),
            patch.object(
                window,
                "_build_author_options",
                return_value=(["auto"], {"auto": "auto"}, {}),
            ),
            patch.object(window, "_render_graph") as render_graph,
            patch.object(window, "refresh") as refresh,
            patch.object(window, "_rebuild_ui") as rebuild_ui,
            patch.object(window, "_save_settings", return_value=True) as save_settings,
            patch.object(window.refresh_coordinator, "invalidate") as invalidate,
        ):
            window.open_settings(3)

        save_settings.assert_called_once()
        render_graph.assert_called_once_with(snapshot)
        refresh.assert_not_called()
        rebuild_ui.assert_not_called()
        invalidate.assert_not_called()
        window.close()

    def test_commit_history_rows_keep_readable_scroll_height(self) -> None:
        from line_tracker import CommitChangeEntry
        from qt_app.history_view import CommitHistoryView
        from qt_app.theme import LIST_ROW_MIN_HEIGHT

        view = CommitHistoryView(lambda key, **kwargs: key.format(**kwargs))
        view.resize(380, 220)
        view.show()
        entries = [
            CommitChangeEntry(
                commit_hash=f"hash-{index}",
                short_hash=f"h{index:06d}",
                date=dt.date(2026, 8, 4),
                subject=f"Commit {index} with a deliberately long subject that must be elided",
                insertions=index + 1,
                deletions=index,
            )
            for index in range(20)
        ]
        view.append_entries(entries, exhausted=True)
        self.app.processEvents()

        rows = [child for child in view.findChildren(QFrame) if child.objectName() == "HistoryRow"]
        self.assertEqual(len(rows), len(entries))
        self.assertTrue(all(row.minimumHeight() >= LIST_ROW_MIN_HEIGHT for row in rows))
        first_row = rows[0]
        added = next(label for label in first_row.findChildren(QLabel) if label.objectName() == "DeltaAdd")
        removed = next(label for label in first_row.findChildren(QLabel) if label.objectName() == "DeltaRemove")
        self.assertLessEqual(added.geometry().right(), first_row.width())
        self.assertLessEqual(removed.geometry().right(), first_row.width())
        activated: list[str] = []
        view.entry_activated.connect(lambda entry: activated.append(entry.commit_hash))
        QTest.mouseClick(first_row, Qt.MouseButton.LeftButton, pos=first_row.rect().center())
        self.assertEqual(activated, ["hash-0"])
        self.assertGreater(view.scroll.verticalScrollBar().maximum(), 0)
        view.close()

    def test_commit_detail_dialog_renders_file_changes(self) -> None:
        from line_tracker import CommitChangeEntry, CommitDetail, CommitFileChange
        from line_tracker_theme import get_theme_palette
        from qt_app.commit_detail_dialog import CommitDetailDialog
        from qt_app.theme import build_stylesheet, build_theme_tokens

        tokens = build_theme_tokens(get_theme_palette("forest"))
        parent = QWidget()
        parent.setStyleSheet(build_stylesheet(tokens))
        entry = CommitChangeEntry("fullhash", "abc1234", dt.date(2026, 8, 4), "Subject", 12, 3)
        dialog = CommitDetailDialog(
            parent,
            repo=Path("C:/repo"),
            entry=entry,
            translate=lambda key, **kwargs: key.format(**kwargs),
            tokens=tokens,
        )
        detail = CommitDetail(
            commit_hash="fullhash",
            short_hash="abc1234",
            authored_at=dt.datetime(2026, 8, 4, 21, 30, tzinfo=dt.timezone.utc),
            author_name="Groun",
            author_email="groun@example.com",
            subject="Subject",
            body="Body",
            files=(
                CommitFileChange("app/main.py", 12, 3),
                CommitFileChange("assets/icon.png", None, None),
            ),
        )

        dialog._show_detail(detail)

        rows = [child for child in dialog.findChildren(QFrame) if child.objectName() == "CommitFileRow"]
        self.assertEqual(len(rows), 2)
        self.assertEqual(dialog.total_added.text(), "+12")
        self.assertEqual(dialog.total_removed.text(), "-3")
        self.assertEqual(dialog.body.text(), "Body")
        dialog.close()

    def test_card_hierarchy_uses_shared_layout_contract(self) -> None:
        from line_tracker_theme import get_theme_palette
        from qt_app.theme import (
            CARD_RADIUS,
            PANEL_PADDING,
            PANEL_RADIUS,
            STAT_CARD_MIN_HEIGHT,
            build_stylesheet,
            build_theme_tokens,
        )
        from qt_app.widgets import StatCard

        card = StatCard("#ffffff")
        self.assertEqual(card.minimumHeight(), STAT_CARD_MIN_HEIGHT)

        stylesheet = build_stylesheet(build_theme_tokens(get_theme_palette("forest")))
        self.assertIn(f"border-radius: {PANEL_RADIUS}px", stylesheet)
        self.assertIn(f"border-radius: {CARD_RADIUS}px", stylesheet)
        self.assertIn("QFrame#HistoryRow", stylesheet)
        self.assertIn("border-bottom:", stylesheet)
        self.assertGreater(PANEL_PADDING, 0)

    def test_compact_overlay_variants_keep_fixed_contracts(self) -> None:
        from line_tracker_theme import get_theme_palette
        from qt_app.overlay import CompactOverlay
        from qt_app.theme import build_theme_tokens

        overlay = CompactOverlay(
            translate=lambda key, **kwargs: key.format(**kwargs),
            tokens=build_theme_tokens(get_theme_palette("forest")),
            variant="card",
            alpha=0.88,
        )
        self.assertEqual((overlay.width(), overlay.height()), (360, 176))
        overlay.set_variant("strip")
        self.assertEqual((overlay.width(), overlay.height()), (440, 44))
        self.assertEqual(overlay.strip_alpha.orientation(), Qt.Orientation.Vertical)
        overlay.close()

    def test_minimum_window_keeps_header_progress_and_workspace_visible(self) -> None:
        from line_tracker_args import make_ui_parser
        from line_tracker_presenters import StatCardPresentation, StatSectionPresentation
        from qt_app.main_window import LineTrackerQtWindow

        args = make_ui_parser().parse_args(["--repo", str(Path.cwd())])
        window = LineTrackerQtWindow(args, capture_mode=True)
        window.resize(860, 520)
        window.show()
        self.app.processEvents()

        self.assertTrue(window.project_title.isVisible())
        self.assertTrue(window.progress_panel.isVisible())
        self.assertTrue(window.graph_panel.isVisible())
        self.assertTrue(window.history_view.isVisible())
        self.assertTrue(window.workspace_tabs.isVisible())
        window._render_branch_stats(tuple(
            StatSectionPresentation(
                title=f"feature/{index}",
                added="+1",
                removed="-0",
                commits="1 commit",
                cards=(StatCardPresentation("Added", "1"), StatCardPresentation("Days", "1")),
            )
            for index in range(5)
        ))
        window.stats_tab_buttons["branch"].click()
        self.app.processEvents()
        self.assertTrue(window.branch_group.isVisible())
        self.assertFalse(window.overall_section.isVisible())
        self.assertEqual(len(window.branch_sections), 5)
        self.assertGreater(window.stats_scroll.verticalScrollBar().maximum(), 0)
        window.stats_tab_buttons["user"].click()
        self.app.processEvents()
        self.assertTrue(window.user_section.isVisible())
        self.assertFalse(window.branch_group.isVisible())
        self.assertTrue(window.progress_panel.isVisible())
        self.assertEqual(window.workspace_tabs.count(), 2)

        stats_right = window.stats_column.mapTo(window, QPoint(window.stats_column.width(), 0)).x()
        center_left = window.center_column.mapTo(window, QPoint(0, 0)).x()
        center_right = window.center_column.mapTo(window, QPoint(window.center_column.width(), 0)).x()
        workspace_left = window.workspace_tabs.mapTo(window, QPoint(0, 0)).x()
        scroll_bottom = window.stats_scroll.mapTo(window, QPoint(0, window.stats_scroll.height())).y()
        progress_top = window.progress_panel.mapTo(window, QPoint(0, 0)).y()
        graph_bottom = window.graph_panel.mapTo(window, QPoint(0, window.graph_panel.height())).y()
        history_top = window.history_view.mapTo(window, QPoint(0, 0)).y()
        self.assertLessEqual(stats_right, center_left)
        self.assertLessEqual(center_right, workspace_left)
        self.assertLessEqual(scroll_bottom, progress_top)
        self.assertLessEqual(graph_bottom, history_top)

        window.workspace_tabs.setCurrentIndex(1)
        self.app.processEvents()
        self.assertTrue(window.activity_graph.isVisible())
        self.assertTrue(window.history_view.isVisible())
        window.close()

    def test_window_construction_does_not_spawn_git_queries(self) -> None:
        from line_tracker_args import make_ui_parser
        from qt_app.main_window import LineTrackerQtWindow

        args = make_ui_parser().parse_args(["--repo", str(Path.cwd())])
        with (
            patch("qt_app.main_window.resolve_valid_repo") as resolve_repo,
            patch("qt_app.main_window.resolve_author") as resolve_author,
            patch("qt_app.main_window.resolve_ref") as resolve_ref,
            patch("qt_app.main_window.resolve_current_ref") as resolve_current_ref,
        ):
            window = LineTrackerQtWindow(args, capture_mode=True)
            resolve_repo.assert_not_called()
            resolve_author.assert_not_called()
            resolve_ref.assert_not_called()
            resolve_current_ref.assert_not_called()
            window.close()

    def test_saved_window_height_is_expanded_once(self) -> None:
        from PySide6.QtGui import QGuiApplication
        from line_tracker_settings import UISettings
        from qt_app.main_window import (
            WINDOW_GEOMETRY_REVISION,
            WINDOW_MIN_HEIGHT,
            LineTrackerQtWindow,
        )

        subject = Mock()
        subject.settings = UISettings(geometry="1200x675+64+223")
        subject.resize = Mock()
        subject.move = Mock()
        expected_width = min(1200, QGuiApplication.primaryScreen().availableGeometry().width())
        subject.width.return_value = expected_width
        subject.height.return_value = min(
            max(900, WINDOW_MIN_HEIGHT), QGuiApplication.primaryScreen().availableGeometry().height()
        )

        LineTrackerQtWindow._restore_window_geometry(subject)

        screen = QGuiApplication.primaryScreen().availableGeometry()
        expected_height = min(max(900, WINDOW_MIN_HEIGHT), screen.height())
        subject.resize.assert_called_once_with(expected_width, expected_height)
        self.assertEqual(subject.settings.geometry_revision, WINDOW_GEOMETRY_REVISION)

        subject.settings = UISettings(
            geometry="1200x900+64+100",
            geometry_revision=WINDOW_GEOMETRY_REVISION,
        )
        subject.resize.reset_mock()
        subject.height.return_value = min(900, screen.height())
        LineTrackerQtWindow._restore_window_geometry(subject)
        subject.resize.assert_called_once_with(expected_width, min(900, screen.height()))

    def test_user_stats_title_uses_selected_identity(self) -> None:
        from line_tracker_settings import UISettings
        from qt_app.main_window import LineTrackerQtWindow

        subject = Mock()
        subject.repo = Path.cwd()
        subject.t = lambda key: {"stats_all_users": "All users", "author_auto": "Auto"}[key]

        subject.author_raw = ""
        self.assertEqual(LineTrackerQtWindow._user_stats_title(subject), "All users")

        subject.author_raw = "auto"
        with patch("qt_app.main_window.run_git", return_value="Alice\n"):
            self.assertEqual(LineTrackerQtWindow._user_stats_title(subject), "Alice")
        with patch("qt_app.main_window.run_git", side_effect=RuntimeError("missing")):
            self.assertEqual(LineTrackerQtWindow._user_stats_title(subject), "Auto")

        subject.author_raw = "alice@example.com"
        subject.settings = UISettings(author_display="Alice <alice@example.com>")
        self.assertEqual(LineTrackerQtWindow._user_stats_title(subject), "Alice")

    def test_settings_save_failure_is_reported(self) -> None:
        from line_tracker_settings import UISettings
        from qt_app.main_window import LineTrackerQtWindow

        subject = Mock()
        subject.capture_mode = False
        subject.settings = UISettings()
        subject.repo = Path.cwd()
        subject.repo_selected = True
        subject.lang = "ko"
        subject.theme_name = "forest"
        subject.goal = 100
        subject.settings_path = Path("C:/unwritable/settings.json")
        subject.width.return_value = 1200
        subject.height.return_value = 800
        subject.x.return_value = 10
        subject.y.return_value = 20
        subject.t.side_effect = lambda key, **kwargs: key.format(**kwargs)

        with (
            patch("qt_app.main_window.save_ui_settings", return_value=False),
            patch("qt_app.main_window.QMessageBox.warning") as warning,
        ):
            saved = LineTrackerQtWindow._save_settings(subject, notify=True)

        self.assertFalse(saved)
        warning.assert_called_once()
        self.assertEqual(subject.settings, UISettings())

    def test_repository_selection_does_not_apply_when_settings_save_fails(self) -> None:
        from line_tracker_args import make_ui_parser
        from qt_app.main_window import LineTrackerQtWindow

        args = make_ui_parser().parse_args(["--repo", str(Path.cwd())])
        window = LineTrackerQtWindow(args, capture_mode=True)
        original_repo = window.repo
        selected_repo = original_repo.parent

        with (
            patch(
                "qt_app.main_window.QFileDialog.getExistingDirectory",
                return_value=str(selected_repo),
            ),
            patch("qt_app.main_window.resolve_valid_repo", return_value=selected_repo),
            patch.object(window, "_save_settings", return_value=False),
            patch.object(window, "refresh") as refresh,
        ):
            window.choose_repository()

        self.assertEqual(window.repo, original_repo)
        refresh.assert_not_called()
        window.close()

    def test_first_run_startup_waits_for_repository_selection(self) -> None:
        from line_tracker_args import make_ui_parser
        from line_tracker_settings import UISettings
        from qt_app.startup_window import StartupWindow

        args = make_ui_parser().parse_args([])
        window = StartupWindow(args, settings_override=UISettings(repo_path=""))

        self.assertIsNone(window.repo)
        self.assertFalse(window._loading)
        self.assertFalse(window.select_button.isHidden())
        self.assertTrue(window.progress.isHidden())
        window.close()

    def test_startup_failure_keeps_path_change_and_retry_available(self) -> None:
        from line_tracker_args import make_ui_parser
        from line_tracker_settings import UISettings
        from qt_app.startup_window import StartupWindow

        args = make_ui_parser().parse_args([])
        window = StartupWindow(args, settings_override=UISettings(repo_path=""))
        window._generation = 1
        window._loading = True

        window._on_failed(1, "git failed")

        self.assertFalse(window._loading)
        self.assertTrue(window.select_button.isEnabled())
        self.assertFalse(window.retry_button.isHidden())
        self.assertIn("git failed", window.status.text())
        window.close()

    def test_preloaded_main_window_does_not_start_initial_refresh(self) -> None:
        from line_tracker_args import make_ui_parser
        from line_tracker_settings import UISettings
        from qt_app.main_window import LineTrackerQtWindow

        payload = Mock()
        payload.repo = Path.cwd()
        payload.settings = UISettings(repo_path=str(Path.cwd()))
        payload.snapshot.author = "resolved-author"
        args = make_ui_parser().parse_args(["--repo", str(Path.cwd())])

        with patch.object(LineTrackerQtWindow, "_apply_startup_payload") as apply_payload:
            window = LineTrackerQtWindow(args, capture_mode=True, startup_payload=payload)

        apply_payload.assert_called_once_with(payload)
        self.assertFalse(window.initial_refresh_timer.isActive())
        self.assertFalse(window.initial_schedule_timer.isActive())
        window.close()


if __name__ == "__main__":
    unittest.main()
