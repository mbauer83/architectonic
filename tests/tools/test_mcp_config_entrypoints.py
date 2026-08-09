from __future__ import annotations

import asyncio
import json
import tomllib
from pathlib import Path
from typing import Any

import pytest

from src.infrastructure.mcp.mcp_artifact_server import mcp_read, mcp_write
from src.infrastructure.mcp.mcp_assurance_server import mcp_assurance_read, mcp_assurance_write

ROOT = Path(__file__).resolve().parents[2]

#: The four hints MCP defines. A host warns a user with these before invoking a tool, so a hint
#: left unset is one a host cannot warn about — which is why the check below is `isinstance(bool)`
#: rather than truthiness: `None` is what an unannotated tool answers, and it reads as "false".
SAFETY_HINTS = ("readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint")

READ_MOUNTS = (("arch-repo-read", mcp_read), ("arch-assurance-read", mcp_assurance_read))
WRITE_MOUNTS = (("arch-repo-write", mcp_write), ("arch-assurance-write", mcp_assurance_write))
ALL_MOUNTS = READ_MOUNTS + WRITE_MOUNTS


def _served_tools(server: Any) -> dict[str, Any]:
    """The tools a client is served, through the accessor a client goes through.

    `server.list_tools()` rather than `server._tool_manager.list_tools()`: the public one needs no
    `# type: ignore[attr-defined]`, and it is the same call the transport makes, so a tool that
    registered but does not survive the listing cannot pass this file.
    """
    return {tool.name: tool for tool in asyncio.run(server.list_tools())}


def _load_json(relative_path: str) -> dict:
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def test_project_scripts_do_not_expose_legacy_arch_model_stdio_aliases() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    scripts = project["project"]["scripts"]

    assert "arch-model-read" not in scripts
    assert "arch-model-write" not in scripts


def test_checked_in_mcp_configs_use_supported_stdio_entrypoints() -> None:
    # Every checked-in stdio entrypoint must be a supported console script. The two
    # architecture servers are always present; the assurance servers are optional
    # (documented opt-in), so this is a subset check rather than exact equality.
    supported = {
        "arch-mcp-stdio-read",
        "arch-mcp-stdio-write",
        "arch-mcp-stdio-assurance-read",
        "arch-mcp-stdio-assurance-write",
    }
    supported_args = {("run", command) for command in supported}
    required_args = {("run", "arch-mcp-stdio-read"), ("run", "arch-mcp-stdio-write")}

    claude_config = _load_json(".mcp.json")
    vscode_config = _load_json(".vscode/mcp.json")

    claude_args = {tuple(server["args"]) for server in claude_config["mcpServers"].values()}
    vscode_args = {tuple(server["args"]) for server in vscode_config["servers"].values()}

    assert claude_args <= supported_args, f"unsupported entrypoint in .mcp.json: {claude_args - supported_args}"
    assert vscode_args <= supported_args, f"unsupported entrypoint in .vscode/mcp.json: {vscode_args - supported_args}"
    assert required_args <= claude_args
    assert required_args <= vscode_args


@pytest.mark.parametrize(("mount", "server"), ALL_MOUNTS, ids=[name for name, _ in ALL_MOUNTS])
def test_every_tool_on_every_mount_declares_all_four_safety_hints(mount: str, server: Any) -> None:
    """A tool that declares no hints is a tool a host cannot warn a user about.

    This is a loop over the served surface rather than a list of names, and that is the whole
    point. The write mount was covered by an enumeration of sixteen tools, so it reported green
    while all forty-five tools on the two assurance mounts carried `annotations=None` — a new
    unannotated tool would have passed it too. An audit found the gap; a test should have.
    """
    tools = _served_tools(server)
    assert tools, f"{mount} served no tools, which would make every assertion below vacuous"

    for name, tool in tools.items():
        annotations = tool.annotations
        assert annotations is not None, f"{mount}/{name} declares no annotations"
        for hint in SAFETY_HINTS:
            value = getattr(annotations, hint)
            assert isinstance(value, bool), f"{mount}/{name}.{hint} is {value!r}, not a bool"


@pytest.mark.verifies("REQ@1785945042.cbXjYz")
@pytest.mark.parametrize(("mount", "server"), READ_MOUNTS, ids=[name for name, _ in READ_MOUNTS])
def test_read_server_tools_are_marked_read_only(mount: str, server: Any) -> None:
    """The context an agent is served is authoritative; what it builds on it is not.

    Every tool on a read bridge announces itself read-only and non-destructive, so nothing an
    agent derives can become model content without going through the authoring surfaces. This
    holds for the assurance read mount for the same reason it holds for the architecture one:
    both serve an analyst session that must not be able to write through what it reads.
    """
    tools = _served_tools(server)
    assert tools, f"{mount} served no tools"

    for name, tool in tools.items():
        ann = tool.annotations
        assert ann is not None, name
        assert ann.readOnlyHint is True, f"{mount}/{name}"
        assert ann.destructiveHint is False, f"{mount}/{name}"
        assert ann.idempotentHint is True, f"{mount}/{name}"
        assert ann.openWorldHint is False, f"{mount}/{name}"


