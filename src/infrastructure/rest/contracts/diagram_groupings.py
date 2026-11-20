"""The contract a diagram's groupings are served under, and read back for a write."""

from __future__ import annotations

from pydantic import ConfigDict, Field

from src.infrastructure.rest.contracts.wire_nulls import NullsOmitted


class AuthoredGroupingResponse(NullsOmitted):
    """One labelled box a diagram draws that the model does not hold.

    Declared rather than served as a bare object: the write side takes these, so a client that can
    author a grouping must be able to read the ones already there — and a read typed as "an object"
    tells it nothing about what to send back. ``entity-ids`` keeps its frontmatter spelling on the
    wire, so what is read and what is written are the same word.

    A member may name an entity or a single *occurrence* of one, which is how an entity drawn twice
    sits in a different box each time. ``stereotype`` is an override the backend still honours; the
    look is otherwise derived from the members' domains.

    A box states either the members it lists or a ``rule`` that selects them — ``{domain: …}`` or
    ``{type: …}`` within its parent. ``id`` is the box's own stable identity, which a layout
    addresses it by: a client sends back the id it read, and a box sent without one is new.
    """

    #: Absent from what the write side authors on a box that only nests others, and present in
    #: every box this contract *serves*. Both halves matter: requiring the key made every diagram
    #: whose groupings nest fail its own read with a 500 — authored cleanly, verified clean,
    #: rendered — while letting the default reach the served document would declare the key
    #: optional to clients and ask each of them to handle an absence the server cannot produce.
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    #: Absent only on a diagram not yet brought to the current format by ``arch-repair upgrade``.
    id: str | None = None
    label: str
    #: Empty for a box that only nests others, or whose members a rule selects.
    entity_ids: list[str] = Field(default_factory=list, alias="entity-ids")
    #: One of ``domain`` or ``type`` to the name it selects. Absent on a box that lists its members.
    rule: dict[str, str] | None = None
    #: Boxes nest to any depth.
    groups: list["AuthoredGroupingResponse"] | None = None
    stereotype: str | None = None
