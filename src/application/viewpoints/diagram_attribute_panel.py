"""What a reader can do with the attributes of the entities a diagram draws.

The panel behind "colour by" and "print with the entity": the entity types and specializations that
actually occur on one diagram, and for each of them the profile attributes those entities could carry —
with what each attribute is declared to be, whether a ramp or a palette can read it, and how many of
the drawn entities have a value.

**Occurring, not declared.** The ontology declares hundreds of attributes across dozens of types. What
a reader of *this* diagram can act on is the handful its own entities carry, and offering the rest is
the difference between a menu and a catalogue. This is the same convention the seven existing legends
already keep — list what is present.

**The vocabulary is injected, not known.** Which attributes a type has is a *profile* question and this
module asks the profile machinery; which of them a ramp can read is a question about a declared level of
measurement, and this module asks `attribute_scales`. Nothing here names an attribute, a type, or a
diagram family.

**Every attribute can be printed.** There is no `printable` flag, because there is no attribute a
reader may not put on the picture — an owner's name as readily as a risk score. A field carrying one
value for every instance is noise, and the panel does not need to be told what it can always do.

**An attribute several types share is offered once, at the top.** Colouring is by attribute name, and
it applies to every drawn entity that has one — so an attribute more than one drawn type declares
*identically* is a global reading, and burying it inside each type's fold says the opposite. It stays
in those folds too, where its per-type presence count lives; the shared row is a shortcut to the same
choice, not a move.

**Identically defined**, and that qualifier is the whole of it: same declared type, same colour kind,
same value set. Two types declaring `risk_score` as an integer share it. One declaring it an integer
and another a string do not, and colouring by that name globally would put two different meanings on
one scale — so those are reported separately rather than left to look like the attributes that were
simply not shared.

**An absent *value* is reported; an absent *attribute* is not a row.** Those pull in opposite
directions and both are right. An attribute no drawn entity carries is listed with a count of zero,
because a reader who cannot see the attribute cannot learn why nothing is coloured. A type that
declares no attributes at all is left out entirely: this is a panel for *choosing*, and a row with
nothing to choose is a fold that opens on nothing. Which types the diagram draws is a question the
entity list beside it already answers.

That row was originally kept, on the reasoning that "this type is here and offers nothing" is
information. It is — but not information this panel is for. What *is* needed is the count of what the
diagram draws, so a surface can tell "nothing is drawn" from "nothing that is drawn declares
anything" — dropping the rows without it made a diagram of thirteen processes and services report
that it drew no model entities.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from src.application.artifacts.schema import compute_effective_attribute_schema
from src.domain.ontology_representation.artifact_types import EntityRecord
from src.domain.ontology_representation.attribute_scales import declares_ordinal
from src.domain.viewpoints.viewpoint_condition_evaluation import read_attribute_value
from src.domain.viewpoints.viewpoint_criteria import NUMERIC_ATTRIBUTE_TYPES

#: How a reader can be offered colour for an attribute.
#:
#: ``ramp`` interpolates between two endpoints and needs an order: a number, a date, or an ordinal,
#: whose order the ontology declares. ``palette`` gives one colour per value and needs a bounded value
#: set with no inherent order. ``none`` is the honest answer for free text and for a list — a ramp over
#: prose is meaningless and a palette over unbounded values is one colour per entity.
ColourKind = Literal["ramp", "palette", "none"]


@dataclass(frozen=True)
class AttributeOffer:
    """One attribute, as a reading control can offer it."""

    name: str
    #: The declared type as the schema states it, or ``ordinal`` where a level of measurement
    #: overrides it — the same precedence `registry_snapshot` applies, and for the same reason: an
    #: ordinal is written as a string enum, and treating it as a string orders it alphabetically.
    declared_type: str
    colour: ColourKind
    #: The value set, in declared order, for an attribute that has one. An ordinal's order *is* its
    #: rank, so this doubles as the scale a ramp reads.
    values: tuple[str, ...]
    #: How many of the drawn entities of this type carry a value. Zero is reported, not hidden.
    present_on: int
    #: The member a schema declares as its `default`, where it declares one. That member is what a
    #: reader sees on an entity nobody has assessed, so a colouring shows it as unset rather than
    #: giving it a place on the scale.
    unset_value: str | None = None


@dataclass(frozen=True)
class TypeOffer:
    """One entity type, or one specialization of it, as it occurs on this diagram."""

    entity_type: str
    #: The specialization slug this row is about, or ``""`` for the bare type. A specialization is its
    #: own row because it contributes its own attributes: two entities of one type carrying different
    #: specializations do not offer the same set, and merging them would offer each the other's.
    specialization: str
    drawn: int
    attributes: tuple[AttributeOffer, ...]


@dataclass(frozen=True)
class SharedAttributeOffer:
    """One attribute more than one drawn type declares, and how far the agreement goes."""

    attribute: AttributeOffer
    #: The rows that declare it, as ``type`` or ``type/specialization``. Named rather than counted: a
    #: reader deciding whether a global colouring means what they want needs to know over what.
    on_rows: tuple[str, ...]


@dataclass(frozen=True)
class DiagramAttributeOffers:
    """The whole panel: what reads across the diagram, and then what each type declares."""

    #: Attributes several rows declare identically, so colouring by one is a reading of the diagram
    #: rather than of one type. ``present_on`` here counts *entities*, diagram-wide — an entity drawn
    #: under two specializations is one entity, not two.
    shared: tuple[SharedAttributeOffer, ...]
    types: tuple[TypeOffer, ...]
    #: How many model entities the diagram places, whether or not their types declare anything.
    #:
    #: Reported because dropping the attribute-less rows made two very different states look
    #: identical: a diagram that draws no model entities at all, and one that draws thirteen whose
    #: types declare no attributes. A surface with only `types` to read told a reader the second was
    #: the first, which was flatly untrue of a diagram full of processes and services.
    drawn: int
    #: Attribute names several rows declare *differently*. Colouring by one of these is still possible
    #: and still global, and would put two meanings on one scale — which a reader can only weigh if
    #: told. Names only: there is no single definition to report.
    disputed: tuple[str, ...] = ()


def palette_members(offers: DiagramAttributeOffers, attribute: str) -> tuple[str, ...]:
    """The members a palette colours *attribute* by, or nothing where a ramp or no colour applies.

    **The one answer to "palette or ramp".** The renderer used to decide this for itself, by asking the
    viewpoint criteria snapshot whether the attribute declared an enum — and a comment there claimed the
    two readings agreed "since both read the same declaration". They did not: this panel also gives a
    boolean two members, and the criteria snapshot deliberately withholds them, because a criteria
    condition on a boolean carries a real `bool` and its value picker is string-shaped. So the day an
    entity attribute is declared boolean, the panel offers two swatches and the picture draws a
    two-colour ramp instead. No such attribute exists today, which is exactly why it would have shipped.

    Asking the panel closes it without a second registry: whatever the panel *offered* is what the
    picture and the legend then draw, and `colour` is already the field that says which colouring
    applies — including for an ordinal, whose enum is a rank and so takes a ramp rather than a palette.

    Shared rows first, then the per-type rows in panel order. A shared attribute is one definition by
    construction, so that lookup is exact. A name several types declare *differently* takes the first
    row's definition — the panel has already told the reader the name is disputed, and one of the two
    meanings as a palette is truer than a gradient over strings, which is what returning nothing would
    have produced. Whichever it takes, the picture and the legend take the same one.

    An attribute this diagram does not offer takes no palette. A query string can name anything, and
    nothing drawn carries a value for it either way, so the colouring paints nothing whichever branch
    it lands in.
    """
    for shared in offers.shared:
        if shared.attribute.name == attribute:
            return shared.attribute.values if shared.attribute.colour == "palette" else ()
    for row in offers.types:
        for offered in row.attributes:
            if offered.name == attribute:
                return offered.values if offered.colour == "palette" else ()
    return ()


def palette_unset(offers: DiagramAttributeOffers, attribute: str) -> str | None:
    """The member *attribute* declares as unset, read off the same offers the panel showed.

    Beside `palette_members` rather than folded into it: both consumers of the palette need this and
    neither needs a second lookup, but the member list is what decides *whether* a palette applies at
    all, and a function answering two questions at once would be asked for one and given both.
    """
    for shared in offers.shared:
        if shared.attribute.name == attribute:
            return shared.attribute.unset_value
    for row in offers.types:
        for offered in row.attributes:
            if offered.name == attribute:
                return offered.unset_value
    return None


def _colour_kind(prop: dict[str, object], declared_type: str, values: tuple[str, ...]) -> ColourKind:
    if declares_ordinal(prop):
        return "ramp"
    if declared_type in NUMERIC_ATTRIBUTE_TYPES:
        return "ramp"
    if declared_type == "string" and str(prop.get("format", "")) == "date":
        return "ramp"
    if declared_type == "boolean" or values:
        return "palette"
    return "none"


def _declared_type(prop: dict[str, object]) -> str:
    return "ordinal" if declares_ordinal(prop) else str(prop.get("type", "string"))


def _unset_value(prop: dict[str, object]) -> str | None:
    """The declared `default`, where it is one of the declared values.

    A default naming something outside the value set is a schema defect and not this module's to
    report, so it is ignored here rather than coloured as a member that cannot occur.
    """
    default = prop.get("default")
    return str(default) if isinstance(default, str) and str(default) in _values(prop) else None


def _values(prop: dict[str, object]) -> tuple[str, ...]:
    raw = prop.get("enum")
    if isinstance(raw, (list, tuple)):
        return tuple(str(value) for value in raw)
    return ("false", "true") if str(prop.get("type", "")) == "boolean" else ()


def _carries(entity: EntityRecord, name: str) -> bool:
    """Whether this entity has a value for the attribute.

    Through `read_attribute_value`, which is the one place that knows where an attribute value lives —
    the decoded Properties table first, frontmatter `extra` as the fallback, reserved fields off the
    record itself. A check of its own here would be a second reader of that question, and it would get
    it wrong the same way a check of `extra` alone already did once in this release: this repository
    records attribute *values* in a Properties table in the document body and declares only their
    *types* in frontmatter.

    It also means the panel cannot offer an attribute the styling then fails to read, or omit one the
    styling would have found — the two ask the same function.
    """
    _value, present = read_attribute_value(entity, name, context="entity")
    return present


def _row_label(entity_type: str, specialization: str) -> str:
    return f"{entity_type}/{specialization}" if specialization else entity_type


def _definition(attribute: AttributeOffer) -> tuple[str, str, str]:
    """What has to match for two rows to be declaring the *same* attribute.

    Not the presence count, which is per row by construction, and not the name alone — that is the
    mistake this guards: a global colouring keyed on a name alone would read two types' unrelated
    `status` fields as one scale.
    """
    return (attribute.declared_type, attribute.colour, "\u0000".join(attribute.values))


def _shared(
    offers: Sequence[TypeOffer], entities: Sequence[EntityRecord]
) -> tuple[tuple[SharedAttributeOffer, ...], tuple[str, ...]]:
    """The attributes that read across this diagram, and the names that only look as though they do."""
    by_name: dict[str, list[tuple[str, AttributeOffer]]] = {}
    for offer in offers:
        label = _row_label(offer.entity_type, offer.specialization)
        for attribute in offer.attributes:
            by_name.setdefault(attribute.name, []).append((label, attribute))

    shared: list[SharedAttributeOffer] = []
    disputed: list[str] = []
    for name, declarations in by_name.items():
        rows = tuple(dict.fromkeys(label for label, _attribute in declarations))
        if len(rows) < 2:
            continue
        definitions = {_definition(attribute) for _label, attribute in declarations}
        if len(definitions) > 1:
            disputed.append(name)
            continue
        # Diagram-wide, over *entities*: the per-row counts cannot simply be added, because an entity
        # carrying two specializations appears under each of them and would be counted twice.
        carriers = {entity.artifact_id for entity in entities if _carries(entity, name)}
        shared.append(
            SharedAttributeOffer(
                attribute=replace(declarations[0][1], present_on=len(carriers)), on_rows=rows
            )
        )
    return tuple(shared), tuple(sorted(disputed))


def offers_for_diagram(
    entities: Sequence[EntityRecord],
    repo_root: Path,
    *,
    specialization_catalog: object,
    profile_registry: object,
) -> DiagramAttributeOffers:
    """The panel, for the entities one diagram draws.

    Grouped by ``(entity_type, specialization)`` because that pair decides the attribute set. Sorted so
    the answer is stable: a panel whose rows move between requests is a panel a reader cannot learn.
    """
    grouped: dict[tuple[str, str], list[EntityRecord]] = {}
    for entity in entities:
        slugs = entity.specializations or ("",)
        for slug in slugs:
            grouped.setdefault((entity.artifact_type, slug), []).append(entity)

    offers: list[TypeOffer] = []
    for (entity_type, slug), drawn in sorted(grouped.items()):
        schema, _conflicts = compute_effective_attribute_schema(
            repo_root,
            entity_type,
            [slug],
            specialization_catalog=specialization_catalog,  # type: ignore[arg-type]
            profile_registry=profile_registry,  # type: ignore[arg-type]
        )
        raw_properties = (schema or {}).get("properties")
        properties: dict[str, object] = raw_properties if isinstance(raw_properties, dict) else {}
        attributes = tuple(
            AttributeOffer(
                name=str(name),
                declared_type=_declared_type(prop),
                colour=_colour_kind(prop, _declared_type(prop), _values(prop)),
                values=_values(prop),
                present_on=sum(1 for entity in drawn if _carries(entity, str(name))),
                unset_value=_unset_value(prop),
            )
            for name, prop in sorted(properties.items())
            if isinstance(prop, dict)
        )
        if not attributes:
            continue
        offers.append(
            TypeOffer(entity_type=entity_type, specialization=slug, drawn=len(drawn), attributes=attributes)
        )
    shared, disputed = _shared(offers, entities)
    return DiagramAttributeOffers(
        shared=shared,
        types=tuple(offers),
        disputed=disputed,
        drawn=len({entity.artifact_id for entity in entities}),
    )
