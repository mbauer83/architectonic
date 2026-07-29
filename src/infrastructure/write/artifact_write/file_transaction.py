"""Atomic publication of a small, known set of file changes.

The middle term between the two existing mechanisms. ``write_atomic`` covers one file, where
``os.replace`` is enough. ``commit_staged_repo`` covers a bulk write whose extent is not
known up front, and pays for a copy-on-write staging repo to find out. A rename or a group
move touches a handful of named files: the extent is known, the copy is unnecessary, but the
changes must still land together or not at all.

Landing "together" is the point. A group move that writes the new file and then fails to
unlink the old leaves the artifact in two groups; a rename that moves an entity and then
fails to rewrite its referrers leaves references naming a slug nothing carries. Both states
are silent — the repository still parses, and every id still resolves — so nothing downstream
reports them. Publishing through one manifest makes the whole change a single fact.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .m4_transaction import (
    ManifestEntry,
    TransactionManifest,
    ensure_transactions_root,
    fsync_directory,
    hash_file,
    publish_transaction,
    write_transaction_intent,
)


@dataclass(frozen=True)
class FileChange:
    """One file's intended end state: *content* to write, or None to delete it."""

    path: Path
    content: str | None

    @property
    def is_delete(self) -> bool:
        return self.content is None


def commit_file_changes(
    *,
    repo_root: Path,
    changes: list[FileChange],
    rebuild_index: Callable[[], None],
    label: str,
    on_boundary: Callable[[str], None] | None = None,
) -> list[Path]:
    """Publish *changes* atomically. Returns the affected paths, in manifest order.

    A change whose file already exists is a ``replace``; one whose file does not is a
    ``create``. Prior-state hashes are taken before anything is staged, so a concurrent
    modification is caught by the manifest rather than silently overwritten.
    """
    txns_dir = ensure_transactions_root(repo_root)
    fsync_directory(txns_dir.parent)
    txn_dir = txns_dir / f"{label}-{uuid.uuid4().hex}"
    txn_dir.mkdir()
    fsync_directory(txns_dir)

    staged = txn_dir / "staged"
    staged.mkdir()

    entries: list[ManifestEntry] = []
    for index, change in enumerate(changes):
        rel = change.path.relative_to(repo_root).as_posix()
        existed = change.path.exists()
        if change.is_delete:
            entries.append(
                ManifestEntry(
                    kind="delete",
                    dest=rel,
                    target_hash="absent",
                    prior_hash_or_absent=hash_file(change.path),
                    payload=None,
                )
            )
            continue
        staged_path = staged / rel
        staged_path.parent.mkdir(parents=True, exist_ok=True)
        staged_path.write_text(change.content or "", encoding="utf-8")
        entries.append(
            ManifestEntry(
                kind="replace" if existed else "create",
                dest=rel,
                target_hash=hash_file(staged_path),
                prior_hash_or_absent=hash_file(change.path) if existed else "absent",
                payload=f"payloads/{index}",
            )
        )

    manifest = TransactionManifest(entries=entries)
    write_transaction_intent(
        repo_root=repo_root,
        transaction_dir=txn_dir,
        staged_root=staged,
        manifest=manifest,
        on_boundary=on_boundary,
    )
    publish_transaction(
        repo_root=repo_root,
        transaction_dir=txn_dir,
        manifest=manifest,
        rebuild_index=rebuild_index,
        on_boundary=on_boundary,
    )
    return [change.path for change in changes]
