"""Tests for group_registry_validation.py.

Covers: validate_and_repair_group_registry (YAML error, schema error,
bad meta_ontology, orphan detection/auto-register, read-only mode),
GroupRegistryError, and _register_orphan.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.application.group_registry_validation import (
    GroupRegistryError,
    _register_orphan,
    validate_and_repair_group_registry,
)
from src.domain.repository.groups import GroupRegistry


def _git_init(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True, capture_output=True)
    (path / ".gitkeep").write_text("")
    subprocess.run(["git", "add", ".gitkeep"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)


def _validate(
    repo: Path,
    *,
    read_only: bool = False,
    valid_meta_ontologies: frozenset[str] = frozenset({"archimate-4"}),
) -> list[str]:
    return validate_and_repair_group_registry(
        repo,
        valid_meta_ontologies=valid_meta_ontologies,
        read_only=read_only,
    )


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    _git_init(root)
    return root


class TestGroupRegistryError:
    def test_stores_errors_list(self) -> None:
        exc = GroupRegistryError(["error 1", "error 2"])
        assert exc.errors == ["error 1", "error 2"]

    def test_str_joins_errors(self) -> None:
        exc = GroupRegistryError(["e1", "e2"])
        assert "e1" in str(exc)
        assert "e2" in str(exc)


class TestValidateAndRepairGroupRegistry:
    def test_valid_empty_registry_returns_empty_messages(self, repo: Path) -> None:
        messages = _validate(repo)
        assert messages == []

    def test_invalid_yaml_raises_group_registry_error(self, repo: Path) -> None:
        arch_dir = repo / ".arch-repo"
        arch_dir.mkdir(parents=True, exist_ok=True)
        (arch_dir / "groups.yaml").write_text(": bad: yaml: [\n", encoding="utf-8")
        with pytest.raises(GroupRegistryError, match="invalid YAML"):
            _validate(repo)

    def test_invalid_meta_ontology_raises(self, repo: Path) -> None:
        from src.infrastructure.write.artifact_write.group_ops import group_create  # noqa: PLC0415

        group_create(repo, axis="model-project", slug="bad-mo", name="Bad MO", meta_ontology="invalid-ontology")
        with pytest.raises(GroupRegistryError, match="meta_ontology"):
            _validate(repo)

    def test_valid_meta_ontology_passes(self, repo: Path) -> None:
        from src.infrastructure.write.artifact_write.group_ops import group_create  # noqa: PLC0415

        group_create(repo, axis="model-project", slug="valid-mo", name="Valid MO", meta_ontology="archimate-4")
        messages = _validate(repo)
        assert messages == []

    def test_disabled_meta_ontology_is_rejected(self, repo: Path) -> None:
        from src.infrastructure.write.artifact_write.group_ops import group_create  # noqa: PLC0415

        group_create(repo, axis="model-project", slug="sysml-mo", name="SysML MO", meta_ontology="sysml-v2")
        with pytest.raises(GroupRegistryError, match="sysml-v2") as exc_info:
            _validate(repo, valid_meta_ontologies=frozenset({"archimate-4"}))
        assert "valid values: 'archimate-4'" in str(exc_info.value)

    def test_enabled_meta_ontology_alias_passes(self, repo: Path) -> None:
        from src.infrastructure.write.artifact_write.group_ops import group_create  # noqa: PLC0415

        group_create(repo, axis="model-project", slug="sysml-mo", name="SysML MO", meta_ontology="sysml-v2")
        messages = _validate(repo, valid_meta_ontologies=frozenset({"archimate-4", "sysml-v2"}))
        assert messages == []

    def test_orphaned_project_dir_auto_registered(self, repo: Path) -> None:
        orphan_dir = repo / "projects" / "orphan-project" / "model"
        orphan_dir.mkdir(parents=True)
        (orphan_dir / "entity.yaml").write_text("# orphan file")
        messages = _validate(repo, read_only=False)
        assert any("orphan-project" in m for m in messages)
        from src.application.group_registry import load_group_registry  # noqa: PLC0415

        registry = load_group_registry(repo)
        assert registry.find("model-project", "orphan-project") is not None

    def test_orphaned_dir_warns_in_read_only_mode(self, repo: Path) -> None:
        orphan_dir = repo / "projects" / "ro-orphan" / "model"
        orphan_dir.mkdir(parents=True)
        (orphan_dir / "entity.yaml").write_text("# orphan file")
        messages = _validate(repo, read_only=True)
        assert any("ro-orphan" in m for m in messages)
        # In read-only mode, no registry change
        from src.application.group_registry import load_group_registry  # noqa: PLC0415

        registry = load_group_registry(repo)
        assert registry.find("model-project", "ro-orphan") is None

    def test_orphaned_diagram_collection_auto_registered(self, repo: Path) -> None:
        dc_dir = repo / "diagram-catalog" / "diagrams" / "orphan-dc"
        dc_dir.mkdir(parents=True)
        (dc_dir / "diagram.puml").write_text("@startuml\n@enduml\n")
        messages = _validate(repo, read_only=False)
        assert any("orphan-dc" in m for m in messages)

    def test_orphaned_document_collection_auto_registered(self, repo: Path) -> None:
        doc_dir = repo / "docs" / "adr" / "orphan-doc"
        doc_dir.mkdir(parents=True)
        (doc_dir / "decision.md").write_text("---\nartifact-id: DOC@1.x\n---\n")
        messages = _validate(repo, read_only=False)
        assert any("orphan-doc" in m for m in messages)

    def test_empty_project_dir_not_auto_registered(self, repo: Path) -> None:
        empty_dir = repo / "projects" / "empty-proj"
        empty_dir.mkdir(parents=True)
        messages = _validate(repo, read_only=False)
        assert not any("empty-proj" in m for m in messages)

    def test_uncategorized_dir_skipped(self, repo: Path) -> None:
        unc_dir = repo / "projects" / "uncategorized"
        unc_dir.mkdir(parents=True)
        (unc_dir / "entity.yaml").write_text("# file")
        messages = _validate(repo, read_only=False)
        # uncategorized should not be auto-registered
        assert not any("uncategorized" in m and "Auto-registered" in m for m in messages)


class TestRegisterOrphan:
    def test_registers_model_project(self) -> None:
        reg = GroupRegistry()
        updated = _register_orphan(reg, "model-project", "new-proj")
        assert updated.find("model-project", "new-proj") is not None

    def test_registers_diagram_collection(self) -> None:
        reg = GroupRegistry()
        updated = _register_orphan(reg, "diagram-collection", "new-dc")
        assert updated.find("diagram-collection", "new-dc") is not None

    def test_registers_document_collection(self) -> None:
        reg = GroupRegistry()
        updated = _register_orphan(reg, "document-collection", "new-doc")
        assert updated.find("document-collection", "new-doc") is not None

    def test_slug_titleized_as_name(self) -> None:
        reg = GroupRegistry()
        updated = _register_orphan(reg, "model-project", "my-project")
        entry = updated.find("model-project", "my-project")
        assert entry is not None
        assert entry.name == "My Project"
