"""Regression: `edit_diagram`'s `viewpoint` parameter previously conflated "omitted by the
caller" with "explicitly set to None" — both defaulted to/collapsed onto `None`, so there
was no way to *clear* a diagram's `ViewpointApplication` once applied (only to leave it
unchanged or replace it with another). The WU-E5a GUI viewpoint selector needs "none" to be
a real selectable state that clears an existing application on save — this is the
`_VIEWPOINT_UNSET` sentinel fix (mirrors the pre-existing `_EDGE_LABELS_UNSET` pattern in
the same module) that makes that possible: omit `viewpoint` to keep the current application,
pass `None` explicitly to clear it, pass a mapping to replace it.

The MCP `artifact_edit_diagram` tool is unaffected — its kwargs are already filtered to drop
`None` values before calling `edit_diagram`, so an MCP caller omitting `viewpoint` (or passing
`null`) has always meant "unchanged" and continues to.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from src.application.verification.artifact_verifier import ArtifactRegistry, ArtifactVerifier
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.write.artifact_write.diagram_edit import edit_diagram


@lru_cache(maxsize=1)
def _catalogs():
    from src.infrastructure.app_bootstrap import build_module_registry, build_runtime_catalogs  # noqa: PLC0415

    return build_runtime_catalogs(build_module_registry())


def _noop_caches(path: Path) -> None:  # noqa: ARG001
    pass


def _verifier(repo_root: Path) -> ArtifactVerifier:
    return ArtifactVerifier(
        ArtifactRegistry(shared_artifact_index(repo_root)), check_puml_syntax=False, catalogs=_catalogs(),
    )


def _make_diagram_with_viewpoint(repo_root: Path, artifact_id: str) -> Path:
    path = repo_root / "diagram-catalog" / "diagrams" / f"{artifact_id}.puml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""\
---
artifact-id: {artifact_id}
artifact-type: diagram
diagram-type: archimate-motivation
name: Landscape
version: 0.1.0
status: draft
last-updated: '2026-01-01'
entity-ids-used: []
connection-ids-used: []
viewpoint: {{slug: motivation, version: 1}}
---
@startuml {artifact_id}
title Landscape
@enduml
""",
        encoding="utf-8",
    )
    return path


def _fm(content: str) -> dict:
    return yaml.safe_load(content.split("---\n")[1])


def test_omitting_viewpoint_keeps_existing_application(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "model").mkdir(parents=True)
    artifact_id = "ARC@1.x.landscape-keep"
    _make_diagram_with_viewpoint(repo_root, artifact_id)

    result = edit_diagram(
        repo_root=repo_root, verifier=_verifier(repo_root), clear_repo_caches=_noop_caches,
        artifact_id=artifact_id, status="active", dry_run=True,
    )

    assert result.content is not None
    assert _fm(result.content)["viewpoint"] == {"slug": "motivation", "version": 1}


def test_explicit_none_clears_existing_application(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "model").mkdir(parents=True)
    artifact_id = "ARC@1.x.landscape-clear"
    _make_diagram_with_viewpoint(repo_root, artifact_id)

    result = edit_diagram(
        repo_root=repo_root, verifier=_verifier(repo_root), clear_repo_caches=_noop_caches,
        artifact_id=artifact_id, viewpoint=None, dry_run=True,
    )

    assert result.content is not None
    assert "viewpoint" not in _fm(result.content)


def test_mapping_replaces_existing_application(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "model").mkdir(parents=True)
    artifact_id = "ARC@1.x.landscape-replace"
    _make_diagram_with_viewpoint(repo_root, artifact_id)

    result = edit_diagram(
        repo_root=repo_root, verifier=_verifier(repo_root), clear_repo_caches=_noop_caches,
        artifact_id=artifact_id, viewpoint={"slug": "layered", "version": 2}, dry_run=True,
    )

    assert result.content is not None
    assert _fm(result.content)["viewpoint"] == {"slug": "layered", "version": 2}
