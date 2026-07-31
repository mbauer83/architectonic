"""Response contracts for the diagram surface.

The list-shaped reads answer an object with ``items`` rather than a bare array. A top-level array
has nowhere to put a total or a cursor, so adding either later would be a second breaking change —
and an array also cannot be a named component in the generated document, which is what the
frontend's type generation keys off.

Diagram *content* stays open where it belongs to a diagram-type module: a datatype classifier's
attributes, an activity step's shape, an entity's display block. Those are the module's vocabulary,
not this contract's, and closing them here would put the delivery layer in the business of every
diagram kind. Everything the surface itself decides is declared.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _ModuleShaped(BaseModel):
    """A payload whose fields belong to a diagram-type module rather than to this surface.

    Open on purpose, and named so the exception is auditable: the alternative is a delivery-layer
    model that has to change whenever a diagram kind adds a field, which would make the ontology's
    extensibility depend on this file.
    """

    model_config = ConfigDict(extra="allow")


class DiagramEntityItem(_ModuleShaped):
    """One entity as it is placed on a diagram: identity plus the kind's own placement data."""

    artifact_id: str
    name: str | None = None
    artifact_type: str | None = None


class DiagramEntityListResponse(_Closed):
    """Entities placed on one diagram."""

    items: list[DiagramEntityItem]


class DiagramConnectionItem(_ModuleShaped):
    """One connection as it is drawn on a diagram."""

    artifact_id: str | None = None
    source: str | None = None
    target: str | None = None
    conn_type: str | None = None


class DiagramConnectionListResponse(_Closed):
    """Connections drawn on one diagram."""

    items: list[DiagramConnectionItem]


class DiagramReference(_Closed):
    """A diagram that draws a given source/target pair."""

    artifact_id: str
    name: str


class DiagramReferenceListResponse(_Closed):
    """Which diagrams draw a given pair — what a rename or removal has to warn about."""

    items: list[DiagramReference]


class DiagramTypeMemberItem(_ModuleShaped):
    """One entity or connection type a diagram kind accepts, with its presentation data."""

    key: str | None = None
    label: str | None = None


class DiagramTypeEntityTypeListResponse(_Closed):
    items: list[DiagramTypeMemberItem]


class DiagramTypeConnectionTypeListResponse(_Closed):
    items: list[DiagramTypeMemberItem]


class DiagramSummary(_Closed):
    """One row of the diagram list."""

    artifact_id: str
    diagram_type: str
    name: str
    version: str
    status: str
    path: str
    is_global: bool
    group: str | None = None
    keywords: list[str] = []
    host_diagram_id: str | None = None
    last_updated: str | None = None
    tlp: str | None = None
    viewpoint: dict[str, Any] | None = None


class DiagramListResponse(_Closed):
    """A page of diagrams, with the count of the *filtered* population."""

    total: int
    items: list[DiagramSummary]


class DatatypeClassifierInfo(_Closed):
    """One classifier a datatype diagram declares, as the picker needs it.

    ``host_diagram_id`` is the diagram that owns it — a classifier is a diagram-local construct, so
    it has no file of its own and its full identifier is composite (see ``_diagram_entity_extraction``).
    Empty for a workspace-scoped type, which is the difference ``scope`` names.
    """

    type_id: str
    label: str
    kind: str
    scope: str
    host_diagram_id: str


class DatatypeTypeListResponse(_Closed):
    """A page of datatype classifier types, with the primitives they may be built from.

    ``generation`` is the index generation the page was read at: a picker holding a page and then
    resolving one of its entries needs to know the two came from the same model, and a stale page that
    silently resolves against a newer index is how a deleted classifier gets offered.

    ``next_cursor`` is null on the last page, following the house pagination convention — present and
    null rather than absent, so a client can tell "no more" from "this server does not paginate".
    """

    generation: int
    primitives: list[str]
    classifiers: list[DatatypeClassifierInfo]
    next_cursor: str | None


class DatatypeTypeUsage(_Closed):
    """One place a classifier type is referenced as an attribute's type."""

    diagram_id: str
    classifier_local_id: str
    attr_name: str


class DatatypeTypeUsageResponse(_Closed):
    """Everywhere one classifier type is used.

    ``type_id`` is echoed although the caller supplied it in the path: a client that fans out over
    several types and collects the answers needs each one to say which question it answers, and
    correlating by request order is the kind of thing that works until it does not.
    """

    type_id: str
    usages: list[DatatypeTypeUsage]
