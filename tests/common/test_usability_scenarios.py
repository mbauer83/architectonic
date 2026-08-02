"""Guards for the usability scenarios (tools/usability_test/scenarios/).

The load-bearing test here is route resolution. A scenario's answer key names the routes
that would have been correct; if a route is renamed, retired or moved and the answer key
is not, the key rots silently and the next run scores personas against surfaces that no
longer exist. So every typed route reference is resolved against the real system — the
frontend router, the registered MCP tools, the shipped viewpoint library, the docs tree,
and the console scripts — and a dangling reference fails the suite.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]

_REPO_ROOT = Path(__file__).resolve().parents[2]
_USABILITY_DIR = _REPO_ROOT / "tools" / "usability_test"
_SCENARIOS_DIR = _USABILITY_DIR / "scenarios"
_ROUTER_DIR = _REPO_ROOT / "tools" / "gui" / "src" / "ui" / "router"
#: Every module of the router package, not a named few. The table names most of its paths through
#: `ROUTE_TEMPLATES`, so the catalogue has to be read as well as the table — and a hand-written list
#: of which files those are goes stale the moment a route table is split out, which is what happened
#: when `modelRoutes.ts` was extracted: the oracle silently stopped knowing about `/search` and
#: every other model route, and only a scenario that referenced one made it visible.
_VIEWPOINT_LIBRARY = _REPO_ROOT / "src" / "ontologies" / "archimate_4" / "viewpoints.yaml"

_KEBAB = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_ROUTER_PATH = re.compile(r"(?:path:\s*|:\s*)'(/[^']*)'")

_REQUIRED_SCENARIO_FIELDS = frozenset({
    "schema", "kind", "id", "title", "work_type", "channels", "situation", "stakes",
    "write_policy", "preconditions", "surfaces", "participants",
})
_REQUIRED_TASK_FIELDS = frozenset({
    "id", "text", "information_need", "decision_artifact", "expected_route",
})


def _load_yaml(path: Path) -> dict[str, Any]:
    loaded: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


@pytest.fixture(scope="module")
def vocabularies() -> dict[str, Any]:
    return _load_yaml(_USABILITY_DIR / "vocabularies.yaml")


@pytest.fixture(scope="module")
def personas() -> dict[str, dict[str, Any]]:
    catalog = _load_yaml(_USABILITY_DIR / "personas.yaml")
    return {str(persona["id"]): persona for persona in catalog["personas"]}


@pytest.fixture(scope="module")
def scenarios() -> dict[str, dict[str, Any]]:
    return {path.stem: _load_yaml(path) for path in sorted(_SCENARIOS_DIR.glob("*.yaml"))}


def _ids(vocabularies: dict[str, Any], name: str) -> frozenset[str]:
    return frozenset(str(entry["id"]) for entry in vocabularies[name])


def _iter_tasks(scenario: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    return [(p, task) for p in scenario["participants"] for task in p["tasks"]]


def _iter_route_refs(scenario: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Every typed route reference in a scenario, with the label to report it under."""
    refs = [(f"{scenario['id']}/surfaces", ref) for ref in scenario["surfaces"]]
    for _, task in _iter_tasks(scenario):
        refs.extend(
            (f"{scenario['id']}/{task['id']}", ref)
            for ref in task["expected_route"]["candidates"]
        )
    return refs


# ---------------------------------------------------------------------------
# The real-system resolvers.
# ---------------------------------------------------------------------------


def _known_gui_routes() -> frozenset[str]:
    modules = sorted(
        path for path in _ROUTER_DIR.glob("*.ts") if not path.name.endswith(".test.ts")
    )
    assert modules, f"no router modules under {_ROUTER_DIR}"
    return frozenset(
        route
        for path in modules
        for route in _ROUTER_PATH.findall(path.read_text(encoding="utf-8"))
    )


