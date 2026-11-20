"""Every scratchpad capability is reachable by an agent and by a person, and by the same route.

Parity here is a property of *this feature*, not of the platform. `PRI@1780220699` deliberately
disclaims full parity across every surface, and it is right to: MCP serves agents, the CLI serves CI,
REST serves GUIs, and their audiences differ. The scratchpad has a local reason the platform as a
whole does not — it is the lowest-barrier surface, the place a newcomer starts. A human-only version
would make that the one place an agent cannot help, which inverts the product's own claim to be for
humans *and* AI. The reason is local, so it is recorded locally: in the scratchpad's ADR, and here.

Two things are asserted, and the second is the one that lasts:

1. the two surfaces expose the same set of capabilities, named the same way;
2. **both go through `ScratchpadService`, and neither has a path into storage the other lacks.**

The first alone decays into a list someone updates. The second is what makes the first true by
construction: as long as the service is the only door, a capability cannot exist on one surface
without a method that the other could equally adapt.
"""

from __future__ import annotations

import ast
import inspect
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.application.scratchpad.service import ScratchpadService
from src.infrastructure.rest.route_policy import ROUTE_POLICY

_SRC = Path(__file__).resolve().parents[2] / "src"
_MCP_TOOLS = _SRC / "infrastructure" / "mcp" / "artifact_mcp" / "scratchpad_tools.py"
_REST_ROUTER = _SRC / "infrastructure" / "rest" / "routers" / "scratchpads.py"

#: The capability names, surface-independent. Both surfaces spell them the same way, so the
#: comparison is over words rather than over a translation table nobody maintains.
_CAPABILITIES = frozenset({"list", "read", "create", "replace", "edit", "delete", "lift"})


