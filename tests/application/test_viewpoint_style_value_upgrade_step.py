"""Tests for the style-value normalization step: silent on absent/malformed files and on
definitions already inside the validated vocabulary; fires per definition carrying
legacy values and rewrites them to 'neutral' (their previously rendered color) while
leaving valid tokens and '#rrggbb' colors untouched."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from src.application.repository_upgrade.steps.viewpoint_style_value_upgrade import (
    ViewpointStyleValueUpgradeStep,
)
from src.infrastructure.repository_upgrade.fs_adapter import (
    FilesystemRepoUpgradeView,
    FilesystemRepoUpgradeWriter,
)

_LEGACY = """\
viewpoints:
- slug: lifecycle-heat
  version: 1
  name: Lifecycle Heat
  presentation:
    representation: exploration
    styling_rules:
    - capability: node_color
      match_criteria:
        kind: group
        conjunction: and
        children: []
      value: highlight
    - capability: node_color
      mode: scale
      scale_attribute: derived.impact-distance
      scale_tokens:
      - cool
      - '#ff0000'
    default_style:
      node_color: grayish
- slug: already-valid
  version: 1
  name: Already Valid
  presentation:
    representation: exploration
    styling_rules:
    - capability: node_color
      match_criteria:
        kind: group
        conjunction: and
        children: []
      value: '#336699'
"""


def _view(root: Path, content: str | None) -> FilesystemRepoUpgradeView:
    (root / ".arch-repo").mkdir(parents=True, exist_ok=True)
    if content is not None:
        (root / ".arch-repo" / "viewpoints.yaml").write_text(content, encoding="utf-8")
    return FilesystemRepoUpgradeView(root)


def test_silent_when_file_absent(tmp_path: Path) -> None:
    assert ViewpointStyleValueUpgradeStep().detect(_view(tmp_path, None)) == []


def test_silent_on_malformed_file(tmp_path: Path) -> None:
    view = _view(tmp_path, "viewpoints:\n  - slug: [unterminated\n")
    assert ViewpointStyleValueUpgradeStep().detect(view) == []


def test_fires_once_per_definition_with_legacy_values(tmp_path: Path) -> None:
    findings = ViewpointStyleValueUpgradeStep().detect(_view(tmp_path, _LEGACY))

    assert [f.finding_id for f in findings] == ["legacy-style-values:lifecycle-heat"]
    (finding,) = findings
    assert finding.auto_migratable is True
    assert "highlight" in finding.description
    assert "cool" in finding.description
    assert "grayish" in finding.description
    assert "#ff0000" not in finding.description


def test_apply_rewrites_only_legacy_values(tmp_path: Path) -> None:
    step = ViewpointStyleValueUpgradeStep()
    view = _view(tmp_path, _LEGACY)
    findings = step.detect(view)

    applied = step.apply(view, FilesystemRepoUpgradeWriter(tmp_path), findings)

    assert [a.outcome for a in applied] == ["applied"]
    loaded: Any = yaml.safe_load((tmp_path / ".arch-repo" / "viewpoints.yaml").read_text(encoding="utf-8"))
    by_slug = {d["slug"]: d for d in loaded["viewpoints"]}
    legacy_rules = by_slug["lifecycle-heat"]["presentation"]["styling_rules"]
    assert legacy_rules[0]["value"] == "neutral"
    assert legacy_rules[1]["scale_tokens"] == ["neutral", "#ff0000"]
    assert by_slug["lifecycle-heat"]["presentation"]["default_style"]["node_color"] == "neutral"
    assert by_slug["already-valid"]["presentation"]["styling_rules"][0]["value"] == "#336699"

    # Idempotent: nothing left to find after the rewrite.
    assert step.detect(FilesystemRepoUpgradeView(tmp_path)) == []
