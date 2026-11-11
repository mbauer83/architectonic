"""Whatever path writes an ArchiMate body, it carries the whole generated header (B72, B85).

The header's skinparams were composed in three places. A body the renderer generated lacked the text
alignment the refresh states, so every created diagram changed on its first edit (B72); an explicit body
completed by the write path lacked the label width bound, so gate 8 refused the body the write path had
just produced (B85). All three now read `generated_header.stated_skinparams`, so a written body is
already what a refresh would make of it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.mcp import mcp_artifact_server as mcp


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-HDR" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


def _goal(repo: Path, name: str) -> str:
    result = mcp.artifact_create_entity(
        artifact_type="goal", name=name, summary=f"Summary for {name}", dry_run=False, repo_root=str(repo),
    )
    assert result["wrote"], result
    return str(result["artifact_id"])


def _body(path: str) -> str:
    return Path(path).read_text(encoding="utf-8").split("---", 2)[2]


def _refreshed(body: str, repo: Path) -> str:
    from src.infrastructure.diagram_type_registry import find_renderer  # noqa: PLC0415

    renderer = find_renderer("archimate-motivation")
    assert renderer is not None
    return renderer.refresh_generated_header(body, repo)


def test_a_created_body_is_already_what_its_first_refresh_makes_it(repo: Path) -> None:
    created = mcp.artifact_create_diagram(
        diagram_type="archimate-motivation", name="Fresh", entity_ids=[_goal(repo, "A goal")],
        dry_run=False, repo_root=str(repo),
    )
    assert created["wrote"], created
    body = _body(created["path"])

    assert "skinparam defaultTextAlignment center" in body
    assert _refreshed(body, repo) == body


def test_an_explicit_body_is_completed_with_the_width_bound(repo: Path) -> None:
    goal = _goal(repo, "A goal")
    created = mcp.artifact_create_diagram(
        diagram_type="archimate-motivation", name="Hand laid", entity_ids=[goal],
        dry_run=False, repo_root=str(repo),
    )
    prefix_part, random_part, *_ = goal.split(".")
    alias = f"{prefix_part.split('@', 1)[0]}_{random_part}"
    hand_laid = "\n".join([
        "@startuml hand-laid",
        f'rectangle "<$archimate_goal{{scale=1.2}}> A goal" <<goal>> as {alias}',
        "@enduml",
    ])

    edited = mcp.artifact_edit_diagram(
        artifact_id=created["artifact_id"], puml=hand_laid, entity_ids=[goal], dry_run=False,
        repo_root=str(repo),
    )

    assert edited["wrote"], edited
    body = _body(edited["path"])
    assert "skinparam wrapWidth" in body and "skinparam maxMessageSize" in body
    assert _refreshed(body, repo) == body
