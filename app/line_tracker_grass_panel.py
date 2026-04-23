from __future__ import annotations

import datetime as dt
import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk
from typing import Callable

from line_tracker_theme import ThemePalette


GRASS_SPLIT_ROWS = 2
GRASS_CELL_SIZE = 15
GRASS_CELL_GAP = 5
GRASS_BAND_DAY_ROWS = 7
GRASS_BAND_GAP = 36
GRASS_OUTER_PAD_X = 18
GRASS_OUTER_PAD_Y = 16
GRASS_LABEL_WIDTH = 30
GRASS_MONTH_LABEL_HEIGHT = 18
GRASS_WEEKS_PER_ROW = 27
GRASS_PANEL_PAD_X = 8
GRASS_LEGEND_SWATCH = 12
GRASS_LEGEND_GAP_X = 10
GRASS_FIXED_LEVEL_BANDS = (
    (1, 99),
    (100, 299),
    (300, 699),
    (700, None),
)
GRASS_UNCOMMITTED_LEVEL_COLORS = (
    "#a9c3ff",
    "#7ea6ff",
    "#4d86f0",
    "#2f63cf",
)
GRASS_CANVAS_WIDTH = (
    (GRASS_OUTER_PAD_X * 2)
    + GRASS_LABEL_WIDTH
    + (GRASS_WEEKS_PER_ROW * GRASS_CELL_SIZE)
    + ((GRASS_WEEKS_PER_ROW - 1) * GRASS_CELL_GAP)
)
GRASS_CANVAS_HEIGHT = (
    (GRASS_OUTER_PAD_Y * 2)
    + (GRASS_MONTH_LABEL_HEIGHT * GRASS_SPLIT_ROWS)
    + (
        (
            (GRASS_BAND_DAY_ROWS * GRASS_CELL_SIZE)
            + ((GRASS_BAND_DAY_ROWS - 1) * GRASS_CELL_GAP)
        )
        * GRASS_SPLIT_ROWS
    )
    + GRASS_BAND_GAP
)


@dataclass(frozen=True)
class GrassPanelBindings:
    translate: Callable[[str], str]
    get_theme: Callable[[], ThemePalette]
    format_month_label: Callable[[int], str]


