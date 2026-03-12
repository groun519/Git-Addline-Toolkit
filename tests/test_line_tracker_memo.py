from pathlib import Path
import sys
import unittest

APP_DIR = Path(__file__).resolve().parents[1] / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from line_tracker_memo import (
    MemoLabels,
    MemoState,
    coerce_saved_memo_text,
    move_memo_item_between_sections,
    normalize_loaded_memo_text,
    parse_memo_text,
    split_commit_message,
)


class MemoModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.labels = MemoLabels(
            template_title="[제목 입력]",
            done_label="DONE",
            todo_label="TODO",
        )

    def test_normalize_loaded_memo_text_adds_default_sections(self) -> None:
        normalized = normalize_loaded_memo_text("Todo Destroy 11", self.labels)

        self.assertEqual(
            normalized,
            "Todo Destroy 11\n\nDONE\n-\n\nTODO\n-\n-",
        )

    def test_parse_memo_text_splits_title_done_and_todo(self) -> None:
        state = parse_memo_text("Ship it\n\nDONE\n- setup\n\nTODO\n- docs\n- tests")

        self.assertEqual(state.title, "Ship it")
        self.assertEqual(state.done_items, ["setup"])
        self.assertEqual(state.todo_items, ["docs", "tests"])

    def test_coerce_saved_memo_text_migrates_legacy_items(self) -> None:
        normalized = coerce_saved_memo_text(
            None,
            "Legacy Title",
            [{"text": "done thing", "done": True}, {"text": "todo thing", "done": False}],
            "",
            "",
            self.labels,
        )

        self.assertEqual(
            normalized,
            "Legacy Title\n\nDONE\n- done thing\n\nTODO\n- todo thing",
        )

    def test_move_memo_item_between_sections_moves_requested_item(self) -> None:
        state = MemoState(
            title="Move test",
            done_items=["done one"],
            todo_items=["todo one", "todo two"],
        )

        moved_to_done = move_memo_item_between_sections(state, "todo", 1)
        moved_back = move_memo_item_between_sections(moved_to_done, "done", 0)

        self.assertEqual(moved_to_done.done_items, ["done one", "todo two"])
        self.assertEqual(moved_to_done.todo_items, ["todo one"])
        self.assertEqual(moved_back.done_items, ["todo two"])
        self.assertEqual(moved_back.todo_items, ["todo one", "done one"])

    def test_split_commit_message_returns_summary_and_description(self) -> None:
        summary, description = split_commit_message(
            MemoState(
                title="Ship release",
                done_items=["feature A"],
                todo_items=["docs"],
            ),
            self.labels,
        )

        self.assertEqual(summary, "Ship release")
        self.assertEqual(description, "DONE\n- feature A\n\nTODO\n- docs")
