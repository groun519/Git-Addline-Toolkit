from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from line_tracker import run_git


MOCKUP_BRANCH = "codex/mockups"
MOCKUP_REMOTE_BRANCH = "origin/codex/mockups"
MOCKUP_ROOTS = ("docs/wip", "docs/archive")

GitRunner = Callable[[Path, list[str]], str]


class MockupCatalogError(RuntimeError):
    pass


@dataclass(frozen=True)
class MockupDocument:
    path: str
    title: str
    workspace: str
    section: str
    status: str = ""
    search_text: str = ""


@dataclass(frozen=True)
class MockupCatalog:
    branch: str
    head: str
    worktree_path: Path | None
    documents: tuple[MockupDocument, ...]
    dirty_count: int = 0
    ahead: int = 0
    behind: int = 0

    @property
    def workspace_count(self) -> int:
        roots = {
            PurePosixPath(document.path).parts[2]
            for document in self.documents
            if document.section == "wip" and len(PurePosixPath(document.path).parts) > 3
        }
        return len(roots)


def load_mockup_catalog(
    repo: Path,
    *,
    run: GitRunner = run_git,
) -> MockupCatalog:
    branch = _resolve_mockup_branch(repo, run)
    worktree_path = find_branch_worktree(repo, MOCKUP_BRANCH, run=run)
    if worktree_path is not None and worktree_path.is_dir():
        documents = _load_worktree_documents(worktree_path)
        dirty_count = len(
            [line for line in run(worktree_path, ["status", "--porcelain"]).splitlines() if line]
        )
    else:
        documents = _load_git_documents(repo, branch, run)
        dirty_count = 0

    try:
        head = run(repo, ["rev-parse", "--short", branch]).strip()
    except RuntimeError:
        head = ""
    ahead, behind = _branch_distance(repo, branch, run)
    return MockupCatalog(
        branch=branch,
        head=head,
        worktree_path=worktree_path,
        documents=documents,
        dirty_count=dirty_count,
        ahead=ahead,
        behind=behind,
    )


def load_mockup_document(
    repo: Path,
    catalog: MockupCatalog,
    document: MockupDocument,
    *,
    run: GitRunner = run_git,
) -> str:
    source_path = mockup_document_path(catalog, document)
    if source_path is not None:
        try:
            return source_path.read_text(encoding="utf-8-sig")
        except OSError as exc:
            raise MockupCatalogError(str(exc)) from exc
    try:
        return run(repo, ["show", f"{catalog.branch}:{document.path}"])
    except RuntimeError as exc:
        raise MockupCatalogError(str(exc)) from exc


def mockup_document_path(
    catalog: MockupCatalog,
    document: MockupDocument,
) -> Path | None:
    if catalog.worktree_path is None:
        return None
    path = catalog.worktree_path.joinpath(*PurePosixPath(document.path).parts)
    return path if path.is_file() else None


def find_branch_worktree(
    repo: Path,
    branch: str,
    *,
    run: GitRunner = run_git,
) -> Path | None:
    try:
        output = run(repo, ["worktree", "list", "--porcelain"])
    except RuntimeError:
        return None
    target = f"refs/heads/{branch}"
    current_path: Path | None = None
    for line in (*output.splitlines(), ""):
        if not line:
            current_path = None
        elif line.startswith("worktree "):
            current_path = Path(line.removeprefix("worktree ").strip())
        elif line == f"branch {target}" and current_path is not None:
            return current_path
    return None


def sync_mockup_worktree(
    repo: Path,
    *,
    run: GitRunner = run_git,
) -> Path:
    worktree_path = find_branch_worktree(repo, MOCKUP_BRANCH, run=run)
    if worktree_path is None:
        raise MockupCatalogError("mockup worktree is not configured")
    if run(worktree_path, ["status", "--porcelain"]).strip():
        raise MockupCatalogError("mockup worktree has uncommitted changes")
    run(
        worktree_path,
        [
            "fetch",
            "origin",
            f"+refs/heads/{MOCKUP_BRANCH}:refs/remotes/{MOCKUP_REMOTE_BRANCH}",
        ],
    )
    run(worktree_path, ["merge", "--ff-only", MOCKUP_REMOTE_BRANCH])
    return worktree_path


