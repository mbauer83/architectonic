"""Tests for the incident-traversal stamping step: silent on absent/malformed files and
on fully-stamped definitions; fires when any incident predicate relies on the implicit
'direct' default; the rewrite stamps the default explicitly, preserves every explicitly
saved traversal (parameterized recipes included), and is idempotent."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from src.application.repository_upgrade.steps.viewpoint_incident_traversal_stamp import (
    ViewpointIncidentTraversalStampStep,
)
from src.domain.viewpoints.viewpoint_parsing import viewpoint_catalog_from_mapping
from src.infrastructure.repository_upgrade.fs_adapter import (
    FilesystemRepoUpgradeView,
    FilesystemRepoUpgradeWriter,
)

_UNSTAMPED = """\
viewpoints:
- slug: layer-leaks
  version: 1
  name: Layer Leaks
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
      - kind: incident
        direction: outgoing
        endpoint_criteria:
          kind: group
          conjunction: and
          children:
          - kind: incident
            direction: incoming
- slug: already-explicit
  version: 1
  name: Already Explicit
  query:
    query_schema: 1
    entity_criteria:
      kind: group
      conjunction: and
      children:
      - kind: incident
        traversal: derived
        max_hops: 3
"""


def _view(root: Path, content: str | None) -> FilesystemRepoUpgradeView:
    (root / ".arch-repo").mkdir(parents=True, exist_ok=True)
    if content is not None:
        (root / ".arch-repo" / "viewpoints.yaml").write_text(content, encoding="utf-8")
    return FilesystemRepoUpgradeView(root)


def test_silent_when_file_absent(tmp_path: Path) -> None:
    assert ViewpointIncidentTraversalStampStep().detect(_view(tmp_path, None)) == []


def test_silent_on_malformed_file(tmp_path: Path) -> None:
    view = _view(tmp_path, "viewpoints:\n  - slug: [unterminated\n")
    assert ViewpointIncidentTraversalStampStep().detect(view) == []


def test_detects_every_unstamped_predicate_including_nested_ones(tmp_path: Path) -> None:
    findings = ViewpointIncidentTraversalStampStep().detect(_view(tmp_path, _UNSTAMPED))
    assert [f.finding_id for f in findings] == ["implicit-incident-traversal"]
    (finding,) = findings
    assert finding.auto_migratable is True
    assert "2 incident predicate(s)" in finding.description


def test_apply_stamps_the_default_and_preserves_explicit_values(tmp_path: Path) -> None:
    step = ViewpointIncidentTraversalStampStep()
    view = _view(tmp_path, _UNSTAMPED)
    before = viewpoint_catalog_from_mapping(yaml.safe_load(_UNSTAMPED))
    findings = step.detect(view)

    applied = step.apply(view, FilesystemRepoUpgradeWriter(tmp_path), findings)

    assert [a.outcome for a in applied] == ["applied"]
    loaded: Any = yaml.safe_load((tmp_path / ".arch-repo" / "viewpoints.yaml").read_text(encoding="utf-8"))
    by_slug = {d["slug"]: d for d in loaded["viewpoints"]}
    outer = by_slug["layer-leaks"]["query"]["entity_criteria"]["children"][0]
    assert outer["traversal"] == "direct"
    assert outer["endpoint_criteria"]["children"][0]["traversal"] == "direct"
    explicit = by_slug["already-explicit"]["query"]["entity_criteria"]["children"][0]
    assert explicit["traversal"] == "derived"
    assert explicit["max_hops"] == 3
    # Parameterized recipe survives untouched.
    assert by_slug["layer-leaks"]["query"]["parameters"][0]["name"] == "anchor"

    # Pure stamping: the parsed semantics are identical before and after.
    assert viewpoint_catalog_from_mapping(loaded) == before

    # Idempotent: nothing left to find, and a second apply writes identical bytes.
    assert step.detect(FilesystemRepoUpgradeView(tmp_path)) == []
    first_bytes = (tmp_path / ".arch-repo" / "viewpoints.yaml").read_bytes()
    step.apply(FilesystemRepoUpgradeView(tmp_path), FilesystemRepoUpgradeWriter(tmp_path), [])
    assert (tmp_path / ".arch-repo" / "viewpoints.yaml").read_bytes() == first_bytes
