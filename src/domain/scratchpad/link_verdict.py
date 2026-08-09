"""What the canvas may say about a drawn link, and why.

Two tiers, and the split is not this module's invention — it falls out of what the ontology says
about its own [classification levels](../ontology_representation/classification_levels.py):

* the level that **keys relationships** decides whether a pair is permitted at all. A violation
  there is the verifier's **E126**, and it *blocks*: the ontology does not have that relation.
* a level that **narrows relationships** may only restrict what the keying level already permits.
  A violation there is **W128/W129**, and it *warns*: the relation exists, and this specialization
  says it does not apply here.

Which is why B3 was a prerequisite. Before it, "type-level refusal versus specialization-level
narrowing" was a special case someone had noticed twice; after it, it is a consequence of the
declaration, and this module reads the declaration rather than restating the rule.

**Pure.** No catalogs are loaded and no I/O happens here: the caller supplies `permits`, which the
application layer builds from the module registry. That is what makes the many cases below
affordable to test — and there are many, because this vocabulary is what a modal renders to
someone in the middle of drawing.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Literal

#: What the canvas can conclude about a link. Ordered from "say nothing" to "this is wrong".
VerdictKind = Literal["unverified", "reference", "permitted", "narrowed", "refused"]

#: A predicate over an ordered triple: is (source_type) --conn_type--> (target_type) permitted?
Permits = Callable[[str, str, str], bool]

#: The connection types permitted for an ordered pair, in whatever order the ontology declares.
PermittedTypes = Callable[[str, str], Sequence[str]]


@dataclass(frozen=True, slots=True)
class LinkVerdict:
    """The answer, and everything the canvas needs to act on it."""

    kind: VerdictKind
    #: The verifier code this corresponds to, so the canvas and a later `artifact_verify` agree.
    code: str = ""
    message: str = ""
    #: Permitted connection types for the pair as drawn — offered as "did you mean one of these".
    alternatives: tuple[str, ...] = ()
    #: **Leads the remedies when true.** ArchiMate relations are ordered triples, and dragging from
    #: a goal to a capability when the rule reads capability → goal is the commonest slip there is.
    #: One click fixes it, and it is almost certainly what was meant.
    reverse_permitted: bool = False
    #: Which specialization narrowed it, when the verdict is `narrowed`.
    narrowed_by: str = ""

    @property
    def blocks(self) -> bool:
        """Whether a lift may proceed. A narrowing warns and does not stop anything."""
        return self.kind == "refused"

    @property
    def is_settled(self) -> bool:
        """Whether anything has been decided yet — verification does not nag."""
        return self.kind != "unverified"


@dataclass(frozen=True, slots=True)
class Endpoint:
    """One end of a drawn link, as far as it has been decided."""

    destination: str = "undecided"
    element_type: str | None = None
    specialization: str | None = None
    document_type: str | None = None

    @property
    def is_element(self) -> bool:
        return self.destination == "element" and bool(self.element_type)

    @property
    def is_document(self) -> bool:
        return self.destination == "document"


UNVERIFIED = LinkVerdict(kind="unverified")

#: A document is not an ArchiMate element and no relation runs to one. The link is realizable as a
#: document→model *reference*, which the document records — and references are one-way
#: (ADR@1783406789), so the canvas must not care which way the user happened to drag.
_REFERENCE = LinkVerdict(
    kind="reference",
    message=(
        "This becomes a reference from the document to the model rather than a connection. "
        "References run one way and are recorded on the document, so the direction you drew "
        "does not matter."
    ),
)


def verify_link(
    source: Endpoint,
    target: Endpoint,
    *,
    connection_type: str | None,
    permits: Permits,
    permitted_types: PermittedTypes,
    narrows: Callable[[str, str, str, str], str | None] | None = None,
) -> LinkVerdict:
    """The verdict for one drawn link.

    `narrows` answers "does this specialization forbid this triple", returning the slug that did.
    It is optional because a scratchpad may name no specialization at all, and because the
    narrowing tier is exactly the part a meta-ontology may declare it does not have.
    """
    if source.is_document and target.is_document:
        # Two documents relate to each other in prose, not in the model. Nothing to verify.
        return UNVERIFIED
    if source.is_document or target.is_document:
        return _REFERENCE if (source.is_element or target.is_element) else UNVERIFIED
    if not (source.is_element and target.is_element):
        # Verification is not nagging: an undecided end is a question nobody has answered yet.
        return UNVERIFIED

    source_type = source.element_type or ""
    target_type = target.element_type or ""

    if connection_type is None:
        # Both ends are typed but the link is not. The pair either has permitted relations or it
        # has none, and "none" is worth saying before the user goes looking for one.
        options = tuple(permitted_types(source_type, target_type))
        if options:
            return LinkVerdict(kind="unverified", alternatives=options)
        reverse = tuple(permitted_types(target_type, source_type))
        return LinkVerdict(
            kind="refused",
            code="E126",
            message=(
                f"The ontology declares no relation from {source_type} to {target_type}."
            ),
            alternatives=(),
            reverse_permitted=bool(reverse),
        )

    if not permits(source_type, connection_type, target_type):
        reverse = permits(target_type, connection_type, source_type)
        return LinkVerdict(
            kind="refused",
            code="E126",
            message=(
                f"{source_type} --{connection_type}--> {target_type} is not a permitted triple."
                + (" The reverse is." if reverse else "")
            ),
            alternatives=tuple(permitted_types(source_type, target_type)),
            reverse_permitted=reverse,
        )

    narrowed_by = _narrowing_slug(
        source, target, connection_type=connection_type, source_type=source_type,
        target_type=target_type, narrows=narrows,
    )
    if narrowed_by:
        return LinkVerdict(
            kind="narrowed",
            code="W128",
            message=(
                f"Specialization '{narrowed_by}' restricts this relation; "
                f"({source_type} -> {target_type}) is outside what it allows. "
                "The relation is still valid — change the specialization, or accept the warning."
            ),
            narrowed_by=narrowed_by,
        )

    return LinkVerdict(kind="permitted", message=f"{connection_type} is permitted here.")


def _narrowing_slug(
    source: Endpoint,
    target: Endpoint,
    *,
    connection_type: str,
    source_type: str,
    target_type: str,
    narrows: Callable[[str, str, str, str], str | None] | None,
) -> str:
    """Which specialization, if any, narrows this otherwise-permitted triple out of existence."""
    if narrows is None:
        return ""
    for slug in (source.specialization, target.specialization):
        if not slug:
            continue
        found = narrows(slug, connection_type, source_type, target_type)
        if found:
            return found
    return ""


@dataclass(frozen=True, slots=True)
class TypingOptions:
    """What a note may become at one level, in the order the ontology declares them.

    Offered rather than required: every level below the first is optional, and a note that stops
    at `undecided` has still done its job.
    """

    level_id: str
    label: str
    values: tuple[str, ...] = field(default_factory=tuple)
    required: bool = False
