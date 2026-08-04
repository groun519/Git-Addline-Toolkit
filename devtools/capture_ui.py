#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ctypes
import datetime as dt
import os
import sys
import time
import tkinter as tk
from ctypes import wintypes
from pathlib import Path

from PIL import Image


ROOT_DIR = Path(__file__).resolve().parents[1]
APP_DIR = ROOT_DIR / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from line_tracker_ui import LineTrackerApp, make_parser  # noqa: E402
from line_tracker_schedule import DirectiveScheduleParser  # noqa: E402
from line_tracker_theme import get_theme_names, get_theme_palette, resolve_theme_name  # noqa: E402
from line_tracker_ui_resources import LANG_DISPLAY  # noqa: E402


CAPTURE_SURFACES = (
    "current",
    "main-schedule-empty",
    "main-schedule-sample",
    "main-schedule-sample-bottom",
    "main-schedule-error",
    "main-grass",
    "stats-top",
    "stats-bottom",
    "settings-general",
    "settings-repo",
    "settings-tracking",
    "settings-schedule",
    "graph-settings",
    "compact-card",
    "compact-strip",
)


class BitmapInfoHeader(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BitmapInfo(ctypes.Structure):
    _fields_ = [("bmiHeader", BitmapInfoHeader), ("bmiColors", wintypes.DWORD * 3)]


def create_hidden_desktop() -> int:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.CreateDesktopW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
    ]
    user32.CreateDesktopW.restype = wintypes.HANDLE
    user32.SetThreadDesktop.argtypes = [wintypes.HANDLE]
    user32.SetThreadDesktop.restype = wintypes.BOOL
    desktop_name = f"LineTrackerCapture-{os.getpid()}-{time.time_ns()}"
    desktop = user32.CreateDesktopW(desktop_name, None, None, 0, 0x10000000, None)
    if not desktop:
        raise ctypes.WinError(ctypes.get_last_error())
    if not user32.SetThreadDesktop(desktop):
        error = ctypes.WinError(ctypes.get_last_error())
        user32.CloseDesktop(desktop)
        raise error
    return int(desktop)


def close_hidden_desktop(desktop: int) -> None:
    user32 = ctypes.windll.user32
    user32.CloseDesktop.argtypes = [wintypes.HANDLE]
    user32.CloseDesktop.restype = wintypes.BOOL
    user32.CloseDesktop(desktop)


def native_window_handle(widget: tk.Misc, *, root_window: bool = False) -> int:
    widget.update_idletasks()
    if not root_window:
        return int(widget.winfo_id())
    user32 = ctypes.windll.user32
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetAncestor.restype = wintypes.HWND
    return int(user32.GetAncestor(widget.winfo_id(), 2))


def capture_window(
    hwnd: int,
    output_path: Path,
    crop_box: tuple[int, int, int, int] | None = None,
) -> tuple[int, int]:
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.GetWindowDC.argtypes = [wintypes.HWND]
    user32.GetWindowDC.restype = wintypes.HDC
    user32.GetDC.argtypes = [wintypes.HWND]
    user32.GetDC.restype = wintypes.HDC
    user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
    user32.PrintWindow.restype = wintypes.BOOL
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    user32.ReleaseDC.restype = ctypes.c_int
    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi32.SelectObject.restype = wintypes.HGDIOBJ
    gdi32.GetDIBits.argtypes = [
        wintypes.HDC,
        wintypes.HBITMAP,
        wintypes.UINT,
        wintypes.UINT,
        wintypes.LPVOID,
        ctypes.POINTER(BitmapInfo),
        wintypes.UINT,
    ]
    gdi32.GetDIBits.restype = ctypes.c_int
    gdi32.BitBlt.argtypes = [
        wintypes.HDC,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.HDC,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.DWORD,
    ]
    gdi32.BitBlt.restype = wintypes.BOOL
    gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi32.DeleteObject.restype = wintypes.BOOL
    gdi32.DeleteDC.argtypes = [wintypes.HDC]
    gdi32.DeleteDC.restype = wintypes.BOOL
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise OSError("Could not read the capture window bounds.")

    width = rect.right - rect.left
    height = rect.bottom - rect.top
    if width <= 0 or height <= 0:
        raise OSError(f"Invalid capture size: {width}x{height}")

    window_dc = user32.GetWindowDC(hwnd)
    memory_dc = gdi32.CreateCompatibleDC(window_dc)
    bitmap = gdi32.CreateCompatibleBitmap(window_dc, width, height)
    previous = gdi32.SelectObject(memory_dc, bitmap)
    try:
        if not user32.PrintWindow(hwnd, memory_dc, 0):
            raise OSError("PrintWindow failed to render the hidden-desktop window.")

        info = BitmapInfo()
        info.bmiHeader.biSize = ctypes.sizeof(BitmapInfoHeader)
        info.bmiHeader.biWidth = width
        info.bmiHeader.biHeight = -height
        info.bmiHeader.biPlanes = 1
        info.bmiHeader.biBitCount = 32
        info.bmiHeader.biCompression = 0
        pixels = ctypes.create_string_buffer(width * height * 4)
        rows = gdi32.GetDIBits(
            memory_dc,
            bitmap,
            0,
            height,
            pixels,
            ctypes.byref(info),
            0,
        )
        if rows != height:
            raise OSError(f"Only {rows} of {height} capture rows were read.")

        image = Image.frombuffer("RGB", (width, height), pixels, "raw", "BGRX", 0, 1).copy()
        if image.getbbox() is None:
            if not gdi32.BitBlt(memory_dc, 0, 0, width, height, window_dc, 0, 0, 0x00CC0020):
                raise OSError("BitBlt fallback failed to render the hidden-desktop window.")
            rows = gdi32.GetDIBits(
                memory_dc,
                bitmap,
                0,
                height,
                pixels,
                ctypes.byref(info),
                0,
            )
            if rows != height:
                raise OSError(f"Only {rows} of {height} fallback capture rows were read.")
            image = Image.frombuffer("RGB", (width, height), pixels, "raw", "BGRX", 0, 1).copy()
        if image.getbbox() is None:
            raise OSError("The hidden-desktop capture returned an empty image.")
        if crop_box is not None:
            image = image.crop(crop_box)
            width, height = image.size
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(output_path)
    finally:
        gdi32.SelectObject(memory_dc, previous)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memory_dc)
        user32.ReleaseDC(hwnd, window_dc)
    return width, height


