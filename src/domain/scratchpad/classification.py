"""A note's decisions, read through the classification levels its meta-ontology declares.

The steps a note is refined by, when it may be lifted, and where its attributes attach are not this
feature's to fix: an ontology module declares its own levels — how many, what they are called, which
are required, which carry attributes — and everything here asks that declaration. Hard-coding
"domain, then type, then specialization" would couple the scratchpad to the shape of one
meta-ontology, and the first module declaring a different ladder would find it unusable.

**What a note stores, and why it is not keyed by level.** A level takes its values from one of three
places every ontology module has — its types' hierarchy, its types, its specializations
(`LevelSource`). A note keeps one value per *source*, so a level's value is found by where the level
says its values come from, never by what the level is called. That is what lets the stored document
keep the three keys it has always had under any declaration, with no upgrade step.

The cost is stated rather than hidden: a note holds one value above the type. A module declaring
several hierarchy-sourced levels has the first chosen directly and the rest reached by choosing a
type, which implies its whole hierarchy.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from src.domain.ontology_representation.classification_levels import (
    ClassificationLevel,
    LevelSource,
    attribute_level,
    is_liftable,
)
from src.domain.scratchpad.parts import Note, ScratchpadError


def _held(note: Note, source: LevelSource) -> str | None:
    """The one value a note keeps for levels taking their values from *source*."""
    match source:
        case "hierarchy":
            return note.domain
        case "type":
            return note.element_type
        case "specializations":
            return note.specialization


def _holding(note: Note, values: Mapping[LevelSource, str | None]) -> Note:
    """The note with the values given per source; a source not named keeps what it had."""
    return replace(
        note,
        domain=values.get("hierarchy", note.domain),
        element_type=values.get("type", note.element_type),
        specialization=values.get("specializations", note.specialization),
    )


#: Every source, re-opened.
_NOTHING: Mapping[LevelSource, str | None] = {"hierarchy": None, "type": None, "specializations": None}


@dataclass(frozen=True, slots=True)
class LevelOption:
    """One value a level offers, and the value of the level above it that allows it."""

    value: str
    #: Empty at the first level, and wherever the level above does not constrain this one.
    within: str = ""


@dataclass(frozen=True, slots=True)
class TypingOptions:
    """What a note may become at one level, in the order the ontology declares them.

    Offered rather than required: a note that stops at `undecided` has still done its job.
    """

    level: ClassificationLevel
    options: tuple[LevelOption, ...] = ()


def classification_of(note: Note) -> tuple[str | None, ...]:
    """Everything the note has decided about what kind of element it is."""
    return tuple(_held(note, source) for source in _NOTHING)


def is_classified(note: Note) -> bool:
    return any(classification_of(note))


def declassified(note: Note) -> Note:
    """The same note with every level re-opened."""
    return _holding(note, _NOTHING)


def _holds_directly(level: ClassificationLevel, levels: Sequence[ClassificationLevel]) -> bool:
    """Whether a note has a field of its own for this level — see the module docstring."""
    first_of_source = next(candidate for candidate in levels if candidate.source == level.source)
    return first_of_source.id == level.id


def value_at(
    note: Note, level: ClassificationLevel, levels: Sequence[ClassificationLevel]
) -> str | None:
    """The value the note has chosen at *level*, or `None`."""
    if not _holds_directly(level, levels):
        return None
    return _held(note, level.source)


def reached_levels(note: Note, levels: Sequence[ClassificationLevel]) -> tuple[str, ...]:
    """The ids of the levels the note has answered, by choosing or by implication.

    A type implies its hierarchy, so choosing one reaches every hierarchy-sourced level whether or
    not it was chosen first — which is also why a bound note, whose type comes from the entity,
    needs no separate answer above it.
    """
    return tuple(
        level.id for level in levels
        if value_at(note, level, levels)
        or (level.source == "hierarchy" and note.element_type)
    )


def unreached_required(
    note: Note, levels: Sequence[ClassificationLevel]
) -> tuple[ClassificationLevel, ...]:
    """The required levels the note has not reached, in declared order."""
    reached = reached_levels(note, levels)
    return tuple(level for level in levels if level.required and level.id not in reached)


def may_be_lifted(note: Note, levels: Sequence[ClassificationLevel]) -> bool:
    """Whether the note is complete enough to become an element.

    Every level the declaration requires has been reached — and a type has been chosen, whatever
    the declaration says, because a model element is created as a type and nothing else.
    """
    return bool(note.element_type) and is_liftable(levels, reached=reached_levels(note, levels))


def attribute_level_of(
    note: Note, levels: Sequence[ClassificationLevel]
) -> ClassificationLevel | None:
    """The level whose attribute schema applies to the note, or `None` while it is below every one."""
    return attribute_level(levels, reached=reached_levels(note, levels))


def refined(
    note: Note, *, level: ClassificationLevel, value: str, levels: Sequence[ClassificationLevel]
) -> Note:
    """The note narrowed to *value* at *level*, with every level declared after it re-opened.

    Narrowing runs one level at a time, and re-answering a coarser question re-opens the finer
    ones rather than leaving a choice the new answer may not contain. What was chosen above stays.
    """
    if level not in levels:
        raise ScratchpadError(
            f"{level.id!r} is not a classification level of this scratchpad's meta-ontology; "
            f"it declares {[declared.id for declared in levels]}"
        )
    if not _holds_directly(level, levels):
        raise ScratchpadError(
            f"level {level.id!r} is reached by choosing a type, which implies it; "
            "it is not chosen on its own"
        )
    finer = levels[list(levels).index(level) + 1:]
    values: dict[LevelSource, str | None] = {
        later.source: None for later in finer if later.source != level.source
    }
    if level.source == "type":
        # The type implies its hierarchy, so a value chosen there earlier is no longer the note's
        # to hold: two places to read it from is two answers waiting to disagree.
        values["hierarchy"] = None
    values[level.source] = value
    return _holding(replace(note, destination="element", document_type=None), values)