def test_the_frontend_route_oracle_is_not_empty() -> None:
    """Guards the guard below.

    The route table names most of its paths through ``ROUTE_TEMPLATES`` rather than spelling them,
    so a scan of that file alone finds a handful of literals — and every scenario reference would
    then be checked against almost nothing. A floor is what makes the shrinkage visible.
    """
    known = _known_gui_routes()
    assert len(known) >= 30, f"the frontend route oracle found only {sorted(known)}"
    for expected in ("/entities", "/entities/:artifactId", "/assurance"):
        assert expected in known, f"{expected} missing from the route oracle"


def _known_mcp_tools() -> frozenset[str]:
    from src.infrastructure.mcp.mcp_artifact_server import mcp_read, mcp_write  # noqa: PLC0415
    from src.infrastructure.mcp.mcp_assurance_server import (  # noqa: PLC0415
        mcp_assurance_read,
        mcp_assurance_write,
    )

    servers = (mcp_read, mcp_write, mcp_assurance_read, mcp_assurance_write)
    return frozenset(
        tool.name
        for server in servers
        for tool in server._tool_manager.list_tools()  # type: ignore[attr-defined]
    )


def _known_viewpoint_slugs() -> frozenset[str]:
    library: Any = yaml.safe_load(_VIEWPOINT_LIBRARY.read_text(encoding="utf-8"))
    return frozenset(str(entry["slug"]) for entry in library["viewpoints"])


def _known_cli_entry_points() -> frozenset[str]:
    with (_REPO_ROOT / "pyproject.toml").open("rb") as handle:
        return frozenset(tomllib.load(handle)["project"]["scripts"])


# ---------------------------------------------------------------------------
# Structure.
# ---------------------------------------------------------------------------


def test_at_least_one_scenario_per_evaluated_channel(scenarios: dict[str, dict[str, Any]]) -> None:
    """The framework exists to reach both channels; a GUI-only set of scenarios is the
    state this iteration replaced."""
    covered = {channel for scenario in scenarios.values() for channel in scenario["channels"]}
    assert {"gui", "mcp"} <= covered


def test_scenarios_declare_every_required_field(scenarios: dict[str, dict[str, Any]]) -> None:
    for scenario_id, scenario in scenarios.items():
        missing = _REQUIRED_SCENARIO_FIELDS - scenario.keys()
        assert not missing, f"{scenario_id}: missing {sorted(missing)}"
        assert scenario["schema"] == 1
        assert scenario["kind"] == "usability-scenario"
        assert scenario["id"] == scenario_id, "the declared id must equal the file stem"
        assert _KEBAB.match(scenario_id), f"{scenario_id}: scenario ids are kebab-case slugs"
        assert scenario["participants"], f"{scenario_id}: no participants"


def test_scenario_controlled_values_resolve(
    scenarios: dict[str, dict[str, Any]], vocabularies: dict[str, Any]
) -> None:
    work_types = _ids(vocabularies, "work_types")
    channels = _ids(vocabularies, "channels")
    policies = _ids(vocabularies, "mutation_policies")
    artifacts = _ids(vocabularies, "decision_artifacts")
    actions = _ids(vocabularies, "route_actions")
    for scenario_id, scenario in scenarios.items():
        assert scenario["work_type"] in work_types, scenario_id
        assert scenario["channels"], f"{scenario_id}: no channels"
        for channel in scenario["channels"]:
            assert channel in channels, f"{scenario_id}: unknown channel {channel!r}"
        assert scenario["write_policy"]["mutations"] in policies, scenario_id
        for _, task in _iter_tasks(scenario):
            assert task["decision_artifact"] in artifacts, task["id"]
            assert task["expected_route"]["action"] in actions, task["id"]


