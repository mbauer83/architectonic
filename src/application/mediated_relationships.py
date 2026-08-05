"""The graph side of pass-through mediation: what an intermediate's legs are, and what is wrong.

The rule itself is pure (`src/domain/relationships/relationship_mediation.py`). What it cannot do is
find the legs: they live in as many files as the intermediate has participants — each participant's
own outgoing file declares its leg *into* the intermediate, and the intermediate's file declares the
legs *out* of it — so only the graph can answer. That is what this module adds, once, for the two
enforcers: the verifier reports the offences as E128/E129, and the write path refuses them.
"""

from __future__ import annotations

from collections.abc import Callable

from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.domain.modules.catalogs import ConnectionSemantics
from src.domain.modules.module_catalog import ModuleCatalog
from src.domain.modules.module_types import EntityTypeName
from src.domain.relationships.relationship_mediation import (
    MediationOffence,
    PassThroughMediation,
    legs_from_records,
    mediation_governing,
    mediation_offences,
    pass_through_mediations,
)


def declared_mediations(catalog: ModuleCatalog) -> tuple[PassThroughMediation, ...]:
    """Every pass-through mediation the loaded ontologies declare."""
    return pass_through_mediations(
        rule for module in catalog.all_ontologies().values() for rule in module.derivation_rules
    )


def mediation_for_type(
    entity_type: str | None,
    catalog: ModuleCatalog,
    mediations: tuple[PassThroughMediation, ...],
) -> PassThroughMediation | None:
    """The mediation governing *entity_type*, by the classes the ontology gives that type."""
    type_infos = catalog.all_entity_types()

    def classes_of(name: str) -> frozenset[str]:
        info = type_infos.get(EntityTypeName(name))
        return frozenset(info.classes) if info is not None else frozenset()

    return mediation_governing(entity_type, classes_of, mediations)


def leg_offences(
    registry: ArtifactRegistry,
    connections: ConnectionSemantics,
    mediation: PassThroughMediation,
    type_of: Callable[[str], str | None],
    *,
    intermediate_id: str,
    intermediate_type: str,
    near_id: str,
    conn_type: str,
    intermediate_is_target: bool,
) -> tuple[MediationOffence, ...]:
    """Judge one leg of *intermediate_id* against every other leg the graph holds for it."""
    return mediation_offences(
        mediation,
        intermediate_id=intermediate_id,
        intermediate_type=intermediate_type,
        carried=conn_type,
        near_id=near_id,
        near_is_upstream=intermediate_is_target,
        legs=legs_from_records(
            inbound=registry.find_connections_for(intermediate_id, direction="inbound"),
            outbound=registry.find_connections_for(intermediate_id, direction="outbound"),
        ),
        type_of=type_of,
        permitted_types=lambda source, target: frozenset(connections.permissible_connection_types(source, target)),
    )
