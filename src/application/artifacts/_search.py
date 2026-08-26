"""Standalone search functions for ArtifactRepository."""

from __future__ import annotations

from typing import cast

from src.application._search_eligibility import EntityEligibility, semantic_entity_hits
from src.application.artifacts._ranking import rank_hits
from src.application.artifacts.scoring import (
    score_connection,
    score_diagram,
    score_document,
    score_entity,
    score_scratchpad,
    score_scratchpad_note,
    tokenize,
)
from src.application.ports import ReadableArtifactStore
from src.domain.ontology_representation.artifact_types import (
    ConnectionRecord,
    DiagramRecord,
    DocumentRecord,
    EntityRecord,
    ScratchpadNoteRecord,
    ScratchpadRecord,
    SearchHit,
    SearchResult,
)
from src.domain.search_records import (
    ALL_SEARCHABLE_KINDS,
    KIND_TO_RECORD_TYPE,
    RECORD_TYPE_TO_KIND,
    RecordType,
    SearchableKind,
    SemanticSearchProvider,
)

# The vocabulary is imported from where it is declared, and the record types from where *they* are:
# `artifact_types` re-exports the vocabulary for the callers that predate the split, but new
# references go to its home. These names stay importable from here because every caller already
# reaches for them here.
__all__ = [
    "ALL_SEARCHABLE_KINDS",
    "RecordType",
    "SearchableKind",
    "search",
    "search_artifacts",
]

_RecordType = RecordType  # internal alias for cast()


def search_artifacts(
    store: ReadableArtifactStore,
    semantic: SemanticSearchProvider | None,
    query: str,
    *,
    limit: int = 10,
    domain: str | list[str] | None = None,
    artifact_type: str | list[str] | None = None,
    include_entities: bool = True,
    include_connections: bool = True,
    include_diagrams: bool = True,
    include_documents: bool = True,
    include_scratchpads: bool = True,
    include_scratchpad_notes: bool = True,
    prefer_record_type: RecordType | None = None,
    strict_record_type: bool = False,
    excluded_entity_types: frozenset[str] = frozenset(),
    visible_diagram_entity_types: frozenset[str] | None = None,
) -> SearchResult:
    """One flag per kind, as the REST query parameters have — mapped to the kind set ``search`` wants.

    Notes are in by default because "indexed and findable" was the decision; the one caller that
    must not see them is the *picker*, which offers content to reference and turns them off by name.
    """
    kinds: set[str] = set()
    if include_entities:
        kinds.add("entities")
    if include_connections:
        kinds.add("connections")
    if include_diagrams:
        kinds.add("diagrams")
    if include_documents:
        kinds.add("documents")
    if include_scratchpads:
        kinds.add("scratchpads")
    if include_scratchpad_notes:
        kinds.add("scratchpad-notes")
    # strict_record_type: restrict search to just the preferred kind.
    if strict_record_type and prefer_record_type is not None:
        kind = RECORD_TYPE_TO_KIND.get(prefer_record_type)
        if kind:
            kinds = {kind}
    prefer_kind = RECORD_TYPE_TO_KIND.get(prefer_record_type) if prefer_record_type else None
    domains = domain if isinstance(domain, list) else ([domain] if domain else None)
    entity_types = artifact_type if isinstance(artifact_type, list) else ([artifact_type] if artifact_type else None)
    return search(
        store,
        semantic,
        query,
        limit=limit,
        domains=domains,
        entity_types=entity_types,
        included_kinds=frozenset(kinds),
        prefer_kind=prefer_kind,
        excluded_entity_types=excluded_entity_types,
        visible_diagram_entity_types=visible_diagram_entity_types,
    )


