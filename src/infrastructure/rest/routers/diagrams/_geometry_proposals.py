"""Read-only render records for elements and relations an editor has yet to save."""

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.application.artifacts.parsing import standard_alias_of
from src.application.runtime_catalogs import RuntimeCatalogs
from src.domain.artifact_id import connection_id_as_written, parse_entity_id, stable_conn_id, stable_id
from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord
from src.infrastructure.rest.routers.diagrams._write_bodies import DiagramComposition


class ProposedElement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    artifact_id: str
    name: str = Field(min_length=1)
    specializations: tuple[str, ...] = ()
    attributes: dict[str, object] = Field(default_factory=dict)


class ProposedRelation(BaseModel):
    description: str = ""
    src_multiplicity: str = ""
    tgt_multiplicity: str = ""
    model_config = ConfigDict(extra="forbid")
    artifact_id: str
    attributes: dict[str, object] = Field(default_factory=dict)


class GeometryPreviewBody(DiagramComposition):
    arrangement: dict[str, Any] | None = None
    proposed_elements: list[ProposedElement] = Field(default_factory=list)
    proposed_relations: list[ProposedRelation] = Field(default_factory=list)

    def proposals(
        self, catalogs: RuntimeCatalogs, repo: Any,
    ) -> tuple[tuple[EntityRecord, ...], tuple[ConnectionRecord, ...]]:
        ontology = catalogs.ontology
        entities: list[EntityRecord] = []
        connections: list[ConnectionRecord] = []
        members = {stable_id(item) for item in self.entity_ids}
        relations = {stable_conn_id(item) for item in self.connection_ids}
        for item in self.proposed_elements:
            key = stable_id(item.artifact_id)
            kind = ontology.entity_type_prefixes().get(parse_entity_id(item.artifact_id).prefix)
            if not kind or key in members or repo.get_entity(item.artifact_id) is not None:
                raise ValueError(f"Invalid or duplicate proposed element {item.artifact_id}")
            members.add(key)
            hierarchy = ontology.all_entity_types()[kind].hierarchy
            entities.append(EntityRecord(
                artifact_id=item.artifact_id, artifact_type=kind, name=item.name, version="", status="draft",
                domain=hierarchy[0], subdomain="", path=Path(), keywords=(), extra={}, content_text="",
                display_blocks={}, display_label=item.name, display_alias=standard_alias_of(item.artifact_id),
                attributes=item.attributes, specializations=item.specializations,
            ))
        for relation in self.proposed_relations:
            source, target, kind = connection_id_as_written(relation.artifact_id)
            key = stable_conn_id(relation.artifact_id)
            if (kind not in ontology.all_connection_types() or key in relations
                    or repo.get_connection(relation.artifact_id) is not None):
                raise ValueError(f"Invalid or duplicate proposed relation {relation.artifact_id}")
            if {stable_id(source), stable_id(target)} - members:
                raise ValueError("Both ends of a proposed relation must be on the diagram")
            relations.add(key)
            connections.append(ConnectionRecord(
                artifact_id=relation.artifact_id, source=source, target=target, conn_type=kind, version="",
                status="draft", path=Path(), extra={}, content_text=relation.description,
                attributes=relation.attributes,
                src_multiplicity=relation.src_multiplicity, tgt_multiplicity=relation.tgt_multiplicity,
            ))
        return tuple(entities), tuple(connections)
