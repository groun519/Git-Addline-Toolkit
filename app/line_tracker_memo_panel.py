from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk
from typing import Callable

from line_tracker_memo import (
    MemoLabels,
    build_memo_text,
    move_memo_item_between_sections,
    normalize_loaded_memo_text,
    parse_memo_text,
    split_commit_message,
)
from line_tracker_theme import ThemePalette


@dataclass(frozen=True)
class MemoPanelBindings:
    root: tk.Misc
    translate: Callable[[str], str]
    get_theme: Callable[[], ThemePalette]
    get_labels: Callable[[], MemoLabels]
    get_placeholder_titles: Callable[[], set[str]]
    save_settings: Callable[[], None]
    copy_to_clipboard: Callable[[str, str], None]
    show_error: Callable[[str], None]
    font_mono: tuple[object, ...]
    scrollbar_style: str


class MemoPanel:
    def __init__(self, bindings: MemoPanelBindings, initial_text: str) -> None:
        self.bindings = bindings
        self.memo_text_value = initial_text.rstrip("\n")
        self.memo_autosave_job: str | None = None
        self.memo_widget_updating = False
        self.preview_title_wraplength = 300
        self.preview_item_wraplength = 250

    def t(self, key: str) -> str:
        return self.bindings.translate(key)

    def theme(self) -> ThemePalette:
        return self.bindings.get_theme()

    def labels(self) -> MemoLabels:
        return self.bindings.get_labels()

    def build(self, parent: ttk.Frame) -> None:
        self.note_editor_label = ttk.Label(parent, text=self.t("memo_editor"), style="CardLabel.TLabel")
        self.note_editor_label.grid(row=0, column=0, sticky="w", pady=(2, 0))

        editor_frame = ttk.Frame(parent, style="CardInner.TFrame")
        editor_frame.grid(row=1, column=0, sticky="ew", pady=(4, 4))
        editor_frame.columnconfigure(0, weight=1)

        palette = self.theme()
        self.memo_text_widget = tk.Text(
            editor_frame,
            width=1,
            height=8,
            wrap="word",
            bg=palette.card_bg,
            fg=palette.text,
            insertbackground=palette.text,
            highlightthickness=1,
            highlightbackground=palette.border,
            highlightcolor=palette.accent,
            relief="flat",
            font=self.bindings.font_mono,
            undo=True,
        )
        self.memo_text_widget.grid(row=0, column=0, sticky="ew")
        self.memo_text_widget.bind("<<Modified>>", self.on_memo_text_modified)
        self.memo_text_widget.bind("<FocusOut>", self.on_memo_text_focus_out)

        self.memo_text_scroll = ttk.Scrollbar(
            editor_frame,
            orient="vertical",
            command=self.memo_text_widget.yview,
            style=self.bindings.scrollbar_style,
        )
        self.memo_text_scroll.grid(row=0, column=1, sticky="ns", padx=(6, 0))
        self.memo_text_widget.configure(yscrollcommand=self.memo_text_scroll.set)
        self._bind_vertical_mousewheel(self.memo_text_widget, self.memo_text_widget)

        self.note_hint_label = ttk.Label(parent, text=self.t("memo_hint"), style="CardLabel.TLabel")
        self.note_hint_label.grid(row=2, column=0, sticky="w", pady=(2, 8))

        self.note_preview_label = ttk.Label(parent, text=self.t("memo_preview"), style="CardLabel.TLabel")
        self.note_preview_label.grid(row=3, column=0, sticky="w", pady=(2, 0))

        preview_frame = ttk.Frame(parent, style="CardInner.TFrame")
        preview_frame.grid(row=4, column=0, sticky="ew", pady=(4, 8))
        preview_frame.columnconfigure(0, weight=1)

        self.memo_preview_canvas = tk.Canvas(
            preview_frame,
            height=180,
            bg=palette.card_bg,
            highlightthickness=1,
            highlightbackground=palette.border,
        )
        self.memo_preview_canvas.grid(row=0, column=0, sticky="ew")

        self.memo_preview_scroll = ttk.Scrollbar(
            preview_frame,
            orient="vertical",
            command=self.memo_preview_canvas.yview,
            style=self.bindings.scrollbar_style,
        )
        self.memo_preview_scroll.grid(row=0, column=1, sticky="ns", padx=(6, 0))
        self.memo_preview_canvas.configure(yscrollcommand=self.memo_preview_scroll.set)

        self.memo_preview_inner = ttk.Frame(self.memo_preview_canvas, style="CardInner.TFrame")
        self.memo_preview_window = self.memo_preview_canvas.create_window(
            (0, 0),
            window=self.memo_preview_inner,
            anchor="nw",
        )
        self.memo_preview_inner.bind("<Configure>", self._on_memo_preview_configure)
        self.memo_preview_canvas.bind("<Configure>", self._on_memo_preview_canvas_configure)
        self._bind_vertical_mousewheel(self.memo_preview_canvas, self.memo_preview_canvas)
        self._bind_vertical_mousewheel(self.memo_preview_inner, self.memo_preview_canvas)

        note_actions = ttk.Frame(parent, style="CardInner.TFrame")
        note_actions.grid(row=5, column=0, sticky="e")
        self.copy_summary_button = ttk.Button(
            note_actions,
            text=self.t("copy_summary"),
            command=self.copy_summary,
        )
        self.copy_summary_button.grid(row=0, column=0, sticky="e")
        self.copy_description_button = ttk.Button(
            note_actions,
            text=self.t("copy_description"),
            command=self.copy_description,
        )
        self.copy_description_button.grid(row=0, column=1, sticky="e", padx=(8, 0))

        self.set_text(self.memo_text_value)

    def apply_language(self) -> None:
        if not hasattr(self, "note_editor_label"):
            return
        self.note_editor_label.configure(text=self.t("memo_editor"))
        self.note_hint_label.configure(text=self.t("memo_hint"))
        self.note_preview_label.configure(text=self.t("memo_preview"))
        self.copy_summary_button.configure(text=self.t("copy_summary"))
        self.copy_description_button.configure(text=self.t("copy_description"))
        self.refresh_preview()

    def apply_theme(self) -> None:
        if not hasattr(self, "memo_text_widget"):
            return
        palette = self.theme()
        self.memo_text_widget.configure(
            bg=palette.card_bg,
            fg=palette.text,
            insertbackground=palette.text,
            highlightbackground=palette.border,
            highlightcolor=palette.accent,
        )
        self.memo_preview_canvas.configure(bg=palette.card_bg, highlightbackground=palette.border)

    def set_panel_width_hint(self, panel_width: int) -> None:
        safe_width = max(220, int(panel_width))
        self.preview_title_wraplength = max(160, safe_width - 80)
        self.preview_item_wraplength = max(140, safe_width - 130)
        if hasattr(self, "memo_preview_inner"):
            self.refresh_preview()

    def get_text(self) -> str:
        if hasattr(self, "memo_text_widget"):
            self.memo_text_value = self.memo_text_widget.get("1.0", "end-1c").rstrip("\n")
        return self.memo_text_value

    def set_text(self, raw_text: str, *, save: bool = False) -> None:
        self.memo_text_value = raw_text.rstrip("\n")
        if save and self.memo_autosave_job:
            self.bindings.root.after_cancel(self.memo_autosave_job)
            self.memo_autosave_job = None
        if hasattr(self, "memo_text_widget"):
            focus_widget = self.bindings.root.focus_get()
            had_focus = focus_widget == self.memo_text_widget
            insert_index = self.memo_text_widget.index("insert")
            yview = self.memo_text_widget.yview()
            self.memo_widget_updating = True
            self.memo_text_widget.delete("1.0", "end")
            if self.memo_text_value:
                self.memo_text_widget.insert("1.0", self.memo_text_value)
            self.memo_text_widget.edit_modified(False)
            self.memo_widget_updating = False
            try:
                self.memo_text_widget.mark_set("insert", insert_index)
            except tk.TclError:
                self.memo_text_widget.mark_set("insert", "end-1c")
            if yview:
                self.memo_text_widget.yview_moveto(yview[0])
            if had_focus:
                self.memo_text_widget.focus_set()
        self.refresh_preview()
        if save:
            self.bindings.save_settings()

    def on_memo_text_modified(self, _: tk.Event | None = None) -> None:
        if self.memo_widget_updating or not hasattr(self, "memo_text_widget"):
            return
        if not self.memo_text_widget.edit_modified():
            return
        self.memo_text_widget.edit_modified(False)
        self.memo_text_value = self.get_text()
        self.refresh_preview()
        if self.memo_autosave_job:
            self.bindings.root.after_cancel(self.memo_autosave_job)
        self.memo_autosave_job = self.bindings.root.after(400, self._memo_autosave)

    def on_memo_text_focus_out(self, _: tk.Event | None = None) -> None:
        if self.memo_widget_updating:
            return
        self.normalize_text(save=True)

    def _memo_autosave(self) -> None:
        self.memo_autosave_job = None
        self.normalize_text(save=True)

    def normalize_text(self, *, save: bool) -> None:
        normalized_text = normalize_loaded_memo_text(self.get_text(), self.labels())
        if normalized_text != self.memo_text_value or normalized_text != self.get_text():
            self.set_text(normalized_text, save=save)
            return
        self.memo_text_value = normalized_text
        if save:
            self.bindings.save_settings()

    def get_summary_and_description(self, *, require_real_title: bool) -> tuple[str, str]:
        memo_state = parse_memo_text(self.get_text())
        placeholder_titles = self.bindings.get_placeholder_titles()
        if require_real_title and (not memo_state.title or memo_state.title in placeholder_titles):
            raise ValueError(self.t("error_need_title"))
        return split_commit_message(memo_state, self.labels())

    def copy_summary(self) -> None:
        try:
            summary, _ = self.get_summary_and_description(require_real_title=True)
        except ValueError as exc:
            self.bindings.show_error(str(exc))
            return
        self.bindings.copy_to_clipboard(summary, "status_summary_copied")

    def copy_description(self) -> None:
        try:
            _, description = self.get_summary_and_description(require_real_title=True)
        except ValueError as exc:
            self.bindings.show_error(str(exc))
            return
        self.bindings.copy_to_clipboard(description, "status_description_copied")

    @staticmethod
    def _normalize_mousewheel_delta(event: tk.Event) -> int:
        delta = int(getattr(event, "delta", 0) or 0)
        if delta:
            steps = delta // 120 if abs(delta) >= 120 else (1 if delta > 0 else -1)
            return -steps
        button_num = int(getattr(event, "num", 0) or 0)
        if button_num == 4:
            return -1
        if button_num == 5:
            return 1
        return 0

    def _bind_vertical_mousewheel(self, widget: tk.Misc, target: tk.Misc) -> None:
        widget.bind("<MouseWheel>", lambda event, scroll_target=target: self._on_mousewheel(event, scroll_target), add="+")
        widget.bind("<Button-4>", lambda event, scroll_target=target: self._on_mousewheel(event, scroll_target), add="+")
        widget.bind("<Button-5>", lambda event, scroll_target=target: self._on_mousewheel(event, scroll_target), add="+")

    def _on_mousewheel(self, event: tk.Event, target: tk.Misc) -> str | None:
        delta = self._normalize_mousewheel_delta(event)
        if delta == 0:
            return None
        target.yview_scroll(delta, "units")
        return "break"

    def _on_memo_preview_configure(self, _: tk.Event) -> None:
        if hasattr(self, "memo_preview_canvas"):
            self.memo_preview_canvas.configure(scrollregion=self.memo_preview_canvas.bbox("all"))

    def _on_memo_preview_canvas_configure(self, event: tk.Event) -> None:
        if hasattr(self, "memo_preview_canvas") and hasattr(self, "memo_preview_window"):
            self.memo_preview_canvas.itemconfigure(self.memo_preview_window, width=event.width)

    def refresh_preview(self) -> None:
        if not hasattr(self, "memo_preview_inner"):
            return

        for child in self.memo_preview_inner.winfo_children():
            child.destroy()
        self.memo_preview_inner.columnconfigure(0, weight=1)

        memo_state = parse_memo_text(self.get_text())
        row_index = 0

        title_label = ttk.Label(self.memo_preview_inner, text=self.t("memo_title"), style="CardLabel.TLabel")
        title_label.grid(row=row_index, column=0, sticky="w")
        self._bind_vertical_mousewheel(title_label, self.memo_preview_canvas)
        row_index += 1

        title_value = memo_state.title if memo_state.title else self.t("memo_empty")
        title_value_label = ttk.Label(
            self.memo_preview_inner,
            text=title_value,
            style="CardTitle.TLabel",
            wraplength=self.preview_title_wraplength,
            justify="left",
        )
        title_value_label.grid(row=row_index, column=0, sticky="ew", pady=(4, 0))
        self._bind_vertical_mousewheel(title_value_label, self.memo_preview_canvas)
        row_index += 1

        row_index = self._render_section(self.memo_preview_inner, row_index, "done", memo_state.done_items)
        self._render_section(self.memo_preview_inner, row_index, "todo", memo_state.todo_items)

    def _render_section(
        self,
        parent: ttk.Frame,
        row_index: int,
        section: str,
        items: list[str],
    ) -> int:
        heading = ttk.Label(parent, text=self.t(section), style="CardLabel.TLabel")
        heading.grid(row=row_index, column=0, sticky="w", pady=(12, 0))
        self._bind_vertical_mousewheel(heading, self.memo_preview_canvas)
        row_index += 1

        if not items:
            empty_label = ttk.Label(parent, text=self.t("memo_empty"), style="CardLabel.TLabel")
            empty_label.grid(row=row_index, column=0, sticky="w", pady=(4, 0))
            self._bind_vertical_mousewheel(empty_label, self.memo_preview_canvas)
            return row_index + 1

        button_key = "move_to_todo" if section == "done" else "move_to_done"
        for idx, item_text in enumerate(items):
            item_row = ttk.Frame(parent, style="CardInner.TFrame")
            item_row.grid(row=row_index, column=0, sticky="ew", pady=(4, 0))
            item_row.columnconfigure(0, weight=1)
            self._bind_vertical_mousewheel(item_row, self.memo_preview_canvas)

            item_label = ttk.Label(
                item_row,
                text=f"- {item_text}",
                style="CardTitle.TLabel",
                wraplength=self.preview_item_wraplength,
                justify="left",
            )
            item_label.grid(row=0, column=0, sticky="w")
            self._bind_vertical_mousewheel(item_label, self.memo_preview_canvas)

            move_button = ttk.Button(
                item_row,
                text=self.t(button_key),
                command=lambda s=section, i=idx: self.move_item(s, i),
            )
            move_button.grid(row=0, column=1, sticky="e", padx=(8, 0))
            self._bind_vertical_mousewheel(move_button, self.memo_preview_canvas)
            row_index += 1

        return row_index

    def move_item(self, section: str, index: int) -> None:
        memo_state = parse_memo_text(self.get_text())
        next_state = move_memo_item_between_sections(memo_state, section, index)
        if next_state == memo_state:
            return
        self.set_text(
            build_memo_text(
                next_state,
                self.labels(),
                include_placeholders=True,
            ),
            save=True,
        )
