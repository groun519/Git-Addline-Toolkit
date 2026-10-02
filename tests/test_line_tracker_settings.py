import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
import sys

APP_DIR = Path(__file__).resolve().parents[1] / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from line_tracker import encode_author_patterns
from line_tracker_authors import build_author_option_entries
from line_tracker_settings import UISettings, classify_settings_change, load_ui_settings
from qt_app.window_state import parse_geometry


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

    def test_build_author_option_entries_deduplicates_same_email_targets(self) -> None:
        options, mapping, aliases = build_author_option_entries(
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
        options, mapping, aliases = build_author_option_entries(
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

            settings = load_ui_settings(tmp_path / "current.json", legacy_path)

        self.assertEqual(settings.lang, "en")
        self.assertEqual(settings.repo_path, "C:/legacy")

    def test_load_settings_returns_default_on_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            current_path = tmp_path / "current.json"
            current_path.write_text("{invalid", encoding="utf-8")

            settings = load_ui_settings(current_path, tmp_path / "legacy.json")

        self.assertEqual(settings, UISettings())

    def test_parse_geometry_preserves_valid_size_and_position(self) -> None:
        self.assertEqual(parse_geometry("1x1+0+0"), (1, 1, 0, 0))
        self.assertEqual(parse_geometry("2000x700+10+20"), (2000, 700, 10, 20))
        self.assertIsNone(parse_geometry("not-a-geometry"))
