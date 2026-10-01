import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
import sys
from unittest.mock import Mock, patch

APP_DIR = Path(__file__).resolve().parents[1] / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from line_tracker import encode_author_patterns
from line_tracker_settings import classify_settings_change
from line_tracker_ui import LineTrackerApp, UISettings


class _FakeRoot:
    def __init__(self, screen_width: int = 1600) -> None:
        self._screen_width = screen_width

    def winfo_screenwidth(self) -> int:
        return self._screen_width


class _FakeGeometryApp:
    _parse_geometry = staticmethod(LineTrackerApp._parse_geometry)

    def __init__(self, screen_width: int = 1600) -> None:
        self.root = _FakeRoot(screen_width)


class _FakeSettingsApp:
    def __init__(self, settings_path: Path, legacy_settings_path: Path) -> None:
        self.settings_path = settings_path
        self.legacy_settings_path = legacy_settings_path


class _FakeScheduleLocationApp:
    def __init__(self, repo: Path, schedule_path: str) -> None:
        self.repo = repo
        self.schedule_path = schedule_path
        self.show_error = Mock()

    @staticmethod
    def t(key: str) -> str:
        return key


class SettingsTests(unittest.TestCase):
    def test_classify_settings_change_keeps_all_graph_controls_local(self) -> None:
        settings = UISettings(repo_path="C:/repo")

        self.assertEqual(
            classify_settings_change(settings, replace(settings, graph_curve=70.0)),
            "graph_render",
        )
        self.assertEqual(
            classify_settings_change(settings, replace(settings, graph_days="30")),
            "graph_render",
        )
        self.assertEqual(
            classify_settings_change(settings, replace(settings, theme="dark")),
            "application",
        )

    def test_open_schedule_location_opens_selected_file_parent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = Path(tmp_dir)
            schedule_path = repo / "docs" / "SCHEDULE.md"
            schedule_path.parent.mkdir()
            schedule_path.write_text("@@BACKLOG", encoding="utf-8")
            app = _FakeScheduleLocationApp(repo, "docs/SCHEDULE.md")

            with patch("line_tracker_ui.os.startfile") as open_location:
                LineTrackerApp.open_schedule_location(app)

        open_location.assert_called_once_with(str(schedule_path.parent))
        app.show_error.assert_not_called()

    def test_build_author_option_entries_deduplicates_same_email_targets(self) -> None:
        options, mapping, aliases = LineTrackerApp._build_author_option_entries(
            [
                "Alice <alice@example.com>",
                "Alice Kim <alice@example.com>",
                "Bob <bob@example.com>",
            ],
            "Auto",
            "All",
        )

        self.assertEqual(
            options,
            ["Auto", "All", "Alice <alice@example.com>", "Bob <bob@example.com>"],
        )
        self.assertEqual(mapping["Alice <alice@example.com>"], "alice@example\\.com")
        self.assertEqual(aliases["Alice\\ Kim\\ <alice@example\\.com>"], "Alice <alice@example.com>")

    def test_build_author_option_entries_merges_matching_github_noreply_and_primary_email(self) -> None:
        options, mapping, aliases = LineTrackerApp._build_author_option_entries(
            [
                "groun519 <54619610+groun519@users.noreply.github.com>",
                "groun519 <groun519@gmail.com>",
            ],
            "Auto",
            "All",
        )

        self.assertEqual(
            options,
            ["Auto", "All", "groun519 <groun519@gmail.com>"],
        )
        self.assertEqual(
            mapping["groun519 <groun519@gmail.com>"],
            encode_author_patterns(
                [
                    "54619610\\+groun519@users\\.noreply\\.github\\.com",
                    "groun519@gmail\\.com",
                ]
            ),
        )
        self.assertEqual(
            aliases["54619610\\+groun519@users\\.noreply\\.github\\.com"],
            "groun519 <groun519@gmail.com>",
        )

    def test_ui_settings_from_dict_preserves_defaults(self) -> None:
        settings = UISettings.from_dict(
            {
                "repo_path": "C:/repo",
                "lang": "en",
                "theme": "slate",
                "goal": 123,
                "compact_variant": "strip",
                "compact_alpha": 0.73,
            }
        )

        self.assertEqual(settings.repo_path, "C:/repo")
        self.assertEqual(settings.lang, "en")
        self.assertEqual(settings.theme, "slate")
        self.assertEqual(settings.goal, 123)
        self.assertEqual(settings.compact_variant, "strip")
        self.assertEqual(settings.compact_alpha, 0.73)
        self.assertEqual(settings.graph_days, "14")
        self.assertEqual(settings.graph_languages, ("C++",))
        self.assertEqual(settings.note_tab, "schedule")
        self.assertEqual(settings.schedule_path, "")

    def test_ui_settings_to_dict_only_writes_current_keys(self) -> None:
        settings = UISettings(
            repo_path="C:/repo",
            lang="ko",
            theme="cream",
            geometry="1200x700+10+20",
            goal=100,
            graph_days="30",
            author="me",
            author_display="Auto",
            custom_today_enabled=True,
            custom_today="2026-03-12",
            auto_refresh=False,
            compact_variant="strip",
            compact_alpha=0.73,
            note_tab="grass",
            schedule_path="docs/SCHEDULE.md",
        )

        self.assertEqual(
            settings.to_dict(),
            {
                "goal": 100,
                "custom_today_enabled": True,
                "custom_today": "2026-03-12",
                "graph_days": "30",
                "graph_show_additions": True,
                "graph_show_deletions": False,
                "graph_show_commits": False,
                "graph_languages": ["C++"],
                "graph_curve": 35.0,
                "auto_refresh": False,
                "author": "me",
                "author_display": "Auto",
                "compact_variant": "strip",
                "compact_alpha": 0.73,
                "note_tab": "grass",
                "schedule_path": "docs/SCHEDULE.md",
                "selected_branches": [],
                "repo_path": "C:/repo",
                "lang": "ko",
                "theme": "cream",
                "geometry": "1200x700+10+20",
                "geometry_revision": 0,
            },
        )

    def test_ui_settings_migrates_legacy_todo_tab_to_schedule(self) -> None:
        settings = UISettings.from_dict(
            {
                "note_tab": "todo",
                "todo_items": [
                    {"text": "First", "done": False, "created_at": "2026-06-04T15:40:00"},
                ],
            }
        )

        self.assertEqual(settings.note_tab, "schedule")
        self.assertNotIn("todo_items", settings.to_dict())

    def test_ui_settings_persists_unique_selected_branches(self) -> None:
        settings = UISettings.from_dict({"selected_branches": ["feature/a", "feature/b", "feature/a"]})
        self.assertEqual(settings.selected_branches, ("feature/a", "feature/b"))
        self.assertEqual(settings.to_dict()["selected_branches"], ["feature/a", "feature/b"])

    def test_ui_settings_accepts_schedule_tab_and_path(self) -> None:
        settings = UISettings.from_dict(
            {
                "note_tab": "schedule",
                "schedule_path": " docs/plan.md ",
            }
        )

        self.assertEqual(settings.note_tab, "schedule")
        self.assertEqual(settings.schedule_path, "docs/plan.md")

    def test_load_settings_falls_back_to_legacy_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            legacy_path = tmp_path / "legacy.json"
            legacy_path.write_text(json.dumps({"lang": "en", "repo_path": "C:/legacy"}), encoding="utf-8")

            app = _FakeSettingsApp(tmp_path / "current.json", legacy_path)
            settings = LineTrackerApp.load_settings(app)

        self.assertEqual(settings.lang, "en")
        self.assertEqual(settings.repo_path, "C:/legacy")

    def test_load_settings_returns_default_on_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            current_path = tmp_path / "current.json"
            current_path.write_text("{invalid", encoding="utf-8")

            app = _FakeSettingsApp(current_path, tmp_path / "legacy.json")
            settings = LineTrackerApp.load_settings(app)

        self.assertEqual(settings, UISettings())

    def test_normalize_geometry_clamps_and_strips_invalid_position(self) -> None:
        app = _FakeGeometryApp(screen_width=1600)

        normalized_small = LineTrackerApp.normalize_geometry(app, "1x1+0+0")
        normalized_wide = LineTrackerApp.normalize_geometry(app, "2000x700+10+20")

        self.assertEqual(normalized_small, "1100x675")
        self.assertEqual(normalized_wide, "1520x700+10+20")
