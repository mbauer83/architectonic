from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

from src.application.ports import Candidate
from src.domain.artifact_id import canonical_reference_key, stable_conn_id, stable_id
from src.domain.ontology_representation.artifact_types import (
    ConnectionRecord,
    DiagramRecord,
    DocumentRecord,
    EntityRecord,
    ScratchpadNoteRecord,
)


@dataclass
class _MemStore:
    entities: dict[str, EntityRecord] = field(default_factory=dict)
    connections: dict[str, ConnectionRecord] = field(default_factory=dict)
    diagrams: dict[str, DiagramRecord] = field(default_factory=dict)
    documents: dict[str, DocumentRecord] = field(default_factory=dict)
    scratchpad_notes: dict[str, ScratchpadNoteRecord] = field(default_factory=dict)
    """note address → the note. Keyed by `{scratchpad_id}#note/{note_id}`; a note id is unique
    only within its own scratchpad."""
    notes_by_scratchpad: dict[str, set[str]] = field(default_factory=dict)
    """scratchpad artifact_id → the addresses of its notes, so re-indexing one file is O(K)."""
    entity_by_path: dict[Path, str] = field(default_factory=dict)
    connections_by_path: dict[Path, set[str]] = field(default_factory=dict)
    connections_by_entity: dict[str, set[str]] = field(default_factory=dict)
    diagram_by_path: dict[Path, str] = field(default_factory=dict)
    document_by_path: dict[Path, str] = field(default_factory=dict)
    entities_by_diagram: dict[str, set[str]] = field(default_factory=dict)
    """diagram_id → set of diagram-only entity artifact_ids owned by that diagram."""
    connections_by_diagram: dict[str, set[str]] = field(default_factory=dict)
    """diagram_id → set of diagram-owned connection artifact_ids (artifact_id contains '#conn/')."""
    diagrams_by_reference: dict[str, set[str]] = field(default_factory=dict)
    """entity/connection artifact_id → set of diagram artifact_ids referencing it."""
    grf_targets_by_entity: dict[str, set[str]] = field(default_factory=dict)
    """global-artifact-id target → set of global-entity-reference entity artifact_ids."""
    attribute_type_refs: dict[str, list[tuple[str, str, str]]] = field(default_factory=dict)
    """diagram_id → [(classifier_local_id, attr_name, type_id)] for classifier-typed attributes."""
    identity_candidates: dict[str, list[Candidate]] = field(default_factory=dict)
    """stable_id → all Candidate files ever indexed under that stable key (cross-mount multimap)."""

    def canonical_id(self, artifact_id: str) -> str:
        """Resolve a short or stale-slug id to the stored full id (any artifact kind).

        Lets readers pass either form: an exact hit wins; otherwise the unique
        record whose stable id matches is returned. Falls back to *artifact_id*
        unchanged when it is absent or ambiguous across mounts (so the caller's
        own lookup then misses safely). Must be called under the index read lock.

        Connection ids (``source---target@@type``) are not entity-shaped and are
        handled separately: ``stable_id()`` finds the *last* dot in a string, which
        for a composite connection id falls inside the target segment, not after a
        connection-type suffix. Applying it to the whole composite string (as the
        generic fallback below does for entities/diagrams/documents) silently drops
        the type and makes two different connection types between the same two
        entities collide on the same "stable id" — a real bug this branch exists to
        avoid, not a hypothetical one (caught by WU-F3a's exchange re-import test).
        """
        stores = (self.entities, self.connections, self.diagrams, self.documents)
        if any(artifact_id in store for store in stores):
            return artifact_id
        if "---" in artifact_id and "@@" in artifact_id:
            normalized_connection_id = stable_conn_id(artifact_id)
            return normalized_connection_id if normalized_connection_id in self.connections else artifact_id
        short = stable_id(artifact_id)
        for store in stores:
            matches = [key for key in store if stable_id(key) == short]
            if len(matches) == 1:
                return matches[0]
        return artifact_id

    def entity(self, artifact_id: str) -> EntityRecord | None:
        """The entity under any id form the caller has — short, stale-slug, or full.

        Canonicalisation belongs beside `canonical_id`, not repeated at each reader. Spelling the
        two steps out per call site is what let three readers omit the first one, so the entity read
        answered for a short id while its context read reported it absent.
        """
        return self.entities.get(self.canonical_id(artifact_id))

    def connection(self, artifact_id: str) -> ConnectionRecord | None:
        return self.connections.get(self.canonical_id(artifact_id))

    def diagram(self, artifact_id: str) -> DiagramRecord | None:
        return self.diagrams.get(self.canonical_id(artifact_id))

    def document(self, artifact_id: str) -> DocumentRecord | None:
        return self.documents.get(self.canonical_id(artifact_id))

    def scratchpad_note(self, artifact_id: str) -> ScratchpadNoteRecord | None:
        """A note by its composed address. Not canonicalized: `canonical_id` reads the *last* dot
        of an id to find its stable stem, and a note address ends in a minted local id with no
        slug, so there is nothing to reconcile and a stale-slug scratchpad id is not a form
        anything produces."""
        return self.scratchpad_notes.get(artifact_id)

    def clear(self) -> None:
        for attr in (
            "entities",
            "connections",
            "diagrams",
            "documents",
            "scratchpad_notes",
            "notes_by_scratchpad",
            "entity_by_path",
            "connections_by_path",
            "connections_by_entity",
            "diagram_by_path",
            "document_by_path",
            "entities_by_diagram",
            "connections_by_diagram",
            "diagrams_by_reference",
            "grf_targets_by_entity",
            "attribute_type_refs",
            "identity_candidates",
        ):
            getattr(self, attr).clear()

    def replace_from(self, other: _MemStore) -> None:
        """Adopt *other*'s records, leaving this store internally consistent.

        Canonicalizing here rather than at the call site makes it the store's own invariant:
        no caller has to remember that a freshly scanned set of records may still name
        entities by a slug they no longer carry.
        """
        for attr in (
            "entities", "connections", "diagrams", "documents", "scratchpad_notes",
            "identity_candidates", "attribute_type_refs",
        ):
            getattr(self, attr).clear()
            getattr(self, attr).update(getattr(other, attr))
        self.canonicalize_connection_endpoints()

    def canonicalize_connection_endpoints(self) -> int:
        """Rewrite every connection's source/target to the entity id actually indexed.

        The slug tail of an artifact id is a human-readable hint, not identity: identity is
        the ``PREFIX@epoch.random`` stem, which is why ``artifact_id`` is built from
        ``stable_id`` on both ends. An ``.outgoing.md`` naming a target by an older slug
        therefore still designates the right entity, and every consumer must see it that
        way — a record left holding the literal file text resolves no name and matches no
        entity in a population join, so the connection silently disappears from queries,
        explorations and diagrams while the file looks fine.

        Runs once per full scan, after all mounts are in and before the derived indexes and
        the SQLite dump, because a connection may point at an entity indexed from a later
        mount or model root; resolving during the scan would make the outcome depend on
        directory order. Returns the number of records changed so callers can report drift.
        """
        changed = 0
        for key, record in self.connections.items():
            canonical = self.canonical_connection(record)
            if canonical is record:
                continue
            self.connections[key] = canonical
            changed += 1
        return changed

    def put_connection(self, record: ConnectionRecord) -> ConnectionRecord:
        """Store one connection, canonicalized and re-indexed. Returns what was stored.

        The single incremental entry point for a connection record, so no producer can admit
        one naming an entity by a slug it no longer has. The bulk path is handled by
        ``replace_from``, which cannot resolve until every mount has been scanned.
        """
        record = self.canonical_connection(record)
        previous = self.connections.get(record.artifact_id)
        if previous is not None:
            self.unindex_connection(previous)
        self.connections[record.artifact_id] = record
        self.index_connection(record)
        return record

    def canonical_connection(self, record: ConnectionRecord) -> ConnectionRecord:
        """*record* with both endpoints resolved to the entity ids actually indexed.

        Returned unchanged (identical object) when both already match, so callers can use
        identity to detect drift. The single rule both the full scan and the incremental
        applier go through, so a connection cannot enter the read model holding an endpoint
        no consumer can join on.
        """
        source = self.canonical_id(record.source)
        target = self.canonical_id(record.target)
        if source == record.source and target == record.target:
            return record
        return replace(record, source=source, target=target)

    def rebuild_path_indexes(self) -> None:
        self.entity_by_path = {
            r.path.resolve(): r.artifact_id for r in self.entities.values() if r.host_diagram_id is None
        }
        self.entities_by_diagram = {}
        self.grf_targets_by_entity = {}
        for r in self.entities.values():
            if r.host_diagram_id is not None:
                self.entities_by_diagram.setdefault(r.host_diagram_id, set()).add(r.artifact_id)
            target = r.extra.get("global-artifact-id")
            if isinstance(target, str) and target.strip():
                self.grf_targets_by_entity.setdefault(target.strip(), set()).add(r.artifact_id)
        self.diagram_by_path = {r.path.resolve(): r.artifact_id for r in self.diagrams.values()}
        self.diagrams_by_reference = {}
        for r in self.diagrams.values():
            for ref_id in _diagram_reference_ids(r):
                self.diagrams_by_reference.setdefault(ref_id, set()).add(r.artifact_id)
        self.document_by_path = {r.path.resolve(): r.artifact_id for r in self.documents.values()}
        notes_by_pad: dict[str, set[str]] = {}
        for r in self.scratchpad_notes.values():
            notes_by_pad.setdefault(r.scratchpad_id, set()).add(r.artifact_id)
        self.notes_by_scratchpad = notes_by_pad
        by_path: dict[Path, set[str]] = {}
        by_entity: dict[str, set[str]] = {}
        by_diagram: dict[str, set[str]] = {}
        for r in self.connections.values():
            by_path.setdefault(r.path.resolve(), set()).add(r.artifact_id)
            by_entity.setdefault(r.source, set()).add(r.artifact_id)
            by_entity.setdefault(r.target, set()).add(r.artifact_id)
            if "#conn/" in r.artifact_id:
                diagram_id = r.artifact_id.split("#conn/")[0]
                by_diagram.setdefault(diagram_id, set()).add(r.artifact_id)
        self.connections_by_path = by_path
        self.connections_by_entity = by_entity
        self.connections_by_diagram = by_diagram

    def index_entity(self, rec: EntityRecord) -> None:
        if rec.host_diagram_id is None:
            self.entity_by_path[rec.path.resolve()] = rec.artifact_id
        else:
            self.entities_by_diagram.setdefault(rec.host_diagram_id, set()).add(rec.artifact_id)
        if (target := _entity_global_target(rec)) is not None:
            self.grf_targets_by_entity.setdefault(target, set()).add(rec.artifact_id)

    def unindex_entity(self, rec: EntityRecord) -> None:
        if (target := _entity_global_target(rec)) is not None:
            _discard_from(self.grf_targets_by_entity, target, rec.artifact_id)
        if rec.host_diagram_id is None:
            self.entity_by_path.pop(rec.path.resolve(), None)
        else:
            _discard_from(self.entities_by_diagram, rec.host_diagram_id, rec.artifact_id)

    def index_connection(self, rec: ConnectionRecord) -> None:
        self.connections_by_path.setdefault(rec.path.resolve(), set()).add(rec.artifact_id)
        self.connections_by_entity.setdefault(rec.source, set()).add(rec.artifact_id)
        self.connections_by_entity.setdefault(rec.target, set()).add(rec.artifact_id)
        if "#conn/" in rec.artifact_id:
            self.connections_by_diagram.setdefault(rec.artifact_id.split("#conn/")[0], set()).add(rec.artifact_id)

    def unindex_connection(self, rec: ConnectionRecord) -> None:
        _discard_from(self.connections_by_path, rec.path.resolve(), rec.artifact_id)
        for eid in (rec.source, rec.target):
            _discard_from(self.connections_by_entity, eid, rec.artifact_id)
        if "#conn/" in rec.artifact_id:
            _discard_from(self.connections_by_diagram, rec.artifact_id.split("#conn/")[0], rec.artifact_id)

    def index_diagram(self, rec: DiagramRecord) -> None:
        self.diagram_by_path[rec.path.resolve()] = rec.artifact_id
        for ref_id in _diagram_reference_ids(rec):
            self.diagrams_by_reference.setdefault(ref_id, set()).add(rec.artifact_id)

    def unindex_diagram(self, rec: DiagramRecord) -> None:
        self.diagram_by_path.pop(rec.path.resolve(), None)
        for ref_id in _diagram_reference_ids(rec):
            _discard_from(self.diagrams_by_reference, ref_id, rec.artifact_id)


def _diagram_reference_ids(rec: DiagramRecord) -> set[str]:
    """What this diagram refers to, keyed the way a reader will ask for it.

    Canonical rather than verbatim, because short and full spellings of an id name the same
    artifact and diagram writers disagree about which to record — see ``canonical_reference_key``.
    Matching the string as written made this the one reverse lookup in the project that treated the
    two as different artifacts, and every caller inherited the blindness.
    """
    return {
        canonical_reference_key(str(item))
        for key in ("entity-ids-used", "connection-ids-used")
        if isinstance(raw := rec.extra.get(key), list)
        for item in raw
        if str(item)
    }


def _entity_global_target(rec: EntityRecord) -> str | None:
    target = rec.extra.get("global-artifact-id")
    return target.strip() if isinstance(target, str) and target.strip() else None


def _discard_from(d: dict, key: object, val: str) -> None:
    if s := d.get(key):
        s.discard(val)
        if not s:
            del d[key]
