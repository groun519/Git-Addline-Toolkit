from __future__ import annotations

from dataclasses import dataclass

DEFAULT_DONE_PLACEHOLDERS = 1
DEFAULT_TODO_PLACEHOLDERS = 2


@dataclass(frozen=True)
class MemoState:
    title: str
    done_items: list[str]
    todo_items: list[str]


@dataclass(frozen=True)
class MemoLabels:
    template_title: str
    done_label: str
    todo_label: str


def strip_bullet(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith(("-", "*", "•")):
        return cleaned[1:].lstrip()
    return cleaned


def normalize_section_header(text: str) -> str | None:
    cleaned = text.strip()
    while cleaned.startswith("#"):
        cleaned = cleaned[1:].lstrip()
    cleaned = cleaned.rstrip(":").strip()
    upper = cleaned.upper()
    if upper == "DONE":
        return "done"
    if upper == "TODO":
        return "todo"
    return None


def parse_memo_text(raw_text: str) -> MemoState:
    title = ""
    done_items: list[str] = []
    todo_items: list[str] = []
    current_section = "todo"

    for raw_line in raw_text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue

        section = normalize_section_header(stripped)
        if not title and section:
            current_section = section
            continue
        if not title:
            title = stripped
            continue
        if section:
            current_section = section
            continue

        text = strip_bullet(stripped)
        if not text:
            continue
        if current_section == "done":
            done_items.append(text)
        else:
            todo_items.append(text)

    return MemoState(
        title=title,
        done_items=done_items,
        todo_items=todo_items,
    )


def build_memo_text(
    memo_state: MemoState,
    labels: MemoLabels,
    *,
    include_placeholders: bool = False,
    done_placeholders: int = DEFAULT_DONE_PLACEHOLDERS,
    todo_placeholders: int = DEFAULT_TODO_PLACEHOLDERS,
) -> str:
    normalized_title = memo_state.title.strip()
    done_lines = [f"- {item.strip()}" for item in memo_state.done_items if item.strip()]
    todo_lines = [f"- {item.strip()}" for item in memo_state.todo_items if item.strip()]
    if include_placeholders and not done_lines:
        done_lines = ["-"] * done_placeholders
    if include_placeholders and not todo_lines:
        todo_lines = ["-"] * todo_placeholders

    parts: list[str] = []
    if normalized_title:
        parts.append(normalized_title)

    if normalized_title or done_lines or todo_lines:
        if parts:
            parts.append("")
        parts.append(labels.done_label)
        parts.extend(done_lines)
        parts.append("")
        parts.append(labels.todo_label)
        parts.extend(todo_lines)

    return "\n".join(parts).strip()


def default_memo_text(labels: MemoLabels) -> str:
    return build_memo_text(
        MemoState(
            title=labels.template_title,
            done_items=[],
            todo_items=[],
        ),
        labels,
        include_placeholders=True,
    )


def normalize_loaded_memo_text(raw_text: str, labels: MemoLabels) -> str:
    normalized_source = raw_text.rstrip("\n")
    memo_state = parse_memo_text(normalized_source)
    if not memo_state.title and not memo_state.done_items and not memo_state.todo_items:
        return default_memo_text(labels)
    return build_memo_text(memo_state, labels, include_placeholders=True)


def coerce_saved_memo_text(
    raw_memo_text: object,
    legacy_title: str,
    legacy_items_raw: object,
    legacy_done_raw: str,
    legacy_todo_raw: str,
    labels: MemoLabels,
) -> str:
    if isinstance(raw_memo_text, str) and raw_memo_text.strip():
        return normalize_loaded_memo_text(raw_memo_text, labels)

    done_items: list[str] = []
    todo_items: list[str] = []
    if isinstance(legacy_items_raw, list):
        for entry in legacy_items_raw:
            if isinstance(entry, dict):
                text = strip_bullet(str(entry.get("text", "")))
                if text:
                    if bool(entry.get("done")):
                        done_items.append(text)
                    else:
                        todo_items.append(text)
            elif isinstance(entry, str):
                text = strip_bullet(entry)
                if text:
                    todo_items.append(text)

    if not done_items and not todo_items:
        for line in legacy_done_raw.splitlines():
            text = strip_bullet(line)
            if text:
                done_items.append(text)
        for line in legacy_todo_raw.splitlines():
            text = strip_bullet(line)
            if text:
                todo_items.append(text)

    if not legacy_title and not done_items and not todo_items:
        return default_memo_text(labels)
    return build_memo_text(
        MemoState(
            title=legacy_title,
            done_items=done_items,
            todo_items=todo_items,
        ),
        labels,
        include_placeholders=True,
    )


def move_memo_item_between_sections(memo_state: MemoState, section: str, index: int) -> MemoState:
    done_items = list(memo_state.done_items)
    todo_items = list(memo_state.todo_items)
    if section == "done":
        if not 0 <= index < len(done_items):
            return memo_state
        todo_items.append(done_items.pop(index))
    else:
        if not 0 <= index < len(todo_items):
            return memo_state
        done_items.append(todo_items.pop(index))
    return MemoState(
        title=memo_state.title,
        done_items=done_items,
        todo_items=todo_items,
    )


def get_placeholder_titles(template_titles: list[str]) -> set[str]:
    return {title.strip() for title in template_titles if title.strip()}


def split_commit_message(memo_state: MemoState, labels: MemoLabels) -> tuple[str, str]:
    commit_text = build_memo_text(memo_state, labels)
    if not commit_text:
        return "", ""

    summary, separator, description = commit_text.partition("\n\n")
    if not separator:
        description = ""
    return summary.strip(), description.strip()
