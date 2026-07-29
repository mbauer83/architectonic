"""Build a deployment tree as an earlier release left it.

The one definition of "a previous-release deployment", shared by the local-CLI and the
Docker upgrade tests so the two can never drift. Every artifact is written at the path the
*current* resolver resolves for that deployment root — the fixture asks the resolver where a
target lives rather than hard-coding a filename, so a change to a path default updates the
fixture automatically instead of silently stranding it.

The layout deliberately mixes surfaces the upgrade must migrate (an old-format guidance
cache, an old-schema signals database) with content it must leave alone (an operator note
beside the cache, extra keys inside a migrated document), plus an optional unreadable
encrypted store to exercise the blocking path.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from src.domain.deployment.layout import CliSelectors, DeploymentManifest
from src.infrastructure.deployment.layout import resolve_manifest

#: A file the guidance-cache step has no opinion about (not ``*.guidance.yaml``).
UNRELATED_NOTE_NAME = "operator-notes.txt"
UNRELATED_NOTE_BODY = "hand-written operator note the migrator must never touch\n"
GUIDANCE_DOC_NAME = "core.guidance.yaml"
#: A body key beside the format header — the header patch must preserve it verbatim.
GUIDANCE_BODY = "entries: []\n"


@dataclass(frozen=True)
class PreviousReleaseDeployment:
    """A built deployment and the resolved locations a test asserts against."""

    root: Path
    manifest: DeploymentManifest

    @property
    def guidance_doc(self) -> Path:
        return self.manifest.guidance_cache_root.path / GUIDANCE_DOC_NAME

    @property
    def unrelated_note(self) -> Path:
        return self.manifest.guidance_cache_root.path / UNRELATED_NOTE_NAME

    @property
    def signals_db(self) -> Path:
        return self.manifest.signals_db_path.path

    @property
    def store_db(self) -> Path:
        return self.manifest.assurance_db_path.path


def build_previous_release_deployment(
    root: Path,
    *,
    guidance_format: int = 1,
    guidance_body: str = GUIDANCE_BODY,
    with_signals: bool = True,
    locked_store: bool = False,
) -> PreviousReleaseDeployment:
    manifest = resolve_manifest(CliSelectors(deployment_root=str(root)), {})
    _write(manifest.settings_document.path, "storage:\n  assurance:\n    signals_backend: sqlite\n")
    _write(
        manifest.guidance_cache_root.path / GUIDANCE_DOC_NAME,
        f"guidance_format: {guidance_format}\n{guidance_body}",
    )
    _write(manifest.guidance_cache_root.path / UNRELATED_NOTE_NAME, UNRELATED_NOTE_BODY)
    if with_signals:
        db = manifest.signals_db_path.path
        db.parent.mkdir(parents=True, exist_ok=True)
        sqlite3.connect(str(db)).close()  # empty file → schema version defaults to 1
    if locked_store:
        # An encrypted store with no available key: unreadable, so uninspectable → blocking.
        _write_bytes(manifest.assurance_db_path.path, b"SQLite format 3\x00opaque-ciphertext")
    return PreviousReleaseDeployment(root=root, manifest=manifest)


def signals_schema_version(db: Path) -> int | None:
    """The stamped signals schema version, or None when the store carries no stamp yet."""
    if not db.is_file():
        return None
    conn = sqlite3.connect(str(db))
    try:
        stamped = conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='signals_schema_meta'"
        ).fetchone()
        if not stamped or not stamped[0]:
            return None
        row = conn.execute(
            "SELECT value FROM signals_schema_meta WHERE key='schema_version'"
        ).fetchone()
        return int(row[0]) if row else None
    finally:
        conn.close()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
