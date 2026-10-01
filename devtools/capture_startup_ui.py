from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
APP_DIR = ROOT_DIR / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from hidden_desktop import close_hidden_desktop, create_hidden_desktop
from line_tracker_args import make_ui_parser
from line_tracker_settings import UISettings
from qt_app.startup_window import StartupWindow


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture the Line Tracker startup card.")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--state", choices=("select", "loading", "complete"), default="select")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT_DIR / "build" / "ui-captures" / "qt-startup-card.png",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    desktop = create_hidden_desktop()
    app: QApplication | None = None
    window: StartupWindow | None = None
    dashboard = None
    error: list[Exception] = []
    try:
        app = QApplication([])
        ui_args = make_ui_parser().parse_args(["--repo", args.repo])
        settings = UISettings(repo_path=str(Path(args.repo).resolve())) if args.state == "complete" else UISettings(repo_path="")
        window = StartupWindow(ui_args, settings_override=settings)
        if args.state == "loading":
            repo = Path(args.repo).resolve()
            window.repo = repo
            window._show_repository(repo)
            window._loading = True
            window.heading.setText(window.t("startup_loading_title"))
            window._set_stage("languages")
            window.progress.setValue(65)
            window.progress_value.setText("65%")
            window.progress.show()
            window.progress_value.show()
            window.select_button.setEnabled(False)
        window.show()
        started = time.monotonic()

        def capture(target) -> None:
            try:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                image = target.grab()
                if not image.save(str(args.output.resolve())):
                    raise OSError(f"Failed to save capture: {args.output.resolve()}")
                print(f"Captured {image.width()}x{image.height()}: {args.output.resolve()}")
            except Exception as exc:
                error.append(exc)
            window.close()
            if dashboard is not None:
                dashboard.close()
            app.quit()

        if args.state == "complete":
            def open_dashboard(payload) -> None:
                nonlocal dashboard
                from qt_app.main_window import LineTrackerQtWindow

                dashboard = LineTrackerQtWindow(ui_args, capture_mode=True, startup_payload=payload)
                dashboard.resize(1420, 780)
                dashboard.show()
                window.hide()
                QTimer.singleShot(300, lambda: capture(dashboard))

            def check_timeout() -> None:
                if dashboard is not None or error:
                    return
                if time.monotonic() - started >= args.timeout:
                    error.append(TimeoutError(f"Startup flow did not finish within {args.timeout:g} seconds."))
                    window.close()
                    app.quit()
                    return
                QTimer.singleShot(250, check_timeout)

            window.ready.connect(open_dashboard)
            QTimer.singleShot(250, check_timeout)
        else:
            QTimer.singleShot(250, lambda: capture(window))
        app.exec()
        if error:
            raise error[0]
    finally:
        if window is not None:
            window.close()
        close_hidden_desktop(desktop)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
