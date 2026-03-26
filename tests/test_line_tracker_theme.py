from __future__ import annotations

import unittest

from line_tracker_theme import (
    DEFAULT_THEME_NAME,
    THEME_PALETTES,
    get_theme_names,
    get_theme_palette,
    resolve_theme_name,
)


class ThemePaletteTests(unittest.TestCase):
    def test_unknown_palette_name_falls_back_to_default(self) -> None:
        self.assertIs(get_theme_palette("missing"), THEME_PALETTES[DEFAULT_THEME_NAME])
        self.assertEqual(resolve_theme_name("missing"), DEFAULT_THEME_NAME)

    def test_default_palette_exposes_tile_accent_sequence(self) -> None:
        palette = get_theme_palette()
        self.assertEqual(
            palette.tile_accents,
            (
                palette.accent_alt,
                palette.accent,
                palette.accent_light,
                palette.accent_dark,
                palette.accent_alt_dark,
            ),
        )

    def test_theme_names_expose_all_registered_palettes(self) -> None:
        self.assertEqual(get_theme_names(), tuple(THEME_PALETTES.keys()))

    def test_blue_family_themes_use_danger_for_grass_today_marker(self) -> None:
        for theme_name in ("slate", "dark", "vs", "neon", "discord", "cyberpunk"):
            self.assertTrue(get_theme_palette(theme_name).grass_today_uses_danger)
        for theme_name in (DEFAULT_THEME_NAME, "cream", "cherry", "mc"):
            self.assertFalse(get_theme_palette(theme_name).grass_today_uses_danger)


if __name__ == "__main__":
    unittest.main()
