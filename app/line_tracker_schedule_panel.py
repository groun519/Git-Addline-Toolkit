from __future__ import annotations

import datetime as dt
import tkinter as tk
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from tkinter import ttk
from typing import Callable

from line_tracker_schedule import (
    SCHEDULE_STATUS_DONE,
    SCHEDULE_STATUS_HOLD,
    SCHEDULE_STATUS_IN_PROGRESS,
    SCHEDULE_STATUS_NEXT,
    SCHEDULE_STATUS_REVIEW,
    ScheduleDocument,
    ScheduleItem,
)
from line_tracker_scroll_panel import ScrollPanel
from line_tracker_theme import ThemePalette
from line_tracker_ui_resources import blend_hex


SCHEDULE_PANEL_WIDTH = 590
SCHEDULE_LIST_HEIGHT = 328
SCHEDULE_ACTION_SIZE = 30


class _ScheduleIconButton:
    def __init__(
        self,
        parent: tk.Misc,
        *,
        icon: str,
        command: Callable[[], None],
        tooltip: str,
        get_theme: Callable[[], ThemePalette],
    ) -> None:
        self.icon = icon
        self.command = command
        self.tooltip_text = tooltip
        self.get_theme = get_theme
        self.enabled = True
        self.state = "normal"
        self.tooltip_job: str | None = None
        self.tooltip_window: tk.Toplevel | None = None
        self.canvas = tk.Canvas(
            parent,
            width=SCHEDULE_ACTION_SIZE,
            height=SCHEDULE_ACTION_SIZE,
            bd=0,
            highlightthickness=0,
            cursor="hand2",
            takefocus=True,
        )
        self.canvas.bind("<Enter>", self._on_enter)
        self.canvas.bind("<Leave>", self._on_leave)
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<FocusIn>", self._on_focus_in)
        self.canvas.bind("<FocusOut>", self._on_focus_out)
        self.canvas.bind("<Return>", self._on_keypress)
        self.canvas.bind("<space>", self._on_keypress)
        self.redraw()

    def grid(self, **kwargs: object) -> None:
        self.canvas.grid(**kwargs)

    def set_tooltip(self, text: str) -> None:
        self.tooltip_text = text
        self._hide_tooltip()

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)
        self.state = "normal" if self.enabled else "disabled"
        self.canvas.configure(cursor="hand2" if self.enabled else "arrow", takefocus=self.enabled)
        if not self.enabled:
            self._hide_tooltip()
        self.redraw()

    def apply_theme(self) -> None:
        self._hide_tooltip()
        self.redraw()

    def redraw(self) -> None:
        palette = self.get_theme()
        state = self.state if self.enabled else "disabled"
        fill = blend_hex(palette.card_bg, palette.accent_light, 0.08)
        border = blend_hex(palette.border, palette.accent_light, 0.18)
        icon_color = palette.accent_light
        if state == "hover":
            fill = blend_hex(palette.card_bg, palette.accent_light, 0.18)
            border = blend_hex(palette.border, palette.accent_light, 0.42)
            icon_color = palette.text
        elif state == "pressed":
            fill = blend_hex(palette.card_bg, palette.accent, 0.26)
            border = blend_hex(palette.border, palette.accent, 0.55)
            icon_color = palette.text
        elif state == "disabled":
            fill = blend_hex(palette.card_bg, palette.border, 0.12)
            border = blend_hex(palette.border, palette.card_bg, 0.35)
            icon_color = blend_hex(palette.muted_text, palette.card_bg, 0.48)

        canvas = self.canvas
        size = SCHEDULE_ACTION_SIZE
        canvas.configure(bg=palette.card_bg)
        canvas.delete("all")
        canvas.create_rectangle(2, 2, size - 2, size - 2, fill=fill, outline=border, width=1)
        if self.icon == "select":
            self._draw_select_icon(icon_color)
        elif self.icon == "reload":
            self._draw_reload_icon(icon_color)
        else:
            self._draw_folder_icon(icon_color)

    def _draw_select_icon(self, color: str) -> None:
        canvas = self.canvas
        canvas.create_polygon(8, 6, 18, 6, 22, 10, 22, 23, 8, 23, fill="", outline=color, width=2)
        canvas.create_line(18, 6, 18, 10, 22, 10, fill=color, width=2)
        canvas.create_line(11, 16, 19, 16, fill=color, width=2)
        canvas.create_line(15, 12, 15, 20, fill=color, width=2)

    def _draw_reload_icon(self, color: str) -> None:
        canvas = self.canvas
        canvas.create_arc(7, 7, 23, 23, start=35, extent=285, style="arc", outline=color, width=2)
        canvas.create_polygon(20, 5, 24, 9, 18, 10, fill=color, outline=color)

    def _draw_folder_icon(self, color: str) -> None:
        canvas = self.canvas
        canvas.create_polygon(
            6,
            10,
            12,
            10,
            14,
            13,
            24,
            13,
            22,
            23,
            6,
            23,
            fill="",
            outline=color,
            width=2,
        )
        canvas.create_line(7, 14, 23, 14, fill=color, width=2)

    def _on_enter(self, _: tk.Event) -> None:
        if not self.enabled:
            return
        self.state = "hover"
        self.redraw()
        self._schedule_tooltip()

    def _on_leave(self, _: tk.Event) -> None:
        if self.enabled:
            self.state = "normal"
            self.redraw()
        self._hide_tooltip()

    def _on_press(self, _: tk.Event) -> str:
        if self.enabled:
            self.state = "pressed"
            self.redraw()
        return "break"

    def _on_release(self, event: tk.Event) -> str:
        if not self.enabled:
            return "break"
        inside = 0 <= event.x <= SCHEDULE_ACTION_SIZE and 0 <= event.y <= SCHEDULE_ACTION_SIZE
        self.state = "hover" if inside else "normal"
        self.redraw()
        if inside:
            self._hide_tooltip()
            self.command()
        return "break"

    def _on_focus_in(self, _: tk.Event) -> None:
        if self.enabled:
            self.state = "hover"
            self.redraw()

    def _on_focus_out(self, _: tk.Event) -> None:
        if self.enabled:
            self.state = "normal"
            self.redraw()
        self._hide_tooltip()

    def _on_keypress(self, _: tk.Event) -> str:
        if self.enabled:
            self.command()
        return "break"

    def _schedule_tooltip(self) -> None:
        self._hide_tooltip()
        self.tooltip_job = self.canvas.after(350, self._show_tooltip)

    def _show_tooltip(self) -> None:
        self.tooltip_job = None
        if not self.enabled or not self.tooltip_text:
            return
        palette = self.get_theme()
        tooltip = tk.Toplevel(self.canvas)
        tooltip.withdraw()
        tooltip.overrideredirect(True)
        try:
            tooltip.attributes("-topmost", True)
        except tk.TclError:
            pass
        tooltip.configure(bg=palette.border)
        label = tk.Label(
            tooltip,
            text=self.tooltip_text,
            bg=palette.card_bg,
            fg=palette.text,
            font=("Bahnschrift", 9),
            padx=8,
            pady=5,
        )
        label.pack(padx=1, pady=1)
        tooltip.update_idletasks()
        x_pos = self.canvas.winfo_rootx() + SCHEDULE_ACTION_SIZE - tooltip.winfo_reqwidth()
        y_pos = self.canvas.winfo_rooty() + SCHEDULE_ACTION_SIZE + 5
        tooltip.geometry(f"+{x_pos}+{y_pos}")
        tooltip.deiconify()
        tooltip.lift()
        self.tooltip_window = tooltip

    def _hide_tooltip(self) -> None:
        if self.tooltip_job is not None:
            try:
                self.canvas.after_cancel(self.tooltip_job)
            except tk.TclError:
                pass
            self.tooltip_job = None
        if self.tooltip_window is not None:
            try:
                self.tooltip_window.destroy()
            except tk.TclError:
                pass
            self.tooltip_window = None