def test_tasks_are_complete_and_unique_within_a_scenario(scenarios: dict[str, dict[str, Any]]) -> None:
    for scenario_id, scenario in scenarios.items():
        seen: list[str] = []
        for _, task in _iter_tasks(scenario):
            missing = _REQUIRED_TASK_FIELDS - task.keys()
            assert not missing, f"{scenario_id}/{task.get('id')}: missing {sorted(missing)}"
            assert _KEBAB.match(str(task["id"])), f"{task['id']}: task ids are kebab-case slugs"
            assert task["id"] not in seen, f"{scenario_id}: duplicate task id {task['id']}"
            seen.append(str(task["id"]))
            budget = task.get("budget_actions")
            assert budget is None or (isinstance(budget, int) and budget > 0), task["id"]


def test_participants_and_their_channels_resolve_against_the_persona_catalog(
    scenarios: dict[str, dict[str, Any]], personas: dict[str, dict[str, Any]]
) -> None:
    """A scenario worked through a channel none of its participants uses is a scenario
    nobody in it could actually have performed."""
    for scenario_id, scenario in scenarios.items():
        taking_part = [str(p["persona"]) for p in scenario["participants"]]
        assert len(taking_part) == len(set(taking_part)), f"{scenario_id}: duplicate participant"
        for persona_id in taking_part:
            assert persona_id in personas, f"{scenario_id}: unknown persona {persona_id!r}"
        for channel in scenario["channels"]:
            assert any(channel in personas[p]["channels"] for p in taking_part), (
                f"{scenario_id}: no participant works the {channel!r} channel"
            )


def test_recurring_question_references_resolve_to_the_referencing_persona(
    scenarios: dict[str, dict[str, Any]], personas: dict[str, dict[str, Any]]
) -> None:
    for scenario_id, scenario in scenarios.items():
        for participant, task in _iter_tasks(scenario):
            referenced = task.get("recurring_question")
            if referenced is None:
                continue
            persona = personas[str(participant["persona"])]
            known = {str(q["id"]) for q in persona["recurring_questions"]}
            assert referenced in known, (
                f"{scenario_id}/{task['id']}: {referenced!r} is not a standing question of "
                f"{participant['persona']}"
            )


def test_expertise_overrides_use_the_declared_axes_and_levels(
    scenarios: dict[str, dict[str, Any]], vocabularies: dict[str, Any]
) -> None:
    axes = _ids(vocabularies, "expertise_axes")
    levels = _ids(vocabularies, "expertise_levels")
    for scenario_id, scenario in scenarios.items():
        for participant in scenario["participants"]:
            for axis, level in (participant.get("expertise_overrides") or {}).items():
                assert axis in axes, f"{scenario_id}: unknown expertise axis {axis!r}"
                assert level in levels, f"{scenario_id}/{axis}: unknown level {level!r}"


def test_only_situational_axes_are_overridden(
    scenarios: dict[str, dict[str, Any]], vocabularies: dict[str, Any]
) -> None:
    """A scenario may restate an axis whose meaning depends on the situation, and no other.

    The rest describe the person: a scenario that restated one would make the same persona
    two different subjects, so findings scored against it would stop being comparable across
    runs. Someone who differs on those axes is a different persona.
    """
    allowed = frozenset(
        str(axis["id"]) for axis in vocabularies["expertise_axes"] if axis.get("overridable") is True
    )
    assert allowed, "no axis is marked overridable — the vocabulary lost its `overridable` flags"
    for scenario_id, scenario in scenarios.items():
        for participant in scenario["participants"]:
            offending = sorted(set(participant.get("expertise_overrides") or {}) - allowed)
            assert not offending, (
                f"{scenario_id}/{participant['persona']}: may not override {offending} — "
                f"overridable axes are {sorted(allowed)}"
            )


def test_execute_tasks_name_a_candidate_and_others_may_not_need_one(
    scenarios: dict[str, dict[str, Any]]
) -> None:
    """Route-hit scoring only means something when there is a route to hit. Every other
    action is scored on route-class recognition, where an empty candidate list is the
    honest answer key: nothing shipped fits."""
    for scenario_id, scenario in scenarios.items():
        for _, task in _iter_tasks(scenario):
            if task["expected_route"]["action"] == "execute":
                assert task["expected_route"]["candidates"], (
                    f"{scenario_id}/{task['id']}: an execute task with no candidate route"
                )