class GrassPanel:
    def __init__(self, bindings: GrassPanelBindings) -> None:
        self.bindings = bindings
        self.points: list[tuple[dt.date, int]] = []
        self.highlight_day: dt.date | None = None
        self.uncommitted_today = 0
        self.layout_scale = 1.0

    def t(self, key: str, **kwargs) -> str:
        text = self.bindings.translate(key)
        try:
            return text.format(**kwargs)
        except (KeyError, ValueError):
            return text

    def theme(self) -> ThemePalette:
        return self.bindings.get_theme()

    def _metrics(self) -> dict[str, int]:
        scale = min(max(self.layout_scale, 0.55), 1.0)
        cell_size = max(10, round(GRASS_CELL_SIZE * scale))
        cell_gap = max(2, round(GRASS_CELL_GAP * scale))
        outer_pad_x = max(12, round(GRASS_OUTER_PAD_X * scale))
        outer_pad_y = max(10, round(GRASS_OUTER_PAD_Y * scale))
        label_width = max(24, round(GRASS_LABEL_WIDTH * scale))
        month_label_height = max(14, round(GRASS_MONTH_LABEL_HEIGHT * scale))
        band_gap = max(22, round(GRASS_BAND_GAP * scale))
        panel_pad_x = max(6, round(GRASS_PANEL_PAD_X * scale))
        legend_swatch = max(10, round(GRASS_LEGEND_SWATCH * scale))
        legend_gap_x = max(6, round(GRASS_LEGEND_GAP_X * scale))
        label_font = max(8, round(9 * scale))
        empty_font = max(9, round(10 * scale))
        width = (
            (outer_pad_x * 2)
            + label_width
            + (GRASS_WEEKS_PER_ROW * cell_size)
            + ((GRASS_WEEKS_PER_ROW - 1) * cell_gap)
        )
        band_height = (GRASS_BAND_DAY_ROWS * cell_size) + ((GRASS_BAND_DAY_ROWS - 1) * cell_gap)
        height = (
            (outer_pad_y * 2)
            + (month_label_height * GRASS_SPLIT_ROWS)
            + (band_height * GRASS_SPLIT_ROWS)
            + band_gap
        )
        return {
            "cell_size": cell_size,
            "cell_gap": cell_gap,
            "outer_pad_x": outer_pad_x,
            "outer_pad_y": outer_pad_y,
            "label_width": label_width,
            "month_label_height": month_label_height,
            "band_gap": band_gap,
            "panel_pad_x": panel_pad_x,
            "legend_swatch": legend_swatch,
            "legend_gap_x": legend_gap_x,
            "width": width,
            "height": height,
            "band_height": band_height,
            "label_font": label_font,
            "empty_font": empty_font,
        }

    def build(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(3, weight=1)
        metrics = self._metrics()
        self.legend_frame = ttk.Frame(parent, style="CardInner.TFrame")
        self.legend_frame.grid(row=0, column=0, sticky="w", padx=metrics["panel_pad_x"], pady=(4, 0))

        palette = self.theme()
        self.canvas = tk.Canvas(
            parent,
            width=metrics["width"],
            height=metrics["height"],
            bg=palette.card_bg,
            highlightthickness=1,
            highlightbackground=palette.border,
        )
        self.canvas.grid(row=1, column=0, sticky="w", padx=metrics["panel_pad_x"], pady=(10, 0))

        self.summary_var = tk.StringVar(value="")
        self.summary_label = ttk.Label(parent, textvariable=self.summary_var, style="CardLabel.TLabel")
        self.summary_label.grid(row=2, column=0, sticky="w", padx=metrics["panel_pad_x"], pady=(12, 10))

    def set_layout_scale(self, scale: float) -> None:
        self.layout_scale = min(max(float(scale), 0.55), 1.0)
        if hasattr(self, "canvas"):
            self.refresh()

    def apply_theme(self) -> None:
        if hasattr(self, "canvas"):
            palette = self.theme()
            self.canvas.configure(bg=palette.card_bg, highlightbackground=palette.border)
        self.refresh()

    def apply_language(self) -> None:
        self.refresh()

    def update(
        self,
        points: list[tuple[dt.date, int]],
        highlight_day: dt.date,
        uncommitted_today: int = 0,
    ) -> None:
        self.points = list(points)
        self.highlight_day = highlight_day
        self.uncommitted_today = max(0, int(uncommitted_today))
        self.refresh()

    def refresh(self) -> None:
        if not hasattr(self, "canvas"):
            return
        metrics = self._metrics()
        self.canvas.configure(width=metrics["width"], height=metrics["height"])
        self.legend_frame.grid_configure(padx=metrics["panel_pad_x"])
        self.summary_label.grid_configure(padx=metrics["panel_pad_x"])

        highlight_day = self.highlight_day or dt.date.today()
        uncommitted_today = self.uncommitted_today if highlight_day == dt.date.today() else 0
        values = [value for _, value in self.points]
        self._refresh_legend(uncommitted_today)
        self._draw_heatmap(self.points, highlight_day, uncommitted_today)

        if not values:
            self.summary_var.set(self.t("grass_empty"))
            return

        active_days = sum(1 for value in values if value > 0)
        total_lines = sum(values)
        avg_lines = (total_lines / active_days) if active_days else 0.0
        self.summary_var.set(
            self.t(
                "grass_summary",
                active=f"{active_days:,}",
                total=f"{total_lines:,}",
                avg=f"{avg_lines:.1f}",
            )
        )

    def _fixed_level_specs(self) -> list[tuple[str, int, int | None]]:
        palette = self.theme()
        colors = [
            palette.accent_light,
            palette.accent,
            palette.accent_dark,
            palette.accent_alt,
        ]
        return [
            (colors[index], start, end)
            for index, (start, end) in enumerate(GRASS_FIXED_LEVEL_BANDS)
        ]

    def _uncommitted_level_specs(self) -> list[tuple[str, int, int | None]]:
        return [
            (GRASS_UNCOMMITTED_LEVEL_COLORS[index], start, end)
            for index, (start, end) in enumerate(GRASS_FIXED_LEVEL_BANDS)
        ]

    def _format_legend_range(self, start: int, end: int | None) -> str:
        start_text = f"{start:,}"
        if end is None:
            return self.t("grass_legend_open", start=start_text)
        end_text = f"{end:,}"
        return self.t("grass_legend_range", start=start_text, end=end_text)

    def _legend_items(self, uncommitted_today: int) -> list[tuple[str, str]]:
        palette = self.theme()
        items: list[tuple[str, str]] = [(palette.graph_grid, self.t("grass_legend_zero"))]
        for color, start, end in self._fixed_level_specs():
            label = self._format_legend_range(start, end)
            items.append((color, label))
        if uncommitted_today > 0:
            items.append((self._today_marker_color(), self.t("grass_uncommitted_legend")))
        return items

    def _today_marker_color(self) -> str:
        palette = self.theme()
        return palette.danger if palette.grass_today_uses_danger else GRASS_UNCOMMITTED_LEVEL_COLORS[2]

    def _today_outline_color(self) -> str:
        palette = self.theme()
        return palette.danger if palette.grass_today_uses_danger else palette.text

    def _refresh_legend(self, uncommitted_today: int) -> None:
        if not hasattr(self, "legend_frame"):
            return
        metrics = self._metrics()

        for child in self.legend_frame.winfo_children():
            child.destroy()

        for column, (color, label_text) in enumerate(self._legend_items(uncommitted_today)):
            item_frame = ttk.Frame(self.legend_frame, style="CardInner.TFrame")
            item_frame.grid(row=0, column=column, sticky="w", padx=(0, metrics["legend_gap_x"]))

            swatch = tk.Frame(
                item_frame,
                width=metrics["legend_swatch"],
                height=metrics["legend_swatch"],
                bg=color,
                highlightthickness=1,
                highlightbackground=self.theme().border,
            )
            swatch.grid(row=0, column=0, sticky="w")
            swatch.grid_propagate(False)

            label = ttk.Label(item_frame, text=label_text, style="CardLabel.TLabel")
            label.grid(row=0, column=1, sticky="w", padx=(5, 0))

    @staticmethod
    def _color_for_specs(value: int, specs: list[tuple[str, int, int | None]], default_color: str) -> str:
        if value <= 0:
            return default_color
        for color, start, end in specs:
            if end is None:
                if value >= start:
                    return color
                continue
            if start <= value <= end:
                return color
        return specs[-1][0] if specs else default_color

    def _level_color(self, value: int, *, uncommitted: bool = False) -> str:
        palette = self.theme()
        specs = self._uncommitted_level_specs() if uncommitted else self._fixed_level_specs()
        return self._color_for_specs(value, specs, palette.graph_grid)

    def _draw_heatmap(
        self,
        points: list[tuple[dt.date, int]],
        highlight_day: dt.date,
        uncommitted_today: int = 0,
    ) -> None:
        canvas = self.canvas
        palette = self.theme()
        canvas.delete("all")
        metrics = self._metrics()
        width = metrics["width"]
        height = metrics["height"]
        cell_size = metrics["cell_size"]
        pitch = metrics["cell_size"] + metrics["cell_gap"]
        band_height = metrics["band_height"]
        outer_pad_x = metrics["outer_pad_x"]
        outer_pad_y = metrics["outer_pad_y"]
        label_width = metrics["label_width"]
        month_label_height = metrics["month_label_height"]
        band_gap = metrics["band_gap"]
        label_font = ("Bahnschrift", metrics["label_font"])
        empty_font = ("Bahnschrift", metrics["empty_font"])

        if not points:
            canvas.create_text(
                width / 2,
                height / 2,
                text=self.t("grass_empty"),
                fill=palette.muted_text,
                font=empty_font,
            )
            return

        start_day = points[0][0]
        end_day = points[-1][0]
        grid_start = start_day - dt.timedelta(days=start_day.weekday())
        grid_end = end_day + dt.timedelta(days=(6 - end_day.weekday()))
        total_days = (grid_end - grid_start).days + 1
        column_count = max(1, ((total_days + 6) // 7))
        weeks_per_row = max(1, ((column_count + GRASS_SPLIT_ROWS - 1) // GRASS_SPLIT_ROWS))
        values_by_day = {day: value for day, value in points}
        actual_today = dt.date.today()
        effective_uncommitted = uncommitted_today if highlight_day == actual_today else 0
        committed_values_by_day = dict(values_by_day)
        if effective_uncommitted > 0 and highlight_day in committed_values_by_day:
            committed_values_by_day[highlight_day] = max(
                0,
                committed_values_by_day[highlight_day] - effective_uncommitted,
            )

        def band_month_y(band_index: int) -> int:
            return outer_pad_y + band_index * (band_height + month_label_height + band_gap)

        def band_grid_y(band_index: int) -> int:
            return band_month_y(band_index) + month_label_height

        for band_index in range(GRASS_SPLIT_ROWS):
            month_y = band_month_y(band_index)
            grid_y = band_grid_y(band_index)

            for label_text, row in (
                (self.t("grass_day_mon"), 0),
                (self.t("grass_day_wed"), 2),
                (self.t("grass_day_fri"), 4),
            ):
                label_y = grid_y + row * pitch + cell_size / 2
                canvas.create_text(
                    outer_pad_x,
                    label_y,
                    text=label_text,
                    anchor="w",
                    fill=palette.muted_text,
                    font=label_font,
                )

            previous_month: int | None = None
            for col_in_band in range(weeks_per_row):
                global_col = band_index * weeks_per_row + col_in_band
                if global_col >= column_count:
                    break
                visible_days = []
                for row in range(7):
                    cell_day = grid_start + dt.timedelta(days=global_col * 7 + row)
                    if start_day <= cell_day <= end_day:
                        visible_days.append(cell_day)
                if not visible_days:
                    continue
                month = visible_days[0].month
                if col_in_band == 0 or month != previous_month:
                    canvas.create_text(
                        outer_pad_x + label_width + col_in_band * pitch,
                        month_y,
                        text=self.bindings.format_month_label(month),
                        anchor="w",
                        fill=palette.muted_text,
                        font=label_font,
                    )
                    previous_month = month

        for day, value in points:
            offset = (day - grid_start).days
            global_col = offset // 7
            band_index = global_col // weeks_per_row
            col_in_band = global_col % weeks_per_row
            row = offset % 7
            x1 = outer_pad_x + label_width + col_in_band * pitch
            y1 = band_grid_y(band_index) + row * pitch
            x2 = x1 + cell_size
            y2 = y1 + cell_size
            is_today = day == highlight_day
            committed_value = committed_values_by_day.get(day, value)
            fill_color = self._level_color(committed_value)
            if is_today and effective_uncommitted > 0:
                fill_color = (
                    self._today_marker_color()
                    if palette.grass_today_uses_danger
                    else self._level_color(effective_uncommitted, uncommitted=True)
                )
            canvas.create_rectangle(
                x1,
                y1,
                x2,
                y2,
                fill=fill_color,
                outline=self._today_outline_color() if is_today else "",
                width=1 if is_today else 0,
            )
