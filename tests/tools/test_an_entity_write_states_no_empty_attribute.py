"""An entity write states the attributes it was given a value for, and writes no empty row for any other.

An empty value cell is unstated wherever the model reads one, but the entity writer added an empty row for
every attribute its type's schema declares and the entity did not state. So a write that changed nothing
about an entity's properties still changed its Properties table: applying a candidate's keywords edit to a
system software element added `| Telemetry | |`, because the schema had gained that attribute since the
element was last written.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.infrastructure.mcp import mcp_artifact_server as tools

SCHEMA = {
    "type": "object",
    "required": ["Maturity"],
    "properties": {"Maturity": {"type": "string"}, "Telemetry": {"type": "string"}},
}


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-TEST" / "work-repositories" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    schemata = root / ".arch-repo" / "schemata"
    schemata.mkdir(parents=True)
    (schemata / "attributes.capability.schema.json").write_text(json.dumps(SCHEMA), encoding="utf-8")
    return root


def _created(repo_root: Path, **stated: object) -> Path:
    result = tools.artifact_create_entity(
        artifact_type="capability", name="Plan Releases", summary="A short description.",
        dry_run=False, repo_root=str(repo_root), **stated,
    )
    assert result["wrote"] is True, result
    return Path(str(result["path"]))


def test_a_created_entity_has_no_row_for_an_attribute_it_does_not_state(repo_root: Path) -> None:
    written = _created(repo_root, properties={"Maturity": "Initial"}).read_text(encoding="utf-8")

    assert "| Maturity | Initial |" in written
    assert "Telemetry" not in written


def test_a_keywords_edit_leaves_the_properties_table_as_it_was(repo_root: Path) -> None:
    path = _created(repo_root)
    before = path.read_text(encoding="utf-8")

    edited = tools.artifact_edit_entity(
        artifact_id=str(path.name).removesuffix(".md"), keywords=["release"], dry_run=False,
        repo_root=str(repo_root),
    )

    assert edited["wrote"] is True, edited
    after = path.read_text(encoding="utf-8")
    assert "| Telemetry | |" not in after
    assert "| Maturity | |" not in after
    assert before.split("## Properties")[1].split("<!--")[0] == after.split("## Properties")[1].split("<!--")[0]


def test_a_rewrite_drops_an_empty_row_the_file_already_held(repo_root: Path) -> None:
    path = _created(repo_root, properties={"Maturity": "Initial"})
    path.write_text(
        path.read_text(encoding="utf-8").replace("| Maturity | Initial |", "| Maturity | Initial |\n| Telemetry | |"),
        encoding="utf-8",
    )

    edited = tools.artifact_edit_entity(
        artifact_id=str(path.name).removesuffix(".md"), keywords=["release"], dry_run=False,
        repo_root=str(repo_root),
    )

    assert edited["wrote"] is True, edited
    after = path.read_text(encoding="utf-8")
    assert "| Maturity | Initial |" in after
    assert "Telemetry" not in after