def search(
    store: ReadableArtifactStore,
    semantic: SemanticSearchProvider | None,
    query: str,
    *,
    limit: int = 10,
    entity_types: list[str] | None = None,
    domains: list[str] | None = None,
    included_kinds: frozenset[str] | None = None,
    prefer_kind: str | None = None,
    excluded_entity_types: frozenset[str] = frozenset(),
    visible_diagram_entity_types: frozenset[str] | None = None,
) -> SearchResult:
    """Search across requested kinds with per-kind FTS + scored supplement.

    ``included_kinds`` selects which record kinds participate (default: all four).
    Per-kind FTS limits prevent a dominant kind from starving minority kinds in
    the ranked results. For any included kind that returns zero FTS hits, the
    full scored path supplements.
    ``prefer_kind`` boosts one kind in cross-kind ranking without excluding others.
    ``excluded_entity_types`` hides those entity types from every branch; an
    explicit entity-type request fully consumed by the exclusion set yields zero
    entity hits.
    """
    kinds = (included_kinds if included_kinds is not None else ALL_SEARCHABLE_KINDS) & ALL_SEARCHABLE_KINDS
    query_lc = query.lower()
    tokens = tokenize(query_lc)
    eligibility = EntityEligibility.build(
        excluded_entity_types, entity_types, domains, visible_diagram_entity_types
    )
    if eligibility.effective_request_is_empty:
        kinds = kinds - {"entities"}

    # Per-kind FTS: each kind gets its own slot budget to prevent starvation.
    per_kind_limit = max(limit * 2, 10)
    fts_hits = store.search_fts(
        query,
        limit=per_kind_limit,
        kinds=frozenset(kinds),
        excluded_entity_types=excluded_entity_types,
        visible_diagram_entity_types=visible_diagram_entity_types,
    )

    seen: set[tuple[str, str]] = set()
    hits: list[SearchHit] = []
    fts_kinds_with_hits: set[str] = set()

    for artifact_id, record_type, score in fts_hits:
        artifact: (
            EntityRecord
            | ConnectionRecord
            | DiagramRecord
            | DocumentRecord
            | ScratchpadRecord
            | ScratchpadNoteRecord
            | None
        )
        match record_type:
            case "entity":
                artifact = store.get_entity(artifact_id)
                if artifact is None or not eligibility.is_eligible(artifact):
                    continue
            case "connection":
                artifact = store.get_connection(artifact_id)
                if artifact is None:
                    continue
            case "document":
                artifact = store.get_document(artifact_id)
                if artifact is None:
                    continue
            case "diagram":
                artifact = store.get_diagram(artifact_id)
                if artifact is None:
                    continue
            case "scratchpad":
                artifact = store.get_scratchpad(artifact_id)
                if artifact is None:
                    continue
            case "scratchpad-note":
                artifact = store.get_scratchpad_note(artifact_id)
                if artifact is None:
                    continue
            case _:
                continue
        key = (record_type, artifact_id)
        if key in seen:
            continue
        seen.add(key)
        fts_kinds_with_hits.add(RECORD_TYPE_TO_KIND.get(record_type, ""))
        hits.append(SearchHit(score=score, record_type=cast(_RecordType, record_type), record=artifact))

    # Supplement scored path for any included kind that got zero FTS hits.
    for kind in kinds:
        if kind in fts_kinds_with_hits:
            continue
        match kind:
            case "entities":
                scored = _search_entities(store, query_lc, tokens, eligibility)
            case "connections":
                scored = _search_connections(store, query_lc, tokens)
            case "diagrams":
                scored = _search_diagrams(store, query_lc, tokens)
            case "documents":
                scored = _search_documents(store, query_lc, tokens)
            case "scratchpads":
                scored = _search_scratchpads(store, query_lc, tokens)
            case "scratchpad-notes":
                scored = _search_scratchpad_notes(store, query_lc, tokens)
            case _:
                scored = []
        for h in scored:
            key = (h.record_type, h.record.artifact_id)
            if key not in seen:
                seen.add(key)
                hits.append(h)

    # Semantic supplement is entity-only; only inject when entities are in scope.
    if "entities" in kinds:
        hits.extend(semantic_entity_hits(store, semantic, query, eligibility=eligibility, seen=seen))

    prefer_rt = KIND_TO_RECORD_TYPE.get(prefer_kind) if prefer_kind else None
    return SearchResult(query=query, hits=rank_hits(hits, query, limit, prefer_rt))


def _search_entities(
    store: ReadableArtifactStore,
    query_lc: str,
    tokens: list[str],
    eligibility: EntityEligibility,
) -> list[SearchHit]:
    hits = []
    for rec in store.list_entities():
        if not eligibility.is_eligible(rec):
            continue
        if (score := score_entity(rec, query_lc, tokens)) > 0:
            hits.append(SearchHit(score=score, record_type="entity", record=rec))
    return hits


def _search_connections(store: ReadableArtifactStore, query_lc: str, tokens: list[str]) -> list[SearchHit]:
    return [
        SearchHit(score=s, record_type="connection", record=r)
        for r in store.list_connections()
        if (s := score_connection(r, query_lc, tokens)) > 0
    ]


def _search_diagrams(store: ReadableArtifactStore, query_lc: str, tokens: list[str]) -> list[SearchHit]:
    return [
        SearchHit(score=s, record_type="diagram", record=r)
        for r in store.list_diagrams()
        if (s := score_diagram(r, query_lc, tokens)) > 0
    ]


def _search_documents(store: ReadableArtifactStore, query_lc: str, tokens: list[str]) -> list[SearchHit]:
    return [
        SearchHit(score=s, record_type="document", record=r)
        for r in store.list_documents()
        if (s := score_document(r, query_lc, tokens)) > 0
    ]


def _search_scratchpad_notes(store: ReadableArtifactStore, query_lc: str, tokens: list[str]) -> list[SearchHit]:
    return [
        SearchHit(score=s, record_type="scratchpad-note", record=r)
        for r in store.list_scratchpad_notes()
        if (s := score_scratchpad_note(r, query_lc, tokens)) > 0
    ]


def _search_scratchpads(
    store: ReadableArtifactStore, query_lc: str, tokens: list[str]
) -> list[SearchHit]:
    hits = []
    for rec in store.list_scratchpads_indexed():
        if (score := score_scratchpad(rec, query_lc, tokens)) > 0:
            hits.append(SearchHit(score=score, record_type="scratchpad", record=rec))
    return hits
