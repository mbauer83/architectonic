"""Temp-file + rename primitive: a reader never observes a half-written file.

The guarantee is atomic *replacement*, not durability. ``os.replace`` is atomic within a
filesystem, so a crash mid-write leaves either the previous content or the new content and
never a truncated mix. Surviving power loss additionally requires fsync, which the M4
transaction does for multi-file commits; a single-file write pays only for atomicity.

Used by every writer that replaces one file in place — artifact writes, deployment targets,
repository upgrades — so one glob pattern finds every stray temp file, whichever writer left
it behind, for ``sweep_stale_tmp_files`` to clean up.
"""

from __future__ import annotations

import os
from pathlib import Path

_TMP_GLOB = "*.tmp-*"


def write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    tmp_path.write_text(content, encoding="utf-8")
    os.replace(tmp_path, path)


def sweep_stale_tmp_files(repo_root: Path) -> list[str]:
    """Remove orphaned `write_atomic` temp files left by a process killed mid-write.

    Safe to call whenever no other upgrade process can be writing concurrently (i.e. after
    the backend-not-serving guard has passed) — a live writer's own in-progress temp file
    would only ever be visible here after that writer has already died.
    """
    removed: list[str] = []
    for tmp_path in repo_root.rglob(_TMP_GLOB):
        if tmp_path.is_file():
            tmp_path.unlink()
            removed.append(str(tmp_path.relative_to(repo_root)))
    return removed
