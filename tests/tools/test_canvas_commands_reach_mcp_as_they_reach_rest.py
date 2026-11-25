"""Every canvas command an agent can do through MCP with the result the canvas gets through REST (A-02.41).

`tests/fixtures/canvas_commands.json` lists each command of the canvas editor with the named operation it is
on the diagram page and on a candidate's, and the request that carries it. Each request is sent through
REST to one copy of a model and through MCP to another, and the two repositories must then be the same,
file for file. The request must also state the command's operation as the backend reads it
(`operation_catalog`), which is what a policy is decided on. The GUI's own table is held to the same
fixture by `canvasCommands.test.ts`.
"""

from __future__ import annotations

import difflib
import json
import re
import shutil
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter

from src.application.artifacts.repository import ArtifactRepository
from src.domain.artifact_id import stable_id
from src.domain.repository.frontmatter import parse_frontmatter
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.candidate_wire import CandidateHeader, RecordedEdit
from src.infrastructure.diagram_composition import DiagramReplacement
from src.infrastructure.diagram_layout_wire import LayoutPatch
from src.infrastructure.mcp.artifact_mcp import candidate_tools
from src.infrastructure.mcp.artifact_mcp.layout_tools import artifact_arrange_diagram, artifact_replace_diagram
from src.infrastructure.operation_catalog import (
    OPERATION_CATALOG,
    arrangement_operations,
    recorded_operations,
    replacement_operations,
)
from src.infrastructure.rest.routers import candidates
from src.infrastructure.rest.routers import state as s
from src.infrastructure.rest.routers.diagrams.router import router as diagrams_router
from tests.support.api_app import build_api_app
from tests.support.rendered_pictures import RenderedModel, build_rendered_model, plantuml_available
from tests.support.rest_state import reset_state_for_test

pytestmark = pytest.mark.skipif(not plantuml_available(), reason="plantuml.jar not found")

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "canvas_commands.json"
COMMANDS: list[dict[str, Any]] = json.loads(FIXTURE.read_text(encoding="utf-8"))["commands"]
SCENE = "groupings"
NEW_ELEMENT = "APP@1790000000.LdgrAbC.ledger"
CANDIDATE = "CAND@1790000000.PrtyAbC.parity"
EDITS = TypeAdapter(list[RecordedEdit])
_TIMESTAMP = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?(Z|[+-]\d\d:\d\d)?")
#: A box made in the write is given an id of its own on each side.
_MINTED_BOX = re.compile(r"\bg-[A-Za-z0-9]{6}\b")
#: What revision of its model a candidate was recorded against is read from where the model is.
_REVISION = re.compile(r"repository-revision: .*")


def _writing(page: str) -> list[Any]:
    return [pytest.param(one, id=one["command"]) for one in COMMANDS if one[page]["operation"] is not None]


class _Names:
    """The fixture's placeholders, as this copy of the model spells them."""

    def __init__(self, ids: Mapping[str, str], groupings: list[dict[str, Any]]) -> None:
        self._ids = ids
        self._groupings = {one["label"]: one["id"] for one in _every_grouping(groupings) if "id" in one}

    def _one(self, text: str) -> str:
        kind, _, name = text.partition(":")
        match kind:
            case "$id":
                return self._ids[name]
            case "$key":
                return stable_id(self._ids[name])
            case "$rel":
                source, connection_type, target = name.split(" ")
                return f"{stable_id(self._ids[source])}---{stable_id(self._ids[target])}@@{connection_type}"
            case "$grouping":
                return self._groupings[name]
            case "$new":
                return NEW_ELEMENT
        return text

    def entity(self, named: str) -> str:
        """An entity a request adds or drops: by nickname, or by a placeholder."""
        return self._one(named if named.startswith("$") else f"$id:{named}")

    def __call__(self, value: Any) -> Any:
        if isinstance(value, str):
            return self._one(value) if value.startswith("$") else value
        if isinstance(value, list):
            return [self(one) for one in value]
        if isinstance(value, dict):
            return {self(key): self(one) for key, one in value.items()}
        return value


