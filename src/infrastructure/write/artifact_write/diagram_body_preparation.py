"""Bringing a stored PUML body up to date before it is written back.

Two normalisations that run over a body the author hands in or that is already stored, and neither is
about *references* — which is why they no longer live in `diagram_references`, whose subject is
inferring which entities and connections a body names. A body preparation that shares a module with
reference inference invites a caller to reach for one while meaning the other, and the file was
carrying two subjects under one name.

Both are keyed on what the ontology and the renderer state, not on a diagram's own content: the
suppressed relation labels are an ontology-global rule, and the generated declarations are the
renderer's own, restated rather than trusted because an author never wrote them.
"""

from __future__ import annotations

from pathlib import Path

from src.infrastructure.diagram_type_registry import find_renderer, suppressed_stereotype_tokens
from src.infrastructure.rendering.archimate_relation_rendering import strip_suppressed_relation_labels


def _restate_generated_declarations(puml_body: str, repo_root: Path, diagram_type: str) -> str:
    """Bring what the *renderer* states in a stored body up to date, and nothing else.

    A palette, a glyph, a relationship's line style and the label width bound are the product's
    statements rather than the author's, so a body that keeps a copy of them has to be refreshed
    whenever it is written — including on the edits that leave the picture alone, which is the only
    way a hand-laid-out diagram ever hears about a change.

    Deliberately not ``inject_includes``: that one *gives* a body a header when it has none, and
    expands an ``!include`` marker in place. An edit that carries no body must not convert a
    diagram's storage form, and `auto_include_stereotypes=False` is an author asking to keep the
    marker. A notation whose header states nothing generated does not implement the capability, and
    its bodies come through untouched.
    """
    from src.domain.ontology_representation.ontology_protocol import (  # noqa: PLC0415
        GeneratedHeaderRefreshingRenderer,
    )

    renderer = find_renderer(diagram_type)
    if renderer is None or not isinstance(renderer, GeneratedHeaderRefreshingRenderer):
        return puml_body
    return renderer.refresh_generated_header(puml_body, repo_root)



def _prepare_diagram_puml_body(puml_body: str, repo_root: Path, diagram_type: str) -> str:
    # Drop relation-stereotype edge labels the arrow style already conveys. This
    # is an ontology-global normalisation (keyed on ``show_stereotype`` across all
    # connection types), not a per-diagram-type concern, so it applies uniformly.
    puml_body = strip_suppressed_relation_labels(puml_body, suppressed_stereotype_tokens())
    renderer = find_renderer(diagram_type)
    return puml_body if renderer is None else renderer.inject_includes(puml_body, repo_root)
