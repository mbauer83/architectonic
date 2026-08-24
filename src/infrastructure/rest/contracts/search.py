"""Response contracts for the three search surfaces, which are three different searches.

The client treated two of them as one: ``ArtifactSearchHitSchema = SearchHitSchema``. They are not.
``/api/search`` serialises a whole record through ``state.search_hit_to_dict`` — domain, subdomain,
diagram type, connection endpoints, depending on what was found. ``/api/artifact-search`` projects six
fields for a picker, and can return assurance nodes, which the keyword search never does.
``/api/reference-search`` has no ``score`` at all: it filters rather than ranks.

Each hit is one closed model with the kind-specific fields nullable, rather than a four-arm ``oneOf``.
Every consumer renders a single list of mixed kinds, so narrowing per row would be work the union
creates and the reader does not want; ``record_type`` says which fields to expect, and the docstrings
say which kind fills which. The alternative — leaving them optional — is what let the client declare
``last_updated`` nowhere while the route sent it on every hit.
"""

from __future__ import annotations

from typing import Literal

from src.infrastructure.rest.contracts.wire_shape import Closed

#: The record kinds the keyword search can return. Connections are excluded upstream and serialised
#: defensively, so the arm exists; assurance nodes are *not* here — they come from the display search
#: and from the assurance surface's own search, at their own addresses. A scratchpad note is here and
#: deliberately absent from ``DisplayRecordType``: a note is findable, but a picker offers model
#: content, and offering a half-formed thought as something to reference would be a category error.
KeywordRecordType = Literal["entity", "connection", "diagram", "document", "scratchpad-note"]


class KeywordSearchHit(Closed):
    """One artifact matched by keyword, with the display fields its kind actually has.

    Mirrors ``state.search_hit_to_dict`` arm for arm. ``name`` and ``artifact_type`` are the *display*
    reading, not the stored one: a document's title arrives as ``name`` and its doc type as
    ``artifact_type``, because a mixed result list has one column for each and a reader does not care
    which record kind supplied it.

    The nullable fields are the kind-specific ones, and each is filled by exactly one kind — ``domain``
    and ``subdomain`` by an entity, ``diagram_type`` by a diagram, ``source``/``target`` by a
    connection. ``host_diagram_id`` and ``diagram_internal`` appear together, only for a construct a
    diagram owns, and they are how a display surface tells one from a model entity.

    A scratchpad note fills ``name`` with its title and ``artifact_type`` with the element type
    someone chose for it — empty while nothing has been chosen, which is a legitimate state here and
    nowhere else, because deciding late is the whole point of a scratchpad.
    """

    score: float
    record_type: KeywordRecordType
    artifact_id: str
    status: str
    path: str
    last_updated: str | None
    name: str
    artifact_type: str
    domain: str | None = None
    subdomain: str | None = None
    is_global: bool | None = None
    host_diagram_id: str | None = None
    diagram_internal: bool | None = None
    diagram_type: str | None = None
    source: str | None = None
    target: str | None = None
    #: A scratchpad note's container. A note has no file of its own — ``path`` is its scratchpad's
    #: and ``artifact_id`` is ``{scratchpad_id}#note/{note_id}`` — so these are what a client needs
    #: to say where a thought lives and to navigate to it.
    scratchpad_id: str | None = None
    scratchpad_name: str | None = None


class KeywordSearchResponse(Closed):
    """The hits, and the query as the repository parsed it — which is not always what was sent."""

    query: str
    hits: list[KeywordSearchHit]


#: The display search reaches the assurance store too, when it is unlocked. A locked or absent store
#: contributes nothing rather than failing the search: an architecture picker must keep working.
DisplayRecordType = Literal["entity", "connection", "diagram", "document", "assurance-node"]


class DisplaySearchHit(Closed):
    """One candidate for a picker: enough to label and identify, and nothing else.

    Six fields, deliberately — this feeds a dropdown, and the record's domain or endpoints would be
    noise in one. ``artifact_type`` is filled only for an assurance node, whose kind is the one thing a
    reader needs to tell a hazard from a loss in a mixed list; ``path`` is empty for one, because an
    assurance node has no file.
    """

    score: float
    record_type: DisplayRecordType
    artifact_id: str
    name: str
    status: str
    path: str
    artifact_type: str | None = None


class DisplaySearchResponse(Closed):
    """The candidates a picker offers, model content first.

    ``prioritize_global_hits`` demotes diagram-owned entities — a node drawn inside one diagram is a
    drawing detail, and a model entity is a commitment — and leaves every other kind in the order the
    search use case ranked it. It has never sorted by repository: an enterprise artifact and an
    engagement one rank against each other on score alone.
    """

    query: str
    hits: list[DisplaySearchHit]


class ReferenceSearchHit(Closed):
    """One artifact a document may cite.

    No ``score``: this filters rather than ranks, so every hit is equally a match and publishing a
    constant would invite sorting by it.

    ``domain`` is an entity's own or a diagram's inferred one, and null for a document — a document is
    filed by type rather than by domain. ``sections`` is a document's alone: a citation may target a
    section, and offering the list is what makes that possible without a second request.
    """

    artifact_id: str
    record_type: Literal["entity", "diagram", "document"]
    name: str
    status: str
    path: str
    domain: str | None = None
    artifact_type: str | None = None
    diagram_type: str | None = None
    doc_type: str | None = None
    sections: list[str] | None = None
    is_global: bool | None = None


class ReferenceSearchResponse(Closed):
    """The citable artifacts, and the query as sent — unparsed here, because this search does not
    reinterpret it."""

    query: str
    hits: list[ReferenceSearchHit]
