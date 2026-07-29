"""Tests for the selection-mode stamping step and its deployment-atomic CLI gate:
mechanical classes stamp cleanly and idempotently; a dual-divergent definition is never
guessed — unresolved it blocks the whole commit with the distinct exit status and zero
writes; resolved it gets ONLY its selection_mode written."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]

from src.application.repository_upgrade.steps.viewpoint_selection_mode_stamp import (
    ViewpointSelectionModeStampStep,
)
from src.domain.viewpoints.viewpoint_parsing import viewpoint_catalog_from_mapping
from src.infrastructure.cli.arch_repair_upgrade import (
    EXIT_UNRESOLVED_MIGRATION,
    main_upgrade,
    parse_selection_resolutions,
)
from src.infrastructure.repository_upgrade.fs_adapter import (
    FilesystemRepoUpgradeView,
    FilesystemRepoUpgradeWriter,
)

_FIXTURE = """\
viewpoints:
- slug: scope-only
  version: 1
  name: Scope Only
  scope:
    entity_types: [goal, requirement]
- slug: query-only
  version: 1
  name: Query Only
  query:
    query_schema: 1
    entity_criteria:
      kind: group
      conjunction: and
      children:
      - kind: condition
        attribute: type
        comparator: eq
        value: goal
- slug: dual-equivalent
  version: 1
  name: Dual Equivalent
  scope:
    entity_types: [goal]
  query:
    query_schema: 1
    entity_criteria:
      kind: group
      conjunction: and
      children:
      - kind: condition
        attribute: type
        comparator: in
        value: [goal]
- slug: dual-divergent
  version: 1
  name: Dual Divergent
  scope:
    entity_types: [goal, requirement, principle, outcome, driver]
  query:
    query_schema: 1
    entity_criteria:
      kind: group
      conjunction: and
      children: []
- slug: parameterized
  version: 1
  name: Parameterized
  query:
    query_schema: 1
    parameters:
    - name: anchor
      type: entity-id
      required: true
    entity_criteria:
      kind: group
      conjunction: and
      children:
      - kind: condition
        attribute: id
        comparator: eq
        value:
          from: parameter
          name: anchor
"""


def _repo(root: Path, content: str = _FIXTURE) -> Path:
    (root / ".arch-repo").mkdir(parents=True, exist_ok=True)
    (root / ".arch-repo" / "viewpoints.yaml").write_text(content, encoding="utf-8")
    return root


def _modes(root: Path) -> dict[str, object]:
    loaded: Any = yaml.safe_load((root / ".arch-repo" / "viewpoints.yaml").read_text(encoding="utf-8"))
    return {d["slug"]: d.get("selection_mode") for d in loaded["viewpoints"]}


class TestDetect:
    def test_mechanical_classes_stamp_without_resolutions(self, tmp_path: Path) -> None:
        view = FilesystemRepoUpgradeView(_repo(tmp_path))
        findings = ViewpointSelectionModeStampStep().detect(view)
        by_id = {f.finding_id: f for f in findings}
        assert by_id["selection-mode:scope-only"].auto_migratable
        assert "'scope'" in by_id["selection-mode:scope-only"].description
        for slug in ("query-only", "dual-equivalent", "parameterized"):
            assert by_id[f"selection-mode:{slug}"].auto_migratable
            assert "'query'" in by_id[f"selection-mode:{slug}"].description

    def test_unresolved_divergent_blocks_commit_and_names_both_populations(self, tmp_path: Path) -> None:
        view = FilesystemRepoUpgradeView(_repo(tmp_path))
        findings = ViewpointSelectionModeStampStep().detect(view)
        (unresolved,) = [f for f in findings if f.finding_id == "unresolved-selection:dual-divergent"]
        assert unresolved.blocks_commit
        assert not unresolved.auto_migratable
        assert "scope selects [driver, goal, outcome, principle, requirement]" in unresolved.description
        assert "query selects" in unresolved.description
        assert "--resolve-selection dual-divergent=" in (unresolved.manual_instructions or "")

    def test_resolution_turns_the_divergent_finding_mechanical(self, tmp_path: Path) -> None:
        view = FilesystemRepoUpgradeView(_repo(tmp_path))
        findings = ViewpointSelectionModeStampStep({"dual-divergent": "scope"}).detect(view)
        by_id = {f.finding_id: f for f in findings}
        assert "unresolved-selection:dual-divergent" not in by_id
        assert by_id["selection-mode:dual-divergent"].auto_migratable
        assert "operator-resolved" in by_id["selection-mode:dual-divergent"].description


class TestApply:
    def test_apply_with_resolution_stamps_only_selection_mode(self, tmp_path: Path) -> None:
        root = _repo(tmp_path)
        step = ViewpointSelectionModeStampStep({"dual-divergent": "scope"})
        view = FilesystemRepoUpgradeView(root)
        before = viewpoint_catalog_from_mapping(yaml.safe_load(_FIXTURE))

        applied = step.apply(view, FilesystemRepoUpgradeWriter(root), step.detect(view))

        assert all(a.outcome == "applied" for a in applied)
        assert _modes(root) == {
            "scope-only": "scope",
            "query-only": "query",
            "dual-equivalent": "query",
            "dual-divergent": "scope",
            "parameterized": "query",
        }
        # ONLY selection_mode changed: stripping it yields the original definitions.
        loaded: Any = yaml.safe_load((root / ".arch-repo" / "viewpoints.yaml").read_text(encoding="utf-8"))
        for definition in loaded["viewpoints"]:
            definition.pop("selection_mode")
        assert viewpoint_catalog_from_mapping(loaded) == before

        # Idempotent: nothing left to detect; re-apply writes identical bytes.
        assert step.detect(FilesystemRepoUpgradeView(root)) == []
        first = (root / ".arch-repo" / "viewpoints.yaml").read_bytes()
        step.apply(FilesystemRepoUpgradeView(root), FilesystemRepoUpgradeWriter(root), [])
        assert (root / ".arch-repo" / "viewpoints.yaml").read_bytes() == first


class TestCliAtomicity:
    def test_commit_with_unresolved_divergence_exits_distinctly_and_writes_nothing(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path)
        before = (root / ".arch-repo" / "viewpoints.yaml").read_bytes()

        code = main_upgrade(["--repo-root", str(root), "--commit"])

        assert code == EXIT_UNRESOLVED_MIGRATION
        assert (root / ".arch-repo" / "viewpoints.yaml").read_bytes() == before
        captured = capsys.readouterr()
        assert "UNRESOLVED MIGRATION" in captured.err
        assert "dual-divergent" in captured.err

    def test_parse_selection_resolutions(self) -> None:
        assert parse_selection_resolutions(["a=scope", "b=query"]) == {"a": "scope", "b": "query"}
        with pytest.raises(SystemExit):
            parse_selection_resolutions(["a=banana"])
        with pytest.raises(SystemExit):
            parse_selection_resolutions(["no-separator"])
