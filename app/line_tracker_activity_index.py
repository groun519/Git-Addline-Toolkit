from __future__ import annotations

import datetime as dt
import json
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from line_tracker_io import write_text_atomic
from line_tracker_text import classify_text_language, is_probably_binary_path


ACTIVITY_INDEX_VERSION = 2
ACTIVITY_INDEX_MAX_REPOSITORIES = 8
ACTIVITY_FETCH_COMMAND_LIMIT = 16_000

GitRunner = Callable[[Path, list[str]], str]


@dataclass(frozen=True)
class CommitActivity:
    day: dt.date
    additions: int
    deletions: int
    languages: dict[str, int]
    author_name: str = ""
    author_email: str = ""


class CommitActivityIndex:
    def __init__(self, cache_path: Path) -> None:
        self.cache_path = cache_path
        self._repositories: dict[str, dict[str, CommitActivity]] = {}
        self._loaded = False
        self._dirty = False
        self._revision = 0
        self._lock = threading.RLock()

    def activity_for_refs(
        self,
        repo: Path,
        refs: tuple[str, ...],
        *,
        exclude_ref: str | None,
        run_git: GitRunner,
    ) -> dict[str, CommitActivity]:
        refs = tuple(dict.fromkeys(ref for ref in refs if ref))
        if not refs:
            return {}
        self._load()
        repo_key = self._repo_key(repo)
        with self._lock:
            repository = self._repositories.setdefault(repo_key, {})
            bootstrap = not repository

        if bootstrap:
            args = [
                "log",
                "--date=short",
                "--format=@@COMMIT@@%H%x09%ad%x09%an%x09%ae",
                "--numstat",
                "--no-renames",
                *refs,
            ]
            if exclude_ref:
                args.extend(["--not", exclude_ref])
            fetched = self._parse_activity(run_git(repo, args))
            with self._lock:
                self._touch_repository(repo_key)
                self._repositories[repo_key].update(fetched)
                if fetched:
                    self._mark_dirty()
            return fetched

        rev_list_args = ["rev-list", *refs]
        if exclude_ref:
            rev_list_args.extend(["--not", exclude_ref])
        commit_hashes = tuple(
            commit_hash.strip()
            for commit_hash in run_git(repo, rev_list_args).splitlines()
            if commit_hash.strip()
        )
        with self._lock:
            repository = self._repositories[repo_key]
            missing = [commit_hash for commit_hash in commit_hashes if commit_hash not in repository]

        if missing:
            fetched: dict[str, CommitActivity] = {}
            for chunk in self._command_chunks(missing):
                fetched.update(self._parse_activity(run_git(repo, self._log_args(chunk))))
            with self._lock:
                self._touch_repository(repo_key)
                self._repositories[repo_key].update(fetched)
                if fetched:
                    self._mark_dirty()

        with self._lock:
            repository = self._repositories.get(repo_key, {})
            return {
                commit_hash: repository[commit_hash]
                for commit_hash in commit_hashes
                if commit_hash in repository
            }

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
                "version": ACTIVITY_INDEX_VERSION,
                "repositories": {
                    repo_key: {
                        commit_hash: {
                            "day": activity.day.isoformat(),
                            "additions": activity.additions,
                            "deletions": activity.deletions,
                            "languages": activity.languages,
                            "author_name": activity.author_name,
                            "author_email": activity.author_email,
                        }
                        for commit_hash, activity in repository.items()
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
        if not isinstance(payload, dict) or payload.get("version") != ACTIVITY_INDEX_VERSION:
            return
        repositories = payload.get("repositories")
        if not isinstance(repositories, dict):
            return

        loaded: dict[str, dict[str, CommitActivity]] = {}
        for repo_key, raw_repository in list(repositories.items())[-ACTIVITY_INDEX_MAX_REPOSITORIES:]:
            if not isinstance(repo_key, str) or not isinstance(raw_repository, dict):
                continue
            repository: dict[str, CommitActivity] = {}
            for commit_hash, raw_activity in raw_repository.items():
                if not isinstance(commit_hash, str) or not isinstance(raw_activity, dict):
                    continue
                try:
                    day = dt.date.fromisoformat(str(raw_activity.get("day", "")))
                    additions = int(raw_activity.get("additions", 0))
                    deletions = int(raw_activity.get("deletions", 0))
                except (TypeError, ValueError):
                    continue
                raw_languages = raw_activity.get("languages", {})
                languages: dict[str, int] = {}
                if isinstance(raw_languages, dict):
                    languages = {
                        str(language): int(value)
                        for language, value in raw_languages.items()
                        if isinstance(value, int)
                    }
                repository[commit_hash] = CommitActivity(
                    day,
                    additions,
                    deletions,
                    languages,
                    str(raw_activity.get("author_name", "")),
                    str(raw_activity.get("author_email", "")),
                )
            loaded[repo_key] = repository
        with self._lock:
            self._repositories.update(loaded)

    def _touch_repository(self, repo_key: str) -> None:
        repository = self._repositories.pop(repo_key, {})
        self._repositories[repo_key] = repository
        while len(self._repositories) > ACTIVITY_INDEX_MAX_REPOSITORIES:
            self._repositories.pop(next(iter(self._repositories)))

    @staticmethod
    def _repo_key(repo: Path) -> str:
        return str(repo.resolve()).casefold()

    @staticmethod
    def _log_args(commit_hashes: list[str]) -> list[str]:
        return [
            "log",
            "--no-walk=unsorted",
            "--date=short",
            "--format=@@COMMIT@@%H%x09%ad%x09%an%x09%ae",
            "--numstat",
            "--no-renames",
            *commit_hashes,
        ]

    @staticmethod
    def _command_chunks(commit_hashes: list[str]) -> list[list[str]]:
        chunks: list[list[str]] = []
        current: list[str] = []
        length = 0
        for commit_hash in commit_hashes:
            item_length = len(commit_hash) + 1
            if current and length + item_length > ACTIVITY_FETCH_COMMAND_LIMIT:
                chunks.append(current)
                current = []
                length = 0
            current.append(commit_hash)
            length += item_length
        if current:
            chunks.append(current)
        return chunks

    @staticmethod
    def _parse_activity(output: str) -> dict[str, CommitActivity]:
        commits: dict[str, CommitActivity] = {}
        current_hash = ""
        current_date: dt.date | None = None
        current_author_name = ""
        current_author_email = ""
        additions = deletions = 0
        languages: dict[str, int] = {}

        def flush() -> None:
            if current_hash and current_date is not None:
                commits[current_hash] = CommitActivity(
                    current_date,
                    additions,
                    deletions,
                    dict(languages),
                    current_author_name,
                    current_author_email,
                )

        for line in output.splitlines():
            if line.startswith("@@COMMIT@@"):
                flush()
                fields = line.removeprefix("@@COMMIT@@").split("\t", 3)
                current_hash = fields[0].strip() if fields else ""
                try:
                    current_date = dt.date.fromisoformat(fields[1].strip())
                except (IndexError, ValueError):
                    current_date = None
                current_author_name = fields[2].strip() if len(fields) > 2 else ""
                current_author_email = fields[3].strip() if len(fields) > 3 else ""
                additions = deletions = 0
                languages = {}
                continue
            if not current_hash:
                continue
            parts = line.split("\t", 2)
            if len(parts) != 3 or not parts[0].isdigit() or not parts[1].isdigit():
                continue
            path = parts[2].strip()
            if not path or is_probably_binary_path(path):
                continue
            added, removed = int(parts[0]), int(parts[1])
            additions += added
            deletions += removed
            language = classify_text_language(path)
            languages[language] = languages.get(language, 0) + added
        flush()
        return commits
