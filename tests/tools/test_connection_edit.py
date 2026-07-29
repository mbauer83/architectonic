"""Tests for connection_edit.py: edit_connection, remove_connection, edit_connection_associations.

Uses fake registry/verifier with real .outgoing.md files in tmp_path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.verification.artifact_verifier_types import VerificationResult
from src.infrastructure.write.artifact_write.connection_edit import (
    edit_connection,
    edit_connection_associations,
    remove_connection,
)

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeRegistry:
    def __init__(self, entity_id: str, entity_file: Path) -> None:
        self._map = {entity_id: entity_file}
        self.repo_roots = [entity_file.parent]

    def find_file_by_id(self, eid: str) -> Path | None:
        return self._map.get(eid)


class _FakeVerifier:
    def __init__(self, *, valid: bool = True) -> None:
        self._valid = valid

    def verify_outgoing_file(self, path: Path) -> VerificationResult:
        res = VerificationResult(path=path, file_type="connection")
        return res  # no issues → valid=True by default


class _FailingVerifier:
    def verify_outgoing_file(self, path: Path) -> VerificationResult:
        from src.application.verification.artifact_verifier_types import Issue

        res = VerificationResult(path=path, file_type="connection")
        res.issues.append(Issue(severity="error", code="E999", message="forced fail", location=""))
        return res


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_OUTGOING_CONTENT = """\
---
artifact-id: ENT@1.src.entity
version: 0.1.0
status: draft
---

<!-- §connections -->

### uses → ENT@2.tgt.entity

