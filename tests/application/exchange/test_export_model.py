"""Pure unit tests for the exchange export use case (WU-F3b): report shape (exported/
unexportable), specialization/multiplicity extension properties, property-definition
dedup, and scope handling — all against fakes; real writer/reader round-trip lives in
tests/infrastructure/exchange/archimate_model_exchange/test_export_import_round_trip.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from src.application.exchange.concept_mapping import ExportElementMapping, ExportRelationshipMapping
from src.application.exchange.export_model import export_model
from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord

# ── fakes ─────────────────────────────────────────────────────────────────────


class FakeExportMapper:
    def __init__(
        self,
        elements: dict[tuple[str, str | None], ExportElementMapping] | None = None,
        relationships: dict[tuple[str, str | None], ExportRelationshipMapping] | None = None,
    ) -> None:
        self._elements = elements or {}
        self._relationships = relationships or {}

    def element_to_exchange(self, archimate_type, specialization=None, *, domain_hint=None):
        from src.application.exchange.concept_mapping import UnmappableArchimateTypeError

        key = (archimate_type, specialization)
        if key not in self._elements:
            raise UnmappableArchimateTypeError(archimate_type, specialization, "element")
        return self._elements[key]

    def relationship_to_exchange(self, connection_type, specialization=None):
        from src.application.exchange.concept_mapping import UnmappableArchimateTypeError

        key = (connection_type, specialization)
        if key not in self._relationships:
            raise UnmappableArchimateTypeError(connection_type, specialization, "relationship")
        return self._relationships[key]


@dataclass
class FakeEntities:
    records: dict[str, EntityRecord] = field(default_factory=dict)

    def get_entity(self, artifact_id: str) -> EntityRecord | None:
        return self.records.get(artifact_id)


@dataclass
class FakeConnections:
    by_source: dict[str, list[ConnectionRecord]] = field(default_factory=dict)

    def find_connections_for(self, entity_id: str, *, direction: str = "any", conn_type: str | None = None):
        return self.by_source.get(entity_id, [])


def _entity(
    artifact_id: str,
    artifact_type: str,
    name: str,
    *,
    domain: str = "business",
    specialization: str = "",
    content_text: str = "",
) -> EntityRecord:
    return EntityRecord(
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        name=name,
        version="0.1.0",
        status="draft",
        domain=domain,
        subdomain="",
        path=Path("dummy.md"),
        keywords=(),
        extra={},
        content_text=content_text,
        display_blocks={},
        display_label=name,
        display_alias=name,
        specialization=specialization,
    )


def _connection(
    artifact_id: str,
    source: str,
    target: str,
    conn_type: str,
    *,
    specialization: str = "",
    src_multiplicity: str = "",
    tgt_multiplicity: str = "",
    content_text: str = "",
) -> ConnectionRecord:
    return ConnectionRecord(
        artifact_id=artifact_id,
        source=source,
        target=target,
        conn_type=conn_type,
        version="0.1.0",
        status="draft",
        path=Path("dummy.outgoing.md"),
        extra={},
        content_text=content_text,
        specialization=specialization,
        src_multiplicity=src_multiplicity,
        tgt_multiplicity=tgt_multiplicity,
    )


# ── entity export ──────────────────────────────────────────────────────────────


def test_exports_a_mapped_entity() -> None:
    entities = FakeEntities({"REQ@1000000000.aaaaaa.foo": _entity("REQ@1000000000.aaaaaa.foo", "requirement", "Foo")})
    mapper = FakeExportMapper(elements={("requirement", None): ExportElementMapping(concept_type="Requirement")})

    report = export_model(
        ["REQ@1000000000.aaaaaa.foo"], entities=entities, connections=FakeConnections(), mapper=mapper
    )

    assert len(report.entities) == 1
    assert report.entities[0].concept_type == "Requirement"
    assert report.document.elements[0].concept_type == "Requirement"
    assert report.document.elements[0].names[0].text == "Foo"
    assert "@" not in report.document.elements[0].identifier


def test_missing_entity_is_unexportable() -> None:
    report = export_model(
        ["REQ@nope"], entities=FakeEntities(), connections=FakeConnections(), mapper=FakeExportMapper()
    )

    assert report.entities == ()
    assert len(report.unexportable) == 1
    assert report.unexportable[0].reason == "entity not found"


def test_unmappable_archimate_type_is_unexportable_not_raised() -> None:
    entities = FakeEntities({"X@1.a.b": _entity("X@1.a.b", "weird-type", "Weird")})
    report = export_model(["X@1.a.b"], entities=entities, connections=FakeConnections(), mapper=FakeExportMapper())

    assert report.entities == ()
    assert len(report.unexportable) == 1
    assert report.unexportable[0].archimate_type == "weird-type"


def test_specialization_extension_carried_as_property() -> None:
    entities = FakeEntities({
        "APP@1.a.svc": _entity("APP@1.a.svc", "application-component", "Svc", specialization="module"),
    })
    mapper = FakeExportMapper(
        elements={
            ("application-component", "module"): ExportElementMapping(
                concept_type="ApplicationComponent", extension_specialization="module"
            )
        }
    )

    report = export_model(["APP@1.a.svc"], entities=entities, connections=FakeConnections(), mapper=mapper)

    element = report.document.elements[0]
    assert element.concept_type == "ApplicationComponent"
    spec_props = [p for p in element.properties if p.property_definition_ref == "archrepo-specialization"]
    assert len(spec_props) == 1
    assert spec_props[0].values[0].text == "module"
    def_ids = {d.identifier for d in report.document.property_definitions}
    assert "archrepo-specialization" in def_ids


def test_decodes_properties_table_from_content_text() -> None:
    content = """\
