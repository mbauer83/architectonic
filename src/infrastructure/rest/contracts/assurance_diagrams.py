"""Response contracts for the assurance diagram surface: the catalogue, and a live rendering.

An assurance diagram is *derived*, never stored: it is one analysis's working set projected through one
diagram type and drawn on request. So there is no artifact behind ``diagram_id`` — it is the composite
``analysis::type``, opaque by intent, because a client that split it apart would be re-deriving a key it
was handed.

Derived from ``application/assurance_diagrams.assurance_surface_diagrams`` and the render handler.
``nodes`` and ``edges`` come back from the diagram type's own ``project_store_graph``, so their shape is
the module's — a bowtie's placement data is not shaped like a control structure's, and enumerating both
here would make the ontology's extensibility depend on this package.
"""

from __future__ import annotations

from typing import Any

from src.infrastructure.rest.contracts.wire_shape import Closed


class AssuranceDiagramCatalogEntry(Closed):
    """One (analysis, diagram type) pair the surface can draw, as a picker needs it.

    Every field is a string because every field is a label or an identity — the entry exists to be
    listed and opened, and it carries no content of its own.

    Filtered before the catalogue is built, not after: an entry names its analysis, so an above-ceiling
    analysis appearing here would disclose both that it exists and which method it uses.
    """

    diagram_id: str
    analysis_id: str
    analysis_name: str
    method: str
    diagram_type: str
    title: str
    type_label: str
    description: str


class AssuranceDiagramListResponse(Closed):
    """Every drawable diagram for the analyses this reader may see."""

    diagrams: list[AssuranceDiagramCatalogEntry]
    count: int
    visibility_limited: bool


class AssuranceNodeRepresentingEdge(Closed):
    """A drawn edge that stands for a node, and the node it stands for.

    A control action is rendered as its arrow rather than as a shape, so a click on that arrow has to
    select the action. Without this mapping the click does nothing, which reads as a broken diagram.
    """

    node_id: str
    source_id: str
    target_id: str


class AssuranceRenderedDiagramResponse(Closed):
    """One analysis projected through one diagram type, drawn as far as the type can draw it.

    ``puml`` and ``svg`` are both null for a type whose grid is built client-side from the nodes and
    edges below — the UCA matrix has no PUML body, and a type that declines to render is not an error.

    ``authored_node_ids`` is the working set's authorship split, narrowed to what was actually
    projected: a borrowed node has to be drawable as borrowed rather than passing for native.

    ``node_aliases`` maps each drawn alias back to its node, because the aliasing rule belongs to
    whatever wrote the PUML. A client that reconstructs it is a second implementation of a contract
    across a language boundary, and the two drifted once already — every shape in a bowtie was inert
    because one side prefixed the alias and the other did not.
    """

    diagram_id: str
    analysis_id: str
    analysis_name: str
    diagram_type: str
    puml: str | None
    svg: str | None
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    authored_node_ids: list[str]
    node_aliases: dict[str, str]
    node_representing_edges: list[AssuranceNodeRepresentingEdge]
    visibility_limited: bool
