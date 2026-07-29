"""Tests for admin-mode write isolation and broken-reference cleanup.

Verifies:
- assert_engagement_write_root still rejects enterprise root in all standard functions
- assert_enterprise_write_root rejects engagement root in admin_ops functions
- admin_ops functions succeed with enterprise root (boundary passes)
- cleanup_broken_refs dry-run reports broken GRFs and their connections
- cleanup_broken_refs execute removes broken GRFs and connections
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pytest

from src.infrastructure.artifact_index import shared_artifact_index


@lru_cache(maxsize=1)
def _catalogs():
    from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry  # noqa: PLC0415

    return build_runtime_catalogs(get_module_registry())

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _entity_md(artifact_id: str, artifact_type: str = "requirement", name: str = "Entity") -> str:
    prefix = artifact_id.split("@")[0]
    rand = artifact_id.split(".")[1] if "." in artifact_id else "XXXXXX"
    return f"""\
---
artifact-id: {artifact_id}
artifact-type: {artifact_type}
name: "{name}"
version: 0.1.0
status: active
last-updated: '2026-04-18'
---

<!-- §content -->

## {name}

## Properties

| Attribute | Value |
|---|---|
| (none) | (none) |

<!-- §display -->

### archimate

```yaml
domain: Motivation
element-type: Requirement
label: "{name}"
alias: {prefix}_{rand}
```
"""


def _grf_md(artifact_id: str, name: str, global_id: str) -> str:
    rand = artifact_id.split(".")[1] if "." in artifact_id else "XXXXXX"
    prefix = artifact_id.split("@")[0] if "@" in artifact_id else "GAR"
    return f"""\
---
artifact-id: {artifact_id}
artifact-type: global-artifact-reference
name: "{name}"
version: 0.1.0
status: active
global-artifact-id: {global_id}
global-artifact-type: entity
last-updated: '2026-04-18'
---

<!-- §content -->

## {name}

<!-- §display -->

### archimate

```yaml
domain: ""
element-type: ""
label: "{name}"
alias: {prefix}_{rand}
```
"""


def _outgoing_md(source_id: str, connections: list[tuple[str, str]]) -> str:
    sections = "\n".join(f"### {ct} → {tgt}\n" for ct, tgt in connections)
    return f"""\
---
source-entity: {source_id}
version: 0.1.0
status: active
last-updated: '2026-04-18'
---

<!-- §connections -->