@dataclass(frozen=True)
class SchedulePanelBindings:
    translate: Callable[[str], str]
    get_theme: Callable[[], ThemePalette]
    select_file: Callable[[], None]
    reload: Callable[[], None]
    open_location: Callable[[], None]


class SchedulePanel:
    def __init__(self, bindings: SchedulePanelBindings) -> None:
        self.bindings = bindings
        self.state = "unconfigured"
        self.document: ScheduleDocument | None = None
        self.today = dt.date.today()
        self.error_message = ""
        self.source_path: Path | None = None

    def t(self, key: str, **kwargs) -> str:
        text = self.bindings.translate(key)
        try:
            return text.format(**kwargs)
        except (KeyError, ValueError):
            return text

    def theme(self) -> ThemePalette:
        return self.bindings.get_theme()

    def build(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)

        header = ttk.Frame(parent, style="CardInner.TFrame")
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        self.header = header

        title_column = ttk.Frame(header, style="CardInner.TFrame")
        title_column.grid(row=0, column=0, sticky="ew")
        title_column.columnconfigure(0, weight=1)

        self.title_var = tk.StringVar(value=self.t("schedule_title"))
        self.title_label = ttk.Label(title_column, textvariable=self.title_var, style="CardTitle.TLabel")
        self.title_label.grid(row=0, column=0, sticky="w")

        self.source_var = tk.StringVar(value=self.t("schedule_no_file"))
        self.source_label = ttk.Label(
            title_column,
            textvariable=self.source_var,
            style="CardLabel.TLabel",
            wraplength=410,
        )
        self.source_label.grid(row=1, column=0, sticky="w", pady=(2, 0))

        actions = ttk.Frame(header, style="CardInner.TFrame")
        actions.grid(row=0, column=1, sticky="e", padx=(12, 0))

        self.select_button = _ScheduleIconButton(
            actions,
            icon="select",
            command=self.bindings.select_file,
            tooltip=self.t("schedule_select"),
            get_theme=self.theme,
        )
        self.select_button.grid(row=0, column=0, sticky="e")

        self.reload_button = _ScheduleIconButton(
            actions,
            icon="reload",
            command=self.bindings.reload,
            tooltip=self.t("schedule_reload"),
            get_theme=self.theme,
        )
        self.reload_button.grid(row=0, column=1, sticky="e", padx=(6, 0))

        self.location_button = _ScheduleIconButton(
            actions,
            icon="folder",
            command=self.bindings.open_location,
            tooltip=self.t("schedule_open_location"),
            get_theme=self.theme,
        )
        self.location_button.grid(row=0, column=2, sticky="e", padx=(6, 0))

        self.summary = ttk.Frame(parent, style="CardInner.TFrame")
        self.summary.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        self.summary.columnconfigure(3, weight=1)
        self.summary_vars: dict[str, tk.StringVar] = {}
        self.summary_labels: dict[str, ttk.Label] = {}
        for column, key in enumerate(("total", "active", "done")):
            chip = ttk.Frame(self.summary, style="VersionBadge.TFrame", padding=(8, 3))
            chip.grid(row=0, column=column, sticky="w", padx=(0, 8))
            label = ttk.Label(chip, text=self.t(f"schedule_summary_{key}"), style="ChipLabel.TLabel")
            label.grid(row=0, column=0, sticky="w")
            self.summary_labels[key] = label
            value_var = tk.StringVar(value="0")
            value = ttk.Label(chip, textvariable=value_var, style="ChipValue.TLabel")
            value.grid(row=0, column=1, sticky="w", padx=(5, 0))
            self.summary_vars[key] = value_var

        list_wrapper = ttk.Frame(
            parent,
            style="CardInner.TFrame",
            width=SCHEDULE_PANEL_WIDTH,
            height=SCHEDULE_LIST_HEIGHT,
        )
        list_wrapper.grid(row=2, column=0, sticky="nsew", pady=(10, 0))
        list_wrapper.grid_propagate(False)
        list_wrapper.columnconfigure(0, weight=1)
        list_wrapper.rowconfigure(0, weight=1)
        self.list_wrapper = list_wrapper

        scroll_panel = ScrollPanel(
            list_wrapper,
            canvas_bg=self.theme().card_bg,
            scrollbar_style="Card.Vertical.TScrollbar",
            content_style="CardInner.TFrame",
        )
        scroll_host = scroll_panel.build()
        scroll_host.grid(row=0, column=0, sticky="nsew")
        self.scroll_panel = scroll_panel
        self.scroll_host = scroll_host
        self.list_container = scroll_panel.content
        if self.list_container is not None:
            self.list_container.columnconfigure(0, weight=1)

        self.refresh()

    def show_unconfigured(self) -> None:
        self.state = "unconfigured"
        self.document = None
        self.source_path = None
        self.error_message = ""
        self.refresh()

    def show_error(self, source_path: Path | None, message: str) -> None:
        self.state = "error"
        self.document = None
        self.source_path = source_path
        self.error_message = message
        self.refresh()

    def show_document(self, document: ScheduleDocument, today: dt.date) -> None:
        self.state = "loaded"
        self.document = document
        self.source_path = document.source_path
        self.today = today
        self.error_message = ""
        self.refresh()

    def apply_theme(self) -> None:
        for button_name in ("select_button", "reload_button", "location_button"):
            button = getattr(self, button_name, None)
            if button is not None:
                button.apply_theme()
        if hasattr(self, "scroll_panel"):
            self.scroll_panel.apply_theme(canvas_bg=self.theme().card_bg)
        self.refresh()

    def apply_language(self) -> None:
        if hasattr(self, "select_button"):
            self.select_button.set_tooltip(self.t("schedule_select"))
            self.reload_button.set_tooltip(self.t("schedule_reload"))
            self.location_button.set_tooltip(self.t("schedule_open_location"))
            for key, label in self.summary_labels.items():
                label.configure(text=self.t(f"schedule_summary_{key}"))
        self.refresh()

    def refresh(self) -> None:
        if not hasattr(self, "list_container"):
            return
        self._clear_content()

        if self.state == "unconfigured":
            self.title_var.set(self.t("schedule_title"))
            self.source_var.set(self.t("schedule_no_file"))
            self._set_summary(0, 0, 0)
            self.summary.grid_remove()
            self.reload_button.set_enabled(False)
            self.location_button.set_enabled(False)
            self._show_empty_state(
                self.t("schedule_unconfigured_title"),
                self.t("schedule_unconfigured_hint"),
                show_select=True,
            )
            return

        if self.state == "error":
            self.title_var.set(self.t("schedule_title"))
            self.source_var.set(self._source_text())
            self._set_summary(0, 0, 0)
            self.summary.grid_remove()
            self.reload_button.set_enabled(self.source_path is not None)
            self.location_button.set_enabled(self.source_path is not None)
            self._show_empty_state(
                self.t("schedule_error_title"),
                self.error_message,
                show_select=False,
            )
            return

        document = self.document
        if document is None:
            self.show_unconfigured()
            return

        self.title_var.set(document.title or self.t("schedule_title"))
        self.source_var.set(self._source_text())
        self.summary.grid()
        total = len(document.items)
        done = document.completed_count
        self._set_summary(total, total - done, done)
        self.reload_button.set_enabled(True)
        self.location_button.set_enabled(self.source_path is not None)
        if not document.items:
            self._show_empty_state(
                self.t("schedule_empty_title"),
                self.t("schedule_empty_hint"),
                show_select=False,
            )
            return
        self._render_items(document.items)

    def _clear_content(self) -> None:
        for child in self.list_container.winfo_children():
            child.destroy()
        empty_state = getattr(self, "empty_state", None)
        if empty_state is not None:
            empty_state.destroy()
            self.empty_state = None

    def _show_empty_state(self, title: str, hint: str, *, show_select: bool) -> None:
        state = ttk.Frame(self.list_wrapper, style="CardInner.TFrame")
        state.place(relx=0.5, rely=0.5, anchor="center")
        self.empty_state = state

        title_label = ttk.Label(state, text=title, style="CardTitle.TLabel", anchor="center")
        title_label.grid(row=0, column=0, sticky="ew")
        hint_label = ttk.Label(
            state,
            text=hint,
            style="CardLabel.TLabel",
            anchor="center",
            justify="center",
            wraplength=360,
        )
        hint_label.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        if show_select:
            button = ttk.Button(state, text=self.t("schedule_select"), command=self.bindings.select_file)
            button.grid(row=2, column=0, pady=(12, 0))

    def _render_items(self, items: tuple[ScheduleItem, ...]) -> None:
        row = 0
        for group_label, group_items in self._group_items(items):
            header = ttk.Label(self.list_container, text=group_label, style="CardTitle.TLabel")
            header.grid(row=row, column=0, sticky="w", pady=(8 if row else 0, 6))
            row += 1
            for item in group_items:
                item_card = self._build_item_card(self.list_container, item)
                item_card.grid(row=row, column=0, sticky="ew", pady=(0, 7))
                row += 1
        self.scroll_panel.bind_content_tree()
        self.scroll_panel.update_scroll_region()

    def _build_item_card(self, parent: ttk.Frame, item: ScheduleItem) -> tk.Frame:
        palette = self.theme()
        status_key, status_color = self._status_appearance(item)
        card = tk.Frame(
            parent,
            bg=palette.card_bg,
            highlightbackground=palette.border,
            highlightcolor=palette.border,
            highlightthickness=1,
            bd=0,
            padx=10,
            pady=8,
        )
        card.columnconfigure(1, weight=1)

        accent = tk.Frame(card, bg=status_color, width=4)
        accent.grid(row=0, column=0, rowspan=3, sticky="nsw", padx=(0, 10))

        title_color = palette.muted_text if item.status == SCHEDULE_STATUS_DONE else palette.text
        title = tk.Label(
            card,
            text=item.title,
            bg=palette.card_bg,
            fg=title_color,
            font=("Bahnschrift", 10, "bold"),
            anchor="w",
            justify="left",
            wraplength=390,
        )
        title.grid(row=0, column=1, sticky="ew")

        status = tk.Label(
            card,
            text=self.t(status_key),
            bg=palette.card_bg,
            fg=status_color,
            font=("Bahnschrift", 9, "bold"),
            anchor="e",
        )
        status.grid(row=0, column=2, sticky="e", padx=(10, 0))

        meta_parts = [item.item_id]
        if item.time_range:
            meta_parts.append(item.time_range)
        if item.is_done and item.date is not None:
            meta_parts.append(item.date.isoformat())
        if item.section and item.section not in meta_parts:
            meta_parts.append(item.section)
        if meta_parts:
            meta = tk.Label(
                card,
                text="  |  ".join(meta_parts),
                bg=palette.card_bg,
                fg=palette.muted_text,
                font=("Bahnschrift", 8),
                anchor="w",
            )
            meta.grid(row=1, column=1, columnspan=2, sticky="ew", pady=(3, 0))

        if item.description:
            description = tk.Label(
                card,
                text=item.description,
                bg=palette.card_bg,
                fg=palette.muted_text,
                font=("Bahnschrift", 9),
                anchor="w",
                justify="left",
                wraplength=480,
            )
            description.grid(row=2, column=1, columnspan=2, sticky="ew", pady=(5, 0))
        return card

    def _group_items(self, items: tuple[ScheduleItem, ...]) -> list[tuple[str, list[ScheduleItem]]]:
        active_by_date: dict[dt.date, list[ScheduleItem]] = defaultdict(list)
        unscheduled: list[ScheduleItem] = []
        completed: list[ScheduleItem] = []
        for item in items:
            if item.is_done:
                completed.append(item)
            elif item.date is None:
                unscheduled.append(item)
            else:
                active_by_date[item.date].append(item)

        groups: list[tuple[str, list[ScheduleItem]]] = []
        for item_date in sorted(active_by_date):
            date_items = active_by_date[item_date]
            if item_date < self.today:
                label = self.t("schedule_group_overdue", date=item_date.isoformat())
            elif item_date == self.today:
                label = self.t("schedule_group_today", date=item_date.isoformat())
            else:
                label = self.t("schedule_group_date", date=item_date.isoformat())
            groups.append((label, date_items))
        if unscheduled:
            groups.append((self.t("schedule_group_unscheduled"), unscheduled))
        if completed:
            completed.sort(key=lambda item: (item.date or dt.date.max, item.title.casefold()))
            groups.append((self.t("schedule_group_completed"), completed))
        return groups

    def _status_appearance(self, item: ScheduleItem) -> tuple[str, str]:
        palette = self.theme()
        if item.status == SCHEDULE_STATUS_DONE:
            return "schedule_status_done", palette.muted_text
        if item.status == SCHEDULE_STATUS_IN_PROGRESS:
            return "schedule_status_in_progress", palette.accent
        if item.status == SCHEDULE_STATUS_REVIEW:
            return "schedule_status_review", palette.success
        if item.status == SCHEDULE_STATUS_NEXT:
            return "schedule_status_next", palette.accent_alt
        if item.status == SCHEDULE_STATUS_HOLD:
            return "schedule_status_hold", palette.muted_text
        if item.date is not None and item.date < self.today:
            return "schedule_status_overdue", palette.danger
        return "schedule_status_planned", palette.accent_alt

    def _source_text(self) -> str:
        if self.source_path is None:
            return self.t("schedule_no_file")
        parts = self.source_path.parts
        if len(parts) >= 2:
            return f"{parts[-2]}/{parts[-1]}"
        return self.source_path.name

    def _set_summary(self, total: int, active: int, done: int) -> None:
        self.summary_vars["total"].set(f"{total:,}")
        self.summary_vars["active"].set(f"{active:,}")
        self.summary_vars["done"].set(f"{done:,}")
