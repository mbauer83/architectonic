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

from pydantic import BaseModel, ConfigDict


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


#: The record kinds the keyword search can return. Connections are excluded upstream and serialised
#: defensively, so the arm exists; assurance nodes are *not* here — they come from the display search
#: and from the assurance surface's own search, at their own addresses.
KeywordRecordType = Literal["entity", "connection", "diagram", "document"]


class KeywordSearchHit(_Closed):
    """One artifact matched by keyword, with the display fields its kind actually has.

    Mirrors ``state.search_hit_to_dict`` arm for arm. ``name`` and ``artifact_type`` are the *display*
    reading, not the stored one: a document's title arrives as ``name`` and its doc type as
    ``artifact_type``, because a mixed result list has one column for each and a reader does not care
    which record kind supplied it.

    The nullable fields are the kind-specific ones, and each is filled by exactly one kind — ``domain``
    and ``subdomain`` by an entity, ``diagram_type`` by a diagram, ``source``/``target`` by a
    connection. ``host_diagram_id`` and ``diagram_internal`` appear together, only for a construct a
    diagram owns, and they are how a display surface tells one from a model entity.
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


class KeywordSearchResponse(_Closed):
    """The hits, and the query as the repository parsed it — which is not always what was sent."""

    query: str
    hits: list[KeywordSearchHit]


#: The display search reaches the assurance store too, when it is unlocked. A locked or absent store
#: contributes nothing rather than failing the search: an architecture picker must keep working.
DisplayRecordType = Literal["entity", "connection", "diagram", "document", "assurance-node"]


class DisplaySearchHit(_Closed):
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


class DisplaySearchResponse(_Closed):
    """The candidates, architecture first: ``prioritize_global_hits`` puts enterprise artifacts above
    engagement ones, so a picker offers the shared vocabulary before a local restatement of it."""

    query: str
    hits: list[DisplaySearchHit]


class ReferenceSearchHit(_Closed):
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


class ReferenceSearchResponse(_Closed):
    """The citable artifacts, and the query as sent — unparsed here, because this search does not
    reinterpret it."""

    query: str
    hits: list[ReferenceSearchHit]
