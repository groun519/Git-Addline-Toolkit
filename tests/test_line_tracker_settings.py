import json
import tempfile
import unittest
from pathlib import Path
import sys

APP_DIR = Path(__file__).resolve().parents[1] / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

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


class SettingsTests(unittest.TestCase):
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

    def test_ui_settings_from_dict_preserves_defaults_and_legacy_fields(self) -> None:
        settings = UISettings.from_dict(
            {
                "repo_path": "C:/repo",
                "lang": "en",
                "theme": "slate",
                "goal": 123,
                "note_title": "legacy title",
                "note_done": "done line",
                "note_todo": "todo line",
            }
        )

        self.assertEqual(settings.repo_path, "C:/repo")
        self.assertEqual(settings.lang, "en")
        self.assertEqual(settings.theme, "slate")
        self.assertEqual(settings.goal, 123)
        self.assertEqual(settings.legacy_note_title, "legacy title")
        self.assertEqual(settings.legacy_note_done, "done line")
        self.assertEqual(settings.legacy_note_todo, "todo line")
        self.assertEqual(settings.graph_days, "14")

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
            memo_text="Title",
            legacy_note_title="unused",
        )

        self.assertEqual(
            settings.to_dict(),
            {
                "goal": 100,
                "custom_today_enabled": True,
                "custom_today": "2026-03-12",
                "graph_days": "30",
                "auto_refresh": False,
                "author": "me",
                "author_display": "Auto",
                "memo_text": "Title",
                "repo_path": "C:/repo",
                "lang": "ko",
                "theme": "cream",
                "geometry": "1200x700+10+20",
            },
        )

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
