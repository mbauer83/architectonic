"""Dispatch optional diagram-owned native SVG rendering."""

from __future__ import annotations

from src.domain.ontology_representation.ontology_protocol import NativeSvgDiagramRenderer
from src.infrastructure.diagram_type_registry import find_diagram_type


def render_native_svg(puml_body: str, diagram_type: str | None) -> str | None:
    if diagram_type is None:
        return None
    diagram_type_module = find_diagram_type(diagram_type)
    if diagram_type_module is None:
        return None
    renderer = diagram_type_module.renderer
    return renderer.render_svg(puml_body) if isinstance(renderer, NativeSvgDiagramRenderer) else None
