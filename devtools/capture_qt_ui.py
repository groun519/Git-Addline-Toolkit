from __future__ import annotations

import argparse
import sys
import time
from dataclasses import replace
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
APP_DIR = ROOT_DIR / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from hidden_desktop import close_hidden_desktop, create_hidden_desktop
from line_tracker_args import make_ui_parser
from line_tracker_theme import get_theme_palette, resolve_theme_name
from qt_app.main_window import LineTrackerQtWindow
from qt_app.settings_dialog import SettingsDialog
from qt_app.theme import build_theme_tokens


CAPTURE_SURFACES = (
    "activity",
    "schedule",
    "grass",
    "history",
    "settings",
    "settings-repo",
    "settings-tracking",
    "settings-graph",
    "settings-schedule",
    "overlay-card",
    "overlay-strip",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture the PySide6 migration UI on an isolated desktop.")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--output", type=Path, default=ROOT_DIR / "build" / "ui-captures" / "qt-main.png")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--width", type=int, default=1420)
    parser.add_argument("--height", type=int, default=780)
    parser.add_argument("--surface", choices=CAPTURE_SURFACES, default="activity")
    parser.add_argument("--theme")
    parser.add_argument("--lang", choices=("ko", "en"))
    parser.add_argument("--graph-series", choices=("additions", "lines", "commits", "all"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    desktop = create_hidden_desktop()
    app: QApplication | None = None
    window: LineTrackerQtWindow | None = None
    result: dict[str, object] = {}
    capture_target: list[object] = []
    prepared = False
    history_settled = False
    try:
        app = QApplication([])
        ui_args = make_ui_parser().parse_args(["--repo", args.repo])
        window = LineTrackerQtWindow(ui_args, capture_mode=True)
        if args.theme or args.lang or args.graph_series:
            if args.theme:
                window.theme_name = resolve_theme_name(args.theme)
                window.palette = get_theme_palette(window.theme_name)
                window.tokens = build_theme_tokens(window.palette)
                window.settings = replace(window.settings, theme=window.theme_name)
            if args.lang:
                window.lang = args.lang
                window.settings = replace(window.settings, lang=args.lang)
            if args.graph_series:
                window.settings = replace(
                    window.settings,
                    graph_show_additions=args.graph_series in {"additions", "lines", "all"},
                    graph_show_deletions=args.graph_series in {"lines", "all"},
                    graph_show_commits=args.graph_series in {"commits", "all"},
                )
            window._rebuild_ui()
            window._load_schedule(force=True)
        window.resize(args.width, args.height)
        window.show()
        started = time.monotonic()

        def capture_when_ready() -> None:
            nonlocal prepared, history_settled
            if window is None:
                return
            if window.last_snapshot is None and window.repo_selected:
                if time.monotonic() - started < args.timeout:
                    QTimer.singleShot(50, capture_when_ready)
                    return
                result["error"] = TimeoutError(f"Qt refresh did not finish within {args.timeout:g} seconds.")
            if "error" in result:
                window.close()
                app.quit()
                return
            if not prepared:
                prepared = True
                target = _prepare_surface(window, args.surface)
                capture_target.append(target)
                QTimer.singleShot(250, capture_when_ready)
                return
            if args.surface == "history" and window.history_view.loading and time.monotonic() - started < args.timeout:
                QTimer.singleShot(50, capture_when_ready)
                return
            if args.surface == "history" and not history_settled:
                history_settled = True
                QTimer.singleShot(500, capture_when_ready)
                return
            else:
                try:
                    args.output.parent.mkdir(parents=True, exist_ok=True)
                    target = capture_target[0]
                    image = target.grab()
                    if not image.save(str(args.output.resolve())):
                        raise OSError(f"Failed to save capture: {args.output.resolve()}")
                    result["size"] = (image.width(), image.height())
                except Exception as exc:
                    result["error"] = exc
            window.close()
            app.quit()

        QTimer.singleShot(0, capture_when_ready)
        app.exec()
        if "error" in result:
            raise result["error"]
        width, height = result["size"]
        print(f"Captured {width}x{height}: {args.output.resolve()}")
    finally:
        if window is not None:
            window.close()
        close_hidden_desktop(desktop)
    return 0


def _prepare_surface(window: LineTrackerQtWindow, surface: str):
    if surface == "activity":
        window.workspace_tabs.setCurrentIndex(0)
        return window
    if surface == "schedule":
        window.workspace_tabs.setCurrentIndex(0)
        return window
    if surface == "grass":
        window.workspace_tabs.setCurrentIndex(1)
        return window
    if surface == "history":
        return window
    if surface.startswith("settings"):
        options, mapping, aliases = window._build_author_options()
        dialog = SettingsDialog(
            window,
            translate=window.t,
            settings=window.settings,
            tokens=window.tokens,
            author_options=options,
            author_filter_map=mapping,
            author_display=window._author_display(mapping, aliases),
        )
        settings_tabs = {
            "settings": 0,
            "settings-repo": 1,
            "settings-tracking": 2,
            "settings-graph": 3,
            "settings-schedule": 4,
        }
        dialog.tabs.setCurrentIndex(settings_tabs[surface])
        dialog.show()
        return dialog
    window.enter_compact_mode()
    if window.overlay is None:
        raise RuntimeError("Compact overlay did not open.")
    window.overlay.set_variant("strip" if surface == "overlay-strip" else "card")
    return window.overlay


if __name__ == "__main__":
    raise SystemExit(main())
