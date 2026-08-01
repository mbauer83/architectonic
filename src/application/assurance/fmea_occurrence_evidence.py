"""What the model already knows about an element, offered when occurrence is asked for.

Occurrence is asserted-only, and that is not a gap to be closed later: complexity correlates weakly
with defect density, churn measures recent change, coverage measures testing, and none of them is a
failure rate. A number derived from any of them would carry the appearance of derivation and none of
the substance, and because the priority band is occurrence-sensitive, it would move real decisions.

So what the integration contributes here is **the evidence, not the value**. When someone is asked
for an occurrence, the rationale field opens already citing what the model holds about the bound
element, each item naming real identifiers rather than recollection. The person still decides. They
simply do not retype what the model already knows, and what they write can be checked afterwards.

Vulnerability findings appear only where the failure mode's concern class is `security` **and** an
SBOM is anchored to the element. For a safety or operational failure mode they say nothing, and a
surface that led with them would mis-frame the method. Every surface works fully without any SBOM.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from src.domain.artifact_id import canonical_entity_key
from src.domain.assurance.fmea_structural_signals import (
    TypedEdge,
    common_cause_exposure,
    reliance_on,
    sole_providers,
)

SECURITY_CONCERN = "security"
ACCESS_CONNECTION_TYPE = "archimate-access"
CLASSIFIED_TYPES = frozenset({"data-object", "business-object"})
SENSITIVITY_ATTRIBUTE = "Sensitivity"


@dataclass(frozen=True)
class CitedFact:
    """One thing the model knows, in a form a rationale can quote."""

    kind: str
    text: str
    witness: tuple[str, ...] = ()


@dataclass(frozen=True)
class OccurrenceEvidence:
    """Everything offered to whoever is about to assert an occurrence.

    Carries no value and no suggested value — by construction, not by convention. The rendering
    surface has nothing to pre-fill the field with even if it tried.
    """

    facts: tuple[CitedFact, ...]

    @property
    def basis(self) -> tuple[str, ...]:
        """The citations, in a stable order, for the occurrence basis digest.

        A judgement retires when what it cited changes, so this is exactly the set of things whose
        movement should retire it.
        """
        return tuple(sorted(f"{fact.kind}:{fact.text}" for fact in self.facts))

    def rationale_draft(self) -> str:
        """The pre-populated rationale text: cited facts, one per line, and nothing else."""
        return "\n".join(f"- {fact.text}" for fact in self.facts)


def _structural_facts(element_id: str, edges: Sequence[TypedEdge]) -> list[CitedFact]:
    facts: list[CitedFact] = []
    reliance = reliance_on(element_id, edges)
    if reliance is None:
        # Absence, stated. A count of zero here would read as "nothing depends on this", when what
        # is true is that nothing about its neighbourhood has been modelled.
        facts.append(CitedFact(
            kind="structure",
            text=f"{element_id} has no modelled relationships, so nothing structural is known about it",
        ))
        return facts
    qualifier = " (computed over a thinly modelled neighbourhood)" if reliance.provisional else ""
    facts.append(CitedFact(
        kind="dependents",
        text=(
            f"{reliance.dependent_count} typed dependent(s) rely on {element_id}"
            f", weighted {reliance.weight}{qualifier}"
        ),
        witness=reliance.witness,
    ))
    if element_id in sole_providers(edges):
        dependents = sole_providers(edges)[element_id]
        facts.append(CitedFact(
            kind="sole-provider",
            text=(
                f"{element_id} is the only provider for {len(dependents)} dependent(s): "
                f"{', '.join(dependents)}"
            ),
            witness=reliance.witness,
        ))
    return facts


def _common_cause_facts(element_id: str, edges: Sequence[TypedEdge]) -> list[CitedFact]:
    from src.domain.assurance.fmea_structural_signals import interchangeable_pairs

    involving = [pair for pair in interchangeable_pairs(edges) if element_id in pair]
    return [
        CitedFact(
            kind="common-cause",
            text=(
                f"{shared.left_id} and {shared.right_id} stand in for each other but both rely on "
                f"{shared.shared_ancestor_id}"
            ),
            witness=shared.left_witness + shared.right_witness,
        )
        for shared in common_cause_exposure(involving, edges)
    ]


def _sensitivity_facts(
    element_id: str,
    connections: Sequence[Mapping[str, object]],
    entities: Mapping[str, Mapping[str, object]],
) -> list[CitedFact]:
    """The classification of the data this element touches, read through the graph.

    The component declares nothing: classification lives on the data, where it belongs, and the
    `archimate-access` edges name which data. This is why no second classification attribute was
    introduced for components.
    """
    facts: list[CitedFact] = []
    for connection in connections:
        if str(connection.get("connection_type", "")) != ACCESS_CONNECTION_TYPE:
            continue
        if canonical_entity_key(str(connection.get("source", ""))) != canonical_entity_key(element_id):
            continue
        target_id = str(connection.get("target", ""))
        target = entities.get(target_id)
        if target is None or str(target.get("artifact_type", "")) not in CLASSIFIED_TYPES:
            continue
        classification = str(target.get(SENSITIVITY_ATTRIBUTE) or "").strip()
        if classification:
            facts.append(CitedFact(
                kind="data-sensitivity",
                text=f"{element_id} accesses {target_id}, classified {classification}",
                witness=(f"{element_id} --{ACCESS_CONNECTION_TYPE}--> {target_id}",),
            ))
    return facts


@dataclass(frozen=True)
class ElementSecurityBasis:
    """What the signal snapshots know about one element, for a security-concern rationale.

    Separate from the architecture graph because it comes from a different store on a different
    refresh cycle, and because that is exactly the point: a judgement citing a snapshot retires
    when the snapshot moves, while a safety judgement about the same element does not.
    """

    vulnerability_ids: tuple[str, ...] = ()
    snapshot_id: str | None = None


def occurrence_evidence(
    element_id: str,
    *,
    concern_class: str,
    edges: Sequence[TypedEdge],
    connections: Sequence[Mapping[str, object]] = (),
    entities: Mapping[str, Mapping[str, object]] | None = None,
    vulnerability_ids: Sequence[str] = (),
    sbom_anchored: bool = False,
    security_basis_snapshot_id: str | None = None,
) -> OccurrenceEvidence:
    """Assemble what the model knows, for a rationale someone is about to write."""
    facts: list[CitedFact] = []
    facts.extend(_structural_facts(element_id, edges))
    facts.extend(_common_cause_facts(element_id, edges))
    facts.extend(_sensitivity_facts(element_id, connections, entities or {}))
    if concern_class == SECURITY_CONCERN and sbom_anchored and vulnerability_ids:
        facts.append(CitedFact(
            kind="vulnerabilities",
            text=(
                f"{len(vulnerability_ids)} open vulnerability finding(s) against {element_id}: "
                f"{', '.join(sorted(vulnerability_ids))}"
            ),
        ))
        if security_basis_snapshot_id:
            # In the basis, so a newly disclosed vulnerability retires a security-concern judgement
            # made against the older picture — and leaves safety judgements untouched.
            facts.append(CitedFact(
                kind="security-snapshot",
                text=f"assessed against security snapshot {security_basis_snapshot_id}",
            ))
    return OccurrenceEvidence(facts=tuple(facts))
