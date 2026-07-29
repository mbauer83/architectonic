"""artifact_edit_diagram / artifact_delete_diagram / artifact_create_matrix accept the
short (rename-stable) artifact id form for the diagram's own identity, not just for
entities referenced inside a diagram.

Regression coverage: `resolve_diagram_source_path`'s registry fallback
(`find_file_by_id`) previously did an exact-key lookup only, so a short id (no trailing
`.slug`) always reported "not found" for edit_diagram/delete_diagram/create_matrix's
upsert path — even though several sibling MCP tools (artifact_edit_entity,
artifact_edit_connection) already accept short ids via `expand_artifact_id`. Fixed at
`find_file_by_id`'s own layer (canonicalizes via `_MemStore.canonical_id`) rather than by
remembering to call `expand_artifact_id` at every diagram/entity call site — see
test_find_file_by_id_kinds.py for the index-layer unit coverage. Also covers the
follow-on bug a naive fix would reintroduce: once resolution succeeds via a short id,
the diagram's own frontmatter/filename must still record the FULL id, not the short
form the caller happened to pass in.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.infrastructure.mcp import mcp_artifact_server as mcp


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


def _read_fm(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    return yaml.safe_load(text.split("---\n")[1])


def _make_standalone_diagram(repo: Path, artifact_id: str, name: str = "Standalone") -> Path:
    slug = name.lower().replace(" ", "-")
    path = repo / "diagram-catalog" / "diagrams" / f"{artifact_id}.puml"
    path.write_text(
        f"""\
---
artifact-id: {artifact_id}
artifact-type: diagram
diagram-type: c4-container
name: "{name}"
version: 0.1.0
status: draft
last-updated: '2026-01-01'
entity-ids-used: []
connection-ids-used: []
diagram-entities:
  software-system:
  - id: sys
    label: MySystem
---
@startuml {slug}
title {name}
@enduml
""",
        encoding="utf-8",
    )
    return path


def _short_id(full_id: str) -> str:
    """First two dot-separated segments — the rename-stable short form."""
    return ".".join(full_id.split(".")[:2])


def test_edit_diagram_resolves_short_form_and_preserves_full_id(repo: Path) -> None:
    full_id = "DIA@1779000001.tshrt.standalone-diagram"
    _make_standalone_diagram(repo, full_id)
    short_id = _short_id(full_id)

    result = mcp.artifact_edit_diagram(
        artifact_id=short_id, name="Renamed via Short Id", dry_run=False, repo_root=str(repo),
    )

    assert result["wrote"], result
    path = repo / "diagram-catalog" / "diagrams" / f"{full_id}.puml"
    assert path.exists()
    fm = _read_fm(path)
    assert fm["artifact-id"] == full_id  # not truncated to the short form
    assert fm["name"] == "Renamed via Short Id"


def test_edit_diagram_short_form_group_move_keeps_full_id_filename(repo: Path) -> None:
    full_id = "DIA@1779000002.tshrt.grouped-diagram"
    _make_standalone_diagram(repo, full_id)
    short_id = _short_id(full_id)

    result = mcp.artifact_edit_diagram(
        artifact_id=short_id, group="landing-zone", dry_run=False, repo_root=str(repo),
    )

    assert result["wrote"], result
    new_path = repo / "diagram-catalog" / "diagrams" / "landing-zone" / f"{full_id}.puml"
    assert new_path.exists()
    assert _read_fm(new_path)["artifact-id"] == full_id


def test_delete_diagram_resolves_short_form(repo: Path) -> None:
    full_id = "DIA@1779000003.tshrt.to-delete"
    path = _make_standalone_diagram(repo, full_id)
    short_id = _short_id(full_id)

    result = mcp.artifact_delete_diagram(artifact_id=short_id, dry_run=False, repo_root=str(repo))

    assert result["wrote"], result
    assert not path.exists()


def test_delete_diagram_ambiguous_short_id_raises_not_found(repo: Path) -> None:
    """Two diagrams sharing one short id (a genuine rename/shadow collision) must fail
    closed rather than silently deleting whichever the scan happened to see first."""
    full_id_a = "DIA@1779000004.tambig.first-slug"
    full_id_b = "DIA@1779000004.tambig.second-slug"
    _make_standalone_diagram(repo, full_id_a, name="First")
    _make_standalone_diagram(repo, full_id_b, name="Second")
    short_id = _short_id(full_id_a)

    with pytest.raises(ValueError, match="not found"):
        mcp.artifact_delete_diagram(artifact_id=short_id, dry_run=False, repo_root=str(repo))


def test_create_matrix_upsert_via_short_id_preserves_full_id(repo: Path) -> None:
    full_id = "MAT@1779000005.tshrt.short-id-matrix"
    first = mcp.artifact_create_matrix(
        name="V1", matrix_markdown="| A |\n|---|\n| 1 |\n", artifact_id=full_id,
        dry_run=False, repo_root=str(repo),
    )
    assert first["wrote"], first
    short_id = _short_id(full_id)

    second = mcp.artifact_create_matrix(
        name="V2", matrix_markdown="| A |\n|---|\n| 2 |\n", artifact_id=short_id,
        dry_run=False, repo_root=str(repo),
    )

    assert second["wrote"], second
    path = repo / "diagram-catalog" / "diagrams" / f"{full_id}.md"
    assert path.exists()
    fm = _read_fm(path)
    assert fm["artifact-id"] == full_id
    assert "| 2 |" in path.read_text(encoding="utf-8")
