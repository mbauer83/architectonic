"""Tests for artifact_write/matrix.py: create_matrix (create, upsert, group-move)."""

from __future__ import annotations

from pathlib import Path

from src.application.verification.artifact_verifier import ArtifactRegistry, ArtifactVerifier
from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.write.artifact_write.matrix import create_matrix


class _Fixture:
    def _eng_root(self, tmp_path: Path) -> Path:
        return tmp_path / "engagements" / "ENG-CMX" / "architecture-repository"

    def _verifier(self, root: Path) -> ArtifactVerifier:
        registry = ArtifactRegistry(shared_artifact_index([root]))
        return ArtifactVerifier(registry, catalogs=build_runtime_catalogs(get_module_registry()))


class TestCreateMatrixDryRun(_Fixture):
    def test_dry_run_returns_write_result(self, tmp_path: Path) -> None:
        root = self._eng_root(tmp_path)
        root.mkdir(parents=True)
        registry = ArtifactRegistry(shared_artifact_index([root]))
        verifier = self._verifier(root)
        md = "| Component | Status |\n|---|---|\n| Alpha | Active |\n"
        result = create_matrix(
            repo_root=root,
            registry=registry,
            verifier=verifier,
            clear_repo_caches=lambda p: None,
            name="Test Matrix",
            matrix_markdown=md,
            artifact_id="MATRIX@1000000240.TstMx.test-matrix",
            dry_run=True,
        )
        assert result.wrote is False
        assert result.content is not None
        assert result.artifact_id == "MATRIX@1000000240.TstMx.test-matrix"

    def test_dry_run_with_entity_id_in_matrix(self, tmp_path: Path) -> None:
        root = self._eng_root(tmp_path)
        eid = "REQ@1000000241.MtxEnt.mtx-ent"
        entity_dir = root / "model" / "motivation" / "requirement"
        entity_dir.mkdir(parents=True)
        (entity_dir / f"{eid}.md").write_text(
            f"---\nartifact-id: {eid}\nname: Matrix Entity\n---\n"
        )
        registry = ArtifactRegistry(shared_artifact_index([root]))
        verifier = self._verifier(root)
        md = f"| {eid} | Active |\n|---|\n"
        result = create_matrix(
            repo_root=root,
            registry=registry,
            verifier=verifier,
            clear_repo_caches=lambda p: None,
            name="Matrix With Entity",
            matrix_markdown=md,
            artifact_id="MATRIX@1000000242.TstMxEnt.test-matrix-ent",
            dry_run=True,
            infer_entity_ids=True,
            auto_link_entity_ids=True,
        )
        assert result.wrote is False
        assert result.content is not None

    def test_dry_run_uses_matrix_verification_not_puml(self, tmp_path: Path) -> None:
        """Regression: matrix content has no @startuml/@enduml — must not run PUML structure checks."""
        root = self._eng_root(tmp_path)
        root.mkdir(parents=True)
        registry = ArtifactRegistry(shared_artifact_index([root]))
        verifier = self._verifier(root)
        md = "| Component | Status |\n|---|---|\n| Alpha | Active |\n"
        result = create_matrix(
            repo_root=root,
            registry=registry,
            verifier=verifier,
            clear_repo_caches=lambda p: None,
            name="Test Matrix",
            matrix_markdown=md,
            artifact_id="MATRIX@1000000243.NoPuml.no-puml",
            dry_run=True,
        )
        assert result.verification is not None
        codes = {i["code"] for i in result.verification["issues"]}
        assert "E304" not in codes  # @startuml missing — would fire if PUML checks ran on this markdown table
        assert "E305" not in codes  # @enduml missing — same

    def test_dry_run_fresh_create_into_group_does_not_claim_a_move(self, tmp_path: Path) -> None:
        """Regression: a brand-new artifact_id with group= set has nothing to relocate —
        commit_diagram_write's `moved` flag is a path comparison, not existence-aware, so a
        naive `if moved:` (borrowed from the always-pre-existing edit_diagram use case) wrongly
        claimed "Will move diagram to group" for a diagram_path that was never on disk."""
        root = self._eng_root(tmp_path)
        root.mkdir(parents=True)
        registry = ArtifactRegistry(shared_artifact_index([root]))
        verifier = self._verifier(root)
        result = create_matrix(
            repo_root=root,
            registry=registry,
            verifier=verifier,
            clear_repo_caches=lambda p: None,
            name="Fresh In Group",
            matrix_markdown="| A |\n|---|\n| 1 |\n",
            artifact_id="MATRIX@1000000246.FreshGrp.fresh-grp",
            group="some-group",
            dry_run=True,
        )
        assert result.wrote is False
        assert not any("Will move diagram" in w for w in result.warnings)