def test_write_server_catalog_and_guidance_are_read_only_yaml_tools() -> None:
    tools = {tool.name: tool for tool in mcp_write._tool_manager.list_tools()}  # type: ignore[attr-defined]

    for name in ("artifact_help", "artifact_authoring_guidance", "artifact_get_operation"):
        tool = tools[name]
        ann = tool.annotations
        assert ann is not None, name
        assert ann.readOnlyHint is True, name
        assert ann.destructiveHint is False, name
        assert ann.idempotentHint is True, name
        assert ann.openWorldHint is False, name
        if name != "artifact_get_operation":
            assert tool.fn_metadata.output_schema is None, name


def test_write_server_mutation_tool_annotations_match_expected_intent() -> None:
    tools = {tool.name: tool for tool in mcp_write._tool_manager.list_tools()}  # type: ignore[attr-defined]

    expected = {
        "artifact_create_entity": (False, False, False, False),
        "artifact_add_connection": (False, False, False, False),
        "artifact_create_matrix": (False, False, False, False),
        "artifact_create_diagram": (False, False, False, False),
        "artifact_create_document": (False, False, False, False),
        "artifact_edit_document": (False, False, False, False),
        "artifact_edit_entity": (False, False, False, False),
        "artifact_edit_connection": (False, True, False, False),
        "artifact_edit_diagram": (False, False, False, False),
        "artifact_edit_connection_associations": (False, False, False, False),
        "artifact_bulk_write": (False, False, False, False),
        "artifact_bulk_delete": (False, True, False, False),
        "artifact_promote_to_enterprise": (False, True, False, False),
        "artifact_save_changes": (False, False, False, True),
        "artifact_submit_for_review": (False, False, False, True),
        # destructive AND open-world: withdraw deletes the REMOTE review branch.
        "artifact_withdraw_changes": (False, True, False, True),
    }

    for name, (read_only, destructive, idempotent, open_world) in expected.items():
        tool = tools[name]
        ann = tool.annotations
        assert ann is not None, name
        assert ann.readOnlyHint is read_only, name
        assert ann.destructiveHint is destructive, name
        assert ann.idempotentHint is idempotent, name
        assert ann.openWorldHint is open_world, name


def test_assurance_write_mount_annotations_match_expected_intent() -> None:
    """What each assurance write tool does to the store, stated rather than inferred.

    The sibling test above does this for the architecture write mount. Both are enumerations on
    purpose: the loop over every mount catches a *missing* classification, and only a table
    catches a *wrong* one — a delete quietly reclassified as additive is exactly the change a
    host would stop warning about, and exactly the change no loop can see.
    """
    tools = _served_tools(mcp_assurance_write)

    expected = {
        # Additive graph and lifecycle writes.
        "assurance_create_node": (False, False, False, False),
        "assurance_add_edge": (False, False, False, False),
        # edit_node cannot retype a node — node_type is not among its updatable fields — so it is
        # additive in the sense artifact_edit_entity is, not replacing like artifact_edit_connection.
        "assurance_edit_node": (False, False, False, False),
        "assurance_seal_baseline": (False, False, False, False),
        "assurance_register_arch_ref": (False, False, False, False),
        "assurance_create_analysis": (False, False, False, False),
        "assurance_update_analysis": (False, False, False, False),
        "assurance_set_fmea_factor": (False, False, False, False),
        "assurance_create_group": (False, False, False, False),
        "assurance_file_analysis": (False, False, False, False),
        "assurance_add_analysis_member": (False, False, False, False),
        "assurance_ingest_security_signals": (False, False, False, False),
        "assurance_reconcile_aibom": (False, False, False, False),
        # Set-once by construction: re-asserting the same analysis changes nothing, which is the
        # one write on this mount a caller may safely repeat after a dropped response.
        "assurance_assign_provenance": (False, False, True, False),
        # Destructive: each removes something the audit trail cannot give back.
        "assurance_delete_node": (False, True, False, False),
        "assurance_delete_edge": (False, True, False, False),
        "assurance_delete_analysis": (False, True, False, False),
        "assurance_delete_group": (False, True, False, False),
        "assurance_remove_analysis_member": (False, True, False, False),
        "assurance_delete_security_snapshot": (False, True, False, False),
        # Reads in write clothing, like artifact_help on the architecture write mount.
        # model_this returns a task spec before touching the store: this mount holds no
        # architecture-write port, so its arch_creator is always None and it returns TaskRequired.
        "assurance_model_this": (True, False, True, False),
        "assurance_promotion_preflight": (True, False, True, False),
    }

    assert set(expected) == set(tools), (
        "the assurance write mount and this table have diverged; "
        f"unlisted: {sorted(set(tools) - set(expected))}, stale: {sorted(set(expected) - set(tools))}"
    )

    for name, (read_only, destructive, idempotent, open_world) in expected.items():
        ann = tools[name].annotations
        assert ann is not None, name
        assert ann.readOnlyHint is read_only, name
        assert ann.destructiveHint is destructive, name
        assert ann.idempotentHint is idempotent, name
        assert ann.openWorldHint is open_world, name
