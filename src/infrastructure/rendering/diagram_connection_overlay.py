"""What a diagram says about a connection it draws, as distinct from what the model says.

The model owns a connection's endpoints: A realizes B, wherever either is drawn. A diagram owns
*which drawing* the arrow attaches to, which only exists on the picture. An entity drawn twice has
two aliases, and without a way to say which one an arrow means, every arrow lands on the first — so
a second occurrence can only ever be an unconnected copy, which is what made the feature useless.

The ``connections`` overlay says so, and `src.domain.diagrams.drawn_relations` is its one reading:
which arrows a connection draws, between which instances, each under which key. This module is the
last step, from an instance to the alias its drawing carries.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from src.application.artifacts.parsing import normalize_puml_alias
from src.domain.diagrams.drawn_relations import connection_overlays, relations_drawn_for
from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord
from src.infrastructure.rendering.archimate_occurrences import occurrence_id_of


@dataclass(frozen=True)
class DrawnArrow:
    """One arrow of a body: the aliases it joins, and the key a statement about it is filed under."""

    source_alias: str
    target_alias: str
    key: str


#: Resolves a connection to the arrows it draws. Empty when neither endpoint is drawn. Usually one;
#: more when a duplicated cluster draws the same relation in each copy.
EndpointRouter = Callable[[ConnectionRecord], list[DrawnArrow]]


def connection_overlay(
    artifact_id: str,
    diagram_connections: Sequence[Mapping[str, object]] | None,
) -> Mapping[str, object] | None:
    """The diagram's first entry for *artifact_id*, matched by stable id.

    First, not only: a connection drawn in two places has an entry per drawing. The label opt-ins
    are a property of the relation rather than of one arrow, so they are read from whichever entry
    comes first; the routing keys are read per entry by `relations_drawn_for`.
    """
    entries = connection_overlays(artifact_id, diagram_connections)
    return entries[0] if entries else None


def occurrence_alias_by_id(render_entities: Sequence[EntityRecord]) -> dict[str, str]:
    """Map each occurrence id to the alias its own drawing carries.

    Occurrences are the records `occurrence_entities` adds: they keep the backing entity's
    `artifact_id` and carry the occurrence id in `host_diagram_id`, which is why they cannot be found
    through the entity-keyed alias map and need this one.
    """
    aliases: dict[str, str] = {}
    for entity in render_entities:
        occurrence_id = occurrence_id_of(entity)
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
    complete unit instead of one copy holding all the arrows. An end whose instance carries no alias
    draws no arrow.
    """

    def route(conn: ConnectionRecord) -> list[DrawnArrow]:
        arrows: list[DrawnArrow] = []
        for drawn in relations_drawn_for(
            conn.artifact_id,
            source=conn.source,
            target=conn.target,
            diagram_connections=diagram_connections,
            occurrences=alias_by_occurrence,
        ):
            source = alias_by_occurrence.get(drawn.source_instance) or alias_by_id.get(drawn.source_instance)
            target = alias_by_occurrence.get(drawn.target_instance) or alias_by_id.get(drawn.target_instance)
            if source and target:
                arrows.append(DrawnArrow(source, target, drawn.key.text))
        return arrows

    return route
