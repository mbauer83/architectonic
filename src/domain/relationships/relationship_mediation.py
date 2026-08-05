"""When an intermediate *is* the relationship it stands between, its legs assert that relationship.

A composition rule that derives a **certain** result through a declared intermediate says the
intermediate carries a relationship rather than holding one of its own: ArchiMate's junction is the
case in point (`RJ3`). Two consequences follow for authoring, and both are the rule's own words, read
back here rather than restated:

* `requires_same_connection_type` — the legs must agree on a type, because they are one relationship;
* `requires_permitted_result` — that type must be permitted between the participants, because what
  the model asserts through the intermediate is a relationship *between them*.

The type-level permission table cannot say either. It admits every junction-capable type between an
element and a junction, in both directions, and has to: which one is admissible depends on what else
that instance joins, which is not a property of either type. So the table alone let a model assert
through an intermediate what it may not assert directly — and once derivation passes through it, that
assertion becomes a derived relationship the ontology forbids.

A **potential** rule (`PDR12`, a grouping's realization holding of its members) imposes nothing here:
it makes no assertion of fact, so there is nothing for authoring to be answerable for.

Kept pure and free of any ontology's vocabulary: callers supply the mediation the rules declare, the
legs the graph holds, and the lookups. Two enforce it and must not drift — the verifier reports
E128/E129 against the file that declares the offending leg, and the write path refuses it.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from src.domain.ontology_representation.artifact_types import ConnectionRecord
from src.domain.relationships.relationship_derivation_rules import CompositionRule


@dataclass(frozen=True)
class PassThroughMediation:
    """A declared intermediate that carries a relationship on, and what its rule demands of the legs."""

    spec_ref: str
    intermediate_classes: frozenset[str]
    intermediate_types: frozenset[str]
    requires_same_connection_type: bool
    requires_permitted_result: bool


def pass_through_mediations(rules: Iterable[CompositionRule]) -> tuple[PassThroughMediation, ...]:
    """Every rule that passes a relationship through an intermediate as a *certain* result.

    Certainty is the whole criterion: a certain result means the model asserts the derived
    relationship, so its legs answer for it. Nothing selects on which intermediate an ontology happens
    to declare.
    """
    return tuple(
        PassThroughMediation(
            spec_ref=rule.spec_ref,
            intermediate_classes=frozenset({rule.intermediate_class} if rule.intermediate_class else ()),
            intermediate_types=frozenset(
                {rule.intermediate_artifact_type} if rule.intermediate_artifact_type else ()
            ),
            requires_same_connection_type=rule.requires_same_connection_type,
            requires_permitted_result=rule.requires_permitted_result,
        )
        for rule in rules
        if rule.certainty == "certain" and (rule.intermediate_class or rule.intermediate_artifact_type)
    )


def mediation_governing(
    entity_type: str | None,
    classes_of_type: Callable[[str], frozenset[str]],
    mediations: Iterable[PassThroughMediation],
) -> PassThroughMediation | None:
    """The mediation whose declared intermediate *entity_type* is, if any."""
    if entity_type is None:
        return None
    classes = classes_of_type(entity_type)
    for mediation in mediations:
        if entity_type in mediation.intermediate_types or not mediation.intermediate_classes.isdisjoint(classes):
            return mediation
    return None


@dataclass(frozen=True)
class MediatedLeg:
    """One relationship attached to an intermediate, as its declaring file states it.

    *upstream* is True for a leg declared **into** the intermediate (the participant's own outgoing
    file) and False for one declared **out of** it (the intermediate's file).
    """

    entity_id: str
    connection_type: str
    upstream: bool


def legs_from_records(
    *, inbound: Iterable[ConnectionRecord], outbound: Iterable[ConnectionRecord]
) -> tuple[MediatedLeg, ...]:
    """The legs of one intermediate, from the connections the graph holds in each direction.

    Both callers ask the graph the same two questions, so which direction means "upstream" is decided
    once here rather than agreed twice.
    """
    return (
        *(MediatedLeg(entity_id=c.source, connection_type=c.conn_type, upstream=True) for c in inbound),
        *(MediatedLeg(entity_id=c.target, connection_type=c.conn_type, upstream=False) for c in outbound),
    )


@dataclass(frozen=True)
class MixedLegTypes:
    """The legs of one intermediate do not agree on a relationship type."""

    intermediate_id: str
    intermediate_type: str
    carried: str
    others: tuple[str, ...]

    def message(self) -> str:
        others = ", ".join(repr(other) for other in self.others)
        return (
            f"The {self.intermediate_type} '{self.intermediate_id}' carries relationships of different "
            f"types: this leg carries '{self.carried}' while others carry {others}. Its legs are one "
            f"relationship, so every leg carries the same type."
        )


@dataclass(frozen=True)
class InadmissibleJoin:
    """The type an intermediate carries is not permitted between two participants it joins."""

    intermediate_id: str
    intermediate_type: str
    carried: str
    source_id: str
    source_type: str
    target_id: str
    target_type: str
    alternatives: tuple[str, ...]

    def message(self) -> str:
        alternatives = ", ".join(self.alternatives) if self.alternatives else "none"
        return (
            f"Relationship '{self.carried}' carried through the {self.intermediate_type} "
            f"'{self.intermediate_id}' is not permitted from '{self.source_type}' to "
            f"'{self.target_type}' ('{self.source_id}' -> '{self.target_id}'). Only relationships "
            f"permitted between every participant it joins may pass through it. "
            f"Permitted alternatives for that pair: {alternatives}."
        )


MediationOffence = MixedLegTypes | InadmissibleJoin


def mediation_offences(
    mediation: PassThroughMediation,
    *,
    intermediate_id: str,
    intermediate_type: str,
    carried: str,
    near_id: str,
    near_is_upstream: bool,
    legs: Iterable[MediatedLeg],
    type_of: Callable[[str], str | None],
    permitted_types: Callable[[str, str], frozenset[str]],
) -> tuple[MediationOffence, ...]:
    """Judge one leg of *intermediate_id* against the rest, by what *mediation* requires.

    *legs* are the intermediate's other legs, however the caller knows them; the leg under judgement
    is identified by *near_id* and *near_is_upstream* and need not appear among them — at write time
    it does not exist yet, and at verification time it usually does. Only the pairs that leg takes
    part in are returned, so each file answers for what it declares rather than for the whole
    cross-product.

    Mixed leg types are returned alone: with no type agreed there is no single type left to ask about,
    and reporting both would give two diagnoses for one defect.
    """
    known = {(leg.entity_id, leg.connection_type, leg.upstream) for leg in legs}
    known.add((near_id, carried, near_is_upstream))
    others = tuple(sorted({conn_type for _, conn_type, _ in known if conn_type != carried}))
    if mediation.requires_same_connection_type and others:
        return (
            MixedLegTypes(
                intermediate_id=intermediate_id,
                intermediate_type=intermediate_type,
                carried=carried,
                others=others,
            ),
        )
    if not mediation.requires_permitted_result:
        return ()
    judged = (
        _inadmissible(
            intermediate_id=intermediate_id,
            intermediate_type=intermediate_type,
            carried=carried,
            source_id=source_id,
            target_id=target_id,
            type_of=type_of,
            permitted_types=permitted_types,
        )
        for source_id, target_id in _pairs(known, near_id=near_id, near_is_upstream=near_is_upstream)
    )
    return tuple(offence for offence in judged if offence is not None)


def _pairs(
    known: set[tuple[str, str, bool]], *, near_id: str, near_is_upstream: bool
) -> tuple[tuple[str, str], ...]:
    """The (source, target) pairs the leg under judgement takes part in, in id order."""
    far_ends = sorted(entity_id for entity_id, _, upstream in known if upstream is not near_is_upstream)
    return tuple(
        (near_id, far_id) if near_is_upstream else (far_id, near_id)
        for far_id in far_ends
        if far_id != near_id
    )


def _inadmissible(
    *,
    intermediate_id: str,
    intermediate_type: str,
    carried: str,
    source_id: str,
    target_id: str,
    type_of: Callable[[str], str | None],
    permitted_types: Callable[[str, str], frozenset[str]],
) -> InadmissibleJoin | None:
    source_type, target_type = type_of(source_id), type_of(target_id)
    if source_type is None or target_type is None:
        return None
    permitted = permitted_types(source_type, target_type)
    if carried in permitted:
        return None
    return InadmissibleJoin(
        intermediate_id=intermediate_id,
        intermediate_type=intermediate_type,
        carried=carried,
        source_id=source_id,
        source_type=source_type,
        target_id=target_id,
        target_type=target_type,
        alternatives=tuple(sorted(permitted)),
    )
