from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class ScrollPanel:
    def __init__(
        self,
        parent: ttk.Frame,
        *,
        canvas_bg: str,
        scrollbar_style: str,
        content_style: str = "App.TFrame",
    ) -> None:
        self.parent = parent
        self.canvas_bg = canvas_bg
        self.scrollbar_style = scrollbar_style
        self.content_style = content_style
        self.host: ttk.Frame | None = None
        self.canvas: tk.Canvas | None = None
        self.scrollbar: ttk.Scrollbar | None = None
        self.content: ttk.Frame | None = None
        self.canvas_window: int | None = None
        self.indicator: int | None = None
        self.indicator_hide_job: str | None = None
        self.indicator_color = "#7d8792"
        self.scroll_callback = None

    def build(self) -> ttk.Frame:
        host = ttk.Frame(self.parent, style="App.TFrame")
        host.columnconfigure(0, weight=1)
        host.rowconfigure(0, weight=1)
        self.host = host

        canvas = tk.Canvas(
            host,
            bg=self.canvas_bg,
            highlightthickness=0,
            bd=0,
            relief="flat",
        )
        canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas = canvas

        canvas.configure(yscrollcommand=self._on_canvas_yview)

        content = ttk.Frame(canvas, style=self.content_style)
        content.columnconfigure(0, weight=1)
        self.content = content
        self.canvas_window = canvas.create_window((0, 0), window=content, anchor="nw")

        content.bind("<Configure>", self.on_content_configure, add="+")
        canvas.bind("<Configure>", self.on_canvas_configure, add="+")
        self.indicator = canvas.create_rectangle(0, 0, 0, 0, fill=self.indicator_color, outline="", state="hidden")
        self._bind_scroll_events()
        return host

    def bind_content_tree(self) -> None:
        return

    def set_scroll_callback(self, callback) -> None:
        self.scroll_callback = callback

    def configure_width(self, content_width: int) -> None:
        if self.canvas is None or self.host is None:
            return
        self.canvas.configure(width=content_width)

    def apply_theme(self, *, canvas_bg: str) -> None:
        self.canvas_bg = canvas_bg
        if self.canvas is not None:
            self.canvas.configure(bg=canvas_bg)
            self.indicator_color = self._blend_hex(canvas_bg, "#ffffff", 0.42)
            if self.indicator is not None:
                self.canvas.itemconfigure(self.indicator, fill=self.indicator_color)

    def update_scroll_region(self) -> None:
        if self.canvas is None:
            return
        try:
            bbox = self.canvas.bbox("all")
            if bbox is not None:
                self.canvas.configure(scrollregion=bbox)
        except tk.TclError:
            return
        self._update_indicator()

    def has_overflow(self) -> bool:
        if self.canvas is None:
            return False
        try:
            bbox = self.canvas.bbox("all")
            viewport_height = int(self.canvas.winfo_height())
        except tk.TclError:
            return False
        return bool(bbox and (bbox[3] - bbox[1]) > viewport_height + 1)

    def on_content_configure(self, _: tk.Event) -> None:
        self.update_scroll_region()

    def on_canvas_configure(self, event: tk.Event) -> None:
        if self.canvas is not None and self.canvas_window is not None:
            self.canvas.itemconfigure(self.canvas_window, width=event.width)
        self.update_scroll_region()

    def _on_canvas_yview(self, first: str, last: str) -> None:
        self._update_indicator(float(first), float(last))

    def _bind_scroll_events(self) -> None:
        if self.host is None:
            return
        self.host.bind_all("<MouseWheel>", self.on_mousewheel, add="+")
        self.host.bind_all("<Button-4>", self.on_mousewheel, add="+")
        self.host.bind_all("<Button-5>", self.on_mousewheel, add="+")

    def _pointer_inside_canvas(self) -> bool:
        if self.canvas is None:
            return False
        try:
            pointer_x = self.canvas.winfo_pointerx()
            pointer_y = self.canvas.winfo_pointery()
            left = self.canvas.winfo_rootx()
            top = self.canvas.winfo_rooty()
            right = left + self.canvas.winfo_width()
            bottom = top + self.canvas.winfo_height()
        except tk.TclError:
            return False
        return left <= pointer_x <= right and top <= pointer_y <= bottom

    def on_mousewheel(self, event: tk.Event) -> str | None:
        if self.canvas is None or not self.has_overflow() or not self._pointer_inside_canvas():
            return None

        delta = 0
        event_num = getattr(event, "num", None)
        if event_num == 4:
            delta = -1
        elif event_num == 5:
            delta = 1
        else:
            raw_delta = int(getattr(event, "delta", 0))
            if raw_delta == 0:
                return None
            step = max(1, abs(raw_delta) // 120)
            delta = -step if raw_delta > 0 else step

        try:
            self.canvas.yview_scroll(delta, "units")
        except tk.TclError:
            return None
        self._show_indicator_temporarily()
        self._notify_scroll()
        return "break"

    def _show_indicator(self) -> None:
        if self.canvas is None or self.indicator is None or not self.has_overflow():
            return
        self._update_indicator()
        self.canvas.itemconfigure(self.indicator, state="normal")
        self.canvas.tag_raise(self.indicator)
        if self.indicator_hide_job is not None and self.host is not None:
            try:
                self.host.after_cancel(self.indicator_hide_job)
            except tk.TclError:
                pass
            self.indicator_hide_job = None

    def _show_indicator_temporarily(self) -> None:
        if self.host is None:
            return
        self._show_indicator()
        if self.indicator_hide_job is not None:
            try:
                self.host.after_cancel(self.indicator_hide_job)
            except tk.TclError:
                pass
        self.indicator_hide_job = self.host.after(650, self._hide_indicator)

    def _hide_indicator(self) -> None:
        self.indicator_hide_job = None
        if self.canvas is None or self.indicator is None:
            return
        self.canvas.itemconfigure(self.indicator, state="hidden")

    def _update_indicator(self, first: float | None = None, last: float | None = None) -> None:
        if self.canvas is None or self.indicator is None:
            return
        if not self.has_overflow():
            self.canvas.itemconfigure(self.indicator, state="hidden")
            return
        if first is None or last is None:
            try:
                first, last = self.canvas.yview()
            except tk.TclError:
                return
        width = max(1, int(self.canvas.winfo_width()))
        height = max(1, int(self.canvas.winfo_height()))
        track_margin = 4
        indicator_width = 3
        min_height = 18
        thumb_height = max(min_height, int((last - first) * height))
        top = track_margin + int(first * max(1, height - (track_margin * 2)))
        bottom = min(height - track_margin, top + thumb_height)
        left = width - track_margin - indicator_width
        right = width - track_margin
        self.canvas.coords(self.indicator, left, top, right, bottom)

    def _notify_scroll(self) -> None:
        if self.scroll_callback is None or self.canvas is None:
            return
        try:
            first, last = self.canvas.yview()
        except tk.TclError:
            return
        self.scroll_callback(first, last)

    @staticmethod
    def _blend_hex(base: str, overlay: str, ratio: float) -> str:
        def parse(value: str) -> tuple[int, int, int]:
            cleaned = value.strip().lstrip("#")
            if len(cleaned) != 6:
                return 127, 135, 146
            return tuple(int(cleaned[index:index + 2], 16) for index in (0, 2, 4))

        mix_ratio = min(max(ratio, 0.0), 1.0)
        base_rgb = parse(base)
        overlay_rgb = parse(overlay)
        blended = tuple(
            round(base_channel + (overlay_channel - base_channel) * mix_ratio)
            for base_channel, overlay_channel in zip(base_rgb, overlay_rgb)
        )
        return "#" + "".join(f"{channel:02x}" for channel in blended)
