from __future__ import annotations

import json
import threading
from pathlib import Path

from line_tracker_io import write_text_atomic
from line_tracker_text import (
    classify_text_language,
    count_text_lines,
    is_probably_binary_path,
    order_language_totals,
)


WORKSPACE_INDEX_VERSION = 1
WORKSPACE_INDEX_MAX_REPOSITORIES = 12


class WorkspaceLineIndex:
    def __init__(self, cache_path: Path) -> None:
        self.cache_path = cache_path
        self._repositories: dict[str, dict[str, tuple[int, int, int]]] = {}
        self._loaded = False
        self._dirty = False
        self._revision = 0
        self._lock = threading.RLock()

    def summarize(self, repo: Path, paths: list[str]) -> dict[str, int]:
        totals: dict[str, int] = {}
        text_paths = [path for path in paths if path and not is_probably_binary_path(path)]
        for relative_path in text_paths:
            line_count = self.line_count(repo, relative_path)
            if line_count <= 0:
                continue
            language = classify_text_language(relative_path)
            totals[language] = totals.get(language, 0) + line_count
        self.retain(repo, text_paths)
        return order_language_totals(totals)

    def line_count(self, repo: Path, relative_path: str) -> int:
        self._load()
        repo_key = self._repo_key(repo)
        normalized_path = relative_path.replace("\\", "/")
        path = repo / relative_path
        try:
            stat = path.stat()
        except OSError:
            return 0
        signature = (stat.st_mtime_ns, stat.st_size)
        with self._lock:
            repository = self._repositories.setdefault(repo_key, {})
            cached = repository.get(normalized_path)
            if cached is not None and cached[:2] == signature:
                return cached[2]

        line_count = count_text_lines(path)
        with self._lock:
            self._touch_repository(repo_key)
            self._repositories[repo_key][normalized_path] = (*signature, line_count)
            self._mark_dirty()
        return line_count

    def retain(self, repo: Path, paths: list[str]) -> None:
        self._load()
        repo_key = self._repo_key(repo)
        retained = {path.replace("\\", "/") for path in paths}
        with self._lock:
            repository = self._repositories.get(repo_key)
            if repository is None:
                return
            removed = set(repository) - retained
            for relative_path in removed:
                del repository[relative_path]
            if removed:
                self._mark_dirty()

    def clear_repo(self, repo: Path) -> None:
        self._load()
        with self._lock:
            if self._repositories.pop(self._repo_key(repo), None) is not None:
                self._mark_dirty()

    def save(self) -> None:
        self._load()
        with self._lock:
            if not self._dirty:
                return
            revision = self._revision
            payload = {
                "version": WORKSPACE_INDEX_VERSION,
                "repositories": {
                    repo_key: {
                        relative_path: [mtime_ns, size, line_count]
                        for relative_path, (mtime_ns, size, line_count) in repository.items()
                    }
                    for repo_key, repository in self._repositories.items()
                },
            }
        try:
            write_text_atomic(
                self.cache_path,
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            )
        except OSError:
            return
        with self._lock:
            if self._revision == revision:
                self._dirty = False

    def _mark_dirty(self) -> None:
        self._dirty = True
        self._revision += 1

    def _load(self) -> None:
        with self._lock:
            if self._loaded:
                return
            self._loaded = True
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(payload, dict) or payload.get("version") != WORKSPACE_INDEX_VERSION:
            return
        repositories = payload.get("repositories")
        if not isinstance(repositories, dict):
            return

        loaded: dict[str, dict[str, tuple[int, int, int]]] = {}
        for repo_key, raw_repository in list(repositories.items())[-WORKSPACE_INDEX_MAX_REPOSITORIES:]:
            if not isinstance(repo_key, str) or not isinstance(raw_repository, dict):
                continue
            entries: dict[str, tuple[int, int, int]] = {}
            for relative_path, raw_entry in raw_repository.items():
                if not isinstance(relative_path, str) or not isinstance(raw_entry, list):
                    continue
                if len(raw_entry) != 3:
                    continue
                try:
                    entries[relative_path] = tuple(int(value) for value in raw_entry)
                except (TypeError, ValueError):
                    continue
            loaded[repo_key] = entries
        with self._lock:
            self._repositories.update(loaded)

    def _touch_repository(self, repo_key: str) -> None:
        repository = self._repositories.pop(repo_key, {})
        self._repositories[repo_key] = repository
        while len(self._repositories) > WORKSPACE_INDEX_MAX_REPOSITORIES:
            self._repositories.pop(next(iter(self._repositories)))

    @staticmethod
    def _repo_key(repo: Path) -> str:
        return str(repo.resolve()).casefold()
