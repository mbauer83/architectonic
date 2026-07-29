"""Resolve a persisted diagram's accepted witness paths into renderable connection
records: reconstructs each accepted path fresh via ``derive_relationship_for_path`` (the
only function rendering ever consumes for a derived connection — the same reconstruction
``path_staleness.py`` uses for staleness classification) and synthesizes a renderer-only
``ConnectionRecord`` per successful outcome. A broken or no-longer-derives path never
silently redraws or drops — it is a staleness finding, not a rendering fallback, so it is
simply omitted here and left to ``classify_accepted_path_staleness`` to surface."""

from __future__ import annotations

from pathlib import Path

from src.domain.modules.module_catalog import ModuleCatalog
from src.domain.ontology_representation.artifact_types import ConnectionRecord
from src.domain.relationships.relationship_path_reconstruction import (
    DerivedPathRelationship,
    RelationshipPathReadAccess,
    derive_relationship_for_path,
)
from src.domain.viewpoints.view_derivations import DerivationSelection


def _synthetic_record(path_key: str, outcome: DerivedPathRelationship) -> ConnectionRecord:
    return ConnectionRecord(
        artifact_id=f"derived::{outcome.connection_type}::{path_key}",
        source=outcome.source_id,
        target=outcome.target_id,
        conn_type=outcome.connection_type,
        version="",
        status="",
        path=Path(),
        extra={"certainty": outcome.certainty},
        content_text="",
    )


def resolve_accepted_derived_connections(
    selection: DerivationSelection | None,
    *,
    read_access: RelationshipPathReadAccess,
    catalog: ModuleCatalog,
) -> list[ConnectionRecord]:
    if selection is None or not selection.included_paths:
        return []
    records: list[ConnectionRecord] = []
    for path_key in selection.included_paths:
        outcome = derive_relationship_for_path(path_key, read_access=read_access, registries=catalog)
        if isinstance(outcome, DerivedPathRelationship):
            records.append(_synthetic_record(path_key, outcome))
    return records
