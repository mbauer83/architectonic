"""Small, normative relationship-derivation example models."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from src.domain.modules.module_catalog import ModuleCatalog, ModuleCatalogBuilder
from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord
from src.ontologies.archimate_4 import module


def entity(identifier: str, type_name: str) -> EntityRecord:
    return EntityRecord(
        artifact_id=identifier,
        artifact_type=type_name,
        name=identifier,
        version="1",
        status="draft",
        domain="",
        subdomain="",
        path=Path("/examples"),
        keywords=(),
        extra={},
        content_text="",
        display_blocks={},
        display_label="",
        display_alias="",
    )


def connection(identifier: str, source: str, target: str, type_name: str) -> ConnectionRecord:
    return ConnectionRecord(identifier, source, target, type_name, "1", "draft", Path("/examples"), {}, "")


@dataclass
class ExampleGraph:
    entities: dict[str, EntityRecord] = field(default_factory=dict)
    connections: list[ConnectionRecord] = field(default_factory=list)

    def get_entity(self, artifact_id: str) -> EntityRecord | None:
        return self.entities.get(artifact_id)

    def get_connection(self, artifact_id: str) -> ConnectionRecord | None:
        return next((item for item in self.connections if item.artifact_id == artifact_id), None)

    def find_connections_for(
        self, entity_id: str, *, direction: str = "any", conn_type: str | None = None
    ) -> list[ConnectionRecord]:
        return [item for item in self.connections if entity_id in {item.source, item.target}]

    def entity_ids(self) -> set[str]:
        return set(self.entities)

    def connection_ids(self) -> set[str]:
        return {item.artifact_id for item in self.connections}


def catalog() -> ModuleCatalog:
    builder = ModuleCatalogBuilder()
    builder.register_ontology(module)
    return builder.build()


def financial_application() -> ExampleGraph:
    return ExampleGraph(
        entities={
            "financial-application": entity("financial-application", "application-component"),
            "payment-function": entity("payment-function", "function"),
            "payment-subfunction": entity("payment-subfunction", "function"),
            "payment-service": entity("payment-service", "service"),
        },
        connections=[
            connection("assigns-function", "financial-application", "payment-function", "archimate-assignment"),
            connection("aggregates-subfunction", "payment-function", "payment-subfunction", "archimate-aggregation"),
            connection("realizes-service", "payment-subfunction", "payment-service", "archimate-realization"),
        ],
    )


def flow_endpoints() -> ExampleGraph:
    return ExampleGraph(
        entities={
            "source-function": entity("source-function", "function"),
            "source-service": entity("source-service", "service"),
            "target-function": entity("target-function", "function"),
            "target-service": entity("target-service", "service"),
        },
        connections=[
            connection("source-realizes", "source-function", "source-service", "archimate-realization"),
            connection("service-flow", "source-service", "target-service", "archimate-flow"),
            connection("target-realizes", "target-function", "target-service", "archimate-realization"),
        ],
    )


def sales_and_shipping() -> ExampleGraph:
    return ExampleGraph(
        entities={
            "sales-department": entity("sales-department", "role"),
            "selling": entity("selling", "process"),
            "invoicing": entity("invoicing", "process"),
            "billing": entity("billing", "process"),
            "payment": entity("payment", "process"),
            "shipping": entity("shipping", "process"),
        },
        connections=[
            connection("sales-assignment", "sales-department", "selling", "archimate-assignment"),
            connection("selling-trigger", "selling", "invoicing", "archimate-triggering"),
            connection("billing-aggregation", "invoicing", "billing", "archimate-aggregation"),
            connection("payment-aggregation", "invoicing", "payment", "archimate-aggregation"),
            connection("shipping-trigger", "invoicing", "shipping", "archimate-triggering"),
        ],
    )


def hosting_suite() -> ExampleGraph:
    return ExampleGraph(
        entities={
            "suite": entity("suite", "application-component"),
            "front-end": entity("front-end", "application-component"),
            "back-end": entity("back-end", "application-component"),
            "database-hosting": entity("database-hosting", "technology-node"),
            "website-hosting": entity("website-hosting", "technology-node"),
        },
        connections=[
            connection("suite-front-end", "suite", "front-end", "archimate-aggregation"),
            connection("suite-back-end", "suite", "back-end", "archimate-aggregation"),
            connection("database-serves-suite", "database-hosting", "suite", "archimate-serving"),
            connection("website-serves-suite", "website-hosting", "suite", "archimate-serving"),
        ],
    )


def project_specialization() -> ExampleGraph:
    return ExampleGraph(
        entities={
            "project-team": entity("project-team", "role"),
            "it-project-team": entity("it-project-team", "role"),
            "project": entity("project", "process"),
            "it-project": entity("it-project", "process"),
            "project-manager": entity("project-manager", "role"),
            "project-planning": entity("project-planning", "data-object"),
            "software-documentation": entity("software-documentation", "data-object"),
        },
        connections=[
            connection("team-specialization", "it-project-team", "project-team", "archimate-specialization"),
            connection("project-specialization", "it-project", "project", "archimate-specialization"),
            connection("team-assignment", "project-team", "project", "archimate-assignment"),
            connection("team-aggregation", "project-team", "project-manager", "archimate-aggregation"),
            connection("project-reads-planning", "project", "project-planning", "archimate-access"),
            connection("it-project-writes-documentation", "it-project", "software-documentation", "archimate-access"),
        ],
    )
