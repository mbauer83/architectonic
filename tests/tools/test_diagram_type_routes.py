from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.application.artifacts.repository import ArtifactRepository
from src.application.modeling.artifact_write import generate_diagram_id
from src.application.runtime_catalogs import RuntimeCatalogs
from src.application.verification.artifact_verifier import ArtifactRegistry, ArtifactVerifier
from src.domain.artifact_id import stable_id
from src.domain.ontology_representation.artifact_types import EntityRecord
from src.infrastructure.app_bootstrap import build_module_registry, build_runtime_catalogs
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.diagram_type_registry import diagram_type_domain
from src.infrastructure.rest.routers import state as gui_state
from src.infrastructure.rest.routers.diagrams._context import fuzzy_entity_hits
from src.infrastructure.rest.routers.diagrams._palette import (
    get_diagram_kind_connection_types,
    get_diagram_kind_entity_types,
)
from src.infrastructure.rest.routers.diagrams.router import read_diagram
from src.infrastructure.rest.routers.diagrams.types import (
    list_diagram_types,
    read_diagram_kind_ui_config,
)
from src.infrastructure.write.artifact_write.connection import add_connection
from src.infrastructure.write.artifact_write.diagram import create_diagram
from src.infrastructure.write.artifact_write.diagram_edit import edit_diagram
from src.infrastructure.write.artifact_write.entity import create_entity


@lru_cache(maxsize=1)
def _catalogs() -> RuntimeCatalogs:
    return build_runtime_catalogs(build_module_registry())


