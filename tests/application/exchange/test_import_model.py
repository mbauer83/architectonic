"""Pure unit tests for the exchange import use case (WU-F3a): report shape (created/
updated/skipped/unmappable), dry-run vs. commit, exchange-identity re-import idempotence,
and the composition-never-downgraded invariant — all against fakes, no real repo I/O
(that lives in tests/infrastructure/exchange/archimate_model_exchange/test_import_integration.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.application.exchange.concept_mapping import ElementMapping, RelationshipMapping, UnmappableConceptError
from src.application.exchange.document import (
    ExchangeElement,
    ExchangeModel,
    ExchangeProperty,
    ExchangePropertyDefinition,
    ExchangeRelationship,
    LangString,
)
from src.application.exchange.import_model import import_model
from src.application.exchange.write_ports import ExchangeWriteOutcome, InvalidRelationshipError
from src.domain.artifact_id import stable_id

# ── fakes ─────────────────────────────────────────────────────────────────────


class FakeMapper:
    def __init__(
        self,
        elements: dict[str, ElementMapping] | None = None,
        relationships: dict[str, RelationshipMapping] | None = None,
    ) -> None:
        self._elements = elements or {}
        self._relationships = relationships or {}
        self.element_hints: dict[str, str | None] = {}
        self.relationship_hints: dict[str, str | None] = {}

    def element_to_archimate(self, concept_type: str, *, specialization_hint: str | None = None) -> ElementMapping:
        self.element_hints[concept_type] = specialization_hint
        if concept_type not in self._elements:
            raise UnmappableConceptError(concept_type, "element")
        return self._elements[concept_type]

    def relationship_to_archimate(
        self, concept_type: str, *, specialization_hint: str | None = None
    ) -> RelationshipMapping:
        self.relationship_hints[concept_type] = specialization_hint
        if concept_type not in self._relationships:
            raise UnmappableConceptError(concept_type, "relationship")
        return self._relationships[concept_type]


@dataclass
class FakeWriter:
    forbidden_connection_types: frozenset[str] = field(default_factory=frozenset)
    created: list[dict[str, object]] = field(default_factory=list)
    updated: list[dict[str, object]] = field(default_factory=list)
    connections_attempted: list[dict[str, object]] = field(default_factory=list)
    _counter: int = 0

    def create_entity(self, *, artifact_type, name, properties, notes, specialization, dry_run) -> ExchangeWriteOutcome:
        self._counter += 1
        artifact_id = f"FAKE@{self._counter}.entity"
        self.created.append({
            "artifact_type": artifact_type, "name": name, "properties": dict(properties),
            "notes": notes, "specialization": specialization, "dry_run": dry_run,
        })
        return ExchangeWriteOutcome(wrote=not dry_run, artifact_id=artifact_id, valid=True)

    def update_entity(self, *, artifact_id, name, properties, notes, specialization, dry_run) -> ExchangeWriteOutcome:
        self.updated.append({
            "artifact_id": artifact_id, "name": name, "properties": dict(properties),
            "notes": notes, "specialization": specialization, "dry_run": dry_run,
        })
        return ExchangeWriteOutcome(wrote=not dry_run, artifact_id=artifact_id, valid=True)

    def add_connection(
        self, *, source, target, connection_type, description, specialization,
        src_multiplicity, tgt_multiplicity, extra_known_ids, dry_run,
    ) -> ExchangeWriteOutcome:
        self.connections_attempted.append({"source": source, "target": target, "connection_type": connection_type})
        if connection_type in self.forbidden_connection_types:
            raise InvalidRelationshipError(f"'{connection_type}' is not permitted from X to Y.")
        conn_id = f"{stable_id(source)}---{stable_id(target)}@@{connection_type}"
        return ExchangeWriteOutcome(wrote=not dry_run, artifact_id=conn_id, valid=True)


class FakeIdentityStore:
    def __init__(self, seed: dict[str, str] | None = None) -> None:
        self._map = dict(seed or {})

    def artifact_id_for(self, exchange_id: str) -> str | None:
        return self._map.get(exchange_id)

    def record(self, exchange_id: str, artifact_id: str) -> None:
        self._map[exchange_id] = artifact_id


@dataclass(frozen=True)
class FakeConnectionRecord:
    artifact_id: str
    source: str
    target: str
    conn_type: str


class FakeStore:
    def __init__(self, connections: list[FakeConnectionRecord] | None = None) -> None:
        self._connections = connections or []

    def find_connections_for(self, entity_id: str, *, direction: str = "any", conn_type: str | None = None):
        return [
            c for c in self._connections
            if c.source == entity_id and (conn_type is None or c.conn_type == conn_type)
        ]


def _element(identifier: str, concept_type: str, name: str = "Name", properties=()) -> ExchangeElement:
    return ExchangeElement(
        identifier=identifier, concept_type=concept_type, names=(LangString(name),), properties=properties
    )


def _relationship(identifier: str, concept_type: str, source: str, target: str) -> ExchangeRelationship:
    return ExchangeRelationship(identifier=identifier, concept_type=concept_type, source=source, target=target)


# ── entity creation / update ──────────────────────────────────────────────────


def test_new_element_dry_run_creates_nothing_but_reports_intent() -> None:
    mapper = FakeMapper(elements={"BusinessActor": ElementMapping(archimate_type="business-actor")})
    writer = FakeWriter()
    document = ExchangeModel(identifier="m1", elements=(_element("e1", "BusinessActor"),))

    report = import_model(document, store=FakeStore(), identity=FakeIdentityStore(), mapper=mapper, writer=writer)

    assert report.committed is False
    assert len(report.entities) == 1
    assert report.entities[0].action == "created"
    assert writer.created[0]["dry_run"] is True


def test_commit_records_identity_so_second_import_updates() -> None:
    mapper = FakeMapper(elements={"BusinessActor": ElementMapping(archimate_type="business-actor")})
    writer = FakeWriter()
    identity = FakeIdentityStore()
    document = ExchangeModel(identifier="m1", elements=(_element("e1", "BusinessActor"),))

    first = import_model(document, store=FakeStore(), identity=identity, mapper=mapper, writer=writer, commit=True)
    assert first.entities[0].action == "created"
    created_id = first.entities[0].artifact_id

    second = import_model(document, store=FakeStore(), identity=identity, mapper=mapper, writer=writer, commit=True)
    assert second.entities[0].action == "updated"
    assert second.entities[0].artifact_id == created_id
    assert writer.updated[0]["artifact_id"] == created_id


def test_unmappable_concept_type_reported_not_raised() -> None:
    mapper = FakeMapper(elements={})
    document = ExchangeModel(identifier="m1", elements=(_element("e1", "SomeUnknownType"),))

    report = import_model(document, store=FakeStore(), identity=FakeIdentityStore(), mapper=mapper, writer=FakeWriter())

    assert report.entities == ()
    assert len(report.unmappable) == 1
    assert report.unmappable[0].concept_type == "SomeUnknownType"
    assert report.unmappable[0].kind == "element"


def test_specialization_hint_extracted_and_excluded_from_properties() -> None:
    mapper = FakeMapper(elements={"ApplicationComponent": ElementMapping(archimate_type="application-component")})
    writer = FakeWriter()
    props = (
        ExchangeProperty(property_definition_ref="archrepo-specialization", values=(LangString("module"),)),
        ExchangeProperty(property_definition_ref="pd-owner", values=(LangString("Alice"),)),
    )
    document = ExchangeModel(
        identifier="m1",
        elements=(_element("e1", "ApplicationComponent", properties=props),),
        property_definitions=(
            ExchangePropertyDefinition(identifier="pd-owner", data_type="string", names=(LangString("Owner"),)),
        ),
    )

    import_model(document, store=FakeStore(), identity=FakeIdentityStore(), mapper=mapper, writer=writer)

    assert mapper.element_hints["ApplicationComponent"] == "module"
    assert writer.created[0]["properties"] == {"Owner": "Alice"}


# ── relationships ──────────────────────────────────────────────────────────────


def _two_element_document(rel: ExchangeRelationship) -> ExchangeModel:
    return ExchangeModel(
        identifier="m1",
        elements=(_element("e1", "BusinessActor"), _element("e2", "BusinessActor")),
        relationships=(rel,),
    )


def _mapper_with_relationship(mapping: RelationshipMapping, concept_type: str = "Serving") -> FakeMapper:
    return FakeMapper(
        elements={"BusinessActor": ElementMapping(archimate_type="business-actor")},
        relationships={concept_type: mapping},
    )


def test_relationship_created_when_new() -> None:
    mapper = _mapper_with_relationship(RelationshipMapping(connection_type="archimate-serving"))
    writer = FakeWriter()
    document = _two_element_document(_relationship("r1", "Serving", "e1", "e2"))

    report = import_model(document, store=FakeStore(), identity=FakeIdentityStore(), mapper=mapper, writer=writer)

    assert len(report.connections) == 1
    assert report.connections[0].action == "created"
    assert writer.connections_attempted[0]["connection_type"] == "archimate-serving"


def test_relationship_skipped_when_already_present() -> None:
    mapper = _mapper_with_relationship(RelationshipMapping(connection_type="archimate-serving"))
    writer = FakeWriter()
    document = _two_element_document(_relationship("r1", "Serving", "e1", "e2"))

    # First (dry) pass to learn the deterministic ids the fake writer assigns to e1/e2.
    identity = FakeIdentityStore()
    first = import_model(
        document, store=FakeStore(), identity=identity, mapper=mapper, writer=FakeWriter(), commit=True
    )
    source_id = first.entities[0].artifact_id
    target_id = first.entities[1].artifact_id
    conn_id = f"{stable_id(source_id)}---{stable_id(target_id)}@@archimate-serving"

    store = FakeStore(connections=[
        FakeConnectionRecord(artifact_id=conn_id, source=source_id, target=target_id, conn_type="archimate-serving"),
    ])
    report = import_model(document, store=store, identity=identity, mapper=mapper, writer=writer, commit=True)

    assert report.connections[0].action == "skipped"
    assert report.connections[0].artifact_id == conn_id
    assert writer.connections_attempted == []


def test_invalid_relationship_downgrades_to_association() -> None:
    mapper = _mapper_with_relationship(RelationshipMapping(connection_type="archimate-serving"))
    writer = FakeWriter(forbidden_connection_types=frozenset({"archimate-serving"}))
    document = _two_element_document(_relationship("r1", "Serving", "e1", "e2"))

    report = import_model(document, store=FakeStore(), identity=FakeIdentityStore(), mapper=mapper, writer=writer)

    assert report.connections[0].action == "created"
    assert "association" in (report.connections[0].warning or "")
    types_tried = [c["connection_type"] for c in writer.connections_attempted]
    assert types_tried == ["archimate-serving", "archimate-association"]


def test_composition_is_never_downgraded_to_association() -> None:
    mapper = _mapper_with_relationship(
        RelationshipMapping(connection_type="archimate-composition"), concept_type="Composition"
    )
    writer = FakeWriter(forbidden_connection_types=frozenset({"archimate-composition"}))
    document = _two_element_document(_relationship("r1", "Composition", "e1", "e2"))

    report = import_model(document, store=FakeStore(), identity=FakeIdentityStore(), mapper=mapper, writer=writer)

    assert report.connections == ()
    assert len(report.unmappable) == 1
    assert "composition" in report.unmappable[0].reason.lower()
    types_tried = [c["connection_type"] for c in writer.connections_attempted]
    assert types_tried == ["archimate-composition"]


def test_relationship_unmappable_when_endpoint_missing() -> None:
    mapper = FakeMapper(
        elements={},
        relationships={"Serving": RelationshipMapping(connection_type="archimate-serving")},
    )
    document = ExchangeModel(
        identifier="m1",
        elements=(),
        relationships=(_relationship("r1", "Serving", "missing-1", "missing-2"),),
    )

    report = import_model(document, store=FakeStore(), identity=FakeIdentityStore(), mapper=mapper, writer=FakeWriter())

    assert len(report.unmappable) == 1
    assert report.unmappable[0].kind == "relationship"
    assert "not imported" in report.unmappable[0].reason
