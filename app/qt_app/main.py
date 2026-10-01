from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QProcess, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from line_tracker import TrackerConfig, compute_metrics, find_repo_root, format_output_lines, resolve_author, resolve_ref
from line_tracker_args import make_ui_parser


RESTART_PROPERTY = "lineTrackerRestartRequested"


def main() -> int:
    raw_args = sys.argv[1:]
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
    from qt_app.startup_window import StartupWindow

    startup = StartupWindow(args, explicit_repo=_has_explicit_repo(raw_args))
    main_window: object | None = None

    def open_dashboard(payload: object) -> None:
        nonlocal main_window
        try:
            from qt_app.main_window import LineTrackerQtWindow

            main_window = LineTrackerQtWindow(args, startup_payload=payload)
            main_window.show()
        except Exception as exc:
            startup.show_finalization_error(str(exc))
            return
        startup.close()

    startup.ready.connect(open_dashboard)
    startup.show()
    exit_code = app.exec()
    if app.property(RESTART_PROPERTY) is True:
        return 0 if _restart_current_process() else 1
    return exit_code


def _restart_current_process() -> bool:
    arguments = list(sys.argv[1:])
    if not getattr(sys, "frozen", False):
        arguments.insert(0, str(Path(sys.argv[0]).resolve()))
    started, _process_id = QProcess.startDetached(
        sys.executable,
        arguments,
        str(Path.cwd()),
    )
    return started


def _has_explicit_repo(args: list[str]) -> bool:
    return any(value == "--repo" or value.startswith("--repo=") for value in args)


if __name__ == "__main__":
    raise SystemExit(main())
