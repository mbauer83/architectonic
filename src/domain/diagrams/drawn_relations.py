"""Which relations a diagram draws for a connection, and between which instances.

The model owns a connection's endpoints. A diagram owns *which drawing* each arrow attaches to: an
entry of its ``connections`` overlay names a connection and may say ``source-occurrence`` or
``target-occurrence``, an occurrence id from ``diagram-entities``. One entry is one arrow; a
connection with no entry is drawn once, between the two base instances.

Decided here over instance ids, so the renderer that draws the arrows, the write path that prunes a
layout and the verifier that checks one all count the same relations under the same keys.
"""

from __future__ import annotations

from collections.abc import Container, Mapping, Sequence
from dataclasses import dataclass

from src.domain.artifact_id import stable_conn_id
from src.domain.diagrams.relation_key import DrawnRelationKey, drawn_relation_key

SOURCE_OCCURRENCE_KEY = "source-occurrence"
TARGET_OCCURRENCE_KEY = "target-occurrence"


@dataclass(frozen=True)
class DrawnRelation:
    """One arrow: the instances it runs between, and the key every statement about it uses."""

    source_instance: str
    target_instance: str
    key: DrawnRelationKey


def connection_overlays(
    artifact_id: str, diagram_connections: Sequence[Mapping[str, object]] | None
) -> list[Mapping[str, object]]:
    """Every overlay entry for *artifact_id*, matched by stable id — one per arrow the diagram draws for it."""
    return [
        item
        for item in diagram_connections or []
        if isinstance(item, Mapping)
        and stable_conn_id(str(item.get("artifact_id") or item.get("connection_id") or "").strip())
        == stable_conn_id(artifact_id)
    ]


def relations_drawn_for(
    connection_id: str,
    *,
    source: str,
    target: str,
    diagram_connections: Sequence[Mapping[str, object]] | None,
    occurrences: Container[str],
) -> list[DrawnRelation]:
    """The arrows a diagram draws for one connection joining *source* and *target*.

    An occurrence the diagram does not draw falls back to the base instance rather than dropping the
    arrow: losing a relation is a worse answer to a stale overlay than drawing it in the plain place.
    Identical pairs collapse, so a diagram cannot stack two arrows in the same place.
    """
    drawn: list[DrawnRelation] = []
    seen: set[tuple[str, str]] = set()
    for overlay in connection_overlays(connection_id, diagram_connections) or [{}]:
        named_source = str(overlay.get(SOURCE_OCCURRENCE_KEY) or "").strip()
        named_target = str(overlay.get(TARGET_OCCURRENCE_KEY) or "").strip()
        ends = (
            named_source if named_source in occurrences else source,
            named_target if named_target in occurrences else target,
        )
        if ends in seen:
            continue
        seen.add(ends)
        key = drawn_relation_key(
            connection_id, source=source, target=target, source_instance=ends[0], target_instance=ends[1]
        )
        drawn.append(DrawnRelation(ends[0], ends[1], key))
    return drawn


def held_connection_id(row: Mapping[str, object]) -> str | None:
    """The id, within its diagram, of a connection the diagram holds itself — or None for a row that is not one.

    A held connection states both its ends (``source``/``target``, or the ``source_id``/``target_id``
    an argument edge uses) and usually its type. Its id is the one it states, else source, type and
    target joined — with the type left empty where a row states none, so the spelling never reads as
    a pair of aliases. This is also the key a statement about that drawn relation uses.
    """
    conn_type = str(row.get("conn_type") or "")
    source = str(row.get("source") or row.get("source_id") or "")
    target = str(row.get("target") or row.get("target_id") or "")
    if not (source and target):
        return None
    return str(row.get("id") or f"{source}:{conn_type}:{target}")
