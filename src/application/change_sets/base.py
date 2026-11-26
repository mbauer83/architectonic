"""What an operation remembers about the content it was written against.

A change set is read long after it was written, against a model that has moved. To tell "this still
applies" from "someone changed this underneath me", each operation records what it saw: the value
itself where the value is small and has an identity, and only its revision where it is prose.

**A revision for prose is a stated trade.** Keeping the text would let a reader be shown three
versions side by side; keeping its revision detects that the text moved and cannot show what it
said. Detection is what an integration check needs, and a set that carried every summary it replaces
would be mostly other people's prose.

**The revision function is the product's one.** `content_revision` is what a diagram edit already
sends back as its base; a second digest here would be a second answer to "is this still what I
read?", and the two could never be compared.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, TypeAlias

from src.application.modeling.edit_field_values import comparable
from src.application.modeling.integration_detection import moved_since
from src.domain.content_revision import content_revision


@dataclass(frozen=True, slots=True)
class BaseValue:
    """The value that was there. `None` says nothing was: the key was absent, the field empty.

    Held in its recorded form — lists and mappings, never a tuple — because a base is read off a record
    (whose list fields are tuples) and answered and stored as plain data. Held as read, the answer to the
    write that recorded it was not JSON, while the same set read back from its file was: a recorded edit of
    `keywords` was written and then answered 500.
    """

    value: Any

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _recordable(self.value))


@dataclass(frozen=True, slots=True)
class BaseRevision:
    """The revision of what was there, for content too large or too shapeless to carry."""

    revision: str


def _recordable(value: Any) -> Any:
    """*value* as plain data: every sequence a list, every mapping a dict, recursively."""
    match value:
        case str() | bytes():
            return value
        case Mapping():
            return {key: _recordable(item) for key, item in value.items()}
        case list() | tuple():
            return [_recordable(item) for item in value]
        case _:
            return value


#: What an operation recorded about the content it replaces or removes.
Base: TypeAlias = BaseValue | BaseRevision


def prose_revision(text: object) -> str:
    """The revision of a prose field's text. Absent and empty are the same text.

    Normalised the way every other comparison of a field is, so a reading that arrives with a
    trailing newline is not reported as an edit.
    """
    return content_revision(str(comparable(text or "")).encode("utf-8"))


def record_revision(values: Mapping[str, Any]) -> str:
    """The revision of a whole artifact, as its field values. What a removal records.

    Canonical by construction: `comparable` orders a mapping's items and turns every sequence into
    one shape, so two readings of the same record cannot serialise differently.
    """
    canonical = json.dumps(comparable(values), ensure_ascii=False, default=str)
    return content_revision(canonical.encode("utf-8"))


def has_moved(base: Base, *, current: Any, proposed: Any) -> bool:
    """Whether *current* is neither what the operation was written against nor what it asks for.

    `moved_since` is the rule, shared with the rebase of a proposed change. This only puts the three
    values in the form the recorded base is in: compared as values, or all three as revisions.
    """
    match base:
        case BaseValue(value):
            return moved_since(base=value, current=current, proposed=proposed)
        case BaseRevision(revision):
            return moved_since(
                base=revision,
                current=prose_revision(current),
                proposed=prose_revision(proposed),
            )


def says_the_same(base: Base, one: Any, other: Any) -> bool:
    """Whether two readings of the content *base* describes are the same content.

    Compared in the form the base is in, so that prose absent and prose empty agree here exactly as
    they do when drift is decided — otherwise an edit could be neither applied nor drifted.
    """
    match base:
        case BaseValue():
            return bool(comparable(one) == comparable(other))
        case BaseRevision():
            return prose_revision(one) == prose_revision(other)
