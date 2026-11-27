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
* two parts are **ordered** when a path of relations that express order runs from one to the other,
  whatever it passes through — a junction, an event, a step of another behaviour. A chain of dynamic
  relations derives a dynamic relation between its ends (ArchiMate's derivation of triggering and
  flow), so a junction needs no special case: it is one more element on the path.

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
    """The ontology's answers to the three questions, resolved to type names once."""

    sequence_types: frozenset[str]
    composing: frozenset[str]
    ordering: frozenset[str]

    @classmethod
    def from_ontology(
        cls,
        entity_types: Mapping[str, EntityTypeInfo],
        connection_types: Mapping[str, ConnectionTypeInfo],
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
        )


@dataclass(frozen=True)
class SequenceGraph:
    """What the question reads of a model: each element's outgoing relations."""

    outgoing: Callable[[str], Iterable[Relation]]


def _reaches_another_part(
    start: str, parts: frozenset[str], graph: SequenceGraph, vocabulary: SequenceVocabulary
) -> bool:
    """Whether a path of ordering relations runs from *start* to another part, through anything.
    Iterative and visited-guarded, so a cycle terminates."""
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
            frontier.append(target)
    return False


def unordered_parts(element_id: str, graph: SequenceGraph, vocabulary: SequenceVocabulary) -> tuple[str, ...]:
    """The composed parts of *element_id* when there are two or more and nothing orders them; else ().

    Two parts are ordered when a path of relations that express order connects them, directly or
    through any other elements. The caller decides whether *element_id* is
    of a sequence type — this asks only about its parts.
    """
    parts = frozenset(r.target for r in graph.outgoing(element_id) if r.conn_type in vocabulary.composing)
    ordered = any(_reaches_another_part(part, parts, graph, vocabulary) for part in parts)
    return tuple(sorted(parts)) if len(parts) >= 2 and not ordered else ()
