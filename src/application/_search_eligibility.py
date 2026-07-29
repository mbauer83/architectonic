"""Entity search-eligibility policy shared by every search branch.

Search visibility is an application policy: entity types excluded here (system-managed
internal types such as global-artifact-reference proxies) must never surface through
any search branch — full-text, scored fallback, or semantic supplement — while raw
id/list access stays unfiltered.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.application.ports import ReadableArtifactStore
from src.domain.ontology_representation.artifact_types import SearchHit, SemanticSearchProvider

SEMANTIC_MIN_CORPUS_SIZE = 50
SEMANTIC_RESULT_BOUND = 1
SEMANTIC_SCORE_THRESHOLD = 0.75
_SEMANTIC_SCORE_WEIGHT = 3.0


@dataclass(frozen=True)
class EntityEligibility:
    """One effective predicate: visible AND matches entity type AND matches domain."""

    excluded_entity_types: frozenset[str]
    entity_types: frozenset[str]
    domains: frozenset[str]

    @staticmethod
    def build(
        excluded_entity_types: frozenset[str],
        entity_types: list[str] | None,
        domains: list[str] | None,
    ) -> "EntityEligibility":
        return EntityEligibility(
            excluded_entity_types=excluded_entity_types,
            entity_types=frozenset(entity_types or ()),
            domains=frozenset(domains or ()),
        )

    @property
    def effective_request_is_empty(self) -> bool:
        """True when an explicit entity-type filter is fully consumed by the exclusion set."""
        return bool(self.entity_types) and self.entity_types <= self.excluded_entity_types

    def is_eligible(self, artifact_type: str, domain: str) -> bool:
        return (
            artifact_type not in self.excluded_entity_types
            and (not self.entity_types or artifact_type in self.entity_types)
            and (not self.domains or domain in self.domains)
        )


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
            if record is None or not eligibility.is_eligible(record.artifact_type, record.domain):
                continue
            seen.add(key)
            hits.append(SearchHit(score=sem_score * _SEMANTIC_SCORE_WEIGHT, record_type="entity", record=record))
            if len(hits) >= SEMANTIC_RESULT_BOUND:
                return hits
        if len(candidates) < k:
            return hits
        scanned = len(candidates)
        k *= 2