<!-- §content -->

## Foo

## Properties

| Attribute | Value |
|---|---|
| Owner | Alice |
"""
    entities = FakeEntities({"REQ@1.a.foo": _entity("REQ@1.a.foo", "requirement", "Foo", content_text=content)})
    mapper = FakeExportMapper(elements={("requirement", None): ExportElementMapping(concept_type="Requirement")})

    report = export_model(["REQ@1.a.foo"], entities=entities, connections=FakeConnections(), mapper=mapper)

    element = report.document.elements[0]
    assert len(element.properties) == 1
    assert element.properties[0].values[0].text == "Alice"
    definition = next(
        d for d in report.document.property_definitions if d.identifier == element.properties[0].property_definition_ref
    )
    assert definition.names[0].text == "Owner"


def test_property_definitions_deduped_across_entities() -> None:
    content = """\
## Properties

| Attribute | Value |
|---|---|
| Owner | Alice |
"""
    entities = FakeEntities({
        "REQ@1.a.foo": _entity("REQ@1.a.foo", "requirement", "Foo", content_text=content),
        "REQ@1.b.bar": _entity("REQ@1.b.bar", "requirement", "Bar", content_text=content.replace("Alice", "Bob")),
    })
    mapper = FakeExportMapper(elements={("requirement", None): ExportElementMapping(concept_type="Requirement")})

    report = export_model(
        ["REQ@1.a.foo", "REQ@1.b.bar"], entities=entities, connections=FakeConnections(), mapper=mapper
    )

    owner_defs = [d for d in report.document.property_definitions if d.names[0].text == "Owner"]
    assert len(owner_defs) == 1
    values = {p.values[0].text for el in report.document.elements for p in el.properties}
    assert values == {"Alice", "Bob"}


# ── relationship export ─────────────────────────────────────────────────────────


def _two_entity_scope():
    entities = FakeEntities({
        "ACT@1.a.one": _entity("ACT@1.a.one", "business-actor", "One"),
        "ACT@1.b.two": _entity("ACT@1.b.two", "business-actor", "Two"),
    })
    mapper = FakeExportMapper(elements={("business-actor", None): ExportElementMapping(concept_type="BusinessActor")})
    return entities, mapper


def test_exports_connection_between_two_in_scope_entities() -> None:
    entities, mapper = _two_entity_scope()
    conn = _connection(
        "ACT@1.a.one---ACT@1.b.two@@archimate-serving", "ACT@1.a.one", "ACT@1.b.two", "archimate-serving"
    )
    connections = FakeConnections({"ACT@1.a.one": [conn]})
    mapper._relationships[("archimate-serving", None)] = ExportRelationshipMapping(concept_type="Serving")

    report = export_model(
        ["ACT@1.a.one", "ACT@1.b.two"], entities=entities, connections=connections, mapper=mapper
    )

    assert len(report.connections) == 1
    rel = report.document.relationships[0]
    assert rel.concept_type == "Serving"
    assert rel.source == report.entities[0].exchange_id
    assert rel.target == report.entities[1].exchange_id


def test_connection_to_out_of_scope_target_is_unexportable() -> None:
    entities, mapper = _two_entity_scope()
    conn = _connection(
        "ACT@1.a.one---OUT@2.c.three@@archimate-serving", "ACT@1.a.one", "OUT@2.c.three", "archimate-serving"
    )
    connections = FakeConnections({"ACT@1.a.one": [conn]})
    mapper._relationships[("archimate-serving", None)] = ExportRelationshipMapping(concept_type="Serving")

    report = export_model(["ACT@1.a.one"], entities=entities, connections=connections, mapper=mapper)

    assert report.connections == ()
    assert len(report.unexportable) == 1
    assert report.unexportable[0].kind == "relationship"
    assert "scope" in report.unexportable[0].reason


def test_unmappable_relationship_type_is_unexportable() -> None:
    entities, mapper = _two_entity_scope()
    conn = _connection("ACT@1.a.one---ACT@1.b.two@@weird-conn", "ACT@1.a.one", "ACT@1.b.two", "weird-conn")
    connections = FakeConnections({"ACT@1.a.one": [conn]})

    report = export_model(
        ["ACT@1.a.one", "ACT@1.b.two"], entities=entities, connections=connections, mapper=mapper
    )

    assert report.connections == ()
    assert len(report.unexportable) == 1
    assert report.unexportable[0].archimate_type == "weird-conn"


def test_multiplicity_exports_as_extension_properties() -> None:
    entities, mapper = _two_entity_scope()
    conn = _connection(
        "ACT@1.a.one---ACT@1.b.two@@archimate-serving",
        "ACT@1.a.one",
        "ACT@1.b.two",
        "archimate-serving",
        src_multiplicity="1",
        tgt_multiplicity="0..*",
    )
    connections = FakeConnections({"ACT@1.a.one": [conn]})
    mapper._relationships[("archimate-serving", None)] = ExportRelationshipMapping(concept_type="Serving")

    report = export_model(
        ["ACT@1.a.one", "ACT@1.b.two"], entities=entities, connections=connections, mapper=mapper
    )

    rel = report.document.relationships[0]
    by_ref = {p.property_definition_ref: p.values[0].text for p in rel.properties}
    assert by_ref["archrepo-src-multiplicity"] == "1"
    assert by_ref["archrepo-tgt-multiplicity"] == "0..*"


def test_connection_specialization_carried_as_extension() -> None:
    entities, mapper = _two_entity_scope()
    conn = _connection(
        "ACT@1.a.one---ACT@1.b.two@@archimate-assignment",
        "ACT@1.a.one",
        "ACT@1.b.two",
        "archimate-assignment",
        specialization="responsibility-assignment",
    )
    connections = FakeConnections({"ACT@1.a.one": [conn]})
    mapper._relationships[("archimate-assignment", "responsibility-assignment")] = ExportRelationshipMapping(
        concept_type="Assignment", extension_specialization="responsibility-assignment"
    )

    report = export_model(
        ["ACT@1.a.one", "ACT@1.b.two"], entities=entities, connections=connections, mapper=mapper
    )

    rel = report.document.relationships[0]
    assert rel.concept_type == "Assignment"
    spec_props = [p for p in rel.properties if p.property_definition_ref == "archrepo-specialization"]
    assert spec_props[0].values[0].text == "responsibility-assignment"
