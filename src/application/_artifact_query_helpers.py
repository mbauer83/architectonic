"""Private helper functions for ArtifactRepository — filter, match, read, traverse."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from src.domain.ontology_representation.artifact_types import (
    ArtifactSummary,
    ConnectionRecord,
    DiagramRecord,
    DocumentRecord,
    EntityRecord,
)

if TYPE_CHECKING:
    from src.application.artifact_repository import ArtifactRepository

_NONE_LABEL = "(none)"


# ---------------------------------------------------------------------------
# Scalar filters
# ---------------------------------------------------------------------------


def matches_entity(
    rec: EntityRecord,
    *,
    artifact_type: str | None,
    domain: str | None,
    subdomain: str | None,
    status: str | None,
    group: str | None = None,
) -> bool:
    return (
        (artifact_type is None or rec.artifact_type == artifact_type)
        and (domain is None or rec.domain == domain)
        and (subdomain is None or rec.subdomain == subdomain)
        and (status is None or rec.status == status)
        and (group is None or rec.group == group)
    )


def matches_connection(
    rec: ConnectionRecord,
    *,
    conn_type: str | None,
    source: str | None,
    target: str | None,
    status: str | None,
    group: str | None = None,
) -> bool:
    return (
        (conn_type is None or rec.conn_type == conn_type)
        and (source is None or source in rec.source_ids)
        and (target is None or target in rec.target_ids)
        and (status is None or rec.status == status)
        and (group is None or rec.group == group)
    )


def matches_diagram(
    rec: DiagramRecord,
    *,
    diagram_type: str | None,
    status: str | None,
    group: str | None = None,
) -> bool:
    return (
        (diagram_type is None or rec.diagram_type == diagram_type)
        and (status is None or rec.status == status)
        and (group is None or rec.group == group)
    )


# ---------------------------------------------------------------------------
# Set filters
# ---------------------------------------------------------------------------


def matches_entity_sets(rec: EntityRecord, types: set[str], domains: set[str], statuses: set[str]) -> bool:
    return (
        (not types or rec.artifact_type in types)
        and (not domains or rec.domain in domains)
        and (not statuses or rec.status in statuses)
    )


def matches_connection_sets(rec: ConnectionRecord, statuses: set[str]) -> bool:
    return not statuses or rec.status in statuses


def matches_diagram_sets(rec: DiagramRecord, types: set[str], statuses: set[str]) -> bool:
    return (not types or rec.artifact_type in types) and (not statuses or rec.status in statuses)


# ---------------------------------------------------------------------------
# Graph helpers
# ---------------------------------------------------------------------------


def next_frontier(
    frontier: set[str],
    visited: set[str],
    registry: "ArtifactRepository",
    conn_type: str | None,
) -> set[str]:
    result: set[str] = set()
    for entity_id in frontier:
        for conn in registry.find_connections_for(entity_id, conn_type=conn_type):
            for neighbor_id in conn.source_ids + conn.target_ids:
                if neighbor_id != entity_id and neighbor_id not in visited:
                    result.add(neighbor_id)
    return result


def matches_direction(
    rec: ConnectionRecord,
    *,
    entity_id: str,
    direction: Literal["any", "outbound", "inbound"],
) -> bool:
    in_src = entity_id in rec.source_ids
    in_tgt = entity_id in rec.target_ids
    match direction:
        case "outbound":
            return in_src
        case "inbound":
            return in_tgt
        case _:
            return in_src or in_tgt


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def to_set(value: str | list[str] | None) -> set[str]:
    if value is None:
        return set()
    return {value} if isinstance(value, str) else set(value)


def single_or_none(value: str | list[str] | None) -> str | None:
    return value if isinstance(value, str) else None


def summary_group_key(
    summary: ArtifactSummary,
    group_by: Literal["artifact_type", "diagram_type", "domain", "group"],
) -> str:
    match group_by:
        case "artifact_type":
            return summary.artifact_type or _NONE_LABEL
        case "group":
            return summary.group or _NONE_LABEL
        case _:
            return _NONE_LABEL


# ---------------------------------------------------------------------------
# Read serialisers
# ---------------------------------------------------------------------------


def read_entity(rec: EntityRecord, *, mode: Literal["summary", "full"]) -> dict[str, object]:
    data: dict[str, object] = {
        "artifact_id": rec.artifact_id,
        "artifact_type": rec.artifact_type,
        "name": rec.name,
        "version": rec.version,
        "status": rec.status,
        "domain": rec.domain,
        "subdomain": rec.subdomain,
        "record_type": "entity",
        "path": str(rec.path),
        "content_snippet": rec.content_text[:400] + ("…" if len(rec.content_text) > 400 else ""),
        "keywords": list(rec.keywords),
        "group": rec.group,
        "specialization": rec.specialization,
        "specializations": list(rec.specializations),
        "attributes": dict(rec.attributes),
        "last_updated": rec.last_updated,
    }
    if rec.host_diagram_id is not None:
        data["host_diagram_id"] = rec.host_diagram_id
    if mode == "full":
        data["content_text"] = rec.content_text
        data["display_blocks"] = rec.display_blocks
        data["extra"] = rec.extra
    return data


def read_connection(rec: ConnectionRecord, *, mode: Literal["summary", "full"]) -> dict[str, object]:
    data: dict[str, object] = {
        "artifact_id": rec.artifact_id,
        "source": rec.source,
        "target": rec.target,
        "conn_type": rec.conn_type,
        "version": rec.version,
        "status": rec.status,
        "record_type": "connection",
        "path": str(rec.path),
        "content_snippet": rec.content_text[:400] + ("…" if len(rec.content_text) > 400 else ""),
        "group": rec.group,
        "specialization": rec.specialization,
        "specializations": list(rec.specializations),
        "attributes": dict(rec.attributes),
        "last_updated": rec.last_updated,
    }
    if mode == "full":
        data["content_text"] = rec.content_text
        data["extra"] = rec.extra
    return data


def read_diagram(rec: DiagramRecord, *, mode: Literal["summary", "full"]) -> dict[str, object]:
    data: dict[str, object] = {
        "artifact_id": rec.artifact_id,
        "artifact_type": rec.artifact_type,
        "name": rec.name,
        "diagram_type": rec.diagram_type,
        "version": rec.version,
        "status": rec.status,
        "record_type": "diagram",
        "path": str(rec.path),
        "content_snippet": "",
        "group": rec.group,
        "last_updated": rec.last_updated,
    }
    if mode == "full":
        try:
            data["puml_source"] = rec.path.read_text(encoding="utf-8")
        except OSError:
            data["puml_source"] = ""
        data["extra"] = rec.extra
    return data


def read_document(
    rec: DocumentRecord,
    *,
    mode: Literal["summary", "full"],
    section: str | None = None,
) -> dict[str, object]:
    data: dict[str, object] = {
        "artifact_id": rec.artifact_id,
        "artifact_type": "document",
        "doc_type": rec.doc_type,
        "title": rec.title,
        "status": rec.status,
        "record_type": "document",
        "path": str(rec.path),
        "keywords": list(rec.keywords),
        "sections": list(rec.sections),
        "content_snippet": rec.content_text[:400] + ("…" if len(rec.content_text) > 400 else ""),
        "group": rec.group,
        "last_updated": rec.last_updated,
    }
    if mode == "full":
        data["content_text"] = _extract_section(rec.content_text, section) if section else rec.content_text
        data["extra"] = rec.extra
    return data


def _extract_section(content: str, section: str) -> str:
    import re

    pattern = re.compile(r"^##\s+" + re.escape(section) + r"\s*$", re.MULTILINE | re.IGNORECASE)
    m = pattern.search(content)
    if not m:
        return ""
    body_start = m.end()
    next_heading = re.search(r"^##\s+", content[body_start:], re.MULTILINE)
    if next_heading:
        return content[body_start : body_start + next_heading.start()].strip()
    return content[body_start:].strip()
