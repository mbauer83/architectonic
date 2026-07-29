"""Normalising a diagram's node/edge payload — shared by every store-projected diagram type.

An assurance diagram is drawn from either of two sources, and both deliver the same two lists:
the live confidential store passes them directly, while a persisted diagram carries them in its
`diagram-entities` frontmatter, where either list may have been serialised as a JSON string.

Kept here, in the diagram-types package, rather than in one diagram type: bowtie, control structure
and the UCA matrix all need it, and a type reaching into a sibling type for it would couple two
notations that have nothing to do with each other.
"""

from __future__ import annotations

import json
from collections.abc import Mapping


def nodes_and_edges_from(
    diagram_entities: Mapping[str, object] | None,
    diagram_connections: list[dict[str, object]] | None = None,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Return `(nodes, edges)` from a diagram-entities payload, tolerating JSON-string lists.

    `diagram_connections` — the write pipeline's separate edge channel — is appended to whatever the
    payload itself carried, so a caller may use either or both.
    """
    nodes: list[dict[str, object]] = []
    edges: list[dict[str, object]] = []
    if diagram_entities:
        nodes = _dict_list(diagram_entities.get("nodes"))
        edges = _dict_list(diagram_entities.get("edges"))
    if diagram_connections:
        edges = edges + [e for e in diagram_connections if isinstance(e, dict)]
    return nodes, edges


def _dict_list(raw: object) -> list[dict[str, object]]:
    """Coerce a payload field to a list of dicts, whether it arrived parsed or as a JSON string."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return []
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]
