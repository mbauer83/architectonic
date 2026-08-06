"""What a diagram says about a connection it draws, as distinct from what the model says.

The model owns a connection's endpoints: A realizes B, wherever either is drawn. A diagram owns
*which drawing* the arrow attaches to, which only exists on the picture. An entity drawn twice has
two aliases, and without a way to say which one an arrow means, every arrow lands on the first — so
a second occurrence can only ever be an unconnected copy, which is what made the feature useless.

`diagram-connections` is that overlay. An entry names a connection and may carry:

* `label` and friends — how the arrow reads (owned by the renderer's label logic).
* `source-occurrence` / `target-occurrence` — an occurrence id from `diagram-entities`, saying which
  drawing of that endpoint this arrow attaches to. Absent means the base drawing, so every existing
  diagram routes exactly as it did.

Both the label lookup and the routing lookup match a connection the same way: by stable id, so a
renamed endpoint slug does not silently orphan the overlay. That match is declared once, here.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from src.application.artifacts.parsing import normalize_puml_alias
from src.domain.artifact_id import stable_conn_id
from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord

#: Resolves a connection to the arrows it draws — one alias pair each. Empty when neither endpoint
#: is drawn. Usually one pair; more when a duplicated cluster draws the same relation in each copy.
EndpointRouter = Callable[[ConnectionRecord], list[tuple[str, str]]]

SOURCE_OCCURRENCE_KEY = "source-occurrence"
TARGET_OCCURRENCE_KEY = "target-occurrence"


def connection_overlay(
    artifact_id: str,
    diagram_connections: Sequence[Mapping[str, object]] | None,
) -> Mapping[str, object] | None:
    """The diagram's first entry for *artifact_id*, matched by stable id.

    First, not only: a connection drawn in two places has an entry per drawing. The label opt-ins
    are a property of the relation rather than of one arrow, so they are read from whichever entry
    comes first; the routing keys are read per entry by `connection_overlays`.
    """
    entries = connection_overlays(artifact_id, diagram_connections)
    return entries[0] if entries else None


def connection_overlays(
    artifact_id: str,
    diagram_connections: Sequence[Mapping[str, object]] | None,
) -> list[Mapping[str, object]]:
    """Every entry for *artifact_id* — one per arrow the diagram draws for it."""
    return [
        item
        for item in diagram_connections or []
        if isinstance(item, Mapping)
        and stable_conn_id(str(item.get("artifact_id") or item.get("connection_id") or "").strip())
        == stable_conn_id(artifact_id)
    ]


def occurrence_alias_by_id(render_entities: Sequence[EntityRecord]) -> dict[str, str]:
    """Map each occurrence id to the alias its own drawing carries.

    Occurrences are the records `occurrence_entities` adds: they keep the backing entity's
    `artifact_id` and carry the occurrence id in `host_diagram_id`, which is why they cannot be found
    through the entity-keyed alias map and need this one.
    """
    aliases: dict[str, str] = {}
    for entity in render_entities:
        occurrence_id = str(entity.host_diagram_id or "").strip()
        if not occurrence_id:
            continue
        alias = normalize_puml_alias(entity.display_alias)
        if alias:
            aliases[occurrence_id] = alias
    return aliases


def endpoint_router(
    diagram_connections: Sequence[Mapping[str, object]] | None,
    *,
    alias_by_id: Mapping[str, str],
    alias_by_occurrence: Mapping[str, str],
) -> EndpointRouter:
    """Resolve the arrows a connection draws, honouring the occurrences the diagram named.

    One entry means one arrow, which is every diagram that predates this. Several entries mean the
    relation is drawn once per entry — what a duplicated cluster needs, so each copy reads as a
    complete unit instead of one copy holding all the arrows.

    An occurrence id the diagram does not draw falls back to the base alias rather than dropping the
    arrow: losing a relation is a worse answer to a stale overlay than drawing it in the plain place.
    Identical pairs collapse, so a diagram cannot stack two arrows in the same place.
    """

    def route(conn: ConnectionRecord) -> list[tuple[str, str]]:
        base_source = alias_by_id.get(conn.source)
        base_target = alias_by_id.get(conn.target)
        overlays = connection_overlays(conn.artifact_id, diagram_connections)
        pairs: list[tuple[str, str]] = []
        for overlay in overlays or [{}]:
            source_key = str(overlay.get(SOURCE_OCCURRENCE_KEY) or "").strip()
            target_key = str(overlay.get(TARGET_OCCURRENCE_KEY) or "").strip()
            source = alias_by_occurrence.get(source_key) or base_source
            target = alias_by_occurrence.get(target_key) or base_target
            if source and target and (source, target) not in pairs:
                pairs.append((source, target))
        return pairs

    return route
