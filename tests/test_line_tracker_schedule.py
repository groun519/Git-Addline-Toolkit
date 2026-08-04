import datetime as dt
import tempfile
import unittest
from pathlib import Path
import sys

APP_DIR = Path(__file__).resolve().parents[1] / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from line_tracker_schedule import (
    DirectiveScheduleParser,
    SCHEDULE_STATUS_DONE,
    SCHEDULE_STATUS_HOLD,
    SCHEDULE_STATUS_IN_PROGRESS,
    SCHEDULE_STATUS_NEXT,
    SCHEDULE_STATUS_PLANNED,
    SCHEDULE_STATUS_REVIEW,
    ScheduleParseError,
    load_schedule_document,
    make_portable_schedule_path,
    resolve_schedule_path,
)


class ScheduleTests(unittest.TestCase):
    def test_parser_ignores_document_preamble_and_supports_work_plan_statuses(self) -> None:
        document = DirectiveScheduleParser().parse(
            "\n".join(
                (
                    "# PROJECT-MA Work Plan",
                    "",
                    "This preamble documents the schedule format.",
                    "- Item rows use ID | STATUS | PERIOD | TITLE.",
                    "",
                    "@@DAY 2026-08-04",
                    "ITEM-001 | NEXT | 2026-08-02..2026-08-04 | Item Core",
                    "ITEM-002 | REVIEW | 2026-08-04 | Verify Item Core",
                    "@@BACKLOG",
                    "HOLD-001 | HOLD | - | Deferred Polish",
                    "",
                    "## Completed",
                    "| Commit | Scope |",
                    "|---|---|",
                    "| abc123 | Previous work |",
                )
            ),
            Path("work-plan.md"),
        )

        self.assertEqual(document.title, "PROJECT-MA Work Plan")
        self.assertEqual(
            [item.status for item in document.items],
            [SCHEDULE_STATUS_NEXT, SCHEDULE_STATUS_REVIEW, SCHEDULE_STATUS_HOLD],
        )
        self.assertEqual(document.items[0].time_range, "2026-08-02..2026-08-04")
        self.assertEqual(document.items[-1].time_range, "")

    def test_directive_parser_builds_dated_and_backlog_items(self) -> None:
        source = Path("SCHEDULE.md")
        document = DirectiveScheduleParser().parse(
            "\n".join(
                (
                    "@@DAY 2026-08-01",
                    "ITEM-001 | IN_PROGRESS | 18:00~22:00 | Inventory Domain Contract",
                    "- Define the public contract",
                    "- Verify repository | service | UI | test boundaries",
                    "",
                    "ITEM-002 | PLANNED | 22:00~23:00 | Item Core",
                    "- Add the core model",
                    "",
                    "@@DAY 2026-08-02",
                    "ITEM-003 | DONE | 10:00~15:00 | Integration Check",
                    "- Complete the smoke test",
                    "",
                    "@@BACKLOG",
                    "ITEM-004 | PLANNED | | Deferred Polish",
                    "- Revisit after the core work",
                )
            ),
            source,
        )

        self.assertEqual(document.title, "SCHEDULE")
        self.assertEqual(
            [item.item_id for item in document.items],
            ["ITEM-001", "ITEM-002", "ITEM-003", "ITEM-004"],
        )
        self.assertEqual(
            [item.date for item in document.items],
            [dt.date(2026, 8, 1), dt.date(2026, 8, 1), dt.date(2026, 8, 2), None],
        )
        self.assertEqual(
            [item.status for item in document.items],
            [
                SCHEDULE_STATUS_IN_PROGRESS,
                SCHEDULE_STATUS_PLANNED,
                SCHEDULE_STATUS_DONE,
                SCHEDULE_STATUS_PLANNED,
            ],
        )
        self.assertEqual(document.items[0].time_range, "18:00~22:00")
        self.assertEqual(
            document.items[0].description,
            "Define the public contract\nVerify repository | service | UI | test boundaries",
        )
        self.assertEqual(document.items[-1].description, "Revisit after the core work")
        self.assertEqual(document.completed_count, 1)
        self.assertEqual(document.in_progress_count, 1)

    def test_parser_reports_invalid_content_with_line_number(self) -> None:
        parser = DirectiveScheduleParser()
        invalid_cases = (
            ("ITEM-001 | PLANNED | 10:00~11:00 | Orphan", 1),
            ("@@DAY 2026-02-30", 1),
            ("@@DAY 2026-08-01\nITEM-001 | BLOCKED | 10:00~11:00 | Unknown", 2),
            ("@@DAY 2026-08-01\nITEM-001 | PLANNED | Missing field", 2),
            (
                "@@DAY 2026-08-01\n"
                "ITEM-001 | PLANNED | 10:00~11:00 | Valid\n"
                "ITEM-002 | PLANNED | Missing field",
                3,
            ),
        )

        for text, expected_line in invalid_cases:
            with self.subTest(text=text):
                with self.assertRaises(ScheduleParseError) as raised:
                    parser.parse(text, Path("SCHEDULE.md"))
                self.assertEqual(raised.exception.line_number, expected_line)

    def test_loader_accepts_utf8_bom(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            schedule_path = Path(tmp_dir) / "SCHEDULE.md"
            schedule_path.write_text(
                "@@DAY 2026-08-01\nITEM-001 | PLANNED | 10:00~12:00 | 구현\n- 상세 내용",
                encoding="utf-8-sig",
            )

            document = load_schedule_document(schedule_path, DirectiveScheduleParser())

        self.assertEqual(document.items[0].title, "구현")
        self.assertEqual(document.items[0].description, "상세 내용")

    def test_resolve_schedule_path_supports_relative_absolute_and_auto_detected_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = Path(tmp_dir)
            auto_path = repo / "SCHEDULE.md"
            auto_path.write_text("@@BACKLOG", encoding="utf-8")
            external_path = repo.parent / "external-schedule.md"

            self.assertEqual(resolve_schedule_path(repo, ""), auto_path.resolve())
            self.assertEqual(resolve_schedule_path(repo, "docs/plan.md"), (repo / "docs/plan.md").resolve())
            self.assertEqual(resolve_schedule_path(repo, str(external_path)), external_path.resolve())

    def test_make_portable_schedule_path_uses_repo_relative_paths_when_possible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = Path(tmp_dir)
            nested = repo / "docs" / "plan.md"

            self.assertEqual(make_portable_schedule_path(repo, nested), "docs/plan.md")


if __name__ == "__main__":
    unittest.main()