def _mcp_tool_names() -> frozenset[str]:
    """Tool names as registered — read from the source, so a tool that is defined but never
    registered does not count as a capability an agent has.

    Two registration forms, because a mutating tool must not use the plain one: reads go through
    `@mcp.tool`, writes through `register_mutation_tool`, which is what puts them behind the write
    queue and the authorization gate. Both name the tool with `name=`.
    """
    tree = ast.parse(_MCP_TOOLS.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        registers = (
            (isinstance(node.func, ast.Attribute) and node.func.attr == "tool")
            or (isinstance(node.func, ast.Name) and node.func.id == "register_mutation_tool")
        )
        if not registers:
            continue
        for keyword in node.keywords:
            if keyword.arg == "name" and isinstance(keyword.value, ast.Constant):
                names.add(str(keyword.value.value))
    return frozenset(names)


def test_every_scratchpad_write_goes_through_the_mutation_executor() -> None:
    """A mutating MCP tool registered with a bare `@mcp.tool` writes outside the serialisation
    every other mutator observes, and no manifest row classifies its intent — registration refuses
    without one, so this asserts the writes reach that refusal rather than dodging it."""
    from src.infrastructure.mcp.artifact_mcp.mutation_registration import MUTATION_TOOL_MANIFEST

    writes = {f"scratchpad_{capability}" for capability in ("create", "replace", "delete", "lift")}
    assert writes <= _mcp_tool_names(), sorted(writes - _mcp_tool_names())
    for name in writes:
        assert name in MUTATION_TOOL_MANIFEST, f"{name} mutates the repository with no manifest row"


def _rest_operation_ids() -> frozenset[str]:
    return frozenset(
        row.operation_id for row in ROUTE_POLICY if row.operation_id.startswith("scratchpads_")
    )


def test_the_scan_finds_both_surfaces() -> None:
    # Without this, a renamed module would report perfect parity between two empty sets.
    assert _MCP_TOOLS.is_file(), _MCP_TOOLS
    assert _mcp_tool_names(), "no MCP scratchpad tools found — has the module moved?"
    assert _rest_operation_ids(), "no scratchpad rows in the route-policy manifest"


def test_an_agent_can_do_everything_a_person_can() -> None:
    mcp_capabilities = frozenset(name.removeprefix("scratchpad_") for name in _mcp_tool_names())

    assert mcp_capabilities == _CAPABILITIES, (
        "the MCP surface does not offer exactly the scratchpad capabilities: "
        f"missing {sorted(_CAPABILITIES - mcp_capabilities)}, "
        f"unexpected {sorted(mcp_capabilities - _CAPABILITIES)}"
    )


def test_a_person_can_do_everything_an_agent_can() -> None:
    rest_capabilities = frozenset(
        operation_id.removeprefix("scratchpads_").removesuffix("_scratchpad").removesuffix("_scratchpads")
        for operation_id in _rest_operation_ids()
    )

    assert rest_capabilities == _CAPABILITIES, (
        "the REST surface does not offer exactly the scratchpad capabilities: "
        f"missing {sorted(_CAPABILITIES - rest_capabilities)}, "
        f"unexpected {sorted(rest_capabilities - _CAPABILITIES)}"
    )


def test_the_service_offers_exactly_those_capabilities_and_no_more() -> None:
    """A method here that no surface adapts is a capability one of them could quietly acquire.

    `group_of` is not a capability: it answers which collection a scratchpad sits in, which both
    surfaces need in order to save an edit back where it came from.
    """
    public = frozenset(
        name for name, _ in inspect.getmembers(ScratchpadService, inspect.isfunction)
        if not name.startswith("_")
    )
    #: `list` is spelled `list_scratchpads` on the service, since `list` is a builtin.
    expected = (_CAPABILITIES - {"list"}) | {"list_scratchpads", "group_of"}
    assert public == expected, sorted(public)


def _reaches_only_the_service(module: Path) -> bool:
    """Whether *module* touches the repository directly instead of going through the service.

    The construction in the composition root is expected — someone has to build the service. What
    must not appear is a call to a repository method, which would be a second door into storage.
    """
    tree = ast.parse(module.read_text(encoding="utf-8"))
    repository_methods = {"save", "load", "list_scratchpads", "delete", "group_of"}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        target = node.func.value
        is_repository = (
            isinstance(target, ast.Call)
            and isinstance(target.func, ast.Name)
            and target.func.id == "YamlScratchpadRepository"
        )
        if is_repository and node.func.attr in repository_methods:
            return False
    return True


def test_neither_surface_reaches_past_the_service_into_storage() -> None:
    """The property that makes parity structural rather than a list to maintain."""
    for module in (_MCP_TOOLS, _REST_ROUTER):
        assert _reaches_only_the_service(module), (
            f"{module.name} calls the repository directly. Both surfaces go through "
            "ScratchpadService, or one of them gains a capability the other cannot express."
        )


def test_both_surfaces_write_the_whole_aggregate_and_carry_a_version() -> None:
    """A per-item write on one surface is how parity is lost in practice: it is cheap to add to
    the agent surface, awkward on the canvas, and the two drift from there."""
    for module in (_MCP_TOOLS, _REST_ROUTER):
        source = module.read_text(encoding="utf-8")
        assert "expected_version" in source, f"{module.name} writes without a concurrency token"
        for absent in ("add_note", "remove_note", "add_link", "remove_link", "move_note"):
            assert absent not in source, (
                f"{module.name} offers a per-item write ({absent}); both surfaces read-modify-replace"
            )


# ── The two surfaces refuse the same writes, in the same words ───────────────────────────────────
#
# The scan above holds the surfaces equal as sets of capabilities. What follows drives both against
# one repository, because a refusal is the part of a capability an agent and a person most need to
# agree on: the sentence names the note at fault and says what to do instead, and it is the
# aggregate's — so neither surface may reword it, and neither may let through what the other stops.

#: (what is attempted, the write shape, what changes) — each a transition the aggregate's own
#: mutations refuse.
_REFUSED_WRITES: list[tuple[str, str, dict[str, Any]]] = [
    ("retype a realized note", "replace", {"notes": {"lifted": {"element-type": "goal"}}}),
    ("retype a realized note", "edit", {"notes": [{"id": "lifted", "element-type": "goal"}]}),
    ("untype a bound note", "edit", {"notes": [{"id": "bound", "element-type": None}]}),
    ("send a realized note to a document", "edit", {"notes": [{
        "id": "lifted", "destination": "document", "element-type": None, "document-type": "adr",
    }]}),
    ("re-bind a realized note", "replace", {"notes": {"lifted": {
        "model-ref": {"artifact-id": "REQ@1.b.other", "kind": "bound"},
    }}}),
    ("change the meta-ontology under typed notes", "replace", {"meta-ontology": "sysml-v2-min"}),
]


@pytest.fixture
def one_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[TestClient, str, str]]:
    """A REST client and a repository root over the same stored scratchpad, which holds a realized
    note and a bound one — written through the repository, as a lift records them."""
    from src.domain.scratchpad import ModelRef, Note, scratchpad_from_parts
    from src.infrastructure.rest.routers import scratchpads as scratchpad_router
    from src.infrastructure.rest.routers import state as rest_state
    from src.infrastructure.scratchpad.yaml_repository import YamlScratchpadRepository
    from tests.support.api_app import build_api_app

    repo_root = tmp_path / "architecture-repository"
    repo_root.mkdir()
    stored = YamlScratchpadRepository(repo_root).save(
        scratchpad_from_parts(artifact_id="SCR@1.a.pad", name="Pad", notes=[
            Note(id="lifted", title="Lifted", destination="element", element_type="requirement",
                 model_ref=ModelRef("REQ@1.a.x", "realized")),
            Note(id="bound", title="Bound", destination="element", element_type="capability",
                 model_ref=ModelRef("CAP@1.a.x", "bound")),
        ]),
        group="thinking",
    )
    monkeypatch.setattr(rest_state, "maybe_engagement_root", lambda: repo_root)
    monkeypatch.setattr(
        rest_state, "authorized_write", lambda _operation_id, fn, *args, **kwargs: fn(*args, **kwargs)
    )
    with TestClient(build_api_app(scratchpad_router.router)) as client:
        yield client, str(repo_root), stored.artifact_id


