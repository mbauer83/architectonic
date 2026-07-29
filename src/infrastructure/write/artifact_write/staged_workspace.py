from __future__ import annotations

import os
import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import Any

_ACTIVE_STAGED_ROOTS: set[Path] = set()
_ACTIVE_LIVE_ROOTS: dict[Path, Path] = {}
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
    return _ORIGINAL_WRITE_TEXT(path, data, *args, **kwargs)


def _guarded_unlink(path: Path, *args: Any, **kwargs: Any):
    for root in tuple(_ACTIVE_STAGED_ROOTS):
        _stage_from_live_if_present(path, root)
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