def test_mutating_scenarios_declare_a_namespace_and_a_cleanup(
    scenarios: dict[str, dict[str, Any]]
) -> None:
    """A run that writes without a namespace and a cleanup cannot be restored, and an
    unrestorable run contaminates every run after it."""
    for scenario_id, scenario in scenarios.items():
        policy = scenario["write_policy"]
        if policy["mutations"] != "run-scoped":
            continue
        assert policy.get("slug_prefix"), f"{scenario_id}: run-scoped writes without a namespace"
        cleanup = _REPO_ROOT / str(policy.get("cleanup", ""))
        assert cleanup.is_file(), f"{scenario_id}: cleanup helper {policy.get('cleanup')!r} not found"


def test_preconditions_and_invariants_state_how_they_are_established(
    scenarios: dict[str, dict[str, Any]]
) -> None:
    for scenario_id, scenario in scenarios.items():
        for block in ("preconditions", "invariants"):
            for entry in scenario.get(block) or []:
                assert entry.get("id") and entry.get("statement"), f"{scenario_id}/{block}"
                assert entry.get("verification_method"), (
                    f"{scenario_id}/{block}/{entry.get('id')}: no verification method — a "
                    "claim nobody knows how to check cannot be preflighted"
                )


# ---------------------------------------------------------------------------
# Route resolution against the real system.
# ---------------------------------------------------------------------------


def test_every_route_reference_declares_a_known_kind(
    scenarios: dict[str, dict[str, Any]], vocabularies: dict[str, Any]
) -> None:
    kinds = _ids(vocabularies, "route_kinds")
    for scenario in scenarios.values():
        for label, ref in _iter_route_refs(scenario):
            assert ref.keys() == {"kind", "ref"}, f"{label}: a route reference is {{kind, ref}}"
            assert ref["kind"] in kinds, f"{label}: unknown route kind {ref['kind']!r}"


def test_gui_route_references_resolve_against_the_frontend_router(
    scenarios: dict[str, dict[str, Any]]
) -> None:
    known = _known_gui_routes()
    for scenario in scenarios.values():
        for label, ref in _iter_route_refs(scenario):
            if ref["kind"] == "gui-route":
                assert ref["ref"] in known, f"{label}: no such frontend route {ref['ref']!r}"


def test_mcp_tool_references_resolve_against_the_registered_tools(
    scenarios: dict[str, dict[str, Any]]
) -> None:
    known = _known_mcp_tools()
    for scenario in scenarios.values():
        for label, ref in _iter_route_refs(scenario):
            if ref["kind"] == "mcp-tool":
                assert ref["ref"] in known, f"{label}: no such MCP tool {ref['ref']!r}"


def test_viewpoint_references_resolve_against_the_shipped_library(
    scenarios: dict[str, dict[str, Any]]
) -> None:
    known = _known_viewpoint_slugs()
    for scenario in scenarios.values():
        for label, ref in _iter_route_refs(scenario):
            if ref["kind"] == "viewpoint":
                assert ref["ref"] in known, f"{label}: no such viewpoint {ref['ref']!r}"


def test_doc_references_resolve_to_existing_pages(scenarios: dict[str, dict[str, Any]]) -> None:
    for scenario in scenarios.values():
        for label, ref in _iter_route_refs(scenario):
            if ref["kind"] == "doc":
                assert (_REPO_ROOT / str(ref["ref"])).is_file(), f"{label}: no such page {ref['ref']!r}"


def test_cli_references_resolve_to_console_scripts(scenarios: dict[str, dict[str, Any]]) -> None:
    known = _known_cli_entry_points()
    for scenario in scenarios.values():
        for label, ref in _iter_route_refs(scenario):
            if ref["kind"] == "cli":
                assert ref["ref"] in known, f"{label}: no such console script {ref['ref']!r}"
