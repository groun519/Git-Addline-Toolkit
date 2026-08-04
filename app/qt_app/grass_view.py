from __future__ import annotations

import datetime as dt

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from line_tracker_grass import GRASS_FIXED_LEVEL_BANDS, GRASS_UNCOMMITTED_LEVEL_COLORS
from qt_app.theme import QtThemeTokens


class GrassView(QWidget):
    def __init__(self, translate, format_month_label) -> None:
        super().__init__()
        self.t = translate
        self.tokens: QtThemeTokens | None = None
        self.points: list[tuple[dt.date, int]] = []
        self.highlight_day: dt.date | None = None
        self.uncommitted_today = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)
        self.legend = QHBoxLayout()
        self.legend.setSpacing(12)
        layout.addLayout(self.legend)
        self.heatmap = GrassHeatmap(translate, format_month_label)
        layout.addWidget(self.heatmap, 1)
        self.summary = QLabel(self.t("grass_empty"))
        self.summary.setObjectName("MutedLabel")
        layout.addWidget(self.summary)

    def set_theme_tokens(self, tokens: QtThemeTokens) -> None:
        self.tokens = tokens
        self.heatmap.set_theme_tokens(tokens)
        self._refresh_legend()

    def set_data(
        self,
        points: list[tuple[dt.date, int]],
        highlight_day: dt.date,
        uncommitted_today: int = 0,
    ) -> None:
        self.points = list(points)
        self.highlight_day = highlight_day
        self.uncommitted_today = max(0, int(uncommitted_today))
        self.heatmap.set_data(self.points, highlight_day, self.uncommitted_today)
        self._refresh_legend()
        values = [value for _, value in self.points]
        if not values:
            self.summary.setText(self.t("grass_empty"))
            return
        active = sum(value > 0 for value in values)
        total = sum(values)
        average = total / active if active else 0.0
        self.summary.setText(
            self.t("grass_summary", active=f"{active:,}", total=f"{total:,}", avg=f"{average:.1f}")
        )

    def _refresh_legend(self) -> None:
        while self.legend.count():
            item = self.legend.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        if self.tokens is None:
            return
        items = [(self.tokens.grid, self.t("grass_legend_zero"))]
        colors = (self.tokens.focus, self.tokens.accent, self.tokens.success, self.tokens.warning)
        for color, (start, end) in zip(colors, GRASS_FIXED_LEVEL_BANDS):
            key = "grass_legend_open" if end is None else "grass_legend_range"
            kwargs = {"start": f"{start:,}"}
            if end is not None:
                kwargs["end"] = f"{end:,}"
            items.append((color, self.t(key, **kwargs)))
        if self.uncommitted_today > 0:
            items.append((GRASS_UNCOMMITTED_LEVEL_COLORS[2], self.t("grass_uncommitted_legend")))
        for color, text in items:
            swatch = QLabel()
            swatch.setFixedSize(11, 11)
            swatch.setStyleSheet(f"background: {color}; border: 1px solid {self.tokens.border};")
            label = QLabel(text)
            label.setObjectName("MutedLabel")
            self.legend.addWidget(swatch)
            self.legend.addWidget(label)
        self.legend.addStretch(1)


class GrassHeatmap(QWidget):
    def __init__(self, translate, format_month_label) -> None:
        super().__init__()
        self.t = translate
        self.format_month_label = format_month_label
        self.tokens: QtThemeTokens | None = None
        self.points: list[tuple[dt.date, int]] = []
        self.highlight_day: dt.date | None = None
        self.uncommitted_today = 0
        self.setMinimumHeight(300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_theme_tokens(self, tokens: QtThemeTokens) -> None:
        self.tokens = tokens
        self.update()

    def set_data(self, points, highlight_day, uncommitted_today) -> None:
        self.points = list(points)
        self.highlight_day = highlight_day
        self.uncommitted_today = uncommitted_today
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        if self.tokens is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(self.tokens.canvas))
        painter.setPen(QPen(QColor(self.tokens.border), 1))
        painter.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), 8, 8)
        if not self.points:
            painter.setPen(QColor(self.tokens.muted))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.t("grass_empty"))
            painter.end()
            return

        start_day = self.points[0][0]
        end_day = self.points[-1][0]
        grid_start = start_day - dt.timedelta(days=start_day.weekday())
        grid_end = end_day + dt.timedelta(days=6 - end_day.weekday())
        week_count = max(1, ((grid_end - grid_start).days + 1) // 7)
        weeks_per_band = max(1, (week_count + 1) // 2)
        left = 42.0
        top = 32.0
        band_gap = 48.0
        available_width = max(260.0, self.width() - left - 18.0)
        pitch = min(21.0, available_width / weeks_per_band)
        cell = max(7.0, pitch - 4.0)
        band_height = pitch * 7
        total_height = band_height * 2 + band_gap + 28
        top = max(25.0, (self.height() - total_height) / 2)

        values = dict(self.points)
        effective_uncommitted = self.uncommitted_today if self.highlight_day == dt.date.today() else 0
        committed = dict(values)
        if self.highlight_day in committed:
            committed[self.highlight_day] = max(0, committed[self.highlight_day] - effective_uncommitted)

        painter.setPen(QColor(self.tokens.muted))
        for band in range(2):
            grid_y = top + band * (band_height + band_gap + 20) + 20
            for label, row in ((self.t("grass_day_mon"), 0), (self.t("grass_day_wed"), 2), (self.t("grass_day_fri"), 4)):
                painter.drawText(QRectF(8, grid_y + row * pitch, 28, cell), Qt.AlignmentFlag.AlignVCenter, label)
            previous_month = None
            for col in range(weeks_per_band):
                global_col = band * weeks_per_band + col
                if global_col >= week_count:
                    break
                visible = [
                    grid_start + dt.timedelta(days=global_col * 7 + row)
                    for row in range(7)
                    if start_day <= grid_start + dt.timedelta(days=global_col * 7 + row) <= end_day
                ]
                if not visible:
                    continue
                month = visible[0].month
                if col == 0 or month != previous_month:
                    painter.drawText(
                        QRectF(left + col * pitch, grid_y - 20, pitch * 3, 16),
                        self.format_month_label(month),
                    )
                    previous_month = month

        for day, value in self.points:
            offset = (day - grid_start).days
            global_col = offset // 7
            band = global_col // weeks_per_band
            col = global_col % weeks_per_band
            row = offset % 7
            grid_y = top + band * (band_height + band_gap + 20) + 20
            rect = QRectF(left + col * pitch, grid_y + row * pitch, cell, cell)
            is_today = day == self.highlight_day
            color = self._level_color(committed.get(day, value))
            if is_today and effective_uncommitted > 0:
                color = self._level_color(effective_uncommitted, uncommitted=True)
            painter.setPen(QPen(QColor(self.tokens.text if is_today else color), 1.2 if is_today else 0))
            painter.setBrush(QColor(color))
            painter.drawRoundedRect(rect, 2, 2)
        painter.end()

    def _level_color(self, value: int, *, uncommitted: bool = False) -> str:
        if self.tokens is None or value <= 0:
            return self.tokens.grid if self.tokens else "#222222"
        colors = GRASS_UNCOMMITTED_LEVEL_COLORS if uncommitted else (
            self.tokens.focus,
            self.tokens.accent,
            self.tokens.success,
            self.tokens.warning,
        )
        for color, (start, end) in zip(colors, GRASS_FIXED_LEVEL_BANDS):
            if value >= start and (end is None or value <= end):
                return color
        return colors[-1]
