"""Tests for startup_validation.validate_repo_compatibility."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from src.application.startup_validation import RepoCompatibilityError, validate_repo_compatibility
from src.domain.modules.module_registry import ModuleRegistry
from src.domain.modules.module_types import ConnectionTypeName, ElementClassName, EntityTypeName
from src.domain.ontology_representation.artifact_types import ConnectionRecord, DiagramRecord, EntityRecord
from src.domain.ontology_representation.ontology_types import ConnectionTypeInfo, EntityTypeInfo
from src.domain.relationships.permitted_relationships import PermittedRelationshipSet

# ── Stub helpers ──────────────────────────────────────────────────────────────


def _entity_type(name: str) -> EntityTypeInfo:
    return EntityTypeInfo(
        artifact_type=name,
        prefix=name[:3].upper(),
        hierarchy=("test", name),
        classes=(),
        create_when="",
        never_create_when="",
    )


def _conn_type(name: str) -> ConnectionTypeInfo:
    return ConnectionTypeInfo(artifact_type=name, conn_lang="test", classes=())


class _StubOntology:
    def __init__(self, entity_names: list[str], conn_names: list[str], *, name: str = "stub") -> None:
        self._name = name
        self._entity_types: dict[EntityTypeName, EntityTypeInfo] = {
            EntityTypeName(n): _entity_type(n) for n in entity_names
        }
        self._connection_types: dict[ConnectionTypeName, ConnectionTypeInfo] = {
            ConnectionTypeName(n): _conn_type(n) for n in conn_names
        }

    @property
    def name(self) -> str:
        return self._name

    @property
    def entity_types(self) -> Mapping[EntityTypeName, EntityTypeInfo]:
        return self._entity_types

    @property
    def connection_types(self) -> Mapping[ConnectionTypeName, ConnectionTypeInfo]:
        return self._connection_types

    @property
    def permitted_relationships(self) -> PermittedRelationshipSet:
        return PermittedRelationshipSet.empty()

    @property
    def element_classes(self) -> dict:
        return {}

    def entity_types_with_class(self, cls: ElementClassName) -> frozenset[EntityTypeName]:
        return frozenset(n for n, info in self._entity_types.items() if cls in info.classes)

    def connection_types_with_class(self, c: str) -> frozenset[ConnectionTypeName]:
        return frozenset(n for n, info in self._connection_types.items() if c in info.classes)

    def permits_connection(self, src: Any, tgt: Any, conn: Any) -> bool:
        return False


class _StubDiagramType:
    def __init__(self, name: str) -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def accepts_entity_type(self, t: Any) -> bool:
        return True

    def accepts_connection_type(self, t: Any) -> bool:
        return True

    def effective_entity_types(self) -> dict:
        return {}

    def effective_connection_types(self) -> dict:
        return {}

    @property
    def own_entity_types(self) -> dict:
        return {}

    @property
    def own_connection_types(self) -> dict:
        return {}

    @property
    def own_permitted_relationships(self) -> PermittedRelationshipSet:
        return PermittedRelationshipSet.empty()

    @property
    def effective_permitted_relationships(self) -> PermittedRelationshipSet:
        return PermittedRelationshipSet.empty()

    @property
    def element_classes(self) -> dict:
        return {}

    @property
    def primary_ontology(self) -> Any:
        return None

    @property
    def renderer(self) -> Any:
        return None

    @property
    def ui_config(self) -> Any:
        from src.domain.ontology_representation.ontology_protocol import DiagramTypeUiConfig  # noqa: PLC0415

        return DiagramTypeUiConfig(label="Stub")

    def write_guidance(self) -> Any:
        from src.domain.ontology_representation.ontology_protocol import DiagramTypeWriteGuidance  # noqa: PLC0415

        return DiagramTypeWriteGuidance(when_to_use="", when_not_to_use="")


def _make_registry(
    entity_names: list[str],
    conn_names: list[str],
    diagram_kind_names: list[str],
) -> ModuleRegistry:
    reg = ModuleRegistry()
    reg.register_ontology(_StubOntology(entity_names, conn_names))
    for dk in diagram_kind_names:
        reg.register_diagram_type(_StubDiagramType(dk))
    return reg


def _entity(
    artifact_id: str,
    artifact_type: str,
    *,
    path: Path = Path("/tmp/e.md"),
) -> EntityRecord:
    return EntityRecord(
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        name=artifact_id,
        version="0.1.0",
        status="draft",
        domain="test",
        subdomain="",
        path=path,
        keywords=(),
        extra={},
        content_text="",
        display_blocks={},
        display_label=artifact_id,
        display_alias=None,
    )


def _conn(artifact_id: str, conn_type: str) -> ConnectionRecord:
    return ConnectionRecord(
        artifact_id=artifact_id,
        source="a",
        target="b",
        conn_type=conn_type,
        version="0.1.0",
        status="draft",
        path=Path("/tmp/c.outgoing.md"),
        extra={},
        content_text="",
    )


def _diagram(artifact_id: str, diagram_type: str) -> DiagramRecord:
    return DiagramRecord(
        artifact_id=artifact_id,
        artifact_type="diagram",
        name=artifact_id,
        diagram_type=diagram_type,
        version="0.1.0",
        status="draft",
        path=Path(f"/tmp/{artifact_id}.puml"),
        extra={},
    )


class _FakeRepo:
    """Minimal duck-typed repo for validation tests."""

    def __init__(
        self,
        entities: list[EntityRecord] | None = None,
        connections: list[ConnectionRecord] | None = None,
        diagrams: list[DiagramRecord] | None = None,
        repo_roots: list[Path] | None = None,
    ) -> None:
        self._entities = entities or []
        self._connections = connections or []
        self._diagrams = diagrams or []
        self._repo_roots = repo_roots or []

    def list_entities(self, **_: Any) -> list[EntityRecord]:
        return self._entities

    def list_connections(self, **_: Any) -> list[ConnectionRecord]:
        return self._connections

    def list_diagrams(self, **_: Any) -> list[DiagramRecord]:
        return self._diagrams

    @property
    def repo_roots(self) -> list[Path]:
        return self._repo_roots


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestCompatibleRepo:
    def test_empty_repo_passes(self) -> None:
        reg = _make_registry(["driver"], ["uses"], ["archimate-application"])
        repo = _FakeRepo()
        validate_repo_compatibility(repo, reg)  # must not raise

    def test_known_types_pass(self) -> None:
        reg = _make_registry(["driver", "system"], ["uses", "flows"], ["archimate-application"])
        repo = _FakeRepo(
            entities=[_entity("e1", "driver"), _entity("e2", "system")],
            connections=[_conn("c1", "uses"), _conn("c2", "flows")],
            diagrams=[_diagram("d1", "archimate-application")],
        )
        validate_repo_compatibility(repo, reg)  # must not raise


class TestUnknownEntityType:
    def test_reports_unknown_entity_type(self) -> None:
        reg = _make_registry(["driver"], [], [])
        repo = _FakeRepo(entities=[_entity("e1", "unknown-entity")])
        with pytest.raises(RepoCompatibilityError) as exc_info:
            validate_repo_compatibility(repo, reg)
        assert "unknown-entity" in exc_info.value.errors[0]
        assert "e1" in exc_info.value.errors[0]

    def test_deduplicates_per_type(self) -> None:
        reg = _make_registry(["driver"], [], [])
        repo = _FakeRepo(
            entities=[
                _entity("e1", "bad-type"),
                _entity("e2", "bad-type"),
            ]
        )
        with pytest.raises(RepoCompatibilityError) as exc_info:
            validate_repo_compatibility(repo, reg)
        assert len([e for e in exc_info.value.errors if "bad-type" in e]) == 1

    def test_skips_empty_artifact_type(self) -> None:
        reg = _make_registry(["driver"], [], [])
        repo = _FakeRepo(entities=[_entity("e1", "")])
        validate_repo_compatibility(repo, reg)  # must not raise


class TestUnknownConnectionType:
    def test_reports_unknown_conn_type(self) -> None:
        reg = _make_registry([], ["uses"], [])
        repo = _FakeRepo(connections=[_conn("c1", "mystery-conn")])
        with pytest.raises(RepoCompatibilityError) as exc_info:
            validate_repo_compatibility(repo, reg)
        assert "mystery-conn" in exc_info.value.errors[0]
        assert "c1" in exc_info.value.errors[0]


class TestUnknownDiagramType:
    def test_reports_unknown_diagram_kind(self) -> None:
        reg = _make_registry([], [], ["archimate-application"])
        repo = _FakeRepo(diagrams=[_diagram("d1", "legacy-view")])
        with pytest.raises(RepoCompatibilityError) as exc_info:
            validate_repo_compatibility(repo, reg)
        assert "legacy-view" in exc_info.value.errors[0]
        assert "d1" in exc_info.value.errors[0]

    def test_skips_empty_diagram_type(self) -> None:
        reg = _make_registry([], [], ["archimate-application"])
        repo = _FakeRepo(diagrams=[_diagram("d1", "")])
        validate_repo_compatibility(repo, reg)  # must not raise


class TestSchemaFilenames:
    def test_unknown_attribute_schema_type(self, tmp_path: Path) -> None:
        schemata = tmp_path / ".arch-repo" / "schemata"
        schemata.mkdir(parents=True)
        (schemata / "attributes.ghost-type.schema.json").write_text("{}")
        reg = _make_registry(["driver"], [], [])
        repo = _FakeRepo(repo_roots=[tmp_path])
        with pytest.raises(RepoCompatibilityError) as exc_info:
            validate_repo_compatibility(repo, reg)
        errors = exc_info.value.errors
        assert any("ghost-type" in e for e in errors)

    def test_known_attribute_schema_passes(self, tmp_path: Path) -> None:
        schemata = tmp_path / ".arch-repo" / "schemata"
        schemata.mkdir(parents=True)
        (schemata / "attributes.driver.schema.json").write_text("{}")
        reg = _make_registry(["driver"], [], [])
        repo = _FakeRepo(repo_roots=[tmp_path])
        validate_repo_compatibility(repo, reg)  # must not raise

    def test_specialization_attachment_schema_for_known_type_passes(self, tmp_path: Path) -> None:
        """`attributes.{type}.{slug}.schema.json` is the specialization-attachment
        convention — only the type part gates startup; an unknown slug is the verifier's
        orphan-attachment warning, never a startup abort."""
        schemata = tmp_path / ".arch-repo" / "schemata"
        schemata.mkdir(parents=True)
        (schemata / "attributes.driver.regulatory-driver.schema.json").write_text("{}")
        reg = _make_registry(["driver"], [], [])
        repo = _FakeRepo(repo_roots=[tmp_path])
        validate_repo_compatibility(repo, reg)  # must not raise

    def test_specialization_attachment_schema_for_unknown_type_is_error(self, tmp_path: Path) -> None:
        schemata = tmp_path / ".arch-repo" / "schemata"
        schemata.mkdir(parents=True)
        (schemata / "attributes.ghost-type.some-slug.schema.json").write_text("{}")
        reg = _make_registry(["driver"], [], [])
        repo = _FakeRepo(repo_roots=[tmp_path])
        with pytest.raises(RepoCompatibilityError) as exc_info:
            validate_repo_compatibility(repo, reg)
        assert any("ghost-type" in e for e in exc_info.value.errors)

    def test_connection_attachment_schema_for_known_type_passes(self, tmp_path: Path) -> None:
        """`connection-metadata.{type}.{slug}.schema.json` gates on the connection type
        only — the same rule as the entity attachment above, since it is the same
        convention on the other concept kind."""
        schemata = tmp_path / ".arch-repo" / "schemata"
        schemata.mkdir(parents=True)
        (schemata / "connection-metadata.flows.deployment-flow.schema.json").write_text("{}")
        reg = _make_registry([], ["flows"], [])
        repo = _FakeRepo(repo_roots=[tmp_path])
        validate_repo_compatibility(repo, reg)  # must not raise

    def test_connection_attachment_schema_for_unknown_type_is_error(self, tmp_path: Path) -> None:
        schemata = tmp_path / ".arch-repo" / "schemata"
        schemata.mkdir(parents=True)
        (schemata / "connection-metadata.ghost-conn.some-slug.schema.json").write_text("{}")
        reg = _make_registry([], ["flows"], [])
        repo = _FakeRepo(repo_roots=[tmp_path])
        with pytest.raises(RepoCompatibilityError) as exc_info:
            validate_repo_compatibility(repo, reg)
        assert any("ghost-conn" in e for e in exc_info.value.errors)

    def test_unconventional_schema_filename_warns_but_never_aborts(self, tmp_path: Path) -> None:
        """A filename no loader will ever pick up must be surfaced (it is otherwise
        silently dead configuration) without blocking startup."""
        schemata = tmp_path / ".arch-repo" / "schemata"
        schemata.mkdir(parents=True)
        (schemata / "attributes.driver.extra.dots.schema.json").write_text("{}")
        reg = _make_registry(["driver"], [], [])
        repo = _FakeRepo(repo_roots=[tmp_path])
        warnings = validate_repo_compatibility(repo, reg)  # must not raise
        assert any("matches no known convention" in w for w in warnings)

    def test_unknown_connection_metadata_schema_type(self, tmp_path: Path) -> None:
        schemata = tmp_path / ".arch-repo" / "schemata"
        schemata.mkdir(parents=True)
        (schemata / "connection-metadata.phantom-conn.schema.json").write_text("{}")
        reg = _make_registry([], ["uses"], [])
        repo = _FakeRepo(repo_roots=[tmp_path])
        with pytest.raises(RepoCompatibilityError) as exc_info:
            validate_repo_compatibility(repo, reg)
        errors = exc_info.value.errors
        assert any("phantom-conn" in e for e in errors)

    def test_missing_schemata_dir_is_ok(self, tmp_path: Path) -> None:
        reg = _make_registry(["driver"], [], [])
        repo = _FakeRepo(repo_roots=[tmp_path])
        validate_repo_compatibility(repo, reg)  # must not raise


class TestMultiRepoMultiOntology:
    def test_mixed_ontologies_across_two_repos(self) -> None:
        """Content from two different ontologies both registered passes."""
        reg = ModuleRegistry()
        reg.register_ontology(_StubOntology(["driver"], ["uses"], name="archimate"))
        reg.register_ontology(_StubOntology(["block"], ["connects"], name="sysml"))
        reg.register_diagram_type(_StubDiagramType("archimate-application"))
        repo = _FakeRepo(
            entities=[_entity("e1", "driver"), _entity("e2", "block")],
            connections=[_conn("c1", "uses"), _conn("c2", "connects")],
            diagrams=[_diagram("d1", "archimate-application")],
        )
        validate_repo_compatibility(repo, reg)  # must not raise

    def test_unsupported_type_in_one_repo_blocks_startup(self, tmp_path: Path) -> None:
        """A single unsupported entity type aborts startup even with valid types present."""
        reg = _make_registry(["driver"], ["uses"], ["archimate-application"])
        repo = _FakeRepo(
            entities=[_entity("e1", "driver"), _entity("e2", "alien-type")],
        )
        with pytest.raises(RepoCompatibilityError) as exc_info:
            validate_repo_compatibility(repo, reg)
        assert "alien-type" in exc_info.value.errors[0]

    def test_multiple_unknown_types_all_reported(self) -> None:
        reg = _make_registry(["driver"], ["uses"], ["archimate-application"])
        repo = _FakeRepo(
            entities=[_entity("e1", "bad-entity")],
            connections=[_conn("c1", "bad-conn")],
            diagrams=[_diagram("d1", "bad-diagram")],
        )
        with pytest.raises(RepoCompatibilityError) as exc_info:
            validate_repo_compatibility(repo, reg)
        errors = exc_info.value.errors
        assert len(errors) == 3
        types_in_errors = {e.split("'")[1] for e in errors}
        assert types_in_errors == {"bad-entity", "bad-conn", "bad-diagram"}

    def test_real_registry_accepts_archimate_types(self) -> None:
        """The real archimate_4 module registry passes with known entity/connection types."""
        from src.infrastructure.app_bootstrap import build_module_registry

        reg = build_module_registry()
        repo = _FakeRepo(
            entities=[_entity("e1", "driver"), _entity("e2", "application-component")],
            connections=[_conn("c1", "archimate-serving")],
            diagrams=[_diagram("d1", "archimate-application")],
        )
        validate_repo_compatibility(repo, reg)  # must not raise


class TestDisabledModuleTolerance:
    """A type from a known-but-disabled module warns; a type no module declares aborts."""

    def test_disabled_module_diagram_type_warns_not_aborts(self) -> None:
        active = _make_registry(["driver"], ["uses"], ["archimate-application"])
        complete = _make_registry(["driver"], ["uses"], ["archimate-application", "bowtie"])
        repo = _FakeRepo(diagrams=[_diagram("d1", "bowtie")])

        warnings = validate_repo_compatibility(repo, active, complete_registry=complete)

        assert any("bowtie" in w and "disabled module" in w for w in warnings)

    def test_type_unknown_to_every_module_still_aborts(self) -> None:
        active = _make_registry(["driver"], ["uses"], ["archimate-application"])
        complete = _make_registry(["driver"], ["uses"], ["archimate-application", "bowtie"])
        repo = _FakeRepo(diagrams=[_diagram("d1", "totally-unknown")])

        with pytest.raises(RepoCompatibilityError) as exc_info:
            validate_repo_compatibility(repo, active, complete_registry=complete)
        assert "totally-unknown" in exc_info.value.errors[0]

    def test_without_complete_registry_unknown_type_is_a_hard_error(self) -> None:
        active = _make_registry(["driver"], ["uses"], ["archimate-application"])
        repo = _FakeRepo(diagrams=[_diagram("d1", "bowtie")])

        with pytest.raises(RepoCompatibilityError):
            validate_repo_compatibility(repo, active)  # no tolerance without a complete registry


class TestDiagramDerivedProjectionsExempt:
    """Diagram-only projections (node_id-format GSN/bowtie/control-structure) must not abort startup.

    Regression for WU-E5: indexing diagram-only entities/connections by ``node_id`` made their
    free-ontology group-key ``artifact_type`` (``nodes``) and edge ``conn_type``
    (``supported-by``/``in-context-of``) appear in the index. These are diagram-internal
    projections owned by the registered diagram type, not authored model artifacts, so the
    registry-compatibility check must skip them rather than treating the group-keys as unknown types.
    """

    @staticmethod
    def _diagram_entity(artifact_id: str, artifact_type: str, host_diagram_id: str) -> EntityRecord:
        return EntityRecord(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            name=artifact_id,
            version="0.1.0",
            status="draft",
            domain="gsn",
            subdomain=artifact_type,
            path=Path("/tmp/host.puml"),
            keywords=(),
            extra={},
            content_text="",
            display_blocks={},
            display_label=artifact_id,
            display_alias="g1",
            host_diagram_id=host_diagram_id,
        )

    def test_gsn_diagram_only_projections_do_not_abort(self) -> None:
        reg = _make_registry(["driver"], ["uses"], ["gsn"])
        host = "GSN@1.aB.case"
        repo = _FakeRepo(
            entities=[self._diagram_entity(f"{host}#nodes/g1", "nodes", host)],
            connections=[
                _conn(f"{host}#conn/g1:supported-by:s1", "supported-by"),
                _conn(f"{host}#conn/g1:in-context-of:cx1", "in-context-of"),
            ],
            diagrams=[_diagram(host, "gsn")],
        )
        validate_repo_compatibility(repo, reg)  # must not raise

    def test_authored_entity_unknown_type_still_aborts(self) -> None:
        """The exemption is scoped to diagram-derived projections — file-backed artifacts still checked."""
        reg = _make_registry(["driver"], ["uses"], ["gsn"])
        repo = _FakeRepo(entities=[_entity("e1", "unknown-entity")])  # host_diagram_id is None
        with pytest.raises(RepoCompatibilityError) as exc_info:
            validate_repo_compatibility(repo, reg)
        assert "unknown-entity" in exc_info.value.errors[0]
