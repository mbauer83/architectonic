"""The contracts a diagram is arranged under: the picture an editor draws from, and a layout patch's answer.

The geometry is PlantUML's own picture of the diagram, read by the one reader of its structure, with
every shape and line named as a layout names it and carried with PlantUML's own drawing of it, so an
editor draws exactly what the composer places (`rendering/layout/diagram_geometry`).
"""

from __future__ import annotations

from typing import Literal

from src.infrastructure.rest.contracts.diagram_groupings import AuthoredGroupingResponse
from src.infrastructure.rest.contracts.diagram_layout import DiagramLayoutContract, DiagramLayoutPatchContract
from src.infrastructure.rest.contracts.wire_nulls import NullsOmitted


class ExtentContract(NullsOmitted):
    left: float
    top: float
    right: float
    bottom: float


class DrawingNodeContract(NullsOmitted):
    """A piece of PlantUML's own drawing — an outline, a glyph, a word, a line, a decoration — as a tree."""

    tag: str
    attributes: dict[str, str]
    text: str | None = None
    children: list[DrawingNodeContract]


class LineEndContract(NullsOmitted):
    """One end of a line: its decorations, and the frame they were drawn in."""

    marks: list[DrawingNodeContract]
    at: tuple[float, float]
    heading: tuple[float, float]
    #: How far short of the end the line itself stops: the run a hollow head's base sits back by.
    gap: float


class LineLabelContract(NullsOmitted):
    texts: list[DrawingNodeContract]
    centre: tuple[float, float]


class LineDrawingContract(NullsOmitted):
    """PlantUML's whole drawing of a line, and its parts for drawing it along a new course."""

    group: DrawingNodeContract
    line: DrawingNodeContract
    #: At the source end, then the target end.
    ends: tuple[LineEndContract, LineEndContract]
    label: LineLabelContract | None = None


class MeasuredWordContract(NullsOmitted):
    text: str
    x: float
    y: float
    width: float


class GeometryElementContract(NullsOmitted):
    alias: str
    #: The instance a layout places it by; null where it is no instance of the diagram's.
    key: str | None = None
    label: str
    extent: ExtentContract
    inside: str | None = None
    words: list[MeasuredWordContract]
    outside_label: ExtentContract | None = None
    drawing: DrawingNodeContract


class GeometryBoxContract(NullsOmitted):
    alias: str
    kind: Literal["domain", "type", "authored-grouping", "element"]
    #: Where a layout states it: an element holding its parts among the elements, any other box among boxes.
    section: Literal["elements", "boxes"]
    key: str | None = None
    label: str
    extent: ExtentContract
    inside: str | None = None
    words: list[MeasuredWordContract]
    title_band: ExtentContract | None = None
    drawing: DrawingNodeContract


class GeometryRelationContract(NullsOmitted):
    index: int
    #: The drawn-relation key a layout states it by.
    key: str | None = None
    source: str
    target: str
    decorated: tuple[bool, bool]
    course: list[tuple[float, float]]
    label: str
    label_size: tuple[float, float] | None = None
    drawing: LineDrawingContract


class SurroundPartContract(NullsOmitted):
    """A part PlantUML draws round the diagram — its title, its legend — and where it is drawn."""

    drawing: DrawingNodeContract
    extent: ExtentContract


class SurroundContract(NullsOmitted):
    """What PlantUML draws round the diagram, and what the diagram occupied when it was drawn: where the layout
    surround route carries each part from."""

    drawn: ExtentContract
    parts: list[SurroundPartContract]


class SurroundPlacementResponse(NullsOmitted):
    """How far each part drawn round the diagram moves, in the order asked, as ``[dx, dy]``."""

    moves: list[tuple[float, float]]


class DiagramLayoutGeometryResponse(NullsOmitted):
    """PlantUML's own picture of a diagram as an editor arranges it, and the layout the diagram states."""

    artifact_id: str
    name: str
    canvas: ExtentContract
    #: What PlantUML draws behind everything: the background.
    backdrop: list[DrawingNodeContract]
    #: What PlantUML draws round the diagram: its title and its legend.
    surround: SurroundContract
    elements: list[GeometryElementContract]
    boxes: list[GeometryBoxContract]
    relations: list[GeometryRelationContract]
    #: The stored layout, or null where PlantUML arranges the picture.
    layout: DiagramLayoutContract | None = None


class DiagramLayoutPatchResponse(NullsOmitted):
    """What a layout patch did: whether it wrote, what the write warned or refused, and the layout block
    the diagram holds after it — empty where it holds none."""

    artifact_id: str
    wrote: bool
    warnings: list[str]
    #: The verifier's errors, one message each; a write with any is not made.
    errors: list[str]
    layout: DiagramLayoutContract


class DiagramLayoutIntentsResponse(DiagramLayoutPatchResponse):
    """What applying layout intents did, and the patch they compiled to: each changed entry with what it
    becomes and what the stored layout held for it (``based_on``)."""

    patch: DiagramLayoutPatchContract
    #: The groupings the diagram holds after grouping intents; absent where none was stated.
    authored_groupings: list[AuthoredGroupingResponse] | None = None


class ShapeDrawingsResponse(NullsOmitted):
    """Each shape asked for, drawn by the composer at its new size, in the order asked."""

    drawings: list[DrawingNodeContract]

