"""Regression: artifact_edit_diagram must pass entity_ids / connection_ids through
to the write layer's entity_ids_used / connection_ids_used (replace semantics).

Guards against the MCP wrapper accepting both parameters but only consuming them
for mode= dispatch, silently dropping them on the default write path — leaving
stale bindings in a diagram's frontmatter with no MCP-reachable way to prune them.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.application.modeling.artifact_write import generate_diagram_id
from src.infrastructure.mcp import mcp_artifact_server as mcp


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


def _make_entity(repo: Path, artifact_type: str, name: str) -> str:
    result = mcp.artifact_create_entity(
        artifact_type=artifact_type,
        name=name,
        summary=f"Summary for {name}",
        dry_run=False,
        repo_root=str(repo),
    )
    assert result["wrote"], result
    return str(result["artifact_id"])


def _alias(artifact_id: str) -> str:
    prefix, rest = artifact_id.split("@", 1)
    random_part = rest.split(".")[1]
    return f"{prefix}_{random_part}".replace("-", "_")


def _body(diagram_id: str, entity_ids: list[str]) -> str:
    decls = "\n".join(
        f'rectangle "Node {i}" <<goal>> as {_alias(eid)}' for i, eid in enumerate(entity_ids)
    )
    return f"@startuml {diagram_id}\n\ntitle Binding Passthrough\n\n{decls}\n\n@enduml\n"


def _frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    _, fm, _ = text.split("---", 2)
    return yaml.safe_load(fm)


def test_entity_ids_replace_existing_bindings(repo: Path) -> None:
    goal_id = _make_entity(repo, "goal", "Binding Goal")
    driver_id = _make_entity(repo, "driver", "Binding Driver")
    diagram_id = generate_diagram_id("archimate-motivation", "Binding Passthrough")

    created = mcp.artifact_create_diagram(
        diagram_type="archimate-motivation",
        name="Binding Passthrough",
        puml=_body(diagram_id, [goal_id, driver_id]),
        artifact_id=diagram_id,
        entity_ids=[goal_id, driver_id],
        dry_run=False,
        repo_root=str(repo),
    )
    assert created["wrote"], created
    fm = _frontmatter(Path(str(created["path"])))
    assert set(fm["entity-ids-used"]) >= {goal_id, driver_id}

    result = mcp.artifact_edit_diagram(
        artifact_id=diagram_id,
        puml=_body(diagram_id, [goal_id]),
        entity_ids=[goal_id],
        connection_ids=[],
        dry_run=False,
        repo_root=str(repo),
    )
    assert result["wrote"], result
    fm = _frontmatter(Path(str(result["path"])))
    assert fm["entity-ids-used"] == [goal_id]
    assert not fm.get("connection-ids-used")
