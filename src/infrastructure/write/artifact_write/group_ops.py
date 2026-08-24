"""Group lifecycle operations: create, rename, archive/unarchive, delete (collections only).

All mutating ops update .arch-repo/groups.yaml atomically via the staged transaction.
Filesystem and registry-persistence detail lives in _group_fs.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from src.application.group_registry import load_group_registry
from src.domain.repository.groups import UNCATEGORIZED, GroupAxis, GroupEntry, GroupRegistry

from ._group_fs import (
    _collection_dirs,
    _collection_files,
    _group_dir,
    _new_id,
    _persist_registry,
    _run_git,
    _safe_rmdir,
    _update_axis,
)

GroupAction = Literal["create", "rename", "archive", "unarchive", "delete", "update"]


class GroupOpError(ValueError):
    """Raised on invalid group lifecycle operations."""


def _require_entry(registry: GroupRegistry, axis: GroupAxis, slug: str) -> GroupEntry:
    entry = registry.find(axis, slug)
    if entry is None:
        raise GroupOpError(f"Group {slug!r} not found on axis {axis!r}.")
    return entry


def _replaced_entries(registry: GroupRegistry, axis: GroupAxis, slug: str, updated: GroupEntry) -> list[GroupEntry]:
    return [updated if e.slug == slug else e for e in registry._by_axis(axis)]


@dataclass(frozen=True)
class GroupEffects:
    """Whether a group operation's effects reach the repository.

    Every operation below has the same shape: load the registry, validate, compute the axis' new
    entry list, commit. A preview is that same code with the commit withheld — so the decision lives
    at this one seam rather than as a flag inside each operation, and an operation cannot honour it
    by accident or forget to.

    It was forgotten. `dry_run` was declared on the tool with a default of `True` and read by one
    branch of one action: `create`, `rename`, `archive`, `unarchive`, `update` and the deletion of a
    diagram- or document-collection all mutated the repository whatever it said, and the result named
    neither the flag nor whether anything was written. A parameter that defaults to the safe value and
    is then ignored reads as a guarantee.
    """

    applies: bool

    def persist_axis(
        self, repo_root: Path, registry: GroupRegistry, axis: GroupAxis, entries: list[GroupEntry]
    ) -> None:
        if self.applies:
            _persist_registry(repo_root, _update_axis(registry, axis, entries))

    def relocate_group_dir(self, repo_root: Path, axis: GroupAxis, slug: str, new_slug: str) -> None:
        if self.applies:
            _git_mv_group_dir(repo_root, axis, slug, new_slug)

    def remove_group_files(self, repo_root: Path, files: list[Path], dirs: list[Path]) -> None:
        if not self.applies or not files:
            return
        _run_git(["rm", "-f", *[str(f.relative_to(repo_root)) for f in files]], repo_root)
        for directory in dirs:
            _safe_rmdir(directory)


#: The repository is changed.
APPLIED = GroupEffects(applies=True)
#: Nothing is changed; the operation still validates and still reports what it would do.
PREVIEWED = GroupEffects(applies=False)


# ---------------------------------------------------------------------------
# Public operation functions
# ---------------------------------------------------------------------------


def group_create(
    repo_root: Path,
    *,
    axis: GroupAxis,
    slug: str,
    name: str,
    description: str = "",
    order: int = 0,
    meta_ontology: str = "",
    type_filter: tuple[str, ...] = (),
    effects: GroupEffects = APPLIED,
) -> dict[str, object]:
    """Register a new group (and lazily create the directory)."""
    registry = load_group_registry(repo_root)
    if registry.find(axis, slug) is not None:
        raise GroupOpError(f"Group {slug!r} already exists on axis {axis!r}.")
    is_model = axis == "model-project"
    entry = GroupEntry(
        slug=slug, id=_new_id(), name=name, description=description, order=order,
        meta_ontology=meta_ontology if is_model else "",
        type_filter=type_filter if not is_model else (),
    )
    effects.persist_axis(repo_root, registry, axis, [*registry._by_axis(axis), entry])
    return {"action": "created", "axis": axis, "slug": slug, "id": entry.id}


def group_rename(
    repo_root: Path,
    *,
    axis: GroupAxis,
    slug: str,
    new_name: str | None = None,
    new_slug: str | None = None,
    effects: GroupEffects = APPLIED,
) -> dict[str, object]:
    """Rename a group: display name only (registry edit) or slug (git mv subtree + registry)."""
    registry = load_group_registry(repo_root)
    entry = _require_entry(registry, axis, slug)

    if new_slug is None or new_slug == slug:
        updated = replace(entry, name=new_name or entry.name)
    else:
        if registry.find(axis, new_slug) is not None:
            raise GroupOpError(f"A group named {new_slug!r} already exists on axis {axis!r}.")
        effects.relocate_group_dir(repo_root, axis, slug, new_slug)
        updated = replace(entry, slug=new_slug, name=new_name or entry.name)

    effects.persist_axis(repo_root, registry, axis, _replaced_entries(registry, axis, slug, updated))
    return {"action": "renamed", "axis": axis, "slug": updated.slug, "old_slug": slug}


def _git_mv_group_dir(repo_root: Path, axis: GroupAxis, slug: str, new_slug: str) -> None:
    old_dir = _group_dir(repo_root, axis, slug)
    new_dir = _group_dir(repo_root, axis, new_slug)
    if old_dir is None or new_dir is None or not old_dir.exists():
        return
    new_dir.parent.mkdir(parents=True, exist_ok=True)
    result = _run_git(["mv", str(old_dir.relative_to(repo_root)), str(new_dir.relative_to(repo_root))], repo_root)
    if result.returncode != 0:
        raise GroupOpError(f"git mv failed: {result.stderr}")


def group_archive(
    repo_root: Path, *, axis: GroupAxis, slug: str, confirm: str | None, effects: GroupEffects = APPLIED,
) -> dict[str, object]:
    """Set archived=True on a group. Non-empty collections require typed confirm."""
    registry = load_group_registry(repo_root)
    entry = _require_entry(registry, axis, slug)
    if entry.slug == UNCATEGORIZED:
        raise GroupOpError("The 'uncategorized' group cannot be archived.")

    is_nonempty = any(any(d.rglob("*")) for d in _collection_dirs(repo_root, axis, slug))
    if is_nonempty and confirm != slug:
        raise GroupOpError(f"Group {slug!r} is non-empty. Pass confirm={slug!r} to archive it.")

    effects.persist_axis(
        repo_root, registry, axis, _replaced_entries(registry, axis, slug, replace(entry, archived=True))
    )
    return {"action": "archived", "axis": axis, "slug": slug}


def group_unarchive(
    repo_root: Path, *, axis: GroupAxis, slug: str, effects: GroupEffects = APPLIED,
) -> dict[str, object]:
    """Set archived=False on a group."""
    registry = load_group_registry(repo_root)
    entry = _require_entry(registry, axis, slug)
    effects.persist_axis(
        repo_root, registry, axis, _replaced_entries(registry, axis, slug, replace(entry, archived=False))
    )
    return {"action": "unarchived", "axis": axis, "slug": slug}


def group_delete_collection(
    repo_root: Path, *, axis: GroupAxis, slug: str, confirm: str | None, dry_run: bool = False,
) -> dict[str, object]:
    """Delete a diagram- or document-collection, or a model-project (cascade).

    For model-project the cascade reports its own impact before it applies anything.
    For diagram/document collections: removes the folder and its files.
    All cases require typed confirm equal to the target slug.

    This is the one operation that already took `dry_run`, so it derives its own effects rather than
    accepting them: two parameters for one decision could disagree, and a caller who passed only
    `dry_run=True` would then get the deletion it asked to preview.
    """
    effects = PREVIEWED if dry_run else APPLIED
    if axis == "model-project":
        from src.infrastructure.write.artifact_write.cascade_delete import (  # noqa: PLC0415
            cascade_delete_model_project,
        )

        try:
            return cascade_delete_model_project(repo_root, slug, confirm or "", dry_run=dry_run)
        except ValueError as exc:
            raise GroupOpError(str(exc)) from exc

    registry = load_group_registry(repo_root)
    entry = _require_entry(registry, axis, slug)
    if entry.slug == UNCATEGORIZED:
        raise GroupOpError("The 'uncategorized' group cannot be deleted.")

    dirs = _collection_dirs(repo_root, axis, slug)
    files = _collection_files(repo_root, axis, slug)
    if files and confirm != slug:
        raise GroupOpError(f"Group {slug!r} contains {len(files)} file(s). Pass confirm={slug!r} to delete.")
    effects.remove_group_files(repo_root, files, dirs)
    effects.persist_axis(repo_root, registry, axis, [e for e in registry._by_axis(axis) if e.slug != slug])
    return {"action": "deleted", "axis": axis, "slug": slug, "files_removed": len(files)}


def group_update(
    repo_root: Path,
    *,
    axis: GroupAxis,
    slug: str,
    name: str | None = None,
    description: str | None = None,
    meta_ontology: str | None = None,
    type_filter: tuple[str, ...] | None = None,
    effects: GroupEffects = APPLIED,
) -> dict[str, object]:
    """Update display metadata without moving files.

    meta_ontology applies to model-project groups only.
    type_filter applies to diagram/document-collection groups only.
    """
    registry = load_group_registry(repo_root)
    entry = _require_entry(registry, axis, slug)
    is_model = axis == "model-project"
    updated = replace(
        entry,
        name=name if name is not None else entry.name,
        description=description if description is not None else entry.description,
        meta_ontology=(meta_ontology if meta_ontology is not None else entry.meta_ontology) if is_model else "",
        type_filter=(type_filter if type_filter is not None else entry.type_filter) if not is_model else (),
    )
    effects.persist_axis(repo_root, registry, axis, _replaced_entries(registry, axis, slug, updated))
    return {"action": "updated", "axis": axis, "slug": slug}


# ---------------------------------------------------------------------------
# Public dispatch
# ---------------------------------------------------------------------------


def group_op(
    repo_root: Path,
    *,
    axis: GroupAxis,
    action: GroupAction,
    target: str | None = None,
    name: str | None = None,
    new_slug: str | None = None,
    description: str = "",
    order: int = 0,
    confirm: str | None = None,
    dry_run: bool = False,
    meta_ontology: str = "",
    type_filter: list[str] | None = None,
) -> dict[str, object]:
    """Dispatch a group lifecycle operation and report what it did.

    Every action honours `dry_run`, and the result says so: `dry_run` echoes what was asked and
    `wrote` says whether the repository changed. A caller should never have to read a tool
    description to learn whether a call mutated anything — which is what every sibling write path
    already answers with.
    """
    slug = target or ""
    tf = tuple(type_filter) if type_filter is not None else None
    effects = PREVIEWED if dry_run else APPLIED
    handlers: dict[str, Callable[[], dict[str, object]]] = {
        "create": lambda: group_create(
            repo_root, axis=axis, slug=slug, name=name or slug, description=description,
            order=order, meta_ontology=meta_ontology, type_filter=tf or (), effects=effects,
        ),
        "rename": lambda: group_rename(
            repo_root, axis=axis, slug=slug, new_name=name, new_slug=new_slug, effects=effects
        ),
        "archive": lambda: group_archive(
            repo_root, axis=axis, slug=slug, confirm=confirm, effects=effects
        ),
        "unarchive": lambda: group_unarchive(repo_root, axis=axis, slug=slug, effects=effects),
        "delete": lambda: group_delete_collection(
            repo_root, axis=axis, slug=slug, confirm=confirm, dry_run=dry_run
        ),
        "update": lambda: group_update(
            repo_root, axis=axis, slug=slug, name=name, description=description or None,
            meta_ontology=meta_ontology or None, type_filter=tf, effects=effects,
        ),
    }
    handler = handlers.get(action)
    if handler is None:
        raise GroupOpError(
            f"Unknown action: {action!r}. Valid: create, rename, archive, unarchive, delete, update."
        )
    if not slug:
        hint = "existing slug" if action == "rename" else "slug"
        raise GroupOpError(f"target ({hint}) is required for action={action!r}.")
    result = handler()
    # A live cascade delete can decline to apply and say so; anything else that reached here without
    # raising has written exactly when the effects policy allowed it to.
    declined = result.get("applied") is False
    return {**result, "dry_run": dry_run, "wrote": effects.applies and not declined}
