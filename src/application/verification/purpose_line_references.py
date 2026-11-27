"""Whether a purpose line's references resolve: the one check, for a diagram's lines and a viewpoint's.

A reference resolves when the repository holds the element it names and that element's type is one the
ontology admits for the list holding it (`purpose_line_elements`, resolved by the ontology catalog). Two
artifacts state purpose lines — a diagram in its frontmatter, a viewpoint definition in `.arch-repo` — and
each reports a fault in its own vocabulary: the diagram verifier as E186/E187, the viewpoint persist path
as a definition issue. What counts as a fault, and how it reads, is decided here once.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.domain.ontology_representation.artifact_types import EntityRecord
from src.domain.ontology_representation.purpose_line_elements import PurposeLineTypes
from src.domain.purpose_lines import STAKEHOLDERS_KEY, PlacedReference, PurposeLines


class EntityLookup(Protocol):
    """The one question this check asks of a repository: which element an id names, if any."""

    def get_entity(self, artifact_id: str) -> EntityRecord | None: ...


@dataclass(frozen=True)
class Missing:
    """The reference names an element the repository does not hold."""


@dataclass(frozen=True)
class Unsuitable:
    """The reference names an element of a type its list does not admit."""

    found_type: str
    admitted: frozenset[str]


type ReferenceFault = Missing | Unsuitable


@dataclass(frozen=True)
class UnresolvedReference:
    """A reference that does not resolve, where it stands, and why."""

    placed: PlacedReference
    fault: ReferenceFault

    def describe(self) -> str:
        key, target = self.placed.list_key, self.placed.reference.artifact_id
        match self.fault:
            case Missing():
                return f"'{key}' refers to '{target}', which this repository does not hold"
            case Unsuitable(found_type, admitted):
                role = "a stakeholder" if key == STAKEHOLDERS_KEY else "the element stating a concern"
                return (
                    f"'{key}' refers to '{target}', a {found_type}, which cannot stand as {role}; "
                    f"admitted types: {', '.join(sorted(admitted)) or 'none — state it in words'}"
                )


@dataclass(frozen=True)
class PurposeLineResolution:
    """What a reference resolves against: the repository's elements, and the types each list admits."""

    entities: EntityLookup
    admitted: PurposeLineTypes

    def _admitted_for(self, list_key: str) -> frozenset[str]:
        return self.admitted.stakeholders if list_key == STAKEHOLDERS_KEY else self.admitted.concerns

    def _fault(self, placed: PlacedReference) -> ReferenceFault | None:
        entity = self.entities.get_entity(placed.reference.artifact_id)
        if entity is None:
            return Missing()
        admitted = self._admitted_for(placed.list_key)
        return None if entity.artifact_type in admitted else Unsuitable(entity.artifact_type, admitted)

    def unresolved(self, lines: PurposeLines) -> tuple[UnresolvedReference, ...]:
        """Every reference in *lines* that does not resolve, in the order stated. Prose is not looked at."""
        return tuple(
            UnresolvedReference(placed, fault)
            for placed in lines.references()
            if (fault := self._fault(placed)) is not None
        )