def capture_after_refresh(
    app: LineTrackerApp,
    output_path: Path,
    timeout_seconds: float,
    widget_name: str,
    surface: str,
) -> tuple[int, int]:
    deadline = time.monotonic() + timeout_seconds
    result: dict[str, object] = {}

    def poll() -> None:
        if app.refresh_in_progress:
            if time.monotonic() >= deadline:
                result["error"] = TimeoutError(
                    f"UI refresh did not finish within {timeout_seconds:g} seconds."
                )
                app.root.quit()
                return
            app.root.after(50, poll)
            return

        try:
            surface_widget = prepare_capture_surface(app, surface)
            app.root.update()
            surface_widget.update()
            widget = surface_widget if widget_name == "root" else getattr(app, widget_name, None)
            if widget is None or not isinstance(widget, tk.Misc):
                raise ValueError(f"Unknown Tk widget attribute: {widget_name}")
            if widget_name in {"progress_section", "progress_card"}:
                app.stats_container.destroy()
                app.root.update()
            capture_root = widget.winfo_toplevel()
            hwnd = native_window_handle(capture_root, root_window=True)
            if not hwnd:
                raise OSError("Could not resolve the Line Tracker window handle.")
            crop_box = None
            if widget is not capture_root:
                left = widget.winfo_rootx() - capture_root.winfo_rootx()
                top = widget.winfo_rooty() - capture_root.winfo_rooty()
                crop_box = (
                    left,
                    top,
                    left + widget.winfo_width(),
                    top + widget.winfo_height(),
                )
            result["size"] = capture_window(hwnd, output_path, crop_box)
        except Exception as exc:
            result["error"] = exc
        finally:
            app.root.quit()

    app.root.after(0, poll)
    app.root.mainloop()
    if "error" in result:
        raise result["error"]
    return result["size"]