def _every_grouping(groupings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [found for one in groupings for found in (one, *_every_grouping(one.get("groups", [])))]


def _ends(connection: str) -> set[str]:
    source, _, rest = connection.partition("---")
    return {stable_id(source), stable_id(rest.partition("@@")[0])}


def _stored(path: Path) -> dict[str, Any]:
    return parse_frontmatter(path.read_text(encoding="utf-8"))


def _names(model: RenderedModel, path: Path) -> _Names:
    return _Names(model.ids, _stored(path).get("authored-groupings") or [])


def _replacement(path: Path, request: Mapping[str, Any], names: _Names) -> dict[str, Any]:
    """The diagram as stored, with what *request* changes in it, as the canvas sends a save."""
    stored = _stored(path)
    dropped = {stable_id(names.entity(one)) for one in request.get("drop_entities", [])}
    unlinked = {stable_id(one) for one in names(request.get("drop_connections", []))}
    added = [names.entity(one) for one in request.get("add_entities", [])]
    return {
        "diagram_type": stored["diagram-type"], "name": stored["name"],
        "entity_ids": [one for one in stored["entity-ids-used"] if stable_id(one) not in dropped] + added,
        "connection_ids": [
            one for one in stored["connection-ids-used"]
            if not (_ends(one) & dropped) and stable_id(one) not in unlinked
        ] + names(request.get("add_connections", [])),
        "authored_groupings": stored.get("authored-groupings"), "diagram_entities": stored.get("diagram-entities"),
        "dry_run": False, **names(request.get("fields", {})),
    }


def _text(path: Path) -> str:
    text = path.read_bytes().decode("utf-8", errors="replace")
    return _REVISION.sub("repository-revision: <read>", _MINTED_BOX.sub("g-<new>", _TIMESTAMP.sub("<when>", text)))


def _tree(repo: Path) -> dict[str, str]:
    """Every file of the repository, as text, with the moments things were written at and new box ids taken out."""
    return {
        str(path.relative_to(repo)): _text(path)
        for path in sorted(repo.rglob("*"))
        if path.is_file() and not any(part.startswith(".") for part in path.relative_to(repo).parts)
    }


def _assert_same(over_rest: Path, over_mcp: Path) -> None:
    """The two repositories hold the same files with the same text; where not, the lines that differ."""
    rest, mcp = _tree(over_rest), _tree(over_mcp)
    assert rest.keys() == mcp.keys()
    differences = [
        "\n".join(difflib.unified_diff(rest[name].splitlines(), mcp[name].splitlines(), name, name, lineterm=""))
        for name in rest if rest[name] != mcp[name]
    ]
    assert not differences, "\n".join(differences)


@pytest.fixture(scope="module")
def original(tmp_path_factory: pytest.TempPathFactory) -> RenderedModel:
    return build_rendered_model(tmp_path_factory.mktemp("canvas-commands"))


def _copied(original: RenderedModel, into: Path) -> RenderedModel:
    shutil.copytree(original.repo, into, ignore=shutil.ignore_patterns(".arch*"))
    return RenderedModel(repo=into, ids=original.ids, scenes={
        name: type(scene)(path=into / scene.path.relative_to(original.repo), body=scene.body, svg=scene.svg)
        for name, scene in original.scenes.items()
    })


@pytest.fixture
def sides(original: RenderedModel, tmp_path: Path) -> Iterator[tuple[RenderedModel, RenderedModel, TestClient]]:
    """Two copies of the model: one the REST client writes, the other MCP."""
    over_rest, over_mcp = _copied(original, tmp_path / "rest"), _copied(original, tmp_path / "mcp")
    s.init_state(ArtifactRepository(shared_artifact_index([over_rest.repo])), over_rest.repo, None)
    try:
        with TestClient(build_api_app(diagrams_router, candidates.router)) as client:
            yield over_rest, over_mcp, client
    finally:
        reset_state_for_test()



def _over_rest(model: RenderedModel, client: TestClient, request: Mapping[str, Any]) -> frozenset[str]:
    path = Path(model.scenes[SCENE].path)
    names = _names(model, path)
    if request["carrier"] == "patch":
        patch = names(request["patch"])
        answer = client.patch(f"/api/diagrams/{path.stem}/layout", json={"patch": patch, "dry_run": False})
        stated = arrangement_operations(LayoutPatch.model_validate(patch), None)
    else:
        body = _replacement(path, request, names)
        answer = client.put(f"/api/diagrams/{path.stem}", json=body)
        stated = replacement_operations(DiagramReplacement.model_validate(body))
    assert answer.status_code == 200 and answer.json()["wrote"] is True, answer.text
    return stated


def _over_mcp(model: RenderedModel, request: Mapping[str, Any]) -> None:
    path = Path(model.scenes[SCENE].path)
    names = _names(model, path)
    if request["carrier"] == "patch":
        answer = artifact_arrange_diagram(
            artifact_id=path.stem, patch=LayoutPatch.model_validate(names(request["patch"])), dry_run=False,
            repo_root=str(model.repo),
        )
    else:
        replacement = DiagramReplacement.model_validate(_replacement(path, request, names))
        answer = artifact_replace_diagram(artifact_id=path.stem, replacement=replacement, repo_root=str(model.repo))
    assert answer["wrote"] is True, answer


_CARRIERS = {"replace": ("diagrams_replace_diagram", "artifact_replace_diagram"),
             "patch": ("diagrams_patch_diagram_layout", "artifact_arrange_diagram")}


@pytest.mark.parametrize("command", _writing("diagram"))
def test_a_diagram_command_writes_the_same_over_mcp_as_over_rest(
    command: dict[str, Any], sides: tuple[RenderedModel, RenderedModel, TestClient],
) -> None:
    over_rest, over_mcp, client = sides
    request, operation = command["diagram"]["request"], command["diagram"]["operation"]
    if "given" in request:  # each side through its own surface, so each reads what it wrote
        given = {"carrier": "patch" if "patch" in request["given"] else "replace", **request["given"]}
        _over_rest(over_rest, client, given)
        _over_mcp(over_mcp, given)

    stated = _over_rest(over_rest, client, request)
    _over_mcp(over_mcp, request)

    assert operation in stated
    assert set(_CARRIERS[request["carrier"]]) <= OPERATION_CATALOG[operation].carriers
    _assert_same(over_rest.repo, over_mcp.repo)


def _candidate(model: RenderedModel) -> str:
    header = CandidateHeader.model_validate({"name": "Parity", "id": CANDIDATE, "scope": list(model.ids.values())})
    return str(candidate_tools.change_set_create(header, repo_root=str(model.repo))["version"])


@pytest.mark.parametrize("command", _writing("candidate"))
def test_a_candidate_command_records_the_same_over_mcp_as_over_rest(
    command: dict[str, Any], sides: tuple[RenderedModel, RenderedModel, TestClient],
) -> None:
    over_rest, over_mcp, client = sides
    edits = _Names(over_rest.ids, [])(command["candidate"]["request"]["edits"])
    operation = command["candidate"]["operation"]

    answer = client.post(f"/api/change-sets/{CANDIDATE}/operations",
                         json={"based_on": _candidate(over_rest), "operations": edits})
    candidate_tools.change_set_record(CANDIDATE, _candidate(over_mcp), EDITS.validate_python(edits),
                                      repo_root=str(over_mcp.repo))

    assert answer.status_code == 200, answer.text
    assert operation in recorded_operations(EDITS.validate_python(edits))
    assert {"changes_record_operation", "change_set_record"} <= OPERATION_CATALOG[operation].carriers
    _assert_same(over_rest.repo, over_mcp.repo)


def test_every_command_of_the_fixture_names_an_operation_of_the_catalog_or_none() -> None:
    named = {one[page]["operation"] for one in COMMANDS for page in ("diagram", "candidate")} - {None}
    assert named <= OPERATION_CATALOG.keys()
    assert len({one["command"] for one in COMMANDS}) == len(COMMANDS)
