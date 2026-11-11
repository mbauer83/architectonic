"""The write-time refusal for a second whole claiming a part — the rule the verifier reports as E340.

Its own file for the reason `mediated_leg_guard` is: one concern, one entry point. The rule names no
relation. Whether a connection type permits only one source per target is declared on the type
(`exclusive_target`) and read through `claims_its_target_exclusively`, the same question E340 asks,
so the refusal and the diagnosis cannot drift apart.

E340 is repository-level because each whole declares the part in its own `.outgoing.md`, and neither
file is wrong on its own. The write knows both: the connection it is adding and the graph it adds to.
"""

from __future__ import annotations

from src.application.runtime_catalogs import RuntimeCatalogs
from src.application.verification.artifact_verifier import ArtifactRegistry
from src.domain.artifact_id import stable_id


def refuse_second_whole(
    registry: ArtifactRegistry,
    catalogs: RuntimeCatalogs,
    connection_type: str,
    source_entity: str,
    target_entity: str,
) -> None:
    """Refuse a connection whose type permits one source per target when another source holds it."""
    if not catalogs.connections.claims_its_target_exclusively(connection_type):
        return
    claimants = sorted({
        record.source
        for record in registry.find_connections_for(target_entity, direction="inbound", conn_type=connection_type)
        if stable_id(record.source) != stable_id(source_entity)
    })
    if claimants:
        raise ValueError(
            f"'{target_entity}' is already claimed through {connection_type} by {', '.join(claimants)}, "
            f"and {connection_type} permits one source per target (E340). Use a relation that lets a "
            f"part be shared, or remove the existing claim first."
        )
