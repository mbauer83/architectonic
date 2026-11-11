"""Reading a diagram by its id returns the diagram, never a record it holds (B110).

A record a diagram holds is addressed ``DIAGRAM_ID#type/local``. ``stable_id`` cut at the last dot,
which for that form lies inside the diagram's slug, so every held record shared its diagram's stem;
the lookups that resolve by stem — MCP's id expansion and the index's ``canonical_id`` — answered one
of the records, whichever an unordered set yielded first. A held record's stable form is now its
host's stable form with the local part kept.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
import yaml
from mcp.server.context import ServerRequestContext
from mcp.types import CallToolRequestParams, TextContent

from src.application.verification.artifact_verifier import ArtifactRegistry
from src.domain.artifact_id import stable_id
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.mcp import mcp_artifact_server as mcp
from src.infrastructure.mcp.artifact_mcp.context import expand_artifact_id
from tests.support.diagram_held_records import DIAGRAM_ID, NOTE_ID, repository_with_held_records

SHORT_DIAGRAM_ID = stable_id(DIAGRAM_ID)


def _read(repo: Path, artifact_id: str) -> dict[str, Any]:
    """Read through the shipped read server's call handler, as an MCP client does."""
    params = CallToolRequestParams(name="artifact_query_read_artifact", arguments={
        "artifact_id": artifact_id, "repo_root": str(repo), "repo_scope": "engagement",
    })
    context = ServerRequestContext(session=None, lifespan_context=None, protocol_version=None,
                                   method="tools/call", params=params, request_id=1)
    entry = mcp.mcp_read._lowlevel_server.get_request_handler("tools/call")
    result = asyncio.run(entry.handler(context, params))
    assert not result.is_error, result
    text = next(c.text for c in result.content if isinstance(c, TextContent))
    return yaml.safe_load(text)["result"]


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return repository_with_held_records(tmp_path, "ENG-READ")


def test_a_held_record_keeps_its_local_part_in_its_stable_form() -> None:
    assert stable_id(NOTE_ID) == f"{SHORT_DIAGRAM_ID}#note/n1"
    assert stable_id(NOTE_ID) != SHORT_DIAGRAM_ID
    assert stable_id(f"{SHORT_DIAGRAM_ID}#note/n1") == f"{SHORT_DIAGRAM_ID}#note/n1"


@pytest.mark.parametrize("addressed_as", [DIAGRAM_ID, SHORT_DIAGRAM_ID])
def test_reading_the_diagram_returns_the_diagram(repo: Path, addressed_as: str) -> None:
    read = _read(repo, addressed_as)

    assert read["record_type"] == "diagram", read
    assert read["artifact_id"] == DIAGRAM_ID


def test_expansion_leaves_the_diagram_id_alone(repo: Path) -> None:
    registry = ArtifactRegistry(shared_artifact_index([repo]))

    assert expand_artifact_id(registry, DIAGRAM_ID) == DIAGRAM_ID


def test_a_held_record_is_found_by_its_own_short_form(repo: Path) -> None:
    read = _read(repo, f"{SHORT_DIAGRAM_ID}#note/n1")

    assert read["artifact_id"] == NOTE_ID, read
