"""Which entity types denote something that *acts*, as each ontology declares it.

A behavioural element is one that does something which can be done well or badly: a component, a
service, a function, a process, a device. It is not a statement about any particular analysis — it is
a statement about the element's nature, which is why it is declared by the ontology that owns the
vocabulary and asked for by whoever needs it. Any analysis that asks how something *malfunctions*
needs this distinction: the question only parses for an element that has a function, where a goal is
met or missed rather than performed badly.

**Declared as lists, not as a flag per type.** Four short lists read as one statement of intent —
"these classes act, except these, plus these types, minus these" — where a boolean on each of forty
entity types is the same information scattered across a file, and an auditor has to re-collect the
set mentally to see what it says.

The two subtractive lists are not symmetry for its own sake. ArchiMate's class taxonomy is coarser
than the question in one specific place: a capability, a course of action and a value stream all
declare `behavior-element` alongside `strategy-behavior-element`, so a plain allowlist of
`behavior-element` admits them — and a capability does not malfunction, it is held or missing.
`excluded_classes` is what closes that. `excluded_types` closes the same gap one level down, for a
class that is ever mostly behavioural with a single exception inside it.

**Precedence: an explicit exclusion is the last word.** `excluded_types` beats `types`, because
between two explicit statements the one that removes a claim is the safe one to honour — a type
wrongly omitted produces a missing finding, while one wrongly admitted produces a question with no
answer, which is what taught readers to ignore the list in the first place.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class BehavioralElementDeclaration:
    """One ontology's statement of which of its entity types act.

    Every field defaults to empty, and an empty declaration resolves to no behavioural types. That
    is the honest answer for an ontology that has not said: silence is not a claim that everything
    acts, nor that nothing does — it is the absence of the declaration, and a caller that needs it
    gets nothing rather than a guess.
    """

    classes: frozenset[str] = frozenset()
    excluded_classes: frozenset[str] = frozenset()
    types: frozenset[str] = frozenset()
    excluded_types: frozenset[str] = frozenset()

    @property
    def is_empty(self) -> bool:
        return not (self.classes or self.types)

    @classmethod
    def from_mapping(cls, data: Mapping[str, object]) -> BehavioralElementDeclaration:
        """Read the declaration from an ontology's parsed YAML. Absent keys mean empty."""
        return cls(
            classes=_names(data.get("behavioral_element_classes")),
            excluded_classes=_names(data.get("non_behavioral_element_classes")),
            types=_names(data.get("behavioral_element_types")),
            excluded_types=_names(data.get("non_behavioral_element_types")),
        )


def _names(raw: object) -> frozenset[str]:
    if not isinstance(raw, (list, tuple)):
        return frozenset()
    return frozenset(str(name) for name in raw if str(name))


def resolve_behavioral_types(
    entity_classes: Mapping[str, Sequence[str]],
    declaration: BehavioralElementDeclaration,
) -> frozenset[str]:
    """Resolve a declaration against ``entity type name → its classes``.

    A type acts when it carries one of the declared classes and none of the excluded ones, or when it
    is named outright — and never when it is excluded outright. See the module docstring for why the
    exclusion wins.
    """
    if declaration.is_empty:
        return frozenset()
    resolved = {
        type_name for type_name, classes in entity_classes.items()
        if _acts_by_class(frozenset(str(c) for c in classes), declaration)
    }
    resolved |= {name for name in declaration.types if name in entity_classes}
    return frozenset(resolved - declaration.excluded_types)


def _acts_by_class(classes: frozenset[str], declaration: BehavioralElementDeclaration) -> bool:
    if classes & declaration.excluded_classes:
        return False
    return bool(classes & declaration.classes)
