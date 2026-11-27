"""Which entity types a purpose line may refer to, as each ontology declares it.

A view's purpose line names who it is for and what it answers (`src.domain.purpose_lines`). An entry may
refer to an element of the model instead of describing one in words — and which elements make sense
there is a fact about the ontology's vocabulary, not about diagrams: in ArchiMate a stakeholder is an
element of its own, and a concern is stated by a motivation element. So the ontology says which, in the
shape `behavioral_elements` established — classes, plus types named outright — and the verifier asks.

An ontology that declares nothing admits no reference of that role. That is the honest reading of
silence: a reference the ontology has not said can stand for a stakeholder is refused rather than
guessed at, and prose is always available.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class ElementSelection:
    """Entity types picked by class, or named outright."""

    classes: frozenset[str] = frozenset()
    types: frozenset[str] = frozenset()

    def resolve(self, entity_classes: Mapping[str, Sequence[str]]) -> frozenset[str]:
        """The types of ``entity type name → its classes`` this selection picks."""
        return frozenset(
            name for name, classes in entity_classes.items()
            if name in self.types or not self.classes.isdisjoint(classes)
        )


@dataclass(frozen=True)
class PurposeLineTypes:
    """The entity types, resolved across every registered ontology, each role of a reference admits."""

    stakeholders: frozenset[str] = frozenset()
    concerns: frozenset[str] = frozenset()


@dataclass(frozen=True)
class PurposeLineElements:
    """One ontology's statement of which of its types stand for a stakeholder, and which state a concern."""

    stakeholders: ElementSelection = ElementSelection()
    concerns: ElementSelection = ElementSelection()

    def resolve(self, entity_classes: Mapping[str, Sequence[str]]) -> PurposeLineTypes:
        """Resolve against ``entity type name → its classes`` — the declaring ontology's own types only."""
        return PurposeLineTypes(
            stakeholders=self.stakeholders.resolve(entity_classes), concerns=self.concerns.resolve(entity_classes)
        )

    @classmethod
    def from_mapping(cls, data: Mapping[str, object]) -> PurposeLineElements:
        """Read the declaration from an ontology's parsed YAML. Absent keys mean empty."""
        return cls(
            stakeholders=ElementSelection(
                classes=_names(data.get("stakeholder_element_classes")),
                types=_names(data.get("stakeholder_element_types")),
            ),
            concerns=ElementSelection(
                classes=_names(data.get("concern_element_classes")),
                types=_names(data.get("concern_element_types")),
            ),
        )


def _names(raw: object) -> frozenset[str]:
    if not isinstance(raw, (list, tuple)):
        return frozenset()
    return frozenset(str(name) for name in raw if str(name))
