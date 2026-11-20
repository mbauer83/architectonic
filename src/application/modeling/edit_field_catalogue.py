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

**Three kinds of field, kept apart.** `ADDRESSING` names what identifies the subject: an entity is
reached by its id, a connection by its (source, target, type) triple. `CONTENT` names what an edit
may change. `MECHANICS` names what tells the *applier* how to behave — whether to rebuild a layout,
whether to replace bindings rather than merge them, which committed repository to resolve candidates
against. A surface needs all three and needs to tell them apart: a connection edit takes
`source_entity` to find the connection and never to move it, and a proposal records what to change
without dictating how a future replay should apply it.

**How a field is addressed is a fact about the field.** `KEYED` names the mappings that are patched
key by key, `PROSE` the text that is replaced whole, and what is left is a value replaced whole and
compared as a value. The write path has always behaved this way; it is stated here because a change
set records one edit per addressable thing and has to know what the things are.

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
ArtifactKind = Literal["entity", "connection", "document", "diagram"]

#: The kinds a global artifact reference can stand for, and so the kinds a change can be proposed
#: against. A connection has no GAR, so a connection edit has nothing to be proposed about.
PROPOSABLE: tuple[ArtifactKind, ...] = ("entity", "document", "diagram")

#: What identifies the subject of an edit.
ADDRESSING: Mapping[ArtifactKind, frozenset[str]] = {
    "entity": frozenset({"artifact_id"}),
    # A connection has no id of its own: the triple is its identity, and an edit that changed one of
    # these would be describing a different connection.
    "connection": frozenset({"source_entity", "target_entity", "connection_type"}),
    "document": frozenset({"artifact_id"}),
    "diagram": frozenset({"artifact_id"}),
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
    "document": frozenset({
        "title", "body", "keywords", "extra_frontmatter", "status", "version", "last_updated",
        "group",
    }),
    "diagram": frozenset({
        "puml", "name", "keywords", "diagram_entities", "diagram_connections", "entity_ids_used",
        "connection_ids_used", "view_derivations", "bindings", "version", "status", "tlp",
        "viewpoint", "edge_labels", "group", "authored_groupings", "manual_layout", "layout",
    }),
}

#: The kinds a change set's operations address. Not `PROPOSABLE`, and the difference is the point: a
#: proposal is addressed to a global artifact reference, which a connection does not have, while a
#: change set is addressed to a repository, where a connection is reached by its triple as every
#: connection write reaches it. Documents and diagrams are absent because a set has no operation for
#: them yet, which is a decision about scope and not about what could be addressed.
IN_A_CHANGE_SET: tuple[ArtifactKind, ...] = ("entity", "connection")

#: The fields whose value is a mapping the write path PATCHES key by key: a key that is sent is set,
#: a key mapped to null is removed, and every other key is kept. Stated here because it decides what
#: one edit *is* — a change to one attribute of `properties` and a change to another are two edits
#: that cannot collide, where two changes to `name` are one field written twice.
KEYED: Mapping[ArtifactKind, frozenset[str]] = {
    "entity": frozenset({"properties", "attribute_types"}),
    "connection": frozenset({"metadata"}),
    # `extra_frontmatter` is merged, but a null does not remove a key, so it is not patched in the
    # sense above and is not claimed here.
    "document": frozenset(),
    "diagram": frozenset(),
}

#: The fields that hold prose: free text an edit replaces whole, because nothing inside it has a
#: name to address. What is recorded about the text an edit replaces is its revision rather than the
#: text — enough to know it moved, not enough to show what it said.
PROSE: Mapping[ArtifactKind, frozenset[str]] = {
    "entity": frozenset({"summary", "notes"}),
    "connection": frozenset({"description"}),
    "document": frozenset({"body"}),
    "diagram": frozenset({"puml"}),
}

#: What a *create* states beyond what an edit may change: the facts that are fixed once the artifact
#: exists. An entity's type is one. A connection's `version` and `status` are the other two — its
#: create takes them and its edit does not. Given for the kinds in `IN_A_CHANGE_SET`; a document's
#: create is still spelled by the bulk decoder alone.
CREATION: Mapping[ArtifactKind, frozenset[str]] = {
    "entity": frozenset({"artifact_type"}),
    "connection": frozenset({"version", "status"}),
}

#: What tells the applier how to behave rather than what the artifact should say. Never part of a
#: proposal: a proposal records the change, and how a replay applies it is the replay's decision.
MECHANICS: Mapping[ArtifactKind, frozenset[str]] = {
    "entity": frozenset(),
    "connection": frozenset(),
    # `part` makes a change to the body in one place of the stored file — a section, a text, rows of
    # a table — and leaves the rest of it byte for byte. It is how `body` is changed, not a field
    # beside it: a proposal has no stored file to change in part, and records the body whole.
    "document": frozenset({"part"}),
    "diagram": frozenset({"replace_bindings", "rebuild_layout", "committed_repo"}),
}


def editable(kind: ArtifactKind) -> frozenset[str]:
    """Everything an edit of *kind* may name: what addresses the subject, and what it may change."""
    return ADDRESSING[kind] | CONTENT[kind]


def atomic(kind: ArtifactKind) -> frozenset[str]:
    """The fields an edit replaces whole and compares by value: neither keyed nor prose."""
    return CONTENT[kind] - KEYED[kind] - PROSE[kind]


def creatable(kind: ArtifactKind) -> frozenset[str]:
    """Everything a create of *kind* may state about what it creates, its address aside."""
    return CONTENT[kind] | CREATION[kind]


def accepted(kind: ArtifactKind) -> frozenset[str]:
    """Everything the write function for *kind* takes, mechanics included."""
    return editable(kind) | MECHANICS[kind]
