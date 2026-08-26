"""Scanning and incremental file-change handlers for ArtifactIndex."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from src.application._diagram_entity_extraction import (
    extract_diagram_connections as _extract_diagram_connections,
)
from src.application._diagram_entity_extraction import (
    extract_diagram_entities as _extract_diagram_entities,
)
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
from src.application.scratchpad.indexing import parse_scratchpad
from src.config.repo_paths import DOCS, MODEL
from src.domain.ontology_representation.artifact_types import (
    ConnectionRecord,
    DiagramRecord,
    DocumentRecord,
    EntityRecord,
    RepoMount,
    ScratchpadNoteRecord,
    ScratchpadRecord,
)
from src.domain.repository.repo_layout import ARTIFACT_SOURCE_SUFFIXES, SCRATCHPAD_SUFFIX, SCRATCHPADS

from ._mem_store import _MemStore
from ._service_scan import _AttrTypeRefFn
from ._sqlite_store import _SqliteStore

# ── Path classification helpers ───────────────────────────────────────────────


def mount_for_path(path: Path, mounts: list[RepoMount]) -> RepoMount | None:
    resolved = path.resolve()
    return next((m for m in mounts if resolved.is_relative_to(m.root)), None)


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


def is_diagram_source_path(path: Path, mounts: list[RepoMount]) -> bool:
    mount = mount_for_path(path, mounts)
    if mount is None:
        return False
    try:
        rel = path.resolve().relative_to(mount.root.resolve()).as_posix()
    except ValueError:
        return False
    return rel.startswith("diagram-catalog/diagrams/") and path.suffix in ARTIFACT_SOURCE_SUFFIXES


def is_document_path(path: Path, mounts: list[RepoMount]) -> bool:
    mount = mount_for_path(path, mounts)
    if mount is None:
        return False
    try:
        rel = path.resolve().relative_to(mount.root.resolve()).as_posix()
    except ValueError:
        return False
    return rel.startswith(f"{DOCS}/") and path.suffix == ".md"


def is_scratchpad_path(path: Path, mounts: list[RepoMount]) -> bool:
    mount = mount_for_path(path, mounts)
    if mount is None:
        return False
    try:
        rel = path.resolve().relative_to(mount.root.resolve()).as_posix()
    except ValueError:
        return False
    return rel.startswith(f"{SCRATCHPADS}/") and path.name.endswith(SCRATCHPAD_SUFFIX)


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


def classify_path_change(
    path: Path, mounts: list[RepoMount], *, domain_names: frozenset[str]
) -> tuple[str, Path, object] | None:
    """Return a (kind, path, parsed-data) triple or None if the path needs a full refresh."""
    if path.name.endswith(".outgoing.md"):
        return ("outgoing", path, parse_outgoing_for_path(path, mounts))
    if is_diagram_source_path(path, mounts):
        return ("diagram", path, parse_diagram_for_path(path, mounts))
    if is_document_path(path, mounts):
        return ("document", path, parse_document_for_path(path, mounts))
    if is_scratchpad_path(path, mounts):
        return ("scratchpad", path, parse_scratchpad_for_path(path, mounts))
    if path.suffix == ".md":
        return ("entity", path, parse_entity_for_path(path, mounts, domain_names=domain_names))
    return None


def _touching_endpoints(entity_id: str, mem: _MemStore) -> set[str]:
    """*entity_id* plus the far endpoint of every connection touching it."""
    endpoints = {entity_id}
    for cid in mem.connections_by_entity.get(entity_id, set()):
        r = mem.connections.get(cid)
        if r is not None:
            endpoints.add(r.source if r.source != entity_id else r.target)
    return endpoints


def _apply_entity_record(path: Path, new: EntityRecord | None, mem: _MemStore, db: _SqliteStore) -> None:
    old_id = mem.entity_by_path.get(path.resolve())
    old = mem.entities.get(old_id) if old_id else None

    impacted: set[str] = set()
    if old is not None:
        impacted |= _touching_endpoints(old.artifact_id, mem)
        if new is None or old.artifact_id != new.artifact_id:
            db.delete_entity(old.artifact_id)
    if new is not None:
        db.upsert_entity(new)
        impacted |= _touching_endpoints(new.artifact_id, mem)
    for eid in sorted(impacted):
        db.rebuild_context_for(eid)


def _apply_outgoing_records(path: Path, new_recs: list[ConnectionRecord], mem: _MemStore, db: _SqliteStore) -> None:
    # upsert_connection canonicalizes on the way in, but the affected-entity set below is
    # derived here: computed from raw endpoints it would rebuild context for an id no entity
    # has and skip the one that changed. Same shared rule, applied where the ids are read.
    new_recs = [mem.canonical_connection(rec) for rec in new_recs]
    old_ids = mem.connections_by_path.get(path.resolve(), set())
    old_recs = [mem.connections[cid] for cid in old_ids if cid in mem.connections]

    affected = {eid for r in old_recs + new_recs for eid in (r.source, r.target)}
    removed = {r.artifact_id for r in old_recs} - {r.artifact_id for r in new_recs}
    for aid in sorted(removed):
        db.delete_connection(aid)
    for rec in new_recs:
        db.upsert_connection(rec)
    for eid in sorted(affected):
        db.rebuild_context_for(eid)


def apply_diagram_change(
    path: Path,
    mem: _MemStore,
    db: _SqliteStore,
    *,
    parsed: DiagramRecord | None,
    workspace_types: dict[str, frozenset[str]] | None = None,
    attr_type_ref_fn: _AttrTypeRefFn | None = None,
) -> None:
    old_id = mem.diagram_by_path.get(path.resolve())
    old = mem.diagrams.get(old_id) if old_id else None
    if old is not None:
        _delete_diagram_entities(old.artifact_id, mem, db)
        _delete_diagram_connections(old.artifact_id, mem, db)
        db.delete_attribute_type_refs(old.artifact_id)
        if parsed is None or old.artifact_id != parsed.artifact_id:
            db.delete_diagram(old.artifact_id)
    if parsed is not None:
        ws = (workspace_types or {}).get(parsed.diagram_type, frozenset())
        # Upsert diagram-local entities first so the diagram's FTS row (built in
        # upsert_diagram) can resolve their names via entities_by_diagram.
        for de in _extract_diagram_entities(parsed, ws):
            db.upsert_entity(de)
        for dc in _extract_diagram_connections(parsed, ws):
            db.upsert_connection(dc)
        db.upsert_diagram(parsed)
        refs = attr_type_ref_fn(parsed) if attr_type_ref_fn is not None else []
        db.upsert_attribute_type_refs(parsed.artifact_id, refs)


def _delete_diagram_entities(diagram_id: str, mem: _MemStore, db: _SqliteStore) -> None:
    owned = list(mem.entities_by_diagram.get(diagram_id, set()))
    for aid in owned:
        db.delete_entity(aid)


def _delete_diagram_connections(diagram_id: str, mem: _MemStore, db: _SqliteStore) -> None:
    owned = list(mem.connections_by_diagram.get(diagram_id, set()))
    for aid in owned:
        db.delete_connection(aid)



def apply_scratchpad_change(
    path: Path,
    mem: _MemStore,
    db: _SqliteStore,
    *,
    parsed: tuple[ScratchpadRecord | None, list[ScratchpadNoteRecord]],
) -> None:
    """Re-index one scratchpad, whole: the pad and its notes, in one replacement.

    The scratchpad id comes from the pad, then from the notes, then from the path — a file emptied of
    notes, or made unreadable, or deleted, still has to take its old rows with it, and the filename
    carries the id because that is what the repository names it by. Taking it from the pad first
    matters for the case a pad exists and its notes have all been lifted: there are no notes to ask.
    """
    pad, notes = parsed
    scratchpad_id = (
        pad.artifact_id if pad is not None
        else notes[0].scratchpad_id if notes
        else path.name[: -len(SCRATCHPAD_SUFFIX)]
    )
    db.replace_scratchpad(scratchpad_id, pad, notes)


def apply_document_change(
    path: Path,
    mem: _MemStore,
    db: _SqliteStore,
    *,
    parsed: DocumentRecord | None,
) -> None:
    old_id = mem.document_by_path.get(path.resolve())
    old = mem.documents.get(old_id) if old_id else None
    if old is not None and (parsed is None or old.artifact_id != parsed.artifact_id):
        db.delete_document(old.artifact_id)
    if parsed is not None:
        db.upsert_document(parsed)