@pytest.fixture()
def repo_root(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-TEST" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


def _verifier(repo_root: Path) -> ArtifactVerifier:
    return ArtifactVerifier(ArtifactRegistry(shared_artifact_index(repo_root)), catalogs=_catalogs())


def _entity(artifact_id: str, artifact_type: str, name: str) -> EntityRecord:
    return EntityRecord(
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        name=name,
        version="0.1.0",
        status="draft",
        domain="motivation",
        subdomain=artifact_type,
        path=Path(f"/tmp/{artifact_id}.md"),
        keywords=(),
        extra={},
        content_text=f"{name} {artifact_type}",
        display_blocks={},
        display_label=name,
        display_alias=artifact_id.split(".")[1],
    )


def test_default_registry_registers_matrix_diagram_kind() -> None:
    registry = build_module_registry()

    matrix = registry.find_diagram_type("matrix")

    assert matrix is not None
    assert "goal" in matrix.effective_entity_types()
    assert "archimate-flow" in matrix.effective_connection_types()


def test_default_registry_registers_activity_diagram_kind() -> None:
    registry = build_module_registry()

    activity = registry.find_diagram_type("activity")

    assert activity is not None
    assert activity.ui_config.label == "Activity Diagram"
    assert activity.effective_entity_types() == {}


def test_default_registry_registers_c4_system_context_diagram_type() -> None:
    registry = build_module_registry()

    c4 = registry.find_diagram_type("c4-system-context")

    assert c4 is not None
    assert c4.ui_config.label == "C4 System Context"
    assert "application-component" in c4.effective_entity_types()
    assert "business-actor" in c4.effective_entity_types()


def test_diagram_type_domain_is_registry_derived() -> None:
    assert diagram_type_domain("archimate-business") == "business"
    assert diagram_type_domain("archimate-layered") is None
    assert diagram_type_domain("matrix") is None


def test_diagram_kind_entity_types_endpoint_excludes_internal_types() -> None:
    items = get_diagram_kind_entity_types("archimate-business", catalogs=_catalogs())["items"]

    assert items
    assert any(item["artifact_type"] == "business-actor" for item in items)
    assert all(item["artifact_type"] != "global-artifact-reference" for item in items)


def test_c4_entity_types_endpoint_exposes_mapped_model_types() -> None:
    items = get_diagram_kind_entity_types("c4-system-context", catalogs=_catalogs())["items"]

    assert any(item["artifact_type"] == "application-component" for item in items)
    assert any(item["artifact_type"] == "business-actor" for item in items)
    assert all(item["artifact_type"] != "person" for item in items)


def test_diagram_kind_connection_types_endpoint_exposes_effective_vocabulary() -> None:
    items = get_diagram_kind_connection_types("matrix", catalogs=_catalogs())["items"]

    flow_item = next(item for item in items if item["connection_type"] == "archimate-flow")

    assert flow_item["conn_lang"] == "archimate"
    assert "dynamic" in flow_item["classes"]


def test_diagram_kind_ui_config_endpoint_shape() -> None:
    kinds = list_diagram_types(catalogs=_catalogs())
    activity = read_diagram_kind_ui_config("activity", catalogs=_catalogs())

    assert any(kind["key"] == "activity" and kind["label"] == "Activity Diagram" for kind in kinds)
    assert not {"bowtie", "control-structure", "uca-matrix"} & {kind["key"] for kind in kinds}
    assert "gsn" in {kind["key"] for kind in kinds}
    assert activity["entity_search_filter"] is False
    assert activity["diagram_only_types"][0]["entity_type"] == "swimlane"
    assert activity["type_ui_slots"]["step_editor"] == "activity-steps"


def test_c4_container_ui_config_exposes_shape_enum_for_containers() -> None:
    """Container entity type must expose a shape property with enum for db/queue shape selection."""
    cfg = read_diagram_kind_ui_config("c4-container", catalogs=_catalogs())
    dot = {t["entity_type"]: t for t in cfg.get("diagram_only_types", [])}

    container = dot.get("container", {})
    props = {p["name"]: p for p in container.get("properties", [])}

    assert "shape" in props, "container entity type must have a 'shape' property"
    shape_schema = props["shape"]["schema"]
    assert shape_schema.get("type") == "string"
    enum_vals = shape_schema.get("enum", [])
    assert "" in enum_vals, "empty string (auto-infer) must be in shape enum"
    assert "ContainerDb" in enum_vals
    assert "ContainerQueue" in enum_vals
    assert "Container" in enum_vals


def test_c4_component_ui_config_exposes_shape_enum_for_components() -> None:
    """Component entity type must expose a shape property with db/queue enum values."""
    cfg = read_diagram_kind_ui_config("c4-component", catalogs=_catalogs())
    dot = {t["entity_type"]: t for t in cfg.get("diagram_only_types", [])}

    component = dot.get("component", {})
    props = {p["name"]: p for p in component.get("properties", [])}

    assert "shape" in props, "component entity type must have a 'shape' property"
    shape_schema = props["shape"]["schema"]
    assert shape_schema.get("type") == "string"
    enum_vals = shape_schema.get("enum", [])
    assert "ComponentDb" in enum_vals
    assert "ComponentQueue" in enum_vals
    assert "Component" in enum_vals


def _registry(repo_root: Path) -> ArtifactRegistry:
    return ArtifactRegistry(shared_artifact_index(repo_root))


def _create_model_entity(repo_root: Path, artifact_type: str, name: str) -> str:
    result = create_entity(
        repo_root=repo_root,
        verifier=_verifier(repo_root),
        clear_repo_caches=lambda path: shared_artifact_index(repo_root).apply_file_changes([path]),
        artifact_type=artifact_type,
        name=name,
        summary=None,
        properties=None,
        notes=None,
        keywords=None,
        artifact_id=None,
        version="0.1.0",
        status="draft",
        last_updated=None,
        dry_run=False,
    )
    assert result.wrote is True
    return result.artifact_id


def test_fuzzy_entity_hits_filters_to_accepted_entity_types() -> None:
    requirement = _entity("REQ@1.req.customer-signup", "requirement", "Customer Signup")
    component = _entity("APP@1.app.customer-service", "application-component", "Customer Service")
    repo = SimpleNamespace(list_entities=lambda: [requirement, component])

    hits = fuzzy_entity_hits(
        repo,
        "customer service application-component",
        10,
        set(),
        _catalogs(),
        accepted_entity_types={"application-component"},
    )

    assert [hit["artifact_id"] for hit in hits] == [component.artifact_id]


def test_c4_diagram_auto_populates_model_references(repo_root: Path) -> None:
    """Model-backed mode auto-derives entities and connections from the ArchiMate graph."""
    user_id = _create_model_entity(repo_root, "business-actor", "Customer")
    system_id = _create_model_entity(repo_root, "application-component", "Ordering System")

    conn_result = add_connection(
        repo_root=repo_root,
        registry=_registry(repo_root),
        verifier=_verifier(repo_root),
        clear_repo_caches=lambda path: shared_artifact_index(repo_root).apply_file_changes([path]),
        source_entity=user_id,
        connection_type="archimate-association",
        target_entity=system_id,
        description="Uses the ordering system",
        version="0.1.0",
        status="draft",
        last_updated=None,
        dry_run=False,
    )
    assert conn_result.wrote is True

    diagram_id = generate_diagram_id("c4-system-context", "Ordering Context")
    create_result = create_diagram(
        repo_root=repo_root,
        verifier=_verifier(repo_root),
        clear_repo_caches=lambda _path: None,
        diagram_type="c4-system-context",
        name="Ordering Context",
        puml="",
        artifact_id=diagram_id,
        keywords=None,
        diagram_entities={"_scope_entity_id": system_id},
        diagram_connections=None,
        version="0.1.0",
        status="draft",
        last_updated=None,
        dry_run=False,
    )
    assert create_result.wrote is True, create_result

    repo = ArtifactRepository(shared_artifact_index(repo_root))
    repo.refresh()
    gui_state.init_state(repo, repo_root, None)
    detail = read_diagram(diagram_id, catalogs=_catalogs())

    assert sorted(detail["entity_ids_used"]) == sorted([user_id, system_id])
    assert detail["connection_ids_used"] == [f"{stable_id(user_id)}---{stable_id(system_id)}@@archimate-association"]


def test_diagram_entities_round_trips_create_read_edit_read(repo_root: Path) -> None:
    diagram_id = generate_diagram_id("activity", "Signup Flow")
    puml = f"@startuml {diagram_id}\ntitle Signup Flow\n@enduml\n"
    created_diagram_entities = {
        "swimlanes": [{"id": "sw-1", "label": "Customer"}],
        "steps": [{"type": "action", "id": "act-1", "label": "Submit Request", "lane_id": "sw-1"}],
    }

    create_result = create_diagram(
        repo_root=repo_root,
        verifier=_verifier(repo_root),
        clear_repo_caches=lambda _path: None,
        diagram_type="activity",
        name="Signup Flow",
        puml=puml,
        artifact_id=diagram_id,
        keywords=None,
        diagram_entities=created_diagram_entities,
        version="0.1.0",
        status="draft",
        last_updated=None,
        dry_run=False,
    )
    assert create_result.wrote is True

    repo = ArtifactRepository(shared_artifact_index(repo_root))
    repo.refresh()
    gui_state.init_state(repo, repo_root, None)
    assert read_diagram(diagram_id, catalogs=_catalogs())["diagram_entities"] == created_diagram_entities

    edited_diagram_entities = {
        "swimlanes": [{"id": "sw-2", "label": "System"}],
        "steps": [{"type": "action", "id": "act-2", "label": "Validate", "lane_id": "sw-2"}],
    }
    edit_result = edit_diagram(
        repo_root=repo_root,
        verifier=_verifier(repo_root),
        clear_repo_caches=lambda _path: None,
        artifact_id=diagram_id,
        puml=puml,
        diagram_entities=edited_diagram_entities,
        dry_run=False,
    )
    assert edit_result.wrote is True

    repo.refresh()
    assert read_diagram(diagram_id, catalogs=_catalogs())["diagram_entities"] == edited_diagram_entities
