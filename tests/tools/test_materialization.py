"""Tests for materialization.py — diagram element → model artifact binding.

Covers the error paths and dry-run paths in materialize_entity and
materialize_connection. Commit paths (real writes) are out of scope here.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from src.infrastructure.write.artifact_write.materialization import (
    DiagramElementRef,
    diagram_entity_exists,
    materialize_connection,
    materialize_entity,
)

# ── helpers ───────────────────────────────────────────────────────────────────


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _diagram_puml(
    artifact_id: str,
    *,
    entities: list[dict] | None = None,
    connections: list[dict] | None = None,
    bindings: list[dict] | None = None,
) -> str:
    fm: dict = {
        "artifact-id": artifact_id,
        "artifact-type": "diagram",
        "name": "Test Diagram",
        "version": "0.1.0",
        "status": "draft",
        "diagram-type": "archimate-application",
        "last-updated": "2026-01-01",
    }
    if entities:
        fm["diagram-entities"] = {"container": entities}
    if connections:
        fm["connections"] = connections
    if bindings:
        fm["bindings"] = bindings
    yaml_text = yaml.safe_dump(fm, sort_keys=False).strip()
    return f"---\n{yaml_text}\n---\n@startuml\n@enduml\n"


DIAG_ID = "DIAG@1000000080.MatTest.mat-test"
DIAG_CONN_ID = "DIAG@1000000081.MatConn.mat-conn"



def _verifier(repo_root: Path):
    from src.application.verification.artifact_verifier import ArtifactVerifier
    from src.application.verification.artifact_verifier_registry import ArtifactRegistry
    from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry
    from src.infrastructure.artifact_index import shared_artifact_index

    registry = ArtifactRegistry(shared_artifact_index([repo_root]))
    return ArtifactVerifier(registry, catalogs=build_runtime_catalogs(get_module_registry()))


# ── diagram_entity_exists multi-group branch ──────────────────────────────────


class TestDiagramEntityExistsMultiGroup:
    def test_second_group_match_covers_loop_continuation(self) -> None:
        fm = {
            "diagram-entities": {
                "group_a": [{"id": "a1", "label": "A1"}],
                "group_b": [{"id": "b1", "label": "B1"}],
            }
        }
        assert diagram_entity_exists(fm, "b1") is True

    def test_no_match_in_multiple_groups_returns_false(self) -> None:
        fm = {
            "diagram-entities": {
                "group_a": [{"id": "a1"}],
                "group_b": [{"id": "b1"}],
            }
        }
        assert diagram_entity_exists(fm, "c1") is False


# ── materialize_entity — error paths ─────────────────────────────────────────


class TestMaterializeEntityErrors:
    def test_diagram_not_found(self, tmp_path: Path) -> None:
        repo_root = tmp_path / "engagements" / "ENG-MAT" / "architecture-repository"
        repo_root.mkdir(parents=True)
        verifier = _verifier(repo_root)
        ref = DiagramElementRef(
            diagram_id="DIAG@9.ZZZ.no-such",
            diagram_element_id="elem1",
        )
        result = materialize_entity(
            repo_root=repo_root,
            verifier=verifier,
            clear_repo_caches=lambda p: None,
            ref=ref,
            artifact_type="requirement",
            name="Test Entity",
        )
        assert result.wrote is False
        assert result.error is not None
        assert "not found" in result.error

    def test_element_not_in_diagram(self, tmp_path: Path) -> None:
        repo_root = tmp_path / "engagements" / "ENG-MAT2" / "architecture-repository"
        diagrams_dir = repo_root / "diagram-catalog" / "diagrams"
        _write(
            diagrams_dir / f"{DIAG_ID}.puml",
            _diagram_puml(DIAG_ID, entities=[{"id": "other_elem", "label": "Other"}]),
        )
        verifier = _verifier(repo_root)
        ref = DiagramElementRef(diagram_id=DIAG_ID, diagram_element_id="missing_elem")
        result = materialize_entity(
            repo_root=repo_root,
            verifier=verifier,
            clear_repo_caches=lambda p: None,
            ref=ref,
            artifact_type="requirement",
            name="Test Entity",
        )
        assert result.wrote is False
        assert result.error is not None
        assert "not found" in result.error


class TestMaterializeEntityDryRun:
    def test_dry_run_returns_proposed_entity_id(self, tmp_path: Path) -> None:
        repo_root = tmp_path / "engagements" / "ENG-MAT3" / "architecture-repository"
        diagrams_dir = repo_root / "diagram-catalog" / "diagrams"
        _write(
            diagrams_dir / f"{DIAG_ID}.puml",
            _diagram_puml(
                DIAG_ID,
                entities=[
                    {"id": "elem1", "label": "Elem One"},
                    {"id": "elem2", "label": "Elem Two"},
                ],
            ),
        )
        verifier = _verifier(repo_root)
        ref = DiagramElementRef(diagram_id=DIAG_ID, diagram_element_id="elem1")
        result = materialize_entity(
            repo_root=repo_root,
            verifier=verifier,
            clear_repo_caches=lambda p: None,
            ref=ref,
            artifact_type="requirement",
            name="Materialized Requirement",
            dry_run=True,
        )
        assert result.wrote is False
        assert result.proposed_entity_id is not None
        assert result.error is None

    def test_dry_run_includes_proposed_binding(self, tmp_path: Path) -> None:
        repo_root = tmp_path / "engagements" / "ENG-MAT4" / "architecture-repository"
        diagrams_dir = repo_root / "diagram-catalog" / "diagrams"
        _write(
            diagrams_dir / f"{DIAG_ID}.puml",
            _diagram_puml(DIAG_ID, entities=[{"id": "elem1", "label": "Elem"}]),
        )
        verifier = _verifier(repo_root)
        ref = DiagramElementRef(diagram_id=DIAG_ID, diagram_element_id="elem1")
        result = materialize_entity(
            repo_root=repo_root,
            verifier=verifier,
            clear_repo_caches=lambda p: None,
            ref=ref,
            artifact_type="requirement",
            name="Materialized Req B",
            dry_run=True,
        )
        assert result.wrote is False
        assert result.proposed_binding
        assert result.proposed_binding["subject"]["id"] == "elem1"


# ── materialize_connection — error paths ──────────────────────────────────────


class TestMaterializeConnectionErrors:
    def test_diagram_not_found(self, tmp_path: Path) -> None:
        repo_root = tmp_path / "engagements" / "ENG-MCN" / "architecture-repository"
        repo_root.mkdir(parents=True)
        verifier = _verifier(repo_root)
        ref = DiagramElementRef(
            diagram_id="DIAG@9.ZZZ.no-such",
            diagram_element_id="conn1",
            diagram_element_kind="connection",
        )
        from src.application.verification.artifact_verifier_registry import ArtifactRegistry
        from src.infrastructure.artifact_index import shared_artifact_index

        registry = ArtifactRegistry(shared_artifact_index([repo_root]))
        result = materialize_connection(
            repo_root=repo_root,
            registry=registry,
            verifier=verifier,
            clear_repo_caches=lambda p: None,
            ref=ref,
            connection_type="archimate-association",
        )
        assert result.wrote is False
        assert "not found" in (result.error or "")

    def test_connection_not_in_diagram(self, tmp_path: Path) -> None:
        repo_root = tmp_path / "engagements" / "ENG-MCN2" / "architecture-repository"
        diagrams_dir = repo_root / "diagram-catalog" / "diagrams"
        _write(
            diagrams_dir / f"{DIAG_CONN_ID}.puml",
            _diagram_puml(DIAG_CONN_ID),  # no connections key
        )
        verifier = _verifier(repo_root)
        ref = DiagramElementRef(
            diagram_id=DIAG_CONN_ID,
            diagram_element_id="missing_conn",
            diagram_element_kind="connection",
        )
        from src.application.verification.artifact_verifier_registry import ArtifactRegistry
        from src.infrastructure.artifact_index import shared_artifact_index

        registry = ArtifactRegistry(shared_artifact_index([repo_root]))
        result = materialize_connection(
            repo_root=repo_root,
            registry=registry,
            verifier=verifier,
            clear_repo_caches=lambda p: None,
            ref=ref,
            connection_type="archimate-association",
        )
        assert result.wrote is False
        assert "not found" in (result.error or "")

    def test_source_entity_no_binding(self, tmp_path: Path) -> None:
        repo_root = tmp_path / "engagements" / "ENG-MCN3" / "architecture-repository"
        diagrams_dir = repo_root / "diagram-catalog" / "diagrams"
        _write(
            diagrams_dir / f"{DIAG_CONN_ID}.puml",
            _diagram_puml(
                DIAG_CONN_ID,
                connections=[{"id": "conn1", "source": "src_elem", "target": "tgt_elem"}],
                # No bindings
            ),
        )
        verifier = _verifier(repo_root)
        ref = DiagramElementRef(
            diagram_id=DIAG_CONN_ID,
            diagram_element_id="conn1",
            diagram_element_kind="connection",
        )
        from src.application.verification.artifact_verifier_registry import ArtifactRegistry
        from src.infrastructure.artifact_index import shared_artifact_index

        registry = ArtifactRegistry(shared_artifact_index([repo_root]))
        result = materialize_connection(
            repo_root=repo_root,
            registry=registry,
            verifier=verifier,
            clear_repo_caches=lambda p: None,
            ref=ref,
            connection_type="archimate-association",
        )
        assert result.wrote is False
        assert "src_elem" in (result.error or "") or "binding" in (result.error or "")

    def test_target_entity_no_binding(self, tmp_path: Path) -> None:
        repo_root = tmp_path / "engagements" / "ENG-MCN4" / "architecture-repository"
        diagrams_dir = repo_root / "diagram-catalog" / "diagrams"
        _write(
            diagrams_dir / f"{DIAG_CONN_ID}.puml",
            _diagram_puml(
                DIAG_CONN_ID,
                connections=[{"id": "conn1", "source": "src_elem", "target": "tgt_elem"}],
                bindings=[{
                    "id": "bind-src",
                    "subject": {"kind": "entity", "id": "src_elem"},
                    "correspondence_kind": "represents",
                    "target": {"entity_id": "REQ@1.AA.src"},
                }],
            ),
        )
        verifier = _verifier(repo_root)
        ref = DiagramElementRef(
            diagram_id=DIAG_CONN_ID,
            diagram_element_id="conn1",
            diagram_element_kind="connection",
        )
        from src.application.verification.artifact_verifier_registry import ArtifactRegistry
        from src.infrastructure.artifact_index import shared_artifact_index

        registry = ArtifactRegistry(shared_artifact_index([repo_root]))
        result = materialize_connection(
            repo_root=repo_root,
            registry=registry,
            verifier=verifier,
            clear_repo_caches=lambda p: None,
            ref=ref,
            connection_type="archimate-association",
        )
        assert result.wrote is False
        assert "tgt_elem" in (result.error or "") or "binding" in (result.error or "")


class TestMaterializeConnectionDryRun:
    def test_dry_run_returns_proposed_connection_id(self, tmp_path: Path) -> None:
        repo_root = tmp_path / "engagements" / "ENG-MCN5" / "architecture-repository"
        diagrams_dir = repo_root / "diagram-catalog" / "diagrams"
        _write(
            diagrams_dir / f"{DIAG_CONN_ID}.puml",
            _diagram_puml(
                DIAG_CONN_ID,
                connections=[{"id": "conn1", "source": "src_elem", "target": "tgt_elem"}],
                bindings=[
                    {
                        "id": "bind-src",
                        "subject": {"kind": "entity", "id": "src_elem"},
                        "correspondence_kind": "represents",
                        "target": {"entity_id": "REQ@1.AA.src"},
                    },
                    {
                        "id": "bind-tgt",
                        "subject": {"kind": "entity", "id": "tgt_elem"},
                        "correspondence_kind": "represents",
                        "target": {"entity_id": "REQ@2.BB.tgt"},
                    },
                ],
            ),
        )
        verifier = _verifier(repo_root)
        ref = DiagramElementRef(
            diagram_id=DIAG_CONN_ID,
            diagram_element_id="conn1",
            diagram_element_kind="connection",
        )
        from src.application.verification.artifact_verifier_registry import ArtifactRegistry
        from src.infrastructure.artifact_index import shared_artifact_index

        registry = ArtifactRegistry(shared_artifact_index([repo_root]))
        result = materialize_connection(
            repo_root=repo_root,
            registry=registry,
            verifier=verifier,
            clear_repo_caches=lambda p: None,
            ref=ref,
            connection_type="archimate-association",
            dry_run=True,
        )
        assert result.wrote is False
        assert result.proposed_connection_id is not None
        assert result.error is None
