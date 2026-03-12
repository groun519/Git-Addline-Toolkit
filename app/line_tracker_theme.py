from __future__ import annotations

from dataclasses import dataclass


DEFAULT_THEME_NAME = "forest"


@dataclass(frozen=True)
class ThemePalette:
    app_bg: str
    card_bg: str
    border: str
    text: str
    muted_text: str
    accent: str
    accent_dark: str
    accent_light: str
    accent_alt: str
    accent_alt_dark: str
    success: str
    danger: str
    canvas_bg: str
    graph_grid: str
    button_text: str = "#ffffff"
    button_disabled_text: str = "#f0f0f0"
    overall_progress_trough: str = "#27302b"
    daily_progress_trough: str = "#2b2620"

    @property
    def tile_accents(self) -> tuple[str, ...]:
        return (
            self.accent_alt,
            self.accent,
            self.accent_light,
            self.accent_dark,
            self.accent_alt_dark,
        )


THEME_PALETTES: dict[str, ThemePalette] = {
    DEFAULT_THEME_NAME: ThemePalette(
        app_bg="#151a18",
        card_bg="#1f2522",
        border="#2e3833",
        text="#e8ebe7",
        muted_text="#b0b8b2",
        accent="#6bb29a",
        accent_dark="#5aa18a",
        accent_light="#8cc7b3",
        accent_alt="#d4a261",
        accent_alt_dark="#c69254",
        success="#76c7a1",
        danger="#d36f6f",
        canvas_bg="#1a201d",
        graph_grid="#2a322e",
    ),
    "cream": ThemePalette(
        app_bg="#f3efe4",
        card_bg="#fffaf1",
        border="#d6c8b3",
        text="#2b241c",
        muted_text="#6c5f52",
        accent="#2f7d67",
        accent_dark="#286b57",
        accent_light="#74a896",
        accent_alt="#c7772d",
        accent_alt_dark="#aa631f",
        success="#3f8f69",
        danger="#c45d4c",
        canvas_bg="#efe7d8",
        graph_grid="#d8ccb8",
        button_text="#fffaf1",
        button_disabled_text="#efe7d8",
        overall_progress_trough="#d8d0c3",
        daily_progress_trough="#ddd2c2",
    ),
    "slate": ThemePalette(
        app_bg="#141923",
        card_bg="#1d2431",
        border="#313c4f",
        text="#e7edf7",
        muted_text="#adb7c8",
        accent="#6d9ee8",
        accent_dark="#5a87c8",
        accent_light="#8eb2ef",
        accent_alt="#e2a84a",
        accent_alt_dark="#c78e35",
        success="#73c3a4",
        danger="#df7a7a",
        canvas_bg="#171e29",
        graph_grid="#273244",
    ),
}


def get_theme_names() -> tuple[str, ...]:
    return tuple(THEME_PALETTES.keys())


def resolve_theme_name(name: str) -> str:
    cleaned = name.strip()
    return cleaned if cleaned in THEME_PALETTES else DEFAULT_THEME_NAME


def get_theme_palette(name: str = DEFAULT_THEME_NAME) -> ThemePalette:
    return THEME_PALETTES[resolve_theme_name(name)]
