"""The search vocabulary: which kinds are searchable, in what order, and what a record is called.

Its own module rather than a section of `ontology_representation/artifact_types.py`, for two reasons
that point the same way.

**Altitude.** The record types are the ontology's — an entity, a connection, a diagram, a document, a
note. Which of them *search* offers, how they rank against one another, and which field of each one a
reader would call its title are questions about the search surface, not about the ontology.

**Size.** `artifact_types.py` stood at 396 lines against the coding standard's 350-line hard limit,
and two cycles of this release add to it.

**What is deliberately *not* here: `SearchHit` and `SearchResult`.** A hit names the five record
classes in its `record` union, so a module holding it would have to name `artifact_types` — and
`artifact_types` re-exports this module's names, so the two would name each other. That is refused by
`tests/architecture/test_no_type_checking_import_cycles.py` even under `TYPE_CHECKING`, on the ground
that a type checker then has to guess which side to resolve first, and the gate's own remedy is to
keep in the shared module only what can be imported downward. Nothing here needs a record class:
the kinds are strings, the order is strings, and the title accessor probes attributes.

**The title accessor probes attributes rather than matching types.** Not laziness — a type-matching
chain would put every record kind's name into a module whose purpose is to answer one question
generically, and it is what lets the search use case's tier predicate name no kind at all.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Literal, Protocol, TypeAlias, runtime_checkable

# ── The searchable-kind vocabulary, in one place ─────────────────────────────
# Two spellings of the same list, and they have to agree: `RecordType` is the discriminator on an
# individual hit, `SearchableKind` the member of the include-set that gates which kinds participate.
# Both were previously restated in `application/artifacts/_search.py`, in `artifacts/repository.py`,
# on `SearchHit` below and in the REST contract — four copies of one vocabulary, which is how a fifth
# kind becomes a hunt rather than an edit.
RecordType: TypeAlias = Literal["entity", "connection", "diagram", "document", "scratchpad-note"]
SearchableKind: TypeAlias = Literal[
    "entities", "connections", "diagrams", "documents", "scratchpad-notes"
]

#: Kind → the record type its hits carry. The plural is what a caller asks for; the singular is what
#: it gets back. Typed `str` → `str` rather than Literal → Literal because every caller looks a
#: *runtime* value up in it — an FTS row's `record_type` column, a request's `include_` flag — and a
#: narrower key type only moves the narrowing to the call site.
KIND_TO_RECORD_TYPE: Mapping[str, str] = MappingProxyType(
    {
        "entities": "entity",
        "connections": "connection",
        "diagrams": "diagram",
        "documents": "document",
        "scratchpad-notes": "scratchpad-note",
    }
)
RECORD_TYPE_TO_KIND: Mapping[str, str] = MappingProxyType(
    {record_type: kind for kind, record_type in KIND_TO_RECORD_TYPE.items()}
)
ALL_SEARCHABLE_KINDS: frozenset[str] = frozenset(KIND_TO_RECORD_TYPE)

#: Kinds that must never outrank the others on similarity alone, **in the order they are drawn**.
#:
#: A sequence rather than a set, and that is the point: a note is a half-formed thought and an entity
#: is a commitment, so a scratchpad can never push model content down a result list — the condition
#: the feature was allowed into the index under. A *set* could say which kinds are held back but not
#: which of them comes first, and one subordinate kind was all that ever needed saying. A second one
#: needs an order, and inventing that order at each reader is how two readers come to disagree.
#:
#: Everything not named here takes part in the round-robin; these are appended after it, in this
#: order, subject to the floor that keeps them from being starved out of the window entirely.
SUBORDINATE_RECORD_ORDER: tuple[str, ...] = ("scratchpad-note",)

#: Membership, derived rather than restated. Kept because the predicate reads better than a scan at
#: the three call sites that ask it, and derived because a second literal is a second declaration.
SUBORDINATE_RECORD_TYPES: frozenset[str] = frozenset(SUBORDINATE_RECORD_ORDER)


@runtime_checkable
class SemanticSearchProvider(Protocol):
    def top_k(self, query: str, k: int, *, threshold: float = 0.75) -> list[tuple[float, str]]: ...


def record_title(record: object) -> str | None:
    """What a reader would call this record, whatever kind it is — or `None` if it has no name.

    One owner for a fact that was spelled twice: `scoring.py` decides which field carries a kind's
    highest match weight, and `_search_hits.py` decides which field becomes the display `name`. A
    third reader asking the same question a third way is how those two come to disagree about what a
    document is called.

    `title` before `name` because a document carries both meanings under the first, and a diagram,
    entity and note carry it under the second. A connection has neither and answers `None` — which is
    correct rather than empty: it is not a thing with a title, and a caller comparing a query against
    `""` would silently match a query that is also empty.
    """
    for attribute in ("title", "name"):
        value = getattr(record, attribute, None)
        if isinstance(value, str) and value:
            return value
    return None
