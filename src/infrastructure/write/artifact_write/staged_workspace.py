"""The copy-on-write staging tree a batch transaction writes into.

It holds only what has been written: a guarded write, unlink or rename symlinks the live file in
first, so a read of a *named* path falls through to the live repository. A directory **listing** has
nothing to fall through to, which is why enumeration goes through `overlay_paths` rather than
`Path.rglob` — see its docstring for what that cost.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

_ACTIVE_STAGED_ROOTS: set[Path] = set()
_ACTIVE_LIVE_ROOTS: dict[Path, Path] = {}
_DELETED_RELPATHS: dict[Path, set[Path]] = {}
"""Paths unlinked or renamed away inside a staged root, so a listing does not resurrect them from
the live tree. Without this an overlay listing would report a file the transaction has deleted."""
_ORIGINAL_WRITE_TEXT = Path.write_text
_ORIGINAL_UNLINK = Path.unlink
_ORIGINAL_RENAME = os.rename


class StagedWorkspace:
    """Symlink-backed staging tree with centralized copy-on-write materialization."""

    def __init__(self, *, live_root: Path, staged_root: Path) -> None:
        self.live_root = live_root
        self.staged_root = staged_root

    def create_mirror(self) -> None:
        self.staged_root.mkdir()

    def activate(self) -> None:
        staged_root = self.staged_root.resolve()
        _ACTIVE_STAGED_ROOTS.add(staged_root)
        _ACTIVE_LIVE_ROOTS[staged_root] = self.live_root.resolve()
        _install_guards()

    def deactivate(self) -> None:
        deactivate_staged_workspace(self.staged_root)

    def materialize(self, path: Path) -> None:
        _materialize_for_write(path, self.staged_root)


@contextmanager
def staged_workspace_guard(staged_root: Path):
    _ACTIVE_STAGED_ROOTS.add(staged_root.resolve())
    _install_guards()
    yield


def deactivate_staged_workspace(staged_root: Path) -> None:
    root = staged_root.resolve()
    _ACTIVE_STAGED_ROOTS.discard(root)
    _ACTIVE_LIVE_ROOTS.pop(root, None)
    _DELETED_RELPATHS.pop(root, None)


def overlay_paths(root: Path, patterns: Sequence[str]) -> Iterator[Path]:
    """Every path under *root* matching *patterns*, as the repository would list it.

    Outside a staged transaction this is `rglob`. Inside one it is the union of what the staging
    tree holds and what the live repository holds, expressed as paths under *root* — so a caller
    that enumerates and then writes still writes into the staging tree, and the guards materialize.

    An operation that enumerates rather than naming its paths — "every outgoing file that references
    this entity", "every document linking to this file" — otherwise sees an *empty* repository
    inside a batch, because a lazy overlay populates itself only for paths something has already
    touched. That is how a rename in `artifact_bulk_write` renamed an entity and left every referrer
    naming the old slug, while the identical rename outside a batch was correct.

    Deletions the transaction has made are honoured: a file it unlinked is not listed again from the
    live tree.
    """
    seen: set[Path] = set()
    for pattern in patterns:
        for path in sorted(root.rglob(pattern)):
            if path not in seen:
                seen.add(path)
                yield path
    # *root* is usually a directory *inside* the staged root — a model root, the docs tree — so the
    # enclosing transaction is what has to be found, not `root` itself.
    enclosing = _enclosing_staged_root(root)
    if enclosing is None:
        return
    staged_root, live_root = enclosing
    live_dir = live_root / root.absolute().relative_to(staged_root.absolute())
    deleted = _DELETED_RELPATHS.get(staged_root, set())
    for pattern in patterns:
        for live_path in sorted(live_dir.rglob(pattern)):
            if live_path.relative_to(live_root) in deleted:
                continue
            staged_path = root / live_path.relative_to(live_dir)
            if staged_path not in seen:
                seen.add(staged_path)
                # Symlinked in as it is listed, so the caller can *read* it: the read guard has no
                # hook, and a listed path that cannot be opened is not a listing. The copy still
                # happens only on write.
                stage_live_path(staged_path, live_path)
                yield staged_path


#: Directories never mirrored: git's own tree, and the transactions root itself — mirroring that
#: would walk the staging tree being created.
_SKELETON_EXCLUDED = frozenset({".git", ".arch-repo"})


def materialize_directory_skeleton(staged_root: Path) -> None:
    """Give *staged_root* the live repository's directory tree, leaving every file lazy.

    Called by the operations that need to *discover* where to look rather than to read a path they
    already name: building an index over a staged root walks `all_model_roots`, which asks
    `exists()` and `iterdir()`, gets an empty tree, finds no model roots, and answers every
    subsequent lookup `None`. `overlay_paths` cannot serve them — it lists files under a directory
    already known, and the directory is what is missing.

    Deliberately **not** part of creating the staging tree. Staging is O(1) by design and a fitness
    test holds it there; this is O(directories) and is paid by the caller that needs a full index,
    which is a whole-repository operation already. Directories are structure and cost one `mkdir`
    each; files stay copy-on-write.
    """
    enclosing = _enclosing_staged_root(staged_root)
    if enclosing is None:
        return
    _, live_root = enclosing
    for live_dir in sorted(p for p in live_root.rglob("*") if p.is_dir()):
        rel = live_dir.relative_to(live_root)
        if _SKELETON_EXCLUDED.intersection(rel.parts):
            continue
        (staged_root / rel).mkdir(parents=True, exist_ok=True)


def _enclosing_staged_root(path: Path) -> tuple[Path, Path] | None:
    """The (staged root, live root) pair whose staging tree contains *path*, if any."""
    for staged_root, live_root in _ACTIVE_LIVE_ROOTS.items():
        if _is_in_staged_root(path, staged_root):
            return staged_root, live_root
    return None


def live_root_for(path: Path) -> Path | None:
    """The live repository the staging tree containing *path* overlays, else None."""
    enclosing = _enclosing_staged_root(path)
    return None if enclosing is None else enclosing[1]


def _record_deleted(path: Path) -> None:
    for root in tuple(_ACTIVE_STAGED_ROOTS):
        if not _is_in_staged_root(path, root):
            continue
        rel = path.absolute().relative_to(root.absolute())
        _DELETED_RELPATHS.setdefault(root.resolve(), set()).add(rel)


def _record_written(path: Path) -> None:
    for root in tuple(_ACTIVE_STAGED_ROOTS):
        if not _is_in_staged_root(path, root):
            continue
        rel = path.absolute().relative_to(root.absolute())
        _DELETED_RELPATHS.get(root.resolve(), set()).discard(rel)


def stage_live_path(staged_path: Path, live_path: Path) -> Path:
    if staged_path.exists() or staged_path.is_symlink() or not live_path.exists():
        return staged_path
    staged_path.parent.mkdir(parents=True, exist_ok=True)
    if live_path.is_dir():
        staged_path.mkdir(exist_ok=True)
    else:
        staged_path.symlink_to(live_path)
    return staged_path


def _install_guards() -> None:
    if Path.write_text is _ORIGINAL_WRITE_TEXT:
        setattr(Path, "write_text", _guarded_write_text)
    if Path.unlink is _ORIGINAL_UNLINK:
        setattr(Path, "unlink", _guarded_unlink)
    if os.rename is _ORIGINAL_RENAME:
        setattr(os, "rename", _guarded_rename)


def _guarded_write_text(path: Path, data: str, *args: Any, **kwargs: Any):
    for root in tuple(_ACTIVE_STAGED_ROOTS):
        _stage_from_live_if_present(path, root)
        _materialize_for_write(path, root)
    _record_written(path)
    return _ORIGINAL_WRITE_TEXT(path, data, *args, **kwargs)


def _guarded_unlink(path: Path, *args: Any, **kwargs: Any):
    for root in tuple(_ACTIVE_STAGED_ROOTS):
        _stage_from_live_if_present(path, root)
    _record_deleted(path)
    return _ORIGINAL_UNLINK(path, *args, **kwargs)


def _guarded_rename(src: str | bytes | os.PathLike[Any], dst: str | bytes | os.PathLike[Any]) -> None:
    source = Path(os.fsdecode(src))
    dest = Path(os.fsdecode(dst))
    for root in tuple(_ACTIVE_STAGED_ROOTS):
        _stage_from_live_if_present(source, root)
        _materialize_for_write(source, root)
        _stage_from_live_if_present(dest, root)
        if _is_in_staged_root(dest, root) and dest.is_symlink():
            dest.unlink()
    _record_deleted(source)
    _record_written(dest)
    _ORIGINAL_RENAME(src, dst)


def _materialize_for_write(path: Path, staged_root: Path) -> None:
    if not _is_in_staged_root(path, staged_root) or not path.is_symlink():
        return
    target = path.resolve()
    path.unlink()
    if target.exists():
        shutil.copy2(target, path, follow_symlinks=True)


def _stage_from_live_if_present(path: Path, staged_root: Path) -> None:
    live_root = _ACTIVE_LIVE_ROOTS.get(staged_root.resolve())
    if live_root is None or not _is_in_staged_root(path, staged_root):
        return
    rel = path.absolute().relative_to(staged_root.absolute())
    stage_live_path(path, live_root / rel)


def _is_in_staged_root(path: Path, staged_root: Path) -> bool:
    try:
        path.absolute().relative_to(staged_root.absolute())
    except ValueError:
        return False
    return True
