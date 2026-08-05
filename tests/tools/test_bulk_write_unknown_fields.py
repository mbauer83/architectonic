"""A batch item that carries a field its op does not accept is refused, not performed differently.

`artifact_edit_connection` takes `operation=update|remove`. A caller passing `mode: "remove"` — the
word every other tool in this space uses — got an *update*: the field was ignored, the connection was
not removed, and the item reported `wrote: true`. The report was the problem. A caller that trusts it
proceeds on a false premise, and the next operation is the one that fails, far from the cause.

Silently ignoring an unrecognised field is only safe when every field is decoration. Here fields
*select the operation*, so ignoring one changes what the item does.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.mcp import mcp_artifact_server as mcp
from src.infrastructure.mcp.artifact_mcp.bulk.write import artifact_bulk_write

_REALIZATION = "archimate-realization"


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-FIELDS" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


def _entity(repo: Path, artifact_type: str, name: str) -> str:
    result = mcp.artifact_create_entity(
        artifact_type=artifact_type, name=name, summary=name, dry_run=False, repo_root=str(repo)
    )
    assert result["wrote"], result
    return str(result["artifact_id"])


def _edge(repo: Path) -> tuple[str, str, Path]:
    source = _entity(repo, "requirement", "Field Source")
    target = _entity(repo, "outcome", "Field Target")
    added = mcp.artifact_add_connection(
        source_entity=source, target_entity=target, connection_type=_REALIZATION,
        description="Realizes it.", dry_run=False, repo_root=str(repo),
    )
    assert added["wrote"], added
    return source, target, next(repo.rglob(f"{source}.outgoing.md"))


def _batch(repo: Path, items: list[dict]) -> dict:
    return artifact_bulk_write(items=items, dry_run=False, repo_root=str(repo), return_mode="full")


def test_a_misspelled_operation_field_is_refused(repo: Path) -> None:
    source, target, outgoing = _edge(repo)
    before = outgoing.read_text(encoding="utf-8")

    result = _batch(repo, [{
        "op": "edit_connection", "source_entity": source, "target_entity": target,
        "connection_type": _REALIZATION, "mode": "remove",
    }])

    assert result["committed"] is False
    assert result["items"][0]["wrote"] is False
    assert "mode" in str(result["items"][0]["error"])
    assert outgoing.read_text(encoding="utf-8") == before


def test_the_refusal_names_the_accepted_fields(repo: Path) -> None:
    """So the caller can fix it without reading the source."""
    source, target, _outgoing = _edge(repo)

    result = _batch(repo, [{
        "op": "edit_connection", "source_entity": source, "target_entity": target,
        "connection_type": _REALIZATION, "mode": "remove",
    }])

    assert "operation" in str(result["items"][0]["error"])


def test_the_documented_field_still_removes(repo: Path) -> None:
    """The refusal must not be a new way to fail a correct batch: `operation` works, and removing the
    last connection deletes the file it was in."""
    source, target, outgoing = _edge(repo)

    result = _batch(repo, [{
        "op": "edit_connection", "source_entity": source, "target_entity": target,
        "connection_type": _REALIZATION, "operation": "remove",
    }])

    assert result["committed"] is True, result
    assert not outgoing.exists()


def test_a_sibling_connection_and_its_description_survive_a_removal(repo: Path) -> None:
    source, target, outgoing = _edge(repo)
    other = _entity(repo, "outcome", "Field Other Target")
    mcp.artifact_add_connection(
        source_entity=source, target_entity=other, connection_type=_REALIZATION,
        description="Keeps its words.", dry_run=False, repo_root=str(repo),
    )

    result = _batch(repo, [{
        "op": "edit_connection", "source_entity": source, "target_entity": target,
        "connection_type": _REALIZATION, "operation": "remove",
    }])

    assert result["committed"] is True, result
    text = outgoing.read_text(encoding="utf-8")
    assert target not in text
    assert other in text
    assert "Keeps its words." in text


def test_an_unknown_field_on_a_create_is_refused_too(repo: Path) -> None:
    """The check is per op, from one table, so no op is left tolerant."""
    result = _batch(repo, [{
        "op": "create_entity", "artifact_type": "requirement", "name": "Stray Field",
        "summary": "s", "descriptions": "not a field",
    }])

    assert result["committed"] is False
    assert "descriptions" in str(result["items"][0]["error"])


def test_the_caller_s_own_alias_is_not_a_stray_field(repo: Path) -> None:
    """`_ref` is how a caller correlates its items to allocated ids; it is accepted everywhere."""
    result = _batch(repo, [{
        "op": "create_entity", "_ref": "mine", "artifact_type": "requirement",
        "name": "Aliased Entity", "summary": "s",
    }])

    assert result["committed"] is True, result
    assert result["refs"]["mine"]
