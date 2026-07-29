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
    """Keep relevance order within model entities, diagram-owned entities, and other records."""
    return sorted(
        hits,
        key=lambda hit: (
            0 if hit.record_type == "entity" and getattr(hit.record, "host_diagram_id", None) is None
            else 1 if hit.record_type == "entity"
            else 2
        ),
    )