def _resolve_mockup_branch(repo: Path, run: GitRunner) -> str:
    for branch in (MOCKUP_BRANCH, MOCKUP_REMOTE_BRANCH):
        try:
            run(repo, ["rev-parse", "--verify", branch])
            return branch
        except RuntimeError:
            continue
    raise MockupCatalogError(f"{MOCKUP_BRANCH} branch was not found")


def _load_worktree_documents(worktree: Path) -> tuple[MockupDocument, ...]:
    documents: list[MockupDocument] = []
    for root_name in MOCKUP_ROOTS:
        root = worktree.joinpath(*PurePosixPath(root_name).parts)
        if not root.is_dir():
            continue
        for path in root.rglob("*.md"):
            try:
                content = path.read_text(encoding="utf-8-sig")
            except OSError:
                continue
            relative_path = path.relative_to(worktree).as_posix()
            title, status = _parse_document_metadata(content, relative_path)
            documents.append(
                _make_document(
                    relative_path,
                    title,
                    status,
                    content.casefold(),
                )
            )
    return tuple(sorted(documents, key=_document_sort_key))


def _load_git_documents(
    repo: Path,
    branch: str,
    run: GitRunner,
) -> tuple[MockupDocument, ...]:
    output = run(repo, ["ls-tree", "-r", "--name-only", branch, "--", *MOCKUP_ROOTS])
    paths = [line.strip() for line in output.splitlines() if line.strip().lower().endswith(".md")]
    metadata: dict[str, tuple[str, str]] = {}
    try:
        grep_output = run(
            repo,
            [
                "grep",
                "-n",
                "-I",
                "-e",
                "^# ",
                "-e",
                "^> Status:",
                branch,
                "--",
                *MOCKUP_ROOTS,
            ],
        )
    except RuntimeError:
        grep_output = ""
    prefix = f"{branch}:"
    for line in grep_output.splitlines():
        if not line.startswith(prefix):
            continue
        fields = line[len(prefix):].split(":", 2)
        if len(fields) != 3:
            continue
        path, _line_number, text = fields
        title, status = metadata.get(path, ("", ""))
        if text.startswith("# ") and not title:
            title = text.removeprefix("# ").strip()
        elif text.startswith("> Status:") and not status:
            status = _clean_status(text.partition(":")[2])
        metadata[path] = (title, status)
    documents = [
        _make_document(path, *metadata.get(path, ("", "")), "")
        for path in paths
    ]
    return tuple(sorted(documents, key=_document_sort_key))


def _parse_document_metadata(content: str, path: str) -> tuple[str, str]:
    title = ""
    status = ""
    for line in content.splitlines():
        if not title and line.startswith("# "):
            title = line.removeprefix("# ").strip()
        elif not status and line.lower().startswith("> status:"):
            status = _clean_status(line.partition(":")[2])
        if title and status:
            break
    if not title:
        title = PurePosixPath(path).stem.replace("_", " ")
    return title, status


def _make_document(
    path: str,
    title: str,
    status: str,
    search_text: str,
) -> MockupDocument:
    pure_path = PurePosixPath(path)
    parts = pure_path.parts
    section = parts[1] if len(parts) > 1 else "wip"
    workspace = parts[2] if len(parts) > 3 else "overview"
    if workspace == "modules" and len(parts) > 5 and parts[3] == "modules":
        workspace = f"modules / {parts[4]}"
    return MockupDocument(
        path=path,
        title=title or pure_path.stem.replace("_", " "),
        workspace=workspace,
        section=section,
        status=status,
        search_text=search_text,
    )


def _clean_status(value: str) -> str:
    return re.sub(r"[*_`]", "", value).strip()


def _document_sort_key(document: MockupDocument) -> tuple[object, ...]:
    path = PurePosixPath(document.path)
    return (
        document.section != "wip",
        document.workspace.casefold(),
        path.name.casefold() != "readme.md",
        path.name.casefold(),
    )


def _branch_distance(repo: Path, branch: str, run: GitRunner) -> tuple[int, int]:
    if branch != MOCKUP_BRANCH:
        return 0, 0
    try:
        output = run(
            repo,
            ["rev-list", "--left-right", "--count", f"{MOCKUP_BRANCH}...{MOCKUP_REMOTE_BRANCH}"],
        ).strip()
        left, right = output.split()
        return int(left), int(right)
    except (RuntimeError, ValueError):
        return 0, 0
