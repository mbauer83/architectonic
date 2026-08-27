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


def placed_connection_triples(
    fm: dict, registry: ArtifactRegistry
) -> tuple[tuple[str, str, str], ...]:
    """Each recorded connection as `(connection_type, source_alias, target_alias)`.

    The aliases are what a PUML body names its endpoints by, so this is the form anything comparing a
    recorded connection against a drawn one needs — which is how the legend decides whether a
    relationship is drawn as a line or as containment.

    Assembled here, beside `resolve_placed_connections`, because both answer "what does this diagram
    record" and the alias is the endpoint entity's own `display_alias`. A caller pairing the two by
    hand would be a second reading of that correspondence.
    """
    triples: list[tuple[str, str, str]] = []
    for connection in resolve_placed_connections(fm, registry):
        source = registry.get_entity(connection.source)
        target = registry.get_entity(connection.target)
        source_alias = getattr(source, "display_alias", "") or ""
        target_alias = getattr(target, "display_alias", "") or ""
        if source_alias and target_alias:
            triples.append((connection.conn_type, source_alias, target_alias))
    return tuple(triples)
