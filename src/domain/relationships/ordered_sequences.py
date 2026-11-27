"""Which elements are ordered sequences, which relations compose them, and which express order.

Three declared facts, read off the ontology rather than named here, so the question "does this
sequence say what order its parts run in?" can be asked of any ontology without spelling one of its
type names:

* an entity type **denotes an ordered sequence** when it declares `denotes_ordered_sequence`;
* a relation **composes** when it is containment that claims its target exclusively — a part of that
  whole alone (`relationship_kind: containment` with `exclusive_target`), which is composition and
  not aggregation;
* a relation **expresses order** when its `derivation_role` is `dynamic` — the role the derivation
  rules already give the relations that carry time or causality between behaviours.

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
        cls, entity_types: Mapping[str, EntityTypeInfo], connection_types: Mapping[str, ConnectionTypeInfo]
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


def unordered_parts(
    element_id: str, outgoing: Callable[[str], Iterable[Relation]], vocabulary: SequenceVocabulary
) -> tuple[str, ...]:
    """The composed parts of *element_id* when there are two or more and nothing orders them; else ().

    "Nothing orders them" is literal: no relation that expresses order runs from one part to another.
    The caller decides whether *element_id* is of a sequence type — this asks only about its parts.
    """
    parts = frozenset(r.target for r in outgoing(element_id) if r.conn_type in vocabulary.composing)
    ordered = any(
        relation.conn_type in vocabulary.ordering and relation.target in parts and relation.target != part
        for part in parts
        for relation in outgoing(part)
    )
    return tuple(sorted(parts)) if len(parts) >= 2 and not ordered else ()
