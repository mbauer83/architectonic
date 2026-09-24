"""What an icon may be used for: the element types and specializations it names, and nothing else.

An icon names them in the vocabulary viewpoint style rules already use for `applies_to` —
`technology-node`, `kubernetes-cluster` — and matches an element the same way, by its type and every
specialization applied to it (`type_and_specializations`). Naming a specialization is narrower than
naming its type by construction: only the elements that carry it match. No names means any element.

Whether changing the names would take an icon away from an element that shows it is answered by
asking each such element, not by comparing the two sets: the names alone do not say which type a
specialization belongs to.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


class InvalidApplicabilityError(ValueError):
    """An `applies-to` entry is not a type or specialization name."""


@dataclass(frozen=True, slots=True)
class Applicability:
    names: frozenset[str] = frozenset()

    @property
    def is_unrestricted(self) -> bool:
        return not self.names

    def admits(self, element: frozenset[str]) -> bool:
        """Whether an element with these type and specialization names may show the icon."""
        return self.is_unrestricted or not self.names.isdisjoint(element)

    def as_list(self) -> list[str]:
        return sorted(self.names)


def applicability_from(raw: Iterable[object] | None) -> Applicability:
    """Read `applies-to` as stored or submitted, refusing an entry that is not a name."""
    return Applicability(frozenset(_name_from(item) for item in raw or ()))


def _name_from(item: object) -> str:
    if not (isinstance(item, str) and item.strip()):
        raise InvalidApplicabilityError(f"applies-to entries are type or specialization names, not {item!r}")
    return item.strip()
