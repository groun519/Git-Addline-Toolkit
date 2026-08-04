from __future__ import annotations

import datetime as dt

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from line_tracker_presenters import StatSectionPresentation
from qt_app.icons import make_icon
from qt_app.theme import QtThemeTokens


LANGUAGE_COLORS = (
    "#67b7a0",
    "#e0ad62",
    "#6f9fd8",
    "#d87885",
    "#9b82d0",
    "#75b8ca",
    "#c89570",
    "#8eb56f",
)


class IconButton(QPushButton):
    def __init__(self, icon_name: str, tooltip: str, *, size: int = 30) -> None:
        super().__init__()
        self._icon_name = icon_name
        self._icon_color = "#ffffff"
        self.setObjectName("IconButton")
        self.setFixedSize(size, size)
        self.setIconSize(self.size() * 0.58)
        self.setToolTip(tooltip)
        self.setAccessibleName(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_icon_color(self, color: str) -> None:
        self._icon_color = color
        self.setIcon(make_icon(self._icon_name, color, max(16, int(self.width() * 0.56))))


class ThemedComboBox(QComboBox):
    def __init__(self) -> None:
        super().__init__()
        self._chevron_color = "#ffffff"

    def set_chevron_color(self, color: str) -> None:
        self._chevron_color = color
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        _draw_chevron(self, self._chevron_color)


class ThemedDateEdit(QDateEdit):
    def __init__(self) -> None:
        super().__init__()
        self._chevron_color = "#ffffff"

    def set_chevron_color(self, color: str) -> None:
        self._chevron_color = color
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        _draw_chevron(self, self._chevron_color)


def _draw_chevron(widget: QWidget, color: str) -> None:
    painter = QPainter(widget)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(QPen(QColor(color), 1.5))
    center_x = widget.width() - 14
    center_y = widget.height() // 2
    painter.drawLine(center_x - 3, center_y - 2, center_x, center_y + 1)
    painter.drawLine(center_x, center_y + 1, center_x + 3, center_y - 2)
    painter.end()


class WindowTitleBar(QFrame):
    minimize_requested = Signal()
    close_requested = Signal()

    def __init__(self, title: str, version: str) -> None:
        super().__init__()
        self.setObjectName("TitleBar")
        self.setFixedHeight(36)
        self._drag_offset: QPoint | None = None

        self.accent = QFrame()
        self.accent.setObjectName("HeaderAccent")
        self.accent.setFixedSize(4, 17)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("TitleBarTitle")
        self.version_label = QLabel(version)
        self.version_label.setObjectName("TitleBarVersion")
        self.minimize_button = IconButton("minimize", "Minimize")
        self.minimize_button.setObjectName("WindowButton")
        self.close_button = IconButton("close", "Close")
        self.close_button.setObjectName("WindowCloseButton")
        self.minimize_button.clicked.connect(self.minimize_requested)
        self.close_button.clicked.connect(self.close_requested)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 3, 6, 3)
        layout.setSpacing(8)
        layout.addWidget(self.accent)
        layout.addWidget(self.title_label)
        layout.addWidget(self.version_label)
        layout.addStretch(1)
        layout.addWidget(self.minimize_button)
        layout.addWidget(self.close_button)

    def set_icon_color(self, color: str) -> None:
        self.minimize_button.set_icon_color(color)
        self.close_button.set_icon_color(color)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.window().frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.window().move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._drag_offset = None
        super().mouseReleaseEvent(event)


class StatCard(QFrame):
    def __init__(self, accent_color: str) -> None:
        super().__init__()
        self.setObjectName("StatCard")
        self.accent = QFrame()
        self.accent.setObjectName("StatAccent")
        self.accent.setFixedWidth(4)
        self.accent.setStyleSheet(f"background: {accent_color};")
        self.label = QLabel()
        self.label.setObjectName("StatLabel")
        self.label.setWordWrap(True)
        self.value = QLabel()
        self.value.setObjectName("StatValue")

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(3)
        text_layout.addWidget(self.label)
        text_layout.addWidget(self.value)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(9)
        layout.addWidget(self.accent)
        layout.addLayout(text_layout, 1)

    def set_content(self, label: str, value: str) -> None:
        self.label.setText(label)
        self.value.setText(value)


