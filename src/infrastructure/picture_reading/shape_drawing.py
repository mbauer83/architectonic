"""Shapes an editor resized, drawn anew at their new size: the request, and the one drawing of it.

A diagram's editor and a candidate's ask the same question of the same composer; only the address that
names the picture the shapes were read from differs. The drawing is a pure function of the request.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from src.infrastructure.rendering.layout.drawing_wire import reshaped


class DrawingNodeBody(BaseModel):
    """A piece of PlantUML's drawing as the geometry read handed it over, sent back to be drawn anew."""

    model_config = ConfigDict(extra="forbid")

    tag: str
    attributes: dict[str, str]
    text: str | None = None
    children: list[DrawingNodeBody] = []


class ExtentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    left: float
    top: float
    right: float
    bottom: float


class ShapeToDraw(BaseModel):
    """A shape an editor resized: PlantUML's drawing of it, where that was drawn, and where it is to go."""

    model_config = ConfigDict(extra="forbid")

    drawing: DrawingNodeBody
    box: bool
    drawn: ExtentBody
    to: ExtentBody


class DrawShapesBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shapes: list[ShapeToDraw]


def shape_drawings(body: DrawShapesBody) -> dict[str, object]:
    """Each shape of *body* drawn by the composer at its new size.

    Raises `Unreadable` where a drawing cannot be read back into a shape.
    """
    return {"drawings": [reshaped(shape.model_dump()) for shape in body.shapes]}
