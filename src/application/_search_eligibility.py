"""Entity search-eligibility policy shared by every search branch.

Search visibility is an application policy: an entity this policy excludes must never surface through
any search branch — full-text, scored fallback, or semantic supplement — while raw id/list access
stays unfiltered.

**One decider, and that is the whole point.** Visibility used to be settled twice on two different
keys: the use case excluded entity *types* named by the module catalogue, and the REST layer then
dropped any record carrying a `host_diagram_id`, whatever its type. Those sets differ — several
diagram families declare no diagram-only types at all — so records invisible to the first key were
ranked, given slots in the window, and removed by the second. A search asked for twenty rows returned
sixteen, and the four it lost were the highest-scoring entity hits it had.

The two exclusions it carries are deliberately separate fields rather than one merged set, because
they answer different questions and are supplied by different callers: `excluded_entity_types` is a
*type* judgement (system-managed internal types, and whatever a caller adds), while diagram ownership
is a *record* judgement that no type name can express — the container key is shared across diagram
families, so naming it would hide one family's nodes by hiding all of them.

The predicate is stated here once and rendered twice: in Python, by `is_eligible`; and in SQL, by the
store, which is handed these sets as data and builds its own `WHERE` from them. The store renders it
because the filter has to run *inside* the per-kind `ORDER BY … LIMIT` — a candidate window spent on
rows the reader will never see is the same defect one layer earlier — and because an application
policy that emitted SQL would be reaching into infrastructure to say it.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.application.ports import ReadableArtifactStore
from src.domain.ontology_representation.artifact_types import EntityRecord, SearchHit, SemanticSearchProvider

SEMANTIC_MIN_CORPUS_SIZE = 50
SEMANTIC_RESULT_BOUND = 1
SEMANTIC_SCORE_THRESHOLD = 0.75
_SEMANTIC_SCORE_WEIGHT = 3.0


@dataclass(frozen=True)
class EntityEligibility:
    """One effective predicate: visible AND not diagram-owned-and-unlisted AND type AND domain."""

    excluded_entity_types: frozenset[str]
    entity_types: frozenset[str]
    domains: frozenset[str]
    #: Diagram-owned entity types a caller has declared searchable, or ``None`` when this caller
    #: is not applying the policy at all.
    #:
    #: Absent and empty are different facts, and conflating them is a wrong answer either way.
    #: ``None`` means *no ownership filtering* — what a direct index query or an internal lookup
    #: wants, and what every caller predating this policy got. An empty set means *the policy is
    #: applied and nothing opts in*, which is what a search surface wants when no module has
    #: declared a diagram-owned type searchable. A record with no ``host_diagram_id`` is a model
    #: entity and passes either way.
    #:
    #: The vocabulary is injected rather than known: which types opt in is a *module* judgement, and
    #: this policy has no business naming one.
    visible_diagram_entity_types: frozenset[str] | None = None

    @staticmethod
    def build(
        excluded_entity_types: frozenset[str],
        entity_types: list[str] | None,
        domains: list[str] | None,
        visible_diagram_entity_types: frozenset[str] | None = None,
    ) -> "EntityEligibility":
        return EntityEligibility(
            excluded_entity_types=excluded_entity_types,
            entity_types=frozenset(entity_types or ()),
            domains=frozenset(domains or ()),
            visible_diagram_entity_types=visible_diagram_entity_types,
        )

    @property
    def effective_request_is_empty(self) -> bool:
        """True when an explicit entity-type filter is fully consumed by the exclusion set."""
        return bool(self.entity_types) and self.entity_types <= self.excluded_entity_types

    def is_eligible(self, record: EntityRecord) -> bool:
        """The whole predicate, over the record — not over a pair of its fields.

        It takes the record because diagram ownership is not derivable from a type name: the
        container key is shared across diagram families, so a type-keyed rule hides all of them or
        none. Every call site already holds the record.
        """
        return self.admits_type_and_domain(record.artifact_type, record.domain) and self.admits_ownership(
            record.artifact_type, record.host_diagram_id
        )

    def admits_type_and_domain(self, artifact_type: str, domain: str) -> bool:
        return (
            artifact_type not in self.excluded_entity_types
            and (not self.entity_types or artifact_type in self.entity_types)
            and (not self.domains or domain in self.domains)
        )

    def admits_ownership(self, artifact_type: str, host_diagram_id: str | None) -> bool:
        """Whether a record is searchable given what owns it. A model entity always is."""
        if self.visible_diagram_entity_types is None:
            return True
        return not host_diagram_id or artifact_type in self.visible_diagram_entity_types


def semantic_entity_hits(
    store: ReadableArtifactStore,
    semantic: SemanticSearchProvider | None,
    query: str,
    *,
    eligibility: EntityEligibility,
    seen: set[tuple[str, str]],
) -> list[SearchHit]:
    """Entity hits from the semantic provider, refilled past ineligible candidates.

    Preserves provider ranking and the configured result bound: leading candidates that
    are hidden, of a non-matching type, in a non-matching domain, or already seen do not
    consume the budget — the request deepens until eligible hits fill the bound or the
    provider is exhausted.
    """
    if semantic is None or not isinstance(semantic, SemanticSearchProvider):
        return []
    if eligibility.effective_request_is_empty:
        return []
    if len(store.entity_ids()) < SEMANTIC_MIN_CORPUS_SIZE:
        return []
    hits: list[SearchHit] = []
    scanned = 0
    k = SEMANTIC_RESULT_BOUND + len(seen)
    while True:
        candidates = semantic.top_k(query, k=k, threshold=SEMANTIC_SCORE_THRESHOLD)
        for sem_score, artifact_id in candidates[scanned:]:
            key = ("entity", artifact_id)
            if key in seen:
                continue
            record = store.get_entity(artifact_id)
            if record is None or not eligibility.is_eligible(record):
                continue
            seen.add(key)
            hits.append(SearchHit(score=sem_score * _SEMANTIC_SCORE_WEIGHT, record_type="entity", record=record))
            if len(hits) >= SEMANTIC_RESULT_BOUND:
                return hits
        if len(candidates) < k:
            return hits
        scanned = len(candidates)
        k *= 2
