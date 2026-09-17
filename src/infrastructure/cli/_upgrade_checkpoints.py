"""The safety point `arch-repair upgrade --commit` takes before it writes, and how it is undone.

A checkpoint set records every target a commit is about to write, as it was: each repository's working
tree pinned under a git ref (`git_worktree_checkpoint.pin_checkpoint`), each operational target as a
file copy beside the set's own record. It is taken after the backend-not-serving gate and before the
first write, so a `--restore` returns exactly the pre-upgrade state — uncommitted edits included, because
the pinned tree carries them. A dry run takes none of this; it writes nothing to protect.

Where the set lives is the deployment's own runtime state: `.arch/upgrade-checkpoints/<id>/` under the
workspace when one is named, else under the deployment settings document's directory, else beside the
first repository root. Exactly one set is kept — the last successful commit prunes the one before it —
because a set that is never used is disk, and the one an operator reaches for is the last.
"""

from __future__ import annotations

import json
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path

from src.application.deployment_upgrade.ports import OperationalTargetHandle
from src.domain.clock import utc_now_compact
from src.domain.repository.operational_upgrade import CheckpointSet, OperationalBackup, RepositoryCheckpoint
from src.infrastructure.git.git_worktree_checkpoint import (
    checkpoint_from_ref,
    checkpoint_worktree,
    pin_checkpoint,
    release_pinned_checkpoint,
    release_worktree_checkpoint,
    restore_worktree_checkpoint,
)

CHECKPOINTS_DIRNAME = "upgrade-checkpoints"
_RECORD = "checkpoint-set.json"


class CheckpointFailed(RuntimeError):
    """The safety point could not be taken; nothing was pinned, copied or written."""


def checkpoint_base(*, workspace: str | None, settings_document: Path | None, roots: Sequence[Path]) -> Path:
    """Where this deployment keeps its checkpoint sets."""
    if workspace is not None:
        return Path(workspace).resolve() / ".arch" / CHECKPOINTS_DIRNAME
    if settings_document is not None:
        return settings_document.parent / ".arch" / CHECKPOINTS_DIRNAME
    return roots[0].parent / ".arch" / CHECKPOINTS_DIRNAME


def take_checkpoint_set(
    roots: Sequence[Path], handles: Sequence[OperationalTargetHandle], base: Path
) -> CheckpointSet:
    """Pin every repository and copy every operational target, then record the set on disk."""
    set_id = utc_now_compact()
    set_dir = base / set_id
    set_dir.mkdir(parents=True, exist_ok=True)
    repositories: list[RepositoryCheckpoint] = []
    operational: list[OperationalBackup] = []
    try:
        for root in roots:
            transient = checkpoint_worktree(root)
            try:
                ref = pin_checkpoint(root, transient, set_id)
            finally:
                # The pin holds the snapshot; the branch goes back to where the operator left it —
                # also when pinning failed, or the transient commit would stay as the branch's head.
                release_worktree_checkpoint(root, transient)
            repositories.append(RepositoryCheckpoint(root=str(root), ref=ref))
        for handle in handles:
            copy = handle.backup(set_dir / handle.target.kind)
            if copy is not None:
                operational.append(OperationalBackup(
                    kind=handle.target.kind, location=handle.target.display_location, backup_path=str(copy),
                ))
    except Exception as exc:
        # All or nothing: a half-taken set is a ref nobody records and a directory `--restore`
        # would trust. What was pinned is released; the restore path never learns the id.
        for taken in repositories:
            try:
                release_pinned_checkpoint(Path(taken.root), taken.ref)
            except RuntimeError:
                pass
        shutil.rmtree(set_dir, ignore_errors=True)
        raise CheckpointFailed(f"the safety point could not be taken, so nothing was written: {exc}") from exc
    checkpoint_set = CheckpointSet(id=set_id, repositories=tuple(repositories), operational=tuple(operational))
    (set_dir / _RECORD).write_text(json.dumps(checkpoint_set.to_dict(), indent=2), encoding="utf-8")
    print(
        f"Checkpoint set {set_id} taken under {base} — `--restore {set_id}` returns every target to it.",
        file=sys.stderr,
    )
    return checkpoint_set


def list_checkpoint_sets(base: Path) -> list[CheckpointSet]:
    if not base.is_dir():
        return []
    sets = []
    for record in sorted(base.glob(f"*/{_RECORD}")):
        sets.append(CheckpointSet.from_dict(json.loads(record.read_text(encoding="utf-8"))))
    return sets


def load_checkpoint_set(base: Path, set_id: str) -> CheckpointSet:
    record = base / set_id / _RECORD
    if not record.is_file():
        known = ", ".join(s.id for s in list_checkpoint_sets(base)) or "none"
        raise SystemExit(f"ERROR: no checkpoint set {set_id!r} under {base} (known: {known})")
    return CheckpointSet.from_dict(json.loads(record.read_text(encoding="utf-8")))


def restore_checkpoint_set(
    checkpoint_set: CheckpointSet,
    handles: Sequence[OperationalTargetHandle],
    *,
    rebuild_index: object,
) -> list[str]:
    """Return every target the set names to its recorded state; what was done, for the report.

    Repositories come back from their pinned ref through the same restore a promotion abort uses,
    then their index is rebuilt. Operational targets come back from their copies through the handle
    that owns each kind. The set itself stays: restoring is not consuming.
    """
    done: list[str] = []
    for repository in checkpoint_set.repositories:
        root = Path(repository.root)
        restore_worktree_checkpoint(root, checkpoint_from_ref(root, repository.ref))
        rebuild_index(root)  # type: ignore[operator]
        done.append(f"repository {root}: restored from {repository.ref}")
    by_location = {handle.target.display_location: handle for handle in handles}
    for backup in checkpoint_set.operational:
        handle = by_location.get(backup.location)
        if handle is None:
            done.append(f"{backup.kind} {backup.location}: not restored — no such target in this deployment")
            continue
        handle.restore(Path(backup.backup_path))
        done.append(f"{backup.kind} {backup.location}: restored from {backup.backup_path}")
    return done


def prune_previous_sets(base: Path, keep: str) -> list[str]:
    """Forget every set but *keep*: its refs are released and its directory removed."""
    pruned: list[str] = []
    for old in list_checkpoint_sets(base):
        if old.id == keep:
            continue
        for repository in old.repositories:
            root = Path(repository.root)
            if root.is_dir():
                release_pinned_checkpoint(root, repository.ref)
        shutil.rmtree(base / old.id, ignore_errors=True)
        pruned.append(old.id)
    return pruned