class TestCreateMatrixLiveWriteAndUpsert(_Fixture):
    def test_create_then_edit_in_place_resolves_existing_path(self, tmp_path: Path) -> None:
        """A second create_matrix call with the same artifact_id must edit the existing
        file in place, not write a stray duplicate at the flat/ungrouped path."""
        root = self._eng_root(tmp_path)
        root.mkdir(parents=True)
        registry = ArtifactRegistry(shared_artifact_index([root]))
        verifier = self._verifier(root)
        aid = "MATRIX@1000000244.EditInPlace.edit-in-place"

        first = create_matrix(
            repo_root=root, registry=registry, verifier=verifier, clear_repo_caches=lambda p: None,
            name="V1", matrix_markdown="| A |\n|---|\n| 1 |\n", artifact_id=aid, dry_run=False,
        )
        assert first.wrote is True

        registry2 = ArtifactRegistry(shared_artifact_index([root]))
        second = create_matrix(
            repo_root=root, registry=registry2, verifier=verifier, clear_repo_caches=lambda p: None,
            name="V2", matrix_markdown="| A |\n|---|\n| 2 |\n", artifact_id=aid, dry_run=False,
        )
        assert second.wrote is True
        assert second.path == first.path

        matches = list(root.rglob(f"{aid}.md"))
        assert len(matches) == 1

    def test_group_move_relocates_existing_matrix_file(self, tmp_path: Path) -> None:
        root = self._eng_root(tmp_path)
        root.mkdir(parents=True)
        registry = ArtifactRegistry(shared_artifact_index([root]))
        verifier = self._verifier(root)
        aid = "MATRIX@1000000245.GroupMove.group-move"

        created = create_matrix(
            repo_root=root, registry=registry, verifier=verifier, clear_repo_caches=lambda p: None,
            name="Grouped Matrix", matrix_markdown="| A |\n|---|\n| 1 |\n", artifact_id=aid, dry_run=False,
        )
        assert created.wrote is True
        old_path = created.path

        registry2 = ArtifactRegistry(shared_artifact_index([root]))
        moved = create_matrix(
            repo_root=root, registry=registry2, verifier=verifier, clear_repo_caches=lambda p: None,
            name="Grouped Matrix", matrix_markdown="| A |\n|---|\n| 1 |\n", artifact_id=aid,
            group="some-group", dry_run=False,
        )
        assert moved.wrote is True
        assert moved.path != old_path
        assert "some-group" in moved.path.parts
        assert not old_path.exists()
        assert moved.path.exists()
        assert any("Moved diagram to group" in w for w in moved.warnings)

    def test_fresh_create_directly_into_group_does_not_claim_a_move(self, tmp_path: Path) -> None:
        """Regression: a brand-new matrix created straight into a group has nothing to
        relocate — must not report "Moved diagram to group" (nothing existed beforehand)."""
        root = self._eng_root(tmp_path)
        root.mkdir(parents=True)
        registry = ArtifactRegistry(shared_artifact_index([root]))
        verifier = self._verifier(root)

        result = create_matrix(
            repo_root=root, registry=registry, verifier=verifier, clear_repo_caches=lambda p: None,
            name="Fresh In Group", matrix_markdown="| A |\n|---|\n| 1 |\n",
            artifact_id="MATRIX@1000000247.FreshGrpLive.fresh-grp-live",
            group="some-group", dry_run=False,
        )
        assert result.wrote is True
        assert "some-group" in result.path.parts
        assert not any("Moved diagram to group" in w for w in result.warnings)
