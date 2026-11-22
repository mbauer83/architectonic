"""Scanning and incremental file-change handlers for ArtifactIndex."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from src.application._diagram_entity_extraction import (
    NOTHING_HELD,
    HeldRecordScope,
)
from src.application._diagram_entity_extraction import (
    extract_diagram_connections as _extract_diagram_connections,
)
from src.application._diagram_entity_extraction import (
    extract_diagram_entities as _extract_diagram_entities,
)
from src.application.artifacts.mounted_readers import artifact_kind_for_path
from src.application.change_sets.candidate_architecture import CandidateArchitecture
from src.domain.icons.icon_record import IconRecord
from src.domain.ontology_representation.artifact_types import (
    ConnectionRecord,
    DiagramRecord,
    DocumentRecord,
    EntityRecord,
    RepoMount,
    ScratchpadNoteRecord,
    ScratchpadRecord,
)
from src.domain.repository.artifact_location import ArtifactKindName
from src.domain.repository.repo_layout import SCRATCHPAD_SUFFIX
from src.infrastructure.candidates.repository import KIND
from src.infrastructure.verification.kind_bindings import KIND_BINDINGS

from ._mem_store import _MemStore
from ._service_scan import _AttrTypeRefFn
from ._sqlite_store import _SqliteStore


def classify_path_change(
    path: Path, mounts: list[RepoMount], *, domain_names: frozenset[str]
) -> tuple[ArtifactKindName, Path, object] | None:
    """Return a (kind, path, parsed-data) triple, or None when a full refresh must answer instead.

    A path that holds no artifact where it sits is None: a full scan would not index it either, so
    only a refresh keeps the two views in agreement.
    """
    kind = artifact_kind_for_path(path, mounts)
    return None if kind is None else (kind, path, KIND_BINDINGS[kind].reader(path, mounts, domain_names))


def apply_candidate_change(path: Path, candidate: CandidateArchitecture | None, mem: _MemStore) -> None:
    mem.candidate_paths.pop(KIND.file_identity(path), None)
    if candidate is not None:
        mem.candidate_paths[candidate.id] = path


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
    record_scopes: Mapping[str, HeldRecordScope] | None = None,
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
        scope = (record_scopes or {}).get(parsed.diagram_type, NOTHING_HELD)
        # Upsert diagram-local entities first so the diagram's FTS row (built in
        # upsert_diagram) can resolve their names via entities_by_diagram.
        for de in _extract_diagram_entities(parsed, scope):
            db.upsert_entity(de)
        for dc in _extract_diagram_connections(parsed, scope):
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


def apply_icon_change(path: Path, mem: _MemStore, *, parsed: IconRecord | None) -> None:
    """Icons are held in memory only: the picker filters them there, and nothing searches them."""
    resolved = path.resolve()
    if (old_id := mem.icon_by_path.pop(resolved, None)) is not None:
        mem.icons.pop(old_id, None)
    if parsed is not None:
        mem.icons[parsed.artifact_id] = parsed
        mem.icon_by_path[resolved] = parsed.artifact_id
