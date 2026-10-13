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
class MockupSource:
    branch: str = MOCKUP_BRANCH
    wip_root: str = MOCKUP_ROOTS[0]
    archive_root: str = MOCKUP_ROOTS[1]

    def normalized(self) -> MockupSource:
        branch = self.branch.strip() or MOCKUP_BRANCH
        if branch.startswith("refs/heads/"):
            branch = branch.removeprefix("refs/heads/")
        elif branch.startswith("refs/remotes/"):
            branch = branch.removeprefix("refs/remotes/")
        if branch.startswith("-") or any(character in branch for character in "~^:?*[\\"):
            branch = MOCKUP_BRANCH
        return MockupSource(
            branch=branch,
            wip_root=_normalize_root(self.wip_root, MOCKUP_ROOTS[0]),
            archive_root=_normalize_root(self.archive_root, MOCKUP_ROOTS[1]),
        )

    @property
    def local_branch(self) -> str:
        return self.branch.removeprefix("origin/")

    @property
    def remote_branch(self) -> str:
        return self.branch if self.branch.startswith("origin/") else f"origin/{self.branch}"

    @property
    def section_roots(self) -> tuple[tuple[str, str], ...]:
        return (("wip", self.wip_root), ("archive", self.archive_root))


DEFAULT_MOCKUP_SOURCE = MockupSource()


@dataclass(frozen=True)
class MockupDocument:
    path: str
    title: str
    workspace: str
    section: str
    status: str = ""
    search_text: str = ""
    workspace_root: str = "overview"


@dataclass(frozen=True)
class MockupCatalog:
    branch: str
    head: str
    worktree_path: Path | None
    documents: tuple[MockupDocument, ...]
    source: MockupSource = DEFAULT_MOCKUP_SOURCE
    dirty_count: int = 0
    ahead: int = 0
    behind: int = 0

    @property
    def workspace_count(self) -> int:
        roots = {
            document.workspace_root
            for document in self.documents
            if document.section == "wip" and document.workspace_root != "overview"
        }
        return len(roots)


def load_mockup_catalog(
    repo: Path,
    *,
    source: MockupSource = DEFAULT_MOCKUP_SOURCE,
    run: GitRunner = run_git,
) -> MockupCatalog:
    source = source.normalized()
    branch = probe_mockup_source(repo, source=source, run=run)
    worktree_path = find_branch_worktree(repo, source.local_branch, run=run)
    if worktree_path is not None and worktree_path.is_dir():
        documents = _load_worktree_documents(worktree_path, source)
        dirty_count = len(
            [line for line in run(worktree_path, ["status", "--porcelain"]).splitlines() if line]
        )
    else:
        documents = _load_git_documents(repo, branch, source, run)
        dirty_count = 0

    try:
        head = run(repo, ["rev-parse", "--short", branch]).strip()
    except RuntimeError:
        head = ""
    ahead, behind = _branch_distance(repo, branch, source, run)
    return MockupCatalog(
        branch=branch,
        head=head,
        worktree_path=worktree_path,
        documents=documents,
        source=source,
        dirty_count=dirty_count,
        ahead=ahead,
        behind=behind,
    )


def probe_mockup_source(
    repo: Path,
    *,
    source: MockupSource = DEFAULT_MOCKUP_SOURCE,
    run: GitRunner = run_git,
) -> str:
    source = source.normalized()
    for branch in (source.local_branch, source.remote_branch):
        try:
            run(repo, ["rev-parse", "--verify", branch])
            return branch
        except RuntimeError:
            continue
    raise MockupCatalogError(f"{source.local_branch} branch was not found")


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
    source: MockupSource = DEFAULT_MOCKUP_SOURCE,
    run: GitRunner = run_git,
) -> Path:
    source = source.normalized()
    worktree_path = find_branch_worktree(repo, source.local_branch, run=run)
    if worktree_path is None:
        raise MockupCatalogError("mockup worktree is not configured")
    if run(worktree_path, ["status", "--porcelain"]).strip():
        raise MockupCatalogError("mockup worktree has uncommitted changes")
    run(
        worktree_path,
        [
            "fetch",
            "origin",
            (
                f"+refs/heads/{source.local_branch}:"
                f"refs/remotes/{source.remote_branch}"
            ),
        ],
    )
    run(worktree_path, ["merge", "--ff-only", source.remote_branch])
    return worktree_path


def _load_worktree_documents(
    worktree: Path,
    source: MockupSource,
) -> tuple[MockupDocument, ...]:
    documents: list[MockupDocument] = []
    for _section, root_name in source.section_roots:
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
                    source,
                )
            )
    return tuple(sorted(documents, key=_document_sort_key))


def _load_git_documents(
    repo: Path,
    branch: str,
    source: MockupSource,
    run: GitRunner,
) -> tuple[MockupDocument, ...]:
    roots = tuple(root for _section, root in source.section_roots)
    output = run(repo, ["ls-tree", "-r", "--name-only", branch, "--", *roots])
    paths = [line.strip() for line in output.splitlines() if line.strip().lower().endswith(".md")]
    content_lines: dict[str, list[str]] = {}
    try:
        grep_output = run(
            repo,
            [
                "grep",
                "-n",
                "-I",
                "-e",
                ".",
                branch,
                "--",
                *roots,
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
        content_lines.setdefault(path, []).append(text)
    documents: list[MockupDocument] = []
    for path in paths:
        content = "\n".join(content_lines.get(path, ()))
        title, status = _parse_document_metadata(content, path)
        documents.append(_make_document(path, title, status, content.casefold(), source))
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
    source: MockupSource,
) -> MockupDocument:
    pure_path = PurePosixPath(path)
    parts = pure_path.parts
    section = "wip"
    relative_parts = parts
    for candidate_section, root in source.section_roots:
        root_parts = PurePosixPath(root).parts
        if parts[:len(root_parts)] == root_parts:
            section = candidate_section
            relative_parts = parts[len(root_parts):]
            break
    workspace_root = relative_parts[0] if len(relative_parts) > 1 else "overview"
    workspace = workspace_root
    if workspace == "modules" and len(relative_parts) > 3 and relative_parts[1] == "modules":
        workspace = f"modules / {relative_parts[2]}"
    return MockupDocument(
        path=path,
        title=title or pure_path.stem.replace("_", " "),
        workspace=workspace,
        section=section,
        status=status,
        search_text=search_text,
        workspace_root=workspace_root,
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


def _branch_distance(
    repo: Path,
    branch: str,
    source: MockupSource,
    run: GitRunner,
) -> tuple[int, int]:
    if branch != source.local_branch:
        return 0, 0
    try:
        output = run(
            repo,
            [
                "rev-list",
                "--left-right",
                "--count",
                f"{source.local_branch}...{source.remote_branch}",
            ],
        ).strip()
        left, right = output.split()
        return int(left), int(right)
    except (RuntimeError, ValueError):
        return 0, 0


def _normalize_root(value: str, fallback: str) -> str:
    candidate = PurePosixPath(value.strip().replace("\\", "/"))
    if (
        candidate.is_absolute()
        or ".." in candidate.parts
        or (candidate.parts and ":" in candidate.parts[0])
    ):
        return fallback
    normalized = candidate.as_posix().strip("/")
    if normalized in {"", "."}:
        return fallback
    return normalized
