from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from line_tracker import TrackerConfig, compute_metrics, find_repo_root, format_output_lines, resolve_author, resolve_ref
from line_tracker_args import make_ui_parser
from qt_app.main_window import LineTrackerQtWindow


def main() -> int:
    args = make_ui_parser().parse_args()
    if args.once:
        repo = find_repo_root(Path(args.repo))
        config = TrackerConfig(
            repo=repo,
            goal=args.goal,
            base_total=args.base_total,
            base_commit=args.base_commit,
            author=resolve_author(repo, args.author),
            ref=resolve_ref(repo, args.ref),
            include_local=True,
            today=args.today,
            month_end=args.month_end,
            assume_uncommitted_zero=False,
        )
        output = "\n".join(format_output_lines(compute_metrics(config)))
        if sys.stdout is not None:
            sys.stdout.write(f"{output}\n")
        return 0

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("Line Tracker")
    app.setOrganizationName("LineTracker")
    app.setStyle("Fusion")
    window = LineTrackerQtWindow(args)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
