"""What may be attached to an intermediate that stands for a relationship.

Three rules about the ends of such a connection, kept together because they share the question "is
this endpoint an intermediate, and which one":

* **W127** — a multiplicity set on a junction connection-end. Junctions do not support them; this is
  the read-time complement to the write-time block in `artifact_write/connection.py::add_connection`,
  catching data that predates that guard or came through the edit path, which does not enforce it.
* **E128** — the legs of one intermediate do not agree on a relationship type.
* **E129** — the type it carries is not permitted between every participant it joins.

E128/E129 are the ontology's own words: `src/domain/relationships/relationship_mediation.py` reads
them off the composition rule that passes a relationship through the intermediate, so this module
decides nothing about which types those are. W127 remains a junction-class rule, because
multiplicities are a property of a connection end rather than of a derivation.
"""

from __future__ import annotations

from collections.abc import Callable

from src.application.mediated_relationships import leg_offences
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.application.verification.artifact_verifier_types import Issue, Severity, VerificationResult
from src.domain.modules.catalogs import ConnectionSemantics, OntologyCatalog
from src.domain.relationships.relationship_mediation import MixedLegTypes, PassThroughMediation


def is_junction(ontology_catalog: OntologyCatalog, entity_type: str | None) -> bool:
    """Whether *entity_type* is a junction, as the ontology classifies it.

    One place asks this question, so no rule here carries a list of junction type names: an ontology
    that declares a third junction flavour gets it from the class, not from an edit to this module.
    """
    return entity_type is not None and entity_type in ontology_catalog.entity_types_with_class("junction")


def check_junction_multiplicity(
    ontology_catalog: OntologyCatalog,
    *,
    entity_id: str,
    entity_type: str,
    multiplicity: str,
    label: str,
    result: VerificationResult,
    loc: str,
) -> None:
    if not multiplicity or not is_junction(ontology_catalog, entity_type):
        return
    result.issues.append(
        Issue(
            Severity.WARNING,
            "W127",
            f"{label.capitalize()} multiplicity '{multiplicity}' is set on a junction connection-end "
            f"('{entity_id}' is a junction); junctions do not support multiplicities.",
            loc,
        )
    )


def check_mediated_leg(
    connections_catalog: ConnectionSemantics,
    registry: ArtifactRegistry,
    entity_type_of: Callable[[str], str | None],
    mediation: PassThroughMediation,
    *,
    intermediate_id: str,
    intermediate_type: str,
    near_id: str,
    conn_type: str,
    intermediate_is_target: bool,
    result: VerificationResult,
    loc: str,
) -> None:
    """Report the rule's verdict on one leg: E128 for mixed types, E129 for an inadmissible join."""
    for offence in leg_offences(
        registry,
        connections_catalog,
        mediation,
        entity_type_of,
        intermediate_id=intermediate_id,
        intermediate_type=intermediate_type,
        near_id=near_id,
        conn_type=conn_type,
        intermediate_is_target=intermediate_is_target,
    ):
        code = "E128" if isinstance(offence, MixedLegTypes) else "E129"
        result.issues.append(Issue(Severity.ERROR, code, offence.message(), loc))
