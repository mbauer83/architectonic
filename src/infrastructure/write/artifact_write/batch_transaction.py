from __future__ import annotations

import filecmp
import shutil
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from src.config.repo_paths import DIAGRAM_CATALOG, DOCS, MODEL, PROJECTS

from .m4_transaction import (
    ChangeKind,
    GitRefTransition,
    ManifestEntry,
    TransactionManifest,
    ensure_transactions_root,
    fsync_directory,
    hash_file,
    publish_transaction,
    write_transaction_intent,
)
from .staged_workspace import StagedWorkspace, deactivate_staged_workspace, staged_workspace_guard

_MANAGED_SUBTREES = (MODEL, DOCS, DIAGRAM_CATALOG, PROJECTS)


@dataclass(frozen=True)
class BatchCommitResult:
    changed_paths: list[Path]
    deleted_paths: list[Path]


@dataclass(frozen=True)
class StagingDirectory:
    path: Path

    def cleanup(self) -> None:
        deactivate_staged_workspace(self.path / "staged")
        if (self.path / "intent").exists():
            return
        shutil.rmtree(self.path, ignore_errors=True)
        fsync_directory(self.path.parent)


def create_staging_repo(
    repo_root: Path,
    *,
    on_boundary: Callable[[str], None] | None = None,
) -> tuple[StagingDirectory, Path]:
    transactions = ensure_transactions_root(repo_root)
    fsync_directory(transactions.parent)
    transaction_dir = transactions / uuid.uuid4().hex
    transaction_dir.mkdir()
    fsync_directory(transactions)
    if on_boundary is not None:
        on_boundary("transaction_dir_created")

    staged_root = transaction_dir / "staged"
    workspace = StagedWorkspace(live_root=repo_root, staged_root=staged_root)
    workspace.create_mirror()
    workspace.activate()
    return StagingDirectory(transaction_dir), staged_root


def staged_write_guard(staged_root: Path):
    return staged_workspace_guard(staged_root)


def commit_staged_repo(
    *,
    live_root: Path,
    staged_root: Path,
    touched_paths: set[Path],
    rebuild_index: Callable[[BatchCommitResult], object],
    ref_transition: GitRefTransition | None = None,
    on_boundary: Callable[[str], None] | None = None,
) -> BatchCommitResult:
    transaction_dir = staged_root.parent
    entries, result = _derive_manifest_from_touched_paths(
        live_root=live_root,
        staged_root=staged_root,
        touched_paths=touched_paths,
    )
    manifest = TransactionManifest(entries=entries, ref=ref_transition)
    write_transaction_intent(
        repo_root=live_root,
        transaction_dir=transaction_dir,
        staged_root=staged_root,
        manifest=manifest,
        on_boundary=on_boundary,
    )
    publish_transaction(
        repo_root=live_root,
        transaction_dir=transaction_dir,
        manifest=manifest,
        rebuild_index=lambda: rebuild_index(result),
        on_boundary=on_boundary,
    )
    return result


def _derive_manifest_from_touched_paths(
    *,
    live_root: Path,
    staged_root: Path,
    touched_paths: set[Path],
) -> tuple[list[ManifestEntry], BatchCommitResult]:
    relpaths = sorted(
        {
            relpath
            for path in touched_paths
            if (relpath := _managed_relpath(path, live_root=live_root, staged_root=staged_root)) is not None
        }
    )
    entries: list[ManifestEntry] = []
    changed_paths: list[Path] = []
    deleted_paths: list[Path] = []

    for relpath in relpaths:
        staged_path = staged_root / relpath
        live_path = live_root / relpath
        if staged_path.exists():
            if live_path.exists() and filecmp.cmp(live_path, staged_path, shallow=False):
                continue
            prior = hash_file(live_path) if live_path.exists() else "absent"
            kind: ChangeKind = "replace" if live_path.exists() else "create"
            entries.append(
                ManifestEntry(
                    kind=kind,
                    dest=relpath.as_posix(),
                    target_hash=hash_file(staged_path),
                    prior_hash_or_absent=prior,
                    payload=f"payloads/{len(entries):06d}",
                )
            )
            changed_paths.append(live_path)
        elif live_path.exists():
            entries.append(
                ManifestEntry(
                    kind="delete",
                    dest=relpath.as_posix(),
                    target_hash="absent",
                    prior_hash_or_absent=hash_file(live_path),
                    payload=None,
                )
            )
            deleted_paths.append(live_path)

    return entries, BatchCommitResult(changed_paths=changed_paths, deleted_paths=deleted_paths)


def _derive_manifest(
    *,
    live_root: Path,
    staged_root: Path,
) -> tuple[list[ManifestEntry], BatchCommitResult]:
    live_files = _managed_files(live_root)
    staged_files = _managed_files(staged_root)
    entries: list[ManifestEntry] = []
    changed_paths: list[Path] = []
    deleted_paths: list[Path] = []

    for relpath in sorted(staged_files):
        staged_path = staged_root / relpath
        live_path = live_root / relpath
        if relpath in live_files and filecmp.cmp(live_path, staged_path, shallow=False):
            continue
        prior = hash_file(live_path) if live_path.exists() else "absent"
        kind: ChangeKind = "replace" if live_path.exists() else "create"
        entries.append(
            ManifestEntry(
                kind=kind,
                dest=relpath.as_posix(),
                target_hash=hash_file(staged_path),
                prior_hash_or_absent=prior,
                payload=f"payloads/{len(entries):06d}",
            )
        )
        changed_paths.append(live_path)

    for relpath in sorted(live_files - staged_files):
        live_path = live_root / relpath
        entries.append(
            ManifestEntry(
                kind="delete",
                dest=relpath.as_posix(),
                target_hash="absent",
                prior_hash_or_absent=hash_file(live_path),
                payload=None,
            )
        )
        deleted_paths.append(live_path)

    return entries, BatchCommitResult(changed_paths=changed_paths, deleted_paths=deleted_paths)


def _managed_files(repo_root: Path) -> set[Path]:
    files: set[Path] = set()
    for subtree in _MANAGED_SUBTREES:
        root = repo_root / subtree
        if not root.exists():
            continue
        files.update(path.relative_to(repo_root) for path in root.rglob("*") if path.is_file())
    return files


def _managed_relpath(path: Path, *, live_root: Path, staged_root: Path) -> Path | None:
    resolved = path.resolve()
    for root in (staged_root.resolve(), live_root.resolve()):
        try:
            relpath = resolved.relative_to(root)
        except ValueError:
            continue
        return relpath if _is_managed_relpath(relpath) else None
    return None


def _is_managed_relpath(relpath: Path) -> bool:
    return bool(relpath.parts) and relpath.parts[0] in _MANAGED_SUBTREES


def _ignore_transaction_storage(directory: str, names: list[str]) -> set[str]:
    path = Path(directory)
    if path.name == ".arch-repo":
        return {"transactions"} & set(names)
    return set()
