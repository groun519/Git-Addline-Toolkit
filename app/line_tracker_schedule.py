from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


SCHEDULE_STATUS_PLANNED = "planned"
SCHEDULE_STATUS_IN_PROGRESS = "in_progress"
SCHEDULE_STATUS_REVIEW = "review"
SCHEDULE_STATUS_NEXT = "next"
SCHEDULE_STATUS_HOLD = "hold"
SCHEDULE_STATUS_DONE = "done"
SCHEDULE_STATUSES = {
    SCHEDULE_STATUS_PLANNED,
    SCHEDULE_STATUS_IN_PROGRESS,
    SCHEDULE_STATUS_REVIEW,
    SCHEDULE_STATUS_NEXT,
    SCHEDULE_STATUS_HOLD,
    SCHEDULE_STATUS_DONE,
}
DEFAULT_SCHEDULE_FILE_NAMES = ("SCHEDULE.md", "schedule.md")


@dataclass(frozen=True)
class ScheduleItem:
    item_id: str
    title: str
    date: dt.date | None = None
    description: str = ""
    status: str = SCHEDULE_STATUS_PLANNED
    time_range: str = ""
    section: str = ""
    source_start_line: int = field(default=-1, compare=False, repr=False)
    source_end_line: int = field(default=-1, compare=False, repr=False)

    def __post_init__(self) -> None:
        normalized_status = self.status if self.status in SCHEDULE_STATUSES else SCHEDULE_STATUS_PLANNED
        object.__setattr__(self, "status", normalized_status)

    @property
    def is_done(self) -> bool:
        return self.status == SCHEDULE_STATUS_DONE


@dataclass(frozen=True)
class ScheduleDocument:
    title: str
    items: tuple[ScheduleItem, ...] = ()
    source_path: Path | None = None

    @property
    def completed_count(self) -> int:
        return sum(item.is_done for item in self.items)

    @property
    def in_progress_count(self) -> int:
        return sum(item.status == SCHEDULE_STATUS_IN_PROGRESS for item in self.items)


class ScheduleParser(Protocol):
    def parse(self, text: str, source_path: Path) -> ScheduleDocument:
        ...


class ScheduleParseError(ValueError):
    def __init__(self, line_number: int, message: str) -> None:
        super().__init__(f"Line {line_number}: {message}")
        self.line_number = line_number


@dataclass
class _PendingScheduleItem:
    item_id: str
    status: str
    time_range: str
    title: str
    date: dt.date | None
    details: list[str]
    source_start_line: int
    source_end_line: int

    def build(self) -> ScheduleItem:
        return ScheduleItem(
            item_id=self.item_id,
            title=self.title,
            date=self.date,
            description="\n".join(self.details),
            status=self.status,
            time_range=self.time_range,
            source_start_line=self.source_start_line,
            source_end_line=self.source_end_line,
        )


class DirectiveScheduleParser:
    _day_re = re.compile(r"^@@DAY\s+(\d{4}-\d{2}-\d{2})$")
    _status_map = {
        "PLANNED": SCHEDULE_STATUS_PLANNED,
        "IN_PROGRESS": SCHEDULE_STATUS_IN_PROGRESS,
        "REVIEW": SCHEDULE_STATUS_REVIEW,
        "NEXT": SCHEDULE_STATUS_NEXT,
        "HOLD": SCHEDULE_STATUS_HOLD,
        "DONE": SCHEDULE_STATUS_DONE,
    }

    def parse(self, text: str, source_path: Path) -> ScheduleDocument:
        document_title = source_path.stem
        section_started = False
        current_date: dt.date | None = None
        pending: _PendingScheduleItem | None = None
        items: list[ScheduleItem] = []

        def flush_pending() -> None:
            nonlocal pending
            if pending is not None:
                items.append(pending.build())
                pending = None

        for line_number, raw_line in enumerate(text.splitlines(), start=1):
            line = raw_line.strip()
            if not line:
                continue

            if section_started and line.startswith("#"):
                flush_pending()
                break

            day_match = self._day_re.fullmatch(line)
            if day_match is not None:
                flush_pending()
                try:
                    current_date = dt.date.fromisoformat(day_match.group(1))
                except ValueError as exc:
                    raise ScheduleParseError(line_number, "invalid @@DAY date") from exc
                section_started = True
                continue

            if line == "@@BACKLOG":
                flush_pending()
                current_date = None
                section_started = True
                continue

            if line.startswith("@@"):
                directive = line.split(maxsplit=1)[0]
                raise ScheduleParseError(line_number, f"unknown or malformed directive: {directive}")

            if not section_started:
                if line.startswith("# "):
                    document_title = line[2:].strip() or document_title
                if not line.startswith("-") and line.count("|") == 3:
                    raise ScheduleParseError(line_number, "schedule item must follow @@DAY or @@BACKLOG")
                continue

            if line.startswith("-"):
                if pending is None:
                    raise ScheduleParseError(line_number, "detail must follow a schedule item")
                detail = line[1:].strip()
                if detail:
                    pending.details.append(detail)
                pending.source_end_line = line_number
                continue

            if line.count("|") == 3:
                if not section_started:
                    raise ScheduleParseError(line_number, "schedule item must follow @@DAY or @@BACKLOG")
                flush_pending()
                item_id, raw_status, time_range, title = (part.strip() for part in line.split("|", 3))
                if not item_id:
                    raise ScheduleParseError(line_number, "schedule item ID is empty")
                if not title:
                    raise ScheduleParseError(line_number, "schedule item title is empty")
                status_name = raw_status.upper()
                status = self._status_map.get(status_name)
                if status is None:
                    expected = ", ".join(self._status_map)
                    raise ScheduleParseError(
                        line_number,
                        f"unknown status '{raw_status}' (expected {expected})",
                    )
                pending = _PendingScheduleItem(
                    item_id=item_id,
                    status=status,
                    time_range="" if time_range == "-" else time_range,
                    title=title,
                    date=current_date,
                    details=[],
                    source_start_line=line_number - 1,
                    source_end_line=line_number,
                )
                continue

            if "|" in line:
                raise ScheduleParseError(line_number, "expected 'ID | STATUS | TIME | TITLE'")

            if pending is None:
                raise ScheduleParseError(line_number, "expected 'ID | STATUS | TIME | TITLE'")

            pending.details.append(line)
            pending.source_end_line = line_number

        flush_pending()
        return ScheduleDocument(
            title=document_title,
            items=tuple(items),
            source_path=source_path,
        )


def resolve_schedule_path(repo: Path, configured_path: str) -> Path | None:
    normalized = configured_path.strip()
    if normalized:
        candidate = Path(normalized).expanduser()
        if not candidate.is_absolute():
            candidate = repo / candidate
        return candidate.resolve(strict=False)

    for file_name in DEFAULT_SCHEDULE_FILE_NAMES:
        candidate = repo / file_name
        if candidate.is_file():
            return candidate.resolve()
    return None


def make_portable_schedule_path(repo: Path, selected_path: Path) -> str:
    resolved_repo = repo.resolve()
    resolved_path = selected_path.expanduser().resolve()
    try:
        return resolved_path.relative_to(resolved_repo).as_posix()
    except ValueError:
        return str(resolved_path)


def load_schedule_document(path: Path, parser: ScheduleParser) -> ScheduleDocument:
    text = path.read_text(encoding="utf-8-sig")
    return parser.parse(text, path)
