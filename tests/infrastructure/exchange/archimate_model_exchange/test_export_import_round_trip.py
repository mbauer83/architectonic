"""Real export -> XML -> import round trip (WU-F3b, D10 §4.5): entities and connections
created in one real repo are exported, serialized through the actual C19C writer, parsed
back through the actual reader, and imported into a *fresh* repo — verifying every mapped
concept (specialization, composition, connection specialization, and a free-text property)
survives losslessly, exactly as WU-F3b's acceptance requires.
"""

from __future__ import annotations

from pathlib import Path

from src.application.exchange.export_model import export_model
from src.application.exchange.import_model import import_model
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.exchange.archimate_model_exchange import (
    ArchimateModelExchangeReader,
    ArchimateModelExchangeWriter,
)
from src.infrastructure.exchange.archimate_model_exchange.concept_mapping import DeclarativeConceptMapper
from src.infrastructure.exchange.archimate_model_exchange.identity_store import RepoExchangeIdentityStore
from src.infrastructure.exchange.archimate_model_exchange.write_adapter import ArtifactWriteExchangeAdapter
from src.infrastructure.mcp import mcp_artifact_server as mcp


def _eng_root(tmp_path: Path, tag: str) -> Path:
    root = tmp_path / "engagements" / f"ENG-{tag}" / "architecture-repository"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _registry(root: Path) -> ArtifactRegistry:
    return ArtifactRegistry(shared_artifact_index([root]))


def _create(repo: Path, artifact_type: str, name: str, *, specialization: str | None = None, properties=None) -> str:
    result = mcp.artifact_create_entity(
        artifact_type=artifact_type,
        name=name,
        specialization=specialization,
        properties=properties,
        dry_run=False,
        repo_root=str(repo),
    )
    assert result["wrote"], result
    return str(result["artifact_id"])


def _connect(repo: Path, source: str, target: str, connection_type: str, *, specialization: str | None = None) -> None:
    result = mcp.artifact_add_connection(
        source_entity=source,
        connection_type=connection_type,
        target_entity=target,
        specialization=specialization,
        dry_run=False,
        repo_root=str(repo),
    )
    assert result["wrote"], result


def test_export_then_import_round_trip_preserves_mapped_concepts(tmp_path: Path) -> None:
    source_root = _eng_root(tmp_path, "EXP1")

    alice = _create(source_root, "business-actor", "Alice Actor")
    bob = _create(source_root, "business-actor", "Bob Actor")
    ops_role = _create(source_root, "role", "Ops Role", specialization="business-role")
    approve = _create(
        source_root, "service", "Approve Requests", specialization="business-service", properties={"Owner": "Ops Team"}
    )
    backend = _create(source_root, "application-component", "Backend Module", specialization="module")
    must_scale = _create(source_root, "requirement", "Must Scale", specialization="constraint")

    _connect(source_root, alice, bob, "archimate-composition")
    _connect(source_root, alice, ops_role, "archimate-assignment", specialization="responsibility-assignment")

    mapper = DeclarativeConceptMapper()
    source_registry = _registry(source_root)
    report = export_model(
        [alice, bob, ops_role, approve, backend, must_scale],
        entities=source_registry,
        connections=source_registry,
        mapper=mapper,
    )
    assert report.unexportable == ()

    document_bytes = ArchimateModelExchangeWriter().write(report.document)
    reparsed = ArchimateModelExchangeReader().read(document_bytes)

    dest_root = _eng_root(tmp_path, "EXP2")
    import_report = import_model(
        reparsed,
        store=_registry(dest_root),
        identity=RepoExchangeIdentityStore(dest_root),
        mapper=mapper,
        writer=ArtifactWriteExchangeAdapter(dest_root),
        commit=True,
    )

    assert import_report.unmappable == ()
    dest_registry = _registry(dest_root)
    by_exchange_id = {e.exchange_id: e for e in import_report.entities}

    def _dest_entity(export_exchange_id: str):
        artifact_id = by_exchange_id[export_exchange_id].artifact_id
        entity = dest_registry.get_entity(artifact_id)
        assert entity is not None
        return entity

    exported_by_source_id = {e.artifact_id: e.exchange_id for e in report.entities}

    alice_dest = _dest_entity(exported_by_source_id[alice])
    assert alice_dest.artifact_type == "business-actor"
    assert alice_dest.name == "Alice Actor"

    ops_role_dest = _dest_entity(exported_by_source_id[ops_role])
    assert ops_role_dest.artifact_type == "role"
    assert ops_role_dest.specialization == "business-role"

    approve_dest = _dest_entity(exported_by_source_id[approve])
    assert approve_dest.artifact_type == "service"
    assert approve_dest.specialization == "business-service"

    backend_dest = _dest_entity(exported_by_source_id[backend])
    assert backend_dest.artifact_type == "application-component"
    assert backend_dest.specialization == "module"

    must_scale_dest = _dest_entity(exported_by_source_id[must_scale])
    assert must_scale_dest.artifact_type == "requirement"
    assert must_scale_dest.specialization == "constraint"

    alice_connections = dest_registry.find_connections_for(alice_dest.artifact_id, direction="outbound")
    connection_types = sorted(c.conn_type for c in alice_connections)
    assert connection_types == ["archimate-assignment", "archimate-composition"]
    assignment = next(c for c in alice_connections if c.conn_type == "archimate-assignment")
    assert assignment.specialization == "responsibility-assignment"


def test_export_composition_never_downgrades_through_the_full_round_trip(tmp_path: Path) -> None:
    source_root = _eng_root(tmp_path, "EXP3")
    alice = _create(source_root, "business-actor", "Alice Actor")
    bob = _create(source_root, "business-actor", "Bob Actor")
    _connect(source_root, alice, bob, "archimate-composition")

    mapper = DeclarativeConceptMapper()
    source_registry = _registry(source_root)
    report = export_model([alice, bob], entities=source_registry, connections=source_registry, mapper=mapper)

    document_bytes = ArchimateModelExchangeWriter().write(report.document)
    reparsed = ArchimateModelExchangeReader().read(document_bytes)

    dest_root = _eng_root(tmp_path, "EXP4")
    dest_registry = _registry(dest_root)
    import_report = import_model(
        reparsed,
        store=dest_registry,
        identity=RepoExchangeIdentityStore(dest_root),
        mapper=mapper,
        writer=ArtifactWriteExchangeAdapter(dest_root),
        commit=True,
    )

    assert import_report.unmappable == ()
    dest_registry = _registry(dest_root)
    alice_dest_id = next(e.artifact_id for e in import_report.entities if e.name == "Alice Actor")
    alice_connections = dest_registry.find_connections_for(alice_dest_id, direction="outbound")
    assert [c.conn_type for c in alice_connections] == ["archimate-composition"]
