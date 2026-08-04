from __future__ import annotations

import datetime as dt
import os
import unittest
from pathlib import Path


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtWidgets import QApplication, QFrame, QWidget
except ImportError:
    QApplication = None


@unittest.skipIf(QApplication is None, "PySide6 is not installed")
class QtApplicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_runtime_icons_render(self) -> None:
        from qt_app.icons import make_icon

        for name in ("settings", "refresh", "file", "folder", "overlay", "history"):
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

    def test_schedule_view_renders_directive_document(self) -> None:
        from line_tracker_schedule import ScheduleDocument, ScheduleItem
        from line_tracker_theme import get_theme_palette
        from qt_app.schedule_view import ScheduleView
        from qt_app.theme import build_theme_tokens

        translate = lambda key, **kwargs: key.format(**kwargs)
        view = ScheduleView(translate)
        view.set_theme_tokens(build_theme_tokens(get_theme_palette("forest")))
        document = ScheduleDocument(
            title="Work Plan",
            items=(ScheduleItem("ITEM-1", "Inventory", date=dt.date(2026, 8, 4)),),
            source_path=Path("work-plan.md"),
        )
        view.show_document(document, dt.date(2026, 8, 4))
        self.assertEqual(view.title_label.text(), "Work Plan")
        self.assertTrue(view.summary.isVisibleTo(view))
        self.assertGreater(view.list_layout.count(), 1)

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
        self.assertEqual(dialog.tabs.count(), 5)

    def test_commit_history_rows_keep_readable_scroll_height(self) -> None:
        from line_tracker import CommitChangeEntry
        from qt_app.history_view import CommitHistoryView

        view = CommitHistoryView(lambda key, **kwargs: key.format(**kwargs))
        view.resize(380, 220)
        view.show()
        entries = [
            CommitChangeEntry(
                commit_hash=f"hash-{index}",
                short_hash=f"h{index:06d}",
                date=dt.date(2026, 8, 4),
                subject=f"Commit {index}",
                insertions=index + 1,
                deletions=index,
            )
            for index in range(20)
        ]
        view.append_entries(entries, exhausted=True)
        self.app.processEvents()

        rows = [child for child in view.findChildren(QFrame) if child.objectName() == "HistoryRow"]
        self.assertEqual(len(rows), len(entries))
        self.assertTrue(all(row.minimumHeight() >= 30 for row in rows))
        self.assertGreater(view.scroll.verticalScrollBar().maximum(), 0)
        view.close()

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
        self.assertGreater(window.stats_scroll.verticalScrollBar().maximum(), 0)
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


if __name__ == "__main__":
    unittest.main()
