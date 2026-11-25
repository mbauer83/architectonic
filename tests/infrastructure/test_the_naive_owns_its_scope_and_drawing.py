"""A stress analysis evaluates the architecture its naive candidate holds: the naive owns the scope and the
diagram it is drawn on, and the document names the naive and the context of the evaluation — over REST and
MCP alike. A scope no stored diagram draws is drawn as a generated view (Q36)."""

import json
from collections.abc import Iterator
from pathlib import Path
from shutil import copyfile

import pytest
from fastapi.testclient import TestClient

from src.application.artifacts.parsing import extract_yaml_block
from src.application.artifacts.repository import ArtifactRepository
from src.domain.artifact_id import stable_id
from src.domain.repository.repo_default_stress_analysis import STRESS_ANALYSIS_SCHEMA
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.candidate_wire import CandidateHeader
from src.infrastructure.mcp.artifact_mcp import candidate_tools as mcp
from src.infrastructure.rest.routers import candidates, documents, state
from tests.support.api_app import build_api_app
from tests.support.rest_state import reset_state_for_test
from tests.support.typed_table_documents import repository_in

_SOURCE = Path(__file__).resolve().parents[2] / "engagements/ENG-ARCH-REPO/architecture-repository"
_DIAGRAM = "ARC@1783185029.4Ayzz3.one-enterprise-repository-many-engagements"
_SERVICE = "SRV@1712870400.Uv9Wx9.repository-promotion-service"


def _repository(tmp_path: Path) -> Path:
    root = repository_in(tmp_path)
    for filename in (f"{_DIAGRAM}.puml", f"{_SERVICE}.md"):
        original = next(_SOURCE.rglob(filename))
        target = root / original.relative_to(_SOURCE)
        target.parent.mkdir(parents=True, exist_ok=True)
        copyfile(original, target)
    (root / ".arch-repo/documents/stress-analysis.json").write_text(json.dumps(STRESS_ANALYSIS_SCHEMA))
    return root


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    root = _repository(tmp_path)
    state.init_state(ArtifactRepository(shared_artifact_index([root])), root, None)
    try:
        with TestClient(build_api_app(candidates.router, documents.router)) as served:
            served.root = root  # type: ignore[attr-defined]
            yield served
    finally:
        reset_state_for_test()


def _frontmatter_of(root: Path, document: str) -> dict[str, object]:
    (path,) = root.rglob(f"{document}*.md")
    frontmatter = extract_yaml_block(path.read_text(encoding="utf-8"))
    assert isinstance(frontmatter, dict)
    return frontmatter


def test_a_start_puts_the_scope_and_the_diagram_in_the_naive_and_the_context_in_the_document(
    client: TestClient,
) -> None:
    root = client.root  # type: ignore[attr-defined]
    started = client.post("/api/stress-analyses", json={
        "title": "Stress analysis — promotion", "context": "Volumes double; informs the tiering decision.",
        "naive": {"name": "Naive architecture", "diagram": _DIAGRAM},
    })
    assert started.status_code == 200, started.text
    naive = started.json()["naive_candidate"]["record"]
    assert naive["diagram"] == _DIAGRAM
    assert stable_id(_SERVICE) in naive["scope"]

    frontmatter = _frontmatter_of(root, started.json()["document"])
    assert frontmatter["context"] == "Volumes double; informs the tiering decision."
    assert frontmatter["naive-candidate"] == naive["id"]
    assert {"question", "scope-diagram"}.isdisjoint(frontmatter)

    by_mcp = mcp.analysis_start(
        "Stress analysis — by an agent", CandidateHeader(name="Naive", diagram=_DIAGRAM),
        context="The same evaluation, started by an agent.", repo_root=str(root),
    )
    assert by_mcp["naive_candidate"]["record"]["diagram"] == _DIAGRAM
    assert _frontmatter_of(root, by_mcp["document"])["context"] == "The same evaluation, started by an agent."


def test_an_explicit_scope_is_kept_beside_the_diagram_it_is_drawn_on(client: TestClient) -> None:
    created = client.post("/api/change-sets", json={
        "record": {"name": "Pressed elements", "diagram": _DIAGRAM, "scope": [_SERVICE]},
    })
    assert created.status_code == 200, created.text
    record = created.json()["record"]
    assert (record["scope"], record["diagram"]) == ([stable_id(_SERVICE)], _DIAGRAM)


def test_a_candidate_is_drawn_on_the_diagram_its_stack_names(client: TestClient) -> None:
    naive = client.post("/api/change-sets", json={"record": {"name": "Naive", "diagram": _DIAGRAM}}).json()
    on_top = client.post("/api/change-sets", json={"record": {"name": "On top", "parent": naive["record"]["id"]}})
    ref = on_top.json()["record"]["id"]

    drawn = client.get(f"/api/change-sets/{ref}/diff")

    assert drawn.status_code == 200, drawn.text
    assert drawn.json()["drawing"]["artifact_id"] == _DIAGRAM
    root = client.root  # type: ignore[attr-defined]
    assert mcp.change_set_compare(ref, repo_root=str(root))["drawing"]["artifact_id"] == _DIAGRAM


def test_a_scope_no_diagram_draws_is_drawn_as_a_generated_view(client: TestClient) -> None:
    """Q36: a search or viewpoint scope with no stored diagram is drawn from the scope itself."""
    scoped = client.post("/api/change-sets", json={"record": {"name": "Searched", "scope": [_SERVICE]}}).json()

    drawing = client.get(f"/api/change-sets/{scoped['record']['id']}/diff").json()["drawing"]
    previewed = client.post("/api/scope-drawings", json={"scope": [_SERVICE], "name": "Searched"})

    assert previewed.status_code == 200, previewed.text
    for picture in (drawing, previewed.json()):
        assert [stable_id(element["key"]) for element in picture["elements"]] == [stable_id(_SERVICE)]


def test_a_scope_the_model_does_not_hold_is_refused_rather_than_drawn_empty(client: TestClient) -> None:
    refused = client.post("/api/scope-drawings", json={"scope": ["SRV@1.nope"], "name": "Nothing"})
    assert refused.status_code == 422, refused.text


def test_a_diagram_that_is_not_stored_is_refused_when_a_candidate_names_it(client: TestClient) -> None:
    refused = client.post("/api/change-sets", json={"record": {"name": "Nowhere", "diagram": "ARC@1.nope"}})
    assert refused.status_code == 404, refused.text
