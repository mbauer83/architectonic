from __future__ import annotations

from typing import Any, cast

from src.domain.ontology_representation.artifact_types import (
    ConnectionRecord,
    DiagramRecord,
    DocumentRecord,
    EntityRecord,
)


class CandidateListMixin:
    def list_entities(
        self,
        *,
        artifact_type: str | None = None,
        domain: str | None = None,
        subdomain: str | None = None,
        status: str | None = None,
        group: str | None = None,
    ) -> list[EntityRecord]:
        owner = cast(Any, self)
        live = [
            rec for rec in owner._live.list_entities(
                artifact_type=artifact_type, domain=domain, subdomain=subdomain, status=status, group=group,
            )
            if rec.artifact_id not in owner._deleted_entities
        ]
        overlay = [
            rec for rec in owner._entities.values()
            if _matches_entity_filter(rec, artifact_type, domain, subdomain, status, group)
        ]
        return [rec for rec in (owner._map_entity(r) for r in live) if rec is not None] + overlay

    def list_connections(
        self,
        *,
        conn_type: str | None = None,
        source: str | None = None,
        target: str | None = None,
        status: str | None = None,
        group: str | None = None,
    ) -> list[ConnectionRecord]:
        owner = cast(Any, self)
        live = [
            rec for rec in owner._live.list_connections(
                conn_type=conn_type, source=source, target=target, status=status, group=group,
            )
            if rec.artifact_id not in owner._deleted_connections
        ]
        overlay = [
            rec for rec in owner._connections.values()
            if _matches_connection_filter(rec, conn_type, source, target, status, group)
        ]
        return [rec for rec in (owner._map_connection(r) for r in live) if rec is not None] + overlay

    def list_diagrams(
        self, *, diagram_type: str | None = None, status: str | None = None, group: str | None = None
    ) -> list[DiagramRecord]:
        owner = cast(Any, self)
        live = [
            rec for rec in owner._live.list_diagrams(diagram_type=diagram_type, status=status, group=group)
            if rec.artifact_id not in owner._deleted_diagrams
        ]
        overlay = [
            rec for rec in owner._diagrams.values()
            if (diagram_type is None or rec.diagram_type == diagram_type)
            and (status is None or rec.status == status)
            and (group is None or rec.group == group)
        ]
        return [rec for rec in (owner._map_diagram(r) for r in live) if rec is not None] + overlay

    def list_documents(
        self, *, doc_type: str | None = None, status: str | None = None, group: str | None = None
    ) -> list[DocumentRecord]:
        owner = cast(Any, self)
        live = [
            rec for rec in owner._live.list_documents(doc_type=doc_type, status=status, group=group)
            if rec.artifact_id not in owner._deleted_documents
        ]
        overlay = [
            rec for rec in owner._documents.values()
            if (doc_type is None or rec.doc_type == doc_type)
            and (status is None or rec.status == status)
            and (group is None or rec.group == group)
        ]
        return [rec for rec in (owner._map_document(r) for r in live) if rec is not None] + overlay


def _matches_entity_filter(
    rec: EntityRecord,
    artifact_type: str | None,
    domain: str | None,
    subdomain: str | None,
    status: str | None,
    group: str | None,
) -> bool:
    return (
        (artifact_type is None or rec.artifact_type == artifact_type)
        and (domain is None or rec.domain == domain)
        and (subdomain is None or rec.subdomain == subdomain)
        and (status is None or rec.status == status)
        and (group is None or rec.group == group)
    )


def _matches_connection_filter(
    rec: ConnectionRecord,
    conn_type: str | None,
    source: str | None,
    target: str | None,
    status: str | None,
    group: str | None,
) -> bool:
    return (
        (conn_type is None or rec.conn_type == conn_type)
        and (source is None or rec.source == source)
        and (target is None or rec.target == target)
        and (status is None or rec.status == status)
        and (group is None or rec.group == group)
    )