Original description.
"""


@pytest.fixture()
def repo(tmp_path: Path):
    model = tmp_path / "engagements" / "ENG-T" / "architecture-repository" / "model" / "domain"
    model.mkdir(parents=True)
    entity_file = model / "ENT@1.src.entity.md"
    entity_file.write_text("---\nname: Source\n---\n")
    outgoing = model / "ENT@1.src.entity.outgoing.md"
    outgoing.write_text(_OUTGOING_CONTENT)
    repo_root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    return repo_root, entity_file, outgoing


# ---------------------------------------------------------------------------
# edit_connection — dry_run
# ---------------------------------------------------------------------------


class TestEditConnectionDryRun:
    def test_dry_run_returns_not_wrote(self, repo) -> None:
        repo_root, entity_file, outgoing = repo
        registry = _FakeRegistry("ENT@1.src.entity", entity_file)
        verifier = _FakeVerifier()
        result = edit_connection(
            repo_root=repo_root,
            registry=registry,
            verifier=verifier,
            clear_repo_caches=lambda p: None,
            source_entity="ENT@1.src.entity",
            target_entity="ENT@2.tgt.entity",
            connection_type="uses",
            description="New description",
            dry_run=True,
        )
        assert result.wrote is False
        assert result.content is not None
        assert "New description" in result.content

    def test_dry_run_preserves_src_multiplicity_unset(self, repo) -> None:
        repo_root, entity_file, outgoing = repo
        registry = _FakeRegistry("ENT@1.src.entity", entity_file)
        verifier = _FakeVerifier()
        result = edit_connection(
            repo_root=repo_root,
            registry=registry,
            verifier=verifier,
            clear_repo_caches=lambda p: None,
            source_entity="ENT@1.src.entity",
            target_entity="ENT@2.tgt.entity",
            connection_type="uses",
            description=None,
            dry_run=True,
        )
        assert result.wrote is False

    def test_raises_when_connection_not_found(self, repo) -> None:
        repo_root, entity_file, outgoing = repo
        registry = _FakeRegistry("ENT@1.src.entity", entity_file)
        verifier = _FakeVerifier()
        with pytest.raises(ValueError, match="not found"):
            edit_connection(
                repo_root=repo_root,
                registry=registry,
                verifier=verifier,
                clear_repo_caches=lambda p: None,
                source_entity="ENT@1.src.entity",
                target_entity="ENT@99.missing.entity",
                connection_type="uses",
                dry_run=True,
            )

    def test_raises_when_no_outgoing_file(self, tmp_path: Path) -> None:
        repo_root = tmp_path
        entity_file = tmp_path / "entity.md"
        entity_file.write_text("---\n---\n")
        registry = _FakeRegistry("ENT@1.x.y", entity_file)
        with pytest.raises(ValueError, match="No outgoing file"):
            edit_connection(
                repo_root=repo_root,
                registry=registry,
                verifier=_FakeVerifier(),
                clear_repo_caches=lambda p: None,
                source_entity="ENT@1.x.y",
                target_entity="ENT@2.a.b",
                connection_type="uses",
                dry_run=True,
            )


# ---------------------------------------------------------------------------
# edit_connection — real write
# ---------------------------------------------------------------------------


class TestEditConnectionWrite:
    def test_writes_when_verification_passes(self, repo) -> None:
        repo_root, entity_file, outgoing = repo
        registry = _FakeRegistry("ENT@1.src.entity", entity_file)
        cleared: list[Path] = []
        result = edit_connection(
            repo_root=repo_root,
            registry=registry,
            verifier=_FakeVerifier(),
            clear_repo_caches=cleared.append,
            source_entity="ENT@1.src.entity",
            target_entity="ENT@2.tgt.entity",
            connection_type="uses",
            description="Updated description",
            dry_run=False,
        )
        assert result.wrote is True
        assert outgoing.read_text().count("Updated description") == 1
        assert cleared

    def test_rollback_when_verification_fails(self, repo) -> None:
        repo_root, entity_file, outgoing = repo
        original_content = outgoing.read_text()
        registry = _FakeRegistry("ENT@1.src.entity", entity_file)
        result = edit_connection(
            repo_root=repo_root,
            registry=registry,
            verifier=_FailingVerifier(),
            clear_repo_caches=lambda p: None,
            source_entity="ENT@1.src.entity",
            target_entity="ENT@2.tgt.entity",
            connection_type="uses",
            description="Should rollback",
            dry_run=False,
        )
        assert result.wrote is False
        assert outgoing.read_text() == original_content


# ---------------------------------------------------------------------------
# remove_connection
# ---------------------------------------------------------------------------


class TestRemoveConnection:
    def test_dry_run_last_connection_reports_delete(self, repo) -> None:
        repo_root, entity_file, outgoing = repo
        registry = _FakeRegistry("ENT@1.src.entity", entity_file)
        result = remove_connection(
            repo_root=repo_root,
            registry=registry,
            verifier=_FakeVerifier(),
            clear_repo_caches=lambda p: None,
            source_entity="ENT@1.src.entity",
            target_entity="ENT@2.tgt.entity",
            connection_type="uses",
            dry_run=True,
        )
        assert result.wrote is False
        assert "deleted" in (result.content or "").lower()

    def test_real_delete_when_last_connection(self, repo) -> None:
        repo_root, entity_file, outgoing = repo
        registry = _FakeRegistry("ENT@1.src.entity", entity_file)
        result = remove_connection(
            repo_root=repo_root,
            registry=registry,
            verifier=_FakeVerifier(),
            clear_repo_caches=lambda p: None,
            source_entity="ENT@1.src.entity",
            target_entity="ENT@2.tgt.entity",
            connection_type="uses",
            dry_run=False,
        )
        assert result.wrote is True
        assert not outgoing.exists()

    def test_dry_run_with_remaining_connections(self, tmp_path: Path) -> None:
        model = tmp_path / "engagements" / "ENG-T" / "architecture-repository" / "model"
        model.mkdir(parents=True)
        entity_file = model / "ENT@1.src.entity.md"
        entity_file.write_text("---\nname: Source\n---\n")
        outgoing = model / "ENT@1.src.entity.outgoing.md"
        outgoing.write_text(
            "---\nartifact-id: ENT@1.src.entity\nversion: 0.1.0\nstatus: draft\n---\n\n"
            "<!-- §connections -->\n\n"
            "### uses → ENT@2.tgt.entity\n\nDesc A.\n\n"
            "### assigned-to → ENT@3.other.entity\n\nDesc B.\n"
        )
        repo_root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
        registry = _FakeRegistry("ENT@1.src.entity", entity_file)
        result = remove_connection(
            repo_root=repo_root,
            registry=registry,
            verifier=_FakeVerifier(),
            clear_repo_caches=lambda p: None,
            source_entity="ENT@1.src.entity",
            target_entity="ENT@2.tgt.entity",
            connection_type="uses",
            dry_run=True,
        )
        assert result.wrote is False
        assert result.content is not None
        assert "ENT@3.other.entity" in result.content

    def test_raises_when_connection_not_found(self, repo) -> None:
        repo_root, entity_file, outgoing = repo
        registry = _FakeRegistry("ENT@1.src.entity", entity_file)
        with pytest.raises(ValueError, match="not found"):
            remove_connection(
                repo_root=repo_root,
                registry=registry,
                verifier=_FakeVerifier(),
                clear_repo_caches=lambda p: None,
                source_entity="ENT@1.src.entity",
                target_entity="ENT@99.ghost.entity",
                connection_type="uses",
                dry_run=True,
            )


# ---------------------------------------------------------------------------
# edit_connection_associations
# ---------------------------------------------------------------------------


class TestEditConnectionAssociations:
    def test_dry_run_adds_association(self, repo) -> None:
        repo_root, entity_file, outgoing = repo
        registry = _FakeRegistry("ENT@1.src.entity", entity_file)
        result = edit_connection_associations(
            repo_root=repo_root,
            registry=registry,
            verifier=_FakeVerifier(),
            clear_repo_caches=lambda p: None,
            source_entity="ENT@1.src.entity",
            connection_type="uses",
            target_entity="ENT@2.tgt.entity",
            add_entities=["ENT@3.assoc.entity"],
            dry_run=True,
        )
        assert result.wrote is False
        assert result.content is not None
        assert "ENT@3.assoc.entity" in result.content

    def test_dry_run_removes_association(self, repo) -> None:
        repo_root, entity_file, outgoing = repo
        outgoing.write_text(
            "---\nartifact-id: ENT@1.src.entity\nversion: 0.1.0\nstatus: draft\n---\n\n"
            "<!-- §connections -->\n\n"
            "### uses → ENT@2.tgt.entity\n\n<!-- §assoc ENT@3.assoc.entity -->\n"
        )
        registry = _FakeRegistry("ENT@1.src.entity", entity_file)
        result = edit_connection_associations(
            repo_root=repo_root,
            registry=registry,
            verifier=_FakeVerifier(),
            clear_repo_caches=lambda p: None,
            source_entity="ENT@1.src.entity",
            connection_type="uses",
            target_entity="ENT@2.tgt.entity",
            remove_entities=["ENT@3.assoc.entity"],
            dry_run=True,
        )
        assert result.wrote is False
        assert "ENT@3.assoc.entity" not in (result.content or "")

    def test_write_adds_and_verifies(self, repo) -> None:
        repo_root, entity_file, outgoing = repo
        registry = _FakeRegistry("ENT@1.src.entity", entity_file)
        cleared: list[Path] = []
        result = edit_connection_associations(
            repo_root=repo_root,
            registry=registry,
            verifier=_FakeVerifier(),
            clear_repo_caches=cleared.append,
            source_entity="ENT@1.src.entity",
            connection_type="uses",
            target_entity="ENT@2.tgt.entity",
            add_entities=["ENT@5.new.entity"],
            dry_run=False,
        )
        assert result.wrote is True
        assert cleared

    def test_raises_when_connection_not_found(self, repo) -> None:
        repo_root, entity_file, outgoing = repo
        registry = _FakeRegistry("ENT@1.src.entity", entity_file)
        with pytest.raises(ValueError, match="not found"):
            edit_connection_associations(
                repo_root=repo_root,
                registry=registry,
                verifier=_FakeVerifier(),
                clear_repo_caches=lambda p: None,
                source_entity="ENT@1.src.entity",
                connection_type="uses",
                target_entity="ENT@99.ghost.entity",
                dry_run=True,
            )


# ---------------------------------------------------------------------------
# Additional branch coverage
# ---------------------------------------------------------------------------


class TestEditConnectionMultiplicities:
    def test_set_src_multiplicity(self, repo) -> None:
        repo_root, entity_file, outgoing = repo
        registry = _FakeRegistry("ENT@1.src.entity", entity_file)
        result = edit_connection(
            repo_root=repo_root,
            registry=registry,
            verifier=_FakeVerifier(),
            clear_repo_caches=lambda p: None,
            source_entity="ENT@1.src.entity",
            target_entity="ENT@2.tgt.entity",
            connection_type="uses",
            src_multiplicity="1:n",
            dry_run=True,
        )
        assert result.wrote is False
        assert "1:n" in (result.content or "")

    def test_clear_src_multiplicity(self, repo) -> None:
        repo_root, entity_file, outgoing = repo
        # First add a multiplicity
        outgoing.write_text(
            "---\nartifact-id: ENT@1.src.entity\nversion: 0.1.0\nstatus: draft\n---\n\n"
            "<!-- §connections -->\n\n### uses [1:n] → ENT@2.tgt.entity\n\nDesc.\n"
        )
        registry = _FakeRegistry("ENT@1.src.entity", entity_file)
        result = edit_connection(
            repo_root=repo_root,
            registry=registry,
            verifier=_FakeVerifier(),
            clear_repo_caches=lambda p: None,
            source_entity="ENT@1.src.entity",
            target_entity="ENT@2.tgt.entity",
            connection_type="uses",
            src_multiplicity="",
            dry_run=True,
        )
        assert result.wrote is False

    def test_set_tgt_multiplicity(self, repo) -> None:
        repo_root, entity_file, outgoing = repo
        registry = _FakeRegistry("ENT@1.src.entity", entity_file)
        result = edit_connection(
            repo_root=repo_root,
            registry=registry,
            verifier=_FakeVerifier(),
            clear_repo_caches=lambda p: None,
            source_entity="ENT@1.src.entity",
            target_entity="ENT@2.tgt.entity",
            connection_type="uses",
            tgt_multiplicity="0:1",
            dry_run=True,
        )
        assert "0:1" in (result.content or "")


class TestRemoveConnectionWithRemaining:
    def test_real_write_with_remaining_connections(self, tmp_path: Path) -> None:
        model = tmp_path / "engagements" / "ENG-T" / "architecture-repository" / "model"
        model.mkdir(parents=True)
        entity_file = model / "ENT@1.src.entity.md"
        entity_file.write_text("---\nname: Source\n---\n")
        outgoing = model / "ENT@1.src.entity.outgoing.md"
        outgoing.write_text(
            "---\nartifact-id: ENT@1.src.entity\nversion: 0.1.0\nstatus: draft\n---\n\n"
            "<!-- §connections -->\n\n"
            "### uses → ENT@2.tgt.entity\n\nDesc A.\n\n"
            "### assigned-to → ENT@3.other.entity\n\nDesc B.\n"
        )
        repo_root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
        registry = _FakeRegistry("ENT@1.src.entity", entity_file)
        result = remove_connection(
            repo_root=repo_root,
            registry=registry,
            verifier=_FakeVerifier(),
            clear_repo_caches=lambda p: None,
            source_entity="ENT@1.src.entity",
            target_entity="ENT@2.tgt.entity",
            connection_type="uses",
            dry_run=False,
        )
        assert result.wrote is True
        assert outgoing.exists()
        assert "ENT@3.other.entity" in outgoing.read_text()
        assert "ENT@2.tgt.entity" not in outgoing.read_text()

    def test_raises_when_no_outgoing_file(self, tmp_path: Path) -> None:
        entity_file = tmp_path / "entity.md"
        entity_file.write_text("---\n---\n")
        registry = _FakeRegistry("ENT@1.x.y", entity_file)
        with pytest.raises(ValueError, match="No outgoing file"):
            remove_connection(
                repo_root=tmp_path,
                registry=registry,
                verifier=_FakeVerifier(),
                clear_repo_caches=lambda p: None,
                source_entity="ENT@1.x.y",
                target_entity="ENT@2.a.b",
                connection_type="uses",
                dry_run=True,
            )


class TestEditConnectionAssociationsNoOutgoing:
    def test_raises_when_no_outgoing_file(self, tmp_path: Path) -> None:
        entity_file = tmp_path / "entity.md"
        entity_file.write_text("---\n---\n")
        registry = _FakeRegistry("ENT@1.x.y", entity_file)
        with pytest.raises(ValueError, match="No outgoing file"):
            edit_connection_associations(
                repo_root=tmp_path,
                registry=registry,
                verifier=_FakeVerifier(),
                clear_repo_caches=lambda p: None,
                source_entity="ENT@1.x.y",
                connection_type="uses",
                target_entity="ENT@2.a.b",
                dry_run=True,
            )
