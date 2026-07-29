"""Filesystem and registry-persistence helpers for group lifecycle operations.

Kept separate from the public operations so the latter read as declarative
intent (find → mutate registry → persist) without filesystem detail noise.
"""

from __future__ import annotations

import subprocess
from dataclasses import replace
from pathlib import Path

from src.application.group_registry import registry_to_yaml
from src.config.repo_paths import ARCH_REPO
from src.domain.repository.groups import GroupAxis, GroupEntry, GroupRegistry
from src.infrastructure.mutation_adapters import run_git

_GROUPS_FILE = "groups.yaml"


def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return run_git(cwd, args)


def _git_add(path: Path, repo_root: Path) -> None:
    _run_git(["add", str(path.relative_to(repo_root))], repo_root)


def _persist_registry(repo_root: Path, registry: GroupRegistry) -> None:
    """Write groups.yaml and stage it — the closing step of every mutating op."""
    arch_dir = repo_root / ARCH_REPO
    arch_dir.mkdir(parents=True, exist_ok=True)
    (arch_dir / _GROUPS_FILE).write_text(registry_to_yaml(registry), encoding="utf-8")
    _git_add(arch_dir / _GROUPS_FILE, repo_root)


def _update_axis(registry: GroupRegistry, axis: GroupAxis, entries: list[GroupEntry]) -> GroupRegistry:
    match axis:
        case "model-project":
            return replace(registry, model_projects=tuple(entries))
        case "diagram-collection":
            return replace(registry, diagram_collections=tuple(entries))
        case _:
            return replace(registry, document_collections=tuple(entries))


def _new_id() -> str:
    from src.application.group_registry import _new_group_id  # noqa: PLC0415

    return _new_group_id()


def _subtree_files(directory: Path) -> list[Path]:
    return [p for p in directory.rglob("*") if p.is_file()]


def _all_doc_group_dirs(repo_root: Path, slug: str) -> list[Path]:
    """Return all existing docs/<doc-type>/<slug> directories for a document-collection."""
    from src.application.repo_path_helpers import docs_root  # noqa: PLC0415

    docs = docs_root(repo_root)
    if not docs.exists():
        return []
    return [
        candidate
        for doc_type_dir in sorted(docs.iterdir())
        if doc_type_dir.is_dir() and (candidate := doc_type_dir / slug).exists()
    ]


def _group_dir(repo_root: Path, axis: GroupAxis, slug: str) -> Path | None:
    """Return the filesystem directory for this group, or None if it has no dedicated dir."""
    from src.application.repo_path_helpers import diagram_source_root  # noqa: PLC0415

    if axis == "model-project":
        return repo_root / "projects" / slug
    if axis == "diagram-collection":
        return diagram_source_root(repo_root) / slug
    dirs = _all_doc_group_dirs(repo_root, slug)  # document-collection: first existing match
    return dirs[0] if dirs else None


def _collection_dirs(repo_root: Path, axis: GroupAxis, slug: str) -> list[Path]:
    """All existing directories backing a group (multiple for document-collections)."""
    if axis == "document-collection":
        return _all_doc_group_dirs(repo_root, slug)
    d = _group_dir(repo_root, axis, slug)
    return [d] if d is not None and d.exists() else []


def _collection_files(repo_root: Path, axis: GroupAxis, slug: str) -> list[Path]:
    return [f for d in _collection_dirs(repo_root, axis, slug) for f in _subtree_files(d)]


def _safe_rmdir(directory: Path) -> None:
    try:
        directory.rmdir()
    except OSError:
        pass
