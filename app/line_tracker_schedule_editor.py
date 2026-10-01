from __future__ import annotations

import codecs
import datetime as dt
import os
import tempfile
from pathlib import Path

from line_tracker_schedule import (
    SCHEDULE_STATUSES,
    DirectiveScheduleParser,
    ScheduleItem,
)


class ScheduleEditError(ValueError):
    pass


_STATUS_NAMES = {
    "planned": "PLANNED",
    "in_progress": "IN_PROGRESS",
    "review": "REVIEW",
    "next": "NEXT",
    "hold": "HOLD",
    "done": "DONE",
}


class ScheduleDocumentEditor:
    def __init__(self, parser: DirectiveScheduleParser | None = None) -> None:
        self.parser = parser or DirectiveScheduleParser()

    def update_item(self, path: Path, target: ScheduleItem, replacement: ScheduleItem) -> None:
        self._validate_item(replacement)
        source = _EditableSource.read(path)
        current = self._resolve_current_item(source, path, target)
        lines = source.lines
        replacement_lines = self._serialize_item(replacement)

        if current.date == replacement.date:
            lines[current.source_start_line : current.source_end_line] = replacement_lines
        else:
            del lines[current.source_start_line : current.source_end_line]
            self._insert_into_section(lines, replacement.date, replacement_lines)
        source.write(path)

    def delete_item(self, path: Path, target: ScheduleItem) -> None:
        source = _EditableSource.read(path)
        current = self._resolve_current_item(source, path, target)
        start = current.source_start_line
        end = current.source_end_line

        if end < len(source.lines) and not source.lines[end].strip():
            end += 1
        elif start > 0 and not source.lines[start - 1].strip():
            start -= 1
        del source.lines[start:end]
        source.write(path)

    def _resolve_current_item(self, source: _EditableSource, path: Path, target: ScheduleItem) -> ScheduleItem:
        document = self.parser.parse(source.text, path)
        id_matches = [item for item in document.items if item.item_id == target.item_id]
        exact_matches = [item for item in id_matches if self._same_content(item, target)]
        if len(exact_matches) == 1:
            return exact_matches[0]

        line_matches = [item for item in exact_matches if item.source_start_line == target.source_start_line]
        if len(line_matches) == 1:
            return line_matches[0]
        if not id_matches:
            raise ScheduleEditError("The schedule item no longer exists in the file.")
        if len(id_matches) == 1:
            raise ScheduleEditError("The schedule item changed outside Line Tracker. Reload and try again.")
        raise ScheduleEditError(f"Schedule item ID '{target.item_id}' is duplicated and cannot be edited safely.")

    @staticmethod
    def _same_content(left: ScheduleItem, right: ScheduleItem) -> bool:
        return (
            left.title,
            left.date,
            left.description,
            left.status,
            left.time_range,
        ) == (
            right.title,
            right.date,
            right.description,
            right.status,
            right.time_range,
        )

    @staticmethod
    def _validate_item(item: ScheduleItem) -> None:
        if not item.item_id.strip():
            raise ScheduleEditError("Schedule item ID is required.")
        if "|" in item.item_id:
            raise ScheduleEditError("Schedule item ID cannot contain '|'.")
        if item.status not in SCHEDULE_STATUSES:
            raise ScheduleEditError("Schedule item status is invalid.")
        if not item.title.strip():
            raise ScheduleEditError("Schedule item title is required.")
        if "|" in item.time_range:
            raise ScheduleEditError("Schedule item time cannot contain '|'.")

    @staticmethod
    def _serialize_item(item: ScheduleItem) -> list[str]:
        status = _STATUS_NAMES[item.status]
        time_range = item.time_range.strip() or "-"
        lines = [f"{item.item_id.strip()} | {status} | {time_range} | {item.title.strip()}"]
        lines.extend(f"- {detail.strip()}" for detail in item.description.splitlines() if detail.strip())
        return lines

    @staticmethod
    def _insert_into_section(lines: list[str], item_date: dt.date | None, item_lines: list[str]) -> None:
        directive = "@@BACKLOG" if item_date is None else f"@@DAY {item_date.isoformat()}"
        section_start = next((index for index, line in enumerate(lines) if line.strip() == directive), None)
        if section_start is None:
            insertion = ScheduleDocumentEditor._schedule_end(lines)
            new_section = [directive, *item_lines]
            if insertion > 0 and lines[insertion - 1].strip():
                new_section.insert(0, "")
            if insertion < len(lines) and lines[insertion].strip():
                new_section.append("")
            lines[insertion:insertion] = new_section
            return

        insertion = len(lines)
        for index in range(section_start + 1, len(lines)):
            stripped = lines[index].strip()
            if stripped.startswith("@@") or stripped.startswith("#"):
                insertion = index
                break
        while insertion > section_start + 1 and not lines[insertion - 1].strip():
            insertion -= 1
        addition = list(item_lines)
        if insertion > section_start + 1:
            addition.insert(0, "")
        if insertion < len(lines) and lines[insertion].strip():
            addition.append("")
        lines[insertion:insertion] = addition

    @staticmethod
    def _schedule_end(lines: list[str]) -> int:
        schedule_started = False
        for index, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("@@"):
                schedule_started = True
            elif schedule_started and stripped.startswith("#"):
                return index
        return len(lines)


class _EditableSource:
    def __init__(self, text: str, *, newline: str, has_bom: bool, final_newline: bool) -> None:
        self.text = text
        self.lines = text.splitlines()
        self.newline = newline
        self.has_bom = has_bom
        self.final_newline = final_newline

    @classmethod
    def read(cls, path: Path) -> _EditableSource:
        raw = path.read_bytes()
        has_bom = raw.startswith(codecs.BOM_UTF8)
        payload = raw[len(codecs.BOM_UTF8) :] if has_bom else raw
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ScheduleEditError("The schedule file is not valid UTF-8.") from exc
        newline = "\r\n" if "\r\n" in text else "\n"
        return cls(
            text,
            newline=newline,
            has_bom=has_bom,
            final_newline=text.endswith(("\n", "\r")),
        )

    def write(self, path: Path) -> None:
        rendered = self.newline.join(self.lines)
        if self.final_newline:
            rendered += self.newline
        payload = rendered.encode("utf-8")
        if self.has_bom:
            payload = codecs.BOM_UTF8 + payload

        mode = path.stat().st_mode
        temporary_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=f".{path.name}.",
                suffix=".tmp",
                dir=path.parent,
                delete=False,
            ) as temporary:
                temporary.write(payload)
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_path = temporary.name
            os.chmod(temporary_path, mode)
            os.replace(temporary_path, path)
        finally:
            if temporary_path is not None and os.path.exists(temporary_path):
                os.unlink(temporary_path)