def prepare_capture_surface(app: LineTrackerApp, surface: str) -> tk.Misc:
    if surface == "current":
        return app.root
    if surface.startswith("main-schedule-"):
        app.cancel_schedule_poll()
        app.show_note_tab("schedule", persist=False)
        if surface == "main-schedule-empty":
            app.schedule_panel_controller.show_unconfigured()
        elif surface == "main-schedule-error":
            app.schedule_panel_controller.show_error(
                app.repo / "SCHEDULE.md",
                app.t("schedule_error_missing"),
            )
        else:
            today = app.current_schedule_today()
            schedule_text = "\n".join(
                (
                    f"@@DAY {today - dt.timedelta(days=2)}",
                    "ITEM-001 | PLANNED | 18:00~22:00 | Lock the combat event contract",
                    f"@@DAY {today}",
                    "ITEM-002 | IN_PROGRESS | 10:00~15:00 | Finish the schedule page frontend",
                    "- Keep the renderer independent from the Markdown parser.",
                    "ITEM-003 | PLANNED | 16:00~18:00 | Verify installer update behavior",
                    f"@@DAY {today + dt.timedelta(days=3)}",
                    "ITEM-004 | PLANNED | 20:00~21:00 | Review the first schedule draft",
                    "@@BACKLOG",
                    "ITEM-006 | PLANNED | | Polish schedule interactions",
                    "- Keep this item undated until the format stabilizes.",
                    f"@@DAY {today - dt.timedelta(days=1)}",
                    "ITEM-005 | DONE | 09:00~12:00 | Define the common schedule model",
                )
            )
            document = DirectiveScheduleParser().parse(
                schedule_text,
                app.repo / "docs" / "SCHEDULE.md",
            )
            app.schedule_panel_controller.show_document(document, today)
        app.freeze_note_panel_size()
        if surface == "main-schedule-sample-bottom":
            app.root.update_idletasks()
            schedule_scroll = app.schedule_panel_controller.scroll_panel
            schedule_scroll.update_scroll_region()
            schedule_scroll.canvas.yview_moveto(1.0)
            schedule_scroll._show_indicator()
        return app.root
    if surface == "main-grass":
        app.show_note_tab("grass", persist=False)
        return app.root
    if surface in {"stats-top", "stats-bottom"}:
        if surface == "stats-bottom" and app.stats_scroll_panel.has_overflow():
            app.stats_canvas.yview_moveto(1.0)
            app.stats_scroll_panel._show_indicator()
        else:
            app.stats_canvas.yview_moveto(0.0)
        return app.stats_scroll_host
    if surface.startswith("settings-"):
        app.open_app_settings_window()
        tab_index = {
            "settings-general": 0,
            "settings-repo": 1,
            "settings-tracking": 2,
            "settings-schedule": 3,
        }[surface]
        app.app_settings_notebook.select(tab_index)
        return app.app_settings_window
    if surface == "graph-settings":
        app.open_graph_settings_window()
        return app.graph_settings_window
    if surface in {"compact-card", "compact-strip"}:
        app.compact_variant = "card" if surface == "compact-card" else "strip"
        app.enter_compact_mode()
        return app.root
    raise ValueError(f"Unknown capture surface: {surface}")


def print_layout_diagnostics(app: LineTrackerApp) -> None:
    for name in (
        "container",
        "stats_scroll_host",
        "progress_section",
        "progress_title",
        "progress_card",
        "overall_progress_bar",
        "daily_progress_bar",
        "footer_frame",
    ):
        widget = getattr(app, name, None)
        if widget is None:
            continue
        print(
            f"{name}: x={widget.winfo_x()} y={widget.winfo_y()} "
            f"size={widget.winfo_width()}x{widget.winfo_height()} "
            f"requested={widget.winfo_reqwidth()}x{widget.winfo_reqheight()}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture the real Line Tracker UI without activating it.")
    parser.add_argument("--repo", default=str(ROOT_DIR), help="Repository used when no saved repository exists.")
    parser.add_argument("--output", type=Path, default=ROOT_DIR / "build" / "ui-captures" / "main.png")
    parser.add_argument("--timeout", type=float, default=120.0, help="Maximum refresh wait in seconds.")
    parser.add_argument("--theme", choices=get_theme_names(), help="Temporarily override the saved theme.")
    parser.add_argument("--lang", choices=("ko", "en"), help="Temporarily override the saved language.")
    parser.add_argument(
        "--surface",
        choices=CAPTURE_SURFACES,
        default="current",
        help="UI state to prepare before capture.",
    )
    parser.add_argument(
        "--widget",
        default="root",
        help="LineTrackerApp widget attribute to capture, such as progress_section.",
    )
    return parser.parse_args()


def main() -> int:
    if sys.platform != "win32":
        raise RuntimeError("Offscreen HWND capture is only supported on Windows.")

    capture_args = parse_args()
    ui_args = make_parser().parse_args(["--repo", capture_args.repo])
    desktop = create_hidden_desktop()
    root: tk.Tk | None = None
    app: LineTrackerApp | None = None
    try:
        root = tk.Tk()
        root.withdraw()
        app = LineTrackerApp(root, ui_args, capture_mode=True)
        if capture_args.theme:
            app.theme_name = resolve_theme_name(capture_args.theme)
            app.theme = get_theme_palette(app.theme_name)
            app.theme_var.set(app.theme_display_label(app.theme_name))
            app.apply_color_palette()
        if capture_args.lang:
            app.lang = capture_args.lang
            app.lang_var.set(LANG_DISPLAY[app.lang])
            app.apply_language()
        width, height = capture_after_refresh(
            app,
            capture_args.output.resolve(),
            capture_args.timeout,
            capture_args.widget,
            capture_args.surface,
        )
        print_layout_diagnostics(app)
        print(f"Captured {width}x{height}: {capture_args.output.resolve()}")
    finally:
        if app is not None:
            app.cancel_auto_refresh()
            app.cancel_schedule_poll()
            app.cancel_compact_clock()
        if root is not None:
            root.destroy()
        close_hidden_desktop(desktop)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
