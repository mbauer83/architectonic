"""The levels a meta-ontology classifies an element through, and what each one governs.

The chain already exists in the data: `entities.yaml` declares a `hierarchy` per entity type,
`specializations.yaml` declares specializations keyed by type, so **domain → entity type →
specialization** is expressible today and `hierarchy` being a list means arbitrary depth above the
type already is too.

What was missing is not the chain but its *characterisation*. A consumer walking it could not ask:
what is this level called, is it required, which level are relationships keyed on, which merely
narrows them, which carry attributes. Every one of those answers was hard-coded in whichever
consumer needed it — which is why the scratchpad's first refinement design came out ArchiMate-shaped
rather than meta-ontology-shaped.

One declaration answers five questions that were previously answered in five places:

============================================  ==========================================
question                                      answered by
============================================  ==========================================
which pickers refinement offers, in order     the level list
when a drawn link should be verified          both ends reached `keys_relationships`
whether a violation blocks or warns           `keys_relationships` → E126, blocks
                                              `narrows_relationships` → W128/W129, warns
which attribute schema applies                deepest level with `carries_attributes`
whether an element may be lifted yet          every `required` level reached
============================================  ==========================================

The third row is what makes this more than convenient. The **two-tier verification** — type-level
refusal against specialization-level narrowing — stops being a special case in the verifier and
becomes a consequence of the declaration. Two mechanisms found separately turn out to be one idea,
and the ontology is where it belongs.

`classification_levels` is **optional**. A module that omits it gets `DERIVED_DEFAULT_LEVELS`, which
is precisely today's behaviour — so `sysml_v2_min` and `assurance` need no edit at all.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol, runtime_checkable

#: Where a level's values come from. Each names data the module already declares, so a level
#: restates nothing — it characterises what is there.
LevelSource = Literal["hierarchy", "type", "specializations"]


class ClassificationLevelsError(ValueError):
    """A `classification_levels` block that cannot mean what it says."""


@dataclass(frozen=True, slots=True)
class ClassificationLevel:
    """One rung of the classification ladder."""

    id: str
    label: str
    source: LevelSource
    #: Whether an element must reach this level before it is complete. A lift preflight reads this;
    #: an unreached required level is why something is not liftable yet.
    required: bool = False
    #: Whether `permitted_relationships` are keyed at this level. Exactly one level may claim it —
    #: a relationship keyed at two levels has no single answer to "is this pair permitted".
    keys_relationships: bool = False
    #: Whether this level may *narrow* what the keying level permits, never widen it. A violation
    #: here warns (W128/W129) where one at the keying level refuses (E126).
    narrows_relationships: bool = False
    #: Whether an attribute schema attaches here. The deepest reached level with this wins, so a
    #: specialization's schema narrows its type's rather than replacing it.
    carries_attributes: bool = False


#: What a module gets by saying nothing: one level per `hierarchy` segment, then the entity type,
#: then specializations. This is the behaviour every consumer already hard-coded, written down.
DERIVED_DEFAULT_LEVELS: tuple[ClassificationLevel, ...] = (
    ClassificationLevel(
        id="domain", label="Domain", source="hierarchy", required=True,
    ),
    ClassificationLevel(
        id="entity_type", label="Entity type", source="type", required=True,
        keys_relationships=True, carries_attributes=True,
    ),
    ClassificationLevel(
        id="specialization", label="Specialization", source="specializations", required=False,
        narrows_relationships=True, carries_attributes=True,
    ),
)


def _level_from_mapping(raw: Mapping[str, Any], *, module: str) -> ClassificationLevel:
    identifier = str(raw.get("id") or "").strip()
    if not identifier:
        raise ClassificationLevelsError(f"{module}: a classification level has no id")
    source = str(raw.get("from") or "").strip()
    if source not in ("hierarchy", "type", "specializations"):
        raise ClassificationLevelsError(
            f"{module}: level {identifier!r} has from={source!r}; expected hierarchy, type or specializations"
        )
    return ClassificationLevel(
        id=identifier,
        label=str(raw.get("label") or identifier.replace("_", " ").capitalize()),
        source=source,  # type: ignore[arg-type]
        required=bool(raw.get("required", False)),
        keys_relationships=bool(raw.get("keys_relationships", False)),
        narrows_relationships=bool(raw.get("narrows_relationships", False)),
        carries_attributes=bool(raw.get("carries_attributes", False)),
    )


def classification_levels_from_config(
    config: Mapping[str, Any], *, module: str = "ontology"
) -> tuple[ClassificationLevel, ...]:
    """The module's declared levels, or the derived default when it declares none.

    Validated here rather than at first use, so a module that cannot mean what it says fails at
    startup with the module named — not later, inside whichever consumer happened to walk it first.
    """
    raw = config.get("classification_levels")
    if raw is None:
        return DERIVED_DEFAULT_LEVELS
    if not isinstance(raw, list) or not raw:
        raise ClassificationLevelsError(
            f"{module}: classification_levels must be a non-empty list, or absent for the default"
        )
    levels = tuple(
        _level_from_mapping(entry, module=module) for entry in raw if isinstance(entry, Mapping)
    )
    validate_classification_levels(levels, module=module)
    return levels


def validate_classification_levels(
    levels: Sequence[ClassificationLevel], *, module: str = "ontology"
) -> None:
    """The rules a level list must satisfy, checked once at startup."""
    identifiers = [level.id for level in levels]
    duplicates = sorted({name for name in identifiers if identifiers.count(name) > 1})
    if duplicates:
        raise ClassificationLevelsError(f"{module}: duplicate classification level id(s) {duplicates}")

    keying = [level.id for level in levels if level.keys_relationships]
    if len(keying) != 1:
        # Not merely "at most one": with none, nothing decides whether a pair is permitted, and the
        # E126-versus-W128 split — the whole reason this declaration exists — has no anchor.
        raise ClassificationLevelsError(
            f"{module}: exactly one classification level must set keys_relationships, found {keying or 'none'}"
        )

    keying_index = next(index for index, level in enumerate(levels) if level.keys_relationships)
    narrowing_above = [
        level.id for index, level in enumerate(levels)
        if level.narrows_relationships and index < keying_index
    ]
    if narrowing_above:
        # A level above the keying one cannot narrow it: it is coarser, so it would be deciding for
        # types it does not distinguish between.
        raise ClassificationLevelsError(
            f"{module}: {narrowing_above} narrow relationships but sit above the keying level"
        )

    if not any(level.carries_attributes for level in levels):
        raise ClassificationLevelsError(
            f"{module}: no classification level carries attributes, so no attribute schema can apply"
        )


@runtime_checkable
class DeclaresClassificationLevels(Protocol):
    """A module that characterises its own levels rather than taking the derived default.

    A protocol rather than a base class or an attribute lookup, because the declaration is genuinely
    optional: `sysml_v2_min` and `assurance` say nothing and are right not to — the default *is*
    their behaviour. Asking `isinstance` states that optionality in the type system, where a
    `getattr` fallback would state it nowhere.
    """

    @property
    def classification_levels(self) -> tuple[ClassificationLevel, ...]: ...


def classification_levels_for(module: object) -> tuple[ClassificationLevel, ...]:
    """The levels this ontology module classifies through — declared, or derived."""
    if isinstance(module, DeclaresClassificationLevels):
        return module.classification_levels
    return DERIVED_DEFAULT_LEVELS


def relationship_keying_level(levels: Sequence[ClassificationLevel]) -> ClassificationLevel:
    """The level a drawn link is verified at, once both its ends have reached it."""
    return next(level for level in levels if level.keys_relationships)


def attribute_level(levels: Sequence[ClassificationLevel], *, reached: Sequence[str]) -> ClassificationLevel | None:
    """The deepest reached level carrying an attribute schema, or None if none has been."""
    candidates = [level for level in levels if level.carries_attributes and level.id in reached]
    return candidates[-1] if candidates else None


def is_liftable(levels: Sequence[ClassificationLevel], *, reached: Sequence[str]) -> bool:
    """Whether every required level has been reached — the lift preflight's question."""
    return all(level.id in reached for level in levels if level.required)