def _replaced(document: dict[str, Any], changes: dict[str, Any]) -> dict[str, Any]:
    """The read document with *changes* applied, as a caller editing what it read would send it."""
    patched = {key: value for key, value in document.items() if key not in ("group", "notes")}
    patched.update({key: value for key, value in changes.items() if key != "notes"})
    per_note: dict[str, dict[str, Any]] = changes.get("notes", {})
    patched["notes"] = [{**note, **per_note.get(note["id"], {})} for note in document["notes"]]
    return patched


@pytest.mark.parametrize(("attempt", "shape", "changes"), _REFUSED_WRITES)
def test_both_surfaces_refuse_a_forbidden_transition_in_the_same_words(
    one_repository: tuple[TestClient, str, str], attempt: str, shape: str, changes: dict[str, Any]
) -> None:
    from src.infrastructure.mcp.artifact_mcp.scratchpad_tools import (
        scratchpad_edit,
        scratchpad_replace,
    )

    client, repo_root, artifact_id = one_repository
    address = f"/api/scratchpads/{artifact_id}"
    read = client.get(address).json()

    if shape == "replace":
        document = _replaced(read, changes)
        over_rest = client.put(address, json={
            "version": read["version"], "group": read["group"], "scratchpad": document,
        })
        over_mcp = scratchpad_replace(
            artifact_id=artifact_id, scratchpad=document, version=read["version"],  # type: ignore[arg-type]
            repo_root=repo_root,
        )
    else:
        over_rest = client.patch(address, json={"version": read["version"], "upsert": changes})
        over_mcp = scratchpad_edit(
            artifact_id=artifact_id, version=read["version"], upsert=changes,  # type: ignore[arg-type]
            repo_root=repo_root,
        )

    assert over_rest.status_code == 400, f"REST let through: {attempt} — {over_rest.text}"
    assert over_mcp["ok"] is False, f"MCP let through: {attempt}"
    assert over_mcp["error"] == "refused"
    assert over_rest.json()["detail"]["message"] == over_mcp["message"]
    # Refused, so nothing moved: the version both were written against is still the store's.
    assert client.get(address).json()["version"] == read["version"]
