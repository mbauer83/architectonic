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
