"""Resolves a diagram/matrix's placed-occurrence frontmatter (``entity-ids-used``/
``connection-ids-used``) to records — shared by the WU-E16 verifier rule and the WU-E5a GUI
projection lookup, both of which assemble the same placed-occurrence set before handing it
to ``project_artifact_local``.
"""

from __future__ import annotations

from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord


def resolve_placed_entities(fm: dict, registry: ArtifactRegistry) -> tuple[EntityRecord, ...]:
    """Resolve ``entity-ids-used`` frontmatter to their ``EntityRecord``s.

    Unresolvable ids are skipped here — the diagram-references verifier rule already
    reports the "unknown entity" error for those; callers of this helper only judge
    resolvable placements.
    """
    raw = fm.get("entity-ids-used")
    if not isinstance(raw, list):
        return ()
    return tuple(entity for eid in raw if (entity := registry.get_entity(str(eid))) is not None)


def resolve_placed_connections(fm: dict, registry: ArtifactRegistry) -> tuple[ConnectionRecord, ...]:
    """Resolve ``connection-ids-used`` frontmatter to their ``ConnectionRecord``s.

    Unresolvable connections/endpoints are skipped here, for the same reason as
    ``resolve_placed_entities`` — callers only judge resolvable placements.
    """
    raw = fm.get("connection-ids-used")
    if not isinstance(raw, list):
        return ()
    resolved: list[ConnectionRecord] = []
    for cid in raw:
        connection = registry.get_connection(str(cid))
        if connection is None:
            continue
        if registry.get_entity(connection.source) is not None and registry.get_entity(connection.target) is not None:
            resolved.append(connection)
    return tuple(resolved)
