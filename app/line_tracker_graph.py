from __future__ import annotations

import datetime as dt


GraphPoint = tuple[dt.date, int]
ScreenPoint = tuple[float, float]


def summarize_graph_values(points: list[GraphPoint]) -> tuple[float, int]:
    if not points:
        return 0.0, 0
    values = [value for _, value in points]
    return sum(values) / len(values), max(values)


def flatten_graph_points(points: list[ScreenPoint]) -> list[float]:
    flat_points: list[float] = []
    for x_pos, y_pos in points:
        flat_points.extend([x_pos, y_pos])
    return flat_points


def smooth_graph_points(points: list[ScreenPoint], curve_strength: float) -> list[ScreenPoint]:
    if len(points) < 3 or curve_strength <= 0.0:
        return points

    normalized_strength = min(max(curve_strength, 0.0), 100.0)
    cut_ratio = 0.16 + (normalized_strength / 100.0) * 0.12
    iterations = 1 + int(normalized_strength >= 30.0) + int(normalized_strength >= 65.0)

    smoothed = list(points)
    for _ in range(iterations):
        if len(smoothed) < 3:
            break
        next_points: list[ScreenPoint] = [smoothed[0]]
        for start_point, end_point in zip(smoothed, smoothed[1:]):
            start_x, start_y = start_point
            end_x, end_y = end_point
            next_points.append(
                (
                    (1.0 - cut_ratio) * start_x + cut_ratio * end_x,
                    (1.0 - cut_ratio) * start_y + cut_ratio * end_y,
                )
            )
            next_points.append(
                (
                    cut_ratio * start_x + (1.0 - cut_ratio) * end_x,
                    cut_ratio * start_y + (1.0 - cut_ratio) * end_y,
                )
            )
        next_points.append(smoothed[-1])
        smoothed = next_points
    return smoothed
