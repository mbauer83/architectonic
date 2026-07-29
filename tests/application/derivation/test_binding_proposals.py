"""Tests for binding_proposals: build_entity_proposals, build_connection_proposals,
entity_binding_guidance."""

from __future__ import annotations

from src.application.derivation.binding_proposals import (
    build_connection_proposals,
    build_entity_proposals,
    entity_binding_guidance,
)
from src.domain.diagrams.allowed_bindings import AllowedBindingsSpec, ConnectionBindingSpec, EntityBindingSpec
from tests.application.derivation._fixtures import FakeQuery, _connection, _entity


def _spec() -> AllowedBindingsSpec:
    return AllowedBindingsSpec(
        entity={
            "container": EntityBindingSpec(
                correspondence_kinds=("represents", "refines", "traces-to"),
                default_correspondence_kind="represents",
                target_forms=("entity-id", "diagram-local"),
            ),
            "person": EntityBindingSpec(
                correspondence_kinds=("represents", "traces-to"),
                default_correspondence_kind="represents",
                target_forms=("entity-id",),
            ),
        },
        connection={
            "c4-uses": ConnectionBindingSpec(
                target_connection_types=("serving", "flow", "access"),
                target_connection_classes=("dependency", "flow"),
                correspondence_kinds=("abstracts", "represents", "traces-to"),
                target_forms=("connection-id", "connection-ids"),
                default_correspondence_kind="abstracts",
            ),
        },
    )


def test_build_entity_proposals_known_entity() -> None:
    query = FakeQuery(entities=[_entity("APP@123", "application-component")])
    spec = _spec()
    proposals = build_entity_proposals(["APP@123"], spec, query)

    assert len(proposals) == 1
    p = proposals[0]
    assert p["model_entity_id"] == "APP@123"
    assert p["model_name"] == "APP@123"
    assert p["model_type"] == "application-component"
    dtypes = {c["diagram_entity_type"] for c in p["candidate_diagram_types"]}  # type: ignore[union-attr]
    assert "container" in dtypes
    assert "person" in dtypes


def test_build_entity_proposals_unknown_entity() -> None:
    query = FakeQuery()
    spec = _spec()
    proposals = build_entity_proposals(["MISSING@999"], spec, query)

    assert len(proposals) == 1
    p = proposals[0]
    assert p["model_entity_id"] == "MISSING@999"
    assert "model_name" not in p
    assert isinstance(p["candidate_diagram_types"], list)


def test_build_entity_proposals_empty_ids() -> None:
    assert build_entity_proposals([], _spec(), FakeQuery()) == []


def test_build_entity_proposals_default_kind() -> None:
    query = FakeQuery(entities=[_entity("APP@1", "application-component")])
    spec = _spec()
    proposals = build_entity_proposals(["APP@1"], spec, query)
    container_entry = next(
        c for c in proposals[0]["candidate_diagram_types"]  # type: ignore[index]
        if c["diagram_entity_type"] == "container"
    )
    assert container_entry["default_correspondence_kind"] == "represents"
    assert "refines" in container_entry["admissible_correspondence_kinds"]


def test_build_connection_proposals_known_connection() -> None:
    conn = _connection("APP@1---APP@2@@serving", "APP@1", "APP@2", "serving")
    query = FakeQuery(connections=[conn])
    spec = _spec()
    proposals = build_connection_proposals(["APP@1---APP@2@@serving"], spec, query)

    assert len(proposals) == 1
    p = proposals[0]
    assert p["model_connection_id"] == "APP@1---APP@2@@serving"
    assert p["model_connection_type"] == "serving"
    dtypes = {c["diagram_connection_type"] for c in p["candidate_diagram_types"]}  # type: ignore[union-attr]
    assert "c4-uses" in dtypes


def test_build_connection_proposals_type_filter() -> None:
    conn = _connection("A---B@@composition", "A", "B", "composition")
    query = FakeQuery(connections=[conn])
    spec = _spec()
    proposals = build_connection_proposals(["A---B@@composition"], spec, query)
    assert proposals[0]["candidate_diagram_types"] == []


def test_build_connection_proposals_default_kind() -> None:
    conn = _connection("APP@1---APP@2@@serving", "APP@1", "APP@2", "serving")
    query = FakeQuery(connections=[conn])
    proposals = build_connection_proposals(["APP@1---APP@2@@serving"], _spec(), query)
    c4_entry = proposals[0]["candidate_diagram_types"][0]  # type: ignore[index]
    assert c4_entry["default_correspondence_kind"] == "abstracts"


def test_entity_binding_guidance_returns_entity_id_forms_only() -> None:
    spec = AllowedBindingsSpec(
        entity={
            "container": EntityBindingSpec(
                correspondence_kinds=("represents",),
                default_correspondence_kind="represents",
                target_forms=("entity-id",),
            ),
            "note": EntityBindingSpec(
                correspondence_kinds=("traces-to",),
                default_correspondence_kind="traces-to",
                target_forms=("diagram-local",),
            ),
        },
        connection={},
    )
    result = entity_binding_guidance("application-component", spec)
    assert any(c["diagram_entity_type"] == "container" for c in result)
    assert not any(c["diagram_entity_type"] == "note" for c in result)


def test_entity_binding_guidance_empty_spec() -> None:
    assert entity_binding_guidance("anything", AllowedBindingsSpec.empty()) == []
