"""Read an artifact record in the context of its repository mount and group."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from src.application.artifacts.parsing import (
    parse_diagram,
    parse_document,
    parse_entity,
    parse_outgoing_file,
)
from src.application.repo_path_helpers import (
    all_model_roots,
    group_fn_diagram,
    group_fn_document,
    group_fn_entity,
    group_fn_scratchpad,
)
from src.application.repository_confinement import is_within
from src.application.scratchpad.indexing import parse_scratchpad
from src.domain.ontology_representation.artifact_types import (
    ConnectionRecord,
    DiagramRecord,
    DocumentRecord,
    EntityRecord,
    RepoMount,
    ScratchpadNoteRecord,
    ScratchpadRecord,
)
from src.domain.repository.artifact_location import ArtifactKindName, artifact_kind_at
from src.domain.repository.repo_layout import MODEL

# ── Path classification helpers ───────────────────────────────────────────────


def mount_for_path(path: Path, mounts: list[RepoMount]) -> RepoMount | None:
    return next((m for m in mounts if is_within(path, m.root)), None)


def model_root_for_path(path: Path, mounts: list[RepoMount]) -> Path | None:
    """Return the nearest model root for path (supports both legacy and target layouts)."""
    mount = mount_for_path(path, mounts)
    if mount is None:
        return None
    # Check target layout first: projects/<slug>/model/
    for mroot in all_model_roots(mount.root):
        try:
            path.resolve().relative_to(mroot.resolve())
            return mroot
        except ValueError:
            continue
    # Fallback to legacy root
    return mount.root / MODEL


def artifact_kind_for_path(path: Path, mounts: list[RepoMount]) -> ArtifactKindName | None:
    """The kind of artifact *path* holds within the repository mounted over it, or None."""
    mount = mount_for_path(path, mounts)
    if mount is None:
        return None
    try:
        relative = path.resolve().relative_to(mount.root.resolve())
    except ValueError:
        return None
    return artifact_kind_at(relative)


# ── Incremental updates ───────────────────────────────────────────────────────

# Each change type has two phases:
#   parse_*  — reads the file from disk; call OUTSIDE the index write lock
#   apply_*  — updates mem and SQLite; call UNDER the index write lock


def parse_entity_for_path(
    path: Path, mounts: list[RepoMount], *, domain_names: frozenset[str]
) -> EntityRecord | None:
    mount = mount_for_path(path, mounts)
    model_root = model_root_for_path(path, mounts)
    if not path.exists() or mount is None or model_root is None:
        return None
    entity = parse_entity(path, model_root, domain_names=domain_names)
    return replace(entity, group=group_fn_entity(path, mount.root)) if entity is not None else None


def parse_outgoing_for_path(path: Path, mounts: list[RepoMount]) -> list[ConnectionRecord]:
    if not path.exists():
        return []
    mount = mount_for_path(path, mounts)
    if mount is None:
        return parse_outgoing_file(path)
    grp = group_fn_entity(path, mount.root)
    return [replace(conn, group=grp) for conn in parse_outgoing_file(path)]


def parse_diagram_for_path(path: Path, mounts: list[RepoMount]) -> DiagramRecord | None:
    if not path.exists():
        return None
    diag = parse_diagram(path)
    if diag is None:
        return None
    mount = mount_for_path(path, mounts)
    return replace(diag, group=group_fn_diagram(path, mount.root)) if mount is not None else diag


def parse_document_for_path(path: Path, mounts: list[RepoMount]) -> DocumentRecord | None:
    if not path.exists():
        return None
    doc = parse_document(path)
    if doc is None:
        return None
    mount = mount_for_path(path, mounts)
    return replace(doc, group=group_fn_document(path, mount.root)) if mount is not None else doc


def parse_scratchpad_for_path(
    path: Path, mounts: list[RepoMount]
) -> tuple[ScratchpadRecord | None, list[ScratchpadNoteRecord]]:
    """The pad and every note the file holds now.

    `(None, [])` when it was deleted, which is what removes its rows — both kinds of row, from one
    answer, so a deleted pad cannot leave its own record behind while its notes go.
    """
    mount = mount_for_path(path, mounts)
    if not path.exists() or mount is None:
        return None, []
    return parse_scratchpad(path, group=group_fn_scratchpad(path, mount.root))
