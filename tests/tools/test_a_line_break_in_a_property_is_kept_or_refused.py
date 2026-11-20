"""A line break in a property is kept when it is in the value and refused when it is in the name.

A property is one row of a table, and a row is one line. A *value* of several lines is legitimate —
the typed codec has always spelled a line feed as an escape — but it spelled no other line break, so a
value pasted with Windows line endings was written as a row broken in two and read back cut at the
break. An attribute *name* has no escape and cannot be several lines, and nothing said so: it too was
written as a broken row.

Every case here goes through a surface a caller actually uses, because the cell is spelled several
layers below each of them and a refusal has to arrive as a sentence at all of them.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from mcp.server.context import ServerRequestContext
from mcp.types import CallToolRequestParams, TextContent

from src.application.artifacts.parsing import parse_entity_content_sections
from src.application.artifacts.query import ArtifactRepository
from src.domain.ontology_representation.property_value import decode
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.mcp import mcp_artifact_server as mcp
from src.infrastructure.mcp.artifact_mcp.bulk_tools import artifact_bulk_write
from src.infrastructure.mcp.artifact_mcp.name_normalization import install_call_tool_normalizer
from src.infrastructure.rest.routers import state as gui_state
from src.infrastructure.rest.routers.entities.router import router as entities_router
from tests.support.api_app import build_api_app

httpx = pytest.importorskip("httpx")

_MARKDOWN_LINE_ENDINGS = {"line-feed": "\n", "windows": "\r\n", "carriage-return": "\r"}

#: Also a character `str.splitlines` breaks at and markdown does not: a value holding one is one line.
_LINE_BREAKS = _MARKDOWN_LINE_ENDINGS | {"line-separator": "\u2028"}

_VALUES = [pytest.param(f"one{line_break}two | three", id=name) for name, line_break in _LINE_BREAKS.items()]

#: What a name may not hold: the three line endings a markdown line can end in.
_BROKEN_NAMES = [
    pytest.param(f"Ratio{line_break}nale", id=name) for name, line_break in _MARKDOWN_LINE_ENDINGS.items()
]

_REFUSAL = "is one line"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-LINEBREAK" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    gui_state.init_state(ArtifactRepository(shared_artifact_index([root])), root, None)
    return root


@pytest.fixture
def client(repo: Path):
    from starlette.testclient import TestClient

    return TestClient(build_api_app(entities_router))


def _create(repo: Path, name: str, properties: dict[str, str]) -> dict[str, Any]:
    return mcp.artifact_create_entity(
        artifact_type="requirement", name=name, summary="A summary.", properties=properties,
        dry_run=False, repo_root=str(repo),
    )


def _stored(repo: Path, artifact_id: str) -> dict[str, object]:
    (path,) = repo.rglob(f"{artifact_id}*.md")
    cells = parse_entity_content_sections(path.read_text(encoding="utf-8"))["properties"]
    return {name: decode(cell, "string") for name, cell in cells.items()}


def _tool_answer(tool_name: str, arguments: dict[str, Any]) -> tuple[bool, str]:
    """What an MCP client is told: the call goes through the boundary that translates a refusal."""
    install_call_tool_normalizer(mcp.mcp_write)
    entry = mcp.mcp_write._lowlevel_server.get_request_handler("tools/call")
    params = CallToolRequestParams(name=tool_name, arguments=arguments)
    context = ServerRequestContext(
        session=None, lifespan_context=None, protocol_version=None,
        method="tools/call", params=params, request_id=1,
    )
    result = asyncio.run(entry.handler(context, params))
    return bool(result.is_error), next(c.text for c in result.content if isinstance(c, TextContent))


class TestAValueOfSeveralLinesIsKeptWhole:
    @pytest.mark.parametrize("value", _VALUES)
    def test_created_through_the_tool(self, repo: Path, value: str) -> None:
        result = _create(repo, "Created", {"Rationale": value, "Other": "kept"})

        assert result["wrote"], result
        assert _stored(repo, str(result["artifact_id"])) == {"Rationale": value, "Other": "kept"}

    @pytest.mark.parametrize("value", _VALUES)
    def test_edited_through_the_tool(self, repo: Path, value: str) -> None:
        artifact_id = str(_create(repo, "Edited", {"Rationale": "before", "Other": "kept"})["artifact_id"])

        result = mcp.artifact_edit_entity(
            artifact_id=artifact_id, properties={"Rationale": value}, dry_run=False, repo_root=str(repo),
        )

        assert result["wrote"], result
        assert _stored(repo, artifact_id) == {"Rationale": value, "Other": "kept"}

    @pytest.mark.parametrize("value", _VALUES)
    def test_edited_over_rest(self, repo: Path, client, value: str) -> None:
        artifact_id = str(_create(repo, "Patched", {"Rationale": "before", "Other": "kept"})["artifact_id"])

        response = client.patch(
            f"/api/entities/{artifact_id}", json={"properties": {"Rationale": value}, "dry_run": False},
        )

        assert response.status_code == 200, response.text
        assert _stored(repo, artifact_id) == {"Rationale": value, "Other": "kept"}

    @pytest.mark.parametrize("value", _VALUES)
    def test_created_over_rest(self, repo: Path, client, value: str) -> None:
        response = client.post("/api/entities", json={
            "artifact_type": "requirement", "name": "Posted", "summary": "A summary.",
            "properties": {"Rationale": value}, "dry_run": False,
        })

        assert response.status_code == 201, response.text
        assert _stored(repo, response.json()["artifact_id"]) == {"Rationale": value}

    @pytest.mark.parametrize("value", _VALUES)
    def test_created_in_a_batch(self, repo: Path, value: str) -> None:
        result = artifact_bulk_write(
            items=[{
                "op": "create_entity", "artifact_type": "requirement", "name": "Batched",
                "summary": "A summary.", "properties": {"Rationale": value},
            }],
            dry_run=False, repo_root=str(repo),
        )

        assert result["committed"] is True, result
        (path,) = repo.rglob("REQ@*.md")
        assert _stored(repo, path.name.split(".md")[0]) == {"Rationale": value}


class TestANameOfSeveralLinesIsRefusedWithASentence:
    @pytest.mark.parametrize("name", _BROKEN_NAMES)
    def test_the_tool_answers_with_the_refusal(self, repo: Path, name: str) -> None:
        is_error, text = _tool_answer("artifact_create_entity", {
            "artifact_type": "requirement", "name": "Refused", "summary": "A summary.",
            "properties": {name: "value"}, "dry_run": False, "repo_root": str(repo),
        })

        assert is_error
        assert _REFUSAL in text and "Ratio" in text, text
        assert "Error executing tool" not in text and "escape_cell" not in text, text
        assert not list(repo.rglob("REQ@*.md")), "a refused write reached a file"

    @pytest.mark.parametrize("name", _BROKEN_NAMES)
    def test_an_edit_through_the_tool_is_refused_and_changes_nothing(self, repo: Path, name: str) -> None:
        artifact_id = str(_create(repo, "Kept", {"Rationale": "before"})["artifact_id"])

        is_error, text = _tool_answer("artifact_edit_entity", {
            "artifact_id": artifact_id, "properties": {name: "value"}, "dry_run": False, "repo_root": str(repo),
        })

        assert is_error
        assert _REFUSAL in text, text
        assert _stored(repo, artifact_id) == {"Rationale": "before"}

    @pytest.mark.parametrize("name", _BROKEN_NAMES)
    def test_rest_answers_400_with_the_refusal(self, repo: Path, client, name: str) -> None:
        artifact_id = str(_create(repo, "Kept", {"Rationale": "before"})["artifact_id"])

        response = client.patch(
            f"/api/entities/{artifact_id}", json={"properties": {name: "value"}, "dry_run": False},
        )

        assert response.status_code == 400, response.text
        message = response.json()["detail"]["message"]
        assert _REFUSAL in message and "escape_cell" not in message, message
        assert _stored(repo, artifact_id) == {"Rationale": "before"}

    @pytest.mark.parametrize("name", _BROKEN_NAMES)
    def test_a_batch_names_the_refusal_on_its_item_and_commits_nothing(self, repo: Path, name: str) -> None:
        result = artifact_bulk_write(
            items=[{
                "op": "create_entity", "artifact_type": "requirement", "name": "Batched",
                "summary": "A summary.", "properties": {name: "value"},
            }],
            dry_run=False, repo_root=str(repo),
        )

        assert result["committed"] is False, result
        assert _REFUSAL in str(result["items"][0]), result["items"][0]
        assert not list(repo.rglob("REQ@*.md")), "a refused batch reached a file"
