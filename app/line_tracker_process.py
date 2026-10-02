from __future__ import annotations

import os
import subprocess
import threading
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path


DEFAULT_COMMAND_TIMEOUT_SECONDS = 180.0
_POLL_INTERVAL_SECONDS = 0.1
_CONTEXT = threading.local()


class CommandCancelledError(RuntimeError):
    pass


class CommandTimeoutError(RuntimeError):
    pass


@contextmanager
def command_cancel_scope(cancel_event: threading.Event) -> Iterator[None]:
    previous = getattr(_CONTEXT, "cancel_event", None)
    _CONTEXT.cancel_event = cancel_event
    try:
        yield
    finally:
        if previous is None:
            try:
                del _CONTEXT.cancel_event
            except AttributeError:
                pass
        else:
            _CONTEXT.cancel_event = previous


def raise_if_command_cancelled() -> None:
    cancel_event = _current_cancel_event()
    if cancel_event is not None and cancel_event.is_set():
        raise CommandCancelledError("Git operation cancelled")


def run_command(
    args: Sequence[str],
    *,
    cwd: Path | None = None,
    timeout_seconds: float | None = None,
) -> subprocess.CompletedProcess[str]:
    raise_if_command_cancelled()
    timeout = _resolve_timeout(timeout_seconds)
    started_at = time.monotonic()
    process = subprocess.Popen(
        list(args),
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    while True:
        try:
            raise_if_command_cancelled()
        except CommandCancelledError:
            _stop_process(process)
            raise

        remaining = timeout - (time.monotonic() - started_at)
        if remaining <= 0:
            _stop_process(process)
            raise CommandTimeoutError(
                f"Git operation exceeded {timeout:g} seconds: {_format_command(args)}"
            )
        try:
            stdout, stderr = process.communicate(timeout=min(_POLL_INTERVAL_SECONDS, remaining))
            return subprocess.CompletedProcess(list(args), process.returncode, stdout, stderr)
        except subprocess.TimeoutExpired:
            continue


def _current_cancel_event() -> threading.Event | None:
    value = getattr(_CONTEXT, "cancel_event", None)
    return value if isinstance(value, threading.Event) else None


def _resolve_timeout(timeout_seconds: float | None) -> float:
    if timeout_seconds is not None:
        return max(float(timeout_seconds), 0.01)
    raw_value = os.environ.get("LINE_TRACKER_GIT_TIMEOUT_SECONDS", "").strip()
    if raw_value:
        try:
            return max(float(raw_value), 0.01)
        except ValueError:
            pass
    return DEFAULT_COMMAND_TIMEOUT_SECONDS


def _stop_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is None:
        process.kill()
    try:
        process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()


def _format_command(args: Sequence[str]) -> str:
    return " ".join(str(value) for value in args)
