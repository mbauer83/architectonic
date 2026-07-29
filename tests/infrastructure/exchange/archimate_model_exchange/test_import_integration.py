"""Real-repo integration for the exchange import use case (WU-F3a): entities and
connections actually land on disk through the ordinary ``artifact_write`` layer,
composition is never downgraded even when the write layer rejects it, and re-importing
the same document is idempotent (no duplicate entities or connections).
"""

from __future__ import annotations

from pathlib import Path

from src.application.exchange.document import ExchangeElement, ExchangeModel, ExchangeRelationship, LangString
from src.application.exchange.import_model import import_model
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.exchange.archimate_model_exchange.concept_mapping import DeclarativeConceptMapper
from src.infrastructure.exchange.archimate_model_exchange.identity_store import RepoExchangeIdentityStore
from src.infrastructure.exchange.archimate_model_exchange.write_adapter import ArtifactWriteExchangeAdapter


def _eng_root(tmp_path: Path, tag: str) -> Path:
    root = tmp_path / "engagements" / f"ENG-{tag}" / "architecture-repository"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _store(root: Path):
    return ArtifactRegistry(shared_artifact_index([root]))


def _two_actor_document(relationship_concept_type: str = "Serving") -> ExchangeModel:
    return ExchangeModel(
        identifier="m1",
        elements=(
            ExchangeElement(identifier="e1", concept_type="BusinessActor", names=(LangString("Actor One"),)),
            ExchangeElement(identifier="e2", concept_type="BusinessActor", names=(LangString("Actor Two"),)),
        ),
        relationships=(
            ExchangeRelationship(identifier="r1", concept_type=relationship_concept_type, source="e1", target="e2"),
        ),
    )


def test_commit_creates_real_entity_and_connection_files(tmp_path: Path) -> None:
    root = _eng_root(tmp_path, "IMP1")
    document = _two_actor_document()

    report = import_model(
        document,
        store=_store(root),
        identity=RepoExchangeIdentityStore(root),
        mapper=DeclarativeConceptMapper(),
        writer=ArtifactWriteExchangeAdapter(root),
        commit=True,
    )

    assert [e.action for e in report.entities] == ["created", "created"]
    assert report.connections[0].action == "created"
    for entity in report.entities:
        assert (root / "model").exists()
        registry = _store(root)
        assert registry.get_entity(entity.artifact_id) is not None
    registry = _store(root)
    assert registry.get_connection(report.connections[0].artifact_id) is not None


def test_reimport_is_idempotent_via_the_association_fallback_path(tmp_path: Path) -> None:
    # Serving is not permitted between two BusinessActors, so every import downgrades
    # this relationship to association; the idempotence check here exercises the
    # "pre-existing association" branch, not the direct connection-type match.
    root = _eng_root(tmp_path, "IMP2")
    document = _two_actor_document()
    identity = RepoExchangeIdentityStore(root)

    def _run() -> object:
        return import_model(
            document,
            store=_store(root),
            identity=identity,
            mapper=DeclarativeConceptMapper(),
            writer=ArtifactWriteExchangeAdapter(root),
            commit=True,
        )

    first = _run()
    registry = _store(root)
    entity_count_after_first = len(registry.entity_ids())
    connection_count_after_first = len(registry.connection_ids())

    second = _run()
    registry = _store(root)
    entity_count_after_second = len(registry.entity_ids())
    connection_count_after_second = len(registry.connection_ids())

    assert [e.action for e in second.entities] == ["updated", "updated"]
    assert second.connections[0].action == "skipped"
    assert [e.artifact_id for e in first.entities] == [e.artifact_id for e in second.entities]
    assert first.connections[0].artifact_id == second.connections[0].artifact_id
    assert entity_count_after_second == entity_count_after_first
    assert connection_count_after_second == connection_count_after_first


def test_reimport_is_idempotent_via_the_direct_match_path(tmp_path: Path) -> None:
    # Aggregation is directly permitted between two BusinessActors (no downgrade), so
    # this exercises the plain "same connection type already exists" idempotence branch.
    root = _eng_root(tmp_path, "IMP2b")
    document = _two_actor_document(relationship_concept_type="Aggregation")
    identity = RepoExchangeIdentityStore(root)

    def _run():
        return import_model(
            document,
            store=_store(root),
            identity=identity,
            mapper=DeclarativeConceptMapper(),
            writer=ArtifactWriteExchangeAdapter(root),
            commit=True,
        )

    first = _run()
    second = _run()

    assert first.connections[0].action == "created"
    assert first.connections[0].artifact_id.endswith("@@archimate-aggregation")
    assert second.connections[0].action == "skipped"
    assert second.connections[0].artifact_id == first.connections[0].artifact_id
    registry = _store(root)
    assert len(registry.connection_ids()) == 1


def test_composition_is_never_downgraded_against_real_permitted_relationships(tmp_path: Path) -> None:
    root = _eng_root(tmp_path, "IMP3")
    # Stakeholder -> BusinessActor permits only association per the real ArchiMate 4
    # relationship rules (verified live against the runtime catalogs): composition here
    # must be reported as unmappable, never silently created as association.
    document = ExchangeModel(
        identifier="m1",
        elements=(
            ExchangeElement(identifier="e1", concept_type="Stakeholder", names=(LangString("Sponsor"),)),
            ExchangeElement(identifier="e2", concept_type="BusinessActor", names=(LangString("Actor"),)),
        ),
        relationships=(
            ExchangeRelationship(identifier="r1", concept_type="Composition", source="e1", target="e2"),
        ),
    )

    report = import_model(
        document,
        store=_store(root),
        identity=RepoExchangeIdentityStore(root),
        mapper=DeclarativeConceptMapper(),
        writer=ArtifactWriteExchangeAdapter(root),
        commit=True,
    )

    assert report.connections == ()
    assert len(report.unmappable) == 1
    assert "composition" in report.unmappable[0].reason.lower()
    registry = _store(root)
    assert len(registry.connection_ids()) == 0


def test_invalid_relationship_really_downgrades_to_association_on_disk(tmp_path: Path) -> None:
    root = _eng_root(tmp_path, "IMP4")
    # Stakeholder -> BusinessActor also rejects Serving; unlike composition this one is
    # expected to fall back to a real, persisted association connection.
    document = ExchangeModel(
        identifier="m1",
        elements=(
            ExchangeElement(identifier="e1", concept_type="Stakeholder", names=(LangString("Sponsor"),)),
            ExchangeElement(identifier="e2", concept_type="BusinessActor", names=(LangString("Actor"),)),
        ),
        relationships=(
            ExchangeRelationship(identifier="r1", concept_type="Serving", source="e1", target="e2"),
        ),
    )

    report = import_model(
        document,
        store=_store(root),
        identity=RepoExchangeIdentityStore(root),
        mapper=DeclarativeConceptMapper(),
        writer=ArtifactWriteExchangeAdapter(root),
        commit=True,
    )

    assert report.unmappable == ()
    assert report.connections[0].action == "created"
    assert "association" in (report.connections[0].warning or "")
    registry = _store(root)
    connection = registry.get_connection(report.connections[0].artifact_id)
    assert connection is not None
    assert connection.conn_type == "archimate-association"
