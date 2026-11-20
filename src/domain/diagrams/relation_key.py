"""The identity of one relation as a diagram draws it, and the one reading and writing of its key.

A model connection is drawn once on most diagrams, and then the connection *is* the drawn relation.
An element drawn more than once changes that: the same connection may be drawn between two further
drawings, or once per copy of a duplicated cluster. So a statement about one drawn relation — its
label, its route — is keyed by the connection and, where either end is not the element's base
drawing, by the two instances at its ends:

* ``<connection id>`` — both ends are base instances;
* ``<connection id>@<source instance>><target instance>`` — otherwise.

The connection is spelled in its stable form and an entity instance likewise, so a renamed element
does not orphan a statement. A connection a diagram holds itself (a C4 relationship, an argument
edge) has no model id; it is keyed by its id within the diagram, and never carries instances.

The key replaced ``SRC_ALIAS:TGT_ALIAS``, which could not tell two relations between one pair apart.
`alias_pair_of` still recognises that spelling, for the two callers that must: the repository upgrade
that re-keys it, and the refusal that says to run it.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from src.domain.artifact_id import canonical_entity_key, stable_conn_id

_TYPE_SEPARATOR = "@@"
_INSTANCES_SEPARATOR = "@"
_ENDS_SEPARATOR = ">"

#: The retired key: two PlantUML aliases joined by one colon.
_ALIAS_PAIR = re.compile(r"(?P<source>[A-Za-z0-9_]+):(?P<target>[A-Za-z0-9_]+)")

UPGRADE_SENTENCE = "Run `arch-repair upgrade --commit` to bring the repository to the current format."


class MalformedRelationKey(ValueError):
    """A string offered as a drawn-relation key that is not one, with the reason in a sentence."""


@dataclass(frozen=True)
class DrawnRelationKey:
    """One drawn relation: the connection, and its two end instances where they are not both base."""

    connection: str
    ends: tuple[str, str] | None = None

    def __post_init__(self) -> None:
        for end in self.ends or ():
            if not end or _ENDS_SEPARATOR in end:
                raise MalformedRelationKey(
                    f"An instance id may not be empty or contain '{_ENDS_SEPARATOR}': {end!r}."
                )

    @property
    def text(self) -> str:
        if self.ends is None:
            return self.connection
        source, target = self.ends
        return f"{self.connection}{_INSTANCES_SEPARATOR}{source}{_ENDS_SEPARATOR}{target}"


def drawn_relation_key(
    connection_id: str, *, source: str, target: str, source_instance: str, target_instance: str
) -> DrawnRelationKey:
    """The key of *connection_id* drawn from *source_instance* to *target_instance*.

    *source* and *target* are the entities the connection joins; an end drawn at its entity's base
    instance is named by that entity's id, so both-base is decided here and nowhere else.
    """
    ends = (canonical_entity_key(source_instance), canonical_entity_key(target_instance))
    both_base = ends == (canonical_entity_key(source), canonical_entity_key(target))
    return DrawnRelationKey(stable_conn_id(connection_id), None if both_base else ends)


def read_relation_key(text: str) -> DrawnRelationKey:
    """The drawn relation *text* names, in canonical spelling. Refuses what is not a key."""
    written = text.strip()
    if not written:
        raise MalformedRelationKey("A drawn-relation key may not be empty.")
    if alias_pair_of(written) is not None:
        raise MalformedRelationKey(
            f"'{written}' is an alias pair, the retired key of a drawn relation; a relation is keyed "
            f"by its connection id. {UPGRADE_SENTENCE}"
        )
    if _ENDS_SEPARATOR not in written:
        return DrawnRelationKey(stable_conn_id(written))
    endpoints, typed, rest = written.partition(_TYPE_SEPARATOR)
    conn_type, qualified, instances = rest.partition(_INSTANCES_SEPARATOR)
    source, _, target = instances.partition(_ENDS_SEPARATOR)
    if not (typed and qualified and conn_type and source and target):
        raise MalformedRelationKey(
            f"'{written}' is not a drawn-relation key: expected '<connection id>' or "
            f"'<connection id>{_INSTANCES_SEPARATOR}<source instance>{_ENDS_SEPARATOR}<target instance>'."
        )
    return DrawnRelationKey(
        stable_conn_id(f"{endpoints}{_TYPE_SEPARATOR}{conn_type}"),
        (canonical_entity_key(source), canonical_entity_key(target)),
    )


def alias_pair_of(text: str) -> tuple[str, str] | None:
    """The two aliases of a retired ``SRC_ALIAS:TGT_ALIAS`` key, or None where *text* is not one."""
    match = _ALIAS_PAIR.fullmatch(text.strip())
    return (match.group("source"), match.group("target")) if match is not None else None


def labels_by_relation(statements: object) -> dict[str, str]:
    """A stored ``edge-labels`` mapping by canonical key, for a reader that must not refuse.

    A key that is not one is kept as written: it then matches no drawn relation, which is the
    verifier's to report and not a reason for a picture or a page to fail.
    """
    labelled: dict[str, str] = {}
    for key, label in (statements.items() if isinstance(statements, Mapping) else ()):
        try:
            labelled[read_relation_key(str(key)).text] = str(label)
        except MalformedRelationKey:
            labelled[str(key)] = str(label)
    return labelled
