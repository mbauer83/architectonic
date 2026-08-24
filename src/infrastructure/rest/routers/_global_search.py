"""Global-search visibility and stable record-kind ordering."""

from collections.abc import Sequence

from src.application.runtime_catalogs import RuntimeCatalogs
from src.domain.ontology_representation.artifact_types import SearchHit


def hidden_diagram_entity_types(catalogs: RuntimeCatalogs) -> frozenset[str]:
    declared = catalogs.module_catalog.all_diagram_entity_types()
    visible = catalogs.module_catalog.diagram_entity_types_in_global_search()
    return frozenset(str(entity_type) for entity_type in declared - visible)


def filter_global_hits(
    hits: Sequence[SearchHit], catalogs: RuntimeCatalogs
) -> list[SearchHit]:
    """Hide diagram-owned entities unless their type explicitly opts in."""
    visible_types = {
        str(entity_type)
        for entity_type in catalogs.module_catalog.diagram_entity_types_in_global_search()
    }
    return [
        hit
        for hit in hits
        if hit.record_type != "entity"
        or getattr(hit.record, "host_diagram_id", None) is None
        or str(getattr(hit.record, "artifact_type", "")) in visible_types
    ]


def prioritize_global_hits(hits: Sequence[SearchHit]) -> list[SearchHit]:
    """Demote diagram-owned entities, and leave every other kind in the order it arrived.

    The concern this expresses is about *entities*: a diagram-local node is a drawing detail and a
    model entity is a commitment, so the two should not interleave. That is the whole of it.

    It used to put every non-entity record in a third bucket behind both — so a diagram or a document
    ranked after *every* entity hit, however it scored. With a window of twenty and forty entity hits,
    a diagram could not appear at all: searching a diagram's exact title returned forty entities and
    none of it, though the index ranked that diagram top of its kind. A document scoring 9.0 came back
    below an entity scoring 7.0, and the test asserted it.

    Worse, it silently undid `_rank_balanced`, which exists to guarantee exactly this: the search use
    case ranks within each kind and round-robins across them *because* bm25 and the token-match
    supplement are incomparable scales. Re-sorting the result here overrode that with a hard
    precedence — two deciders, and the second one won without knowing what the first had promised.

    So a stable sort on one key: diagram-owned entities last, everyone else untouched. `_rank_balanced`
    has already put scratchpad notes behind the other kinds, and leaving non-entity records alone
    preserves that too.
    """
    return sorted(
        hits,
        key=lambda hit: (
            1 if hit.record_type == "entity" and getattr(hit.record, "host_diagram_id", None) is not None
            else 0
        ),
    )
