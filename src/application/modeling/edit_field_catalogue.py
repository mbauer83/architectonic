"""Which fields an edit is made of, per artifact kind — one catalogue, several projections.

The same vocabulary was written down in three places that had no way to disagree out loud: the write
functions' signatures, the REST request bodies, and the MCP bulk decoder's `KNOWN_ITEM_FIELDS`. Each
is a legitimate surface with its own concerns — a signature is typed, a body validates, a decoder
refuses an unknown key — but *which fields exist* is one decision, and while it was spelled three
times the enterprise entity edit lost two of them without anything failing.

So the vocabulary lives here, at the application layer, and each surface projects it. It sits at this
layer rather than in the domain because it describes what the write path accepts, not what the
ontology declares — and because a domain module may import only the domain, so nothing outside it
could derive from a catalogue kept there.

**Two kinds of field, kept apart.** `ADDRESSING` names what identifies the subject: an entity is
reached by its id, a connection by its (source, target, type) triple. `CONTENT` names what an edit
may change. A surface needs both and needs to tell them apart — a connection edit takes
`source_entity` to find the connection, never to move it.

**The wire envelope is not here.** `op` and `_ref` belong to the MCP bulk decoder: they say which
operation an item is and what the caller calls it, which is a property of a batch request rather
than of an artifact. Keeping them out is what lets this catalogue be checked against the write
functions, which have never heard of either.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

#: The artifact kinds the write path edits. Closed, because a new kind is a decision about the
#: model rather than a key someone can add in passing.
ArtifactKind = Literal["entity", "connection"]

#: What identifies the subject of an edit.
ADDRESSING: Mapping[ArtifactKind, frozenset[str]] = {
    "entity": frozenset({"artifact_id"}),
    # A connection has no id of its own: the triple is its identity, and an edit that changed one of
    # these would be describing a different connection.
    "connection": frozenset({"source_entity", "target_entity", "connection_type"}),
}

#: What an edit may change. `group` is included for the entity because the engagement authority takes
#: it; that it is a relocation rather than a field on the record is stated where it is enforced.
CONTENT: Mapping[ArtifactKind, frozenset[str]] = {
    "entity": frozenset({
        "name", "summary", "properties", "attribute_types", "notes", "keywords",
        "specializations", "version", "status", "group",
    }),
    "connection": frozenset({
        "description", "src_multiplicity", "tgt_multiplicity", "specializations", "metadata",
    }),
}


def editable(kind: ArtifactKind) -> frozenset[str]:
    """Everything an edit of *kind* may name: what addresses the subject, and what it may change."""
    return ADDRESSING[kind] | CONTENT[kind]
