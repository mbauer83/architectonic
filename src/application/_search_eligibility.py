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
from src.domain.ontology_representation.artifact_types import EntityRecord, SemanticSearchProvider
from src.domain.search_records import RECORD_TYPE_TO_KIND, SearchCandidate

#: Below this many entities the vector branch is not consulted at all. On a corpus this small a
#: retriever asked for its nearest neighbours returns its nearest neighbours whether or not any of
#: them is relevant, and fusion gives an only-vector candidate the same weight as an only-keyword
#: one — so the noise does not merely rank low, it ties the right answer.
SEMANTIC_MIN_CORPUS_SIZE = 50

#: How deep a list to ask the vector branch for, relative to the window. Deeper than the window
#: because fusion rewards a candidate two retrievers found, and a candidate cut off at the window's
#: edge cannot be one of them. The retriever ranks its whole corpus either way; only the slice costs.
_SEMANTIC_DEPTH_FACTOR = 5
_SEMANTIC_MIN_DEPTH = 50


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


def semantic_candidates(
    store: ReadableArtifactStore,
    semantic: SemanticSearchProvider | None,
    query: str,
    *,
    eligibility: EntityEligibility,
    kinds: frozenset[str],
    limit: int,
) -> dict[str, list[SearchCandidate]]:
    """The vector branch's ranked candidates, per record type, with this policy's exclusions applied.

    Filtered here rather than by the caller because visibility is settled once, in this module, for
    every branch. An ineligible candidate is dropped rather than replaced: under rank fusion a gap
    costs the candidates below it one rank, where the old bounded supplement had to refill because
    an ineligible leading candidate would otherwise have consumed its entire budget of one.

    Entities are the only kind this policy judges. A document or a diagram carries no type or domain
    to exclude, so what governs those is the caller's `kinds`.
    """
    if semantic is None or not isinstance(semantic, SemanticSearchProvider):
        return {}
    if len(store.entity_ids()) < SEMANTIC_MIN_CORPUS_SIZE:
        return {}

    wanted = {RECORD_TYPE_TO_KIND.get(rt, "") for rt in ("entity", "document", "diagram")} & kinds
    if not wanted:
        return {}
    if eligibility.effective_request_is_empty:
        wanted = wanted - {"entities"}

    depth = max(limit * _SEMANTIC_DEPTH_FACTOR, _SEMANTIC_MIN_DEPTH)
    per_type: dict[str, list[SearchCandidate]] = {}
    for candidate in semantic.ranked_candidates(query, limit=depth):
        if RECORD_TYPE_TO_KIND.get(candidate.record_type) not in wanted:
            continue
        if candidate.record_type == "entity" and not _eligible_entity(store, candidate, eligibility):
            continue
        per_type.setdefault(candidate.record_type, []).append(candidate)
    return per_type


def _eligible_entity(
    store: ReadableArtifactStore, candidate: SearchCandidate, eligibility: EntityEligibility
) -> bool:
    record = store.get_entity(candidate.artifact_id)
    return record is not None and eligibility.is_eligible(record)
