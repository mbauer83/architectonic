"""The authoring rule for a pass-through intermediate is the composition rule's own words.

`RJ3` already says what a junction demands of its legs — `requires_same_connection_type` and
`requires_permitted_result` — so a verifier that restated those demands in code would hold a second
copy of a rule the ontology owns, free to drift from it. These tests pin the reading, not the
restatement: change the flag and the demand changes with it.

The certainty split is the other half. A *certain* result means the model asserts the derived
relationship, so its legs answer for it; a *potential* one (`PDR12`, a grouping's realization holding
of its members) asserts nothing, so authoring owes nothing — a grouping may aggregate a member that
could not itself realize what the grouping realizes, and that is a legitimate model.
"""

from __future__ import annotations

from src.domain.relationships.relationship_derivation_rules import CompositionRule
from src.domain.relationships.relationship_mediation import (
    InadmissibleJoin,
    MediatedLeg,
    MixedLegTypes,
    legs_from_records,
    mediation_governing,
    mediation_offences,
    pass_through_mediations,
)
from src.infrastructure.app_bootstrap import get_module_registry

_ASSIGNMENT = "archimate-assignment"
_TRIGGERING = "archimate-triggering"


def _rule(**overrides) -> CompositionRule:
    defaults = dict(
        spec_ref="TEST",
        certainty="certain",
        first_role="structural",
        second_role="structural",
        result="first",
        intermediate_class="junction",
        requires_same_connection_type=True,
        requires_permitted_result=True,
    )
    return CompositionRule(**{**defaults, **overrides})


def _mediation(**overrides):
    (mediation,) = pass_through_mediations([_rule(**overrides)])
    return mediation


def _offences(mediation, *, carried: str = _ASSIGNMENT, legs=(), types=None, permitted=frozenset()):
    resolved = types or {"NEAR": "function", "FAR": "function"}
    return mediation_offences(
        mediation,
        intermediate_id="JUN",
        intermediate_type="and-junction",
        carried=carried,
        near_id="NEAR",
        near_is_upstream=True,
        legs=legs,
        type_of=resolved.get,
        permitted_types=lambda _source, _target: frozenset(permitted),
    )


# ── what the rules declare ────────────────────────────────────────────────────


def test_the_real_ontology_declares_a_pass_through_mediation() -> None:
    """If this is empty the reading silently enforces nothing — the failure mode of derived data."""
    rules = [
        rule
        for module in get_module_registry().all_ontologies().values()
        for rule in module.derivation_rules
    ]
    mediations = pass_through_mediations(rules)

    assert mediations
    assert any("junction" in mediation.intermediate_classes for mediation in mediations)
    assert all(
        mediation.requires_same_connection_type and mediation.requires_permitted_result
        for mediation in mediations
        if "junction" in mediation.intermediate_classes
    )


def test_a_potential_rule_declares_no_authoring_constraint() -> None:
    """`PDR12` pushes a grouping's realization down potentially; that is an inference, not a claim."""
    assert pass_through_mediations([_rule(certainty="potential", intermediate_artifact_type="grouping")]) == ()


def test_a_rule_without_an_intermediate_is_not_a_mediation() -> None:
    assert pass_through_mediations([_rule(intermediate_class=None)]) == ()


def test_the_governing_mediation_is_found_by_class_or_by_type() -> None:
    by_class = _mediation()
    by_type = _mediation(intermediate_class=None, intermediate_artifact_type="grouping")

    assert mediation_governing("or-junction", lambda _t: frozenset({"junction"}), [by_class]) is by_class
    assert mediation_governing("grouping", lambda _t: frozenset({"composite-element"}), [by_type]) is by_type
    assert mediation_governing("function", lambda _t: frozenset({"behavior"}), [by_class, by_type]) is None


# ── what the demands do ───────────────────────────────────────────────────────


def test_mixed_leg_types_are_refused_when_the_rule_demands_one_type() -> None:
    offences = _offences(
        _mediation(),
        legs=[MediatedLeg(entity_id="FAR", connection_type=_TRIGGERING, upstream=False)],
    )

    assert [type(offence) for offence in offences] == [MixedLegTypes]


def test_mixed_leg_types_are_tolerated_when_the_rule_does_not_demand_one_type() -> None:
    """The demand is the rule's, so withdrawing it withdraws the diagnosis."""
    offences = _offences(
        _mediation(requires_same_connection_type=False, requires_permitted_result=False),
        legs=[MediatedLeg(entity_id="FAR", connection_type=_TRIGGERING, upstream=False)],
    )

    assert offences == ()


def test_an_unpermitted_pair_is_refused_when_the_rule_demands_a_permitted_result() -> None:
    offences = _offences(
        _mediation(),
        legs=[MediatedLeg(entity_id="FAR", connection_type=_ASSIGNMENT, upstream=False)],
        permitted=frozenset({"archimate-association"}),
    )

    (offence,) = offences
    assert isinstance(offence, InadmissibleJoin)
    assert offence.alternatives == ("archimate-association",)


def test_a_permitted_pair_passes() -> None:
    offences = _offences(
        _mediation(),
        legs=[MediatedLeg(entity_id="FAR", connection_type=_ASSIGNMENT, upstream=False)],
        permitted=frozenset({_ASSIGNMENT}),
    )

    assert offences == ()


def test_only_the_far_side_is_paired_with_the_leg_under_judgement() -> None:
    """A second leg on the *same* side is not a pair — an intermediate joins across itself."""
    offences = _offences(
        _mediation(),
        legs=[MediatedLeg(entity_id="OTHER", connection_type=_ASSIGNMENT, upstream=True)],
        types={"NEAR": "function", "OTHER": "function"},
    )

    assert offences == ()


def test_an_unresolvable_endpoint_is_not_judged() -> None:
    """A missing entity is E120's business; guessing a type here would invent a defect."""
    offences = _offences(
        _mediation(),
        legs=[MediatedLeg(entity_id="GONE", connection_type=_ASSIGNMENT, upstream=False)],
        types={"NEAR": "function"},
    )

    assert offences == ()


def test_the_legs_of_a_record_pair_carry_their_direction() -> None:
    class _Record:
        def __init__(self, source: str, target: str, conn_type: str) -> None:
            self.source, self.target, self.conn_type = source, target, conn_type

    legs = legs_from_records(
        inbound=[_Record("UP", "JUN", _ASSIGNMENT)], outbound=[_Record("JUN", "DOWN", _ASSIGNMENT)]
    )

    assert {(leg.entity_id, leg.upstream) for leg in legs} == {("UP", True), ("DOWN", False)}
