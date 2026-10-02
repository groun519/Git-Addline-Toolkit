import sys
import threading
import time
import unittest
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1] / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from line_tracker_process import (
    CommandCancelledError,
    CommandTimeoutError,
    command_cancel_scope,
    run_command,
)


class CommandProcessTests(unittest.TestCase):
    def test_command_scope_rejects_work_after_cancellation(self) -> None:
        cancel_event = threading.Event()
        cancel_event.set()

        with command_cancel_scope(cancel_event):
            with self.assertRaises(CommandCancelledError):
                run_command([sys.executable, "-c", "print('should not run')"])

    def test_command_timeout_stops_long_running_process(self) -> None:
        started_at = time.monotonic()

        with self.assertRaises(CommandTimeoutError):
            run_command(
                [sys.executable, "-c", "import time; time.sleep(10)"],
                timeout_seconds=0.1,
            )

        self.assertLess(time.monotonic() - started_at, 3)

    def test_command_scope_stops_process_when_cancelled(self) -> None:
        cancel_event = threading.Event()
        timer = threading.Timer(0.1, cancel_event.set)
        started_at = time.monotonic()
        timer.start()
        try:
            with command_cancel_scope(cancel_event):
                with self.assertRaises(CommandCancelledError):
                    run_command(
                        [sys.executable, "-c", "import time; time.sleep(10)"],
                        timeout_seconds=5,
                    )
        finally:
            timer.cancel()

        self.assertLess(time.monotonic() - started_at, 3)

    def test_command_captures_utf8_output(self) -> None:
        result = run_command(
            [sys.executable, "-c", "print('Line Tracker')"],
            timeout_seconds=5,
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "Line Tracker")


if __name__ == "__main__":
    unittest.main()
