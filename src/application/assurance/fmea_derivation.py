"""Deriving a failure mode's severity and detectability from the assurance graph.

Both are functions of the model, so both are computed rather than asked for. What each is computed
*from* is the substance:

**Severity** is the worst loss the failure can reach, following the causal spine the analysis
already holds: `failure-mode --leads-to--> hazard --leads-to--> loss`. It is the loss's own
severity, so a failure mode inherits consequence from the chain rather than restating it. Absent
when no loss is reachable — that is a coverage gap, and rendering it as a low severity would make
an unlinked failure mode look harmless.

**Detectability** is a property of the detection controls that exist, not a statistic. It is derived
from the constraints that `detects` this failure mode and from nothing else, because that is the
only thing that measures whether *this* failure gets caught. A component's declared telemetry is
shown beside the row as context for whoever writes the next control, and never raises the band: a
component that emits logs is not thereby a component whose silent partial-output failure is noticed.

Each derived value carries the inputs it came from, and those inputs are what the basis digest is
computed over. That is what makes a human judgement stop applying when the model moves — see
`fmea_factors`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from src.application.verification._assurance_rule_support import attributes_of
from src.domain.assurance.fmea_factors import (
    DETECTABILITY_SCALE,
    SEVERITY_SCALE,
    UNGROUNDED_BASIS,
    compute_basis_digest,
)
from src.domain.viewpoints.viewpoint_derived_value_reduction import reduce_values

LEADS_TO = "leads-to"
DETECTS = "detects"
EVIDENCED_BY = "evidenced-by"
EVIDENCED_BY_ARTIFACT = "evidenced-by-artifact"

HAZARD = "hazard"
LOSS = "loss"
EVIDENCE = "evidence"

#: Detectability bands, weakest evidence of detection first. Index alignment with
#: `DETECTABILITY_SCALE` is asserted by test rather than assumed.
NO_CONTROL, CONTROL_ONLY, EVIDENCED, SEALED, PIPELINE_EXERCISED = DETECTABILITY_SCALE

#: Attribute by which an evidence node names the quality gate that runs it. Present means the
#: control is exercised by an automated check rather than by someone remembering to look.
GATE_ATTRIBUTE = "gate"


@dataclass(frozen=True)
class DerivedFactor:
    """One derived value together with the inputs that produced it."""

    value: str | None
    basis: tuple[str, ...] = ()
    """Cited inputs, ordered, each naming an identifier and the state that mattered. The digest is
    computed over these, so a change of input retires a judgement even when the value is unchanged."""
    witness: tuple[str, ...] = ()
    """The path that produced the value, for a reader who wants to check it."""


@dataclass(frozen=True)
class DerivedFactors:
    severity: DerivedFactor
    detectability: DerivedFactor
    digests: Mapping[str, str] = field(default_factory=dict)


class _Graph:
    """Indexed once per derivation run, so a matrix costs one pass rather than one per row."""

    def __init__(
        self, nodes: Sequence[Mapping[str, object]], edges: Sequence[Mapping[str, object]]
    ) -> None:
        self.nodes: dict[str, Mapping[str, object]] = {str(n["node_id"]): n for n in nodes}
        self._out: dict[tuple[str, str], list[str]] = {}
        self._in: dict[tuple[str, str], list[str]] = {}
        for edge in edges:
            conn = str(edge.get("conn_type", ""))
            source = str(edge.get("source_id", ""))
            target = str(edge.get("target_id", ""))
            self._out.setdefault((source, conn), []).append(target)
            self._in.setdefault((target, conn), []).append(source)

    def out(self, node_id: str, conn_type: str, *, of_type: str | None = None) -> list[str]:
        found = self._out.get((node_id, conn_type), [])
        return [i for i in found if of_type is None or self._type_of(i) == of_type]

    def into(self, node_id: str, conn_type: str, *, of_type: str | None = None) -> list[str]:
        found = self._in.get((node_id, conn_type), [])
        return [i for i in found if of_type is None or self._type_of(i) == of_type]

    def _type_of(self, node_id: str) -> str:
        node = self.nodes.get(node_id)
        return str(node.get("node_type", "")) if node else ""


def derive_severity(failure_mode_id: str, graph: _Graph) -> DerivedFactor:
    """The worst severity among the losses this failure mode can reach, or absence."""
    reached: list[tuple[str, str, str]] = []
    for hazard_id in sorted(set(graph.out(failure_mode_id, LEADS_TO, of_type=HAZARD))):
        for loss_id in sorted(set(graph.out(hazard_id, LEADS_TO, of_type=LOSS))):
            severity = str(attributes_of(dict(graph.nodes[loss_id])).get("severity") or "")
            if severity:
                reached.append((hazard_id, loss_id, severity))
    if not reached:
        return DerivedFactor(value=None)
    # Ordinal max, not lexical: `catastrophic` sorts before `minor` alphabetically.
    worst = reduce_values(
        tuple(severity for _hazard, _loss, severity in reached), "max", ordinal_scale=SEVERITY_SCALE,
    )
    return DerivedFactor(
        value=None if worst is None else str(worst),
        basis=tuple(f"{loss_id}:{severity}" for _hazard, loss_id, severity in sorted(reached)),
        witness=tuple(
            f"{failure_mode_id} --{LEADS_TO}--> {hazard_id} --{LEADS_TO}--> {loss_id} ({severity})"
            for hazard_id, loss_id, severity in sorted(reached)
        ),
    )


def _evidence_state(
    constraint_id: str,
    graph: _Graph,
    *,
    evidenced_ref_ids: frozenset[str],
    sealed_evidence_ids: frozenset[str],
) -> str:
    """How well substantiated one detecting control is: the band its evidence supports."""
    evidence_ids = sorted(set(graph.out(constraint_id, EVIDENCED_BY, of_type=EVIDENCE)))
    if not evidence_ids and constraint_id not in evidenced_ref_ids:
        return CONTROL_ONLY
    if any(
        str(attributes_of(dict(graph.nodes[e])).get(GATE_ATTRIBUTE) or "").strip()
        for e in evidence_ids
        if e in graph.nodes
    ):
        return PIPELINE_EXERCISED
    if any(e in sealed_evidence_ids for e in evidence_ids):
        return SEALED
    return EVIDENCED


def derive_detectability(
    failure_mode_id: str,
    graph: _Graph,
    *,
    evidenced_ref_ids: frozenset[str] = frozenset(),
    sealed_evidence_ids: frozenset[str] = frozenset(),
) -> DerivedFactor:
    """The band the detection controls on this failure mode support.

    Always a value, never absence: "nothing detects this" is a finding, and the weakest band says
    it. Absence would read as "not yet assessed", which is a different and much softer claim.
    """
    controls = sorted(set(graph.into(failure_mode_id, DETECTS)))
    if not controls:
        return DerivedFactor(
            value=NO_CONTROL,
            basis=(),
            witness=(f"no control {DETECTS} {failure_mode_id}",),
        )
    states = {
        control_id: _evidence_state(
            control_id, graph,
            evidenced_ref_ids=evidenced_ref_ids,
            sealed_evidence_ids=sealed_evidence_ids,
        )
        for control_id in controls
    }
    best = reduce_values(tuple(states.values()), "max", ordinal_scale=DETECTABILITY_SCALE)
    return DerivedFactor(
        value=None if best is None else str(best),
        basis=tuple(f"{control_id}:{state}" for control_id, state in sorted(states.items())),
        witness=tuple(
            f"{control_id} --{DETECTS}--> {failure_mode_id} ({state})"
            for control_id, state in sorted(states.items())
        ),
    )


def derive_factors(
    failure_mode_id: str,
    *,
    nodes: Sequence[Mapping[str, object]],
    edges: Sequence[Mapping[str, object]],
    evidenced_ref_ids: frozenset[str] = frozenset(),
    sealed_evidence_ids: frozenset[str] = frozenset(),
    occurrence_basis: Sequence[str] | None = (),
) -> DerivedFactors:
    """Both derived factors for one failure mode, with a basis digest per factor.

    `occurrence_basis` is what an occurrence rationale cited — occurrence has no derived value, but
    it does have a basis, so a judgement about it retires when what it cited changes.

    **`None` is not the empty sequence.** Empty means the architecture graph was read and cites
    nothing about this element, which is a fact a judgement may be held against. `None` means the
    graph could not be read at all, and the digest is then `UNGROUNDED_BASIS` rather than the hash of
    an empty list — a value no judgement may be recorded against, because it would be superseded the
    moment anyone with the model looked. Stated as two types rather than a flag, since it is a
    property of the input and not a mode.

    Severity and detectability are unaffected either way: both derive from the assurance graph, which
    is present whatever the architecture model is doing.
    """
    graph = _Graph(nodes, edges)
    severity = derive_severity(failure_mode_id, graph)
    detectability = derive_detectability(
        failure_mode_id, graph,
        evidenced_ref_ids=evidenced_ref_ids,
        sealed_evidence_ids=sealed_evidence_ids,
    )
    return DerivedFactors(
        severity=severity,
        detectability=detectability,
        digests={
            "severity": compute_basis_digest(list(severity.basis)),
            "detectability": compute_basis_digest(list(detectability.basis)),
            "occurrence": (
                UNGROUNDED_BASIS if occurrence_basis is None
                else compute_basis_digest(list(occurrence_basis))
            ),
        },
    )
