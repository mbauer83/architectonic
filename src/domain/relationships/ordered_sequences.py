"""Which elements are ordered sequences, which relations compose them, and which express order.

Three declared facts, read off the ontology rather than named here, so the question "does this
sequence say what order its parts run in?" can be asked of any ontology without spelling one of its
type names:

* an entity type **denotes an ordered sequence** when it declares `denotes_ordered_sequence`;
* a relation **composes** when it is containment that claims its target exclusively — a part of that
  whole alone (`relationship_kind: containment` with `exclusive_target`), which is composition and
  not aggregation;
* a relation **expresses order** when its `derivation_role` is `dynamic` — the role the derivation
  rules already give the relations that carry time or causality between behaviours;
* an element **carries order on** when it is the intermediate of a certain composition rule whose
  legs both express order — the pass-through the ontology already declares for its junctions — so
  part → junction → part is order between the parts, as part → part is.

The core (`unordered_parts`) takes the relations as a lookup, so the repository-wide rule reading
files and a single element read off the index ask the same question the same way.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from src.domain.ontology_representation.ontology_types import (
    CONTAINMENT_KIND,
    ConnectionTypeInfo,
    EntityTypeInfo,
)
from src.domain.relationships.relationship_derivation_rules import CompositionRule

#: The derivation role whose relations carry order between behaviours.
ORDERING_DERIVATION_ROLE = "dynamic"


@dataclass(frozen=True)
class Relation:
    """One declared relation, reduced to what the question needs."""

    conn_type: str
    source: str
    target: str


@dataclass(frozen=True)
class SequenceVocabulary:
    """The ontology's answers to the four questions, resolved to type names once."""

    sequence_types: frozenset[str]
    composing: frozenset[str]
    ordering: frozenset[str]
    #: Entity types that carry order through rather than being ordered: the intermediates of a
    #: *certain* composition rule whose two legs both express order — a relation passing through one
    #: is one relation between what it joins (ArchiMate's junction, by its class, under RJ3).
    order_carriers: frozenset[str] = frozenset()

    @classmethod
    def from_ontology(
        cls,
        entity_types: Mapping[str, EntityTypeInfo],
        connection_types: Mapping[str, ConnectionTypeInfo],
        rules: Iterable[CompositionRule] = (),
    ) -> SequenceVocabulary:
        return cls(
            sequence_types=frozenset(str(n) for n, info in entity_types.items() if info.denotes_ordered_sequence),
            composing=frozenset(
                str(n) for n, info in connection_types.items()
                if info.relationship_kind == CONTAINMENT_KIND and info.exclusive_target
            ),
            ordering=frozenset(
                str(n) for n, info in connection_types.items() if info.derivation_role == ORDERING_DERIVATION_ROLE
            ),
            order_carriers=_order_carriers(entity_types, rules),
        )


def _order_carriers(entity_types: Mapping[str, EntityTypeInfo], rules: Iterable[CompositionRule]) -> frozenset[str]:
    carrying = [
        rule for rule in rules
        if rule.certainty == "certain"
        and rule.first_role == rule.second_role == ORDERING_DERIVATION_ROLE
        and (rule.intermediate_class or rule.intermediate_artifact_type)
    ]
    classes = {rule.intermediate_class for rule in carrying if rule.intermediate_class}
    types = {rule.intermediate_artifact_type for rule in carrying if rule.intermediate_artifact_type}
    return frozenset(
        str(name) for name, info in entity_types.items() if str(name) in types or not classes.isdisjoint(info.classes)
    )


@dataclass(frozen=True)
class SequenceGraph:
    """What the question reads of a model: each element's outgoing relations, and each element's type."""

    outgoing: Callable[[str], Iterable[Relation]]
    type_of: Callable[[str], str | None]


def _reaches_another_part(
    start: str, parts: frozenset[str], graph: SequenceGraph, vocabulary: SequenceVocabulary
) -> bool:
    """Whether a path of ordering relations runs from *start* to another part, passing only through
    elements that carry order on. Iterative and visited-guarded, so a cycle of carriers terminates."""
    frontier, seen = [start], {start}
    while frontier:
        node = frontier.pop()
        for relation in graph.outgoing(node):
            target = relation.target
            if relation.conn_type not in vocabulary.ordering or target in seen:
                continue
            if target in parts:
                return True
            seen.add(target)
            if graph.type_of(target) in vocabulary.order_carriers:
                frontier.append(target)
    return False


def unordered_parts(element_id: str, graph: SequenceGraph, vocabulary: SequenceVocabulary) -> tuple[str, ...]:
    """The composed parts of *element_id* when there are two or more and nothing orders them; else ().

    Two parts are ordered when a path of relations that express order connects them, directly or
    through elements that only carry order on (a junction). The caller decides whether *element_id* is
    of a sequence type — this asks only about its parts.
    """
    parts = frozenset(r.target for r in graph.outgoing(element_id) if r.conn_type in vocabulary.composing)
    ordered = any(_reaches_another_part(part, parts, graph, vocabulary) for part in parts)
    return tuple(sorted(parts)) if len(parts) >= 2 and not ordered else ()
