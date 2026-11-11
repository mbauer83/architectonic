"""A diagram edit given short entity ids records each entity once, by its full id (B83).

`artifact_edit_diagram(entity_ids=…)` with an explicit body accepted the short form
(`PREFIX@epoch.random`) and recorded it beside the full id the body's inference found, so every element
appeared twice in `entity-ids-used`. Ids are normalised at the boundary, so what is recorded is the same
whichever spelling the caller used.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.infrastructure.mcp import mcp_artifact_server as mcp


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-SID" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


def _goal(repo: Path, name: str) -> str:
    result = mcp.artifact_create_entity(
        artifact_type="goal", name=name, summary=f"Summary for {name}", dry_run=False, repo_root=str(repo),
    )
    assert result["wrote"], result
    return str(result["artifact_id"])


def _short(artifact_id: str) -> str:
    return artifact_id.rsplit(".", 1)[0]


def _alias(artifact_id: str) -> str:
    prefix_part, random_part, *_ = artifact_id.split(".")
    return f"{prefix_part.split('@', 1)[0]}_{random_part}"


def test_short_ids_beside_an_explicit_body_are_recorded_once_and_in_full(repo: Path) -> None:
    first, second = _goal(repo, "First goal"), _goal(repo, "Second goal")
    created = mcp.artifact_create_diagram(
        diagram_type="archimate-motivation", name="Hand laid", entity_ids=[first, second],
        dry_run=False, repo_root=str(repo),
    )
    hand_laid = "\n".join([
        "@startuml hand-laid",
        f'rectangle "<$archimate_goal{{scale=1.2}}> First goal" <<goal>> as {_alias(first)}',
        f'rectangle "<$archimate_goal{{scale=1.2}}> Second goal" <<goal>> as {_alias(second)}',
        "@enduml",
    ])

    edited = mcp.artifact_edit_diagram(
        artifact_id=created["artifact_id"], puml=hand_laid, entity_ids=[_short(first), _short(second)],
        dry_run=False, repo_root=str(repo),
    )

    assert edited["wrote"], edited
    text = Path(edited["path"]).read_text(encoding="utf-8")
    recorded = yaml.safe_load(text.split("---", 2)[1])["entity-ids-used"]
    assert sorted(recorded) == sorted([first, second])
