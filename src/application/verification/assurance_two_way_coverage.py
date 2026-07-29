"""Findings that need both models, each using one to say what is missing from the other.

This is the clearest thing the joined model buys, and it runs in both directions.

*Structure naming an analysis gap*: the architecture graph shows an element to be load-bearing — a
sole provider, or carrying many typed dependents — and no analysis has ever looked at it. A
component nobody has drawn into a control structure is invisible to the hazard analysis, and the
architecture model is the only place that knows it exists.

*Analysis naming an architecture gap*: a failure mode reaches a severe loss through data that
carries no classification at all. The analysis has established that this path matters; the
architecture has not said how sensitive what flows along it is.

*Redundancy that is not redundancy*: two elements standing as each other's alternative that both
rely on the same thing underneath.

Neither direction writes anything. Assurance never writes to the architecture repository, and a
finding is a read rendered where it is useful — the architect's page for the ones they can fix.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from src.application.assurance_fmea_architecture import (
    ArchitectureBasis,
    accessed_data_by_element,
    classifications,
)
from src.application.assurance_fmea_occurrence_evidence import (
    ACCESS_CONNECTION_TYPE,
    CLASSIFIED_TYPES,
    SENSITIVITY_ATTRIBUTE,
)
from src.application.verification.assurance_findings import (
    LOAD_BEARING_ELEMENT_IS_ANALYSED,
    REDUNDANT_ELEMENTS_DO_NOT_SHARE_A_CAUSE,
    SEVERE_FAILURE_TOUCHES_CLASSIFIED_DATA,
    AssuranceFindingKind,
)
from src.domain.assurance.fmea_structural_signals import (
    TypedEdge,
    common_cause_exposure,
    interchangeable_pairs,
    reliance_on,
)

#: An element carrying at least this many typed dependents is load-bearing enough that an analysis
#: overlooking it is worth saying out loud. Below it, silence is not evidence of a gap.
MANY_DEPENDENTS = 4

SEVERE_LOSS_VALUES = frozenset({"major", "catastrophic"})


@dataclass(frozen=True)
class CoverageFinding:
    """A finding about one of the two models, expressed without writing to either."""

    kind: AssuranceFindingKind
    subject_id: str
    message: str
    witness: tuple[str, ...] = ()
    subject_name: str = ""
    """The subject's reader-facing name, when the architecture model can supply one.

    Carried so a reader can tell which element a finding is about. A list of a hundred findings
    identified only by artifact id is a list nobody acts on — which is what it was."""

    @property
    def code(self) -> str:
        return self.kind.code


def element_names(basis: ArchitectureBasis) -> dict[str, str]:
    """Element id → reader-facing name, from the one place these surfaces read the graph.

    `display_label` first, so a finding names an element the way every other surface names it.
    """
    return {
        element_id: str(entity.get("display_label") or entity.get("name") or "")
        for element_id, entity in basis.entities.items()
        if entity.get("display_label") or entity.get("name")
    }


def load_bearing_but_unanalysed(
    *,
    edges: Sequence[TypedEdge],
    analysed_element_ids: frozenset[str],
    analysable_element_ids: frozenset[str] = frozenset(),
    names: Mapping[str, str] | None = None,
) -> tuple[CoverageFinding, ...]:
    """Elements many things depend on that no failure-mode analysis has reached.

    Two restrictions, both learned from what this produced against the repository this software
    describes — 107 findings, of which sixteen were requirements, twelve outcomes, ten goals, three
    values and two principles.

    **`sole_providers` is deliberately not among the reasons.** It reported "nothing can stand in for
    it", which the model never says: what it actually computes is the target of some element's single
    modelled dependency, so it measures how sparsely the *source* is drawn. Seventy-four of the 107
    rested on it. This is the same error, in the same words, that `redundancy_sharing_a_cause` is
    already withheld for — and the same remedy applies: the model can state that two elements stand in
    for each other, through an OR-junction, and the reason becomes sound when it derives from that
    declaration instead of from how much of the graph happens to be drawn. The function and its tests
    stay; this no longer feeds it.

    **`analysable_element_ids` narrows the candidates to elements a failure mode is a sensible
    question about** — see `fmea_analysable_elements`. A goal does not fail; it is met or missed.
    Asking for the failure modes of a goal is a question with no answer, and a hundred of them is a
    list nobody reads. An empty set narrows nothing, so a caller without the ontology still gets the
    dependency finding rather than silently none.

    ``names`` maps element id → reader-facing name. Optional, and absent means the finding carries
    no name: a caller with no architecture model still gets sound findings, and inventing a label
    for an element nothing can describe would be worse than showing its id."""
    candidates = {edge.target_id for edge in edges if edge.target_id}
    if analysable_element_ids:
        candidates &= analysable_element_ids
    findings: list[CoverageFinding] = []
    for element_id in sorted(candidates - analysed_element_ids):
        reliance = reliance_on(element_id, edges)
        if reliance is None or reliance.dependent_count < MANY_DEPENDENTS:
            continue
        reason = f"{reliance.dependent_count} typed dependents rely on it"
        provisional = " This rests on a thinly modelled neighbourhood." if reliance.provisional else ""
        findings.append(CoverageFinding(
            kind=LOAD_BEARING_ELEMENT_IS_ANALYSED,
            subject_id=element_id,
            # The id is not repeated in the message: the surface showing these already leads with
            # the element, and a sentence that restated it produced every line twice on screen.
            message=(
                f"Load-bearing — {reason} — but appears in no control structure and has no "
                f"failure modes.{provisional}"
            ),
            witness=reliance.witness,
            subject_name=(names or {}).get(element_id, ""),
        ))
    return tuple(findings)


def severe_failure_over_unclassified_data(
    *,
    element_ids_reaching_severe_loss: Mapping[str, str],
    accessed_data_by_element: Mapping[str, Sequence[str]],
    data_classifications: Mapping[str, str],
) -> tuple[CoverageFinding, ...]:
    """Severe failures whose element touches data nobody has classified."""
    findings: list[CoverageFinding] = []
    for element_id, severity in sorted(element_ids_reaching_severe_loss.items()):
        if severity not in SEVERE_LOSS_VALUES:
            continue
        touched = list(accessed_data_by_element.get(element_id, ()))
        if not touched:
            continue
        unclassified = [d for d in touched if not str(data_classifications.get(d, "")).strip()]
        if not unclassified:
            continue
        findings.append(CoverageFinding(
            kind=SEVERE_FAILURE_TOUCHES_CLASSIFIED_DATA,
            subject_id=element_id,
            message=(
                f"{element_id} can fail into a {severity} loss and accesses "
                f"{len(unclassified)} unclassified data object(s): {', '.join(sorted(unclassified))}. "
                "Classifying them is an architecture edit, not an analysis one."
            ),
            witness=tuple(f"{element_id} accesses {d}" for d in sorted(unclassified)),
        ))
    return tuple(findings)


def redundancy_sharing_a_cause(*, edges: Sequence[TypedEdge]) -> tuple[CoverageFinding, ...]:
    """Pairs that stand in for each other while both relying on the same thing."""
    shared = common_cause_exposure(interchangeable_pairs(edges), edges)
    return tuple(
        CoverageFinding(
            kind=REDUNDANT_ELEMENTS_DO_NOT_SHARE_A_CAUSE,
            subject_id=exposure.left_id,
            message=(
                f"{exposure.left_id} and {exposure.right_id} stand as each other's alternative but "
                f"both rely on {exposure.shared_ancestor_id}. A failure there takes both, so this "
                "pair is not the redundancy it looks like."
            ),
            witness=exposure.left_witness + exposure.right_witness,
        )
        for exposure in shared
    )


def two_way_findings(
    *,
    basis: ArchitectureBasis,
    analysed_element_ids: frozenset[str],
    severity_by_element: Mapping[str, str],
) -> tuple[CoverageFinding, ...]:
    """Every finding that needs both models, from one assembled view of the graph.

    One entry point rather than a call per direction at each caller, so a surface cannot pick up some
    of them and silently omit the one that would have named its problem. An empty basis yields
    nothing, which is the honest answer when the architecture graph is not available: none of these
    questions can be asked of the assurance store alone.

    `redundancy_sharing_a_cause` is deliberately **not** among them. Its input is every pair of
    elements serving the same dependent, and that is not a pair of alternatives — two elements serving
    the same thing are collaborating. Run against the repository this software describes it produced
    3670 findings, including pairs of a data object and a requirement, which asserts substitutability
    nobody claimed. This model does have a way to say two elements stand in for each other — an
    OR-junction, in a realization relation for instance — and the check becomes sound when it derives
    from that declaration instead of from co-service. The function and its tests stay; nothing feeds
    it until then.
    """
    if not basis.edges:
        return ()
    return (
        *load_bearing_but_unanalysed(
            edges=basis.edges,
            analysed_element_ids=analysed_element_ids,
            analysable_element_ids=basis.analysable_element_ids,
            names=element_names(basis),
        ),
        *severe_failure_over_unclassified_data(
            element_ids_reaching_severe_loss=severity_by_element,
            accessed_data_by_element=accessed_data_by_element(
                basis, access_connection_type=ACCESS_CONNECTION_TYPE,
            ),
            data_classifications=classifications(
                basis, attribute=SENSITIVITY_ATTRIBUTE, classified_types=CLASSIFIED_TYPES,
            ),
        ),
    )
