"""The write-time refusal for a leg an intermediate may not carry.

Its own file because it is one concern with one entry point, and because the rule it enforces is
shared: `src/application/mediated_relationships.py` asks the graph, and
`src/domain/relationships/relationship_mediation.py` holds the rule the ontology declares. What the
verifier reports as E128/E129 is refused here before it reaches a file.
"""

from __future__ import annotations

from src.application.mediated_relationships import declared_mediations, leg_offences, mediation_for_type
from src.application.runtime_catalogs import RuntimeCatalogs
from src.application.verification.artifact_verifier import ArtifactRegistry

from .entity_frontmatter import entity_artifact_type


def refuse_inadmissible_leg(
    registry: ArtifactRegistry,
    catalogs: RuntimeCatalogs,
    connection_type: str,
    source_entity: str,
    target_entity: str,
) -> None:
    """Refuse a leg an intermediate may not carry — the rule the verifier reports as E128/E129.

    This used to read the junction's own `.outgoing.md` and refuse a second relationship type found
    *there*, which missed both halves of the rule: a mismatched leg declared in a participant's own
    file was invisible to it (its docstring said so), and whether the type is admissible between the
    participants was not asked at all. Both questions now go to one place, so a write refusal and a
    verifier diagnosis cannot drift apart.
    """
    mediations = declared_mediations(catalogs.module_catalog)
    for intermediate_id, near_id, intermediate_is_target in (
        (target_entity, source_entity, True),
        (source_entity, target_entity, False),
    ):
        intermediate_type = entity_artifact_type(registry, intermediate_id)
        mediation = mediation_for_type(intermediate_type, catalogs.module_catalog, mediations)
        if mediation is None or intermediate_type is None:
            continue
        offences = leg_offences(
            registry,
            catalogs.connections,
            mediation,
            lambda entity_id: entity_artifact_type(registry, entity_id),
            intermediate_id=intermediate_id,
            intermediate_type=intermediate_type,
            near_id=near_id,
            conn_type=connection_type,
            intermediate_is_target=intermediate_is_target,
        )
        if offences:
            raise ValueError(offences[0].message())
