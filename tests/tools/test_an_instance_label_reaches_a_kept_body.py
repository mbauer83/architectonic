"""A label set on an instance reaches the picture whichever way the body is written.

An ArchiMate element is called what its record says, on every diagram, and that name is often too
long for one crowded box. ``diagram-entities.display_labels`` is the diagram's own say about an
instance, keyed by the entity's id for its base instance and by the occurrence id for a further one.

Where the body is regenerated the renderer emits it. Where the body is kept as the author left it —
a hand-laid diagram, the case that raised this — the statement has no other way in, so the write
path relabels the declaration in place and touches nothing else. Asserted through the MCP tools,
because the question is what a *write* leaves on disk, not what a function returns.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.mcp import mcp_artifact_server as mcp


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-LBL" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


def _entity(repo: Path, name: str) -> str:
    result = mcp.artifact_create_entity(
        artifact_type="goal", name=name, summary=f"Summary for {name}", dry_run=False, repo_root=str(repo),
    )
    assert result["wrote"], result
    return str(result["artifact_id"])


def _alias(artifact_id: str) -> str:
    prefix_part, random_part, *_ = artifact_id.split(".")
    return f"{prefix_part.split('@', 1)[0]}_{random_part}"


def _body_of(repo: Path, diagram_id: str) -> str:
    text = (repo / "diagram-catalog" / "diagrams" / f"{diagram_id}.puml").read_text(encoding="utf-8")
    return text.split("---", 2)[2]


def _declaration(body: str, alias: str) -> str:
    lines = [line for line in body.splitlines() if line.rstrip().endswith(f" as {alias}")]
    assert len(lines) == 1, (alias, lines)
    return lines[0]


LONG = "Provide Governed Self-Service Read Access to Architecture"


def test_a_regenerated_body_calls_the_instance_what_the_diagram_says(repo: Path) -> None:
    goal = _entity(repo, LONG)
    created = mcp.artifact_create_diagram(
        diagram_type="archimate-motivation", name="Labelled", entity_ids=[goal],
        diagram_entities={"display_labels": {goal: "Self-Service Read Access"}},
        dry_run=False, repo_root=str(repo),
    )
    assert created["wrote"], created

    assert '"<$archimate_goal{scale=1.2}> Self-Service Read Access"' in _declaration(
        _body_of(repo, str(created["artifact_id"])), _alias(goal)
    )


def test_a_hand_laid_body_is_relabelled_in_place_and_otherwise_kept(repo: Path) -> None:
    goal = _entity(repo, LONG)
    other = _entity(repo, "Another Goal")
    created = mcp.artifact_create_diagram(
        diagram_type="archimate-motivation", name="Hand laid", entity_ids=[goal, other],
        dry_run=False, repo_root=str(repo),
    )
    diagram_id = str(created["artifact_id"])
    hand_laid = "\n".join([
        "@startuml hand-laid",
        "left to right direction",
        f'rectangle "<$archimate_goal{{scale=1.2}}> Validated Before Implementation" <<goal>> as {_alias(goal)}',
        f'rectangle "<$archimate_goal{{scale=1.2}}> Another Goal" <<goal>> as {_alias(other)}',
        f"{_alias(goal)} -[hidden]right- {_alias(other)}",
        "@enduml",
    ])
    laid = mcp.artifact_edit_diagram(
        artifact_id=diagram_id, puml=hand_laid, manual_layout=True, dry_run=False, repo_root=str(repo),
    )
    assert laid["wrote"], laid
    # A body-less edit restates the renderer's own header lines even on a kept body (that is how a
    # hand-laid diagram hears about a palette change), so the baseline is one such edit with no
    # label stated — what changes between it and the relabel is then the relabel alone.
    control = mcp.artifact_edit_diagram(artifact_id=diagram_id, status="draft", dry_run=False, repo_root=str(repo))
    assert control["wrote"], control
    before = _body_of(repo, diagram_id)
    assert "Validated Before Implementation" in _declaration(before, _alias(goal))

    relabelled = mcp.artifact_edit_diagram(
        artifact_id=diagram_id, diagram_entities={"display_labels": {goal: "Validated"}},
        dry_run=False, repo_root=str(repo),
    )
    assert relabelled["wrote"], relabelled

    after = _body_of(repo, diagram_id)
    assert _declaration(after, _alias(goal)).endswith(
        f'"<$archimate_goal{{scale=1.2}}> Validated" <<goal>> as {_alias(goal)}'
    )
    # Everything the author laid out is exactly where it was: only the one declaration moved.
    assert [line for line in after.splitlines() if _alias(goal) not in line or "-[hidden]" in line] == [
        line for line in before.splitlines() if _alias(goal) not in line or "-[hidden]" in line
    ]
    assert "Another Goal" in _declaration(after, _alias(other))