{sections}
"""


@pytest.fixture()
def engagement_root(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


@pytest.fixture()
def enterprise_root(tmp_path: Path) -> Path:
    root = tmp_path / "enterprise-repository"
    (root / "model").mkdir(parents=True)
    return root


# ---------------------------------------------------------------------------
# Boundary guard tests
# ---------------------------------------------------------------------------


class TestBoundaryGuards:
    def test_standard_create_entity_rejects_enterprise_root(self, engagement_root: Path, enterprise_root: Path) -> None:
        from src.application.verification.artifact_verifier import ArtifactVerifier
        from src.infrastructure.write.artifact_write.entity import create_entity

        with pytest.raises(ValueError, match="enterprise"):
            create_entity(
                repo_root=enterprise_root,
                verifier=ArtifactVerifier(None, catalogs=_catalogs()),
                clear_repo_caches=lambda _: None,
                artifact_type="requirement",
                name="Should Fail",
                summary=None,
                properties=None,
                notes=None,
                artifact_id=None,
                version="0.1.0",
                status="draft",
                last_updated=None,
                dry_run=True,
            )

    def test_standard_add_connection_rejects_enterprise_root(self, enterprise_root: Path) -> None:
        from src.application.verification.artifact_verifier import ArtifactRegistry, ArtifactVerifier
        from src.infrastructure.write.artifact_write.connection import add_connection

        with pytest.raises(ValueError, match="enterprise"):
            add_connection(
                repo_root=enterprise_root,
                registry=ArtifactRegistry(shared_artifact_index(enterprise_root)),
                verifier=ArtifactVerifier(None, catalogs=_catalogs()),
                clear_repo_caches=lambda _: None,
                source_entity="X",
                connection_type="archimate-association",
                target_entity="Y",
                description=None,
                version="0.1.0",
                status="active",
                last_updated=None,
                dry_run=True,
            )

    def test_admin_create_entity_rejects_engagement_root(self, engagement_root: Path) -> None:
        from src.application.verification.artifact_verifier import ArtifactVerifier
        from src.infrastructure.write.artifact_write.admin_ops import admin_create_entity

        with pytest.raises(ValueError, match="enterprise"):
            admin_create_entity(
                repo_root=engagement_root,  # wrong root → should be rejected
                verifier=ArtifactVerifier(None, catalogs=_catalogs()),
                clear_repo_caches=lambda _: None,
                artifact_type="requirement",
                name="Should Fail",
                summary=None,
                properties=None,
                notes=None,
                artifact_id=None,
                version="0.1.0",
                status="draft",
                last_updated=None,
                dry_run=True,
            )

    def test_admin_create_entity_accepts_enterprise_root(self, enterprise_root: Path) -> None:
        from src.application.verification.artifact_verifier import ArtifactVerifier
        from src.infrastructure.write.artifact_write.admin_ops import admin_create_entity

        # dry_run=True — no files written, just verifies the guard passes
        result = admin_create_entity(
            repo_root=enterprise_root,
            verifier=ArtifactVerifier(None, catalogs=_catalogs()),
            clear_repo_caches=lambda _: None,
            artifact_type="requirement",
            name="Enterprise Entity",
            summary=None,
            properties=None,
            notes=None,
            artifact_id=None,
            version="0.1.0",
            status="active",
            last_updated=None,
            dry_run=True,
        )
        assert result.wrote is False  # dry_run
        # No exception means the enterprise boundary check passed

    def test_standard_delete_entity_rejects_enterprise_root(self, enterprise_root: Path) -> None:
        from src.application.verification.artifact_verifier import ArtifactRegistry
        from src.infrastructure.write.artifact_write.entity_delete import delete_entity

        with pytest.raises(ValueError, match="enterprise"):
            delete_entity(
                repo_root=enterprise_root,
                registry=ArtifactRegistry(shared_artifact_index(enterprise_root)),
                clear_repo_caches=lambda _: None,
                artifact_id="REQ@2000000000.GloAAA.global-req",
                dry_run=True,
            )

    def test_admin_delete_entity_accepts_enterprise_root(self, enterprise_root: Path) -> None:
        from src.application.verification.artifact_verifier import ArtifactRegistry
        from src.infrastructure.write.artifact_write.admin_ops import admin_delete_entity

        entity_id = "REQ@2000000000.GloAAA.global-req"
        _write(
            enterprise_root / "model" / "motivation" / "requirement" / f"{entity_id}.md",
            _entity_md(entity_id, "requirement", "Global Req"),
        )

        result = admin_delete_entity(
            repo_root=enterprise_root,
            registry=ArtifactRegistry(shared_artifact_index(enterprise_root)),
            clear_repo_caches=lambda _: None,
            artifact_id=entity_id,
            dry_run=True,
        )
        assert result.wrote is False

    def test_standard_delete_diagram_rejects_enterprise_root(self, enterprise_root: Path) -> None:
        from src.infrastructure.write.artifact_write.diagram_delete import delete_diagram

        with pytest.raises(ValueError, match="enterprise"):
            delete_diagram(
                repo_root=enterprise_root,
                clear_repo_caches=lambda _: None,
                artifact_id="diag-1",
                dry_run=True,
            )

    def test_admin_delete_diagram_accepts_enterprise_root(self, enterprise_root: Path) -> None:
        from src.infrastructure.write.artifact_write.admin_ops import admin_delete_diagram

        diag_id = "diag-1"
        _write(
            enterprise_root / "diagram-catalog" / "diagrams" / f"{diag_id}.puml",
            f"""\