class StatsSection(QWidget):
    def __init__(self, accent_colors: tuple[str, str]) -> None:
        super().__init__()
        self.title = QLabel()
        self.title.setObjectName("SectionTitle")
        self.added = QLabel()
        self.added.setObjectName("DeltaAdd")
        self.removed = QLabel()
        self.removed.setObjectName("DeltaRemove")
        self.commits = QLabel()
        self.commits.setObjectName("CommitCount")
        self.cards = (StatCard(accent_colors[0]), StatCard(accent_colors[1]))

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(9)
        header.addWidget(self.title)
        header.addWidget(self.added)
        header.addWidget(self.removed)
        header.addWidget(self.commits)
        header.addStretch(1)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.addWidget(self.cards[0], 0, 0)
        grid.addWidget(self.cards[1], 0, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addLayout(header)
        layout.addLayout(grid)

    def set_presentation(self, presentation: StatSectionPresentation) -> None:
        self.title.setText(presentation.title)
        self.added.setText(presentation.added)
        self.removed.setText(presentation.removed)
        self.commits.setText(presentation.commits)
        self.added.setVisible(bool(presentation.added))
        self.removed.setVisible(bool(presentation.removed))
        self.commits.setVisible(bool(presentation.commits))
        for card, content in zip(self.cards, presentation.cards):
            card.set_content(content.label, content.value)


class LanguageProgressBar(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setMinimumHeight(22)
        self.setMouseTracking(True)
        self._percent = 0.0
        self._text = ""
        self._language_lines: dict[str, int] = {}
        self._tokens: QtThemeTokens | None = None
        self._segments: list[tuple[QRectF, str, int, int]] = []

    def set_theme_tokens(self, tokens: QtThemeTokens) -> None:
        self._tokens = tokens
        self.update()

    def set_progress(self, percent: float, text: str, language_lines: dict[str, int]) -> None:
        self._percent = max(0.0, min(100.0, percent))
        self._text = text
        self._language_lines = {key: value for key, value in language_lines.items() if value > 0}
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        if self._tokens is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        bounds = QRectF(0.5, 1.5, max(1.0, self.width() - 1.0), max(1.0, self.height() - 3.0))
        path = QPainterPath()
        path.addRoundedRect(bounds, 5.0, 5.0)
        painter.fillPath(path, QColor(self._tokens.raised))
        painter.setPen(QPen(QColor(self._tokens.border), 1.0))
        painter.drawPath(path)

        filled_width = bounds.width() * self._percent / 100.0
        fill_rect = QRectF(bounds.left(), bounds.top(), filled_width, bounds.height())
        painter.save()
        painter.setClipPath(path)
        self._segments.clear()
        total = sum(self._language_lines.values())
        if total > 0 and filled_width > 0:
            cursor = fill_rect.left()
            for index, (language, value) in enumerate(self._language_lines.items()):
                segment_width = filled_width * value / total
                segment = QRectF(cursor, fill_rect.top(), segment_width, fill_rect.height())
                painter.fillRect(segment, QColor(LANGUAGE_COLORS[index % len(LANGUAGE_COLORS)]))
                self._segments.append((segment, language, value, total))
                cursor += segment_width
        elif filled_width > 0:
            painter.fillRect(fill_rect, QColor(self._tokens.accent))
        painter.restore()

        painter.setPen(QColor(self._tokens.accent_text if self._percent > 52 else self._tokens.text))
        font = painter.font()
        font.setBold(True)
        font.setPointSize(8)
        painter.setFont(font)
        painter.drawText(bounds, Qt.AlignmentFlag.AlignCenter, self._text)
        painter.end()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        position = event.position()
        for rect, language, value, total in self._segments:
            if rect.contains(position):
                percent = value / total * 100.0 if total else 0.0
                QToolTip.showText(event.globalPosition().toPoint(), f"{language}\n{value:,} lines ({percent:.1f}%)", self)
                return
        QToolTip.hideText()

    def leaveEvent(self, event) -> None:  # noqa: N802
        QToolTip.hideText()
        super().leaveEvent(event)


class ActivityGraph(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setMinimumHeight(190)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._tokens: QtThemeTokens | None = None
        self._series: list[tuple[str, str, list[tuple[dt.date, int]], bool]] = []
        self._highlight_day: dt.date | None = None
        self._curve_strength = 35.0
        self._adaptive_axis = False

    def set_theme_tokens(self, tokens: QtThemeTokens) -> None:
        self._tokens = tokens
        self.update()

    def set_data(
        self,
        series: list[tuple[str, str, list[tuple[dt.date, int]], bool]],
        highlight_day: dt.date,
        curve_strength: float,
    ) -> None:
        self._series = series
        self._highlight_day = highlight_day
        self._curve_strength = curve_strength
        self._adaptive_axis = self._should_use_adaptive_axis()
        self.update()

    @property
    def uses_adaptive_axis(self) -> bool:
        return self._adaptive_axis

    def _should_use_adaptive_axis(self) -> bool:
        values = [
            value
            for name, _, points, enabled in self._series
            if enabled and name != "commits"
            for _, value in points
        ]
        positive_values = sorted(value for value in values if value > 0)
        if len(values) < 8 or not positive_values:
            return False
        median = positive_values[len(positive_values) // 2]
        return median > 0 and max(values, default=0) >= median * 4

    def paintEvent(self, _event) -> None:  # noqa: N802
        if self._tokens is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(self._tokens.canvas))
        active = [entry for entry in self._series if entry[3]]
        line_series = [entry for entry in active if entry[0] != "commits"]
        commit_series = [entry for entry in active if entry[0] == "commits"]
        has_secondary_axis = bool(line_series and commit_series)
        right_margin = 46 if has_secondary_axis else 14
        chart = QRectF(44, 12, max(1, self.width() - 44 - right_margin), max(1, self.height() - 42))
        painter.setPen(QPen(QColor(self._tokens.border), 1.0))
        painter.drawRect(chart)

        primary_series = line_series or commit_series
        primary_values = [value for _, _, points, _ in primary_series for _, value in points]
        secondary_values = [value for _, _, points, _ in commit_series for _, value in points] if line_series else []
        y_top = max(max(primary_values, default=0), 1)
        secondary_top = max(max(secondary_values, default=0), 1)
        adaptive_axis = self._adaptive_axis
        exponent = 0.5 if adaptive_axis else 1.0

        def value_ratio(name: str, value: int) -> float:
            if name == "commits" and line_series:
                return max(0.0, value / secondary_top)
            return (max(0.0, value / y_top)) ** exponent

        def value_y(name: str, value: int) -> float:
            plot_top = chart.top() + 4.0
            plot_bottom = chart.bottom() - 4.0
            return plot_bottom - value_ratio(name, value) * (plot_bottom - plot_top)

        for index in range(5):
            ratio = index / 4
            y_pos = chart.bottom() - chart.height() * ratio
            painter.setPen(QPen(QColor(self._tokens.grid), 1.0))
            painter.drawLine(chart.left(), y_pos, chart.right(), y_pos)
            painter.setPen(QColor(self._tokens.muted))
            tick_value = y_top * (ratio ** (1.0 / exponent))
            painter.drawText(
                QRectF(0, y_pos - 8, 38, 16),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                f"{round(tick_value):,}",
            )
            if has_secondary_axis:
                painter.setPen(QColor(commit_series[0][1]))
                painter.drawText(
                    QRectF(chart.right() + 6, y_pos - 8, 36, 16),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    f"{secondary_top * ratio:.1f}".rstrip("0").rstrip("."),
                )

        first_points = active[0][2] if active else []
        count = max(1, len(first_points))
        slot = chart.width() / count
        for name, color, points, _enabled in active:
            screen_points: list[tuple[float, float]] = []
            for index, (_day, value) in enumerate(points):
                x_pos = chart.left() + slot * index + slot / 2
                y_pos = value_y(name, value)
                screen_points.append((x_pos, y_pos))
            if len(screen_points) >= 2:
                path = QPainterPath()
                path.moveTo(QPointF(*screen_points[0]))
                curve_ratio = min(max(self._curve_strength, 0.0), 100.0) / 100.0 * 0.42
                for start, end in zip(screen_points, screen_points[1:]):
                    if curve_ratio <= 0.0:
                        path.lineTo(QPointF(*end))
                        continue
                    distance = end[0] - start[0]
                    path.cubicTo(
                        QPointF(start[0] + distance * curve_ratio, start[1]),
                        QPointF(end[0] - distance * curve_ratio, end[1]),
                        QPointF(*end),
                    )
                pen = QPen(QColor(color), 2.0)
                if name == "commits":
                    pen.setStyle(Qt.PenStyle.DashLine)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPath(path)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(color))
            for index, (day, value) in enumerate(points):
                x_pos = chart.left() + slot * index + slot / 2
                y_pos = value_y(name, value)
                radius = 4.0 if day == self._highlight_day else 2.4
                painter.drawEllipse(QPoint(round(x_pos), round(y_pos)), round(radius), round(radius))

        if first_points:
            max_labels = max(2, min(7, int(chart.width() // 64)))
            label_count = min(len(first_points), max_labels)
            if label_count <= 1:
                label_indices = {0}
            else:
                label_indices = {
                    round(index * (len(first_points) - 1) / (label_count - 1))
                    for index in range(label_count)
                }
            painter.setPen(QColor(self._tokens.muted))
            for index, (day, _value) in enumerate(first_points):
                if index in label_indices:
                    x_pos = chart.left() + slot * index + slot / 2
                    painter.drawText(QRectF(x_pos - 28, chart.bottom() + 6, 56, 18), Qt.AlignmentFlag.AlignCenter, day.strftime("%m-%d"))
        painter.end()
