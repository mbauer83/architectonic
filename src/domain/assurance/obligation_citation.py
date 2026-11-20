"""Which rule an obligation comes from — the one stored form, and the forms it replaced.

An obligation is a duty under some rule, and it says which in two attributes: `source`, the
regulation, standard, framework or contract ("EU AI Act", "ISO 26262"), and `provision`, the
article, clause or control in it ("Art. 12", "6-8"). Those are the words the people who own such
duties use.

Three spellings existed before this one, and no code read any of them: the wizard wrote `scheme` and
`code`, the ontology text asked for a single `cites` of the form `scheme:code`, and neither was
checked against anything. Every reader and writer of the citation takes the names from here, so the
next spelling cannot arrive unannounced; the superseded names are kept only so a store written
before can be recognised and rewritten.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

SOURCE = "source"
PROVISION = "provision"

#: What the form asks for. Stated here because the guidance, the skills and the form must say the
#: same thing, and a label written three times is three labels.
SOURCE_LABEL = "Regulation, standard or contract"
PROVISION_LABEL = "Article, clause or control"

#: The wizard's former pair, each renamed one for one.
SUPERSEDED_PAIR: Mapping[str, str] = {"scheme": SOURCE, "code": PROVISION}
#: The ontology's former single attribute, `source:provision`.
SUPERSEDED_COMBINED = "cites"
_COMBINED_SEPARATOR = ":"

SUPERSEDED_ATTRIBUTES: tuple[str, ...] = (*SUPERSEDED_PAIR, SUPERSEDED_COMBINED)

#: Source key → the provisions a reference vocabulary lists for it. Keyed by `source_key`, so
#: "ISO 26262" finds the vocabulary filed as `ISO26262`.
ReferenceProvisions = Mapping[str, frozenset[str]]


@dataclass(frozen=True)
class ObligationCitation:
    """The citation as stored. Either part is empty when the obligation does not state it."""

    source: str
    provision: str


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def citation_of(attributes: Mapping[str, object]) -> ObligationCitation:
    """The citation an obligation's attributes state, in the current form only."""
    return ObligationCitation(source=_text(attributes.get(SOURCE)), provision=_text(attributes.get(PROVISION)))


def superseded_attributes_in(attributes: Mapping[str, object]) -> tuple[str, ...]:
    """The former citation attributes still present, in a stable order."""
    return tuple(name for name in SUPERSEDED_ATTRIBUTES if name in attributes)


def source_key(source: str) -> str:
    """A source as it is compared: letters and digits only, case folded.

    A standard is written "ISO 26262", "ISO26262" and "iso-26262" by people who all mean the same
    document, and a comparison that tells them apart checks nothing for most of them.
    """
    return "".join(character for character in source.casefold() if character.isalnum())


@dataclass(frozen=True)
class CitationRewrite:
    """What bringing one obligation's attributes to the current form does."""

    attributes: dict[str, object]
    """The attributes afterwards. Equal to the input when nothing could be moved."""

    moved: tuple[tuple[str, str], ...]
    """(former attribute, current attribute) for every value that was moved, in order."""

    left_in_place: tuple[tuple[str, str], ...]
    """(former attribute, why) for every former attribute that could not be moved."""

    @property
    def changes_something(self) -> bool:
        return bool(self.moved)


def _split_combined(value: object) -> tuple[str, str] | None:
    """`source:provision`, split at the first separator — a provision may itself hold one."""
    source, separator, provision = _text(value).partition(_COMBINED_SEPARATOR)
    parts = (source.strip(), provision.strip())
    return parts if separator and all(parts) else None


def _conflict(attributes: Mapping[str, object], target: str, value: str) -> bool:
    """Whether *target* already states something else. An empty target states nothing."""
    held = _text(attributes.get(target))
    return bool(held) and held != value


def rewrite_superseded(attributes: Mapping[str, object]) -> CitationRewrite:
    """Move every former citation attribute to `source` and `provision`.

    A former attribute is removed only when all of what it said has arrived. Where the current
    attribute already says something different the former one stays, because which of two
    disagreeing values is right is not something a rename can know; and a `cites` that is not
    `source:provision` stays because there is no reading of it to move. Applying the result again
    changes nothing.
    """
    rewritten = dict(attributes)
    moved: list[tuple[str, str]] = []
    left: list[tuple[str, str]] = []

    def move(former: str, parts: Mapping[str, str]) -> None:
        clashing = [target for target, value in parts.items() if _conflict(rewritten, target, value)]
        if clashing:
            left.append((former, f"`{'`, `'.join(clashing)}` already states something else"))
            return
        rewritten.update(parts)
        del rewritten[former]
        moved.extend((former, target) for target in parts)

    for former, target in SUPERSEDED_PAIR.items():
        if former not in rewritten:
            continue
        value = _text(rewritten[former])
        if not value:
            left.append((former, "it holds no text"))
            continue
        move(former, {target: value})

    if SUPERSEDED_COMBINED in rewritten:
        split = _split_combined(rewritten[SUPERSEDED_COMBINED])
        if split is None:
            left.append((SUPERSEDED_COMBINED, f"it is not of the form source{_COMBINED_SEPARATOR}provision"))
        else:
            move(SUPERSEDED_COMBINED, {SOURCE: split[0], PROVISION: split[1]})

    return CitationRewrite(attributes=rewritten, moved=tuple(moved), left_in_place=tuple(left))
