"""Tests for the group meta-ontology rename step: detect/apply/idempotence, scoping to the
legacy value only, quoted-value handling, and the step-conformance harness."""

from __future__ import annotations

from pathlib import Path

import yaml

from src.application.repository_upgrade.apply import apply_repository
from src.application.repository_upgrade.evaluate import evaluate_repository
from src.application.repository_upgrade.registry import StepRegistry
from src.application.repository_upgrade.steps.group_meta_ontology_rename import GroupMetaOntologyRenameStep
from src.infrastructure.repository_upgrade.fs_adapter import (
    FilesystemRepoUpgradeView,
    FilesystemRepoUpgradeWriter,
)
from tests.support.repository_upgrade_conformance import assert_step_preserves_unknown_content

_GROUPS_WITH_LEGACY = """\
model-projects:
- slug: autocam
  id: GRP@1782219058.rSYVsT
  name: autoCAM
  description: Keep this description untouched — archimate-next appears here too
  meta_ontology: archimate-next
diagram-collections:
- slug: autocam
  id: GRP@1782278447.nvuXSU
  name: autoCAM
document-collections: []
"""


def _registry() -> StepRegistry:
    reg = StepRegistry()
    reg.register(GroupMetaOntologyRenameStep())
    return reg


def _setup(tmp_path: Path, content: str) -> Path:
    arch_repo = tmp_path / ".arch-repo"
    arch_repo.mkdir(parents=True, exist_ok=True)
    path = arch_repo / "groups.yaml"
    path.write_text(content, encoding="utf-8")
    return path


def test_detects_legacy_meta_ontology(tmp_path: Path) -> None:
    _setup(tmp_path, _GROUPS_WITH_LEGACY)
    view = FilesystemRepoUpgradeView(tmp_path)

    (finding,) = GroupMetaOntologyRenameStep().detect(view)

    assert finding.auto_migratable is True
    assert finding.severity == "error"
    assert finding.location == ".arch-repo/groups.yaml"
    assert "1 model-project group" in finding.description


def test_silent_when_no_groups_file(tmp_path: Path) -> None:
    view = FilesystemRepoUpgradeView(tmp_path)
    assert GroupMetaOntologyRenameStep().detect(view) == []


def test_silent_when_already_current(tmp_path: Path) -> None:
    _setup(tmp_path, _GROUPS_WITH_LEGACY.replace("meta_ontology: archimate-next", "meta_ontology: archimate-4"))
    view = FilesystemRepoUpgradeView(tmp_path)
    assert GroupMetaOntologyRenameStep().detect(view) == []


def test_apply_renames_only_the_meta_ontology_value_not_the_description(tmp_path: Path) -> None:
    path = _setup(tmp_path, _GROUPS_WITH_LEGACY)
    view = FilesystemRepoUpgradeView(tmp_path)
    writer = FilesystemRepoUpgradeWriter(tmp_path)

    findings = GroupMetaOntologyRenameStep().detect(view)
    GroupMetaOntologyRenameStep().apply(view, writer, findings)

    rewritten = path.read_text(encoding="utf-8")
    loaded = yaml.safe_load(rewritten)
    assert loaded["model-projects"][0]["meta_ontology"] == "archimate-4"
    # The identical token inside the free-text description is NOT touched — the rewrite is
    # scoped to the `meta_ontology:` key, not a blind string replace.
    assert "archimate-next appears here too" in rewritten


def test_apply_handles_quoted_value(tmp_path: Path) -> None:
    quoted = _GROUPS_WITH_LEGACY.replace("meta_ontology: archimate-next", 'meta_ontology: "archimate-next"')
    path = _setup(tmp_path, quoted)
    view = FilesystemRepoUpgradeView(tmp_path)
    writer = FilesystemRepoUpgradeWriter(tmp_path)

    findings = GroupMetaOntologyRenameStep().detect(view)
    GroupMetaOntologyRenameStep().apply(view, writer, findings)

    assert yaml.safe_load(path.read_text(encoding="utf-8"))["model-projects"][0]["meta_ontology"] == "archimate-4"


def test_apply_is_idempotent(tmp_path: Path) -> None:
    _setup(tmp_path, _GROUPS_WITH_LEGACY)
    view = FilesystemRepoUpgradeView(tmp_path)
    writer = FilesystemRepoUpgradeWriter(tmp_path)
    registry = _registry()

    first = apply_repository(view, writer, registry=registry, software_version="0.0.0-test")
    second = apply_repository(view, writer, registry=registry, software_version="0.0.0-test")

    assert first.applied_steps_after == ("group-meta-ontology-archimate-4-rename",)
    assert second.results == ()


def test_dry_run_never_mutates(tmp_path: Path) -> None:
    path = _setup(tmp_path, _GROUPS_WITH_LEGACY)
    view = FilesystemRepoUpgradeView(tmp_path)
    before = path.read_text(encoding="utf-8")

    report = evaluate_repository(view, registry=_registry(), software_version="0.0.0-test")

    assert report.unapplied_required_steps == ("group-meta-ontology-archimate-4-rename",)
    assert path.read_text(encoding="utf-8") == before


def test_step_conformance_harness(tmp_path: Path) -> None:
    _setup(tmp_path, _GROUPS_WITH_LEGACY)
    view = FilesystemRepoUpgradeView(tmp_path)
    writer = FilesystemRepoUpgradeWriter(tmp_path)

    assert_step_preserves_unknown_content(
        GroupMetaOntologyRenameStep(),
        view,
        writer,
        location=".arch-repo/groups.yaml",
        unknown_marker="id: GRP@1782219058.rSYVsT",
    )