---
artifact-id: {diag_id}
artifact-type: diagram
diagram-type: activity
name: "Diag"
version: 0.1.0
status: active
last-updated: '2026-04-20'
---
@startuml
:x;
@enduml
""",
        )

        result = admin_delete_diagram(
            repo_root=enterprise_root,
            clear_repo_caches=lambda _: None,
            artifact_id=diag_id,
            dry_run=True,
        )
        assert result.wrote is False


# ---------------------------------------------------------------------------
# Broken-reference cleanup
# ---------------------------------------------------------------------------


class TestCleanupBrokenRefs:
    def _setup(self, engagement_root: Path, enterprise_root: Path) -> tuple[str, str, str]:
        """Returns (eng_id, grf_id, glo_id_that_no_longer_exists)."""
        eng_id = "REQ@1000000001.EngAaa.eng-req"
        grf_id = "GAR@1000000002.GrfBbb.broken-ref"
        glo_id_deleted = "REQ@2000000001.DelCcc.deleted-req"

        _write(
            engagement_root / "model" / "motivation" / "requirement" / f"{eng_id}.md",
            _entity_md(eng_id, "requirement", "Eng Req"),
        )
        _write(
            engagement_root / "model" / "common" / "global-artifact-reference" / f"{grf_id}.md",
            _grf_md(grf_id, "Broken Ref", glo_id_deleted),
        )
        # Connection from eng entity to the broken GRF
        _write(
            engagement_root / "model" / "motivation" / "requirement" / f"{eng_id}.outgoing.md",
            _outgoing_md(eng_id, [("archimate-association", grf_id)]),
        )
        # Enterprise repo does NOT contain glo_id_deleted
        return eng_id, grf_id, glo_id_deleted

    def test_dry_run_reports_broken_grf(self, engagement_root: Path, enterprise_root: Path) -> None:
        from src.infrastructure.write.artifact_write.cleanup_broken_refs import cleanup_broken_refs

        _, grf_id, _ = self._setup(engagement_root, enterprise_root)

        report = cleanup_broken_refs(engagement_root, enterprise_root, dry_run=True)

        assert grf_id in report.broken_grfs
        assert not report.executed

        kinds = {a.kind for a in report.actions}
        assert "remove_connection" in kinds
        assert "delete_grf" in kinds

    def test_dry_run_does_not_modify_files(self, engagement_root: Path, enterprise_root: Path) -> None:
        from src.infrastructure.write.artifact_write.cleanup_broken_refs import cleanup_broken_refs

        eng_id, grf_id, _ = self._setup(engagement_root, enterprise_root)
        grf_path = engagement_root / "model" / "common" / "global-artifact-reference" / f"{grf_id}.md"
        outgoing_path = engagement_root / "model" / "motivation" / "requirement" / f"{eng_id}.outgoing.md"

        cleanup_broken_refs(engagement_root, enterprise_root, dry_run=True)

        assert grf_path.exists(), "Dry run must not delete GRF"
        assert outgoing_path.exists(), "Dry run must not modify outgoing file"

    def test_execute_removes_broken_grf_and_connections(self, engagement_root: Path, enterprise_root: Path) -> None:
        from src.infrastructure.write.artifact_write.cleanup_broken_refs import cleanup_broken_refs

        eng_id, grf_id, _ = self._setup(engagement_root, enterprise_root)
        grf_path = engagement_root / "model" / "common" / "global-artifact-reference" / f"{grf_id}.md"
        outgoing_path = engagement_root / "model" / "motivation" / "requirement" / f"{eng_id}.outgoing.md"

        report = cleanup_broken_refs(engagement_root, enterprise_root, dry_run=False)

        assert report.executed
        assert not report.errors
        assert not grf_path.exists(), "GRF should be deleted"
        # Outgoing file removed (only connection was to the GRF)
        assert not outgoing_path.exists(), "Outgoing file should be deleted (no connections left)"

    def test_non_broken_grf_not_touched(self, engagement_root: Path, enterprise_root: Path) -> None:
        from src.infrastructure.write.artifact_write.cleanup_broken_refs import cleanup_broken_refs

        # Create a VALID GRF pointing to an enterprise entity that exists
        eng_id = "REQ@1000000003.EngDdd.eng2"
        grf_id = "GAR@1000000004.GrfEee.valid-ref"
        glo_id = "REQ@2000000002.EntFff.real-req"

        _write(
            engagement_root / "model" / "motivation" / "requirement" / f"{eng_id}.md",
            _entity_md(eng_id),
        )
        _write(
            engagement_root / "model" / "common" / "global-artifact-reference" / f"{grf_id}.md",
            _grf_md(grf_id, "Valid Ref", glo_id),
        )
        _write(
            enterprise_root / "model" / "motivation" / "requirement" / f"{glo_id}.md",
            _entity_md(glo_id, "requirement", "Real Global Req"),
        )

        report = cleanup_broken_refs(engagement_root, enterprise_root, dry_run=False)

        assert grf_id not in report.broken_grfs
        grf_path = engagement_root / "model" / "common" / "global-artifact-reference" / f"{grf_id}.md"
        assert grf_path.exists(), "Valid GRF should not be touched"

    def test_no_broken_grfs_reports_empty(self, engagement_root: Path, enterprise_root: Path) -> None:
        from src.infrastructure.write.artifact_write.cleanup_broken_refs import cleanup_broken_refs

        report = cleanup_broken_refs(engagement_root, enterprise_root, dry_run=True)
        assert report.broken_grfs == []
        assert report.actions == []
