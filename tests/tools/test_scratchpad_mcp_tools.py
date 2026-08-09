"""The scratchpad MCP tools, driven the way an agent drives them.

The parity test holds the two surfaces equal as *sets*; this asserts the agent surface actually
works — that the document `scratchpad_read` returns is one `scratchpad_replace` accepts, which is
the whole loop an agent has, and that a refusal comes back as data it can branch on rather than as
an exception it cannot see.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from mcp.server.fastmcp import FastMCP

from src.infrastructure.mcp.artifact_mcp.scratchpad_tools import (
    register_scratchpad_read_tools,
    scratchpad_create,
    scratchpad_delete,
    scratchpad_lift,
    scratchpad_replace,
)


@pytest.fixture
def tools(tmp_path: Path) -> dict[str, Any]:
    """The registered callables, keyed by tool name — the same objects the server exposes."""
    repo_root = tmp_path / "architecture-repository"
    repo_root.mkdir()
    registry: dict[str, Any] = {}

    class _Capturing(FastMCP):
        def tool(self, **kwargs: Any):  # type: ignore[override]
            def decorate(fn):
                registry[str(kwargs["name"])] = fn
                return fn
            return decorate

    server = _Capturing(name="test")
    register_scratchpad_read_tools(server)
    # The write tools are module-level functions registered through `register_mutation_tool`, which
    # wraps them in the write queue and the authorization gate. This suite is about what the tools
    # answer, so it calls the functions; that they are behind the executor is asserted by
    # `test_scratchpad_surface_parity` and by the MCP mutation-manifest equality test.
    registry["scratchpad_create"] = scratchpad_create
    registry["scratchpad_replace"] = scratchpad_replace
    registry["scratchpad_delete"] = scratchpad_delete
    registry["scratchpad_lift"] = scratchpad_lift
    registry["_repo_root"] = str(repo_root)
    return registry


def _create(tools: dict[str, Any], name: str = "Q3 thinking", group: str = "strategy-and-value"):
    result = tools["scratchpad_create"](name=name, group=group, repo_root=tools["_repo_root"])
    assert result["ok"], result
    return result["scratchpad"]


class TestTheAgentLoop:
    def test_a_created_scratchpad_comes_back_seeded(self, tools: dict[str, Any]) -> None:
        created = _create(tools)

        assert created["artifact-id"].startswith("SCR@")
        assert {area["id"] for area in created["areas"]} == {
            "strategy", "portfolio", "project", "enabling"
        }

    def test_read_returns_a_document_replace_accepts(self, tools: dict[str, Any]) -> None:
        """The loop an agent has: read, edit the document, hand it back. If the two shapes differ
        by one key the agent has no way to bridge them."""
        created = _create(tools)
        read = tools["scratchpad_read"](
            artifact_id=created["artifact-id"], repo_root=tools["_repo_root"]
        )["scratchpad"]

        document = {key: value for key, value in read.items() if key != "group"}
        document["notes"] = [{"id": "n1", "title": "Grow into mid-market"}]
        document["layout"] = {**document.get("layout", {}), "notes": {"n1": [40, 60]}}

        written = tools["scratchpad_replace"](
            artifact_id=created["artifact-id"],
            scratchpad=document,
            version=read["version"],
            repo_root=tools["_repo_root"],
        )

        assert written["ok"], written
        assert [note["title"] for note in written["scratchpad"]["notes"]] == ["Grow into mid-market"]
        assert written["scratchpad"]["notes"][0]["area"] == "strategy"

    def test_an_edit_stays_in_the_collection_it_came_from(self, tools: dict[str, Any]) -> None:
        """`group` is optional on replace; omitting it must not re-home the scratchpad."""
        created = _create(tools, group="platform-core")
        read = tools["scratchpad_read"](
            artifact_id=created["artifact-id"], repo_root=tools["_repo_root"]
        )["scratchpad"]

        tools["scratchpad_replace"](
            artifact_id=created["artifact-id"],
            scratchpad={key: value for key, value in read.items() if key != "group"},
            version=read["version"],
            repo_root=tools["_repo_root"],
        )

        listed = tools["scratchpad_list"](repo_root=tools["_repo_root"])["scratchpads"]
        assert [summary["group"] for summary in listed] == ["platform-core"]


class TestRefusalsComeBackAsData:
    def test_an_unknown_scratchpad_reports_not_found(self, tools: dict[str, Any]) -> None:
        result = tools["scratchpad_read"](artifact_id="SCR@9.z.nothing", repo_root=tools["_repo_root"])

        assert result == {"ok": False, "error": "not_found", "message": result["message"]}
        assert "SCR@9.z.nothing" in result["message"]

    def test_a_stale_version_reports_a_conflict_rather_than_overwriting(
        self, tools: dict[str, Any]
    ) -> None:
        created = _create(tools)
        read = tools["scratchpad_read"](
            artifact_id=created["artifact-id"], repo_root=tools["_repo_root"]
        )["scratchpad"]
        document = {key: value for key, value in read.items() if key != "group"}
        tools["scratchpad_replace"](
            artifact_id=created["artifact-id"], scratchpad=document,
            version=read["version"], repo_root=tools["_repo_root"],
        )

        second = tools["scratchpad_replace"](
            artifact_id=created["artifact-id"], scratchpad=document,
            version=read["version"], repo_root=tools["_repo_root"],
        )

        assert second["error"] == "version_conflict"
        assert "Reload" in second["message"]

    def test_a_broken_invariant_names_the_id_at_fault(self, tools: dict[str, Any]) -> None:
        created = _create(tools)
        read = tools["scratchpad_read"](
            artifact_id=created["artifact-id"], repo_root=tools["_repo_root"]
        )["scratchpad"]
        document = {key: value for key, value in read.items() if key != "group"}
        document["notes"] = [{"id": "n1", "title": "A"}]
        document["links"] = [{"id": "l1", "source": "n1", "target": "ghost"}]

        result = tools["scratchpad_replace"](
            artifact_id=created["artifact-id"], scratchpad=document,
            version=read["version"], repo_root=tools["_repo_root"],
        )

        assert result["error"] == "refused"
        assert "ghost" in result["message"]


class TestListAndDelete:
    def test_listing_filters_and_omits_the_notes(self, tools: dict[str, Any]) -> None:
        _create(tools, "One", group="strategy-and-value")
        _create(tools, "Two", group="platform-core")

        filtered = tools["scratchpad_list"](group="platform-core", repo_root=tools["_repo_root"])

        assert [summary["name"] for summary in filtered["scratchpads"]] == ["Two"]
        assert "notes" not in filtered["scratchpads"][0]

    def test_delete_removes_it(self, tools: dict[str, Any]) -> None:
        created = _create(tools)

        deleted = tools["scratchpad_delete"](
            artifact_id=created["artifact-id"], repo_root=tools["_repo_root"]
        )

        assert deleted == {"ok": True, "deleted": created["artifact-id"]}
        assert tools["scratchpad_list"](repo_root=tools["_repo_root"])["scratchpads"] == []

    def test_deleting_what_is_not_there_reports_not_found(self, tools: dict[str, Any]) -> None:
        assert tools["scratchpad_delete"](
            artifact_id="SCR@9.z.nothing", repo_root=tools["_repo_root"]
        )["error"] == "not_found"


class TestLiftingFromAnAgent:
    """An agent gets the same preflight a person does, in the same vocabulary.

    That is the whole claim of parity on this feature: the surface a newcomer starts on must not be
    the one an agent cannot help with, and a lift is the moment help is worth most.
    """

    def _typed(self, tools: dict[str, Any]) -> dict[str, Any]:
        created = _create(tools)
        document = {key: value for key, value in created.items() if key != "group"}
        document["notes"] = [
            {"id": "n1", "title": "Grow into mid-market", "destination": "element",
             "element-type": "goal"},
            {"id": "n2", "title": "Still thinking"},
        ]
        stored = tools["scratchpad_replace"](
            artifact_id=created["artifact-id"],
            scratchpad=document,
            version=created["version"],
            repo_root=tools["_repo_root"],
        )
        assert stored["ok"], stored
        return stored["scratchpad"]

    def test_a_preflight_reports_what_would_be_created_and_writes_nothing(
        self, tools: dict[str, Any]
    ) -> None:
        pad = self._typed(tools)

        answer = tools["scratchpad_lift"](
            artifact_id=pad["artifact-id"], selection=["n1"], version=pad["version"],
            repo_root=tools["_repo_root"],
        )

        assert answer["ok"], answer
        lift = answer["lift"]
        assert [item["id"] for item in lift["items"] if item["outcome"] == "create"] == ["n1"]
        assert lift["dry-run"] is True and lift["committed"] is False

    def test_an_undecided_note_blocks_the_lift_with_a_reason_an_agent_can_act_on(
        self, tools: dict[str, Any]
    ) -> None:
        pad = self._typed(tools)

        lift = tools["scratchpad_lift"](
            artifact_id=pad["artifact-id"], selection=["n1", "n2"], version=pad["version"],
            repo_root=tools["_repo_root"],
        )["lift"]

        refused = [item for item in lift["items"] if item["outcome"] == "refuse"]
        assert lift["blocks"] is True
        assert refused[0]["id"] == "n2" and refused[0]["reason"]

    def test_lifting_an_unknown_scratchpad_is_data_rather_than_an_exception(
        self, tools: dict[str, Any]
    ) -> None:
        answer = tools["scratchpad_lift"](
            artifact_id="SCR@9.z.nothing", selection=["n1"], version="0.1.0",
            repo_root=tools["_repo_root"],
        )

        assert answer == {"ok": False, "error": "not_found", "message": answer["message"]}
