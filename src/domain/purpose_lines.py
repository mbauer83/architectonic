"""Who a view is for and what it answers: the `stakeholders` and `concerns` lists, read and written here only.

One shape for every artifact that states a purpose. A viewpoint states one for every view built with it; a
diagram states its own, and a diagram applying a viewpoint inherits the viewpoint's lists where it states
none of its own. Each list holds entries of two kinds:

```yaml
stakeholders:
- Operations team                     # prose: a stakeholder nothing in the model names
- ref: STK@1712870400.aB3dEf          # a reference: an element of the model that stands for one
concerns:
- How does an order reach the warehouse?
- ref: GOL@1712870400.x9YzQw          # the element that states the concern
```

What a reference may name — which types stand for a stakeholder, which state a concern — is the
ontology's to declare (`PurposeLineElements`); whether a reference resolves is the verifier's to check.
This module decides only what the syntax is. A block that is not this does not become a value:
`read_purpose_lines` refuses it with a sentence, as `MalformedPurposeLine`.

A viewpoint written before references existed holds plain strings, which read as prose entries, so no
stored form changes.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from src.domain.artifact_id import canonical_entity_key

#: The frontmatter key naming who a view is for.
STAKEHOLDERS_KEY = "stakeholders"
#: The frontmatter key naming what a view answers.
CONCERNS_KEY = "concerns"
#: The one key of an entry that refers to an element instead of describing one.
REFERENCE_KEY = "ref"


class MalformedPurposeLine(ValueError):
    """A `stakeholders` or `concerns` value that cannot be read, saying what is wrong and where."""


@dataclass(frozen=True)
class Prose:
    """An entry stated in words: a stakeholder or a concern the model holds no element for."""

    text: str


@dataclass(frozen=True)
class Reference:
    """An entry naming an element of the model by its artifact id."""

    artifact_id: str

    @property
    def key(self) -> str:
        """The id this entry names, in the spelling ids are compared by."""
        return canonical_entity_key(self.artifact_id)


type PurposeEntry = Prose | Reference


@dataclass(frozen=True)
class PlacedReference:
    """A reference where it stands: the list holding it, and its position in that list's entries."""

    list_key: str
    position: int
    reference: Reference


@dataclass(frozen=True)
class PurposeLines:
    """A view's audience and its questions: the two lists, each in the order its author wrote it."""

    stakeholders: tuple[PurposeEntry, ...] = ()
    concerns: tuple[PurposeEntry, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not (self.stakeholders or self.concerns)

    def over(self, defaults: PurposeLines) -> PurposeLines:
        """These lines, each list that states nothing taking the one *defaults* states.

        How a diagram inherits from the viewpoint it applies: per list, so a diagram naming its own
        audience still answers the viewpoint's concerns until it states concerns of its own.
        """
        return PurposeLines(
            stakeholders=self.stakeholders or defaults.stakeholders,
            concerns=self.concerns or defaults.concerns,
        )

    def restated(
        self, *, stakeholders: Sequence[object] | None, concerns: Sequence[object] | None
    ) -> PurposeLines:
        """These lines with each list a caller gives read in its place; a list given as None is kept."""
        return PurposeLines(
            stakeholders=self.stakeholders if stakeholders is None else read_entries(stakeholders, STAKEHOLDERS_KEY),
            concerns=self.concerns if concerns is None else read_entries(concerns, CONCERNS_KEY),
        )

    def references(self) -> tuple[PlacedReference, ...]:
        """Every reference, with the list holding it and its position there."""
        return tuple(
            PlacedReference(key, position, entry)
            for key, entries in ((STAKEHOLDERS_KEY, self.stakeholders), (CONCERNS_KEY, self.concerns))
            for position, entry in enumerate(entries)
            if isinstance(entry, Reference)
        )

    def names(self, artifact_id: str) -> bool:
        """Whether either list refers to *artifact_id*, in whichever spelling either side uses."""
        wanted = canonical_entity_key(artifact_id)
        return any(placed.reference.key == wanted for placed in self.references())


def _read_entry(raw: object, *, where: str) -> PurposeEntry:
    match raw:
        case str() if raw.strip():
            return Prose(raw.strip())
        case str():
            raise MalformedPurposeLine(f"{where} is empty; state the entry in words or as {{ref: <id>}}")
        case Mapping() if set(raw) == {REFERENCE_KEY}:
            target = raw[REFERENCE_KEY]
            if isinstance(target, str) and target.strip():
                return Reference(target.strip())
            raise MalformedPurposeLine(f"{where}: '{REFERENCE_KEY}' must name an artifact id")
        case Mapping():
            raise MalformedPurposeLine(
                f"{where} is a mapping with keys {sorted(map(str, raw))}; a reference has the one key "
                f"'{REFERENCE_KEY}'"
            )
        case _:
            raise MalformedPurposeLine(f"{where} is a {type(raw).__name__}; an entry is prose or {{ref: <id>}}")


def read_entries(raw: object, key: str) -> tuple[PurposeEntry, ...]:
    """The entries of one list as stated under *key*. None, or no list at all, states none."""
    if raw is None:
        return ()
    if isinstance(raw, str) or not isinstance(raw, Sequence):
        raise MalformedPurposeLine(f"'{key}' must be a list of entries, not a {type(raw).__name__}")
    return tuple(_read_entry(item, where=f"'{key}' entry {index + 1}") for index, item in enumerate(raw))


def read_purpose_lines(frontmatter: Mapping[str, object]) -> PurposeLines:
    """The purpose lines *frontmatter* states — a diagram's, or one viewpoint definition's."""
    return PurposeLines(
        stakeholders=read_entries(frontmatter.get(STAKEHOLDERS_KEY), STAKEHOLDERS_KEY),
        concerns=read_entries(frontmatter.get(CONCERNS_KEY), CONCERNS_KEY),
    )


def entry_as_written(entry: PurposeEntry) -> str | dict[str, str]:
    match entry:
        case Prose(text):
            return text
        case Reference(artifact_id):
            return {REFERENCE_KEY: artifact_id}


def purpose_lines_as_written(lines: PurposeLines) -> dict[str, list[str | dict[str, str]]]:
    """The keys to store for *lines*: a list that states nothing is not written."""
    return {
        key: [entry_as_written(entry) for entry in entries]
        for key, entries in ((STAKEHOLDERS_KEY, lines.stakeholders), (CONCERNS_KEY, lines.concerns))
        if entries
    }
