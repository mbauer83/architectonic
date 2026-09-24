"""What an icon may be used for: the elements it states at upload, and nothing else.

An icon names the element kinds it is for as entries of *ontology*, *type* and optionally
*specialization* — `archimate-4 / technology-node / kubernetes-cluster`, `c4 / container`. An entry
with a specialization is narrower than one without it. No entries means any element.

The names are the owning ontology's own, so this module stores and compares them without knowing
what any of them mean. Whether one entity *is* of a type or carries a specialization is the
ontology's question, answered through its module; what is decided here is only how entries relate
to one another — whether one covers another, and whether replacing a set narrows it — which is pure
set reasoning over names.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass


class InvalidApplicabilityError(ValueError):
    """An `applies-to` entry is missing a name it needs, or names an unknown field."""


@dataclass(frozen=True, slots=True, order=True)
class ApplicabilityEntry:
    """One kind of element an icon is for."""

    ontology: str
    type: str
    specialization: str | None = None

    def covers(self, other: ApplicabilityEntry) -> bool:
        """Whether every element *other* describes is also described by this entry."""
        return (self.ontology, self.type) == (other.ontology, other.type) and (
            self.specialization is None or self.specialization == other.specialization
        )

    def as_mapping(self) -> dict[str, str]:
        base = {"ontology": self.ontology, "type": self.type}
        return base if self.specialization is None else {**base, "specialization": self.specialization}


@dataclass(frozen=True, slots=True)
class Applicability:
    """The set of element kinds an icon is for; empty means any element."""

    entries: frozenset[ApplicabilityEntry] = frozenset()

    @property
    def is_unrestricted(self) -> bool:
        return not self.entries

    def admits(self, element: ApplicabilityEntry) -> bool:
        """Whether an element of this ontology, type and specialization may show the icon.

        *element* describes one concrete element, so its specialization is the one it carries, or
        None for an element that carries none.
        """
        return self.is_unrestricted or any(entry.covers(element) for entry in self.entries)

    def covers(self, other: Applicability) -> bool:
        """Whether every element *other* admits, this admits too."""
        if self.is_unrestricted:
            return True
        return not other.is_unrestricted and all(self._covers_entry(entry) for entry in other.entries)

    def narrows(self, previous: Applicability) -> bool:
        """Whether replacing *previous* by this set would stop admitting an element it admitted."""
        return not self.covers(previous)

    def as_list(self) -> list[dict[str, str]]:
        return [entry.as_mapping() for entry in sorted(self.entries)]

    def _covers_entry(self, entry: ApplicabilityEntry) -> bool:
        return any(mine.covers(entry) for mine in self.entries)


_FIELDS = frozenset({"ontology", "type", "specialization"})


def applicability_from(raw: Iterable[Mapping[str, object]] | None) -> Applicability:
    """Read `applies-to` as stored or submitted, refusing an entry it cannot state exactly."""
    return Applicability(frozenset(_entry_from(item) for item in raw or ()))


def _entry_from(item: Mapping[str, object]) -> ApplicabilityEntry:
    unknown = set(item) - _FIELDS
    if unknown:
        raise InvalidApplicabilityError(f"applies-to entry has unknown fields: {sorted(unknown)}")
    ontology, type_name = _required_name(item, "ontology"), _required_name(item, "type")
    specialization = item.get("specialization")
    if specialization is not None and not (isinstance(specialization, str) and specialization.strip()):
        raise InvalidApplicabilityError("applies-to specialization must be a non-empty name when given")
    return ApplicabilityEntry(ontology, type_name, specialization.strip() if specialization else None)


def _required_name(item: Mapping[str, object], field: str) -> str:
    value = item.get(field)
    if not (isinstance(value, str) and value.strip()):
        raise InvalidApplicabilityError(f"applies-to entry needs a non-empty '{field}'")
    return value.strip()
