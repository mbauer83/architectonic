"""An and-junction and an or-junction are drawn differently (B91).

Both were emitted as `circle " "`, so a reader could not tell whether a diagram joined relationships
that all hold or any of which may. ArchiMate draws the and-junction filled and the or-junction hollow.
The ontology now declares that structurally — `mark_classes`, keyed on classes the two junction types
carry — and the declaration writer honours it without naming either type.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.domain.ontology_representation.element_appearance import ElementAppearance
from src.infrastructure.mcp import mcp_artifact_server as mcp


def test_the_appearance_reads_marks_off_classes() -> None:
    appearance = ElementAppearance.from_mapping({
        "element_appearance": {"mark_classes": {"filled": ["a"], "hollow": ["b"], "striped": ["c"]}},
    })

    assert appearance.mark_for(["junction", "a"]) == "filled"
    assert appearance.mark_for(["b"]) == "hollow"
    assert appearance.mark_for(["c"]) is None, "a style outside the closed set is dropped, not invented"
    assert appearance.mark_for(["junction"]) is None


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-JNC" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


def _entity(repo: Path, artifact_type: str, name: str) -> str:
    result = mcp.artifact_create_entity(
        artifact_type=artifact_type, name=name, summary=f"Summary for {name}", dry_run=False,
        repo_root=str(repo),
    )
    assert result["wrote"], result
    return str(result["artifact_id"])


def _alias(artifact_id: str) -> str:
    prefix_part, random_part, *_ = artifact_id.split(".")
    return f"{prefix_part.split('@', 1)[0]}_{random_part}"


def test_a_diagram_draws_the_and_junction_filled_and_the_or_junction_hollow(repo: Path) -> None:
    both = _entity(repo, "and-junction", "Both")
    either = _entity(repo, "or-junction", "Either")
    goal = _entity(repo, "goal", "A goal")
    created = mcp.artifact_create_diagram(
        diagram_type="archimate-motivation", name="Junctions", entity_ids=[both, either, goal],
        dry_run=False, repo_root=str(repo),
    )
    assert created["wrote"], created

    body = Path(created["path"]).read_text(encoding="utf-8")
    declarations = {line.strip() for line in body.splitlines() if line.strip().startswith("circle ")}

    assert f'circle " " as {_alias(both)} #1F1F1F' in declarations, declarations
    assert f'circle " " as {_alias(either)} #FFFFFF' in declarations, declarations
