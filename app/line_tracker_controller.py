from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

from line_tracker import TrackerConfig
from line_tracker_process import command_cancel_scope
from line_tracker_refresh import RefreshSnapshot, build_refresh_snapshot


Dispatch = Callable[[Callable[[], None]], None]
SnapshotBuilder = Callable[[Path, str, TrackerConfig, int], RefreshSnapshot]
ThreadStarter = Callable[[Callable[[], None]], None]
RefreshSuccess = Callable[[int, RefreshSnapshot], None]
RefreshFailure = Callable[[int, str], None]


class RefreshCoordinator:
    def __init__(
        self,
        dispatch: Dispatch,
        *,
        snapshot_builder: SnapshotBuilder = build_refresh_snapshot,
        thread_starter: ThreadStarter | None = None,
    ) -> None:
        self._dispatch = dispatch
        self._snapshot_builder = snapshot_builder
        self._thread_starter = thread_starter or _start_daemon_thread
        self._lock = threading.Lock()
        self._next_request_id = 0
        self._active_request_id: int | None = None
        self._active_cancel_event: threading.Event | None = None

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._active_request_id is not None

    def start(
        self,
        *,
        repo: Path,
        author: str,
        config: TrackerConfig,
        graph_days: int,
        on_success: RefreshSuccess,
        on_failure: RefreshFailure,
    ) -> int | None:
        with self._lock:
            if self._active_request_id is not None:
                return None
            self._next_request_id += 1
            request_id = self._next_request_id
            self._active_request_id = request_id
            cancel_event = threading.Event()
            self._active_cancel_event = cancel_event

        def run() -> None:
            try:
                with command_cancel_scope(cancel_event):
                    snapshot = self._snapshot_builder(repo, author, config, graph_days)
            except Exception as exc:  # pragma: no cover - exercised through injected builders
                self._dispatch(
                    lambda error_message=str(exc): self._deliver_failure(
                        request_id,
                        error_message,
                        on_failure,
                    )
                )
                return
            self._dispatch(lambda: self._deliver_success(request_id, snapshot, on_success))

        try:
            self._thread_starter(run)
        except Exception:
            self._finish(request_id)
            raise
        return request_id

    def invalidate(self) -> None:
        with self._lock:
            if self._active_cancel_event is not None:
                self._active_cancel_event.set()
            self._next_request_id += 1
            self._active_request_id = None
            self._active_cancel_event = None

    def _deliver_success(
        self,
        request_id: int,
        snapshot: RefreshSnapshot,
        callback: RefreshSuccess,
    ) -> None:
        if self._finish(request_id):
            callback(request_id, snapshot)

    def _deliver_failure(
        self,
        request_id: int,
        error_message: str,
        callback: RefreshFailure,
    ) -> None:
        if self._finish(request_id):
            callback(request_id, error_message)

    def _finish(self, request_id: int) -> bool:
        with self._lock:
            if self._active_request_id != request_id:
                return False
            self._active_request_id = None
            self._active_cancel_event = None
            return True


def _start_daemon_thread(target: Callable[[], None]) -> None:
    threading.Thread(target=target, daemon=True).start()
