"""A part a whole already composes cannot be composed by a second whole (B84).

E340 says composition admits one whole per part, but only the repository-level verification saw it:
a bulk write committed a second composition parent, and the error appeared on an unrelated later
write's full verify. The connection write now asks the same question, through the type's declared
exclusivity, and refuses before anything reaches a file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.mcp import mcp_artifact_server as mcp
from src.infrastructure.mcp.artifact_mcp.bulk_tools import artifact_bulk_write


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-E340" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


def _component(repo: Path, name: str) -> str:
    result = mcp.artifact_create_entity(
        artifact_type="application-component", name=name, summary=f"Summary for {name}", dry_run=False,
        repo_root=str(repo),
    )
    assert result["wrote"], result
    return str(result["artifact_id"])


def _connect(repo: Path, source: str, conn_type: str, target: str) -> dict:
    return mcp.artifact_add_connection(
        source_entity=source, connection_type=conn_type, target_entity=target, dry_run=False,
        repo_root=str(repo),
    )


def test_a_second_composition_parent_is_refused(repo: Path) -> None:
    first, second, part = _component(repo, "First"), _component(repo, "Second"), _component(repo, "Part")
    assert _connect(repo, first, "archimate-composition", part)["wrote"]

    with pytest.raises(ValueError, match=r"permits one source per target") as refused:
        _connect(repo, second, "archimate-composition", part.rsplit(".", 1)[0])

    assert first in str(refused.value)
    written = "".join(p.read_text(encoding="utf-8") for p in repo.glob("**/*.outgoing.md"))
    assert written.count("archimate-composition") == 1, "the refused claim reached a file"


def test_a_relation_that_lets_a_part_be_shared_is_still_written(repo: Path) -> None:
    first, second, part = _component(repo, "First"), _component(repo, "Second"), _component(repo, "Part")
    assert _connect(repo, first, "archimate-composition", part)["wrote"]

    assert _connect(repo, second, "archimate-aggregation", part)["wrote"]


def test_the_bulk_write_refuses_it_too(repo: Path) -> None:
    first, second, part = _component(repo, "First"), _component(repo, "Second"), _component(repo, "Part")

    result = artifact_bulk_write(
        items=[
            {"op": "add_connection", "source_entity": first, "connection_type": "archimate-composition",
             "target_entity": part},
            {"op": "add_connection", "source_entity": second, "connection_type": "archimate-composition",
             "target_entity": part},
        ],
        dry_run=False, repo_root=str(repo),
    )

    assert result["committed"] is False, result
    assert "permits one source per target" in str(result["items"][1]), result["items"][1]
    assert not list(repo.glob("**/*.outgoing.md")), "a refused batch reached a file"
