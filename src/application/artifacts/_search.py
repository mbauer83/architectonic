"""Standalone search functions for ArtifactRepository."""

from __future__ import annotations

from typing import cast

from src.application._search_eligibility import EntityEligibility, semantic_entity_hits
from src.application.artifacts.scoring import (
    score_connection,
    score_diagram,
    score_document,
    score_entity,
    score_scratchpad_note,
    tokenize,
)
from src.application.ports import ReadableArtifactStore
from src.domain.ontology_representation.artifact_types import (
    ALL_SEARCHABLE_KINDS,
    KIND_TO_RECORD_TYPE,
    RECORD_TYPE_TO_KIND,
    SUBORDINATE_RECORD_TYPES,
    ConnectionRecord,
    DiagramRecord,
    DocumentRecord,
    EntityRecord,
    RecordType,
    ScratchpadNoteRecord,
    SearchableKind,
    SearchHit,
    SearchResult,
    SemanticSearchProvider,
)

# The vocabulary itself lives beside `SearchHit` in the domain, where the record types are declared;
# these names stay importable from here because every caller already reaches for them here.
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
    include_scratchpad_notes: bool = True,
    prefer_record_type: RecordType | None = None,
    strict_record_type: bool = False,
    excluded_entity_types: frozenset[str] = frozenset(),
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
    eligibility = EntityEligibility.build(excluded_entity_types, entity_types, domains)
    if eligibility.effective_request_is_empty:
        kinds = kinds - {"entities"}

    # Per-kind FTS: each kind gets its own slot budget to prevent starvation.
    per_kind_limit = max(limit * 2, 10)
    fts_hits = store.search_fts(
        query,
        limit=per_kind_limit,
        kinds=frozenset(kinds),
        excluded_entity_types=excluded_entity_types,
    )

    seen: set[tuple[str, str]] = set()
    hits: list[SearchHit] = []
    fts_kinds_with_hits: set[str] = set()

    for artifact_id, record_type, score in fts_hits:
        artifact: (
            EntityRecord | ConnectionRecord | DiagramRecord | DocumentRecord | ScratchpadNoteRecord | None
        )
        match record_type:
            case "entity":
                artifact = store.get_entity(artifact_id)
                if artifact is None or not eligibility.is_eligible(artifact.artifact_type, artifact.domain):
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
    return SearchResult(query=query, hits=_rank_balanced(hits, limit, prefer_rt))


def _rank_balanced(hits: list[SearchHit], limit: int, prefer_rt: str | None) -> list[SearchHit]:
    """Select up to ``limit`` hits with fair representation across record kinds.

    Per-table FTS (bm25) and the token-match supplement produce scores on incomparable
    scales, so a single global sort lets a high-volume kind (entities) crowd minority
    kinds (diagrams, documents) out of the result window entirely. Instead, rank within
    each kind by its own score, then round-robin across kinds — ordering the kinds by
    their strongest hit (``prefer_rt`` first) — so every matching kind stays visible.

    ``SUBORDINATE_RECORD_TYPES`` do not take part in the round-robin at all: they fill whatever
    slots are left once every other kind has had its turn. A scratchpad note is a half-formed
    thought and an entity is a commitment, and "never outranks model content, documents or
    diagrams" was the condition notes were allowed into the index under — a round-robin honours it
    only against the *first* hit of each other kind, and would still put a note above the second
    entity. A preference cannot lift them either.

    It is enforced here rather than by weights because the two scales cannot be compared: bm25 and
    the token-match supplement say nothing about each other, so only the draw order can promise it.
    The cost is real and accepted — a query whose window is filled by model content will not show a
    note even if the note matched it exactly.
    """
    by_kind: dict[str, list[SearchHit]] = {}
    for h in hits:
        by_kind.setdefault(h.record_type, []).append(h)
    for group in by_kind.values():
        group.sort(key=lambda h: h.score, reverse=True)
    order = sorted(by_kind, key=lambda rt: by_kind[rt][0].score, reverse=True)
    if prefer_rt in by_kind and prefer_rt not in SUBORDINATE_RECORD_TYPES:
        order = [prefer_rt, *(rt for rt in order if rt != prefer_rt)]
    ranked: list[SearchHit] = []
    rank = 0
    while len(ranked) < limit:
        drawn = [
            by_kind[rt][rank]
            for rt in order
            if rt not in SUBORDINATE_RECORD_TYPES and rank < len(by_kind[rt])
        ]
        if not drawn:
            break
        ranked.extend(drawn)
        rank += 1
    subordinate = sorted(
        (h for rt in order if rt in SUBORDINATE_RECORD_TYPES for h in by_kind[rt]),
        key=lambda h: h.score,
        reverse=True,
    )
    return (ranked + subordinate)[:limit] if len(ranked) < limit else ranked[:limit]


def _search_entities(
    store: ReadableArtifactStore,
    query_lc: str,
    tokens: list[str],
    eligibility: EntityEligibility,
) -> list[SearchHit]:
    hits = []
    for rec in store.list_entities():
        if not eligibility.is_eligible(rec.artifact_type, rec.domain):
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
