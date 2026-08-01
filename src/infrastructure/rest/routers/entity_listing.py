"""Selecting and shaping the entity population a browse list shows.

One place decides *which* entities are browsable, because two answers would drift: the
group sidebar's member counts and the list a user sees after clicking that group are the same
population by construction, not by coincidence.
"""

from __future__ import annotations

from functools import lru_cache as _lru_cache
from typing import Any

from src.application.artifact_query import ArtifactRepository
from src.application.entity_type_predicates import is_assurance_entity_type, is_internal_entity_type
from src.application.record_sorting import sort_entity_records
from src.domain.ontology_representation.artifact_types import EntityRecord
from src.infrastructure.rest.routers import state as s


@_lru_cache(maxsize=1)
def _catalogs():
    from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry  # noqa: PLC0415

    return build_runtime_catalogs(get_module_registry())


def browsable_entities(records: list[EntityRecord], *, scope: str | None = None) -> list[EntityRecord]:
    """The model-entity catalog: what browsing entities means.

    Excluded, and why: diagram-owned entities (swimlanes, lifelines, actions, …) live inside a
    diagram's frontmatter — indexed so they are queryable in-diagram, but they have no file of
    their own and are not standalone model entities. Internal types (global artifact
    references) are plumbing the promotion machinery creates. Assurance types belong to the
    assurance product area, which browses them through its own surface.

    ``scope`` narrows by repository tier: ``"global"`` to the enterprise repository,
    ``"engagement"`` to the local one, anything else (including None) spans both.
    """
    catalogs = _catalogs()
    return [
        record for record in records
        if record.host_diagram_id is None
        and not is_internal_entity_type(record.artifact_type, catalogs.ontology)
        and not is_assurance_entity_type(record.artifact_type, catalogs.module_catalog)
        and _matches_tier(record, scope)
    ]


def _matches_tier(record: EntityRecord, scope: str | None) -> bool:
    if scope == "global":
        return s.is_global(record.path)
    if scope == "engagement":
        return not s.is_global(record.path)
    return True


def engagement_model_catalog(records: list[EntityRecord]) -> list[EntityRecord]:
    """The engagement-side model-entity catalog — the exact population
    `/api/entities?scope=engagement` lists, shared with `/api/groups`'s member counts so a
    sidebar badge can never disagree with what opening that group shows."""
    return browsable_entities(records, scope="engagement")


def select_entity_population(
    repo: ArtifactRepository,
    *,
    domain: str | None,
    artifact_type: str | None,
    status: str | None,
    group: str | None,
    scope: str | None,
    allowed_types: frozenset[str] | None,
    sort: str | None,
    order: str,
) -> list[EntityRecord]:
    """The filtered, ordered population a list request describes — before any page slice.

    Ordering last and paging afterwards is what makes a sorted column mean "the newest in the
    repository" rather than "the newest on this page".
    """
    records = browsable_entities(
        repo.list_entities(domain=domain, artifact_type=artifact_type, status=status, group=group),
        scope=scope,
    )
    if allowed_types is not None:
        records = [record for record in records if record.artifact_type in allowed_types]
    return sort_entity_records(records, sort, order)


def build_entity_list_rows(entities: list[EntityRecord], repo: ArtifactRepository) -> list[dict[str, Any]]:
    counts = s.build_conn_counts_for_entities(repo, [e.artifact_id for e in entities])
    return [s.entity_to_summary(e, counts) for e in entities]
